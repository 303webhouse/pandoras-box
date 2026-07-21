# Signal Provenance — producer mapping + the `source` cutline

**Status:** reference. Created 2026-07-21 (DEF-SIGNAL-METADATA, Nick+Fable ruling 3).
**Read when:** you need to know which code produced a `signals` row, or you're tempted to trust/backfill the `source` column.

---

## The cutline: `e8ed614` (2026-07-21)

`signals.source` was **fiction before this commit**. `log_signal()`'s INSERT never listed the column, so PostgreSQL's `DEFAULT 'tradingview'` stamped **every** row regardless of true origin — `SELECT DISTINCT source FROM signals` returned exactly one value, table-wide, for the life of the table.

| | rows | `source` meaning |
|---|---|---|
| **Before the cutline** | `id < 15678` | **Meaningless.** Always the literal `'tradingview'`, whatever actually wrote the row. Do NOT filter, group, or reason on it. |
| **After the cutline** | `id >= 15678` | **Real.** Set by `process_signal_unified()` (`signals/pipeline.py:1198`) to the true producer and now persisted. |

**First row with real provenance:** `id=15678`, `strategy='CTA Scanner'`, `source='cta_scanner'`, `created_at 2026-07-21 17:23:13 UTC` (the first signal written by the container running `e8ed614`).

**No historical backfill will be performed — declined permanently (Nick+Fable, 2026-07-21).** Rationale: a backfill would write *inferred* values into a column that otherwise holds *recorded* values, making the two indistinguishable forever. The `strategy` column already identifies the producer for nearly every row (table below) without inventing anything. If you need pre-cutline provenance, derive it from `strategy` at query time and keep the inference visible in your query — do not persist it.

---

## strategy → producer → `source`

| strategy | producer module | `source` value |
|---|---|---|
| `CVD_ABSORPTION`, `CVD_DIVERGENCE` | `bias_filters/crypto_tape_health_engine.py` | `crypto_cvd_engine` |
| `Funding_Rate_Fade`, `Session_Sweep`, `Liquidation_Flush` | `strategies/crypto_setups.py` | `crypto_engine` |
| `Crypto Scanner` | `scheduler/bias_scheduler.py` (crypto scan job) | `crypto_scanner` |
| `CTA Scanner` (`PULLBACK_ENTRY`, `BEARISH_BREAKDOWN`, `GOLDEN_TOUCH`, `TWO_CLOSE_VOLUME`, `TRAPPED_LONGS/SHORTS`, `RESISTANCE_REJECTION`) | `scanners/cta_scanner.py` via `scheduler/bias_scheduler.py` | `cta_scanner` |
| `sell_the_rip` (Achilles) | `scanners/sell_the_rip_scanner.py` | `server_scanner` |
| `Footprint_Imbalance` | `webhooks/footprint.py` | `footprint` |
| `Whale_Hunter` | `webhooks/whale.py` | `whale_hunter` |
| (whale reversal) | `scanners/wh_reversal.py` | `wh_reversal` |
| (WRR buy model) | `strategies/wrr_buy_model.py` | `wrr_scanner` |
| (UW flow ingestion) | `api/flow_ingestion.py` | `uw_flow` |
| `Artemis`, `Phalanx`, `Sniper`, `Exhaustion` | `webhooks/tradingview.py` (TradingView alerts) | `tradingview` |

### ⚠ The two dual-origin strategies — `strategy` is NOT lossless here

Two strategies are emitted by **both** a server-side scanner and the TradingView webhook, with identical `strategy` strings:

| strategy | producer A | producer B |
|---|---|---|
| `Holy_Grail` | `scanners/holy_grail_scanner.py:224,255` → `server_scanner` | `webhooks/tradingview.py:438` → `tradingview` |
| `Scout Sniper` | `scanners/scout_sniper_scanner.py:312` → `server_scanner` | `webhooks/tradingview.py:340` → `tradingview` |

For these two, `strategy` alone **cannot** tell you which side produced a given row. This is precisely why the backfill was declined rather than merely deferred — for `Holy_Grail`/`Scout Sniper` a backfill would have had to *guess*, and these are exactly the strategies that the (currently dormant) shadow-validation tooling compares server-vs-webhook. **Post-cutline, `source` resolves this cleanly** (`server_scanner` vs `tradingview`); pre-cutline it is unrecoverable.

Note also that `server_scanner` is shared by three distinct scanners (`holy_grail_scanner`, `scout_sniper_scanner`, `sell_the_rip_scanner`) — so `source` alone doesn't disambiguate *those*; the pair `(strategy, source)` does. Neither column is sufficient alone; together they're complete post-cutline.

---

## Querying provenance correctly

- **Post-cutline only.** Any `source`-based analysis must be scoped `WHERE id >= 15678` (or `created_at >= '2026-07-21 17:23:13'`), or it silently mixes real values with the pre-cutline `'tradingview'` default.
- **Timestamps:** `signals.timestamp` and `signals.created_at` are `timestamp without time zone` holding **correct UTC**. Read them via `::text` casts in any tool/script outside the app — the `mcp__postgres__query` serializer misparses naive columns and adds +6h on display (proven in `docs/codex-briefs/def-signal-metadata-phase0-findings.md`; it fooled this program once already).
- **Known stale consumer:** `analytics/confluence_validation.py::compute_shadow_validation` filters on a source vocabulary that never existed (`'holy_grail_scanner'`/`'scout_scanner'`/`'SCANNER'`) rather than the real `'server_scanner'` — it has therefore matched zero server rows for its entire life and its verdict is meaningless. Backlogged, not fixed.

## Related

- `docs/codex-briefs/def-signal-metadata-completion.md` — the fix that created this cutline
- `docs/codex-briefs/def-signal-metadata-phase0-findings.md` — why the "+6h timestamp bug" was a viewing artifact, not a defect
