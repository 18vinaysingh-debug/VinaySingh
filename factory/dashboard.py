"""Daily reporting dashboard -> reports/dashboard.html (open in any browser)."""
import html
from collections import Counter
from datetime import datetime

from . import db
from .config import REPORTS_DIR

PILL = {"awaiting_approval": "#b45309", "ready_to_publish": "#1d4ed8", "published": "#047857",
        "analytics_pending": "#047857", "complete": "#065f46", "rejected": "#6b7280", "failed": "#b91c1c",
        "needs_human_review": "#b91c1c", "blocked": "#b91c1c"}


def e(x):
    return html.escape(str(x if x is not None else ""))


def build(readiness_rows=None):
    jobs = db.all_jobs()
    st = Counter(j["status"] for j in jobs)
    topics = db.topics_log()
    ev = db.events(limit=400)
    usage = db.usage_summary()
    revised = sum(1 for x in ev if x["result"] == "revise")
    qc_fail = sum(1 for x in ev if x["agent"] == "qc" and str(x["result"]).startswith("fail"))
    qc_pass = sum(1 for x in ev if x["agent"] == "qc" and x["result"] == "pass")
    rendered = sum(1 for j in jobs if j.get("production_status") == "done")
    retries = sum(j.get("retry_count", 0) for j in jobs)

    tiles = [("Topics scored", len(topics)), ("Selected", sum(t["selected"] for t in topics)),
             ("Scripts revised", revised), ("Videos rendered", rendered), ("QC pass / fail", f"{qc_pass} / {qc_fail}"),
             ("Awaiting approval", st.get("awaiting_approval", 0)),
             ("Published", sum(1 for j in jobs if j.get("youtube_url") or j.get("instagram_url"))),
             ("Need review", st.get("needs_human_review", 0) + st.get("failed", 0)), ("Retries", retries)]
    tiles_html = "".join(f'<div class="tile"><b>{e(v)}</b><span>{e(k)}</span></div>' for k, v in tiles)

    review = ""
    for j in [j for j in jobs if j["status"] in ("awaiting_approval", "needs_human_review")]:
        d = j.get("distribution") or {}
        fails = "".join(f"<li>{e(c['id'])}: {e(c.get('correction'))}</li>" for c in (j.get("qc") or {}).get("failed", []))
        errs = "".join(f"<li>{e(x['agent'])}: {e(x['error'][:200])}</li>" for x in j.get("error_log", [])[-3:])
        review += f"""<div class="card"><video src="../jobs/{e(j['job_id'])}/final.mp4" controls preload="metadata"></video>
<div><h3>{e(j['job_id'])} <span class="pill" style="background:{PILL.get(j['status'], '#374151')}">{e(j['status'])}</span></h3>
<p class="t">[{e(j.get('format', 'story'))}] {e(j['topic'])}</p>
<p><b>Series:</b> {e(j['topic_detail'].get('series'))} &nbsp; <b>Expert panel:</b> {e((j.get('panel') or {}).get('panel_score'))}/10 from {len((j.get('panel') or {}).get('members', []))} specialists</p><p><b>YT title:</b> {e((d.get('youtube') or {}).get('title'))}</p>
<p><b>Sources:</b> {len(j.get('source_urls', []))} &nbsp; <b>Fact-check:</b> {e(j.get('fact_check_status'))} &nbsp; <b>QC:</b> {e(j.get('quality_status'))}</p>
{f'<ul class="bad">{fails}</ul>' if fails else ''}{f'<ul class="bad">{errs}</ul>' if errs else ''}
<code>python run.py approve {e(j['job_id'])}</code> &nbsp; <code>python run.py revise {e(j['job_id'])} "your note"</code> &nbsp;
<code>python run.py reject {e(j['job_id'])} "reason"</code>
<p class="m">Package: jobs/{e(j['job_id'])}/UPLOAD_PACKAGE.txt</p></div></div>"""
    review = review or '<p class="m">Nothing waiting for you.</p>'

    rows = ""
    for j in reversed(jobs):
        yt = j.get("analytics", {}).get("youtube", {})
        last = yt[sorted(yt)[-1]] if yt else {}
        links = " ".join(f'<a href="{e(u)}" target="_blank">{n}</a>' for n, u in
                         (("YT", j.get("youtube_url")), ("IG", j.get("instagram_url"))) if u)
        rows += (f"<tr><td>{e(j['job_id'])}</td><td>{e(j.get('format', 'story'))}</td><td>{e(j['topic'])}</td><td>{e(j['topic_score'])}</td>"
                 f"<td><span class='pill' style='background:{PILL.get(j['status'], '#374151')}'>{e(j['status'])}</span></td>"
                 f"<td>{e(j.get('retry_count'))}</td><td>{e(last.get('viewCount', ''))}</td><td>{e(last.get('likeCount', ''))}</td>"
                 f"<td>{e(last.get('commentCount', ''))}</td><td>{links}</td><td>{e(j['updated'])}</td></tr>")

    trows = "".join(f"<tr><td>{'✔' if t['selected'] else ''}</td><td>{e(t['score'])}</td><td>{e(t['topic'])}</td>"
                    f"<td>{e(t['ts'][:10])}</td></tr>" for t in topics[:40])
    urows = "".join(f"<tr><td>{e(u['d'])}</td><td>{e(u['model'])}</td><td>{e(u['calls'])}</td><td>{e(u['tokens'])}</td>"
                    f"<td>{e(u['failures'])}</td></tr>" for u in usage[:30])
    erows = "".join(f"<tr><td>{e(x['ts'])}</td><td>{e(x['job_id'])}</td><td>{e(x['agent'])}</td>"
                    f"<td>{e(x['from_status'])} → {e(x['to_status'])}</td><td>{e(x['result'])}</td><td>{e((x['reason'] or '')[:160])}</td></tr>"
                    for x in ev[:80])
    rd = "".join(f"<tr><td>{e(c)}</td><td><b>{e(s)}</b></td><td>{e(n)}</td></tr>" for c, s, n in (readiness_rows or []))

    page = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Content Factory Dashboard</title><style>
:root{{--bg:#f6f7fb;--card:#fff;--ink:#111827;--mute:#6b7280;--line:#e5e7eb;--acc:#2E3B8B}}
body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,Segoe UI,Arial}}
header{{background:linear-gradient(120deg,#2E3B8B,#415FFF);color:#fff;padding:18px 22px}}
header h1{{margin:0;font-size:20px}} header p{{margin:2px 0 0;opacity:.85}}
main{{padding:16px 22px;max-width:1300px;margin:auto}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:16px}}
.tile{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px}}
.tile b{{display:block;font-size:22px;color:var(--acc)}} .tile span{{color:var(--mute);font-size:12px}}
h2{{font-size:15px;margin:22px 0 8px}} .card{{display:flex;gap:16px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px;margin-bottom:10px;flex-wrap:wrap}}
video{{width:200px;aspect-ratio:9/16;background:#000;border-radius:8px}} .card>div{{flex:1;min-width:260px}}
.card h3{{margin:0 0 4px;font-size:15px}} .t{{font-weight:600;margin:0 0 6px}} .m{{color:var(--mute);font-size:12px}}
.pill{{color:#fff;border-radius:99px;padding:1px 8px;font-size:11px;white-space:nowrap}}
code{{background:#eef2ff;padding:2px 6px;border-radius:5px;font-size:12px;display:inline-block;margin:2px 0}}
.bad{{color:#b91c1c;margin:4px 0;padding-left:18px}}
.tw{{overflow-x:auto;background:var(--card);border:1px solid var(--line);border-radius:10px}}
table{{border-collapse:collapse;width:100%;font-size:12.5px}} th,td{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{background:#f9fafb;color:var(--mute);font-weight:600}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} @media(max-width:800px){{.two{{grid-template-columns:1fr}}}}
</style></head><body><header><h1>AI Content Factory — Daily Dashboard</h1>
<p>Updated {datetime.now().strftime('%d %b %Y, %H:%M')} · {len(jobs)} jobs</p></header><main>
<div class="tiles">{tiles_html}</div>
<h2>Needs you</h2>{review}
<h2>All jobs</h2><div class="tw"><table><tr><th>Job</th><th>Format</th><th>Topic</th><th>Score</th><th>Status</th><th>Retries</th><th>Views</th><th>Likes</th><th>Comments</th><th>Links</th><th>Updated</th></tr>{rows}</table></div>
<div class="two"><div><h2>Topic decisions</h2><div class="tw"><table><tr><th>Pick</th><th>Score</th><th>Topic</th><th>Date</th></tr>{trows}</table></div></div>
<div><h2>Gemini usage</h2><div class="tw"><table><tr><th>Date</th><th>Model</th><th>Calls</th><th>Tokens</th><th>Failed</th></tr>{urows}</table></div>
{'<h2>Components</h2><div class="tw"><table>' + rd + '</table></div>' if rd else ''}</div></div>
<h2>Audit trail (latest)</h2><div class="tw"><table><tr><th>Time</th><th>Job</th><th>Agent</th><th>Status</th><th>Result</th><th>Reason</th></tr>{erows}</table></div>
<p class="m">Topic scores are prioritisation signals, not predictions. Metrics are as reported by the platform on the date shown.</p>
</main></body></html>"""
    out = REPORTS_DIR / "dashboard.html"
    out.write_text(page, encoding="utf-8")
    return out
