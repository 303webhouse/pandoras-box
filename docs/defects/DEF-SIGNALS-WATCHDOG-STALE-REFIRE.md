# DEF-SIGNALS-WATCHDOG-STALE-REFIRE

**Severity:** P2 (facet 3 may warrant P1 — severity left to spine)
**Filed:** 2026-08-24 · **Status:** OPEN
**Surface:** `backend/main.py` → `signals_freshness_watchdog_loop()` (~:505)
**Origin:** found while answering R-IV.53(c), the owed line on the heal predicate.
**Parent:** DEF-SIGNAL-PERSISTENCE-COLLAPSE (the instrument this defect degrades
was built by 073395f to close that P0).

## R-IV.53(c) answered first: the heal predicate is CORRECT

Spine asked whether the heal requires the FIRING conditions resolved (dark classes
producing) or merely rejection-quiet, and ordered a defect filed if it were the
latter.

**It is the former. There is no false-heal path.** The heal branch is
`elif episode_open or latched`, reachable only when `new_rejections` is empty AND
`stale_bad` is empty. `stale_bad = dark_now - baseline_dark`, and `baseline_dark`
is only ever *shrunk* (`baseline_dark -= (set(classes) - dark_now)`), never grown
after the first look. So a class that fired for darkness stays in `stale_bad`
until it actually persists a row and its age drops back under SLO.

Confirmed on the live day-0 episode: FIRED 2026-08-21T13:33:00Z for `footprint`
and `tradingview`; both produced rows (13:45:05, 14:10:37) before CLEARED at
14:23:01Z. Recovery, not quiet.

**Cosmetic rider, also answered — and it is worse than cosmetic.** See facet 2.

## The defect: the same predicate is wrong in the inverse direction

The heal is correctly strict. The **fire** is not: the staleness arm is
level-triggered where the rejection arm is edge-triggered.

### Facet 1 — staleness re-pages every LATCH_TTL, forever

`new_rejections` is a delta (edge). `stale_bad` is a set membership (level). Once a
class is dark and outside `baseline_dark`, `stale_bad` is non-empty on **every**
cycle. The Redis latch suppresses re-fires for `LATCH_TTL = 7200`, then expires,
and the alarm fires again identically. Forever, until the emitter recovers.

Observed, still running at filing time — 11 identical Discord pages at exactly
2-hour intervals:

```
2026-08-23T18:58:30.392 ERROR:main:Signal persistence alarm FIRED: crypto_scanner: no data (age=43276s)
2026-08-23T20:58:30.357 ERROR:main:Signal persistence alarm FIRED: crypto_scanner: no data (age=50477s)
2026-08-23T22:58:32.320 ERROR:main:Signal persistence alarm FIRED: crypto_scanner: no data (age=57678s)
2026-08-24T00:58:34.279 ... 02:58:37 ... 04:58:40 ... 06:58:42 ... 08:58:41 ...
2026-08-24T10:58:37.911 ... 12:58:42.397 ... 14:58:38.639  (age=115287s)
```

`send_alert()` posts to Discord, so these are 11 embeds in Nick's alerts channel
for one standing condition.

This is the exact anti-pattern the function's own docstring says it was built to
avoid, on the arm the docstring does not cover:

> "a cumulative gap never returns to zero within a process lifetime, so it would
> re-fire every latch-TTL forever and make recovery unreachable. **A permanently-
> crying alarm gets muted, which restores fake-healthy by another route.**"

The delta was applied to rejections and not to staleness. Muting is the predicted
end state, and muting reinstates fake-healthy — the defect class the parent P0 exists
to prevent.

### Facet 2 — the fire text has been wrong on 100% of firings

The fire line renders `f"{c}: no data (age=...)"` for every member of `stale_bad`.
But `stale_bad` admits both `flatline` (age exceeds SLO) and `no_data` (age IS
None), and `no_data` is a distinct status term in the same instrument.

Every firing to date carried a real age — `footprint` 64966s, `tradingview` 34267s,
`crypto_scanner` 43276s and up — so every one was `flatline`, and every one was
labelled "no data". Meanwhile the CLEARED line's `worst=no_data` refers to the
genuinely-`no_data` classes (`crypto_engine`, `crypto_cvd_engine`).

Same episode, same string, two meanings. A reader triaging the 08-21 page would
conclude `footprint` had never produced, when in fact it had produced 18 hours
earlier. Not cosmetic: it misdirects triage.

### Facet 3 — boot-dark adoption launders a live outage across a deploy

`baseline_dark` is adopted at the first look of each process and never re-armed.
It was designed so a class dark for weeks (`crypto_engine`, last row 07-22) does
not page on history at every restart. But it does not distinguish *history* from
*a live, unresolved outage that happens to straddle a deploy*.

A push to `main` auto-deploys and restarts the process. Any emitter that died
before the restart is adopted as baseline and **never pages again**, at any age,
for the life of that process. Since deploys are frequent, the dead-man's switch
effectively only catches deaths noticed within a single deploy cycle.

**DEMONSTRATED ON PRODUCTION, not argued.** The R-IV.53 Wave 1 docs push
(`703df75`) auto-deployed as `d5c8fc44`, SUCCESS 2026-08-24T16:26:48Z. The new
process's first watchdog look:

```
2026-08-24T16:31:23.188 INFO:main:Signals watchdog baseline-dark at boot (not paged):
    crypto_cvd_engine, crypto_engine, crypto_scanner
```

`crypto_scanner` — dead 33.5 hours, and paging every 2 hours across the 20 hours
immediately prior — was adopted as baseline and **will not page again for the life
of this process**, at any age, while still dead.

The record survived; only the alarm was laundered. `/health` after the restart
still reports it truthfully:

```
overall: degraded   worst_status: flatline   any_flatline: True
  crypto_scanner    flatline   p=0 r=0 gap=0 age=120858
```

That is the exact scope of the defect: `/health` is the RECORD and stayed correct;
the watchdog is the ALARM and went silent on a live, unresolved outage. The build
that closed the parent P0 reasoned that a record with no reader is a fake-healthy
seam, which is why the watchdog exists. Facet 3 restores that seam whenever an
outage straddles a deploy — the reader stops reading, and only the unread record
is left.

A deploy is also what resets the counters: all classes returned `p=0` after the
restart, so `persisted`/`rejected`/`deduped` are per-process and any cumulative
claim must first prove process continuity (done for `d2cfc3f4` via a monotonic
176 -> 324 counter walk before this restart).

## Not implicated

`rejected = 0` and `reconciliation_gap = 0` for every class across the full
83.5-hour deploy life of `d2cfc3f4` / `073395f`. `crypto_scanner`'s last pipeline
call was a clean success (`✅ Pipeline complete: NEAR-USD ... in 769.1ms`,
2026-08-23T06:57:14Z) followed by silence — no INSERT was attempted and rejected.
This is **upstream emitter death, not persistence failure.** The 073395f fix is
not implicated; the instrument correctly distinguished the two, which is why the
finding is legible at all.

## Proposed fix (not built — queued behind T8 per R-IV.53(g))

1. **Edge-trigger the staleness arm.** Keep `paged_dark: set[str]`; fire only on
   `dark_now - baseline_dark - paged_dark`; then `paged_dark |= newly_dark` and
   `paged_dark &= dark_now`, so a class that recovers and re-darkens pages again.
   The heal predicate keeps testing the full `dark_now - baseline_dark`, so
   Facet-1's fix cannot introduce the false-heal spine asked about.
2. **Render the class's real status term** in the fire text instead of the literal
   "no data".
3. **Distinguish history from a straddling outage.** Persist the dark set to Redis
   at each cycle; at boot adopt as baseline only classes that were *already dark at
   the previous process's last observation*. A class that was healthy before the
   restart and is dark after it is a transition and must page.

Facet 3 is the one that most undermines the instrument, and is why the severity
ruling is left open.

## Verification requirement

Each fix needs a discriminating pre-fix failure (null-verifier law). Facet 1 and 2
are unit-testable against the pure predicate. Facet 3 requires a two-process test
— dark set persisted, process restarted, page asserted — not a single-process
assertion, which could not fail.
