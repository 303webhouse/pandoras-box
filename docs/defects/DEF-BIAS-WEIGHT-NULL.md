# DEF-BIAS-WEIGHT-NULL · P2 (per citation)

> **STUB — R-IV.263(c), 2026-09-05.** Filed to retire a phantom, not to diagnose one.
> **Everything below is read from CITING CONTEXT ONLY. No investigation was performed**,
> no code was read for this stub, and nothing here is a measurement by this lane.
> Citations counted mechanically over `docs/` at HEAD `727d609`.

**Cited:** 4 times across 3 files, including the EDGE lane charter's P7 row.

## What the citations say

> **R5 / DEF-BIAS-WEIGHT-NULL still unshipped.** Factor weights are hardcoded in
> `FACTOR_CONFIG` but serialize as `None` in the hub …

> ### 4.5 Hub exposure — **DEF-BIAS-WEIGHT-NULL (P2)**, one-line + one optional

## Status: OPEN and explicitly UNSHIPPED on the citations

The shape: the weights **exist and are correct in code** — `FACTOR_CONFIG` is asserted at
import to sum to 1.00 — but the hub surface serialises them as `None`. So a consumer
reading weights through the hub gets nulls for values the engine holds.

**This is the compute-then-discard family**, the same shape as the coverage ratio that
was computed as a divisor and thrown away: the information exists at the point of
serialisation and does not survive it. Noted as a family resemblance from the citation
text, not from a code read.

**The citations call the fix "one-line + one optional"**, which is why "still unshipped"
is the striking part rather than the size.

## What a real artifact would need

The hub serialisation path and whether the null is a projection choice or an omission.
Not read here.
