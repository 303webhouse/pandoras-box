# DEF-BIAS-`coverage_ratio`ERAGE-OMITS-ABSENT · P1

**Registered** 2026-09-08 by R-IV.321(c). **Confirmed live the same day.** **Status:** OPEN.
**P1: the composite's self-monitor is a null verifier.**
**Census of record:** `docs/edge/results/2026-09-08-regime-factor-census.md`

---

## The defect

`coverage_ratio` reports the fraction of factor weight that is `active_weight_sum`. **A factor that is
present, fresh and scored `0.0` counts as active** — so a dead factor rendered as neutral
(`DEF-BIAS-NULL-AS-NEUTRAL`) **raises coverage rather than lowering it.**

**The metric cannot fall for the failure it exists to detect.**

> ## CORRECTION 2 — 2026-09-09: the live instance is `gex`, and it is a RATE not a count
>
> **`dxy_trend` is withdrawn as an instance** (CC-QUERY, `docs/edge/results/2026-09-09-band-vs-dead-factor-discrimination.md` — it is a band). **The live
> mis-count is `gex`, 35 of its 695 readings.**
>
> **That changes the defect's arithmetic in a way worth stating: it is INTERMITTENT.**
> `gex` is not permanently dead — it carries real values 95% of the time and fabricates
> 5%. **So coverage is not steadily overstated by one factor's weight; it is overstated
> only on the 5% of cycles where `gex` has no input**, and a single reading of
> `coverage_ratio` cannot tell you which kind of cycle you are in.
>
> **That is harder to catch than a permanently dead factor, not easier.** A factor that is
> always wrong shows up in any sample; one that is wrong 5% of the time shows up in none.

> ## CORRECTION — 2026-09-08 evening: the LIVE instance is 1 of 18, not 4
>
> **The measurement cited below said four of eighteen "covered" factors were dead. Three of
> those were genuinely covered** — their 0.0 is a designed scoring band, not a fabrication
> (see `DEF-BIAS-NULL-AS-NEUTRAL`'s correction). **The live figure is one: `dxy_trend`.**
>
> **THE DEFECT STANDS UNCHANGED, and the correction sharpens rather than weakens it.**
> Coverage counted a fabricated 0.0 as covered — that is demonstrated, once. **And the
> demonstration is now cleaner: one factor confirmed dead by an independent source
> (`factor_history`, 0 rows since 07-23) is counted at full weight toward 0.94.**
>
> **The structural half is untouched:** a metric that cannot fall when a factor dies is a
> null verifier whether it is currently mis-counting one factor or four.

## Measured 2026-09-08 15:04 ET

```
reported   active 18 of 20   coverage_ratio 0.94   excluded ["excess_cape", "savita"]
actual     14 of 20 carrying a measured value
           4 counted as covered while contributing 0.0 without measuring anything
```

**0.94 while four of the eighteen are dead.** Every test coverage applies is satisfied by a
null rendered as 0.0: present, not stale, in range.

## Why this is the null-verifier law and not merely an inaccuracy

`coverage_ratio` was surfaced under R-IV.47(d) **precisely to stop
`active_weight_sum` being computed and discarded** — the compute-then-discard family's first fix. It
became visible, and **the visible number cannot report the thing it was surfaced to
report.**

**A monitor that only moves when something else already told you is not a monitor.** It
would have to fall when a factor dies; it rises.

## The second half, from the ruling

**Factors missing from the ROSTER are not counted as excluded at all.** `excluded_factors` is computed
over `FACTOR_CONFIG`, so the roster defines the universe — **and the roster is the thing
that could be incomplete.** Weights are normalised to sum to 1.00 across whatever is in it,
so **dropping a factor from the roster leaves coverage reading 1.00 with one fewer input.**

**Measured today the roster is complete** — 18 active + 2 excluded = 20 = `FACTOR_CONFIG`. **The
defect is structural, not currently realised**, and it is registered because the metric
would be silent if it were.

## Fix shape — not chosen here

**Coverage counts MEASURED factors, not present ones**, and a null-scored factor is
excluded and named. **Ships with `DEF-BIAS-NULL-AS-NEUTRAL`**; either alone leaves the pair intact.

**And the roster needs a source outside itself** — an expected-factor list the config is
checked against, so absence from the config is detectable. Without it, this half of the
defect is unfixable by construction: **a set cannot notice what was never in it.**

---

## FACET — THE RULED FIX IS UNVERIFIABLE HISTORICALLY (R-IV.350(b))

**Registered 2026-09-10. Found while answering R-IV.348(a); not asserted as a cause.**

**`coverage_ratio` and `excluded_factors` are NEVER PERSISTED.** Both are computed in
`compute_composite()` (`bias_engine/composite.py:929, 932`), placed on the `CompositeResult`,
served live at `api/bias.py:654`, cached in Redis — **and dropped at the database boundary.**

`bias_composite_history` writes exactly nine columns (`database/postgres_client.py:459-471`):

```
composite_score  bias_level  bias_numeric  active_factors  stale_factors
velocity_multiplier  override  confidence  factor_scores
```

**Neither is among them.**

### Why this is a facet of THIS defect and not a separate one

**The ruled fix is exclusion PLUS counting** — a null-scored factor is excluded and the
coverage figure falls to say so. **`coverage_ratio` IS the counting half.** It is not stored,
**so the counting half cannot be shown to have worked on any historical window** — only
inferred from `active_factors` / `stale_factors`, which is the exclusion half restated.

**A fix whose effect is computed and discarded cannot be verified after the fact**, and this
register's standing objection to compute-then-discard is exactly that. **Tenth instance.**

### The remedy travels with the sinks brief

**Persist per cycle: `coverage_ratio`, `active_factors`, `stale_factors`.** Two of the three
are already columns; **`coverage_ratio` is the one that is not.** Filed as an addition to the
sinks brief's canonicalization item — **schema change, not a new writer.**

## KNOWN LIMITATION — A FAILED REDIS DELETE LEAVES gex STALE-BUT-ACTIVE FOR UP TO 4 h (R-IV.350(c))

**On the face, not fixed now.**

The exclusion depends on a Redis DELETE that sits inside a `try/except` which **logs and
continues** (`bias_engine/factor_scorer.py:96-99`):

```python
except Exception as del_exc:
    logger.warning("Failed to clear stale key for %s: %s", factor_id, del_exc)
```

**That is the warning line to grep.** If it fires, the previous `gex` key survives, and
`compute_composite()` will keep counting it as **active** until it ages past
`FACTOR_CONFIG["gex"]["staleness_hours"] = 4` — **up to four hours of a fabricated reading
still inside the composite, after the fix.**

**Note which bound applies:** the Redis TTL is
`max(REDIS_FACTOR_LATEST_TTL 86400, 4 × 3600) = 86400 s`, but **TTL is not what gates
`active` — the 4-hour staleness window is** (`composite.py:769-775`). The key outlives its
usefulness by 20 h; the damage window is 4 h.

**Consequence for any read:** **a `gex` still in `active_factors` does NOT falsify the fix**
without first checking whether that warning line fired in the same interval.

**Not fixed now, and the reason is stated:** making the delete authoritative means either
failing the scoring pass on a delete error or writing an explicit tombstone, and **both change
what a no-data cycle means** — which is a decision for the ruling that owns the exclusion, not
a quiet hardening.
