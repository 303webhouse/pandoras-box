# CC-STATER lane — status

**Written:** 2026-10-06 20:45 MDT (2026-10-07 02:45 UTC)
**Worked against:** `origin/main` = `a146cd4` (feat(tide): the 66-session backfill is in…)
**Where:** the Cursor agent on the principal's PC, in `C:\th-cursor`, on `claude/stater-r692-cache` (cut from `origin/main` `a146cd4`).
**Hub at read time:** prod `a146cd4`, `status: healthy`, process started 02:42:07 UTC. Proxy flag false.

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

## R-IV.692(a) — 684 accepted
`predictedFundings` stands for five coins; HYPE's two nulls stay honest. Matrix branch
`claude/stater-r684-matrix` is still not on `origin/main` (BUILD said they merge it,
R-IV.688(d)). Last-good crypto copy is in legacy `app.js` (relayed to CC-ABACUS).

## (b) HYPE Binance spot — keep asking
Hub `GET /crypto/market?symbol=HYPE` 2026-10-07 02:42 UTC (20:42 MDT): `binance_spot`
present, `errors` empty. Same payload for BTC. FARTCOIN `binance_spot` still null
(already not asked).

It is **neither** no-listing **nor** a US block. HYPE is listed; `data-api.binance.vision`
answers from Railway (same finding as 2026-10-06 16:10 UTC). R-IV.645's skip applies
to venues that cannot answer. This one can.

## (c) Queue — response cache vs the 5 s poll
`CACHE_TTL_SECONDS` was 4. Legacy Agora polls `/crypto/market` every 5 s, so every
tick missed the cache. Raised to **8** so that poll hits. Test:
`test_response_cache_outlasts_legacy_agora_poll`.

Still open, not this branch:
- HYPE's thin Coinalyze history endpoints (the cold 1.873 s)
- geo-blocked strategy engine (`crypto_setups.py` → fapi)
- cycle engine double count
- Robinhood: revisit only if a keyless feed is published

## Robinhood
US perps announced for "the coming months", not live, no keyless feed. Charter forbids
holding the principal's trading key.

## Branch
| Branch | State | Ready for BUILD? |
|---|---|---|
| `claude/stater-r692-cache` | `/crypto/market` response cache 4 s → 8 s. | **Yes. Merge this.** |
| `claude/stater-r684-matrix` | Pushed `0e3dca4`. Not yet on `origin/main`. | BUILD already accepted (R-IV.688(d)). |
| `claude/stater-perps` | Merged (`30adbd3`). | Done. |

## What the next CC-STATER session should do first
HYPE's two Coinalyze history calls on the cold `/market` path, if SPINE wants that
1.873 s down. Do not skip HYPE Binance spot unless a later Railway read shows it
dead (400 listing or 451 block).
