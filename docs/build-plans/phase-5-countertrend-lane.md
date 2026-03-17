# Phase 5: Countertrend Lane + STRC Circuit Breaker

**Created:** March 16, 2026
**Status:** PENDING TITANS REVIEW
**Olympus Approval:** March 16, 2026 (unanimous conditional yes)
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

### Architecture Changes

#### A. Gatekeeper Modification (backend)
- Add `lane` field to signal/trade idea schema (default: `trend`)
- In the gatekeeper logic (wherever bias alignment is checked before committee), add a branch:
  - If `lane == trend` → existing behavior (bias must align with signal direction)
  - If `lane == countertrend` → apply countertrend rules:
    - Bias composite must be at extreme (≤25 for longs, ≥75 for shorts)
    - Confluence score must be ≥ 90 (vs. normal MAJOR=85)
    - Strategy must be in `COUNTERTREND_WHITELIST` (initially just `WRR`)
- Add `position_size_modifier: 0.5` to countertrend trade ideas
- Set `expires_at` to 24-48 hours from signal time (vs. standard window)

#### B. WRR Scanner (backend)
- New file: `backend/strategies/wrr_buy_model.py`
- Server-side scanner (like Scout Sniper — no TradingView alert slot needed)
- Input: daily bars from yfinance for watchlist tickers
- Checks: consecutive down days, RSI(3), reversal candle pattern, volume spike, proximity to support, ROC(10)
- Output: candidate signals routed through `process_signal_unified()` with `lane: countertrend`
- Scheduling: run once daily after market close (4:15 PM ET) via existing cron or new scheduled task

#### C. Trade Ideas UI (frontend — Agora)
- Add visual badge/tag for countertrend signals: amber/orange color, "COUNTERTREND" label
- Show `lane` in Trade Idea detail view
- Show position size modifier ("Half-Size" indicator)
- Show accelerated expiry countdown

#### D. Committee Pipeline
- No changes to committee prompt structure needed — the existing TORO/URSA/TECHNICALS/PIVOT framework naturally handles countertrend analysis
- Add `lane` context to the committee prompt so analysts know they're evaluating a countertrend setup
- Countertrend signals should include a note: "This signal is AGAINST the prevailing bias. Evaluate whether the extreme condition justifies a countertrend entry."

#### E. Strategy Backlog Update
- Move WRR from "Deferred" to reference `docs/approved-strategies/wrr-buy-model.md`
- Update backlog entry to show promotion date

### Files Touched (Estimated)
- `backend/strategies/wrr_buy_model.py` — NEW
- `backend/scoring/rank_trades.py` or wherever gatekeeper logic lives — MODIFY (add lane branching)
- `backend/models/` or signal schema — MODIFY (add `lane` field)
- `backend/webhooks/tradingview.py` or `process_signal_unified()` — MODIFY (pass lane through)
- `frontend/app.js` — MODIFY (Trade Ideas rendering for countertrend badge)
- `frontend/styles.css` — MODIFY (countertrend visual treatment)
- `docs/strategy-backlog.md` — MODIFY

### Definition of Done
- [ ] WRR scanner runs daily after close and produces candidate signals
- [ ] Countertrend signals pass through the pipeline with `lane: countertrend`
- [ ] Gatekeeper correctly applies countertrend rules (extreme bias, 90 threshold, whitelist)
- [ ] Trade Ideas UI shows countertrend badge with half-size and accelerated expiry indicators
- [ ] Committee prompt includes lane context for countertrend signals
- [ ] At least one test covering the countertrend gatekeeper branch

---

## Work Item 2: STRC Circuit Breaker (Stater Swap)

### What It Does
Monitors STRC (Strategy Stretch Preferred Stock) price. When STRC is below $100 par value, displays a persistent visual warning in the Stater Swap (crypto trading) UI price bar area. This is a structural risk indicator — STRC below par means Strategy's primary BTC funding mechanism is impaired.

### Why Stater Only
This is crypto-specific alpha. STRC's relevance is entirely about BTC structural demand. It has no bearing on the equities/options side (Agora).

### Architecture

#### A. STRC Price Check (backend)
- Add STRC to the watchlist/ticker universe (DB insert or config update)
- New endpoint or addition to existing crypto market data endpoint: `GET /api/v2/crypto/circuit-breakers`
- Returns: `{ "strc": { "price": 98.50, "below_par": true, "par_level": 100, "last_updated": "..." } }`
- Data source: yfinance (`STRC` ticker) — polled on same schedule as other market data, or every 5 minutes during market hours
- Redis cache with 5-minute TTL

#### B. Stater Swap UI (frontend)
- In the Stater Swap price bar area, add a circuit breaker indicator section
- When STRC is ABOVE $100: no indicator shown (clean UI)
- When STRC is BELOW $100: show persistent amber/red warning bar:
  - Icon: warning triangle or lightning bolt
  - Text: "STRC BELOW PAR ($XX.XX) — Strategy funding at risk"
  - Styling: amber background when $95-100, red background when <$95
  - Tooltip/info: "Strategy's preferred stock is below $100 par value. Their ability to issue new shares and buy BTC is impaired. Structural bid weakening."
- This is NOT a dismissible notification — it stays visible as long as STRC < $100

#### C. Optional: Discord Alert
- One-time alert to Discord when STRC first crosses below $100 (not on every poll)
- De-duplicate: only fire once per crossing event (use Redis flag)

### Files Touched (Estimated)
- `backend/routes/` or crypto endpoints — MODIFY (add circuit breaker endpoint)
- `backend/data/` or market data fetcher — MODIFY (add STRC to polling)
- `frontend/app.js` — MODIFY (Stater Swap section, circuit breaker rendering)
- `frontend/styles.css` — MODIFY (circuit breaker warning styles)
- DB: Add STRC to watchlist table if applicable

### Definition of Done
- [ ] STRC price is fetched and cached (yfinance, 5-min TTL)
- [ ] `/api/v2/crypto/circuit-breakers` endpoint returns STRC status
- [ ] Stater Swap UI shows warning bar when STRC < $100
- [ ] Warning bar uses amber ($95-100) / red (<$95) color coding
- [ ] No warning shown when STRC ≥ $100
- [ ] STRC added to watchlist

---

## Build Sequence

1. **Titans Review** ← YOU ARE HERE
2. Titans approve/modify architecture
3. CC Brief written with exact find/replace anchors
4. Titans final review of brief
5. CC executes (Work Item 2 first — it's simpler and immediately useful)
6. Work Item 1 follows (more architectural, needs scanner + gatekeeper changes)

---

## Open Questions for Titans

1. **ATLAS**: Where exactly does gatekeeper logic live? Need the specific file/function for the `lane` branching. Is it in `rank_trades.py`, `process_signal_unified()`, or somewhere else?
2. **HELIOS**: What does the Stater Swap price bar currently look like? Need to understand the DOM structure for the circuit breaker injection point.
3. **AEGIS**: Does the STRC endpoint need auth? It's read-only market data, but confirming.
4. **ATHENA**: Should the WRR scanner run against the full 207-ticker Primary Watchlist, or a smaller curated subset? Full watchlist = more signals but more compute. Recommendation: start with Primary Watchlist, throttle later if noisy.
