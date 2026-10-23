"""The Regime Strategy card's live payload: the stored label, the diff, the health state.

R-IV.1195(b). This is the ONLY reader of `regime_snapshots` outside the job that writes it, and
a CI check (backend/tests/test_regime_live_r1195.py) enforces that. #42: the label drives the
card and nothing else -- no gate, cap, kill-switch, Kairos input or grade may read it.

NO MOCK FALLBACK, deliberately. When the live read fails this serves `unavailable` with a named
reason and the card shows "cannot confirm". Falling back to the fixture would put plausible
numbers on a screen that looks healthy -- the `/api/crypto/market` fault, where a sibling
symbol's price was served as `binance_spot` for weeks because the fallback was invisible.

WHY THE PAYLOAD CARRIES `settled_close` AND `display_only`. Both are shown on the face of the
card (R-IV.1193(b)), so they are fields rather than front-end string literals: a caption the
server does not author is a caption that can drift from the value it describes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from database.postgres_client import get_postgres_client

logger = logging.getLogger(__name__)

#: Served on every payload. The card prints it; nothing computes from it.
DISPLAY_ONLY = "display only"

#: registration §1 / R-IV.1277(b): the small line under the label. The thresholds in section 2 were fitted on a span
#: in which dips were bought, and a reader is entitled to know what the rules were tuned against
#: before reading a label off them. Stated once, here, rather than written into the renderer.
TUNED_FOR = "Tuned for: post-2013 dip-buying market"


def _drift_prior_for(shown_regime):
    """LAB's stamped drift prior for a shown label. R-IV.1284(c).

    Imported inside the function because this module is loaded by the route and the table is a
    leaf module -- and because a failure to read it must cost the card its grey line, not its
    label. An absent prior is reported, never substituted.
    """
    try:
        from models.regime_drift_prior import for_label

        return for_label(shown_regime)
    except Exception as exc:                                        # noqa: BLE001
        return {"available": False,
                "reason": "LAB's drift-prior table could not be read (%s)" % type(exc).__name__}

#: R-IV.1203(b)4. The designated source, now WIRED. Measured for 2026-10-16:
#:
#:   Polygon daily aggregate   SPY 763.25   QQQ 709.80   IWM 270.44   <- designated, and served
#:   UW chart close            SPY 763.25   QQQ 709.80   IWM 270.44   <- agrees, and verifies it
#:   stable_daily_bars         SPY 764.29   QQQ 712.57   IWM 270.67   <- superseded
#:
#: The series is SPLIT-ADJUSTED AND NOT DIVIDEND-ADJUSTED (Polygon `adjusted=true`), which is
#: the basis a settled close has to be on. `stable_daily_bars` stays fully adjusted and is still
#: what the SECTOR BREADTH is read from -- R-IV.1203(c) rules that basis correct for moving
#: averages and breadth, so only the settled close moved.
CLOSE_SOURCE = "polygon"
CLOSE_SOURCE_NOTE = (
    "polygon daily aggregate, split-adjusted and not dividend-adjusted, verified against the "
    "UW chart close before each nightly write (R-IV.1203(b)). Sector breadth is still read "
    "from stable_daily_bars on a fully-adjusted basis, which is correct for moving averages.")

#: §2's ten keys mapped to the display labels the registered playbook file uses. Taken from the
#: playbook, not invented here (R-IV.925(b)).
#:
#: THIS WAS DELETED BY ACCIDENT AND THE ROUTE 500ed ON IT. The R-IV.1203(b) edit replaced a
#: block by two computed offsets, and this dict sat between them, so it was swallowed with the
#: comment it followed. Convention #43 exists for exactly that: a replace anchors BOTH ends by
#: CONTENT and asserts the line after -- a slice between two index() positions asserts nothing
#: about what is inside it. Guarded now by a test that assembles the available payload.
_LABELS = {
    "crash_liquidation": "CRASH / LIQUIDATION", "bear_market": "BEAR MARKET",
    "bear_market_rally": "BEAR-MARKET RALLY", "breakdown": "BREAKDOWN",
    "recovery": "RECOVERY", "correction": "CORRECTION", "range_chop": "RANGE / CHOP",
    "melt_up": "MELT-UP", "uptrend": "UPTREND", "narrow_uptrend": "NARROW UPTREND",
}


def _unavailable(reason: str) -> Dict[str, Any]:
    """The honest empty payload. `regime_key` is None so the card cannot place a marker."""
    return {
        "available": False,
        "unavailable_reason": reason,
        "regime_key": None,
        "regime_label": None,
        "label": None,
        "tags": [],
        "basis": None,
        "settled_close": None,
        "close_source": CLOSE_SOURCE,
        "close_source_note": CLOSE_SOURCE_NOTE,
        "per_index": [],
        "evidence": {"families": []},
        "display_only": DISPLAY_ONLY,
        "health": "unconfirmed",
        "health_reason": reason,
        "health_detail": {"state": "unavailable", "reason": reason},
        "diff": None,
    }


#: The three display blocks §1 shows that v1 has no feed for. Served as an explicit statement
#: rather than omitted, so the card can print the reason instead of an empty panel the reader
#: has to interpret.
#: R-IV.1198(e). Ratified as INTERIM, not final: §2 names five families but states no
#: per-family test, so these two reuse the Correction row's own clauses. Nothing gates on them
#: (#42), and per-family tests get designed at the same review as the flip rate.
INTERIM_FAMILIES = ("structure", "breadth")

NO_FEED_IN_V1 = {
    "lights": "no ruled discipline feed in v1",
    "tripwires": "no intraday tripwire feed in v1",
    "overlays": "overlays are a judgement input, not computed in v1",
    "lens_split": "no watchlist/macro lens feed in v1",
    "intraday": "the kill-switch is not read by this card (R-IV.1186(c))",
}


def _per_index(inputs: Dict[str, Any]) -> list:
    """The index strip, from the stored inputs.

    An index the job could not read for that session is carried with `uncertain` set and its
    reason, NOT dropped: a missing row and a healthy row look the same once the strip is three
    tiles wide, and the gauge would silently rescale around the two that remain.
    """
    out = []
    for tkr, blk in (inputs.get("indices") or {}).items():
        price, ma50, ma200 = blk.get("price"), blk.get("ma50"), blk.get("ma200")
        usable = None not in (price, ma50, ma200)
        state = blk.get("market_state")
        # UNCERTAIN COVERS BOTH GAPS, not just the missing price. An index whose prices are fine
        # but whose market_state is null still shows "CANNOT CONFIRM", and a chip that says that
        # without carrying its reason is the caption-without-its-field fault again.
        why = blk.get("unavailable_reason")
        if not why and not usable:
            why = "price or an average is unavailable"
        if not why and state is None:
            why = "market_state is null (ADX or the average stack is unavailable)"
        out.append({
            "ticker": tkr,
            "price": price, "ma50": ma50, "ma200": ma200,
            "state": (state or "cannot confirm").upper(),
            "uncertain": (not usable) or state is None,
            "uncertain_why": why or "",
        })
    # SPY first, then QQQ, then IWM -- the order §1's strip uses.
    order = {"SPY": 0, "QQQ": 1, "IWM": 2}
    return sorted(out, key=lambda r: order.get(r["ticker"], 9))


def _families(inputs: Dict[str, Any]) -> list:
    """The evidence panel. A family with no feed is listed WITH ITS REASON, never omitted.

    R-IV.1193(d): "Any family with no feed yet (VOL, CARRY until v2) renders as no data. Never
    infer it." Omitting the row would read as "not risk-off", which is a claim nobody measured.

    THE FIELD IS `key`, NOT `name`. v2.js reads `f.key`, and `esc(undefined)` renders the
    literal word "undefined" rather than failing -- so serving `name` put five dots labelled
    "undefined" on the live card. The server and the renderer are two ends of one contract and
    only the renderer gets to name it.
    """
    fams = inputs.get("families") or {}
    basis = inputs.get("families_basis") or {}
    absent = inputs.get("families_absent_in_v1") or {}
    rows = []
    for name in ("structure", "breadth", "credit", "vol", "carry"):
        if name in fams and fams[name] is not None:
            # INTERIM, per R-IV.1198(e). These two reuse the Correction row's own clauses
            # because §2 names five families and states no per-family test; per-family tests
            # get designed at the same review as the flip rate. The mark goes on the TOOLTIP
            # and not only in a ruling, so the reader of the dot knows what it is standing on.
            why = basis.get(name)
            rows.append({"key": name.upper(),
                         "state": "risk_off" if fams[name] else "risk_on",
                         "why": ("%s · interim test (R-IV.1198(e))" % why) if why
                                else "interim test (R-IV.1198(e))",
                         "interim": name in INTERIM_FAMILIES})
        elif name in absent:
            rows.append({"key": name.upper(), "state": None, "why": absent[name],
                         "interim": False})
        else:
            # NOT "no feed in v1". That claim belongs only to the families the rules file names
            # as having no feed. A family that HAS a feed but no value for this session is a
            # different fact, and saying "no feed" about it is a caption asserting an absence
            # that is not real -- which is what the first live payload did for STRUCTURE and
            # BREADTH, because the read-back had not selected inputs_json.
            rows.append({"key": name.upper(), "state": None,
                         "why": "not recorded for this session", "interim": False})
    return rows


async def _report_card(conn):
    """The Regime Report Card payload. R-IV.1321(b). Never raises.

    EMPTY TODAY, AND THAT IS THE CORRECT STATE. The card scores sessions strictly AFTER the
    v2.1 cutover and never backfills; `RULES_VERSION` is still "v2" on main and the cutover is
    on its branch awaiting deploy, so there are no scorable rows. The panels say so rather than
    showing zeroes -- a zero here would read as "measured, and it was nil".

    THE OUTCOME PANELS NEED A SERIES THE HUB DOES NOT STORE, and that is reported rather than
    worked around. Spec section 1.2 is explicit that "higher 20 sessions later" and "worst dip"
    are defined on SPY FULLY ADJUSTED closes (splits and dividends), while the 200-day line and
    the 60-session low are defined on SPLIT-adjusted, DIVIDEND-UNADJUSTED closes.
    `regime_daily_bars` holds the second basis only. Using it for the first would make every
    live figure incomparable with the base rate printed beside it -- which the spec names as
    "the single likeliest implementation error, because one series would work everywhere". So
    those panels carry `available: false` and the reason, and nothing is computed on the wrong
    basis to fill a space.
    """
    try:
        from models import regime_report_scoring as rs

        rows = await conn.fetch(
            """SELECT as_of, shown_regime
                 FROM regime_snapshots
                WHERE rules_version = $1 AND superseded = FALSE AND settled IS TRUE
                ORDER BY as_of""", rs.SCORED_VERSION)
        if not rows:
            return rs.empty_card(
                "no settled %s rows yet: the card scores only sessions after the cutover and "
                "never backfills" % rs.SCORED_VERSION)

        from jobs.regime_job import label_to_group, version_live_instant

        # ── P11 (R-IV.1354(b)2): A SESSION IS IN SCOPE IFF ITS CLOSE IS AFTER THE CUTOVER ──
        #
        # THE BREACH THIS EXISTS FOR, measured. Friday's fallback labelled session 2026-10-20
        # as v2.1 (row 930) -- a CORRECT label, reproducing v2's own 10-20 reading exactly --
        # and the card then served `first_session: 2026-10-20` with `backfilled: false`. But
        # 10-20 closed at 2026-10-20T16:00-04:00, which is BEFORE the cutover instant of
        # 2026-10-22T19:03:00.396505Z. The card was a scoring card with a BACKDATED START,
        # claiming to measure the new rules on a session that predates them. The scope was
        # wrong, not the classifier.
        #
        # THE INSTANT COMES FROM THE RECORDED FACT, never a hardcoded date here and never
        # /health: the hub has restarted since the cutover, so /health reports the CURRENT
        # process and re-deriving the boundary from it would walk it forward on every deploy,
        # quietly pulling already-scored sessions back out of scope.
        cutover_instant, cutover_source = await version_live_instant(conn, rs.SCORED_VERSION)
        if cutover_instant is None:
            # NO MARKER MEANS SCORE NOTHING, not score everything. An unknown boundary cannot
            # be treated as "no boundary" -- that is precisely the backdated card again.
            out = rs.empty_card(
                "the cutover instant is not recorded, so no session can be shown to fall after "
                "it: %s" % cutover_source)
            out["scope"] = dict(out["scope"], cutover_instant=None,
                                cutover_source=cutover_source, excluded_pre_cutover=[])
            return out

        scoped = [r for r in rows if rs.in_scope(r["as_of"], cutover_instant)]
        excluded = [str(r["as_of"])[:10] for r in rows
                    if not rs.in_scope(r["as_of"], cutover_instant)]

        if not scoped:
            # E1, NOT A SCORING CARD. R-IV.1354(b)3: row 930 STAYS -- it is not deleted and not
            # wrong -- and it appears here by name. A card that dropped it silently would leave
            # a reader unable to tell "nothing has been scored yet" from "nothing exists".
            out = rs.empty_card(
                "every %s row so far closed before the cutover instant, so there is nothing in "
                "scope yet: the card scores only sessions whose close is after %s and never "
                "backfills" % (rs.SCORED_VERSION, cutover_instant.isoformat()))
            out["scope"] = dict(out["scope"],
                                cutover_instant=cutover_instant.isoformat(),
                                cutover_source=cutover_source,
                                excluded_pre_cutover=excluded)
            return out

        rows = scoped
        shown = [r["shown_regime"] for r in rows]
        first, last = rows[0]["as_of"], rows[-1]["as_of"]
        span = None
        try:
            span = float((last - first).days)
        except Exception:                                           # noqa: BLE001
            span = None

        out = rs.empty_card("")
        out["available"] = True
        out["reason"] = ""
        # `backfilled` IS ASSERTED, NOT DEFAULTED (QUERY's §1.1.2). It read `False` as a literal
        # with nothing having checked anything -- a claim the payload had not earned. It is now
        # the RESULT of the scope test: false because every row in `rows` was shown to close
        # after the instant, with the instant, its source and the excluded rows all on the
        # payload so a reader can repeat the check instead of trusting it.
        earliest_close = rs.session_close(first)
        backfilled = not (earliest_close > cutover_instant)
        out["scope"] = {"first_session": str(first)[:10], "sessions": len(rows),
                        "rules_version": rs.SCORED_VERSION, "backfilled": backfilled,
                        "cutover_instant": cutover_instant.isoformat(),
                        "cutover_source": cutover_source,
                        "first_session_close": earliest_close.isoformat(),
                        "excluded_pre_cutover": excluded}
        out["flips"] = rs.flips_panel(shown, days_span=span, sessions=len(rows))
        # P1/P2 and P9. `checked` is 0 until a session is 20 sessions old AND the fully
        # adjusted series exists to score it against, so the counts start as total/0/total --
        # which is the honest shape, not a placeholder.
        out["calls"] = rs.calls_block(len(rows), 0)
        out["v2_divergence"] = rs.divergence_block(0, 0)
        out["ma200"] = rs.ma200_panel(0, 0, 0)
        # R-IV.1327(b): THE OUTCOME PANELS NOW COMPUTE, from the SPY series matched to LAB's
        # drift-prior pull (yfinance, auto_adjust=False, Adj Close). Until this existed they
        # reported an absence rather than a figure on the wrong basis, because a live share
        # computed on the split-only series cannot sit beside a base rate measured on the
        # fully adjusted one -- spec section 1.2's named error.
        #
        # `all_clears_held` STILL REPORTS AN ABSENCE, and deliberately: its test is R4/G4, a new
        # 60-session CLOSING low, which section 6 defines on the SPLIT-ADJUSTED series. The
        # ruling asked for the fully adjusted series, and using it here would be the same basis
        # mixing pointed the other way.
        try:
            from integrations.spy_adjusted_closes import closes as _adj

            adj = _adj()
        except Exception:                                           # noqa: BLE001
            adj = {"available": False, "reason": "the adjusted series could not be read"}

        groups = {}
        try:
            groups = label_to_group()
        except Exception:                                           # noqa: BLE001
            groups = {}

        if adj.get("available"):
            scored = rs.score_sessions(
                [{"as_of": r["as_of"], "shown_regime": r["shown_regime"]} for r in rows],
                adj["rows"], groups)
            out["by_label"] = rs.label_rows(scored["per_label"], groups)
            out["calls"] = rs.calls_block(len(rows), scored["checked_total"])
            out["warnings_held"] = dict(scored["warnings"], available=True)
            dips = scored["dips_by_group"]
            out["dip_order"] = dict(
                rs.dip_order_panel(dips.get("TREND-DOWN/STRESS", []), dips.get("TREND-UP", [])),
                available=True)
            out["series"] = {"basis": adj["basis"], "n": adj["n"],
                             "first": adj.get("first"), "last": adj.get("last"),
                             "matched_to": adj.get("matched_to")}
        else:
            no_series = {"available": False,
                         "reason": adj.get("reason") or "the adjusted series is unavailable"}
            out["by_label"] = []
            out["warnings_held"] = dict(no_series, pending=None,
                                        threshold_pct=rs.WARNING_DIP_PCT,
                                        basis=rs.BASIS_ADJUSTED)
            out["dip_order"] = dict(no_series, basis=rs.BASIS_ADJUSTED,
                                    question="does STRESS's median forward-20 dip exceed UP's?")

        out["all_clears_held"] = {
            "available": False,
            "reason": ("needs the 60-session closing low on %s, which R4/G4 defines and this "
                       "card does not yet read" % rs.BASIS_ALL_CLEAR),
            "pending": None, "horizon_sessions": rs.ALL_CLEAR_HORIZON,
            "basis": rs.BASIS_ALL_CLEAR}
        out["groups"] = groups
        return out
    except Exception as exc:                                        # noqa: BLE001
        from models import regime_report_scoring as rs

        return rs.empty_card("report card unavailable: %s" % type(exc).__name__)

async def _ma200_row(conn):
    """SPY against its 200-day line, as a display row. R-IV.1309(b)3. Never raises.

    SPY ONLY, deliberately. `load_designated_series` defaults to fourteen tickers and takes
    0.72s; this row is about SPY and SPY alone, and the narrower load measures 0.13s for an
    identical answer. The compute itself is free (a rolling sum, under a millisecond).

    Guarded like every other leaf read here: a failure costs the card this ROW, never its
    label. Convention #42 -- nothing gates on it, so losing it loses a sentence and no more.
    """
    try:
        from jobs.regime_job import load_designated_series
        from models.regime_ma200 import ma200_row, row_text

        series = await load_designated_series(conn, tickers=("SPY",))
        bars = (series or {}).get("SPY") or []
        row = ma200_row(bars)
        row["text"] = row_text(row)
        return row
    except Exception as exc:                                        # noqa: BLE001
        return {"available": False, "reason": "%s" % type(exc).__name__}

def _cost_lines(rules_version):
    """The card's cost line(s), or []. Never raises into the payload.

    Guarded like every other leaf read in this module: "a failure to read it must cost the card
    its grey line, not its label." A display sentence is the least important thing on the card
    and must never be the reason the label does not render.
    """
    try:
        from models.regime_card_display import cost_lines

        return cost_lines(rules_version)
    except Exception:                                               # noqa: BLE001
        return []

async def get_regime_strategy(rules_version: Optional[str] = None) -> Dict[str, Any]:
    """The card's payload, or an `unavailable` one naming why.

    Reads through `jobs.regime_job`, which already owns the diff and health questions. Two
    implementations of "is this label current" would eventually disagree, and the one on the
    screen would be the one nobody tested.
    """
    try:
        from jobs.regime_job import (audit_notes, bar_freshness, flip_history,
                                     health as regime_health, ribbon as regime_ribbon,
                                     label_diff, latest_with_diff, seed_run, unmatched_run)
    except Exception as exc:
        return _unavailable("regime module unavailable (%s)" % type(exc).__name__)

    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            got = await latest_with_diff(conn, rules_version)
            hp = await regime_health(conn, rules_version)
            # R-IV.1278(b)4. READ EVEN WHEN A LABEL EXISTS, which is the whole point: on
            # 2026-10-19 and 10-20 a label existed (2026-10-16's) and the BARS had stopped,
            # and the card showed that label with nothing on its face to say so. This is the
            # one block the headline is allowed to replace a label with.
            fresh = await bar_freshness(conn)
            # registration §1 / R-IV.1277(b). A DIFFERENT staleness from `bar_freshness`: the data
            # arrived and NOTHING MATCHED, so the card is holding a label no rule supports.
            # Derived at read time from stored columns -- `regime_snapshots.regime` is NULL when
            # no row matched -- so there is no schema change and no second writer.
            held = await unmatched_run(conn, rules_version)
            # R-IV.1309(b)3: the 200-day row, DISPLAY ONLY (#42). Read beside the others so it
            # shares the one connection rather than opening a second.
            ma200 = await _ma200_row(conn)
            # R-IV.1321(b): the report card, display only (#42).
            report_card = await _report_card(conn)
            # R-IV.1195(b) asks for the seed count executed at deploy. Served here so the
            # number outlives the deploy log it was first read from.
            seeded_run = await seed_run(conn)
            # R-IV.1198(c): the flip list, so a reader can see whether the churn is real
            # regime change or chatter between two neighbouring labels.
            flips = await flip_history(conn, rules_version)
            # B8 section 7. Read here rather than in its own route: the
            # drawer already has this payload, and a second route for one
            # field is a second thing to keep in step.
            ribbon_block = await regime_ribbon(conn, rules_version)
            from jobs.regime_job import label_counts_by_version as _lcbv

            counts_by_version = await _lcbv(conn)
            # R-IV.1198(c)/(e): the standing notes, readable rather than only recorded.
            notes = await audit_notes(conn)
            # R-IV.1203(b)2: where the re-seed changed a label, as a list of dates.
            ldiff = await label_diff(conn, rules_version)
    except Exception as exc:
        logger.warning("[regime_strategy] read failed: %s", type(exc).__name__)
        return _unavailable("regime_snapshots unreadable (%s)" % type(exc).__name__)

    snap = got.get("snapshot")
    if snap is None:
        return _unavailable(got.get("unavailable_reason") or "no snapshot stored")

    # The RAW verdict and the SHOWN label are different facts and both are published. Serving
    # only the shown one would hide every session where hysteresis held a change back, which is
    # exactly what §2 requires the card to be able to say.
    import json as _json
    raw_inputs = snap.get("inputs_json")
    if isinstance(raw_inputs, str):
        try:
            raw_inputs = _json.loads(raw_inputs)
        except ValueError:
            raw_inputs = {}
    inputs = raw_inputs or {}

    shown = snap.get("shown_regime")
    # `health` is a STRING for the card's dot, which reads 'ok' or anything else. The full
    # three-state block rides alongside as `health_detail`, because collapsing stale into
    # unconfirmed on the wire would throw away the distinction the block exists to make.
    state = (hp or {}).get("state")
    return {
        "available": True,
        "as_of": snap["as_of"],
        "settled_close": snap["as_of"],
        # R-IV.1198(d): until the designated source is wired, the card NAMES the source it
        # is actually showing. An unnamed close is the one a reader assumes is right.
        "close_source": CLOSE_SOURCE,
        "close_source_note": CLOSE_SOURCE_NOTE,
        "regime_key": shown,
        "regime_label": _LABELS.get(shown) if shown else None,
        "raw_regime_key": snap.get("regime"),
        "label": snap.get("label"),
        "tags": list(snap.get("tags") or []),
        "per_index": _per_index(inputs),
        "evidence": {"families": _families(inputs)},
        "no_feed_in_v1": NO_FEED_IN_V1,
        "health": "ok" if state == "current" else "unconfirmed",
        "health_reason": (hp or {}).get("reason"),
        "health_detail": hp,
        # R-IV.1278(b)4: "Never a silent old label." `data_freshness.headline` is non-null ONLY
        # when the designated bar series has stopped arriving, and the card prints it INSTEAD
        # of the label. Served as its own block rather than folded into `health` because the
        # two measure different things -- `health` is the newest LABEL's lag, this is the
        # newest BAR's -- and the outage of 2026-10-19/20 is exactly the case where a reader
        # needs to know it is the DATA that stopped, not the classifier that declined.
        "data_freshness": fresh,
        # registration §1 / R-IV.1277(b): the HELD block. `stale` here means "no rule matched", which
        # is NOT the same as `data_freshness.stale` ("the bars stopped arriving") -- two causes,
        # two messages, and a reader who sees one must not think it is the other.
        "held_no_match": held,
        # R-IV.1284(c): LAB's stamped drift prior for the label being shown. Descriptive and
        # nothing gates on it (#42); `available` is False where the table has no row, because
        # a label v2 has never shown has NO prior, which is not a prior of zero.
        "drift_prior": _drift_prior_for(snap.get("shown_regime")),
        # registration §1 / R-IV.1277(b): the small line under the label. The classifier's thresholds were
        # fitted on a market that bought dips, and a reader is entitled to know what the rules
        # were tuned against before reading a label off them.
        "tuned_for": TUNED_FOR,
        "basis": snap.get("basis"),
        "not_evaluable": list(snap.get("not_evaluable") or []),
        "pending": snap.get("pending"),
        "pending_closes": snap.get("pending_closes"),
        "held_sessions": snap.get("held_sessions"),
        "change": snap.get("change"),
        "blocked": snap.get("blocked"),
        "seeded": bool(snap.get("seeded")),
        "rules_version": got.get("rules_version"),
        # R-IV.1303(b): THE COST LINE COMES FROM THE DISPLAY CONFIG, never from the stamped
        # rules file. Empty today and correctly so -- QUERY supplies v2.1's line under
        # R-IV.1301(c), and R-IV.1280 found the previous wording misleading. The card renders
        # no COSTS block at all on an empty list, rather than a heading with nothing under it,
        # which reads as a failed load.
        "costs": _cost_lines(got.get("rules_version")),
        # R-IV.1309(b)3. `display_only` rides on the row itself as well, so a later reader of
        # the payload alone cannot mistake it for an input.
        "ma200_row": ma200,
        "regime_report_card": report_card,
        "display_only": DISPLAY_ONLY,
        "diff": got.get("diff"),
        "seed_run": seeded_run,
        "flip_history": flips,
        "ribbon": ribbon_block,
        # R-IV.1260(c) asks for v2's label counts BESIDE v1's. Served rather than
        # queried by hand: R-IV.552(b) says a route exists so nobody needs SQL, and a
        # figure a ruling asks to be reported should be readable from the thing that
        # produced it.
        "label_counts_by_version": counts_by_version,
        # B8 section 1 (R-IV.1243(e)). Built from the rules file and this same
        # snapshot, so the conditions and the counters cannot disagree with the
        # classifier that produced the label.
        "flip_triggers": _flip_triggers_block(snap, shown),
        "audit_notes": notes,
        "label_diff": ldiff,
    }


def _flip_triggers_block(snap: dict, shown) -> dict:
    """B8 section 1's block, or its reason for being absent.

    Never raises into the payload: a drawer section that cannot be built says so, and the
    other seven sections still render.
    """
    try:
        from models.regime_classifier import load_rules
        from models.regime_flip_triggers_b8 import flip_triggers

        blob = snap.get("inputs_json")
        if isinstance(blob, str):
            import json as _json

            try:
                blob = _json.loads(blob)
            except ValueError:
                blob = None
        return flip_triggers({"regime_label": shown,
                              "raw_regime_key": snap.get("regime"),
                              "pending_closes": snap.get("pending_closes"),
                              "held_sessions": snap.get("held_sessions"),
                              # §4's bull side needs the sector count, which lives in the
                              # snapshot's own inputs rather than in a column.
                              "breadth": (blob or {}).get("breadth")
                              if isinstance(blob, dict) else None},
                             load_rules())
    except Exception as exc:                                        # noqa: BLE001
        return {"error": "%s" % type(exc).__name__,
                "basis": "the flip conditions could not be built from the rules file"}
