# L1 — Recon Complete → Build-Phase Handoff
**Date:** 2026-06-18 (recon done evening 2026-06-17 MT)
**Status:** Phase-0 recon COMPLETE. Ready for Titans review → brief authoring.
**Predecessor:** `docs/codex-briefs/2026-06-17-L1-build-handoff.md` (kicked off recon)
**Full findings:** `docs/phase0-l1-findings.md` ← READ THIS FIRST

## Fresh-chat kickoff (paste this)
> Read `docs/phase0-l1-findings.md` — L1 Phase-0 recon is done. Run the Titans review (ATLAS / AEGIS / HELIOS / ATHENA) on the recommended 3-brief plan, then write the L1.0 / L1a / L1b briefs. Start with the urgent independent item (zero-flow → BULLISH). Confirm live state before writing (committed ≠ deployed); no code during market hours 7:30 AM–2:00 PM MT.

## What L1 is
The "auction accepted the level (PYTHIA market profile) AND flow confirmed (UW order flow)" signal-quality gate. Recon found it near-greenfield: flow + auction are scattered SCORE NUDGES across 8 paths, never a real gate.

## The 3-brief plan (Titans → author in order)
**1. L1.0 — Flow-plumbing repair (PRE-REQ).**
- Fix **zero-flow → BULLISH**: `_compute_flow_radar` returns $0/$0 → `overall_pc=0` → `0<0.7` → "BULLISH". Committee fed fake-bullish NOW. Must read NEUTRAL on empty. **Urgent, independent, after-hours-safe.**
- Fix the still-live **`_flow_aligned` key bug** (`scoring/feed_tier_classifier_v2.py:124`): reads `net_call_premium`/`net_put_premium`/`net_premium`; writer produces `call_premium`/`put_premium`/`total_premium` → always False → v2 classifier flow arm dead in prod; `fully_confirmed` badge impossible. Fix or excise the dead arm.
- Add a real flow-freshness gate + dead-feed alarm (fail LOUD on absent data).
- Flow-poller re-enable is BUDGET-BLOCKED — see decision below.

**2. L1a — Auction + Flow Gate.**
- Soft **PYTHIA gate**, 3-state: fresh-accept / stale-or-missing → asterisk + mandatory PYTHIA review → committee escalation / feed-down → loud alarm. SOFT not hard (TradingView webhook is spotty). Liquid-universe scoped.
- Canonical flow = `flow_events` net flow, **per-ticker direction computed (call−put)** — NOT the market-tide `net_premium` field (different endpoint/scope; that mismatch is the root of the `_flow_aligned` bug).
- Insertion: in-chokepoint `signals/pipeline.py::process_signal_unified` (L1153), after `apply_scoring`, beside L0.1a. **SHADOW-FIRST.**
- **INTEGRATION-test on real pipeline output**, not fabricated-dict unit tests — fabricated inputs are exactly how `_flow_aligned` stayed green while broken.
- Decide the **2 bypass leaks**: `scheduler/bias_scheduler.py:3575` + `analytics/api.py:2079` call `log_signal` directly, skipping the chokepoint.

**3. L1b — Canonical factor strategies.**
- `docs/the-stable/` is a research LIBRARY, not specs → **AUTHOR** specs for the 5 (TS+XS momentum / RSI-2 / ORB / vol-risk-premium / PEAD) from canon.
- Each via **Anti-Bloat** (REPLACES/ELEVATES/ADDS/REJECTED + confluence caps 3 cash / 2 deriv + one-in-one-out) + its own backtest. Liquid-universe only.
- 2 bonus docx anomaly candidates with backtests worth a look: `SP500_Index_Inclusion_Backtest.docx`, `Price_Insensitive_Flows_Guide.docx`.

## OPEN DECISION — UW budget vs flow-poller re-enable
- `flow_events` poller (`jobs/uw_flow_poller.py`) is **deliberately deactivated** — `main.py` task line commented out, 2026-06-16 UW budget incident. Loop is resilient (`while True: try/except→log+sleep`); off purely by the comment-out, not a fault.
- June 17 UW usage = **16,226 / 20,000 (81%)** WITHOUT the poller. Poller adds ~3,900/day → ~20,126 = **OVER cap. Can't re-enable as-is.**
- **Leading option:** trim `FLOW_POLLER_TICKERS` to the liquid-universe / L0.2 allowlist only (the gate is liquid-scoped anyway) → ~halves footprint to ~2k → 16.2k + 2k ≈ 91% (tight but fits). Alternatives: cut big UW eaters, or raise the UW plan.
- Biggest UW eaters Jun 17: `ohlc_bars` 4,006 · `option_contracts` 3,680 · `technical_indicator` 2,170 · `ohlc_sector` 2,147 (heatmap).

## Ruled OUT (don't re-chase)
- **Upstash Redis is NOT full:** 5.165MB / 256MB (2%), 0 evictions, writes healthy (pythia:* = 65 keys, healthy TTLs). The "storage full" notice is a **request-volume / billing alert** (14.1M commands), not storage → check Upstash dashboard's request/billing metric. Confirms Cluster B: SPY's "frozen at open" is the event-driven cadence, not a Redis write-failure. Redis ruled out of every symptom.

## Gated on external
- `signals.regime` 100% NULL → L0.1b + L1 regime-conditioning gated on the **sb3 ADX-regime promote (~2026-06-18)**.

## Discipline (carry forward)
- Investigation-first; shadow mode before any scoring change; verify live (committed ≠ deployed); **no market-hours code** (7:30 AM–2:00 PM MT, Railway redeploy drops hub 60-170s); atomic commits w/ explicit pathspecs (**NEVER `git add .`** — tree is full of untracked scratch incl. RH trade CSVs); commit via `git commit -F C:\temp\commitmsg.txt`.
- Cross-cutting bug class: **FAKE-HEALTHY** (confident zeros/defaults masquerading as real data) — 4 instances found this recon. Gate + tests must fail LOUD on absent data.
