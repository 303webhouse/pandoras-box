# Brief 3C: Abacus UI Consolidation — Strategos, Chronicle, Symposium

## Summary

Consolidate the 6 existing analytics tabs into 3 focused surfaces with Greek-themed naming. Surface existing backend power that the frontend doesn't use. Add a persistent P&L header visible across all tabs.

Depends on Brief 3B (The Oracle) for the insights payload.

## Current State (6 tabs)

```
Dashboard | Trade Journal | Signal Explorer | Factor Lab | Backtest | Risk
```

## New State (3 tabs)

```
Strategos | Chronicle | Symposium
```

## Persistent P&L Header (Aegis Bar)

Visible across ALL three tabs. Always shows current system status:

```html
<div class="abacus-header">
    <div class="abacus-pnl">
        <span class="pnl-total positive">+$1,240</span>
        <span class="pnl-split">[Equity: +$890] [Crypto: +$350]</span>
    </div>
    <div class="abacus-metrics">
        <span>Win Rate: 54.8%</span>
        <span>Streak: W3</span>
        <span class="trajectory improving">▲ Improving</span>
    </div>
</div>
```

Data source: `GET /api/analytics/oracle` → `system_health` section.

Color coding:
- P&L positive = green, negative = red
- Trajectory IMPROVING = green arrow, DECLINING = red arrow, STABLE = gray dash
- Streak ≥ 3 wins = green highlight, ≥ 3 losses = red highlight

## Tab 1: Strategos (The General — Command Center)

**Purpose:** Forward-looking. "What's the current state and what can I do today?"

Replaces: Dashboard + Risk tabs.

### Content Sections:

#### 1a. The Oracle's Narrative
AI-generated summary from `/api/analytics/oracle` → `narrative`.
Displayed as a quote block with The Oracle attribution:
```html
<blockquote class="oracle-narrative">
    <p>"Holy Grail is your best performer this month (+$640, 6/8 wins).
    Session Sweep needs attention (1/4 wins). Your override rate is 18%
    and overrides are net-positive (+$35)."</p>
    <cite>— The Oracle</cite>
</blockquote>
```

#### 1b. Risk Budget (Aspis — The Shield)
Live risk exposure from `/api/analytics/risk-budget` (Brief 3A):

**Equity:**
- Open positions count
- Total max loss at risk
- Capital at risk %

**Crypto (Breakout):**
- Open positions (N / 2 max)
- Static DD remaining ($X of $1,500)
- Daily limit remaining ($X of $1,000)
- Can open new: YES/NO badge

Use progress bars for the Breakout limits — visually show how close to the edge.

#### 1c. Strategy Scorecards
From Oracle → `strategy_scorecards`. Display as compact cards:

```
[A] Holy Grail    8W/4L  +$390  Exp: $32.50
[B] CTA Scanner   5W/4L  +$120  Exp: $13.33
[C] Session Sweep 1W/3L  -$80   Exp: -$20.00
```

Grade badge color: A=green, B=blue, C=orange, F=red.
Sort by expectancy descending.

#### 1d. Health Alerts
From existing `/api/analytics/health-alerts`. Display as dismissible cards.

#### 1e. Current Regime Context
Show current bias regime (TORO/URSA/NEUTRAL level) and active circuit breakers.
Data from existing `/api/bias/composite`.

### Equity/Crypto Toggle
All Strategos sections support filtering. Default: combined. One-click to see equity-only or crypto-only. When filtered:
- Oracle narrative regenerates for that asset class (cached separately)
- Risk budget shows only relevant section
- Scorecards filter to relevant strategies

## Tab 2: Chronicle (Records of Time — Journal & Review)

**Purpose:** Backward-looking. "What happened and what did I learn?"

Replaces: Trade Journal tab.

### Content Sections:

#### 2a. Trade Log
Existing trade journal table, enhanced with:
- Signal origin column (which strategy generated it)
- Committee recommendation (TAKE/PASS/WATCHING if reviewed)
- Outcome (WIN/LOSS/BREAKEVEN)
- "Was this an override?" badge
- Options fields: structure, DTE at entry/exit, exit quality
- "What I learned" editable notes field per trade

#### 2b. Override Review (Prometheus Panel)
Dedicated section for committee override analysis.
From Oracle → `decision_quality`:
- Total overrides and override win rate
- Best/worst override trades
- "The committee was right X% of the time"

#### 2c. Counterfactuals (Cassandra's Mirror)
"Signals you passed on — what would have happened?"
From signals where `outcome LIKE 'COUNTERFACTUAL%'`:
- Show signals Nick dismissed that would have been winners
- Show signals Nick dismissed that would have been losers
- Net counterfactual P&L: "You saved $X by passing on losers, missed $Y by passing on winners"

#### 2d. Lessons (Sophia's Scroll)
From VPS lessons_bank.jsonl and/or a future `weekly_reports` table.
Displays distilled weekly lessons in reverse chronological order.

### Equity Curve
Retained from current dashboard. Show P&L over time with drawdown overlay.
Supports equity/crypto toggle.

## Tab 3: Symposium (Intellectual Gathering — Deep Dives)

**Purpose:** Analytical. "Where is my edge? How do I improve?"

Replaces: Signal Explorer + Factor Lab + Backtest tabs.

### Content Sections:

#### 3a. Signal Explorer (Hermes' Map)
Existing signal explorer — table of all signals with filtering.
Enhanced with:
- Outcome column (WIN/LOSS/COUNTERFACTUAL from Ariadne's Thread)
- Market structure context (for crypto signals)
- Quick filter: "Show only signals I took" / "Show only passed"

#### 3b. Factor Lab (Athena's Forge)
Existing factor performance, but reoriented per GPT's recommendation:
- **Primary view:** Factor value at signal time → trade outcome
- **Secondary view:** Factor vs SPY (demoted, still available)
- Correlation matrix between factors
- Factor timeline charts

Also surface `target_field` comparison from the backtest engine:
```
"Which target field matters? target_1 hit 68% of the time, target_2 only 34%"
```

#### 3c. Backtest Engine (Chronos' Sandbox)
Existing backtest UI — strategy simulation from historical signals.
Surface the comparison mode (backtest strategy A vs strategy B).
Surface the `skipped` signal analysis: "Signals the system generated but that were filtered out — how would they have done?"

#### 3d. Convergence Analysis (Syzygy)
Existing convergence stats. Show when multiple strategies fired on the same ticker/direction and what the combined outcome was.

## Implementation Notes

### HTML Structure
Replace the 6 `analytics-subtab` buttons in `frontend/index.html` (~lines 967-973) with 3:

```html
<section class="analytics-subtabs" role="tablist" aria-label="Abacus Views">
    <button class="analytics-subtab active" data-analytics-tab="strategos">Strategos</button>
    <button class="analytics-subtab" data-analytics-tab="chronicle">Chronicle</button>
    <button class="analytics-subtab" data-analytics-tab="symposium">Symposium</button>
</section>
```

Replace the 6 pane sections with 3 new ones.

### JavaScript
In `frontend/analytics.js`, restructure the tab loading:
- `loadStrategos()` → calls Oracle endpoint + risk-budget endpoint + health + regime
- `loadChronicle()` → calls trade-stats + signals with outcomes + counterfactuals
- `loadSymposium()` → calls signal-stats + factor-performance + backtest (on demand)

### CSS
Retain existing chart styling. Add Greek-themed section headers.

### Retiring Dead UI
- The separate Risk tab content gets absorbed into Strategos
- The standalone dashboard health cards get absorbed into Strategos
- Factor Lab standalone becomes a Symposium subsection
- Backtest standalone becomes a Symposium subsection

Check for any orphaned JS functions that only served the deleted tabs.

## Files Modified

| File | Change |
|------|--------|
| `frontend/index.html` | Replace 6 analytics tabs with 3, restructure pane content |
| `frontend/analytics.js` | Restructure tab loaders, add Oracle rendering, add equity/crypto toggle |
| `frontend/styles.css` | Add Oracle narrative styling, risk budget progress bars, Greek section headers |

## Definition of Done

- [ ] 3 tabs: Strategos, Chronicle, Symposium
- [ ] Persistent P&L header visible across all tabs
- [ ] The Oracle narrative displayed in Strategos
- [ ] Risk budget (Aspis) with Breakout progress bars in Strategos
- [ ] Strategy scorecards with letter grades in Strategos
- [ ] Trade log enhanced with signal origin, committee rec, outcome, override badge
- [ ] Override review panel (Prometheus) in Chronicle
- [ ] Counterfactual display (Cassandra's Mirror) in Chronicle
- [ ] Lessons display (Sophia's Scroll) in Chronicle
- [ ] Signal explorer with outcomes in Symposium
- [ ] Factor lab reoriented to outcome-linked in Symposium
- [ ] Backtest with comparison mode surfaced in Symposium
- [ ] Equity/crypto toggle on all views
- [ ] 6 old tabs retired, no orphaned JS functions
- [ ] All existing tests pass
