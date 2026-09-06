# OUTAGE DIAGNOSIS — crypto_scanner + stable_jobs, 2026-09-05

**Ordered:** R-IV.271(c), position 0, read-only. **Run:** 2026-09-05 by CC-BUILD.
**Hypothesis under test:** shared dependency, both surfaces yfinance-sourced.

---

## VERDICT: THE SHARED-DEPENDENCY HYPOTHESIS IS NOT SUPPORTED, and the two surfaces
## have DIFFERENT causes

They alarmed the same afternoon. **That is where the resemblance ends.**

| | stable_jobs | crypto_scanner |
|---|---|---|
| cause | **weekday-gated job, weekend SLO** | genuinely silent |
| severity | **FALSE RED** | real, precedented |
| clears | **Monday, by itself** | unknown |

## 1 — stable_jobs: a FALSE RED, and a known class

The flatlining job is `provisional`: age 28.1h, **zero consecutive failures, no error**.

**It is weekday-gated.** `backend/jobs/stable_jobs.py`:217 — `if is_weekday(et):`. It has not failed; it has not been
*asked* to run since Friday.

**The discriminator is in the same payload:** `movers` and `strip` sit at **28.2h**, older
than provisional, and both read `ok`. Same age, different verdict, so the difference is
the per-job SLO and not the data.

**This is DEF-NIGHTLY-FLATLINE's exact mechanism recurring on a sibling job** — a
weekday-cadence job whose SLO does not model the weekend, producing a guaranteed false
red every weekend. That defect already cost this board one wrong finding on 09-02, when
a 70.6h age was reported as a recurrence and was the weekday gate working correctly.

**It will clear Monday without intervention.** Registered as its own DEF per the ruling,
P2, mechanism identified rather than pending.

## 2 — crypto_scanner: real, and precedented

31.5h silent against a 12h SLO on a source that genuinely runs 24/7 — confirmed by
day-of-week counts over 60 days: **Sat 73 signals, Sun 24**. Weekend silence is not
schedule-expected here.

**But the absence law applies before calling it a defect.** Gap distribution over 30
days, 492 gaps:

```
avg 1.04h   p95 0.5h   max 131.9h
gaps > 24h: 3      gaps > 31h: 2
```

**A 31.5h gap is rare but has precedent**, and this source has previously gone dark for
**131.9 hours** and returned. The alarm is correct to fire; the state is one this source
has entered before and recovered from unaided — consistent with the self-recovery
family already recorded on `DEF-CRYPTO-SCANNER-DARK`.

**Mechanism NOT identified here.** It needs the scanner's own logs, and the 500-line
Railway buffer covers hours, not the 31 needed. Stated rather than guessed.

## 3 — THE FINDING NEITHER ALARM WAS ABOUT: UW BARS ARE DEAD

Not what was asked, surfaced by the log scan, and larger than either alarm:

```
40 x  "UW /ohlc/1d unavailable or empty for <T> — falling back to yfinance"
      across 15 tickers: COPX GLD HYG IWM QQQ RSP SMH SPY TLT XLE XLF XLK XLP XLU XLY
```

**Every daily-bar fetch in the buffer is falling through to yfinance.** The fallback is
working — which is why nothing alarms — and that is precisely the problem: **a fallback
that works silently makes the primary's death invisible.** Same shape as the grader
running on deploys.

**This bears directly on a live instrument.** The R-IV.193 QQQ 200-SMA watch computes
from this path. It is currently correct *because the fallback holds*, not because the
primary does.

## 4 — yfinance: failing on BREADTH SYMBOLS ONLY

```
^ADVN  ^DECLN  ^ADV  ^DEC  ADVN  DECLN     6 failures each
"Quote not found for symbol: ^ADVN"        HTTP 404
rate-limit signatures (429 / Too Many)     ZERO
```

**All 15 equity tickers succeeded through the fallback.** So yfinance is not broadly
degraded and is not rate-limiting — it has lost the advance/decline breadth symbols
specifically, which Yahoo appears to have delisted or renamed.

**This is what falsifies the shared-dependency hypothesis.** Had yfinance been
rate-limited, the 15 equity tickers would have failed too. They did not.

## 5 — THE TENSION THE RULING ASKED ME TO RECORD

R-IV.271(c): *if yfinance is the cause, record that memory says yfinance is
fallback-only, yet two production surfaces have it as primary.*

**yfinance is not the cause** — so the conditional does not fire. **But the tension is
real and worse than stated**, and it is recorded here on that basis:

- `backend/jobs/stable_jobs.py`'s own docstring reads **"yfinance-only (zero UW calls)"**. Not a fallback.
  Primary, by design, declared in the module.
- The daily-bar path is **nominally UW-primary with yfinance fallback**, and today
  **100% of its fetches are served by the fallback.**

**So one surface has yfinance as declared primary and the other has it as de-facto
primary.** The "fallback-only" belief is false on both, in different ways. **A dependency
that is load-bearing everywhere and documented as a fallback is a single point of failure
nobody is counting**, and it is the reason a yfinance outage was a plausible hypothesis
for two unrelated alarms.

## What was NOT determined

- Why crypto_scanner stopped. Needs its own logs; buffer too short.
- Whether UW's OHLC outage is account-side, vendor-side, or endpoint-specific.
- Whether the breadth symbols are recoverable under different tickers.
