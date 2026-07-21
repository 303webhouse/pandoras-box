# DEF-FUNDING-CACHE-HEALTH — completion report

**Brief:** `docs/codex-briefs/2026-07-21-def-funding-cache-health-micro-brief.md`
**Commit:** `db5e398` (code + tests). Deployed 2026-07-21, Railway SUCCESS.
**Severity:** P1 — false-negative signal suppression (fake-degraded).
**Result:** Fixed, tested (4 tests proven failing pre-fix), 4-step deploy verified.

---

## Verdict

`_finalize_result()` cached the funding result **before** attaching
`health_status`, so every cache hit inside the 300s TTL returned a dict missing
the field, and the funding consumer's bare `.get("health_status")` read `None →
degraded=true` on healthy data. Fixed by building one merged dict and using it
for both the cache write and the return, so the two paths cannot diverge again.

---

## Phase 0 — confirmed before editing

1. **Ordering — confirmed exactly as the brief states.** Pre-fix
   `coinalyze_client.py`: line 119 `_set_cache(cache_key, result)` (no
   `health_status`), line 120 `return {**result, "health_status": status}`
   (attached only to the return).
2. **Consumers — confirmed.** Funding uses a **bare** `.get("health_status")` at
   `api/crypto_market.py:716`. OI (`:740`) and basis (`:752`) use
   `.get("health_status", "LIVE")` — structurally immune, which is why the bug
   presented as funding-specific.
3. **TTL = 300s** (`CACHE_TTL_SECONDS`, line 61). The single funding cache-writer
   is the `_finalize_result` line; the reader is `get_funding_rate` lines
   212–214, returning `cached["data"]` by reference.
4. **Scope — wider than funding, and better for it.** `_finalize_result` is
   shared by **funding, OI, and term_structure** (all route through it), so the
   one-line fix corrects the cache-hit path for all three. It cannot regress OI
   or term_structure because their cache-*miss* path already returns
   `health_status` and their consumers already tolerate it. `get_liquidations`
   uses a separate cache path (`_set_cache` at the get_liquidations sites) and
   has **no** `health_status` consumer in `crypto_market.py` (which has exactly
   three `health_status` readers: funding/OI/basis) — correctly untouched.

---

## Phase 1 — fix applied

Primary root-cause fix only. The cached and returned objects are now the same
merged dict:

```python
result_with_health = {**result, "health_status": status}
_set_cache(cache_key, result_with_health)
return result_with_health
```

The D1.4 `FIRING → NEUTRAL` contract was **not touched** — it is correct and
stays. This fixes the input, never the rule.

---

## Phase 2 — verification

### 1. Unit tests — PROVEN FAILING PRE-FIX

`backend/tests/test_def_funding_cache_health.py`, 4 tests. Method: `git stash`
of the source edit, ran the tests against pre-fix code → **4/4 FAILED**, then
`git stash pop` → **4/4 PASSED**. A regression guard that passes pre-fix guards
nothing; these demonstrably do not.

The pre-fix failure output is the bug itself: the cache-hit dict was
`{'funding_rate': 0.0013, ...}` with **no `health_status`** while the fresh dict
carried `'health_status': 'LIVE'`.

| Test | Locks |
|---|---|
| `test_cache_hit_carries_health_status` | cache hit returns `health_status` intact (1 network call, 2nd served from cache) |
| `test_consumer_degraded_stable_across_cache_hit` | the `false,true,true` production repro reduced to a unit — now `false,false,false` |
| `test_honest_degradation_survives_cache_hit` | a genuinely DEGRADED fetch still reads DEGRADED on cache hits (see §4 below) |
| `test_cache_and_return_are_consistent` | cached object and returned object carry identical `health_status` |

### 2. Live three-call repro — PASS

Post-deploy, `GET /api/crypto/state/{symbol}` inside one 300s TTL window
(container restarted ~40s prior, so call 1 = cache miss, subsequent = hits):

| Symbol | Calls | `funding.degraded` | rate (identical) |
|---|---|---|---|
| BTC | 3 | **false, false, false** | 0.0013 |
| ETH | 5 | **false ×5** | 0.0018 |
| SOL | 3 | **false, false, false** | 0.0052 |

Prior failing state (04a1983) was `false, true, true` at 0.0013. All symbols now
hold a stable verdict across the full window with an identical rate — proof the
flip was purely a cache artifact and is gone.

### 3. Non-regression (OI + basis) — PASS

OI and basis read `degraded=false` across every call above. They were never
affected and stay unaffected.

### 4. Honest-degradation path — EXERCISED AT UNIT LEVEL, NOT EXERCISABLE LIVE

Stated plainly per the brief, because this is the one way the fix could be worse
than the bug:

- **Unit: exercised and green.** `test_honest_degradation_survives_cache_hit`
  forces `record_observation → "DEGRADED"` with an in-bounds value (so it *is*
  cached), and asserts the cache hit returns `health_status == "DEGRADED"` and
  the consumer computes `degraded=true`. The fix does **not** convert a real
  degradation into a false all-clear.
- **Live: NOT exercised — and I am not claiming it.** I cannot force a genuine
  Coinalyze degradation in production without a write or an actual vendor
  outage, both out of scope for a read-only verification. The vendor was healthy
  throughout (`crypto_vendor_health_audit` shows zero non-LIVE funding rows all
  window). So the live degraded-path is reasoned-about and unit-proven, not
  production-observed. If it must be observed live, it needs a sanctioned fault
  injection, which this brief did not authorize.

### 5. Full suite — byte-identical known-red

**18 failed / 492 passed / 1 skipped / 200 errors.** Failed/skipped/errors
unchanged from baseline; passed 488 → 492 = exactly the 4 new tests.

### 6. Four-step deploy verification

1. Railway **SUCCESS** (deploy of `db5e398`).
2. SHA attribution: deploy commit `db5e398` matches the pushed commit.
3. Empirical side-effect: the live three-call repro above (§2) — the observable
   patch behavior, not `/health`.
4. Not silent — deploy completed in ~105s; health 200 after ~40s cycle.

---

## Consumer-side "LIVE" default — RECOMMENDATION, NOT APPLIED

The brief asked me to report, not bundle. **Recommendation: apply it, but as a
separate defensive commit if the coordination lane calls it — not required for
correctness now.**

Aligning funding's bare `.get("health_status")` at `crypto_market.py:716` to the
`.get("health_status", "LIVE")` default used by OI (`:740`) and basis (`:752`)
would make funding structurally immune to any *future* re-introduction of this
class of bug, and it matches in-file precedent (two of three sibling consumers
already do it).

Two caveats that make it a **secondary** change, correctly deferred:

1. It **masks** a missing field rather than fixing it. With the root cause now
   fixed, `health_status` is always present on funding reads, so the default
   would never actually fire today — it is pure belt-and-suspenders.
2. A default of `"LIVE"` is fail-**open** (absent field → treated as healthy).
   That is the right bias for a display/enrichment field and matches the
   siblings, but it is the opposite of the envelope's own fail-*closed* default
   (`_field_envelope` treats `None` degraded as `True`). Worth a deliberate
   decision rather than a reflexive copy, which is exactly why it should be its
   own commit with its own reasoning, not bundled here where it would be
   invisible.

Not applied. Awaiting an explicit call.

---

## Olympus impact

Committee agents and the Discord notifier both hide the funding line when
`degraded` fires. Post-fix, funding data will appear in crypto committee passes
and embeds **substantially more often** — a restoration, not a new feature, but
it will read as a behavior change, so it is noted here.

**Data surface confirmed correct** (the prerequisite for the committee pass):
`/api/crypto/state/{BTC,ETH,SOL}` now return `funding.degraded=false` with sane
rates. The actual **one crypto committee pass on a Tier-1 symbol** the brief
requests runs in Claude.ai / on the VPS, not from this lane — flagged as the
coordination lane's post-deploy step, alongside confirming the funding line
renders with these values rather than the suppressed state that had been the
norm.

---

## Out of scope (per brief, untouched)

- Persisting `degraded` — deferred indefinitely; the motivation evaporated in
  Phase 0 (neither gate reads this input).
- Flipping `funding_fade_negative_floor_raise_enabled` / the Tier-3 block — both
  stay shadow.
- `Funding_Rate_Fade`'s zero-signal problem — routed to the W2-4 silent-strategy
  triage (Kodiak / Nemesis / Icarus). Not investigated here.
