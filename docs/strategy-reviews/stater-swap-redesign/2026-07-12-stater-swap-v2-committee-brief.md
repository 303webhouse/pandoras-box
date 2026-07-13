# Stater Swap v2 — Olympus Double-Pass Review & Titans Handoff Brief

**Date:** 2026-07-12 (Sunday) | **Lane:** Coordination (Fable) | **Status:** DRAFT — awaiting Nick ACK before Titans convene
**Seats:** TORO, URSA, PYTHIA, PYTHAGORAS, DAEDALUS, THALES, PIVOT + two guest seats: **MIDAS** (crypto derivatives & flows specialist) and **OCEANUS** (30-year FX/commodities veteran)
**Target file location after approval:** `docs/strategy-reviews/stater-swap-redesign/2026-07-12-stater-swap-v2-committee-brief.md`

---

## DATA NOTE (read first)

- **MCP: connected** (schema v2.0, server time 2026-07-13T02:43Z).
- **`hub_get_quote("BTC")` returned $28.33 with `status="live"` — that is the NYSE-listed ETF ticker "BTC," NOT Bitcoin.** The hub currently has **no crypto-native quote path**, and worse, it resolves crypto symbols to same-named equities silently. This is a confidently-wrong-asset failure in the fake-healthy class and is treated as a P0 requirement below (F-3).
- **Ground truth (web fallback for crypto leg, per Context B rules):** BTC ≈ **$64,100** (blockchain.com $64,145; Coinbase "near $64,000," sourced 2026-07-12); ETH ≈ **$1,800–1,820** (CoinMarketCap $1,802.62, crypto.com $1,805.39, blockchain.com $1,819.76 — data dates 2026-07-11/12). BTC dominance ~56.2%. Regime color: ETH ETFs +$1.6B inflows last week vs BTC ETF outflows ~$175M — active ETH-rotation tape; a July 7 analyst warning flagged unliquidated-long dominance across majors. All numbers are context for this audit, not trade anchors.
- **Conviction on this review: MEDIUM-HIGH.** Not capped by any two-flag rule; held below HIGH because two Phase-0 facts are unverified (vendor client health, outcome-tracking parity — see F-1/F-2).

---

## PART 1 — CURRENT STATE AUDIT (Phase-0 recon, repo-verified)

**What Stater Swap is today** (per `docs/reference/subsystems.md`, `DEVELOPMENT_STATUS.md`, briefs 2A–2E):

1. **BTC Setup Engine** — `backend/strategies/crypto_setups.py`. Three strategies run every 5 min, 24/7: **Funding Rate Fade**, **Session Sweep**, **Liquidation Flush**. Breakout Prop sizing (1% max risk).
2. **Market Structure Filter** — `backend/strategies/btc_market_structure.py`. Volume profile (POC/VAH/VAL) + **CVD gate** + orderbook imbalance, modifying signal scores −45 to +35. CVD exists today as a hidden score input, not a user-facing surface.
3. **Bitcoin Bottom Signals** — `backend/bias_filters/btc_bottom_signals.py` + `backend/api/btc_signals.py`. **9 automated derivative signals** fed by Coinalyze (funding, OI, liquidations, term structure), Deribit (25-delta skew), DeFiLlama (stablecoin APRs), Binance (orderbook, quarterly basis), yfinance (VIX). Manual-override support. Source doc: The Stable's "BTC Derivative Bottom-Signals Checklist" (in `docs/the-stable/`).
4. **Session windows** — already coded (`/btc/sessions`): Asia Handoff, London Open, Peak Volume, ETF Fixing, Friday CME Close. Currently metadata, not a strategy gate or UI element.
5. **TradingView crypto** — Holy Grail + Exhaustion PineScript on `BTCUSDT.P` via `/webhook/tradingview`.
6. **Discord delivery** — crypto embeds, Take/Pass/Watching, no committee (too slow for scalps).
7. **STRC Circuit Breaker** — `backend/circuit_breakers/strc_monitor.py`: warns when Strategy's preferred (STRC) trades below $100 par → structural BTC bid impaired. Source: `docs/the-stable/microstrategy_policy_analysis.html`.
8. **UI** — Stater Swap is a mode tab in the **legacy** frontend (`frontend/index.html`). The hub has since flipped to `/app/v2`; Stater has not been ported.

**Known defects and gaps (verified):**

- **L0 governance bypass:** crypto signals write via `bias_scheduler.log_signal`, not `process_signal_unified` — they skirt the signal-governance layer that every equity signal obeys. Open fix item.
- **Wrong-asset trap:** `hub_get_quote("BTC")` → NYSE ETF at $28.33, status "live" (verified live this session). No crypto quote/bars exposure on the hub MCP; the PYTHIA crypto stub notes BTC/ETH MP data is "strategy-internal only."
- **`session_sweep` has a known-red scanner test** (one of the 3 standing scanner failures in the known-red baseline).
- **Vendor sprawl predates the data hierarchy:** Coinalyze, Deribit, Binance, DeFiLlama, yfinance were wired before the April 2026 UW-primary ruling. None are formally sanctioned; Binance public API famously geo-restricts US-region IPs — Railway region compliance is **unverified**.
- **Outcome-tracking parity unknown:** whether `asset_class=CRYPTO` signals land in `signal_outcomes` with the Phase A/B/C machinery is unverified. If they don't, no crypto strategy can ever clear a promotion gate.
- **Drogen momentum framework note (2026-05-22 session) was never committed** — `docs/strategy-reviews/stater-swap-redesign/drogen-momentum-framework.md` 404s. Contents recovered from the session record (Module A: BTC 50-DMA regime filter; Module B: cross-sectional momentum, long top 20% / short bottom 20% by 30-day return; Module C: broken parabolic short — already handled at prompt level). Recovery item.
- **Crypto playbook stubs:** all seven Olympus `references/crypto.md` files are deliberate stubs awaiting this rebuild. `PROJECT_RULES.md` bars authoring crypto methodology "from general pretrained priors" — every recommendation below is therefore grounded in (a) repo-verified system state, (b) The Stable library, (c) live-data validation gates. Anything not yet evidenced ships **shadow-first**.

**The Stable inputs used by this pass** (`docs/the-stable/`): BTC Derivative Bottom-Signals Checklist (source of feature #3), Crypto Scalping Considerations, Flow Trading Crypto, Crypto ETF Flow Structure, `spot_flows_futures_impact.html` ("spot leads, perps follow" — spot is price discovery; perp indices weight to spot venues; execution style matters as much as size; weekend/holiday liquidity amplifies impact), `comprehensive_btc_levels_guide.html`, Bitcoin Intraday Cheat Sheet, Market Microstructure & Time-of-Day Analysis, `microstrategy_policy_analysis.html`, Price_Insensitive_Flows_Guide, risk_premia_alpha_guide (per the June L1 recon: this library is education/philosophy, **not** a spec repository — specs get authored and validated, not lifted).

---

## PART 2 — PASS 1: INDEPENDENT SEAT READS

### PYTHAGORAS (trend, structure, technicals)

Crypto is the most purely technical major asset Nick trades — no earnings, no analyst tape, price memory and momentum dominate. Portability read on the equity stack: **structural-trigger and trend classes port well; mean-reversion classes port worst.** Specifics: ARTEMIS-style AVWAP/structure entries, Holy Grail MA-pullback (already live on BTCUSDT.P), Exhaustion, and the approved WRR buy model (its own doc already names BTC via Stater Swap as an application) are all portable **with recalibration**: the intraday frame shifts from 5m/15m to 1h/4h (per the existing crypto stub), and every ATR/threshold parameter must be re-fit to crypto volatility — BTC's daily range is a different animal. The single highest-value, lowest-cost build is the **BTC regime gate**: Drogen Module A (50-DMA) upgraded with ADX and DMA slope, mirroring the shipped equity regime classifier — long-side scalps only in TREND-UP, sweeps/fades in CHOP, reduced or short-only in TREND-DOWN. Everything else in this brief is downstream of knowing the regime. Level framework should be authored from `comprehensive_btc_levels_guide.html`, not priors.

### PYTHIA (auction theory, market profile, CVD custody)

Two verdicts. **First, the MP framework adaptation:** 24/7 markets need session-based profiles (Asia 00:00–08:00 UTC, London 08:00–16:00, NY 16:00–24:00) plus rolling 24h composites — the framework in my stub is right; what's missing is data plumbing. The Market Structure Filter already computes BTC volume profile internally; **expose it** (hub MCP + UI) so committee passes and the dashboard read the same levels. **Second — the CVD question Nick asked directly:** a raw cumulative CVD line is tracking data, and staring at it is how retail loses hours. CVD earns its place only as **events at levels**. Concretely: (a) **Divergence events** — price makes a new session/day extreme, CVD does not confirm → exhaustion candidate, only meaningful at a profile edge (VAH/VAL, session high/low, prior POC); (b) **Absorption events** — heavy one-sided delta into a level with price refusing to move → passive player defending; that's a structural trigger, the same class B3 scalps already require; (c) a persistent **tape-health state chip**, not a chart. Mid-range CVD wiggle is noise and should never alert. This converts CVD from a chart Nick watches into signals that come to him — exactly the hub v2 actionable-alpha doctrine.

### DAEDALUS (structure, Greeks → perp risk math)

No listed options in Nick's crypto accounts, so my lane translates: **funding is the theta of perps** — a held perp position pays or earns carry every interval, and that carry must be first-class in every signal card (est. funding cost over intended hold). **Liquidation distance is the new max-loss math:** any contemplated size should render liquidation-distance-in-ATRs; if the liquidation price sits inside ~2 ATR of entry, the size is wrong regardless of conviction. On the **Breakout Prop trailing drawdown floor**: distance-to-floor is existential (losing the eval = losing the account) and belongs on the UI as a hard chip, with size suggestions computed off distance-to-floor, not off nominal balance. One genuinely new hypothesis from the equity lane: **RSI-2 mean reversion failed Stage 2 on equities specifically because the options expression died of IV crush (net-long vega problem). Perps are linear — no vega.** The failed factor deserves a crypto re-test on perp expression, regime-gated to CHOP, shadow-only, standard n-gates. That's a rare case where the *expression*, not the edge, was the killer.

### TORO (bull lane)

The bull case for this rebuild: crypto is *the* momentum asset, and momentum is the one factor family that has repeatedly cleared bars in this asset class — strength begets strength through liquidation fuel and reflexive flows. The long playbook should chase **confirmed** strength at structure (HH/HL, Donchian-class breakouts, sweep-and-reclaim longs), never knife-catch. The institutional tape now has a legible proxy the equity side would kill for: **spot ETF creations/redemptions** — price-insensitive structural flow, per The Stable's Crypto ETF Flow Structure + Price-Insensitive Flows guides — and it's **on-stack** via UW's ETF endpoints. Today's tape proves the point: ETH funds +$1.6B while BTC funds bled — an ETH-rotation regime the current BTC-only build is blind to. Minimum viable fix: a **dominance / ETH-BTC regime strip** and ETH as a first-class second symbol. Also: the Bottom Signals panel firing into a recovery like the current one is exactly when B1 crypto adds get sized — keep it, upgrade it, surface it.

### URSA (risk, bias challenge)

Five flags, in priority order. **(1) Prior-fabrication risk:** the temptation in a crypto rebuild is to ship "known" crypto wisdom. PROJECT_RULES forbids it; the mitigation is structural — every new signal enters shadow with the same n-gates as equities, which requires fixing outcome-tracking parity *first*, or nothing can ever graduate. **(2) Fake-healthy, again:** the wrong-asset quote trap is live *today*; the bottom-signals cache can serve stale FIRING states; every crypto surface must carry the house labeling contract (`as_of`, `data_age_seconds`, `degraded`) with a distinct DEAD state. A bottom panel that quietly froze during the one week it mattered is worse than no panel. **(3) Vendor risk:** four unsanctioned dependencies; Binance geo-restriction vs Railway US region is an unverified single point of failure under two strategies (orderbook, basis). Verify, sanction or replace, and give each client the flatline-detection treatment. **(4) Nick-specific risk:** a 24/7 momentum market pointed at a trader with documented patterns of same-direction stacking, emotional sizing, and revenge re-entry — this is the highest-leverage risk in the whole project. The discipline layer (daily loss cap, max concurrent, post-2-loss cooldown, distance-to-floor) must be **rendered state, enforced in UI**, not prose in a doc. Weekend/holiday size reduction should be a default, not a suggestion (The Stable's own microstructure doc: thin books amplify the same size). **(5) Correlation illusion:** in risk-off, everything crypto is one BTC-beta trade, and it clusters with Nick's equity risk-on book. Portfolio coherence checks must treat crypto as a single risk cluster cross-checked against equity exposure.

### THALES (fires: concentrated narrative + macro catalyst + crowded trade — all three triggers hit)

A no-cash-flow asset doesn't get a discounted-cash-flow opinion from me, and I won't fake one. My framework translates: NARRATIVE / QUALITY / VALUATION becomes **NARRATIVE / ADOPTION / FLOWS**. The honest read: bitcoin doesn't have earnings; it has believers and plumbing — so track the plumbing. Plumbing = ETF flows (structural, price-insensitive), stablecoin supply growth (the DeFiLlama client already exists — repurpose it from APY-only to supply trend), and treasury-company mechanics (the STRC breaker is exactly this — keep it, it's one of the smartest things in the current build). Macro overlay: crypto is long-duration dollar-liquidity beta — DXY trend and real yields belong on the dashboard **as B1 context only**. The Horse Rule stands and should be enforced in the layout itself: macro strip lives in the top context band, structurally separated from the scalp feed, and never feeds a B3 signal score.

### MIDAS (guest seat — crypto derivatives & flows specialist)

The three incumbent strategies are the *correct three classes* — funding extremes, session liquidity raids, liquidation cascades are where repeatable crypto edge lives. The upgrade path is precision, not replacement: funding should be read as **trend + extreme, aggregated cross-exchange** (a +0.05% print means nothing; three rising intervals into a resistance test means a lot); Liquidation Flush needs a "**no second-flush catch**" rule — first cascade fades are fadeable, re-flush within the same impulse is trend continuation, demand a structural reclaim before entry. What's missing from the dashboard, ranked by signal-per-build-cost: **(1) OI × price divergence state** — rising price + rising OI = new money (durable); rising price + falling OI = short-covering (fragile); falling price + rising OI = aggressive shorts (squeeze fuel). Four states, one chip, enormous context. **(2) ETF flow tracker** — daily net creations for the major BTC/ETH funds; it's the institutional tape and it's already on-stack via UW. **(3) Perp basis** (Binance client computes it — surface it). **(4) Dominance + ETH/BTC strip** as the alt-regime gate before any alt ambitions. On **Bottom Signals**: derivative-positioning capitulation is the *right* design — no halving astrology, no paid on-chain vendor needed — but it's half a tool. The same clients already compute the froth side (basis >10% annualized = overleveraged longs; extreme call skew; funding blowouts). **Mirror it into a two-sided "Cycle Extremes" panel — CAPITULATION column and FROTH column** — and add a 10th signal: sustained ETF-outflow exhaustion. Finally, 24/7 ops reality: alert fatigue kills scalpers; keep 2E's score decay, add session-aware thresholds (raise the bar during Asia chop).

### OCEANUS (guest seat — FX/commodities veteran)

Currencies taught me everything this asset needs, because FX is also a no-earnings, flow-and-positioning market. Six transfers, one warning. **(1) The session IS the regime.** Tokyo builds the range, London breaks it (often falsely), New York resolves it — crypto inherits this rhythm plus an ETF-fixing window FX never had. Your sessions endpoint already encodes the windows; **elevate it from metadata to a first-class session clock and per-strategy gates** — Session Sweep should hunt at session opens and extremes, not at 3 a.m. Denver time in the middle of the Asia range. **(2) Positioning is the fundamental.** In FX we squinted at weekly COT reports; funding + OI is a real-time COT, better than anything I had. Funding Rate Fade is classic carry-crowding logic — right instinct; trade the *change* in positioning, not the level alone. **(3) Stop-hunts are a business model.** FX dealers ran stops at round figures and session extremes; crypto is worse/better — the liquidation map is effectively public. Sweep-and-reclaim is the most portable FX setup class; fix session_sweep's red test and make it session-gated. **(4) Trade the reaction, not the news.** Scheduled macro (CPI, FOMC) whipsaws crypto exactly like EURUSD; the calendar belongs on the dashboard with a "no fresh entries N minutes pre-print" rule. **(5) The dollar rules everything around me.** Crypto is an anti-dollar expression; DXY and real yields are your B1 weather report — context band only, per the Horse Rule. **(6) Ranging honesty:** currencies spend most of their life ranging and pay in violent bursts; a regime classifier ahead of strategy selection is the single most valuable decision layer — I co-sign PYTHAGORAS's gate as build #1. **The warning:** I watched EURCHF in 2015 teach a generation that liquidity is a courtesy, not a right. Crypto has no circuit breakers, no central bank, and thin weekend books. Size for the gap, not the stop — especially on a prop account where the drawdown floor is a trapdoor.

---

## PART 3 — PASS 2: CROSS-EXAMINATION (challenges & resolutions)

1. **URSA challenges MIDAS** on adding surfaces (OI chip, basis, ETF flows, Cycle Extremes) as scope creep atop four unsanctioned vendors. **Resolution:** every Pass-1 surface maps to an *existing* client (Coinalyze OI, Binance basis, Deribit skew, DeFiLlama supply, UW ETF) — zero new vendors, zero new spend. Sequencing: vendors get verified/sanctioned in Phase 0 before any surface builds on them. Adopted as F-1.
2. **OCEANUS challenges TORO** on momentum-chasing: FX history says most breakouts fail in range regimes. **Resolution:** unified — momentum entries are regime-gated (TREND states only); sweep/fade entries own CHOP. The regime gate is the arbiter, which is why it's R-1.
3. **PYTHAGORAS challenges DAEDALUS** on the RSI-2 perp re-test: the factor failed Stage 1 sibling tests too; is this zombie-reviving? **Resolution:** narrow scope — RSI-2 specifically failed on *expression* (IV crush), which perps eliminate; it re-enters only as an L1b-style pipeline hypothesis, CHOP-gated, shadow-only, standard n≥ gates, lowest priority in R-3. If Stage-1 economics fail on crypto data, it dies quietly.
4. **PYTHIA challenges the CVD keep-request as stated:** "live CVD tracking" as a chart is exactly the tracking-data pattern hub v2 rejects. **Resolution (and answer to Nick's question):** CVD survives as (a) one tape-health chip with **spot-vs-perp split** — spot-led moves are real, perp-led moves are leveraged air, per The Stable's spot-flows doc — and (b) a divergence/absorption **event feed anchored to profile levels**. No standalone CVD chart on the default view. Unanimous.
5. **THALES challenges MIDAS** on Cycle Extremes' froth side: won't a FROTH column trigger Nick's documented early-winner-cutting? **Resolution:** FROTH is labeled a *sizing/hedging dial* (B1 context), never a short signal generator; URSA adds it to the bias-challenge checklist — a froth reading plus an open long prompts trim-review, not reflexive exit. UI copy must say "reduce new risk," not "sell."
6. **URSA challenges OCEANUS** on macro strips (DXY, yields, calendar) violating the Horse Rule for a scalping UI. **Resolution:** layout-level enforcement — macro lives in a collapsed context band, feeds zero scalp scores, and the pre-print entry freeze is a *risk* rule (timing), not a directional input. Horse Rule intact.
7. **DAEDALUS challenges the incumbent Funding Rate Fade** on carry asymmetry: fading extreme positive funding *earns* carry while short (good); fading extreme negative funding *pays* carry while long — the two directions aren't symmetric trades. **Resolution:** signal cards must show est. funding P&L over intended hold; the negative-funding fade requires a stronger structural trigger. MIDAS co-signs.
8. **PIVOT challenges everyone** on build volume: nine seats produced ~20 wants; Nick's execution bandwidth is the binding constraint and idea-generation-outpacing-execution is his documented pattern. **Resolution:** the R-stack below is strictly ordered, foundation-first; R-4/R-5 are explicitly forbidden to start before R-0 ships. ATHENA owns enforcement.

---

## PART 4 — PIVOT SYNTHESIS

Here's the call, no hedging. The current Stater Swap got the *classes* right — funding, sweeps, flushes, derivative bottom signals — and got the *plumbing* wrong: it predates the data hierarchy, skips governance, tracks nothing, resolves the wrong asset when you ask the hub what Bitcoin costs, and lives on a UI the rest of the system already abandoned. So this is not a strategy rebuild first. **It's a foundation rebuild that unlocks a strategy validation program.** The good news: almost everything the nine seats want runs on clients you already pay for or already wrote. The edge thesis is coherent across all seats and The Stable library: **crypto is a positioning-and-flows market wearing a technical costume — regime first, session second, positioning third, then and only then a trade.** Verdict on proceeding: **GO**, in the order below, with shadow-first discipline on anything that scores a signal.

### Recommendation stack (hand to Titans in this order)

**R-0 — FOUNDATION (no UI, blocks everything):**
- **F-1** Vendor verification & sanction: live-test Coinalyze/Deribit/Binance/DeFiLlama clients from Railway (Binance geo-check explicitly); formally sanction survivors in the data-hierarchy doc; wire each into flatline detection with honest DEAD states.
- **F-2** Outcome-tracking parity: confirm/route `asset_class=CRYPTO` signals into `signal_outcomes` with BAR_WALK grading (crypto bars source required — see F-3). Without this, no promotion gate can ever pass.
- **F-3** Crypto data path on the hub: `hub_get_crypto_quote` / crypto bars (UW crypto endpoints primary where coverage exists; sanctioned vendors otherwise) **plus an asset-class guard on `hub_get_quote`** so "BTC"/"ETH" either route correctly or return an explicit disambiguation error — never the ETF silently.
- **F-4** L0 enforcement: route crypto signals through `process_signal_unified`; retire the `bias_scheduler.log_signal` side door.
- **F-5** Hygiene: commit the recovered Drogen framework note; fix session_sweep's known-red test.

**R-1 — REGIME & SESSION LAYER (the alpha decision):**
- BTC regime classifier: 50-DMA (Drogen Module A) + ADX + slope → TREND-UP / CHOP / TREND-DOWN; gates which strategies may fire. Shadow-log regime states for validation before gating goes live.
- Session engine elevation: existing session windows become per-strategy gates + a UI session clock; weekend/holiday thin-liquidity flag with default size reduction.

**R-2 — KEEP-LIST UPGRADES (Nick's two named features):**
- **Bottom Signals → Cycle Extremes:** keep all 9 signals; mirror the froth side from existing client logic (basis >10%, call-skew extreme, funding blowout, OI extreme); add signal #10 (ETF-flow exhaustion, UW-fed); staleness honesty per label contract; panel framed as a **regime dial** (CAPITULATION ⟷ FROTH), froth side labeled sizing-context-only.
- **CVD event-ization:** spot-vs-perp CVD split; tape-health chip (SPOT-LED / PERP-LED / MIXED + slope); divergence & absorption event detection anchored to profile levels (VAH/VAL/POC/session extremes); events land in the signal feed with setup framing, not on a chart wall. Expose the Market Structure Filter's profile levels via hub MCP while in there (PYTHIA parity).

**R-3 — STRATEGY PORTFOLIO (all shadow-first, n-gated):**
- Retune incumbents: funding trend+extreme aggregation; carry-asymmetry display (DAEDALUS rule); second-flush prohibition on Liquidation Flush; session gates on Session Sweep; keep 2E's regime pre-filter and score decay.
- Port candidates from equity stack: WRR buy model on BTC daily (its doc already names this), ARTEMIS-class structure entries recalibrated to 1h/4h; Holy Grail/Exhaustion already live — enroll them in outcome tracking like everything else.
- Hypotheses: RSI-2 on perp expression (CHOP-gated; lowest priority); Drogen Module B (cross-sectional momentum) stays **deferred** — capital-constrained and architecturally overlapping the queued THALES module.

**R-4 — NEW CONTEXT SURFACES (state chips, not charts):**
- OI × price divergence chip (4-state), perp basis chip, ETF flow tracker (daily net, BTC + ETH funds), dominance + ETH/BTC regime strip, stablecoin supply trend (DeFiLlama repurpose), macro context band (DXY, real yields, econ calendar w/ pre-print entry freeze) — Horse-Rule-separated.
- ETH as first-class second symbol (strategy coverage decision belongs to Nick — see Open Decisions).

**R-5 — UI PORT TO v2 (MOCKUP GATE APPLIES):**
- Port Stater Swap into the `/app/v2` design system with the actionable-alpha layout: regime header (regime chip + session clock + weekend flag + distance-to-floor), tape-health strip (CVD state, funding, OI delta, basis), signal feed with governance tags (shadow/live) and full setup cards (entry/invalidation/size incl. funding cost + liquidation-distance-in-ATRs), Cycle Extremes dial, collapsed macro band, discipline chips (daily loss, concurrent count, cooldown state).
- **HELIOS standing veto: no build until Nick approves ≥3 concept mockups; post-deploy screenshot comparison against the approved mockup.**

### Explicitly deferred / rejected
- Alt-coin scalping universe (until dominance regime layer proves out) · paid on-chain vendors (Glassnode etc. — derivative-positioning approach covers it at $0 incremental) · crypto options structures (no Deribit account) · Drogen Module B (deferred, see R-3) · any live scoring change without shadow validation.

### Budget & governance notes for Titans
- **UW budget:** crypto data is overwhelmingly non-UW (Coinalyze/Binance/Deribit/DeFiLlama), so the rebuild is nearly UW-budget-neutral; the only new UW draw is ETF-flow + any crypto-endpoint polling — ATLAS to size it against the 17K/18K watchdog thresholds.
- **Committee logging:** this pass should be persisted with `outcome_source='COMMITTEE_REVIEW'` once the write path ships (Brief D dependency); until then this document is the record.
- **Skill stubs:** when R-1/R-2 land, the seven `references/crypto.md` stubs get authored from this brief + validated data — closing the loop PROJECT_RULES requires.

### Open decisions for Nick (answer before Titans Pass 1)
1. **Vendor sanction:** formally bless Coinalyze/Deribit/Binance/DeFiLlama as the crypto data tier (pending F-1 verification), or direct consolidation?
2. **ETH scope:** first-class second symbol in this rebuild (strategies + Cycle Extremes), or BTC-only v2 with ETH fast-follow?
3. **Cycle Extremes two-sided design:** approve the FROTH column with the sizing-only framing?
4. **New-spend ceiling:** committee recommends $0 incremental data spend; confirm.

---

## PART 5 — TITANS HANDOFF

**Requested flow:** ATHENA sequences the R-stack against the master backlog (this is Backlog Item II / ZEUS Phase II) → ATLAS owns F-1/F-2/F-3/F-4 architecture (schema, hub MCP tools, poller cadence, UW budget math) → AEGIS reviews vendor keys/env-vars and any new webhook surfaces → HELIOS produces ≥3 Stater v2 concept mockups (gate) → ATHENA synthesis → Nick approval → CC briefs authored per phase, committed to `docs/codex-briefs/`, executed with pathspec-only commits outside trading hours.

**Suggested brief decomposition (ATHENA to confirm):** Brief S-1 = R-0 foundation · S-2 = R-1 regime/session · S-3 = R-2 keep-list upgrades · S-4 = R-3 strategy retune + shadow enrollment · S-5 = R-4 surfaces · S-6 = R-5 UI port (post-mockup-gate).

**ACK line:** Nick replies ACK (with answers to the four open decisions) → Titans Pass 1 convenes.

---

*Prepared in the coordination lane, 2026-07-12. Repo refs verified at commit 3eb3b00 (main). Nothing in this document has been committed to the repo; committing this file is itself part of the handoff.*

---

# ADDENDUM A — Nick's Decisions & Scope Amendment (2026-07-12, post-ACK)

## Decision log

| # | Decision | Nick's answer |
|---|----------|---------------|
| D1 | Vendor sanction (Coinalyze/Deribit/Binance/DeFiLlama, pending F-1 verification) | **APPROVED** |
| D2 | Symbol scope | **EXPANDED** — universe is now **BTC, ETH, SOL, HYPE, ZEC, FARTCOIN** |
| D3 | Cycle Extremes two-sided design | **APPROVED**, with clarification below |
| D4 | $0 incremental data spend | **APPROVED (for now)** |

## D3 clarification — what reads what

The dial measures **positioning extremes in both directions**: CAPITULATION column = overly-bearish extreme (the original 9 bottom signals); FROTH column = overly-bullish extreme. **Momentum in both directions** is intentionally a separate instrument: the R-1 regime classifier (TREND-UP/CHOP/TREND-DOWN) + the OI×price quality chip (durable-up / fragile-up / squeeze-fuel-down / durable-down). Keeping the thermometer (crowding) separate from the speedometer (momentum) prevents fading strong-but-clean trends. Framing rule extends to both columns: CAPITULATION = B1 accumulation-timing context; FROTH = risk-reduction/sizing context; **neither column auto-generates scalp signals.**

## D2 — Multi-symbol universe: consequences absorbed into the R-stack

The rebuild changes from "BTC-native + ETH fast-follow" to a **six-symbol universe with tiered data coverage**. The foundation work (R-0) barely changes; complexity is absorbed by one new first-class architecture artifact:

### A-1. Symbol Capability Matrix (new ATLAS deliverable under F-1)
F-1 vendor verification extends to a **per-symbol × per-signal coverage matrix** across all six tokens: funding, OI, liquidations, term structure (Coinalyze — explicitly verify Hyperliquid exchange coverage for HYPE/FARTCOIN-native liquidity), 25-delta skew (Deribit — expected BTC/ETH, verify SOL, expect N/A for others), quarterly basis (Binance — expected BTC/ETH only), spot orderbook (Binance — verify listings per symbol), UW crypto endpoint coverage per symbol, TV MCP coverage per symbol. **Every panel and signal renders per-symbol only where data exists, with explicit N/A states — never fake-neutral, never silently blank.** Coverage claims above are expectations to verify, not assertions.

**Conditional vendor note:** if Coinalyze does not carry Hyperliquid-native pairs, the **Hyperliquid public API (free)** enters F-1 as a sanction candidate — still $0 spend but a fifth vendor, which amends Pass-2 resolution #1. Nick pre-approves the verification; adding it as a dependency comes back as a one-line confirm.

### A-2. Symbol tier system (URSA/MIDAS joint, replaces the old ETH-scope question)
- **Tier 1 — BTC, ETH:** full signal coverage, full strategy menu, full Cycle Extremes.
- **Tier 2 — SOL:** near-Tier-1 expected (deep perps, options and ETF-flow data likely available — verify in F-1). Full menu pending matrix confirmation.
- **Tier 3 — HYPE, ZEC, FARTCOIN:** funding/OI/liquidation-class strategies only; reduced size caps; wider-spread slippage assumptions baked into stop math; momentum-regime-gated (no Tier-3 entries when BTC regime = TREND-DOWN); second-flush prohibition strictly enforced; **no negative-funding-fade longs at Tier 3 initially** (carry asymmetry + thin books compound).

### A-3. Regime hierarchy update (amends R-1)
BTC regime = **master gate for all crypto risk** (alts are BTC-beta in risk-off). The dominance / ETH-BTC / alt-breadth strip is promoted from context surface (R-4) to **gating input for Tier 2/3 long scalps** (alt entries want alt-season confirmation or at minimum BTC-regime-not-down). Per-symbol trend state refines individual entries.

### A-4. URSA per-symbol risk flags (carry into Titans review and UI copy)
- **ZEC** — privacy-coin regulatory/delisting tail risk on major venues; post-parabolic structure after the late-2025 run means broken-parabola dynamics (Drogen Module C class) are the operative pattern — rips into prior supply are suspect.
- **FARTCOIN** — pure sentiment vehicle; liquidity/spread cliff risk; hard per-trade size floor-cap; sentiment-regime dependency means Tier-3 gating is non-negotiable.
- **HYPE** — venue concentration: liquidity and canonical data live primarily on one venue (Hyperliquid); single-venue outage/data risk must be visible in staleness states.
- **SOL** — nearest to Tier-1 profile; the main open question is data parity (options/ETF coverage), not tradability.

### A-5. Cycle Extremes scope under the matrix
Full two-column dial for BTC/ETH; partial dials render for other symbols only where inputs exist (e.g., funding/OI/liquidation-based signals compute for all six; skew/basis columns show N/A outside covered symbols). The dial header states its coverage per symbol.

## Superseded lines
- Part 4 / R-4 "ETH as first-class second symbol (decision belongs to Nick)" — **superseded by D2 + A-2.**
- Pass-2 resolution #1 "zero new vendors" — **conditionally amended by A-1** (Hyperliquid public API, verification-gated, $0).

## Updated Titans handoff note
ATLAS's F-1 deliverable now includes the Symbol Capability Matrix (A-1) and tier enforcement points (A-2); HELIOS mockups must show the multi-symbol switcher, per-symbol N/A states, and tier badges; AEGIS adds any new vendor key/env-var to review scope. Brief decomposition unchanged (S-1…S-6); S-1 grows by the matrix work.

*Addendum recorded 2026-07-12 evening MT. Decisions D1–D4 are Nick's, verbatim intent preserved.*
