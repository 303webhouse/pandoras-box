"""R-IV.1052(e)(c)6 — the F: README must describe the code that generates it.

The README says of itself: *"Generated, not hand-maintained — if it disagrees with the data, the
data is right and this file is stale."* It then disagreed with the data for several releases. Its
"Reading it safely" paragraph defined a complete session as `exhausted = TRUE AND
prints_received > 0` while the export query beside it had required `reached_floor = TRUE` since
R-IV.1005(d).

**That is why the fix is here and not on F:.** Hand-editing the ferry copy would be overwritten
by the next nightly run, and it would also break R-IV.1043(c), which makes ferry files immutable
once handed to a lane. The generator is the author; the file is its output.

These tests COUPLE the prose to the query, so the two cannot drift apart silently again. A
comment asking the next person to remember would not have stopped the first drift either.
"""
from __future__ import annotations

import os
import re

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EXPORT = os.path.join(REPO, "scripts", "f_export.py")


@pytest.fixture(scope="module")
def mod():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_f_export_under_test", EXPORT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.fixture(scope="module")
def readme(mod):
    return mod.README


# -- 0. positive control ---------------------------------------------------------------

def test_the_readme_and_the_query_were_both_found(mod, readme):
    """Without this, every assertion below could be passing on an empty string."""
    assert len(readme) > 2000, "README constant looks truncated"
    sql = _all_sql(mod)
    assert "exhausted" in sql, "the SQL scan found no eligible-sessions predicate"
    assert "reached_floor" in sql, "the export query no longer gates on reached_floor"


def _all_sql(mod):
    return "\n".join(str(v) for k, v in vars(mod).items()
                     if isinstance(v, str) and ("SELECT" in v or "FROM" in v))


# -- 1. THE COUPLING: whatever the query requires, the README states --------------------

def test_every_completeness_predicate_the_query_uses_is_named_in_the_readme(mod, readme):
    """THE DRIFT ITSELF. The export selects its eligible sessions with three predicates; the
    README named two. Any predicate the query gates on must appear in the prose, so adding a
    fourth without documenting it fails here rather than on F: four releases later."""
    sql = _all_sql(mod)
    m = re.search(r"WHERE\s+(exhausted[^\n]*prints_received\s*>\s*0)", sql, re.I)
    assert m, "the eligible-sessions predicate could not be located in the export SQL"
    predicate = m.group(1)
    for col in re.findall(r"\b(exhausted|reached_floor|prints_received)\b", predicate):
        assert col in readme, (
            "the export query gates on `%s` and the README does not mention it -- the README "
            "is stale the moment it is written" % col)


def test_reached_floor_is_explained_and_not_merely_mentioned(readme):
    """Naming the column is not documenting it. A reader needs to know that `exhausted` alone
    is satisfied by a budget cut-off, which is the whole reason the second predicate exists."""
    assert "reached_floor" in readme
    assert "04:00" in readme, "reached_floor's meaning is the session's 04:00 ET start"
    low = readme.lower()
    assert "budget" in low or "cut short" in low


# -- 2. b1 / b2 and the measured cap ---------------------------------------------------

def test_both_completeness_proofs_are_documented(readme):
    assert re.search(r"\bb1\b", readme) and re.search(r"\bb2\b", readme)
    assert "04:15" in readme, "b2's guard was tightened to 04:15 ET by R-IV.1010(c)"


def test_the_page_cap_is_documented_as_MEASURED_not_configured(readme):
    """The subtle one. b2 asks whether the final page came back below the cap. Using the
    CONFIGURED PAGE_LIMIT when the vendor silently caps lower makes every final page look
    short, and then b2 proves completeness for nothing."""
    assert "MAX(row_count)" in readme
    assert "PAGE_LIMIT" in readme, "the README must say which number NOT to use"


# -- 3. the three-state vocabulary -----------------------------------------------------

def test_SUSPECT_is_documented_as_a_third_state(readme):
    assert "SUSPECT" in readme
    assert "third state" in readme.lower()


def test_completeness_unknown_is_distinguished_from_partial(readme):
    """A missing claim and a negative claim are different facts; the manifest has both."""
    assert "COMPLETENESS_UNKNOWN" in readme
    i = readme.find("COMPLETENESS_UNKNOWN")
    assert "PARTIAL" in readme[i:i + 400], "the README must say it is NOT PARTIAL"


# -- 4. the two non-vendor columns -----------------------------------------------------

@pytest.mark.parametrize("col", ["session_date", "quarantined"])
def test_the_hub_written_columns_are_documented(readme, col):
    assert col in readme, "%s is written onto every row and is not documented" % col


def test_session_date_is_distinguished_from_the_executed_date(readme):
    """THE PARTITION MISMATCH. A walk for one session returns prints that executed on the
    session before, so `session_date` and `executed_at::date` are different partitions. The
    2,053-row disagreement on 2026-09-21 was this. A reader told only "the session" would
    group by the wrong one."""
    i = readme.find("session_date")
    window = readme[i:i + 900]
    assert "executed_at" in window, "session_date must be contrasted with executed_at"
    assert "2026-09-21" in window, "the measured disagreement is the evidence; cite it"


def test_quarantined_still_carries_its_prohibition(readme):
    """Pre-existing and must survive the rewrite: collected and kept, never joined to the
    Triton shadow table."""
    i = readme.find("quarantined")
    window = readme[i:i + 600]
    assert "triton_flow_shadow" in window
    assert "never" in window.lower()


# -- 5. the file is still generated, and LAB still gets it -----------------------------

def test_the_readme_is_written_to_both_destinations(mod):
    """LAB cannot read F:, so it has its own copy. A rewrite that updated only the ferry copy
    would leave LAB reading the stale definition -- and LAB is the lane that grades."""
    src = open(EXPORT, encoding="utf-8").read()
    assert "LAB_COPY" in src
    assert src.count("README)") >= 2 or src.count("README,") >= 2


def test_it_still_declares_itself_generated(readme):
    """The sentence that makes hand-editing the F: copy wrong. If it ever goes, the next
    person will fix the output instead of the generator."""
    assert "Generated, not hand-maintained" in readme
