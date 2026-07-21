# DEF-FUNDING-DUTY-CYCLE — Phase 0 findings (STOP-GATE FIRED)

**Brief:** `docs/codex-briefs/2026-07-21-def-funding-duty-cycle-micro-brief.md`
**Executed:** 2026-07-21, ~21:00–21:20 UTC (15:00–15:20 MDT)
**Status:** **Phase 0 halted execution. Phase 1 was not run.** Two separate stop
conditions fired, and a live production defect was found in the process.
**Writes performed:** none. No migrations, no config changes, no gate flips.

---

## Verdict, stated first

**The funding `degraded` flag is NOT PERSISTED. The duty cycle is not
retroactively measurable.** Per the brief's own stop condition, that is the
complete and correct deliverable for this branch, and the forward-persistence
proposal below is the substitute.

Method: five independent trace lanes (flag origin, code write-paths, live
schema, shadow-log, non-Postgres stores) followed by three adversarial
verifiers instructed to refute the consensus. **0 of 3 refuted.** All three
independently corrected to `NOT_PERSISTED`. Every load-bearing claim below was
then re-verified by hand against source and the live database.

The flag is computed inline in the request handler at
`backend/api/crypto_market.py:716`:

```python
funding_degraded = is_na or bool(funding_data.get("error")) or funding_data.get("health_status") != "LIVE"
```

It is placed into the HTTP response envelope by `_field_envelope()` and returned
at `crypto_market.py:907`. It is a request-scoped local. There is no INSERT or
UPDATE anywhere in `get_crypto_state()` that writes it, and no log line records
it. It exists for the duration of one HTTP response and is discarded.

Searched and ruled out: all `crypto%` tables, every JSONB/JSON column DB-wide
for a nested `degraded` key, Redis, VPS local persistence, and log retention.

### Near-misses that must NOT be used as substitutes

| Location | Rows | Window (::text) | Why it is not the flag |
|---|---|---|---|
| `crypto_vendor_health_audit` (`feed_type='funding_rate'`) | 175 | 2026-07-13 → 2026-07-21 | **Transition-only** by design — a vendor that stays LIVE forever produces zero rows. All 175 are `LIVE`; zero DEGRADED/DEAD. |
| `crypto_cycle_log.cells` → `signal_id='perp_funding'` → `state` | 639 | 2026-07-16 → 2026-07-21 | Computed by a **different rule** that ignores `health_status` entirely. All 639 `LIVE`. |
| `crypto_cycle_log.cells` → `signal_id='funding_blowout'` → `state` | 639 | same | Same objection. |
| `crypto_regime_log.degraded`, `crypto_tape_health_log.degraded`, `crypto_cycle_log.degraded` | — | — | **Unrelated senses of the word** (live-cell count, CVD staleness). Not the funding flag. |

Both proxies read **100% LIVE across the entire window.** Section 3 shows the
API envelope simultaneously reporting `degraded=true` on most reads. They do not
merely under-report — they contradict the flag, so reconstruction from them
would produce a confident, wrong number. This is exactly the "incomplete number
is worse than a wrong one" failure the brief was written to avoid.

Reconstruction from a stored rate was also assessed and rejected: `degraded` is
an OR over three terms, two of which (`error`, `health_status`) depend on
process-local state and vendor call outcomes that no stored row determines.

---

## Contradiction 1 — the brief's core premise does not hold

> The brief: "Both shadow gates shipped in S-4 Phase 3 ride the funding input."

**Neither gate rides this input.** They read a different vendor through a
different client:

- `check_funding_rate_fade()` — `crypto_setups.py:127` does
  `from integrations.binance_futures import get_funding_rate`. **Binance**, not
  Coinalyze. That client has no `degraded` flag, no vendor-health tracking, and
  no sanity bounds.
- The Tier-3 negative-funding-fade LONG block — `crypto_gates.py:117-123` keys
  on `strategy` + `direction` + `tier` only. It never reads a funding value.

The `degraded` flag is a **Coinalyze-path artifact** (`coinalyze_client` →
`crypto_market.py:716`) that exists only on the `/api/crypto/state/{symbol}`
read surface. The DEF-FEED-TRIAGE D1 contract governs that endpoint. It does not
reach either shadow gate.

Per the brief's own instruction — "the brief is wrong, not the codebase" — this
is recorded as a brief defect, not worked around.

## Contradiction 2 — the denominator is zero, not thinned

The brief's concern was a *silently reduced* shadow-gate denominator. Measured:

- `signals` where `strategy = 'Funding_Rate_Fade'`: **0 rows. Ever.**
  (`strategy ILIKE '%funding%'` is also 0.)
- `crypto_gate_shadow` where `strategy = 'Funding_Rate_Fade'`: **0 rows**
  (of 140 total).
- `crypto_gate_shadow` has 18 columns, **none** carrying funding rate or
  degraded state, and **no JSONB column** for it to hide in. So the brief's
  load-bearing question — "does the shadow log record funding state at
  evaluation time?" — answers **no**, categorically.

There are no shadow-gate observations to correct. The floor-raise gate is worse
still: in the delta zone it only emits a **log line**, never a DB row, so its
hits are unmeasurable by construction regardless of any of the above.

## Contradiction 3 — D1 changed the consequence, not the rate

Phase 1.3 asked for a pre/post-`2eb079d` duty-cycle comparison. Moot: the diff
shows the degraded expression was **character-identical before and after**,
merely hoisted from an inline argument into a named variable. D1 added the
`FIRING → NEUTRAL` suppression (the consequence). The computation was untouched.

The `*100` unit fix in the same commit did theoretically move a bounds
boundary, but empirically that path never fired — `crypto_vendor_health_audit`
has zero non-LIVE funding rows across the whole window.

---

## 3. LIVE DEFECT FOUND — funding reports degraded on healthy data

Not what the brief went looking for, and more actionable than what it did.

**Root cause.** `_finalize_result()` in `backend/bias_filters/coinalyze_client.py`
caches the result *before* attaching `health_status`:

```python
_set_cache(cache_key, result)              # line 119 — cached WITHOUT health_status
return {**result, "health_status": status} # line 120 — attached only to THIS return
```

On any cache hit inside the 300s TTL, `_get_cached()` (line 213) returns the
bare cached dict. `funding_data.get("health_status")` is then `None`, and
`None != "LIVE"` is `True`, so `degraded=True` on perfectly healthy data.

**Asymmetry — funding is the only field exposed.** It is the sole consumer using
a bare `.get("health_status")`. OI (`crypto_market.py:740`) and basis (`:753`)
both use `.get("health_status", "LIVE")` with a default and are immune.

**Empirical confirmation, production, 2026-07-21 ~21:18 UTC (15:18 MDT)** —
three consecutive `GET /api/crypto/state/BTC` calls:

| Call | Cache | `funding.degraded` | `rate_pct` | OI / basis |
|---|---|---|---|---|
| 1 | miss (fresh fetch) | **false** | 0.0013 | false / false |
| 2 | hit | **true** | 0.0013 | false / false |
| 3 | hit | **true** | 0.0013 | false / false |

The rate is **identical** across all three. Vendor health is unchanged and
`crypto_vendor_health_audit` shows unbroken `LIVE`. The flag flips purely on
cache state, and OI/basis stay clean throughout — precisely as the missing
default predicts.

**Consequence, and why this matters beyond cosmetics.** With a 300s TTL against
an endpoint polled far more often than every five minutes, the large majority of
reads report `degraded=true`. D1.4 then correctly suppresses `FIRING → NEUTRAL`
on a degraded input — so **a correct contract is being driven by a false input,
and genuine funding signals are being suppressed on the read surface most of the
time.** The `/api/crypto/state/{symbol}` funding block is consumed by the
committee and the Discord notifier, both of which currently hide the funding
line whenever this fires.

**Not fixed here.** This brief is read-only and the fix deserves its own brief
and sign-off. The one-line shape would be caching the health-attached dict (or
defaulting to `"LIVE"` as OI and basis already do), plus a regression test that
asserts two consecutive calls return the same `degraded` value.

---

## 4. Forward-persistence proposal (the substitute deliverable)

**Smallest change that makes the duty cycle measurable going forward.** Fix the
cache defect *first* — persisting the flag as it stands would durably record a
cache artifact and manufacture a fake ~80–90% duty cycle, which is worse than
having no data. Once the flag is trustworthy, the minimal change is to extend
the existing `crypto_vendor_health.record_observation()` call — already invoked
on every funding fetch at `coinalyze_client.py:115`, already carrying symbol,
value validity and reason — from **transition-only** writes to a lightweight
per-observation row (or a counter bucketed per symbol per hour, if row volume is
a concern). That reuses a live code path, adds no new vendor call, needs one
append-only table or one added column, and is the only place where all three
OR-terms of the flag are simultaneously in scope. Two-week collection would then
give a real per-symbol duty cycle with a clustered-vs-uniform read.

**Do not** instrument the shadow gates for this. They read Binance and never see
this flag (Contradiction 1); wiring it in would create the coupling the brief
mistakenly assumed already exists.

---

## 5. Recommendation

**One line, as the brief requests:** the two S-4 Phase 3 shadow gates cannot be
decided on current evidence — not because the sample is thin, but because it is
**empty** (zero `Funding_Rate_Fade` signals ever emitted), and the funding-input
concern that motivated this brief does not apply to them at all.

The flip decision remains Nick's and the committee's. The actionable item to
come out of Phase 0 is **the cache defect in section 3**, which is live, has a
real consumer-visible consequence, and is a small, config-free, recoverable fix.

**Recommended next step, for authoring not action:** a micro-brief for the
`coinalyze_client` cache fix. Separately, the zero-signal fact for
`Funding_Rate_Fade` deserves its own question — a strategy that has never fired
once is either mis-gated or unreachable, and that is a larger finding than the
duty cycle this brief set out to measure.
