# Phase 5: Countertrend Lane + STRC Circuit Breaker

**Created:** March 16, 2026
**Status:** TITANS APPROVED — ready for CC brief
**Olympus Approval:** March 16, 2026 (unanimous conditional yes)
**Titans Approval:** March 17, 2026 (all four approve with corrections)
**Greek Name:** Nemesis (goddess of retribution against hubris — fitting for a strategy that punishes overextended crowds)

---

## Summary

Two related additions to the trading system:

1. **Nemesis (Countertrend Lane)** — A new pipeline lane that allows whitelisted countertrend strategies to bypass the bias engine's directional gate under strict conditions. First strategy: WRR Buy Model (Linda Raschke).

2. **STRC Circuit Breaker** — A visual alert in the Stater Swap UI that monitors Strategy's preferred stock (STRC) and warns when it drops below $100 par value, signaling that a major structural BTC buyer may lose its funding mechanism.

---

## Work Item 1: Nemesis (Countertrend Lane)

### What It Does
Adds a `lane` field to the signal pipeline. Currently all signals are implicitly `lane: trend` and must pass bias alignment. Countertrend signals get `lane: countertrend` and are evaluated by a separate set of gating rules.

### Architecture Changes (Post-Titans Corrections)

#### A. Scoring & Pipeline Modification (backend)
**ATLAS correction:** There is no standalone "gatekeeper" function. Bias alignment is applied as a **score multiplier** inside `calculate_signal_score()` in `backend/scoring/trade_ideas_scorer.py`. The existing `contrarian_qualifier.py` already restores the penalty for qualifying counter-bias signals.

The `lane` field is set on signal_data *before* it enters `process_signal_unified()`. Inside `apply_scoring()` (in `backend/signals/pipeline.py`), when `lane == "countertrend"`:
- Fetch composite score
- If composite is NOT at extreme (>25 and <75): **reject the signal entirely** — log and return, don't score
- If composite IS at extreme: score normally with bias_alignment multiplier = 1.0 (no penalty, no bonus)
- After scoring, if `score_v2 < 90`: downgrade to LOW priority, don't flag for committee

In `_maybe_flag_for_committee()` (in `pipeline.py`): if `signal_data.get("lane") == "countertrend"` then committee threshold = 90 (vs. standard 75).

`COUNTERTREND_WHITELIST` is a Python constant in the scoring module (not DB). Initially: `["WRR"]`.

- Add `position_size_modifier: 0.5` to countertrend trade ideas (informational — Nick sizes manually)
- Override `expires_at` to 24-48 hours from signal time for countertrend lane

#### B. WRR Scanner (backend)
- New file: `backend/strategies/wrr_buy_model.py`
- Server-side scanner (like Scout Sniper — no TradingView alert slot needed)
- **Data source: Polygon.io** (Stocks Starter plan) for daily bars. Fallback to yfinance only if Polygon unavailable.
- Runs against full 207-ticker Primary Watchlist (daily after-close scan is light compute)
- Checks: consecutive down days, RSI(3), reversal candle pattern, volume spike, proximity to support, ROC(10)
- Output: candidate signals routed through `process_signal_unified()` with `lane: countertrend`
- Scheduling: run once daily after market close (4:15 PM ET) via existing cron or new scheduled task

#### C. Trade Ideas UI (frontend — Agora)
- Tag pill: amber/orange with text "↺ COUNTERTREND" next to score badge
- "HALF-SIZE" subtitle text below ticker name, same amber color
- Show `lane` in Trade Idea detail view
- Show accelerated expiry countdown (existing countdown, just reflects shorter 24-48h window)

#### D. Committee Pipeline
- No changes to committee prompt structure needed
- Add `lane` context to the committee prompt so analysts know they're evaluating a countertrend setup
- Countertrend signals include note: "This signal is AGAINST the prevailing bias. Evaluate whether the extreme condition justifies a countertrend entry."

#### E. Strategy Backlog Update
- Already done: WRR moved to "Promoted" section, references `docs/approved-strategies/wrr-buy-model.md`

### Files Touched (Corrected per Titans)
- `backend/strategies/wrr_buy_model.py` — NEW (scanner)
- `backend/scoring/trade_ideas_scorer.py` — MODIFY (lane-aware multiplier logic)
- `backend/signals/pipeline.py` — MODIFY (lane-aware committee threshold + expiry override + countertrend rejection)
- `frontend/app.js` — MODIFY (Trade Ideas rendering for countertrend badge)
- `frontend/styles.css` — MODIFY (countertrend visual treatment)

### Definition of Done
- [ ] WRR scanner runs daily after close and produces candidate signals (Polygon data)
- [ ] Countertrend signals pass through the pipeline with `lane: countertrend`
- [ ] Scoring applies neutral multiplier (1.0) for countertrend at bias extremes
- [ ] Signals at non-extreme bias are rejected (not scored)
- [ ] Committee threshold is 90 for countertrend lane
- [ ] Trade Ideas UI shows countertrend badge with half-size and accelerated expiry indicators
- [ ] Committee prompt includes lane context for countertrend signals
- [ ] At least one test covering the countertrend scoring branch

---

## Work Item 2: STRC Circuit Breaker (Stater Swap)

### What It Does
Monitors STRC (Strategy Stretch Preferred Stock) price. When STRC is below $100 par value, displays a persistent visual warning in the Stater Swap (crypto trading) UI. This is a structural risk indicator — STRC below par means Strategy's primary BTC funding mechanism is impaired.

### Why Stater Only
This is crypto-specific alpha. STRC's relevance is entirely about BTC structural demand. It has no bearing on the equities/options side (Agora).

### Architecture (Post-Titans Corrections)

#### A. STRC Price Check (backend)
- Add STRC to the watchlist/ticker universe
- **Data source: Polygon.io** (STRC is a US-listed preferred stock, covered by Stocks Starter plan). Fallback to yfinance only if Polygon unavailable.
- **ATLAS correction:** No dedicated REST endpoint. Store in Redis key `circuit_breaker:strc` with `{price, below_par, par_level, last_updated}`. Frontend polls alongside existing crypto data.
- Polled every 5 minutes during market hours. Redis TTL: 5 minutes.
- **AEGIS addition:** Staleness detection — if Redis key hasn't updated in >15 minutes, frontend shows "STRC data stale" instead of last cached price. Prevents silent failure.
- No auth needed (read-only public market data)

#### B. Stater Swap UI (frontend)
- **HELIOS correction:** Sticky banner ABOVE the Stater Swap price bar, not inline in it.

```
┌──────────────────────────────────────────────────┐
│ ⚠ STRC BELOW PAR ($98.50) — Strategy funding     │  ← amber/red banner
│   at risk. Structural BTC bid weakening.          │
├──────────────────────────────────────────────────┤
│ BTC: $83,421  |  24H: -1.2%  |  Funding: +0.01% │  ← existing price bar
└──────────────────────────────────────────────────┘
```

- Color system:
  - `$95 ≤ STRC < $100`: amber background (`#f59e0b` / `--color-warning`)
  - `STRC < $95`: red background (`#ef4444` / `--color-danger`)
  - `STRC ≥ $100`: banner hidden entirely (no DOM footprint)
- NOT dismissible — stays visible as long as STRC < $100
- CC brief must include DOM anchor grep instructions for Stater Swap section injection point

#### C. Optional: Discord Alert
- One-time alert to Discord when STRC first crosses below $100
- De-duplicate: only fire once per crossing event (use Redis flag `circuit_breaker:strc:alerted`)

### Files Touched (Corrected per Titans)
- `backend/data/` or market data fetcher — MODIFY (add STRC to Polygon polling)
- `frontend/app.js` — MODIFY (Stater Swap section, circuit breaker banner rendering)
- `frontend/styles.css` — MODIFY (circuit breaker warning styles)
- DB: Add STRC to watchlist table if applicable

### Definition of Done
- [ ] STRC price is fetched via Polygon.io and cached in Redis (5-min TTL)
- [ ] Staleness detection: frontend shows "data stale" if >15 min old
- [ ] Stater Swap UI shows sticky warning banner above price bar when STRC < $100
- [ ] Warning bar uses amber ($95-100) / red (<$95) color coding
- [ ] No warning shown when STRC ≥ $100
- [ ] STRC added to watchlist

---

## Build Sequence

1. ~~Titans Review~~ ✅ APPROVED (March 17, 2026)
2. **CC Brief writing** ← NEXT STEP (split: Brief 5A = STRC, Brief 5B = Nemesis)
3. Titans final review of briefs
4. CC executes 5A first (simpler, immediately useful for prop account)
5. CC executes 5B (scanner + scoring + UI)

---

## Titans Review Notes (March 17, 2026)

### Key Corrections Applied
1. **ATLAS:** No standalone gatekeeper function exists. Lane logic targets `trade_ideas_scorer.py` (multiplier path) and `pipeline.py` (committee threshold + expiry). STRC uses Redis key, not dedicated REST endpoint.
2. **HELIOS:** STRC warning is sticky banner above price bar, not inline. CC brief needs DOM anchor grep instructions.
3. **AEGIS:** No auth for STRC. Added staleness detection (>15 min). Countertrend whitelist is Python constant, not DB.
4. **ATHENA:** Full 207-ticker watchlist for WRR scanner. Split into Brief 5A + 5B.
5. **DATA SOURCE:** All market data uses **Polygon.io first**, yfinance as fallback only.
