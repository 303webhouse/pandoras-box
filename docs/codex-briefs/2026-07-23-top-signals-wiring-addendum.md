# TOP-SIGNALS WIRING — ADDENDUM BRIEF

**Date:** 2026-07-23
**Lane:** TOP-SIGNALS-WIRING (docs/skills), parallel to DEF-CVD-QUARANTINE Tier A (backend). Isolated worktree, **zero file overlap** by construction.
**Pattern followed:** `d55a115` (OLYMPUS-CRYPTO-WIRING) — skill markdown only, citation/capability lines, no interpretive framing in CC's voice, methodology sourced by file + section.
**Base:** `origin/main` @ `c9de689` (Tier A EXECUTED — completion evidence).

This brief records what was filed and wired. It carries **no new methodology** — every citation traces to the ratified framework doc, which is Nick's, not this lane's.

---

## TASK 0 — Filing (two ratified docs)

1. **`docs/the-stable/btc-derivative-top-signals-checklist.md`** — the crypto TOP-signals framework, **RATIFIED as-written (Nick, 2026-07-22)**. Filed by **verbatim rename** from the candidate drop (`2026-07-22-crypto-top-signals-candidate-framework.md`), byte-identical — no methodology, tier, or status-header edits (this lane does not reconcile methodology). Per the doc's own guard, committing it to `docs/the-stable/` is the ratification event that unblocks wiring. It is the top-side counterpart to the existing **BTC Derivative Bottom-Signals Checklist**, which had no top-side complement — an invisible bullish bias, since both TORO and URSA previously read only the bottom framework.
2. **`docs/strategy-reviews/stater-swap-redesign/2026-07-22-stater-swap-v2-mockup-concept-plan.md`** — S-6 mockup concept plan, filed verbatim at its canonical path. **Appended one line to `helios-mockup-track.md`** (2026-07-23): concept plan filed, three concepts (C1 Command Rail / C2 Cockpit Grid / C3 Tape-First), renders in progress via Figma, Nick reaction pass pending. **This formally starts the concept session — HELIOS gate, pass one.**

## PHASE 0 — Bottom-checklist reconciliation (§1/§4, never seen by the authoring lane)

Read the full bottom checklist (8 numbered sections + VIX bonus + Cluster Effect). The two sections the top-authoring lane never saw:

- **§1 — 25-Delta Skew: Extreme Negativity** — an options-skew / dealer-short-gamma signal (puts panic-bid → vanna/charm reversal tailwind).
- **§4 — Stablecoin APRs: The Apathy Floor** — a DeFi money-market leverage proxy (USDT/USDC borrow rates collapsing to ~0% = long-leverage washout).

**Verdict: CLEAN — no contradiction, no duplication; proceeded.** Neither §1 nor §4 is mirrored by any T-signal (the top framework's explicit mirrors are §2/§5→T-4, §3→T-1, §6→T-2a, §7→T-3), and neither contradicts it — §4 even states its own top-side ("high APRs indicate euphoria"), which *aligns* with the carry-froth thesis (T-4/T-1). Both are un-mirrored **gaps**, not conflicts. Note for Nick (methodology, not this lane's to reconcile): §1's options-skew and §4's stablecoin-APR top-side mirrors are candidate top signals the ratified doc does not carry, and neither is served by `hub_get_crypto_state` — they would join T-7 (ETF flow) as manual/external reads if ever adopted. §8 (spot orderbook skew), the VIX macro bonus, and the Cluster-Effect execution logic are likewise un-mirrored but fall outside the §1/§4 gate.

---

## WIRING — what was cited where (`d55a115` pattern; citation-only)

Each agent received one **top-side methodology bullet** inserted directly after its `hub_get_crypto_state` bullet (where `d55a115` attached the bottom-checklist citation), citing the new checklist by **file + T-signal**. The FROTH tie-in was appended to each existing `cta_zone`/FROTH citation line.

| Agent | Blocks / lane | T-signals cited | FROTH tie-in |
|---|---|---|---|
| **TORO** (primary consumer) | `funding`, `open_interest` (+ THALES's `basis`) | **5-stage tracker framing**; **T-1** funding persistence-with-stall, **T-2a** levered stall, **T-4** basis/carry froth. Bold: **LONG DE-RISKING FIRST — no item is a standalone short trigger** (short-thesis secondary). | ✅ appended to cycle-extremes line |
| **URSA** (short-thesis, secondary) | `liquidations`, `funding`, `open_interest` | **T-3** short-liquidation blow-off — `long_pct ≤ 20%` **AT HIGHS = terminal; the same print out of CAPITULATION = ignition** (location is the signal). **T-2b** covering rally **valid only paired with T-5's spot-CVD confirmation** (killed standalone). | ✅ appended to froth-dial line |
| **THALES** (macro) | `basis`, `regime`, `cta_zone` | **T-4** basis/term-structure froth (§2/§5 mirror; exposure timer, never a short trigger). **ALL thresholds distributional (trailing percentile, never absolute).** **Cyclical-positioning-not-secular** boundary. | ✅ appended to cycle-extremes line |
| **PYTHIA** (T-5 confirm) | `tape_health` (+ MP) | **T-5** spot-led distribution — **distribution into an MP poor high = strong form** (poor-high/excess vocab confirms). Tier-3 hypothesis (n=0), observation log. **Observation may begin immediately:** `tape_health` is a live trade fetch, confirmed clean/alive in **DEF-CVD-QUARANTINE R2** (the disabled branch is CVD *events*, not the tape log). | — (no `cta_zone` citation in her file, correctly none) |

**Not changed, by design:** `_shared/COMMITTEE_RULES.md` (no rule changes), no new tools, no scores/gates/automation. Interpretive framework only, same status as the bottom checklist. PYTHAGORAS / PIVOT / DAEDALUS untouched (outside the ratified doc's §3 wiring scope).

---

## VERIFY

- **Packager:** `scripts\package-skill.bat` clean for **toro, ursa, thales, pythia**.
- **Scope:** `git diff --stat` touches **only** `docs/` and `skills/` — zero `backend/` or `tests/`.
- **Suite:** docs/skills carry no test impact — **provably inert**, two ways. (1) By construction: no test imports or reads any of the 9 changed markdown files. (2) Empirically: same-env clean-vs-change delta = **0** — this worktree env produced **28f / 579p / 1s / 200e** on *both* the clean `c9de689` tree (changes stashed) and the changed tree. The canonical main-checkout baseline is **17f / 517p / 1s / 200e** (Tier A completion doc); the worktree env carries ~11 more DB/network-dependent failures (the 200 fixture errors are the tell), present with or without these changes — orthogonal to the wiring. Errors (200) and skipped (1) match the canonical exactly.

## HANDBACK

CC stops here. **Nick:** package + upload the four `.skill` files (toro, ursa, thales, pythia). **No connector toggle / no tool-manifest change** — no tools were added. First top-side committee crypto pass + T-5 observation-log seeding = coordination lane.
