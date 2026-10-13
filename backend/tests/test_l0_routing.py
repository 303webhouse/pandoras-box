"""L0.1a — suppression gate (SHADOW) tests."""

import importlib

import pytest

import config.l0_routing as l0


def _decide(signal_type, ticker=None):
    return l0.evaluate_l0_gate({"signal_type": signal_type, "ticker": ticker})


# --- unconditional suppress set ----------------------------------------
@pytest.mark.parametrize("st", ["HOLY_GRAIL_1H", "HOLY_GRAIL_15M", "PULLBACK_ENTRY", "TRAPPED_LONGS", "ARTEMIS_LONG"])
def test_unconditional_suppress(st):
    d = _decide(st, ticker="AAPL")  # liquid ticker must not rescue these
    assert d["rule"] == l0.RULE_SUPPRESS
    assert d["would_suppress"] is True


# --- the liquid-conditional MECHANISM, which is still live code ----------
# RESISTANCE_REJECTION (SISYPHUS) was this rule's only member until R-IV.945(c)1 promoted it to
# the unconditional set, leaving SUPPRESS_IF_NON_LIQUID empty. The mechanism itself is NOT
# retired -- `evaluate_l0_gate` still implements it and a future type can be added -- so it is
# exercised here against a stand-in rather than losing its only coverage along with its member.
@pytest.mark.parametrize("ticker", ["SPY", "QQQ", "NVDA", "META"])
def test_the_conditional_rule_keeps_a_liquid_ticker(ticker, monkeypatch):
    monkeypatch.setattr(l0, "SUPPRESS_IF_NON_LIQUID", frozenset({"STANDIN_TYPE"}))
    d = _decide("STANDIN_TYPE", ticker=ticker)
    assert d["rule"] == l0.RULE_SUPPRESS_IF_NON_LIQUID
    assert d["is_liquid"] is True
    assert d["would_suppress"] is False


@pytest.mark.parametrize("ticker", ["AON", "VRTX", "RIVN", "DOCU"])
def test_the_conditional_rule_suppresses_a_non_liquid_ticker(ticker, monkeypatch):
    monkeypatch.setattr(l0, "SUPPRESS_IF_NON_LIQUID", frozenset({"STANDIN_TYPE"}))
    d = _decide("STANDIN_TYPE", ticker=ticker)
    assert d["is_liquid"] is False
    assert d["would_suppress"] is True


def test_the_conditional_set_is_now_empty_and_that_is_deliberate():
    assert l0.SUPPRESS_IF_NON_LIQUID == frozenset()


# --- keepers untouched --------------------------------------------------
# R-IV.945(c) RETIRED FIVE OF THE ORIGINAL NINE from this list: GOLDEN_TOUCH (MIDAS),
# TRAPPED_SHORTS (HECTOR), TWO_CLOSE_VOLUME (PERSEPHONE), SELL_RIP_EMA (ACHILLES) and
# ARTEMIS_SHORT. They are asserted as suppressed in test_the_r945_retirements_are_suppressed
# below. What remains here is what is genuinely still kept.
@pytest.mark.parametrize("st", [
    "APIS_CALL", "FOOTPRINT_LONG", "KODIAK_CALL", "CIRCES_STEW", "SOME_UNKNOWN_TYPE",
])
def test_keepers_never_suppressed(st):
    # keepers must never be flagged would_suppress, regardless of ticker liquidity
    for ticker in ("AON", "SPY", None):
        d = _decide(st, ticker=ticker)
        assert d["rule"] == l0.RULE_KEEP
        assert d["would_suppress"] is False


@pytest.mark.parametrize("st", [
    "GOLDEN_TOUCH",          # MIDAS
    "SELL_RIP_EMA",          # ACHILLES
    "SELL_RIP_VWAP",         # ACHILLES
    "SELL_RIP_EARLY",        # ACHILLES
    "RESISTANCE_REJECTION",  # SISYPHUS, promoted from the conditional set
    "ARTEMIS_SHORT",         # a RUN-OFF: still stored and graded, surface withdrawn
    "TRAPPED_SHORTS",        # HECTOR
    "TWO_CLOSE_VOLUME",      # PERSEPHONE
])
def test_the_r945_retirements_are_suppressed(st):
    """R-IV.945(c)1 and (c)2. On BOTH asset classes and whatever the ticker's liquidity: this
    set is keyed on signal_type alone and is consulted before any ticker test, which is what
    makes (c)2's "both asset classes" true by construction rather than by a second entry."""
    for ticker in ("AON", "SPY", "BTC-USD", "ETH-USD", None):
        d = _decide(st, ticker=ticker)
        assert d["rule"] == l0.RULE_SUPPRESS, (st, ticker, d)
        assert d["would_suppress"] is True, (st, ticker, d)


def test_suppression_is_a_SURFACE_verdict_and_not_a_kill():
    """The property that makes this the right instrument for a run-off, and the reason
    ARTEMIS_SHORT can be listed at all: the module's own contract is that suppressed rows are
    still persisted and still graded, and only actionable READ surfaces exclude them."""
    import inspect

    doc = inspect.getsource(l0)
    assert "actionable READ surfaces exclude" in doc
    # the gate itself never drops: should_divert is the only thing that could, and it is gated
    assert l0.should_divert({"would_suppress": False}) is False


# --- robustness ---------------------------------------------------------
def test_blank_signal_type_is_kept():
    d = _decide("", ticker="SPY")
    assert d["would_suppress"] is False
    d2 = l0.evaluate_l0_gate({})
    assert d2["would_suppress"] is False


def test_whitespace_signal_type_normalized():
    d = _decide("  HOLY_GRAIL_1H  ", ticker="AAPL")
    assert d["would_suppress"] is True


def test_does_not_mutate_input():
    sig = {"signal_type": "HOLY_GRAIL_1H", "ticker": "AAPL"}
    before = dict(sig)
    l0.evaluate_l0_gate(sig)
    assert sig == before


def test_decision_shape():
    d = _decide("HOLY_GRAIL_1H", ticker="AAPL")
    assert set(d) == {"v", "mode", "signal_type", "rule", "would_suppress", "is_liquid", "reason"}
    assert d["v"] == l0.L0_SHADOW_VERSION


# --- ENFORCE is the default (2026-07-03 flip); L0_ENFORCE=false is rollback ----
def test_default_mode_is_enforce(monkeypatch):
    monkeypatch.delenv("L0_ENFORCE", raising=False)
    importlib.reload(l0)
    assert l0._enforce_enabled() is True
    d = l0.evaluate_l0_gate({"signal_type": "HOLY_GRAIL_1H", "ticker": "AAPL"})
    assert d["mode"] == "enforce"
    # should_divert is True under the default-enforce for a would-suppress decision
    assert l0.should_divert(d) is True


def test_rollback_to_shadow_via_explicit_false(monkeypatch):
    # The single-flag rollback: L0_ENFORCE=false returns to shadow.
    monkeypatch.setenv("L0_ENFORCE", "false")
    importlib.reload(l0)
    assert l0._enforce_enabled() is False
    d = l0.evaluate_l0_gate({"signal_type": "HOLY_GRAIL_1H", "ticker": "AAPL"})
    assert d["mode"] == "shadow"
    assert l0.should_divert(d) is False
    monkeypatch.delenv("L0_ENFORCE", raising=False)
    importlib.reload(l0)


def test_enforce_flag_parsing(monkeypatch):
    # Enforce-y values AND empty/unset (Railway '' -> default -> ENFORCE).
    for val in ("true", "1", "YES", "on", ""):
        monkeypatch.setenv("L0_ENFORCE", val)
        importlib.reload(l0)
        assert l0._enforce_enabled() is True
    # Explicit rollback values -> shadow.
    for val in ("false", "0", "no", "off"):
        monkeypatch.setenv("L0_ENFORCE", val)
        importlib.reload(l0)
        assert l0._enforce_enabled() is False
    monkeypatch.delenv("L0_ENFORCE", raising=False)
    importlib.reload(l0)


def test_should_divert_true_only_under_enforce(monkeypatch):
    monkeypatch.setenv("L0_ENFORCE", "true")
    importlib.reload(l0)
    d = l0.evaluate_l0_gate({"signal_type": "HOLY_GRAIL_1H", "ticker": "AAPL"})
    assert l0.should_divert(d) is True
    # APIS_CALL, not GOLDEN_TOUCH: R-IV.945(c)1 retired MIDAS, so the old "keeper" here is now
    # suppressed and the test would have asserted the opposite of the rule it is about.
    keeper = l0.evaluate_l0_gate({"signal_type": "APIS_CALL", "ticker": "AAPL"})
    assert l0.should_divert(keeper) is False
    monkeypatch.delenv("L0_ENFORCE", raising=False)
    importlib.reload(l0)


# --- a retirement must reach rows that ALREADY EXIST ---------------------

def test_the_filter_excludes_a_retired_type_even_with_a_KEEP_tag():
    """MEASURED, not reasoned. After R-IV.945(c) added eight types, all eight STILL surfaced on
    /api/trade-ideas: 7,381 active rows carried no suppress tag -- pre-gate rows COALESCE to
    keep by design -- and `expires_at` was NULL for four of the types, so those rows would have
    surfaced for ever. A retirement that only reaches rows created after it is not a
    retirement."""
    rows = [
        {"signal_type": "SELL_RIP_EMA", "triggering_factors": {}},
        {"signal_type": "TRAPPED_SHORTS", "triggering_factors": None},
        {"signal_type": "ARTEMIS_SHORT",
         "triggering_factors": {"l0_shadow": {"would_suppress": False}}},
        {"signal_type": "CIRCES_STEW", "triggering_factors": {}},
    ]
    kept = l0.l0_enforce_filter_rows(rows)
    assert [r["signal_type"] for r in kept] == ["CIRCES_STEW"]


def test_the_SQL_and_PYTHON_paths_name_the_same_types():
    """The two arms must not disagree about one row -- a surface that hid a row the other
    showed would be worse than either being wrong alone."""
    where = l0.l0_enforce_where_clause()
    for t in l0.SUPPRESS_ALWAYS:
        assert "'%s'" % t in where, t
        assert l0._row_would_suppress({"signal_type": t}) is True, t


def test_the_tag_arm_SURVIVES_so_a_drifted_type_stays_suppressed():
    """THE CONTROL for the change. The tag is kept as the first arm because `signal_type` can
    DRIFT after gate evaluation -- a Holy_Grail row relabelled APIS_CALL keeps its correct
    SUPPRESS tag. The new arm may only ever exclude MORE, never less."""
    drifted = {"signal_type": "APIS_CALL",          # a live type today...
               "triggering_factors": {"l0_shadow": {"would_suppress": True}}}  # ...tagged then
    assert l0._row_would_suppress(drifted) is True
    assert l0.l0_enforce_filter_rows([drifted]) == []


def test_the_type_list_in_the_sql_is_built_from_the_one_author():
    """Not a second hand-maintained list: it is generated from SUPPRESS_ALWAYS, so a retirement
    cannot be half-applied, and every literal is asserted to be a bare identifier."""
    where = l0.l0_enforce_where_clause()
    # Count inside the NOT IN clause only. The predicate has its own literals
    # ('l0_shadow', 'would_suppress', '') and an earlier version of this test counted every
    # quote in the fragment, which simply measured the wrong thing.
    clause = where.split("NOT IN (", 1)[1].rstrip(")")
    assert clause.count("'") == 2 * len(l0.SUPPRESS_ALWAYS), clause
    assert sorted(x.strip().strip("'") for x in clause.split(",")) == sorted(l0.SUPPRESS_ALWAYS)
    for t in l0.SUPPRESS_ALWAYS:
        assert t.replace("_", "").isalnum(), t
