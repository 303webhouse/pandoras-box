"""Phase B mechanism confirmation — step the resolver on NXTS signal."""
import os
import sys

import psycopg2
import yfinance as yf
import pandas as pd
from datetime import timedelta, timezone

DSN = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
if not DSN:
    sys.exit("FATAL: DATABASE_PUBLIC_URL/DATABASE_URL not set")


def main():
    conn = psycopg2.connect(DSN, connect_timeout=15)
    cur = conn.cursor()

    # 1. Pull the NXTS signal row in full
    print("=" * 78)
    print("STEP 1: NXTS signal row")
    print("=" * 78)
    cur.execute("""
        SELECT signal_id, ticker, direction, timestamp,
               entry_price, stop_loss, target_1,
               outcome, outcome_pnl_pct, outcome_resolved_at, outcome_source
        FROM signals
        WHERE signal_id = 'HG_NXTS_20260423_192057_3-10';
    """)
    row = cur.fetchone()
    if not row:
        print("NOT FOUND")
        return
    sid, tkr, dirn, ts, entry, stop, t1, outcome, pnl, res_at, src = row
    print(f"  signal_id    = {sid}")
    print(f"  ticker       = {tkr}")
    print(f"  direction    = {dirn}")
    print(f"  signal_ts    = {ts}")
    print(f"  entry        = {entry}")
    print(f"  stop_loss    = {stop}")
    print(f"  target_1     = {t1}")
    print(f"  outcome      = {outcome}  (claimed pnl: {pnl}%)")
    print(f"  resolved_at  = {res_at}")
    print(f"  source       = {src}")
    print()

    # 2. signal_outcomes side
    print("=" * 78)
    print("STEP 2: signal_outcomes side")
    print("=" * 78)
    cur.execute("""
        SELECT outcome, outcome_at, outcome_price, max_favorable, max_adverse, days_to_outcome
        FROM signal_outcomes
        WHERE signal_id = 'HG_NXTS_20260423_192057_3-10';
    """)
    so_row = cur.fetchone()
    if so_row:
        so_outcome, so_at, so_price, mfe, mae, days = so_row
        print(f"  outcome      = {so_outcome}")
        print(f"  outcome_at   = {so_at}")
        print(f"  outcome_price= {so_price}")
        print(f"  MFE          = {mfe}  (max favorable post-signal, in price units)")
        print(f"  MAE          = {mae}  (max adverse post-signal, in price units)")
        print(f"  days_to      = {days}")
    print()

    # 3. Re-execute resolver's yfinance call exactly
    print("=" * 78)
    print("STEP 3: Re-fetch yfinance bars exactly as resolver does")
    print("=" * 78)
    if ts.tzinfo is None:
        signal_ts = ts.replace(tzinfo=timezone.utc)
    else:
        signal_ts = ts
    fetch_start = signal_ts - timedelta(minutes=15)
    print(f"  resolver call: yf.download('{tkr}', start={fetch_start}, interval='15m')")
    bars = yf.download(
        tkr,
        start=fetch_start,
        interval="15m",
        progress=False,
        auto_adjust=False,
        prepost=False,
    )
    if isinstance(bars.columns, pd.MultiIndex):
        bars.columns = bars.columns.get_level_values(0)
    print(f"  returned {len(bars)} bars")
    print()
    if bars.empty:
        print("  EMPTY — yfinance no longer has this data (15m horizon ~60 days). Falling back to daily.")
        # Try daily
        signal_age = (pd.Timestamp.now(tz='UTC') - signal_ts).days
        if signal_age > 55:
            print(f"  Signal is {signal_age} days old, resolver would fall back to '1d' interval")
            bars = yf.download(
                tkr,
                start=fetch_start,
                interval="1d",
                progress=False,
                auto_adjust=False,
                prepost=False,
            )
            if isinstance(bars.columns, pd.MultiIndex):
                bars.columns = bars.columns.get_level_values(0)
            print(f"  daily bars returned: {len(bars)}")
            print()

    # 4. Step through bar walk exactly as resolver would
    print("=" * 78)
    print("STEP 4: Walk bars and find which one matches as 'target hit'")
    print("=" * 78)
    print(f"  direction={dirn}, entry={entry}, target={t1}, stop={stop}")
    print()
    print(f"  {'idx':<3} {'bar_ts':<26} {'high':>10} {'low':>10} {'pre_signal?':<12} {'target_hit':<11} {'stop_hit':<9} {'note'}")
    print(f"  {'-'*3:<3} {'-'*24:<26} {'-'*10:>10} {'-'*10:>10} {'-'*11:<12} {'-'*10:<11} {'-'*8:<9}")
    matched_idx = None
    matched_bar_ts = None
    matched_outcome = None
    target_f = float(t1)
    stop_f = float(stop)
    entry_f = float(entry)
    for idx, (bar_ts, bar) in enumerate(bars.iterrows()):
        try:
            high = float(bar["High"])
            low = float(bar["Low"])
        except Exception:
            continue
        # Normalize bar_ts to UTC for comparison
        if bar_ts.tzinfo is None:
            bar_ts_utc = bar_ts.tz_localize('UTC') if hasattr(bar_ts, 'tz_localize') else bar_ts
        else:
            bar_ts_utc = bar_ts.tz_convert('UTC') if hasattr(bar_ts, 'tz_convert') else bar_ts
        try:
            pre_signal = bar_ts_utc < signal_ts
        except Exception:
            pre_signal = "?"
        pre_marker = "PRE-SIGNAL" if pre_signal is True else ("post" if pre_signal is False else "?")

        if dirn == "LONG":
            target_hit = high >= target_f
            stop_hit = low <= stop_f
        else:
            target_hit = low <= target_f
            stop_hit = high >= stop_f

        note = ""
        if matched_idx is None:
            if target_hit and stop_hit:
                matched_idx = idx
                matched_bar_ts = bar_ts
                matched_outcome = "LOSS (both, conservative)"
                note = "FIRST MATCH — both"
            elif target_hit:
                matched_idx = idx
                matched_bar_ts = bar_ts
                matched_outcome = "WIN"
                note = "FIRST MATCH — target"
            elif stop_hit:
                matched_idx = idx
                matched_bar_ts = bar_ts
                matched_outcome = "LOSS"
                note = "FIRST MATCH — stop"
        print(f"  {idx:<3} {str(bar_ts_utc):<26} {high:>10.4f} {low:>10.4f} {pre_marker:<12} {str(target_hit):<11} {str(stop_hit):<9} {note}")
        if matched_idx is not None and idx >= matched_idx + 3:
            print("  ... (resolver returns at first match; stopping early for readability)")
            break

    print()
    print("=" * 78)
    print("STEP 5: Verdict")
    print("=" * 78)
    if matched_idx is not None and matched_bar_ts is not None:
        if hasattr(matched_bar_ts, 'tz_localize') and matched_bar_ts.tzinfo is None:
            matched_utc = matched_bar_ts.tz_localize('UTC')
        elif hasattr(matched_bar_ts, 'tz_convert'):
            matched_utc = matched_bar_ts.tz_convert('UTC')
        else:
            matched_utc = matched_bar_ts
        try:
            is_pre = matched_utc < signal_ts
        except Exception:
            is_pre = "?"
        print(f"  resolver matched bar #{matched_idx} at {matched_utc}  ({matched_outcome})")
        print(f"  signal_ts                   = {signal_ts}")
        print(f"  matched bar predates signal? {is_pre}")
        if is_pre is True:
            print()
            print("  *** CONFIRMED: pre-signal bar registered as outcome match ***")
            print("  *** This is the mechanism: bar-window includes bars before signal_ts ***")
        elif is_pre is False:
            print()
            print("  Match was on a post-signal bar. Mechanism is NOT pre-signal bar window.")
            print("  Need to investigate other hypotheses (timezone, daily-bar same-day overlap, etc.)")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
