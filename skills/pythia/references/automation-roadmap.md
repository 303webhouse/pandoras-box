# PYTHIA — Automation Roadmap

Status as of 2026-05-24: Phase 0 — manual input from Nick required.
Phases 1–4 below are the path to automation; none are built yet.

Referenced from `skills/pythia/SKILL.md § Data Sources`.

## Automation Roadmap: Getting PYTHIA Live MP Data

**Status as of 2026-05-19:** Phase 0 — manual input from Nick required. Phases 1–4 below are the path to automation; none are built yet. The hub MCP (v1 shipped 2026-05-15) does not currently expose MP data; that's a v2 candidate for `hub_get_market_profile` once a TradingView webhook → Railway pipeline is built. Nick has TradingView Premium+ (400 alerts, webhook-capable), which is the substrate for Phase 1.

### Phase 1: Key Level Alerts (TradingView → Webhook)

Pine Script indicators that fire webhook alerts when structurally significant MP events occur.

**Daily Value Area Levels Broadcast** — at session open (or shortly after IB forms), compute prior day's VAH, VAL, POC from TPO or volume profile. Send via webhook to Pandora's Box as a "level sheet" injected into committee context. Update developing POC/VA periodically (every 30 min or on significant change). This alone transforms PYTHIA from "ask Nick" to "I can see the levels."

**IB Range Alert** — after first 60 minutes, compute IB width and compare to N-day average. Fire "Narrow IB" (< 75% of average → breakout likely) or "Wide IB" (> 125% → range likely set). Gives PYTHIA early day-type classification.

**Value Area Migration Tracker** — compare today's developing VA to prior session's VA. Fire on Higher value / Lower value / Overlapping value / Non-overlapping value (gap = strong directional move). This is the trending vs bracketing signal PYTHIA needs most.

**80% Rule Alert** — detect price opening outside prior VA then re-entering. Fire with direction: "80% rule triggered — expect travel to opposite VA edge." Highest-probability MP setup; automating removes discretion.

**Poor High / Poor Low Detection** — at session close, evaluate whether the session high/low has excess (tail of 2+ TPOs) or is flat/blunt. Fire "Poor high at $XXX — likely to be revisited." These become next-session targets.

### Phase 2: Profile Shape Classification

**Day Type Classifier** — analyze profile shape at session close (or mid-session for developing classification). Classify as Normal (bell curve), Trend (elongated/single prints), Double Distribution, P-shape, b-shape, Normal Variation. Feeds M.05 (day type determines strategy) and signals to the committee whether to use trend-following or mean-reversion frameworks.

**Single Print Detection** — identify single-print sections in the developing profile. Support/resistance levels + unfinished-business targets. Fire alert when price approaches a single-print zone from a prior session.

### Phase 3: Composite Profile Dashboard

**Multi-Session Composite** — build composite profile over last 5/10/20 sessions. Compute composite POC, composite VA, identify developing balance areas vs migration. Pipe into committee context as a "macro structure" block — the swing-trade structural context PYTHIA needs for multi-day positions.

### Phase 4: Volume Delta Integration

**CVD at Key MP Levels** — when price reaches POC, VAH, or VAL, check whether volume delta confirms or diverges. Rally into VAH with declining delta = fade. Rally into VAH with accelerating delta = breakout. Connects M.06 (delta divergence) directly to structural levels.

### Training Value for Nick

Building these indicators isn't just feeding PYTHIA data — it's a structured way to learn Market Profile through implementation:
- Building the IB alert teaches what Initial Balance means and why width matters.
- Building the VA migration tracker teaches how to read trending vs bracketing.
- Building the 80% rule alert teaches one of MP's highest-probability setups via hands-on construction.
- Building the day type classifier forces deep understanding of profile shapes and their strategic implications.
- Each phase can ship as a standalone Pine Script indicator, tested visually on charts, then connected via webhook once validated.
