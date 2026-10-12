# ACHILLES | Sell the Rip (`SELL_RIP_EMA`, `SELL_RIP_VWAP`, `SELL_RIP_EARLY`)

| field | value |
|---|---|
| signal_type / strategy keys | `SELL_RIP_EMA`, `SELL_RIP_VWAP`, `SELL_RIP_EARLY` / `sell_the_rip` |
| emitting code | `check_sell_the_rip` (`backend/scanners/sell_the_rip_scanner.py:245`; types at `:320`, `:353`, `:386`); the scan `run_sell_the_rip_scan` (`:564`) |
| side | SHORT |
| grid cell | EMA and VWAP: **WITH-TREND SHORT** (a rally into the 20-EMA or VWAP under a falling 50-day). EARLY: **BEFORE THE TURN SHORT** (a rally in a sector in distribution, before the 50-day confirms). Canonical per the census (R-IV.855(b)) |
| schedule / trigger | `sell_the_rip_scan_loop` (`backend/main.py`), trading days, about one or two runs a day, on daily bars |
| status | **LIVE** (L0 KEEP) |
| bucket ceiling | EMA / VWAP: no provenance ceiling (with-trend). EARLY: before-the-turn, so **B3 or TAIL** (R-IV.823(c)3); TA reviews what C5 means for ACHILLES (R-IV.855(b)) |
| lifetime tries counter | unrecorded before LAB |

## The scan-wide gate
The whole scan runs only when the cached composite bias is ≤ −0.20 (`_check_bias_allows_shorts`,
`sell_the_rip_scanner.py:529-541`, called at `:570`). A missing composite allows the scan
(`:536`). The scan is skipped when VIX > 45 (`:576`).

## Evidence so far
- **Task 8: NOT REPLAYABLE ON DAILY BARS** (R-IV.877(a)): no composite-bias history exists before
  2026, and the composite cannot be rebuilt from daily bars.
  - Its VWAP is a daily-bar cumulative VWAP (`compute_indicators`), and EARLY's sector class is
    daily-bar sector RS (`backend/scanners/sector_rs.py:47-67`). Both are reproducible; the gate
    is the blocker.
- Census part 2 (window 2026-07-13 → 10-08): LIVE. EMA 214 saved vs 149 expected ticker-days;
  VWAP 130 vs 90; EARLY 132 rows saved (no replay).

## Change log
- 2026-03: built. 2026-10-12: card v0 (R-IV.879(b)).
