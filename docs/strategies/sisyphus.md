# SISYPHUS | Resistance Rejection (`RESISTANCE_REJECTION`)

| field | value |
|---|---|
| signal_type / strategy keys | `RESISTANCE_REJECTION` / "CTA Scanner" |
| emitting code | `check_resistance_rejection` (`backend/scanners/cta_scanner.py:1314`; type at `:1362`); only when shorts are allowed, which the equity scan passes |
| side | SHORT |
| grid cell | **WITH-TREND SHORT** (a failed retest of the 50-day from below) |
| schedule / trigger | the CTA `_scanner_loop`, trading days 9–16 ET, on a forming daily bar |
| status | **LIVE on liquid names, pending QUERY's read of its surfaced outcomes** (R-IV.879(b)). L0 `SUPPRESS_IF_NON_LIQUID` (`backend/config/l0_routing.py:76`): only the liquid universe surfaces |
| bucket ceiling | No provenance ceiling: C5 and F5 do not reach this cell |
| lifetime tries counter | unrecorded before LAB; unchanged by Task 8 |

## Rules as coded
The prior bar's high ≥ 0.99 × SMA50; today's close < the prior close; close < SMA50; volume
ratio ≥ 1.2 (a NaN ratio passes) (`cta_scanner.py:1314-1345`).

## Evidence so far
**Task 8 replay** (`roster-replay\01-TASK8-RESULTS.md`, `aac4303c…`), h3:

| subset | all | bull stack | **bear stack** | same-date (C), bear |
|---|---|---|---|---|
| **liquid names (what surfaces)** | −0.12% (t −1.74), 2,534 / 1,396 | −0.16 (t −1.91) | **+0.73 (t 1.82)**, 105 / 66 | **+0.81 (t 2.11)** |
| all names | −0.03 (t −0.77), 25,048 / 4,231 | −0.08 (t −2.02) | −0.09 (t −0.48) | +0.02 (t 0.09) |

- Bear-stack sessions are about 84% from two episodes (2008–09, 2022–23). **Not established**,
  but it is the only live short with any downtrend evidence. It loses in bull stacks.
- All names, h1: +0.04 (t 2.41), fading by h2.

## Change log
- 2026-01: CTA scanner. 2026-06-16: liquid-only routing (L0). 2026-10-12: card v0 (R-IV.879(b)).
