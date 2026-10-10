"""The registered SHADOW forward tests (R-IV.855(d)): NEMESIS long and PHOENIX washout.

The cycle test runs the REAL `evaluate_session` with only the bar vendor and the pipeline stubbed:
synthetic bars built to satisfy each rule must come out as a signal row carrying every key
`log_signal` indexes, scored-skipped (no APIS relabel, no countertrend gate) and L0-suppressed.
"""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from strategies import registered_shadow as rs

SESSION = date(2026, 10, 12)
REQUIRED = ("signal_id", "asset_class", "entry_price", "stop_loss", "target_1")  # log_signal


def _frame(closes, opens=None, highs=None, lows=None, vols=None):
    n = len(closes)
    days = [SESSION - timedelta(days=n - 1 - i) for i in range(n)]
    c = np.array(closes, float)
    o = np.array(opens if opens is not None else c, float)
    h = np.array(highs if highs is not None else np.maximum(o, c) + 0.5, float)
    l = np.array(lows if lows is not None else np.minimum(o, c) - 0.5, float)
    v = np.array(vols if vols is not None else [1_000_000] * n, float)
    return pd.DataFrame({"date": days, "o": o, "h": h, "l": l, "c": c, "v": v})


def nemesis_bars():
    """Flat at 100, ten closes down to 92.5, then a hammer on double volume that still closes
    lower (3 down closes), 7.8% under its close 10 bars back, at the prior low."""
    closes = [100.0] * 250 + [99.0, 98.0, 97.0, 96.0, 95.0, 94.5, 94.0, 93.5, 93.0, 92.5]
    opens = [x + 0.3 for x in closes]
    highs = [max(o, c) + 0.3 for o, c in zip(opens, closes)]
    lows = [min(o, c) - 0.3 for o, c in zip(opens, closes)]
    closes.append(92.2); opens.append(92.5); highs.append(92.8); lows.append(89.0)
    vols = [1_000_000] * 260 + [2_000_000]
    return _frame(closes, opens, highs, lows, vols)


def phoenix_bars():
    """240 bars rising 50 -> 115 (far above the 200-day), then a slide to 99 on ordinary volume
    and a DOWN candle: PHOENIX's candle and volume tests would both reject it; the washout
    takes it."""
    closes = [50 + 65 * i / 239 for i in range(240)] + [115 - 16 * k / 10 for k in range(1, 11)]
    opens = [x + 0.4 for x in closes]                              # every bar closes below its open
    return _frame(closes, opens)


def test_the_nemesis_rule_fires_on_its_literal_shape():
    f = nemesis_bars()
    assert bool(rs.nemesis_long(f).iat[-1]) is True
    assert bool(rs.phoenix_washout(f).iat[-1]) is False         # below/at its 200-day: no


def test_the_washout_fires_where_phoenix_as_coded_would_not():
    from strategies import wrr_buy_model as w
    f = phoenix_bars()
    assert bool(rs.phoenix_washout(f).iat[-1]) is True
    last = f.iloc[-1]
    assert not w._is_reversal_candle(last.o, last.h, last.l, last.c)  # the coded filter rejects


def test_the_washout_rsi_is_phoenixs_own_arithmetic():
    from strategies import wrr_buy_model as w
    f = phoenix_bars()
    vec = rs.plain_rsi3(f.c)
    for i in range(len(f) - 30, len(f)):
        assert vec.iat[i] == w._compute_rsi(list(f.c.iloc[: i + 1]), 3)


def test_roc_at_exactly_minus_three_percent_does_not_fire():
    """The literal variant is brief 5B's `roc < -3.0`: strictly below."""
    f = nemesis_bars()
    c10 = f.c.iat[-11]
    f.loc[f.index[-1], "c"] = round(c10 * 0.97, 6)              # exactly -3.000%
    assert bool(rs.nemesis_long(f).iat[-1]) is False


@pytest.mark.asyncio
async def test_one_real_cycle_emits_both_kinds_as_shadow_rows():
    frames = {"AAPL": nemesis_bars(), "MSFT": phoenix_bars(), "XOM": _frame([100.0] * 260)}
    asked, sent = [], []

    def _fetch(tickers, start, end):
        asked.extend(tickers)
        return {t: frames[t] for t in tickers if t in frames}

    async def _process(signal, source=None, skip_scoring=False, **_):
        sent.append((signal, source, skip_scoring))
        return signal

    res = await rs.evaluate_session(SESSION, fetch=_fetch, process=_process)

    assert set(asked) == set(rs.UNIVERSE)                       # the frozen universe, all of it
    assert res["emitted"] == {rs.NEMESIS_SIGNAL_TYPE: 1, rs.PHOENIX_W_SIGNAL_TYPE: 1}
    by_type = {s["signal_type"]: (s, src, skip) for s, src, skip in sent}
    n, src, skip = by_type[rs.NEMESIS_SIGNAL_TYPE]
    assert (n["ticker"], n["strategy"], src, skip) == ("AAPL", "nemesis_spec", "lab_registered", True)
    assert all(n[k] not in (None, "") for k in REQUIRED)
    assert n["target_1"] > n["entry_price"] > n["stop_loss"]
    p, _, _ = by_type[rs.PHOENIX_W_SIGNAL_TYPE]
    assert (p["ticker"], p["strategy"]) == ("MSFT", "phoenix_washout")
    assert p["triggering_factors"]["lab_registered"]["registration"] == "phoenix-washout-v1"


@pytest.mark.asyncio
async def test_a_frame_that_does_not_end_on_the_session_is_stale_not_a_fire():
    old = nemesis_bars().iloc[:-1]                               # the session's bar not final

    def _fetch(tickers, start, end):
        return {"AAPL": old} if "AAPL" in tickers else {}

    sent = []

    async def _process(signal, **_):
        sent.append(signal)

    res = await rs.evaluate_session(SESSION, fetch=_fetch, process=_process)
    assert res["stale"] == 1 and sent == []


def test_both_registered_types_are_suppressed_from_every_surface():
    from config.l0_routing import SUPPRESS_ALWAYS, evaluate_l0_gate
    for st in (rs.NEMESIS_SIGNAL_TYPE, rs.PHOENIX_W_SIGNAL_TYPE):
        assert st in SUPPRESS_ALWAYS
        assert evaluate_l0_gate({"signal_type": st, "ticker": "AAPL"})["would_suppress"] is True


def test_sessions_start_at_the_registration_and_catch_up_at_most_five():
    assert rs._sessions_to_run(date(2026, 10, 12)) == []        # Monday morning: Friday is pre-registration
    assert rs._sessions_to_run(date(2026, 10, 13)) == [date(2026, 10, 12)]
    late = rs._sessions_to_run(date(2026, 10, 27))
    assert len(late) == 5 and late[-1] == date(2026, 10, 26)


@pytest.mark.asyncio
async def test_unfinished_bars_raise_so_the_session_is_retried(monkeypatch):
    """completed_defective would count as done and never retry; a stale session must be an
    error, so tomorrow's pass picks it up."""
    import jobs.job_runs as jr
    import jobs.stable_jobs as sj

    async def _not_done(job, session):
        return False

    async def _stale(session):
        return {"session": session.isoformat(), "frames": 196, "missing": 0, "stale": 150,
                "emitted": {rs.NEMESIS_SIGNAL_TYPE: 0, rs.PHOENIX_W_SIGNAL_TYPE: 0}}

    raised = []

    async def _record(name, fn, session_date=None):
        try:
            return await fn()
        except Exception as e:  # noqa: BLE001
            raised.append(type(e))
            return None

    monkeypatch.setattr(jr, "has_completed", _not_done)
    monkeypatch.setattr(sj, "_record", _record)
    monkeypatch.setattr(rs, "evaluate_session", _stale)
    from datetime import datetime
    await rs.run(now=datetime(2026, 10, 13, 7, 0, tzinfo=rs.ET))
    assert raised == [RuntimeError]
    assert sj.OutputCheckFailed not in raised
