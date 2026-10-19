"""R-IV.1209(c) A2 — regime bar v2: the lean scale, the agreement rules, and the left drawer.

(d) IS A RULE SET WITH A COUNT IN IT, so the parts that can be got subtly wrong are the ones
these tests go after:

  - CALM and PREMIUM SELLING are 0, NOT bull ((d)1). Calm is not a bull call, and a quiet tape
    read as bullish is how a gauge starts lying in the direction its reader hopes.
  - The Tide read has NO EXTREME ((d)1), however strong its word sounds.
  - "No reading" is 0 and still OCCUPIES ITS SLOT. The threshold is "3 or more lean one way and
    0 lean the other", so three of FIVE -- not three of however many happened to report.
  - A read at an extreme pulses on its own ((d)3) even when the group is mixed, and the kill
    switch beats the group rule entirely ((d)5).

The lean tables and `regimeAgreement` are extracted from v2.js and executed, rather than
pattern-matched: a count rule asserted by grep is a count rule nobody ran. Node is used when
present and the test skips when it is not, so the suite stays green on a machine without it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

import pytest

from ._srcscan import read_source

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND)
FRONTEND = os.path.join(ROOT, "frontend")
NODE = shutil.which("node")


def _js():
    return read_source(os.path.join(FRONTEND, "v2.js"))


def _html():
    return read_source(os.path.join(FRONTEND, "v2.html"))


def _css():
    return read_source(os.path.join(FRONTEND, "v2.css"))


def _run_lean(script_tail: str):
    """Execute the lean engine out of v2.js with a tail appended, and return its JSON."""
    if not NODE:
        pytest.skip("node is not on this machine")
    js = _js()
    start = js.index("const LEAN_SCALE")
    end = js.index("function renderRegimeBand")
    block = js[start:end]
    # `leanColor` lives earlier in the file and is not needed by the rules under test.
    prog = block + "\n" + script_tail
    r = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-2000:]
    return json.loads(r.stdout.strip().splitlines()[-1])


# ── (d)1: the lean of each read ─────────────────────────────────────────────

def test_THE_RULED_LEANS_ARE_THE_CODED_LEANS():
    """Every word R-IV.1209(d)1 names, checked against what `leanOf` returns."""
    cases = {
        # Strategy
        "MELT-UP": "strong-bull", "UPTREND": "bull", "NARROW UPTREND": "bull",
        "RECOVERY": "bull", "RANGE / CHOP": "neutral", "CORRECTION": "bear",
        "BEAR-MARKET RALLY": "bear", "BREAKDOWN": "bear", "BEAR MARKET": "bear",
        "CRASH / LIQUIDATION": "strong-bear",
        # Market mix
        "TORO MAJOR": "strong-bull", "TORO MINOR": "bull", "NEUTRAL": "neutral",
        "URSA MINOR": "bear", "URSA MAJOR": "strong-bear",
        # Theme breadth
        "STRONG BUY": "strong-bull", "MODERATE BUY": "bull",
        "MODERATE SELL": "bear", "STRONG SELL": "strong-bear",
        # Tide
        "BULL FLOW": "bull", "BEAR FLOW": "bear", "PREMIUM SELLING": "notable",
        "TWO-WAY": "neutral", "NO READING": "neutral",
        # Vol curve
        "CALM": "notable", "FIRMING": "bear", "STRESS": "strong-bear",
    }
    got = _run_lean(
        "const out={};"
        + "".join("out[%s]=leanOf(%s);" % (json.dumps(w), json.dumps(w)) for w in cases)
        + "console.log(JSON.stringify(out));")
    for word, want in cases.items():
        assert got[word] == want, (word, got[word], want)


def test_CALM_AND_PREMIUM_SELLING_ARE_NOT_BULL():
    """(d)1 says so outright: "CALM = 0 (teal; calm is not a bull call)". A quiet tape read as
    bullish is how a gauge starts lying in the direction its reader hopes."""
    got = _run_lean(
        "console.log(JSON.stringify({calm: leanSide(leanOf('CALM')),"
        " prem: leanSide(leanOf('PREMIUM SELLING')),"
        " calmX: leanExtreme(leanOf('CALM'), 'CALM')}));")
    assert got["calm"] == 0
    assert got["prem"] == 0
    assert got["calmX"] is False


def test_THE_TIDE_READ_HAS_NO_EXTREME():
    """(d)1: "No extreme." BULL FLOW leans bull but can never be the extreme that turns an
    agreement into a group pulse."""
    got = _run_lean(
        "console.log(JSON.stringify({"
        " bullSide: leanSide(leanOf('BULL FLOW')),"
        " bullX: leanExtreme(leanOf('BULL FLOW'), 'BULL FLOW'),"
        " bearX: leanExtreme(leanOf('BEAR FLOW'), 'BEAR FLOW')}));")
    assert got["bullSide"] == 1, "it still leans"
    assert got["bullX"] is False
    assert got["bearX"] is False


def test_AN_UNKNOWN_WORD_IS_NULL_NOT_NEUTRAL():
    """A word the table does not know is a gap, not a zero. Defaulting it to neutral would let
    a renamed backend label quietly join the count as a vote for nothing."""
    got = _run_lean("console.log(JSON.stringify({u: leanOf('WOBBLY'), e: leanOf(''),"
                    " n: leanOf(null)}));")
    assert got["u"] is None and got["e"] is None and got["n"] is None


# ── (d)4: the agreement rules ───────────────────────────────────────────────

def _agree(words):
    tail = ("const reads=%s.map(w=>({word:w, lean:leanOf(w)}));"
            "console.log(JSON.stringify(regimeAgreement(reads)));" % json.dumps(words))
    return _run_lean(tail)


def test_THREE_ONE_WAY_AND_ZERO_THE_OTHER_OUTLINES_EVERY_BOX():
    """(d)4: "3 or more lean one way and 0 lean the other: every regime box gets a solid outline
    in that side's colour." """
    a = _agree(["UPTREND", "TORO MINOR", "MODERATE BUY", "TWO-WAY", "CALM"])
    assert a["bull"] == 3 and a["bear"] == 0
    assert a["consistent"] is True
    assert a["outline"] == "bull"
    assert a["pulse"] is False, "no extreme on that side yet"


def test_AGREEMENT_PLUS_A_SAME_SIDE_EXTREME_PULSES_EVERY_BOX():
    """(d)4: "Agreement AND at least one same-side extreme: every regime box pulses." """
    a = _agree(["MELT-UP", "TORO MINOR", "MODERATE BUY", "TWO-WAY", "CALM"])
    assert a["consistent"] is True and a["outline"] == "bull"
    assert a["pulse"] is True


def test_AN_EXTREME_ON_THE_OTHER_SIDE_DOES_NOT_PULSE_THE_GROUP():
    """"Same-side" is load-bearing. A bear extreme cannot be what makes a bull agreement pulse
    -- and in fact a lean on the other side breaks the agreement outright."""
    a = _agree(["STRESS", "TORO MINOR", "MODERATE BUY", "BULL FLOW", "NEUTRAL"])
    assert a["bear"] == 1, "STRESS leans bear"
    assert a["consistent"] is False, "a lean on the other side breaks 'and 0 lean the other'"
    assert a["outline"] == "grey"
    assert a["pulse"] is False


def test_ONE_LEAN_THE_OTHER_WAY_MAKES_IT_GREY():
    """(d)4: "Otherwise: grey outlines." Two bull and one bear is mixed, not a weak bull."""
    a = _agree(["UPTREND", "TORO MINOR", "MODERATE SELL", "TWO-WAY", "CALM"])
    assert a["bull"] == 2 and a["bear"] == 1
    assert a["consistent"] is False and a["outline"] == "grey"


def test_TWO_LEANS_AND_THREE_NEUTRALS_IS_STILL_GREY():
    """Three is the threshold, so two with nothing against is NOT agreement. The rule is a
    count, and a count read as "whichever side is ahead" is a different rule."""
    a = _agree(["UPTREND", "TORO MINOR", "NEUTRAL", "TWO-WAY", "CALM"])
    assert a["bull"] == 2 and a["bear"] == 0
    assert a["consistent"] is False and a["outline"] == "grey"


def test_NO_READING_OCCUPIES_ITS_SLOT():
    """THE COUNT IS OUT OF FIVE. Three bull reads beside two that cannot answer IS agreement;
    but two bull beside three silent ones is not -- and it would be if the denominator shrank to
    the reads that reported."""
    a = _agree(["UPTREND", "TORO MINOR", "MODERATE BUY", "NO READING", "NO READING"])
    assert a["bull"] == 3 and a["bear"] == 0 and a["consistent"] is True
    b = _agree(["UPTREND", "TORO MINOR", "NO READING", "NO READING", "NO READING"])
    assert b["bull"] == 2 and b["consistent"] is False


def test_the_agreement_states_its_BASIS():
    """So the tooltip can explain the outlines rather than leaving a reader to count dots."""
    a = _agree(["URSA MAJOR", "STRONG SELL", "BREAKDOWN", "TWO-WAY", "CALM"])
    assert a["outline"] == "bear" and a["pulse"] is True
    assert "of 5 lean bear" in a["basis"]
    assert "extreme on that side" in a["basis"]
    m = _agree(["UPTREND", "MODERATE SELL", "NEUTRAL", "TWO-WAY", "CALM"])
    assert m["basis"].startswith("mixed:")


# ── (d)3 and (d)5: the per-read pulse, and the kill switch beating the group ──

def test_A_SINGLE_EXTREME_PULSES_ITS_OWN_BOX_WHATEVER_THE_OTHERS_SAY():
    """(d)3. The CSS carries it: the own-box rules come AFTER the group rules and use
    !important on the border, so a grey group cannot grey out an extreme's own outline."""
    css = _css()
    i = css.index("PHASE A2")
    block = css[i:]
    gi = block.index(".rb-grp-pulse.rb-grp-bull {")
    xi = block.index(".rb-cell.rb-x-bull {")
    assert xi > gi, "the own-extreme rule must come after the group rule"
    rule = block[xi:block.index("}", xi)]
    assert "!important" in rule
    assert "animation:" in rule


def test_THE_KILL_SWITCH_ALARM_BEATS_THE_GROUP_RULE():
    """(d)5: "Kill switch ARMED, or any overlay ACTIVE: red alarm pulse on the Strategy card
    regardless of (4)." """
    js = _js()
    i = js.index("rb-alarm")
    body = js[max(0, i - 400):i + 200]
    assert "ARMED" in body
    css = _css()
    assert ".tile.rb-alarm" in css
    rule = css[css.index(".tile.rb-alarm"):]
    rule = rule[:rule.index("}")]
    assert "!important" in rule and "kodiak-pulse" in rule


def test_PREFERS_REDUCED_MOTION_STOPS_EVERY_A2_ANIMATION():
    """(d)7. Every keyframe this block introduces has to be named in the reduce query, or one
    of them keeps moving for a reader who asked for stillness."""
    css = _css()
    i = css.index("PHASE A2")
    block = css[i:]
    anim = set(re.findall(r"animation:\s*([A-Za-z-]+)", block)) - {"none"}
    j = block.rindex("@media (prefers-reduced-motion: reduce)")
    reduce_block = block[j:]
    assert "animation: none !important" in reduce_block
    # Every selector that animates must appear in the reduce block.
    for sel in (".rb-grp-pulse.rb-grp-bull", ".rb-grp-pulse.rb-grp-bear",
                ".rb-cell.rb-x-bull", ".rb-cell.rb-x-bear",
                ".rb-x-bull .rb-lab-x", ".rb-x-bear .rb-lab-x", ".tile.rb-alarm"):
        assert sel in reduce_block, sel
    assert anim, "there are animations to turn off"


# ── the 2x2 grid, the gauges, the details toggles ──────────────────────────

def test_THE_BAND_IS_A_2x2_GRID_OF_BIG_LABELS():
    js = _js()
    i = js.index("band.innerHTML")
    body = js[i:i + 1800]
    for key in ("'mix'", "'breadth'", "'tide'", "'vol'"):
        assert "rbCell(" + key in body, key
    css = _css()
    k = css.index("PHASE A2")
    block = css[k:]
    assert ".rb-grid { display: grid; grid-template-columns: 1fr; gap: 6px; }" in block
    assert "grid-template-columns: 1fr 1fr" in block[block.index("@media (min-width: 769px)"):]


def test_EVERY_REGIME_LABEL_WEARS_ORBIT():
    """Nick's first tweak. Declared as a var so a label cannot drift onto the mono stack by
    being written out by hand, and the font is ALREADY loaded for the PANDORA logo."""
    css = _css()
    assert "--orbit: 'Orbit'" in css
    for sel in (".rb-lab", ".rd-lab"):
        i = css.index(sel + " {")
        assert "var(--orbit)" in css[i:css.index("}", i)], sel
    assert "family=Orbit" in _html(), "the font must actually be loaded"


def test_A_READ_WITH_NO_NUMBER_GETS_NO_GAUGE_MARKER():
    """An empty track is honest. A marker at zero is a reading, and the Tide read has no 0-100
    position at all."""
    js = _js()
    i = js.index("function rbCell")
    body = js[i:js.index("\n  }", i)]
    assert "pct != null" in body
    assert "rb-g-none" in body


def test_BOTH_LENS_VIEWS_RETURN_THE_GAUGE_POSITION():
    """The 0-100 figure each gauge needs was already computed inside both views and thrown
    away. Returned now rather than re-derived in the renderer: two derivations of one position
    would eventually disagree, and the one on screen would be the untested one."""
    js = _js()
    i = js.index("function lens1View")
    assert "pct: d" in js[i:js.index("function lens2Call")]
    j = js.index("function lens2View")
    assert "pct: Number(p)" in js[j:js.index("const lensSplit")]
    # And the no-reading paths return a NULL position, not 0.
    assert "held: false, pct: null" in js
    assert "dir: 0, pct: null" in js


def test_THE_FINE_PRINT_IS_BEHIND_A_DETAILS_TOGGLE():
    """Nick's third tweak: bigger labels, fine print moved into toggles."""
    js = _js()
    i = js.index("function rbCell")
    body = js[i:js.index("\n  }", i)]
    assert 'class="rb-det"' in body
    assert 'class="rb-fine" hidden' in body
    assert 'aria-expanded="false"' in body
    # The toggle must not also open the drawer.
    k = js.index("band.querySelectorAll('.rb-det')")
    assert "stopPropagation" in js[k:k + 400]
    assert "e.target.closest('.rb-det')" in js, "the drawer handler ignores the toggle"


# ── the themes chips removed, with the drawer route preserved ──────────────

def test_THE_THEMES_CHIP_LIST_IS_GONE_FROM_THE_REGIME_TILE():
    """R-IV.1209(c) A2."""
    js = _js()
    i = js.index("band.innerHTML")
    body = js[i:i + 2000]
    assert "th-chips" not in body
    assert "rc-themes" not in body
    assert "themeChipsAll" not in body


def test_THE_DEAD_CHIP_FITTER_IS_DELETED_NOT_LEFT_RETURNING_EARLY():
    """Its only DOM target was `#regimeBand .th-chips`, which this change removed -- so it could
    only ever return early, and a function that silently does nothing reads to the next author
    as a thing that works. Its resize listeners went with it."""
    js = _js()
    assert "function fitThemeChips" not in js
    assert "addEventListener('resize', fitThemeChips)" not in js
    assert "setTimeout(fitThemeChips" not in js


def test_themeChipsAll_SURVIVES_because_the_DRAWER_still_uses_it():
    js = _js()
    assert "function themeChipsAll" in js


def test_THE_THEMES_DRAWER_IS_STILL_REACHABLE():
    """THE CAPABILITY THE RULING DID NOT ASK ME TO DELETE. `data-drawer="themes"` existed ONLY
    on the cell A2 removes, and the Themes TILE had no drawer route -- so removing the chip list
    would have made the themes drawer unreachable. The route moved to the Themes tile."""
    html = _html()
    assert 'id="themesDrawerBtn"' in html
    i = html.index('gs-id="themes"')
    j = html.index("</div>", html.index('id="themesTable"'))
    assert 'id="themesDrawerBtn"' in html[i:j], "the button belongs to the Themes tile"
    js = _js()
    assert "openDrawer('themes'" in js
    k = js.index("themesDrawerBtn")
    assert "addEventListener" in js[k:k + 200], "bound in JS, not inline in the markup"


# ── the yield curve moved into the bar ─────────────────────────────────────

def test_THE_CURVE_TILE_IS_GONE_FROM_THE_GRID():
    assert 'gs-id="curve"' not in _html()


def test_THE_CURVE_IDS_ARE_UNCHANGED_SO_loadRates_IS_UNTOUCHED():
    """The R-IV.1210(b) census found `curveChart` and `curveVals` had exactly two readers --
    loadRates' $('curveVals') and makeLineChart('curveChart'). Renaming them would have broken
    a live read for no reason, so the markup moved and the ids did not."""
    js = _js()
    i = js.index("band.innerHTML")
    body = js[i:i + 2500]
    assert 'id="curveChart"' in body
    assert 'id="curveVals"' in body
    assert "$('curveVals')" in js
    assert "makeLineChart('curveChart'" in js


def test_the_curve_in_the_bar_is_FULLY_LIVE_SINCE_B3():
    """B3 arrived (R-IV.1220(b)), so the PART MOCK chip is GONE rather than left to lie.

    This test asserted `"PART MOCK" in body` while the shape word, the z-scores and the
    spreads were still missing -- which was right then and is wrong now. A panel still wearing
    a mock chip after its data went live trains the reader to ignore the chip, which costs more
    than the chip was ever worth.

    What replaces it is the thing the chip was standing in for: the tile must carry the three
    B3 elements and must NOT claim to be a mock.
    """
    js = _js()
    i = js.index("rb-curve")
    body = js[i:i + 700]
    assert "PART MOCK" not in body
    assert "ycShape" in body, "the shape word's element"
    assert "ycHeads" in body, "the 3m10s / 2s10s headline numbers"
    assert "ycFlag" in body, "the UN-INVERTED flag"


# ── the left DETAILS drawer ─────────────────────────────────────────────────

def test_THE_STRATEGY_BUTTON_SAYS_DETAILS_AND_POINTS_LEFT():
    html = _html()
    m = re.search(r'id="rsOpen"[^>]*>(.*?)</button>', html, re.S)
    assert m, "rsOpen not found"
    assert "DETAILS" in m.group(1)
    assert "&#9666;" in m.group(1), "the left-pointing marker"
    assert "Open" not in m.group(1)


def test_THE_DRAWER_IS_FORCED_TO_THE_LEFT():
    """R-IV.1209(c) A2 says left. `popSide` would otherwise pick, and the Strategy card is full
    width -- exactly the case where popSide falls back to whatever was clicked."""
    js = _js()
    i = js.index("function openRegimeDetails")
    body = js[i:js.index("\n  }", i)]
    assert "setSide(d, 'left')" in body
    assert "popSide" not in body
    css = _css()
    assert ".drawer.from-left" in css, "the left mode must exist"


#: The drawer sections B8 has wired. Section 7, the ribbon, came first because it needed
#: no new source (R-IV.1239(h)).
WIRED_DRAWER_SECTIONS = {"7"}


def test_EVERY_UNWIRED_DRAWER_SECTION_STILL_SAYS_IT_IS_MOCK():
    """A placeholder that looks like a finished section is the A1 chip problem one level up."""
    js = _js()
    i = js.index("function openRegimeDetails")
    body = js[i:js.index("\n  }", i)]
    # B8 wires the eight sections ONE AT A TIME (R-IV.1239(h)), so the count is 8 minus the
    # wired set. This asserted `>= 8` while all eight were placeholders; as a set, the
    # assertion TIGHTENS as sections land instead of having to be deleted eight times. A wired
    # section still calling itself a mock is the same fault inverted, so that is checked too.
    assert body.count("mock(") == 8 - len(WIRED_DRAWER_SECTIONS), body.count("mock(")
    assert "rd-mock" in js
    # The footer COUNTS rather than asserting, so it cannot go stale as sections are wired.
    assert "WIRED: 7 (ribbon)" in body
    assert "STILL PLACEHOLDERS: 1-6, 8" in body
    for n in sorted(WIRED_DRAWER_SECTIONS):
        start = body.index("'%s', " % n)
        nxt = body.find("+ sec(", start)
        assert "mock(" not in body[start:nxt if nxt > 0 else len(body)], (
            "section %s is wired and must not claim to be a mock" % n)


def test_THE_DRAWER_HEADER_IS_LIVE_NOT_MOCK():
    """The label, close and source come from the card's own stored payload. Marking that MOCK
    would be the opposite error -- a true reading disclaimed."""
    js = _js()
    i = js.index("function openRegimeDetails")
    body = js[i:js.index("\n  }", i)]
    assert "m.regime_label" in body
    assert "m.close_source" in body
    assert "display only" in body


def test_the_drawer_reads_the_SAME_payload_the_card_does():
    """Two derivations of one label would eventually disagree, and the one on screen would be
    the untested one."""
    js = _js()
    i = js.index("function openRegimeDetails")
    body = js[i:js.index("\n  }", i)]
    # `_rsLive`, renamed from `_rsMock` in B1: it has held the LIVE regime-strategy
    # payload since R-IV.1203, and a variable called Mock holding live data is the
    # caption-lies-about-its-field fault.
    assert "_rsLive" in body
    # And the band's fifth read comes from the same place.
    k = js.index("const stratWord")
    assert "_rsLive" in js[k:k + 200]


# ── housekeeping ───────────────────────────────────────────────────────────

def test_THE_A2_CSS_IS_TOKENS_AND_PHONE_FIRST():
    css = _css()
    block = css[css.index("PHASE A2"):]
    hexes = set(re.findall(r"#[0-9a-fA-F]{3,8}", block))
    assert hexes == set(), hexes
    assert "@media (min-width: 769px)" in block
    assert not re.search(r"@media[^{]*max-width", block)


def test_THE_PINS_MOVED_FOR_A2():
    pins = {}
    for page in ("v2.html", "stater.html", "abacus.html"):
        m = re.search(r"/v2\.css\?v=(\d+)", read_source(os.path.join(FRONTEND, page)))
        assert m, page
        pins[page] = int(m.group(1))
    assert pins["v2.html"] >= 54, pins
    assert pins["stater.html"] >= 50, pins
    assert pins["abacus.html"] >= 49, pins
    jm = re.search(r"/v2\.js\?v=(\d+)", read_source(os.path.join(FRONTEND, "v2.html")))
    assert jm and int(jm.group(1)) >= 68


def test_the_regime_band_tile_GREW_to_hold_the_grid_and_the_curve():
    """A 2x2 grid plus the curve does not fit in three rows, and a tile that clips its own
    content is a tile nobody trusts."""
    m = re.search(r'gs-id="regime-band"[^>]*gs-h="(\d+)"[^>]*gs-min-h="(\d+)"', _html())
    assert m, "regime-band attrs not found"
    assert int(m.group(1)) >= 6, m.group(1)
    assert int(m.group(2)) >= 5, m.group(2)
