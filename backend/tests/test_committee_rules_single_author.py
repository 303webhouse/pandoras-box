"""COMMITTEE_RULES.md has ONE author and seven generated copies -- R-IV.735(b), R-IV.735(c).

Eight copies of one text is one fact with eight writers, and the failure mode is silent: a skill
loading a stale copy still answers, just under last month's rules. Nothing surfaces. So the
identity of the eight is asserted here, on RAW BYTES (#32), and the applied rules text is pinned
so that reverting R-IV.735(b) fails a NAMED test rather than passing quietly.

Regenerate with `python scripts/sync_committee_rules.py`; check without writing with `--check`.
"""
import importlib.util
import io
import os
import shutil

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BACKEND)


def _load_sync():
    """Import the generator by path. `scripts/` is not a package and is not on sys.path, and the
    test must exercise the SAME code the operator runs -- a reimplementation here would be a
    second author of the comparison rule, which is the fault this file exists to prevent."""
    p = os.path.join(REPO, "scripts", "sync_committee_rules.py")
    if not os.path.isfile(p):
        pytest.fail("the generator is missing: %s" % p)
    spec = importlib.util.spec_from_file_location("sync_committee_rules", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


SYNC = _load_sync()

# R-IV.735(b)'s text, quoted from the applied sections. Each is unique to the new rules.
# R-IV.775(a): re-pinned to v5.1. Six of the eight R-IV.735 markers survived verbatim; two were
# reworded by v5.1 and are replaced by its own text, NOT loosened to keep the old test green:
#   "FIDELITY_401A strategic holdings sit outside this cap" -> the phrase now spans a line break
#   "Household net-direction cap - RULED 2026-10-07 [R-IV.730(a)]" -> "- TWO TESTS, REPORTED
#    SEPARATELY", because v5.1 made it two independent tests
# A marker must be on ONE line: these files are wrapped, and a needle that straddles a break can
# only fail, which would read as missing rule text.
APPLIED_MARKERS = (
    "FIDELITY_401A — BrokerageLink, account 653641836",
    "FIDELITY_ROTH — Roth Brokerage, account 652303158",
    "10% of all three tracked accounts combined (FIDELITY_401A + FIDELITY_ROTH +",
    "20% portfolio risk cap — tactical positions in BOTH Fidelity accounts.",
    "Deployment schedule — RULED 2026-10-07 [R-IV.730(a), R-IV.734(a)]",
    "Breakout Prop** — crypto-only, **untracked by design** (DESCOPED 2026-07-23)",
    # --- v5.1's own text, so these pins test the CURRENT rules and not what survived from v2 ---
    "### § Household net-direction cap — TWO TESTS, REPORTED SEPARATELY",
    "**FIDELITY_401A strategic",            # the line break falls after "strategic"
    "### § Z2 trend gate",
    "- **Z2 returns one of THREE results, not two:** PASS, FAIL, or **NOT EVALUABLE**.",
    "- **Household net-direction — report BOTH tests, separately.**",
)

# The two bullets SECTION B replaced, quoted far enough in to be unmistakable. Two of these
# phrases also appear inside SECTION A's own "### Retired, do not reinstate" list, where the new
# text QUOTES the old wording in order to retire it -- so each needle here runs past the quoted
# part into the old bullet's own continuation, which the retirement entry does not carry.
SUPERSEDED = (
    "- **Sizing is governed by the ROBINHOOD sleeve ceiling** (§ Account Context), not by",
    "- **20% portfolio risk cap — FIDELITY_ROTH only.** Sum of max losses across open",
    "- **FIDELITY_ROTH** — ONE account (Roth / 401(k) / 403(b) / BrokerageLink",
    "**Retired 2026-09-23, do not reinstate:** the separate",
)


def _text(path):
    return io.open(path, encoding="utf-8-sig").read().replace("\r\n", "\n")


def _all_eight():
    return [("_shared", SYNC.author_path())] + [(a, SYNC.copy_path(a)) for a in SYNC.ROSTER]


class TestOneAuthorSevenCopies:
    def test_the_ruled_roster_is_the_seven_committee_skills(self):
        assert SYNC.ROSTER == ("daedalus", "pivot", "pythagoras", "pythia", "thales", "toro",
                               "ursa")

    def test_every_file_exists(self):
        for name, p in _all_eight():
            assert os.path.isfile(p), "%s missing: %s" % (name, p)

    def test_all_eight_are_byte_identical(self):
        """THE assertion. Hashed on raw bytes, so a copy that differs only in line endings fails
        here too -- the eight must be identical on disk, not merely equivalent when decoded."""
        hashes = {name: SYNC.sha256(p) for name, p in _all_eight()}
        want = hashes["_shared"]
        drifted = {n: h for n, h in hashes.items() if h != want}
        assert not drifted, ("author is %s; drifted: %s -- run "
                             "`python scripts/sync_committee_rules.py`" % (want[:16], drifted))

    def test_no_directory_outside_the_roster_carries_a_copy(self):
        """Drift in the other direction: a copy nobody ruled into existence becomes a ninth
        writer, and `--check` would never look at it if the roster were discovered instead of
        declared."""
        assert SYNC.discovered() == SYNC.ROSTER

    def test_the_audit_the_operator_runs_passes(self):
        ok, lines = SYNC.audit()
        assert ok, "\n".join(lines)


class TestTheAuditCanActuallyFail:
    """POSITIVE CONTROLS (#30), on a real tree built in tmp -- not on a mock of the comparison."""

    def _tree(self, tmp_path):
        root = str(tmp_path / "repo")
        os.makedirs(os.path.join(root, "skills", "_shared"))
        for a in SYNC.ROSTER:
            os.makedirs(os.path.join(root, "skills", a, "_shared"))
        shutil.copyfile(SYNC.author_path(), SYNC.author_path(root))
        for a in SYNC.ROSTER:
            shutil.copyfile(SYNC.author_path(), SYNC.copy_path(a, root))
        return root

    def test_the_unmutated_tree_passes(self, tmp_path):
        ok, lines = SYNC.audit(self._tree(tmp_path))
        assert ok, "\n".join(lines)

    def test_one_drifted_copy_fails_and_is_NAMED(self, tmp_path):
        root = self._tree(tmp_path)
        with io.open(SYNC.copy_path("ursa", root), "ab") as fh:
            fh.write(b"\r\nstale\r\n")
        ok, lines = SYNC.audit(root)
        assert ok is False
        assert any("ursa" in l and "DRIFTED" in l for l in lines), lines

    def test_a_one_byte_difference_is_enough(self, tmp_path):
        """A whitespace-only edit to a copy is still a second author, so it must fail."""
        root = self._tree(tmp_path)
        p = SYNC.copy_path("toro", root)
        raw = io.open(p, "rb").read()
        io.open(p, "wb").write(raw + b" ")
        ok, _ = SYNC.audit(root)
        assert ok is False

    def test_a_deleted_copy_fails(self, tmp_path):
        root = self._tree(tmp_path)
        os.remove(SYNC.copy_path("pivot", root))
        ok, lines = SYNC.audit(root)
        assert ok is False
        assert any("pivot" in l for l in lines), lines

    def test_an_unruled_extra_copy_fails(self, tmp_path):
        root = self._tree(tmp_path)
        extra = os.path.join(root, "skills", "helios", "_shared")
        os.makedirs(extra)
        shutil.copyfile(SYNC.author_path(), os.path.join(extra, "COMMITTEE_RULES.md"))
        ok, lines = SYNC.audit(root)
        assert ok is False
        assert any("UNRULED COPY" in l and "helios" in l for l in lines), lines

    def test_regenerate_repairs_drift(self, tmp_path):
        root = self._tree(tmp_path)
        io.open(SYNC.copy_path("thales", root), "wb").write(b"wrong")
        assert SYNC.audit(root)[0] is False
        assert "thales" in SYNC.regenerate(root)
        assert SYNC.audit(root)[0] is True


class TestTheAppliedRulesText:
    """Pins R-IV.735(b) in all eight files, so a revert fails here by name."""

    @pytest.mark.parametrize("marker", APPLIED_MARKERS)
    def test_the_marker_is_in_every_copy(self, marker):
        for name, p in _all_eight():
            assert marker in _text(p), "%s is missing: %r" % (name, marker[:60])

    @pytest.mark.parametrize("old", SUPERSEDED)
    def test_the_superseded_bullet_is_no_longer_an_active_rule(self, old):
        for name, p in _all_eight():
            assert old not in _text(p), "%s still carries: %r" % (name, old[:60])

    def test_the_old_wording_IS_still_quoted_in_the_retired_list(self):
        """Not a formality: SECTION A retires the old rules by NAMING them. If the retirement
        entries were lost, an agent reading the file would have no record that the previous
        wording was wrong rather than merely absent, and the next ruling could reinstate it."""
        t = _text(SYNC.author_path())
        head, _, retired = t.partition("### Retired, do not reinstate")
        assert retired, "the Retired list is gone"
        for quoted in ("FIDELITY_ROTH — ONE account (Roth / 401(k) / 403(b) / BrokerageLink",
                       "20% portfolio risk cap — FIDELITY_ROTH only."):
            assert quoted in retired, quoted[:50]
            assert quoted not in head, "%r appears ABOVE the Retired list" % quoted[:50]

    def test_the_paragraph_below_the_replaced_section_survived(self):
        """R-IV.735(b): change nothing else. Line 150 onward was outside the replacement."""
        t = _text(SYNC.author_path())
        assert "Each agent's `SKILL.md` may add a short agent-specific note" in t
        assert "## § Knowledge Architecture" in t

    def test_the_seven_untouched_bullets_between_the_two_replacements_survived(self):
        """SECTION B replaced two bullets that are NOT adjacent -- seven others sit between them,
        and an in-place replacement that treated the pair as one block would have eaten them."""
        t = _text(SYNC.author_path())
        for bullet in ("**B3 daily circuit breaker — UNCHANGED.**",
                       "**No averaging down.**",
                       "**Two contracts minimum, whenever the sleeve allows it.**",
                       "**X3 — exits by structure.**",
                       "**X4 — reachability (DAEDALUS hard rule).**",
                       "**X7 — max loss for the portfolio cap",
                       "**X10 — flow confirms, it does not originate.**"):
            assert bullet in t, bullet
