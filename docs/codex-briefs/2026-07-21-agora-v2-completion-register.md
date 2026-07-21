# AGORA v2 — COMPLETION REGISTER + OLYMPUS DASHBOARD PASS

**Authored:** 2026-07-21, coordination lane
**Companion to:** `2026-07-21-master-plan-vacation-safe-aug-4.md` (this fills in thread A, which HELIOS could not review without a defect list)
**Method:** code-verified against `v2.js` @ `10cf67e9` + live MCP reads. Nothing below is inferred from memory.
**Trip window updated:** depart 2026-08-04, return **2026-08-15**. Light trading and market-watching possible; **no serious coding**.

---

## TASK 0 — FILING

```
cd /d C:\trading-hub
git fetch origin && git status
git mv 2026-07-21-agora-v2-completion-register.md docs\codex-briefs\
git add docs/codex-briefs/2026-07-21-agora-v2-completion-register.md
git commit -F C:\temp\commitmsg.txt
git push origin main
```

---

## PART 1 — ANSWERS (code-verified, not inferred)

### Q1. What are the "C" and "S" lenses under REGIME?

**Verified at `v2.js:219-222`.** They are two genuinely different instruments measuring two different things, deliberately shown side by side.

| | **C** | **S** |
|---|---|---|
| Gloss tag | `data-gloss="COMPOSITE"` | `data-gloss="STABLE"` |
| Endpoint | `/api/bias/composite` | `/api/stable/regime` |
| What it measures | 20-factor weighted directional bias | breadth — % of universe above its 50-day MA |
| Inputs | options flow, technicals, sector rotation, factor scores | daily bars across the Stable universe |
| Output | TORO MAJOR / TORO MINOR / NEUTRAL / URSA MINOR / URSA MAJOR | RISK-ON / NEUTRAL / RISK-OFF |
| Cadence | frequent intraday refresh | nightly recompute + intraday provisional overlay |
| Timeframe param | **yes** — `swing` / `daily` / `intraday` | **no** |

**Two things about C worth knowing:**

1. **The X/100 number is rescaled, not a percentage.** `to100()` at `v2.js:156` does `Math.round(((score + 1) / 2) * 100)`. The raw composite runs −1.0 to +1.0. So **50/100 = perfectly neutral (raw 0.0)**, 62/100 = raw +0.24, 38/100 = raw −0.24. If you have been reading it as "62% bullish," it is not that — it is "mildly bullish, about a quarter of the way up the scale."
2. **The `⚠ divergence` chip fires when the two lenses disagree** (`v2.js:196-198`). C is directional if ≥55 or ≤45 on the rescaled scale (raw ±0.10); S is directional if RISK-ON or RISK-OFF. When both are directional and they point opposite ways, the warning renders.

**Are they calculated correctly? Two separate answers.**

- **The math is correct.** The rescale is right, the threshold logic is right, the divergence comparison is right.
- **The comparison is not clock-safe, and this is a real defect.** Live read at time of writing: `metrics_date: 2026-07-20` (yesterday), `data_age_seconds: 22657` (**6.3 hours**), `anchor: "provisional"`. The C lens refreshes on a much tighter cadence. So the band can flag "⚠ divergence" simply because **one lens is a day behind the other**, not because the market is actually diverging. There is no age guard on the comparison. **DEF-REGIME-CLOCK below.**

### Q2. Is TIDE daily only? Can it be toggled?

**TIDE is a current-session cumulative options-flow read. It is not daily-bar-based, and it is not toggleable — at any layer.**

Verified: `hub_get_board_state` takes **zero parameters**; `/api/board/tide` takes zero parameters; the tool contract states it is "read-only from an existing UW cache — this tool never triggers a new UW request."

Live payload right now:

```
net_call_premium   $648,592,694
net_put_premium   -$370,854,793
net_volume          1,379,000
net_premium_delta  $1,019,447,487
direction          BULLISH
scope              market
staleness          158s
```

**What it actually tells you:** across the whole market today, net premium is running about **$1.02B toward calls**. It is a same-session flow tally that resets each morning. It answers "which way is money leaning *today*," and nothing longer.

**Can it be made multi-timeframe?** Not as a toggle — the cache holds a **current snapshot, not a time series**, so there is no history to select a window from. Multi-timeframe TIDE means persisting daily tide snapshots and then reading back over them. That is a real build (new table + writer + a windowed read), roughly the same shape as `uw_daily_burn`. It is genuinely useful — a 5-day tide trend would tell you whether today's bullish flow is a continuation or a one-day reversal — but it is a build, not a setting, and ATLAS needs to size the UW call cost against the 17K/18K watchdog thresholds first.

**Recommendation: not before Aug 4.** Log it as a named backlog item. What *is* cheap and worth doing now is labeling the tile so it reads as "today" rather than ambiguously timeless.

### Q3. What is the Kill Switch? Is it working? What is it telling me?

**What it is:** a market-risk circuit breaker. When it arms, it overrides the rest of the system — it caps or floors the bias (`bias_cap` / `bias_floor`) and applies a `scoring_modifier` to signal scores. PIVOT is required to check `kill_switch.active` **before** synthesizing any final recommendation; an armed breaker outranks whatever else the signals say.

**Three states** (`v2.js:207-212`):

| Display | Condition | Meaning |
|---|---|---|
| **CLEAR** | `active: false` | normal operation, no override |
| **ARMED** | `active: true`, `pending_reset: false` | breaker live, bias capped/floored, tile pulses vermilion |
| **PENDING** | `active: true`, `pending_reset: true` | breaker fired, waiting on reset |

**What it is telling you right now:** `active: false`, `scoring_modifier: 1.0`, `trigger: null` → **CLEAR / normal**. Nothing is being overridden.

**Is it working?** Honest split answer, and I am not going to overstate either half:

- **The read path is verified working.** It returns correct structured state and renders it correctly.
- **The arm path is unverified.** I have not confirmed that the breaker has ever actually fired, nor read the arming conditions. A `scoring_modifier` of 1.0 and a null trigger are exactly what you would see both from a healthy idle breaker *and* from one that can never fire.

Those are indistinguishable from the outside — which is the same fake-healthy shape as the `rs_10d` zeros, the dead regime writer, and the never-scheduled tape-health collector. **One verification closes it: read the arming logic, confirm the trigger conditions are reachable, and force one arm/reset cycle in a controlled window.** Given that you are about to spend 11 days unable to fix code, an unverified circuit breaker is the single least comfortable item on this list.

### Q4. Themes showing stale or misorganized data

**Partly explained, partly a real defect, and the real part is worse than you thought.**

**The staleness is mostly by design and mostly mislabeled.** Live: `metrics_date: 2026-07-20`, `as_of: 2026-07-21T13:45:42Z`, `data_age_seconds: 22657`, `anchor: "provisional"`, `degraded: false`, `flatline: false`. The Stable Engine recomputes nightly from daily bars, then an intraday overlay flips the anchor to `provisional`. So the theme scores are genuinely built on **yesterday's** closes with a live price overlay on top. That is the intended architecture — but the band does not say so, which is why it reads as "stale" rather than "end-of-day plus overlay."

**The real defect: Robotics is not just wrong, it is displacing real signal.**

`themeChips(regime.dominant, 'dom', 2)` renders **only the top 2** dominant themes. Live:

| Rank | Theme | Score | On the band? |
|---|---|---|---|
| 1 | Robotics | **100.0 — fabricated (LAZR)** | ✅ shown |
| 2 | Software Infrastructure | 87.4 | ✅ shown |
| 3 | **Energy** | **83.4 — real** | ❌ **pushed off** |

And `themeChips()` (`v2.js:177-181`) has **no `data_quality_warnings` handling whatsoever.** The MCP layer warns committee agents. The dashboard renders "Robotics 100" as a clean chip with no flag.

So: a delisted ticker is occupying one of two dominant slots and pushing **Energy** — the theme your book is most heavily long across XLE, GUSH, USO, and OBE — entirely off the regime band. This reclassifies the LAZR fix from "orphaned P3, cosmetic" to **a defect that actively hides your own thesis from you.**

**Also worth a question, not an assertion:** `breadth.total` reads **250**, against a documented ~690-ticker Stable universe. That may be a legitimate subset (tickers with complete 50-day history), or it may be a coverage gap that makes `pct_above_50dma` — and therefore the entire S-lens RISK-OFF label — a read on 36% of the universe. **ATLAS should confirm which before anyone trusts the S lens further.** Flagging, not diagnosing.

---

## PART 2 — AGORA v2 DEFECT + FEATURE REGISTER

Ordered by ratio of value to cost. HELIOS now has his list.

### Fix (defects)

| ID | Item | Size | Notes |
|---|---|---|---|
| **A-1** | **LAZR / Robotics upstream fix** — evict LAZR from `universe.csv` (691→690), quarantine + delete post-2026-04-07 garbage rows from `stable_daily_bars` / `stable_metrics` after export, full recompute. | M | Scoped-but-unbuilt since 7/10. Micro-brief already drafted. **Displacing Energy makes this urgent, not cosmetic.** |
| **A-2** | **Render `data_quality_warnings` on the band.** `themeChips()` ignores the field entirely. Minimum: strike-through or a ⚠ on any flagged theme. | S | Belt-and-braces for A-1 — protects against the *next* bad ticker too |
| **A-3** | **DEF-REGIME-CLOCK** — age-guard the C-vs-S divergence comparison. Suppress `⚠ divergence` (or mark it "stale-lens") when the two lenses' data ages differ beyond a threshold. | S | Currently can fire purely from clock skew |
| **A-4** | **Kill-switch arm-path verification** — read the arming logic, confirm triggers are reachable, force one controlled arm/reset. | S | **Do before departure.** Unverified breaker + 11 days of no-code-fixes is the worst combination on this list |
| **A-5** | **Stable universe coverage question** — confirm whether `breadth.total: 250` vs ~690 is intended. | S | Gates trust in the whole S lens |
| **A-6** | **Label the timeframe on every regime tile** — "Tide · today", "S · EOD +overlay (as of {metrics_date})", "C · {timeframe}". | S | Pure labeling. Removes the entire class of confusion that generated this question list |
| **A-7** | **Pythia v2.4 `loBinIdx` clamp** — wrap in `math.min(loBinIdx, numBins - 1)`. A bar whose low lands exactly at session high computes bucket 50 on a 50-element array. | S | Carries the coordinated secret rotation — see master plan W1-4 |

### Add (features Nick named)

| ID | Item | Size | Notes |
|---|---|---|---|
| **A-8** | **New H/L ticker popup** — clicking New Highs / New Lows shows the actual tickers. | **M** | ⚠️ **Backend work required.** The regime payload returns **counts only** (`new_high_20d: 13`, `new_low_52w: 4`) — no ticker lists. The Stable Engine must already know which tickers to count them, so this is "return what you already computed," but it is a new field on the payload, not a frontend-only change |
| **A-9** | **Kairos ticker → chart popup** — wire Kairos cards into the existing chart-popup handler other dashboard tickers already use. | **S** | Frontend only, reuses existing behavior. Cheapest win on the list |
| **A-10** | **Sector Divergence expansion** — see Part 4 | M–L | Phased; Tier 1 is nearly free |

---

## PART 3 — OLYMPUS DOUBLE PASS ON THE DASHBOARD

*Question put to the committee: beyond Nick's list, what is missing from Agora before it can be called done?*

### PASS 1 — independent

**PYTHIA (market profile / auction).**
There are **no market-profile levels on the dashboard at all.** POC, VAH, VAL for SPY/QQQ/IWM exist in the hub, feed every committee pass, and have zero Agora surface. This is my single largest gap and it is not on Nick's list. A trader looking at the band can see *what regime* we are in but not *where value is* — and "where is price relative to value" is the most decision-relevant thing on any given morning. Second point: that feed just returned from a **14-day outage** that went undetected because the alarm checked a global timestamp. The per-name watchdog now exists, but there is still no **per-ticker freshness indicator on the dashboard itself.** Nick should be able to see at a glance that SPY's profile is current without trusting that an alarm would have told him.

**DAEDALUS (options structure / Greeks).**
**No IV regime anywhere on this dashboard.** IV rank or percentile is the single most actionable options input there is — it determines whether he should be *buying* or *selling* premium, which is a more consequential decision than direction. Its absence is why the NBIS pass had to discover IV rank 100/100 through a separate lookup rather than seeing it on screen. Second gap: **no expiry ladder.** Twenty-one open positions with expiries scattered across 7/31, 8/21, 9/18, 9/30, and 10/16, and nothing on the dashboard shows the calendar shape of that book. The 21-DTE rule cannot be applied to a book you cannot see the DTEs of.

**URSA (risk / bear case).**
**There is no risk surface on this dashboard.** Twenty-one open positions, $3,530 nominal at risk, and the band shows regime, themes, tide, breadth, and a kill switch — none of which is *his* exposure. The book is a single Iran-escalation thesis expressed eight different ways across energy, metals, credit, financials, and semis, and nothing on screen says so. The bias-alignment check (D.03) fires inside committee passes and nowhere else. If the dashboard is the thing he looks at every morning, then **concentration and thesis-clustering belong on it**, not buried in a committee output he has to request.

And bluntly: adding six modules three weeks before a trip is how the mockup gate gets skipped. I want it on record that I raised the gap *and* that I do not think most of it should ship before Aug 4.

**PYTHAGORAS (trend / structure).**
Both lenses report **state, never slope.** "RISK-OFF" and "NEUTRAL 52/100" tell you where things are, not which way they are moving — and at turns, the derivative matters more than the level. A composite grinding from 38 → 52 over four sessions is a completely different market from one that has sat at 52 all week, and the band renders them identically. The themes payload already carries a **1-day score delta** and the band does not render it. That is free directional information being discarded.

**THALES (macro / regime plausibility).**
Themes show score but not **duration.** A theme at 87 that has been dominant for three weeks is a crowded trade; the same 87 reached in three days is a rotation you can still get in front of. Same number, opposite trade. No macro calendar band either — FOMC, CPI, PPI, and OPEX all shape the week and none appear.

**TORO (bull case).**
The band answers "what is true now" and never "**what changed since yesterday.**" Every element is a level. Momentum is where the entries are. Give me deltas on the composite, on the themes, and on breadth, and the same six tiles become an opportunity surface instead of a status readout.

### PASS 2 — cross-examination

- **Broad agreement** that PYTHAGORAS's and TORO's point is the same point arriving from two directions — the band is a **state readout, not a change detector** — and that it is the cheapest high-value fix available, because the 1d delta is already in the payload.
- **DAEDALUS and URSA converge:** the expiry ladder and the risk surface are the same widget. One "book" tile carrying aggregate exposure, thesis clustering, and DTE distribution satisfies both lanes. Neither wants two tiles.
- **PYTHIA concedes sequencing to URSA:** the MP levels tile is her largest gap but it is a new module under the mockup gate, and the gate is already committed to S-6. She asks instead for the **per-ticker freshness indicator** as the pre-vacation slice — small, uses data already present, and closes the failure mode that actually bit (14 silent days), rather than the aesthetic gap.
- **THALES withdraws the macro calendar band** for this window on his own motion — Hermes alerts already cover a 10-day forward window and the Battlefield Brief covers the rest. Theme duration he keeps; it is one field.
- **URSA holds his objection to scope**, and it is the right one.

### PIVOT — synthesis

> **VERDICT: ship the deltas and the freshness indicator. Defer every new module.**
> **CONVICTION: HIGH.**

The committee named six real gaps and five of them are new modules. New modules go through HELIOS's mockup gate, and that gate is committed to S-6 through 7/31. Trying to run it twice produces two bad gates.

But two of the six are **not** new modules — they are fields already present in payloads the dashboard already fetches and simply does not render:

1. **1-day deltas** on composite, themes, and breadth (PYTHAGORAS + TORO, converged) — turns a status board into a change detector.
2. **Per-ticker MP freshness indicator** (PYTHIA, rescoped) — closes the exact failure mode that cost two weeks of silently-corrupted committee inputs.

Add **theme duration** (THALES, one field) and that is the whole pre-vacation dashboard scope. Everything else — MP levels tile, IV regime, book/risk tile, macro band — goes into the **Agora v3 module set**, post-vacation, behind one properly-run mockup gate.

**"Done" for Agora v2 means: no fabricated numbers on screen, every tile states its own timeframe, and the band shows change as well as state.** Not: every module the committee can imagine.

---

## PART 4 — SECTOR DIVERGENCE EXPANSION (Olympus recommendation)

**Framing:** the current module compares equity sectors to each other, which only ever answers "which sector is winning." The higher-value divergences are **cross-asset** — they answer "does the market believe its own price," which is where reversals come from.

**Cost note that drives the tiering:** `SPY / QQQ / IWM / SMH / UUP / XLK / XLU / HYG / TLT / RSP` are **already fetched** by `bias_scheduler`, and every Stable-universe ticker already has daily bars. So Tier 1 is a compute-and-render task with **zero new data integration.**

### Tier 1 — build first, no new data required

| Pair | Reads | Why it matters | Advocate |
|---|---|---|---|
| **HYG / SPY** | credit vs equity | Credit leads equity at turns. Spreads widening while equities hold is the classic pre-reversal tell. You are already short HYG — this instruments the thesis | THALES |
| **RSP / SPY** | equal-weight vs cap-weight | The cleanest narrow-leadership measure there is. Directly quantifies "36% above 50dma while the index sits near highs" | PYTHIA |
| **XLU / SPY** | defensives vs index | Utilities outperforming into an up-tape = risk-off underneath a calm surface. This is exactly the regime THALES called on 7/16 and it had no instrument | THALES |
| **VIX / VIX3M** | vol term structure | Backwardation = live stress. Single best short-horizon reversal tell on the list, and it doubles as DAEDALUS's premium buy/sell signal | URSA + DAEDALUS |

### Tier 2 — high value, small additions

| Pair | Reads | Why |
|---|---|---|
| **Copper / Gold** | growth vs fear | The classic reflation-vs-risk-off ratio. Leads cyclical rotation |
| **SMH / SPY** | semis vs index | Semis lead the cycle; instruments your existing semi-short thesis |
| **Crude / XLE** | commodity vs its equity complex | Divergence distinguishes a supply shock the equities disbelieve from a genuine energy re-rating. **Directly relevant to your largest thesis cluster** |
| **GLD / real yields** | gold vs TIP or ^TNX | Gold rising *with* real yields means something non-monetary is driving it — geopolitics, central-bank buying. Your Iran thesis, instrumented |

### Tier 3 — crypto, and the bridge to Stater Swap

| Pair | Reads | Why |
|---|---|---|
| **BTC / QQQ** | crypto vs high-beta equity | BTC is the cleanest liquidity proxy available. Breaking down while QQQ holds = liquidity tightening ahead of equities |
| **BTC / Crypto Equities theme** | spot vs the equity complex | Equity complex leading spot = speculative froth; spot leading = real flows. You already track a Crypto Equities theme (currently 16.0, WEAK) |
| **Spot vs Perp CVD** | already built | S-3b already computes SPOT_LED / PERP_LED / MIXED for six symbols. Surfacing it in Agora as a divergence is nearly free and **architecturally connects Stater Swap to the main dashboard** |

**Recommended scope before Aug 4: Tier 1 only, and only if A-1 through A-9 land first.** Four ratio lines against data already in hand. Tiers 2 and 3 go to Agora v3 with the module set.

---

## PART 5 — PLAN DELTAS FROM NICK'S ANSWERS

### Trip window: 2026-08-04 → 2026-08-15 (11 days), light trading, no coding

**Good news, verified against the live book: nothing expires during the trip.** Expiries are 7/31 (×2), 8/21 (×3), 9/18 (×4), 9/30 (×2), 10/16 (×5), plus four stock positions with no expiry. The 8/21 batch lands **six days after you are back.** The only calendar action needed pre-departure is the two 7/31 positions, which expire before you leave anyway.

**This changes thread E's shape.** The original hardening pass assumed a fully unattended system. It is not — you will be watching and able to trade. What you *cannot* do is deploy a fix. So the governing constraint becomes:

> **Anything that can break must be recoverable without a code change.**

Concretely, the hardening thread re-prioritizes to:

1. **Config-driven controls over code-driven ones.** Every kill switch, gate flag, and threshold you might need to touch must be flippable from a phone — DB config row or Railway env var, not a source edit. Anything that would require a deploy to fix should be identified *now* and either made configurable or accepted as frozen for 11 days.
2. **Alert quality over alert suppression.** You are watching, so an alert-rate ceiling matters less than it would have. But a repeat of the CVD burst class still buries the signal you *would* have acted on.
3. **A-4 (kill-switch arm-path verification) is promoted to must-ship.** An unverified circuit breaker you cannot repair is the worst item on the board.
4. **Watchdog liveness sweep stays** — a dead watchdog and a healthy system are indistinguishable, and you will have no way to tell the difference from a phone.

### Abacus v2 — formally parked, with a named re-entry trigger

Deferred until **both** Agora v2 and Stater Swap are complete. Recording the trigger explicitly so it cannot quietly rot:

> **Abacus v2 re-enters the queue when: (a) Agora v2 register items A-1 through A-9 are closed, AND (b) Stater Swap S-6 has passed post-deploy screenshot comparison.** At that point ATHENA promotes it to top-of-queue and it begins with an **audit** — the thing both prior rebuilds skipped.

Its foundation still ships in Week 1 regardless: position-record integrity, account reconciliation, `is_test` convention. Those are Abacus prerequisites that are *also* required by everything else, which is why they are not deferred with it.

**Backlog v5 must carry this trigger as a first-class row, not a footnote.**
