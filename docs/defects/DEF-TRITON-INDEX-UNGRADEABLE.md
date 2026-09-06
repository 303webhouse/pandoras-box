# DEF-TRITON-INDEX-UNGRADEABLE

**Class:** coverage / classification — an instrument class that can never be graded is
carried as unresolved backlog
**Severity:** **P2** — assigned by spine at R-IV.265(d). *(Stubbed UNASSIGNED on
2026-09-05: no severity appeared in any citing document; assignment discharged same day.)*
**Status:** **OPEN · ONGOING** — new ungradeable rows keep arriving
**Surface:** `triton_flow_shadow` — the grader's ungraded queue, and every count derived
from it
**Stubbed:** 2026-09-05 per R-IV.262(b), from citing documents only. **No new
investigation was performed for this stub.**

**First citation:** `docs/codex-briefs/2026-09-01-triton-handoff-to-olympus.md:36`

## What is known

Five cash-settled index symbols — **SPX · SPXW · RUT · RUTW · VIX** — have **no price
series** available to the grader. Without a series the grader can compute neither
`prior_5d_ret` at fire time nor `fwd_ret_*` at grade time: one missing input, two symptoms.

Measured population, table-wide (90 rows total):

| bucket | rows |
|---|---|
| pre-08-17 residue | **72** |
| inside the pinned holdout (`k`) | **15** |
| future cohort (`id > 377783`) | **3** |

- **0 of 72** residue rows have ever been graded, and **all 72** carry `prior_5d_ret IS NULL`.
- Per-symbol inside the pin: SPX 6 · SPXW 6 · RUTW 2 · VIX 1 · RUT 0 = **k = 15**.
- **Effective validation n = 843 − 15 = 828** (holdout registration, §5).

**Two second-order effects on the grader**, both consequences of these rows sitting
permanently at the head of the ungraded queue:

- `lookback_days = (today − earliest).days + 12` anchors `earliest` at **2026-07-02**, so the
  per-ticker bar window **grows by one day every day, without bound** (74 days × 337 tickers
  on 09-02).
- `GRADE_LIMIT = 1000` with `ORDER BY fired_at ASC` means these rows occupy the **first 72
  slots of every pass, permanently.**

## What is FALSIFIED — do not re-derive these

Registered explicitly as dead so they are not rediscovered:

- that these rows are **stalled backlog** — they are permanently ungradeable, not late
- that **grader remediation clears them** — DEF-TRITON-GRADER-DARK's fix does not and cannot
- that **"holdout fully graded" is a reachable state** — 15 of 843 never grade, so any
  completion monitor keyed to it waits forever
- that the **residue is a random sample of ungraded rows** — it is predominantly this class
- that **`liquidity_bucket = 'index'` is the same population** — that is a *liquidity tier*
  (QQQ, SPY, NVDA, SMH, META, MSFT…), fully graded at 1,881 rows, and unrelated

## Fix direction, as recorded in the citing documents

Classify at ingest as **UNGRADEABLE-NO-SERIES** so these rows stop reading as stalled
backlog; completion monitors then target the gradeable subpopulation.

## Lineage

Cited in **5 documents**, on **5 lines** (counts stated separately per R-IV.262(c)):

- `docs/codex-briefs/2026-09-01-triton-handoff-to-olympus.md:36`
- `docs/defects/DEF-TRITON-GRADER-DARK.md:54`
- `docs/edge/results/2026-09-02-triton-k-capture-and-burn-sweep.md:65`
- `docs/handoffs/BOOK-CLOSING-HANDOFF.md:276`
- `docs/strategy-reviews/2026-09-03-triton-rescope-proposal.md:60`
