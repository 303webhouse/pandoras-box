# DEF-ENRICH-CLOBBER — Completion Note (2026-07-19)

Executes `docs/codex-briefs/2026-07-18-def-enrich-clobber-fix-brief.md`. **All three phases done: code fix deployed, quarantine applied.** Fable approved the apply after reviewing the dry-run's 148-row count.

## Phase 1 — Code fix: DONE

All three tasks applied exactly per the brief's exact-anchor diffs (`backend/enrichment/signal_enricher.py`):

- **Task 1.1** — CRYPTO early-return before any fetch (`asset_class == "CRYPTO"` → return unmodified).
- **Task 1.2** — merge-don't-clobber at the write site: existing `enrichment_data` (dict or JSON string) is parsed and updated with the enricher's own keys, never replaced wholesale.
- **Task 1.3** — `persist_enrichment()`'s `UPDATE` does a DB-side `COALESCE(enrichment_data, '{}'::jsonb) || $2::jsonb` merge (matches `api/signals.py:95`'s established pattern); payload binding is str-safe so a producer-held JSON string isn't double-encoded.

**Task 1.4 tests** — `backend/tests/test_def_enrich_clobber.py`, 11 tests, all passing: (a) CRYPTO early-return + zero-fetch proof, (b) equity merge preserves producer/pipeline keys, (c) str-form enrichment parsed+preserved + malformed-str doesn't crash, (d) `persist_enrichment` SQL/payload assertions (COALESCE+`||` present, dict encoded once, str not double-encoded), (e) `score_v2`/`feed_tier_classifier_v2` tolerate enricher-keyless dicts, (f) equity fixture's enricher-owned key set (14 keys) unchanged.

Full suite: **`18f/391p/1s/203e`** — byte-identical known-red composition, `+11` from this brief's new tests, no regressions.

## Phase 2 — Deploy + verify: DONE

Pushed `34143ee`. Railway deploy SUCCESS, `commitHash` confirmed exact match (`34143ee26ef93cf7376a72b8c6e76601dcfe8f1b`). `hub_mcp` untouched (no connector/skill impact, per the brief).

## Phase 3 — Quarantine remediation: APPLIED

`scripts/quarantine_enrich_clobber.py` (`26ccfc9`), modeled on `scripts/backfill_suppression.py`'s runbook conventions.

**Dry-run, re-confirmed immediately before apply (no drift from the original 2026-07-18 night count):**

```
matching rows       : 148
total signals rows  : 15274
hard-stop band      : 125-175
A1 pre-image: 148 rows -> C:\temp\quarantine_preimage_DEF_ENRICH_20260719T141008Z.jsonl
```

**Apply** (`--apply --i-have-go`):

```
=== quarantine_enrich_clobber APPLY ===
matching rows       : 148
total signals rows  : 15274
hard-stop band      : 125-175

A1 pre-image: 148 rows -> C:\temp\quarantine_preimage_DEF_ENRICH_20260719T141014Z.jsonl

apply: UPDATE 148
A6 row-count invariance: before=15274 after=15274 -> OK
post-apply predicate count (must be 0): 0 -> OK
```

**Independently re-verified via a separate read-only query** (not just the script's own self-report):

| check | result |
|---|---|
| total `signals` rows | 15274 (unchanged) |
| predicate count (`asset_class='CRYPTO' AND enrichment_data ? 'avg_volume_20d'`) | 0 |
| rows carrying `quarantine_meta` | 148 |

Spot-checked one wrapped row's structure — transform correct, pre-image genuinely preserved in-row:

```json
{
  "quarantine_meta": {"defect": "DEF-ENRICH-CLOBBER", "quarantined_at": "2026-07-19T14:10:14Z"},
  "quarantined_equity_clobber": {"ticker": "BTCUSDT", "current_price": null, "avg_volume_20d": null, ...}
}
```

**Connection-mechanism note:** the brief specified `railway run` for this step; it failed with a DNS resolution error (`getaddrinfo failed`) — `railway run` injects Railway's *internal* network hostname for `DB_HOST`, which isn't resolvable from this machine, and once `DB_HOST` is set the script's `.mcp.json` fallback never engages. Ran instead via that `.mcp.json` fallback path (the public proxy connection), the same mechanism used successfully for every other DB write this session, confirmed reaching the identical production database (re-verified independently above) — flagging the substitution rather than silently swapping it.

`--i-have-go` was passed only after Fable's explicit apply approval, following review of the dry-run's 148-row count.

## Acceptance (§5 of the brief)

1. **Sentinel (transferred from S-3b)** — first CRYPTO row post-deploy persisting `market_structure` with sane values. **Not yet observed.** Checked immediately post-deploy (`34143ee`) and again post-apply: zero rows. Brief's stated likely vehicle is `Session_Sweep` via `webhooks/tradingview.py:137-155` (24/7, weekend-satisfiable) — hasn't fired naturally yet. Not forced/simulated — will surface on its own or needs a follow-up check.
2. **Equity flag persistence** — unit-tested (Task 1.4b, passing). Live passive-verify explicitly deferred to Monday per the brief (markets closed this weekend) — not a gate for tonight.
3. **Suite baseline byte-identical + new tests green** — DONE, `18f/391p/1s/203e`.
4. **Phase 3 applied with the invariance proof** — **DONE**: 148 rows updated, A6 row-count invariance OK, post-apply predicate count 0 (self-verifying), independently re-confirmed.
5. **Ledger + ACK** — `docs/workstreams.md` STATER-SWAP DEF-ENRICH-CLOBBER row updated with status, SHAs (`34143ee`, `26ccfc9`), and this note.

## SHAs

- `34143ee` — Phase 1 code fix + 11 tests.
- `26ccfc9` — Phase 3 quarantine script.

**ACK — all three phases done. Code fix live, quarantine applied and independently verified (148 rows, A6 invariance OK, predicate count 0). Sentinel still pending a natural signal fire — will keep being worth a check.**
