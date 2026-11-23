"""Gemini wrapper: JSON answers, optional Google Search grounding, retries, usage log.

provider: mock  -> canned answers so the whole pipeline can be tested offline.
"""
import json
import re
import time

from . import db
from .config import secret


class LLMError(Exception):
    pass


def _extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    try:
        return json.loads(text)
    except Exception:
        pass
    for open_c, close_c in (("{", "}"), ("[", "]")):
        s, e = text.find(open_c), text.rfind(close_c)
        if s != -1 and e > s:
            try:
                return json.loads(text[s:e + 1])
            except Exception:
                continue
    raise LLMError(f"Model did not return valid JSON: {text[:300]}")


class LLM:
    def __init__(self, cfg):
        self.cfg = cfg
        self.provider = cfg["models"]["provider"]
        self.client = None
        if self.provider == "gemini":
            key = secret("GEMINI_API_KEY")
            if not key:
                raise LLMError("GEMINI_API_KEY missing in .env (get one free at aistudio.google.com/apikey)")
            from google import genai
            self.client = genai.Client(api_key=key)

    def json(self, task, prompt, tier="fast", search=False, creative=False, job_id=None):
        """Return (parsed_json, sources[list of {url,title}])."""
        if self.provider == "mock":
            from .mock import mock_answer
            return mock_answer(task, prompt), [{"url": "https://example.org/mock-source", "title": "Mock source"}]

        from google.genai import types
        model = self.cfg["models"][tier]
        temp = self.cfg["models"]["temperature_creative" if creative else "temperature_strict"]
        kwargs = {"temperature": temp}
        if search:
            # Grounded answers can't use JSON mode, so JSON is requested in the prompt.
            kwargs["tools"] = [types.Tool(google_search=types.GoogleSearch())]
        else:
            kwargs["response_mime_type"] = "application/json"
        conf = types.GenerateContentConfig(**kwargs)

        last = None
        for attempt in range(4):
            try:
                resp = self.client.models.generate_content(model=model, contents=prompt, config=conf)
                tokens = getattr(getattr(resp, "usage_metadata", None), "total_token_count", 0)
                data = _extract_json(resp.text)
                db.log_usage(job_id, task, model, tokens, True)
                return data, self._sources(resp)
            except Exception as e:  # rate limits / server errors / bad JSON -> limited retry
                last = e
                db.log_usage(job_id, task, model, 0, False)
                msg = str(e)
                wait = 20 * (attempt + 1) if ("429" in msg or "RESOURCE_EXHAUSTED" in msg) else 4 * (attempt + 1)
                print(f"    ! {task} attempt {attempt + 1} failed: {msg[:150]}  (retry in {wait}s)")
                time.sleep(wait)
        raise LLMError(f"{task} failed after retries: {last}")

    @staticmethod
    def _sources(resp):
        out = []
        try:
            gm = resp.candidates[0].grounding_metadata
            for ch in (gm.grounding_chunks or []):
                if ch.web and ch.web.uri:
                    out.append({"url": ch.web.uri, "title": ch.web.title or ""})
        except Exception:
            pass
        return out

    def ping(self):
        if self.provider == "mock":
            return True, "mock mode"
        try:
            r = self.client.models.generate_content(model=self.cfg["models"]["fast"], contents="Reply with the word OK")
            return "OK" in (r.text or "").upper(), (r.text or "").strip()[:40]
        except Exception as e:
            return False, str(e)[:200]
