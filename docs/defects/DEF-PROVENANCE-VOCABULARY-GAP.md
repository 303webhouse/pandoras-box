# DEF-PROVENANCE-VOCABULARY-GAP

**Severity:** P2 — evidence level understated on live rows · **Filed:** 2026-09-22 (R-IV.468(c))
**Author:** CC-POSITIONS — sole author under convention #9. **Status:** CLOSED 2026-09-23 (R-IV.476(d))
**Surface:** `provenance` on `unified_positions`, `position_lots`, `position_legs` — CHECK
`(PRINCIPAL_REPORTED, BROKER_VERIFIED, IMPORTED, UNKNOWN)`, plus
`unified_positions_verified_needs_evidence`: BROKER_VERIFIED requires `broker_ref`,
`verified_event` and `verified_at`.

## THE DEFECT

**Three rulings in a row named a provenance level the column cannot hold.**

| ruling | named | what the column can do |
|---|---|---|
| R-IV.466 | "provenance SCREEN_VERIFIED until an export line confirms" | **no such value** |
| R-IV.469(a) | "provenance SCREEN_VERIFIED" | **no such value** |
| R-IV.467(b), R-IV.468(a) | "BROKER_VERIFIED from this order screen" (row and lot 1) | the value exists but is **unreachable for this evidence** |

BROKER_VERIFIED is reachable only with a broker **reference**, a named matched event and a match
time. **A filled-order screen carries no reference.** So six rows entered on 2026-09-22 — HYG 516
and the five of R-IV.469 — and HYG 516's lot 1 all read `PRINCIPAL_REPORTED`, **the weakest claim
in the vocabulary**, while the ruling that created them named a stronger one.

## WHAT IT COST — the first case where per-lot provenance was to do real work, and could not

R-IV.468(c) commissioned this filing as *"the lots model's first case where a single position would
otherwise have carried one wrong evidence level for two different origins."* **HYG id 516 is that
case, and the model could not express it:**

| lot | fill | origin | ruled | stored |
|---|---|---|---|---|
| 1 | 3 @ 0.14 | the roll's open side — recorded here as a filled-order screen, **corrected by R-IV.480 to the export's own lines** (see RESIDUE RESTATED) | BROKER_VERIFIED | `PRINCIPAL_REPORTED` |
| 2 | 2 @ 0.13 | principal-reported, **no fill date supplied** | PRINCIPAL_REPORTED | `PRINCIPAL_REPORTED` |

**The two origins are genuinely different and the column says they are the same.** The lots model
did its half — two lots, two prices, two dates, one derived basis of 68.00 — and then both lots
took the same evidence label. **The distinction survives only in prose**, which is the state the
lots model exists to end.

## THE SHAPE, GENERALISED

**A broker-owned screen is stronger than the principal's recollection and weaker than a
confirmation with a reference.** The vocabulary has no rung between them, so every such reading
**rounds down to the weakest**. A reader cannot then tell "the principal remembered this" from
"the broker's own screen showed this", and the second is re-checkable against an export line while
the first is not.

Rounding down is the safe direction — it never overstates — but it is **lossy in a way that
matters for supersession**: when the RH export arrives, the rows that should be promoted to
BROKER_VERIFIED are indistinguishable from rows that never had broker evidence at all.

## REMEDY — BUILD's, and it is one of two

1. **Add `SCREEN_VERIFIED`** between PRINCIPAL_REPORTED and BROKER_VERIFIED, with its own
   evidence requirement (which screen, captured when, by whom) so it is a transition and not a
   free label — the shape BROKER_VERIFIED already has.
2. **Or rule that a screen is PRINCIPAL_REPORTED** and stop naming a stronger level in relays.
   Either is coherent; the present state — rulings naming a level the database refuses — is not.

**There is no third option.** Loosening BROKER_VERIFIED's evidence requirement is not available:
that constraint is the whole reason the value means anything (R-IV.448(b)).

## WHAT IS NOT ESTABLISHED

- **Whether other rulings have named levels the column cannot hold.** Not censused; these three
  were found by executing them.
- **Whether `SCREEN_VERIFIED` would have other writers.** Only this lane's hand-entry path uses
  it so far.

## ROWS CARRYING THE UNDERSTATEMENT TODAY

`516` (HYG 11/20 76/73, and both its lots), `517` AVGO, `518` IBIT, `519` TSLA, `520` NVDA,
`521` TJX. Each row's note names the ruled level and why the column does not carry it, so the
promotion is mechanical once the export lands.

---

## CLOSED 2026-09-23 — REMEDY 1, SHIPPED AND EXERCISED (R-IV.476(d))

**R-IV.470(a) took remedy 1 and BUILD shipped it** (`3e44243`, `migrations/052_screen_verified.sql`):
`SCREEN_VERIFIED` is its own transition with its own evidence — the fields read, the capture time,
and who transcribed it — ranking above PRINCIPAL_REPORTED and below BROKER_VERIFIED, whose
reference requirement is untouched. An export line supersedes it.

**Exercised on the six rows this DEF named**, then **read back by SQL — a different path from the
API that wrote them** (R-IV.476(c)). The first stamps had three defects, all corrected by
re-stamping:

| defect | correction |
|---|---|
| 516's evidence carried an **implied** entry (~0.1357, ~68.00) the screen never displayed | evidence now names instrument, legs, quantity, mark and total return only |
| the capture time echoed as `+00:00` | the offset is written explicitly: `12:44 -06:00 (18:44Z)` |
| the five said nothing about the relay's `~` | each now reads **APPROXIMATE** with the reason |

**Read-back after re-stamping is clean** on all six: level `SCREEN_VERIFIED`, capture time with an
explicit offset, approximate marked as approximate, and every named field one the screen showed.

### What this DEF does NOT close

- **HYG 516's lot 1 is still unstamped.** ~~Waiting on the capture time of the filled-order screen —
  the route requires it and no relay has stated it. Not a vocabulary gap: a missing fact.~~
  **SUPERSEDED 2026-09-23 by R-IV.480 — see RESIDUE RESTATED below.** The capture-time ask is
  withdrawn; the evidence is an export line, and what lot 1 awaits is the **IMPORTED reference
  shape**, not a fact.
- **`with-legs` writes `PRINCIPAL_REPORTED` whatever its `source`.** A row entered from an export
  through that path (TLT 523, VIX 524) cannot be labelled `IMPORTED`, so its label understates its
  evidence. That is the same class one path further down, and it is BUILD's.

---

## RESIDUE RESTATED 2026-09-23 (R-IV.480, relayed in R-IV.481(b))

**The capture-time ask is WITHDRAWN.** It was the wrong question. HYG 516 lot 1's evidence is not a
screenshot at all — it is **the roll's own open legs in the export**:

| | |
|---|---|
| file | `data/imports/rh-8.31.2026.csv` |
| sha256 | `b7fce7073c1d8e6ea7b35323ad1ed532cdba60b785c3846960b550eec8bbb16d` |
| records | **L40–L41**, within the roll's L38–L41 (record numbering: header = L1, a CSV row spanning two physical lines counts once) |
| L40 | `8/20/2026 · HYG 11/20/2026 Put $73.00 · STO · 3 · $0.15 · $44.86` |
| L41 | `8/20/2026 · HYG 11/20/2026 Put $76.00 · BTO · 3 · $0.29 · ($87.12)` |
| derived | net 0.29 − 0.15 = **0.14 × 3** — exactly lot 1 as stored |

So lot 1 was never waiting on a missing fact. It was waiting on a **reference shape**: an export
line is a stronger, re-checkable evidence than any screen, and the level for it is `IMPORTED`.

**Lot 1 awaits the IMPORTED reference shape.** `IMPORTED` is in the CHECK vocabulary today, but no
write path accepts the only reference an export line has — **a file sha256 plus record numbers**.
BROKER_VERIFIED's evidence triple (`broker_ref`, `verified_event`, `verified_at`) does not fit a CSV
row, and `SCREEN_VERIFIED` names a screen this lot does not have. Until BUILD's path accepts
`sha256 + line numbers` as the reference for `IMPORTED` (**R-IV.477(i)**), lot 1 **stays as it is**
at `PRINCIPAL_REPORTED` — understated, and now understated against evidence that is on file rather
than against a screen nobody can re-open.

**This is the same gap as the `with-legs` item above, one rung higher:** that path cannot *write*
`IMPORTED`; this reference shape cannot *be expressed* for `IMPORTED`. Both are BUILD's, and the
second is the one that unblocks every future export-entered lot, not just this one.
