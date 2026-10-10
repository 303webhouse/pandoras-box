"""SPY market state per session, per the census declarations.

state_stack (C1, R-IV.838(e), STACK-FIRST):
    trend      = SMA 20/50/120/200 strictly aligned (either way) on >= 10 consecutive sessions
    range      = stack not aligned AND ADX(14) < 20
    transition = everything else
state_adx (R-IV.823(f)4, reported for continuity only):
    range = ADX(14) < 20; trend = ADX(14) >= 25 and SMA 20/50/200 aligned; transition = else
Wilder ADX on fully adjusted daily bars from yfinance.
"""
import sys

import pandas as pd
import yfinance as yf


def wilder_adx(df: pd.DataFrame, n: int = 14) -> pd.Series:
    h, l, c = df["High"], df["Low"], df["Close"]
    up, dn = h.diff(), -l.diff()
    plus_dm = up.where((up > dn) & (up > 0), 0.0)
    minus_dm = dn.where((dn > up) & (dn > 0), 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    a = 1.0 / n
    atr = tr.ewm(alpha=a, adjust=False).mean()
    pdi = 100 * plus_dm.ewm(alpha=a, adjust=False).mean() / atr
    mdi = 100 * minus_dm.ewm(alpha=a, adjust=False).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return dx.ewm(alpha=a, adjust=False).mean()


def spy_states(start="2024-06-01", end=None) -> pd.DataFrame:
    df = yf.download("SPY", start=start, end=end, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["High", "Low", "Close"])  # an unfinalised session arrives as NaN OHLC
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    out = pd.DataFrame(index=df.index)
    out["close"] = df["Close"]
    out["adx14"] = wilder_adx(df)
    for n in (20, 50, 120, 200):
        out[f"sma{n}"] = df["Close"].rolling(n).mean()
    # R-IV.823(f)4 ADX rule, three-average stack (continuity only)
    bull3 = (out.sma20 > out.sma50) & (out.sma50 > out.sma200)
    bear3 = (out.sma20 < out.sma50) & (out.sma50 < out.sma200)
    out["state_adx"] = "transition"
    out.loc[out.adx14 < 20, "state_adx"] = "range"
    out.loc[(out.adx14 >= 25) & (bull3 | bear3), "state_adx"] = "trend"
    # R-IV.838(e) STACK-FIRST, four-average stack held >= 10 sessions
    bull = (out.sma20 > out.sma50) & (out.sma50 > out.sma120) & (out.sma120 > out.sma200)
    bear = (out.sma20 < out.sma50) & (out.sma50 < out.sma120) & (out.sma120 < out.sma200)
    out["stack"] = bull.map({True: "bull"}).fillna(bear.map({True: "bear"})).fillna("mixed")
    run = out["stack"].ne(out["stack"].shift()).cumsum()
    out["stack_run"] = out.groupby(run).cumcount() + 1
    aligned = out["stack"].isin(["bull", "bear"])
    out["state_stack"] = "transition"
    out.loc[~aligned & (out.adx14 < 20), "state_stack"] = "range"
    out.loc[aligned & (out.stack_run >= 10), "state_stack"] = "trend"
    out.index = out.index.date
    return out


if __name__ == "__main__":
    s = spy_states(end=sys.argv[1] if len(sys.argv) > 1 else None)
    s.to_csv(sys.argv[2] if len(sys.argv) > 2 else "spy_states.csv")
    w = s.loc[s.index >= pd.Timestamp("2026-07-12").date()]
    print(pd.crosstab(w.state_stack, w.state_adx, margins=True).to_string())
    print("sessions", len(w), "last", w.index[-1])
