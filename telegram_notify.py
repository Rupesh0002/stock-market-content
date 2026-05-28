# ─────────────────────────────────────────────────────────────
#  telegram_notify.py  —  Telegram bot notifications & video delivery
# ─────────────────────────────────────────────────────────────
import logging
from pathlib import Path

import requests

import config

logger = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot{token}/{method}"


def _enabled() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def send_message(text: str) -> None:
    if not _enabled():
        logger.debug("Telegram not configured — skipping message.")
        return
    try:
        resp = requests.post(
            _BASE.format(token=config.TELEGRAM_BOT_TOKEN, method="sendMessage"),
            json={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "HTML",
            },
            timeout=15,
        )
        resp.raise_for_status()
        logger.info("Telegram message sent.")
    except Exception as exc:
        logger.warning("Telegram message failed: %s", exc)


def send_video(path: Path, caption: str = "") -> None:
    if not _enabled():
        logger.debug("Telegram not configured — skipping video upload.")
        return
    try:
        with open(path, "rb") as fh:
            resp = requests.post(
                _BASE.format(token=config.TELEGRAM_BOT_TOKEN, method="sendVideo"),
                data={"chat_id": config.TELEGRAM_CHAT_ID, "caption": caption},
                files={"video": (path.name, fh, "video/mp4")},
                timeout=180,
            )
        resp.raise_for_status()
        logger.info("Telegram video sent: %s", path.name)
    except Exception as exc:
        logger.warning("Telegram video upload failed (%s): %s", path.name, exc)
