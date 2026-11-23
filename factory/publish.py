"""YouTube publishing + stats through the official YouTube Data API (OAuth, least privilege).

One-time setup (see README): put your OAuth client file at secrets/client_secret.json,
then run  python run.py youtube-auth  . The token is stored in secrets/youtube_token.json.
Instagram: the Graph API needs a Business account + publicly hosted video URL, so v1 uses
the UPLOAD_PACKAGE for manual posting and you record the URL with  python run.py mark-ig.
"""
from .config import SECRETS_DIR

SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]
CLIENT = SECRETS_DIR / "client_secret.json"
TOKEN = SECRETS_DIR / "youtube_token.json"


def youtube_ready():
    return CLIENT.exists() and TOKEN.exists()


def _service():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
    if not creds or not creds.valid:
        raise RuntimeError("YouTube not authorised. Run:  python run.py youtube-auth")
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def youtube_auth():
    from google_auth_oauthlib.flow import InstalledAppFlow
    if not CLIENT.exists():
        raise SystemExit(f"Put your Google OAuth desktop client file at {CLIENT} first (see README).")
    creds = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES).run_local_server(port=0)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    print("YouTube authorised. Token saved to", TOKEN)


def upload_youtube(cfg, job, video_path, thumb_path=None):
    from googleapiclient.http import MediaFileUpload
    yt = _service()
    d = job["distribution"]["youtube"]
    body = {
        "snippet": {"title": d["title"][:100], "description": d["description"][:4900],
                    "tags": d.get("tags", [])[:15], "categoryId": cfg["publishing"]["youtube_category_id"],
                    "defaultLanguage": "hi", "defaultAudioLanguage": "hi"},
        "status": {"privacyStatus": cfg["publishing"]["youtube_privacy"], "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": bool(job["distribution"].get("synthetic_disclosure"))},
    }
    req = yt.videos().insert(part="snippet,status", body=body,
                             media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp.get("id")
    if not vid:
        raise RuntimeError(f"Upload returned no video id: {resp}")
    if thumb_path:
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(thumb_path))).execute()
        except Exception as e:  # custom thumbnails need a verified channel; not fatal
            print(f"    ! thumbnail not set: {str(e)[:120]}")
    return vid, resp.get("status", {}).get("privacyStatus")


def youtube_stats(video_ids):
    yt = _service()
    out = {}
    for i in range(0, len(video_ids), 50):
        r = yt.videos().list(part="statistics,status", id=",".join(video_ids[i:i + 50])).execute()
        for it in r.get("items", []):
            st = it.get("statistics", {})
            out[it["id"]] = {k: int(st.get(k, 0)) for k in ("viewCount", "likeCount", "commentCount")}
            out[it["id"]]["privacy"] = it.get("status", {}).get("privacyStatus")
    return out
