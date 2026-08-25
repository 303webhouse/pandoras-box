# BRIEF — Factor-render coverage honesty

**Ordered:** spine R-IV.99 item 2 (committee-stack item 1) · **Lane:** CC-BUILD
**Defect class:** compute-then-discard / fake-healthy · **Built:** 2026-08-25

## Symptom

The composite bias score renders identically whether it was computed from 20 factors
or 3. A consumer — including the trading committee — cannot tell how much evidence
the number rests on.

## Mechanism

`backend/bias_engine/composite.py`, in `compute_composite()`:

```python
active_weight_sum = sum(FACTOR_CONFIG[f]["weight"] for f in active)
normalized_weights = {f: FACTOR_CONFIG[f]["weight"] / active_weight_sum for f in active}
raw_score = sum(active[f].score * normalized_weights[f] for f in active)
```

`FACTOR_CONFIG` holds **20 factors whose weights sum to exactly 1.0000** (asserted at
import). So `active_weight_sum` **is** the fraction of intended evidence that survived
staleness. It was computed, used once as a normalisation divisor, and discarded.

Because the surviving factors are renormalised back to a full weight of 1.0, a score
built on 19% of the book is numerically indistinguishable from one built on 100%.

### Why `confidence` did not already cover this

`confidence` is **count-based**:

```python
active_count = len(active)
if active_count >= 6:   _conf = "HIGH"
elif active_count >= 4: _conf = "MEDIUM"
else:                   _conf = "LOW"
```

Measured against the live weight table:

| six active factors | actual coverage |
|---|---|
| the six heaviest | **0.400** |
| the six lightest | **0.190** |

**`"HIGH"` spans 19%–40% of the intended evidence.** A count cannot stand in for a
weight, and the field that could say so was being thrown away.

## What was NOT wrong (correction to the T8 step-3 report)

The excluded-factor **identities were already surfaced** as `stale_factors`
(`composite.py:918` → `CompositeResult:960`). The earlier finding that "the composite
renders no indication of which factors were excluded" was wrong — it came from a grep
for `excluded|missing_factors|unavailable|skipped`, which missed the word actually
used. Half of R-IV.67(iv) was already implemented. Only the coverage ratio was missing.

`excluded_factors` is still added here, as the explicit complement of `active` over
`FACTOR_CONFIG`, because `stale_factors` is built from `stale_set` and the complement
formulation also names a factor that never reported at all.

## Change

Three surfaces, because surfacing on the model alone would not reach any consumer.

1. **`bias_engine/composite.py`** — `CompositeResult` gains
   `coverage_ratio: Optional[float]` and `excluded_factors: List[str]`;
   `compute_composite()` assigns `coverage_ratio = round(active_weight_sum, 4)`,
   deriving it from the divisor actually used rather than recomputing it.
2. **`hub_mcp/tools/bias_composite.py`** — the committee-facing payload previously
   emitted only `active_factor_count` / `stale_factor_count` (counts — the misleading
   measure) with `"weight": None` on every factor. Now carries `coverage_ratio` and
   `excluded_factors`.
3. **`api/bias.py`** — the REST payload emitted `confidence` but no coverage. Now
   carries both.

`None`, never `0.0`, when unknown — **GREEKS-ZERO precedent**. A cached pre-fix
payload deserialises without the field, and "unknown coverage" must not render as
"zero factors active".

## Explicitly out of scope

**`confidence`'s thresholds are unchanged.** Re-tiering it on weight would alter live
trading behaviour — `composite.py:600` branches on `LOW`, and `:998` alerts on a
`HIGH → LOW` transition. The order was to *surface* the ratio, not to re-tier. That
`confidence` remains count-based and spans 19–40% is reported as a finding for spine,
not acted on here.

## Verification

`backend/tests/test_composite_coverage_honesty.py` — 7 tests, all passing.

Fail-first proven: each test was driven against a **reconstructed pre-fix**
`composite.py` (edits reversed in memory — no tree mutation, per the restore-point
clause) and **all six discriminating assertions failed**, three by `AttributeError`
on the absent fields and three by `AssertionError` on the absent source expressions.
Zero non-discriminating tests. The same assertions pass against post-fix source.

The load-bearing test is `test_coverage_discriminates_what_confidence_conflates`: it
constructs two results that are both `confidence="HIGH"`, asserts the confidence
fields are equal, and asserts the coverage ratios are not.

Regression: `pytest -k "composite or bias"` → **23 passed**, unchanged from pre-change.
The 8 errors in `test_frontend_routes.py` are pre-existing suite debt
(`TypeError: Client.__init__() got an unexpected keyword argument 'app'`, an httpx
TestClient version mismatch) in files this change does not touch.

## Follow-on, not built

- `confidence` re-tiering on weight rather than count — needs a ruling, changes behaviour.
- Frontend render of `coverage_ratio`. The data is now available; no UI work was done.
- The same compute-then-discard shape remains open at two other sites already filed:
  `UWUnavailable` discarded at the flow-poller call site, and per-row `is_stale`
  discarded by `total_balance` (`portfolio_balances.py:118-120`, approved-shape,
  gated on the descoping decision).
