# Registration — DEF-WAL-AMPLIFICATION · v1.0

**Registered by:** Fable (spine) · 2026-08-02
**Priority:** P3 · post-vacation · **conditional on Railway exposing `wal_compression`**
**Ships:** NOT pre-freeze. **Spine ruling: NO pre-freeze config change.**
**Related:** [DEF-PGSS-TEXTFILE-GROWTH](2026-08-02-registration-def-pgss-textfile-growth.md) — P1, holds what DEF-DB-VOLUME-CEILING was actually about.

---

## Why this is P3 and not the volume fix

**`wal_compression` is not the volume lever.** It reduces WAL *generation*; it does not reduce
what was climbing on the volume. CC-SHELL's bounded-WAL finding disarmed it as a remedy for
DEF-DB-VOLUME-CEILING, and spine registered this separately rather than letting a real but
unrelated efficiency finding be spent as a false fix.

The volume growth is `pgss_query_texts.stat`. See the P1 registration.

What remains here is genuine and worth doing on its own terms: this cluster generates
FPI-dominated WAL with compression off, and turning it on is a real reduction — post-vacation,
if Railway exposes the setting.

---

## The FPI arithmetic

Recorded by spine, **attributed to CC-SHELL's 2026-08-02 report**, reproduced verbatim:

> `full_page_writes=on`; `checkpoint_timeout=300s` -> 288 checkpoints/day;
> ~270 first-touch pages per interval x 8KB x 288 ~= 620MB/day, matching the
> measured 592-624MB across 37-39 segments; `wal_compression=off` leaves FPIs
> uncompressed. Lever: `wal_compression=on`, 50-75% typical reduction on
> FPI-dominated workloads, conditional on Railway exposing it.

---

## CC-SHELL corroboration — read-only, 2026-08-03 04:40Z (2026-08-02 22:40 MDT)

Every input to the arithmetic above re-measured directly against the live cluster:

| Input | Measured | Matches |
|---|---|---|
| `full_page_writes` | `on` | yes |
| `checkpoint_timeout` | `300` s | yes — 86400/300 = 288/day |
| `wal_compression` | `off` | yes |
| WAL segments | 37 files, 592.0 MiB | in the stated 37–39 / 592–624 band |
| `max_wal_size` | 1024 MB | WAL is bounded *below* the cap |
| `min_wal_size` | 80 MB | — |
| `wal_keep_size` | 0 MB | nothing pinned by retention |
| `archive_mode` | `off` | nothing pinned by archiving |
| Replication slots | **none** | nothing pinned by a stale slot |

The bounded-WAL finding is therefore evidence-backed from four independent directions: WAL
sits under `max_wal_size`, no slot retains it, no archiver retains it, and `wal_keep_size` is
zero. **WAL is not what was climbing.**

**Two precision notes for whoever executes this post-vacation:**

1. **Units.** `270 x 8KB x 288` lands at 593.3 MiB/day reading 8KB as 8000 bytes, or
   607.5 MiB/day reading it as 8192. Measured resident WAL is 592.0 MiB. Agreement is within
   ~3% on either reading — the arithmetic holds; the band is just tighter than round numbers
   suggest.
2. **Generation vs resident.** The arithmetic computes WAL *generated per day*; the 592.0 MiB
   is WAL *resident right now* (37 x 16 MiB segments). These are distinct quantities that
   happen to be close here because recycling under these settings turns the working set over
   on roughly a daily cadence. Do not treat the match as identity when re-measuring after any
   change to `checkpoint_timeout` or `max_wal_size`.

---

## Fix shape — post-vacation, conditional

1. **Determine whether Railway exposes `wal_compression`** on the managed Postgres service.
   If it does not, this registration is blocked and should be recorded as such rather than
   retried.
2. If exposed: set `wal_compression=on` (`pglz`, or `lz4`/`zstd` if the build supports them —
   PG17 does support all three).
3. Re-measure WAL generation over a full day and compare against the ~620MB/day baseline
   above. Expected reduction 50–75% on an FPI-dominated workload.

**No restart is required for `wal_compression`** — it is `sighup`-reloadable. That is one
reason it is low-risk *when* it becomes available, and no reason at all to do it pre-freeze.

---

## Explicitly out of scope

The 1.2GB on the volume. That is `pgss_query_texts.stat` and it is tracked at P1 under
DEF-PGSS-TEXTFILE-GROWTH. **This registration must not be used to justify a volume fix** —
that conflation is the exact error this separation exists to prevent.
