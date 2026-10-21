"""`position_lot_closures.trade_date`: the column, and the writers that fill it. R-IV.1265(b).

THE COLUMN WAS NOT THE WHOLE JOB. The DDL shipped in 07596487 and the live route confirms the
column exists — and on 2026-10-19, with 840 closure rows in the ledger, **0 were trade-dated.**
Nothing wrote it. POSITIONS' 839-row backfill would have been diluted by every subsequent close,
because each new closure arrived NULL again: a backfill into a column with no writer is a
one-time correction that starts decaying the next day.

WHERE THE DATE COMES FROM, and why not from anywhere else:

  * NOT the clock. `created_at` already records when the row was written, and conflating the two
    is the exact fault the column exists to remove — Abacus reported +3,535.22 for "since
    2026-09-01" where the trades that actually closed in that window sum to about -30.
  * NOT a caller-supplied day. A caller could pass a day its own lot does not support.
  * THE DISPOSAL LOT'S OWN SESSION. The disposal lot is the row that records the disposal, so
    deriving from it means the two cannot disagree — and it is derived inside the same INSERT,
    so there is no window in which a separate read could see a different lot.

AND THE SESSION RULE IS R-IV.726'S, NOT A NEW ONE. `fill_time` is a `timestamptz` holding both
days-written-down (exactly midnight UTC) and real moments, so the per-value discriminator that
the Abacus census measured is the rule here too. It moved to `models/session_day.py` and both
callers import it; a second copy of a rule this subtle disagrees eventually, and the copy that
disagrees is the one nobody re-read.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from models import session_day as sd                                # noqa: E402

from ._srcscan import read_source                                   # noqa: E402

WRITER = _BACKEND / "api" / "unified_positions.py"
MAIN = _BACKEND / "main.py"


def _tree(path):
    return ast.parse(read_source(str(path)))


def _sql_literals(path, needle):
    """Every STRING LITERAL in the file containing `needle`, from the parsed tree.

    From the tree, so the comments above these statements — which name `trade_date` repeatedly,
    because they explain it — can neither satisfy nor trip the assertions. That trap has been hit
    seventeen times in this repo.
    """
    return [n.value for n in ast.walk(_tree(path))
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and needle in n.value]


# ── the writers ──────────────────────────────────────────────────────────────

def test_every_closure_insert_names_trade_date():
    """All three sites: the expiry sweep, /close and /reduce's confirm. A site that omitted it
    would write NULL silently and nothing downstream could tell that row from a historical one."""
    lits = _sql_literals(WRITER, "INSERT INTO position_lot_closures")
    assert len(lits) == 3, "expected 3 closure-insert sites, found %d" % len(lits)
    for sql in lits:
        assert "trade_date" in sql, sql[:200]
        # R-IV.1272(b)1 "labelled as such": the basis column travels with the date, at every
        # site. A column named at one site and not another is how two closures written minutes
        # apart come to disagree about what their dates mean.
        assert "trade_date_basis" in sql, sql[:240]


def test_every_closure_insert_derives_it_from_its_own_disposal_lot():
    """The column list is not enough: it must be FILLED, and filled from the disposal lot. One
    call per insert site, each bound to the disposal id's parameter."""
    # R-IV.1272(b)1: the helper is now `trade_date_values`, which emits the date AND the basis
    # label together. The date alone was what 863fae8d shipped; a date with no record of where
    # it came from is one a later reader has to guess at.
    calls = [n for n in ast.walk(_tree(WRITER))
             if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "trade_date_values"]
    assert len(calls) == 3, "expected 3 derivations, found %d" % len(calls)
    for c in calls:
        assert len(c.args) == 1 and isinstance(c.args[0], ast.Constant), ast.dump(c)
        assert c.args[0].value == 2, ("the disposal lot id is $2 at every site", c.args[0].value)


def test_the_insert_and_its_derivation_are_one_statement():
    """Concatenated into the same SQL string, so the value cannot be bound by a later read that
    could see a different lot. Asserted structurally: each literal is part of a BinOp whose other
    side is the derivation call."""
    tree = _tree(WRITER)
    joined = 0
    for n in ast.walk(tree):
        if not isinstance(n, ast.BinOp) or not isinstance(n.op, ast.Add):
            continue
        txt = ast.dump(n)
        if "INSERT INTO position_lot_closures" in txt and "trade_date_values" in txt:
            joined += 1
    assert joined >= 3, joined


def test_no_closure_insert_uses_now_or_created_at_for_the_trade_date():
    """The two wrong answers, excluded by name. `created_at` keeps its own DEFAULT NOW() in the
    DDL — that column is the write time and is supposed to be — but it must not appear in a
    `trade_date` position."""
    for sql in _sql_literals(WRITER, "INSERT INTO position_lot_closures"):
        head = sql[:sql.index("VALUES")] if "VALUES" in sql else sql
        assert "created_at" not in head, head
        assert "NOW()" not in sql.upper().replace("DEFAULT NOW()", ""), sql[:200]


def test_the_scan_would_notice_a_site_that_dropped_it():
    """Positive control (#30). Without this, a scan whose literal-finder matched nothing would
    read as three passing sites."""
    fake = ast.parse(
        'q = """INSERT INTO position_lot_closures (position_id, qty) VALUES ($1, $2)"""')
    lits = [n.value for n in ast.walk(fake)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and "INSERT INTO position_lot_closures" in n.value]
    assert len(lits) == 1 and "trade_date" not in lits[0]


# ── the session rule ─────────────────────────────────────────────────────────

def test_a_day_written_down_is_taken_as_written():
    """The 454-row half of the census. Converting exactly-midnight-UTC moves it backwards — the
    WRTH (948) error, which reported 09-30 for a fill both exports date 10-01."""
    import datetime as dt
    assert sd.day_of(dt.datetime(2026, 10, 1, 0, 0, tzinfo=dt.timezone.utc)) == dt.date(2026, 10, 1)


def test_a_real_moment_is_converted_to_the_principals_day():
    """The 103-row half. 03:00Z is 9 PM Mountain the previous day, and the principal's calendar
    day is the one that decides which side of a cutoff it falls on."""
    import datetime as dt
    assert sd.day_of(dt.datetime(2026, 10, 2, 3, 0, tzinfo=dt.timezone.utc)) == dt.date(2026, 10, 1)


def test_a_naive_timestamp_is_read_as_utc_and_not_as_local():
    import datetime as dt
    assert sd.day_of(dt.datetime(2026, 10, 1, 0, 0)) == dt.date(2026, 10, 1)


def test_a_date_passes_through_and_none_stays_none():
    import datetime as dt
    assert sd.day_of(dt.date(2026, 10, 1)) == dt.date(2026, 10, 1)
    assert sd.day_of(None) is None


def test_the_sql_and_the_python_agree_on_the_discriminator():
    """Both halves of the rule must branch on the same thing, or a window and a label computed
    from it would disagree at exactly the rows the rule was written for."""
    sql = sd.day_sql("fill_time")
    assert "AT TIME ZONE 'UTC')::time = TIME '00:00:00'" in sql
    assert "AT TIME ZONE 'UTC')::date" in sql
    assert "AT TIME ZONE 'America/Denver')::date" in sql


def test_the_derivation_reads_the_disposal_lot_by_id():
    sql = sd.trade_date_from_disposal(2)
    assert sql.startswith("(SELECT ") and "FROM position_lots WHERE id = $2" in sql
    assert "fill_time" in sql
    assert sd.trade_date_from_disposal(7).endswith("id = $7)")


# ── abacus still behaves exactly as it did ───────────────────────────────────

def test_abacus_delegates_and_its_sql_is_byte_identical():
    """The rule moved; the string it produces did not. A refactor of a window predicate that
    changed the predicate would move trades between periods silently."""
    from api.abacus import _day_sql
    assert _day_sql("x") == (
        "(CASE WHEN (x AT TIME ZONE 'UTC')::time = TIME '00:00:00' "
        "THEN (x AT TIME ZONE 'UTC')::date "
        "ELSE (x AT TIME ZONE 'America/Denver')::date END)")


def test_abacus_has_no_second_copy_of_the_arithmetic():
    src = read_source(str(_BACKEND / "api" / "abacus.py"))
    assert "from models.session_day import" in src
    body = src[src.index("def _day_sql"):]
    assert "CASE WHEN" not in body[:400], "the SQL must come from session_day, not be rebuilt here"


# ── the migration ────────────────────────────────────────────────────────────

def test_the_column_is_migrated_at_startup_as_a_nullable_date():
    """R-IV.1265(b): DATE, NULL allowed. NULL allowed is the point — the broker action date is
    not known for every historical closure, and a DEFAULT of created_at would bake in the very
    confusion the column removes."""
    lits = _sql_literals(MAIN, "position_lot_closures")
    alters = [s for s in lits if "ADD COLUMN" in s.upper()]
    assert alters, lits
    joined = " ".join(alters)
    assert "trade_date DATE" in joined, joined
    assert "NOT NULL" not in joined.upper()
    assert "DEFAULT" not in joined.upper()


@pytest.mark.parametrize("wrong", ["trade_date TIMESTAMPTZ", "trade_date DATE NOT NULL",
                                   "trade_date DATE DEFAULT NOW()"])
def test_the_migration_assertion_can_fail(wrong):
    """Control for the assertions above: each wrong form must trip at least one of them."""
    bad = wrong
    tripped = ("trade_date DATE" not in bad) or ("NOT NULL" in bad.upper()) \
        or ("DEFAULT" in bad.upper())
    assert tripped, bad
