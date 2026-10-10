# HYPNOS | Exhaustion Reversal (`EXHAUSTION_BULL` / `EXHAUSTION_BEAR`)

Name per the registry (`backend/config/strategy_aliases.py`, R-IV.843(e); principal 2026-10-09).

| field | value |
|---|---|
| signal_type / strategy keys | `EXHAUSTION_BULL` / `EXHAUSTION_BEAR`, strategy "Exhaustion" (`backend/strategies/exhaustion.py:77-104`; `backend/webhooks/tradingview.py:519`) |
| emitting code | **no hub detector.** TradingView webhook `/webhook/tradingview` (`tradingview.py:222`, mounted in `backend/main.py`), dispatched on `"exhaustion" in strategy` (`:299`) to `process_exhaustion_signal` (`:480`) |
| side | BOTH (by the alert's direction, `exhaustion.py:51-60`) |
| grid cell | nominal **BEFORE THE TURN**, LONG and SHORT (a reversal at an extended move, per the spec). **Not coverage**: there's no detector to grade |
| incumbent it would replace | none |
| schedule / trigger | whenever an off-repo TradingView alert fires |
| status | **NO DETECTOR** (R-IV.830(e)). The L0 default is KEEP (it's in no suppress set; `backend/config/l0_routing.py:55-73`) |
| bucket ceiling | **B3 or TAIL** (before-the-turn). **SHORT: no-fly flag "entering parabolic shorts too early".** |
| lifetime tries counter | **0** |

## Verified: there is no hub detector
- `exhaustion.py` holds **no price-bar logic**:
  - `validate_exhaustion_signal` (`:29-74`) checks `enabled` and maps direction;
  - `classify_exhaustion_signal` (`:77-104`) names the type;
  - the Leledc params in `STRATEGY_CONFIG` (`:22-23`) are read by nothing;
  - `calculate_exhaustion_targets` (`:107-146`) is imported nowhere.
- There is no Exhaustion Pine script in the repo (`docs/pinescript/PINESCRIPT_INVENTORY.md:120`).
  The `artemis_v3.pine` / `hub_sniper_v2.1.pine` "EXHAUSTION DETECTION" blocks emit Artemis and
  Sniper, not Exhaustion.
- `process_exhaustion_signal` sets `status "IGNORE"` on a BULL alert when the composite is
  < −0.3 (`tradingview.py:500`, `:538`). `docs/defects/DEF-SIGNAL-STATUS-DISCARDED.md` (P2, not
  fixed) says that status is discarded at write, so suppressed rows store as ACTIVE.

## Rules as approved
`docs/approved-strategies/exhaustion-reversal.md`:
- Logic (`:15-19`): extended move, capitulation volume, wick-rejection candle, RSI extreme.
- **"Exact thresholds are defined in `exhaustion.py`"** (`:21`). **False**: that file defines none.
- The spec also says the CTA scanner generates them server-side (`:10-12`). **False**:
  `backend/scanners/cta_scanner.py` contains no exhaustion logic.

## Rules as coded
None in the hub. The rules live in an unversioned TradingView alert outside this repo.

## Evidence so far
- 13 all-time rows as of 2026-03-06: 7 BEAR, 5 BULL, 1 upgrade (`exhaustion-reversal.md:32`).
- No backtest, no verdict. Whether it still fires: census (R-IV.809(f)).

## Kill rule
LAB proposal: it stays NO DETECTOR until someone writes a detector in the hub, with its rules in a
card and a REPLAY. An alert whose logic isn't in the repo can't be registered, because the
register hash needs the code commit (skill §2).

## Change log
- 2026-01-20: handler added (be1dc60). 2026-03-06: spec doc (8737be4). 2026-03-09: BULL suppression brief.
- 2026-10-09: card v0. Status NO DETECTOR.
