"""B9's vocabulary and lint. R-IV.1265(e), amended by R-IV.1364(c).

THE MOCK IS GONE. B9 went live under R-IV.1431 (/api/b9/world, services/b9_live.py), so the no-mock
sweep removed the fixture (world_mock.v1.json), its `?b9=1` review flag and the mock renderer in
v2.js, and the tests that read them. What stays here is what b9_live still computes and lints with:
the race universe (equity only, SPY and QQQ in it), the commodity refusal, one China proxy, the
UNUSUAL/EXTREME labels with their measured fires per year, the keep-out and no-orders lints, the
governing document's hash and the footnote's convention. The tests at the end pin the removal.
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


# ── 2 · the return basis ─────────────────────────────────────────────────────


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


# ── 4 · one China proxy ──────────────────────────────────────────────────────

def test_fxi_stands_and_mchi_is_refused():
    assert "FXI" in b9.RACE_UNIVERSE and "MCHI" not in b9.RACE_UNIVERSE
    with pytest.raises(ValueError) as e:
        b9.race_rows([{"ticker": "MCHI"}])
    assert "superseded by FXI" in str(e.value)


# ── 5 and 6 · the columns and the footnote ───────────────────────────────────


def test_the_race_footnote_has_ONE_source():
    """R-IV.1441(b)2: SPEC-B9.md's sentence, held once in b9_live; amendment 7's older wording is
    gone, so no second footnote can drift from it."""
    from services import b9_live
    assert not hasattr(b9, "RACE_FOOTNOTE")
    f = b9_live.RACE_FOOTNOTE_SPEC
    assert "8/9, 6/9, 4/8 and 2/9" in f and "(QUERY R-IV.1221)" in f


# ── 7 · the reframe, and the keep-out list ───────────────────────────────────


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


# ── the rest of the synthesis's own numbers ──────────────────────────────────


# ── the renderer ─────────────────────────────────────────────────────────────


# ── R-IV.1364(c): THE MOCK IS GONE ───────────────────────────────────────────
#
# B9 went live under R-IV.1431 (/api/b9/world, services/b9_live.py), so the no-mock sweep removed
# the fixture, its `?b9=1` review flag and the mock renderer. The tests that read the fixture or
# the old renderer went with them; the vocabulary and lint tests above stay, because b9_live
# computes and lints with them. These pin the removal so it cannot quietly come back.

def _v2_code():
    """v2.js with comment lines dropped: the slot's own comment SAYS `?b9=1` was removed, and a
    scan that reads prose fails on the explanation instead of the code (memory: source-scan
    tests must strip prose)."""
    src = (_REPO / "frontend" / "v2.js").read_text(encoding="utf-8")
    return "\n".join(l for l in src.splitlines() if not l.strip().startswith(("//", "*", "/*")))


def test_the_mock_fixture_and_its_loader_are_gone():
    assert not (_REPO / "frontend" / "assets" / "b9" / "world_mock.v1.json").exists()
    for name in ("load_mock", "mock_path", "MOCK_FILE", "MOCK_VERSION"):
        assert not hasattr(b9, name), name


def test_no_b9_mock_code_is_left_in_v2js():
    code = _v2_code()
    for gone in ("pvWorld(", "_b9Mock", "b9Load", "B9_MOCK_SHOWN", "world_mock", "get('b9')",
                 "PW_CSS", "pwStyle"):
        assert gone not in code, gone


def test_the_rollback_drawers_slot_carries_the_LIVE_mount():
    """`?clean=off` still renders the old drawer; its B9 slot is the same #b9-mount the cleaned
    pop-out has (R-IV.1432(d)), so assets/b9/b9_live.js fills it with live data there too."""
    code = _v2_code()
    fn = code[code.index("function pvWorldSlot()"):]
    fn = fn[:fn.index("\n  }") + 4]
    assert 'id="b9-mount"' in fn and "pvWorld(" not in fn


def test_the_popout_gate_checks_the_live_mount_not_the_mock():
    gate = (_REPO / "scripts" / "check_pop_v2.js").read_text(encoding="utf-8")
    assert "'b9-mount'" in gate and "'pv-world'" not in gate
