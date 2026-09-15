# `outcome_resolver` and `flow_per_expiry` — both reads, and both contradict a comment

**CC-BUILD, 2026-09-14. R-IV.380(b).** Same session, code reads only.

**Neither caller is what the governor's table said it was**, and in both cases the
table was sized from a comment rather than a measurement.

---

## 1. `outcome_resolver` — THE TAG NAMES A JOB, NOT AN ENDPOINT

### What it is

**One call site, and it is not in the outcome resolver.**

```
jobs/crypto_bars.py:75
  await uw_api._uw_request(f"/api/crypto/{pair}/ohlc/{candle_size}",
                           params={"limit": limit}, caller="outcome_resolver")
```

**It is a CRYPTO OHLC fetch** — `/api/crypto/{pair}/ohlc/{candle_size}`, `limit=500` —
wearing the name of the job that happens to call it.

`jobs/outcome_resolver.py:196` calls `fetch_crypto_bars(...)`, which reaches
`_fetch_uw_bars_full`, which issues the request. **The resolver never touches UW
directly.**

### Why it is the largest hub caller

**Per resolved signal, per pair, per candle size, 500 bars a call.** 2,764 requests by
13:52 ET today — 23.6% of hub spend. It is the highest-volume endpoint the hub uses, and
nothing about the name says so.

### AND IT VIOLATES THE TAGGING CONVENTION — which is why it was never in the table

`uw_api_cache.py:115` states the rule in the code that maintains the counters:

> *"`caller` is an **endpoint-grain** tag (e.g. `"snapshot"`, `"flow_per_expiry"`,
> `"ohlc"`)"*

**Every other tag names an endpoint. This one names a consumer.** So when the quota table
was written by walking the endpoints, this caller was not among them — **it was invisible
to the exercise that produced the table**, and fell through to `DEFAULT_QUOTA = 500`, the
allowance meant for unknown code paths.

**It is not a rogue caller. It is a correctly-working one that the naming scheme could not
see.**

### The fragility that outlives the fix

**Today `outcome_resolver.py` is the only consumer of `fetch_crypto_bars`, so the
attribution is accidentally accurate.** The moment a second consumer appears — the crypto
engine, tape health, a backtest — **its spend is silently attributed to the outcome
resolver**, and the budget line for one job starts absorbing another's.

### Budget line

**`"outcome_resolver": (4500, TIER_STANDARD)`** — measured 2,764 at 13:52 ET, projecting
~3,705 for the quota day, sized ×1.2.

**RENAME RECOMMENDED, NOT TAKEN TODAY.** The correct tag is endpoint-grain —
`crypto_ohlc`. **Renaming resets the counter to zero and breaks the continuity of the
measurement spine asked for at the close**, which is the same objection filed against
renaming the grader's skip reason. **Do it after the close or Tuesday**, with the old key
kept in the table for one day so the budget does not vanish mid-session.

---

## 2. `flow_per_expiry` — THE POLLER IS RUNNING AND ITS OUTPUT IS CONSUMED

**The comment is wrong. Per R-IV.380(b): fix the comment.**

### It is running

```
main.py:882   uw_flow_poller_task = asyncio.create_task(uw_flow_poller_loop())
main.py:399   async def uw_flow_poller_loop():        every 300 s
main.py:409       if et.weekday() < 5 and 9 <= et.hour < 16:
                      await run_flow_poller()          self-gated to RTH
jobs/uw_flow_poller.py:47   flow_data = await get_flow_per_expiry(ticker)
uw_api.py:1001              caller="flow_per_expiry"
```

**Started at boot, polls every five minutes, weekday-gated to 09:00–16:00 ET.**

### Its output is consumed — three ways

- **`api/flow_radar.py:115`** imports `build_flow_summary` from the poller;
- **`api/board_state.py:80`** reads `uw:flow:{ticker}`, *"written by
  `jobs/uw_flow_poller.py`, 900s TTL"*;
- it writes **`flow_events`**, which `main.py:878-881` says *"restores the flow_events
  feed for pipeline P2C / wh_confluence / committee briefings."*

**Not consumed → stop it. Consumed → fix the comment. It is consumed three ways.**

### Where the wrong belief came from, and what it cost

**There are TWO flow-polling loops, and only one is disabled.**

```
bias_scheduler.py:~2886   # asyncio.create_task(_uw_flow_polling_loop())
                          # "UW flow polling loop DISABLED (L1.0 Path A ...)"   <- commented out
main.py:882                 asyncio.create_task(uw_flow_poller_loop())          <- LIVE
```

**The governor's comment — *"uw_flow_poller (deactivated) — standby reclaimed 500→100"* —
names the disabled one and sizes the quota of the live one.** Its budget was cut to
**100** on the strength of that belief while it spent **1,640**.

**And the system already recorded the right number somewhere else.** `main.py:878-880`
says the poller makes **"~1,680 UW calls/day"** — within 3% of Friday's measured 1,640.
**One file documented the real usage while another asserted the caller was off.**

### Budget line

**`"flow_per_expiry": (2000, TIER_STANDARD)`** — matching the ~1,680 its own docstring
states, not the 100 a stale comment justified.

---

## The shape both share

> **A QUOTA SIZED FROM A COMMENT IS SIZED FROM WHAT SOMEBODY BELIEVED, NOT FROM WHAT THE
> SYSTEM DOES.**

**Both entries would have blocked a working caller on the first day of enforcement** — one
because the naming scheme could not see it, one because a comment described a different
object with a similar name. **Neither was discoverable by reading the table; both were
obvious the moment the table was checked against a measurement.**

**The retune's arithmetic is now asserted by a test rather than stated in a comment, for
exactly this reason.**
