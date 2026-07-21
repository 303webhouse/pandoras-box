# MICRO-BRIEF — DEF-FUNDING-DUTY-CYCLE

**Authored:** 2026-07-21, coordination lane
**Authorized by:** Nick, GO given 2026-07-21
**Type:** READ-ONLY characterization. No code changes, no migrations, no deploys, no writes.
**Estimated:** ~1 hour. If it exceeds 2, stop and report — that means Phase 0 found something.
**Titans review:** not required. Read-only investigation with no production surface falls outside the "significant build" definition in `TITANS_RULES.md § Review Workflow`. Recorded here so the skip is deliberate, not an oversight.

---

## TASK 0 — FILING (first, before any query)

```
cd /d C:\trading-hub
git fetch origin && git status
git mv 2026-07-21-def-funding-duty-cycle-micro-brief.md docs\codex-briefs\
git add docs/codex-briefs/2026-07-21-def-funding-duty-cycle-micro-brief.md
git commit -F C:\temp\commitmsg.txt
git push origin main
```

---

## PURPOSE

Both shadow gates shipped in S-4 Phase 3 ride the funding input:

- `funding_fade_negative_floor_raise_enabled` — the 0.0003 → 0.0005 LONG floor (default false)
- the Tier-3 negative-funding-fade LONG block (`gating_enabled` false)

Since DEF-FEED-TRIAGE D1 (`2eb079d`), the contract forbids a signal reporting FIRING while its funding input reads `degraded` — it is suppressed to NEUTRAL. Correct behavior, and verified live.

**The gap:** nobody has measured how often `degraded` is true. Every shadow-gate observation is conditioned on funding being trustworthy at that moment. If funding is degraded a meaningful fraction of the time, the shadow log has a **silently reduced denominator** — the counts look small, the rules look unimportant, and the eventual flip-or-leave decision gets made on a sample nobody knows was thin.

An incomplete number is worse than a wrong one. A wrong number gets caught by a cross-check. An unknowably incomplete one does not.

**This brief produces an honest denominator.** It decides nothing about the gates themselves.

---

## PHASE 0 — DOES THE DATA EXIST? (stop-gate, report before proceeding)

**Do this first and report before writing any analysis query.** The three most recent defects in this program (D2 reader/writer key mismatch, D3 never-scheduled collector, DEF-SIGNAL-METADATA's S2 display artifact) were all cases where the assumed data shape was not the real one. Assume nothing here.

Establish, with evidence:

1. **Is `degraded` persisted anywhere, or computed only at read time?** Trace the funding field's `degraded` flag from `coinalyze_client.get_funding_rate` through `crypto_market.py`'s funding-field contract to `/api/crypto/state/{symbol}`. Name the specific table and column if it is persisted. If it is only computed on read and thrown away, say so plainly.

2. **If persisted — where, at what cadence, and since when?** Candidate tables to check, not assume: `crypto_tape_health_log`, `crypto_regime_log`, `crypto_cycle_log`, `crypto_gate_shadow`. Report actual row counts and the earliest timestamp carrying a usable degraded state, per symbol.

3. **Does the shadow-gate log record the funding state at evaluation time?** This is the load-bearing question. If `crypto_gate_shadow` rows carry the funding read that was live when the gate was evaluated, the duty cycle can be computed directly against the gate population — which is the number we actually want. If not, we can only compute a *global* duty cycle and infer, which is weaker and must be labeled as such.

**STOP CONDITIONS — report and halt, do not work around:**

- **If `degraded` is not persisted at all:** the retroactive characterization is impossible. Do not substitute a proxy, do not infer from vendor error logs, do not estimate. Report "not retroactively measurable" and produce instead a **one-paragraph proposal** for the smallest persistence change that would make it measurable going forward. That is the correct deliverable in that branch and it is not a failure.
- **If persisted but the history is shorter than ~5 days:** report the actual window and flag the sample as thin rather than computing a duty cycle that looks authoritative on three days of data.
- **If Phase 0 contradicts anything in this brief:** the brief is wrong, not the codebase. Report the contradiction and stop.

---

## PHASE 1 — CHARACTERIZE (only if Phase 0 clears)

### 1.1 — Duty cycle, per symbol

For each of BTC, ETH, SOL, HYPE, ZEC, FARTCOIN, over the longest clean window available:

- total funding reads
- reads where `degraded = true`
- **duty cycle = degraded / total**, expressed as a percentage

Report per-symbol, not pooled. Tier-3 symbols (HYPE/ZEC/FARTCOIN) are expected to degrade more often than BTC — pooling would hide exactly the variation that matters, and the Tier-3 gate is one of the two riding this contract.

### 1.2 — Is degraded random or clustered?

Bucket degraded reads by hour-of-day (UTC) and check for burst structure (consecutive degraded reads inside a single window).

**Why this matters more than the headline percentage:** if degraded is uniformly random, a 20% duty cycle means the shadow log is a fair 80% sample and can be scaled up honestly. If degraded **clusters during volatile windows** — which is the plausible failure mode, since vendor feeds degrade under load — then the shadow log is missing precisely the observations where the gates would most likely have fired. Same percentage, completely different conclusion. Name which pattern the data shows.

### 1.3 — Did D1 change the rate or only the consequence?

`2eb079d` deployed 2026-07-21T03:07:06Z. Split the window at that boundary and compare pre/post duty cycle.

D1 fixed a ×100 unit error and hardened the contract so degraded input cannot report FIRING. Those are different things. If the duty cycle is unchanged across the boundary, D1 changed only what happens *during* degraded — which is what we believe. If the rate moved materially, the unit fix was also changing what counted as out-of-bounds, and that is a finding nobody has recorded.

### 1.4 — The honest denominator

Express the result in the form the eventual gate decision needs:

> "The shadow log recorded **N** hits. Funding was degraded for **D%** of the evaluation window, clustered/uniform. The true opportunity count is therefore approximately **M**, and the observed rate should be read as **X**, not **N**."

If 1.2 found clustering, state explicitly that scaling is **not** valid and the shadow sample is biased rather than merely small.

---

## PHASE 2 — OUTPUT

Findings doc at `docs/strategy-reviews/stater-swap-redesign/funding-degraded-duty-cycle-findings.md`:

- Phase 0 result (data location + availability), stated before any numbers
- Per-symbol duty cycle table, window explicitly stated
- Clustered vs. uniform verdict with the evidence
- Pre/post-D1 comparison
- The honest denominator paragraph
- **A one-line recommendation on whether the two shadow gates can be decided on current evidence, or need more collection.** Recommendation only — the flip decision is Nick's and the committee's, not CC's.

Update the `workstreams.md` STATER-SWAP row. Commit both.

---

## GATES — WHAT NOT TO DO

- **No writes.** No migrations, no config changes, no `crypto_gate_config` bumps, no deploys. Read-only means read-only.
- **Do not flip either shadow gate.** Not in scope. Both stay shadow regardless of what the numbers say.
- **Do not fabricate a duty cycle** if Phase 0 shows the data was never persisted. "Not retroactively measurable" is a complete and correct answer.
- **Do not pool symbols** into a single headline number without the per-symbol table alongside it.
- **`::text` cast every timestamp comparison.** `mcp__postgres__query` misparses `timestamp without time zone` — it reads the naive wall-clock as America/Denver, then stamps a UTC "Z", mechanically adding +6h **on display only**. The database is correct. This exact trap fooled two lanes for two days and produced a brief built on a phantom defect. Do not repeat it.
- **Do not touch `TRITON-EXPLORE` or the pending-grade holdout.** Different workstream, and the holdout law is absolute.

---

## DONE DEFINITION

1. Phase 0 answered with named tables and real row counts, or a clean "not persisted" verdict.
2. Per-symbol duty cycle table with the measurement window stated, **or** the not-measurable branch with its forward-persistence proposal.
3. Clustered-vs-uniform verdict, backed by the bucketed data.
4. Pre/post-D1 comparison across the `2eb079d` boundary.
5. Honest-denominator paragraph in the form specified in 1.4.
6. Findings doc committed; `workstreams.md` row updated.
7. Zero writes to any production table. Zero deploys.

---

## OLYMPUS IMPACT

**Indirect but real.** This changes no committee-visible surface today. It determines whether the eventual `funding_fade_negative_floor_raise_enabled` and Tier-3 block decisions are made on trustworthy evidence. If the duty cycle comes back high and clustered, the correct output is "keep collecting," and that will displace an assumption several agents have been carrying — that the shadow logs are a fair sample of reality.

No post-build committee re-test required, since no data source the committee reads is modified.
