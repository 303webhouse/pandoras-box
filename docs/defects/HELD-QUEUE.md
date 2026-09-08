# HELD DOCS QUEUE — CC-BUILD

Items registered and recorded but **not scheduled**. Each has an artifact so it is not a
phantom; none is claimed to be diagnosed. Ordered by nothing — sequencing is spine's.

**Created** 2026-09-05 (R-IV.263(c)). **Owner** CC-BUILD.

---

## READ FIRST — WHERE STAGED ARTIFACTS ACTUALLY LIVE

**The ferry directory is `C:\temp\cc-query-handoff\`. It is outside both git trees.**

Staged files arrive there under **UPPERCASE** names and are filed into the repo under
**lowercase** ones — e.g. `2026-09-05-PHANTOM-REGISTRATION-SWEEP.md` became `docs/edge/results/2026-09-05-phantom-registration-sweep.md`. **Sixteen of the
thirty-five files in that directory have already been filed this way.**

**Why this is pinned.** On 2026-09-05 this lane reported a staged census as *"not on any
reachable path"* **three times**, after sweeping `C:\th-build`, `C:\trading-hub` and
Downloads by content hash. The file was present the whole time, at the ferry path, gate
matching exactly. **The sweep was exhaustive over the wrong set.**

**The lesson is not about this directory.** A negative result is a property of **where you
looked**, never of the thing you were looking for — and reporting it as the latter sends
another lane to re-stage an artifact that was already staged. **State the search scope with
every negative finding**, so a reader can see the hole rather than infer its absence. This
is the probe-artifact family (a `limit=` that is not a parameter, a `cut -c` truncation, a
`grep -c` counting lines not characters) arriving as a search boundary rather than a tool
flag.

**When an artifact cannot be found: name the paths searched, before concluding anything.**

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

**MOVED OUT OF HELD 2026-09-07 (R-IV.308(a)):** the **account-string write-path trace** is
now **in scope for the ledger-integrity build** as T6c. It was parked as a read-only
investigation of a label problem; TA-003 showed the same write path producing **four wrong
fields on one money row** (id 409: qty, entry, trade date, account). **A label defect and a
numeric defect turned out to be one unguarded write**, which is why it stops being a
question and becomes a task.

## SINKS BUILD — A PRECONDITION THAT MUST NOT BE INHERITED

**Raised by CC-QUERY on the census relay, recorded here so the sinks build cannot lose it.**

R-IV.276 resolved UW-side backfill support **for tide only**, read from the unusualwhales
MCP tool description (`market_tide` with *date optional, interval_5m optional*). **That
description says nothing about `/api/darkpool/{TICKER}`**, and the two endpoints are not the same shape —
one is a market-wide time series, the other a per-ticker print list.

**Leg (d)'s backfill support is UNMEASURED.** Both legs sat in one paragraph of the census
and share a concluding sentence, which is exactly how one inherits the other's answer
without evidence.

**BUILD's obligation, in the sinks build:** when tide is confirmed against the live
endpoint, **dark pool is confirmed separately in the same pass.** A single confirmation
covering both is not acceptable, because *backfillable* versus *forward-only* is precisely
what the Hunter would be claiming about its own history.

**And the consequence is asymmetric.** Tide is one market-wide series; dark pool is
per-ticker across the universe. **If dark pool IS backfillable, the draw is large enough
that AEGIS sizing applies before anything ships** — the 2026-07-17 watchdog-shed precedent.

**Both pollers are currently PAUSED** (R-IV.273(c)), so neither is accruing history while
this is unresolved. Nothing is lost by the pause; the backfill question is what decides
whether anything can be recovered.

## HELD — CALENDAR MIGRATION (R-IV.320(b))

**Sequenced BEHIND sinks and ledger. Small, mechanical, and not to be pulled forward.**

T7 built `backend/stable_engine/market_calendar.py` and wired the **three consumers the grader brief ruled**. The
rest of the tree still approximates.

**Measured 2026-09-08, stated with its scope:** the weekday rule appears in **~55 sites**
across `backend/`, and there are **THREE separate `is_trading_day()` implementations**, none of them the
calendar:

| implementation | site |
|---|---|
| bias scheduler's | `scheduler/bias_scheduler.py:2070` |
| discord bridge's | `discord_bridge/bot.py:241` |
| score_signals' | `jobs/score_signals.py:86` |

**The discord bridge's is the one already known to be wrong** — it computes eight
holidays from rules and **omits Juneteenth and Good Friday**, so it reports the market open
on both, every year.

**Why it is held rather than done.** It is a wide, low-risk edit across subsystems this
build has not measured, and **the three ruled consumers are the ones with a live defect
behind them.** A migration that touches fifty-five call sites on the evening of a deploy is
how a small correct change becomes an incident.

**Why it is registered rather than left.** Three competing implementations of one question
is the shape that produced the family in the first place — **and the calendar has now made
it four unless the others are retired.** Adding a correct implementation beside three wrong
ones is not obviously progress; it is progress only if the migration follows.

## Not held — position one

The grader precondition build. Brief drafted at `docs/codex-briefs/2026-09-04-grader-precondition-brief-DRAFT.md`, **awaiting ATLAS/AEGIS**.
No code until that returns.
