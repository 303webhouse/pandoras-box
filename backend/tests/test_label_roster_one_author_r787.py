"""The thesis-label roster has ONE author — R-IV.787(c), and its provenance stamp — R-IV.787(d).

THE DEFECT D5 NAMED. The roster was enumerated in four places: `COMMITTEE_RULES § Bias and Thesis
Labels`, `ursa/SKILL.md`, and `thales/SKILL.md` TWICE. Every new label therefore needed four
edits, and the cost had already been paid before anyone noticed:

  * `thales/SKILL.md` line 204 was a label behind -- it omitted `trend-continuation`, which line
    174 in the same file already carried.
  * `ursa/SKILL.md` was TWO behind: no `trend-continuation` and no `credit-stress`.

So the drift was not hypothetical and not new. § Bias and Thesis Labels warns about exactly this
("Don't let labels drift across agent files") in the same sentence as each site's own copy.

Each of those sites already cited the shared list. The enumerations are deleted and the citations
kept, so a new label is one edit in one file and CANNOT drift. URSA's site had no citation at all
-- it read "Common groupings to recognize:" and then listed them -- so one was supplied there.

What is NOT deleted: the per-thesis TELLS in THALES's step 2 and URSA's THESIS GROUPING guidance
bullet. Those are agent guidance -- how to recognise a thesis from the tape and the book -- not
the roster of what the labels are.
"""
import io
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SKILLS = os.path.join(REPO, "skills")
RULES_NAME = "COMMITTEE_RULES.md"

# The canonical source hash R-IV.787(b) gated on.
SOURCE = "claude/account-context-2026-10-08-v5_2.md"
SOURCE_SHA = "2a4a4eaf82c4b9b306f9d0705eee656b8c4e09462ded3a3343fad462b8307b71"


def _md_files():
    for root, _dirs, files in os.walk(SKILLS):
        for f in files:
            if f.endswith(".md"):
                yield os.path.join(root, f)


def _read(p):
    return io.open(p, encoding="utf-8-sig").read().replace("\r\n", "\n")


class TestOnlyTheRulesFileEnumeratesTheRoster:
    def test_the_comma_run_appears_only_in_COMMITTEE_RULES(self):
        """R-IV.787(c)'s own example. Any file enumerating the roster is a second author."""
        offenders = [os.path.relpath(p, REPO) for p in _md_files()
                     if "Iran-escalation, AI-bubble-deflation" in _read(p)
                     and os.path.basename(p) != RULES_NAME]
        assert not offenders, "these enumerate the roster: %s" % offenders

    def test_the_rules_file_itself_still_carries_it(self):
        """POSITIVE CONTROL (#30). The test above passes trivially if the roster vanished
        everywhere, which would be a worse defect than drift."""
        hits = [p for p in _md_files() if os.path.basename(p) == RULES_NAME
                and "Iran-escalation" in _read(p)]
        assert len(hits) == 8, "expected the author plus seven copies, found %d" % len(hits)

    @pytest.mark.parametrize("label", ["Iran-escalation", "AI-bubble-deflation", "Fed-hawkish",
                                       "Trend-continuation", "Credit-stress"])
    def test_every_label_lives_in_the_rules_file(self, label):
        text = _read(os.path.join(SKILLS, "_shared", RULES_NAME))
        assert "- **%s thesis.**" % label in text, label

    def test_ursa_no_longer_enumerates_and_cites_instead(self):
        t = _read(os.path.join(SKILLS, "ursa", "SKILL.md"))
        assert "- **Iran-escalation thesis:**" not in t
        assert "- **Pure macro-bearish bias stack:**" not in t
        assert "§ Bias and Thesis Labels" in t, "the citation must remain"
        assert "Common groupings to recognize:" not in t, "the dangling lead-in must be gone"

    def test_thales_no_longer_enumerates_at_either_site(self):
        t = _read(os.path.join(SKILLS, "thales", "SKILL.md"))
        assert "currently: Iran-escalation" not in t
        assert t.count("§ Bias and Thesis Labels") >= 2, "both citations must remain"

    def test_the_trend_continuation_DRIFT_is_gone_by_construction(self):
        """The drift that proved the point: one site listed trend-continuation and the other did
        not. With no enumeration in either, the two cannot disagree."""
        t = _read(os.path.join(SKILLS, "thales", "SKILL.md"))
        assert "Pure macro-bearish bias stack)" not in t


class TestTheGuidanceSurvived:
    """Deleting the roster must not delete how an agent recognises a thesis."""

    def test_ursas_grouping_guidance_bullet_is_intact(self):
        t = _read(os.path.join(SKILLS, "ursa", "SKILL.md"))
        assert "- **Credit-stress.** Does the book hold short exposure" in t
        assert "short HYG or short" in t, "the Fed-hawkish discriminator must remain"

    def test_thales_keeps_its_per_thesis_tells(self):
        t = _read(os.path.join(SKILLS, "thales", "SKILL.md"))
        for tell in ("- Iran-escalation thesis: oil prices climbing",
                     "- Fed-hawkish thesis: 10y yield rising"):
            assert tell in t, tell

    def test_thales_gained_D3s_two_lines(self):
        t = _read(os.path.join(SKILLS, "thales", "SKILL.md"))
        assert "- Credit-stress thesis: HY spreads widening against IG" in t
        assert "- Credit-stress vs Fed-hawkish: read HY-minus-IG spreads" in t

    def test_the_uncorrected_drafts_bullet_was_removed(self):
        """The first draft put a `- **Credit-stress world-check.**` bullet here. The corrected
        document replaces it with D3's two tells, so leaving it would be a third statement of the
        same thing in the same file."""
        t = _read(os.path.join(SKILLS, "thales", "SKILL.md"))
        assert "- **Credit-stress world-check.**" not in t


class TestTheProvenanceStamp:
    """R-IV.787(d). 'v5.2' names two documents, so the version line alone no longer says which
    bytes were applied."""

    def _rules(self, who="_shared"):
        # The AUTHOR is skills/_shared/COMMITTEE_RULES.md; each COPY is
        # skills/<agent>/_shared/COMMITTEE_RULES.md. My first version omitted the inner
        # `_shared` for the copies, which happened to resolve for the author and not for the
        # seven -- so the test reported a missing stamp while the generator reported all eight
        # identical. The generator was right.
        parts = [SKILLS, RULES_NAME] if who == "_shared" else [SKILLS, who, "_shared", RULES_NAME]
        if who == "_shared":
            parts = [SKILLS, "_shared", RULES_NAME]
        return _read(os.path.join(*parts))

    def test_the_author_carries_the_stamp(self):
        t = self._rules()
        assert "Applied from: %s" % SOURCE in t
        assert SOURCE_SHA in t

    def test_it_sits_AFTER_the_whole_RULES_VERSION_paragraph(self):
        """Not after its first line: that statement is a wrapped sentence, and a generated line
        dropped into the middle of it would cut the sentence it qualifies in half."""
        lines = self._rules().split("\n")
        vi = next(i for i, l in enumerate(lines) if l.startswith("RULES VERSION:"))
        si = next(i for i, l in enumerate(lines) if l.startswith("Applied from: "))
        assert si > vi
        assert lines[si - 1].strip() == "", "a blank line should set the stamp off"
        assert all(lines[i].strip() for i in range(vi, si - 1)), \
            "the stamp must not interrupt the version paragraph"

    @pytest.mark.parametrize("who", ["daedalus", "pivot", "pythagoras", "pythia", "thales",
                                     "toro", "ursa"])
    def test_every_copy_inherits_the_same_stamp(self, who):
        assert "Applied from: %s" % SOURCE in self._rules(who)
        assert SOURCE_SHA in self._rules(who)

    def test_there_is_exactly_one_stamp(self):
        assert self._rules().count("Applied from: ") == 1

    def test_the_generator_is_what_writes_it(self):
        """Generated, not authored. If someone hand-edits the stamp, the next generator run
        overwrites it, which is the correct direction."""
        src = io.open(os.path.join(REPO, "scripts", "sync_committee_rules.py"),
                      encoding="utf-8-sig").read()
        assert "def stamp_applied_from(" in src
        assert "--applied-from" in src
        assert "NO PROVENANCE STAMP" in src, "an unstamped author must FAIL the check"
