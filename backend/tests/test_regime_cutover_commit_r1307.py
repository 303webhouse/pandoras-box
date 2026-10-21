"""The v2.1 cutover, as one commit. R-IV.1303(c) / R-IV.1307(c).

QUERY cleared c7261e90 for v2.1 under R-IV.1301(b) -- H1, M1 and M2 met, M1 proven as a property
over 2,200 randomised series -- so the flip happens here, with the four things R-IV.1307(c)
requires in a single commit: `RULES_VERSION`, the pin test, the cost line, and `cutover_state`
passing its four-counter check against row 929.

THE FIFTH THING, WHICH IS NOT IN THE RULING AND IS WHY THIS COMMIT ALSO TOUCHES main.py.
Flipping `RULES_VERSION` alone would have made the next deploy re-seed the era. `main.py`'s
startup task asks "are there any current rows for RULES_VERSION?", and on the deploy carrying
the flip the answer is 0 -- so it would have

    1. marked ALL 304 CURRENT v2 ROWS SUPERSEDED, and
    2. called `run_seed`, an unconditional backfill of every classifiable session,

which is a full replay of the era that registration section 1 / R-IV.1277(b) item 7 forbids in
terms: "no replay or re-seed of any era", and "if the job cannot start without a seeded history,
STOP and ask SPINE. Do not backfill."

The gate built under R-IV.1288(c) lives in `run_nightly`, and that is the wrong place ON ITS OWN:
the startup task runs first, on the very deploy that carries the flip, and would have re-seeded
before any nightly ran. A cutover commit that cannot be deployed without replaying the era is
not a prepared cutover, so the guard is here rather than reported and deferred.

THE RULE IT ADDS, kept as narrow as it can be: a version with a DECLARED PREDECESSOR is a
cutover and never seeds. A version with none keeps the old first-boot behaviour exactly, so v1
and v2 on a fresh database are untouched.

MEASURED LIVE before this commit was made, against the real database:

    anchor row      id=929, 2026-10-20, shown=range_chop raw=correction held=5
                    pending=correction closes=3
    current v2.1    0 rows, so the cutover path is the one that runs
    cutover_state   ok=True inherited=True needs_ruling=False differs=None
    four counters   shown_regime, held_sessions, pending, pending_closes -- all four agree
"""
from __future__ import annotations

import ast
import json
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from models.regime_classifier import RULES_VERSION, load_rules       # noqa: E402
from models.regime_hysteresis import cost_statement                  # noqa: E402

from ._srcscan import read_source                                    # noqa: E402

MAIN = str(_BACKEND / "main.py")
DISPLAY = _BACKEND / "config" / "regime_card_display.v1.json"

#: R-IV.1307(b), character for character.
COST_LINE = ("SPY 1999-2026, 24 declines: all-clear a median 81.5 sessions after the low, "
             "never on 11; 200d line 38. (R-IV.1301)")


def _startup_block() -> str:
    """The regime seed task in `main.py`, bounded by its own `except`."""
    src = read_source(MAIN)
    i = src.index("async def _regime_seed_task")
    return src[i:src.index("asyncio.ensure_future(_regime_seed_task())", i)]


# ── the flip ────────────────────────────────────────────────────────────────

def test_the_version_is_v21_everywhere_it_is_read():
    assert RULES_VERSION == "v2.1"
    assert load_rules()["version"] == "v2.1"


# ── the cost line ───────────────────────────────────────────────────────────

def test_the_cost_line_is_R_IV_1307bs_SENTENCE_VERBATIM():
    """Character for character. A cost line is a claim about measured behaviour, so a paraphrase
    would be BUILD authoring one -- which R-IV.925(b) forbids and which is how the previous
    wording came to call QUERY's own graded figures "ungraded"."""
    assert cost_statement("v2.1") == [COST_LINE]


def test_it_carries_the_FIGURES_and_the_CENSORING_the_old_line_dropped():
    """R-IV.1280's finding against the old sentence was not that it was vague: it reported a
    median and SILENTLY DROPPED that the median ranks 11 never-called recoveries as worst. For
    nearly half the events the honest answer is "never", and a reader could not recover that."""
    line = cost_statement("v2.1")[0]
    assert "81.5" in line, "the median, to the precision QUERY graded it"
    assert "never on 11" in line, "the censoring, which is the half that was missing"
    assert "24 declines" in line, "the denominator"
    assert "SPY 1999-2026" in line, "the universe and the span (Conventions #37/#38)"
    assert "200d line 38" in line, "the baseline it is measured against"


def test_the_line_is_v21s_and_is_NOT_served_for_v2():
    """Attributing a measurement to the version that did not produce it is the exact fault
    R-IV.1280 found. v2's absence is deliberate."""
    assert cost_statement("v2") == []
    cfg = json.loads(DISPLAY.read_text(encoding="utf-8"))
    assert list(cfg["cost_lines"]) == ["v2.1"]


def test_the_line_still_does_not_come_from_the_rules_file():
    """R-IV.1303(b) holds after the flip too -- the stamped artifact is not the display source
    even now that the served version IS v2.1."""
    stamped = load_rules("v2.1")["hysteresis"]["stated_cost"]
    assert stamped != COST_LINE
    assert stamped not in cost_statement("v2.1")


def test_the_retired_phrase_is_gone_from_every_live_file():
    """R-IV.1307(b) asked for every live occurrence of the retired phrase to go. It survived in
    a dead `MEASURED_COST` constant and in two prose copies quoting it.

    THE NEEDLE IS ASSEMBLED AT RUNTIME so that this file -- which has to name what it sweeps
    for -- does not itself contain the string and fail its own test. That is the eleventh time
    a scan has been defeated by the prose explaining it, and `ast` does not help: the text
    would be a docstring, which `ast.unparse` keeps.
    """
    needle = "b6a6abd9" + ", " + "ungraded"
    offenders = []
    for path in sorted(_BACKEND.rglob("*.py")):
        if "__pycache__" in str(path):
            continue
        if needle in path.read_text(encoding="utf-8"):
            offenders.append(str(path))
    for path in sorted((_BACKEND / "config").glob("*.json")):
        if needle in path.read_text(encoding="utf-8"):
            offenders.append(str(path))
    assert offenders == [], offenders

def test_the_drift_priors_PROVENANCE_hash_is_deliberately_kept():
    """`regime_drift_prior.py` cites `b6a6abd9` as the source of the figures on the grey line.
    That is a provenance hash, not the retired phrase, and deleting it would strip the citation
    from a number the card displays. Pinned so a future sweep for the string does not take it."""
    src = read_source(str(_BACKEND / "models" / "regime_drift_prior.py"))
    assert "b6a6abd9" in src
    assert ("b6a6abd9" + ", " + "ungraded") not in src


# ── the four-counter check ──────────────────────────────────────────────────

def test_the_inheritance_compares_ALL_FOUR_counters_and_refuses_on_any():
    """Read off the function: the live run proves it passes TODAY, this proves it would CATCH a
    disagreement tomorrow. A verifier that happens to agree once is not a verifier."""
    src = read_source(str(_BACKEND / "jobs" / "regime_job.py"))
    i = src.index("async def cutover_state")
    block = src[i:src.index("async def unmatched_run", i)]
    for field in ("shown_regime", "held_sessions", "pending", "pending_closes"):
        assert field in block, field
    assert "needs_ruling=True" in block
    assert "VERIFIED, NOT COPIED" in block
    assert "INSERT" not in block.upper() and "_write_snapshot" not in block


def test_a_disagreement_NAMES_THE_FIELD_rather_than_refusing_vaguely():
    """The live run PASSED, which proves it agrees today and nothing about tomorrow. Driving a
    real disagreement needs the whole bar-series machinery -- `cutover_state` loads the
    designated series to recompute the anchor -- and a stub thin enough to write here would be
    testing the stub. My first attempt was exactly that and died on `conn.fetch`.

    The refusal PATHS that need no series are already driven for real in
    `test_regime_cutover_r1288` (undeclared version, predecessor with no settled row). What is
    left to pin is that the four-counter branch reports WHICH field moved, because a refusal
    that only says "they differ" sends the next reader back to the database to find out.
    """
    src = read_source(str(_BACKEND / "jobs" / "regime_job.py"))
    i = src.index("async def cutover_state")
    block = src[i:src.index("async def unmatched_run", i)]
    assert "stored=%r computed=%r" in block, "the refusal must name the values"
    assert "differs=diffs" in block, "and which fields they belong to"
    assert "STOPPING and asking" in block

# ── the fifth thing: the startup path must not re-seed ──────────────────────

def test_the_startup_task_NEVER_SEEDS_a_version_with_a_declared_predecessor():
    """THE REASON THIS COMMIT TOUCHES main.py. Without it the flip's own deploy would supersede
    304 current v2 rows and replay the era."""
    block = _startup_block()
    assert "CUTOVER_PREDECESSOR" in block
    assert "elif _RV in _PRED:" in block
    # the seed and the supersede both live in the no-predecessor branch, after the elif
    i_elif = block.index("elif _RV in _PRED:")
    # ANCHORED ON THE FIRST-BOOT ARM'S OWN COMMENT. `block.index("else:")` finds the INNER
    # else of `if _cs.get("inherited"): ... else:` and truncates the cutover arm before the
    # content being asserted -- the sixth window-locator failure of this build.
    i_boot = block.index("# No declared predecessor: a genuine first boot")
    cutover_arm, first_boot_arm = block[i_elif:i_boot], block[i_boot:]
    assert "run_seed" not in cutover_arm, "the cutover arm must not seed"
    assert "_sup(" not in cutover_arm, "the cutover arm must not supersede"
    assert "run_seed" in first_boot_arm and "_sup(" in first_boot_arm


def test_the_cutover_arm_REFUSES_rather_than_falling_through_to_a_seed():
    """A blocked cutover must stop, not quietly become a first boot -- which is the shape the
    old code had: one `if not _have` with a seed on the end of it."""
    block = _startup_block()
    i = block.index("elif _RV in _PRED:")
    arm = block[i:block.index("# No declared predecessor: a genuine first boot", i)]
    assert 'if _cs.get("inherited"):' in arm
    assert "CUTOVER BLOCKED" in arm
    assert "logger.error" in arm


def test_a_version_with_NO_predecessor_keeps_the_OLD_first_boot_behaviour():
    """The guard must be as narrow as the problem. v1 and v2 on a fresh database are the case
    this must not change, and `CUTOVER_PREDECESSOR` declares neither."""
    from jobs.regime_job import CUTOVER_PREDECESSOR
    assert CUTOVER_PREDECESSOR == {"v2.1": "v2"}
    assert "v2" not in CUTOVER_PREDECESSOR and "v1" not in CUTOVER_PREDECESSOR


def test_nothing_is_superseded_before_a_v21_row_exists():
    """Superseding v2 at cutover time would leave every `superseded = FALSE` read -- the ribbon,
    the breadth history, the flip list -- with nothing to return, and the card would go blank
    until the first nightly. The comment says so where the decision is."""
    block = _startup_block()
    assert "until a v2.1 row exists" in block


def test_the_startup_block_still_PARSES_as_it_reads():
    """It is edited by hand inside a deeply indented async closure, where an indentation slip
    compiles into the wrong branch. Parsed rather than eyeballed."""
    tree = ast.parse(read_source(MAIN))
    fns = [n for n in ast.walk(tree)
           if isinstance(n, ast.AsyncFunctionDef) and n.name == "_regime_seed_task"]
    assert len(fns) == 1
    ifs = [n for n in ast.walk(fns[0]) if isinstance(n, ast.If)]
    assert any(len(n.orelse) and isinstance(n.orelse[0], ast.If) for n in ifs), (
        "the if/elif/else chain must be a chain, not three independent ifs")
