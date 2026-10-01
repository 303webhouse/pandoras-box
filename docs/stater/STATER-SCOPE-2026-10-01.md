# Stater Swap — scope (CC-STATER, R-IV.618)

**Written:** 2026-10-01 by CC-STATER (Claude Code cloud session), against `origin/main` `b0ada46`.
**Status:** proposal. Phase 0 (fixes) is authorized by SPINE R-IV.619 and runs on `claude/stater-phase0`.
Phase 1 waits for the principal's approval of the mockup. Phases 2 and 3 each need their own written ruling.
**Mockup (sample data only):** `docs/stater/mockups/stater-phase1-sample.html`, also published as a
private artifact for the principal.

---

## 1. What Stater Swap is today

Stater Swap is the hub's crypto page (`/app/stater`, files `frontend/stater.html|js|css`) plus a
crypto backend that runs around the clock. It is **read-only**: there is no order code, no exchange
credential and no wallet key anywhere in the repo.

### What works
- **The page.** Six coin cards (BTC, ETH, SOL, HYPE, ZEC, FARTCOIN, in tiers 1/2/3). Each card
  shows its regime, its tape state and six data-health dots. The page also has a BTC derivatives
  band (funding, open interest, basis, liquidations), a spot-vs-perp "tape health" band, a
  capitulation-to-froth "Cycle Extremes" dial, and a detail drawer per coin. It polls every 30 s
  and pauses when the tab is hidden.
- **Background jobs**, all 24/7:
  - regime, hourly (`jobs/crypto_regime.py`);
  - cycle extremes, hourly (`bias_filters/crypto_cycle_engine.py`);
  - tape health, every 15 minutes (`bias_filters/crypto_tape_health_engine.py`);
  - the BTC bottom-signal checklist, every 5 minutes (`bias_filters/btc_bottom_signals.py`).
- **Free data sources already in use:**
  - OKX public;
  - Binance spot mirror (`data-api.binance.vision`);
  - Coinbase public spot price;
  - Deribit public;
  - DeFiLlama;
  - Coinalyze, free tier.
- **Hub tools:** `hub_get_crypto_quote`, `hub_get_crypto_state` and `hub_get_crypto_market_profile`.
- **Tests:** about 220 crypto tests in 18 files.

### What is stubbed (honest placeholders)
- The DAILY and DIST-TO-FLOOR chips, the floor rings and the drawer's distance-to-floor row always
  read N/A. This was ruled honest placeholders in S-6.
- Signal #10 (ETF-flow exhaustion) and the whole S-5 phase (dominance, the ETH/BTC strip, the macro
  band extension) were never built.
- Gating is shadow-only everywhere (`gating_enabled=false`).
- The volume profile uses a placeholder volume of 1.0 per bar, so it is really a time-at-price count.

### What is broken (ranked by harm)
1. **An open page spends paid calls and writes data.**
   - Each 30 s refresh calls `/api/crypto/state/BTC` and `/api/crypto/tape-health`. Both pull bars
     through Unusual Whales (`jobs/crypto_bars.py`, tagged `outcome_resolver`). The code-path
     estimate is about 11k UW calls a day from one open tab; Phase 0 measures the real figure from
     the governor's own counts.
   - GETs on `/cycle-extremes` and `/tape-health` recompute and **insert log rows**, roughly 17k a
     day from one tab. Tape-health can also emit CVD signals.
2. **The signal feed is always empty.** `/api/trade-ideas` drops crypto on the server
   (R-IV.566(e)2), and the page then keeps only crypto rows.
3. **Prices and order-flow leak between coins.** `/api/crypto/market` keeps one response cache and
   one set of last-good fallbacks for every symbol. The page also asks for bare `BTC` rather than
   `BTCUSDT`. Agora and the Discord bot read the same cache.
4. **Readings that look healthy when they are not:**
   - A missing tape reading shows "CVD ALIGNED 0 / 0" with a green dot.
   - The dial ignores its own `degraded` flag.
   - The session field is always null, because it reads keys `crypto_sessions` never returns.
   - The tape reads "stale" about a third of the time, because a 600 s limit is applied to a 900 s job.
5. **The strategy engine is dead.**
   - `strategies/crypto_setups.py` reads `fapi.binance.com`, which returns HTTP 451 (geo-blocked)
     from Railway. It has written 3 signals ever, all on 2026-07-22.
   - The CVD leg of `btc_market_structure.py` calls `localhost:8000` with the wrong response keys,
     so it always scores 0.
6. **The cycle engine counts top signals as capitulation.** Vendor "FIRING" flags fire at both
   extremes, so a funding blow-off can count as capitulation and froth at once.
7. **Smaller issues:**
   - `/api/btc/bottom-signals/reset` cannot be reached, because it is declared after `/{signal_id}`.
   - "Quarterly basis" is really perp-vs-spot annualised over an arbitrary 7 days.
   - On phones the page has no way back to Agora.
   - The stylesheet pin lags Agora's.

---

## 2. The principal's framing, mapped to what exists

| Framing | What exists now | Gap |
|---|---|---|
| An autonomous crypto trading project, not yet formally scoped | Read-only cockpit and a dead strategy engine | Everything between "see" and "act" |
| BTC bottom timing (@TheFlowHorse): a capitulation flush where bid-ask spreads blow out, then a "death of vol" phase of collapsed volatility and quiet base-building | The capitulation side of the Cycle dial; the BTC bottom checklist; spread and depth inside the bottom-signal payload only | No flush detector, no volatility-compression measure, no stage model, and spreads are not shown |
| LBR 3/10 oscillator, crypto only | An equity version (`indicators/three_ten_oscillator.py`, (H+L)/2 based) and a crypto Pine script (`docs/pinescript/lbr_3_10_oscillator.pine`, close-based, 16-period slow line) that disagree | No crypto computation in the hub |
| A small Coinbase sandbox | Nothing | Phases 2 and 3 |

---

## 3. What Stater Swap should become

### Phase 0 — make the page safe and honest (authorized, R-IV.619)
Fixes only, in owned files, on `claude/stater-phase0`:
1. GETs stop spending UW calls and stop writing rows. They read the latest stored rows, and the
   jobs keep doing the writing. The drain is measured before and after from
   `GET /api/uw/health/by_caller`.
2. BTC/ETH/SOL bars move off UW to Coinbase Exchange public candles, with OKX public as the fallback.
3. `/api/crypto/market` caches and falls back per symbol, and the page sends the full pair. The
   response shape Agora and the bot read stays the same.
4. Honest readings: N/A rather than 0, the dial respects `degraded`, the session key is fixed, and
   the stale limit matches the job's real cadence.
5. A crypto-only signal feed served from `crypto_market.py`.
6. The reset route's order.

After those come the geo-blocked strategy engine and the cycle double count, each as its own item.

### Phase 1 — bottom-timing cockpit (read-only; the mockup)
A stage track for BTC, using the FlowHorse sequence. Each stage lists its evidence; every item is
met (✓), not yet (○) or no data (N/A, never faked).
- **FLUSH:**
  - spread blowout (more than 5× the 30-day median);
  - a liquidation spike;
  - deeply negative funding;
  - a one-day drop of more than 2.5× ATR;
  - a spot ETF outflow spike (N/A: no free source yet).
- **DEATH OF VOL:**
  - 7-day realised volatility in the bottom 10% of its year;
  - implied volatility (Deribit DVOL) low;
  - a tight 20-day range;
  - funding near zero;
  - spreads back to normal;
  - open interest flat.
- **BASE:**
  - a higher low above the flush low;
  - the 3/10 fast line crossing up through the slow line below zero;
  - a close above the 20-day high.
- **TREND:**
  - above the 50-day average;
  - the 3/10 fast line above zero.

Under the track:
- a BTC daily chart with the flush and the quiet range marked;
- the LBR 3/10 panel, computed close-based per the repo's crypto Pine script;
- a spread and liquidity card;
- a volatility card;
- a positioning card (existing data).

The existing coin grid, tape band and dial stay.

**Needs:**
- Two new read-only jobs: daily candles and a book-spread sampler.
- A stage evaluator (pure functions, tested on recorded data).
- One new GET.
- Page work in `stater.*`.

The stage thresholds are proposals for SPINE and the committee to rule on before they are wired.

### Phase 2 — paper sandbox (needs its own ruling)
- Rules from Phase 1 open **paper** trades, sized to the sandbox the principal set aside.
- The journal records real fees and spread.
- At Coinbase Advanced's entry tier (under $1K of 30-day volume: 0.60% maker, 1.20% taker), a
  taker round trip costs about 2.4% before spread. A small account has to clear that on every trade,
  which is the main thing Phase 2 would measure.
- CC-QUERY measures the results before anything else is proposed.
- No keys and no exchange connection.

### Phase 3 — autonomous live sandbox (out of charter until a written ruling)
SPINE's floor, not the whole list:
- keys held outside the repo and the hub;
- a hard cap equal to the sandbox;
- a kill switch;
- a daily-loss stop;
- an AEGIS review.

This lane will not hold keys.

---

## 4. Data sources (all free; each named)

| Source | Host | Key | Used for |
|---|---|---|---|
| Coinbase Exchange public | `api.exchange.coinbase.com` | none | Candles (Phase 0 bars, Phase 1 chart), level-2 book (spread, depth) |
| OKX public | `www.okx.com/api/v5` | none | Fallback candles and books; trades for tape health (existing) |
| Deribit public | `www.deribit.com/api/v2` | none | DVOL implied-volatility index, 25-delta skew (existing) |
| Binance spot mirror | `data-api.binance.vision` | none | Existing spot reads |
| DeFiLlama | `yields.llama.fi` | none | Existing stablecoin yields |
| Coinalyze | `api.coinalyze.net` | free-tier key already in Railway | Funding, open interest, liquidations (existing) |

**No new Unusual Whales calls.** Phase 0 removes the crypto UW calls that exist today.

---

## 5. Decisions only the principal can make
1. Approve, change or reject the Phase 1 mockup's layout.
2. Whether the stage thresholds should be ruled by the committee first, or tuned on recorded
   history after Phase 1 ships.
3. When Phase 2 (paper) should be considered: after Phase 1 has run for a set period, or never.
