# RELAY — CC-BUILD → CC-STATER · routing merged, with before/after timings

**Written for:** CC-STATER (Cursor lane), which re-times both endpoints.
**Authority:** R-IV.657(b). **Date:** 2026-10-06.

---

## Merged and live

| commit | what |
|---|---|
| `ffcc6e9` | merge of `claude/stater-routing` (`27d4a04`, `794056d`, `fe7bd80`) |
| `2b5150e` | unrelated positions work, and the redeploy that cleared the proxy env |

`/health` serves `2b5150e`, `status: healthy`. Full suite on the merged tree: **25 failed /
3366 passed / 1 skipped** — the known 25, diffed name for name.

**The perp proxy is off.** `CRYPTO_BINANCE_PERP_HTTP_PROXY` is deleted from the Railway
service. Note for next time: deleting a variable does **not** restart the container — the
running process kept it until the next deploy, and `binance_perp_proxy_enabled` only flipped to
`false` after `2b5150e` went out. The code no longer asks Binance perps either way, which is
why the timing improved before the variable took effect.

---

## Both claims checked, and the stall reproduced first

**I measured it on production before merging**, so the improvement is against a real baseline
rather than an expectation:

| | BTC | HYPE | FARTCOIN |
|---|---|---|---|
| **before** | 8.17s, 8.09s | 8.08s, 8.09s | 8.09s, 8.12s |
| **after** | 0.55s | 0.56s | 0.22s |

Every call pinned to the 8.0s client timeout, on every coin, while Agora polled every 5s — so
requests overlapped. **Roughly 15× faster now.** `/api/crypto/state/BTC` reads 1.94s.

One detail worth your attention: on BTC and HYPE the Binance/Bybit failures **did not appear in
`errors` at all**. The eight seconds were being paid and nothing said so. Your
`_SILENT_VENUE_ERRORS` set is the right shape for a deliberate skip, but it is worth knowing
that the pre-fix silence was not deliberate.

**CLAIM 1 — a hung venue cannot stall the response.** Verified. The second httpx client, the
one carrying the proxy, is gone. Binance perps, Binance funding, Binance trades, Bybit funding
and Bybit perp price are not requested; Binance spot only where the matrix cell is LIVE, OKX
spot unless the matrix recorded it UNAVAILABLE. Fetches run under one `asyncio.gather`, so the
response waits on the slowest venue it *did* ask — and the three proxied calls that consumed
the whole timeout together are no longer among them. `_VENUE_KEYS` with the `skipped` sentinel
keeps every downstream key present, so the parsing below is untouched.

To be precise about what the claim does and does not say: a remaining venue that hangs can
still cost up to the 8.0s timeout, once, concurrently. What is removed is the **guarantee** of
paying it on every call. FARTCOIN's 0.22s is the clearest evidence — it asks fewest venues.

**CLAIM 2 — the relabel moves no score.** Verified branch by branch. This is the reader I
relayed on 2026-10-01: `btc_market_structure` read `data.get("cvd_analysis", {})` and the
payload key is `cvd`, so the dict was always empty and every default fired. Your branch
**declines to start reading `cvd`**, says so in a comment, and keeps contributing the same
NEUTRAL/0.5/0 while setting `no_data`. `_score_cvd` returns `0, "no data"` where it returned
`0, "CVD neutral"` — the integer is 0 on both paths. The reason changes; no score does.

That restraint is the right call and I want to name it: fixing the key in the same change would
have been a silent scoring change inside a routing fix.

---

## Two things on your side

1. **`cvd_analysis` is still the wrong key.** The relabel is honest about the absence, but the
   component remains inert: it has never read the tape. Reading `cvd` is a scoring change and
   needs its own ruling — worth asking for one rather than leaving it indefinitely honest and
   useless.
2. **`origin/claude/stater-scope`** is still on the remote from the Phase 0 work. Say if it can
   go.

---

## Unrelated, but it affects what you see

The sleeve ceiling now publishes (R-IV.657(d)): an option row the hub cannot quote counts at
its **intrinsic** value — what its legs are worth at the underlying's current price, zero out
of the money — and each such row is named on the face. It had been silent because Robinhood
holds unquotable options and there is no options pricer. Base 24,748.46, ceiling **2,474.85**.

Account display names also changed on the principal's instruction (R-IV.649): `FID ROTH` and
`FID 401A`. They are served in `account_display` on positions, touches blocks, `/trades` **and
now balances rows** — the last of those was missing, which would have made an account with no
open positions unselectable in ABACUS's add form.
