# Strategy Backlog — Evaluated but Not Integrated

**Last Updated:** March 6, 2026
**Purpose:** Track strategies that have been evaluated by the Trading Committee or discussed for integration but were deferred, rejected, or are pending further work.

---

## Deferred Strategies

### WRR Buy Model (Linda Raschke)
- **Evaluated:** Feb 2026
- **Verdict:** DEFERRED — countertrend conflict
- **Reason:** The WRR Buy Model is a countertrend/mean-reversion strategy. It conflicts with the system's trend-following bias (CTA framework, Holy Grail, etc.). Adding countertrend signals alongside trend-following signals would create conflicting recommendations in the committee pipeline.
- **Revisit when:** If a dedicated countertrend module is built with separate risk rules and committee context.

### Dollar Smile Strategy
- **Evaluated:** Feb 2026
- **Status:** Webhook setup doc exists (`docs/tradingview-webhooks/dollar-smile-setup.md`) but no TradingView alert was ever configured, no signals have been generated.
- **Verdict:** DEFERRED — incomplete implementation
- **Reason:** The strategy uses DXY (Dollar Index) regime to filter equity signals. The concept is sound but it was never wired end-to-end. The Whale Hunter v2 has an optional DXY context overlay that partially covers this concept.
- **Revisit when:** If DXY macro context becomes a priority for signal filtering.

### HTF Reversal Divergences (LuxAlgo)
- **Evaluated:** Mar 2026 (committee evaluation initiated but not completed)
- **Indicator:** LuxAlgo engulfing/hammer/shooting star + RSI divergence + HTF PO3 with volume delta
- **Verdict:** PENDING — evaluation started via React artifact but session ended before completion
- **Revisit when:** Next strategy review session. Has potential as a reversal confirmation layer.

---

## Pending Integration Decisions

### LBR 3/10 Oscillator
- **PineScript:** In repo (`docs/pinescript/lbr_3_10_oscillator.pine`) — visual only
- **Evaluated:** Feb 2026
- **Options:**
  1. **Bias factor** — Use daily 3/10 crossover as a momentum factor in the composite bias engine
  2. **Signal source** — Wire as a webhook to generate trade ideas (momentum thrust signals)
  3. **Visual only** — Keep as chart reference, no pipeline integration
- **Decision needed:** Which option best fits the current architecture. The bias engine already has 20 factors; adding another needs to justify its weight.

### UW Flow as Independent Signal Source
- **Current state:** UW Watcher captures institutional flow to Redis (1h TTL). Committee sees it as context only.
- **Proposed:** High-conviction UW flow ($1M+ sweeps on watchlist tickers) should trigger committee review directly, not just sit as passive context.
- **Flagged in:** TODO.md Phase 1
- **Decision needed:** Threshold definition (what volume/premium qualifies?), deduplication against existing signals, cost impact on committee runs.

### Absorption Wall Detector
- **PineScript:** In repo (`docs/pinescript/webhooks/absorption_wall_detector_v1.5.pine`)
- **TV alerts:** Configured and firing
- **Problem:** Uses pipe-delimited payload format, not JSON. No Railway handler exists to receive the data.
- **Options:**
  1. Build a Railway handler that parses the pipe format
  2. Rewrite the PineScript alert payload to JSON and route through `process_generic_signal()`
  3. Keep as visual-only until a dedicated handler is built
- **Decision needed:** Is the signal valuable enough to justify handler work?

---

## Rejected Strategies

*None formally rejected yet. All evaluated strategies are either active, deferred, or pending.*

---

## Dead Code Candidates

These exist in the codebase but have unclear status:

### Hybrid Scanner (`backend/scanners/hybrid_scanner.py` — 42KB)
- UI was killed in Brief 09
- Backend API still mounted in `main.py` (`/api` prefix, "hybrid-scanner" tag)
- **Question:** Is anything calling these endpoints? If not, this is 42KB of dead code plus an unnecessary import in main.py.
- **Action:** Grep for `hybrid_scanner` or `/api/hybrid` calls in frontend code. If no callers, remove the router import from main.py and archive the file.

### Old Holy Grail PineScript (`docs/pinescript/holy_grail_pullback.pine`)
- Superseded by `webhooks/holy_grail_webhook_v1.pine`
- No webhook capability, visual alerts only
- **Action:** Move to `docs/pinescript/archive/` or delete.
