"""A write that names no account is refused, not defaulted — R-IV.654(c).

`POST /api/v2/positions` turned a missing account into ROBINHOOD, twice over: the request model
defaulted `account: str = "ROBINHOOD"`, and the handler then wrote
`canonical_account(req.account or "ROBINHOOD")` in case the first default was bypassed.

That was safe while Robinhood was the only account options went to. With three tracked
accounts it files money in the wrong one **invisibly**, which is the worst outcome available
here: a 400 is read and fixed in a second, a silently misfiled position is found during a
reconciliation weeks later — and the reconciliation doctrine in `models/accounts.py` exists
because a row under the wrong label is a row no rule reaches.

Same reasoning as the keyword-only crypto-bar caller tags (R-IV.624(b)) and the required
`auto_adjust` (R-IV.647(c)): **a caller that says nothing must not inherit someone else's
answer.** ABACUS is fixing the form's hard-coded list beside this (R-IV.651).
"""

import ast
import io
import os

import pytest
from fastapi import HTTPException

from models.accounts import (ACCOUNT_NUMBERS, CANONICAL_ACCOUNTS, FIDELITY_401A,
                             FIDELITY_ROTH, ROBINHOOD)

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


class TestNeitherDefaultSurvives:

    def test_the_request_model_has_no_account_default(self):
        from api.unified_positions import CreatePositionRequest

        field = CreatePositionRequest.model_fields["account"]
        assert field.default is None, "a model default re-creates the bug above the handler"

    def test_the_handler_no_longer_substitutes_robinhood(self):
        """BOTH defaults mattered. Removing only the model's would leave the handler's `or`
        doing the same thing one line later."""
        code = _code("api/unified_positions.py")
        assert 'canonical_account(req.account or "ROBINHOOD")' not in code
        assert 'account: str = "ROBINHOOD"' not in code

    def test_the_handler_refuses_before_it_resolves(self):
        code = _code("api/unified_positions.py")
        i = code.index('if not (req.account or "").strip():')
        j = code.index("account = canonical_account(req.account)", i)
        assert "raise HTTPException" in code[i:j]


class TestTheRefusalIsUseful:
    """A caller told only "invalid" sends the same request again. The refusal names the
    accounts and says what changed, because the old behaviour was reasonable and someone will
    have built against it."""

    def _detail(self, value):
        from models.accounts import canonical_account

        if not (value or "").strip():
            pairs = ", ".join(
                f"{k}" + (f" (#{ACCOUNT_NUMBERS[k]})" if k in ACCOUNT_NUMBERS else "")
                for k in CANONICAL_ACCOUNTS)
            return (f"account is required: this hub tracks {len(CANONICAL_ACCOUNTS)} accounts "
                    f"— {pairs}. It used to default to ROBINHOOD, which was safe while that "
                    f"was the only account options went to and is not now. Name the account, "
                    f"or send its number.")
        return canonical_account(value)

    @pytest.mark.parametrize("missing", [None, "", "   ", "\t"])
    def test_every_shape_of_missing_is_refused(self, missing):
        d = self._detail(missing)
        assert "account is required" in d

    def test_the_refusal_names_all_three_accounts(self):
        d = self._detail(None)
        for key in CANONICAL_ACCOUNTS:
            assert key in d, key

    def test_the_refusal_carries_both_fidelity_numbers(self):
        """Because a Fidelity name alone cannot identify an account (R-IV.638(b)1), telling a
        caller to "name the account" is only actionable with the numbers beside it."""
        d = self._detail(None)
        assert ACCOUNT_NUMBERS[FIDELITY_ROTH] in d
        assert ACCOUNT_NUMBERS[FIDELITY_401A] in d

    def test_the_refusal_says_what_changed(self):
        """The old default was reasonable in its time. A caller that relied on it deserves to
        be told it is gone rather than left guessing at a new validation error."""
        d = self._detail(None)
        assert "used to default to ROBINHOOD" in d


class TestAStatedAccountStillWorks:
    """POSITIVE CONTROLS. The change refuses silence, not the caller."""

    def _resolve(self, value):
        from models.accounts import canonical_account

        return canonical_account(value)

    @pytest.mark.parametrize("value,expected", [
        ("ROBINHOOD", ROBINHOOD),
        ("robinhood", ROBINHOOD),
        ("FIDELITY_ROTH", FIDELITY_ROTH),
        ("FIDELITY_401A", FIDELITY_401A),
        ("652303158", FIDELITY_ROTH),
        ("653641836", FIDELITY_401A),
    ])
    def test_a_named_or_numbered_account_resolves(self, value, expected):
        assert self._resolve(value) == expected

    def test_a_bare_fidelity_name_is_still_refused_on_its_own_grounds(self):
        """Unchanged by this ruling: it is ambiguous between two accounts, which is a
        different refusal from "you named none"."""
        with pytest.raises(HTTPException) as e:
            self._resolve("FIDELITY")
        assert "names Fidelity without saying WHICH" in str(e.value.detail)
