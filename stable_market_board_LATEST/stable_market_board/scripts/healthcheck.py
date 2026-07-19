"""Quick sanity check: verify the Polygon API key works and a small ingestion runs.

Run with: python -m scripts.healthcheck
"""

import sys
from datetime import date, timedelta

from rich.console import Console

from stable import polygon_client, db, ingest, metrics

console = Console()


def main():
    console.rule("[bold cyan]Stable Market Board - Healthcheck")

    # 1. API key works
    console.print("\n[1/4] Verifying Polygon API key...")
    if not polygon_client.health_check():
        console.print("[red]FAIL: API key check failed. Verify POLYGON_API_KEY in .env[/red]")
        sys.exit(1)
    console.print("[green]OK[/green] - SPY data pulled successfully")

    # 2. DB schema initializes
    console.print("\n[2/4] Initializing DuckDB schema...")
    db.init_schema()
    console.print("[green]OK[/green] - schema ready")

    # 3. Test ingestion on 3 tickers
    console.print("\n[3/4] Test ingestion (SPY, QQQ, NVDA)...")
    summary = ingest.ingest(tickers=["SPY", "QQQ", "NVDA"], workers=3)
    if summary["tickers_with_errors"] > 0:
        console.print(f"[red]FAIL: {summary['errors']}[/red]")
        sys.exit(1)
    console.print("[green]OK[/green]")

    # 4. Metrics compute
    console.print("\n[4/4] Computing metrics on test tickers...")
    # We need RSP too for relative strength to work
    ingest.ingest(tickers=["RSP"], workers=1)
    metrics.compute_metrics(tickers=["SPY", "QQQ", "NVDA", "RSP"])

    # Show the latest NVDA row as proof of life
    with db.connect(read_only=True) as conn:
        row = conn.execute("""
            SELECT date, ret_1d, ret_5d, ret_20d, dist_ma50_pct, atr_ext_50ma,
                   above_ma50, new_high_20d, rs_qqq_20d
            FROM metrics WHERE ticker = 'NVDA' ORDER BY date DESC LIMIT 1
        """).fetchone()

    if row:
        console.print(f"\n[green]Latest NVDA metrics:[/green]")
        console.print(f"  date           {row[0]}")
        console.print(f"  ret_1d         {row[1]:+.4f}" if row[1] is not None else "  ret_1d         n/a")
        console.print(f"  ret_5d         {row[2]:+.4f}" if row[2] is not None else "  ret_5d         n/a")
        console.print(f"  ret_20d        {row[3]:+.4f}" if row[3] is not None else "  ret_20d        n/a")
        console.print(f"  dist_ma50_pct  {row[4]:+.4f}" if row[4] is not None else "  dist_ma50_pct  n/a")
        console.print(f"  atr_ext_50ma   {row[5]:+.4f}" if row[5] is not None else "  atr_ext_50ma   n/a")
        console.print(f"  above_ma50     {row[6]}")
        console.print(f"  new_high_20d   {row[7]}")
        console.print(f"  rs_qqq_20d     {row[8]:+.4f}" if row[8] is not None else "  rs_qqq_20d     n/a")

    console.rule("[bold green]Healthcheck passed. Ready for full ingestion.")


if __name__ == "__main__":
    main()
