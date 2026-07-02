# Olympus System Review — Rebuild State & Path to Edge

**Date:** 2026-07-01 (run ~16:50 MT, market closed; NFP 7/2 8:30 ET; market closed 7/3 for July 4th)
**Type:** Olympus double-pass META-review (system, not a trade setup) · precedent: `olympus-edge-review-2026-06-22.md`
**Data pulled at run-time:** mcp_ping ok (v2.0) · bias composite · flow radar (8h) · sector strength · hermes · hydra · trade ideas · positions · balances · market_profile (SPY, IWM) · web price/headline verification · full commit log 6/01–6/30 · repo docs
**Author:** Claude (chat) with Nick · logged toward committee-review attribution (n≥250 goal)

---

## TL;DR

June shipped the measurement apparatus (edge validation on 12,822 signals, L0 gates, L1a shadow, Stage-2 harness, outcome resolvers, darkpool enrichment) — **and left every switch in shadow.** Live check 7/1: the #1 trade idea is an 85-score Holy_Grail LONG (NKE); 6 of the top-15 ideas are Holy_Grail; 13/15 are LONGs — the exact classes the 6/16 validation killed. **The fastest edge is enforcement, not invention.** Committee verdict: flip the switches, gate Achilles, mine three already-collected shadow datasets, and start Triton's forward-edge evidence accruing in parallel (see companion brief `2026-07-01-triton-step0-flow-health-forward-edge-logger.md`).

---

## 1. Verified state (commits + live checks, not memory)

| Item | Status | Evidence |
|---|---|---|
| Edge validation (12,822 signals) | DONE 6/16 | `signal-edge-validation-2026-06-16.md` — score broken as probability sorter; edge = liquid universe + SHORT/URSA regime cell |
| L0.1a suppression gate | **SHADOW ONLY** | tagging Holy_Grail/Crypto since 6/17 (`d8c1522`), `L0_ENFORCE=False`, diverts nothing |
| L0.2 allowlist / L0.3 APIS / L0.4 codenames | BUILT | `430251b` / `2bc288d` (inert by design) / L0.4 live |
| L1.0 flow plumbing | REPAIRED | Path A `ab39f47`, staleness `1874b01`, fabricated-bullish fix `635c18e`, cached-quote `130e848`, Hydra `bf7994c`+`e22985f` |
| L1a auction+flow gate | SHADOW, was starved | wk1: 563 tagged / 53 in-scope / **1 pass**; root cause MP feed decay 191→23 (`3fdc97f`, `2617c31`) |
| PYTHIA feed re-arm (Option A) | **TOOK** | SPY MP live for the 7/1 session (verified this run); IWM restored after a zero-week |
| L1b factor pipeline | 0/3 | RSI-2 S1✓/S2✗ (long-vega vs IV crush); Momentum S1✗; PEAD S1✗ (decayed post-2020) |
| bars.py 'r' filter | SHIPPED 6/30 | `facf023` — ADX clean-data clock running for Chunk-3 promote |
| hub_get_chart_indicators | SHIPPED | `e6a94ed`; happy-path retest still pending (UW quota has reset — 10-min task) |
| Doc reconciliation | SHIPPED 6/30 | `6bbd58e` |
| Triton / Nemesis (L2) | PARKED (correctly) | design locked; confluence premise unsupported on current data (CONVICTION n=7, −0.57) |
| Sidecar (Achilles regime gate + kill-switch) | **NEVER BUILT** | no commit exists; `signals.regime` conditioning still `deferred_sb3_null` |
| 6/22 scoring trio (theme×dir, hold-horizon, convexity tags) + 10d-RS fix | **NO BRIEF, NOT BUILT** | codex-briefs scan confirms; 10d RS column verified all-zeros again 7/1 |

## 2. Red flags found in the 7/1 live checks

1. **Flow radar returned ZERO events over an 8-hour lookback spanning full RTH on a normal trading day.** Honest-unavailable (not fabricated), but the feed appears dark. Poller was re-enabled 6/18 and validated 6/23 with 1,371 events — something broke since, or quota died early. **P1 — root-caused in Phase 0 of the companion Triton brief.** *(Post-P0 update: RCA = transient Upstash/Redis write-failure during RTH; poller, quota, and `flow_events` table all healthy; fix routed to its own mini-brief — `flow_events` DB fallback tagged `source:"db_fallback"` + age.)*
2. **10-day sector RS feed still all zeros** (dead yfinance feed in `backend/scanners/sector_rs.py`, flagged 6/22, never fixed). `state` labels in sector_strength are junk wherever they lean on it.
3. **June-22 greenlit scoring trio never briefed** — dropped ball.
4. **Sidecar never shipped** despite the rebuild-stack brief marking it "does NOT wait on the stack." The single most validated strategy improvement (regime-gated sell_the_rip + kill-switch) is idle.
5. Hygiene: balances stale since 6/22; one XLF position row with null strikes; `trading-memory.md` frozen at 6/12 with April-era positions and stale trip wires (SPX 7,483 vs a ~6,600 trip level written in April).

## 3. Tape context (web-verified 7/1)

S&P 7,483 (SPY ≈ $744.6 — matches hub MP `price_at_event`). Best quarter since 2020 just closed (Nasdaq +20% Q2; H1: SPX +9.6%, Russell +22%). **7/1: semis cracked — SOXX −4.7%, MU −8/−10%** after chips ran +80% H1; META +9–11% on cloud-business pivot; CRWV −14%. Warsh hawkish at Sintra ("prices are too high"), rate-HIKE risk being priced. ADP soft (98K vs 110K est); NFP 7/2 8:30 ET. Iran ceasefire violated again; US strikes ongoing. Hub: bias NEUTRAL +0.09, GEX MOMENTUM, **copper/gold flipped to −0.7** (was +0.7 on 6/22), sector leadership rotated defensive (XLV +11.0 / XLF +8.4 / XLI +7.1 lead; XLK −4.7 now 2nd-worst; XLE −6.7 worst), narrow leadership (breadth 0.18).

---

## 4. Olympus Pass 1 — independent reads

**TORO:** The rebuild is working — L0 shadow proved tags match intent (77 tagged, zero keepers lost), the re-arm restored SPY same-day, Stage-2 killed three seductive factors for free. Post-enforcement, a liquid-only feed leans positive: the validation's only positive buckets — index_macro (57.8% WR, +0.78) and large-cap tech (+0.82) — are exactly what L0.2 keeps.

**URSA:** Three bleeds. (1) Every day L0 stays in shadow, the feed runs −0.46%/signal and Nick's attention is polluted by Holy_Grail longs; two weeks of clean shadow on a KILL-confirmed strategy is enough — shadow-by-default is build discipline, not a permanent residence. (2) The n≥250 L1a bar is a timeline trap: at 53 in-scope/week, resolved-pass n≥250 is months out; if all enforcement waits on it, no edge until autumn. (3) Feed-decay has bitten twice; the per-name freshness monitor (briefed 6/29) is unbuilt — L1a's dataset accrual will silently die a third time. Book note: 4× XLF bearish positions vs the #2-strongest 20d sector + META spread expiring worthless 7/2 into NFP = counter-tape concentration; trip wires too stale to evaluate.

**PYTHAGORAS:** The barbell (1–2d PF 2.93 / 16d+ PF 4.70 / 6–15d dead) and single-leg convexity (PF 8.47 vs verticals 1.46) remain the strongest personal-edge facts — and their operationalizing tags were greenlit 6/22 and never briefed. ADX clean-data clock started 6/30; Chunk-3 promote is the technical prerequisite for the Achilles gate — the sequence is now unblocked. Tape: today's semi break + defensive rotation + hawkish Warsh is the first structural crack in the melt-up; have Achilles gated BEFORE a regime arrives, not after.

**PYTHIA:** Re-arm took (SPY 7/1: POC 742.86, VA migrating lower, thin volume, "above VAH in thin extension – caution") — but one session proves nothing about decay; the monitor is the difference between a feed and a hope. Second: the L1a `fail` bucket is being wasted — 23/53 in-scope signals had flow contradicting direction; that's a suppression filter already computing itself in shadow, needing only an outcome join. The gate may earn its keep as a REJECTOR long before its pass logic accrues n≥250.

**DAEDALUS:** Sharpest insight this pass: **RSI-2's Stage-2 failure mechanism inverts on the short side.** Long-side dip-buying enters at elevated IV and exits into IV crush (long vega fighting you). Short-the-rip in a downtrend enters at compressed IV and exits into expanding IV — vega becomes a tailwind — and lands in the platform's one proven cell (SHORT/URSA +0.256, n=2,036; sell_the_rip/URSA 59% WR, +1.36). **L1b factor #4 = Connors short-side mirror (RSI-2 > 90, price < 200-SMA, put debit spread) through the existing Stage-2 harness.** Also: the B2 options-expression shadow layer has collected real expression grades since 6/5 and nobody has analyzed it. Free study.

**THALES (fires: macro catalyst + crowded trade):** (1) NFP into a holiday-thinned tape, a Fed chair floating hikes, Iran hot, and the most crowded trade on the planet (semis, +80% H1) taking its first −4.7% hit — a regime-transition WATCH, not a call; argues for finishing the bear-side machinery now, while it's cheap. (2) The dark-pool angle: darkpool enrichment has shadow-collected spread-relative direction metadata on every signal since 6/7 with bonus=0 — three-plus weeks of signal×darkpool×outcome data exists, never analyzed. Mine what's free before designing any new dark-pool strategy.

## 5. Pass 2 — cross-examination

- **TORO vs URSA on shadow discipline → distinction ratified:** shadow-first stays sacred for NEW logic; L0.1a suppression of KILL-confirmed strategies is executing a verdict already rendered (Holy_Grail n=4,657; Crypto n=108). Two weeks of shadow tags with zero keepers lost is sufficient. **Enforce is overdue.** Measurement stays on for the before/after.
- **URSA's timeline trap → accepted; PIVOT reframes:** "edge flowing into the hub" gets two horizons. Near-term edge = subtraction + regime gating (days away). Long-term edge = confluence gating + Triton (correctly parked behind the dataset).
- **PYTHIA's fail-reverse vs Triton's premise → complementary:** confluence-as-PROMOTION is unsupported (n=7, −0.57); flow-contradiction-as-SUPPRESSION is a different, cheaper claim. L1a may validate as a rejector first.
- **DAEDALUS factor #4 vs Anti-Bloat → passes as REPLACE-track** (options-correct expression of the lane the platform already owns). Pre-registered URSA risk: it aligns with Nick's documented bearish bias — ruthless B.05/B.06 beta-strip required at Stage-1, logged now so it can't be softened later.
- **THALES + URSA dual-check on the tape:** semi crack + defensive rotation + hawkish Fed is consistent with Nick's book → extra skepticism of narrative confirmation. Logged as "regime-transition watch," not thesis validation. No trade recommendations issued this pass.
- **Flow-radar-dark (all agents):** promoted to top of the action queue — every flow-dependent workstream (L1a flow half, fail-suppression study, Triton) sits on this feed.

## 6. PIVOT — synthesis

**DATA NOTE:** MCP connected (v2.0). Degraded inputs: `flow_radar` (0 events/8h — treated as feed-down, not "no flow"), `portfolio_balances` (stale 6/22), `hydra` (empty, benign). Prices cross-verified hub-MP ↔ web (SPY ≈ 744.6 / SPX 7,483, 7/1 close). Meta-review — no trade entries issued; any execution requires a fresh `hub_get_quote` pass.

**VERDICT: BUILD — flip enforcement, gate Achilles, mine the free data. DON'T build any new signal source until the switches already owned are on.**
**CONVICTION: HIGH** on the sequence; MEDIUM on the L1a long-game timeline (feed-decay risk until the monitor ships).

**CONVERGENCES:** all seven lanes independently converged on "enforcement, not invention, is the missing edge" · URSA+PYTHAGORAS+THALES: ship the Achilles gate + kill-switch BEFORE a potential URSA regime arrives (April −7.80 lesson) · PYTHIA+DAEDALUS+THALES: three shadow datasets (L1a tags, darkpool enrichment, B2 expressions) already collected and unanalyzed = cheapest alpha available.

**DIVERGENCES:** TORO "trust the long bake" vs URSA "bake is too slow" → resolved via two-horizon edge definition · DAEDALUS factor-#4 enthusiasm vs URSA bias-alignment concern → proceed with pre-registered ruthless beta-strip.

**SYNTHESIS:** June built a lie detector and kept listening to the liar. The validation says exactly where the money burns — Holy_Grail, Crypto, un-gated longs, the single-name graveyard — and the 7/1 feed still fronts all of it because every switch is welded in shadow. Flip L0.1a. Gate Achilles with a kill-switch so the one real edge can't April us again. Fix the flow feed that went dark today before building anything on top of it. Then let the three shadow datasets filling since early June reveal the next edge for free, while L1a bakes toward n≥250 and Triton waits its turn. No new toys until the bought ones are out of the box.

---

## 7. Edge opportunities (ranked)

1. **Subtraction alpha (immediate):** whole-feed expectancy −0.46%/signal; Holy_Grail ≈ −4,855 pnl-units alone. Enforcing suppression + allowlist converts the feed from negative-sum to ~flat-positive before any new signal exists. Config flip + small brief.
2. **SHORT/URSA cell, properly caged:** only positive directional cell (n=2,036); sell_the_rip/URSA 59% WR +1.36 — worthless un-gated (Apr −7.80, Jun −2.33), potent gated. Sidecar = regime gate + regime-flip kill-switch; ADX promote path unblocked since `facf023`.
3. **Short-side RSI-2 mirror (L1b #4):** vega-inversion insight — the mechanism that killed the long factor becomes a tailwind short, landing in the proven cell. Stage-1 → Stage-2 via existing harness; beta-strip pre-registered.
4. **Flow-contradiction as suppression (L1a `fail` tag):** already computed in shadow (23/53 wk1); needs only an outcome join at larger n. Likely validates before the confluence pass premise does.
5. **Three free studies on collected data:** darkpool enrichment × outcomes (since 6/7) · B2 options-expression grades (since 6/5) · L1a asterisk/fail buckets × resolved P&L. All read-only.
6. **Personal-edge tags (greenlit 6/22, unbuilt):** hold-horizon barbell alerts + convexity-structure tag target the PF-8.47 single-leg edge and the 6–15d dead-zone leak.
7. **Triton forward-edge evidence (companion brief):** whale-flow shadow logger + forward-return grading answers the make-or-break question (does whale flow LEAD price; follow vs fade) in parallel, without building the strategy.

## 8. Scrap / retire

- **Holy_Grail & Crypto Scanner** — scrap-in-effect via L0.1a ENFORCE (keep tagging for audit trail).
- **WH_ACCUMULATION / wh_reversal** — retire (zero rows all-time, deprecated lineage, superseded by Triton design when its turn comes).
- **CTA parent** — retire parent; keep isolated APIS_CALL / TRAPPED_SHORTS via the built (inert) L0.3 gate.
- **Artemis** — stays demoted; archives on Triton's arrival per the locked 6/16 decision.
- **Feed-tier ladder as conviction display** — empirically inverted (ta_feed is the WORST tier); deprecate cosmetically once L1a tags are the quality surface. Low priority.
- **ICARUS 0DTE shadow** — park indefinitely; leveraged-ETF/0-day churn is a documented anti-edge.

## 9. Build queue (backlog v4 seed)

**This week, in order:** (1) Triton Step-0 = flow-radar dark RCA + whale forward-edge shadow logger — SHIPPED same-day, see brief §9 · (2) L0.1a ENFORCE flip brief (flag + before/after snapshot + rollback) · (3) Sidecar brief: Achilles regime gate + kill-switch (verify a few clean ADX days first) · (4) quick wins: PYTHAGORAS happy-path retest, balances sync + RH CSV import (captures recent SOXS trades, kills null-strike XLF row) · (5) PYTHIA per-name freshness monitor (brief exists 6/29 — build it).

**Next:** flow_radar db_fallback mini-brief (`2026-07-01-flow-radar-db-fallback-minibrief.md`) · Governor enforce (OBSERVE-log pull over one full RTH + HELIOS staleness UI, then flip) · June-22 scoring trio brief + 10d-RS fix · doc hygiene (trading-memory.md full refresh, backlog v4 reseat).

**Research lane (parallel, read-only):** the three free studies · L1b factor #4 Stage-1.

**Parked (correctly):** Triton v0 strategy + Nemesis (await L1a n≥250 + `fired_mode` + the forward-edge study from Step 0) · 3-10 re-audit · Outcome Tracking Phase C · Stater Swap · dashboards · Great Library.
