"""The ?card=v21 preview: STALE, DATA STALE and the 200-day row. R-IV.1309(b).

NICK'S DECISION (2026-10-21 17:25 MT, via TA): no v3b. The card stays on v2.1 and gains a
display-only 200-day row, with design board 13's three states built mock-first behind one flag.

CONVENTION #42 IS THE SPINE OF THIS FILE. Nothing computes from the 200-day row. It never
changes a label, never feeds a section 2 row, never touches the kill switch. Several tests below
exist only to keep it that way, because a figure on a card is exactly the kind of thing a later
reader reaches for when they want a number.

WHY THE DEFINITION IS PINNED SO HARD. "Above the 200-day" has three plausible readings and they
disagree on the day that matters -- strict close vs the SMA200 including that day (the PR-6
baseline, and the one used here), close vs an SMA200 of the prior 200 sessions, and close vs the
line as of the prior session. They differ by a day at every crossing, so "ABOVE since
2026-04-08" is simply wrong if read against a definition it did not use.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from models.regime_inputs import Bar                               # noqa: E402
from models.regime_ma200 import (ABOVE, BELOW, BASIS,              # noqa: E402
                                 DRIFT_CAVEAT, WINDOW, ma200_row, row_text, sides)
from services.regime_card_v21 import (CAVEAT, COST_LINE,           # noqa: E402
                                      load_fixture, lint_card_mock)

from ._srcscan import read_source                                  # noqa: E402

V2JS = str(_BACKEND.parent / "frontend" / "v2.js")
SERVICE = str(_BACKEND / "services" / "read_only" / "regime_strategy.py")


def _bars(closes, start=1):
    return [Bar(date="2026-%02d-%02d" % ((i // 28) % 12 + 1, (i % 28) + 1),
                c=closes[i], h=closes[i], l=closes[i], v=1e6)
            for i in range(len(closes))]


# ── the definition ──────────────────────────────────────────────────────────

def test_the_comparison_is_STRICT_so_a_close_ON_the_line_is_not_above_it():
    """`>=` would flip the side on a tie, and a flat series is exactly the case that produces
    one -- every close equals the average. MEASURED, because a tie is the only input that can
    tell the two comparisons apart."""
    flat = _bars([100.0] * (WINDOW + 40))
    assert sides(flat)[-1] == BELOW
    assert ma200_row(flat)["side"] == BELOW


def test_the_average_INCLUDES_the_session_being_judged():
    """The PR-6 baseline. A series whose last close is the only one above its own window must
    read ABOVE; if the average excluded that close the answer would be the same, so the test
    uses an arithmetic identity instead: the reported `ma` must equal the mean of the last 200
    closes INCLUDING the newest."""
    closes = [100.0] * (WINDOW - 1) + [200.0]
    row = ma200_row(_bars(closes))
    assert row["ma"] == pytest.approx(sum(closes[-WINDOW:]) / WINDOW, abs=0.01)
    assert row["close"] == 200.0
    assert row["side"] == ABOVE


def test_the_basis_is_CARRIED_not_left_to_be_inferred():
    row = ma200_row(_bars([100.0 + i for i in range(WINDOW + 10)]))
    assert row["basis"] == BASIS
    assert "including that day" in BASIS and "PR-6" in BASIS


# ── the run ─────────────────────────────────────────────────────────────────

def test_the_run_starts_on_the_session_the_SIDE_BEGAN():
    """"since" names the first session OF THIS RUN, not the last session of the previous one.
    An off-by-one here dates every crossing a day early."""
    closes = [100.0] * (WINDOW + 10) + [100.0 + i * 1.5 for i in range(1, 31)]
    row = ma200_row(_bars(closes))
    sd = sides(_bars(closes))
    first = len(sd) - row["sessions"]
    assert sd[first] == row["side"]
    assert first == 0 or sd[first - 1] != row["side"]


def test_a_crossing_older_than_the_window_is_reported_as_a_FLOOR():
    """Dating the run to the oldest loaded bar would read as a crossing that happened there.
    `window_bounded` says "at least this long" instead, and `row_text` prints "at least"."""
    row = ma200_row(_bars([100.0 + i for i in range(WINDOW + 5)]))
    assert row["window_bounded"] is True
    assert "at least" in row_text(row)


def test_a_crossing_INSIDE_the_window_is_dated_exactly():
    closes = [100.0] * (WINDOW + 10) + [100.0 + i * 1.5 for i in range(1, 31)]
    row = ma200_row(_bars(closes))
    assert row["window_bounded"] is False
    assert "at least" not in row_text(row)
    assert row["sessions"] == 30


# ── refusals ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("n", [0, 1, 50, WINDOW - 1])
def test_too_few_closes_is_a_STATED_REFUSAL_not_a_side(n):
    """A row that reported BELOW on a short series would be a claim built from nothing -- the
    fault class this whole lane files most often."""
    row = ma200_row(_bars([100.0] * n))
    assert row["available"] is False
    assert str(WINDOW) in row["reason"]
    assert row_text(row) is None


def test_bars_with_no_close_are_SKIPPED_rather_than_counted():
    bars = _bars([100.0] * (WINDOW + 5))
    bars[0] = Bar(date="2026-01-01", c=None, h=None, l=None, v=1e6)
    assert ma200_row(bars)["available"] is True


# ── #42: it computes nothing ────────────────────────────────────────────────

def test_the_row_SAYS_it_is_display_only():
    assert ma200_row(_bars([100.0 + i for i in range(WINDOW + 10)]))["display_only"] is True


def test_NOTHING_in_the_classifier_or_the_inputs_imports_this_module():
    """CONVENTION #42, asserted structurally. The row must never become an input: a figure on a
    card is what a later reader reaches for when they want a number, and an import is the first
    step. The classifier, the input builders and the hysteresis must not know it exists."""
    for mod in ("regime_classifier.py", "regime_inputs.py", "regime_inputs_v2.py",
                "regime_hysteresis.py"):
        src = read_source(str(_BACKEND / "models" / mod))
        assert "regime_ma200" not in src, mod
    job = read_source(str(_BACKEND / "jobs" / "regime_job.py"))
    assert "regime_ma200" not in job, "the nightly must not read it either"


def test_the_only_readers_are_the_READ_PATH_and_the_tests():
    """If a third importer appears, it needs a ruling -- which is what this test is for."""
    hits = []
    for path in sorted(_BACKEND.rglob("*.py")):
        if "__pycache__" in str(path) or path.name.startswith("test_"):
            continue
        if "regime_ma200" in path.read_text(encoding="utf-8"):
            hits.append(path.name)
    # EXACTLY ONE production reader: the card's read path. `regime_ma200.py` is absent from
    # this list because a module does not name itself -- my first expectation included it and
    # was wrong about the code rather than the other way round.
    assert sorted(hits) == ["regime_strategy.py"], hits


# ── the payload ─────────────────────────────────────────────────────────────

def test_the_payload_serves_the_row_and_loads_SPY_ONLY():
    """`load_designated_series` defaults to fourteen tickers and measures 0.72s; SPY alone is
    0.13s for an identical answer, and this row is about SPY."""
    src = read_source(SERVICE)
    assert '"ma200_row": ma200,' in src
    i = src.index("async def _ma200_row")
    block = src[i:i + 1200]
    assert 'tickers=("SPY",)' in block


def test_the_payload_reader_can_never_break_the_card():
    src = read_source(SERVICE)
    i = src.index("async def _ma200_row")
    block = src[i:i + 1200]
    assert "try:" in block and "except Exception" in block
    assert '"available": False' in block


# ── the fixture ─────────────────────────────────────────────────────────────

def test_the_fixture_lints_clean():
    assert lint_card_mock(load_fixture()) == []


def test_the_fixture_announces_itself_as_a_mock():
    assert load_fixture()["_mock"] is True


def test_the_fixture_carries_all_THREE_board_13_states():
    assert sorted(load_fixture()["states"]) == ["A", "B", "C"]


def test_the_fixture_uses_the_LIVE_payloads_field_names():
    """The whole value of mock-first. A fixture spelling `heldNoMatch` would preview perfectly
    and render nothing once live, which is the fault mock-first exists to prevent."""
    for key, st in load_fixture()["states"].items():
        for field in ("regime_label", "regime_key", "held_no_match", "data_freshness",
                      "costs", "ma200_row"):
            assert field in st, (key, field)


def test_the_whipsaw_line_carries_BOTH_ERAS():
    """R-IV.1311(b). QUERY measured 50.00% (19 of 38) since 2013 against 44.79% (43 of 96)
    since 1999, and the line this replaces reported only the second.

    THAT UNDERSTATED THE ERA NICK TRADES by five points, on the half of the record that is his.
    One rate over a span that straddles a regime change is an average of two different things,
    and a reader cannot recover either figure from it -- Conventions #37/#38, where here there
    are TWO universes and TWO spans and both have to travel with the numbers.

    Pinned as a PROPERTY (both eras present, in order, with their spans) and as the exact
    string, because a paraphrase of a graded figure is BUILD authoring one (R-IV.925(b)).
    """
    want = ("Whipsaw: 50% of up-crosses since 2013 (45% since 1999) hit a new 60-session low "
            "within 60 sessions. (LAB R-IV.1279)")
    assert DRIFT_CAVEAT == want
    assert CAVEAT == want, "the lint and the model must quote ONE sentence, not two copies"
    # the property, so a future edit that keeps the shape but drops an era still fails
    assert "since 2013" in DRIFT_CAVEAT and "since 1999" in DRIFT_CAVEAT
    assert DRIFT_CAVEAT.index("2013") < DRIFT_CAVEAT.index("1999"), (
        "the era Nick trades leads; the longer history is the parenthetical")
    assert "50%" in DRIFT_CAVEAT and "45%" in DRIFT_CAVEAT
    assert "LAB R-IV.1279" in DRIFT_CAVEAT, "the measurement keeps its source"


def test_the_superseded_single_era_wording_is_GONE_from_every_live_file():
    """The old sentence reported one rate for a span straddling a regime change. It must not
    survive anywhere a reader or a renderer can reach."""
    needle = "were followed by a new 60-session low"
    offenders = []
    for path in sorted(_BACKEND.rglob("*.py")):
        if "__pycache__" in str(path) or path.name == pathlib.Path(__file__).name:
            continue
        if needle in path.read_text(encoding="utf-8"):
            offenders.append(str(path))
    for path in sorted((_BACKEND.parent / "frontend" / "assets" / "regime").glob("*.json")):
        if needle in path.read_text(encoding="utf-8"):
            offenders.append(str(path))
    assert offenders == [], offenders

def test_the_fixtures_sentences_are_the_RULINGS_verbatim():
    for key, st in load_fixture()["states"].items():
        assert COST_LINE in st["costs"], key
        assert st["ma200_row"]["caveat"] == CAVEAT, key
    assert CAVEAT == DRIFT_CAVEAT, "the lint and the model must quote one sentence, not two"


@pytest.mark.parametrize("mutate,expect", [
    (lambda f: f["states"]["B"]["held_no_match"]["decay"].update({"elapsed": 4}), "disagree"),
    (lambda f: f["states"]["C"]["data_freshness"].update({"lag_sessions": 1}), "lag_sessions"),
    (lambda f: f["states"]["A"].update({"costs": ["paraphrased"]}), "verbatim"),
    (lambda f: f["states"]["A"]["ma200_row"].update({"display_only": False}), "display_only"),
    (lambda f: f["states"].pop("B"), "state B is missing"),
])
def test_the_lint_CATCHES_each_fault_it_claims_to(mutate, expect):
    """CONVENTION #30. A lint that has only ever seen a good fixture is a lint nobody has
    tested -- and this one's whole job is to fail in the suite instead of in Nick's browser."""
    f = load_fixture()
    mutate(f)
    assert any(expect in m for m in lint_card_mock(f)), lint_card_mock(f)


def test_state_C_must_not_ALSO_claim_no_rule_matched():
    """The two stalenesses are different faults and the headline can only be one of them."""
    f = load_fixture()
    f["states"]["C"]["held_no_match"] = {"stale": True}
    assert any("distinct states" in m for m in lint_card_mock(f))


# ── the renderer ────────────────────────────────────────────────────────────

def test_every_preview_row_is_GATED_on_the_flag():
    """The live card must be untouched without `?card=v21`. Asserted on each renderer, because
    one unguarded function ships the whole preview to everyone."""
    js = read_source(V2JS)
    for fn in ("rs21Ma200", "rs21Decay", "rs21DataChip", "rs21Cost"):
        i = js.index("function %s(" % fn)
        body = js[i:i + 320]
        assert "if (!CARD_V21) return" in body, fn


def test_the_mock_state_is_only_honoured_WITH_the_flag():
    js = read_source(V2JS)
    i = js.index("const CARD_STATE")
    assert "CARD_V21 &&" in js[i:i + 360], "?state= alone must do nothing"


def test_the_mock_is_MERGED_OVER_a_real_payload_not_substituted_for_it():
    """A fixture that replaced the whole payload would approve a layout against absences the
    live card never has."""
    js = read_source(V2JS)
    i = js.index("async function rs21MockState")
    body = js[i:js.index("function rs21", i + 10)]
    assert "Object.assign({}, live || {}, st" in body
    assert "return live" in body, "no fixture, no change"


def test_an_empty_cost_list_renders_NO_BLOCK():
    """A heading over an empty list reads as a read that failed. On main the display config is
    empty until the cutover merges, so this is the state today."""
    js = read_source(V2JS)
    i = js.index("function rs21Cost(")
    body = js[i:i + 700]
    assert "if (!cs.length) return" in body


def test_the_dim_is_applied_to_the_HOST_not_to_a_row():
    """State C is a statement about everything on the card."""
    js = read_source(V2JS)
    i = js.index("function rs21Dim(")
    body = js[i:i + 420]
    assert "host.classList.toggle('rs-dim'" in body


def test_the_preview_css_is_INJECTED_and_not_added_to_v2_css():
    """v2.css is pinned INDEPENDENTLY by v2.html, stater.html and abacus.html and the three
    values have already diverged, so a rule added there ships three times or reaches a stale
    cache on the pages that were missed."""
    js = read_source(V2JS)
    assert "const RS21_CSS" in js and "rs21-css" in js
    css = read_source(str(_BACKEND.parent / "frontend" / "v2.css"))
    for cls in (".rs-ma200", ".rs-decay", ".rs-datachip", ".rs-cost21"):
        assert cls not in css, cls


def test_each_preview_row_claims_its_OWN_LINE():
    """`.rs-call` is a flex ROW, so `display:block` alone still leaves a child beside its
    siblings -- the first render put the decay bar, its caption and the 200-day row on one line.
    Board 13 makes each of them a row."""
    js = read_source(V2JS)
    i = js.index("const RS21_CSS")
    block = js[i:js.index("function rs21InjectCss", i)]
    for cls in (".rs-ma200{", ".rs-ma200-note{", ".rs-decay{"):
        j = block.index(cls)
        assert "flex:0 0 100%" in block[j:j + 200], cls


def test_the_row_text_comes_from_the_PAYLOAD_so_words_and_numbers_cannot_drift():
    js = read_source(V2JS)
    i = js.index("function rs21Ma200(")
    body = js[i:i + 900]
    assert "row.text" in body
