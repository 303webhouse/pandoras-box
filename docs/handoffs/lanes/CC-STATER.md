# CC-STATER lane — status

**Written:** 2026-10-07 11:07 MDT (2026-10-07 17:07 UTC)
**Worked against:** `origin/main` = `b8515f1`
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`. Branch `claude/stater-r707-liq`.
**Hub at read time:** `/api/crypto/state` HTTP 200. BTC liquidations envelope not degraded; SOL liquidations envelope degraded. Funding/OI/term_structure LIVE on the alt symbols in the same cycle log tick.

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

## R-IV.707 — in flight, not merged
SPINE: fix the primary first; the fallback never scores. Reports for (c) and (e) are in the
R-IV.707 reply. Code on this branch is (d) only. Nothing merges until SPINE rules.

- **(e)** Composition is size-gated, then share-gated. 90 → balanced is intended. Not changed.
- **(c)** Coinalyze `/liquidation-history` is the primary defect for non-BTC. Sister endpoints
  (funding, OI, term_structure) are LIVE for the same aggregate symbols on the same tick, so
  the discriminator is that endpoint, not the `.A` format and not `from`/`to` milliseconds.
  Local env has no Coinalyze key (charter forbids Railway CLI); live 200 bodies were not
  captured. No primary request change. BTC's `/liquidation-history` request stays as-written.
- **(d)** Non-BTC OKX fallback: `instFamily=<BASE>-USDT`; USD = contracts × ctVal × bkPx with
  ctVal from `/public/instruments`, cached. Source `"okx"`. Cell state **NA**, reason
  `OKX_FALLBACK_UNSCORED`. `_compute_composite` live lists are LIVE-only, so it cannot FIRING
  or move the composite. BTC `uly=BTC-USDT` and source `okx_fallback` unchanged.

**Alt cells have not gone LIVE.** When they first do (after a merge that lets the primary
answer), record that date here so the composite's history shows the break.

## R-IV.706 — scoped, not patched
OKX `instId` → HTTP 400 code 50015 for every non-BTC symbol. BTC `uly=BTC-USDT` is the
positive control. Units defect was separate. Cycle log 2026-07-17 → 10-07: every non-BTC
liquidations cell DEGRADED on 100% of ~2,150 ticks.

## R-IV.700 — merged
Cycle remap + strategy engine off fapi + HYPE history skip is on `main` (`eff4077`).
BUILD re-timed HYPE: 1.873 s → 0.701 s cold. Spot stays.

## Robinhood
US perps announced for "the coming months", not live, no keyless feed. Charter
forbids holding the principal's trading key.

## Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-r707-liq` | Pushed. (d) only. Wait for SPINE. | No — do not merge until SPINE rules on the report. |
| `claude/stater-r700-queue` | Merged (`eff4077`). | Done. |
| `claude/stater-r692-cache` | Cache 4 s → 8 s. | BUILD accepted (R-IV.699). |

## What the next CC-STATER session should do first
Wait for SPINE's ruling on R-IV.707. Do not merge. Do not change composition. Do not change
BTC's Coinalyze `/liquidation-history` request or BTC's OKX `uly` path. If SPINE wants the
six Coinalyze raw bodies, that read needs a key this lane does not hold. Do not skip HYPE
Binance spot. Do not rebuild the Binance VPN. When alt liquidations first go LIVE, date it
in this file.
