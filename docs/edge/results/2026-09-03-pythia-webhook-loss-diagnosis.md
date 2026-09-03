# R-IV.228 — PYTHIA WEBHOOK-LOSS DIAGNOSIS

**Ordered:** R-IV.228, read-only, **before any alert-recreation order issues.**
**Run:** 2026-09-03 by CC-BUILD. **No writes. No prescription — see the ruling section.**

---

## HEADLINE — THE FEED HAS LOST 97% OF ITS UNIVERSE, AND THE ALARM HAS BEEN FIRING THE WHOLE TIME

```
tickers that ever fired into pythia_events   212
alive today (fired 2026-09-03)                 6    AMD AMZN IWM RKLB SPCX SPY
liquid-20 roster still alive                   4 of 20
Redis latches currently set on alarm:pythia_stale:*   16
```

**The detection instrument is not missing, is not broken, and is not silent.** It is
firing, correctly, on the right roster, and has been for weeks. **What failed is the
step after the alarm.**

---

## 1 — THE COLLAPSE, MEASURED

Feeds ending, by session:

| session | feeds ended | session | feeds ended |
|---|---|---|---|
| 07-27 | **39** | 08-04 | **25** |
| 07-28 | **39** | 08-05 | 8 |
| 07-29 | 12 | 08-06 to 08-28 | ~16 trickle |
| 07-30 | **20** | 08-31 | 1 (CRWV) |
| 07-31 | 11 | **09-01** | **2 — QQQ, SMH** |
| 08-03 | 13 | 09-03 | 6 still alive |

**167 of 212 died in the ten sessions 07-27 to 08-05.** The rest trickled out over the
following month. SPEC-01's "five dark tickers" are **five of two hundred and six
casualties** — recreating five alerts treats a symptom of a feed-wide failure.

## 2 — (b) DEPLOY CROSS-REFERENCE: NOT DEPLOY-CAUSED

**The Railway deployment list retains only 20 entries, reaching back to 09-02 15:11 ET.**
It cannot see 07-27 to 08-05, and it cannot see 09-01. A "no deploy near the failure"
result computed from it would be **vacuous** — the probe could not have found one either
way. Git history is complete and was used instead.

| event | time (ET) | nearest deploy |
|---|---|---|
| QQQ last event | 09-01 10:30:53 | 09-01 **17:03** and **17:31** — both post-close, 6.5h later |
| SMH last event | 09-01 11:30:56 | same two, 5.5h later |
| the 07-27 to 08-05 waves | — | outside all retained deploy data; git shows no RTH deploys in that window |

**Neither failure is deploy-aligned.**

**RTH deploy exposure, stated because it is real and separate:** 8 of the 20 retained
deploys started inside RTH (09-02 15:11-15:50, 09-03 14:33-15:08), all CC-BUILD's, for an
estimated **8 to 23 minutes** of cumulative hub downtime during collection hours at the
brief's stated 60-170s per restart. That is worth avoiding on its own merits and is
**not** the cause of a 97% feed loss.

## 3 — (c) LOSS TAXONOMY

| class | assigned | evidence |
|---|---|---|
| **delivered-stored** | the 6 survivors | rows land, timestamps normal |
| **fired-delivery-failed** | **QQQ, SMH** (09-01) | principal reports TV red-exclamation; endpoint provably up because other tickers landed the same day through the same URL |
| **TV-not-firing OR fired-delivery-failed** | **the other ~204**, incl. SPEC-01's DIA TLT XLE XLF XLK | zero rows for 34-38 days; **not separable from inside the DB** |
| **delivered-rejected** | **NOT DETERMINABLE** | the log buffer holds 500 lines, hours not weeks; no retained non-2xx record for the failure window |

The QQQ/SMH assignment is firm: the failure is **per-alert, not per-endpoint**, because
other alerts delivered successfully through the same endpoint on the same days.

The 204 cannot be split between the first two classes with available evidence, and this
diagnosis does not guess. **That split is what determines whether the fix is
alert-recreation or availability**, which is exactly why R-IV.228 ordered diagnosis first.

## 4 — THE ACTUAL FAILURE: ALARM FIRED, NOTHING FOLLOWED

`pythia_staleness_watchdog_loop` monitors the liquid-20 roster with a per-ticker Redis latch. **Live check:**

```
alarm:pythia_stale:  AAPL AVGO FXI GOOGL HYG INTU ISRG META
                     MSFT NVDA QQQ SMH TLT TSLA XLK ZS      = 16 latches set
```

Sixteen latches, matching the sixteen dead liquid-20 tickers exactly. `LATCH_TTL` is
**7200s**, so each re-arms roughly every two hours of RTH: on the order of **three alarms
per ticker per session, ~48 per day, ~1,200 over the five weeks** this has been running.

**Everything worked except the response.** The roster was right, the session-aware
threshold was right, the latch mechanics were right, the alarms were delivered. The
condition persisted for five weeks anyway.

### The part CC-BUILD owns

SPEC-01 shipped a **second** liveness instrument — per-ticker watermarks — for
**exactly this condition**, and this lane never checked whether the existing one was
already alarming. Had it looked, the five dark tickers would have been known **before**
the allowlist was written, and R-IV.109(e)'s dedicated-alert precondition would have
been testable at build time instead of discovered in the dry-run.

**A new detector for a condition an existing detector is already reporting is not
redundancy. **It is a second alarm against a condition the first alarm reported
1,200 times without producing action, and it consumed a build slot.**

*[FORECAST-AS-STATE correction. This read "a second alarm nobody will act on" —
a flat future indicative predicting behaviour that has not occurred. The measured
claim is the one that carries the argument anyway: the first alarm's ~1,200
deliveries produced no action, which is evidence, not forecast. Found by
CC-QUERY's future-conditional tell run on this lane's own artifacts.]*

## 5 — (d) LIMITATION REGISTERED

The watermark sentinel monitors the **pipe end**. From inside the database, a delivery
outage and a quiet market are the same observation. The only source-side sentinel that
works today is the red exclamation on the principal's phone — which is how the QQQ/SMH
mechanism became known at all. **Routed to the 09-15 supervision inputs.**

## 6 — (e) DRY-RUN CAVEAT

Today's single IB break is a **lower bound on IB breaks, not a measurement of them**,
taken through a feed at 3% of its historical breadth. Recorded on
`DEF-STRIKE-WATERMARK-NEVER-ALIVE.md` as well.

## 7 — WHAT THIS DIAGNOSIS DOES NOT DO

**It does not prescribe.** R-IV.228 ordered diagnosis before any alert-recreation order,
and the decisive question — TV-not-firing versus delivery-failed for the ~204 — **is not
answerable from the pipe end.** Recreating alerts would be a fix for one branch chosen
without evidence for it.

**What would settle it**, offered not implemented: TradingView's own alert log, which the
principal can read and this lane cannot. Per-alert status there splits the population in
one pass.

## 8 — SCOPE BEYOND SPEC-01, FLAGGED BECAUSE OF TIMING

`pythia_events` is an input to more than the STRIKE converter. **Any study reading it across
2026-07-27 onward is reading a collapsing universe**, and a breadth change of this size
is not a neutral background condition for a forward-looking study. The TRITON
forward-window registration is at spine's desk awaiting T0 as this is filed; whether its
instruments touch `pythia_events` is TRITON's and spine's to say, and it is stated here only so the
question is asked before T0 rather than after.
