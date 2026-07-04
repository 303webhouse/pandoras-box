"""One-time backfill for the Stable Engine: 5y daily bars -> metrics -> theme scores.

Adapted from Stable Market Board by Ryan Scott (shared within The Stable, 2026).
yfinance-only (zero UW calls). Honors the coverage contract: reports fetched/missing
per table, marks the run degraded when coverage < 90%, and never fabricates gaps.

Run:
  PYTHONPATH=backend STABLE_DB_URL=postgresql://... python scripts/stable_backfill.py
Options:
  --years N        history length (default 5)
  --limit N        cap the universe (smoke test)
  --block-pct P    simulate a partial outage: randomly skip P% of tickers (degraded)
  --seed S         RNG seed for --block-pct (default 7)
  --skip-metrics   only refresh bars
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from stable_engine import bars_yf, config, db, metrics, scoring, universe  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stable_backfill")


def _counts() -> dict:
    def n(sql):
        v = scoring._scalar(sql)
        return int(v) if v is not None else 0
    return {
        "stable_universe": n("SELECT COUNT(*) FROM stable_universe"),
        "stable_daily_bars": n("SELECT COUNT(*) FROM stable_daily_bars"),
        "stable_daily_bars_tickers": n("SELECT COUNT(DISTINCT ticker) FROM stable_daily_bars"),
        "stable_metrics": n("SELECT COUNT(*) FROM stable_metrics"),
        "stable_metrics_tickers": n("SELECT COUNT(DISTINCT ticker) FROM stable_metrics"),
        "stable_theme_scores": n("SELECT COUNT(*) FROM stable_theme_scores"),
    }


def main() -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=config.HISTORY_YEARS)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--block-pct", type=float, default=0.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--skip-metrics", action="store_true")
    args = ap.parse_args()

    db.init_schema()

    log.info("Loading universe.csv into stable_universe ...")
    udf = universe.load_universe()
    tickers = sorted(set(udf["ticker"].tolist()) | set(config.BENCHMARK_SYMBOLS))
    if args.limit:
        # Keep the RS/regime benchmarks so a capped smoke run still scores themes.
        must_keep = {"QQQ", "RSP", "SPY"} & set(tickers)
        tickers = sorted(set(tickers[:args.limit]) | must_keep)

    block = set()
    if args.block_pct > 0:
        rng = random.Random(args.seed)
        k = max(1, int(len(tickers) * args.block_pct / 100.0))
        block = set(rng.sample(tickers, k))
        log.info("Degraded simulation: blocking %d/%d tickers (%.0f%%)", len(block), len(tickers), args.block_pct)

    log.info("Downloading %dy daily bars for %d tickers ...", args.years, len(tickers))
    coverage = bars_yf.download_and_store(tickers, years=args.years, block_tickers=block)

    metrics_summary = {"skipped": True}
    scores_stored = 0
    if not args.skip_metrics:
        log.info("Computing metrics ...")
        metrics_summary = metrics.compute_metrics()
        log.info("Computing + storing theme scores (anchor=close) ...")
        scores = scoring.compute_theme_scores()
        scores_stored = scoring.store_theme_scores(scores, anchor="close", degraded=coverage["degraded"])

    report = {
        "coverage": coverage,
        "metrics": metrics_summary,
        "theme_scores_stored": scores_stored,
        "table_counts": _counts(),
    }
    print("\n===== STABLE BACKFILL REPORT =====")
    print(json.dumps(report, indent=2, default=str))
    return report


if __name__ == "__main__":
    main()
