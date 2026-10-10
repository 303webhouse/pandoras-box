"""Registered SHADOW forward tests (R-IV.855(d)).

Two strategies emit here, graded under L0 SUPPRESS_ALWAYS, never surfaced:

  NEMESIS long  (`WRR_LONG` / `nemesis_spec`) -- the March spec read literally
                (docs/approved-strategies/wrr-buy-model.md, approved 2026-03-16), one variant.
                Registration: docs/strategies/registrations/nemesis-long-v1.md
  PHOENIX washout (`PHOENIX_WASHOUT` / `phoenix_washout`) -- the coded WRR's washout without
                its candle and volume tests; a NEW variant of PHOENIX, not PHOENIX as coded.
                Registration: docs/strategies/registrations/phoenix-washout-v1.md

ONE SOURCE OF RULES. The pure functions below are what this job emits from AND what the frozen
forward grader (scripts/lab/forward_registered.py) replays. A registration hashes the commit
that holds them, so a change to either rule is a new version, never an edit.

WHEN. A daily bar from yfinance is final only late in the evening (2026-10-09's bar still read
NaN at 20:35 ET). So the job runs the NEXT MORNING at 07:00 ET, before the open, on the
previous session's completed bar: the signal is known before the first price a person could
trade it at, which is the next session's open. It also catches up on any recent session it has
not yet completed (a late deploy loses nothing).

BARS. yfinance daily, fully adjusted, through `stable_engine.bars_yf` (CIRCE's helper): the same
basis the replay computed its indicators on.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")

JOB_NAME = "lab_registered_shadow"
SOURCE = "lab_registered"
REGISTERED_FROM = date(2026, 10, 12)      # first forward session of both registrations
CATCH_UP_SESSIONS = 5
BAR_CALENDAR_DAYS = 420                   # 200-day SMA + warm-up
BATCH_SIZE = 100

NEMESIS_SIGNAL_TYPE, NEMESIS_STRATEGY = "WRR_LONG", "nemesis_spec"
NEMESIS_REGISTRATION = "nemesis-long-v1"
# THE LITERAL VARIANT. The spec says ROC(10) "deeply negative" with no number (wrr-buy-model.md
# :29). The only number the approving process wrote for this spec is brief 5B's scanner,
# `roc < -3.0` (docs/codex-briefs/brief-5b-nemesis-countertrend-lane.md:429), Titans 2026-03-17.
NEMESIS_ROC_BELOW = -0.03

PHOENIX_W_SIGNAL_TYPE, PHOENIX_W_STRATEGY = "PHOENIX_WASHOUT", "phoenix_washout"
PHOENIX_W_REGISTRATION = "phoenix-washout-v1"

# The census proxy universe (scanners/universe.py:154-161 fallback, first 200) minus SPY (the
# benchmark) and BK, MMC, SQ (no yfinance bars): 196 names, FROZEN here so a later edit to
# universe.py cannot move a registered test.
UNIVERSE = (
    "XLK", "XLY", "XLF", "XLV", "XLE", "XLI", "XLP", "XLC", "XLU", "XLRE", "XLB", "QQQ", "IWM",
    "DIA", "RSP", "UVXY", "TLT", "HYG", "LQD", "GLD", "SLV", "USO", "COPX", "EEM", "EFA", "FXI",
    "EWJ", "EWY", "EWG", "INDA", "EWU", "UUP", "FXE", "FXY", "FXB", "URA", "SMH", "XBI", "AAPL",
    "MSFT", "AMZN", "NVDA", "GOOGL", "META", "TSLA", "AVGO", "ORCL", "AMD", "CRM", "ADBE",
    "CSCO", "INTC", "QCOM", "INTU", "NOW", "PANW", "SNPS", "AMAT", "JPM", "BAC", "WFC", "GS",
    "MS", "C", "BLK", "SCHW", "AXP", "USB", "PNC", "TFC", "COF", "STT", "SPGI", "MCO", "ICE",
    "CME", "AON", "UNH", "JNJ", "LLY", "ABBV", "MRK", "PFE", "TMO", "ABT", "DHR", "BMY", "AMGN",
    "GILD", "ISRG", "REGN", "VRTX", "CI", "CVS", "ELV", "HUM", "ZTS", "HD", "MCD", "NKE", "SBUX",
    "TJX", "LOW", "BKNG", "MAR", "WMT", "PG", "KO", "PEP", "COST", "PM", "MO", "MDLZ", "CL",
    "GIS", "CAT", "BA", "UNP", "UPS", "RTX", "HON", "GE", "DE", "ITW", "WM", "EMR", "ETN", "FDX",
    "NSC", "CSX", "XOM", "CVX", "COP", "SLB", "EOG", "MPC", "PSX", "VLO", "OXY", "HAL", "LIN",
    "APD", "SHW", "ECL", "NEM", "FCX", "NEE", "SO", "DUK", "AEP", "SRE", "D", "EXC", "PLD",
    "AMT", "EQIX", "PSA", "WELL", "SPG", "O", "CBRE", "NFLX", "DIS", "CMCSA", "T", "VZ", "TMUS",
    "PLTR", "SOFI", "RIVN", "LCID", "F", "SNAP", "COIN", "HOOD", "RBLX", "U", "ZM", "DOCU",
    "CRWD", "NET", "DDOG", "SNOW", "MDB", "HUBS", "ZS", "OKTA", "PYPL", "SHOP", "ROKU", "PINS",
    "TWLO", "LYFT", "UBER", "DASH", "ABNB",
)


# ── the rules (pure; frame columns o, h, l, c, v; ascending; fully adjusted) ─────────────────
def wilder_rsi(c: pd.Series, n: int) -> pd.Series:
    d = c.diff()
    au = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    ad = (-d).clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + au / ad.replace(0, np.nan))


def wilder_atr(f: pd.DataFrame, n: int = 14) -> pd.Series:
    tr = pd.concat([f.h - f.l, (f.h - f.c.shift()).abs(), (f.l - f.c.shift()).abs()],
                   axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _round_level(c: pd.Series) -> pd.Series:
    step = np.where(c < 20, 1.0, np.where(c < 100, 5.0, np.where(c < 500, 10.0, 50.0)))
    return pd.Series(np.round(c.values / step) * step, index=c.index)


def nemesis_long(f: pd.DataFrame) -> pd.Series:
    """The March spec's Buy Day, literal (wrr-buy-model.md:22-29), mechanical forms as declared
    in Task 5 §1; ROC strictly below -3% (brief 5B). The bias condition (:23) is NOT a gate: the
    spec's 0-100 scale has no defined mapping to the live -1..+1 composite (recorded at fire)."""
    o, h, l, c, v = f.o, f.h, f.l, f.c, f.v
    body, rng = (c - o).abs(), h - l
    up_w, lo_w = h - np.maximum(o, c), np.minimum(o, c) - l
    down3 = (c < c.shift(1)) & (c.shift(1) < c.shift(2)) & (c.shift(2) < c.shift(3))
    low20 = l.shift(1).rolling(20).min()
    cond_decline = down3 | (l < low20)                                      # :24
    cond_rsi = wilder_rsi(c, 3) <= 15                                        # :25
    pbear = c.shift(1) < o.shift(1)
    engulf = pbear & (c > o) & (o <= c.shift(1)) & (c >= o.shift(1))
    hammer = (lo_w >= 2 * body) & (up_w <= body)
    doji = (body <= 0.10 * rng) & (lo_w > 2 * body)
    cond_candle = engulf | hammer | doji                                     # :26
    cond_vol = v >= 1.5 * v.shift(1).rolling(20).mean()                      # :27
    atr = wilder_atr(f)
    tp = (h + l + c) / 3
    vwap20 = (tp * v).rolling(20).sum() / v.rolling(20).sum()
    near = lambda lvl: (c - lvl).abs() <= atr                                # noqa: E731
    cond_support = near(low20) | near(vwap20) | near(_round_level(c))        # :28
    cond_roc = (c / c.shift(10) - 1) < NEMESIS_ROC_BELOW                     # :29, brief 5B
    return (cond_decline & cond_rsi & cond_candle & cond_vol & cond_support & cond_roc).fillna(False)


def plain_rsi3(c: pd.Series) -> pd.Series:
    """strategies.wrr_buy_model._compute_rsi(closes, 3), vectorised: plain mean of 3 deltas."""
    d = c.diff()
    g = d.clip(lower=0).rolling(3).sum() / 3
    lo = (-d).clip(lower=0).rolling(3).sum() / 3
    rsi = 100 - 100 / (1 + g / lo.replace(0, np.nan))
    return rsi.where(lo != 0, 100.0).round(2)


def phoenix_washout(f: pd.DataFrame) -> pd.Series:
    """PHOENIX's washout, without its candle and volume tests: close above the 200-day SMA,
    RSI(3) <= 10 by PHOENIX's own arithmetic, ROC(10) <= -8% (wrr_buy_model.py:128-143)."""
    from strategies import wrr_buy_model as w
    c = f.c
    above = (c > c.rolling(w.SMA_200_PERIOD).mean()) & (np.arange(len(c)) >= w.SMA_200_PERIOD + 4)
    rsi_ok = plain_rsi3(c) <= w.RSI_THRESHOLD
    roc_ok = (c / c.shift(w.ROC_PERIOD) - 1) * 100 <= w.ROC_THRESHOLD
    return (above & rsi_ok & roc_ok).fillna(False)


# ── the signal row ────────────────────────────────────────────────────────────────────────
def _levels(kind: str, f: pd.DataFrame, i: int) -> Dict[str, float]:
    c, l = float(f.c.iat[i]), float(f.l.iat[i])
    if kind == NEMESIS_SIGNAL_TYPE:                       # spec :37 and :40
        stop = l - 0.5 * float(wilder_atr(f).iat[i])
        return {"entry_price": round(c, 2), "stop_loss": round(stop, 2),
                "target_1": round(c + 1.5 * (c - stop), 2)}
    stop = l * 0.98                                       # PHOENIX's own levels
    return {"entry_price": round(c, 2), "stop_loss": round(stop, 2),
            "target_1": round(c + 3 * (c - stop), 2)}


def build_signal(ticker: str, session: date, kind: str, f: pd.DataFrame, i: int) -> Dict[str, Any]:
    strategy, registration = ((NEMESIS_STRATEGY, NEMESIS_REGISTRATION) if kind == NEMESIS_SIGNAL_TYPE
                              else (PHOENIX_W_STRATEGY, PHOENIX_W_REGISTRATION))
    close_at = datetime.combine(session, time(16, 0), tzinfo=ET).astimezone(timezone.utc)
    return {
        "signal_id": "%s-%s-%s" % (registration, ticker, session.strftime("%Y%m%d")),
        "timestamp": close_at.isoformat(),
        "strategy": strategy,
        "signal_type": kind,
        "ticker": ticker,
        "asset_class": "EQUITY",
        "direction": "LONG",
        "timeframe": "D",
        **_levels(kind, f, i),
        "triggering_factors": {"lab_registered": {
            "registration": registration, "session": session.isoformat(),
            "bars": "yfinance daily, auto_adjust=True (stable_engine.bars_yf)",
            "evaluated_at": datetime.now(timezone.utc).isoformat()}},
    }


def hits_on(frame: pd.DataFrame, session: date) -> List[str]:
    """Which registered kinds fire on `session`, the frame's last bar. [] if it is not."""
    if frame is None or frame.empty or frame["date"].iloc[-1] != session:
        return []
    f = frame.reset_index(drop=True)
    out = []
    if bool(nemesis_long(f).iat[-1]):
        out.append(NEMESIS_SIGNAL_TYPE)
    if bool(phoenix_washout(f).iat[-1]):
        out.append(PHOENIX_W_SIGNAL_TYPE)
    return out


# ── the job ───────────────────────────────────────────────────────────────────────────────
def _sessions_to_run(today: date) -> List[date]:
    from stable_engine.market_calendar import is_trading_day, previous_trading_day
    out, d = [], previous_trading_day(today)
    while d >= REGISTERED_FROM and len(out) < CATCH_UP_SESSIONS:
        if is_trading_day(d):
            out.append(d)
        d = previous_trading_day(d)
    return sorted(out)


async def evaluate_session(session: date, fetch=None, process=None) -> Dict[str, Any]:
    """Fetch bars ending `session`, emit every registered hit through the pipeline (shadow)."""
    if fetch is None:
        from stable_engine.bars_yf import fetch_batch as fetch
    if process is None:
        from signals.pipeline import process_signal_unified as process
    start, end = session - timedelta(days=BAR_CALENDAR_DAYS), session + timedelta(days=1)
    frames: Dict[str, pd.DataFrame] = {}
    for i in range(0, len(UNIVERSE), BATCH_SIZE):
        frames.update(fetch(list(UNIVERSE[i:i + BATCH_SIZE]), start, end))
    stale = [t for t, fr in frames.items() if fr is None or fr.empty or fr["date"].iloc[-1] != session]
    emitted = {NEMESIS_SIGNAL_TYPE: 0, PHOENIX_W_SIGNAL_TYPE: 0}
    for t, fr in frames.items():
        for kind in hits_on(fr, session):
            f = fr.reset_index(drop=True)
            await process(build_signal(t, session, kind, f, len(f) - 1),
                          source=SOURCE, skip_scoring=True)
            emitted[kind] += 1
    return {"session": session.isoformat(), "frames": len(frames), "missing": len(UNIVERSE) - len(frames),
            "stale": len(stale), "emitted": emitted}


async def run(now: Optional[datetime] = None) -> Dict[str, Any]:
    """One morning pass: every recent session not yet completed, oldest first."""
    from jobs.job_runs import has_completed
    from jobs.stable_jobs import _record

    today = (now or datetime.now(ET)).astimezone(ET).date()
    done: List[Dict[str, Any]] = []
    for session in _sessions_to_run(today):
        if await has_completed(JOB_NAME, session) is True:
            continue

        async def _one(session=session):
            res = await evaluate_session(session)
            if res["frames"] == 0 or res["stale"] > 0.1 * max(res["frames"], 1):
                # Bars not final for this session yet. An ERROR, not OutputCheckFailed: the
                # latter files as completed_defective, which has_completed counts as done, and
                # the session would never be retried (jobs/job_runs.py, R-IV.426(b)).
                raise RuntimeError("lab_registered_shadow %s: %d frames, %d stale"
                                   % (session, res["frames"], res["stale"]))
            res["rows_touched"] = sum(res["emitted"].values())
            return res

        out = await _record(JOB_NAME, _one, session_date=session)
        done.append(out or {"session": session.isoformat(), "failed": True})
    return {"sessions": done}
