# TWO_CLOSE_VOLUME

| field | value |
|---|---|
| signal_type / strategy keys | `TWO_CLOSE_VOLUME` / "CTA Scanner" (equities) and "Crypto Scanner" (crypto) |
| emitting code | `check_two_close_volume` (`backend/scanners/cta_scanner.py:803-866`) |
| side | LONG only (`:850`) |
| grid cell | **CONFIRMED TURN, LONG** (partial): a fresh two-close cross above the 50-day with volume. The 09-23 definition also asks for the stack turning, which this doesn't test |
| incumbent it would replace | n/a (incumbent) |
| schedule / trigger | equities: `_scanner_loop` (`backend/scheduler/bias_scheduler.py:3078`) → `run_cta_scan_scheduled` (`:3317`), trading days 9–16 ET, every 15 min (first hour and from 15:00) or 30 min; crypto: `run_crypto_scan_scheduled` (`:3619`), every 30 min, 24/7 |
| status | **LIVE**: in no suppress set; L0 default KEEP (`backend/config/l0_routing.py:72-73`) |
| bucket ceiling | **UNSET.** Not before-the-turn, not flow-originated. Needs a ruling |
| lifetime tries counter | **≥ 1**: the volume threshold was retuned 1.10 → 1.50 ("H2", `cta_scanner.py:104`); earlier tries are unrecorded |

## Rules as coded
- **Fresh cross:** the latest close is above the 50-SMA, the prior close too, and the one before
  was not (`cta_scanner.py:819-823`).
- **Volume:** `vol_ratio ≥ 1.50` (`:825`, threshold `:104`); `vol_ratio` = volume ÷ 30-day mean.
- **Levels:** invalidation at price − 1.5 ATR (`:832`). Entry zone and stop come from shared
  helpers.
- **Bars:** yfinance daily, `period="1y"` (`_fetch_history_async`, `:65-70`; called at `:1393`).
  - **The scanner runs intraday on daily logic**, so the latest "daily" bar is still forming.
    Its close is the live price and its volume a partial day measured against a 1.5× full-day
    threshold.
  - A cross that is undone by the close still fires. A live fire is therefore not the same event
    as an after-close evaluation of the same rule.
- **Docstring is stale:** "Volume > 10% above" (`:807-810`), versus the coded 1.50.

## Rules as approved
`docs/approved-strategies/cta-flow-replication.md:41-46`: two consecutive closes above the 50 SMA
(below before) and volume ≥ 1.5× the 30-day average. These match. The stop, "0.5 ATR below the
50 SMA", differs from the coded invalidation at price − 1.5 ATR.

## Evidence so far
- `docs/strategy-reviews/cta-artemis-decompose-and-uw-era-2026-06-16.md:14`:
  n = 30, win 36.7%, **+0.82** (`outcome_pnl_pct`, bar-walk, not market-adjusted), KEEP.
  n distinct dates not stated.
- The L0 brief lists 520 rows (`docs/codex-briefs/2026-06-17-L0-foundation-build-brief.md:41`).
  Most are Crypto Scanner (`docs/edge/results/QS-02-RESULTS.md:462,471`: 489 crypto vs 49 CTA).
  The +0.82 is the equity slice.
- No market-adjusted figure exists yet.

## Kill rule
LAB proposal: re-grade the equity fires at fixed horizons from the next open, market-adjusted, with
a same-date control. Retire if the result isn't positive at the registered horizon with
n ≥ 30 and ≥ 20 distinct dates.

## Change log
- 2026-01-21: CTA scanner (6c3b3b1); volume threshold 1.10 → 1.50 (H2).
- 2026-06-16: KEEP (+0.82, n = 30). 2026-10-09: card v0.
