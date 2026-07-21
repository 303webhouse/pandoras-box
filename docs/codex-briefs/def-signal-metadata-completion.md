# DEF-SIGNAL-METADATA — Completion Report (reduced scope)

Date: 2026-07-21
Brief: `docs/codex-briefs/2026-07-21-def-signal-metadata-brief.md`
Phase 0 findings: `docs/codex-briefs/def-signal-metadata-phase0-findings.md`
Code commit: `e8ed614` (4 files, 11 new tests)
Railway deploy: SHA `e8ed614` — 4-step verification below

**Scope note:** this brief ran at reduced scope by explicit Nick+Fable decision (2026-07-21). Phase 0 had falsified two of the brief's three evidence points — S2 (`created_at` +6h) and S3 (`age_minutes` ~12h) were a `mcp__postgres__query` display artifact, not real bugs. The ratified scope: **(1)** fix the real `source` defect, **(2)** harden the two naive `datetime.now()` writer paths as defense-in-depth, **(3)** propose (not apply) a disposition for the `/api/analytics/log-signal` side door. No timestamp/age-computation logic was changed — Phase 0 confirmed it's correct.

---

## 1. Source provenance (S1 — the real defect) — FIXED

**Root cause:** `log_signal()`'s `INSERT INTO signals` (`backend/database/postgres_client.py`) never listed the `source` column, so the column's `DEFAULT 'tradingview'` stamped **every** row regardless of true origin — `SELECT DISTINCT source FROM signals` returned the single value `'tradingview'` table-wide.

**Fix:** added `source` as the 37th column/`$37`/bind arg, bound to `signal_data.get("source") or "tradingview"`. `process_signal_unified()` already sets `signal_data["source"]` to the true writer at `pipeline.py:1198` (`crypto_engine`, `cta_scanner`, `footprint`, `whale_hunter`, `crypto_scanner`, `crypto_cvd_engine`, `server_scanner`, `wh_reversal`, `wrr_scanner`; TradingView webhooks default `"tradingview"`), and that value survives unmutated to the `log_signal()` call — it was simply being dropped at the INSERT. The `or "tradingview"` fallback preserves the prior column-default behavior only for the (unused) direct `/log-signal` caller, which supplies no source.

**No schema change** — the column and its DEFAULT already exist; this only populates it. Brief constraint honored (no ATLAS flag needed for populating an existing column).

**Historical backfill: NOT applied (DECISION GATE).** New rows carry real provenance from deploy forward; the ~15k historical rows keep `'tradingview'`. A proposed `strategy → source` backfill mapping is in §4 below — it is **not** applied and should not be without explicit approval (data migration; ATLAS flag if pursued), especially because the mapping is genuinely ambiguous for a few strategies (see §4).

## 2. Timestamp hygiene — HARDENED (defense-in-depth)

The naive `datetime.now()` calls that feed a persisted signal field were changed to `datetime.now(timezone.utc)` in both writers Phase 0 flagged:
- **`backend/webhooks/tradingview.py`**: 7 signal `timestamp` fallbacks + 7 `signal_id` date/time components (`SCOUT_`/`HG_`/`ARTEMIS_`/`PHALANX_`/directional ids).
- **`backend/scanners/cta_scanner.py`**: 9 signal `timestamp` fields + 2 `TRAPPED_*` `signal_id` date components.

These were correct only by virtue of Railway's container clock being UTC; they're now correct regardless of host timezone. `datetime.now()` uses left as-is (deliberately, not signal-row fields): `scan_time` scan-metadata (×3) and a `start_time`/`elapsed` duration measurement (naive−naive, correct). This is a latent-robustness fix, not a live-bug fix — no observed data was wrong.

## 3. Adversarial verification (pre-deploy)

Because this touches `log_signal()` — every signal write — a 2-agent adversarial pass ran on the diff before deploy. Both cleared it with **no blockers**:
- **INSERT binding:** 37 columns / 37 placeholders / 37 bind args, exact 1:1 alignment confirmed — no positional corruption of any prior column.
- **`source` consumers:** the *only* reader of `signals.source` is `analytics/confluence_validation.py::compute_shadow_validation` — it was **already degenerate** (its `server_rows` query expects `'holy_grail_scanner'/'scout_scanner'/'SCANNER'`, which no row ever carried, so it matched zero rows) and **stays degenerate** after the fix (the real server-scanner value is `'server_scanner'`, still not in its IN-list). Its verdict was already meaningless (0 overlap by construction) and stays so. Classification: "already broken, stays broken" — **not a regression**. Flagged as a follow-up in §5. `analytics/health_monitor.py` is fully unaffected (groups by strategy/signal_type, never reads the `source` column).
- **Fallback safety:** every automated writer passes a non-empty `source`, so `or "tradingview"` never clobbers a real value; only the unused `/log-signal` manual endpoint hits it (identical to prior default).
- **Timestamp:** no aware/naive arithmetic breakage (every hardened value is immediately `.isoformat()`/`.strftime()`'d to a string); `_normalize_timestamp_for_db` handles the now-present `+00:00` suffix identically (parses aware → converts to UTC → strips tzinfo → same instant, no shift). One consistency gap the pass flagged (tradingview `signal_id` strftime components) was **fixed in the same commit**.

## 4. PROPOSAL (not applied) — historical `source` backfill mapping

Per the brief's decision-gate, a proposed `strategy → source` mapping for the ~15k historical rows, **with confidence flags**:

| strategy | proposed source | confidence | note |
|---|---|---|---|
| CVD_ABSORPTION | `crypto_cvd_engine` | HIGH | single producer |
| Session_Sweep | `crypto_engine` | HIGH | single producer (crypto_setups) |
| Crypto Scanner | `crypto_scanner` | HIGH | single producer |
| CTA Scanner (PULLBACK_ENTRY/BEARISH_BREAKDOWN/…) | `cta_scanner` | HIGH | single producer |
| Footprint_Imbalance | `footprint` | HIGH | single producer (webhook) |
| Whale_Hunter | `whale_hunter` | HIGH | single producer |
| sell_the_rip | `server_scanner` | HIGH | Achilles server scanner |
| **Holy_Grail** | ambiguous | **LOW — DO NOT BACKFILL** | fires from BOTH the TV webhook (`tradingview`) AND the server-side `holy_grail_scanner` (`server_scanner`); strategy alone can't disambiguate |
| **Scout / Scout Sniper** | ambiguous | **LOW — DO NOT BACKFILL** | same dual-origin problem (webhook vs `server_scanner`) |
| **Artemis** | ambiguous | **MEDIUM** | believed webhook-only (`tradingview`) but not proven exhaustively |

**Recommendation:** if a backfill is pursued at all, apply only the HIGH-confidence single-producer strategies and **leave the ambiguous ones as-is** (`'tradingview'`) rather than guess — the dual-origin strategies (Holy_Grail, Scout) are exactly the ones `confluence_validation` cares about, so a wrong backfill there would be worse than the honest-but-stale default. Forward-fill (new rows, already done by this fix) is unambiguous and sufficient for going-forward provenance.

> **RULING (Nick + Fable, 2026-07-21): NO — declined permanently.** No historical backfill will ever be performed. Rationale: `strategy` already identifies the producer without inventing anything, and a backfill would write *inferred* values into a column that otherwise holds *recorded* values, making the two permanently indistinguishable. Instead, the strategy→producer mapping and the `e8ed614` provenance cutline are documented at **`docs/reference/signal-provenance.md`**.
>
> **One correction recorded in that doc**, since it strengthens rather than weakens the ruling: `strategy` is *not* quite lossless. `Holy_Grail` and `Scout Sniper` are **dual-origin** — `scanners/holy_grail_scanner.py:224,255` and `scanners/scout_sniper_scanner.py:312` emit the identical `strategy` string that `webhooks/tradingview.py:438,340` does — so for those two, `strategy` alone cannot tell you which side produced a row. That is precisely the class where a backfill would have had to guess, so the "no backfill" outcome is right; only the "losslessly" premise needed the footnote. Post-cutline, `source` resolves it cleanly (`server_scanner` vs `tradingview`); pre-cutline it is unrecoverable, and that is now documented rather than papered over.

## 5. PROPOSAL (not applied) — `/api/analytics/log-signal` side-door disposition

**Finding:** `POST /api/analytics/log-signal` (`backend/analytics/api.py:2072-2087`) calls `log_signal()` directly, bypassing `process_signal_unified()` (skips scoring, feed-tier classification, gate evaluation, dedup, outcome-record writing, Discord/WS broadcast, committee flagging). It's `require_api_key`-gated, self-tags `triggering_factors.bypass_source = "analytics_log_signal_endpoint"`, and shows **zero rows** carrying that tag — i.e. live/callable but never actually used since the tag was added (`1e27d11`, 2026-06-18). It's the sole remaining `log_signal()` side door; no SQL-level side door into `signals` exists anywhere else.

**Options:**
- **(A) Remove the endpoint** (recommended) — it's unused dead code that bypasses the entire F-4 governance chokepoint; deleting it + its auth test closes the last bypass. Lowest ongoing risk.
- **(B) Reroute through `process_signal_unified()`** — if a manual/external signal-insert capability is genuinely wanted, make it a first-class writer (pass `source="manual_api"`) so it inherits scoring/gating/dedup like everything else.
- **(C) Leave as-is** — harmless today (unused, self-tagging), but it's a standing hole that a future caller could use to inject ungoverned rows.

**Recommendation: (A) remove**, or (B) if the capability is wanted.

> **RULING (Nick + Fable, 2026-07-21): REMOVE — done, commit `982257c`.**
> Removal precondition required by the ruling was verified first and came back clean: **zero callers** in `frontend/`, in `scripts/`, or anywhere on the VPS (`/opt/openclaw/workspace/`, `/home/openclaw/.openclaw/`, `/opt/pivot/`) — the only references in the entire repo were the route definition itself and one auth-test case. Combined with the zero rows ever carrying its `bypass_source` tag, nothing has ever called it.
> Removed: the endpoint, the `LogSignalRequest` model, the now-dead `log_signal` import in `analytics/api.py`, and the route's parametrized auth-test entry. An in-place comment at the removal site records what was removed, why, and how to reinstate it correctly (routed **through** `process_signal_unified(source="manual_api")`) if the capability is ever wanted.
> **Recoverability: commit `982257c`** (also recorded in `docs/workstreams.md` per the ruling). This closes the last side door around F-4's chokepoint — every remaining writer now routes through `process_signal_unified()`.

## 6. Follow-up flagged (out of scope, not fixed)

`analytics/confluence_validation.py::compute_shadow_validation` has a **stale source vocabulary**: its queries expect `'holy_grail_scanner'/'scout_scanner'/'SCANNER'` but the pipeline emits `'server_scanner'`, so the tool has never produced a meaningful verdict (server_rows always 0). Now that `source` carries real values, this tool *could* be made functional by aligning its query literals to the actual vocabulary (`'server_scanner'`) — a small, separate fix, not in this brief's scope. Note the dual-origin ambiguity (§4) means even a fixed query can't perfectly separate webhook-Holy_Grail from server-Holy_Grail without a finer-grained source than `'server_scanner'`.

## 7. Tests

11 new tests (`backend/tests/test_def_signal_metadata.py`): source persisted for each writer, source fallback when absent/None, `_normalize_timestamp_for_db` correctness on aware-UTC / `Z` / non-UTC-aware inputs (proving the write path stores the correct instant from the now-aware writers), and static regression guards asserting no naive signal-`timestamp` or `signal_id`-date pattern remains in either writer. Full suite: `18f/1s/203e` unchanged from baseline, passed 464 → 477.

## 8. Deploy verification (PROJECT_RULES.md 4-step standard)

1. **Railway status SUCCESS.**
2. **SHA `e8ed614` exact match** to the pushed commit.
3. **Live empirical proof:** the first signal written by the new container — `id=15678`, `strategy='CTA Scanner'`, **`source='cta_scanner'`**, `created_at 2026-07-21 17:23:13 UTC` — carries its real provenance. Before this fix, that same row would have been stamped `'tradingview'` like every other row in the table. The `source` column now reflects the true writer for new rows.
4. **No errors** in Railway logs referencing the INSERT / `source` column / any integrity or column error post-deploy (the new `$37` column binds and executes cleanly, proven by the row landing).

## 9. Constraints honored

Investigation-first (Phase 0 findings committed before any edit). No schema change (existing column populated). Pathspec-only commit — a concurrent lane's theme-members-rerank work was in the tree and deliberately left unstaged. Adversarial pre-deploy verify on the hot path. Historical backfill and the side-door disposition proposed but NOT applied, per the brief's decision gates.
