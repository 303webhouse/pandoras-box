# Dual Review — Hub Scope (Titans + Olympus) — 2026-05-27

**Question under review:** Given that committee work is migrating to Claude.ai-on-demand (VPS committee crons decommissioned) and that a normal Claude.ai session has *no* direct UW access (only the Pandora hub proxy), what must **stay** in the hub, what is **luxury/clutter**, and what must be **fixed/added** to make the hub's trade system work — with Nick's stated priority that *chat committee headroom outranks a large options-data surface in the hub*.

**Inputs (all from `origin/main`, fetched 2026-05-27):**
- `docs/uw-mcp-committee-integration-audit-brief-2026-05-27.md` (CC's complete audit)
- `vps-decommission-brief-2026-05-27.md`
- Last-week commit log through `2939476` (2026-05-27 16:57 MT)
- `docs/build-backlog.md` (last substantive update 2026-05-22/24)

**DATA NOTE / fidelity:**
- Hub reachability confirmed earlier this session (`mcp_ping` → ok, schema v1.0). This review makes no price-anchored claims, so no `hub_get_quote` anchor is required.
- This is a **build-scope consult**, not a trade-verdict committee pass — there is no ticker. The Olympus agents therefore speak in **direct-consumer mode** (what data each needs to operate at full power), grounded in their `SKILL.md` data-caveat sections as captured verbatim in the audit's Part C. No live committee trade pass was run.
- **Partial Titans prereq:** `PROJECT_RULES.md` was not separately read in this pass; the review works from the audit + backlog + `_shared/COMMITTEE_RULES.md` + `_shared/TITANS_RULES.md` + today's commits. The formal **Titans Final Review on the authored brief** (workflow step 8) should re-run with full prereqs before CC executes. Treat this document as the Pass 1 → Pass 2 → Overview consult (workflow steps 2–5), advisory only — Nick makes the final call.

---

## Part 1 — Olympus Consumer Panel (direct-mode data-need reads)

The committee is **hard-gated on the hub**: per `COMMITTEE_RULES.md § Hub MCP Preflight`, no agent may produce trade-setup output (entry/sizing/structure/conviction/stop/target/invalidation) without the Pandora hub reachable, and agents are explicitly forbidden from falling back to web search or training data for flow / Greeks / IV / dark pool / technical / sector data. So the hub is not a convenience for the committee — it is the *only* sanctioned data path. That frames every read below.

### DAEDALUS (options structure / Greeks) — currently HALF POWER
- **Needs (essential):** per-contract Greeks (delta/theta/gamma/vega), IV rank/percentile, max pain, bid-ask spread % for the >10% liquidity hard-flag. Today DAEDALUS runs in "qualitative-IV mode" and must caveat every options read.
- **Closed by:** `hub_get_options_chain(ticker, expiry, option_type)` — **already built** (staged, ~750 LoC, registry-wired), needs only a live-market Greeks smoke + commit. The audit says this closes **100%** of DAEDALUS's documented caveat.
- **Luxury, not need:** `spot-exposures`, `expiry-breakdown`, `volatility/term-structure`, `option-trades/flow-alerts`, `ownership`, `earnings-estimates` — DAEDALUS's documented caveat is closed by the chain tool alone; the rest are enhancements, not gap-closers.
- **Synthesis-quality tax:** while DAEDALUS is half-power, PIVOT caps conviction on every options pass (demote-only rule #3 + DAEDALUS sizing dependency). Shipping the chain tool lifts the cap on the most common trade type Nick runs.

### PYTHAGORAS (structure / trend / TA) — currently HALF POWER
- **Needs (essential):** specific values for RSI, MACD, SMA (20/50/120/200 CTA stack), EMA, VWAP, BBANDS, ATR. Today these require a Nick screenshot or the read goes framework-only.
- **Closed by:** `hub_get_chart_indicators` — and the audit's decisive finding is that **UW already serves this** (`/technical-indicator/{function}`, 50+ functions). PYTHAGORAS's own SKILL.md prediction that this needs TradingView is **wrong** — it is a pure UW-wrap, same shape as the options-chain tool.
- **Luxury, not need:** the full 50-function list. Six functions (RSI, MACD, SMA, EMA, VWAP, BBANDS) cover the documented workflow; the rest expand later on demand.

### PYTHIA (market profile / auction) — currently FULLY BLOCKED
- **Needs (essential):** POC, VAH, VAL, IB width + classification, value-area migration, 80% rule, poor high/low. This is the single largest gap — PYTHIA has *no* hub path today and is fully reliant on Nick-provided levels.
- **Closed by:** `hub_get_market_profile` Phase 1 — and this is the **only** tool that genuinely requires the TradingView pipeline (UW exposes zero MP/TPO data). New infra: Pine indicators (Nick-side), Railway webhook receiver, `market_profile_levels` Postgres table.
- **Scope honesty:** Phase 1 (5 alert types) brings PYTHIA from *blocked* to *functional*, not to full power; Phases 2–4 are follow-ups. Biggest of the three builds (~12–20h).

### TORO / URSA (bull / bear) — already FULL POWER, no unmet need
- Both run on `hub_get_quote`, `hub_get_flow_radar`, `hub_get_bias_composite`, `hub_get_positions`, `hub_get_hydra_scores` — all shipped. **None of the proposed enrichment wrappers serve the bull/bear lane.** From TORO/URSA's seat, the ~9 extra enrichment wrappers are not data they consume.

### THALES (macro / sector, conditional) — no current need; one future hook
- Runs on sector strength + bias + macro context, which exist. The proposed `etf-tide` / `sector-tide` wrappers map to THALES's *deferred* module (Tier 3 — cross-sectional sector RS), **not** to current committee operation. So those two wrappers are "future-luxury tied to a deferred build," not present need.

### PIVOT (synthesizer) — no unmet data need; quality verdict
- Runs on `hub_get_quote` + `hub_get_portfolio_balances` + `hub_get_positions`, all shipped. PIVOT's stake is **synthesis quality**: three half-power analysts means PIVOT's demote-only rules fire more often than they should. The three core tools are the highest-leverage quality upgrade available to the committee. The ~9 enrichment wrappers do not change any agent's conviction and therefore do not change PIVOT's synthesis — by the committee's own logic, they are non-load-bearing.

**Olympus panel consensus:** the committee needs **exactly three** new hub tools (chain, indicators, market-profile). Everything else proposed in the Phase C "enrichment" list is not consumed by any agent's documented workflow.

---

## Part 2 — Titans Pass 1 (independent reviews)

### ATLAS — PASS 1
**BUILD:** Hub-scope rationalization (Phase C bundle re-scope) per UW MCP / Committee Integration Audit.

**PRE-REVIEW PREREQUISITES:** PARTIAL — `git fetch` done, reviewing against `origin/main` (local working tree 121 commits behind; irrelevant since review reads `origin/main`). Audit read in full. `PROJECT_RULES.md` not separately read this pass (flagged in DATA NOTE).

**VALIDATION CHECK:** Verified. The audit (file:line citations + git log + live tool inventory) is the canonical validation artifact, and it confirms the gap empirically: three agents documented half-power, `hub_get_options_chain` staged-but-uncommitted across 4 files, UW confirmed as the only viable source. This is validate-before-design satisfied.

**SCOPE FIT (backend lens):** The three tools extend the existing `hub_get_*` wrapper pattern correctly — central caching, single `UW_API_KEY` surface, and (critically) all UW calls stay inside `integrations/uw_api.py` where A.4a caller-tagging lives. D.2 (hub wrappers) over D.1 (direct UW MCP) is the right call on data-integrity grounds, not just security.

**FINDINGS:**
- `hub_get_options_chain` is the lead case and is non-destructive (read-only tool). The Greeks-verification smoke (`scripts/options_chain_greeks_smoke.py`) **is the gate** and has never been run — disposition is "not run, not failed." SEVERITY: ship-blocker only until smoke passes during RTH. Tighten pass criterion from ≥1 contract to the ATLAS Pass-1-amendment "5 ATM strikes both sides" before running (audit Q2).
- **Overdraw is the binding constraint, not a side note.** A.4a (commit `56ad4c0`) shipped against a 153%-of-cap overdraw. `hub_get_chart_indicators` is 6 UW calls/ticker/pass (RSI+MACD+SMA+EMA+VWAP+BBANDS); without confirmed headroom from A.4b/A.4c that re-blows the cap. SEVERITY: HIGH on sequencing.
- **Phase B (`get_bars` yfinance→UW) collides with the overdraw fight.** Retaining yfinance in the hot path is normally an ATLAS veto trigger — but migrating it onto a capped, over-budget UW account is worse right now. SEVERITY: MEDIUM. Resolution is sequencing, not cancellation.
- `hub_get_market_profile` introduces a new Postgres table (`market_profile_levels`) → migration must ship with an explicit rollback path (ATLAS hard rule). New webhook receiver is reviewed for *how it connects*, not the Pine logic.
- The ~9 enrichment wrappers each add a UW caller. On an over-budget account, every un-needed wrapper is pure load with no consumer. SEVERITY: MEDIUM (cost/integrity, not correctness).

**PHASE GATE REQUIREMENTS:** The three data tools are read-only → no dry-run/apply phasing. The MP Postgres migration is the only schema change → standard migration + rollback. The Greeks smoke is a hard-stop gate on the options-chain ship.

**DATA INTEGRITY IMPACT:** No canonical-table writes from the three tools. `market_profile_levels` is a new non-canonical read cache, must not be confused with `signals`/`unified_positions`. A.4a caller-tag discipline must extend to all three new tools (each passes an endpoint-grain tag).

**RECOMMENDATIONS:**
- Ship `hub_get_options_chain` first (gated on the tightened RTH smoke). Defer the `uw_api.py` dedupe (byte-identical helpers; cosmetic).
- Gate `hub_get_chart_indicators` and `hub_get_market_profile` behind confirmed UW headroom (A.4b/A.4c). Add a batch param to `chart_indicators` (one cache entry, N functions) to cut round-trips and load (audit Q6).
- Drop the broad enrichment-wrapper list; build per-endpoint only when a specific agent caveat demands it.

**VETO:** None.
**CONVICTION:** MODERATE — the three tools are architecturally sound and one is already built, but the overdraw sequencing is a real constraint that must be respected or it becomes a data-availability regression.

### AEGIS — PASS 1
**BUILD:** Hub-scope rationalization per audit.

**PRE-REVIEW PREREQUISITES:** PARTIAL — `claude_desktop_config.json` read (this session is on Nick's office PC); confirms only `desktop-commander` present, no UW/TV/Pandora entries (memory note stale, retire it). `docs/operations/mcp-token-rotation.md` not read this pass (flag).

**VALIDATION CHECK:** The security-relevant gap is verified: D.2 keeps UW behind one credential surface with caller-tagging; D.1 (direct UW MCP) would add a new credential surface and bypass A.4a attribution. The audit confirms direct UW MCP is vapor anyway (UW ships no MCP server). So the recommended path is also the lower-credential-surface path.

**CREDENTIAL SCOPE:**
- Data-API credentials touched: `UW_API_KEY` (existing; pre-production override applies — Nick-overridable, must be logged).
- Broker/trading credentials touched: None. (RH MCP is on the backburner per Nick — equities-only, no options trades yet — so no broker-execution credential enters scope here. The moment RH *trade* scope connects, the pre-production override expires and absolute broker veto applies.)
- New credentials introduced: TradingView webhook secret (for `hub_get_market_profile`).

**FINDINGS:**
- **TradingView webhook MUST validate signatures.** A webhook receiver without HMAC/shared-secret validation is an AEGIS veto trigger (spoofable ingestion into `market_profile_levels`). The PYTHIA build is **not** approvable without this (audit Q8). SEVERITY: HIGH (becomes a veto if the brief omits it).
- **Leaked GitHub PAT (this session).** The `origin` remote on `C:\trading-hub` carries a `ghp_` token in plaintext in the URL; it printed to terminal during this session's git work. This is a data/dev credential (not broker) → pre-production override available, but it is an **override-accepted finding** that must be logged and the token rotated + remote re-pointed to a credential helper. SEVERITY: MEDIUM. (Referring to it by name/location only, per ATHENA hard rule.)
- The three data tools surface market data only — no exfiltration boundary concern (no positions/credentials in their output envelopes).

**OVERRIDE-ACCEPTED FINDINGS:** (1) `UW_API_KEY` continues as the sole UW credential under pre-production override. (2) Leaked `ghp_` PAT — record in `pre-production-override-log.md`, rotate, re-point remote. Both feed the comprehensive security review backlog.

**AUDIT LOGGING COVERAGE:** New webhook ingestion should log fire events (ticker, level_type, fired_at) — already implied by the table schema; confirm the receiver logs auth failures too.

**ROTATION GUIDANCE:** TradingView webhook secret follows the shared-secret URL-token pattern; document rotation alongside `UW_API_KEY` in `mcp-token-rotation.md`.

**VETO:** None *as scoped* — conditional on the MP webhook brief including signature validation. If that brief is authored without it, AEGIS vetoes.
**CONVICTION:** MODERATE — clean except the webhook-signature requirement and the housekeeping token rotation.

### HELIOS — PASS 1
**BUILD:** Hub-scope rationalization per audit.

**PRE-REVIEW PREREQUISITES:** PARTIAL — Agora design-system reference not read this pass; working from known conventions (dark teal, vanilla JS, single `app.js`).

**VALIDATION CHECK:** From the UX lens, the verified gap is *committee output quality*, not a dashboard surface — the three tools are consumed by Claude.ai committee skills, not (primarily) rendered as Agora widgets. So HELIOS's direct surface here is limited, which is itself a finding: this build barely touches the dashboard.

**SURFACE INVENTORY:**
- Surfaces touched: committee output text (a surface in the ADHD sense), and — *if* any of the three tools feed Agora widgets — those widgets.
- New surfaces: Phase A.5 ticker info sub-card (the one genuine UI item in the original Phase C bundle).
- Removed: none.

**ADHD-FRIENDLY CHECK:**
- The `COMMITTEE_RULES` "CONNECTOR REQUIRED" block is good decisive UX — when the hub is unreachable it tells Nick exactly what to do, no analysis-paralysis. PASS.
- Analysis-paralysis risk on the **enrichment wrappers**: HIGH in the over-engineering sense. Nine wrappers no agent consumes is build surface that shows a recommendation to no one — the canonical "this widget is doing the work of three" anti-pattern, applied to backend tools. HELIOS backs the trim.
- If `hub_get_market_profile` / `chart_indicators` data lands in any dashboard widget, **staleness indicators are mandatory** (real-time data, could go stale outside RTH). Flag for the build brief.

**PERFORMANCE IMPACT:** Market-hours critical paths affected only if these tools render in the live dashboard. The audit frames them as committee-consumed, so impact is LOW — but confirm none of them get wired into a per-tick dashboard refresh (that would put UW calls on the hot path, compounding ATLAS's overdraw finding).

**FINDINGS:**
- Phase A.5 ticker sub-card is the only real UI deliverable and is **decoupled** from the three data tools once the shared `companies/{ticker}/profile` wrapper is dropped. Recommend splitting A.5 into its own UI brief rather than riding the data-tool bundle. SEVERITY: LOW (scope hygiene).
- Decision deferred-to-lane-owner precedent (2026-05-22) already set inline-expansion for A.5; preserve it.

**BACKEND DEPENDENCIES:** The MP tool's freshness contract depends on TradingView alert cadence → HELIOS's staleness indicator (if surfaced) must reflect "synthesized from Pine alert fire time," not wall-clock. Flag for ATLAS coordination.

**VETO:** None.
**CONVICTION:** MODERATE — minimal UI footprint; main HELIOS contribution is backing the enrichment-trim and requiring staleness indicators if any tool surfaces on the dashboard.

### ATHENA — PASS 1 (PM lens)
**BUILD:** Phase C bundle re-scope per audit + Nick's priority (chat headroom > hub options bloat).

**PRE-REVIEW PREREQUISITES:** PASS — `docs/build-backlog.md` read (stale as of 2026-05-22/24; reconciliation needed — see findings).

**VALIDATION CHECK:** Verified via the audit. The build solves a documented three-agent half-power gap; not speculative.

**PRIORITY SLOT:** This re-scopes the existing Tier-1 "Phase C bundle." It does **not** add net-new queue weight — it *shrinks* the bundle. Displaces nothing; frees runway.

**DISPLACEMENT WORTH IT?** YES — the re-scope removes already-shipped and non-consumed work from the bundle, which is pure runway recovery.

**BUCKET FIT:** Foundation (the three tools) + one tactical UI item (A.5). The original bundle mixed foundation + UI + an already-solved reliability fix — classic scope creep. Splitting is the fix.

**OLYMPUS IMPACT:** All three tools touch Olympus skills (DAEDALUS, PYTHAGORAS, PYTHIA). Each ships with a SKILL.md edit + `.skill` bundle rebuild + Nick re-upload, and **each requires a post-ship committee re-test** per the Olympus cross-reference rule (the 2026-05-21 TORO fabrication incident is the standing lesson). This is mandatory, not optional.

**SCOPE OBSERVATIONS:**
- **Strike OAuth state persistence from the bundle** — shipped + validated today via Brief D rev2 (`3d6dd94`). The backlog still lists it as open Tier-1 and lists a "rev3 investigation" track. Both are stale. Reconcile the backlog.
- **Drop the ~9 enrichment wrappers** from the bundle. Build per-endpoint only when an agent caveat or the (deferred) THALES module demands it.
- **Split A.5** into its own UI brief (HELIOS lane), now that it's decoupled from the dropped profile wrapper.
- The "urgent overhaul TBD (Nick, 2026-05-27)" has no authored brief — it cannot be sequenced until one exists.

**VETO:** None.
**RECOMMENDED VERDICT:** RESCOPE.
**CONVICTION:** HIGH — the audit makes the re-scope unusually clean.

---

## Part 3 — Titans Pass 2 (cross-review)

**ATLAS → others:** Agrees with AEGIS that D.2 is correct and that the MP webhook needs signature validation (also a data-integrity concern: unsigned ingestion can poison `market_profile_levels`). Agrees with ATHENA's strike of OAuth (Brief D rev2 confirmed in `origin/main`). Gap others may underweight: the overdraw is a *hard* sequencing gate, not a preference — `chart_indicators` and `market_profile` must wait on A.4b/A.4c headroom confirmation.

**AEGIS → others:** Agrees with ATLAS on caller-tag preservation as the deciding factor for D.2. Agrees with HELIOS that no enrichment wrapper introduces an exfiltration surface (market data only). Reiterates: the MP webhook signature is veto-conditional; the leaked PAT is override-accepted-and-logged, not dismissed.

**HELIOS → others:** Agrees with ATHENA on splitting A.5 and dropping the enrichment list (over-engineering lens aligns with the no-consumer finding). Confirms ATLAS's backend dependency on MP freshness contract. No disagreements.

**ATHENA → others:** No arbitration needed — no Titan disagrees with another; no vetoes in play (AEGIS's is conditional on the future MP brief, correctly deferred to that brief's final review). Validation flags: none raised. Scope now agreed across all four.

---

## Part 4 — ATHENA Overview (the answer)

**RECOMMENDED VERDICT:** RESCOPE the Phase C bundle into three tightly-scoped, sequenced builds; strike the already-shipped and non-consumed items.
**CONVICTION:** HIGH.

### What must STAY in the hub (load-bearing)
- **All 8 existing `hub_get_*` tools** — `quote`, `flow_radar`, `sector_strength`, `hermes_alerts`, `hydra_scores`, `positions`, `portfolio_balances`, `bias_composite`. The committee is hard-gated on these; TORO/URSA/THALES/PIVOT run at full power on them today. Non-negotiable.
- **The hub-wrapper architecture (D.2) itself**, because it preserves the A.4a caller-tagging that keeps UW spend attributable. This is what actually protects your "headroom."

### What must be FIXED / ADDED (the trade system needs these)
1. **`hub_get_options_chain` — ship now.** Already built; gate on the tightened RTH Greeks smoke; ~1h. Brings DAEDALUS to full power. Highest leverage per hour of any item here.
2. **UW overdraw → confirm headroom (A.4b/A.4c).** This is the *enabler* for everything below and the real meaning of "headroom" — the binding constraint is the 20K/day UW cap, not chat-side anything. Sequence before the next two tools.
3. **`hub_get_chart_indicators` — UW-wrap, batched.** ~6–8h. Brings PYTHAGORAS to full power. No TradingView needed (audit's key correction).
4. **`hub_get_market_profile` Phase 1 — TradingView pipeline.** ~12–20h, largest. Brings PYTHIA from blocked to functional. **Must include webhook signature validation** (AEGIS veto-conditional).

### What is LUXURY / CLUTTER (cut or defer)
- **The ~9 enrichment wrappers** in the original Phase C list (`spot-exposures`, `expiry-breakdown`, `volatility/term-structure`, `option-trades/flow-alerts`, `ownership`, `earnings-estimates`, `etf-tide`, `sector-tide`, `institution/ownership`). No agent's documented workflow consumes them; each adds UW load to an over-budget account. Build per-endpoint **only** when a specific agent caveat or the deferred THALES module requires it. This is the direct expression of your "headroom > hub bloat" priority.
- **OAuth state persistence in the bundle — STRIKE.** Shipped + validated today (Brief D rev2, `3d6dd94`). Dead work if re-attempted.
- **Phase A.5 ticker sub-card — SPLIT OUT** into its own UI brief (decoupled once the profile wrapper is dropped).

### Sequencing (what defers what)
`options_chain` (ship now) → A.4b/A.4c overdraw headroom → `chart_indicators` → `market_profile` P1. **Phase B (`get_bars`→UW) defers** until headroom is confirmed — migrating the last yfinance hot-path dependency onto a capped account during an overdraw is backwards.

### Olympus Impact (mandatory)
Three skills touched (DAEDALUS, PYTHAGORAS, PYTHIA). Each ship: SKILL.md caveat-closure edit + `.skill` rebuild + Nick re-upload + **post-ship committee re-test on a known-good ticker** (per cross-reference rule; 2026-05-21 TORO fabrication lesson). After all three land, run one full Olympus pass and confirm all three surface real data instead of qualitative-only language.

### Backlog reconciliation (ATHENA action)
`docs/build-backlog.md` is stale (last real update 2026-05-22/24): strike the OAuth Tier-1 item + rev3 track; replace the monolithic Phase C bundle with the three sequenced tools + the dropped-enrichment note; add the RH-MCP-backburner status (equities-only, no options trades). The 2026-05-27 "Top of queue restored / urgent overhaul TBD" entry needs a brief before it can be sequenced.

### Open questions for Nick
- **Q2 (smoke criterion):** confirm the options-chain Greeks smoke tightens to "5 ATM strikes both sides" before the RTH run.
- **Q6 (batch):** approve batch param on `chart_indicators` (recommended — fewer UW calls).
- **Q7 (Pine ownership):** CC drafts Pine, you review + paste? (audit recommends co-build.)
- **Q8 (webhook auth):** confirm shared-secret URL-token + HMAC for the TV webhook (AEGIS-required).
- **Q9 (TV alert quota):** confirm headroom against your TradingView alert cap before MP Phase 1.
- **"Urgent overhaul TBD":** does this still exist, and does it outrank shipping `options_chain`? If yes, it needs a brief.

---

*Advisory only. Titans review is infrastructure, not authority — Nick makes the final scope call. The formal Titans Final Review (workflow step 8) should re-run on the authored brief with full `PROJECT_RULES.md` + reference prereqs before CC executes.*
