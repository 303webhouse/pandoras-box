# Brief 10 — Unified Position Ledger + Options Intelligence

**Priority:** HIGH — blocks accurate portfolio risk display, committee context, and usable position management
**Predecessor:** Replaces the fragmented position system (3 tables, 3 APIs, 3 UI panels)
**Owner:** Claude Code (Codex)

---

## Problem Statement

The trading hub has three disconnected position-tracking systems that were built incrementally across different briefs:

1. **Signal pipeline** (`positions` table) — created when accepting Trade Ideas. Equity-only, no options structure awareness. Frontend has duplicate renderers with race conditions and a null-reference bug that makes "Accept" show a false error.
2. **Brokerage sync** (`open_positions` table) — written by Pivot screenshot parsing. Has `short_strike` and `spread_type` fields but is display-only in the UI and disconnected from the signal pipeline.
3. **Options pipeline** (`options_positions` table) — separate API, separate UI tab, in-memory storage with inconsistent DB sync. Accepts user-provided max_loss but doesn't calculate it from spread structure.

Additionally, closing a position in system #1 never creates a record in the `trades` table (analytics journal), so the analytics dashboard is blind to positions managed through the hub unless they're double-entered via CSV import.

The committee's portfolio risk context uses `entry_price - stop_loss` for capital-at-risk, which is wrong for defined-risk spreads (should be spread width × contracts - premium).

**Result:** Nick sees two "OPEN POSITIONS" panels showing different data, can't reliably accept Trade Ideas, and the committee makes risk assessments based on incorrect numbers.

---

## Design Principles

1. **One table, one API, one UI panel** for all positions regardless of source (signal, manual, CSV, screenshot)
2. **Options-native** — spreads are first-class citizens with auto-calculated max loss from structure
3. **Two interfaces, one truth** — Frontend for quick single-trade CRUD (no LLM cost), Pivot for bulk operations (CSV, screenshots, natural language)
4. **Close → Trade** — closing a position automatically creates an analytics `trades` record. No double-entry.
5. **Committee awareness, not dominance** — agents see open positions as context but evaluate the trade setup on its own merits

---

## Phase A: Unified Backend

### A1. New `unified_positions` table schema

```sql
CREATE TABLE unified_positions (
    id              SERIAL PRIMARY KEY,
    position_id     TEXT UNIQUE NOT NULL,  -- e.g. "POS_NVDA_20260226_143022"

    -- What
    ticker          TEXT NOT NULL,
    asset_type      TEXT NOT NULL DEFAULT 'OPTION',  -- EQUITY, OPTION, SPREAD
    structure       TEXT,           -- "put_credit_spread", "long_call", "iron_condor", "stock", etc.
    direction       TEXT NOT NULL,  -- LONG, SHORT, MIXED (iron condor)
    legs            JSONB,          -- [{strike, short_strike, expiry, option_type, quantity, action}]

    -- Entry
    entry_price     NUMERIC,        -- net premium paid/received per unit
    entry_date      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    quantity        INTEGER NOT NULL DEFAULT 1,  -- contracts or shares
    cost_basis      NUMERIC,        -- total dollars committed

    -- Risk (auto-calculated for spreads, user-provided for equity)
    max_loss        NUMERIC,        -- auto-calc from spread width, or entry for debit, or user stop for equity
    max_profit      NUMERIC,        -- auto-calc from spread width, or unlimited for long options
    stop_loss       NUMERIC,        -- user's mental stop (optional for defined-risk)
    target_1        NUMERIC,
    target_2        NUMERIC,
    breakeven       NUMERIC[],      -- can have multiple for iron condors

    -- Current state
    current_price   NUMERIC,        -- last known price (manual update, yfinance, or screenshot)
    unrealized_pnl  NUMERIC,        -- computed from entry vs current
    price_updated_at TIMESTAMPTZ,   -- when current_price was last refreshed

    -- Options-specific
    expiry          DATE,           -- earliest expiry across legs (NULL for equity)
    dte             INTEGER,        -- computed: expiry - today (NULL for equity)
    long_strike     NUMERIC,        -- for spreads: the protective leg
    short_strike    NUMERIC,        -- for spreads: the risk leg

    -- Metadata
    source          TEXT NOT NULL DEFAULT 'MANUAL',  -- SIGNAL, MANUAL, CSV_IMPORT, SCREENSHOT_SYNC
    signal_id       TEXT,           -- FK to signals table if accepted from Trade Ideas
    account         TEXT DEFAULT 'ROBINHOOD',  -- ROBINHOOD, FIDELITY, etc.
    notes           TEXT,
    tags            TEXT[],         -- user tags for filtering

    -- Lifecycle
    status          TEXT NOT NULL DEFAULT 'OPEN',  -- OPEN, CLOSED, EXPIRED
    exit_price      NUMERIC,
    exit_date       TIMESTAMPTZ,
    realized_pnl    NUMERIC,
    trade_outcome   TEXT,           -- WIN, LOSS, BREAKEVEN, EXPIRED
    trade_id        INTEGER,        -- FK to trades table (created on close)

    -- Housekeeping
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_unified_positions_status ON unified_positions(status);
CREATE INDEX idx_unified_positions_ticker ON unified_positions(ticker);
CREATE INDEX idx_unified_positions_signal ON unified_positions(signal_id);
```

### A2. Max loss calculation engine

Pure function, no external dependencies. Used by API on position creation and by Pivot skill.

```python
def calculate_position_risk(structure: str, legs: list, entry_price: float, quantity: int) -> dict:
    """
    Returns {max_loss, max_profit, breakeven, direction} based on structure.

    Rules:
    - Long call/put (debit):           max_loss = premium_paid * qty * 100
    - Short naked call/put (credit):   max_loss = None (undefined — flag as high risk)
    - Vertical credit spread:          max_loss = (width - premium) * qty * 100
    - Vertical debit spread:           max_loss = premium_paid * qty * 100
    - Iron condor:                     max_loss = (wider_wing_width - total_premium) * qty * 100
    - Covered call:                    max_loss = (stock_price - premium) * qty * 100 (downside)
    - Cash-secured put:                max_loss = (strike - premium) * qty * 100
    - Stock long:                      max_loss = entry_price * quantity (or stop-based)
    - Stock short:                     max_loss = None (undefined — use stop if provided)

    Width = abs(long_strike - short_strike)
    """
```

### A3. Unified positions API

Replace the current 3 APIs with one clean set. All at `/api/v2/positions/`.

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/v2/positions` | GET | List positions. Query params: `status=OPEN`, `ticker=`, `account=` |
| `/api/v2/positions` | POST | Create position (manual or from signal accept). Auto-calculates max_loss. |
| `/api/v2/positions/{id}` | PATCH | Update fields (stop, target, current_price, notes). Recalculates unrealized_pnl. |
| `/api/v2/positions/{id}/close` | POST | Close position. Calculates realized P&L. Auto-creates `trades` record. |
| `/api/v2/positions/{id}` | DELETE | Remove position (for errors/test data). No trade record created. |
| `/api/v2/positions/mark-to-market` | POST | Fetch current prices via yfinance for all open positions. Update unrealized P&L. |
| `/api/v2/positions/bulk` | POST | Create/update multiple positions at once (used by CSV import and screenshot sync). |
| `/api/v2/positions/reconcile` | POST | Screenshot reconciliation: match incoming positions to existing, update/create/flag. |
| `/api/v2/positions/summary` | GET | Portfolio summary: total positions, capital at risk (sum of max_loss), net direction, nearest expiry. |

### A4. Close-to-trade bridge

When `POST /api/v2/positions/{id}/close` is called:

1. Calculate realized P&L from entry vs exit price, adjusted for debit/credit structure
2. Set `status = 'CLOSED'`, `exit_price`, `exit_date`, `realized_pnl`, `trade_outcome`
3. Create a `trades` table record with all fields mapped:
   - `trades.ticker` = position ticker
   - `trades.structure` = position structure
   - `trades.strike` / `trades.short_strike` = from position legs
   - `trades.entry_price` / `trades.exit_price` = from position
   - `trades.pnl_dollars` = realized_pnl
   - `trades.signal_source` = position source
   - `trades.opened_at` / `trades.closed_at` = position entry/exit dates
4. Store `trade_id` FK back on the position row
5. If position was from a signal (`signal_id` is set), update the `signals` record with outcome

This eliminates the need for separate trade logging or CSV import for positions managed through the hub.

### A5. Data migration

One-time migration script to move existing data from the 3 old tables into `unified_positions`:

1. `positions` WHERE status = 'OPEN' → migrate with `source = 'SIGNAL'`
2. `open_positions` WHERE is_active = TRUE → migrate with `source = 'SCREENSHOT_SYNC'`
3. `options_positions` WHERE status = 'OPEN' → migrate with `source = 'MANUAL'`
4. Deduplicate by (ticker, strike, expiry, direction) — prefer the record with more data
5. Keep old tables as read-only archives (don't delete)

### A6. Committee portfolio context fix

Update `fetch_portfolio_context()` in `committee_context.py` to:

1. Call `GET /api/v2/positions/summary` instead of separate portfolio/positions endpoints
2. Use `max_loss` for capital-at-risk calculation (not `entry_price - stop_loss`)
3. Show structure type per position so agents understand the risk profile

**New format for committee context:**
```
## PORTFOLIO CONTEXT
Account: $4,469 (Robinhood) | Cash: $2,868
Open: 4 positions | Capital at risk: $1,050 (23.5% of account) — sum of max losses
- XLF put credit spread 50/48 6/18 (5 contracts) — max loss $250, DTE 112
- GS put debit spread 740/730 5/15 (2 contracts) — max loss $400, DTE 78
- TSLA put credit spread 380/370 3/20 (2 contracts) — max loss $300, DTE 22
- PLTR short stock 5 shares @ $95 — stop at $105, risk $50
Nearest expiry: TSLA 3/20 (22 DTE)
Net lean: bearish (3 bearish, 1 neutral)
NOTE: Portfolio context is for awareness only. Evaluate this signal on its own setup quality.
```

**Committee prompt update** — Add to each agent's system prompt (TORO, URSA, TECHNICALS, PIVOT):
```
## Portfolio Context Rules
You will receive the trader's current open positions as context. Use this to:
- Note potential correlation (e.g., "you already hold 3 bearish SPY-correlated spreads")
- Flag concentration risk if > 40% of capital is in one direction or sector
- Note if a new position would push total capital at risk above 50%

Do NOT:
- Reject a setup primarily because it doesn't "fit" the current portfolio
- Assume the trader's existing thesis is correct — it may be wrong
- Weight portfolio fit more heavily than setup quality, technicals, or risk/reward
- Reduce conviction based on portfolio lean alone

The trader makes portfolio-level allocation decisions. Your job is to evaluate THIS setup.
```

---

## Phase B: Pivot Position Manager Skill

### B1. Skill document: `skills/positions/POSITION_MANAGER.md`

Deploy to VPS at `/opt/openclaw/workspace/skills/positions/POSITION_MANAGER.md`. This is Pivot's reference doc for all position management operations.

**Contents:**

#### CSV Upload Flow
```
When Nick uploads a Robinhood CSV:
1. POST the file to {PANDORA_API_URL}/analytics/parse-robinhood-csv
2. The parser returns grouped trades (opened, closed, open_positions)
3. Show Nick a summary:
   "Found 12 new trades (8 closed, 4 still open):
    Closed: SPY put spread +$150, NVDA call -$80, ...
    Open: XLF put spread 50/48 6/18 (5 contracts), ..."
4. On confirm ("import all"):
   - For each open position: POST to /api/v2/positions/bulk with structure, legs, entry
   - For each closed trade: POST to /api/v2/positions/bulk with full lifecycle (entry+exit)
   - Report: "Created 4 open positions, logged 8 closed trades to analytics"
```

#### Screenshot Flow
```
When Nick sends a Robinhood position screenshot:
1. Extract positions per RH_SCREENSHOT_RULES.md
2. POST to /api/v2/positions/reconcile with extracted positions
3. The API returns {matched, created, closed, conflicts}
4. Report to Nick:
   "Reconciled 4 positions:
    ✓ XLF put spread — updated value to $215 (+$40)
    ✓ GS put spread — updated value to $380 (-$20)
    + TSLA put spread 380/370 3/20 — NEW, added (max loss $300)
    ⚠ PLTR short stock — in hub but not in screenshot. Did it close?"
```

#### Manual Update Flow
```
When Nick says something like:
- "Closed my SPY spread for $1.20" → Match to open SPY spread position, POST /api/v2/positions/{id}/close
- "Move my NVDA stop to $185" → Match to open NVDA position, PATCH /api/v2/positions/{id}
- "Opened 3 XLF 50/48 put spreads for $0.45 credit, June expiry" → POST /api/v2/positions with structure auto-detected
- "What am I holding?" → GET /api/v2/positions?status=OPEN, format as readable summary
```

#### Options Intelligence Reference
```
CRITICAL: Understand defined risk vs. undefined risk.

SPREAD RISK RULES:
- A put credit spread (sell higher strike put, buy lower strike put) has max loss = (width × 100 × contracts) - premium received
  Example: Sell $50 put, buy $48 put for $0.35 credit, 5 contracts
  Width = $2, max loss = ($2 × 100 × 5) - ($0.35 × 100 × 5) = $1,000 - $175 = $825
  This is DEFINED RISK — the bought $48 put caps the loss. It is NOT a naked short put.

- A put debit spread (buy higher strike put, sell lower strike put) has max loss = premium paid
  Example: Buy $50 put, sell $48 put for $0.65 debit, 2 contracts
  Max loss = $0.65 × 100 × 2 = $130

- A call credit spread (sell lower strike call, buy higher strike call) has max loss = (width × 100 × contracts) - premium received

- A call debit spread (buy lower strike call, sell higher strike call) has max loss = premium paid

- An iron condor = call credit spread + put credit spread. Max loss = wider wing width × 100 × contracts - total premium

- A long call or long put: max loss = premium paid (debit position)
- A short naked call or put: max loss = UNDEFINED (flag as high risk, require stop loss)
- Stock: max loss = entry × shares (or stop-based if set)

DIRECTION RULES:
- "LONG" a put spread means BEARISH (you profit if price drops)
- "SHORT" a put spread means BULLISH (you profit if price stays above short strike)
- Credit spreads: you want the options to expire worthless (collect premium)
- Debit spreads: you want the options to move in your favor (sell for more than you paid)

RECORDING RULES:
- Always record both strikes for spreads (long_strike and short_strike)
- Always record expiry date
- Always calculate max_loss from structure — don't leave it blank
- entry_price = net premium per contract (positive for credit received, negative for debit paid)
- cost_basis = |entry_price| × 100 × quantity (total dollars)
```

### B2. Skill script: `skills/positions/manage.py`

A callable Python skill on VPS that Pivot can invoke for structured position operations. This handles the API calls so Pivot doesn't need to construct raw HTTP requests in conversation.

```python
"""
Pivot Position Manager skill.
Usage: python manage.py <command> [args]

Commands:
    list                    -- Show all open positions
    summary                 -- Portfolio risk summary
    open <json>             -- Open a new position
    close <position_id> <exit_price>  -- Close a position
    update <position_id> <field=value>  -- Update a position field
    mark-to-market          -- Refresh all prices via yfinance
    reconcile <json>        -- Screenshot reconciliation
    bulk <json>             -- Bulk create/update from CSV import
"""
```

---

## Phase C: Frontend + Cleanup

### C1. Fix existing bugs (do first, before any redesign)

1. **Null reference bug** — In `confirmPositionEntry()` ([app.js:7948](frontend/app.js#L7948)), save `pendingPositionSignal` to a local variable BEFORE calling `closePositionEntryModal()`:
   ```javascript
   const signal = pendingPositionSignal;  // save before modal close nulls it
   closePositionEntryModal();
   // ... use signal.ticker instead of pendingPositionSignal.ticker
   ```

2. **Kill duplicate renderer** — Delete `renderPositions()` and `loadOpenPositions()`. Replace all calls with `renderPositionsEnhanced()` / `loadOpenPositionsEnhanced()`. Merge `_open_positions_cache` into the single `openPositions` array.

3. **Remove double API call** — Page load currently calls `/api/positions/open` twice. Call `loadOpenPositionsEnhanced()` once from `loadInitialData()`.

### C2. Unified positions panel

Replace the two "OPEN POSITIONS" sections with one panel:

- **Heading:** "OPEN POSITIONS" (the only one)
- **Data source:** `GET /api/v2/positions?status=OPEN`
- **Position card shows:**
  - Ticker + structure badge (e.g., "SPY put credit spread")
  - Strikes + expiry + DTE countdown (e.g., "590/585 3/7 — 9 DTE")
  - Entry price, current price, unrealized P&L (color-coded green/red)
  - Max loss bar (visual: how much of max loss has been consumed)
  - Stop / Target levels
  - Quick actions: [Edit] [Close] [Remove]
- **Sort options:** DTE (default — soonest first), P&L, Ticker
- **"+ Add Position" button** — opens options-aware form

### C3. Options-aware manual entry form

When user clicks "+", the form should:

1. Ask for structure type (dropdown): Stock, Long Call, Long Put, Put Credit Spread, Put Debit Spread, Call Credit Spread, Call Debit Spread, Iron Condor, Custom
2. Based on structure, show relevant fields:
   - **Stock:** Ticker, Direction, Entry Price, Quantity, Stop, Target
   - **Single option:** Ticker, Strike, Expiry, Entry Premium, Quantity, Stop, Target
   - **Vertical spread:** Ticker, Long Strike, Short Strike, Expiry, Net Premium, Quantity
   - **Iron condor:** Ticker, Put Long Strike, Put Short Strike, Call Short Strike, Call Long Strike, Expiry, Net Premium, Quantity
3. Auto-calculate and display: Max Loss, Max Profit, Breakeven, Direction
4. On submit: POST to `/api/v2/positions`

### C4. Close position form

When user clicks "Close":
1. Show current position summary (what you're closing)
2. Ask for exit price (pre-fill with current_price if available)
3. Show calculated P&L before confirming: "Close for $0.80 credit → P&L: +$175 (WIN)"
4. On confirm: POST to `/api/v2/positions/{id}/close`
5. Position disappears from panel, trade record auto-created in analytics

### C5. Layout restructure — Portfolio into bias row

Move the portfolio widget from its separate `.portfolio-row` section into the `.bias-section` grid, creating a single unified top row.

**Target layout (all in one row, height = current Market Bias card):**
```
┌──────────────┬──────────┬──────────┬──────────┐
│              │          │  SWING   │  MACRO   │
│  MARKET BIAS │ INTRADAY ├──────────┴──────────┤
│              │          │     PORTFOLIO       │
└──────────────┴──────────┴─────────────────────┘
     col 1        col 2       col 3      col 4
      25%          25%              50%
```

**Grid rules:**
- `.bias-section` becomes a 4-column, 2-row grid: `grid-template-columns: 1fr 1fr 1fr 1fr; grid-template-rows: auto 1fr;`
- **Market Bias** (`.bias-composite-panel`): `grid-column: 1; grid-row: 1 / 3;` — spans both rows, full height
- **Intraday** (`.tf-card#tfIntraday`): `grid-column: 2; grid-row: 1 / 3;` — spans both rows, stretches to match Market Bias
- **Swing** (`.tf-card#tfSwing`): `grid-column: 3; grid-row: 1;`
- **Macro** (`.tf-card#tfMacro`): `grid-column: 4; grid-row: 1;`
- **Portfolio widget**: `grid-column: 3 / 5; grid-row: 2;` — spans columns 3-4, sits below Swing + Macro
- Swing row height + Portfolio row height = Market Bias height (use `grid-template-rows: auto 1fr` so Portfolio stretches to fill remaining space)

**HTML changes (`index.html`):**
1. Move the portfolio card (account balances + positions summary) from `.portfolio-row` into `.bias-section`, after the Macro tf-card
2. Delete the `.portfolio-row` section entirely
3. The unified positions panel (C2) stays in the main content area below — this portfolio card is the compact summary (account balance, position count, total capital at risk, nearest expiry)

**CSS changes (`styles.css`):**
1. Update `.bias-section` grid to support 2 rows
2. Add grid placement rules for each child element
3. Ensure Market Bias and Intraday cards stretch to full row height (`align-self: stretch`)
4. Portfolio card fills remaining height below Swing/Macro
5. Delete `.portfolio-row` styles
6. Responsive: at `max-width: 768px`, stack everything vertically (single column)

**Portfolio card content (compact summary for the bias row):**
- Account balance total (from existing `/api/portfolio/balances`)
- Open position count
- Total capital at risk (sum of max_loss across open positions)
- Capital at risk % of account
- Nearest expiry + DTE countdown
- Net direction lean (bullish/bearish/neutral)
- No individual position rows — those live in the full unified panel (C2) in the main content area below

### C6. Remove old position panels

Delete the separate "OPEN POSITIONS" portfolio table that was in `.portfolio-row` (now absorbed into C5). Remove the old lower "OPEN POSITIONS" panel from the main content area — replaced by the unified panel (C2). The old `/api/portfolio/positions` endpoint stays alive for backward compatibility (committee context still calls it until Phase A6 is deployed) but is no longer rendered in the frontend.

### C7. Accept from Trade Ideas flow

Update the signal accept flow to create a unified position:

1. User clicks "Accept" on a Trade Idea card
2. Modal pre-fills from signal data: ticker, direction, entry, stop, target
3. User selects structure type (the committee's STRUCTURE recommendation is shown as a suggestion)
4. If spread selected: fill in strikes, expiry, premium
5. On confirm: POST to `/api/v2/positions` with `source = 'SIGNAL'` and `signal_id`
6. Position appears in the unified panel

---

## Files to Create/Modify

### New files
| File | Purpose |
|------|---------|
| `backend/api/unified_positions.py` | New v2 positions API |
| `backend/models/position_risk.py` | Max loss calculation engine |
| `backend/migrations/010_unified_positions.sql` | Schema migration |
| `backend/migrations/011_migrate_position_data.py` | Data migration script |
| `skills/positions/POSITION_MANAGER.md` | Pivot skill reference doc (deploy to VPS) |
| `skills/positions/manage.py` | Pivot callable skill script (deploy to VPS) |

### Modified files
| File | Changes |
|------|---------|
| `backend/main.py` | Register v2 positions router |
| `backend/api/positions.py` | Mark old endpoints as deprecated (keep working for backward compat) |
| `backend/api/options_positions.py` | Mark as deprecated |
| `frontend/app.js` | Fix null ref bug, kill duplicate renderer, rebuild positions panel, new entry/close forms |
| `frontend/index.html` | Move portfolio card into bias-section grid, remove old portfolio-row and duplicate OPEN POSITIONS, update panel HTML |
| `frontend/styles.css` | Restructure `.bias-section` to 4-col 2-row grid, add grid placement rules, delete `.portfolio-row` styles |
| `scripts/committee_context.py` | Update `fetch_portfolio_context()` to use v2 API and max_loss for risk |
| `scripts/committee_prompts.py` | Add portfolio context rules to all 4 agent prompts |
| `scripts/pivot2_committee.py` | Update portfolio context injection |

---

## Build Order

1. **Phase A1-A3**: Schema + risk calculator + new API (can be tested independently)
2. **Phase C1**: Fix existing bugs in app.js (quick wins, independent of backend changes)
3. **Phase A4**: Close-to-trade bridge
4. **Phase A5**: Data migration
5. **Phase C2-C4**: Frontend rebuild — unified positions panel, entry form, close form (depends on A1-A3 being live)
6. **Phase C5**: Layout restructure — move portfolio card into bias-section grid
7. **Phase C6-C7**: Remove old panels, update accept flow
8. **Phase A6**: Committee context fix (depends on A1-A3 being live)
9. **Phase B**: Pivot skill (depends on A1-A3 being live, can parallel with C2-C7)

---

## Verification

1. Create a position manually via frontend → appears in unified panel with correct max loss
2. Close a position via frontend → trade record appears in analytics journal
3. Accept a Trade Idea → creates unified position with signal linkage
4. Upload CSV via Pivot → positions created/closed correctly with spread detection
5. Screenshot via Pivot → reconciles against existing positions, updates values
6. Committee run → portfolio context shows correct max_loss-based capital at risk
7. Committee run → agents note portfolio but focus on setup quality
8. Mark-to-market → all positions get refreshed prices from yfinance

---

## What This Does NOT Do

- **No Robinhood API integration** — position updates come from manual entry, CSV, or screenshots
- **No live options pricing** — current_price is updated manually, via screenshot, or via yfinance (equity underlying only for options)
- **No auto-detection of closed positions** — Nick tells the system when positions close (via frontend, Pivot, or screenshot reconciliation)
- **No Greeks tracking in the unified system** — the old options_positions API tracked delta/gamma/theta/vega but this was rarely accurate without live data. The unified system focuses on what matters: max loss, P&L, DTE
- **No deletion of old tables** — `positions`, `open_positions`, `options_positions` stay as read-only archives
