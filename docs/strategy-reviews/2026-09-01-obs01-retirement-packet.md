# OBS-01 TERMINAL READ — d7 · 2026-09-01 (Tuesday)

## LABELED: EMITTER-CHARACTERIZATION ONLY

**Lane:** CC-QUERY · SELECT-only · **Registered text:** OBS-01 **v2.1**, no amendment
**As-of (in-DB UTC):** `2026-09-01 22:53:38.405271+00` · run 2 `22:53:39.076539+00`
**Gate:** past 20:00Z close, adjudicated against in-DB wall-time.

## Provenance

| item | value |
|---|---|
| registered-text sha256 | `714b1bfe1928…6ee7b221` at **HEAD · origin/main · 14fb9ff · CRLF-normalized tree** — all four agree |
| working-tree HEAD | `6e3ca4bfcf8b8a4bcfc34bb2cd7993a495233dd5` |
| origin/main | `692ff3f2b24a57782f9d27ddff21ce03a2156192` (10 ahead, 0 behind; no `docs/strike/` change) |
| dual-run stability hash | `6e15fdfeddf22dce8018e147a0e99011533c82012649e9af2325aa76009ed2ba` — **PASS** |
| known-absent control | `fatal: path … does not exist in 'HEAD'` — guard discriminates |
| database | railway · PostgreSQL 17.11 · read_only_session True |
| freshness | `pg_postmaster_start_time 2026-08-23 11:40:25Z`, uptime 9d 11h — no restart since d5 |

## RESTATED HEADER LINE — stated in-read per R-IV.127(f), no amendment to the file

> **PULLBACK_ENTRY — DUAL-EMITTER, BOTH ARMS LIVE as of 2026-08-28.** CTA arm ≈7–16/day.
> Crypto arm: dark ~08-23→08-27, **RESUMED 2026-08-28** (ADA-USD; LTC-USD joins 08-31) —
> rate not established. **REPORT PER-ARM.** Combined totals from 08-28 forward are two-arm
> sums and are NOT comparable to the CTA band.

**Settled per-arm figures, measured this read (out-of-text probe):**

| day | total | crypto | CTA |
|---|---|---|---|
| 08-28 | 19 | 2 | 17 |
| 08-29 *(Sat)* | 5 | 5 | 0 |
| 08-30 *(Sun)* | 7 | 7 | 0 |
| **08-31** | **44** | **24** | **20** |
| 09-01 *(d7)* | 28 | 11 | 17 |

**08-31 settles at 24 of 44**, not the `11 of 31` the restatement carried as PARTIAL.
R-IV.136(c)'s PARTIAL edit is vindicated: the figure more than doubled after the d6 read.
Had it filed as fixed, the header would have been wrong by a factor of two.

Note the CTA arm alone now reads **17 · 20 · 17** on the last three sessions — above its
≈7–16 band on all three, independent of the crypto arm.

## TRIPWIRE — ALL THREE PASS · **OUT-OF-TEXT PROBE** (R-IV.127(e))

| row | asserted | observed | source |
|---|---|---|---|
| 08-20 HG_1H | 36 | **36** ✓ | **OUT-OF-TEXT PROBE** |
| 08-21 HG_1H | 63 | **63** ✓ | **OUT-OF-TEXT PROBE** |
| 08-24 HG_1H | 66 | **66** ✓ | in registered text (final day observable) |

Two of three came from the labeled probe. From tomorrow the window opens 08-25 and **all
three reference rows are outside it** — coverage reaches zero exactly as the decay defect
predicted. The instrument retires one day before its tripwire goes fully blind.

## OBS-1 — last 36h of HOLY_GRAIL_1H · 102 rows

Not a cap hit (LIMIT 400). 102 reconciles exactly with OBS-2: 50 (08-31) + 52 (09-01).

- first: `2026-09-01 19:20:35.461955 | OKTA | LONG | 37.00 | ACTIVE | NULL | watchlist | TRADE_SETUP | true`
- last: `2026-08-31 13:11:43.377544 | META | LONG | 52.00 | DISMISSED | DISMISSED | watchlist | TRADE_SETUP | true`

**`l0_tag=true` on 102 of 102.** Status ACTIVE 47 · EXPIRED 36 · DISMISSED 19.
Direction SHORT 56 · LONG 46. user_action NULL 52 · DISMISSED 50.

## OBS-2 — 23 rows · window 08-24 → 09-01

| utc_day | HG_1H | ARTEMIS_LONG | PULLBACK_ENTRY |
|---|---|---|---|
| 08-24 | 66 | 5 | 15 |
| 08-25 | 58 | 10 | 13 |
| 08-26 | 53 | 23 | 13 |
| 08-27 | 41 | 13 | 15 |
| 08-28 | 59 | 12 | 19 |
| 08-29 *(Sat)* | — | — | 5 |
| 08-30 *(Sun)* | — | — | 7 |
| 08-31 | 50 | 30 | **44** *(was 31 at the d6 read — settled)* |
| **09-01 (d7)** | **52** | **11** | **28** |

HG_1H d7 = 52, inside 36–73. Every observed day of the window sits in band.

## LIVENESS — INDETERMINATE (terminal statement)

**OBS-0 was never implemented in v2.1.** Per the registered text's own rule, row-presence
alone yields INDETERMINATE. **All eight observation days, d0 through d7, close
INDETERMINATE.** Evidence consistent with LIVE, stated separately and never as a substitute:
52 HG_1H rows today, 13:0x → 19:20Z.

Extending the R-IV.127(a) certification to d7: **d0–d7 = LIVENESS-INDETERMINATE-BUT-NON-ZERO**
for the three firing types; the low-day exception remains **d4 (08-27, HG_1H = 41)**.

## Labels — final state

| | |
|---|---|
| **L1** suppression premise | **HELD to terminus** — `l0_tag=true` on every row of every read; creation-side only, zero surfaced |
| **L2** record-death window | RETIRED at d5, as scheduled |
| **L3** HG_15M documented null | **HELD** — zero rows across all eight days |
| **L4** oldest-bucket truncation | RETIRED by the epoch anchor |
| **L5** OBS-1 cap | **HELD, never triggered** — max observed 102 of 400 |

---

# PACKET

## Findings of record

**The emitter is healthy and entirely suppressed.** Across eight observation days HG_1H fired
36–66/day, every day in band, with `l0_tag=true` on 100% of rows and **zero signals surfaced**.
Nothing in this window bears on whether HOLY_GRAIL_1H has edge — it was never allowed to
express one. That is the whole characterization, and it is what "EMITTER-CHARACTERIZATION
ONLY" means.

## Debt section (R-IV.127(f))

**1 · OBS-0 — the sentinel that was named but never built.** v2.1 made OBS-0 the deciding
liveness instrument and shipped without it. Consequence: **eight of eight days INDETERMINATE**.
Bounded for the three firing types; the cost lands on the two null types, where quiet and
deafness were never distinguishable. Forced-grid measurement across d0–d7:
**`HOLY_GRAIL_15M` zero on 8 of 8 days · `TRAPPED_LONGS` zero on 8 of 8 days — 16 of 40 grid
cells zero, all rate-adjudicated, none deafness-tested.** Ruled a requirement for any
successor instrument at R-IV.127(b).

**2 · TRIPWIRE DECAY.** A guard anchored to fixed calendar rows inside a scrolling window.
Observable coverage 3 → 1 → 0; it would have kept returning PASS with nothing left to check.
General form, per EDGE: **a guard must be anchored to the window it guards, never to values
outside it.** Today's read needed an out-of-text probe to assert two of its three rows.

**3 · ARTEMIS_LONG BAND — the band does not describe the series.** Measured d0–d7 against the
artifact-cited ≈15–20/day:

```
d0 20 · d1 5 · d2 10 · d3 23 · d4 13 · d5 12 · d6 30 · d7 11
```

**1 of 8 days in band** (d0). Five below, two above; range 5–30, a 6× spread. This is not a
band with outliers — it is a band that fails to characterize. Recommend re-derivation before
any consumer conditions on it.

**BOUNDARY NOTE (EDGE, R-IV.143):** OBS-01 measured EMISSION under suppression; PR-105
measured OUTCOMES on historical emission. They do not bear on each other in either
direction. A healthy suppressed emitter is not evidence against the KILL, and the KILL
is not evidence about what OBS-01 observed. PR-105's verdict rests on 5,791
non-dismissed verdict rows across two eras with all four criterial cells negative and
no flip across the friction band; OBS-01 has no outcome data at all, by construction.

**Debt-section confirmations at filing:** ARTEMIS band WITHDRAWN by its author
(period-average derivation, 1-of-8 in band); PULLBACK CTA band flagged same class
(17 · 20 · 17 above ≈7–16); both re-derivations live in SPEC-01's watermark work, from
observed daily distributions, n-gated.

**4 · FALSIFIED-FINDINGS LEDGER — instrument-scoped (R-IV.130).** Two entries belong to
OBS-01 and stay here: **the monotonic-decline retraction** and **the crypto-arm-dark status
claim** (falsified 08-28; the arm had resumed, and the stale clause corrected cleanly only
because it carried an "until stated otherwise" hedge).

> Board-wide entries, including EDGE's six and F9, live in
> `docs/conventions/falsified-findings-ledger.md`. Not duplicated here.

## Closing position

Eight observation days, terminus reached on schedule, destination **RETIRE** unchanged.

**OBS-01 RETIRES at this read.**
