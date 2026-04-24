# CC Build Brief — HG iv_regime Gate v2: Percentile + Guardrails

**Upstream context:**
- Olympus review: `docs/strategy-reviews/raschke/olympus-review-2026-04-22.md` **Pass 9** (VIX Threshold Recalibration, 2026-04-24)
- Previous iv_regime gate: `docs/codex-briefs/brief-hg-tier1-iv-regime-gate.md` (v1, shipped commit `57ea60d`)
- VIX history gap finding: DB has ~37 trading days as of 2026-04-24 (query evidence in Pass 9)

**Build type:** Medium-sized build. Two components bundled:
1. **FRED VIX backfill script** (one-shot — pulls 252-day VIXCLS history and seeds `factor_readings`)
2. **Percentile gate v2** (config, gate logic, dual-logging, tests, rollback)

**Estimate:** ~3-4 hours CC work.

**Prerequisite:** Day-0 calibration PR (#17) must be merged to main first. This brief assumes that's landed.

---

## Prime Directives

1. **Read `PROJECT_RULES.md` and `CLAUDE.md` at repo root before touching code.**
2. **Shadow mode only.** Percentile gate runs alongside legacy gate with dual-logging — neither suppresses the other. 60-day observation period before promotion.
3. **Legacy gate stays live.** Do NOT delete `VIX_REGIME_LOW_THRESHOLD = 15.0` or `VIX_REGIME_HIGH_THRESHOLD = 30.0`. Rollback capability depends on these still existing.
4. **Do NOT modify the existing `_vix_regime_ceiling` function signature callers rely on.** The dual-logging is additive — legacy function keeps its current behavior, v2 logic sits alongside it.
5. **FRED backfill is one-shot.** Pull once, write once, done. Don't build a reusable FRED client — that's scope creep.
6. **All find/replace anchors are copy-paste-verbatim.** If a string has drifted, STOP and ask Nick.
7. **All writes to `factor_readings` MUST use `source='fred_backfill'`** to distinguish from live `source='yfinance'` readings. This is critical for the rollback story.


---

## Phase A — FRED VIX Backfill (one-shot, ~45 min)

### A.1 Purpose

Seed `factor_readings` with 252 trading days of historical VIX close values so the percentile gate has real history to compute against from day 1. Without this, the gate runs in warmup fallback mode for ~9 months while DB organically accumulates readings.

### A.2 Script location

Create `scripts/fred_vix_backfill.py` at the repo root's `scripts/` directory (NOT under `backend/`). This is a one-shot admin script, not production infrastructure.

### A.3 FRED API details

- Endpoint: `https://api.stlouisfed.org/fred/series/observations`
- Required query params:
  - `series_id=VIXCLS` (VIX daily close)
  - `file_type=json`
  - `api_key=<FRED_API_KEY>` — see credentials below
  - `observation_start=<date>` — calculate as today minus ~365 calendar days (to cover 252 trading days with buffer)
- Response shape: `{"observations": [{"date": "YYYY-MM-DD", "value": "18.74", ...}, ...]}`
- Skip observations where `value == "."` (FRED's missing-data sentinel — happens on holidays)

### A.4 FRED API key

FRED requires a free API key. Options:
1. Check if `FRED_API_KEY` is already in `claude_desktop_config.json` or Railway env — use that
2. If not present, Nick needs to register at https://fred.stlouisfed.org/docs/api/api_key.html (30 seconds, instant approval)

**CC task:** check for existing key first. If missing, STOP and tell Nick to register. Do NOT hardcode a key.

### A.5 Schema mapping

Each FRED observation becomes one row in `factor_readings`:

```python
{
    "factor_id":   "iv_regime",
    "score":       None,  # not computed historically — gate only needs raw vix
    "signal":      None,  # same reasoning
    "source":      "fred_backfill",  # CRITICAL — distinguishes from 'yfinance' live readings
    "metadata":    {
        "raw_data": {
            "vix":         float(observation.value),
            "iv_rank":     None,  # not available retroactively
            "rank_source": "fred_backfill",
            "source_note": "VIXCLS daily close from FRED — historical backfill for percentile gate",
        },
    },
    "timestamp":   datetime(observation.date, 16, 00),  # 16:00 UTC = market close
    "created_at":  datetime.utcnow(),
}
```

**Key discipline:** only write `factor_id='iv_regime'` rows with `source='fred_backfill'`. Do not touch existing live readings.

### A.6 Idempotency

Script must be safe to re-run. Approach:
1. Query DB for existing `source='fred_backfill'` rows, build set of dates already backfilled
2. Skip FRED observations whose dates are already in the set
3. Only INSERT new dates

If the script is re-run after a partial failure, it resumes cleanly.

### A.7 Verification output

After backfill, script prints:
```
FRED backfill complete.
  FRED observations fetched:    N
  Missing-data (.) skipped:     N
  Already-present skipped:      N
  New rows inserted:            N
  Total fred_backfill rows now: N
  Date range: YYYY-MM-DD to YYYY-MM-DD
  Trading days covered:         N (target: ≥252)
```

If "Trading days covered" < 252, script exits with code 2 and Nick needs to adjust `observation_start` to pull further back.

### A.8 Run posture

This script runs LOCALLY on Nick's Windows machine, not on the VPS or Railway. Reason: it hits Railway's public Postgres endpoint from Nick's IP (sandbox can't reach Railway), and it's a one-shot admin task. Once complete, the data lives in Railway and the percentile gate reads it from there normally.

CC task: create the script, run it locally (or walk Nick through running it), verify the row counts land, confirm `SELECT COUNT(*) FROM factor_readings WHERE source='fred_backfill'` returns ≥252.


---

## Phase B — Percentile Gate v2 Implementation

### B.1 Config additions

**EXACT FIND/REPLACE ANCHOR** in `backend/signals/pipeline.py`:

**FIND:**

```python
# ── VIX regime thresholds (Olympus 2026-04-22 Tier 1 fix #3) ─────────────────
# Extreme regimes suppress Holy Grail signals from reaching top_feed:
#   VIX < 15 → too quiet, trend continuation patterns under-perform
#   VIX > 30 → too chaotic, mean reversion dominates, HG continuation fails
VIX_REGIME_LOW_THRESHOLD  = 15.0
VIX_REGIME_HIGH_THRESHOLD = 30.0

TREND_CONTINUATION_STRATEGIES = {"Holy_Grail"}
```

**REPLACE WITH:**

```python
# ── VIX regime thresholds (Olympus 2026-04-22 Tier 1 fix #3) ─────────────────
# Legacy absolute thresholds (v1, shipped 2026-04-23, commit 57ea60d).
# KEEP THESE — rollback capability depends on legacy logic remaining live.
VIX_REGIME_LOW_THRESHOLD  = 15.0
VIX_REGIME_HIGH_THRESHOLD = 30.0

# Percentile gate v2 (Olympus Pass 9, 2026-04-24). Shadow-mode dual-log
# alongside v1 for 60 days, then promote to default or revert.
# Per empirical finding: VIX ≥ 30 has become a crisis-regime marker in
# post-2023 structural vol regime. Percentile-based gate corrects the drift.
VIX_REGIME_USE_PERCENTILE       = True      # master feature flag
VIX_REGIME_PERCENTILE_LOW        = 5.0       # 5th percentile of lookback
VIX_REGIME_PERCENTILE_HIGH       = 90.0      # 90th percentile of lookback
VIX_REGIME_PERCENTILE_LOOKBACK   = 252       # trading days
VIX_REGIME_ABS_FLOOR             = 11.0      # always-suppress override (compressed, reversal-risk)
VIX_REGIME_ABS_CEILING           = 35.0      # always-suppress override (crisis)
VIX_REGIME_WARMUP_FALLBACK_LOW   = 14.0      # used if <252 days history in DB
VIX_REGIME_WARMUP_FALLBACK_HIGH  = 28.0      # used if <252 days history in DB

TREND_CONTINUATION_STRATEGIES = {"Holy_Grail"}
# CTA/Artemis/Sell_the_Rip require per-strategy Olympus review first.
# (Named here for context; not active in this gate.)
```


### B.2 Percentile computation helper

Add this helper function in `backend/signals/pipeline.py`, placed just above the existing `_vix_regime_ceiling` logic (or wherever you placed the v1 gate — grep for `vix_regime_extreme` to find the exact location):

```python
async def _compute_vix_percentiles(lookback_days: int = 252) -> dict | None:
    """
    Compute VIX percentiles from factor_readings over lookback window.
    Returns {'p5', 'p90', 'n_days', 'p5_value', 'p90_value'} or None if insufficient data.

    Queries daily VIX close readings (deduped by date, most recent reading per day).
    Uses numpy.percentile for consistent computation.
    """
    try:
        from postgres_client import fetch_all  # or existing DB accessor pattern
        rows = await fetch_all("""
            SELECT DISTINCT ON (DATE(timestamp))
                DATE(timestamp) AS day,
                (metadata->'raw_data'->>'vix')::FLOAT AS vix
            FROM factor_readings
            WHERE factor_id = 'iv_regime'
              AND metadata->'raw_data'->>'vix' IS NOT NULL
              AND timestamp > NOW() - INTERVAL '%s days' * 1.5
            ORDER BY DATE(timestamp), timestamp DESC
            LIMIT %s
        """, (lookback_days, lookback_days))

        if len(rows) < lookback_days:
            return None  # signal warmup — caller falls back to absolute thresholds

        import numpy as np
        vix_values = [r['vix'] for r in rows]
        return {
            'p5_value':  float(np.percentile(vix_values, VIX_REGIME_PERCENTILE_LOW)),
            'p90_value': float(np.percentile(vix_values, VIX_REGIME_PERCENTILE_HIGH)),
            'n_days':    len(rows),
        }
    except Exception as exc:
        logger.warning(f"VIX percentile computation failed: {exc}")
        return None
```

**Note on the DB accessor:** match the existing pipeline.py pattern. If pipeline.py uses `async_session` + SQLAlchemy, use that. If it uses `asyncpg` directly, use that. Do NOT introduce a new DB client pattern.


### B.3 Gate decision logic — dual evaluation

The existing v1 gate logic (grep for `vix_regime_extreme` in `pipeline.py`) currently looks something like:

```python
# Existing v1 logic — DO NOT DELETE, just extend
strategy = signal_data.get("strategy", "")
if strategy in TREND_CONTINUATION_STRATEGIES:
    vix = ...  # read from iv_regime factor cache
    if vix < VIX_REGIME_LOW_THRESHOLD or vix > VIX_REGIME_HIGH_THRESHOLD:
        # Suppress to watchlist, record reason
        signal_data["feed_tier_ceiling"] = "watchlist"
        signal_data["_score_ceiling_reason"] = "vix_regime_extreme"
```

**REPLACE the existing `if vix < VIX_REGIME_LOW_THRESHOLD or vix > VIX_REGIME_HIGH_THRESHOLD:` block with dual evaluation:**

```python
strategy = signal_data.get("strategy", "")
if strategy in TREND_CONTINUATION_STRATEGIES:
    vix = ...  # read from iv_regime factor cache (unchanged)

    # ── v1 legacy gate (always computed for dual-logging) ─────────────────
    v1_suppressed = vix < VIX_REGIME_LOW_THRESHOLD or vix > VIX_REGIME_HIGH_THRESHOLD
    v1_threshold_used = f"{VIX_REGIME_LOW_THRESHOLD}/{VIX_REGIME_HIGH_THRESHOLD}"

    # ── v2 percentile gate (Olympus Pass 9) ──────────────────────────────
    v2_suppressed = False
    v2_threshold_used = None
    v2_meta = {}

    if VIX_REGIME_USE_PERCENTILE:
        pct = await _compute_vix_percentiles(VIX_REGIME_PERCENTILE_LOOKBACK)
        if pct:
            # Full percentile mode
            low, high = pct['p5_value'], pct['p90_value']
            v2_meta = {"p5": low, "p90": high, "n_days": pct['n_days'], "mode": "percentile"}
            v2_threshold_used = f"p5={low:.2f}/p90={high:.2f}"
            v2_suppressed = (
                vix < low
                or vix > high
                or vix < VIX_REGIME_ABS_FLOOR    # always-suppress override
                or vix > VIX_REGIME_ABS_CEILING  # always-suppress override
            )
        else:
            # Warmup fallback — not enough history yet
            low, high = VIX_REGIME_WARMUP_FALLBACK_LOW, VIX_REGIME_WARMUP_FALLBACK_HIGH
            v2_meta = {"mode": "warmup_fallback", "low": low, "high": high}
            v2_threshold_used = f"warmup={low}/{high}"
            v2_suppressed = vix < low or vix > high

    # ── Dual-logging (both decisions written to committee_data) ──────────
    signal_data.setdefault("committee_data", {})["iv_regime_legacy"] = {
        "decision": "suppress" if v1_suppressed else "allow",
        "threshold_used": v1_threshold_used,
        "vix_value": vix,
    }
    signal_data["committee_data"]["iv_regime_v2"] = {
        "decision": "suppress" if v2_suppressed else "allow",
        "threshold_used": v2_threshold_used,
        "vix_value": vix,
        **v2_meta,
    }
    signal_data["committee_data"]["iv_regime_diverged"] = (v1_suppressed != v2_suppressed)

    # ── Effective suppression: v1 stays authoritative until promotion ────
    # This is critical — v2 runs in shadow mode only. Do NOT let v2 affect
    # the actual feed_tier until 60-day validation completes.
    if v1_suppressed:
        signal_data["feed_tier_ceiling"] = "watchlist"
        signal_data["_score_ceiling_reason"] = "vix_regime_extreme"
```


### B.4 Discord divergence alerts

When `iv_regime_diverged = True`, we want a real-time notification to `#zeus-ta-feed`. This is the validation signal for the 60-day review.

**CC task:** add a hook to the existing Discord alert dispatch code (probably in whatever file handles `_score_ceiling_reason` → Discord post). When writing a new signal row with `committee_data.iv_regime_diverged = true`, queue a Discord message to the webhook stored in `DISCORD_WEBHOOK_BRIEFS` (the one we fixed earlier — it's the catchall for VPS alerts until separate channels are set up).

Message format:
```
🔀 iv_regime gate divergence — {ticker} {strategy}
  VIX: {vix_value}
  v1 ({v1_threshold}): {v1_decision}
  v2 ({v2_threshold}): {v2_decision}
  Signal: {signal_url_if_available}
```

Throttle: max 1 divergence alert per ticker per hour (simple in-memory dedupe, can reset on process restart — don't over-engineer).

If the existing alert dispatch doesn't have a clean hook, flag it and Nick will decide whether to add it now or defer to a follow-up brief. Don't force the integration if it requires significant refactor.

---

## Phase C — Tests

### C.1 Unit tests

New file: `backend/tests/signals/test_vix_percentile_gate.py`

Tests required:
1. `test_percentile_computation_with_synthetic_low_vol_series` — feed 252 VIX values centered around 12, assert p5 and p90 are both below 15
2. `test_percentile_computation_with_synthetic_high_vol_series` — feed 252 VIX values centered around 28, assert p90 is above 32
3. `test_percentile_computation_with_regime_shift` — first 150 values at 14, next 102 at 22. Assert p90 is around 23-25 (blended)
4. `test_warmup_fallback_when_history_insufficient` — mock only 50 days of readings. Assert `_compute_vix_percentiles` returns None and the caller falls back to warmup thresholds (14/28)
5. `test_abs_floor_always_suppresses` — set vix=10 (below 11 floor). Even if percentiles would say "allow" (synthetic extreme low-vol history), assert `v2_suppressed = True`
6. `test_abs_ceiling_always_suppresses` — set vix=40 (above 35 ceiling). Assert `v2_suppressed = True` regardless of percentile state
7. `test_dual_log_diverged_flag_true_when_decisions_disagree` — construct a scenario where v1 allows but v2 suppresses (VIX=26, between 15 and 30 legacy but above p90=24). Assert `iv_regime_diverged = True` in committee_data
8. `test_dual_log_diverged_flag_false_when_decisions_agree` — VIX in comfortable middle. Assert `iv_regime_diverged = False`

### C.2 Integration test — March 2026 drawdown replay

New file: `backend/tests/integration/test_vix_gate_march_2026_replay.py`

This is the ATHENA-requested integration test. Replay a 30-day window covering the March 2026 drawdown through the gate with dual-logging active. Assert:
- At VIX values 26-28 during the drawdown: `v1_suppressed = False` AND `v2_suppressed = True` (legacy fails to catch the regime; percentile catches it)
- At least 5 days in the replay window show `iv_regime_diverged = True`
- No days show `v2` suppressing when VIX is in the 15-25 comfortable range

Use real historical VIX close data from FRED backfill (after Phase A runs) as the replay source. Build a mock signal-emitting scenario with a Holy_Grail strategy firing daily — doesn't need to be realistic signals, just needs the gate to evaluate each day.


---

## Phase D — Verification Post-Deploy

Once the build is deployed and running on Railway, run these queries to confirm the gate is behaving correctly.

### D.1 Percentile gate is reading real history (not warmup)

```sql
-- Should return percentile-mode decisions, not warmup
SELECT
    DATE(created_at) as day,
    COUNT(*) FILTER (WHERE committee_data->'iv_regime_v2'->>'mode' = 'percentile') as pct_mode,
    COUNT(*) FILTER (WHERE committee_data->'iv_regime_v2'->>'mode' = 'warmup_fallback') as warmup_mode,
    COUNT(*) as total
FROM signals
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND strategy = 'Holy_Grail'
GROUP BY DATE(created_at)
ORDER BY day DESC;
```

**Expected after FRED backfill:** `pct_mode` > 0 and `warmup_mode` = 0 for all recent days.

### D.2 Divergence rate is measurable but not runaway

```sql
SELECT
    COUNT(*) FILTER (WHERE (committee_data->>'iv_regime_diverged')::BOOLEAN) as diverged,
    COUNT(*) as total_hg,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE (committee_data->>'iv_regime_diverged')::BOOLEAN) / NULLIF(COUNT(*), 0),
        1
    ) as pct_diverged
FROM signals
WHERE created_at > NOW() - INTERVAL '7 days'
  AND strategy = 'Holy_Grail';
```

**Expected after 7 days:** `pct_diverged` between 5% and 30%. If 0%, the gates are producing identical decisions (possibly a bug). If >50%, the percentile thresholds may be miscalibrated — escalate to Olympus.

### D.3 Percentile values are reasonable

```sql
SELECT
    DISTINCT
    committee_data->'iv_regime_v2'->>'threshold_used' as thresholds,
    committee_data->'iv_regime_v2'->>'n_days' as lookback_used
FROM signals
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND strategy = 'Holy_Grail'
  AND committee_data->'iv_regime_v2'->>'mode' = 'percentile';
```

**Expected:** `thresholds` shows values like `p5=13.2/p90=22.7` (not absurdly extreme). `lookback_used` = 252 (or close to it).

---

## Phase E — Commit & Merge

Branch: `feature/hg-iv-regime-percentile-v2`

Commit message:

```
feat(pipeline): iv_regime gate v2 — percentile thresholds + dual-logging (Olympus Pass 9)

Shadow-mode percentile gate runs alongside v1 absolute gate. v1 stays
authoritative for feed_tier decisions; v2 logs decisions in committee_data
for 60-day validation. Discord alerts fire on gate divergence.

Per empirical finding (Nick 2026-04-24): VIX ≥ 30 has become a crisis
marker in post-2023 vol structure. Original 15/30 absolute gate failed
to catch the March 2026 drawdown where VIX peaked at 26-28. Percentile
gate with 5/90 thresholds corrects the calibration drift.

Data dependency: 252 trading days of VIX history in factor_readings.
Phase A of this brief includes a FRED VIXCLS backfill script.

Includes:
- scripts/fred_vix_backfill.py (one-shot admin script)
- config additions (percentile thresholds, guardrails, warmup fallback)
- _compute_vix_percentiles helper
- Dual-evaluation gate logic with committee_data logging
- Discord divergence alerts
- 8 unit tests + 1 integration test (March 2026 replay)

Rollback: flip VIX_REGIME_USE_PERCENTILE = False, zero other changes needed.

Refs:
- docs/strategy-reviews/raschke/olympus-review-2026-04-22.md (Pass 9)
- docs/codex-briefs/brief-hg-iv-regime-percentile-v2.md (this brief)
```

Push branch, open PR, **do NOT merge** — Nick reviews first.


---

## Output to Nick

Phase A (FRED backfill):
1. Path to `scripts/fred_vix_backfill.py`
2. FRED API key status (found existing, or flagged for Nick to register)
3. Backfill script execution output — row counts, date range, trading day total
4. SQL verification: `SELECT COUNT(*) FROM factor_readings WHERE source='fred_backfill'`

Phase B/C (gate + tests):
1. Branch HEAD SHA + PR link
2. Full test suite output (expect baseline + 8 new unit tests + 1 integration)
3. Confirmation all percentile-mode queries return sensible values
4. Any surprises or scope-creep tempted but not taken

---

## Constraints

- **Strict scope:** Phase A backfill + Phase B/C v2 gate implementation only. Do NOT touch Day-0 calibration (already merged). Do NOT expand to other strategies (Artemis/CTA/Sell_the_Rip remain explicitly out of scope per Pass 9 §11 decisions).
- **Do NOT delete or modify `VIX_REGIME_LOW_THRESHOLD` or `VIX_REGIME_HIGH_THRESHOLD`.** These are the rollback mechanism. Pass 9 promotion happens 60 days from now after Olympus review of divergence data.
- **Do NOT modify the effective gate behavior.** v1 stays authoritative. v2 is shadow-logged only. If you find yourself tempted to make v2 affect `feed_tier_ceiling`, STOP — that's the promotion step, not this build.
- **Do NOT modify `docs/strategy-reviews/` files.** The Olympus doc (including Pass 9) is the source of truth for this build's requirements. Additions to that folder are allowed; deletions or edits to existing content are NOT.
- **Do NOT commit the FRED API key to git.** It goes in env vars / claude_desktop_config.json only.
- **Do NOT hardcode a 252-day FRED lookback.** Use `observation_start` as a calculated value (today minus ~365 calendar days) so the script works when re-run on any future date.
- **No new DB migrations.** The `factor_readings` table and `committee_data` JSONB column already support everything this brief requires.
- **Rollback is a config flag flip.** `VIX_REGIME_USE_PERCENTILE = False` reverts behavior. Zero code changes. If your build can't be rolled back this way, the architecture is wrong.

---

**End of brief.**
