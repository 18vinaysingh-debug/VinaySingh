"""The 100-specialist roster and the expert-panel mechanism.

Specialists are expert briefs run on Gemini. For each job and stage the Orchestrator
selects only the relevant ones and runs them together in ONE panel call.
"""
import json

import yaml

from .config import ROOT

_ROSTER = None


def roster():
    global _ROSTER
    if _ROSTER is None:
        data = yaml.safe_load((ROOT / "roster.yaml").read_text(encoding="utf-8"))
        _ROSTER = []
        for d in data["departments"]:
            for a in d["agents"]:
                _ROSTER.append({**a, "dept": d["name"]})
    return _ROSTER


def select(stage, fmt=None, limit=12):
    out = []
    for a in roster():
        if stage not in a["stages"]:
            continue
        f = a.get("formats", ["both"])
        if fmt and "both" not in f and fmt not in f:
            continue
        out.append(a)
    return out[:limit]


def brief_block(agents_):
    return "\n".join(f"- {a['id']} {a['name']}: {a['brief']}" for a in agents_)


def panel(llm, stage, fmt, task_text, artifact, job_id=None, limit=14, tier="fast"):
    """One Gemini call in which each selected specialist reviews the artifact."""
    members = select(stage, fmt, limit)
    if not members:
        return {"members": [], "reviews": [], "top_fixes": [], "panel_score": 10}
    prompt = f"""You are an expert review PANEL. Each member below reviews strictly from their own specialty.
PANEL MEMBERS:
{brief_block(members)}

TASK: {task_text}
ARTIFACT:
{json.dumps(artifact, ensure_ascii=False)[:9000]}

Each member: score 1-10 and at most 2 concrete, specific fixes (quote the line to change and give the new wording).
Members with nothing important to fix give score >= 8 and no fixes. Do not invent facts.
Then act as the panel chair: merge into the 6 highest-impact fixes and give an overall panel_score.

Return ONLY JSON:
{{"reviews":[{{"id":"","name":"","score":0,"fixes":[""]}}],"top_fixes":[""],"panel_score":0}}"""
    data, _ = llm.json(f"panel_{stage}", prompt, tier=tier, job_id=job_id)
    data["members"] = [a["id"] for a in members]
    return data
