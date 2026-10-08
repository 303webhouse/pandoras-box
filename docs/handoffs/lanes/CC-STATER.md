# CC-STATER lane — status

**Written:** 2026-10-07 22:12 MDT (2026-10-08 04:12 UTC)
**Worked against:** `origin/main` = `6e57c24`
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`. Branch `claude/stater-r742-stale`.
**Hub at read time:** not re-timed this turn.

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
- The database login is read-only.
- No Railway CLI, no deploys, no environment-variable changes.

## Composite-break dates (R-IV.727(e) / R-IV.742(b))
First cycle after `ed5491c` plus the scheduler boot fix: **2026-10-08 00:41:05.72 UTC
(2026-10-07 18:41:05 MDT)**.

| Symbol | Liquidations | Open interest |
|---|---|---|
| BTC | still NA, okx-sourced | first LIVE, Coinalyze-sourced, this cycle |
| ETH | still NA, okx-sourced | (not dated this cycle) |
| SOL | still NA, okx-sourced | (not dated this cycle) |
| HYPE | first LIVE, Coinalyze-sourced, this cycle | — |
| ZEC | first LIVE, Coinalyze-sourced, this cycle | — |
| FARTCOIN | first LIVE, Coinalyze-sourced, this cycle | — |

BTC liquidations are not yet genuinely Coinalyze-sourced. That date is still open.
ETH and SOL first LIVE liquidations: still open.

## R-IV.742 — in flight (nothing merges until SPINE rules)
`stale` on a cycle cell is age only. Vendor health is `health_status`. Signal goes
UNKNOWN only on stale-by-age or an explicit `error`. Cap and froth share one
funding and one OI call per symbol (36 → 24). Page snapshot cache is 60 s.

**Consumers of cycle-cell `stale` (listed before the change):**
- `_make_cell` / `crypto_cycle_log.cells` (writer)
- `services/read_only/crypto_state.py` `_classify(..., stale_flag=)` — used the
  flag as a health failure (`degraded`). It already has `state` and
  `row_degraded` for health, so it does not need vendor health under the name
  `stale`. After the correction, LIVE + age-stale reads `stale`.
- `hub_mcp` crypto_state via that `_classify`
- `test_stater_p0_reads.py`, `test_hub_mcp_crypto_state.py`, `test_s3_phase2_cycle_engine.py`
- `frontend/stater.js` reads tape/envelope `stale` (age from `envelope()`), not
  cycle cells — left alone.

## R-IV.741 — accepted
`claude/stater-r741-lsr` at `8c4d31e`. BUILD merges it under R-IV.743. This
branch does not contain that commit.

## R-IV.742(e) — USD vs USDT aggregates, proposed, no code
From `/future-markets` (filed in `symbol-capability-matrix.md`; BUILD's
R-IV.735(e) read). Hub maps BTC/ETH/SOL to the USD-margined `.A`; HYPE/ZEC/
FARTCOIN already use USDT.

| Base | Aggregates that exist | Current map | Proposed |
|---|---|---|---|
| BTC | `BTCUSD_PERP.A` (coin-margined), `BTCUSDC_PERP.A`, `BTCUSDT_PERP.A` (linear) | `BTCUSD_PERP.A` | `BTCUSDT_PERP.A` |
| ETH | `ETHUSD_PERP.A`, `ETHBTC_PERP.A`, `ETHUSDT_PERP.A` | `ETHUSD_PERP.A` | `ETHUSDT_PERP.A` |
| SOL | `SOLUSD_PERP.A`, `SOLUSDT_PERP.A`, `SOLUSDC_PERP.A` | `SOLUSD_PERP.A` | `SOLUSDT_PERP.A` |

A remap would move funding, OI, and liquidations onto the linear majority.
BTC OI would leave the ~$1.31B coin-margined slice for a much larger USDT
notional; `oi_change_4h` % would be a different market. Liquidation buckets
in a 2-hour window would be denser, so BTC/ETH/SOL would be likelier to stay
Coinalyze LIVE and enter the `$5M` hourly gate instead of falling to OKX NA.
Funding and term-structure would be the USDT-perp rate, not the inverse-perp
rate. Do not code this until SPINE rules.

## R-IV.727 — merged
`ed5491c`. Units USD; Coinalyze OI/liq score again; OKX stays unscored.

## R-IV.700 — merged
`eff4077`. Spot stays.

## Robinhood
US perps announced for "the coming months", not live, no keyless feed. Charter
forbids holding the principal's trading key.

## Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-r742-stale` | Pushed. (c)+(d) only. | After SPINE's merge ruling. |
| `claude/stater-r741-lsr` | Accepted. BUILD merges under R-IV.743. | BUILD. |
| `claude/stater-r707-liq` | Merged (`ed5491c`). | Done. |

## What the next CC-STATER session should do first
Hold r742 until SPINE rules. Do not add the USDT remap unless a ruling names
it. Do not skip HYPE Binance spot. Do not rebuild the Binance VPN. Do not
edit `bias_scheduler.py`.
