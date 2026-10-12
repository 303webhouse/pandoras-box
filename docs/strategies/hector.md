# HECTOR | Trapped Shorts (`TRAPPED_SHORTS`)

| field | value |
|---|---|
| signal_type / strategy keys | `TRAPPED_SHORTS` / "CTA Scanner" (equities) and "Crypto Scanner" |
| emitting code | `check_trapped_shorts` (`backend/scanners/cta_scanner.py:1117`; type at `:1171`); called after the death-cross strip, so exempt from it (`:1449`) |
| side | LONG |
| grid cell | **WITH-TREND LONG** (momentum above the 200-day and the 20-bar VWAP) |
| schedule / trigger | the CTA `_scanner_loop` (`backend/scheduler/bias_scheduler.py`), trading days 9–16 ET, on a forming daily bar; also the crypto scanner (24/7) |
| status: EQUITY ("CTA Scanner") | **Ruled SHADOW (R-IV.893), NOT ENFORCED.** L0 routing keys on `signal_type` only, so suppressing `TRAPPED_SHORTS` would also suppress crypto: BUILD's stop (R-IV.892). **The regrade decides it.** Under the fixed grader, ≥ 30 equity verdicts with a hit rate > 50% → LIVE. Otherwise → SHADOW, and SPINE rules on an asset-class routing key. Until then it surfaces as before. The earlier "58.99% on 473" (R-IV.880) was ~94% Crypto Scanner rows and is not equity evidence (R-IV.889(b)) |
| status: CRYPTO ("Crypto Scanner") | **Unchanged: LIVE.** 392 verdicts on 18 dates, graded by the LIVE-GRADER before the fix. **This is not HECTOR's equity evidence.** |
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
Retirement is SPINE's and QUERY's. Equity is ruled SHADOW (R-IV.893) but not enforced, because routing cannot yet separate asset classes. The regrade under the fixed grader decides: ≥ 30 equity verdicts and > 50% → LIVE; otherwise SHADOW plus a routing-key ruling. Crypto is unchanged.

## Change log
- 2026-01: CTA scanner. 2026-10-12: card v0; SHADOW proposed (R-IV.879(b)) and WITHDRAWN the same day (R-IV.884) — stays LIVE pending LAB's reconciliation of the replay against QUERY's live outcomes (R-IV.880). 2026-10-12: status split by asset class (R-IV.898(a)). Equity: SHADOW ruled (R-IV.893), not enforced (R-IV.892), the regrade decides. Crypto: unchanged.
