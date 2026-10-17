"""Convention #42 (TA-177) — every served field declares STORED or DERIVED.

THE RULE: *every served field declares STORED or DERIVED; no cap, gate or filter may be
computed from a DERIVED field.* It exists because `strategy_tag` was gated on: one column held
three independent taxonomies, each row kept whichever was written last, and filtering it for the
Roth's 20% tactical cap returned SOXS alone at 8.26% against a truth of 19.50%. A reader cannot
see from a payload whether a value is the book's record or this hub's arithmetic, so the payload
has to say.

THREE LABELS, and the third is not a loophole -- it is a citation.

    STORED              served as the book stores it. May be gated on.
    DERIVED             computed for this response. MAY NOT be gated on.
    GATEABLE_BY_RULING  derived, and a ruling explicitly permits gating on it anyway. The
                        ruling is named in the declaration. Nothing enters this category
                        without one.

WHY THE THIRD EXISTS. R-IV.844(d)3 requires open rows to be selected by `open_quantity > 0`,
"never by `trade_outcome` or `strategy_tag`" -- and `open_quantity` is DERIVED, a SUM over
`position_lots`. Taken literally, convention #42 forbids the filter that R-IV.844(d)3 mandates.
Both rules are right: #42's target is a field with no single author, and `open_quantity` has
exactly one (`services.open_quantity.stamp_open_quantity`, R-IV.660(b)2). So the conflict is
recorded as a citation rather than resolved by silently downgrading either rule. **Flagged to
SPINE for confirmation; if the ruling comes back the other way, this category empties and
nothing else changes.**

A FIELD WHOSE ORIGIN VARIES BY ROW IS DERIVED. `trade_outcome` is the stored column when the
row has one and this module's word ("OPEN"/"UNKNOWN") when it does not; `classification_reason`
is the row's text or one of three sentences written here. A single per-tool map cannot say
"stored on that row, computed on this one", and the safe reading of an ambiguous provenance is
the one that forbids gating. Where a tool serves a PER-ROW origin field -- R-IV.1048(c)'s
`classification_reason_origin` is the first -- the declaration names it, because that field can
answer per row what this map cannot.
"""
from __future__ import annotations

from typing import Dict, Optional, Tuple

STORED = "stored"
DERIVED = "derived"
GATEABLE_BY_RULING = "gateable_by_ruling"

ORIGINS = (STORED, DERIVED, GATEABLE_BY_RULING)

#: The labels a cap, gate or filter may be computed from.
GATEABLE = frozenset({STORED, GATEABLE_BY_RULING})


#: Why a field is labelled as it is, where the reason is not obvious from the name. Keyed by
#: (tool, field). Prose only -- nothing reads these but a person.
NOTES: Dict[Tuple[str, str], str] = {
    ("hub_get_positions", "trade_outcome"):
        "the stored column when the row has one, else this module's OPEN/UNKNOWN -- origin "
        "varies by row, so it is DERIVED and may not be gated on (R-IV.844(d)2)",
    ("hub_get_positions", "classification_reason"):
        "the row's text when stored, else one of three sentences written by "
        "models.position_taxonomy. PER-ROW ORIGIN: classification_reason_origin "
        "(R-IV.1048(c))",
    ("hub_get_positions", "bucket_reason"):
        "same shape as classification_reason, computed by models.position_taxonomy. No "
        "per-row origin field exists for it yet",
    ("hub_get_positions", "strategy_tag"):
        "THE FIELD THAT CAUSED THIS CONVENTION. A display string mixing three taxonomies; "
        "stored, but NEVER gateable -- see GATE_FORBIDDEN below",
    ("hub_get_positions", "open_quantity"):
        "a SUM over position_lots, but R-IV.844(d)3 requires open rows to be selected by it "
        "and R-IV.660(b)2 gives it one author",
    ("hub_get_positions", "open_remainder"):
        "the OLDER KEY for open_quantity, kept so nothing reading it breaks (R-IV.660(b)2) -- "
        "same author, same figure, so it carries the same R-IV.844(d)3 exemption. If the two "
        "ever diverge, one of them is wrong and neither should be gated on",
    ("hub_get_positions", "leverage_factor"):
        "stored, and NULL means NOT RECORDED rather than 1x. leverage_factor_recorded says "
        "which, and nothing may be sized off the value while it is false (R-IV.1052(e)(c)4)",
    ("hub_get_positions", "tactical_pct"):
        "R-IV.1167(a). Tactical market value over the account balance, by "
        "models.roth_tactical_cap.tactical_share -- the same author the push reminder uses. "
        "`pct` is null WITH A REASON on any call whose rows are not a capped account's whole "
        "open set, because a share of a subset understates a limit",
    ("hub_get_positions", "unrealized_pnl"):
        "R-IV.1183(b). DERIVED: attach_economics (R-IV.526(b)) replaces it with the figure the "
        "row's LOTS support, at the open remainder and on the cash basis (R-IV.1181(c)2), and "
        "moves the table's value to unrealized_pnl_stored -- which this tool does not serve. "
        "It was declared STORED until 2026-10-16, so anything gating on it was in breach",
    ("hub_get_positions", "max_loss"):
        # A note saying "same reason as the other field" sends the reader somewhere else to
        # find out why, and this note's whole job is to stop the next relabel. Self-contained.
        "R-IV.1183(b). DERIVED: attach_economics (R-IV.526(b)) replaces it with the worst case "
        "the row's LOTS support at the open remainder, and moves the table's value to "
        "max_loss_stored, which this tool does not serve. R-IV.207(d) separately forbids "
        "separately forbids SUMMING it: the stored column carried the wrong scope on ten of "
        "seventeen lotted open rows, understating the total by $632.08 (13.7%) on 2026-09-24. "
        "capital_at_risk is cost-derived instead, and says so",
}


#: A STORED field that still may not be gated on, with the ruling that forbids it. STORED is a
#: statement about PROVENANCE; it is not a licence. `strategy_tag` is stored and is the exact
#: field whose gating produced the 8.26%-vs-19.50% error, so the prohibition is explicit and
#: outranks the label.
GATE_FORBIDDEN: Dict[Tuple[str, str], str] = {
    ("hub_get_positions", "tactical_pct"):
        "R-IV.1033(e) / R-IV.1167(a): the 20% tactical cap REMINDS and blocks nothing, so the "
        "figure that measures it must not become a block. It is also null on any filtered "
        "call -- a share of a subset is not the account's share -- and a gate reading that "
        "null would either fail open or refuse every filtered read.",
    ("hub_get_positions", "strategy_tag"):
        "TA-123 / R-IV.794(b): one column held classification, sleeve and bucket, so each row "
        "kept only the last written. Read classification / sleeve_tag / bucket instead.",
}


#: Per-tool declarations. A tool present here must declare EVERY field it serves.
DECLARED: Dict[str, Dict[str, str]] = {
    "hub_get_positions": {
        # ---- the row ----------------------------------------------------------------
        "position_id": STORED,
        "ticker": STORED,
        "account": STORED,              # lower-cased for display; the value is the book's
        "structure": STORED,
        "quantity": STORED,             # the size OPENED (convention #29)
        "entry_price": STORED,
        "current_price": STORED,
        "current_value": DERIVED,
        # R-IV.1183(b): DERIVED, and not a nuance. `attach_economics` (R-IV.526(b)) replaces
        # both of these with the figure the row's LOTS support and moves the table's own value
        # to `unrealized_pnl_stored` / `max_loss_stored`, so by the time this tool serialises a
        # row neither field holds what the book stores. See NOTES for what rested on the old
        # label.
        "unrealized_pnl": DERIVED,
        "max_loss": DERIVED,
        "open_quantity": GATEABLE_BY_RULING,
        "open_quantity_basis": DERIVED,
        "open_remainder": GATEABLE_BY_RULING,   # the older key for open_quantity, same author
        "basis_reason": DERIVED,
        "long_strike": STORED,
        "short_strike": STORED,
        "expiry": STORED,
        "dte": DERIVED,                 # computed from expiry against a clock
        "stop_loss": STORED,
        "target": STORED,
        "opened_at": STORED,
        "closed_at": STORED,
        "trade_outcome": DERIVED,
        "strategy_tag": STORED,         # stored AND gate-forbidden; see GATE_FORBIDDEN
        "classification": STORED,
        "sleeve_tag": STORED,
        "bucket": STORED,
        "needs_document": STORED,
        "classification_reason": DERIVED,
        "classification_reason_origin": DERIVED,
        "sleeve_reason": STORED,
        "orientation_at_entry": STORED,
        "x4_result": STORED,
        "cut_due": STORED,
        "cut_status": STORED,
        "leverage_factor": STORED,
        "leverage_factor_recorded": DERIVED,
        "bucket_reason": DERIVED,
        # ---- the response body ------------------------------------------------------
        "status": STORED,               # the caller's own filter, echoed
        "positions": DERIVED,
        "position_count": DERIVED,
        "strategy_tag_basis": DERIVED,
        "classification_backfilled": DERIVED,
        "positions_without_classification": DERIVED,
        "position_ids_without_classification": DERIVED,
        "cap_enforceable": DERIVED,
        "classifications_without_basis": DERIVED,
        "bucket_coverage": DERIVED,
        # R-IV.1167(a). DERIVED, and gate-forbidden below as well: DERIVED alone merely
        # withholds permission, while a GATE_FORBIDDEN entry says out loud that this figure
        # must never become a block. R-IV.1033(e) settled that the cap reminds and stops
        # nothing.
        "tactical_pct": DERIVED,
        "tactical_pct_basis": DERIVED,
        "cap_scope": DERIVED,
        "cap_scope_basis": DERIVED,
        "positions_without_strategy_tag": DERIVED,
        "untagged_position_ids": DERIVED,
        "positions_not_open": DERIVED,
        "capital_at_risk_cost_basis": DERIVED,
        "basis": DERIVED,
        "positions_included": DERIVED,
        "positions_excluded": DERIVED,
        "excluded": DERIVED,
        "complete": DERIVED,
    },
}


#: Tools with no declaration yet. **THIS SET MUST SHRINK AND NEVER GROW.**
#:
#: Convention #42 was adopted for the whole MCP surface, and this is 20 of 22 data tools still
#: owing one. They are listed by name rather than left implicit, because "every field declares
#: its origin" with twenty silent exceptions is not a convention, it is a claim.
#:
#: `hub_get_positions` is declared first on purpose: it is the surface the 20% tactical cap is
#: computed from, so it is where gating on the wrong field has already cost a real figure. A
#: declaration is only worth having if it is RIGHT, and each one needs its payload builder read
#: field by field -- `classification_reason` is both a column name and a computed sentence, so
#: matching field names against the schema would have mislabelled exactly the field R-IV.1048(c)
#: had just corrected.
UNDECLARED = frozenset({
    "hub_get_bias_composite", "hub_get_board_state", "hub_get_chart_indicators",
    "hub_get_crypto_market_profile", "hub_get_crypto_quote", "hub_get_crypto_state",
    "hub_get_flow_radar", "hub_get_hermes_alerts", "hub_get_hydra_scores",
    "hub_get_market_profile", "hub_get_options_chain", "hub_get_portfolio_balances",
    "hub_get_quote", "hub_get_sector_strength", "hub_get_stable_movers",
    "hub_get_stable_rates_fx", "hub_get_stable_regime", "hub_get_stable_theme_members",
    "hub_get_stable_themes", "hub_get_trade_ideas",
})


def origin_map(tool: str) -> Optional[Dict[str, str]]:
    """The tool's declaration, or None when it has not been written yet.

    None is NOT an empty map. An empty map would say "this tool serves no fields", and a
    consumer that read it that way would conclude nothing is gateable rather than that nothing
    is known.
    """
    declared = DECLARED.get(tool)
    return dict(declared) if declared is not None else None


def origin_of(tool: str, field: str) -> Optional[str]:
    """One field's origin, or None when the tool or the field is undeclared."""
    return (DECLARED.get(tool) or {}).get(field)


def may_gate(tool: str, field: str) -> Tuple[bool, str]:
    """(allowed, reason) — whether a cap, gate or filter may be computed from this field.

    FAILS CLOSED on anything undeclared. An unknown provenance is the case convention #42 was
    written for, so "I have no declaration for that" must not read as permission.
    """
    forbidden = GATE_FORBIDDEN.get((tool, field))
    if forbidden:
        return False, "explicitly gate-forbidden: %s" % forbidden
    origin = origin_of(tool, field)
    if origin is None:
        if tool in UNDECLARED:
            return False, ("%s has no field-origin declaration yet, so no field of it may be "
                           "gated on (convention #42 fails closed)" % tool)
        return False, "%s.%s is not declared, and an undeclared field is not gateable" % (
            tool, field)
    if origin in GATEABLE:
        note = NOTES.get((tool, field))
        return True, ("%s is %s%s" % (field, origin, "; " + note if note else ""))
    return False, ("%s is DERIVED -- computed for this response, so no cap, gate or filter may "
                   "rest on it%s" % (field, "; " + NOTES[(tool, field)]
                                     if (tool, field) in NOTES else ""))
