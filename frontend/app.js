/**
 * Pandora's Box - Frontend Application
 * Real-time WebSocket connection for multi-device sync
 */

// Configuration
// Use Railway backend for production, localhost for local development
const BACKEND_HOST = 'pandoras-box-production.up.railway.app';
const WS_URL = `wss://${BACKEND_HOST}/ws`;
const API_URL = `https://${BACKEND_HOST}/api`;

// State
let ws = null;
let tvWidget = null;
let currentSymbol = 'SPY';
let currentTimeframe = 'WEEKLY';
let activeAssetType = 'equity';
let signals = {
    equity: [],
    crypto: []
};

// Price levels to display on chart (entry, stop, target)
let activePriceLevels = null;

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    initTradingViewWidget();
    initWebSocket();
    initEventListeners();
    loadInitialData();
});

// TradingView Widget
function initTradingViewWidget() {
    const container = document.getElementById('tradingview-widget');
    
    // Clear any existing content
    container.innerHTML = '';
    
    tvWidget = new TradingView.widget({
        symbol: currentSymbol,
        interval: 'D',
        timezone: 'America/New_York',
        theme: 'dark',
        style: '1',
        locale: 'en',
        toolbar_bg: '#0a0e27',
        enable_publishing: false,
        hide_top_toolbar: false,
        hide_legend: false,
        save_image: false,
        container_id: 'tradingview-widget',
        width: '100%',
        height: '100%',
        studies: [
            { id: 'MASimple@tv-basicstudies', inputs: { length: 200 } }
        ],
        studies_overrides: {
            // 200 SMA - thick teal line
            'moving average.ma.color': '#14b8a6',
            'moving average.ma.linewidth': 3,
            // Volume bars
            'volume.volume.color.0': '#FF6B35',
            'volume.volume.color.1': '#7CFF6B',
            'volume.volume ma.color': '#14b8a6'
        },
        overrides: {
            // Candlestick colors - lime up, orange down
            'mainSeriesProperties.candleStyle.upColor': '#7CFF6B',
            'mainSeriesProperties.candleStyle.downColor': '#FF6B35',
            'mainSeriesProperties.candleStyle.borderUpColor': '#7CFF6B',
            'mainSeriesProperties.candleStyle.borderDownColor': '#FF6B35',
            'mainSeriesProperties.candleStyle.wickUpColor': '#7CFF6B',
            'mainSeriesProperties.candleStyle.wickDownColor': '#FF6B35',
            
            // Background - dark navy
            'paneProperties.background': '#0a0e27',
            'paneProperties.backgroundType': 'solid',
            
            // Grid lines - subtle
            'paneProperties.vertGridProperties.color': '#1e293b',
            'paneProperties.horzGridProperties.color': '#1e293b',
            'paneProperties.vertGridProperties.style': 0,
            'paneProperties.horzGridProperties.style': 0,
            
            // Scale/axis text
            'scalesProperties.textColor': '#94a3b8',
            'scalesProperties.backgroundColor': '#0a0e27',
            'scalesProperties.lineColor': '#334155',
            
            // Crosshair
            'paneProperties.crossHairProperties.color': '#14b8a6',
            'paneProperties.crossHairProperties.style': 0,
            
            // Legend text
            'paneProperties.legendProperties.showStudyArguments': true,
            'paneProperties.legendProperties.showStudyTitles': true,
            'paneProperties.legendProperties.showStudyValues': true,
            'paneProperties.legendProperties.showSeriesTitle': true,
            'paneProperties.legendProperties.showSeriesOHLC': true,
            
            // Separator lines between panes
            'paneProperties.separatorColor': '#334155'
        },
        loading_screen: {
            backgroundColor: '#0a0e27',
            foregroundColor: '#14b8a6'
        }
    });
}

function changeChartSymbol(symbol) {
    currentSymbol = symbol;
    
    // Update tab active state
    document.querySelectorAll('.chart-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.symbol === symbol);
    });
    
    // Clear price levels when changing symbols
    activePriceLevels = null;
    
    // Reinitialize widget with new symbol
    initTradingViewWidget();
}

function showTradeOnChart(signal) {
    // Change to the signal's ticker
    const symbol = signal.asset_class === 'CRYPTO' 
        ? signal.ticker + 'USD' 
        : signal.ticker;
    
    currentSymbol = symbol;
    
    // Store price levels to display
    activePriceLevels = {
        entry: signal.entry_price,
        stop: signal.stop_loss,
        target: signal.target_1
    };
    
    // Update tab styling (remove active from all since this is a custom ticker)
    document.querySelectorAll('.chart-tab').forEach(tab => {
        tab.classList.remove('active');
        if (tab.dataset.symbol === symbol) {
            tab.classList.add('active');
        }
    });
    
    // Reinitialize with the new symbol
    initTradingViewWidget();
    
    // Note: TradingView widget doesn't easily support drawing horizontal lines
    // For full price level display, we'd need TradingView Advanced Charts (paid)
    // For now, the signal details panel shows the levels clearly
    
    console.log(`📊 Showing ${signal.ticker} on chart with levels:`, activePriceLevels);
}

// WebSocket Connection
function initWebSocket() {
    console.log('🔌 Connecting to Pandora\'s Box...');
    
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
        console.log('✅ Connected to backend');
        updateConnectionStatus(true);
        
        // Send heartbeat every 30 seconds
        setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send('ping');
            }
        }, 30000);
    };
    
    ws.onmessage = (event) => {
        // Handle heartbeat pong response
        if (event.data === 'pong') {
            return;
        }
        
        try {
            const message = JSON.parse(event.data);
            handleWebSocketMessage(message);
        } catch (e) {
            console.warn('⚠️ Non-JSON message received:', event.data);
        }
    };
    
    ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        updateConnectionStatus(false);
    };
    
    ws.onclose = () => {
        console.log('🔌 Connection closed. Reconnecting...');
        updateConnectionStatus(false);
        
        // Reconnect after 3 seconds
        setTimeout(initWebSocket, 3000);
    };
}

function handleWebSocketMessage(message) {
    console.log('📨 Received:', message);
    
    switch (message.type) {
        case 'NEW_SIGNAL':
            addSignal(message.data);
            break;
        case 'BIAS_UPDATE':
            updateBias(message.data);
            break;
        case 'POSITION_UPDATE':
            updatePosition(message.data);
            break;
        case 'SIGNAL_DISMISSED':
            removeSignal(message.signal_id);
            break;
    }
}

function updateConnectionStatus(connected) {
    const statusDot = document.querySelector('.status-dot');
    const statusText = document.querySelector('.status-text');
    
    if (connected) {
        statusDot.classList.add('connected');
        statusText.textContent = 'Live';
    } else {
        statusDot.classList.remove('connected');
        statusText.textContent = 'Reconnecting...';
    }
}

// Event Listeners
function initEventListeners() {
    // Timeframe selector
    document.getElementById('timeframeSelector').addEventListener('change', (e) => {
        currentTimeframe = e.target.value;
        loadSignals();
    });
    
    // Refresh button
    document.getElementById('refreshBtn').addEventListener('click', () => {
        loadSignals();
        loadBiasData();
    });
    
    // Chart tabs (SPY, VIX, BTC)
    document.querySelectorAll('.chart-tab').forEach(tab => {
        tab.addEventListener('click', (e) => {
            changeChartSymbol(e.target.dataset.symbol);
        });
    });
    
    // Asset type toggle (Equities / Crypto)
    document.querySelectorAll('.toggle-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            document.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            activeAssetType = e.target.dataset.asset;
            renderSignals();
        });
    });
}

// Data Loading
async function loadInitialData() {
    await Promise.all([
        loadSignals(),
        loadBiasData(),
        loadOpenPositions()
    ]);
}

async function loadSignals() {
    try {
        const response = await fetch(`${API_URL}/signals/active`);
        const data = await response.json();
        
        if (data.status === 'success') {
            // Separate equity and crypto signals
            signals.equity = data.signals.filter(s => s.asset_class === 'EQUITY');
            signals.crypto = data.signals.filter(s => s.asset_class === 'CRYPTO');
            
            renderSignals();
        }
    } catch (error) {
        console.error('Error loading signals:', error);
    }
}

async function loadBiasData() {
    // Load Daily and Weekly from generic bias endpoint
    const timeframes = ['DAILY', 'WEEKLY'];
    
    for (const timeframe of timeframes) {
        try {
            const response = await fetch(`${API_URL}/bias/${timeframe}`);
            const data = await response.json();
            
            const tfLower = timeframe.toLowerCase();
            const container = document.getElementById(`${tfLower}Bias`);
            const levelElement = document.getElementById(`${tfLower}Level`);
            const detailsElement = document.getElementById(`${tfLower}Details`);
            
            if (levelElement) {
                const level = data.level || 'NEUTRAL';
                levelElement.textContent = level.replace('_', ' ');
                
                if (container) {
                    container.classList.remove('bullish', 'bearish', 'neutral');
                    if (level.includes('TORO')) {
                        container.classList.add('bullish');
                    } else if (level.includes('URSA')) {
                        container.classList.add('bearish');
                    } else {
                        container.classList.add('neutral');
                    }
                }
            }
            
            if (detailsElement) {
                if (data.details) {
                    detailsElement.textContent = data.details;
                } else if (data.data) {
                    detailsElement.textContent = `TICK: ${data.data.tick || 'N/A'}`;
                } else {
                    detailsElement.textContent = 'No data available';
                }
            }
        } catch (error) {
            console.error(`Error loading ${timeframe} bias:`, error);
            const tfLower = timeframe.toLowerCase();
            const detailsElement = document.getElementById(`${tfLower}Details`);
            if (detailsElement) {
                detailsElement.textContent = 'Failed to load';
            }
        }
    }
    
    // Load Monthly (Savita Indicator) separately
    await loadSavitaIndicator();
}

async function loadSavitaIndicator() {
    try {
        const response = await fetch(`${API_URL}/bias/savita`);
        const data = await response.json();
        
        const container = document.getElementById('monthlyBias');
        const levelElement = document.getElementById('monthlyLevel');
        const detailsElement = document.getElementById('monthlyDetails');
        
        if (data.status === 'success') {
            const bias = data.bias || 'NEUTRAL';
            
            if (levelElement) {
                levelElement.textContent = bias.replace('_', ' ');
            }
            
            if (container) {
                container.classList.remove('bullish', 'bearish', 'neutral');
                if (bias.includes('TORO')) {
                    container.classList.add('bullish');
                } else if (bias.includes('URSA')) {
                    container.classList.add('bearish');
                } else {
                    container.classList.add('neutral');
                }
            }
            
            if (detailsElement) {
                // Show reading and interpretation
                const reading = data.reading || 'N/A';
                const signal = data.signal || '';
                const updated = data.last_updated || 'Unknown';
                detailsElement.innerHTML = `
                    <span class="savita-reading">${reading}%</span> - ${signal}<br>
                    <small>Updated: ${updated}</small>
                `;
            }
        } else {
            if (detailsElement) {
                detailsElement.textContent = data.message || 'Unavailable';
            }
        }
    } catch (error) {
        console.error('Error loading Savita indicator:', error);
        const detailsElement = document.getElementById('monthlyDetails');
        if (detailsElement) {
            detailsElement.textContent = 'Failed to load';
        }
    }
}

async function loadOpenPositions() {
    try {
        const response = await fetch(`${API_URL}/positions/open`);
        const data = await response.json();
        
        if (data.status === 'success') {
            renderPositions(data.positions);
        }
    } catch (error) {
        console.error('Error loading positions:', error);
    }
}

// Signal Rendering
function renderSignals() {
    const container = document.getElementById('tradeSignals');
    
    // Top 20 crypto by market cap (+ common variations)
    const SUPPORTED_CRYPTO = [
        // Base tickers
        'BTC', 'ETH', 'USDT', 'BNB', 'SOL', 'XRP', 'USDC', 'ADA', 'AVAX', 'DOGE',
        'DOT', 'TRX', 'LINK', 'MATIC', 'POL', 'SHIB', 'TON', 'LTC', 'BCH', 'XLM', 'UNI',
        // TradingView USD pairs
        'BTCUSD', 'ETHUSD', 'SOLUSD', 'XRPUSD', 'ADAUSD', 'AVAXUSD', 'DOGEUSD',
        'DOTUSD', 'LINKUSD', 'MATICUSD', 'LTCUSD', 'BCHUSD', 'XLMUSD', 'UNIUSD',
        // TradingView USDT pairs
        'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'ADAUSDT', 'AVAXUSDT', 'DOGEUSDT',
        'DOTUSDT', 'LINKUSDT', 'MATICUSDT', 'LTCUSDT', 'BCHUSDT', 'XLMUSDT', 'UNIUSDT'
    ];
    
    // Get signals based on active asset type
    const activeSignals = activeAssetType === 'equity' 
        ? signals.equity 
        : signals.crypto.filter(s => SUPPORTED_CRYPTO.includes(s.ticker.toUpperCase()));
    
    // Limit to top 10
    const topSignals = activeSignals.slice(0, 10);
    
    if (topSignals.length === 0) {
        const assetLabel = activeAssetType === 'equity' ? 'equity' : 'crypto';
        container.innerHTML = `<p class="empty-state">No ${assetLabel} signals</p>`;
        return;
    }
    
    container.innerHTML = topSignals.map(signal => createSignalCard(signal)).join('');
    
    // Add event listeners to action buttons and cards
    attachSignalActions();
}

function createSignalCard(signal) {
    const typeLabel = signal.signal_type.replace('_', ' ');
    
    return `
        <div class="signal-card ${signal.signal_type}" data-signal-id="${signal.signal_id}" data-signal='${JSON.stringify(signal)}'>
            <div class="signal-header">
                <div>
                    <div class="signal-type ${signal.signal_type}">${typeLabel}</div>
                    <div class="signal-strategy">${signal.strategy}</div>
                </div>
                <div class="signal-ticker ticker-link" data-action="view-chart">${signal.ticker}</div>
            </div>
            
            <div class="signal-details">
                <div class="signal-detail">
                    <div class="signal-detail-label">Entry</div>
                    <div class="signal-detail-value">${signal.entry_price.toFixed(2)}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Stop</div>
                    <div class="signal-detail-value">${signal.stop_loss.toFixed(2)}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Target</div>
                    <div class="signal-detail-value">${signal.target_1.toFixed(2)}</div>
                </div>
            </div>
            
            <div class="signal-details">
                <div class="signal-detail">
                    <div class="signal-detail-label">R:R</div>
                    <div class="signal-detail-value">${signal.risk_reward}:1</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Direction</div>
                    <div class="signal-detail-value">${signal.direction}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Score</div>
                    <div class="signal-detail-value">${signal.score}</div>
                </div>
            </div>
            
            <div class="signal-actions">
                <button class="action-btn dismiss-btn" data-action="dismiss">✕ Dismiss</button>
                <button class="action-btn select-btn" data-action="select">✓ Select</button>
            </div>
        </div>
    `;
}

function attachSignalActions() {
    // Clickable ticker to view on chart
    document.querySelectorAll('.ticker-link').forEach(ticker => {
        ticker.addEventListener('click', (e) => {
            e.stopPropagation();
            const card = e.target.closest('.signal-card');
            const signal = JSON.parse(card.dataset.signal);
            showTradeOnChart(signal);
        });
    });
    
    // Dismiss and Select buttons
    document.querySelectorAll('.action-btn').forEach(btn => {
        btn.addEventListener('click', handleSignalAction);
    });
}

async function handleSignalAction(event) {
    event.stopPropagation();
    const button = event.target;
    const card = button.closest('.signal-card');
    const signalId = card.dataset.signalId;
    const action = button.dataset.action.toUpperCase();
    
    if (action === 'VIEW-CHART') return; // Handled separately
    
    try {
        const response = await fetch(`${API_URL}/signal/action`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ signal_id: signalId, action })
        });
        
        const data = await response.json();
        
        if (data.status === 'dismissed' || data.status === 'selected') {
            // Remove card with animation
            card.style.opacity = '0';
            card.style.transform = 'translateX(-20px)';
            setTimeout(() => card.remove(), 300);
            
            // Reload positions if selected
            if (data.status === 'selected') {
                loadOpenPositions();
            }
        }
    } catch (error) {
        console.error('Error handling signal action:', error);
    }
}

// Signal Management
function addSignal(signalData) {
    if (signalData.asset_class === 'EQUITY') {
        signals.equity.unshift(signalData);
        signals.equity = signals.equity.slice(0, 10);
    } else {
        signals.crypto.unshift(signalData);
    }
    
    renderSignals();
}

function removeSignal(signalId) {
    signals.equity = signals.equity.filter(s => s.signal_id !== signalId);
    signals.crypto = signals.crypto.filter(s => s.signal_id !== signalId);
    
    renderSignals();
}

// Bias Updates
function updateBias(biasData) {
    const timeframe = biasData.timeframe.toLowerCase();
    const container = document.getElementById(`${timeframe}Bias`);
    const levelElement = document.getElementById(`${timeframe}Level`);
    const detailsElement = document.getElementById(`${timeframe}Details`);
    
    if (levelElement) {
        levelElement.textContent = biasData.level.replace('_', ' ');
        levelElement.className = `bias-level ${biasData.level}`;
    }
    
    if (container) {
        container.classList.remove('bullish', 'bearish', 'neutral');
        if (biasData.level.includes('TORO')) {
            container.classList.add('bullish');
        } else if (biasData.level.includes('URSA')) {
            container.classList.add('bearish');
        } else {
            container.classList.add('neutral');
        }
    }
    
    if (detailsElement && biasData.details) {
        detailsElement.innerHTML = biasData.details;
    }
}

// Position Management
function renderPositions(positions) {
    const container = document.getElementById('openPositions');
    
    if (!positions || positions.length === 0) {
        container.innerHTML = '<p class="empty-state">No open positions</p>';
        return;
    }
    
    container.innerHTML = positions.map(pos => `
        <div class="signal-card">
            <div class="signal-header">
                <div class="signal-ticker">${pos.ticker}</div>
                <div class="signal-type">${pos.direction}</div>
            </div>
            <div class="signal-details">
                <div class="signal-detail">
                    <div class="signal-detail-label">Entry</div>
                    <div class="signal-detail-value">${pos.entry_price?.toFixed(2) || 'N/A'}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Stop</div>
                    <div class="signal-detail-value">${pos.stop_loss.toFixed(2)}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Target</div>
                    <div class="signal-detail-value">${pos.target_1.toFixed(2)}</div>
                </div>
            </div>
        </div>
    `).join('');
}

function updatePosition(positionData) {
    loadOpenPositions();
}

// ==========================================
// HUNTER SCANNER
// ==========================================

let hunterResults = {
    ursa: [],
    taurus: []
};

// Initialize Hunter Scanner
function initHunterScanner() {
    const runScanBtn = document.getElementById('runScanBtn');
    if (runScanBtn) {
        runScanBtn.addEventListener('click', runHunterScan);
    }
    
    // Load any cached results
    loadHunterResults();
}

// Run a new scan
async function runHunterScan() {
    const btn = document.getElementById('runScanBtn');
    const status = document.getElementById('scanStatus');
    
    // Disable button and update status
    btn.disabled = true;
    btn.textContent = 'Scanning...';
    status.textContent = 'Scanning S&P 500...';
    status.classList.add('scanning');
    
    try {
        // Trigger the scan
        const response = await fetch(`${API_URL}/scanner/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: 'all' })
        });
        
        const data = await response.json();
        
        if (data.status === 'started') {
            // Poll for results
            pollForResults();
        } else {
            throw new Error(data.message || 'Scan failed to start');
        }
        
    } catch (error) {
        console.error('Hunter scan error:', error);
        status.textContent = 'Scan failed';
        status.classList.remove('scanning');
        btn.disabled = false;
        btn.textContent = 'Run Scan';
    }
}

// Poll for scan results
async function pollForResults() {
    const btn = document.getElementById('runScanBtn');
    const status = document.getElementById('scanStatus');
    
    let attempts = 0;
    const maxAttempts = 60; // 5 minutes max
    
    const poll = async () => {
        try {
            const response = await fetch(`${API_URL}/scanner/status`);
            const data = await response.json();
            
            if (data.status === 'complete') {
                // Scan complete, load results
                await loadHunterResults();
                status.textContent = 'Scan complete';
                status.classList.remove('scanning');
                btn.disabled = false;
                btn.textContent = 'Run Scan';
                return;
            }
            
            if (data.status === 'scanning' && attempts < maxAttempts) {
                attempts++;
                status.textContent = `Scanning... (${attempts * 5}s)`;
                setTimeout(poll, 5000); // Poll every 5 seconds
            } else if (data.status && data.status.startsWith('error')) {
                throw new Error(data.status);
            }
            
        } catch (error) {
            console.error('Poll error:', error);
            status.textContent = 'Error';
            status.classList.remove('scanning');
            btn.disabled = false;
            btn.textContent = 'Run Scan';
        }
    };
    
    poll();
}

// Load Hunter results from API
async function loadHunterResults() {
    try {
        const response = await fetch(`${API_URL}/scanner/results`);
        const data = await response.json();
        
        if (data.status === 'success') {
            hunterResults.ursa = data.ursa_signals || [];
            hunterResults.taurus = data.taurus_signals || [];
            renderHunterResults();
        }
        
    } catch (error) {
        console.error('Error loading Hunter results:', error);
    }
}

// Render Hunter results
function renderHunterResults() {
    renderUrsaSignals();
    renderTaurusSignals();
}

function renderUrsaSignals() {
    const container = document.getElementById('ursaSignals');
    const countEl = document.getElementById('ursaCount');
    
    if (!container) return;
    
    countEl.textContent = hunterResults.ursa.length;
    
    if (hunterResults.ursa.length === 0) {
        container.innerHTML = '<p class="empty-state">No trapped longs detected</p>';
        return;
    }
    
    container.innerHTML = hunterResults.ursa.map(signal => createHunterCard(signal, 'ursa')).join('');
    attachHunterCardEvents();
}

function renderTaurusSignals() {
    const container = document.getElementById('taurusSignals');
    const countEl = document.getElementById('taurusCount');
    
    if (!container) return;
    
    countEl.textContent = hunterResults.taurus.length;
    
    if (hunterResults.taurus.length === 0) {
        container.innerHTML = '<p class="empty-state">No trapped shorts detected</p>';
        return;
    }
    
    container.innerHTML = hunterResults.taurus.map(signal => createHunterCard(signal, 'taurus')).join('');
    attachHunterCardEvents();
}

function createHunterCard(signal, type) {
    const priority = signal.action_required?.priority || 'MEDIUM';
    const metrics = signal.quality_metrics || {};
    const marketData = signal.market_data || {};
    const instruction = signal.action_required?.sniper_instruction || '';
    
    return `
        <div class="hunter-card" data-symbol="${signal.symbol}">
            <div class="hunter-card-header">
                <span class="hunter-ticker" data-symbol="${signal.symbol}">${signal.symbol}</span>
                <span class="hunter-priority ${priority.toLowerCase()}">${priority}</span>
            </div>
            <div class="hunter-metrics">
                <div class="hunter-metric">
                    <div class="hunter-metric-label">ADX</div>
                    <div class="hunter-metric-value">${metrics.adx_trend_strength?.toFixed(1) || '-'}</div>
                </div>
                <div class="hunter-metric">
                    <div class="hunter-metric-label">RSI</div>
                    <div class="hunter-metric-value">${metrics.rsi_momentum?.toFixed(1) || '-'}</div>
                </div>
                <div class="hunter-metric">
                    <div class="hunter-metric-label">RVOL</div>
                    <div class="hunter-metric-value">${metrics.rvol_institutional?.toFixed(1) || '-'}x</div>
                </div>
            </div>
            <div class="hunter-metrics">
                <div class="hunter-metric">
                    <div class="hunter-metric-label">Price</div>
                    <div class="hunter-metric-value">$${marketData.current_price?.toFixed(2) || '-'}</div>
                </div>
                <div class="hunter-metric">
                    <div class="hunter-metric-label">VWAP</div>
                    <div class="hunter-metric-value">$${marketData.vwap_20?.toFixed(2) || '-'}</div>
                </div>
                <div class="hunter-metric">
                    <div class="hunter-metric-label">From VWAP</div>
                    <div class="hunter-metric-value">${marketData.pct_distance_from_vwap?.toFixed(1) || '-'}%</div>
                </div>
            </div>
            ${instruction ? `<div class="hunter-instruction">📍 ${instruction}</div>` : ''}
        </div>
    `;
}

function attachHunterCardEvents() {
    // Click ticker to view on chart
    document.querySelectorAll('.hunter-ticker').forEach(ticker => {
        ticker.addEventListener('click', (e) => {
            e.stopPropagation();
            const symbol = e.target.dataset.symbol;
            changeChartSymbol(symbol);
        });
    });
    
    // Click card to view on chart
    document.querySelectorAll('.hunter-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (!e.target.classList.contains('hunter-ticker')) {
                const symbol = card.dataset.symbol;
                changeChartSymbol(symbol);
            }
        });
    });
}

// Add Hunter initialization to DOMContentLoaded
document.addEventListener('DOMContentLoaded', () => {
    // Initialize Hunter Scanner after a short delay
    setTimeout(initHunterScanner, 500);
    
    // Initialize Watchlist
    setTimeout(initWatchlist, 600);
    
    // Initialize Ticker Analyzer
    setTimeout(initTickerAnalyzer, 700);
});


// ==========================================
// WATCHLIST MANAGEMENT
// ==========================================

let watchlistTickers = [];

function initWatchlist() {
    const addBtn = document.getElementById('addTickerBtn');
    const addInput = document.getElementById('addTickerInput');
    const resetBtn = document.getElementById('resetWatchlistBtn');
    
    if (addBtn) {
        addBtn.addEventListener('click', addTickerToWatchlist);
    }
    
    if (addInput) {
        addInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                addTickerToWatchlist();
            }
        });
    }
    
    if (resetBtn) {
        resetBtn.addEventListener('click', resetWatchlist);
    }
    
    // Load current watchlist
    loadWatchlist();
}

async function loadWatchlist() {
    try {
        const response = await fetch(`${API_URL}/watchlist`);
        const data = await response.json();
        
        if (data.status === 'success') {
            watchlistTickers = data.tickers || [];
            renderWatchlist();
        }
    } catch (error) {
        console.error('Error loading watchlist:', error);
        document.getElementById('watchlistTickers').innerHTML = 
            '<p class="empty-state">Failed to load watchlist</p>';
    }
}

function renderWatchlist() {
    const container = document.getElementById('watchlistTickers');
    const countEl = document.getElementById('watchlistCount');
    
    if (!container) return;
    
    countEl.textContent = watchlistTickers.length;
    
    if (watchlistTickers.length === 0) {
        container.innerHTML = '<p class="empty-state">No tickers in watchlist</p>';
        return;
    }
    
    container.innerHTML = watchlistTickers.map(ticker => `
        <div class="watchlist-ticker" data-ticker="${ticker}">
            <span class="ticker-name">${ticker}</span>
            <span class="remove-ticker" data-ticker="${ticker}">✕</span>
        </div>
    `).join('');
    
    // Attach click events
    container.querySelectorAll('.ticker-name').forEach(el => {
        el.addEventListener('click', (e) => {
            e.stopPropagation();
            const ticker = e.target.closest('.watchlist-ticker').dataset.ticker;
            changeChartSymbol(ticker);
        });
    });
    
    container.querySelectorAll('.remove-ticker').forEach(el => {
        el.addEventListener('click', (e) => {
            e.stopPropagation();
            removeTickerFromWatchlist(e.target.dataset.ticker);
        });
    });
}

async function addTickerToWatchlist() {
    const input = document.getElementById('addTickerInput');
    const ticker = input.value.trim().toUpperCase();
    
    if (!ticker) return;
    
    try {
        const response = await fetch(`${API_URL}/watchlist/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker })
        });
        
        const data = await response.json();
        
        if (data.status === 'success' || data.status === 'already_exists') {
            watchlistTickers = data.tickers;
            renderWatchlist();
            input.value = '';
        }
    } catch (error) {
        console.error('Error adding ticker:', error);
    }
}

async function removeTickerFromWatchlist(ticker) {
    try {
        const response = await fetch(`${API_URL}/watchlist/remove`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ticker })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            watchlistTickers = data.tickers;
            renderWatchlist();
        }
    } catch (error) {
        console.error('Error removing ticker:', error);
    }
}

async function resetWatchlist() {
    try {
        const response = await fetch(`${API_URL}/watchlist/reset`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            watchlistTickers = data.tickers;
            renderWatchlist();
        }
    } catch (error) {
        console.error('Error resetting watchlist:', error);
    }
}


// ==========================================
// SINGLE TICKER ANALYZER
// ==========================================

function initTickerAnalyzer() {
    const analyzeBtn = document.getElementById('analyzeTickerBtn');
    const analyzeInput = document.getElementById('analyzeTickerInput');
    
    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', analyzeTicker);
    }
    
    if (analyzeInput) {
        analyzeInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                analyzeTicker();
            }
        });
    }
}

async function analyzeTicker() {
    const input = document.getElementById('analyzeTickerInput');
    const resultsContainer = document.getElementById('analyzerResults');
    const ticker = input.value.trim().toUpperCase();
    
    if (!ticker) return;
    
    resultsContainer.innerHTML = '<p class="empty-state">Analyzing...</p>';
    
    try {
        const response = await fetch(`${API_URL}/scanner/analyze/${ticker}`);
        const data = await response.json();
        
        renderAnalyzerResults(data);
        
        // Also switch chart to this ticker
        changeChartSymbol(ticker);
        
    } catch (error) {
        console.error('Error analyzing ticker:', error);
        resultsContainer.innerHTML = '<p class="empty-state">Analysis failed</p>';
    }
}

function renderAnalyzerResults(data) {
    const container = document.getElementById('analyzerResults');
    
    if (!container) return;
    
    if (data.error) {
        container.innerHTML = `<p class="empty-state">${data.error}</p>`;
        return;
    }
    
    const verdict = data.overall_verdict || 'NO_SIGNAL';
    const metrics = data.current_metrics || {};
    const ursaCriteria = data.criteria_breakdown?.ursa_bearish || {};
    const taurusCriteria = data.criteria_breakdown?.taurus_bullish || {};
    
    // Determine verdict styling
    let verdictClass = 'no-signal';
    let verdictText = 'NO SIGNAL';
    
    if (verdict === 'URSA_SIGNAL') {
        verdictClass = 'ursa';
        verdictText = '🐻 URSA SIGNAL (BEARISH)';
    } else if (verdict === 'TAURUS_SIGNAL') {
        verdictClass = 'taurus';
        verdictText = '🐂 TAURUS SIGNAL (BULLISH)';
    }
    
    let html = `
        <div class="analyzer-verdict ${verdictClass}">
            <span class="verdict-ticker">${data.ticker}</span>
            <span class="verdict-result">${verdictText}</span>
        </div>
        
        <div class="analyzer-metrics">
            <div class="analyzer-metric">
                <div class="analyzer-metric-label">Price</div>
                <div class="analyzer-metric-value">$${metrics.price ?? '-'}</div>
            </div>
            <div class="analyzer-metric">
                <div class="analyzer-metric-label">SMA 200</div>
                <div class="analyzer-metric-value">$${metrics.sma_200 ?? '-'}</div>
            </div>
            <div class="analyzer-metric">
                <div class="analyzer-metric-label">VWAP</div>
                <div class="analyzer-metric-value">$${metrics.vwap_20 ?? '-'}</div>
            </div>
            <div class="analyzer-metric">
                <div class="analyzer-metric-label">ADX</div>
                <div class="analyzer-metric-value">${metrics.adx ?? '-'}</div>
            </div>
            <div class="analyzer-metric">
                <div class="analyzer-metric-label">RSI</div>
                <div class="analyzer-metric-value">${metrics.rsi ?? '-'}</div>
            </div>
            <div class="analyzer-metric">
                <div class="analyzer-metric-label">RVOL</div>
                <div class="analyzer-metric-value">${metrics.rvol ?? '-'}x</div>
            </div>
        </div>
    `;
    
    // URSA criteria breakdown
    html += `
        <div class="criteria-section">
            <div class="criteria-header ursa">🐻 URSA (Bearish) Criteria</div>
            ${renderCriteriaList(ursaCriteria)}
        </div>
    `;
    
    // TAURUS criteria breakdown
    html += `
        <div class="criteria-section">
            <div class="criteria-header taurus">🐂 TAURUS (Bullish) Criteria</div>
            ${renderCriteriaList(taurusCriteria)}
        </div>
    `;
    
    // Near miss info if no signal
    if (verdict === 'NO_SIGNAL' && data.near_miss) {
        html += `
            <div class="near-miss">
                <div class="near-miss-title">Criteria Met</div>
                <div class="near-miss-counts">
                    <span class="near-miss-ursa">URSA: ${data.near_miss.ursa_criteria_met}</span>
                    <span class="near-miss-taurus">TAURUS: ${data.near_miss.taurus_criteria_met}</span>
                </div>
            </div>
        `;
    }
    
    container.innerHTML = html;
}

function renderCriteriaList(criteria) {
    let html = '';
    
    for (const [key, value] of Object.entries(criteria)) {
        if (key === 'ALL_PASSED') continue;
        if (typeof value !== 'object') continue;
        
        const passed = value.passed;
        const statusIcon = passed ? '✅' : '❌';
        const statusClass = passed ? 'pass' : 'fail';
        
        html += `
            <div class="criteria-item">
                <span class="criteria-status ${statusClass}">${statusIcon}</span>
                <div class="criteria-content">
                    <div class="criteria-name">${value.description}</div>
                    <div class="criteria-detail">${value.current} (Need: ${value.required})</div>
                </div>
            </div>
        `;
    }
    
    return html;
}


// ==========================================
// STRATEGY CONTROLS
// ==========================================

let strategiesData = {};

function initStrategies() {
    const enableAllBtn = document.getElementById('enableAllBtn');
    const disableAllBtn = document.getElementById('disableAllBtn');
    
    if (enableAllBtn) {
        enableAllBtn.addEventListener('click', enableAllStrategies);
    }
    
    if (disableAllBtn) {
        disableAllBtn.addEventListener('click', disableAllStrategies);
    }
    
    loadStrategies();
}

async function loadStrategies() {
    try {
        const response = await fetch(`${API_URL}/strategies`);
        const data = await response.json();
        
        if (data.status === 'success') {
            strategiesData = data.strategies;
            renderStrategies();
        }
    } catch (error) {
        console.error('Error loading strategies:', error);
        document.getElementById('strategiesGrid').innerHTML = 
            '<p class="empty-state">Failed to load strategies</p>';
    }
}

function renderStrategies() {
    const container = document.getElementById('strategiesGrid');
    
    if (!container) return;
    
    const strategyIds = Object.keys(strategiesData);
    
    if (strategyIds.length === 0) {
        container.innerHTML = '<p class="empty-state">No strategies configured</p>';
        return;
    }
    
    container.innerHTML = strategyIds.map(id => {
        const strategy = strategiesData[id];
        const enabled = strategy.enabled;
        const category = strategy.category || 'other';
        
        return `
            <div class="strategy-card ${enabled ? 'enabled' : 'disabled'}" data-strategy-id="${id}">
                <div class="strategy-card-header">
                    <span class="strategy-name">${strategy.name}</span>
                    <label class="strategy-toggle">
                        <input type="checkbox" ${enabled ? 'checked' : ''} data-strategy-id="${id}">
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                <div class="strategy-description">${strategy.description}</div>
                <div class="strategy-meta">
                    <span class="strategy-badge ${category}">${category}</span>
                    ${strategy.timeframes ? strategy.timeframes.map(tf => 
                        `<span class="strategy-badge">${tf}</span>`
                    ).join('') : ''}
                </div>
            </div>
        `;
    }).join('');
    
    // Attach toggle events
    container.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
        checkbox.addEventListener('change', (e) => {
            toggleStrategy(e.target.dataset.strategyId, e.target.checked);
        });
    });
}

async function toggleStrategy(strategyId, enabled) {
    try {
        const response = await fetch(`${API_URL}/strategies/${strategyId}/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enabled })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            // Update local state
            strategiesData[strategyId].enabled = enabled;
            
            // Update card styling
            const card = document.querySelector(`.strategy-card[data-strategy-id="${strategyId}"]`);
            if (card) {
                card.classList.toggle('enabled', enabled);
                card.classList.toggle('disabled', !enabled);
            }
            
            console.log(`Strategy ${strategyId} ${enabled ? 'enabled' : 'disabled'}`);
        }
    } catch (error) {
        console.error('Error toggling strategy:', error);
        // Revert checkbox
        const checkbox = document.querySelector(`input[data-strategy-id="${strategyId}"]`);
        if (checkbox) {
            checkbox.checked = !enabled;
        }
    }
}

async function enableAllStrategies() {
    try {
        const response = await fetch(`${API_URL}/strategies/enable-all`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            loadStrategies();
            console.log('All strategies enabled');
        }
    } catch (error) {
        console.error('Error enabling all strategies:', error);
    }
}

async function disableAllStrategies() {
    if (!confirm('⚠️ KILL SWITCH: This will disable ALL strategies. Continue?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/strategies/disable-all`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            loadStrategies();
            console.log('🛑 All strategies DISABLED');
        }
    } catch (error) {
        console.error('Error disabling all strategies:', error);
    }
}

// Initialize strategies on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initStrategies, 800);
    setTimeout(initCtaScanner, 900);
    setTimeout(initBtcSignals, 1000);
});


// ==========================================
// CTA SCANNER (Equity Swing Trading)
// ==========================================

let ctaResults = {
    goldenTouch: [],
    twoClose: [],
    pullback: [],
    zoneUpgrade: []
};

let ctaZones = {};

function initCtaScanner() {
    const runCtaScanBtn = document.getElementById('runCtaScanBtn');
    if (runCtaScanBtn) {
        runCtaScanBtn.addEventListener('click', runCtaScan);
    }
    
    // Load CTA zone data for watchlist tickers
    loadCtaZones();
}

async function loadCtaZones() {
    const watchlistTickers = ['SPY', 'QQQ', 'AAPL', 'MSFT', 'NVDA'];
    const zoneCardsContainer = document.getElementById('ctaZoneCards');
    
    if (!zoneCardsContainer) return;
    
    for (const ticker of watchlistTickers) {
        try {
            const response = await fetch(`${API_URL}/cta/analyze/${ticker}`);
            const data = await response.json();
            
            if (data.cta_analysis) {
                ctaZones[ticker] = data.cta_analysis;
            }
        } catch (error) {
            console.error(`Error loading CTA zone for ${ticker}:`, error);
        }
    }
    
    renderCtaZones();
}

function renderCtaZones() {
    const container = document.getElementById('ctaZoneCards');
    if (!container) return;
    
    const tickers = Object.keys(ctaZones);
    
    if (tickers.length === 0) {
        container.innerHTML = `
            <div class="cta-zone-card">
                <span class="zone-ticker">SPY</span>
                <span class="zone-status loading">Loading...</span>
            </div>
        `;
        return;
    }
    
    container.innerHTML = tickers.map(ticker => {
        const zone = ctaZones[ticker];
        const zoneStatus = zone.cta_zone || 'UNKNOWN';
        
        return `
            <div class="cta-zone-card ${zoneStatus}" data-ticker="${ticker}">
                <span class="zone-ticker">${ticker}</span>
                <span class="zone-status ${zoneStatus}">${zoneStatus.replace('_', ' ')}</span>
            </div>
        `;
    }).join('');
    
    // Attach click events to view on chart
    container.querySelectorAll('.cta-zone-card').forEach(card => {
        card.addEventListener('click', () => {
            const ticker = card.dataset.ticker;
            changeChartSymbol(ticker);
        });
    });
}

async function runCtaScan() {
    const btn = document.getElementById('runCtaScanBtn');
    const status = document.getElementById('ctaScanStatus');
    
    btn.disabled = true;
    btn.textContent = 'Scanning...';
    status.textContent = 'Scanning watchlist + S&P 500...';
    status.classList.add('scanning');
    
    try {
        const response = await fetch(`${API_URL}/cta/scan?include_watchlist=true`);
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        // Store results by signal type
        ctaResults.goldenTouch = data.golden_touch_signals || [];
        ctaResults.twoClose = data.two_close_signals || [];
        ctaResults.pullback = data.pullback_signals || [];
        ctaResults.zoneUpgrade = data.zone_upgrade_signals || [];
        
        renderCtaResults();
        
        status.textContent = `Found ${data.total_signals} signals`;
        status.classList.remove('scanning');
        
    } catch (error) {
        console.error('CTA scan error:', error);
        status.textContent = 'Scan failed';
        status.classList.remove('scanning');
    } finally {
        btn.disabled = false;
        btn.textContent = 'Run Scan';
    }
}

function renderCtaResults() {
    renderCtaColumn('goldenSignals', 'goldenCount', ctaResults.goldenTouch, 'Rare: 120 SMA first touch');
    renderCtaColumn('twoCloseSignals', 'twoCloseCount', ctaResults.twoClose, 'No confirmed breakouts');
    renderCtaColumn('pullbackSignals', 'pullbackCount', ctaResults.pullback, 'No pullbacks to 20 SMA');
}

function renderCtaColumn(containerId, countId, signals, emptyMessage) {
    const container = document.getElementById(containerId);
    const countEl = document.getElementById(countId);
    
    if (!container) return;
    
    countEl.textContent = signals.length;
    
    if (signals.length === 0) {
        container.innerHTML = `<p class="empty-state">${emptyMessage}</p>`;
        return;
    }
    
    container.innerHTML = signals.slice(0, 5).map(signal => createCtaCard(signal)).join('');
    
    // Attach click events
    container.querySelectorAll('.cta-ticker').forEach(ticker => {
        ticker.addEventListener('click', (e) => {
            e.stopPropagation();
            changeChartSymbol(e.target.dataset.symbol);
        });
    });
}

function createCtaCard(signal) {
    const setup = signal.setup || {};
    const context = signal.context || {};
    
    return `
        <div class="cta-card" data-symbol="${signal.symbol}">
            <div class="cta-card-header">
                <span class="cta-ticker" data-symbol="${signal.symbol}">${signal.symbol}</span>
                <span class="cta-score">${signal.priority}</span>
            </div>
            <div class="cta-card-body">
                <div class="cta-metric">
                    <div class="cta-metric-label">Entry</div>
                    <div class="cta-metric-value">$${setup.entry?.toFixed(2) || '-'}</div>
                </div>
                <div class="cta-metric">
                    <div class="cta-metric-label">Stop</div>
                    <div class="cta-metric-value">$${setup.stop?.toFixed(2) || '-'}</div>
                </div>
                <div class="cta-metric">
                    <div class="cta-metric-label">R:R</div>
                    <div class="cta-metric-value">${setup.rr_ratio || '-'}:1</div>
                </div>
            </div>
            <div class="cta-card-footer">
                Zone: ${context.cta_zone || 'Unknown'} • Vol: ${context.volume_ratio?.toFixed(1) || '-'}x
            </div>
        </div>
    `;
}


// ==========================================
// BTC BOTTOM SIGNALS DASHBOARD
// ==========================================

let btcSignals = {};
let btcSummary = {};

function initBtcSignals() {
    const refreshBtn = document.getElementById('refreshBtcSignalsBtn');
    const resetBtn = document.getElementById('resetBtcSignalsBtn');
    
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadBtcSignals);
    }
    
    if (resetBtn) {
        resetBtn.addEventListener('click', resetBtcSignals);
    }
    
    // Initial load
    loadBtcSignals();
    loadBtcSessions();
}

async function loadBtcSignals() {
    try {
        const response = await fetch(`${API_URL}/btc/bottom-signals`);
        const data = await response.json();
        
        btcSignals = data.signals || {};
        btcSummary = data.summary || {};
        
        renderBtcSignals();
        renderBtcSummary();
        
    } catch (error) {
        console.error('Error loading BTC signals:', error);
        document.getElementById('btcSignalsGrid').innerHTML = 
            '<p class="empty-state">Failed to load signals</p>';
    }
}

function renderBtcSummary() {
    const container = document.getElementById('btcConfluenceSummary');
    if (!container) return;
    
    const firingCount = btcSummary.firing_count || 0;
    const totalSignals = btcSummary.total_signals || 9;
    const verdict = btcSummary.verdict || 'Checking signals...';
    
    // Determine verdict class
    let verdictClass = 'none';
    if (firingCount >= 6) verdictClass = 'strong';
    else if (firingCount >= 4) verdictClass = 'moderate';
    else if (firingCount >= 2) verdictClass = 'weak';
    
    container.innerHTML = `
        <div class="confluence-meter">
            <span class="confluence-count">${firingCount}/${totalSignals}</span>
            <span class="confluence-label">Signals Firing</span>
        </div>
        <div class="confluence-verdict ${verdictClass}">${verdict}</div>
    `;
}

function renderBtcSignals() {
    const container = document.getElementById('btcSignalsGrid');
    if (!container) return;
    
    const signalIds = Object.keys(btcSignals);
    
    if (signalIds.length === 0) {
        container.innerHTML = '<p class="empty-state">No signals configured</p>';
        return;
    }
    
    container.innerHTML = signalIds.map(id => {
        const signal = btcSignals[id];
        const status = signal.status || 'UNKNOWN';
        
        return `
            <div class="btc-signal-card ${status}" data-signal-id="${id}">
                <div class="btc-signal-header">
                    <span class="btc-signal-name">${signal.name}</span>
                    <span class="btc-signal-status ${status}">${status}</span>
                </div>
                <div class="btc-signal-description">${signal.description}</div>
                <div class="btc-signal-meta">
                    <span class="btc-signal-threshold">Threshold: ${signal.threshold}</span>
                    ${signal.value !== null ? `<span class="btc-signal-value">${signal.value}</span>` : ''}
                </div>
                <div class="btc-signal-source">Source: ${signal.source}</div>
            </div>
        `;
    }).join('');
    
    // Attach click events for manual toggle
    container.querySelectorAll('.btc-signal-card').forEach(card => {
        card.addEventListener('click', () => {
            toggleBtcSignal(card.dataset.signalId);
        });
    });
}

async function toggleBtcSignal(signalId) {
    const currentStatus = btcSignals[signalId]?.status || 'UNKNOWN';
    
    // Cycle through: UNKNOWN -> FIRING -> NEUTRAL -> UNKNOWN
    let newStatus;
    if (currentStatus === 'UNKNOWN' || currentStatus === 'NEUTRAL') {
        newStatus = 'FIRING';
    } else {
        newStatus = 'NEUTRAL';
    }
    
    try {
        const response = await fetch(`${API_URL}/btc/bottom-signals/${signalId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            // Reload all signals to update summary
            loadBtcSignals();
        }
    } catch (error) {
        console.error('Error toggling BTC signal:', error);
    }
}

async function resetBtcSignals() {
    if (!confirm('Reset all manual BTC signals to UNKNOWN?')) return;
    
    try {
        await fetch(`${API_URL}/btc/bottom-signals/reset`, { method: 'POST' });
        loadBtcSignals();
    } catch (error) {
        console.error('Error resetting BTC signals:', error);
    }
}

async function loadBtcSessions() {
    try {
        const response = await fetch(`${API_URL}/btc/sessions`);
        const data = await response.json();
        
        renderBtcSessions(data);
        
    } catch (error) {
        console.error('Error loading BTC sessions:', error);
    }
}

function renderBtcSessions(data) {
    const currentContainer = document.getElementById('btcSessionCurrent');
    const listContainer = document.getElementById('btcSessionList');
    
    if (!currentContainer || !listContainer) return;
    
    // Current session
    if (data.current_session && data.current_session.active) {
        currentContainer.classList.add('active');
        currentContainer.innerHTML = `
            <span class="session-status">🟢 NOW: ${data.current_session.name}</span>
            <div style="font-size: 11px; color: var(--text-secondary); margin-top: 4px;">
                ${data.current_session.trading_note}
            </div>
        `;
    } else {
        currentContainer.classList.remove('active');
        currentContainer.innerHTML = `
            <span class="session-status">No active key session</span>
        `;
    }
    
    // Session list
    const sessions = data.sessions || {};
    const sessionIds = Object.keys(sessions);
    
    listContainer.innerHTML = sessionIds.map(id => {
        const session = sessions[id];
        return `
            <div class="btc-session-item">
                <div class="session-name">${session.name}</div>
                <div class="session-time">${session.ny_time} ET</div>
                <div class="session-note">${session.trading_note}</div>
            </div>
        `;
    }).join('');
}
