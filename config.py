# ─────────────────────────────────────────────────────────────
#  config.py  —  All settings in one place.
#  Secrets are loaded from .env (never commit .env to git).
#  For GitHub Actions, set the same keys as repository secrets.
# ─────────────────────────────────────────────────────────────
import os
from dotenv import load_dotenv

load_dotenv()

# ── Secrets (from .env / environment) ───────────────────────
GEMINI_API_KEY: str      = os.getenv("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN: str  = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str    = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Branding ────────────────────────────────────────────────
CHANNEL_NAME: str = "@CryptoDaily"

# ── Scheduler ───────────────────────────────────────────────
DAILY_RUN_TIME: str = "23:00"     # 24-hour format, local time

# ── Paths ───────────────────────────────────────────────────
OUTPUT_DIR: str = "output"        # Final .mp4 files saved here
TEMP_DIR: str = "temp"            # Intermediate files, auto-cleaned

# ── Video ───────────────────────────────────────────────────
VIDEO_WIDTH: int = 1080
VIDEO_HEIGHT: int = 1920
VIDEO_FPS: int = 30
VIDEO_PRESET: str = "fast"        # ffmpeg preset: ultrafast/fast/medium/slow

# ── Chart ───────────────────────────────────────────────────
CHART_DPI: int = 100              # 1080/100=10.8in × 1920/100=19.2in

# ── Gemini ──────────────────────────────────────────────────
GEMINI_MODEL: str = "gemini-2.0-flash"
# Fallback models tried in order when the primary model returns 429 (quota exhausted).
# gemini-1.5-flash and gemini-2.0-flash-lite have separate free-tier quotas.
GEMINI_MODEL_FALLBACKS: list = [
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]
GEMINI_MAX_RETRIES: int = 3          # retries per model on RATE LIMIT (RPM) 429 only
                                     # quota-exhausted 429s skip immediately to the next model
GEMINI_RETRY_DELAY: int = 15         # base delay in seconds for rate-limit retries; doubles each attempt (15→30→60)
GEMINI_CALL_DELAY: float = 4.0       # seconds between successive Gemini calls (skipped when loading from cache)

# ── Voices ──────────────────────────────────────────────────
VOICE_GAINERS: str  = "en-US-ChristopherNeural"   # energetic
VOICE_OVERVIEW: str = "en-US-GuyNeural"           # calm / authoritative
VOICE_INDIA: str    = "en-US-EricNeural"          # confident / financial

# ── Network ─────────────────────────────────────────────────
MAX_RETRIES: int = 3
RETRY_DELAY_SECONDS: int = 5
RATE_LIMIT_SLEEP: float = 2.0     # seconds between CoinGecko calls
