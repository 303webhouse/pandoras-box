"""IV at fire time — R-IV.597(c). Capture it or lose it.

No history exists, so every session without it is lost for good. These tests pin the two things
that would make the capture worthless: a fake zero, and a second opinion about the payload.
"""

import ast
import inspect
import io
import os

import pytest

from jobs import triton_shadow_common as tsc

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _src(rel):
    return io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()


class TestItSpendsFromTheRightBudget:

    def test_it_is_tagged_to_tritons_own_background_lane(self):
        """Shadow research yields to committee and radar priority, never the reverse. The
        governor sheds BACKGROUND first, so a shadow study must not ride the FOREGROUND
        `iv_rank` quota that live trading depends on."""
        src = inspect.getsource(tsc.iv_at_fire)
        assert 'caller="triton_flow_shadow"' in src

        from integrations.uw_governor import QUOTAS, TIER_BACKGROUND, TIER_FOREGROUND
        assert QUOTAS["triton_flow_shadow"][1] == TIER_BACKGROUND
        # POSITIVE CONTROL: the lane it is NOT using is the protected one.
        assert QUOTAS["iv_rank"][1] == TIER_FOREGROUND

    def test_the_caller_tag_never_forks_the_cache(self):
        """Two caches would double the real spend to keep the accounting tidy."""
        from integrations import uw_api
        src = inspect.getsource(uw_api.get_iv_rank)
        assert 'cache_get("iv_rank", ticker.upper())' in src
        assert 'cache_set("iv_rank", ticker.upper()' in src

    def test_the_default_caller_is_unchanged_for_everyone_else(self):
        sig = inspect.signature(__import__("integrations.uw_api",
                                          fromlist=["x"]).get_iv_rank)
        assert sig.parameters["caller"].default == "iv_rank"


class TestItNeverInventsAValue:

    @pytest.mark.asyncio
    async def test_a_failure_is_none_and_never_zero(self, monkeypatch):
        """A fake 0 would read as 'volatility is at its one-year low', which is a claim. None is
        the absence of one."""
        import integrations.uw_api as uw

        async def _boom(ticker, caller="iv_rank"):
            raise RuntimeError("UW down")

        monkeypatch.setattr(uw, "get_iv_rank", _boom)
        out = await tsc.iv_at_fire("NVDA")
        assert out == {"iv_rank_at_fire": None, "iv_at_fire": None, "iv_source": None}

    @pytest.mark.asyncio
    async def test_an_empty_payload_is_none(self, monkeypatch):
        import integrations.uw_api as uw

        for payload in (None, [], {}, [None], ["not a dict"]):
            async def _p(ticker, caller="iv_rank", _p=payload):
                return _p
            monkeypatch.setattr(uw, "get_iv_rank", _p)
            out = await tsc.iv_at_fire("NVDA")
            assert out["iv_rank_at_fire"] is None, payload

    @pytest.mark.asyncio
    async def test_a_rank_is_converted_and_a_level_is_named(self, monkeypatch):
        import integrations.uw_api as uw

        async def _p(ticker, caller="iv_rank"):
            return [{"date": "2026-09-01", "iv_rank_1y": 0.10},
                    {"date": "2026-09-25", "iv_rank_1y": 0.83, "implied_volatility": 0.412}]

        monkeypatch.setattr(uw, "get_iv_rank", _p)
        out = await tsc.iv_at_fire("NVDA")
        assert out["iv_rank_at_fire"] == 83.0        # the LAST row, and x100
        assert out["iv_at_fire"] == 0.412
        assert out["iv_source"] == "implied_volatility"

    @pytest.mark.asyncio
    async def test_the_source_says_rank_when_no_level_is_offered(self, monkeypatch):
        """A rank is NOT an expected move -- it says where today's IV sits in its own one-year
        range. `iv_source` makes that legible instead of letting a rank pass as a level."""
        import integrations.uw_api as uw

        async def _p(ticker, caller="iv_rank"):
            return [{"date": "2026-09-25", "iv_rank_1y": 0.5}]

        monkeypatch.setattr(uw, "get_iv_rank", _p)
        out = await tsc.iv_at_fire("NVDA")
        assert out["iv_rank_at_fire"] == 50.0
        assert out["iv_at_fire"] is None
        assert out["iv_source"] == "iv_rank_1y"


class TestOneReaderNotAThird:

    def test_it_delegates_rather_than_reparsing(self):
        """Two callers already disagree about which end of the series is current --
        `signal_enricher` takes `data[-1]`, `b2_options_resolver` takes `[0]`. One reads a
        year-old figure as today's. This reuses the conversion helper and the `[-1]` end, which
        has 7,383 rows of history behind it, rather than adding a third opinion."""
        src = inspect.getsource(tsc.iv_at_fire)
        assert "iv_rank_1y_to_100" in src
        assert "data[-1]" in src
        # ...and it does NOT do its own arithmetic on the fraction.
        assert "* 100" not in src

    def test_the_disagreement_is_still_there_to_be_settled(self):
        """POSITIVE CONTROL for the note above: if someone fixes the two callers, this fails and
        the note stops being true, which is when it should be rewritten."""
        enricher = _src("enrichment/signal_enricher.py")
        resolver = _src("jobs/b2_options_resolver.py")
        assert "data[-1] if isinstance(data, list)" in enricher
        assert "iv_data[0] if isinstance(iv_data, list)" in resolver

    def test_the_payload_shape_is_logged_once_per_ticker_per_day(self):
        """So the next decision about this data is made on measured keys, not on a guess."""
        src = inspect.getsource(tsc.iv_at_fire)
        assert "_IV_SHAPE_LOGGED" in src
        assert "payload keys" in src

    def test_the_poller_stores_all_three_columns(self):
        code = _src("jobs/triton_shadow_poller.py")
        for col in ("iv_rank_at_fire", "iv_at_fire", "iv_source"):
            assert col in code, col
        assert "await iv_at_fire(ticker)" in code
