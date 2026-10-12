# HECTOR | Trapped Shorts (`TRAPPED_SHORTS`)

| field | value |
|---|---|
| signal_type / strategy keys | `TRAPPED_SHORTS` / "CTA Scanner" (equities) and "Crypto Scanner" |
| emitting code | `check_trapped_shorts` (`backend/scanners/cta_scanner.py:1117`; type at `:1171`); called after the death-cross strip, so exempt from it (`:1449`) |
| side | LONG |
| grid cell | **WITH-TREND LONG** (momentum above the 200-day and the 20-bar VWAP) |
| schedule / trigger | the CTA `_scanner_loop` (`backend/scheduler/bias_scheduler.py`), trading days 9–16 ET, on a forming daily bar; also the crypto scanner (24/7) |
| status | **SHADOW** (R-IV.879(b), 2026-10-12): negative in every regime, including against its same-date control. Still stored and graded; BUILD moves it into L0 `SUPPRESS_ALWAYS` |
| bucket ceiling | No provenance ceiling: C5 and F5 do not reach this cell (the R-IV.838(c) reading for with-trend cells) |
| lifetime tries counter | unrecorded before LAB; unchanged by Task 8 (evaluation only) |

## Rules as coded
`price > SMA200`, `price > vwap_20`, `ADX > 25`, `RSI < 60`, `RVOL > 1.25`, all on the latest bar
(`cta_scanner.py:1129-1146`).

## Evidence so far
**Task 8 replay** (R-IV.877(a); `C:\temp\cc-query-handoff\lab\roster-replay\01-TASK8-RESULTS.md`,
`aac4303c…`):
- Data: 2007–2026, Task 5's yfinance snapshot, 196 names (survivorship-biased), next-open entry,
  market-adjusted, date-clustered t. Detector fires, without the top-10 cut.
- h3:
  - **all −0.11% (t −2.23)**, 5,019 fires / 2,465 dates; same-date control difference
    **−0.14 (t −2.91)**;
  - bull stack −0.17 (t −3.02); **bear stack −1.14 (t −2.39)**, 79 / 66, about two episodes;
  - transition −0.03 (t −0.33); range +0.06 (t 0.32); sector ETFs −0.12 (t −1.61).

## Kill rule
Retirement is SPINE's and QUERY's. It is in SHADOW now; it surfaces again only on new evidence.

## Change log
- 2026-01: CTA scanner. 2026-10-12: card v0; SHADOW (R-IV.879(b)).
