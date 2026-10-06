"""The third account — R-IV.632(c).

The principal converted his untracked 401(a) into a SECOND Fidelity BrokerageLink account and
started trading in it. Three accounts are now tracked separately, and every position, touches
block and analytics row must carry which one — labelled and sortable without inferring
(R-IV.633).

WHAT THE CENSUS FOUND, and it was not "the account is missing":

  * **It was already half-registered, contradictorily.** `models/accounts.py` has had
    FIDELITY_401A in CANONICAL_ACCOUNTS since R-IV.445(a), so it was a legal WRITE target for
    positions — while `config/accounts.py` listed `fidelity_401a` in _OUT_OF_SCOPE_LABELS, so
    every money aggregate excluded it. Writable and unsummable at the same time.
  * **A prefix match silently merged the two Fidelity accounts.** `/v2/positions?account=
    FIDELITY` ran `account LIKE 'FIDELITY%'`, which with a second Fidelity account returns
    BOTH, mixed, under one total. config/accounts.py's own note says a prefix is not a
    classification; this was the surface still doing it.
  * **The loss alert was one hard-coded account.** `ACCOUNT = "FIDELITY_ROTH"` as a module
    constant, so the new account's losses were invisible to it, and a 2% threshold computed
    from the Roth's value is not the new account's threshold.
  * **The startup seed spoke the retired vocabulary.** Empty-table guarded (DEF-SEED-
    RESURRECTION), so it only fires on an empty table — and on that day it would have
    recreated 'Fidelity 401A' and 'Fidelity 403B' as display-style rows, reintroducing the
    mess R-IV.394 cleaned up.
"""

import ast
import io
import os

import pytest

from config.accounts import OUT_OF_SCOPE, UNKNOWN
from config.accounts import CANONICAL_ACCOUNTS as SCOPE_CANONICAL
from config.accounts import is_in_scope
from config.accounts import normalize_account as scope_normalize
from models.accounts import (CANONICAL_ACCOUNTS, FIDELITY_401A, FIDELITY_ROTH,
                             PROVISIONAL_NAMES, ROBINHOOD, account_envelope, display_name,
                             is_fidelity_name, normalize_account)

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


# ─────────────────────── (c)1 registered, once

class TestRegistered:

    def test_three_accounts_and_the_key_is_as_the_ruling_names_it(self):
        assert FIDELITY_401A == "FIDELITY_401A"
        assert CANONICAL_ACCOUNTS == (ROBINHOOD, FIDELITY_ROTH, FIDELITY_401A)

    def test_the_display_name_is_as_the_ruling_names_it(self):
        assert display_name(FIDELITY_401A) == "FID 401A"

    def test_the_name_is_declared_provisional(self):
        """R-IV.632(c)1 says Trade Analysis may rename it. One string in one dict, so a
        rename is one edit — and declared, so it is a known operation not a discovery."""
        assert FIDELITY_401A in PROVISIONAL_NAMES

    def test_a_key_is_not_a_label(self):
        """`FIDELITY_401A.replace("_"," ").title()` gives "Fidelity 401A", which is not what
        the account is called -- the principal calls it "FID 401A" (R-IV.649(a)). Every
        surface deriving a label from the key would get it subtly differently, and none of
        them would get THIS."""
        assert display_name(FIDELITY_401A) != FIDELITY_401A.replace("_", " ").title()
        assert display_name(FIDELITY_401A) == "FID 401A"

    def test_only_the_exact_key_or_the_number_resolves(self):
        """AMENDED R-IV.638(b)1/2. The first pass accepted 'fidelity 401a' and
        'FIDELITY 401A' as well — and those name the PARKED money, which collapses to the
        same normalised string as the traded key. The account number is the identity now."""
        assert normalize_account("FIDELITY_401A") == FIDELITY_401A
        assert normalize_account("653641836") == FIDELITY_401A
        assert normalize_account("fidelity 401a") is None   # a name no longer routes


# ─────────────────────── the two registries can no longer disagree

class TestOneRegistry:

    def test_the_scope_module_imports_the_canonical_set(self):
        """THE DEFECT. Two modules each retyped the set, and they disagreed about this very
        account: writable per models/accounts.py, OUT_OF_SCOPE per config/accounts.py."""
        assert SCOPE_CANONICAL == frozenset(CANONICAL_ACCOUNTS)
        code = _code("config/accounts.py")
        assert "from models.accounts import CANONICAL_ACCOUNTS as _CANONICAL_TUPLE" in code
        assert 'CANONICAL_ACCOUNTS = frozenset({FIDELITY_ROTH, ROBINHOOD})' not in code

    def test_the_account_is_in_scope_for_money(self):
        """It was classified as parked mutual-fund money. It is traded now, so the
        classification is false rather than stale — a scope class is re-decided, not
        refreshed, and a ruling has re-decided it.

        AMENDED R-IV.638(b)2: the EXACT key only. 'Fidelity 401(a)' as a display string is
        not a scope input — the parked history collapses to the same normalised key, and no
        name-based rule can separate the two pots."""
        assert is_in_scope(FIDELITY_401A)
        assert scope_normalize(FIDELITY_401A) == FIDELITY_401A
        assert not is_in_scope("Fidelity 401A")

    @pytest.mark.parametrize("label", ["Fidelity 403B", "fidelity_403b",
                                       "BROKERAGE_LINK_401K", "IBKR"])
    def test_what_stays_out_of_scope(self, label):
        """POSITIVE CONTROL: the change is narrow. The 403(b), the parked SUM under a
        disputed name, and the retired broker are untouched."""
        assert scope_normalize(label) == OUT_OF_SCOPE
        assert not is_in_scope(label)

    def test_an_unclassified_label_is_still_unknown_and_still_out(self):
        assert scope_normalize("some new broker") == UNKNOWN
        assert not is_in_scope("some new broker")


# ─────────────────────── (c)2 whole wherever an account exists

class TestWholeEverywhere:

    def test_the_balances_tool_offers_it(self):
        from hub_mcp.tools.portfolio_balances import _DB_TO_NORMAL, _VALID_ACCOUNTS

        assert "fidelity_401a" in _VALID_ACCOUNTS
        assert _DB_TO_NORMAL["FIDELITY_401A"] == "fidelity_401a"

    def test_the_positions_tool_offers_it_and_round_trips(self):
        from hub_mcp.tools.positions import _VALID_ACCOUNTS, _normalize_account

        assert "fidelity_401a" in _VALID_ACCOUNTS
        assert _normalize_account("fidelity_401a") == FIDELITY_401A

    def test_both_mcp_tools_derive_their_set_rather_than_retyping_it(self):
        """A hand-kept copy here is how the account became writable through the API while
        staying invisible to the tools."""
        for rel in ("hub_mcp/tools/portfolio_balances.py", "hub_mcp/tools/positions.py"):
            code = _code(rel)
            assert "_CANONICAL_TUPLE" in code, rel

    def test_the_loss_alert_watches_it(self):
        from jobs.loss_alert import LOSS_ALERT_ACCOUNTS

        assert FIDELITY_401A in LOSS_ALERT_ACCOUNTS
        assert FIDELITY_ROTH in LOSS_ALERT_ACCOUNTS

    def test_robinhood_is_deliberately_not_watched(self):
        """It was never covered, and it is not the same problem: it holds options, where T1
        and the cost-recovery trigger were reasoned about an account that holds none."""
        from jobs.loss_alert import LOSS_ALERT_ACCOUNTS

        assert ROBINHOOD not in LOSS_ALERT_ACCOUNTS

    def test_the_threshold_is_two_percent_of_that_accounts_own_value(self):
        """A single threshold across accounts is the wrong number for every account but one:
        too large for a smaller book and too small for a larger one, at the same time."""
        from jobs.loss_alert import loss_threshold_usd

        assert loss_threshold_usd(11_319.53) == 226.39
        assert loss_threshold_usd(2_000.00) == 40.0
        assert loss_threshold_usd(None) is None

    def test_the_value_and_the_rows_are_scoped_by_account(self):
        import inspect

        from jobs import loss_alert as la

        for fn in (la.account_value, la._account_value_now, la.evaluate_rows):
            assert "account" in inspect.signature(fn).parameters, fn.__name__

    def test_the_pass_records_each_account_separately(self):
        """One account's failure must not silence another's, and a reader must be able to
        see which accounts actually ran."""
        code = _code("jobs/loss_alert.py")
        assert "for _acct in LOSS_ALERT_ACCOUNTS:" in code
        assert 'result["per_account"] = per_account' in code

    def test_the_seed_speaks_canonical_and_skips_the_untracked(self):
        code = _code("database/postgres_client.py")
        assert "from models.accounts import CANONICAL_ACCOUNTS as _SEED_ACCOUNTS" in code
        # Scoped to the seed block. A whole-file sweep caught something real but SEPARATE
        # -- `cash_flows.account_name DEFAULT 'Robinhood'`, fixed below -- and a window on
        # the wrong occurrence passes or fails for the wrong reason either way.
        i = code.index("_SEED_ACCOUNTS")
        seed = code[i - 200:i + 900]
        for retired in ("'Fidelity 401A'", "'Fidelity 403B'", "'Interactive Brokers'",
                        "'Fidelity Roth'", "'Robinhood'"):
            assert retired not in seed, retired

    def test_the_cash_ledgers_account_column_has_no_default(self):
        """It was `DEFAULT 'Robinhood'` — a FOURTH spelling the live ledger does not use, so
        an insert omitting the column filed money where `WHERE account_name = 'ROBINHOOD'`,
        the loss alert's own query, could never see it. All nine inserters name the column,
        so the default was never a convenience."""
        code = _code("database/postgres_client.py")
        assert "account_name TEXT NOT NULL DEFAULT 'Robinhood'" not in code
        assert "account_name TEXT NOT NULL," in code

    def test_the_seed_leaves_cash_null_rather_than_zero(self):
        """`balance` is NOT NULL so a row must carry a number; `cash` is nullable, and
        unknown cash is not zero cash. Only one of those is true for a new account."""
        code = _code("database/postgres_client.py")
        i = code.index("_SEED_ACCOUNTS")
        window = code[i:i + 900]
        assert "awaiting the first cash entry" in window


# ─────────────────────── (c)3 served, never inferred

class TestServed:

    def test_the_envelope_carries_key_and_name_together(self):
        assert account_envelope(FIDELITY_401A) == {
            "account": "FIDELITY_401A", "account_display": "FID 401A"}

    def test_both_keys_are_present_even_with_no_account(self):
        """A missing key and a null read differently in JSON, and only one is honest about
        an unlabelled row."""
        env = account_envelope(None)
        assert set(env) == {"account", "account_display"}
        assert env == {"account": None, "account_display": None}

    def test_a_disputed_label_gets_no_display_name(self):
        """BROKERAGE_LINK_401K must not be shown to the principal as though it were a name:
        the label is under dispute about which plan it even denotes."""
        assert display_name("BROKERAGE_LINK_401K") is None
        assert account_envelope("BROKERAGE_LINK_401K")["account_display"] is None

    def test_every_position_row_carries_the_display_name(self):
        from api.unified_positions import _row_to_dict

        assert _row_to_dict({"position_id": "X", "account": "FIDELITY_401A"})[
            "account_display"] == "FID 401A"

    def test_a_row_with_no_account_column_gains_no_field(self):
        """Adding the field to a row that was never asked about its account would assert
        the position is unlabelled, which is a different claim from "this query did not
        ask"."""
        from api.unified_positions import _row_to_dict

        assert "account_display" not in _row_to_dict({"position_id": "Z", "ticker": "SPY"})

    def test_a_balance_row_carries_the_display_name_too(self):
        """R-IV.649(b) / R-IV.651(c)3. ABACUS's add form builds its account list from the
        positions AND balances payloads, and renders an account it has no label for as a
        DISABLED option. Positions were the only surface serving a label, so an account with
        no open positions was unselectable — the case of opening the FIRST position in a new
        account, which is what had just happened with the 401(a)."""
        import ast
        import io as _io
        import os as _os
        import tokenize

        src = _io.open(_os.path.join(BACKEND, "services/read_only/balances.py"),
                       encoding="utf-8-sig").read()
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                                 ast.ClassDef)):
                doc = ast.get_docstring(node, clean=False)
                if doc:
                    src = src.replace(doc, "")
        lines = src.splitlines(keepends=True)
        try:
            for tok in tokenize.generate_tokens(_io.StringIO(src).readline):
                if tok.type == tokenize.COMMENT:
                    r, c0, c1 = tok.start[0] - 1, tok.start[1], tok.end[1]
                    lines[r] = lines[r][:c0] + " " * (c1 - c0) + lines[r][c1:]
        except (tokenize.TokenError, IndentationError):
            pass
        code = "".join(lines)
        assert 'd["account_display"] = _account_display(d.get("account_name"))' in code

    def test_the_touches_block_carries_the_account(self):
        from models.position_direction import touches_block

        t = touches_block({"position_id": "P", "structure": "long_call",
                           "account": "FIDELITY_401A"}, "LONG")
        assert t["account"] == "FIDELITY_401A"
        assert t["account_display"] == "FID 401A"

    def test_the_feed_selects_the_column_the_block_serves(self):
        """A column the block reads and the query omits yields a null that looks like an
        unlabelled position rather than a missing SELECT."""
        code = _code("signals/feed_service.py")
        assert "SELECT position_id, ticker, structure, account" in code


# ─────────────────────── the prefix match that merged two accounts

class TestNoPrefixMatching:

    def test_the_positions_filter_no_longer_matches_by_prefix(self):
        """`account LIKE 'FIDELITY%'` matches FIDELITY_ROTH **and** FIDELITY_401A, so a
        request for one silently returned both under one total."""
        code = _code("api/unified_positions.py")
        assert "account LIKE 'FIDELITY%'" not in code

    def test_the_bare_alias_now_resolves_to_nothing_at_all(self):
        """SUPERSEDED R-IV.638(b)3. The first pass kept `FIDELITY` -> FIDELITY_ROTH so a
        long-right caller would not start failing. But with two BrokerageLink accounts the
        kind answer is the dangerous one: it files the new account's money in the old one.
        It resolves to nothing, and the write path refuses it by name with both numbers."""
        assert normalize_account("FIDELITY") is None
        assert is_fidelity_name("FIDELITY")
