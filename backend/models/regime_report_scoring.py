"""The Regime Report Card's scoring, to QUERY's spec. R-IV.1321(b).

SPEC: `SPEC-REGIME-REPORT-CARD-v1-R-IV.1316.md`, sha256
dbe09fff0fb9c2507185411f43828e03796a18cd7125b9c14ae5aa2664bc7961 (28,146 bytes), verified
before use. Every P-item adopted (R-IV.1320).

THE HASH MOVED (R-IV.1332(b)). QUERY settled the empty state as "E1" and amended the spec IN
PLACE, so the adopted hash is now dbe09fff and the superseded 876a74b3 stays citable in the
spec's own section 14 change log. The pin is updated rather than kept "for continuity": a hash
that names a file nobody is working from is worse than no hash, because it reads as verified.

The spec is staged outside the repo and is not committed.

THE FINDING THAT SHAPES THE LAYOUT, which is QUERY's and not mine. Three of the four panels in
the original mock cannot mean anything for years, and the mock gave the most space to the
slowest one:

    flips per year                     ~1.3 years to a verdict
    the 200-day row (10 scored)        ~2.9 years
    worst-dip order, STRESS vs UP      ~5.3 years
    per-label share vs the base rate   ~14.6 years, and that is POOLED, not per label

So the order is inverted: flips and the 200-day row lead, the worst-dip ORDER panel is added
(P10 -- the only grading panel reachable this decade), and the per-label table becomes the
smallest element, DESCRIPTIVE ONLY with no verdict column.

AND `NOT REACHABLE AT THIS RATE` EXISTS BECAUSE AMBER LIES (P8). Without it, `range_chop` -- the
label the card is showing today -- sits "EARLY, too few to judge" for a decade while implying a
verdict is coming. Measured from R9's label frequencies, five independent windows in
`range_chop` needs ~8.4 years and in `bear_market_rally` ~79. Saying so is information: it tells
a reader which parts of this card will ever grade and which are permanently descriptive.

TWO PRICE BASES, AND THEY ARE NOT INTERCHANGEABLE (spec §1.2) -- "the single likeliest
implementation error, because one series would work everywhere":

    higher-20-sessions-later, worst dip   SPY FULLY ADJUSTED closes (splits AND dividends)
    the 200-day line, up-crosses, 60-session low   SPLIT-adjusted, DIVIDEND-UNADJUSTED

Mixing them makes the live figures incomparable with the base rates printed beside them. Each
figure carries its basis.

#42: nothing computes from any of this. No gate, no kill switch, no sizing, no routing. A test
asserts that nothing imports this module.
"""
from __future__ import annotations

import datetime as _dt
import math
from typing import Any, Dict, List, Optional, Sequence

#: Spec §1.1. The only version that may be scored, read from the rows rather than configured.
SCORED_VERSION = "v2.1"


#: R-IV.1354(b)2 / QUERY's P11, §1.1.1. The zone and hour a session CLOSES at. A session is in
#: scope iff its close is strictly after the cutover instant.
CLOSE_ZONE = "America/New_York"
CLOSE_HOUR = 16


def session_close(session) -> _dt.datetime:
    """The instant a session closed: 16:00 America/New_York on that date, DST-correct.

    THE ZONE IS RESOLVED FOR THAT DATE, which is the whole reason this is a function and not
    `date + "T20:00:00Z"`. The exchange closes at 16:00 LOCAL: 20:00Z under EDT and 21:00Z
    under EST, and the changeover falls in the first week of November -- inside the span this
    card will be scoring within two weeks. A fixed UTC offset would put every November session
    an hour early and, for a session closing in the hour either side of a cutover, on the wrong
    side of the boundary.

    COMPARED STRICTLY (`>`), per the spec: a session whose close EQUALS the instant did not
    close after it.
    """
    from zoneinfo import ZoneInfo

    d = session
    if not isinstance(d, _dt.date) or isinstance(d, _dt.datetime):
        d = _dt.date.fromisoformat(str(session)[:10])
    return _dt.datetime(d.year, d.month, d.day, CLOSE_HOUR, 0, tzinfo=ZoneInfo(CLOSE_ZONE))


def in_scope(session, cutover_instant) -> bool:
    """Whether `session` is scored. One predicate, so no caller can write its own.

    A row that is NOT in scope is neither deleted nor wrong -- it is a correct label of a
    session this card does not score, and `excluded_pre_cutover` is how the card says so out
    loud instead of silently dropping it.
    """
    if cutover_instant is None:
        return False          # unknown boundary scores NOTHING, never everything
    return session_close(session) > cutover_instant


#: R7. 20-session windows overlap, so about n/20 are independent. Every n is reported with its
#: independent count beside it, and no percentage is shown below one independent window.
WINDOW_SESSIONS = 20
INDEP_DIVISOR = 20

#: Spec §8, in INDEPENDENT WINDOWS, never in sessions -- except flips, which the spec states in
#: live sessions because its threshold comes from a Poisson power calculation.
MIN_INDEP_LABEL_SHARE = 20
MIN_INDEP_HELD = 10
MIN_SESSIONS_FLIPS = 333
MIN_SCORED_UPCROSSES = 10

#: P6. Below this many live sessions the annualised flip rate is shown grey: a rate extrapolated
#: from a few weeks is arithmetic, not evidence.
FLIPS_GREY_BELOW_SESSIONS = 126

#: P5a. A warning "held" if the forward-20 worst dip reaches the ALL-sessions median (R9).
WARNING_DIP_PCT = 3.09

#: P5b/R4. An all-clear "held" if no new 60-session closing low prints inside the window.
ALL_CLEAR_HORIZON = 60

#: §1.2, and I had this one WRONG. The all-clear test is R4/G4 -- "a new 60-session CLOSING
#: low" -- which the stamped section 6 defines on the SPLIT-ADJUSTED, DIVIDEND-UNADJUSTED
#: series, not the fully adjusted one. I had labelled it fully adjusted because it sits beside
#: the forward-20 figures, which IS the basis mixing §1.2 calls the likeliest error here.
#: QUERY's checker caught it.
BASIS_ALL_CLEAR = "SPY split-adjusted, dividend-unadjusted closes (R4/G4)"

#: R8/R-IV.1296 and the stated target.
HISTORY_FLIPS_PER_YEAR = 12.78
TARGET_FLIPS_PER_YEAR = 6.0

#: R10, adopted R-IV.1312(a).
WHIPSAW_HISTORY_2013 = 0.5000
WHIPSAW_HISTORY_1999 = 0.4479

#: P8. Beyond this the panel says so instead of sitting amber.
NOT_REACHABLE_YEARS = 10.0
SESSIONS_PER_YEAR = 252.0

#: The four verdict states (P7c + P8).
EARLY = "EARLY"
CONSISTENT = "CONSISTENT WITH HISTORY"
DEPARTS = "DEPARTS FROM HISTORY"
NOT_REACHABLE = "NOT REACHABLE AT THIS RATE"

#: Spec §1.2, carried on every figure (Convention #37).
BASIS_ADJUSTED = "SPY fully adjusted closes (splits and dividends)"
BASIS_SPLIT_ONLY = "SPY split-adjusted, dividend-unadjusted closes"

#: R9's two gaps. v2 never showed these, so a live session under one has NO base rate -- not 0%,
#: not a blank, not the group's rate.
NO_BASE_RATE = "no base rate (never shown 1999-2026)"


def indep(n: Optional[int]) -> Optional[float]:
    """Independent windows for `n` overlapping ones. R7: about n / 20.

    A RATIO, NOT A FLOOR. I floored it first, and QUERY's conformance checker caught that the
    floor THROWS AWAY THE FIGURE: 18 checked windows is 0.9 independent, and printing 0 reads
    as "none", which is a different claim. The suppression rule is unchanged -- no percentage
    below ONE independent window -- and 0.9 fails that test exactly as 0 did, while still
    telling a reader how close it is.
    """
    if n is None:
        return None
    return round(int(n) / float(INDEP_DIVISOR), 2)


def wilson95(k: int, n: int) -> Optional[Dict[str, float]]:
    """A Wilson 95% interval on k of n. P3.

    NOT the normal approximation: at the counts this card will carry for years, the normal
    interval runs past 0 and 1 and reports a width it has not earned. None below one
    observation -- "no percentage from fewer than one independent window" (spec §11.4).
    """
    if not n or n <= 0 or k < 0 or k > n:
        return None
    z = 1.959963984540054
    p = k / float(n)
    d = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / d
    half = (z / d) * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return {"lo": round(max(0.0, centre - half) * 100.0, 1),
            "hi": round(min(1.0, centre + half) * 100.0, 1),
            "half_width_pts": round(half * 100.0, 1)}


def years_to_threshold(have: float, need: float, per_year: Optional[float]) -> Optional[float]:
    """How long at the OBSERVED accrual rate, or None when it cannot be estimated. P8."""
    if per_year is None or per_year <= 0:
        return None
    missing = need - have
    if missing <= 0:
        return 0.0
    return missing / per_year


def verdict(have: float, need: float, *, per_year: Optional[float] = None,
            live: Optional[float] = None, history: Optional[float] = None,
            higher_is_departure: bool = True) -> Dict[str, Any]:
    """One panel's verdict, in the four-state vocabulary. P7c + P8.

    BELOW THRESHOLD IS NOT AUTOMATICALLY `EARLY`. If the threshold is more than ten years away
    at the rate the data is actually arriving, the honest state is NOT REACHABLE and the wait is
    printed. An amber "too few to judge" on a panel that will never judge tells a reader to keep
    waiting for something that is not coming.
    """
    if have >= need:
        if live is None or history is None:
            return {"state": CONSISTENT, "text": CONSISTENT,
                    "reason": "at or above the minimum count"}
        pts = round(live - history, 1)
        departs = abs(pts) >= 10.0
        if not departs:
            return {"state": CONSISTENT,
                    "text": "%s (%+.1f pts)" % (CONSISTENT, pts),
                    "reason": "within 10 points of the base rate"}
        direction = "higher" if pts > 0 else "lower"
        return {"state": DEPARTS,
                "text": "%s (%s, %+.1f pts)" % (DEPARTS, direction, pts),
                "reason": "10 points or more from the base rate"}

    yrs = years_to_threshold(have, need, per_year)
    if yrs is not None and yrs > NOT_REACHABLE_YEARS:
        return {"state": NOT_REACHABLE,
                "text": "%s · ~%d yrs at this rate" % (NOT_REACHABLE, round(yrs)),
                "reason": "the threshold is more than %d years away at the observed rate"
                          % int(NOT_REACHABLE_YEARS),
                "years": round(yrs, 1)}
    return {"state": EARLY,
            "text": "%s · %d of %d" % (EARLY, int(have), int(need)),
            "reason": "below the minimum count, which is reachable",
            "years": None if yrs is None else round(yrs, 1)}


# ── the panels ──────────────────────────────────────────────────────────────

def flips_panel(shown: Sequence[Optional[str]], *, days_span: Optional[float] = None,
                sessions: Optional[int] = None) -> Dict[str, Any]:
    """R8. A change of `shown_regime` between consecutive sessions, BOTH non-null. Tags never
    count. Leads the card because it pays off first (~1.3 years) and is the one figure with a
    stated target.
    """
    n = len(shown) if sessions is None else sessions
    flips = 0
    for a, b in zip(shown, list(shown)[1:]):
        if a is not None and b is not None and a != b:
            flips += 1
    years = None if not days_span else days_span / 365.25
    per_year = None if not years else round(flips / years, 2)
    return {
        "flips": flips,
        "sessions": n,
        "years": None if years is None else round(years, 2),
        "per_year": per_year,
        # P6: an annualised rate from under half a year is arithmetic, not evidence.
        "annualised_is_grey": bool(n < FLIPS_GREY_BELOW_SESSIONS),
        "history_per_year": HISTORY_FLIPS_PER_YEAR,
        "target_per_year": TARGET_FLIPS_PER_YEAR,
        "min_sessions": MIN_SESSIONS_FLIPS,
        "verdict": verdict(n, MIN_SESSIONS_FLIPS, per_year=SESSIONS_PER_YEAR,
                           live=per_year, history=HISTORY_FLIPS_PER_YEAR,
                           higher_is_departure=True),
        "basis": "shown_regime transitions; tags never count (R8)",
    }


def ma200_panel(up_crosses: int = 0, scored: int = 0, whipsaws: int = 0,
                pending: Optional[int] = None) -> Dict[str, Any]:
    """P7, the spec's own highest-risk item: UP-CROSSES / SCORED / PENDING, never a bare count.

    "whipsaws: 0" is ambiguous in the worst way -- it reads as "none went wrong" when it usually
    means "none has finished its 60-session window yet". The three counts separate "it has not
    happened" from "it cannot be known yet", and the share is computed over SCORED only.
    """
    pend = (up_crosses - scored) if pending is None else pending
    share = None if scored <= 0 else round(whipsaws / float(scored) * 100.0, 1)
    return {
        "up_crosses": up_crosses,
        "scored": scored,
        "pending": max(0, pend),
        "whipsaws": whipsaws if scored > 0 else None,
        "share": share,
        "ci95": wilson95(whipsaws, scored) if scored > 0 else None,
        "history_2013_pct": round(WHIPSAW_HISTORY_2013 * 100.0, 2),
        "history_1999_pct": round(WHIPSAW_HISTORY_1999 * 100.0, 2),
        "min_scored": MIN_SCORED_UPCROSSES,
        "verdict": verdict(scored, MIN_SCORED_UPCROSSES, per_year=3.5,
                           live=share, history=WHIPSAW_HISTORY_2013 * 100.0),
        # P7b: the yardstick, not a fifth score.
        "caption": "the yardstick the labels are measured against, not a fifth score",
        "basis": BASIS_SPLIT_ONLY,
    }


def dip_order_panel(stress_dips: Sequence[float], up_dips: Sequence[float]) -> Dict[str, Any]:
    """P10. Does TREND-DOWN/STRESS's median forward-20 worst dip exceed TREND-UP's?

    Added by the spec and absent from the mock, and it is the most informative thing reachable
    in under a decade (~5.3 years): a one-line restatement of T1's order limb on live data. It
    needs no per-label counts, only two groups.
    """
    def med(xs):
        xs = sorted(float(x) for x in xs if x is not None)
        if not xs:
            return None
        mid = len(xs) // 2
        return round(xs[mid] if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2.0, 2)

    s_med, u_med = med(stress_dips), med(up_dips)
    i_s, i_u = indep(len(stress_dips)), indep(len(up_dips))
    holds = None if (s_med is None or u_med is None) else bool(s_med > u_med)
    have = min(i_s or 0, i_u or 0)
    return {
        "stress_dip_median": s_med,
        "up_dip_median": u_med,
        "n_stress": len(stress_dips), "n_up": len(up_dips),
        "indep_stress": i_s, "indep_up": i_u,
        "order_holds": holds,
        "min_indep": MIN_INDEP_HELD,
        "verdict": verdict(have, MIN_INDEP_HELD, per_year=SESSIONS_PER_YEAR / INDEP_DIVISOR),
        "question": "does STRESS's median forward-20 dip exceed UP's?",
        "basis": BASIS_ADJUSTED,
    }


def label_rows(per_label: Dict[str, Dict[str, Any]],
               label_to_group: Dict[str, str]) -> List[Dict[str, Any]]:
    """The per-label table: DESCRIPTIVE ONLY, no verdict column (R-IV.1321(b)).

    The smallest element on the card, because a pooled verdict here is ~14.6 years away and a
    per-label one is further. Each row still carries its n, its independent-window count and the
    base rate beside it -- description from day one -- and `NOT REACHABLE AT THIS RATE` where
    the label's own frequency says the count will never arrive.

    R9's gap is honoured: `melt_up` and `crash_liquidation` have no base rate at all (v2 never
    showed them, and v2.1 made the melt-up row reachable), so they print the sentence rather
    than a number, a blank, or the group's rate.
    """
    from models.regime_drift_prior import BY_LABEL

    out: List[Dict[str, Any]] = []
    for label, got in per_label.items():
        sessions = int(got.get("sessions") or 0)
        checked = int(got.get("checked") or 0)
        higher = got.get("higher")
        k = indep(checked)
        hist = BY_LABEL.get(label)
        share = None
        if checked > 0 and higher is not None and k and k >= 1:
            share = round(higher / float(checked) * 100.0, 1)
        out.append({
            "label": label,
            "group": label_to_group.get(label),
            "sessions": sessions,
            "checked": checked,
            "pending": max(0, sessions - checked),
            "indep": k,
            "share_higher": share,
            "share_higher_ci95": wilson95(int(higher or 0), checked) if checked else None,
            "worst_dip_median": got.get("worst_dip_median"),
            # R9's gap, said out loud.
            "history_available": hist is not None,
            "history_share": None if hist is None else hist["higher_pct"],
            "history_dip": None if hist is None else hist["worst_dip_pct"],
            "history_n": None if hist is None else hist["n"],
            "history_note": None if hist is not None else NO_BASE_RATE,
            # Descriptive only: the reachability note replaces a verdict, it is not one.
            "reach": _reach_note(label, k),
            "basis": BASIS_ADJUSTED,
        })
    return out


#: Share of sessions per label, from R9's n's -- used only to say how far off a count is.
_LABEL_SHARE = {"uptrend": 0.358, "correction": 0.226, "bear_market": 0.204,
                "breakdown": 0.076, "narrow_uptrend": 0.061, "range_chop": 0.047,
                "recovery": 0.018, "bear_market_rally": 0.005}


def _reach_note(label: str, have_indep: Optional[int]) -> Optional[Dict[str, Any]]:
    """`NOT REACHABLE AT THIS RATE` where the label's own frequency says so. P8."""
    share = _LABEL_SHARE.get(label)
    if share is None or not share:
        return None
    have = have_indep or 0
    if have >= MIN_INDEP_LABEL_SHARE:
        return None
    need_sessions = (MIN_INDEP_LABEL_SHARE - have) * INDEP_DIVISOR / share
    yrs = need_sessions / SESSIONS_PER_YEAR
    if yrs > NOT_REACHABLE_YEARS:
        return {"state": NOT_REACHABLE, "years": round(yrs, 1),
                "text": "%s · ~%d yrs" % (NOT_REACHABLE, round(yrs))}
    return {"state": EARLY, "years": round(yrs, 1),
            "text": "%s · %d of %d" % (EARLY, have, MIN_INDEP_LABEL_SHARE)}


def score_sessions(sessions: Sequence[Dict[str, Any]], adj_rows: Sequence[Dict[str, Any]],
                   label_to_group: Dict[str, str],
                   horizon: int = WINDOW_SESSIONS) -> Dict[str, Any]:
    """Score the live sessions against the fully adjusted series. R-IV.1327(b).

    `sessions` is `[{as_of, shown_regime}]`, oldest-first, v2.1 only. `adj_rows` is
    `integrations.spy_adjusted_closes.closes()["rows"]` -- the series MATCHED to LAB's
    drift-prior pull, which is the only reason the live shares can sit beside its base rates.

    A SESSION IS "CHECKED" ONLY WHEN ITS WHOLE WINDOW EXISTS (P1). A label with 30 sessions and
    11 complete windows reports 11 checked and 19 pending -- never 30 scored off partial data,
    which would be a different quantity under the same name.
    """
    from integrations.spy_adjusted_closes import forward_outcome

    by_date = {r["date"]: i for i, r in enumerate(adj_rows)}
    per: Dict[str, Dict[str, Any]] = {}
    dips_by_group: Dict[str, List[float]] = {}
    warn_checked = warn_held = warn_pending = 0
    checked_total = 0

    for row in sessions:
        label = row.get("shown_regime")
        if not label:
            continue
        slot = per.setdefault(label, {"sessions": 0, "checked": 0, "higher": 0, "dips": []})
        slot["sessions"] += 1
        i = by_date.get(str(row.get("as_of"))[:10])
        out = None if i is None else forward_outcome(list(adj_rows), i, horizon)
        group = label_to_group.get(label)
        if out is None:
            # NOT YET KNOWABLE. Counted as pending, never as a zero.
            if group in ("TREND-DOWN/STRESS", "TREND-UP"):
                pass
            if group == "TREND-DOWN/STRESS":
                warn_pending += 1
            continue
        slot["checked"] += 1
        checked_total += 1
        if out["higher"]:
            slot["higher"] += 1
        slot["dips"].append(out["worst_dip_pct"])
        if group:
            dips_by_group.setdefault(group, []).append(out["worst_dip_pct"])
        # P5a: a "warning" is a STRESS label, and it HELD if the forward-20 dip reached the
        # registered ALL-sessions median.
        if group == "TREND-DOWN/STRESS":
            warn_checked += 1
            if out["worst_dip_pct"] >= WARNING_DIP_PCT:
                warn_held += 1

    def med(xs):
        xs = sorted(xs)
        if not xs:
            return None
        m = len(xs) // 2
        return round(xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2.0, 2)

    for slot in per.values():
        slot["worst_dip_median"] = med(slot.pop("dips"))

    return {
        "per_label": per,
        "checked_total": checked_total,
        "dips_by_group": dips_by_group,
        "warnings": {"checked": warn_checked, "held": warn_held, "pending": warn_pending,
                     "share": (None if warn_checked <= 0
                               else round(warn_held / float(warn_checked) * 100.0, 1)),
                     "threshold_pct": WARNING_DIP_PCT,
                     "min_indep": MIN_INDEP_HELD,
                     "basis": BASIS_ADJUSTED},
    }

def calls_block(total: int, checked: int) -> Dict[str, Any]:
    """P1/P2: three counts, and `pending` is PRINTED rather than inferred by the reader.

    A card that showed "1 of 21" left the other 20 to be worked out, and "not yet knowable" and
    "nothing happened" look identical once a reader is doing arithmetic in their head.
    """
    total, checked = int(total or 0), int(checked or 0)
    return {"total": total, "checked": checked, "pending": max(0, total - checked),
            "horizon_sessions": WINDOW_SESSIONS}


def divergence_block(diverged: int = 0, checked: int = 0,
                     labels: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """P9: per-session v2-vs-v2.1 label divergence.

    The base rates were measured on V2's labels, and they are comparable to v2.1 only because
    the two were label-identical over the measured span (R-IV.1301). If that stops being true,
    the history column beside a diverged label is no longer the right yardstick -- so the count
    is recorded and a non-zero count suppresses that label's history column and says why.
    """
    labs = sorted(set(labels or ()))
    return {
        "sessions_compared": int(checked or 0),
        "diverged": int(diverged or 0),
        "labels": labs,
        "suppress_history_for": labs if diverged else [],
        "note": ("the base rates were measured on v2 labels and hold for v2.1 only while the "
                 "two agree (R-IV.1301); a diverged label loses its history column"),
    }

def empty_card(reason: str) -> Dict[str, Any]:
    """Every panel in its empty state, with one reason. R-IV.1321(b).

    THIS IS THE STATE TODAY and it is not a failure: `RULES_VERSION` is still "v2" on main, the
    cutover is on its branch awaiting deploy, and the card scores post-cutover sessions ONLY and
    never backfills. So there is nothing to score yet, and the panels say that rather than
    showing zeroes -- a zero here would read as "measured, and it was nil".
    """
    return {
        "available": False,
        "reason": reason,
        "scope": {"first_session": None, "sessions": 0, "rules_version": SCORED_VERSION,
                  "backfilled": False},
        "display_only": "display only (#42)",
        "calls": calls_block(0, 0),
        "v2_divergence": divergence_block(),
        # THE PANELS ARE PRESENT AND EMPTY, NOT ABSENT. I had them as None, and QUERY's
        # checker was right to flag it: "the worst-dip ORDER panel is required" means the panel
        # must be ON THE CARD, and a panel that vanishes when it has nothing to say takes its
        # own absence with it. An empty panel states that it is empty; a missing one states
        # nothing, and a reader cannot tell it was ever meant to be there.
        # THE KEYS ARE ALWAYS PRESENT, and the two HISTORY figures are present with VALUES:
        # 12.78/yr and the target of 6 are registered constants, true before a single session
        # is scored. Only the live counts are None. A panel that withheld the target as well
        # would be hiding the thing the live number will be read against.
        "flips": {"available": False, "reason": reason,
                  "flips": None, "sessions": 0, "per_year": None,
                  "annualised_is_grey": True,
                  "history_per_year": HISTORY_FLIPS_PER_YEAR,
                  "target_per_year": TARGET_FLIPS_PER_YEAR,
                  "min_sessions": MIN_SESSIONS_FLIPS,
                  "basis": "shown_regime transitions; tags never count (R8)"},
        "ma200": {"available": False, "reason": reason,
                  "up_crosses": None, "scored": None, "pending": None, "whipsaws": None,
                  "basis": BASIS_SPLIT_ONLY},
        "dip_order": {"available": False, "reason": reason, "basis": BASIS_ADJUSTED,
                      "question": "does STRESS's median forward-20 dip exceed UP's?"},
        "warnings_held": {"available": False, "reason": reason, "pending": None,
                          "threshold_pct": WARNING_DIP_PCT, "basis": BASIS_ADJUSTED},
        "all_clears_held": {"available": False, "reason": reason, "pending": None,
                            "horizon_sessions": ALL_CLEAR_HORIZON,
                            "basis": BASIS_ALL_CLEAR},
        "by_label": [],
    }
