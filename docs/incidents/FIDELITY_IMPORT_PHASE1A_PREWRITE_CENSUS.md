# FIDELITY-IMPORT-ACCT-ROTH — Phase 1a PRE-WRITE CENSUS

**AUTHORIZATION: CLEARED (R-IV.84(c), 2026-08-25). STILL NO WRITES PERFORMED** — execution
is blocked on the segmenter script, which R-IV.84(c) assigns to POSITIONS to author. This
file is the census-first preimage baseline required by binding condition 8, produced
entirely read-only and re-verified stable at the stamp below.

**Dual-provenance stamp** (R-IV.84(h) general form):

| provenance | value |
|---|---|
| **Tree SHA** (execution pin) | **`8b2d767`** — own fetch 2026-08-25 06:57 UTC, confirmed by `git ls-remote origin refs/heads/main`, **0 ahead / 0 behind** |
| **Text SHA** (this document) | `8b2d767` — authored and re-stamped at the same tree |
| **DB preimage** | `md5 db0d0231c62cc4fa49453253a425f1a5` over Fidelity-side rows, re-verified 06:58 UTC |

Stamped 2026-08-25 06:58 UTC (2026-08-25 00:58 MDT). Per R-IV.84(c) the inherited `2de26c6`
pin does **not** carry forward — that pin governs the Phase 0/0b reports only. This tree SHA
will be re-fetched and re-stamped again at the moment of execution, per R-IV.84(h).

**Read path:** direct SQL via read-only Postgres MCP with `::text` casts; artifacts read
from `data/imports/`. `hub_get_positions` not used.

---

## Prerequisites — all three complete

### 1. Fetch / drift — CLEAN

```
local  HEAD:  8b2d767
remote main:  8b2d767
ls-remote  :  8b2d767
behind: 0    ahead: 0
```

No pull required. The tree was rebased to `8b2d767` at 06:11 UTC in the prior turn and has
not drifted since.

### 2. Normalizer artifacts — CURRENT, no re-run needed

Artifacts are dated **2026-08-25 00:12 MDT**, generated *after* the pull to `8b2d767`
(~00:11 MDT). They do not predate the pull, so the re-run condition does not fire.

All ten stated figures verified against `import_reconciliation.json`, 10/10 exact:

```
  OK  trade_fills: 83          OK  pre_split_rows: 16
  OK  cash_events: 11          OK  unsettled_rows: 7
  OK  buys: 50                 OK  duplicate_same_day_fills: 0
  OK  sells: 33                OK  hash_collisions: 0
  OK  split_boundary_last_pre: 2026-07-14
  OK  split_boundary_first_post: 2026-07-15
```

Per-ticker fill counts reconcile to the brief's reference table exactly:

```
 BITX  6    GDXJ 10    GUSH 11    RAMZ  3    SOXS 32
 SQQQ  9    SSPC  2    WRTH  3    XLE   7          total 83
```

The seven realized tickers sum to **69**; `GUSH 11 + WRTH 3 = 14` are the open positions.
`69 + 14 = 83`. ✅

### 3. Census — zero Fidelity overlap CONFIRMED, but see the hazard below

```
 A. Fidelity-side rows with ANY date in 06-25 → 08-24 ......  0
 B. Fidelity-side rows, all dates ..........................  46
 C. Fidelity-side max entry_date ........... 2026-06-18 17:49:13.085966+00
 D. Fidelity-side max exit_date ............ 2026-06-18 17:47:46.620612+00
 E. Rows on the 9 CSV tickers, ANY account, in window ......  11   <-- HAZARD
 F. BROKERAGE_LINK_401K rows, any date .....................  0
```

**A = 0 confirms the expectation rather than assuming it.** Both Fidelity date bounds stop
2026-06-18, seven days before the window opens. There is no Fidelity-labeled row to collide
with.

---

## ⚠️ PRE-WRITE HAZARD — 11 same-ticker in-window rows under `ROBINHOOD`

The brief anticipated zero overlap *on the Fidelity label* and that holds. But the same
tickers, inside the same window, carry **11 rows labeled `ROBINHOOD`**. If any of these
describe the same real trades the CSV describes, writing Fidelity rows for them
**double-counts**.

| id | position_id | tkr | qty | realized | source | window dates |
|---|---|---|---|---|---|---|
| 348 | `POS_SOXS_20260707_06000003` | SOXS | 87 | −58.30 | CSV_RECONCILE | exit 07-14 |
| 354 | `POS_SOXS_20260715_060000` | SOXS | 6 | +69.79 | MANUAL | 07-15 → 07-17 |
| 368 | `POS_SOXS_20260720_120005` | SOXS | 10 | +20.57 | CSV_RECONCILE | 07-20 |
| 382 | `POS_SOXS_20260805_130010` | SOXS | 8 | +5.14 | CSV_RECONCILE | 08-05 → 08-11 |
| 383 | `POS_SOXS_20260817_130011` | SOXS | 6 | +38.28 | MANUAL | 08-17 → 08-18 |
| 369 | `POS_BITX_20260721_120006` | BITX | 50 | +2.01 | CSV_RECONCILE | 07-21 |
| 370 | `POS_SQQQ_20260722_120007` | SQQQ | 10 | +17.91 | CSV_RECONCILE | 07-22 → 07-23 |
| 358 | `POS_GUSH_20260724_181446` | GUSH | 15 | +6.40 | MANUAL | 07-24 → 07-31 |
| 347 | `POS_XLE_20260707_06000002` | XLE | 1 | +53.90 | CSV_RECONCILE | **OPTION** |
| 351 | `POS_XLE_20260715_164155` | XLE | 1 | +81.94 | MANUAL | **OPTION** |
| 365 | `POS_XLE_20260803_120002` | XLE | 1 | — (OPEN) | MANUAL | **OPTION** |

**The three XLE rows are safe to ignore** — they are `asset_type='OPTION'` with option
premiums (0.29 / 0.18 / 0.231), a different instrument from the CSV's 7 XLE *equity* fills.
No collision possible.

**The eight equity rows are unresolved.** They are same-ticker, same-window, and five carry
`source='CSV_RECONCILE'` — meaning they were themselves produced by a prior CSV import.
Spot-checks are suggestive but not conclusive:

- id 368: 07-20, qty 10 — CSV has `2026-07-20 BUY 10 @ 52.38`. **Date and quantity match.**
- id 354: entry 07-15 @ 46.208 qty 6 — CSV has `07-15 BUY 10 @ 46.04`. Same date, **qty and
  price differ**.
- id 382: 08-05 qty 8 @ 43.3719 — CSV has `08-05 BUY 15 @ 44.30`. Same date, **qty differs**.
- id 383: 08-17 qty 6 @ 38.48 — CSV has `08-17 BUY 10 @ 37.96`. Same date, **qty differs**.

Two readings, and DB state cannot separate them: either the principal traded the same ETFs
in both accounts on the same days (plausible — these are his core tickers), or some of these
are **mis-attributed Fidelity trades already sitting under the Robinhood label**.

**This must be adjudicated before any write.** It is not resolvable from the artifacts in
hand — it needs the Robinhood export for the same window to subtract. Raising rather than
guessing.

---

## Reference totals — INDEPENDENTLY VALIDATED, 7/7 to the cent

Cross-checked without segmenting, by summing signed `gross` per ticker (buys negative,
sells positive). For a ticker flat at both ends, that sum *is* realized P&L:

```
 tkr    fills  net_qty   sum_gross  brief_ref     delta
 BITX       6    0.000       81.19      81.19     +0.00
 GDXJ      10    0.000       89.16      89.16     +0.00
 RAMZ       3    0.000       46.92      46.92     -0.00
 SOXS      32  -45.000      791.12     791.12     -0.00
 SQQQ       9    0.000      -38.60     -38.60     +0.00
 SSPC       2    0.000       13.90      13.90     -0.00
 XLE        7   -0.071      110.69     110.69     +0.00
 GUSH      11   30.000    -1199.69     (open)        —
 WRTH       3   20.000     -510.93     (open)        —
```

Total of the seven: **+$1,094.38** ✅ — matches the brief exactly.

**SOXS corroborates the exemption.** Its figure is `sum(gross) − 1817.775`, and 1817.775 is
exactly `45 × 40.395` — the principal-confirmed pre-window lot. The number only closes with
that basis, from a source independent of both the principal's statement and the −45
net-flow gap. Row `id 311` independently stores `cost_basis = 1817.78`. Three-way agreement.

---

## ⚠️ Condition 1 vs the XLE reference total — a live tension

XLE's `sum_gross` of **+110.69** matches the brief's reference, **but net quantity is
−0.071** — a fractional disposal with no in-window acquisition. That is precisely the
zero-basis case the brief declares **not exempt**.

So condition 1 (render `cost_basis` NULL and realized N/A) and the XLE reference total
(110.69) **cannot both be satisfied**. Whichever trade carries the 0.071 disposal must be
`UNKNOWN`, so the XLE trade-level rows will sum to **less than 110.69** by that trade's
contribution — the unknown basis of 0.071 shares plus its proceeds.

Per the brief's own instruction — *"these figures are the check, not the target … report the
discrepancy rather than reconciling to them"* — this is reported, not reconciled. Expect and
accept an XLE shortfall. Flagging now so it is not later read as a segmentation failure.

---

## Canonical account label — recommendation

The brief requires one label, stated. DB facts:

| label | rows in `unified_positions` | rows in `account_balances` |
|---|---|---|
| `FIDELITY_ROTH` (underscore, upper) | **46** | 0 |
| `BROKERAGE_LINK_401K` | **0** | 1 |
| `'Fidelity Roth'` (space, mixed case) | 0 | 1 |

**Recommend `FIDELITY_ROTH`** for the position writes: it is the only label with existing
position rows, so writing there keeps one account's history in one place and avoids creating
a second identity for the same real account. `BROKERAGE_LINK_401K` has never held a position
row and is additionally mislabeled on plan type (Fidelity states 403(b), per
DEF-ACCOUNT-LABEL-DUP).

**Do not** propagate this to `account_balances` — the space-vs-underscore split lives there
and binding condition 7 bars touching that table. Note this recommendation does not resolve
DEF-ACCOUNT-LABEL-DUP; it only picks a write target.

---

## BLOCKERS — one cleared, one outstanding

1. ~~**Authorization not granted.**~~ **CLEARED** by R-IV.84(c), 2026-08-25. All eight
   binding conditions confirmed as written.
2. **Segmenter script not supplied — STILL OUTSTANDING.** R-IV.84(c) fixes the division of
   labour: *"Segmenter script authored by POSITIONS, run and validated by CC-POSITIONS"* —
   Item 10's reproduce-don't-trust pattern. Re-checked at tree `8b2d767` after a fresh
   fetch: `data/imports/` holds only the original five files (source CSV, normalizer, and
   its three outputs); `scripts/` has no match (`fix_ibit_call_roundtrip.py` is unrelated,
   IBIT options). **This blocker is not CC-POSITIONS' to clear** — hand-building the
   segmentation is forbidden by the Phase 1a brief and would destroy the derivation of
   record the pattern depends on.

### Ready-on-arrival: the validation plan

The moment the script lands, execution is: re-fetch and re-stamp the tree SHA → run the
script → diff its output against expectation, namely (i) ~25–30 trade rows from 83 fills,
(ii) per-ticker sums matching the seven validated reference totals **except XLE**, which
must fall short by the UNKNOWN-basis trade (see the tension section above), (iii) zero rows
violating the ETF-only invariant, (iv) `fill_hash` idempotency proven by a second run being
a verifiable no-op → then census-first write with per-row preimage/postimage under
`FIDELITY_ROTH`.

## Standing items carried in

- **`SBU`** — still unconfirmed as an ETF; the principal has not answered. Its only row is
  `POS_SBU_20260429_031106`, CLOSED 2026-04-29, **outside this window**, so it cannot be
  touched by Phase 1a. Flag carried, no action available.
- **GUSH quantity RESOLVED by this brief** — Phase 0b left it UNKNOWN (30 or 90). The brief
  supplies **30 sh @ mark $43.86**, so the pre-window balance was 0. This means the live DB
  row `POS_GUSH_20260609_232044` (OPEN, **qty 60**, FIDELITY_ROTH) is wrong on quantity.
  Correction is **out of scope** here; recorded for the lane that owns it.
- **`WRTH` 20 sh @ $25.815** — no `unified_positions` row on any status. Coverage absence
  confirmed at this pin.
- **7 unsettled 08-24 fills excluded** per condition 6. They will alter GUSH and the final
  SOXS exit.
- **`id 347` zero-basis defect re-confirmed at this pin**: `cost_basis = 0` (literal zero,
  not NULL) alongside `realized_pnl = +53.90`. This is the pattern condition 1 bars.

---

## Manifest (law v2)

| Scope | Rows | Fingerprint |
|---|---|---|
| Fidelity-side `unified_positions`, all dates | **46** | `db0d0231c62cc4fa49453253a425f1a5` — preimage baseline, 0 rows in window |
| `unified_positions` total | **329** | unchanged since Phase 0 census |
| In-window rows on the 9 CSV tickers, any account | **11** | 8 equity (hazard) + 3 XLE option (safe) |
| `fidelity_ACCT-ROTH_fills_normalized.csv` | **83** | 83 unique `fill_hash`, 0 collisions |
| `fidelity_ACCT-ROTH_cash_events.csv` | **11** | — |
| Reference totals validated | **7 / 7** | Σ +$1,094.38, delta ±$0.00 |

**No writes, no migrations, no schema changes, no allowlist edits. Nothing staged.**
