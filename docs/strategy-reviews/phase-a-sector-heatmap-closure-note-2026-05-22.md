# Phase A — Sector Heatmap Closure Note (2026-05-22)

**Status:** Shipped to main (pending push)
**Brief:** `docs/codex-briefs/` (this build was authored from a CC brief delivered to Claude Code inline; no separate brief file was committed prior to execution per the inline-brief workflow).
**Audit predecessor:** `docs/uw-integration-audit-2026-05-22.md`
**Olympus Titans review:** Pass 1 → Nick injection → Pass 2 → ATHENA Overview (2026-05-22).

---

## 1. What shipped

1. **`backend/integrations/uw_api.py`** — two new public wrappers and one refactor:
   - `get_ohlc(ticker, candle_size, lookback_days=30)` wraps `/api/stock/{ticker}/ohlc/{candle_size}`. Token-bucket-aware and circuit-breaker-protected via the existing `_uw_request` path. 60s Redis TTL under the new `ohlc` category.
   - `get_technical_indicator(ticker, function="RSI", lookback=14)` wraps `/api/stock/{ticker}/technical-indicator/{function}`. Currently supports `function="RSI"`; the docstring documents how to expand. 60s Redis TTL under the new `technical_indicator` category.
   - `_get_regular_session_change` refactored to call `get_ohlc(ticker, "1d", lookback_days=10)` rather than `_uw_request` directly. One canonical entry point shared between the snapshot helper and the new refresh job.

2. **`backend/integrations/uw_api_cache.py`** — added `ohlc` and `technical_indicator` cache categories (60s TTL each).

3. **`backend/integrations/sector_cache.py`** — NEW module. Canonical envelope-shape cache with three operations:
   - `write_field(ticker, field, value, source="UW")` — writes `{"value": float|None, "ts": ISO8601, "source": "UW"}` at `sector:constituent:{TICKER}:{field}`. Null writes intentional — record that a refresh ran with no usable data.
   - `read_field(ticker, field)` — single envelope read.
   - `read_many(tickers, fields)` — batch MGET roundtrip used by the popup route.
   - No TTL on writes — the refresh job's cadence is the freshness contract; readers see freshness via the `ts` field.

4. **`backend/jobs/sector_constituent_refresh.py`** — NEW job. Exposes two entry points:
   - `refresh_fast()` — pulls 30-day OHLC + RSI(14) per constituent, derives WK% (5-session) and writes RSI(14) envelope. Headroom guard: when the UW token bucket drops below 20% of capacity, WK refresh is dropped for remaining constituents while RSI continues (most operationally visible gap). Audit lines: `[sector_refresh] fast tick start/complete` with universe size, wk_ok, rsi_ok, failures, skipped_wk, elapsed.
   - `refresh_slow()` — pulls 35-day OHLC per constituent, derives MO% (21-session). Headroom guard not applied — 1-hour cadence already keeps UW load minimal.

5. **`backend/main.py`** — two new scheduler loops registered as `sector_refresh_fast_task` and `sector_refresh_slow_task`. Fast loop: 60s cadence in-market, 300s off-hours. Slow loop: 3600s cadence regardless of market state. Both wait for the DB pool + sector seed to land (150s and 300s startup delays respectively).

6. **`backend/api/sectors.py`** — three changes:
   - Module docstring rewritten — the "yfinance under the hood" framing was inaccurate since the 2026-04-28 `get_snapshot` migration. Per the audit's Section 1 hotfix list.
   - `_fetch_sector_snapshot` docstring de-staled.
   - `_get_rsi_for_ticker` private helper deleted; replaced by `sector_cache.read_many` batch read at the start of the `/sectors/{etf}/leaders` route (envelope-shape surfaced for `week_change_pct`, `month_change_pct`, `rsi_14`).
   - Hardcoded `None` for week/month change removed.

7. **`backend/api/ticker_profile.py`** — `_get_rsi` legacy helper replaced by `_get_rsi_envelope` + `_get_change_envelope` (sector_cache-backed). Profile route now surfaces envelope shape for `rsi_14`, `week_change_pct`, `month_change_pct`. Quick-review path (`POST /committee/quick-review`) extracts the scalar from the envelope before formatting the prompt — no committee-visible behavior change.

8. **`frontend/app.js`** — envelope rendering for both popup paths:
   - New helpers `_envValue`, `_envAge`, `_formatAge`, `_cellMeta` translate envelope shape → display value + small per-cell annotation ("UW · 12s ago" or "stale" / "n/a").
   - `_sectorPopupRow` updated to render envelope for WK%, MO%, RSI(14).
   - `_tpRow` updated to accept envelope OR raw number, gracefully degrading for legacy fields.
   - Ticker profile RSI display path (`tpPriceBody` render) updated for envelope.

9. **`frontend/styles.css`** — new `.cell-meta` and `.cell-meta-stale` classes. Tiny font (0.62em), lower-contrast color from existing palette, block layout with 1px top margin. Designed not to materially increase row height (single line of text, 8px effective height at base font).

10. **`frontend/index.html`** — cache-bust bumps: `styles.css?v=138`, `app.js?v=156`.

---

## 2. What changed from the brief

- **Audit logging:** Brief mentioned `/var/log/committee_audit.log` as a possible target. That log lives on the VPS, not Railway. The refresh job writes audit lines via Python's standard `logger.info` under the `sector_refresh` logger name with a `[sector_refresh]` prefix. Railway's log capture is the persistence layer; queryable via `railway logs` per the existing pattern.

- **`docs/operations/` runbook:** Brief said "Document in `docs/operations/` if a runbook is the convention for cron documentation." The existing `docs/operations/` directory contains only MCP-specific guides (`mcp-connection-guide.md`, `mcp-token-rotation.md`); no cron runbook convention is established for the existing 15+ scheduled loops. This closure note documents the cadence + envelope schema instead. If a cron runbook convention emerges later, extract Section 1 entries 4–5 into it.

- **Annotation rendering choice:** Brief allowed "subscript or small annotation per cell ... or tooltip on hover. Pick the option that doesn't increase row height materially." Chose inline `<span class="cell-meta">` block — visible without hover (per the brief's "annotations visible per spec" line), 0.62em font + block layout takes ~8px which is well within the existing row padding budget.

---

## 3. What was deferred / out of scope

- **Phase A.5** (ticker info sub-card under heatmap row): not in this build. Pending separate Titans review of inline sub-card pattern.
- **Phase B** (bars on UW, not yfinance): not in this build. `get_bars` still uses yfinance; was not in Phase A scope per the brief.
- **Olympus committee tactical upgrades** (Phase C): not started; will reference this closure note for the cache pattern.

---

## 4. Olympus impact

Per the Titans cross-reference rule (`skills/_shared/TITANS_RULES.md` § Olympus Cross-Reference), the impact assessment:

1. **Which Olympus skills are touched.** None directly. The committee skills (TORO, URSA, PYTHIA, PYTHAGORAS, DAEDALUS, THALES) read via `hub_mcp` tools (`hub_get_quote`, `hub_get_bias_composite`, `hub_get_flow_radar`, etc.). Grep confirms no `hub_mcp` module imports any module modified in this build.
2. **What committee behavior changes.** None. The `enrichment/context_modifier.py:196` `_get_rsi` private helper (a separate copy of the legacy Redis-fanout pattern, distinct from the `_get_rsi_for_ticker` deleted from `sectors.py`) is untouched. It still reads legacy `rsi:{ticker}` / `indicator:rsi:{ticker}` / `scanner:rsi:{ticker}` keys. Bias engine pipeline behavior is unchanged.
3. **Post-build re-test required.** Light smoke-test on a known-good ticker (SPY). Not invocable from Claude Code — the committee runs in Claude.ai conversations per `PROJECT_RULES.md`. **Action item for Nick:** when convenient, run one committee pass on SPY and confirm output matches the pre-build baseline. Quickest verification path: trigger an Olympus quick-review via the dashboard's `Run Olympus Review` button after deploy.

**Phase C inheritance.** The envelope pattern `{value, ts, source}` introduced here is the canonical shape Phase C will adopt for committee enrichment caching. Keep the shape stable. Phase C will add new fields (e.g., `greek_exposure`, `net_premium`, `flow_alert_score`) at new Redis keys (`committee:enrichment:{ticker}:{field}`) following the same envelope contract.

---

## 5. Post-build smoke-test outcomes

| Check | Method | Result |
|---|---|---|
| Python syntax across 7 modified files | `python -c "ast.parse(open(f).read())"` for each | All 7 parse |
| Removed helpers have no remaining callers | grep `_get_rsi_for_ticker` across `backend/` | 0 matches (clean removal) |
| Cache categories registered in TTL map | grep `ohlc\|technical_indicator` in `uw_api_cache.py` | 2 entries, 60s each |
| Olympus-facing modules unmodified | grep `from api\.sectors\|from api\.ticker_profile` outside main.py routing | 0 matches outside FastAPI router registration |
| `hub_mcp` consumers of touched code | grep `sectors\|ticker_profile\|sector_cache\|get_ohlc\|get_technical_indicator` in `backend/hub_mcp/` | 1 match (`sector_strength.py:80` — local variable named `sectors`, not an import) |
| `_get_regular_session_change` semantics | Refactored to call new `get_ohlc` wrapper; UW response shape passed through unchanged | No behavior change for callers |

**Deferred verification:** Railway deploy verification (per `PROJECT_RULES.md` § Deployment Verification, step 3 — empirical confirmation the patched code is live) is the user's next step after `git push`. Recommended check: hit `GET /sectors/XLK/leaders` and confirm at least one constituent has `week_change_pct: {value: <number>, ts: "...", source: "UW"}` (not raw null) once the refresh job has completed its first tick (~3 minutes after Railway deploy goes green).

---

## 6. Rate-limit envelope notes

UW Basic plan: 120 req/min. The fast loop's worst case (220 constituents × 2 calls = 440 calls per tick) saturates the bucket; the token-bucket limiter inside `_uw_request` self-paces and the actual tick duration extends to ~3.7 minutes. The fast loop's outer `sleep(60 - elapsed)` clamps to a 5s minimum, so when a tick overruns its cadence the next tick fires immediately — the limiter handles the back-pressure.

The slow loop's per-tick cost (220 OHLC pulls only, 60-min cadence) is ~1.83 minutes at full token utilization; comfortable headroom for other UW callers.

If the constituent universe grows materially (e.g., expand to mid-caps), or if the plan tier changes, revisit cadence math. The headroom guard at 20% of bucket capacity is conservative enough to absorb 1.5× universe growth without breaching budget.

---

## 7. Files touched

```
backend/api/sectors.py               (modified)
backend/api/ticker_profile.py        (modified)
backend/integrations/sector_cache.py (new)
backend/integrations/uw_api.py       (modified)
backend/integrations/uw_api_cache.py (modified)
backend/jobs/sector_constituent_refresh.py (new)
backend/main.py                      (modified — 2 new scheduler loops)
frontend/app.js                      (modified)
frontend/index.html                  (modified — cache-bust)
frontend/styles.css                  (modified — .cell-meta class)
```

Total: 8 files modified, 2 files created.
