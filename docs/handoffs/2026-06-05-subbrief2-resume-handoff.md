# Handoff — Pandora's Box Edge-Consolidation Build (Sub-brief 2 Resume)

**Created:** 2026-06-05 (post-close) · **Source session:** signal-audit -> master brief -> sub-brief 1 build
**Master brief:** `docs/codex-briefs/2026-06-05-master-brief-edge-consolidation.md` (on `main`)

> Paste the body below into a fresh chat to resume the build cold.

## Where we are
Sub-brief 1 essentially done. Resuming **sub-brief 2: B3 + B4 + A3 + A4.**

## Deployed (2026-06-05)
- **B2 options-P&L resolver** — `signal_options_expressions` table + 15-min resolver, SHADOW mode (`B2_SHADOW_MODE=true`). Grades signals in options terms **forward only** (no historical chain -> no re-grade of the ~11k historical signals; the options-P&L validation gate accumulates going forward).
- **GEX fix** — `compute_score_uw` reads the **latest row** of UW's daily GEX series (not the sum), `$10M` provisional scale, fail-loud guard, 5-day staleness guard, price-decoupled, Polygon retired, cache 3600s. The `gex` bias factor should now read ~-0.2/-0.3 instead of a broken 0.0.

## First actions in the new chat
1. Pull `hub_get_bias_composite`; confirm `gex` is non-zero with `obs 2026-06-05` (or later) in the detail string — the "actually-working-in-prod" stamp.
2. Confirm **B1 status**: no `hub_get_regime` tool exists in the MCP yet, so the sign-based regime gate (fade vs momentum on the latest GEX row's sign) likely still needs building — only its GEX data foundation is fixed. Decide sequencing vs sub-brief 2; it's the top-priority UW integration and B3 may lean on it.

## Sub-brief 2 work (full spec: brief §5 B3/B4, §4 A3/A4, §9 sequencing)
- **B3** — live UW flow/GEX/darkpool as confluence, replacing the stale DB flow snapshot in the scorer; fold into `score_v2`.
- **B4** — PYTHIA MP feed (`hub_get_market_profile`), a TradingView webhook — **must validate HMAC** (AEGIS).
- **A3** — outcome self-scoring (forward-return + options-P&L); new `outcome_source` values (`FWD_RETURN`/`OPTIONS_PNL`), never overwrite `ACTUAL_TRADE` or pollute `signal_outcomes` BAR_WALK.
- **A4** — committee-review logging (`outcome_source='COMMITTEE_REVIEW'`); folded in with A3 (shares the outcome plumbing).

## Hard-won gotchas — don't re-learn these
- **UW `/greek-exposure` is a DAILY TIME SERIES** (251 rows ~ trading days, `date` = observation day, EOD update) — NOT per-expiry, NOT forward-looking. Use the **latest row**; never sum.
- **UW api_spec is unreliable** — it said `call_gex/put_gex`; the real fields are `call_gamma/put_gamma`. Verify field names against live data.
- **Postgres is fine (~60%, 302/500 MB)** — the brief's "94% / drop tables" was stale. The deprecated `positions`/`open_positions`/`options_positions` tables are **NOT droppable** — they have live code paths (the `unified_positions` migration is incomplete; that's the separate portfolio-reconciliation problem, its own future brief).
- **UW quote/snapshot (`/stock-state`) is flaky** — returned unavailable repeatedly on 2026-06-05. Don't couple critical reads to it.
- **Olympus Impact:** anything touching PYTHIA/THALES/PIVOT/DAEDALUS or the Insights feed needs a post-build **full committee pass on a known-good ticker** before go-live.

## Working pattern
- **Investigation-first** — each workstream opens with read-only Phase 0; report and STOP at the gate before code/schema/deploy.
- **Shadow by default; no production writes/migrations/deploys without Nick's explicit greenlight.**
- **CC (Claude Code in VSCode) builds; the chat reviews** — produce paste-to-CC review gates; relay CC's reports back.
- **Don't deploy during market hours / volatile tape** (Railway restart drops the hub ~1-3 min) — deploy after close.
- **Verify, don't assume** — the gates caught three silent GEX bugs on 2026-06-05 (fake-healthy 0.0, a field-name "fix" that would've broken a working read, a year-sum masquerading as current GEX). Confirm live state; never trust "deployed = working."
