# CC BRIEF — SINKS: persist the two discarded feeds, and stop losing NBBO

> **REVISION 2 — R-IV.376.** Amends ATLAS PASS 1 (F1–F9) and AEGIS A2.
> **BASE: gate `8d6f4e3f`, LF-normalised, 13,660 B** — the version carrying S7 and S9.
>
> **GATE DISCREPANCY, stated rather than absorbed.** The review names `4cad9aa8`.
> **No version in this lane's tree hashes to it** — the three committed versions are
> `638863f1` (original), `9adbad19` (+S7), `8d6f4e3f` (+S9), and raw == LF for all three
> (this file has no CRLF, so line endings cannot explain the difference). No copy exists
> in the ferry directory.
> **Every finding maps cleanly onto `8d6f4e3f`** — F9 cites S9, which exists only there —
> **so this revision is built on `8d6f4e3f` and says so.** If EDGE holds a `4cad9aa8` the
> two need reconciling before the final read; the amendments below are unaffected either
> way, but the gate arithmetic is not.

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

## THE BUILD SPLITS IN TWO (F2, A2) — and the split is a sequencing constraint

**SINKS-A and SINKS-B ship separately. B cannot start before the quota layer enforces.**

| | contents | new UW fetches | gate to start |
|---|---|---|---|
| **SINKS-A** | S1 · S2 (writer) · S5 · S6 · S7 · S9 — **the live writers** | **ZERO** | none. Codes this weekend after the ledger carve-out. |
| **SINKS-B** | S4 — log ingest, then sized vendor gap draws | **yes** | **governor ENFORCING with the corrected denominator, `/health` showing account usage, and the transfer verified** |

**Why the split is not optional.** SINKS-A reuses payloads the pollers already hold (S3)
and issues no request at all, so it cannot touch the budget. **SINKS-B draws from the
vendor — and a draw against an unmetered account is precisely the outage just diagnosed.**
`uw_forward_logger` exhausted 40,000 requests/day and took the GEX factor dark for
10 h 28 m; **a per-ticker backfill sweep is the same shape of spend, run deliberately.**

**So the order is: quota layer → SINKS-A → transfer verified → SINKS-B**, and SINKS-B is
**AEGIS-sized against `40,000 − measured hub demand`**, not against 40,000, and
**scheduled after the 20:00 ET reset** so a miscalculation costs the quiet overnight
window rather than the next session's panels.

**The measured remainder does not exist yet.** It arrives with the meter (`/health`
account usage) and the post-stop convergence read. **SINKS-B has no start date until that
number does.**

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

**FIXED BY THE REGISTRATION (F8): 5-MINUTE BARS, NOT SNAPSHOTS.** Amendment 1's S6 defines
tide sign as *"the net premium sign of the 5-minute market-tide bar containing
`fired_at`"* — **so a snapshot cadence cannot compute it**, however convenient. One row per
5-minute bar, **stored from the response the poller already receives** (S3: no second
fetch), **deduped on the BAR timestamp** rather than on arrival time.

Per the census: `net_call_premium`, `net_put_premium`, `net_volume`, plus the **bar**
timestamp.

**Dedupe on the bar, not the fetch, is the load-bearing detail.** The warmer polls more
often than 5 minutes, so the same bar arrives repeatedly; **keying on arrival would store
the same bar many times and make a count of rows meaningless as a count of bars.**

### S3 — the writers reuse the pollers' PARSED payloads

**No second fetch.** The tide warmer and the WH-ACCUMULATION scan already parse what the
sinks need; the writer takes the parsed object.

**This is a constraint, not an optimisation.** A separate fetch would (a) double the metered
spend the k/burn artifact measured, and (b) **persist a different observation from the one
the live consumer acted on** — which would make the sink's history disagree with the
decisions taken from it, silently.

### S4 — Backfill (SINKS-B) — THE SOURCE HAS CHANGED (F1)

**The dark-pool backfill is no longer a vendor draw. It is an INGEST OF OUR OWN LOGS.**

`uw_forward_logger` has written per-ticker Parquet since ~mid-August — `darkpool`,
`flow_alerts`, `net_prem_ticks`, `spot_exposures` — under
`/opt/openclaw/workspace/data/cache/uw/<type>/<TICKER>/<YYYYMM>.parquet`, merge-and-append
with `drop_duplicates`. **The data this brief was going to buy from the vendor is already
on disk, collected by the very process that exhausted the quota collecting it.**

- **provider = `'uw_forward_logger'`** on every ingested row. Not `'uw'`: these arrived
  through a different client, on a different host, with a different retry and backoff.
  **Same vendor is not same provenance**, and S1's `provider` invariant is what makes that
  recordable.
- **The vendor is drawn ONLY for gaps**, only after the ingest establishes what the gaps
  are, and only if P0.1's measurement supports it.
- **Ingest runs under the T5b discipline**: expected counts declared before the write,
  invariants asserted before and after, seal-equivalent on any table it touches.

**The window is bounded by what was copied, not by what was collected.** Coverage starts
at the earliest `YYYYMM` present in the transfer and **ends when the logger stopped** —
both dates are facts about the archive, and **both must be read off the copy rather than
assumed from the deploy date.**

**TIDE IS DIFFERENT AND STAYS A VENDOR DRAW.** The logger holds **per-ticker net-premium
ticks, not the market-wide series**, so it cannot supply `market_tide_history`. That
backfill comes from the vendor's `date` + `interval_5m` parameters — **~78 bars/day**,
which is small enough that AEGIS sizing is a formality rather than a constraint. **Stated
so nobody reaches for the logger's `net_prem_ticks` and gets a different quantity with a
similar name.**

**If the transfer is incomplete, the ingest window shrinks and no draw replaces it** — the
logger's archive is the only copy, and the box retires. **That is the risk the transfer
plan's verification step exists to bound.**

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

**THE WRITE MERGES, IT DOES NOT REPLACE (F5).** `enrichment_data` already holds keys from
other enrichment paths. **A whole-column write destroys them silently** — the signal still
has an `enrichment_data`, it is still valid JSONB, and what is missing is only visible to
someone who knew it was there.

```sql
-- merge, preserving existing keys
UPDATE signals SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || $2::jsonb
WHERE id = $1
```

**Not `SET enrichment_data = $2`.** The `||` operator is the whole fix, and the test is a
signal that carries another path's key before the dark-pool write and still carries it
after.

**This is the smallest task and the one most likely to be dropped**, because the aggregate
"works" today — it reaches the committee live. **It is in scope because a decision surface
that cannot be reconstructed cannot be graded**, which is the same argument the grader build
just finished making.

---

### S7 — persist the composite's coverage figures (R-IV.350(b))

**Added by R-IV.350(b). Schema change, not a new writer.**

**`bias_composite_history` must carry `coverage_ratio` per cycle.** `active_factors` and
`stale_factors` are already columns; **`coverage_ratio` is computed at
`bias_engine/composite.py:929` and discarded at the DB boundary.**

**Why it belongs in THIS brief:** the brief's subject is sinks that compute and discard. This
is the same shape one layer up — **a figure the engine produces every cycle, serves live, and
never writes down** — and its absence makes `DEF-BIAS-COVERAGE-OMITS-ABSENT`'s ruled fix
unverifiable on any historical window.

- **add** `coverage_ratio DOUBLE PRECISION` to `bias_composite_history` (nullable: rows before
  the migration genuinely do not have it, and **a backfilled default would fabricate the exact
  quantity this defect is about**);
- **write it** in `log_composite()` alongside the nine existing columns;
- **do NOT backfill.** The value cannot be reconstructed from stored columns —
  `active_factors` gives the membership but the weights live in `FACTOR_CONFIG`, which has
  changed. **A recomputed historical coverage would be a derived value witnessing its own
  input** (conventions #14).

**Done when:** a cycle's served `coverage_ratio` and its stored value agree on a live read.

### S9 — `observation_date` on factor readings (R-IV.364(d))

**Same shape as S7, one table over: a field the engine HAS and does not write down.**

`factor_readings.timestamp` is the WRITE time. For a factor built from a market series the
observation may be a different day — the batch runs 96×/24 h with no market-hours gate, so
weekend and holiday rows carry the prior session's values under a current stamp.

- **add** `observation_date DATE` to `factor_readings`, nullable;
- **`observation_date` IS THE INPUT'S EXCHANGE DATE (F9), never the fetch time.** For a
  bar-sourced factor it is the bar's session date. **For a non-bar input it is the release
  date if the source states one, and `NULL` if it does not** — `NULL` meaning *"the source
  did not say"*, which is a different fact from *"we did not look"* and must not be
  conflated with it;
- **source it from the input's own as-of.** `get_latest_price()` currently discards that at
  `factor_utils.py:453` (`iloc[-1]` on a 5-day frame) — **the date exists in the frame and is
  thrown away one line before it is needed**, which is what makes this cheap;
- **do NOT backfill.** The as-of of a past reading is not recoverable from the row, and
  inferring it from the stamp is the assumption the column exists to remove.

**Done when:** a reading written on a Saturday reports the preceding Friday as its
`observation_date`, and a reading written intraday reports that day.

### S10 — THE WRITERS RUN AFTER THE LIVE RETURN (F6) — a mechanism, not a check

**D4 says "no change to any live consumer's payload." That is a CHECK. F6 asks for the
property that makes the check unnecessary.**

**Every sink writer runs in a background task scheduled AFTER the live payload has been
returned to its consumer.** Not before, not inline, not in a `finally`.

```python
result = build_live_payload(...)      # what the consumer gets
asyncio.ensure_future(write_sink(parsed))   # cannot alter or delay `result`
return result
```

**Why a check is insufficient.** A writer on the live path can fail in three ways a payload
diff will not catch: it can **raise** (killing the response), it can **block** (the
TradingView handler has a ~10 s timeout — `CLAUDE.md`), or it can **succeed slowly** and
turn a fast surface into a slow one. **D4 compares outputs; none of those three changes an
output.**

**A BROKEN SINK MUST NOT BECOME THE PAUSE OUTAGE BY ANOTHER ROUTE.** The pollers were
paused once this register already, and the lesson was that live consumers are live.
**Adding a writer to their path re-creates that exposure with a new name.**

**Testable as a property:** a writer that raises unconditionally must leave every live
consumer's response byte-identical and no slower. **That test is the deliverable, not the
diff.**

### S11 — SIZE AND RETENTION, DECLARED BEFORE THE FIRST ROW (F7)

**Railway Postgres has a ceiling, and this build's whole purpose is to write a lot of rows
forever.**

**Before the first migration runs, the brief states:**

- **`prints/day × tickers × bytes/row`** → a **stated table-growth figure** in MB/month,
  computed from a measured session, not estimated from a guess;
- **a retention or partition policy**, declared with it — monthly partitions on
  `executed_at`, or a stated retention horizon, or an explicit "keep forever and here is
  the ceiling date";
- **the same for `market_tide_history`**, which is small (~78 bars/day) and should be
  stated anyway so the asymmetry is on the record.

**A growth figure without a policy is not a plan**, and a policy chosen after the table is
large is a migration under pressure. **`DEF-PGSS-TEXTFILE-GROWTH` is already on this
register for a volume nobody sized in advance.**

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
- **D8** — migrations carry `-- DOWN`. **All of them, both halves.**
- **D9** — **SINKS-A ships with zero new UW requests**, demonstrated: the account counter
  is unchanged across a deploy and a full session of writer activity.
- **D10** — **a writer that raises unconditionally leaves every live payload byte-identical
  and no slower** (S10). The property, not the diff.
- **D11** — **table-growth figure and retention policy stated before the first migration**
  (S11).
- **D12** — **`enrichment_data` merge preserves a pre-existing key** from another path
  (S6/F5).
- **D13** — **ingest counts declared before the write and met exactly**, T5b discipline,
  with the archive's coverage window read off the copy.

## Gates / what NOT to do

- **NO second fetch** for the sink (S3).
- **NO backfill draw before the governor ENFORCES**, `/health` shows account usage, and
  AEGIS has sized it against the **measured remainder** — not against 40,000 (S4, A2).
- **NO vendor draw for anything the archive already holds.**
- **NO writer on a live request path** (S10).
- **NO whole-column write to `enrichment_data`** (S6).
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

**Q2 — what is the print key? MEASURE ON BOTH SOURCES (F3).** UW prints carry no id in the
path the enricher reads. If the composite key is not unique, dedupe on replay is undefined.
**Measure before designing the table, per §1.2** — `(rows, distinct_keys)` stated, not
assumed.

**And measure it TWICE, on two different populations:**

1. **the logger's Parquet** — which stored the RAW payload. **If UW prints carry an id that
   the enricher's read path simply does not surface, the archive already contains it**, and
   the key question is answered before the table is designed rather than after.
2. **one live session** — because the archive's shape is what UW sent in August, and the
   live path is what it sends now.

**The two answers can differ, and that difference is itself the finding.** A key that is
unique in the archive and not live means the field was dropped somewhere between them.

**Q4 — the logger's GEX file: do not build on it (F4).** `greek_exposure_daily/<TICKER>/
<TICKER>_rolling.parquet` is **overwritten every run** — one fetch wide, not a history.
**And GEX history already exists in `factor_readings.metadata`**, which stores the raw
payload per reading, at the 15-minute factor cadence since the column existed.

**Verify the archive's depth when the transfer lands — then do not build on it.** The
in-house series is denser, longer, and already governed. **Named here because "we have GEX
Parquet" is exactly the sentence that would send someone to the wrong source.**

**Q3 — does the tide sink's 5-minute interval need its own row, or is the snapshot cadence
enough?** Amendment 1's S6 defines tide sign as *"the net premium sign of the 5-minute
market-tide bar containing `fired_at`"* — **so the answer is fixed by the registration, not
by convenience: 5-minute bars, or S6 cannot be computed as declared.**
