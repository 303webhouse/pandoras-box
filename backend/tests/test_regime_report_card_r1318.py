"""The Regime Report Card skeleton, and the CSS tokens that do not exist. R-IV.1318(c).

SKELETON ONLY, MOCK VALUES ONLY. QUERY is writing the scoring spec under R-IV.1316 and the
wiring waits for it. A report card is the most trustable-looking surface on this hub: a
plausible number on it gets believed immediately and questioned late, which is backwards for a
figure whose definition nobody has agreed yet.

THE SCOPE RULE is the part worth guarding now rather than later. When it is wired, its only
reads are rows AFTER the v2.1 cutover, and nothing is backfilled -- with 304 pre-cutover rows
sitting in the same table behind nothing but a `rules_version` column, a report card that graded
the earlier era would be marking a different classifier's homework and reporting it as this
one's. That is one forgotten predicate away at all times.

AND THE CSS TOKENS. The last class of test here exists because the first render of this card
was silently half-invisible: `var(--muted)` and `var(--line)` ARE NOT DEFINED in this
stylesheet, and I used them seventeen times. `color: var(--undefined)` falls back to INHERIT and
looks perfectly fine, so the text read correctly -- while `background: var(--undefined)` falls
back to TRANSPARENT. The history tick on every table row was invisible, and so were the three
unfilled segments of the decay bar shipped in 78518228, which turned a "7 of 10" bar into a bare
7-segment one. The real tokens are `--text-3` and `--border`.
"""
from __future__ import annotations

import hashlib
import io
import pathlib
import re
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from services.regime_report_card import (FERRY_SHA256, SCOPE_RULE,  # noqa: E402
                                         SCORED_VERSION, load_fixture, lint_report_mock)

from ._srcscan import read_source                                  # noqa: E402

V2JS = str(_BACKEND.parent / "frontend" / "v2.js")
V2CSS = str(_BACKEND.parent / "frontend" / "v2.css")
FERRY = pathlib.Path(r"C:\temp\cc-query-handoff\AGORA-MOCK-RegimeReport.dc.html")


# ── the design it was built from ────────────────────────────────────────────

def test_the_ferry_file_hashes_to_the_rulings_sha256():
    """R-IV.1318(c) names it. Verified before anything was written; raw and LF hashes agree
    because the file is LF already, so one value pins it either way."""
    if not FERRY.exists():
        pytest.skip("the ferry file is not on this machine")
    raw = FERRY.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FERRY_SHA256
    assert hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == FERRY_SHA256


# ── the fixture ─────────────────────────────────────────────────────────────

def test_the_fixture_lints_clean():
    assert lint_report_mock(load_fixture()) == []


def test_it_announces_itself_as_a_mock():
    """The most important chip on this card. Everything on it is invented."""
    f = load_fixture()
    assert f["_mock"] is True
    assert "Mock values" in f["footer"]


def test_the_footer_states_the_scope_and_that_nothing_gates_on_it():
    foot = load_fixture()["footer"]
    assert "backfilled" in foot
    assert "#42" in foot
    assert "never change the label" in foot


def test_every_PANEL_carries_its_BASIS_or_its_caption():
    """REPLACED BY R-IV.1321(b)'s LAYOUT. The four "stat cells" became five panels in a
    ruled order -- flips and the 200-day row lead, the worst-dip ORDER panel is added -- so
    the cell-level assertion is restated at panel level.

    The property is unchanged: a bare score is a number whose definition the reader has to
    guess, and a guessed meaning is how a figure gets trusted for something it does not
    measure. Each panel still has to say what it is measuring and on which basis."""
    f = load_fixture()
    for key in ("flips", "ma200", "dip_order"):
        panel = f[key]
        assert panel.get("basis") or panel.get("caption") or panel.get("question"), key

@pytest.mark.parametrize("mutate,expect", [
    (lambda f: f["by_label"][0].update({"checked": 999}), "more checked calls"),
    (lambda f: f["by_label"][2].update({"share_higher": 72.0}),
     "no independent window"),
    (lambda f: f["by_label"][3].update({"history_share": 64.4}),
     "claims a base rate"),
    (lambda f: f["by_label"][0].update({"verdict": {"state": "EARLY"}}),
     "descriptive only"),
    (lambda f: f["ma200"].update({"scored": 0, "whipsaws": 0}), "bare zero"),
    (lambda f: f["ma200"].update({"whipsaws": 99}), "more whipsaws"),
    (lambda f: f.update({"_mock": False}), "must be true"),
    (lambda f: f.update({"footer": "no caveats here"}), "#42"),
    (lambda f: f["scope"].update({"backfilled": True}), "backfilled"),
])
def test_the_lint_CATCHES_each_fault_it_claims_to(mutate, expect):
    """CONVENTION #30, restated for the new shape. These are the forms a half-written
    scorer produces first, plus the three the spec forbids outright: a bare `whipsaws: 0`
    (P7), a share with no independent window (section 11.4), and a base rate claimed by a
    label that has none (R9)."""
    f = load_fixture()
    mutate(f)
    assert any(expect in m for m in lint_report_mock(f)), lint_report_mock(f)

def test_only_post_cutover_rows_may_ever_be_scored():
    assert SCORED_VERSION == "v2.1"
    assert "v2.1" in SCOPE_RULE
    assert "No backfill" in SCOPE_RULE
    assert "settled IS TRUE" in SCOPE_RULE


def test_the_skeleton_reads_NOTHING_yet():
    """Mock values only until QUERY's spec lands. A module that quietly started reading rows
    would be scoring against a spec nobody has written."""
    src = read_source(str(_BACKEND / "services" / "regime_report_card.py"))
    for needle in ("SELECT", "fetchrow", "fetchval", "get_postgres_client", "conn"):
        assert needle not in src, needle


def test_NOTHING_imports_it_the_same_rule_as_regime_ma200():
    """#42, stated by R-IV.1318(c) in those words. A score is precisely what a later reader
    reaches for when they want to gate something, and an import is the first step."""
    for mod in ("regime_classifier.py", "regime_inputs.py", "regime_inputs_v2.py",
                "regime_hysteresis.py", "regime_ma200.py"):
        assert "regime_report_card" not in read_source(str(_BACKEND / "models" / mod)), mod
    assert "regime_report_card" not in read_source(str(_BACKEND / "jobs" / "regime_job.py"))

    # COUNTED AS IMPORTS, from the parsed tree. A substring sweep flags a file that merely
    # MENTIONS the module -- which is how the twin of this test broke when this very module's
    # docstring named `regime_ma200` while explaining it follows the same rule.
    import ast

    hits = []
    for path in sorted(_BACKEND.rglob("*.py")):
        if "__pycache__" in str(path) or path.name.startswith("test_"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""] + [a.name for a in node.names]
            else:
                continue
            if any("regime_report_card" in (n or "") for n in names):
                hits.append(path.name)
                break
    # EMPTY, not ["regime_report_card.py"]: a module does not name itself, so the sweep finds
    # NOTHING at all. That is a stronger result than the one I expected and it is the correct
    # state for a skeleton -- the same correction this suite made for `regime_ma200`.
    assert hits == [], hits


# ── the renderer ────────────────────────────────────────────────────────────

def test_the_card_is_GATED_and_takes_TWO_values():
    """`?report=1` renders the LIVE card (empty until the cutover deploys) and
    `?report=mock` forces the fixture. Both go through the same renderer."""
    js = read_source(V2JS)
    i = js.index("function rcRender(")
    assert "if (!REPORT_ON || !m) return" in js[i:i + 200]
    j = js.index("const REPORT_PARAM")
    block = js[j:j + 420]
    assert "get(" in block and "report" in block
    assert "'1'" in block and "'mock'" in block

def test_an_unmeasured_share_prints_a_DASH_not_a_zero():
    """The old layout drew a live BAR; the new one prints the share as text. The property
    survives the redraw: nothing measured is nothing shown, never 0%."""
    js = read_source(V2JS)
    i = js.index("const rows = (m.by_label || [])")
    block = js[i:i + 900]
    assert "r.share_higher == null" in block


def test_the_table_columns_match_what_the_rows_carry():
    """Eight columns now, and no VERDICT among them (R-IV.1321(b))."""
    js = read_source(V2JS)
    i = js.index("const head = [")
    head = js[i:i + 340]
    for col in ('LABEL', 'SESSIONS', 'CHECKED', 'PENDING', 'INDEP', 'BASE RATE',
                'REACHABILITY'):
        assert "'" + col + "'" in head, col
    assert "'VERDICT'" not in head
    for row in load_fixture()["by_label"]:
        for field in ("sessions", "checked", "pending", "indep", "history_available"):
            assert field in row, (row.get("label"), field)

# ── the tokens, which is where the first render went wrong ──────────────────

def _declared_tokens() -> set:
    css = read_source(V2CSS)
    return set(re.findall(r"--([a-z0-9-]+)\s*:", css))


def test_EVERY_CSS_VARIABLE_THE_INJECTED_BLOCKS_USE_IS_ACTUALLY_DEFINED():
    """THE BUG THIS EXISTS FOR, found by a screenshot and not by any assertion.

    `var(--muted)` and `var(--line)` are not defined in this stylesheet. I used them seventeen
    times across two injected blocks. `color: var(--undefined)` falls back to INHERIT and looks
    right, so every line of text read correctly; `background: var(--undefined)` falls back to
    TRANSPARENT. The history tick on every report-card row was invisible, and so were the three
    unfilled segments of the decay bar already shipped in 78518228 -- a "7 of 10" bar rendering
    as a bare 7.

    A value test could not see this: the DOM was correct, the computed background was
    `rgba(0, 0, 0, 0)`, and only pixels showed it. So the guard is on the SOURCE of the injected
    CSS, where the token name is written.
    """
    js = read_source(V2JS)
    declared = _declared_tokens()
    assert "text-3" in declared and "border" in declared, "the real tokens must exist"
    used = set()
    for name in ("RS21_CSS", "RC_CSS"):
        i = js.index("const %s" % name)
        block = js[i:js.index("].join('')", i)]
        used |= set(re.findall(r"var\(--([a-z0-9-]+)\)", block))
    missing = sorted(t for t in used if t not in declared)
    assert missing == [], missing


def test_the_two_tokens_that_do_not_exist_are_gone_from_the_frontend():
    for path in (V2JS, V2CSS):
        src = read_source(path)
        assert "var(--muted)" not in src, path
        assert "var(--line)" not in src, path


def test_the_decay_bars_unfilled_segments_have_a_VISIBLE_background():
    """The specific regression: the bar must read as N of 10, not as N."""
    js = read_source(V2JS)
    i = js.index("'.rs-decay i{")
    rule = js[i:js.index("',", i)]
    m = re.search(r"background:var\(--([a-z0-9-]+)\)", rule)
    assert m, rule
    assert m.group(1) in _declared_tokens(), m.group(1)
