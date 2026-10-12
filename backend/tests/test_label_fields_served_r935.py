"""The label fields are SERVED, not merely built — R-IV.935(e)1/2/3.

WHY THIS FILE EXISTS. ABACUS found `attach_label_fields` had **zero callers outside tests**.
R-IV.833's two fields were authored, unit-tested, merged and deployed, and no route ever put
them on a payload. Every test passed the whole time, because a test can import the function
directly. "It exists" and "it reaches the page" are different claims and only the second one
matters to a reader of the page.

So the assertions below are about the CALL GRAPH, read from the parsed tree -- a docstring that
merely discusses the name cannot satisfy them.
"""
from __future__ import annotations

import ast
import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from config import strategy_aliases as sa  # noqa: E402

SKIP_DIRS = {"tests", "__pycache__", ".venv-test", "hub_mcp"}


def _py_files():
    for p in _BACKEND.rglob("*.py"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        yield p


def _calls_in(path: pathlib.Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return set()
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Call):
            f = n.func
            if isinstance(f, ast.Name):
                out.add(f.id)
            elif isinstance(f, ast.Attribute):
                out.add(f.attr)
    return out


@pytest.fixture(autouse=True)
def _fresh():
    sa.reset_card_cache_for_tests()
    yield
    sa.reset_card_cache_for_tests()


def test_attach_label_fields_has_at_least_one_NON_TEST_caller():
    """THE ASSERTION THAT WAS MISSING. A field nobody calls is not served."""
    callers = [p for p in _py_files() if "attach_label_fields" in _calls_in(p)]
    assert callers, (
        "attach_label_fields is called from no non-test module, so display_label and "
        "upgrade_tag reach no payload")


def test_both_trade_ideas_enrich_paths_are_wrapped():
    """R-IV.935(e)1 names two paths: the grouped feed's primary_signal and the paged route's
    _enrich. Both must wrap, or one surface silently lacks the fields."""
    path = _BACKEND / "api" / "trade_ideas.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    sites = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
             and n.func.id == "attach_label_fields"]
    assert len(sites) >= 2, "expected both enrich paths wrapped, found %d" % len(sites)
    # and each wraps the existing codename enrichment rather than replacing it
    for s in sites:
        inner = ast.dump(s)
        assert "attach_codename" in inner or "tag_row" in inner, inner


def test_the_import_is_real_and_resolves():
    """A wired call that imports a name which does not exist is the Hermes defect again."""
    from config.strategy_aliases import attach_label_fields  # noqa: F401
    assert callable(attach_label_fields)


# ── (e)3 Title Case in the data ───────────────────────────────────────────

def test_no_card_derived_codename_is_left_shouting():
    """The cards' titles are ALL CAPS. The payload is not: the page styles the capitals, and a
    codename shouting in the DATA cannot be un-shouted by CSS."""
    shouting = sorted({c for c in sa.card_codenames().values()
                       if c and c.upper() == c and any(ch.isalpha() for ch in c)})
    assert not shouting, shouting


def test_labels_are_title_case_end_to_end():
    for t, expect in (("BEARISH_BREAKDOWN", "Phaethon | "),
                      ("ARTEMIS_SHORT", "Artemis | "),
                      ("TWO_CLOSE_VOLUME", "Persephone | "),
                      ("TRAPPED_SHORTS", "Hector | ")):
        assert sa.display_label(t).startswith(expect), (t, sa.display_label(t))


@pytest.mark.parametrize("raw,want", [
    ("PHAETHON", "Phaethon"),
    ("CIRCE'S STEW", "Circe's Stew"),     # str.title() gives "Circe'S Stew" -- the bug this avoids
    ("CIRCE’S STEW", "Circe’s Stew"),
    ("MIDAS", "Midas"),
    ("", ""),
])
def test_the_casing_helper_handles_the_apostrophe(raw, want):
    assert sa._title_case_codename(raw) == want


def test_str_title_would_have_been_wrong():
    """A positive control for the helper's reason to exist, so nobody 'simplifies' it back."""
    assert "CIRCE'S STEW".title() == "Circe'S Stew"
    assert sa._title_case_codename("CIRCE'S STEW") != "CIRCE'S STEW".title()


# ── the served shape, on a row like the route's ───────────────────────────

def test_a_route_shaped_row_gets_both_fields():
    row = {"signal_id": "x", "ticker": "HAL", "signal_type": "BEARISH_BREAKDOWN",
           "strategy": "CTA Scanner", "score": 61.0}
    out = sa.attach_label_fields(row)
    assert out is row
    assert out["display_label"] == "Phaethon | Bearish Breakdown"
    assert "upgrade_tag" in out and out["upgrade_tag"] is None
    assert out["signal_type"] == "BEARISH_BREAKDOWN" and out["strategy"] == "CTA Scanner"
