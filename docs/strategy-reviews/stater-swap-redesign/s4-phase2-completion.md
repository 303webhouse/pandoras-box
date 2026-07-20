# S-4 Phase 2 — Discord Embed Parity: Completion Report (2026-07-20 UTC)

Implements `docs/codex-briefs/2026-07-16-stater-swap-s4-strategy-layer-brief.md` §3, all four named gaps, on top of DEF-NOTIFIER-STALE's deploy. HELIOS's char-limit precondition verified empirically, not assumed.

## The four gaps

**3.1 Funding cost over intended hold.** Shown per its natural 8h settlement unit (`Funding: +0.3286%/8h`), not projected against a guessed hold duration — Phase 0.3 confirmed no `timeframe`→hold-duration convention exists anywhere in this codebase, and inventing one would be exactly the kind of fabricated composite this program has avoided all engagement. A trader can scale the real, well-defined rate to their own actual hold length.

**3.2 Liquidation-distance-in-ATRs.** Re-scoped, disclosed here rather than silently decided: no price-level liquidation-cluster data source exists anywhere in the codebase (`get_liquidations()` is backward-looking $ volume/composition over the last hour, not a price heatmap), and liquidation-$ and ATR-price-units don't share coherent dimensions to combine into a real "distance." Shipped as two separate, honestly-labeled real numbers instead — `💥 Liq(1h): $6.4M (29% long)` and `ATR: $197.52` — rather than fabricate a metric that would *look* like real distance data but isn't.

**3.3 Tier badge.** Reuses the already-HTTP-live `crypto_symbol_matrix.py` source (what `/api/crypto/state/{symbol}` already returned before this phase), not the parallel `crypto_gate_config` copy the brief named as canonical — both agree numerically today (Phase 0.3's own flagged open question), simplest integration path, disclosed rather than silently resolved.

**3.4 First line: `{regime} | {session_partition} | Tier {n}`.** Sourced from the same `/state/{symbol}` call (bundles regime + session.partition + tier in one round-trip rather than three separate HTTP calls). Graceful "N/A" fallback per missing piece — confirmed live right now BTC's `regime.state` is `null` ("no regime rows yet," a pre-existing, unrelated staleness gap, not something this phase touched).

## Backend change

`/api/crypto/state/{symbol}` (`backend/api/crypto_market.py`) gets two new fields, `atr` and `liquidations` — additive only, all 10 pre-existing keys unchanged (locked in by test). ATR reuses the canonical `indicators/atr.py::latest_atr()` fed by `jobs/crypto_bars.py`'s intraday bars (same matrix-gated honesty pattern as everywhere else — `[]` bars or <15 bars degrades to NA, never a fabricated value). Liquidations reuses `coinalyze_client.get_liquidations()` as-is, no new vendor.

## Notifier change

`scripts/signal_notifier.py::post_crypto_signal_alert` now calls the extended state endpoint (`fetch_crypto_state`, best-effort — a fetch failure degrades to exactly the pre-existing embed, proven by test, never blocks the alert the way it worked before this phase). Two new description lines inserted: the regime/session/tier first line, and the funding/liquidations/ATR line.

## Two real bugs caught by testing, before deploy

1. **Backend ordering bug**: my ATR field referenced `now_utc`, a variable assigned *later* in `get_crypto_state()`'s execution order than where I'd inserted the new code — would have raised `UnboundLocalError` on every single call in production. Caught by the first test run, fixed by computing the timestamp inline instead of depending on the outer variable.
2. **Notifier unit bug**: `funding.rate_pct` is already a percentage (`coinalyze_client.get_funding_rate()` multiplies by 100 internally) — my first draft multiplied by 100 again, which would have shown every crypto alert's funding rate 100x too large (e.g., 0.0123% displayed as 1.2300%). Caught by writing the test before trusting the format string, fixed and locked in with a named regression test (`test_funding_line_not_double_converted`).

Neither would have been caught by a visual read of the diff alone — both are exactly why this session runs tests before every deploy, not after.

## HELIOS's char-limit precondition: verified, not assumed

Computed actual lengths against a deliberately worst-case payload (longest strategy name in the population — `Liquidation_Flush`, largest realistic numbers, negative funding rate):

| | length | Discord limit | margin |
|---|---|---|---|
| title | 36 | 256 | 14% used |
| description | 335 | 4096 | 8% used |
| footer | 24 | 2048 | 1% used |
| **total** | **395** | **6000** | **7% used** |

Comfortable margin in every dimension — not a risk with this design.

## Tests

17 new: `test_s4_phase2_crypto_state_atr_liq.py` (8, backend field logic — live/NA/exception paths for both new fields, response-shape regression), `test_s4_phase2_notifier_embed.py` (9, notifier embed logic — first line, funding unit lock, liq/ATR line, degraded-fields-omitted, state-fetch-failure graceful degradation, no-api-url skip, pre-existing-fields-unchanged regression). Full suite: `18f/408p/1s/203e` — byte-identical known-red, no regressions.

## Deploy — 4-step verification

1. Railway deploy SUCCESS.
2. `commitHash` exact match: `0595a4bc9cb4a8cb19853bfacb239f7c495f5e37`.
3. **Empirical live check**: `curl /api/crypto/state/BTC` — both new fields present with real data (`atr: 197.5151`, `liquidations: {total_usd: 6433142.4, long_pct: 29.2, composition: "balanced"}`), `degraded: false` on both. (One transient 502 immediately post-deploy, resolved within seconds on retry — Railway edge-proxy cutover noise, not a code issue; logs show the background scheduler running throughout, and repeated `/health` polls returned clean 200s moments later.)
4. No new warnings/errors in Railway logs from the new code paths (`grep`-checked explicitly).

Notifier side: SCP'd to the VPS (same proven mechanism as DEF-NOTIFIER-STALE — byte-exact `scp`, prior version backed up first), hash-verified exact match (`29df418a...`, 625 lines), syntax-verified clean.

## Gate 3 — still a watch item, not yet satisfied

Per the ruling: **"when the first live crypto embed posts, flag it in your report so Nick can eyeball Discord."** Not yet observed — no new crypto trade signal has fired since either deploy tonight, so `post_crypto_signal_alert` (with all four new gaps) hasn't actually posted to Discord yet. The mechanism is fully verified end-to-end short of that one live event: backend data is real and live, notifier code is deployed and syntactically clean, the embed-building logic is unit-tested against the real backend response shape. **Flagging this explicitly as still open — will report the moment a real signal exercises it, not claiming Gate 3 closed on a synthetic proof.**

**ACK — Phase 2 done, deployed, 4-step verified on the backend side, hash-verified on the notifier side. Gate 3 (live Discord eyeball) remains open, watching for the next real crypto signal.**
