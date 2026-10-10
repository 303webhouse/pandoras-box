# PHAETHON | Bearish Breakdown (`BEARISH_BREAKDOWN`)

Name per the registry (`backend/config/strategy_aliases.py`, R-IV.843(e); principal 2026-10-09).

| field | value |
|---|---|
| signal_type / strategy keys | `BEARISH_BREAKDOWN` / "CTA Scanner" |
| emitting code | `check_bearish_breakdown` (`backend/scanners/cta_scanner.py:1194-1267`) |
| side | SHORT only (`:1250`); emitted only when `allow_shorts=True` (`:1435-1438`), which the equity scan passes and the crypto scan does not |
| grid cell | **CONFIRMED TURN, SHORT**: a fresh two-close cross below the 50-day, volume, and a falling 20-SMA (the stack turning, partially) |
| incumbent it would replace | n/a (incumbent) |
| schedule / trigger | equities only: `_scanner_loop` (`backend/scheduler/bias_scheduler.py:3078`) → `run_cta_scan_scheduled` (`:3317`), trading days 9–16 ET, every 15–30 min |
| status | **LIVE**: in no suppress set; L0 default KEEP (`backend/config/l0_routing.py:55-73`). This contradicts the 06-16 "suppress (small-n)" recommendation; the L0 brief left it out of scope (`docs/codex-briefs/2026-06-17-L0-foundation-build-brief.md:47`) |
| bucket ceiling | **No provenance ceiling: C5 and F5 do not reach this cell.** Ordinary bucket rules apply: intent at entry, X4, X10 (R-IV.838(c)) |
| lifetime tries counter | **≥ 1** (the 2026-10-10 replay; earlier history unrecorded) |

## Rules as coded
- **Fresh cross down:** the latest close is below the 50-SMA, the prior close too, and the one
  before was ≥ 50-SMA (`cta_scanner.py:1211-1215`).
- **Volume:** `vol_ratio ≥ 1.50` (`:1221-1222`; docstring "1.2×" at `:1199` is stale).
- **SMA20 falling:** `sma20 < prior sma20` (`:1225`).
- **Levels:** invalidation at SMA50 + 0.5 ATR (`:1232`); priority 75.
- **Bars:** yfinance daily, `period="1y"`, evaluated **intraday on a forming bar**. This is the
  same caveat as [two-close-volume.md](two-close-volume.md).

## Rules as approved
`docs/approved-strategies/cta-flow-replication.md:80-85`: break below the 50 **or 120** SMA, volume
confirming, stop 0.5 ATR above the broken level. Coded tests only the 50 SMA, requires two closes
and a falling 20-SMA, and fixes volume at 1.5×.

## Evidence so far
- `docs/strategy-reviews/cta-artemis-decompose-and-uw-era-2026-06-16.md:16`:
  n = 12, win 41.7%, **−1.09** (`outcome_pnl_pct`), "suppress (small-n)". Not market-adjusted;
  n dates not stated.
- 37 all-time rows (`docs/edge/results/QS-02-RESULTS.md:472`).
- It is a short, so its market-adjusted figure is the one that matters, and none exists.
- **Task 5 replay (R-IV.850(e); `C:\temp\cc-query-handoff\lab
emesis-replay-TASK5-RESULTS.md`, results sha256 `2964fc9e…`): yfinance daily 2007-01-03 → 2026-09-30, 196 names (survivorship-biased), next-open entry, market-adjusted, date-clustered t. REPLAY, not a verdict.** 3,418 fires / 1,565 dates: h1/h2/h3 date-mean −0.01 / −0.04 / **−0.02%** (t −0.27 at h3); same-date difference +0.02 (t 0.22); flat in every split. **No edge in stage 1**; the n the roster review lacked (TA-140 §4 had 12). Stage 2 not run (declared: stage 1 not positive).

## Kill rule
LAB proposal: re-grade market-adjusted at fixed horizons with a same-date control. Retire if
negative with n ≥ 30 and ≥ 20 distinct dates. If n can't reach that in a reasonable window,
QUIET, and a ruling decides.

## Change log
- 2026-01-28: added (465659d). 2026-06-16: "suppress (small-n)", not applied. 2026-10-09: card v0.
- 2026-10-10: ceiling ruled (R-IV.838(c)).
