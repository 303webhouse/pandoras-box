# RH Book Reconciliation v2 — brief (filed artifact)

> **EDGE FILING WRAPPER — added 2026-08-25 per R-IV.76(g)(3).**
> Original authored 2026-08-17 in-lane, executed same day by CC (20 ops: 10 updates,
> 10 inserts, one transaction; pre-image at
> `backend/database/archive/2026-08-17-rh-book-reconciliation-v3-preimage.jsonl` era
> set, committed `b251b9e`). Item 18 was withheld at execution pending principal
> confirmation. Chat-held-only until this filing — casualty-class remediation.
>
> The wrapper is EDGE's; everything between the BEGIN/END markers is the original
> brief text, untouched.

<!-- BEGIN VERBATIM -->

RELAY → CC-SHELL — RH BOOK RECONCILIATION v2 (final) · 2026-08-17
Source: 8-4_RH_Trade_Updates.csv (fills 7/20–8/3, fees included in
all figures) diffed against hub_get_positions(robinhood, OPEN) on
08-05 and re-verified 08-17. Market closed; run at will. Apply
house lot-blending conventions; per-lot facts given. Echo
hub_get_positions after writes.

A · FIX existing rows
1. SPY 733/730 p-spread (POS_SPY_20260731_165120) — no longer
   OPEN; VERIFY closure: true qty was 1 (row said 3), entry 0.321,
   closed 8/3 at 0.059 credit → realized −26.20. Correct the
   closed record if the auto-close wrote qty-3 numbers.
2. POS_TSLA_20260729_132725 — strikes are 220/210 (not 210/200).
   Add 8/3 lot +1 @ 0.181 → final 220/210 ×3, blended 0.334.
3. POS_GLD_20260610_173759 (9/30 500/510 ×4) — CLOSED 8/3 via
   roll: exit credit 15.66 total → realized −42.44.
4. POS_OBE_20260713_231900 — partial close 7/23: sold 1 of 2 @
   0.41 vs 0.14 entry → realized +26.94; qty 2→1 remains OPEN
   (expires 8/21 — flag to Nick in echo).
5. POS_BX_20260724_182213 — fill long_strike = 60 (null now).

B · QUANTITY ADDS (new lots, per-spread net debit)
6.  PLTR 75/70 p ×+1 @ 0.151 (7/23) → qty 4
7.  SLV 120/130 c ×+1 @ 0.011 (7/20) → qty 5
8.  QQQ 510/500 p ×+1 @ 0.341 (7/24) → qty 3
    (optional true-up: 7/20 lot nets 0.311/spread, row says 0.24)
9.  QQQ 360/350 p ×+1 @ 0.081 (7/24) → qty 3
    (optional true-up: 7/20 lot nets 0.071/spread, row says 0.04)
10. XLF 45/40 p ×+1 @ 0.031 (7/23) → qty 3
11. XLF 30P long ×+1 @ 0.110 (7/23) → qty 3

C · INSERT missing OPEN positions
12. GLD 12/18 500/510 call debit ×4 @ 0.191 (8/3 roll target)
13. XLE 10/16 70/80 call debit ×3 @ 0.231 (8/3)
14. TRIN 10/16 12.50P long ×2 @ 0.100 avg (7/27, 7/28)
15. WEAT 10/16 29/30 call debit ×6 @ 0.051/spread, total debit
    30.52 (CONFIRMED by Nick: 6, two 3-lot fills)

D · INSERT completed round-trips
16. SOXS 10sh 7/20 → +20.57       17. BITX 50sh 7/21 → +2.01
18. SQQQ 10sh 7/22→23 → +17.91    19. AMC 8/21 3/7c ×2 → −16.36
20. GUSH 15.35sh 7/24→31 → +6.40  21. HYG 7/31 79/78.5p ×5 → −30.86
22. MSFT 8/3 430/425p ×3 expired worthless 8/3 → −47.28

E · VERIFY closed (pre-window entries; exits below; basis from
   house records; insert-as-closed if absent)
· TSLA 9/18 300/295p — closed 7/23, exit credit 174.88
· DRAM 9/18 40/36p — closed 7/28, exit credit 124.90
· XLE 7/31 60C — closed 7/24, +81.94
· XLE 8/21 60/65c — closed 7/31, exit credit 82.90
· XLF 7/31 53.5/48.5p ×5 — expired worthless 7/31 (OEXP leg-sides
  ambiguous in export)

F · Notes: ACH −250.00 on 7/24 (balances context). Data-quality
flag, no action: June HYG 77/65 row's max_loss (102) is
inconsistent with its own entry×qty (153 debit) — log for the
true-up pass.
COVERAGE ENDS 8/3. Trades from 8/4 onward are NOT in this brief.

<!-- END VERBATIM -->
