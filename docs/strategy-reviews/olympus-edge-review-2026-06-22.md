# Olympus Committee Review — Edge Definition & Scoring Revisions

_Double-pass review of `olympus-personal-trade-breakdown-2026-06-18.md`. Run 2026-06-22. Live hub regime context (bias / sector / flow / balances) pulled at run-time via Pandora MCP. This is meta-analysis of 231 closed trades — not price-anchored._

## Context & regime snapshot (run-time)
- **Source:** 231 closed trades, net +$3,731, 55% WR, PF 1.72. RH options book +18.1% on capital; Fidelity leveraged-ETF book +0.7%.
- **Bias composite:** NEUTRAL (+0.01) headline — but internals split clean. Reflation/trend factors bullish (copper-gold +0.7, sector_rotation +0.6, price >50/200dma); froth factors bearish (excess_cape −0.8, tick_breadth −0.75, credit_spreads −0.50). GEX regime MOMENTUM.
- **Sector (20d RS, narrow leadership, breadth 0.09):** Tech / Industrials / Financials lead; **Energy now the WORST sector (−9%)** — rotated away from a historically top-2 book. _Data flag: the 10-day RS column reads all zeros = dead feed in `backend/scanners/sector_rs.py` (yfinance-based). Only 20d is trustworthy._
- **Flow:** net NEUTRAL globally; megacap tech (NVDA/AMZN/GOOGL/MSFT) heavy bullish call premium. Open NVDA-bear & META-bear spreads are COUNTER to live flow (STRONG on NVDA); HYG-bear CONFIRMING.

## Pass 1 — independent reads
- **TORO:** long edge = real-asset complex (Energy / Materials / Gold-Silver, PF 3.0–4.2), expressed as single-leg convexity, 0–3d holds. Not megacaps.
- **URSA:** the bleed is surgical — long crowded growth dies (Software/AI-BULL PF 0.32, Crypto-BULL 0.48, Financials-BULL 0.00); the SHORT side of those same themes wins (Crypto-BEAR 2.85, Semis-BEAR 1.70, SW/AI-BEAR 1.51). Live risk: NVDA/META shorts fighting flow; HYG short clean.
- **PYTHAGORAS:** holding-period barbell. 1–2d PF 2.93 (+17%), 16d+ PF 4.70 (+25%), 6–15d dead (PF 1.08). Momentum-impulse trader, not swing-trend.
- **PYTHIA:** lane half-engaged — no auction tags in the data. The 0-day book (leveraged-ETF scalps) is churn without value-area discipline. Forward fix: tag auction-acceptance at fire-time.
- **DAEDALUS:** P&L is tail-driven. Single-leg PF 8.47 (+1,597% on capital) vs verticals PF 1.46 (+15%). The default vertical structure amputates the fat tail that pays. Leveraged-ETF book = worst capital use; RH engine starved at ~$1.5K BP.
- **THALES:** edge = two canonical theses (reflation/Iran-escalation + AI-bubble-deflation). Bleed = breaking coherence to buy growth. Live caveat: the energy leg has rotated out — re-point the long leg to metals / industrials / gold.

## Pass 2 — cross-examination (refinements)
- Holding period is a **barbell**, not "cut faster": scalp the impulse OR commit to the thesis; the 6–15d middle (half-committed) is the dead zone.
- Single-leg's 47% WR is what convexity looks like — gate it to high-conviction real-asset impulse, not the house default.
- **Triton directional risk:** whales are in megacaps (bullish), but megacap-BULL was Nick's worst cell (PF 1.08). Triton must not become a machine for the documented losing trade — its forward-edge test must compare following-flow-long vs fading-exhausted-flow-short.
- **Thin-n caution:** the long-growth bleed cells are n=4–9. Strong enough to penalize + shadow-track, NOT to hard-block.
