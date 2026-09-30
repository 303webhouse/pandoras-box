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
    """A module's LIVE CODE: docstrings and comments both removed, spacing preserved.

    Stripping only docstrings was not enough, and the same trap has now caught five scans in this
    lane -- most recently a comment written to EXPLAIN a fix, which named the very string the
    test asserts is gone. A `#` comment is documentation too.

    Comments are BLANKED IN PLACE rather than tokenised away, because a tokenize round-trip
    respaces the source and every substring assertion built on it stops matching.
    """
    import io as _io
    import tokenize

    src = _io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    lines = src.splitlines(keepends=True)
    try:
        for tok in tokenize.generate_tokens(_io.StringIO(src).readline):
            if tok.type != tokenize.COMMENT:
                continue
            r, c0 = tok.start[0] - 1, tok.start[1]
            c1 = tok.end[1]
            lines[r] = lines[r][:c0] + " " * (c1 - c0) + lines[r][c1:]
    except (tokenize.TokenError, IndentationError):
        pass                # unparseable after the strip; return what we have rather than lie
    return "".join(lines)


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
            return [{"date": "2026-09-24", "iv_rank_1y": 10.0},
                    {"date": "2026-09-30", "iv_rank_1y": 83.0, "volatility": 0.412}]

        monkeypatch.setattr(uw, "get_iv_rank", _p)
        out = await tsc.iv_at_fire("NVDA")
        assert out["iv_rank_at_fire"] == 83.0        # the LAST row — the series ascends
        assert out["iv_at_fire"] == 0.412
        assert out["iv_source"] == "volatility"     # the payload's own key

    @pytest.mark.asyncio
    async def test_the_source_says_rank_when_no_level_is_offered(self, monkeypatch):
        """A rank is NOT an expected move -- it says where today's IV sits in its own one-year
        range. `iv_source` makes that legible instead of letting a rank pass as a level."""
        import integrations.uw_api as uw

        async def _p(ticker, caller="iv_rank"):
            return [{"date": "2026-09-30", "iv_rank_1y": 50.0}]

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

    def test_the_disagreement_is_settled_and_both_readers_agree(self):
        """SETTLED 2026-09-30 from the payload's own log: the series runs first=2026-09-24 to
        last=2026-09-30, ASCENDING. So `[0]` was the OLDEST row in the window -- six days stale --
        and `b2_options_resolver` was the offender. Both take `[-1]` now."""
        enricher = _src("enrichment/signal_enricher.py")
        resolver = _src("jobs/b2_options_resolver.py")
        assert "data[-1] if isinstance(data, list)" in enricher
        assert "iv_data[-1] if isinstance(iv_data, list)" in resolver
        assert "iv_data[0]" not in resolver
        # ...and it no longer scales a percent by 100 either. Narrow to the IV expression: the
        # module has a legitimate `* 100` elsewhere, on a percentage-of-mark calculation.
        assert "float(raw_iv) * 100" not in resolver

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

        assert iv_rank_1y_to_100(4.0881) == 4.1
        assert iv_rank_1y_to_100(0.0) == 0.0
        assert iv_rank_1y_to_100(100.0) == 100.0

    def test_an_out_of_range_input_is_refused_not_clamped(self):
        """A clamp turns 'this input is not what I was told' into 'IV is at its one-year high',
        which is a claim. None is the absence of one."""
        from scoring.sb3_iv_units import iv_rank_1y_to_100

        for raw in (100.1, 4170, -0.1, -1):
            assert iv_rank_1y_to_100(raw) is None, raw

    def test_the_values_that_looked_plausible_are_the_misleading_ones(self):
        """Seventeen readings looked like real mid-range ranks. Each came from a raw value BELOW
        one, multiplied up — so it read as a mid-range rank when the raw number was under one
        percent. Those are preserved by the raw column, not by the conversion."""
        from scoring.sb3_iv_units import iv_rank_1y_to_100

        assert iv_rank_1y_to_100(0.417) == 0.4       # what produced the table's 41.7, correctly
        assert iv_rank_1y_to_100(41.7) == 41.7       # what a true 41.7% rank arrives as

    def test_nan_and_junk_are_refused(self):
        from scoring.sb3_iv_units import iv_rank_1y_to_100

        assert iv_rank_1y_to_100(float("nan")) is None
        assert iv_rank_1y_to_100("41.7%") is None
        assert iv_rank_1y_to_100(None) is None
        # POSITIVE CONTROL: a numeric string still reads.
        assert iv_rank_1y_to_100("41.7") == 41.7

    def test_every_caller_goes_through_the_one_converter(self):
        """`b2_options_resolver` did its own `* 100` inline. Fixed under R-IV.599(b)2 rather than
        left dead, because it would have been wrong the first time it ran."""
        src = _src("jobs/b2_options_resolver.py")
        assert "iv_rank_1y_to_100" in src
        assert "float(raw_iv) * 100" not in src


class TestTheRawValueIsKept:

    @pytest.mark.asyncio
    async def test_the_raw_is_stored_beside_the_converted_value(self, monkeypatch):
        """This is what SETTLED the units: the number as it arrived. One session of it showed 58
        of 58 readings above 1, which is a percent, not a fraction."""
        import integrations.uw_api as uw

        async def _p(ticker, caller="iv_rank"):
            return [{"date": "2026-09-30", "iv_rank_1y": 41.7}]

        monkeypatch.setattr(uw, "get_iv_rank", _p)
        out = await tsc.iv_at_fire("NVDA")
        assert out["iv_rank_raw"] == 41.7            # kept
        # R-IV.599(b)2: 41.7 is a VALID percent, measured. The raw column is what proved it.
        assert out["iv_rank_at_fire"] == 41.7

    @pytest.mark.asyncio
    async def test_an_out_of_range_raw_is_kept_while_the_rank_refuses(self, monkeypatch):
        """The raw column outlives the refusal, which is the point of having it."""
        import integrations.uw_api as uw

        async def _p(ticker, caller="iv_rank"):
            return [{"date": "2026-09-30", "iv_rank_1y": 4170}]

        monkeypatch.setattr(uw, "get_iv_rank", _p)
        out = await tsc.iv_at_fire("NVDA")
        assert out["iv_rank_raw"] == 4170
        assert out["iv_rank_at_fire"] is None
        assert out["iv_rank_valid"] is False

    def test_the_poller_persists_the_raw_column(self):
        code = _src("jobs/triton_shadow_poller.py")
        assert "iv_rank_raw" in code
        assert 'iv["iv_rank_raw"]' in code
