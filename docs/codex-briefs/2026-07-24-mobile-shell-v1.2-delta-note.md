# Delta Note — Mobile Shell Brief v1.1 → v1.2

**Author:** SHELL, 2026-07-24 · **Requested by:** spine (Phase 0 closure ACK)
**Companions:** `2026-07-24-brief-pandora-mobile-shell.md` (v1.2, governing) · `2026-07-24-mobile-shell-phase0-ack.md` (CC-SHELL findings, detailed spec)
**Purpose:** change-of-record for the spine ledger, and a cold-start block so any incoming spine instance can seat itself from files, not chat scrollback.

## 1. What changed and why (each mapped to a Phase 0 finding)

- **Phase 0 marked COMPLETE**; stop-gate fired on P0.1/P0.2/P0.3 and resolved by this revision.
- **Route corrections:** Agora v2 lives at `/app` (not `/`, which serves a JSON health payload); Abacus is hardcoded `/app/analytics` (never `buildModePath`); new routes go ABOVE the `main.py:1864` catch-all. Driver: P0.2.
- **Sixth tracked target:** `frontend/styles.css` (deck-bar occlusion reserve lives there). Driver: P0.6 addendum.
- **T1.0 added** — layout-row insurance copy (`backup_20260724`), executable pre-build under Amendment 2. Driver: single-row store, no history, unconditional upsert (P0.1) + live touch-resize hazard (P0.3).
- **T1.1 tightened** — explicit `columnOpts` shape (`breakpointForWindow: true`, explicit `layout: 'list'`) + per-`gs-id` order map (collapse follows saved y, not DOM) + corrected tile count (**11**, `river` was missing). Driver: P0.3 confirmed mechanics.
- **T1.2 reframed** — hazards are `h` bypassing the column cache, `layoutsNodesChange()` corrupting the cached desktop layout on drag, and always-armed touch-resize; mitigations now `setStatic(true)` + `saveLayout()` guard + the load-order invariant pinned with an acceptance check. Driver: P0.3 (CC-SHELL's own draft correction — the original "collapse writes collapsed x/y/w" framing was wrong; GridStack's cache-merge is real anti-clobber, with three residual leaks).
- **T1.3 rescoped** — restructuring, not typography: kill nested per-tile scrollers, wrap `.regime-band`, fix `.mem-row`/`.th-row`, topbar ≤390px + body overflow-x guard. Driver: P0.3/P0.2 measurements (~2,900px stack; 32px columns under 22px type; ~420px topbar min-content).
- **T1.4 grounded** — `position: fixed` reality: occlusion reserve in `styles.css:70` + v2 container, `viewport-fit=cover` + `env(safe-area-inset-bottom)` (no safe-area handling exists anywhere today).
- **T1.5 corrected** — manifest link + `apple-touch-icon` + `apple-mobile-web-app-*` on both pages; `start_url` → `/app`; Done Definition explicitly **iOS-only** for standalone install (no SW until Phase 2, Android install requires it).
- **T1.7 added** — pre-existing `grid.load()` `addRemove:true` defect (new tiles silently deleted for saved-layout holders) fixed with load-without-removal + reconcile.
- **Done Definition expanded** to cover T1.0/T1.7, occlusion, safe-area, zero horizontal scroll.
- **Deploy gate** — six-target build-time re-diff replaces the branch-overlap clause (s6 ratified to main made the old clause moot); **clobber hotfix carve-out** if Phase 1 misses 08-01 — PRE-APPROVED by spine ruling 2026-07-24.
- **Phase 2 T2.1 simplified** — layout slots become additional `layout_key` rows (no DDL); schema changes, if ever, go through `migrations/` + `init_database()` mirror, never `_ensure_table()`. AEGIS riders recorded: auth-gate GET, CSRF on POST, stored-XSS check on layout payload (spine addition).
- **Phase 2 T2.4 verdicts baked in** — bucket/B3 chips OMITTED (no runtime source; recorded work package: real `bucket` column + CHECK, wired on create/update); greeks fix-or-render-staleness as a shipping precondition; CB semantic constraint (label "Market CB (SPY/VIX)", never grouped with discipline chips, fourth UNKNOWN state before reusing kill-switch logic); closed-today `since`/`limit` gate decision.

## 2. Self-certification rationale (accepted by spine, recorded here)

Every v1.2 change is scope-reducing, defect-absorbing, or a factual correction from Phase 0. No new surfaces, no new data flows, no visual redesign — the approved mockup remains sole design authority. Titans record §6 updated in-file (ATLAS: DDL eliminated; HELIOS: restructure serves approved legibility intent; AEGIS: riders logged; ATHENA: no full re-pass at 8 days to gate). Full re-review reserved for any future delta that adds scope.

## 3. Cold-start state block (for the incoming spine — read this first)

- **Lane registry:** Fable = spine, exclusive (rotated 2026-07-24 evening; this block is your seating doc). SHELL = mobile-shell lane (claude.ai). CC-SHELL = its build session. BUILDER-1 = S-6 build. BUILDER-2 = filing/checkout custodian.
- **Filed:** brief v1.1 at `669013d`; brief v1.2 at `238e831` (current main HEAD). This note + the spine's XSS rider are the pending BUILDER-2 filing.
- **Executed:** T1.0 backup row `backup_20260724` (md5 `e437db9bbe6c`, 11 tiles) — insurance against the live clobber hazard.
- **PHASE 1 IS BUILT, NOT DEPLOYED.** Branch `mobile-shell-phase1` off `238e831`, three commits, unpushed. SHELL's Done-evidence review: **PASS** — 6 of 8 boxes closed with evidence (incl. a positive-controlled clobber test); the 2 open boxes (iOS install, production verification) are physically post-deploy. Two spec deviations reviewed and approved as improvements. CC-SHELL built through a hold amendment that never reached it (relay loss, not defiance) — no harm: nothing pushed, nothing deployed.
- **THE ONE DECISION PENDING FROM SPINE:** release the Phase 1 build order for push + deploy. Prior spine's closure line gated it on "the new spine's review." Gate: EOD 2026-08-01 MDT.
- **Standing hazard until deploy:** a phone drag on live `/app` overwrites Nick's single desktop layout row — empirically confirmed, not derived. Nick is advised to avoid `/app` on phone until Phase 1 ships. Hotfix carve-out was pre-approved by the prior spine but is likely moot, since the fix is already built.
- **Dates:** Phase 1 deploy gate EOD 08-01 · SG-3 screenshot comparison 08-03 (spine-held, HELIOS veto) · freeze 08-04→08-15 · Phase 2 opens 08-15+.
- **Spine-owned open items inherited:** Saturday diff ruling (s6-brief +24 = uncommitted discipline amendment, default discard; watchlist ~230) · Monday P1 queue (DEF-KILLSWITCH-FAILOPEN + A-4 arm-path first; DEF-GREEKS-ZERO, interim caveat "zeros = unknown") · Phase 1 build-order release.
