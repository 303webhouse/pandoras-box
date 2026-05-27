# RH MCP Integration Audit — 2026-05-27

**Status:** Audit-only. No code changes. No RH MCP integration code written. All Part B database access was SELECT-only via Railway's `DATABASE_PUBLIC_URL` proxy; no INSERT / UPDATE / DELETE / DDL was issued. The `ENABLE_PRICE_HISTORY_COLLECTION=false` killswitch was not touched.

**Authoritative artifacts:**
- Robinhood official docs (Part A): URLs cited inline in each finding (`robinhood.com/us/en/support/articles/agentic-trading-overview/`, `…/trading-with-your-agent/`, `…/newsroom/robinhood-is-now-open-to-agents/`, `…/agentic-trading/`, `…/multiple-investing-accounts-faq/`).
- Backend code (Part B): file:line citations inline.
- Database receipts (Part B): query text + numeric output reproduced inline. Source script: [`scripts/audit_price_history_inspect.py`](../scripts/audit_price_history_inspect.py). Run via `railway run --service Postgres -- python <abs-path>/scripts/audit_price_history_inspect.py` on 2026-05-27.

**Scope:** Two paired investigations gating the RH MCP rebuild brief (handoff at commit `a643456`):
- **Part A** — RH MCP capability + auth surface as of launch day, 2026-05-27.
- **Part B** — `price_history` Phase 0: retention, 300 MB abort behavior, write-rate breakdown.

---

## 1. Executive Summary

- **RH Trading MCP shipped today** at `https://agent.robinhood.com/mcp/trading` (HTTP transport). Tool inventory is **10 tools, equities-only beta**: `get_accounts`, `get_portfolio`, `get_equity_positions`, `get_equity_quotes` (≤20 symbols), `get_equity_orders`, `get_equity_tradability`, `review_equity_order`, `place_equity_order`, `cancel_equity_order`, `search`. **No options support, no Greeks, no options chain, no transaction stream, no per-leg detail.** RH explicitly states: "You currently can use your agent to place long equities orders only. Note that we'll be adding support for more assets soon" — `robinhood.com/us/en/support/articles/trading-with-your-agent/`.
- **The Trading MCP read scope spans all RH accounts**, including the Individual account ("All your Robinhood accounts, including your Robinhood account numbers; All details about your positions and balances; All details about your transactions, including your order history" — `…/agentic-trading-overview/`). **Trade scope is funds-isolated to a dedicated Agentic Account**, separate from the Individual account ("your agent only has access to the funds you deposit into that account" — `…/newsroom/robinhood-is-now-open-to-agents/`). This is decisive for AEGIS: the Hub can mirror Individual-account positions via MCP read while trade execution is architecturally blocked from the Individual account, regardless of OAuth scope granularity.
- **No formally documented read-only scope distinct from trade scope.** RH docs are silent on OAuth scope granularity. Funds-isolation (separate Agentic Account) is the publicly-documented safeguard rather than scope separation. AEGIS implication: the Hub gets the architectural safeguard "for free" by simply never funding the Agentic Account, but cannot rely on a scope claim to revoke trade capability if the Agentic Account is later funded.
- **OAuth/auth specifics are docs-silent.** RH directs users to `claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading` and says "you authorize third-party AI agents" but does not document the OAuth flavor, token TTL, refresh mechanism, scope strings, or revocation API. Per the MCP authorization spec for remote HTTP servers, this is **strongly likely** OAuth 2.1 with Dynamic Client Registration, but the audit marks this **Unknown — docs silent** and recommends a follow-up by inspecting the live `/.well-known/oauth-authorization-server` metadata document during Phase 1 implementation. Probing the MCP endpoint via WebFetch returned HTTP 405 (POST-only, no metadata leakage from a GET).
- **No `last_updated_at` or freshness field is documented on positions.** HELIOS dependency: the staleness-indicator data contract must be **synthesized from poll cadence** rather than read from a per-position field. Recommend HELIOS Pass 2 use the wall-clock time of the most recent successful `get_equity_positions` response as the staleness anchor.
- **Lot-level closed positions / realized P&L is Unknown — docs silent.** `get_equity_orders` returns "equity order status history" but the doc gives no field-list; whether realized P&L per closed lot is exposed must be confirmed empirically against a populated account during Phase 1.
- **`price_history` is NOT the dominant DB writer.** It is **37 MB (13.2%)** of the 284 MB total Postgres volume. The dominant table is **`signals` at 122 MB (43%)**, followed by `factor_readings` (56 MB, 19.7%) and `price_history` (37 MB, 13%). The 300 MB abort threshold is gated on **whole-database size** (`pg_database_size(current_database())` at [`backend/analytics/price_collector.py:402`](../backend/analytics/price_collector.py#L402)), not on `price_history` table size. The "Price History DB Volume" alert title is **a misnomer**: it is a DB-volume alert that `price_collector` happens to be the sole enforcer of.
- **`price_history` schema has no `source` / `provider` / `inserted_at` columns.** Source breakdown must be inferred from ticker pattern (yfinance for equities, Binance for crypto, per [`price_collector.py:269-390`](../backend/analytics/price_collector.py#L269-L390)). Write-rate must be inferred from the bar `timestamp` column (which is bar-open time, not insert time). Both inferences are documented in Part B.3.
- **Retention is enforced post-cycle** by `_trim_old_price_history` at [`price_collector.py:509-561`](../backend/analytics/price_collector.py#L509-L561), with env-tunable bounds: daily=30d (`RETENTION_DAILY_DAYS`), intraday=2d (`RETENTION_INTRADAY_DAYS`). An out-of-band, local-first archive job exists at [`backend/jobs/archive_price_history.py`](../backend/jobs/archive_price_history.py) — run manually from the PC, exports compressed CSV per batch, optional `--purge`.
- **Top three rebuild-brief gates the audit unblocks:** (1) **ATLAS DB-write-budget envelope** — confirmed there is ~16 MB of headroom (300 MB abort − 284 MB current) at the database level, NOT the price_history level; RH MCP-driven writes will land in new tables and must size against whole-DB headroom; (2) **AEGIS credential-storage veto** — funds-isolation is the publicly-documented safeguard; OAuth scope granularity remains Unknown and is the open conditionality on the veto-lift; (3) **HELIOS staleness contract** — no per-position freshness field; staleness must be synthesized from poll-cadence wall-clock time.

---

## 2. Part A — RH MCP Capability + Auth

### 2.1 (A.1) Capability Inventory

**Source:** `https://robinhood.com/us/en/support/articles/trading-with-your-agent/`, "What can my agent do?" section. Per the support article, the **Robinhood Trading MCP exposes 10 tools at launch**:

| # | Tool name | Quoted description | Notes |
|---|---|---|---|
| 1 | `get_accounts` | "View all your Robinhood accounts" | Returns the full set of Robinhood accounts under the authenticated identity. Per `…/agentic-trading-overview/` "What your agent can access": "All your Robinhood accounts, including your Robinhood account numbers". Multi-account read confirmed. |
| 2 | `get_portfolio` | "Get a snapshot of your portfolio—including total value—plus values by asset class and real-time buying power" | Total value, asset-class breakdown, real-time buying power. **Day-trade equity and margin used: Unknown — docs silent** beyond "real-time buying power". |
| 3 | `get_equity_positions` | "View open equity positions with quantity and cost basis" | Per-position fields explicitly enumerated by RH: **quantity, cost basis**. Other per-position fields (current mark, last_updated_at, average price, market value) are **Unknown — docs silent**. **No Greeks** because there is no options support. |
| 4 | `get_equity_quotes` | "Get real-time equity quotes and prior close for up to 20 symbols" | Hard cap of 20 symbols per call. Returns real-time quote + prior close. |
| 5 | `get_equity_orders` | "Get equity order status history" | Order-status history. **Whether closed-lot realized P&L is included in the response is Unknown — docs silent.** Field list not published. |
| 6 | `get_equity_tradability` | "Check if a symbol can be traded and find out if it can be traded fractionally" | Boolean + fractional-eligibility check per symbol. |
| 7 | `review_equity_order` | "Simulate an equity order and get pre-trade warnings" | Pre-trade dry-run — surfaces RH-side warnings. |
| 8 | `place_equity_order` | "Place an equity order" | Long equity only per `…/trading-with-your-agent/`: "You currently can use your agent to place long equities orders only." |
| 9 | `cancel_equity_order` | "Cancel an open equity order" | |
| 10 | `search` | "Find a company name or partial name to a ticker" | Ticker-lookup helper. |

**Specific answers from A.1:**

- **Position state granularity** — **Aggregated per ticker, not per-leg.** No options support means no per-leg model. Fields explicitly named by RH: **quantity, cost basis**. Strike/expiry/side/premium/current-mark fields are not applicable (no options) or **Unknown — docs silent** (current mark).
- **Greeks on held options** — **N/A.** Per `…/trading-with-your-agent/`: equities-only. RH explicitly says "we'll be adding support for more assets soon" but options are not currently in the inventory.
- **Trade events vs state** — **State snapshots only.** `get_equity_positions` is a query against current state; `get_equity_orders` returns "order status history" (snapshot, not streaming). No transaction stream / event subscription / webhook is documented. Polling cadence is **Unknown — docs silent**, and is governed by the MCP client, not the server.
- **Cash, buying power, day-trade equity, margin used** — `get_portfolio` exposes "total value … values by asset class and real-time buying power." Day-trade equity and margin used are **Unknown — docs silent**.
- **Closed positions / realized P&L** — `get_equity_orders` returns order status history. Whether the response includes per-fill realized P&L, lot accounting, or holding period is **Unknown — docs silent.** Historical depth is also **Unknown — docs silent**.
- **Options chain** — **No options chain endpoint exposed.** Beta scope is equities-only. Cross-references: this resolves Task 3 (`hub_get_options_chain`) — RH cannot replace it; existing UW endpoint (`/api/stock/{ticker}/option-contracts`) remains the only chain source. (Per brief Out-of-Scope rule, the disposition decision belongs to a separate ATHENA call; this finding only informs it.)
- **Freshness field (HELIOS Pass 2 dependency)** — **No `last_updated_at` (or equivalent) is documented on any position.** Freshness must be synthesized from poll cadence — the wall-clock time of the client-side `get_equity_positions` call. HELIOS implication called out in §7.

### 2.2 (A.2) Auth Model

**Source:** `…/trading-with-your-agent/` "Connect your AI agent" section; `…/newsroom/robinhood-is-now-open-to-agents/`; `…/agentic-trading/`.

**Documented setup pattern** (Claude Code example): `claude mcp add robinhood-trading --transport http https://agent.robinhood.com/mcp/trading` (cited in multiple sources including the agentic-trading product page: "Paste one URL into your MCP config to connect most agents out of the box").

**Specific answers from A.2:**

- **Auth artifact type** — **Unknown — docs silent.** Robinhood says only "you'll authorize the AI agent" (`…/agentic-trading-overview/`) and "By creating an Agentic Account, you authorize third-party AI agents to view your account data and execute trades on your behalf" (`…/newsroom/…`). No mention of OAuth flavor (Authorization Code, PKCE, DCR), bearer token, API key, or device-bound credential. The MCP spec's default for remote HTTP servers is **OAuth 2.1 with Dynamic Client Registration** (modelcontextprotocol.io/specification/draft/basic/authorization), and the `--transport http` integration pattern matches that spec, but RH does not confirm this in the public-facing docs. **Recommend follow-up via `/.well-known/oauth-authorization-server` GET against the MCP host during Phase 1 — that endpoint should return OAuth issuer metadata if the spec is followed.** Probing `agent.robinhood.com/mcp/trading` directly via WebFetch returned **HTTP 405 Method Not Allowed** (POST-only endpoint, no metadata leakage from a GET).
- **Credential storage requirements** — **Unknown — docs silent.** RH does not dictate client-side storage. Storage discipline is governed by the MCP client (Claude Code, ChatGPT, etc.). RH explicitly disclaims downstream data: "Once your data is shared with an AI provider of your choice, it leaves Robinhood's security environment and is governed by that provider's terms, not ours" (`…/agentic-trading/`). **AEGIS implication:** the threat-model decision is "which MCP client stores the token" rather than "where RH requires it stored". Recommend HELIOS/AEGIS define a Hub-side storage convention (Railway secret + OS keychain on the VPS) once the auth flow is empirically confirmed.
- **Token lifetime + refresh flow** — **Unknown — docs silent.** No TTL, refresh-token mechanism, or rotation policy is documented. **Recommend follow-up:** observe the access token + refresh token expiry on a real `claude mcp add` flow during Phase 1.
- **Scope granularity (read-only vs trade-execution)** — **Unknown — docs silent.** The 10 tools include both read tools (`get_*`) and trade tools (`place_*`, `cancel_*`) under a **single MCP endpoint URL**. No documented mechanism splits read scope from trade scope. **However**, trade execution is **architecturally constrained** to the dedicated Agentic Account: "your agent only has access to the funds you deposit into that account" (`…/newsroom/…`). For the Hub use case (read-only portfolio mirroring of the Individual account), the safety property is delivered by **never funding the Agentic Account**, not by scope claim. **AEGIS implication:** veto-lift conditionality — see §7.
- **Rotation / revocation procedure** — **Documented at the user-action level, not the API level.** Per `…/newsroom/…`: "you can disconnect the agent at any time with the tap of a button" and "one-tap kill switch to disconnect the agent at any time" — confirmed instant disconnect. The **programmatic** revocation API (e.g., DELETE on a token endpoint) is **Unknown — docs silent**.

### 2.3 (A.3) Operational Characteristics

- **Rate limits** — **Unknown — docs silent.** No per-second / per-minute / per-day or per-endpoint limits published. **Recommend follow-up via empirical measurement during Phase 1 implementation** (start with conservative client-side rate-limiting; observe 429 / 503 behavior; document observed limits).
- **Poll vs webhook vs hybrid** — **Poll-only** based on the documented tool inventory (all 10 tools are RPC-style requests; no subscription / streaming / event endpoint). Push notifications exist but are user-facing iOS/Android notifications, not webhooks ("You'll get push notifications any time your agent makes a trade and can see a real-time activity feed and P&L directly in the Robinhood apps" — `…/newsroom/…`). **No developer-facing webhook is documented.**
- **Webhook signature mechanism** — **N/A** (no webhooks).
- **Error behavior** — **Unknown — docs silent.** Retry-After, exponential backoff, idempotency keys: not documented. **Recommend follow-up:** observe the response shape on a deliberately-malformed request and on rate-limited 429 responses during Phase 1.

### 2.4 (A.4) Multi-account Dimension

- **Single-account-per-token or multi-account read?** — **Multi-account read confirmed.** `get_accounts` is documented as "View all your Robinhood accounts" (`…/trading-with-your-agent/`), and the read-access scope includes "All your Robinhood accounts, including your Robinhood account numbers" (`…/agentic-trading-overview/`). Per the multiple-investing-accounts FAQ (`…/multiple-investing-accounts-faq/`): "You can access all your Robinhood accounts, including your multiple individual investing accounts with the same login that you use now for your first or primary individual investing account" — confirms single-identity, multi-account architecture at the RH platform layer.
- **Account-selection mechanism per request** — **Unknown — docs silent.** Whether per-account scoping is via a tool argument (e.g., `account_id` parameter on `get_equity_positions`), an MCP server header, or session state is not documented. **Recommend follow-up:** inspect the JSON schema of each tool when the MCP server is connected during Phase 1.
- **Implications for Nick's setup** — Nick currently has one RH Individual account. Adding an Agentic Account is a precondition for the MCP integration (see §7). A future Roth or cash account would likely be exposed under the same MCP authentication; isolation between accounts at the **trade execution** layer is delivered by the funds-isolation architecture (each account holds its own balance; trade tools only act on Agentic-Account funds per the newsroom quote). Isolation at the **read** layer is NOT delivered — agents see all accounts. **AEGIS Pass 2 implication:** if Nick opens a future Roth, the agent will read it too. There is no documented opt-out from per-account read visibility.

---

## 3. Part B — `price_history` Phase 0

### 3.1 (B.1) Current Retention Policy

**Schema source:** [`backend/database/postgres_client.py:258-281`](../backend/database/postgres_client.py#L258-L281) — the `price_history` table is created idempotently at app boot. No standalone migration file exists in `migrations/` for this table (only `2026_04_30_close_handler_refactor.sql`); the schema is owned by the bootstrap path. Confirmed via live `information_schema.columns` query:

```
Column      Type                       Nullable  Default
id          integer                    NO        nextval('price_history_id_seq'::regclass)
ticker      text                       NO        —
timeframe   text                       NO        —
timestamp   timestamp with time zone   NO        —
open        real                       YES       —
high        real                       YES       —
low         real                       YES       —
close       real                       YES       —
volume      real                       YES       —
```

UNIQUE(ticker, timeframe, timestamp). Indexes: `price_history_pkey`, `price_history_ticker_timeframe_timestamp_key`, `idx_price_ticker_tf`, `idx_price_timeframe_timestamp`.

**No `source` / `data_source` / `provider` / `caller` column. No `inserted_at` / `created_at`.** This is decisive for the B.3 inference shape — write rate cannot be measured against insert time; only bar-time can be measured.

**Retention enforcement (live path):** `_trim_old_price_history()` at [`backend/analytics/price_collector.py:509-561`](../backend/analytics/price_collector.py#L509-L561), called once per collection cycle from `collect_price_history_cycle()` at [`backend/analytics/price_collector.py:706-710`](../backend/analytics/price_collector.py#L706-L710). The trim issues two `DELETE ... WHERE timestamp < NOW() - $1::interval` statements: one for `timeframe='D'`, one for `timeframe!='D'`. Retention bounds are env-tunable:

- `PRICE_HISTORY_RETENTION_DAILY_DAYS` — default **30** ([`price_collector.py:84`](../backend/analytics/price_collector.py#L84))
- `PRICE_HISTORY_RETENTION_INTRADAY_DAYS` — default **2** ([`price_collector.py:85`](../backend/analytics/price_collector.py#L85))

**Retention enforcement (out-of-band, manual):** [`backend/jobs/archive_price_history.py`](../backend/jobs/archive_price_history.py) — local-first archive job (compressed CSV per batch, optional `--purge`). Run manually from the PC ([`archive_price_history.py:1-13`](../backend/jobs/archive_price_history.py#L1-L13)); not on any cron.

**Optional VACUUM:** `_maybe_vacuum_price_history()` at [`price_collector.py:564-587`](../backend/analytics/price_collector.py#L564-L587), disabled by default (`PRICE_HISTORY_VACUUM_AFTER_TRIM=false`), fires only after a trim that deletes ≥ `PRICE_HISTORY_VACUUM_AFTER_TRIM_MIN_DELETES` (50000 default) rows.

### 3.2 (B.2) 300 MB Abort Behavior

**Threshold check:** `_upsert_price_rows()` at [`backend/analytics/price_collector.py:445-502`](../backend/analytics/price_collector.py#L445-L502). Before issuing the batched upsert SQL, it calls `_get_db_size_mb()` at [`price_collector.py:397-406`](../backend/analytics/price_collector.py#L397-L406):

```python
async def _get_db_size_mb() -> float:
    """Return current database size in MB. Used to guard against filling the volume."""
    try:
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            size_bytes = await conn.fetchval("SELECT pg_database_size(current_database())")
            return (size_bytes or 0) / (1024 * 1024)
```

**The check is whole-database, not table-specific.** `pg_database_size(current_database())` returns the size of the entire `railway` database, NOT `pg_total_relation_size('price_history')`. Implication: when the alert fires, the headroom is owned by the entire DB, not by `price_history`.

**Abort action** at [`price_collector.py:463-469`](../backend/analytics/price_collector.py#L463-L469):

```python
if db_mb > VOLUME_ABORT_MB:
    logger.error(
        "DB size %.0f MB exceeds abort threshold %d MB - skipping insert of %d rows to protect volume!",
        db_mb, VOLUME_ABORT_MB, len(payload),
    )
    await _maybe_send_volume_alert("critical", db_mb, len(payload))
    return 0
```

**What it does** (precise, at the code level):
- **Skips this batch of `price_history` upserts** by returning 0 early. The collector cycle continues; subsequent tickers will hit the same gate and also be skipped (since DB size does not change mid-cycle).
- **Does NOT halt other Postgres writes.** Only `_upsert_price_rows` enforces the check. Inserts from `signals`, `factor_readings`, `bias_composite_history`, `flow_events`, `signal_enricher`, the bias scheduler, the webhook circuit breaker, the analytics queries, and the signals API are all **unguarded** — they will continue to write into the same volume even while `price_history` is aborted. (Confirmed via grep across `backend/` — no other module references `VOLUME_ABORT_MB` or `pg_database_size`.)
- **Does NOT raise an exception.** No bubble-up to FastAPI. No 500 to clients. The collector returns normally.
- **Does NOT trigger the killswitch.** The `ENABLE_PRICE_HISTORY_COLLECTION` env flag (referenced at [`backend/scheduler/bias_scheduler.py`](../backend/scheduler/bias_scheduler.py) and surfaced in the alert description text at [`price_collector.py:432`](../backend/analytics/price_collector.py#L432)) is **operator-set**, not auto-flipped. The alert merely tells the operator to set it manually.

**Alert:** `_maybe_send_volume_alert()` at [`price_collector.py:409-442`](../backend/analytics/price_collector.py#L409-L442). Title format ([`price_collector.py:428`](../backend/analytics/price_collector.py#L428)): `Price History DB Volume {level.upper()} ({db_mb:.1f} MB)`. Severity is `"critical"` when level is `"critical"` (above abort threshold) else `"warning"`. Throttle: per-severity, default 60 minutes (`PRICE_HISTORY_DB_ALERT_COOLDOWN_MINUTES`). Discord webhook routed via `bias_engine.anomaly_alerts.send_alert` at [`price_collector.py:436-438`](../backend/analytics/price_collector.py#L436-L438).

**Misnomer flag:** the alert title says "Price History DB Volume" — but the underlying metric is **`pg_database_size(current_database())`**, the whole `railway` Postgres database. The collector is just the only writer that enforces the threshold. Operators reading the alert may assume `price_history` is the culprit when it represents 13% of volume; **rename consideration is a backlog candidate**, not in this audit's scope. // backlog candidate

### 3.3 (B.3) Write-Rate Breakdown by Source

All queries below were executed once on **2026-05-27** via Railway's Postgres-service public proxy (`trolley.proxy.rlwy.net:25012`) using SELECT-only access. Source script: [`scripts/audit_price_history_inspect.py`](../scripts/audit_price_history_inspect.py).

#### B.3.1 Size context

```
=== SIZES (live, 2026-05-27) ===
price_history table: 37 MB  (39,223,296 bytes) — 13.2% of DB
whole database:      284 MB (297,536,659 bytes)
total rows in price_history: 4,002
```

#### B.3.2 Top 5 tables by size — `price_history` is NOT the dominant driver

```sql
SELECT relname AS table_name,
       pg_size_pretty(pg_total_relation_size(c.oid)) AS size_pretty,
       pg_total_relation_size(c.oid) AS size_bytes
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r' AND n.nspname = 'public'
ORDER BY pg_total_relation_size(c.oid) DESC
LIMIT 5;
```

| Table | Size | % of DB |
|---|---|---|
| `signals` | 122 MB | 43.0% |
| `factor_readings` | 56 MB | 19.7% |
| `price_history` | 37 MB | 13.0% |
| `bias_composite_history` | 20 MB | 7.0% |
| `flow_events` | 13 MB | 4.6% |

**Headroom: 16 MB to the 300 MB abort.** This is the **whole-DB envelope** — every writer competes for it, not just `price_history`. (Cross-reference: the 300 MB abort triggered the alert that prompted this audit; `price_history` only contributes ~13% of the volume that triggered it.)

#### B.3.3 Schema gap — no source column, no insert-time column

The `price_history` table has **no `source` / `data_source` / `provider` / `caller` column** (full column list shown in B.1). It also has **no `inserted_at` / `created_at`** column. Implications:

- **Source breakdown must be inferred from ticker pattern.** The collector dispatches per ticker at [`price_collector.py:672-685`](../backend/analytics/price_collector.py#L672-L685): `_is_crypto_ticker(ticker)` → `_fetch_crypto_rows()` (Binance via `https://data-api.binance.vision/api/v3/klines`); else → `_fetch_equity_rows()` (yfinance). `_is_crypto_ticker()` at [`price_collector.py:134-141`](../backend/analytics/price_collector.py#L134-L141) returns True if the ticker is in `CRYPTO_TICKERS = {BTC, ETH, SOL, XRP, ADA, AVAX, DOGE, DOT, LINK, LTC, BCH, XLM}` OR ends with `USDT` / `USDTPERP` / `PERP`. Tickers ending with `-USD` (e.g. `ATOM-USD`) get normalized to `<sym>-USD` by `_normalize_symbol_for_yf` and are routed to yfinance.
- **Write rate must be inferred from bar `timestamp`** (the bar-open time), not from when the row was inserted. The collector cycle runs on the bias scheduler cadence; inserts of "today's daily bar" cluster at the start of each cycle. The bar timestamp is normalized to midnight UTC for daily bars (see `_purge_malformed_daily_rows` at [`price_collector.py:244-266`](../backend/analytics/price_collector.py#L244-L266) — a guard that hard-deletes daily rows that drifted off midnight).

#### B.3.4 Rows by timeframe — intraday is currently OFF

```sql
SELECT timeframe, COUNT(*) AS rows, COUNT(DISTINCT ticker) AS tickers,
       MIN(timestamp) AS oldest, MAX(timestamp) AS newest
FROM price_history GROUP BY timeframe ORDER BY rows DESC;
```

| Timeframe | Rows | Distinct tickers | Oldest | Newest |
|---|---|---|---|---|
| `D` (daily) | 4,002 | 239 | 2026-04-28 00:00:00 UTC | 2026-05-27 00:00:00 UTC |

**Only daily bars are stored.** No `5m` or other intraday timeframe rows exist in the table. This matches the runtime default `ENABLE_INTRADAY_COLLECTION=False` at [`price_collector.py:94`](../backend/analytics/price_collector.py#L94) — intraday collection is gated off by env flag. The 30-day data window matches `RETENTION_DAILY_DAYS=30`.

#### B.3.5 Recent rows by `timestamp` (bar-time proxy for write rate)

```sql
SELECT COUNT(*) FROM price_history WHERE timestamp > NOW() - INTERVAL '<span>';
```

| Window | Rows |
|---|---|
| last 1h | 0 |
| last 24h | 138 |
| last 7d | 670 |

The 0-row-in-last-hour is structural: daily bars timestamp at 00:00 UTC, so "last hour" sees no new bars unless the cycle just ran past midnight. The last-24h count of 138 reflects today's collected universe size.

#### B.3.6 Rows-per-day for last 14 days (collection cadence proxy)

| Day | Rows |
|---|---|
| 2026-05-27 | 138 |
| 2026-05-26 | 164 |
| 2026-05-25 | 4 (memorial day, no equity bars) |
| 2026-05-24 | 4 (sat) |
| 2026-05-23 | 3 (sat — fri-stamped rows that crossed midnight) |
| 2026-05-22 | 184 |
| 2026-05-21 | 173 |
| 2026-05-20 | 189 |
| 2026-05-19 | 190 |
| 2026-05-18 | 197 |
| 2026-05-17 | 6 (sat) |
| 2026-05-16 | 6 (sat) |
| 2026-05-15 | 191 |
| 2026-05-14 | 193 |

**Trading-day pattern: ~140–200 rows/day.** Weekend rows correspond to crypto-only bars (Binance is 24/7) plus the small set of always-collected crypto tickers (`CRYPTO_TICKERS = 12 symbols`). Memorial Day (2026-05-25) collapses to weekend-shape (crypto only).

#### B.3.7 Top 15 tickers by row count

| Ticker | Rows |
|---|---|
| BTC | 30 |
| DXY | 26 |
| ATOM-USD | 25 |
| BTCUSDT | 25 |
| GLD | 22 |
| UNH, MPC, WELL, ITW, AMZN, PSX, GS, ADBE, BAC, SHW | 21 each |

The top is dominated by **always-collected tickers** (`DEFAULT_TICKERS = {SPY, QQQ, IWM, GDX, SLV, BTC, DXY}` at [`price_collector.py:26`](../backend/analytics/price_collector.py#L26)) and crypto symbols. Note `BTC` (30 rows) and `BTCUSDT` (25 rows) are **separate symbols stored independently** — `_is_crypto_ticker` accepts both, and both are normalized for their respective providers (`BTC` → `BTC-USD` for yfinance; `BTCUSDT` already in Binance form). **Possible duplicate-source ingestion of the same underlying asset** — backlog candidate to dedupe, not in this audit's scope. // backlog candidate

#### B.3.8 Average row size estimate

```sql
SELECT relpages, reltuples,
       (relpages * 8192.0 / reltuples)::numeric(10,1) AS avg_bytes_per_row
FROM pg_class WHERE relname = 'price_history';
```

`relpages=68`, `reltuples=4002`, **avg_bytes_per_row ≈ 139.2**. The 37 MB table-size figure includes indexes (the table itself is ~556 KB by `relpages * 8KB`). The bulk of the 37 MB is index pages and tuple overhead, not row payload — implying the table size shrinks **disproportionately** to row-count reductions (deleting half the rows will not halve the size without a VACUUM FULL or REINDEX).

#### B.3.9 Volume-growth rate (back-of-envelope)

At ~140–200 rows/day × ~139 bytes/row ≈ **20–28 KB of raw row payload per day**. The 37 MB current size is dominated by index pages and historical churn (no VACUUM FULL has been run), not by live row payload. **Implication: `price_history`-driven growth is not the source of the 16 MB headroom pressure**; the dominant growth driver is one of `signals` (122 MB), `factor_readings` (56 MB), or `bias_composite_history` (20 MB). Sizing the rebuild's RH-MCP-driven writes against the wrong table is the failure mode to avoid.

#### B.3.10 Source-share inference (heuristic, no `source` column)

Per the collector dispatch logic, every row in `price_history` is either:
- **yfinance equity** — ticker not in `CRYPTO_TICKERS`, not ending in `USDT`/`PERP`. Includes all standard equity symbols (SPY, AMZN, GS, etc.) and `<sym>-USD` patterns routed via `DX-Y.NYB` and `<sym>-USD` normalization.
- **Binance crypto** — ticker in `CRYPTO_TICKERS` OR ends with `USDT`/`PERP`.

A row-count split was attempted by approximating the regex (top-15 hints at the shape): roughly 95%+ of rows are equity (`yfinance`), with the small crypto set contributing the weekend rows and the `BTC` / `BTCUSDT` / crypto-symbol pairs. The exact split was not enumerated since (a) the audit's scope is sizing-headroom, not provider-quota; (b) `price_history` is 13% of DB, not the dominant driver. **If a future brief needs an exact split, the easiest hardening is to add a `source TEXT` column on insert** — backlog candidate. // backlog candidate

---

## 6. Open Questions

Every question the audit landed at "Unknown — docs silent" or recommended for follow-up:

| # | Question | Follow-up vector |
|---|---|---|
| Q1 | OAuth flavor used by the Trading MCP (Authorization Code? PKCE? Dynamic Client Registration?) | Phase 1: GET `https://agent.robinhood.com/.well-known/oauth-authorization-server` on connect; inspect Claude Code's stored MCP metadata after `claude mcp add` flow. |
| Q2 | Access token TTL and refresh-token mechanism + rotation | Phase 1: observe token expiry on first refresh; capture refresh request shape. |
| Q3 | Read-only OAuth scope distinct from trade-execution scope (AEGIS veto-lift critical) | Phase 1: inspect the scope strings requested during the `claude mcp add` consent screen. If a `read` scope is offered separately, AEGIS conditionality lifts on it; if all-or-nothing, AEGIS lifts on funds-isolation alone (see §7). |
| Q4 | Programmatic revocation API endpoint (vs the in-app "one-tap disconnect") | Phase 1: search RH developer docs after auth flow is captured; if absent, the in-app disconnect is the only revocation path. |
| Q5 | Rate limits (per-second / per-minute / per-day, per-endpoint or global) | Phase 1: empirical measurement with conservative client-side limiter; observe 429 responses. |
| Q6 | Error response shape (Retry-After, idempotency keys, 5xx semantics) | Phase 1: deliberately malformed requests + load tests. |
| Q7 | Per-position fields beyond `quantity` + `cost basis` (current mark, average price, market value) | Phase 1: inspect actual `get_equity_positions` response JSON on a populated account. |
| Q8 | Whether `get_equity_orders` includes per-fill realized P&L, lot accounting, holding-period (HELIOS portfolio-surface dependency) | Phase 1: inspect actual response on an account with closed positions. |
| Q9 | Lot-level closed-position history depth (how far back?) | Phase 1: pagination probe on `get_equity_orders` against an account with year+ of trades. |
| Q10 | Day-trade equity and margin-used fields in `get_portfolio` (currently only "real-time buying power" is named) | Phase 1: inspect actual `get_portfolio` response JSON. |
| Q11 | Account-selection mechanism per request (account_id parameter? header? session state?) | Phase 1: inspect each tool's JSON schema via MCP client introspection. |
| Q12 | Webhook support (currently believed poll-only; verify no separate webhook endpoint exists) | Phase 1: explicit RH support ticket if not in docs after auth flow is captured. |
| Q13 | Push-notification settings programmatic control (currently user-facing only) | Out of scope unless rebuild needs it; flag if encountered. |
| Q14 | RH MCP server version pinning / API versioning policy (does the URL change between v1 and v2?) | Phase 1: inspect MCP `initialize` response for server version. |
| Q15 | Add `source TEXT` column to `price_history` to remove inference shape from future audits | Backlog candidate, not in audit scope. // backlog candidate |
| Q16 | Rename "Price History DB Volume" alert to reflect it gates whole-DB volume | Backlog candidate, not in audit scope. // backlog candidate |
| Q17 | Dedupe `BTC` vs `BTCUSDT` collection (both stored as separate `price_history` rows for the same underlying) | Backlog candidate. // backlog candidate |
| Q18 | Investigate `signals` table 122 MB growth driver (dominant DB-volume contributor; the actual root cause of the alert prompting this audit) | Separate brief — out of scope for RH MCP rebuild. // backlog candidate |

---

## 7. Implications for Rebuild Brief

This section names which architectural decisions in the eventual RH MCP rebuild brief are **resolved** by the audit vs **still open**, organized by Titan dependency:

### 7.1 AEGIS — broker-credential veto-lift

**Resolved:**
- Funds-isolation safeguard is publicly documented and architectural. Hub-side mitigation: never fund the Agentic Account. This is a "free" safeguard that does not depend on OAuth scope claims.
- Read-scope spans all RH accounts (Individual, IRA, Joint, etc.). The Hub use case (mirror Individual-account positions) is supported.

**Still open (conditionality on the veto-lift):**
- **No documented read-only scope distinct from trade scope (Q3).** Until the OAuth consent flow is inspected during Phase 1, the veto-lift rests on funds-isolation alone, not on scope granularity. **If Phase 1 confirms a separate read scope exists, AEGIS can lift the veto on the stronger basis of "scope + funds-isolation, defense in depth." If Phase 1 confirms no read scope is offered, AEGIS must decide whether funds-isolation alone meets the threat model.**
- Credential storage discipline is governed by the MCP client, not RH (Q1, Q2). HELIOS/AEGIS need to define a Hub-side convention (recommend: Railway secret for the Railway-side mirror; OS keychain on the VPS if a second client is added) before Phase 1 lands code.

### 7.2 ATLAS — DB write-budget envelope

**Resolved:**
- The 300 MB abort threshold is **whole-DB**, not `price_history`-specific. Sizing the RH-MCP-driven writes (new tables: `rh_positions`, `rh_orders`, `rh_portfolio_snapshots`, etc.) must use the **16 MB current headroom** as the envelope, not the much larger headroom `price_history` alone (~263 MB) would suggest.
- `price_history` is a minor (13%) contributor to volume. The dominant table is `signals` (43%). RH-MCP-driven writes will compete with `signals` growth for envelope, not with `price_history`.

**Still open:**
- The actual `signals` table growth rate over the next 30 days is not measured in this audit (out of scope — Q18 is the backlog item to chase it).
- The rebuild brief should size its Phase 1 footprint conservatively (<10 MB delta across new tables) until the `signals` envelope is independently characterized.

### 7.3 HELIOS — staleness-indicator data contract

**Resolved (as a constraint, not a green-light):**
- **No per-position `last_updated_at` field is documented (Q7 may surface one in Phase 1, but the audit must assume not).** The staleness contract must be synthesized from poll-cadence wall-clock time on the client side.

**Recommended contract for the portfolio surface:**
- Store a `mirror_last_synced_at TIMESTAMPTZ` on each Hub-side `rh_positions` row, set to the wall-clock at the time of the last successful `get_equity_positions` response that included the row.
- Surface a "Last synced: X seconds ago" badge in Agora next to the position card.
- If `now - mirror_last_synced_at > <threshold>`, render the badge yellow; if `> 2 × threshold`, render red and pause derived calculations until next sync.

**Still open:**
- The polling cadence itself depends on Q5 (rate limits). Default a 60s cadence until rate limits are characterized.

### 7.4 ATHENA — sequencing / scope decisions

**Resolved:**
- **`hub_get_options_chain` (Task 3) cannot be served by RH MCP.** Equities-only beta confirms RH is not a chain provider; UW remains the only chain source. The disposition decision (deprecate Task 3? keep it on UW?) is still ATHENA's call but is now informed by hard data.
- The rebuild brief can drop "options support via RH" from any P0/P1 scope. Whenever RH adds options ("coming soon" per `…/trading-with-your-agent/`), a separate brief addendum can revisit.

**Still open:**
- The order in which the rebuild brief lands its tools depends on Q11 (account-selection mechanism) and Q10 (margin/day-trade exposure) — both are Phase 1 inspections, not blockers for the brief's structural decisions.

### 7.5 Net status of veto-lifts after this audit

| Titan | Pre-audit status | Post-audit status | Conditionality remaining |
|---|---|---|---|
| AEGIS | Absolute veto on broker credentials | **Conditional lift on funds-isolation** (publicly documented, architectural) | Q3 — scope granularity. Veto strengthens to defense-in-depth if Phase 1 confirms separate read scope. |
| ATLAS | Audit-first | **Lift** — sufficient information to architect rebuild | Q18 (`signals` growth) is a separate brief, not a rebuild blocker. |
| HELIOS | Awaiting staleness contract | **Contract defined as synthesized-from-cadence** (no per-position freshness field) | Q5 (rate limits) gates the cadence value but not the contract shape. |
| ATHENA | Awaiting capability inventory | **Equities-only, 10 tools confirmed; scope decisions unblocked** | Q11 / Q10 are inspections, not blockers. |

---

**Audit drafted:** 2026-05-27
**Audit committed:** TBD — `docs(audit): RH MCP integration audit — Part A capability + auth, Part B price_history Phase 0`
**Next action:** Titans Final Review pass (ATLAS, AEGIS, HELIOS, ATHENA) on this audit; rebuild brief drafted only after veto-lift confirmations.
