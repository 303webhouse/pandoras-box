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

## 2. Blast radius — all 272 quarantined

`signal_category = 'CRYPTO_CVD_EVENT'` — **272 rows as of 2026-07-22 (growing until the detector is disabled)**, all `CVD_ABSORPTION`, **0 `CVD_DIVERGENCE` lifetime**:

| Symbol | Vendor | Rows | `quarantine_class` |
|--------|--------|------|--------------------|
| BTC | UW (desc) | 79 | `mispriced` |
| ETH | UW (desc) | 64 | `mispriced` |
| HYPE | OKX (desc) | 48 | `mispriced` |
| SOL | UW (desc) | 20 | `mispriced` |
| ZEC | Binance (asc) | 61 | `correct_priced_phantom` |
| **Total** | | **272** | **211 + 61** |

**80 graded outcomes** (BTC 43, ETH 37) carry propagated-wrong verdicts. The **73 "burst" rows** (Nick ruled KEEP) are a subset — §3 ruling 1.

---

## 3. Rulings baked in (Fable, 2026-07-22)

**Ruling 1 — QUARANTINE-EXCLUDE (not rewrite, not purge).** Additive marker, default-excluded from every read, excluded from grading, pre-image JSONL, one-line reversible. Precedent ×3: `is_test`, `cvd_dedup_burst`, `quarantined_equity_clobber`.
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

### 5b. Default-exclude from every read — READ-PATH INVENTORY IS EVIDENCE (ATLAS #4)
- **Central filter:** add `enrichment_data->'quarantine' IS NULL` to the canonical signals read path (`feed_service` builder), exactly as `is_test` is filtered centrally — every downstream read inherits exclusion from one place.
- **Mandatory evidence for the done-definition:** an **enumerated list of every read path**, each marked filtered-centrally or filtered-individually, with per-path verification. **`hub_get_*` MCP tools are the committee-facing surface and MUST be in the list.** Candidates to enumerate + verify: `feed_service`, `signal_notifier.py`, `api/committee_bridge.py`, `analytics/api.py`, `analytics/oracle_engine.py`, `api/trade_ideas.py` + `hub_mcp/tools/trade_ideas.py`, `hub_mcp/tools/*` reading signals, `discord_bridge/bot.py`. Any path bypassing the canonical builder gets its own filter. **Do not assume central coverage — prove it.**
- **Grading exclusion:** `outcome_resolver` and `score_signals` must skip quarantined rows so their (already-wrong) outcomes stop accruing/re-grading.

### 5c. Pre-image JSONL (immediately before the write, frozen set)
- Dump the full pre-state of all quarantined `signals` rows + their `signal_outcomes` rows (11 fields + `signal_id` + full `enrichment_data`) to a timestamped JSONL under `backend/database/archive/`. Restore artifact + ATLAS evidence. **Taken AFTER the detector is disabled** (§8) so the snapshotted set is frozen.

### 5d. Detector disable-pending-fix — DB CONFIG ROW, not env var (ATLAS #3)
- **Halt via a DB config flag, not an env var.** An env-var change forces a Railway restart, which triggers the known transient-stale window across every in-process crypto asyncio writer (cycle/regime/tape). Use the **`crypto_gate_config` hot-reload pattern**: add a `cvd_events_enabled` key (default currently-true; set **false** to disable). The tape engine reads it per cycle via `get_gate_config()`, so it flips **without a bounce** — phone-flippable via a single DB write, no surface restart.
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

## 8. Execution phases (ATLAS-ordered; each ATLAS condition is a stop-gate)

Reordered per **ATLAS #1** — disable lands **before** the pre-image so no rows accrue between snapshot and write:

1. **Phase 0 — inventory + dry-run (no writes).** Enumerate every read path (§5b, evidence) + every `enrichment_data` writer (§5e, confirm all merge). Count-only predicate check (expect ~272 + the §2 symbol breakdown).
2. **Phase 1 — DISABLE the detector** via the `crypto_gate_config` DB row (§5d). Confirm no new CVD rows accrue. **The row set is now frozen.**
3. **Phase 2 — pre-image JSONL** of the frozen set (§5c).
4. **Phase 3 — quarantine write:** central read-filter + additive marker (with `quarantine_class`) on the frozen set + grading exclusion. `--i-have-go` required.
5. **Phase 4 — verify:** quarantined rows absent from every enumerated read path (committee/`hub_get_*`, notifier, feed, analytics) + from grading; `signal_outcomes` join intact (no orphans); ZEC queryable as `correct_priced_phantom`; reversal rehearsed against the pre-image.

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
3. **DB config row for the disable flag**, not env var (avoid the restart-induced transient-stale window). → §5d (`crypto_gate_config` hot-reload, `cvd_events_enabled`).
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
