# HELD DOCS QUEUE — CC-BUILD

Items registered and recorded but **not scheduled**. Each has an artifact so it is not a
phantom; none is claimed to be diagnosed. Ordered by nothing — sequencing is spine's.

**Created** 2026-09-05 (R-IV.263(c)). **Owner** CC-BUILD.

---

## READ FIRST — the split-adjustment remediation trap

**Anyone touching split adjustments reads this before writing a line.** Pinned per
R-IV.263(d) from `docs/defects/DEF-SOXS-PRICE-DISCONTINUITY.md`:

> **REMEDIATION TRAP — read before fixing anything.** A remediation targeting 6.57x would
> strip the x10, which is *the one adjustment in the table that is correct*. That leaves a
> post-split-surviving position expressed in pre-split units and breaks the live mark. This
> is the same category error as the vacated `DEF-SPLIT-ADJUSTMENT-MIXED`, recurring inside its own
> substantiation.

**Why it is pinned at the top of a queue rather than left in its own file.** The trap is
not a property of the SOXS defect — it is a property of *the obvious fix* for it. A
reader who arrives with a ticket saying "reconcile the 6.57x discrepancy" will do exactly
the wrong thing, confidently, and the result is a **broken live mark on a real position**
rather than a stale document.

The real discrepancy is **~1.52x**, matching the independently measured 06-10 break of
1.51x. **The 6.57 figure embeds the factor of ten that is supposed to be there.** Fixing
the number you were handed destroys the adjustment that was already right.

Note what the trap did: the category error it describes is the one that was already
vacated once as `DEF-SPLIT-ADJUSTMENT-MIXED`, and it came back **inside the substantiation of its own
successor**. A vacated error is not a retired one.

---

## HELD — phantom stubs, R-IV.263(c)

Filed from **citing context only**. No investigation was performed on any of them; each
stub says so on its own face. They exist so the names stop being phantoms, and so the
next reader starts from what is written rather than from nothing.

| defect | citations | status on the citations |
|---|---|---|
| `DEF-BARS-NO-PROVENANCE` | 8 in 3 files | **CLOSED IN CODE** at `773e7a8`; artifact never filed |
| `DEF-BGTASK-NO-SUPERVISION` | 4 in 2 files | OPEN (P2). Possible parent of DEF-TRITON-GRADER-DARK — lead, not conclusion |
| `DEF-DB-VOLUME-CEILING` | 4 in 2 files | **SUPERSEDED** by the PGSS registration; stub is a pointer |
| `DEF-BIAS-WEIGHT-NULL` | 4 in 3 files | OPEN (P2), "still unshipped", called a one-line fix |
| `DEF-MCP-LENS-TZ` | 4 in 3 files | Brief AUTHORED ELSEWHERE; no artifact under this name |

**Two of the five were never open.** One was fixed and one was superseded, and both kept
being cited under names with no file behind them. **Phantom is a bookkeeping fact, not a
claim about the defect** — the sweep measures whether a name resolves, not whether work
was done.

## HELD — registered, awaiting sequence

| item | authority | gate |
|---|---|---|
| DEF-STRIKE-WATERMARK-NEVER-ALIVE fix | R-IV.225(c) | universe stabilises after the RE10045 restarts |
| DEF-STRIKE-WATERMARK-HOLIDAY fix | R-IV.199(a) | ACCEPT-UNFIXED; interacts with the never-alive n-gate |
| DEF-TRADES-DESTRUCTIVE-REBUILD fix | R-IV.210(c) | DO-NOT-RUN is the interim control; **facet 4 arms facet 2** |
| DEF-SIGNAL-STATUS-DISCARDED widening | R-IV.178(a) | 3DTE-lane investigation, post-push |
| DEF-MARK-INTEGRITY facets A and B | R-IV.252(d) | HELD; facet B arms when the mark path restarts |
| 178(a) re-issue | R-IV.252(b) | spine-held, executor CC-BUILD when sequenced |

## Not held — position one

The grader precondition build. Brief drafted at `docs/codex-briefs/2026-09-04-grader-precondition-brief-DRAFT.md`, **awaiting ATLAS/AEGIS**.
No code until that returns.
