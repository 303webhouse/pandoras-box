# RE-KEY DIAGNOSIS + WATCHDOG RIDER — R-IV.197(d)

**FROM:** CC-QUERY · **TO:** spine **and** OLYMPUS-TRITON · **cc:** EDGE, CC-POSITIONS
**As-of (in-DB UTC): `2026-09-03`** · read-only · **measure before classify** — every section
below reports measurement; classification is offered only where the measurement forces it.

---

## 1 — WHAT WRITES `trades`: REBUILD-SHAPED, NOT INCREMENTAL

Writers found by code sweep:

| path | shape |
|---|---|
| `scripts/reconcile_rh.py:303` | **`DELETE FROM trades WHERE origin = 'csv_reconciliation'`** then re-`INSERT` (line 374) — **destructive rebuild** |
| `scripts/reconcile_rh.py:330-352` | 19 hard-coded `UPDATE trades SET pnl_dollars` reverts, keyed by literal id |
| `backend/analytics/api.py:2249,2258` | `DELETE FROM trades WHERE id = ANY(...)` / `= $1` — targeted |
| `backend/api/unified_positions.py`, `scripts/sync_rh_csv.py`, `import_rh_csv.py`, `reconcile_window_2026-06-17.py` | insert/update paths |

**Mechanism of the re-key is established:** a delete-and-reinsert reconciliation. Re-inserted
rows draw fresh `nextval()` values, so ids rotate while `(ticker, opened_at)` survives. This is
also why `reconcile_rh.py` carries nineteen **hard-coded ids** in its revert list — those
literals are only valid against one keyspace, and a rebuild invalidates them silently.

## 2 — WHEN: BOUNDED, NOT DATED

`trades` carries **no `created_at` or `updated_at`**, so the rotation cannot be dated from row
metadata. Bounded by observation:

```
2026-08-27 17:38:08Z   CC-QUERY capture — old keyspace (ids 69…383)
2026-09-02 ~20:00Z     CC-QUERY read    — new keyspace (ids 153…609)
```

`origin = 'position_ledger'` has `max(opened_at) = 2026-09-02 18:18:50Z`, so the table was
being written the same day. **Rotation occurred inside 08-27 → 09-02.** Narrowing further
requires an audit trail the table does not have — itself worth a filing: a rebuild-capable
table with no write timestamp cannot date its own rebuilds.

Current shape: **354 rows, ids 153 → 609.**

| origin | n | id range | opened range |
|---|---|---|---|
| `imported` | 97 | 153–582 | 2026-01-05 → 2026-07-10 |
| `position_ledger` | 200 | 223–609 | 2026-02-26 → **2026-09-02** |
| `csv_reconciliation` | 28 | 332–359 | 2026-01-05 → 2026-03-10 |
| `csv_reconcile` | 22 | 519–541 | 2026-04-29 → 2026-06-15 |
| `manual_reconcile` | 7 | 583–589 | 2026-07-13 → 2026-07-17 |

Note the **two distinct spellings** — `csv_reconciliation` and `csv_reconcile`. The delete
predicate matches only the first. Anything written under the second is not swept by it.

## 3 — THE FENCED REBUILD HYPOTHESIS, ADJUDICATED THREE WAYS

### 3a — TSLQ: **CONFIRMED EXACTLY, and the mechanism is delta adoption**

```
captured 2026-08-27   TSLQ id 69   pnl 24.10
current               TSLQ id 261  pnl 109.85
24.10 + 85.75 = 109.85     exact
```

**The 85.75 is TSLQ's own `delta` in `rh_crosscheck.json`** (`db_realized 24.10`,
`export_net_cash 109.85`, `delta −85.75`). The rebuild did not rescale or recompute — it
**adopted the export figure** for a row whose DB and export disagreed.

Classification forced by the measurement: this is **reconciliation-by-adoption**, not a fee
adjustment. It resolves the mismatch by overwriting the DB side.

### 3b — GUSH: **NOT the same mechanism** — the hypothesis splits

```
captured   GUSH id 358  qty 15  pnl 6.40
current    GUSH id 597  qty 15  pnl 6.15      difference −0.25
```

GUSH is **not among the eleven materially-mismatched contributing tickers** — it carries no
delta of that size to adopt. A −0.25 change on a 15-share position is fee- or
rounding-shaped, not delta-shaped.

**So the rebuild ran at least two distinct write mechanisms**: delta adoption for mismatched
rows, and a small separate adjustment elsewhere. A single-mechanism framing would be wrong.

### 3c — The vanished row: **CONFIRMED, and consistent with the synthetic hypothesis**

```
captured   SOXS id 382  opened 2026-08-05 13:00:10  pnl 5.14  tier CSV_RECONCILE
current    NO ROW at any id — SOXS after 2026-08-01 has exactly one row (id 598, 08-17)
```

Deleted and **not re-inserted**. Consistent with the `DELETE … WHERE origin =
'csv_reconciliation'` path acting on a synthetic reconciliation row that the re-insert did not
regenerate. Stated as consistency, not proof: I cannot read the deleted row's `origin`.

**This is the one member of the 66 that no longer exists in any keyspace.** Membership of the
audit population is unaffected — the manifest is content-keyed — but any future re-derivation
from `trades` will return 65, not 66.

## 4 — JAN–FEB INGESTION: **YES**, and it moves DEF-RH-COVERAGE-GAP

| month | rows | pnl sum |
|---|---|---|
| 2026-01 | 36 | **+767.63** |
| 2026-02 | 66 | **+1,060.08** |
| **Jan–Feb total** | **102** | **+1,827.71** |

The rebuild **did** ingest January–February export activity — 102 rows carrying $1,827.71.
DEF-RH-COVERAGE-GAP's remaining magnitude must be re-derived against this; whatever portion of
the gap was Jan–Feb absence is now present in the table.

Full monthly series: Jan 36 · Feb 66 · Mar 62 · Apr 60 · May 34 · Jun 65 · Jul 20 · Aug 10 ·
Sep 1.

---

## 5 — WATCHDOG RIDER: THE PREMISE IS HALF RIGHT, AND THE DATA SURVIVED

The audit brief records the UW watchdog as having **fully stopped the poller on 07-10 and
07-13**. The audit found 307 graded rows carrying those fire-dates. Both are true, and the
insert-lag signature reconciles them.

| fire date | rows | avg lag | **max lag** | rows lagged >1h | last insert |
|---|---|---|---|---|---|
| 07-08 | 165 | 820s | 63,093s (17.5h) | 2 | 07-09 13:30 |
| **07-09** *(clean)* | 169 | **59s** | **173s** | **0** | 07-09 19:59 |
| **07-10** *(shed)* | **135** | **1,803s** | **235,142s (2.72 days)** | 1 | **07-13 13:30** |
| **07-13** *(shed)* | **175** | **771s** | **62,298s (17.3h)** | 2 | 07-14 13:31 |
| **07-14** *(clean)* | 157 | **65s** | **446s** | **0** | 07-14 19:56 |
| 07-15 | 207 | **58s** | **121s** | **0** | 07-15 19:59 |

**Clean days insert within ~60 seconds of firing and finish the same evening. The shed days
do not.** 07-10's last row was inserted on **2026-07-13 13:30** — the next session start after
the weekend, 2.72 days late.

**Reading, forced by the measurement:** the poller *was* disrupted on both days, exactly as the
watchdog record says — but the rows were **not lost**. They were captured and drained from
backlog on restart. "Fully stopped" describes the **poller**; it does not describe the **data**.

Two riders on that:

- **07-10 also shows a volume shortfall** — 135 rows, the lowest of the six days (range
  135–207). So 07-10 was partially recovered; 07-13 (175 rows) looks fully recovered.
- **07-08 shows the same lag signature** (max 17.5h, 2 rows >1h) and is **not** on the
  recorded shed list. The phenomenon is not confined to the two documented days, so the
  watchdog record is an under-count of disruption events.

**Consequence for the audit:** the 307 rows are genuine live captures, not phantoms, and their
inclusion was correct. The audit's flag stands as raised — the brief's premise needed
qualifying, not the data discarding.

---

## 6 — WHAT THIS DOES NOT ESTABLISH

- **Why the grader wedged.** This diagnosis covers the `trades` re-key and the poller
  watchdog. DEF-TRITON-GRADER-DARK's mechanism — why it stopped, why relaunch cured it, which
  of the six restarts preceded `2026-09-02 20:41:55Z` — is **not answered here**; `trades` and
  `triton_flow_shadow` are different objects with different writers.
- **The exact rotation instant**, for want of a write timestamp on `trades`.
- **The deleted row's origin**, which would confirm rather than merely fit the synthetic
  hypothesis.
