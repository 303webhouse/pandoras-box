"""R-IV.566(c) — the live form writes a lot the moment a position exists.

Rows entered through the form carried no lots until a cleanup ran, so they had no
open remainder and no value: the loss alert was blind to a position on the day it
opened, and every balance read PARTIAL for it.

Convention #30: each "it writes one" is paired with a case that must NOT, because a
path that lotted everything would pass every positive test and corrupt the remainder
on rows that have no acquisitions.
"""

import re
from datetime import datetime, timezone

import pytest

from models import position_lots as pl


def test_the_source_carries_the_instant_it_was_entered():
    src = pl.principal_entry_source(datetime(2026, 9, 24, 18, 30, 17, tzinfo=timezone.utc))
    assert src == "principal-entry@2026-09-24T18:30:17+00:00"
    assert pl.is_principal_entry(src)


@pytest.mark.parametrize("other", ["MANUAL", "IMPORT", "LEGACY-SINGLE-LOT", "", None])
def test_the_other_sources_are_not_principal_entries(other):
    assert not pl.is_principal_entry(other)


def test_the_constraint_regex_accepts_what_the_helper_writes():
    """The database CHECK is generated from this regex, so a helper that wrote a
    string the regex refused would fail every create at the last step."""
    for instant in (datetime(2026, 9, 24, 18, 30, 17, tzinfo=timezone.utc),
                    datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc),
                    datetime(2026, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc)):
        assert re.match(pl.PRINCIPAL_ENTRY_SOURCE_REGEX,
                        pl.principal_entry_source(instant))


@pytest.mark.parametrize("bad", ["principal-entry@", "principal-entry@yesterday",
                                 "MANUAL", "principal-entry@26-09-24T18:30"])
def test_the_regex_refuses_a_source_that_is_not_an_instant(bad):
    assert not re.match(pl.PRINCIPAL_ENTRY_SOURCE_REGEX, bad)


def test_the_database_constraint_is_generated_from_this_module():
    """Two copies of a vocabulary is how the second one gets forgotten."""
    import inspect

    from database import postgres_client as pc

    assert pc._LOT_SOURCES is pl.LOT_SOURCES
    assert pc._PRINCIPAL_ENTRY_SOURCE_REGEX == pl.PRINCIPAL_ENTRY_SOURCE_REGEX
    src = inspect.getsource(pc)
    assert "position_lots_source_check" in src
    assert "_LOT_SOURCES" in src


# -- the write paths ---------------------------------------------------------

def _live(fn):
    """The function's live string constants, docstrings and comments excluded."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(fn).lstrip())
    docs = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)) and body:
            first = body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docs.add(id(first.value))
    return " ".join(n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in docs).upper()


def test_the_create_path_writes_an_opening_lot():
    from api.unified_positions import create_position

    live = _live(create_position)
    assert "INSERT INTO POSITION_LOTS" in live
    # Positive control: it still writes the position itself, so the scan is reading
    # the real function.
    assert "INSERT INTO UNIFIED_POSITIONS" in live


def test_the_close_path_writes_a_disposal_lot():
    from api.unified_positions import close_position

    live = _live(close_position)
    assert "INSERT INTO POSITION_LOTS" in live
    assert "UPDATE UNIFIED_POSITIONS" in live


def test_the_close_path_checks_for_lots_before_writing_a_disposal():
    """A disposal against a row with no acquisitions makes the remainder NEGATIVE,
    and the legs constraint would refuse the whole close. The guard is what keeps a
    close working on the 100 historical rows that have no lots at all."""
    from api.unified_positions import close_position

    live = _live(close_position)
    assert "SELECT 1 FROM POSITION_LOTS" in live


def test_neither_path_invents_a_broker_reference():
    """broker_ref is the BROKER's, and a principal entry has none until the cleanup
    matches it against the export. Naming one here would make an unverified row look
    verified -- and the verified-needs-evidence constraint exists for that reason."""
    from api.unified_positions import close_position, create_position

    for fn in (create_position, close_position):
        live = _live(fn)
        assert "BROKER_REF" not in live

