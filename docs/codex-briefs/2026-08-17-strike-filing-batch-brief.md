# CC BRIEF — STRIKE Filing Batch + Q1 Census Run

**Date:** 2026-08-17 · **Issued by:** STRIKE (via Nick) · **Executor:** Claude Code, repo root `C:\trading-hub`
**Scope fence:** docs only + read-only DB queries. **No application code changes.** Any defect discovered en route gets a ticket note in the report, not a fix.

---

## PHASE 0 — Preconditions (verify, don't assume)

1. `git status` must show: branch main, up to date with origin/main, **no
   modified tracked files** (Nick ran `git restore` on the two bias_filters
   phantoms), only untracked files remaining.
2. Verify this batch's files exist at their repo-relative paths (Nick extracted
   the zip into `C:\trading-hub`):
   - `docs/strike/2026-08-17-strike-lane-charter.md`
   - `docs/strike/specs/STRIKE-SPEC-01-ib-break-feed-conversion.md`
   - `docs/strike/specs/STRIKE-SPEC-02-strong-close-continuation.md`
   - `docs/strike/specs/STRIKE-SPEC-03-compression-flag.md`
   - `docs/strike/specs/STRIKE-SPEC-04-pdh-pdl-engine.md`
   - `docs/strike/queries/STRIKE-Q1-melt-up-census.sql`
   - `docs/defects/DEF-QUOTE-PRIORCLOSE-VINTAGE.md`
   - `docs/defects/DEF-HYDRA-NULL-SCAN.md`
   - `docs/defects/DEF-HERMES-EARNINGS-GAP.md`
   - `docs/defects/DEF-THEME-VINTAGE-LAG.md`
   - `docs/defects/DEF-MOVERS-SCREENER-STALL.md`
   - `docs/codex-briefs/2026-08-17-strike-filing-batch-brief.md` (this file)
   If the extraction nested into a subfolder (e.g. `C:\trading-hub\strike-batch\docs\...`),
   move the `docs` tree contents into place first and report the correction.

## PHASE 1 — Backfill commit (July strays)

Tidy-up moves (report each):
```
git mv 2026-07-24-aegis-coordinated-pass-brief.md docs/2026-07-24-aegis-coordinated-pass-brief.md
git mv 2026-07-24-handoff-iii-addendum-a.md docs/2026-07-24-handoff-iii-addendum-a.md
```
Stage with explicit pathspecs ONLY (never `git add .`):
```
git add docs/2026-07-24-aegis-coordinated-pass-brief.md docs/2026-07-24-handoff-iii-addendum-a.md docs/2026-08-01-edge-lane-charter.md docs/codex-briefs/2026-07-29-runbook-cb-webhook-enforce.md backend/database/archive/2026-07-23-def-position-integrity-preimage.jsonl backend/database/archive/2026-07-23-reconciliation-preimage.jsonl backend/database/archive/2026-07-24-reseed-cleanup-preimage.jsonl backend/database/archive/def_cvd_divergence_leak_preimage_20260724T185329Z.jsonl backend/database/archive/def_cvd_quarantine_preimage_20260723T054219Z.jsonl
```
Commit message → write to `C:\temp\commitmsg.txt`:
```
docs: backfill July work product (EDGE charter, AEGIS brief, handoff addendum, CB runbook, DB preimage archives)
```
Then `git commit -F C:\temp\commitmsg.txt`. Confirm with `git status` (only the
strike-batch files should remain untracked).

## PHASE 2 — STRIKE batch commit

Stage with explicit pathspecs:
```
git add docs/strike/ docs/defects/ docs/codex-briefs/2026-08-17-strike-filing-batch-brief.md
```
(`docs/strike/` and `docs/defects/` are new directories containing only this
batch — directory pathspec is acceptable here; list the staged files in the
report via `git status --short`.)

Commit message → `C:\temp\commitmsg.txt`:
```
docs(strike): file STRIKE lane batch — charter, SPEC-01..04, Q1 census package, five defect tickets
```
`git commit -F C:\temp\commitmsg.txt`.

## PHASE 3 — Push + deploy verification (one push, watched)

1. `git push origin main` — this WILL trigger a Railway production redeploy of
   byte-identical application code (docs-only change). Expected safe; watched
   anyway per standing law.
2. Verify: Railway deploy status SUCCESS **and** deploy SHA == the new local
   HEAD SHA **and** `/health` responds OK **and** hub `mcp_ping` succeeds.
   Committed ≠ deployed ≠ validated — report all four checks explicitly.
3. Any deploy anomaly: report and STOP. Do not retry-push.

## PHASE 4 — STRIKE-Q1 census execution (read-only)

1. DB connection: use `DATABASE_URL` from the local environment; if absent,
   ask Nick to provide it in-session (public endpoint, Railway dashboard).
   Never echo the URL or credentials into any file or report.
2. Open `docs/strike/queries/STRIKE-Q1-melt-up-census.sql`. Execute under its
   embedded protocol, which is binding:
   - **Q0 first. Gate check.** If any referenced table/column is absent from
     Q0 output — including the NAME-GATED Q6/Q7/Q8 table names — STOP that
     query per the file's instructions and include Q0 output in the results
     instead. Do not rewrite queries. Errors returned unedited.
   - SELECT-only. Sequential. Capture every result set in full.
3. Rosetta step: read `backend/config/strategy_aliases.py` and append its
   label→codename mapping verbatim to the results file.
4. Write results to `docs/strike/queries/results/2026-08-17-STRIKE-Q1-RESULTS.md`:
   raw outputs per query (fenced blocks, labeled Q0–Q9, Q1a), row counts,
   the Rosetta mapping, and an "anomalies observed" list (observations only —
   no fixes, no interpretation; interpretation is STRIKE's job).
5. Commit (explicit pathspec `docs/strike/queries/results/2026-08-17-STRIKE-Q1-RESULTS.md`),
   message: `docs(strike): STRIKE-Q1 census results 2026-08-17`. Push. Verify
   deploy per Phase 3 rules.

## REPORT BACK (paste to Nick for relay to STRIKE)

- Phase 0 status · Phase 1 commit SHA · Phase 2 commit SHA · Phase 3 four-way
  verification · Phase 4: which queries ran clean, which hit the gate, results
  file path + commit SHA · anomalies list.
