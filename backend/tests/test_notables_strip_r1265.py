"""The NOTABLES option strip's wording and its spending cap. R-IV.1265(c)-(d).

(c) RESOLVED A RULING AGAINST ITSELF. R-IV.1259(f) specified the IV-rank tag as "cheap below 30"
and (g) banned the word "cheap" from every card: one ruling requiring and forbidding the same
word in the same place. R-IV.1265(c) settles it by wording -- "IV LOW" / "IV MID" / "IV HIGH" --
and these tests pin BOTH BAND EDGES, because "below 30" and "30-60" could each be read to own
30, and two numbers for one threshold is a fault class already on this board's record.

(d) FIFTY CALLS A DAY, CAPPED TWICE. The governor refuses a tag past its quota, and
`notables_strip` is registered there at 50 with the safety buffer cut from 2,000 to 1,950 to
fund it. The strip caps again on its own, because the governor's enforcement is a MODE and a cap
that holds only while a global switch is in one position is not a cap. Both caps must agree, so
a test compares them rather than trusting two constants to stay equal.
"""
from __future__ import annotations

import json
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))

from integrations import uw_governor as g                           # noqa: E402
from models import notables_strip as ns                             # noqa: E402
from services import notables as N                                  # noqa: E402

from ._srcscan import read_source                                   # noqa: E402

FIXTURE = _REPO / "frontend" / "assets" / "notables" / "notables_mock.v1.json"
V2JS = _REPO / "frontend" / "v2.js"


# ── (c) the bands ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("rank,expected", [
    (0, ns.IV_LOW), (1.5, ns.IV_LOW), (29, ns.IV_LOW), (29.999, ns.IV_LOW),
    (30, ns.IV_MID), (30.001, ns.IV_MID), (45, ns.IV_MID), (59.999, ns.IV_MID),
    (60, ns.IV_MID),
    (60.001, ns.IV_HIGH), (61, ns.IV_HIGH), (100, ns.IV_HIGH),
])
def test_the_band_for_every_rank_including_both_edges(rank, expected):
    assert ns.iv_rank_label(rank) == expected, rank


def test_each_edge_is_owned_by_exactly_one_band():
    """30 and 60 belong to MID and to nothing else. Stated as its own test because the ruling's
    prose ("below 30", "30-60", "above 60") leaves each edge nameable twice."""
    assert ns.iv_rank_label(30) == ns.IV_MID
    assert ns.iv_rank_label(60) == ns.IV_MID
    assert ns.iv_rank_label(29.999) != ns.iv_rank_label(30)
    assert ns.iv_rank_label(60) != ns.iv_rank_label(60.001)


def test_a_missing_rank_renders_no_band_rather_than_the_middle_one():
    """MID is the band a reader is least likely to question, so defaulting to it would be a
    caption lying about its field. None, NaN and unparseable all render nothing."""
    assert ns.iv_rank_label(None) is None
    assert ns.iv_rank_label(float("nan")) is None
    assert ns.iv_rank_label("not a number") is None
    assert ns.iv_rank_tone(None) is None


def test_the_ruled_words_are_the_only_ones_the_strip_can_print():
    assert ns.IV_LABELS == ("IV LOW", "IV MID", "IV HIGH")
    for label in ns.IV_LABELS:
        assert ns.iv_rank_tone(label) in ("low", "mid", "high")


def test_cheap_is_still_banned_and_no_band_label_trips_the_lint():
    """(c) keeps "cheap" banned everywhere. The new labels must be clean under the SAME lint, or
    the resolution would have replaced one contradiction with another."""
    assert "cheap" in N.SALES_WORDS
    for label in ns.IV_LABELS:
        assert not N.sales_findings(label), label
    assert N.sales_findings("this one is cheap"), "the ban must still bite"


def test_the_retired_words_are_gone_from_the_fixture_and_the_renderer():
    """(f)'s "rich" and "neutral" were its wording, not the board's, and they are retired with
    it. Checked on the FIXTURE and on the renderer's tone classes, which is where they lived."""
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    tones = []
    for card in fixture["watch"]:
        for key in ("strip", "compact_strip"):
            block = card.get(key) or {}
            ivr = block.get("iv_rank")
            if ivr:
                tones.append(ivr.get("tone"))
                assert ivr["label"].startswith(("IV LOW", "IV MID", "IV HIGH")), ivr
    assert tones and set(tones) <= {"low", "mid", "high"}, tones
    src = read_source(str(V2JS))
    assert ".nb-ivr.rich" not in src and ".nb-ivr.neutral" not in src
    for cls in (".nb-ivr.low", ".nb-ivr.mid", ".nb-ivr.high"):
        assert cls in src, cls


def test_the_conflict_and_its_resolution_are_both_on_the_record():
    """The text stays rather than being deleted: a reader of a card that says "IV LOW" should be
    able to find out why it does not say what (f) says."""
    assert "RESOLVED by R-IV.1265(c)" in N.IV_RANK_CONFLICT
    assert N.IV_RANK_CONFLICT_RESOLVED_BY == "R-IV.1265(c)"
    for word in ("IV LOW", "IV MID", "IV HIGH"):
        assert word in N.IV_RANK_CONFLICT, word


# ── the injected stylesheet is a template literal ────────────────────────────

def test_no_backtick_appears_inside_the_injected_stylesheet():
    """A BACKTICK ENDS THE TEMPLATE LITERAL. A CSS comment written with backticks around a
    filename closed NB_CSS mid-block and the whole file stopped parsing -- caught by `node`,
    which the parse test skips when node is absent. This assertion does not need node.
    """
    src = read_source(str(V2JS))
    start = src.index("const NB_CSS = `") + len("const NB_CSS = `")
    end = src.index("`;", start)
    assert "`" not in src[start:end], "a backtick inside NB_CSS ends the template literal"
    assert len(src[start:end]) > 2000, "the block being checked is suspiciously short"


# ── (d) the cap ──────────────────────────────────────────────────────────────

def test_the_two_caps_agree():
    """One in the governor's table, one in the strip. Compared rather than trusted: two
    constants meant to be equal are two places to change one number."""
    quota, tier = g.QUOTAS[ns.UW_CALLER]
    assert quota == ns.DAILY_CALL_CAP == 50, (quota, ns.DAILY_CALL_CAP)
    assert tier == g.TIER_STANDARD, (
        "display-only (#42) must not compete with the reads that mark the book", tier)


def test_the_quota_came_from_the_buffer_and_the_table_still_fits():
    """R-IV.1265(d): carved from the 2,000 buffer, which becomes 1,950. The table summed to
    exactly the old target, so this is the only change that funds the tag without reopening a
    measured sizing."""
    from integrations.uw_api_cache import DAILY_BUDGET
    assert g.QUOTA_SAFETY_BUFFER == 1950
    total = sum(q for q, _ in g.QUOTAS.values())
    assert total == DAILY_BUDGET - g.QUOTA_SAFETY_BUFFER == 26050, total


def test_the_tag_is_logged_beside_the_others():
    """(d)'s third clause. The count is not a private tally: the tag is in the governor's table,
    so `/api/uw/governor` reports it with the other 38 and the same ledger feeds both."""
    assert ns.UW_CALLER in g.QUOTAS
    src = read_source(str(_BACKEND / "models" / "notables_strip.py"))
    assert "get_caller_count_or_none" in src, "the count must come from the governor's ledger"
    assert "get_caller_count(" not in src.replace("get_caller_count_or_none", ""), (
        "the OR_NONE variant only: get_caller_count returns 0 on a failed read, which lets a "
        "cap fail open to unlimited")


@pytest.mark.asyncio
async def test_at_the_cap_the_strip_says_options_data_unavailable(monkeypatch):
    async def at_cap(_caller):
        return 50
    monkeypatch.setattr("integrations.uw_api_cache.get_caller_count_or_none", at_cap)
    state = await ns.budget_state()
    assert state["allowed"] is False
    assert state["text"] == "Options data unavailable — chart only"
    assert state["remaining"] == 0 and state["used"] == 50
    assert "1265(d)" in state["reason"]


@pytest.mark.asyncio
async def test_under_the_cap_it_allows_and_reports_what_is_left(monkeypatch):
    async def used(_caller):
        return 7
    monkeypatch.setattr("integrations.uw_api_cache.get_caller_count_or_none", used)
    state = await ns.budget_state()
    assert state["allowed"] is True and state["remaining"] == 43
    assert state["text"] is None


@pytest.mark.asyncio
async def test_an_unreadable_counter_refuses_rather_than_spending(monkeypatch):
    """None is NOT zero. An unreadable counter read as "nothing spent" is what lets a cap fail
    open to unlimited, which is the fault `get_caller_count_or_none` exists for."""
    async def unknown(_caller):
        return None
    monkeypatch.setattr("integrations.uw_api_cache.get_caller_count_or_none", unknown)
    state = await ns.budget_state()
    assert state["allowed"] is False
    assert state["used"] is None and state["remaining"] is None
    assert state["text"] == ns.UNAVAILABLE_TEXT
    assert "could not be read" in state["reason"]


@pytest.mark.asyncio
async def test_a_raising_counter_is_also_a_refusal(monkeypatch):
    async def boom(_caller):
        raise RuntimeError("redis down")
    monkeypatch.setattr("integrations.uw_api_cache.get_caller_count_or_none", boom)
    state = await ns.budget_state()
    assert state["allowed"] is False and state["text"] == ns.UNAVAILABLE_TEXT


# ── the spread light, whose absent case must not pass ────────────────────────

@pytest.mark.parametrize("spread,light,collapse", [
    (0.0, "green", False), (5.0, "green", False),
    (5.01, "amber", False), (10.0, "amber", False),
    (10.01, "red", True), (14.0, "red", True),
])
def test_the_spread_light_and_its_collapse_threshold(spread, light, collapse):
    assert ns.spread_light(spread) == (light, collapse)


@pytest.mark.parametrize("bad", [None, float("nan"), "wide"])
def test_an_unmeasurable_spread_collapses_the_strip(bad):
    """"Could not measure the spread" and "the spread is fine" must not render alike. Failing
    open on "could not tell" would put a quote on a card whose tradeability is unknown."""
    light, collapse = ns.spread_light(bad)
    assert collapse is True and light is None
