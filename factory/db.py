"""Shared job record store (SQLite) - the single source of truth for every agent.

Every status change is written to the events table with timestamp, agent,
result and reason (audit trail).
"""
import json
import sqlite3
from datetime import datetime

from .config import DATA_DIR

DB_PATH = DATA_DIR / "factory.db"

STATUSES = [
    "queued", "researching", "topic_selected", "scripting", "fact_check",
    "production", "quality_check", "awaiting_approval", "ready_to_publish",
    "publishing", "published", "analytics_pending", "complete",
]
TERMINAL = {"complete", "rejected", "blocked", "failed"}
STOPPED = TERMINAL | {"needs_human_review", "awaiting_approval"}


def now():
    return datetime.now().isoformat(timespec="seconds")


def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("""CREATE TABLE IF NOT EXISTS jobs(
        job_id TEXT PRIMARY KEY, status TEXT, data TEXT, created TEXT, updated TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, ts TEXT, agent TEXT,
        from_status TEXT, to_status TEXT, result TEXT, reason TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS usage(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, job_id TEXT, agent TEXT,
        model TEXT, tokens INTEGER, ok INTEGER)""")
    c.execute("""CREATE TABLE IF NOT EXISTS topics_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, topic TEXT, score REAL,
        selected INTEGER, reason TEXT)""")
    return c


def new_job_id():
    year = datetime.now().year
    with _conn() as c:
        n = c.execute("SELECT COUNT(*) FROM jobs WHERE job_id LIKE ?", (f"CONTENT-{year}-%",)).fetchone()[0]
    return f"CONTENT-{year}-{n + 1:03d}"


def blank_job(cfg, topic, score, content_type="youtube_short"):
    """The shared JSON contract from the blueprint, plus working fields."""
    return {
        "job_id": new_job_id(),
        "channel": cfg["channel"]["name"],
        "language": cfg["channel"]["language"],
        "content_type": content_type,
        "format": topic.get("format", "story"),
        "topic": topic["topic"],
        "topic_detail": topic,
        "topic_score": score,
        "source_urls": [],
        "status": "topic_selected",
        "assigned_agent": "research",
        "script_status": "pending",
        "fact_check_status": "pending",
        "production_status": "pending",
        "quality_status": "pending",
        "publishing_status": "draft",
        "approval_required": bool(cfg["publishing"]["require_approval"]),
        "approval": None,
        "asset_urls": [],
        "rights": [],
        "youtube_url": None,
        "instagram_url": None,
        "analytics": {},
        "retry_count": 0,
        "error_log": [],
        "feedback": [],
        "research": None, "script": None, "fact_check": None,
        "qc": None, "distribution": None,
        "created": now(), "updated": now(),
    }


def create(job):
    with _conn() as c:
        c.execute("INSERT INTO jobs VALUES(?,?,?,?,?)",
                  (job["job_id"], job["status"], json.dumps(job, ensure_ascii=False), job["created"], job["updated"]))
        c.execute("INSERT INTO events(job_id,ts,agent,from_status,to_status,result,reason) VALUES(?,?,?,?,?,?,?)",
                  (job["job_id"], now(), "orchestrator", None, job["status"], "created",
                   f"topic score {job['topic_score']}"))
    return job


def save(job):
    job["updated"] = now()
    with _conn() as c:
        c.execute("UPDATE jobs SET status=?, data=?, updated=? WHERE job_id=?",
                  (job["status"], json.dumps(job, ensure_ascii=False), job["updated"], job["job_id"]))


def transition(job, to_status, agent, result, reason=""):
    frm = job["status"]
    job["status"] = to_status
    save(job)
    with _conn() as c:
        c.execute("INSERT INTO events(job_id,ts,agent,from_status,to_status,result,reason) VALUES(?,?,?,?,?,?,?)",
                  (job["job_id"], now(), agent, frm, to_status, result, reason[:1000]))
    print(f"  [{job['job_id']}] {frm} -> {to_status}  ({agent}: {result}) {reason[:120]}")


def log_error(job, agent, message):
    job["error_log"].append({"ts": now(), "agent": agent, "error": str(message)[:2000]})
    save(job)


def get(job_id):
    with _conn() as c:
        r = c.execute("SELECT data FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    if not r:
        raise SystemExit(f"No job {job_id}")
    return json.loads(r["data"])


def all_jobs(status=None):
    with _conn() as c:
        if status:
            rows = c.execute("SELECT data FROM jobs WHERE status=? ORDER BY job_id", (status,)).fetchall()
        else:
            rows = c.execute("SELECT data FROM jobs ORDER BY job_id").fetchall()
    return [json.loads(r["data"]) for r in rows]


def events(job_id=None, limit=500):
    with _conn() as c:
        if job_id:
            rows = c.execute("SELECT * FROM events WHERE job_id=? ORDER BY id", (job_id,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def log_usage(job_id, agent, model, tokens, ok):
    with _conn() as c:
        c.execute("INSERT INTO usage(ts,job_id,agent,model,tokens,ok) VALUES(?,?,?,?,?,?)",
                  (now(), job_id, agent, model, tokens or 0, 1 if ok else 0))


def usage_summary():
    with _conn() as c:
        rows = c.execute("""SELECT substr(ts,1,10) d, model, COUNT(*) calls, SUM(tokens) tokens,
                            SUM(1-ok) failures FROM usage GROUP BY d, model ORDER BY d DESC""").fetchall()
    return [dict(r) for r in rows]


def log_topics(scored, selected_topics):
    with _conn() as c:
        for t, s in scored:
            sel = t["topic"] in selected_topics
            c.execute("INSERT INTO topics_log(ts,topic,score,selected,reason) VALUES(?,?,?,?,?)",
                      (now(), t["topic"], s, 1 if sel else 0, t.get("why_now", "")))


def topics_log(days=30):
    with _conn() as c:
        rows = c.execute("SELECT * FROM topics_log ORDER BY id DESC LIMIT 500").fetchall()
    return [dict(r) for r in rows]
