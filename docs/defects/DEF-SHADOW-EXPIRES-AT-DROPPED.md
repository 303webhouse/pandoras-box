# DEF-SHADOW-EXPIRES-AT-DROPPED — P2

**Registered:** R-IV.430(c). **Found:** 2026-09-17, CC-BUILD, while building CIRCE'S STEW
(R-IV.429(b)). **Status:** RESOLVED — both halves (SHADOW rows with 2bc8a59; every row by R-IV.432(f)).
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

## RESOLUTION

**Half 1 — SHADOW rows (2bc8a59, with the backtest module).** A separate write after the insert,
SHADOW only, while the live half waited for its ruling.

**Half 2 — every row (R-IV.432(f): "fix it, announce the change on the River").** The INSERT
now names `expires_at` ($39), and the separate SHADOW write is gone. A value that cannot be read
is stored as NULL -- the old behaviour -- and logged; it never fails the INSERT.

### What the pipeline computes, and one mapping it got wrong

`calculate_expiry`: intraday 4 hours, 4-hour and daily charts 24 hours, weekly 7 days, anything
unrecognised 4 hours. **TradingView sends intraday intervals as minute counts** (`"60"`,
`"240"`), and the lists never matched a number, so a **4-hour chart fell to the 4-hour
default** instead of 24. Harmless while nothing was stored; wrong the moment it is. Minute
counts are now read as minutes: >= 240 -> 24 hours, >= 10080 -> 7 days, otherwise 4.

### What changes on the live surfaces — stated before it lands

| surface | before | after |
|---|---|---|
| flat feed `/api/trade-ideas?status=ACTIVE` (the River, Kairos) | every row passed `expires_at IS NULL` | an intraday idea drops out 4 hours after it fired |
| expiry sweep (every 5 min) | ACTIVE rows expired at `created_at + 24h` | at their own expiry; the 24h fallback remains for rows with none |
| a user action on an expired idea | possible for 24 hours | refused as terminal after the expiry (`EXPIRED` was already terminal) |
| legacy `/api/signals/active` (the old UI) | hides a ticker for 24h after a dismissal | unchanged rule, but the sweep's `DISMISSED` now lands 4h after an intraday fire, so **a fresh same-day idea on that ticker is hidden there** until the 24h passes |
| CTA scanner cooldown (`has_recent_active_signal`) | — | **unchanged**: CTA rows are `DAILY` (24h) and carry no pipeline expiry |
| SHADOW rows | not on ACTIVE surfaces | unchanged |

The legacy-UI effect is the sweep's existing choice to record a system expiry as
`user_action = 'DISMISSED'`; it is reported, not changed here.

**Announced on the River:** `GET /api/trade-ideas/notices` carries the notice from the deploy
day for two weeks, for CC-ABACUS to render.
