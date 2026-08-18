# CC BRIEF — Phase A: Staged Un-Suppression (HOLY_GRAIL_1H)

**Date:** 2026-08-18 · **Issued by:** STRIKE (via Nick) · **Executor:** Claude Code, repo root `C:\trading-hub`
**Authority:** Olympus double-pass 2026-08-18 — APPROVED WITH FOUR BINDING CONDITIONS (Nick sign-off 2026-08-18). Approval record: `docs/strike/2026-08-18-phase-a-approval-record.md`.
**Scope fence:** ONE code line changes in this session (the A1 set edit). Everything else is docs, read-only queries, and read-only code investigation. A2 and A4 are INVESTIGATE-AND-REPORT only. New defects get tickets, not fixes.
**Timing:** Execute before Tuesday's open (pre-07:30 MT) for a clean observation day one, or immediately if run tonight. The deploy lands off-hours either way.

---

## PHASE 0 — Preconditions

1. `git fetch origin` → `git status`. Main moved 3+ times on 08-17 and the recon
   lane may push `6aa37cb` at any time. If behind: `git pull origin main`.
2. **EOL-noise cleanup (pre-authorized):** if the 12 CR-at-EOL-only files from
   the Q2 session still show modified, verify zero content drift again
   (`git diff --ignore-cr-at-eol --stat` must be empty), then restore them with
   an explicit pathspec list taken from `git status --short`. If ANY file shows
   real content drift: STOP and report.
3. Verify kit files present (Nick extracted the zip):
   - this brief · `docs/strike/2026-08-18-phase-a-approval-record.md`
   - `docs/strike/queries/STRIKE-OBS-01-hg1h-daily.sql`
   - `docs/defects/DEF-COMMITTEE-BRIDGE-DEAD.md` · `DEF-B2-RESOLVER-ZERO-ROWS.md`
     · `DEF-UNIFIED-QTY-INTEGER.md` · `DEF-NIGHTLY-FLATLINE.md`
4. Commit the kit docs now (explicit pathspecs; message via `C:\temp\commitmsg.txt`):
   `docs(strike): Phase-A kit — approval record, observation query, batch-2 defect tickets`
   Do not push yet.

## PHASE 1 — CONDITION GATES (all three must pass before any edit)

**GATE 1 — Archaeology (Committee Condition 1).**
`git log --follow -p` on the file identified in STRIKE-Q2 CR-1 (`l0_routing.py`),
focused on every commit that introduced or modified `SUPPRESS_ALWAYS`. Report:
SHAs, dates, messages, and any in-code comments or adjacent docs explaining WHY
each member was added.
- **HALT RULE:** if the history shows HOLY_GRAIL_1H was suppressed in response
  to a documented malfunction of HOLY_GRAIL_1H itself (bad signals, pipeline
  breakage attributed to it), STOP the session, report, committee reconvenes.
- Feed-noise curation, bulk additions, or no stated reason → gate PASSES
  (report the story either way).
- **AMBIGUITY RULE:** if the history is ambiguous, PAUSE and report to Nick
  before proceeding. Do not self-adjudicate.

**GATE 2 — Split count (Committee Condition 2).**
From the committed Q2 results (`docs/strike/queries/results/2026-08-17-STRIKE-Q2-RESULTS.md`,
Q2.1 crosstab) — or a single targeted COUNT if faster — report row counts for
`signal_type='HOLY_GRAIL_1H'` vs `'HOLY_GRAIL_15M'` in the 2026-07-30 →
2026-08-16 window.
- **HALT RULE:** HOLY_GRAIL_1H < 12 rows in that window (≈5/week) → STOP,
  report, committee reconvenes on whether to substitute a different type.

**GATE 3 — Mechanics read (day-zero behavior).**
From the CR-1/CR-3 code: determine whether removing HOLY_GRAIL_1H from
`SUPPRESS_ALWAYS` affects (a) only signals created after the deploy, or
(b) also retroactively surfaces existing rows still inside their ACTIVE/<24h
feed window (because the check is evaluated read-side and/or the persisted
`would_suppress` tag is or is not re-consulted). Report the expected day-zero
surfacing count (query the currently-eligible rows if mechanism (b)).
No halt — this gate is informational but MANDATORY in the report.

## PHASE 2 — THE FLIP (A1)

1. Edit: remove `HOLY_GRAIL_1H` from `SUPPRESS_ALWAYS` in the CR-1 file.
   Leave HOLY_GRAIL_15M, PULLBACK_ENTRY, TRAPPED_LONGS, ARTEMIS_LONG in place.
   Add an adjacent comment:
   `# 2026-08-18 STRIKE Phase-A A1: HOLY_GRAIL_1H un-suppressed for 7-day watch-only observation — see docs/strike/2026-08-18-phase-a-approval-record.md`
2. Commit (explicit pathspec, own commit — do not mix with docs):
   `feat(l0): un-suppress HOLY_GRAIL_1H — Phase-A A1, 7-day watch-only observation (Olympus 2026-08-18)`
3. **One push** carrying the docs commit + the code commit.
4. Four-way verification: Railway SUCCESS · deploy SHA == HEAD · `/health` 200
   · `mcp_ping` ok. **Plus a fifth for a code change:** one
   `hub_get_trade_ideas` call returns without error.
5. Day-zero check: run `STRIKE-OBS-01-hg1h-daily.sql` once; report whether any
   HG_1H rows are already feed-eligible, consistent with Gate 3's prediction.

**ROLLBACK LINE (Committee Condition 4 — keep taped to the wall):**
`git revert <flip-SHA> && git push origin main` → four-way verify. Execute
immediately if any kill criterion fires during the week:
- more than 10 HG_1H signals SURFACED to the feed in one session, or
- any pipeline error attributable to the flip, or
- kill-switch activation.
(High CREATION volume alone — e.g., >25 created/day — is report-and-continue,
not a kill; creation is not user-facing.)

## PHASE 3 — A2 INVESTIGATION (read-only, report for ATLAS)

1. Identify which scanner modules actually bound their ticker universes — do
   they iterate `liquid_universe.py`'s 20-name allowlist, their own lists, or
   something else? (CR-2 found L1 shadow-only, so the enforcement path is
   non-obvious — name the real one.)
2. Estimate UW API calls/day added per additional ticker for the CTA and
   Holy_Grail scan paths (Governor is OBSERVE — this is the quota math ATLAS
   needs to rule on the semis/AI expansion).
3. NO universe changes this session.

## PHASE 4 — A4 DIAGNOSIS (read-only)

Trace why `signal_options_expressions` has 0 rows despite both entry points
being live (CR-6: fire-and-forget at pipeline.py:1540 + 15-min market-hours
task at main.py:1046, B2_SHADOW_MODE default true). Fire-and-forget swallows
exceptions — find where they go. Deliver root cause + proposed minimal fix.
NO fix applied this session.

## PHASE 5 — Hydra ticket addendum

Append to `docs/defects/DEF-HYDRA-NULL-SCAN.md` (do not rewrite it): a dated
section noting the CR-5 reshape — reads Postgres `squeeze_scores`
(squeezes.py:39), no `%hydra%` table exists, and the code states no rescan
cron exists; fix = build/restore the scan cron + emit `last_scan_at`
unconditionally. Include in the docs commit if executed before Phase 2's
commit; otherwise commit separately with the results.

## REPORT BACK — top the report with `RELAY → STRIKE`

Gate 1 story + verdict · Gate 2 counts · Gate 3 mechanism + day-zero
prediction vs observed · flip SHA · five-way verification · A2 findings ·
A4 root cause · anomalies (observations only).
