# Build Backlog

Authoritative queue of in-flight, near-term, and deferred build work for Pandora's Box. Maintained as ATHENA's canonical reference for priority arbitration during Titans review passes.

**Last updated:** 2026-05-22 (post Phase A closure)
**Maintained by:** ATHENA (Olympus Titans synthesis lane). Nick or CC may update directly when items are added, promoted, demoted, or closed.

---

## How to use this file

**Tier definitions:**
- **Tier 1 — Foundation / High-leverage / Gated.** Items currently in scope or immediately next. Foundational architecture, critical reliability, or items that unblock multiple Tier 2 builds. ATHENA pulls from this list when arbitrating "what's next."
- **Tier 2 — Tactical / Queued.** Items waiting for Tier 1 dependencies or for capacity. Typically days of work each. ATHENA can promote items to Tier 1 when gates clear.
- **Tier 3 — Research / Speculative / Post-ZEUS.** Lower-priority builds, exploratory work, or items gated on major future milestones (ZEUS phases, broker API integration, etc.). Reviewed periodically; not actively scheduled.

**Status conventions per item:** `QUEUED` (default), `IN_FLIGHT` (build active), `BLOCKED: <reason>` (gated), `CLOSED: <commit>` (shipped, link to closure note).

**Update protocol:**
- New items added at the bottom of their tier with a one-line problem statement + initial bucket fit (foundation / tactical / quick win).
- Promotions/demotions noted in the **Update log** at the bottom with date and reason.
- Closure: move to **Recent closures** with commit SHA and closure note path. Do not delete history.
- Cross-cutting framework debt lives in its own section, not the tiers.

---

## Top of queue (active scope)

*Empty.* Phase A closed as `363cde6` on 2026-05-22. PIVOT skill promotes to active scope when next session starts on it.

---

## Tier 1 — Foundation / High-leverage / Gated

### 1. PIVOT skill — last Olympus persona (orchestration)
**Bucket:** Foundation.
**Status:** QUEUED, top of Tier 1.
**Why:** Final Olympus committee member. Synthesis lane. Currently exists as `skills/user/pivot/SKILL.md` per available skills surface — needs cross-reference review, equities/crypto references, and integration check with the six existing analyst skills (TORO, URSA, PYTHIA, PYTHAGORAS, DAEDALUS, THALES).
**Gates:** None blocking. Top of queue when next session begins.
**Unblocks:** Olympus committee cross-review pass (all seven personas reviewing each other's skills).

### 2. Phase B — `get_bars` migration off yfinance to UW
**Bucket:** Foundation.
**Status:** QUEUED.
**Why:** Closes the last yfinance dependency in the hot path per Data Source Hierarchy (memory #10). Audit Section 5 scoped this; Phase A delivered the `get_ohlc` wrapper that Phase B will consume. Smaller scope now than originally estimated.
**Gates:** Phase A's `get_ohlc` wrapper shipped (✓ in `363cde6`). Ready when scheduled.
**Unblocks:** Cleaner downstream consumers (sectors fallback, market_data, scanners, correlation_monitor, trip_wire_monitor).

### 3. Phase C — Outcome tracking re-walk projection
**Bucket:** Foundation.
**Status:** QUEUED.
**Why:** `signal_outcomes.MFE` is a point-in-time snapshot, not living truth. Phase C re-walks on current yfinance, projects results onto `signals.outcome*` columns, applies canonical-walker policy (daily resolver wins for B1/B2; 15-min resolver wins for B3). Per memory #23 and #26.
**Gates:** None blocking. Brief not yet authored.
**Unblocks:** 3-10 promotion re-audit (gated on Phase C + n≥250 signals), URSA stop-tightness recalibration, future strategy promotion gates.

### 4. OAuth on `backend/hub_mcp/` — transparent token refresh
**Bucket:** Foundation.
**Status:** QUEUED.
**Why:** Surfaced 2026-05-22 during Phase A smoke-test. Static `MCP_BEARER_TOKEN` goes stale after Railway deploys restart FastMCP, requiring manual Claude Desktop restart to recover. OAuth flow lets Anthropic's infra auto-refresh tokens transparently. Real operational reliability fix. Per memory #14.
**Gates:** None blocking. ATLAS + AEGIS Titans review territory; would extend `docs/operations/mcp-token-rotation.md`.
**Unblocks:** Persistent Olympus availability across sessions; reduces manual reconnect cost to zero.

---

## Tier 2 — Tactical / Queued

### Strategy and outcome work

- **3-10 oscillator promotion re-audit.** Gated on Phase C ship + n≥250 post-Phase-B `both`-gate signals with leave-one-out robustness. Current verdict: NOT YET (per `docs/strategy-reviews/raschke/3-10-promotion-reaudit-2026-05-08.md`). Per memory #26.
- **URSA stop-tightness recalibration.** Bounded MFE/MAE semantic shift post-Phase B. Sequencing: after Phase C ships.
- **`score_signals` pre-walk age cap remediation.** Per memory recent updates. Specific scope TBD on first ATHENA review.
- **BTCUSDT crypto ticker support.** Per memory recent updates. Probably small scope; could be quick-win bucket on closer look.

### Olympus committee enrichment (depends on Tier 1 #2 + #3)

- **Hub MCP Phase C — Olympus tactical enrichment expansion.** ~12 wrappers from audit OLYMPUS/BOTH buckets per Section 5: `stock/{ticker}/greeks`, `stock/{ticker}/flow-alerts`, `stock/{ticker}/oi-change`, `stock/{ticker}/expiry-breakdown`, `stock/{ticker}/spot-exposures`, `stock/{ticker}/volatility/term-structure`, `market/{ticker}/etf-tide`, `market/{sector}/sector-tide`, `option-trades/flow-alerts`, `institution/{ticker}/ownership`, `companies/{ticker}/profile`, `companies/{ticker}/earnings-estimates`. Uses Phase A's Redis envelope cache pattern.
- **Three v2 hub MCP tools for technical analysts** (per memory #29): `hub_get_options_chain` (DAEDALUS, lowest effort), `hub_get_chart_indicators` (PYTHAGORAS via TV webhook), `hub_get_market_profile` (PYTHIA via TV MP webhook, hardest). Gated on PIVOT + committee cross-review per memory.
- **Committee review logging.** Every Olympus pass persisted (ticker, ts, spot, per-agent read, PIVOT synthesis, conviction, entry/stop/target/invalidation) for outcome attribution. `outcome_source='COMMITTEE_REVIEW'`. Requires MCP v2 write-tool gates OR direct `/api/committee/log` endpoint. Per memory #24. At n≥250: PIVOT calibration, per-agent edge, B.06 hit rate, regime conditioning.

### UI / dashboard work

- **Phase A.5 — Ticker info sub-card.** Inline sub-card under heatmap row, on-demand. UX decided (HELIOS recommendation + ATHENA arbitration on 2026-05-22): inline expansion, NOT route to existing ticker-profile popup. Backend dependency: `companies/{ticker}/profile` wrapper (overlaps with Hub MCP Phase C scope above — bundle decision TBD).
- **Radar feature review.** Currently broken or useless per Nick injection 2026-05-22. Diagnose first, then fix or replace. Queued post-UW-MCP-build per Open Question 4 resolution.

### Framework / housekeeping

- **Titans reference docs authoring** (the five-doc set per Titan, ~20 total references). Currently all Titan `SKILL.md` files reference docs that do not exist; the "authoring status note" convention tells future agents to work from `PROJECT_RULES.md` + codebase in the interim. Sequence per ATHENA: ATLAS first (backend-architecture, database-schema, phase-gate-playbook, uw-integration-playbook, mcp-server-patterns), then ATHENA (bucket-framework-builds, priority-decision-framework, olympus-impact-checklist, arbitration-precedent-log), then AEGIS + HELIOS in parallel.

---

## Tier 3 — Research / Speculative / Post-ZEUS

*ZEUS = multi-phase project gating most Tier 3 work. Currently undefined in this backlog. Phase 3 of ZEUS specifically gates trading hub UI v3 per memory #27. ATHENA flags: ZEUS scope should be documented before scheduling any Tier 3 item that depends on it.*

- **HG Tier 1 strategy.** Queued after 3-10 cleared.
- **80-20 strategy.** Queued after 3-10 cleared.
- **Anti HG strategy.** Queued after 3-10 cleared.
- **News Reversal strategy.** Queued after 3-10 cleared.
- **Stater Swap crypto re-evaluation.** Full strategy redesign around UW + TV MCPs. Current crypto strategies pre-date MCP availability. Per memory recent updates.
- **THALES module deployment.** Currently THALES exists only as committee persona invoked manually. Module would deploy cross-sectional sector RS, narrow-leadership detection, sector divergence alerts on schedule with pushed notifications. Closest existing infra: `/api/watchlist/sector-strength`. Per memory recent updates.
- **Abacus widget overhaul.** Display strategies in use post-ZEUS tier routing. Current shows stale bias/factor data not matching flow-led pipeline. Per memory #27.
- **Trading hub UI v3.** Real-time UW + TV MCP streams, actionable flow/DP/GEX/profile at a glance. Gated on ZEUS Phase 3. Per memory #27.
- **X API Bookmark Intel Stream.** Post-ZEUS evaluation. ~$3/mo; Titans one-pager required before any build commitment. Per memory #27.

---

## Cross-cutting concerns

- **Diagnostic queue (low-priority):**
  - `hub_get_quote` returns `unavailable` for SPY after-hours (UW `/stock-state` behavior, not Phase A regression). Surfaced 2026-05-22 smoke-test. Diagnose separately.
  - `sector_strength.rs_10d` returning 0.0 for all sectors after-hours. Surfaced 2026-05-22 smoke-test. Likely data refresh quirk; verify behavior during RTH and document.

- **Comprehensive security review.** Future activity per AEGIS SKILL.md pre-production override mechanic. Triggers when (a) any broker trading API is connected, OR (b) Nick formally schedules it. AEGIS maintains the override-accepted findings backlog in the interim (currently empty; first entries will come as builds run).

---

## Recent closures

| Build | SHA | Closure note | Closed date |
|---|---|---|---|
| Phase A — Sector heatmap popup completeness via scheduled UW refresh | `363cde6` | `docs/strategy-reviews/phase-a-sector-heatmap-closure-note-2026-05-22.md` | 2026-05-22 |
| Titans framework — four `SKILL.md` files committed | `0d80f57` | (no formal closure — framework infrastructure) | 2026-05-22 |
| Titans framework — `_shared/TITANS_RULES.md` shipped | `12a6936` | (no formal closure — framework infrastructure) | 2026-05-22 |
| UW Integration Audit | `4ce3fd4` | (audit doc itself: `docs/uw-integration-audit-2026-05-22.md`) | 2026-05-22 |
| Outcome tracking Phase B | `e81d8a8` + `730ccfa` | `docs/strategy-reviews/phase-b-closure-note-2026-05-08.md` | 2026-05-08 |
| Outcome tracking Phase A | `0750e44` | (see Phase B closure note for context) | 2026-05-08 |

---

## Arbitration precedents (this session)

Recording priority calls made during ATHENA workflow passes that may set future precedent:

- **2026-05-22, Phase A review:** Phase A displaces PIVOT skill by 3-5 days. Displacement deemed worth it because Phase A closed a user-visible operational gap (heatmap popup) and was the canonical first test for the new Titans framework. Precedent: user-visible operational gaps in active dashboard surfaces can displace foundational committee work for short windows when the displacement is bounded.

- **2026-05-22, Phase A Pass 2:** ATHENA arbitrated Nick injection vs. ATLAS finding on yfinance scope. Nick proposed yfinance for ticker popup non-critical fields (market cap, 52w high/low). ATLAS pushed back: UW already wraps `/info` covering those fields. ATHENA ruled for ATLAS — UW first for everything UW covers; yfinance reserved for indices/breadth (`^VIX`, `^GSPC`, etc.). Precedent: Nick injection is input, not instruction; Titans can correct directional inputs when codebase audit data contradicts them.

- **2026-05-22, Phase A.5 UX:** ATHENA arbitrated the inline-sub-card vs. route-to-existing-ticker-profile-popup question (audit Open Question 1). Nick had no opinion. HELIOS recommended inline sub-card for scan-tab workflow preservation. ATHENA ratified HELIOS's call. Precedent: when Nick defers a UX decision, ATHENA defers to HELIOS in HELIOS's lane.

---

## Update log

| Date | Event | Details |
|---|---|---|
| 2026-05-22 | File created | Initial backlog authored from Nick's memory snapshot + this session's surfaces. Approved by ATHENA Pass 1 for canonical use. |
| 2026-05-22 | Closure | Phase A closed as `363cde6`. Moved to Recent closures. |
| 2026-05-22 | New Tier 1 item | OAuth on `backend/hub_mcp/` added; surfaced during smoke-test. |
| 2026-05-22 | New Tier 2 item | Phase A.5 (ticker info sub-card) entered backlog with UX decision recorded. |
| 2026-05-22 | New Tier 2 item | Radar feature review added; deferred post-UW-MCP per Nick injection. |
| 2026-05-22 | Promotion | PIVOT skill promoted to top of Tier 1 (was queued, now top-of-queue after Phase A closure). |
