# HECTOR | Trapped Shorts (`TRAPPED_SHORTS`)

| field | value |
|---|---|
| signal_type / strategy keys | `TRAPPED_SHORTS` / "CTA Scanner" (equities) and "Crypto Scanner" |
| emitting code | `check_trapped_shorts` (`backend/scanners/cta_scanner.py:1117`; type at `:1171`); called after the death-cross strip, so exempt from it (`:1449`) |
| side | LONG |
| grid cell | **WITH-TREND LONG** (momentum above the 200-day and the 20-bar VWAP) |
| schedule / trigger | the CTA `_scanner_loop` (`backend/scheduler/bias_scheduler.py`), trading days 9–16 ET, on a forming daily bar; also the crypto scanner (24/7) |
| status | **LIVE** (R-IV.884, 2026-10-12). NOT in `SUPPRESS_ALWAYS` (`backend/config/l0_routing.py` — present on the kept-live list in `backend/tests/test_nemesis_wiring_r809.py`). This card previously read SHADOW per R-IV.879(b); **R-IV.884 withdrew that move and BUILD reverted it** (`dcb61a65`), because QUERY's live outcomes (R-IV.880) disagree with the replay below — 58.99% hits and +4.07% excess on 473 verdicts on surfaced rows. **Two independent routes disagree, so nothing moves until LAB reconciles them.** The replay finding stands as a finding; it no longer governs the roster. |
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
Retirement is SPINE's and QUERY's. It is LIVE: the SHADOW move was withdrawn by R-IV.884 on the day it was proposed, because the live record disagrees with the replay. It moves only when the two routes are reconciled.

## Change log
- 2026-01: CTA scanner. 2026-10-12: card v0; SHADOW proposed (R-IV.879(b)) and WITHDRAWN the same day (R-IV.884) — stays LIVE pending LAB's reconciliation of the replay against QUERY's live outcomes (R-IV.880).
