"""Master Orchestrator: assigns work, enforces gates, routes failures, limits retries."""
import json
import subprocess
from datetime import datetime, timedelta

from . import agents, db, roster
from .config import DATA_DIR, JOBS_DIR, REPORTS_DIR, secret
from .llm import LLM
from .production import ffmpeg_bin, make_thumbnail, produce, write_upload_package
from .publish import upload_youtube, youtube_ready, youtube_stats
from .qc import run_qc


# ------------------------------------------------------------------ readiness
def readiness(cfg, ping=True):
    rows = []
    prov = cfg["models"]["provider"]
    if prov == "mock":
        rows.append(("Gemini (brain)", "MOCK", "offline test mode - set models.provider: gemini"))
    elif not secret("GEMINI_API_KEY"):
        rows.append(("Gemini (brain)", "MISSING", "add GEMINI_API_KEY to .env (aistudio.google.com/apikey)"))
    elif ping:
        try:
            ok, msg = LLM(cfg).ping()
            rows.append(("Gemini (brain)", "READY" if ok else "FAILED", msg))
        except Exception as e:
            rows.append(("Gemini (brain)", "FAILED", str(e)[:120]))
    else:
        rows.append(("Gemini (brain)", "UNTESTED", "key present"))
    try:
        ff = ffmpeg_bin()
        filt = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        rows.append(("ffmpeg (editing)", "READY" if " ass " in filt else "PARTIAL",
                     "captions burn-in OK" if " ass " in filt else "no libass: install full build (winget install Gyan.FFmpeg)"))
    except Exception as e:
        rows.append(("ffmpeg (editing)", "MISSING", str(e)[:120]))
    tp = cfg["tts"]["provider"]
    if tp == "edge":
        try:
            import edge_tts  # noqa
            rows.append(("Voice (Edge TTS)", "UNTESTED", f"installed, voice {cfg['tts']['edge_voice']}"))
        except ImportError:
            rows.append(("Voice (Edge TTS)", "MISSING", "pip install edge-tts"))
    else:
        rows.append((f"Voice ({tp})", "UNTESTED" if tp != "mock" else "MOCK", ""))
    rows.append(("Stock video (Pexels)", "UNTESTED" if secret("PEXELS_API_KEY") else "MISSING",
                 "key present" if secret("PEXELS_API_KEY") else "optional - without it scenes use title cards / your Veo clips"))
    rows.append(("YouTube upload", "READY" if youtube_ready() else "MISSING",
                 "authorised" if youtube_ready() else "optional - run youtube-auth after README step 5"))
    rows.append(("Instagram", "MANUAL", "post from UPLOAD_PACKAGE.txt, then: python run.py mark-ig JOB URL"))
    rows.append(("Daily schedule", "NOT VERIFIED", "set up Windows Task Scheduler with RUN_DAILY.bat (README)"))
    rows.append(("Specialist roster", "READY", f"{len(roster.roster())} specialists in roster.yaml"))
    rows.append(("Series bible", "READY" if (DATA_DIR / "series_bible.json").exists() else "PENDING",
                 "storyline plan" if (DATA_DIR / "series_bible.json").exists() else "created automatically on first daily run (or: python run.py plan)"))
    n_cr = sum(len(v or []) for k, v in (cfg.get("creators") or {}).items() if k in ("story", "skit"))
    rows.append(("Creator study", "READY" if (DATA_DIR / "creator_playbook.json").exists() else "PENDING",
                 f"{n_cr} creators listed; YouTube API key {'present' if secret('YOUTUBE_API_KEY') else 'missing (Google Search fallback)'}"))
    return rows


def print_readiness(rows):
    print("\nCOMPONENT STATUS")
    for c, s, n in rows:
        print(f"  {c:<22} {s:<13} {n}")
    print()


# ------------------------------------------------------------------ handlers (return True = keep going)
def _bump_retry(cfg, job, agent, reason):
    job["retry_count"] += 1
    if job["retry_count"] > cfg["limits"]["max_retries"]:
        db.transition(job, "needs_human_review", agent, "retry limit reached", reason)
        return False
    return True


def h_research(llm, cfg, job):
    job["assigned_agent"] = "research"
    r = agents.research_agent(llm, cfg, job)
    urls = []
    for f in r.get("key_facts", []):
        u = (f.get("source_url") or "").strip()
        if u.startswith("http") and u not in urls:
            urls.append(u)
    for s in r.get("grounding_sources", []):
        if s["url"] not in urls:
            urls.append(s["url"])
    job["research"], job["source_urls"] = r, urls
    if job.get("format") == "skit":
        db.transition(job, "scripting", "research", "ok", f"{len(r.get('situations', []))} relatable beats")
        return True
    if not r.get("sufficient", True) or len(urls) < 2:
        db.transition(job, "rejected", "research", "insufficient sources", f"{len(urls)} usable sources")
        return False
    db.transition(job, "scripting", "research", "ok", f"{len(r.get('key_facts', []))} facts, {len(urls)} sources")
    return True


def _valid_script(s):
    scenes = s.get("scenes") or []
    if len(scenes) < 3 or any(not (sc.get("narration") or "").strip() for sc in scenes):
        raise ValueError("Script incomplete (needs >=3 scenes with narration)")
    return scenes


def h_script(llm, cfg, job):
    job["assigned_agent"] = "script"
    s = agents.script_agent(llm, cfg, job)
    _valid_script(s)
    job["script"] = s
    pc = cfg.get("panels") or {}
    if pc.get("enabled") and not job.get("panel_history"):  # panel reviews the first draft only (saves quota)
        fmt = job.get("format", "story")
        task = ("Review this " + ("comedy skit" if fmt == "skit" else "mystery/facts story") +
                " script for a 35-58 s Hindi/Hinglish Short. Judge hook, retention, originality, pacing, visuals, "
                + ("humour, timing and sensitivity." if fmt == "skit" else "accuracy risk, suspense and narration."))
        for rnd in range(int(pc.get("max_rounds", 1)) + 1):
            job["assigned_agent"] = "expert_panel"
            pr = roster.panel(llm, "review", fmt, task, {"topic": job["topic"], "script": job["script"]},
                              job_id=job["job_id"], limit=int(pc.get("max_members", 14)))
            job.setdefault("panel_history", []).append({"round": rnd, "score": pr.get("panel_score"),
                                                        "members": pr.get("members"), "top_fixes": pr.get("top_fixes", [])})
            job["panel"] = pr
            score = float(pr.get("panel_score") or 0)
            db.transition(job, "scripting", "expert_panel", f"score {score}",
                          f"{len(pr.get('members', []))} specialists; fixes: " + "; ".join(pr.get("top_fixes", [])[:3]))
            if score >= float(pc.get("pass_score", 7.5)) or rnd >= int(pc.get("max_rounds", 1)):
                break
            job["feedback"].extend(f"PANEL: {f}" for f in pr.get("top_fixes", []))
            job["assigned_agent"] = "script"
            s = agents.script_agent(llm, cfg, job)
            _valid_script(s)
            job["script"] = s
    job["script_status"] = "drafted"
    job["distribution"] = None
    db.transition(job, "fact_check", "script", "drafted",
                  f"{len(job['script']['scenes'])} scenes, ~{job['script'].get('est_duration_sec')}s")
    return True


def h_factcheck(llm, cfg, job):
    job["assigned_agent"] = "fact_check"
    fc = agents.factcheck_agent(llm, cfg, job)
    job["fact_check"] = fc
    for c in fc.get("claims", []):
        u = (c.get("evidence_url") or "").strip()
        if u.startswith("http") and u not in job["source_urls"]:
            job["source_urls"].append(u)
    v = (fc.get("verdict") or "").lower()
    bad = [c for c in fc.get("claims", []) if c.get("status") in ("unsupported", "misleading")]
    if v == "pass" and not bad:
        job["fact_check_status"], job["script_status"] = "pass", "approved"
        db.transition(job, "production", "fact_check", "pass", f"{len(fc.get('claims', []))} claims checked")
        return True
    if v == "reject":
        job["fact_check_status"] = "reject"
        db.transition(job, "rejected", "fact_check", "reject", fc.get("notes", ""))
        return False
    fixes = [f"Scene {c.get('scene')}: '{c.get('claim')}' is {c.get('status')}. Fix: {c.get('fix')}" for c in bad] \
        or [fc.get("notes", "Fact-checker asked for revision")]
    job["feedback"].extend(fixes)
    job["fact_check_status"] = "revise"
    if not _bump_retry(cfg, job, "fact_check", "; ".join(fixes)):
        return False
    db.transition(job, "scripting", "fact_check", "revise", "; ".join(fixes))
    return True


def h_production(llm, cfg, job):
    job["assigned_agent"] = "production"
    final = produce(cfg, job)
    job["production_status"] = "done"
    db.transition(job, "quality_check", "production", "rendered", str(final))
    return True


def h_qc(llm, cfg, job):
    job["assigned_agent"] = "qc"
    if not job.get("distribution"):
        job["distribution"] = agents.distribution_agent(llm, cfg, job)
    make_thumbnail(cfg, job)
    res = run_qc(llm, cfg, job)
    job["qc"] = res
    if res["passed"]:
        job["quality_status"] = "pass"
        write_upload_package(job)
        nxt = "awaiting_approval" if job["approval_required"] else "ready_to_publish"
        db.transition(job, nxt, "qc", "pass", f"{len(res['checks'])} checks passed")
        return nxt == "ready_to_publish"
    job["quality_status"] = "fail"
    owners = {c.get("owner", "qc") for c in res["failed"]}
    reason = "; ".join(f"{c['id']}: {c.get('correction', '')}" for c in res["failed"])
    write_upload_package(job)
    if not _bump_retry(cfg, job, "qc", reason):
        return False
    if "qc" in owners:
        db.transition(job, "needs_human_review", "qc", "fail", reason)
        return False
    if owners & {"script", "research"}:
        job["feedback"].extend(f"QC: {c.get('correction')}" for c in res["failed"] if c.get("owner") in ("script", "research"))
        job["fact_check_status"] = "pending"
        db.transition(job, "scripting", "qc", "fail -> script", reason)
    elif "production" in owners:
        db.transition(job, "production", "qc", "fail -> production", reason)
    else:  # distribution only
        job["distribution"] = None
        db.transition(job, "quality_check", "qc", "fail -> distribution", reason)
    return True


def h_publish(llm, cfg, job):
    if not youtube_ready():
        job["publishing_status"] = "package_ready"
        db.save(job)
        print(f"  [{job['job_id']}] ready to publish - YouTube not connected; upload manually from {JOBS_DIR / job['job_id']}")
        return False
    db.transition(job, "publishing", "distribution", "uploading", "YouTube")
    jd = JOBS_DIR / job["job_id"]
    try:
        vid, privacy = upload_youtube(cfg, job, jd / "final.mp4", jd / "thumbnail.jpg")
    except Exception as e:
        db.log_error(job, "distribution", e)
        db.transition(job, "ready_to_publish", "distribution", "upload failed", str(e)[:300])
        return False
    job["youtube_url"] = f"https://youtube.com/shorts/{vid}"
    job["youtube_id"] = vid
    job["published_at"] = db.now()
    job["publishing_status"] = f"youtube:{privacy}"
    db.transition(job, "published", "distribution", "confirmed", f"{job['youtube_url']} ({privacy})")
    db.transition(job, "analytics_pending", "orchestrator", "ok", "collect metrics daily")
    write_upload_package(job)
    return False


HANDLERS = {"topic_selected": h_research, "researching": h_research, "scripting": h_script,
            "fact_check": h_factcheck, "production": h_production, "quality_check": h_qc,
            "ready_to_publish": h_publish}


def process(llm, cfg, job):
    for _ in range(25):  # hard stop: never an infinite loop
        h = HANDLERS.get(job["status"])
        if not h:
            return job
        try:
            if not h(llm, cfg, job):
                return job
        except Exception as e:
            agent = job.get("assigned_agent", job["status"])
            db.log_error(job, agent, e)
            print(f"  [{job['job_id']}] ERROR in {agent}: {str(e)[:300]}")
            if not _bump_retry(cfg, job, agent, str(e)[:500]):
                return job
    db.transition(job, "needs_human_review", "orchestrator", "step limit", "too many steps in one run")
    return job


# ------------------------------------------------------------------ commands
def start_new_topics(llm, cfg, need, fmt="story"):
    print(f"\nTrend Research [{fmt}]: asking for {cfg['daily']['candidate_topics']} candidates...")
    existing = [j["topic"] for j in db.all_jobs()]
    recent = existing + [t["topic"] for t in db.topics_log()]
    topics = agents.trend_agent(llm, cfg, recent, fmt)
    seen = {x.lower().strip() for x in existing}
    scored = sorted(((t, agents.score_topic(t, cfg["topic_weights"])) for t in topics if t.get("topic")),
                    key=lambda x: -x[1])
    chosen = [(t, s) for t, s in scored if t["topic"].lower().strip() not in seen][:need]
    db.log_topics(scored, {t["topic"] for t, _ in chosen})
    for t, s in scored:
        print(f"   {'*' if any(t is c for c, _ in chosen) else ' '} {s:5.2f}  {t['topic']}")
    jobs = []
    for t, s in chosen:
        job = db.create(db.blank_job(cfg, t, s))
        print(f"  [{job['job_id']}] created: {job['topic']}")
        jobs.append(job)
    return jobs


def daily(cfg):
    rows = readiness(cfg)
    print_readiness(rows)
    if rows[0][1] in ("MISSING", "FAILED"):
        raise SystemExit("Gemini is not ready - fix the line above and run again.")
    llm = LLM(cfg)
    in_flight = [j for j in db.all_jobs() if j["status"] in HANDLERS]
    if in_flight:
        print(f"Resuming {len(in_flight)} in-flight job(s)")
    for j in in_flight:
        process(llm, cfg, j)
    if not (DATA_DIR / "series_bible.json").exists():
        make_plan(cfg, llm)
    age = None
    try:
        from .creators import playbook_age_days
        age = playbook_age_days()
    except Exception:
        pass
    has_creators = any((cfg.get("creators") or {}).get(k) for k in ("story", "skit"))
    if has_creators and (age is None or age >= int(cfg["creators"].get("refresh_days", 7))):
        study_creators(cfg, llm)
    today = datetime.now().date().isoformat()
    for fmt, quota in (cfg["daily"].get("formats") or {"story": 2}).items():
        started = sum(1 for j in db.all_jobs() if j["created"].startswith(today) and j.get("format", "story") == fmt)
        need = int(quota) - started
        if need > 0:
            for j in start_new_topics(llm, cfg, need, fmt):
                process(llm, cfg, j)
        else:
            print(f"Daily {fmt} quota already started today.")
    if youtube_ready():
        collect_analytics(cfg)


def approve(cfg, job_id, note=""):
    job = db.get(job_id)
    if job["status"] != "awaiting_approval":
        raise SystemExit(f"{job_id} is '{job['status']}', not awaiting_approval")
    job["approval"] = {"by": "owner", "ts": db.now(), "note": note}
    db.transition(job, "ready_to_publish", "owner", "approved", note)
    process(None, cfg, job)  # publishing step needs no model


def reject(cfg, job_id, reason):
    job = db.get(job_id)
    db.transition(job, "rejected", "owner", "rejected", reason)


def revise(cfg, job_id, feedback):
    job = db.get(job_id)
    job["feedback"].append(f"OWNER: {feedback}")
    job["retry_count"] = 0
    job["fact_check_status"] = "pending"
    db.transition(job, "scripting", "owner", "revision requested", feedback)
    process(LLM(cfg), cfg, job)


def rerender(cfg, job_id):
    job = db.get(job_id)
    job["retry_count"] = 0
    db.transition(job, "production", "owner", "rerender", "new clips / settings")
    process(LLM(cfg), cfg, job)


def mark_instagram(cfg, job_id, url):
    job = db.get(job_id)
    if not url.startswith("https://www.instagram.com/") and not url.startswith("https://instagram.com/"):
        raise SystemExit("That doesn't look like an Instagram URL")
    job["instagram_url"] = url
    db.save(job)
    db.transition(job, job["status"], "owner", "instagram confirmed", url)


def record_metrics(cfg, job_id, platform, **metrics):
    job = db.get(job_id)
    job["analytics"].setdefault(platform, {})[datetime.now().date().isoformat()] = metrics
    db.save(job)
    print(f"Recorded {platform} metrics for {job_id}: {metrics}")


def collect_analytics(cfg):
    jobs = [j for j in db.all_jobs() if j.get("youtube_id") and j["status"] in ("analytics_pending", "published")]
    if not jobs:
        print("No published YouTube videos to measure yet.")
        return
    stats = youtube_stats([j["youtube_id"] for j in jobs])
    today = datetime.now().date().isoformat()
    for j in jobs:
        st = stats.get(j["youtube_id"])
        if not st:
            continue
        j["analytics"].setdefault("youtube", {})[today] = st
        db.save(j)
        pub = datetime.fromisoformat(j.get("published_at", db.now()))
        if datetime.now() - pub >= timedelta(days=7):
            db.transition(j, "complete", "analytics", "7-day metrics recorded", json.dumps(st))
    print(f"Analytics updated for {len(jobs)} video(s).")


def weekly(cfg):
    rows = []
    for j in db.all_jobs():
        if j.get("analytics"):
            rows.append({"job_id": j["job_id"], "topic": j["topic"], "niche": j["topic_detail"].get("niche"),
                         "hook": (j.get("script") or {}).get("hook"), "published_at": j.get("published_at"),
                         "metrics_by_date": j["analytics"]})
    if not rows:
        print("No analytics yet - publish a few videos first.")
        return
    res = agents.analytics_agent(LLM(cfg), cfg, rows)
    (DATA_DIR / "learnings.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    out = REPORTS_DIR / f"weekly_{datetime.now().date().isoformat()}.json"
    out.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=2))
    print("\nSaved. The Trend agent will read these learnings from now on.")


def make_plan(cfg, llm=None):
    llm = llm or LLM(cfg)
    print("\nStrategy & Storyline department: designing your page's series bible...")
    plan = agents.plan_agent(llm, cfg)
    plan["created"] = db.now()
    (DATA_DIR / "series_bible.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    for x in plan.get("series", []):
        print(f"   [{x.get('format')}] {x.get('name')}: {x.get('premise')}")
    for c in plan.get("recurring_characters", []):
        print(f"   character: {c.get('name')} ({c.get('voice')}) - {c.get('personality')}")
    return plan


def study_creators(cfg, llm=None):
    from .creators import study
    llm = llm or LLM(cfg)
    print("\nCreator Intelligence department: studying top creators...")
    pb = study(llm, cfg)
    for k in ("hook_patterns", "adapt_for_us"):
        for x in (pb.get(k) or [])[:5]:
            print(f"   {k}: {x}")
    print(f"   evidence strength: {pb.get('evidence_strength')}")
    return pb


def list_roster():
    cur = None
    for a in roster.roster():
        if a["dept"] != cur:
            cur = a["dept"]
            print(f"\n== {cur} ==")
        print(f"  {a['id']:<5} {a['name']:<36} stages={','.join(a['stages'])}  formats={','.join(a['formats'])}")
    print(f"\nTotal: {len(roster.roster())} specialists")
