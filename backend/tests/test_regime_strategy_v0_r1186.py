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

# R-IV.1189(b) supersedes R-IV.1186's hash. BOTH are kept: v2 cites the new document
# and v1 must go on citing the old one, or the audit trail says a superseded file came
# from a document it never saw.
SOURCE_SHA = "61940f0264a91839b8c47353b25a5cd421ee0bdba8f35c99d8cc8670eec0247b"
SOURCE_SHA_V1 = "37dff5af7faa3843f33722d6c2827fee6d9532c79980ff8fd21375217a657d3e"


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

def test_the_playbook_is_a_versioned_file_AND_BOTH_VERSIONS_EXIST():
    """R-IV.1186(b): "stored as versioned files". The version is in the FILENAME, and
    R-IV.1189 is what makes that matter: v1 and v2 now sit side by side, so "playbook v1" on a
    card can never mean two different texts."""
    assert os.path.exists(os.path.join(ASSETS, "playbooks.v1.json"))
    assert os.path.exists(os.path.join(ASSETS, "playbooks.v2.json"))
    assert rp.load_playbooks()["version"] == "v2"
    assert rp.load_playbooks("v1")["version"] == "v1"
    assert rp.playbook_versions() == ["v1", "v2"]


def test_THE_BUILD_GATE_COVERS_EVERY_VERSION_ON_DISK():
    """A superseded file stays in the repository for audit, and "it is not the live one" is not
    a reason for it to hold an order."""
    rp.assert_no_orders_any_version()


def test_v1_names_the_OLD_document_hash_and_v2_the_new():
    """A superseded version that silently claimed the new document would make the audit trail
    useless."""
    assert SOURCE_SHA_V1 in rp.load_playbooks("v1")["source"]
    assert SOURCE_SHA in rp.load_playbooks("v2")["source"]
    assert SOURCE_SHA_V1 in rp.load_playbooks("v2")["supersedes"]


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


def test_NOTHING_IS_HELD_IN_V2():
    """R-IV.1189(b) supplied the reworded pricing-fact form of all three sentences v1 withheld,
    so v2 holds nothing. The POLICY survives, because the next text that reads as an order gets
    the same treatment."""
    pb = rp.load_playbooks()
    held = {k: v["held_sentences"] for k, v in pb["regimes"].items()
            if v.get("held_sentences")}
    assert held == {}, held
    assert pb["held_policy"], "the policy must survive having nothing to apply to"


def test_V1_STILL_RECORDS_WHAT_IT_HELD():
    """The superseded version is the audit trail. If v1 were edited to look clean, there would
    be no record that three sentences were ever withheld or why."""
    v1 = rp.load_playbooks("v1")
    held = {k: v["held_sentences"] for k, v in v1["regimes"].items()
            if v.get("held_sentences")}
    assert held == {"crash_liquidation": 2, "recovery": 1}
    for key in held:
        assert v1["regimes"][key].get("held_reason")


def test_the_reworded_premium_lines_are_the_ruled_text():
    """Verbatim from the document at R-IV.1189's hash, lines 118 and 146 - bold markers
    stripped as they were for every other line, and the editorial "(Reworded...)" note excluded
    because that is a changelog entry, not a pricing fact."""
    pb = rp.load_playbooks()
    crash = pb["regimes"]["crash_liquidation"]["premium"]
    rec = pb["regimes"]["recovery"]["premium"]
    assert crash.startswith("EXPENSIVE. Premium is at its most expensive here:")
    assert "priced for the move that already happened" in crash
    assert "the two-contract rule, and X3 (60\u201370% of max value under 21 DTE)" in crash
    assert "Reworded" not in crash, "the editorial note is not playbook text"
    assert rec.startswith("CRUSHING. Long premium loses value fastest as volatility deflates.")
    assert "cheapest again once VIX is back in its low band with normal contango" in rec
    assert "Reworded" not in rec


def test_the_reworded_text_is_LINT_CLEAN_which_is_the_point_of_the_rewording():
    """The sentences were withheld BECAUSE they read as orders. The replacements must not."""
    pb = rp.load_playbooks()
    for key in ("crash_liquidation", "recovery"):
        assert rp.order_findings(pb["regimes"][key]["premium"]) == [], key


def test_v2_is_derived_from_v1_and_only_the_two_lines_moved():
    """v2 was DERIVED from v1, not retyped. Eight regimes and all seven overlays must be
    byte-identical, or 200 lines of prose went back through someone's fingers for no reason and
    a dropped clause would be invisible."""
    v1, v2 = rp.load_playbooks("v1"), rp.load_playbooks("v2")
    assert v1["overlays"] == v2["overlays"]
    untouched = set(v1["regimes"]) - {"crash_liquidation", "recovery"}
    assert len(untouched) == 8
    for key in untouched:
        assert v1["regimes"][key] == v2["regimes"][key], key


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

def test_the_REGISTRATION_IS_STILL_RECORDED_after_the_badge_left_the_face():
    """R-IV.1190(b)1 lists what the header carries and (b)6 forbids other prose on the face, so
    the REGISTERED badge came off in v0.1. The FACT did not change, only where it is shown.

    "display only" survives in the settled line - asserted in the v0.1 file, which owns the new
    layout. What this test keeps is the half that the redesign could have quietly lost: that
    both documents still record the registration at all.
    """
    html = _read(os.path.join(FRONTEND, "v2.html"))
    assert 'id="rsBadge"' not in html, "the badge is off the face of the card in v0.1"
    assert "UNREGISTERED" not in html
    for doc in (rp.load_mock(), rp.load_playbooks()):
        assert doc["registered"] is True
        assert "19:07" in doc["registered_by"]
    # and the phrase itself is still on the header, in the line that replaced the badge
    js = _code(_js())
    i = js.index("rsSettled")
    assert "display only" in js[i:i + 400]
    # The header still leads with the title, which is what the badge used to sit beside.
    assert '<span class="tile-title">Regime Strategy</span>' in html


def test_the_labels_are_REGISTERED_with_who_and_when():
    """R-IV.1189(c): Nick, 2026-10-16 19:07 MT. A flipped boolean with no author is a claim
    nobody can check later."""
    for doc in (rp.load_mock(), rp.load_playbooks()):
        assert doc["registered"] is True
        assert doc["registered_at"] == "2026-10-16"
        assert "19:07" in doc["registered_by"]
        assert "R-IV.1189" in doc["registered_by"]


def test_V1_IS_STILL_UNREGISTERED():
    """v1 was built before the labels were registered and must go on saying so."""
    assert rp.load_playbooks("v1")["registered"] is False


def test_REGISTRATION_DID_NOT_MAKE_THE_CARD_A_GATE():
    """THE DISTINCTION THE BADGE HAS TO CARRY. Registration changed what the labels ARE (rules);
    it did not change what the card may DO. §1 and convention #42 are untouched, and both
    documents say so in their own words rather than leaving it to be inferred."""
    for doc in (rp.load_mock(), rp.load_playbooks()):
        note = doc.get("registration_note", "")
        assert "display only" in note.lower()
        assert "gate" in note.lower()
        assert "42" in note


def test_LENS_2_IS_LABELLED_AN_ALARM_AND_IS_NOT_THE_HEADLINE():
    """R-IV.1186(b), §1 and §5. The headline is the base regime; the watchlist reading is the
    high-beta alarm. In the renderer the label block comes BEFORE the lens block, and the lens
    block carries the words."""
    js = _code(_js())
    i = js.index("function renderRegimeStrategy")
    # Anchored to the NEXT FUNCTION, not to a comment. The old anchor was a comment line, which
    # `_code()` strips, so the slice silently fell back to a fixed 6000 characters -- and the
    # live-wiring changes pushed the lens block past it. A function name survives the stripper.
    body = js[i:js.index("function renderRegimePlaybook", i)]
    assert "Watchlist \\u2014" not in body
    assert "(high-beta) alarm" in body
    assert body.index("rs-label") < body.index("rs-lens"), (
        "the base regime must render before the watchlist lens")
    m = rp.load_mock()
    assert "NEVER the headline" in m["lens_split"]["headline_rule"]


def test_the_card_reads_THE_LIVE_LABEL_and_the_versioned_playbook():
    """SUPERSEDED AND RETARGETED. R-IV.1186(c) said "nothing reads or writes a regime table
    yet", and this asserted the card fetched only the two static files. R-IV.1195(b) lifted it:
    "GO on the held live wiring". The label now comes from the route; the playbook stays a
    versioned FILE, which R-IV.1186(b) requires ("stored as versioned files, not editable from
    the UI") and no ruling has changed.
    """
    js = _code(_js())
    i = js.index("async function loadRegimeStrategy")
    # To the next function in the module. `rsChip` was the v0 boundary and the redesign removed
    # it, so the slice is taken to whatever follows rather than to a name that may move again.
    body = js[i:js.index("function rsScale", i)]
    assert body.count("fetch(") == 2
    assert "/api/stable/regime-strategy" in body, "the label is live now (R-IV.1195(b))"
    assert "/assets/regime/regime_mock.json" not in body, (
        "the fixture must not survive as a fallback: plausible numbers on a healthy-looking "
        "card is the /api/crypto/market fault")
    assert "/assets/regime/playbooks.v2.json" in body, (
        "the card must fetch the CURRENT version; the URL and the card's 'playbook vN' line "
        "have to agree")
    assert "apiFetch" not in body, "the card must not call the authed hub helper"
    routes = set(re.findall(r"/api/[A-Za-z0-9_/-]+", body))
    assert routes == {"/api/stable/regime-strategy"}, routes


def test_v0_TOUCHES_NO_KILL_SWITCH_NO_CAPS_NO_JOURNAL():
    """R-IV.1186(c). The kill-switch line is a DISPLAY of a value the fixture carries, so the
    module must contain no write and no kill-switch call."""
    js = _code(_js())
    i = js.index("let _rsMock = null")
    j = js.index("function initGrid()", i)
    module = js[i:j]
    # The read ban moved under R-IV.1195(b); the WRITE ban and the kill-switch ban did not.
    for banned in ("method: 'POST'", 'method: "POST"', "XMLHttpRequest", "apiFetch",
                   "kill_switch =", "killSwitch("):
        assert banned not in module, banned
    routes = set(re.findall(r"/api/[A-Za-z0-9_/-]+", module))
    assert routes == {"/api/stable/regime-strategy"}, routes


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
    k = css.index("Regime Strategy card (R-IV.1186 v0, redesigned")
    # BOUNDED AT THE END OF THE CARD'S OWN BLOCK. The slice used to run to the end of the
    # file, so ANY CSS appended to v2.css later became "the card's CSS" to these checks -- the
    # A1 Agora block landed inside them and failed the card's hex and phone-first guards while
    # the card itself was untouched. A guard whose scope grows with the file reports findings
    # about code it was never about.
    start = css.rindex("/*", 0, k)
    nxt = css.find("AGORA ADDITIONS, PHASE A1", k)
    end = css.rindex("/*", 0, nxt) if nxt != -1 else len(css)
    block = css[start:end]
    assert "min-width: 760px" in block
    # A max-width MEDIA QUERY is what would invert phone-first. `max-width` on an element is a
    # sizing constraint - the premium gauge caps at 120px - and the substring form of this
    # assertion failed on it.
    assert not re.search(r"@media[^{]*max-width", block), (
        "a max-width media query would make the desktop rules the base")


def test_every_class_the_renderer_uses_has_a_style():
    js, css = _code(_js()), _read(os.path.join(FRONTEND, "v2.css"))
    i = js.index("function renderRegimeStrategy")
    used = set(re.findall(r'class="(rs-[a-z0-9-]+)"', js[i:i + 9000]))
    # `rs-badge` is absent on purpose: R-IV.1190(b)1/(b)6 took the badge off the face.
    used |= {"rs-open", "rs-playbook", "rs-held", "rs-pb-title"}
    missing = sorted(c for c in used if "." + c not in css)
    assert not missing, missing


def test_the_pins_moved_for_both_changed_assets():
    html = _read(os.path.join(FRONTEND, "v2.html"))
    for asset, floor in (("v2.js", 63), ("v2.css", 50)):
        m = re.search(re.escape(asset) + r"\?v=(\d+)", html)
        assert m and int(m.group(1)) >= floor, (asset, m and m.group(1))


def test_the_other_pages_pinning_v2_css_moved_too():
    """v2.css is pinned by three pages at independent values; the page missed keeps serving
    whatever was cached under its unchanged pin."""
    for page, floor in (("stater.html", 46), ("abacus.html", 45)):
        m = re.search(r"v2\.css\?v=(\d+)", _read(os.path.join(FRONTEND, page)))
        assert m and int(m.group(1)) >= floor, (page, m and m.group(1))


def test_the_assets_live_where_the_server_serves_them_wholesale():
    """CLAUDE.md: new static files must live under `frontend/assets/`, because only that folder
    is served wholesale — `main.py` routes every other file by name, so a file outside it would
    404 and the card would render its "did not load" message in production."""
    assert os.path.isdir(ASSETS)
    assert ASSETS.replace("\\", "/").endswith("frontend/assets/regime")
    for fn in ("playbooks.v1.json", "playbooks.v2.json", "regime_mock.json"):
        assert os.path.exists(os.path.join(ASSETS, fn))
        json.loads(_read(os.path.join(ASSETS, fn)))
