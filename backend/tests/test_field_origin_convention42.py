"""Convention #42 (TA-177) — every served field declares STORED or DERIVED.

*No cap, gate or filter may be computed from a DERIVED field.* The convention exists because
`strategy_tag` was gated on: one column carried classification, sleeve and bucket, each row kept
whichever was written last, and filtering it for the Roth's 20% tactical cap returned SOXS alone
at 8.26% against a truth of 19.50%.

THE TEST THAT MATTERS is `test_every_served_field_is_declared`: a declaration written beside a
payload drifts from it the first time someone adds a field, and a map that silently omits the
new field would report it as undeclared-and-ungateable rather than wrong — which is safe, but
only until someone trusts the map to be complete. So the map is checked against the real
payload, field by field.
"""
from __future__ import annotations

import ast
import os

import pytest

from hub_mcp import field_origin as fo
from hub_mcp.envelope import make_response

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSITIONS = os.path.join(BACKEND, "hub_mcp", "tools", "positions.py")


def _payload_keys():
    """Every string key of every dict literal in the positions tool.

    Parsed, not grepped: the DESCRIPTION prose names plenty of fields in sentences, and an
    earlier test of mine failed on exactly that kind of mention.
    """
    with open(POSITIONS, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    keys = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for k in node.keys:
                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                    keys.add(k.value)
    return keys


# -- 0. the vocabulary ------------------------------------------------------------------

def test_the_three_labels_are_closed():
    assert set(fo.ORIGINS) == {"stored", "derived", "gateable_by_ruling"}


def test_only_two_of_them_permit_gating():
    assert fo.GATEABLE == {fo.STORED, fo.GATEABLE_BY_RULING}
    assert fo.DERIVED not in fo.GATEABLE


def test_every_declared_value_is_a_known_label():
    for tool, m in fo.DECLARED.items():
        for field, origin in m.items():
            assert origin in fo.ORIGINS, "%s.%s -> %r" % (tool, field, origin)


# -- 1. THE COUPLING: the map matches the payload --------------------------------------

def test_every_served_field_is_declared():
    """THE POINT OF THE FILE. Every key the positions payload actually serves must appear in
    the declaration."""
    declared = set(fo.DECLARED["hub_get_positions"])
    served = _payload_keys()
    # Envelope keys and internal dict literals are not served payload fields.
    envelope = {"status", "data", "summary", "staleness_seconds", "schema_version", "error",
                "field_origin"}
    missing = (served - declared - envelope)
    # Sub-structures built inside helpers (bucket_coverage's own keys, the as_of block) are
    # declared at their container, not leaf by leaf.
    containers = {"rows_bucketed", "rows_with_basis", "rows_without_basis",
                  "position_ids_without_basis", "safe_to_gate", "long", "short", "mixed",
                  "utc", "america_new_york", "exchange_session", "utc_to_the_second",
                  "derived_at", "stored_as_of", "derived_fields", "stored_fields", "now",
                  "account", "ticker", "positions", "note",
                  # R-IV.1167(a): the per-account tactical verdict's own keys. Declared at
                  # their container, `tactical_pct`, exactly as bucket_coverage's keys above
                  # are -- the contract is that a served FIELD is declared, not that every
                  # leaf of a nested structure is.
                  "pct", "at_or_over", "reason"}
    missing -= containers
    assert not missing, (
        "the positions payload serves fields that convention #42 does not declare: %s"
        % sorted(missing))


def test_no_declaration_describes_a_field_that_is_not_served():
    """The other direction. A declaration for a field nobody serves is a claim about a
    payload that does not exist, and it makes the map look more complete than it is."""
    declared = set(fo.DECLARED["hub_get_positions"])
    served = _payload_keys()
    # These are keys of `risk` and of the caller-echo, built in other modules and merged in.
    merged = {"capital_at_risk_cost_basis", "basis", "positions_included",
              "positions_excluded", "excluded", "complete", "positions_not_open",
              "position_count", "status"}
    stale = declared - served - merged
    assert not stale, "declared but never served: %s" % sorted(stale)


# -- 2. may_gate FAILS CLOSED ----------------------------------------------------------

def test_a_stored_field_may_be_gated_on():
    ok, why = fo.may_gate("hub_get_positions", "classification")
    assert ok, why


def test_a_derived_field_may_NOT_be_gated_on():
    ok, why = fo.may_gate("hub_get_positions", "dte")
    assert not ok and "DERIVED" in why


def test_an_UNDECLARED_tool_refuses_rather_than_permits():
    """THE FAIL-CLOSED CONTROL. Twenty tools have no declaration yet. "I have no map" must
    not read as "go ahead" -- that is how an unenforced cap reports itself as satisfied."""
    ok, why = fo.may_gate("hub_get_market_profile", "poc")
    assert not ok, why
    assert "no field-origin declaration" in why


def test_an_unknown_field_on_a_DECLARED_tool_also_refuses():
    ok, why = fo.may_gate("hub_get_positions", "a_field_nobody_declared")
    assert not ok and "not declared" in why


def test_strategy_tag_is_STORED_and_still_refused():
    """THE ORIGINAL SIN, and the reason STORED is a statement about provenance rather than a
    licence. strategy_tag IS stored; gating on it produced 8.26% against a truth of 19.50%."""
    assert fo.origin_of("hub_get_positions", "strategy_tag") == fo.STORED
    ok, why = fo.may_gate("hub_get_positions", "strategy_tag")
    assert not ok, "strategy_tag must never be gateable"
    assert "gate-forbidden" in why
    assert "R-IV.794" in why or "TA-123" in why


def test_open_quantity_is_gateable_by_a_CITED_ruling():
    """R-IV.844(d)3 requires open rows to be selected by `open_quantity > 0`, and it is a SUM
    over lots. The conflict with #42 is recorded as a citation, not resolved by pretending the
    field is stored."""
    assert fo.origin_of("hub_get_positions", "open_quantity") == fo.GATEABLE_BY_RULING
    ok, why = fo.may_gate("hub_get_positions", "open_quantity")
    assert ok and "R-IV.844(d)3" in fo.NOTES[("hub_get_positions", "open_quantity")]


def test_nothing_is_gateable_by_ruling_without_a_note_naming_one():
    """The third label is only legitimate while every member cites a ruling. Without this it
    becomes the escape hatch that empties the convention."""
    for tool, m in fo.DECLARED.items():
        for field, origin in m.items():
            if origin == fo.GATEABLE_BY_RULING:
                note = fo.NOTES.get((tool, field), "")
                assert "R-IV." in note or "TA-" in note, (
                    "%s.%s is gateable_by_ruling and cites no ruling" % (tool, field))


# -- 3. a varying origin is DERIVED ----------------------------------------------------

@pytest.mark.parametrize("field", ["trade_outcome", "classification_reason", "bucket_reason"])
def test_a_field_whose_origin_varies_by_row_is_DERIVED(field):
    """A single per-tool map cannot say "stored on that row, computed on this one", and the
    safe reading of an ambiguous provenance is the one that forbids gating."""
    assert fo.origin_of("hub_get_positions", field) == fo.DERIVED


def test_classification_reason_points_at_its_PER_ROW_origin_field():
    """R-IV.1048(c)'s field answers per row what the static map cannot, so the declaration
    names it."""
    note = fo.NOTES[("hub_get_positions", "classification_reason")]
    assert "classification_reason_origin" in note


# -- 4. the register of what is still owed ---------------------------------------------

def test_the_undeclared_register_and_the_declarations_are_disjoint():
    assert not (set(fo.DECLARED) & fo.UNDECLARED)


def test_the_register_covers_every_tool_on_the_surface():
    """A tool that is neither declared nor on the register is an unnoticed gap -- and it would
    answer `may_gate` with "not declared" rather than naming itself as owed work."""
    import importlib
    import pkgutil

    import hub_mcp.tools as tools_pkg
    found = set()
    for _f, name, _p in pkgutil.iter_modules(tools_pkg.__path__):
        if name in ("describe", "ping"):
            continue
        mod = importlib.import_module("hub_mcp.tools.%s" % name)
        for attr in dir(mod):
            if attr.startswith("hub_get_"):
                found.add(attr)
    accounted = set(fo.DECLARED) | fo.UNDECLARED
    assert not (found - accounted), (
        "tools neither declared nor registered as owed: %s" % sorted(found - accounted))


# -- 5. the envelope ------------------------------------------------------------------

def test_the_envelope_carries_the_map_when_there_is_one():
    r = make_response("ok", data={}, field_origin={"x": fo.STORED})
    assert r["field_origin"] == {"x": fo.STORED}


def test_the_envelope_OMITS_the_key_when_there_is_no_declaration():
    """An empty map would read as "this tool serves no fields", which a consumer could take as
    "nothing is gateable" when the truth is "nobody has said yet". An absent claim gets an
    absent key."""
    assert "field_origin" not in make_response("ok", data={})
    assert "field_origin" not in make_response("ok", data={}, field_origin=None)
    assert "field_origin" not in make_response("ok", data={}, field_origin={})


def test_origin_map_returns_None_not_empty_for_an_undeclared_tool():
    assert fo.origin_map("hub_get_market_profile") is None
    assert fo.origin_map("hub_get_positions") is not None


def test_the_map_handed_out_is_a_copy():
    """A caller mutating the response must not rewrite the declaration for every later call."""
    m = fo.origin_map("hub_get_positions")
    m["classification"] = "nonsense"
    assert fo.origin_of("hub_get_positions", "classification") == fo.STORED
