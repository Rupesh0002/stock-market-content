#!/usr/bin/env python3
# ─────────────────────────────────────────────────────────────
#  main.py  —  Pipeline orchestrator
#
#  Usage:
#    python main.py          → starts the daily scheduler
#    python main.py --now    → runs the pipeline immediately
# ─────────────────────────────────────────────────────────────
import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import config  # validate config exists and is importable first


# ── Logging setup ─────────────────────────────────────────────

def _setup_logging() -> None:
    """Configure root logger with timestamp + level prefix."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-7s  %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Suppress noisy third-party loggers
    for noisy in ("httpx", "httpcore", "urllib3", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ── Directories ───────────────────────────────────────────────

def _ensure_dirs() -> None:
    """Create output and temp directories if they don't exist."""
    Path(config.OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    Path(config.TEMP_DIR).mkdir(parents=True, exist_ok=True)


# ── Cleanup ───────────────────────────────────────────────────

def _cleanup_temp() -> None:
    """Delete all files inside the temp directory after a successful run."""
    temp_dir = Path(config.TEMP_DIR)
    if not temp_dir.exists():
        return
    removed = 0
    for item in temp_dir.iterdir():
        if item.is_file():
            item.unlink()
            removed += 1
    if removed:
        logging.getLogger(__name__).info("Cleaned up %d temp file(s).", removed)


# ── Pipeline ──────────────────────────────────────────────────

def run_pipeline() -> None:
    """
    Execute the full content-creation pipeline end-to-end.

    Steps:
        1. Fetch live market data (CoinGecko + Fear & Greed)
        2. Generate scripts with Gemini
        3. Create voiceovers with edge-tts
        4. Render chart images with matplotlib
        5. Assemble and export MP4 videos with moviepy

    On any failure the exception is logged and the function returns
    cleanly so the scheduler can continue to the next day's run.
    """
    logger = logging.getLogger(__name__)
    run_ts = datetime.now().strftime("%Y-%m-%d  %H:%M:%S")

    print()
    print("  ┌──────────────────────────────────────────────────────┐")
    print(f"  │  FINANCIAL CONTENT BOT  │  {run_ts}  │")
    print("  └──────────────────────────────────────────────────────┘")
    print()

    try:
        # ── Step 1: Data ──────────────────────────────────────
        print("  ▶ [1/5]  Fetching market data…")
        from fetcher import get_market_data
        data = get_market_data()
        print(
            f"        ✓  Top crypto: {data['gainers'][0]['symbol'].upper()}"
            f" +{data['gainers'][0]['price_change_percentage_24h']:.1f}%  |"
            f"  F&G: {data['fear_greed']['value']} — {data['fear_greed']['classification']}"
        )
        if data["india_indices"]:
            n = data["india_indices"][0]
            sign = "+" if n["change_pct"] >= 0 else ""
            print(f"        ✓  Nifty 50:   {n['price']:,.0f}  ({sign}{n['change_pct']:.2f}%)")
        if data["india_stocks"]:
            print(f"        ✓  Top NSE:    {data['india_stocks'][0]['symbol']}"
                  f" +{data['india_stocks'][0]['change_pct']:.1f}%")
        else:
            print("        ⚠  NSE data unavailable — India video skipped")

        # ── Step 2: Scripts ───────────────────────────────────
        print("  ▶ [2/5]  Generating scripts with Gemini…")
        from script_generator import generate_scripts
        scripts = generate_scripts(data)
        print(
            f"        ✓  Gainers script: {len(scripts['gainers'].split())} words  |"
            f"  Overview script: {len(scripts['overview'].split())} words"
        )

        # ── Step 3: Voiceovers ────────────────────────────────
        print("  ▶ [3/5]  Creating voiceovers (edge-tts)…")
        from tts import generate_all_voiceovers, get_audio_duration
        audio_paths = generate_all_voiceovers(scripts)
        for name, path in audio_paths.items():
            dur = get_audio_duration(path)
            print(f"        ✓  {name}: {dur:.1f}s  →  {path.name}")

        # ── Step 4: Charts ────────────────────────────────────
        print("  ▶ [4/5]  Building charts (matplotlib)…")
        from chart_maker import generate_all_charts
        chart_paths = generate_all_charts(data)
        for name, path in chart_paths.items():
            sz = path.stat().st_size / 1024
            print(f"        ✓  {name}: {path.name}  ({sz:.0f} KB)")

        # ── Step 5: Videos ────────────────────────────────────
        print("  ▶ [5/5]  Assembling videos (moviepy)…")
        from video_maker import assemble_all_videos
        video_paths = assemble_all_videos(chart_paths, audio_paths)

        # ── Done ──────────────────────────────────────────────
        print()
        print("  ┌──────────────────────────────────────────────────────┐")
        print("  │  ✅  Run complete — videos saved to /output/          │")
        print("  ├──────────────────────────────────────────────────────┤")
        for name, path in video_paths.items():
            size_mb = path.stat().st_size / 1_048_576
            print(f"  │  📁  {path.name:<36}  {size_mb:>5.1f} MB  │")
        print("  └──────────────────────────────────────────────────────┘")
        print()

        logger.info("Pipeline completed successfully.")
        _cleanup_temp()

        # ── Step 6: Telegram ──────────────────────────────────
        print("  ▶ [6/6]  Sending to Telegram…")
        from telegram_notify import send_message, send_video
        top   = data["gainers"][0]
        lines = [
            f"✅ <b>Daily Content Ready</b>",
            f"📅 {run_ts}",
            f"",
            f"₿ Top crypto: <b>{top['symbol'].upper()}</b>"
            f" +{top['price_change_percentage_24h']:.1f}%",
            f"😨 Fear &amp; Greed: <b>{data['fear_greed']['value']}"
            f" — {data['fear_greed']['classification']}</b>",
        ]
        if data["india_indices"]:
            n    = data["india_indices"][0]
            sign = "+" if n["change_pct"] >= 0 else ""
            lines.append(f"🇮🇳 Nifty 50: <b>{n['price']:,.0f}</b> ({sign}{n['change_pct']:.2f}%)")
        if data["india_stocks"]:
            s = data["india_stocks"][0]
            lines.append(f"📈 Top NSE: <b>{s['symbol']}</b> +{s['change_pct']:.1f}%")
        summary = "\n".join(lines)
        send_message(summary)
        for name, path in video_paths.items():
            send_video(path, caption=f"{config.CHANNEL_NAME} — {name}")
        print("        ✓  Telegram notifications sent.")

    except Exception as exc:  # noqa: BLE001
        logger.error("Pipeline FAILED: %s", exc, exc_info=True)
        print()
        print(f"  ❌  Pipeline failed: {exc}")
        print("      Check the log above for the full traceback.")
        print()
        from telegram_notify import send_message
        send_message(f"❌ <b>Pipeline failed</b> — {run_ts}\n\n<code>{exc}</code>")


# ── Entry point ───────────────────────────────────────────────

def main() -> None:
    """Parse CLI arguments and either run now or start the scheduler."""
    parser = argparse.ArgumentParser(
        description="Financial Content Bot — automated crypto video pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python main.py          # start daily scheduler\n"
            "  python main.py --now    # run pipeline immediately\n"
        ),
    )
    parser.add_argument(
        "--now",
        action="store_true",
        help="Run the pipeline immediately instead of waiting for the scheduled time.",
    )
    args = parser.parse_args()

    _setup_logging()
    _ensure_dirs()

    if not config.GEMINI_API_KEY:
        print()
        print("  ⚠️  WARNING: GEMINI_API_KEY is empty in config.py")
        print("     Get a free key at https://aistudio.google.com/")
        print("     The pipeline will fail at the script-generation step.")
        print()

    if args.now:
        run_pipeline()
    else:
        from scheduler import start_scheduler
        start_scheduler(run_pipeline)


if __name__ == "__main__":
    main()
