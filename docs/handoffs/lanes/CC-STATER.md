# CC-STATER lane — status

**Written:** 2026-10-07 16:33 MDT (2026-10-07 22:33 UTC)
**Worked against:** `origin/main` = `db1d864`
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`. Branch `claude/stater-r707-liq`.
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

## R-IV.727 — one commit after `ff25480` (R-IV.728)
Units settled USD under R-IV.724(b). `COINALYZE_UNITS_UNVERIFIED` is gone. Coinalyze-sourced
liquidations, open_interest, and oi_extreme score again. `convert_to_usd="true"` stays, with a
one-line comment that it is inert because the values are already USD. OKX fallbacks stay
`OKX_FALLBACK_UNSCORED` (R-IV.707(d)). Composition `$5M` is `$5M` of hourly liquidations.

**R-IV.725 accepted:** history callers send UNIX seconds via `_history_range_seconds`; snapshots
untouched; five cells take source from the vendor result; NA gate as instructed; OI divergence
and oi_extreme compare points inside one payload (never a % change across two sources);
`.A` aggregates may carry no LSR data.

**This is the only commit after `ff25480`.** BUILD merges on that condition.

## Composite-break dates (R-IV.727(e)) — waiting on BUILD
Not live yet. When BUILD reports the first hourly cycle after the deploy, record here:

- Date BTC liquidations and open interest became genuinely Coinalyze-sourced:
  **TBD (first post-deploy hourly cycle).**
- First LIVE liquidations date per alt:
  - ETH: **TBD**
  - SOL: **TBD**
  - HYPE: **TBD**
  - ZEC: **TBD**
  - FARTCOIN: **TBD**

That is the composite's break. Do not backfill from pre-seconds / units-gated cycles.

## R-IV.727(d) — long/short, proposed, no code
Hub currently asks `/long-short-ratio-history` with the same `.A` map as funding. Empty
history → `ratio: None`; no OKX fallback. Scope-only proposal for BUILD:

`GET /v1/future-markets`, then for each of BTC, ETH, SOL, HYPE, ZEC, FARTCOIN keep rows
where `base_asset` matches and `has_long_short_ratio_data` is true (prefer `is_perpetual`).
Name the Coinalyze market symbol that carries LSR for that base. Optional confirm:
`GET /v1/long-short-ratio-history` on that symbol with a UNIX-seconds window (no
`convert_to_usd`). STATER does not hold the Coinalyze key; BUILD makes the read on request.

## R-IV.718 / R-IV.715 / R-IV.707
Source-from-result for liquidations stands. The 715 "0 of 2,153 OKX-sourced" count
read a literal. Composition `$5M` gate stands. Seed vs hardcoded `$5M`/75% recorded.

## R-IV.700 — merged
Cycle remap + strategy engine off fapi + HYPE history skip is on `main` (`eff4077`).
Spot stays.

## Robinhood
US perps announced for "the coming months", not live, no keyless feed. Charter
forbids holding the principal's trading key.

## Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-r707-liq` | One commit after `ff25480`. Pushed. | Yes — merge if that is the only commit (R-IV.728). |
| `claude/stater-r700-queue` | Merged (`eff4077`). | Done. |
| `claude/stater-r692-cache` | Cache 4 s → 8 s. | BUILD accepted (R-IV.699). |

## What the next CC-STATER session should do first
If BUILD merged: wait for the first hourly cycle, then fill the composite-break dates
above (BTC Coinalyze-sourced liq+OI date; each alt's first LIVE liquidations date).
Do not skip HYPE Binance spot. Do not rebuild the Binance VPN. Do not add a second
commit on this branch if merge is still pending.
