# DEF-ENRICH-CLOBBER — Fix Micro-Brief

**Date:** 2026-07-18 · **Author:** Fable (coordination lane) · **Review:** ATLAS Pass 1 — HIGH conviction, no veto
**Sequencing:** FIRST build slot 2026-07-18, before S-4 (ledger: `docs/workstreams.md` STATER-SWAP row).
**Boundary:** the L0-bypass defect (scanner paths skipping `process_signal_unified`) is SEPARATE and stays open — do not touch scanner routing in this build.

## Defect

`enrich_signal()` (`backend/enrichment/signal_enricher.py`) runs unconditionally for every signal at `backend/signals/pipeline.py:1447` (step 4c) and:

1. Routes CRYPTO tickers through the **equity** lookup stack — UW equity snapshot collides "BTC" with a ~$28 NYSE instrument; the yfinance fallback launders a plausible ~$65k price for hyphenated forms ("BTC-USD").
2. **Wholesale-replaces** `signal_data["enrichment_data"]` (line 137), destroying producer-built keys (`cvd_*`, `market_structure`, `event_reason`) and pipeline forensic flags (`needs_structural_review` @577; `iv_regime_extreme`, `vix_at_signal` @675-676) before persistence.
3. `persist_enrichment()` (:258-266) then writes the replaced dict with a full-replace `UPDATE`.

## Evidence (verified 2026-07-18, read-only prod query)

- 980 CRYPTO rows since 2026-03-01 = **148 equity-clobbered** (`enrichment_data ? 'avg_volume_20d'`) + 832 no-enrichment (the separate L0-bypass population).
- **0** CRYPTO rows have ever persisted `market_structure` or `cvd_level`.
- 4 rows @ ~$28.12 (ticker "BTC"); 3 rows @ ~$64,956 (ticker "BTC-USD" — accidentally correct via yfinance). **Quarantine keys on dict SHAPE, never price sanity.**
- Live-caught by CC in `4ca0980`; full account: `docs/strategy-reviews/stater-swap-redesign/s3b-items-1-2-completion-report.md`.
- Runtime gating is NOT affected (`feed_tier_ceiling` / `_score_ceiling_reason` are top-level keys; tier classifiers run at `pipeline.py:1227-1282`, pre-clobber). Damage class = persistence/audit-trail loss + wrong-asset pollution.

## Hard rules for this build

- Pathspec-only commits. Known-red suite baseline stays **byte-identical** (18f/1s/203e); passed count grows only by this brief's new tests.
- No scope creep: no crypto-native enrichment (S-4 territory), no scanner-routing changes, no score_v2 history recompute.
- Phase 3 is destructive → its gates are mandatory (ATLAS veto tripwire if skipped).

## Phase 1 — Code fix (non-destructive)

### Task 1.1 — Asset gate: CRYPTO early-return before any fetch

File: `backend/enrichment/signal_enricher.py`. FIND (exact):

```python
    ticker = (signal_data.get("ticker") or "").upper()
    if not ticker:
        return signal_data
```

REPLACE with:

```python
    ticker = (signal_data.get("ticker") or "").upper()
    if not ticker:
        return signal_data

    # DEF-ENRICH-CLOBBER (2026-07-18): equity enrichment is asset-gated.
    # CRYPTO signals carry producer-built enrichment (cvd_*, market_structure,
    # ...) and must never route through the equity lookup stack (UW equity
    # snapshot collides "BTC" with a ~$28 NYSE instrument; the yfinance
    # fallback launders plausible prices for hyphenated forms). Same
    # comparison as the shadow-gate check at signals/pipeline.py:1392.
    if signal_data.get("asset_class") == "CRYPTO":
        return signal_data
```

### Task 1.2 — Merge-don't-clobber at the single write site

Same file. FIND (exact):

```python
    # --- Write to signal ---
    signal_data["enrichment_data"] = enrichment
    signal_data["enriched_at"] = datetime.utcnow().isoformat()
```

REPLACE with:

```python
    # --- Write to signal (merge, never replace) ---
    # enrichment_data is a shared namespace: the enricher owns exactly the
    # keys it builds above; producer keys and pipeline flags must survive.
    existing = signal_data.get("enrichment_data")
    if isinstance(existing, str):
        try:
            existing = json.loads(existing)
        except (ValueError, TypeError):
            existing = None
    if not isinstance(existing, dict):
        existing = {}
    existing.update(enrichment)
    signal_data["enrichment_data"] = existing
    signal_data["enriched_at"] = datetime.utcnow().isoformat()
```

### Task 1.3 — `persist_enrichment`: DB-side merge + str-safe payload

Same file, inside `persist_enrichment()`. FIND (exact):

```python
                UPDATE signals
                SET enrichment_data = $2, enriched_at = NOW()
                WHERE signal_id = $1
```

REPLACE with:

```python
                UPDATE signals
                SET enrichment_data = COALESCE(enrichment_data, '{}'::jsonb) || $2::jsonb,
                    enriched_at = NOW()
                WHERE signal_id = $1
```

This matches the established merge pattern at `api/signals.py:95` (nick_decision writer) and stops any out-of-order writer from being silently erased.

ALSO make the bound payload type-safe — producers may hold enrichment as a JSON *string* in-memory, and `json.dumps` of a str double-encodes. FIND (exact):

```python
                signal_id,
                json.dumps(enrichment_data),
```

REPLACE with:

```python
                signal_id,
                enrichment_data if isinstance(enrichment_data, str) else json.dumps(enrichment_data),
```

Accepted semantics note: with Task 1.1's early-return, step 4c may re-persist producer-built CRYPTO enrichment via the `||` merge — idempotent by construction — and will stamp `enriched_at` on those rows. Accepted; do NOT add a second gate at the call site.

### Task 1.4 — Tests

New file `backend/tests/test_def_enrich_clobber.py` (unless an obviously better existing home exists):

- **a.** CRYPTO early-return: `asset_class="CRYPTO"` + pre-built producer enrichment → dict returned unchanged; zero enricher-owned keys added; fetch helpers not invoked (mock and assert).
- **b.** Equity merge: pre-set `{"needs_structural_review": True, "custom_x": 1}` → post-enrich, both survive alongside the enricher's keys.
- **c.** Str-form producer enrichment is parsed and preserved by the merge.
- **d.** `persist_enrichment` str input is not double-encoded (assert the bound payload), and the SQL carries the `COALESCE ... ||` merge.
- **e.** `score_v2` and `feed_tier_classifier_v2` tolerate enricher-keyless dicts (assert the existing `.get()`-default behavior explicitly, so it can't regress silently).
- **f.** Equity regression: the enricher-owned key set (14 keys) on an equity fixture is unchanged pre/post-fix.

Full suite after: known-red byte-identical (18f/1s/203e), passed count grows only by the new tests.

## Phase 2 — Deploy + verify (non-destructive)

Push to `main` when Phase 1 is green (RTH blackout RETIRED per `cdec3e8`; `hub_mcp` is untouched so the market-hours "preferred" note does not apply — and it's Saturday). Then the standard 4-step deploy verification per `PROJECT_RULES.md`: SHA match, `/health` clean, boot clean, empirical check = the Acceptance sentinel below.

## Phase 3 — Quarantine remediation (DESTRUCTIVE — gated, runs only after Phase 2 is live-verified)

New script `scripts/quarantine_enrich_clobber.py`, modeled on `scripts/backfill_suppression.py`:

- **Predicate** (never a frozen ID list — rows accrued until the fix deployed): `asset_class='CRYPTO' AND enrichment_data ? 'avg_volume_20d'`
- **--dry-run (default):** print count + write A1 pre-image JSONL (`signal_id`, `ticker`, `created_at`, full `enrichment_data`) to `C:\temp\quarantine_preimage_DEF_ENRICH_<ts>.jsonl`. ZERO writes.
- **Hard-stop band:** apply refuses if the live count falls outside **150 ± 25** — report to Nick instead of proceeding.
- **--apply requires --i-have-go** (A5). Parameterized single UPDATE only (A7 — no f-string SQL):

```sql
UPDATE signals
SET enrichment_data = jsonb_build_object(
    'quarantined_equity_clobber', enrichment_data,
    'quarantine_meta', jsonb_build_object(
        'defect', 'DEF-ENRICH-CLOBBER',
        'quarantined_at', to_char(now() at time zone 'utc', 'YYYY-MM-DD"T"HH24:MI:SS"Z"')))
WHERE asset_class = 'CRYPTO' AND enrichment_data ? 'avg_volume_20d'
```

- **A6 invariance:** total `signals` row count unchanged; post-apply predicate count == 0 (the fingerprint key is no longer top-level — the predicate self-verifies the transform).
- Wrapping (not nulling) preserves the pre-image in-row while removing top-level poison from every reader, including `api/committee_bridge.py:58`.
- SMOKE_TEST rows are included — no `is_test` convention exists yet (separate mini-brief); do not special-case.
- Run locally from repo root with DB env via `railway run` — never on Railway itself.

## Acceptance (Done definition)

1. **Sentinel (transferred from S-3b, unchanged):** the first CRYPTO row post-deploy persisting `market_structure` with sane values — BTC price ~$6xk magnitude, modifier within -45..+35, legs labeled per status. Likely vehicle: Session_Sweep via `webhooks/tradingview.py:137-155` (fires 24/7 — weekend-satisfiable). Report the signal_id + values in the completion note. Note: CVD rows evidence "producer enrichment survives" (`cvd_*`) but do NOT satisfy the `market_structure` sentinel — do not conflate the two evidences.
2. **Equity flag persistence:** unit-tested now (Task 1.4b); live passive-verify on the first natural equity signal carrying a 577/675 flag — markets are closed, so expect Monday. Explicitly NOT a weekend gate.
3. Suite baseline byte-identical + new tests green.
4. Phase 3 applied with the invariance proof, or explicitly deferred by Nick.
5. **Ledger + ACK (silent-failure rule):** update the `docs/workstreams.md` STATER-SWAP DEF-ENRICH-CLOBBER row with status, SHAs, and sentinel evidence — ACK with SHA required. Completion note: `docs/strategy-reviews/stater-swap-redesign/def-enrich-clobber-completion.md`.

## Olympus impact

Committee reads of crypto `enrichment_data` become trustworthy post-fix; Phase 3 removes the $28-class poison from `api/committee_bridge.py:58` reads. No Olympus skill content changes. No `hub_mcp` changes → no connector toggle, no skill re-upload.

## Out of scope (explicit)

L0-bypass routing defect (separate, open) · crypto-native enrichment (S-4) · score_v2 history recompute · `is_test` convention · VP window truth-in-labeling (backlog item a).
