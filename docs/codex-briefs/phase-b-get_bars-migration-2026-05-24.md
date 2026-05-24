# CC Brief: Phase B — `get_bars` migration off yfinance to UW (2026-05-24)

**Bucket:** ZEUS Phase I, foundation hygiene. Smaller than Phase A or Phase C.
**Branch strategy:** Direct on `main` (focused, low-risk refactor; no feature flag needed). Same smoke-then-revert discipline as the C.1 cycles.
**Predecessors:**
- Phase A shipped `get_ohlc()` wrapper (`backend/integrations/uw_api.py`) which Phase B will consume.
- Phase A.3 shipped TTL bumps to `ohlc` and `technical_indicator` cache categories (60s → 300s).

## Purpose

`get_bars()` is the last yfinance dependency in the hot path. Per Data Source Hierarchy in `PROJECT_RULES.md`:

| Data Type | Primary Source | Fallback |
|---|---|---|
| Equity/ETF daily bars | UW API `uw_api.get_bars()` | yfinance |

Hierarchy says UW is primary, yfinance is fallback. The current implementation has it inverted — yfinance is sole source, no UW call. Phase B flips the polarity: UW is primary, yfinance becomes the documented fallback for resilience and for indices/breadth (`^VIX`, `^GSPC`, `^ADVN`, `^DECLN`) that UW does not cover.

## Pre-flight (mandatory)

1. `cd /d C:\trading-hub`
2. `git fetch && git status` — confirm clean working tree on `main` at post-rev2-revert SHA (currently `6d53857`).
3. Read `PROJECT_RULES.md` § Data Source Hierarchy.
4. Read `backend/integrations/uw_api.py` sections relevant to `get_bars`, `get_ohlc`, `get_bars_as_dataframe`, `get_previous_close` (in-context already from this session).
5. Confirm `UW_API_KEY` and `REDIS_URL` set in Railway env. Do NOT print, log, or commit values.

## Tasks

### Task 1 — Replace `get_bars()` body to call `get_ohlc()`, translate response

In `backend/integrations/uw_api.py:467-491`:

- Keep the public signature stable: `get_bars(ticker, multiplier=1, timespan="day", from_date=None, to_date=None)`.
- Keep the cache layer stable: same `quote` category, same key shape.
- New behavior:
  1. Compute `lookback_days` from `(today - from_date)` or default to ~60 if no `from_date` provided. Cap at the largest range any current consumer asks for + buffer.
  2. Call `get_ohlc(ticker, candle_size="1d", lookback_days=N)` for daily bars (the only `timespan` any consumer uses today — verified via grep).
  3. Filter to regular-session bars: `b.get("market_time") == "r"` — matches yfinance's "one bar per trading day" semantic. (Including pre/post bars would change downstream calculations.)
  4. Translate each UW bar to Polygon shape (the public contract that all consumers rely on):
     - `open`, `high`, `low`, `close` → `o`, `h`, `l`, `c` (float)
     - `total_volume` (or `volume` fallback) → `v` (int)
     - `vwap` → `vw` if present, else `None`
     - `trades` → `n` if present, else `None`
     - `start_time` (ISO string from UW) → `t` (epoch milliseconds int)
  5. Apply date range filter (`from_date`, `to_date`) AFTER translation — slice the list to the requested window.
  6. **Fallback:** if UW returns None (rate limit, circuit breaker, or upstream blip), fall through to `_fetch_yfinance_bars()` with a WARNING log. **Preserves resilience** during the transition window; we can remove the fallback later once Phase B has soaked.

### Task 2 — Verify `get_bars_as_dataframe()` and `get_previous_close()` still work

Both are at `backend/integrations/uw_api.py:494-527` and `:530-542` respectively. Both consume `get_bars()` output via the public Polygon shape. With the contract preserved by Task 1, no edits expected — but verify:
- `get_bars_as_dataframe()` builds a pandas DataFrame with `Date` index from `t` (ms epoch). Works as long as `t` is correctly populated.
- `get_previous_close()` slices `bars[-2]` and rewraps. Same.

If either needs adjustment, scope creep — document and ask before changing.

### Task 3 — Smoke tests (must pass before merging to main)

Direct curl/Python checks against the deployed service:

1. **Bars endpoint shape unchanged.** Hit `GET /market/bars?ticker=SPY&days=30` (or whatever the existing route is — verify in `backend/api/market_data.py`); confirm response is a list of `{o,h,l,c,v,vw,t,n}` dicts with reasonable values.
2. **Sector heatmap historical bars work.** Hit `GET /api/sectors/heatmap` — uses `_fetch_all_bars()` which calls `get_bars()`. Should return non-empty sector data with weekly/monthly change calculations.
3. **`get_bars_as_dataframe()` works.** Hit any endpoint that uses it (`scanners/hydra_squeeze` or `bias_engine/factor_utils`).
4. **yfinance fallback fires when UW unavailable.** Optional/manual: temporarily set `UW_API_KEY` to invalid value locally; confirm WARNING log + yfinance result returns.
5. **Indices still work via yfinance.** `^VIX`, `^GSPC`, `^ADVN`, `^DECLN` — UW doesn't carry these. Phase B should NOT break them; the yfinance fallback path should keep handling them. Verify by hitting whatever route consumes them (bias_engine has factor_utils that uses `^VIX`).

### Task 4 — Documentation cleanup

- Update the docstring on `get_bars()` to reflect "UW primary, yfinance fallback."
- Confirm `PROJECT_RULES.md` Data Source Hierarchy is already accurate (it should already say UW primary per the table). If not, update.
- Sector module docstring (`backend/api/sectors.py:1-9`) — re-check after the Phase A.3 hygiene pass; should already reflect UW-first. Skip if accurate.

### Task 5 — Closure note

Author `docs/strategy-reviews/phase-b-get_bars-migration-closure-note-2026-05-24.md`. Cover:
- Before/after of `get_bars()` body (10-line diff or so).
- Smoke results (all 5 checks).
- Indices/breadth fallback validation.
- Any consumer that needed adjustment.
- Tier 2 follow-up: once Phase B has soaked for ~7 days clean, remove the yfinance fallback from `get_bars()`; keep yfinance only in `_yf_quote_sync` / `_fetch_yfinance_bars` for the indices/breadth path (`^VIX` etc.).

## Output spec

- Modified: `backend/integrations/uw_api.py` (`get_bars` body)
- Possibly modified: docstrings only (Tasks 4)
- New: `docs/strategy-reviews/phase-b-get_bars-migration-closure-note-2026-05-24.md`

Commit messages:
- Implementation: `feat(integrations): Phase B — get_bars uses UW /ohlc/1d (yfinance fallback)`
- Closure: `docs(strategy-reviews): Phase B closure note`

## Gates / what NOT to do

- Do NOT change the public signature of `get_bars()`. Consumer breakage is unacceptable.
- Do NOT change the Polygon-compatible return shape. Every key (`o, h, l, c, v, vw, t, n`) stays.
- Do NOT remove yfinance imports or `_fetch_yfinance_bars()` in this phase. They stay as fallback for `get_bars()` and as the primary path for indices/breadth.
- Do NOT change the cache schema or cache key. Existing cached entries continue to serve.
- Do NOT touch `unified_positions`, `signal_outcomes`, `signals`, or canonical data tables.
- Do NOT introduce new credentials.
- Do NOT bundle other work (Phase C, OAuth rev3, Outcome Tracking Phase C) into this brief.

## Olympus Impact

Zero direct impact. `get_bars()` is consumed by bias engine + scanners + analysis, none of which are Olympus skills. Indirect benefit: cleaner data lineage means committee agents that eventually pull bar data via hub MCP (Phase C future state) inherit a more consistent source.

**Required post-build smoke (Task 3):** if any consumer of `get_bars` is on an Olympus path (none identified in pre-flight grep, but worth a final check), one committee pass on SPY post-deploy confirms no regression.

## Done definition

- `get_bars()` calls UW `/ohlc/1d` primary, yfinance fallback.
- Public signature + return shape preserved.
- All 5 smoke checks pass.
- Closure note authored.
- Commit pushed to `main`.
- Service responsive after deploy (`/health` 200, leaders endpoint timing in normal range).
- Stop and notify Nick when complete.

## Notes for the implementer

- This is a 30-min-ish refactor on the hot path. The bigger risk is consumer breakage from a subtle shape difference, not code complexity. The smoke tests catch that.
- `get_ohlc()` already has the right rate-limit + circuit-breaker + cache semantics. Leverage it; don't reimplement.
- `_fetch_yfinance_bars()` returns bars with `vw=None, n=None` historically — UW may give us better values for those. Optional polish; not in scope.
- If a consumer ends up needing intraday bars (`timespan="hour"` or `"minute"`), that's a separate brief — Phase B is daily-only because that's what consumers ask for today.
- Standard merge-then-smoke-then-revert-if-fails discipline. No feature branch needed for a refactor this contained; commit directly to `main` after greenlight.
