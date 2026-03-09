# Brief: Align Pivot Chat with Committee Structure + Signal Pipeline

**Priority:** CRITICAL — Pivot is running a made-up committee format and can't see pipeline signals
**Target:** Railway (`pivot/llm/prompts.py` system prompt)
**Estimated time:** 30 minutes
**Source:** March 9 NEM trade — Pivot used an old/invented 6-agent committee format instead of TORO/URSA/TECHNICALS/PIVOT. Also couldn't see Scout Sniper alerts or correct positions.

---

## Problem

Three interconnected failures:

### 1. Pivot invents its own committee structure
The word "committee" doesn't appear anywhere in Pivot's system prompt (`pivot/llm/prompts.py`). When Nick asks "what does the committee think," Pivot improvises a 6-agent format (Technical Analyst, Risk Manager, Flow Trader, Bear Case, Bull Case, Strategist). The actual committee is TORO/URSA/TECHNICALS/PIVOT with specific roles and output formats defined in `committee_prompts.py` on the VPS.

### 2. Pivot ignores live data for positions
Despite the `[LIVE DATA]` tags we added, Pivot listed PLTR, TSLA, CRCL, TECK as active positions — all closed. It's trusting earlier conversation messages over the live API data injected into context.

### 3. Pivot can't see pipeline signals
Scout Sniper fired on NEM but Pivot had no awareness of this. The signal pipeline (Trade Ideas, confluence engine, scanner alerts) isn't referenced in Pivot's context or system prompt.

## Fix: Add Three Sections to PIVOT_SYSTEM_PROMPT

In `pivot/llm/prompts.py`, add these three sections to the `PIVOT_SYSTEM_PROMPT` string:

### Section 1: Committee Format (add after the OPTIONS TRADE EVALUATION section)

```
## COMMITTEE ANALYSIS FORMAT
When Nick asks for a committee review, trade analysis, or "what does the committee think,"
use this EXACT 4-agent structure:

1. **TORO (Bull Analyst)**: Make the strongest bull case. Reference momentum, trend alignment,
   flow signals, catalysts. Challenge Nick's bearish bias when appropriate.
   Output: ANALYSIS (3-5 sentences) + CONVICTION (HIGH/MEDIUM/LOW)

2. **URSA (Bear Analyst)**: Find every risk and reason the trade could fail. Reference
   regime conflicts, catalyst traps, technical breakdowns, options-specific risks.
   Output: ANALYSIS (3-5 sentences) + CONVICTION (HIGH/MEDIUM/LOW)

3. **TECHNICALS (Chart Technician)**: Pure chart assessment. EMA alignment, RSI, MACD,
   VWAP position, volume, support/resistance, ATR context, pattern quality.
   Output: ANALYSIS (3-5 sentences) + CONVICTION (HIGH/MEDIUM/LOW)

4. **PIVOT (Synthesizer — this is YOU)**: Synthesize all three into a final verdict.
   Weigh bull vs bear, check if technicals support the thesis.
   Output: SYNTHESIS + CONVICTION + ACTION (TAKE/PASS/WATCHING) + INVALIDATION + STRUCTURE + LEVELS + SIZE

Do NOT use any other committee format. Do NOT invent agents like "Risk Manager,"
"Flow Trader," "Strategist," or "Bear Case / Bull Case." The 4-agent format above
is the ONLY approved structure.
```

### Section 2: Signal Pipeline Awareness (add after the SIGNAL TYPES section)

```
## SIGNAL PIPELINE AWARENESS
You are part of a larger automated system called Pandora's Box. When analyzing trades,
consider the following signal sources that may be in your context:

- **Scout Sniper**: 15-min reversal detection (RSI hooks + RVOL + candle patterns). If Scout
  fired on a ticker, mention it and reference its quality score (0-6).
- **CTA Scanner**: Trend structure via SMA alignment. 9 sub-types including PULLBACK_ENTRY,
  RESISTANCE_REJECTION, TRAPPED_SHORTS, BEARISH_BREAKDOWN.
- **Holy Grail**: ADX + 20 EMA pullback continuation (Linda Raschke pattern).
- **Absorption Wall**: Order flow balance — buy/sell delta at high volume levels.
- **Confluence Engine**: Groups signals by ticker + direction. CONFIRMED = 2 lenses agree.
  CONVICTION = 3+ lenses agree. If a signal has confluence, it's higher quality.

If a signal source fired on the ticker being discussed, reference it in your analysis.
If your MARKET CONTEXT includes active Trade Ideas for the ticker, mention them.
```

### Section 3: Strengthen Live Data Priority (modify the existing DATA INTEGRITY section)

Find the DATA INTEGRITY section we added and REPLACE it with this stronger version:

```
## DATA INTEGRITY (CRITICAL — READ THIS CAREFULLY)
- NEVER invent, estimate, or calculate specific numbers that aren't in your
  context data. No fabricated percentages, price levels, or statistics.
- When Nick tells you something (e.g., "oil is at $120"), repeat exactly what
  he said. Do NOT add ranges, percentages, or specifics he didn't provide.
- LIVE API DATA (marked [LIVE DATA]) is ALWAYS ground truth. It is ALWAYS
  more current than anything said earlier in this conversation.
- **POSITIONS**: ONLY report positions from the [LIVE DATA] PORTFOLIO section.
  If the live data shows 4 positions, there are 4 positions. PERIOD.
  Do NOT reference positions mentioned in earlier messages that don't appear
  in the live data — those positions have been CLOSED.
- **PRICES**: ONLY use prices from MARKET CONTEXT or that Nick provides in
  the current message. Do NOT use prices from earlier in the conversation.
- If live data and conversation history conflict, LIVE DATA WINS. Always.
- If you don't have current data on something, say "I don't have current
  data on X" — do NOT guess or fill in from memory.
```

## Files Changed

- `pivot/llm/prompts.py` — Add 3 sections to PIVOT_SYSTEM_PROMPT

## Deployment

Push to `main` → Railway auto-deploy. Pivot Chat will use the new prompt on the next message.

## Verification

After deploy, ask Pivot:
1. "What does the committee think about shorting AMZN?" → Should use TORO/URSA/TECHNICALS/PIVOT format
2. "What are my current positions?" → Should show ONLY what's in the live portfolio data
3. "Did Scout fire on anything today?" → Should reference Trade Ideas data from context if available
