# DEF-ENRICH-CLOBBER — Completion Note (2026-07-19)

Executes `docs/codex-briefs/2026-07-18-def-enrich-clobber-fix-brief.md`. Phase 1 and Phase 2 are done and deployed. Phase 3 ran dry-run only tonight, per explicit instruction — **`--i-have-go` was not passed, no writes made.** Apply is Nick's call after reviewing the dry-run count below.

## Phase 1 — Code fix: DONE

All three tasks applied exactly per the brief's exact-anchor diffs (`backend/enrichment/signal_enricher.py`):

- **Task 1.1** — CRYPTO early-return before any fetch (`asset_class == "CRYPTO"` → return unmodified).
- **Task 1.2** — merge-don't-clobber at the write site: existing `enrichment_data` (dict or JSON string) is parsed and updated with the enricher's own keys, never replaced wholesale.
- **Task 1.3** — `persist_enrichment()`'s `UPDATE` does a DB-side `COALESCE(enrichment_data, '{}'::jsonb) || $2::jsonb` merge (matches `api/signals.py:95`'s established pattern); payload binding is str-safe so a producer-held JSON string isn't double-encoded.

**Task 1.4 tests** — `backend/tests/test_def_enrich_clobber.py`, 11 tests, all passing: (a) CRYPTO early-return + zero-fetch proof, (b) equity merge preserves producer/pipeline keys, (c) str-form enrichment parsed+preserved + malformed-str doesn't crash, (d) `persist_enrichment` SQL/payload assertions (COALESCE+`||` present, dict encoded once, str not double-encoded), (e) `score_v2`/`feed_tier_classifier_v2` tolerate enricher-keyless dicts, (f) equity fixture's enricher-owned key set (14 keys) unchanged.

Full suite: **`18f/391p/1s/203e`** — byte-identical known-red composition, `+11` from this brief's new tests, no regressions.

## Phase 2 — Deploy + verify: DONE

Pushed `34143ee`. Railway deploy SUCCESS, `commitHash` confirmed exact match (`34143ee26ef93cf7376a72b8c6e76601dcfe8f1b`). `hub_mcp` untouched (no connector/skill impact, per the brief).

## Phase 3 — Quarantine remediation: DRY-RUN ONLY, apply deferred to Nick

`scripts/quarantine_enrich_clobber.py` (`26ccfc9`), modeled on `scripts/backfill_suppression.py`'s runbook conventions.

```
=== quarantine_enrich_clobber DRY-RUN ===
predicate           : asset_class = 'CRYPTO' AND enrichment_data ? 'avg_volume_20d'
matching rows       : 148
total signals rows  : 15274
hard-stop band      : 125-175

A1 pre-image: 148 rows -> C:\temp\quarantine_preimage_DEF_ENRICH_20260719T065854Z.jsonl
```

**148 rows** — exact match to the brief's Phase-0 evidence, comfortably inside the 150±25 hard-stop band. Pre-image JSONL written (148 lines, verified: `signal_id`/`ticker`/`created_at`/full `enrichment_data` per row), zero writes to `signals`. **`--i-have-go` was not passed** — per explicit instruction, apply is gated on Nick's GO after reviewing this count.

## Acceptance (§5 of the brief)

1. **Sentinel (transferred from S-3b)** — first CRYPTO row post-deploy persisting `market_structure` with sane values. **Not yet observed.** Checked immediately post-deploy (`34143ee`): zero rows. Brief's stated likely vehicle is `Session_Sweep` via `webhooks/tradingview.py:137-155` (24/7, weekend-satisfiable) — hasn't fired naturally yet since deploy. Not forced/simulated — will surface on its own or needs a follow-up check.
2. **Equity flag persistence** — unit-tested (Task 1.4b, passing). Live passive-verify explicitly deferred to Monday per the brief (markets closed this weekend) — not a gate for tonight.
3. **Suite baseline byte-identical + new tests green** — DONE, `18f/391p/1s/203e`.
4. **Phase 3 applied with invariance proof, or explicitly deferred by Nick** — **deferred**: dry-run done, count reported (148, in-band), apply withheld pending Nick's GO.
5. **Ledger + ACK** — `docs/workstreams.md` STATER-SWAP DEF-ENRICH-CLOBBER row updated with status, SHAs (`34143ee`, `26ccfc9`), and this note.

## SHAs

- `34143ee` — Phase 1 code fix + 11 tests.
- `26ccfc9` — Phase 3 quarantine script (dry-run executed, not applied).

**ACK — Phase 1/2 done and deployed, Phase 3 dry-run count reported (148, pre-image written). Holding on `--i-have-go` for Nick's GO.**
