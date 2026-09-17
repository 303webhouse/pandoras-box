# DEF-SHADOW-EXPIRES-AT-DROPPED — P2

**Registered:** R-IV.430(c). **Found:** 2026-09-17, CC-BUILD, while building CIRCE'S STEW
(R-IV.429(b)). **Status:** OPEN — **not to be fixed yet** (see DISPOSITION).
**Row count:** CC-QUERY, when next free. **Code-path facts below:** read from source by
CC-BUILD at d990abb; no database was read for this entry.

---

## THE STATEMENT

> **A shadow emitter builds an expiry; the insert has no column for it; the value is
> discarded without a trace.**

## WHAT THE SOURCE SHOWS

- `jobs/strike_ib_converter.py` — binding condition 6: *"expires_at = entry session + 3
  trading sessions. Promotion-gate analysis treats outcome_resolved_at > expires_at as
  EXPIRED, not WIN/LOSS."* `compute_expires_at()` computes it and `build_signal_data()`
  puts it on the signal dict.
- `database/postgres_client.py::log_signal` — the `INSERT INTO signals` column list has
  **no `expires_at`**. The key is never read.
- No other writer sets `signals.expires_at` on these rows. Searched: every `expires_at`
  occurrence under `backend/` outside tests; the only INSERT naming it writes
  `pending_trades`, not `signals`.

So every STRIKE shadow row is expected to carry `expires_at` NULL. **That the rows ARE NULL is a
database fact and is CC-QUERY's read** — this entry states only what the code does.

## WHY IT MATTERS

**Binding condition 6 cannot operate.** A rule of the form "resolved after expiry is EXPIRED"
reads NULL as *no expiry*, so a late resolution is graded WIN or LOSS — **the exact
outcome the condition exists to prevent**, and one that looks like an ordinary grade.

It is the same family as the two drops already fixed at this insert — `source` ($37,
DEF-SIGNAL-METADATA) and the Pass 9 evidence (R-IV.423(b)): **a producer sets a field, the
writer does not name it, and nothing says so.**

CIRCE'S STEW does not set `expires_at` and does not depend on it; its grading horizon belongs
to the backtest module.

## DISPOSITION — R-IV.430(c)

**Do not fix yet.** Persisting `expires_at` changes STRIKE's grading data, so it moves **with
the backtest module**, which is where the grading horizon and the EXPIRED rule get defined.
Rows already written cannot be repaired from the row: the expiry would have to be recomputed
from the entry session under the rule the backtest module fixes, and stated as recomputed.
