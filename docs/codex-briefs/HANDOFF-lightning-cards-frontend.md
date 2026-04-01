# CC HANDOFF: Lightning Cards — Frontend Build
## Date: 2026-04-01 | Priority: P1
## Depends on: Hermes Flash + Hydra Squeeze (both deployed)

---

## WHAT'S ALREADY DONE

| Component | Status |
|-----------|--------|
| `lightning_cards` DB table | ✅ Created in Railway Postgres |
| `GET /api/hydra/lightning` endpoint | ✅ In `backend/api/hydra.py` |
| `PATCH /api/hydra/lightning/{id}/status` endpoint | ✅ In `backend/api/hydra.py` |
| Lightning Card INSERT on convergence | ✅ In `backend/webhooks/hermes.py` |
| Position classification (CONFIRMING/OPPOSING/UNRELATED) | ✅ In `backend/webhooks/hermes.py` |
| Correlated ETF detection (MRVL→SMH, COIN→IBIT, etc.) | ✅ In `backend/webhooks/hermes.py` |
| Pivot analysis populates Lightning Card headline | ✅ In `backend/webhooks/hermes.py` |
| Migration script | ✅ `scripts/migrate_lightning.py` |

## WHAT NEEDS BUILDING

All frontend. Three pieces in `frontend/app.js` and `frontend/styles.css`:

---

### 1. Lightning Card CSS — add to `frontend/styles.css`

```css
/* === LIGHTNING CARDS === */

.lightning-card {
    position: relative;
    border-radius: 6px;
    padding: 12px 14px;
    margin-bottom: 10px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    background: rgba(0,0,0,0.4);
    overflow: hidden;
    animation: lightning-border-pulse 2s ease-in-out infinite;
}

.lightning-card.bullish {
    border: 1.5px solid #00e676;
    box-shadow: 0 0 8px rgba(0, 230, 118, 0.15);
}
.lightning-card.bearish {
    border: 1.5px solid #ff9800;
    box-shadow: 0 0 8px rgba(255, 152, 0, 0.15);
}

@keyframes lightning-border-pulse {
    0%, 100% { opacity: 1; filter: brightness(1); }
    50% { opacity: 0.8; filter: brightness(1.3); }
}

.lightning-card.expired {
    animation: none;
    opacity: 0.4;
    border-color: rgba(255,255,255,0.15);
    box-shadow: none;
}

.lightning-icon {
    width: 20px;
    height: 20px;
    flex-shrink: 0;
    animation: lightning-icon-pulse 2s ease-in-out infinite;
}
.lightning-card.expired .lightning-icon { animation: none; opacity: 0.3; }

@keyframes lightning-icon-pulse {
    0%, 100% { opacity: 1; transform: scale(1); }
    50% { opacity: 0.7; transform: scale(1.08); }
}

.lightning-header {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
}
.lightning-ticker { font-size: 16px; font-weight: 700; }

.lightning-direction-badge {
    padding: 2px 8px;
    border-radius: 3px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}
.lightning-direction-badge.bullish { background: rgba(0, 230, 118, 0.2); color: #00e676; }
.lightning-direction-badge.bearish { background: rgba(255, 152, 0, 0.2); color: #ff9800; }

.lightning-countdown { margin-left: auto; font-size: 11px; opacity: 0.7; }
.lightning-countdown.urgent { color: #ff9800; opacity: 1; }
.lightning-countdown.critical { color: #f44336; opacity: 1; font-weight: 700; }

.lightning-catalyst {
    font-size: 11px;
    margin-bottom: 8px;
    padding: 4px 8px;
    background: rgba(255,255,255,0.04);
    border-radius: 3px;
    color: rgba(255,255,255,0.8);
    font-style: italic;
}

.lightning-squeeze-stats {
    display: flex;
    gap: 12px;
    margin-bottom: 8px;
    font-size: 11px;
}
.lightning-stat { display: flex; flex-direction: column; align-items: center; }
.lightning-stat-label { opacity: 0.5; font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px; }
.lightning-stat-value { font-weight: 700; font-size: 13px; }

.lightning-thesis {
    font-size: 11px;
    padding: 4px 8px;
    border-radius: 3px;
    margin-bottom: 6px;
}
.lightning-card.bullish .lightning-thesis { background: rgba(0,230,118,0.06); border-left: 2px solid rgba(0,230,118,0.3); }
.lightning-card.bearish .lightning-thesis { background: rgba(255,152,0,0.06); border-left: 2px solid rgba(255,152,0,0.3); }

.lightning-confirming {
    background: rgba(0, 230, 118, 0.1);
    border: 1px solid rgba(0, 230, 118, 0.3);
    border-radius: 3px;
    padding: 4px 8px;
    margin-bottom: 6px;
    font-size: 11px;
    color: #00e676;
}

.lightning-opposing {
    background: rgba(244, 67, 54, 0.12);
    border: 1px solid rgba(244, 67, 54, 0.3);
    border-radius: 3px;
    padding: 4px 8px;
    margin-bottom: 6px;
    font-size: 11px;
    color: #f44336;
}

.lightning-action-hint {
    margin-top: 3px;
    font-size: 10px;
    font-style: italic;
    opacity: 0.8;
}

.lightning-dismiss {
    position: absolute;
    top: 6px;
    right: 6px;
    background: none;
    border: 1px solid rgba(255,255,255,0.15);
    color: rgba(255,255,255,0.5);
    cursor: pointer;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 10px;
}
.lightning-dismiss:hover { background: rgba(255,255,255,0.1); color: white; }

.lightning-postmortem {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    font-size: 14px;
    font-weight: 700;
    flex-direction: column;
    gap: 4px;
}
.lightning-postmortem .missed-pnl.positive { color: #00e676; }
.lightning-postmortem .missed-pnl.negative { color: #f44336; }
```

---

### 2. Lightning Card JavaScript — add to `frontend/app.js`

Add this block near the Hydra section (around line 12000+ where the Hydra code lives).

```javascript
// === LIGHTNING CARDS — Frontend Logic ===

const _lightningCardsSounded = new Set();
let lightningPollingInterval = null;

function initLightningCards() {
    lightningPollingInterval = setInterval(fetchLightningCards, 10000);
    fetchLightningCards();
}

async function fetchLightningCards() {
    try {
        const resp = await fetch(`${API_URL}/hydra/lightning?active_only=true&limit=3`, {
            headers: getHeaders()
        });
        if (!resp.ok) return;
        const data = await resp.json();
        renderLightningCards(data.lightning_cards || []);
    } catch (err) {
        console.error('Lightning card fetch error:', err);
    }
}

function renderLightningCards(cards) {
    const container = document.getElementById('tradeSignals');
    if (!container) return;

    // Remove existing lightning cards
    container.querySelectorAll('.lightning-card').forEach(el => el.remove());

    if (cards.length === 0) return;

    // Insert at top of container, before existing signal cards
    const firstChild = container.firstChild;

    cards.forEach(card => {
        const cardEl = createLightningCard(card);

        // Only play thunder for cards we haven't seen before
        if (!_lightningCardsSounded.has(card.id) && card.status === 'active') {
            playThunderSound();
            _lightningCardsSounded.add(card.id);
        }

        container.insertBefore(cardEl, firstChild);
    });
}

function createLightningCard(card) {
    const dir = card.direction || 'bullish';
    const color = dir === 'bullish' ? '#00e676' : '#ff9800';
    const isExpired = card.status === 'expired';

    // Calculate countdown
    const createdAt = new Date(card.created_at);
    const ageMinutes = Math.floor((Date.now() - createdAt.getTime()) / 60000);
    let countdownClass = '';
    if (ageMinutes > 90) countdownClass = 'critical';
    else if (ageMinutes > 60) countdownClass = 'urgent';

    // Lightning bolt SVG — color matches direction
    const lightningSvg = `<svg class="lightning-icon" viewBox="0 0 24 24" fill="${color}" xmlns="http://www.w3.org/2000/svg">
        <path d="M13 2L3 14h8l-1 8 10-12h-8l1-8z" stroke="${color}" stroke-width="0.5" stroke-linejoin="round"/>
    </svg>`;

    // Position relationship display
    let relationshipHtml = '';
    if (card.position_relationship === 'CONFIRMING') {
        relationshipHtml = `<div class="lightning-confirming">✅ CONFIRMING: ${card.related_position_details || 'Aligns with existing position'}
            <div class="lightning-action-hint">${card.action_hint || 'Thesis accelerating — manage your winner'}</div>
        </div>`;
    } else if (card.position_relationship === 'OPPOSING') {
        relationshipHtml = `<div class="lightning-opposing">⚠️ OPPOSING: ${card.related_position_details || 'Works against existing position'}
            <div class="lightning-action-hint">${card.action_hint || 'Position at risk — consider hedging'}</div>
        </div>`;
    }

    // Thesis impact
    let thesisHtml = '';
    if (card.thesis_impact) {
        thesisHtml = `<div class="lightning-thesis"><strong>Thesis:</strong> ${card.thesis_impact}</div>`;
    }

    // Post-mortem overlay for expired cards
    let postmortemHtml = '';
    if (isExpired && card.actual_move_pct !== null && card.actual_move_pct !== undefined) {
        const move = parseFloat(card.actual_move_pct || 0);
        postmortemHtml = `
            <div class="lightning-postmortem">
                <div style="font-size:11px; opacity:0.7;">EXPIRED — ${card.ticker} moved ${move >= 0 ? '+' : ''}${move.toFixed(1)}%</div>
            </div>
        `;
    }

    const div = document.createElement('div');
    div.className = `lightning-card ${dir} ${isExpired ? 'expired' : ''}`;
    div.setAttribute('data-card-id', card.id);
    div.innerHTML = `
        <button class="lightning-dismiss" onclick="dismissLightningCard('${card.id}')" title="Dismiss">✕</button>

        <div class="lightning-header">
            ${lightningSvg}
            <span class="lightning-ticker" style="color:${color}">${card.ticker}</span>
            <span class="lightning-direction-badge ${dir}">SQUEEZE ${dir === 'bullish' ? 'LONG' : 'SHORT'}</span>
            <span class="lightning-countdown ${countdownClass}">${ageMinutes}m ago</span>
        </div>

        <div class="lightning-catalyst">${card.catalyst_headline || 'Velocity breach + elevated squeeze score'}</div>

        <div class="lightning-squeeze-stats">
            <div class="lightning-stat">
                <span class="lightning-stat-label">Score</span>
                <span class="lightning-stat-value">${parseFloat(card.squeeze_composite_score || 0).toFixed(0)}/100</span>
            </div>
            <div class="lightning-stat">
                <span class="lightning-stat-label">Tier</span>
                <span class="lightning-stat-value">${(card.squeeze_tier || 'low').toUpperCase()}</span>
            </div>
        </div>

        ${thesisHtml}
        ${relationshipHtml}
        ${postmortemHtml}
    `;

    // Start countdown updater for active cards
    if (!isExpired) {
        const countdownEl = div.querySelector('.lightning-countdown');
        if (countdownEl) {
            setInterval(() => {
                const now = Date.now();
                const age = Math.floor((now - createdAt.getTime()) / 60000);
                countdownEl.textContent = `${age}m ago`;
                countdownEl.className = 'lightning-countdown';
                if (age > 90) countdownEl.classList.add('critical');
                else if (age > 60) countdownEl.classList.add('urgent');
            }, 30000);
        }
    }

    return div;
}

function playThunderSound() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();

        // Low rumble (80Hz)
        const rumble = ctx.createOscillator();
        const rumbleGain = ctx.createGain();
        rumble.type = 'sine';
        rumble.frequency.value = 80;
        rumbleGain.gain.setValueAtTime(0.15, ctx.currentTime);
        rumbleGain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 1.5);
        rumble.connect(rumbleGain);
        rumbleGain.connect(ctx.destination);
        rumble.start();
        rumble.stop(ctx.currentTime + 1.5);

        // Mid crack (120Hz sawtooth)
        const crack = ctx.createOscillator();
        const crackGain = ctx.createGain();
        crack.type = 'sawtooth';
        crack.frequency.value = 120;
        crackGain.gain.setValueAtTime(0.08, ctx.currentTime);
        crackGain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
        crack.connect(crackGain);
        crackGain.connect(ctx.destination);
        crack.start();
        crack.stop(ctx.currentTime + 0.5);

        // Sharp attack (300Hz burst)
        const attack = ctx.createOscillator();
        const attackGain = ctx.createGain();
        attack.type = 'square';
        attack.frequency.value = 300;
        attackGain.gain.setValueAtTime(0.06, ctx.currentTime);
        attackGain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);
        attack.connect(attackGain);
        attackGain.connect(ctx.destination);
        attack.start();
        attack.stop(ctx.currentTime + 0.2);
    } catch (e) { /* Audio not available */ }
}

async function dismissLightningCard(cardId) {
    try {
        await fetch(`${API_URL}/hydra/lightning/${cardId}/status`, {
            method: 'PATCH',
            headers: { ...getHeaders(), 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: 'dismissed' })
        });
        const el = document.querySelector(`[data-card-id="${cardId}"]`);
        if (el) el.remove();
    } catch (err) {
        console.error('Lightning dismiss error:', err);
    }
}
```

---

### 3. Initialize Lightning Cards

Find where `initHermesFlash()` or `initHydra()` or similar init functions are called
in the dashboard startup, and add:

```javascript
initLightningCards();
```

---

### 4. Cache Bust

Increment the CSS and JS version query strings in `index.html` so browsers
pick up the new code.

---

## HOW IT ALL WORKS

When Hermes detects a velocity breach AND Hydra finds an elevated squeeze
score on the same or correlated ticker, the backend automatically:

1. Creates a `lightning_cards` row with position classification
2. When Pivot's analysis arrives, updates the card with headline + thesis impact
3. Frontend polls `GET /api/hydra/lightning` every 10 seconds
4. Card renders at TOP of the Insights `#tradeSignals` container
5. Thunder sound plays once per card
6. Pulsing lime green (bullish) or orange (bearish) border + ⚡ icon
7. Shows CONFIRMING / OPPOSING / UNRELATED based on Nick's positions
8. Countdown timer shows age, turns yellow at 60min, red at 90min
9. Dismiss button removes card

## DATA FLOW

```
Hermes webhook fires
  → convergence check runs (hermes.py)
  → if squeeze score >= 50, INSERT lightning_cards row
  → classify position: CONFIRMING / OPPOSING / UNRELATED
  → Pivot analysis arrives later → UPDATE card headline + thesis
  → frontend polls /hydra/lightning every 10s
  → card renders at top of Insights feed
  → thunder sound plays
```
