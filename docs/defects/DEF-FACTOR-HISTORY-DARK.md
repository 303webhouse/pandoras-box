# DEF-FACTOR-HISTORY-DARK · ~~P2~~ — SEVERITY IN QUESTION, see the correction

> ## CORRECTED FROM THE FILED READ — R-IV.331(b) / R-IV.336(c). THIS FILE CITED THE WRONG
> ## TABLE.
>
> **Source: `docs/edge/results/2026-09-08-factor-history-read.md` (`192f134c`), CC-QUERY, vintage 2026-09-09 02:30:57Z.**
>
> ```
> factor_readings          327,828 rows   last write 2026-09-09 02:20:54   11,654 in 7d   28 factors   ALIVE
> bias_composite_history    32,614 rows   last write 2026-09-09 02:20:56      851 in 7d                ALIVE
> factor_history             4,507 rows   last write 2026-07-23 08:00:00        0 in 7d    8 factors   DEAD
> bias_history                   0 rows   —                                                           EMPTY
> ```
>
> **`factor_history` IS A STALE DUPLICATE. `factor_readings` IS CANONICAL AND WRITING** — 25× larger,
> differently named, and never probed by either lane until this read.
>
> ### What is WITHDRAWN from this file
>
> **The consequence claim.** This file said *"44 days of factor history have no backfill and
> are simply gone."* **FALSE.** `factor_readings` holds that history — 11,654 rows in the last
> seven days alone. **Nothing was lost.**
>
> **And the P2 justification went with it.** The severity rested on *"the table's purpose is
> history"* and on that history being unrecoverable. **Neither holds.** Severity is spine's
> to set; this lane will not quietly keep a P2 whose stated reason is withdrawn.
>
> ### What SURVIVES, narrowly
>
> **`factor_history` really is dark since 2026-07-23**, and the code-side finding stands: its only
> two writers are `persist_savita_reading` and `update_factor_from_pivot` behind a cross-host POST from Pivot, and its failure
> path is a swallowed `logger.warning`. **All of that is true of a table that should be retired.**
>
> **The precise fact:** `factor_history` and the `excess_cape` factor both stop at exactly
> `2026-07-23 08:00:00.501827`. **They are one series written to two places, and that series
> died.** The table did not go dark independently — it went dark because its last writer did.
>
> ### The error this file made, which is the same one twice over
>
> **A property of ONE TABLE was reported as a property of THE SURFACE.** CC-QUERY owns the
> original miss and says so on their artifact; **this lane repeated it** — the Moby Dick
> census said *"factor_history is dark"*, and this file turned that into *"factor history is
> dark"* without probing for a differently-named table.
>
> **That is conventions #10 in its other form:** a negative is a property of where you
> looked. **Here the search space was table NAMES, and one name was searched.**



**Found** 2026-09-05 by CC-BUILD, while verifying a claim in CC-QUERY's Moby Dick census
rather than restating it. **Status:** OPEN. **Not previously registered** — the name appears
in `docs/edge/results/QS-01-RESULTS.md` and `docs/session-handoff.md`, but no defect artifact existed.

---

## Measured

**CC-QUERY, census vintage 2026-09-06 00:11:34Z:** `factor_history` holds **0 rows** for
`dxy_trend`, and **the table's last write of ANY factor was 2026-07-23**.

That is **44 days dark at the time of this filing**, across every factor, not one.

**The last factor written was `excess_cape`** (census §(b)). The composite itself lives at
`backend/bias_engine/composite.py:134` and is described as *"DXY 5d trend + SMA20 context +
VIX interaction"* — **it is computed, and it was never persisted per row**, which is a
second finding sitting underneath the first: even a live `factor_history` would not have
carried a per-row DXY stamp.

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
