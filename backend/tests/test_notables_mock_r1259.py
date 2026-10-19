"""NOTABLES v2, the MOCK step. R-IV.1259(b)(c)(d)(e)(g)(i).

WHAT THESE ASSERT, and why each one is here rather than being taken on trust:

1. THE APPROVED MOCKS, by hash. (b) names two files and says verify both. The hashes are
   recorded in `services.notables.APPROVED_MOCKS` and checked against the files when they are
   present; when they are not (a fresh clone, CI), the test SKIPS with the reason rather than
   passing, because "the file is missing" and "the file matches" must not read alike.

2. THE WORDING. (g) holds every card to the no-orders lint and adds six sales words. Both run
   over every string in the fixture, through the same walker the playbooks use.

3. THE UNIVERSE. (b) says AMZN is illustration only and not in the v1 universe, and (e) keeps
   QQQ off cards 2 and 3. A fixture is the one place a reader could learn the wrong universe
   from, so it is checked against the roster rather than against the mock's screenshot.

4. COVERAGE. (c) names five cards and (d) six states. A fixture missing one renders a surface
   that looks complete, so each kind is asserted present by name.

5. THE TYPOGRAPHY (b): "Every ticker symbol renders at 26px mono bold on every card type and
   state." That is a RENDERER fact, so it is checked in the renderer's source, per card type.

6. NOTHING IS SENT AND NOTHING IS WRITTEN (i). The mock step has no table and no POST, so the
   renderer must contain no fetch and no write path, and `notables_log` must NOT exist yet --
   (h) puts both tables in the deploy that writes to them.
"""
from __future__ import annotations

import hashlib
import io
import os
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))

from services import notables as N                                  # noqa: E402

from ._srcscan import read_source                                   # noqa: E402

V2JS = _REPO / "frontend" / "v2.js"
MOCK_DIR = pathlib.Path(r"C:\temp\cc-query-handoff")


def _mock():
    return N.load_mock()


# ── 1 · the approved mocks ────────────────────────────────────────────────────

@pytest.mark.parametrize("which,fname", [
    ("main", "NOTABLES-MOCK-Main.dc.html"),
    ("states", "NOTABLES-MOCK-States.dc.html"),
])
def test_the_approved_mock_still_hashes_to_what_the_ruling_named(which, fname):
    path = MOCK_DIR / fname
    if not path.exists():
        pytest.skip("%s is not on this machine; the hash cannot be checked here" % path)
    got = hashlib.sha256(path.read_bytes()).hexdigest()
    assert got == N.APPROVED_MOCKS[which], (which, got, N.APPROVED_MOCKS[which])


def test_the_fixture_records_the_same_two_hashes():
    """The fixture carries them too, so a card set can be traced to the mock it came from
    without the ruling in hand."""
    assert _mock()["approved_mocks"] == N.APPROVED_MOCKS


# ── 2 · the wording ──────────────────────────────────────────────────────────

def test_no_string_in_the_fixture_reads_as_an_instruction_or_a_sales_pitch():
    findings = N.lint_findings(_mock())
    assert not findings, "R-IV.1259(g) wording findings:\n  " + "\n  ".join(findings)


def test_the_sales_lint_can_actually_fail():
    """Positive control (#30). Each of (g)'s six must be caught, or the list is decoration."""
    for word in N.SALES_WORDS:
        assert N.sales_findings("This is a %s here" % word), word
    for phrase in N.SALES_PHRASES:
        assert N.sales_findings("A %s next week" % phrase), phrase


def test_the_sales_lint_does_not_fire_on_the_descriptions_it_must_allow():
    """The other half: a word INSIDE another word, and the past-tense description of a break
    that already happened, are not pitches. A lint that fails those would force the cards to
    stop describing the tape."""
    for ok in ("The breakout failed and price closed back inside",
               "Entries in the day's record stay listed",
               "Targeting is not something this card does",
               "value area edge"):
        assert not N.sales_findings(ok), ok


def test_the_order_lint_is_the_playbook_one_and_not_a_second_copy():
    src = read_source(str(_BACKEND / "services" / "notables.py"))
    assert "from services.regime_playbook import order_findings" in src
    assert "def order_findings" not in src, "notables.py must not define its own order lint"


def test_the_iv_rank_conflict_is_recorded_in_code():
    """(f) mandates the word (g) bans. The conflict is a fact about the ruling, so it is
    written where the next reader of this module will find it, not only in a report."""
    assert "cheap" in N.IV_RANK_CONFLICT and "(f)" in N.IV_RANK_CONFLICT
    assert "cheap" in N.SALES_WORDS


def test_no_fixture_string_says_cheap_so_the_mock_does_not_have_to_choose():
    lowered = [t.lower() for _, t in __import__(
        "services.regime_playbook", fromlist=["walk_texts"]).walk_texts(_mock())]
    assert not [t for t in lowered if "cheap" in t]


# ── 3 · the universe ─────────────────────────────────────────────────────────

#: The fixture's own provenance fields, which are never rendered. `note` RECORDS WHY AMZN IS
#: ABSENT, and naming it there is the only way the next reader learns it -- so a scan for the
#: symbol over every string fails on the sentence explaining the rule it is enforcing. That
#: trap has now been hit seventeen times in this repo, usually in a code comment; this is the
#: first time in a JSON string. The exclusion is by KEY and written down, not a silent skip.
_PROVENANCE_KEYS = ("note",)


def test_amzn_is_nowhere_in_the_fixture():
    """(b): illustration only, not in the v1 universe."""
    for path, text in __import__("services.regime_playbook",
                                 fromlist=["walk_texts"]).walk_texts(_mock()):
        if path in _PROVENANCE_KEYS:
            continue
        assert "AMZN" not in text.upper(), (path, text)


def test_the_amzn_scan_is_reading_the_cards_and_not_only_the_provenance():
    """The positive control for the exclusion above: skipping `note` must not be skipping
    everything. A card string carrying the symbol has to still fail."""
    walk = __import__("services.regime_playbook", fromlist=["walk_texts"]).walk_texts
    seen = [p for p, _ in walk(_mock()) if p not in _PROVENANCE_KEYS]
    assert len(seen) > 100, len(seen)
    planted = dict(_mock())
    planted["watch"] = [dict(planted["watch"][0], ticker="AMZN")]
    bad = [p for p, t in walk(planted)
           if p not in _PROVENANCE_KEYS and "AMZN" in t.upper()]
    assert bad, "the scan cannot see a ticker on a card"


def test_every_ticker_on_a_card_is_in_the_v1_universe():
    """A bracketed placeholder is allowed -- the States mock uses "[CORE NAME]" rather than
    naming a stock -- because a placeholder teaches nothing about the universe."""
    for t in N.tickers_in(_mock()):
        if t.startswith("["):
            continue
        assert t in N.UNIVERSE, t


def test_qqq_appears_only_on_the_card_that_withholds_it():
    """(e) + R-IV.1258(a)4: QQQ stays off VALUE MOVED and FAILED BREAK. The one place it may
    appear as the card's subject is the "structure unverified" state, whose whole content is
    that the card is WITHHELD."""
    for kind, card in N.cards(_mock()):
        if card.get("ticker") in N.NO_STRUCTURE_CARDS:
            assert kind == "state_unverified", (kind, card.get("ticker"))
            assert "WITHHELD" in card.get("headline", ""), card


# ── 4 · coverage ─────────────────────────────────────────────────────────────

def test_the_fixture_covers_every_card_kind_and_every_state():
    kinds = {k for k, _ in N.cards(_mock())}
    missing = [k for k in (N.CARD_KINDS + N.STATE_KINDS) if k not in kinds]
    assert not missing, missing


def test_the_rotation_shift_is_a_context_line_and_not_a_card():
    """(c)5: rotation is a Context line. A fixture that made it a card would put a market-wide
    item where ticker cards go and the cap would start counting it."""
    labels = [s.get("label") for s in (_mock()["context"]["strips"] or [])]
    assert "ROTATION SHIFT" in labels
    assert "rotation" not in {k for k, _ in N.cards(_mock())}


def test_the_loud_move_is_pinned_and_excluded_from_the_cap():
    loud = _mock()["context"]["loud_move"]
    assert "NOT COUNTED IN CAP" in loud["pinned"].upper()
    cap = _mock()["cap"]
    assert cap["shown"] <= cap["max"] == 5, cap
    assert len(_mock()["watch"]) == cap["shown"], "the tally must match the cards shown"


def test_the_unknown_reason_line_is_the_rulings_words():
    """(c)1 gives the line verbatim. A paraphrase is a different promise about what the hub
    knows."""
    assert (_mock()["context"]["loud_move"]["why"]["text"]
            == "Hub doesn't know why. Probably news. Go look.")


def test_every_ticker_card_prints_counter_evidence_and_a_stale_line():
    """(g): reasons as chips, counter-evidence from the same data, and the stale fact with its
    own disclaimer. Asserted on the fixture so a card cannot ship without the half that argues
    against it."""
    for card in _mock()["watch"]:
        assert card.get("chips"), card["ticker"]
        assert card.get("against"), card["ticker"]
        assert card.get("stale", "").startswith("Stale if"), card["ticker"]


def test_the_three_buttons_are_the_three_the_ruling_names():
    assert _mock()["watch"][0]["buttons"] == ["Dismiss", "Pin", "Send to journal"]


# ── 5 · the typography, in the renderer ──────────────────────────────────────

def test_the_renderer_prints_every_ticker_at_26px_mono_bold():
    """(b), and it is a renderer fact so it is checked there. ONE helper emits the symbol, so
    the claim "on every card type and state" is structural rather than six separate strings
    that have to agree."""
    src = read_source(str(V2JS))
    assert "function nbSym" in src, "one helper must emit every ticker symbol"
    assert "nb-sym" in src
    css = _notables_css(src)
    assert "font-size:26px" in css.replace(" ", "")
    assert "font-weight:700" in css.replace(" ", "")


def _notables_css(src: str) -> str:
    """The injected stylesheet, read out of the renderer's source."""
    start = src.index("NB_CSS")
    end = src.index("`;", start)
    return src[start:end]


def test_the_notables_styles_are_injected_and_not_added_to_the_shared_stylesheet():
    """v2.css is pinned INDEPENDENTLY by v2.html, stater.html and abacus.html, and those three
    values have already diverged. A rule added there means bumping all three; a rule the
    renderer injects means bumping only the page that loads the renderer."""
    assert "NB_CSS" in read_source(str(V2JS))
    css = (_REPO / "frontend" / "v2.css").read_text(encoding="utf-8", errors="replace")
    assert ".nb-card" not in css, "the NOTABLES styles belong in the injected block"


# ── 6 · nothing is sent, nothing is written ──────────────────────────────────

def test_the_renderer_has_no_write_path():
    """(i): the mock step writes nothing. Read from the PARSED source, so the comment that
    explains why there is no POST cannot satisfy the check (#30's companion trap, 16 instances)."""
    code = read_source(str(V2JS))
    nb = code[code.index("NOTABLES_MOCK"):]
    nb = nb[:nb.index("// ── end notables")] if "// ── end notables" in nb else nb
    for forbidden in ("method: 'POST'", 'method: "POST"', "notables_log", "notables_outcomes"):
        assert forbidden not in nb, forbidden


def test_neither_notables_table_is_created_yet():
    """(h): both tables are created in the deploy that writes to them. The mock writes nothing,
    so a CREATE TABLE here would be a table nothing fills -- and the next reader would take its
    emptiness for a quiet day."""
    hits = []
    for base in (_BACKEND,):
        for path in base.rglob("*.py"):
            if "__pycache__" in str(path) or path.name == "test_notables_mock_r1259.py":
                continue
            try:
                txt = io.open(path, encoding="utf-8-sig").read()
            except Exception:                                       # noqa: BLE001
                continue
            if "CREATE TABLE" in txt.upper() and "notables_log" in txt:
                hits.append(str(path.relative_to(_REPO)))
    assert not hits, hits


def test_the_fixture_is_labelled_a_mock_in_its_own_text():
    """A realistic card is exactly the thing a reader could mistake for the live feature
    working, so the badge is part of the fixture rather than a renderer flourish."""
    m = _mock()
    assert "MOCK" in m["badge"].upper()
    assert "SAMPLE" in m["stamp"].upper() or "NOT A LIVE READ" in m["stamp"].upper()
