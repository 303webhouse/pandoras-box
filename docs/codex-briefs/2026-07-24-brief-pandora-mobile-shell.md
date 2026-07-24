# Brief — Pandora Mobile Shell (4 Decks + Agora Mobile Layout)

**Target:** Claude Code (VSCode)
**Author:** Fable / HELIOS (design lead), 2026-07-24
**Status:** MOCKUP GATE satisfied — Nick approved `docs/mockups/pandora-mobile-shell-mockup.html` on 2026-07-24
**Depends on:** Nothing (Phase 1). Phase 2 is calendar-gated: **no work before 2026-08-15.**
**Deploy freeze:** ABSOLUTE — no deploys 2026-08-04 through 2026-08-15.
**v1.1 (2026-07-24):** Deconflicted with the S-6M mobile design lane charter — all `stater.html`/`stater.css` writes removed from this brief; T2.5 Stater pass superseded; P0.6 branch-overlap check added; deploy gate tightened.

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

**STOP-GATE:** post Phase 0 findings; proceed to Phase 1 only if P0.1–P0.3 hold no surprises. Any surprise → stop and surface.

## 4. PHASE 1 — "Legible on vacation" (small, low-risk)

**T1.1 — One-column mobile collapse (v2.js).**
Below 768 px, the grid renders as a single column. Default order (top→bottom): Regime, Movers, Kairos, Book, Themes, Sector Divergence, Breadth, Index, Yield Curve, USD Carry. Mechanism is CC's choice (gridstack columnOpts vs. explicit one-column sort) under the constraint in T1.2.

**T1.2 — Desktop-slot clobber guard (CRITICAL).**
While in one-column/mobile mode: dragging and resizing disabled, grips hidden, and `saveLayout()` hard-guarded so it cannot POST (e.g., early-return when effective column count is 1). Acceptance test is mandatory: record `/api/layout` `updated_at` → use the site on a phone viewport for a full session → confirm `updated_at` unchanged and desktop grid renders identically after.

**T1.3 — Mobile CSS pass (v2.css).**
`@media (max-width: 768px)`: tile typography up to legible sizes, touch targets ≥ 44 px, tile spacing per mockup Deck 1 frame (minus glance row — that's Phase 2), drawer/popup/modal surfaces usable at phone width.

**T1.4 — Shared bottom deck bar (3 tabs).**
AGORA · STATER · ABACUS on `v2.html` and legacy `index.html` only — S-6M owns adding it to Stater surfaces after 08-03. Mobile-only (hidden ≥ 768 px), active state per current page, plain links to the routes confirmed in P0.2, no client-side framework. Known temporary gap: navigating to Stater is one-way (no bar there yet) until S-6M lands the reciprocal bar — acceptable, time-boxed, and noted here so nobody "fixes" it out of lane. File the bar's markup + CSS as a standalone reusable snippet alongside this brief so S-6M consumes it verbatim (one component, two lanes, zero drift).

**T1.5 — PWA linking.**
Add `<link rel="manifest" href="/manifest.json">` + apple-touch-icon tags to `v2.html` and `index.html` (Stater's tags arrive via the S-6M lane); align theme-color with the manifest; verify `start_url` lands on Agora v2 (fix path only if P0.2 shows otherwise). No service worker.

**T1.6 — Cache-bust.**
Bump `?v=` on `v2.css` / `v2.js` (and any touched assets) so phones don't serve stale files.

**Phase 1 Done Definition**
- [ ] Phone screenshot vs mockup Deck 1 frame (minus glance row): legible, single column, correct default order
- [ ] T1.2 clobber test passed (updated_at unchanged; desktop grid identical)
- [ ] Deck bar navigates across all three surfaces; no dead tabs
- [ ] Add to Home Screen (iPhone) opens standalone with the Pandora icon
- [ ] Desktop rendering byte-identical in behavior (no regressions ≥ 768 px)
- [ ] Live-verified on production URL, not just committed (committed ≠ deployed ≠ validated)

**Phase 1 deploy-window gate (ATHENA):** deploy only if commit + Railway deploy + live verification complete by **EOD Fri 2026-08-01 (MDT)**, the vacation-safe sprint's critical path is not displaced, **and P0.6 shows zero file overlap with `s6-stater-build`**. Miss the window or find overlap → Phase 1 waits and ships with Phase 2 after 2026-08-15. Never deploy 08-04 → 08-15.

**STOP-GATE:** hard stop after Phase 1. Do not begin Phase 2 without an explicit go from Nick (calendar-gated regardless).

## 5. PHASE 2 — Full shell (2026-08-15+ only)

**T2.1 — Layout slots (backend; ATLAS lane).**
Extend `/api/layout` storage to slots keyed by `(user, device_class, deck)`; `device_class ∈ {desktop, mobile}`, `deck ∈ {agora, stater, abacus, book}`. Additive migration; existing row backfilled as `(desktop, agora)` and **never mutated**. Slot payload = versioned JSON (`layout_version`, module order, per-module size S/M/L, hidden flags, glance pins). Desktop code path behavior unchanged (shadow-by-default).

**T2.2 — Glance row (Agora mobile).**
Pinned 2×2 above the stack; defaults Regime / Index / Book / Kairos; data sourced from existing tile feeds — no new endpoints; staleness surfaced.

**T2.3 — Edit mode (per deck, mobile).**
Per the Edit Mode mockup frame: list editor with drag-handle reorder, S/M/L per module, hide toggles, pin swap on Agora; Save → POST the deck's mobile slot; Cancel discards. Save status surfaced ("saved / failed / sign in") — no silent failure.

**T2.4 — BOOK deck + fourth tab.**
New mobile surface off the Book tile's existing data path (P0.4): summary strip (day P/L, open risk), one card per open position (structure, bucket tag, P/L%, DTE, stop, opened date), add/close via the existing modal flow, closed-today list. Bucket/circuit chips only if P0.5 found a truthful source; otherwise omit.

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

- **ATLAS:** Sole schema touch is T2.1; additive-only, existing row immutable; T1.2 is the Phase 1 correctness item; P0.1/P0.5 close my unverified areas. Conviction HIGH on Phase 1, MODERATE on Phase 2 pending Phase 0.
- **HELIOS:** Design authority = approved mockup; hard rules embedded (staleness ages, no hidden state, no dead tabs, no touch drag-resize). Conviction HIGH.
- **AEGIS:** Layout writes stay behind existing auth; SW deferred / API never cached; no credentials enter client code. No veto.
- **ATHENA:** Displaces nothing in the vacation-safe sprint; Abacus v2 veto preserved; S-6M lane charter deconflicted (v1.1 — Stater ceded, P0.6 added); deploy gate as specified including the zero-overlap condition. Approved for CC.

## 7. Risk register

1. **Desktop-slot clobber** (T1.2) — the one way this build hurts Nick. Guard + mandatory test.
2. **Gridstack one-column ordering quirks** — P0.3 exists because 11.1.2's collapse ordering must be verified, not assumed.
3. **Stale cached assets on phone** — T1.6 version bumps; no SW pre-vacation.
4. **Scope creep into Stater/Abacus content** — rulings 1 & 5 are the fence.
5. **Untruthful bucket chips** — omit unless P0.5 finds a real source; fail-closed.
