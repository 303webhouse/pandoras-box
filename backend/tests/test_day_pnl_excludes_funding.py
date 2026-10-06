"""Day P&L moves with prices, not with money walking in the door — R-IV.644(c).

THE DEFECT. `/api/portfolio/pnl` differenced two BALANCES: the sum of
`account_balances.balance` now, against the latest `balance_snapshots.balance` on or before
the comparison date. A balance rises for four different reasons and only one of them is
performance, so a deposit, a transfer and a correction to a past entry each read as that
day's profit.

`cash_ledger` has said so since R-IV.539(d), in its own module docstring — *"money walking in
the door is not a gain, and an account value that grew by a deposit has not performed"* — and
this computation never asked it. The rule existed and the P&L path ignored it, which is the
single-author failure in its usual shape.

IT WAS ABOUT TO FIRE THREE TIMES AT ONCE. CC-POSITIONS is booking the 401(a)'s funding and
rebuilding the Roth's past entries including the 403(b) transfer (R-IV.642) — a deposit, a
transfer and a correction, in one window.
"""

import ast
import io
import os

import pytest

from services.cash_ledger import (ADJUSTMENT, ANCHOR, DIVIDEND, EXTERNAL_TYPES, INTEREST,
                                  NOT_PERFORMANCE_TYPES, TRADE_CREDIT, TRADE_DEBIT,
                                  TRANSFER_IN, TRANSFER_OUT,
                                  moves_balance_without_performing)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _code(rel):
    """Live code only: docstrings and comments both removed, spacing preserved."""
    import tokenize

    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    lines = src.splitlines(keepends=True)
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                continue
            r, c0, c1 = tok.start[0] - 1, tok.start[1], tok.end[1]
            lines[r] = lines[r][:c0] + " " * (c1 - c0) + lines[r][c1:]
    except (tokenize.TokenError, IndentationError):
        pass
    return "".join(lines)


def _pnl(opening, closing, flows):
    """The computation under test, in the shape `calc_pnl` applies it.

    `closing` is the balance now, `opening` the snapshot's, `flows` the window's events.
    """
    funded = round(sum(float(f["amount"]) for f in flows
                       if moves_balance_without_performing(f)), 2)
    dollar = round(closing - opening - funded, 2)
    base = opening + funded
    pct = round((dollar / base) * 100, 2) if base else None
    return dollar, pct, funded


# ─────────────────────── the three controls the ruling asks for

class TestTheThreeThingsThatMustNotMoveIt:

    def test_a_deposit_alone_is_not_a_days_profit(self):
        """CONTROL 1. $2,000 walks in, no price moves: the day is FLAT."""
        dollar, pct, funded = _pnl(10_000.00, 12_000.00,
                                   [{"flow_type": "DEPOSIT", "amount": 2_000.00}])
        assert dollar == 0.0
        assert pct == 0.0
        assert funded == 2_000.00, "and the funding is reported, not hidden"

    def test_a_transfer_in_is_not_a_days_profit(self):
        """CONTROL 2. The 403(b) transfer into the Roth (R-IV.642)."""
        dollar, _, funded = _pnl(8_842.09, 9_408.82,
                                 [{"flow_type": "TRANSFER_IN", "amount": 566.73}])
        assert dollar == 0.0
        assert funded == 566.73

    def test_a_correction_to_past_entries_is_not_a_days_profit(self):
        """CONTROL 3. An ADJUSTMENT restates history. Even when it corrects a mis-recorded
        trade result — which WAS performance once — it did not happen today, so crediting
        it to today is wrong either way."""
        dollar, _, funded = _pnl(10_000.00, 9_880.00,
                                 [{"flow_type": ADJUSTMENT, "amount": -120.00}])
        assert dollar == 0.0
        assert funded == -120.00

    def test_all_three_in_one_window(self):
        """Which is the case actually arriving: POSITIONS is doing all three at once."""
        flows = [{"flow_type": "DEPOSIT", "amount": 2_000.00},
                 {"flow_type": TRANSFER_IN, "amount": 566.73},
                 {"flow_type": ADJUSTMENT, "amount": -120.00}]
        dollar, _, funded = _pnl(10_000.00, 12_446.73, flows)
        assert dollar == 0.0
        assert funded == 2_446.73

    def test_a_withdrawal_is_not_a_days_loss(self):
        """The mirror, and it matters as much: a withdrawal would otherwise read as a loss
        and the principal would hunt for a trade that never happened."""
        dollar, _, funded = _pnl(10_000.00, 9_500.00,
                                 [{"flow_type": "WITHDRAWAL", "amount": -500.00}])
        assert dollar == 0.0
        assert funded == -500.00


# ─────────────────────── POSITIVE CONTROLS: it must still see real movement

class TestItStillReportsRealPerformance:

    def test_a_price_move_with_no_flows_reads_in_full(self):
        """The test that would catch over-correction: subtract too much and the day reads
        flat when the book genuinely moved."""
        dollar, pct, funded = _pnl(10_000.00, 10_250.00, [])
        assert dollar == 250.00
        assert pct == 2.5
        assert funded == 0.0

    def test_a_price_move_alongside_a_deposit_reports_only_the_move(self):
        """$2,000 in AND $250 earned: the day is 250, not 2,250 and not 0."""
        dollar, _, funded = _pnl(10_000.00, 12_250.00,
                                 [{"flow_type": "DEPOSIT", "amount": 2_000.00}])
        assert dollar == 250.00
        assert funded == 2_000.00

    def test_a_dividend_is_real_return_and_is_kept(self):
        """A dividend is earned by holding. Excluding it would UNDER-report the day, and
        `cash_ledger` types income apart from external flow precisely so this stays in."""
        dollar, _, funded = _pnl(10_000.00, 10_000.64,
                                 [{"flow_type": DIVIDEND, "amount": 0.64}])
        assert dollar == 0.64
        assert funded == 0.0

    def test_a_trade_pair_nets_out_rather_than_being_subtracted(self):
        """TRADE_DEBIT and TRADE_CREDIT move cash and securities in opposite directions and
        net to zero in a BALANCE. Subtracting them would double-count the trade."""
        flows = [{"flow_type": TRADE_DEBIT, "amount": -1_595.35},
                 {"flow_type": TRADE_CREDIT, "amount": 3_014.00}]
        dollar, _, funded = _pnl(10_000.00, 10_120.00, flows)
        assert funded == 0.0
        assert dollar == 120.00

    def test_a_real_loss_is_still_a_loss(self):
        dollar, pct, _ = _pnl(10_000.00, 9_750.00, [])
        assert dollar == -250.00 and pct == -2.5


# ─────────────────────── the percentage base

def test_the_denominator_carries_the_funding_too():
    """Money that arrived mid-window was capital for part of it. Dividing a flow-adjusted
    gain by the UN-adjusted opening balance overstates the percentage on exactly the days
    funding lands — $250 on 10,000 is 2.5%, but with 2,000 added the capital at risk was
    12,000 and the honest figure is 2.08%."""
    dollar, pct, _ = _pnl(10_000.00, 12_250.00,
                          [{"flow_type": "DEPOSIT", "amount": 2_000.00}])
    assert dollar == 250.00
    assert pct == round(250.0 / 12_000.0 * 100, 2) == 2.08


def test_a_zero_base_yields_no_percentage_rather_than_a_crash():
    dollar, pct, _ = _pnl(0.0, 0.0, [])
    assert dollar == 0.0 and pct is None


# ─────────────────────── the input was frozen, and the basis must match

class TestTheBasisOfTheComparison:
    """R-IV.647(b). The funding exclusion above was correct and was operating on a figure
    that could not move. `/pnl` read `account_balances.balance`, whose ONLY writer is the
    manual POST /balances route -- nothing automatic updates it.

    MEASURED 2026-10-05: FIDELITY_ROTH 8,842.09 and ROBINHOOD 835.69 in EVERY snapshot from
    09-24 to 10-05. Eleven identical days. P&L differences two snapshots, and the difference
    of a constant is zero, so day, weekly and monthly had all read 0.00 for eleven days --
    reported as flat, which is not the same as quiet.

    Both sides now read the DERIVED value, and the comparison refuses to cross bases: the
    600 pre-existing snapshot rows are stored-basis, and differencing today's derived value
    against one of them would book the whole gap between the bases as a day's gain. Measured
    on the switch date that gap was +1,129.83.
    """

    def test_the_current_total_comes_from_the_balances_service(self):
        code = _code("api/portfolio.py")
        assert "get_account_balances" in code
        assert 'SELECT account_name, balance FROM account_balances' not in code

    def test_the_comparison_requires_a_derived_basis_on_both_sides(self):
        code = _code("api/portfolio.py")
        assert "basis = 'derived'" in code
        assert "partial IS NOT TRUE" in code

    def test_the_snapshot_writes_the_derived_value_and_records_its_basis(self):
        """A snapshot of the frozen figure is what made the series uncomparable."""
        code = _code("api/portfolio.py")
        i = code.index("async def snapshot_account_balances")
        block = code[i:i + 2600]
        assert "get_account_balances" in block
        assert "'derived'" in block
        assert "balance_partial" in block

    def test_an_account_with_no_derived_value_is_not_snapshotted(self):
        """A row here would be a number standing in for one that does not exist, and the
        P&L would difference it."""
        code = _code("api/portfolio.py")
        i = code.index("async def snapshot_account_balances")
        block = code[i:i + 2600]
        assert "skipped.append" in block

    def test_the_payload_names_its_basis_and_what_is_missing(self):
        """A figure whose basis a reader cannot see is a figure they cannot check."""
        code = _code("api/portfolio.py")
        assert '"basis"' in code
        assert '"accounts_partial"' in code
        assert '"accounts_unavailable"' in code
        assert '"comparison_rule"' in code


# ─────────────────────── the vocabulary, and who owns it

class TestTheVocabularyHasOneAuthor:

    def test_the_rule_lives_in_cash_ledger_not_in_the_endpoint(self):
        """The endpoint asks; it does not classify. A second list of flow types beside the
        first is the failure this whole module exists to avoid."""
        code = _code("api/portfolio.py")
        assert "moves_balance_without_performing" in code
        # Scoped to the P&L path. A whole-file sweep failed for the wrong reason: the
        # cash-flow WRITE routes in the same module legitimately name flow types, because
        # writing one is their job. What must not classify is the computation.
        i = code.index("def funding_since(after, names):")
        j = code.index("daily_dollar, daily_pct = calc_pnl", i)
        pnl_path = code[i:j]
        for t in ("TRANSFER_IN", "DEPOSIT", "ADJUSTMENT", "OPENING_BALANCE", "DIVIDEND"):
            assert t not in pnl_path, f"{t} is retyped in the P&L computation"

    def test_what_is_excluded(self):
        assert NOT_PERFORMANCE_TYPES == EXTERNAL_TYPES | {ANCHOR, ADJUSTMENT}
        for t in (TRANSFER_IN, TRANSFER_OUT, ANCHOR, ADJUSTMENT):
            assert moves_balance_without_performing({"flow_type": t, "amount": 1})

    def test_what_is_kept(self):
        for t in (DIVIDEND, INTEREST, TRADE_DEBIT, TRADE_CREDIT):
            assert not moves_balance_without_performing({"flow_type": t, "amount": 1})

    def test_ach_is_read_by_its_sign(self):
        """`ACH` names a MECHANISM, not a direction — 22 of the rows — and the same word
        covers money arriving and money leaving. Both are external."""
        assert moves_balance_without_performing({"flow_type": "ACH", "amount": 500})
        assert moves_balance_without_performing({"flow_type": "ACH", "amount": -500})

    def test_an_unknown_type_is_treated_as_NOT_performance(self):
        """The safe direction. Under-reporting a gain is a visible disappointment;
        crediting an unknown balance movement as profit is an invisible lie."""
        assert moves_balance_without_performing({"flow_type": "SOMETHING_NEW", "amount": 99})
        assert moves_balance_without_performing({"flow_type": None, "amount": 99})

    def test_the_funding_is_reported_beside_the_figure(self):
        """A day that reads flat after $2,000 walked in is a different fact from a day that
        was flat, and the reader must be able to tell them apart."""
        code = _code("api/portfolio.py")
        assert '"funding_excluded"' in code

    def test_the_window_is_scoped_to_the_same_accounts_as_the_comparison(self):
        """Otherwise an account excluded from both balances would still have its funding
        removed, turning a correct zero into a phantom loss."""
        code = _code("api/portfolio.py")
        i = code.index("def funding_since(after, names):")
        window = code[i:i + 900]
        assert "names is not None and r[\"account_name\"] not in names" in window
