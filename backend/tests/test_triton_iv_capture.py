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
        # Every value, not an exact key set: the claim is "nothing was invented", and pinning the
        # dict's shape instead made this fail when `iv_rank_raw` was added — a test breaking for
        # the wrong reason, which is the same fault as a positional index.
        assert out and all(v is None for v in out.values()), out

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


# ─────────────── the unit trap, measured 2026-09-30 (R-IV.597(c) follow-up)

class TestTheConverterRefusesInsteadOfClamping:
    """`iv_rank_1y_to_100` multiplied by 100 and clamped to [0, 100].

    Measured on `signals.enrichment_data.iv_rank_uw_shadow`, which it produces: 7,553 of 7,606
    rows exactly 100.0 and 35 exactly 0.0 — the two clamp bounds — with nineteen distinct values
    since 2026-06-11. The unrelated proxy rank has 711 distinct values and none at 100, so the
    constant is the conversion, not the market.

    A quantity defined on [0, 1] cannot exceed 1 in 99.3% of observations.
    """

    def test_a_real_fraction_still_converts(self):
        from scoring.sb3_iv_units import iv_rank_1y_to_100

        assert iv_rank_1y_to_100(0.417) == 41.7
        assert iv_rank_1y_to_100(0.0) == 0.0
        assert iv_rank_1y_to_100(1.0) == 100.0

    def test_an_out_of_range_input_is_refused_not_clamped(self):
        """A clamp turns 'this input is not what I was told' into 'IV is at its one-year high',
        which is a claim. None is the absence of one."""
        from scoring.sb3_iv_units import iv_rank_1y_to_100

        for raw in (41.7, 100, 1.0001, 83.6, -0.1, -1):
            assert iv_rank_1y_to_100(raw) is None, raw

    def test_the_values_that_looked_plausible_are_the_misleading_ones(self):
        """Seventeen readings looked like real mid-range ranks. Each came from a raw value BELOW
        one, multiplied up — so it read as a mid-range rank when the raw number was under one
        percent. Those are preserved by the raw column, not by the conversion."""
        from scoring.sb3_iv_units import iv_rank_1y_to_100

        assert iv_rank_1y_to_100(0.417) == 41.7      # what produced the 41.7 in the table
        assert iv_rank_1y_to_100(41.7) is None       # what a true 41.7% rank would arrive as

    def test_nan_and_junk_are_refused(self):
        from scoring.sb3_iv_units import iv_rank_1y_to_100

        assert iv_rank_1y_to_100(float("nan")) is None
        assert iv_rank_1y_to_100("41.7%") is None
        assert iv_rank_1y_to_100(None) is None

    def test_no_caller_clamps_on_its_own(self):
        """`b2_options_resolver` does its own `* 100` inline rather than using the helper, so it
        carries the same trap. It is named here because it writes to a table holding ZERO rows —
        it has never run — and the fix belongs with its first use, not with a guess now."""
        src = _src("jobs/b2_options_resolver.py")
        assert "float(raw_iv) * 100" in src           # still there, and still dead
        from database.postgres_client import get_postgres_client  # noqa: F401


class TestTheRawValueIsKept:

    @pytest.mark.asyncio
    async def test_the_raw_is_stored_even_when_the_conversion_refuses(self, monkeypatch):
        """This is what settles the units on the next session: the number as it arrived."""
        import integrations.uw_api as uw

        async def _p(ticker, caller="iv_rank"):
            return [{"date": "2026-09-30", "iv_rank_1y": 41.7}]

        monkeypatch.setattr(uw, "get_iv_rank", _p)
        out = await tsc.iv_at_fire("NVDA")
        assert out["iv_rank_raw"] == 41.7            # kept
        assert out["iv_rank_at_fire"] is None        # and not converted into a false claim

    @pytest.mark.asyncio
    async def test_a_genuine_fraction_gives_both(self, monkeypatch):
        import integrations.uw_api as uw

        async def _p(ticker, caller="iv_rank"):
            return [{"date": "2026-09-30", "iv_rank_1y": 0.417}]

        monkeypatch.setattr(uw, "get_iv_rank", _p)
        out = await tsc.iv_at_fire("NVDA")
        assert out["iv_rank_raw"] == 0.417
        assert out["iv_rank_at_fire"] == 41.7

    def test_the_poller_persists_the_raw_column(self):
        code = _src("jobs/triton_shadow_poller.py")
        assert "iv_rank_raw" in code
        assert 'iv["iv_rank_raw"]' in code
