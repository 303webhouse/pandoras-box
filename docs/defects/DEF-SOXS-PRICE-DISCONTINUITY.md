# DEF-SOXS-PRICE-DISCONTINUITY

**Severity:** P2 sustained · **Registered:** 2026-08-19 (R-IV.86d, re-registration accepted;
P2 confirmed R-IV.91a) · **FILED AS A DOCUMENT:** 2026-09-05 (R-IV.258(a))
**Status:** OPEN — registration only. Cause UNKNOWN and deliberately not proposed.
**Owner:** CC-POSITIONS (evidence) · CC-BUILD (SOXS OHLC fetch, R-IV.90(c))
**Surface:** SOXS price series in `unified_positions` / `price_history` across 2026-05-13 → 06-10
**Supersedes:** `DEF-SPLIT-ADJUSTMENT-MIXED` — vacated; its name asserted a mechanism the
evidence does not support.

> **LINEAGE — this defect was registered in relay and never filed.** Between R-IV.86d
> (2026-08-19) and R-IV.258 (2026-09-05) it was cited as established in **6 documents across
> 8 citation lines**, including three that draw corroboration from it, with **no file of this
> name anywhere in the tree**. It existed as a name the corpus reasoned from. This stub is the
> first document behind it. The pre-existing citations:
>
> | document | line(s) |
> |---|---|
> | `docs/codex-briefs/RELAY_POSITIONS_to_SPINE_R-IV.86d.md` | 41 |
> | `docs/codex-briefs/RELAY_POSITIONS_to_SPINE_R-IV.91a.md` | 95 |
> | `docs/handoffs/EDGE-CLOSING-HANDOFF.md` | 248 |
> | `docs/incidents/DEF-SPLIT-ADJUSTMENT-MIXED_MECHANISM_CORRECTION.md` | 146 |
> | `docs/incidents/FIDELITY_HALVES_RECONCILIATION.md` | 100 |
> | `docs/incidents/FIDELITY_OVERLAP_VALIDATION_RESULT.md` | 116 · 156 · 255 |
>
> A seventh citing document, `docs/trading-theses.md:120`, was added 2026-09-05 by the
> negative instance below and is **not** part of the pre-file lineage. Counting discipline:
> 6 documents / 8 lines before today, 7 / 9 after — documents and lines are different counts
> and the distinction is why this table lists both.

---

## THE DEFECT

**Three discrete same-day price breaks** in the SOXS series, compounding to a cumulative
price error of **~4.05×**.

| break | date | factor |
|---|---|---|
| 1 | **2026-05-13** | 1.49× |
| 2 | **2026-05-26** | 1.51× |
| 3 | **2026-06-10** | 1.80× |
| | **compounded** | **4.05×** |

**Cause UNKNOWN and not proposed.** Three candidates are live and *not separable from DB
state*: mixed-source data entry, lot-averaging on partial closes, and a genuine non-10:1
corporate action. Leaving it unproposed is the registration's position, not an omission.

### The decomposition — and the part that is NOT a defect

```
 total observed move ....... 9.62×
 three breaks .............. 4.05×   <-- THE DEFECT
 residual .................. 2.38×   <-- ordinary decay for a -3x semi ETF, NOT a defect
```

**~4× is the defect; ~2.4× is not a defect at all.** POSITIONS previously counted the whole
9.62× as defective and that was wrong. Any remediation scoped to the total move will overshoot.

### Adjusted rows: exactly one

`POS_SOXS_20260610_154556` — and it is **already correct**. The scope is three dated
boundaries, not a date range and not a row population.

---

## FALSIFIED — do not re-derive these

Registered explicitly as dead so they are not rediscovered:

- the **10× ratio** as the defect's shape
- **date-range population** (the defect is three instants, not an interval)
- **boundary-crossing** as the selector
- the **04-07 / 14.33 pairing**

---

## CORROBORATION — two independent sources

**1 · `FIDELITY_HALVES_RECONCILIATION` (:100).** Measured against an external series:

| comparison | DB | external | ratio |
|---|---|---|---|
| raw vs raw | 4.0395 | ~6.15 | **1.52×** |
| adjusted vs adjusted | 40.395 | ~61.5 | **1.52×** |
| as stated in (f) | 40.395 *(adjusted)* | ~6.15 *(raw)* | 6.57× |

The real discrepancy is **~1.52×**, matching the independently measured 06-10 break of
**1.51×**. **The 6.57 figure embeds the factor of 10 that is supposed to be there.**

> **REMEDIATION TRAP — read before fixing anything.** A remediation targeting 6.57× would
> strip the ×10, which is *the one adjustment in the table that is correct*. That leaves a
> post-split-surviving position expressed in pre-split units and breaks the live mark. This is
> the same category error as the vacated `DEF-SPLIT-ADJUSTMENT-MIXED`, recurring inside its
> own substantiation.

**2 · `FIDELITY_OVERLAP_VALIDATION_RESULT` (:116, :156).** Second source, overlap window: the
DB holds `250` and `150` **raw** alongside `45` **adjusted** — same ticker, same window. That
is the mixed-unit condition, and it is **confined to SOXS**. The overlap test found only
defects already on the books and no new class of error.

---

## NEGATIVE INSTANCE — 2026-09-04 (R-IV.256(a))

**id 411 · SOXS ×7, entry 51.67 @ 2026-09-04 17:58Z, marked 46.34 — a −10.3% day-one move,
unrealized −37.31.**

POSITIONS filed this mark **UNVERIFIED** on 09-04: the quote source returned `unavailable`
for SOXS and SMH, and the bars series stopped at 09-03 (last close 51.60), so it could not be
adjudicated either way. This defect was the named suspect, on its own namesake ticker.

**Principal-verified 2026-09-05: the move is real price action. This defect is NOT
implicated.** Recorded because a defect that accumulates only positive instances stops being
falsifiable — and because the caution was correct to raise and resolved *against* the
position rather than in its favour.

---

## CLASS BOUNDARY — which breaks any artifact can reach

Per `FIDELITY_OVERLAP_VALIDATION_RESULT` (:255), the three breaks **straddle** the
attestation-tier boundary:

- **05-13** and **05-26** fall in **class A** — the attested interior, where **no broker
  artifact exists**. R-IV.91(d)'s check is the only artifact-level instrument on those two.
- **06-10** sits in **class B**.

This is why the resolving instrument below is bounded the way it is.

---

## WHAT RESOLVES IT

> **A broker export covering only 2026-05-13 → 2026-06-10 resolves this defect independently
> of PR-106.** (R-IV.86d §4)

A four-week export. It resolves a registered P2 on its own and falls inside the
05-27 → 06-18 overlap window, so it partially serves Task 2 as well. Only the principal can
place it.

---

## STATUS

Registration only. **No fix authorized, no trace run, no rows touched.** The SOXS OHLC fetch
is CC-BUILD's (R-IV.90(c)) and is not touched by this filing.
