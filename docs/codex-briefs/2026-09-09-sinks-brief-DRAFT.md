# CC BRIEF — SINKS: persist the two discarded feeds, and stop losing NBBO

**Authority** R-IV.326(a). **Position two**, behind the grader precondition build and ahead
of ledger integrity (R-IV.273(d)).

**Status: DRAFT. Titans pass follows the ledger brief's. NO CODE until it returns.**

**Author** CC-BUILD, drafted 2026-09-08 evening for the 09-09 frozen day.

---

## What this fixes, in one line

**Two UW feeds are fetched, used, and thrown away** — `market_tide` and `darkpool` — at
roughly **15,246 metered calls over 54 days, 2.7% of all UW spend, for data persisting
nowhere** (k/burn artifact `4557c775`). They are also **exactly the two missing triad legs.**

## THE FINDING THAT CHANGES THIS BRIEF'S URGENCY

**The dark-pool payload already carries NBBO per print, and the code already reads it.**

```
backend/signals/darkpool_enrichment.py:191-192
    nbbo_ask = float(p.get("nbbo_ask") or 0)
    nbbo_bid = float(p.get("nbbo_bid") or 0)
```

The enricher computes a spread-relative dead band from those two fields, classifies each
print buy/sell/mid, tracks a `spreads` list for `SPREAD_FRACTION_K` calibration, buckets
`no_nbbo_premium` separately — **and then returns aggregates and discards every per-print
NBBO it just used.**

**Collector design law item 6 (R-IV.303(d)) says the sinks must store the underlying's
bid/ask at print time, and that it is THE ONE ITEM THAT CANNOT BE RETROFITTED.** It is
correct that it cannot be retrofitted. **What is new is that it does not need to be
fetched** — it is arriving right now, on every print, and being dropped.

**So the cost of delay is not "we will need a harder build later." It is that every cycle
between now and the sink loses NBBO permanently**, and the pollers were un-paused on
2026-09-08, so the loss is running.

**Seventh member of the compute-then-discard family**, and the most expensive: the others
discarded a number that could be recomputed. **This one discards a market state that existed
for an instant.**

---

## Binding conditions

- **Broker exports are never committed.** The repo is PUBLIC.
- **No manual SQL against prod.** Migrations are code, reviewed, reversible, and carry
  `-- DOWN` (AEGIS hygiene).
- **Backfill draws are AEGIS-sized BEFORE any draw** (R-IV.303, the 2026-07-17
  watchdog-shed precedent). A per-ticker dark-pool backfill across the universe is a large
  draw; it does not start on this brief's say-so.
- **The sinks add persistence ALONGSIDE the live path** (R-IV.321(a)). The Regime panel's
  flow read and the `options_flow` / `darkpool` composite factors are LIVE consumers —
  the 09-05→09-08 pause proved it by breaking them. **Nothing in this build may change what
  a live consumer receives.**
- **The secret stays on the register.** Not named in any artifact this build produces.

## Phase 0 — already largely done, and cited rather than repeated

| input | artifact | what it settles |
|---|---|---|
| Moby Dick census | `docs/edge/results/2026-09-06-moby-dick-census-phase0.md` (`3bbddd58`) | tide and dark pool: fetch exists, **0 persisted rows**, Redis TTL 60 s / 300 s; backfill "not supported by the hub client" |
| first market read | `docs/edge/results/2026-09-06-triton-first-market-read.md` (`5f3da161`) | the explore population and its labels |
| second market read | `docs/edge/results/2026-09-07-triton-second-market-read-core4.md` (`ef52c6f7`) | H-CORE4's weekly series; regime beta |
| third market read | `docs/edge/results/2026-09-07-triton-third-market-read-tape.md` (`8d1f4e92`) | the week is the unit; **every excess figure is before-friction** |

**The third read is why this build exists in its current form.** *"No underlying quote
exists at print time anywhere, so every excess figure in all three reads is before-friction
and no retrospective query can fix that."* **Only signals collected after the NBBO sink
lands can be measured net of cost.**

### P0.1 — dark-pool backfill support: MEASURED IN THIS BUILD, not assumed

**R-IV.276 resolved backfill support for TIDE ONLY** (the MCP tool description lists
`market_tide` with *date optional, interval_5m optional*). **It says nothing about
`/api/darkpool/{TICKER}`, and the two endpoints are not the same shape** — one is a
market-wide time series, the other a per-ticker print list.

**Leg (d) is measured live in this build, in the same pass as tide's confirmation**
(CC-QUERY's flag, carried in the held queue). **A single confirmation covering both is not
acceptable:** *backfillable* versus *forward-only* is exactly what the Hunter would be
claiming about its own history.

**And there is a second dark-pool endpoint the census did not name.** `get_darkpool_recent()`
(`uw_api.py:927`, `/api/darkpool/recent`, caller `darkpool_recent`) is **market-wide**, not
per-ticker. **Its backfill support is a third open question**, and it may be the cheaper
draw if it supports a date — one call per interval instead of one per ticker per interval.

---

## Tasks

### S1 — `darkpool_prints` (per-print, per-ticker)

One row per print. **`nbbo_bid` and `nbbo_ask` are NOT optional columns** — they are the
reason this table exists ahead of the ledger build.

Minimum shape, to be settled at the Titans pass:

```
ticker · executed_at · price · size · premium · nbbo_bid · nbbo_ask
canceled flag · market_center if present · ingested_at · provider
```

**`provider` from day one**, per the lesson filed on `DEF-UW-OHLC-DEAD` this week: a column
added later leaves every earlier row `NULL`, and `NULL` then means both *"before provenance
existed"* and *"unknown"*. **The invariant to carry across from that build:
`provider IS NULL` must mean exactly one thing, declared here before the first row.**

**Key uniqueness is a registered predicate** (verification-laws §1.2): state
`(rows, distinct_keys)` before any key is used as a join key. UW prints have no id in the
enricher's read path — **the candidate key is composite and must be measured, not assumed.**

### S2 — `market_tide_history` (per-snapshot, including 5-minute)

One row per tide snapshot. The warmer currently writes **one Redis key with a 1800 s TTL**
and overwrites it (`stable_jobs.py::_warm_tide`), so **the series has never existed.**

Per the census: `net_call_premium`, `net_put_premium`, `net_volume`, plus the snapshot
timestamp — and **the 5-minute interval the MCP description exposes**, which is what S6's
tide-sign stratum needs.

### S3 — the writers reuse the pollers' PARSED payloads

**No second fetch.** The tide warmer and the WH-ACCUMULATION scan already parse what the
sinks need; the writer takes the parsed object.

**This is a constraint, not an optimisation.** A separate fetch would (a) double the metered
spend the k/burn artifact measured, and (b) **persist a different observation from the one
the live consumer acted on** — which would make the sink's history disagree with the
decisions taken from it, silently.

### S4 — Backfill, gated

**Tide:** supported per the MCP description, **confirmed live in this build** before any
draw. Backfill to the window's start where the endpoint allows.

**Dark pool:** **OPEN** — measured in this build (P0.1). **If backfillable, AEGIS sizes it
before any draw**, because per-ticker across the universe is a large call count. **If not,
(d) is forward-only and no backfill exists at any price** — which changes what the Hunter
can claim about its own history and must be stated on the registration face, not discovered.

### S5 — NBBO at print time

**Store `nbbo_bid` and `nbbo_ask` as they arrive, per print, unmodified.**

**Not a derived spread, not a bucket, not a classification.** The enricher already derives
all three and they are all reconstructible from the pair; **the pair is not reconstructible
from them.** Store the inputs.

**Explicitly in scope: the `no_nbbo` case.** A print arriving with missing or zero NBBO is
stored **with its NBBO null and a flag**, never dropped and never defaulted — the enricher
already refuses to force those directional, and the sink must not undo that refusal by
storing a zero.

### S6 — the dark-pool enricher's `enrichment_data` write

The enricher returns a dict that `process_signal_unified` folds into the signal.
**`enrichment_data` is a JSONB column on `signals`** (read at `api/dev_shadow.py:42`,
`api/committee_bridge.py:59`, written at `api/signals.py:96`).

**What the enricher computes and returns must land in `enrichment_data` on the signal row**,
so a signal's dark-pool context is recoverable from the signal rather than only from a live
re-fetch that no longer returns the same window.

**This is the smallest task and the one most likely to be dropped**, because the aggregate
"works" today — it reaches the committee live. **It is in scope because a decision surface
that cannot be reconstructed cannot be graded**, which is the same argument the grader build
just finished making.

---

## Done definition

- **D1** — tests green; deploy verified four-step with the poll sequence reported.
- **D2** — **NBBO present on stored prints, measured**: a count of stored prints and the
  count carrying a non-null pair, both stated, on a real session's data.
- **D3** — the tide series has **more than one row for a single day** — the thing a
  1800 s overwriting key could never produce.
- **D4** — **no change to any live consumer's payload**, demonstrated: the Regime panel's
  flow read and the two composite factors return what they returned before.
- **D5** — dark-pool backfill support **stated as measured**, either way, with the call
  made and its response recorded.
- **D6** — key uniqueness registered: `(rows, distinct_keys)` on the print key, before use.
- **D7** — `provider` populated on every row from the first, and the `NULL` meaning declared.
- **D8** — migrations carry `-- DOWN`.

## Gates / what NOT to do

- **NO second fetch** for the sink (S3).
- **NO backfill draw before AEGIS sizing** (S4).
- **NO storing a derived spread in place of the NBBO pair** (S5).
- **NO defaulting a missing NBBO to zero** — it has a bucket already.
- **NO change to live consumer payloads** — the pause proved they are live.
- **NO deferring the NBBO columns to "phase two."** Every cycle without them loses data
  that cannot be recovered, which is the one property that distinguishes this build from
  every other item in the register.

## Open questions for the review

**Q1 — is `/api/darkpool/recent` (market-wide) the cheaper backfill?** If it accepts a date
it is one call per interval instead of one per ticker per interval. **Unmeasured; named
because the census did not cover it.**

**Q2 — what is the print key?** UW prints carry no id in the path the enricher reads. If the
composite key is not unique, dedupe on replay is undefined. **Measure before designing the
table, per §1.2.**

**Q3 — does the tide sink's 5-minute interval need its own row, or is the snapshot cadence
enough?** Amendment 1's S6 defines tide sign as *"the net premium sign of the 5-minute
market-tide bar containing `fired_at`"* — **so the answer is fixed by the registration, not
by convenience: 5-minute bars, or S6 cannot be computed as declared.**
