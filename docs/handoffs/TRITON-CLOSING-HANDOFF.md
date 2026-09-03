# TRITON CLOSING HANDOFF — OLYMPUS-TRITON → SPINE

**Authority:** R-IV.230 (consolidation; lane function moves to spine) · **Authored:** 2026-09-03
**Registration of record:** origin blob `1fd693ff`, gate `bb2ae40c` — cite the blob, never the ferry copies. **T0: declared at R-IV.229.** Window clock: starts at the first session after P1/P2 verify live, per §2 of the registration.
**Channel note:** authored in-container after a live DC drop mid-first-chunk (the conditional operating as filed: app-down → fallback, not failure). The authored gate below is measured on these bytes. **A partial ghost of §1 may exist at the destination path from the aborted write — the ferry is overwrite-then-verify, never append.** Delivery asserts when a path-reading lane reproduces the gate at the path.

This document is written to be sufficient without its author. Counts carry addresses; expectations are stated so a surprise is detectable as one.

---

## §1 · OPEN READS AWAITED — owners, expectations, tripwires

**R1 — Q4 vacuous-conditioning sweep** (CC-QUERY/DC; commissioned R-IV.152, approved R-IV.154). Repo-wide sweep for readers of dark-pool keys on `enrichment_data`. Declared expectation: **zero scoring consumers** (`confluence_bonus=0` by founding design); display-path readers possible — any reader found has been reading absence since inception. Tripwire on return: any *scoring* consumer → defect registration at elevated severity. Nothing ratified conditions on this result.

**R2 — Q5 whale reachability read** (commissioned R-IV.152/154). Is `whale_hunter_v2` wired to a live webhook route, and does the `DARK_POOL` classification branch depend on data that never persisted (which would explain zero fires by construction). FOLD-AND-PARK does not condition on it; any revival requires its own registration and must answer the two-instrument convergence against the mega-cap tier (PR-106 worst cell + tercile inversion, `triton-shadow-audit-2026-07.md` §4).

**R3 — Friday's grader mechanism diagnosis** (CC-BUILD, queue position one; the window's opening act). Two riders folded in, results previously dual-routed to this lane — **now route to spine**: (a) grade-identity stratification per R-IV.213(f) — sample MUST include post-repair-graded rows; one exercise answers external correctness and cross-repair consistency; (b) the watchdog-premise contradiction — 307 graded rows carry fire-dates 07-10/07-13 the brief records as fully shed — plus the re-key rider ruled one-object with it.

**R4 — T0 census** (CC-QUERY, per registered §8.2 I2b). The between-populations cohort — `id > 377783 AND fired_at < T0` — counted at T0, sub-stated by fired-date bucket: holdout-era late arrivals (the tilt cohort) vs post-pin fires. Expected nonzero (106 measured on 09-01 alone). **Zero would itself be a finding** (poller dark through the interregnum).

**R5 — Holdout late-arrival tilt check** (asked of CC-QUERY pre-registration: rows-per-day across `id 305533…377783`; whether 08-28→08-31 run materially below the 08-17→08-27 daily average). Stated per the phrasing law: **not present in my inputs** — if it returned, it did not reach this lane. If never run: one metadata read whose result takes a face line on the criterion-(v) artifact either way.

## §2 · TRIGGERED CONDITION REQUIRING A DECISION — do not let this one bury

The ratified PERSIST-with-hard-pause call (re-scope §4, R-IV.213(d)) reads: *if no sink is live by forward-window T0, the dark-pool poller pauses by flag.* **T0 was declared today. No sink is live — the briefs are not even filed (§3). As written, the pause condition has FIRED.**

Disposition belongs to the principal at the PIVOT pass (the 2.7% is his spend), with three options: **(a)** pause now by flag, 48h watch — any breakage identifies the hidden runtime consumer R1 hasn't swept, itself diagnostic; **(b)** amend the trigger date to the window *clock start* (P1/P2-verify) or a named sink-ship date, and persist to it — closest to the clause's drafted intent, since T0 arrived faster than any build could; **(c)** persist indefinitely — not recommended; it re-opens the exact discard the measurement closed. Until the pass rules, the literal state is: **condition fired, execution held for the principal's decision.** That sentence should appear wherever the spend is next discussed.

## §3 · UNDELIVERED COMMITMENT — sink briefs

Drafting was authorized (R-IV.213(d)) and declared in progress by this lane; **no brief artifact was filed before consolidation.** The obligation transfers with its constraints, all previously ratified: typed tables preferred — `darkpool_prints` (per-print) and `market_tide_history` (per-snapshot); `uw_snapshots` evaluated CANDIDATE-NOT-PREFERRED (semantic mismatch; never-called writer flagged for deprecation review); the dp enricher **additionally writes its computed keys into `enrichment_data`** (the one-line fix for the silent no-op); five-defect collector design law binds (re-scope §5); AEGIS sizes the incremental UW draw before anything ships (07-17 watchdog-shed precedent); builds Titans-gated; queue position two behind the grader work.

## §4 · PIVOT-PASS AGENDA — as this lane would frame it (schedules after NFP, per R-IV.229(d))

**Pre-review sequence runs standard, with one hard gate:** every `hub_get_market_profile` read carries a per-ticker last-event freshness check. The PYTHIA feed collapsed 212→6 (survivors: AMD, AMZN, IWM, RKLB, SPCX, SPY; QQQ dead 09-01 10:30 ET, SMH 11:30 ET). MP for non-survivors is skipped or rendered loudly stale — a corpse renders with ordinary formatting, which is the whole hazard.

**Three decisions, one sitting:**
1. **Bless EXTEND.** Plain language: the premise wasn't killed (the 3d read is real) and wasn't promoted (one week carried the whole result; the biggest prints performed worst — the same tier PR-106 says is your worst personal cell; the effect hasn't yet paid for its own friction).
2. **Bless the seven-week test as registered** — five criteria, PROMOTE/RETIRE semantics, and the anti-drift clause verbatim: *no third EXTEND without a new instrument class: a leg, not more of the same.*
3. **Rule the spend (§2 above)** — pause now, persist-to-a-new-date, or persist. Recommendation on record: (b).
**Context riders:** PYTHIA collapse recap + SPEC-01 re-scope pointer (STRIKE's lane, not this pass's decision) · grader-diagnosis results if landed · the plain-language accounting owed, closing on §7(d)'s sentence **as written**: "six days of machinery, one exposure event caught in twenty-five seconds by its own tripwire, a premise neither killed nor promoted, and an instrument set now clean enough that the next answer will be believable."

## §5 · FENCED ITEMS & HELD EXPECTATIONS — stated so surprises are detectable

- **The seal:** n = 843 total · **828 gradeable = effective validation n** · 15 index rows never grade. Read **once**, only on a passing window, per §8.6's refutation form under the R-IV.186 firewall; mandatory face statement verbatim; PASS means does-not-contradict, never confirmed-twice. RELEASE clause adopted (R-IV.229(b)) — **verify BUILD's one-quoted-anchor edit lands in the holdout registration** with chain line "→ R-IV.229 — RELEASE clause adopted." Open until seen on origin.
- **Post-repair expectation:** when the grader backfills, the holdout grades to **828, not 843** — any completion monitor keyed to 843 waits forever; a shortfall to 828 is the k=15, not a fresh stall.
- **I1 forever:** `count(id ≤ 377783 AND fired_at ≥ 2026-08-17) == 843` at every read; deviation = seal breach, HALT.
- **§8.4 band:** 1,900–8,400 gradeable over 7 weeks, central ~2,500; outside = face-stated finding, not HALT (T7 deliberately non-HALT). Zero index rows in-window = finding (class unexercised, T3 untested).
- **C4:** criterial 0.25 pp; sensitivities 0.10/0.25/0.50 reported; **verdict binds on no-flip**; scope on the face — underlying-equivalent claim only, options gate at L1a.
- **Jurisdiction:** the audit disposed the **sweep premise only**; dark-pool/absorption/tide/timing pillars untouched in both directions. Triad dissolved; legs earn entry — footprint (558 rows, live, `strategy=` not `source=` for scoping, 3.8× under-count trap) is the only other leg with history; its marginal test has never run and is eligible post-window.
- **Defects:** five registered + NO-SINK pair at `3bcf4b3` (`DEF-TRITON-NO-SINK.md`, `f14c11d6`). RETENTION-DARK fix stays **BLOCKED** pending residue documentation; any restored policy must be grader-gated. INDEX-UNGRADEABLE is **ongoing** — index rows keep arriving. `DEF-TRADES-DESTRUCTIVE-REBUILD` (P1, sibling table) is BOOK/POSITIONS turf, cited here only as I2a's reachability.
- **R-IV.229 clearance line:** this lane answered the PYTHIA-collapse question against the registration post-declaration (window reads `triton_flow_shadow`, not `pythia_events`); the requested annotation on R-IV.229 — "asked and answered post-declaration" — is **open at spine's desk.**

## §6 · STANDING PRACTICES & CHANNEL CONDITIONS — transfer as operating notes

Scoped counts ship with their complement's status (`#scoped-count`) · cautions name the one inference they protect (`#narrow-caution`) · every registered predicate declares expected satisfaction, HALT on mismatch, 0%/100% agreements demonstrate reachability (`#null-trigger` §1.1) · tallies carry addresses (host artifact + line) or they are not citable · "not present in my inputs or on disk" is what a lane can attest; "never ruled" is a claim about the record · status lines re-read from origin at filing or ship with their observation vintage · attribution reads from record, not from another lane's self-effacing phrasing · **DC channel is conditional, proven both ways today:** app-up → direct write + cross-process gates; app-down → origin reads and principal ferry, stated as fallback, not failure.

## §7 · LEDGER AWARENESS — riding the next pass, none of it gating

FORECAST-AS-STATE enumeration ruling files **first**, with its four instances addressed (`931f35c:DEF-STRIKE-WATERMARK-HOLIDAY.md:50` · `triton-shadow-audit-2026-07.md:204` · trades-rebuild forecast · the widened-definition tooling entry), before any trigger keys on the count — EDGE ITEM 4 + CC-QUERY's amendment. Tooling-scoped STATUS-FROM-RECALL n=2 entry with spine's conditional-truths lesson. This lane's own entries stand as filed (E-11 attribution-from-recall; two status-from-recall instances, mitigation standing).

---

**Chain:** R-IV.152 commission → re-scope `986327cc` (R-IV.213) → base draft `5f23564b` → §8 `b1c9791b` → joint manifest `bb2ae40c` / blob `1fd693ff` (R-IV.229, T0) → R-IV.230 consolidation → **this handoff.**

**OLYMPUS-TRITON closes. The instruments are registered, the seal is fenced, the questions have owners. Whatever the seven weeks say, the answer will be believable — which was the entire point.**
