# Audit Report: Trojan Horse + Whale Hunter Signal Delivery

**Date:** March 25, 2026
**Auditor:** Claude Code (Opus 4.6)
**Status:** Complete

---

## 1. Whale Hunter

**Status: BROKEN — No real signals have ever reached the database.**

### Findings

| Check | Result |
|-------|--------|
| Signals in DB (signal_category = DARK_POOL) | **0 rows total** — not just recent, zero ever |
| Webhook endpoint (`POST /webhook/whale`) | **Working** — test payload returned 200, wrote to DB as `Whale_Hunter` / `DARK_POOL` with score 51 |
| Recent API (`GET /webhook/whale/recent/SPY`) | **Working** — returns `{"available": false}` (correct, no cached data) |
| Committee whale context | **NOT WIRED** — `build_market_context()` never fetches whale data; the `whale_volume` key is never set in the context dict despite `committee_context.py` having a full renderer for it (lines 153-175) |
| Committee routing for whale signals | **Bypasses committee** — whale signals route to `format_whale_message()` which asks Nick to post a UW screenshot for confirmation, not to the committee directly |

### Root Cause

The Railway backend webhook handler works. The problem is **upstream**: TradingView alerts for Whale Hunter are either not configured, expired, or erroring. Zero real `DARK_POOL` signals have ever hit the endpoint. This is a TradingView-side issue that requires Nick to verify alert status (Audit Step 6 — manual).

### Committee Gap

Even when whale signals do flow, the committee won't see them in context for other signals. `build_market_context()` (line 617 of `pivot2_committee.py`) fetches bias, DEFCON, circuit breakers, earnings, zone, portfolio, timeframes, CB status, and flow — but **not** whale data. The renderer in `committee_context.py` (line 153) is ready and waiting for `context["whale_volume"]`, but nothing populates it.

---

## 2. Trojan Horse (Footprint)

**Status: FLOWING — Actively delivering signals.**

### Findings

| Check | Result |
|-------|--------|
| Signals in DB (strategy = Footprint_Imbalance) | **20+ signals** in last 5 days. Most recent: GLD SHORT, 2026-03-26 01:15 UTC |
| Active tickers | GLD, NVDA, NBIS, SMH, GOOGL, CRCL, IGV, QQQ, PLTR, URA |
| Scores | Range 23.80–41.80 (base DEFAULT 30 + technical bonuses) |
| Webhook endpoint (`POST /webhook/tradingview`) | **Working** — test payload returned 200 |
| Dedup | Working (300s window) |
| v2 handler brief implemented? | **YES — fully implemented** |

### v2 Field Status (from brief-trojan-horse-v2-handler.md)

| Build | Status |
|-------|--------|
| Build 1: v2 fields in Pydantic model (`density_pct`, `zone_coverage_pct`, `vol_ratio`) | Done (lines 59-61) |
| Build 2: v2 fields in Redis cache | Done (lines 157-159) |
| Build 3: v2 fields in pipeline metadata | Done (lines 202-204) |
| Build 4: Dead absorption references removed | Done — `_sub_type_display` and docstring cleaned |

### Observations

- All footprint signals score 30-42, which is below the visibility threshold for most views. They never surface in Agora Insights unless "Show all scores" is enabled.
- `FOOTPRINT_LONG` and `FOOTPRINT_SHORT` are not in `STRATEGY_BASE_SCORES` — they fall through to `DEFAULT: 30`. The v2 brief's "Future Consideration" section recommends adding them with v2 quality-gate scoring modifiers once enough data accumulates. The forward test ends March 28.
- The v2 PineScript is deployed (confirmed by signals flowing), but it's unclear if the v2 fields (`density_pct`, `zone_coverage_pct`, `vol_ratio`) are actually populated in incoming payloads — the DB doesn't store the metadata column, so we can't confirm from the signals table. Redis cache would show it if a recent signal is cached.

---

## 3. Action Items (Priority Order)

### P0 — Nick (Manual)
1. **Check TradingView Whale Hunter alerts.** Open TradingView Alerts panel and verify:
   - Are Whale Hunter alerts active or errored/expired?
   - Which of the 32 tickers have active alerts?
   - Is the webhook URL set to `https://pandoras-box-production.up.railway.app/webhook/tradingview`?
   - Note: Whale signals route through `/webhook/whale` (direct) OR through `/webhook/tradingview` if the payload has `"signal": "WHALE"` — check which URL the TV alerts use.

### P1 — Code Fix
2. **Wire whale context into committee.** Add a whale data fetch to `build_market_context()` in `pivot2_committee.py` so the committee can see whale signals when reviewing any ticker:
   ```
   # After section 9 (flow context), add:
   # 10. Whale volume context
   whale_context = {}
   try:
       ticker = str(signal.get("ticker") or "").upper()
       if ticker:
           whale_raw = http_json(url=f"{base}/webhook/whale/recent/{ticker}", headers=headers, timeout=10)
           if isinstance(whale_raw, dict) and whale_raw.get("available"):
               whale_context = whale_raw.get("whale", {})
   except Exception:
       pass
   # Add to return dict: "whale_volume": whale_context
   ```

### P2 — Scoring Enhancement
3. **Add footprint signal types to STRATEGY_BASE_SCORES** (after March 28 forward test concludes):
   - `"FOOTPRINT_LONG": 40` and `"FOOTPRINT_SHORT": 40` in `trade_ideas_scorer.py`
   - Add v2 quality-gate scoring modifiers: bonus for high `density_pct` (>60%), high `zone_coverage_pct` (>50%), high `vol_ratio` (>2.0)

### P3 — Cleanup
4. **Delete TEST_AUDIT signal from database.** One test row (id=4977) was created during this audit. Needs manual SQL: `DELETE FROM signals WHERE ticker = 'TEST_AUDIT';`

---

## Summary

| Source | Signal Flow | DB Records | Webhook | v2 Brief | Committee Access |
|--------|------------|------------|---------|----------|-----------------|
| Whale Hunter | **BROKEN** (0 signals ever) | 0 rows | Working | N/A | Not wired |
| Trojan Horse | **FLOWING** | 20+ last 5 days | Working | Fully implemented | N/A (not routed to committee) |

**Bottom line:** Trojan Horse is healthy and delivering. Whale Hunter's backend is ready but TradingView isn't sending anything — Nick needs to check alert status. The committee can't see whale data even when it flows because `build_market_context` doesn't fetch it.
