"""Creator Intelligence: read public stats of the top channels you list, then let the
specialists extract patterns (never content) into data/creator_playbook.json."""
import json
import re
from datetime import datetime, timezone

import requests

from .agents import creator_study_agent
from .config import DATA_DIR, secret

API = "https://www.googleapis.com/youtube/v3"


def _get(path, **params):
    params["key"] = secret("YOUTUBE_API_KEY")
    r = requests.get(f"{API}/{path}", params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _iso_dur(s):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    return sum(int(x or 0) * k for x, k in zip(m.groups(), (3600, 60, 1))) if m else 0


def channel_evidence(handle, fmt, per_channel=50, top=12):
    h = handle if handle.startswith("@") else "@" + handle
    ch = _get("channels", part="contentDetails,statistics,snippet", forHandle=h).get("items", [])
    if not ch:
        return {"handle": h, "error": "channel not found"}
    ch = ch[0]
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    items = _get("playlistItems", part="contentDetails", playlistId=uploads, maxResults=per_channel).get("items", [])
    ids = [i["contentDetails"]["videoId"] for i in items]
    vids = _get("videos", part="snippet,statistics,contentDetails", id=",".join(ids)).get("items", []) if ids else []
    now = datetime.now(timezone.utc)
    rows = []
    for v in vids:
        pub = datetime.fromisoformat(v["snippet"]["publishedAt"].replace("Z", "+00:00"))
        age = max((now - pub).days, 1)
        st = v.get("statistics", {})
        views = int(st.get("viewCount", 0))
        rows.append({"title": v["snippet"]["title"], "duration_sec": _iso_dur(v["contentDetails"]["duration"]),
                     "age_days": age, "views": views, "views_per_day": round(views / age),
                     "likes": int(st.get("likeCount", 0)), "comments": int(st.get("commentCount", 0)),
                     "published_weekday": pub.strftime("%a"), "published_hour_utc": pub.hour,
                     "description_start": v["snippet"].get("description", "")[:200]})
    rows.sort(key=lambda r: -r["views_per_day"])
    return {"handle": h, "format": fmt, "channel": ch["snippet"]["title"],
            "subscribers": ch["statistics"].get("subscriberCount"), "videos_sampled": len(rows),
            "uploads_per_week": round(len(rows) / max(rows[-1]["age_days"] / 7, 1), 1) if rows else None,
            "top_videos": rows[:top]}


def study(llm, cfg):
    handles = cfg.get("creators", {}) or {}
    evidence, notes = [], []
    for fmt in ("story", "skit"):
        for h in handles.get(fmt) or []:
            if secret("YOUTUBE_API_KEY"):
                try:
                    evidence.append(channel_evidence(h, fmt))
                    print(f"  studied {h}")
                    continue
                except Exception as e:
                    notes.append(f"{h}: API error {str(e)[:100]}")
            evidence.append({"handle": h, "format": fmt, "note": "no API data - research via Google Search"})
    if not evidence:
        evidence = [{"note": "No creators listed in config.yaml -> creators. Find the top Hindi mystery/story and "
                             "comedy-skit Shorts/Reels pages via Google Search and study them."}]
    pb = creator_study_agent(llm, cfg, evidence)
    pb["studied"] = [e.get("handle") for e in evidence if e.get("handle")]
    pb["updated"] = datetime.now().isoformat(timespec="seconds")
    pb["notes"] = notes
    (DATA_DIR / "creator_playbook.json").write_text(json.dumps(pb, ensure_ascii=False, indent=2), encoding="utf-8")
    (DATA_DIR / "creator_evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    return pb


def playbook_age_days():
    p = DATA_DIR / "creator_playbook.json"
    if not p.exists():
        return None
    try:
        return (datetime.now() - datetime.fromisoformat(json.loads(p.read_text(encoding="utf-8"))["updated"])).days
    except Exception:
        return None
