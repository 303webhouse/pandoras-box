# MASTER BRIEF — Edge Consolidation + UW Options Integration

**Date:** 2026-06-05 · **Rev 2** (incorporates Titans review 2026-06-05: ATLAS / AEGIS / HELIOS / ATHENA)
**Origin:** Full signal-edge audit (this session) — Railway Postgres `signals` table, 11,091 real equity signals graded on 1-day forward return + SPY alpha, validated through Olympus (4 committee passes) and Titans (1 review pass).
**North star:** ONE repeatable edge. Discard what's clearly not working, sharpen what is.
**For:** CC (Claude Code). Split into sub-briefs if useful; suggested split in §9.

**Titans verdict (ATHENA):** PROCEED — conditional on the Rev-2 revisions now incorporated below. Build scope unchanged from Rev 1; this revision adds the Olympus Impact section, security requirements, a blocking Postgres gate, outcome_source discipline, committee-review logging, and a named frontend dependency.

---

## 0. RULES OF ENGAGEMENT (read first)

- **Investigation-first.** Every workstream begins with a Phase 0 read-only investigation. Report findings and STOP at the gate before any code change.
- **Shadow by default.** Every new signal/strategy/regime-gate enters SHADOW — logged and scored, NOT surfaced to Insights and NOT traded — until it clears the §8 validation gates.
- **No production writes/deploys without Nick's explicit greenlight** through the chat. No `--apply`, no signal suppression/retirement in prod, no schema migration, no Railway deploy without sign-off.
- **Committed ≠ deployed.** After any push, verify the live endpoint before claiming done.
- **Sync hygiene.** `git fetch && git status` on `C:\trading-hub` before starting. Do not build on a stale clone.
- **Respect the UW budget.** 120 req/min, 20K/day, existing circuit breaker in `backend/integrations/uw_api.py`. No new standing UW load without checking headroom. All bar/OHLC + chain reads use the **Railway UW key** (the local key 403s on OHLC — never fall back to yfinance in a hot path; see §5/ATLAS).
- **★ BLOCKING PRE-FLIGHT — Postgres headroom.** Volume was last seen ~94% (470/500 MB). No `CREATE TABLE` (B2 outcomes, C1 institutional-flow, any feed table) until headroom is remediated. **Approved remediation:** drop the deprecated `positions`, `open_positions`, `options_positions` tables. Because `DROP TABLE` is irreversible, this is a destructive op requiring its own gate:
  1. Grep the codebase + confirm zero reads/writes against all three tables.
  2. Export each to a backup dump (this is the rollback path) before dropping.
  3. Nick greenlight.
  4. Drop, then re-measure headroom.
- **Pipeline:** Titans pass complete (this rev). Next: commit → CC launched from repo root.

---

## 1. VALIDATED FINDINGS (the WHY — do not re-litigate)

1. **Standalone signals ≈ coin flips after stripping market beta.** Across 11,091 signals, beta-stripped alpha ran −0.08% to +0.16%.
2. **Edge concentrates in the high-SCORE band, ACROSS strategies — keep/discard is score-conditioned, not strategy-conditioned.** CTA score_v2 60–80 = 59% hit / +0.25% alpha; 0–60 bleeds −0.3% to −0.9%. Cross-strategy alpha climbs ≥70 (−0.05%) → ≥80 (+0.06%) → ≥90 (+0.17%).
3. **Score/confluence is strategy-family-aware:** helps continuation (CTA, footprint-breakout), INVERTS for reversion (Artemis ≥80 = −0.52% alpha). No blind global high-score filter.
4. **The one edge:** responsive entries at **structural extremes, expressed convexly, regime-gated.** Flagship: **sell_the_rip ≥80 = 71% hit** (MFE +2.34% / MAE −0.51%).
5. **Holy_Grail is dead** by two methods. Its ≥80 slice (n=44) is ~1% of the strategy.
6. **Footprint = confluence INPUT, not standalone.** Momentum signal (above-VAH 59% / below-VAL 28%), not reversion.
7. Everything must be measured in **OPTIONS P&L, not underlying %**, and gated by **REGIME**.

**Caveats CC must carry:** one regime (Feb–Jun 2026 up-tape); all grading was daily-close on the underlying (yfinance proxy), NOT options P&L; thin high-score sub-samples; non-monotonic score curve (80–90 dip). The *existence* of a high-score edge is solid; no specific threshold is locked.

---

## 2. OLYMPUS IMPACT (required — cross-reference rule)

This build touches multiple Olympus skills and the data the committee pulls. Per the Olympus cross-reference rule, the touched skills, behavior changes, and re-test are named here.

**Skills touched + behavior change:**
- **PYTHIA** — gains a live committee feed via B4 (`hub_get_market_profile`). Behavior change: PYTHIA's MP levels become real-time instead of absent.
- **THALES + PIVOT** — B1 GEX regime gate feeds the regime/bias lane. Behavior change: regime read becomes mechanical (GEX-derived) rather than narrative; PIVOT synthesis can condition on regime.
- **DAEDALUS** — B2/B3 surface the live UW chain + greeks + flow. Behavior change: DAEDALUS structure recs and the options-P&L grade run on live UW marks.
- **Whole committee (Insights feed)** — A1 demotion changes what populates the Insights feed the committee reviews. Behavior change: feed density drops; low-score bulk no longer surfaces.

**Mandatory post-build re-test (non-negotiable):** before anything goes live, run **one full Olympus committee pass on a known-good ticker** to confirm no agent-behavior regression. The 2026-05-21 TORO fabrication incident is the precedent — committee behavior degrades silently when upstream data assumptions shift. Closure note records the pass.

---

## 3. SECURITY REQUIREMENTS (AEGIS)

No broker/trading credentials are in scope — this build is read-only on market data + internal scoring. No order path. (The moment any of this connects to a broker for execution, AEGIS's pre-production override expires and a full security review is mandatory.) Requirements:

- **Webhook HMAC (B4).** The PYTHIA MP feed runs through a TradingView webhook (`/webhook/pythia`, `/webhook/mp_levels`). Any webhook ingesting external data MUST validate an HMAC signature. Confirm existing TV webhooks validate; any new endpoint MUST validate before shipping. (Absence = AEGIS veto.)
- **Log scrubbing (C1 + all new UW calls).** UW error responses carry the auth header. NO raw UW response objects in any log line — scrub headers before logging.
- **MCP exfiltration boundary (B1/B4).** New tools `hub_get_regime` and `hub_get_market_profile` must be read-only, behind the existing bearer auth, and must surface nothing beyond documented boundaries (no position/account/credential bleed).
- **Audit logging.** New external ingestion (C1) + new MCP tools fall under the existing `/var/log/committee_audit.log` pattern. Confirm coverage; flag gaps.
- **Override log.** The increased UW-API usage is a pre-production override-accepted finding (data-API credential, pre-production phase). Record it in `skills/aegis/references/pre-production-override-log.md` at build time — acknowledgment, not dismissal; it enters the comprehensive-security-review backlog.

---

## 4. WORKSTREAM A — Score-conditioned keep/discard (cleanup)

**A0 (investigation, hard stop):** Map current signal routing — how `strategy`, `score_v2`, `feed_tier`, `feed_tier_v2`, `confluence_tier`, `signal_category` decide what surfaces to Insights (`hub_get_trade_ideas`) vs research_log. Document where each strategy is gated. Report + STOP.

**A1 — Demote, don't delete.** Holy_Grail → all to shadow/research_log (retain rows). CTA → keep high-score core, route low-score bulk to shadow. Keep: CTA high-score, Artemis (confluence-gated reversion), sell_the_rip, footprint (as INPUT). Confirm this is a `feed_tier`/routing change, not a row operation. **Greenlight gate before any prod suppression.**

**A2 — Reclassify footprint + whale/footprint as confluence INPUTS**, not standalone signals (feed the score, don't surface alone).

**A3 — Outcome self-scoring.** Wire the resolver to populate forward-return AND options-P&L outcomes going forward (options P&L depends on B2). **Data-integrity invariant (ATLAS):** these write a NEW `outcome_source` enum value (e.g. `FWD_RETURN`, `OPTIONS_PNL`). They must NOT overwrite `ACTUAL_TRADE` (live perf) or pollute `signal_outcomes` BAR_WALK. Canonical walker stays clean.

**A4 — Committee-review logging** (folded in here per ATHENA — shares A3's outcome-attribution plumbing). Persist every Olympus committee pass (ticker, ts, spot, each agent's read, PIVOT synthesis, conviction, entry/stop/target/invalidation) with `outcome_source='COMMITTEE_REVIEW'`. At n≥250: PIVOT calibration, per-agent edge, B.06 hit rate, regime conditioning. Requires the hub MCP v2 write-gate OR a direct `/api/committee/log` endpoint.

---

## 5. WORKSTREAM B — UW options integration (HIGHEST LEVERAGE — everything depends on it)

**B0 (investigation, hard stop):** Validate UW endpoint behavior, response shapes, rate-limit headroom, cache TTLs for `get_greek_exposure`, `get_options_snapshot`, `get_flow_per_expiry`, `get_darkpool_ticker`, `get_iv_rank`, `get_max_pain`, `get_market_tide`. Confirm BS-greeks path (`hub_get_options_chain`, schema v2.0) usable for marking. Report + STOP.

**B1 — GEX REGIME GATE (top priority).** Build a regime classifier from UW net GEX: **+GEX = vol-suppressed / mean-reverting / pinned → FADE book** (sell_the_rip, condors to the pin); **−GEX = vol-amplified / trending → MOMENTUM/convexity book** (breakouts, cheap OTM). The regime switch sits ABOVE all signal routing. Thresholds data-driven in investigation (pull historical GEX, classify, validate against realized vol + the observed fade-vs-momentum split). Expose as a hub field + MCP read (`hub_get_regime`). **Staleness contract (ATLAS):** GEX is timestamped — a stale read during market hours must degrade like `hub_get_quote` (`live`/`stale`/`unavailable`); never let a 40-min-old regime drive routing silently. Bars pulled from **UW Railway key**, not yfinance.

**B2 — OPTIONS-P&L MEASUREMENT LAYER.** Use UW live chain + greeks to grade signals/strategies in OPTIONS terms. Define a standardized options expression per bucket with DAEDALUS rules (B2 ~30-delta debit; B3 0DTE/near-dated; defined-risk where appropriate; ≤21 DTE close at 60–70% of max). Mark to UW. Unblocks the §8 gates.

**B3 — LIVE UW flow/GEX/darkpool as confluence.** Replace the stale DB flow snapshot (frozen in `triggering_factors`) with real-time UW reads in the scorer; fold into `score_v2`. Inputs: `get_flow_per_expiry`, `get_darkpool_ticker`, `get_greek_exposure`, `get_iv_rank`.

**B4 — PYTHIA MP feed.** Ship `hub_get_market_profile` (TV market-profile webhook). Needed to (a) give PYTHIA a live committee feed and (b) decompose the score into structural-location vs noise (explains the 80–90 dip). **HMAC-validated webhook (AEGIS) — see §3.**

---

## 6. WORKSTREAM C — New strategy shadows (each enters SHADOW, gated)

**C1 — Institutional-flow following ("the real whale").** Repeat aggressive sweeps + dark-pool accumulation + OI confirmation → directional convex swing. Closes the original whale-capture gap — build on the UW API, NOT the broken Discord-scrape path. Persist parsed events to a new table (gated on the §0 headroom pre-flight) with UW enrichment + forward + options-P&L outcome fields (distinct `outcome_source`, per A3). Table needs a migration with explicit rollback. **Log-scrubbing required (AEGIS) — see §3.**

**C2 — 0DTE GEX-gated scalps.** B3 VA-break/rejection trigger + GEX sign (B1: run vs fade) + max-pain magnet. MUST respect existing B3 caps: $100/scalp until cash infusion, max 2 concurrent / 3 per day, same-day close, 2-loss circuit breaker, $300 daily max loss.

**C3 — Vol-regime structure selection (overlay).** IV-rank-conditioned: high IVR → sell premium (defined-risk condors/spreads) around the GEX pin; low IVR → buy convexity (debit spreads / 0DTE). Not a new signal — a structure overlay.

**All C: SHADOW only** — logged + scored, not surfaced, not traded, until §8 gates clear.

---

## 7. FRONTEND FOLLOW-ON (HELIOS — tracked dependency)

Not in this brief's build scope, but named so it is not lost. Two B-workstream outputs are operationally user-facing and create hidden state until surfaced:

- **Regime badge (depends on B1).** The +GEX/−GEX regime that flips the fade/momentum book MUST be visible on the dashboard with a freshness stamp (e.g. "−GEX · MOMENTUM · 2m ago"). A regime living only in backend routing is the hidden-state anti-pattern.
- **Insights feed quiet/empty state (depends on A1).** Demotion thins the feed — the surface must show decisive ranked recs and handle the quiet state gracefully (not a blank panel that reads as broken).
- Wherever live-flow-driven score (B3) or MP levels (B4) surface, staleness must show without a click.

Correct order: backend field (B1/B4) ships first, then the Agora surface. To be scoped as a follow-on HELIOS brief after B1/B4 land.

---

## 8. VALIDATION GATES (apply to: A1/A3 thresholds, B1 regime cuts, all of C)

Nothing goes live / no threshold locked / no signal surfaced until:
1. **Options-P&L** (via B2), not underlying %.
2. **Out-of-sample / walk-forward.**
3. **Across ≥1 non-up-tape regime** (use the B1 GEX classifier to bucket history).
4. **Regime gate (B1) wired above signal routing.**

**No live capital and no production surfacing without Nick's explicit greenlight per item.** No threshold is locked and no strategy is killed in prod until B2 makes P&L measurable and the OOS/regime gates clear (non-arbitrable, per ATHENA).

Open questions CC resolves in investigation (data-driven, do not assume): GEX thresholds for regime classification; the standardized options expression per bucket; the score keep/discard threshold (60–80 vs ≥80; the 80–90 dip) — settle in options-P&L.

---

## 9. SEQUENCING (CC may split into sub-briefs)

0. **Postgres headroom remediation** (drop deprecated tables, backup-first, destructive-op gate per §0) — **blocking pre-flight.**
1. **B1 + B2** (GEX regime gate + options-P&L layer) — everything depends on these. *(Sub-brief 1.)*
2. **B3 + B4 + A3 + A4** (live confluence, MP feed, outcome scoring, committee-review logging — shared outcome-attribution plumbing) — then re-grade on the new measurement. *(Sub-brief 2.)*
3. **A0 / A1 / A2** cleanup — once the high-score keep-set is validated in options-P&L. *(Sub-brief 3.)*
4. **C1 / C2 / C3** shadows — in parallel, promoted only on gate-clear. *(Sub-brief 4.)*
5. **Frontend follow-on** (regime/MP Agora surface, HELIOS) — separate brief, after B1/B4 backend lands.
6. **Post-build:** mandatory full Olympus committee pass on a known-good ticker (§2) before go-live.

---

## 10. OUT OF SCOPE / DEFERRED

- **Crypto Scanner** — separate pass (different ticker format, 24/7 bars, BTC benchmark not SPY).
- **Discord whale-scrape path** — superseded by C1 (UW API). The `uw_watcher` Redis-only path stays for live committee context but is not the capture mechanism.
- Holy_Grail revival — not unless its top-slice clears gates on its own.

---

*End of master brief (Rev 2). All performance numbers herein are 1-day-forward, underlying %, one-regime — directional evidence, not locked thresholds. The options-P&L layer (B2) is the prerequisite for converting any of this into live decisions.*
