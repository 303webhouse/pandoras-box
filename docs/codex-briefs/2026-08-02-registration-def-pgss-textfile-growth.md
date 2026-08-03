# Registration — DEF-PGSS-TEXTFILE-GROWTH · v1.0

**Registered by:** Fable (spine) · 2026-08-02, on CC-SHELL's measurement of the same date
**Priority:** P1 · **FIRST in the post-vacation queue**, alongside DEF-TIMESTAMP-NAIVE-SHIFT
**Ships:** NOT pre-freeze. **Spine ruling: NO pre-freeze DB write.**
**Supersedes:** DEF-DB-VOLUME-CEILING — this registration holds that defect's real content.

---

## Summary

`pg_stat_statements` writes its external query-text file to
`$PGDATA/pg_stat_tmp/pgss_query_texts.stat`. On the Railway Postgres service that file has
reached **1,261,730,321 bytes (1203.3 MiB)** and is **actively growing**. It is the entire
"~1.3GB the database cannot see" recorded against DEF-DB-VOLUME-CEILING.

The space was never invisible. It was **not covered by the instruments used** —
`pg_database_size()` sums per-database directories under `base/`, and `pg_ls_waldir()` lists
`pg_wal/`. Neither touches `pg_stat_tmp/`. A recursive walk of PGDATA finds the file
immediately.

**The library is preloaded but the extension was never installed.** `pg_extension` in the
`railway` database contains only `plpgsql`. The cluster is paying 1.2GB and ~128 MiB/day to
collect statistics that nothing in this database can read.

---

## Measurement — read-only, 2026-08-03 04:40–04:43Z (2026-08-02 22:40–22:43 MDT)

Executed by CC-SHELL through the read-only postgres MCP. No writes, no config changes.

**Environment**

| Fact | Value |
|---|---|
| Version | PostgreSQL 17.10 (Debian 17.10-1.pgdg13+1) |
| Volume mount | `/var/lib/postgresql/data` |
| `data_directory` | `/var/lib/postgresql/data/pgdata` |
| `pg_postmaster_start_time()` | **2026-07-24T19:15:47Z** (13:15:47 MDT) |
| Uptime at measurement | 9 days 9 hours 25 minutes |
| Volume-root entries | `lost+found`, `certs`, `pgdata` — no stale sibling cluster |

**PGDATA recursive walk** — `pg_ls_dir` / `pg_stat_file` as superuser, 2213 files, 28 dirs

| Subdirectory | Files | MiB |
|---|---|---|
| **pg_stat_tmp** | **1** | **1203.3** |
| base | 1886 | 990.2 |
| pg_wal | 37 | 592.0 |
| pg_xact | 5 | 1.0 |
| global | 273 | 0.6 |
| pg_subtrans / pg_logical / pg_multixact | 4 | ~0.0 |
| **Total** | **2213** | **2787.1** |

**The file**

```
pg_stat_tmp/pgss_query_texts.stat
  size      1,261,730,321 bytes  (1203.3 MiB)
  mtime     2026-08-03T04:43:18Z   <-- being written during measurement
  atime     2026-07-28T01:01:46Z
pg_stat_tmp/ directory mtime = 2026-07-24T19:15:47Z  (== postmaster start)
```

**Reconciliation against the Railway gauge**

```
walked PGDATA                     2787.1 MiB
Railway volume gauge              ~2918   MB
residual                          ~131    MB   -> lost+found, certs, dirent/fs overhead
```

Prior record was `967 + 624 = 1591` (db + WAL) against a ~2918 gauge. Both legs were
correct measurements of the wrong denominator; `pg_stat_tmp` was outside both.

**Settings** — all `source=default`

| Setting | Value |
|---|---|
| `pg_stat_statements.max` | 5000 |
| `pg_stat_statements.save` | **on** |
| `pg_stat_statements.track` | top |
| `pg_stat_statements.track_utility` | on |
| `pg_stat_statements.track_planning` | off |
| `pg_extension` (database `railway`) | **`plpgsql` only** |

---

## Growth rate and freeze math

```
1203.3 MiB accumulated 2026-07-24T19:15:47Z -> 2026-08-03T04:43:18Z
elapsed                = 9.394 days
rate                   = 1203.3 / 9.394  = ~128.1 MiB/day
projection to 08-15    = 128.1 x 11.8    = ~1512 MiB
volume on 2026-08-15   = 2918 + 1512     = ~4430 MB  (~4.4 GB)
cap                    = 5.12 GB
margin                 = ~700 MB
```

**Spine ruling: the projection clears the freeze with ~700MB of margin. Nothing ships.**

**Rate caveat, on the record:** the ~128 MiB/day figure assumes the file was at zero when the
postmaster started on 07-24. With `save=on` PG17 persists query texts to `pg_stat/` on clean
shutdown and reloads them at startup, so the file may have started non-zero — in which case
the true rate is *lower* than 128 MiB/day and the projection is conservative. It is not
higher. Growth may also be sawtooth rather than linear if garbage collection fires.

---

## Fix shape — post-vacation, not now

1. **`CREATE EXTENSION pg_stat_statements;` then `SELECT pg_stat_statements_reset();`** — the
   reset truncates the query-text file. Requires the extension to exist in order to call the
   function. This is the direct remedy for the 1.2GB.
2. **Evaluate disabling the preload with Railway** — if nothing consumes these statistics,
   removing `pg_stat_statements` from `shared_preload_libraries` stops the cost at source.
   Requires Railway to expose the setting and a service restart.
3. **Root-cause rider — code quality, its own finding.** ~128 MiB/day of *distinct* query
   texts means the application is **inlining literals instead of parameterizing**. Every
   distinct literal produces a distinct queryId and a fresh stored text. This is a defect in
   its own right independent of disk: it defeats plan caching, inflates parse overhead, and
   is the reason the text file grows at all. **Fold it into the post-vacation work** — the
   disk symptom and the parameterization defect are one investigation.

---

## Operator protocol — Nick

- **One gauge glance, ~2026-08-09.** Not before; there is nothing to see and no decision it
  would change.
- **Valve one: resize the volume.** Available, understood, low risk.
- **Valve two: restart the Postgres *service*** (not an app redeploy). **UNVERIFIED** — with
  `save=on` a restart may reload the persisted texts rather than release the space. Do not
  count on it until verified.
- **Supporting evidence for valve two:** the 07-24 cliff. `pg_stat_tmp/` carries the
  postmaster's start-time mtime, which is consistent with the file being recreated at
  startup — but consistent is not confirmed.

---

## Verification debt — post-vacation, explicitly deferred by spine

Restart semantics under `pg_stat_statements.save=on` on PG17: does a restart release,
partially compact, or fully preserve `pgss_query_texts.stat`? Does the answer differ for a
clean shutdown versus a container SIGKILL? **Not to be investigated pre-freeze.**

---

## Corrected premise, logged

Saturday 2026-08-01 23:16Z's deploy restart could not have tested the release hypothesis:
**Railway Postgres is a separate service from the app.** An app redeploy does not restart the
database. `pg_postmaster_start_time()` proves continuous operation since 2026-07-24T19:15:47Z,
across both that deploy and the QS-01 docs push at 2026-08-03T02:38Z. Neither was DB-inert by
accident — neither touched the database process at all.
