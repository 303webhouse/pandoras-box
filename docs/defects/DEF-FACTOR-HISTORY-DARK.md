# DEF-FACTOR-HISTORY-DARK · P2

**Found** 2026-09-05 by CC-BUILD, while verifying a claim in CC-QUERY's Moby Dick census
rather than restating it. **Status:** OPEN. **Not previously registered** — the name appears
in `docs/edge/results/QS-01-RESULTS.md` and `docs/session-handoff.md`, but no defect artifact existed.

---

## Measured

**CC-QUERY, census vintage 2026-09-06 00:11:34Z:** `factor_history` holds **0 rows** for
`dxy_trend`, and **the table's last write of ANY factor was 2026-07-23**.

That is **44 days dark at the time of this filing**, across every factor, not one.

## Code side — this lane's contribution, and it narrows the cause

**The table has exactly two writers, both reachable, both in `backend/api/bias.py`:**

| writer | site | reached by |
|---|---|---|
| `persist_savita_reading` | `backend/api/bias.py`:104 → :143 | the scheduled Savita read |
| `update_factor_from_pivot` | `backend/api/bias.py`:673 → :717 | `POST /bias/factors/{factor_name}` — **a POST from Pivot on the VPS** |

**So the table is not dark because nothing writes to it. It is dark because neither writer
has fired in 44 days**, and one of the two is a cross-host push from the VPS. **That
relocates the question from the hub's schema to the VPS→hub factor path**, which is a
different subsystem and a different owner.

## The failure is swallowed by construction

`_log_factor_history` (`bias.py:875`) wraps its INSERT in a try/except whose entire failure path is:

```
logger.warning(f"Failed to log factor history for {factor_id}: {exc}")
```

**A warning is not an alarm and nothing reads it.** If the writes were being attempted and
failing, the evidence would be a log line in a 500-line rolling buffer, days ago, and
nowhere else. **This is why 44 days passed without notice**, and it is the same shape as
the working-fallback in `DEF-UW-OHLC-DEAD` and the compute-then-discard family: the system
continues, so nothing asks.

## Why P2, not P1

**Nothing sizes off `factor_history` today**, and the one consumer that would have — Amendment 1's
S2 DXY-trend stratum — **was routed away from it before this was filed**: the census found
`dxy_trend` empty, so S2 declares a **UUP proxy from `stable_daily_bars`** instead. **The registration
was saved by the census, not by the alarm**, which is the part worth keeping.

**It is not P3 because the table's purpose is history.** Whatever the bias engine was
computing between 07-23 and now, **it is not recoverable** — a factor series has no
backfill, and 44 days of it are simply gone.

## Not determined here

Why the writers stopped; whether the VPS Pivot push is erroring, disabled, or never
scheduled; and whether the Savita path shares the cause or has its own. **All read-only,
all outside this lane's tree** — the VPS half is not in this repo.
