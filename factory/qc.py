"""Quality Control Agent: automated technical checks + LLM editorial checks.
Each failed check names the responsible agent so the Orchestrator can route the fix."""

from .agents import editorial_qc_agent
from .config import JOBS_DIR
from .production import mean_volume, probe


def technical_checks(cfg, job):
    jd = JOBS_DIR / job["job_id"]
    final = jd / "final.mp4"
    lo, hi = cfg["daily"]["short_duration_sec"]
    W, H = cfg["video"]["width"], cfg["video"]["height"]
    checks = []

    def add(cid, ok, owner, correction):
        checks.append({"id": cid, "pass": bool(ok), "owner": owner, "correction": "" if ok else correction})

    if not final.exists():
        add("export_exists", False, "production", "final.mp4 missing")
        return checks
    info = probe(final)
    add("aspect_resolution", (info["width"], info["height"]) == (W, H), "production",
        f"Expected {W}x{H}, got {info['width']}x{info['height']}")
    add("duration", lo - 8 <= info["duration"] <= 59.5, "script",
        f"Video is {info['duration']:.1f}s; target {lo}-{hi}s and under 60s for Reels/Shorts. "
        + ("Cut a scene / tighten lines." if info["duration"] > 59.5 else "Add one more substantive scene."))
    add("audio_present", info["has_audio"], "production", "No audio stream")
    mv = mean_volume(final)
    add("audio_level", mv is not None and -30 <= mv <= -8, "production", f"Mean volume {mv} dB outside -30..-8 dB")
    srt = jd / "captions.srt"
    add("captions_present", srt.exists() and srt.stat().st_size > 20, "production", "Captions file empty")
    add("captions_burned", (job.get("production") or {}).get("captions_burned", False), "production",
        "Captions not burned in - install full ffmpeg (winget install Gyan.FFmpeg) and rerender")
    n_scenes = len(job["script"]["scenes"])
    vis = [r for r in job.get("rights", []) if r["asset"].startswith("visual")]
    add("every_scene_has_visual", len(vis) == n_scenes, "production", "Some scenes lack a visual")
    add("rights_recorded", all(r.get("license") for r in job.get("rights", [])), "production",
        "An asset has no recorded licence/permission")
    add("fact_check_passed", job.get("fact_check_status") == "pass", "script", "Fact-check not passed")
    if job.get("format", "story") == "story":
        add("sources_recorded", len(job.get("source_urls", [])) >= 2, "research", "Fewer than 2 sources recorded")
    return checks


def run_qc(llm, cfg, job):
    tech = technical_checks(cfg, job)
    try:
        ed = editorial_qc_agent(llm, cfg, job).get("checks", [])
    except Exception as e:
        ed = [{"id": "editorial_review", "pass": False, "owner": "qc", "correction": f"Editorial QC could not run: {e}"}]
    checks = tech + ed
    failed = [c for c in checks if not c.get("pass")]
    return {"passed": not failed, "checks": checks, "failed": failed}
