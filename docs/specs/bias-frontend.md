# Bias Frontend — Implementation Spec
**Status:** Ready to build
**Depends on:** `composite-bias-engine.md` (API it reads from)
**Estimated effort:** ~200 lines of JS + CSS updates

## What This Does
Replaces the current single-indicator bias display with a composite bias dashboard that shows the overall bias level, all contributing factors, confidence level, and staleness warnings.

## Current State
The frontend (`frontend/app.js`) has bias cards that show the 5-level system (URSA MAJOR → TORO MAJOR) with accent colors. It currently reads from `/api/bias/{timeframe}` which only returns Savita-based data.

## New State
The bias section reads from `GET /api/bias/composite` and displays:
1. **Primary bias level** — large, prominent, color-coded
2. **Composite score** — numeric (-1.0 to +1.0)
3. **Confidence badge** — HIGH / MEDIUM / LOW
4. **Factor breakdown** — expandable list of all 8 factors with individual scores
5. **Override indicator** — visible when manual override is active
6. **Pivot health** — small indicator showing if data collector is alive

---

## API Endpoint
**GET /api/bias/composite** — returns the CompositeResult JSON (see `composite-bias-engine.md`)

**WebSocket message type:** `BIAS_UPDATE` — triggers a re-render when bias changes

---

## UI Layout

```
┌──────────────────────────────────────────────────────────┐
│  MARKET BIAS                                    ● Pivot  │
│                                                 ● Live   │
│  ████████████████████████████████████████████            │
│  █        URSA MAJOR  (-0.68)               █   HIGH    │
│  ████████████████████████████████████████████  confidence│
│                                                          │
│  ▸ Factor Breakdown (7/8 active)                        │
│  ┌────────────────────────────────────────────────────┐  │
│  │ ● Credit Spreads    ████████░░  -0.50  URSA MINOR │  │
│  │ ● Market Breadth    █████████░  -0.80  URSA MAJOR │  │
│  │ ● VIX Term          █████████░  -0.60  URSA MAJOR │  │
│  │ ● TICK Breadth      █████████░  -0.80  URSA MAJOR │  │
│  │ ● Sector Rotation   ██████████  -0.90  URSA MAJOR │  │
│  │ ● Dollar Smile      ██████░░░░  -0.40  URSA MINOR │  │
│  │ ● Excess CAPE       ████████░░  -0.50  URSA MINOR │  │
│  │ ○ Savita            ░░░░░░░░░░  STALE  (45d ago)  │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  [Override Bias ▾]              Last update: 2 min ago   │
└──────────────────────────────────────────────────────────┘
```

---

## Color Mapping (matches existing dark teal theme)

```javascript
const BIAS_COLORS = {
    TORO_MAJOR: { bg: "#0a2e1a", accent: "#00e676", text: "#00e676" },
    TORO_MINOR: { bg: "#1a2e1a", accent: "#66bb6a", text: "#66bb6a" },
    NEUTRAL:    { bg: "#1a2228", accent: "#78909c", text: "#78909c" },
    URSA_MINOR: { bg: "#2e1a0a", accent: "#ff9800", text: "#ff9800" },
    URSA_MAJOR: { bg: "#2e0a0a", accent: "#f44336", text: "#f44336" },
};

const CONFIDENCE_COLORS = {
    HIGH:   "#00e676",
    MEDIUM: "#ff9800",
    LOW:    "#f44336",
};
```

---

## JavaScript Implementation

### Fetching Composite Bias
```javascript
async function fetchCompositeBias() {
    try {
        const resp = await fetch("/api/bias/composite");
        const data = await resp.json();
        renderBiasDisplay(data);
    } catch (err) {
        console.error("Failed to fetch composite bias:", err);
        showBiasError();
    }
}
```

### Rendering
```javascript
function renderBiasDisplay(data) {
    const container = document.getElementById("bias-section");
    const colors = BIAS_COLORS[data.bias_level];
    
    // Primary bias banner
    const banner = container.querySelector(".bias-banner");
    banner.style.background = colors.bg;
    banner.style.borderColor = colors.accent;
    banner.querySelector(".bias-level").textContent = data.bias_level.replace("_", " ");
    banner.querySelector(".bias-level").style.color = colors.accent;
    banner.querySelector(".bias-score").textContent = `(${data.composite_score.toFixed(2)})`;
    
    // Confidence badge
    const conf = container.querySelector(".confidence-badge");
    conf.textContent = data.confidence;
    conf.style.color = CONFIDENCE_COLORS[data.confidence];
    
    // Override indicator
    const override = container.querySelector(".override-indicator");
    if (data.override) {
        override.style.display = "block";
        override.textContent = `⚡ Override active: ${data.override}`;
    } else {
        override.style.display = "none";
    }
    
    // Factor breakdown
    const factorList = container.querySelector(".factor-list");
    factorList.innerHTML = "";
    
    const factorOrder = [
        "credit_spreads", "market_breadth", "vix_term", "tick_breadth",
        "sector_rotation", "dollar_smile", "excess_cape", "savita"
    ];
    
    for (const factorId of factorOrder) {
        const factor = data.factors[factorId];
        const isActive = data.active_factors.includes(factorId);
        const isStale = data.stale_factors.includes(factorId);
        
        const row = document.createElement("div");
        row.className = `factor-row ${isStale ? "stale" : ""}`;
        
        // Score bar (0-100% width, colored by score)
        const barPct = factor ? Math.abs(factor.score) * 100 : 0;
        const barColor = !factor ? "#455a64" :
            factor.score <= -0.6 ? "#f44336" :
            factor.score <= -0.2 ? "#ff9800" :
            factor.score >= 0.6 ? "#00e676" :
            factor.score >= 0.2 ? "#66bb6a" : "#78909c";
        
        row.innerHTML = `
            <span class="factor-status">${isActive ? "●" : "○"}</span>
            <span class="factor-name">${formatFactorName(factorId)}</span>
            <div class="factor-bar">
                <div class="factor-bar-fill" style="width:${barPct}%;background:${barColor}"></div>
            </div>
            <span class="factor-score">${factor && isActive ? factor.score.toFixed(2) : "STALE"}</span>
            <span class="factor-signal" style="color:${barColor}">${factor && isActive ? factor.signal.replace("_", " ") : "—"}</span>
        `;
        
        // Click to expand detail
        if (factor && factor.detail) {
            row.title = factor.detail;
            row.style.cursor = "pointer";
            row.addEventListener("click", () => {
                const detail = row.querySelector(".factor-detail");
                if (detail) {
                    detail.remove();
                } else {
                    const d = document.createElement("div");
                    d.className = "factor-detail";
                    d.textContent = factor.detail;
                    row.appendChild(d);
                }
            });
        }
        
        factorList.appendChild(row);
    }
    
    // Last update timestamp
    const timeAgo = getTimeAgo(new Date(data.timestamp));
    container.querySelector(".last-update").textContent = `Last update: ${timeAgo}`;
}
```

### WebSocket Handler
```javascript
// Add to existing WebSocket message handler in app.js
case "BIAS_UPDATE":
    renderBiasDisplay(msg.data);
    // Flash the bias banner briefly to draw attention
    flashElement(document.querySelector(".bias-banner"), msg.data.bias_level);
    break;
```

### Override Controls
```javascript
async function overrideBias(level) {
    const reason = prompt("Reason for override:");
    if (!reason) return;
    
    await fetch("/api/bias/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            level: level,
            reason: reason,
            expires_hours: 24,
        }),
    });
    
    fetchCompositeBias();  // Refresh display
}

async function clearOverride() {
    await fetch("/api/bias/override", { method: "DELETE" });
    fetchCompositeBias();
}
```

---

## CSS Additions

```css
/* Bias Section */
.bias-banner {
    border: 2px solid;
    border-radius: 8px;
    padding: 16px 20px;
    margin-bottom: 12px;
    transition: all 0.3s ease;
}

.bias-level {
    font-size: 24px;
    font-weight: 800;
    font-family: 'JetBrains Mono', monospace;
    letter-spacing: 1px;
}

.bias-score {
    font-size: 14px;
    color: #78909c;
    margin-left: 8px;
}

.confidence-badge {
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1px;
    padding: 2px 8px;
    border-radius: 4px;
    background: rgba(255,255,255,0.05);
}

.factor-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.factor-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    background: rgba(255,255,255,0.02);
    border-radius: 4px;
    font-size: 12px;
    font-family: 'JetBrains Mono', monospace;
}

.factor-row.stale {
    opacity: 0.4;
}

.factor-status {
    font-size: 8px;
}

.factor-name {
    width: 130px;
    color: #c8d6e0;
}

.factor-bar {
    flex: 1;
    height: 4px;
    background: rgba(255,255,255,0.06);
    border-radius: 2px;
}

.factor-bar-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 0.5s ease;
}

.factor-score {
    width: 45px;
    text-align: right;
    color: #78909c;
}

.factor-signal {
    width: 90px;
    text-align: right;
    font-size: 10px;
    font-weight: 700;
}

.factor-detail {
    width: 100%;
    font-size: 11px;
    color: #78909c;
    padding: 4px 0 0 20px;
    margin-top: 4px;
    border-top: 1px solid rgba(255,255,255,0.05);
}

.override-indicator {
    font-size: 11px;
    color: #ff9800;
    padding: 4px 8px;
    background: rgba(255,152,0,0.1);
    border-radius: 4px;
    margin-bottom: 8px;
}

.pivot-health {
    font-size: 10px;
    display: flex;
    align-items: center;
    gap: 4px;
}

.pivot-health.online { color: #00e676; }
.pivot-health.offline { color: #f44336; }

.last-update {
    font-size: 10px;
    color: #546e7a;
    text-align: right;
}

/* Flash animation when bias changes */
@keyframes bias-flash {
    0% { box-shadow: 0 0 20px rgba(244,67,54,0.5); }
    100% { box-shadow: none; }
}

.bias-banner.flash {
    animation: bias-flash 1.5s ease-out;
}
```

---

## Pivot Health Display

Add a small indicator in the bias section header:

```javascript
async function checkPivotHealth() {
    try {
        const resp = await fetch("/api/bias/health");
        const data = await resp.json();
        const indicator = document.querySelector(".pivot-health");
        
        const lastHeartbeat = new Date(data.last_heartbeat);
        const minutesAgo = (Date.now() - lastHeartbeat) / 60000;
        
        if (minutesAgo < 30) {
            indicator.className = "pivot-health online";
            indicator.innerHTML = "● Pivot live";
        } else {
            indicator.className = "pivot-health offline";
            indicator.innerHTML = "● Pivot offline (" + Math.round(minutesAgo) + "m)";
        }
    } catch {
        document.querySelector(".pivot-health").className = "pivot-health offline";
        document.querySelector(".pivot-health").innerHTML = "● Pivot unknown";
    }
}

// Check every 5 minutes
setInterval(checkPivotHealth, 300000);
checkPivotHealth();
```

---

## Dynamic Accent Color (Existing Feature)

The existing frontend already changes accent colors based on bias level. This should continue to work — just point it at the new composite data:

```javascript
// Existing accent color logic — update the data source
function updateAccentColor(biasLevel) {
    const root = document.documentElement;
    const colors = BIAS_COLORS[biasLevel];
    root.style.setProperty("--accent-color", colors.accent);
    root.style.setProperty("--accent-bg", colors.bg);
}
```

---

## Build Checklist

- [ ] Add HTML structure for composite bias section in `frontend/index.html`
- [ ] Add CSS styles to `frontend/styles.css`
- [ ] Add `renderBiasDisplay()` function to `frontend/app.js`
- [ ] Add WebSocket handler for `BIAS_UPDATE` message type
- [ ] Add override dropdown with all 5 bias levels + clear option
- [ ] Add Pivot health indicator
- [ ] Add factor detail expand/collapse on click
- [ ] Test with mock data (hardcoded JSON) before connecting to live API
- [ ] Verify dynamic accent colors still work with new data source
- [ ] Mobile responsive: factor bars should stack vertically on small screens
