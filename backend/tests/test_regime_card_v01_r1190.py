"""R-IV.1190 — the v0.1 visual redesign: tokens not hexes, computed not stored, alarm first.

Nick approved three mockups at 00:08 MT on 10-17 and asked for "far fewer words, mostly visuals,
matching Pandora's existing aesthetic". R-IV.1190(b) is explicit that the mockups are DESIGN
FILES, not code to paste: the card is built from v2.css primitives that already exist and
already match.

    mockup                                what is used instead
    -----------------------------------   -------------------------------------------------
    the KILL span's exact styling         .dead-badge (byte-for-byte the same rule)
    a track + i ticks + b marker          .vc-gauge i / .vc-gauge b
    chip(c, b) with inline colours        .status-chip / .chip and their state classes
    #7CFF6B #ff5c33 #223258 #70829d       var(--up) var(--down) var(--border-strong) var(--text-3)
    @keyframes apisPulse / kodiakPulse    apis-pulse / kodiak-pulse (already defined)

THREE THINGS THESE TESTS ARE REALLY FOR:

  1. NO RAW HEXES IN THE DECLARATIONS. A hex that survives here is a colour that will not
     follow a theme change, and the whole point of (b) was to stop that.
  2. THE NUMBERS ARE COMPUTED FROM THE FIXTURE. The mockup hard-codes "+5.3%" and a marker at
     "77.2%". Storing those would make v1 replace the renderer as well as the data.
  3. THE ALARM IS CHECKED BEFORE THE REGIME COLOUR. Today's fixture is a Correction (grey) with
     the kill-switch ACTIVE, so the card must pulse vermilion. Written the other way round, an
     alarm loses to a label - and the current fixture is exactly the case that catches it.
"""
from __future__ import annotations

import io
import json
import os
import re
import re

import pytest

from services import regime_playbook as rp

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(os.path.dirname(BACKEND), "frontend")
ASSETS = os.path.join(FRONTEND, "assets", "regime")


def _read(name: str) -> str:
    return io.open(os.path.join(FRONTEND, name), encoding="utf-8", errors="replace").read()


def _js_code() -> str:
    """v2.js with `//` comments stripped - a comment naming a banned pattern contains it."""
    out = []
    for line in _read("v2.js").split("\n"):
        i = line.find("//")
        if i > 0:
            before = line[:i]
            if before.count("'") % 2 or before.count('"') % 2 or before.count("`") % 2:
                i = -1
        out.append(line if i < 0 else line[:i])
    return "\n".join(out)


def _card_css(strip_comments: bool = True) -> str:
    """The card's CSS block, sliced from its comment's OPENING.

    Slicing from text INSIDE the opening comment leaves it unterminated, so the stripper never
    removes it and the check then reports the comment's own prose as a finding. That happened
    while writing this file.
    """
    css = _read("v2.css")
    k = css.index("Regime Strategy card (R-IV.1186 v0, redesigned")
    blk = css[css.rindex("/*", 0, k):]
    return re.sub(r"/\*.*?\*/", "", blk, flags=re.S) if strip_comments else blk


# ── 1. tokens, not hexes ────────────────────────────────────────────────────

def test_NO_RAW_HEX_IN_THE_CARDS_DECLARATIONS():
    """R-IV.1190(b): v2.css tokens, not the mockup's hard-coded hexes. A hex that survives here
    is a colour that will not follow a theme change."""
    hexes = sorted(set(re.findall(r"#[0-9a-fA-F]{3,8}", _card_css())))
    assert hexes == [], hexes


def test_the_gradients_intermediate_stops_are_DERIVED_not_picked():
    """The mockup's five-stop gradient has two stops no token covers. color-mix reproduces them
    from --down and --up, so the whole track follows the theme rather than two hexes staying
    behind. color-mix is already relied on by this file's pulse keyframes."""
    code = _card_css()
    i = code.index(".rs-slider")
    blk = code[i:i + 500]
    assert blk.count("color-mix") == 2
    assert "var(--down)" in blk and "var(--up)" in blk and "var(--border-strong)" in blk


def test_the_card_uses_the_EXISTING_primitives():
    code = _card_css()
    js = _js_code()
    # gauges are .vc-gauge, so tick and marker geometry is the dashboard's
    assert js.count("vc-gauge") >= 3
    # the index state and the overlays use the existing chip families
    assert "status-chip" in js
    assert "class=\"chip " in js or "'chip " in js
    # and the card's own rules only EXTEND those, never redefine their geometry
    # A TOP-LEVEL rule would redefine the shared primitive. `.rs-ovs .chip { ... }` is a
    # descendant selector scoped to this card, which is precisely "extend, don't redefine" --
    # and the first version of this test rejected it.
    assert not re.search(r"(?m)^\.vc-gauge\s*\{", code), (
        "the card must not redefine the shared gauge")
    assert not re.search(r"(?m)^\.chip\s*\{", code), (
        "the card must not redefine the shared chip")
    assert ".rs-ovs .chip" in code, "the overlay chips must SCOPE their override to the card"


def test_the_KILL_tag_reuses_dead_badge_rather_than_restyling_it():
    """The mockup's KILL span and `.dead-badge` are the same rule written twice. The class is
    used and the duplicate is not re-declared."""
    html = _read("v2.html")
    i = html.index('id="rsKill"')
    assert 'class="dead-badge"' in html[max(0, i - 120):i + 40]
    assert ".dead-badge" not in _card_css(), "dead-badge must not be re-declared here"


def test_the_pulse_uses_the_EXISTING_keyframes():
    code = _card_css()
    assert "apis-pulse" in code and "kodiak-pulse" in code
    assert "@keyframes" not in code, "the card must not define its own keyframes"


# ── 2. the header (R-IV.1190(b)1) ───────────────────────────────────────────

def test_the_header_carries_exactly_the_ruled_elements():
    html = _read("v2.html")
    i = html.index('gs-id="regime-strategy"')
    # To the BODY, not to the first `</div>` -- that one closes `<div class="spacer">` and
    # truncated the header before every element this test is about.
    hdr = html[i:html.index('class="tile-body"', i)]
    assert "Regime Strategy" in hdr
    assert 'id="rsKill"' in hdr
    assert 'id="rsSettled"' in hdr
    assert 'id="rsHealth"' in hdr
    assert "tile-grip" in hdr


def test_the_KILL_tag_is_HIDDEN_until_the_switch_is_active():
    """A permanent KILL chip is an alarm nobody reads. It starts hidden in the markup and the
    renderer decides."""
    html = _read("v2.html")
    i = html.index('id="rsKill"')
    assert "hidden" in html[i:i + 60]
    js = _js_code()
    j = js.index("const kill = $('rsKill')")
    body = js[j:j + 600]
    assert "kill.hidden = !on" in body
    assert "ACTIVE" in body


def test_the_settled_line_still_says_DISPLAY_ONLY():
    """R-IV.1189(d) accepted that "display only" surviving registration is the right reading of
    §1 and #42. The badge came off the face of the card under R-IV.1190(b)1/(b)6, so the phrase
    has to live in the line that replaced it - otherwise the redesign quietly drops it."""
    js = _js_code()
    i = js.index("rsSettled")
    assert "display only" in js[i:i + 400]


def test_the_registration_is_still_recorded_even_though_the_badge_left_the_face():
    """The fact did not change, only where it is shown. Both documents still carry it."""
    for doc in (rp.load_mock(), rp.load_playbooks()):
        assert doc["registered"] is True
        assert "19:07" in doc["registered_by"]


# ── 3. the slider (R-IV.1190(b)2) ───────────────────────────────────────────

def test_the_slider_has_the_TEN_regimes_in_the_ruled_bear_to_bull_order():
    js = _js_code()
    i = js.index("const RS_SLIDER = [")
    order = re.findall(r"'([a-z_]+)'", js[i:js.index("]", i)])
    assert order == ["crash_liquidation", "bear_market", "bear_market_rally", "breakdown",
                     "correction", "range_chop", "recovery", "narrow_uptrend", "uptrend",
                     "melt_up"], order


def test_every_slider_key_is_a_registered_regime():
    """A tick with no playbook behind it would render a label from nowhere."""
    js = _js_code()
    i = js.index("const RS_SLIDER = [")
    order = re.findall(r"'([a-z_]+)'", js[i:js.index("]", i)])
    regimes = rp.load_playbooks()["regimes"]
    assert len(order) == 10
    for k in order:
        assert k in regimes, k
    assert set(order) == set(regimes)


def test_the_slider_order_is_a_CONSTANT_not_a_fixture_field():
    """A FIXED presentation order. In v1 it must not vary with the reading, which it could if it
    travelled in the data."""
    assert "slider_order" not in json.dumps(rp.load_mock())


def test_the_marker_sits_on_the_current_regime():
    js = _js_code()
    i = js.index("const at = RS_SLIDER.indexOf(m.regime_key)")
    body = js[i:i + 600]
    assert "at * 10 + 5" in body, "the marker must use the same tick geometry as the ticks"
    assert "at === -1" in body, "an unknown regime must render no marker rather than tick 0"


def test_the_tripwires_come_from_the_fixture_with_their_basis():
    """Numbers under each end, and each one says which rule turns on it - §2 row 4 for the bear
    end, §4's proves-wrong for the bull end."""
    tw = rp.load_mock()["tripwires"]
    assert "768.50" in tw["bear"]["text"]
    assert "726.77" in tw["bull"]["text"] and "289.07" in tw["bull"]["text"]
    for side in ("bear", "bull"):
        assert tw[side]["basis"], side


# ── 4. the index strip (R-IV.1190(b)3) ──────────────────────────────────────

def test_the_fixture_carries_the_10_16_closes_from_the_ruling():
    per = {x["ticker"]: x for x in rp.load_mock()["per_index"]}
    assert (per["SPY"]["price"], per["SPY"]["ma50"], per["SPY"]["ma200"]) == (763.25, 768.50, 725.01)
    assert (per["QQQ"]["price"], per["QQQ"]["ma50"], per["QQQ"]["ma200"]) == (709.80, 726.77, 674.91)
    assert (per["IWM"]["price"], per["IWM"]["ma50"], per["IWM"]["ma200"]) == (270.44, 289.07, 277.65)


@pytest.mark.parametrize("ticker,d200,d50", [
    ("SPY", "+5.3", "-0.7"), ("QQQ", "+5.2", "-2.3"), ("IWM", "-2.6", "-6.4"),
])
def test_the_percentages_REPRODUCE_the_approved_mockup_from_the_stored_closes(ticker, d200, d50):
    """THE CHECK THAT THE FIXTURE AND THE APPROVED DESIGN AGREE. Every figure in the mockup is
    exactly (price - ma) / ma, so storing the three closes and computing is not a
    reinterpretation of the design - it is the design's own arithmetic."""
    ix = next(x for x in rp.load_mock()["per_index"] if x["ticker"] == ticker)
    f = lambda v: ("%+.1f" % v).replace("+-", "-")
    assert f((ix["price"] - ix["ma200"]) / ix["ma200"] * 100) == d200
    assert f((ix["price"] - ix["ma50"]) / ix["ma50"] * 100) == d50


def test_the_percentages_are_COMPUTED_and_not_stored():
    """If they were stored, v1 would have to replace the renderer as well as the data."""
    blob = json.dumps(rp.load_mock())
    for shown in ("+5.3%", "-0.7%", "+5.2%", "-2.3%", "-2.6%", "-6.4%"):
        assert shown not in blob, shown
    js = _js_code()
    assert "const rsPct = (px, ma) => (px - ma) / ma * 100" in js


def test_the_price_marker_is_vermilion_below_the_50d_and_lime_above():
    """R-IV.1190(b)3, and the sign comes from the numbers rather than from a stored colour."""
    js = _js_code()
    i = js.index("const below = ix.price < ix.ma50")
    body = js[i:i + 900]
    assert "rs-below" in body and "rs-above" in body
    code = _card_css()
    assert "b.rs-below { background: var(--down)" in code
    assert "b.rs-above { background: var(--up)" in code


def test_all_three_indices_are_below_their_50d_today_so_all_three_read_vermilion():
    """Not a tautology: it is the state the approved mockup shows, and it is what makes the
    marker colouring visible at all on this fixture."""
    for ix in rp.load_mock()["per_index"]:
        assert ix["price"] < ix["ma50"], ix["ticker"]


def test_the_gauge_scale_is_stated_rather_than_magic():
    js = _js_code()
    i = js.index("function rsScale")
    body = js[i:js.index("\n  }", i)]
    assert "0.06" in body, "the padding must be explicit"
    assert "Math.min" in body and "Math.max" in body


# ── 5. evidence and overlays (R-IV.1190(b)4) ────────────────────────────────

def test_the_five_families_are_in_the_ruled_order():
    fams = [f["key"] for f in rp.load_mock()["evidence"]["families"]]
    assert fams == ["STRUCT", "BREADTH", "CREDIT", "VOL", "CARRY"]


def test_a_FAMILY_WITH_NO_DATA_renders_in_text_3_and_not_as_a_reading():
    """R-IV.1190(b)4. An unmeasured family is neither reassuring nor alarming, so it is painted
    neither green nor red. VOL and CARRY are both unmeasured today and each says why."""
    fams = {f["key"]: f for f in rp.load_mock()["evidence"]["families"]}
    assert fams["VOL"]["state"] is None and fams["VOL"]["why"]
    assert fams["CARRY"]["state"] is None and fams["CARRY"]["why"]
    code = _card_css()
    assert ".rs-dot.rs-nodata { background: var(--text-3); }" in code


def test_the_overlay_chip_states_are_the_ruled_four():
    """watch = teal, active = vermilion, candidate = dashed, clear = muted."""
    js = _js_code()
    i = js.index("const ovs = (m.overlays || [])")
    body = js[i:i + 700]
    assert "'WATCH'" in body and "'emg'" in body          # teal
    assert "'ACTIVE'" in body and "'fad'" in body          # vermilion
    assert "'CANDIDATE'" in body and "rs-cand" in body     # dashed
    assert "rs-clear" in body                              # muted
    code = _card_css()
    assert ".rs-ovs .chip.rs-cand { border-style: dashed;" in code


def test_the_fixture_overlays_are_credit_WATCH_and_AI_CANDIDATE():
    """R-IV.1190(d). CANDIDATE is weaker than WATCH - §5 calls AI-capex a "WATCH candidate" -
    and must not render as WATCH."""
    ov = {o["short"]: o["state"] for o in rp.load_mock()["overlays"]}
    assert ov["CREDIT"] == "WATCH"
    assert ov["AI"] == "CANDIDATE"
    assert {k: v for k, v in ov.items() if v != "CLEAR"} == {"CREDIT": "WATCH", "AI": "CANDIDATE"}


def test_every_overlay_short_resolves_to_a_registered_overlay():
    pb = rp.load_playbooks()["overlays"]
    for o in rp.load_mock()["overlays"]:
        assert o["key"] in pb, o["key"]


# ── 6. the three lights (R-IV.1190(b)5) ─────────────────────────────────────

def test_each_light_has_a_value_AND_A_BASIS():
    """R-IV.1190(b)5: "Each value must come from an existing rule or a fixture field. No new
    advice text." Without the basis the card asserts three words with no provenance, which is
    the thing this module exists not to do."""
    L = rp.load_mock()["lights"]
    assert set(L) == {"shorts", "longs", "premium"}
    for k, v in L.items():
        assert v.get("value"), k
        assert v.get("basis"), k


def test_the_lights_cite_rules_that_exist():
    L = rp.load_mock()["lights"]
    assert "C5" in L["shorts"]["basis"] and "B3" in L["shorts"]["value"]
    assert "narrow" in L["longs"]["basis"]
    assert "premium posture" in L["premium"]["basis"].lower()


def test_the_premium_light_is_a_THREE_SEGMENT_gauge():
    L = rp.load_mock()["lights"]["premium"]
    assert L["bands"] == 3
    assert 0 <= L["position_pct"] <= 100
    js = _js_code()
    i = js.index("const segs = Number(prem.bands || 3)")
    body = js[i:i + 500]
    assert "segs - 1" in body, "a 3-band gauge draws 2 dividers"
    assert "vc-gauge rs-prem" in body


def test_the_lights_carry_NO_NEW_ADVICE_TEXT():
    """Every value is a word the rules already use, and the no-orders lint must pass over them
    exactly as it does over the playbook."""
    for k, v in rp.load_mock()["lights"].items():
        assert rp.order_findings(v["value"]) == [], (k, v["value"])
        assert rp.order_findings(v["basis"]) == [], (k, v["basis"])


# ── 7. the outline rule (R-IV.1190(c)) ──────────────────────────────────────

def test_the_three_outline_groups_are_the_ruled_ones():
    js = _js_code()
    lime = re.findall(r"'([a-z_]+)'", js[js.index("const RS_LIME = ["):js.index("]", js.index("const RS_LIME = ["))])
    verm = re.findall(r"'([a-z_]+)'", js[js.index("const RS_VERMILION = ["):js.index("]", js.index("const RS_VERMILION = ["))])
    assert set(lime) == {"uptrend", "melt_up", "recovery"}
    assert set(verm) == {"breakdown", "bear_market", "bear_market_rally", "crash_liquidation"}
    # grey is everything else - the three that remain
    rest = set(rp.load_playbooks()["regimes"]) - set(lime) - set(verm)
    assert rest == {"narrow_uptrend", "range_chop", "correction"}


def test_THE_ALARM_IS_TESTED_BEFORE_THE_REGIME_COLOUR():
    """R-IV.1190(c): the override beats the regime colour. That is only true if it is checked
    first, and written the other way round an alarm loses to a label."""
    js = _js_code()
    i = js.index("function rsOutlineClass")
    body = js[i:js.index("\n  }", i)]
    assert body.index("killed || anyActive") < body.index("RS_VERMILION"), body
    assert body.index("killed || anyActive") < body.index("RS_LIME")


def test_a_correction_with_the_kill_switch_active_pulses_VERMILION():
    """THE CASE TODAY'S FIXTURE IS. Correction is a GREY regime, the kill-switch is ACTIVE, so
    the card must pulse vermilion - which is exactly the state that catches the override being
    written in the wrong order."""
    m = rp.load_mock()
    assert m["regime_key"] == "correction"
    assert m["intraday"]["kill_switch"] == "ACTIVE"
    js = _js_code()
    i = js.index("function rsOutlineClass")
    body = js[i:js.index("\n  }", i)]
    assert "'rs-o-bear'" in body


def test_an_ACTIVE_overlay_also_forces_vermilion():
    js = _js_code()
    i = js.index("function rsOutlineClass")
    body = js[i:js.index("\n  }", i)]
    assert "anyActive" in body
    assert "'ACTIVE'" in body


def test_the_pulse_is_on_the_OUTLINE_and_never_the_text():
    """H-13. A card whose text fades in and out cannot be read mid-cycle."""
    code = _card_css()
    for sel in (".rs-tile.rs-o-bull", ".rs-tile.rs-o-bear"):
        i = code.index(sel)
        rule = code[i:code.index("}", i)]
        assert "animation:" in rule
        # The PROPERTY `color`, not any substring: `border-color` is the outline this rule is
        # supposed to paint, and forbidding the substring forbids the feature.
        assert not re.search(r"(?:^|[;{]\s*)color\s*:", rule), (
            "the pulse must not animate text colour")
    assert "box-shadow" in _read("v2.css")[_read("v2.css").index("@keyframes apis-pulse"):][:400]


def test_reduced_motion_drops_the_ANIMATION_and_keeps_the_COLOUR():
    """The colour IS the state; only the movement is decoration."""
    code = _card_css()
    i = code.index("prefers-reduced-motion")
    blk = code[i:code.index("}\n", code.index("{", i))]
    assert "animation: none" in blk
    assert "border-color" not in blk, "reduced motion must not drop the colour"


# ── 8. phone-first, and the prose stays behind Open ─────────────────────────

def test_the_base_rules_are_the_phones_and_the_query_WIDENS():
    code = _card_css()
    assert "min-width: 760px" in code
    # A max-width MEDIA QUERY is what would invert phone-first. `max-width` on an element is a
    # sizing constraint (the premium gauge caps at 120px) and has nothing to do with it.
    assert not re.search(r"@media[^{]*max-width", code), (
        "a max-width media query would make the desktop rules the base")
    i = code.index("min-width: 760px")
    blk = code[i:]
    assert "flex-direction: row" in blk, "the index strip widens to a row"
    assert "grid-template-columns: repeat(2" in blk, "the two lower boxes sit side by side"


def test_the_index_strip_STACKS_by_default():
    code = _card_css()
    i = code.index(".rs-strip {")
    assert "flex-direction: column" in code[i:code.index("}", i)]


def test_the_card_is_still_second_in_the_mobile_order():
    js = _js_code()
    i = js.index("const MOBILE_ORDER = [")
    order = re.findall(r"'([a-z-]+)'", js[i:js.index("]", i)])
    assert order.index("regime-strategy") == 1


def test_NO_PROSE_ON_THE_FACE_OF_THE_CARD():
    """R-IV.1190(b)6: the playbook stays behind Open, and no other prose is on the face. The
    v0 face carried WATCH NOW bullets, a proves-me-wrong line, a tape line, a counterexample
    and a costs block; all of that is now inside the expander."""
    js = _js_code()
    i = js.index("function renderRegimeStrategy")
    face = js[i:js.index("function renderRegimePlaybook", i)]
    for gone in ("WATCH NOW", "PROVES ME WRONG", "TAPE REWARDING", "rs-counter", "rs-costs"):
        assert gone not in face, gone
    pb = js[js.index("function renderRegimePlaybook"):]
    assert "COSTS, STATED" in pb, "the costs line moved into the playbook, not away"


def test_the_playbook_still_uses_the_R_IV_1189_text():
    js = _js_code()
    i = js.index("function renderRegimePlaybook")
    body = js[i:js.index("function toggleRegimePlaybook", i)]
    assert "r.premium" in body
    assert rp.load_playbooks()["regimes"]["correction"]["premium"]


# ── 9. still no wiring, still lint-clean ───────────────────────────────────

def test_the_card_reads_EXACTLY_ONE_ROUTE_and_it_is_the_regime_one():
    """SUPERSEDED AND RETARGETED. This asserted `/api/` appeared nowhere, under R-IV.1186(c)'s
    "nothing reads or writes a regime table yet". R-IV.1195(b) lifted that: "GO on the held live
    wiring". So the constraint moves to the tightest form the new ruling allows -- one route,
    and that route -- rather than being dropped.
    """
    js = _js_code()
    i = js.index("async function loadRegimeStrategy")
    body = js[i:js.index("function rsScale", i)]
    assert body.count("fetch(") == 2
    assert "apiFetch" not in body, "the card must not use the authed hub helper"
    routes = set(re.findall(r"/api/[A-Za-z0-9_/-]+", body))
    assert routes == {"/api/stable/regime-strategy"}, routes


def test_v0_1_STILL_TOUCHES_NO_KILL_SWITCH_NO_CAPS_NO_JOURNAL():
    """The half of R-IV.1186(c) that NO ruling has lifted: the card reads, it never writes, and
    it never calls the kill-switch. Only the read ban moved."""
    js = _js_code()
    i = js.index("let _rsMock = null")
    module = js[i:js.index("function initGrid()", i)]
    for banned in ("method: 'POST'", 'method: "POST"', "XMLHttpRequest", "apiFetch",
                   "kill_switch =", "killSwitch("):
        assert banned not in module, banned
    routes = set(re.findall(r"/api/[A-Za-z0-9_/-]+", module))
    assert routes == {"/api/stable/regime-strategy"}, routes


def test_the_no_orders_lint_still_passes_over_every_version_and_the_fixture():
    rp.assert_no_orders_any_version()
    findings = []
    for path, text in rp.walk_texts(rp.load_mock()):
        findings.extend(rp.lint_text(text, path))
    assert findings == [], findings


def test_the_pins_moved_for_both_changed_assets():
    html = _read("v2.html")
    for asset, floor in (("v2.js", 64), ("v2.css", 51)):
        m = re.search(re.escape(asset) + r"\?v=(\d+)", html)
        assert m and int(m.group(1)) >= floor, (asset, m and m.group(1))


def test_the_other_pages_pinning_v2_css_moved_too():
    for page, floor in (("stater.html", 47), ("abacus.html", 46)):
        m = re.search(r"v2\.css\?v=(\d+)", _read(page))
        assert m and int(m.group(1)) >= floor, (page, m and m.group(1))


def test_every_rs_class_the_renderer_emits_has_a_style():
    js, css = _js_code(), _read("v2.css")
    i = js.index("function renderRegimeStrategy")
    used = set(re.findall(r"rs-[a-z0-9_]+", js[i:js.index("function toggleRegimePlaybook", i)]))
    # state classes built by concatenation, and ids, are not selectors
    used -= {"rs-o-bear", "rs-o-bull", "rs-o-mixed"}
    missing = sorted(c for c in used if "." + c not in css)
    assert not missing, missing
