# Build Backlog

Authoritative queue of in-flight, near-term, and deferred build work for Pandora's Box. Maintained as ATHENA's canonical reference for priority arbitration during Titans review passes.

**Last updated:** 2026-05-22 (v2 — ZEUS phase structure added, Phase A closure incorporated, four arbitrations from 2026-05-22 session locked in)
**Maintained by:** ATHENA (Olympus Titans synthesis lane). Nick or CC may update directly when items are added, promoted, demoted, or closed.

---

## Project context — ZEUS

ZEUS is the meta-project name for the multi-phase overhaul currently in progress. Phase labels (II, III, IV) are for tracking and grouping; exact execution order between phases is not strict — phases can interleave when scope warrants. **Phase I is the only phase formally in scope right now.**

| Phase | Scope | Status |
|---|---|---|
| **I** | Full Unusual Whales API integration into Pandora's Box (the work currently underway: Phase A heatmap popup, Phase B `get_bars` migration, Phase C Olympus enrichment + Phase A.5 ticker sub-card + OAuth on hub MCP) | IN_FLIGHT |
| **II** | Stater Swap (crypto account) complete strategy revision around UW + TV MCPs | QUEUED |
| **III** | Analytics functionality and dashboard overhaul (includes Trading hub UI v3, Abacus widget overhaul, related analytics surfaces) | QUEUED |
| **IV** | Great Library update / revision | QUEUED — scope TBD, recovery via codebase grep + Nick recall pending |

Items deeper in Tier 2 / Tier 3 that previously anchored on "post-ZEUS" now anchor on the specific Phase that fits them.

---

## How to use this file

**Tier definitions:**
- **Tier 1 — Foundation / High-leverage / Gated.** Items currently in scope or immediately next. Foundational architecture, critical reliability, or items that unblock multiple Tier 2 builds. ATHENA pulls from this list when arbitrating "what's next."
- **Tier 2 — Tactical / Queued.** Items waiting for Tier 1 dependencies or for capacity. Typically days of work each. ATHENA can promote items to Tier 1 when gates clear.
- **Tier 3 — Research / Speculative / Cross-Phase.** Lower-priority builds, exploratory work, or items in future ZEUS phases. Reviewed periodically; not actively scheduled.

**Status conventions per item:** `QUEUED` (default), `IN_FLIGHT` (build active), `BLOCKED: <reason>` (gated), `CLOSED: <commit>` (shipped, link to closure note).

**Update protocol:**
- New items added at the bottom of their tier with a one-line problem statement + initial bucket fit (foundation / tactical / quick win).
- Promotions/demotions noted in the **Update log** at the bottom with date and reason.
- Closure: move to **Recent closures** with commit SHA and closure note path. Do not delete history.
- Cross-cutting framework debt lives in its own section, not the tiers.

---

## Top of queue (active scope)

*Empty.* Phase A closed as `363cde6` on 2026-05-22. The Phase C bundle (next Tier 1 item) promotes to active scope when its brief is authored and Titans-reviewed.

---

## Tier 1 — Foundation / High-leverage / Gated

### 1. Phase C bundle — Olympus enrichment + Phase A.5 + OAuth (ZEUS Phase I)
**Bucket:** Foundation. Large multi-day build.
**Status:** QUEUED, top of Tier 1. Brief not yet authored.
**Why:** This bundle finally closes the committee data gap that has been hurting trade reviews (documented in the 2026-05-20 TSLA pass and 2026-05-22 HAL pass — three Olympus agents at half-power without chain/Greeks/IV/MP data). Also closes the Phase A.5 ticker-info sub-card UX gap and the MCP auth-reliability issue that hit this session.

**Bundle contents:**
- **Olympus enrichment wrappers (~12):** `stock/{ticker}/greeks`, `stock/{ticker}/flow-alerts`, `stock/{ticker}/oi-change`, `stock/{ticker}/expiry-breakdown`, `stock/{ticker}/spot-exposures`, `stock/{ticker}/volatility/term-structure`, `market/{ticker}/etf-tide`, `market/{sector}/sector-tide`, `option-trades/flow-alerts`, `institution/{ticker}/ownership`, `companies/{ticker}/profile`, `companies/{ticker}/earnings-estimates`. Use Phase A's Redis envelope cache pattern.
- **Three v2 hub MCP tools** (per memory #29): `hub_get_options_chain` (DAEDALUS — lowest effort), `hub_get_chart_indicators` (PYTHAGORAS via TV webhook), `hub_get_market_profile` (PYTHIA via TV MP webhook — hardest).
- **Phase A.5 — Ticker info sub-card.** Inline sub-card expansion under heatmap row, on-demand. UX decided 2026-05-22: inline expansion, NOT route to existing ticker-profile popup. Backend: `companies/{ticker}/profile` wrapper (shares with Olympus enrichment list above — single implementation serves both).
- **OAuth on `backend/hub_mcp/`.** Replaces static `MCP_BEARER_TOKEN` with OAuth flow so Anthropic's infra auto-refreshes tokens transparently. Eliminates the manual Claude Desktop restart cycle after Railway deploys. ATLAS + AEGIS Titans review territory. Extends `docs/operations/mcp-token-rotation.md`.

**Gates:** None blocking. Titans final review on the bundled brief is where scope-too-big risk gets evaluated — if the bundle is genuinely unwieldy, Titans split OAuth and/or A.5 into separate briefs.
**Unblocks:** DAEDALUS / PYTHAGORAS / PYTHIA full-power committee passes; reliable MCP availability across sessions; ticker drill-down UX in the heatmap.

### 2. Phase B — `get_bars` migration off yfinance to UW (ZEUS Phase I)
**Bucket:** Foundation hygiene. Smaller scope than original estimate.
**Status:** QUEUED.
**Why:** Closes the last yfinance dependency in the hot path per Data Source Hierarchy (memory #10). Phase A delivered the `get_ohlc` wrapper that Phase B consumes.
**Gates:** Phase A's `get_ohlc` wrapper shipped (✓ in `363cde6`). Independent of Phase C — can ship in parallel or after.
**Unblocks:** Cleaner downstream consumers (sectors fallback, market_data, scanners, correlation_monitor, trip_wire_monitor). Closes ZEUS Phase I.

### 3. PIVOT skill — last Olympus persona (post-ZEUS-Phase-I)
**Bucket:** Foundation.
**Status:** QUEUED. Held until ZEUS Phase I closes per Nick's "UW integration first" call on 2026-05-22.
**Why:** Final Olympus committee member. Synthesis lane. Exists as `skills/user/pivot/SKILL.md` per available skills surface — needs cross-reference review, equities/crypto references, and integration check with the six existing analyst skills.
**Gates:** ZEUS Phase I (Phase C bundle + Phase B) ships first.
**Unblocks:** Olympus committee cross-review pass (all seven personas reviewing each other's skills).

---

## Tier 2 — Tactical / Queued

### Outcome tracking and strategy promotion

- **Outcome Tracking Phase C** — re-walk projection onto `signals.outcome*` columns using current yfinance; canonical-walker policy (daily resolver for B1/B2, 15-min for B3). Per memory #23 and #26. Brief not yet authored. NOTE: distinct from ZEUS Phase C above (which is Olympus enrichment). Naming collision worth resolving in the brief — always reference as "Outcome Tracking Phase C" explicitly.
- **3-10 oscillator promotion re-audit.** Gated on Outcome Tracking Phase C ship + n≥250 post-Outcome-Tracking-Phase-B `both`-gate signals with leave-one-out robustness. Current verdict: NOT YET per `docs/strategy-reviews/raschke/3-10-promotion-reaudit-2026-05-08.md`.
- **URSA stop-tightness recalibration.** Bounded MFE/MAE semantic shift post-Outcome-Tracking-Phase-B. Sequencing: after Outcome Tracking Phase C ships.
- **`score_signals` pre-walk age cap remediation.** Specific scope TBD on first ATHENA review.
- **BTCUSDT crypto ticker support.** Probably small scope; possible quick-win bucket on closer look.

### Olympus / committee infrastructure

- **Committee review logging.** Every Olympus pass persisted (ticker, ts, spot, per-agent read, PIVOT synthesis, conviction, entry/stop/target/invalidation) for outcome attribution. `outcome_source='COMMITTEE_REVIEW'`. Requires MCP v2 write-tool gates OR direct `/api/committee/log` endpoint. Per memory #24. At n≥250: PIVOT calibration, per-agent edge, B.06 hit rate, regime conditioning. Should ship after PIVOT skill and before Outcome Tracking Phase C runs at scale.

### Framework / housekeeping

- **Titans reference docs authoring** (~20 references across the four Titans). Currently all `SKILL.md` files reference docs that do not exist; the "authoring status note" convention tells future agents to work from `PROJECT_RULES.md` + codebase in the interim. Recommended sequence: ATLAS first (backend-architecture, database-schema, phase-gate-playbook, uw-integration-playbook, mcp-server-patterns), then ATHENA (bucket-framework-builds, priority-decision-framework, olympus-impact-checklist, arbitration-precedent-log), then AEGIS + HELIOS in parallel.

### Radar feature (UI)

- **Radar feature review.** Currently broken or useless per Nick injection 2026-05-22. Diagnose first, then fix or replace. Queued post-ZEUS-Phase-I per Nick's deferral.

---

## Tier 3 — Research / Speculative / Cross-Phase

### ZEUS Phase II — Stater Swap

- **Stater Swap (crypto account) complete strategy re-evaluation.** Full strategy redesign around UW + TV MCPs and new data feeds for both scalping and swing trading. Current crypto strategies pre-date MCP availability. Per memory recent updates + Nick recall 2026-05-22.

### ZEUS Phase III — Analytics + dashboard overhaul

- **Abacus widget overhaul.** Display strategies in use post-tier-routing. Current shows stale bias/factor data not matching flow-led pipeline. Per memory #27.
- **Trading hub UI v3.** Real-time UW + TV MCP streams, actionable flow/DP/GEX/profile at a glance. Per memory #27. Anchored on Phase III dashboard work itself rather than as a Phase-III-prerequisite-gated item.

### ZEUS Phase IV — Great Library

- **Great Library update / revision.** Scope TBD. Recovery via codebase grep + Nick recall pending. ATHENA flag: this should be defined before scheduling any Phase IV work. Suggested next step: small CC task to grep `C:\trading-hub` for "Great Library" references and surface any closure notes or briefs that clarify scope.

### Post-ZEUS or unphased

- **HG Tier 1, 80-20, Anti HG, News Reversal strategies.** Queued after 3-10 oscillator cleared. Not strictly tied to a ZEUS phase.
- **THALES module deployment.** Currently THALES exists only as committee persona invoked manually. Module would deploy cross-sectional sector RS, narrow-leadership detection, sector divergence alerts on schedule with pushed notifications. Closest existing infra: `/api/watchlist/sector-strength`. Could fit into Phase III dashboard work or be its own thing.
- **X API Bookmark Intel Stream.** ~$3/mo. Titans one-pager required before any build commitment. Per memory #27. Post-ZEUS or Phase IV-adjacent.

---

## Cross-cutting concerns

- **Diagnostic queue (low-priority):**
  - `hub_get_quote` returns `unavailable` for SPY after-hours (UW `/stock-state` behavior, not Phase A regression). Surfaced 2026-05-22 smoke-test. Diagnose separately during RTH next session.
  - `sector_strength.rs_10d` returning 0.0 for all sectors after-hours. Surfaced 2026-05-22 smoke-test. Likely data refresh quirk; verify behavior during RTH and document.

- **Memory hygiene observation.** Nick's memory snapshot contained one ghost reference (ZEUS, ultimately recovered via Nick recall on 2026-05-22). There may be others. Not urgent, but worth a slow review pass through memory items #27, #29, and anywhere project names appear, to confirm current intent vs. memory residue. Cheap to do in a low-energy session; reduces future arbitration friction.

- **Comprehensive security review.** Future activity per AEGIS SKILL.md pre-production override mechanic. Triggers when (a) any broker trading API is connected, OR (b) Nick formally schedules it. AEGIS maintains the override-accepted findings backlog in the interim (currently empty; first entries will come as builds run).

---

## Recent closures

| Build | SHA | Closure note | Closed date |
|---|---|---|---|
| Build backlog v1 (this file's initial version) | `b700cc4` | (no formal closure — superseded by v2 this update) | 2026-05-22 |
| Phase A — Sector heatmap popup completeness via scheduled UW refresh | `363cde6` | `docs/strategy-reviews/phase-a-sector-heatmap-closure-note-2026-05-22.md` | 2026-05-22 |
| Titans framework — four `SKILL.md` files committed | `0d80f57` | (no formal closure — framework infrastructure) | 2026-05-22 |
| Titans framework — `_shared/TITANS_RULES.md` shipped | `12a6936` | (no formal closure — framework infrastructure) | 2026-05-22 |
| UW Integration Audit | `4ce3fd4` | (audit doc itself: `docs/uw-integration-audit-2026-05-22.md`) | 2026-05-22 |
| Outcome tracking Phase B | `e81d8a8` + `730ccfa` | `docs/strategy-reviews/phase-b-closure-note-2026-05-08.md` | 2026-05-08 |
| Outcome tracking Phase A | `0750e44` | (see Phase B closure note for context) | 2026-05-08 |

---

## Arbitration precedents

Recording priority calls made during ATHENA workflow passes that may set future precedent:

- **2026-05-22, Phase A review:** Phase A displaces PIVOT skill by 3-5 days. Displacement deemed worth it because Phase A closed a user-visible operational gap and was the canonical first test for the new Titans framework. Precedent: user-visible operational gaps in active dashboard surfaces can displace foundational committee work for short windows when displacement is bounded.

- **2026-05-22, Phase A Pass 2:** ATHENA arbitrated Nick injection vs. ATLAS finding on yfinance scope. Nick proposed yfinance for ticker popup non-critical fields. ATLAS pushed back: UW already wraps `/info`. ATHENA ruled for ATLAS — UW first for everything UW covers; yfinance reserved for indices/breadth (`^VIX`, `^GSPC`). Precedent: Nick injection is input, not instruction; Titans can correct directional inputs when codebase audit data contradicts them.

- **2026-05-22, Phase A.5 UX:** ATHENA arbitrated inline-sub-card vs. route-to-existing-ticker-profile-popup (audit Open Question 1). Nick had no opinion. HELIOS recommended inline sub-card. ATHENA ratified HELIOS. Precedent: when Nick defers a UX decision, ATHENA defers to the lane-owning Titan.

- **2026-05-22, ZEUS recovery:** ZEUS surfaced as a phantom memory reference, recovered via Nick recall as the meta-project name for the multi-phase overhaul. Phase I = UW integration (in-flight), Phase II = Stater Swap revision, Phase III = analytics/dashboard overhaul, Phase IV = Great Library. Precedent: memory snapshot can contain ghost references to past or partially-defined concepts; recovery path is Nick recall first, codebase grep second.

- **2026-05-22, Tier 1 ordering:** Nick ruled "UW integration first" → revised order is Phase C bundle → Phase B → PIVOT. Precedent: when multiple Tier 1 items compete, Nick can set ordering preference even if dependency graphs don't strictly require it.

- **2026-05-22, OAuth bundling:** OAuth on `backend/hub_mcp/` bundled into Phase C brief. Titans final review will catch if the bundle is too big and split it. Precedent: when an operational reliability fix is adjacent to a high-value build, default to bundling and let Titans final review arbitrate scope size.

- **2026-05-22, Phase C + Phase A.5 bundling:** Bundled because both share the `companies/{ticker}/profile` wrapper and the ticker popup UI is small enough to ride along. Tradeoff accepted: heatmap popup ticker sub-card waits longer. Precedent: when two builds share a non-trivial backend dependency, bundle by default unless the UX dimension is genuinely independent.

---

## Update log

| Date | Event | Details |
|---|---|---|
| 2026-05-22 | File created | Initial backlog authored from Nick's memory snapshot + this session's surfaces. Approved by ATHENA Pass 1 for canonical use. Committed as `b700cc4`. |
| 2026-05-22 | Closure | Phase A closed as `363cde6`. Moved to Recent closures. |
| 2026-05-22 | New Tier 1 item | OAuth on `backend/hub_mcp/` added; surfaced during smoke-test. |
| 2026-05-22 | New Tier 2 item | Phase A.5 (ticker info sub-card) entered backlog with UX decision recorded. |
| 2026-05-22 | New Tier 2 item | Radar feature review added; deferred post-ZEUS-Phase-I per Nick injection. |
| 2026-05-22 | Promotion | PIVOT skill promoted to top of Tier 1 (was queued, now top-of-queue after Phase A closure). |
| 2026-05-22 | v2 restructure | ZEUS phase context added. Phases I-IV labeled. Tier 1 reordered per Nick "UW integration first" call: Phase C bundle (Phase C + A.5 + OAuth) → Phase B → PIVOT. Stater Swap moved from Tier 3 → ZEUS Phase II. Dashboard items re-anchored on ZEUS Phase III. Great Library added as Phase IV with scope TBD. Six new arbitration precedents recorded. |
