"""Regime classifier v2's missing inputs. R-IV.1260(c).

LAB (R-IV.1256) found that `build_inputs` never fills eight inputs the v1 rule rows already
check, so four labels could never be shown and two clauses never fired. NOTHING HERE CHANGES A
THRESHOLD OR A RULE: every value below is computed because a row already asks for it by name,
and the thresholds come from the rules file.

WHAT WAS ACTUALLY BLOCKED, measured by diffing the classifier's `_get(inputs, ...)` paths
against what `build_inputs` produces:

  RANGE_CHOP          `spy.adx_below_20_sessions`      -> row returned NOT EVALUABLE, always
  RECOVERY            `prior_regime` never passed, plus `spy.confirmed_break_up_50dma`,
                      `spy.ma20_crossed_above_ma50`, `breadth.thrust`
  BEAR_MARKET_RALLY   `prior_regime`, `spy.closes_above_20_and_50`,
                      `spy.below_falling_200dma`, `sessions_since_crash`
  BEAR_MARKET         `spy.closes_below_falling_200dma` (its second clause only; the row could
                      still match on the 20%-below-52w-high clause)
  CRASH               `vix.vix` / `vix.vix3m` -> see `models/regime_vix.py`

`prior_regime` IS THE ONE THAT SURPRISED ME. `build_inputs` accepts it as a parameter and its
docstring says the job passes it; a grep of the job and the seed finds it passed NOWHERE. With
it None, `_row_recovery`'s first test ("the prior regime is one of rows 1-4") is False on every
session, so RECOVERY could not match even with every other input present. A parameter with a
default is a silent one.

EVERY FUNCTION RETURNS None RATHER THAN False WHEN IT CANNOT ANSWER. That is this module's
standing rule and the reason the rows distinguish NOT EVALUABLE from "no": a check that never
ran is not a check that passed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from models.regime_inputs import (Bar, MIN_BARS, _closes, _day, latest_adx,
                                  latest_moving_averages, sectors_above_50dma)


def adx_below_sessions(bars: Sequence[Bar], threshold: float) -> Optional[int]:
    """How many sessions, counting back from the latest, ADX(14) has been below `threshold`.

    THE CONSECUTIVE RUN ENDING NOW, not a count within a window. The Range row reads it as "ADX
    below 20 for 10 sessions", which is a statement about a stretch that is still running: a
    count of 10 scattered through 30 sessions is a different market and would let Range match on
    a tape that spent the last week trending.

    None when the series cannot produce an ADX at the latest session -- never 0, which would
    read as "ADX is above the threshold today".
    """
    cs = _closes(bars)
    if len(cs) < MIN_BARS:
        return None
    highs = [b.h for b in bars]
    lows = [b.l for b in bars]
    latest = latest_adx(highs, lows, cs)
    if latest is None:
        return None
    if latest >= threshold:
        return 0
    run = 0
    # Walk back one session at a time, recomputing ADX as it stood then. Slower than keeping a
    # rolling series and exact about the "as it stood" question, which is what the row means.
    for k in range(0, len(cs) - MIN_BARS):
        n = len(cs) - k
        a = latest_adx(highs[:n], lows[:n], cs[:n])
        if a is None or a >= threshold:
            break
        run += 1
    return run


def ma_falling(bars: Sequence[Bar], window: str, lookback: int = 10) -> Optional[bool]:
    """Is the `window`-day average lower than it was `lookback` sessions ago?

    The mirror of `_ma50_rising`, generalised, because the Bear row asks about a FALLING 200dma
    and the Bear-rally row asks again. Falling is not "not rising": a flat average is neither,
    and both callers want the strict direction.
    """
    cs = _closes(bars)
    if len(cs) < MIN_BARS:
        return None
    now = latest_moving_averages(cs)["sma"].get(window)
    then = latest_moving_averages(cs[:-lookback])["sma"].get(window) if len(cs) > lookback \
        else None
    if now is None or then is None:
        return None
    return now < then


def closes_below_falling_200dma(bars: Sequence[Bar]) -> Optional[int]:
    """The consecutive run of closes below a 200dma that is itself falling. Bear row, clause 2.

    BOTH CONDITIONS ARE TESTED PER SESSION, as they stood on that session: a run counted
    against today's 200dma would stretch back through sessions whose 200dma was higher, and the
    row's "15 closes below a FALLING 200dma" is a statement about a deteriorating tape rather
    than about today's average alone.
    """
    cs = _closes(bars)
    if len(cs) < MIN_BARS:
        return None
    run = 0
    for k in range(0, len(cs) - MIN_BARS):
        n = len(cs) - k
        ma = latest_moving_averages(cs[:n])["sma"]["200"]
        if ma is None:
            break
        if cs[n - 1] >= ma:
            break
        falling = ma_falling(bars[:n], "200")
        if falling is not True:
            break
        run += 1
    return run


def below_falling_200dma(bars: Sequence[Bar]) -> Optional[bool]:
    """Is the latest close below a falling 200dma? Bear-rally row's qualifier."""
    n = closes_below_falling_200dma(bars)
    return None if n is None else n > 0


def closes_above_20_and_50(bars: Sequence[Bar]) -> Optional[int]:
    """The consecutive run of closes above BOTH the 20dma and the 50dma. Bear-rally row.

    Both, not either: the row's test is a rally that has reclaimed the short and the medium
    average, and reading it as "above the 20" would fire on the first bounce in a downtrend --
    which is the whole thing a bear-market-rally label is trying to name rather than miss.
    """
    cs = _closes(bars)
    if len(cs) < MIN_BARS:
        return None
    run = 0
    for k in range(0, len(cs) - MIN_BARS):
        n = len(cs) - k
        sma = latest_moving_averages(cs[:n])["sma"]
        m20, m50 = sma.get("20"), sma.get("50")
        if m20 is None or m50 is None:
            break
        if not (cs[n - 1] > m20 and cs[n - 1] > m50):
            break
        run += 1
    return run


def confirmed_break_up_50dma(bars: Sequence[Bar],
                             rules: Optional[Dict[str, Any]] = None) -> Optional[bool]:
    """§2's C5 test applied UPWARD, mirroring `confirmed_break_down_50dma` exactly.

    The same N closes, the same stack requirement and the same volume confirmation, with every
    comparison reversed -- written beside the downward one rather than as a flag on it, because
    a single function with a direction argument is where a sign error hides.
    """
    if rules is None:
        from models.regime_classifier import load_rules
        rules = load_rules()
    cb = rules.get("confirmed_break") or {}
    need = int(cb.get("closes_through_50dma") or 2)
    rvol_min = float(cb.get("rvol_min_on_break_day") or 1.2)

    cs = _closes(bars)
    if len(cs) < MIN_BARS or len(bars) < need + 20:
        return None
    for k in range(need):
        upto = cs[:len(cs) - k]
        ma = latest_moving_averages(upto)["sma"]["50"]
        if ma is None:
            return None
        if upto[-1] <= ma:
            return False
    if cb.get("stack_must_turn"):
        stack = latest_moving_averages(cs)["sma"]["stack_state"]
        if stack is None:
            return None
        if stack == "bearish":
            return False
    vols = [b.v for b in bars if b.v is not None]
    if len(vols) >= 21:
        base = sum(vols[-21:-1]) / 20.0
        if base > 0 and (vols[-1] / base) < rvol_min:
            return False
    return True


def ma20_crossed_above_ma50(bars: Sequence[Bar], within: int = 10) -> Optional[bool]:
    """Did the 20dma cross above the 50dma within the last `within` sessions? Recovery row.

    A CROSS, not a position: the row pairs it with a confirmed break as the signature of a turn,
    and "the 20 is above the 50" is true for most of an uptrend. Reading the position instead
    would make Recovery match months after any recovery.
    """
    cs = _closes(bars)
    if len(cs) < MIN_BARS + within:
        return None
    above = []
    for k in range(within + 1):
        n = len(cs) - k
        sma = latest_moving_averages(cs[:n])["sma"]
        m20, m50 = sma.get("20"), sma.get("50")
        if m20 is None or m50 is None:
            return None
        above.append(m20 > m50)
    # `above` is newest-first. A cross is "above now, below at some point in the window".
    return above[0] and any(not a for a in above[1:])


def breadth_thrust(series: Dict[str, List[Bar]], as_of: str, rules: Dict[str, Any],
                   window_dates: Sequence[str]) -> Optional[bool]:
    """The Recovery row's breadth thrust, on the thresholds the rules file already carries.

    `recovery_breadth_thrust_from_pct` (15) to `recovery_breadth_thrust_to_pct` (60) within
    `recovery_breadth_thrust_within_sessions` (10), measured on the SECTOR breadth this module
    already computes -- the same series §2's Uptrend row reads.

    NOT Zweig's advance/decline thrust, and the difference is stated wherever this is shown: the
    hub stores no advance/decline line. This is the measure the rules file's own thresholds
    describe, on the breadth series that exists.

    None when any session in the window cannot produce a full sector count. `sectors_above_50dma`
    refuses a partial count, so a missing day is a hole and not a zero.
    """
    th = rules.get("thresholds") or {}
    lo = float(th.get("recovery_breadth_thrust_from_pct") or 15.0)
    hi = float(th.get("recovery_breadth_thrust_to_pct") or 60.0)
    within = int(th.get("recovery_breadth_thrust_within_sessions") or 10)
    # NORMALISED AT THE BOUNDARY, and this cost a deploy. `sectors_above_50dma` compares
    # `_day(bar.date) <= as_of`, so `as_of` must be an ISO STRING — its signature says so. My
    # local fixtures built bars with ISO-string dates while production reads DATE objects out
    # of Postgres, so the first v2 seed died on "'<=' not supported between instances of 'str'
    # and 'datetime.date'" — and the reason was invisible until the session build was audited.
    # Converting here rather than trusting the caller means no call site can get the shape
    # wrong again, and the test for this uses date OBJECTS.
    dates = [d for d in (_day(x) for x in list(window_dates)[-(within + 1):]) if d]
    if len(dates) < 2:
        return None
    pcts = []
    for d in dates:
        sec = sectors_above_50dma(series, d)
        if sec.get("count") is None or not sec.get("total"):
            return None
        pcts.append(100.0 * float(sec["count"]) / float(sec["total"]))
    return min(pcts) < lo and pcts[-1] > hi


def fill(inputs: Dict[str, Any], series: Dict[str, List[Bar]], i: int, *,
         rules: Dict[str, Any], prior_regime: Optional[str] = None,
         sessions_since_crash: Optional[int] = None,
         vix: Optional[Dict[str, Any]] = None,
         window_dates: Sequence[str] = ()) -> Dict[str, Any]:
    """Add v2's inputs to a v1 `build_inputs` result, in place, and return it.

    ADDITIVE ONLY. Nothing already present is overwritten, so a v1 value and a v2 value can
    never disagree about the same key -- and the diff between v1 and v2 labels is attributable
    to the inputs that were MISSING rather than to any recomputation of the ones that were not.
    """
    spy = series.get("SPY") or []
    bars = spy[:i + 1]
    th = rules.get("thresholds") or {}
    spy_block = inputs.setdefault("spy", {})
    breadth = inputs.setdefault("breadth", {})

    def put(block, key, value):
        if block.get(key) is None:
            block[key] = value

    put(spy_block, "adx_below_20_sessions",
        adx_below_sessions(bars, float(th.get("range_adx_below") or 20.0)))
    put(spy_block, "ma50_falling", ma_falling(bars, "50"))
    put(spy_block, "ma200_falling", ma_falling(bars, "200"))
    put(spy_block, "closes_below_falling_200dma", closes_below_falling_200dma(bars))
    put(spy_block, "below_falling_200dma", below_falling_200dma(bars))
    put(spy_block, "closes_above_20_and_50", closes_above_20_and_50(bars))
    put(spy_block, "confirmed_break_up_50dma", confirmed_break_up_50dma(bars, rules))
    put(spy_block, "ma20_crossed_above_ma50", ma20_crossed_above_ma50(bars))
    put(breadth, "thrust", breadth_thrust(series, _day(bars[-1].date), rules,
                                          window_dates or [b.date for b in bars]))
    if inputs.get("prior_regime") is None:
        inputs["prior_regime"] = prior_regime
    if inputs.get("sessions_since_crash") is None:
        inputs["sessions_since_crash"] = sessions_since_crash
    if vix:
        existing = inputs.setdefault("vix", {})
        for k, v in vix.items():
            if existing.get(k) is None:
                existing[k] = v
    return inputs
