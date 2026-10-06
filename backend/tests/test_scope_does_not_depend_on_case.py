"""The traded 401(a) is in scope in any casing — R-IV.660(c)1 and (d).

`hub_get_portfolio_balances` reported `total_balance` 12,881.24 across "2 of 3 accounts" and
named `fidelity_401a` as excluded parked money. The account is not parked: it is the converted
BrokerageLink the principal trades, and `account_balances` holds it under the canonical
`FIDELITY_401A`.

THE CAUSE WAS NOT A MISSING ENTRY, IT WAS THE KIND OF RULE. R-IV.638(b)2 separated the traded
401(a) from the parked mutual-fund history `'Fidelity 401A'` by matching the canonical key
EXACTLY, before normalisation, and leaving every other spelling out of scope. That made an
account's scope depend on its CAPITALISATION:

    is_in_scope("FIDELITY_401A")  ->  True
    is_in_scope("fidelity_401a")  ->  False      # the same account

Case is itself a name-based rule -- the very thing R-IV.638(b)2 correctly says cannot separate
these two pots -- and it is the most fragile one available, because every boundary that folds
case flips the answer. One did: `_build_account` lowercases the name for its own payload key and
then asked this module, so the traded 401(a) came back OUT OF SCOPE and was dropped from the
headline total.

WHAT ACTUALLY HOLDS THE PARKED MONEY OUT is not a name at all. The parked history lives in
`balance_snapshots` (90 rows as 'Fidelity 401A', up to $11,075.62) and the day-P&L reader selects
`account_name = ANY(<the exact names in account_balances>) AND basis = 'derived'`. Those exact
names are the three canonical keys, so a parked row cannot match whatever this module says about
its spelling. Identity and an exact membership test were doing the work all along.
"""

import ast
import io
import os

import pytest

from config.accounts import OUT_OF_SCOPE, UNKNOWN, is_in_scope, normalize_account
from models.accounts import (CANONICAL_ACCOUNTS, FIDELITY_401A, FIDELITY_ROTH, ROBINHOOD,
                             canonical_account)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every casing and separator a real boundary produces: a DB column, a JSON key, a URL query, a
# display label, a lowercased payload key.
SPELLINGS = {
    FIDELITY_401A: ["FIDELITY_401A", "fidelity_401a", "Fidelity_401A", "fidelity 401a",
                    "Fidelity 401A", " FIDELITY_401A "],
    FIDELITY_ROTH: ["FIDELITY_ROTH", "fidelity_roth", "Fidelity Roth", "fidelity roth"],
    ROBINHOOD: ["ROBINHOOD", "robinhood", "Robinhood", " robinhood "],
}

STILL_PARKED = ["FIDELITY_403B", "fidelity_403b", "fidelity 403b",
                "BROKERAGE_LINK_401K", "brokerage_link_401k", "brokerage link 401k",
                "IBKR", "ibkr", "interactive brokers"]


class TestScopeIsIndependentOfCase:
    @pytest.mark.parametrize("canonical,spellings", sorted(SPELLINGS.items()))
    def test_every_spelling_of_a_traded_account_is_in_scope(self, canonical, spellings):
        for s in spellings:
            assert is_in_scope(s) is True, "%r must be in scope" % s
            assert normalize_account(s) == canonical

    def test_the_reproduction_the_mcp_tool_hit(self):
        """`_build_account` lowercases the DB name into its payload key and then asks for the
        scope. This is the exact pair of calls that dropped the account from the total."""
        from hub_mcp.tools.portfolio_balances import _build_account

        built = _build_account({"account_name": "FIDELITY_401A", "balance": 1.0})
        key = built.get("account") or built.get("name")
        assert key == "fidelity_401a", "the tool does lowercase it"
        assert is_in_scope(key) is True

    def test_all_three_accounts_count_as_tradeable(self):
        for canonical in CANONICAL_ACCOUNTS:
            assert is_in_scope(canonical) is True
        assert len(CANONICAL_ACCOUNTS) == 3


class TestWhatIsStillOutOfScope:
    """POSITIVE CONTROL. A fix that put everything in scope would pass every test above."""

    @pytest.mark.parametrize("name", STILL_PARKED)
    def test_the_parked_pots_and_the_retired_broker_stay_out(self, name):
        assert is_in_scope(name) is False
        assert normalize_account(name) == OUT_OF_SCOPE

    def test_an_unclassified_name_is_unknown_and_not_in_scope(self):
        """UNKNOWN is not in scope: an account nobody has classified must not be summed into a
        tradeable total on the strength of not having been recognised."""
        assert normalize_account("some new broker") == UNKNOWN
        assert is_in_scope("some new broker") is False

    def test_the_403b_is_not_swept_in_with_the_401a(self):
        """They were converted separately. Only the 401(a) became a BrokerageLink."""
        assert is_in_scope("FIDELITY_403B") is False
        assert is_in_scope("FIDELITY_401A") is True


class TestTheTwoRegistriesAgreeOnABareFidelity:
    """One question, two registries, opposite answers -- the second list R-IV.660(c)1 removes.

    `models/accounts.py` has refused a bare `FIDELITY` since R-IV.638(b)3, with a 400 naming
    both keys and both account numbers. `config/accounts.py` carried `"fidelity": FIDELITY_ROTH`
    and went on answering the same string with one of the two. Whichever module a surface
    happened to ask decided whether the principal's filter was refused or silently narrowed.
    """

    def test_the_registry_refuses_it(self):
        with pytest.raises(Exception) as exc:
            canonical_account("FIDELITY")
        msg = str(exc.value)
        assert "FIDELITY_ROTH" in msg and "FIDELITY_401A" in msg

    def test_and_the_scope_module_no_longer_answers_it(self):
        assert normalize_account("FIDELITY") == UNKNOWN
        assert normalize_account("fidelity") == UNKNOWN

    def test_the_specific_fidelity_spellings_still_resolve(self):
        """POSITIVE CONTROL: removing the ambiguous alias must not take the unambiguous ones."""
        assert normalize_account("fidelity roth") == FIDELITY_ROTH
        assert normalize_account("FIDELITY_401A") == FIDELITY_401A

    def test_the_summary_route_asks_the_registry_before_filtering(self):
        src = io.open(os.path.join(BACKEND, "api/unified_positions.py"),
                      encoding="utf-8-sig").read()
        i = src.index("async def portfolio_summary")
        body = src[i:src.index("\n@router", i)]
        assert "is_fidelity_name(account)" in body
        assert "_canonical(account)" in body

    def test_non_fidelity_aliases_are_not_routed_through_the_registry(self):
        """`rh` works in the scope module and is not a key the registry carries. Refusing it
        would break a filter that works, so only Fidelity-ish strings are checked."""
        assert normalize_account("rh") == ROBINHOOD
        with pytest.raises(Exception):
            canonical_account("rh")


class TestTheDeadSecondListIsGone:
    def test_parked_fidelity_keys_is_removed(self):
        """It held the same four strings as the out-of-scope set and was read by nothing in the
        repo -- a scope list no caller consulted. An unread vocabulary cannot be trusted to
        still mean what it says, so it was removed rather than amended."""
        import config.accounts as accounts_cfg

        assert not hasattr(accounts_cfg, "_PARKED_FIDELITY_KEYS")
        # No assignment anywhere -- the name may still appear in the comment that records why it
        # went, which is the point of keeping that comment.
        src = io.open(os.path.join(BACKEND, "config/accounts.py"), encoding="utf-8-sig").read()
        assignments = [n for n in ast.walk(ast.parse(src))
                       if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)
                       and n.id == "_PARKED_FIDELITY_KEYS"]
        assert assignments == []

    def test_the_401a_spellings_left_the_out_of_scope_set(self):
        from config.accounts import _OUT_OF_SCOPE_LABELS

        assert "fidelity 401a" not in _OUT_OF_SCOPE_LABELS
        assert "fidelity401a" not in _OUT_OF_SCOPE_LABELS
        # and the ones that must remain
        assert "fidelity 403b" in _OUT_OF_SCOPE_LABELS
        assert "brokerage_link_401k" in _OUT_OF_SCOPE_LABELS


class TestTheParkedHistoryIsHeldOutByIdentity:
    """What replaces the casing trick, stated as a test rather than left as a claim.

    The day-P&L reader's filter is an EXACT membership test against the names currently in
    `account_balances`, plus `basis = 'derived'`. Measured 2026-10-06: 'Fidelity 401A' (90 rows,
    max 11,075.62) and BROKERAGE_LINK_401K (43 rows, 11,642.35) are not admitted; the canonical
    FIDELITY_401A (4 derived rows) is.
    """

    def test_the_filter_is_an_exact_name_match_not_a_normalised_one(self):
        src = io.open(os.path.join(BACKEND, "api/portfolio.py"), encoding="utf-8-sig").read()
        i = src.index("FROM balance_snapshots")
        clause = src[i:i + 400]
        assert "account_name = ANY($2::text[])" in clause
        assert "basis = 'derived'" in clause
        assert "normalize_account" not in clause, (
            "normalising here would admit the parked spellings this filter excludes")

    def test_a_parked_snapshot_name_is_not_one_of_the_current_names(self):
        current = list(CANONICAL_ACCOUNTS)
        assert "Fidelity 401A" not in current
        assert "BROKERAGE_LINK_401K" not in current
        assert "FIDELITY_401A" in current


class TestBothBrokerageLinkAccountsAreEtfOnly:
    """R-IV.660(d). The principal confirms the 401(a) cannot trade options.

    A fact about the brokerage, which is why it is named rather than inferred from the account
    being a retirement account or from its history of holding only ETFs. All four of its live
    rows are EQUITY (measured 2026-10-06), so the rule contradicts nothing already booked.
    """

    def test_both_fidelity_accounts_refuse_an_option(self):
        from api.unified_positions import _ETF_ONLY_ACCOUNTS, _assert_etf_only

        assert _ETF_ONLY_ACCOUNTS == {FIDELITY_ROTH, FIDELITY_401A}
        for acct in (FIDELITY_ROTH, FIDELITY_401A):
            with pytest.raises(Exception):
                _assert_etf_only(acct, "OPTION")

    def test_robinhood_may_still_hold_options(self):
        """POSITIVE CONTROL. A rule that refused options everywhere would pass the test above
        and break the only account that actually trades them."""
        from api.unified_positions import _assert_etf_only

        _assert_etf_only(ROBINHOOD, "OPTION")

    def test_and_equities_are_permitted_on_both(self):
        from api.unified_positions import _assert_etf_only

        for acct in (FIDELITY_ROTH, FIDELITY_401A):
            _assert_etf_only(acct, "EQUITY")

    def test_the_set_is_built_from_the_registry_not_typed(self):
        """A key spelled out here and renamed in the registry is how an invariant comes to
        guard an account that no longer exists."""
        src = io.open(os.path.join(BACKEND, "api/unified_positions.py"),
                      encoding="utf-8-sig").read()
        assert "_ETF_ONLY_ACCOUNTS = {FIDELITY_ROTH_KEY, FIDELITY_401A_KEY}" in src
