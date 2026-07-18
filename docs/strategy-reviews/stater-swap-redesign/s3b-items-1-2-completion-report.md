# S-3b Items 1+2 — Completion Report (2026-07-18)

Implements Fable's "GATE OPEN" ruling: spot-CVD wire-in (Item 1) + CVD event detection (Item 2). Both are done and live-verified. **One thing needs your/Fable's ruling before I call this fully closed: the sentinel condition reads Absent, for a reason bigger than S-3b.**

## Sentinel finding — read this first

Fable's added sentinel: *"first CRYPTO row persisting a `market_structure` key post-`81dc0bf` must show sane values... Absent or insane → STOP Items 1/2, report."*

**It's Absent** — zero CRYPTO rows have carried `market_structure` since `81dc0bf` (checked live, post-deploy). Root cause, found live during Item 2's own verification: `backend/enrichment/signal_enricher.py::enrich_signal()` runs unconditionally inside `process_signal_unified()` (`signals/pipeline.py:1447`, **no `asset_class` gate**) and **wholesale-overwrites `enrichment_data` for every signal**, replacing whatever the caller built with an equity-market-data snapshot (price/volume/rvol/atr/sector) looked up for the raw ticker string. For crypto tickers like "BTC" this produces garbage (observed: ~$28 for "BTC" — the exact same value the earlier `Session_Sweep` anomaly showed, confirming this is the shared root cause of both).

**This is not a Phase 0.1 regression** — `get_market_structure_context()` itself is independently verified correct (Fable's own BTC/ETH `vp:ok` probes, plus my own 8 unit tests). It's that whatever it computes gets erased a few pipeline steps later, for every crypto signal, always — this predates S-3b entirely (explains why 0/977 historical CRYPTO rows ever carried `market_structure`, per my earlier pollution assessment). The sentinel would read Absent for any crypto signal fired through `process_signal_unified()`, forever, until this is fixed — it's not something this deploy could pass.

**I didn't fix it.** Fixing `enrich_signal()` to be asset-class-aware touches the enrichment path for every signal type, not just crypto — real surgery, well beyond Item 2's scope, and exactly the kind of thing this engagement's standing rule says to report rather than silently expand into. Flagging for a dedicated ruling.

**What I did fix, in-scope:** Item 2's own dedup mechanism depended on `enrichment_data->>'cvd_level'` surviving to a lookback query — it doesn't, for the same reason. Caught this live (see below), fixed by keying `signal_id` instead (confirmed intact on both live rows), which the enrichment clobber never touches. 2 new regression tests lock this in.

## Item 1 — spot-CVD wire-in: DONE, live-verified

`_fetch_spot_cvd()` added to `crypto_tape_health_engine.py`, mirrors `_fetch_perp_cvd()`, OKX spot trades via `_OKX_SPOT_INSTID`. Live call to `/api/crypto/tape-health` post-deploy:

| symbol | state | spot_cvd | perp_cvd | source |
|---|---|---|---|---|
| BTC | PERP_LED | -52,213.92 | -2,807,917.28 | okx_spot+okx_swap |
| ETH | PERP_LED | -640.75 | -34,624.88 | okx_spot+okx_swap |
| SOL | PERP_LED | 2,654.61 | -8,910.58 | okx_spot+okx_swap |
| HYPE | MIXED | -55,351.85 | -38,521.26 | okx_spot+okx_swap |
| ZEC | PERP_LED | -1,928.79 | 850,518.87 | okx_spot+okx_swap |
| FARTCOIN | **NA** | null | -2,014.89 | none (reason: SPOT_FEED_UNAVAILABLE) |

Five of six live with real classified states. FARTCOIN's live OKX spot fetch failed at runtime despite having a coded `_OKX_SPOT_INSTID` mapping — honestly degraded to NA, not a fabricated value (matches the "coverage ≠ mapping exists, verified at runtime" caveat documented in the mapping's own comment). Also fixed a latent crash this activation made reachable: `_classify_and_persist()` did `abs(perp_cvd)` unconditionally, which would `TypeError` if perp failed while spot succeeded — unreachable before (spot was always `None`), real now that both legs are live independently. Both legs are now checked before classifying.

## Item 2 — CVD event detection: DONE, live-verified

Two real shadow events fired through the actual deployed `process_signal_unified()`:

| signal_id | ticker | direction | entry | stop | target | gate_shadow verdict |
|---|---|---|---|---|---|---|
| `CRYPTO_CVD_CVD_ABSORPTION_ZEC_1784394199753` | ZEC | SHORT | 555.85 | 558.30 | 552.18 | WOULD_PASS (tier 3) |
| `CRYPTO_CVD_CVD_ABSORPTION_BTC_1784394193265` | BTC | LONG | 62,682.37 | 62,483.21 | 62,981.10 | WOULD_PASS (tier 1) |

Both have full BAR_WALK fields (entry/stop/target1/direction all sane, correctly ordered for their direction) and a matching `crypto_gate_shadow` row — S-2's apparatus confirmed intact, exactly as the brief anticipated (unclassified `strategy_class`, `WOULD_PASS_WITH_NOTE`).

**Dedup/cooldown, live-caught and fixed:** as described above, the original `enrichment_data`-keyed cooldown query would never have matched a past row. Re-verified post-fix: a third live trigger on BTC within the same session produced a legitimately new event (different anchor level, POC vs. the earlier unlabeled one — that older row predates the fix and has no level in its `signal_id`), and a fourth immediate re-trigger on BTC produced **no new row** — consistent with the dedup either correctly suppressing a repeat or no repeat condition being detected; the deterministic unit test (`test_fire_events_second_trigger_in_cooldown_does_not_double_fire`) is the primary proof, live behavior is corroborating, not contradicting.

**Unrelated observation, not a bug:** 2 of the 3 fired events show `status=DISMISSED`, notes: *"Auto-dismissed: conflicting signals on BTC. New CVD_ABSORPTION(SHORT) vs active CVD_ABSORPTION(LONG). Both sides logged for backtesting."* This is the pipeline's pre-existing, already-tested conflict-dismissal mechanism (same one referenced in `0037375`'s own test suite — "conflict-dismissal key proof") — triggered because my own repeated live testing fired two opposite-direction BTC events in the same session, not because of anything in Item 1/2's code. `gating_enabled` confirmed unchanged (`false`) throughout — this dismissal path is independent of the crypto gate entirely.

## Done Definition

1. Precondition check — DONE (S-3b Phase 0.1 findings + fix, committed prior).
2. `_fetch_spot_cvd()` live, real states for 5/6 symbols, honest NA for the 6th — **DONE**, live table above.
3. One shadow CVD event fired via real `process_signal_unified()`, observed in `signals` + `crypto_gate_shadow` — **DONE**, two fired, table above.
4. Cooldown/dedup proven — **DONE** (unit test + live-consistent behavior; the live-caught bug that would have broken this is fixed).
5. Zero live impact re-confirmed — **DONE**, `gating_enabled=false` confirmed; the 2 dismissals are the pre-existing conflict-dismissal mechanism, unrelated to gating.
6. 4-step deployment verification — **DONE** across three deploys tonight (`3891a4f`, `0d562e0`, `4ca0980`), each: Railway SUCCESS, exact `commitHash` match, empirical live side-effect (the tape-health table + fired events above go well beyond a health-check).
7. Known-red baseline unchanged — **DONE**, `18f/380p/1s/203e`, byte-identical failed-test composition throughout.
8. Completion report + ACK — this document.

## Recommendation

Items 1 and 2 are correct and shipped on their own evidence — I'm not proposing to hold or roll them back. The sentinel's "Absent" reading is real but traces to a separate, pre-existing, asset-class-blind bug in `enrich_signal()` that's bigger than this brief (touches every signal type's enrichment path) and was never in S-3b's scope to fix. Recommend: rule on `enrich_signal()` separately (own brief, own ATLAS review given the blast radius) rather than folding it into tonight's close — flagged in `docs/workstreams.md`'s STATER-SWAP section either way.

**ACK — holding here for your/Fable's read on the sentinel finding before treating S-3b as fully closed.**
