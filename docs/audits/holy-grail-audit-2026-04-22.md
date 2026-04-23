# Holy Grail Audit — 2026-04-22

**Scope:** Olympus-expanded (original PIVOT brief + 3 committee additions)
**Status:** READ-ONLY diagnostic — no code modifications
**Next step:** Nick + Titans review → Phase 2 fix brief

---

## 1. File Locations (confirmed)

- **Primary scanner:** `backend/scanners/holy_grail_scanner.py`
- **15m variant:** No separate Python file. Routes via TradingView webhook → `backend/webhooks/tradingview.py:362–372` (`process_holy_grail_signal()`)
- **Scheduler:** `backend/main.py:241–261` (`holy_grail_scan_loop()`)
- **Pipeline:** `backend/signals/pipeline.py:706–930` (`process_signal_unified()`)
- **DB write target:** `signals` table (via `log_signal()` in `database.postgres_client`)
- **Feed tier classifier:** `backend/scoring/feed_tier_classifier.py:37–90`
- **Bias engine:** `backend/bias_engine/composite.py:87–92` (`iv_regime` factor)

---

## 2. Raschke 7-Point Delta (Validated)

| # | Raschke Point | Current State | File:Line | Gap Severity |
|---|---|---|---|---|
| 1 | Trend filter (ADX + EMA slope + HH/HL) | ADX ≥ 25 + DI+/DI- for direction; NO HH/HL tracking, NO EMA slope | `holy_grail_scanner.py:28–38, 88–92, 148–152` | MED |
| 2 | Pullback depth (hold EMA intrabar / close back) | Partial: EMA tolerance band (0.15%) + close confirmation; no intrabar wick tracking | `holy_grail_scanner.py:97–118` | LOW |
| 3 | 1st pullback only (after ADX ignition) | **Not tracked.** 24h Redis cooldown is a proxy only — does not distinguish 1st vs Nth pullback | `holy_grail_scanner.py:42, 238–243` | HIGH |
| 4 | 3-10 oscillator momentum confirm | **Not present.** Uses RSI only (long: RSI < 70; short: RSI > 30 with strong-trend carve-out) | `holy_grail_scanner.py:152–167` | MED |
| 5 | Scale exit: 50% at 1R, trail remainder | **Not present.** Fixed 2R target only; no partial close or trailing logic | `holy_grail_scanner.py:37, 176, 206` | HIGH |
| 6 | Session filter (skip open 30 min, lunch, close 30 min) | **None** in server scanner. 15m relies entirely on TradingView time-based alerts | `holy_grail_scanner.py` (absent); `webhooks/tradingview.py:365–370` | MED (1H) / HIGH (15m) |
| 7 | VIX regime gate (skip VIX < 15 or > 30) | Partial: tolerance widens at VIX ≥ 25 (0.15% → 0.25%) but no signal gate. `iv_regime` factor present in composite but not called as a gate | `holy_grail_scanner.py:49–63`; `composite.py:87–92` | MED — gate is absent; `iv_regime` exists, just not wired |

---

## 3. 15m Variant Findings

**3.1 Separate Python scanner:** Does not exist. No `holy_grail_15m_scanner.py`.

**3.2 TradingView webhook routing (confirmed live path):**
- `backend/webhooks/tradingview.py:365–371` parses timeframe field from alert payload
- `signal_type_suffix = "1H"` if tf in `("60", "1H", "H", "1")`, else `"15M"`
- Emits `HOLY_GRAIL_1H` or `HOLY_GRAIL_15M` as the `signal_type` field
- Same Redis cooldown: 7200s equity / 3600s crypto — identical for both timeframes

**3.3 Config toggle for 15m:** None. Timeframe is inferred from TradingView alert payload field at receipt, not from a config toggle in the scanner.

**3.4 PineScript:** `docs/pinescript/holy_grail_webhook_v1.pine` — single parameterized indicator, runs on any timeframe (1H, 15m, 5m, etc.). No separate 15m file. Webhook payload includes `timeframe` field read at `tradingview.py:365`.

**3.5 Config differences (1H vs 15m via webhook):**

| Parameter | 1H | 15m | Source |
|-----------|-----|-----|--------|
| Base score | 50 | 40 | `trade_ideas_scorer.py:67–68` |
| Confluence Tier 3 bonus | +6 | +4 | `feed_tier_classifier.py:63, 74` |
| Trade type classification | SWING | SPRINT | `trade_ideas_scorer.py:157` |
| Redis cooldown | 7200s | 7200s | `webhooks/tradingview.py:55` |
| Session filter (server-side) | None | None | (both rely on TradingView) |
| ADX threshold | Same (TV) | Same (TV) | PineScript param |

**Conclusion:** 15m Holy Grail is a **configuration of the same webhook path**, not a separate implementation. Differentiation occurs at webhook receipt via timeframe string parsing. 15m inherits all 1H flaws except EMA slope (moot since neither tracks it). Session filter gap is **equally present in both**.

---

## 4. Additional Findings

**4.1 Asset class lock-in:** Hardcoded `asset_class: "EQUITY"` in server scanner (`holy_grail_scanner.py:192`). Crypto support exists only via TradingView webhook (`webhooks/tradingview.py:279–301, 374`).

**4.2 Timeframe lock-in:** Server scanner hardcoded `interval="1h"` (`holy_grail_scanner.py:70`). 15m only reachable via TradingView.

**4.3 EMA slope not computed:** `ema20` is calculated but slope is never evaluated (`holy_grail_scanner.py:80–85`). Raschke trend filter requires slope confirmation — current state is ADX + DI+/DI- only, no slope or HH/HL structural check.

**4.4 Field naming inconsistency:**
- Server scanner: `rvol` field = `di_plus - di_minus` (DI spread) — `holy_grail_scanner.py:177, 207`
- Webhook path: `rvol` = actual relative volume from PineScript — `tradingview.py:305, 405`
- Same field name, different meaning depending on signal source. Upstream consumers (pipeline, committee context) cannot distinguish. Rename server field to `di_spread`.

**4.5 No universe tiering:** All ~200 tickers scanned equally regardless of watchlist priority (`holy_grail_scanner.py:281`). 50ms sleep between tickers (`holy_grail_scanner.py:292`).

---

## 5. Integration Map

**Scheduler cadence:**
- Interval: every 15 minutes (`main.py:261`: `await asyncio.sleep(900)`)
- Startup offset: +3 min (`main.py:247`: `await asyncio.sleep(180)`)
- Market hours gate: 9:30 AM–4:00 PM ET, weekdays only (`main.py:253`)
- No per-signal circuit breaker on the scheduler loop itself

**Committee review:**
- Score ≥ 85.0 → auto-promoted to `COMMITTEE_REVIEW` (`pipeline.py:21, 116–117`)
- Signal persisted to DB first, then flagged for committee
- Committee runs asynchronously on VPS via `pivot2-interactions`; not blocking signal delivery

**DB write targets:**
- `signals` table — primary (`pipeline.py:791–811`)
- `signals.score_v2` — updated post-scoring (`pipeline.py:843–865`)
- `signals.enrichment_data` JSONB — enrichment fields (`pipeline.py:832–839`)

**Confluence scoring applied to Holy Grail:**
- Tier 3 bonus: 1H = +6 pts, 15m = +4 pts (`feed_tier_classifier.py:63, 74`)
- Max total confluence bonus: +20 (`feed_tier_classifier.py:94`)
- WH-ACCUMULATION backing check + dark pool blocks (`pipeline.py:418–433`)
- Flow enrichment: directional sentiment bonus from `flow_events` (`pipeline.py:339–414`)

**`iv_regime` factor:** Active in composite (`composite.py:87–92`). **Not consumed by `holy_grail_scanner.py`** — the scanner fetches VIX independently for tolerance adjustment only. The composite `iv_regime` score does influence the broader bias signal that committee agents consume, but it does not gate Holy Grail signal generation.

---

## 6. Deprecation Classifications

### 6.1 `sell_the_rip_scanner.py`

**Trigger logic:**
- Mode 1 (Confirmed Downtrend): Price < 50 SMA, EMA < SMA, ADX ≥ 20, rejection at EMA or VWAP (`sell_the_rip_scanner.py:120–165`)
- Mode 2 (Early Detection): Sector = `ACTIVE_DISTRIBUTION`, ADX ≥ 15, EMA rejection (`sell_the_rip_scanner.py:165–184`)
- 20-bar swing low + expected move calculation (`sell_the_rip_scanner.py:165–184`)
- Convexity grading A/B/C via sector + volume + ADX + expected move (`sell_the_rip_scanner.py:187–230`)

**Failed-breakout / N-day extreme logic:**
- YES — detects reversals after rallies into resistance (EMA/VWAP rejection)
- PARTIAL on 20-day range: uses 50 SMA (not 20-day), swing low lookback is 20 bars on daily ≈ 4 weeks

**Turtle Soup overlap:** Logic is adjacent to Turtle Soup (fade into prior N-day extreme) but cleaner and more structured. Not duplicative — addresses downtrend entries, not range breakout fades.

**Verdict: ELEVATE.** Sell the Rip is a valid distinct signal. Improvement path: (1) parameterize swing window from 20 bars to true 20-day, (2) add 3-10 oscillator confirmation alongside ADX per Raschke doctrine, (3) Turtle Soup becomes a separate ELEVATES-on-top lane, not a replacement.

---

### 6.2 `hunter.py`

**File header note:** `hunter.py:2` contains deprecation comment — "DEPRECATED: Trapped trader detection has been absorbed into cta_scanner.py" — but the file is still importable and referenced.

**Trigger logic:**
- URSA (trapped longs): Price < 200 SMA, < VWAP, ADX > 20, RSI > 40, RVOL > 1.5 (`hunter.py:85–112`)
- TAURUS (trapped shorts): Price > 200 SMA, > VWAP, ADX > 20, RSI < 60, RVOL > 1.5 (`hunter.py:85–112`)
- Quality scorer: `calculate_hunter_score()` — ADX 25%, RSI 25%, RVOL 30%, VWAP distance 20% (`hunter.py:116–145`)

**Signal types emitted:** `SNIPER_URSA`, `SNIPER_TAURUS` (both weighted 3 pts in `feed_tier_classifier.py:49–50`)

**Overlap analysis:**
- vs Scout-Sniper: Scout uses 15m RSI hooks + reversal candles; Hunter uses daily 200 SMA + VWAP. Different timeframe and trigger — minimal overlap.
- vs Artemis: Both use VWAP, but Artemis is intraday reversion bands; Hunter is macro trend trap. Different context.
- vs CTA: CTA detects via price/volume accumulation pattern; Hunter via SMA/VWAP/RSI threshold. Different mechanism.
- vs `ursa_taurus.py`: **Near-identical logic.** `hunter.py:116` defines `check_ursa_signal()`; `ursa_taurus.py:28` defines `validate_ursa_signal()`. Same 200 SMA + VWAP + ADX + RSI + RVOL inputs, different function names and scoring weights.

**Verdict: CONSOLIDATE → then DEPRECATE `hunter.py`.** `ursa_taurus.py` is the active implementation. `hunter.py` should be formally removed after verifying all import references are cleared. Signal types `SNIPER_URSA`/`SNIPER_TAURUS` should route through `ursa_taurus.py`'s `validate_ursa_taurus_signal()` or be renamed for consistency.

---

### 6.3 `ursa_taurus.py`

**File status:** Exists and active (`backend/strategies/ursa_taurus.py`, ~230 lines).

**Structure:** Paired bull/bear strategy with unified entry `validate_ursa_taurus_signal()`:
- URSA path: Price < 200 SMA, < VWAP, ADX > 20, RSI > 40, RVOL > 1.5
- TAURUS path: Price > 200 SMA, > VWAP, ADX > 20, RSI < 60, RVOL > 1.5
- Quality scorer: `calculate_hunter_score()` — ADX 25%, RSI 25%, RVOL 30%, VWAP distance 20% (`ursa_taurus.py:28–80`)

**Signal types emitted:** `URSA_SIGNAL`, `TAURUS_SIGNAL` (both weighted 3 pts in `feed_tier_classifier.py:50, 86–87`)

**Overlap check:**
- vs CTA: RSI extremes + volume vs. SMA/VWAP threshold. Complementary, not duplicative.
- vs Scout-Sniper: 15m reversals vs. daily macro filters. No overlap.
- vs WH-ACCUMULATION: Volume profile accumulation vs. price-action trap. No overlap.
- vs Artemis: Intraday VWAP bands vs. macro trend + VWAP distance. Minimal overlap.
- vs `hunter.py`: **Near-duplicate** (see §6.2 above).

**Verdict: KEEP.** Logic is clean and non-overlapping with active scanners (excluding the now-deprecated `hunter.py`). The paired bull/bear symmetry is valid. Recommended rename: `URSA_SIGNAL` → `TRAPPED_LONGS_SHORT`, `TAURUS_SIGNAL` → `TRAPPED_SHORTS_LONG` for signal feed clarity. This counts as a banked deprecation candidate per the anti-bloat framework (bank `hunter.py` deprecation against a future ADD).

---

## 7. Olympus-Consolidated Fix List Priority

### Tier 1 — Build alongside 3-10 oscillator

| Fix | Status | Evidence | File:Line |
|-----|--------|----------|-----------|
| Call existing `iv_regime` filter (gate VIX < 15 / > 30 at feed tier, not scanner) | **CONFIRMED NEEDED** — `iv_regime` exists but does not gate signal generation | `composite.py:87–92`; `holy_grail_scanner.py:49–63` | Implement at `feed_tier_classifier.py` |
| Sector-rotation tag at trigger time (lookup against `sector_rs` scanner output) | **CONFIRMED NEEDED** — signal payload has no sector-rotation state tag | `holy_grail_scanner.py:192` (no sector field) | Add enrichment step |

### Tier 2 — Moderate

| Fix | Status | Evidence | File:Line |
|-----|--------|----------|-----------|
| Session filter — config-gated; off 1H, on for 15m | **CONFIRMED NEEDED** (15m HIGH severity) | `tradingview.py:365–371`; no time-of-day check present | Add to `holy_grail_scanner.py` or `tradingview.py` |
| EMA slope confirmation | **CONFIRMED NEEDED** — `ema20` computed but slope never evaluated | `holy_grail_scanner.py:80–85` | Add slope calc |
| HH/HL structure check | **CONFIRMED NEEDED** — not present | `holy_grail_scanner.py` (absent) | New lookback logic |
| Parameterize `asset_class` for crypto variant | **CONFIRMED NEEDED** — hardcoded EQUITY | `holy_grail_scanner.py:192` | Config param |
| Prior-session VA-relative context tag | **CONFIRMED NEEDED** — signal has no VA context field | `holy_grail_scanner.py` (absent) | Requires Pythia zone lookup at trigger time |
| ATR-alternative stop: MAX(prev-bar stop, entry − 1.5×ATR(14)) | **CONFIRMED NEEDED** — current stop = prev bar low/high only | `holy_grail_scanner.py:176, 206` | ATR calculation exists in yfinance; add MAX comparison |

### Tier 3 — Harder

| Fix | Status | Evidence | File:Line |
|-----|--------|----------|-----------|
| Scale exit: 50% at 1R, trail remainder | **CONFIRMED NEEDED** — fixed 2R only | `holy_grail_scanner.py:37, 176, 206` | Requires trade-tracking integration |
| Pullback sequence tracking (1st vs Nth after ADX ignition) | **CONFIRMED NEEDED** — cooldown is proxy only | `holy_grail_scanner.py:42, 238–243` | Add Redis `pullback_count` key per ticker |
| Ticker-level circuit breaker (skip after 2 consecutive losses in 10d) | **CONFIRMED NEEDED** — no per-ticker loss tracking | `holy_grail_scanner.py` (absent) | Add outcome-linked Redis gate |

### Tier 4 — Nice to have

| Fix | Status | Evidence | File:Line |
|-----|--------|----------|-----------|
| VIX regime transition opportunistic fire | NOT APPLICABLE until Tier 1 gate is live | — | — |
| IV rank context in signal payload (structure-selection hint, not filter) | **CONFIRMED NEEDED** — UW enrichment fetches IV rank but not written to signal payload | `holy_grail_scanner.py:192` (no iv_rank field) | Payload addition only |

### Already present (no action needed)

- `iv_regime` factor in composite bias — `composite.py:87–92`
- 15m signal type routing — `tradingview.py:365–371`
- Committee auto-promotion at score ≥ 85 — `pipeline.py:116–117`
- Confluence scoring (Tier 3 bonuses) — `feed_tier_classifier.py:63, 74`
- Redis cooldown (24h / 2h depending on source) — `holy_grail_scanner.py:238–243`

---

## 8. Non-Trivial Decisions for Nick

### A. ADX 25 vs 30
**Current:** 25.0 (`holy_grail_scanner.py:29`). **Raschke:** ≥ 20 for trend presence; > 30 for high conviction.
**Recommendation: Keep 25.** It's above Raschke's minimum and empirically reasonable. If signal quality degrades after the pullback-count fix reduces noise, raise to 28 and A/B for 30 days.

### B. `hunter.py` deprecation timing
`hunter.py` self-identifies as DEPRECATED (`hunter.py:2`) but is still live in the codebase. `ursa_taurus.py` is the active successor with near-identical logic. **Recommendation: Remove `hunter.py` now** (no new code needed — just deletion and import cleanup). Count this as the **banked deprecation** against one future ADD per the anti-bloat framework one-in-one-out rule.

### C. 15m session filter scope
**Decision required:** Should 15m Holy Grail server-side gate match 1H (no gate) or add 30-min open/close/lunch skip?
**Recommendation: Add 15m gate (30-min open + 30-min close only; skip lunch is optional).** 15m is noisier; the two highest-risk windows are open and close whipsaws. This is a LOW-effort, HIGH-impact config add in `tradingview.py`.

### D. 15m feed tier ceiling
**Current:** 15m can theoretically reach `top_feed` tier if confluence stacks (base 40 + bonuses). Given the 10-point handicap vs 1H (40 vs 50), this is unlikely but possible.
**Recommendation: Set `feed_tier_ceiling = "watchlist"` for all 15m Holy Grail signals.** 15m is a research/watchlist signal category, not a primary feed signal. Implement in `feed_tier_classifier.py` alongside the iv_regime gate (Tier 1).

### E. `hunter.py` vs `ursa_taurus.py` naming inconsistency in `feed_tier_classifier.py`
`feed_tier_classifier.py` references `SNIPER_URSA`/`SNIPER_TAURUS` (hunter naming) AND `URSA_SIGNAL`/`TAURUS_SIGNAL` (ursa_taurus naming) as separate signal types weighted identically. After `hunter.py` removal, `SNIPER_URSA`/`SNIPER_TAURUS` entries in the classifier become dead weight. Clean up in the same pass.

### F. EMA slope + HH/HL — do both or just slope?
**Raschke requires both** EMA slope + HH/HL structure for the trend filter. HH/HL tracking requires storing N-bar swing structure (non-trivial). **Recommendation: Ship EMA slope alone first** (Tier 2, easy) and bank HH/HL for Tier 3 — the slope alone closes half the gap with minimal complexity.
