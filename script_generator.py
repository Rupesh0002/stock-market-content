# ─────────────────────────────────────────────────────────────
#  script_generator.py  —  Gemini LLM script generation
# ─────────────────────────────────────────────────────────────
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import requests

import config

logger = logging.getLogger(__name__)


# ── Helpers ───────────────────────────────────────────────────

def _fmt_price(price: float) -> str:
    """Format a coin price with appropriate decimal places."""
    if price < 0.001:
        return f"${price:.6f}"
    if price < 1:
        return f"${price:.4f}"
    if price < 100:
        return f"${price:.2f}"
    return f"${price:,.2f}"


def _fmt_billions(n: float) -> str:
    """Format large USD values as T or B strings."""
    if n >= 1e12:
        return f"${n / 1e12:.2f} trillion"
    return f"${n / 1e9:.1f} billion"


GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models"
    "/{model}:generateContent"
)


def _call_gemini(prompt: str) -> str:
    """Send a prompt to the Gemini REST API and return the response text.

    Retries up to GEMINI_MAX_RETRIES times on 429 quota errors, with
    exponential backoff (30 s → 60 s → 120 s).
    """
    if not config.GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is empty. Add your key to config.py. "
            "Get a free key at: https://aistudio.google.com/"
        )
    url = GEMINI_URL.format(model=config.GEMINI_MODEL)
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    for attempt in range(1, config.GEMINI_MAX_RETRIES + 1):
        resp = requests.post(
            url,
            params={"key": config.GEMINI_API_KEY},
            json=payload,
            timeout=60,
        )
        if resp.status_code == 429:
            if attempt < config.GEMINI_MAX_RETRIES:
                wait = config.GEMINI_RETRY_DELAY * (2 ** (attempt - 1))
                logger.warning(
                    "Gemini quota hit (429) — waiting %ds before retry %d/%d",
                    wait, attempt, config.GEMINI_MAX_RETRIES,
                )
                time.sleep(wait)
                continue
            raise RuntimeError(
                f"Gemini API error {resp.status_code}: {resp.text[:300]}"
            )
        if not resp.ok:
            raise RuntimeError(
                f"Gemini API error {resp.status_code}: {resp.text[:300]}"
            )
        data = resp.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected Gemini response shape: {data}") from exc

    raise RuntimeError("Gemini API failed after all retries.")


# ── Daily script cache ────────────────────────────────────────

def _cache_path(date_str: str) -> Path:
    return Path(config.OUTPUT_DIR) / f"scripts_{date_str}.json"


def _load_cached_scripts(date_str: str) -> Optional[Dict[str, str]]:
    """Return today's cached scripts if available, else None."""
    path = _cache_path(date_str)
    if path.exists():
        try:
            with open(path, encoding="utf-8") as fh:
                cached = json.load(fh)
            logger.info("Using cached scripts from %s — skipping Gemini API calls.", path)
            return cached
        except Exception as exc:
            logger.warning("Script cache unreadable (%s) — regenerating.", exc)
    return None


def _save_cached_scripts(date_str: str, scripts: Dict[str, str]) -> None:
    Path(config.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    with open(_cache_path(date_str), "w", encoding="utf-8") as fh:
        json.dump(scripts, fh, indent=2)
    logger.info("Scripts cached to %s.", _cache_path(date_str))


# ── Prompt builders ───────────────────────────────────────────

def _build_gainers_prompt(data: Dict) -> str:
    """Build the prompt for Script A (Top Gainers — upbeat/exciting)."""
    top3 = data["gainers"][:3]
    fg = data["fear_greed"]

    coins_block = "\n".join(
        f"  • {c['symbol'].upper()} ({c['name']}): "
        f"+{c['price_change_percentage_24h']:.1f}% | price {_fmt_price(c['current_price'])}"
        for c in top3
    )

    return f"""You are writing a YouTube Shorts / TikTok voiceover script about today's top crypto gainers.

LIVE MARKET DATA (use these exact numbers):
{coins_block}
Fear & Greed Index: {fg['value']} — {fg['classification']}

STRICT REQUIREMENTS:
1. EXACTLY 110–130 words total (count every word carefully before finishing)
2. First sentence must be a punchy hook naming a specific coin and its gain (e.g., "One coin just pumped 40% overnight…")
3. Mention 2–3 coins with their exact % gains and prices
4. Include ONE sentence referencing the Fear & Greed reading of {fg['value']} ({fg['classification']})
5. Final two lines must be EXACTLY:
   Follow for daily crypto updates.
   This is not financial advice.
6. Tone: upbeat, energetic, like an excited knowledgeable friend — NOT a news anchor
7. No hashtags, no stage directions, no [brackets], no asterisks
8. No markdown formatting — plain text only

OUTPUT: The script text only. No intro, no labels, no word count annotation."""


def _build_overview_prompt(data: Dict) -> str:
    """Build the prompt for Script B (Market Overview — calm/informative)."""
    fg = data["fear_greed"]
    mkt = data["market"]
    top2 = data["gainers"][:2]

    coins_block = "\n".join(
        f"  • {c['symbol'].upper()}: +{c['price_change_percentage_24h']:.1f}% | {_fmt_price(c['current_price'])}"
        for c in top2
    )

    return f"""You are writing a calm, informative YouTube Shorts / TikTok voiceover script giving a crypto market overview.

LIVE MARKET DATA (use these exact numbers):
Fear & Greed Index: {fg['value']} — {fg['classification']}
Total Market Cap: {_fmt_billions(mkt['total_market_cap_usd'])}
24h Trading Volume: {_fmt_billions(mkt['total_volume_24h_usd'])}
Bitcoin Dominance: {mkt['btc_dominance']:.1f}%
Market Cap Change (24h): {mkt['market_cap_change_24h_pct']:+.1f}%
Today's top movers:
{coins_block}

STRICT REQUIREMENTS:
1. EXACTLY 110–130 words total (count every word carefully before finishing)
2. Open with a hook built around the Fear & Greed reading of {fg['value']} ({fg['classification']})
3. Cover total market cap, 24h volume, and BTC dominance — use exact figures
4. Mention 1–2 specific movers with exact percentages
5. One sentence explaining what a {fg['classification']} reading signals for traders
6. Final two lines must be EXACTLY:
   Follow for daily crypto updates.
   This is not financial advice.
7. Tone: calm, authoritative, measured — like a trusted financial commentator
8. No hashtags, no stage directions, no [brackets], no asterisks
9. No markdown formatting — plain text only

OUTPUT: The script text only. No intro, no labels, no word count annotation."""


def _build_india_prompt(data: Dict) -> str:
    """Build the prompt for Script C (Indian Market — indices + NSE gainers)."""
    indices = data.get("india_indices", [])
    stocks  = data.get("india_stocks", [])[:3]

    indices_block = "\n".join(
        f"  • {idx['name']}: {'+' if idx['change_pct'] >= 0 else ''}{idx['change_pct']:.2f}%"
        f"  |  {idx['price']:,.0f} pts"
        for idx in indices
    )
    stocks_block = "\n".join(
        f"  • {s['symbol']}: +{s['change_pct']:.1f}%  |  ₹{s['price']:,.1f}"
        for s in stocks
    )

    return f"""You are writing a YouTube Shorts / TikTok voiceover about today's Indian stock market performance.

LIVE MARKET DATA (use these exact numbers):
Key Indices:
{indices_block}

Top NSE Gainers:
{stocks_block}

STRICT REQUIREMENTS:
1. EXACTLY 110–130 words total (count every word carefully before finishing)
2. Open with a hook about the overall market direction (Nifty 50 or Sensex move)
3. Mention 2–3 index moves with exact % changes
4. Name 1–2 top NSE stock gainers with their exact % gains
5. Final two lines must be EXACTLY:
   Follow for daily market updates.
   This is not financial advice.
6. Tone: confident and informative — like an Indian financial news anchor
7. No hashtags, no stage directions, no [brackets], no asterisks
8. No markdown formatting — plain text only

OUTPUT: The script text only. No intro, no labels, no word count annotation."""


# ── Main generator ────────────────────────────────────────────

def generate_scripts(data: Dict) -> Dict[str, str]:
    """
    Generate both video scripts using Gemini.

    Args:
        data: Combined market data dict from fetcher.get_market_data().

    Returns:
        {'gainers': <script A text>, 'overview': <script B text>}
    """
    date_str = datetime.now().strftime("%Y%m%d")

    cached = _load_cached_scripts(date_str)
    if cached:
        return cached

    logger.info("Generating Script A (gainers)…")
    try:
        script_a = _call_gemini(_build_gainers_prompt(data)).strip()
    except Exception as exc:
        raise RuntimeError(f"Gemini failed on Script A: {exc}") from exc

    time.sleep(config.GEMINI_CALL_DELAY)

    logger.info("Generating Script B (overview)…")
    try:
        script_b = _call_gemini(_build_overview_prompt(data)).strip()
    except Exception as exc:
        raise RuntimeError(f"Gemini failed on Script B: {exc}") from exc

    scripts = {"gainers": script_a, "overview": script_b}

    if data.get("india_indices") or data.get("india_stocks"):
        time.sleep(config.GEMINI_CALL_DELAY)
        logger.info("Generating Script C (India)…")
        try:
            script_c = _call_gemini(_build_india_prompt(data)).strip()
            scripts["india"] = script_c
        except Exception as exc:
            logger.warning("Gemini failed on Script C (India) — skipping: %s", exc)

    _save_cached_scripts(date_str, scripts)

    # ── Log scripts to /temp for review ──────────────────────
    temp_dir = Path(config.TEMP_DIR)
    temp_dir.mkdir(exist_ok=True)
    log_path = temp_dir / f"script_{date_str}.txt"

    with open(log_path, "w", encoding="utf-8") as fh:
        for key, text in scripts.items():
            word_count = len(text.split())
            fh.write(f"{'='*60}\n")
            fh.write(f"SCRIPT: {key.upper()}  |  words: {word_count}\n")
            fh.write(f"{'='*60}\n")
            fh.write(text + "\n\n")

    logger.info(
        "Scripts saved to %s  (%s)",
        log_path,
        "  |  ".join(f"{k}: {len(v.split())} words" for k, v in scripts.items()),
    )

    return scripts
