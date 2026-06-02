# ─────────────────────────────────────────────────────────────
#  script_generator.py  —  Gemini LLM script generation
# ─────────────────────────────────────────────────────────────
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict

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


def _is_quota_exhausted(resp) -> bool:
    """Return True if the 429 is a daily/monthly quota error, not a per-minute rate limit.

    Quota exhaustion: status == RESOURCE_EXHAUSTED or message contains "exceeded your current quota".
    Rate limiting: status == RATE_LIMIT_EXCEEDED — retrying with backoff can succeed.
    Only quota exhaustion should skip immediately to the next model without sleeping.
    """
    try:
        status = resp.json().get("error", {}).get("status", "")
        if status == "RESOURCE_EXHAUSTED":
            return True
    except Exception:
        pass
    msg = resp.text.lower()
    return "exceeded your current quota" in msg or "check your plan and billing" in msg


def _call_gemini(prompt: str) -> str:
    """Send a prompt to the Gemini REST API and return the response text.

    Tries the primary model first, then each fallback model in order.
    - Quota exhaustion (RESOURCE_EXHAUSTED): skips immediately to the next model, no retries.
    - Rate limiting (RPM exceeded): retries up to GEMINI_MAX_RETRIES times with exponential backoff.
    Falls through to the next model only on 429, not on other errors.
    """
    if not config.GEMINI_API_KEY:
        raise ValueError(
            "GEMINI_API_KEY is empty. Add your key to config.py. "
            "Get a free key at: https://aistudio.google.com/"
        )

    models_to_try = [config.GEMINI_MODEL] + list(config.GEMINI_MODEL_FALLBACKS)
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    last_error: Exception = RuntimeError("No models configured.")

    for model in models_to_try:
        url = GEMINI_URL.format(model=model)
        move_to_next = False

        for attempt in range(1, config.GEMINI_MAX_RETRIES + 1):
            resp = requests.post(
                url,
                params={"key": config.GEMINI_API_KEY},
                json=payload,
                timeout=60,
            )

            if resp.status_code == 429:
                if _is_quota_exhausted(resp):
                    # Daily quota hit — retrying this model is pointless, move on immediately
                    last_error = RuntimeError(
                        f"Gemini API error 429: {resp.text[:300]}"
                    )
                    logger.warning("Daily quota exhausted on %s — trying next model.", model)
                    move_to_next = True
                    break

                # Per-minute rate limit — exponential backoff may help
                if attempt < config.GEMINI_MAX_RETRIES:
                    wait = config.GEMINI_RETRY_DELAY * (2 ** (attempt - 1))
                    logger.warning(
                        "Gemini rate limit on %s — waiting %ds (retry %d/%d)",
                        model, wait, attempt, config.GEMINI_MAX_RETRIES,
                    )
                    time.sleep(wait)
                    continue

                last_error = RuntimeError(
                    f"Gemini API error 429 on {model}: {resp.text[:300]}"
                )
                logger.warning("Rate limit retries exhausted on %s — trying next model.", model)
                move_to_next = True
                break

            if not resp.ok:
                raise RuntimeError(
                    f"Gemini API error {resp.status_code} on {model}: {resp.text[:300]}"
                )

            data = resp.json()
            try:
                text = data["candidates"][0]["content"]["parts"][0]["text"]
                if model != config.GEMINI_MODEL:
                    logger.info("Used fallback model: %s", model)
                return text
            except (KeyError, IndexError) as exc:
                raise RuntimeError(
                    f"Unexpected Gemini response shape from {model}: {data}"
                ) from exc

        if not move_to_next:
            break

    raise last_error


# ── Daily script cache ────────────────────────────────────────

def _cache_path(date_str: str) -> Path:
    return Path(config.OUTPUT_DIR) / f"scripts_{date_str}.json"


def _load_cached_scripts(date_str: str) -> Dict[str, str]:
    """Return today's cached scripts (may be partial). Returns empty dict if none."""
    path = _cache_path(date_str)
    if path.exists():
        try:
            with open(path, encoding="utf-8") as fh:
                cached = json.load(fh)
            if cached:
                logger.info(
                    "Loaded %d cached script(s) from %s: %s",
                    len(cached), path, ", ".join(cached.keys()),
                )
            return cached
        except Exception as exc:
            logger.warning("Script cache unreadable (%s) — starting fresh.", exc)
    return {}


def _save_cached_scripts(date_str: str, scripts: Dict[str, str]) -> None:
    Path(config.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    with open(_cache_path(date_str), "w", encoding="utf-8") as fh:
        json.dump(scripts, fh, indent=2)
    logger.info(
        "Scripts cached (%d script(s)) to %s.",
        len(scripts), _cache_path(date_str),
    )


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
    Generate video scripts using Gemini, resuming from partial cache if available.

    Saves each script to disk immediately after generation so that a re-run after
    a quota failure only needs to call Gemini for the scripts that weren't cached yet.

    Args:
        data: Combined market data dict from fetcher.get_market_data().

    Returns:
        {'gainers': <script A>, 'overview': <script B>, 'india': <script C (optional)>}
    """
    date_str = datetime.now().strftime("%Y%m%d")

    # Load whatever was already generated and saved today (possibly partial)
    scripts = _load_cached_scripts(date_str)
    need_india = bool(data.get("india_indices") or data.get("india_stocks"))

    # ── Script A — Gainers ────────────────────────────────────
    if "gainers" not in scripts:
        logger.info("Generating Script A (gainers)…")
        try:
            scripts["gainers"] = _call_gemini(_build_gainers_prompt(data)).strip()
            _save_cached_scripts(date_str, scripts)  # persist immediately in case B/C fail
        except Exception as exc:
            raise RuntimeError(f"Gemini failed on Script A: {exc}") from exc
    else:
        logger.info("Script A (gainers) loaded from cache — skipping API call.")

    # ── Script B — Overview ───────────────────────────────────
    if "overview" not in scripts:
        time.sleep(config.GEMINI_CALL_DELAY)
        logger.info("Generating Script B (overview)…")
        try:
            scripts["overview"] = _call_gemini(_build_overview_prompt(data)).strip()
            _save_cached_scripts(date_str, scripts)
        except Exception as exc:
            raise RuntimeError(f"Gemini failed on Script B: {exc}") from exc
    else:
        logger.info("Script B (overview) loaded from cache — skipping API call.")

    # ── Script C — India (optional) ───────────────────────────
    if need_india and "india" not in scripts:
        time.sleep(config.GEMINI_CALL_DELAY)
        logger.info("Generating Script C (India)…")
        try:
            scripts["india"] = _call_gemini(_build_india_prompt(data)).strip()
            _save_cached_scripts(date_str, scripts)
        except Exception as exc:
            logger.warning("Gemini failed on Script C (India) — skipping: %s", exc)
    elif "india" in scripts:
        logger.info("Script C (India) loaded from cache — skipping API call.")

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
