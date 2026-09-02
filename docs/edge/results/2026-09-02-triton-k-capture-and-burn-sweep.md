# k-CAPTURE + QUEUE ITEMS 3 & 4 — R-IV.153

**FROM:** CC-QUERY · **TO:** spine · **cc:** Olympus lane, EDGE, CC-BUILD
**As-of (in-DB UTC): `2026-09-02 18:48:49.830100+00`** · read-only · dual-run **PASS**

Sequencing note: k was flagged blocking, and items 2–4 are all cheap reads sharing one
connection, so I took them first. **Item (1), the audit artifact, is next** — the filed brief
is located at `docs/codex-briefs/2026-07-21-triton-shadow-audit-brief.md`.

---

## (2) k = 15 — THE EXPECTATION IS NOT CONFIRMED

**Direct read, not complement:**

```
k = 15
```

Per-symbol inside the pin (all five named, so zeros are visible):

| symbol | n in holdout |
|---|---|
| SPX | 6 |
| SPXW | 6 |
| RUTW | 2 |
| VIX | 1 |
| RUT | **0** |
| **k** | **15** |

**Known-present control:** the same predicate returns 843 rows across 152 distinct tickers.
The probe discriminates; 15 is a measurement, not an empty result.

### Where the k = 0 expectation went wrong

The whole index-symbol population, bucketed:

| bucket | n |
|---|---|
| pre-08-17 (residue) | **72** |
| **holdout (pinned)** | **15** |
| future cohort (`id > 377783`) | 3 |
| **total index rows, table-wide** | **90** |

The 72 I reported was **residue-scoped by construction** — every query carrying it was
predicated on `fired_at < 2026-08-17`. It was never the table-wide total. The inference read
a scoped count as a population count and concluded the holdout share was zero.

This is precisely why spine held it as complement-as-measurement pending a direct read. The
hold was correct and the direct read overturns the expectation.

### Consequences

**EFFECTIVE VALIDATION n = 843 − 15 = 828.**

**The audit tripwire is NOT affected.** EDGE's bounds — `audit_n ∈ [6,045 · 6,099]` and
`residue_pending ≥ 72` — derive solely from residue gradeability (54 gradeable + 72
ungradeable = 126) and are untouched by k. What the read overturns is the k = 0 expectation
and effective n, not the audit bounds. The opened question should be scoped that narrowly.

**The holdout will never fully grade.** At remediation, 15 of 843 stay pending permanently.
Any monitor treating "holdout fully graded" as a completion signal waits forever.

**The defect is ongoing.** Three index rows have already landed in the future cohort since the
pin — new ungradeable rows keep arriving, as DEF-TRITON-INDEX-UNGRADEABLE anticipated.

**One limit, stated.** That these 15 are *permanently* ungradeable is **inferred from the
symbol class** — 0 of 72 same-symbol residue rows were ever graded, and all 72 carry
`prior_5d_ret IS NULL`. It is **not measured on these 15**. Confirming it directly needs one
further authorized read of `prior_5d_ret` (a pre-fire field, not an outcome) on the holdout;
that sits outside the "one aggregate metadata read" authorized at R-IV.140, so I have not
taken it.

**Registration §5 text, if useful:** *"EFFECTIVE HOLDOUT: 843 rows pinned; **15** are
cash-settled index symbols (SPX 6 · SPXW 6 · RUTW 2 · VIX 1 · RUT 0) with no price series and
are PERMANENTLY UNGRADEABLE — they do not become validation data at remediation. Effective
validation n = **828**, stated at registration rather than discovered at validation."*

---

## (3) uw_snapshots SCHEMA — commissioned read

```
id                integer                    NOT NULL  nextval('uw_snapshots_id_seq')
timestamp         timestamptz                NOT NULL  now()
dashboard_type    text                       NOT NULL
time_slot         text                       NULL
extracted_data    jsonb                      NOT NULL  '{}'::jsonb
raw_summary       text                       NULL
signal_alignment  text                       NULL
```

**0 rows.** Writer `insert_uw_snapshot()` exists at `backend/analytics/queries.py:706`.

The shape — `dashboard_type · time_slot · raw_summary · signal_alignment` — reads as a sink
for **periodic dashboard captures** (human- or LLM-extracted summaries), not a per-record API
feed. It is a **candidate** home for discarded UW data, with the caveat that per-print
dark-pool records would likely want their own typed table rather than `extracted_data` jsonb.
Stated as a candidate, not a recommendation.

---

## (4) uw_daily_burn CALLER SWEEP — INFERENCE CONVERTED TO MEASUREMENT

**`darkpool_ticker` appears, and it is running today.**

| caller | total calls | days active | avg/active day | peak | first day | last day |
|---|---|---|---|---|---|---|
| `_TOTAL` | 562,421 | 54 | 10,415.2 | 18,504 | 2026-07-09 | 2026-09-01 |
| `flow_per_expiry` | 61,076 | 38 | 1,607.3 | 1,660 | 07-09 | 09-01 |
| `triton_flow_shadow` | 21,337 | 40 | 533.4 | 2,469 | 07-09 | 09-01 |
| **`darkpool_ticker`** | **12,320** | **49** | **251.4** | 479 | **2026-07-09** | **2026-09-01** |
| `flow_recent` | 3,704 | 35 | 105.8 | 139 | 07-09 | 09-01 |
| **`market_tide`** | **2,926** | **41** | **71.4** | 81 | **2026-07-09** | **2026-09-01** |
| `greek_exposure` | 1,228 | 54 | 22.7 | 66 | 07-09 | 09-01 |

`darkpool_ticker`, last fourteen active days — the weekday/weekend shape of a live poller:

```
09-01 318 · 08-31 352 · 08-30 7 · 08-29 5 · 08-27 266 · 08-26 290 · 08-25 288
08-24 279 · 08-23 14 · 08-22 47 · 08-21 402 · 08-20 446 · 08-19 378 · 08-18 423
```

### The finding, now measured rather than inferred

**The hub has made 12,320 UW dark-pool calls across 49 active days — ~251/day, continuously
from 2026-07-09 to 2026-09-01 — and the element census found zero dark-pool rows persisted
anywhere.** `market_tide` is the same story at **2,926 calls over 41 days**, cached to Redis
on a 60s TTL and never written down.

**15,246 UW calls for data that persists nowhere** — **2.7% of all metered UW spend**
(darkpool 2.19%, tide 0.52% against `_TOTAL` 562,421).

Both discarded feeds are exactly the two missing legs of the confluence triad
(`flow AND dp AND tide`). The data has been arriving and being paid for the entire time; only
the sink is absent. That is a materially cheaper problem than building the fetch, and it is
now safe to put on a proposal face as measurement.

**One caveat on the denominator:** the named callers sum to 562,415 against `_TOTAL` 562,421 —
a 6-call gap, so `_TOTAL` is maintained independently rather than as an exact sum of parts.
Percentages above are accurate to ~0.001%, but `_TOTAL` should not be treated as a derived
figure.
