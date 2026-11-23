"""The specialised agents. Each takes structured input and returns structured output."""
import json

from .config import DATA_DIR


def _channel_brief(cfg):
    ch = cfg["channel"]
    rules = "\n".join(f"- {r}" for r in ch["brand_rules"])
    return (f"CHANNEL: {ch['name']} | LANGUAGE: {ch['language']} | NICHES: {', '.join(ch['niches'])}\n"
            f"AUDIENCE: {ch['audience']}\nVOICE: {ch['voice_style']}\nBRAND RULES:\n{rules}\n")


def _read(name):
    p = DATA_DIR / name
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _learnings():
    return _read("learnings.json").get("guidance_for_next_topics", "")


def _playbook(fmt=None):
    pb = _read("creator_playbook.json")
    if not pb:
        return "none yet (run: python run.py creators)"
    keep = {k: pb.get(k) for k in ("hook_patterns", "title_patterns", "ideal_length_sec", "structure_patterns",
                                     "what_audiences_love", "avoid")}
    if fmt and pb.get("by_format", {}).get(fmt):
        keep["format_specific"] = pb["by_format"][fmt]
    return json.dumps(keep, ensure_ascii=False)[:3000]


def _bible(fmt=None):
    b = _read("series_bible.json")
    if not b:
        return "none yet"
    series = [x for x in b.get("series", []) if not fmt or x.get("format") == fmt]
    return json.dumps({"positioning": b.get("page_positioning"), "brand_voice": b.get("brand_voice"),
                       "series": [{k: x.get(k) for k in ("name", "format", "premise", "recurring_elements")} for x in series],
                       "characters": b.get("recurring_characters", []) if fmt != "story" else []},
                      ensure_ascii=False)[:3500]


FORMAT_DESC = {
    "story": "MYSTERY / FASCINATING FACTS / STORYTELLING: true, verifiable stories told with suspense by one narrator",
    "skit": "COMEDY / ENTERTAINMENT / RELATABLE SKIT: original fictional short skit with 1-3 recurring characters",
}


# ---------------------------------------------------------------- Trend Research
def trend_agent(llm, cfg, recent_topics, fmt="story", n=None):
    from .roster import brief_block, select
    n = n or cfg["daily"]["candidate_topics"]
    prompt = f"""You are the Trend Research desk of a YouTube Shorts / Instagram Reels page, working as these specialists:
{brief_block(select("trend", fmt))}
{_channel_brief(cfg)}
FORMAT FOR THIS BATCH: {FORMAT_DESC[fmt]}
SERIES ON THE PAGE (assign each idea to one): {_bible(fmt)}
PATTERNS LEARNED FROM TOP CREATORS: {_playbook(fmt)}

Use Google Search to find what Indian audiences care about right now, plus strong evergreen ideas.
Propose exactly {n} candidate ideas for 35-58 second vertical videos in this format.

Do NOT repeat or closely resemble these recent topics:
{json.dumps(recent_topics[-60:], ensure_ascii=False)}

Lessons from past performance (may be empty):
{_learnings() or 'none yet'}

{"Each topic must be sourceable (credible public sources exist) and allow ORIGINAL narration and analysis." if fmt == "story" else
 "Each idea must be an ORIGINAL relatable situation (no copying other creators' skits), shootable cheaply, and offend no group. Sourceability = how universally relatable it is."}
Score each 1-10: demand (search/social interest), originality (fresh angle possible), relevance (fits channel),
competition_gap (10 = few good videos on it), evergreen (stays interesting for months), sourceability.

Return ONLY JSON:
{{"topics":[{{"topic":"short English title","angle":"the specific original angle","niche":"one of the niches","series":"series name or ''",
"why_now":"evidence of interest","demand":0,"originality":0,"relevance":0,"competition_gap":0,"evergreen":0,"sourceability":0}}]}}"""
    data, _ = llm.json("trend", prompt, tier="fast", search=True, creative=True)
    topics = data.get("topics", [])
    for t in topics:
        t["format"] = fmt
    return topics


def score_topic(t, weights):
    s = 0.0
    for k, w in weights.items():
        try:
            s += float(t.get(k, 0)) * w
        except (TypeError, ValueError):
            pass
    if float(t.get("sourceability", 10) or 0) < 5:   # hard gate: must be sourceable
        s -= 5
    return round(s, 2)


# ---------------------------------------------------------------- Research
def research_agent(llm, cfg, job):
    t = job["topic_detail"]
    if job.get("format") == "skit":
        prompt = f"""You are the Research desk for a comedy skit. Idea: "{t['topic']}". Angle: "{t.get('angle','')}".
Use Google Search to understand how Indian people talk about this situation online (memes, complaints, common phrases).
Do NOT collect other creators' jokes or scripts - only the real-life situation and vocabulary.
Return ONLY JSON:
{{"summary":"what makes this situation relatable","situations":["specific real-life beats people recognise"],
"vocabulary":["words/phrases people actually use"],"sensitivities":["what to avoid so no group is mocked"],
"key_facts":[],"uncertainties":[],"do_not_say":[],"sufficient":true}}"""
        data, sources = llm.json("research", prompt, tier="fast", search=True, job_id=job["job_id"])
        data["grounding_sources"] = sources
        return data
    prompt = f"""You are the Research Agent. Topic: "{t['topic']}". Angle: "{t.get('angle','')}".
Use Google Search. Collect facts a 45-second explainer needs. Prefer primary sources, reputable media,
journals, official sites. Never invent a source, date, number or quote. If something is disputed or a theory, say so.

Return ONLY JSON:
{{"summary":"3-4 sentence neutral summary",
"key_facts":[{{"claim":"one factual statement","source_url":"exact URL","source_title":"","published":"date or unknown","confidence":"high|medium|low"}}],
"uncertainties":["what is unproven or disputed"],
"do_not_say":["tempting but false/unsupported claims to avoid"],
"sufficient":true}}
Give 5-8 key_facts. Set sufficient=false if credible sources are too thin."""
    data, sources = llm.json("research", prompt, tier="smart", search=True, job_id=job["job_id"])
    data["grounding_sources"] = sources
    return data


# ---------------------------------------------------------------- Script
def script_agent(llm, cfg, job):
    from .roster import brief_block, select
    lo, hi = cfg["daily"]["short_duration_sec"]
    fb = job.get("feedback") or []
    fb_txt = "\n".join(f"- {f}" for f in fb[-10:]) or "none"
    if job.get("format") == "skit":
        return _skit_script(llm, cfg, job, lo, hi, fb_txt)
    prompt = f"""You are the Scriptwriting desk, working as these specialists:
{brief_block(select("script", "story"))}
{_channel_brief(cfg)}
SERIES: {job['topic_detail'].get('series','')}  |  PAGE SERIES BIBLE: {_bible("story")}
PATTERNS LEARNED FROM TOP CREATORS (adapt, never copy): {_playbook("story")}
TOPIC: {job['topic']}
ANGLE: {job['topic_detail'].get('angle','')}
RESEARCH (use ONLY these facts; respect uncertainties and do_not_say):
{json.dumps(job['research'], ensure_ascii=False)[:9000]}

CORRECTIONS FROM PREVIOUS REVIEW (must all be fixed):
{fb_txt}

Write an ORIGINAL vertical short of {lo}-{hi} seconds when spoken (about 2.3 Hindi words per second).
Structure: hook (first 2 seconds, honest curiosity, no clickbait lie) -> 5-7 scenes -> satisfying ending + soft CTA.
- "narration": natural spoken Hindi in Devanagari, English tech words kept in English (Hinglish feel). This is read by a TTS voice.
- "caption": the same line in Roman-script Hinglish for on-screen captions.
- "visual_query": 2-4 English words to search stock video (concrete, filmable: "server room lights", "brain scan").
- "veo_prompt": a cinematic 8-second vertical video prompt in English for an AI video generator, no real people's likeness, no logos.
- "on_screen_text": max 4 words of big text (English or Roman Hinglish), or "".
Every factual sentence must map to a research claim; list them in claims_used.

Return ONLY JSON:
{{"working_title":"","hook":"Devanagari hook line (also scene 1 narration start)",
"scenes":[{{"n":1,"narration":"","caption":"","visual_query":"","veo_prompt":"","on_screen_text":""}}],
"ending":"", "est_duration_sec":0, "claims_used":["exact factual claims stated in the script"]}}"""
    data, _ = llm.json("script", prompt, tier="fast", creative=True, job_id=job["job_id"])
    for i, s in enumerate(data.get("scenes", []), 1):
        s["n"] = i
        s.setdefault("voice", "narrator")
    return data


def _skit_script(llm, cfg, job, lo, hi, fb_txt):
    from .roster import brief_block, select
    prompt = f"""You are the Comedy Writers' Room, working as these specialists:
{brief_block(select("script", "skit"))}
{_channel_brief(cfg)}
IDEA: {job['topic']}  |  ANGLE: {job['topic_detail'].get('angle','')}  |  SERIES: {job['topic_detail'].get('series','')}
PAGE SERIES BIBLE + RECURRING CHARACTERS (reuse them when they fit): {_bible("skit")}
RELATABILITY RESEARCH: {json.dumps(job['research'], ensure_ascii=False)[:4000]}
PATTERNS LEARNED FROM TOP CREATORS (adapt, never copy jokes): {_playbook("skit")}
CORRECTIONS FROM PREVIOUS REVIEW (must all be fixed):
{fb_txt}

Write an ORIGINAL {lo}-{hi} second skit (about 2.5 Hindi words per second) with 2-3 characters.
- Line 1 must hook instantly (relatable POV or conflict). Escalate. Punchline near the end, optional tag/callback.
- No stereotypes about caste, religion, region, gender, body or disability. No real people or brands mocked.
- Each scene = one line of dialogue (or a short narrator line).
- "speaker": character name or "Narrator". "voice": male | female | narrator.
- "narration": the spoken line in natural Hindi (Devanagari), English words kept in English. Read by TTS.
- "caption": same line in Roman Hinglish.
- "visual_query": 2-4 English words for a stock clip of the setting/reaction.
- "veo_prompt": 8-second 9:16 cinematic prompt for this beat, fictional people only, no logos.
- "shot": how to film this line on a phone (angle, location, prop, expression).
- "on_screen_text": max 4 words or "".

Return ONLY JSON:
{{"working_title":"","hook":"","characters":[{{"name":"","voice":"male|female","personality":""}}],
"scenes":[{{"n":1,"speaker":"","voice":"","narration":"","caption":"","visual_query":"","veo_prompt":"","shot":"","on_screen_text":""}}],
"ending":"","est_duration_sec":0,"claims_used":[]}}"""
    data, _ = llm.json("script", prompt, tier="fast", creative=True, job_id=job["job_id"])
    for i, s in enumerate(data.get("scenes", []), 1):
        s["n"] = i
    return data


# ---------------------------------------------------------------- Fact-check
def factcheck_agent(llm, cfg, job):
    sc = job["script"]
    narration = "\n".join(f"[{s['n']}] {s.get('speaker', '')} {s['narration']}" for s in sc["scenes"])
    if job.get("format") == "skit":
        prompt = f"""You are the Trust & Safety checker for a FICTIONAL comedy skit. Jokes need not be factual.
Check only: (1) any statement presented as a real fact that is false, (2) any real person or brand defamed or mocked,
(3) jokes built on caste, religion, region, gender, body or disability stereotypes, (4) copied well-known jokes/catchphrases
of other creators, (5) platform policy risks.
SKIT:
{narration}
Return ONLY JSON:
{{"verdict":"pass|revise|reject","claims":[{{"scene":1,"claim":"","status":"supported|unsupported|misleading|opinion_ok","evidence_url":"","fix":""}}],"notes":""}}"""
        data, _ = llm.json("fact_check", prompt, tier="fast", job_id=job["job_id"])
        return data
    prompt = f"""You are the Fact-Checking Agent. Verify every material factual claim in this Hindi/Hinglish script.
Use Google Search to check independently, and compare with the research notes.
SCRIPT:
{narration}
CLAIMS LISTED BY WRITER: {json.dumps(sc.get('claims_used', []), ensure_ascii=False)}
RESEARCH NOTES: {json.dumps(job['research'].get('key_facts', []), ensure_ascii=False)[:6000]}

Status per claim: supported | unsupported | misleading | opinion_ok.
verdict = "pass" only if no unsupported or misleading MATERIAL claim remains.
verdict = "revise" if fixable (give exact fix). verdict = "reject" if the topic itself rests on false premises.

Return ONLY JSON:
{{"verdict":"pass|revise|reject","claims":[{{"scene":1,"claim":"","status":"","evidence_url":"","fix":""}}],"notes":""}}"""
    data, sources = llm.json("fact_check", prompt, tier="smart", search=True, job_id=job["job_id"])
    data["grounding_sources"] = sources
    return data


# ---------------------------------------------------------------- Distribution
def distribution_agent(llm, cfg, job):
    sc = job["script"]
    from .roster import brief_block, select
    prompt = f"""You are the Distribution & Growth desk, working as these specialists:
{brief_block(select("distribution", job.get("format")))}
Prepare honest, platform-specific metadata.
{_channel_brief(cfg)}
FORMAT: {FORMAT_DESC.get(job.get("format"), "")}  |  SERIES: {job['topic_detail'].get('series','')}
TITLE PATTERNS THAT WIN FOR TOP CREATORS (adapt honestly): {_playbook(job.get("format"))}
TOPIC: {job['topic']}
SCRIPT CAPTIONS: {json.dumps([s['caption'] for s in sc['scenes']], ensure_ascii=False)}
SOURCES: {json.dumps(job['source_urls'][:8])}
VISUAL SOURCES USED: {json.dumps(sorted({r['source'] for r in job.get('rights', [])}))}

Rules: title/caption must accurately represent the video (no misleading promise). Hinglish in Roman script.
YouTube Shorts title max 90 chars incl. #shorts. Description: 2-3 lines + "Sources:" list of the URLs + hashtags.
Instagram caption: hook line, 2 short lines, CTA, 8-12 hashtags.
synthetic_disclosure = true if any realistic AI-generated video/voice could be mistaken for real footage or a real person.

Return ONLY JSON:
{{"youtube":{{"title":"","description":"","tags":[""]}},
"instagram":{{"caption":""}},
"thumbnail_text":"max 4 words","pinned_comment":"a question that invites comments",
"synthetic_disclosure":false,"disclosure_reason":""}}"""
    data, _ = llm.json("distribution", prompt, tier="fast", creative=True, job_id=job["job_id"])
    return data


# ---------------------------------------------------------------- Editorial QC (LLM half of QC)
def editorial_qc_agent(llm, cfg, job):
    sc, dist = job["script"], job["distribution"]
    prompt = f"""You are the Quality Control Agent (editorial checks). Be strict but fair.
{_channel_brief(cfg)}
SCRIPT: {json.dumps(sc, ensure_ascii=False)[:7000]}
FACT-CHECK RESULT: {json.dumps(job['fact_check'], ensure_ascii=False)[:3000]}
METADATA: {json.dumps(dist, ensure_ascii=False)[:3000]}

Check each item and answer pass true/false with a specific correction if false:
hook_honest - opening hook is clear, relevant, no deceptive promise
original - original narration/analysis, not filler or a rehash
claims_supported - material claims are supported per the fact-check
metadata_accurate - title, captions, description, thumbnail text represent the content truthfully
visual_fit - visual queries/prompts match narration and won't create a misleading factual impression
disclosure - synthetic-media disclosure decision is correct
pacing - runs 35-58 s, no dead scenes, ending lands

Return ONLY JSON:
{{"checks":[{{"id":"hook_honest","pass":true,"owner":"script|distribution|production","correction":""}}],"overall_notes":""}}"""
    data, _ = llm.json("qc_editorial", prompt, tier="smart", job_id=job["job_id"])
    return data


# ---------------------------------------------------------------- Analytics review
def analytics_agent(llm, cfg, rows):
    from .roster import brief_block, select
    prompt = f"""You are the Analytics & Learning department, working as:
{brief_block(select("analytics", None, 14))}
Here are per-video results (period noted per row; format = story or skit):
{json.dumps(rows, ensure_ascii=False)[:12000]}
Judge on retention/engagement signals (likes, comments, shares per view, subscribers) - not views alone.
Small samples are noisy: say so when evidence is weak.
Return ONLY JSON:
{{"top_subjects":[""],"what_worked":[""],"what_failed":[""],
"experiments_next_week":[""],"recommended_mix":{{"story":0,"skit":0}},
"guidance_for_next_topics":"one paragraph the Trend and Script agents will read"}}"""
    data, _ = llm.json("analytics", prompt, tier="smart")
    return data


# ---------------------------------------------------------------- Storyline / series bible
def plan_agent(llm, cfg):
    from .roster import brief_block, select
    prompt = f"""You are the Strategy & Storyline department of a new Hindi/Hinglish Shorts + Reels page, working as:
{brief_block(select("plan", None, 20))}
{_channel_brief(cfg)}
FORMATS: {json.dumps(FORMAT_DESC)}
DAILY MIX: {json.dumps(cfg["daily"]["formats"])}
PATTERNS LEARNED FROM TOP CREATORS: {_playbook()}
Use Google Search to check what similar Indian pages already do, so our positioning is distinct.

Design the page's storyline system. All names, series and characters must be ORIGINAL (not other creators').
Return ONLY JSON:
{{"page_positioning":"one line","brand_voice":"","audience_personas":[{{"name":"","wants":""}}],
"series":[{{"name":"","format":"story|skit","premise":"","recurring_elements":[""],"episode_ideas":["10 ideas"],"best_days":[""]}}],
"recurring_characters":[{{"name":"","voice":"male|female","personality":"","catchphrase":"original","look":""}}],
"weekly_calendar":[{{"day":"Mon","slots":[{{"format":"","series":"","time_ist":""}}]}}],
"community_rituals":[""],"visual_identity":{{"story":"","skit":""}},"monetisation_path":""}}
Make 3-5 series (mix of story and skit) and 2-4 recurring skit characters."""
    data, _ = llm.json("plan", prompt, tier="smart", search=True, creative=True)
    return data


# ---------------------------------------------------------------- Learn from top creators
def creator_study_agent(llm, cfg, evidence):
    from .roster import brief_block, select
    prompt = f"""You are the Creator Intelligence department, working as:
{brief_block(select("creator_study", None, 12))}
Our page: {_channel_brief(cfg)}
EVIDENCE about top creators' best-performing recent videos (views per day = strength signal):
{json.dumps(evidence, ensure_ascii=False)[:14000]}
If evidence is thin, use Google Search to study these creators' public pages.

Extract PATTERNS we can learn from (structure, hook types, length, packaging, cadence, series formats).
Never output their jokes, scripts, characters or catchphrases to copy. Say where the evidence is weak.
Return ONLY JSON:
{{"hook_patterns":[""],"title_patterns":[""],"ideal_length_sec":{{"story":0,"skit":0}},
"structure_patterns":[""],"posting_cadence":"","series_formats":[""],"what_audiences_love":[""],
"by_format":{{"story":[""],"skit":[""]}},"avoid":[""],"adapt_for_us":["concrete moves for our page"],
"evidence_strength":"strong|medium|weak"}}"""
    data, _ = llm.json("creator_study", prompt, tier="smart", search=True)
    return data
