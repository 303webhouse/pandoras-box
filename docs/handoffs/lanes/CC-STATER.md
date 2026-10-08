# CC-STATER lane — status

**Written:** 2026-10-08 08:51 MDT (2026-10-08 14:51 UTC)
**Worked against:** `origin/main` = `25d579e`
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`. Branch `claude/stater-r753-dates`.
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

## Remap break (R-IV.753(a) / R-IV.745)
First cycle on the USDT-linear map: **2026-10-08 05:41:24.698 UTC
(2026-10-07 23:41:24 MDT)** — BTC. ETH 05:41:25.209Z, SOL 05:41:26.969Z.
That timestamp is also **BTC's first genuinely Coinalyze-sourced liquidations
date** (closes the open line from R-IV.742(b)).

All nine cells (funding, open_interest, liquidations × BTC/ETH/SOL) were
coinalyze / LIVE / not stale. Liquidations moved NA/okx → LIVE/coinalyze,
which confirms R-IV.742(e).

On that cycle BTC liquidations 19,335,585.87 and ETH 5,810,020.41 were FIRING
against the $5M gate. OI jumped 6× (BTC), 16× (ETH), 17× (SOL) because the
population changed. ETH and SOL open_interest DEGRADED → LIVE cannot be
credited to r742 or r745: both shipped in one deploy (R-IV.753(b)).

No computation compares a value across this switch (R-IV.725(c)4).
Thresholds are unchanged until SPINE rules after the week.

## 7-day collection (R-IV.745(c) widened by R-IV.753(c)) — no threshold change
Window starts at 05:41:24.698Z. Report on **2026-10-15 or after**. Per symbol:

- Hourly liquidation totals: count, median, p90, max, hours that crossed $5M.
- `oi_change_4h`: median, p10, p90, max |value|.
- How often `oi_extreme` fires.

Any OI or oi_extreme threshold calibrated before 05:41:24Z was calibrated on
a different population.

## Composite-break dates (R-IV.727(e) / R-IV.742(b))
First cycle after `ed5491c` plus the scheduler boot fix: **2026-10-08 00:41:05.72 UTC
(2026-10-07 18:41:05 MDT)**.

| Symbol | Liquidations | Open interest |
|---|---|---|
| BTC | first LIVE Coinalyze-sourced: **2026-10-08 05:41:24.698Z** (remap) | first LIVE Coinalyze-sourced: 2026-10-08 00:41:05.72Z |
| ETH | first LIVE Coinalyze-sourced: 2026-10-08 05:41:25.209Z (remap) | LIVE at remap cycle; DEGRADED→LIVE confound (r742+r745 one deploy) |
| SOL | first LIVE Coinalyze-sourced: 2026-10-08 05:41:26.969Z (remap) | LIVE at remap cycle; DEGRADED→LIVE confound (r742+r745 one deploy) |
| HYPE | first LIVE, Coinalyze-sourced, 00:41:05.72Z cycle | — |
| ZEC | first LIVE, Coinalyze-sourced, 00:41:05.72Z cycle | — |
| FARTCOIN | first LIVE, Coinalyze-sourced, 00:41:05.72Z cycle | — |

## R-IV.745 — merged
`25d579e` / `304412c`. BTC/ETH/SOL → `BTCUSDT_PERP.A` / `ETHUSDT_PERP.A` /
`SOLUSDT_PERP.A`.

## R-IV.742 — merged
`e9e746e` / `43342ae`. stale is age only. Singleflight 36→24. 60s snapshot cache.

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
| `claude/stater-r753-dates` | Lane-file dates only. | Docs; merge when convenient. |
| `claude/stater-r745-remap` | Merged (`25d579e`). | Done. |
| `claude/stater-r742-stale` | Merged (`e9e746e`). | Done. |
| `claude/stater-r741-lsr` | Merged (`1bd7810`). | Done. |
| `claude/stater-r707-liq` | Merged (`ed5491c`). | Done. |

## What the next CC-STATER session should do first
On **2026-10-15 or after**, report the 7-day collection (liquidations +
`oi_change_4h` + oi_extreme fire rate) per symbol. Do not change any
threshold until SPINE rules. Do not skip HYPE Binance spot. Do not rebuild
the Binance VPN. Do not edit `bias_scheduler.py`.
