"""B9's mock: the global markets + commodities tracker. R-IV.1265(e).

THE DOCUMENT WAS VERIFIED BEFORE ANY OF THIS WAS WRITTEN, which is the clause R-IV.1224(f)
added for a reason: three hashes have governed this one document, and the copy sitting on this
machine before the ferry was the TWICE-SUPERSEDED `5c97eeea...`. Building from it would have
committed exactly the error the re-verification clause exists to prevent, so the hash is
asserted here too -- a verification that happened once and was not written down is a
verification the next reader has to repeat.

WHAT THESE PIN, each because the amendment it comes from says why:

1. THE RACE IS EQUITY ONLY (amendment 1). "A race is a comparison, and comparing an equity
   index's recovery with gold's is a comparison of two different things on one axis." A
   commodity in the race is a REFUSAL, not a filter: silently dropping it would leave a caller
   believing it raced eleven markets when it raced seven.
2. THE RETURN BASIS IS LABELLED (amendment 2). Adj Close, "USD total return" -- a reader who
   assumes price return misreads a year of VGK by its yield.
3. EVERY LABEL CARRIES ITS MEASURED FREQUENCY (amendment 3). A threshold whose frequency is not
   stated is a threshold nobody can calibrate against.
4. ONE CHINA PROXY (amendment 4). FXI stands, MCHI is superseded -- not both.
5. THE COLUMN ORDER IS AN ORDER OF AUTHORITY (amendments 6-7). The footnote reorders the
   columns' standing: the first is the measure history supports in 8 of 9 episodes, the last in
   2 of 9.
6. THE FOOTNOTE IS VERBATIM (amendment 7). Not paraphrased, not reflowed.
7. THE REFRAME SUPERSEDES THE ASIA FRAMING. No Asia-specific panel exists, the keep-out list
   forbids the labels, and the bias check's own line is the test: the tool must be as loud when
   SPY reclaims first as when any other market does -- so SPY and QQQ are IN the race.
8. "1 of 10" IS WITHDRAWN and no panel states it.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))

from services import b9_world as b9                                 # noqa: E402

DOC = pathlib.Path(r"C:\temp\cc-query-handoff") / b9.DOC_FILE


def _mock():
    return b9.load_mock()


# ── the document ─────────────────────────────────────────────────────────────

def test_the_governing_document_still_hashes_to_what_the_ruling_named():
    if not DOC.exists():
        pytest.skip("%s is not on this machine; the hash cannot be checked here" % DOC)
    assert hashlib.sha256(DOC.read_bytes()).hexdigest() == b9.DOC_SHA256


def test_the_superseded_copies_are_recorded_so_one_cannot_be_used_by_mistake():
    """Three hashes have governed this document. The one that was on disk before the ferry is
    the oldest, and nothing in the repo distinguished them until now."""
    assert b9.DOC_SHA256 not in b9.DOC_SUPERSEDED
    assert any(h.startswith("5c97eeea") for h in b9.DOC_SUPERSEDED)
    assert any(h.startswith("75c4ba39") for h in b9.DOC_SUPERSEDED)


def test_the_fixture_records_the_same_hash():
    assert _mock()["governing_document"]["sha256"] == b9.DOC_SHA256


# ── 1 · the race is equity only ──────────────────────────────────────────────

def test_the_race_universe_is_the_seven_plus_spy_and_qqq():
    assert b9.RACE_UNIVERSE == ("EWJ", "FXI", "EWY", "EWT", "INDA", "EEM", "VGK", "SPY", "QQQ")
    assert len(b9.RACE_UNIVERSE) == 9


def test_spy_and_qqq_are_in_the_race_which_is_the_bias_checks_own_test():
    """"The tool must be as loud when SPY reclaims first as when Asia does." A race that left
    the US out could not be."""
    rows = [{"ticker": t} for t in ("SPY", "QQQ", "EWJ")]
    assert [r["ticker"] for r in b9.race_rows(rows)] == ["SPY", "QQQ", "EWJ"]


@pytest.mark.parametrize("ticker", ["GLD", "CPER", "USO", "DBA"])
def test_a_commodity_in_the_race_is_refused_and_not_filtered(ticker):
    with pytest.raises(ValueError) as e:
        b9.race_rows([{"ticker": ticker}])
    assert "commodity" in str(e.value) and "separate context list" in str(e.value)


def test_the_four_commodities_are_their_own_list_with_the_reason_on_it():
    m = _mock()
    assert [c["ticker"] for c in m["commodities"]] == list(b9.COMMODITIES)
    assert "never raced" in m["commodities_note"]
    raced = {r["ticker"] for r in m["recovery_race"]["rows"]}
    assert not (raced & set(b9.COMMODITIES))


def test_the_race_rows_are_exactly_the_race_universe():
    raced = {r["ticker"] for r in _mock()["recovery_race"]["rows"]}
    assert raced == set(b9.RACE_UNIVERSE), sorted(raced ^ set(b9.RACE_UNIVERSE))


# ── 2 · the return basis ─────────────────────────────────────────────────────

def test_the_return_basis_is_labelled_on_the_fixture():
    m = _mock()
    assert m["return_basis"] == b9.RETURN_BASIS == "USD total return"
    assert "dividends are included" in m["return_basis_note"]
    assert "VGK" in m["return_basis_note"], (
        "the note must name the holding the mislabel would hurt most")


# ── 3 · the labels and their measured frequency ──────────────────────────────

@pytest.mark.parametrize("z,expected", [
    (0, None), (1.99, None), (-1.99, None),
    (2.0, b9.UNUSUAL), (-2.0, b9.UNUSUAL), (2.9, b9.UNUSUAL),
    (3.0, b9.EXTREME), (-3.0, b9.EXTREME), (9.0, b9.EXTREME),
])
def test_the_label_for_a_z_score_including_both_edges(z, expected):
    assert b9.label_for(z) == expected


def test_a_missing_z_is_not_a_normal_day():
    assert b9.label_for(None) is None
    assert b9.label_for(float("nan")) is None
    assert b9.label_for("x") is None


def test_the_labels_are_b3s_and_not_a_new_vocabulary():
    assert b9.UNUSUAL == "UNUSUAL" and b9.EXTREME == "EXTREME"
    from models import yield_curve_b3 as b3
    assert b9.UNUSUAL == b3.UNUSUAL and b9.EXTREME == b3.EXTREME
    assert (b9.UNUSUAL_Z, b9.EXTREME_Z) == (b3.UNUSUAL_Z, b3.EXTREME_Z)


def test_every_label_carries_its_measured_fires_per_year():
    for label in (b9.UNUSUAL, b9.EXTREME):
        tip = b9.tooltip_for(label)
        assert tip and b9.FIRES_PER_YEAR[label] in tip
        assert "excluding today" in tip
    assert b9.tooltip_for(None) is None
    assert b9.FIRES_PER_YEAR == {"UNUSUAL": "14-16/yr", "EXTREME": "2.6-3.8/yr"}


def test_today_is_excluded_from_its_own_denominator():
    """Included, a large move inflates the window it is scored against and scores LOWER than it
    should -- the move the test exists to catch is the one it would understate."""
    assert b9.Z_EXCLUDES_TODAY is True and b9.Z_WINDOW == 60
    note = _mock()["labels"]["note"]
    assert "excluded" in note and "inflates its own denominator" in note


# ── 4 · one China proxy ──────────────────────────────────────────────────────

def test_fxi_stands_and_mchi_is_refused():
    assert "FXI" in b9.RACE_UNIVERSE and "MCHI" not in b9.RACE_UNIVERSE
    with pytest.raises(ValueError) as e:
        b9.race_rows([{"ticker": "MCHI"}])
    assert "superseded by FXI" in str(e.value)


def test_mchi_appears_nowhere_in_the_fixture():
    assert "MCHI" not in json.dumps(_mock())


# ── 5 and 6 · the columns and the footnote ───────────────────────────────────

def test_the_column_order_is_the_amendments():
    assert b9.RACE_COLUMNS == ("gained most since SPY's low", "first back above 200d",
                               "first to accept higher prices", "fell least")
    assert _mock()["recovery_race"]["columns"] == list(b9.RACE_COLUMNS)


def test_the_column_order_is_an_order_of_authority_and_the_panel_says_so():
    note = _mock()["recovery_race"]["column_authority_note"]
    assert "history supports" in note and "did not" in note


def test_the_footnote_is_verbatim():
    """Amendment 7: not paraphrased, not reflowed. Compared character for character."""
    expected = ("US selloffs since 2003 (9 episodes; equity ETFs; USD total return; "
                "QUERY 2026-10-18): the 'gained most' leader still led SPY 6 months later in "
                "8 of 9, 'fell least' in 2 of 9. History, not a forecast.")
    assert b9.RACE_FOOTNOTE == expected
    assert _mock()["recovery_race"]["footnote"] == expected


def test_the_footnote_is_a_worked_example_of_convention_37():
    """Source, universe and as-of in the SAME SENTENCE as the figure."""
    f = b9.RACE_FOOTNOTE
    for part in ("QUERY 2026-10-18", "9 episodes", "equity ETFs", "USD total return",
                 "8 of 9", "2 of 9"):
        assert part in f, part
    assert f.index("QUERY 2026-10-18") < f.index("8 of 9"), (
        "the source must sit in the same sentence as the figure, before it")


# ── 7 · the reframe, and the keep-out list ───────────────────────────────────

def test_the_panel_is_market_neutral_and_not_an_asia_thesis():
    panel = _mock()["new_leader_panel"]
    assert panel["title"] == "A NEW LEADER IS REAL IF"
    assert "every market" in panel["note"] and "US included" in panel["note"]
    assert len(panel["confirms"]) == 3 and len(panel["refutes"]) == 3


def test_no_string_in_the_fixture_breaks_the_keep_out_list_or_reads_as_an_order():
    findings = b9.lint_findings(_mock())
    assert not findings, "B9 keep-out / no-orders findings:\n  " + "\n  ".join(findings)


@pytest.mark.parametrize("bad", [
    "buy Asia on the rebound", "a generational buy", "dominance score 7",
    "thesis score rising", "the Asian century", "Asian dominance",
    "this predicts the US open", "GDP growth of 5%",
])
def test_the_keep_out_lint_can_actually_fail(bad):
    assert b9.keep_out_findings(bad), bad


@pytest.mark.parametrize("ok", [
    "Asia", "China large-cap", "Japan", "EEM is the dominant mover",
    "the ratio's 200-day", "USD total return",
])
def test_the_keep_out_lint_allows_what_the_document_does_not_forbid(ok):
    """The document rules out the LABELS, not the continent. A substring ban on "asia" would
    forbid the panel from naming the markets it tracks."""
    assert not b9.keep_out_findings(ok), ok


def test_the_order_lint_is_the_playbook_one_and_not_a_second_copy():
    from pathlib import Path
    src = Path(_BACKEND / "services" / "b9_world.py").read_text(encoding="utf-8")
    assert "from services.regime_playbook import order_findings" in src
    assert "def order_findings" not in src


# ── 8 · the withdrawn line, and the recollection caveat ──────────────────────

def test_the_withdrawn_dry_run_line_appears_nowhere():
    """"1 of 10" is WITHDRAWN. A panel stating it would be quoting a figure the board pulled."""
    blob = json.dumps(_mock())
    assert "1 of 10" not in blob
    assert "1 of 10" not in b9.RACE_FOOTNOTE


def test_the_recollection_caveat_is_on_the_surface_and_not_only_in_the_document():
    """"Every historical figure below is the seats' recollection. No live data or web was used."
    A panel built from recalled figures that does not say so launders recollection into data."""
    m = _mock()
    assert "recollection" in m["caveat"] and "not a measurement" in m["caveat"]
    assert "race footnote" in m["caveat"], (
        "the caveat must name the one figure that IS measured, or it reads as distrusting that "
        "too")
    assert b9.RECOLLECTION_CAVEAT.startswith("Every historical figure")


def test_the_mock_is_labelled_a_mock_and_its_ranks_say_they_are_illustrative():
    m = _mock()
    assert "MOCK" in m["badge"].upper()
    assert "illustrative" in m["recovery_race"]["anchor_note"]


# ── the rest of the synthesis's own numbers ──────────────────────────────────

def test_meltdown_arms_at_ten_percent_below_the_252_day_high():
    """The PIVOT synthesis's figure, not THALES's 15%: the synthesis is the design and a seat's
    own number is an input to it."""
    assert b9.MELTDOWN_DRAWDOWN_PCT == 10.0 and b9.MELTDOWN_HIGH_SESSIONS == 252
    assert "10%" in _mock()["meltdown"]["arms_at"]
    assert "252-day high" in _mock()["meltdown"]["arms_at"]


def test_a_not_armed_meltdown_says_why_rather_than_being_blank():
    md = _mock()["meltdown"]
    assert md["armed"] is False and md["reason_not_armed"]
    assert "inside the 10% arming level" in md["reason_not_armed"]


def test_nothing_is_pushed_from_the_mock_and_it_says_so():
    assert "Nothing is sent from this mock" in _mock()["meltdown"]["push_note"]


def test_the_currency_gap_flag_and_the_commodity_flags_are_the_documents():
    assert b9.CURRENCY_GAP_FLAG_PP == 1.5
    assert b9.CRUDE_ATR_FLAG == 2.0
    assert b9.USDJPY_5D_FLAG_PCT == -3.0
    flags = [c.get("flag") for c in _mock()["cross_reads"]]
    assert any(f and "2 ATR" in f for f in flags)
    assert any(f and "\u22123%" in f for f in flags)


def test_the_overnight_label_is_the_documents_words():
    assert b9.OVERNIGHT_LABEL == "reacting to the prior US close \u00b7 context, not a forecast"
    assert _mock()["overnight"]["label"] == b9.OVERNIGHT_LABEL


def test_a_holiday_shows_as_stale_with_its_reason():
    rows = _mock()["overnight"]["rows"]
    stale = [r for r in rows if r.get("stale")]
    assert stale and all(r.get("stale_reason") for r in stale)


def test_a_leadership_change_shows_how_far_through_confirmation_it_is():
    lc = _mock()["leadership_change"]
    assert lc["state"] == "EMERGING" and lc["held_sessions"] < lc["confirm_after"] == 10
    assert "flicker" in lc["basis"], "a reader must know it can reset"


# ── the renderer ─────────────────────────────────────────────────────────────

V2JS = _REPO / "frontend" / "v2.js"


def _src():
    from ._srcscan import read_source
    return read_source(str(V2JS))


def test_the_section_renders_beside_leadership_which_is_where_the_synthesis_puts_it():
    """"section 7 of the left Regime pop-out, next to the leadership ratios." So pvWorld sits
    between pvLead and pvRates, and the ORDER is the assertion -- a section appended at the end
    would also be "in the drawer" and would not be next to anything."""
    src = _src()
    lead = src.index("pvLead(S.leadership)")
    world = src.index("pvWorld(_b9Mock)")
    rates = src.index("pvRates(S.rates)", lead)
    assert lead < world < rates, (lead, world, rates)


def test_the_section_carries_its_marker_even_when_the_fixture_has_not_loaded():
    """`pvWorld(null)` must still emit the id, or the headless gate would report a drawer with
    a missing section as a pass on a slow fetch."""
    src = _src()
    fn = src[src.index("function pvWorld("):]
    fn = fn[:fn.index("  // ── end b9")] if "end b9" in fn else fn[:4000]
    head = fn[:fn.index("const L =")] if "const L =" in fn else fn[:900]
    assert 'id="pv-world"' in head, head[:400]
    assert "pvNa(" in head


def test_the_popout_gate_knows_about_the_new_section():
    gate = (_REPO / "scripts" / "check_pop_v2.js").read_text(encoding="utf-8")
    assert "pv-world" in gate
    assert "10 global markets (B9)" in gate


def test_no_backtick_appears_inside_the_injected_stylesheet():
    """A backtick ends the template literal. One in a CSS comment closed NB_CSS mid-block
    earlier today and the whole file stopped parsing; `node --check` caught it, and node is
    skipped when it is not installed, so this assertion needs no node."""
    src = _src()
    i = src.index("const PW_CSS = `") + len("const PW_CSS = `")
    j = src.index("`;", i)
    assert "`" not in src[i:j]
    assert len(src[i:j]) > 1200, "the block being checked is suspiciously short"


def test_the_renderer_reuses_the_popouts_one_sparkline_and_does_not_add_a_second():
    """Two sparkline renderers in one drawer would eventually scale differently, and two lines
    in the same drawer that are not comparable is worse than one line."""
    src = _src()
    fn = src[src.index("function b9Spark("):src.index("function b9Arrows(")]
    assert "pvSpark(" in fn
    assert "Math.min" not in fn and "Math.max" not in fn, (
        "the scaling belongs to pvSpark, not to a second implementation")


def test_a_z_under_the_unusual_threshold_renders_no_label_at_all():
    """"normal" is not one of the two labels, so nothing is printed. A third label would be a
    vocabulary the amendment does not have (R-IV.925(b))."""
    src = _src()
    fn = src[src.index("function b9ZTag("):src.index("function b9Row(")]
    assert "if (!name) return ''" in fn
    assert "NORMAL" not in fn.upper().replace("UNUSUAL", "").replace("EXTREME", "")


def test_the_meltdown_panel_shows_a_reason_when_it_is_not_armed():
    """A blank panel and "SPY is 3.1% below its 252-day high, inside the 10% arming level" are
    not the same information."""
    src = _src()
    assert "MELTDOWN MODE OFF" in src and "reason_not_armed" in src
