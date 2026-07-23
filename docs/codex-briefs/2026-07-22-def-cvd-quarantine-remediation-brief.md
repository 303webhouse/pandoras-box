# BRIEF — DEF-CVD-QUARANTINE (remediation)

**Authored:** 2026-07-22 (Claude Code), from the DEF-CRYPTO-VP-ANCHOR sibling audit
**Severity:** P1 data-integrity — fabricated signals + corrupted grading anchors on a committee-adjacent surface
**Titans review:** **ATLAS — PASS WITH FOUR CONDITIONS** (§10). All four are folded in below and are internal stop-gates during execution.
**GATE:** **Nothing in this brief mutates data or disables a live path until Nick gives the explicit GO.** Fable recommends GO; Nick's GO is the authorization. This is a plan, not an execution.

---

## 0. What this remediates (and what is already fixed)

The vendor-order read-path defect is **already fixed and deployed** (`5da9e6c`, source sort in `_fetch_full_ohlc`, four-step verified — BTC CVD entry moved 63,092→65,757 post-deploy). This brief handles what the fix does **not** cure:

1. **Historical corrupted rows** already written by the CVD event engine before the sort landed.
2. **A detector-logic defect** the audit surfaced that is **independent of the vendor-order bug** — the CVD_ABSORPTION detector is structurally phantom (§6). The source sort corrected the *price label*; it did not make the detections real.

Both are entangled in the same 272 rows, so they are remediated together.

---

## 1. Corrupted-field list — FROZEN at 11 fields

The ruling-4 mini-audit (required before this froze) confirmed the other three crypto outcome sources — **FWD_RETURN, PROJECTED_FROM_BAR_WALK, COUNTERFACTUAL** — all source prices from **yfinance / date-keyed lookups**, never `crypto_bars` (grep=0 for the corrupted imports), and select order-safely. **The field list does not grow.**

| # | Field | Corruption | Birthdate |
|---|-------|-----------|-----------|
| 1 | `signals.entry_price` | `= recent[-1]` stale price (vendor-order) | `3891a4f` 2026-07-18 |
| 2 | `signals.stop_loss` | stale-window level ± buffer | `3891a4f` |
| 3 | `signals.target_1` | stale current_price ± risk·rr | `3891a4f` |
| 4 | `signals.enrichment_data → cvd_level_price` | stale-window level | `3891a4f` |
| 5 | `signals.enrichment_data → cvd_level` | which VP level (phantom anchor) | `3891a4f` |
| 6 | `signals.enrichment_data → event_reason` | reasoning string embeds stale price + phantom level | `3891a4f` |
| 7 | `signals.signal_id` | **identity key** (embeds level_name); join key to `signal_outcomes` — **never rewrite in place** | `3891a4f` |
| 8 | `signal_outcomes.entry` | copied from stale `signals.entry_price` | `3891a4f` |
| 9 | `signal_outcomes.stop` | copied from stale `signals.stop_loss` | `3891a4f` |
| 10 | `signal_outcomes.t1` | copied from stale `signals.target_1` | `3891a4f` |
| 11 | `signal_outcomes.outcome` | graded against corrupt anchors (walk itself is sound) | accrues post-grade |

**Not corrupted (exclude from predicate):** `signals.direction` (live `cvd_net` sign), `crypto_tape_health_log.*` (live OKX fetch). **Not persisted (no data action):** the `crypto_state.atr` sibling — served-only, auto-corrected by the source sort.

---

## 2. Blast radius — all quarantined (predicate category-keyed)

`signal_category = 'CRYPTO_CVD_EVENT'`, all `CVD_ABSORPTION`, **0 `CVD_DIVERGENCE` lifetime**. The count **grew in real time until the detector was disabled**: 272 (audit) → 329 → 349 (at the 2026-07-23 05:06Z flip). Snapshot at 329:

| Symbol | Vendor | Rows | `quarantine_class` |
|--------|--------|------|--------------------|
| BTC | UW (desc) | 98 | `mispriced` |
| ETH | UW (desc) | 77 | `mispriced` |
| HYPE | OKX (desc) | 54 | `mispriced` |
| SOL | UW (desc) | 24 | `mispriced` |
| ZEC | Binance (asc) | 76 | `correct_priced_phantom` |
| **Total (@329)** | | **329** | **253 + 76** |

The predicate is **category-keyed**, so the exact frozen count (final per-symbol split confirmed by the R2 exit gate) does not change the write. ~80 graded outcomes carry propagated-wrong verdicts; the burst rows (Nick ruled KEEP) are a subset — §3 ruling 1.

**Fire-rate characterization (R3 — the free data shadow mode would have collected):** the detector fired **272→329 (+57) in a single afternoon** and continued to 349 — this is its **post-source-sort fire rate on live-priced bars**, and it is (a) the floor the redesign must beat and (b) empirical proof that ATLAS #1 (disable-before-pre-image) was load-bearing. **The accrual is vendor-independent:** ZEC (Binance-ascending, correctly priced) added **15 of the 57** — a correctly-priced symbol phantom-firing at the same clip is one more nail in the logic-defect finding (§6). The 0-divergence lifetime held across all of it.

---

## 3. Rulings baked in (Fable, 2026-07-22)

**Ruling 1 — QUARANTINE-EXCLUDE (not rewrite, not purge).** Additive marker, default-excluded from every read, excluded from grading, pre-image JSONL, one-line reversible. Precedent: `cvd_dedup_burst`, `quarantined_equity_clobber` (both real, additive). **Correction:** `is_test` was cited as a third precedent but was **never built** (0 occurrences in backend; queued as W1-3) — so Tier A creates the first central visible-signals filter (§5b), it does not piggyback on one. Also (Fable): Option 2 (status/`user_action` overload) was rejected — it destroys DISMISSED lifecycle state, `user_action` is Nick's field, and grading needs a code edit either way (80 outcomes graded on the 335 DISMISSED rows).
- **Validation-set re-scope (Fable):** the "keep them to replay a fixed detector" argument does **not** hold — there is no fixed detector to replay against; the 272 are the redesign's **BEFORE-picture**, nothing more. Quarantine therefore stands on **reversibility + precedent ×3 + Nick's burst-row KEEP**, not on replay value.
- **Governance (Nick's explicit YES):** the 272 contain the 73 burst rows Nick ruled KEEP. Quarantine **keeps the rows** (honors the letter) while **excluding them from grading** (supersedes intent). Nick blessed this supersession.

**Ruling 2 — DISABLE-pending-fix** (converted from SHADOW by the conditional; the logic is broken beyond pricing — §6). Config-DB-row halt + redesign requirements: §5d.

**Ruling 3 — ZEC as pricing baseline, RESOLVED (§4).** Fable accepted the two-value tag: quarantine all 272; ZEC tagged `correct_priced_phantom`. Fable's note: ruling 3's premise was wrong — "legitimate" conflated *correctly-priced* with *real-detection*; ZEC only ever qualified for the first, and ruling 2's conditional should have cascaded to it. Notifier suppression uniform across all six.

**Ruling 4 — field list frozen at 11** (§1).

---

## 4. ZEC — RESOLVED (two-value tag)

ZEC's 61 rows are **correctly priced but still phantom** (same dead divergence branch, same tautological proximity — §6; ordering-independent). Resolution (Fable-accepted):

- **Quarantine all 272.** `quarantine_class = mispriced` (211: BTC/ETH/SOL/HYPE) | `correct_priced_phantom` (61: ZEC).
- ZEC stays **queryable** as the pricing-validation baseline (source-sort proof) and is **not** rewritten (nothing to rewrite — it's correctly priced) — but it is **excluded from grading and reads** like the rest, because its detections are not real. It validates *pricing*, not *signal validity*.

---

## 5. Mechanics (for ATLAS)

### 5a. Quarantine marker (additive, reversible)
- Additive key in `signals.enrichment_data`: `"quarantine": {"reason": "DEF-CVD-QUARANTINE", "class": "mispriced|correct_priced_phantom", "at": "<UTC>", "brief": "2026-07-22-def-cvd-quarantine"}`. **No existing field overwritten; `signal_id` never touched** → `signal_outcomes` never orphaned.
- **Reversal = one statement:** strip the `quarantine` key. Pre-image JSONL (§5c) is the full-restore backstop.

### 5b. Default-exclude from every read — TIERED (ATLAS #4, inventory-verified)
**Premise correction:** there is **no central signals filter to piggyback on.** `is_test` has **0 occurrences** in `backend/` — it was never built (it is queued as **W1-3**, whose own scope assumed a `get_trade_rows()` chokepoint the inventory proves does not exist). `feed_service.get_active_trade_ideas` is a chokepoint for the committee + grouped feed only, not a universal builder.

**Inventory (verified):** `hub_get_trade_ideas` is the **only** signals-reading hub tool (→ feed_service); the other 20 `hub_get_*` tools are signals-free — so **the committee surface is secured by one feed_service edit.** ~10 other raw read paths query `signals` directly (REST `/trade-ideas` flat+tier, 3 legacy `postgres_client` readers behind `/signals/active`, `board_state`, `analyzer`, `hydra`, `confluence`), plus ~4–6 grading/analytics paths.

**TIER A (this remediation — ~4 files, one deploy):**
- **`feed_service` conditions[] one-liner:** `enrichment_data->'quarantine' IS NULL` — secures the committee (`hub_get_trade_ideas`) + grouped feed. **This creates the first central visible-signals predicate.**
- **Grading exclusion:** same predicate into `outcome_resolver` (base_query) and `score_signals` (PROJECTED). A code edit, not status-based: 80 CVD outcomes were graded and persist on now-DISMISSED rows, so status alone doesn't gate. Log a skip count.
- **Reconstruct guard:** `scripts/quarantine_enrich_clobber.py` predicate `+= AND signal_category IS DISTINCT FROM 'CRYPTO_CVD_EVENT'` — so a re-run cannot bury the quarantine key (ATLAS #2 mitigation, accepted).

**TIER B — SIGNALS-READ-LAYER (new named build, NOT this remediation):** the canonical visible-signals predicate generalized across the remaining ~10 raw read paths, **delivering `is_test` (W1-3) in the same sweep.** Scheduled **only if reconciliation + breakout_prop land first this week; otherwise first post-vacation** — a 15-path read-layer deploy days before an 11-day no-code window is the exact pattern being avoided. Until Tier B, those ~10 dashboard/analytics/REST paths still surface quarantined rows; acceptable because the committee surface is secured (Tier A) and the 13 currently-ACTIVE rows self-age within 24h with the detector dark.

### 5c. Pre-image JSONL (immediately before the write, frozen set)
- Dump the full pre-state of all quarantined `signals` rows + their `signal_outcomes` rows (11 fields + `signal_id` + full `enrichment_data`) to a timestamped JSONL under `backend/database/archive/`. Restore artifact + ATLAS evidence. **Taken AFTER the detector is disabled** (§8) so the snapshotted set is frozen.

### 5d. Detector disable-pending-fix — no-bounce config sentinel (ATLAS #3)
ATLAS #3's core requirement is a **no-bounce, config-hot disable**. The named `cvd_events_enabled` flag this brief originally assumed **does not exist in code** — `_detect_cvd_events` ([crypto_tape_health_engine.py:247-250](../../backend/bias_filters/crypto_tape_health_engine.py#L247)) reads only *thresholds*, no gating boolean; and the hot-reload table is **`crypto_cycle_config`** (`get_cycle_config()`, 60s TTL, append-only), not `crypto_gate_config`. So the option that satisfies ATLAS #3 **as reviewed** is:
- **Option A (chosen) — SENTINEL threshold-hack.** Set `crypto_cycle_config.cvd_events.absorption_cvd_threshold_usd = 1e15`. Divergence is already dead (§6) and absorption requires `|cvd_net| ≥ threshold`, so nothing fires. Config-only, hot-reloaded ≤60s, **no restart**, one-INSERT reversible, surgical (kills CVD event firing; leaves `crypto_tape_health_log` — the committee tape block — computing). **A is not a substitute for what ATLAS reviewed: the no-bounce config-hot disable is the condition; the named flag was an assumed implementation detail that turned out absent. B is the deviation.**
- **Option B (rejected) — add the `enabled` flag in code.** Requires a Railway deploy = the exact restart/transient-stale window ATLAS #3 exists to avoid. The clean flag belongs in the detector redesign, not now.
- **R1 — sentinel proven numeric (before the flip).** Stored as a JSON **number** (`jsonb_typeof = number`, value `1000000000000000`) so the loader's `json.loads` yields a Python number and `abs(cvd_net) ≥ 1e15` is a clean numeric compare that never fires — no string, no throw, no fire-on-everything fallback. **Applied 2026-07-23 as `crypto_cycle_config` id=5 (baseline id=4). RESTORE = re-INSERT config with `absorption_cvd_threshold_usd = 50000`.**
- **R2 — exit gate (empirical).** After the flip, wait ≥2 detection cycles past the 60s TTL, then confirm **zero new `CRYPTO_CVD_EVENT` rows** AND `crypto_tape_health_log` still writing. Only then pre-image (ATLAS #1).
- **Redesign requirements** (the fix the disable is pending):
  1. **Divergence branch is mathematically dead** ([crypto_tape_health_engine.py:279-281](../../backend/bias_filters/crypto_tape_health_engine.py#L279-L281)): `current_price = recent[-1][4]` (a close) is compared to `max/min` of a `window` that **includes recent[-1] itself** → a bar's close is bounded by its own high/low → `is_local_high/low` ~never true → CVD_DIVERGENCE ~never fires (0/272). Fix: compare the current bar's **high/low** vs the **prior** window (exclude the current bar).
  2. **Proximity is tautological** (line 276): `current_price` ∈ the bars that build POC/VAH/VAL and the 6h VA is ~0.6–0.8% wide → ~always within `proximity_pct` of a level. Fix: test proximity against structure not built from the current bar.
  3. Reconcile the **6h window** length (deferred PYTHIA methodology question).

### 5e. CLOBBER-SURVIVAL — the marker must survive every enrichment_data writer (ATLAS #2)
The marker lives in `enrichment_data`, the one column with a documented wholesale-overwrite history (DEF-ENRICH-CLOBBER). Every writer must **merge**, not reconstruct. Enumerated (backend):
- `signal_enricher.py:282` `persist_enrichment` — `COALESCE(enrichment_data,'{}'::jsonb) || $2::jsonb` — **MERGE ✓** (post-INSERT enrichment; short-circuits for crypto via the asset gate, so it does not re-touch historical CVD rows).
- `api/signals.py:95` (accept/pass/watch action) — `COALESCE(...) || jsonb_build_object('nick_decision', …)` — **MERGE ✓**.
- Producer paths (`tradingview.py:155`, `crypto_tape_health_engine.py:374`, `crypto_setups.py:112/512/544`) — build the in-memory dict at signal creation and flow through `persist_enrichment` (merge); they do **not** UPDATE historical rows.
- **Phase 0 condition:** re-run this enumeration at execution across `backend/` **and `scripts/`** and any raw SQL, and confirm **zero reconstruct-style** `SET enrichment_data = <new>` writers exist. If any is found, it must be converted to a merge (or excluded) before the quarantine write. Load-bearing.

---

## 6. Evidence: the detector is broken independent of pricing (ruling-2 basis)

Confirmed against [crypto_tape_health_engine.py:259-305](../../backend/bias_filters/crypto_tape_health_engine.py#L259-L305):
- **272/0** ABSORPTION/DIVERGENCE lifetime (Postgres-verified) — never once the other branch.
- **Divergence dead:** close-vs-window-highs-including-own-bar (§5d.1) — ordering-independent; the source sort does not change it.
- **Absorption tautological:** current_price ∈ the VP-building window + narrow VA → always "near a level"; every row has `entry_price ≈ cvd_level_price` (BTC 63137.75 ≈ POC 63099).
- **Net:** the detector reduces to *"if |net CVD| ≥ 50k, emit ABSORPTION at the current bar"* — the structural framing is fabricated. The source sort fixed only the price label.

---

## 7. Predicate + the +6h timestamp gotcha

- **Predicate:** `signals WHERE signal_category = 'CRYPTO_CVD_EVENT'` (272), cascade to `signal_outcomes ON signal_id`. **Key on `signal_category`, not a timestamp literal.**
- **⚠ +6h gotcha:** the postgres MCP renders `signals.timestamp`/`created_at` **+6h ahead of the true instant** (serialization/tz; `now()` and `now()-col` arithmetic are correct). Any time bound must be computed by arithmetic against `now()`, **never a displayed literal** — else it selects a 6h-wrong window. (The audit's "first row 2026-07-18T23:03Z" is really ~17:03Z.) If a bound is added, state the column and account for DEF-SIGNAL-METADATA's offset.

---

## 8. Execution phases (ATLAS-ordered; current state marked)

Per **ATLAS #1**, disable lands before the pre-image.

- **Phase 0 — inventory + dry-run — ✅ DONE.** Read-path inventory (§5b) + `enrichment_data` writer enumeration (§5e) + count (349, category-keyed). Contradictions surfaced and ruled: no central filter → Tier A/B split (§5b); one reconstruct writer → guarded (§5e).
- **Phase 1 — DISABLE — ✅ DONE (pending R2).** `crypto_cycle_config` id=5 sentinel (§5d).
- **Phase 2 — R2 exit gate.** ≥2 cycles past the 60s TTL → confirm **zero new CVD rows** + `crypto_tape_health_log` still writing. Set frozen.
- **Phase 3 — pre-image JSONL** of the frozen set (§5c).
- **⛔ STOP — Nick's `--i-have-go`** (the marker write is the first destructive step).
- **Phase 4 — marker write:** additive `enrichment_data.quarantine` (+ `quarantine_class`) on the frozen CVD set, via psycopg2. Reversible; pre-imaged.
- **Phase 5 — Tier A deploy:** `feed_service` filter + grading exclusion (`outcome_resolver`, `score_signals`) + `quarantine_enrich_clobber` predicate guard. ~4 files, one deploy.
- **Phase 6 — verify + reversal rehearsal** (test population = the 349): `hub_get_trade_ideas` returns **zero** CVD rows; grading job logs a **skip count**; `signal_outcomes` join intact (no orphans); ZEC queryable as `correct_priced_phantom`; reversal rehearsed against the pre-image.

**TIER B (SIGNALS-READ-LAYER)** — the ~10 remaining raw read paths + `is_test` (W1-3) — is a **separate named build**, scheduled per §5b (this-week only if reconciliation + breakout_prop land first; else post-vacation).

---

## 9. Out of scope (flag, do not fold in)

- **yfinance bare-ticker data-quality** — filed as its own backlog row (workstreams): bare `'BTC'`/`'ETH'` PROJECTED rows show degenerate `max_favorable/max_adverse`; crypto COUNTERFACTUAL effectively ungraded (bare tickers empty in yfinance). Value/coverage, not vendor-order.
- **6h→24h VP window** — deferred PYTHIA methodology call.
- **Alert-floor recalibration** — postponed past vacation; the n=55 sample is now dead on both halves (Session_Sweep −5 + CVD phantom).
- yfinance `iterrows()` walks rely on implicit ascending order (not a defensive sort) — code-hardening note, not a corruption risk.

---

## 10. ATLAS — PASS WITH FOUR CONDITIONS (all folded in)

1. **Reorder phases** — disable before pre-image. → §8 (Phase 1 disable → Phase 2 pre-image).
2. **Clobber-survival** — enumerate every `enrichment_data` writer, confirm merge-not-reconstruct. → §5e (both direct UPDATEs merge; Phase 0 re-confirms completeness incl. `scripts/`).
3. **No-bounce config-hot disable**, not env var (avoid the restart-induced transient-stale window). → §5d **Option A**: `crypto_cycle_config` sentinel (`absorption_cvd_threshold_usd=1e15`, hot-reload ≤60s, no restart, applied as id=5). The assumed `cvd_events_enabled` flag does not exist in code — **A satisfies the condition as reviewed; B (code flag + deploy) is the deviation.** R1 parse proof + R2 empirical gate folded into §5d.
4. **Read-path inventory is evidence** — enumerated bypass list with per-path verification, `hub_get_*` included. → §5b + done-def #2.

**Standing rule:** any contradiction encountered mid-execution = stop and report.

---

## DONE DEFINITION
1. Detector disabled (Phase 1) via the DB config row — no new CVD rows accrue.
2. Read-path inventory produced as **evidence**: every path enumerated + per-path verified excluded (`hub_get_*` included).
3. Clobber-survival confirmed: every `enrichment_data` writer merges (backend + scripts).
4. Pre-image JSONL of the frozen 272 written and validated restorable.
5. Quarantine written; quarantined rows absent from every read + grading; `quarantine_class` set (211 mispriced / 61 ZEC); no orphaned `signal_outcomes`.
6. Reversal rehearsed against the pre-image.
7. **No data mutated before Nick's explicit GO; phases executed in ATLAS order.**
