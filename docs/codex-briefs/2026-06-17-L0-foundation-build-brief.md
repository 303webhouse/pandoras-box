# L0 — Foundation Build Brief

**Date:** 2026-06-17
**Status:** DRAFT — TITANS-REVIEWED 2026-06-17 (verdict: PROCEED, rescoped — see §7). Awaiting Nick clarify (§7 pending Qs) + Titans final review before CC. No build/writes/migrations until greenlit.
**Repo baseline:** `main` @ `947a24b` (advanced from `34032c9` mid-session via sb3 FF-merges). Worktrees live: `sb3-work` (C:/th-scoring), `sec-work` (C:/th-security).
**Parent:** `docs/codex-briefs/2026-06-16-rebuild-stack-master-brief.md` (§2, §8, §11)
**Findings (settled — do NOT re-derive):** `docs/strategy-reviews/holy-grail-gate-test-2026-06-16.md`, `cta-artemis-decompose-and-uw-era-2026-06-16.md`, `regime-gate-and-flow-audit-2026-06-16.md`
**Phase-0 recon performed:** 2026-06-17 against LIVE `railway` Postgres (12,835 signals, range 2026-02-20 → 06-17) + repo @ `34032c9`.

---

## 0. Goal
L0 = **subtraction + routing**. Stop the bleed before adding anything (L1 and L2 rest on this layer). Three jobs:
1. **Suppress** confirmed bleeders — Holy Grail outright; CTA bleeders by `signal_type`.
2. **Route** survivors on **regime × direction × liquid-universe** — NOT on score.
3. **Plumbing** — liquid allowlist, alias-rename layer, APIS/KODIAK label gating, bar-feed hardening, pre/post-UW marker.

**Hard rules (master brief §9):** shadow-mode MANDATORY before any scoring change goes live · no prod writes / migrations / deploys without explicit greenlight · deploys ONLY outside 7:30 AM–2:00 PM MT (Railway drops the hub 60–170s) · atomic commits, explicit pathspecs, never `git add .`, commit via `git commit -F C:\temp\commitmsg.txt` · verify against LIVE data ("committed ≠ deployed ≠ validated").

---

## 1. Phase-0 (read-only) — run / confirm BEFORE any write
1. **Lock the live signal_type/strategy table** (§2 — captured 2026-06-17; re-confirm counts haven't drifted at build time).
2. **Pull Artemis per-signal_type verdicts** from `cta-artemis-decompose-and-uw-era-2026-06-16.md` — `ARTEMIS_LONG`/`ARTEMIS_SHORT` routing is NOT yet in this brief (see §5 Q1).
3. **Confirm the gate is leak-free.** `process_signal_unified` (`backend/signals/pipeline.py` L1141) is the universal chokepoint — all 14 scanner/webhook paths route through it (holy_grail L353, sell_the_rip L655, CTA via `bias_scheduler.py` L3358, footprint, tradingview, whale, flow_ingestion, scout_sniper, wh_accumulation, wh_reversal, crypto_setups, wrr_buy_model). **BUT** two callers write via `log_signal` DIRECTLY, bypassing the gate: `bias_scheduler.py` L3575 and `analytics/api.py` L2079. Phase-0 MUST confirm neither is a live primary signal-emit path — or the suppression gate leaks.
4. **Capture literal find/replace anchors via dry-run** at build time. This brief gives file + function + line anchors and the data; CC captures exact source strings in its dry-run before `--apply` (per process — anchors drift, re-verify at build).
5. **Confirm the UW-era cutover timestamp** for §L0.6.

## 2. Signal reference — LIVE, verified 2026-06-17 (SINGLE SOURCE OF TRUTH)
Suppression/routing keys on **`signal_type`, NOT `strategy`.** The casual name "Holy_Grail" is the *strategy*; the *signal_types* are `HOLY_GRAIL_1H` / `HOLY_GRAIL_15M`. **A gate keyed on `signal_type = 'Holy_Grail'` matches ZERO rows** — this is the headline correction from recon.

| signal_type | n | strategy | L0 verdict |
|---|---:|---|---|
| `HOLY_GRAIL_1H` | 4591 | Holy_Grail | **SUPPRESS** (kill, all timeframes) |
| `HOLY_GRAIL_15M` | 59 | Holy_Grail | **SUPPRESS** |
| `PULLBACK_ENTRY` | 1134 | CTA Scanner | **SUPPRESS** (−0.25) |
| `RESISTANCE_REJECTION` | 619 | CTA Scanner | **SUPPRESS if non-liquid** (−1.37 single-name; +0.73 liquid → keep on allowlist) |
| `TRAPPED_LONGS` | 49 | CTA Scanner | **SUPPRESS** (−2.54) |
| `GOLDEN_TOUCH` | 91 | CTA Scanner | **KEEP** — Midas (+1.75) |
| `TRAPPED_SHORTS` | 74 | CTA Scanner | **KEEP** — Hector (+0.82); trend-gate is Sidecar/L1, not L0 |
| `TWO_CLOSE_VOLUME` | 520 | CTA Scanner | **KEEP** (+0.82) |
| `APIS_CALL` | 155 | (label) | **KEEP, gate to non-liquid only** (§L0.3) |
| `KODIAK_CALL` | 8 | (label) | **KEEP, ungated / park** (§L0.3) |
| `SELL_RIP_EMA` / `_VWAP` / `_EARLY` | 1937 / 482 / 352 | sell_the_rip | Achilles — **Sidecar track**, NOT an L0 gate target |
| `ARTEMIS_LONG` / `ARTEMIS_SHORT` | 1132 / 1098 | Artemis | **TBD — §5 Q1** |

Low-volume types not in L0 subtraction scope (leave as-is): `FOOTPRINT_*`, `Session_Sweep`, `SCOUT_ALERT`, `BEARISH_BREAKDOWN`, `DEATH_CROSS`, `WHALE_*`, `EXHAUSTION_*`.

---

## 3. Workstreams (ordered)

### L0.1 — Suppression + routing gate  ★ the core change
- **Where:** top of `process_signal_unified` — `backend/signals/pipeline.py` L1141, BEFORE the `apply_scoring` call (L1187) and `log_signal` (L1294).
- **What:** one gate that, per `signal_type`, decides KEEP / SUPPRESS / SUPPRESS-IF-NON-LIQUID, then routes survivors on **regime × direction × liquid** (reads `regime`, `direction`, ticker ∈ allowlist). **Score is NOT a routing input.**
- **Mechanism:** a declarative routing map (dict/config keyed on `signal_type` → action), sourced from §2. No scattered per-scanner `if`s.
- **Shadow → enforce (MANDATORY):**
  - **Phase 1 (SHADOW):** gate computes the decision and TAGS the signal (e.g. `gate_type = 'L0_SUPPRESS_SHADOW'`) but does NOT drop it — signal still flows + logs. Run ≥1 week. Confirm via query that the gate would drop exactly the intended populations, with ZERO false drops on keepers.
  - **Phase 2 (ENFORCE):** flip ONE config flag → suppressed signals diverted (not fed, not committee-eligible). Keep rows in DB with the suppress tag for audit — do NOT hard-delete.
- **Holy Grail extra:** after Phase-2 confirms, disable the scanner cron to reclaim compute/UW budget — `backend/scanners/holy_grail_scanner.py::run_holy_grail_scan` (L327). Gate = safety net; scanner-disable = budget win. Order: gate first, disable second.
- **Acceptance:** post-enforce — `HOLY_GRAIL_1H/15M`, `PULLBACK_ENTRY`, `TRAPPED_LONGS` = 0 new fed signals; `RESISTANCE_REJECTION` survives only for allowlist tickers; keepers unaffected; backtest delta matches doc (CTA −592 → +190).
- **Rollback:** config flag → SHADOW.

### L0.2 — Liquid-ticker ALLOWLIST  (dependency for L0.1 + L0.3)
- **Where:** NEW `backend/config/liquid_universe.py` (does NOT exist — confirmed in recon; the only `allowlist` hits in-repo are auth/CORS).
- **What:** a maintained allowlist of liquid tickers. **`non-liquid = NOT in list`** (no fire-time ADV calc — the `signals` table has no liquidity field).
- **Proposed initial membership** (CONFIRM against the validation doc's buckets before locking):
  - `index_macro`: SPY, QQQ, IWM, HYG, TLT, FXI
  - semis/tech (the +0.82 bucket): NVDA, SMH, XLK, MSFT, META, AMZN, GOOGL, AAPL, AVGO, AMD, TSLA, ISRG, INTU, ZS — *confirm full list from doc*
- **Acceptance:** `is_liquid(ticker)` importable + unit-tested; consumed by L0.1 (RESISTANCE_REJECTION conditional) and L0.3 (APIS gate).

### L0.3 — APIS / KODIAK label gating
- **Where:** `backend/bias_filters/macro_confluence.py::upgrade_signal_if_confluence` (L238).
- **What:**
  - **APIS_CALL** → fire on **non-liquid tickers ONLY** (n=154 resolved: non-liquid +1.52 vs liquid ~0). Add an `is_liquid(ticker)` guard (L0.2) — if liquid, do NOT apply the APIS upgrade label.
  - **KODIAK_CALL** → leave **UNGATED** (only 7–8 resolved fires ever, none since 2026-05-27; +1.11 is noise; restricting an ultra-rare signal starves validation). Park; revisit at n≥30.
- **Note:** APIS/KODIAK overwrite `signal_type` with the label (existing behavior). The **score ≥ 85 trigger SURVIVES L0** — score is still computed; L0 only stops *routing* on it. Whether APIS even needs the score≥85 cut (vs pure macro-confluence + non-liquid) is a DEFERRED post-build decompose — hold confluence fixed, vary the score gate. Not an L0 blocker.
- **Acceptance:** APIS no longer applied to allowlist tickers; KODIAK unchanged; shadow-compare counts before enforce.

### L0.4 — Alias-rename layer  ★ ATLAS-owned
- **Where:** NEW `backend/config/strategy_aliases.py`; applied **READ-TIME** at the surface boundary — `backend/signals/feed_service.py::get_active_trade_ideas` (L61) + every hub_mcp tool that emits signals. **NOT** in `log_signal`.
- **CRITICAL:** this is an **ALIAS layer, NOT a mutation** of `strategy` / `signal_type` values. Mutating those orphans outcome history and breaks the n-gates. DB identifiers stay frozen.
- **Map (display only):** Midas → `GOLDEN_TOUCH` · Achilles → `sell_the_rip` (`SELL_RIP_*`) · Hector → `TRAPPED_SHORTS` · Triton → `Whale_Hunter` (L2) · Nemesis → (L2) · Icarus → (existing). Labels: Apis → `APIS_CALL` · Kodiak → `KODIAK_CALL`.
- **Acceptance:** feed + MCP surfaces show display names; DB queries + outcome attribution unchanged; round-trip (display ↔ underlying) test passes; grep confirms no read surface left un-aliased.

### L0.5 — UW fail-loud: VERIFICATION ONLY (the P0 is already shipped)
- **Status correction (2026-06-17):** the handoff's "silent-None-on-429 at `uw_api.py` line 172 (P0)" is **stale**. Read the code: the 429 branch (`uw_api.py:185-200`) already returns a typed, falsy, logged sentinel `UWUnavailable(_GOV_RATE_LIMITED)` — fake-healthy-on-throttle is fixed at the source. The B2 per-caller quota governor + token bucket + circuit breaker + Redis 429 counter live in `backend/integrations/uw_governor.py`. Line 172 is now `increment_daily_counter(caller)`.
- **What remains (small, mostly optional):**
  - Confirm the governor's current mode (observe vs enforce) — operational check; matters only because L0's added UW load could get quota-blocked in enforce mode.
  - The sentinel is branched on in only 2 wrapper sites (`uw_api.py:267,318`); NO downstream consumer (scorer/bars/regime/hub_mcp) branches on it — all treat it as falsy and degrade to fallback. For polling/heatmap that's the desired behavior; for the scoring/regime path sb3 already fails loud via its `unknown` regime state. ATLAS decides whether any consumer needs to *distinguish* throttle-vs-no-data; if not, no work.
  - Non-429 HTTP errors (`uw_api.py:204`) + retry-exhaustion (`:214`) still return silent `None` — decide if those should be typed too (separate, low priority).
- **NOT a pre-06-18 hotfix. NOT in L0's critical path.**

### L0.6 — pre/post-UW segmentation marker
- **Where:** define the UW-era cutover as a constant; ensure outcome attribution can segment on `created_at` vs cutover. (Verdict already RAN — pessimism is structural; this exists so future re-cuts segment correctly, per "segment by regime, never pool.")
- **Decision (§5 Q4):** persisted boolean column vs derived check at query time — lean **derived** (no migration).
- **Acceptance:** any analysis can split pre-UW vs UW-era by one documented timestamp.

---

## 4. Sequencing (authoritative — incorporates §7 rescope)
1. **L0.2 allowlist** — no dependencies; unblocks the RESISTANCE_REJECTION conditional + L0.3.
2. **L0.1a suppression** (Holy Grail both TFs + CTA bleeders) in **SHADOW** → measure ≥1 week. No regime dependency.
3. **L0.3 APIS/KODIAK** gating in shadow alongside.
4. **L0.4 alias layer** — read-time surface, low risk, coverage-complete; can land anytime.
5. **Flip L0.1a + L0.3 → ENFORCE** (after-hours, greenlit); then disable the Holy Grail scanner cron.
6. **[GATED] L0.1b regime × direction routing** — starts ONLY after the sb3 ADX-regime fix promotes (06-18+) AND Phase-0 confirms how `signals.regime` is populated. Shadow → measure → enforce.
7. **L0.6 UW-era marker** — anytime (derived, no migration).
8. **L0.5** — verification only (see §3), not a build.
- Artemis routing → **L1**, not L0. Never deploy 7:30–2 MT. Three live worktrees (`sb3-work`, `sec-work`, + new L0 branch off `947a24b`) — stagger deploys.

## 5. Decisions — RESOLVED in the Titans pass (see §7). Kept for the audit trail.
- **Q1 → RESOLVED: Artemis routing → L1** (not L0). Verdicts pulled from the decompose doc during L1 Phase-0.
- **Q2 → RESOLVED: MOOT.** The 429 fix is already shipped (`uw_api.py:200` typed sentinel + `uw_governor.py`); no hotfix. See §3 / §7.
- *Q3–Q5 below were Titan recommendations, now ratified:* gate-at-chokepoint (§L0.1), derived UW-era marker (§L0.6), dedicated alias module + full read-surface coverage (§L0.4 / §7 item 8).
- **Q3 (ATLAS):** suppress at the pipeline gate (RECOMMENDED — uniform, shadow-friendly, single chokepoint) vs short-circuit each scanner's `check_*` function? Recommend gate; scanner-disable only for Holy Grail (budget).
- **Q4 (ATLAS):** UW-era marker — persisted boolean vs derived (recommend derived).
- **Q5 (HELIOS):** alias-layer home — dedicated module (recommend) vs `signal_profiles.py`; confirm ALL read surfaces covered (feed + every hub_mcp signal tool).

## 6. Scope fence — what L0 does NOT touch
- **Flow Radar key bug** (`hub_mcp/tools/flow_radar.py` mis-keyed → $0/$0/NEUTRAL) → **L1** (Amendment 2). L1 Phase-0 owns the question: is `feed_tier_classifier_v2._flow_aligned` (L124) mis-keyed too, or just the MCP tool?
- **Triton / Nemesis** → L2. Do not pull forward.
- **Sidecar** (sell_the_rip productionize + kill-switch) → parallel track, separate brief.
- **Scoring system NOT deleted** — score + feed_tier still computed; L0 only stops *routing* on score. The APIS score≥85 trigger survives.
- **Security** (plaintext Postgres pw in `.mcp.json` + `scripts/backfill_imported_to_unified.py`) → "Fable" review, pre-June-22. Note only; not fixed here.

---
**Next step:** Titans review pass on this draft → resolve §5 → finalize → CC builds in VSCode → after-hours shadow deploy. **No build until greenlit.**

---

## 7. Titans Review — Outcome & Rescope (2026-06-17)
**Verdict (ATHENA): PROCEED TO BRIEF, rescoped. Conviction MODERATE-HIGH. No vetoes.**
Pass 1: ATLAS MODERATE · AEGIS HIGH · HELIOS HIGH · ATHENA MODERATE-HIGH. Pass 2: unanimous.
Validation: PASS (signal-edge-validation-2026-06-16 + 3 strategy-review docs; 12.8k signals).

**Agreed rescope (no Nick decision needed):**
1. **Split L0.1** → **L0.1a** = signal_type SUPPRESSION (Holy Grail both TFs, PULLBACK_ENTRY, TRAPPED_LONGS, RESISTANCE_REJECTION-if-non-liquid) — NO regime dependency, proceeds now in shadow. **L0.1b** = regime × direction ROUTING of survivors — **HARD-GATED on the sb3 ADX-regime fix promoting (ETA 06-18+).**
2. **`signals.regime` is 100% NULL** (verified — 0 of 12,837). L0.1b cannot route until populated. **Phase-0 (ATLAS):** confirm whether sb3 persists regime to the `signals.regime` COLUMN, or only to the `regime:spy_adx` job/Redis key the scorer reads. If the latter, L0.1b wires its own read from `backend/scoring/adx_regime.py` (do NOT assume the column fills itself).
3. **L0.5 (UW 429) is NOT a build — already shipped.** Verified in code 2026-06-17: 429 → `UWUnavailable` typed sentinel (`uw_api.py:200`); B2 governor in `uw_governor.py`. Remaining is small/optional: confirm governor observe-vs-enforce mode, and whether scoring/bars/regime consumers should `isinstance(resp, UWUnavailable)`-branch vs the current falsy-degrade (sb3 already fails loud on the regime path via its `unknown` state). NOT a pre-06-18 blocker.
4. **`gate_type` collision (ATLAS MEDIUM)** — `gate_type` is already in use (`rsi`/`both`/`3-10`). Do NOT tag shadow-suppression on it. Use a dedicated column or `triggering_factors` jsonb.
5. **Shadow namespace** — use `l0_shadow.*`, NOT `score_v2_factors.sb3_shadow.*` (don't clobber sb3's in-flight shadow data).
6. **Gate-leak check (ATLAS MEDIUM)** — confirm the two direct `log_signal` callers (`bias_scheduler.py` L3575, `analytics/api.py` L2079) are not live emit paths, or extend the gate to cover them.
7. **Reuse, don't rebuild (ATLAS)** — consume `backend/indicators/bars.py` for any bar read (a new bar path risks the yfinance-hot-path veto); `adx_regime.py` is the regime classifier. Base the L0 branch off `main` @ `947a24b`; coordinate with the `sb3-work` and `sec-work` worktrees.
8. **Alias coverage = requirement, not a Q (HELIOS)** — every read surface shows the display name consistently, or none do. (Resolves old §5 Q5.)
9. **Coherence note (ATLAS)** — sb3's `CHOP_STRATEGY_ADJUSTMENTS` already keys on `signal_type` (e.g. `GOLDEN_TOUCH` −8 in chop). The scoring layer and L0's routing layer now both key on signal_type+regime — keep coherent. L0 keeps `GOLDEN_TOUCH` regardless of regime (no conflict; documented).
10. **L1 carry-forward (ATLAS, NOT L0)** — a possible THIRD flow path: `feed_tier_classifier_v2._flow_aligned` (L124). sb3 fixed P2 + P4A; Flow Radar MCP tool is L1 (Amendment 2). L1 Phase-0 must check `_flow_aligned` too.

**Clarify gate — RESOLVED 2026-06-17 (Nick):**
- **Q-A → MOOT.** The 429 silent-None fix is ALREADY SHIPPED on `main`: `uw_api.py:185-200` returns a typed falsy sentinel `UWUnavailable(_GOV_RATE_LIMITED)` (not silent None), with the B2 governor + Redis 429 counters in `backend/integrations/uw_governor.py`. The handoff's "line 172 P0" is stale (line 172 is now `increment_daily_counter`). No hotfix to ship — L0.5 reclassified to verification (see §3).
- **Q-B → YES.** Artemis (`ARTEMIS_LONG`/`ARTEMIS_SHORT`) routing deferred to L1 (rides L1 flow/auction gating).

**Backlog note (ATHENA):** `docs/build-backlog.md` is stale (dated 05-27, predates the rebuild-stack framing + sb3 + sec-work). Update it to seat the L0/L1/L2 stack as the active top-of-queue overhaul.

## 8. Olympus Impact
- **Skills touched:** suppression + routing change WHAT signals reach the feed/committee (fewer Holy Grail / CTA-bleeder signals; regime-routed survivors). The alias layer changes DISPLAY names committee agents may surface (Midas / Achilles / Hector / Apis / Kodiak).
- **Behavior change:** committee sees a smaller, cleaner signal set post-enforce. PYTHIA / THALES / PIVOT / DAEDALUS logic unaffected (alias is read-time, display-only) — but Phase-0 must confirm no committee skill keys on a raw `signal_type` string that the alias would mask.
- **Post-build re-test (REQUIRED):** one full Olympus committee pass on a known-good ticker after enforce, to confirm no regression. (TORO-fabrication-incident discipline — committee behavior can degrade silently when upstream signal assumptions shift.)
