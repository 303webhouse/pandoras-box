# MIDAS | Golden Touch (`GOLDEN_TOUCH`)

| field | value |
|---|---|
| signal_type / strategy keys | `GOLDEN_TOUCH` / "CTA Scanner" (equities) and "Crypto Scanner" |
| emitting code | `check_golden_touch` (`backend/scanners/cta_scanner.py:708`; type at `:780`); its LONG is stripped when the death cross is active (`:1427-1432`) |
| side | LONG |
| grid cell | **WITH-TREND LONG** (a deep pullback to the 120-day inside an intact uptrend) |
| schedule / trigger | the CTA `_scanner_loop`, trading days 9–16 ET, on a forming daily bar; also the crypto scanner |
| status | **LIVE, pending QUERY's read of its surfaced outcomes** (R-IV.879(b)); L0 default KEEP. The read is to be filled in from QUERY's relabelled R-IV.880 reissue when it lands. **The live figure is NOT CITABLE: 152 of 178 rows are INVALIDATED,** because the invalidation level sits above the entry. The fix is approved (R-IV.894(c)) and pending in BUILD's versioned grader fix |
| bucket ceiling | No provenance ceiling: C5 and F5 do not reach this cell |
| lifetime tries counter | ≥ 1: the volume threshold was retuned 2.00 → 1.30 (`backend/scanners/cta_scanner.py:105`); earlier tries unrecorded; unchanged by Task 8 |

## Rules as coded
In the last 3 bars, low ≤ 1.01 × SMA120 and close ≥ 0.99 × SMA120; at least 30 days above the
120-day; a 5–12% correction from the 60-bar high; SMA20 > SMA120; volume ratio ≥ 1.3 in the touch
window (`cta_scanner.py:708-770`).

## Evidence so far
**Task 8 replay** (`roster-replay\01-TASK8-RESULTS.md`, `aac4303c…`; method as in the HECTOR card).
h3:
- **all +0.01% (t 0.28)**, 6,150 / 2,508; same-date difference −0.01 (t −0.35);
- bull stack +0.05 (t 1.09); **bear stack −0.42 (t −1.54)**, 174 / 91, same-date −0.72 (t −2.37);
- transition −0.06 (t −0.82); range +0.03 (t 0.29); sector ETFs −0.10 (t −1.74).
- **No edge in replay.** The decision waits on QUERY's read of the rows it actually surfaced.

## Change log
- 2026-01: CTA scanner. 2026-10-12: card v0 (R-IV.879(b)). 2026-10-12: live figure marked not citable (R-IV.898(a)). Invalidation spec approved (R-IV.894(c)): `min(SMA120 − 0.25·ATR, entry − 0.25·ATR)`.
