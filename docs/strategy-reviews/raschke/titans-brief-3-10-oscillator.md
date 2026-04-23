# 3-10 Oscillator — Titans Pass 2 Brief (Final)

**Type:** Pre-build architecture review — **Pass 2 complete, ATHENA decision locked**
**Source:** Olympus review 2026-04-22 — highest-leverage ELEVATE in Raschke suite
**Priority:** Phase 1 build (ships first in Raschke queue, gated on ZEUS Phase 3 + hunter.py deprecation)
**Status:** Ready for CC build brief drafting

---

## 1. Context

Olympus unanimously endorsed the 3-10 Oscillator as the single highest-leverage addition in the Raschke strategy review. It:

- **Unlocks** The Anti as a Holy Grail variant (hard dependency)
- **Improves** Holy Grail by replacing its RSI filter (per Raschke's canonical spec)
- **Supports** Turtle Soup's divergence filter (Phase 2)
- **Enriches** sector-rotation signals via sector-ETF 3-10 (THALES bonus)
- **Costs almost nothing** — trivial pandas math, OHLCV only, zero new data dependencies

Because it's an overlay (not a signal generator), it doesn't count against the "≤ current + 3" strategy cap.

---

## 2. What's Being Built

A system-wide momentum oscillator indicator that any strategy, scanner, or Olympus agent can query.

**Mathematical definition (Linda Raschke canonical):**
- **Midpoint:** `(High + Low) / 2` per bar
- **Raw line:** `3-bar SMA of midpoint − 10-bar SMA of midpoint`
- **Fast line:** `3-bar SMA of raw line`
- **Slow line:** `10-bar SMA of raw line`

**Primary outputs per bar:**
1. Fast line value
2. Slow line value
3. Crossover boolean (fast crossed slow up / down on this bar)
4. Divergence flag (mechanical rule per §3.1)

---

## 3. Non-Negotiables From Olympus (Locked)

These are locked — not up for Titans debate.

### 3.1 Mechanical Divergence Detection
- **Bullish:** price makes a new N-bar low (default N=5), while fast line's corresponding pivot low is HIGHER than its prior pivot low by ≥X% (default X=10%).
- **Bearish:** price makes a new N-bar high, while fast line's corresponding pivot high is LOWER than its prior pivot high by ≥X%.
- **Pivot detection:** 5-bar window (2 before + pivot + 2 after). Divergence flag fires only when both price pivot AND fast-line pivot are confirmed.

### 3.2 Timeframe Agnostic
Serves 1m, 5m, 15m, 1H, Daily, Weekly. Input: DataFrame with `high`, `low` columns + DatetimeIndex. Output: same DataFrame + 4 appended columns.

### 3.3 Holy Grail RSI Replacement in Shadow Mode
- Signals fire on BOTH gates; both logged with gate tag
- 6-month default comparison window
- Keep whichever gate wins by ≥3pp win rate OR ≥0.1 profit factor
- Day-90 Olympus checkpoint reviews for early cutover eligibility

### 3.4 Sector-ETF 3-10 From Day One (THALES)
Compute 3-10 on XLK, XLF, XLE, XLY, XLV, XLP, XLU, XLI, XLB, XLRE, XLC. Every trading signal carries the sector 3-10 reading as context.

### 3.5 Frequency Cap Sanity Check (URSA)
Divergence events >3/ticker/month on daily bars → warning log in `/var/log/committee_audit.log` or equivalent.

---

## 4. Titans Pass 1 Design Questions (Retained for Record)

*Pass 1 questions preserved from v1 brief. Solo and Pass 2 responses in §9-§11 below.*

[§4.1-§4.4 original agent questions retained verbatim from v1 — see commit history]

---

## 5. Proposed MVP Architecture (Superseded by §11)

*v1 architecture proposal retained for traceability. §11 is the locked architecture.*

---

## 6-8. Deliverable, Dependencies, Out of Scope

See §11 (ATHENA final) — supersedes original §6-§8.

---

## 9. Titans Pass 1 — Solo Agent Responses

### ATLAS (Backend Architect)

**Q1 — Location:** New package `backend/indicators/three_ten_oscillator.py`. Not `bias_filters/` (different domain — those score macro conditions). Not `shared/` (that's DB clients, logging). Indicators are a distinct domain and this sets precedent. Structure: `__init__.py` + `three_ten_oscillator.py`. Defer `base.py` abstract class until there's a second indicator (YAGNI).

**Q2 — API contract:** Stateless pure function. Signature: `compute_3_10(df: pd.DataFrame, divergence_lookback: int = 5, divergence_threshold: float = 0.10) -> pd.DataFrame`. Returns df with 4 appended columns: `osc_fast`, `osc_slow`, `osc_cross`, `osc_div`. Column names exported as module constants. Function is pure — zero side effects; logging/DB writes live in the caller.

**Q3 — Caching:** `functools.lru_cache` keyed by `(ticker, timeframe, last_bar_timestamp)`, maxsize=5000. NOT Redis for MVP — pandas compute is sub-millisecond and Redis round-trip is slower than recompute. Escalation path documented; Redis only if profiling proves a bottleneck.

**Q4 — Live/backtest sharing:** Direct import of same module. Pure deterministic function = zero duplication risk. Satisfies backtest/live parity requirement.

**Q5 — Sector-ETF delivery:** Centralized in `pipeline/signal_enrichment.py`. Computes all 11 ETF readings once per bar close, caches in-process, attaches sector reading to every signal passing through enrichment. DRY, cache hit rate near 100%. **Flag:** confirm `signal_enrichment.py` exists or scope creation.

### HELIOS (Frontend UI/UX)

**Q1 — UI viz:** No dedicated viz for MVP. 3-10 is an input, not a signal. Signal cards gain gate tag during shadow mode; sector-rotation tag already leverages 3-10 under the hood. Phase 2 could add sparkline in detail drawer if requested.

**Q2 — Divergence alerts:** Backend-only. Divergences feed Olympus context and Turtle Soup/Anti inputs but aren't standalone signals. Revisit after 3 months of shadow signal-to-noise data.

**Q3 — Shadow-mode display:** **Option C selected.** Main feed is unified, RSI-primary, with `3-10 confirms` badge when both gates agree. Separate dev view at `/dev/shadow-3-10` for 3-10-only signals. Nick builds intuition on 3-10 over shadow period without noise in the main feed. Options A (both visible) and B (3-10 silent) both rejected — A doubles noise, B blocks intuition-building.

### AEGIS (Security)

**Q1 — Attack surface:** Zero inherent surface. Pure OHLCV math, no creds, no external calls. Any exposing route requires `X-API-Key` — no public routes, no IP allow-list exceptions, no localhost escape hatches.

**Q2 — Storage:** Ephemeral compute + opportunistic cache + persist divergences only. Full persistence math is absurd (~390k rows/day on 5m alone). Divergence event schema:
```
divergence_events (
  id SERIAL PRIMARY KEY,
  ticker TEXT NOT NULL,
  timeframe TEXT NOT NULL,
  bar_timestamp TIMESTAMPTZ NOT NULL,
  div_type TEXT NOT NULL,
  fast_pivot_prev NUMERIC(12,6),
  fast_pivot_curr NUMERIC(12,6),
  price_pivot_prev NUMERIC(12,6),
  price_pivot_curr NUMERIC(12,6),
  threshold_used NUMERIC(5,4),
  lookback_used INT,
  created_at TIMESTAMPTZ DEFAULT NOW()
)
```
`NUMERIC(12,6)` mandatory — float drift on 10% threshold comparison is a real risk.

### ATHENA (PM)

**Q1 — MVP scope:** Agreed + adds. Ships: (1) core math + divergence, (2) HG shadow-mode dual-gate integration, (3) sector-ETF variant + enrichment wiring, (4) freq cap self-check, (5) unit tests, (6) dev view `/dev/shadow-3-10`, (7) schema migrations for `gate_type` column + `divergence_events` table.

**Q2 — Priority:** First in Raschke queue. Ships after ZEUS Phase 3 + hunter.py deprecation; before The Anti P3 and 80-20 P2. ~6 days CC work.

**Q3 — Rollout gate:** 6-month shadow default; day-90 Olympus checkpoint for potential early cutover if statistical significance + OOS volume both clear.

**Q4 — Success criteria:** Agreed list + math to 4 decimal places on Raschke vectors; sector-ETF cache within 10s of bar close; dev view X-API-Key protected; unit tests cover math + divergence synthetics + freq cap trigger.

---

## 10. Titans Pass 2 — Cross-Reactions (Deltas Only)

**ATLAS → HELIOS:** Option C requires scanner-level changes — Holy Grail emits `gate=rsi`, `gate=3-10`, `gate=both` channels. Adds ~1 day to estimate. Also requires `gate_type` column migration on trade signals table — in scope.

**ATLAS → AEGIS:** In-process cache wiped on every Railway deploy. Shadow-mode comparison relies on `trade_signals` persistence with `gate_type`, not the cache. Migration in scope.

**HELIOS → ATLAS:** Dev view implementation: `/dev/shadow-3-10` queries `trade_signals` filtered by `gate_type='3-10'`. No new storage, filtered read only.

**HELIOS → ATHENA:** Dev view must be MVP, not Phase 2. Without it we collect 6 months of shadow data with Nick having no visibility, which delays cutover-readiness rather than solving it.

**AEGIS → ATLAS + HELIOS:** `/dev/shadow-3-10` gets same `X-API-Key` auth as production routes. No exceptions.

**AEGIS → ATHENA:** Schema accepted; `NUMERIC(12,6)` mandate confirmed.

**ATLAS → ATHENA (pushback on v1 §7):** Hard dependency #2 in v1 is incorrect — pipeline cannot handle dual-gate tagging without changes. Migration + scanner split must be in build scope, not a separate ticket. Reflected in §11.

---

## 11. ATHENA Final — Architecture, Scope, Priority (LOCKED)

### Architecture

| Concern | Decision |
|---|---|
| Code location | `backend/indicators/three_ten_oscillator.py` (new package) |
| API | Stateless pure function, named-constant column outputs |
| Caching | `functools.lru_cache`, maxsize=5000, in-process |
| Sector-ETF delivery | `pipeline/signal_enrichment.py` centralized |
| Live/backtest | Shared via direct import |
| Frontend | HELIOS Option C (unified feed + dev view) |
| Auth | `X-API-Key` on all routes, including dev view |

### Pipeline Changes In Scope

1. Holy Grail scanner splits output into `gate=rsi` / `gate=3-10` / `gate=both` channels
2. `trade_signals` schema migration: add `gate_type TEXT` column
3. New `divergence_events` table (schema per §9 AEGIS spec)
4. `signal_enrichment.py` verified or created; sector-ETF 3-10 wired
5. Frequency cap self-check writes to audit log

### MVP Done Criteria

1. Math matches Raschke published vectors to 4 decimal places
2. Mechanical divergence passes synthetic bull/bear test cases
3. Holy Grail emits dual-gate signals with `gate_type` tagged and persisted
4. Sector-ETF 3-10 cache refreshes within 10s of bar close; enriches all signals
5. Divergence events persist to `divergence_events` table
6. Frequency cap self-check logs warning at >3/ticker/month on daily
7. Dev view `/dev/shadow-3-10` live, `X-API-Key` protected, no nav link
8. Unit tests pass (math + divergence synthetics + freq cap trigger)

### Priority Placement

- Ships FIRST in Raschke queue
- Gated on: ZEUS Phase 3 complete + hunter.py deprecation brief clear
- Blocks downstream: HG Tier 1 RSI replacement, The Anti P3, Turtle Soup P1 divergence filter, sector-rotation enrichment

### Estimate

**~6 days CC work**
- Indicator math + divergence: 2 days
- Pipeline dual-gate + schema migration: 2 days
- Enrichment + sector ETF: 1 day
- Dev view + tests: 1 day

### Rollout Gate

6-month shadow default. Day-90 Olympus checkpoint reviews for potential early cutover — requires (a) statistical significance on ≥3pp win rate or ≥0.1 PF delta, (b) sufficient out-of-sample volume per Olympus call.

### Hard Dependencies (Updated — Supersedes v1 §7)

1. ✅ Mechanical divergence rule specified (§3.1)
2. ✅ Pipeline dual-gate tagging + schema migration **in scope** (corrected from v1)
3. ⏳ **TODO for Nick:** source 2-3 known 3-10 readings from Linda Raschke published examples for test vectors
4. ⏳ **TODO for CC (first task):** verify `signal_enrichment.py` exists on repo; if not, scope creation

### Out of Scope (Unchanged)

- Options/futures timeframes beyond current
- Custom divergence variants (hidden, multi-leg)
- ML or parameter optimization
- Historical backfill of 3-10 readings
- Redis caching (MVP uses in-process LRU)
- Public API endpoint for 3-10 values
- Frontend visualization of oscillator values
- Divergence alerting to Nick

---

**End of Titans Pass 2 final brief. Ready for CC build brief drafting.**
