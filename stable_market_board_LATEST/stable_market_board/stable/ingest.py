"""Ingest daily bars from Polygon into DuckDB.

- Idempotent: re-running is safe. Already-stored (ticker, date) rows are not duplicated.
- Incremental: if a ticker has data already, only pulls bars after the last stored date.
- Concurrent: uses a thread pool. Stocks Starter has unlimited API calls so we can hit 10
  workers without hitting rate limits.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import List, Optional

import pandas as pd
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from . import config, db, polygon_client, universe

console = Console()


def _start_date_for(ticker: str, latest: dict, full_history_years: int) -> date:
    """Determine where to start pulling for a ticker."""
    if ticker in latest:
        # Pull from the day after the last stored bar
        return latest[ticker] + timedelta(days=1)
    return date.today() - timedelta(days=365 * full_history_years)


def _fetch_one(
    ticker: str,
    start: date,
    end: date,
) -> tuple[str, Optional[pd.DataFrame], Optional[str]]:
    """Fetch bars for one ticker. Returns (ticker, dataframe_or_None, error_or_None)."""
    try:
        df = polygon_client.fetch_daily_bars(ticker, start, end)
        return ticker, df, None
    except Exception as e:
        return ticker, None, str(e)


def ingest(
    tickers: Optional[List[str]] = None,
    workers: int = 10,
    end_date: Optional[date] = None,
) -> dict:
    """Ingest daily bars for the given tickers (or the full universe).

    Returns a summary dict with counts and any errors.
    """
    db.init_schema()

    if tickers is None:
        uni = universe.get_universe()
        if uni.empty:
            console.print("[yellow]Universe table is empty. Loading from CSV first...[/yellow]")
            uni = universe.load_universe()
        tickers = uni["ticker"].tolist()

    end_date = end_date or date.today()
    latest = db.latest_date_per_ticker()

    console.print(
        f"[cyan]Ingesting {len(tickers)} tickers up to {end_date.isoformat()} "
        f"({len(latest)} have existing data)[/cyan]"
    )

    all_frames: list[pd.DataFrame] = []
    errors: dict[str, str] = {}
    skipped: list[str] = []

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching", total=len(tickers))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {}
            for ticker in tickers:
                start = _start_date_for(ticker, latest, config.HISTORY_YEARS)
                if start > end_date:
                    skipped.append(ticker)
                    progress.update(task, advance=1)
                    continue
                futures[pool.submit(_fetch_one, ticker, start, end_date)] = ticker

            for fut in as_completed(futures):
                ticker, df, err = fut.result()
                if err:
                    errors[ticker] = err
                elif df is not None and not df.empty:
                    all_frames.append(df)
                progress.update(task, advance=1)

    rows_inserted = 0
    if all_frames:
        combined = pd.concat(all_frames, ignore_index=True)
        with db.connect() as conn:
            conn.register("incoming", combined)
            # Insert only rows that don't already exist (composite PK on ticker, date)
            result = conn.execute("""
                INSERT INTO prices
                SELECT i.* FROM incoming i
                LEFT JOIN prices p ON p.ticker = i.ticker AND p.date = i.date
                WHERE p.ticker IS NULL
            """)
            rows_inserted = combined.shape[0]  # approximate; some may have been deduped

    summary = {
        "tickers_attempted": len(tickers),
        "tickers_with_new_data": len(all_frames),
        "tickers_skipped_already_current": len(skipped),
        "tickers_with_errors": len(errors),
        "rows_inserted_approx": rows_inserted,
        "errors": errors,
    }

    console.print(f"[green]Done.[/green] {summary['tickers_with_new_data']} tickers updated, "
                  f"{summary['tickers_skipped_already_current']} already current, "
                  f"{summary['tickers_with_errors']} errors.")

    if errors:
        console.print("[yellow]Errors:[/yellow]")
        for t, e in list(errors.items())[:10]:
            console.print(f"  {t}: {e}")
        if len(errors) > 10:
            console.print(f"  ... and {len(errors) - 10} more")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Ingest Polygon daily bars into DuckDB")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test mode: pull only SPY, QQQ, NVDA to verify the pipeline.",
    )
    parser.add_argument(
        "--tickers",
        nargs="*",
        help="Specific tickers to ingest (default: full universe).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=10,
        help="Concurrent fetch workers (default: 10).",
    )
    args = parser.parse_args()

    if args.test:
        console.print("[cyan]Test mode: ingesting SPY, QQQ, NVDA only[/cyan]")
        tickers = ["SPY", "QQQ", "NVDA"]
    elif args.tickers:
        tickers = [t.upper() for t in args.tickers]
    else:
        tickers = None

    if tickers is None:
        # Make sure universe is loaded
        universe.load_universe()

    ingest(tickers=tickers, workers=args.workers)


if __name__ == "__main__":
    main()
