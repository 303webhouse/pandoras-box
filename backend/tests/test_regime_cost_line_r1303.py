"""The card's cost line comes from a display config, not the stamped rules file. R-IV.1303(b).

THE COLLISION THIS RESOLVES. R-IV.1297(e) asked for v2.1's `stated_cost` to become QUERY's
graded sentence. R-IV.1297(c) required `regime_rules.v2.1.json` to stay byte-identical to LF
sha256 `4bc6d895...`, and R-IV.1043(c) makes a ferried artifact immutable. `cost_statement()`
read the sentence out of that file, so the two instructions had no common satisfaction and the
item was reported blocked rather than guessed at.

R-IV.1303(b) names the real fault, which is placement rather than wording:

    the rules file   a CLASSIFICATION artifact -- stamped, hashed, must not change
    the cost line    a DISPLAY fact -- it changes whenever someone GRADES the classifier

So the sentence moves out. The rules file KEEPS its own `stated_cost` -- it is part of the
stamped bytes and removing it would break the hash -- and that copy is simply never displayed.

WHY THE CONFIG IS EMPTY, which is a state and not an omission. QUERY supplies v2.1's line under
R-IV.1301(c). v2's previous wording was found misleading by R-IV.1280: it called QUERY's own
graded figures "ungraded" and dropped the censoring, because the ~80-session median ranks 11 of
24 never-called recoveries as worst -- for nearly half the events the honest answer is "never",
which a reader cannot recover from the sentence. A cost line is a claim about measured
behaviour, so BUILD does not author one (R-IV.925(b)). Empty is correct today.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from models.regime_card_display import (cost_lines,                # noqa: E402
                                        has_cost_line, load_display_config)
from models.regime_classifier import load_rules                    # noqa: E402
from models.regime_hysteresis import cost_statement                # noqa: E402

from ._srcscan import read_source                                  # noqa: E402

DISPLAY = _BACKEND / "config" / "regime_card_display.v1.json"
RULES_V21 = _BACKEND / "config" / "regime_rules.v2.1.json"
HYST = str(_BACKEND / "models" / "regime_hysteresis.py")
SERVICE = str(_BACKEND / "services" / "read_only" / "regime_strategy.py")
STAMPED_SHA256 = "4bc6d895484a2f581efa3b4356591209b966351183d693cd158eedb240974e9a"


# ── the split ───────────────────────────────────────────────────────────────

def test_the_display_config_exists_and_is_its_own_file():
    cfg = load_display_config()
    assert cfg["version"] == "v1"
    assert "cost_lines" in cfg
    assert DISPLAY.exists() and DISPLAY.name != RULES_V21.name


def test_the_stamped_rules_file_is_STILL_byte_identical():
    """The whole reason the line moved. If this ever goes red, the move failed at its purpose."""
    lf = RULES_V21.read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(lf).hexdigest() == STAMPED_SHA256


def test_the_rules_file_KEEPS_its_stated_cost_because_the_bytes_are_pinned():
    """Deleting the key would be the obvious tidy-up and it would break the hash. The copy
    stays and is not read for display -- those are different things and both are required."""
    assert "stated_cost" in load_rules("v2.1")["hysteresis"]
    assert "stated_cost" in load_rules("v2")["hysteresis"]


def test_nothing_in_the_DISPLAY_path_reads_the_rules_file_for_a_COST():
    """The property that makes the split real. Read from the source of both the reader and the
    payload, because a value test would pass while the old read sat one branch away."""
    hyst = read_source(HYST)
    i = hyst.index("def cost_statement")
    block = hyst[i:hyst.index(chr(10) * 3, i) if chr(10) * 3 in hyst[i:] else len(hyst)]
    assert "load_rules" not in block, "cost_statement must not reach for the rules file"
    assert "regime_card_display" in block
    svc = read_source(SERVICE)
    j = svc.index("def _cost_lines")
    assert "load_rules" not in svc[j:j + 700]


# ── absent means absent ─────────────────────────────────────────────────────

@pytest.mark.parametrize("version", ["v2", "v1", "v3", "", None])
def test_only_v21_HAS_a_cost_line(version):
    """R-IV.1307(b) supplied v2.1's and only v2.1's. Every other version shows none -- which
    is the property, not a gap: attributing a measurement to a version that did not produce it
    is the fault R-IV.1280 found in the wording this replaces."""
    assert cost_lines(version) == []
    assert has_cost_line(version) is False


def test_v21s_line_is_served():
    assert has_cost_line("v2.1") is True
    assert cost_lines("v2.1") == ['SPY 1999-2026, 24 declines: all-clear a median 81.5 sessions after the low, never on 11; 200d line 38. (R-IV.1301)']


def test_cost_statement_returns_a_LIST_so_a_caller_cannot_iterate_a_SENTENCE():
    """The type change is a safety property, not tidiness. The old return was a `str`, and the
    card's block is a list -- `[c for c in some_string]` renders one bullet PER CHARACTER. A
    list return makes that shape impossible to reach by accident."""
    got = cost_statement("v2.1")
    assert isinstance(got, list)
    assert cost_statement() == []


def test_a_single_string_in_the_config_is_WRAPPED_not_exploded():
    """The same hazard from the config side: whoever supplies QUERY's line will write one
    sentence, and a string is iterable."""
    cfg = {"cost_lines": {"v2.1": "one sentence, not thirty characters"}}
    assert cost_lines("v2.1", cfg) == ["one sentence, not thirty characters"]


def test_a_list_in_the_config_is_served_in_order():
    cfg = {"cost_lines": {"v2.1": ["first", "second"]}}
    assert cost_lines("v2.1", cfg) == ["first", "second"]


def test_blank_and_whitespace_entries_are_DROPPED_not_rendered():
    """An empty bullet is a visible artifact of a config mistake, on the card, in front of Nick."""
    assert cost_lines("v2.1", {"cost_lines": {"v2.1": ""}}) == []
    assert cost_lines("v2.1", {"cost_lines": {"v2.1": ["  ", "kept"]}}) == ["kept"]


def test_it_NEVER_borrows_another_versions_line():
    """Showing v2's sentence under a v2.1 label attributes a measurement to a classifier that
    did not produce it -- the exact fault R-IV.1280 found in the old wording."""
    cfg = {"cost_lines": {"v2": "v2's measured cost"}}
    assert cost_lines("v2.1", cfg) == []
    assert cost_lines("v2", cfg) == ["v2's measured cost"]


# ── it can never break the card ─────────────────────────────────────────────

def test_an_unreadable_config_costs_the_CARD_ITS_LINE_not_its_LABEL():
    """This module's neighbours state the rule outright: "a failure to read it must cost the
    card its grey line, not its label." A display sentence is the least important thing on the
    card and must never be why the label does not render."""
    assert load_display_config("C:/nope/does-not-exist.json") == {"version": None,
                                                                  "cost_lines": {}}
    assert cost_lines("v2.1", load_display_config("C:/nope/does-not-exist.json")) == []


@pytest.mark.parametrize("broken", [
    {"cost_lines": "not a dict"},
    {"cost_lines": None},
    {},
    {"cost_lines": {"v2.1": 17}},
    {"cost_lines": {"v2.1": {"nested": "object"}}},
])
def test_a_MALFORMED_config_yields_no_line_rather_than_raising(broken):
    assert cost_lines("v2.1", broken) == []


def test_the_payload_reader_is_GUARDED_like_the_modules_other_leaf_reads():
    src = read_source(SERVICE)
    i = src.index("def _cost_lines")
    block = src[i:i + 800]
    assert "try:" in block and "except Exception" in block
    assert "return []" in block


# ── the payload and the card ────────────────────────────────────────────────

def test_the_payload_serves_costs_from_the_display_config():
    src = read_source(SERVICE)
    assert '"costs": _cost_lines(got.get("rules_version"))' in src


def test_the_card_renders_NO_BLOCK_when_there_is_no_line():
    """The live card has been showing "COSTS, STATED" over an EMPTY list, because the payload
    never carried `costs` at all and the heading was unconditional. An empty heading reads as a
    read that failed; nothing reads as "there is no stated cost yet", which is the truth."""
    js = read_source(str(_BACKEND.parent / "frontend" / "v2.js"))
    i = js.index("COSTS, STATED")
    window = js[max(0, i - 700):i + 400]
    assert "(_rsLive.costs || []).length" in window, "the block must be conditional"
    assert "NO LINE MEANS NO BLOCK" in window


def test_the_cards_pin_moved_with_its_file():
    """CLAUDE.md: "A changed asset behind an unchanged pin is a fix that never reaches the
    browser." v2.js changed here, so v2.html's pin and the manifest must both agree with it."""
    frontend = _BACKEND.parent / "frontend"
    manifest = json.loads(frontend.joinpath("asset-pins.json").read_text(encoding="utf-8"))
    recorded = manifest["v2.html"]["v2.js"]
    digest = hashlib.sha256(frontend.joinpath("v2.js").read_bytes()).hexdigest()
    assert recorded["sha256"] == digest, "the manifest does not match the file on disk"
    html = frontend.joinpath("v2.html").read_text(encoding="utf-8")
    assert '/v2.js?v=%d"' % recorded["pin"] in html
