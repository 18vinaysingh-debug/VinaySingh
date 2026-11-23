# AI Content Factory: YouTube Shorts + Instagram Reels

An automated, quality-checked content pipeline for a Hindi/Hinglish page in two formats:

- **story**: mystery, fascinating facts and storytelling. True stories that are researched and fact-checked.
- **skit**: comedy, entertainment and relatable skits. Original fiction, with 2–3 recurring characters and two voices.

Gemini runs the thinking and **100 specialist agents** (see `roster.yaml`) work in 10 departments. Each video is still checked by you before anything is posted.

---

## How it works

```
Daily run
 ├─ Strategy & Storyline dept  → series bible + recurring characters (first run, or `plan`)
 ├─ Creator Intelligence dept  → learns PATTERNS from the top pages you list (weekly, or `creators`)
 ├─ Trend dept                 → 10 ideas per format, scored → best picked → job_id
 ├─ Research dept              → sources + facts (story) / real-life beats + sensitivities (skit)
 ├─ Writers' room              → story script or skit script (+ shot list)
 ├─ EXPERT PANEL (10-14 specialists picked for this job) → scores + fixes → rewrite if < 7.5
 ├─ Fact-check / Trust & Safety → unsupported claims or offensive jokes go back for rewrite
 ├─ Production                 → voices, visuals, captions, edit, 1080x1920 MP4
 ├─ Distribution dept          → YouTube title/description/tags, Instagram caption, thumbnail
 ├─ QC                         → 10 technical + 7 editorial checks; failures routed to the right agent
 └─ AWAITING YOUR APPROVAL     → approve → YouTube upload (private) · Instagram from package
Analytics → weekly review → lessons feed back into topic selection and scripts
```

**About the 100 agents:** each specialist is an expert brief that runs on Gemini. For any one video, the Orchestrator picks only the 10–15 specialists that video needs and runs them together as **one panel call**. That keeps you inside the free Gemini API limits, at about 10–12 calls per video. To make an agent smarter, edit its brief in `roster.yaml`.

**About learning from top creators:** list their YouTube handles in `config.yaml → creators`. The Creator Intelligence agents read the public stats of those pages' recent videos (views per day, length, titles, posting rhythm) and pull out *patterns*: hook types, structure, packaging and cadence. They are told never to copy jokes, scripts, characters or footage. Instagram pages are not scraped, because that breaks Instagram's rules. The agents study them through Google Search instead.

---

## Setup (Windows, about 20 minutes, once)

1. Install **Python 3.11+** from python.org. Tick "Add Python to PATH".
2. Unzip this folder somewhere, for example `D:\AI Tools\ai_content_factory`.
3. Double-click **START_HERE.bat**. It installs ffmpeg and all libraries, and creates a `.env` file.
4. Open `.env` in Notepad and paste in:
   - `GEMINI_API_KEY`: free key from https://aistudio.google.com/apikey
     *(the API key is separate from your Gemini Pro app subscription. The free API tier is enough for 2 videos a day.)*
   - `PEXELS_API_KEY`: free key from https://www.pexels.com/api/ for licensed stock video (recommended)
   - `YOUTUBE_API_KEY` (optional): lets the creator-study agents read public channel stats
5. In `config.yaml`, set your page name, and add the top creators you want to learn from:
   ```yaml
   creators:
     story: ["@channelhandle1", "@channelhandle2"]
     skit:  ["@channelhandle3"]
   ```
6. Double-click **RUN_DAILY.bat**. The dashboard opens in your browser with the videos to review.

### Connect YouTube upload (optional, once)
1. Go to https://console.cloud.google.com → create a project → enable **YouTube Data API v3**.
2. Set up the OAuth consent screen (External, add yourself as a test user) → Credentials → **Create OAuth client ID → Desktop app** → download the JSON.
3. Save the file as `secrets\client_secret.json`.
4. In **APPROVE_OR_FIX.bat**, run `python run.py youtube-auth` and log in.

After that, approved videos upload as **private**. Flip them to public in YouTube Studio, or set `youtube_privacy: public` in `config.yaml` once you trust the pipeline.

### Run it every day automatically
Open Task Scheduler → Create Basic Task → Daily, at a time of your choice → Action "Start a program" → choose `RUN_DAILY.bat` → in "Start in", enter the folder path. Your PC needs to be on at that time.

---

## Daily routine (about 10 minutes)

1. Open `reports\dashboard.html` and watch each video in "Needs you".
2. Open **APPROVE_OR_FIX.bat** and run one of these:
   - `python run.py approve CONTENT-2026-001` to approve (and upload to YouTube if connected)
   - `python run.py revise CONTENT-2026-001 "hook aur strong karo"` to send it back with your notes
   - `python run.py reject CONTENT-2026-001 "topic weak"` to reject it
3. Post to Instagram from `jobs\<JOB>\` using `final.mp4` and the caption in `UPLOAD_PACKAGE.txt`. Then run `python run.py mark-ig CONTENT-2026-001 https://www.instagram.com/reel/...`
4. Optional: `python run.py metrics CONTENT-2026-001 instagram views=1200 likes=80 shares=12 follows=3`
5. Every Sunday: `python run.py weekly`. The Analytics department writes lessons, and the agents use them from then on.

## Getting more from your Gemini Pro subscription
- **Veo / Flow (in the Gemini app):** each job folder has `veo_prompts.txt`. Generate the clips you like, save them as `jobs\<JOB>\clips\scene_2.mp4` and so on, then run `python run.py rerender <JOB>`. Your clips replace the stock footage. If a clip looks realistic, the disclosure check will make sure it's labelled.
- **Acting in skits yourself:** each skit has a `SHOOT_PLAN.txt`. Film any line on your phone and save it as `clips\scene_N.mp4`. Your video and your own voice replace that scene.
- **Deep Research / NotebookLM:** handy for long-form (6–10 minute) mystery episodes built from your best-performing Shorts.

## All commands
```
python run.py check | agents | plan | creators | daily | status | show JOB
python run.py approve JOB | revise JOB "note" | reject JOB "reason" | rerender JOB
python run.py youtube-auth | mark-ig JOB URL | metrics JOB platform k=v ... | analytics | weekly | dashboard
```

## Settings worth knowing (config.yaml)
- `daily.formats`: how many story and skit videos to start each day
- `panels.pass_score` / `max_rounds`: how strict the expert panel is
- `models.smart`: if you hit Gemini rate limits, change `gemini-2.5-pro` to `gemini-2.5-flash`
- `tts.provider`: `edge` (free Microsoft Hindi voices) or `gemini` (Gemini TTS voices)
- `publishing.require_approval`: keep this `true` until the pipeline has proven itself

## Safety rails built in
Facts must have sources, and unverified claims are rewritten or rejected. Comedy never punches down. Every asset's rights are recorded (stock licence, your own clip, synthetic voice). Synthetic-media disclosure is set on the YouTube upload and flagged for Instagram. Retries are limited, with no endless loops. Nothing is marked "published" without a confirmed URL. Keys stay in `.env` and `secrets\`, and never in logs.
