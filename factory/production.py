"""Production Agent: narration (TTS), visuals (your clips > Pexels > generated cards),
captions, edit and export a 1080x1920 video. Every asset's rights are recorded."""
import asyncio
import json
import re
import shutil
import subprocess
import textwrap
import wave
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .config import JOBS_DIR, secret


class ProductionError(Exception):
    pass


# ------------------------------------------------------------------ ffmpeg helpers
def ffmpeg_bin():
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        raise ProductionError("ffmpeg not found. On Windows run:  winget install Gyan.FFmpeg  then reopen the terminal.")


def run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise ProductionError(f"ffmpeg failed: {' '.join(map(str, cmd[:6]))}...\n{r.stderr[-1500:]}")
    return r


def probe(path):
    """Return dict(duration, width, height, has_audio) using ffmpeg -i output (no ffprobe needed)."""
    r = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    err = r.stderr
    info = {"duration": 0.0, "width": 0, "height": 0, "has_audio": "Audio:" in err}
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err)
    if m:
        info["duration"] = int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
    if m:
        info["width"], info["height"] = int(m[1]), int(m[2])
    return info


def mean_volume(path):
    r = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    m = re.search(r"mean_volume: (-?[\d.]+) dB", r.stderr)
    return float(m[1]) if m else None


def find_font(bold=True):
    cands = (["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/segoeuib.ttf"] if bold else ["C:/Windows/Fonts/arial.ttf"]) + [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/Library/Fonts/Arial Bold.ttf"]
    for c in cands:
        if Path(c).exists():
            return c
    return None


# ------------------------------------------------------------------ narration
def tts(cfg, text, out_path, voice="narrator"):
    prov = cfg["tts"]["provider"]
    out_path = Path(out_path)
    if prov == "mock":
        dur = max(2.0, len(text.split()) * 0.6)
        freq = {"male": 220, "female": 440}.get(voice, 330)
        run([ffmpeg_bin(), "-y", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration={dur:.2f}",
             "-af", "volume=0.35", str(out_path)])
        return {"source": "mock tone", "license": "test only"}
    if prov == "edge":
        import edge_tts

        vname = cfg["tts"].get(f"edge_voice_{voice}") or cfg["tts"]["edge_voice"]

        async def _go():
            await edge_tts.Communicate(text, vname, rate=cfg["tts"].get("edge_rate", "+0%")).save(str(out_path))
        asyncio.run(_go())
        return {"source": f"Microsoft Edge neural TTS ({vname})", "license": "Synthetic voice; check Microsoft terms before monetised scale-up"}
    if prov == "gemini":
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=secret("GEMINI_API_KEY"))
        resp = client.models.generate_content(
            model=cfg["tts"]["gemini_model"],
            contents=f"Say this in Hindi like an engaging, confident storyteller: {text}",
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=cfg["tts"].get(f"gemini_voice_{voice}") or cfg["tts"]["gemini_voice"])))))
        pcm = resp.candidates[0].content.parts[0].inline_data.data
        wav = out_path.with_suffix(".wav")
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000); w.writeframes(pcm)
        run([ffmpeg_bin(), "-y", "-i", str(wav), str(out_path)])
        return {"source": f"Gemini TTS ({voice})", "license": "Synthetic voice, Google API terms"}
    raise ProductionError(f"Unknown tts provider {prov}")


# ------------------------------------------------------------------ visuals
def make_card(text, path, w, h, seed=0):
    palettes = [((14, 20, 60), (88, 40, 160)), ((5, 40, 60), (20, 140, 160)), ((40, 10, 40), (170, 40, 90)),
                ((10, 25, 45), (46, 59, 139))]
    top, bot = palettes[seed % len(palettes)]
    img = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(top[i] * (1 - t) + bot[i] * t) for i in range(3)))
    glow = Image.new("L", (w, h), 0)
    ImageDraw.Draw(glow).ellipse([w * 0.1, h * 0.25, w * 0.9, h * 0.65], fill=90)
    img = Image.composite(Image.new("RGB", (w, h), (255, 255, 255)), img, glow.filter(ImageFilter.GaussianBlur(160)))
    fp = find_font(True)
    font = ImageFont.truetype(fp, 120) if fp else ImageFont.load_default()
    lines = textwrap.wrap((text or "").upper(), 12)[:4]
    d = ImageDraw.Draw(img)
    y = h * 0.42 - len(lines) * 70
    for ln in lines:
        tw = d.textlength(ln, font=font)
        d.text(((w - tw) / 2, y), ln, font=font, fill="white", stroke_width=6, stroke_fill=(0, 0, 0))
        y += 140
    img.save(path, quality=92)


def pexels_video(query, used, out_path):
    key = secret("PEXELS_API_KEY")
    if not key:
        return None
    try:
        r = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": key}, timeout=30,
                         params={"query": query, "orientation": "portrait", "per_page": 10})
        r.raise_for_status()
        for v in r.json().get("videos", []):
            if v["id"] in used:
                continue
            files = [f for f in v.get("video_files", []) if f.get("height") and f.get("width")
                     and f["height"] >= f["width"] and f["height"] >= 1280 and f.get("file_type") == "video/mp4"]
            if not files:
                continue
            f = sorted(files, key=lambda f: abs(f["height"] - 1920))[0]
            with requests.get(f["link"], stream=True, timeout=120) as dl:
                dl.raise_for_status()
                with open(out_path, "wb") as fh:
                    for chunk in dl.iter_content(1 << 16):
                        fh.write(chunk)
            used.add(v["id"])
            return {"source": "Pexels", "url": v.get("url"), "author": (v.get("user") or {}).get("name", ""),
                    "license": "Pexels License - free to use, no attribution required (pexels.com/license)"}
    except Exception as e:
        print(f"    ! Pexels search '{query}' failed: {str(e)[:120]}")
    return None


def owner_clip(job_dir, n):
    for ext in (".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg"):
        p = job_dir / "clips" / f"scene_{n}{ext}"
        if p.exists():
            return p
    return None


# ------------------------------------------------------------------ captions
def _ass_time(t):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _ass_escape(s):
    return s.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def caption_chunks(text, start, dur, words_per_chunk=4):
    words = text.split()
    chunks = [" ".join(words[i:i + words_per_chunk]) for i in range(0, len(words), words_per_chunk)] or [""]
    total = sum(len(c) + 2 for c in chunks)
    out, t = [], start
    for c in chunks:
        d = dur * (len(c) + 2) / total
        out.append((t, t + d, c))
        t += d
    return out


def write_captions(cfg, timeline, ass_path, srt_path):
    v = cfg["video"]
    W, H = v["width"], v["height"]
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{v['caption_font']},{v['caption_size']},&H00FFFFFF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,6,2,2,70,70,520,1
Style: Big,{v['caption_font']},{int(v['caption_size'] * 1.45)},&H0000E5FF,&H0000FFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,8,3,8,60,60,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines, srt, k = [], [], 1
    for sc in timeline:
        if sc.get("on_screen_text") and not sc.get("card"):
            lines.append(f"Dialogue: 1,{_ass_time(sc['start'])},{_ass_time(sc['start'] + min(2.6, sc['dur']))},Big,,0,0,0,,"
                         f"{{\\fad(150,200)}}{_ass_escape(sc['on_screen_text'].upper())}")
        for s, e, c in caption_chunks(sc["caption"], sc["start"], sc["audio_dur"]):
            lines.append(f"Dialogue: 0,{_ass_time(s)},{_ass_time(e)},Cap,,0,0,0,,{_ass_escape(c)}")
            srt.append(f"{k}\n{_srt_time(s)} --> {_srt_time(e)}\n{c}\n")
            k += 1
    Path(ass_path).write_text(head + "\n".join(lines) + "\n", encoding="utf-8")
    Path(srt_path).write_text("\n".join(srt), encoding="utf-8")


def _srt_time(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# ------------------------------------------------------------------ main
def produce(cfg, job):
    v = cfg["video"]
    W, H, FPS = v["width"], v["height"], v["fps"]
    jd = JOBS_DIR / job["job_id"]
    for sub in ("audio", "visuals", "scenes", "clips"):
        (jd / sub).mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_bin()
    scenes = job["script"]["scenes"]
    rights, used, timeline, t0 = [], set(), [], 0.0

    (jd / "veo_prompts.txt").write_text(
        "Optional: generate these with Veo/Flow in your Gemini app, save as clips/scene_N.mp4, "
        f"then run:  python run.py rerender {job['job_id']}\n\n" +
        "\n".join(f"scene_{s['n']}: {s.get('veo_prompt', '')}" for s in scenes), encoding="utf-8")
    if job.get("format") == "skit":
        chars = job["script"].get("characters", [])
        (jd / "SHOOT_PLAN.txt").write_text(
            f"SKIT: {job['script'].get('working_title', job['topic'])}\n"
            "Want it with real acting? Film each line on your phone (vertical), save as clips/scene_N.mp4,\n"
            f"then run:  python run.py rerender {job['job_id']}   (your clip AND your own voice replace that scene;\n"
            "scenes you don't film keep the AI voice + stock visual).\n\nCHARACTERS:\n" +
            "\n".join(f"  {c.get('name')} ({c.get('voice')}): {c.get('personality')}" for c in chars) + "\n\nSHOTS:\n" +
            "\n".join(f"  {s['n']}. [{s.get('speaker', '')}] {s.get('caption', '')}\n     SHOT: {s.get('shot', '')}" for s in scenes),
            encoding="utf-8")

    for s in scenes:
        n = s["n"]
        # narration
        a_path = jd / "audio" / f"scene_{n}.mp3"
        voice = (s.get("voice") or "narrator").lower()
        if voice not in ("male", "female"):
            voice = "narrator"
        oc = owner_clip(jd, n)
        if (oc and oc.suffix.lower() in (".mp4", ".mov", ".webm") and v.get("owner_clip_audio", True)
                and probe(oc)["has_audio"]):
            run([ff, "-y", "-i", str(oc), "-vn", "-ac", "2", "-ar", "44100", str(a_path)])  # your own acted line
            r = {"source": "Owner-recorded audio (own clip)", "license": "Owned"}
        else:
            r = tts(cfg, s["narration"], a_path, voice)
        rights.append({"asset": f"voice scene_{n}", "type": "voice", **r})
        a_dur = probe(a_path)["duration"]
        if a_dur < 0.5:
            raise ProductionError(f"Narration for scene {n} is empty")
        dur = a_dur + 0.25

        # visual: owner clip > Pexels > generated card
        vis, is_img = owner_clip(jd, n), False
        if vis:
            is_img = vis.suffix.lower() in (".png", ".jpg", ".jpeg")
            rights.append({"asset": f"visual scene_{n}", "type": "image" if is_img else "video",
                           "source": "Owner-provided clip (e.g. Veo/Flow)", "license": "Owner confirms rights; disclose if realistic AI"})
        else:
            pv = jd / "visuals" / f"scene_{n}.mp4"
            info = pexels_video(s.get("visual_query") or job["topic"], used, pv) if cfg["visuals"].get("use_pexels") else None
            if info:
                vis = pv
                rights.append({"asset": f"visual scene_{n}", "type": "video", **info})
            else:
                vis, is_img = jd / "visuals" / f"scene_{n}.jpg", True
                make_card(s.get("on_screen_text") or s.get("caption", "")[:40], vis, W, H, seed=n)
                rights.append({"asset": f"visual scene_{n}", "type": "image", "source": "Self-generated title card",
                               "license": "Owned"})

        out = jd / "scenes" / f"scene_{n}.mp4"
        if is_img:
            W2, H2 = int(W * 1.12) // 2 * 2, int(H * 1.12) // 2 * 2
            vf = (f"scale={W2}:{H2}:force_original_aspect_ratio=increase,crop={W}:{H}:"
                  f"x='(in_w-{W})*t/{dur:.2f}':y='(in_h-{H})/2',fps={FPS},setsar=1,format=yuv420p")
            inputs = ["-loop", "1", "-framerate", str(FPS), "-i", str(vis)]
        else:
            vf = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,format=yuv420p"
            inputs = ["-stream_loop", "-1", "-i", str(vis)]
        run([ff, "-y", *inputs, "-i", str(a_path), "-t", f"{dur:.2f}", "-vf", vf, "-af", "apad,aresample=44100",
             "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
             "-c:a", "aac", "-b:a", "160k", "-ac", "2", "-r", str(FPS), str(out)])
        real = probe(out)["duration"] or dur
        cap = s.get("caption", "")
        if job.get("format") == "skit" and s.get("speaker") and s["speaker"].lower() != "narrator":
            cap = f"{s['speaker']}: {cap}"
        timeline.append({"n": n, "start": t0, "dur": real, "audio_dur": a_dur, "caption": cap,
                         "on_screen_text": s.get("on_screen_text", ""),
                         "card": "title card" in rights[-1]["source"].lower()})
        t0 += real

    # join
    (jd / "scenes" / "list.txt").write_text("".join(f"file 'scene_{s['n']}.mp4'\n" for s in scenes), encoding="utf-8")
    run([ff, "-y", "-f", "concat", "-safe", "0", "-i", "list.txt", "-c", "copy", "../body.mp4"], cwd=jd / "scenes")

    # captions + music + loudness -> final
    write_captions(cfg, timeline, jd / "captions.ass", jd / "captions.srt")
    cmd = [ff, "-y", "-i", "body.mp4"]
    music = (v.get("music_file") or "").strip()
    if music and Path(music).exists():
        cmd += ["-stream_loop", "-1", "-i", str(Path(music).resolve())]
        fc = (f"[0:v]ass=captions.ass[v];[1:a]volume={v.get('music_volume', 0.1)}[m];"
              f"[0:a][m]amix=inputs=2:duration=first:dropout_transition=0,loudnorm=I=-14:TP=-1.5:LRA=11[a]")
        rights.append({"asset": "music", "type": "music", "source": music, "license": "Owner confirms rights"})
    else:
        fc = "[0:v]ass=captions.ass[v];[0:a]loudnorm=I=-14:TP=-1.5:LRA=11[a]"
    cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "final.mp4"]
    try:
        run(cmd, cwd=jd)
        burned = True
    except ProductionError as e:
        if "ass" not in str(e).lower():
            raise
        print("    ! caption burn-in failed (ffmpeg without libass) - exporting without burned captions")
        run([ff, "-y", "-i", "body.mp4", "-c", "copy", "final.mp4"], cwd=jd)
        burned = False

    job["rights"] = rights
    job["asset_urls"] = [str(jd / "final.mp4"), str(jd / "captions.srt"), str(jd / "veo_prompts.txt")]
    job["production"] = {"timeline": timeline, "captions_burned": burned, "duration": round(t0, 2)}
    return jd / "final.mp4"


def make_thumbnail(cfg, job):
    jd = JOBS_DIR / job["job_id"]
    final = jd / "final.mp4"
    dur = probe(final)["duration"]
    frame = jd / "thumb_frame.jpg"
    run([ffmpeg_bin(), "-y", "-ss", f"{dur * 0.3:.2f}", "-i", str(final), "-frames:v", "1", str(frame)])
    img = Image.open(frame).convert("RGB")
    W, H = img.size
    shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shade).rectangle([0, int(H * 0.30), W, int(H * 0.62)], fill=(0, 0, 0, 150))
    img = Image.alpha_composite(img.convert("RGBA"), shade).convert("RGB")
    d = ImageDraw.Draw(img)
    fp = find_font(True)
    font = ImageFont.truetype(fp, 130) if fp else ImageFont.load_default()
    text = (job.get("distribution") or {}).get("thumbnail_text", job["topic"]).upper()
    lines = textwrap.wrap(text, 11)[:3]
    y = H * 0.46 - len(lines) * 75
    for ln in lines:
        tw = d.textlength(ln, font=font)
        d.text(((W - tw) / 2, y), ln, font=font, fill=(255, 229, 0), stroke_width=8, stroke_fill="black")
        y += 150
    out = jd / "thumbnail.jpg"
    img.save(out, quality=90)
    frame.unlink(missing_ok=True)
    return out


def write_upload_package(job):
    """Human-readable package for manual upload (Instagram) and review."""
    jd = JOBS_DIR / job["job_id"]
    d = job.get("distribution") or {}
    yt, ig = d.get("youtube", {}), d.get("instagram", {})
    txt = f"""JOB {job['job_id']}  |  {job['topic']}
VIDEO: final.mp4    THUMBNAIL: thumbnail.jpg    CAPTIONS FILE: captions.srt

=== YOUTUBE SHORTS ===
TITLE: {yt.get('title', '')}

DESCRIPTION:
{yt.get('description', '')}

TAGS: {', '.join(yt.get('tags', []))}
PINNED COMMENT: {d.get('pinned_comment', '')}
ALTERED/SYNTHETIC CONTENT DISCLOSURE: {'YES - ' if d.get('synthetic_disclosure') else 'No - '}{d.get('disclosure_reason', '')}

=== INSTAGRAM REELS ===
{ig.get('caption', '')}
{'(Turn on the "AI info" label when posting)' if d.get('synthetic_disclosure') else ''}

=== SOURCES ===
""" + "\n".join(job.get("source_urls", [])) + "\n\n=== ASSET RIGHTS ===\n" + \
        "\n".join(f"{r['asset']}: {r['source']} | {r.get('license', '')} {r.get('url', '') or ''}" for r in job.get("rights", []))
    (jd / "UPLOAD_PACKAGE.txt").write_text(txt, encoding="utf-8")
    (jd / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
