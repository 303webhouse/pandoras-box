"""A field served from the cache reports its age at SERVE time — R-IV.699.

`envelope()` computes `age_s` and `stale` once, when the dict is built. `/crypto/market` caches
the whole response, so a body served from that cache reported the age it had WHEN CACHED.

MEASURED ON PRODUCTION before the fix, at the then-current 4 s TTL: two reads 1.28 s apart
returned the identical body (same response `timestamp`) with `mark.age_s` frozen at 0.611 on
both, `funding` at 0.257 on both, `open_interest` at 0.0 on both. R-IV.692 raises the TTL to 8 s
so legacy Agora's 5 s poll hits the cache — which doubles the understatement on the very field
ABACUS's staleness line reads.

`as_of` is the FACT and never changes. `age_s` and `stale` are DERIVED from it against now. A
derived value that travels inside a cache stops being derived and becomes a stale copy — the same
shape as a stored total that no longer matches its ledger.
"""

import ast
import io
import os
from datetime import datetime, timedelta, timezone

from bias_filters.crypto_perps import (TTL_FUNDING, TTL_PRICE, envelope, reage)

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _code(rel):
    src = io.open(os.path.join(BACKEND, rel), encoding="utf-8-sig").read()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                src = src.replace(doc, "")
    return "".join(l for l in src.splitlines(keepends=True)
                   if not l.strip().startswith("#"))


def _body(now):
    """A response shaped like the one the cache holds: top-level and NESTED envelopes."""
    return {
        "timestamp": now.isoformat(),
        "derivatives": {
            "mark": envelope(85000.0, "hyperliquid", now, TTL_PRICE),
            "funding": {**envelope(0.004, "coinalyze", now, TTL_FUNDING),
                        "predicted": envelope(1e-5, "hyperliquid:BinPerp", now, TTL_FUNDING)},
            "predicted_by_venue": {
                "binance": envelope(1e-5, "hyperliquid:BinPerp", now, TTL_FUNDING)},
        },
    }


class TestTheAgeAdvances:
    def test_a_cached_field_reports_the_age_it_has_not_the_age_it_had(self):
        now = datetime.now(timezone.utc)
        body = _body(now)
        assert body["derivatives"]["mark"]["age_s"] == 0.0
        reage(body, now + timedelta(seconds=7.5))
        assert body["derivatives"]["mark"]["age_s"] == 7.5

    def test_nested_envelopes_are_walked(self):
        """A reader that trusted the top-level age and not the nested one would be worse off
        than one that trusted neither."""
        now = datetime.now(timezone.utc)
        body = _body(now)
        reage(body, now + timedelta(seconds=6))
        assert body["derivatives"]["funding"]["age_s"] == 6.0
        assert body["derivatives"]["funding"]["predicted"]["age_s"] == 6.0
        assert body["derivatives"]["predicted_by_venue"]["binance"]["age_s"] == 6.0

    def test_as_of_is_never_rewritten(self):
        """The fact stays fixed; only what is derived from it moves. Rewriting `as_of` would
        make a cached reading look like a fresh one, which is the opposite of the fix."""
        now = datetime.now(timezone.utc)
        body = _body(now)
        before = body["derivatives"]["mark"]["as_of"]
        reage(body, now + timedelta(seconds=30))
        assert body["derivatives"]["mark"]["as_of"] == before

    def test_a_value_that_ages_past_its_ttl_inside_the_cache_is_withdrawn(self):
        """Otherwise the cache becomes a way to serve a reading the TTL already rejects — the
        TTL would hold on a fresh build and not on a cached one, for the same instant."""
        now = datetime.now(timezone.utc)
        body = _body(now)
        reage(body, now + timedelta(seconds=TTL_PRICE + 5))
        mark = body["derivatives"]["mark"]
        assert mark["stale"] is True
        assert mark["value"] is None
        # and the funding field, on a 900 s ttl, is NOT withdrawn at the same instant
        assert body["derivatives"]["funding"]["stale"] is False
        assert body["derivatives"]["funding"]["value"] == 0.004

    def test_a_fresh_field_is_not_disturbed(self):
        """POSITIVE CONTROL. A re-ager that withdrew everything would pass the test above and
        empty the endpoint."""
        now = datetime.now(timezone.utc)
        body = _body(now)
        reage(body, now + timedelta(seconds=2))
        assert body["derivatives"]["mark"]["value"] == 85000.0
        assert body["derivatives"]["mark"]["stale"] is False

    def test_an_envelope_with_no_as_of_is_left_alone(self):
        """An absent reading has no age to recompute, and inventing one would turn honest
        absence into a measured zero."""
        now = datetime.now(timezone.utc)
        body = {"derivatives": {"long_short": envelope(None, None, None, TTL_PRICE)}}
        reage(body, now + timedelta(seconds=60))
        ls = body["derivatives"]["long_short"]
        assert ls["age_s"] is None
        assert ls["value"] is None
        assert ls["stale"] is False


class TestTheCacheHitUsesIt:
    def test_the_market_route_reages_on_a_cache_hit(self):
        src = _code("api/crypto_market.py")
        i = src.index("if cache[\"data\"] and (now - cache[\"timestamp\"]) < CACHE_TTL_SECONDS:")
        block = src[i:i + 400]
        assert "reage(cache[\"data\"])" in block
        assert "return cache[\"data\"]\n" not in block, (
            "a bare return of the cached body is the fault this closes")

    def test_the_ttl_is_longer_than_the_legacy_poll(self):
        """R-IV.692's reason for the raise: at 4 s, legacy Agora's 5 s poll missed the cache on
        every tick and paid the full fan-out. The fix above is what makes the raise safe."""
        from api.crypto_market import CACHE_TTL_SECONDS

        assert CACHE_TTL_SECONDS == 8
        assert CACHE_TTL_SECONDS > 5
