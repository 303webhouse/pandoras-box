# Brief 03B: Committee Prompts + LLM Integration

## Context for Sub-Agent

You are wiring **real AI agents** into the committee pipeline built by Brief 03A. The gatekeeper, context builder, Discord output, and logging already work with stub responses. Your job is to replace those stubs with four LLM calls that produce genuine trade analysis.

**Prerequisite:** Brief 03A must be fully functional — signals filtered, context assembled, stubs posting to Discord. This brief ONLY replaces the `run_committee()` function internals.

## What You're Building

Four sequential LLM calls per committee run:

```
Signal + Context
       │
       ▼
  ┌─────────┐     ┌─────────┐     ┌──────────────┐
  │  TORO    │     │  URSA   │     │    RISK      │
  │ Analyst  │     │ Analyst │     │  Assessor    │
  │ (bull    │     │ (bear   │     │ (sizing,     │
  │  case)   │     │  case)  │     │  stops, IV,  │
  └────┬─────┘     └────┬────┘     │  theta, liq) │
       │                │          └──────┬───────┘
       │                │                 │
       ▼                ▼                 ▼
  ┌──────────────────────────────────────────┐
  │  PIVOT / MARK BAUM                       │
  │  Reads all three, synthesizes,           │
  │  makes final call with personality       │
  └──────────────────────────────────────────┘
```

**Sequential, not parallel.** Pivot needs all three analyst outputs to synthesize. TORO and URSA could theoretically run in parallel, but sequential is simpler and the total cost is ~$0.05/run — not worth the complexity.

## LLM Configuration

| Setting | Value |
|---------|-------|
| Provider | OpenRouter (already configured for Pivot) |
| Model | `anthropic/claude-sonnet-4-20250514` |
| Max tokens per agent | 500 (TORO/URSA), 800 (Risk), 1000 (Pivot) |
| Temperature | 0.3 (TORO/URSA/Risk), 0.6 (Pivot — more personality) |
| Timeout | 30 seconds per call |
| Retry | 1 retry on timeout/5xx, then fallback to stub |

### Cost Model

Per committee run: ~$0.05 (4 Sonnet calls with context)
- TORO: ~$0.01 (short prompt, short response)
- URSA: ~$0.01
- Risk: ~$0.015 (more context — positions, catalysts)
- Pivot: ~$0.015 (reads all three + synthesizes)

Daily budget: 3-5 typical runs = $0.15-$0.25. Hard cap at 20 runs = $1.00/day max.

### Fallback Strategy

If any agent call fails after retry:
- TORO/URSA fail → Use stub with `[ANALYSIS UNAVAILABLE]` flag, continue pipeline
- Risk fails → Use stub with conservative defaults ("1 contract, tight stops"), continue
- Pivot fails → Concatenate TORO + URSA + Risk analyses as plain summary, skip personality

Never block the entire pipeline because one agent timed out.

## What's NOT In Scope (03B)

- ❌ Gatekeeper changes (03A is locked)
- ❌ Decision tracking / button handlers (Brief 03C)
- ❌ Pushback mechanics (Brief 03C)
- ❌ Outcome tracking (Brief 04)
- ❌ Prompt tuning based on performance data (future iteration)

---


## Section 1: LLM Call Wrapper

All four agents use the same underlying function to call OpenRouter. This wrapper handles auth, retries, timeouts, and response parsing.

### OpenRouter Call Function

```python
import aiohttp
import json
import os
import logging
from typing import Optional

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")  # already in Pivot's env
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-4-20250514"

async def call_agent(
    system_prompt: str,
    user_message: str,
    max_tokens: int = 500,
    temperature: float = 0.3,
    agent_name: str = "unknown",
    timeout: int = 30,
    retries: int = 1
) -> Optional[str]:
    """
    Call OpenRouter with system prompt and user message.
    
    Returns the assistant's text response, or None on failure.
    
    Args:
        system_prompt: Agent's persona and instructions
        user_message: The assembled context + signal data
        max_tokens: Response length limit
        temperature: Creativity control (0.3 = analytical, 0.6 = personality)
        agent_name: For logging ("TORO", "URSA", "RISK", "PIVOT")
        timeout: Seconds before timeout
        retries: Number of retry attempts on failure
    """
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://pandoras-box.trading",
        "X-Title": "Pandora's Box Committee"
    }
    
    payload = {
        "model": DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ]
    }
    
    for attempt in range(retries + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    OPENROUTER_URL,
                    headers=headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        text = data["choices"][0]["message"]["content"]
                        logging.info(f"[{agent_name}] Response received ({len(text)} chars)")
                        return text
                    else:
                        error = await resp.text()
                        logging.warning(
                            f"[{agent_name}] API error {resp.status}: {error} "
                            f"(attempt {attempt + 1}/{retries + 1})"
                        )
        except asyncio.TimeoutError:
            logging.warning(
                f"[{agent_name}] Timeout after {timeout}s "
                f"(attempt {attempt + 1}/{retries + 1})"
            )
        except Exception as e:
            logging.error(
                f"[{agent_name}] Unexpected error: {e} "
                f"(attempt {attempt + 1}/{retries + 1})"
            )
    
    logging.error(f"[{agent_name}] All attempts failed, returning None")
    return None
```

### Response Parser

Each agent returns plain text that must be parsed into the response contract defined in 03A. Agents are instructed to use a simple structured format.

```python
def parse_analyst_response(raw: str, agent_name: str) -> dict:
    """
    Parse TORO or URSA analyst response into contract dict.
    
    Expected raw format from LLM:
    ANALYSIS: <1-3 sentence analysis>
    CONVICTION: HIGH|MEDIUM|LOW
    
    Fallback: If format isn't matched, use entire response as analysis
    with MEDIUM conviction.
    """
    result = {
        "agent": agent_name,
        "analysis": raw.strip(),  # fallback: entire response
        "conviction": "MEDIUM"     # fallback default
    }
    
    lines = raw.strip().split("\n")
    for line in lines:
        line_clean = line.strip()
        if line_clean.upper().startswith("ANALYSIS:"):
            result["analysis"] = line_clean[9:].strip()
        elif line_clean.upper().startswith("CONVICTION:"):
            conv = line_clean[11:].strip().upper()
            if conv in ("HIGH", "MEDIUM", "LOW"):
                result["conviction"] = conv
    
    return result


def parse_risk_response(raw: str) -> dict:
    """
    Parse Risk Assessor response into contract dict.
    
    Expected raw format:
    ANALYSIS: <risk assessment paragraph>
    ENTRY: <entry price/level>
    STOP: <stop loss>
    TARGET: <profit target>
    SIZE: <position size recommendation>
    
    Fallback: entire response as analysis, N/A for trade params.
    """
    result = {
        "agent": "RISK",
        "analysis": raw.strip(),
        "entry": "N/A",
        "stop": "N/A",
        "target": "N/A",
        "size": "1 contract (conservative default)"
    }
    
    field_map = {
        "ANALYSIS:": "analysis",
        "ENTRY:": "entry",
        "STOP:": "stop",
        "TARGET:": "target",
        "SIZE:": "size"
    }
    
    lines = raw.strip().split("\n")
    for line in lines:
        line_clean = line.strip()
        for prefix, key in field_map.items():
            if line_clean.upper().startswith(prefix):
                result[key] = line_clean[len(prefix):].strip()
                break
    
    return result


def parse_pivot_response(raw: str) -> dict:
    """
    Parse Pivot/Baum synthesizer response into contract dict.
    
    Expected raw format:
    SYNTHESIS: <Mark Baum-voiced synthesis paragraph>
    CONVICTION: HIGH|MEDIUM|LOW
    ACTION: TAKE|PASS|WATCHING
    INVALIDATION: <what kills this trade>
    
    Fallback: entire response as synthesis, MEDIUM conviction, WATCHING action.
    """
    result = {
        "agent": "PIVOT",
        "synthesis": raw.strip(),
        "conviction": "MEDIUM",
        "action": "WATCHING",
        "invalidation": "See full analysis above"
    }
    
    field_map = {
        "SYNTHESIS:": "synthesis",
        "CONVICTION:": "conviction",
        "ACTION:": "action",
        "INVALIDATION:": "invalidation"
    }
    
    lines = raw.strip().split("\n")
    for line in lines:
        line_clean = line.strip()
        for prefix, key in field_map.items():
            if line_clean.upper().startswith(prefix):
                value = line_clean[len(prefix):].strip()
                if key == "conviction":
                    value = value.upper()
                    if value not in ("HIGH", "MEDIUM", "LOW"):
                        value = "MEDIUM"
                elif key == "action":
                    value = value.upper()
                    if value not in ("TAKE", "PASS", "WATCHING"):
                        value = "WATCHING"
                result[key] = value
                break
    
    return result
```

---

## Section 2: Context Formatter

Before calling agents, the raw context dict from 03A's `build_committee_context()` needs to be formatted into readable text for each agent's user message. Each agent gets the same base context but with different emphasis.

### Base Context Formatter

```python
def format_signal_context(signal: dict, context: dict) -> str:
    """
    Formats the signal + market context into a readable text block
    that all agents receive as their user message (with agent-specific
    additions appended by each caller).
    """
    bias = context.get("bias", {})
    catalysts = context.get("catalysts", {})
    positions = context.get("open_positions", [])
    cbs = context.get("circuit_breakers", [])
    
    sections = []
    
    # Signal info
    sections.append(
        f"## SIGNAL\n"
        f"Ticker: {signal['ticker']}\n"
        f"Direction: {signal['direction']}\n"
        f"Alert Type: {signal['alert_type']}\n"
        f"Score: {signal.get('score', 'N/A')}\n"
        f"Strategy: {signal.get('metadata', {}).get('strategy', 'N/A')}\n"
        f"Timeframe: {signal.get('metadata', {}).get('timeframe', 'N/A')}"
    )
    
    # Market regime
    sections.append(
        f"## MARKET REGIME\n"
        f"Bias: {bias.get('regime', 'UNKNOWN')}\n"
        f"Composite Score: {bias.get('composite_score', 'N/A')}\n"
        f"DEFCON: {bias.get('defcon', 'UNKNOWN')}\n"
        f"VIX: {bias.get('vix', 'N/A')}"
    )
    
    # Circuit breaker alerts (if any in last 2 hours)
    if cbs:
        cb_text = "\n".join(
            f"- [{cb['timestamp']}] {cb['trigger']} ({cb['severity']})"
            for cb in cbs
        )
        sections.append(f"## RECENT CIRCUIT BREAKER EVENTS\n{cb_text}")
    
    # Upcoming catalysts
    ticker_events = catalysts.get("ticker_events", [])
    macro_events = catalysts.get("macro_events", [])
    
    if ticker_events or macro_events:
        cat_lines = []
        if ticker_events:
            cat_lines.append("Ticker-specific:")
            for evt in ticker_events:
                cat_lines.append(f"  - {evt['date']}: {evt['event']} ({evt['type']})")
        if macro_events:
            cat_lines.append("Macro events (within DTE window):")
            for evt in macro_events[:10]:  # cap at 10 to save tokens
                cat_lines.append(f"  - {evt['date']}: {evt['event']} ({evt['type']})")
        sections.append(f"## UPCOMING CATALYSTS\n" + "\n".join(cat_lines))
    
    # Whale context (if whale_flow_confirmed)
    if signal.get("alert_type") == "whale_flow_confirmed":
        whale_meta = signal.get("metadata", {})
        sections.append(
            f"## WHALE FLOW CONFIRMATION\n"
            f"Original alert: {whale_meta.get('original_whale_alert', {})}\n"
            f"UW Screenshot analysis: {whale_meta.get('uw_screenshot_description', 'N/A')}\n"
            f"Confirmation delay: {whale_meta.get('confirmation_delay_seconds', 'N/A')}s"
        )
    
    return "\n\n".join(sections)


def format_positions_context(positions: list) -> str:
    """
    Formats open positions for the Risk Assessor.
    Only Risk gets this detail — TORO/URSA don't need it.
    """
    if not positions:
        return "## CURRENT POSITIONS\nNo open positions."
    
    lines = ["## CURRENT POSITIONS"]
    for pos in positions:
        lines.append(
            f"- {pos['ticker']} {pos['type']} {pos['strike']} "
            f"exp {pos['expiration']} x{pos['quantity']} | "
            f"Cost: ${pos['avg_cost']} | Now: ${pos['current_price']} | "
            f"P/L: {pos['pnl']} | Sector: {pos.get('sector', 'Unknown')}"
        )
    
    return "\n".join(lines)
```

---

## Section 3: Agent System Prompts

These are the system prompts for each of the four committee agents. They define personality, analytical focus, and output format. Store each as a constant string in the committee module.

### TORO Analyst — System Prompt

```python
TORO_SYSTEM_PROMPT = """You are TORO, the bull analyst on a 4-person trading committee. Your job is to make the strongest possible bull case for this trade setup.

ROLE:
- Find every reason this trade could work
- Identify momentum, trend alignment, support levels, and bullish catalysts
- Consider the signal type and what historically works in this market regime
- Be specific — reference the actual ticker, actual market conditions, actual catalysts provided

CONSTRAINTS:
- You are NOT a cheerleader. If the bull case is genuinely weak, say so honestly. "The bull case here is thin" is a valid analysis.
- Do not fabricate data. Work only with the context provided.
- Do not recommend entry/stop/target — that's the Risk Assessor's job.
- Keep it to 2-3 sentences max. Be direct and specific.

OUTPUT FORMAT (follow exactly):
ANALYSIS: <your 2-3 sentence bull case>
CONVICTION: <HIGH or MEDIUM or LOW>

CONVICTION GUIDE:
- HIGH: Multiple confluent factors align (signal + regime + catalyst timing + technical setup)
- MEDIUM: Setup has merit but missing one key element or has notable uncertainty
- LOW: Bull case exists but is stretched or relies on hope more than evidence"""
```

### URSA Analyst — System Prompt

```python
URSA_SYSTEM_PROMPT = """You are URSA, the bear analyst on a 4-person trading committee. Your job is to find every risk and reason this trade could fail.

ROLE:
- Identify headwinds: resistance levels, adverse catalysts, regime misalignment
- Flag if the signal conflicts with the current bias regime (e.g., bullish signal during URSA_MAJOR)
- Consider what the market is pricing in that the signal might be ignoring
- Highlight timing risks — earnings, FOMC, CPI within the DTE window
- Be the voice that prevents the team from walking into a trap

CONSTRAINTS:
- You are NOT a permanent pessimist. If the setup is genuinely clean with minimal risk, acknowledge it. "I'm struggling to find material risk here" is valid.
- Do not fabricate risks. Work only with the context provided.
- Do not recommend trade parameters — that's the Risk Assessor's job.
- Keep it to 2-3 sentences max. Be direct and specific.

OUTPUT FORMAT (follow exactly):
ANALYSIS: <your 2-3 sentence bear case / risk identification>
CONVICTION: <HIGH or MEDIUM or LOW>

CONVICTION GUIDE (inverted — HIGH means high conviction the trade FAILS):
- HIGH: Multiple serious risks present (regime conflict + catalyst trap + weak signal)
- MEDIUM: Notable risks exist but the setup isn't fatally flawed
- LOW: Risks are minor or manageable — this is a relatively clean setup"""
```

### Risk Assessor — System Prompt

```python
RISK_SYSTEM_PROMPT = """You are the Risk Assessor on a 4-person options trading committee. You translate trade ideas into executable positions with precise parameters.

ROLE:
- Define exact entry, stop loss, and profit target levels
- Calculate position size based on account rules (see below)
- Evaluate options-specific factors: IV rank, theta decay timeline, bid-ask liquidity
- Check correlation with current open positions (provided in context)
- Flag catalyst timing conflicts (earnings/FOMC within DTE = materially different trade)
- Recommend exit management: partial profit targets, trailing stop rules

ACCOUNT RULES:
- Account size: ~$4,700 (Robinhood)
- Max risk per trade: 5% = ~$235
- Position size = max risk / (entry - stop)
- Never exceed 3 contracts on any single position
- If IV rank > 75th percentile, flag the premium expense explicitly

OPTIONS INTELLIGENCE:
- If buying options near earnings, state the IV crush risk explicitly
- If theta burn exceeds 5% of position value per day, flag it
- For spreads, calculate max loss and max gain
- Note bid-ask spread — if wider than 10% of option price, flag liquidity concern

POSITION CORRELATION:
- Check the CURRENT POSITIONS section of context
- If new trade is in same sector or correlated ticker, reduce size recommendation
- If new trade is same direction as majority of portfolio, note concentration risk
- Count total open positions — if 5+, suggest closing weakest before adding

EXIT PLAN (include with every recommendation):
- Partial profit: at what level to take half off
- Trailing stop: when to move stop to breakeven on remainder
- Time stop: if trade hasn't moved in X days, reassess
- Greed prevention: specific level where "good enough, take the win"

OUTPUT FORMAT (follow exactly):
ANALYSIS: <risk assessment paragraph — IV, theta, liquidity, correlation, catalyst timing>
ENTRY: <specific entry price or condition>
STOP: <specific stop loss level>
TARGET: <specific profit target>
SIZE: <number of contracts with reasoning>"""
```

### Pivot / Mark Baum — System Prompt

```python
PIVOT_SYSTEM_PROMPT = """You are Pivot, the lead synthesizer of a 4-person trading committee. You have the personality of Mark Baum from "The Big Short" — sharp, skeptical, impatient with weak reasoning, but fair when the data is clean.

YOUR VOICE:
- Direct and unvarnished. No corporate-speak, no hedging with "it could potentially maybe..."
- If the setup is good, say so plainly: "This is clean. Take it."
- If the setup is garbage, say so: "I'm not putting money on this. The risk/reward is upside down."
- Challenge weak reasoning from TORO or URSA — if one of them made a lazy argument, call it out
- Use occasional wit but never at the expense of clarity
- You're talking to one person (Nick) who trades options. Be conversational, not formal.

YOUR JOB:
- Read all three analyst reports (TORO, URSA, Risk Assessor)
- Weigh the bull vs bear case and determine which is more compelling
- Consider the Risk Assessor's parameters — are they realistic?
- Make a final recommendation: TAKE, PASS, or WATCHING
- State what specifically would invalidate this trade (the "what kills it" scenario)
- Assign a conviction level based on how aligned the committee is

DECISION FRAMEWORK:
- TAKE: Bull case outweighs bear case, risk parameters are clean, timing is right
- PASS: Bear case is stronger, or risk/reward doesn't justify the position
- WATCHING: Setup has potential but needs something to confirm (a level to break, a catalyst to pass, etc.)

CONVICTION CALIBRATION:
- HIGH: All three analysts mostly agree, clean setup, manageable risk
- MEDIUM: Mixed signals — valid arguments on both sides, proceed with caution
- LOW: Recommending despite significant uncertainty — only for asymmetric setups

OUTPUT FORMAT (follow exactly):
SYNTHESIS: <your Mark Baum-voiced synthesis, 3-5 sentences, reference specific analyst points>
CONVICTION: <HIGH or MEDIUM or LOW>
ACTION: <TAKE or PASS or WATCHING>
INVALIDATION: <one sentence — the specific scenario that kills this trade>"""
```

---

## Section 4: Updated `run_committee()` Function

This replaces the stub version from 03A. The function signature and return shape are identical — only the internals change.

### Full Replacement

```python
async def run_committee(signal: dict, context: dict) -> dict:
    """
    Run all four committee agents via LLM and produce recommendation.
    
    Replaces the stub version from Brief 03A.
    Returns same contract shape — orchestrator and Discord output unchanged.
    """
    
    # Format base context (shared by all agents)
    base_context = format_signal_context(signal, context)
    
    # ---- TORO ANALYST ----
    toro_raw = await call_agent(
        system_prompt=TORO_SYSTEM_PROMPT,
        user_message=base_context,
        max_tokens=500,
        temperature=0.3,
        agent_name="TORO"
    )
    
    if toro_raw:
        toro_response = parse_analyst_response(toro_raw, "TORO")
    else:
        toro_response = {
            "agent": "TORO",
            "analysis": "[ANALYSIS UNAVAILABLE — TORO agent timed out]",
            "conviction": "MEDIUM"
        }
    
    # ---- URSA ANALYST ----
    ursa_raw = await call_agent(
        system_prompt=URSA_SYSTEM_PROMPT,
        user_message=base_context,
        max_tokens=500,
        temperature=0.3,
        agent_name="URSA"
    )
    
    if ursa_raw:
        ursa_response = parse_analyst_response(ursa_raw, "URSA")
    else:
        ursa_response = {
            "agent": "URSA",
            "analysis": "[ANALYSIS UNAVAILABLE — URSA agent timed out]",
            "conviction": "MEDIUM"
        }
    
    # ---- RISK ASSESSOR ----
    # Risk gets additional position context
    positions_text = format_positions_context(context.get("open_positions", []))
    risk_context = f"{base_context}\n\n{positions_text}"
    
    risk_raw = await call_agent(
        system_prompt=RISK_SYSTEM_PROMPT,
        user_message=risk_context,
        max_tokens=800,
        temperature=0.3,
        agent_name="RISK"
    )
    
    if risk_raw:
        risk_response = parse_risk_response(risk_raw)
    else:
        risk_response = {
            "agent": "RISK",
            "analysis": "[ANALYSIS UNAVAILABLE — Risk Assessor timed out. Using conservative defaults.]",
            "entry": "N/A — manual review required",
            "stop": "Tight stop — define before entry",
            "target": "N/A — manual review required",
            "size": "1 contract (conservative default)"
        }
    
    # ---- PIVOT / MARK BAUM ----
    # Pivot reads all three analyst reports
    pivot_context = (
        f"{base_context}\n\n"
        f"## TORO ANALYST REPORT\n"
        f"Analysis: {toro_response['analysis']}\n"
        f"Conviction: {toro_response['conviction']}\n\n"
        f"## URSA ANALYST REPORT\n"
        f"Analysis: {ursa_response['analysis']}\n"
        f"Conviction: {ursa_response['conviction']}\n\n"
        f"## RISK ASSESSOR REPORT\n"
        f"Analysis: {risk_response['analysis']}\n"
        f"Entry: {risk_response['entry']}\n"
        f"Stop: {risk_response['stop']}\n"
        f"Target: {risk_response['target']}\n"
        f"Size: {risk_response['size']}"
    )
    
    pivot_raw = await call_agent(
        system_prompt=PIVOT_SYSTEM_PROMPT,
        user_message=pivot_context,
        max_tokens=1000,
        temperature=0.6,
        agent_name="PIVOT"
    )
    
    if pivot_raw:
        pivot_response = parse_pivot_response(pivot_raw)
    else:
        # Fallback: concatenate analyst reports as plain summary
        pivot_response = {
            "agent": "PIVOT",
            "synthesis": (
                f"[PIVOT UNAVAILABLE — plain summary]\n"
                f"Bull: {toro_response['analysis']}\n"
                f"Bear: {ursa_response['analysis']}\n"
                f"Risk: {risk_response['analysis']}"
            ),
            "conviction": "LOW",
            "action": "WATCHING",
            "invalidation": "Manual review required — Pivot synthesis unavailable"
        }
    
    # ---- ASSEMBLE RECOMMENDATION ----
    return {
        "signal": signal,
        "agents": {
            "toro": toro_response,
            "ursa": ursa_response,
            "risk": risk_response,
            "pivot": pivot_response
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": DEFAULT_MODEL,
        "raw_responses": {
            "toro": toro_raw,
            "ursa": ursa_raw,
            "risk": risk_raw,
            "pivot": pivot_raw
        }
    }
```

### Logging Enhancement

Add raw LLM responses to the committee log for prompt debugging:

```python
# In log_committee(), add these fields to the entry dict:
"model": recommendation.get("model"),
"toro_raw_length": len(recommendation.get("raw_responses", {}).get("toro") or ""),
"ursa_raw_length": len(recommendation.get("raw_responses", {}).get("ursa") or ""),
"risk_raw_length": len(recommendation.get("raw_responses", {}).get("risk") or ""),
"pivot_raw_length": len(recommendation.get("raw_responses", {}).get("pivot") or ""),
"any_agent_failed": any(
    v is None for v in recommendation.get("raw_responses", {}).values()
)
```

Do NOT log full raw responses to JSONL — they bloat the file. Store raw responses in a separate debug log if needed:

```python
# Optional: /opt/openclaw/workspace/data/committee_debug.jsonl
# Only written when DEBUG logging is enabled
# Contains full raw LLM responses for prompt tuning
```

---

## Section 5: Nick's Bias Challenge Injection

Pivot is specifically configured to challenge Nick's known biases. This is NOT in the system prompt (which stays stable) — it's injected as additional context in the user message when relevant conditions are met.

### Bias Challenge Logic

```python
def get_bias_challenge_context(signal: dict, context: dict) -> str:
    """
    Returns additional context to inject into Pivot's user message
    when the signal might trigger Nick's known biases.
    
    Nick's documented biases:
    1. Extremely bearish on Trump admin / US macro stability
    2. Extremely bullish on AI disruption as a trade thesis
    
    Pivot should challenge these when they might lead to bad trades.
    """
    challenges = []
    bias = context.get("bias", {})
    ticker = signal["ticker"]
    direction = signal["direction"]
    
    # Challenge 1: Nick's bearish macro bias
    # If signal is BEARISH and regime is actually TORO, Nick might be
    # confirmation-biasing into a bad short
    if direction == "BEARISH" and bias.get("regime", "").startswith("TORO"):
        challenges.append(
            "⚠️ BIAS CHECK: This is a BEARISH signal but the market regime "
            "is actually bullish. Nick has a documented bearish macro bias — "
            "make sure this trade is based on the chart, not on macro anxiety. "
            "Challenge him if the bear case relies on 'the market should be lower' "
            "rather than specific technical evidence."
        )
    
    # Challenge 2: Nick's AI bullish bias
    ai_tickers = {"NVDA", "AMD", "SMCI", "MSFT", "GOOGL", "GOOG", "META", 
                   "AMZN", "PLTR", "ARM", "TSM", "AVGO", "MRVL", "AI", "SNOW"}
    
    if ticker in ai_tickers and direction == "BULLISH":
        challenges.append(
            "⚠️ BIAS CHECK: This is a BULLISH signal on an AI-related ticker. "
            "Nick has a documented bullish bias on AI disruption. "
            "Be extra critical of the bull case — is this actually a good entry "
            "or is Nick just bullish on the sector regardless of timing and price? "
            "Check if IV is elevated from AI hype cycles."
        )
    
    # Challenge 3: Bearish on AI ticker when he's usually bullish
    # This one is actually useful — might be right for once
    if ticker in ai_tickers and direction == "BEARISH":
        challenges.append(
            "💡 NOTE: Nick is typically very bullish on AI tickers, so a bearish "
            "signal here is counter to his usual bias. This might actually be a "
            "higher-quality signal since it's not confirmation bias. Evaluate on merits."
        )
    
    if challenges:
        return "\n\n## BIAS CHALLENGE NOTES (for Pivot only)\n" + "\n\n".join(challenges)
    return ""
```

### Integration Point

Add the bias challenge to Pivot's user message only (not TORO/URSA/Risk):

```python
# In run_committee(), before calling Pivot:
bias_challenge = get_bias_challenge_context(signal, context)

pivot_context = (
    f"{base_context}\n\n"
    f"## TORO ANALYST REPORT\n..."
    f"## URSA ANALYST REPORT\n..."
    f"## RISK ASSESSOR REPORT\n..."
    f"{bias_challenge}"  # Only appended when relevant
)
```

---

## Section 6: Discord Embed Update

The Discord embed format from 03A used stub data. Now that agents return real analysis, the embed needs richer formatting. The embed structure stays the same — only the content mapping changes.

### Updated Embed Field Mapping

```python
def build_committee_embed(recommendation: dict) -> discord.Embed:
    """
    Build Discord embed from committee recommendation.
    
    Changes from 03A stub version:
    - Real analysis text instead of hardcoded strings
    - Color based on Pivot's action (not hardcoded green)
    - Truncation safety for long LLM responses
    - Bias challenge indicator if present
    """
    agents = recommendation["agents"]
    signal = recommendation["signal"]
    pivot = agents["pivot"]
    risk = agents["risk"]
    
    # Color by action
    color_map = {
        "TAKE": 0x00FF88,    # green
        "PASS": 0xFF4444,    # red
        "WATCHING": 0xFFAA00  # amber
    }
    color = color_map.get(pivot["action"], 0x888888)
    
    # Action emoji
    emoji_map = {
        "TAKE": "🟢",
        "PASS": "🔴",
        "WATCHING": "🟡"
    }
    emoji = emoji_map.get(pivot["action"], "⚪")
    
    # Title
    embed = discord.Embed(
        title=f"{emoji} {signal['ticker']} — {pivot['action']}",
        color=color,
        timestamp=datetime.now(timezone.utc)
    )
    
    # Pivot synthesis (main body)
    synthesis = truncate(pivot["synthesis"], 1024)
    embed.description = synthesis
    
    # Conviction bar
    conviction_display = {
        "HIGH": "🟩🟩🟩 HIGH",
        "MEDIUM": "🟨🟨⬜ MEDIUM",
        "LOW": "🟥⬜⬜ LOW"
    }
    embed.add_field(
        name="Conviction",
        value=conviction_display.get(pivot["conviction"], pivot["conviction"]),
        inline=True
    )
    
    embed.add_field(
        name="Direction",
        value=signal["direction"],
        inline=True
    )
    
    embed.add_field(
        name="Signal",
        value=f"{signal['alert_type']} (score: {signal.get('score', 'N/A')})",
        inline=True
    )
    
    # Trade parameters from Risk
    trade_params = (
        f"**Entry:** {risk['entry']}\n"
        f"**Stop:** {risk['stop']}\n"
        f"**Target:** {risk['target']}\n"
        f"**Size:** {risk['size']}"
    )
    embed.add_field(name="📊 Trade Parameters", value=truncate(trade_params, 1024), inline=False)
    
    # Bull vs Bear summary
    toro = agents["toro"]
    ursa = agents["ursa"]
    embed.add_field(
        name=f"🐂 TORO ({toro['conviction']})",
        value=truncate(toro["analysis"], 512),
        inline=True
    )
    embed.add_field(
        name=f"🐻 URSA ({ursa['conviction']})",
        value=truncate(ursa["analysis"], 512),
        inline=True
    )
    
    # Invalidation
    embed.add_field(
        name="❌ Invalidation",
        value=truncate(pivot["invalidation"], 256),
        inline=False
    )
    
    # Footer with signal metadata
    embed.set_footer(
        text=f"Signal ID: {signal.get('id', 'N/A')} | Model: {recommendation.get('model', 'N/A')}"
    )
    
    return embed


def truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."
```

### Button Row (Visual Only in 03B)

Same as 03A — buttons rendered but not wired. Brief 03C wires them.

```python
class CommitteeView(discord.ui.View):
    """Placeholder buttons — wired in Brief 03C."""
    
    def __init__(self, signal_id: str):
        super().__init__(timeout=None)
        self.signal_id = signal_id
    
    @discord.ui.button(label="✅ Take", style=discord.ButtonStyle.green, custom_id="take")
    async def take_button(self, interaction, button):
        await interaction.response.send_message("Decision tracking coming in Brief 03C", ephemeral=True)
    
    @discord.ui.button(label="❌ Pass", style=discord.ButtonStyle.red, custom_id="pass")
    async def pass_button(self, interaction, button):
        await interaction.response.send_message("Decision tracking coming in Brief 03C", ephemeral=True)
    
    @discord.ui.button(label="👀 Watching", style=discord.ButtonStyle.grey, custom_id="watching")
    async def watching_button(self, interaction, button):
        await interaction.response.send_message("Decision tracking coming in Brief 03C", ephemeral=True)
    
    @discord.ui.button(label="🔄 Re-evaluate", style=discord.ButtonStyle.blurple, custom_id="reeval")
    async def reeval_button(self, interaction, button):
        await interaction.response.send_message("Re-evaluation coming in Brief 03C", ephemeral=True)
```

---

## Section 7: Testing Checklist

### LLM Call Wrapper Tests

- [ ] `call_agent()` returns text on successful call
- [ ] `call_agent()` returns `None` after timeout + exhausted retries
- [ ] `call_agent()` retries once on 500 error, then returns `None`
- [ ] `call_agent()` retries once on timeout, then returns `None`
- [ ] `call_agent()` logs each attempt with agent name
- [ ] OpenRouter API key loaded from environment
- [ ] Model string matches `anthropic/claude-sonnet-4-20250514`

### Response Parser Tests

- [ ] `parse_analyst_response()` extracts ANALYSIS and CONVICTION from well-formatted response
- [ ] `parse_analyst_response()` uses fallback (whole text as analysis, MEDIUM) on malformed response
- [ ] `parse_analyst_response()` rejects invalid conviction values (uses MEDIUM)
- [ ] `parse_risk_response()` extracts all 5 fields from well-formatted response
- [ ] `parse_risk_response()` uses fallback defaults for missing fields
- [ ] `parse_pivot_response()` extracts all 4 fields from well-formatted response
- [ ] `parse_pivot_response()` rejects invalid ACTION values (uses WATCHING)
- [ ] `parse_pivot_response()` rejects invalid CONVICTION values (uses MEDIUM)
- [ ] All parsers handle empty string input without crashing
- [ ] All parsers handle `None` input without crashing (guard before calling)

### Context Formatter Tests

- [ ] `format_signal_context()` includes all signal fields
- [ ] `format_signal_context()` includes market regime section
- [ ] `format_signal_context()` includes circuit breakers when present
- [ ] `format_signal_context()` omits circuit breakers section when none recent
- [ ] `format_signal_context()` includes whale context for `whale_flow_confirmed` signals
- [ ] `format_signal_context()` caps macro events at 10 items
- [ ] `format_positions_context()` shows "No open positions" when empty
- [ ] `format_positions_context()` formats all position fields correctly

### Committee Flow Tests

- [ ] `run_committee()` calls all 4 agents sequentially
- [ ] `run_committee()` returns correct contract shape even when all agents fail
- [ ] TORO failure → stub response with `[ANALYSIS UNAVAILABLE]`, pipeline continues
- [ ] URSA failure → stub response with `[ANALYSIS UNAVAILABLE]`, pipeline continues
- [ ] Risk failure → stub with conservative defaults, pipeline continues
- [ ] Pivot failure → concatenated analyst reports as plain summary
- [ ] Risk receives position context that TORO/URSA do not
- [ ] Pivot receives all three analyst reports in its user message
- [ ] Pivot receives bias challenge context when triggered
- [ ] Return dict includes `raw_responses` for debug logging
- [ ] Return dict includes `model` field
- [ ] Return dict includes ISO timestamp

### Bias Challenge Tests

- [ ] Bearish signal during TORO regime → bearish macro bias challenge injected
- [ ] Bullish signal on AI ticker → AI bullish bias challenge injected
- [ ] Bearish signal on AI ticker → "counter-bias, might be quality" note injected
- [ ] Bullish signal on non-AI ticker during URSA regime → no challenge
- [ ] No challenge context → empty string returned (no section added)
- [ ] Challenge only appears in Pivot's context, not TORO/URSA/Risk

### Discord Embed Tests

- [ ] Embed color matches Pivot's action (green/red/amber)
- [ ] Embed title shows ticker and action
- [ ] Synthesis displayed in description (truncated if >1024 chars)
- [ ] Trade parameters formatted correctly
- [ ] TORO and URSA analyses shown side by side with conviction
- [ ] Invalidation field present
- [ ] Footer shows signal ID and model
- [ ] `truncate()` handles strings shorter than max_len (no ellipsis)
- [ ] `truncate()` handles strings longer than max_len (adds ellipsis)
- [ ] All embed fields stay within Discord's limits (title: 256, field value: 1024, description: 4096)

### Integration Smoke Test

1. Send a test CTA Scanner signal via Railway API (`POST /api/signals/test`)
2. Signal passes gatekeeper (03A) → context built → committee called
3. Verify TORO agent produces real analysis (not stub text)
4. Verify URSA agent produces real analysis
5. Verify Risk Assessor produces trade parameters with real numbers
6. Verify Pivot produces Mark Baum-voiced synthesis with TAKE/PASS/WATCHING
7. Verify Discord embed renders correctly with all fields populated
8. Verify committee_log.jsonl contains model and raw response lengths
9. Total time from signal to Discord post: < 2 minutes (4 LLM calls @ 30s timeout max)
10. Send a BULLISH signal on NVDA → verify bias challenge appears in Pivot's synthesis
11. Send a signal when TORO regime active + BEARISH direction → verify macro bias challenge
12. Kill OpenRouter (set bad API key) → verify all 4 agents fallback gracefully → Discord still posts

### Implementation Order

1. Add `call_agent()` wrapper to committee module
2. Add all 4 parser functions with unit tests
3. Add `format_signal_context()` and `format_positions_context()`
4. Add all 4 system prompt constants
5. Replace stub `run_committee()` with real version — test with TORO only first
6. Wire in URSA, then Risk, then Pivot one at a time
7. Add `get_bias_challenge_context()` and inject into Pivot's user message
8. Update `build_committee_embed()` to use real agent data
9. Add logging enhancement (raw response lengths, model, any_agent_failed)
10. Run full integration smoke test (steps 1-12 above)
11. Run with bad API key to verify all fallback paths
12. Monitor first 5 live signals for prompt quality — note any parsing failures

---

## File Summary

| File | Action |
|------|--------|
| `/opt/openclaw/workspace/scripts/pivot2_committee.py` | **Modify** — replace stubs with real LLM calls |
| `/opt/openclaw/workspace/scripts/committee_prompts.py` | **Create** — system prompts as constants |
| `/opt/openclaw/workspace/scripts/committee_parsers.py` | **Create** — response parsers |
| `/opt/openclaw/workspace/scripts/committee_context.py` | **Create** — context formatters + bias challenge |
| `/opt/openclaw/workspace/data/committee_debug.jsonl` | **Create** — optional debug log for raw responses |

All other files from 03A remain unchanged. Gatekeeper, orchestrator, systemd timer, Discord output pipeline — all untouched.
