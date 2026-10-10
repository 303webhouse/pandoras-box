"""R-IV.857(b) PHAETHON to shadow, and R-IV.849(c) guard 1 — Triton's cohort cannot move.

TWO INDEPENDENT THINGS, in one file because both are preconditions on the persistence work and
both are about the same question: what happens to a row that newly saves.

── (b) PHAETHON → SHADOW ───────────────────────────────────────────────────────────────────────
"Stored and graded, not surfaced" is two claims and needs two proofs. The mechanism is L0
suppression, which is a SURFACE verdict and not a kill:

  STORED   the pipeline computes the L0 decision as a SHADOW label into
           `triggering_factors.l0_shadow` and says so in its own comment -- non-blocking. No
           write path consults SUPPRESS_ALWAYS, so a suppressed type still persists and still
           grades. That matters: a type that stopped persisting would stop accumulating the
           record the review needs, which would defeat the shadow.
  NOT      the three actionable READ surfaces -- board_state, positions, trade_ideas -- exclude
  SURFACED would_suppress rows through l0_enforce_where_clause / l0_enforce_filter_rows.

── guard 1: TRITON'S COHORT ────────────────────────────────────────────────────────────────────
R-IV.849(c)1 asks me to show that no WH_ACCUMULATION, WH_REVERSAL or DARK_POOL row CAN enter
Triton's cohort. The answer is structural and stronger than any name test: there is no code path
from `signals` to `triton_flow_shadow` at all.

  * `triton_flow_shadow` has exactly ONE insert site, `jobs/triton_shadow_poller.py`;
  * it is fed from Unusual Whales' option-FLOW ALERT payloads (uw_alert_id, alert_rule, rule_id,
    strike, expiry, total_ask_side_prem), not from the signals table;
  * it is keyed `ON CONFLICT (uw_alert_id) DO NOTHING`, and a signals row has no uw_alert_id;
  * §8.1's three population handles are DATE (`fired_at >= T0`), ID (one-directional, "never
    selects") and grade CLASS (`NOT UNGRADEABLE-NO-SERIES`) -- none of which is a signal_type.

So the populations are disjoint BY TABLE AND BY KEY, not by a filter somebody could widen.

AND THE CASE-INSENSITIVE INSTRUCTION EARNED ITS KEEP, in the opposite direction to the one
expected. R-IV.849(d) warned the stored value is 'Whale_Hunter', not 'whale_hunter'. Searching
Triton's modules case-insensitively for whale/darkpool returns FOUR hits and every one is English
in a docstring -- "whale-flow shadow poller", "a whale print fired". A case-sensitive search for
the stored spelling would have found nothing and looked clean for the wrong reason; the
case-insensitive one finds prose and proves there is no predicate. Both are pinned below so the
distinction survives an edit.
"""
from __future__ import annotations

import io
import os
import re
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

ROOT = __file__.rsplit("tests", 1)[0]

PERSISTENCE_TYPES = ("WH_ACCUMULATION", "WH_REVERSAL", "DARK_POOL", "PHALANX",
                     "BEARISH_BREAKDOWN", "NEMESIS_LONG")


def _src(rel):
    return io.open(os.path.join(ROOT, rel), encoding="utf-8-sig").read()


# ── (b) PHAETHON to shadow ───────────────────────────────────────────────────────────────────
class TestPhaethonIsShadowed:
    def test_BEARISH_BREAKDOWN_is_suppressed_at_the_surface(self):
        from config.l0_routing import SUPPRESS_ALWAYS

        assert "BEARISH_BREAKDOWN" in SUPPRESS_ALWAYS

    def test_the_routing_verdict_is_SUPPRESS(self):
        """Through the real decision function, not by reading the set."""
        from config import l0_routing as l0

        decided = l0.evaluate_l0_gate({"signal_type": "BEARISH_BREAKDOWN", "ticker": "SPY"})
        blob = str(decided).upper()
        assert "SUPPRESS" in blob, decided

    def test_the_comment_states_it_is_a_surface_verdict_not_a_kill(self):
        src = _src(os.path.join("config", "l0_routing.py"))
        assert "R-IV.857(b) shadow" in src
        assert "stored and graded, not surfaced" in src

    def test_the_other_suppressed_types_are_untouched(self):
        """CONTROL (#30). A change that suppressed more than PHAETHON passes the test above."""
        from config.l0_routing import SUPPRESS_ALWAYS

        for t in ("STRIKE_IB_BREAK", "HOLY_GRAIL_1H", "HOLY_GRAIL_15M", "PULLBACK_ENTRY",
                  "TRAPPED_LONGS", "ARTEMIS_LONG", "NEMESIS_LONG"):
            assert t in SUPPRESS_ALWAYS, t
        assert len(SUPPRESS_ALWAYS) == 8
        for t in ("ARTEMIS_SHORT", "TRAPPED_SHORTS", "GOLDEN_TOUCH", "TWO_CLOSE_VOLUME",
                  "DEATH_CROSS"):
            assert t not in SUPPRESS_ALWAYS, t


class TestShadowMeansSTOREDAsWellAsNotSurfaced:
    """The half that is easy to get wrong: suppression must not stop the write."""

    def test_no_write_path_consults_the_suppress_set(self):
        """If `log_signal` or the pipeline's persist step read SUPPRESS_ALWAYS, a shadow type
        would stop accumulating the record its review depends on."""
        for rel in (os.path.join("database", "postgres_client.py"),
                    os.path.join("signals", "pipeline.py")):
            src = _src(rel)
            # The pipeline may EVALUATE the gate (it stores the verdict as a shadow label);
            # what it must not do is gate the INSERT on it. COMMENTS ARE STRIPPED FIRST: my own
            # R-IV.820 comment in pipeline.py says "it is in L0 SUPPRESS_ALWAYS", and a plain
            # substring test failed on that documentation — the same trap as the windowless
            # get_bars call appearing in the comment explaining why it was wrong.
            for line in src.split("\n"):
                code = line.split("#", 1)[0]
                if "SUPPRESS_ALWAYS" in code:
                    pytest.fail("%s consults SUPPRESS_ALWAYS in code: %r" % (rel, line.strip()))

    def test_the_pipeline_treats_the_L0_verdict_as_a_non_blocking_label(self):
        src = _src(os.path.join("signals", "pipeline.py"))
        assert "evaluate_l0_gate(signal_data)" in src
        assert "shadow, non-blocking" in src
        assert '_tf["l0_shadow"] = _l0_decision' in src

    def test_the_actionable_READ_surfaces_are_what_exclude_it(self):
        """board_state, positions and trade_ideas — all three, so a suppressed row cannot reach
        an actionable surface through one that was missed."""
        hits = []
        for rel in (os.path.join("api", "board_state.py"),
                    os.path.join("api", "positions.py"),
                    os.path.join("api", "trade_ideas.py")):
            src = _src(rel)
            if "l0_enforce_where_clause" in src or "l0_enforce_filter_rows" in src:
                hits.append(rel)
        assert len(hits) == 3, "only these enforce L0 at the surface: %s" % hits


# ── guard 1: the cohort ──────────────────────────────────────────────────────────────────────
class TestTritonsCohortCannotMove:
    POLLER = os.path.join("jobs", "triton_shadow_poller.py")

    def test_the_cohort_table_has_exactly_one_writer(self):
        writers = []
        for dirpath, _dirs, files in os.walk(ROOT):
            if "__pycache__" in dirpath or os.sep + "tests" in dirpath:
                continue
            for f in files:
                if not f.endswith(".py"):
                    continue
                p = os.path.join(dirpath, f)
                if "INSERT INTO triton_flow_shadow" in io.open(
                        p, encoding="utf-8-sig", errors="replace").read():
                    writers.append(os.path.relpath(p, ROOT))
        assert writers == [self.POLLER], writers

    def test_that_writer_is_fed_from_UW_FLOW_ALERTS_not_from_signals(self):
        src = _src(self.POLLER)
        for flow_field in ("uw_alert_id", "alert_rule", "rule_id", "total_ask_side_prem"):
            assert flow_field in src, flow_field
        assert "FROM signals" not in src
        assert "INSERT INTO signals" not in src

    def test_the_cohort_is_keyed_on_an_id_a_signals_row_does_not_have(self):
        assert "ON CONFLICT (uw_alert_id) DO NOTHING" in _src(self.POLLER)

    @pytest.mark.parametrize("sig_type", PERSISTENCE_TYPES)
    def test_no_triton_module_selects_on_any_of_these_types(self, sig_type):
        """Case-INSENSITIVE, per R-IV.849(d). Any hit must be prose, never a predicate."""
        for f in sorted(os.listdir(os.path.join(ROOT, "jobs"))):
            if not (f.startswith("triton_") or f.startswith("tide_")) or not f.endswith(".py"):
                continue
            src = _src(os.path.join("jobs", f))
            for i, line in enumerate(src.split("\n"), 1):
                if re.search(re.escape(sig_type), line, re.IGNORECASE):
                    stripped = line.strip()
                    assert stripped.startswith("#") or '"""' in stripped, \
                        "jobs/%s:%d references %s outside a comment: %r" % (
                            f, i, sig_type, stripped)

    def test_the_whale_references_in_triton_are_ENGLISH_not_predicates(self):
        """The case-insensitive search earns its keep in the OPPOSITE direction to the expected
        one: it finds four hits and every one is a docstring. A case-sensitive search for the
        stored spelling 'Whale_Hunter' would have found nothing and looked clean for the wrong
        reason."""
        prose, selectors = 0, []
        pat = re.compile(r"whale|darkpool|dark_pool", re.IGNORECASE)
        # A reference is PROSE when it is a comment, a docstring, or inside a string literal —
        # a log message is prose too, which the first version of this test got wrong: line 166
        # is `logger.info("...new whale prints...")`, executable but not a predicate. What would
        # matter is the word used as a SELECTOR, so that is what this looks for.
        quoted = re.compile(r"""['"][^'"]*(?:whale|darkpool|dark_pool)[^'"]*['"]""",
                            re.IGNORECASE)
        for f in sorted(os.listdir(os.path.join(ROOT, "jobs"))):
            if not f.startswith("triton_") or not f.endswith(".py"):
                continue
            src = _src(os.path.join("jobs", f))
            for i, line in enumerate(src.split("\n"), 1):
                if not pat.search(line):
                    continue
                s = line.strip()
                bare = line.split("#", 1)[0]
                if s.startswith("#") or '"""' in s or not pat.search(bare):
                    prose += 1                      # comment or docstring
                elif quoted.search(bare) and not re.search(
                        r"\b(if|elif|while|WHERE|AND|OR|==|!=|\bin\b)\b", bare):
                    prose += 1                      # a message string, not a predicate
                else:
                    selectors.append("jobs/%s:%d %r" % (f, i, s))
        assert prose >= 4, "expected the prose mentions to still be there, found %d" % prose
        assert not selectors, "a whale/darkpool reference is used as a SELECTOR: %s" % selectors

    def test_no_triton_module_reads_the_signals_table_at_all(self):
        offenders = []
        for f in sorted(os.listdir(os.path.join(ROOT, "jobs"))):
            if not (f.startswith("triton_") or f.startswith("tide_")) or not f.endswith(".py"):
                continue
            src = _src(os.path.join("jobs", f))
            if re.search(r"\bFROM\s+signals\b|\bINTO\s+signals\b", src, re.IGNORECASE):
                offenders.append(f)
        assert not offenders, offenders

    def test_the_registrations_population_handles_are_not_signal_types(self):
        """§8.1: DATE, ID (one-directional, never selects) and grade CLASS. None is a
        signal_type, so there is no handle a new emitter could be caught by."""
        p = os.path.join(ROOT, "..", "docs", "edge", "preregistrations",
                         "2026-09-03-triton-forward-window-registration-JOINT.md")
        if not os.path.exists(p):
            pytest.skip("the JOINT registration is not on disk in this checkout")
        src = io.open(p, encoding="utf-8-sig", errors="replace").read()
        assert "POPULATION HANDLES" in src
        assert "UNGRADEABLE-NO-SERIES" in src
        assert "Selection is by date and class only" in src
        for sig_type in PERSISTENCE_TYPES:
            assert sig_type not in src, "%s appears in the registration" % sig_type
