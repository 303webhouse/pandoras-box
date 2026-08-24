# ORPH-SRC-1 - RESULTS (spine-assigned R-IV.38(e); EDGE-authored)

```
lane            : CC-QUERY
governing SHA   : 2de26c6
in-DB wall-time : 2026-08-20 21:29:42.177056 UTC
protocol        : SELECT-only, verbatim, read-only session, TZ UTC,
                  passthrough typecasters, errors unedited
status          : HELD un-pushed; scratchpad only
```

---

## ORPH-SRC-0  wall-time

```sql
SELECT (NOW() AT TIME ZONE 'UTC')::text AS utc_now;
```

```
utc_now                   
--------------------------
2026-08-20 21:29:42.207972
(1 rows)
```

---

## ORPH-SRC-A  poison-window orphans by source x type

```sql
SELECT o.source, o.signal_type, COUNT(*) AS n
FROM signal_outcomes o
LEFT JOIN signals s ON s.signal_id = o.signal_id
WHERE s.signal_id IS NULL
  AND o.created_at >= TIMESTAMP '2026-08-18 13:23:37'
  AND o.created_at <= TIMESTAMP '2026-08-19 22:30:31'
GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 40;
```

**ERROR (verbatim, unedited):**

```
UndefinedColumn: column o.source does not exist
LINE 1: SELECT o.source, o.signal_type, COUNT(*) AS n
               ^
HINT:  Perhaps you meant to reference the column "s.source".
```

---

## ORPH-SRC-A-FALLBACK  (gated: runs ONLY if A errored on the column)

```sql
SELECT o.signal_type, COUNT(*) AS n
FROM signal_outcomes o
LEFT JOIN signals s ON s.signal_id = o.signal_id
WHERE s.signal_id IS NULL
  AND o.created_at >= TIMESTAMP '2026-08-18 13:23:37'
  AND o.created_at <= TIMESTAMP '2026-08-19 22:30:31'
GROUP BY 1 ORDER BY 2 DESC LIMIT 40;
```

```
signal_type          | n  
---------------------+----
PULLBACK_ENTRY       | 223
HOLY_GRAIL_1H        | 103
ARTEMIS_LONG         | 38 
ARTEMIS_SHORT        | 35 
APIS_CALL            | 32 
TWO_CLOSE_VOLUME     | 14 
FOOTPRINT_LONG       | 4  
SELL_RIP_EMA         | 4  
SELL_RIP_VWAP        | 4  
FOOTPRINT_SHORT      | 1  
RESISTANCE_REJECTION | 1  
(11 rows)
```

---

## ORPH-SRC-B  key-format fingerprint, PULLBACK_ENTRY ghosts

```sql
SELECT o.signal_id, o.created_at::text AS created_at_txt
FROM signal_outcomes o
LEFT JOIN signals s ON s.signal_id = o.signal_id
WHERE s.signal_id IS NULL
  AND o.signal_type = 'PULLBACK_ENTRY'
  AND o.created_at >= TIMESTAMP '2026-08-18 13:23:37'
  AND o.created_at <= TIMESTAMP '2026-08-19 22:30:31'
ORDER BY o.created_at ASC LIMIT 10;
```

```
signal_id                            | created_at_txt            
-------------------------------------+---------------------------
24e182b1-d424-4e8d-b2a3-d830be17de0a | 2026-08-18 13:31:34.519116
0410ee5e-1869-4e99-8cee-7fea12b72380 | 2026-08-18 13:31:37.099328
fd2022b8-0405-42fb-8c9e-115a4970a0a5 | 2026-08-18 13:46:42.723407
1d23ec3d-5e46-418e-af4f-b00132c6c89c | 2026-08-18 13:46:44.280011
a934faed-e847-44cb-aea9-24c572df3fd8 | 2026-08-18 13:46:47.36656 
90cbf552-9e63-443f-9dd6-9ab7b2f67b94 | 2026-08-18 13:46:49.340752
aaf08314-db54-46cc-b6c9-05f88e081065 | 2026-08-18 14:02:22.869795
3f10d581-a0dc-4cda-a1b5-cdac55c8affc | 2026-08-18 14:02:25.285774
fbc344e8-5c13-4150-9435-ff0b08c785a4 | 2026-08-18 14:02:26.937196
d317eda3-513c-47b2-8386-b2d4d103721b | 2026-08-18 14:02:29.276413
(10 rows)
```

---

## ORPH-SRC-C  post-restoration persisted-type check

```sql
SELECT strategy, source, COUNT(*) AS n,
       MIN(created_at)::text AS first_row,
       MAX(created_at)::text AS last_row
FROM signals
WHERE signal_type = 'PULLBACK_ENTRY'
  AND created_at > TIMESTAMP '2026-08-19 22:30:31'
GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 10;
```

```
strategy    | source      | n  | first_row                  | last_row                  
------------+-------------+----+----------------------------+---------------------------
CTA Scanner | cta_scanner | 16 | 2026-08-20 13:00:54.473932 | 2026-08-20 20:12:06.450951
(1 rows)
```

---

## Row counts

| Block | Rows |
|---|---|
| ORPH-SRC-0  wall-time | 1 |
| ORPH-SRC-A  poison-window orphans by source x type | ERROR |
| ORPH-SRC-A-FALLBACK  (gated: runs ONLY if A errored on the column) | 11 |
| ORPH-SRC-B  key-format fingerprint, PULLBACK_ENTRY ghosts | 10 |
| ORPH-SRC-C  post-restoration persisted-type check | 1 |

---

## ADJUDICATION v1.1 · EDGE · 2026-08-24

Supersedes the v1.0 adjudication (relay-only, never filed) **whole**; authored with
the filed artifact open; strike lineage carried.

**(i)** `signal_outcomes` has **NO `source` column — STANDS.** Artifact:
`UndefinedColumn`; the gate fired correctly and the fallback ran only then.

**(ii)** A-FALLBACK by-type ≡ LETH-f3: **11/11 cells, both sum 459** —
chair-verified (R-IV.65(a)); reads 40 minutes apart the same evening (20:49:09Z ·
21:29:42Z, 2026-08-20). **NO DIVERGENCE**; outcomes-type-mutation **DEAD**; RECON
retired.

**(iii) CORRECTED.** The B block's 10 sampled ghost keys are **10/10 bare UUIDs**.
UUID is the CTA pipeline's NORMAL persisted key format (artifact exhibits
`e43fd128-…`, `b906c177-…` — persisted CTA PULLBACK_ENTRY rows; T6-C
precedent per R-IV.65(b)) ⇒ **B alone discriminates nothing.**
NON-PIPELINE-WRITER is **DEAD** on the surviving grounds: the C block — CTA
Scanner persisting PULLBACK_ENTRY post-restoration (16 rows, 08-20 13:00 → 20:12,
source `cta_scanner`) — plus ghost-key format matching the pipeline's own.

**(iv)** Emitter-never-dead **STANDS**; premise-error root = unscoped
Crypto-Scanner-only C2 citation (owned two-sided per R-IV.40(a)).

**(v) RATE RESIDUAL, upgraded (R-IV.65(f)).** B-block cluster timing (~15-min
cycles, 2–4 per burst) + rate coherence (~90/day in-window vs 8–16/day
persisted either side) **SUPPORT** table-reading-dedupe. Refined mechanism: UUID ids
⇒ `ON CONFLICT` cannot dedupe ⇒ the suppressor must be a **pre-insert
`signals` query**, disabled by table death. Discriminator: one grep of the CTA scan
path for a pre-insert `signals` query — EDGE-claimed, non-blocking.

### STRIKE LINEAGE

- **v1.0(iii) evidence description STRUCK** — inversion ("structured keys, ZERO
  UUIDs" written against a 10/10-UUID artifact in view; mechanism: the conclusion
  was re-justified under the already-falsified original premise instead of the
  corrected route).
- **v1.0 timeline STRUCK** ("08-20 vs 08-21" — both reads were 2026-08-20 evening).
- **v1.0 relay rollup cells STRUCK** (arithmetic false; summed past 459).

Conclusions survive on artifact grounds throughout.

**LESSON, binding:** adjudication prose is authored with the artifact open —
**RECALL MAY PROPOSE; ONLY THE ARTIFACT MAY ASSERT** applies to the adjudicator
first.
