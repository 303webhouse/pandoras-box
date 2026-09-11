# R-IV.355(c) ANSWERED — both surfaces dedup today, and the premise needs correcting

**CC-BUILD, 2026-09-11.** From the code, before tomorrow's read.

---

## THE ANSWER: YES. BOTH DEDUP. THE WEEKEND ITEM IS NOT NEEDED TO PREVENT RATE INFLATION.

| surface | mechanism | key | durable? |
|---|---|---|---|
| `pythia_events` webhook | **Redis `SETNX`** (`webhooks/pythia_events.py:141-155`) | `pythia_seen:{ticker}:{alert_type}:{bar_time_ms}` | **NO — cache, TTL 30 min, degrades OPEN** |
| SPEC-01 converter | **Postgres `ON CONFLICT (signal_id) DO NOTHING`** (`jobs/strike_ib_converter.py:125-127`) | `signal_id` | **YES — a constraint** |

**The webhook already dedups on EXACTLY the key proposed** — `(ticker, event, bar_time)`. A
duplicate returns `{"status": "duplicate"}` and **writes no row** (`:153-155`).

**So the rate re-derivation is NOT inflated for every ticker on both surfaces.** Duplicates
suppressed by the claim never became rows on either surface. **The premise behind the weekend
item does not hold in the direction that motivated it.**

**The one exception, and it is measurable:** the claim is skipped entirely when Redis is absent
(`if _redis:` at `:145`) and on any SETNX exception (`is_new = True`, `:150-152`). **This is
deliberate — "never drop a real event for a cache outage" — and it means duplicates DO land
during a Redis outage.** Rate inflation is therefore possible **only inside Redis-down
windows**, which `/health.redis` and the `"PYTHIA idempotency SETNX failed"` debug line both
date.

## (b) THE DUPLICATE CENSUS CANNOT BE COMPUTED FROM THE TABLE — and a zero there would be vacuous

**Two independent reasons, either one sufficient.**

**1. `bar_time` is never persisted.** It is parsed at `:120`, used for replay protection
(`±10 min`, `:124-128`) and for the idempotency key (`:146`) — **and then dropped. It is not in
the INSERT column list (`:163-167`) and not a column of either DDL.**

**ELEVENTH COMPUTE-THEN-DISCARD INSTANCE**, and the most pointed one yet: **the value is
computed, used twice for correctness, and discarded before the thing that would let anyone
audit either use.**

**2. A suppressed duplicate leaves NO ROW AT ALL.** By design. So the duplicates the census
wants to count are precisely the ones absent from the table.

> **`SELECT ... FROM pythia_events GROUP BY ... HAVING count(*) > 1` will return ~0, and that
> zero means "the dedup held" — NOT "no duplicates arrived."** Read as the latter it is a
> null result dressed as a finding. **It cannot fail in the normal case.**

**The census must be read from the LOG**, where the suppressed ones are the only place they
exist:

```
pythia_events.py:154   "PYTHIA duplicate suppressed: %s %s bar_time=%s"
```

**That line carries ticker, alert_type and bar_time — the whole key** — and the log timestamps
give the arrival gap. **Count and gap are both available there and nowhere else.**

## THE REAL GAP IS DURABILITY, NOT DETECTION — and it is the R-IV.352(c) shape again

**The converter's dedup is a database constraint. The webhook's is a cache that is designed to
fail open.** Same purpose, different guarantees, and **nothing on the webhook surface records
which regime it was in when a row was written.**

**This is structurally identical to the tombstone ruling** on `DEF-BIAS-NULL-AS-NEUTRAL`:
*exclusion must not depend on a delete succeeding* → **dedup must not depend on Redis being
up.** Same defect shape, different subsystem, ruled once already.

**Recommended weekend item — re-justified, NOT the one proposed:**

1. **persist `bar_time`** (migration: `bar_time TIMESTAMPTZ` or epoch-ms `BIGINT`, nullable —
   rows before it genuinely lack it, and **a backfilled default would fabricate the exact
   quantity the census is about**);
2. **`UNIQUE (ticker, alert_type, bar_time)`** + `ON CONFLICT DO NOTHING` on the INSERT;
3. **keep the Redis claim** — it saves the round-trip and it is not wrong; the constraint is
   the floor beneath it, not a replacement.

**Then dedup survives a cache outage, and the census becomes answerable from the table it
should have been answerable from.**

## PRE-FLIGHT — TWO THINGS THAT WOULD POISON TOMORROW'S FIRST-HOUR READ

### 1. There are TWO divergent DDLs for `pythia_events`, and the INSERT fits only one

| | `init_database()` @ `postgres_client.py:1481` | inside `log_options_position()` @ `:2548` |
|---|---|---|
| runs | **startup**, `main.py:49` | **on every options-position log** |
| columns | 17, incl. `va_migration, poor_high, poor_low, volume_quality, ib_high, ib_low, interpretation` | **10 — missing all seven** |
| time column | `timestamp` | `created_at` |

**Both are `CREATE TABLE IF NOT EXISTS`, so FIRST WRITER WINS and the loser is a silent
no-op.** Startup normally wins, which makes this **latent rather than active** — but **the
INSERT writes all seven columns the `:2548` shape lacks**, so on any database where the
options path created the table first, **every accepted PYTHIA event fails at the INSERT —
after auth, so it would NOT appear as a 401.**

**Separately and regardless: DDL for four unrelated tables is buried in a function named
`log_options_position`.** Registering that as a finding; not fixing it tonight.

### 2. Zero accepted events means the INSERT has never been OBSERVED to succeed

**The v2.5 read recorded three 401s and zero accepted events for any ticker.** So the write
path has no successful execution on record in the observed window. **Before tomorrow's report
attributes anything to the feed, confirm the live table has the columns the INSERT writes** —
otherwise "accepted at the webhook, zero rows" gets read as a feed problem when it would be a
schema problem.

**The check is read-only and belongs to CC-QUERY** (no manual SQL against prod from this lane):

```sql
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'pythia_events'
ORDER BY ordinal_position;
```

**Pass = all fifteen INSERT columns present.** Absence of `interpretation` or `ib_high` is the
tell for the wrong shape.

## (a) IS COMPUTABLE AS SPECIFIED

`accepted events per ticker` and `first accepted timestamp` come from
`pythia_events(ticker, timestamp)` directly, with the index at `:1502-1503` already covering
`(ticker, timestamp DESC)`. **No gap.**

---

## ONE TRANSFERABLE NOTE

**This answer inverted on a fuller read.** The DDL has no `UNIQUE`, and the INSERT has no
`ON CONFLICT` — **on the schema evidence alone the correct-looking conclusion was "no dedup,"
and it was wrong.** The dedup is twenty lines earlier and lives in Redis, outside the schema
entirely.

**A schema read cannot answer "does this dedup" when the enforcement is not in the schema.**
Kin to conventions #14 and to the same failure the census made three nights running: **the
artifact that looks authoritative for a question is not always the one that decides it.**
