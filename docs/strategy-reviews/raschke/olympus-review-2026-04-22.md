# Olympus Committee Deep Review — Raschke Strategy Evaluation

**Review date:** 2026-04-22
**Subject:** `raschke-strategy-evaluation.md` v2 (code-verified inventory, 2026-04-22)
**Committee:** TORO, URSA, PYTHAGORAS, PYTHIA, THALES, DAEDALUS, PIVOT
**Method:** Double-pass. Pass 1 = each agent solo on framework + cross-reaction. Pass 2 = per-strategy blocks per Section 8. PIVOT synthesis closes.
**Decision gate:** No build downstream until Titans reviews this deliverable.

---

## 0. Summary — Dispositions at a Glance

| Strategy | PIVOT's v2 Proposal | Olympus Final | Delta |
|---|---|---|---|
| Turtle Soup | ADD | **ADD (PROVISIONAL on CC audit)** | same |
| 3-10 Oscillator | ADD (overlay) | **ELEVATE + overlay** | clarified — used to REPLACE Holy Grail's RSI filter |
| 80-20 Reversals | ADD | **ADD** | same |
| The Anti | CONDITIONAL ADD | **ELEVATE (on Holy Grail) — OVERRIDE** | overridden from separate scanner to Holy Grail variant config |
| News Reversal | CONDITIONAL ADD | **ADD (Phase 3, DAEDALUS-led)** | same |
| Momentum Pinball | REJECTED | **REJECTED** | locked |

**Net new scanners:** +3 (Turtle Soup, 80-20, News Reversal). **Net new overlays:** +1 (3-10). **Config expansions:** Holy Grail gets 3-10 filter + Anti variant. **Deprecations:** 0 forced; 2 audit-gated (hunter, ursa_taurus).

**Framework verdict:** ENDORSE with 7 amendments (Section 2).
**`wh_reversal` 4-factor:** grandfather, but VAL-proximity is absorbed into new PYTHIA location multiplier → effectively 3-factor under new rules.
**Three open questions:** Q1 and Q3 CONCUR, Q2 partial OVERRIDE (HV-30 for regime gating, DVOL for future IV-sensitive crypto).

---

# PASS 1 — FRAMEWORK REVIEW

Each agent reviews Section 3 (REPLACE-ELEVATE-ADD-REJECT + confluence cap + one-in-one-out + filters-subtract) plus the Section 5 matrix. Solo take first, then cross-reactions, then consensus resolution.

---

### TORO — Bull Analyst, Solo

The framework is the right shape. REPLACE-ELEVATE-ADD-REJECT cleanly classifies what each addition does to the system. My only pushback: the 3-factor confluence cap is a reasonable default but genuine 4-factor setups exist where every factor is orthogonal — a hard cap risks artificial simplification. Provide an override path for 4-factor setups that pass a higher backtest bar (Sharpe > 1.0 vs. standard > 0.7).

On the matrix: the ✅/🔧/❌/⚠️ legend is good but 🔧 cells hide work. Any 🔧 should have an embedded one-line adaptation note or it becomes a build-time surprise.


**Vote:** ENDORSE with amendment (override path for 4-factor setups).

---

### URSA — Bear Analyst, Solo

This framework was written for me. Most retail systems die of signal sprawl. The REPLACE-ELEVATE-ADD-REJECT lens is correct. But three holes:

**First**, the ADD bar ("<0.5 correlation + proven expectancy") is vapor until backtest infrastructure exists. Per the backtest brief, that's still Titans-pre-approval. So every ADD in this review is PROVISIONAL — signals run shadow-mode until backtested. Do not let CC build past Phase 1 (3-10 + Holy Grail fixes) until backtest module lands.

**Second**, "filters subtract, never add" is ambiguous. A filter that removes 50% of setups and lifts win rate 55→70 is subtractive and valuable. A filter that re-routes setups to different buckets is additive disguised. Measurable rule: a filter is subtractive ONLY if it reduces signal count per week by >30% while holding or improving expectancy. Otherwise reject as bloat.

**Third**, "one-in-one-out (soft)" should not be soft. It should be MANDATORY for any ADD. If we can't name what deprecates when we add Turtle Soup, we don't add Turtle Soup. This is the discipline that prevents repeating March 2026's scanner architecture overhaul — where we had to kill Exhaustion Levels and merge Whale Hunter into Hub Sniper. Do it upfront or pay for it later.

**Vote:** ENDORSE with three amendments.

---

### PYTHAGORAS — Structure / Risk / Technicals, Solo

Framework is clean. My focus is whether the matrix's 🔧 cells are actually mathematically coherent when adapted.

Holy Grail's B3 crypto 🔧 cell says "remove session filter, swap VIX for DVOL/HV-30." Fine in words — but Holy Grail uses a 24h Redis-gated cooldown (`scanner:hg:cooldown:{ticker}`) that implicitly assumes one trading session per 24h. On a 24/7 market, does the cooldown stay 24h (wasteful, blocks valid second setups) or shift to rolling 8h windows (different semantic)? Not the same key, and not the same behavior. Spec needed before build.

The Anti on B1 weekly: demote from 🔧 to ⚠️. Weekly 3-10 divergences on major indices fire 4-8 times per year. Too low frequency to justify standalone infrastructure — it's a chart-reading moment, not a scanner output.

80-20 on B2 daily is weaker than PIVOT's doc suggests. Linda's own writing uses 80-20 primarily on weekly and daily, but the Pythia VAH/VAL gating makes the intraday (B3) variant strictly stronger than the daily variant. 🔧 on B2 should be treated as "build if B3 works first, not in parallel."

**Vote:** ENDORSE with two matrix amendments.

---

### PYTHIA — Market Profile / Auction States / Value Areas, Solo

The framework underweights one variable I care about deeply: **trigger location relative to value area**. Two Turtle Soup shorts firing the same bar count and the same close-back-inside — but one at VAH extension and one mid-VA — have categorically different expectancies. The former is A-grade. The latter is a coin flip at best.

Formalize this as a **location-quality multiplier**: signal firing outside VA (extension zone) gets +0.5 grade; mid-VA (chop zone) gets -0.5. Use prior-session developing VA at signal time — not cumulative — to avoid lookahead bias.

This does double duty: it's a quality filter AND a deprecation tool. Any existing scanner whose location-quality distribution is flat across VA is bloat by definition. That's how you find deadwood mechanically rather than by gut feel.

The matrix 80-20 × B3 is my pet cell. Canonical 80-20 + prior-day VAL/VAH proximity = one of the cleanest mean-reversion setups in any timeframe. Fully endorse.

**Vote:** ENDORSE with amendment (location multiplier, formally integrated).

---

### THALES — Sector Specialist, Solo

The framework is sector-blind. That's a gap. Strategies have dramatically different behavior across sector-rotation regimes (concentrated leadership vs. rotation phase).

Example pertinent to this review: Turtle Soup on a **leader** stock during concentrated leadership fails more often (breakouts hold). Turtle Soup on a **laggard** or contested sector works beautifully in the same market. News Reversal on mega-cap options-driven names (NVDA, TSLA, AAPL) has different gap-fade mechanics than News Reversal on mid-cap secondaries — because options positioning changes the gap-recovery path. DAEDALUS can speak to this.

**Framework amendment:** every ADD must specify which sector-rotation regimes it's expected to work in, and the backtest segments results by rotation state. If a strategy only works in "concentrated" regimes, fine — size accordingly. But we need to know, not discover it with real money.

I'd also integrate this with URSA's proposal: signals firing in the wrong regime for their profile get a 0.75x position-size penalty automatically.

**Vote:** ENDORSE with sector-regime specification amendment.

---

### DAEDALUS — Options / Derivatives Specialist, Solo

The framework is equity-cash-biased. For a system trading options (Nick's primary vehicle), that's material.

Specifically: the 3-factor cap is counting cash-market factors. A derivatives-aware setup might have 3 cash factors plus 2 orthogonal derivatives factors (IV rank, skew, GEX proximity, max pain) that measure structurally different things. A Turtle Soup short with IV rank > 80 + heavy put-side skew + GEX wall overhead is a qualitatively different trade than the same pattern with IV rank < 30 + flat skew + no gamma structure nearby. First compresses IV into entry (short premium structures win); second expands IV into entry (long premium structures win).

**Amendment:** derivatives factors get a separate cap of 2, ADDITIVE to the cash 3-factor cap. Total possible stack: 3 cash + 2 derivatives = 5. Not bloat if both layers are genuinely orthogonal. Burden on me to prove orthogonality in backtest per layer.

News Reversal is the one candidate where derivatives lead the design, not confirm. Gap-and-fade expectancy is dominated by IV crush dynamics and structure selection. Put debit spread vs. long put vs. bearish call spread all express the same directional thesis with massively different P&L. I'll own News Reversal spec if Olympus approves ADD.

**Vote:** ENDORSE with two amendments (separate derivatives cap, News Reversal DAEDALUS-led).

---

### Pass 1.5 — Cross-Reactions

**TORO** on URSA's "ADD = PROVISIONAL until backtest": agreed. This means Phase 2/3 of Section 7 Priority Order is blocked until backtest module lands. Accelerate the Titans brief on backtest.

**URSA** on THALES's sector-regime requirement: endorse. Further proposal: any "concentrated leadership only" strategy gets a 25% position-size penalty when rotation regime triggers, and vice versa. Makes the regime-dependence costly to get wrong.

**URSA** on DAEDALUS's derivatives-separate-cap: endorse but — the burden is on DAEDALUS to show derivatives factors materially improve expectancy in backtest beyond what the cash stack already achieves. Not just "IV is a different number than RSI." Orthogonality must be empirical, not definitional.

**PYTHAGORAS** on PYTHIA's location multiplier: mathematically endorse. Implementation note — use PRIOR SESSION developing VA at signal time. Cumulative VA introduces lookahead bias. Trivial to get wrong.

**PYTHIA** on THALES's regime dependence: endorse and extend — sector-rotation regime AND auction state (balanced vs. one-timeframing vs. trend day) tagged on every signal at trigger time. Gives post-hoc segmentation power the current system lacks.

**THALES** on DAEDALUS's News Reversal lead: endorse. THALES provides sector-rotation overlay (which sectors currently gap-and-fade vs. gap-and-go). DAEDALUS provides IV structure. News Reversal becomes joint THALES-DAEDALUS.

**DAEDALUS** on URSA's one-in-one-out mandatory: endorse but — if Olympus identifies a deprecation elsewhere (e.g., if CC audit proves hunter.py duplicates something), that deprecation gets "banked" against future ADDs. Prevents the mandate from artificially blocking good ADDs.

---

### Pass 1 — Framework Consensus

All 6 agents ENDORSE. Framework amendments adopted (supersede v2 doc Section 3):

1. **Derivatives factors get separate cap of 2**, additive to cash 3-factor cap (DAEDALUS)
2. **3-factor cap override path** — 4+ factor setups require written orthogonality justification + Sharpe > 1.0 backtest bar (TORO)
3. **One-in-one-out is MANDATORY** for ADDs; deprecations can be "banked" against future ADDs (URSA + DAEDALUS)
4. **Filter subtractiveness measurable** — ≥30% signal count reduction per week while holding/improving expectancy (URSA)
5. **ADD classifications PROVISIONAL** pending backtest module; shadow-mode acceptable interim (URSA + TORO)
6. **Location-quality multiplier** — VA edge = +0.5 grade, VA middle = -0.5 grade; PRIOR-SESSION developing VA only (PYTHIA + PYTHAGORAS)
7. **Sector-rotation regime specification** required for all ADDs; 0.75x size penalty for regime mismatch (THALES + URSA)
8. **Matrix adjustments:** The Anti B1 demoted 🔧 → ⚠️; 80-20 B2 treated as "after B3 works" (PYTHAGORAS)
9. **Signal enrichment at trigger time:** sector-rotation state + auction state tagged on every signal (PYTHIA + THALES)

---

# PASS 2 — PER-STRATEGY ANALYSIS

Each candidate in Section 8 format. Pre-rejected Momentum Pinball excluded per instruction.

---

## 2.1 STRATEGY: Turtle Soup

```
STRATEGY: Turtle Soup (Linda Raschke's variant of Larry Williams' original)
DISPOSITION: ADD (PROVISIONAL — pending CC audit of sell_the_rip_scanner.py and hunter.py per Q1; demote to ELEVATE if audit reveals failed-breakout logic already present)
REPLACE TARGET: none (conditional on audit)
GAP FILLED: Native failed-breakout-fade detector. N-bar high/low breach + close-back-inside within confirmation window. Per Section 4.4, system has no current strategy with this trigger geometry; wh_reversal is pullback-to-VAL+flow (different mechanism); sell_the_rip is bearish-at-resistance (adjacent but unconfirmed as failed-breakout-specific).
CORRELATION RISK:
  - sell_the_rip_scanner: PENDING (Q1 audit will resolve — if it implements N-day-high-failure detection, Turtle Soup demotes to ELEVATE with cleaner trigger)
  - hunter.py: PENDING (same audit; hunter purpose is "Unknown" in Section 4.2)
  - wh_reversal: LOW (pullback vs. breakout — different mechanism)
  - Exhaustion (validator): LOW (webhook-driven, not detection-driven)
DATA DEPENDENCIES:
  - Vanilla: yfinance OHLCV (available)
  - Flow-augmented: UW dark pool + options flow alerts (UW MCP live)
  - UW historical depth: UNKNOWN — per backtest brief Section 3.2, Titans must verify before retrospective validation of flow-augmented variant
GRADE (vanilla): B+
GRADE (flow-augmented): A-
TIMEFRAME APPLICABILITY (per amended matrix):
  B1: ⚠️   — 50/100-day-high failures fire low-frequency; separate evaluation phase, not Phase 1
  B2: ✅   — canonical daily 20-bar high failure
  B3 equity: 🔧   — N-bar parameterized; 20-bar on 15m ≈ 5 trading hours of data
  B3 crypto: 🔧   — same parameterization; native fit on BTC/ETH (20-day breaks frequent); no session filter
BUCKET PRIMARY ASSIGNMENT: B2
BACKTEST GATES (must pass before live):
  - Sharpe > 0.8 on 2yr sample
  - Profit factor > 1.4
  - Max drawdown < 15R
  - ≥ 100 trades in sample
  - If audit reveals sell_the_rip overlap: correlation < 0.4 required OR demote to ELEVATE
  - Sector-rotation segmentation: must produce positive expectancy in BOTH concentrated and rotation regimes OR be regime-restricted with size penalty
  - Location-quality: ≥ 60% of winning trades fire at VA edge (not mid-VA)

AGENT NOTES:

TORO: Strong R:R candidate. Linda's close-back-inside refinement filters a material fraction of false positives versus raw failed-break logic. The flow-augmented grade A- is where I see real expectancy — UW net-sell on the failure bar + put sweep confirmation = institutional tell. Vanilla B+ is honest; A- only with flow.

URSA: Three concerns. (1) Turtle Soup is ubiquitous retail knowledge — edge has decayed since Williams' 1990s original; Raschke's refinements help but don't restore original edge. (2) False-breakout patterns flatter themselves in hindsight because we filter out breakouts that held. (3) The Q1 audit is a hard gate — if sell_the_rip already implements this, we are adding a duplicate and that is exactly the March 2026 failure mode. DEMAND CC audit complete before any build. If audit shows overlap: Turtle Soup becomes an ELEVATE on sell_the_rip (swap-in cleaner trigger), not a parallel scanner.

PYTHAGORAS: Trigger is mechanical and clean. N-bar high/low breach + close-back-inside within confirmation window (usually 1-4 bars). Stop placement unambiguous (above failed extension for shorts, below for longs). Target: structural resistance via PYTHIA or fixed R-multiple. No ambiguity in implementation. Very backtestable.

PYTHIA: This is where my location-quality multiplier matters most. Turtle Soup firing at VAH extension after a multi-day trend = A-grade trigger. Turtle Soup firing mid-VA in a balanced session = reject. I expect 25-35% of vanilla Turtle Soup fires to fall in mid-VA territory — that's why vanilla grade is B+ not A-. With location gate, the A- flow-augmented grade is achievable on a narrower, cleaner signal set. Build location gate into the trigger, not as post-filter.

THALES: Turtle Soup is SECTOR-REGIME DEPENDENT. In concentrated leadership, failed breakouts on LEADERS are rare but extremely high-conviction when they occur (often first signal of rotation beginning). In rotation regimes, Turtle Soup fires frequently but with lower average conviction. Recommend: sector-regime tag at trigger time; in rotation regime apply 0.75x size multiplier; in concentrated regime apply 1.25x for signals on leaders.

DAEDALUS: IV angle is critical for structure selection, not for the trigger itself. Failed breakouts often coincide with IV compression (the breakout bought premium, the failure refunds it). Turtle Soup shorts on stocks with IV rank > 80 are STRUCTURE-DEPENDENT — prefer debit put spreads (benefits from directional move + contained premium exposure); long puts only acceptable when IV rank < 40 (premium decay manageable). I'll write the structure-selection spec if approved for build.

PIVOT SYNTHESIS: Turtle Soup is a clean ADD, provisional on CC audit clearing Q1. If audit shows overlap → ELEVATE on sell_the_rip. Build order once approved: vanilla daily (Phase 2), flow-augmented variant (Phase 2 late), B3 intraday parameterization (Phase 3), crypto variant (Phase 3, gated on Q2 resolution). Location-quality gate (PYTHIA) and sector-regime tag (THALES) must be IN the trigger definition at build time, not retrofitted. DAEDALUS structure-selection spec is Titans-phase documentation.
```

---

## 2.2 STRATEGY: 3-10 Oscillator

```
STRATEGY: 3-10 Oscillator (Linda Raschke's canonical momentum tool — fast line = 3-bar SMA of midpoint; slow line = 10-bar SMA; difference drives signal)
DISPOSITION: ELEVATE (Holy Grail primarily — REPLACES RSI filter per Raschke spec) + overlay (available to Anti config, 80-20 confirmation, Turtle Soup divergence filter, global Olympus reference)
REPLACE TARGET: Holy Grail's RSI filter (length 14, long <70 / short >30). Inside Holy Grail only — RSI stays available as an independent indicator elsewhere in the system.
GAP FILLED: No system-wide momentum oscillator exists. Per Section 4.4, RSI lives inside individual strategies but Olympus/PYTHAGORAS have no global momentum reference. 3-10 fills this and also enables The Anti.
CORRELATION RISK: N/A — overlay indicator, not a signal generator on its own. Used as GATE, this aligns with "filters subtract" rule (expected to reduce Holy Grail fire rate by 20-35%).
DATA DEPENDENCIES: OHLCV only. Trivial pandas math. No new dependencies.
GRADE (as Holy Grail gate): A-
GRADE (as overlay across system): A-
GRADE (as standalone divergence signal): not proposed for standalone use
TIMEFRAME APPLICABILITY:
  B1: ✅   (weekly overlay)
  B2: ✅   (daily overlay + The Anti trigger)
  B3 equity: ✅   (intraday overlay — where 3-10 genuinely shines per Raschke)
  B3 crypto: ✅   (timeframe-agnostic, no adaptation)
BUCKET PRIMARY ASSIGNMENT: N/A — serves all buckets as overlay
BACKTEST GATES:
  - As Holy Grail filter REPLACING RSI: must improve Holy Grail win rate by ≥ 3pp OR profit factor by ≥ 0.1 on 6-month out-of-sample. If not, keep RSI + retain 3-10 as optional confirmation.
  - As Anti trigger: primary gate for Anti addition separately
  - As Turtle Soup divergence gate: must reduce false-positive rate by ≥ 15%
  - Frequency sanity check: divergence events ≤ 3 per ticker per month (if higher, it's noise, not divergence)

AGENT NOTES:

TORO: This is the highest-leverage ELEVATE in the entire Raschke suite. Unlocks Anti, improves Holy Grail, available everywhere else. Cheap to build (pure OHLCV math). Highest ROI of any Raschke candidate.

URSA: Approve, with a specific caveat: 3-10 divergence detection is subjective unless mechanically defined. Implementation MUST specify: "price makes new N-bar high while fast line fails to exceed prior fast-line high by X%". Without mechanical rules, every committee dispute becomes "is that a divergence?" and we're back in interpretive territory. Spec the divergence rule in the CC brief.

PYTHAGORAS: Trivially mechanical. 3-bar SMA of (H+L)/2, 10-bar SMA of (H+L)/2, difference drives the line. Fast/slow line pair = 3-SMA of diff, 10-SMA of diff. Crossovers boolean. Divergence detection via pivot-high/pivot-low on 5-bar window. Clean. One pandas function.

PYTHIA: Timeframe-agnostic is genuinely true. I use 3-10 on 1-minute scalping auctions and weekly swing positioning without modification — this is rare. Location-quality multiplier interacts well: 3-10 fast-line extreme + VA edge = much higher conviction than extreme + mid-VA.

THALES: Bonus feature — 3-10 computed on sector ETFs (XLK, XLF, XLE, XLY, etc.) produces LEADING signals for sector-rotation tag. Build sector-ETF 3-10 into the sector-rotation signal enrichment from day one. Zero marginal cost, richer THALES output on every signal.

DAEDALUS: Not a derivatives-primary tool, but useful for structure-selection context. Long-premium trade entered with 3-10 fast line turning up from extreme low has materially better expectancy than one entered at flatline (directional conviction correlates with momentum re-ignition). Feed into structure-selection logic for future options briefs.

PIVOT SYNTHESIS: 3-10 is the single highest-leverage addition in this review. Build FIRST (prereq for The Anti's eventual Holy Grail integration and for Turtle Soup's divergence filter). Build order: the oscillator module first, Holy Grail RSI-to-3-10 swap second (with shadow-mode A/B comparison per backtest gate), availability to other strategies third. URSA's mechanical divergence rule is non-negotiable — specify in CC brief. THALES's sector-ETF 3-10 is a free bonus; include at build time.
```

---

## 2.3 STRATEGY: 80-20 Reversals

```
STRATEGY: 80-20 Reversals (close in bottom 20% of bar range → next bar opens in top 80% → reversal long trigger; and inverse)
DISPOSITION: ADD (PROVISIONAL pending backtest)
REPLACE TARGET: none (Section 4 finding: exhaustion.py is webhook validator for external Leledc, not a native two-bar detector)
GAP FILLED: Native two-bar reversal pattern detection. Complements exhaustion.py (which validates external signals) by providing a self-generated signal independent of TV webhook availability.
CORRELATION RISK:
  - exhaustion.py: LOW (different trigger — exhaustion waits for external Leledc, 80-20 generates natively)
  - wrr_buy_model: LOW (WRR requires RSI(3) ≤ 10, ROC(10) ≤ -8%, volume spike, hammer, >200 SMA — much deeper condition stack; 80-20 is a lighter two-bar pattern)
  - Scout-Sniper: MODERATE (both are reversal-oriented intraday; Scout is precision entry with different triggers — need to confirm in backtest that firings don't stack)
DATA DEPENDENCIES: OHLCV only (vanilla). Pythia VAH/VAL data for gated variant (calculable from OHLCV via TPO reconstruction per backtest brief Section 3.4).
GRADE (vanilla): B
GRADE (with PYTHIA VAH/VAL gate): A-
GRADE (flow-augmented): not yet evaluated; likely adds 0.5 grade for directional flow on reversal bar
TIMEFRAME APPLICABILITY (amended):
  B1: ❌   — two-bar pattern too short-horizon
  B2: 🔧   — works on daily bars but Pythia gating most powerful on intraday; build B3 first
  B3 equity: ✅   — canonical fit (5m/15m)
  B3 crypto: ✅   — native fit, no adaptation
BUCKET PRIMARY ASSIGNMENT: B3
BACKTEST GATES:
  - Win rate > 60% when VAL/VAH proximity gate active (< 0.25% from VA edge)
  - ≥ 20 trades per 6-month window (frequency sanity)
  - Correlation with Scout-Sniper < 0.4
  - Location-quality: ≥ 75% of fires at VA edges (by construction if gated correctly)

AGENT NOTES:

TORO: High-conviction scalp with Pythia gate. A- grade is honest. The two-bar pattern is one of the simplest high-quality reversal triggers in Linda's toolkit — low computational cost, low cognitive load. Fits B3 scalping profile well.

URSA: Two concerns. (1) Frequency risk — two-bar patterns at VA edges are rare. If backtest shows <20 trades per 6 months, the strategy is statistically underpowered regardless of win rate. (2) Overlap with Scout-Sniper is not resolved — both are intraday reversal-oriented. Requires explicit non-overlap check in backtest or I demote to ELEVATE on Scout-Sniper.

PYTHAGORAS: Mechanics very clean. Bar-1 closes in bottom 20% of its range; Bar-2 opens in top 80% of Bar-1 range. Stop: below Bar-1 low (longs). Target: opposite extreme or next structural level via PYTHIA. Unambiguous. Backtestable with trivial OHLCV.

PYTHIA: This is my strategy. The two-bar pattern is interesting on its own (B grade) but becomes A-grade ONLY with VAL/VAH proximity gate — and that gating must use prior-session developing VA at Bar-1 close time, not cumulative. I take point on spec'ing the gate logic for CC.

THALES: Less sector-dependent than Turtle Soup. Two-bar exhaustion at VA edges is relatively sector-agnostic — works on leaders and laggards similarly. Minor note: on B3 equity variant, prefer single-stock momentum leaders (higher-beta names) because the setup's R:R improves on stocks with wider ranges.

DAEDALUS: Short-duration play — 5m/15m scalp typically exits within 30-60 minutes. Options structure implications: this is a theta-hostile duration for long-premium. Prefer shares/futures for directional expression, or very short-dated (0-1 DTE) options if trading options — which Nick does. Flag for structure-selection: 0DTE debit spreads are cleanest fit because debit caps the theta exposure.

PIVOT SYNTHESIS: Clean ADD. Build B3 intraday variant first with PYTHIA-specced VAL/VAH gate mandatory in trigger definition. B2 daily variant secondary, only if B3 shows positive expectancy. Non-overlap test vs. Scout-Sniper is a hard gate — if correlation > 0.4, demote to ELEVATE on Scout-Sniper. DAEDALUS 0DTE structure note should appear in strategy documentation for future trade selection.
```

---

## 2.4 STRATEGY: The Anti

```
STRATEGY: The Anti (after 3-10 oscillator registers extreme reading, wait for shallow pullback 1-2 bars, enter on resumption)
DISPOSITION: ELEVATE (OVERRIDE of PIVOT's "Conditional ADD" proposal — treat as Holy Grail "shallow-pullback variant" config, not a separate scanner)
REPLACE TARGET: none directly — becomes a Holy Grail mode/config rather than standalone
GAP FILLED: Shallow-pullback continuation that Holy Grail's 20-EMA-touch requirement misses. The original Section 4.4 gap analysis identified this.
CORRELATION RISK:
  - Holy Grail: HIGH by design — both are trend-continuation at pullbacks. Treating Anti as Holy Grail variant RESOLVES the correlation risk by making them share infrastructure and deduplicate at signal time. This is the Olympus override vs. PIVOT's proposal.
  - Turtle Soup: LOW (breakout failure vs. trend continuation)
DATA DEPENDENCIES: 3-10 oscillator MUST BE LIVE FIRST (hard dependency). Then OHLCV. No additional.
GRADE (as Holy Grail variant): B+
GRADE (standalone — rejected path): B+ with HIGH correlation risk vs. Holy Grail
TIMEFRAME APPLICABILITY:
  B1: ⚠️   (weekly 3-10 divergences fire 4-8x/year — too low frequency; PYTHAGORAS demotion from 🔧)
  B2: ✅   (daily, fills shallow-pullback gap Holy Grail misses)
  B3 equity: ✅   (short-horizon momentum re-entry)
  B3 crypto: ✅   (native fit)
BUCKET PRIMARY ASSIGNMENT: B2/B3 (served as Holy Grail config expansion)
BACKTEST GATES:
  - As Holy Grail variant: distinct trigger conditions produce non-overlapping fires (<50% overlap with standard Holy Grail fires on same ticker same session)
  - Independent expectancy check: Anti-triggered Holy Grail fires must show expectancy ≥ standard Holy Grail fires (if lower, kill the variant — standard works, the shallow-pullback hypothesis is wrong)

AGENT NOTES:

TORO: Fills a real gap. Shallow momentum dips that don't quite tag the 20-EMA but re-ignite on 3-10 confirmation = fast continuation trades with tight stops. R:R is excellent when the pattern works. Override to Holy Grail variant makes sense — shares Holy Grail's infrastructure and benefits from its fix list.

URSA: This is the override I wanted. Standalone Anti + Holy Grail = high correlation, high bloat risk. Anti as a Holy Grail config is the right architecture: one codepath, two trigger modes, deduplicated at signal time. This is textbook ELEVATE-not-ADD discipline. Strong support for the override.

PYTHAGORAS: Mechanics require 3-10 live before this is implementable. Once 3-10 lands, Anti is a conditional branch inside holy_grail_scanner.py: if standard pullback (touch 20-EMA) → fire HOLY_GRAIL; elif shallow pullback + 3-10 extreme + 3-10 turn → fire HOLY_GRAIL_ANTI. Clean branching, minimal code duplication. Deduplication at signal layer: on any bar where both triggers fire, prefer the standard (HOLY_GRAIL) unless backtest shows Anti-mode has higher expectancy.

PYTHIA: Intraday fit is strong. The Anti pattern on 15m bars during session initiative (not chop) fires rarely but with high expectancy. In chop sessions, suppress — location-quality multiplier will handle this automatically once built.

THALES: Works best in concentrated leadership regimes where trends have persistence. In rotation regimes, the Anti pattern more often traps — the "shallow pullback" becomes the start of a larger reversal. Apply URSA's 0.75x size penalty in rotation regime.

DAEDALUS: Short-duration momentum continuation = call debit spread or long call preferred (on long side), mirror on shorts. If 3-10 extreme reading is deep enough, short-dated options have IV support that rewards directional moves. 0-1 DTE on leaders, 1-2 DTE on mid-caps.

PIVOT SYNTHESIS: Override accepted. The Anti becomes Holy Grail shallow-pullback variant, not a separate scanner. This cleanly resolves correlation risk AND keeps net strategy count down. Implementation: wait for 3-10 live, then extend holy_grail_scanner.py with Anti branch + dedup logic. Backtest the variant separately before enabling live. URSA's endorsement of the override is decisive here — this is exactly the anti-bloat discipline the framework was designed for.
```

---

## 2.5 STRATEGY: News Reversal

```
STRATEGY: News Reversal (gap-and-fade: post-news gap, wait 30min, look for failure at key level, fade back toward prior close)
DISPOSITION: ADD (Phase 3, DAEDALUS-led design)
REPLACE TARGET: none
GAP FILLED: No native gap-fade detector. Opening-drive specialists currently handled only via general scanners.
CORRELATION RISK:
  - sell_the_rip_scanner: MODERATE (both are bearish at resistance; news-triggered context differs but backtest must confirm non-overlap)
  - exhaustion.py: LOW (different trigger; could fire sympathetically during news events)
  - Scout-Sniper: LOW-MODERATE (Scout is precision-entry; news-triggered context differs)
DATA DEPENDENCIES:
  - News event tagging: UW news endpoints (live) + earnings calendar. Historical depth per backtest brief Section 3.2: UNKNOWN — Titans must verify UW news historical availability before retrospective backtest; otherwise forward-test only.
  - OHLCV for gap detection and 30min rule
  - IV data for structure selection (DAEDALUS leads)
GRADE (vanilla): B
GRADE (with DAEDALUS IV crush integration): A-
GRADE (flow-augmented + IV): A-
TIMEFRAME APPLICABILITY:
  B1: ❌   — event-driven, not long-horizon
  B2: 🔧   — works only when event coincides with daily chart setup; low frequency
  B3 equity: ✅   — canonical opening-drive fade at 15m/30m
  B3 crypto: ⚠️   — crypto news taxonomy differs (Twitter/X, listings, macro); OLYMPUS requires separate DAEDALUS design pass for crypto variant
BUCKET PRIMARY ASSIGNMENT: B3
BACKTEST GATES:
  - Win rate ≥ 65% on news-tagged setups
  - ≥ 30 trades per year (frequency check — News Reversal will fire low frequency by nature)
  - IV crush capture: average IV reduction from entry to exit ≥ 20% (the edge is IV crush, not pure directional move)
  - Sector segmentation: separate expectancy tracking for mega-cap options-driven names vs. mid-cap secondaries
  - Correlation with sell_the_rip < 0.4

AGENT NOTES:

TORO: Real edge exists here, but frequency is low by nature. The best news reversals happen on earnings misreacts and macro surprises — 30-50 high-quality setups per year across the universe. Not a volume strategy; a quality strategy. Phase 3 placement is correct.

URSA: Most skeptical candidate. News Reversal is where retail traders die — buying dips into downtrending-on-news names that keep downtrending. The 30-minute waiting rule helps but does not eliminate the risk. Three additional URSA gates: (1) require fade direction aligned with broader trend (not news-caused trend change), (2) require IV crush pattern consistent with post-event options compression, (3) mandatory DAEDALUS structure selection — no naked puts/calls on earnings plays regardless of technical setup.

PYTHAGORAS: Mechanics depend heavily on news tagging quality. Where does the "news event" signal come from? UW news endpoints are the likely source — but news taxonomy (earnings, guidance, analyst action, M&A rumor, regulatory) differs in reversion behavior. Each category needs separate expectancy tracking. Implementation is not trivial — news classification is a substantive upstream task, not something to hand-wave.

PYTHIA: Opening drive + VAH/VAL = strong trigger. News gaps frequently fail at the prior session's VAH (in gap-ups) or VAL (in gap-downs). The 30-minute rule approximates "let the initial auction complete." If the initial auction (first 30-45min) doesn't break the VA edge in the direction of the news, fade is high-quality.

THALES: SECTOR-CRITICAL. Mega-cap options-driven names (NVDA, TSLA, AAPL, META, AMZN) have gap-fade dynamics dominated by dealer hedging flows (DAEDALUS can speak to this). Mid-cap secondaries (say, small-cap biotech after FDA decision) have gap-fade dynamics dominated by float absorption and news interpretation lag. These are structurally different trades — must segment at design time. Joint THALES-DAEDALUS design pass required.

DAEDALUS: This is my strategy to own. The edge is IV crush timing, not pure directional fade. Post-earnings IV crush compresses call AND put premiums — naked directional option buys are disadvantaged even when you're right on direction. Structure selection: bearish call debit spread (for gap-up fade) or bullish put debit spread (for gap-down fade) — limits IV-crush exposure and captures directional move. Mega-cap options-driven names: dealer GEX positioning often creates the fade target itself — check for gamma wall at prior-close or VAH/VAL levels. Crypto variant is qualitatively different because crypto news doesn't produce the same IV crush pattern (no quarterly earnings cycle); design separately.

PIVOT SYNTHESIS: Phase 3 ADD. DAEDALUS + THALES joint design pass required before CC brief. Don't attempt before Phase 1 (Holy Grail fixes, 3-10) and Phase 2 (Turtle Soup, 80-20) are live and validated. News classification upstream work is substantial — may warrant its own Titans brief. URSA's three additional gates are mandatory pre-build. Crypto variant parked for later (requires separate DAEDALUS design per PYTHIA's crypto-news-taxonomy concern).
```

---

# PASS 3 — SECTION 6.1 HOLY GRAIL FIX LIST COMPLETENESS

Section 6.1 of the evaluation doc lists 8 current failures for the 1H server-side Holy Grail. Each agent checks the list from their lens — is anything missing?

**Original 8 failures (from Section 6.1):**
1. Fixed 2R target ❌
2. No session filter ❌
3. No VIX floor (<15) or ceiling (>30) skip ❌
4. No pullback sequence tracking (1st vs 2nd vs 3rd) ❌
5. No EMA slope confirmation ❌
6. No HH/HL structure check ❌
7. No 3-10 oscillator ❌
8. Asset class: EQUITY only ❌

**Agent additions:**

- **TORO:** Add opportunistic fire on VIX regime transition — first valid Holy Grail setup after VIX drops back below 20 from above is historically higher-expectancy than steady-state fires. Low cost to add.
- **URSA:** Add ticker-level circuit breaker — skip the next Holy Grail fire on any ticker that had 2 consecutive losing Holy Grail signals in the prior 10 trading days. Cheap protection against strategies that stop working on specific names (regime change that the macro filters miss).
- **PYTHAGORAS:** Current stop = prev-bar low/high. In very tight or very wide bars, this is structurally wrong. Add ATR-based alternative: stop = MAX(prev-bar low, entry - 1.5×ATR(14)). Preserves defined-R math while protecting against bar-size anomalies.
- **PYTHIA:** Add VA-relative trigger context — tag every Holy Grail signal with "inside VA / at VA edge / outside VA." Signals outside VA (extension) are typically higher-expectancy; signals mid-VA (chop) often fail. This becomes a scoring input downstream.
- **THALES:** Add sector-rotation tag at trigger time. Trivial lookup against sector_rs scanner output. Integrates with framework amendment 7 (sector-regime specification).
- **DAEDALUS:** Add IV rank context to signal payload. Not a filter (don't skip based on IV) — a structure-selection hint for downstream options logic. IV rank >80 → debit spread preferred; IV rank <30 → long option acceptable.

**Consolidated fix list priority (Olympus consensus):**

Tier 1 (trivial, high-value, build in Phase 1 alongside 3-10):
- #3 VIX regime gate (skip <15/>30) — already has `iv_regime` bias filter, just call it
- #7 3-10 oscillator as RSI replacement (built separately, wired into Holy Grail config)
- THALES sector-rotation tag

Tier 2 (moderate, high-value):
- #2 session filter (config-gated; off for 1H, on for future 15m variant)
- #5 EMA slope confirmation
- #6 HH/HL structure check
- #8 Parameterize asset_class for crypto B3 variant
- PYTHIA VA-relative context tag
- PYTHAGORAS ATR-alternative stop

Tier 3 (harder, high-value):
- #1 Scale exit: 50% at 1R, trail remainder (changes exit architecture — requires pipeline support)
- #4 Pullback sequence tracking (1st vs 2nd vs 3rd pullback — needs ADX-ignition event memory)
- URSA ticker-level circuit breaker

Tier 4 (nice-to-have):
- TORO VIX regime transition opportunistic fire
- DAEDALUS IV rank context (payload-only addition, no filter change)

**Agent consensus on fix list completeness:** ORIGINAL LIST IS INCOMPLETE. 6 additions recommended. Nothing critical is missing from the original 8, but the additions materially improve signal quality — especially PYTHIA's VA-context tag (enables retrospective quality analysis even before backtest module lands).

---

# PASS 4 — 15m HOLY GRAIL VARIANT IMPLICATIONS

Nick reports a 15m Holy Grail variant is live; grep couldn't locate a separate Python file. Likely a TradingView webhook alert routing through `backend/webhooks/tradingview.py`. CC audit Section 2.1-B will confirm. Assume it exists for now; agent implications:

- **TORO:** Amplifies every critique. 15m is true intraday; session filter becomes critical (the 1H variant can skate without one, the 15m cannot). Fixed-2R on 15m is structurally expensive — intraday bars have much higher noise-to-signal ratio than 1H.
- **URSA:** If it duplicates 1H flaws, fix scope doubles. If it's a TV webhook that inherits downstream pipeline logic, fix is cheaper — just upgrade the pipeline. This is a material scope question for the CC audit to answer. No build on 15m fixes until audit confirms architecture.
- **PYTHAGORAS:** On 15m bars, ADX is less stable than on 1H. Threshold may need to be 30 (not 25) for 15m. EMA slope becomes more important (the 20-EMA on 15m is noisier). All fix-list items apply with higher urgency.
- **PYTHIA:** 15m aligns better with intraday VA rotation than 1H does. VA-relative context tag (proposed as fix list addition) matters MORE on 15m than on 1H. 15m Holy Grail firing at VA edge is a genuinely A-grade setup; firing mid-VA is near-random on that timeframe.
- **THALES:** 15m on high-beta single-stock names (QQQ/TQQQ/leaders) is where sector-rotation edge pays off. Sector tag at trigger time especially important for 15m because sector flips happen faster than 1H bars refresh.
- **DAEDALUS:** 15m = shorter-duration options plays. 0DTE to 2DTE. Theta dominates at this duration; structure selection must emphasize debit spreads over naked long options. IV crush on 0DTE around key levels is its own dynamic — requires gamma-wall awareness.

**Consensus:** If 15m exists, fix priority ELEVATES for items #2 (session filter), #5 (EMA slope), and PYTHAGORAS's ATR stop alternative. CC audit output determines scope. Hold all 15m-specific fixes until audit lands.

---

# PASS 5 — SYSTEM-LEVEL SUMMARY (per Section 8 format)

```
SIGNAL HYGIENE FRAMEWORK: AGREED WITH AMENDMENTS
Amendments adopted (Section 1.X of this review):
  1. Derivatives factors = separate cap of 2, additive to cash 3-factor cap
  2. 4+ factor override path — requires written orthogonality justification + Sharpe > 1.0 backtest bar
  3. One-in-one-out MANDATORY for ADDs; deprecations bankable
  4. Filter subtractiveness measurable: ≥30% signal count reduction / week while holding expectancy
  5. ADD classifications PROVISIONAL pending backtest module; shadow-mode interim acceptable
  6. Location-quality multiplier: VA edge +0.5 grade / mid-VA -0.5 grade (prior-session developing VA only)
  7. Sector-rotation regime specification required for all ADDs; 0.75x size penalty for regime mismatch

CONFLUENCE CAP (3 CASH FACTORS): AGREED, with derivatives extension (cap of 2 derivatives factors additive)

`wh_reversal` 4-FACTOR REVIEW:
  Current stack: WH-ACCUMULATION + 5-day return + VAL proximity + flow sentiment
  Analysis: Under the new framework, VAL proximity is absorbed into PYTHIA's location-quality multiplier (not a separate factor — it's a grade modifier). That reduces wh_reversal to effectively 3 cash factors: WH-ACCUMULATION + 5-day return + flow sentiment.
  CONCLUSION: wh_reversal does NOT violate the amended cap. No simplification required. Grandfather confirmed; rule compliance achieved via framework amendment 6 absorbing VAL proximity as a multiplier rather than a counting factor.

STRATEGIES PROPOSED FOR DEPRECATION:
  - None forced in this review.
  - AUDIT-GATED (pending CC): hunter.py (purpose unknown; if duplicate of any existing scanner → deprecate). ursa_taurus.py (purpose unknown; requires same audit treatment). BANKED against future ADDs once resolved.
  - NOT DEPRECATED: Momentum Pinball (never added; rejection doesn't count as deprecation credit).

NET STRATEGY COUNT AFTER ALL CHANGES:
  Current signal-generating detectors per Section 4 (excluding filters/deprecated): ~13-15 depending on classification (sector_rs borderline, hunter/ursa_taurus unknown)
  Additions: +3 scanners (Turtle Soup, 80-20, News Reversal), +1 overlay (3-10), +1 Holy Grail config variant (The Anti)
  Overlay does not count toward strategy budget; The Anti as Holy Grail variant does not count as new scanner.
  Net delta: +3 scanners
  Rule check: "≤ current + 3" — COMPLIANT at exact limit. No further ADDs without a deprecation.
```

---

# PASS 6 — THREE OPEN QUESTIONS (Section 9)

**Q1: Read sell_the_rip_scanner.py + hunter.py manually now, or let CC audit surface?**

Nick's recommendation: let CC audit surface.

**Olympus disposition: CONCUR WITH AMPLIFICATION.**

- Let CC audit (per holy-grail-audit-brief Section 2.3) resolve sell_the_rip's failed-breakout logic.
- **AMPLIFY:** hunter.py is flagged "Unknown without deeper read" in Section 4.2. This is higher priority than Nick implied — it's an unknown signal generator in production. Audit scope should explicitly classify hunter's trigger logic. If hunter duplicates anything (Scout-Sniper, Hub-Sniper, or another existing scanner), that's a BANKED DEPRECATION under framework amendment 3.
- URSA additional: same treatment for ursa_taurus.py (strategy file, purpose unclear). Should also be in audit scope.

**Q2: Crypto B3 volatility proxy — BTC realized vol (HV-30) as default?**

Nick's recommendation: BTC HV-30 as default, simplest, no new data dependency.

**Olympus disposition: PARTIAL OVERRIDE.**

- HV-30 is fine as the REGIME GATE proxy (equivalent of VIX floor/ceiling logic). No additional data dependency — OHLCV-derivable from existing bars. Approved for current use.
- HOWEVER — for IV-sensitive strategies (News Reversal crypto variant, any future crypto options strategy), HV-30 is insufficient because it measures realized historical vol, not forward-implied vol. Those need Deribit DVOL.
- **OLYMPUS RULE:** HV-30 for regime gating (Holy Grail crypto variant, Turtle Soup crypto variant, 80-20 crypto variant). DVOL required BEFORE any crypto News Reversal or crypto options strategy is built. Defer DVOL integration work until that trigger fires — don't pre-build.
- DAEDALUS monitors for DVOL trigger; flags when needed.

**Q3: wh_reversal 4-factor — grandfather or simplify?**

Nick's recommendation: grandfather existing, enforce cap on new builds only.

**Olympus disposition: CONCUR with REFRAMING.**

- Under framework amendment 6 (location-quality multiplier), VAL proximity in wh_reversal is no longer a "factor" — it's a grade modifier. Effective count drops from 4 to 3. No actual simplification needed.
- wh_reversal complies with amended framework. Grandfather confirmed.
- **NEW CHECK:** add wh_reversal to the Q3 2026 Olympus review cadence regardless of performance grade, to verify the reframing holds up in production. If VAL proximity behaves as a factor and not a multiplier (which would happen if signals frequently fire at VAL without the location-quality distinction producing different win rates), revisit.

---

# PASS 7 — PIVOT SYNTHESIS

The framework as authored is sound. The seven amendments adopted this review close the edge cases — most importantly (a) separating derivatives factor accounting so DAEDALUS's structural inputs don't get suppressed by the cash cap, (b) formalizing PYTHIA's location-quality multiplier so VA-edge setups get the grade premium they deserve, and (c) making one-in-one-out mandatory so future ADDs can't happen without explicit deprecation accounting. These three amendments, taken together, convert "don't add noise" from a principle to a mechanism.

The Raschke candidates come out cleaner than PIVOT's v2 proposal. Three ADDs (Turtle Soup, 80-20, News Reversal), one ELEVATE (3-10 into Holy Grail's RSI slot, with overlay availability system-wide), and one ELEVATE-not-ADD override on The Anti. This is the disciplined answer. PIVOT's v2 had The Anti as a separate ADD, which would have stacked correlation risk against Holy Grail and pushed net new scanners to +4 (over the "≤ current + 3" rule). Olympus's override fixes both.

The single highest-leverage item in the entire review is 3-10 Oscillator. Build it first. It unlocks the Holy Grail RSI replacement (Tier 1 fix), unlocks The Anti as a Holy Grail variant, feeds into Turtle Soup's divergence filter, gives THALES a sector-rotation leading signal via sector-ETF 3-10, and costs almost nothing (trivial pandas math, no new data dependencies). Do not build Raschke strategies in any other order.

Three items are HARD GATES on downstream work:

1. **CC audit of holy-grail-audit-brief Section 2.3** must complete before Turtle Soup build. If it reveals sell_the_rip or hunter already implements failed-breakout logic, Turtle Soup demotes to ELEVATE.
2. **Backtest module (Titans brief)** must be live before Phase 2/3 strategies go past shadow-mode. URSA's PROVISIONAL rule is binding.
3. **UW historical data depth question** (per backtest brief Section 3.2) must be resolved before flow-augmented variants can be retrospectively validated. If historical depth < 6 months, flow-augmentation runs forward-test only; that is acceptable but changes the confidence timeline for A-grade flow-augmented trades.

The 15m Holy Grail variant is the biggest unknown in this review. If it exists as an independent Python module with duplicated logic, the fix scope doubles. If it's a TV webhook inheriting pipeline logic, the fix is contained. The CC audit Section 2.1-B resolves this. No downstream decisions until it does.

System-level framework compliance: the proposed net addition of +3 scanners puts us EXACTLY at the "≤ current + 3" limit. Any future Raschke Phase 4 or beyond (e.g., B1 long-term Turtle Soup variant on 50/100-day high failures, or a crypto-specific News Reversal) requires a deprecation first. hunter.py and ursa_taurus.py are the banked-deprecation candidates pending audit classification. This is healthy — the discipline is tight, not artificial.

**Build order (Olympus-endorsed):**

Phase 1 (1-2 weeks, gated only on CC audit completion):
1. 3-10 Oscillator module (overlay — shared dependency for all downstream)
2. Holy Grail fix list Tier 1: VIX regime gate (call existing `iv_regime`), 3-10 as RSI replacement in shadow mode, sector-rotation tag at trigger time

Phase 2 (2-3 weeks, gated on backtest module live + Phase 1 validation):
3. Turtle Soup (B2 daily vanilla → flow-augmented → B3 intraday)
4. 80-20 Reversals (B3 equity with PYTHIA VAL/VAH gate mandatory)
5. Holy Grail fix list Tier 2 (session filter, EMA slope, HH/HL check, asset_class parameterization, VA-context tag, ATR alternative stop)

Phase 3 (conditional, gated on Phase 1+2 live expectancy positive):
6. The Anti as Holy Grail config branch (requires 3-10 live + overlap backtest < 50%)
7. News Reversal (DAEDALUS + THALES joint design; requires UW news classification upstream; Phase 3 lowest priority)
8. Holy Grail fix list Tier 3 (scale exit, pullback sequence tracking, ticker circuit breaker)

Phase 4 (closes anti-bloat loop):
9. Run backtest on hunter.py and ursa_taurus.py outputs to classify overlap with other scanners; deprecate if redundant
10. Review crypto variants (Turtle Soup, 80-20, Holy Grail) for live validation
11. Review wh_reversal against new framework at Q3 2026 cycle

---

# PASS 8 — NEXT ACTIONS FOR NICK

1. **Save this review** to `docs/strategy-reviews/raschke/olympus-review-2026-04-22.md` (per handoff Step 4 action 1).

2. **Hand CC the audit brief** (`holy-grail-audit-brief.md`). Audit scope expansion recommended: explicitly add `hunter.py` and `ursa_taurus.py` to Section 2.3 overlap check (currently only sell_the_rip is named).

3. **Hold Titans backtest brief** (`backtest-module-brief.md`) for review now — CC audit running in parallel doesn't block Titans. Start Titans Pass 1 on backtest module today or tomorrow; by the time CC audit returns, you'll have Titans's response and can move to CC brief for Phase 1 builds.

4. **Framework amendments** from Pass 1 (7 items) need to be recorded in `PROJECT_RULES.md` or equivalent so CC inherits them in future briefs. This is the single most important follow-up after the build plan itself — otherwise future reviews repeat this discussion.

5. **Decision point for Nick:** does the ELEVATE-override on The Anti (treat as Holy Grail variant, not separate scanner) work for your mental model? Olympus endorses it unanimously, but you own the architecture decision. If you prefer Anti as a separate scanner with explicit correlation management, flag in reply and Olympus will revisit — but that path requires a deprecation to stay under +3 cap.

6. **Decision point for Nick:** the Q2 override (HV-30 for regime gating, DVOL deferred to IV-sensitive strategies) delays any crypto News Reversal / crypto options work until DVOL is integrated. If you want crypto News Reversal earlier, DVOL integration becomes a Phase 2 dependency rather than deferred. Low cost to add now if it's on your near-term roadmap.

---

**End of Olympus deep review.**

---

## Pass 9 — VIX Threshold Recalibration (2026-04-24)

**Context:** iv_regime Tier 1 gate shipped 2026-04-23 (PR #15, commit `57ea60d`) with `VIX_REGIME_LOW_THRESHOLD = 15.0` and `VIX_REGIME_HIGH_THRESHOLD = 30.0`. Nick surfaced an empirical concern Day-0: the S&P had a ~10% drawdown in the last 2 months where VIX barely exceeded 30 at any point. If 30 is the "chaotic" threshold but meaningful corrections don't breach it, the gate is anchored to stale volatility structure (pre-2023 era where VIX routinely spiked above 40 during selloffs).

Ran full Olympus double-pass review in separate chat 2026-04-24. Findings below.

### PIVOT Synthesis

**Finding:** Nick's hypothesis is empirically confirmed. VIX ≥ 30 has become a crisis-regime marker in the post-2023 structural vol regime, not a "tape is chaotic" marker. Calibration drift is real and non-trivial; current thresholds mean the gate is functionally inert during the drawdowns it was designed to flag.

**Consensus recommendation:** Replace current absolute thresholds with a percentile-based primary signal + absolute guardrails, using a 252-trading-day lookback, and treat the gate asymmetrically (high-VIX suppression does most of the real work; low-VIX is a soft floor for reversal-risk regimes).

**Open questions parked for future passes:**
- VX1–VX2 backwardation as v2 secondary signal (DAEDALUS)
- Whether low-VIX suppression should be dropped entirely for HG (TORO)
- Whether realized-vs-implied vol spread should replace absolute VIX as the cleaner input (DAEDALUS, weakly held)

Shadow mode remains mandatory until dual-logging validates.


### ATHENA Lock — Implementation Brief

**Status:** Recalibration approved. Build as shadow-mode update; no promotion to hard-skip in this change.

**Changes to ship:**

1. **Add to config:**

```python
VIX_REGIME_USE_PERCENTILE        = True      # feature flag
VIX_REGIME_PERCENTILE_LOW        = 5.0       # 5th percentile
VIX_REGIME_PERCENTILE_HIGH       = 90.0      # 90th percentile
VIX_REGIME_PERCENTILE_LOOKBACK   = 252       # trading days
VIX_REGIME_ABS_FLOOR             = 11.0      # always-allow override
VIX_REGIME_ABS_CEILING           = 35.0      # always-suppress override
VIX_REGIME_WARMUP_FALLBACK_LOW   = 14.0      # used if <252 days data
VIX_REGIME_WARMUP_FALLBACK_HIGH  = 28.0      # used if <252 days data
```

Keep existing `VIX_REGIME_LOW_THRESHOLD = 15.0` and `VIX_REGIME_HIGH_THRESHOLD = 30.0` for backward-compat/rollback.

2. **Gate decision logic (shadow mode):**
   - If `VIX_REGIME_USE_PERCENTILE is False` → use legacy absolute thresholds (current behavior).
   - If `True` AND ≥252 days of VIX history in DB:
     - Suppress if `VIX_current < P5(252d)` OR `VIX_current > P90(252d)`
     - Override 1: `VIX_current < VIX_REGIME_ABS_FLOOR` → always suppress (abnormally compressed, reversal-risk zone)
     - Override 2: `VIX_current > VIX_REGIME_ABS_CEILING` → always suppress (crisis override)
   - If `True` AND <252 days of history → fall back to warmup absolute thresholds (14/28).

3. **Logging (REQUIRED — this is the validation data):**
   - For every HG signal, log BOTH: the legacy gate decision (30/15 absolute) AND the new gate decision (percentile + guardrails).
   - Schema addition in `committee_data`:
     - `iv_regime_legacy`: `{decision, threshold_used, vix_value}`
     - `iv_regime_v2`: `{decision, threshold_used, vix_value, p5, p90, lookback_days}`
     - `iv_regime_diverged: bool` — true if v2 and legacy disagree
   - Discord alert to `#zeus-ta-feed`: when `iv_regime_diverged = true`, include both decisions + VIX context. This is the review data.

4. **Promotion criteria (NOT in this ship):**
   - After 60 trading days of dual-logging, Olympus reviews divergence cases.
   - If v2 produces better outcome alignment (suppresses failed HG trades, permits successful ones at materially better rate), promote `VIX_REGIME_USE_PERCENTILE = True` as default and remove legacy.
   - If no meaningful improvement, revert.

5. **Not in scope (parked for v2):**
   - VX1–VX2 term structure cross-check (DAEDALUS)
   - IV-vs-RV spread signal
   - Dropping low-VIX suppression entirely for HG (TORO)
   - All re-open after 60-day validation.


**Data dependency:** Requires ≥252 days of VIX close history in DB. Verify before ship. If gap, backfill from FRED (VIXCLS series) or UW. Warmup fallback covers transition.

**Data dependency — empirical finding 2026-04-24:** DB query confirmed `factor_readings` currently has only ~37 trading days of VIX history (range 2026-02-27 to 2026-04-24). Well below the 252-day lookback requirement. Two options:

- **Option A (ship with warmup):** Deploy Pass 9 with `VIX_REGIME_USE_PERCENTILE=True`. Falls back to warmup thresholds (14/28) until DB accumulates 252 days (~9 more months). Warmup thresholds are already better than legacy (28 suppresses where legacy 30 did not), so this is a net improvement from day 1.
- **Option B (backfill first):** Pull VIX close history from FRED `VIXCLS` series (free API, covers back to 1990), backfill `factor_readings` with `source='fred_backfill'`, then ship Pass 9. Unlocks true percentile gate immediately. Estimated ~1-2 hours CC work (single REST endpoint, ~252 rows to write).

**Recommendation: Option B.** The backfill is small, the benefit is material (true percentile gate ships functional on day 1 instead of 9 months later), and FRED's VIXCLS is the canonical public VIX close series that this calibration was designed against. Option A is a valid fallback if FRED access has any friction.

**Rollback plan:** Flip `VIX_REGIME_USE_PERCENTILE = False`. Zero code change needed.

**Testing:** Unit tests on percentile calculation with synthetic series (low-vol, high-vol, regime-shift). Integration test: replay March 2026 drawdown through gate with dual logging, confirm v2 suppresses HG at VIX 26–28 where legacy did not.

**Review interval:** 30-day check-in on divergence rate. 60-day full promotion review.

### Sequencing Note (updated by Nick 2026-04-24)

Original Pass 9 output suggested this follows HG Tier 1 + smoke test. As of 2026-04-24 that stack is already complete: hunter removal ✅, 3-10 shadow mode ✅ (live since 2026-04-23), HG Tier 1 ✅ (PR #15 merged 2026-04-23). Pass 9 is now positioned as the immediate next iteration on the iv_regime gate rather than a future-stacked item.

**Next step:** CC brief authored referencing this Pass 9 lock. Branch name convention: `feature/hg-iv-regime-percentile-v2`.
