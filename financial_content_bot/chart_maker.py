# ─────────────────────────────────────────────────────────────
#  chart_maker.py  —  Matplotlib 1080×1920 chart generation
# ─────────────────────────────────────────────────────────────
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple

import matplotlib
matplotlib.use("Agg")            # non-interactive, safe for servers & Windows
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from PIL import Image

import config

logger = logging.getLogger(__name__)

# ── Canvas constants ──────────────────────────────────────────
DPI = config.CHART_DPI
W_PX, H_PX = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
W_IN, H_IN = W_PX / DPI, H_PX / DPI   # 10.8 × 19.2 inches

# ── Palette ───────────────────────────────────────────────────
BG      = "#0D0D0D"
GREEN   = "#00FF88"
RED     = "#FF3355"
ORANGE  = "#FF8844"
YELLOW  = "#FFE033"
WHITE   = "#FFFFFF"
GREY    = "#888888"
CARD_BG = "#161624"
CARD_BD = "#2A2A44"


# ── Utility ───────────────────────────────────────────────────

def _fmt_price(price: float) -> str:
    """Return a human-readable price string."""
    if price < 0.001:
        return f"${price:.6f}"
    if price < 1:
        return f"${price:.4f}"
    if price < 1_000:
        return f"${price:,.2f}"
    return f"${price:,.0f}"


def _fmt_large(n: float) -> str:
    """Format large USD values as compact strings."""
    if n >= 1e12:
        return f"${n / 1e12:.2f}T"
    if n >= 1e9:
        return f"${n / 1e9:.1f}B"
    return f"${n / 1e6:.0f}M"


def _fg_color(value: int) -> str:
    """Return Fear & Greed colour based on numeric value."""
    if value < 25:
        return RED
    if value < 50:
        return ORANGE
    if value < 75:
        return YELLOW
    return GREEN


def _ensure_exact_size(path: Path) -> None:
    """Crop/resize output to exactly W_PX × H_PX using PIL."""
    img = Image.open(str(path))
    if img.size != (W_PX, H_PX):
        img = img.resize((W_PX, H_PX), Image.LANCZOS)
        img.save(str(path))


def _new_figure() -> Tuple[plt.Figure, plt.Axes]:
    """Create a full-bleed figure with a coordinate system 0–10 × 0–20."""
    fig = plt.figure(figsize=(W_IN, H_IN), dpi=DPI)
    fig.patch.set_facecolor(BG)
    ax = fig.add_axes([0, 0, 1, 1])      # axes fills the entire canvas
    ax.set_facecolor(BG)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 20)
    ax.axis("off")
    return fig, ax


def _save(fig: plt.Figure, path: Path) -> None:
    """Save figure at exact pixel dimensions then verify size."""
    fig.savefig(str(path), dpi=DPI, facecolor=BG, pad_inches=0)
    plt.close(fig)
    _ensure_exact_size(path)


# ── Chart A — Top Gainers horizontal bars ────────────────────

def _gainers_chart(data: Dict) -> Path:
    """
    Generate a 1080×1920 horizontal bar chart of the top-5 24h gainers.

    Saves to /temp/chart_gainers_YYYYMMDD.png and returns the path.
    """
    gainers = data["gainers"][:5]
    date_str = datetime.now().strftime("%Y%m%d")
    out = Path(config.TEMP_DIR) / f"chart_gainers_{date_str}.png"

    fig, ax = _new_figure()

    # ── Title block ──────────────────────────────────────────
    ax.text(5, 19.3, "Today's Top Gainers",
            color=WHITE, fontsize=68, fontweight="bold",
            ha="center", va="top", fontfamily="sans-serif")
    ax.text(5, 18.2, "24-Hour Performance",
            color=GREY, fontsize=36, ha="center", va="top")

    # Thin separator line
    ax.axhline(17.6, color="#222222", linewidth=2, xmin=0.05, xmax=0.95)

    # ── Bars ─────────────────────────────────────────────────
    max_change = max(c["price_change_percentage_24h"] for c in gainers)
    max_change = max(max_change, 1)   # avoid division by zero

    x_label   = 0.4     # rank + symbol zone
    x_bar_s   = 2.6     # bar start
    x_bar_e   = 9.4     # bar end (full width)
    bar_h     = 1.05
    y_centers = [15.8, 12.8, 9.8, 6.8, 3.8]

    for i, (coin, yc) in enumerate(zip(gainers, y_centers)):
        sym    = coin["symbol"].upper()
        chg    = coin["price_change_percentage_24h"]
        price  = coin["current_price"]
        bw     = max(0.08, (chg / max_change) * (x_bar_e - x_bar_s))

        # Subtle background track
        ax.add_patch(mpatches.FancyBboxPatch(
            (x_bar_s, yc - bar_h / 2), x_bar_e - x_bar_s, bar_h,
            boxstyle="round,pad=0.05",
            facecolor="#1A2A1A", edgecolor="none", zorder=1,
        ))

        # Green fill bar
        ax.add_patch(mpatches.FancyBboxPatch(
            (x_bar_s, yc - bar_h / 2), bw, bar_h,
            boxstyle="round,pad=0.05",
            facecolor=GREEN, edgecolor="none", alpha=0.88, zorder=2,
        ))

        # Rank badge
        ax.add_patch(plt.Circle((x_label, yc + 0.3), 0.38,
                                color="#1E2E1E", zorder=2))
        ax.text(x_label, yc + 0.3, f"#{i+1}",
                color=GREEN, fontsize=24, fontweight="bold",
                ha="center", va="center", zorder=3)

        # Coin symbol
        ax.text(x_bar_s - 0.15, yc + 0.2, sym,
                color=WHITE, fontsize=38, fontweight="bold",
                ha="right", va="center", zorder=3)

        # Price (smaller, below symbol)
        ax.text(x_bar_s - 0.15, yc - 0.32, _fmt_price(price),
                color=GREY, fontsize=22, ha="right", va="center", zorder=3)

        # Percentage — after bar, or inside if bar is wide
        pct_str = f"+{chg:.1f}%"
        pct_x   = x_bar_s + bw + 0.18
        ax.text(pct_x, yc, pct_str,
                color=GREEN, fontsize=32, fontweight="bold",
                ha="left", va="center", zorder=3)

    # ── Footer ────────────────────────────────────────────────
    ax.axhline(1.8, color="#222222", linewidth=2, xmin=0.05, xmax=0.95)
    ax.text(5, 1.2, f"Source: CoinGecko  •  {config.CHANNEL_NAME}",
            color=GREY, fontsize=24, ha="center", va="center")

    _save(fig, out)
    logger.info("Chart A saved: %s", out.name)
    return out


# ── Chart B — Fear & Greed gauge + market stats ───────────────

def _draw_gauge(ax: plt.Axes, cx: float, cy: float, r_out: float,
                r_in: float, value: int) -> None:
    """
    Draw a semicircular Fear & Greed gauge at (cx, cy) in data coordinates.

    value 0 → left  (180°)
    value 100 → right (0°)
    """
    # Coloured wedge sections
    sections = [
        (0,  25,  RED,    "Extreme Fear"),
        (25, 50,  ORANGE, "Fear"),
        (50, 75,  YELLOW, "Greed"),
        (75, 100, GREEN,  "Extreme Greed"),
    ]
    for lo, hi, colour, _ in sections:
        # matplotlib angles: CCW from positive-x, so value=0 → 180°, value=100 → 0°
        ang_lo = 180.0 - hi * 1.8   # 1.8 = 180/100
        ang_hi = 180.0 - lo * 1.8
        w = mpatches.Wedge(
            (cx, cy), r_out, ang_lo, ang_hi,
            width=r_out - r_in,
            facecolor=colour, edgecolor=BG, linewidth=4, alpha=0.88,
        )
        ax.add_patch(w)

    # Dark inner fill (clean look)
    ax.add_patch(plt.Circle((cx, cy), r_in, color=BG, zorder=3))

    # Needle
    needle_ang_deg = 180.0 - value * 1.8
    needle_rad     = np.radians(needle_ang_deg)
    needle_len     = r_in - 0.15
    nx = cx + needle_len * np.cos(needle_rad)
    ny = cy + needle_len * np.sin(needle_rad)

    ax.annotate(
        "", xy=(nx, ny), xytext=(cx, cy),
        arrowprops=dict(
            arrowstyle="-|>", color=WHITE, lw=3.5, mutation_scale=28,
        ),
        zorder=4,
    )

    # Centre dot
    ax.add_patch(plt.Circle((cx, cy), 0.20, color=WHITE, zorder=5))

    # Tick labels
    for tick_val, label in [(0, "0"), (25, "25"), (50, "50"), (75, "75"), (100, "100")]:
        ang  = np.radians(180.0 - tick_val * 1.8)
        tx   = cx + (r_out + 0.25) * np.cos(ang)
        ty   = cy + (r_out + 0.25) * np.sin(ang)
        ax.text(tx, ty, label, color=GREY, fontsize=19,
                ha="center", va="center", zorder=4)


def _overview_chart(data: Dict) -> Path:
    """
    Generate a 1080×1920 Fear & Greed gauge + market stats card.

    Saves to /temp/chart_overview_YYYYMMDD.png and returns the path.
    """
    fg    = data["fear_greed"]
    mkt   = data["market"]
    date_str = datetime.now().strftime("%Y%m%d")
    out   = Path(config.TEMP_DIR) / f"chart_overview_{date_str}.png"

    fig, ax = _new_figure()

    # ── Title ─────────────────────────────────────────────────
    ax.text(5, 19.3, "Market Overview",
            color=WHITE, fontsize=68, fontweight="bold",
            ha="center", va="top")

    # ── Gauge ─────────────────────────────────────────────────
    cx, cy = 5.0, 14.2
    _draw_gauge(ax, cx=cx, cy=cy, r_out=3.4, r_in=2.2, value=fg["value"])

    # ── Fear & Greed value + label ────────────────────────────
    fg_col = _fg_color(fg["value"])
    ax.text(cx, cy - 0.5, str(fg["value"]),
            color=fg_col, fontsize=110, fontweight="bold",
            ha="center", va="center", zorder=6)
    ax.text(cx, cy - 2.2, fg["classification"].upper(),
            color=fg_col, fontsize=40, fontweight="bold",
            ha="center", va="center", zorder=6)
    ax.text(cx, cy - 3.0, "Fear & Greed Index",
            color=GREY, fontsize=26, ha="center", va="center")

    # Separator
    ax.axhline(9.8, color="#222222", linewidth=2, xmin=0.05, xmax=0.95)

    # ── Market stats cards ────────────────────────────────────
    stats = [
        ("Total Market Cap",  _fmt_large(mkt["total_market_cap_usd"])),
        ("24h Volume",        _fmt_large(mkt["total_volume_24h_usd"])),
        ("BTC Dominance",     f"{mkt['btc_dominance']:.1f}%"),
    ]

    card_x, card_w, card_h = 0.5, 9.0, 1.9
    y_tops = [9.2, 7.0, 4.8]

    for (label, value), y_top in zip(stats, y_tops):
        # Card background
        ax.add_patch(mpatches.FancyBboxPatch(
            (card_x, y_top - card_h), card_w, card_h,
            boxstyle="round,pad=0.12",
            facecolor=CARD_BG, edgecolor=CARD_BD, linewidth=2,
        ))
        ax.text(5, y_top - 0.42, label,
                color=GREY, fontsize=28, ha="center", va="center")
        ax.text(5, y_top - 1.20, value,
                color=WHITE, fontsize=44, fontweight="bold",
                ha="center", va="center")

    # ── Market cap change badge ───────────────────────────────
    chg24 = mkt["market_cap_change_24h_pct"]
    chg_col  = GREEN if chg24 >= 0 else RED
    chg_sign = "+" if chg24 >= 0 else ""
    ax.text(5, 3.4,
            f"Market Cap 24h: {chg_sign}{chg24:.1f}%",
            color=chg_col, fontsize=30, fontweight="bold",
            ha="center", va="center")

    # ── Footer ────────────────────────────────────────────────
    ax.axhline(2.0, color="#222222", linewidth=2, xmin=0.05, xmax=0.95)
    ax.text(5, 1.3,
            f"Source: CoinGecko / Alternative.me  •  {config.CHANNEL_NAME}",
            color=GREY, fontsize=22, ha="center", va="center")

    _save(fig, out)
    logger.info("Chart B saved: %s", out.name)
    return out


# ── Chart C — Indian Market (Indices + NSE Gainers) ──────────

SAFFRON  = "#FF9933"
IND_GREEN = "#138808"
NAVY_BG  = "#0A0F1E"
CARD_IND = "#111827"
CARD_BDI = "#1F2D48"


def _india_chart(data: Dict) -> Path:
    """
    Generate a 1080×1920 chart showing key Indian indices + top-5 NSE gainers.

    Saves to /temp/chart_india_YYYYMMDD.png and returns the path.
    """
    indices  = data["india_indices"]
    stocks   = data["india_stocks"][:5]
    date_str = datetime.now().strftime("%Y%m%d")
    out      = Path(config.TEMP_DIR) / f"chart_india_{date_str}.png"

    fig = plt.figure(figsize=(W_IN, H_IN), dpi=DPI)
    fig.patch.set_facecolor(NAVY_BG)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_facecolor(NAVY_BG)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 20)
    ax.axis("off")

    # ── Title ─────────────────────────────────────────────────
    ax.text(5, 19.3, "Indian Market Today",
            color=WHITE, fontsize=64, fontweight="bold",
            ha="center", va="top", fontfamily="sans-serif")
    ax.text(5, 18.2, "NSE / BSE  —  Live Snapshot",
            color=GREY, fontsize=34, ha="center", va="top")
    ax.axhline(17.6, color="#1A2540", linewidth=2, xmin=0.05, xmax=0.95)

    # ── Index cards 2 × 2 ─────────────────────────────────────
    positions = [
        (0.25, 16.5),  # Nifty 50   — top-left
        (5.15, 16.5),  # Sensex     — top-right
        (0.25, 13.1),  # Bank Nifty — bottom-left
        (5.15, 13.1),  # Nifty IT   — bottom-right
    ]
    card_w, card_h = 4.6, 2.9

    for idx, (ind, (cx, cy)) in enumerate(zip(indices[:4], positions)):
        chg     = ind["change_pct"]
        chg_col = GREEN if chg >= 0 else RED
        sign    = "+" if chg >= 0 else ""

        # Card background
        ax.add_patch(mpatches.FancyBboxPatch(
            (cx, cy - card_h), card_w, card_h,
            boxstyle="round,pad=0.12",
            facecolor=CARD_IND, edgecolor=CARD_BDI, linewidth=2,
        ))
        mid_x = cx + card_w / 2

        # Index name
        ax.text(mid_x, cy - 0.38, ind["name"],
                color=GREY, fontsize=26, fontweight="bold",
                ha="center", va="center")
        # Price value
        ax.text(mid_x, cy - 1.35, f"{ind['price']:,.0f}",
                color=WHITE, fontsize=40, fontweight="bold",
                ha="center", va="center")
        # % change badge
        ax.add_patch(mpatches.FancyBboxPatch(
            (mid_x - 1.1, cy - 2.45), 2.2, 0.75,
            boxstyle="round,pad=0.08",
            facecolor=chg_col + "22", edgecolor=chg_col + "88", linewidth=1.5,
        ))
        ax.text(mid_x, cy - 2.08, f"{sign}{chg:.2f}%",
                color=chg_col, fontsize=28, fontweight="bold",
                ha="center", va="center")

    # ── Section divider ───────────────────────────────────────
    ax.axhline(10.0, color="#1A2540", linewidth=2, xmin=0.05, xmax=0.95)
    ax.text(5, 9.6, "Top NSE Gainers",
            color=SAFFRON, fontsize=38, fontweight="bold",
            ha="center", va="center")
    ax.axhline(9.1, color="#1A2540", linewidth=1.5, xmin=0.05, xmax=0.95)

    # ── Bars ─────────────────────────────────────────────────
    if stocks:
        max_chg   = max(s["change_pct"] for s in stocks)
        max_chg   = max(max_chg, 1)
        x_label   = 0.45
        x_bar_s   = 2.5
        x_bar_e   = 9.4
        bar_h     = 0.95
        y_centers = [8.4, 7.1, 5.8, 4.5, 3.2]

        for i, (stock, yc) in enumerate(zip(stocks, y_centers)):
            sym   = stock["symbol"]
            chg   = stock["change_pct"]
            price = stock["price"]
            bw    = max(0.08, (chg / max_chg) * (x_bar_e - x_bar_s))

            # Track
            ax.add_patch(mpatches.FancyBboxPatch(
                (x_bar_s, yc - bar_h / 2), x_bar_e - x_bar_s, bar_h,
                boxstyle="round,pad=0.05",
                facecolor="#151E30", edgecolor="none", zorder=1,
            ))
            # Saffron bar
            ax.add_patch(mpatches.FancyBboxPatch(
                (x_bar_s, yc - bar_h / 2), bw, bar_h,
                boxstyle="round,pad=0.05",
                facecolor=SAFFRON, edgecolor="none", alpha=0.88, zorder=2,
            ))
            # Rank badge
            ax.add_patch(plt.Circle((x_label, yc + 0.22), 0.34,
                                    color="#1E1504", zorder=2))
            ax.text(x_label, yc + 0.22, f"#{i+1}",
                    color=SAFFRON, fontsize=22, fontweight="bold",
                    ha="center", va="center", zorder=3)
            # Symbol
            ax.text(x_bar_s - 0.15, yc + 0.18, sym,
                    color=WHITE, fontsize=34, fontweight="bold",
                    ha="right", va="center", zorder=3)
            # Price (INR)
            ax.text(x_bar_s - 0.15, yc - 0.28, f"₹{price:,.1f}",
                    color=GREY, fontsize=20, ha="right", va="center", zorder=3)
            # % change
            ax.text(x_bar_s + bw + 0.18, yc, f"+{chg:.1f}%",
                    color=SAFFRON, fontsize=28, fontweight="bold",
                    ha="left", va="center", zorder=3)

    # ── Footer ────────────────────────────────────────────────
    ax.axhline(2.0, color="#1A2540", linewidth=2, xmin=0.05, xmax=0.95)
    ax.text(5, 1.3, f"Source: NSE / Yahoo Finance  •  {config.CHANNEL_NAME}",
            color=GREY, fontsize=22, ha="center", va="center")

    fig.savefig(str(out), dpi=DPI, facecolor=NAVY_BG, pad_inches=0)
    plt.close(fig)
    _ensure_exact_size(out)
    logger.info("Chart C (India) saved: %s", out.name)
    return out


# ── Pipeline entry point ──────────────────────────────────────

def generate_all_charts(data: Dict) -> Dict[str, Path]:
    """
    Generate both chart images.

    Args:
        data: Combined market data dict from fetcher.get_market_data().

    Returns:
        {'gainers': Path, 'overview': Path}
    """
    temp_dir = Path(config.TEMP_DIR)
    temp_dir.mkdir(exist_ok=True)

    logger.info("Rendering Chart A (gainers)…")
    chart_a = _gainers_chart(data)

    logger.info("Rendering Chart B (overview)…")
    chart_b = _overview_chart(data)

    charts = {"gainers": chart_a, "overview": chart_b}

    if data.get("india_indices") or data.get("india_stocks"):
        logger.info("Rendering Chart C (India)…")
        charts["india"] = _india_chart(data)

    return charts
