# 🔱 TRITON — BUILD HANDOFF
*Created 2026-06-15 (evening, post-market). Hand this to a fresh chat to continue the build with full context. Standard hub rules/profile apply via memory; this doc is the Triton-specific layer.*

## TL;DR
**Triton** is a unified whale-confirmation options signal — reverse-engineered from a pro trader's heuristic, then discovered to be **~70% already built and dormant** inside the hub. Nick is making it the **primary signal** the hub hunts (alongside rare-event signals like Golden Touch). This session designed the full strategy, verified the existing code, and set a **two-track build plan**. Nothing has been built or deployed yet. **This is the edge — treat the build accordingly: rigorous, shadow-validated, verify-don't-assume.**

## Why this is the edge (the thesis)
A whale (institution) working a large order via an execution algo leaves a **fingerprint**. Triton detects that fingerprint, gates it through **multi-source confluence**, classifies the **hold horizon**, and expresses it as an **options structure** — on a **tight, liquid universe**, **Tue–Thu post-open only**. Confidence comes from three things converging: (1) it's the confluence of everything already built, (2) it's a genuine options-trading edge, and (3) external validation from the pro traders Nick sourced it from — *"it works when you dial in the right noise filters."* The noise filters are the whole game.

## What already exists (the discovery — all verified this session)
- **`whale_hunter_v2.pine`** (DORMANT) — `C:\trading-hub\docs\pinescript\archived\whale_hunter_v2.pine`. Detects algorithmic-execution fingerprints: N consecutive bars (default 3) matched on total volume (≤8%) **and** POC price (≤0.2%), RVOL≥1.5, + directional lean, structural confirm (50-bar swing extreme), ATR framework (0.85 stop, 1.5R/2.5R), lunch filter, DXY hook (off, only colors bg). Fires `signal:WHALE` → `/whale`. This is **Mode A (absorption)**.
- **Trojan Horse** (LIVE, webhook `FOOTPRINT`) — `request.footprint()` stacked bid/ask-imbalance detector. This is **Mode B (aggression)**. Dropped "absorption" by design (whale_hunter_v2 restores it). ⚠️ Has a documented **pre-auth router bypass** vuln (AEGIS backlog).
- **Holy Grail** (LIVE, hub-reimplemented) — Linda Raschke ADX≥25 + 20-EMA pullback = trend regime. Becomes Triton's **Mode B regime filter**.
- **The hub scoring path** — webhook → `process_signal_unified()` in `backend/signals/pipeline.py` → enrichment → `score_v2.py` (base score, **factor-based, no per-strategy hardcode** — "Holy Grail 60" is computed) → `feed_tier_classifier_v2.py` → feed routing → `trade_ideas_scorer.py` (display_score, CONVICTION/CONFIRMED/STANDALONE).
- **The confluence brain** — `backend/scoring/feed_tier_classifier_v2.py`, function `_confluence_badge(pythia, flow, sector)` (~lines 196–212): all three → `fully_confirmed`; any one → `confirmed`. `_flow_aligned` reads `triggering_factors.flow.net_call/put_premium` (~124–133). `Whale_Hunter` + `Footprint` already in `WATCHLIST_APPROVED_STRATEGIES` (~90–94). Behind `FEED_TIER_USE_V2` flag (shadow). `TOP_FEED_FLOOR=82`, documented >20/week circuit breaker.
- **Enrichment** — `flow_enrichment.py` (⚠️ **yfinance**, per-ticker, pc_ratio/net_premium — NOT UW), `darkpool_enrichment.py` (✅ **UW**, 4h prints, directional — but **SHADOW ONLY, `confluence_bonus=0`**, writes to `metadata`, never scores), `price_enrichment.py`.
- **`/whale` handler** — `backend/webhooks/whale.py`: `signal:WHALE` → posts **🐋 Discord embed** → caches `whale:recent:{TICKER}` (Redis, 30min) → `process_signal_unified` as `Whale_Hunter`/`DARK_POOL`. Runs **OBSERVE-only**; `WEBHOOK_WHALE_ENFORCE=1` flips to fail-closed. **The Discord + hub-print plumbing already exists.**
- **Pythia** (`docs/pythia-market-profile-v2.4.pine`) — **zero `request.*` calls**, pure chart-native, `alert()` + JSON. This is why it runs in the **Pine Screener** across 222 tickers from ONE alert.

## Key technical findings + the ONE open question
- **Pythia covers 222 from one alert via the Pine Screener** — because it's request-free single-symbol logic. ✅ Verified.
- **whale_hunter_v2 is NOT request-free:** `request.security_lower_tf(syminfo.tickerid, ltfSource)` for the POC (line 51; `ltfSource = input.timeframe("1")` — **1-min default, tunable**, line 16) + 2× `request.security` for DXY (lines 134–135).
- **⚠️ OPEN QUESTION (forks the v0 path):** *Does the Pine Screener support `request.security_lower_tf`?* The script is explicitly **"watchlist-safe"** and references *"TV watchlist evaluation mode"* (lines 314–315) — so the author likely built/tested it for the screener, meaning it may run there as-is. **TEST: drop whale_hunter_v2 into the Pine Screener on a 5-name watchlist → does it compile + fire? 2 minutes, settles everything.**
- **1-min bars are a COARSE proxy**, not the true whale signature. The real fingerprint lives in order flow: **dark-pool prints > footprint (bid/ask volume) > trade tape > 1-min volume-at-price POC**. 1-min OHLCV discards the intra-minute slicing rhythm AND the bid/ask dimension. This is why the precise version belongs **hub-side** (UW data), and validates unifying v2 on the footprint engine.
- **The real fork: breadth vs. fidelity.** Broad-on-TV = coarse 1-min proxy. Precise fingerprint = hub-side with UW dark-pool/footprint data. Hub-side solves the screener limit AND the data-quality question at once.

## The two-track build plan
**v0 — SCAFFOLDING (fast, coarse, this week):**
- `whale_hunter_v2` live. Universe: Tier-1 ~16 via per-symbol alerts, OR the full list via Pine Screener **if the test passes**.
- DXY → its own request-free single alert → hub (DXY already in bias composite as `dxy_trend`; remove the 2 requests from the Pine).
- Add timing gate (Tue–Thu + ≥15min post-open, `America/New_York`) to the Pine.
- Flip `WEBHOOK_WHALE_ENFORCE=1` (closes OBSERVE gap).
- **Purpose:** exercise Discord/hub plumbing + a *rough* thesis read. It's a proxy — **do NOT sink time tuning its knobs.**

**v1 — THE REAL BUILD (hub-side, the actual edge):**
- Detection moves **hub-side**, computed from **UW dark-pool + flow + footprint-grade data** (not TV 1-min). No screener/slot limits, full universe.
- Wire the confluence stack into scoring: promote dark-pool from shadow (add `_dp_confirms`, flip `confluence_bonus`), add **Market Tide** (new UW fetch + `_tide_aligned`), extend `_confluence_badge` to the whale triad (`flow AND dp AND tide → fully_confirmed`). Optional: upgrade flow_enrichment yfinance → UW.
- Add the **Tempo tag** (SCALP 0–2DTE / SWING 3–10 / POSITION 2–6wk) from mode + ADX + days-to-target (= target distance ÷ daily ATR), **regime-adjusted by GEX** (demote SCALP in FADE regime).
- **Fail-safe (URSA P0):** Triton degrades to detection-only with capped conviction when UW feeds go dark (flow radar was empty/dark this session — feed reliability is real).
- "Hub swallows everything and synthesizes" = this is literally the architecture.

## The universe
**Screen:** liquid chains (tight spreads = executability) + big/institutional (real whale prints) + moves (range pays convexity). Triton's edge is strongest on **single-stock equities + equity-index/sector ETFs**; commodities/international/crypto-ETF are weaker-flow **satellites** (size lighter). **VIX products excluded** (decay + footprint doesn't apply). **No leveraged ETFs** (decay).
- **Tier-1 core (~16, validation set):** SPY, QQQ, IWM, NVDA, TSLA, AAPL, MSFT, AMZN, META, AMD, AVGO, SMH, MU, PLTR, MSTR, COIN.
- **Full universe (~80):** + DRAM *(verified: ~40M avg vol, $26→$71/52wk — real & liquid)*, SOXX, ARM, MRVL, SMCI, QCOM, TSM, ASML, AMAT, LRCX, IGV, CRM, ORCL, NOW, SNOW, PANW, CRWD, NET, DDOG, SHOP, XLF, KRE, JPM, GS, BAC, MS, SCHW, V, MA, AXP, PYPL, SOFI, HOOD, IBIT, ETHA, MARA, RIOT, XLE, XOP, USO, UNG, GLD, SLV, GDX, FCX, CCJ, URA, FXI, KWEB, EEM, EWZ, EWJ, EFA, INDA, DKNG, AFRM, RBLX, CVNA, ABNB, UBER, RDDT, LLY, BA, DIS.
- **Mechanism:** `TRITON_UNIVERSE` config (no whitelist exists today — additive). Static list v0; dynamic monthly screen later (rank by `bid_ask_spread_pct` + volume + realized vol).

## Alert/swap decisions
- **Drop Artemis, keep Pythia.** Artemis (VWAP±2σ fade) is the low-conviction signal Nick ignores; Triton Mode A is the confluence-gated version. **Pythia stays — it FEEDS Triton's structure gate** (POC/VAH/VAL/IB). **Harvest Artemis's VWAP±2σ band into Triton's structure gate** as another level type. Archive Artemis (free the alert, keep the script).

## Immediate next actions (fresh chat starts here)
1. **▶ Run the 2-min Pine Screener test** on whale_hunter_v2 — does `request.security_lower_tf` run in the screener? Forks v0 (broad-coarse vs narrow-precise).
2. **Confirm TV alert slot count** (Nick's plan tier) — sizes v0 if screener test fails.
3. **Titans review** of this plan (ATLAS: hub-side detection + scoring + Market Tide fetch/caching; AEGIS: enforce flip + footprint pre-auth bypass; HELIOS: tempo/mode badge surfacing; ATHENA: v0/v1 sequencing + floor re-tune + scope-vs-bucket).
4. **Backtest data inventory** (investigation-first): what historical data does the hub store + which UW historical endpoints exist (dark pool is queryable)? Honest constraint: full footprint/flow backtest is hard ("camera not rolling") — **forward record is the primary validation**; live deployment starts the clock.
5. **Write the formal v0 + v1 codex briefs** once the screener test + Titans pass are done.

## Discipline reminders (hold these on the build)
- **Deploy only outside market hours** (7:30 AM–2:00 PM MT) — Railway drops the hub 60–170s.
- **Greenlight before any commit/deploy.** Shadow-by-default. Investigation-first / Phase-0 read before code or schema changes.
- **Verify, don't assume.** This session was the case study: TV alert mechanics were called wrong *twice* until the actual scripts were read. Read the code; test the claim.
- **Security:** flip `WEBHOOK_WHALE_ENFORCE=1`; the FOOTPRINT pre-auth bypass matters if Trojan Horse/footprint enters v2; mind the prior PYTHIA secret-exposure incident on any webhook-secret handling.
- **Anything touching PYTHIA/PIVOT/DAEDALUS or the Insights feed** → post-build full Olympus committee pass on a known-good ticker.

## Session regime snapshot (context, will be stale)
TORO_MINOR (+0.23), **GEX = FADE** (pinning tape — favors Mode A reversals over Mode B breakouts). Flow radar empty (after-hours). Re-pull live (`hub_get_bias_composite`, `hub_get_flow_radar`, `hub_get_portfolio_balances`) at the start of the next working session.
