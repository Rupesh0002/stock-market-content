# Financial Content Bot

Fully automated pipeline that generates two short-form crypto market videos every day and saves them to `/output` ready for manual upload.

---

## What it produces

| Video | Content | Voice |
|---|---|---|
| `gainers_YYYYMMDD.mp4` | Top 5 24h gainers bar chart + energetic script | Christopher Neural |
| `overview_YYYYMMDD.mp4` | Fear & Greed gauge + market stats + calm script | Guy Neural |

Both videos are **1080 × 1920 px** (9:16), **30 fps**, ~45–55 seconds — ready for YouTube Shorts, TikTok, and Instagram Reels.

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.9 + | 3.10 or 3.11 recommended |
| ffmpeg | any recent | Must be on your `PATH` |
| Internet | required | CoinGecko, Alternative.me, Gemini API, edge-tts |

### Install ffmpeg

- **Linux (Debian/Ubuntu):** `sudo apt install ffmpeg`
- **macOS:** `brew install ffmpeg`
- **Windows:** Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add the `bin/` folder to your `PATH`

---

## Setup

### 1. Clone / copy the project

```bash
cd /path/to/your/projects
# copy the financial_content_bot/ folder here
cd financial_content_bot
```

### 2. Create a virtual environment (recommended)

```bash
python -m venv venv

# macOS / Linux
source venv/bin/activate

# Windows
venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Get a free Gemini API key

1. Go to **[https://aistudio.google.com/](https://aistudio.google.com/)**
2. Sign in with a Google account
3. Click **Get API key** → **Create API key**
4. Copy the key (starts with `AIza…`)

### 5. Edit `config.py`

Open `config.py` and fill in at minimum:

```python
GEMINI_API_KEY = "AIzaSy..."      # paste your key here
CHANNEL_NAME   = "@YourChannel"  # your brand name shown in videos
DAILY_RUN_TIME = "09:00"         # 24h local time the scheduler fires
```

---

## Running

### Run once immediately

```bash
python main.py --now
```

### Start the daily scheduler

```bash
python main.py
```

The scheduler will run the pipeline every day at `DAILY_RUN_TIME` (default 09:00) and print a countdown every hour. Press **Ctrl+C** to stop.

### Keep it running in the background

**Linux / macOS — using nohup:**
```bash
nohup python main.py > bot.log 2>&1 &
```

**Linux — using systemd** (create `/etc/systemd/system/content-bot.service`):
```ini
[Unit]
Description=Financial Content Bot

[Service]
WorkingDirectory=/path/to/financial_content_bot
ExecStart=/path/to/venv/bin/python main.py
Restart=always

[Install]
WantedBy=multi-user.target
```
Then: `sudo systemctl enable --now content-bot`

**Windows — Task Scheduler:** Create a Basic Task, trigger Daily at your chosen time, action: run `python main.py --now`.

---

## Project structure

```
financial_content_bot/
├── main.py              ← orchestrator & CLI entry point
├── config.py            ← all settings (edit this)
├── fetcher.py           ← CoinGecko + Fear & Greed data
├── script_generator.py  ← Gemini script generation
├── tts.py               ← edge-tts voiceover generation
├── chart_maker.py       ← matplotlib chart images
├── video_maker.py       ← moviepy video assembly
├── scheduler.py         ← daily schedule loop
├── requirements.txt
├── output/              ← finished .mp4 files (never auto-deleted)
└── temp/                ← intermediate files (auto-deleted after each run)
```

---

## Configuration reference (`config.py`)

| Key | Default | Description |
|---|---|---|
| `GEMINI_API_KEY` | `""` | **Required.** Your Google AI Studio key |
| `CHANNEL_NAME` | `"@CryptoDaily"` | Shown in video footer |
| `DAILY_RUN_TIME` | `"09:00"` | 24h local time for the scheduler |
| `OUTPUT_DIR` | `"output"` | Where finished MP4s are saved |
| `TEMP_DIR` | `"temp"` | Intermediate files (auto-cleaned) |
| `VIDEO_FPS` | `30` | Frames per second |
| `VIDEO_PRESET` | `"fast"` | ffmpeg preset (`ultrafast` → bigger file; `slow` → smaller) |
| `VOICE_GAINERS` | `en-US-ChristopherNeural` | Edge-TTS voice for Script A |
| `VOICE_OVERVIEW` | `en-US-GuyNeural` | Edge-TTS voice for Script B |
| `MAX_RETRIES` | `3` | API call retry attempts |
| `RETRY_DELAY_SECONDS` | `5` | Seconds between retries |
| `RATE_LIMIT_SLEEP` | `2.0` | Seconds between CoinGecko calls |

---

## APIs used

| Service | Key required | Cost | Docs |
|---|---|---|---|
| CoinGecko `/coins/markets` | No | Free | [docs.coingecko.com](https://docs.coingecko.com) |
| CoinGecko `/global` | No | Free | — |
| Alternative.me Fear & Greed | No | Free | [alternative.me/crypto/fear-and-greed-index](https://alternative.me/crypto/fear-and-greed-index/) |
| Google Gemini (`gemini-1.5-flash`) | Yes | Free tier | [aistudio.google.com](https://aistudio.google.com/) |
| Microsoft Edge TTS | No | Free | Via `edge-tts` library |

---

## Troubleshooting

**`GEMINI_API_KEY is empty`** — Add your key to `config.py` (Step 4 above).

**`FileNotFoundError: ffmpeg`** — ffmpeg is not on your PATH. See Prerequisites.

**`decorator` version conflict with moviepy** — Ensure `decorator==4.4.2` is installed: `pip install "decorator==4.4.2"`.

**Charts look wrong / off-screen text** — Fonts vary by OS. The chart code tries several common font paths and falls back to a bitmap font. On headless servers, install DejaVu fonts: `sudo apt install fonts-dejavu`.

**CoinGecko 429 Too Many Requests** — Free tier has a rate limit. The code sleeps 2s between calls. If you hit 429 repeatedly, increase `RATE_LIMIT_SLEEP` to `5.0` in `config.py`.

**Videos are large (>50 MB)** — Change `VIDEO_PRESET = "slow"` in `config.py` for better compression, at the cost of longer encoding time.

---

## Legal

- All scripts end with **"This is not financial advice."**
- CoinGecko and Alternative.me data is attributed in the video charts.
- This tool is for educational / entertainment content only. You are responsible for compliance with the platform policies of any site where you upload the output.
