"""
Gate 2 sample run — A3 FWD_RETURN resolver.

Scoped to two signals (CRCL LONG + PLD SHORT, 2026-05-29) to produce at least
one LONG and one SHORT for sign verification. Writes to signal_forward_returns
and sets the secondary label on signals — both are new isolated tables that do
not affect scoring, Insights, or any live feature.

A3_SHADOW_MODE is forced to False for this run so writes land.
Verify: pre/post outcome_source distribution unchanged (ACTUAL_TRADE 2, BAR_WALK 1852).

Run from C:\trading-hub:
    python scripts\a3_gate2_sample.py
"""

from __future__ import annotations

import asyncio
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.abspath(os.path.join(HERE, "..", "backend"))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# Force shadow OFF for the Gate 2 write
os.environ["A3_SHADOW_MODE"] = "false"

# Gate 2 sample — one LONG, one SHORT, both from 2026-05-29 with T+1/T+5 bars available
GATE2_SIGNAL_IDS = [
    "FP_CRCL_20260529_200008_109c7a",   # CRCL LONG
    "STR_PLD_20260529_185656",           # PLD SHORT
]


async def _get_pool():
    """Build an asyncpg pool from .mcp.json (URL not printed)."""
    import json as _json, asyncpg as _asyncpg
    cfg = _json.load(open(os.path.join(HERE, "..", ".mcp.json")))
    args = cfg["mcpServers"]["postgres"]["args"]
    url = next((a for a in reversed(args) if a.startswith("postgres")), None)
    if not url:
        raise RuntimeError("postgres URL not found in .mcp.json")
    return await _asyncpg.create_pool(url, min_size=1, max_size=3)


async def main() -> None:
    # Import resolver logic inline so we can override the bar-fetch with yfinance
    # (UW_API_KEY not available locally; yfinance is the acceptable Gate 2 fallback
    #  for sign/number verification — resolver code on Railway uses UW primary)
    from jobs.a3_fwd_return_resolver import (
        _nth_trading_day, _direction_adjusted_return, HORIZONS, A3_SHADOW_MODE,
        _LONG_DIRS, _SHORT_DIRS,
    )

    print(f"A3_SHADOW_MODE = {A3_SHADOW_MODE}")
    print(f"Sample signals: {GATE2_SIGNAL_IDS}")
    print()

    pool = await _get_pool()

    # Pre-snapshot: outcome_source distribution
    async with pool.acquire() as conn:
        pre_dist = await conn.fetch(
            "SELECT outcome_source, COUNT(*) AS n FROM signals "
            "WHERE outcome_source IS NOT NULL GROUP BY outcome_source ORDER BY n DESC"
        )
    print("--- pre-run outcome_source distribution ---")
    for r in pre_dist:
        print(f"  {r['outcome_source']}: {r['n']}")
    print()

    # Fetch signal data directly
    async with pool.acquire() as conn:
        signals = await conn.fetch(
            "SELECT signal_id, ticker, direction, timestamp, entry_price, outcome_source "
            "FROM signals WHERE signal_id = ANY($1::text[])",
            GATE2_SIGNAL_IDS,
        )
    if not signals:
        print("ERROR: no signals found for sample IDs")
        return

    # Fetch bars via yfinance (UW_API_KEY not available locally;
    # yfinance is Gate 2 fallback for sign verification)
    import yfinance as yf
    from datetime import date, timedelta

    print("Fetching bars via yfinance (Gate 2 local fallback)...")
    results = []
    for sig in signals:
        sig_id    = sig["signal_id"]
        ticker    = (sig["ticker"] or "").upper()
        direction = (sig["direction"] or "").upper()
        entry     = float(sig["entry_price"])
        sig_date  = sig["timestamp"].date()

        tk = yf.Ticker(ticker)
        hist = tk.history(start=(sig_date - timedelta(days=2)).isoformat(),
                          end=(date.today()).isoformat(), interval="1d")
        if hist is None or hist.empty:
            print(f"  {sig_id}: no yfinance bars")
            continue

        close_index = {}
        for ts, row in hist.iterrows():
            d = ts.date() if hasattr(ts, "date") else ts
            close_index[d] = float(row["Close"])

        for horizon in HORIZONS:
            target_date = _nth_trading_day(sig_date, horizon)
            if target_date > date.today():
                print(f"  {sig_id} T+{horizon}: not yet ({target_date})")
                continue
            horizon_close = close_index.get(target_date)
            if horizon_close is None:
                for delta in [1, -1, 2, -2]:
                    horizon_close = close_index.get(target_date + timedelta(days=delta))
                    if horizon_close is not None:
                        break
            if horizon_close is None:
                print(f"  {sig_id} T+{horizon}: bar missing for {target_date}")
                continue

            ret_pct = _direction_adjusted_return(entry, horizon_close, direction)
            results.append({
                "signal_id": sig_id, "ticker": ticker, "direction": direction,
                "horizon": horizon, "entry": entry,
                "horizon_date": target_date, "horizon_close": horizon_close,
                "ret_pct": ret_pct,
            })
            print(
                f"  {sig_id} [{ticker} {direction}] T+{horizon}: "
                f"entry={entry} close={horizon_close:.4f} "
                f"ret={ret_pct:+.6f}%"
            )

    if not results:
        print("No results computed — cannot write")
        return

    print(f"\nWriting {len(results)} rows to signal_forward_returns (shadow={A3_SHADOW_MODE})...")
    for r in results:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO signal_forward_returns
                    (signal_id, horizon_days, reference_price,
                     horizon_close_price, fwd_return_pct, computed_at)
                VALUES ($1, $2, $3, $4, $5, NOW())
                ON CONFLICT (signal_id, horizon_days) DO UPDATE
                    SET horizon_close_price = EXCLUDED.horizon_close_price,
                        fwd_return_pct      = EXCLUDED.fwd_return_pct,
                        computed_at         = NOW()
                """,
                r["signal_id"], r["horizon"], r["entry"],
                r["horizon_close"], r["ret_pct"],
            )
            # IS-NULL guard: set secondary label
            await conn.execute(
                """
                UPDATE signals SET outcome_source = 'FWD_RETURN'
                WHERE signal_id = $1 AND outcome_source IS NULL
                """,
                r["signal_id"],
            )
    print("Writes complete.")

    # Post-snapshot
    async with pool.acquire() as conn:
        post_dist = await conn.fetch(
            "SELECT outcome_source, COUNT(*) AS n FROM signals "
            "WHERE outcome_source IS NOT NULL GROUP BY outcome_source ORDER BY n DESC"
        )
    print("\n--- post-run outcome_source distribution ---")
    for r in post_dist:
        print(f"  {r['outcome_source']}: {r['n']}")

    pre_map  = {r["outcome_source"]: r["n"] for r in pre_dist}
    post_map = {r["outcome_source"]: r["n"] for r in post_dist}
    at_ok = pre_map.get("ACTUAL_TRADE", 0) == post_map.get("ACTUAL_TRADE", 0)
    bw_ok = pre_map.get("BAR_WALK", 0)     == post_map.get("BAR_WALK", 0)
    print(f"\nACTUAL_TRADE unchanged: {at_ok} ({pre_map.get('ACTUAL_TRADE', 0)})")
    print(f"BAR_WALK unchanged:     {bw_ok} ({pre_map.get('BAR_WALK', 0)})")

    # Show final rows
    async with pool.acquire() as conn:
        written = await conn.fetch(
            """
            SELECT sfr.signal_id, s.ticker, s.direction, s.outcome_source,
                   sfr.horizon_days, sfr.reference_price,
                   sfr.horizon_close_price, sfr.fwd_return_pct
            FROM signal_forward_returns sfr
            JOIN signals s ON s.signal_id = sfr.signal_id
            WHERE sfr.signal_id = ANY($1::text[])
            ORDER BY sfr.signal_id, sfr.horizon_days
            """,
            GATE2_SIGNAL_IDS,
        )
    print("\n--- Gate 2 signal_forward_returns rows ---")
    for r in written:
        pct = float(r["fwd_return_pct"]) if r["fwd_return_pct"] else None
        sign = ("POSITIVE (correct call)" if pct and pct > 0
                else "NEGATIVE (wrong-way)" if pct and pct < 0
                else "n/a")
        print(
            f"  {r['signal_id']} [{r['ticker']} {r['direction']}] "
            f"T+{r['horizon_days']}: entry={r['reference_price']} "
            f"close={r['horizon_close_price']} ret={r['fwd_return_pct']}%  {sign} "
            f"[outcome_source={r['outcome_source']}]"
        )

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())
