"""The River's "Your book" lane — R-IV.568 / R-IV.599(e), and crypto's exemption (c)."""

import ast
import io
import os
from datetime import datetime

import pytest

from config.asset_class import is_crypto
from models.position_direction import (BEARISH, BULLISH, CONFIRMS, CONTRADICTS,
                                       direction_of_signal, direction_of_structure,
                                       exit_block, relation, touches_block)
from signals import session_policy as sp

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _code(rel):
    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return src


# ───────────────────────── (c) crypto is outside the session rule

class TestCryptoIsExempt:

    @pytest.mark.parametrize("timeframe", ["15", "60", "DAILY", "W", None])
    def test_crypto_is_never_dropped_or_held(self, timeframe):
        """Every clause of the rule reasons about an exchange session: an intraday setup is
        dropped because it is gone by the open, a swing one is held UNTIL the open. Crypto trades
        around the clock, so there is no open to be gone by and none to wait for."""
        overnight = datetime(2026, 9, 26, 2, 0)          # a Friday night, market shut
        for ac in ("CRYPTO", "crypto", " Crypto "):
            action, release, why = sp.decide(timeframe, overnight, "T", asset_class=ac)
            assert action == sp.DELIVER, (ac, timeframe)
            assert release is None
            assert "around the clock" in why

    @pytest.mark.parametrize("asset_class", ["EQUITY", None, ""])
    def test_equity_still_obeys_the_rule(self, asset_class):
        """POSITIVE CONTROL: the exemption is narrow. Without it this test would pass on a
        policy that had stopped working for everyone."""
        overnight = datetime(2026, 9, 26, 2, 0)
        assert sp.decide("15", overnight, "T", asset_class=asset_class)[0] == sp.DROP
        assert sp.decide("DAILY", overnight, "T", asset_class=asset_class)[0] == sp.HOLD

    def test_it_is_asked_before_the_calendar_and_the_band(self):
        """A crypto signal must not need a readable timeframe or a reachable calendar to be
        delivered — neither question applies to it."""
        action, _, _ = sp.decide("nonsense", None, "T", asset_class="CRYPTO")
        assert action == sp.DELIVER

    def test_it_uses_the_one_crypto_author(self):
        assert is_crypto("CRYPTO") and not is_crypto("EQUITY")
        assert "is_crypto" in _code("signals/session_policy.py")


# ───────────────────────── (e)1 the touches block

class TestTheDirectionMap:

    @pytest.mark.parametrize("structure,expected", [
        ("stock", BULLISH), ("long_call", BULLISH), ("call_debit_spread", BULLISH),
        ("put_credit_spread", BULLISH), ("short_put", BULLISH),
        ("long_put", BEARISH), ("put_debit_spread", BEARISH),
        ("call_credit_spread", BEARISH), ("short_call", BEARISH),
    ])
    def test_the_map_from_the_ruling(self, structure, expected):
        assert direction_of_structure(structure) == expected

    @pytest.mark.parametrize("structure,expected", [
        # every composite live in the book on 2026-09-30
        ("put_debit_spread+long_put", BEARISH),
        ("put_debit_spread+put_debit_spread", BEARISH),
    ])
    def test_a_composite_that_agrees_has_that_direction(self, structure, expected):
        assert direction_of_structure(structure) == expected

    def test_a_two_sided_composite_has_no_direction(self):
        """Picking the first component's would state something nobody chose."""
        assert direction_of_structure("put_debit_spread+call_debit_spread") is None

    def test_an_unreadable_structure_is_none_not_a_guess(self):
        for s in ("iron_condor", "CUSTOM", "", None, "put_debit_spread+wat"):
            assert direction_of_structure(s) is None, s

    def test_an_inverse_etf_is_not_special_cased(self):
        """Long SRTY is a bearish bet on the Russell but a LONG position in SRTY, and the
        relation is computed against a signal on the SAME ticker. So the instrument's own
        direction is the right frame — a LONG SRTY signal confirms a long SRTY position."""
        assert relation("stock", "LONG") == CONFIRMS
        assert relation("stock", "SHORT") == CONTRADICTS

    def test_both_spellings_of_each_side(self):
        for word in ("LONG", "long", "BUY", "bullish"):
            assert direction_of_signal(word) == BULLISH, word
        for word in ("SHORT", "short", "SELL", "bearish"):
            assert direction_of_signal(word) == BEARISH, word
        assert direction_of_signal("sideways") is None

    def test_a_relation_is_never_asserted_on_an_unread_side(self):
        """A CONTRADICTS badge on the principal's own book is not a claim to make on a
        structure nobody parsed."""
        assert relation("iron_condor", "LONG") is None
        assert relation("stock", "sideways") is None
        # POSITIVE CONTROL
        assert relation("stock", "LONG") == CONFIRMS

    def test_the_block_serves_the_direction_beside_the_relation(self):
        """So a null relation is distinguishable from a null direction: the first means the
        signal was unreadable, the second means the structure was."""
        b = touches_block({"position_id": "POS_X", "structure": "put_debit_spread",
                           "account": "ROBINHOOD"}, "SHORT")
        # The account travels with the touch since R-IV.632(c)3, so ABACUS does not join
        # back to the book to answer "which account contradicts this signal" -- a question
        # that now has three possible answers.
        # R-IV.660(b)2 adds the open quantity: "this touches your book" is not usable without
        # how much of the book it touches. Both are None here because this caller passed no
        # lots -- which is itself the point of `open_quantity_basis` travelling with the figure.
        # Still EXACT equality: a field nobody meant to add should fail this test.
        assert b == {"position_id": "POS_X", "structure": "put_debit_spread",
                     "position_direction": BEARISH, "relation": CONFIRMS,
                     "account": "ROBINHOOD", "account_display": "Robinhood",
                     "open_quantity": None, "open_quantity_basis": None}

    def test_one_author(self):
        """This was about to be a fourth reading of `structure`."""
        for rel in ("signals/feed_service.py", "services/read_only/positions.py"):
            code = _code(rel)
            assert "put_debit_spread" not in code, rel


class TestTheTouchesWiring:

    def test_the_book_is_read_once_for_the_page(self):
        """An N+1 across every signal on the page is the shape that made the balances read slow
        enough to notice."""
        for rel in ("signals/feed_service.py", "api/trade_ideas.py"):
            assert "open_positions_by_ticker" in _code(rel), rel

    def test_a_ticker_with_two_positions_gets_both(self):
        """QQQ holds two open positions on different structures today, and one could confirm
        while the other contradicts. Serving the first would hide the disagreement."""
        from signals.feed_service import attach_touches

        book = {"QQQ": [{"position_id": "A", "structure": "put_debit_spread"},
                        {"position_id": "B", "structure": "call_debit_spread"}]}
        row = attach_touches({"ticker": "QQQ", "direction": "SHORT"}, book)
        assert len(row["touches"]) == 2
        assert {t["relation"] for t in row["touches"]} == {CONFIRMS, CONTRADICTS}

    def test_a_ticker_not_in_the_book_has_no_block_at_all(self):
        """Absent, not empty, so "no position" and "a position with an unreadable structure"
        stay different."""
        from signals.feed_service import attach_touches

        row = attach_touches({"ticker": "NVDA", "direction": "LONG"}, {})
        assert "touches" not in row

    def test_the_feed_is_gated_because_the_block_discloses_the_book(self):
        """`test_no_ungated_get_touches_a_book_table` is right to refuse this on an open route,
        and its other remedy is an exemption — which is what hid six routes before it existed."""
        code = _code("api/trade_ideas.py")
        assert code.count("Depends(require_api_key)") >= 2

    def test_an_unreadable_book_serves_the_feed_anyway(self):
        """Fail OPEN: a feed that cannot read the book shows no touches, not no feed."""
        import inspect

        from signals.feed_service import open_positions_by_ticker
        src = inspect.getsource(open_positions_by_ticker)
        assert "except Exception" in src and "return out" in src


# ───────────────────────── (e)2 the exit block

class TestTheExitBlock:

    def test_it_carries_all_four_fields_and_says_whether_anything_was_written(self):
        b = exit_block({"stop_loss": 206.61, "stop_type": "none",
                        "invalidation": "IWM daily close above its 50-day SMA",
                        "time_stop": "2026-10-23"})
        assert b["stop"] == 206.61
        assert b["stop_type"] == "none"
        assert b["invalidation"].startswith("IWM")
        assert b["time_stop"] == "2026-10-23"
        assert b["written"] is True

    def test_an_empty_plan_says_so_in_one_field(self):
        """The page tests one thing for "No exit written", not four."""
        b = exit_block({})
        assert b["written"] is False
        assert all(b[k] is None for k in ("stop", "stop_type", "invalidation", "time_stop"))

    def test_a_stop_alone_still_counts_as_written(self):
        """`stop_loss` is a LIVE BROKER ORDER per TA-025. A row carrying one has an exit even
        with no written plan, and showing "No exit written" over a resting order would be the
        more dangerous error of the two."""
        assert exit_block({"stop_loss": 24.5})["written"] is True

    def test_every_open_position_carries_it(self):
        assert "exit_block" in _code("services/read_only/positions.py")
