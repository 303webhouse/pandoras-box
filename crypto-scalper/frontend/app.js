/**
 * Crypto Scalper - Frontend Application
 * Real-time BTC trading signals for Breakout prop trading
 */

// Configuration
const CONFIG = {
    WS_URL: `ws://${window.location.hostname}:8001/ws`,
    API_URL: `http://${window.location.hostname}:8001/api`,
    RECONNECT_DELAY: 3000,
    MAX_SIGNALS: 10,
    PRICE_HISTORY_SIZE: 60
};

// Application State
const state = {
    ws: null,
    connected: false,
    signals: [],
    currentPrice: 0,
    priceHistory: [],
    accountStatus: null,
    selectedSignal: null,
    messageCount: 0
};

// DOM Elements
const elements = {
    connectionStatus: document.getElementById('connectionStatus'),
    currentPrice: document.getElementById('currentPrice'),
    priceChange: document.getElementById('priceChange'),
    signalCount: document.getElementById('signalCount'),
    signalsList: document.getElementById('signalsList'),
    high24h: document.getElementById('high24h'),
    low24h: document.getElementById('low24h'),
    vwapPrice: document.getElementById('vwapPrice'),
    fundingRate: document.getElementById('fundingRate'),
    obBid: document.getElementById('obBid'),
    obAsk: document.getElementById('obAsk'),
    bidDepth: document.getElementById('bidDepth'),
    askDepth: document.getElementById('askDepth'),
    obImbalance: document.getElementById('obImbalance'),
    sessionName: document.getElementById('sessionName'),
    nextSession: document.getElementById('nextSession'),
    liqLong: document.getElementById('liqLong'),
    liqShort: document.getElementById('liqShort'),
    liqLongVal: document.getElementById('liqLongVal'),
    liqShortVal: document.getElementById('liqShortVal'),
    accountType: document.getElementById('accountType'),
    startingBalance: document.getElementById('startingBalance'),
    currentBalance: document.getElementById('currentBalance'),
    hwm: document.getElementById('hwm'),
    ddCurrent: document.getElementById('ddCurrent'),
    ddMeter: document.getElementById('ddMeter'),
    dailyPnl: document.getElementById('dailyPnl'),
    dailyMeter: document.getElementById('dailyMeter'),
    riskValue: document.getElementById('riskValue'),
    serverTime: document.getElementById('serverTime'),
    messageCount: document.getElementById('messageCount'),
    signalModal: document.getElementById('signalModal'),
    modalTitle: document.getElementById('modalTitle'),
    modalBody: document.getElementById('modalBody')
};

// WebSocket Connection
function connectWebSocket() {
    console.log('Connecting to WebSocket...');
    
    state.ws = new WebSocket(CONFIG.WS_URL);
    
    state.ws.onopen = () => {
        console.log('WebSocket connected');
        state.connected = true;
        updateConnectionStatus(true);
    };
    
    state.ws.onclose = () => {
        console.log('WebSocket disconnected');
        state.connected = false;
        updateConnectionStatus(false);
        
        // Reconnect after delay
        setTimeout(connectWebSocket, CONFIG.RECONNECT_DELAY);
    };
    
    state.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        updateConnectionStatus(false, true);
    };
    
    state.ws.onmessage = (event) => {
        state.messageCount++;
        elements.messageCount.textContent = `${state.messageCount} msgs`;
        
        try {
            const message = JSON.parse(event.data);
            handleMessage(message);
        } catch (e) {
            console.error('Failed to parse message:', e);
        }
    };
}

function updateConnectionStatus(connected, error = false) {
    const statusDot = elements.connectionStatus.querySelector('.status-dot');
    const statusText = elements.connectionStatus.querySelector('.status-text');
    
    statusDot.classList.remove('connected', 'error');
    
    if (connected) {
        statusDot.classList.add('connected');
        statusText.textContent = 'Connected';
    } else if (error) {
        statusDot.classList.add('error');
        statusText.textContent = 'Error';
    } else {
        statusText.textContent = 'Reconnecting...';
    }
}

// Message Handlers
function handleMessage(message) {
    switch (message.type) {
        case 'CONNECTED':
            console.log('Server acknowledged connection');
            break;
            
        case 'INITIAL_SIGNALS':
            state.signals = message.data || [];
            renderSignals();
            break;
            
        case 'ACCOUNT_STATUS':
            state.accountStatus = message.data;
            updateAccountDisplay();
            break;
            
        case 'PRICE_UPDATE':
            handlePriceUpdate(message.data);
            break;
            
        case 'NEW_SIGNAL':
        case 'FUNDING_SIGNAL':
        case 'LIQUIDATION_SIGNAL':
        case 'HIGH_PRIORITY_SIGNAL':
            handleNewSignal(message.data);
            break;
            
        case 'FUNDING_UPDATE':
            handleFundingUpdate(message.data);
            break;
            
        case 'ORDERBOOK_UPDATE':
            handleOrderbookUpdate(message.data);
            break;
            
        case 'LIQUIDATION':
            handleLiquidation(message.data);
            break;
            
        case 'RISK_WARNING':
            handleRiskWarning(message.data);
            break;
    }
}

function handlePriceUpdate(data) {
    const previousPrice = state.currentPrice;
    state.currentPrice = data.price;
    
    // Update price display
    elements.currentPrice.textContent = formatPrice(data.price);
    
    // Calculate and show change
    if (previousPrice > 0) {
        const change = ((data.price - previousPrice) / previousPrice) * 100;
        elements.priceChange.textContent = `${change >= 0 ? '+' : ''}${change.toFixed(3)}%`;
        elements.priceChange.className = `price-change ${change >= 0 ? 'positive' : 'negative'}`;
    }
    
    // Update market stats
    elements.high24h.textContent = formatPrice(data.high_24h);
    elements.low24h.textContent = formatPrice(data.low_24h);
    elements.vwapPrice.textContent = formatPrice(data.vwap);
    
    // Store price history
    state.priceHistory.push({
        price: data.price,
        timestamp: new Date(data.timestamp)
    });
    
    if (state.priceHistory.length > CONFIG.PRICE_HISTORY_SIZE) {
        state.priceHistory.shift();
    }
}

function handleFundingUpdate(data) {
    const rate = data.funding_rate * 100;
    elements.fundingRate.textContent = `${rate >= 0 ? '+' : ''}${rate.toFixed(4)}%`;
    elements.fundingRate.className = `stat-value ${rate >= 0 ? 'positive' : 'negative'}`;
}

function handleOrderbookUpdate(data) {
    const imbalance = data.imbalance;
    const bidPct = ((1 + imbalance) / 2) * 100;
    const askPct = 100 - bidPct;
    
    elements.obBid.style.width = `${bidPct}%`;
    elements.obAsk.style.width = `${askPct}%`;
    
    elements.bidDepth.textContent = `${data.bid_depth.toFixed(1)} BTC`;
    elements.askDepth.textContent = `${data.ask_depth.toFixed(1)} BTC`;
    elements.obImbalance.textContent = `${(imbalance * 100).toFixed(1)}%`;
}

function handleLiquidation(data) {
    const longLiq = data.long_liq_1h || 0;
    const shortLiq = data.short_liq_1h || 0;
    const total = longLiq + shortLiq || 1;
    
    const longPct = (longLiq / total) * 100;
    const shortPct = (shortLiq / total) * 100;
    
    elements.liqLong.style.width = `${longPct}%`;
    elements.liqShort.style.width = `${shortPct}%`;
    
    elements.liqLongVal.textContent = formatUSD(longLiq);
    elements.liqShortVal.textContent = formatUSD(shortLiq);
}

function handleNewSignal(signalData) {
    // Add to front of array
    state.signals.unshift(signalData);
    
    // Trim to max
    if (state.signals.length > CONFIG.MAX_SIGNALS) {
        state.signals.pop();
    }
    
    renderSignals();
    
    // Play notification sound for high priority
    if (signalData.priority === 'high') {
        playNotificationSound();
        showNotification(signalData);
    }
}

function handleRiskWarning(data) {
    console.warn('Risk Warning:', data.message);
    
    // Update risk badge
    elements.riskValue.textContent = 'WARNING';
    elements.riskValue.className = 'risk-value warning';
    
    // Show alert
    showAlert(data.message, 'warning');
}

// Rendering Functions
function renderSignals() {
    elements.signalCount.textContent = state.signals.length;
    
    if (state.signals.length === 0) {
        elements.signalsList.innerHTML = `
            <div class="no-signals">
                <span class="icon">📡</span>
                <p>Waiting for signals...</p>
                <p class="sub">Monitoring 4 strategies 24/7</p>
            </div>
        `;
        return;
    }
    
    elements.signalsList.innerHTML = state.signals.map(signal => `
        <div class="signal-card ${signal.direction.toLowerCase()} ${signal.priority === 'high' ? 'high-priority' : ''}"
             onclick="showSignalDetails('${signal.id}')">
            <div class="signal-header">
                <span class="signal-direction ${signal.direction.toLowerCase()}">
                    ${signal.direction === 'LONG' ? '🟢' : '🔴'} ${signal.direction}
                </span>
                <span class="signal-strategy">${formatStrategy(signal.strategy)}</span>
            </div>
            <div class="signal-prices">
                <div class="signal-price">
                    <span class="label">Entry</span>
                    <span class="value entry">${formatPrice(signal.entry)}</span>
                </div>
                <div class="signal-price">
                    <span class="label">Stop</span>
                    <span class="value stop">${formatPrice(signal.stop)}</span>
                </div>
                <div class="signal-price">
                    <span class="label">Target</span>
                    <span class="value target">${formatPrice(signal.target_1)}</span>
                </div>
            </div>
            <div class="signal-meta">
                <span class="signal-rr">R:R ${signal.rr_ratio}</span>
                <span class="signal-confidence">
                    <span class="confidence-bar">
                        <span class="confidence-fill" style="width: ${signal.confidence * 100}%"></span>
                    </span>
                    ${Math.round(signal.confidence * 100)}%
                </span>
                <span class="signal-time">${formatTime(signal.timestamp)}</span>
            </div>
        </div>
    `).join('');
}

function updateAccountDisplay() {
    if (!state.accountStatus) return;
    
    const { account, risk_status, positions } = state.accountStatus;
    
    // Account info
    elements.accountType.textContent = account.type;
    elements.startingBalance.textContent = formatUSD(account.starting_balance);
    elements.currentBalance.textContent = formatUSD(account.current_balance);
    elements.hwm.textContent = formatUSD(account.high_water_mark);
    
    // Risk status
    const ddPct = risk_status.current_drawdown_pct;
    const ddLimit = account.type === '1-step' ? 6 : 8;
    elements.ddCurrent.textContent = `${ddPct.toFixed(2)}%`;
    elements.ddMeter.style.width = `${(ddPct / ddLimit) * 100}%`;
    
    const dailyPnl = risk_status.current_daily_pnl_pct;
    const dailyLimit = account.type === '1-step' ? 4 : 5;
    elements.dailyPnl.textContent = `${dailyPnl >= 0 ? '+' : ''}${dailyPnl.toFixed(2)}%`;
    
    // Calculate daily meter (inverse - showing how much loss room is used)
    if (dailyPnl < 0) {
        elements.dailyMeter.style.width = `${(Math.abs(dailyPnl) / dailyLimit) * 100}%`;
    } else {
        elements.dailyMeter.style.width = '0%';
    }
    
    // Risk badge
    if (ddPct > 4 || dailyPnl < -2.5) {
        elements.riskValue.textContent = 'CAUTION';
        elements.riskValue.className = 'risk-value warning';
    } else if (ddPct > 5 || dailyPnl < -3) {
        elements.riskValue.textContent = 'DANGER';
        elements.riskValue.className = 'risk-value danger';
    } else {
        elements.riskValue.textContent = `${risk_status.room_to_drawdown_pct.toFixed(1)}% room`;
        elements.riskValue.className = 'risk-value';
    }
}

// Signal Details Modal
function showSignalDetails(signalId) {
    const signal = state.signals.find(s => s.id === signalId);
    if (!signal) return;
    
    state.selectedSignal = signal;
    
    elements.modalTitle.textContent = `${signal.direction} Signal - ${formatStrategy(signal.strategy)}`;
    elements.modalBody.innerHTML = `
        <div class="signal-detail">
            <div class="detail-section">
                <h4>Trade Setup</h4>
                <div class="detail-row">
                    <span>Direction</span>
                    <strong class="${signal.direction.toLowerCase()}">${signal.direction}</strong>
                </div>
                <div class="detail-row">
                    <span>Entry Price</span>
                    <strong>${formatPrice(signal.entry)}</strong>
                </div>
                <div class="detail-row">
                    <span>Stop Loss</span>
                    <strong class="short">${formatPrice(signal.stop)}</strong>
                </div>
                <div class="detail-row">
                    <span>Target 1</span>
                    <strong class="long">${formatPrice(signal.target_1)}</strong>
                </div>
                ${signal.target_2 ? `
                <div class="detail-row">
                    <span>Target 2</span>
                    <strong class="long">${formatPrice(signal.target_2)}</strong>
                </div>
                ` : ''}
            </div>
            
            <div class="detail-section">
                <h4>Risk Analysis</h4>
                <div class="detail-row">
                    <span>Risk/Reward</span>
                    <strong>${signal.rr_ratio}:1</strong>
                </div>
                <div class="detail-row">
                    <span>Confidence</span>
                    <strong>${Math.round(signal.confidence * 100)}%</strong>
                </div>
                <div class="detail-row">
                    <span>Priority</span>
                    <strong>${signal.priority.toUpperCase()}</strong>
                </div>
                ${signal.position_size_btc ? `
                <div class="detail-row">
                    <span>Position Size</span>
                    <strong>${signal.position_size_btc.toFixed(4)} BTC</strong>
                </div>
                <div class="detail-row">
                    <span>Risk Amount</span>
                    <strong>${formatUSD(signal.risk_amount_usd)}</strong>
                </div>
                ` : ''}
            </div>
            
            <div class="detail-section">
                <h4>Reasoning</h4>
                <p class="reasoning">${signal.reasoning}</p>
            </div>
        </div>
    `;
    
    elements.signalModal.classList.add('active');
}

function closeModal() {
    elements.signalModal.classList.remove('active');
    state.selectedSignal = null;
}

async function dismissSignal() {
    if (!state.selectedSignal) return;
    
    try {
        await fetch(`${CONFIG.API_URL}/signals/${state.selectedSignal.id}`, {
            method: 'DELETE'
        });
        
        state.signals = state.signals.filter(s => s.id !== state.selectedSignal.id);
        renderSignals();
        closeModal();
    } catch (e) {
        console.error('Failed to dismiss signal:', e);
    }
}

// Strategy Toggles
document.querySelectorAll('.strategy-toggle input').forEach(toggle => {
    toggle.addEventListener('change', async (e) => {
        const strategy = e.target.dataset.strategy;
        const enabled = e.target.checked;
        
        try {
            await fetch(`${CONFIG.API_URL}/strategies/toggle`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ strategy, enabled })
            });
        } catch (e) {
            console.error('Failed to toggle strategy:', e);
            e.target.checked = !enabled; // Revert
        }
    });
});

// Phase Buttons
document.querySelectorAll('.phase-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
        const phase = e.target.dataset.phase;
        
        document.querySelectorAll('.phase-btn').forEach(b => b.classList.remove('active'));
        e.target.classList.add('active');
        
        try {
            await fetch(`${CONFIG.API_URL}/risk/set-phase?phase=${phase}`, {
                method: 'POST'
            });
            
            updatePhaseInfo(phase);
        } catch (e) {
            console.error('Failed to set phase:', e);
        }
    });
});

function updatePhaseInfo(phase) {
    const phaseInfo = {
        conservative: 'Max 1% risk per trade | 2:1 min R:R | 1-2x leverage',
        growth: 'Max 1.5% risk per trade | 1.5:1 min R:R | 2-3x leverage',
        aggressive: 'Max 2.5% risk per trade | 1.25:1 min R:R | 3-5x leverage'
    };
    
    document.getElementById('phaseInfo').innerHTML = `<p>${phaseInfo[phase]}</p>`;
}

// Utility Functions
function formatPrice(price) {
    if (!price) return '--,---.--';
    return price.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function formatUSD(amount) {
    if (!amount && amount !== 0) return '--';
    return '$' + amount.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
}

function formatStrategy(strategy) {
    const names = {
        funding_rate: 'Funding',
        vwap: 'VWAP',
        session_breakout: 'Session',
        liquidation_reversal: 'Liq Rev'
    };
    return names[strategy] || strategy;
}

function formatTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit'
    });
}

function playNotificationSound() {
    // Create a simple beep
    try {
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioContext.createOscillator();
        const gainNode = audioContext.createGain();
        
        oscillator.connect(gainNode);
        gainNode.connect(audioContext.destination);
        
        oscillator.frequency.value = 880;
        oscillator.type = 'sine';
        gainNode.gain.value = 0.3;
        
        oscillator.start();
        setTimeout(() => oscillator.stop(), 200);
    } catch (e) {
        console.log('Audio not available');
    }
}

function showNotification(signal) {
    if ('Notification' in window && Notification.permission === 'granted') {
        new Notification('Crypto Scalper Signal', {
            body: `${signal.direction} @ ${formatPrice(signal.entry)} - ${formatStrategy(signal.strategy)}`,
            icon: '⚡'
        });
    }
}

function showAlert(message, type = 'info') {
    // Simple alert for now - could enhance with toast notifications
    console.log(`[${type.toUpperCase()}] ${message}`);
}

// Update server time
function updateServerTime() {
    const now = new Date();
    elements.serverTime.textContent = now.toISOString().substr(11, 8) + ' UTC';
}

// Initialize
function init() {
    console.log('Initializing Crypto Scalper...');
    
    // Request notification permission
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission();
    }
    
    // Connect WebSocket
    connectWebSocket();
    
    // Start server time updates
    setInterval(updateServerTime, 1000);
    updateServerTime();
    
    // Keep WebSocket alive
    setInterval(() => {
        if (state.ws && state.ws.readyState === WebSocket.OPEN) {
            state.ws.send('ping');
        }
    }, 30000);
}

// Start app
init();

// Export for debugging
window.cryptoScalper = {
    state,
    showSignalDetails,
    closeModal,
    dismissSignal
};
