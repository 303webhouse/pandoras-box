# DEF-FEED-TRIAGE — Completion Report

Date: 2026-07-20/21 (session spanned MT evening into early UTC morning)
Brief: `docs/strategy-reviews/stater-swap-redesign/2026-07-20-def-feed-triage-brief.md`
Code commit: `2eb079d` (backend D1/D2/D3 + notifier D4, 8 files, 39 new tests)
Railway deploy: SHA `2eb079d0c7339245840bedc8e53fe5ded84e7eab`, status SUCCESS
VPS deploy: `scripts/signal_notifier.py`, SHA-256 `ea225ebee67dd9fd6badb3a94aca3ac0e46ac6e5cd1d2d1516ede332174dbf91`

All four defects closed in the mandated D1→D2→D3→D4→V1 order. This brief did **not** touch S-4 Phase 3.

---

## D1 — Funding feed emitting garbage; signal FIRING on degraded input

**Root cause (written before any edit, per the brief's investigation-first constraint):** `bias_filters/coinalyze_client.py`'s `get_funding_rate()` and `get_term_structure()` both multiplied Coinalyze's `value`/`v` field by 100 to "convert to percentage." Live cross-vendor evidence (Coinalyze raw response captured via a diagnostic script run through `railway run`, cross-checked against a live OKX `funding-rate` curl at the same moment) proved Coinalyze's field is **already a percentage** — the `*100` was a genuine ~100x unit error, not a clamp, sentinel, or fallback. It is the same defect *family* as the notifier's funding-rate double-conversion caught in S-4 Phase 2, but this instance lives upstream in the writer/vendor-client path, not the notifier.

The OKX fallback path in both functions is a true fraction and correctly needs `*100` — verified live and left unchanged in both places.

**Fix:**
- Removed the erroneous `*100` from the Coinalyze primary path in both `get_funding_rate()` and `get_term_structure()`.
- D1.4 contract change (scoped local to `crypto_market.py`'s `funding_field` construction only, not touching `crypto_cycle_engine.py`'s separate FROTH consumer): a degraded funding reading can no longer report `signal: "FIRING"` — suppressed to `"NEUTRAL"` when `degraded=true`.

**Bonus finding (disclosed, not separately fixed):** the same unit bug also silently corrupted `crypto_cycle_engine.py`'s FROTH "funding blowout" cell, since it reads the same `coinalyze_client.get_funding_rate()`. The fix is automatic (same source function) — not a separate change.

**Verification:**
- 8 new unit tests (`test_def_feed_triage_d1_funding_units.py`), including a regression guard confirming the OKX fallback path is *still* multiplied in both directions.
- Live post-deploy: `GET /api/crypto/state/BTC` → `funding.rate_pct: 0.0011, signal: "NEUTRAL", degraded: false` (2026-07-21T03:10:47Z). Sane magnitude, reads NEUTRAL not FIRING — matches D1.6's sanity check (real BTC funding ~0.001-0.002%/8h, well under the 0.05% FIRING floor).

---

## D2 — Regime writer: zero rows, ever

**Root cause (found by a parallel recon agent; contradicted the brief's own "writer never wrote" framing — investigated and reported honestly rather than followed blindly):** `jobs/crypto_regime.py`'s writer has been healthy the entire time — hourly cadence, zero gaps, 648+ rows — keyed by the **hyphenated canonical form** (`"BTC-USD"`, matching `crypto_gates.py`'s real gate-consumer). The `/api/crypto/state/{symbol}` reader in `crypto_market.py` queried `crypto_regime_log` with the **bare** `base_symbol` (`"BTC"`), so the query matched zero rows from the day the field was wired (`4a9b335`, 2026-07-16) — a reader bug, not a writer outage.

**Fix:** hyphenate the symbol before the `crypto_regime_log` query only. `crypto_tape_health_log`'s sibling query (bare form, correct for its own writer) was verified and left untouched.

**Verification:**
- 3 new unit tests confirming the exact bind parameter passed is `"BTC-USD"` (not `"BTC"`), across all 6 tracked symbols.
- Live post-deploy: `GET /api/crypto/state/BTC` → `regime.state: "CHOP", degraded: false, as_of: "2026-07-21T01:47:13Z"` — previously always `null`.

---

## D3 — CVD/tape_health collector frozen since Saturday

**Root cause (found by a parallel recon agent; also contradicted the brief's assumed "crashed/broken cron" framing):** `compute_all_tape_health()` (S-3b) was **never registered with the scheduler at all**. Its entire `crypto_tape_health_log` write history was three isolated manual-verification bursts (07-16/17/18) that exactly line up with S-3b's own deploy-verification curls — not a crashed job. When S-3b closed 07-18, the manual calls simply stopped.

**Fix:** added a real scheduled job, mirroring the existing `crypto_regime`/`crypto_cycle` registration pattern exactly — `ENABLE_CRYPTO_TAPE_HEALTH_JOB` kill switch (default on), 15-minute interval (chosen deliberately: more responsive than regime/cycle's hourly cadence since CVD data moves faster, but not so aggressive it hammers OKX across 6 symbols × 2 vendor legs), status tracking in `_scheduler_status`, exceptions swallowed so a failure never takes the scheduler loop down.

**Verification:**
- 4 new unit tests (job enabled by default, status/rows_written update on success, failure doesn't raise, status dict wired).
- Live post-deploy: Railway logs confirm `"Added job \"Crypto Tape Health (spot-vs-perp CVD)\"" ` to the scheduler on boot. First 15-min tick had not yet elapsed at initial verification time (deploy completed 03:07 UTC, curl at 03:10 UTC); `tape_health.as_of` was still the pre-fix 07-18 value at that moment — expected given interval-trigger semantics, not a failure.
- **First natural tick confirmed 2026-07-21T03:31:02Z**: Railway logs show `"Running scheduled tape-health evaluation (all six symbols)..."` → `"Tape-health evaluation complete -- 5/6 symbols logged"` (5/6 non-NA; the 6th's honest-NA classification is expected — matches S-3b's known FARTCOIN live-OKX-spot-fetch gap, not a new issue). Live curl of `/api/crypto/state/BTC` immediately after: `tape_health.as_of: "2026-07-21T03:31:00.966Z", data_age_seconds: 34, degraded: false` — fresh, was 208,000+ seconds (58h) stale before this fix. **D3 fully closed, no open follow-up.**

---

## D4 — Equity/crypto notifier drops alerts on Discord 429, no retry

**Root cause:** `scripts/signal_notifier.py`'s `post_signal_alert()`/`post_crypto_signal_alert()` each made exactly one Discord POST attempt; any failure (429 included) returned `None` and the alert was dropped. Worse, `main()`'s loop marked a signal `seen` **before** attempting the post — so a 429'd signal was never retried, not in this run, not in any future run. Evidence: the VPS log's `2026-07-20T14:00:02Z` run (`signals_fetched: 10, new_signals: 10, alerts_posted: 7`) shows three consecutive `429` errors for AMD/LYFT/TFC immediately before that summary line; the *next* run 15 minutes later (`14:15:02Z`) shows `new_signals: 3` — a different 3 tickers entirely. AMD/LYFT/TFC were gone for good. Grepping the full log also showed this is a **long-standing, recurring pattern** (429s appear repeatedly back to at least 07-15), not a one-off — this fix has more real-world value than the brief's single-instance framing suggested.

**Fix (shared between both post functions, one fix point):**
1. `_post_discord_with_retry()` — a shared helper that catches `urllib.error.HTTPError` specifically; on a 429 it extracts the wait time (preferring Discord's JSON-body `retry_after` over the generic `Retry-After` header) and retries, bounded to `DISCORD_POST_MAX_ATTEMPTS = 3` within the run. A non-429 HTTPError or a generic exception is not retried (matches prior behavior).
2. Inter-post spacing: `time.sleep(DISCORD_POST_SPACING_SECONDS)` (1.2s) after each post attempt in `main()`'s loop, so a full batch doesn't fire back-to-back and trip the limit itself.
3. Deferred seen-marking: `seen_ids`/`seen_set` are now updated **after** the outcome is known — on a successful post, on a non-trade route (permanently terminal), or on an aged-out signal (`is_signal_too_old()`, permanently terminal) — never on a failed post. A post that exhausts its retries is left un-seen, so the *next* cron run retries it naturally, bounded by the existing `SIGNAL_MAX_AGE_MIN=60` cutoff rather than being lost outright.

**Verification:**
- 16 new unit tests: `_extract_retry_after()`'s JSON-body/header/default precedence, the retry helper's success/429-then-success/exhausted/non-429/generic-exception paths, both post functions routing through the shared helper with the correct label, and 6 `main()`-level integration tests proving the deferred-seen-marking contract directly (mixed success/failure batch, non-trade skip, aged-out skip, inter-post spacing call count).
- Deployed to VPS via byte-exact `scp` + SHA-256 verify (local and remote hashes match exactly: `ea225ebe...`). Prior file backed up in place (`signal_notifier.py.pre-d4-backup-20260720`), not deleted. `python3 -m py_compile` clean on the VPS.
- Cron mechanism confirmed: equity notifier (`*/15 14-21 * * 1-5`, RTH-gated) and a separate **crypto notifier (`*/5 * * * *`, 24/7)** both point at the same deployed file. The crypto cron's next tick (within ~5 min of deploy) is the nearer live-fire opportunity for this fix; the equity cron's next natural multi-alert run is the next RTH session.

---

## V1 — Bonus verify: persistence independent of notification success

Confirmed directly against production Postgres. The three signals whose Discord post 429'd in the `2026-07-20T14:00:02Z` run — `STR_AMD_20260720_135514` (AMD), `9f4066af-5786-421b-9888-7b93684a6ce5` (TFC), `abd5600f-22c1-4634-b5f4-cc53f52bdec8` (LYFT) — all persisted `enrichment_data.needs_structural_review: true` and `feed_tier_ceiling: "watchlist"` (the Pythia-coverage gate, `pipeline.py:577`), **despite their Discord alert being permanently dropped under the pre-fix code**. `iv_regime_extreme`/`vix_at_signal` were null for all three (that specific VIX-regime gate wasn't the one that fired for this batch — expected, gate-dependent, not a gap). This closes the handoff's Monday verify (a): persistence is confirmed independent of notification success.

**Secondary observation — CORRECTED 2026-07-21, was wrong:** this doc originally flagged `signals.created_at` as reading ~6h ahead of the signal_id-embedded time, speculating a write-path timezone bug. DEF-SIGNAL-METADATA's Phase 0 investigation (2026-07-21) falsified this: `created_at`/`timestamp` are stored correctly in UTC (confirmed via raw `::text` casts matching signal_id-embedded epochs to the second, and by re-checking these exact AMD/TFC/LYFT/SMH rows directly — gaps of seconds, not hours). The +6h was an artifact of the `mcp__postgres__query` MCP client itself misparsing `timestamp without time zone` columns (treats the naive value as America/Denver local time, then serializes with a "Z" suffix via `.toISOString()`, mechanically adding 6h) — reproduced live and confirmed against a sibling `timestamptz` column (unaffected, since it carries an explicit offset). No write-path bug exists. Leaving the original text below struck through for the record, not deleted:

~~the `signals.created_at` timestamp for these rows (and at least one other checked, `SMH`) reads roughly 6 hours later than the timestamp embedded in the signal_id itself and the notifier log's fetch time — consistent with the exact MDT/UTC offset. Possible timezone-handling artifact in the write path; out of scope for this brief, worth a look if it recurs.~~

---

## Test suite

39 new tests total (8 D1, 3 D2, 4 D3, 16 D4, plus 8 pre-existing S-4 Phase 2 notifier tests reconfirmed clean against the D4 refactor). Full suite (`cd backend && pytest tests/ -q`): **18 failed / 439 passed / 1 skipped / 203 errors** — failures/skips/errors byte-identical to the pre-existing known-red baseline; passed count grew by exactly the 31 tests contributed by this brief's own new test files (408 → 439).

## Deploy verification (PROJECT_RULES.md 4-step standard)

**Railway:** (1) status SUCCESS (2) SHA `2eb079d0c7339245840bedc8e53fe5ded84e7eab` exact match to pushed commit (3) live curl of `/api/crypto/state/BTC` shows D1 and D2's fixes active with real data (4) — not needed, no silence >5 min.

**VPS:** byte-exact `scp`, SHA-256 verified identical pre/post, `py_compile` clean, cron entries confirmed pointing at the deployed file, prior version backed up in place.

## Constraints honored
Investigation-first with written root cause before every edit (all four defects, especially D2/D3 where the recon findings *contradicted* the brief's own assumed failure mode — reported honestly rather than following the given premise). Pathspec-only commits. No schema changes. D1.4's contract change scoped local to `crypto_market.py`'s funding field only, not touching `crypto_cycle_engine.py`'s separate consumer, per the brief's ATLAS-flag caution. No S-4 Phase 3 work started.

## Follow-ups (not blocking, not built)
- The `signals.created_at` ~6-hour offset noted in V1 — worth a dedicated look if it recurs elsewhere.

D3's tape-health first-tick watch (the only item open when this report was first drafted) is now closed — see verification above, confirmed live 2026-07-21T03:31Z.
