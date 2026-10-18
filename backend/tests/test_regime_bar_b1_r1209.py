"""R-IV.1209(e) B1 — regime bar v2 LIVE: real thresholds on the gauges, and the CSS sweep.

WHAT B1 ACTUALLY HAD LEFT TO DO. A2 already wired the lean/outline engine to live reads --
`loadRegimeBand` makes four real API calls (/api/bias/composite, /api/stable/regime,
/api/board/tide, /api/board/kill-switch) and the fifth read comes from the live
regime-strategy payload. So "(d) driven by the real reads" was already true, and what was
missing was the other half: "gauges from the real thresholds". A2 drew a marker on a bare
track -- a position against nothing.

THE FAULT B1 FIXED ALONG THE WAY. The vol-curve WORDS came from 0.90 / 1.00 while the gauge's
ticks were hard-coded 33.33% / 66.67% in the markup: two numbers for one threshold, which drift
apart the moment either is tuned. One mapping now, and the ticks are that mapping applied to
the band edges -- verified to reproduce 33.33 / 66.67 exactly, so the change is provably
behaviour-preserving today and correct tomorrow.

AND THE BREADTH TICKS COME FROM THE PAYLOAD, not from constants. The backend owns 60/40 and can
move them. A tick drawn at a number the backend no longer uses is worse than no tick: it is a
scale that lies.
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


def _js_code() -> str:
    """v2.js with comments removed.

    FULL-LINE `//` ONLY. v2.js carries URLs with "://" on code lines, so stripping from a
    mid-line `//` would cut a URL in half -- which is why the A3 helper's blanket "://"
    assertion does not transfer here. Block comments go wholesale.
    """
    js = re.sub(r"/\*.*?\*/", "", _js(), flags=re.S)
    kept = [ln for ln in js.splitlines() if not ln.lstrip().startswith("//")]
    return "\n".join(kept)


def _css():
    return read_source(os.path.join(FRONTEND, "v2.css"))


def _html():
    return read_source(os.path.join(FRONTEND, "v2.html"))


# ── the reads were already live; B1 proves it rather than assuming ─────────

def test_ALL_FIVE_READS_ARE_LIVE():
    """(d)1 counts five reads. Four come from real API calls in `loadRegimeBand`; the fifth is
    the regime-strategy payload, which has been live since R-IV.1203."""
    js = _js()
    i = js.index("async function loadRegimeBand")
    body = js[i:i + 1400]
    for route in ("/api/bias/composite", "/api/stable/regime", "/api/board/tide",
                  "/api/board/kill-switch"):
        assert route in body, route
    k = js.index("const stratWord")
    assert "_rsLive" in js[k:k + 200], "the fifth read comes from the live payload"


def test_THE_LIVE_PAYLOAD_IS_NOT_CALLED_MOCK_ANY_MORE():
    """It has held the LIVE regime-strategy payload since R-IV.1203, and a variable called
    `_rsMock` holding live data is the caption-lies-about-its-field fault somewhere a reader
    trusts without checking. Renamed in B1, the pass that touches this surface."""
    js = _js()
    assert "let _rsLive = null" in js
    # The only surviving mention of the old name is the comment recording the rename.
    assert js.count("_rsMock") == 1
    i = js.index("_rsMock")
    assert "renamed" in js[max(0, i - 250):i + 250]


# ── the gauges carry the real thresholds ──────────────────────────────────

def test_THE_MARKET_MIX_TICKS_ARE_THE_REAL_DIAL_CUTS():
    """LENS1_CUTS is the same array `lens1View` uses for the distance-to-flip, so the ticks and
    the words cannot disagree."""
    js = _js()
    assert "const LENS1_CUTS = [20, 40, 60, 80];" in js
    i = js.index("rbCell('mix'")
    assert "LENS1_CUTS)" in js[i:i + 400]


def test_THE_BREADTH_TICKS_COME_FROM_THE_PAYLOAD():
    """"Gauges from the real thresholds." The backend owns 60/40 via
    risk_on_pct_above_50dma / risk_off_pct_above_50dma and can move them."""
    js = _js()
    assert "function lens2Ticks" in js
    i = js.index("function lens2Ticks")
    body = js[i:js.index("\n  }", i)]
    assert "risk_on_pct_above_50dma" in body
    assert "risk_off_pct_above_50dma" in body
    assert "30" in body and "70" in body, "the STRONG tier edges"
    k = js.index("rbCell('breadth'")
    assert "lens2Ticks(r.thresholds)" in js[k:k + 400], "fed from the payload, not a constant"


@pytest.mark.skipif(not NODE, reason="node is not on this machine")
def test_the_breadth_ticks_FOLLOW_the_payload_and_fall_back_honestly():
    """A payload that moves the cut-offs moves the ticks; a payload without them falls back to
    the backend's documented defaults rather than to nothing."""
    js = _js()
    i = js.index("function lens2Ticks")
    fn = js[i:js.index("\n  }", i) + 4]
    prog = (fn + "\nconsole.log(JSON.stringify({"
            "def: lens2Ticks(null),"
            "moved: lens2Ticks({risk_on_pct_above_50dma: 65, risk_off_pct_above_50dma: 35})"
            "}));")
    r = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-1500:]
    got = json.loads(r.stdout.strip().splitlines()[-1])
    assert got["def"] == [30, 40, 60, 70]
    assert got["moved"] == [30, 35, 65, 70]


def test_THE_VOL_BANDS_HAVE_ONE_SOURCE():
    """THE FAULT B1 FIXED. The words came from 0.90 / 1.00 and the ticks were hard-coded
    33.33% / 66.67% in the markup -- two numbers for one threshold."""
    js = _js()
    assert "const VOL_FIRMING_AT = 0.90, VOL_STRESS_AT = 1.00;" in js
    assert "const VOL_TICKS = [volPct(VOL_FIRMING_AT), volPct(VOL_STRESS_AT)];" in js
    i = js.index("const word = shown >= VOL_STRESS_AT")
    assert "VOL_FIRMING_AT" in js[i:i + 160]
    assert "pct: volPct(ratio)" in js
    k = js.index("rbCell('vol'")
    assert "VOL_TICKS)" in js[k:k + 400]
    # No hard-coded gauge ticks left in the CODE. Checked on comment-stripped source: the
    # comment recording this very fix names both numbers, and a raw scan reports the
    # explanation as the offence.
    code = _js_code()
    assert "33.33" not in code and "66.67" not in code


@pytest.mark.skipif(not NODE, reason="node is not on this machine")
def test_THE_DERIVED_TICKS_REPRODUCE_THE_OLD_HARD_CODED_ONES():
    """The change is provably behaviour-preserving TODAY -- the derived positions are the same
    numbers the markup used to carry -- and correct tomorrow, when a band moves."""
    js = _js()
    i = js.index("const VOL_FIRMING_AT")
    block = js[i:js.index("function volCurveView", i)]
    prog = block + "\nconsole.log(JSON.stringify(VOL_TICKS.map(t => Math.round(t * 100) / 100)));"
    r = subprocess.run([NODE, "-e", prog], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr[-1500:]
    assert json.loads(r.stdout.strip().splitlines()[-1]) == [33.33, 66.67]


def test_THE_TIDE_READ_STILL_GETS_NO_GAUGE():
    """Its thresholds are premium dollars, not a 0-100 position, so there is no honest scale to
    draw. An empty track is right; a marker would be a reading."""
    js = _js()
    i = js.index("rbCell('tide'")
    assert "null, null)" in js[i:i + 300], "pct and ticks both null"


def test_a_cell_with_no_position_renders_NO_TICKS_EITHER():
    """Ticks on an empty track would be a scale with nothing on it, which invites a reader to
    look for a marker they cannot see."""
    js = _js()
    i = js.index("function rbCell")
    body = js[i:js.index("\n  }", i)]
    assert "pct != null" in body
    j = body.index("pct != null")
    assert "ticks || []" in body[j:], "the ticks are inside the has-a-position branch"
    assert "rb-g-none" in body


def test_the_ticks_are_CLAMPED():
    """A threshold outside 0-100 -- a payload with a bad cut-off -- must not paint outside the
    track."""
    js = _js()
    i = js.index("function rbCell")
    body = js[i:js.index("\n  }", i)]
    j = body.index("ticks || []")
    assert "Math.max(0, Math.min(100," in body[j:j + 260]


# ── the CSS sweep (R-IV.1211(b)) ──────────────────────────────────────────

@pytest.mark.parametrize("sel", [
    "rc-regime", "rc-themes", "rc-tide", "rc-vol",
    "lens-lab", "lens-line", "lens-call", "lens-num", "lens-dist",
    "th-chips", "th-more", "tide-lean", "tide-long",
])
def test_THE_DEAD_SELECTOR_IS_GONE(sel):
    """R-IV.1211(b), carried into B1. Checked against the RULES, not the raw file: the sweep's
    own note names several of these in prose, and a raw search would report the note as a
    finding -- the comment fault in CSS form."""
    css = re.sub(r"/\*.*?\*/", "", _css(), flags=re.S)
    assert "." + sel not in css, sel


@pytest.mark.parametrize("sel", [
    ".regime-cell {", ".chip {", ".chip.dom", ".chip.emg", ".chip.fad",
    ".split-chip", ".vc-gauge", ".val-up", ".val-down",
])
def test_THE_LIVE_SELECTOR_SURVIVED(sel):
    """The sweep's real risk was taking something still in use. `.chip.dom` looks like band CSS
    and is still rendered by the themes DRAWER; `.val-*` is used across the dashboard."""
    assert sel in _css(), sel


def test_the_loading_placeholder_still_has_its_rules():
    """It is the one surviving user of `.regime-cell`, and it renders before the first paint --
    so if its rules went, the first thing anyone sees would be unstyled."""
    html = _html()
    assert 'class="regime-cell placeholder"' in html
    css = _css()
    assert ".regime-cell {" in css
    assert ".placeholder" in css


def test_the_sweep_NOTE_describes_what_actually_happened():
    """The note that stood here described the rules as "left in place", which stopped being true
    the moment they were removed. A note describing the old plan is worse than none."""
    css = _css()
    assert "left in place" not in css
    i = css.index("was REMOVED here in B1")
    note = css[i:i + 800]
    assert "census" in note
    assert "PROSE IN COMMENTS" in note
    assert "Kept:" in note


def test_the_old_four_column_grid_is_gone():
    css = re.sub(r"/\*.*?\*/", "", _css(), flags=re.S)
    i = css.index(".regime-band {")
    rule = css[i:css.index("}", i)]
    assert "grid-template-columns" not in rule
    assert "display: flex" in rule, "A2's rule is what remains"


def test_THE_PINS_MOVED_FOR_B1():
    pins = {}
    for page in ("v2.html", "stater.html", "abacus.html"):
        m = re.search(r"/v2\.css\?v=(\d+)", read_source(os.path.join(FRONTEND, page)))
        assert m, page
        pins[page] = int(m.group(1))
    assert pins["v2.html"] >= 56, pins
    assert pins["stater.html"] >= 52, pins
    assert pins["abacus.html"] >= 51, pins
    jm = re.search(r"/v2\.js\?v=(\d+)", read_source(os.path.join(FRONTEND, "v2.html")))
    assert jm and int(jm.group(1)) >= 70
