"""The intraday yield overlay. R-IV.1257(c).

THE RULING'S WORDS ARE THE TEST LIST: "^IRX/^FVX/^TNX/^TYX, FRED stays official, 2Y stays FRED,
verify each symbol, no substitution."

WHY VERIFICATION BY NAME IS THE CENTRE OF THIS FILE. A wrong symbol that ANSWERS is worse than
one that does not: its numbers are plausible, and a 5-year yield placed on the 10-year row reads
as a 20bp move rather than as a wrong series. The same check is what established that `VIX3M` is
not a FRED id while `VXVCLS` is. So the overlay reads the vendor's own instrument name BEFORE it
reads a number, and these tests assert both halves -- that a matching name is accepted and that
a mismatching one is DROPPED rather than placed.

NETWORK TESTS ARE MARKED AND SKIPPED WHEN THE VENDOR IS UNREACHABLE, never passed: "the vendor
is down" and "the symbol is right" must not read alike.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_BACKEND = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from models import yield_intraday as yi                             # noqa: E402
from models import yield_curve_b3 as yc                             # noqa: E402

from ._srcscan import read_source                                   # noqa: E402


# ── the symbols the ruling names ─────────────────────────────────────────────

def test_the_four_symbols_are_exactly_the_ones_the_ruling_names():
    assert sorted(s for s, _m in yi.SYMBOLS.values()) == ["^FVX", "^IRX", "^TNX", "^TYX"]


def test_the_2y_has_no_intraday_leg_and_the_reason_names_the_substitution_it_refuses():
    assert "2Y" in yi.NO_INTRADAY
    why = yi.NO_INTRADAY["2Y"]
    assert "substitution" in why and "5-year" in why and "13-week" in why


def test_every_tenor_the_box_shows_is_either_overlaid_or_explained():
    """The box's rows come from `yield_curve_b3.SERIES`. A tenor that is neither overlaid nor
    listed as having no leg would render with an intraday slot that is silently empty -- which
    is the blank R-IV.1251(b) forbids, one row down."""
    covered = set(yi.SYMBOLS) | set(yi.NO_INTRADAY)
    missing = [t for t in yc.SERIES if t not in covered]
    assert not missing, missing


def test_no_tenor_is_both_overlaid_and_declared_absent():
    assert not (set(yi.SYMBOLS) & set(yi.NO_INTRADAY))


# ── verification, on fixtures ────────────────────────────────────────────────

def _body(name, closes=(4.1, 4.2), stamps=(1000, 2000)):
    return {"chart": {"result": [{
        "meta": {"shortName": name, "exchangeTimezoneName": "America/New_York"},
        "timestamp": list(stamps),
        "indicators": {"quote": [{"close": list(closes)}]},
    }], "error": None}}


def _patched(monkeypatch, body):
    import json as _json
    import io as _io

    class _Resp:
        def __init__(self, payload):
            self._b = _json.dumps(payload).encode("utf-8")

        def read(self):
            return self._b

        def __enter__(self):
            return _io.BytesIO(self._b)

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(yi.urllib.request, "urlopen", lambda *a, **k: _Resp(body))


def test_a_symbol_whose_name_matches_is_accepted(monkeypatch):
    _patched(monkeypatch, _body("10-Year Bond"))
    out = yi.fetch_one("10Y", "^TNX", "10")
    assert out["verified"] is True
    assert out["last_pct"] == 4.2
    assert out["change_bp"] == 10.0, out["change_bp"]


def test_a_symbol_whose_name_does_not_match_is_dropped_and_not_placed(monkeypatch):
    """THE WHOLE POINT. The response is well-formed and carries numbers; it is the INSTRUMENT
    that is wrong. The block must come back unverified with no figure on it."""
    _patched(monkeypatch, _body("Treasury Yield 5 Years"))
    out = yi.fetch_one("10Y", "^TNX", "10")
    assert out["verified"] is False
    assert out["last_pct"] is None and out["change_bp"] is None and not out["bars"]
    assert "does not carry" in out["reason"] and "Treasury Yield 5 Years" in out["reason"]


def test_a_dropped_leg_is_never_filled_from_another(monkeypatch):
    """No substitution (c). With the 10Y answering as the 5-year, the 10Y row must be empty --
    not carrying ^FVX's number, and not carrying the 30Y's either."""
    def fake(tenor, symbol, marker):
        if symbol == "^TNX":
            return {"tenor": tenor, "symbol": symbol, "verified": False, "bars": [],
                    "last_pct": None, "change_bp": None, "as_of": None, "reason": "mismatch"}
        return {"tenor": tenor, "symbol": symbol, "verified": True,
                "bars": [{"t": 1, "pct": 9.99}], "last_pct": 9.99, "change_bp": 1.0,
                "as_of": None, "reason": None}
    monkeypatch.setattr(yi, "fetch_one", fake)
    yi._cache.clear()
    out = yi.overlay()
    assert out["tenors"]["10Y"]["last_pct"] is None
    assert "10Y" in out["unavailable"]
    assert "10Y" not in out["verified_tenors"]


def test_a_response_with_no_closes_is_an_absence_with_a_reason(monkeypatch):
    _patched(monkeypatch, _body("10-Year Bond", closes=(None, None)))
    out = yi.fetch_one("10Y", "^TNX", "10")
    assert out["verified"] is True, "the instrument was right; only the data is missing"
    assert out["last_pct"] is None and "none with a close" in out["reason"]


def test_a_fetch_failure_is_an_absence_and_never_raises(monkeypatch):
    def boom(*a, **k):
        raise OSError("down")
    monkeypatch.setattr(yi.urllib.request, "urlopen", boom)
    out = yi.fetch_one("10Y", "^TNX", "10")
    assert out["verified"] is False and "fetch failed" in out["reason"]


# ── the cache, which must not outlive a bar ──────────────────────────────────

def test_the_cache_is_one_bar_long_and_not_one_day(monkeypatch):
    """A day-long cache on an INTRADAY series serves the open all afternoon. That is the
    "stale presented as current" fault the module rules out, so the window is asserted."""
    assert yi.CACHE_SECONDS == 15 * 60
    src = read_source(str(_BACKEND / "models" / "yield_intraday.py"))
    assert "CACHE_SECONDS" in src


def test_a_cached_overlay_says_so_and_carries_its_age(monkeypatch):
    monkeypatch.setattr(yi, "fetch_one", lambda t, s, m: {
        "tenor": t, "symbol": s, "verified": True, "bars": [{"t": 1, "pct": 1.0}],
        "last_pct": 1.0, "change_bp": 0.0, "as_of": None, "reason": None})
    yi._cache.clear()
    first = yi.overlay()
    assert first["cached"] is False
    second = yi.overlay()
    assert second["cached"] is True and second["cache_age_seconds"] >= 0


# ── FRED stays official ──────────────────────────────────────────────────────

def test_the_overlay_says_in_its_own_words_that_it_is_not_the_official_level():
    yi._cache.clear()
    import types
    monkey = types.SimpleNamespace()
    del monkey
    out = yi.overlay.__doc__ or ""
    assert "Cached" in out or "report" in out
    src = read_source(str(_BACKEND / "models" / "yield_intraday.py"))
    assert "FRED STAYS OFFICIAL" in src
    assert "never replaces" in src


def test_the_route_keeps_the_overlay_under_its_own_key(monkeypatch):
    """Merged into `tenors`, a 15-minute tick and a settled close would share a field and a
    label computed off it would be computed off an unsettled number."""
    src = read_source(str(_BACKEND / "api" / "yield_curve.py"))
    assert '"intraday": _intraday_block()' in src
    assert "_tenor_block" in src and "yield_intraday" in src


def test_the_route_does_not_let_the_overlay_blank_the_fred_table():
    """A second vendor must not be able to take out the first one's numbers. The overlay has
    its own try, inside the payload, not around it."""
    src = read_source(str(_BACKEND / "api" / "yield_curve.py"))
    block = src[src.index("def _intraday_block"):src.index("def payload")]
    assert "try:" in block and "except Exception" in block
    assert "FRED's daily series is unaffected" in block.replace("\n", " ").replace("  ", " ") \
        or "is unaffected" in block


# ── live, and skipped rather than passed when the vendor is unreachable ──────

@pytest.mark.parametrize("tenor", sorted(yi.SYMBOLS))
def test_live_each_symbol_identifies_itself_as_the_tenor_it_is_placed_on(tenor):
    symbol, marker = yi.SYMBOLS[tenor]
    out = yi.fetch_one(tenor, symbol, marker)
    if out["reason"] and "fetch failed" in out["reason"]:
        pytest.skip("%s unreachable from here: %s" % (symbol, out["reason"]))
    assert out["verified"] is True, out["reason"]
    assert out["vendor_name"], out
    assert out["last_pct"] is not None and 0.0 < out["last_pct"] < 25.0, out["last_pct"]


def test_live_a_symbol_that_does_not_exist_is_refused():
    """The positive control against the live vendor: a made-up symbol must not come back
    verified. Without it, a probe that accepted everything would read as four passes.

    A 404 IS THE CONTROL FIRING, NOT A SKIP. The first version of this test skipped on any
    reason containing "fetch failed", and the vendor answers a non-existent symbol with HTTP
    404 -- so the control that proves the probe can refuse was being skipped BECAUSE it
    worked. The module now reports a status separately from an outage, and only a genuine
    transport failure skips.
    """
    out = yi.fetch_one("10Y", "^TNX.NOPE", "10")
    if out["reason"] and "fetch failed" in out["reason"]:
        pytest.skip("vendor unreachable; the control cannot run")
    assert out["verified"] is False, out
    assert out.get("http_status") == 404 or "does not carry" in (out["reason"] or ""), out
