"""R-IV.1178 / R-IV.1180 — the Add control in the page Nick actually opens.

WHAT THIS FILE IS REALLY GUARDING, and it is my own mistake. `/app` has served **v2.html ->
v2.js -> v2.css** since the flip on 2026-07-13; `index.html` + `app.js` moved to
`/app/legacy`. I built all of R-IV.1173 STEP 1 in the legacy pair and then verified the
deploy carefully -- pins, served bytes, the disabled Confirm -- against `/app/legacy`. Every
check was correct and not one of them was about the page in front of Nick. He hard-refreshed
and of course saw nothing: no cache state can produce a button that is not in the file the
page loads.

The first test below is therefore the one that matters most: the route table says which file
`/app` serves, and the Add control must be in THAT file. A test that asserted "the control
exists in app.js" would have passed throughout the entire failure.

The rest pin the things that would silently diverge: the mirrored structure sets (a drift
inverts the sign of the previewed cash movement), the 100x multiplier, and STEP 1's guarantee
that there is no path to a write.
"""
from __future__ import annotations

import io
import os
import re

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND = os.path.join(os.path.dirname(BACKEND), "frontend")


def _read(name: str) -> str:
    return io.open(os.path.join(FRONTEND, name), encoding="utf-8", errors="replace").read()


def _v2() -> str:
    return _read("v2.js")


def _js_set(name: str, src: str) -> set:
    i = src.index("const %s = new Set([" % name)
    return set(re.findall(r"'([a-z_]+)'", src[i:src.index("]);", i)]))


# ── the one that would have caught the whole failure ────────────────────────

def test_the_page_app_serves_is_the_page_with_the_add_control():
    """THE TEST I DID NOT HAVE. Read the route table for the file `/app` returns, then require
    the control to be in that file -- rather than naming v2.js here, which would just be my
    assumption written down a second time."""
    main = io.open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
    i = main.index('@app.get("/app", response_class=FileResponse)')
    block = main[i:i + 400]
    m = re.search(r'FileResponse\(os\.path\.join\(frontend_path,\s*"([^"]+)"\)\)', block)
    assert m, "could not read which file /app serves"
    served_html = m.group(1)
    assert served_html == "v2.html", (
        "/app serves %s; this test and the Add control must follow it" % served_html)

    html = _read(served_html)
    scripts = re.findall(r'<script src="/([^"?]+)', html)
    assert any("Add to position" in _read(s) for s in scripts if s.endswith(".js")), (
        "none of the scripts %r that %s loads contains the Add control" % (scripts, served_html))


def test_the_legacy_page_keeps_its_copy():
    """R-IV.1178(b): "If it's currently only on the list rows, keep it there too." The legacy
    build is untouched, so /app/legacy still works for anyone on that link."""
    assert "Add to position (R-IV.1173)" in _read("app.js")


# ── the button is in the detail panel, beside Close position ────────────────

def test_the_add_button_sits_in_the_drawer_actions_beside_close():
    """Where Nick looks. The panel he opened showed only Close position and Chart."""
    src = _v2()
    i = src.index('<div class="drawer-actions">')
    block = src[i:src.index("</div>`", i)]
    assert "posCloseBtn" in block
    assert "posAddBtn" in block
    assert "posChartBtn" in block
    assert block.index("posCloseBtn") < block.index("posAddBtn") < block.index("posChartBtn"), (
        "the Add button must sit between Close position and Chart")


def test_the_add_button_is_styled_as_a_peer():
    src = _v2()
    i = src.index("posAddBtn")
    decl = src[max(0, i - 200):i]
    assert "btn-secondary" in decl, "Add must carry the same class as its peer buttons"


def test_the_button_only_renders_for_OPEN():
    """R-IV.1173(e): a closed row has nothing to add to. A control that appears and then
    refuses is worse than one that is absent."""
    src = _v2()
    assert "ADD_POS_ELIGIBLE(p) ?" in src
    i = src.index("const ADD_POS_ELIGIBLE")
    assert "'OPEN'" in src[i:i + 200]


def test_the_handler_is_bound_only_when_the_button_was_drawn():
    """`$('posAddBtn')` is null when the template chose not to render it, and
    `null.addEventListener` would throw and take the rest of the drawer -- the earnings fetch
    included -- down with it."""
    src = _v2()
    i = src.index("$('posAddBtn')")
    window = src[max(0, i - 120):i + 160]
    assert "if ($('posAddBtn'))" in window


def test_status_is_actually_on_the_payload_the_drawer_receives():
    """THE WAY THIS FIX COULD HAVE REPEATED THE BUG. Gating on a field the API does not send
    means the button never renders and the symptom is identical. `GET /api/v2/positions`
    returns `SELECT *` from unified_positions through `_row_to_dict`, and the route's own code
    already reads `p["status"]`, which is the proof the key is there."""
    src = io.open(os.path.join(BACKEND, "api", "unified_positions.py"),
                  encoding="utf-8").read()
    assert "SELECT * FROM unified_positions" in src
    assert 'p["status"] == "OPEN"' in src


# ── the mirrored rules ──────────────────────────────────────────────────────

def test_the_credit_structures_mirror_the_backend_exactly():
    """THE SIGN OF THE PREVIEWED CASH MOVEMENT DEPENDS ON THIS. A credit structure is paid on
    open, so adding to one CREDITS cash. If the lists drift, the preview shows the opposite
    sign from what the write path will record, and both sides look self-consistent."""
    from api.unified_positions import CREDIT_STRUCTURES

    assert _js_set("ADD_POS_CREDIT_STRUCTURES", _v2()) == set(CREDIT_STRUCTURES)


def test_the_v2_and_legacy_mirrors_agree_with_each_other():
    """Two copies of the same rule now exist, one per frontend. They must not drift apart
    either -- that would make the two pages preview different trades."""
    assert _js_set("ADD_POS_CREDIT_STRUCTURES", _v2()) == \
        _js_set("ADD_POS_CREDIT_STRUCTURES", _read("app.js"))


def test_the_multiplier_is_1_for_stock_and_100_otherwise():
    src = _v2()
    i = src.index("const addPosMultiplier")
    body = src[i:i + 200]
    assert "? 1 : 100" in body


# ── STEP 1: there is no path to a write ─────────────────────────────────────

def test_confirm_is_disabled_in_the_markup():
    src = _v2()
    i = src.index('id="a_submit"')
    assert "disabled" in src[i:i + 80]


def test_STEP_2_BINDS_A_HANDLER_AND_THE_PREVIEW_OWNS_THE_BUTTON():
    """R-IV.1243(d): step 2 arrived, so this guard changed with it.

    It asserted that NO handler was bound — correct while saving was switched off, and now
    exactly backwards. What replaces it is the property that still matters: the button is
    enabled by THE PREVIEW and by nothing else, so the condition for saving is the same
    computation Nick checked on 2026-10-18, not a second opinion about the numbers.
    """
    src = _v2()
    i = src.index("function openAddToPositionForm")
    body = src[i:src.index("\n  function updateAddToPositionPreview", i)]
    assert "$('a_submit').addEventListener" in body, "step 2 binds the handler"
    assert 'id="a_submit" disabled' in body, "it still starts disabled"
    prev = src[src.index("function updateAddToPositionPreview"):]
    prev = prev[:prev.index("async function submitAddToPosition")]
    assert "okBtn.disabled = true" in prev
    assert prev.count("okBtn.disabled = false") == 1, "exactly one place may enable it"
    assert prev.index("okBtn.disabled = true") < prev.index("okBtn.disabled = false")


def test_THE_WRITE_IS_SINGLE_FLIGHT_BECAUSE_THE_SERVER_GUARD_DOES_NOT_COVER_IT():
    """This banned every write. Step 2 is the write, so the ban is replaced by the property
    that makes the write safe.

    `position_lots` has NO server-side duplicate guard for a MANUAL add — the route's guard
    fires only on a `broker_ref`, and a hand entry has none. That is the filed defect where
    cash_flows refuses a duplicate same-day movement and position_lots does not, leaving
    basis > cash with the two stores disagreeing as the only detector.

    So the client holds both halves: `disabled` for the round trip AND an in-flight flag, which
    is what stops a second click arriving before the browser repaints. Neither replaces a
    server guard, and the gap is reported rather than papered over.
    """
    src = _v2()
    i = src.index("async function submitAddToPosition")
    body = src[i:src.index("\n  function openCloseForm", i)]
    assert "if (addLotInFlight) return;" in body
    assert "addLotInFlight = true;" in body
    assert "addLotInFlight = false;" in body
    assert "finally" in body, "the flag must clear on failure too, or one error locks the form"
    assert "X-Requested-With" in body, "a session-authed mutation needs the CSRF header"
    assert "/lots" in body, "the lot route, not the position-create route"


def test_THE_EXACT_TOTAL_IS_SENT_AS_A_PRICE_BECAUSE_THE_ROUTE_HAS_NO_FIELD_FOR_IT():
    """FOUND BY READING THE ROUTE, and it would have failed silently.

    `AddLotRequest` carries fill_time / qty / price / fees / source / broker_ref / reason /
    actor and NO cost_basis, with Pydantic's default `extra: ignore`. A `cost_basis` key would
    have been DROPPED and the basis derived from price x qty — the user's own broker figure
    discarded without a word.

    It is carried instead as the per-unit price that reproduces the total: the same money by
    construction. The preview states what will be recorded, because the saved price is then
    not the price typed in, and a reader comparing the lot against the ticket would otherwise
    find a discrepancy nobody explained.
    """
    from api.unified_positions import AddLotRequest

    assert "cost_basis" not in AddLotRequest.model_fields
    src = _v2()
    i = src.index("async function submitAddToPosition")
    body = src[i:src.index("\n  function openCloseForm", i)]
    assert "body.cost_basis" not in body
    assert "Math.abs(exact) / (addPosMultiplier(p) * qty)" in body
    prev = src[src.index("function updateAddToPositionPreview"):]
    assert "Recorded price per" in prev[:prev.index("async function submitAddToPosition")]


def test_THE_EXPLANATORY_TEXT_IS_GONE_AND_THE_LABELS_REMAIN():
    """R-IV.1243(d): remove all the explanatory text, keep each field with its label.

    The step-1 note said "Preview only — saving is switched off in this step", which is now
    false, so it is DELETED rather than reworded: a sentence that has to be rewritten every
    time the behaviour changes is a sentence the next change will forget.
    """
    src = _v2()
    assert "add-pos-step1-note" not in src
    assert "Preview only" not in src
    assert "add-pos-lock-note" not in src
    i = src.index("function openAddToPositionForm")
    body = src[i:src.index("\n  function updateAddToPositionPreview", i)]
    assert "fld-echo" not in body, "the field hints are explanatory text"
    for label in ("Quantity to add", "Price per", "Exact total", "Date added", "Note"):
        assert label in body, label
    # The PREVIEW stays: Nick checked it, and it is the thing that enables the save.
    assert "a_preview" in body and "What this would do" in body


# ── locked to the row ───────────────────────────────────────────────────────

def test_account_and_instrument_are_text_not_inputs():
    """An add that could change the account or the instrument is a different position. The
    lock is that there is no field to change them, not a check that could be bypassed."""
    src = _v2()
    i = src.index("function openAddToPositionForm")
    form = src[i:src.index("$('a_cancel')", i)]
    # `a_when` is absent from this set on purpose: it is generated by `dateFieldHtml`, so no
    # literal id="a_when" appears here. Asserting the literal ids AND the absences separately
    # keeps the claim about what a caller can change, rather than about how the markup is
    # spelled -- the first version of this test failed on the spelling and said nothing about
    # the lock.
    ids = set(re.findall(r"id=\"(a_[a-z_]+)\"", form))
    assert ids == {"a_qty", "a_price", "a_cost", "a_note",
                   "a_preview", "a_refusal", "a_msg", "a_submit", "a_cancel"}, sorted(ids)
    for forbidden in ("a_account", "a_ticker", "a_structure", "a_symbol", "a_expiry",
                      "a_strike"):
        assert forbidden not in form, forbidden
    assert "add-pos-locked" in form


def test_the_preview_names_every_figure_the_ruling_asked_for():
    """R-IV.1173(c): current qty -> new qty, average cost, new cost_basis, and the cash change
    on that account."""
    src = _v2()
    i = src.index("function updateAddToPositionPreview")
    body = src[i:src.index("\n  function openCloseForm", i)]
    for phrase in ("Quantity goes from", "Average cost per", "Cost basis goes from", "Cash in"):
        assert phrase in body, phrase


def test_an_unknown_held_quantity_is_said_not_guessed():
    """Convention #29: `quantity` is the size OPENED and `open_quantity` is what is held.
    When the held figure is unknown the preview must say so rather than put a wrong total in
    front of a decision."""
    src = _v2()
    i = src.index("function updateAddToPositionPreview")
    body = src[i:src.index("\n  function openCloseForm", i)]
    assert "what is held now is unknown" in body
    assert "the current basis is not recorded" in body


def test_the_default_date_field_is_the_shared_one():
    """`dateFieldHtml` + `wireDateField` carry the measured WebKit fix (a `type="date"` that
    reads back as text at 390px). Hand-rolling a date input here would reintroduce the bug
    that silently created a position with NO EXPIRY."""
    src = _v2()
    i = src.index("function openAddToPositionForm")
    body = src[i:src.index("updateAddToPositionPreview(p);\n  }", i)]
    assert "dateFieldHtml('a_when'" in body
    assert "wireDateField('a_when')" in body


# ── cache busting, and the page that authors the pins ───────────────────────

@pytest.mark.parametrize("page,asset,floor", [
    ("v2.html", "v2.js", 59),
    ("v2.html", "v2.css", 47),
    ("stater.html", "v2.css", 43),
    ("abacus.html", "v2.css", 42),
])
def test_every_page_pinning_a_changed_asset_was_bumped(page, asset, floor):
    """THE TRAP CLAUDE.md NAMES, and it is live here: `v2.css` is pinned by THREE pages at
    THREE DIFFERENT values (41 / 42 / 46 before this change). Each is incremented from its own
    value; a page missed keeps serving whatever was cached under its unchanged pin."""
    m = re.search(re.escape(asset) + r"\?v=(\d+)", _read(page))
    assert m, "%s does not pin %s" % (page, asset)
    assert int(m.group(1)) >= floor, "%s pins %s at %s, expected >= %d" % (
        page, asset, m.group(1), floor)


def test_the_html_documents_are_revalidated():
    """R-IV.1178(c). Measured on production: the HTML comes back with `etag` and
    `last-modified` and NO Cache-Control, so a browser applies heuristic freshness and may
    reuse the document without revalidating. The HTML is what authors every `?v=` number, so a
    stale copy pins the old asset and the cache-busting scheme silently does nothing."""
    main = io.open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
    assert "_revalidate_html" in main
    i = main.index("async def _revalidate_html")
    body = main[i:i + 1800]
    assert 'text/html' in body
    assert '"Cache-Control"' in body and "no-cache" in body


def test_the_pinned_assets_are_NOT_forced_to_revalidate():
    """The pin IS the cache key: a fingerprinted asset should stay cacheable. Restricting the
    header to text/html is what keeps that true, so the condition is asserted, not assumed."""
    main = io.open(os.path.join(BACKEND, "main.py"), encoding="utf-8").read()
    i = main.index("async def _revalidate_html")
    body = main[i:i + 1800]
    assert 'ctype.startswith("text/html")' in body


def test_the_styles_exist_for_the_classes_the_module_uses():
    css = _read("v2.css")
    for cls in (".add-pos-locked", ".add-pos-refusal", ".add-pos-step1-note",
                ".add-pos-preview-list", ".add-pos-preview-wait"):
        assert cls in css, cls
    assert "#a_submit:disabled" in css
