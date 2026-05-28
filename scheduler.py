# ─────────────────────────────────────────────────────────────
#  scheduler.py  —  Daily pipeline scheduler
# ─────────────────────────────────────────────────────────────
import logging
import time
from datetime import datetime
from typing import Callable

import schedule

import config

logger = logging.getLogger(__name__)


def _print_next_run() -> None:
    """Log the time remaining until the next scheduled run."""
    next_run = schedule.next_run()
    if next_run is None:
        return
    delta     = next_run - datetime.now()
    total_sec = max(0, int(delta.total_seconds()))
    hours, rem = divmod(total_sec, 3600)
    minutes    = rem // 60
    logger.info(
        "Next run in %dh %02dm  →  %s",
        hours, minutes, next_run.strftime("%Y-%m-%d %H:%M"),
    )


def start_scheduler(pipeline_func: Callable) -> None:
    """
    Schedule *pipeline_func* to run daily at config.DAILY_RUN_TIME
    and block in an event loop, printing a countdown every hour.

    Args:
        pipeline_func: The zero-argument callable that runs the pipeline.
    """
    schedule.every().day.at(config.DAILY_RUN_TIME).do(pipeline_func)

    print()
    print("  ╔══════════════════════════════════════╗")
    print(f"  ║  Scheduler running                   ║")
    print(f"  ║  Daily run at  {config.DAILY_RUN_TIME}                  ║")
    print("  ║  Ctrl+C to stop                      ║")
    print("  ╚══════════════════════════════════════╝")
    print()

    _print_next_run()

    last_hourly = time.monotonic()

    try:
        while True:
            schedule.run_pending()

            # Print countdown once per hour
            if time.monotonic() - last_hourly >= 3600:
                _print_next_run()
                last_hourly = time.monotonic()

            time.sleep(60)

    except KeyboardInterrupt:
        print("\n  Scheduler stopped by user.")
        logger.info("Scheduler stopped.")
