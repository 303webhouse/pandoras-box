# CC-STATER lane — status

**Written:** 2026-10-07 12:04 MDT (2026-10-07 18:04 UTC)
**Worked against:** `origin/main` = `2fd0f9d`
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`. Branch `claude/stater-r707-liq`.
**Hub at read time:** not re-timed this turn.

## Why this lane exists
SPINE chartered CC-STATER (R-IV.618) to own Stater Swap, the hub's crypto surface.
- **Frontend:** `frontend/stater.*`.
- **Crypto backend:** `api/crypto_market.py`, `api/btc_signals.py`, `bias_filters/crypto_*`,
  `config/crypto_*`, `jobs/crypto_*`, `strategies/crypto_setups.py`, `strategies/btc_market_structure.py`,
  `services/read_only/crypto_*`, `hub_mcp/tools/crypto_*` and `utils/crypto_sessions.py`.

It inherits S-6M's ownership of `stater.*`. It never touches Agora files, `backend/signals/`,
`main.py`, schema or migrations, or positions and cash. It holds no exchange credentials and places
no orders.

**On the principal's PC (R-IV.628(b)):**
- Never check out, commit to or push `main`; BUILD merges.
- The database login is read-only.
- No Railway CLI, no deploys, no environment-variable changes.

## R-IV.715 — in flight, not merged
Gap against R-IV.707(d): BTC's OKX path kept source `okx_fallback` and still entered the
scoring branch. This turn: that cell goes through the same NA / `OKX_FALLBACK_UNSCORED`
branch (`vendor_src in ("okx", "okx_fallback")`). BTC's Coinalyze `/liquidation-history`
request and its Coinalyze output stay as-written. BTC's OKX request is still `uly=BTC-USDT`
and `sz × 0.01 × bkPx` (no instruments call).

`crypto_cycle_log` 2026-07-17 → 10-07: **0** of 2,153 BTC liquidations cells were
OKX-sourced (all 2,153 source `coinalyze`, LIVE). This change does not rewrite a
recorded cell.

Recorded, not changed: `$5M` and 75% are hardcoded in `coinalyze_client.py` while the
seed config holds the same values. Taken up with the per-symbol threshold question.

**Alt cells have not gone LIVE.** When they first do, record that date here.

Coinalyze raw bodies for non-BTC `/liquidation-history` are BUILD's (R-IV.714(b)).

## R-IV.707 — accepted, plus the 715 gap
Composition is the `$5M` size gate. Primary isn't symbol format or timestamps. Non-BTC
OKX: `instFamily`, instruments `ctVal`, source `okx`, NA, LIVE-only fence at 462–463.

## R-IV.700 — merged
Cycle remap + strategy engine off fapi + HYPE history skip is on `main` (`eff4077`).
BUILD re-timed HYPE: 1.873 s → 0.701 s cold. Spot stays.

## Robinhood
US perps announced for "the coming months", not live, no keyless feed. Charter
forbids holding the principal's trading key.

## Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-r707-liq` | Pushed. Wait for SPINE. | No — BUILD merges after SPINE rules. |
| `claude/stater-r700-queue` | Merged (`eff4077`). | Done. |
| `claude/stater-r692-cache` | Cache 4 s → 8 s. | BUILD accepted (R-IV.699). |

## What the next CC-STATER session should do first
Wait for SPINE's ruling on R-IV.715. Do not merge. Do not change composition or the
hardcoded `$5M`/75% (recorded). Do not change BTC's Coinalyze request. Do not skip
HYPE Binance spot. Do not rebuild the Binance VPN. When alt liquidations first go
LIVE, date it in this file.
