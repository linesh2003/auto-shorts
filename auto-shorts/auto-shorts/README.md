# Auto-Shorts Pipeline

Turns your (or your friends') stream VODs into vertical Shorts with viral
karaoke captions — automatically — and uploads them to YouTube after **you
approve each draft** in Telegram. 100% free, no usage limits, runs entirely
on GitHub's servers, so any laptop works.

```
VOD url ──> download ──> find hype moments ──> cut + captions ──> Telegram draft
                                                                      │
                                              you reply "approve d2026..." 
                                                                      ▼
                                              YouTube upload (hourly job)
```

Two GitHub Actions jobs do all the work:

| Workflow | When | What it does |
| --- | --- | --- |
| **produce drafts** | 2×/day (06:00 & 18:00 UTC) + manual button | Downloads your configured VODs, transcribes them, scores hype moments (keywords + speech rate + loudness + optional chat spam), renders vertical drafts with captions, sends each to your Telegram |
| **publish approved** | hourly + manual button | Reads your Telegram "approve / reject" replies, uploads approved drafts to YouTube, respects a daily upload cap |

## What you need (all free)

- A GitHub account
- A Google account (for the YouTube upload permission)
- Telegram (any device) — this is your approval inbox
- ~30 minutes of one-time setup

---

## Setup — Step 1: Put this folder into YOUR GitHub repo

1. Create a GitHub account if you don't have one → [github.com/signup](https://github.com/signup)
2. Click the **+** (top right) → **New repository** → name it `auto-shorts`,
   set it **Public** (public = unlimited free Actions minutes), click **Create**.
3. Upload this folder's contents:
   - easiest: on the repo page press `.` (period) → GitHub's web editor opens →
     drag-and-drop all files from this folder (keep the folder structure!) → commit.
   - or with git installed:
     ```bash
     cd auto-shorts
     git init && git remote add origin https://github.com/YOURNAME/auto-shorts.git
     git add -A && git commit -m "auto-shorts" && git push -u origin main
     ```
   - if you drag-drop a folder, make sure `.github/workflows/` kept its two
     YAML files — hidden folders sometimes don't upload in the browser.

## Step 2: Create your Telegram approval bot (5 min)

1. In Telegram, open **@BotFather** → send `/newbot` → give it a name (e.g.
   `My Shorts Studio`) and a username ending in `bot`. BotFather replies with a
   **token** like `123456:AA...` — copy it.
2. Message your new bot once (send "hi") — this unlocks it to talk to you.
3. Get your chat id: open in a browser
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
   and find `"chat":{"id": 123456789, ...}` in the response — that number is
   your **chat id**. (If the page is empty, send the bot another message first.)

## Step 3: Get YouTube upload permission (10 min)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) →
   top bar → **New project** → name it `shorts-pipeline` → Create.
2. In the search bar type **YouTube Data API v3** → open it → **Enable**.
3. Left menu → **APIs & Services → OAuth consent screen** →
   - User type **External** → Create
   - App name anything, your email, Developer email → Save
   - **Audience → Test users → + Add users** → add **your own Google account**
     (mandatory or login will fail).
4. **APIs & Services → Credentials → + Create credentials → OAuth client ID**
   - Application type: **Desktop app** → Create
   - Copy the **Client ID** and **Client secret**.

## Step 4: One-time token exchange (on your own computer, 2 min)

You need Python installed (or run it in Google Colab). Then:

```bash
pip install requests
python scripts/make_token.py
```

- Paste your Client ID + Secret when asked.
- Your browser opens Google's login → choose the SAME account you added as a
  test user → **Allow**. (If you see "app not verified", click Advanced →
  Go to app — it's your own app.)
- The script prints three values. **Keep the terminal open.**

## Step 5: Add the 5 secrets to your repo

On your repo page: **Settings → Secrets and variables → Actions → New repository
secret** — add each of these (from the steps above):

| Secret name | Value |
| --- | --- |
| `TELEGRAM_BOT_TOKEN` | from BotFather (step 2) |
| `TELEGRAM_CHAT_ID` | your numeric chat id (step 2) |
| `YT_CLIENT_ID` | from step 3/4 |
| `YT_CLIENT_SECRET` | from step 3/4 |
| `YT_REFRESH_TOKEN` | printed by make_token.py (step 4) |

## Step 6: Tell it what to clip

Edit **config.yaml** (via the web editor: press `.` on your repo):

1. Replace the placeholder under `sources:` with a real VOD URL:
   ```yaml
   sources:
     - type: vod_url
       url: "https://www.twitch.tv/videos/123456789"
       credit: "StreamersName"
   ```
   Any Twitch VOD / Kick / YouTube video link that yt-dlp supports works.
   **Only clip streams you own or have permission to clip** — reuploading
   others' content gets your channel copyright-struck.
2. Tune `keywords:` to your game/streamer (the words that mark hype moments).
3. Style: `crop_mode: blur_pad` (gameplay) or `center` (action mid-screen),
   caption size, clip length, hook duration — all there with comments.

## Step 7: First run + your first clip

1. Repo → **Actions** tab → if asked, click **I understand my workflows, go
   ahead and enable them**.
2. Click **produce drafts** → **Run workflow** → **Run workflow**.
3. Wait ~10-20 min (first run also downloads the Whisper model). Green check =
   drafts are in your Telegram, each as a video with its draft id.
4. Reply to the bot: `approve d20261123-...` (the id in the message).
5. Within the hour the **publish approved** job uploads it — the bot messages
   you the live YouTube link. (You can also run publish manually from Actions.)

From then on it runs itself: drafts twice a day, uploads hourly after your
approval. Change the cron times in `.github/workflows/*.yml` if you want.

---

## Daily rhythm & honest limits

- **Drafts per run**: default 3 (config `schedule.drafts_per_run`).
- **Uploads per day**: default 4 — the YouTube API free quota allows max 6/day.
- **Action minutes**: unlimited for public repos (private repos: 2000 min/month
  free — a run uses ~20-30 min).
- **Your approval step is the point**: YouTube demonetizes mass-produced
  auto-uploads ("inauthentic content" policy, enforced since 2025). Watching
  each draft 10 seconds and hitting approve keeps you in the clear AND is your
  quality gate. Don't skip it, don't run 6 auto-uploads a day of raw clips.
- **Copyright**: clip your own streams or streamers who allow clips
  (check their channel rules). Clips of someone else's stream without
  permission = strikes = channel death.

## Optional: use Twitch chat as a hype radar

Chat spam spikes = hype. Generate a chat log once per VOD on your PC with
[TwitchDownloader](https://github.com/lay295/TwitchDownloader):
`TwitchDownloaderCLI chatdownload -u <VOD_ID> -o <VOD_ID>.json` — then commit
the file to the repo's `work/` folder named exactly after the VOD id
(`123456789.json`). The moment-finder picks it up automatically and boosts
windows where chat exploded. Without it, audio + keywords still work fine.

## Testing locally (optional)

```bash
pip install -r requirements.txt        # needs ffmpeg on PATH
python -m pipeline.run produce --count 1 --local path/to/video.mp4 --dry-run
```
Drafts land in `drafts/` — same rendering as the cloud, no Telegram needed.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| Workflow doesn't run | Actions tab → enable workflows; check both YAML files exist |
| "no hype moments found" | Loosen `keywords`, lower `style.min_clip_seconds`, or add the chat JSON |
| Telegram message never arrives | Re-check `TELEGRAM_BOT_TOKEN` (no spaces), send the bot any message once, re-check chat id |
| Token errors on upload | `YT_REFRESH_TOKEN` wrong or expired → rerun `scripts/make_token.py`; make sure you completed consent-screen test users |
| Upload quota errors | You hit 6 uploads/day — wait for the quota reset (midnight PT) |
| Clips cut at wrong moments | Lower `whisper_model` to `base` if timing looks off, or raise `min_clip_seconds` |
| Draft too long/short | `style.min/max_clip_seconds` in config |

## File map

```
pipeline/
  run.py        orchestrator (produce / publish)
  download.py   yt-dlp source fetching
  moments.py    whisper transcription + hype scoring
  captions.py   ASS karaoke caption + hook banner generator
  render.py     two-pass ffmpeg renderer (cut -> vertical + captions)
  telegram.py   draft delivery + approval polling
  upload.py     YouTube Data API resumable upload
  state.py      state/state.json (what's pending/approved/uploaded)
  config.py     config.yaml loader
scripts/
  make_token.py one-time YouTube OAuth setup
.github/workflows/
  produce.yml   the twice-daily draft job
  publish.yml   the hourly upload job
state/state.json  committed automatically by the workflows — do not edit by hand
```
