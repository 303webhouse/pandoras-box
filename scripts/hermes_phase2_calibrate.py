"""Hermes phase 2 calibration — R-IV.820(h)2. READ-ONLY, no writes, no pushes.

Replays every session since 2026-09-15 on 5-minute bars and reports, per symbol, how many
SESSIONS would have fired. The ruling's bar: no symbol may fire on more than ONE SESSION IN
FIVE. A symbol over that has its threshold raised in 0.25% steps until it is not.

POSITIVE CONTROL: QQQ must fire on 2026-10-08 — the session the principal missed, which closed
−1.65% while its largest 30-minute velocity breach was −1.01%. If calibration and the control
conflict, this reports BOTH and settles nothing.

WHY 5-MINUTE BARS AND NOT DAILY CLOSES. The alarm fires INTRADAY, so a daily close understates
it: a session that touched −1.4% and closed −0.6% would fire in life and not in a close-only
replay. Walking the bars is the only replay that answers the question actually asked. yfinance
serves 5-minute history for about 60 days, which covers 09-15 onward.

THE PRIOR CLOSE IS THE PREVIOUS SESSION'S LAST BAR, not the current session's first open. A gap
is displacement — on a gap-down morning the move from yesterday's close is exactly what the
principal wants to be told about, and measuring from the open would hide it.
"""
import os
import sys
from collections import defaultdict
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "backend"))

from webhooks.hermes_session import (  # noqa: E402
    CALIBRATION_STEP_PCT, MAX_FIRE_RATE, REALERT_STEP_PCT, SESSION_THRESHOLD_PCT, displacement_pct,
    in_rth, should_alert,
)

SYMBOLS = ["SPY", "QQQ", "SMH"]
SINCE = date(2026, 9, 15)
CONTROL_DATE = date(2026, 10, 8)
CONTROL_SYMBOL = "QQQ"


def fetch(symbol):
    """5-minute bars, RTH only, grouped by ET session date. {date: [(ts, close), ...]}"""
    import yfinance as yf

    df = yf.Ticker(symbol).history(period="60d", interval="5m", auto_adjust=False)
    if df is None or df.empty:
        return {}
    sessions = defaultdict(list)
    for ts, row in df.iterrows():
        when = ts.to_pydatetime()
        if when.tzinfo is None:
            continue
        if not in_rth(when):
            continue
        c = row.get("Close")
        if c is None or c != c:          # NaN
            continue
        sessions[when.astimezone(__import__("zoneinfo").ZoneInfo("America/New_York")).date()
                 ].append((when, float(c)))
    for d in sessions:
        sessions[d].sort(key=lambda x: x[0])
    return dict(sessions)


def replay(symbol, sessions, threshold):
    """Which sessions would fire, and how many alerts each would have sent."""
    days = sorted(d for d in sessions if d >= SINCE)
    overrides = {symbol: threshold}
    fired, detail = [], {}
    for i, d in enumerate(days):
        bars = sessions[d]
        if not bars:
            continue
        # The prior session's LAST bar close. Skipped when there is no prior session in range:
        # inventing one would manufacture a displacement.
        prev = None
        for cand in reversed([x for x in sorted(sessions) if x < d]):
            if sessions[cand]:
                prev = sessions[cand][-1][1]
                break
        if prev is None:
            detail[d] = ("skipped", "no prior session close in range", None)
            continue
        last_alerted, alerts, peak = None, 0, 0.0
        for when, close in bars:
            mv = displacement_pct(prev, close)
            if mv is None:
                continue
            if abs(mv) > abs(peak):
                peak = mv
            ok, _ = should_alert(symbol, mv, last_alerted, overrides=overrides)
            if ok:
                alerts += 1
                last_alerted = mv
        if alerts:
            fired.append(d)
        detail[d] = ("fired" if alerts else "quiet", "%d alert(s)" % alerts, peak)
    return days, fired, detail


def main():
    print("Hermes phase 2 calibration — sessions from %s, 5-minute bars, READ-ONLY" % SINCE)
    print("Bar: no symbol fires on more than 1 session in 5 (<= %.0f%%). Step %.2f%%.\n"
          % (MAX_FIRE_RATE * 100, CALIBRATION_STEP_PCT))

    final, control = {}, None
    for sym in SYMBOLS:
        sessions = fetch(sym)
        if not sessions:
            print("%-5s NO BARS RETURNED — cannot calibrate, reported rather than assumed\n" % sym)
            final[sym] = None
            continue
        thr = SESSION_THRESHOLD_PCT[sym]
        while True:
            days, fired, detail = replay(sym, sessions, thr)
            evaluated = [d for d in days if detail.get(d, ("skipped",))[0] != "skipped"]
            rate = (len(fired) / len(evaluated)) if evaluated else 0.0
            print("%-5s threshold %.2f%%  sessions %2d  fired %2d  rate %5.1f%%  %s"
                  % (sym, thr, len(evaluated), len(fired), rate * 100,
                     "OK" if rate <= MAX_FIRE_RATE else "TOO NOISY -> raising"))
            if rate <= MAX_FIRE_RATE or not evaluated:
                break
            thr = round(thr + CALIBRATION_STEP_PCT, 2)
        final[sym] = thr
        if sym == CONTROL_SYMBOL:
            st = detail.get(CONTROL_DATE)
            control = (st, CONTROL_DATE in fired)
        print("      fired on: %s" % (", ".join(str(d) for d in fired) or "no session"))
        worst = sorted((v[2] or 0, d) for d, v in detail.items() if v[2] is not None)
        if worst:
            print("      largest displacement seen: %+.2f%% on %s" % (worst[0][0], worst[0][1]))
        print()

    print("=== FINAL THRESHOLDS (provisional until SPINE ratifies) ===")
    for sym in SYMBOLS:
        start = SESSION_THRESHOLD_PCT[sym]
        got = final.get(sym)
        print("  %-5s %s" % (sym, "unmeasurable" if got is None else
                             ("%.2f%%%s" % (got, "" if got == start
                                            else "  (raised from %.2f%%)" % start))))
    print()
    print("=== POSITIVE CONTROL: %s must fire on %s ===" % (CONTROL_SYMBOL, CONTROL_DATE))
    if control is None:
        print("  NOT ESTABLISHED — no data for the control symbol")
    else:
        st, did = control
        print("  session state: %s" % (st,))
        print("  RESULT: %s" % ("PASS — it fires" if did else "FAIL — it does NOT fire"))
        if not did:
            print("  CALIBRATION AND CONTROL CONFLICT. Reporting both, settling neither.")


if __name__ == "__main__":
    main()
