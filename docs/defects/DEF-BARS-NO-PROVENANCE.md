# DEF-BARS-NO-PROVENANCE

> **STUB — R-IV.263(c), 2026-09-05.** Filed to retire a phantom, not to diagnose one.
> **Everything below is read from CITING CONTEXT ONLY. No investigation was performed**,
> no code was read for this stub, and nothing here is a measurement by this lane.
> Citations counted mechanically over `docs/` at HEAD `727d609`.

**Cited:** 8 times across 3 files (this lane's count; the sweep states 9 — the
difference is one citation outside `docs/` or a counting-scope difference, unreconciled
and not material to the stub).

## What the citations say

Every citation is the same Clause-1 line in `docs/edge/preregistrations/PR-106-ARMS-PART1.md`:

> bars PROVIDER yfinance (uniform, VERIFIED per-series via the per-bar provider field
> shipped in `727d609`773; DEF-BARS-NO-PROVENANCE closed)

## Status: CLOSED IN CODE, ARTIFACT NEVER FILED

**This is not an open defect.** The fix shipped at `727d609`773 — a `provider` tag applied
at both live return points in `backend/integrations/uw_api.py`, before the cache write, so cached series carry the
provider they were fetched under. The closure is what the citations assert, and the
per-series verification behind them is what let the arms artifact state a uniform
provider rather than assume one.

**The phantom is bookkeeping only.** A defect was found, fixed, verified, and cited as
closed — and never acquired a file. That is precisely the case the R-IV.263(b) convention
describes: registration and filing came apart, and the name entered circulation with
nothing behind it.

## What a real artifact would still need

The citations assert closure; they do not record the original symptom, the discovery, or
the verification method. If this is ever wanted as a proper record rather than a stub,
it needs the pre-fix behaviour written down — which is not recoverable from the citations
and is not invented here.
