# GAP-FLUSH (working name) | gap-down flush dip-buy (TA-186)

Working name until the principal names it (lab §7). The source is TA-186 §A/§B; Nick confirmed it on
2026-10-15 ("A+B confirmed"). The rules below are as relayed verbatim in SPINE R-IV.1430(b). The
TA-186 file itself lives in SPINE's project.

| field | value |
|---|---|
| signal_type / strategy keys | none: **not coded in the hub.** A playbook under replay |
| emitting code | none. The replay instrument is `scripts/lab/ta186_stage1.py` (stage 1, daily bars) |
| side | LONG (a dip-buy; 0–1 DTE call debit spread in the playbook) |
| grid cell | **WITH-TREND, LONG** (LAB's classification, provisional): A4 trades only with SPY above its 200-day, buying a flush after a gap down |
| incumbent it would replace | none known |
| schedule / trigger | the playbook: a gap down at the open, then a flush below the opening print. No live trigger exists |
| status | **REPLAY, stage 1 of 3** (stage 1 = daily screen; stage 2 = intraday replay of the exact rules; stage 3 = money gate). Stamped R-IV.1435 |
| bucket ceiling | not set: the bucket question goes to TA at any promotion |
| lifetime tries counter | **1** (stage 1, v0: one definition, X = 0.75%, no variants) |

## Rules as approved (TA-186 §A, relayed in R-IV.1430(b))
- **A1, the universe:** SPY, QQQ, IWM, SMH. Single names are optional and not counted.
- **A2, the setup:** a gap down from the prior close of ≥ 0.75% (ETF) or 2.0% (single name). *"The
  flush: price then trades below the opening print, so the low of day is made after the open."*
- **A3.3:** uses NYSE TICK intraday. **There is no history,** so it is forward only.
- **A4, the skips:**
  - every day with SPY below its 200-day;
  - the gamma regime (`gex_regime` from 2026-06-07 only, so forward only);
  - macro days (FOMC, CPI, PPI, payrolls, Fed speakers). **No long calendar exists, so this is not
    applied historically** (R-IV.1435(c)).
- **§B, the evidence path:** stage 1, P(close > open) and (close − low) ÷ gap against all gap-down
  days, split by SPY 200-day and VIX band → stage 2, the intraday replay → stage 3, modeled 0–1 DTE
  call-debit-spread P&L after costs > 0.

## Rules as coded
**Stage 1 only:** `scripts/lab/ta186_stage1.py`. The registration is
`lab\ta186\TA186-GAPFLUSH-STAGE1-STAMPED-R-IV.1435.md`, sha256 `5620546f…`.
- **The gap:** ref = the prior close − the ex-date dividend (`build_panel`); gap = open / ref − 1.
- **The event:** gap ≤ −0.75% and low < open (`masks`).
- **The control:** the same ticker and month, a flat open (|gap| < 0.25%), low < open, open ≠ the prior
  close (`masks`, `contributions`).
- **PASS iff P1–P5 hold** (`verdict`). SMH is used from 2011-12-21 only (`START`).

## Where they differ
- **§B's literal comparison, "all gap-down days",** contains the events and is biased against the
  claim. It is kept only as a secondary. The primary control is the same-month flat-open flush day
  (R-IV.1435(a)).
- **Daily bars cannot see when the low was made.** "Low made after the open" is approximated by
  "traded below the open" (true on 92–99% of gap-down days). Stage 2 tests the real flush.
- **A3.3, the gamma skip and the macro skip are not replayable historically** (above).
- **The playbook's 13:30 ET fill needs intraday bars:** stage 2.

## Evidence so far
- **Stage 1:** see the run record `C:\lane-state\lab-durable\ta186\run1\stage1_result.json`
  (aggregates; LAB's run; QUERY grades). Results are not copied here until QUERY's grade.

## Kill rule
- **Stage 1:** failing any of P1–P5 (registration §8) is KILL, and it ends the line.
- **Stages 2 and 3** are registered separately, only after a stage 1 PASS and a SPINE ruling.
- **Stage 3 passes only above 0.**

## Change log
- 2026-10-25: card v0, written with the stage 1 instrument (R-IV.1435(d)3).
