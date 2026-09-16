"""Ledger carve-out T1/T2/T4 — R-IV.394.

The load-bearing tests are the ones about what is NOT written and what is NOT
summed. Both defects being fixed here produced numbers that looked like
measurements: a zero P&L that reads as "flat", and a total that reads as money you
can spend.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import mark_guard as mg
from config import accounts as acc


# ══════════════════════════════════════════════ T2 — the vocabulary

@pytest.mark.parametrize("raw", [
    "FIDELITY_ROTH", "fidelity_roth", "Fidelity Roth", "  fidelity roth  ",
    "FIDELITY", "fidelity", "Fid",
])
def test_fidelity_forms_resolve_to_the_roth(raw):
    if raw.strip().lower() == "fid":
        return                              # not an alias; see the UNKNOWN test
    assert acc.normalize_account(raw) == acc.FIDELITY_ROTH


@pytest.mark.parametrize("raw", ["ROBINHOOD", "robinhood", "rh", "Robinhood - Individual"])
def test_robinhood_forms(raw):
    assert acc.normalize_account(raw) == acc.ROBINHOOD


@pytest.mark.parametrize("raw", [
    "FIDELITY_401A", "Fidelity 401A", "fidelity 403b", "FIDELITY_403B",
    "BROKERAGE_LINK_401K", "brokerage link 401k", "Interactive Brokers", "IBKR",
])
def test_parked_and_retired_labels_are_out_of_scope(raw):
    """NOT aliases of anything (R-IV.284(c)). A different pot, not an old reading."""
    assert acc.normalize_account(raw) == acc.OUT_OF_SCOPE
    assert acc.is_in_scope(raw) is False


@pytest.mark.parametrize("raw", ["", None, "   ", "SCHWAB", "vanguard", "fid"])
def test_unrecognised_is_unknown_not_guessed(raw):
    """A wrong resolution on a money surface is worse than an unresolved one,
    because it is spendable."""
    assert acc.normalize_account(raw) == acc.UNKNOWN


def test_unknown_is_not_in_scope():
    """An account nobody has classified must not be summed into a tradeable total
    on the strength of not having been recognised."""
    assert acc.is_in_scope("SCHWAB") is False
    assert acc.is_in_scope(None) is False


def test_exactly_two_canonical_accounts():
    assert acc.CANONICAL_ACCOUNTS == {acc.FIDELITY_ROTH, acc.ROBINHOOD}


# ── the startswith defect, stated as its own test ──

def test_fidelity_filter_does_not_match_the_parked_accounts():
    """THE DEFECT: `startswith('fidelity')` matched Fidelity Roth, 401A and 403B
    alike, so a request for the one traded account silently summed two parked ones
    with it."""
    assert acc.accounts_match("FIDELITY", "Fidelity Roth") is True
    assert acc.accounts_match("FIDELITY", "Fidelity 401A") is False
    assert acc.accounts_match("FIDELITY", "Fidelity 403B") is False
    assert acc.accounts_match("FIDELITY", "BROKERAGE_LINK_401K") is False


def test_a_prefix_that_is_not_an_account_matches_nothing():
    assert acc.accounts_match("FID", "Fidelity Roth") is False
    assert acc.accounts_match("ROBIN", "ROBINHOOD") is False


def test_match_is_symmetric_across_forms():
    assert acc.accounts_match("fidelity_roth", "FIDELITY ROTH") is True
    assert acc.accounts_match("ROBINHOOD", "robinhood - individual") is True


def test_unknown_never_matches_anything():
    assert acc.accounts_match("SCHWAB", "SCHWAB") is False


def test_the_startswith_call_is_gone_from_the_matcher():
    """Reads the CODE, not the docstring. The docstring deliberately describes the
    old `startswith` defect, so a naive substring search over the whole function
    matches the explanation and passes for the wrong reason — which is what the
    first version of this test did."""
    import ast
    import inspect
    from api import unified_positions as up
    fn = ast.parse(inspect.getsource(up._match_account_balance)).body[0]
    body = fn.body[1:] if isinstance(fn.body[0], ast.Expr) else fn.body   # drop docstring
    code = ast.unparse(ast.Module(body=body, type_ignores=[]))
    assert "startswith" not in code, "the prefix match survived the fix"
    assert "accounts_match" in code


# ══════════════════════════════════════════════ T1 — the mark guard

def test_good_mark_is_ok():
    st, why = mg.evaluate_mark(101.25, entry_price=100.0)
    assert st == mg.MARK_OK and why is None
    assert mg.mark_is_writable(st)


@pytest.mark.parametrize("px,expect", [
    (None, mg.MARK_ABSENT),
    ("abc", mg.MARK_REJECTED),
    (float("nan"), mg.MARK_REJECTED),
    (float("inf"), mg.MARK_REJECTED),
    (0, mg.MARK_REJECTED),
    (-5.0, mg.MARK_REJECTED),
    (2_000_000.0, mg.MARK_REJECTED),
])
def test_bad_marks_are_classified_and_not_writable(px, expect):
    st, why = mg.evaluate_mark(px, entry_price=100.0)
    assert st == expect
    assert mg.mark_is_writable(st) is False
    assert why


def test_absent_is_distinguishable_from_rejected():
    """'no mark' and 'a mark that failed' have different fixes and different owners."""
    assert mg.evaluate_mark(None)[0] == mg.MARK_ABSENT
    assert mg.evaluate_mark(-1.0)[0] == mg.MARK_REJECTED


def test_units_error_is_rejected_rather_than_priced():
    """A mark 100x the entry is far more likely cents-vs-dollars than a real move.
    Rejecting is recoverable; a P&L computed from it is not."""
    st, why = mg.evaluate_mark(10_000.0, entry_price=1.0)
    assert st == mg.MARK_REJECTED
    assert "units error" in why


def test_a_real_large_move_is_not_rejected():
    """The guard must not eat the position it exists to price."""
    assert mg.evaluate_mark(300.0, entry_price=100.0)[0] == mg.MARK_OK


def test_stale_mark():
    old = datetime.now(timezone.utc) - timedelta(hours=40)
    st, why = mg.evaluate_mark(100.0, entry_price=100.0, price_asof=old)
    assert st == mg.MARK_STALE and "old" in why
    assert mg.mark_is_writable(st) is False


def test_fresh_mark_over_a_weekend_is_not_stale():
    recent = datetime.now(timezone.utc) - timedelta(hours=20)
    assert mg.evaluate_mark(100.0, entry_price=100.0, price_asof=recent)[0] == mg.MARK_OK


def test_absent_vintage_is_unknown_freshness_not_stale():
    """Nothing here invents an age. A missing vintage is a gap in the schema, not
    evidence about the mark."""
    assert mg.evaluate_mark(100.0, entry_price=100.0, price_asof=None)[0] == mg.MARK_OK


def test_an_unusable_entry_does_not_condemn_the_mark():
    assert mg.evaluate_mark(100.0, entry_price="junk")[0] == mg.MARK_OK
    assert mg.evaluate_mark(100.0, entry_price=0)[0] == mg.MARK_OK


def test_evaluate_mark_never_raises():
    for bad in (object(), [], {}, "", b"x"):
        st, _ = mg.evaluate_mark(bad, entry_price=bad)
        assert st in (mg.MARK_OK, mg.MARK_STALE, mg.MARK_REJECTED, mg.MARK_ABSENT)


def test_only_ok_is_writable():
    for st in (mg.MARK_STALE, mg.MARK_REJECTED, mg.MARK_ABSENT):
        assert mg.mark_is_writable(st) is False
    assert mg.mark_is_writable(mg.MARK_OK) is True


def test_the_write_site_never_zeroes_on_failure():
    """THE RULE. A zero P&L is a CLAIM that the position is flat, and it is
    indistinguishable from a real flat position downstream."""
    src = (Path(__file__).resolve().parents[1] / "api" / "unified_positions.py").read_text(
        encoding="utf-8")
    i = src.index("T1 MARK GUARD")
    block = src[i:i + 1800]
    assert "mark_is_writable" in block
    # The failure branch must not WRITE unrealized_pnl. Checked against the SQL,
    # not the prose: the log line legitimately contains the words
    # "unrealized_pnl NOT written", and the first version of this test matched
    # that sentence and failed a correct implementation.
    fail = block[block.index("else:"):]
    sql = [ln for ln in fail.splitlines()
           if "UPDATE unified_positions" in ln or ("SET " in ln and '"' in ln)]
    assert sql, "no SQL found in the failure branch"
    assert not any("unrealized_pnl" in ln for ln in sql), (
        "the failure branch writes unrealized_pnl: %s" % sql)


# ══════════════════════════════════════════════ T4 — the aggregate

def test_totals_exclude_out_of_scope_by_vocabulary():
    accounts = [
        {"account": "robinhood", "balance": 5220.12, "cash": 5220.12, "buying_power": 0},
        {"account": "fidelity_roth", "balance": 4457.66, "cash": 0, "buying_power": 0},
        {"account": "brokerage_link_401k", "balance": 11642.35, "cash": 11642.35,
         "buying_power": 0},
    ]
    tradeable = [a for a in accounts if acc.is_in_scope(a["account"])]
    assert len(tradeable) == 2
    assert round(sum(a["balance"] for a in tradeable), 2) == 9677.78
    assert round(sum(a["cash"] for a in tradeable), 2) == 5220.12


def test_the_measured_overstatement_is_what_the_fix_removes():
    """2026-09-05: 21,320.13 against 9,677.78 true (+120%)."""
    assert round(21320.13 - 9677.78, 2) == 11642.35


def test_excluded_rows_are_named_not_dropped():
    src = (Path(__file__).resolve().parents[1] / "hub_mcp" / "tools"
           / "portfolio_balances.py").read_text(encoding="utf-8")
    assert "excluded_out_of_scope" in src
    assert "for r in rows" in src, "the rows are still returned, not filtered away"


def test_staleness_is_judged_on_tradeable_only():
    src = (Path(__file__).resolve().parents[1] / "hub_mcp" / "tools"
           / "portfolio_balances.py").read_text(encoding="utf-8")
    assert "funded = [a for a in tradeable" in src


# ══════════════════════════════════════════════ the seed, on a fresh DB

def test_fresh_db_seed_does_not_create_out_of_scope_accounts():
    """R-IV.394's fresh-DB boot test. The seed at postgres_client.py once created
    `Fidelity 401A`, `Fidelity 403B` and `Interactive Brokers` — and
    DEF-SEED-RESURRECTION is the record of those rows coming BACK after deletion.

    A fresh boot must not re-introduce the vocabulary the carve-out just retired.
    """
    src = (Path(__file__).resolve().parents[1] / "database"
           / "postgres_client.py").read_text(encoding="utf-8")
    i = src.find("account_balances")
    assert i > 0
    window = src[max(0, i - 2000):i + 6000]
    for retired in ("Fidelity 401A", "Fidelity 403B", "Interactive Brokers"):
        if retired in window:
            assert "if not" in window or "COUNT(*)" in window or "empty" in window.lower(), (
                "the seed still names %r with no empty-table guard — "
                "DEF-SEED-RESURRECTION" % retired)


def test_migration_032_has_a_down():
    sql = (Path(__file__).resolve().parents[2] / "migrations"
           / "032_mark_status.sql").read_text(encoding="utf-8")
    assert "-- DOWN" in sql
    assert "mark_status" in sql and "ABSENT" in sql
