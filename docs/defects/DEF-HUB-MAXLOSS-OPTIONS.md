# DEF-HUB-MAXLOSS-OPTIONS

**Severity:** P2 · **Filed:** 2026-09-03 (R-IV.207(d)) · **Class:** FAKE-HEALTHY
**Status:** OPEN — registration only. Trace and fix HELD in BUILD's queue.
**Owner:** CC-POSITIONS (evidence) · CC-BUILD (surface)
**Surface:** `unified_positions.max_loss` on option/spread rows
**Interim rule:** filed into `docs/trading-theses.md` → Standing rules

## THE DEFECT

`max_loss` on option rows disagrees with the position's actual risk and **overstates it**,
while two independent derivations agree with each other:

```
id 365  XLE 70/80 call debit ×1   entry 0.231       max_loss  69.30
        entry x qty x 100 = 23.10 · cost_basis = 23.10 · unrealized_pnl +38.90 on a 23.10 basis
        -> max_loss overstates by 3.00x

id 367  WEAT 29/30 call debit ×3  entry 0.0508667   max_loss  30.52
        entry x qty x 100 = 15.26 · cost_basis = 15.26
        -> max_loss overstates by 2.00x
```

A debit spread cannot lose more than its debit. `max_loss` claims otherwise on both rows,
and `cost_basis` and the P&L arithmetic both contradict it. The factor is not constant
(3.00x and 2.00x), so it is not one scalar error — mechanism unknown and **not proposed here.**

## WHY FAKE-HEALTHY

`max_loss` reads as the conservative field — the one a sizing check would trust. Here it is
the wrong one, and wrong in the direction that *looks* safe. A consumer summing `max_loss`
believes it is being careful while working from inflated numbers.

**Demonstrated consequence, same session:** the D5 commodity/inflation sleeve totals
**$3,845.08** on cost basis against a **$3,850** cap — $4.92 of headroom, sleeve closed.
Summing `max_loss` for its three option members instead gives **$3,906.54**, a phantom
**$56.54 breach** of a cap that is not in fact breached. The wrong field inverts the answer.

## SCOPE — measured, and smaller than the raw count suggests

Across all 19 open option/spread rows with a non-null `entry_price`:

```
open option rows ........................ 19
carry max_loss .......................... 18
disagree with entry x qty x 100 ..........  7
  ...of which OVERSTATE ..................  2   <- this defect (XLE 365, WEAT 367)
  ...of which UNDERSTATE .................  5   <- NOT this defect, see below
```

**The five understating rows are not instances.** They are the R-IV.105-b quantity raises
(QQQ 355/356, XLF 300/301, TSLA 360) where quantity was raised and `entry_price`/`cost_basis`
were deliberately left at original vintage under the **BLENDED-UNRECORDED** carve-out — "do
not invent a weighted average silently". Their `max_loss` equals their `cost_basis` exactly;
both are stale relative to the new quantity, by design and on the record. Recorded so the
trace does not chase five phantom instances.

**Correction to the filing brief:** R-IV.207(d) cites "the same disagreement on QQQ 510/500".
QQQ id 355 does disagree with the derived basis (112.40 vs 224.80) but in the **opposite
direction** and for the **known blended-basis reason** — its `max_loss` and `cost_basis`
agree with each other. It is not a second instance of this defect. WEAT id 367 is, and was
not named in the brief.

## INTERIM RULE (in force, filed to the standing-rules section)

- **Never size off `max_loss`.**
- **Derive** `entry_price × quantity × 100`; **cross-check** against `unrealized_pnl`.
- Binds until this defect is closed.

## WHAT IS NOT ESTABLISHED

- **Mechanism.** Two instances, two different multipliers. Not one scalar bug on this evidence.
- **Whether closed rows are affected.** Only open rows were scanned.
- **Whether `max_loss` is ever right.** 11 of 18 agree with the derived basis; whether that is
  correctness or coincidence of structure is untested.

## REMEDIATION

**HELD.** No fix attempted, no `max_loss` value written or corrected by this lane.
