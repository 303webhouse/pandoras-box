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


async def get_regime_strategy(rules_version: Optional[str] = None) -> Dict[str, Any]:
    """The card's payload, or an `unavailable` one naming why.

    Reads through `jobs.regime_job`, which already owns the diff and health questions. Two
    implementations of "is this label current" would eventually disagree, and the one on the
    screen would be the one nobody tested.
    """
    try:
        from jobs.regime_job import (audit_notes, flip_history, health as regime_health,
                                     ribbon as regime_ribbon,
                                     label_diff, latest_with_diff, seed_run)
    except Exception as exc:
        return _unavailable("regime module unavailable (%s)" % type(exc).__name__)

    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            got = await latest_with_diff(conn, rules_version)
            hp = await regime_health(conn, rules_version)
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
        "basis": snap.get("basis"),
        "not_evaluable": list(snap.get("not_evaluable") or []),
        "pending": snap.get("pending"),
        "pending_closes": snap.get("pending_closes"),
        "held_sessions": snap.get("held_sessions"),
        "change": snap.get("change"),
        "blocked": snap.get("blocked"),
        "seeded": bool(snap.get("seeded")),
        "rules_version": got.get("rules_version"),
        "display_only": DISPLAY_ONLY,
        "diff": got.get("diff"),
        "seed_run": seeded_run,
        "flip_history": flips,
        "ribbon": ribbon_block,
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

        return flip_triggers({"regime_label": shown,
                              "raw_regime_key": snap.get("regime"),
                              "pending_closes": snap.get("pending_closes"),
                              "held_sessions": snap.get("held_sessions")},
                             load_rules())
    except Exception as exc:                                        # noqa: BLE001
        return {"error": "%s" % type(exc).__name__,
                "basis": "the flip conditions could not be built from the rules file"}
