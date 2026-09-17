"""Acceptance test #2, live (R-IV.425(a), R-IV.428(d)): the six known-answer cases.

Each case has a MEASURED WRONG ANSWER from CC-QUERY's scope read (2026-09-17 03:02Z vintage).
The module passes a case when, on bars fetched now, it (1) applies the split-type factor the
case turns on, (2) verifies the entry against the anchor session, and (3) reports a return
that is not the wrong answer.

INDEPENDENCE, stated per case (Law 2):
  independent  the raw entry is a price recorded by another system at fire (KORU's UW
               spot_at_fire; CRWD's raw entry as measured) -- the conversion is tested
               against a number the vendor did not produce.
  mechanism    the raw entry is REBUILT from the fetched bars and the vendor's ratio, so the
               case tests the grading mechanism on real bars (ranges, calendar, walk), not the
               vendor's data. Stated so it is not read as more.
APH is a STORE case: a fresh fetch must be seam-free, and the detector must find the measured
seam pattern (0.491 / 1.981) when the store's mixed bases are laid onto real bars.

Network only (yfinance). No database is read or written.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List

from . import basis as B
from . import bars as bars_mod
from . import grade as G

UTC = timezone.utc


def _row(sid, ticker, direction, fired, entry, stop=None, target=None):
    return G.ShadowRow(sid, ticker, direction, fired, entry, stop, target, B.ENTRY_INTRADAY)


def _naive_ret(entry, exit_close, direction):
    raw = (exit_close / entry - 1) * 100
    return raw if G.direction_sign(direction) > 0 else -raw


def case_koru(s) -> Dict[str, Any]:
    """Triton 38201: BULL, fired 07-08, spot 504.50; 20-for-1, ex 07-15 = the grade date.
    Stored 1d/3d/5d: -94.35 / -95.85 / -95.23."""
    row = _row("38201", "KORU", "BULL", datetime(2026, 7, 8, 15, 0, tzinfo=UTC), 504.50)
    wrong = {1: -94.35, 3: -95.85, 5: -95.23}
    out = {"case": "KORU 38201", "independence": "independent (UW spot_at_fire)", "horizons": {}}
    ok = True
    for h, w in wrong.items():
        g = G.grade_return(row, s, h, date(2026, 9, 16))
        good = (g.status == G.GRADED and g.entry_factor == round(1 / 20, 8)
                and abs(g.ret_pct - w) > 50)
        ok &= good
        out["horizons"][h] = {"status": g.status, "reason": g.reason, "factor": g.entry_factor,
                              "ret_pct": g.ret_pct, "known_wrong": w, "pass": good}
    out["pass"] = ok
    return out


def case_crwd(s) -> Dict[str, Any]:
    """HG rows 8289...13265: raw entry ~455 on 04-27 against an adjusted close of 113.65;
    4-for-1, ex 07-02. Stored returns +/-70-78%."""
    row = _row("CRWD-0427", "CRWD", "LONG", datetime(2026, 4, 27, 17, 0, tzinfo=UTC), 455.0)
    g = G.grade_return(row, s, 5, date(2026, 9, 16))
    naive = _naive_ret(455.0, g.exit_price, "LONG") if g.exit_price else None
    good = g.status == G.GRADED and g.entry_factor == 0.25 and abs(g.ret_pct) < 40
    return {"case": "CRWD 04-27", "independence": "independent (raw entry as measured, approx.)",
            "factor": g.entry_factor, "ret_pct": g.ret_pct, "naive_ret_pct": naive,
            "reason": g.reason, "note": "the ex-date is after T+5 here: the SECOND window",
            "pass": good}


def case_bkng(s) -> Dict[str, Any]:
    """signal_forward_returns, 84 rows: 25-for-1, ex 04-06; stored ~ +96% (short-aligned).
    Split BETWEEN fire and exit."""
    fire = date(2026, 3, 30)
    raw = s.close(fire) * 25
    row = _row("BKNG-0330", "BKNG", "SHORT", datetime(2026, 3, 30, 19, 0, tzinfo=UTC), raw)
    g = G.grade_return(row, s, 5, date(2026, 9, 16))
    naive = _naive_ret(raw, g.exit_price, "SHORT") if g.exit_price else None
    good = (g.status == G.GRADED and g.entry_factor == round(1 / 25, 8)
            and naive is not None and naive > 90 and abs(g.ret_pct) < 30)
    return {"case": "BKNG 03-30", "independence": "mechanism", "factor": g.entry_factor,
            "ret_pct": g.ret_pct, "naive_ret_pct": naive, "known_wrong": "~ +96",
            "reason": g.reason, "pass": good}


def case_spgi(s) -> Dict[str, Any]:
    """HG 9193...13536: a 1.057 factor, ex 07-01 -- small enough to sit near a daily range.
    Positive: a raw entry carrying the factor must resolve to 1/1.057. Control: an entry that
    does NOT carry it (the HON shape) must resolve to 1."""
    fire = date(2026, 6, 24)
    on_basis = s.close(fire)
    fired = datetime(2026, 6, 24, 19, 55, tzinfo=UTC)
    pos = G.grade_return(_row("SPGI+", "SPGI", "LONG", fired, on_basis * 1.057), s, 5, date(2026, 9, 16))
    ctl = G.grade_return(_row("SPGI-", "SPGI", "LONG", fired, on_basis), s, 5, date(2026, 9, 16))
    good = (pos.status == G.GRADED and abs(pos.entry_factor - 1 / 1.057) < 1e-6
            and ctl.status == G.GRADED and ctl.entry_factor == 1.0
            and "unapplied_event_in_window" in ctl.flags)
    return {"case": "SPGI 06-24", "independence": "mechanism",
            "positive": {"factor": pos.entry_factor, "flags": pos.flags, "ret_pct": pos.ret_pct},
            "control": {"factor": ctl.entry_factor, "flags": ctl.flags, "ret_pct": ctl.ret_pct},
            "pass": good}


def case_fubo(s) -> Dict[str, Any]:
    """signal_outcomes: 1-for-12 reverse, ex 03-24; a walk graded STOPPED_OUT falsely."""
    fire = date(2026, 3, 17)
    raw = s.close(fire) / 12
    row = _row("FUBO-0317", "FUBO", "SHORT", datetime(2026, 3, 17, 19, 0, tzinfo=UTC),
               raw, stop=raw * 1.10, target=raw * 0.80)
    g = G.grade_walk(row, s, 10, date(2026, 9, 16))
    # the naive walk: raw levels against the adjusted bars stop out on the first bar
    first = s.bar(next(d for d in s.dates if d > fire))
    naive = "STOP" if first["h"] >= raw * 1.10 else "not stopped on bar 1"
    stop_on_basis = (g.basis.get("levels_on_basis") or {}).get("stop")
    good = (g.status == G.GRADED and abs(g.entry_factor - 12) < 1e-6 and naive == "STOP"
            and stop_on_basis is not None
            and abs(stop_on_basis / (s.close(fire) * 1.10) - 1) < 1e-6)
    return {"case": "FUBO 03-17", "independence": "mechanism", "factor": g.entry_factor,
            "stop_on_basis": stop_on_basis, "outcome": g.outcome, "r_multiple": g.r_multiple,
            "exit_session": g.target_session, "naive_outcome": naive, "pass": good}


def case_aph(s) -> Dict[str, Any]:
    """The STORE: APH 2-for-1, ex 09-03, applied to part of the stored series only;
    measured one-day ratios 0.491 (08-19 -> 08-20) and 1.981 (08-21 -> 08-24)."""
    closes = {d: s.close(d) for d in s.dates if date(2026, 8, 1) <= d <= date(2026, 9, 10)}
    fresh = [st for st in B.find_steps(closes, s.splits) if st.kind == "adjustment_seam"]
    # lay the measured basis pattern onto real bars: 08-20 and 08-21 on the new basis,
    # everything else on the pre-action basis (x2)
    new_basis = {date(2026, 8, 20), date(2026, 8, 21)}
    mixed = {d: (c if d in new_basis else c * 2) for d, c in closes.items() if d < date(2026, 9, 3)}
    found = [st for st in B.find_steps(mixed, s.splits) if st.kind == "adjustment_seam"]
    where = sorted((st.before.isoformat(), st.after.isoformat(), st.ratio) for st in found)
    good = (not fresh and len(found) == 2
            and {(w[0], w[1]) for w in where} == {("2026-08-19", "2026-08-20"), ("2026-08-21", "2026-08-24")}
            and all(st.event == ("2026-09-03", 2.0) for st in found))
    return {"case": "APH store", "independence": "mechanism (store pattern laid on real bars)",
            "fresh_series_seams": len(fresh), "seams_found": where,
            "measured": [("2026-08-19", "2026-08-20", 0.491), ("2026-08-21", "2026-08-24", 1.981)],
            "pass": good}


CASES: List[tuple] = [
    ("KORU", date(2026, 6, 20), case_koru),
    ("CRWD", date(2026, 4, 15), case_crwd),
    ("BKNG", date(2026, 3, 20), case_bkng),
    ("SPGI", date(2026, 6, 10), case_spgi),
    ("FUBO", date(2026, 3, 5), case_fubo),
    ("APH", date(2026, 7, 25), case_aph),
]


def run(fetch: Callable = bars_mod.fetch_daily, end: date = date(2026, 9, 16)) -> List[Dict[str, Any]]:
    results = []
    for ticker, start, fn in CASES:
        series = fetch([ticker], start, end).get(ticker)
        if series is None:
            results.append({"case": ticker, "pass": None, "reason": "no bars returned"})
            continue
        try:
            results.append(fn(series))
        except Exception as exc:  # noqa: BLE001 -- a broken case is reported, not hidden
            results.append({"case": ticker, "pass": False, "error": f"{type(exc).__name__}: {exc}"})
    return results
