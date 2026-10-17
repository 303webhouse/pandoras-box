# CC-STATER lane — status

**Written:** 2026-10-17 02:40 MDT (2026-10-17 08:40 UTC). Data read at 08:33 UTC.
**Worked against:** `origin/main` = `f9f67c4d`
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`. Branch `claude/stater-r1197-report` (docs only).
**Hub at read time:** `/health` healthy, build `f9f67c4d`, process started 08:27 UTC.

## Why this lane exists
SPINE chartered CC-STATER (R-IV.618) to own Stater Swap, the hub's crypto surface.
- **Frontend:** `frontend/stater.*`.
- **Crypto backend:** `api/crypto_market.py`, `api/btc_signals.py`, `bias_filters/crypto_*`,
  `config/crypto_*`, `jobs/crypto_*`, `strategies/crypto_setups.py`, `strategies/btc_market_structure.py`,
  `services/read-only/crypto_*`, `hub_mcp/tools/crypto_*` and `utils/crypto_sessions.py`.

It inherits S-6M's ownership of `stater.*`. It never touches Agora files, `backend/signals/`,
`main.py`, schema or migrations, or positions and cash. It holds no exchange credentials and places
no orders.

**On the principal's PC (R-IV.628(b)):**
- Never check out, commit to or push `main`; BUILD merges.
- The database login is read-only (`stater_ro`, SELECT only).
- No Railway CLI, no deploys, no environment-variable changes.

## 7-day collection report (R-IV.745(c) / R-IV.753(c) / R-IV.1197(a))
Window: 2026-10-08 05:41:24.698Z to 2026-10-15 05:41:24.698Z, inclusive. That is **169 hourly
cycles per symbol** (first 05:41:24.698Z, last 05:38:24Z; cadence 54 to 64 min, no gap over 90 min).
No threshold was changed. All figures come from `crypto_cycle_log`, filtered inside the database.

**What the liquidation number is.** The `liquidations` cell value is long + short liquidations
summed over the last two 1-hour buckets of a 2-hour Coinalyze request (`history[-2:]` in
`coinalyze_client.get_liquidations`). It is not a single clock hour. Consecutive cycles share a
bucket, so one large hour can lift two cycles. The raw buckets are not stored; only this sum is.
Counts below are therefore cycles, not distinct hours. First-cycle values reproduce BUILD's
figures (BTC 19,335,585.87; ETH 5,810,020.41).

### Liquidations (USD, two-bucket sum per cycle)
| Symbol | Cycles | Median | p90 | Max | Cycles >= $5M | Runs of consecutive cycles >= $5M | Cell FIRING |
|---|---|---|---|---|---|---|---|
| BTC | 169 | 620,305 | 8,952,168 | 61,184,017 | 22 (13.0%) | 9 (longest 8) | 17 |
| ETH | 169 | 627,412 | 8,802,284 | 104,604,981 | 23 (13.6%) | 9 (longest 8) | 19 |
| SOL | 169 | 117,834 | 1,830,999 | 14,074,376 | 8 (4.7%) | 3 (longest 4) | 8 |
| HYPE | 164 | 10,896 | 248,223 | 7,134,416 | 2 | n/a | 2 |
| ZEC | 169 | 115,320 | 1,160,883 | 10,592,495 | 4 | n/a | 3 |
| FARTCOIN | 146 | 1,640 | 15,323 | 288,982 | 0 | n/a | 0 |

BTC/ETH/SOL were coinalyze / LIVE in 169 of 169 cycles for funding, open interest, liquidations
and oi_extreme. HYPE has 5 and FARTCOIN 23 cycles where Coinalyze returned nothing and the OKX
fallback (NA, `OKX_FALLBACK_UNSCORED`) was used; those cycles are excluded from their rows.
Percentiles for threshold work: BTC p80 2.30M, p95 19.74M, p99 45.70M; ETH p80 3.26M, p95 16.55M,
p99 91.45M; SOL p80 0.70M, p95 4.04M, p99 12.81M; HYPE p99 4.87M; ZEC p99 7.12M; FARTCOIN p99 201,648.

### oi_change_4h (percent) and oi_extreme (threshold 5.0, all cycles)
| Symbol | Median | p10 | p90 | Max | Max abs | Fires | Fire rate |
|---|---|---|---|---|---|---|---|
| BTC | 0.000 | -1.136 | 0.832 | 1.740 | 4.340 | 0 | 0.00% |
| ETH | 0.000 | -1.538 | 1.272 | 4.790 | 8.180 | 0 | 0.00% |
| SOL | -0.100 | -1.646 | 1.538 | 3.550 | 4.830 | 0 | 0.00% |
| HYPE | 0.080 | -1.936 | 2.572 | 12.390 | 12.390 | 4 | 2.37% |
| ZEC | -0.150 | -3.230 | 2.494 | 9.900 | 9.900 | 5 | 2.96% |
| FARTCOIN | 0.040 | -3.426 | 2.836 | 10.970 | 10.970 | 10 | 5.92% |

oi_extreme only fires on positive change above 5.0 (FROTH). Positive p99: BTC 1.578, ETH 3.923,
SOL 3.334. The OI series is in USD, so a 4h change mixes positioning with price.

### Proposals only (SPINE rules; nothing changed)
1. **Liquidations, $5M gate:** keep for BTC, ETH, SOL. It fires on 13.0% / 13.6% / 4.7% of cycles.
   **FARTCOIN:** the gate cannot fire (max 288,982, 58x below). If SPINE wants it live, the basis
   number is FARTCOIN p99 = $201,648 (about 1 to 2 cycles a week). HYPE and ZEC need nothing:
   their p99 is near $5M already.
2. **oi_extreme, 5.0:** dead on BTC/ETH/SOL this week (max 1.74 / 4.79 / 3.55); live on HYPE, ZEC
   and FARTCOIN. If SPINE wants a non-dead BTC/ETH/SOL gate, the basis numbers are the positive p99s
   above (1.58 / 3.92 / 3.33). **Recommendation: hold.** The sample is one regime, and 169 hourly
   values of a 4-hour change are about 42 independent windows. Revisit with LAB's long-history
   replay (by 2026-11-30).

## Remap break (R-IV.753(a) / R-IV.745)
First cycle on the USDT-linear map: **2026-10-08 05:41:24.698 UTC (2026-10-07 23:41:24 MDT)** —
BTC. ETH 05:41:25.209Z, SOL 05:41:26.969Z. That is also BTC's first genuinely Coinalyze-sourced
liquidations date. OI jumped 6x (BTC), 16x (ETH), 17x (SOL) because the population changed.
ETH/SOL open_interest DEGRADED to LIVE cannot be credited to r742 or r745 (one deploy).
No computation compares a value across this switch (R-IV.725(c)4).

## Current state at 2026-10-17 08:33 UTC (R-IV.1197(b))
**Cycle:** last writes 07:37 UTC for all six symbols (56 min old at read; the hourly cadence is on time).

| Symbol | Funding | Open interest | Liquidations | Source |
|---|---|---|---|---|
| BTC | LIVE 07:35:46Z | LIVE 07:37:16Z | LIVE 07:37:18Z | coinalyze |
| ETH | LIVE 07:37:19Z | LIVE 07:37:20Z | LIVE 07:37:20Z | coinalyze |
| SOL | LIVE 07:37:21Z | LIVE 07:37:22Z | LIVE 07:37:22Z | coinalyze |
| HYPE | LIVE 07:37:24Z | LIVE 07:37:24Z | LIVE 07:37:24Z | coinalyze |
| ZEC | LIVE 07:37:25Z | LIVE 07:37:26Z | LIVE 07:37:26Z | coinalyze |
| FARTCOIN | LIVE 07:37:27Z | LIVE 07:37:27Z | **NA 07:37:27Z (okx, unscored)** | coinalyze; liquidations okx |

BTC has 13 live cells; FARTCOIN 7 (basis cells DEGRADED, Deribit skew and Binance spot NA by
coverage, S-10 ETF flow NA, deferred).

**/stater sections.** All seven are live-wired in `frontend/stater.js` and served (`/stater.js`
and `/app/stater` return 200): S5.1 chips, S5.2 grid, S5.5 macro band, S5.3 tape band, S5.4 cycle
dial, S5.7 feed, drawer. The header comments in `stater.js` lines 1-6 and `stater.html` lines
15-16 still say "placeholders pending the SG-1 layout gate"; they are stale. What is genuinely
N/A by design: DAILY chip, FLOOR chip, floor rings, distance-to-floor, concurrent chip is
advisory, feed funding-cost and liq-ATR, S-10 ETF flow, and S-5 (dominance, ETH/BTC strip,
macro extension). The feed is honest-empty when the scanners are quiet (the crypto scanner
reports quiet: DE_LEVERAGING, MAX_LONG, WATERFALL zones). I did not eyeball the page (sign-in).

**SG-1 layout gate.** Scaffold-vs-approved-render check of S5.1 chips + S5.2 grid. CLEAR on
2026-07-24, ratified by Nick; the layout comparison was CC-produced and HELIOS's veto was not
exercised (ledger `s6-rulings-ledger.md`). It waits on nobody. The ledger shows SG-3 (HELIOS
post-deploy screenshot comparison, due 2026-08-03) as binding; I found no recorded outcome.

**Paid plans or tiers.** None of the crypto feeds needs a paid plan: Coinalyze (free-tier key,
40 calls/min), Coinbase Exchange public (BTC/ETH/SOL bars), OKX public (HYPE/FARTCOIN bars),
Binance spot mirror, Deribit public, Hyperliquid public, DeFiLlama, yfinance (VIX). The free-tier
claim for Coinalyze is from `docs/stater/STATER-SCOPE-2026-10-01.md`; I have not seen the
vendor's account page. The only paid vendor near this lane is Unusual Whales (Basic, already
paid), used by equities, not by the six crypto bar paths; it is hitting QUOTA_EXCEEDED right
now (health shows a governor block). The S-10 ETF-flow cell stays deferred because there is no
free source. No new spend is needed.

## Standing context (R-IV.1197(c))
Crypto scanners keep running but stay off the trade-idea surface, graded against always-long BTC.
LAB's long-history replay of the crypto rules comes by 2026-11-30. Nothing changes.

## Merged
- R-IV.753 dates: `claude/stater-r753-dates` is merged on `main` (`22f64542`); no longer queued.
- R-IV.745 `25d579e` / `304412c` (USDT-linear remap); R-IV.742 `e9e746e` / `43342ae`
  (stale is age only, singleflight 36 to 24 calls, 60 s snapshot cache); R-IV.741 `1bd7810`;
  R-IV.727 `ed5491c`; R-IV.700 `eff4077` (spot stays).

## Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-r1197-report` | This file and `CURSOR.md` only. | Docs; merge when convenient. |
| `claude/stater-r753-dates` | Merged. | Done. |

## Robinhood
US perps announced for "the coming months", not live, no keyless feed. Charter forbids holding
the principal's trading key.

## What the next CC-STATER session should do first
Wait for SPINE's ruling on the proposals above. No new build is open. Do not change any
threshold until SPINE rules. Do not skip HYPE Binance spot. Do not rebuild the Binance VPN.
Do not edit `bias_scheduler.py`. A one-line fix for the stale header comments in
`stater.js`/`stater.html` is available if SPINE wants it.
