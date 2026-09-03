# DEF-STRIKE-WATERMARK-NULL-TRIGGER · P1

**Found:** 2026-09-03, during SPEC-01's D1 step-4 dry-run session, by reading the
watermark table rather than the rendered state.
**Status:** TICKETED, NOT FIXED (brief Gates). **SPEC-01 stays in dry-run.**

---

## The defect

The per-ticker watermark alarm **cannot fire for a ticker that was already dark at
deploy.** It is a NULL-TRIGGER in the exact sense of `verification-laws.md` section 1: a predicate that
runs clean, raises nothing, and can never be satisfied.

`baseline_sessions` increments **only when a NEW `last_event_session` is observed**:

    if last_session is not None and last_session != prev_session:
        baseline += 1

For a permanently dark ticker `last_event_session` never changes, so after the first cycle
`prev_session` equals it and the counter **caps at 1**. The alarm gates on `baseline_sessions >= 3`.
**1 < 3, forever.**

**A ticker that has never been alive since deploy cannot be reported as dead** — and
that is precisely the condition the instrument exists to detect.

## Demonstrated by live data, not argued

Read from `strike_feed_watermarks` at 2026-09-03 18:42Z. Seven of eight tickers sit at exactly
`baseline_sessions = 1`, including five dark for over a month. IWM reads 2 solely because it fired
today.

| ticker | last_event_session | baseline_sessions | rows last 7d |
|---|---|---|---|
| IWM | 2026-09-03 | **2** | 27 |
| QQQ | 2026-09-01 | 1 | 32 |
| SMH | 2026-09-01 | 1 | 13 |
| XLK | **2026-07-31** | **1** | **0** |
| XLE | **2026-07-30** | **1** | **0** |
| DIA | **2026-07-28** | **1** | **0** |
| XLF | **2026-07-27** | **1** | **0** |
| TLT | **2026-07-27** | **1** | **0** |

## The population it is failing to report: five dark tickers

**Five of the eight allowlist tickers have produced zero events for 34 to 38 days.**
All five fired historically — 57, 22, 29, 23 and 18 IB rows respectively — then
stopped in a four-day cluster, **2026-07-27 to 07-31**.

That cluster shape is the **TradingView watchlist-decay signature** already documented
in `pythia_staleness_watchdog_loop`: one ~240-symbol watchlist alert, ~39 calc slots, survivor set
reshuffles on every watchlist edit. R-IV.109(e) forbids exactly this upstream —
**every allowlist ticker MUST hold a verified dedicated per-symbol alert**, and
prey-list or watchlist coverage is never valid.

**Consequence for the study, stated because it moves a date:** SPEC-01's n>=50
both-direction sample accumulates from **three tickers, not eight**. The 09-18 target
was sized against eight.

**This half is not a code fix.** The five alerts need re-creating in TradingView. The
code defect is that nothing would ever have told anyone.

## D7 passes vacuously against this

D7's first half reads *"Watermark rows exist for all 8 tickers."* **It is true right
now, while five of them are dark.** Row existence cannot discriminate liveness — the
same shape as a control that tests file existence against a claim about rows. D7's
second half (no false alarms across a weekend) will also pass, for the wrong reason:
the alarm cannot fire at all.

**A green D7 on 09-07 must not be read as this defect being absent.**

## Interaction with DEF-STRIKE-WATERMARK-HOLIDAY

The two are opposite faces of one gate. The holiday defect makes the alarm fire when it
should not; this one makes it silent when it should not be. **Both live in
`baseline_sessions`**, and a fix for either must be checked against the other — raising the
gate worsens this defect, lowering it worsens the holiday one.

## Fix, when commissioned — not chosen here

The gate conflates two questions it should separate:

1. **Has this ticker ever been alive?** If a ticker has *any* historical events but none
   since deploy, that is a **dead feed**, reportable immediately and not subject to an
   onboarding gate at all. The n-gate exists for genuinely new tickers.
2. **Is this ticker alive today?** The current check, correctly gated.

Distinguishing them needs no new data: `strike_feed_watermarks` already stores `last_event_ts`. A ticker with
a non-null `last_event_ts` older than N sessions is dead, regardless of `baseline_sessions`.
