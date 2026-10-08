# CC-STATER lane — status

**Written:** 2026-10-07 22:29 MDT (2026-10-08 04:29 UTC)
**Worked against:** `origin/main` = `1bd7810` (43342ae had not landed at cut; remap diff is the three map entries only)
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`. Branch `claude/stater-r745-remap`.
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

## R-IV.745 — in flight (BUILD merges on a three-entry diff, R-IV.744(c))
BTC → `BTCUSDT_PERP.A`, ETH → `ETHUSDT_PERP.A`, SOL → `SOLUSDT_PERP.A`.
HYPE / ZEC / FARTCOIN already use USDT aggregates. Funding, OI, and liquidations
for BTC/ETH/SOL move to the linear majority. No computation compares a value
across this switch (R-IV.725(c)4). Thresholds are unchanged.

**Remap break date:** TBD — record BUILD's first post-merge hourly cycle here.

## $5M threshold collection (R-IV.745(c)) — no threshold change
For the first 7 days after the remap, collect hourly liquidation totals per
symbol: count, median, p90, max, and hours that crossed $5M. Report on
**2026-10-15 or after**. Thresholds are ruled then. FARTCOIN is expected never
to cross; BTC linear is expected to cross far more often than the coin-margined
slice did.

## Composite-break dates (R-IV.727(e) / R-IV.742(b))
First cycle after `ed5491c` plus the scheduler boot fix: **2026-10-08 00:41:05.72 UTC
(2026-10-07 18:41:05 MDT)**.

| Symbol | Liquidations | Open interest |
|---|---|---|
| BTC | still NA, okx-sourced (pre-remap) | first LIVE, Coinalyze-sourced, that cycle |
| ETH | still NA, okx-sourced (pre-remap) | (not dated that cycle) |
| SOL | still NA, okx-sourced (pre-remap) | (not dated that cycle) |
| HYPE | first LIVE, Coinalyze-sourced, that cycle | — |
| ZEC | first LIVE, Coinalyze-sourced, that cycle | — |
| FARTCOIN | first LIVE, Coinalyze-sourced, that cycle | — |

## R-IV.742 — accepted
`claude/stater-r742-stale` at `43342ae`. stale is age only. Singleflight 36→24.
60s snapshot cache. BUILD merges under R-IV.744(b).

## R-IV.741 — merged
`1bd7810` on `main`.

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
| `claude/stater-r745-remap` | Pushed. Three map entries + tests + this file. | Yes — merge if the diff is only that (R-IV.744(c)). |
| `claude/stater-r742-stale` | Accepted (`43342ae`). | BUILD under R-IV.744(b). |
| `claude/stater-r741-lsr` | Merged (`1bd7810`). | Done. |
| `claude/stater-r707-liq` | Merged (`ed5491c`). | Done. |

## What the next CC-STATER session should do first
If BUILD merged the remap: wait for the first hourly cycle and write the remap
break date above. On 2026-10-15 or after, report the 7-day liquidation
totals (count / median / p90 / max / hours ≥ $5M) per symbol. Do not change
any threshold until SPINE rules. Do not skip HYPE Binance spot. Do not
rebuild the Binance VPN. Do not edit `bias_scheduler.py`.
