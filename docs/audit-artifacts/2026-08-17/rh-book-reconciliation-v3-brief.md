# RH Book Reconciliation v3 — brief (filed artifact)

> **EDGE FILING WRAPPER — added 2026-08-25 per R-IV.76(g)(3).**
> Original authored 2026-08-17 in-lane, executed same day (hub echo: 22 open,
> $1,175.48 at risk); item 18 held NICK-VERIFY at execution, confirmed 2026-08-18
> ("SOXS confirmed") and inserted as `POS_SOXS_20260817_130011` with
> DEF-UNIFIED-QTY-INTEGER noted on the row. Window realized reconciled to +35.74
> position-level (+0.01 stock-lending cash line). Chat-held-only until this filing
> — casualty-class remediation.
>
> The wrapper is EDGE's; everything between the BEGIN/END markers is the original
> brief text, untouched.

<!-- BEGIN VERBATIM -->

RELAY → CC-SHELL — RH BOOK RECONCILIATION v3 (vacation delta
8/5–8/17)
Source: RH_Report_8_17_26.csv (fees included) +
Positions_8_17_26.PNG cross-check, diffed against post-v2 hub
book. Market closed; run at will. House blending; per-lot facts
given. Echo positions after.

A · FIX + CLOSE
1. OBE (POS_OBE_20260713) — original qty was 3, not 2 (CSV: sold
   1 on 7/23 + 2 on 8/11; entry basis 3 @ 0.14 = 42.00). Close
   remaining: 8/11 exit 2 @ 0.10 → realized −8.10 on final lot.
   Position fully CLOSED. Lifetime: proceeds 60.84 vs basis 42.00
   → +18.84 total (v2's +26.94 partial stands; this books the
   −8.10 remainder).
2. HYG June 77/65 (POS_HYG_20260603) — true-up entry to RH basis:
   122.01 total (0.4067/spread ×3), replacing 0.51; resolves the
   max_loss inconsistency flagged in v2-F.
3. GLD 12/18 500/510 (POS_GLD_20260803) — fully CLOSED in two
   lots: 8/7 ×2 exit credit 83.81 → +45.61; 8/17 ×2 exit credit
   79.81 → +41.61. Total realized +87.22.
4. PLTR 9/18 75/70 (POS_PLTR_20260609) — closed 3 of 4 on 8/10
   for net −3.26 (paid to exit) → realized −52.16. Qty 4→1
   remains OPEN.

B · QUANTITY ADDS (new lots, per-spread net)
5. QQQ 510/500 p: +1 @ 0.161 (8/5) → qty 4, blended 0.281
6. QQQ 360/350 p: +1 @ −0.009 CREDIT (8/5, legged) → qty 4,
   blended 0.0535
7. ORCL 65/60 p: +1 @ 0.211 (8/11) → qty 2, blended 0.406
8. XLF 45/40 p: +1 @ −0.029 CREDIT (8/17, legged) → qty 4,
   blended 0.1455
9. XLF 30P long: +1 @ 0.0804 (8/17) → qty 4, blended 0.0826
10. TSLA 220/210 p: +2 @ 0.0309 (8/17) → qty 5, blended 0.2129

C · INSERT new OPEN positions
11. PLTR 12/18 85/80 put debit ×3 @ 0.1409 (8/10 roll target)
12. IBIT 8/31 40/45 call debit ×4 @ 0.1059 (lots: 8/10 ×2
    @0.1609, 8/17 ×2 @0.0509)
13. UVXY 9/18 40/45 call debit ×4 @ 0.1409 (8/11, two lots
    @0.0809/@0.2009)
14. UBER 10/16 60/55 put debit — opened ×4 @ 0.1209 (8/11),
    closed ×2 on 8/17 @ 0.1391 credit → realized +3.64; insert
    ×2 OPEN remaining @ 0.1209
15. ABNB 10/16 140/130 put debit ×2 @ 0.2009 (8/11)
16. SPCX 10/16 60/55 put debit ×3 @ 0.081 (8/11, three 1-lot
    fills — corroborated by screenshot basis, no WEAT-style
    ambiguity)
17. TGT 8/28 130/125 put debit ×2 @ 0.2009 (8/17 — note 11 DTE)
18. SOXS equity 6.185477 sh @ 38.48 avg, basis 238.00 (8/17,
    three fills) — NICK VERIFY: absent from the 8/17 screenshot,
    likely taken pre-fill; confirm in-app before insert

D · INSERT completed round-trips
19. SOXS 8.185061 sh, 8/5–8/6 → 8/11 @ 44.00 → realized +5.14
    (+0.01 stock-lending, cash line)

E · Coverage now 7/20 → 8/17 EOD complete. Realized this window:
+87.22 GLD, +5.14 SOXS, +3.64 UBER, −52.16 PLTR, −8.10 OBE =
+35.75 net. Non-trade: SLIP +0.01.

<!-- END VERBATIM -->
