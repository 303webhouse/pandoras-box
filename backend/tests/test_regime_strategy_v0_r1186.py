"""R-IV.1186 v0 — the Regime Strategy card: mock only, no orders, UNREGISTERED.

THE CONSTRAINT THIS FILE ENFORCES is §1 of the double-pass record: the module "is not a signal.
It never says 'buy X' or 'short Y', never ranks tickers, and nothing in the hub uses its label
to change caps, gates, the kill-switch or the journal (Convention #42)."

THE NO-ORDERS LINT IS THE CENTREPIECE, and the hard part is that the source texts contain the
words. "short squeezes", "a before-the-turn short", "sellers' market", "dips bought", "B1/B2
shorts only after a confirmed downtrend" are all descriptive, and a lint on the bare word
`short` would reject the very text it exists to protect. Meanwhile "Don't buy new premium in the
spike" and "re-arm tails only once..." ARE directives and must be caught.

So the rule is about GRAMMAR, not vocabulary, and both halves are tested below: fifteen
instruction forms that must fail, and fourteen descriptive forms that must pass. A lint that
only proved one half would be either decoration or a blanket ban.

WRITTEN BEFORE THE TEXTS WERE TRANSCRIBED. A lint shaped to pass a particular transcription
tests the transcription, not the rule.

THREE SENTENCES ARE HELD, not reworded. §4 line 3 asks the premium line to be "a pricing fact,
never an order", and three source sentences are orders — so the source disagrees with its own
specification there. BUILD does not paraphrase a committee's ruled text, so those sentences are
withheld, counted on the card, and reported for SPINE's rewording.
"""
from __future__ import annotations

import io
import json
import os
import re

import pytest

from services import regime_playbook as rp

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(os.path.dirname(BACKEND), "frontend")
ASSETS = os.path.join(FRONTEND, "assets", "regime")

SOURCE_SHA = "37dff5af7faa3843f33722d6c2827fee6d9532c79980ff8fd21375217a657d3e"


def _read(path: str) -> str:
    return io.open(path, encoding="utf-8", errors="replace").read()


def _js() -> str:
    return _read(os.path.join(FRONTEND, "v2.js"))


def _code(js: str) -> str:
    out = []
    for line in js.split("\n"):
        i = line.find("//")
        if i > 0:
            before = line[:i]
            if before.count("'") % 2 or before.count('"') % 2 or before.count("`") % 2:
                i = -1
        out.append(line if i < 0 else line[:i])
    return "\n".join(out)


# ── THE NO-ORDERS LINT: the build gate ──────────────────────────────────────

def test_THE_BUILD_GATE_no_playbook_text_reads_as_an_instruction():
    """R-IV.1186(b). This is the test that fails the build."""
    rp.assert_no_orders()


@pytest.mark.parametrize("text", [
    "Buy the dip.",
    "Short the rally.",
    "Take 60-70% under 21 DTE.",
    "Don't buy new premium in the spike.",
    "Re-arm tails only once VIX is back in the low band.",
    "Enter on a reclaim of the 50dma.",
    "So buy spreads here.",
    "Sell SPY into the bounce.",
    "Trim the position by half.",
    "Harvest tails now.",
    "Take profits into strength.",
    "Cut risk here.",
    "Short SPY.",
    "Short puts here.",
    "Long calls into the close.",
])
def test_an_instruction_is_caught(text):
    """Fifteen forms of order. A lint that caught none of these would be decoration."""
    assert rp.order_findings(text), text


@pytest.mark.parametrize("text", [
    "short squeezes, with the most-beaten-down names ripping hardest",
    "a before-the-turn short is still capped at B3/TAIL",
    "sellers' market",
    "dips bought",
    "puts lose twice, on direction and on falling vol",
    "The C5/Z2 gates allow B1/B2 shorts only after a confirmed downtrend.",
    "QQQ and IWM back above their 50dma",
    "SPY 50dma: confirmed break = BREAKDOWN",
    "Tails are cheapest here",
    "credit spreads and the funding/carry crosses",
    "Long premium bleeds fastest as vol deflates",
    "short interest is elevated",
    "Defined-risk structures.",
    "Short dated puts cost the most.",
])
def test_a_description_is_spared(text):
    """Fourteen forms of description, every one of them from or modelled on the record. A lint
    that rejected these would be a blanket ban on the vocabulary the record needs."""
    assert rp.order_findings(text) == [], (text, rp.order_findings(text))


def test_the_rule_is_grammar_not_vocabulary():
    """The same word, twice, with opposite verdicts. This is the whole design in one test: a
    word list cannot separate these and the grammar can."""
    assert rp.order_findings("Short the rally.")          # command
    assert not rp.order_findings("short squeezes are violent")  # compound noun


def test_a_ticker_as_a_measurement_is_fine_but_as_an_object_is_not():
    """§1 forbids ranking tickers and saying "buy X". It does not forbid naming a ticker: §2 is
    nothing but tickers and levels."""
    assert not rp.order_findings("QQQ back above its 50dma on 2 closes")
    assert rp.order_findings("Sell QQQ on the reclaim.")


def test_an_exempted_noun_phrase_is_ENUMERATED_not_inferred():
    """An exception that is not written down is a hole. The allowlist is a module constant and
    `describes()` exposes it, so a test can assert what is exempt rather than discover it."""
    assert rp.describes("long premium")
    assert rp.describes("short squeezes")
    assert not rp.describes("short puts"), (
        "`short puts` reads as a command and must NEVER be exempted")
    assert not rp.describes("long calls")
    assert "short puts" not in rp.DESCRIPTIVE_PHRASES
    assert "long calls" not in rp.DESCRIPTIVE_PHRASES


def test_the_exemption_is_per_occurrence_and_does_not_mask_a_later_command():
    """A noun-slot exemption clears ONE occurrence. A real command later in the same sentence
    must still be caught, or the allowlist becomes a way to smuggle one in."""
    assert rp.order_findings("A capex-guidance cut; then buy spreads.")


def test_the_lint_walks_EVERY_string_in_the_file():
    """A text is not made safe by living under a key nobody expects to render. The walker is
    recursive and the test proves it reaches a nested list element."""
    found = dict(rp.walk_texts({"a": {"b": ["x", {"c": "y"}]}}))
    assert found["a.b[0]"] == "x"
    assert found["a.b[1].c"] == "y"


def test_a_failure_names_the_field_it_came_from():
    """"The playbook contains an order" is not actionable. "regimes.crash.premium contains one"
    is."""
    out = rp.lint_text("Buy the dip.", "regimes.x.premium")
    assert out and out[0].startswith("regimes.x.premium:")


def test_the_lint_raises_rather_than_returning_False():
    """It has to stop a build, so it raises — a boolean would need every caller to remember to
    check it."""
    with pytest.raises(rp.PlaybookLintError):
        rp.assert_no_orders.__wrapped__() if hasattr(rp.assert_no_orders, "__wrapped__") \
            else _raise_on_dirty()


def _raise_on_dirty():
    import unittest.mock as mock
    with mock.patch.object(rp, "lint_playbooks", lambda version=rp.PLAYBOOK_VERSION:
                           ["regimes.x.premium: imperative 'buy' opens: 'Buy the dip.'"]):
        rp.assert_no_orders()


# ── the versioned files ─────────────────────────────────────────────────────

def test_the_playbook_is_a_versioned_file():
    """R-IV.1186(b): "stored as versioned files, not editable from the UI". The version is in
    the FILENAME, so two versions can exist side by side and a card names which it read."""
    assert os.path.exists(os.path.join(ASSETS, "playbooks.v1.json"))
    assert rp.load_playbooks()["version"] == "v1"


def test_nothing_in_the_hub_writes_the_playbook_or_the_fixture():
    """"Not editable from the UI" has to be true by construction, not by the absence of a
    button. No route, job or service opens either file for writing."""
    hits = []
    for root, _dirs, files in os.walk(BACKEND):
        if "test" in root or "__pycache__" in root:
            continue
        for fn in files:
            if not fn.endswith(".py"):
                continue
            src = _read(os.path.join(root, fn))
            for name in ("playbooks.v1.json", "regime_mock.json", "playbooks.%s.json"):
                if name in src and re.search(r'open\([^)]*%s[^)]*["\']w' % re.escape(name), src):
                    hits.append(os.path.join(root, fn))
    assert not hits, "something writes a playbook/fixture file: %s" % hits


def test_all_ten_regimes_and_all_seven_overlays_are_present():
    pb = rp.load_playbooks()
    assert len(pb["regimes"]) == 10
    assert len(pb["overlays"]) == 7
    assert sorted(r["n"] for r in pb["regimes"].values()) == list(range(1, 11))


def test_every_regime_carries_the_five_lines_of_section_4():
    """§4: "Each regime card shows the same five lines." A regime missing one would render a
    gap that reads as "nothing to say here"."""
    for key, r in rp.load_playbooks()["regimes"].items():
        for field in ("matters_now", "tape", "premium", "ending_signs", "proves_wrong"):
            assert r.get(field), "%s is missing %s" % (key, field)
        assert isinstance(r["matters_now"], list) and r["matters_now"]


def test_every_overlay_carries_its_three_state_columns():
    for key, o in rp.load_playbooks()["overlays"].items():
        for field in ("label", "type", "watch_when", "active_needs", "clears_when"):
            assert o.get(field), "%s is missing %s" % (key, field)


def test_a_held_line_is_COUNTED_AND_EXPLAINED_never_silently_dropped():
    """THREE SENTENCES ARE WITHHELD. A playbook that silently drops one reads as complete,
    which is the one thing a held text must not do — so the count and the reason are on the
    row, and the card renders them."""
    pb = rp.load_playbooks()
    held = {k: v["held_sentences"] for k, v in pb["regimes"].items()
            if v.get("held_sentences")}
    assert held == {"crash_liquidation": 2, "recovery": 1}
    for key in held:
        assert pb["regimes"][key].get("held_reason"), "%s holds a line with no reason" % key
    assert pb["held_policy"]


def test_the_playbook_names_its_source_and_that_source_s_hash():
    """Convention #44's spirit: a text transcribed from a document cites the document by hash,
    so a reader can tell which version it came from."""
    pb = rp.load_playbooks()
    assert SOURCE_SHA in pb["source"]


# ── the fixture: mock, and saying so ────────────────────────────────────────

def test_the_fixture_declares_itself_a_fixture():
    """A mock that does not say it is a mock is indistinguishable from a reading."""
    m = rp.load_mock()
    assert m["fixture"] is True
    assert "MOCK" in m["fixture_note"]
    assert SOURCE_SHA in m["source"]


def test_the_fixture_is_the_10_16_state_from_section_9():
    m = rp.load_mock()
    assert m["regime_label"] == "CORRECTION"
    assert m["tags"] == ["narrow", "credit-stress"]
    assert m["settled_close"] == "2026-10-16"
    assert m["health"] == "PARTIAL"
    assert m["evidence"]["crash_check"] == "NOT EVALUABLE"
    assert m["evidence"]["families_risk_off"] == 3
    assert m["evidence"]["families_total"] == 5
    per = {x["ticker"]: x["state"] for x in m["per_index"]}
    assert per == {"SPY": "RANGE", "QQQ": "CORRECTION", "IWM": "DOWNTREND"}


def test_the_fixture_marks_IWM_uncertain_because_its_RVOL_leg_is_unverified():
    """§5 says so, and dropping the qualifier would publish a confirmed break that was never
    confirmed."""
    iwm = next(x for x in rp.load_mock()["per_index"] if x["ticker"] == "IWM")
    assert iwm["uncertain"] is True
    assert "RVOL" in iwm["uncertain_why"]


def test_an_uncomputed_figure_is_null_with_a_reason_never_a_zero():
    """`bull_intact` is not computed in v0. A 0 there would say "none of the seven hold", which
    is a measurement of a bull case nobody measured."""
    ev = rp.load_mock()["evidence"]
    assert ev["bull_intact"] is None
    assert ev["bull_intact_reason"]


def test_the_fixture_regime_key_resolves_to_a_real_playbook():
    """The Open button expands THE CURRENT regime's playbook, so the key has to match one."""
    m, pb = rp.load_mock(), rp.load_playbooks()
    assert m["regime_key"] in pb["regimes"]


def test_every_fixture_overlay_key_resolves_too():
    m, pb = rp.load_mock(), rp.load_playbooks()
    for o in m["overlays"]:
        assert o["key"] in pb["overlays"], o["key"]


def test_the_fixture_is_also_lint_clean():
    """The fixture is rendered text too. A WATCH-NOW bullet is as capable of carrying an order
    as a playbook line is."""
    findings = []
    for path, text in rp.walk_texts(rp.load_mock()):
        findings.extend(rp.lint_text(text, path))
    assert findings == [], findings


# ── the badge, the lens rule, and v0's "no wiring" ──────────────────────────

def test_the_UNREGISTERED_badge_is_in_the_markup_beside_the_title():
    """R-IV.1186(b) asks for it VISIBLE. At the foot of a scrolling card it is not."""
    html = _read(os.path.join(FRONTEND, "v2.html"))
    i = html.index('id="rsBadge"')
    assert "UNREGISTERED" in html[i:i + 220]
    assert "display only" in html[i:i + 220]
    # The TITLE ELEMENT, not the first occurrence of the words -- which is the HTML comment
    # above the tile, 456 characters earlier. Measuring from there made this test fail on a
    # badge that is correctly placed: the same "anchor matched the wrong occurrence" fault
    # Convention #43 exists for, in a test rather than an edit.
    title = html.index('<span class="tile-title">Regime Strategy</span>')
    assert title < i < title + 400, "the badge must sit beside the title"


def test_the_fixture_is_not_registered():
    assert rp.load_mock()["registered"] is False
    assert rp.load_playbooks()["registered"] is False


def test_LENS_2_IS_LABELLED_AN_ALARM_AND_IS_NOT_THE_HEADLINE():
    """R-IV.1186(b), §1 and §5. The headline is the base regime; the watchlist reading is the
    high-beta alarm. In the renderer the label block comes BEFORE the lens block, and the lens
    block carries the words."""
    js = _code(_js())
    i = js.index("function renderRegimeStrategy")
    body = js[i:js.index("\n  // \"Open\" expands", i)] if '\n  // "Open" expands' in js[i:] \
        else js[i:i + 6000]
    assert "Watchlist \\u2014" not in body
    assert "(high-beta) alarm" in body
    assert body.index("rs-label") < body.index("rs-lens"), (
        "the base regime must render before the watchlist lens")
    m = rp.load_mock()
    assert "NEVER the headline" in m["lens_split"]["headline_rule"]


def test_v0_READS_NO_HUB_ROUTE_AT_ALL():
    """R-IV.1186(c): nothing reads or writes a regime table yet. The card's only inputs are the
    two static asset files."""
    js = _code(_js())
    i = js.index("async function loadRegimeStrategy")
    body = js[i:js.index("function rsChip", i)]
    assert body.count("fetch(") == 2
    assert "/assets/regime/regime_mock.json" in body
    assert "/assets/regime/playbooks.v1.json" in body
    assert "apiFetch" not in body, "v0 must not call a hub route"
    assert "/api/" not in body


def test_v0_TOUCHES_NO_KILL_SWITCH_NO_CAPS_NO_JOURNAL():
    """R-IV.1186(c). The kill-switch line is a DISPLAY of a value the fixture carries, so the
    module must contain no write and no kill-switch call."""
    js = _code(_js())
    i = js.index("let _rsMock = null")
    j = js.index("function initGrid()", i)
    module = js[i:j]
    for banned in ("method: 'POST'", 'method: "POST"', "XMLHttpRequest", "apiFetch",
                   "kill_switch =", "killSwitch(", "/api/"):
        assert banned not in module, banned


def test_the_card_is_loaded_ONCE_and_never_polled():
    """A refresh interval on a static fixture would imply the card is tracking something. v0
    tracks nothing."""
    js = _code(_js())
    i = js.index("loadRegimeStrategy();")
    window = js[i:i + 260]
    assert "managedInterval(loadRegimeStrategy" not in js
    assert "rsOpen" in window, "the Open button is bound at boot, not inline in the markup"


def test_the_markup_carries_no_inline_behaviour():
    html = _read(os.path.join(FRONTEND, "v2.html"))
    i = html.index('gs-id="regime-strategy"')
    block = html[i:html.index("<!-- Movers tape", i)]
    assert "onclick" not in block
    assert "javascript:" not in block


# ── phone-first ─────────────────────────────────────────────────────────────

def test_the_card_is_SECOND_in_the_mobile_order_not_last():
    """`applyMobileOrder` sorts an UNLISTED tile AFTER the known set, so markup alone would
    bury the one card Nick is being asked to look at."""
    js = _code(_js())
    i = js.index("const MOBILE_ORDER = [")
    block = js[i:js.index("]", i)]
    order = re.findall(r"'([a-z-]+)'", block)
    assert "regime-strategy" in order, "the card is not in MOBILE_ORDER"
    assert order.index("regime-strategy") == 1, order


def test_the_styles_are_phone_first():
    """The base rules are the phone's, and the one media query WIDENS from 760px up. Written
    the other way round — desktop base plus a phone override — a card reads only on the machine
    it was built on."""
    css = _read(os.path.join(FRONTEND, "v2.css"))
    i = css.index("Regime Strategy card (R-IV.1186 v0)")
    block = css[i:]
    assert "min-width: 760px" in block
    assert "max-width:" not in block, (
        "a max-width query would make the desktop rules the base")


def test_every_class_the_renderer_uses_has_a_style():
    js, css = _code(_js()), _read(os.path.join(FRONTEND, "v2.css"))
    i = js.index("function renderRegimeStrategy")
    used = set(re.findall(r'class="(rs-[a-z0-9-]+)"', js[i:i + 9000]))
    used |= {"rs-badge", "rs-open", "rs-playbook", "rs-held", "rs-pb-title"}
    missing = sorted(c for c in used if "." + c not in css)
    assert not missing, missing


def test_the_pins_moved_for_both_changed_assets():
    html = _read(os.path.join(FRONTEND, "v2.html"))
    for asset, floor in (("v2.js", 62), ("v2.css", 49)):
        m = re.search(re.escape(asset) + r"\?v=(\d+)", html)
        assert m and int(m.group(1)) >= floor, (asset, m and m.group(1))


def test_the_other_pages_pinning_v2_css_moved_too():
    """v2.css is pinned by three pages at independent values; the page missed keeps serving
    whatever was cached under its unchanged pin."""
    for page, floor in (("stater.html", 45), ("abacus.html", 44)):
        m = re.search(r"v2\.css\?v=(\d+)", _read(os.path.join(FRONTEND, page)))
        assert m and int(m.group(1)) >= floor, (page, m and m.group(1))


def test_the_assets_live_where_the_server_serves_them_wholesale():
    """CLAUDE.md: new static files must live under `frontend/assets/`, because only that folder
    is served wholesale — `main.py` routes every other file by name, so a file outside it would
    404 and the card would render its "did not load" message in production."""
    assert os.path.isdir(ASSETS)
    assert ASSETS.replace("\\", "/").endswith("frontend/assets/regime")
    for fn in ("playbooks.v1.json", "regime_mock.json"):
        assert os.path.exists(os.path.join(ASSETS, fn))
        json.loads(_read(os.path.join(ASSETS, fn)))
