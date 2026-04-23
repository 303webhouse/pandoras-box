# CC Build Brief — Holy Grail Tier 1: `iv_regime` Wiring

**Upstream context:**
- Olympus review 2026-04-22 (`docs/strategy-reviews/raschke/olympus-review-2026-04-22.md` — Pass 3 Tier 1 fix list, item #3)
- Holy Grail audit 2026-04-22 (`docs/audits/holy-grail-audit-2026-04-22.md` — flagged that `iv_regime` factor exists but is NOT wired to Holy Grail's gating path)
- `PROJECT_RULES.md` — anti-bloat framework, filter subtractiveness requirement (≥30% signal count reduction while holding expectancy)

**Build type:** Small, single-phase build. No Titans review required — this is the Tier 1 fix the 3-10 build explicitly deferred, not a new strategy.
**Estimate:** ~2 hours CC work.

---

## Prime Directives

1. **Read `PROJECT_RULES.md` and `CLAUDE.md` at repo root before touching code.**
2. **This is NOT a new indicator.** `iv_regime` already exists as a bias factor (`backend/bias_filters/iv_regime.py`) and is computed on the bias engine's schedule, storing a `FactorReading` in Redis. The work is purely wiring an existing cached reading into Holy Grail's classification path.
3. **Shadow mode first, production cutover second.** The gate ships as a `feed_tier_ceiling` modifier initially — it caps signals at `watchlist` (not `top_feed`) when VIX is in extreme regime, but does NOT suppress the signal entirely. This matches the 3-10 shadow-mode discipline: let Nick observe behavior in the feed before enabling hard suppression.
4. **All exact find/replace anchors are copy-paste-verbatim.** Do not paraphrase. If a string doesn't match, STOP and ask Nick.

---

## Background: Why This Is Needed

Olympus Pass 3 (Tier 1 fix #3) called for a VIX regime gate on Holy Grail — skip or de-prioritize signals when `VIX < 15` (too quiet, trend-continuation patterns fail) or `VIX > 30` (too chaotic, mean reversion dominates).

The audit revealed the `iv_regime` factor was computed and cached but never consumed by the feed tier classifier. Holy Grail's `_hg_touch_tolerance` reads VIX independently for tolerance widening, but there's no gating logic.

This brief wires the missing connection: **read the cached `iv_regime` reading in `feed_tier_classifier.classify_signal_tier()` and apply a ceiling when VIX is in extreme regime.**

---

## Phase 0 — Pre-Flight Check (15 min, no code)

Before any edits, verify:

1. `backend/bias_filters/iv_regime.py` exists and `compute_score()` stores a `FactorReading` with `raw_data["vix"]` and `raw_data["iv_rank"]` populated. Read lines 100–180 to confirm.
2. `backend/bias_engine/composite.py::get_latest_reading("iv_regime")` returns a `FactorReading` (or `None` if unavailable). Confirm signature around line 294.
3. `backend/scoring/feed_tier_classifier.py::classify_signal_tier(signal_data, score)` is the target function — confirm it exists and that `ceiling` is already part of its flow around lines 152–180.
4. Grep for existing callers of `classify_signal_tier` to confirm the signature change in this brief (making it async) won't break downstream. Expected caller: `backend/signals/pipeline.py:756–757`.

Report findings, then proceed to Phase 1.

---

## Phase 1 — Implementation

### 1.1 Add the VIX regime ceiling helper

Create a new helper function in `backend/scoring/feed_tier_classifier.py` that reads the cached `iv_regime` reading and returns a ceiling string if VIX is extreme.

**Location:** Add just before the `def classify_signal_tier` function (around line 142 — after `_pythia_confirms` helper ends).

**Content:**

```python
# ── VIX regime thresholds (Olympus 2026-04-22 Tier 1 fix #3) ─────────────────
# Extreme regimes suppress Holy Grail signals from reaching top_feed:
#   VIX < 15 → too quiet, trend continuation patterns under-perform
#   VIX > 30 → too chaotic, mean reversion dominates, HG continuation fails
# When VIX is in either extreme, cap the signal at 'watchlist' (still visible
# for research/context, but not promoted to top_feed). This is SHADOW MODE —
# we're observing gating behavior before escalating to hard suppression.
VIX_REGIME_LOW_THRESHOLD  = 15.0
VIX_REGIME_HIGH_THRESHOLD = 30.0

# Only apply the VIX regime gate to Holy Grail family signals.
# Other strategies have their own volatility sensitivity profiles.
VIX_GATED_SIGNAL_TYPES = {
    "HOLY_GRAIL",
    "HOLY_GRAIL_1H",
    "HOLY_GRAIL_15M",
}


async def _vix_regime_ceiling(signal_data: Dict[str, Any]) -> str | None:
    """
    Return 'watchlist' if the signal is a Holy Grail family signal AND VIX is
    in an extreme regime (< 15 or > 30). Returns None otherwise (no cap).

    Reads the cached iv_regime FactorReading from Redis via get_latest_reading.
    Silent-fail: if the factor is unavailable or stale, returns None (no cap
    applied) rather than blocking the signal. VIX gating is a quality
    modifier, not a safety-critical gate.
    """
    signal_type = (signal_data.get("signal_type") or "").upper()
    if signal_type not in VIX_GATED_SIGNAL_TYPES:
        return None

    try:
        from bias_engine.composite import get_latest_reading
        reading = await get_latest_reading("iv_regime")
        if not reading or not reading.raw_data:
            return None
        vix = reading.raw_data.get("vix")
        if vix is None:
            return None
        if vix < VIX_REGIME_LOW_THRESHOLD or vix > VIX_REGIME_HIGH_THRESHOLD:
            return "watchlist"
    except Exception:
        # Never block a signal on a classifier-side failure.
        return None

    return None
```

### 1.2 Make `classify_signal_tier` async and apply the VIX ceiling

The existing function is synchronous. Reading a Redis-backed factor requires `await`, so the function becomes async. This is the main change.

**EXACT FIND/REPLACE ANCHOR** in `backend/scoring/feed_tier_classifier.py`:

**FIND:**

```python
def classify_signal_tier(signal_data: Dict[str, Any], score: float) -> str:
    """
    Classify a signal into its feed tier.

    Returns one of: 'top_feed', 'watchlist', 'ta_feed', 'research_log'

    See module docstring for tier definitions and priority order.
    """
    ceiling         = signal_data.get("feed_tier_ceiling")
    signal_category = (signal_data.get("signal_category") or "").upper()
    signal_type     = (signal_data.get("signal_type")     or "").upper()

    # ── 1. WATCHLIST_PROMOTION → always watchlist ──────────────────────────
    if signal_category == "WATCHLIST_PROMOTION":
        return "watchlist"
```

**REPLACE WITH:**

```python
async def classify_signal_tier(signal_data: Dict[str, Any], score: float) -> str:
    """
    Classify a signal into its feed tier.

    Returns one of: 'top_feed', 'watchlist', 'ta_feed', 'research_log'

    See module docstring for tier definitions and priority order.
    """
    ceiling         = signal_data.get("feed_tier_ceiling")
    signal_category = (signal_data.get("signal_category") or "").upper()
    signal_type     = (signal_data.get("signal_type")     or "").upper()

    # ── 0. VIX regime ceiling (Olympus 2026-04-22 Tier 1 fix #3) ───────────
    # Apply BEFORE WATCHLIST_PROMOTION check so WATCHLIST_PROMOTION still wins
    # for non-HG signals. For HG signals in extreme VIX, this sets a ceiling
    # that prevents top_feed promotion.
    vix_ceiling = await _vix_regime_ceiling(signal_data)
    if vix_ceiling:
        # Take the more restrictive of existing ceiling and vix_ceiling.
        # Order: research_log (most restrictive) → ta_feed → watchlist → None.
        ceiling_restrictiveness = {
            "research_log": 3,
            "ta_feed":      2,
            "watchlist":    1,
        }
        current = ceiling_restrictiveness.get(ceiling, 0)
        proposed = ceiling_restrictiveness.get(vix_ceiling, 0)
        if proposed > current:
            ceiling = vix_ceiling
            signal_data["feed_tier_ceiling"] = vix_ceiling
            signal_data["_vix_regime_gated"] = True  # audit trail

    # ── 1. WATCHLIST_PROMOTION → always watchlist ──────────────────────────
    if signal_category == "WATCHLIST_PROMOTION":
        return "watchlist"
```

### 1.3 Update the caller in `signals/pipeline.py`

Because `classify_signal_tier` is now async, the one caller must be updated.

**EXACT FIND/REPLACE ANCHOR** in `backend/signals/pipeline.py` (around line 756):

**FIND:**

```python
        from scoring.feed_tier_classifier import classify_signal_tier
        signal_data["feed_tier"] = classify_signal_tier(
```

**REPLACE WITH:**

```python
        from scoring.feed_tier_classifier import classify_signal_tier
        signal_data["feed_tier"] = await classify_signal_tier(
```

### 1.4 Persist the `_vix_regime_gated` audit flag

When the gate fires, we set `signal_data["_vix_regime_gated"] = True`. For shadow-mode observability, this needs to land in the database as part of the `score_ceiling_reason` field (existing column, already handled by `log_signal`).

**CC task:** open `backend/signals/pipeline.py`, grep for `_score_ceiling_reason`. Find the section that builds this string/list. Add logic equivalent to:

```python
if signal_data.get("_vix_regime_gated"):
    # Append to existing reason list, or create new one.
    existing = signal_data.get("_score_ceiling_reason") or ""
    addition = "vix_regime_extreme"
    signal_data["_score_ceiling_reason"] = (
        f"{existing}; {addition}" if existing else addition
    )
```

If the exact structure of the reason field differs from what this snippet assumes, adapt to match the existing pattern. Do NOT invent a new field.

### 1.5 Unit tests

New file: `backend/tests/scoring/test_iv_regime_gate.py`

```python
"""
Tests for the VIX regime ceiling in feed_tier_classifier.

Shadow-mode gate (Olympus 2026-04-22 Tier 1 fix #3): when VIX is in extreme
regime (< 15 or > 30), Holy Grail signals get capped at 'watchlist' rather
than reaching 'top_feed'.
"""

from unittest.mock import AsyncMock, patch

import pytest

from scoring.feed_tier_classifier import classify_signal_tier


class _FakeReading:
    def __init__(self, vix):
        self.raw_data = {"vix": vix}


def _hg_signal(**overrides):
    base = {
        "signal_type": "HOLY_GRAIL",
        "strategy":    "Holy_Grail",
        "direction":   "LONG",
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_vix_low_regime_caps_hg_signal():
    with patch(
        "scoring.feed_tier_classifier.get_latest_reading",
        new_callable=AsyncMock,
        return_value=_FakeReading(vix=12.5),
    ):
        signal = _hg_signal()
        await classify_signal_tier(signal, score=85.0)
    assert signal.get("_vix_regime_gated") is True
    assert signal.get("feed_tier_ceiling") == "watchlist"


@pytest.mark.asyncio
async def test_vix_high_regime_caps_hg_signal():
    with patch(
        "scoring.feed_tier_classifier.get_latest_reading",
        new_callable=AsyncMock,
        return_value=_FakeReading(vix=35.0),
    ):
        signal = _hg_signal()
        await classify_signal_tier(signal, score=85.0)
    assert signal.get("_vix_regime_gated") is True
    assert signal.get("feed_tier_ceiling") == "watchlist"


@pytest.mark.asyncio
async def test_vix_normal_regime_does_not_gate():
    with patch(
        "scoring.feed_tier_classifier.get_latest_reading",
        new_callable=AsyncMock,
        return_value=_FakeReading(vix=22.0),
    ):
        signal = _hg_signal()
        await classify_signal_tier(signal, score=85.0)
    assert signal.get("_vix_regime_gated") is not True
    assert signal.get("feed_tier_ceiling") in (None,)


@pytest.mark.asyncio
async def test_non_hg_signal_unaffected_by_vix():
    # A non-HG signal during extreme VIX should NOT be gated.
    with patch(
        "scoring.feed_tier_classifier.get_latest_reading",
        new_callable=AsyncMock,
        return_value=_FakeReading(vix=12.0),
    ):
        signal = {"signal_type": "ARTEMIS_LONG", "strategy": "Artemis"}
        await classify_signal_tier(signal, score=85.0)
    assert signal.get("_vix_regime_gated") is not True


@pytest.mark.asyncio
async def test_silent_fail_when_factor_unavailable():
    # If get_latest_reading returns None (factor not cached), no gate applied.
    with patch(
        "scoring.feed_tier_classifier.get_latest_reading",
        new_callable=AsyncMock,
        return_value=None,
    ):
        signal = _hg_signal()
        await classify_signal_tier(signal, score=85.0)
    assert signal.get("_vix_regime_gated") is not True
```

Make sure the test file's directory has a `conftest.py` or matches the existing test discovery pattern. If `tests/scoring/` doesn't exist, create it with an `__init__.py`.

**Note on pytest-asyncio:** TODO.md already tracks that `pytest-asyncio` is missing from `requirements-dev.txt`. If running these tests locally requires it, install it (`pip install pytest-asyncio`) — but don't commit a requirements change as part of this brief.

---

## Phase 2 — Verification

### 2.1 Import check

```bash
cd backend && python -c "from scoring.feed_tier_classifier import classify_signal_tier; import asyncio; print('OK')"
```

### 2.2 Full test suite

```bash
cd backend && python -m pytest tests/ -v
```

Expected: same baseline (234 pass + 5 indicator + N new iv_regime tests) + 1 skip + 19 pre-existing async failures. **Zero new failures introduced.**

If the iv_regime tests fail because pytest-asyncio isn't installed, that's the tracked TODO — install it locally to run them, but do not add it to requirements in this commit.

### 2.3 Shadow-mode observability query

Post-deploy, this query confirms the gate is firing on Railway:

```sql
SELECT
  COUNT(*) FILTER (WHERE score_ceiling_reason LIKE '%vix_regime_extreme%') AS gated_count,
  COUNT(*) FILTER (WHERE strategy = 'Holy_Grail') AS total_hg_signals,
  MIN(created_at), MAX(created_at)
FROM signals
WHERE created_at > NOW() - INTERVAL '24 hours';
```

Add this to `TODO.md`'s Raschke verification checklist as Test 7 (Nick will handle).

---

## Phase 3 — Commit & Merge

Work on a feature branch:

```bash
git checkout main
git pull origin main
git checkout -b feature/hg-tier1-iv-regime-gate
```

Commit message:

```
feat(feed_tier): wire iv_regime VIX gate for Holy Grail (Olympus Tier 1 fix #3)

Reads the cached iv_regime FactorReading from Redis. When VIX is in
extreme regime (<15 or >30) on a Holy Grail family signal, caps the
feed tier at 'watchlist' rather than letting it reach 'top_feed'.

Shadow-mode gate — observes behavior before escalating to hard
suppression. Audit flag signal_data._vix_regime_gated + appended
score_ceiling_reason for post-deploy observability.

classify_signal_tier() is now async; updated the one caller in
signals/pipeline.py.

Refs:
- docs/strategy-reviews/raschke/olympus-review-2026-04-22.md (Pass 3 Tier 1)
- docs/audits/holy-grail-audit-2026-04-22.md (iv_regime not wired finding)
- docs/codex-briefs/brief-hg-tier1-iv-regime-gate.md (this brief)
```

Push to origin and open a PR for Nick to review. **Do NOT merge to main** — Nick merges once the verification query is added to TODO.md and the tests pass.

---

## Output to Nick

1. Branch HEAD SHA
2. Phase 0 findings (confirm preconditions)
3. Full test suite output
4. Confirmation the `classify_signal_tier` async conversion propagated correctly to `signals/pipeline.py`
5. Any surprises or scope-creep tempted but not taken

---

## Constraints

- Strict scope: VIX regime ceiling on Holy Grail signal types only. No other strategy types.
- No changes to `iv_regime.py` itself — it already works, just wire its output.
- No hard suppression yet — shadow-mode ceiling (`watchlist`) only. Hard suppression is a future ticket after observation.
- No new DB columns — reuse `score_ceiling_reason` for the audit trail.
- Do not touch `_hg_touch_tolerance` — that's the existing VIX-based tolerance widening and serves a different purpose (tolerance, not gating).

---

**End of brief.**
