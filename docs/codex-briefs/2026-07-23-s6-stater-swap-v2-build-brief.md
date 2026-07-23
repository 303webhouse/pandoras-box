# S-6 BUILD BRIEF — STATER SWAP v2 UI · C2 COCKPIT GRID

**Brief ID:** S6-BUILD-01 · **Authored:** 2026-07-23, Fable (coordination lane)
**Status:** APPROVED — Titans final review passed 2026-07-23, six conditions folded into this text (record: `docs/strategy-reviews/stater-swap-redesign/2026-07-23-titans-final-s6-brief.md`). CC launch authorized once Task 0 lands on `origin/main`.
**Baseline:** `origin/main` @ `49f702e` (verified 2026-07-23). Repo overrides this brief wherever they disagree — flag conflicts, don't improvise.
**Hard dates:** Deploy by **2026-07-31**. Post-deploy screenshot comparison **2026-08-03** (HELIOS, standing veto). **No deploys 2026-08-04 → 2026-08-15.** If the 07-31 deploy slips, S-6 holds past the window — per HELIOS Pass 2, an unverified UI does not sit unaccepted through an 11-day no-code period.

---

## 1. Mission

Build the Stater Swap v2 crypto surface as the approved **C2 Cockpit Grid** concept: all six symbols (BTC / ETH / SOL / HYPE / ZEC / FARTCOIN) visible at once as a 2×3 grid of compact cards, detail in the existing v2 drawer pattern, ported entirely into the Agora v2 design system. The page's single job: **"Is there a trade right now, and does discipline permit it?"** Go/no-go surface, not a data browse.

Sign-off authority: `helios-mockup-track.md` log entry 2026-07-23 — Nick selected C2; iteration deferred to in-use tweaks. **Build to the approved render. No unrequested design improvements.** Deviations require a Fable ruling before code.

## 2. Canonical references (read all in Phase 0)

1. `docs/strategy-reviews/stater-swap-redesign/helios-mockup-track.md` — binding gate text + required surface inventory + sign-off log.
2. `docs/strategy-reviews/stater-swap-redesign/2026-07-22-stater-swap-v2-mockup-concept-plan.md` — C2 definition, honest-seam requirements, live payload values used in renders.
3. Approved C2 render — Figma: `https://www.figma.com/design/yYehgiOjzTOBeqh9hogs1H/Stater-Swap-v2-%E2%80%94-Concepts` (C2 frame). **Layout truth.** Frozen export required per Task 0 before build.
4. `docs/strategy-reviews/stater-swap-redesign/2026-07-12-stater-swap-v2-committee-brief.md` — R-5 source of the surface inventory (context only; the mockup-track distillation is binding).
5. `frontend/v2.html` / `frontend/v2.js` / `frontend/v2.css` (v=9) — design tokens, chip/drawer/regime-band patterns. **Inherited, not chosen. Do not invent styling, hex values, or type scales.**

Precedence on conflict: approved C2 render → mockup-track charter inventory → concept plan prose → this brief. Any material conflict = STOP, report to Fable.

## 3. Task 0 — Freeze the comparison target (BLOCKING, before any build)

`49f702e` committed only the sign-off log line — **no render assets are in the repo**, and the Figma file is flagged for in-use tweaks, so it can drift after sign-off. The 08-03 screenshot comparison needs an immutable target.

- **T0.1 (Nick):** Export the approved C2 frame from Figma as PNG (desktop framing, at-sign-off state). Drop at `docs/strategy-reviews/stater-swap-redesign/renders/c2-cockpit-grid-signoff-2026-07-23.png`. **Deadline 2026-07-24 — this is the only Nick-side item on the critical path to 07-31.**
- **T0.2 (CC):** Commit the render + this brief's companion handoff file `docs/strategy-reviews/stater-swap-redesign/2026-07-23-s6-lane-handoff.md`. Pathspec-only. Verify both on `origin/main` before proceeding.
- No mobile render exists — the mobile collapse (§6) is spec-defined in this brief and is compared against spec + tokens, not a render.

## 4. Phase 0 — Read-only investigation (STOP-GATE SG-0)

No code until Phase 0 findings are filed and acknowledged. Standard sync hygiene first: `git fetch && git status` on the build machine; confirm clean tree at `49f702e` or later.

Investigate and report:

- **P0.1 Frontend mount point.** Where does the current Stater Swap surface live, and where does the v2 page mount (route, file, nav entry)? Inventory existing crypto frontend code that S-6 replaces vs. reuses.
- **P0.2 Token + pattern inventory.** Extract the v2 palette, type scale, chip, drawer, and regime-band patterns actually in `frontend/v2.css` v=9. Confirm the existing responsive breakpoint token, if any (needed for §6).
- **P0.3 Payload contracts, live.** Hit and record current response shapes for: `/api/crypto/regime`, `/api/crypto/clock`, `/api/crypto/tape-health`, `/api/crypto/cycle-extremes`, the crypto signal feed source, and the discipline-state endpoint. Confirm which fields are present vs. absent today (notably: `cta_zone` presence; any S-5-dependent dial fields; `breakout_prop` absent from `hub_get_portfolio_balances` → distance-to-floor uncomputable). **Branch rules:** if no discipline-state endpoint exists, STOP at SG-0 — hidden backend dependency, Fable scope ruling required, do not build around it. If no live crypto signal-feed source exists, the feed renders honest-empty-with-reason and the build proceeds. Record whether the six symbols are fetchable in one batched call or only per-symbol — the perf budget wants one refresh cycle, not six.
- **P0.4 Render reconciliation.** Compare the frozen C2 render against the charter's seven-surface inventory (§5). Flag any block whose placement or content differs between concept-plan prose and render (known candidate: macro-band contents — charter says DXY / real yields / calendar; concept-plan inventory line lists funding/OI/basis/liqs, which per the render belong to per-card blocks and tape-health). Render + charter win; log the resolution.
- **P0.5 Signal feed placement.** Confirm from the render where the feed lives in C2 (global below grid vs. per-symbol in drawer) and record it as the build spec.

File findings at `docs/strategy-reviews/stater-swap-redesign/s6-phase0-findings.md`, commit, **STOP for Fable ack.**

## 5. Build scope — the seven surfaces (charter-binding, all mandatory)

Layout per the frozen C2 render. Coverage per the mockup-track inventory:

- **S5.1 Global chips row (pinned top):** dual-labeled session clock **rendered straight from `/api/crypto/clock` — the UI renders time, it never computes it**; weekend/thin-liquidity flag; BTC master regime chip; discipline chips (see S5.6); **distance-to-floor — in this header, always visible, per the 2026-07-13 carry-forward. Red-state thresholds are config-driven and hot-reloadable (no redeploy-to-tune). Renders unavailable-with-reason until `breakout_prop` ships; the per-card rings in S5.2 are additional, not a substitute.** Staleness affordance visible without clicks.
- **S5.2 Symbol grid (2×3):** one card per symbol — regime chip (per-symbol), tape state, cycle position, tier badge, per-block health, and the **distance-to-floor ring** (C2's signature element). Ring renders **unavailable-with-reason** while `breakout_prop` is absent — never zero, never a filled ring. Component reads a nullable field so the ring lights up without a code change once `breakout_prop` ships.
- **S5.3 Drawer detail (existing v2 drawer pattern):** per-symbol regime header, tape-health strip (CVD state chip SPOT-LED / PERP-LED / MIXED + slope, funding, OI delta, basis), and per-render placement of the signal feed.
- **S5.4 Cycle Extremes dial:** **single-axis marker (CAPITULATION ⟷ FROTH), not two tables.** FROTH copy reads **"reduce new risk," never "sell."** Per-symbol coverage stated in the header; N/A cells explicit. Any S-5-dependent field absent today renders as an honest seam (unavailable-with-reason), not a stub.
- **S5.5 Collapsed macro band:** Horse-Rule-separated context (DXY, real yields, calendar). Feeds zero scalp scores. Visually subordinate; collapsed by default.
- **S5.6 Discipline chips:** daily loss, concurrent count, cooldown state — **rendering enforced backend state, never client math.** Visibility-based polling client-side only (pause when tab hidden).
- **S5.7 Signal feed:** governance tags (shadow/live); full setup cards — entry / invalidation / size **including est. funding cost over intended hold and liquidation-distance-in-ATRs**; tier badge.

**Honest-seam acceptance states (these are the tests, not edge cases):**
- **FARTCOIN per-block degradation:** BASIS and LIQS down while FUNDING / OI / REGIME / TAPE healthy — the card and drawer must show partial degradation per block. A symbol that can only be wholly healthy or wholly broken fails.
- **Distance-to-floor:** unavailable-with-reason on every card, per S5.2.
- **N/A discipline everywhere:** never fake-neutral, never silently blank, staleness always visible. Fail-closed rendering — fake-healthy is a P0 bug class.

## 6. Mobile collapse — single column (sign-off carry-forward, mandatory)

C2 scored worst-on-phone of the three concepts, and Nick is phone-only 08-04 → 08-15. This section is why the window exists.

- At the v2 narrow breakpoint (P0.2 confirms token; default ≤768px if none exists), the 2×3 grid collapses to a **single-column stack of all six cards**, tier order: BTC, ETH, SOL, HYPE, ZEC, FARTCOIN.
- Chips row stays pinned, wraps to max two lines; no chip silently dropped.
- Drawer becomes a full-height sheet.
- **No horizontal scroll at 390px width.** Tap targets ≥44px. Distance-to-floor reason text remains readable, not truncated to ambiguity. All honest-seam states preserved at mobile widths.
- Verify at 390×844 viewport before SG-2.

## 7. Stop-gates

- **SG-0:** Phase 0 findings filed → Fable ack → build may start.
- **SG-1 (layout gate):** After S5.1 + S5.2 scaffold renders with live data — screenshot vs. frozen C2 render, reviewed by HELIOS via Fable, before drawer/dial/feed work proceeds. Catch layout drift early, not on 08-03.
- **SG-2 (pre-deploy):** All seven surfaces + §6 mobile pass local verification, honest-seam states demonstrated with screenshots (FARTCOIN degraded, ring unavailable-with-reason, mobile 390px). Fable go required to deploy.
- **SG-3 (post-deploy, 2026-08-03):** Screenshot comparison of the live deployed surface vs. frozen render — **HELIOS standing veto.** Independent Fable verification of the live endpoint. Committed ≠ deployed ≠ validated.

**Screenshot protocol (all gates):** desktop captures at the frozen render's framing; mobile captures at 390×844 against §6. Unmatched viewports invalidate the comparison.

## 8. Guardrails

- **Git:** pathspec-only commits, never `git add .`. Commit messages via `C:\temp\commitmsg.txt` with `git commit -F`. Verify every deliverable file lands on `origin/main` (brief-orphan failure class).
- **AEGIS lane:** the client consumes backend `/api/crypto/*` routes only — it never calls the Hub MCP endpoint. `MCP_BEARER_TOKEN`, `UW_API_KEY`, and every other credential stay server-side; nothing credential-bearing in client code, console output, or logs. Existing v2 auth pattern only, no new auth surface.
- **Perf:** market-hours performance budget per HELIOS lane — visibility-based polling only, no polling storms across six symbols; batch where the render allows.
- **No shadow-enforcement concerns:** S-6 is display-only. It renders enforced backend state; it enforces nothing client-side.

## 9. Out of scope (do not touch)

- `breakout_prop` backend work in `hub_get_portfolio_balances` — separate lane; S-6 only consumes it nullable.
- S-5 Cycle Extremes backend enrichment — S-6 renders what the payload provides, honest seams for the rest.
- Any new API endpoints, committee/Olympus files, order entry or trade execution UI, Agora v2 (equities) surfaces.

## 10. Olympus impact

None — S-6 ships no hub MCP tools and touches no Olympus skills or committee files. The standing obligation (Olympus Impact + connector re-toggle + BTC/SPY committee re-test on MCP-shipping briefs) is not triggered.

## 11. Definition of done

All seven surfaces live per frozen render · both honest-seam states demonstrable in production · mobile single-column verified at 390px · SG-3 passed with HELIOS sign-off recorded in `helios-mockup-track.md` (gate step 3) · deployed on or before 2026-07-31 · Fable live-endpoint verification logged.
