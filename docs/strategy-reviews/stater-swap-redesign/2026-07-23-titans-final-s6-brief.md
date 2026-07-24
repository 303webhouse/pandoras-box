# Titans Final Review Record — S-6 Build Brief (Stater Swap v2 · C2 Cockpit Grid)

**Date:** 2026-07-23 | **Lane:** Coordination (Fable) | **Repo state reviewed:** `main` @ `49f702e`
**Brief reviewed:** `docs/codex-briefs/2026-07-23-s6-stater-swap-v2-build-brief.md` (S6-BUILD-01)
**Review stage:** Brief Final Review (Titans gate before CC launch). Pass 1 / Pass 2 for the v2 program were completed 2026-07-13 (`2026-07-13-titans-review-stater-swap-v2.md`); mockup gate pass 1 completed and C2 signed off 2026-07-23 (`helios-mockup-track.md`).
**Skills honored:** atlas / helios / aegis / athena SKILL.md, Brief Final Review formats.

## Verdicts

| Titan | Approve for CC | Conviction | Conditions |
|---|---|---|---|
| ATLAS | YES | HIGH | C-A1, C-A2, C-A3 |
| HELIOS | YES | HIGH | C-H1, C-H2 |
| AEGIS | YES | HIGH | C-S1 |
| ATHENA | YES — **APPROVED WITH CONDITIONS** | HIGH | C-T1, C-T2 + sequencing rulings |

No vetoes. No validation flags — validate-before-design satisfied by the 07-13 program review plus the completed HELIOS mockup gate (sign-off recorded). All six conditions were folded into the brief text on 2026-07-23 before status flipped to APPROVED.

## Conditions applied to the brief

- **C-A1 (ATLAS, MEDIUM):** P0.3 branch rule — if no discipline-state endpoint exists, STOP at SG-0 for a Fable scope ruling. Hidden backend dependency; no build-arounds.
- **C-A2 (ATLAS, LOW):** if no live crypto signal-feed source exists, the feed renders honest-empty-with-reason and the build proceeds.
- **C-A3 (ATLAS, MEDIUM):** distance-to-floor red-state thresholds are config-driven and hot-reloadable, per the 2026-07-13 settled rule that all gate/threshold parameters in this program are no-redeploy-to-tune.
- **C-H1 (HELIOS, HIGH):** carry-forward enforcement — distance-to-floor sits in the global header, always visible, red-state thresholds, in addition to the per-card rings; unavailable-with-reason until `breakout_prop` ships. Source: 07-13 carry-forward table, second S-6 row.
- **C-H2 (HELIOS, LOW):** matched-viewport screenshot protocol on all gates — desktop at the frozen render's framing, mobile at 390×844 against the §6 spec.
- **C-S1 (AEGIS, MEDIUM):** client consumes backend `/api/crypto/*` routes only, never the Hub MCP endpoint; `MCP_BEARER_TOKEN` / `UW_API_KEY` and all credentials stay server-side; nothing credential-bearing in client code, console, or logs.
- **C-T1 (ATHENA, LOW):** Olympus Impact section added — "None"; S-6 ships no MCP tools, so the standing connector re-toggle + BTC/SPY re-test obligation is not triggered.
- **C-T2 (ATHENA):** Task 0.1 (Nick exports the frozen C2 render PNG) carries a 2026-07-24 micro-deadline — the only Nick-side item on the critical path to the 07-31 deploy.

## Carry-forward compliance check (07-13 table, S-6 rows)

- **MOCKUP GATE row:** satisfied — three concepts rendered, sign-off recorded 2026-07-23, post-deploy screenshot comparison bound as SG-3 (2026-08-03) with HELIOS standing veto.
- **Distance-to-floor / discipline-chips row:** satisfied post-C-H1 — header placement always visible with red-state thresholds; discipline chips render enforced backend state only; visibility-based polling client-side only (UI may pause on hidden tab; backend collection never pauses).

## Sequencing rulings (ATHENA)

1. **Launch order:** CC clears the pending Olympus crypto-wiring Tasks 2/3 paste block before the S-6 build session starts — removes queue-collision risk on CC's plate.
2. **Critical path:** Task 0 (frozen render on `origin/main`) gates everything; Nick-side deadline 2026-07-24.
3. **Displacement, named:** S-6 occupies CC through ~07-31, deferring DEF-ENRICH-CLOBBER reconciliation, untracked-file triage (~60 files), and remaining Perf Architecture items to the post-vacation window. Accepted — vacation-safety and the HELIOS Pass 2 deploy-or-hold rule outrank.
4. **Timeline law restated:** deploy by 2026-07-31, comparison 2026-08-03, or S-6 holds past the 08-04→08-15 freeze entirely.

## Files this review produced

- Brief status flipped DRAFT → APPROVED with all conditions folded: `docs/codex-briefs/2026-07-23-s6-stater-swap-v2-build-brief.md`
- This record: `docs/strategy-reviews/stater-swap-redesign/2026-07-23-titans-final-s6-brief.md`
- Companion handoff filing: `docs/strategy-reviews/stater-swap-redesign/2026-07-23-s6-lane-handoff.md`

## Addendum — Fable render verification (2026-07-23, post-approval, non-scope)

The approved C2 frame (Figma node `8:3`) was inspected read-only via the Figma MCP the same day as sign-off, and the frozen export was pulled directly to the repo path via Desktop Commander (`curl` HTTP 200, 109,704 bytes — exact match to Figma's declared export size): `renders/c2-cockpit-grid-signoff-2026-07-23.png`. T0.1 satisfied at at-sign-off state; T0.2 (commit) remains with CC.

Structural verification against the brief, from frame metadata + screenshot:

- **C-H1 confirmed in the render itself:** header chips row carries `DIST-TO-FLOOR · N/A — breakout_prop not reported` alongside regime / session / concurrent / daily chips. The condition matches the signed-off artifact exactly.
- **P0.5 pre-answered:** the signal feed is a global section on the main page, below the Cycle Extremes seam; the drawer (labeled "EXISTING /app/v2 PATTERN") carries per-symbol detail blocks (funding, OI, basis, liquidations 24h, long share, divergence, CTA zone, POC). CC confirms at Phase 0 per verify-don't-trust, but arrives with the answer.
- **Cards carry the six-dot per-block health cluster (`FU OI BA LQ RG TP`)** — C1's signature element hybridized into the approved C2, per the concept plan's "hybrid legitimate" note. S5.2 builds it.
- **FARTCOIN stress case rendered as required:** `PREC-BLOCKED`, `BASIS — · LIQS —`, `PARTIAL DATA` badge, degraded dots — per-block, not symbol-wide.
- **S-5 seam honest:** Cycle Extremes section labeled `S-5 · DIAL PENDING BUILD` over the single-axis CAPITULATION ⟷ FROTH marker.
- **P0.4 narrowed, not closed:** the collapsed `MACRO ▸` line in the render carries BTC-master derivatives (funding/OI/basis/liqs), not the charter's DXY / real yields / calendar — expanded-state contents remain the open reconciliation item, along with where the charter's full setup-card fields (entry / invalidation / size incl. funding cost + liq-distance-in-ATRs) surface, since the rendered feed rows are compact latest-events rows.
- Dual labeling present: ET clock top-right, MT timestamps on feed rows.

## Amendment A6 — discipline read-projection endpoint (2026-07-23, Nick ruling)

C-A1's STOP branch resolved same-day by Nick ruling (Option A) after a Fable pre-scout confirmed the endpoint absent — backend search for `discipline` / `cooldown` / `circuit_breaker` / `daily_loss` returned zero endpoint-shaped hits. Rationale for building over deferring: the surface's stated mission is "is there a trade, and does discipline permit it?" — honest-N/A discipline chips would blind half the question during the exact phone-only window (08-04 → 08-15) the build exists for.

T-D1 added to the brief (§5a): `GET /api/crypto/discipline`, SELECT-only over `unified_positions`, config-driven B3 caps (300 / 2 / 3, `America/Denver` day boundary, hot-reloadable), fail-closed staleness, no schema migration, no enforcement writes — the endpoint observes state, it enforces nothing.

Targeted lane sign-off (full four-Titan re-pass not triggered — one additive read-only route):
- **ATLAS:** conditions written into §5a verbatim (canonical-source-only, read-only, fail-closed, config-driven). Nothing destructive — no phase-gating required. APPROVE.
- **HELIOS:** chip visuals unchanged from the frozen render; real data source replaces mockup values. No new surface. APPROVE.
- **AEGIS:** route inherits the existing v2 auth pattern; no new credentials; nothing credential-bearing in response or logs. APPROVE.
- **ATHENA:** ~0.5 CC-day added inside the existing window; §9 out-of-scope line amended to carve out T-D1 (a direct contradiction with "any new API endpoints," caught and fixed at amendment time); timeline law unchanged. Scope amendment RECORDED.

Definition-of-done extended: discipline chips live-fed by T-D1 with a forced-degraded state demonstrated.

## SG-0 resolution — Amendment A6 RESCINDED (2026-07-24)

Phase 0 (`s6-phase0-findings.md`, `c36ebff`) invalidated A6's premise. T-D1 assumed daily realized P&L was derivable read-only from `unified_positions`; live probes show the prop-account telemetry simply does not exist — `/api/analytics/risk-budget` carries a hard-coded `$1000` daily-remaining that never subtracts realized P&L, `breakout_balance=25000` is static, `breakout_prop` is untracked, and no cooldown state exists anywhere. A read-projection over missing source data would have been fake-healthy moved server-side.

Nick ruled the honest-seam descope in the CC session with the Phase 0 evidence in front of him (CC's resolution menu "Option A" — note: opposite labeling from this lane's earlier A/B; recorded here to close the cross-lane fork). Ruling stands as final: CONCURRENT renders real advisory count, DAILY and COOLDOWN render N/A-with-reason, nothing fake ships. **SG-0 retro-acked by Fable.** The enforced-discipline endpoint moves to a post-vacation backend package: prop-account P&L ingestion + `breakout_prop` tracking + discipline state + shadow-tag read route as one coherent "prop telemetry" lane. The A6 section above stands as historical record; its brief edits were never committed and are discarded — `origin/main`'s brief is canonical.

## SG-1 — LAYOUT GATE: **CLEAR** (HELIOS via Fable, 2026-07-24)

Scaffold `1b47e82` on branch `s6-stater-build`, verified: structural skeleton faithful to the frozen render (five-chip row, tier-ordered 2×3 grid, section order MACRO → TAPE → CYCLE → FEED → footnote verbatim, v2 drawer pattern, honest placeholders); route declared before the `/app/{mode}` catch-all per P0.1; AEGIS held (client → backend `/api` only); §6 mobile collapse authored at ≤768px (P0.2 confirmed no pre-existing breakpoint); headless captures committed at 1480px and 390px. The live red `LQ` dots absent from the 07-22 mock are the honest seam functioning — live per-block degradation, not layout drift. Accepted. Build proceeds to drawer / dial / feed / macro band.

## Rulings ledger (Fable, 2026-07-24)

1. **P0.4-1 macro band — build to the render:** collapsed strip carries funding / OI / basis / liqs / long-share. The charter's DXY / real-yields / calendar Horse-Rule context is **deferred coverage, not dropped** — post-vacation item (candidate: expanded band state or Agora cross-link).
2. **P0.4-2 cycle dial — render live:** single-axis marker from live `composite_score` (matches the frozen frame's marker geometry), honest note "S-10 input deferred (S-5)". Rendering "DIAL PENDING BUILD" over live data would be the inverse lie. **SG-3 instruction:** the seam-label text change is an approved deviation — the 08-03 comparison must not flag it.
3. **`cta_zone` relabel approved:** drawer cycle position reads `composite_score` / context copy — mislabel fix, not a design change.
4. **Per-card data source ratified as built:** card dots from cycle-extremes cells (one batched call); `/state/{symbol}` fetched lazily on drawer-open only.
5. **S5.7 gaps:** shadow/live tag → unavailable-with-reason seam (read route joins the prop-telemetry lane); funding-cost-over-hold → seam, not fabricated; liquidation-distance-in-ATRs → not built, documented un-sourceable; tier badge → join from `/regime`, build it.
6. **DEF-CRYPTO-MARKET-FAKE-SPOT registered (P0 fake-healthy class):** `/api/crypto/market` fabricates `binance_spot: 506.59` for Binance-unlisted FARTCOIN. Diagnostic hint: the value sits in ZEC's price neighborhood — likely symbol-mapping/fallback contamination, not random garbage. Client-side cohort-outlier guard is containment; backend fix is a separate micro-brief (pre-freeze if trivial, else post-vacation). Out of S-6 scope.
7. **Freeze rule sharpened:** any push to `origin/main` triggers a Railway redeploy — docs included. The 08-04 → 08-15 rule is therefore **no pushes to `origin/main` at all**; branch pushes remain fine.
