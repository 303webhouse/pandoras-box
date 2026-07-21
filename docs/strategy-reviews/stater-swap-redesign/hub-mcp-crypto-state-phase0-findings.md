# HUB-MCP-CRYPTO-STATE — Phase 0 inventory (STOP-GATE: ATLAS sign-off required)

**Brief:** `docs/codex-briefs/2026-07-21-hub-mcp-crypto-state-micro-brief.md`
**Executed:** 2026-07-21, read-only inventory. **No tool built.**
**Status:** **Phase 0 HALTED at the vendor-call stop-gate.** The endpoint triggers
outbound vendor calls; per the brief this hands to ATLAS for sizing **before any
build**. Full inventory below so ATLAS decides on evidence, not assertion.

---

## Q3 FIRST — the load-bearing gate: DOES IT TRIGGER VENDOR CALLS? **YES.**

`GET /api/crypto/state/{symbol}` (`backend/api/crypto_market.py:679`) is **not**
cache-only. It calls the vendor clients directly on every request, each guarded
only by a 300s in-process cache:

| Sub-block | Call (file:line) | Vendor | Fallback chain (extra outbound on cold cache) |
|---|---|---|---|
| funding | `coinalyze_client.get_funding_rate` (:714) | Coinalyze `/funding-rate` | → OKX `/public/funding-rate` |
| open_interest | `coinalyze_client.get_open_interest` (:736) | Coinalyze `/open-interest-history` | → OKX `/public/open-interest` → OKX `/market/candles` (USD conv) |
| basis | `binance_client.get_quarterly_basis` (:748) | Binance spot + futures `/ticker/price` | **Binance is HTTP-451 geo-blocked from Railway** → OKX spot + OKX perp `/ticker` |
| atr (bars) | `jobs.crypto_bars.fetch_crypto_ohlc` (:771) | Binance-vision spot klines / OKX candles | per-symbol source |
| liquidations | `coinalyze_client.get_liquidations` (:789) | Coinalyze `/liquidation-history` | → OKX `/public/liquidation-orders` |

**Fan-out per single-symbol invocation (cold cache):** 5 logical fetches,
**up to ~10–12 raw outbound HTTP requests**. `basis` alone is **structurally
~4 every cold fetch** — Binance spot + futures both 451 from Railway, then both
OKX fallbacks fire. A committee pass reading BTC+ETH doubles it; a full
six-symbol sweep on cold cache is **~50–70 outbound vendor requests**.

**Cache warmth is thin.** The 300s TTL is in-process; the only same-process
warmer is `crypto_cycle_engine` (hourly). 300s ≪ 3600s, so the caches are cold
for ~92% of each hour. A committee pass is far more likely to hit cold caches
and pay full fan-out than to ride a warm one.

### The budget the brief names does not govern this endpoint

The brief says "size against the 17K SHED / 18K ESCALATE thresholds." Those are
in `backend/jobs/uw_budget_watchdog.py:39-40` and meter the **daily UW request
total** — Unusual Whales only. This endpoint calls **Coinalyze / Binance / OKX**,
none of which the UW watchdog counts. So:

- The named 17K/18K ceiling is **not** the relevant limit.
- The real limits are **Coinalyze's plan rate limit** (the client has 429 →
  `sleep(60)` handling at `coinalyze_client.py:155-158`, so it already expects to
  hit it) and OKX public-endpoint limits.
- **There is no watchdog on crypto-vendor spend today.** A committee-invoked
  tool that fans out to these vendors would be the first uncapped, human-triggered
  multiplier on an unmonitored budget. That is precisely the risk the brief's gate
  exists to catch — it just named the wrong meter.

**This is the ATLAS sizing question, and it is a real one. Build halts here.**

---

## Q1 — Field inventory (`get_crypto_state`, returns at `crypto_market.py:902-915`)

Top-level keys: `symbol` (str), `tier` (int 1–3), `capabilities` (dict, the
`CRYPTO_SYMBOL_MATRIX` entry), `generated_at` (ISO str), plus eight sub-blocks.
Every sub-block is a `_field_envelope` (`:661`): `{**data, as_of, data_age_seconds,
degraded}`. **The envelope is fail-CLOSED at construction** — `degraded` defaults
to `True` when passed `None` (`:670`). Good, and it is the base the tool must
preserve.

| Block | Payload keys | Source |
|---|---|---|
| session | state, session_label, partition | `utils.crypto_sessions` (pure compute + gate_config) |
| funding | rate_pct, signal, na_reason | Coinalyze (vendor) |
| open_interest | current_oi_usd, signal, na_reason | Coinalyze (vendor) |
| basis | basis_annualized_pct, signal, na_reason | Binance→OKX (vendor) |
| tape_health | state, slope, spot_cvd, perp_cvd | Postgres `crypto_tape_health_log` (DB) |
| regime | state, degrade_reason | Postgres `crypto_regime_log` (DB) |
| atr | atr | bars (vendor) |
| liquidations | total_usd, long_pct, composition, signal | Coinalyze (vendor) |

Split by cost: **5 vendor-backed** (funding/OI/basis/atr/liquidations),
**3 DB/compute-backed and cheap** (session/regime/tape_health).

---

## Q2 — Per-field health, and the fail-open asymmetry (matters for Phase 1's rule #1)

All eight carry an independent `degraded`. But the **inputs** to that flag are
inconsistent, and the inconsistency is exactly the class of bug just fixed:

- **funding** (`:716`): bare `.get("health_status")` — fail-CLOSED (the
  `db5e398` path). Correct.
- **OI** (`:740`), **basis** (`:752`): `.get("health_status", "LIVE")` —
  **fail-OPEN**. A missing field coerces to healthy. This is the same latent
  pattern that hid the cache bug on OI/term_structure for its whole life; it is
  live in this endpoint right now.
- **liquidations** (`:793`): keys only on `is_na`/`error`, ignores
  `health_status` entirely.
- **regime**/**tape_health**: DB `degraded` column OR staleness (regime > 7200s,
  tape > 600s).

Consequence for the tool: **the brief's Phase-1 rule #1 (no fail-open defaults)
cannot be satisfied by faithfully mirroring the endpoint** — the endpoint itself
fails open on OI and basis. The tool must either (a) re-derive per-block health
fail-closed at the wrapper, or (b) the endpoint's OI/basis defaults get fixed
first. Flagging as a design decision for ATLAS, not resolving unilaterally.

---

## Q4 — Symbol coverage (live probe, all six, 2026-07-21 ~22:1xZ)

Source of truth: `backend/config/crypto_symbol_matrix.py` (`CRYPTO_SYMBOL_MATRIX`).
Live `degraded` per block, this instant:

| Symbol | tier | fund | oi | basis | liq | atr | sess | regime | tape |
|---|---|---|---|---|---|---|---|---|---|
| BTC | 1 | ok | ok | ok | ok | ok | ok | **deg** | **deg** |
| ETH | 1 | ok | ok | ok | **deg** | ok | ok | **deg** | **deg** |
| SOL | 2 | ok | ok | ok | **deg** | ok | ok | **deg** | **deg** |
| HYPE | 3 | ok | ok | ok | **deg** | ok | ok | **deg** | **deg** |
| ZEC | 3 | ok | ok | ok | **deg** | ok | ok | **deg** | **deg** |
| FARTCOIN | 3 | ok | ok | **deg** | **deg** | ok | ok | **deg** | **deg** |

Three findings, none of which the committee can currently see (the whole point
of the brief), and all of which the tool would expose:

1. **funding = ok across all six** — first cross-symbol confirmation that
   `db5e398` holds beyond BTC. Good.
2. **regime = degraded on ALL six, tape_health = degraded on ALL six.** Not a
   coverage gap — a live staleness signal. Regime rows are >7200s old and/or
   flagged; tape rows >600s old, everywhere. Worth its own look (is the
   regime/tape writer cadence keeping up?), but **out of scope here** — noted,
   not investigated. It does harden the case that the committee is flying blind
   on degraded crypto state today.
3. **liquidations degraded on 5/6 (all but BTC); basis degraded on FARTCOIN.**
   Consistent with the known Tier-3 thinness and the FARTCOIN spot-fetch gap.

The tool must render all of the above as `degraded`/`unavailable` honestly — and
the live data proves that is the common case, not the exception.

---

## Q5 — Cycle Extremes seam

`/api/crypto/cycle-extremes` **exists** (`crypto_market.py:989`, →
`crypto_cycle_engine.evaluate_cycle_extremes`). It is **not** part of
`/state/{symbol}` and, critically, `evaluate_cycle_extremes` calls the vendor
clients **again** (funding/OI/basis/liq at `crypto_cycle_engine.py:157-345`).
Folding it into this tool would **compound** the vendor fan-out, not reuse it.
Per the brief's out-of-scope note it stays out; recorded as a seam. If a cycle
surface is wanted later it should read `crypto_cycle_log` (persisted hourly), not
re-invoke the engine.

---

## Two build paths for ATLAS to choose between

The vendor-call gate is not fatal to the tool — it is a fork.

**Path A — live-wrap `/state/{symbol}` as-is.** Freshest data, simplest code.
Cost: every committee call fans out ~5–12 outbound vendor requests × symbols on
cold cache, against an **unmonitored** Coinalyze/OKX budget. Would want a
crypto-vendor watchdog before it is safe for committee-frequency use.

**Path B — DB/cache-backed, zero new vendor calls (matches `hub_get_board_state`
"never triggers a new request").** Serve the vendor-backed blocks from their
**already-persisted** hourly snapshots in `crypto_cycle_log.cells` (funding/OI/
basis/liq are written there every hour — established in the DEF-FUNDING-DUTY-CYCLE
Phase 0), plus `crypto_regime_log`, `crypto_tape_health_log`, and session
compute. Cost: data is **hourly-vintage, not live**, and `crypto_cycle_log`'s
field coverage must be verified against the eight blocks before committing. But
it is config-free, adds no vendor spend, and its freshness is honestly labeled by
the existing `as_of`/`data_age_seconds` machinery.

**My recommendation (ATLAS/Fable's call, not mine):** **Path B.** It fits the
governing constraint for this whole window — Nick is away 2026-08-04→15 with no
ability to deploy, so anything committee-facing must be safe and recoverable
without code changes. An uncapped live-vendor multiplier triggered by phone-based
committee passes is the opposite of that. Path B trades live-vintage for
zero-budget-risk and zero new failure surface, which is the right trade for a
tool whose whole purpose is to be leaned on while nobody can fix it. It also
sidesteps the fail-open OI/basis problem, since `crypto_cycle_log` carries its
own per-cell `state`.

---

## Done-definition status (Phase 0 only)

1. ✅ Inventory reported with named files/lines.
2. ⛔ **ATLAS sign-off REQUIRED and NOT obtained** — endpoint triggers vendor
   calls. **This is the stop.** Nothing in Phase 1+ is started.
3–8. Not started (correctly gated behind #2).

**Handing to ATLAS/Fable:** pick Path A (with a vendor watchdog) or Path B
(DB-backed). I recommend B. Await the call before building.
