# CC BRIEF — STRIKE-Q2: The Suppression Map

**Date:** 2026-08-17 · **Issued by:** STRIKE (via Nick) · **Executor:** Claude Code, repo root `C:\trading-hub`
**Scope fence:** read-only DB queries + read-only code investigation + docs commits. **No application code changes.** New defects get ticket notes in the report, not fixes.

**Why this session exists:** STRIKE-Q1 convicted a strategy-selective burial —
Holy_Grail 610 fired / 0 surfaced (scores to 90.30), Artemis 482 / 6, CTA Scanner
~95% of all review rows — and surfaced an L0 gate logging an "unconditional
suppress set" keyed by `signal_type`. This session maps that mechanism in data
(SQL) and in code (CR tasks) so STRIKE can rule: **un-suppress existing
strategies vs. build new ones.**

---

## PHASE 0 — Preconditions

1. `git fetch origin` then `git status`. **Main moved multiple times today
   (three lanes active), and the reconciliation lane may have pushed commit
   `6aa37cb`.** If behind: `git pull origin main` before anything else. If the
   working tree shows unexpected modified tracked files: STOP and report.
2. Verify both Q2 files exist at their repo-relative paths (Nick extracted the
   zip; a Desktop Commander write timeout earlier may have left a partial file
   at the SQL path — the extracted zip version replaces it; confirm the SQL
   file ends with the "END STRIKE-Q2 SQL" footer):
   - `docs/strike/queries/STRIKE-Q2-suppression-map.sql`
   - `docs/codex-briefs/2026-08-17-strike-q2-suppression-map-brief.md` (this file)
3. Commit the two spec files now (explicit pathspecs, message via
   `C:\temp\commitmsg.txt`): `docs(strike): file STRIKE-Q2 suppression-map package`
   **Do not push yet** — one push at session end.

## PHASE 1 — SQL execution (read-only)

- DB connection: same established path as STRIKE-Q1 (repo `.mcp.json` URL).
  Credentials never echoed anywhere.
- Reuse the Q1 fidelity method exactly: session TZ pinned UTC, passthrough
  typecasters on date/time/numeric/array OIDs, raw server text only, UTF-8
  verified on the committed blob.
- Execute `STRIKE-Q2-suppression-map.sql` per its embedded protocol:
  Q2.0a is the schema authority; **per-query gates** (a gated query stops,
  the session continues); no rewrites, no substitutions; errors unedited.
- Capture every result set in full. All statements are column-scoped or
  LIMIT-5 samples; nothing here should approach Q1's 1 MB problem.

## PHASE 2 — Code reads (read-only investigation, CR-1..CR-7)

For each: report file path(s), relevant line numbers, and verbatim snippets of
the governing config/constants (never secrets). Observations only.

- **CR-1 — The L0 gate.** Locate the code producing the `l0_shadow` block
  (search: "unconditional suppress", "l0_shadow", "would_suppress",
  "SUPPRESS"). Deliver: the suppress set's members verbatim; what sets
  `mode` (env var? config? constant?); and the exact pipeline point where it
  applies — before or after the APIS/KODIAK ≥85 relabel, and whether it
  affects `status`, `feed_tier`, feed surfacing, or all three.
- **CR-2 — The L1 gate.** Locate `l1_shadow` / "non_liquid_universe" /
  "out_of_scope". Deliver the liquid-universe definition (explicit list or
  criteria) and where it applies.
- **CR-3 — Feed surfacing query.** Find the code behind the Insights feed /
  `hub_get_trade_ideas`. Deliver the verbatim WHERE/filter logic: what
  combination of status / feed_tier / score / suppression actually surfaces
  a signal to the operator.
- **CR-4 — COMMITTEE_REVIEW promotion.** Find what sets
  `status='COMMITTEE_REVIEW'`. Deliver: is there an explicit strategy
  allowlist, or is the CTA monopoly emergent from CR-1's suppress set?
- **CR-5 — Hydra's real source.** Find the `hub_get_hydra_scores`
  implementation. Deliver: what it reads (table? Redis? API?), since no
  `%hydra%` table exists — this closes or reshapes DEF-HYDRA-NULL-SCAN.
- **CR-6 — b2_options_resolver.** Read `jobs/b2_options_resolver`. Deliver:
  its output table (expected: `signal_options_expressions`), its schedule,
  and whether it currently runs.
- **CR-7 — The relabel site.** Locate the APIS_CALL/KODIAK_CALL ≥85 relabel
  logic. Deliver: threshold, and ordering relative to CR-1's gate (this
  determines whether high scores escape suppression by relabel).

## PHASE 3 — File results + single push

1. Write `docs/strike/queries/results/<RUN-DATE>-STRIKE-Q2-RESULTS.md`:
   raw SQL outputs per query (fenced, labeled, row counts), gate outcomes,
   then a **Code Findings** section for CR-1..CR-7 (paths, lines, verbatim
   snippets), then an anomalies list (observations only).
2. Commit results (explicit pathspec), message:
   `docs(strike): STRIKE-Q2 suppression-map results <RUN-DATE>`
3. **One push** for the session's two commits. Four-way deploy verification
   (Railway SUCCESS · deploy SHA == HEAD · /health 200 · mcp_ping ok).
   Docs-only push → expect a byte-identical redeploy; note queue time and any
   502 blip for the ATLAS watch-paths ticket.

## REPORT BACK (paste to Nick for relay to STRIKE)

Phase 0 state · spec commit SHA · which queries ran clean / gated · results
file path + commit SHA · four-way verification · CR-1..CR-7 one-line summaries
· anomalies count. STRIKE interprets; do not interpret in the report.
