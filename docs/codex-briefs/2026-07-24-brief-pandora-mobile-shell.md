# Brief — Pandora Mobile Shell (4 Decks + Agora Mobile Layout)

**Target:** Claude Code (VSCode)
**Author:** Fable / HELIOS (design lead), 2026-07-24
**Status:** MOCKUP GATE satisfied — Nick approved `docs/mockups/pandora-mobile-shell-mockup.html` on 2026-07-24
**Depends on:** Nothing (Phase 1). Phase 2 is calendar-gated: **no work before 2026-08-15.**
**Deploy freeze:** ABSOLUTE — no deploys 2026-08-04 through 2026-08-15.
**v1.1 (2026-07-24):** Deconflicted with the S-6M mobile design lane charter — all `stater.html`/`stater.css` writes removed from this brief; T2.5 Stater pass superseded; P0.6 branch-overlap check added; deploy gate tightened.
**v1.2 (2026-07-24, post-Phase-0):** Phase 0 COMPLETE, stop-gate fired and resolved. Absorbs CC-SHELL's ACK (filed alongside this brief as `docs/codex-briefs/2026-07-24-mobile-shell-phase0-ack.md` — the ACK is the detailed spec; this brief governs). Phase 1 rescoped T1.0–T1.7; route map corrected (`/app`, not `/`); `styles.css` added as sixth tracked target; Phase 2 T2.1 simplified to layout_key rows; truthful-source verdicts baked in.

---

## 1. Context & validation (verified against repo, not memory)

- `frontend/v2.js` `initGrid()` hardcodes `GridStack.init({ column: 12, ... })` with no responsive column config. On a ~390 px phone the full 12-column desktop grid renders at ~1/3 scale. This is the user-reported symptom (tiles jammed, illegible).
- `frontend/v2.css` contains exactly one media query (`prefers-reduced-motion`). Zero mobile breakpoints exist.
- Layout persistence is already server-side: `saveLayout()` → `grid.save(false)` → `POST /api/layout` (401 → "sign in to save layout"); restore via `grid.load(d.layout)`. **There is a single layout slot.** Any save from a collapsed mobile grid would overwrite the desktop arrangement. This is the central hazard of the whole build.
- `frontend/manifest.json` exists (standalone, portrait, icons 192/512, theme `#14b8a6`, `start_url: "/"`) but **v2.html does not link it** (no `<link rel="manifest">`, no apple-touch-icon; theme-color mismatch `#050810`).
- Abacus lives as a mode inside legacy `index.html` (Cockpit + Laboratory via `cockpit.js` / `laboratory.js`, lazy-loaded). **Abacus v2 is formally parked** with a named re-entry trigger and an ATHENA veto on its UI build this window. This brief must not smuggle it in.
- Stater v2 lives at `stater.html` (S-6 scaffold; chips row + symbol grid live).

Validated gap: user-reported, repo-confirmed. Not speculative polish.

## 2. Design authority & rulings

**Design authority:** `docs/mockups/pandora-mobile-shell-mockup.html` (5 frames: Agora, Stater, Abacus, Book, Edit Mode). Post-deploy screenshot comparison against these frames is required at each phase close (MOCKUP GATE).

Standing rulings (do not relitigate in-build):
1. **Decks = existing pages wearing one shared bottom bar.** No SPA rewrite. The bar is the "one app" feel inside the PWA.
2. **Mobile resize = S/M/L height presets per module.** No drag-corner resizing on touch. Reordering = list-style drag handles in edit mode only.
3. **Phase 1 ships THREE tabs** (AGORA · STATER · ABACUS). BOOK joins in Phase 2 when the deck exists. No dead buttons.
4. **Service worker deferred** (Phase 2 optional). Phase 1 PWA scope = manifest linking + icon tags + start_url verification only.
5. **Abacus deck = existing surface + responsive pass only.** The thin-read mobile treatment in the mockup ships as part of Abacus v2 when it re-enters per its own trigger.
6. **Staleness ages remain visible on every tile header** in every deck and every size preset (HELIOS hard rule).
7. **Mobile never writes to the desktop layout slot.** Ever.
8. **Stater mobile layout belongs to the S-6M design lane** (charter registered 2026-07-24). This brief writes nothing to `stater.html`/`stater.css` in any phase. It publishes two integration surfaces for S-6M to consume: the deck-bar component spec (T1.4) and the `deck='stater'` layout-slot contract (T2.1). The `s6-stater-build` branch is frozen through its 2026-08-03 screenshot comparison — nothing in this brief may touch that branch or its file surfaces.

## 3. PHASE 0 — Investigation (read-only; report before any code)

CC must verify and report (ACK message) before writing code:
- P0.1 Read the backend `/api/layout` handler + storage shape (table/columns/row keying). Fable read frontend only; the handler is unverified.
- P0.2 Confirm the route map: what `/` serves (believed: Agora v2 since `e9a4840`), routes for `stater.html`, legacy `index.html`/Abacus mode, `/app/legacy`.
- P0.3 Confirm GridStack 11.1.2 responsive API surface (`columnOpts` breakpoints / `column(1)` behavior and its one-column ordering rules) against the pinned CDN version — do not assume from newer docs.
- P0.4 Identify the Book tile's data endpoints (`bookStrip` / `bookPositions` sources) for Phase 2 reuse.
- P0.5 Confirm whether any truthful source exists for bucket usage (B2 open count, B3 count today, circuit-breaker state). If none: Phase 2 omits those chips. **Do not hardcode or derive optimistically — fake-healthy is P0.**
- P0.6 Diff the touched-file list of `s6-stater-build` against Phase 1's targets (`v2.html`, `v2.css`, `v2.js`, `index.html`, `manifest.json`). Report any overlap. **Any overlap → Phase 1 defers to 2026-08-15+ (see deploy gate).**

**STATUS: PHASE 0 COMPLETE (2026-07-24, CC-SHELL ACK filed).** Stop-gate fired on P0.1/P0.2/P0.3; findings reviewed and absorbed into v1.2. Key corrections of record: `/` serves a JSON health payload — Agora v2 lives at `/app` (alias `/app/v2`); Abacus is `/app/analytics` (hardcoded href only — never derive via `buildModePath`, which emits 404-prone two-segment paths); any new route must be declared ABOVE the `/app/{mode}` catch-all at `main.py:1864`; layout store is `v2_dashboard_layout(layout_key TEXT PK, layout JSONB, updated_at)` — single row `'default'`, unconditional upsert, `_ensure_table()` is `CREATE TABLE IF NOT EXISTS` and is NOT a migration path (schema changes go through `migrations/` + the `init_database()` mirror); GridStack 11.1.2's touch-resize handles are armed by default on phones today (live clobber hazard, pre-existing); `grid.load()`'s default `addRemove:true` deletes new tiles for saved-layout holders (pre-existing defect, fixed in T1.7).

## 4. PHASE 1 — "Legible on vacation" (rescoped v1.2)

**T1.0 — Layout-row insurance (FIRST; may pre-run under Amendment 2).**
Duplicate the live row: `INSERT` a copy of `layout_key='default'` as `layout_key='backup_20260724'`. Additive, reversible, makes the standing "unrecoverable clobber" recoverable. Report row count + both `updated_at` values.

**T1.1 — One-column mobile collapse (v2.js).**
Per the ACK's confirmed mechanics: `columnOpts` with `breakpointForWindow: true` (else the JS and CSS breakpoints fire at different widths) and a `{w: 768, c: 1}` breakpoint with **explicit `layout: 'list'`** (the default is `moveScale`). `'list'` sorts by saved y — NOT DOM order — so T1.1 includes an explicit per-`gs-id` mobile order map that overrides persisted positions. Mobile default order (all **11** tiles): `regime, movers, kairos, book, river, themes, divergence, breadth, index, curve, usd`.

**T1.2 — Anti-clobber (reframed; CRITICAL).**
The real hazards: touch-resize handles armed by default on phones today; `h` bypassing GridStack's column cache (any mobile height change writes straight into the desktop slot); `layoutsNodesChange()` corrupting the cached desktop layout on mobile drags, which `save()` then persists. Mitigations, ALL required: (a) `setStatic(true)` whenever effective column count is 1 — single mechanism; do NOT mix with `enableMove`/`enableResize`, which are silent no-ops under static; (b) hard guard in `saveLayout()` — early-return when collapsed; (c) pin the load-order invariant: the change handler is wired only after `grid.load()` resolves (today an accident of `.finally()` ordering at v2.js:411–419) — make it explicit with a comment + acceptance check so no refactor re-arms cold-load clobber. Acceptance test mandatory: record `updated_at` → full phone session on `/app` including deliberate touch/drag/resize attempts → `updated_at` unchanged, desktop renders identically.

**T1.3 — Mobile restructure (v2.css; restructuring, not typography).**
At ≤768px: tiles auto-height with per-tile internal scroll containers removed (no ~2,900px stack of nested scrollers); `.regime-band` 6-column grid → wrapped chips (32px columns cannot hold 22px type at 390px); `.mem-row` / `.th-row` width fixes; `.v2-topbar` wraps or fits ≤390px and `body` gets an overflow-x guard (the topbar's ~420px min-content is the one element forcing document-level horizontal scroll); touch targets ≥ 44px; staleness ages visible on all 11 tiles (Ruling 6 — river included).

**T1.4 — Bottom deck bar (3 tabs; fixed-position reality).**
`position: fixed` bar on `v2.html` + legacy `index.html`, mobile-only, S-6M owns Stater surfaces. Content-occlusion reserve: `padding-bottom` on `.container` (`styles.css:70` — **styles.css is hereby the sixth tracked target**) AND v2's scroll container, so the last tile clears the bar. Safe-area: `viewport-fit=cover` + `env(safe-area-inset-bottom)` padding so the bar clears the iPhone home indicator (zero safe-area handling exists in `frontend/` today). Hrefs hardcoded: `/app` (AGORA, active), `/app/stater` (STATER), `/app/analytics` (ABACUS) — never derived via `buildModePath` (emits 404-prone two-segment paths). Standing constraint: any future route is declared ABOVE the `main.py:1864` catch-all. Bar markup + CSS filed as a standalone reusable snippet for S-6M (one component, two lanes, zero drift).

**T1.5 — PWA (corrected fix set).**
On `v2.html` AND `index.html`: `<link rel="manifest">`, `apple-touch-icon`, and `apple-mobile-web-app-*` tags (none exist anywhere today). `manifest.json`: `start_url` → **`/app`** (`/` serves a JSON health payload, not the dashboard). Theme-color aligned. No service worker — standalone install is therefore **iOS-only in Phase 1** (Android's install prompt requires the SW, deferred to Phase 2; Nick's device is an iPhone).

**T1.6 — Cache-bust.**
Bump `?v=` on every touched asset so phones don't serve stale files.

**T1.7 — `grid.load()` tile-deletion defect (pre-existing; fixed here).**
`v2.js:411` calls `grid.load(d.layout)` with `addRemove` defaulting to true — every tile whose `gs-id` is absent from the saved row is deleted from the DOM. Consequence today: any newly deployed tile silently vanishes for saved-layout holders (i.e., Nick). Fix: load without removal and reconcile — tiles present in markup but absent from the saved layout stay visible at a sane default position. Acceptance: simulate a saved row missing one tile; the tile renders.

**Phase 1 Done Definition (v1.2)**
- [ ] `backup_20260724` row exists (T1.0)
- [ ] Phone screenshot vs mockup Deck 1 frame (minus glance row): legible single column, T1.1 order, zero horizontal scroll
- [ ] T1.2 clobber test passed (`updated_at` unchanged; desktop identical; grid static on phone)
- [ ] T1.7 reconcile test passed (missing-from-row tile still renders)
- [ ] Deck bar navigates all three surfaces; last tile fully visible above the bar; bar clears the home indicator
- [ ] iOS Add to Home Screen from `/app`: standalone, named, Pandora icon (Android install expressly deferred)
- [ ] Desktop rendering and behavior identical ≥ 769px
- [ ] Live-verified on production, not just committed (committed ≠ deployed ≠ validated)

**Phase 1 deploy-window gate (ATHENA, v1.2):** deploy only if commit + Railway deploy + live verification complete by **EOD Fri 2026-08-01 (MDT)**, the vacation-safe sprint's critical path is not displaced, and a **build-time re-diff of all six targets** (`v2.html`, `v2.css`, `v2.js`, `index.html`, `manifest.json`, `styles.css`) against origin/main HEAD shows no unresolved cross-lane changes. Miss the window → Phase 1 ships with Phase 2 after 2026-08-15. Never deploy 08-04 → 08-15. **Conditional carve-out:** if Phase 1 misses the gate, T1.0 + T1.2's `saveLayout()` guard alone (clobber insurance) may ship as a standalone spine-cleared hotfix before 08-01, since that hazard is live regardless of this build.

**STOP-GATE:** hard stop after Phase 1. Do not begin Phase 2 without an explicit go from Nick (calendar-gated regardless).

## 5. PHASE 2 — Full shell (2026-08-15+ only)

**T2.1 — Layout slots (backend; ATLAS lane; simplified per P0.1).**
No schema migration. Slots are **additional rows** in `v2_dashboard_layout` keyed by `layout_key`: `'default'` (desktop, untouched forever), `'mobile:agora'`, `'mobile:book'`, etc. Handler gains an allowlisted `key` param; `'default'` remains the hardcoded fallback so the desktop code path is byte-identical (shadow-by-default). Any true schema change goes through `migrations/` + the `init_database()` mirror — never by editing `_ensure_table()`, which is a silent no-op on the live DB. Slot payload = versioned JSON (`layout_version`, order, per-module size S/M/L, hidden flags, glance pins). Note of record: GridStack's column cache does not carry `h` — separate rows are the ONLY safe home for S/M/L heights. AEGIS riders from P0.1, decided at Phase 2 order time: auth-gate GET (currently public), add CSRF check on POST, stored-XSS check on the layout POST payload (spine addition, 2026-07-24).

**T2.2 — Glance row (Agora mobile).**
Pinned 2×2 above the stack; defaults Regime / Index / Book / Kairos; data sourced from existing tile feeds — no new endpoints; staleness surfaced.

**T2.3 — Edit mode (per deck, mobile).**
Per the Edit Mode mockup frame: list editor with drag-handle reorder, S/M/L per module, hide toggles, pin swap on Agora; Save → POST the deck's mobile slot; Cancel discards. Save status surfaced ("saved / failed / sign in") — no silent failure.

**T2.4 — BOOK deck + fourth tab (rescoped per P0.4/P0.5).**
New mobile surface off the Book tile's existing endpoints (`/api/portfolio/balances`, `/api/portfolio/pnl`, `/api/v2/positions?status=OPEN`): summary strip (day P/L, open risk), one card per open position — structure, DTE, opened date (present), P/L% (derived client-side). **Preconditions before this deck ships:** fix the always-zero greeks branch (`unified_positions.py:1152-1165`) or render the `stale: true` flag already on the wire — the mobile deck must not inherit the live fake-healthy; hoist the double-fetched open-positions payload (v2.js:1132 + :663). **Omitted, with a recorded work package:** bucket chips and B3-count chips have no runtime source (caps live only in the prompt layer; 0/304 historical rows carry a signal) — honest enablement = a real `bucket` column on `unified_positions` with a CHECK constraint, wired on create and update; separate future brief. `stop`/`target` render `—` when NULL (currently 20/20). "Closed today" requires a `since`/`limit` param server-side or is descoped — gate decision at Phase 2 order time. **Semantic constraint (mandatory):** the only implemented circuit breaker is the market-risk SPY/VIX one — if surfaced, label it "Market CB (SPY/VIX)", never group it with discipline chips, and add a fourth UNKNOWN state before reusing the kill-switch logic (v2.js:160-164/:208-211 currently collapses fetch failure into "CLEAR" — fail-open, do not copy).

**T2.5 — Abacus deck.**
Bottom bar + responsive CSS pass on the legacy Abacus surface only; content stays current-surface per the standing veto. **Stater's entire mobile pass is superseded by the S-6M lane charter** — its design happens in that lane (3-concept mockup gate → Nick reaction → brief), its brief routes through Fable for the HELIOS gate, and it consumes this brief's bar component + `deck='stater'` layout slot.

**T2.6 — Optional service worker.** Static shell only, versioned cache name, network-only for `/api/*` (AEGIS: never cache API/account responses). Skippable if flaky.

**Phase 2 Done Definition**
- [ ] Post-deploy screenshots vs all five mockup frames (MOCKUP GATE closure)
- [ ] Customizations persist across relaunch AND on a second phone/browser (server slot, not device-local)
- [ ] Desktop regression: arrange desktop → edit mobile heavily → desktop slot bit-identical
- [ ] Edit-save round-trip verified against production
- [ ] Per-deck slots verified independent (editing Agora doesn't touch Book, etc.)

## 6. Titans record (condensed)

- **ATLAS:** Sole schema touch eliminated — T2.1 is now additive rows, no DDL; migration-convention correction recorded (`migrations/` + `init_database()` mirror, never `_ensure_table()`); T1.0/T1.2 are the Phase 1 correctness items. Conviction HIGH.
- **HELIOS:** Design authority = approved mockup; T1.3 restructuring serves the approved legibility intent; hard rules embedded (staleness on all 11 tiles, no hidden state, no dead tabs, no touch drag-resize, fail-open patterns banned). Conviction HIGH.
- **AEGIS:** Rotation-era riders logged (public GET, no CSRF on POST) — decided at Phase 2 order time; SW stays deferred; no credentials enter client code. No veto.
- **ATHENA:** v1.2 self-certified under the standing Titans record (changes reduce risk and stay inside the reviewed architecture — delta note to spine, no full re-pass at 8 days to gate); S-6M cession intact; deploy gate incl. six-target re-diff + hotfix carve-out. Approved for CC.

## 7. Risk register (v1.2)

1. **Live touch-resize clobber (pre-existing, armed today)** — mitigated T1.0 (backup row) + T1.2 (static + guard + pinned load-order invariant). Interim: Nick avoids `/app` on phone until deploy.
2. **`grid.load()` tile deletion (pre-existing)** — T1.7; explains future "deployed tile invisible to Nick" ghosts before they happen.
3. **Fail-open kill-switch rendering + always-zero greeks (pre-existing fake-healthy, desktop)** — flagged to spine for triage; Phase 2 constraints recorded; not Phase 1 scope.
4. **Stale cached assets on phone** — T1.6 version bumps; no SW pre-vacation.
5. **Scope creep into Stater/Abacus content** — rulings 1, 5, 8 are the fence.
6. **Cross-lane drift into the six targets** — build-time re-diff in the deploy gate.
