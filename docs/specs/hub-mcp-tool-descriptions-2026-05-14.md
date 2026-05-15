# Pandora's Box Hub MCP — Tool Descriptions v1 (2026-05-14)

**Authored by:** ATHENA (Titans PM persona)
**Purpose:** Specify the user-facing surface of the v1 hub MCP. Tool descriptions, parameter ergonomics, when-to-call / when-not-to-call guidance, and the structured response schema for every endpoint Claude.ai (Olympus) will call. This doc is the canonical reference CC implements against — descriptions copied verbatim into the FastMCP `@tool(description=...)` decorators.

**Why this matters:** Skills under-trigger by default; tools likewise. Whether `hub_get_bias_composite` actually fires when TORO needs bias data depends almost entirely on the description text and Claude's relevance ranker matching it to the conversation context. Vague descriptions = under-firing = back to web_search fallback = back to the fabrication risk we just fixed. These descriptions are the product surface.

---

## Universal Response Envelope

Every tool returns this shape. No exceptions. Implementations that diverge fail the v1 acceptance test.

```json
{
  "status": "ok" | "stale" | "degraded" | "unavailable",
  "data": <tool-specific structured payload, or null>,
  "summary": "Concise human-readable line, ≤300 chars, suitable for inline chat output",
  "staleness_seconds": 0 | <int> | null,
  "schema_version": "v1.0",
  "error": null | "Brief error description"
}
```

**Status semantics:**
- `ok` — data is fresh per the source's own staleness rules; full confidence
- `stale` — data is past the staleness threshold but still returned; caller should degrade conviction one notch
- `degraded` — data is partial or some factors missing; caller must flag in DATA NOTE
- `unavailable` — tool could not fetch data (downstream hub error, rate limit, timeout); `data` is null, `error` populated

**Summary field rules:**
- Always ≤300 chars; server truncates with ellipsis if a tool implementation produces more
- Plain prose, no JSON, no markdown — designed for inline chat output
- Includes the most decision-relevant numbers and a one-clause directional take where applicable
- Examples:
  - Good: "SPY bias composite: TORO MINOR (+0.32) on swing timeframe. Credit spreads and breadth constructive; VIX term backwardation flat."
  - Bad: "Bias data retrieved successfully. See data field for full details."

---

## Tool 1: `hub_get_bias_composite`

**Description (verbatim for FastMCP decorator):**

> Returns the current 20-factor composite bias reading from the Pandora's Box hub, with per-factor breakdown and staleness flags. Use this when evaluating directional context for any trade idea, when running pre-market or weekly briefing setup, when any Olympus committee member (TORO, URSA, PYTHAGORAS, PYTHIA, THALES, DAEDALUS, PIVOT) needs to confirm whether the market regime supports the proposed direction, or when the user asks about "the bias," "market regime," "directional context," "what does the system see," or any equivalent.
>
> Do NOT call this for company-specific fundamentals, single-stock catalysts, or sector rotation — those have their own tools (`hub_get_hermes_alerts`, `hub_get_sector_strength`). Do NOT call this repeatedly within a single committee pass; one call per pass is sufficient.
>
> Returns 5-level bias mapping (TORO MAJOR / TORO MINOR / NEUTRAL / URSA MINOR / URSA MAJOR), composite score (−1.0 to +1.0), per-factor scores and weights, and staleness per factor.

**Parameters:**

```
timeframe?: "swing" | "daily" | "intraday"
  Optional. If omitted, returns all three timeframes. Most committee passes
  want a specific horizon — TORO/URSA usually want "swing" (multi-day) for
  B1/B2 thesis evaluation, "intraday" for B3 scalp context.
```

**When to call:**
- TORO or URSA opening a committee pass on any ticker (always call once per pass)
- PYTHAGORAS evaluating structural risk and trend alignment against system bias
- PYTHIA cross-referencing whether the auction state aligns with directional bias
- THALES validating sector calls against the broader bias regime (and macro voice-of-reason cross-check)
- DAEDALUS picking options structures appropriate for the current IV/bias regime
- PIVOT pulling final synthesis context for the committee output
- User asks "what's the bias right now?" or equivalent
- Pre-market briefing setup
- Weekly Battlefield Brief context check
- Bias-challenge moments where URSA needs to validate whether system bias matches the user's directional lean

**When NOT to call:**
- Multiple times in the same committee pass (one call, cache the response in conversation context)
- For sector-specific or stock-specific reads (use `hub_get_sector_strength` / `hub_get_flow_radar` instead)
- For historical bias (v1 returns current state only; v2 may add history)

**Data field schema:**

```json
{
  "timeframes": {
    "swing": {
      "composite_score": -1.0 to +1.0,
      "bias_level": "TORO_MAJOR" | "TORO_MINOR" | "NEUTRAL" | "URSA_MINOR" | "URSA_MAJOR",
      "factors": [
        {
          "name": "credit_spreads",
          "score": -1.0 to +1.0,
          "weight": 0.0 to 1.0,
          "staleness_seconds": int,
          "is_stale": bool
        },
        ...
      ],
      "active_factor_count": int,
      "stale_factor_count": int
    },
    "daily": { ... same shape ... },
    "intraday": { ... same shape ... }
  },
  "manual_override_active": bool,
  "override_level": "TORO_MAJOR" | ... | null
}
```

**Summary example:**

> "Swing bias: TORO MINOR (+0.34). 17/20 factors fresh, credit spreads + breadth constructive, VIX term flat. Daily: NEUTRAL (+0.08). Intraday: TORO MINOR (+0.28). No manual override active."

---

## Tool 2: `hub_get_flow_radar`

**Description (verbatim for FastMCP decorator):**

> Returns the current options flow imprint from the Pandora's Box hub — recent unusual options activity, net call/put premium direction, biggest sweeps, sector aggregations. Optionally filtered to a specific ticker. Use this whenever evaluating directional conviction on a trade idea, when TORO needs to confirm bullish positioning is flowing in, when URSA needs to confirm distribution, when DAEDALUS is reading options-specific positioning for structure recommendations, when PYTHIA is checking volume imprint at her key auction levels, when PIVOT is synthesizing committee output, or when the user asks about "the flow," "options imprint," "what's the smart money doing," "unusual activity," or any equivalent.
>
> Do NOT call this for general bias context (use `hub_get_bias_composite` instead). Do NOT call this for fundamentals or catalyst awareness (use `hub_get_hermes_alerts`). For squeeze setup scoring specifically, use `hub_get_hydra_scores`.
>
> Returns ranked list of recent flow events with premium, direction (calls vs puts), unusual-vs-baseline ratio, and timestamp. Includes net premium aggregation for the lookback window.

**Parameters:**

```
ticker?: str
  Optional. If provided, filters to flow events on that specific ticker.
  If omitted, returns top-N global flow events across all tickers
  (default lookback: last 4 hours of market session).

lookback_hours?: int (1-24)
  Optional, defaults to 4. Lookback window for the flow imprint.
```

**When to call:**
- TORO's "Breakout with flow confirmation" pattern (per references/equities.md)
- URSA's "Catalyst asymmetry" or "Crowded long positioning" patterns
- PYTHAGORAS confirming flow direction against trend/structure setup
- PYTHIA cross-referencing volume imprint against her auction-state read at key levels
- THALES checking sector-level flow when evaluating rotation context
- DAEDALUS (primary user) reading options-specific positioning to pick the right structure
- PIVOT pulling flow context for the final synthesis
- User asks about a specific options flow event they saw
- Any committee pass on a specific ticker — confirms whether positioning aligns with the directional thesis

**When NOT to call:**
- For directional bias context (use `hub_get_bias_composite`)
- For historical flow analysis spanning days (v1 caps at 24-hour lookback)
- For dark pool prints specifically (v2 candidate: `hub_get_dark_pool_prints`)

**Data field schema:**

```json
{
  "ticker": str | null,
  "lookback_hours": int,
  "net_premium_calls_usd": float,
  "net_premium_puts_usd": float,
  "net_premium_direction": "BULLISH" | "BEARISH" | "NEUTRAL",
  "events": [
    {
      "ticker": str,
      "strike": float,
      "expiry": "YYYY-MM-DD",
      "option_type": "CALL" | "PUT",
      "side": "BUY" | "SELL",
      "premium_usd": float,
      "size": int,
      "unusual_ratio": float,
      "timestamp": "ISO-8601",
      "type": "SWEEP" | "BLOCK" | "SPLIT" | "ABSORPTION"
    },
    ...
  ],
  "event_count": int
}
```

**Summary example:**

> "TSLA flow last 4h: net BEARISH (-$2.1M premium). 14 events, top is 12,000-lot 5/22 $400 put sweep ($1.4M premium). Mostly distribution; no offsetting call buying."

---

## Tool 3: `hub_get_sector_strength`

**Description (verbatim for FastMCP decorator):**

> Returns cross-sectional sector relative strength and rotation regime tags from the Pandora's Box hub. Identifies leading and lagging sectors, narrow vs broad leadership, and the current rotation state (concentrated leadership / rotation / regime-agnostic). Use this whenever evaluating sector context for a trade, when THALES (primary user) needs sector-rotation input, when TORO is hunting sector-RS-leader patterns, when URSA is flagging crowded sector positioning, when PYTHAGORAS is mapping structural trends to sector backdrop, when DAEDALUS is reading sector-level options pricing context, when PIVOT is assembling sector context for synthesis, or when the user asks about "sector leadership," "rotation," "which sectors are leading," "narrow vs broad," or any equivalent.
>
> Do NOT call this for company-specific fundamentals within a sector (use `hub_get_hermes_alerts`). Do NOT call this for general directional bias (use `hub_get_bias_composite`).
>
> Returns 11 sector ETFs (XLK, XLF, XLE, XLV, XLY, XLP, XLI, XLU, XLB, XLRE, XLC) with rolling 10-day and 20-day RS vs SPY, plus the current rotation regime classification.

**Parameters:** none.

**When to call:**
- Any THALES committee pass (sector context is THALES's primary lens)
- TORO's "Sector RS leader inside a leading sector" pattern
- URSA's "Crowded long positioning" pattern when the question is sector-level
- PYTHAGORAS evaluating whether structural setups align with sector regime
- PYTHIA cross-referencing sector ETF auction state for context
- DAEDALUS reading sector-level IV and options positioning
- PIVOT pulling sector context for synthesis
- Pre-market briefing setup
- User asks about sector rotation explicitly

**When NOT to call:**
- For single-stock RS within a sector (out of v1 scope; v2 candidate)
- For historical rotation analysis (v1 returns current state)
- Multiple times per committee pass

**Data field schema:**

```json
{
  "rotation_regime": "CONCENTRATED_LEADERSHIP" | "BROAD_ROTATION" | "REGIME_AGNOSTIC" | "ACTIVE_DISTRIBUTION",
  "sectors": [
    {
      "etf": "XLK" | "XLF" | ...,
      "name": "Technology" | "Financials" | ...,
      "rs_10d": float,
      "rs_20d": float,
      "rank_10d": int (1-11),
      "rank_20d": int (1-11),
      "state": "LEADING" | "LAGGING" | "ROTATING_IN" | "ROTATING_OUT" | "NEUTRAL"
    },
    ...
  ],
  "narrow_leadership_flag": bool,
  "leadership_breadth_score": 0.0 to 1.0
}
```

**Summary example:**

> "Sector regime: CONCENTRATED_LEADERSHIP (narrow). Leading: XLK (+4.2% 20d RS), XLC (+2.8%), XLY (+1.6%). Lagging: XLE (-3.1%), XLU (-2.4%). Leadership breadth 0.34 — narrow tape, vulnerable to a rotation event."

---

## Tool 4: `hub_get_hermes_alerts`

**Description (verbatim for FastMCP decorator):**

> Returns active catalysts and upcoming events from the Hermes alert system — earnings, FDA decisions, M&A announcements, macro data releases, geopolitical deadlines. Filtered by ticker and lookback window. Use this whenever evaluating catalyst risk for a trade, when TORO needs catalyst tailwinds, when URSA needs catalyst-asymmetry risks, when PYTHAGORAS is mapping catalysts to DTE selection, when PYTHIA is checking for catalyst-driven volume regime shifts at her key levels, when THALES (macro voice-of-reason) is evaluating macro event risk, when DAEDALUS is selecting expiry windows around catalyst risk, when PIVOT is assembling catalyst context for synthesis, or when the user asks about "catalysts," "what's coming up," "earnings," "FDA," "Fed meeting," or any equivalent.
>
> Do NOT call this for general macro context (use `hub_get_bias_composite` for the system's directional read). Do NOT call this for completed catalysts older than the lookback window.
>
> Returns ranked list of upcoming and recent catalysts with type, scheduled timestamp, expected impact, and any system-generated context. Includes both ticker-specific and macro events.

**Parameters:**

```
ticker?: str
  Optional. If provided, filters to catalysts affecting that ticker.
  If omitted, returns all active catalysts across the watchlist plus
  macro events.

lookback_hours?: int (default 24)
  How far back to surface recently-completed catalysts (for catalyst-fade
  analysis). Pass 0 to get only future catalysts.

forward_days?: int (default 14)
  How far forward to look for upcoming catalysts.
```

**When to call:**
- Any committee pass on a specific ticker — catalyst risk awareness is mandatory per the URSA hard-rules block
- TORO checking for catalyst tailwinds supporting the bull thesis
- URSA flagging catalyst-asymmetry where downside is binary
- PYTHAGORAS mapping catalyst dates to structural setups and DTE selection
- PYTHIA watching for catalyst-driven volume regime shifts that invalidate her auction read
- THALES (primary user for macro events) evaluating Fed/CPI/jobs/geopolitical risk
- DAEDALUS selecting expiry windows that bracket or avoid catalyst risk
- PIVOT pulling catalyst context for the final synthesis
- DTE selection for any options expression (catalyst within DTE window changes the trade)
- User asks about upcoming events
- Pre-market briefing setup

**When NOT to call:**
- For real-time news scraping (Hermes is a curated/scheduled catalyst stream, not a news feed)
- For historical catalyst outcomes (v2 candidate: `hub_get_catalyst_outcomes`)

**Data field schema:**

```json
{
  "ticker": str | null,
  "lookback_hours": int,
  "forward_days": int,
  "alerts": [
    {
      "id": str,
      "ticker": str | "MACRO",
      "type": "EARNINGS" | "FDA" | "M_AND_A" | "MACRO_DATA" | "GEOPOLITICAL" | "SECTOR_EVENT",
      "title": str,
      "scheduled_at": "ISO-8601",
      "is_upcoming": bool,
      "hours_until": float | null,
      "hours_since": float | null,
      "expected_impact": "LOW" | "MEDIUM" | "HIGH" | "CRITICAL",
      "context_note": str | null
    },
    ...
  ],
  "critical_count": int,
  "high_count": int
}
```

**Summary example:**

> "TSLA catalysts: Q2 earnings 7/29 (75 days out, HIGH impact). No near-term catalysts within DTE window. Macro: FOMC 5/20 (5 days, CRITICAL); CPI 5/22 (7 days, HIGH). Heads-up for any May-expiry positions."

---

## Tool 5: `hub_get_hydra_scores`

**Description (verbatim for FastMCP decorator):**

> Returns the current Hydra squeeze setup scores from the Pandora's Box hub — composite scoring on squeeze-trade candidates based on short interest, days-to-cover, options positioning, gamma flip levels, and price compression. Filtered by ticker or returns top-N candidates globally. Use this whenever evaluating squeeze potential for a trade, when TORO is checking the "Squeeze setup" pattern (per references/equities.md), when URSA is grading whether a previously squeezed name is fading, when PYTHAGORAS is mapping squeeze candidates to structural breakout setups, when DAEDALUS is sizing options exposure on a squeeze candidate, when PIVOT is assembling the synthesis around a squeeze thesis, or when the user asks about "squeezes," "short squeeze," "Hydra," or any equivalent.
>
> Do NOT call this for general flow analysis (use `hub_get_flow_radar`). Do NOT call this for bias context (use `hub_get_bias_composite`).
>
> Returns ranked squeeze scores with component breakdown (short interest, options skew, gamma positioning, price compression).

**Parameters:**

```
ticker?: str
  Optional. If provided, returns Hydra score for that specific ticker.
  If omitted, returns top-10 squeeze candidates globally.

min_score?: float (0-100, default 50)
  Only return candidates with composite score above this threshold.
```

**When to call:**
- TORO's "Squeeze setup" pattern evaluation (primary user)
- URSA grading whether a previously squeezed name is fading (failed-squeeze pattern)
- PYTHAGORAS mapping squeeze candidates to structural breakout / compression setups
- DAEDALUS sizing the options structure on a squeeze candidate (long calls vs call debit spread)
- PIVOT pulling squeeze context for synthesis
- Any committee pass where short positioning is part of the thesis
- User asks about squeeze candidates

**When NOT to call:**
- For general options flow (use `hub_get_flow_radar`)
- For sector rotation context (use `hub_get_sector_strength`)
- For historical squeeze outcomes (v2 candidate)

**Data field schema:**

```json
{
  "ticker": str | null,
  "min_score": float,
  "candidates": [
    {
      "ticker": str,
      "composite_score": 0-100,
      "components": {
        "short_interest_score": 0-100,
        "days_to_cover_score": 0-100,
        "options_skew_score": 0-100,
        "gamma_positioning_score": 0-100,
        "price_compression_score": 0-100
      },
      "short_interest_pct": float,
      "days_to_cover": float,
      "gamma_flip_level": float | null,
      "current_price": float
    },
    ...
  ],
  "candidate_count": int
}
```

**Summary example:**

> "TSLA Hydra: 47/100 — below squeeze threshold. SI 2.8% (low), DTC 0.4 (low), options skew neutral. Not a squeeze candidate. Top global candidates: KRMN (88), SNOW (76), LPTH (71)."

---

## Tool 6: `hub_get_positions`

**Description (verbatim for FastMCP decorator):**

> Returns positions from the unified_positions table — the canonical source of truth for Nick's trading book across Robinhood, Fidelity Roth IRA, 401k BrokerageLink, and Breakout Prop. Optionally filtered by account or status. Use this whenever evaluating portfolio coherence (URSA's mandatory check), when a trade idea touches an existing position, when sizing recommendations need awareness of current exposure, when TORO is evaluating an "add to existing position" decision, when PYTHAGORAS is checking structural risk concentration, when PYTHIA is checking which positions sit at her key auction levels, when THALES is flagging sector concentration risk, when DAEDALUS is computing per-account exposure for sizing math, when PIVOT is pulling existing book context for synthesis, or when the user asks about "my positions," "open trades," "what am I holding," or any equivalent.
>
> Do NOT call this to check live account balances (use `hub_get_portfolio_balances` for cash/buying power). Do NOT call this for closed trade outcomes prior to position close (those live in `signal_outcomes`, a v2 tool).
>
> Returns full position records including structure, strikes, expiry, quantity, entry price, current value, unrealized PnL, stop loss, and account assignment.

**Parameters:**

```
account?: "robinhood" | "fidelity_roth" | "brokerage_link_401k" | "breakout_prop"
  Optional. If provided, filters to that account only. If omitted, returns
  all accounts.

status?: "OPEN" | "CLOSED" | "ALL"
  Optional, defaults to "OPEN". Use "CLOSED" for recent closes (last 30
  days), "ALL" for combined view.

ticker?: str
  Optional. If provided, returns positions on that specific ticker across
  accounts.
```

**When to call:**
- URSA's mandatory portfolio coherence check (every URSA committee pass — primary user)
- TORO's evaluation of an existing position (add/rework/hold decision)
- PYTHAGORAS checking structural risk concentration and correlation across the book
- PYTHIA cross-referencing positions sitting at her key auction levels
- THALES flagging sector concentration (e.g., multiple longs in one sector during narrow leadership)
- DAEDALUS computing per-account options exposure for sizing math
- PIVOT pulling existing book context for synthesis
- User asks what they're holding
- Sizing recommendations that need account-level exposure context
- Pre-market briefing setup

**When NOT to call:**
- For live account balances or buying power (use `hub_get_portfolio_balances`)
- For closed trade analytics or strategy outcome attribution (v2 tool — links to the committee-review-logging TODO)

**Data field schema:**

```json
{
  "account": str | null,
  "status": str,
  "ticker": str | null,
  "positions": [
    {
      "position_id": str,
      "ticker": str,
      "account": "robinhood" | ...,
      "structure": "equity" | "long_call" | "long_put" | "call_debit_spread" | "put_debit_spread" | "call_credit_spread" | "put_credit_spread" | "iron_condor" | ...,
      "quantity": int,
      "entry_price": float,
      "current_price": float | null,
      "current_value": float | null,
      "unrealized_pnl": float | null,
      "max_loss": float,
      "long_strike": float | null,
      "short_strike": float | null,
      "expiry": "YYYY-MM-DD" | null,
      "dte": int | null,
      "stop_loss": float | null,
      "target": float | null,
      "opened_at": "ISO-8601",
      "closed_at": "ISO-8601" | null,
      "trade_outcome": "WIN" | "LOSS" | "BREAKEVEN" | "OPEN"
    },
    ...
  ],
  "position_count": int,
  "total_capital_at_risk": float
}
```

**Summary example:**

> "8 open positions, $1,847 capital at risk (26% of accounts). RH: 5 (mostly bearish — HYG, BX, JETS puts + IBIT bull). Fidelity Roth: 2 (JEPI, EFA equity). 401k: 1 (cash-heavy). No Breakout positions. Nearest expiry: HYG 5/16 (1 DTE — flag)."

---

## Tool 7: `hub_get_portfolio_balances`

**Description (verbatim for FastMCP decorator):**

> Returns live account balances across all four trading accounts — total balance, cash, buying power, margin. Use this whenever sizing recommendations need real account values (replaces the prior practice of hardcoding dollar amounts in skill files), when TORO/URSA/DAEDALUS/PIVOT is producing a sizing recommendation, when PYTHAGORAS is computing per-position risk parameters against account size, when PYTHIA is sizing a B3 scalp trigger, when THALES is flagging sector concentration as a % of account, when the user asks about "my balance," "how much cash," "buying power," or any equivalent, when evaluating whether a proposed trade fits within three-bucket sizing rules.
>
> Do NOT call this for position-level data (use `hub_get_positions`). Do NOT call this for historical balance changes (v2 candidate).
>
> Returns per-account balance, cash, buying power, margin, last-updated timestamp.

**Parameters:**

```
account?: "robinhood" | "fidelity_roth" | "brokerage_link_401k" | "breakout_prop"
  Optional. If provided, returns balance for that account only. If omitted,
  returns all four accounts.
```

**When to call:**
- Any committee pass with a sizing recommendation — primary callers: TORO (long sizing), URSA (short sizing / hedge sizing), DAEDALUS (options structure sizing math — primary user), PIVOT (synthesis sizing)
- PYTHAGORAS computing per-position risk parameters against total account size
- PYTHIA sizing a B3 scalp trigger ($100 cap until cash infusion lands)
- THALES flagging sector concentration as a percentage of account
- Pre-market briefing setup
- User asks about account balances
- B3 daily-max-loss circuit breaker check (start-of-day balance vs current)

**When NOT to call:**
- For position details (use `hub_get_positions`)
- For historical balance series (v2)
- More than once per committee pass (cache in conversation context)

**Data field schema:**

```json
{
  "accounts": [
    {
      "account": "robinhood",
      "broker": "Robinhood",
      "balance": float,
      "cash": float,
      "buying_power": float,
      "margin_total": float | null,
      "trailing_drawdown_floor": float | null,
      "high_water_mark": float | null,
      "updated_at": "ISO-8601",
      "is_stale": bool
    },
    ...
  ],
  "total_balance": float,
  "total_cash": float,
  "total_buying_power": float
}
```

**Summary example:**

> "Total $39,742. RH $4,371 ($1,892 cash, $4,371 BP). Fidelity Roth $8,503. 401k BL $8,082. Breakout $24,856 ($23,158 trailing floor, $25,158 HWM). All balances <2h old."

---

## Tool 8: `mcp_ping`

**Description (verbatim for FastMCP decorator):**

> Lightweight health check for the Pandora's Box hub MCP server. Returns server status, schema version, and current server time. Used by Olympus skills at the start of every committee pass to confirm MCP connectivity before producing GROUND TRUTH blocks. Rate-limit exempt.
>
> ALWAYS call this as the first action in any Olympus committee pass to verify connection state. If `mcp_ping` returns successfully, downstream tools are reachable. If it fails, fall back to the Context B (web_search) path documented in TORO/URSA skill files and surface "MCP: unreachable" in the DATA NOTE block.
>
> Do NOT call this in the middle of normal data flow — only as a connection check at the start of a pass.

**Parameters:** none.

**When to call:**
- First action in any Olympus committee pass (mandatory)
- When a downstream tool returns `unavailable` status, to determine if the issue is the specific tool or the MCP server itself

**When NOT to call:**
- Mid-pass after other tools have already succeeded
- As a way to keep the connection alive (not needed; SSE handles this)

**Data field schema:**

```json
{
  "status": "ok",
  "server_time": "ISO-8601",
  "schema_version": "v1.0",
  "uptime_seconds": int
}
```

**Summary example:**

> "MCP: connected. Schema v1.0. Server time 2026-05-15T19:42:18Z. Uptime 3d 14h."

---

## Tool 9: `mcp_describe_tools`

**Description (verbatim for FastMCP decorator):**

> Returns the list of all available tools on the Pandora's Box hub MCP server with their descriptions, parameters, and current schema versions. Use this when the user or Claude needs to discover what data is available from the hub, when troubleshooting why a particular tool isn't firing, or when documenting the MCP for reference.
>
> Do NOT call this in normal committee passes — it's a discovery tool, not a data tool. Call it on demand.

**Parameters:** none.

**When to call:**
- User asks "what tools does this MCP have" or equivalent
- Troubleshooting: a tool isn't firing and you want to verify it's registered
- Documentation/audit purposes

**When NOT to call:**
- In every committee pass (waste of rate limit)
- As a substitute for calling specific data tools

**Data field schema:**

```json
{
  "tools": [
    {
      "name": "hub_get_bias_composite",
      "description": "Returns the current 20-factor composite bias...",
      "parameters": [
        {
          "name": "timeframe",
          "type": "string",
          "required": false,
          "values": ["swing", "daily", "intraday"]
        }
      ],
      "schema_version": "v1.0"
    },
    ...
  ],
  "tool_count": 9,
  "server_schema_version": "v1.0"
}
```

**Summary example:**

> "9 tools available: hub_get_bias_composite, hub_get_flow_radar, hub_get_sector_strength, hub_get_hermes_alerts, hub_get_hydra_scores, hub_get_positions, hub_get_portfolio_balances, mcp_ping, mcp_describe_tools. All schema v1.0."

---

## Acceptance Criteria for Tool Descriptions

Before CC implements, this doc must pass three checks:

1. **Nick reads each description and confirms it matches how he'd naturally phrase the data need.** If "the bias" doesn't trigger `hub_get_bias_composite` because the description over-indexed on "20-factor composite," that's a copy fix, not an implementation fix.

2. **Every "When to call" and "When NOT to call" example is concrete enough that Claude's relevance ranker has a sharp signal.** Negative examples are as important as positive ones — they prevent over-firing.

3. **The structured `data` schemas match the actual hub endpoint response shapes.** CC verifies this against the live hub during implementation; if a schema drifts, that's an ATHENA-level review.

---

## Decisions Locked by Nick

1. **Tool naming convention:** `hub_` prefix confirmed for all data tools. `mcp_` prefix retained for meta-tools (`mcp_ping`, `mcp_describe_tools`).

2. **Agent references in "When to call" guidance:** specific, not generic. Each of the seven Olympus members (TORO, URSA, PYTHAGORAS, PYTHIA, THALES, DAEDALUS, PIVOT) is named explicitly in the descriptions and "When to call" lists of every tool where they would plausibly call it. Mappings are educated guesses for the five agents that don't have skill files yet; when each agent's actual skill lands, descriptions can be tweaked in a one-line code change per tool decorator.

**Agent-to-tool mapping reference** (for reviewing whether the right agents are listed on the right tools):

| Tool | Primary agents | Secondary agents |
|------|----------------|------------------|
| `hub_get_bias_composite` | TORO, URSA, PIVOT | PYTHAGORAS, PYTHIA, THALES, DAEDALUS |
| `hub_get_flow_radar` | DAEDALUS, TORO, URSA, PIVOT | PYTHAGORAS, PYTHIA, THALES |
| `hub_get_sector_strength` | THALES | TORO, URSA, PYTHAGORAS, PYTHIA, DAEDALUS, PIVOT |
| `hub_get_hermes_alerts` | THALES (macro), TORO, URSA, DAEDALUS | PYTHAGORAS, PYTHIA, PIVOT |
| `hub_get_hydra_scores` | TORO | URSA, PYTHAGORAS, DAEDALUS, PIVOT |
| `hub_get_positions` | URSA (mandatory) | TORO, PYTHAGORAS, PYTHIA, THALES, DAEDALUS, PIVOT |
| `hub_get_portfolio_balances` | DAEDALUS, TORO, URSA, PIVOT | PYTHAGORAS, PYTHIA, THALES |

The tool-descriptions doc is complete. Implementation brief for CC is next.
