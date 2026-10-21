"""Build one session's classifier inputs from a bar series. Pure, and strictly backward-looking.

R-IV.1195(b) wires v1 live, and this is the piece between the bars and `regime_classifier`.
R-IV.1193(d) names `market_state` as the structure input, so that is what this computes --
through the same `indicators/` helpers the live chart path uses, not a second implementation.

NO LOOKAHEAD, which is the whole reason this takes an index rather than a frame. Every input for
session `i` is computed from `bars[:i+1]`. Computing a 200dma over the whole window and reusing
it for each session would let October's prices decide a February label, and the resulting seed
would look better than anything the job could do live.

ONE SOURCE FOR market_state. `chart_indicators.market_state(adx, stack_state, price_vs)` is the
fix-first #5 function the card already shows. Calling it here means the seeded labels and the
live labels agree by construction; reimplementing the ADX bands would give two answers to one
question, which is the fault class this lane keeps paying for.

WHAT v1 CANNOT BUILD, stated rather than defaulted: no VIX series (so row 1 is NOT EVALUABLE),
no HY OAS, no carry strip. The families dict carries only what the bars can answer. An absent
family is absent, never inferred (R-IV.1193(d)).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from indicators.adx import latest_adx
from indicators.moving_averages import latest_moving_averages
from services.read_only.chart_indicators import market_state

#: §2's rows need a 200dma, and `latest_moving_averages` returns None for a short series rather
#: than a partial average, so this is the floor at which a session becomes classifiable.
MIN_BARS = 200

#: The 52-week high is a trailing-year extreme. 252 sessions is the convention used elsewhere in
#: this repo for a year of dailies.
YEAR_SESSIONS = 252

#: The indices §2 reads for its breadth test. SPY is also the structure index.
INDICES = ("SPY", "QQQ", "IWM")

#: The eleven SPDR sector ETFs. §2's thresholds say "sectors above their 50dma" out of
#: `uptrend_sectors_total: 11`, and these are the eleven that number refers to. Without them the
#: Uptrend, Melt-up and Narrow-uptrend rows are permanently NOT EVALUABLE -- measured on a
#: synthetic uptrend, which produced NO LABEL AT ALL, because the most common regime in the book
#: was the one v1 could not name.
SECTORS = ("XLK", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLU", "XLRE", "XLC")


class Bar:
    """One daily bar. A class rather than a tuple so a caller cannot silently swap h and l."""

    __slots__ = ("date", "o", "h", "l", "c", "v")

    def __init__(self, date, o=None, h=None, l=None, c=None, v=None):
        self.date, self.o, self.h, self.l, self.c, self.v = date, o, h, l, c, v

    @classmethod
    def from_row(cls, row) -> "Bar":
        g = row.get if hasattr(row, "get") else (lambda k, d=None: row[k])
        return cls(g("date"), g("o"), g("h"), g("l"), g("c"), g("v"))


def _day(d) -> Optional[str]:
    if d is None:
        return None
    iso = getattr(d, "isoformat", None)
    return (iso() if callable(iso) else str(d))[:10]


def _closes(bars: Sequence[Bar]) -> List[float]:
    return [b.c for b in bars if b.c is not None]


def pct_below_52w_high(bars: Sequence[Bar]) -> Optional[float]:
    """How far the last close sits below the trailing-year high, as a positive percentage.

    Computed from the CLOSES this series actually holds. A series shorter than a year still gets
    a figure -- it is the high of what exists -- which is honest for a 200-bar seed window and is
    why `window_sessions` is published beside it rather than assumed to be 252.
    """
    cs = _closes(bars)[-YEAR_SESSIONS:]
    if not cs:
        return None
    hi = max(cs)
    if hi <= 0:
        return None
    return round((hi - cs[-1]) / hi * 100.0, 4)


def _index_block(bars: Sequence[Bar]) -> Dict[str, Any]:
    """price / ma50 / ma200 / market_state for one index, from this slice only."""
    cs = _closes(bars)
    if len(cs) < MIN_BARS:
        return {"price": None, "ma50": None, "ma200": None, "market_state": None,
                "bars": len(cs)}
    ma = latest_moving_averages(cs)
    adx = latest_adx([b.h for b in bars], [b.l for b in bars], cs)
    ms = market_state(adx, ma["sma"]["stack_state"], ma["sma"]["price_vs"])
    return {
        "price": cs[-1],
        "ma20": ma["sma"]["20"], "ma50": ma["sma"]["50"],
        "ma120": ma["sma"]["120"], "ma200": ma["sma"]["200"],
        "stack_state": ma["sma"]["stack_state"],
        "price_vs": ma["sma"]["price_vs"],
        "adx": adx,
        "market_state": ms.get("state"),
        "market_state_basis": ms.get("basis"),
        "bars": len(cs),
    }


#: The only version whose defect fixes are live. R-IV.1297(b)1.
RULES_VERSION_V21 = "v2.1"


def v21_fixes_apply(rules_version: Optional[str] = None,
                    rules: Optional[Dict[str, Any]] = None) -> bool:
    """Whether to compute v2.1's corrected inputs rather than v2's frozen ones.

    WHY A GATE AT ALL. R-IV.1265(a) froze the v2 classifier: "any change is v3 with a ruling."
    The two v2.1 fixes went into the SHARED builder, and `RULES_VERSION` is still "v2" -- so
    had 0e301ea8 deployed as written, every row stamped `rules_version = 'v2'` would have
    carried v2.1 ARITHMETIC. The label would say one thing and the numbers behind it another,
    and the rows already in the table would no longer be reproducible from the version they
    name. QUERY caught this before the deploy (M1).

    ONE PREDICATE, read by both gated call sites, because a version test written twice is a
    version test that will disagree with itself. The explicit argument wins; otherwise the
    rules file's own `version` answers, which is the file actually being applied. Absent both,
    the answer is NO -- an unknown version gets the frozen behaviour, never the new one.
    """
    if rules_version is not None:
        return str(rules_version) == RULES_VERSION_V21
    if rules:
        return str(rules.get("version") or "") == RULES_VERSION_V21
    return False

def build_inputs(series: Dict[str, List[Bar]], i: int, *, settled: bool,
                 overlays: Optional[Dict[str, Any]] = None,
                 lenses: Optional[Dict[str, Any]] = None,
                 prior_regime: Optional[str] = None,
                 vix: Optional[Dict[str, Any]] = None,
                 rules_version: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Inputs for the session at index `i` of SPY's series, or None if it predates MIN_BARS.

    `series` maps ticker -> oldest-first bars. Each index is sliced to the same SESSION DATE, not
    to the same index: a ticker that missed a session would otherwise be read a day out of step,
    which is the UW/Yahoo bar landmine in a different costume.
    """
    spy = series.get("SPY") or []
    if i < 0 or i >= len(spy):
        return None
    as_of = _day(spy[i].date)
    if len(_closes(spy[:i + 1])) < MIN_BARS:
        return None

    indices: Dict[str, Any] = {}
    for tkr in INDICES:
        bars = series.get(tkr) or []
        # Slice by DATE, so each index is read as of the same session.
        upto = [b for b in bars if _day(b.date) is not None and _day(b.date) <= as_of]
        block = _index_block(upto)
        # A TICKER WITH NO BAR FOR THIS SESSION IS UNAVAILABLE, not "its last known price".
        # Slicing by date already stops a FUTURE bar leaking in; without this it still reuses
        # the newest bar BEFORE `as_of`, so an index missing 30 sessions reported a 30-session
        # old price as current and the breadth family was computed from it. Measured on a
        # synthetic series where IWM stopped 30 sessions early: it read 483.20 while SPY was
        # at 539.20, and `breadth` came back False -- a number, from nothing.
        newest = _day(upto[-1].date) if upto else None
        if newest != as_of:
            block = {"price": None, "ma50": None, "ma200": None, "market_state": None,
                     "bars": block.get("bars", 0),
                     "unavailable_reason": ("no bar for %s; newest is %s" % (as_of, newest))}
        indices[tkr] = block

    spy_block = dict(indices["SPY"])
    spy_block["pct_below_52w_high"] = pct_below_52w_high(spy[:i + 1])
    spy_block["window_sessions"] = min(len(_closes(spy[:i + 1])), YEAR_SESSIONS)
    spy_block["ma50_rising"] = _ma50_rising(spy[:i + 1])
    # The KEY name is unchanged on purpose: `regime_classifier` reads
    # `spy.rsi_ge_75_of_last_5` by name and every stored `inputs_json` already carries it, so
    # renaming it would orphan both. Only the FUNCTION was renamed (R-IV.1297(e)).
    spy_block["rsi_ge_75_of_last_5"] = _rsi_hits_above_melt_up_min(
        spy[:i + 1], rules_version=rules_version)
    # §2's C5 test. None when the series cannot answer -- the Breakdown row then refuses by
    # name rather than being handed a False it did not earn.
    spy_block["confirmed_break_down_50dma"] = confirmed_break_down_50dma(spy[:i + 1])

    # FAMILIES. Only two of the five can be answered from bars, and the definitions below are
    # V1 WORKING DEFINITIONS rather than ones I am entitled to invent (R-IV.925(b)). Each is a
    # clause §2 already uses for another row, so nothing new is asserted:
    #
    #   STRUCTURE risk-off   SPY below its 50dma            (the Correction row's first test)
    #   BREADTH   risk-off   >= 2 of 3 indices below 50dma  (the Correction row's second test)
    #
    # Reported with `families_basis` so a reader sees the test and not just the boolean, and
    # flagged in the rules file as pending ratification. CREDIT, VOL and CARRY have no feed in
    # v1: ABSENT, never inferred (R-IV.1193(d)).
    #
    # The LABEL does not turn on any of this in v1. Only §2 row 1 counts families, and that row
    # is NOT EVALUABLE without a VIX series. These exist for the card's evidence panel.
    below_50 = [t for t in INDICES
                if indices[t]["price"] is not None and indices[t]["ma50"] is not None
                and indices[t]["price"] < indices[t]["ma50"]]
    families: Dict[str, Any] = {}
    families_basis: Dict[str, str] = {}
    if spy_block.get("price") is not None and spy_block.get("ma50") is not None:
        families["structure"] = spy_block["price"] < spy_block["ma50"]
        families_basis["structure"] = "SPY %.2f is %s its 50dma %.2f" % (
            spy_block["price"], "below" if families["structure"] else "above",
            spy_block["ma50"])
    if all(indices[t]["price"] is not None and indices[t]["ma50"] is not None
           for t in INDICES):
        families["breadth"] = len(below_50) >= 2
        families_basis["breadth"] = "%d of 3 indices below their 50dma (%s)" % (
            len(below_50), ", ".join(below_50) if below_50 else "none")

    return {
        "as_of": as_of,
        "settled": bool(settled),
        "spy": spy_block,
        "indices": {t: {"price": indices[t]["price"], "ma50": indices[t]["ma50"],
                        "ma200": indices[t]["ma200"],
                        "market_state": indices[t]["market_state"]} for t in INDICES},
        "families": families,
        "families_basis": families_basis,
        "families_absent_in_v1": {
            "credit": "no HY OAS feed in v1",
            "vol": "no VIX/VIX3M series in v1",
            "carry": "no carry strip in v1",
            "rule": "an absent family is counted neither way and never inferred",
        },
        "overlays": overlays or {},
        "lenses": lenses or {},
        "prior_regime": prior_regime,
        "breadth": _breadth_block(series, as_of, below_50, families),
        "vix": vix or {},
    }


def _breadth_block(series: Dict[str, List[Bar]], as_of: str, below_50, families) -> Dict[str, Any]:
    """The `breadth.*` paths §2's Uptrend, Melt-up and Narrow-uptrend rows read.

    `high_beta_above_50dma_pct` is LEFT ABSENT. §2's narrow-uptrend row compares it to 40%, but
    no ruling states which names make up the high-beta universe, and picking one would be
    inventing the measurement rather than taking it (R-IV.925(b)). So Narrow-uptrend stays NOT
    EVALUABLE in v1 and says so, while Uptrend and Melt-up -- which need only the sector count --
    become answerable.
    """
    sec = sectors_above_50dma(series, as_of)
    out: Dict[str, Any] = {
        "indices_below_50dma": len(below_50) if families.get("breadth") is not None else None,
        "sectors_total": sec["total"],
        "sectors_basis": sec["reason"] or ("%d of %d sectors above their 50dma (%s)"
                                           % (sec["count"], sec["total"],
                                              ", ".join(sec.get("above") or []) or "none")),
        "high_beta_above_50dma_pct_absent_reason":
            "no ruled high-beta universe in v1; not inferred (R-IV.925(b))",
    }
    if sec["count"] is not None:
        out["sectors_above_50dma"] = sec["count"]
    return out


def sectors_above_50dma(series: Dict[str, List[Bar]], as_of: str) -> Dict[str, Any]:
    """How many of the eleven sector ETFs closed above their own 50dma on `as_of`.

    REFUSES A PARTIAL COUNT. §2 compares against a total of 11 (`uptrend_sectors_total`), so a
    count built from seven usable series is not a number that can be compared to 5 -- it is a
    smaller sample wearing the same units. Short of the full set this returns None with the
    missing tickers named, and the three rows that need it report NOT EVALUABLE.
    """
    above, usable, missing = [], [], []
    for t in SECTORS:
        bars = [b for b in (series.get(t) or [])
                if _day(b.date) is not None and _day(b.date) <= as_of]
        if not bars or _day(bars[-1].date) != as_of:
            missing.append(t)
            continue
        cs = _closes(bars)
        ma = latest_moving_averages(cs)["sma"]["50"] if len(cs) >= 50 else None
        if ma is None or not cs:
            missing.append(t)
            continue
        usable.append(t)
        if cs[-1] > ma:
            above.append(t)
    if missing:
        return {"count": None, "total": len(SECTORS), "missing": missing,
                "reason": ("%d of %d sector series unusable for %s (%s); a partial count cannot "
                           "be compared to a threshold stated out of %d"
                           % (len(missing), len(SECTORS), as_of, ", ".join(missing),
                              len(SECTORS)))}
    return {"count": len(above), "total": len(SECTORS), "above": above,
            "missing": [], "reason": None}


def confirmed_break_down_50dma(bars: Sequence[Bar], rules: Optional[Dict[str, Any]] = None
                               ) -> Optional[bool]:
    """§2's C5 test, applied downward: N closes through the 50dma, the stack turned, and volume
    confirming on the break day.

    Returns None when the series cannot answer, never False. "No confirmed break" and "I could
    not check" put the same word on the screen and mean opposite things, which is the fault this
    whole module is built around.
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

    # The last `need` closes must each sit below the 50dma AS IT STOOD on that session.
    for k in range(need):
        upto = cs[:len(cs) - k]
        ma = latest_moving_averages(upto)["sma"]["50"]
        if ma is None:
            return None
        if upto[-1] >= ma:
            return False

    if cb.get("stack_must_turn"):
        stack = latest_moving_averages(cs)["sma"]["stack_state"]
        if stack is None:
            return None
        if stack == "bullish":
            return False

    # Volume on the break day, relative to the 20 sessions before it.
    vols = [b.v for b in bars[-(20 + need):-need] if b.v is not None]
    break_v = bars[-need].v
    if not vols or break_v is None:
        return None
    avg = sum(vols) / len(vols)
    if avg <= 0:
        return None
    return (break_v / avg) >= rvol_min


def _rsi_hits_above_melt_up_min(bars: Sequence[Bar], threshold: Optional[float] = None,
                                lookback: int = 5, rules: Optional[Dict[str, Any]] = None,
                                rules_version: Optional[str] = None):
    """The Melt-up row's RSI leg over the last `lookback` settled closes.

    RENAMED FROM `_rsi_ge_75_of_last_5` (R-IV.1297(e)): the 75 belongs to
    `thresholds.melt_up_rsi_min`, and a name that states it is a second place for one figure --
    the place nobody edits, and therefore the one that drifts. The DICT KEY keeps its old
    spelling, because the classifier reads `spy.rsi_ge_75_of_last_5` by name and every stored
    `inputs_json` already carries it.

    TWO BEHAVIOURS, CHOSEN BY VERSION (R-IV.1297(b)1), because v2 is frozen (R-IV.1265(a)) and
    the fix changes what the Melt-up row can do:

    v2 and anything else  999aae43's exact behaviour: a BOOL -- True on the first close at or
                          above 75.0, False if none of the `lookback` reach it. The threshold
                          is this signature's literal, as it was, NOT the rules file's.
    v2.1                  an INTEGER COUNT, with the threshold read from the rules file.

    WHY v2's BOOL IS KEPT RATHER THAN QUIETLY REPAIRED. `regime_classifier` tests
    `hits >= melt_up_rsi_hits_of_last_5`, where that threshold is 2: `float(True)` is 1.0 and
    `1.0 >= 2` is False, so UNDER v2 THE MELT-UP RSI LEG CAN NEVER PASS. That is a defect, and
    v2.1 is the version that fixes it -- but v2's stored rows were computed with it and must
    stay reproducible from the version they name. Repairing v2 in place would make 304 stored
    labels unexplainable by any version in the repo.

    None when the series is too short, or when any session in the window cannot be read: a
    SESSION THAT CANNOT BE READ MAKES THE COUNT UNKNOWABLE, not smaller. Returning the partial
    count would understate it, and the row would then fail for a reason about the data rather
    than about the tape. Both versions agree on that.
    """
    from indicators.rsi import latest_rsi

    v21 = v21_fixes_apply(rules_version=rules_version, rules=rules)

    if threshold is None:
        if not v21:
            threshold = 75.0   # 999aae43's signature default, frozen with the rest of v2
        else:
            if rules is None:
                # DEFERRED, like the other reader in this module: `regime_classifier` imports
                # from here, so a module-level import back would be a cycle. My first version
                # used the bare name and raised NameError on the very first call.
                from models.regime_classifier import load_rules

                rules = load_rules()
            th = rules.get("thresholds") or {}
            threshold = float(th.get("melt_up_rsi_min", 75.0))

    cs = _closes(bars)
    if len(cs) < 15 + lookback:
        return None
    hits = 0
    for k in range(lookback):
        r = latest_rsi(cs[:len(cs) - k])
        if r is None or r.get("value") is None:
            return None
        if r["value"] >= threshold:
            if not v21:
                return True
            hits += 1
    return hits if v21 else False


def _ma50_rising(bars: Sequence[Bar]) -> Optional[bool]:
    """Is the 50dma higher than it was 10 sessions ago? None when either end is unavailable."""
    cs = _closes(bars)
    if len(cs) < 60:
        return None
    now = latest_moving_averages(cs)["sma"]["50"]
    then = latest_moving_averages(cs[:-10])["sma"]["50"]
    if now is None or then is None:
        return None
    return now > then


def sessions_from_series(series: Dict[str, List[Bar]], *,
                         settled_through: Optional[str] = None,
                         overlays: Optional[Dict[str, Any]] = None,
                         lenses: Optional[Dict[str, Any]] = None,
                         vix_by_date: Optional[Dict[str, Dict[str, Any]]] = None,
                         v2: bool = False,
                         rules_version: Optional[str] = None) -> List[Dict[str, Any]]:
    """Every classifiable session in `series`, oldest-first, each as a complete inputs dict.

    `settled_through` is the last session known to be settled; later sessions are marked unsettled
    and the classifier refuses them. Passing None marks every session settled, which is correct
    for a backfill of closes that are all in the past.
    """
    spy = series.get("SPY") or []
    out: List[Dict[str, Any]] = []
    prior: Optional[str] = None
    for i in range(len(spy)):
        day = _day(spy[i].date)
        settled = True if settled_through is None else (day is not None and day <= settled_through)
        row = build_inputs(series, i, settled=settled, overlays=overlays, lenses=lenses,
                           prior_regime=prior, rules_version=rules_version)
        if row is None:
            continue
        if v2:
            # R-IV.1260(c): v2's bar-derived inputs, which the v1 rows already read by name.
            # The two STATEFUL ones -- prior_regime and sessions_since_crash -- are NOT set
            # here: this module must not import the classifier, so it cannot know a label. The
            # replay injects them as it walks, which is what the comment below always claimed.
            from models.regime_classifier import RULES_VERSION, load_rules
            from models.regime_inputs_v2 import fill as _fill_v2

            # THE RULES FILE MUST MATCH THE VERSION BEING COMPUTED. Loading v2's thresholds
            # while computing v2.1 would gate the fixes off inside `_fill_v2` (which reads the
            # version off the rules it is handed) and silently compute a third thing that is
            # neither version.
            _fill_v2(row, series, i, rules=load_rules(rules_version or RULES_VERSION),
                     vix=(vix_by_date or {}).get(_day(spy[i].date)),
                     window_dates=[b.date for b in spy[:i + 1]])
        out.append(row)
        # The prior regime §2's Recovery row reads is the PREVIOUS session's label, which the
        # replay fills in as it goes. Left None here and set by the replay, because this module
        # must not import the classifier: the classifier reads these inputs.
    return out
