"""R-IV.1173 STEP 1 — the Add-to-position button, form and preview. SAVING IS DISABLED.

WHAT THIS FILE IS REALLY FOR. The preview computes a trade's effect in the browser, and the
write path computes it again in Python. If the two ever disagree, the principal confirms one
trade and the book records another — and the disagreement would be invisible, because each side
looks internally consistent. So the shared rules are MIRRORED deliberately and pinned here:

  * CREDIT_STRUCTURES — a credit structure is PAID on open, so adding CREDITS cash. Get this
    wrong and the preview shows a debit where the book will record a credit, with the sign of
    the cash movement inverted.
  * the 100x multiplier — options are per-contract, stock is per-share. Get this wrong and
    every options preview is off by 100x, which is the one error large enough that nobody would
    miss it, and small enough in code to be a single missing branch.

STEP 1's own guarantee is also tested: Confirm is disabled AND no handler is bound to it, so
there is no path to a write even if the attribute were stripped by hand.
"""
from __future__ import annotations

import io
import os
import re

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(os.path.dirname(BACKEND), "frontend")
APP_JS = os.path.join(FRONTEND, "app.js")
INDEX = os.path.join(FRONTEND, "index.html")
STYLES = os.path.join(FRONTEND, "styles.css")


def _js() -> str:
    return io.open(APP_JS, encoding="utf-8", errors="replace").read()


def _html() -> str:
    return io.open(INDEX, encoding="utf-8", errors="replace").read()


def _js_set(name: str) -> set:
    """The members of a `const NAME = new Set([...])` literal in app.js."""
    src = _js()
    i = src.index("const %s = new Set([" % name)
    body = src[i:src.index("]);", i)]
    return set(re.findall(r"'([a-z_]+)'", body))


# ── the mirrored rules ──────────────────────────────────────────────────────

def test_the_credit_structures_mirror_the_backend_exactly():
    """THE SIGN OF THE CASH MOVEMENT DEPENDS ON THIS. A credit structure is paid on open, so
    adding to one CREDITS cash; everything else debits. If the two lists drift, the preview
    shows the opposite sign from what the write path will record."""
    from api.unified_positions import CREDIT_STRUCTURES
    assert _js_set("ADD_POS_CREDIT_STRUCTURES") == set(CREDIT_STRUCTURES)


def test_the_stock_structures_mirror_the_backend_exactly():
    """These decide the multiplier, so a drift makes every options preview wrong by 100x."""
    js = _js_set("ADD_POS_STOCK_STRUCTURES")
    src = io.open(os.path.join(BACKEND, "api", "unified_positions.py"),
                  encoding="utf-8").read()
    # the backend spells the set inline at its is_stock sites; take the canonical one
    m = re.search(r'is_stock = s in \(([^)]*)\)', src)
    assert m, "could not find the backend's is_stock tuple"
    py = set(re.findall(r'"([a-z_]+)"', m.group(1)))
    assert js == py, "JS %r != backend %r" % (sorted(js), sorted(py))


def test_the_multiplier_is_1_for_stock_and_100_otherwise():
    js = _js()
    i = js.index("function addPosMultiplier")
    body = js[i:i + 160]
    assert "? 1 :" in body and "100" in body


# ── STEP 1: there is no path to a write ─────────────────────────────────────

def test_confirm_is_disabled_in_the_markup():
    html = _html()
    i = html.index('id="addToPosConfirmBtn"')
    assert "disabled" in html[i:i + 160]


def test_no_handler_is_bound_to_confirm():
    """The stronger half. A disabled attribute can be removed in devtools; an unbound button
    cannot do anything regardless. STEP 2 is where a handler appears."""
    js = _js()
    i = js.index("function initAddToPositionModal")
    body = js[i:js.index("\n}", i)]
    assert "addToPosConfirmBtn" not in body, (
        "STEP 1 must bind nothing to Confirm; a handler here is STEP 2's work")


def test_nothing_in_the_module_posts_or_writes():
    """No fetch, no POST, no route. The preview is pure arithmetic over the row already loaded."""
    js = _js()
    i = js.index("// --- Add to position (R-IV.1173)")
    module = js[i:]
    for banned in ("fetch(", "XMLHttpRequest", "/v2/positions", "method: 'POST'",
                   'method: "POST"'):
        assert banned not in module, banned


def test_the_form_says_saving_is_off():
    """A dead button with no explanation reads as a bug. The form says why."""
    html = _html()
    assert "addToPosStep1Note" in html
    i = html.index('id="addToPosStep1Note"')
    assert "Preview only" in html[i:i + 400]


# ── locked to the row ───────────────────────────────────────────────────────

def test_account_and_instrument_are_TEXT_not_inputs():
    """An add that could change the account or the instrument is a different position. The
    lock is enforced by there being no input to change them, not by a check."""
    html = _html()
    i = html.index('id="addToPositionModal"')
    modal = html[i:html.index("<!-- Position Entry Modal", i)]
    inputs = re.findall(r'id="(addToPos[A-Za-z]+)"', modal)
    for forbidden in ("addToPosAccount", "addToPosTicker", "addToPosStructure"):
        assert forbidden not in inputs, forbidden
    assert "addToPosLocked" in modal


@pytest.mark.parametrize("field", ["addToPosQty", "addToPosPrice", "addToPosCost",
                                   "addToPosWhen", "addToPosNote"])
def test_every_ruled_form_field_exists(field):
    assert 'id="%s"' % field in _html()


def test_the_exact_total_is_OPTIONAL_and_says_what_blank_means():
    """R-IV.1173(b): blank derives it and records derived_from_cost_basis. A caller who does not
    know whether blank is allowed will guess, and a guessed total is worse than a derived one."""
    html = _html()
    i = html.index('id="addToPosCost"')
    window = html[max(0, i - 400):i + 600]
    assert "optional" in window.lower()
    assert "derived_from_cost_basis" in window


# ── the button only on OPEN rows ────────────────────────────────────────────

def test_the_add_button_renders_only_for_OPEN():
    """R-IV.1173(e): a closed row has nothing to add to, so the button is not drawn at all --
    a control that appears and then refuses is worse than one that is absent."""
    js = _js()
    i = js.index('class="position-actions"')
    block = js[i:i + 700]
    assert "add-btn" in block
    assert "'OPEN'" in block and "status" in block


def test_the_preview_names_every_figure_the_ruling_asked_for():
    """R-IV.1173(c): current qty -> new qty, current average cost -> new average cost, new
    cost_basis, and the cash change on that account."""
    js = _js()
    i = js.index("function updateAddToPositionPreview")
    body = js[i:js.index("\nfunction initAddToPositionModal", i)]
    for phrase in ("Quantity goes from", "Average cost per", "Cost basis goes from",
                   "Cash in"):
        assert phrase in body, phrase


def test_the_leg_ratio_refusal_exists_and_names_the_alternative():
    js = _js()
    i = js.index("function addPosLegRatioProblem")
    body = js[i:js.index("\n}", js.index("return null;", i))]
    assert "whole" in body
    assert "Open it as a new position instead" in body


def test_the_default_time_is_MOUNTAIN():
    """The only clock Nick reads. A default in UTC would be silently six or seven hours out."""
    js = _js()
    i = js.index("function openAddToPositionModal")
    body = js[i:js.index("\nfunction closeAddToPositionModal", i)]
    assert "America/Denver" in body


# ── cache busting ───────────────────────────────────────────────────────────

def test_the_changed_assets_are_repinned():
    """CLAUDE.md: a changed asset behind an unchanged pin is a fix that never reaches the
    browser. app.js and styles.css both changed in this commit."""
    html = _html()
    for asset, floor in (("app.js", 179), ("styles.css", 155)):
        m = re.search(re.escape(asset) + r"\?v=(\d+)", html)
        assert m, asset
        assert int(m.group(1)) >= floor, "%s pin is %s, expected >= %d" % (
            asset, m.group(1), floor)


def test_the_OTHER_page_pinning_styles_css_was_bumped_too():
    """THE TRAP CLAUDE.md NAMES. `styles.css` is pinned by index.html AND knowledgebase.html at
    independent values; the page missed keeps serving whatever was cached under its old pin."""
    kb = io.open(os.path.join(FRONTEND, "knowledgebase.html"),
                 encoding="utf-8", errors="replace").read()
    m = re.search(r"styles\.css\?v=(\d+)", kb)
    assert m, "knowledgebase.html does not pin styles.css"
    assert int(m.group(1)) >= 30


def test_the_styles_exist_for_the_classes_the_module_uses():
    css = io.open(STYLES, encoding="utf-8", errors="replace").read()
    for cls in (".add-pos-locked", ".add-pos-refusal", ".add-pos-step1-note",
                ".add-pos-preview-list"):
        assert cls in css, cls
