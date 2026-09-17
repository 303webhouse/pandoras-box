# DEF-SHADOW-EXPIRES-AT-DROPPED — P2

**Registered:** R-IV.430(c). **Found:** 2026-09-17, CC-BUILD, while building CIRCE'S STEW
(R-IV.429(b)). **Status:** FIXED FOR SHADOW ROWS with the backtest module (see RESOLUTION);
**the wider drop below is OPEN and needs its own ruling.**
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

## RESOLUTION — with the backtest module (R-IV.429(b))

`log_signal` now writes `expires_at` **for SHADOW rows only**, by a separate statement after a
real insert (`_write_shadow_expiry`), so a failure there cannot lose the signal. STRIKE rows
written from this deploy onward carry their expiry; rows already written stay NULL and are not
back-filled.

## THE DROP IS WIDER THAN STRIKE — OPEN, needs a ruling

The entry above says no other writer sets `signals.expires_at`. **That is true of STRIKE's rows,
and it understates the defect.** `signals/pipeline.py` sets
`signal_data["expires_at"] = ... or calculate_expiry(signal_data)` for **every** signal that goes
through `process_signal_unified` (4 hours intraday, 24 hours swing, 7 days weekly), and the same
INSERT discards all of them.

**The live feed has been running on that absence:**
- the flat feed's ACTIVE filter is `expires_at IS NULL OR expires_at > NOW()`, which every live
  row passes;
- `/api/trade-ideas/expire` falls back to `created_at + 24 hours` when `expires_at` is NULL.

So an intraday signal the pipeline meant to expire after 4 hours stays on the ACTIVE surfaces
for 24. **Persisting the value for ACTIVE rows would change what the live feed shows, and for how
long.** That is a live-surface decision, so this fix is scoped to SHADOW rows and the rest is left
as found. Source-read facts; how the live feed's contents would change is a CC-QUERY read.
