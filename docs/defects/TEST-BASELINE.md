# TEST-BASELINE — the known-failing tests, by name

**Registered:** R-IV.430(f). **Owner:** CC-BUILD.
**Why this file exists:** *untracked failures are how a real one hides.* A count ("25 failed")
cannot show that one of the 25 is new and a different one was fixed. A list can.

## HOW TO READ A RUN AGAINST THIS

A run is **clean against the baseline** when its failing node ids are **exactly** this list —
not when the count matches. Compare sets:

```
diff <(grep ^FAILED baseline.txt | sed 's/ - .*//' | sort) \
     <(grep ^FAILED this_run.txt | sed 's/ - .*//' | sort)
```

A test that leaves this list (fixed) is removed here in the same commit that fixes it. A test
that joins it is a regression until a ruling says otherwise, and is never added silently.

## ENVIRONMENT OF RECORD

Measured at **d990abb** (tree including 513b653), 2026-09-17 ~05:50 UTC, in the pinned env
DEF-TEST-SUITE-CANNOT-RUN documents: Python 3.12.10, httpx 0.26.0, starlette 0.35.1,
fastapi 0.109.0, pytest 9.0.2.

## `backend/tests` — 25 failing (1428 passed, 1 skipped)

Identical set before and after R-IV.423, R-IV.426 and R-IV.429.

```
tests/integration/test_feed_tier_v2_replay.py::test_all_ceiling_capped_pullback_entries_stay_capped
tests/signals/test_feed_tier_classifier_v2.py::test_path_a_footprint_long
tests/test_analytics_endpoints.py::TestOracleEndpoint::test_oracle_returns_expected_keys
tests/test_analytics_endpoints.py::TestOracleEndpoint::test_oracle_system_health_shape
tests/test_countertrend.py::TestCountertrendAcceptance::test_accept_counter_short_extreme_bull
tests/test_countertrend.py::TestCountertrendAcceptance::test_accept_counter_long_extreme_bear
tests/test_frontend_routes.py::TestFrontendEndpointsExist::test_endpoint_exists[/api/monitoring/polygon-health]
tests/test_positions.py::TestPositionRoutes::test_list_positions_returns_200
tests/test_positions.py::TestPositionRoutes::test_position_summary_returns_200
tests/test_uw_api_mapping.py::test_get_snapshot
tests/test_uw_api_mapping.py::test_get_bars
tests/test_uw_api_mapping.py::test_get_bars_as_dataframe
tests/test_uw_api_mapping.py::test_get_previous_close
tests/test_uw_api_mapping.py::test_get_options_snapshot
tests/test_uw_api_mapping.py::test_get_flow_recent
tests/test_uw_api_mapping.py::test_get_greek_exposure
tests/test_uw_api_mapping.py::test_get_market_tide
tests/test_uw_api_mapping.py::test_get_darkpool_recent
tests/test_uw_api_mapping.py::test_get_iv_rank
tests/test_uw_api_mapping.py::test_get_earnings
tests/test_uw_api_mapping.py::test_get_economic_calendar
tests/test_uw_api_mapping.py::test_get_short_interest
tests/test_uw_api_mapping.py::test_health
tests/test_webhooks.py::TestTradingViewWebhookSecret::test_wrong_secret_rejected[/webhook/tradingview-payload0]
tests/test_webhooks.py::TestTradingViewWebhookSecret::test_missing_secret_rejected[/webhook/tradingview-payload0]
```

Notes carried from DEF-TEST-SUITE-CANNOT-RUN: these are **not triaged**. The two
`test_countertrend` cases are order-dependent: in the full-suite order both fail, and in other
orders a different one of the pair has been seen to fail — **so compare a full-suite run only
against a full-suite run.** The 14
`test_uw_api_mapping` cases fail with pytest's "async def functions are not natively
supported. You need to install a suitable plugin for your async framework" — no async plugin
runs them in this env, so they have never executed here.

## `backend/hub_mcp/tests/test_tools_smoke.py` — 4 failing (33 passed)

**Outside the `backend/tests` run.** A run of `backend/tests` alone never sees these. Identical
set before and after R-IV.429.

```
hub_mcp/tests/test_tools_smoke.py::test_hermes_ok_with_events
hub_mcp/tests/test_tools_smoke.py::test_trade_ideas_db_unavailable
hub_mcp/tests/test_tools_smoke.py::test_trade_ideas_ok_with_groups
hub_mcp/tests/test_tools_smoke.py::test_trade_ideas_degraded_when_redis_fails
```

As observed (not triaged):
- `test_hermes_ok_with_events` — `assert 0 == 1`, the tool returned no events.
- the three `test_trade_ideas_*` — the test patches `get_postgres_client` /
  `get_active_trade_ideas` on `hub_mcp.tools.trade_ideas`, but the tool imports both INSIDE
  the function (`database.postgres_client`, `signals.feed_service`), so the module has no
  such attributes and the patch raises `AttributeError` before the tool runs. **Those three
  tests never reach the tool**, so the MCP trade-ideas tool has no working smoke test.

## `backend/hub_mcp/tests/test_envelope.py` — 2 failing (registered R-IV.457(g), 2026-09-18)

```
hub_mcp/tests/test_envelope.py::test_status_ok
hub_mcp/tests/test_envelope.py::test_schema_version_is_always_v1
```

**Cause, measured:** the envelope emits `schema_version: v2.0`; both tests assert `v1.0`. They
fail on the tree BEFORE the 2026-09-18 kill-switch work (checked by stashing it and re-running),
so the version was bumped without the tests following. Registered rather than edited: whether
v2.0 is the intended contract is the envelope owner's call, and a test changed to match the code
is a test that no longer checks anything.
