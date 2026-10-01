"""One crypto-bar caller tag per consumer — R-IV.624(b).

Every crypto bar fetch reached the governor tagged `outcome_resolver`, this module's first
consumer. Five more arrived and the tag did not move, so:

  * the governor counted SIX consumers under one wrong name and could attribute none of them;
  * its 4,500 quota sat on a path spending ~370/day;
  * a budget alarm naming `outcome_resolver` sent a reader to the wrong job;
  * an open Stater tab — measured 2026-10-01 at 4 calls per 30 s, 11,520/day, 41% of
    DAILY_BUDGET — was INDISTINGUISHABLE from the resolver's own traffic.

The BEFORE figure under the old tag, recorded because a rename resets the counter (which is
why R-IV.380(b) deferred it): 09-30 **369** for the full day, of which **333** was the two
scheduled jobs; 10-01 **204** by 14:40 UTC, accounted for exactly by those jobs.
"""

import ast
import inspect
import io
import os

import pytest

from integrations.uw_api_cache import DAILY_BUDGET
from integrations.uw_governor import (DEFAULT_QUOTA, DEFAULT_TIER, QUOTA_SAFETY_BUFFER,
                                      QUOTAS, TIER_STANDARD, quota_for)
from jobs import crypto_bars as cb

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# consumer source file -> the one tag it is allowed to pass
CONSUMERS = {
    "jobs/outcome_resolver.py": "CALLER_OUTCOME_RESOLVER",
    "bias_filters/crypto_tape_health_engine.py": "CALLER_TAPE_HEALTH",
    "api/crypto_market.py": "CALLER_STATE_API",
    "jobs/crypto_regime.py": "CALLER_REGIME",
    "hub_mcp/tools/crypto_market_profile.py": "CALLER_VP_MCP",
    "strategies/btc_market_structure.py": "CALLER_MARKET_STRUCTURE",
}

FAMILY = {k: v for k, v in QUOTAS.items() if k.startswith("crypto_bars_")}
OLD_SINGLE_TAG_QUOTA = 4500   # what the one `outcome_resolver` tag held
FAMILY_TOTAL = 5000           # what the six hold — see TestBudgetImpact for why it rose
MEASURED_PEAK_09_14 = 2764    # this family's largest recorded day, under the old tag


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


# ─────────────────────── the vocabulary has one author

class TestTheVocabulary:

    def test_six_tags_declared_in_one_place(self):
        assert len(cb.CRYPTO_BAR_CALLERS) == 6

    def test_every_tag_is_distinct(self):
        """A shared name is the whole defect. Six constants, six values."""
        names = [cb.CALLER_OUTCOME_RESOLVER, cb.CALLER_TAPE_HEALTH, cb.CALLER_STATE_API,
                 cb.CALLER_REGIME, cb.CALLER_VP_MCP, cb.CALLER_MARKET_STRUCTURE]
        assert len(set(names)) == 6
        assert set(names) == set(cb.CRYPTO_BAR_CALLERS)

    def test_the_old_shared_tag_is_gone(self):
        assert "outcome_resolver" not in QUOTAS
        assert "outcome_resolver" not in cb.CRYPTO_BAR_CALLERS
        assert 'caller="outcome_resolver"' not in _code("jobs/crypto_bars.py")

    def test_the_tag_names_the_endpoint_family_not_a_job(self):
        """The convention at uw_api_cache.py:115 is endpoint-grain. `outcome_resolver`
        named a JOB, which is why a table built by walking endpoints never saw it."""
        for tag in cb.CRYPTO_BAR_CALLERS:
            assert tag.startswith("crypto_bars_"), tag


# ─────────────────────── no tag may fall to DEFAULT_QUOTA

class TestEveryTagIsQuotedExplicitly:

    @pytest.mark.parametrize("tag", sorted(cb.CRYPTO_BAR_CALLERS))
    def test_declared_means_quoted(self, tag):
        """THE FAULT THIS GUARDS. An absent tag silently takes DEFAULT_QUOTA 500 — which is
        exactly how `outcome_resolver` came to spend 2,764 against a default meant for unknown
        code paths (see that table's own note). Declaring a tag and forgetting the quota row
        reintroduces it, silently, and only under load.

        NOTE on the assertion: comparing quota_for()'s RESULT against (DEFAULT_QUOTA,
        DEFAULT_TIER) is unsound, and the positive control below caught it — two of these
        six are sized at exactly 500/STANDARD on merit, which is the default pair, so a
        value test cannot tell a declared row from a fallthrough. Membership plus "the
        lookup resolves to the declared row" is the sound form."""
        assert tag in QUOTAS, f"{tag} declared but absent from QUOTAS -> DEFAULT_QUOTA"
        assert quota_for(tag) == QUOTAS[tag], f"{tag} did not resolve to its declared row"
        assert QUOTAS[tag][1] == TIER_STANDARD

    def test_an_undeclared_tag_still_takes_the_default(self):
        """POSITIVE CONTROL: the assertion above would pass vacuously if quota_for returned
        a real pair for anything."""
        assert quota_for("crypto_bars_not_a_real_consumer") == (DEFAULT_QUOTA, DEFAULT_TIER)


# ─────────────────────── the split moved no budget

class TestBudgetImpact:

    def test_the_family_total_and_why_it_rose(self):
        """A rename should not be a raise, and the first pass split the 4,500 six ways to
        keep the table fixed. test_uw_governor_account.py refused that, correctly: this
        family's measured peak is 2,764 in a single day, so a sixth of 4,500 blocks the
        largest consumer on sight — the fault the 09-14 retune was filed to fix.

        So it rises by 500, and the rise is bounded: the resolver alone must clear the
        historical peak, and the whole family must still fit the table's headroom."""
        assert len(FAMILY) == 6
        assert sum(q for q, _ in FAMILY.values()) == FAMILY_TOTAL
        assert FAMILY_TOTAL - OLD_SINGLE_TAG_QUOTA == 500
        assert QUOTAS["crypto_bars_outcome_resolver"][0] > MEASURED_PEAK_09_14

    def test_no_single_consumer_was_sized_below_the_familys_measured_peak_by_accident(self):
        """The 2,764 cannot be attributed to one consumer retroactively — that IS the defect
        being fixed. It follows the resolver because over-sizing wastes headroom while
        under-sizing blocks."""
        biggest = max(FAMILY.items(), key=lambda kv: kv[1][0])
        assert biggest[0] == "crypto_bars_outcome_resolver"

    def test_the_table_still_fits_under_the_hub_budget(self):
        assert sum(q for q, _ in QUOTAS.values()) <= DAILY_BUDGET - QUOTA_SAFETY_BUFFER

    def test_the_measured_consumers_are_sized_above_measured_demand(self):
        """Scheduled demand is known exactly: tape-health 96 runs/day x 3 UW symbols = 288,
        regime 24 x 3 = 72. A quota under measured demand blocks on sight — the fault the
        2026-09-14 retune was filed to fix."""
        assert QUOTAS["crypto_bars_tape_health"][0] > 288
        assert QUOTAS["crypto_bars_regime"][0] > 72

    def test_state_api_is_sized_well_under_an_open_tab(self):
        """Deliberate: a tab left open spends 2,880/day on this route alone. The quota is NOT
        sized to that — it is sized to a real visit, so a forgotten tab shows up as a
        would-block instead of as 41% of the daily budget."""
        assert QUOTAS["crypto_bars_state_api"][0] < 2880
        assert QUOTAS["crypto_bars_state_api"][0] > 288  # ...but above a real visit's cost


# ─────────────────────── each consumer passes its own tag

class TestEachConsumerPassesItsOwn:

    @pytest.mark.parametrize("rel,const", sorted(CONSUMERS.items()))
    def test_the_consumer_passes_exactly_one_tag_and_it_is_its_own(self, rel, const):
        code = _code(rel)
        assert f"caller={const}" in code, f"{rel} does not pass {const}"
        others = set(CONSUMERS.values()) - {const}
        for other in others:
            assert other not in code, f"{rel} reaches for {other}"

    def test_no_consumer_passes_a_bare_string(self):
        """A literal at the call site is a second author for the name."""
        for rel in CONSUMERS:
            code = _code(rel)
            for tag in cb.CRYPTO_BAR_CALLERS:
                assert f'"{tag}"' not in code and f"'{tag}'" not in code, rel

    def test_all_six_consumers_are_covered(self):
        """If a seventh consumer appears, it must be added here — which is the point."""
        assert len(CONSUMERS) == len(cb.CRYPTO_BAR_CALLERS)


# ─────────────────────── omission cannot inherit someone else's name

class TestCallerIsRequired:

    @pytest.mark.parametrize("fn", ["fetch_crypto_ohlc", "fetch_crypto_bars",
                                    "_fetch_full_ohlc", "_fetch_uw_bars_full"])
    def test_caller_is_keyword_only_with_no_default(self, fn):
        """THE DURABLE PART. With a default, consumer seven inherits consumer one's name by
        saying nothing — which is how this defect was born. With none, it is a TypeError at
        the call site, caught the first time the code runs."""
        p = inspect.signature(getattr(cb, fn)).parameters["caller"]
        assert p.kind is inspect.Parameter.KEYWORD_ONLY, fn
        assert p.default is inspect.Parameter.empty, f"{fn} lets a caller go untagged"

    def test_the_uw_fetch_refuses_an_undeclared_tag(self):
        code = _code("jobs/crypto_bars.py")
        assert "assert caller in CRYPTO_BAR_CALLERS" in code

    def test_the_tag_reaches_the_governor_unchanged(self):
        """The counter is only as good as the last hop: a tag threaded six levels and then
        hard-coded at the request would measure nothing."""
        code = _code("jobs/crypto_bars.py")
        assert "caller=caller" in code
        assert code.count("caller=caller") >= 3  # uw_request + both wrappers -> dispatcher
