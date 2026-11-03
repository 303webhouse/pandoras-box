"""
UW Forward-Logger — main entry point.

Daily cron (21:00 UTC Mon-Fri) pulls 5 UW data types for 10 watchlist tickers
and accumulates them in Parquet cache files for the backtest module's
forward-test lane (Phase 2 bifurcation).

Usage:
    # Normal production run
    python3 logger.py

    # Dry-run single ticker (fetch but don't write to real cache)
    python3 logger.py --dry-run --ticker SPY

Ref: docs/codex-briefs/brief-phase-0-5-uw-forward-logger.md §Phase B
"""

import argparse
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

# ── path setup so package imports work when run as script ─────────────────────
_WORKSPACE = Path(__file__).resolve().parents[2]
if str(_WORKSPACE) not in sys.path:
    sys.path.insert(0, str(_WORKSPACE))

import pandas as pd

from scripts.uw_forward_logger import alerts, cache, config
from scripts.uw_forward_logger.fetchers import (
    darkpool,
    flow_alerts,
    greek_exposure,
    net_prem_ticks,
    spot_exposures,
)
from scripts.uw_forward_logger.fetchers.greek_exposure import CarveOutCanaryTriggered

# ── logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
    stream=sys.stdout,
)
logger = logging.getLogger("uw_forward_logger")

# ── 2026 NYSE Holidays (simple static list) ───────────────────────────────────
# Avoids pandas-market-calendars dep. Extend annually.
_NYSE_HOLIDAYS_2026 = {
    date(2026, 1, 1),   # New Year's Day
    date(2026, 1, 19),  # MLK Day
    date(2026, 2, 16),  # Presidents Day
    date(2026, 4, 3),   # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 7, 3),   # Independence Day (observed)
    date(2026, 9, 7),   # Labor Day
    date(2026, 11, 26), # Thanksgiving
    date(2026, 11, 27), # Black Friday (early close — treat as holiday for data purposes)
    date(2026, 12, 25), # Christmas
}


def _market_was_open(run_date: date) -> bool:
    """Return True if NYSE was open on run_date (weekday and not holiday)."""
    if run_date.weekday() >= 5:  # Saturday=5, Sunday=6
        return False
    if run_date in _NYSE_HOLIDAYS_2026:
        return False
    return True


def _yesterday() -> str:
    """Return yesterday's date as YYYY-MM-DD."""
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


def run(
    tickers: list[str],
    api_key: str,
    dry_run: bool = False,
    first_run: bool = False,
) -> None:
    """
    Main loop — fetch and cache all 5 data types for each ticker.
    Emits alerts on consecutive empties, rate-limit failures, auth errors.
    """
    today = datetime.now(timezone.utc).date()

    if not _market_was_open(today):
        logger.info("Market closed today (%s) — skipping full run.", today)
        return

    yesterday = _yesterday()
    logger.info(
        "Starting UW forward-logger run — %s — %d tickers — dry_run=%s",
        today, len(tickers), dry_run,
    )

    t_start = time.time()
    empty_tracker: dict = {}  # (ticker, data_type) -> consecutive empty days
    call_count = 0
    errors: list[str] = []

    # ── Define fetch tasks ────────────────────────────────────────────────────
    # (data_type, fetcher_fn, extra_kwargs)
    # greek_exposure_daily uses "rolling" cache mode — same data_type key
    def _make_tasks(ticker: str):
        return [
            ("flow_alerts",         lambda: flow_alerts.fetch(ticker, api_key)),
            ("darkpool",            lambda: darkpool.fetch(ticker, api_key, date=yesterday)),
            ("net_prem_ticks",      lambda: net_prem_ticks.fetch(ticker, api_key)),
            ("spot_exposures",      lambda: spot_exposures.fetch(ticker, api_key)),
            ("greek_exposure_daily", lambda: _fetch_greek(ticker, api_key, empty_tracker, errors)),
        ]

    for ticker in tickers:
        logger.info("── %s ──────────────────────────", ticker)
        tasks = _make_tasks(ticker)

        for data_type, fetcher_fn in tasks:
            try:
                df: pd.DataFrame = fetcher_fn()
                call_count += 1

                row_count = len(df) if df is not None else 0
                is_empty = row_count == 0

                logger.info(
                    "  %s.%s: %d rows%s",
                    ticker, data_type, row_count,
                    " [EMPTY]" if is_empty else "",
                )

                alerts.check_consecutive_empty(ticker, data_type, is_empty, empty_tracker)

                if not is_empty:
                    cache.merge_and_write(data_type, ticker, df, dry_run=dry_run)

            except CarveOutCanaryTriggered as canary:
                alerts.alert_carve_out_canary(canary.ticker, canary.row_count)
                errors.append(f"{ticker}.{data_type}: carve-out canary fired ({canary.row_count} rows)")

            except RuntimeError as e:
                err_str = str(e)
                errors.append(f"{ticker}.{data_type}: {err_str}")
                if "429" in err_str or "Rate-limited" in err_str:
                    alerts.alert_rate_limit_failure(ticker, data_type, err_str)
                elif "401" in err_str or "403" in err_str:
                    alerts.alert_auth_error(ticker, f"/api/.../", err_str)
                else:
                    logger.error("  %s.%s FAILED: %s", ticker, data_type, e)

            # Throttle between calls
            call_count_since_burst_start = call_count % config.THROTTLE_MAX_BURST
            if call_count_since_burst_start == 0 and call_count > 0:
                logger.debug("Burst pause (%.1fs)...", config.THROTTLE_BURST_PAUSE_S)
                time.sleep(config.THROTTLE_BURST_PAUSE_S)
            else:
                time.sleep(config.THROTTLE_SLEEP_BETWEEN_CALLS_S)

    elapsed_s = time.time() - t_start
    elapsed_min = elapsed_s / 60

    logger.info(
        "Run complete — %.1f min, %d API calls, %d errors",
        elapsed_min, call_count, len(errors),
    )

    if errors:
        logger.warning("Errors this run:\n  " + "\n  ".join(errors))

    if elapsed_min > 30:
        alerts.alert_slow_run(elapsed_min)

    if first_run and not errors:
        alerts.alert_logger_online()


def _fetch_greek(
    ticker: str,
    api_key: str,
    empty_tracker: dict,
    errors: list,
) -> pd.DataFrame:
    """Thin wrapper that lets the canary exception propagate up."""
    return greek_exposure.fetch(ticker, api_key)


def main() -> None:
    parser = argparse.ArgumentParser(description="UW Forward-Logger")
    parser.add_argument("--dry-run", action="store_true", help="Fetch but don't write to cache")
    parser.add_argument("--ticker", help="Run for a single ticker only (testing)")
    parser.add_argument("--first-run", action="store_true", help="Send 'logger online' alert after success")
    args = parser.parse_args()

    try:
        api_key = config.get_api_key()
    except EnvironmentError as e:
        logger.error(str(e))
        sys.exit(1)

    try:
        all_tickers = config.load_watchlist()
    except (FileNotFoundError, ValueError) as e:
        logger.error("Watchlist load failed: %s", e)
        sys.exit(1)

    tickers = [args.ticker.upper()] if args.ticker else all_tickers
    if args.ticker and args.ticker.upper() not in all_tickers:
        logger.warning("Ticker %s not in watchlist — running anyway (testing mode)", args.ticker.upper())

    run(tickers, api_key, dry_run=args.dry_run, first_run=args.first_run)


if __name__ == "__main__":
    main()
