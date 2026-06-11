# Phase 0 — Faked-Fresh Bias Factors (tick_breadth / breadth_intraday)

**Authored:** 2026-06-11 · **Mode:** investigation-only, read-only. No code changes.
**Class:** data-integrity / confident-stale (same family as the dead-ADX default-25). A factor
whose underlying feed died **2026-06-10 20:00Z** is still scored into the composite as if fresh.
**Independent of the webhook flip** — this is a scoring-correctness bug.

## TL;DR

The composite **does** have a staleness gate (`compute_composite`, [composite.py:753-766]) keyed
on `reading.timestamp` vs each factor's `staleness_hours` (tick/breadth = 4h). The bug: **the
timestamp is the only freshness anchor, and it gets re-stamped to "now" by a recompute on stale
cached data** — so a dead feed sails through the gate. The fail-loud signal that should catch this
(`timestamp_source == "fallback"`) is computed and recorded but **never acted on**.

## Evidence (2026-06-11, ~6h into the session, no live feed since prior close)

| Key | timestamp | data age | source | metadata |
|-----|-----------|----------|--------|----------|
| `tick:current` | `2026-06-10T20:00:32Z` | yesterday's close | webhook | — |
| `breadth:uvol_dvol:current` | `2026-06-10T20:00:05Z` | yesterday's close | webhook | — |
| `bias:factor:breadth_intraday:latest` | `2026-06-10T20:00:05Z` | correct (stale) | tradingview | `timestamp_source=updated_at` |
| `bias:factor:tick_breadth:latest` | **`2026-06-11T13:35:21Z`** (today) | **stale data, fresh stamp** | tradingview | **`{}` (empty)** |

`tick_breadth:latest` carries **today's** timestamp on **yesterday's** values
(`tick_high 765 / tick_low -1104 / tick_avg -147.81` — byte-identical to the 06-10 20:00 cache),
with `raw_data.data.source="pandora_api"` and **empty metadata**. That is the faked-fresh reading.

## Where the staleness guard fails

### The gate (works as designed, but is blind)
`compute_composite()` [composite.py:753-766]:
```python
timestamp_source = (reading.metadata or {}).get("timestamp_source")
if timestamp_source == "fallback":
    unverifiable_factors.append(factor_id)        # ← recorded …
max_age = timedelta(hours=FACTOR_CONFIG[factor_id]["staleness_hours"])
reading_ts = _utc_naive(reading.timestamp)
if (now - reading_ts) <= max_age:
    active[factor_id] = reading                   # ← … but still scored at full weight
else:
    stale_set.add(factor_id)
```
The gate trusts `reading.timestamp`. A fresh stamp ⇒ ACTIVE ⇒ full weight. **`unverifiable_factors`
is appended but never excludes the factor** — the fail-loud flag is dropped on the floor.

### Hole 1 — recompute re-stamps stale data (the observed offender)
An **external writer** (tagged `pandora_api`, empty metadata — **not present in the Railway backend**;
`grep -r pandora_api backend` = 0 matches → almost certainly the VPS pivot-collector) re-reads the
cached tick values and writes a `tick_breadth` FactorReading **stamped at rescore time**, not at the
source data's age. With no `timestamp_source` in metadata, the gate can't even flag it. → fresh
stamp on a 17-hour-old feed.

### Hole 2 — backend utcnow fallback (latent, same class)
`tick_breadth.compute_tick_score` [tick_breadth.py:448-453] extracts the source timestamp from the
payload's `updated_at`, but **falls back to `datetime.utcnow()`** when absent, only logging a warning:
```python
source_timestamp, timestamp_source = _extract_source_timestamp(tick_data)
if timestamp_source == "fallback":
    logger.warning("No source timestamp for tick_breadth; using utcnow fallback ...")
```
This stamps stale data "now" and sets `timestamp_source="fallback"` — which the composite records
but ignores (above). So even the in-backend path can fake-fresh; it's only saved today because the
offending reading came from the external writer.

### Why breadth looks OK (today) — and isn't safe
`breadth_intraday:latest` kept the real `updated_at` (`timestamp_source=updated_at`) → its 22h age
exceeds 4h → it IS correctly dropped as stale. So breadth currently fails **safe**. But it shares
the identical contract: the moment any recompute path re-stamps it (as the VPS does for tick), it
fakes fresh too. The bug is the **contract**, not one factor.

## Root cause (one sentence)

The composite treats `reading.timestamp` as proof of data freshness, but nothing guarantees the
timestamp reflects the **source data's** age rather than the **rescore** time — and the one signal
that would expose a non-authentic timestamp (`timestamp_source`) is captured and then ignored.

## Fail-loud fix (recommended; not implemented here)

1. **Act on the unverifiable flag.** In `compute_composite`, a reading with
   `timestamp_source == "fallback"` **or missing/empty `timestamp_source`** must be treated as
   unverifiable → excluded from `active` (added to `stale_set`), not scored. Fail-closed, not advisory.
2. **Require a trustworthy timestamp_source in the reading contract.** Every `FactorReading` must
   carry `metadata.timestamp_source ∈ {updated_at, timestamp, received_at}`. Empty/unknown ⇒ the
   factor is labeled `stale/unknown`, surfaced in the composite's stale report, and excluded.
3. **Recompute must preserve source age.** Any rescorer that reads cached data (the backend factor
   re-score loop **and** the external `pandora_api`/VPS writer) must set `reading.timestamp` to the
   cached datum's `updated_at`, never to rescore-time. Re-scoring stale data must yield a stale-stamped
   (and therefore gate-droppable) reading.
4. **Scorer-side stale gate (defense in depth).** `compute_tick_score` / breadth `compute_score`
   should compare the source `updated_at` to the factor's `staleness_hours` and emit `None`
   (or an explicit `signal="STALE"`, `score=None`) instead of a confident score on dead data —
   mirroring the "return None when unavailable, never 0.0" factor rule.
5. **Surface it.** When a factor is dropped as stale/unverifiable, log loudly and reflect it in the
   composite confidence (`active_count` already drives HIGH/MEDIUM/LOW) so a quietly-shrinking active
   set is visible, not silent.

## Blast radius

`tick_breadth` weight 0.06, `breadth_intraday` weight 0.03 (intraday tier). A faked-fresh tick factor
injects a stale −0.2…−0.7 breadth read into every composite recompute at full weight, and inflates
`active_count` (→ overstated composite **confidence**). Not catastrophic alone, but it is a silent
wrong-data path feeding the directional bias the whole committee reads.

## Scope notes
- Read-only Phase 0. No fix applied. The fix touches `bias_engine/composite.py` and the factor
  scorers — **scoring-engine territory**; coordinate with that session before implementing.
- The external `pandora_api` writer is almost certainly VPS-side (`pivot-collector`) — confirm on the
  VPS and align it to the same timestamp contract as part of the fix.
