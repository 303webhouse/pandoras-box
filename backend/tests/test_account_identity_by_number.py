"""Identity by number, and the retired snapshot kept out — R-IV.638(b).

A NAME CANNOT TELL THE TWO FIDELITY ACCOUNTS APART, AND IT NEVER COULD. Both are BrokerageLink
accounts: "Fidelity", "BrokerageLink", "401k", "Brokerage" describe both equally. The 09-22
rule that every Fidelity name means the Roth was only true while there was one.

ABACUS'S CATCH, which is the reason the ruling exists. `config.accounts._key()` lowercases and
turns underscores into spaces, so the PARKED mutual-fund history `'Fidelity 401A'` — 90
`balance_snapshots` rows, 2026-03-20 to 2026-07-23, up to $11,075.62 — and the TRADEABLE
`'FIDELITY_401A'` collapse to the identical key `"fidelity 401a"`. An earlier pass of
R-IV.632(c) aliased that key to FIDELITY_401A, which would have brought the parked history into
scope along with the account. No name-based rule can separate them.

THE RETIRED JUNE SNAPSHOT lives in `balance_snapshots`: 43 rows under `BROKERAGE_LINK_401K` at
$11,642.35 (2026-07-24 to 2026-09-22), the merged sum of the parked 401(a) + 403(b). It is in
NO live figure, and the tests below find it where it actually lives rather than asserting
against an empty table.
"""

import ast
import io
import os

import pytest
from fastapi import HTTPException

from config.accounts import OUT_OF_SCOPE
from config.accounts import is_in_scope
from config.accounts import normalize_account as scope_normalize
from models.accounts import (ACCOUNT_BY_NUMBER, ACCOUNT_NUMBERS, ALIASES, FIDELITY_401A,
                             FIDELITY_ROTH, HISTORICAL_SPELLINGS, RETIRED_FIDELITY_NAMES,
                             ROBINHOOD, account_choices, account_for_number,
                             canonical_account, describe_accounts, is_fidelity_name,
                             normalize_account, scope_for)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# the retired June snapshot, as it actually exists
RETIRED_LABEL = "BROKERAGE_LINK_401K"
RETIRED_AMOUNT = 11_642.35
PARKED_401A_LABEL = "Fidelity 401A"      # 90 snapshot rows, max $11,075.62


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


# ─────────────────────── (b)1 the number is the identity

class TestIdentityByNumber:

    def test_both_fidelity_accounts_are_keyed_by_number(self):
        assert ACCOUNT_NUMBERS[FIDELITY_ROTH] == "652303158"
        assert ACCOUNT_NUMBERS[FIDELITY_401A] == "653641836"
        assert ACCOUNT_BY_NUMBER["652303158"] == FIDELITY_ROTH
        assert ACCOUNT_BY_NUMBER["653641836"] == FIDELITY_401A

    @pytest.mark.parametrize("raw,expected", [
        ("652303158", FIDELITY_ROTH),
        ("653641836", FIDELITY_401A),
        ("X653641836 ", FIDELITY_401A),      # digits extracted
        ("Z-652-303-158", FIDELITY_ROTH),
    ])
    def test_a_number_resolves_however_it_is_written(self, raw, expected):
        assert account_for_number(raw) == expected

    @pytest.mark.parametrize("raw", ["1836", "652", "", None, "99999999"])
    def test_a_partial_or_unknown_number_resolves_to_nothing(self, raw):
        """A partial match on an account number is how money lands in the wrong account."""
        assert account_for_number(raw) is None

    def test_a_number_resolves_through_the_write_path_too(self):
        """The refusal tells a caller to send a number; it would be a poor instruction if the
        number were then rejected."""
        assert canonical_account("652303158") == FIDELITY_ROTH
        assert canonical_account("653641836") == FIDELITY_401A


# ─────────────────────── (b)3 names stop routing

class TestNamesStopRouting:

    def test_the_fidelity_aliases_are_gone_from_the_write_path(self):
        """THE RETIRED RULE. Every one of these resolved a NAME to an account."""
        for name in ("FIDELITY", "FIDELITY ROTH", "FID", "FIDELITY - INDIVIDUAL",
                     "FIDELITY 401A"):
            assert name not in ALIASES, name

    @pytest.mark.parametrize("name", ["FIDELITY", "Fidelity", "BrokerageLink",
                                      "Brokerage Link", "401k", "403b", "Brokerage",
                                      "Fidelity Roth", "fidelity 401a"])
    def test_a_fidelity_name_is_refused_with_a_reason(self, name):
        """Defaulting is what the 09-22 rule did, and with two accounts it would file the new
        account's money in the old one — the worst available outcome, and an invisible one."""
        with pytest.raises(HTTPException) as e:
            canonical_account(name)
        assert e.value.status_code == 400
        detail = str(e.value.detail)
        assert "653641836" in detail and "652303158" in detail, detail
        assert FIDELITY_ROTH in detail and FIDELITY_401A in detail

    def test_the_refusal_says_a_combined_view_asks_for_both(self):
        with pytest.raises(HTTPException) as e:
            canonical_account("FIDELITY")
        assert "both keys" in str(e.value.detail)

    def test_robinhood_keeps_its_alias(self):
        """POSITIVE CONTROL: the change is about ambiguity, not about names in general. There
        is one Robinhood account and no number is needed to tell it from another."""
        assert normalize_account("ROBINHOOD ") == ROBINHOOD
        assert not is_fidelity_name("ROBINHOOD")

    def test_a_canonical_key_still_resolves(self):
        assert canonical_account(FIDELITY_ROTH) == FIDELITY_ROTH
        assert canonical_account(FIDELITY_401A) == FIDELITY_401A

    def test_the_bare_filter_is_refused_by_the_positions_route(self):
        """`?account=FIDELITY` passed through as a literal would return zero rows — a silent
        empty book that reads exactly like "this account holds nothing"."""
        code = _code("api/unified_positions.py")
        assert "_is_fid(account_upper)" in code
        assert "_canon_account(account_upper" in code

    def test_the_retired_names_are_declared_not_guessed(self):
        for n in ("FIDELITY", "BROKERAGELINK", "401K", "403B", "BROKERAGE"):
            assert n in RETIRED_FIDELITY_NAMES, n


# ─────────────────────── the read path keeps seeing history

class TestHistoricalReadsStillWork:

    def test_the_reconciliation_scope_reads_every_historical_spelling(self):
        """A REGRESSION CAUGHT BEFORE SHIPPING. Closing the write path to Fidelity names
        narrowed scope_for(FIDELITY_ROTH) to one spelling — reintroducing the LABEL half of
        the reconciliation rule, which exists because a scope that misses a row reports
        ABSENCE where there is DUPLICATION, and then writes the row it believes is missing."""
        scope = scope_for(FIDELITY_ROTH)
        assert scope[0] == FIDELITY_ROTH
        for sp in ("FIDELITY", "FIDELITY ROTH", "FID", "FIDELITY - INDIVIDUAL"):
            assert sp in scope, sp

    def test_the_new_account_has_no_historical_spellings(self):
        """ABACUS'S CATCH, as an assertion. `'Fidelity 401A'` names the PARKED money. Giving
        it to the traded account would pull 90 snapshot rows of a different pot into scope."""
        assert HISTORICAL_SPELLINGS[FIDELITY_401A] == ()
        assert scope_for(FIDELITY_401A) == [FIDELITY_401A]
        assert "FIDELITY 401A" not in scope_for(FIDELITY_401A)


# ─────────────────────── (b)2 the retired snapshot reaches no live figure

class TestTheRetiredSnapshotIsUnreachable:

    def test_the_parked_spelling_and_the_traded_key_part_ways(self):
        """They collapse to the same normalised key, so the canonical key is matched EXACTLY,
        before normalisation. This is the only thing that separates them."""
        assert scope_normalize(FIDELITY_401A) == FIDELITY_401A
        assert is_in_scope(FIDELITY_401A)
        assert scope_normalize(PARKED_401A_LABEL) == OUT_OF_SCOPE
        assert not is_in_scope(PARKED_401A_LABEL)

    @pytest.mark.parametrize("label", [RETIRED_LABEL, "brokerage_link_401k",
                                       "brokerage link 401k", "Fidelity 403B"])
    def test_the_retired_and_parked_labels_are_out_of_scope(self, label):
        assert scope_normalize(label) == OUT_OF_SCOPE
        assert not is_in_scope(label)

    def test_the_retired_label_is_not_a_write_target_and_says_why(self):
        with pytest.raises(HTTPException) as e:
            canonical_account(RETIRED_LABEL)
        d = str(e.value.detail)
        assert "RETIRED" in d
        assert FIDELITY_401A in d and ACCOUNT_NUMBERS[FIDELITY_401A] in d

    def test_the_committee_cannot_ask_for_the_retired_snapshot(self):
        """(b)4. Offering it beside the traded accounts is how a committee member sizes off
        $11,642.35 that is in neither of them."""
        from hub_mcp.tools.portfolio_balances import _VALID_ACCOUNTS as bal
        from hub_mcp.tools.positions import _VALID_ACCOUNTS as pos

        assert "brokerage_link_401k" not in bal
        assert "brokerage_link_401k" not in pos

    def test_the_balances_tool_reads_only_the_live_account_table(self):
        """POSITIVE CONTROL that finds the row where it LIVES: the retired snapshot is in
        `balance_snapshots`, and the balances service never reads that table — so the
        exclusion is structural, not a happy accident of an empty table."""
        code = _code("services/read_only/balances.py")
        assert "account_balances" in code
        assert "balance_snapshots" not in code

    def test_the_day_pnl_excludes_it_by_exact_membership(self):
        """It DOES live in balance_snapshots, which day-P&L reads. The filter is exact
        membership in account_balances, where no retired row exists — not a normalised
        comparison, which would have matched the parked spelling."""
        code = _code("api/portfolio.py")
        # The mechanism changed under R-IV.647(b) and the guarantee did not. The comparison
        # no longer subselects account_balances; it restricts to the accounts the BALANCES
        # SERVICE returned a derived value for, which only ever names registry keys — so a
        # retired label cannot enter either side, now by construction rather than by a join.
        assert "basis = 'derived'" in code
        assert "account_name = ANY($2::text[])" in code
        assert "[n for n in current if n not in current_partial]" in code

    def test_the_loss_alert_values_one_named_account_at_a_time(self):
        """Its cash read is `WHERE account_name = $1` with a canonical key, so no label it was
        not given can enter the valuation."""
        code = _code("jobs/loss_alert.py")
        assert "FROM cash_flows WHERE account_name = $1" in code
        from jobs.loss_alert import LOSS_ALERT_ACCOUNTS

        assert RETIRED_LABEL not in LOSS_ALERT_ACCOUNTS


# ─────────────────────── the mirror of DEF-DAYPNL-PHANTOM

def test_adding_an_account_does_not_read_as_one_days_profit():
    """The active-account filter handles an account being RETIRED. ADDING one breaks it the
    other way: a new account is in account_balances today and has no snapshot before the day
    it was created, so current_total carries its balance and prev_total cannot — the whole
    balance reads as one day's gain.

    FIDELITY_401A was registered at 0.00, so nothing is wrong today; the error appears the
    moment the principal enters its real cash, which is the next thing he does. Both sides are
    now summed over the SAME account set."""
    code = _code("api/portfolio.py")
    assert "comparable = sum(v for k, v in current.items() if k in prev_names)" in code
    # The signature gained `after` under R-IV.644(c), when the same function also started
    # subtracting the window's non-performance flows. Pinned on the NAME and the two
    # parameters this ruling is about, so the next widening does not read as a regression.
    assert "def calc_pnl(prev_total, prev_names" in code
    assert "prev_names" in code and "funding_since(after, prev_names)" in code


# ─────────────────────── (b)4 the tools describe themselves from the registry

class TestToolsServeTheRegistry:

    def test_the_choices_are_the_canonical_accounts(self):
        assert account_choices() == ["robinhood", "fidelity_roth", "fidelity_401a"]

    def test_the_description_names_every_account_and_its_number(self):
        d = describe_accounts()
        for key, num in ACCOUNT_NUMBERS.items():
            assert key in d and num in d
        assert "FID 401A" in d

    def test_neither_tool_still_says_401k_brokeragelink(self):
        """It described a "401k BrokerageLink" — a name that now sounds like the traded
        401(a) but pointed at the retired snapshot."""
        from hub_mcp.tools.portfolio_balances import DESCRIPTION as bal
        from hub_mcp.tools.positions import DESCRIPTION as pos

        assert "401k BrokerageLink" not in pos
        assert "FID 401A" in pos and "FID 401A" in bal

    def test_both_tools_offer_the_new_account(self):
        from hub_mcp.tools.portfolio_balances import _VALID_ACCOUNTS as bal
        from hub_mcp.tools.positions import _VALID_ACCOUNTS as pos

        assert "fidelity_401a" in bal and "fidelity_401a" in pos
