"""R-IV.1209(c) A1 — the four Agora boards as MOCK tiles.

THE GATE CAME FIRST. All ten handoff files were verified against the sha256s in R-IV.1209(b)
before anything was built, on two independent hashers (Python hashlib and PowerShell
Get-FileHash). The four board hashes are pinned here so a mockup swapped under the build would
show up as a test failure rather than as a silently different tile.

WHAT MATTERS MOST IN PHASE A: THE MOCK CHIP, AND THAT IT CANNOT OUTLIVE ITS TRUTH. Every value
in these fixtures is fake (R-IV.1209(b)). A tile that looks like the rest of the dashboard and
is full of invented numbers is the most dangerous thing this lane can ship, so the chip is
driven by the FIXTURE'S OWN `_mock` flag -- when Phase B replaces a fixture with a live read,
the flag goes and the chip goes with it. A chip that had to be removed by hand is a chip that
gets left behind on live data, or removed early from fake data. Both are worse than no chip.

DISPLAY ONLY (#42). Nothing here gates, grades or feeds Kairos, and that is asserted rather
than assumed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re

import pytest

from ._srcscan import read_source

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND)
FRONTEND = os.path.join(ROOT, "frontend")
ASSETS = os.path.join(FRONTEND, "assets", "agora")
HANDOFF = r"C:\temp\cc-query-handoff"

#: R-IV.1209(b) / R-IV.1194(b). Boards 1-4, the ones A1 is built from.
BOARD_SHA = {
    "AGORA-MOCK-CrowdGauge.dc.html":
        "1c931cf87504afa7b8efca3266c33e3201bb92a89e3c9b4ad7c60269105cb6d7",
    "AGORA-MOCK-FearPrice.dc.html":
        "2c0d8962ac20a0c775db15132dc3e54f2a446e5f79536da505d420aface7eeae",
    "AGORA-MOCK-BookStress.dc.html":
        "8e06d963a98f3741b1715108014f354a4e1fbb6bde81902590f686892f0d16eb",
    "AGORA-MOCK-EventStrip.dc.html":
        "5480bb3689464c8a7e9b66e2ffd6837bfd31f5391d99077735a4ebb75863ccfe",
}

FIXTURES = {
    "crowd": "crowd_mock.json",
    "fear": "fear_mock.json",
    "bookStress": "book_stress_mock.json",
    "eventStrip": "event_strip_mock.json",
}


def _fx(name):
    return json.load(io.open(os.path.join(ASSETS, name), encoding="utf-8"))


def _js():
    return read_source(os.path.join(FRONTEND, "v2.js"))


def _html():
    return read_source(os.path.join(FRONTEND, "v2.html"))


def _css():
    return read_source(os.path.join(FRONTEND, "v2.css"))


# ── the gate ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,want", sorted(BOARD_SHA.items()))
def test_THE_BOARD_HASHES_STILL_MATCH(name, want):
    """R-IV.1209(b). Skipped rather than failed when the handoff folder is not on this machine:
    the hash is evidence about a file, and a missing file is not a mismatch."""
    p = os.path.join(HANDOFF, name)
    if not os.path.exists(p):
        pytest.skip("handoff file not present on this machine")
    h = hashlib.sha256()
    with io.open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    assert h.hexdigest() == want


def test_each_fixture_CITES_the_board_it_came_from():
    """So a reader of the fixture can get back to the mockup, and a fixture built from a
    different board shows up as a wrong hash rather than as a judgement call."""
    for key, fname in FIXTURES.items():
        src = _fx(fname).get("_source") or ""
        assert "AGORA-MOCK-" in src, key
        m = re.search(r"sha256 ([0-9a-f]{64})", src)
        assert m, "%s: no full hash in _source" % key
        assert m.group(1) in BOARD_SHA.values(), key


# ── the MOCK chip ───────────────────────────────────────────────────────────

def test_EVERY_FIXTURE_IS_FLAGGED_MOCK():
    """R-IV.1209(b): every value in them is fake. The flag is what the chip reads."""
    for key, fname in FIXTURES.items():
        fx = _fx(fname)
        assert fx.get("_mock") is True, key
        assert "fake" in (fx.get("_note") or "").lower(), key


def test_THE_CHIP_IS_DRIVEN_BY_THE_FIXTURE_NOT_HARD_CODED():
    """THE PROPERTY THAT MATTERS MOST. When Phase B replaces a fixture with a live read, the
    `_mock` flag goes and the chip goes with it. A chip removed by hand is a chip that gets left
    behind on live data, or taken off fake data early."""
    js = _js()
    i = js.index("function setMockChip")
    body = js[i:i + 500]
    assert "fixture && fixture._mock" in body
    assert "el.hidden = !isMock" in body
    # And the markup ships it HIDDEN, so a fixture that fails to load cannot leave a chip
    # asserting mockness about a tile with nothing in it.
    html = _html()
    for chip in ("crowdMock", "fearMock", "evMock"):
        m = re.search(r'id="%s"[^>]*>' % chip, html)
        assert m, chip
        assert "hidden" in m.group(0), chip


def test_every_mock_tile_shows_a_chip():
    """Three tile headers plus the BOOK section, which renders its own chip because it has no
    header of its own to hang one in."""
    html = _html()
    for chip in ("crowdMock", "fearMock", "evMock"):
        assert 'id="%s"' % chip in html, chip
    js = _js()
    i = js.index("function renderBookStress")
    assert 'class="mock-chip"' in js[i:i + 4000], "the BOOK section renders its own chip"


def test_the_chip_has_a_CSS_RULE_and_is_LOUD():
    """Amber on dark, bold. A quiet chip on a confident-looking tile is worse than no chip:
    every value behind it is invented."""
    css = _css()
    assert ".mock-chip {" in css
    rule = css[css.index(".mock-chip {"):]
    rule = rule[:rule.index("}")]
    assert "var(--amber)" in rule
    assert "font-weight: 700" in rule


def test_the_chip_TITLE_says_the_values_are_fake():
    """The chip is four letters. The tooltip is where a reader learns what it means."""
    js = _js()
    i = js.index("function setMockChip")
    assert "Every value on this tile is fake" in js[i:i + 600]


# ── display only (#42) ──────────────────────────────────────────────────────

#: The A1 tiles that have gone live, and the ONE route each is allowed to read. B4 moved the
#: Event Strip; B5/B6/B7 will move Fear Price, Crowd and Book Reality. Listed rather than
#: open-ended, so a tile that starts reading a route it was not given still fails.
LIVE_TILES = {"/api/event-strip", "/api/fear-price"}


def test_EACH_TILE_READS_ONLY_ITS_OWN_ROUTE_OR_ITS_FIXTURE():
    """R-IV.1209(c)'s "no hub route in Phase A" has EXPIRED BY SCHEDULE for one tile, not been
    relaxed: B4 (R-IV.1237(c)) made the Event Strip live.

    So the ban becomes a whitelist. The tiles still on fixtures must still read fixtures, the
    tiles that have gone live may read exactly the route they were given, and nothing may read
    anything else. The old assertion would have had to be deleted outright at B5, B6 and B7 as
    well; this one survives each move and keeps failing for the right reason.
    """
    js = _js()
    i = js.index("const AGORA_FIXTURES")
    j = js.index("function initGrid")
    body = js[i:j]
    assert "/assets/agora/" in body, "the tiles still on fixtures must still read them"
    routes = set(re.findall(r"'(/api/[^']+)'", body))
    assert routes == LIVE_TILES, routes


def test_NOTHING_GATES_ON_THESE_TILES():
    """#42, and R-IV.1209(a) says it outright: nothing gates, grades or feeds Kairos."""
    js = _js()
    i = js.index("const AGORA_FIXTURES")
    j = js.index("function initGrid")
    body = js[i:j]
    for banned in ("method: 'POST'", 'method: "POST"', "XMLHttpRequest",
                   "kairos", "Kairos", "addRiverItems", "emitRegime"):
        assert banned not in body, banned


def test_the_fixtures_are_under_assets_so_they_are_SERVED():
    """backend/main.py serves `frontend/assets/` wholesale and routes every other file by name.
    A fixture outside that folder is a 404 at runtime and an empty tile on the dashboard."""
    for fname in FIXTURES.values():
        p = os.path.join(ASSETS, fname)
        assert os.path.exists(p), fname
        rel = os.path.relpath(p, FRONTEND).replace(os.sep, "/")
        assert rel.startswith("assets/"), rel
    js = _js()
    # A tile that has gone live no longer references its fixture, and that is correct: B4's
    # loader must NOT fall back to the mock, because a fixture served where live data belongs
    # looks exactly like the real thing. The file stays on disk as the layout reference, which
    # is what the existence check above is for.
    live_fixtures = {"event_strip_mock.json", "fear_mock.json"}
    for fname in FIXTURES.values():
        if fname in live_fixtures:
            assert "/assets/agora/" + fname not in js, (
                "%s is live now, so the panel must not read its fixture" % fname)
            continue
        assert "/assets/agora/" + fname in js, fname


# ── the tiles exist, are placed, and are ordered on a phone ────────────────

@pytest.mark.parametrize("gs_id", ["crowd", "fear", "event-strip"])
def test_the_tile_is_in_the_grid(gs_id):
    assert 'gs-id="%s"' % gs_id in _html()


def test_the_event_strip_is_FULL_WIDTH():
    """R-IV.1194(c): "Event Strip is a full-width strip." """
    html = _html()
    m = re.search(r'gs-id="event-strip"[^>]*gs-w="(\d+)"', html)
    assert m and m.group(1) == "12", m.group(1) if m else None


def test_book_reality_is_a_SECTION_INSIDE_BOOK_not_its_own_tile():
    """R-IV.1194(c): "Book Reality is a section inside BOOK." """
    html = _html()
    assert 'gs-id="book-stress"' not in html, "it must not be its own tile"
    i = html.index('gs-id="book"')
    j = html.index('gs-id="crowd"')
    assert 'id="bookStress"' in html[i:j], "the section lives inside the BOOK tile"


def test_THE_NEW_TILES_ARE_IN_MOBILE_ORDER():
    """An unlisted tile sorts AFTER the known set, so leaving these out would bury four new
    boards below every legacy tile on a phone -- the same trap `regime-strategy` was in."""
    js = _js()
    i = js.index("const MOBILE_ORDER")
    block = js[i:js.index("]", i)]
    for t in ("event-strip", "fear", "crowd"):
        assert "'%s'" % t in block, t


# ── the fixtures carry what the boards showed ──────────────────────────────

def test_the_crowd_headline_rule_is_the_ruled_one():
    """R-IV.1194(f): BEARS/BULLS CROWDED only when 2 or more rows sit at an extreme on the same
    side. The fixture must not show a headline its own rows do not support."""
    fx = _fx("crowd_mock.json")
    extremes = [r for r in fx["rows"] if r.get("extreme")]
    assert len(extremes) >= 2, "the headline claims an extreme pair; the rows must show one"
    assert fx["headline"] in ("BEARS CROWDED", "BULLS CROWDED", "NEUTRAL")
    assert "2 of 3" in fx["headline_basis"]
    # No contrarian arrow and no composite score: the committee ruled both out.
    assert "composite" not in json.dumps(fx).lower()
    assert "arrow" not in json.dumps(fx).lower()


def test_a_THIN_HISTORY_row_is_starred_and_amber():
    """R-IV.1194(f): short history shows amber "n / N" with the percentile starred. Amber is
    "cannot confirm", which is exactly what a percentile over nine weeks is."""
    fx = _fx("crowd_mock.json")
    thin = [r for r in fx["rows"] if r.get("thin")]
    assert thin, "the board showed a thin AAII row"
    assert thin[0]["pct_label"].endswith("*")
    assert any("9 / 52" in f for f in fx["footnotes"])
    css = _css()
    assert ".ag-g b.ag-thin { background: var(--amber); }" in css
    assert ".ag-rp.ag-thin { color: var(--amber); }" in css


def test_the_fear_tile_can_say_CANNOT_CONFIRM_and_can_PREFIX_approx():
    """R-IV.1194(e): a symbol that will not return data shows amber "cannot confirm", and a
    VIX-implied expected move is shown with a "≈" prefix. Both paths must exist before B wires
    them, or B arrives needing a renderer change nobody budgeted."""
    js = _js()
    i = js.index("function renderFearPrice")
    # TO THE END OF THE FUNCTION, not a fixed 3000 characters. The slice was a LENGTH, and
    # B5's null-safe curve bars pushed `approx` past it -- so the guard failed while the thing
    # it guards was still there, three lines further down. Fourth scope-by-distance guard found
    # in this session; this file's own comment at line 427 records the same fault.
    body = js[i:js.index("function renderBookStress", i)]
    assert "approx" in body
    assert "\\u2248" in body, "the approx prefix"
    fx = _fx("fear_mock.json")
    assert "approx" in (fx.get("expected_move") or {})


def test_the_book_grid_is_the_ruled_shape():
    """R-IV.1194(g): rows RH / ROTH / 401A / TOTAL; columns SPY -10, -5, -3, +3, +5."""
    fx = _fx("book_stress_mock.json")
    assert [r["key"] for r in fx["rows"]] == ["RH", "ROTH", "401A", "TOTAL"]
    assert len(fx["columns"]) == 5
    for r in fx["rows"]:
        assert len(r["cells"]) == 5, r["key"]
    assert fx["rows"][-1]["total"] is True


def test_the_book_section_calls_itself_a_MODELED_ESTIMATE():
    """R-IV.1194(g): "Label: modeled estimate"."""
    fx = _fx("book_stress_mock.json")
    assert "modeled estimate" in fx["caption"]


def test_unmodellable_holdings_are_LISTED_not_dropped():
    """R-IV.1194(g): crypto and anything unmodellable are listed as "not modelled", never
    silently dropped. A dropped row makes the worst cell look better than it is."""
    fx = _fx("book_stress_mock.json")
    assert fx["not_modelled"], "the board showed crypto as unmodellable"
    js = _js()
    i = js.index("function renderBookStress")
    assert "not modelled:" in js[i:i + 4500]
    assert ".bs-nm" in _css()


def test_the_worst_cell_is_called_out_with_its_sleeve_percent():
    """R-IV.1194(g): worst cell as $ AND as % of that sleeve's total value."""
    fx = _fx("book_stress_mock.json")
    w = fx["worst"]
    assert w["value"].startswith("\u2212$")
    assert "of sleeve" in w["pct_of_sleeve"]
    assert w["where"]


def test_the_event_strip_covers_TEN_sessions_and_flags_opex_outside_the_window():
    """R-IV.1194(d): the next 10 sessions; "next OpEx · Nd" when it falls outside."""
    fx = _fx("event_strip_mock.json")
    assert len(fx["days"]) == 10
    assert "NEXT OPEX" in fx["next_opex"]
    assert re.search(r"\d+d", fx["next_opex"]), "the days-away figure"


def test_the_blackout_is_shaded_AND_labelled_est():
    """R-IV.1194(d): shaded and labelled "est." A shade with no label is a claim the reader has
    to guess at."""
    fx = _fx("event_strip_mock.json")
    assert "est." in fx["blackout_label"]
    assert any(d.get("blackout") for d in fx["days"])
    css = _css()
    assert ".ev-day.ev-blackout" in css


def test_book_earnings_are_HIGHLIGHTED_against_the_watchlist_count():
    """R-IV.1194(d): a count per day for book plus watchlist, with book names highlighted."""
    fx = _fx("event_strip_mock.json")
    assert any((d.get("book_earn") or 0) > 0 for d in fx["days"])
    js = _js()
    i = js.index("function renderEventStrip")
    body = js[i:i + 2600]
    assert "yours" in body
    assert "var(--teal)" in body, "book names get the teal, the rest the border colour"


# ── the colour scale, and reduced motion ───────────────────────────────────

def test_THE_LEAN_SCALE_IS_THE_RULED_ONE():
    """R-IV.1209(d)2. Five steps plus teal, expressed as tokens and color-mix so a palette
    change carries, and the percentages are the ruled ones (60% bear, 55% bull)."""
    js = _js()
    i = js.index("const LEAN_COLOR")
    block = js[i:js.index("};", i)]
    assert "'strong-bear': 'var(--down)'" in block
    assert "var(--down) 60%" in block
    assert "'neutral': 'var(--text-2)'" in block
    assert "var(--up) 55%" in block
    assert "'strong-bull': 'var(--up)'" in block
    assert "'notable': 'var(--teal)'" in block
    assert "--amber" not in block, "amber is reserved for cannot-confirm (R-IV.1209(d)2)"


def test_PREFERS_REDUCED_MOTION_stops_the_animations():
    """R-IV.1209(d)7."""
    css = _css()
    i = css.rindex("@media (prefers-reduced-motion: reduce)")
    block = css[i:i + 300]
    assert "animation: none !important" in block


def test_the_new_css_uses_TOKENS_not_hexes():
    """R-IV.1190(b). The two exceptions are the page background colour used as a FOREGROUND on
    the amber chip and the top-tier event chip, where the token would be the wrong end."""
    css = _css()
    i = css.index("AGORA ADDITIONS, PHASE A1")
    block = css[i:]
    hexes = set(re.findall(r"#[0-9a-fA-F]{3,8}", block))
    assert hexes <= {"#050810"}, hexes
    assert "var(--" in block


# ── the cache pins moved ───────────────────────────────────────────────────

def test_THE_PINS_MOVED_FOR_EVERY_PAGE_THAT_PINS_A_CHANGED_ASSET():
    """v2.js, v2.css and v2.html all changed. v2.css is pinned by THREE pages at independent
    values, and the pages missed keep serving whatever was cached under their unchanged pin."""
    pins = {}
    for page in ("v2.html", "stater.html", "abacus.html"):
        src = read_source(os.path.join(FRONTEND, page))
        m = re.search(r"/v2\.css\?v=(\d+)", src)
        assert m, page
        pins[page] = int(m.group(1))
    assert pins["v2.html"] >= 53, pins
    assert pins["stater.html"] >= 49, pins
    assert pins["abacus.html"] >= 48, pins
    jm = re.search(r"/v2\.js\?v=(\d+)", read_source(os.path.join(FRONTEND, "v2.html")))
    assert jm and int(jm.group(1)) >= 67, jm.group(1) if jm else None


def test_THE_CARDS_CSS_GUARDS_ARE_BOUNDED_TO_THE_CARD():
    """The regime card's CSS slice ran to the END of the file, so any block appended to v2.css
    later became "the card's CSS" to its own guards -- this A1 block landed inside them and
    failed the card's hex and phone-first checks while the card itself was untouched.

    A guard whose scope grows with the file reports findings about code it was never about.
    Both slices are bounded now, and this asserts it so the next append does not re-learn it."""
    for f in ("test_regime_card_v01_r1190.py", "test_regime_strategy_v0_r1186.py"):
        src = read_source(os.path.join(BACKEND, "tests", f))
        assert 'css.find("AGORA ADDITIONS, PHASE A1", k)' in src, f
        assert "css[css.rindex(\"/*\", 0, k):]" not in src, f


def test_THE_A1_BLOCK_IS_PHONE_FIRST():
    """The repo's convention, and the card's guards enforce it: base rules are the phone's and
    the media query WIDENS. A max-width query makes the desktop rules the base."""
    css = _css()
    block = css[css.index("AGORA ADDITIONS, PHASE A1"):]
    assert "@media (min-width: 769px)" in block
    assert not re.search(r"@media[^{]*max-width", block), (
        "a max-width media query would invert phone-first")
    # The base is the narrow grid; the query widens it.
    i = block.index(".ev-grid {")
    assert "repeat(5," in block[i:block.index("}", i)]
    j = block.index("@media (min-width: 769px)")
    assert "repeat(10," in block[j:]
