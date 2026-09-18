# DEF-KILLSWITCH-LATCH — the breaker's clear never reached the store its arm wrote to

**Registered:** R-IV.455(e). **Found and disarmed:** CC-BUILD, 2026-09-18, during market hours.
**Status:** DISARMED 17:55:58 UTC (13:55 ET) through the operator path; mechanism FIXED.

> **A safety device that cannot clear is not conservative, it is broken in the other
> direction.** It read ACTIVE for about 47 hours on a condition its own check had cleared two
> days earlier — and a kill switch that is visibly wrong teaches the principal to ignore it,
> which is worse than having none.

---

## WHAT WAS MEASURED

| reading | value |
|---|---|
| trigger | `spy_down_1pct` (TradingView alert) |
| fired | **2026-09-16 19:11:50 UTC** (Wed 15:11 ET) — not today |
| pending reset since | **2026-09-16 23:19:58 UTC** — timer elapsed AND recovery condition cleared that evening |
| persisted record | `bias:circuit_breaker`, armed, **no expiry** |
| provenance at the call | `restored-at-boot` — re-armed from Redis on every restart |
| SPX at ~12:11 ET 09-18 | 7,621.76, **−0.20%** (R-IV.455(a)) |

**Of the three candidates, it was the LATCH.** Not a stale reference (the hub computed nothing
at fire time), and not drawdown semantics on today's session (it had not fired today).

## THE MECHANISM

1. **Arm persists forever.** An armed record is written with no expiry, by design (R4,
   DEF-KILLSWITCH-TTL-RESTART: an armed breaker must not expire into silence).
2. **The daily clear did not persist.** `reset_circuit_breaker_scheduled` (09:30 ET) reset
   in-memory state only. The armed record stayed in Redis.
3. **Every restart re-armed it.** `restore_circuit_breaker_state()` reloads the record at boot.
   About ten deploys on 09-18 each restored the 09-16 fire.
4. **`pending_reset` waited on a human** — an accept on a surface the principal may not use,
   announced over a notification path that ran through a host now retired.

So nothing cleared it except the operator endpoint: **not a restart (it re-arms), not the daily
reset (memory only), not the recovery check (which had already passed and only moved it to
pending).**

## WHAT IT SUPPRESSED WHILE ACTIVE

**Nothing in the reported bias.** All 265 composite readings between the fire and the disarm
were NEUTRAL, scores −0.135 to +0.070. The `MINOR_TORO` cap binds only at ≥ 0.60 and was never
reached. The 0.9 scoring modifier dampened positive scores while unfaded — about five hours on
09-16 — without moving any reading across a band.

**What it did do: it displayed ACTIVE** — on the board, the kill-switch endpoint, and to every
consumer of board state — for ~47 hours after its own condition cleared. The harm is a false
signal, not a changed number.

## ONE THING NOT ESTABLISHED

For a period on 09-18 the composite payload carried a different state — `triggered_at`
2026-09-18T17:44:46Z, not pending, modifier 0.9 — while the persisted record and the serving
process both held the 09-16 latch. The logs that would say what produced it belong to deployments
that are no longer retrievable. After the disarm both surfaces agree: inactive. **Recorded as
unexplained rather than attributed.**

## WHAT SHIPPED

- **The scheduled reset persists**, so the clear reaches the same store the arm did. A breaker
  now clears at each market open unless it fires again.
- **A fire carries its evidence (the vintage rule).** TradingView sends a trigger *name*; the
  hub now takes its own reading of SPY against its prior close — price, prior close, percentage,
  vendor, method, time — and writes it into the state and the description. A fire the hub's
  reading does not confirm is marked **`disputed`**; a reading that cannot be taken says so and
  is neither. **Recorded and flagged, not rejected**: refusing to arm on a disagreement changes
  what the safety device does, and that is a ruling.
- **The board shows how long a latch has waited** — trigger age, pending age, the hub reading,
  and the dispute flag.
- **Also fixed on the way:** the recovery check's primary path read `prev.get("c")` from a
  payload shaped `{"results": [...]}`, so it never computed anything and always used its
  fallback.

## OPEN, FOR RULING

- Whether a **disputed** fire should arm at all.
- Whether `pending_reset` should resolve on its own after a bound, rather than waiting
  indefinitely for an accept.
- The TradingView alert's own comparison — prior close, session open, or intraday high — lives
  in the Pine script, not in this repository, and cannot be read from here.
