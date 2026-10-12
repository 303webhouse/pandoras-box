# ARTEMIS | VWAP Band Short (`ARTEMIS_SHORT`)

| field | value |
|---|---|
| signal_type / strategy keys | `ARTEMIS_SHORT` / "Artemis" (`ARTEMIS_LONG` is the suppressed long; not this card) |
| emitting code | **no hub detector.** TradingView webhook `/webhook/tradingview` → `process_artemis_signal` (`backend/webhooks/tradingview.py:760`; type at `:778`). Pine: `docs/pinescript/webhooks/artemis_v3.pine` |
| side | SHORT |
| grid cell | normal mode: **WITH-TREND SHORT** (a touch of the upper VWAP band, `vah = basis + 2σ`, with the close back inside, under the weekly AVWAP) (`artemis_v3.pine:61-62`, `:176`). Flush mode: **BEFORE THE TURN SHORT** (a 3%+ move into the band with an exhaustion bar, `:180`). One stored type spans both cells |
| schedule / trigger | whenever the off-repo TradingView alert fires (15-minute bars) |
| status | **LIVE** (L0 KEEP; `ARTEMIS_LONG` alone is in `SUPPRESS_ALWAYS`, `backend/config/l0_routing.py:61`) |
| bucket ceiling | normal mode: no provenance ceiling (with-trend); flush mode: B3 or TAIL (before-the-turn) |
| lifetime tries counter | unrecorded |

## Evidence so far
- **Task 8: NOT REPLAYABLE ON DAILY BARS** (R-IV.877(a)): a 15-minute TradingView Pine script
  with no hub detector.
- Census part 2: 1,221 rows in 90 days, unsuppressed and surfacing. The 2026-06-16 decomposition
  called it "salvageable-marginal, +0.04" (`l0_routing.py:61-63` comment).

## Change log
- 2026-03: webhook live. 2026-10-12: card v0 (R-IV.879(b)).
