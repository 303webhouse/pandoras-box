"""R-IV.1209(c) A3 — Position Watch: the panel and the phone-push text, as a MOCK list.

TWO THINGS COULD DO REAL HARM HERE, and they are what these tests are mostly about.

1. WORDING. R-IV.1209(f)5 allows "tighten / trim" and "review stop" and forbids buy, sell or
   reverse. This is the one surface in the build that speaks to Nick about a position he holds
   while the market is open, so an instruction that slipped in would be read as one. The test
   runs the EXISTING no-orders lint -- the same `regime_playbook.order_findings` that guards the
   registered playbooks -- over every string in the fixture. Reusing the lint matters: a second
   implementation of "is this an order?" would eventually disagree with the first, and the
   surface with the looser one is the one that ships the instruction.

2. SENDING. A3 is a mock list and NOTHING IS SENT. The phone block is a picture of a
   notification. So the tests check that the browser has no path to a push, that the ntfy topic
   appears nowhere (R-IV.1209(f)6, R-IV.901(b)1), and that the panel says in its own words that
   it sends nothing -- because a realistic picture of a lock screen is exactly the thing a
   reader could mistake for the real feature working.

ROUTING (f)4 is checked on the fixture: push only for AGAINST, WITH logged, non-held quiet.
"""
from __future__ import annotations

import io
import json
import os
import re

import pytest

import services.regime_playbook as rp

from ._srcscan import read_source

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.dirname(BACKEND)
FRONTEND = os.path.join(ROOT, "frontend")
FIXTURE = os.path.join(FRONTEND, "assets", "agora", "position_watch_mock.json")
HANDOFF = r"C:\temp\cc-query-handoff"

BOARD_SHA = {
    "AGORA-MOCK-PositionWatch.dc.html":
        "c3c65fc0d3fd13b970e84cf40dc24c388405da4185e037583aeae07563957942",
    "AGORA-MOCK-PhonePush.dc.html":
        "e041a80bfbd899d107f0b3eb48c2a695c7c4ff7ccd58911dcfbd218dc08b8bd2",
}


def _fx():
    return json.load(io.open(FIXTURE, encoding="utf-8"))


def _js():
    return read_source(os.path.join(FRONTEND, "v2.js"))


def _panel_js():
    """Just the A3 panel, so a finding is about this code and not the whole file."""
    js = _js()
    return js[js.index("A3 \u2014 POSITION WATCH"):]


def _code_only(js: str) -> str:
    """`js` with comments removed.

    THE PROSE FAULT AGAIN (instance twelve). The panel's own comments explain that it must not
    touch ntfy, `signals` or Kairos, so a raw substring scan reports the explanation as the
    offence. `ast.unparse` has no JS equivalent here, so: block comments go, and so do lines
    whose first non-space characters are `//`. That is sound for this file, which contains no
    URL with `//` and no regex literal -- asserted below, so the stripper cannot quietly become
    wrong when the file grows.
    """
    assert "://" not in js, "a URL would break the // strip; widen the stripper"
    js = re.sub(r"/\*.*?\*/", "", js, flags=re.S)
    kept = [ln for ln in js.splitlines() if not ln.lstrip().startswith("//")]
    return "\n".join(kept)


def _strings(obj, out=None):
    """Every string value in the fixture, keys excluded."""
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).startswith("_"):
                continue        # the _note / _action_rule fields DISCUSS the rule
            _strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _strings(v, out)
    elif isinstance(obj, str):
        out.append(obj)
    return out


# ── the gate ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,want", sorted(BOARD_SHA.items()))
def test_THE_BOARD_HASHES_STILL_MATCH(name, want):
    import hashlib
    p = os.path.join(HANDOFF, name)
    if not os.path.exists(p):
        pytest.skip("handoff file not present on this machine")
    h = hashlib.sha256()
    with io.open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    assert h.hexdigest() == want


def test_the_fixture_cites_BOTH_boards():
    src = _fx().get("_source") or ""
    for want in BOARD_SHA.values():
        assert want in src


# ── 1. WORDING: never buy, sell or reverse ─────────────────────────────────

def test_NO_ORDER_WORDING_ANYWHERE_IN_THE_FIXTURE():
    """R-IV.1209(f)5, enforced by the EXISTING lint rather than a second one. A second
    implementation of "is this an order?" would eventually disagree with the first, and the
    surface with the looser one is the one that ships the instruction."""
    findings = []
    for s in _strings(_fx()):
        findings.extend(rp.lint_text(s, "position_watch_mock.json"))
    assert findings == [], findings


def test_POSITIVE_CONTROL_the_lint_WOULD_catch_an_order():
    """Without this, a lint that found nothing in anything would satisfy the test above."""
    assert rp.lint_text("Sell your IWM puts now.", "x")
    assert rp.lint_text("Buy QQQ calls into the close.", "x")
    assert rp.lint_text("Reverse the GUSH position.", "x")


def test_THE_ACTIONS_ARE_THE_TWO_RULED_PHRASES_PLUS_LOGGED():
    """(f)5 names exactly two actions. LOGGED is not an action at all -- it is what a WITH alert
    gets instead of one, so it is listed and then excluded from the pair."""
    fx = _fx()
    allowed = set(fx["allowed_actions"])
    assert allowed == {"TIGHTEN / TRIM", "REVIEW STOP", "LOGGED"}
    for r in fx["rows"]:
        assert r["action"] in allowed, r["action"]
    # Every ACTIONABLE row uses one of the two ruled phrases.
    acting = [r for r in fx["rows"] if r["action"] != "LOGGED"]
    assert acting, "the board showed actionable rows"
    for r in acting:
        assert r["action"] in {"TIGHTEN / TRIM", "REVIEW STOP"}, r


def test_THE_RIGHT_PHRASE_FOR_THE_RIGHT_EVENT():
    """(f)5 pairs them: "tighten / trim" for exhaustion or a failed breakout against you,
    "review stop" for a LEVEL BREAK against you. Swapping them would be advice about the wrong
    thing, which is subtler than an order and just as wrong."""
    for r in _fx()["rows"]:
        if not r["against"]:
            continue
        ev = r["event"].upper()
        if "LEVEL BREAK" in ev:
            assert r["action"] == "REVIEW STOP", r
        elif "EXHAUSTION" in ev or "FAILED" in ev:
            assert r["action"] == "TIGHTEN / TRIM", r


def test_EVERY_ROW_CARRIES_ITS_REGIME_AND_THE_PANEL_SAYS_ALERT_NOT_SIGNAL():
    """(f)5, both halves."""
    fx = _fx()
    for r in fx["rows"]:
        assert r.get("shown_regime"), r
    assert "alerts, not signals" in fx["caption"]
    js = _panel_js()
    assert "shown_regime" in js, "the renderer must actually print the tag"
    assert "pw-reg" in js


# ── 2. SENDING: nothing is sent, and the panel says so ────────────────────

def test_THE_PANEL_CANNOT_SEND_ANYTHING():
    """The browser has no path to a push, and these are the paths it would have to take.

    `/api/` WAS ON THIS LIST AND IS NOT ANY MORE, which is a widening of the guard and so is
    explained rather than just done. While A3 was a mock, "touches no backend route" was a
    cheap proxy for "sends nothing". B2 makes the panel LIVE, and it has to read
    `/api/position-watch` to show stored events at all. A read is not a send.

    So the ban is now on SENDING, which was always the point, plus an explicit check that the
    only route the panel names is the read-only one -- the proxy is replaced by the thing it
    was standing in for, not dropped.
    """
    js = _code_only(_panel_js())
    for banned in ("ntfy", "method: 'POST'", 'method: "POST"', "XMLHttpRequest",
                   "navigator.sendBeacon", "Notification(", "requestPermission",
                   "serviceWorker"):
        assert banned not in js, banned
    routes = set(re.findall(r"'(/api/[^']+)'", js))
    assert routes == {"/api/position-watch"}, routes


def test_THE_NTFY_TOPIC_APPEARS_NOWHERE():
    """R-IV.1209(f)6 and R-IV.901(b)1: never printed, never logged. It is not in the panel, not
    in the fixture, and it cannot be -- the browser never learns it."""
    assert "ntfy" not in _code_only(_panel_js()).lower()
    raw = io.open(FIXTURE, encoding="utf-8").read().lower()
    assert "ntfy" not in raw
    # And nothing that looks like a 32+ char topic slug.
    assert not re.search(r"[A-Za-z0-9_-]{32,}", io.open(FIXTURE, encoding="utf-8").read()
                         .replace(BOARD_SHA["AGORA-MOCK-PositionWatch.dc.html"], "")
                         .replace(BOARD_SHA["AGORA-MOCK-PhonePush.dc.html"], ""))


def test_THE_PANEL_SAYS_IN_ITS_OWN_WORDS_THAT_IT_SENDS_NOTHING():
    """A realistic picture of a lock screen is exactly the thing a reader could mistake for the
    real feature working, so the panel says so where the picture is."""
    js = _panel_js()
    assert "picture of a" in js
    assert "not a notification" in js
    assert "pw-warn" in js
    fx = _fx()
    assert "NO PUSH IS SENT" in fx["_note"]


def test_the_panel_and_the_fixture_are_flagged_MOCK():
    assert _fx().get("_mock") is True
    js = _panel_js()
    assert 'class="mock-chip"' in js
    assert "NO PUSH IS SENT" in js


# ── 3. ROUTING (f)4 ────────────────────────────────────────────────────────

def test_PUSH_ONLY_FOR_AGAINST():
    """(f)4: "Push via ntfy only for AGAINST. WITH goes to the panel log." """
    for r in _fx()["rows"]:
        if r["pushed"]:
            assert r["against"] is True, r
        if not r["against"]:
            assert r["pushed"] is False, r


def test_EVERY_PUSH_IN_THE_PHONE_BLOCK_IS_AN_AGAINST_ROW():
    """The phone block must not show a push that the routing rule would never have sent."""
    fx = _fx()
    pushed = {r["ticker"] for r in fx["rows"] if r["pushed"]}
    for p in fx["pushes"]:
        tk = p["title"].split("\u00b7")[0].strip()
        assert tk in pushed, (tk, sorted(pushed))
    assert len(fx["pushes"]) == len(pushed)


def test_the_WITH_row_is_LOGGED_not_pushed():
    withs = [r for r in _fx()["rows"] if not r["against"]]
    assert withs, "the board showed a WITH row"
    for r in withs:
        assert r["action"] == "LOGGED"
        assert r["pushed"] is False


def test_NON_HELD_GOES_TO_THE_QUIET_TAB_AS_A_COUNT():
    """(f)4: non-held goes to QUIET. It is shown as a COUNT with a note, not as a list -- a
    panel listing alerts about tickers Nick does not own, laid out like the ones he does, is
    an invitation to act on someone else's position."""
    fx = _fx()
    assert fx["quiet_count"] > 0
    assert "don't hold" in fx["quiet_note"] and "not pushed" in fx["quiet_note"]
    js = _panel_js()
    i = js.index("pw-quiet")
    assert "quiet_note" in js[max(0, i - 400):i + 200]
    # The quiet tab must not render rows.
    k = js.index("tab === 'held'")
    body = js[k:k + 1200]
    assert "rows.map(rowHtml)" in body


def test_the_push_rule_is_stated_on_the_panel():
    assert "against a position you hold" in _fx()["push_rule"]
    assert "push_rule" in _panel_js()


# ── 4. never a signal (f)6 ────────────────────────────────────────────────

def test_NOTHING_HERE_TOUCHES_SIGNALS_KAIROS_OR_THE_RIVER():
    """(f)6: never written to signals, never graded, never shown in Kairos or the River's
    actionable lanes."""
    js = _code_only(_panel_js())
    for banned in ("signals", "signal_id", "addRiverItems", "kairos", "Kairos",
                   "grade", "outcome"):
        assert banned not in js, banned


def test_the_a3_table_does_not_exist_yet():
    """(f)6 puts live events in their own `position_watch_events` table. A3 is a mock list, so
    nothing creates it -- and a table created early is a table someone writes to early."""
    ddl = read_source(os.path.join(BACKEND, "database", "postgres_client.py"))
    assert "position_watch_events" not in ddl


# ── 5. the panel is wired and reachable ───────────────────────────────────

def test_THE_PANEL_IS_REACHABLE_FROM_THE_BOOK_TILE():
    html = read_source(os.path.join(FRONTEND, "v2.html"))
    assert 'id="posWatchBtn"' in html
    i = html.index('gs-id="book"')
    j = html.index('gs-id="crowd"')
    assert 'id="posWatchBtn"' in html[i:j], "the button belongs to the BOOK tile"
    js = _panel_js()
    assert "#posWatchBtn" in js


def test_the_fixture_is_under_assets_so_it_is_SERVED():
    assert os.path.exists(FIXTURE)
    rel = os.path.relpath(FIXTURE, FRONTEND).replace(os.sep, "/")
    assert rel.startswith("assets/")
    assert "/assets/agora/position_watch_mock.json" in _panel_js()


def test_a_FAILED_FIXTURE_LOAD_SAYS_SO():
    """An empty list would read as "no alerts", which is a claim. The panel says the fixture
    did not load instead."""
    js = _panel_js()
    assert "did not load" in js
    i = js.index("if (!data)")
    assert "did not load" in js[i:js.index("function build()", i)]


def test_THE_A3_CSS_IS_TOKENS_AND_PHONE_FIRST():
    css = read_source(os.path.join(FRONTEND, "v2.css"))
    block = css[css.index("PHASE A3"):]
    assert set(re.findall(r"#[0-9a-fA-F]{3,8}", block)) == set()
    assert "@media (min-width: 769px)" in block
    assert not re.search(r"@media[^{]*max-width", block)


def test_THE_PINS_MOVED_FOR_A3():
    pins = {}
    for page in ("v2.html", "stater.html", "abacus.html"):
        m = re.search(r"/v2\.css\?v=(\d+)", read_source(os.path.join(FRONTEND, page)))
        assert m, page
        pins[page] = int(m.group(1))
    assert pins["v2.html"] >= 55, pins
    assert pins["stater.html"] >= 51, pins
    assert pins["abacus.html"] >= 50, pins
    jm = re.search(r"/v2\.js\?v=(\d+)", read_source(os.path.join(FRONTEND, "v2.html")))
    assert jm and int(jm.group(1)) >= 69
