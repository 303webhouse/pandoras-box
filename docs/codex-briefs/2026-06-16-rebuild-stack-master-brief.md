# Pandora's Box — The Rebuild Stack (Master Brief)

**Date:** 2026-06-16
**Source:** Strategy session carryover (signal-edge validation finding)
**Status:** ARCHITECTURE & SEQUENCING brief. PRE-TITANS. No build until Titans pass → per-layer briefs.
**Supersedes:** the ad-hoc "strategy list" framing. The rebuild is a dependency stack, not a backlog.

---

## 0. Why this exists (the finding that forced the rebuild)

**Source doc:** `docs/strategy-reviews/signal-edge-validation-2026-06-16.md`
**Dataset:** `signals` (12,822 rows, 2026-02-20 → 06-17), `signal_outcomes` (12,239 resolved).
**PnL unit:** `signals.outcome_pnl_pct`.

**Headline: the hub's SCORE / feed-tier system has no demonstrable edge.** Win rate is flat
~30–35% across every score band from 20 to 100. The tier ladder is *inverted* against its own
naming — `top_feed` is the best bucket (+0.69 avg) while the "high" `ta_feed` tier is the *worst*
(−1.08). And `top_feed`'s positive read is n=14 — a flag to investigate, not a strategy to deploy.

**Where edge actually lives** (and it is AI-independent — does not depend on any model call):
- **Liquid universe.** `index_macro` (SPY/QQQ/IWM/HYG/TLT/FXI): 427 signals, 57.8% WR, +0.78.
  Semis/tech: 563 signals, +0.82.
- **The single-name long tail is the graveyard:** 7,400 signals, 30.3% WR, −0.70. This is where
  the account bleeds.
- **Regime-conditional shorting.** `sell_the_rip` short-in-bear (URSA's lane): 59% WR, +1.355 over
  n=900 — BUT a March phenomenon. It blew up Apr/Jun when the tape flipped. Real edge, but only
  inside a hard regime gate with a kill-switch.

**Two non-negotiable rules for any re-cut of the data, forever:**
1. **Segment by regime. Never pool.** A pooled number hides the regime that made it.
2. **Strip AI-beta.** Edge must survive with the model calls removed, or it isn't edge.

---

## 1. The shape: a STACK, not a list

The rebuild has layers with hard dependencies. Each layer stands on the one below it. Building an
upper layer first = building on sand — specifically, building a live *options* strategy before the
*signal* it trades has been validated is how you light money on fire with leverage.

```
L2  OPTIONS EXPRESSION    Triton + Nemesis    (only on VALIDATED signals)
L1  SIGNAL QUALITY         gating + canonical factor strategies
L0  FOUNDATION             subtraction + regime routing      <-- everything rests here
--------------------------------------------------------------------------------
SIDECAR (parallel, does NOT wait on the stack):
     regime-gated sell_the_rip + kill-switch   — the one data-backed live build
```

Order of operations is the whole point: **L0 → L1 → L2.** The Sidecar is the exception — already
validated, so it ships on its own track.

---

## 2. L0 — Foundation (subtraction + routing)

The cheapest alpha is *removing the bleeders.* Do this before adding anything.

**Subtract:**
- Suppress the single-name long-tail graveyard (the 7,400-signal, −0.70 bucket) + the other
  confirmed bleeders.
- **Decompose before you kill.** Every strategy gets broken into sub-setups, and each sub-setup
  gated to its own precondition *before* anything is killed. A strategy that bleeds in aggregate
  may contain a profitable sub-setup that was firing outside its precondition. (See §8 — Holy Grail
  and CTA Scanner are exactly this.)

**Route (this replaces score as the primary classifier):**
- The classifier routes on **regime × direction × liquid-universe** — NOT on score. Score is demoted
  from gatekeeper to (at most) a tiebreaker until it earns its place back.

**Segment:**
- Split every analysis **pre-UW vs UW-era.** Many of the 12,822 signals fired before real-time
  Unusual Whales data was wired in, so the pooled numbers are a *pessimistic lower bound.* We need
  to separate bad strategy from bad data.

**Harden:**
- Harden the real-time bar feed. The signal layer is only as trustworthy as the bars feeding it.

L0 is mostly subtraction and plumbing. Unglamorous, and the highest expected-value work in the stack.

---

## 3. L1 — Signal Quality

Once the foundation isn't leaking, *raise the quality of what's left.*

**Highest-leverage upgrade — wire structure + flow into GATING:**
- Market-profile (PYTHIA) and order-flow are currently barely wired into signal gating. The rule
  becomes: a signal only passes if **the auction accepted the level AND flow confirmed.** This is
  the single biggest quality lever available, and it's mostly unbuilt.

**Add canonical factor strategies** (from `docs/the-stable/`) — well-documented, liquid-universe,
AI-independent edges:
- Time-series + cross-sectional momentum
- RSI-2 mean-reversion in liquid index ETFs
- Opening-range breakout
- Vol-risk-premium / VIX term-structure
- PEAD (post-earnings-announcement drift)

---

## 4. L2 — Options Expression (Triton + Nemesis, siblings)

**Gate for the entire layer:** an options expression is only built on a signal that has passed
L0+L1 *and* cleared a forward-edge test. No exceptions. Both strategies are liquid-universe only.

Triton and Nemesis are **siblings, not rivals.** Neither is killed. The only difference is *timing*
relative to the move:

**TRITON — position AHEAD of the move (cheap convexity, whale-led).**
- Universe instinct VALIDATED: liquid names are where edge is.
- Core premise — that stacking aligned signals ("confluence") raises conviction — is UNVALIDATED.
  Confluence is n=7, −0.57. That's "no evidence," not "disproven."
- **Required gate before resuming the build:** a forward-edge test. Do whale-flow-led signals on
  liquid names actually *lead* price, or are they *coincident*? If coincident, Triton is buying
  options ahead of noise. It was mid-build — revisit this before resuming.
- Prior art: `brief-2026-06-15-triton-build-handoff.md` (banked).

**NEMESIS — react DURING the move (acceleration-gated). Build this FIRST of the two.**
- Reframed from a reversal strategy to an **acceleration / impulse detector** (direction-agnostic).
- The real hard problem is **IGNITION vs EXHAUSTION** (is this move starting or ending?), framed by
  structural context + gamma-as-fuel. It is NOT "reversal vs continuation."
- **Critical constraint:** options are NOT cheap during a move — IV spikes the moment the move is
  visible. You cannot naively buy premium mid-impulse.
- Therefore build Nemesis FIRST as an **acceleration primitive / confluence-tag** — velocity +
  acceleration + volume surge + range expansion, contextualized by PYTHIA structure + gamma. Let
  shadow data answer ignition-vs-exhaustion BEFORE any naked premium is risked. A standalone scalp
  is a gated later step, not the starting point.
- Olympus pre-mortem verdict: **REFINE, not BUILD.** Conviction capped LOW (B.06 — URSA + THALES
  both flagged chase risk). 5 required refinements in §5.

---

## 5. Nemesis v0.2 — the 5 required refinements

(Full spec to live in `docs/codex-briefs/2026-06-16-nemesis-spec.md` — to be written next. Summary here.)

1. **Entry = the RETEST, not the initial break.** Don't chase the first print.
2. **PYTHIA auction-acceptance is a co-master-gate with gamma.** Both must agree.
3. **Default expression = short-dated DEBIT SPREAD** (caps vega). Naked 0DTE only on the cleanest gates.
4. **Structural stop at the reclaim level.** Mechanical, defined before entry.
5. **Shadow-gate on the clean-cascade base rate.** Prove the pattern's hit rate in shadow before live.

---

## 6. SIDECAR — regime-gated sell_the_rip + kill-switch (ship-sooner)

The one build that does NOT wait on the stack, because it's the one strategy with live data backing
it (59% WR, +1.355, n=900). It's also the one that *blew up* when the regime flipped. So:
- **Productionize behind a hard regime gate** (only fires short-in-bear when the regime test confirms bear).
- **Build the kill-switch** that cuts it the moment the tape flips — the missing piece that made it
  dangerous in Apr/Jun.
- Can ship sooner than L2. Still requires shadow-mode validation of the gate + kill-switch before live.

---

## 7. UX — collapse the signal card

**Decision (carry it):** kill the "Entry / Stop / T1" levels on signal cards. False precision —
Olympus re-derives levels live, so a stale printed level is worse than none.

The card collapses to **one glanceable 3-state tag**, mapping 1:1 to the three strategy families:
- 🔴 **short-expiry scalp** (Nemesis) — flashing border
- 🐋 **whale-led move** (Triton)
- 📈 **momentum / value long-term hold** (P2) — solid bright border

---

## 8. Open re-analyses (RUN these — they are L0's first gating work)

Not described-and-shelved — the first executable items of L0, and now that local compute is
restored they get *run.* Each has explicit keep/kill logic.

**8.1 Gate-test Holy Grail.**
Re-run filtered to **(ADX > 30) × (liquid universe) × (in-trend direction)**, split **1H vs 15m**.
This is Raschke's Holy Grail (a trend-continuation setup). It bled worst in NEUTRAL chop *because it
was firing outside its ADX>30 precondition.*
→ KEEP if a properly-gated subset has edge. KILL only if still negative when correctly gated.
Prior art: `brief-6b-holy-grail-pipeline.md`, `brief-holy-grail-audit-olympus-expanded.md`.

**8.2 Decompose CTA Scanner by `signal_type`.**
The CTA Scanner is an independent scheduled scanner but a MIXED BUCKET: `PULLBACK_ENTRY`
(trend-cont long), `RESISTANCE_REJECTION` (short), `TWO_CLOSE_VOLUME` (momentum). `PULLBACK_ENTRY`
reaches `top_feed` via Path A — meaning **the thin `top_feed` edge may literally BE the CTA
pullback-entries**, buried inside a "CTA = NONE" aggregate that hides them. Score **per `signal_type`,
not per strategy.** Same treatment for Artemis (doc currently grades it FRAGILE → NONE).

**8.3 Segment the dataset pre-UW vs UW-era.**
Lots of the 12,822 signals fired before real-time UW data was wired in, so the analysis is a
pessimistic lower bound. Isolate bad-data from bad-strategy. This gate informs how aggressively L0
subtracts — we don't want to kill a strategy that was only failing on stale data.

**Not in scope / not dead:** Trojan Horse is a newer footprint-based strategy in OBSERVE mode
(`backend/webhooks/footprint.py`) — too new for resolved data, correctly absent from this analysis,
not a kill candidate.

---

## 9. Hard process rules (carry — these gate every build below)

- **No prod writes / migrations / deploys without explicit greenlight.** Shadow-mode mandatory
  before any scoring change goes live.
- **Deploys only outside 7:30 AM – 2:00 PM MT** (Railway restart drops the hub 60–170s).
- **git:** atomic commits, explicit pathspecs, NEVER `git add .`. `git fetch && git status` before
  any work. Commit message via `git commit -F C:\temp\commitmsg.txt`.
- **Verify against LIVE data.** "Committed ≠ deployed ≠ validated." Ping/query to confirm.
- **Build path:** Titans (ATLAS / HELIOS / AEGIS / ATHENA) → per-layer brief → CC builds in VSCode
  → after-hours deploy.
- **UW API budget:** 120 req/min + 20,000 req/day SHARED across the hub. Blew out 2026-06-16
  (~28.8k), degraded all UW tools until ~10 PM MT reset. Fake-healthy silent-None-on-429 at
  `backend/integrations/uw_api.py` line 172 is P0 — it masks failure instead of surfacing it.
  (NOTE: UW-budget rework appears further along than seed assumes — commits 17d0290 / 7135382 /
  bebee5d. Confirm B/C/D status against live before assuming pending.)

---

## 10. Recommended sequencing

1. **Run §8 re-analyses** (L0 gating work) — unblocked now.
2. **L0 build brief** → Titans → CC. Subtraction + routing + pre/post-UW segmentation + bar-feed hardening.
3. **Sidecar** in parallel (regime gate + kill-switch, shadow first).
4. **L1** — PYTHIA/flow gating, then The Stable factor strategies.
5. **L2** — Nemesis-as-primitive first (5 refinements), Triton forward-edge test, then expressions
   on validated signals only.

**Nothing in L2 goes live until the signal under it has passed L0+L1+forward-edge. That sentence is
the whole brief.**
