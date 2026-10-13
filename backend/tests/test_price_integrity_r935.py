"""ARTEMIS price plausibility — R-IV.935(b). Log-and-flag, never reject.

The three cases the ruling names are the first three tests. The rest guard the properties that
make this safe to put on a live money path: the TYPE stays live, nothing is ever dropped, and
`would_suppress` keeps exactly one author.
"""
from __future__ import annotations

import asyncio
import sys

import pytest

sys.path.insert(0, __file__.rsplit("tests", 1)[0])

from config import l0_routing as l0  # noqa: E402
from signals import price_integrity as pi  # noqa: E402


def _run(c):
    return asyncio.run(c)


def _stub_ref(monkeypatch, value):
    async def fake(ticker):
        return value
    monkeypatch.setattr(pi, "reference_price", fake)


# ── the three cases R-IV.935(b)2 names ───────────────────────────────────

def test_a_HAL_row_at_4500_FLAGS(monkeypatch):
    """The real defect: HAL priced from the Indian listing while US HAL is about 32."""
    _stub_ref(monkeypatch, 32.60)
    out = _run(pi.check({"signal_type": "ARTEMIS_SHORT", "ticker": "HAL",
                         "entry_price": 4500.0}))
    assert out["status"] == pi.IMPLAUSIBLE, out
    assert "different instrument" in out["reason"]
    assert out["reference"] == 32.60 and out["incoming"] == 4500.0


def test_a_HAL_row_at_38_does_NOT_flag(monkeypatch):
    """The control. Without this, a check that flagged everything would read as working."""
    _stub_ref(monkeypatch, 32.60)
    out = _run(pi.check({"signal_type": "ARTEMIS_LONG", "ticker": "HAL",
                         "entry_price": 38.0}))
    assert out["status"] == pi.OK, out


def test_a_MISSING_reference_is_unknown_NOT_passed(monkeypatch):
    """"I could not check" is not "I checked and it is fine". Collapsing the two is how a
    blind alarm reports health, and the ruling says flag it."""
    _stub_ref(monkeypatch, None)
    out = _run(pi.check({"signal_type": "ARTEMIS_SHORT", "ticker": "HAL",
                         "entry_price": 38.0}))
    assert out["status"] == pi.UNKNOWN, out
    assert out["status"] != pi.OK


# ── the band, reported as 25% ─────────────────────────────────────────────

def test_the_band_is_25_percent():
    assert pi.BAND_PCT == 25.0


@pytest.mark.parametrize("inc,expect", [
    (100.0, pi.OK),           # 0% off
    (124.9, pi.OK),           # just inside
    (125.1, pi.IMPLAUSIBLE),  # just outside
    (75.1, pi.OK),            # just inside, below
    (74.9, pi.IMPLAUSIBLE),   # just outside, below
])
def test_the_band_bites_in_both_directions(inc, expect):
    status, _ = pi.evaluate("X", inc, 100.0)
    assert status == expect, (inc, status)


def test_the_real_measured_cases_all_flag():
    """The numbers actually found in the book, so a future loosening has to face them."""
    assert pi.evaluate("HAL", 5088.80, 32.60)[0] == pi.IMPLAUSIBLE     # 156x
    assert pi.evaluate("CBRE", 995.00, 130.71)[0] == pi.IMPLAUSIBLE    # 7.6x
    # ...and the same tickers' GOOD rows do not, judged against a SAME-INSTANT reference.
    assert pi.evaluate("HAL", 42.70, 42.00)[0] == pi.OK
    assert pi.evaluate("CBRE", 153.50, 150.00)[0] == pi.OK


def test_the_check_is_SAME_INSTANT_ONLY_and_this_is_why():
    """A LIMIT, pinned deliberately. My first version of the test above compared HAL's good
    42.70 fire price against TODAY's 32.60 and the check flagged it -- correctly, at 31%. That
    is the identical basis error diagnosed under R-IV.930(b)3: a historical fire price measured
    against a present-day quote. So this check is only ever valid where the two prices share a
    moment, which is exactly why it lives on the INGEST path and must never be used as a
    retrospective sweep over stored rows."""
    assert pi.evaluate("HAL", 42.70, 32.60)[0] == pi.IMPLAUSIBLE   # across months: meaningless
    assert pi.evaluate("HAL", 42.70, 42.00)[0] == pi.OK            # same instant: the real test


# ── scope: ARTEMIS tonight, and the rest untouched ───────────────────────

@pytest.mark.parametrize("t,inscope", [
    ("ARTEMIS_SHORT", True), ("ARTEMIS_LONG", True), ("artemis_short", True),
    ("HOLY_GRAIL_1H", False), ("SELL_RIP_EMA", False), ("CIRCES_STEW", False),
    ("", False), (None, False),
])
def test_only_ARTEMIS_is_in_scope_tonight(t, inscope):
    assert pi.is_in_scope(t) is inscope


def test_an_out_of_scope_signal_is_not_checked_at_all(monkeypatch):
    """No verdict, no UW call, no behaviour change for every other strategy."""
    called = []

    async def fake(ticker):
        called.append(ticker)
        return 1.0
    monkeypatch.setattr(pi, "reference_price", fake)
    assert _run(pi.check({"signal_type": "HOLY_GRAIL_1H", "ticker": "HAL",
                          "entry_price": 4500.0})) is None
    assert called == []


# ── the gate: one author, the row suppressed, the TYPE still live ────────

def test_a_flagged_row_sets_would_suppress():
    d = l0.evaluate_l0_gate({"signal_type": "ARTEMIS_SHORT", "ticker": "HAL"},
                            price_integrity={"status": "implausible", "reason": "HAL 4500"})
    assert d["would_suppress"] is True
    assert "price integrity implausible" in d["reason"]
    assert d["price_integrity"]["status"] == "implausible"


def test_an_unknown_row_also_sets_would_suppress():
    d = l0.evaluate_l0_gate({"signal_type": "ARTEMIS_SHORT", "ticker": "HAL"},
                            price_integrity={"status": "unknown", "reason": "no reference"})
    assert d["would_suppress"] is True


def test_a_clean_row_is_NOT_suppressed_BY_THE_PRICE_CHECK():
    """Uses a type the salvage plan left live, so this tests the PRICE CHECK rather than
    ARTEMIS's retirement. Pointed at ARTEMIS_SHORT it would now pass for the wrong reason --
    suppressed by the type, not by the price -- which is a test that has stopped measuring
    what it is named for."""
    d = l0.evaluate_l0_gate({"signal_type": "CIRCES_STEW", "ticker": "HAL"},
                            price_integrity={"status": "ok", "reason": "within 2%"})
    assert d["would_suppress"] is False
    assert d["price_integrity"]["status"] == "ok"


def test_the_price_check_still_flags_a_ROW_even_though_the_TYPE_is_now_retired():
    """SUPERSEDED IN PART, and the part that survives is the point.

    R-IV.935(b) forbade suppressing ARTEMIS_SHORT as a TYPE, because it was QUERY's only
    |t| above 2 and switching it off to stop two tickers would have hidden the strongest signal
    we had. R-IV.945(c)1 then retired its surface anyway, under the Olympus salvage plan -- a
    different decision on different grounds, and it overrides the conclusion without touching
    the reasoning.

    What must NOT be lost is the row-level mechanism: the price check still has to mark an
    individual implausible row, with its own reason, independently of the type's standing. A
    type-wide retirement that quietly absorbed the per-row verdict would leave nothing to count
    for (b)3 and nothing to point at when the principal's chart is repointed."""
    assert "ARTEMIS_SHORT" in l0.SUPPRESS_ALWAYS          # retired by R-IV.945(c)1
    d = l0.evaluate_l0_gate({"signal_type": "ARTEMIS_SHORT", "ticker": "HAL"},
                            price_integrity={"status": "implausible", "reason": "HAL 4500"})
    assert d["would_suppress"] is True
    # the ROW's own verdict is still recorded and still says why
    assert d["price_integrity"]["status"] == "implausible"
    assert "price integrity implausible" in d["reason"]


def test_omitting_the_verdict_changes_nothing_for_existing_callers():
    """Backward compatibility: the field is absent, not null, when nothing was measured."""
    # CIRCES_STEW, verified KEEP -- HOLY_GRAIL_1H is itself in SUPPRESS_ALWAYS, so it could
    # never have shown that omitting the verdict leaves would_suppress alone.
    d = l0.evaluate_l0_gate({"signal_type": "CIRCES_STEW", "ticker": "NVDA"})
    assert d["rule"] == l0.RULE_KEEP
    assert d["would_suppress"] is False
    assert "price_integrity" not in d


# ── it never raises, and never drops ─────────────────────────────────────

@pytest.mark.parametrize("bad", [None, "x", {}, [], -1, 0])
def test_evaluate_never_raises(bad):
    status, reason = pi.evaluate("X", bad, 100.0)
    assert status in (pi.OK, pi.IMPLAUSIBLE, pi.UNKNOWN)
    assert isinstance(reason, str) and reason


def test_check_survives_an_exploding_reference(monkeypatch):
    async def boom(ticker):
        raise RuntimeError("UW exploded")
    monkeypatch.setattr(pi, "reference_price", boom)
    out = _run(pi.check({"signal_type": "ARTEMIS_SHORT", "ticker": "HAL",
                         "entry_price": 38.0}))
    assert out["status"] == pi.UNKNOWN
    assert "RuntimeError" in out["reason"]


def test_nothing_in_this_module_can_drop_a_signal():
    """Read the parsed source: a raise on the ingest path would drop a signal, which is the
    one thing R-IV.935(b)1 forbids."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(pi))
    raises = [n for n in ast.walk(tree) if isinstance(n, ast.Raise)]
    assert not raises, "a raise here would drop a signal on the ingest path"
