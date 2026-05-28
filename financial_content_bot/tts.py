# ─────────────────────────────────────────────────────────────
#  tts.py  —  Edge-TTS voiceover generation
# ─────────────────────────────────────────────────────────────
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

import edge_tts
from mutagen.mp3 import MP3

import config

logger = logging.getLogger(__name__)


# ── Async core ────────────────────────────────────────────────

async def _synthesise(text: str, voice: str, output_path: Path) -> None:
    """Synthesise speech and save to an MP3 file using edge-tts."""
    communicate = edge_tts.Communicate(text=text, voice=voice)
    await communicate.save(str(output_path))


# ── Public helpers ────────────────────────────────────────────

def generate_voiceover(text: str, voice: str, output_path: Path) -> None:
    """
    Generate a voiceover MP3 at *output_path* using edge-tts.

    Uses asyncio.run() which is cross-platform on Python 3.7+.
    On Windows, also sets the Selector event-loop policy to avoid
    known ProactorEventLoop compatibility issues with edge-tts.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(_synthesise(text, voice, output_path))
    except Exception as exc:
        raise RuntimeError(
            f"edge-tts failed for voice '{voice}' → {output_path.name}: {exc}"
        ) from exc

    logger.info("Voiceover saved: %s", output_path.name)


def get_audio_duration(path: Path) -> float:
    """
    Return the duration of an MP3 file in seconds using mutagen.

    Args:
        path: Absolute or relative path to the .mp3 file.

    Returns:
        Duration as a float (seconds).
    """
    try:
        audio = MP3(str(path))
        return float(audio.info.length)
    except Exception as exc:
        raise RuntimeError(f"Cannot read duration of '{path}': {exc}") from exc


# ── Pipeline entry point ──────────────────────────────────────

def generate_all_voiceovers(scripts: Dict[str, str]) -> Dict[str, Path]:
    """
    Generate voiceover MP3 files for both scripts.

    Args:
        scripts: {'gainers': <text>, 'overview': <text>}

    Returns:
        {'gainers': Path, 'overview': Path}
    """
    temp_dir = Path(config.TEMP_DIR)
    temp_dir.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")

    voice_map: Dict[str, str] = {
        "gainers":  config.VOICE_GAINERS,
        "overview": config.VOICE_OVERVIEW,
        "india":    config.VOICE_INDIA,
    }

    paths: Dict[str, Path] = {}
    for key, text in scripts.items():
        voice = voice_map.get(key, config.VOICE_OVERVIEW)
        path  = temp_dir / f"vo_{key}_{date_str}.mp3"
        paths[key] = path
        logger.info("Synthesising '%s' with voice %s…", key, voice)
        generate_voiceover(text, voice, path)
        duration = get_audio_duration(path)
        logger.info("  → %s  (%.1fs)", path.name, duration)

    return paths
