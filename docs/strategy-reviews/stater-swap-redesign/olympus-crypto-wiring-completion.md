# OLYMPUS-CRYPTO-WIRING — completion report

**Brief:** `docs/codex-briefs/2026-07-21-olympus-crypto-wiring-brief.md`
**Rulings:** Nick+Fable, 2026-07-21 (all three Phase 0 findings accepted).
**Commits:** Task 1 `cd2cf83`; Tasks 2/3 in this commit.
**Scope:** skill markdown + docs only. No backend. Suite byte-identical 18f/510p/1s/200e.
**Handback:** package + upload + connector toggle = Nick; first crypto committee pass = coordination lane.

---

## What shipped

`hub_get_crypto_state` is now referenced by all seven committee agents, per the
post-Phase-0 rulings (wired into `references/crypto.md`, NOT the equity Context A
lists; DAEDALUS by carve-out only; framings sourced from `docs/the-stable/`, not
pretrained priors).

### Task 1 — `cd2cf83` (already shipped)
COMMITTEE_RULES multi-block conviction clause: penalize the block the agent used,
never the top-level worst-of-blocks rollup.

### Task 3 placement decision (reported per the brief's "CC's call")
The four shared discipline lines are placed **once** in
`skills/_shared/COMMITTEE_RULES.md` as a new `§ Crypto Data Discipline` section
(hourly vintage; never bare `hub_get_quote` on the six symbols; no inferred
scores; FARTCOIN coverage gap), rather than duplicated across seven files.
Rationale: they are cross-agent invariants, COMMITTEE_RULES is the canonical home
for those, and one copy can't drift. It nests into every `.skill` bundle at
packaging time, so every agent gets it.

### Task 2 — per-agent, with the ruled assignments

| Agent | Blocks wired | Methodology cited (the-stable) |
|---|---|---|
| **URSA** | liquidations, funding, open_interest (forced flow) | BTC Derivative Bottom-Signals Checklist §3/§6/§7 |
| **TORO** | funding, open_interest (positioning) | BTC Derivative Bottom-Signals Checklist §3/§6 |
| **THALES** | regime, cta_zone, basis (macro) | Checklist §2/§5 + Crypto ETF Flow Structure.html |
| **PYTHIA** | tape_health (spot/perp CVD), session, regime | spot_flows_futures_impact.html |
| **DAEDALUS** | funding, basis — **carve-out only** | Checklist §2/§3 |
| **PYTHAGORAS** | **warning only** — ATR not served | (n/a — fallback to market_profile/chart) |
| **PIVOT** | block-health synthesis over all | COMMITTEE_RULES multi-block rule |

**DAEDALUS carve-out** (finding 2, as ruled): `hub_get_crypto_state`'s
`funding`/`basis` blocks are readable **only** as context for a crypto-equity
**proxy** options thesis (COIN, MSTR, IBIT, MARA/miners) — never for a spot/perp
structure, never as a directional read. Wired into his existing proxy-equity path
(item 1), so it preserves his ratified mandate instead of reversing it; his
"decline direct crypto" path (item 2) still governs.

### Finding 3a — stale stubs RECONCILED (the priority half)
TORO and URSA `references/crypto.md` said `/api/crypto/tape-health` was
`NA:SPOT_FEED_UNAVAILABLE` for all symbols, "do not treat as a real read." **S-3b
landed; the tool serves spot/perp CVD.** Both now state the blanket no longer
holds, point at the `tape_health` block, and note per-symbol coverage (FARTCOIN
spot leg can still be NA). PIVOT's "CVD split not yet live" line reconciled the
same way. This was the dangerous case — an agent ignoring good data because the
stub said to — the inverse of fabrication.

### Finding 3b — methodology sourcing
Every interpretive pointer routes to `docs/the-stable/` and is cited by file +
section; no directional framing is asserted in CC's own voice. Sources used:
**BTC Derivative Bottom-Signals Checklist** (verified: §2 basis, §3 perp funding,
§5 term structure, §6 OI divergence, §7 liquidation 80/20 — a clean 1:1 with the
tool's funding/OI/basis/liquidations blocks incl. the `divergence` and
`long_pct`/`composition` fields), **spot_flows_futures_impact.html** (spot→perp
CVD transmission), **Crypto ETF Flow Structure.html** (THALES QUALITY input). No
gap required filling from priors, so nothing was flagged to Nick on that basis.

## Verification
- `scripts/package-skill.ps1 all` — clean; all seven committee agents packaged
  (daedalus/pivot/pythagoras/pythia/thales/toro/ursa). `positions` skip is
  pre-existing (no SKILL.md; not a committee agent).
- `git diff --stat` — `skills/` only (+ the untracked runtime `data/watchlist.json`,
  not part of this change and not staged).
- Suite `tests/` — **18 failed / 510 passed / 1 skipped / 200 errors**,
  byte-identical (skill markdown is not imported by tests).

## Handback (CC stops here)
| Step | Owner |
|---|---|
| Package + upload all seven `.skill` files | Nick |
| Toggle Pandora connector | Nick |
| Fresh chat → crypto committee pass on BTC/ETH | coordination lane |

**Post-pass fabrication check** (per the TORO precedent): no agent asserts a
crypto ATR value; no agent cites a value from a `degraded`/`unavailable` block;
no agent converts `cta_zone`/`regime` to a number; PIVOT degrades on block status,
not the top-level rollup.

## Known remaining gap (not in scope, stated plainly)
The committee can now READ crypto; it still cannot SIZE crypto —
`hub_get_portfolio_balances` omits `breakout_prop`, the only crypto-capable
account. Closing that is the reconciliation apply (rulings locked 2026-07-18,
dry-run `c7df849`) + the `breakout_prop` fake-healthy fix (Tier 1 #3). Separate
build.
