"""The v1 regime classifier — §2 of the registered doc, as a pure function.

R-IV.1193(d). The ten base regimes, checked TOP-DOWN with FIRST MATCH WINS, from settled closes
only. `market_state` (fix-first #5) is the structure input.

PURE: no clock, no network, no database. Everything it needs arrives in one `inputs` dict and
everything it decides comes back in one verdict dict. That is what makes the dry run meaningful
-- a classifier that reached for its own data could not be handed 10-16 and asked what it would
have said.

THREE PROPERTIES THAT MATTER MORE THAN THE RULES THEMSELVES:

  1. AN UNTESTABLE ROW IS "NOT EVALUABLE", NEVER "NO". Row 1 (Crash) has a HARD REQUIREMENT --
     VIX above VIX3M on a close -- and v1 has no VIX series. Returning "not a crash" from a test
     that never ran would be the worst answer this module could give, so the row records
     NOT_EVALUABLE, the scan continues, and the verdict carries that caveat to the card. §5 shows
     exactly this on the 10-16 state.

  2. A MISSING INPUT STOPS ITS OWN ROW, NOT THE WHOLE SCAN. Each row states which inputs it
     needs; absent one, that row is NOT_EVALUABLE and the next is tried. A row that silently
     read a missing input as zero would match on arithmetic over nothing.

  3. THE BASIS IS PART OF THE VERDICT. Every row that matches says which clause of §2 fired and
     with what numbers, because "CORRECTION" with no working is a label a reader has to take on
     trust -- and the whole module is built not to ask for that.

DISPLAY ONLY (#42, §1). The label drives the card. Nothing gates on it, and this module is
deliberately given no way to write anything.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

#: THE CUTOVER. R-IV.1303(c) / R-IV.1307(c), after QUERY cleared c7261e90 under R-IV.1301(b).
#:
#: v2.1 inherits v2's shown label and hysteresis state; it does NOT re-seed and does NOT replay
#: any era (registration section 1 / R-IV.1277(b) item 7). `cutover_state` verifies the
#: inheritance by RECOMPUTING v2's anchor session and comparing all four counters, and REFUSES
#: rather than carrying on if they differ -- measured against row 929 (2026-10-20): shown
#: range_chop, held 5, pending correction, pending_closes 3, all four agreeing.
RULES_VERSION = "v2.1"
_RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "config", "regime_rules.%s.json" % RULES_VERSION)

NOT_EVALUABLE = "NOT_EVALUABLE"


def load_rules(version: str = RULES_VERSION) -> Dict[str, Any]:
    """The versioned rules file. §8 requires the hysteresis to live in one, and the thresholds
    belong beside it -- a threshold in code and a threshold in a file is two places for one
    number."""
    path = os.path.join(os.path.dirname(_RULES_PATH), "regime_rules.%s.json" % version)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _f(v: Any) -> Optional[float]:
    """A float, or None. A non-finite value is None and never a number: `float('nan')` passes
    every `if not x` guard downstream, which is the fault the Triton grader paid for."""
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x not in (float("inf"), float("-inf")) else None


def _pct(a: Optional[float], b: Optional[float]) -> Optional[float]:
    """(a - b) / b as a percentage, or None when either side is missing."""
    if a is None or b is None or b == 0:
        return None
    return (a - b) / b * 100.0


class Row:
    """One §2 row's outcome: matched, not matched, or not evaluable -- and why."""

    __slots__ = ("key", "matched", "evaluable", "basis", "missing")

    def __init__(self, key, matched=False, evaluable=True, basis="", missing=None):
        self.key = key
        self.matched = matched
        self.evaluable = evaluable
        self.basis = basis
        self.missing = list(missing or [])

    def as_dict(self):
        return {"regime": self.key,
                "verdict": ("MATCH" if self.matched else
                            ("NO" if self.evaluable else NOT_EVALUABLE)),
                "basis": self.basis,
                "missing_inputs": self.missing}


def _need(inputs: Dict[str, Any], *paths) -> List[str]:
    """Which of these dotted input paths are missing. Named so a row can refuse by name.

    MISSING MEANS THE SAME THING HERE AS IN `_f`. A non-finite number is missing, not present:
    `float("nan")` is not None, so an earlier version let it past this check and the row then
    compared the None `_f` turned it into against a float. Two helpers disagreeing about the
    word "present" is how a NaN reaches arithmetic.

    A string is left alone -- `_f` would reject "bullish" too, and `stack_state` is a real input.
    """
    out = []
    for p in paths:
        cur: Any = inputs
        for part in p.split("."):
            cur = cur.get(part) if isinstance(cur, dict) else None
            if cur is None:
                break
        if cur is None:
            out.append(p)
        elif isinstance(cur, (int, float)) and not isinstance(cur, bool) and _f(cur) is None:
            out.append(p)
    return out


def _get(inputs: Dict[str, Any], path: str) -> Any:
    cur: Any = inputs
    for part in path.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
        if cur is None:
            return None
    return cur


# ── the ten rows, in §2's order ──────────────────────────────────────────────

def _row_crash(inputs, th) -> Row:
    """Row 1. HARD REQUIREMENT: VIX above VIX3M on a close, AND >= 3 of 5 families.

    v1 has no VIX series, so this row is NOT EVALUABLE and the scan continues. It must never
    return "no" -- a crash check that never ran is not a crash check that passed.
    """
    missing = _need(inputs, "vix.vix", "vix.vix3m")
    if missing:
        return Row("crash_liquidation", evaluable=False, missing=missing,
                   basis="the hard requirement (VIX above VIX3M on a close) cannot be tested "
                         "without a raw VIX/VIX3M series, so this row is not evaluable and is "
                         "NOT read as 'not a crash'")
    vix, v3 = _f(_get(inputs, "vix.vix")), _f(_get(inputs, "vix.vix3m"))
    if not (vix > v3):
        return Row("crash_liquidation",
                   basis="VIX %.2f is not above VIX3M %.2f, so the hard requirement fails"
                         % (vix, v3))
    fams = _get(inputs, "families") or {}
    hit = [k for k, v in fams.items() if v is True]
    need = int(th["crash_families_required"])
    if len(hit) >= need:
        return Row("crash_liquidation", matched=True,
                   basis="backwardation on the close, and %d of %d families: %s"
                         % (len(hit), int(th["crash_families_total"]), ", ".join(sorted(hit))))
    return Row("crash_liquidation",
               basis="backwardation holds but only %d of %d families (need %d)"
                     % (len(hit), int(th["crash_families_total"]), need))


def _row_bear(inputs, th) -> Row:
    """Row 2. SPY 50dma below its 200dma, AND (>=20% below the 52w high OR 15 closes below a
    falling 200dma)."""
    missing = _need(inputs, "spy.ma50", "spy.ma200")
    if missing:
        return Row("bear_market", evaluable=False, missing=missing)
    ma50, ma200 = _f(_get(inputs, "spy.ma50")), _f(_get(inputs, "spy.ma200"))
    if not (ma50 < ma200):
        return Row("bear_market",
                   basis="the SPY 50dma (%.2f) is not below its 200dma (%.2f)" % (ma50, ma200))
    off = _f(_get(inputs, "spy.pct_below_52w_high"))
    closes = _f(_get(inputs, "spy.closes_below_falling_200dma"))
    if off is not None and off >= th["bear_pct_below_52w_high"]:
        return Row("bear_market", matched=True,
                   basis="50dma below 200dma and %.1f%% below the 52-week high" % off)
    if closes is not None and closes >= th["bear_closes_below_falling_200dma"]:
        return Row("bear_market", matched=True,
                   basis="50dma below 200dma and %d closes below a falling 200dma" % int(closes))
    if off is None and closes is None:
        return Row("bear_market", evaluable=False,
                   missing=["spy.pct_below_52w_high", "spy.closes_below_falling_200dma"],
                   basis="the 50dma is below the 200dma, but neither second condition can be "
                         "tested")
    return Row("bear_market",
               basis="50dma below 200dma, but neither second condition is met")


def _row_bear_rally(inputs, th) -> Row:
    """Row 3. In Bear, or within 30 sessions of Crash: 2 closes above the 20dma and 50dma while
    still below a falling 200dma."""
    prior = _get(inputs, "prior_regime")
    since_crash = _f(_get(inputs, "sessions_since_crash"))
    in_scope = (prior == "bear_market") or (
        since_crash is not None and since_crash <= th["bear_rally_sessions_after_crash"])
    if not in_scope:
        return Row("bear_market_rally",
                   basis="not in Bear and not within %d sessions of a Crash"
                         % int(th["bear_rally_sessions_after_crash"]))
    missing = _need(inputs, "spy.closes_above_20_and_50", "spy.below_falling_200dma")
    if missing:
        return Row("bear_market_rally", evaluable=False, missing=missing)
    n = _f(_get(inputs, "spy.closes_above_20_and_50"))
    if n >= th["bear_rally_closes_above_20_and_50"] and _get(inputs, "spy.below_falling_200dma"):
        return Row("bear_market_rally", matched=True,
                   basis="%d closes above the 20dma and 50dma while below a falling 200dma"
                         % int(n))
    return Row("bear_market_rally", basis="the rally test is not met")


def _row_breakdown(inputs, th) -> Row:
    """Row 4. A confirmed downside break of the 50dma, AND (close below the 200dma OR the 50dma
    falling), with Bear not yet met."""
    missing = _need(inputs, "spy.confirmed_break_down_50dma")
    if missing:
        return Row("breakdown", evaluable=False, missing=missing)
    if not _get(inputs, "spy.confirmed_break_down_50dma"):
        return Row("breakdown", basis="no confirmed downside break of the SPY 50dma (C5's test: "
                                      "2 closes through, the stack turning, RVOL >= 1.2)")
    price, ma200 = _f(_get(inputs, "spy.price")), _f(_get(inputs, "spy.ma200"))
    falling = _get(inputs, "spy.ma50_falling")
    below = price is not None and ma200 is not None and price < ma200
    if below or falling is True:
        return Row("breakdown", matched=True,
                   basis="confirmed 50dma break, and " + ("the close is below the 200dma"
                                                          if below else "the 50dma is falling"))
    if falling is None and not below:
        return Row("breakdown", evaluable=False, missing=["spy.ma50_falling"],
                   basis="the break is confirmed but the second condition cannot be tested")
    return Row("breakdown", basis="the break is confirmed but neither second condition holds")


def _row_recovery(inputs, th) -> Row:
    """Row 5. Coming out of 1-4: a confirmed upside break of the 50dma with the 20dma crossing
    above the 50dma, OR a breadth thrust plus a close above the 50dma."""
    prior = _get(inputs, "prior_regime")
    coming_out = prior in ("crash_liquidation", "bear_market", "bear_market_rally", "breakdown")
    if not coming_out:
        return Row("recovery",
                   basis="the prior regime is %r, not one of rows 1-4" % (prior,))
    up = _get(inputs, "spy.confirmed_break_up_50dma")
    cross = _get(inputs, "spy.ma20_crossed_above_ma50")
    thrust = _get(inputs, "breadth.thrust")
    price, ma50 = _f(_get(inputs, "spy.price")), _f(_get(inputs, "spy.ma50"))
    above = price is not None and ma50 is not None and price > ma50
    if up and cross:
        return Row("recovery", matched=True,
                   basis="confirmed upside 50dma break with the 20dma crossing above the 50dma")
    if thrust and above:
        return Row("recovery", matched=True,
                   basis="a breadth thrust with the close above the 50dma")
    if up is None and thrust is None:
        return Row("recovery", evaluable=False,
                   missing=["spy.confirmed_break_up_50dma", "breadth.thrust"])
    return Row("recovery", basis="neither recovery entry is met")


def _row_correction(inputs, th) -> Row:
    """Row 6. SPY below its 50dma but above its 200dma, with the 50dma above the 200dma. OR SPY
    in Range/Uptrend while >= 2 of 3 indices are below their 50dma."""
    missing = _need(inputs, "spy.price", "spy.ma50", "spy.ma200")
    if missing:
        return Row("correction", evaluable=False, missing=missing)
    price = _f(_get(inputs, "spy.price"))
    ma50 = _f(_get(inputs, "spy.ma50"))
    ma200 = _f(_get(inputs, "spy.ma200"))
    if price < ma50 and price > ma200 and ma50 > ma200:
        return Row("correction", matched=True,
                   basis="SPY %.2f is below its 50dma %.2f and above its 200dma %.2f, with the "
                         "50dma above the 200dma" % (price, ma50, ma200))
    below = [t for t, d in (_get(inputs, "indices") or {}).items()
             if _f(d.get("price")) is not None and _f(d.get("ma50")) is not None
             and _f(d.get("price")) < _f(d.get("ma50"))]
    structure = _get(inputs, "spy.market_state")
    if structure in ("range", "trend") and len(below) >= th["correction_indices_below_50dma"]:
        return Row("correction", matched=True,
                   basis="SPY structure is %r while %d of 3 indices are below their 50dma (%s)"
                         % (structure, len(below), ", ".join(sorted(below))))
    return Row("correction",
               basis="SPY is not below its 50dma while above a rising-stacked 200dma, and the "
                     "index clause does not hold (%d below their 50dma)" % len(below))


def _row_range(inputs, th) -> Row:
    """Row 7. SPY ADX below 20 (20-25 keeps the prior state) for >= 10 sessions, the close within
    +/-3% of the 50dma, and fewer than 2 of 3 indices below their 50dma."""
    missing = _need(inputs, "spy.adx", "spy.price", "spy.ma50")
    if missing:
        return Row("range_chop", evaluable=False, missing=missing)
    adx = _f(_get(inputs, "spy.adx"))
    if adx >= th["range_adx_below"]:
        return Row("range_chop", basis="SPY ADX %.1f is not below %.0f"
                                       % (adx, th["range_adx_below"]))
    sessions = _f(_get(inputs, "spy.adx_below_20_sessions"))
    if sessions is None:
        return Row("range_chop", evaluable=False, missing=["spy.adx_below_20_sessions"],
                   basis="ADX is below %.0f but the %d-session requirement cannot be tested"
                         % (th["range_adx_below"], int(th["range_min_sessions"])))
    if sessions < th["range_min_sessions"]:
        return Row("range_chop", basis="ADX below %.0f for only %d of the required %d sessions"
                                       % (th["range_adx_below"], int(sessions),
                                          int(th["range_min_sessions"])))
    dist = abs(_pct(_f(_get(inputs, "spy.price")), _f(_get(inputs, "spy.ma50"))) or 0.0)
    if dist > th["range_within_pct_of_50dma"]:
        return Row("range_chop", basis="the close is %.1f%% from the 50dma, outside +/-%.0f%%"
                                       % (dist, th["range_within_pct_of_50dma"]))
    below = [t for t, d in (_get(inputs, "indices") or {}).items()
             if _f(d.get("price")) is not None and _f(d.get("ma50")) is not None
             and _f(d.get("price")) < _f(d.get("ma50"))]
    if len(below) >= th["correction_indices_below_50dma"]:
        return Row("range_chop", basis="%d of 3 indices are below their 50dma, which is Range's "
                                       "disqualifier" % len(below))
    return Row("range_chop", matched=True,
               basis="ADX %.1f below %.0f for %d sessions, close %.1f%% from the 50dma, and "
                     "fewer than %d indices below theirs"
                     % (adx, th["range_adx_below"], int(sessions), dist,
                        int(th["correction_indices_below_50dma"])))


def _row_melt_up(inputs, th) -> Row:
    """Row 8. Uptrend conditions, AND SPY >= 12% above its 200dma, AND RSI(14) >= 75 on 2 of the
    last 5 closes."""
    up = _row_uptrend(inputs, th)
    if not up.matched:
        return Row("melt_up", evaluable=up.evaluable, missing=up.missing,
                   basis="uptrend conditions are not met, so melt-up cannot be")
    ext = _pct(_f(_get(inputs, "spy.price")), _f(_get(inputs, "spy.ma200")))
    hits = _f(_get(inputs, "spy.rsi_ge_75_of_last_5"))
    if ext is None or hits is None:
        return Row("melt_up", evaluable=False,
                   missing=_need(inputs, "spy.price", "spy.ma200", "spy.rsi_ge_75_of_last_5"))
    if ext >= th["melt_up_pct_above_200dma"] and hits >= th["melt_up_rsi_hits_of_last_5"]:
        return Row("melt_up", matched=True,
                   basis="uptrend, %.1f%% above the 200dma and RSI >= %.0f on %d of the last 5"
                         % (ext, th["melt_up_rsi_min"], int(hits)))
    return Row("melt_up", basis="uptrend, but %.1f%% above the 200dma with %d RSI hits"
                                % (ext, int(hits)))


def _row_uptrend(inputs, th) -> Row:
    """Row 9. SPY above a rising 50dma above the 200dma, IWM above its 50dma, and >= 5 of 11
    sector SPDRs above their 50dma."""
    missing = _need(inputs, "spy.price", "spy.ma50", "spy.ma200")
    if missing:
        return Row("uptrend", evaluable=False, missing=missing)
    price = _f(_get(inputs, "spy.price"))
    ma50 = _f(_get(inputs, "spy.ma50"))
    ma200 = _f(_get(inputs, "spy.ma200"))
    rising = _get(inputs, "spy.ma50_rising")
    if not (price > ma50 and ma50 > ma200):
        return Row("uptrend", basis="SPY %.2f is not above a 50dma %.2f above the 200dma %.2f"
                                    % (price, ma50, ma200))
    if rising is False:
        return Row("uptrend", basis="the SPY 50dma is not rising")
    iwm = (_get(inputs, "indices") or {}).get("IWM") or {}
    iwm_px, iwm_ma50 = _f(iwm.get("price")), _f(iwm.get("ma50"))
    sectors = _f(_get(inputs, "breadth.sectors_above_50dma"))
    if iwm_px is None or iwm_ma50 is None or sectors is None or rising is None:
        return Row("uptrend", evaluable=False,
                   missing=([] if rising is not None else ["spy.ma50_rising"])
                           + ([] if iwm_px is not None and iwm_ma50 is not None
                              else ["indices.IWM.price", "indices.IWM.ma50"])
                           + ([] if sectors is not None else ["breadth.sectors_above_50dma"]))
    if iwm_px > iwm_ma50 and sectors >= th["uptrend_sectors_above_50dma_min"]:
        return Row("uptrend", matched=True,
                   basis="SPY above a rising 50dma above the 200dma, IWM above its 50dma, and "
                         "%d of %d sectors above theirs"
                         % (int(sectors), int(th["uptrend_sectors_total"])))
    return Row("uptrend", basis="SPY qualifies but IWM above 50dma is %s and sectors are %d of %d"
                                % (iwm_px > iwm_ma50, int(sectors),
                                   int(th["uptrend_sectors_total"])))


def _row_narrow_uptrend(inputs, th) -> Row:
    """Row 10. Uptrend conditions for SPY, but IWM below its 50dma, OR <= 4 of 11 sectors above
    theirs, OR high-beta breadth below 40% above the 50dma."""
    missing = _need(inputs, "spy.price", "spy.ma50", "spy.ma200")
    if missing:
        return Row("narrow_uptrend", evaluable=False, missing=missing)
    price = _f(_get(inputs, "spy.price"))
    ma50 = _f(_get(inputs, "spy.ma50"))
    ma200 = _f(_get(inputs, "spy.ma200"))
    if not (price > ma50 and ma50 > ma200):
        return Row("narrow_uptrend",
                   basis="SPY does not hold uptrend conditions (%.2f vs 50dma %.2f vs 200dma "
                         "%.2f)" % (price, ma50, ma200))
    iwm = (_get(inputs, "indices") or {}).get("IWM") or {}
    iwm_below = (_f(iwm.get("price")) is not None and _f(iwm.get("ma50")) is not None
                 and _f(iwm.get("price")) < _f(iwm.get("ma50")))
    sectors = _f(_get(inputs, "breadth.sectors_above_50dma"))
    hb = _f(_get(inputs, "breadth.high_beta_above_50dma_pct"))
    reasons = []
    if iwm_below:
        reasons.append("IWM is below its 50dma")
    if sectors is not None and sectors <= th["narrow_uptrend_sectors_max"]:
        reasons.append("only %d of %d sectors are above theirs"
                       % (int(sectors), int(th["uptrend_sectors_total"])))
    if hb is not None and hb < th["narrow_uptrend_high_beta_breadth_below_pct"]:
        reasons.append("high-beta breadth is %.1f%%" % hb)
    if reasons:
        return Row("narrow_uptrend", matched=True,
                   basis="SPY holds uptrend conditions but " + "; ".join(reasons))
    if sectors is None and hb is None and not iwm_below:
        return Row("narrow_uptrend", evaluable=False,
                   missing=["breadth.sectors_above_50dma", "breadth.high_beta_above_50dma_pct"])
    return Row("narrow_uptrend", basis="SPY holds uptrend conditions and nothing narrows it")


_ROWS = {
    "crash_liquidation": _row_crash,
    "bear_market": _row_bear,
    "bear_market_rally": _row_bear_rally,
    "breakdown": _row_breakdown,
    "recovery": _row_recovery,
    "correction": _row_correction,
    "range_chop": _row_range,
    "melt_up": _row_melt_up,
    "uptrend": _row_uptrend,
    "narrow_uptrend": _row_narrow_uptrend,
}


# ── tags (§2: tags, not regimes) ────────────────────────────────────────────

def derive_tags(inputs: Dict[str, Any], regime: Optional[str], th) -> Dict[str, Any]:
    """`{tags, not_evaluable}`. A tag that cannot be tested is NOT absent -- it is named, so the
    card does not imply the market lacks a property nobody measured."""
    tags: List[str] = []
    unknown: List[str] = []

    off = _f(_get(inputs, "spy.pct_below_52w_high"))
    if regime == "correction":
        if off is None:
            unknown.append("narrow")
        elif off <= th["correction_narrow_within_pct_of_high"]:
            tags.append("narrow")

    credit = _get(inputs, "overlays.credit_stress")
    if credit in ("WATCH", "ACTIVE"):
        tags.append("credit-stress")
    elif credit is None:
        unknown.append("credit-stress")

    l1, l2 = _get(inputs, "lenses.macro"), _get(inputs, "lenses.watchlist")
    if l1 and l2 and l1 != l2:
        tags.append("lens-split")
    elif not l1 or not l2:
        unknown.append("lens-split")

    states = {t: (d or {}).get("market_state")
              for t, d in (_get(inputs, "indices") or {}).items()}
    known = [v for v in states.values() if v]
    if len(known) >= 2 and len(set(known)) > 1:
        tags.append("index-divergence")

    return {"tags": tags, "not_evaluable": unknown}


# ── the verdict ─────────────────────────────────────────────────────────────

def classify(inputs: Dict[str, Any], rules: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """§2's scan: top-down, first match wins, from settled closes only.

    `inputs["as_of"]` is echoed into the verdict rather than read from a clock -- R-IV.1193(d)
    requires each label to be stamped, and a pure function cannot stamp itself.

    `inputs["settled"]` must be True. A label computed from an unsettled session is the
    R-IV.1176 fault wearing a new hat, so it is refused outright rather than produced with a
    caveat nobody reads.
    """
    rules = rules or load_rules()
    th = rules["thresholds"]

    out: Dict[str, Any] = {
        "rules_version": rules["version"],
        "as_of": inputs.get("as_of"),
        "settled": bool(inputs.get("settled")),
        "regime": None,
        "label": None,
        "tags": [],
        "tags_not_evaluable": [],
        "basis": None,
        "rows": [],
        "not_evaluable_rows": [],
        "gating": rules["gating"],
    }

    if not inputs.get("settled"):
        out["basis"] = ("refused: the session is not settled. A label from an unsettled close is "
                        "the R-IV.1176 fault again, so none is produced.")
        return out

    for key in rules["order"]:
        row = _ROWS[key](inputs, th)
        out["rows"].append(row.as_dict())
        if not row.evaluable:
            out["not_evaluable_rows"].append(key)
        if row.matched:
            out["regime"] = key
            out["basis"] = row.basis
            break

    tg = derive_tags(inputs, out["regime"], th)
    out["tags"] = tg["tags"]
    out["tags_not_evaluable"] = tg["not_evaluable"]

    if out["regime"] is None:
        out["basis"] = ("no row matched. %d row(s) could not be evaluated: %s"
                        % (len(out["not_evaluable_rows"]),
                           ", ".join(out["not_evaluable_rows"]) or "none"))
    out["label"] = out["regime"].replace("_", " ").upper() if out["regime"] else None
    return out
