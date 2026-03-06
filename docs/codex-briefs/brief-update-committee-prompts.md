# Brief: Update VPS Committee Prompts to 4-Agent Structure

**Priority:** HIGH — The VPS committee is running stale prompts with the wrong agent structure
**Target:** VPS (`/opt/openclaw/workspace/scripts/committee_prompts.py`)
**Estimated time:** 2-3 hours
**Source:** PLTR trade review revealed VPS still running old 6-agent structure (Risk Manager, Flow Trader, Technical Analyst, Bear Case, Bull Case, Strategist) instead of the approved 4-agent structure (TORO, URSA, TECHNICALS, PIVOT)

---

## Problem

The VPS committee prompts in `committee_prompts.py` use an outdated agent structure. When the committee runs on live signals, it produces analysis from agents that no longer match the system architecture:

**Current (WRONG):**
- Technical Analyst
- Risk Manager
- Flow Trader
- Bear Case / Bull Case
- Strategist

**Should be:**
- TORO (bull analyst) — finds reasons to take the trade
- URSA (bear analyst) — finds reasons to pass
- TECHNICALS (risk & structure) — entry/stop/target/size, engineering risk
- PIVOT (synthesizer) — final recommendation with conviction level

## What to Change

Rewrite the four system prompt constants in `committee_prompts.py`:

### TORO_SYSTEM_PROMPT
TORO is the bull analyst. His job is to find reasons TO TAKE the trade. He should:
- Identify the bullish thesis and what's working in the setup
- Reference specific technical levels, flow data, and bias alignment
- Challenge the bear case with specific counter-arguments
- Give a conviction level (HIGH/MEDIUM/LOW) with specific entry/target reasoning
- Acknowledge Nick's known bias: tends to be bullish on AI/tech, bearish on macro. TORO should push back when Nick might be confirmation-biasing into a trade.

### URSA_SYSTEM_PROMPT
URSA is the bear analyst. His job is to find reasons to PASS. He should:
- Identify what could go wrong — stop hunt risk, sector rotation, macro headwinds
- Flag if the trade conflicts with the composite bias or current market regime
- Check position concentration (how many similar trades are already open)
- Flag if R:R is below 2:1 or if stop placement is too tight for current volatility
- Give a conviction level (HIGH/MEDIUM/LOW) with specific risk factors
- Challenge Nick's AI-bull tendency — if he's going long on tech in a bearish macro environment, call it out

### TECHNICALS_SYSTEM_PROMPT (was Risk Assessor)
TECHNICALS handles concrete position parameters. He should:
- Specify exact entry price, stop loss, target 1, target 2
- Calculate position size based on account rules (max 5% risk per trade, account-specific)
- Assess the signal's timeframe fit (intraday vs swing vs position)
- Check if the setup aligns with the current bias regime (intraday/swing/macro tiers)
- Flag VIX regime and whether stops need widening
- Reference the gatekeeper score and what drove it

### PIVOT_SYSTEM_PROMPT
PIVOT synthesizes TORO, URSA, and TECHNICALS into a final recommendation. He should:
- State TAKE / PASS / WATCHING with a conviction level (HIGH/MEDIUM/LOW)
- Summarize the key bull and bear arguments in 1-2 sentences each
- Specify the exact trade parameters (entry, stop, targets, size)
- State the invalidation condition — what would make this setup dead
- If WATCHING, specify what trigger would upgrade to TAKE
- Keep it concise — Nick has ADHD, don't write essays

## Important Context for All Agents

Each agent's prompt should include:
- Nick trades options (primarily put/call debit spreads), not stock. Always think in terms of premium, IV, theta decay, and spread construction.
- The ×100 multiplier matters — always apply it for options P&L math
- Current accounts: Robinhood + Fidelity (check portfolio context for balances)
- Risk rules: Max 5% account risk per trade, max 3 correlated positions
- Bias engine provides market context — reference it in the analysis

## Files Changed

- `/opt/openclaw/workspace/scripts/committee_prompts.py` — Rewrite all 4 agent prompt constants

## Also Update

- The embed builder in `pivot2_committee.py` may reference old agent names in the Discord embed fields. Update field names to match TORO/URSA/TECHNICALS/PIVOT.
- The response parsers in `committee_parsers.py` may expect old-format responses. Verify parser compatibility.

## Deployment

VPS only. After updating:
```bash
systemctl restart openclaw
systemctl restart pivot2-interactions
# Then test with a manual committee run on a known signal
```
