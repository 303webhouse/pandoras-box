"""Option rows become POSITIONS WITH LEGS (R-IV.444(b)). Idempotent, and it drops nothing.

A multi-leg position stored as two strike columns cannot say what it holds. The columns carry
the shape of a vertical and nothing else, so a three-leg structure is either split across rows
(XLF 300/301) or written into a note (NVDA 415) — and a screen reading those rows renders the
same position two or three times, which is what the principal's screenshot showed.

THE MAPPING IS READ OFF THE BOOK, not assumed from the structure names. Measured over all 280
option rows: `long_strike` is the BOUGHT leg and `short_strike` is the SOLD leg, in every
structure the vocabulary contains — put debit spreads hold long > short in all 148 rows with
both, call debit spreads hold long < short in all 90, and the one put credit spread holds the
sold (higher) put in short_strike. The side is the column; the right is the structure's name.

EVERY OPTION ROW GETS AN OUTCOME AND NOTHING IS SILENTLY DROPPED (R-IV.432(c)). A row that
cannot become legs is recorded with the reason it cannot, and is left exactly as it is:

  MIGRATED                 legs written from the stored strikes
  MERGED_INTO              its legs belong to another position (the XLF group)
  ENTERED_BY_HAND          the shape exceeded the columns and the legs were typed in
  PENDING_CAPABILITY       the data exists but the shape needs hand-entry (R-IV.445(c)):
                           a third leg recorded in prose, or a structure with more legs than
                           two strike columns can hold. NOT a failure -- the row is waiting on
                           a capability, and the capability now exists at
                           POST /v2/positions/{id}/legs
  UNMIGRATABLE_NO_STRIKES  typed OPTION with no strike to convert (R-IV.444(b))
  UNMIGRATABLE_NO_EXPIRY   a leg without an expiry is not a leg

The two classes are kept apart because they resolve differently: an UNMIGRATABLE row needs a
SOURCE (an export, a memory, a broker record), while a PENDING_CAPABILITY row needs nothing but
someone to type what the note already says. Filing the second under the first would have
described work as damage.

PRICES ARE NOT INVENTED. A vertical records its NET, never the split, so each leg's price is
NULL unless a fill recorded it. The unknown is representable, exactly as it is for a lot.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# structure name -> (option right, has a sold leg)
STRUCTURES = {
    "put_debit_spread":  ("PUT", True),
    "put_spread":        ("PUT", True),
    "put_credit_spread": ("PUT", True),
    "call_debit_spread": ("CALL", True),
    "call_spread":       ("CALL", True),
    "long_put":          ("PUT", False),
    "long_call":         ("CALL", False),
}
# Structures whose leg count exceeds what two strike columns can hold.
LEGS_EXCEED_STRIKES = {"iron_condor"}

MIGRATED = "MIGRATED"
MERGED_INTO = "MERGED_INTO"
ENTERED_BY_HAND = "ENTERED_BY_HAND"
NO_STRIKES = "UNMIGRATABLE_NO_STRIKES"
NO_EXPIRY = "UNMIGRATABLE_NO_EXPIRY"
# R-IV.445(c): waiting on hand-entry, not failed. Both members were ruled to stay unmigrated
# until the edit path could enter their legs, and to be recorded as pending-capability.
PENDING_CAPABILITY = "PENDING_CAPABILITY"
# The labels these rows were first written under, remapped once on the next boot.
LEGACY_PENDING_LABELS = ("UNMIGRATABLE_LEGS_EXCEED_STRIKES", "UNMIGRATABLE_LEG_IN_NOTES")

# ── The XLF group, ruled (R-IV.444(b)) ───────────────────────────────────────────────────
# 300 holds 45P/40P at 8, 301 holds 30P at 8, and 420 holds two 09-01 structures whose own
# note records the fills that prove the shape: BTO 45P @0.02, STO 40P @0.03, BTO 30P @0.06.
# One position, three legs, and the rows that fed it recorded by name.
XLF_SURVIVOR = "POS_XLF_20260609_233055"          # id 300 — earliest entry, largest quantity
XLF_MERGED = ("POS_XLF_20260609_233128",          # id 301 — the 30P leg
              "POS_XLF_20260901_R385")            # id 420 — the two 09-01 structures
XLF_LEGS = (
    # (seq, right, side, strike, qty)  -- 10 structures: 8 from the June vintage, 2 from 09-01
    (1, "PUT", "LONG", 45.0, 10),
    (2, "PUT", "SHORT", 40.0, 10),
    (3, "PUT", "LONG", 30.0, 10),
)
XLF_DETAIL = ("one position, three legs (45P/40P/30P 10/16), fed by id 300 (45P/40P x8), "
              "id 301 (30P x8) and id 420 (two 09-01 structures). Per-leg prices are known "
              "for the 09-01 fills only (0.02/0.03/0.06); the June vintage records a net per "
              "spread (0.1455) and a single (0.0826), so no per-leg price is asserted.")

# A leg recorded in prose rather than in a column. Named, because migrating the two stored
# strikes would publish a 2-leg position where a 3-leg one exists.
LEG_IN_NOTES_POSITIONS = {"POS_NVDA_20260911_001150": "third leg ($50 put) recorded in notes"}


def classify(row: Dict[str, Any]) -> Tuple[str, List[Dict[str, Any]], str]:
    """(outcome, legs, detail) for one option row. Pure."""
    pid = row.get("position_id")
    if pid in LEG_IN_NOTES_POSITIONS:
        return (PENDING_CAPABILITY, [],
                f"{LEG_IN_NOTES_POSITIONS[pid]} — awaiting hand-entry of the full structure")

    structure = (row.get("structure") or "").strip().lower()
    long_strike, short_strike = row.get("long_strike"), row.get("short_strike")
    expiry, qty = row.get("expiry"), row.get("quantity")

    if structure in LEGS_EXCEED_STRIKES:
        return (PENDING_CAPABILITY, [],
                f"{structure} has more legs than long_strike/short_strike can hold — awaiting "
                f"hand-entry of the full structure")
    if not structure or structure not in STRUCTURES:
        if long_strike is None and short_strike is None:
            return NO_STRIKES, [], f"structure={structure or 'NULL'} and no strike on the row"
        return (PENDING_CAPABILITY, [],
                f"structure={structure or 'NULL'} is not in the mapped vocabulary — its legs "
                f"are entered by hand, not guessed from a name")
    if long_strike is None:
        return NO_STRIKES, [], f"{structure} with no long_strike"

    right, has_short = STRUCTURES[structure]
    if has_short and short_strike is None:
        return NO_STRIKES, [], f"{structure} with no short_strike"
    if expiry is None:
        return NO_EXPIRY, [], f"{structure} with no expiry — a leg without one is not a leg"

    q = abs(float(qty or 0)) or 1.0
    legs = [{"leg_seq": 1, "option_type": right, "side": "LONG",
             "strike": float(long_strike), "expiry": expiry, "qty": q, "price": None}]
    if has_short:
        legs.append({"leg_seq": 2, "option_type": right, "side": "SHORT",
                     "strike": float(short_strike), "expiry": expiry, "qty": q, "price": None})
    return MIGRATED, legs, f"{structure}: long_strike bought, short_strike sold"


async def run(conn) -> Dict[str, int]:
    """Expand every option row that has no outcome yet. Idempotent; never rewrites a row.

    The guard is the outcome record, not the legs: a position recorded as UNMIGRATABLE has no
    legs by definition, and re-running must not keep reconsidering it.
    """
    # R-IV.445(c): rows filed under the first labels are re-filed as pending-capability. They
    # were never failures; the capability they wait on arrived after they were classified.
    await conn.execute(
        "UPDATE position_legs_migration SET outcome = $1 WHERE outcome = ANY($2::text[])",
        PENDING_CAPABILITY, list(LEGACY_PENDING_LABELS))

    rows = await conn.fetch(
        """SELECT p.position_id, p.structure, p.long_strike, p.short_strike, p.expiry,
                  p.quantity, p.asset_type
             FROM unified_positions p
            WHERE p.asset_type IN ('OPTION', 'SPREAD')
              AND NOT EXISTS (SELECT 1 FROM position_legs_migration m
                               WHERE m.position_id = p.position_id)""")
    counts: Dict[str, int] = {}
    for r in rows:
        row = dict(r)
        pid = row["position_id"]
        if pid == XLF_SURVIVOR or pid in XLF_MERGED:
            continue                                   # handled as a group below
        outcome, legs, detail = classify(row)
        await _write(conn, pid, outcome, legs, detail)
        counts[outcome] = counts.get(outcome, 0) + 1
    counts.update(await _migrate_xlf_group(conn))
    if counts:
        logger.info("position legs migration: %s", counts)
    return counts


async def _write(conn, position_id: str, outcome: str, legs, detail: str,
                 merged_into: Optional[str] = None) -> None:
    async with conn.transaction():
        for leg in legs:
            await conn.execute(
                """INSERT INTO position_legs
                       (position_id, leg_seq, option_type, side, strike, expiry, qty, price,
                        provenance, migrated_from)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 'PRINCIPAL_REPORTED', $9)
                   ON CONFLICT (position_id, leg_seq) DO NOTHING""",
                position_id, leg["leg_seq"], leg["option_type"], leg["side"],
                leg["strike"], leg["expiry"], leg["qty"], leg["price"],
                leg.get("migrated_from") or position_id)
        await conn.execute(
            """INSERT INTO position_legs_migration
                   (position_id, outcome, detail, legs_written, merged_into)
               VALUES ($1, $2, $3, $4, $5)
               ON CONFLICT (position_id) DO NOTHING""",
            position_id, outcome, detail, len(legs), merged_into)


async def _migrate_xlf_group(conn) -> Dict[str, int]:
    """The ruled group: one position, three legs, and the rows that fed it named."""
    present = await conn.fetch(
        "SELECT position_id FROM unified_positions WHERE position_id = ANY($1::text[])",
        [XLF_SURVIVOR, *XLF_MERGED])
    live = {r["position_id"] for r in present}
    if XLF_SURVIVOR not in live:
        return {}
    done = await conn.fetchval(
        "SELECT 1 FROM position_legs_migration WHERE position_id = $1", XLF_SURVIVOR)
    if done:
        return {}
    legs = [{"leg_seq": seq, "option_type": right, "side": side, "strike": strike,
             "expiry": _xlf_expiry(), "qty": qty, "price": None,
             "migrated_from": "id 300 + id 301 + id 420"}
            for seq, right, side, strike, qty in XLF_LEGS]
    await _write(conn, XLF_SURVIVOR, MIGRATED, legs, XLF_DETAIL)
    out = {MIGRATED: 1, MERGED_INTO: 0}
    for pid in XLF_MERGED:
        if pid in live:
            await _write(conn, pid, MERGED_INTO, [],
                         f"legs belong to {XLF_SURVIVOR} (R-IV.444(b))", merged_into=XLF_SURVIVOR)
            out[MERGED_INTO] += 1
    return out


def _xlf_expiry():
    from datetime import date
    return date(2026, 10, 16)
