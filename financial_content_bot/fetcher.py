# ─────────────────────────────────────────────────────────────
#  fetcher.py  —  CoinGecko + Fear & Greed data fetching
# ─────────────────────────────────────────────────────────────
import logging
import time
from typing import Any, Dict, List, Optional

import requests

import config

logger = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
FEAR_GREED_URL = "https://api.alternative.me/fng/"

YAHOO_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://finance.yahoo.com",
}
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
    "Referer": "https://www.nseindia.com/",
    "Accept-Language": "en-US,en;q=0.9",
}

INDIA_INDICES = [
    ("^NSEI",    "Nifty 50"),
    ("^BSESN",   "Sensex"),
    ("^NSEBANK", "Bank Nifty"),
    ("^CNXIT",   "Nifty IT"),
]


# ── Low-level HTTP ────────────────────────────────────────────

def _get(url: str, params: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
    """GET a URL with retry logic. Returns parsed JSON or None on failure."""
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=params, timeout=20)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as exc:
            logger.warning(
                "HTTP %s from %s (attempt %d/%d): %s",
                exc.response.status_code, url, attempt, config.MAX_RETRIES, exc,
            )
        except requests.exceptions.RequestException as exc:
            logger.warning(
                "Request error for %s (attempt %d/%d): %s",
                url, attempt, config.MAX_RETRIES, exc,
            )
        if attempt < config.MAX_RETRIES:
            logger.info("Retrying in %ss…", config.RETRY_DELAY_SECONDS)
            time.sleep(config.RETRY_DELAY_SECONDS)
    return None


# ── Individual API calls ──────────────────────────────────────

def fetch_coin_markets() -> List[Dict]:
    """Fetch the top-250 coins by market cap from CoinGecko /coins/markets."""
    logger.debug("Fetching /coins/markets…")
    data = _get(
        f"{COINGECKO_BASE}/coins/markets",
        params={
            "vs_currency": "usd",
            "order": "market_cap_desc",
            "per_page": 250,
            "page": 1,
            "sparkline": False,
            "price_change_percentage": "24h",
        },
    )
    if not data:
        raise RuntimeError("Failed to fetch coin markets from CoinGecko.")
    time.sleep(config.RATE_LIMIT_SLEEP)
    return data


def fetch_fear_greed() -> Dict[str, Any]:
    """Fetch the current Fear & Greed Index from alternative.me."""
    logger.debug("Fetching Fear & Greed index…")
    data = _get(FEAR_GREED_URL, params={"limit": 1})
    if not data or not data.get("data"):
        raise RuntimeError("Failed to fetch Fear & Greed Index.")
    time.sleep(config.RATE_LIMIT_SLEEP)
    return data["data"][0]


def fetch_global_market() -> Dict[str, Any]:
    """Fetch global crypto market stats from CoinGecko /global."""
    logger.debug("Fetching /global market data…")
    data = _get(f"{COINGECKO_BASE}/global")
    if not data or not data.get("data"):
        raise RuntimeError("Failed to fetch global market data from CoinGecko.")
    time.sleep(config.RATE_LIMIT_SLEEP)
    return data["data"]


# ── Indian market data ────────────────────────────────────────

def fetch_india_indices() -> List[Dict]:
    """Fetch Nifty 50, Sensex, Bank Nifty, Nifty IT from Yahoo Finance."""
    logger.debug("Fetching India indices…")
    indices = []
    for sym, name in INDIA_INDICES:
        try:
            resp = requests.get(
                f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}",
                params={"interval": "1d", "range": "1d"},
                headers=YAHOO_HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            meta  = resp.json()["chart"]["result"][0]["meta"]
            price = meta.get("regularMarketPrice", 0)
            prev  = meta.get("previousClose") or meta.get("chartPreviousClose", 0)
            chg   = round(((price - prev) / prev * 100) if prev else 0, 2)
            indices.append({"symbol": sym, "name": name, "price": price, "change_pct": chg})
        except Exception as exc:
            logger.warning("Index fetch failed for %s: %s", sym, exc)
        time.sleep(0.3)
    return indices


def _nse_session() -> requests.Session:
    """Return a requests session with valid NSE cookies."""
    sess = requests.Session()
    sess.get(
        "https://www.nseindia.com/",
        headers={"User-Agent": NSE_HEADERS["User-Agent"], "Accept": "text/html"},
        timeout=15,
    )
    return sess


def fetch_india_stocks() -> List[Dict]:
    """Fetch top 5 NSE daily gainers from F&O eligible stocks."""
    logger.debug("Fetching NSE top gainers…")
    try:
        sess = _nse_session()
        resp = sess.get(
            "https://www.nseindia.com/api/live-analysis-variations?index=gainers",
            headers=NSE_HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        raw  = data.get("FOSec", {}).get("data", []) or data.get("NIFTY", {}).get("data", [])
        return [
            {
                "symbol":     s["symbol"],
                "price":      s["ltp"],
                "change_pct": s["perChange"],
            }
            for s in raw[:5]
        ]
    except Exception as exc:
        logger.warning("NSE stock fetch failed (market may be closed): %s", exc)
        return []


# ── Aggregator ────────────────────────────────────────────────

def get_market_data() -> Dict[str, Any]:
    """
    Fetch and combine all required market data.

    Returns a dict with:
        gainers   – list[dict] top-5 24h gainers
        losers    – list[dict] top-5 24h losers
        fear_greed – dict with 'value' (int) and 'classification' (str)
        market    – dict with total_market_cap, volume, btc_dominance, …
    """
    logger.info("Fetching coin market data…")
    coins  = fetch_coin_markets()

    # Filter out coins without valid 24h data, then rank
    valid = [c for c in coins if c.get("price_change_percentage_24h") is not None]
    ranked = sorted(valid, key=lambda c: c["price_change_percentage_24h"], reverse=True)

    gainers = ranked[:5]
    losers = list(reversed(ranked[-5:]))   # worst first

    logger.info("Fetching Fear & Greed index…")
    fg_raw = fetch_fear_greed()
    fear_greed = {
        "value": int(fg_raw["value"]),
        "classification": fg_raw["value_classification"],
    }

    logger.info("Fetching global market stats…")
    gm = fetch_global_market()
    market = {
        "total_market_cap_usd": gm["total_market_cap"].get("usd", 0),
        "total_volume_24h_usd": gm["total_volume"].get("usd", 0),
        "btc_dominance": gm["market_cap_percentage"].get("btc", 0),
        "eth_dominance": gm["market_cap_percentage"].get("eth", 0),
        "market_cap_change_24h_pct": gm.get("market_cap_change_percentage_24h_usd", 0),
        "active_cryptocurrencies": gm.get("active_cryptocurrencies", 0),
    }

    logger.info("Fetching India indices…")
    india_indices = fetch_india_indices()

    logger.info("Fetching NSE top gainers…")
    india_stocks = fetch_india_stocks()

    if india_stocks:
        logger.info("Top NSE stock: %s +%.1f%%", india_stocks[0]["symbol"], india_stocks[0]["change_pct"])
    else:
        logger.warning("No NSE stock data — market may be closed.")

    logger.info(
        "Data ready — top crypto: %s +%.1f%%  |  F&G: %s (%s)",
        gainers[0]["symbol"].upper(),
        gainers[0]["price_change_percentage_24h"],
        fear_greed["value"],
        fear_greed["classification"],
    )

    return {
        "gainers":       gainers,
        "losers":        losers,
        "fear_greed":    fear_greed,
        "market":        market,
        "india_stocks":  india_stocks,
        "india_indices": india_indices,
    }
