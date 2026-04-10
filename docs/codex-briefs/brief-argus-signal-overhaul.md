# BRIEF: ARGUS — Signal Quality, Timing & Confluence Overhaul
## Priority: P1-P4 tiered | Systems: Backend scoring, Frontend cards, PineScript
## Date: 2026-04-09
## Source: Olympus + Titans committee review of signal timing study
## Depends on: None (all changes are additive)

---

## CONTEXT FOR CLAUDE CODE

A timing study of 111 high-conviction signals (score >= 80) revealed that 41% fire
after 60%+ of the price move is already done. The scoring engine has no freshness
penalty, flow data is completely disconnected from signal scoring, and the squeeze
scanner is not cross-referenced with trade signals. The Insight cards also need
a redesign for clarity, mobile density, and time-horizon guidance.

This brief is split into four priority tiers. Each tier is independently deployable.
Build them in order: P1 first, then P2, etc.

### KEY FINDINGS FROM THE STUDY:
- CTA Scanner sub-strategies have wildly different timing quality:
  - Pullback Entry (n=57): 65% actionable — KEEP
  - Trapped Shorts (n=5): 80% actionable — BEST
  - Resistance Rejection (n=18): 56% actionable — MIXED
  - Sell Rip VWAP (n=12): 25% actionable — STALE
- Technical confluence bonus inversely correlates with timing (higher = later)
- flow_events table has 1 row, uw_snapshots has 0 rows — flow is unused
- squeeze_scores exists (20 tickers) but is never cross-referenced with signals
- Score factors: base_score, bias_alignment, recency, risk_reward,
  sector_priority, sector_rotation_bonus, technical_confluence, time_of_day,
  circuit_breaker_bonus/penalty, contrarian. NO flow factor. NO freshness factor.

---

## P1: FRESHNESS PENALTY + DISPLAY FIXES (highest impact, smallest effort)

### P1A: Freshness penalty in scoring engine

**File: `backend/signals/scoring.py` (or wherever the score calculation lives)**

At signal creation time, BEFORE applying the alignment multiplier, calculate:

```python
# Range consumed = where current price sits in the 10-day high/low range
ten_day_high = max(daily_closes[-10:])
ten_day_low = min(daily_closes[-10:])
range_size = ten_day_high - ten_day_low
if range_size > 0:
    if direction == 'LONG':
        range_consumed = (entry_price - ten_day_low) / range_size
    else:  # SHORT
        range_consumed = (ten_day_high - entry_price) / range_size
else:
    range_consumed = 0.5

# Apply penalty
if range_consumed > 0.85:
    freshness_penalty = -25
elif range_consumed > 0.70:
    freshness_penalty = -15
elif range_consumed > 0.60:
    freshness_penalty = -8
else:
    freshness_penalty = 0
```

Add `freshness_penalty` to the `triggering_factors.calculation` dict alongside
the existing `rr_bonus`, `technical_bonus`, etc. Apply it BEFORE the alignment
multiplier. Also store `range_consumed` as a float in triggering_factors so the
frontend can display the timing badge.

Price data source: Use Polygon.io daily bars (already available). Fall back to
yfinance if Polygon is unavailable.

### P1B: Display name mapping (underscores to English)

**File: Frontend `app.js` — wherever signal_type is rendered**

Add a display name map. Apply it everywhere signal_type appears on cards:

```javascript
const SIGNAL_TYPE_DISPLAY = {
    'PULLBACK_ENTRY': 'Pullback Entry',
    'RESISTANCE_REJECTION': 'Resistance Rejection',
    'TRAPPED_SHORTS': 'Trapped Shorts',
    'TRAPPED_LONGS': 'Trapped Longs',
    'TWO_CLOSE_VOLUME': 'Two Close Volume',
    'GOLDEN_TOUCH': 'Golden Touch',
    'DEATH_CROSS': 'Death Cross',
    'BEARISH_BREAKDOWN': 'Bearish Breakdown',
    'SELL_RIP_VWAP': 'Sell the Rip (VWAP)',
    'SELL_RIP_EMA': 'Sell the Rip (EMA)',
    'SCOUT_ALERT': 'Scout Alert',
    'FOOTPRINT_SHORT': 'Footprint Short',
    'FOOTPRINT_LONG': 'Footprint Long',
    'Session_Sweep': 'Session Sweep',
    'BULLISH_TRADE': 'Bullish Trade',
    'WHALE_LONG': 'Whale Long',
    'BEAR_CALL': 'Bear Call',
};

function displaySignalType(raw) {
    return SIGNAL_TYPE_DISPLAY[raw] || raw.replace(/_/g, ' ');
}
```

Use `displaySignalType(signal.signal_type)` in all card templates.

### P1C: Timing badge on Insight cards

**File: Frontend `app.js` — in the card rendering function**

Using the `range_consumed` value from triggering_factors (added in P1A), render
a colored dot at the start of the card header:

```javascript
function getTimingBadge(triggeringFactors) {
    const calc = triggeringFactors?.calculation || {};
    const rc = calc.range_consumed;
    if (rc === undefined || rc === null) return '';
    if (rc < 0.33) return '<span class="timing-dot early" title="Early catch">●</span>';
    if (rc < 0.60) return '<span class="timing-dot ontime" title="On time">●</span>';
    if (rc < 0.80) return '<span class="timing-dot late" title="Late">●</span>';
    return '<span class="timing-dot very-late" title="Very late — move mostly done">●</span>';
}
```

CSS (add to existing styles):
```css
.timing-dot { font-size: 10px; margin-right: 6px; }
.timing-dot.early { color: #97C459; }
.timing-dot.ontime { color: #85B7EB; }
.timing-dot.late { color: #FAC775; }
.timing-dot.very-late { color: #F09595; }
```

### P1D: Sub-strategy label on Insight cards

**File: Frontend `app.js` — card header area**

Replace the current display of `signal.strategy` ("CTA Scanner") with
the sub-strategy: `displaySignalType(signal.signal_type)`.

Keep the parent strategy as a smaller secondary label only if it adds info.
For CTA Scanner, the sub-strategy IS the useful info. The card header should read:
"Pullback Entry" not "CTA Scanner".

If a signal has confirming signals from a DIFFERENT strategy, show those as
small inline pills: `+1 Trapped Shorts` rather than a separate panel.

---

## P2: CONFLUENCE ENRICHMENT (connecting existing data)

### P2A: Sector momentum confluence factor

**File: Backend scoring engine**

At signal creation time, query the sector heatmap for the signal ticker's sector
ranking. The sector heatmap already calculates relative performance. Use two
lookback windows:

- 5-day relative strength ranking (1=best sector, 11=worst)
- 1-day relative strength ranking

Scoring:
- Sector ranked top 3 on BOTH 5-day AND 1-day: +5 bonus
- Sector ranked top 3 on 5-day only (fading today): +2
- Sector ranked bottom 3 on BOTH: -5 penalty
- Otherwise: 0

Add `sector_momentum_bonus` to triggering_factors.calculation. This replaces
the current `sector_rotation_bonus` if that's static/hardcoded.

Data source: The existing sector snapshot data in the `sector_constituents`
or sector heatmap tables. If this data is only in the frontend, add a backend
function to compute it from Polygon sector ETF daily returns.

### P2B: Squeeze score cross-reference

**File: Backend scoring engine**

When a CTA Scanner signal fires (especially Trapped Shorts or Trapped Longs),
query `squeeze_scores` for the ticker:

```python
async def get_squeeze_confluence(ticker: str) -> dict:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT composite_score, squeeze_tier, short_pct_float, "
            "days_to_cover FROM squeeze_scores WHERE ticker = $1", ticker
        )
        if not row:
            return {'squeeze_bonus': 0}
        cs = row['composite_score'] or 0
        if cs >= 30:  # high squeeze score
            return {'squeeze_bonus': 8, 'squeeze_tier': row['squeeze_tier'],
                    'short_float': row['short_pct_float']}
        elif cs >= 20:
            return {'squeeze_bonus': 4, 'squeeze_tier': row['squeeze_tier'],
                    'short_float': row['short_pct_float']}
        return {'squeeze_bonus': 0}
```

Add squeeze_bonus to the score calculation and store the data in
triggering_factors so the frontend can show a squeeze badge on the card.

NOTE: The squeeze_scores table currently has only 20 tickers. If the scanner
cron is working, it should cover all watchlist tickers. Check if the cron is
running — if not, that's a separate fix.

### P2C: Flow data cross-reference

**File: Backend scoring engine**

The flow_events table exists but is empty (1 smoke test row). The uw_snapshots
table has 0 rows. Before flow can be a confluence factor, the data pipeline
needs to work. This is a prerequisite check:

1. Is the UW flow watcher cron running on the VPS? Check `/opt/openclaw` for
   the flow scraping job. If not running, that's a VPS fix, not a Railway fix.

2. If flow_events IS populated (after the pipeline is fixed), add a flow
   confluence check at signal creation time:

```python
async def get_flow_confluence(ticker: str) -> dict:
    pool = await get_postgres_client()
    async with pool.acquire() as conn:
        # Check for flow events in the last 4 hours
        row = await conn.fetchrow(
            "SELECT flow_sentiment, total_premium, pc_ratio "
            "FROM flow_events WHERE ticker = $1 "
            "AND captured_at > NOW() - INTERVAL '4 hours' "
            "ORDER BY captured_at DESC LIMIT 1", ticker
        )
        if not row:
            return {'flow_bonus': 0}
        sentiment = row['flow_sentiment']
        premium = row['total_premium'] or 0
        # Bullish flow + LONG signal = aligned
        # High premium = institutional conviction
        bonus = 0
        if premium > 1_000_000:  # >$1M premium = significant
            bonus += 5
        # Sentiment alignment checked by caller
        return {'flow_bonus': bonus, 'flow_sentiment': sentiment,
                'flow_premium': premium}
```

For now, mark this as BLOCKED on the flow pipeline being operational. The
scoring engine should accept a flow_bonus of 0 gracefully (no impact) until
the pipeline is live.

---

## P3: INSIGHT CARD REDESIGN

### P3A: Time horizon classification

**File: Backend scoring engine — at signal creation time**

Add a `time_horizon` field to each signal based on signal_type and anchor level:

```python
HORIZON_MAP = {
    'TRAPPED_SHORTS': 'SPRINT',
    'TRAPPED_LONGS': 'SPRINT',
    'SELL_RIP_EMA': 'SPRINT',
    'SELL_RIP_VWAP': 'SPRINT',
    'GOLDEN_TOUCH': 'SPRINT',
    'Session_Sweep': 'SPRINT',
    'TWO_CLOSE_VOLUME': 'SWING',
    'RESISTANCE_REJECTION': 'SWING',
    'DEATH_CROSS': 'SWING',
    'BEARISH_BREAKDOWN': 'SWING',
}

def get_time_horizon(signal_type, anchor_level=None):
    if signal_type == 'PULLBACK_ENTRY':
        # Anchor-dependent: short MAs = sprint, long MAs = swing/position
        if anchor_level in ('8ema', '20ema', '8_ema', '20_ema'):
            return 'SPRINT'
        elif anchor_level in ('50sma', '50_sma', '50dma'):
            return 'SWING'
        elif anchor_level in ('200sma', '200_sma', '200dma', 'weekly'):
            return 'POSITION'
        return 'SWING'  # default for pullback
    return HORIZON_MAP.get(signal_type, 'SWING')
```

Store `time_horizon` in the signal record or in triggering_factors.

Display name mapping for the frontend:
- SPRINT → "Sprint (1-3d)" — lime green pill
- SWING → "Swing (5-14d)" — blue pill
- POSITION → "Position (2-4w)" — purple pill

### P3B: Compact card layout

**File: Frontend `app.js` — `createGroupedSignalCard()` or equivalent**

Replace the current multi-row card with a compact two-line format:

```
Line 1: [timing dot] TICKER ↑/↓    $entry_price    [score colored]
Line 2: Sub-Strategy • Time Horizon  +N conf  Xm ago
```

Things to REMOVE from the default card view:
- The text tier label (CRITICAL / HIGH / MEDIUM / LOW) — color the score instead
- The standalone confluence badge — show count inline as "+2 conf"
- The separate related signals panel — show as inline pills
- Stop loss and target prices — move behind tap/expand
- The strategy name when it's "CTA Scanner" — sub-strategy IS the label

Things to ADD:
- Timing dot (from P1C)
- Time horizon pill (SPRINT/SWING/POSITION from P3A)
- Direction arrow (↑ for long, ↓ for short) next to ticker

Things to KEEP:
- Accept button (primary action, prominent)
- Reject via swipe-left gesture OR small X button
- Analyze available on card tap (opens detail view)

The goal: 5-6 cards visible on mobile without scrolling (currently 2-3).

### P3C: Expanded detail view (on card tap)

When a compact card is tapped, expand to show the full detail panel:
- Entry, stop loss, target prices
- Score breakdown (base + each bonus factor as a horizontal bar)
- Confirming signals from other strategies (if any)
- Squeeze data (if available from P2B): short float %, days to cover, tier
- Flow sentiment (if available from P2C)
- Profile position (future, from P4)
- Full action buttons: Accept, Analyze (opens committee), Reject

---

## P4: PYTHIA INTEGRATION (market profile alerts)

### P4A: PineScript market profile indicator

**Platform: TradingView**

Create a PineScript indicator that calculates the developing daily value area
(VAH, VAL, POC) using volume profile. Set alerts for:

1. Price crossing below VAL → webhook to Hermes VPS endpoint
   - Tag: `pythia_val_cross_below`
   - Interpretation: potential long entry zone (institutional buying area)

2. Price crossing above VAH → webhook to Hermes VPS endpoint
   - Tag: `pythia_vah_cross_above`
   - Interpretation: price in extension, thin volume overhead

3. POC migration (optional, daily check): value area shifting directionally

Webhook URL: same Hermes endpoint (188.245.250.2:8000/api/hermes/trigger)
with a `source: pythia` field to distinguish from Hermes velocity alerts.

Apply to the full watchlist (200+ tickers). TradingView premium allows 400
alerts. Use 2 alerts per ticker (VAL cross + VAH cross) = 400 alerts max.

### P4B: Profile position scoring factor (FUTURE — after P4A is validated)

Once Pythia alerts are flowing into the VPS and stored in a `pythia_events`
table, add a `profile_position` factor to the scoring engine:

- Signal entry at or below VAL + LONG direction: +8 bonus
- Signal entry between VAL and POC: +3
- Signal entry between POC and VAH: 0
- Signal entry above VAH + LONG direction: -10 penalty
- (Invert for SHORT signals)

This is the same pattern as the squeeze and flow cross-references (P2B/P2C).

---

## OPERATIONAL FIX: Migration lock prevention

**File: Backend migration/startup code**

The signals table was completely locked for hours by a stuck ALTER TABLE
migration (`ADD COLUMN IF NOT EXISTS score DECIMAL(5,2)`) that ran on deploy
even though the column already exists. This blocked ALL reads and writes.

Fix:
1. Find the migration/DDL code that runs `ALTER TABLE signals ADD COLUMN IF
   NOT EXISTS score`. It's likely in `postgres_client.py` `init_database()`.
2. Either: (a) remove it if the column already exists, or (b) wrap it in a
   check that queries `information_schema.columns` FIRST and only runs the
   ALTER if the column is genuinely missing.
3. Add `SET lock_timeout = '5s'` before any ALTER TABLE so it fails fast
   instead of blocking the table indefinitely.
4. Add PostgreSQL config: `idle_in_transaction_session_timeout = '5min'`
   to auto-kill zombie connections that hold locks.
5. Add `statement_timeout = '30s'` as a server-level default to prevent
   runaway queries from accumulating.

---

## DUPLICATE SIGNAL DEDUPLICATION

When the same ticker fires multiple signals on the same day (e.g., 5 SPGI
sell_the_rip signals in 4 hours, 8 LOW signals in 5 hours), they should be
grouped into ONE Insight card, not 5-8 separate cards.

The existing dedup logic (Redis-based, from Brief 6A) should handle this. If
it's not working, check:
1. Is Redis running on Railway?
2. Is the dedup check wired into the CTA Scanner signal path?
3. Are sell_the_rip signals going through the same dedup pipeline?

The timing study showed that duplicate signals inflated the "actionable"
count for sell_the_rip (3 BKNG signals on the same day = 1 trade idea, not 3).

---

## DEFINITION OF DONE

### P1 (ship first):
- [ ] Freshness penalty applied to all new signals; range_consumed stored
- [ ] Signal type display names show English (no underscores)
- [ ] Timing badge (colored dot) visible on Insight cards
- [ ] Sub-strategy label shown as primary label on cards

### P2 (ship second):
- [ ] Sector momentum bonus/penalty active in scoring
- [ ] Squeeze score cross-referenced for Trapped Shorts/Longs signals
- [ ] Flow data pipeline status checked; flow_bonus wired (even if 0)

### P3 (ship third):
- [ ] Time horizon (Sprint/Swing/Position) calculated and displayed
- [ ] Compact two-line card layout deployed
- [ ] Expanded detail view on card tap

### P4 (ship when ready):
- [ ] PineScript profile indicator created and applied to watchlist
- [ ] Pythia webhook events stored in DB
- [ ] Profile position factor wired into scoring

### Operational:
- [ ] Migration lock bug fixed (ALTER TABLE with lock_timeout)
- [ ] idle_in_transaction_session_timeout set to 5min
- [ ] statement_timeout default set to 30s
