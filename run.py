"""AI Content Factory - command line.

  python run.py check                      component status (ready / missing / untested)
  python run.py agents                     list the 100 specialists by department
  python run.py plan                       (re)design the page's series bible + recurring characters
  python run.py creators                   learn patterns from the top creators listed in config.yaml
  python run.py daily                      run the daily pipeline (resume jobs + start today's topics)
  python run.py status                     list jobs
  python run.py show JOB                   full job record + audit trail
  python run.py approve JOB ["note"]       approve a video (uploads to YouTube if connected)
  python run.py revise JOB "feedback"      send back to the script writer with your notes
  python run.py reject JOB "reason"
  python run.py rerender JOB               re-edit after dropping your own clips in jobs/JOB/clips/
  python run.py youtube-auth               one-time YouTube login
  python run.py mark-ig JOB URL            record the Instagram Reel URL after you post it
  python run.py metrics JOB instagram views=1200 likes=80 shares=12 saves=9 follows=3
  python run.py analytics                  pull YouTube stats now
  python run.py weekly                     weekly strategy review -> learnings for topic selection
  python run.py dashboard                  rebuild reports/dashboard.html
"""
import json
import sys

from factory import db, orchestrator as orc
from factory.config import load_config
from factory.dashboard import build


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cfg = load_config()
    cmd, args = argv[0], argv[1:]
    rows = None
    if cmd == "check":
        rows = orc.readiness(cfg)
        orc.print_readiness(rows)
    elif cmd == "agents":
        orc.list_roster()
        return
    elif cmd == "plan":
        orc.make_plan(cfg)
    elif cmd == "creators":
        orc.study_creators(cfg)
    elif cmd == "daily":
        orc.daily(cfg)
        rows = orc.readiness(cfg, ping=False)
    elif cmd == "status":
        for j in db.all_jobs():
            print(f"{j['job_id']:<18} {j.get('format', 'story'):<6} {j['status']:<20} retries={j['retry_count']}  {j['topic'][:70]}")
    elif cmd == "show":
        j = db.get(args[0])
        print(json.dumps(j, ensure_ascii=False, indent=2))
        for x in db.events(args[0]):
            print(x["ts"], x["agent"], f"{x['from_status']} -> {x['to_status']}", x["result"], x["reason"][:150])
        return
    elif cmd == "approve":
        orc.approve(cfg, args[0], " ".join(args[1:]))
    elif cmd == "revise":
        orc.revise(cfg, args[0], " ".join(args[1:]) or "Improve it")
    elif cmd == "reject":
        orc.reject(cfg, args[0], " ".join(args[1:]) or "owner rejected")
    elif cmd == "rerender":
        orc.rerender(cfg, args[0])
    elif cmd == "youtube-auth":
        from factory.publish import youtube_auth
        youtube_auth()
    elif cmd == "mark-ig":
        orc.mark_instagram(cfg, args[0], args[1])
    elif cmd == "metrics":
        kv = dict(a.split("=", 1) for a in args[2:])
        orc.record_metrics(cfg, args[0], args[1], **{k: int(v) for k, v in kv.items()})
    elif cmd == "analytics":
        orc.collect_analytics(cfg)
    elif cmd == "weekly":
        orc.weekly(cfg)
    elif cmd != "dashboard":
        print(f"Unknown command {cmd}\n{__doc__}")
        return
    out = build(rows)
    print(f"\nDashboard: {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
