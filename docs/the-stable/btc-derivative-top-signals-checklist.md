# CRYPTO TOP-SIGNALS FRAMEWORK — CANDIDATE FOR RATIFICATION

**Authored:** 2026-07-22, coordination lane — double pass (crypto experts panel + Olympus)
**Status:** **DRAFT. Not methodology until Nick ratifies.** Per the stubs guard, nothing here enters any agent's `crypto.md` until this document is edited/approved by Nick and committed to `docs/the-stable/`.
**Purpose:** the-stable has a **BTC Derivative Bottom-Signals Checklist** (cited in committee wiring: §2 quarterly basis, §3 perp funding, §5 term structure, §6 OI divergence, §7 liquidation 80/20). It has **no top-side counterpart.** Both TORO and URSA currently read the bottom framework, which quietly equips the committee to spot bottoms better than tops — an invisible bullish bias, because every individual read is correctly sourced.
**Sources used:** the five cited checklist sections as wired at `d55a115`; the live `hub_get_crypto_state` block schema; panel knowledge (explicitly authorized by Nick for this brainstorm, 2026-07-22). **Sections §1/§4 of the bottom checklist were not read by this lane — the ratification pass must check this draft against the full original for structure and overlap.**

---

## TASK 0 — FILING (after Nick's ratification edit, not before)

```
cd /d C:\trading-hub
git fetch origin && git status
git mv 2026-07-22-crypto-top-signals-candidate-framework.md docs\the-stable\btc-derivative-top-signals-checklist.md
git add docs/the-stable/btc-derivative-top-signals-checklist.md
git commit -F C:\temp\commitmsg.txt
git push origin main
```

---

## THE CORE FINDING BEFORE ANY SIGNAL: A TOP CHECKLIST IS NOT A MIRRORED BOTTOM CHECKLIST

Four structural asymmetries break the naive mirror. Every candidate signal below is built on them.

**A1 — Bottoms are events; tops are processes.** Capitulation compresses into coincident extremes — one violent window where funding, liquidations, and basis all scream at once. Distribution stretches across days of ambiguous, rotating signals. Consequence: the bottom checklist can score a snapshot; a top checklist must track **persistence and sequence**. (This happens to suit the hourly-vintage constraint of `hub_get_crypto_state` — tops are slow, and hourly sampling is exactly wrong for scalps but exactly right for process detection.)

**A2 — The zero line only works on the bottom side.** Crypto's structural majority is long; positive funding is the *baseline state*, not a signal. `funding < 0` is meaningful at the zero line precisely because it's rare. The top-side equivalent is **not** `funding > 0` — that's noise — it's funding **persistently extreme relative to its own trailing distribution**. Thresholds must be distributional, not absolute.

**A3 — Short squeezes are dual-natured.** An 80%-short liquidation cascade *ends* a move when fuel is exhausted at highs, and *ignites* one when it fires out of a capitulation zone. The same print means opposite things by regime. Any top rule built on short liquidations is regime-conditioned or it's wrong half the time.

**A4 — The consumer inverts.** The bottom checklist is an **entry** aid (URSA confirms exhaustion, TORO times accumulation). A top checklist's primary job in Nick's actual book is an **exit** aid — TORO protecting B1/B2 longs — with short-thesis support secondary. This changes what "good" looks like: early-but-actionable beats precise-but-late.

---

## PASS 1 — CRYPTO EXPERTS PANEL

*Four ad hoc archetypes, convened once for this brainstorm. Not committee members; Greek working names per project convention.*

### CASSANDRA — cycle-top process analyst
*The lane: distribution structure; cursed to call tops correctly and be doubted.*

Tops are sequences, not moments. The recurring order across cycles: **carry froth first** (basis blows out — the crowd builds levered length), then **funding persistence** (longs pay heavily and keep paying), then **stall** (price stops progressing while positioning stays extreme), then **distribution** (real coins leave into the levered bid), and only then the **blow-off or breakdown**. A checklist that scores these as independent coincident items misses that the *sequence itself* is the signal. Propose the framework as a **stage tracker**, not a scorecard: knowing you're at stage 2 of 5 is more useful than a 3-of-7 count.

### PLUTUS — derivatives carry specialist
*The lane: funding, basis, term structure — the price of leverage.*

Two candidates. **First, the cleanest mirror in the whole set:** extreme contango. Annualized quarterly basis in its top decile — historically double-digit annualized at cycle froth — with a steep term structure means the cash-and-carry trade is crowded and everyone is synthetically long. This is the §2/§5 mirror and it's nearly symmetric; backwardation marks bottoms, extreme contango marks froth. **Second, per A2:** funding *persistence* — top-decile-of-trailing-30d funding sustained across many consecutive reads **while price makes no new high**. Longs paying premium rates for zero progress is the crowd financing a top. Single elevated prints are noise; persistence-with-stall is signal.

### CHARON — forced-flow specialist
*The lane: liquidations — who is being carried out, and when it matters.*

The §7 mirror with A3's conditioner built in: **≥80% short liquidations** in a window is a squeeze — and its meaning is *positional*. At range highs, after an extended advance, with funding already elevated: that cascade is the last fuel burning — nobody left to squeeze, blow-off candidate. Out of a CAPITULATION zone or early in an advance: ignition, not exhaustion. Never wire the ratio without the location. Secondary tell: liquidation *quiet* at highs — a market grinding up on vanishing forced flow is a market running out of participants, the forced-flow version of volume divergence.

### PROTEUS — market-maker / orderflow
*The lane: who is actually transacting — spot vs perp, the S-3b split.*

The one signal in this stack that generic checklists don't have, because Nick built the instrument for it. **Spot-led distribution:** price holding or advancing on the *perp* bid while **spot CVD turns and steepens negative** — real coins being sold to levered buyers. That's distribution in its literal mechanical form, readable directly off `tape_health`. Its weaker cousin: a **PERP_LED advance** with flat spot — not distribution yet, but an advance with no real money behind it, fragile by construction. The inverse of the accumulation read the committee already runs (spot-led buying = real). Same instrument, other direction — and today's live BTC read (PERP_LED, perp CVD deeply negative, spot barely positive) shows the machinery already resolves this.

---

## PASS 2 — OLYMPUS CROSS-EXAMINATION

**URSA (assigned: kill every candidate).**
T-4 contango: *elevated is not a top* — 2021 ran double-digit basis for months while price doubled. Survives only as an **exposure-reduction timer, never a short trigger**; the checklist must say so in bold or it will be misused. T-2b covering rallies: in flow-driven regimes a covering rally hands off to real bids — kill it as a standalone, keep it only paired with spot CVD confirmation. T-5 spot-led distribution: the mechanism is sound but **unvalidated in-house** — n=0 observed instances since S-3b went live; it enters as a hypothesis with an observation log, not a rule. And the meta-objection: a top framework used badly becomes a reason to cut winners early. The consumer inversion (A4) must be printed on the label.

**THALES (regime conditioning).**
Every threshold is regime-relative. The ETF era moved the funding baseline and the basis distribution — trailing-percentile thresholds, never the absolute numbers from prior cycles. And one boundary the bottom checklist never needed: this framework detects **cyclical froth**, not secular tops. It should say plainly that it times *positioning*, not *narrative* — B1 thesis exits are a different instrument. On-chain confirmation (MVRV, exchange reserves) remains outside the hub; flag as a manual step, don't fake a block for it.

**PYTHIA (participation).**
T-5 in auction terms is **an auction failing at the highs** — initiative buyers levered, responsive sellers real. That's the same read as her poor-high/excess vocabulary on the profile, which means MP structure (post-`adfd5bc`, now trustworthy) can *confirm* T-5: distribution into a poor high is the strong form. Also claims partial ownership of T-2a: OI building while price stalls **inside value** is balance, not fragility — location on the profile conditions the read.

**TORO (the actual consumer).**
Reframes the deliverable: *"My job with this list is knowing when to stop being long."* Wants the stage tracker (CASSANDRA) over the scorecard — "stage 3 of 5, tighten stops" is actionable; "4 of 7 boxes" is trivia. Endorses T-5 as the highest-value candidate because it's the one that fires *before* the blow-off rather than during it. Accepts URSA's label: this list de-risks longs first, arms shorts second.

**PIVOT (synthesis).**
Adopt seven candidates in three tiers. Frame as **stage tracker with per-stage confirmations**, per CASSANDRA/TORO. Print the consumer inversion and the never-a-short-trigger warning, per URSA. All thresholds distributional, per THALES. T-5 enters as observed-hypothesis with a log, per URSA's n=0 objection. **No scores, no gates, no automation — interpretive framework only, same status as the bottom checklist.** Recommend ratification with those edits.

---

## THE CANDIDATE CHECKLIST

**Consumer note (print first):** this framework's primary job is **long de-risking** (TORO), secondary **short-thesis support** (URSA). No item below is a standalone short trigger. It detects **cyclical positioning froth**, not secular tops.

**Stage model** (typical sequence; stages can overlap or abort — the sequence is the signal, per A1):

| Stage | Name | Primary blocks | Candidate signals |
|---|---|---|---|
| 1 | **Carry froth** | `basis` | **T-4** |
| 2 | **Funding persistence** | `funding` | **T-1** |
| 3 | **Stall** | `open_interest` + price | **T-2a / T-2b** |
| 4 | **Distribution** | `tape_health` (+ MP confirm) | **T-5** |
| 5 | **Terminal flow** | `liquidations` | **T-3** |

### Tier 1 — well-established (ratify with confidence)

**T-4 · Basis/term-structure froth** — `basis` block. Annualized basis in its top decile of the trailing distribution; steep term structure. The §2/§5 mirror, the cleanest symmetry in the set. **URSA's bold label: an exposure timer, never a short trigger — froth can persist for months.**

**T-1 · Funding persistence-with-stall** — `funding` block. Funding in its top decile of trailing 30d, sustained across ≥6 consecutive hourly reads, **while price makes no new high**. The A2 rule: distributional threshold, never the zero line, never a single print.

**T-2a · Levered stall** — `open_interest` + price. OI building at/after highs while price stops progressing, funding already elevated. Fragile by construction. PYTHIA's conditioner: only fragile *above/at value* — the same shape inside value is balance.

### Tier 2 — sound mechanism, regime-conditioned

**T-3 · Short-liquidation blow-off** — `liquidations` block. `long_pct ≤ 20%` (the §7 mirror) **at range highs / after extended advance / with funding elevated** = terminal fuel. The identical print out of CAPITULATION = ignition. Location is the signal; the ratio alone is not.

**T-2b · Covering rally** — price advancing while OI *falls* = advance powered by short covering, no new commitment. **Standalone: killed by URSA. Valid only paired with T-5's spot read.**

### Tier 3 — hypothesis, observe before trusting

**T-5 · Spot-led distribution** — `tape_health` block. Price holding/advancing on perp bid while spot CVD steepens negative: real coins sold to levered buyers. Strong form: into an MP poor high (PYTHIA confirm). Weak form: PERP_LED advance, flat spot. **The highest-value candidate and the only one native to Nick's own instrument — and n=0 observed since S-3b. Enters with an observation log, promotes on evidence.**

**T-7 · ETF flow reversal** — no hub block. Sourced from the-stable's *Crypto ETF Flow Structure*: sustained inflow deceleration flipping to outflows after an advance. Manual/web-search step until the hub exposes it. Listed so the gap is named, not faked.

**Zone tie-in:** `cta_zone` already carries **FROTH** as its top-side label. This checklist is FROTH's confirm/deny panel: FROTH + T-4 + T-1 concurrent = high-conviction top-adjacent; FROTH alone = classifier opinion awaiting confirmation. The framework slots into the existing taxonomy rather than inventing one.

---

## RATIFICATION PATH

1. **Nick edits this document** — cut, reword, re-tier anything. Check against the full bottom checklist (including §1/§4, unseen by this lane) for structure and overlap.
2. On approval: file per Task 0 into `docs/the-stable/`.
3. **Wiring addendum brief** (small, the `d55a115` pattern): citations into TORO/URSA/THALES `crypto.md` (+ PYTHIA for T-5's MP confirm), pure capability/citation lines, no interpretive text beyond what this ratified doc carries.
4. Repackage → upload → connector toggle (the four-step Nick now knows).
5. **Not wired, by design:** no scores, no gates, no automated detection. Interpretive framework for committee reads, same status as the bottom checklist. Any future automation goes through shadow-by-default like everything else.
6. **T-5 observation log:** first three live instances get annotated in committee passes before anyone leans on it.

---

## WHAT THIS DELIBERATELY DOES NOT DO

- No numeric thresholds beyond distributional definitions ("top decile of trailing") — absolute numbers from prior cycles are exactly what THALES's regime objection kills.
- No composite score. The stage tracker is the output. A single froth number would invite the false precision the −45..+35 filter guard exists to prevent.
- No secular-top claims. B1 thesis exits are narrative decisions; this instrument times positioning.
