# Brief S-4 — Stater Swap v2: Strategy Layer Foundation (R-3)

**Date:** 2026-07-16 | **Executor:** Claude Code | **Coordination:** Fable (Nick's coordination lane)
**Repo path for this brief:** `docs/codex-briefs/2026-07-16-stater-swap-s4-strategy-layer-brief.md`
**Predecessor:** S-3 (R-2 Keep-List Upgrades) — CLOSED. Completion report: `docs/strategy-reviews/stater-swap-redesign/s3-phase1-5-completion-report.md`. Post-R-2 checkpoint: `post-r2-checkpoint-2026-07-16.md` — ATHENA verdict PROCEED TO R-3, ratified.
**Status: AUTHORED ONLY.** Per the checkpoint's own sequencing ruling, this brief is authorable immediately on ratification; **execution does not begin until tomorrow's S-3 overnight live checks clear AND S-3b (spot-CVD wire-in) is deployed and verified.** Nothing in this brief is code tonight.

## Mission

S-4 is the R-3 "strategy layer" — but per the Titans carry-forward table (`2026-07-13-titans-review-stater-swap-v2.md`), its actual scope is narrower than "enroll new crypto strategies." Read precisely, the carry-forward items are:

1. **Anti-Bloat classification table** (ATHENA) — apply the EXISTING, already-ratified `PROJECT_RULES.md` Strategy Anti-Bloat Framework (Olympus-ratified 2026-04-22: REPLACES/ELEVATES/ADDS/REJECTED, mandatory named deprecation target for every ADD) to the crypto strategy population, before any enrollment decision.
2. **Discord embed parity** (HELIOS) — close specific, named gaps in the existing crypto Discord embed (`scripts/signal_notifier.py::post_crypto_signal_alert`).
3. **Carry-asymmetry display + funding-fade rules** (ATLAS, DAEDALUS rule) — a specific display + gating rule for funding-rate-fade signal cards.
4. **Daily-walker crypto support** (ATLAS) — **conditional**: "ships here IF WRR-on-BTC-daily enrolls." No strategy enrollment decision has been made — this item builds the technical readiness only, does not itself enroll anything.
5. RSI-2 perp re-test — explicitly "lowest priority, CHOP-gated, shadow-only" per its own carry-forward wording. Deferred past S-4 unless items 1-4 leave meaningful capacity.

**What this brief explicitly does NOT do:** invent, design, or enroll any new crypto trading strategy. Strategy *methodology* (bear/bull pattern libraries, entry/exit rules, the actual WRR-on-BTC-daily or RSI-2-perp specs) is Nick/committee-level work, not CC's lane — matching the same discipline this whole program has held since S-1 ("do not author crypto reads from general LLM pretrained priors"). Item 1's classification table is a **governance tool**, not a strategy-design exercise: it takes strategies that already exist in code (six identified in S-2 Phase 0: `Crypto Scanner`, `Session_Sweep`, `Funding_Rate_Fade`, `Liquidation_Flush`, `Holy_Grail`, `Exhaustion`) and classifies them against the existing framework so future enrollment/deprecation decisions have a real basis instead of an ad hoc call.

---

## §1 — Phase 0: read-only reconnaissance (no code changes; findings committed first)

Commit as `docs/strategy-reviews/stater-swap-redesign/s4-phase0-findings.md`, file:line evidence, before any Phase 1+ code. If any finding contradicts this brief's assumptions, STOP and flag to Fable before Phase 1 — same discipline as S-2/S-3.

- **0.1** Re-verify the six-strategy population from S-2 Phase 0 finding 0.6 is still accurate (live `SELECT DISTINCT strategy FROM signals WHERE asset_class='CRYPTO'` — has anything new fired since?). For each of the six, gather: current win/loss/expectancy from `signal_outcomes`/`signals.outcome*` columns (S-1 F-2 grading machinery) if enough graded history exists; whether it's REAL (has fired) or purely theoretical (code exists, never fired — per S-2's finding, only `Crypto Scanner` and `Session_Sweep` have ever actually produced a signal).
- **0.2** Read `PROJECT_RULES.md`'s Strategy Anti-Bloat Framework in full (confluence caps, filter rules, ADD requirements, location-quality multiplier, sector-rotation regime spec, signal-enrichment-at-trigger-time requirements) — confirm which of these sub-rules are equity-specific (e.g. sector-rotation regime, PYTHIA VA location) and don't cleanly map to crypto's 24/7, no-sector structure, vs. which apply directly (confluence caps, ADD/deprecation-target requirement).
- **0.3** `scripts/signal_notifier.py::post_crypto_signal_alert` — full current embed field inventory (confirmed so far: direction, entry/stop/target, R:R + risk $, market-structure POC/CVD/book-imbalance). Confirm exactly what's missing for carry-forward parity: funding cost over intended hold (source: which vendor client, per-symbol post-FA-7 parametrization), liquidation-distance-in-ATRs (source: ATR calc location, liquidation-cluster data source — Coinalyze `get_liquidations()` per S-3's FA-7 work), tier badge (source: `crypto_gate_config`'s `tiers` dict, S-2), regime+session+tier legible in the first line (source: `/api/crypto/regime` + `/api/crypto/clock`, S-2 — confirm these are callable from the VPS notifier's context, not just the hub's own process).
- **0.4** Funding-fade carry-asymmetry rule (DAEDALUS, ATLAS-owned): locate `Funding_Rate_Fade`'s current signal-construction code (`crypto_setups.py::check_funding_rate_fade`) and confirm it does NOT yet enforce "no negative-funding-fade longs at Tier 3" or "negative-funding fades require stronger structural trigger" — these are NEW gating rules to add, confirm they don't already exist under different naming before building a duplicate.
- **0.5** Daily-walker crypto support: read `jobs/score_signals.py` (the daily walker, per S-1 F-2's finding it's explicitly deferred from the 15-min BAR_WALK resolver) — confirm its current asset-class awareness (expected: none, equity-only, matching S-1's finding). Scope what "crypto support" would require technically (symbol routing via the F-2 matrix, same pattern as `outcome_resolver.py`'s existing crypto branch) — without assuming WRR-on-BTC-daily is enrolling.
- **0.6** Bypass-retirement tracker: run `scripts/crypto_dual_write_diff_report.py` per the standing instruction before any `bias_scheduler.py` touch.
- **0.7** Known-red baseline: record current FAILED test names + count (expected: unchanged from S-3's recording, plus S-3b's own tests once that lands first).

## §2 — Phase 1: Anti-Bloat classification table (the actual governance deliverable)

- **2.1** Produce `docs/strategy-reviews/stater-swap-redesign/crypto-anti-bloat-classification.md` — one row per strategy (all six from 0.1), columns: current status (REAL/fired vs. THEORETICAL/never-fired), classification (REPLACES/ELEVATES/ADDS/REJECTED per the existing framework), confluence-factor count (cash + derivatives, checked against the existing caps), named deprecation target if ADD (mandatory, no exceptions per the ratified rule), and an explicit note on which equity-specific sub-rules (sector-rotation regime, PYTHIA VA-location multiplier) don't apply and why.
- **2.2** This table is a **recommendation artifact**, not a self-executing decision — it does not itself enroll, retune, or deprecate anything. It exists so Nick/Titans have a real basis for a future enrollment call, closing the carry-forward obligation.

## §3 — Phase 2: Discord embed parity (`scripts/signal_notifier.py`, VPS deploy)

- **3.1** Add funding-cost-over-intended-hold to the embed (per-symbol, post-FA-7 parametrized funding rate × estimated hold duration from the signal's timeframe field).
- **3.2** Add liquidation-distance-in-ATRs (current price vs. nearest known liquidation cluster from Coinalyze, expressed in ATR units using the existing ATR calc already available to the signal).
- **3.3** Add a tier badge (Tier 1/2/3, from `crypto_gate_config`'s seeded `tiers` dict — read via the existing `crypto_gate_loader.py`, no new config table).
- **3.4** First line of the embed becomes `{regime} | {session_partition} | Tier {n}` — sourced from `/api/crypto/regime` and `/api/crypto/clock` (S-2), called from the VPS notifier process (confirm connectivity/latency is acceptable for a per-signal Discord post — do not add a new polling loop if a per-call fetch is fast enough; check before assuming).
- **3.5** **FA-4-equivalent constraint (inherited discipline from S-3):** zero breaking changes to the existing embed fields or the equity Analyze/Dismiss embed path — this is additive to the crypto-specific embed only.

## §4 — Phase 3: carry-asymmetry display + funding-fade gating rules

- **4.1** Display: funding-fade signal cards show the carry asymmetry (cost of holding against the fade thesis) explicitly, not just embedded in the funding-cost line from §3.1 — DAEDALUS's rule is that this must be a first-class, not buried, field on funding-fade cards specifically.
- **4.2** Gating rule 1: negative-funding fades require a stronger structural trigger than positive-funding fades (define "stronger" concretely against existing signal-construction fields in `check_funding_rate_fade` — do not invent a new scoring dimension, tighten an existing threshold).
- **4.3** Gating rule 2: no negative-funding-fade LONGS at Tier 3 (HYPE/ZEC/FARTCOIN) — a hard block, config-driven (extend `crypto_gate_config`, matching the existing hot-reload pattern — do not hardcode the threshold in Python).
- **4.4** These are real behavior changes to a strategy that IS currently live-eligible (`Funding_Rate_Fade` exists in `crypto_setups.py`, though S-2 Phase 0 found it's never actually fired) — confirm via 0.1 whether it's fired since, and if the gate matrix (S-2, still `gating_enabled=false`) should shadow-tag this rule too, for consistency with the rest of the shadow-first posture, rather than enforcing it live immediately.

## §5 — Phase 4: daily-walker crypto support (technical readiness only)

- **5.1** Extend `jobs/score_signals.py` (the daily walker) with the same asset-class-aware branching pattern S-1 F-2 already built into `outcome_resolver.py` (the 15-min walker) — reuse `crypto_bars.py`'s per-symbol routing, do not fork a second implementation.
- **5.2** **Do not enroll any strategy onto the daily walker in this phase.** This ships the capability; enrollment is a separate decision gated on the Anti-Bloat table (§2) and Nick's own strategy-methodology call.
- **5.3** No historical backfill (same hard rule as every prior phase in this program).

## §6 — Hard rules (inherited, unchanged)

Shadow-first where new gating logic is involved (§4.4); `gating_enabled` untouched at `false`; sanctioned vendors only, zero new vendors; all new thresholds config-driven + hot-reloadable via the existing `crypto_gate_config`/`crypto_cycle_config` pattern (do not create a third config table without a specific reason); every migration (if any — §4.3 may not need one, a config value addition) carries `-- DOWN` if a table changes; pathspec-only commits, message via `C:\temp\commitmsg.txt`; no historical `signals`/`unified_positions` mutation; Railway blackout 07:30–14:00 MT applies on trading days for the actual EXECUTION pass (not tonight — tonight is author-only).

## §7 — Done Definition (execution phase, not tonight)

1. Phase-0 findings committed with file:line evidence, including the re-verified strategy population and bypass-tracker output.
2. Anti-Bloat classification table committed, one row per strategy, no strategy self-enrolled by the table itself.
3. Discord embed parity: all four named gaps (funding cost, liquidation-distance-ATRs, tier badge, regime+session+tier first line) live and verified with one real captured embed payload in the completion report.
4. Carry-asymmetry display + both funding-fade gating rules live, config-driven, shadow-tagged if 0.1/4.4 finds the strategy has started firing for real.
5. Daily-walker crypto support technically live (asset-class branching present) with zero strategies enrolled onto it.
6. Known-red baseline unchanged; new tests green.
7. Deployment verification, all 4 PROJECT_RULES steps.
8. Completion report + ACK.

## §8 — Olympus Impact

**No hub MCP tools ship in S-4** — no connector re-toggle, no BTC/SPY committee re-test mandated (standing carry-forward applies to hub-tool briefs only, per the rule ATHENA has applied consistently since S-2). The Discord embed changes (§3) are a VPS-side, committee-adjacent surface, not a hub MCP change — no Olympus skill files are touched by this brief.

---

## §9 — Titans final review (2026-07-16, coordination lane) — verdicts

```
ATLAS — BRIEF FINAL REVIEW
BRIEF: this file
CC-ACTIONABLE: YES — findings-first, exact deliverables named per carry-forward item.
GATES PRESENT: YES — Phase-0 commit gate; the Anti-Bloat table is explicitly non-self-executing
  (2.2); daily-walker support explicitly does not enroll a strategy (5.2).
SCOPE MATCHES CARRY-FORWARD: YES, with one narrowing worth flagging on record — the carry-forward
  table's wording ("strategy layer") could be read as inviting new strategy design. This brief
  reads it narrower (governance + technical readiness only, per the RSI-2/WRR conditional wording
  actually used in the carry-forward table) and explicitly declines to invent strategy methodology.
  CONCERN: §4.2's "stronger structural trigger" for negative-funding fades is under-specified —
  Phase 0 (0.4) must return a concrete, existing-field-based definition before Phase 3 writes code,
  or this becomes an ad hoc threshold invented mid-build. Flagging now so it doesn't get skipped.
CONFLUENCE-CAP CHECK: the Anti-Bloat table (§2) must actually apply the existing cash/derivatives
  factor caps, not just classify REPLACES/ELEVATES/ADDS/REJECTED — Phase 0's 0.2 read confirms
  which sub-rules transfer; make sure the count check itself isn't skipped in Phase 1's table.
APPROVE FOR CC: YES, with the §4.2 concern carried into Phase 0 as a named precondition.

HELIOS — BRIEF FINAL REVIEW
BRIEF: this file
CC-ACTIONABLE: YES.
DESIGN SYSTEM COMPLIANCE: Not applicable — no dashboard UI ships; the embed work is a Discord
  message format, not an `/app/v2` surface.
DISCORD EMBED PARITY: the four named gaps are concrete and checkable (funding cost, liq-distance-
  ATRs, tier badge, first-line regime/session/tier) — APPROVE the scope as specified. NOTE: §3.4's
  first-line format `{regime} | {session_partition} | Tier {n}` should be confirmed against Discord's
  actual embed-title character limits before Phase 2 locks the format — a truncated first line
  defeats the whole point of "legible." Add as a Phase-2 acceptance check, not assumed.
BACKEND DEPENDENCIES NOTED: YES — embed work depends on S-2's regime/clock endpoints and S-3's
  FA-7 parametrized funding client, both already shipped; no new dependency invented.
APPROVE FOR CC: YES, with the character-limit check added to Phase 2's acceptance criteria.

AEGIS — BRIEF FINAL REVIEW
BRIEF: this file
CC-ACTIONABLE: YES.
SECRET HANDLING: Not applicable — no new credentials, reuses existing Discord bot token (VPS-side,
  already provisioned) and sanctioned vendor clients only.
AUDIT LOGGING: the funding-fade gating rules (§4.3) go into `crypto_gate_config` (append-only,
  versioned) — consistent with the established S-2/S-3 pattern. APPROVED.
OVERRIDE-ACCEPTED FINDINGS: None new. NOTE (carried forward, not this brief's to fix): the
  reconciliation micro-brief authored the same night as this brief found a hardcoded plaintext
  DB credential in `scripts/reconcile_rh.py` (untracked, never committed). Not in S-4's scope,
  but AEGIS flags it should not be forgotten — recommend a standing backlog item if one doesn't
  already exist.
APPROVE FOR CC: YES.

ATHENA — BRIEF FINAL REVIEW
BRIEF: this file
CC-ACTIONABLE: YES.
SCOPE MATCHES POST-R-2 CHECKPOINT RULING: YES — the checkpoint explicitly named this "R-3 strategy
  layer," and this brief's narrower governance-plus-readiness reading is the correct interpretation
  given the carry-forward table's own conditional language on daily-walker support and RSI-2's
  explicit lowest-priority status. Endorse the narrow reading over a maximalist one.
SEQUENCING: correctly gated behind S-3b (spot-CVD) and tomorrow's S-3 live checks — no execution
  tonight. RSI-2 perp re-test correctly deferred past S-4 given its own carry-forward wording.
DISPLACEMENT: none new. C-1/C-2 from the post-R-2 checkpoint (L1 re-entry conditions, L1 briefs
  landing on main) are unaffected by S-4 and remain tracked at the checkpoint level, not duplicated
  here.
APPROVE FOR CC: YES.
```

**Titans final review verdict: 4/4 APPROVE FOR CC**, with two binding preconditions carried into Phase 0/Phase 2: (1) ATLAS's §4.2 "stronger structural trigger" definition must come from Phase 0's 0.4 finding, not be invented in Phase 3; (2) HELIOS's Discord character-limit check is added to Phase 2's acceptance criteria.

## §10 — Gate line

Execution does not begin until: tomorrow's S-3 overnight live checks (autonomous hourly-job fire, hot-reload proof) clear against the current container, AND S-3b (spot-CVD wire-in) is deployed and its own Done Definition met. Nothing in R-4+ may start until this brief's Done Definition is met and ACK'd, matching every prior phase's own gate.

*Authored in this session 2026-07-16 evening, folding in the post-R-2 checkpoint's ratification and the Titans carry-forward table from `2026-07-13-titans-review-stater-swap-v2.md`. Repo refs verified against `origin/main` at authoring time (commit `c7df849`).*
