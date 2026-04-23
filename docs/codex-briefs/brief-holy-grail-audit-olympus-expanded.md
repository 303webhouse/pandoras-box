# Holy Grail Audit — CC Brief (Olympus-Expanded)

**Type:** DIAGNOSTIC AUDIT — READ ONLY. No code modifications.
**Source docs:** `holy-grail-audit-brief.md` (original PIVOT brief), `olympus-review-2026-04-22.md` (committee review adding scope)
**Output target:** `docs/audits/holy-grail-audit-2026-04-22.md`
**Estimated runtime:** 30–60 min (scope expanded from original)
**Repo:** `github.com/303webhouse/pandoras-box` main branch

---

## 1. What Changed From the Original Brief

Olympus committee review on 2026-04-22 added three scope items:

1. **`ursa_taurus.py` added to audit scope.** Section 4 of the evaluation doc flags it as "Unknown without deeper read" — same treatment as `hunter.py`.
2. **Explicit deprecation classification** for `hunter.py` AND `ursa_taurus.py` — not just overlap check with Turtle Soup. Olympus needs these classified as part of the anti-bloat framework (candidates for banked deprecation).
3. **Fix list expanded** with 6 Olympus agent additions on top of the original 8. Consolidated into priority tiers (see Section 5 of this brief).

Everything else in the original brief is still in scope.

---

## 2. Preliminary Delta (From Original Brief — Validate, Don't Redo)

PIVOT already documented these findings from `backend/scanners/holy_grail_scanner.py`. CC's Phase 1 job is to **validate they still hold at HEAD and add anything missing.**

### Code-verified current state (as of 2026-04-22)

- **Timeframe:** 1H bars via yfinance, 3-month history (`period="3mo"`, `interval="1h"`)
- **ADX threshold:** 25 (Raschke canonical: 30) — more permissive than spec
- **ADX length:** 14 — standard
- **EMA length:** 20 ✅
- **RSI:** length 14, long filter <70, short filter >30 with strong-trend carve-out (ADX ≥ 30 AND DI- > 1.5×DI+ allows short even with RSI ≤ 30)
- **Touch tolerance:** 0.15% of EMA, widens to 0.25% when VIX ≥ 25
- **Pullback logic:** prev bar low/high within tolerance OR crosses and closes back
- **Direction filter:** DI+ > DI- for longs, DI- > DI+ for shorts
- **Cooldown:** 24h Redis-backed (`scanner:hg:cooldown:{ticker}`), daily cap 2/ticker (`scanner:hg:daily_count:{ticker}:{date}`)
- **Exit:** fixed 2R target, stop = prev bar's low (long) or high (short)
- **Signal output:** `signal_type=HOLY_GRAIL_1H`, `asset_class=EQUITY`
- **Universe:** 200 tickers max from `scanners.universe.build_scan_universe`

### Raschke 7-Point Gap Analysis (validate each row)

| # | Raschke Point | Current State | Gap Severity |
|---|---|---|---|
| 1 | Trend filter (ADX + EMA slope + HH/HL) | ADX-only; DI+/- for direction | MED |
| 2 | Pullback depth (hold EMA intrabar / close back) | Partial match | LOW |
| 3 | 1st pullback only (after ADX ignition) | No tracking; 24h cooldown is proxy only | HIGH |
| 4 | 3-10 oscillator momentum confirm | Not present (uses RSI) | MED |
| 5 | Scale exit: 50% at 1R, trail remainder | Fixed 2R target, no scale | HIGH |
| 6 | Session filter (skip open 30min, lunch, close 30min) | None | MED for 1H, HIGH for 15m |
| 7 | VIX regime (skip < 15 and > 30) | Only widens tolerance at ≥ 25 | MED — `iv_regime` filter exists, just needs to be called |

### Additional findings (validate)

- **Asset class lock-in:** hardcoded `asset_class: "EQUITY"` — blocks crypto variant
- **Timeframe lock-in:** 1H only in Python
- **EMA slope not computed:** `ema20` calculated but slope never evaluated
- **No universe tiering:** same 200-ticker universe regardless of timeframe
- **Signal field naming:** `rvol` field is actually DI-spread, not relative volume — misleading

---

## 3. CRITICAL: Locate ALL Holy Grail Timeframe Variants

Nick reports a 15m Holy Grail is live. Grep didn't find a separate Python file. Possibilities:

1. **15m via TradingView webhook** (most likely): Pine script fires on TV, webhook → `backend/webhooks/tradingview.py` → signals pipeline. Check webhook handler for `HOLY_GRAIL_15M` or `15m` routing.
2. **15m via separate Python module**: re-verify with `search_code` for `15m` and `interval.*15`.
3. **15m via config toggle** in existing scanner: check if `HG_CONFIG` or `_fetch_1h_bars` has a 15m variant.
4. **15m PineScript** in `docs/pinescript/webhooks/`: inspect for `holy_grail_15m.pine` or equivalent.

For each variant located, document:
- File path and line references
- Trigger mechanism (server scan / webhook / TV alert)
- Config differences from 1H (ADX threshold, tolerance, RSI, exit logic)
- Signal type string (`HOLY_GRAIL_1H`, `HOLY_GRAIL_15M`, etc.)
- Whether it reuses `holy_grail_scanner.py` functions or duplicates
- Whether it inherits the same fixed-2R exit, session filter absence, etc.

**Why this matters:** if 15m duplicates 1H flaws, fix scope doubles. If it's a TV webhook inheriting pipeline logic, fix is contained.

---

## 4. Cross-Reference Integrations

Read the following and answer the questions below with file:line refs.

### 4.1 `backend/main.py` (49KB)
- How often is `run_holy_grail_scan()` scheduled? (cron or interval)
- Is it market-hours-gated?
- Any circuit breakers tied to Holy Grail signal generation?

### 4.2 `backend/signals/pipeline.py` (40KB)
- What does `process_signal_unified` do with a Holy Grail signal?
- Does it run confluence scoring? Which factors?
- Does Holy Grail go to committee review before hitting alerts?
- Which DB tables does it write to?

### 4.3 `backend/bias_engine/composite.py`
- Is `iv_regime` a current factor in the composite?
- Does Holy Grail already consume any bias factor other than `vix_term` for tolerance adjustment?

### 4.4 `backend/database/`
- Where do Holy Grail signals land? (`signals` table? `strategy_signals`?)
- Any Holy Grail-specific columns?

### 4.5 Cadence / Universe
- Actual scan cadence in practice
- Universe size
- Any tiering (watchlist priority)?

---

## 5. Turtle Soup Overlap Check + Deprecation Classification

### 5.1 `backend/scanners/sell_the_rip_scanner.py` (22KB) — Full Read
- Does it contain failed-breakout-fade logic (price breaks N-day high/low, fails, reverses)?
- Does it use "20-day range" or "N-day extreme" triggers?
- **Verdict for Turtle Soup:** ADD (clean) / ELEVATE (overlap → replace with cleaner Turtle Soup trigger) / REPLACE candidate

### 5.2 `backend/scanners/hunter.py` (22KB) — Full Classification
**NEW per Olympus — not just overlap check.** Classify:
- What trigger logic does it use? (cite code)
- Which signal types does it emit?
- How does it integrate with the signals pipeline?
- Does it overlap with ANY existing scanner (not just for Turtle Soup) — Scout-Sniper, Hub-Sniper, CTA, wh_reversal, etc.?
- **Deprecation verdict:** KEEP (unique edge, no overlap) / CONSOLIDATE (merge into another scanner) / DEPRECATE (redundant)

### 5.3 `backend/strategies/ursa_taurus.py` — Full Classification
**NEW per Olympus.** Classify:
- Is it a paired bull/bear strategy or something else?
- Signal types emitted
- Pipeline integration
- Overlap check with all other strategies/scanners
- **Deprecation verdict:** KEEP / CONSOLIDATE / DEPRECATE

---

## 6. Delta Report Format

Save to `docs/audits/holy-grail-audit-2026-04-22.md`:

```markdown
# Holy Grail Audit — 2026-04-22

## 1. File Locations (confirmed)
- Primary: backend/scanners/holy_grail_scanner.py
- 15m variant: [location or "not found as distinct file — TV webhook via backend/webhooks/tradingview.py line X"]
- Scheduler: [main.py:line]
- Pipeline: backend/signals/pipeline.py
- DB write target: [table]

## 2. Raschke 7-Point Delta (Validated)
[Table — confirm each row or correct it]

## 3. 15m Variant Findings
[File paths, trigger mechanism, config differences, code-reuse assessment]

## 4. Additional Findings
[Asset class lock-in, timeframe lock-in, EMA slope not computed, field naming]

## 5. Integration Map
- Scheduler cadence: [cron/interval]
- Committee review: [yes/no — which committee]
- DB write target: [table, columns]
- Confluence scoring: [which factors consumed]

## 6. Turtle Soup / Deprecation Classifications
### 6.1 sell_the_rip_scanner.py
[Classification + evidence + Turtle Soup verdict]

### 6.2 hunter.py
[Full classification — keep/consolidate/deprecate — with evidence]

### 6.3 ursa_taurus.py
[Full classification — keep/consolidate/deprecate — with evidence]

## 7. Olympus-Consolidated Fix List Priority

Tier 1 (build alongside 3-10 oscillator):
- Call existing `iv_regime` filter (skip VIX <15 / >30)
- Sector-rotation tag at trigger time (lookup against sector_rs)

Tier 2 (moderate):
- Session filter (config-gated; off 1H, on 15m)
- EMA slope confirmation
- HH/HL structure check
- Parameterize asset_class for crypto variant
- Prior-session VA-relative context tag
- ATR-alternative stop (MAX of prev-bar stop, entry - 1.5×ATR(14))

Tier 3 (harder):
- Scale exit: 50% at 1R, trail remainder
- Pullback sequence tracking (1st vs Nth after ADX ignition)
- Ticker-level circuit breaker (skip next fire after 2 consecutive losses in 10d)

Tier 4 (nice-to-have):
- VIX regime transition opportunistic fire
- IV rank context in signal payload (structure-selection hint, not filter)

## 8. Non-Trivial Decisions for Nick
[Any judgment calls — ADX 25 vs 30, whether to deprecate hunter/ursa_taurus before Phase 2 begins, etc.]
```

---

## 7. Constraints

- **READ ONLY.** No code modifications in this phase.
- If an integration requires live behavior to verify, mark "REQUIRES LIVE VALIDATION" and move on.
- Cite file:line refs for every finding.

---

## 8. When Done

Post the audit report path. Do not start any fixes. Nick + Titans review next, then Phase 2 fix brief.
