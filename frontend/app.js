/**
 * Pandora's Box - Frontend Application
 * Real-time WebSocket connection for multi-device sync
 */

// Configuration
// Resolve backend from current host so /app and /app/crypto always hit the same deployment.
const IS_HTTPS = window.location.protocol === 'https:';
const WS_URL = `${IS_HTTPS ? 'wss' : 'ws'}://${window.location.host}/ws`;
const API_URL = `${window.location.origin}/api`;

const BIAS_COLORS = {
    TORO_MAJOR: { bg: '#0a2e1a', accent: '#00e676', text: '#00e676' },
    TORO_MINOR: { bg: '#1a2e1a', accent: '#66bb6a', text: '#66bb6a' },
    NEUTRAL:    { bg: '#1a2228', accent: '#78909c', text: '#78909c' },
    URSA_MINOR: { bg: '#2e1a0a', accent: '#ff9800', text: '#ff9800' },
    URSA_MAJOR: { bg: '#2e0a0a', accent: '#e5370e', text: '#e5370e' },
};

const CONFIDENCE_COLORS = {
    HIGH: '#00e676',
    MEDIUM: '#ff9800',
    LOW: '#e5370e',
};

const COMPOSITE_FACTOR_DISPLAY_ORDER = [
    // Intraday
    'vix_term',
    'tick_breadth',
    'vix_regime',
    'spy_trend_intraday',
    'breadth_momentum',
    'options_sentiment',
    // Swing
    'credit_spreads',
    'market_breadth',
    'sector_rotation',
    'spy_200sma_distance',
    'high_yield_oas',
    'dollar_smile',
    'put_call_ratio',
    // Macro
    'yield_curve',
    'initial_claims',
    'sahm_rule',
    'copper_gold_ratio',
    'excess_cape',
    'ism_manufacturing',
    'savita'
];

// Shared helpers
function escapeHtml(value) {
    if (value === null || value === undefined) return '';
    return String(value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/\"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function formatChange(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '-';
    const num = Number(value);
    const sign = num > 0 ? '+' : '';
    return `${sign}${num.toFixed(2)}%`;
}

function changeColor(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '#78909c';
    const num = Number(value);
    if (num > 0) return '#4caf50';
    if (num < 0) return '#e5370e';
    return '#78909c';
}

function normalizeRiskReward(value) {
    if (value === null || value === undefined || value === '') return null;
    const num = Number.parseFloat(value);
    if (!Number.isFinite(num)) return null;
    const normalized = Math.abs(num);
    return normalized > 0 ? normalized : null;
}

function formatRiskReward(value) {
    const normalized = normalizeRiskReward(value);
    return normalized ? `${normalized.toFixed(1)}:1` : '-';
}

// State
let ws = null;
let tvWidget = null;
let currentSymbol = 'SPY';
let currentTimeframe = 'WEEKLY';
let activeAssetType = 'equity';
const APP_MODES = {
    HUB: 'hub',
    CRYPTO: 'crypto',
    ANALYTICS: 'analytics'
};
let signals = {
    equity: [],
    crypto: []
};
const TRADE_IDEAS_PAGE_SIZE = 10;
let tradeIdeasPagination = {
    equity: { offset: 0, limit: TRADE_IDEAS_PAGE_SIZE, hasMore: true, loading: false },
    crypto: { offset: 0, limit: TRADE_IDEAS_PAGE_SIZE, hasMore: true, loading: false }
};

// Price levels to display on chart (entry, stop, target)
let activePriceLevels = null;
let tvLevelShapes = [];

// Weekly Bias Factor State
let weeklyBiasFullData = null; // Stores complete weekly bias data with factors
let weeklyBiasFactorStates = {
    index_trends: true,
    dollar_trend: true,
    sector_rotation: true,
    credit_spreads: true,
    market_breadth: true,
    vix_term_structure: true
};

// Daily Bias Factor State
let dailyBiasFullData = null;
let dailyBiasFactorStates = {
    spy_rsi: true,
    vix_level: true,
    tech_leadership: true,
    small_cap_risk: true,
    spy_trend: true,
    market_breadth: true,
    tick_breadth: true
};

// Composite Bias API response cache (used by crypto bias bar without needing DOM from hub)
let _compositeBiasData = null;
let _dailyBiasPrimaryData = null;

// Keep a reference to open positions for crypto rendering
let _open_positions_cache = [];
let cryptoMarketData = null;
let cryptoMarketTimer = null;
let cryptoMarketLastGood = {};
let cryptoWma9 = null;
let cryptoWmaUpdated = null;
let cryptoWmaTimer = null;
let cryptoWmaLoading = false;
const CRYPTO_MARKET_POLL_MS = 5 * 1000;

// Cyclical Bias Factor State
let cyclicalBiasFullData = null;
let cyclicalBiasFactorStates = {
    sma_200_positions: true,
    yield_curve: true,
    credit_spreads: true,
    excess_cape_yield: true,
    savita_indicator: true,
    longterm_breadth: true,
    sahm_rule: true
};

// Personal Bias & Override State
let personalBias = 'NEUTRAL';  // NEUTRAL, TORO, URSA
let biasOverrideActive = false;
let biasOverrideDirection = 'MAJOR_TORO';  // MAJOR_TORO or MAJOR_URSA

// Per-timeframe personal bias toggles (default: apply to all)
let personalBiasAppliesTo = {
    daily: true,
    weekly: true,
    cyclical: true
};

// Scout Alert State
let scoutAlerts = [];
const SCOUT_ALERT_MAX_VISIBLE = 3;
const SCOUT_ALERT_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes
let manualPositionContext = 'equity';

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    // Bind critical UI interactions first so mode switches still work
    // even if downstream initializers fail.
    try {
        initRouting();
    } catch (error) {
        console.error('initRouting failed:', error);
    }

    try {
        initEventListeners();
    } catch (error) {
        console.error('initEventListeners failed:', error);
    }

    try {
        initTradingViewWidget();
    } catch (error) {
        console.error('initTradingViewWidget failed:', error);
    }

    try {
        initWebSocket();
    } catch (error) {
        console.error('initWebSocket failed:', error);
    }

    Promise.resolve(loadInitialData()).catch((error) => {
        console.error('loadInitialData failed:', error);
    });

    try {
        initCryptoScalper();
    } catch (error) {
        console.error('initCryptoScalper failed:', error);
    }

    // Portfolio tracker (Brief 07-E)
    try {
        loadPortfolioBalances();
        loadPortfolioPositions();
    } catch (error) {
        console.error('Portfolio load failed:', error);
    }
});

function initRouting() {
    const modeFromPath = getModeFromPath();
    const storedMode = localStorage.getItem('pandoraAppMode');
    const initialMode = modeFromPath || storedMode || APP_MODES.HUB;

    setMode(initialMode, { replace: true });

    window.addEventListener('popstate', () => {
        const nextMode = getModeFromPath() || localStorage.getItem('pandoraAppMode') || APP_MODES.HUB;
        setMode(nextMode, { skipHistory: true });
    });
}

function getModeFromPath() {
    const path = window.location.pathname.replace(/\/$/, '');
    if (path.endsWith('/analytics')) return APP_MODES.ANALYTICS;
    if (path.endsWith('/crypto')) return APP_MODES.CRYPTO;
    if (path.endsWith('/hub')) return APP_MODES.HUB;
    return null;
}

function getModeBasePath() {
    const path = window.location.pathname.replace(/\/$/, '');
    if (path.endsWith('/analytics')) return path.slice(0, -10) || '';
    if (path.endsWith('/crypto')) return path.slice(0, -7) || '';
    if (path.endsWith('/hub')) return path.slice(0, -4) || '';
    return path || '';
}

function buildModePath(mode) {
    const basePath = getModeBasePath();
    const safeBase = basePath === '/' ? '' : basePath;
    return `${safeBase}/${mode}`.replace(/\/+/g, '/');
}

function setMode(mode, options = {}) {
    let nextMode = APP_MODES.HUB;
    if (mode === APP_MODES.CRYPTO) nextMode = APP_MODES.CRYPTO;
    if (mode === APP_MODES.ANALYTICS) nextMode = APP_MODES.ANALYTICS;
    document.body.dataset.mode = nextMode;

    const hubShell = document.getElementById('hubShell');
    const cryptoShell = document.getElementById('cryptoShell');
    const analyticsShell = document.getElementById('analyticsShell');
    if (hubShell) hubShell.hidden = nextMode !== APP_MODES.HUB;
    if (cryptoShell) cryptoShell.hidden = nextMode !== APP_MODES.CRYPTO;
    if (analyticsShell) analyticsShell.hidden = nextMode !== APP_MODES.ANALYTICS;

    const hubBtn = document.getElementById('modeHubBtn');
    const cryptoBtn = document.getElementById('modeCryptoBtn');
    const analyticsBtn = document.getElementById('modeAnalyticsBtn');
    if (hubBtn && cryptoBtn && analyticsBtn) {
        hubBtn.classList.toggle('active', nextMode === APP_MODES.HUB);
        cryptoBtn.classList.toggle('active', nextMode === APP_MODES.CRYPTO);
        analyticsBtn.classList.toggle('active', nextMode === APP_MODES.ANALYTICS);
        hubBtn.setAttribute('aria-selected', nextMode === APP_MODES.HUB);
        cryptoBtn.setAttribute('aria-selected', nextMode === APP_MODES.CRYPTO);
        analyticsBtn.setAttribute('aria-selected', nextMode === APP_MODES.ANALYTICS);
    }

    localStorage.setItem('pandoraAppMode', nextMode);

    if (!options.skipHistory) {
        const targetPath = buildModePath(nextMode);
        const currentPath = window.location.pathname;
        if (currentPath !== targetPath) {
            if (options.replace || currentPath === '/' || currentPath === '') {
                window.history.replaceState({}, '', targetPath);
            } else {
                window.history.pushState({}, '', targetPath);
            }
        }
    }

    renderCryptoSignals();
    renderCryptoBiasSummary();

    // Only poll the crypto market endpoint while the crypto view is active.
    // This keeps the 5s update cadence without burning API calls in Hub mode.
    if (nextMode === APP_MODES.CRYPTO) {
        startCryptoMarketPolling();
    } else {
        stopCryptoMarketPolling();
    }

    // Initialize crypto chart when switching to crypto mode
    if (nextMode === APP_MODES.CRYPTO && !cryptoTvWidget) {
        setTimeout(initCryptoChart, 200);
    }

    try {
        document.dispatchEvent(new CustomEvent('pandora:modechange', { detail: { mode: nextMode } }));
    } catch (error) {
        console.warn('Mode change event dispatch failed:', error);
    }
}

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
        autosize: true,
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

    // Best-effort: draw levels if the widget supports it
    if (tvWidget && typeof tvWidget.onChartReady === 'function') {
        tvWidget.onChartReady(() => {
            drawLevelsOnChart();
        });
    }
}

function changeChartSymbol(symbol) {
    currentSymbol = symbol;
    
    // Update tab active state
    document.querySelectorAll('.chart-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.symbol === symbol);
    });
    
    // Update price levels panel for this symbol
    updatePriceLevelsPanel(symbol);
    
    // Reinitialize widget with new symbol
    initTradingViewWidget();
}

function getTickerFromSymbol(symbol) {
    if (!symbol) return symbol;
    const upper = symbol.toUpperCase();
    if (upper.endsWith('USDT')) return upper.slice(0, -4);
    if (upper.endsWith('USD')) return upper.slice(0, -3);
    return upper;
}

function updatePriceLevelsPanel(symbol) {
    const panel = document.getElementById('priceLevelsPanel');
    if (!panel) return;
    
    // Check if we have price levels for this symbol
    const tickerKey = getTickerFromSymbol(symbol);
    const levels = window.activePriceLevels?.[tickerKey];
    
    if (levels) {
        // Show panel with levels
        panel.style.display = 'block';
        document.getElementById('priceLevelsTicker').textContent = tickerKey;
        document.getElementById('priceLevelEntry').textContent = levels.entry ? `$${parseFloat(levels.entry).toFixed(2)}` : '--';
        document.getElementById('priceLevelStop').textContent = levels.stop ? `$${parseFloat(levels.stop).toFixed(2)}` : '--';
        document.getElementById('priceLevelTarget1').textContent = levels.target1 ? `$${parseFloat(levels.target1).toFixed(2)}` : '--';
        
        const target2Row = document.getElementById('priceLevelTarget2Row');
        if (levels.target2) {
            document.getElementById('priceLevelTarget2').textContent = `$${parseFloat(levels.target2).toFixed(2)}`;
            target2Row.style.display = 'flex';
        } else {
            target2Row.style.display = 'none';
        }
    } else {
        // Check if there's an open position for this symbol
        const position = openPositions.find(p => (p.ticker || '').toUpperCase() === tickerKey);
        if (position) {
            panel.style.display = 'block';
            document.getElementById('priceLevelsTicker').textContent = tickerKey;
            document.getElementById('priceLevelEntry').textContent = position.entry_price ? `$${parseFloat(position.entry_price).toFixed(2)}` : '--';
            document.getElementById('priceLevelStop').textContent = position.stop_loss ? `$${parseFloat(position.stop_loss).toFixed(2)}` : '--';
            document.getElementById('priceLevelTarget1').textContent = position.target_1 ? `$${parseFloat(position.target_1).toFixed(2)}` : '--';
            
            const target2Row = document.getElementById('priceLevelTarget2Row');
            if (position.target_2) {
                document.getElementById('priceLevelTarget2').textContent = `$${parseFloat(position.target_2).toFixed(2)}`;
                target2Row.style.display = 'flex';
            } else {
                target2Row.style.display = 'none';
            }
        } else {
            // No levels for this symbol - hide panel
            panel.style.display = 'none';
        }
    }

    // Best-effort: update chart lines if supported
    drawLevelsOnChart();
}

function showTradeOnChart(signal) {
    // Change to the signal's ticker
    const symbol = signal.asset_class === 'CRYPTO' 
        ? signal.ticker + 'USD' 
        : signal.ticker;
    
    currentSymbol = symbol;
    
    // Store price levels to display
    storePriceLevels(signal.ticker, {
        entry: signal.entry_price,
        stop: signal.stop_loss,
        target1: signal.target_1,
        target2: signal.target_2
    });
    
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
    
    console.log(`ðŸ“Š Showing ${signal.ticker} on chart with levels:`, window.activePriceLevels?.[signal.ticker]);
}

function clearChartLevels() {
    if (!tvWidget || typeof tvWidget.activeChart !== 'function') {
        tvLevelShapes = [];
        return;
    }

    try {
        const chart = tvWidget.activeChart();
        if (!chart || typeof chart.removeEntity !== 'function') {
            tvLevelShapes = [];
            return;
        }

        for (const id of tvLevelShapes) {
            try {
                chart.removeEntity(id);
            } catch {
                // ignore best-effort cleanup
            }
        }
    } catch {
        // ignore best-effort cleanup
    }

    tvLevelShapes = [];
}

function drawLevelsOnChart() {
    if (!tvWidget || typeof tvWidget.activeChart !== 'function') {
        return;
    }

    const tickerKey = getTickerFromSymbol(currentSymbol);
    const levels = window.activePriceLevels?.[tickerKey];
    if (!levels) {
        clearChartLevels();
        return;
    }

    try {
        const chart = tvWidget.activeChart();
        if (!chart || typeof chart.createShape !== 'function') {
            return;
        }

        clearChartLevels();

        const shapes = [
            { price: levels.entry, color: '#22c55e', text: 'Entry' },
            { price: levels.stop, color: '#e5370e', text: 'Stop' },
            { price: levels.target1, color: '#3b82f6', text: 'Target' },
            { price: levels.target2, color: '#6366f1', text: 'Target 2' }
        ];

        for (const shape of shapes) {
            if (!shape.price) continue;
            const id = chart.createShape(
                { price: shape.price },
                {
                    shape: 'horizontal_line',
                    text: shape.text,
                    lock: true,
                    disableSelection: true,
                    disableSave: true,
                    overrides: {
                        linecolor: shape.color,
                        linewidth: 2
                    }
                }
            );
            if (id) tvLevelShapes.push(id);
        }
    } catch {
        // Widget may not support drawings; ignore
    }
}

// WebSocket Connection
function initWebSocket() {
    console.log('ðŸ”Œ Connecting to Pandora\'s Box...');
    
    ws = new WebSocket(WS_URL);
    
    ws.onopen = () => {
        console.log('âœ… Connected to backend');
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
            console.warn('âš ï¸ Non-JSON message received:', event.data);
        }
    };
    
    ws.onerror = (error) => {
        console.error('âŒ WebSocket error:', error);
        updateConnectionStatus(false);
    };
    
    ws.onclose = () => {
        console.log('ðŸ”Œ Connection closed. Reconnecting...');
        updateConnectionStatus(false);
        
        // Reconnect after 3 seconds
        setTimeout(initWebSocket, 3000);
    };
}

function handleWebSocketMessage(message) {
    console.log('ðŸ“¨ Received:', message);
    
    switch (message.type) {
        case 'NEW_SIGNAL':
            // Add signal and check if it should jump to top 10
            handleNewSignal(message.data);
            break;
        case 'SIGNAL_PRIORITY_UPDATE':
            // New high-priority signal that should be shown immediately
            handlePrioritySignal(message.data);
            break;
        case 'SIGNAL_ACCEPTED':
            // Signal was accepted by user, remove from feed and refill
            removeSignal(message.signal_id);
            refillTradeIdeas();
            break;
        case 'SIGNAL_DISMISSED':
            // Signal was dismissed, remove from feed
            removeSignal(message.signal_id);
            refillTradeIdeas();
            break;
        case 'BIAS_UPDATE':
            if (message.data && typeof message.data.bias_level !== 'undefined' && typeof message.data.composite_score !== 'undefined') {
                fetchCompositeBias();
                flashCompositeBanner();
            } else {
                // Handle weekly bias updates with factor filtering
                if (message.data.timeframe === 'weekly' || message.data.timeframe === 'WEEKLY') {
                    checkAndResetFactorsForNewDay(message.data);
                    weeklyBiasFullData = message.data;
                    updateWeeklyBiasWithFactors(message.data);
                } else {
                    updateBias(message.data);
                }
                // Also refresh shift status when bias updates
                fetchBiasShiftStatus();
            }
            break;
        case 'POSITION_UPDATE':
            updatePosition(message.data);
            break;
        case 'SCOUT_ALERT':
            displayScoutAlert(message.data);
            // Also feed Scout into Trade Ideas stream in real time.
            handleNewSignal(message.data);
            break;
        case 'FLOW_UPDATE':
            // New flow data from Discord bot via UW - refresh the Options Flow section
            console.log(`ðŸ‹ Flow update: ${message.count} tickers (${(message.tickers_updated || []).join(', ')})`);
            loadFlowData();
            checkFlowStatus();
            break;
    }
}

// Audio alert for new signals (uses Web Audio API â€” no file needed)
function playSignalAlert(priority = false) {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.type = 'sine';
        gain.gain.value = 0.12;

        if (priority) {
            // Priority signal: two-tone rising chime
            osc.frequency.value = 660;
            osc.start(ctx.currentTime);
            osc.frequency.setValueAtTime(880, ctx.currentTime + 0.15);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.4);
            osc.stop(ctx.currentTime + 0.4);
        } else {
            // Regular signal entering top 10: single soft tone
            osc.frequency.value = 880;
            osc.start(ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.25);
            osc.stop(ctx.currentTime + 0.25);
        }
    } catch (e) { /* Audio not available */ }
}

function handleNewSignal(signalData) {
    if (!signalData || !signalData.signal_id) return;

    const isScout = (signalData.signal_type || '').toUpperCase() === 'SCOUT_ALERT'
        || (signalData.strategy || '').toLowerCase().includes('scout');

    // Add to appropriate signal list
    if (signalData.asset_class === 'EQUITY' || !signalData.asset_class) {
        signals.equity = signals.equity.filter(s => s.signal_id !== signalData.signal_id);
        // Check if this signal should jump into top 10
        const currentLowestScore = getLowestDisplayedScore();
        const newScore = signalData.score || 0;

        if (newScore > currentLowestScore || signals.equity.length < 10) {
            // Insert at correct position based on score
            insertSignalByScore(signalData, 'equity');
            refreshSignalViews();

            // Highlight new signal with animation + sound
            highlightNewSignal(signalData.signal_id);
            playSignalAlert(false);
        } else {
            // Add to queue but don't display
            signals.equity.push(signalData);
        }
    } else {
        signals.crypto = signals.crypto.filter(s => s.signal_id !== signalData.signal_id);
        signals.crypto.push(signalData);
        refreshSignalViews();
    }

    // Auto-dismiss Scout alert if a real signal fires for the same ticker
    if (!isScout && signalData.ticker) {
        dismissScoutAlertByTicker(signalData.ticker);
    }
}

function handlePrioritySignal(signalData) {
    // High-priority signal - insert at top with animation
    console.log('ðŸ”¥ Priority signal received:', signalData.ticker, signalData.score);
    
    if (signalData.asset_class === 'EQUITY' || !signalData.asset_class) {
        // Remove if already exists
        signals.equity = signals.equity.filter(s => s.signal_id !== signalData.signal_id);
        // Insert at top (newest signals always first)
        signals.equity.unshift(signalData);
    } else {
        signals.crypto = signals.crypto.filter(s => s.signal_id !== signalData.signal_id);
        signals.crypto.unshift(signalData);
    }
    
    refreshSignalViews();
    highlightNewSignal(signalData.signal_id);
    playSignalAlert(true);
}

function getLowestDisplayedScore() {
    const displayed = signals.equity.slice(0, 10);
    if (displayed.length < 10) return 0;
    return displayed.reduce((min, s) => Math.min(min, s.score || 0), 100);
}

function insertSignalByScore(signalData, type) {
    const list = type === 'equity' ? signals.equity : signals.crypto;
    
    // Remove if already exists
    const filtered = list.filter(s => s.signal_id !== signalData.signal_id);
    
    // Find insert position
    let insertIdx = filtered.findIndex(s => (s.score || 0) < (signalData.score || 0));
    if (insertIdx === -1) insertIdx = filtered.length;
    
    // Insert
    filtered.splice(insertIdx, 0, signalData);
    
    if (type === 'equity') {
        signals.equity = filtered;
    } else {
        signals.crypto = filtered;
    }
}

function highlightNewSignal(signalId) {
    setTimeout(() => {
        const card = document.querySelector(`[data-signal-id="${signalId}"]`);
        if (card) {
            card.classList.add('new-signal-highlight');
            setTimeout(() => card.classList.remove('new-signal-highlight'), 3000);
        }
    }, 100);
}

// ============================================
// SCOUT ALERT FUNCTIONS
// Early warning signals (15m) before main Sniper (1H)
// ============================================

function displayScoutAlert(data) {
    console.log('ðŸ”­ Scout Alert received:', data.ticker, data.direction);

    // Check if we already have a scout alert for this ticker
    const existingIndex = scoutAlerts.findIndex(a => a.ticker === data.ticker);
    if (existingIndex !== -1) {
        // Update existing alert
        scoutAlerts[existingIndex] = data;
    } else {
        // Add new alert
        scoutAlerts.unshift(data);
    }

    // Enforce max visible limit (oldest drops off)
    if (scoutAlerts.length > SCOUT_ALERT_MAX_VISIBLE) {
        scoutAlerts = scoutAlerts.slice(0, SCOUT_ALERT_MAX_VISIBLE);
    }

    // Set auto-dismiss timeout
    setTimeout(() => {
        dismissScoutAlert(data.signal_id);
    }, SCOUT_ALERT_TIMEOUT_MS);

    renderScoutAlerts();
}

function dismissScoutAlert(signalId) {
    scoutAlerts = scoutAlerts.filter(a => a.signal_id !== signalId);
    renderScoutAlerts();
}

function dismissScoutAlertByTicker(ticker) {
    // Called when a real Sniper signal fires for the same ticker
    const alert = scoutAlerts.find(a => a.ticker === ticker);
    if (alert) {
        console.log('ðŸŽ¯ Scout alert confirmed by Sniper signal:', ticker);
        scoutAlerts = scoutAlerts.filter(a => a.ticker !== ticker);
        renderScoutAlerts();
    }
}

function createScoutAlertCard(alert) {
    const directionClass = alert.direction === 'LONG' ? 'scout-long' : 'scout-short';
    const directionIcon = alert.direction === 'LONG' ? '^' : 'v';

    return `
        <div class="scout-alert-card ${directionClass}" data-scout-id="${alert.signal_id}" data-ticker="${alert.ticker}">
            <div class="scout-alert-header">
                <div class="scout-badge">
                    <span class="scout-icon">!</span>
                    <span class="scout-label">SCOUT</span>
                </div>
                <button class="scout-dismiss-btn" data-action="dismiss-scout" title="Dismiss">x</button>
            </div>
            <div class="scout-alert-content">
                <div class="scout-ticker-row">
                    <span class="scout-ticker">${alert.ticker}</span>
                    <span class="scout-direction ${directionClass}">${directionIcon} ${alert.direction}</span>
                </div>
                <div class="scout-metrics">
                    <div class="scout-metric">
                        <span class="scout-metric-label">RSI</span>
                        <span class="scout-metric-value">${alert.rsi?.toFixed(1) || '--'}</span>
                    </div>
                    <div class="scout-metric">
                        <span class="scout-metric-label">RVOL</span>
                        <span class="scout-metric-value">${alert.rvol?.toFixed(2) || '--'}x</span>
                    </div>
                    <div class="scout-metric">
                        <span class="scout-metric-label">TF</span>
                        <span class="scout-metric-value">${alert.timeframe}m</span>
                    </div>
                </div>
                <div class="scout-note">${alert.note || 'Early warning - confirm with 1H Sniper'}</div>
            </div>
        </div>
    `;
}

function renderScoutAlerts() {
    const container = document.getElementById('scoutAlertsContainer');
    if (!container) return;

    const countEl = document.getElementById('scoutAlertCount');
    if (countEl) {
        countEl.textContent = scoutAlerts.length;
        countEl.style.display = scoutAlerts.length > 0 ? 'inline-flex' : 'none';
    }

    if (scoutAlerts.length === 0) {
        container.innerHTML = '<p class="scout-empty-state">No active scout alerts</p>';
        return;
    }

    container.innerHTML = scoutAlerts.map(alert => createScoutAlertCard(alert)).join('');
    attachScoutAlertActions();
}

function attachScoutAlertActions() {
    document.querySelectorAll('.scout-dismiss-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const card = e.target.closest('.scout-alert-card');
            const signalId = card.dataset.scoutId;
            dismissScoutAlert(signalId);
        });
    });

    // Click on card to show ticker on chart
    document.querySelectorAll('.scout-alert-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.classList.contains('scout-dismiss-btn')) return;
            const ticker = card.dataset.ticker;
            if (ticker && typeof changeChartSymbol === 'function') {
                changeChartSymbol(ticker);
            }
        });
    });
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
    // Refresh button
    document.getElementById('refreshBtn').addEventListener('click', () => {
        loadSignals();
        loadBiasData();
        fetchCompositeBias();
        fetchTimeframeBias();
        checkPivotHealth();
        checkRedisHealth();
        if (window.analyticsUI && typeof window.analyticsUI.refreshAll === 'function') {
            window.analyticsUI.refreshAll();
        }
    });

    // Mode switcher
    document.querySelectorAll('.mode-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const mode = e.currentTarget.dataset.mode;
            setMode(mode);
        });
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
            refreshSignalViews();
        });
    });
    
    // Hybrid Scanner
    initHybridScanner();
    
    // Bias Factor Settings Modals
    initWeeklyBiasSettings();
    initDailyBiasSettings();
    initCyclicalBiasSettings();
    
    // Savita Update Modal
    initSavitaUpdateModal();

    // Composite Bias Controls
    initCompositeBiasControls();
}

// Data Loading
async function loadInitialData() {
    // Load timeframe bias cards first; composite views are sourced from backend endpoints.
    await loadBiasData();
    await Promise.all([
        loadSignals(),
        fetchCompositeBias(),
        fetchTimeframeBias(),
        loadOpenPositionsEnhanced()
    ]);

    // Initialize Scout Alerts section
    renderScoutAlerts();
    
    // Initialize timeframe card toggles
    initTimeframeToggles();

    // Set up auto-refresh for bias shift status every 5 minutes
    setInterval(() => {
        fetchBiasShiftStatus();
    }, 5 * 60 * 1000); // 5 minutes
    
    // Refresh timeframe data every 2 minutes
    setInterval(fetchTimeframeBias, 2 * 60 * 1000);

    // Pivot health checks
    checkPivotHealth();
    setInterval(checkPivotHealth, 5 * 60 * 1000);

    // Redis health checks
    checkRedisHealth();
    setInterval(checkRedisHealth, 2 * 60 * 1000);
}

let cryptoTvWidget = null;
let cryptoCurrentSymbol = 'BTCUSD';

function initCryptoScalper() {
    // Top coin chips
    const topCoins = document.getElementById('cryptoTopCoins');
    if (topCoins) {
        topCoins.querySelectorAll('.coin-chip').forEach(chip => {
            chip.addEventListener('click', () => {
                topCoins.querySelectorAll('.coin-chip').forEach(c => c.classList.remove('active'));
                chip.addEventListener('click', () => {});
                chip.classList.add('active');
                const sym = chip.dataset.symbol;
                if (sym && sym !== cryptoCurrentSymbol) {
                    cryptoCurrentSymbol = sym;
                    initCryptoChart();
                }
            });
        });
    }

    const sortSelect = document.getElementById('cryptoSignalSort');
    if (sortSelect) {
        sortSelect.addEventListener('change', renderCryptoSignals);
    }

    // Chart tab switching (legacy tabs) + chips already handle above
    const chartTabs = document.getElementById('cryptoChartTabs');
    if (chartTabs) {
        chartTabs.querySelectorAll('.chart-tab').forEach(tab => {
            tab.addEventListener('click', () => {
                chartTabs.querySelectorAll('.chart-tab').forEach(t => t.classList.remove('active'));
                tab.classList.add('active');
                const sym = tab.dataset.symbol;
                if (sym && sym !== cryptoCurrentSymbol) {
                    cryptoCurrentSymbol = sym;
                    initCryptoChart();
                }
            });
        });
    }

    // Strategy filter checkboxes
    document.querySelectorAll('.crypto-strategy-cb').forEach(cb => {
        cb.addEventListener('change', renderCryptoSignals);
    });
    const dirLong = document.getElementById('cryptoFilterLong');
    const dirShort = document.getElementById('cryptoFilterShort');
    if (dirLong) dirLong.addEventListener('change', renderCryptoSignals);
    if (dirShort) dirShort.addEventListener('change', renderCryptoSignals);
    const autoBiasToggle = document.getElementById('cryptoAutoBiasToggle');
    if (autoBiasToggle) {
        autoBiasToggle.addEventListener('change', () => {
            applyCryptoBiasPreset();
            renderCryptoSignals();
        });
    }
    const scoreThreshold = document.getElementById('cryptoScoreThreshold');
    if (scoreThreshold) scoreThreshold.addEventListener('input', renderCryptoSignals);

    // Signal action delegation
    const signalList = document.getElementById('cryptoSignalsList');
    if (signalList) {
        signalList.addEventListener('click', handleCryptoSignalAction);
    }

    loadCryptoKeyLevels();
    setInterval(loadCryptoKeyLevels, 10 * 60 * 1000);

    refreshCryptoWma9();
    if (cryptoWmaTimer) clearInterval(cryptoWmaTimer);
    cryptoWmaTimer = setInterval(refreshCryptoWma9, 15 * 60 * 1000);

    // Start 5s market polling only if the crypto view is currently visible.
    if (document.body.dataset.mode === APP_MODES.CRYPTO) {
        startCryptoMarketPolling();
    }
}

function startCryptoMarketPolling() {
    loadCryptoMarketData();
    if (cryptoMarketTimer) clearInterval(cryptoMarketTimer);
    cryptoMarketTimer = setInterval(loadCryptoMarketData, CRYPTO_MARKET_POLL_MS);
}

function stopCryptoMarketPolling() {
    if (!cryptoMarketTimer) return;
    clearInterval(cryptoMarketTimer);
    cryptoMarketTimer = null;
}

function initCryptoChart() {
    const container = document.getElementById('crypto-tradingview-widget');
    if (!container) return;
    if (typeof TradingView === 'undefined') return;

    // TradingView requires a visible container with non-zero dimensions.
    // If the container is not yet laid out (e.g. parent is hidden or has zero size),
    // defer the init by one animation frame so the browser can reflow first.
    const parentContainer = document.getElementById('cryptoChartContainer');
    if (parentContainer && parentContainer.offsetWidth === 0) {
        requestAnimationFrame(() => setTimeout(initCryptoChart, 50));
        return;
    }

    container.innerHTML = '';
    cryptoTvWidget = new TradingView.widget({
        symbol: cryptoCurrentSymbol,
        interval: '15',
        timezone: 'America/New_York',
        theme: 'dark',
        style: '1',
        locale: 'en',
        toolbar_bg: '#0a0e27',
        enable_publishing: false,
        hide_top_toolbar: false,
        hide_legend: false,
        save_image: false,
        container_id: 'crypto-tradingview-widget',
        width: '100%',
        height: '100%',
        studies: [
            { id: 'MASimple@tv-basicstudies', inputs: { length: 50 } },
            { id: 'MASimple@tv-basicstudies', inputs: { length: 200 } }
        ],
        overrides: {
            'mainSeriesProperties.candleStyle.upColor': '#7CFF6B',
            'mainSeriesProperties.candleStyle.downColor': '#FF6B35',
            'mainSeriesProperties.candleStyle.borderUpColor': '#7CFF6B',
            'mainSeriesProperties.candleStyle.borderDownColor': '#FF6B35',
            'mainSeriesProperties.candleStyle.wickUpColor': '#7CFF6B',
            'mainSeriesProperties.candleStyle.wickDownColor': '#FF6B35',
            'paneProperties.background': '#0a0e27',
            'paneProperties.backgroundType': 'solid',
            'paneProperties.vertGridProperties.color': '#1e293b',
            'paneProperties.horzGridProperties.color': '#1e293b',
            'scalesProperties.textColor': '#94a3b8',
            'scalesProperties.backgroundColor': '#0a0e27',
            'paneProperties.crossHairProperties.color': '#F7931A'
        }
    });
}

function handleCryptoSignalAction(e) {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const card = btn.closest('.crypto-signal-card');
    if (!card) return;
    const signalId = card.dataset.signalId;
    if (!signalId) return;

    const action = btn.dataset.action;
    if (action === 'select') {
        // Find signal data
        const signal = signals.crypto.find(s => s.signal_id === signalId);
        if (signal) {
            openCryptoAcceptModal(signal);
        }
    } else if (action === 'dismiss') {
        dismissCryptoSignal(signalId);
    } else if (action === 'view-chart') {
        // Normalize the ticker: strip any trailing USDT or USD suffix before building symbol
        const rawTicker = btn.textContent.trim().toUpperCase().replace(/USDT?$/, '');
        if (rawTicker) {
            cryptoCurrentSymbol = rawTicker + 'USD';
            initCryptoChart();
            // Highlight matching tab (if no tab matches, all tabs become inactive â€” graceful)
            const tabs = document.getElementById('cryptoChartTabs');
            if (tabs) {
                tabs.querySelectorAll('.chart-tab').forEach(t => {
                    t.classList.toggle('active', t.dataset.symbol === cryptoCurrentSymbol);
                });
            }
        }
    }
}

function openCryptoAcceptModal(signal) {
    // Reuse the existing position entry modal from hub mode.
    // IMPORTANT: must set pendingPositionSignal so confirmPositionEntry() has the data.
    const modal = document.getElementById('positionEntryModal');
    if (!modal) return;

    // Wire up pendingPositionSignal so the shared confirmPositionEntry handler works
    pendingPositionSignal = signal;
    pendingPositionCard = null; // No card element ref in crypto mode; skip animation

    const tickerDisplay = document.getElementById('positionTickerDisplay');
    const dirDisplay = document.getElementById('positionDirectionDisplay');
    const entryInput = document.getElementById('positionEntryPrice');
    const qtyInput = document.getElementById('positionQuantity');
    const qtyLabel = document.getElementById('positionQtyLabel');
    const summaryStop = document.getElementById('summaryStop');
    const summaryTarget = document.getElementById('summaryTarget');
    const summarySize = document.getElementById('summarySize');
    const summaryRisk = document.getElementById('summaryRisk');

    if (tickerDisplay) tickerDisplay.textContent = signal.ticker || '--';
    if (dirDisplay) {
        dirDisplay.textContent = signal.direction || 'LONG';
        dirDisplay.className = 'position-direction-display ' + (signal.direction || 'LONG');
    }
    if (entryInput) entryInput.value = signal.entry_price ? parseFloat(signal.entry_price).toFixed(2) : '';
    if (qtyInput) { qtyInput.value = ''; qtyInput.placeholder = 'Contracts'; }
    if (qtyLabel) qtyLabel.textContent = 'Quantity (Contracts) *';
    if (summaryStop) summaryStop.textContent = signal.stop_loss ? `$${parseFloat(signal.stop_loss).toLocaleString()}` : '--';
    if (summaryTarget) summaryTarget.textContent = signal.target_1 ? `$${parseFloat(signal.target_1).toLocaleString()}` : '--';
    if (summarySize) summarySize.textContent = '$--';
    if (summaryRisk) summaryRisk.textContent = '$--';

    // Use classList.add('active') to match the hub modal open/close pattern
    modal.classList.add('active');
}

async function dismissCryptoSignal(signalId) {
    try {
        await fetch(`${API_URL}/signals/${signalId}/dismiss`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ signal_id: signalId })
        });
        signals.crypto = signals.crypto.filter(s => s.signal_id !== signalId);
        renderCryptoSignals();
    } catch (err) {
        console.error('Error dismissing crypto signal:', err);
    }
}

async function loadSignals() {
    try {
        const response = await fetch(`${API_URL}/signals/active`);
        const data = await response.json();
        
        console.log('ðŸ“¡ Loaded signals:', data);
        
        if (data.status === 'success' && data.signals) {
            // Merge counter-trend signals that aren't already in the main list
            const allSignals = [...data.signals];
            if (data.counter_trend_signals && data.counter_trend_signals.length > 0) {
                const mainIds = new Set(allSignals.map(s => s.signal_id));
                for (const ct of data.counter_trend_signals) {
                    ct.is_counter_trend = true;
                    if (!mainIds.has(ct.signal_id)) {
                        allSignals.push(ct);
                    }
                }
            }
            
            // Separate equity and crypto signals (be more flexible with asset_class matching)
            const cryptoTickers = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'AVAX', 'DOGE', 'DOT', 'LINK', 'MATIC', 'LTC', 'UNI'];
            
            signals.equity = allSignals.filter(s => {
                // If explicitly marked as EQUITY
                if (s.asset_class === 'EQUITY') return true;
                // If no asset_class but ticker doesn't look like crypto
                if (!s.asset_class) {
                    const tickerBase = (s.ticker || '').toUpperCase().replace(/USD.*/, '');
                    return !cryptoTickers.includes(tickerBase);
                }
                return false;
            });
            
            signals.crypto = allSignals.filter(s => {
                // If explicitly marked as CRYPTO
                if (s.asset_class === 'CRYPTO') return true;
                // If no asset_class but ticker looks like crypto
                if (!s.asset_class) {
                    const tickerBase = (s.ticker || '').toUpperCase().replace(/USD.*/, '');
                    return cryptoTickers.includes(tickerBase);
                }
                return false;
            });
            
            console.log(`ðŸ“Š Signals loaded: ${signals.equity.length} equity, ${signals.crypto.length} crypto`);
            console.log('ðŸª™ Crypto signals:', signals.crypto);
            
            resetTradeIdeasPagination();
            
            // Force render signals with a small delay to ensure DOM is ready
            setTimeout(() => {
                refreshSignalViews();
            }, 100);
        } else {
            console.warn('No signals in response or error:', data);
        }
    } catch (error) {
        console.error('Error loading signals:', error);
    }
}

function resetTradeIdeasPagination() {
    tradeIdeasPagination = {
        equity: { offset: signals.equity.length, limit: TRADE_IDEAS_PAGE_SIZE, hasMore: true, loading: false },
        crypto: { offset: signals.crypto.length, limit: TRADE_IDEAS_PAGE_SIZE, hasMore: true, loading: false }
    };
}

function syncTradeIdeasOffset(assetType) {
    if (!tradeIdeasPagination[assetType]) return;
    tradeIdeasPagination[assetType].offset = signals[assetType].length;
}

async function loadBiasData() {
    loadDailyFactorStatesFromStorage();
    loadCyclicalFactorStatesFromStorage();

    // Load all biases from the auto-scheduler endpoint (includes trends!)
    try {
        const response = await fetch(`${API_URL}/bias-auto/status`);
        const result = await response.json();
        
        if (result.status === 'success' && result.data) {
            const data = result.data;
            const effective = result.effective;  // Hierarchical modifiers
            
            // Update Daily Bias - store full data and apply factor filters
            if (data.daily) {
                dailyBiasFullData = data.daily;
                if (data.daily.details && data.daily.details.factors) {
                    updateDailyBiasWithFactors(data.daily);
                } else {
                    updateBiasWithTrend('daily', data.daily);
                }
                
                // Show effective bias if different from raw (hierarchical modifier applied)
                if (effective && effective.daily && effective.daily !== data.daily.level) {
                    updateEffectiveBias('daily', data.daily.level, effective.daily, effective.modifiers?.daily);
                } else {
                    hideEffectiveBias('daily');
                }
            }
            
            // Update Weekly Bias - store full data and check for new day reset
            if (data.weekly) {
                checkAndResetFactorsForNewDay(data.weekly);
                weeklyBiasFullData = data.weekly;
                updateWeeklyBiasWithFactors(data.weekly);
                
                // Show effective bias if different from raw (modified by Cyclical)
                if (effective && effective.weekly && effective.weekly !== data.weekly.level) {
                    updateEffectiveBias('weekly', data.weekly.level, effective.weekly, effective.modifiers?.weekly);
                } else {
                    hideEffectiveBias('weekly');
                }
            }
            
            // Update Cyclical Bias - store full data and apply factor filters
            // Note: Cyclical has no modifier (it's the highest level)
            if (data.cyclical) {
                cyclicalBiasFullData = data.cyclical;
                if (data.cyclical.details && data.cyclical.details.factors) {
                    updateCyclicalBiasWithFactors(data.cyclical);
                } else {
                    updateBiasWithTrend('cyclical', data.cyclical);
                }
                
                // Check for crisis mode and display alert
                checkAndDisplayCrisisAlert(data.cyclical);
                
                // Check Savita status for update reminder
                checkSavitaStatus(data.cyclical);
            }
        } else {
            // Fallback to old endpoint if scheduler not ready
            await loadBiasDataFallback();
        }
    } catch (error) {
        console.error('Error loading bias data from scheduler:', error);
        // Fallback to old endpoint
        await loadBiasDataFallback();
    }
    
    // Load shift status for weekly bias
    await fetchBiasShiftStatus();

    // Check and apply alignment styling
    checkAndApplyBiasAlignment();

    renderCryptoBiasSummary();
}

function normalizeCompositeBiasLevel(level) {
    if (!level) return 'NEUTRAL';
    const raw = String(level).toUpperCase().replace(/\s+/g, '_');
    const map = {
        MAJOR_TORO: 'TORO_MAJOR',
        MINOR_TORO: 'TORO_MINOR',
        LEAN_TORO: 'TORO_MINOR',
        LEAN_URSA: 'URSA_MINOR',
        MINOR_URSA: 'URSA_MINOR',
        MAJOR_URSA: 'URSA_MAJOR',
        TORO_MAJOR: 'TORO_MAJOR',
        TORO_MINOR: 'TORO_MINOR',
        URSA_MINOR: 'URSA_MINOR',
        URSA_MAJOR: 'URSA_MAJOR',
        NEUTRAL: 'NEUTRAL'
    };
    return map[raw] || 'NEUTRAL';
}

function normalizeDailyBiasLevel(level) {
    if (!level) return 'NEUTRAL';
    return String(level).toUpperCase().replace(/\s+/g, '_');
}

function timeframeVoteToBiasLabel(vote) {
    if (vote >= 6) return 'MAJOR_TORO';
    if (vote >= 3) return 'MINOR_TORO';
    if (vote <= -6) return 'MAJOR_URSA';
    if (vote <= -3) return 'MINOR_URSA';
    return 'NEUTRAL';
}

function scoreToTimeframeVote(score) {
    if (!Number.isFinite(score)) return 0;
    return Math.round(score * 10);
}

function biasTrendToMomentum(trend) {
    const value = String(trend || '').toUpperCase();
    if (value === 'IMPROVING') return 'strengthening';
    if (value === 'DECLINING') return 'weakening';
    return 'stable';
}

function compositeLevelToScore(level) {
    const normalized = normalizeCompositeBiasLevel(level);
    const scoreMap = {
        TORO_MAJOR: 0.9,
        TORO_MINOR: 0.45,
        NEUTRAL: 0,
        URSA_MINOR: -0.45,
        URSA_MAJOR: -0.9
    };
    return scoreMap[normalized] ?? 0;
}

function scoreToCompositeLevel(score) {
    if (score >= 0.6) return 'TORO_MAJOR';
    if (score >= 0.2) return 'TORO_MINOR';
    if (score <= -0.6) return 'URSA_MAJOR';
    if (score <= -0.2) return 'URSA_MINOR';
    return 'NEUTRAL';
}

function factorMapToRows(factorMap) {
    if (!factorMap || typeof factorMap !== 'object') return [];
    return Object.entries(factorMap).map(([factorId, factorData]) => {
        const voteRaw = Number(factorData?.vote ?? 0);
        const vote = Number.isFinite(voteRaw) ? voteRaw : 0;
        const score = Math.max(-1, Math.min(1, vote / 2));
        const signal = factorData?.details?.signal || factorData?.signal || 'NEUTRAL';
        const detail = factorData?.details ? JSON.stringify(factorData.details) : '';
        return {
            factor_id: factorId,
            weight: 1,
            description: '',
            stale: false,
            score,
            signal,
            detail
        };
    });
}

async function fetchDailyBiasPrimary() {
    try {
        const resp = await fetch(`${API_URL}/bias/DAILY`);
        if (!resp.ok) {
            throw new Error(`/bias/DAILY returned HTTP ${resp.status}`);
        }
        const data = await resp.json();
        if (!data || typeof data !== 'object') {
            throw new Error('/bias/DAILY returned invalid payload');
        }
        _dailyBiasPrimaryData = data;
        return data;
    } catch (err) {
        console.error('Failed to fetch daily bias primary:', err);
        return null;
    }
}

async function fetchCompositeBias() {
    try {
        const [compositeResp, dailyData] = await Promise.all([
            fetch(`${API_URL}/bias/composite`),
            fetchDailyBiasPrimary(),
        ]);
        if (!compositeResp.ok) {
            throw new Error(`/bias/composite returned HTTP ${compositeResp.status}`);
        }
        const data = await compositeResp.json();
        if (!data || typeof data !== 'object') {
            throw new Error('/bias/composite returned invalid payload');
        }
        renderCompositeBias(data, dailyData);
    } catch (err) {
        console.error('Failed to fetch composite bias:', err);
        showCompositeError();
    }
}

function showCompositeError() {
    const levelEl = document.getElementById('compositeBiasLevel');
    const scoreEl = document.getElementById('compositeBiasScore');
    const confEl = document.getElementById('compositeConfidence');
    const secondaryEl = document.getElementById('compositeBiasSecondary');
    const lastUpdateEl = document.getElementById('compositeLastUpdate');

    if (levelEl) levelEl.textContent = 'UNKNOWN';
    if (scoreEl) scoreEl.textContent = '(--)';
    if (confEl) confEl.textContent = 'LOW';
    if (secondaryEl) secondaryEl.textContent = 'Composite: --';
    if (lastUpdateEl) lastUpdateEl.textContent = 'Last update: --';
}

function renderCompositeBias(data, dailyData = null) {
    if (!data) return;

    // Cache for use by crypto bias bar (avoids reading from hub DOM elements)
    _compositeBiasData = data;
    if (dailyData && typeof dailyData === 'object') {
        _dailyBiasPrimaryData = dailyData;
    }

    const banner = document.getElementById('compositeBiasBanner');
    const levelEl = document.getElementById('compositeBiasLevel');
    const scoreEl = document.getElementById('compositeBiasScore');
    const confEl = document.getElementById('compositeConfidence');
    const secondaryEl = document.getElementById('compositeBiasSecondary');
    const overrideEl = document.getElementById('compositeOverrideIndicator');
    const factorList = document.getElementById('compositeFactorList');
    const activeCountEl = document.getElementById('factorActiveCount');
    const lastUpdateEl = document.getElementById('compositeLastUpdate');

    const dailySource = _dailyBiasPrimaryData || dailyBiasFullData || {};
    const dailyLevel = normalizeDailyBiasLevel(dailySource.level || data.bias_level || 'NEUTRAL');
    const dailyVoteRaw = Number(dailySource?.details?.total_vote);
    const dailyVote = Number.isFinite(dailyVoteRaw) ? Math.trunc(dailyVoteRaw) : null;
    const dailyColorKey = normalizeCompositeBiasLevel(dailyLevel);
    const colors = BIAS_COLORS[dailyColorKey] || BIAS_COLORS.NEUTRAL;

    const scoreValue = typeof data.composite_score === 'number'
        ? data.composite_score
        : parseFloat(data.composite_score || 0);
    const confidence = (data.confidence || 'LOW').toUpperCase();
    const activeCount = Array.isArray(data.active_factors) ? data.active_factors.length : null;
    const staleCount = Array.isArray(data.stale_factors) ? data.stale_factors.length : null;
    const totalCount = Number.isFinite(activeCount) && Number.isFinite(staleCount)
        ? activeCount + staleCount
        : (data.factors && typeof data.factors === 'object' ? Object.keys(data.factors).length : null);

    if (banner) {
        banner.style.background = colors.bg;
        banner.style.borderColor = colors.accent;
    }
    if (levelEl) {
        levelEl.textContent = dailyLevel.replace(/_/g, ' ');
        levelEl.style.color = colors.accent;
    }
    if (scoreEl) {
        const scoreText = dailyVote === null ? '--' : `${dailyVote >= 0 ? '+' : ''}${dailyVote}`;
        scoreEl.textContent = `(${scoreText})`;
    }
    if (confEl) {
        const suffix = Number.isFinite(activeCount) && Number.isFinite(totalCount)
            ? ` (${activeCount}/${totalCount} active)`
            : '';
        confEl.textContent = `${confidence}${suffix}`;
        confEl.style.color = CONFIDENCE_COLORS[confidence] || CONFIDENCE_COLORS.LOW;
    }
    if (secondaryEl) {
        const compositeLevel = String(data.bias_level || 'NEUTRAL').replace(/_/g, ' ');
        const compositeScoreText = Number.isFinite(scoreValue) ? scoreValue.toFixed(2) : '--';
        const staleLabel = Number.isFinite(staleCount)
            ? ` - ${staleCount} stale factor${staleCount === 1 ? '' : 's'}`
            : '';
        secondaryEl.textContent = `Composite: ${compositeLevel} (${compositeScoreText})${staleLabel}`;
    }

    if (overrideEl) {
        if (data.override) {
            overrideEl.style.display = 'block';
            overrideEl.textContent = `Override active: ${data.override.replace(/_/g, ' ')}`;
        } else {
            overrideEl.style.display = 'none';
        }
    }

    if (factorList) {
        const activeSet = new Set(data.active_factors || []);
        const staleSet = new Set(data.stale_factors || []);
        const factorsMap = data.factors && typeof data.factors === 'object' ? data.factors : {};
        const discoveredFactorIds = new Set([
            ...Object.keys(factorsMap),
            ...Array.from(activeSet),
            ...Array.from(staleSet)
        ]);

        const factorOrderMap = new Map(COMPOSITE_FACTOR_DISPLAY_ORDER.map((id, idx) => [id, idx]));
        const sortedFactorIds = Array.from(discoveredFactorIds).sort((a, b) => {
            const ai = factorOrderMap.has(a) ? factorOrderMap.get(a) : Number.MAX_SAFE_INTEGER;
            const bi = factorOrderMap.has(b) ? factorOrderMap.get(b) : Number.MAX_SAFE_INTEGER;
            if (ai !== bi) return ai - bi;
            return a.localeCompare(b);
        });

        factorList.innerHTML = '';

        sortedFactorIds.forEach((factorId) => {
            const factor = factorsMap[factorId] || null;
            const isActive = activeSet.has(factorId);
            const isStale = staleSet.has(factorId) || !isActive;
            const score = factor && typeof factor.score === 'number' ? factor.score : null;
            const barPct = score !== null ? Math.min(100, Math.abs(score) * 100) : 0;

            const barColor = score === null ? '#455a64'
                : score <= -0.6 ? '#e5370e'
                : score <= -0.2 ? '#ff9800'
                : score >= 0.6 ? '#00e676'
                : score >= 0.2 ? '#66bb6a' : '#78909c';

            const row = document.createElement('div');
            row.className = `factor-row${isStale ? ' stale' : ''}`;
            row.innerHTML = `
                <span class="factor-status">${isActive ? 'o' : '-'}</span>
                <span class="factor-name">${formatFactorName(factorId)}</span>
                <div class="factor-bar">
                    <div class="factor-bar-fill" style="width:${barPct}%;background:${barColor}"></div>
                </div>
                <span class="factor-score">${score !== null && isActive ? score.toFixed(2) : 'STALE'}</span>
                <span class="factor-signal" style="color:${barColor}">${score !== null && isActive ? (factor.signal || '').replace(/_/g, ' ') : '?'}</span>
            `;

            if (factor && factor.detail) {
                row.title = factor.detail;
                row.style.cursor = 'pointer';
                row.addEventListener('click', () => {
                    const existing = row.querySelector('.factor-detail');
                    if (existing) {
                        existing.remove();
                    } else {
                        const detail = document.createElement('div');
                        detail.className = 'factor-detail';
                        detail.textContent = factor.detail;
                        row.appendChild(detail);
                    }
                });
            }

            factorList.appendChild(row);
        });

        if (activeCountEl) {
            const total = sortedFactorIds.length;
            const active = (data.active_factors || []).length;
            activeCountEl.textContent = `${active}/${total} active`;
        }
    }

    if (lastUpdateEl && data.timestamp) {
        const timeAgo = getTimeAgo(new Date(data.timestamp));
        lastUpdateEl.textContent = `Last update: ${timeAgo}`;
    }
}

function initCompositeBiasControls() {
    const toggle = document.getElementById('factorBreakdownToggle');
    const list = document.getElementById('compositeFactorList');
    const caret = toggle ? toggle.querySelector('.factor-breakdown-caret') : null;

    if (toggle && list) {
        toggle.addEventListener('click', () => {
            const isOpen = list.style.display !== 'none';
            list.style.display = isOpen ? 'none' : 'flex';
            if (caret) caret.textContent = isOpen ? '>' : 'v';
        });
    }

    const applyBtn = document.getElementById('compositeOverrideApply');
    const clearBtn = document.getElementById('compositeOverrideClear');
    const selectEl = document.getElementById('compositeOverrideSelect');

    if (applyBtn && selectEl) {
        applyBtn.addEventListener('click', async () => {
            const level = selectEl.value;
            if (!level) return;
            const reason = prompt('Reason for override?');
            if (!reason) return;

            await fetch(`${API_URL}/bias/override`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    level,
                    reason,
                    expires_hours: 24,
                })
            });

            fetchCompositeBias();
        });
    }

    if (clearBtn) {
        clearBtn.addEventListener('click', async () => {
            await fetch(`${API_URL}/bias/override`, { method: 'DELETE' });
            fetchCompositeBias();
        });
    }
}

// =========================================================================
// TIMEFRAME FACTOR CARDS (Intraday / Swing / Macro)
// =========================================================================

async function fetchTimeframeBias() {
    try {
        const resp = await fetch(`${API_URL}/bias/composite/timeframes`);
        if (!resp.ok) {
            throw new Error(`/bias/composite/timeframes returned HTTP ${resp.status}`);
        }
        const data = await resp.json();
        if (!data || !data.timeframes || typeof data.timeframes !== 'object') {
            throw new Error('/bias/composite/timeframes returned invalid payload');
        }

        if (data && data.timeframes) {
            // Backfill cache only from backend-computed timeframe payload.
            if (data.composite_bias && typeof data.composite_score === 'number') {
                _compositeBiasData = {
                    ...(typeof _compositeBiasData === 'object' && _compositeBiasData ? _compositeBiasData : {}),
                    bias_level: data.composite_bias,
                    composite_score: data.composite_score,
                    confidence: data.confidence || _compositeBiasData?.confidence || 'LOW'
                };
            }

            renderTimeframeCards(data);
            renderSectorRotationStrip(data.sector_rotation);
            renderCryptoBiasSummary();
            
            // Apply pulse to composite banner at extremes
            const banner = document.getElementById('compositeBiasBanner');
            if (banner) {
                banner.classList.remove('pulse-toro', 'pulse-ursa');
                if (data.composite_bias === 'TORO_MAJOR') banner.classList.add('pulse-toro');
                else if (data.composite_bias === 'URSA_MAJOR') banner.classList.add('pulse-ursa');
            }
        }
    } catch (err) {
        console.error('Failed to fetch timeframe bias:', err);
    }
}

function renderTimeframeCards(data) {
    const tfNames = ['intraday', 'swing', 'macro'];
    const cardIds = { intraday: 'tfIntraday', swing: 'tfSwing', macro: 'tfMacro' };

    for (const tf of tfNames) {
        const tfData = data.timeframes[tf];
        if (!tfData) continue;

        const card = document.getElementById(cardIds[tf]);
        if (!card) continue;

        // Use API-computed bias_level (same score_to_bias thresholds as composite)
        const apiLevel = tfData.bias_level || '';
        const visualLevel = normalizeCompositeBiasLevel(apiLevel) || 'NEUTRAL';
        // Fallback to vote conversion only if API didn't provide bias_level
        const displayLevel = apiLevel ? visualLevel : (() => {
            const voteValue = scoreToTimeframeVote(typeof tfData.sub_score === 'number' ? tfData.sub_score : 0);
            return normalizeCompositeBiasLevel(timeframeVoteToBiasLabel(voteValue));
        })();
        const subScore = typeof tfData.sub_score === 'number' ? tfData.sub_score : 0;
        const momentum = tfData.momentum || 'stable';

        // Update level
        const levelEl = card.querySelector('.tf-level');
        if (levelEl) {
            levelEl.textContent = visualLevel.replace(/_/g, ' ');
        }

        // Update score — show sub_score as compact value
        const scoreEl = card.querySelector('.tf-score');
        if (scoreEl) {
            const scoreText = `${subScore >= 0 ? '+' : ''}${subScore.toFixed(2)}`;
            scoreEl.textContent = `(${scoreText})`;
        }

        // Update momentum
        const momEl = card.querySelector('.tf-momentum');
        if (momEl) {
            const arrows = { strengthening: '^', weakening: 'v', stable: '->' };
            const labels = { strengthening: 'Strengthening', weakening: 'Weakening', stable: 'Stable' };
            momEl.className = `tf-momentum ${momentum}`;
            momEl.innerHTML = `<span class="tf-momentum-arrow">${arrows[momentum] || '->'}</span> ${labels[momentum] || 'Stable'}`;
        }

        // Update divergence
        const divEl = card.querySelector('.tf-divergence');
        if (divEl) {
            if (tfData.divergent) {
                const compDir = data.composite_score > 0 ? 'bullish' : 'bearish';
                divEl.textContent = `Diverging from composite (${compDir})`;
                divEl.style.display = 'block';
            } else {
                divEl.style.display = 'none';
            }
        }

        // Apply bias color class
        card.className = `tf-card ${visualLevel}`;

        // Pulse at extremes
        card.classList.remove('pulse-toro', 'pulse-ursa');
        if (visualLevel === 'TORO_MAJOR') card.classList.add('pulse-toro');
        else if (visualLevel === 'URSA_MAJOR') card.classList.add('pulse-ursa');

        // Render factor bars
        const factorsEl = card.querySelector('.tf-factors');
        if (factorsEl && tfData.factors) {
            factorsEl.innerHTML = tfData.factors.map(f => {
                const fScore = f.score !== null ? f.score : 0;
                const pct = Math.abs(fScore) * 50; // 0-50% of bar width
                const dir = fScore >= 0 ? 'bullish' : 'bearish';
                const staleClass = f.stale ? 'stale' : '';
                const name = f.factor_id.replace(/_/g, ' ');
                return `
                    <div class="tf-factor-row ${staleClass}">
                        <span class="tf-factor-name">${name}</span>
                        <div class="tf-factor-bar">
                            <div class="tf-factor-bar-fill ${dir}" style="width:${pct}%"></div>
                        </div>
                        <span class="tf-factor-score">${
                            f.score !== null
                                ? (fScore >= 0 ? '+' : '') + fScore.toFixed(2)
                                : (f.stale ? 'STALE' : '--')
                        }</span>
                    </div>`;
            }).join('');
        }
    }
}

// =========================================================================
// SECTOR ROTATION STRIP
// =========================================================================

function renderSectorRotationStrip(sectorData) {
    const container = document.getElementById('sectorChips');
    if (!container) return;

    if (!sectorData || !sectorData.sectors || sectorData.sectors.length === 0) {
        container.innerHTML = '<span style="font-size:10px;color:var(--text-secondary)">Sector rotation data loading...</span>';
        return;
    }

    // Sort: SURGING first, then STEADY, then DUMPING (by rotation momentum)
    const sectors = [...sectorData.sectors].sort((a, b) => (b.rotation_momentum || 0) - (a.rotation_momentum || 0));

    container.innerHTML = sectors.map(s => {
        const status = s.status || 'STEADY';
        const arrow = status === 'SURGING' ? '^' : (status === 'DUMPING' ? 'v' : '-');
        const mom = s.rotation_momentum !== undefined ? (s.rotation_momentum >= 0 ? '+' : '') + s.rotation_momentum.toFixed(1) + '%' : '';
        const rs5 = s.rs_5d !== undefined ? (s.rs_5d >= 0 ? '+' : '') + s.rs_5d.toFixed(1) + '%' : '--';
        const rs20 = s.rs_20d !== undefined ? (s.rs_20d >= 0 ? '+' : '') + s.rs_20d.toFixed(1) + '%' : '--';
        const rankChange = s.rank_change_5d !== undefined ? (s.rank_change_5d > 0 ? '+' + s.rank_change_5d : s.rank_change_5d) : '--';
        const accel = s.acceleration || 'unknown';

        return `
            <div class="sector-chip ${status}" title="${s.sector}">
                <span class="sector-chip-arrow">${arrow}</span>
                ${s.etf}
                <div class="sector-tooltip">
                    <div class="sector-tooltip-row"><span class="sector-tooltip-label">${s.sector}</span></div>
                    <div class="sector-tooltip-row"><span class="sector-tooltip-label">5d RS</span><span>${rs5}</span></div>
                    <div class="sector-tooltip-row"><span class="sector-tooltip-label">20d RS</span><span>${rs20}</span></div>
                    <div class="sector-tooltip-row"><span class="sector-tooltip-label">Momentum</span><span>${mom}</span></div>
                    <div class="sector-tooltip-row"><span class="sector-tooltip-label">Rank Delta</span><span>${rankChange}</span></div>
                    <div class="sector-tooltip-row"><span class="sector-tooltip-label">Accel</span><span>${accel}</span></div>
                </div>
            </div>`;
    }).join('');

    // Make sector chips clickable to change chart
    container.querySelectorAll('.sector-chip').forEach(chip => {
        chip.addEventListener('click', (e) => {
            if (e.target.closest('.sector-tooltip')) return;
            const match = chip.textContent.trim().match(/[A-Z]{2,5}/);
            if (match && match[0]) changeChartSymbol(match[0]);
        });
    });
}

// Initialize timeframe card expand/collapse toggles
function initTimeframeToggles() {
    document.querySelectorAll('.tf-expand-toggle').forEach(toggle => {
        toggle.addEventListener('click', () => {
            const targetId = toggle.dataset.target;
            const target = document.getElementById(targetId);
            if (target) {
                const isOpen = target.style.display !== 'none';
                target.style.display = isOpen ? 'none' : 'flex';
                toggle.textContent = isOpen ? 'Factors >' : 'Factors v';
            }
        });
    });
}


function checkPivotHealth() {
    const indicators = Array.from(document.querySelectorAll('[data-pivot-health="true"]'));
    if (!indicators.length) return;

    const updateIndicators = (status, text) => {
        indicators.forEach(indicator => {
            const dot = indicator.querySelector('.pivot-dot');
            const textEl = indicator.querySelector('.pivot-text');
            indicator.classList.remove('online', 'offline');
            if (status) indicator.classList.add(status);
            if (dot) dot.textContent = 'o';
            if (textEl) textEl.textContent = text;
        });
    };

    fetch(`${API_URL}/bias/health`)
        .then(resp => resp.ok ? resp.json() : null)
        .then(data => {
            if (!data || !data.last_heartbeat) {
                updateIndicators(null, 'Pivot unknown');
                return;
            }

            const lastHeartbeat = new Date(data.last_heartbeat);
            const minutesAgo = (Date.now() - lastHeartbeat.getTime()) / 60000;
            if (minutesAgo < 30) {
                updateIndicators('online', 'Pivot live');
            } else {
                updateIndicators('offline', `Pivot offline (${Math.round(minutesAgo)}m)`);
            }
        })
        .catch(() => {
            updateIndicators(null, 'Pivot unknown');
        });
}

function checkRedisHealth() {
    const indicators = Array.from(document.querySelectorAll('[data-redis-health="true"]'));
    if (!indicators.length) return;

    const updateIndicators = (status, text, title) => {
        indicators.forEach(indicator => {
            const dot = indicator.querySelector('.redis-dot');
            const textEl = indicator.querySelector('.redis-text');
            indicator.classList.remove('ok', 'throttled', 'error');
            if (status) indicator.classList.add(status);
            if (dot) dot.textContent = 'o';
            if (textEl) textEl.textContent = text;
            if (title) {
                indicator.title = title;
            } else {
                indicator.removeAttribute('title');
            }
        });
    };

    fetch(`${API_URL}/redis/health`)
        .then(resp => resp.ok ? resp.json() : null)
        .then(data => {
            if (!data) {
                updateIndicators(null, 'Redis unknown');
                return;
            }

            const status = data.status || 'unknown';
            const lastError = data.last_error || null;
            const lastErrorAt = data.last_error_at ? new Date(data.last_error_at) : null;
            const minutesAgo = lastErrorAt ? Math.round((Date.now() - lastErrorAt.getTime()) / 60000) : null;

            if (status === 'throttled') {
                const suffix = Number.isFinite(minutesAgo) ? ` (${minutesAgo}m)` : '';
                updateIndicators('throttled', `Redis throttled${suffix}`, lastError || 'Redis throttled');
                return;
            }

            if (status === 'error') {
                const suffix = Number.isFinite(minutesAgo) ? ` (${minutesAgo}m)` : '';
                updateIndicators('error', `Redis error${suffix}`, lastError || 'Redis error');
                return;
            }

            if (status === 'ok') {
                updateIndicators('ok', 'Redis ok');
                return;
            }

            updateIndicators(null, 'Redis unknown');
        })
        .catch(() => {
            updateIndicators(null, 'Redis unknown');
        });
}

function formatFactorName(factorId) {
    return factorId
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
}

function getTimeAgo(date) {
    if (!date || Number.isNaN(date.getTime())) return '--';
    const diffMs = Date.now() - date.getTime();
    const diffMin = Math.floor(diffMs / 60000);
    if (diffMin < 1) return 'just now';
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHr = Math.floor(diffMin / 60);
    if (diffHr < 24) return `${diffHr}h ago`;
    const diffDay = Math.floor(diffHr / 24);
    return `${diffDay}d ago`;
}

function flashCompositeBanner() {
    const banner = document.getElementById('compositeBiasBanner');
    if (!banner) return;
    banner.classList.add('flash');
    setTimeout(() => banner.classList.remove('flash'), 1500);
}

// ==================== PORTFOLIO BALANCES (Brief 07-E) ====================

async function loadPortfolioBalances() {
    try {
        const res = await fetch(`${API_URL.replace('/api', '')}/api/portfolio/balances`);
        if (!res.ok) return;
        const accounts = await res.json();

        const container = document.getElementById('balance-rows');
        const totalEl = document.getElementById('balance-total');
        const updatedEl = document.getElementById('balance-updated-time');

        if (!container || !accounts.length) return;

        let total = 0;
        let latestUpdate = null;
        let html = '';

        for (const acct of accounts) {
            const bal = parseFloat(acct.balance);
            total += bal;

            if (acct.updated_at && (!latestUpdate || new Date(acct.updated_at) > new Date(latestUpdate))) {
                latestUpdate = acct.updated_at;
            }

            const isRH = acct.broker === 'robinhood';
            const rowClass = isRH ? 'active-account' : 'passive-account';

            html += `<div class="balance-row ${rowClass}">
                <span class="balance-label">${escapeHtml(acct.account_name)}</span>
                <span class="balance-value">$${bal.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}</span>
            </div>`;

            if (isRH && acct.cash != null) {
                html += `<div class="balance-row active-account">
                    <span class="balance-sub">Cash: $${parseFloat(acct.cash).toLocaleString('en-US', {minimumFractionDigits: 2})} · BP: $${parseFloat(acct.buying_power).toLocaleString('en-US', {minimumFractionDigits: 2})}</span>
                </div>`;
            }
        }

        container.innerHTML = html;
        totalEl.textContent = `$${total.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

        if (latestUpdate) {
            const ago = getTimeAgo(new Date(latestUpdate));
            updatedEl.textContent = `Updated ${ago}`;
        }
    } catch (err) {
        console.error('Failed to load portfolio balances:', err);
    }
}

// ==================== OPEN POSITIONS (Brief 07-E) ====================

async function loadPortfolioPositions() {
    try {
        const res = await fetch(`${API_URL.replace('/api', '')}/api/portfolio/positions`);
        if (!res.ok) return;
        const positions = await res.json();

        const tbody = document.getElementById('portfolio-positions-tbody');
        const countEl = document.getElementById('positions-count');
        if (!tbody) return;

        countEl.textContent = positions.length;

        if (positions.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-secondary);">No open positions</td></tr>';
            return;
        }

        let html = '';
        for (const pos of positions) {
            let desc = '';
            if (pos.position_type === 'option_spread') {
                desc = `${pos.option_type || ''} ${pos.strike}/${pos.short_strike} ${pos.spread_type || ''}`;
                if (pos.expiry) desc += ` ${formatExpiry(pos.expiry)}`;
            } else if (pos.position_type === 'option_single') {
                desc = `${pos.option_type || ''} ${pos.strike}`;
                if (pos.expiry) desc += ` ${formatExpiry(pos.expiry)}`;
            } else if (pos.position_type === 'short_stock') {
                desc = 'Short';
            } else {
                desc = 'Stock';
            }

            const cost = pos.cost_basis != null ? `$${parseFloat(pos.cost_basis).toFixed(2)}` : '\u2014';
            const value = pos.current_value != null ? `$${parseFloat(pos.current_value).toFixed(2)}` : '\u2014';

            let pnlHtml = '\u2014';
            if (pos.unrealized_pnl != null) {
                const pnl = parseFloat(pos.unrealized_pnl);
                const pnlPct = pos.unrealized_pnl_pct != null ? ` (${parseFloat(pos.unrealized_pnl_pct).toFixed(1)}%)` : '';
                const cls = pnl >= 0 ? 'pnl-positive' : 'pnl-negative';
                const sign = pnl >= 0 ? '+' : '-';
                pnlHtml = `<span class="${cls}">${sign}$${Math.abs(pnl).toFixed(2)}${pnlPct}</span>`;
            }

            html += `<tr>
                <td><strong>${escapeHtml(pos.ticker)}</strong></td>
                <td>${escapeHtml(desc)}</td>
                <td>${pos.quantity}</td>
                <td>${cost}</td>
                <td>${value}</td>
                <td>${pnlHtml}</td>
            </tr>`;
        }

        tbody.innerHTML = html;
    } catch (err) {
        console.error('Failed to load positions:', err);
    }
}

function formatExpiry(dateStr) {
    if (!dateStr) return '';
    const d = new Date(dateStr + 'T00:00:00');
    return `${d.getMonth()+1}/${d.getDate()}`;
}

setInterval(loadPortfolioBalances, 60000);
setInterval(loadPortfolioPositions, 60000);


// Display effective bias when hierarchical modifier is applied
function updateEffectiveBias(timeframe, rawLevel, effectiveLevel, modifierDetails) {
    const container = document.getElementById(`${timeframe}Bias`);
    const effectiveEl = document.getElementById(`${timeframe}Effective`);
    
    if (!effectiveEl) return;
    
    const levelEl = effectiveEl.querySelector('.effective-level');
    if (levelEl) {
        levelEl.textContent = effectiveLevel.replace('_', ' ');
        
        // Determine if it's a boost or drag
        const rawValue = getBiasValue(rawLevel);
        const effectiveValue = getBiasValue(effectiveLevel);
        
        levelEl.classList.remove('boost', 'drag');
        if (effectiveValue > rawValue) {
            levelEl.classList.add('boost');
        } else if (effectiveValue < rawValue) {
            levelEl.classList.add('drag');
        }
    }
    
    // Show the effective display
    effectiveEl.style.display = 'flex';
    
    // Add modifier indicator to card
    if (container) {
        container.classList.add('has-modifier');
        container.classList.remove('modifier-boost', 'modifier-drag');
        
        const rawValue = getBiasValue(rawLevel);
        const effectiveValue = getBiasValue(effectiveLevel);
        if (effectiveValue > rawValue) {
            container.classList.add('modifier-boost');
        } else if (effectiveValue < rawValue) {
            container.classList.add('modifier-drag');
        }
    }
    
    // Add tooltip with modifier details if available
    if (modifierDetails && effectiveEl) {
        const reason = modifierDetails.adjustment_reason || 'hierarchical modifier';
        const modifierName = modifierDetails.modifier_name || 'higher timeframe';
        effectiveEl.title = `Modified by ${modifierName}: ${reason.replace(/_/g, ' ')}`;
    }
}

// Hide effective bias display
function hideEffectiveBias(timeframe) {
    const effectiveEl = document.getElementById(`${timeframe}Effective`);
    const container = document.getElementById(`${timeframe}Bias`);
    
    if (effectiveEl) {
        effectiveEl.style.display = 'none';
    }
    
    if (container) {
        container.classList.remove('has-modifier', 'modifier-boost', 'modifier-drag');
    }
}

// Convert bias level to numeric value for comparison
function getBiasValue(level) {
    const values = {
        // New 6-level system
        'MAJOR_TORO': 6, 'MAJOR TORO': 6,
        'MINOR_TORO': 5, 'MINOR TORO': 5,
        'LEAN_TORO': 4, 'LEAN TORO': 4,
        'LEAN_URSA': 3, 'LEAN URSA': 3,
        'MINOR_URSA': 2, 'MINOR URSA': 2,
        'MAJOR_URSA': 1, 'MAJOR URSA': 1,
        // Legacy mappings
        'TORO_MAJOR': 6, 'TORO MAJOR': 6,
        'TORO_MINOR': 5, 'TORO MINOR': 5,
        'NEUTRAL': 4,  // Map to LEAN_TORO
        'URSA_MINOR': 2, 'URSA MINOR': 2,
        'URSA_MAJOR': 1, 'URSA MAJOR': 1
    };
    return values[level?.toUpperCase()?.replace('_', ' ')] || 4;  // Default LEAN_TORO
}

// Check if bias level is bullish (TORO-based)
function isBullishBias(level) {
    return level && (level.toUpperCase().includes('TORO') || getBiasValue(level) >= 4);
}

// Check if bias level is bearish (URSA-based)
function isBearishBias(level) {
    return level && (level.toUpperCase().includes('URSA') || getBiasValue(level) <= 3);
}

// Check and apply alignment styling when Cyclical and Weekly are aligned
function checkAndApplyBiasAlignment() {
    const container = document.querySelector('.container');
    const alignmentIndicator = document.getElementById('biasAlignmentIndicator');
    const alignmentText = document.getElementById('alignmentText');
    
    if (!container) return;
    
    // Remove existing alignment classes
    container.classList.remove('bias-aligned-bullish', 'bias-aligned-bearish');
    
    // Get current bias levels
    const cyclicalLevel = cyclicalBiasFullData?.level || '';
    const weeklyLevel = weeklyBiasFullData?.level || '';
    
    const alignment = getBiasAlignmentStatus(cyclicalLevel, weeklyLevel);

    if (alignment.alignmentClass) {
        container.classList.add(alignment.alignmentClass);
    }

    if (alignmentText) alignmentText.textContent = alignment.alignmentText;
}

// Check and display crisis alert when tiered factors are in crisis mode
function checkAndDisplayCrisisAlert(cyclicalData) {
    const crisisBanner = document.getElementById('crisisAlertBanner');
    const crisisFactorsEl = document.getElementById('crisisFactors');
    
    if (!crisisBanner) return;
    
    // Check if crisis mode is active from the cyclical data
    const details = cyclicalData?.details || {};
    const crisisActive = details.crisis_mode_active || false;
    const factors = details.factors || {};
    
    if (crisisActive) {
        // Find which factors are in crisis tier
        const crisisFactorNames = [];
        
        Object.keys(factors).forEach(factorName => {
            const factorData = factors[factorName];
            const tier = factorData?.details?.tier || 'standard';
            
            if (tier.startsWith('crisis')) {
                // Convert factor name to readable format
                const readableName = factorName
                    .replace(/_/g, ' ')
                    .replace(/\b\w/g, l => l.toUpperCase());
                
                const status = factorData?.details?.status || tier;
                crisisFactorNames.push(`${readableName} (${status})`);
            }
        });
        
        if (crisisFactorNames.length > 0) {
            crisisFactorsEl.textContent = crisisFactorNames.join(', ');
            crisisBanner.classList.add('active');
            crisisBanner.style.display = 'flex';
            console.warn('CRISIS MODE ACTIVE:', crisisFactorNames);
        }
    } else {
        // No crisis - hide the banner
        crisisBanner.classList.remove('active');
        crisisBanner.style.display = 'none';
    }
}

// Savita Indicator Update Functions (Optional - bonus factor when BofA data available)
function checkSavitaStatus(cyclicalData) {
    const btn = document.getElementById('savitaUpdateBtn');
    if (!btn) return;
    
    const factors = cyclicalData?.details?.factors || {};
    const savitaData = factors.savita_indicator?.details || {};
    
    // Check Savita freshness
    const lastUpdated = savitaData.last_updated || savitaData.reading?.last_updated;
    
    if (!lastUpdated) {
        // No Savita data - just show normal button
        btn.classList.remove('stale');
        btn.title = 'Add Savita Indicator (optional)';
        return;
    }
    
    // Check if data is stale (>30 days old)
    const updateDate = new Date(lastUpdated);
    const now = new Date();
    const daysSinceUpdate = Math.floor((now - updateDate) / (1000 * 60 * 60 * 24));
    
    if (daysSinceUpdate > 30) {
        // Stale - add pulse animation
        btn.classList.add('stale');
        btn.title = `Savita inactive (${daysSinceUpdate}d old) - click to update`;
    } else if (daysSinceUpdate > 20) {
        // Getting stale soon
        btn.classList.add('stale');
        btn.title = `Savita getting stale (${daysSinceUpdate}d) - consider updating`;
    } else {
        // Fresh and active
        btn.classList.remove('stale');
        btn.title = `Savita active (updated ${daysSinceUpdate}d ago)`;
    }
}

function initSavitaUpdateModal() {
    const updateBtn = document.getElementById('savitaUpdateBtn');
    const modal = document.getElementById('savitaUpdateModal');
    const closeBtn = document.getElementById('closeSavitaModal');
    const cancelBtn = document.getElementById('cancelSavitaUpdate');
    const submitBtn = document.getElementById('submitSavitaUpdate');
    
    if (!modal) return;
    
    // Open modal from new button
    if (updateBtn) {
        updateBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            openSavitaModal();
        });
    }
    
    async function openSavitaModal() {
        // Fetch current Savita status
        try {
            const response = await fetch(`${API_URL}/bias-auto/savita`);
            const result = await response.json();
            
            if (result.status === 'success') {
                const data = result.data;
                document.getElementById('savitaCurrentReading').textContent = data.reading || '--';
                document.getElementById('savitaLastUpdated').textContent = data.last_updated || '--';
                
                // Check if stale
                const currentInfo = document.getElementById('savitaCurrentInfo');
                if (data.last_updated) {
                    const daysSince = Math.floor((new Date() - new Date(data.last_updated)) / (1000 * 60 * 60 * 24));
                    if (daysSince > 30) {
                        currentInfo.classList.add('stale');
                        currentInfo.innerHTML = `<strong>DISABLED (${daysSince}d old)</strong> - Savita not affecting score until updated`;
                    } else {
                        currentInfo.classList.remove('stale');
                    }
                }
            }
        } catch (error) {
            console.error('Error fetching Savita status:', error);
        }
        
        modal.classList.add('active');
    }
    
    // Close modal
    const closeModal = () => {
        modal.classList.remove('active');
        document.getElementById('savitaReading').value = '';
        document.getElementById('savitaDate').value = '';
    };
    
    closeBtn?.addEventListener('click', closeModal);
    cancelBtn?.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });
    
    // Submit update
    submitBtn?.addEventListener('click', async () => {
        const reading = parseFloat(document.getElementById('savitaReading').value);
        const date = document.getElementById('savitaDate').value;
        
        if (isNaN(reading) || reading < 40 || reading > 70) {
            alert('Please enter a valid reading between 40 and 70');
            return;
        }
        
        try {
            let url = `${API_URL}/bias-auto/savita/update?reading=${reading}`;
            if (date) url += `&date=${date}`;
            
            const response = await fetch(url, { method: 'POST' });
            const result = await response.json();
            
            if (result.status === 'success') {
                alert(`Savita updated to ${reading}%`);
                closeModal();
                
                // Refresh bias data and update button style
                await loadBiasData();
                updateSavitaButtonStatus();
            } else {
                alert('Error updating Savita: ' + (result.detail || 'Unknown error'));
            }
        } catch (error) {
            console.error('Error updating Savita:', error);
            alert('Error updating Savita');
        }
    });
}

// Update Savita button style based on data freshness
function updateSavitaButtonStatus() {
    const btn = document.getElementById('savitaUpdateBtn');
    if (!btn) return;
    
    // Check if Savita data is stale (could be enhanced with actual data check)
    // For now, remove stale class after update
    btn.classList.remove('stale');
}

function updateBiasWithTrend(timeframe, biasData) {
    const container = document.getElementById(`${timeframe}Bias`);
    const levelElement = document.getElementById(`${timeframe}Level`);
    const detailsElement = document.getElementById(`${timeframe}Details`);
    
    if (!biasData) {
        if (detailsElement) detailsElement.textContent = 'Awaiting first refresh';
        return;
    }
    
    const rawLevel = biasData.level || 'LEAN_TORO';
    const trend = biasData.trend || 'NEW';
    const previousLevel = biasData.previous_level;
    const timestamp = biasData.timestamp;
    
    // Apply personal bias adjustment if enabled for this timeframe
    let level = rawLevel;
    let personalBiasApplied = false;
    if (personalBias !== 'NEUTRAL' && personalBiasAppliesTo[timeframe]) {
        const rawValue = getBiasValue(rawLevel);
        let adjustedValue = rawValue;
        
        if (personalBias === 'TORO') {
            adjustedValue = Math.min(6, rawValue + 1);
        } else if (personalBias === 'URSA') {
            adjustedValue = Math.max(1, rawValue - 1);
        }
        
        if (adjustedValue !== rawValue) {
            const levelMap = {6: 'MAJOR_TORO', 5: 'MINOR_TORO', 4: 'LEAN_TORO', 3: 'LEAN_URSA', 2: 'MINOR_URSA', 1: 'MAJOR_URSA'};
            level = levelMap[adjustedValue] || rawLevel;
            personalBiasApplied = true;
        }
    }
    
    // Update level display (preserve shift indicator if it exists, only for weekly)
    if (levelElement) {
        const shiftIndicator = (timeframe === 'weekly') ? levelElement.querySelector('.bias-shift-indicator') : null;
        levelElement.textContent = level.replace('_', ' ');
        levelElement.className = `bias-level ${level}`;
        // Re-add shift indicator if it existed (for weekly bias)
        if (shiftIndicator && timeframe === 'weekly') {
            levelElement.appendChild(shiftIndicator);
        }
    }
    
    // Update container styling
    if (container) {
        container.classList.remove('bullish', 'bearish', 'neutral');
        if (level.includes('TORO')) {
            container.classList.add('bullish');
        } else if (level.includes('URSA')) {
            container.classList.add('bearish');
        } else {
            container.classList.add('bullish');  // Default bullish in 6-level system
        }
    }
    
    // Update details with trend
    if (detailsElement) {
        let trendIcon = '';
        let trendText = '';
        
        switch (trend) {
            case 'IMPROVING':
                trendIcon = '&uarr;';
                trendText = `vs ${(previousLevel || 'N/A').replace('_', ' ')}`;
                break;
            case 'DECLINING':
                trendIcon = '&darr;';
                trendText = `vs ${(previousLevel || 'N/A').replace('_', ' ')}`;
                break;
            case 'STABLE':
                trendIcon = '&rarr;';
                trendText = 'unchanged';
                break;
            default:
                trendIcon = '&bull;';
                trendText = 'first reading';
        }
        
        // Format timestamp in Eastern Time (market hours)
        let timeStr = '';
        if (timestamp) {
            const date = new Date(timestamp);
            timeStr = date.toLocaleString('en-US', { 
                timeZone: 'America/New_York',
                month: 'short', 
                day: 'numeric',
                hour: 'numeric',
                minute: '2-digit'
            }) + ' ET';
        }
        
        const details = biasData?.details || {};
        const totalVote = Number.isFinite(Number(details.total_vote)) ? Number(details.total_vote) : null;
        const maxVote =
            Number.isFinite(Number(details.max_possible))
                ? Number(details.max_possible)
                : Number.isFinite(Number(details.max_possible_current))
                    ? Number(details.max_possible_current)
                    : Number.isFinite(Number(details.max_possible_normal))
                        ? Number(details.max_possible_normal)
                        : null;
        const factorCount = details.factors && typeof details.factors === 'object'
            ? Object.keys(details.factors).length
            : null;
        const source = details.source || null;

        const metaParts = [];
        if (totalVote !== null && maxVote !== null) metaParts.push(`vote ${totalVote}/${maxVote}`);
        if (factorCount !== null) metaParts.push(`${factorCount} factors`);
        if (source) metaParts.push(source.replaceAll('_', ' '));

        detailsElement.innerHTML = `
            <span class="trend-indicator trend-${trend.toLowerCase()}">${trendIcon}</span> ${trendText}
            ${metaParts.length ? `<br><small>${metaParts.join(' | ')}</small>` : ''}
            ${timeStr ? `<br><small>Updated: ${timeStr}</small>` : ''}
        `;
    }
}

// Update weekly bias with factor filtering
function updateWeeklyBiasWithFactors(biasData) {
    if (!biasData || !biasData.details || !biasData.details.factors) {
        // Fallback to regular update if no factor data
        updateBiasWithTrend('weekly', biasData);
        return;
    }
    
    // Load factor states from localStorage
    loadFactorStatesFromStorage();
    
    // Preserve shift indicator before updating
    const weeklyLevelElement = document.getElementById('weeklyLevel');
    const shiftIndicator = weeklyLevelElement ? weeklyLevelElement.querySelector('.bias-shift-indicator') : null;
    
    // Calculate filtered vote total
    const factors = biasData.details.factors;
    let filteredVote = 0;
    let enabledCount = 0;
    
    Object.keys(factors).forEach(factorName => {
        if (weeklyBiasFactorStates[factorName]) {
            filteredVote += factors[factorName].vote || 0;
            enabledCount++;
        }
    });
    
    // 6-level system thresholds (scaled by enabled factors)
    const totalFactors = Math.max(1, Object.keys(factors).length);
    const scaleFactor = enabledCount / totalFactors;
    const majorThreshold = Math.round(7 * scaleFactor);
    const minorThreshold = Math.round(3 * scaleFactor);
    
    // 6-level system: MAJOR_TORO, MINOR_TORO, LEAN_TORO, LEAN_URSA, MINOR_URSA, MAJOR_URSA
    let newLevel;
    if (filteredVote >= majorThreshold) {
        newLevel = 'MAJOR_TORO';
    } else if (filteredVote >= minorThreshold) {
        newLevel = 'MINOR_TORO';
    } else if (filteredVote > 0) {
        newLevel = 'LEAN_TORO';
    } else if (filteredVote === 0) {
        newLevel = 'LEAN_TORO';  // Default bullish for ties
    } else if (filteredVote > -minorThreshold) {
        newLevel = 'LEAN_URSA';
    } else if (filteredVote > -majorThreshold) {
        newLevel = 'MINOR_URSA';
    } else {
        newLevel = 'MAJOR_URSA';
    }
    
    // Create modified bias data for display
    const modifiedBiasData = {
        ...biasData,
        level: newLevel,
        filtered_vote: filteredVote,
        enabled_factors: enabledCount
    };
    
    // Update display
    updateBiasWithTrend('weekly', modifiedBiasData);
    
    // Re-add shift indicator if it existed
    if (shiftIndicator && weeklyLevelElement) {
        weeklyLevelElement.appendChild(shiftIndicator);
    }
    
    // Show/hide warning badge
    updateWarningBadge(enabledCount, 'weekly', totalFactors);
}

// Check if new day and reset factors
function checkAndResetFactorsForNewDay(biasData) {
    if (!biasData || !biasData.timestamp) return;
    
    const lastResetDate = localStorage.getItem('weeklyBiasLastReset');
    const currentDate = new Date(biasData.timestamp).toDateString();
    
    if (!lastResetDate || lastResetDate !== currentDate) {
        // New day detected - reset all factors to enabled
        weeklyBiasFactorStates = {
            index_trends: true,
            dollar_trend: true,
            sector_rotation: true,
            credit_spreads: true,
            market_breadth: true,
            vix_term_structure: true
        };
        localStorage.setItem('weeklyBiasFactors', JSON.stringify(weeklyBiasFactorStates));
        localStorage.setItem('weeklyBiasLastReset', currentDate);
        console.log('ðŸ”„ New day detected - reset all weekly bias factors to enabled');
    }
}

// Load factor states from localStorage
function loadFactorStatesFromStorage() {
    const stored = localStorage.getItem('weeklyBiasFactors');
    if (stored) {
        try {
            weeklyBiasFactorStates = { ...weeklyBiasFactorStates, ...JSON.parse(stored) };
        } catch (e) {
            console.error('Error loading factor states:', e);
        }
    }
}

// Save factor states to localStorage
function saveFactorStatesToStorage() {
    localStorage.setItem('weeklyBiasFactors', JSON.stringify(weeklyBiasFactorStates));
}

// Update warning badge for any timeframe
function updateWarningBadge(enabledCount, timeframe = 'weekly', totalFactorsOverride = null) {
    const levelElement = document.getElementById(`${timeframe}Level`);
    if (!levelElement) return;
    
    // Remove existing warning badge
    const existingBadge = levelElement.querySelector('.bias-warning-badge');
    if (existingBadge) {
        existingBadge.remove();
    }
    
    const totalFactors = Number.isFinite(totalFactorsOverride) && totalFactorsOverride > 0
        ? totalFactorsOverride
        : Math.max(1, getConfiguredFactorCount(timeframe));

    // Add warning if not all factors enabled
    if (enabledCount < totalFactors) {
        const badge = document.createElement('span');
        badge.className = 'bias-warning-badge';
        badge.textContent = '!';
        badge.title = `${enabledCount} of ${totalFactors} factors active`;
        levelElement.appendChild(badge);
    }
}

function getConfiguredFactorCount(timeframe) {
    if (timeframe === 'daily') return Object.keys(dailyBiasFactorStates).length;
    if (timeframe === 'cyclical') return Object.keys(cyclicalBiasFactorStates).length;
    return Object.keys(weeklyBiasFactorStates).length;
}

// Update Daily Bias with factor filtering
function updateDailyBiasWithFactors(biasData) {
    if (!biasData || !biasData.details || !biasData.details.factors) {
        updateBiasWithTrend('daily', biasData);
        return;
    }
    
    const factors = biasData.details.factors;
    let filteredVote = 0;
    let enabledCount = 0;
    
    Object.keys(factors).forEach(factorName => {
        if (dailyBiasFactorStates[factorName]) {
            filteredVote += factors[factorName].vote || 0;
            enabledCount++;
        }
    });
    
    // 6-level system thresholds (scaled by enabled factors)
    const totalFactors = Math.max(1, Object.keys(factors).length);
    const scaleFactor = enabledCount / totalFactors;
    const majorThreshold = Math.round(8 * scaleFactor);
    const minorThreshold = Math.round(4 * scaleFactor);
    
    // 6-level system: MAJOR_TORO, MINOR_TORO, LEAN_TORO, LEAN_URSA, MINOR_URSA, MAJOR_URSA
    let newLevel;
    if (filteredVote >= majorThreshold) {
        newLevel = 'MAJOR_TORO';
    } else if (filteredVote >= minorThreshold) {
        newLevel = 'MINOR_TORO';
    } else if (filteredVote > 0) {
        newLevel = 'LEAN_TORO';
    } else if (filteredVote === 0) {
        newLevel = 'LEAN_TORO';  // Default bullish for ties
    } else if (filteredVote > -minorThreshold) {
        newLevel = 'LEAN_URSA';
    } else if (filteredVote > -majorThreshold) {
        newLevel = 'MINOR_URSA';
    } else {
        newLevel = 'MAJOR_URSA';
    }
    
    const modifiedBiasData = {
        ...biasData,
        level: newLevel,
        filtered_vote: filteredVote,
        enabled_factors: enabledCount
    };
    
    updateBiasWithTrend('daily', modifiedBiasData);
    updateWarningBadge(enabledCount, 'daily', totalFactors);
}

// Update Cyclical Bias with factor filtering
function updateCyclicalBiasWithFactors(biasData) {
    if (!biasData || !biasData.details || !biasData.details.factors) {
        updateBiasWithTrend('cyclical', biasData);
        return;
    }
    
    const factors = biasData.details.factors;
    let filteredVote = 0;
    let enabledCount = 0;
    
    Object.keys(factors).forEach(factorName => {
        if (cyclicalBiasFactorStates[factorName]) {
            filteredVote += factors[factorName].vote || 0;
            enabledCount++;
        }
    });
    
    // 6-level system thresholds (scaled by enabled factors)
    const totalFactors = Math.max(1, Object.keys(factors).length);
    const scaleFactor = enabledCount / totalFactors;
    const majorThreshold = Math.round(7 * scaleFactor);
    const minorThreshold = Math.round(3 * scaleFactor);
    
    // 6-level system: MAJOR_TORO, MINOR_TORO, LEAN_TORO, LEAN_URSA, MINOR_URSA, MAJOR_URSA
    let newLevel;
    if (filteredVote >= majorThreshold) {
        newLevel = 'MAJOR_TORO';
    } else if (filteredVote >= minorThreshold) {
        newLevel = 'MINOR_TORO';
    } else if (filteredVote > 0) {
        newLevel = 'LEAN_TORO';
    } else if (filteredVote === 0) {
        newLevel = 'LEAN_TORO';  // Default bullish for ties
    } else if (filteredVote > -minorThreshold) {
        newLevel = 'LEAN_URSA';
    } else if (filteredVote > -majorThreshold) {
        newLevel = 'MINOR_URSA';
    } else {
        newLevel = 'MAJOR_URSA';
    }
    
    const modifiedBiasData = {
        ...biasData,
        level: newLevel,
        filtered_vote: filteredVote,
        enabled_factors: enabledCount
    };
    
    updateBiasWithTrend('cyclical', modifiedBiasData);
    updateWarningBadge(enabledCount, 'cyclical', totalFactors);
}

// Initialize Weekly Bias Settings Modal
function initWeeklyBiasSettings() {
    const settingsBtn = document.getElementById('weeklyBiasSettingsBtn');
    const modal = document.getElementById('weeklyBiasSettingsModal');
    const closeBtn = document.getElementById('closeWeeklyBiasSettingsBtn');
    const resetBtn = document.getElementById('resetFactorsBtn');
    const applyBtn = document.getElementById('applyFactorsBtn');
    
    if (!settingsBtn || !modal) {
        console.warn('Weekly bias settings elements not found');
        return;
    }
    
    // Open modal
    settingsBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        try {
            loadFactorStatesIntoModal('weekly', weeklyBiasFactorStates, weeklyBiasFullData);
        } catch (err) {
            console.error('Error loading factor states:', err);
        }
        modal.classList.add('active');
    });
    
    // Close modal
    const closeModal = () => {
        modal.classList.remove('active');
    };
    
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });
    
    // Reset all factors
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            document.querySelectorAll('#weeklyBiasSettingsModal input[type="checkbox"]').forEach(cb => {
                cb.checked = true;
            });
        });
    }
    
    // Apply factors
    if (applyBtn) {
        applyBtn.addEventListener('click', () => {
            // Save checkbox states
            document.querySelectorAll('#weeklyBiasSettingsModal .factor-toggle:not(.personal-bias-toggle)').forEach(toggle => {
                const factorName = toggle.dataset.factor;
                const checkbox = toggle.querySelector('input[type="checkbox"]');
                if (factorName) weeklyBiasFactorStates[factorName] = checkbox.checked;
            });
            
            // Save personal bias toggle for this timeframe
            const personalBiasToggle = document.getElementById('weeklyPersonalBiasToggle');
            if (personalBiasToggle) {
                personalBiasAppliesTo.weekly = personalBiasToggle.checked;
                savePersonalBiasState();
                reRenderBiasCardsWithPersonalBias();  // Re-render with new settings
                applyPersonalBiasToCards();  // Update badges
                checkBiasAlignment();
            }
            
            saveFactorStatesToStorage();
            
            // Recalculate and update display
            if (weeklyBiasFullData) {
                updateWeeklyBiasWithFactors(weeklyBiasFullData);
            }
            
            closeModal();
        });
    }
}

// Initialize Daily Bias Settings Modal
function initDailyBiasSettings() {
    const settingsBtn = document.getElementById('dailyBiasSettingsBtn');
    const modal = document.getElementById('dailyBiasSettingsModal');
    const closeBtn = document.getElementById('closeDailyBiasSettingsBtn');
    const resetBtn = document.getElementById('resetDailyFactorsBtn');
    const applyBtn = document.getElementById('applyDailyFactorsBtn');
    
    if (!settingsBtn || !modal) {
        console.warn('Daily bias settings elements not found');
        return;
    }
    
    // Open modal
    settingsBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        loadFactorStatesIntoModal('daily', dailyBiasFactorStates, dailyBiasFullData);
        modal.classList.add('active');
    });
    
    // Close modal
    const closeModal = () => modal.classList.remove('active');
    
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });
    
    // Reset all factors
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            document.querySelectorAll('#dailyBiasSettingsModal input[type="checkbox"]').forEach(cb => {
                cb.checked = true;
            });
        });
    }
    
    // Apply factors
    if (applyBtn) {
        applyBtn.addEventListener('click', () => {
            document.querySelectorAll('#dailyBiasSettingsModal .factor-toggle:not(.personal-bias-toggle)').forEach(toggle => {
                const factorName = toggle.dataset.factor;
                const checkbox = toggle.querySelector('input[type="checkbox"]');
                if (factorName) dailyBiasFactorStates[factorName] = checkbox.checked;
            });
            
            // Save personal bias toggle for this timeframe
            const personalBiasToggle = document.getElementById('dailyPersonalBiasToggle');
            if (personalBiasToggle) {
                personalBiasAppliesTo.daily = personalBiasToggle.checked;
                savePersonalBiasState();
                reRenderBiasCardsWithPersonalBias();  // Re-render with new settings
                applyPersonalBiasToCards();  // Update badges
                checkBiasAlignment();
            }
            
            saveDailyFactorStatesToStorage();
            
            if (dailyBiasFullData) {
                updateDailyBiasWithFactors(dailyBiasFullData);
            }
            
            closeModal();
        });
    }
}

// Initialize Cyclical Bias Settings Modal
function initCyclicalBiasSettings() {
    const settingsBtn = document.getElementById('cyclicalBiasSettingsBtn');
    const modal = document.getElementById('cyclicalBiasSettingsModal');
    const closeBtn = document.getElementById('closeCyclicalBiasSettingsBtn');
    const resetBtn = document.getElementById('resetCyclicalFactorsBtn');
    const applyBtn = document.getElementById('applyCyclicalFactorsBtn');
    
    if (!settingsBtn || !modal) {
        console.warn('Cyclical bias settings elements not found');
        return;
    }
    
    // Open modal
    settingsBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        loadFactorStatesIntoModal('cyclical', cyclicalBiasFactorStates, cyclicalBiasFullData);
        modal.classList.add('active');
    });
    
    // Close modal
    const closeModal = () => modal.classList.remove('active');
    
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });
    
    // Reset all factors
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            document.querySelectorAll('#cyclicalBiasSettingsModal input[type="checkbox"]').forEach(cb => {
                cb.checked = true;
            });
        });
    }
    
    // Apply factors
    if (applyBtn) {
        applyBtn.addEventListener('click', () => {
            document.querySelectorAll('#cyclicalBiasSettingsModal .factor-toggle:not(.personal-bias-toggle)').forEach(toggle => {
                const factorName = toggle.dataset.factor;
                const checkbox = toggle.querySelector('input[type="checkbox"]');
                if (factorName) cyclicalBiasFactorStates[factorName] = checkbox.checked;
            });
            
            // Save personal bias toggle for this timeframe
            const personalBiasToggle = document.getElementById('cyclicalPersonalBiasToggle');
            if (personalBiasToggle) {
                personalBiasAppliesTo.cyclical = personalBiasToggle.checked;
                savePersonalBiasState();
                reRenderBiasCardsWithPersonalBias();  // Re-render with new settings
                applyPersonalBiasToCards();  // Update badges
                checkBiasAlignment();
            }
            
            saveCyclicalFactorStatesToStorage();
            
            if (cyclicalBiasFullData) {
                updateCyclicalBiasWithFactors(cyclicalBiasFullData);
            }
            
            closeModal();
        });
    }
}

// =========================================================================
// PERSONAL BIAS & OVERRIDE CONTROLS
// =========================================================================

function initPersonalBiasControls() {
    const personalBiasSelector = document.getElementById('personalBiasSelector');
    const overrideToggle = document.getElementById('biasOverrideToggle');
    const overrideDirectionSelector = document.getElementById('overrideDirectionSelector');
    const biasSection = document.querySelector('.bias-section');
    
    if (!personalBiasSelector || !overrideToggle) {
        console.warn('Personal bias control elements not found');
        return;
    }
    
    // Load saved states from localStorage
    loadPersonalBiasState();
    
    // Personal Bias Selector
    personalBiasSelector.addEventListener('change', (e) => {
        personalBias = e.target.value;
        savePersonalBiasState();
        
        // Re-render bias cards with new personal bias applied
        reRenderBiasCardsWithPersonalBias();
        
        // Update badges and alignment styling
        applyPersonalBiasToCards();
        checkBiasAlignment();
        
        console.log(`Personal bias set to: ${personalBias}`);
    });
    
    // Override Toggle
    overrideToggle.addEventListener('click', () => {
        biasOverrideActive = !biasOverrideActive;
        overrideToggle.dataset.active = biasOverrideActive.toString();
        overrideToggle.textContent = biasOverrideActive ? 'ON' : 'OFF';
        overrideDirectionSelector.disabled = !biasOverrideActive;
        
        // Update override direction data attribute
        const isBullish = biasOverrideDirection.includes('TORO');
        overrideToggle.dataset.direction = isBullish ? 'bullish' : 'bearish';
        
        // Update UI state - apply override styling to container
        applyOverrideStyling();
        
        // Update override banner
        updateOverrideBanner();
        
        savePersonalBiasState();
        
        // Re-render signals with new bias state
        if (typeof renderSignals === 'function') {
            refreshSignalViews();
        }
        
        console.log(`Bias override: ${biasOverrideActive ? 'ACTIVE' : 'INACTIVE'} - ${biasOverrideDirection}`);
    });
    
    // Override Direction Selector
    overrideDirectionSelector.addEventListener('change', (e) => {
        biasOverrideDirection = e.target.value;
        
        // Update override toggle direction attribute
        const isBullish = biasOverrideDirection.includes('TORO');
        overrideToggle.dataset.direction = isBullish ? 'bullish' : 'bearish';
        
        // Update styling
        applyOverrideStyling();
        updateOverrideBanner();
        savePersonalBiasState();
        
        // Re-render signals with new bias
        if (typeof renderSignals === 'function') {
            refreshSignalViews();
        }
        
        console.log(`Override direction set to: ${biasOverrideDirection}`);
    });
    
    // Apply initial state
    applyPersonalBiasToCards();
    applyOverrideStyling();
    updateOverrideBanner();
}

// Apply override styling to container and all sections
function applyOverrideStyling() {
    const container = document.querySelector('.container');
    if (!container) return;
    
    // Remove existing override classes
    container.classList.remove('override-active-bullish', 'override-active-bearish');
    
    // Also remove from body for wider support
    document.body.classList.remove('override-active-bullish', 'override-active-bearish');
    
    if (biasOverrideActive) {
        const isBullish = biasOverrideDirection.includes('TORO');
        const overrideClass = isBullish ? 'override-active-bullish' : 'override-active-bearish';
        container.classList.add(overrideClass);
        document.body.classList.add(overrideClass);
        console.log(`Override styling applied: ${overrideClass}`);
    } else {
        console.log('Override styling removed');
    }
}

function loadPersonalBiasState() {
    try {
        const saved = localStorage.getItem('personalBiasState');
        if (saved) {
            const state = JSON.parse(saved);
            personalBias = state.personalBias || 'NEUTRAL';
            biasOverrideActive = state.biasOverrideActive || false;
            biasOverrideDirection = state.biasOverrideDirection || 'MAJOR_TORO';
            
            // Load per-timeframe personal bias toggles
            if (state.personalBiasAppliesTo) {
                personalBiasAppliesTo = {
                    daily: state.personalBiasAppliesTo.daily !== false,
                    weekly: state.personalBiasAppliesTo.weekly !== false,
                    cyclical: state.personalBiasAppliesTo.cyclical !== false
                };
            }
        }
        
        // Apply to per-timeframe toggle checkboxes
        const dailyToggle = document.getElementById('dailyPersonalBiasToggle');
        const weeklyToggle = document.getElementById('weeklyPersonalBiasToggle');
        const cyclicalToggle = document.getElementById('cyclicalPersonalBiasToggle');
        
        if (dailyToggle) dailyToggle.checked = personalBiasAppliesTo.daily;
        if (weeklyToggle) weeklyToggle.checked = personalBiasAppliesTo.weekly;
        if (cyclicalToggle) cyclicalToggle.checked = personalBiasAppliesTo.cyclical;
        
        // Apply to UI elements
        const personalBiasSelector = document.getElementById('personalBiasSelector');
        const overrideToggle = document.getElementById('biasOverrideToggle');
        const overrideDirectionSelector = document.getElementById('overrideDirectionSelector');
        const biasSection = document.querySelector('.bias-section');
        
        if (personalBiasSelector) personalBiasSelector.value = personalBias;
        if (overrideToggle) {
            overrideToggle.dataset.active = biasOverrideActive.toString();
            overrideToggle.textContent = biasOverrideActive ? 'ON' : 'OFF';
            // Set direction attribute for styling
            const isBullish = biasOverrideDirection.includes('TORO');
            overrideToggle.dataset.direction = isBullish ? 'bullish' : 'bearish';
        }
        if (overrideDirectionSelector) {
            overrideDirectionSelector.value = biasOverrideDirection;
            overrideDirectionSelector.disabled = !biasOverrideActive;
        }
        if (biasSection) {
            biasSection.classList.toggle('override-active', biasOverrideActive);
        }
        
        // Apply override styling to container
        applyOverrideStyling();
        
    } catch (e) {
        console.error('Error loading personal bias state:', e);
    }
}

function savePersonalBiasState() {
    try {
        localStorage.setItem('personalBiasState', JSON.stringify({
            personalBias,
            biasOverrideActive,
            biasOverrideDirection,
            personalBiasAppliesTo
        }));
    } catch (e) {
        console.error('Error saving personal bias state:', e);
    }
}

function reRenderBiasCardsWithPersonalBias() {
    // Re-render all bias cards from cached data with new personal bias applied
    // This avoids an API call - just re-renders with existing data
    
    if (dailyBiasFullData) {
        if (dailyBiasFullData.details && dailyBiasFullData.details.factors) {
            updateDailyBiasWithFactors(dailyBiasFullData);
        } else {
            updateBiasWithTrend('daily', dailyBiasFullData);
        }
    }
    
    if (weeklyBiasFullData) {
        if (weeklyBiasFullData.details && weeklyBiasFullData.details.factors) {
            updateWeeklyBiasWithFactors(weeklyBiasFullData);
        } else {
            updateBiasWithTrend('weekly', weeklyBiasFullData);
        }
    }
    
    if (cyclicalBiasFullData) {
        if (cyclicalBiasFullData.details && cyclicalBiasFullData.details.factors) {
            updateCyclicalBiasWithFactors(cyclicalBiasFullData);
        } else {
            updateBiasWithTrend('cyclical', cyclicalBiasFullData);
        }
    }
    
    console.log('Bias cards re-rendered with personal bias adjustment');
}

function applyPersonalBiasToCards() {
    // Remove existing badges
    document.querySelectorAll('.personal-bias-badge').forEach(b => b.remove());
    
    if (personalBias === 'NEUTRAL') return;
    
    // Add badge to each bias card where personal bias is enabled for that timeframe
    const timeframeMap = {
        'dailyBias': 'daily',
        'weeklyBias': 'weekly',
        'cyclicalBias': 'cyclical'
    };
    
    Object.entries(timeframeMap).forEach(([cardId, timeframe]) => {
        // Only add badge if personal bias is enabled for this timeframe
        if (!personalBiasAppliesTo[timeframe]) return;
        
        const card = document.getElementById(cardId);
        if (!card) return;
        
        const biasLevel = card.querySelector('.bias-level');
        const biasDetails = card.querySelector('.bias-details');
        
        if (biasLevel && biasDetails) {
            const badge = document.createElement('div');
            badge.className = `personal-bias-badge ${personalBias.toLowerCase()}`;
            badge.textContent = personalBias === 'TORO' ? '+1 Personal Bias' : '-1 Personal Bias';
            badge.title = `Your personal ${personalBias} bias adds ${personalBias === 'TORO' ? '+1' : '-1'} to the score`;
            
            // Insert after bias-level (and bias-effective if present)
            const biasEffective = card.querySelector('.bias-effective');
            const insertAfter = biasEffective || biasLevel;
            insertAfter.parentNode.insertBefore(badge, insertAfter.nextSibling);
        }
    });
}

function updateOverrideBanner() {
    const banner = document.getElementById('overrideActiveBanner');
    const biasDisplay = document.getElementById('overrideBiasDisplay');
    
    if (banner && biasDisplay) {
        biasDisplay.textContent = biasOverrideDirection.replace('_', ' ');
    }
}

/**
 * Get the effective bias for trade filtering
 * When override is active, returns the override direction
 * Otherwise, returns the calculated bias with personal bias modifier
 */
function getEffectiveTradingBias() {
    if (biasOverrideActive) {
        return {
            level: biasOverrideDirection,
            isOverride: true,
            personalBias: personalBias
        };
    }
    
    // Get current daily bias (or use LEAN_TORO if not loaded - bullish default)
    const dailyLevel = dailyBiasFullData?.level || 'LEAN_TORO';
    const weeklyLevel = weeklyBiasFullData?.level || 'LEAN_TORO';
    const cyclicalLevel = cyclicalBiasFullData?.level || 'LEAN_TORO';
    
    // Calculate composite score
    let compositeScore = getBiasValue(dailyLevel);
    
    // Add personal bias modifier
    if (personalBias === 'TORO') {
        compositeScore += 1;
    } else if (personalBias === 'URSA') {
        compositeScore -= 1;
    }
    
    // Clamp to valid range [1, 6]
    compositeScore = Math.max(1, Math.min(6, compositeScore));
    
    // Convert back to level name (6-level system)
    const levelMap = {6: 'MAJOR_TORO', 5: 'MINOR_TORO', 4: 'LEAN_TORO', 3: 'LEAN_URSA', 2: 'MINOR_URSA', 1: 'MAJOR_URSA'};
    const effectiveLevel = levelMap[compositeScore] || 'LEAN_TORO';
    
    return {
        level: effectiveLevel,
        rawDaily: dailyLevel,
        rawWeekly: weeklyLevel,
        rawCyclical: cyclicalLevel,
        isOverride: false,
        personalBias: personalBias,
        personalModifier: personalBias === 'NEUTRAL' ? 0 : (personalBias === 'TORO' ? 1 : -1)
    };
}

/**
 * Check if a trade signal aligns with current bias
 * Used by Trade Ideas filtering
 */
function isSignalAlignedWithBias(signalDirection) {
    const bias = getEffectiveTradingBias();
    const biasValue = getBiasValue(bias.level);
    
    if (signalDirection === 'LONG') {
        // LONG signals align with bullish bias (TORO levels: >= 4)
        return biasValue >= 4;
    } else if (signalDirection === 'SHORT') {
        // SHORT signals align with bearish bias (URSA levels: <= 3)
        return biasValue <= 3;
    }
    
    return true; // Unknown direction, allow
}

// Generic function to load factor states into any modal
function loadFactorStatesIntoModal(timeframe, factorStates, fullData) {
    try {
        const modalId = `${timeframe}BiasSettingsModal`;
        
        // Load from storage first
        const stored = localStorage.getItem(`${timeframe}BiasFactors`);
        if (stored) {
            try {
                Object.assign(factorStates, JSON.parse(stored));
            } catch (e) {
                console.error(`Error loading ${timeframe} factor states:`, e);
            }
        }
        
        // Update checkboxes
        document.querySelectorAll(`#${modalId} .factor-toggle`).forEach(toggle => {
            const factorName = toggle.dataset.factor;
            const checkbox = toggle.querySelector('input[type="checkbox"]');
            if (checkbox) {
                checkbox.checked = factorStates[factorName] !== false;
            }
        });
        
        // Update vote displays if we have factor data
        if (fullData && fullData.details && fullData.details.factors) {
            const factors = fullData.details.factors;
            document.querySelectorAll(`#${modalId} .factor-toggle:not(.personal-bias-toggle)`).forEach(toggle => {
                const factorName = toggle.dataset.factor;
                const voteElement = toggle.querySelector('.factor-vote');
                if (voteElement && factors[factorName]) {
                    const vote = factors[factorName].vote || 0;
                    const sign = vote >= 0 ? '+' : '';
                    voteElement.textContent = `(vote: ${sign}${vote})`;
                    voteElement.dataset.vote = vote;
                }
            });
        }
        
        // Set personal bias toggle state for this timeframe
        const personalBiasToggle = document.getElementById(`${timeframe}PersonalBiasToggle`);
        if (personalBiasToggle) {
            personalBiasToggle.checked = personalBiasAppliesTo[timeframe] !== false;
        }
    } catch (err) {
        console.error(`Error in loadFactorStatesIntoModal for ${timeframe}:`, err);
    }
}

// Storage functions for each timeframe
function saveDailyFactorStatesToStorage() {
    localStorage.setItem('dailyBiasFactors', JSON.stringify(dailyBiasFactorStates));
}

function loadDailyFactorStatesFromStorage() {
    const stored = localStorage.getItem('dailyBiasFactors');
    if (stored) {
        try {
            dailyBiasFactorStates = { ...dailyBiasFactorStates, ...JSON.parse(stored) };
        } catch (e) {
            console.error('Error loading daily factor states:', e);
        }
    }
}

function saveCyclicalFactorStatesToStorage() {
    localStorage.setItem('cyclicalBiasFactors', JSON.stringify(cyclicalBiasFactorStates));
}

function loadCyclicalFactorStatesFromStorage() {
    const stored = localStorage.getItem('cyclicalBiasFactors');
    if (stored) {
        try {
            cyclicalBiasFactorStates = { ...cyclicalBiasFactorStates, ...JSON.parse(stored) };
        } catch (e) {
            console.error('Error loading cyclical factor states:', e);
        }
    }
}

// Fetch and display bias shift status (weekly bias shift from Monday baseline)
async function fetchBiasShiftStatus() {
    try {
        const response = await fetch(`${API_URL}/bias-auto/shift-status`);
        const data = await response.json();
        if (data.status === 'success') {
            updateBiasShiftDisplay(data.data);
        }
    } catch (error) {
        console.error('Error fetching bias shift:', error);
    }
}

// Update weekly bias display with shift indicator
function updateBiasShiftDisplay(shiftData) {
    const weeklyLevelElement = document.getElementById('weeklyLevel');
    const weeklyDetailsElement = document.getElementById('weeklyDetails');
    
    if (!shiftData || !weeklyLevelElement) {
        return;
    }
    
    // Remove any existing shift indicator
    const existingIndicator = weeklyLevelElement.querySelector('.bias-shift-indicator');
    if (existingIndicator) {
        existingIndicator.remove();
    }
    
    // Check if we have baseline data
    if (!shiftData.has_baseline) {
        // No baseline yet - don't show indicator
        return;
    }
    
    const shiftDirection = shiftData.shift_direction || 'STABLE';
    const delta = shiftData.delta || 0;
    
    // Determine icon and class based on shift direction
    let shiftIcon = '';
    let shiftClass = '';
    let shiftText = '';
    
    switch (shiftDirection) {
        case 'IMPROVING':
        case 'STRONGLY_IMPROVING':
            shiftIcon = '^';
            shiftClass = 'bias-shift-improving';
            shiftText = shiftDirection === 'STRONGLY_IMPROVING' ? 'strongly improving' : 'improving';
            break;
        case 'DETERIORATING':
        case 'STRONGLY_DETERIORATING':
            shiftIcon = 'v';
            shiftClass = 'bias-shift-deteriorating';
            shiftText = shiftDirection === 'STRONGLY_DETERIORATING' ? 'strongly deteriorating' : 'deteriorating';
            break;
        case 'STABLE':
        default:
            shiftIcon = '-';
            shiftClass = 'bias-shift-stable';
            shiftText = 'stable';
            break;
    }
    
    // Create shift indicator element
    const shiftIndicator = document.createElement('span');
    shiftIndicator.className = `bias-shift-indicator ${shiftClass}`;
    
    // Add strong class for STRONGLY_* states
    if (shiftDirection === 'STRONGLY_IMPROVING' || shiftDirection === 'STRONGLY_DETERIORATING') {
        shiftIndicator.classList.add('bias-shift-strong');
    }
    
    // Format delta (always show sign)
    const deltaSign = delta >= 0 ? '+' : '';
    shiftIndicator.innerHTML = `${shiftIcon} ${deltaSign}${delta}`;
    shiftIndicator.title = `Shift: ${shiftText} (${deltaSign}${delta} from Monday baseline)`;
    
    // Append to level element (inline with bias level)
    weeklyLevelElement.appendChild(shiftIndicator);
}

async function loadBiasDataFallback() {
    // Fallback to old endpoints if scheduler not available
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
                const level = data.level || 'LEAN_TORO';
                levelElement.textContent = level.replace('_', ' ');
                
                if (container) {
                    container.classList.remove('bullish', 'bearish', 'neutral');
                    if (level.includes('TORO')) {
                        container.classList.add('bullish');
                    } else if (level.includes('URSA')) {
                        container.classList.add('bearish');
                    } else {
                        container.classList.add('bullish');  // Default to bullish in 6-level system
                    }
                }
            }
            
            if (detailsElement) {
                detailsElement.textContent = 'TICK: N/A';
            }
        } catch (error) {
            console.error(`Error loading ${timeframe} bias:`, error);
        }
    }
    
    // Load Cyclical separately (fallback)
    await loadCyclicalBiasFallback();
}

async function loadCyclicalBiasFallback() {
    try {
        // Try to load from bias-auto endpoint first
        const response = await fetch(`${API_URL}/bias-auto/CYCLICAL`);
        const result = await response.json();
        
        const container = document.getElementById('cyclicalBias');
        const levelElement = document.getElementById('cyclicalLevel');
        const detailsElement = document.getElementById('cyclicalDetails');
        
        if (result.status === 'success' && result.data) {
            const data = result.data;
            const bias = data.level || 'LEAN_TORO';
            
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
                const details = data.details || {};
                const totalVote = details.total_vote !== undefined ? details.total_vote : '?';
                const timestamp = data.timestamp ? new Date(data.timestamp).toLocaleString('en-US', {
                    timeZone: 'America/New_York',
                    month: 'short',
                    day: 'numeric',
                    hour: 'numeric',
                    minute: '2-digit'
                }) + ' ET' : 'Unknown';
                detailsElement.innerHTML = `
                    Vote: ${totalVote}/12 | Long-term macro<br>
                    <small>Updated: ${timestamp}</small>
                `;
            }
        } else {
            if (detailsElement) {
                detailsElement.textContent = 'Awaiting first refresh';
            }
        }
    } catch (error) {
        console.error('Error loading Cyclical bias:', error);
        const detailsElement = document.getElementById('cyclicalDetails');
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
            _open_positions_cache = data.positions || [];
            renderPositions(data.positions);
            renderCryptoPositions();
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
    
    if (activeSignals.length === 0) {
        const assetLabel = activeAssetType === 'equity' ? 'equity' : 'crypto';
        container.innerHTML = `<p class="empty-state">No ${assetLabel} signals</p>`;
        return;
    }
    
    const pagination = tradeIdeasPagination[activeAssetType];
    const loadMoreText = pagination?.loading ? 'Loading...' : 'Reload previous';
    const loadMoreDisabled = pagination?.loading ? 'disabled' : '';
    const loadMoreButton = pagination?.hasMore
        ? `<div class="trade-ideas-footer">
                <button class="reload-previous-btn" ${loadMoreDisabled}>${loadMoreText}</button>
           </div>`
        : '';
    
    container.innerHTML = activeSignals.map(signal => createSignalCard(signal)).join('') + loadMoreButton;
    
    // Add event listeners to action buttons and cards
    attachSignalActions();
    attachReloadPreviousHandler();
    
    // Attach KB link handlers to dynamically created content
    attachDynamicKbHandlers(container);
}

function getCryptoFilterState() {
    const enabledStrategies = new Set();
    document.querySelectorAll('.crypto-strategy-cb:checked').forEach(cb => {
        enabledStrategies.add(cb.dataset.strategy);
    });
    const allowLong = document.getElementById('cryptoFilterLong')?.checked !== false;
    const allowShort = document.getElementById('cryptoFilterShort')?.checked !== false;
    const minScore = parseInt(document.getElementById('cryptoScoreThreshold')?.value || '1', 10);
    return { enabledStrategies, allowLong, allowShort, minScore };
}

function renderCryptoSignals() {
    const container = document.getElementById('cryptoSignalsList');
    if (!container) return;

    const sortBy = document.getElementById('cryptoSignalSort')?.value || 'score';
    const filters = getCryptoFilterState();
    let cryptoSignals = [...signals.crypto];

    // Apply strategy filters
    cryptoSignals = cryptoSignals.filter(s => {
        const strategy = (s.strategy || '').toLowerCase().replace(/[\s-]/g, '_');
        if (filters.enabledStrategies.size > 0) {
            let matched = false;
            for (const enabled of filters.enabledStrategies) {
                // Exact match OR strategy is a versioned variant (e.g. "golden_touch_v2")
                // Use prefix check so partial checkbox keys like "touch" don't match "golden_touch"
                if (strategy === enabled || strategy.startsWith(enabled + '_')) {
                    matched = true;
                    break;
                }
            }
            if (!matched) return false;
        }
        const dir = (s.direction || '').toUpperCase();
        if (dir === 'LONG' && !filters.allowLong) return false;
        if (dir === 'SHORT' && !filters.allowShort) return false;
        if ((s.score || 0) < filters.minScore) return false;
        return true;
    });

    if (cryptoSignals.length === 0) {
        container.innerHTML = '<p class="empty-state">No crypto signals match filters</p>';
        return;
    }

    cryptoSignals.sort((a, b) => {
        const rankA = getCryptoSignalPriority(a);
        const rankB = getCryptoSignalPriority(b);
        if (rankA !== rankB) {
            return rankB - rankA;
        }
        if (sortBy === 'recency') {
            const timeA = new Date(a.timestamp || a.created_at || 0).getTime();
            const timeB = new Date(b.timestamp || b.created_at || 0).getTime();
            return timeB - timeA;
        }
        return (Number(b.score) || 0) - (Number(a.score) || 0);
    });

    container.innerHTML = cryptoSignals.map(signal => createCryptoSignalCard(signal)).join('');

    // Also update crypto positions
    renderCryptoPositions();
}

function refreshSignalViews() {
    if (typeof renderSignals === 'function') {
        renderSignals();
    }
    renderCryptoSignals();
}

function createCryptoSignalCard(signal) {
    const score = signal.score !== undefined && signal.score !== null ? Number(signal.score).toFixed(1) : '--';
    const scoreTier = typeof getScoreTier === 'function' ? getScoreTier(Number(score) || 0) : 'MODERATE';
    const direction = signal.direction || 'N/A';
    const strategy = signal.strategy || 'Crypto Scanner';
    const formatPrice = (val) => val ? `$${parseFloat(val).toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}` : '--';

    let timestampStr = '';
    if (signal.timestamp || signal.created_at) {
        try {
            let timeStr = signal.timestamp || signal.created_at;
            if (!timeStr.endsWith('Z') && !timeStr.includes('+') && !timeStr.includes('-', 10)) {
                timeStr += 'Z';
            }
            timestampStr = new Date(timeStr).toLocaleString('en-US', {
                hour: 'numeric', minute: '2-digit', month: 'short', day: 'numeric'
            });
        } catch (e) { /* ignore */ }
    }

    const badges = [];
    if (signal.signal_type === 'APIS_CALL') badges.push('<span class="crypto-badge apis">APIS</span>');
    if (signal.signal_type === 'KODIAK_CALL') badges.push('<span class="crypto-badge kodiak">KODIAK</span>');
    const strategyLower = (strategy || '').toLowerCase();
    if (strategyLower.includes('scout')) badges.push('<span class="crypto-badge scout">SCOUT</span>');
    if (strategyLower.includes('sniper')) badges.push('<span class="crypto-badge sniper">SNIPER</span>');
    if (strategyLower.includes('exhaustion')) badges.push('<span class="crypto-badge exhaustion">EXHAUST</span>');

    const biasAlignment = signal.bias_alignment || 'NEUTRAL';
    const isAligned = biasAlignment.includes('ALIGNED') && !biasAlignment.includes('COUNTER');
    const biasClass = isAligned ? 'aligned' : (biasAlignment.includes('COUNTER') ? 'counter' : '');
    const biasIcon = isAligned ? '&#10003;' : (biasAlignment.includes('COUNTER') ? '&#9888;' : '&#9675;');
    const biasText = biasAlignment.replace(/_/g, ' ');

    const signalTypeClass = signal.signal_type || '';

    return `
        <div class="crypto-signal-card ${signalTypeClass}" data-signal-id="${signal.signal_id || ''}" data-signal="${encodeURIComponent(JSON.stringify(signal))}">
            <div class="crypto-signal-header">
                <span class="crypto-signal-ticker" data-action="view-chart">${escapeHtml(signal.ticker || '--')}</span>
                <div class="crypto-signal-meta">
                    ${badges.join('')}
                    <span class="crypto-badge">${escapeHtml(direction)}</span>
                </div>
            </div>
            <div class="crypto-signal-score">
                <span class="crypto-score-value">${score}</span>
                <span class="crypto-score-tier ${scoreTier.toLowerCase()}">${scoreTier}</span>
                <span style="margin-left:auto;font-size:11px;color:var(--text-secondary)">${escapeHtml(strategy)}</span>
            </div>
            <div class="crypto-signal-details">
                <span><span class="crypto-signal-detail-label">Entry</span> <span class="crypto-signal-detail-value">${formatPrice(signal.entry_price)}</span></span>
                <span><span class="crypto-signal-detail-label">Stop</span> <span class="crypto-signal-detail-value">${formatPrice(signal.stop_loss)}</span></span>
                <span><span class="crypto-signal-detail-label">Target</span> <span class="crypto-signal-detail-value">${formatPrice(signal.target_1)}</span></span>
                <span><span class="crypto-signal-detail-label">R:R</span> <span class="crypto-signal-detail-value">${formatRiskReward(signal.risk_reward)}</span></span>
            </div>
            <div class="crypto-signal-bias ${biasClass}">${biasIcon} ${biasText}${timestampStr ? `  &middot;  ${timestampStr}` : ''}</div>
            <div class="crypto-signal-actions">
                <button class="action-btn dismiss-btn" data-action="dismiss">&#10005; Dismiss</button>
                <button class="action-btn select-btn" data-action="select">&#10003; Accept</button>
            </div>
        </div>
    `;
}

function createSignalCard(signal) {
    const typeLabel = (signal.signal_type || 'SIGNAL').replace('_', ' ');
    
    // Calculate score tier and pulse class
    const score = signal.score || 0;
    const scoreTier = getScoreTier(score);
    const isStrongSignal = score >= 75;
    const pulseClass = isStrongSignal ? 'signal-pulse' : '';
    
    // Check bias alignment from signal data or calculate
    const biasAlignment = signal.bias_alignment || 'NEUTRAL';
    const isAligned = biasAlignment.includes('ALIGNED') && !biasAlignment.includes('COUNTER');
    const biasAlignmentClass = isAligned ? 'bias-aligned' : (biasAlignment === 'NEUTRAL' ? '' : 'bias-misaligned');
    const biasAlignmentIcon = isAligned ? 'OK' : (biasAlignment.includes('COUNTER') ? '!' : 'o');
    const biasAlignmentText = biasAlignment.replace('_', ' ');
    
    // Safe number formatting
    const formatPrice = (val) => val ? parseFloat(val).toFixed(2) : '-';
    const formatRR = (val) => formatRiskReward(val);
    
    // Handle multiple strategies (deduplicated signals)
    let strategiesHtml = '';
    if (signal.strategies && signal.strategies.length > 1) {
        // Multiple strategies - show all
        strategiesHtml = signal.strategies.map(s => wrapWithKbLink(s)).join(' + ');
    } else {
        // Single strategy
        strategiesHtml = wrapWithKbLink(signal.strategy || 'Unknown');
    }
    
    const typeWithKb = wrapWithKbLink(typeLabel);
    
    // Format timestamp as "Jan 28, 1:45 PM" (convert from UTC)
    let timestampStr = '';
    if (signal.timestamp || signal.created_at) {
        try {
            // Server stores UTC without 'Z', so add it for proper parsing
            let timeStr = signal.timestamp || signal.created_at;
            if (!timeStr.endsWith('Z') && !timeStr.includes('+') && !timeStr.includes('-', 10)) {
                timeStr += 'Z';  // Treat as UTC
            }
            const signalDate = new Date(timeStr);
            const options = { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true };
            timestampStr = signalDate.toLocaleString('en-US', options);
        } catch (e) {
            timestampStr = '';
        }
    }
    
    const isCounterTrend = signal.is_counter_trend || signal.contrarian_qualified;
    const counterTrendClass = isCounterTrend ? 'counter-trend' : '';
    const counterTrendTag = isCounterTrend ? '<span class="counter-trend-tag">COUNTER-TREND</span>' : '';
    const contrarianTag = signal.contrarian_qualified ? '<span class="counter-trend-tag" style="color:#14b8a6;background:rgba(20,184,166,0.12)">CONTRARIAN</span>' : '';
    
    return `
        <div class="signal-card ${signal.signal_type || ''} ${biasAlignmentClass} ${pulseClass} ${counterTrendClass}" 
             data-signal-id="${signal.signal_id}" 
             data-signal="${encodeURIComponent(JSON.stringify(signal))}">
            
            <div class="signal-header">
                <div>
                    <div class="signal-type ${signal.signal_type || ''}">${typeWithKb}${counterTrendTag}${contrarianTag}</div>
                    <div class="signal-strategy">${strategiesHtml}</div>
                </div>
                <div class="signal-ticker ticker-link" data-action="view-chart">${signal.ticker}</div>
            </div>
            
            ${timestampStr ? `<div class="signal-timestamp">${timestampStr}</div>` : ''}
            
            <div class="signal-score-bar">
                <div class="score-label">Score</div>
                <div class="score-value ${scoreTier.toLowerCase()}">${score}</div>
                <div class="score-tier ${scoreTier.toLowerCase()}">${scoreTier}</div>
            </div>
            
            <div class="signal-details">
                <div class="signal-detail">
                    <div class="signal-detail-label">Entry</div>
                    <div class="signal-detail-value">${formatPrice(signal.entry_price)}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Stop</div>
                    <div class="signal-detail-value">${formatPrice(signal.stop_loss)}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Target</div>
                    <div class="signal-detail-value">${formatPrice(signal.target_1)}</div>
                </div>
            </div>
            
            <div class="signal-details">
                <div class="signal-detail">
                    <div class="signal-detail-label">R:R</div>
                    <div class="signal-detail-value">${formatRR(signal.risk_reward)}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Direction</div>
                    <div class="signal-detail-value direction-${(signal.direction || '').toLowerCase()}">${signal.direction || '-'}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Confidence</div>
                    <div class="signal-detail-value">${signal.confidence || '-'}</div>
                </div>
            </div>
            
            <div class="signal-bias-indicator ${biasAlignmentClass}" title="${biasAlignmentText}">
                <span class="bias-icon">${biasAlignmentIcon}</span>
                <span class="bias-text">${biasAlignmentText}</span>
            </div>
            
            <div class="signal-actions">
                <button class="action-btn dismiss-btn" data-action="dismiss">X Dismiss</button>
                <button class="action-btn select-btn" data-action="select">OK Accept</button>
            </div>
        </div>
    `;
}

function getBiasAlignmentStatus(cyclicalLevel, weeklyLevel) {
    const cyclicalBullish = isBullishBias(cyclicalLevel);
    const cyclicalBearish = isBearishBias(cyclicalLevel);
    const weeklyBullish = isBullishBias(weeklyLevel);
    const weeklyBearish = isBearishBias(weeklyLevel);

    if (cyclicalBullish && weeklyBullish) {
        return {
            note: 'Macro alignment: Bullish (Cyclical + Weekly aligned)',
            alignmentText: 'BULLISH ALIGNED',
            alignmentClass: 'bias-aligned-bullish'
        };
    }
    if (cyclicalBearish && weeklyBearish) {
        return {
            note: 'Macro alignment: Bearish (Cyclical + Weekly aligned)',
            alignmentText: 'BEARISH ALIGNED',
            alignmentClass: 'bias-aligned-bearish'
        };
    }
    return {
        note: 'Macro alignment: Mixed signals across timeframes',
        alignmentText: 'MIXED',
        alignmentClass: ''
    };
}

function renderCryptoBiasSummary() {
    const biasValues = {
        daily: _dailyBiasPrimaryData?.level || dailyBiasFullData?.level || 'NEUTRAL',
        composite: _compositeBiasData?.bias_level || 'NEUTRAL'
    };

    const inlineDaily = document.getElementById('cryptoBiasDaily');
    const inlineComposite = document.getElementById('cryptoCompositeInline');

    if (inlineDaily) inlineDaily.textContent = (biasValues.daily || '--').replace(/_/g, ' ');
    if (inlineComposite) inlineComposite.textContent = (biasValues.composite || 'NEUTRAL').replace(/_/g, ' ');

    const applyBiasPill = (pill, level) => {
        if (!pill) return;
        const biasKey = (level || 'NEUTRAL').toUpperCase();
        pill.classList.remove('TORO_MAJOR', 'TORO_MINOR', 'URSA_MINOR', 'URSA_MAJOR', 'NEUTRAL');
        pill.classList.add(biasKey);
    };

    applyBiasPill(document.querySelector('.bias-pill[data-bias="daily"]'), biasValues.daily);
    applyBiasPill(document.querySelector('.bias-pill[data-bias="composite"]'), biasValues.composite);

    const levelEl = document.getElementById('cryptoCompositeBiasLevel');
    const scoreEl = document.getElementById('cryptoCompositeBiasScore');
    const confEl = document.getElementById('cryptoCompositeBiasConfidence');

    const compositeLevel = (biasValues.composite || 'NEUTRAL').replace(/_/g, ' ');
    const compositeScoreVal = typeof _compositeBiasData?.composite_score === 'number'
        ? _compositeBiasData.composite_score
        : parseFloat(_compositeBiasData?.composite_score || 0);
    const compositeConf = (_compositeBiasData?.confidence || 'LOW').toUpperCase();
    const colors = BIAS_COLORS[_compositeBiasData?.bias_level] || BIAS_COLORS.NEUTRAL;

    if (levelEl) {
        levelEl.textContent = compositeLevel;
        levelEl.style.color = colors?.text || '#9fb7ff';
    }
    if (scoreEl) scoreEl.textContent = Number.isFinite(compositeScoreVal) ? `(${compositeScoreVal.toFixed(2)})` : '(--)';
    if (confEl) {
        confEl.textContent = compositeConf;
        confEl.style.color = CONFIDENCE_COLORS[compositeConf] || CONFIDENCE_COLORS.LOW;
    }
}

function getCryptoSignalPriority(signal) {
    const strategy = (signal.strategy || '').toLowerCase();
    if (strategy.includes('sniper')) return 3;
    if (strategy.includes('scout')) return 2;
    if (strategy.includes('exhaustion')) return 1;
    return 0;
}

function applyCryptoBiasPreset() {
    const autoToggle = document.getElementById('cryptoAutoBiasToggle');
    if (!autoToggle || !autoToggle.checked) return;

    const longCb = document.getElementById('cryptoFilterLong');
    const shortCb = document.getElementById('cryptoFilterShort');
    if (!longCb || !shortCb) return;

    const bias = (_compositeBiasData?.bias_level || 'NEUTRAL').toUpperCase();
    if (bias.includes('TORO')) {
        longCb.checked = true;
        shortCb.checked = false;
    } else if (bias.includes('URSA')) {
        longCb.checked = false;
        shortCb.checked = true;
    } else {
        longCb.checked = true;
        shortCb.checked = true;
    }
}

function renderCryptoPositions() {
    const container = document.getElementById('cryptoPositionsList');
    const countEl = document.getElementById('cryptoPositionsCount');
    if (!container) return;

    // Filter open positions for crypto
    const cryptoTickers = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'AVAX', 'DOGE', 'DOT', 'LINK', 'MATIC', 'LTC', 'UNI'];
    const cryptoPositions = _open_positions_cache.filter(p => {
        if (p.asset_class === 'CRYPTO') return true;
        const tickerBase = (p.ticker || '').toUpperCase().replace(/USD.*/, '');
        return cryptoTickers.includes(tickerBase);
    });

    if (countEl) countEl.textContent = cryptoPositions.length;

    if (cryptoPositions.length === 0) {
        container.innerHTML = '<p class="empty-state">No open crypto positions</p>';
        return;
    }

    container.innerHTML = cryptoPositions.map(p => `
        <div class="crypto-position-card">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <span class="crypto-position-ticker">${escapeHtml(p.ticker || '--')}</span>
                <span class="crypto-position-direction ${p.direction || ''}" style="font-size:11px;font-weight:700">${escapeHtml(p.direction || '--')}</span>
            </div>
            <div class="crypto-position-meta">
                Entry: $${p.entry_price ? parseFloat(p.entry_price).toLocaleString() : '--'}
                &middot; Qty: ${p.quantity || '--'}
                ${p.stop_loss ? `&middot; Stop: $${parseFloat(p.stop_loss).toLocaleString()}` : ''}
                ${p.strategy ? `&middot; ${escapeHtml(p.strategy)}` : ''}
            </div>
        </div>
    `).join('');
}

async function loadCryptoKeyLevels() {
    const updatedEl = document.getElementById('cryptoKeyLevelsUpdated');
    // Note: was previously guarded by a 'cryptoKeyLevelsGrid' ID that no longer exists.
    // updateCryptoLevelValue() uses querySelectorAll('[data-level=...]') which targets
    // the strip elements directly, so no container reference needed here.

    try {
        const symbol = 'BTCUSDT';
        const daily = await fetchBinanceKlines(symbol, '1d', { limit: 3 });
        const weekly = await fetchBinanceKlines(symbol, '1w', { limit: 2 });
        const monthly = await fetchBinanceKlines(symbol, '1M', { limit: 2 });

        const today = daily?.[daily.length - 1];
        const yesterday = daily?.[daily.length - 2];

        const todayOpen = today ? parseFloat(today[1]) : null;
        const yesterdayClose = yesterday ? parseFloat(yesterday[4]) : null;

        const overnight = await fetchOvernightRange(symbol);
        const weeklyOpen = weekly?.[weekly.length - 1] ? parseFloat(weekly[weekly.length - 1][1]) : null;
        const monthlyOpen = monthly?.[monthly.length - 1] ? parseFloat(monthly[monthly.length - 1][1]) : null;

        updateCryptoLevelValue('todayOpen', todayOpen);
        updateCryptoLevelValue('yesterdayClose', yesterdayClose);
        updateCryptoLevelValue('overnightHigh', overnight?.high);
        updateCryptoLevelValue('overnightLow', overnight?.low);
        updateCryptoLevelValue('weeklyOpen', weeklyOpen);
        updateCryptoLevelValue('monthlyOpen', monthlyOpen);

        if (updatedEl) {
            updatedEl.textContent = `Updated ${new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`;
        }
    } catch (error) {
        console.error('Error loading crypto key levels:', error);
        if (updatedEl) {
            updatedEl.textContent = 'Update failed';
        }
    }
}

async function loadCryptoMarketData() {
    const spotEl = document.getElementById('cryptoCoinbaseSpotInline');
    if (!spotEl) return;

    let data = null;
    try {
        const response = await fetch(`${API_URL}/crypto/market`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        data = await response.json();
    } catch (error) {
        console.error('Error loading crypto market data:', error);
        // Keep the last good snapshot visible on transient API failures.
        if (cryptoMarketData) {
            renderCryptoMarketData();
        } else {
            renderCryptoMarketError();
        }
        return;
    }

    cryptoMarketData = data;

    try {
        renderCryptoMarketData();
    } catch (error) {
        // Keep last good values on screen if a render-only issue occurs.
        console.error('Error rendering crypto market data:', error);
    }
}

function renderCryptoMarketError() {
    const ids = [
        'cryptoCoinbaseSpotInline', 'cryptoBinanceSpotInline', 'cryptoBinancePerpInline',
        'cryptoPerpSourceInline', 'cryptoFundingInline', 'cryptoCvdInline', 'cryptoTakerBuy', 'cryptoTakerSell', 'cryptoCvdTrend'
    ];
    ids.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.textContent = '--';
            el.classList.remove('bullish', 'bearish');
        }
    });
}

function renderCryptoMarketData() {
    if (!cryptoMarketData) return;
    const prices = cryptoMarketData.prices || {};
    const funding = cryptoMarketData.funding || {};
    const cvd = cryptoMarketData.cvd || {};

    const rememberNumber = (key, value) => {
        const num = Number(value);
        if (value !== null && value !== undefined && !Number.isNaN(num)) {
            cryptoMarketLastGood[key] = num;
            return num;
        }
        return cryptoMarketLastGood[key] ?? null;
    };

    const rememberString = (key, value) => {
        if (value !== null && value !== undefined && `${value}`.trim() !== '') {
            cryptoMarketLastGood[key] = value;
            return value;
        }
        return cryptoMarketLastGood[key] ?? null;
    };

    const perps = prices.perps || {};
    const spotRaw = prices.coinbase_spot ?? prices.coinbase ?? prices.spot_coinbase ?? null;
    const binanceSpotRaw = prices.binance_spot ?? prices.binance ?? prices.spot_binance ?? prices.spot ?? null;
    const perpRaw = perps.binance ?? perps.bybit ?? perps.okx ?? perps.binance_perp ?? perps.perp ?? prices.perp_price ?? prices.perp ?? null;

    rememberNumber('coinbase_spot', spotRaw ?? binanceSpotRaw);
    rememberNumber('binance_spot', binanceSpotRaw);
    rememberNumber('perp_price', perpRaw);
    rememberString('binance_spot_ts', prices.binance_spot_ts);
    rememberString('perp_source', perps.source);

    const fundingInlineEl = document.getElementById('cryptoFundingInline');
    const cvdInlineEl = document.getElementById('cryptoCvdInline');

    if (fundingInlineEl) {
        const primaryFunding = rememberNumber(
            'funding_primary',
            funding.primary?.rate ?? funding.binance?.rate ?? funding.okx?.rate ?? funding.bybit?.rate ?? funding.okx_rate
        );
        const fundingSource = rememberString('funding_source', funding.primary?.source);
        const fundingSourceLabel = fundingSource ? `${String(fundingSource).toUpperCase()}` : '';
        const fundingLabel = fundingSourceLabel ? `Funding (${fundingSourceLabel})` : 'Funding';
        fundingInlineEl.textContent = formatFundingRate(primaryFunding, fundingLabel);
        // Color by numeric sign for immediate readability.
        fundingInlineEl.className = `crypto-price-extra ${primaryFunding > 0 ? 'bullish' : primaryFunding < 0 ? 'bearish' : ''}`.trim();
    }

    if (cvdInlineEl) {
        const netUsd = rememberNumber('cvd_net_usd', cvd.net_usd ?? cvd.net ?? cvd.value_usd);
        const cvdDir = rememberString('cvd_direction', cvd.direction ?? cvd.smoothed_direction ?? 'NEUTRAL');
        const cvdConfidence = rememberString('cvd_confidence', cvd.direction_confidence ?? '');
        if (netUsd !== null) {
            const confidenceBadge = (cvdDir && cvdDir !== 'NEUTRAL' && cvdConfidence) ? ` ${cvdConfidence.charAt(0)}` : '';
            const directionLabel = cvdDir && cvdDir !== 'NEUTRAL' ? `${cvdDir}${confidenceBadge}` : 'NEUTRAL';
            const compactValue = formatCompactSignedUsd(netUsd);
            cvdInlineEl.innerHTML = `<span class="crypto-cvd-direction">CVD ${directionLabel}</span> <span class="crypto-cvd-net">(${compactValue})</span>`;
        } else {
            cvdInlineEl.textContent = 'CVD --';
        }
        cvdInlineEl.className = `crypto-price-extra ${cvdDir?.includes('BULL') ? 'bullish' : cvdDir?.includes('BEAR') ? 'bearish' : ''}`.trim();
    }

    renderOrderflow(cvd, cryptoMarketData.order_flow || []);
    updateCryptoPriceStrip();
}

function updateCryptoPriceStrip() {
    const coinbaseEl = document.getElementById('cryptoCoinbaseSpotInline');
    const binanceSpotEl = document.getElementById('cryptoBinanceSpotInline');
    const binancePerpEl = document.getElementById('cryptoBinancePerpInline');
    const perpSourceEl = document.getElementById('cryptoPerpSourceInline');

    if (!coinbaseEl && !binanceSpotEl && !binancePerpEl) return;

    const prices = cryptoMarketData?.prices || {};
    const perps = prices.perps || {};
    const coinbaseSpot = cryptoMarketLastGood.coinbase_spot ?? prices.coinbase_spot ?? null;
    const binanceSpot = cryptoMarketLastGood.binance_spot ?? prices.binance_spot ?? null;
    const perpPrice = cryptoMarketLastGood.perp_price ?? perps.binance ?? perps.bybit ?? perps.okx ?? prices.perp_price ?? null;
    const perpSource = (cryptoMarketLastGood.perp_source ?? perps.source ?? '').toString().toUpperCase();
    const perpSourceMap = {
        BINANCE: 'BINANCE PERPS',
        BYBIT: 'BYBIT PERPS',
        OKX: 'OKX PERPS',
    };

    if (coinbaseEl) coinbaseEl.textContent = coinbaseSpot !== null ? formatUsdValue(coinbaseSpot) : '--';
    if (binanceSpotEl) binanceSpotEl.textContent = binanceSpot !== null ? formatUsdValue(binanceSpot) : '--';
    if (binancePerpEl) binancePerpEl.textContent = perpPrice !== null ? formatUsdValue(perpPrice) : '--';
    if (perpSourceEl) perpSourceEl.textContent = perpSourceMap[perpSource] || (perpSource ? `${perpSource} PERPS` : '--');

    const compareSpot = coinbaseSpot ?? binanceSpot ?? perpPrice;
    const wma = cryptoWma9;
    const trendClass = (wma !== null && compareSpot !== null && !Number.isNaN(Number(wma)) && !Number.isNaN(Number(compareSpot)))
        ? (Number(compareSpot) >= Number(wma) ? 'bullish' : 'bearish')
        : null;

    [coinbaseEl, binanceSpotEl, binancePerpEl].forEach(el => {
        if (!el) return;
        el.classList.remove('bullish', 'bearish');
        if (trendClass) el.classList.add(trendClass);
    });
}

function renderOrderflow(cvd, tape) {
    const takerBuyEl = document.getElementById('cryptoTakerBuy');
    const takerSellEl = document.getElementById('cryptoTakerSell');
    const cvdTrendEl = document.getElementById('cryptoCvdTrend');
    const tapeEl = document.getElementById('cryptoOrderflowTape');
    const updatedEl = document.getElementById('cryptoOrderflowUpdated');
    const sparklineEl = document.getElementById('cryptoCvdSparkline');

    if (takerBuyEl) takerBuyEl.textContent = (cvd?.taker_buy_qty !== null && cvd?.taker_buy_qty !== undefined) ? `${Number(cvd.taker_buy_qty).toFixed(2)} BTC` : '--';
    if (takerSellEl) takerSellEl.textContent = (cvd?.taker_sell_qty !== null && cvd?.taker_sell_qty !== undefined) ? `${Number(cvd.taker_sell_qty).toFixed(2)} BTC` : '--';
    if (cvdTrendEl) {
        const dir = cvd?.direction || 'NEUTRAL';
        const confidence = (cvd?.direction_confidence || '').toUpperCase();
        cvdTrendEl.textContent = (confidence && dir !== 'NEUTRAL') ? `${dir} (${confidence})` : dir;
        cvdTrendEl.className = `metric-value ${dir.includes('BULL') ? 'bullish' : dir.includes('BEAR') ? 'bearish' : 'neutral'}`;
    }
    if (updatedEl) {
        const stamp = new Date().toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
        const source = (cvd?.source || '').toString().toUpperCase();
        updatedEl.textContent = source ? `${source} ${stamp}` : stamp;
    }

    if (sparklineEl) {
        sparklineEl.innerHTML = renderSparklineSvg(cvd?.cvd_series || []);
    }

    if (tapeEl) {
        if (!tape || tape.length === 0) {
            tapeEl.innerHTML = '<p class="empty-state">No tape yet</p>';
        } else {
            tapeEl.innerHTML = tape.map(row => {
                const sideClass = row.side === 'BUY' ? 'buy' : 'sell';
                const price = row.price ? row.price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '--';
                const qty = row.qty ? row.qty.toFixed(3) : '--';
                return `<div class="orderflow-tape-row ${sideClass}"><span>${row.side}</span><span>$${price}</span><span>${qty} BTC</span></div>`;
            }).join('');
        }
    }
}

function renderSparklineSvg(series) {
    if (!series || series.length < 2) {
        return '<svg viewBox="0 0 100 50"><path d="M0 25 L100 25" stroke="#314255" stroke-width="2" fill="none" /></svg>';
    }
    const min = Math.min(...series);
    const max = Math.max(...series);
    const range = max - min || 1;
    const points = series.map((v, i) => {
        const x = (i / (series.length - 1)) * 100;
        const y = 50 - ((v - min) / range) * 45 - 2;
        return `${x.toFixed(2)},${y.toFixed(2)}`;
    }).join(' ');
    return `<svg viewBox=\"0 0 100 50\" preserveAspectRatio=\"none\"><polyline points=\"${points}\" fill=\"none\" stroke=\"#00e5ff\" stroke-width=\"2\" /></svg>`;
}

function formatUsdValue(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    return `$${Number(value).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatSignedUsd(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    const num = Number(value);
    const sign = num >= 0 ? '+' : '';
    return `${sign}$${Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatCompactSignedUsd(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    const num = Number(value);
    const abs = Math.abs(num);
    const sign = num >= 0 ? '+' : '-';
    let compact = '';
    if (abs >= 1_000_000_000) {
        compact = `${(abs / 1_000_000_000).toFixed(2)}B`;
    } else if (abs >= 1_000_000) {
        compact = `${(abs / 1_000_000).toFixed(2)}M`;
    } else if (abs >= 1_000) {
        compact = `${(abs / 1_000).toFixed(1)}K`;
    } else {
        compact = abs.toFixed(0);
    }
    return `${sign}$${compact}`;
}

function formatSignedPercent(value) {
    if (value === null || value === undefined || Number.isNaN(value)) return '--';
    const num = Number(value);
    const sign = num >= 0 ? '+' : '';
    return `${sign}${num.toFixed(2)}%`;
}

function formatFundingRate(rate, label) {
    if (rate === null || rate === undefined || Number.isNaN(rate)) return `${label}: --`;
    const num = Number(rate);
    const pct = num * 100;
    const sign = pct >= 0 ? '+' : '';
    const side = num > 0 ? 'Longs pay' : num < 0 ? 'Shorts pay' : 'Flat';
    return `${label}: ${sign}${pct.toFixed(4)}% (${side})`;
}

function updateCryptoLevelValue(levelKey, value) {
    const formatted = (value !== null && value !== undefined && !Number.isNaN(value))
        ? `$${Number(value).toLocaleString('en-US', { maximumFractionDigits: 0 })}`
        : '--';
    // Update all matching elements (strip <b> tags + any other data-level targets)
    document.querySelectorAll(`[data-level="${levelKey}"]`).forEach(el => {
        const b = el.querySelector('b');
        if (b) {
            b.textContent = formatted;
        } else {
            el.textContent = formatted;
        }
    });
}

async function fetchBinanceKlines(symbol, interval, params = {}) {
    const url = new URL(`${API_URL}/crypto/binance/klines`);
    url.searchParams.set('symbol', symbol);
    url.searchParams.set('interval', interval);
    Object.entries(params).forEach(([key, value]) => {
        if (value !== undefined && value !== null) {
            url.searchParams.set(key, value);
        }
    });

    const response = await fetch(url.toString());
    if (!response.ok) {
        throw new Error(`Binance proxy error: ${response.status}`);
    }
    const result = await response.json();
    if (result.status !== 'success') {
        throw new Error(result.error || 'Binance proxy error');
    }
    return result.data;
}

function calculateWeightedMovingAverage(values) {
    if (!Array.isArray(values) || values.length === 0) return null;
    let weightedSum = 0;
    let weightTotal = 0;
    values.forEach((value, idx) => {
        const weight = idx + 1;
        weightedSum += Number(value) * weight;
        weightTotal += weight;
    });
    if (weightTotal === 0) return null;
    return weightedSum / weightTotal;
}

function extractSessionOpenPrices(klines) {
    if (!Array.isArray(klines)) return [];
    return klines
        .filter(row => {
            const openTime = row?.[0];
            if (!openTime) return false;
            const date = new Date(openTime);
            return date.getUTCHours() === 1; // 8:00pm EST = 01:00 UTC
        })
        .map(row => Number(row?.[1]))
        .filter(value => !Number.isNaN(value));
}

async function refreshCryptoWma9() {
    if (cryptoWmaLoading) return;
    cryptoWmaLoading = true;
    try {
        const klines = await fetchBinanceKlines('BTCUSDT', '1h', { limit: 240 });
        const sessionOpens = extractSessionOpenPrices(klines);
        if (sessionOpens.length >= 9) {
            const lastNine = sessionOpens.slice(-9);
            const wma = calculateWeightedMovingAverage(lastNine);
            if (wma !== null && !Number.isNaN(wma)) {
                cryptoWma9 = wma;
                cryptoWmaUpdated = Date.now();
            }
        }
    } catch (error) {
        console.error('Error refreshing BTC 9-day WMA:', error);
    } finally {
        cryptoWmaLoading = false;
        updateCryptoPriceStrip();
    }
}

async function fetchOvernightRange(symbol) {
    const now = new Date();
    const start = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate(), 0, 0, 0);
    const end = start + 8 * 60 * 60 * 1000;

    const klines = await fetchBinanceKlines(symbol, '1h', {
        startTime: start,
        endTime: end
    });

    if (!Array.isArray(klines) || klines.length === 0) {
        return null;
    }

    const highs = klines.map(k => parseFloat(k[2]));
    const lows = klines.map(k => parseFloat(k[3]));

    return {
        high: Math.max(...highs),
        low: Math.min(...lows)
    };
}

function getScoreTier(score) {
    if (score >= 85) return 'EXCEPTIONAL';
    if (score >= 75) return 'STRONG';
    if (score >= 60) return 'MODERATE';
    if (score >= 45) return 'WEAK';
    return 'LOW';
}

function attachSignalActions() {
    // Clickable ticker to view on chart
    document.querySelectorAll('.ticker-link').forEach(ticker => {
        ticker.addEventListener('click', (e) => {
            e.stopPropagation();
            const card = e.target.closest('.signal-card');
            const signal = JSON.parse(decodeURIComponent(card.dataset.signal));
            showTradeOnChart(signal);
        });
    });
    
    // Dismiss and Select buttons
    document.querySelectorAll('.action-btn').forEach(btn => {
        btn.addEventListener('click', handleSignalAction);
    });
}

function attachReloadPreviousHandler() {
    const btn = document.querySelector('.reload-previous-btn');
    if (!btn) return;
    btn.addEventListener('click', loadMoreTradeIdeas);
}

async function loadMoreTradeIdeas() {
    const pagination = tradeIdeasPagination[activeAssetType];
    if (!pagination || pagination.loading || !pagination.hasMore) return;

    pagination.loading = true;
    refreshSignalViews();

    try {
        const assetClass = activeAssetType === 'equity' ? 'EQUITY' : 'CRYPTO';
        const response = await fetch(
            `${API_URL}/signals/active/paged?limit=${pagination.limit}&offset=${pagination.offset}&asset_class=${assetClass}`
        );
        const data = await response.json();

        if (data.status === 'success' && Array.isArray(data.signals)) {
            const existingIds = new Set(signals[activeAssetType].map(s => s.signal_id));
            const newSignals = data.signals.filter(s => !existingIds.has(s.signal_id));
            signals[activeAssetType] = signals[activeAssetType].concat(newSignals);
            pagination.offset = signals[activeAssetType].length;
            pagination.hasMore = data.has_more ?? (newSignals.length >= pagination.limit);
        } else {
            pagination.hasMore = false;
        }
    } catch (error) {
        console.error('Error loading previous trade ideas:', error);
    } finally {
        pagination.loading = false;
        refreshSignalViews();
    }
}

async function handleSignalAction(event) {
    event.stopPropagation();
    const button = event.target;
    const card = button.closest('.signal-card');
    const signalId = card.dataset.signalId;
    const action = button.dataset.action.toUpperCase();
    
    if (action === 'VIEW-CHART') return; // Handled separately
    
    if (action === 'SELECT') {
        // Open position entry modal instead of directly selecting
        const signal = JSON.parse(decodeURIComponent(card.dataset.signal));
        openPositionEntryModal(signal, card);
        return;
    }
    
    if (action === 'DISMISS') {
        // Open dismiss modal with reason selection
        const signal = JSON.parse(decodeURIComponent(card.dataset.signal));
        openDismissModal(signal, card);
        return;
    }
}

async function dismissSignalWithReason(signalId, reason, notes, card) {
    try {
        const response = await fetch(`${API_URL}/signals/${signalId}/dismiss`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                signal_id: signalId, 
                reason: reason,
                notes: notes
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'dismissed') {
            // Remove card with animation
            card.style.opacity = '0';
            card.style.transform = 'translateX(-20px)';
            setTimeout(() => {
                card.remove();
                // Auto-refill Trade Ideas list
                refillTradeIdeas();
            }, 300);
        }
    } catch (error) {
        console.error('Error dismissing signal:', error);
    }
}

function openDismissModal(signal, card) {
    const modal = document.createElement('div');
    modal.className = 'signal-modal-overlay active';
    modal.innerHTML = `
        <div class="signal-modal dismiss-modal">
            <div class="modal-header">
                <h3>Dismiss ${signal.ticker} Signal</h3>
                <button class="modal-close">&times;</button>
            </div>
            <div class="modal-body">
                <p>Why are you dismissing this signal?</p>
                <div class="dismiss-reasons">
                    <label class="dismiss-reason">
                        <input type="radio" name="dismissReason" value="NOT_ALIGNED">
                        <span>Not aligned with my thesis</span>
                    </label>
                    <label class="dismiss-reason">
                        <input type="radio" name="dismissReason" value="MISSED_ENTRY">
                        <span>Missed optimal entry</span>
                    </label>
                    <label class="dismiss-reason">
                        <input type="radio" name="dismissReason" value="TECHNICAL_CONCERN">
                        <span>Technical concerns</span>
                    </label>
                    <label class="dismiss-reason">
                        <input type="radio" name="dismissReason" value="OTHER" checked>
                        <span>Other / No reason</span>
                    </label>
                </div>
                <div class="modal-field">
                    <label>Notes (optional)</label>
                    <textarea id="dismissNotes" placeholder="Additional notes..."></textarea>
                </div>
            </div>
            <div class="modal-actions">
                <button class="modal-btn cancel">Cancel</button>
                <button class="modal-btn dismiss">Dismiss Signal</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Handle close
    modal.querySelector('.modal-close').addEventListener('click', () => modal.remove());
    modal.querySelector('.modal-btn.cancel').addEventListener('click', () => modal.remove());
    
    // Handle dismiss
    modal.querySelector('.modal-btn.dismiss').addEventListener('click', async () => {
        const reason = modal.querySelector('input[name="dismissReason"]:checked')?.value || 'OTHER';
        const notes = modal.querySelector('#dismissNotes').value;
        
        modal.remove();
        await dismissSignalWithReason(signal.signal_id, reason, notes, card);
    });
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
}

async function refillTradeIdeas() {
    // Fetch updated signal queue and re-render
    try {
        const response = await fetch(`${API_URL}/signals/active`);
        const data = await response.json();
        
        if (data.status === 'success' && data.signals) {
            // Update in-memory signals
            signals.equity = data.signals.filter(s => s.asset_class === 'EQUITY' || !s.asset_class);
            signals.crypto = data.signals.filter(s => s.asset_class === 'CRYPTO');
            resetTradeIdeasPagination();
            
            // Re-render
            refreshSignalViews();
            
            console.log(`Trade Ideas refilled: ${data.signals.length} signals`);
        }
    } catch (error) {
        console.error('Error refilling trade ideas:', error);
    }
}

// Signal Management
function addSignal(signalData) {
    if (signalData.asset_class === 'EQUITY') {
        signals.equity.unshift(signalData);
    } else {
        signals.crypto.unshift(signalData);
    }
    syncTradeIdeasOffset(signalData.asset_class === 'EQUITY' ? 'equity' : 'crypto');
    refreshSignalViews();
}

function removeSignal(signalId) {
    signals.equity = signals.equity.filter(s => s.signal_id !== signalId);
    signals.crypto = signals.crypto.filter(s => s.signal_id !== signalId);
    syncTradeIdeasOffset('equity');
    syncTradeIdeasOffset('crypto');
    refreshSignalViews();
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
                    <div class="signal-detail-value">${pos.stop_loss != null ? Number(pos.stop_loss).toFixed(2) : 'N/A'}</div>
                </div>
                <div class="signal-detail">
                    <div class="signal-detail-label">Target</div>
                    <div class="signal-detail-value">${pos.target_1 != null ? Number(pos.target_1).toFixed(2) : 'N/A'}</div>
                </div>
            </div>
        </div>
    `).join('');
}

function updatePosition(positionData) {
    loadOpenPositionsEnhanced();
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
            ${instruction ? `<div class="hunter-instruction">${instruction}</div>` : ''}
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
// WATCHLIST MANAGEMENT (v3)
// ==========================================

let watchlistRefreshInterval = null;
let watchlistLastData = null;
let watchlistTickerCache = [];
let watchlistCounts = {};
let selectedTickers = new Set();
let lastAnalyzedTicker = null;

const ZONE_COLORS = {
    MAX_LONG: { bg: '#0a2e1a', text: '#00e676' },
    LEVERAGED_LONG: { bg: '#0a2e2a', text: '#4caf50' },
    DE_LEVERAGING: { bg: '#2e2e0a', text: '#ffeb3b' },
    WATERFALL: { bg: '#2e1a0a', text: '#ff9800' },
    CAPITULATION: { bg: '#2e0a0a', text: '#e5370e' },
    RECOVERY: { bg: '#0a1a2e', text: '#42a5f5' },
    NEUTRAL: { bg: '#1a2228', text: '#78909c' }
};

function initWatchlist() {
    initWatchlistV3();
}

function initWatchlistV3() {
    const sectorSort = document.getElementById('watchlist-sector-sort');
    if (sectorSort) {
        sectorSort.addEventListener('change', () => {
            watchlistLastData = null;
            fetchEnrichedWatchlist();
        });
    }

    const refreshBtn = document.getElementById('watchlist-refresh');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', () => {
            watchlistLastData = null;
            fetchEnrichedWatchlist();
        });
    }

    const tickerSort = document.getElementById('ticker-sort');
    if (tickerSort) {
        tickerSort.addEventListener('change', () => fetchTickerList());
    }

    const tickerFilter = document.getElementById('ticker-filter');
    if (tickerFilter) {
        tickerFilter.addEventListener('change', () => renderTickerList());
    }

    const tickersRefresh = document.getElementById('tickers-refresh');
    if (tickersRefresh) {
        tickersRefresh.addEventListener('click', () => fetchTickerList(true));
    }

    setupBulkActions();
    fetchEnrichedWatchlist();
    fetchTickerList(true);
    startWatchlistRefresh();
}

async function fetchEnrichedWatchlist() {
    const grid = document.getElementById('watchlist-grid');
    if (!grid) return;

    const sortSelect = document.getElementById('watchlist-sector-sort');
    const sortBy = sortSelect ? sortSelect.value : 'strength_rank';

    try {
        const url = `${API_URL}/watchlist/enriched?sort_by=${encodeURIComponent(sortBy)}`;
        if (!watchlistLastData) {
            grid.innerHTML = '<div class="watchlist-loading">Loading watchlist data...</div>';
        }

        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (data.status === 'success') {
            watchlistLastData = data;
            renderSectorWatchlist(data);
            renderBenchmark(data.benchmark);
            updateEnrichedTimestamp(data.enriched_at);
        } else {
            throw new Error(data.message || 'Unknown error');
        }
    } catch (error) {
        console.error('Watchlist fetch failed:', error);
        grid.innerHTML = `
            <div class="watchlist-error">
                Failed to load watchlist data<br>
                <span style="font-size:11px;color:#78909c">${error.message}</span>
            </div>
        `;
    }
}

function renderBenchmark(benchmark) {
    const el = document.getElementById('watchlist-benchmark');
    if (!el) return;
    if (!benchmark) {
        el.innerHTML = '';
        return;
    }
    const price = benchmark.price !== null && benchmark.price !== undefined
        ? `$${Number(benchmark.price).toFixed(2)}`
        : '-';
    const chg = formatChange(benchmark.change_1d);
    const color = changeColor(benchmark.change_1d);
    el.innerHTML = `
        <span class="benchmark-label">${escapeHtml(benchmark.symbol || 'SPY')}</span>
        <span class="benchmark-price">${price}</span>
        <span style="color:${color}">${chg}</span>
    `;
}

function updateEnrichedTimestamp(ts) {
    const el = document.getElementById('watchlist-enriched-at');
    if (!el) return;
    const dt = ts ? new Date(ts) : new Date();
    el.textContent = `Updated: ${dt.toLocaleTimeString()}`;
}

function renderSectorWatchlist(data) {
    const grid = document.getElementById('watchlist-grid');
    if (!grid) return;

    const sectors = Array.isArray(data.sectors) ? data.sectors : [];
    if (!sectors.length) {
        grid.innerHTML = '<div class="watchlist-loading">No sectors available</div>';
        return;
    }

    grid.innerHTML = '';

    sectors.forEach(sector => {
        const card = document.createElement('div');
        card.className = 'sector-card';

        const vsSpy = sector.vs_spy_1w ?? sector.vs_spy_1d;
        const vsSpyLabel = formatChange(vsSpy);
        const vsSpyColor = changeColor(vsSpy);
        const etf = sector.etf || '-';
        const rank = sector.strength_rank !== undefined && sector.strength_rank !== null
            ? `#${sector.strength_rank}`
            : '#-';
        const bias = sector.bias_alignment || 'NEUTRAL';

        card.innerHTML = `
            <div class="sector-header">
                <div class="sector-title-row">
                    <span class="sector-name">${escapeHtml(sector.name || 'Uncategorized')}</span>
                    <span class="sector-etf">${escapeHtml(etf)}</span>
                    <span class="sector-vs-spy" style="color:${vsSpyColor}">${vsSpyLabel}</span>
                </div>
                <div class="sector-meta">
                    <span class="sector-bias">${escapeHtml(bias)}</span>
                    <span class="sector-rank">${escapeHtml(rank)}</span>
                </div>
            </div>
            <div class="ticker-header-row">
                <div>Symbol</div>
                <div class="col-price">Price</div>
                <div class="col-1d">1D</div>
                <div class="col-1w">1W</div>
                <div class="col-zone">CTA</div>
                <div class="col-signals">Sigs</div>
            </div>
        `;

        const tickers = sector.tickers || [];
        tickers.forEach(ticker => {
            const row = document.createElement('div');
            row.className = 'ticker-row';
            row.dataset.symbol = ticker.symbol;

            const price = ticker.price !== null && ticker.price !== undefined
                ? `$${Number(ticker.price).toFixed(2)}`
                : '-';
            const zone = ticker.cta_zone || 'NEUTRAL';
            const zoneStyle = ZONE_COLORS[zone] || ZONE_COLORS.NEUTRAL;
            const signals = ticker.active_signals || 0;

            row.innerHTML = `
                <div class="ticker-symbol">${escapeHtml(ticker.symbol)}</div>
                <div class="col-price">${price}</div>
                <div class="col-1d" style="color:${changeColor(ticker.change_1d)}">${formatChange(ticker.change_1d)}</div>
                <div class="col-1w" style="color:${changeColor(ticker.change_1w)}">${formatChange(ticker.change_1w)}</div>
                <div class="col-zone">
                    <span class="zone-badge" style="background:${zoneStyle.bg};color:${zoneStyle.text}">
                        ${escapeHtml(zone.replace(/_/g, ' '))}
                    </span>
                </div>
                <div class="col-signals ${signals > 0 ? 'signal-active' : 'signal-none'}">${signals || '-'}</div>
            `;

            row.addEventListener('click', () => openTickerChart(ticker.symbol));
            card.appendChild(row);
        });

        grid.appendChild(card);
    });
}

function startWatchlistRefresh() {
    stopWatchlistRefresh();
    watchlistRefreshInterval = setInterval(() => {
        fetchEnrichedWatchlist();
        fetchTickerList();
    }, 60000);
}

function stopWatchlistRefresh() {
    if (watchlistRefreshInterval) {
        clearInterval(watchlistRefreshInterval);
        watchlistRefreshInterval = null;
    }
}

async function fetchTickerList(force = false) {
    const list = document.getElementById('ticker-list');
    if (!list) return;

    const sortSelect = document.getElementById('ticker-sort');
    const sortBy = sortSelect ? sortSelect.value : 'sector';
    const sortDir = sortBy === 'sector' ? 'asc' : 'desc';

    if (force) {
        list.innerHTML = '<div class="watchlist-loading">Loading tickers...</div>';
    }

    try {
        const url = `${API_URL}/watchlist/tickers?sort_by=${encodeURIComponent(sortBy)}&sort_dir=${sortDir}&include_enrichment=true`;
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        if (data.status === 'success') {
            watchlistTickerCache = data.tickers || [];
            watchlistCounts = data.counts || {};
            renderTickerList();
            updateTickersTimestamp();
            updateTickerMeta();
        } else {
            throw new Error(data.message || 'Unknown error');
        }
    } catch (error) {
        console.error('Ticker list fetch failed:', error);
        const message = error && error.message ? error.message : 'Unknown error';
        list.innerHTML = `
            <div class="watchlist-error">
                Failed to load tickers<br>
                <span style="font-size:11px;color:#78909c">${message}</span>
            </div>
        `;
    }
}

function getFilteredTickers() {
    const filterSelect = document.getElementById('ticker-filter');
    const filterVal = filterSelect ? filterSelect.value : 'all';
    const all = watchlistTickerCache || [];

    if (filterVal === 'mine') {
        return all.filter(t => t.source === 'manual' || t.source === 'position');
    }
    if (filterVal === 'positions') {
        return all.filter(t => t.priority === 'high');
    }
    if (filterVal === 'scanner') {
        return all.filter(t => t.source === 'scanner');
    }
    if (filterVal === 'muted') {
        return all.filter(t => t.muted);
    }
    return all;
}

function updateTickerMeta() {
    const countEl = document.getElementById('ticker-count');
    const positionsEl = document.getElementById('ticker-positions');
    const filtered = getFilteredTickers();
    if (countEl) {
        countEl.textContent = `Showing: ${filtered.length} tickers`;
    }
    const positionsCount = watchlistCounts.position || filtered.filter(t => t.priority === 'high').length;
    if (positionsEl) {
        positionsEl.textContent = `Positions: ${positionsCount} active`;
    }
}

function updateTickersTimestamp() {
    const el = document.getElementById('tickers-updated-at');
    if (!el) return;
    const now = new Date();
    el.textContent = `Updated: ${now.toLocaleTimeString()}`;
}

function renderTickerList() {
    const list = document.getElementById('ticker-list');
    if (!list) return;
    list.innerHTML = '';

    const tickers = getFilteredTickers();
    updateTickerMeta();

    if (tickers.length === 0) {
        list.innerHTML = '<div class="watchlist-loading">No tickers found</div>';
        return;
    }

    const header = document.createElement('div');
    header.className = 'ticker-header-v3';
    header.innerHTML = `
        <span></span>
        <span>Symbol</span>
        <span>Sector</span>
        <span>Price</span>
        <span>1D</span>
        <span>RVOL</span>
        <span>CTA</span>
        <span>Sigs</span>
        <span></span>
    `;
    list.appendChild(header);

    tickers.forEach(t => {
        const row = document.createElement('div');
        row.className = `ticker-row-v3${t.muted ? ' muted' : ''}`;
        row.dataset.symbol = t.symbol;

        const dotClass = t.priority === 'high'
            ? 'dot-high'
            : (t.source === 'manual' || t.source === 'position') ? 'dot-manual' : 'dot-scanner';

        const zoneStyle = ZONE_COLORS[t.cta_zone] || ZONE_COLORS.NEUTRAL;
        const zoneLabel = t.cta_zone ? t.cta_zone.replace(/_/g, ' ').substring(0, 9) : '-';
        const signalDisplay = t.active_signals > 0 ? String(t.active_signals) : '-';
        const relVol = t.relative_volume !== null && t.relative_volume !== undefined
            ? `${t.relative_volume.toFixed(2)}x` : '-';
        const price = t.price !== null && t.price !== undefined ? `$${t.price.toFixed(2)}` : '-';

        row.innerHTML = `
            <div class="ticker-checkbox">
                <input type="checkbox" data-symbol="${escapeHtml(t.symbol)}" ${selectedTickers.has(t.symbol) ? 'checked' : ''}/>
            </div>
            <div class="ticker-symbol-v3">
                <span class="ticker-dot ${dotClass}"></span>${escapeHtml(t.symbol)}
            </div>
            <div class="ticker-sector-v3">${escapeHtml(t.sector || '-')}</div>
            <div class="ticker-price-v3">${price}</div>
            <div class="ticker-change-v3" style="color:${changeColor(t.change_1d)}">${formatChange(t.change_1d)}</div>
            <div class="ticker-rvol-v3">${relVol}</div>
            <div class="ticker-zone-v3">
                <span class="zone-badge" style="background:${zoneStyle.bg};color:${zoneStyle.text}">
                    ${zoneLabel}
                </span>
            </div>
            <div class="ticker-signals-v3">${signalDisplay}</div>
            <div class="ticker-actions-v3">...
                <div class="ticker-menu">
                    <button data-action="analyze">Open in Analyzer</button>
                    <button data-action="chart">View CTA Zones</button>
                    <button data-action="mute">${t.muted ? 'Unmute' : 'Mute'}</button>
                    <button data-action="remove">Remove</button>
                </div>
            </div>
        `;

        row.addEventListener('click', (e) => {
            if (e.target.closest('.ticker-actions-v3') || e.target.type === 'checkbox' || e.target.tagName === 'BUTTON') {
                return;
            }
            openTickerChart(t.symbol);
        });

        const checkbox = row.querySelector('input[type="checkbox"]');
        if (checkbox) {
            checkbox.addEventListener('change', (e) => {
                if (e.target.checked) {
                    selectedTickers.add(t.symbol);
                } else {
                    selectedTickers.delete(t.symbol);
                }
                updateBulkActions();
            });
        }

        const menuButton = row.querySelector('.ticker-actions-v3');
        if (menuButton) {
            menuButton.addEventListener('click', (e) => {
                e.stopPropagation();
                row.classList.toggle('menu-open');
            });
        }

        const menu = row.querySelector('.ticker-menu');
        if (menu) {
            menu.addEventListener('click', (e) => {
                e.stopPropagation();
                const action = e.target.getAttribute('data-action');
                if (!action) return;
                row.classList.remove('menu-open');
                if (action === 'analyze') analyzeTicker(t.symbol);
                if (action === 'chart') openTickerChart(t.symbol);
                if (action === 'mute') toggleMuteTicker(t.symbol, !t.muted);
                if (action === 'remove') deleteTicker(t.symbol);
            });
        }

        list.appendChild(row);
    });
}

function setupBulkActions() {
    const muteBtn = document.getElementById('bulk-mute');
    const unmuteBtn = document.getElementById('bulk-unmute');
    const removeBtn = document.getElementById('bulk-remove');
    const cancelBtn = document.getElementById('bulk-cancel');

    if (muteBtn) muteBtn.addEventListener('click', () => bulkMuteTickers(true));
    if (unmuteBtn) unmuteBtn.addEventListener('click', () => bulkMuteTickers(false));
    if (removeBtn) removeBtn.addEventListener('click', bulkRemoveTickers);
    if (cancelBtn) cancelBtn.addEventListener('click', () => {
        selectedTickers.clear();
        renderTickerList();
        updateBulkActions();
    });
}

function updateBulkActions() {
    const bulkBar = document.getElementById('bulk-actions');
    const countEl = document.getElementById('bulk-count');
    if (!bulkBar || !countEl) return;
    const count = selectedTickers.size;
    countEl.textContent = `${count} selected`;
    bulkBar.style.display = count > 0 ? 'flex' : 'none';
}

async function toggleMuteTicker(symbol, muted) {
    try {
        const response = await fetch(`${API_URL}/watchlist/tickers/${encodeURIComponent(symbol)}/mute`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ muted })
        });
        const data = await response.json();
        if (data.status === 'success') {
            fetchTickerList(true);
        } else {
            alert(data.message || 'Failed to update mute status');
        }
    } catch (error) {
        console.error('Mute toggle failed:', error);
    }
}

async function bulkMuteTickers(muted) {
    if (selectedTickers.size === 0) return;
    try {
        const response = await fetch(`${API_URL}/watchlist/tickers/bulk-mute`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbols: Array.from(selectedTickers), muted })
        });
        const data = await response.json();
        if (data.status === 'success') {
            selectedTickers.clear();
            fetchTickerList(true);
            updateBulkActions();
        } else {
            alert(data.message || 'Bulk update failed');
        }
    } catch (error) {
        console.error('Bulk mute failed:', error);
    }
}

async function bulkRemoveTickers() {
    if (selectedTickers.size === 0) return;
    if (!confirm('Remove selected tickers?')) return;
    const symbols = Array.from(selectedTickers);
    await Promise.all(symbols.map(symbol => deleteTicker(symbol, false)));
    selectedTickers.clear();
    fetchTickerList(true);
    updateBulkActions();
}

async function deleteTicker(symbol, confirmDelete = true) {
    if (confirmDelete && !confirm(`Remove ${symbol} from watchlist?`)) return;
    try {
        const response = await fetch(`${API_URL}/watchlist/tickers/${encodeURIComponent(symbol)}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        if (data.status === 'success') {
            fetchTickerList(true);
        } else {
            alert(data.message || 'Remove failed');
        }
    } catch (error) {
        console.error('Delete ticker failed:', error);
    }
}

// Helper functions for watchlist actions
function analyzeTicker(ticker) {
    const input = document.getElementById('analyzeTickerInput');
    const btn = document.getElementById('analyzeTickerBtn');
    if (input && ticker) input.value = ticker;
    if (btn) btn.click();
}

function openTickerChart(ticker) {
    if (typeof changeChartSymbol === 'function') {
        changeChartSymbol(ticker);
        return;
    }
    if (typeof tvWidget !== 'undefined' && tvWidget.setSymbol) {
        tvWidget.setSymbol(ticker, '1D');
        return;
    }
    window.open(`https://www.tradingview.com/chart/?symbol=${encodeURIComponent(ticker)}`, '_blank');
}

// ==========================================
// SINGLE TICKER ANALYZER (Unified)
// ==========================================

function initTickerAnalyzer() {
    const analyzeBtn = document.getElementById('analyzeTickerBtn');
    const analyzeInput = document.getElementById('analyzeTickerInput');
    const addBtn = document.getElementById('addToWatchlistBtn');

    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', runUnifiedAnalyzer);
    }

    if (analyzeInput) {
        analyzeInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                runUnifiedAnalyzer();
            }
        });
    }

    if (addBtn) {
        addBtn.addEventListener('click', addAnalyzedTickerToWatchlist);
    }
}

async function runUnifiedAnalyzer() {
    const input = document.getElementById('analyzeTickerInput');
    const intervalSelect = document.getElementById('analyzeInterval');
    const resultsContainer = document.getElementById('analyzerResultsV3');
    const addBtn = document.getElementById('addToWatchlistBtn');
    const ticker = input ? input.value.trim().toUpperCase() : '';
    const interval = intervalSelect ? intervalSelect.value : '1d';

    if (!ticker || !resultsContainer) return;
    lastAnalyzedTicker = ticker;
    if (addBtn) addBtn.disabled = true;

    resultsContainer.innerHTML = '<p class="empty-state">Analyzing...</p>';

    try {
        const response = await fetch(`${API_URL}/analyze/${encodeURIComponent(ticker)}?interval=${encodeURIComponent(interval)}`);
        const data = await response.json();
        if (data.status === 'success') {
            renderAnalyzerResultsV3(data.analysis || {});
            if (addBtn) addBtn.disabled = false;
            openTickerChart(ticker);
        } else {
            resultsContainer.innerHTML = `<p class="empty-state">${data.message || 'Analysis failed'}</p>`;
        }
    } catch (error) {
        console.error('Analyzer error:', error);
        resultsContainer.innerHTML = '<p class="empty-state">Analysis failed</p>';
    }
}

function renderAnalyzerResultsV3(analysis) {
    const container = document.getElementById('analyzerResultsV3');
    if (!container) return;

    const cta = analysis.cta || {};
    const trapped = analysis.trapped_traders || {};
    const tech = analysis.technicals || {};
    const fund = analysis.fundamentals || {};
    const combined = analysis.combined || {};

    const ctaAnalysis = cta.cta_analysis || {};
    const signals = cta.signals || [];

    const zone = ctaAnalysis.cta_zone || 'UNKNOWN';
    const zonePill = zone === 'UNKNOWN' ? 'neutral' : zone.includes('LONG') ? 'good' : zone.includes('CAPIT') || zone.includes('WATER') ? 'bad' : 'neutral';

    const signalsHtml = signals.length
        ? signals.map(s => `
            <div class="analysis-card">
                <div><strong>${escapeHtml(s.signal_type || 'SIGNAL')}</strong> (${escapeHtml(s.direction || '')})</div>
                <div>Entry: ${s.setup?.entry ?? '-'}</div>
                <div>Stop: ${s.setup?.stop ?? '-'}</div>
                <div>Target: ${s.setup?.target ?? '-'}</div>
            </div>
        `).join('')
        : '<div class="analysis-card">No active signals</div>';

    const trappedCriteria = trapped.ursa_bearish?.criteria || {};
    const taurusCriteria = trapped.taurus_bullish?.criteria || {};

    const buildCriteriaList = (criteria) => Object.values(criteria).map(c => `
        <div class="analysis-card">
            <div>${c.passed ? 'PASS' : 'FAIL'} ${escapeHtml(c.label || '')}</div>
            <div>Current: ${escapeHtml(c.current || 'N/A')} | Need: ${escapeHtml(c.required || 'N/A')}</div>
        </div>
    `).join('');

    container.innerHTML = `
        <div class="analysis-section">
            <h3>CTA Zone</h3>
            <div class="analysis-grid">
                <div>Zone: <span class="analysis-pill ${zonePill}">${escapeHtml(zone)}</span></div>
                <div>Price: ${ctaAnalysis.current_price ?? '-'}</div>
                <div>SMA20: ${ctaAnalysis.sma20 ?? '-'}</div>
                <div>SMA50: ${ctaAnalysis.sma50 ?? '-'}</div>
                <div>SMA120: ${ctaAnalysis.sma120 ?? '-'}</div>
                <div>ATR: ${ctaAnalysis.atr ?? '-'}</div>
            </div>
        </div>

        <div class="analysis-section">
            <h3>Active Signals</h3>
            <div class="analysis-grid">
                ${signalsHtml}
            </div>
        </div>

        <div class="analysis-section">
            <h3>Trapped Trader Check</h3>
            <div class="analysis-grid">
                <div class="analysis-card">
                    <strong>Verdict:</strong> ${escapeHtml(trapped.verdict || 'NO_SIGNAL')}
                </div>
                ${buildCriteriaList(trappedCriteria)}
                ${buildCriteriaList(taurusCriteria)}
            </div>
        </div>

        <div class="analysis-section">
            <h3>TradingView Technical</h3>
            <div class="analysis-grid">
                <div>Signal: <span class="analysis-pill neutral">${escapeHtml(tech.signal || 'N/A')}</span></div>
                <div>Score: ${tech.score ?? '-'}</div>
                <div>Price: ${tech.price ?? '-'}</div>
            </div>
        </div>

        <div class="analysis-section">
            <h3>Analyst Consensus</h3>
            <div class="analysis-grid">
                <div>Rating: ${escapeHtml(fund.analyst?.rating || 'N/A')}</div>
                <div>Target: ${fund.price_target?.target ?? '-'}</div>
                <div>Upside: ${fund.price_target?.upside_pct ?? '-'}%</div>
            </div>
        </div>

        <div class="analysis-section">
            <h3>Combined Recommendation</h3>
            <div class="analysis-grid">
                <div>Action: <span class="analysis-pill neutral">${escapeHtml(combined.action || 'MONITOR')}</span></div>
                <div>Source: ${escapeHtml(combined.source || 'Combined Analysis')}</div>
                <div>Note: ${escapeHtml(combined.note || '')}</div>
            </div>
        </div>
    `;
}

async function addAnalyzedTickerToWatchlist() {
    if (!lastAnalyzedTicker) return;
    try {
        const response = await fetch(`${API_URL}/watchlist/tickers/add`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ symbol: lastAnalyzedTicker, notes: 'Added from Analyzer' })
        });
        const data = await response.json();
        if (data.status === 'success' || data.status === 'already_exists') {
            fetchTickerList(true);
        } else {
            alert(data.message || 'Failed to add ticker');
        }
    } catch (error) {
        console.error('Add to watchlist failed:', error);
    }
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
    if (!confirm('KILL SWITCH: This will disable ALL strategies. Continue?')) {
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/strategies/disable-all`, {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            loadStrategies();
            console.log('ðŸ›‘ All strategies DISABLED');
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
        const zoneDisplay = zoneStatus.replace('_', ' ');
        const zoneWithKb = wrapWithKbLink(zoneStatus);
        
        return `
            <div class="cta-zone-card ${zoneStatus}" data-ticker="${ticker}">
                <span class="zone-ticker">${ticker}</span>
                <span class="zone-status ${zoneStatus}">${zoneWithKb}</span>
            </div>
        `;
    }).join('');
    
    // Attach KB handlers
    attachDynamicKbHandlers(container);
    
    // Attach click events to view on chart (but not on KB links)
    container.querySelectorAll('.cta-zone-card').forEach(card => {
        card.addEventListener('click', (e) => {
            // Don't change chart if clicking a KB link
            if (e.target.classList.contains('kb-term-dynamic')) return;
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
    
    // Attach KB handlers
    attachDynamicKbHandlers(container);
    
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
    const zoneWithKb = wrapWithKbLink(context.cta_zone || 'Unknown');
    
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
                    <div class="cta-metric-value">${formatRiskReward(setup.rr_ratio)}</div>
                </div>
            </div>
            <div class="cta-card-footer">
                Zone: ${zoneWithKb} | Vol: ${context.volume_ratio?.toFixed(1) || '-'}x
            </div>
        </div>
    `;
}


// ==========================================
// HYBRID MARKET SCANNER (Batch Scan Only)
// ==========================================

function initHybridScanner() {
    const scanBtn = document.getElementById('runHybridScanBtn');
    
    if (scanBtn) {
        scanBtn.addEventListener('click', runHybridScan);
    }
}

async function analyzeHybridTicker(ticker) {
    // Show loading state
    updateHybridGauges({
        technical: { signal: 'Loading...', loading: true },
        analyst: { signal: 'Loading...', loading: true },
        combined: { signal: 'Loading...', loading: true }
    });
    
    try {
        const response = await fetch(`${API_URL}/hybrid/combined/${ticker}`);
        const data = await response.json();
        
        if (data.status === 'success') {
            // API returns data at root level, not nested under 'data'
            renderHybridAnalysis(data);
        } else {
            updateHybridGauges({
                technical: { signal: 'Error', error: true },
                analyst: { signal: 'Error', error: true },
                combined: { signal: data.message || data.detail || 'Error', error: true }
            });
        }
    } catch (error) {
        console.error('Hybrid analysis error:', error);
        updateHybridGauges({
            technical: { signal: 'Error', error: true },
            analyst: { signal: 'Error', error: true },
            combined: { signal: 'Failed to fetch', error: true }
        });
    }
}

function renderHybridAnalysis(data) {
    // Use the actual API response structure
    const tech = data.technical_gauge || {};
    const analyst = data.analyst_gauge || {};
    const combined = data.combined || {};
    const meta = data.metadata || {};
    const price = data.price || {};
    
    // Technical Gauge
    const techSignal = document.getElementById('techSignal');
    const techScoreEl = document.getElementById('techScore');
    const techDetails = document.getElementById('techDetails');
    
    if (techSignal) {
        const signal = tech.signal || '--';
        techSignal.textContent = signal.replace('_', ' ');
        techSignal.className = 'gauge-signal ' + getSignalClass(signal);
    }
    
    if (techScoreEl) {
        const score = tech.score || {};
        const buyCount = score.buy || 0;
        const sellCount = score.sell || 0;
        techScoreEl.innerHTML = `<span class="buy-count">${buyCount} Buy</span> / <span class="sell-count">${sellCount} Sell</span>`;
    }
    
    if (techDetails) {
        const oscSignal = tech.oscillators_summary || '--';
        const maSignal = tech.ma_summary || '--';
        techDetails.innerHTML = `
            <div>Oscillators: <span>${oscSignal?.replace('_', ' ') || '--'}</span></div>
            <div>Moving Avgs: <span>${maSignal?.replace('_', ' ') || '--'}</span></div>
        `;
    }
    
    // Analyst Gauge
    const analystSignal = document.getElementById('analystSignal');
    const analystScoreEl = document.getElementById('analystScore');
    const analystDetails = document.getElementById('analystDetails');
    
    if (analystSignal) {
        const rec = analyst.consensus || '--';
        const displayRec = rec.toUpperCase().replace('_', ' ');
        analystSignal.textContent = displayRec;
        analystSignal.className = 'gauge-signal ' + getAnalystClass(rec);
    }
    
    if (analystScoreEl) {
        const numAnalysts = analyst.num_analysts || '?';
        analystScoreEl.innerHTML = `<span class="analyst-count">${numAnalysts} analysts</span>`;
    }
    
    if (analystDetails) {
        const targetPrice = analyst.price_target;
        const upsidePct = analyst.upside_pct;
        let upside = '--';
        let upsideClass = '';
        
        if (upsidePct !== undefined && upsidePct !== null) {
            upside = (upsidePct > 0 ? '+' : '') + upsidePct.toFixed(1) + '%';
            upsideClass = upsidePct > 0 ? 'upside-positive' : 'upside-negative';
        }
        
        analystDetails.innerHTML = `
            <div>Price Target: <span>$${targetPrice?.toFixed(2) || '--'}</span></div>
            <div>Upside: <span class="${upsideClass}">${upside}</span></div>
        `;
    }
    
    // Combined Gauge
    const combinedSignal = document.getElementById('combinedSignal');
    const combinedScoreEl = document.getElementById('combinedScore');
    const tickerMeta = document.getElementById('tickerMeta');
    
    if (combinedSignal) {
        const rec = combined.recommendation || 'NEUTRAL';
        combinedSignal.textContent = rec.replace('_', ' ');
        combinedSignal.className = 'gauge-signal ' + getSignalClass(rec);
    }
    
    if (combinedScoreEl) {
        const score = combined.score || '--';
        combinedScoreEl.textContent = `Score: ${score}/5`;
    }
    
    if (tickerMeta) {
        const name = meta.name || data.ticker || '--';
        const sector = meta.sector || '--';
        tickerMeta.innerHTML = `
            <div id="tickerName">${name}</div>
            <div id="tickerSector">${sector}</div>
        `;
    }
}

function updateHybridGauges(state) {
    // Technical
    const techSignal = document.getElementById('techSignal');
    if (techSignal) {
        techSignal.textContent = state.technical?.signal || '--';
        techSignal.className = state.technical?.error ? 'gauge-signal error' : 'gauge-signal';
    }
    
    // Analyst
    const analystSignal = document.getElementById('analystSignal');
    if (analystSignal) {
        analystSignal.textContent = state.analyst?.signal || '--';
        analystSignal.className = state.analyst?.error ? 'gauge-signal error' : 'gauge-signal';
    }
    
    // Combined
    const combinedSignal = document.getElementById('combinedSignal');
    if (combinedSignal) {
        combinedSignal.textContent = state.combined?.signal || '--';
        combinedSignal.className = state.combined?.error ? 'gauge-signal error' : 'gauge-signal';
    }
}

function getSignalClass(signal) {
    const s = (signal || '').toLowerCase();
    if (s.includes('strong buy')) return 'strong-buy';
    if (s.includes('buy')) return 'buy';
    if (s.includes('strong sell')) return 'strong-sell';
    if (s.includes('sell')) return 'sell';
    return 'neutral';
}

function getAnalystClass(rec) {
    const r = (rec || '').toLowerCase();
    if (r === 'strong_buy' || r === 'strongbuy') return 'strong-buy';
    if (r.includes('buy')) return 'buy';
    if (r === 'strong_sell' || r === 'strongsell') return 'strong-sell';
    if (r.includes('sell') || r.includes('under')) return 'sell';
    return 'neutral';
}

function calculateHybridScore(tech, fund) {
    let score = 3; // Neutral baseline
    
    const techSig = (tech.summary_signal || '').toLowerCase();
    const analystRec = (fund.recommendation_key || '').toLowerCase();
    
    // Technical contribution
    if (techSig.includes('strong buy')) score += 1;
    else if (techSig.includes('buy')) score += 0.5;
    else if (techSig.includes('strong sell')) score -= 1;
    else if (techSig.includes('sell')) score -= 0.5;
    
    // Analyst contribution
    if (analystRec === 'strong_buy' || analystRec === 'strongbuy') score += 1;
    else if (analystRec.includes('buy')) score += 0.5;
    else if (analystRec === 'strong_sell' || analystRec === 'strongsell') score -= 1;
    else if (analystRec.includes('sell') || analystRec.includes('under')) score -= 0.5;
    
    return Math.max(1, Math.min(5, Math.round(score)));
}

async function runHybridScan() {
    const btn = document.getElementById('runHybridScanBtn');
    const resultsDiv = document.getElementById('hybridResults');
    const tableBody = document.getElementById('hybridTableBody');
    
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Scanning...';
    }
    
    try {
        // Scan a mix of popular tickers
        const tickers = 'NVDA,AAPL,MSFT,GOOGL,META,AMZN,TSLA,AMD,NFLX,SPY';
        const response = await fetch(`${API_URL}/hybrid/scan?tickers=${tickers}&limit=10`);
        const data = await response.json();
        
        // API returns results directly or under data.results
        const results = data.results || data.data?.results;
        if (data.status === 'success' && results) {
            renderHybridTable(results);
            if (resultsDiv) resultsDiv.style.display = 'block';
        } else {
            if (tableBody) tableBody.innerHTML = '<tr><td colspan="6" style="text-align:center">No results</td></tr>';
        }
        
    } catch (error) {
        console.error('Hybrid scan error:', error);
        if (tableBody) tableBody.innerHTML = '<tr><td colspan="6" style="text-align:center">Scan failed</td></tr>';
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Scan Top 10';
        }
    }
}

function renderHybridTable(results) {
    const tableBody = document.getElementById('hybridTableBody');
    if (!tableBody) return;
    
    if (!results || results.length === 0) {
        tableBody.innerHTML = '<tr><td colspan="6" style="text-align:center">No results</td></tr>';
        return;
    }
    
    tableBody.innerHTML = results.map(item => {
        // Use the actual API response structure
        const tech = item.technical_gauge || item.technical || {};
        const analyst = item.analyst_gauge || item.fundamental || {};
        const meta = item.metadata || {};
        
        const techSignal = (tech.signal || '--').replace('_', ' ');
        const techClass = getSignalClass(tech.signal);
        
        const analystRec = (analyst.consensus || '--').toUpperCase().replace('_', ' ');
        const analystClass = getAnalystClass(analyst.consensus);
        
        // Calculate upside from API response
        let upside = '--';
        let upsideClass = '';
        if (analyst.upside_pct !== undefined && analyst.upside_pct !== null) {
            upside = (analyst.upside_pct > 0 ? '+' : '') + analyst.upside_pct.toFixed(1) + '%';
            upsideClass = analyst.upside_pct > 0 ? 'upside-positive' : 'upside-negative';
        }
        
        // Calculate strength (buy - sell) from score
        const score = tech.score || {};
        const strength = (score.buy || 0) - (score.sell || 0);
        const strengthStr = strength > 0 ? '+' + strength : String(strength);
        
        const sector = meta.sector || '--';
        
        return `
            <tr>
                <td><strong style="cursor:pointer" onclick="changeChartSymbol('${item.ticker}')">${item.ticker}</strong></td>
                <td class="signal-${techClass.replace(' ', '-')}">${techSignal}</td>
                <td>${strengthStr}</td>
                <td class="signal-${analystClass.replace(' ', '-')}">${analystRec}</td>
                <td class="${upsideClass}">${upside}</td>
                <td>${sector}</td>
            </tr>
        `;
    }).join('');
}

// Enhanced Analyzer with Context Cards
async function analyzeTickerEnhanced(ticker) {
    const contextContainer = document.getElementById('analyzerContext');
    if (!contextContainer) return;

    try {
        // Show context section
        contextContainer.style.display = 'grid';

        // Fetch all data in parallel
        const [ctaResponse, sectorResponse, biasResponse, flowResponse, signalsResponse, priceResponse] = await Promise.all([
            fetch(`${API_URL}/cta/analyze/${ticker}`),
            fetch(`${API_URL}/hybrid/combined/${ticker}`),
            fetch(`${API_URL}/bias-auto/status`),
            fetch(`${API_URL}/flow/ticker/${ticker}`),
            fetch(`${API_URL}/signals/ticker/${ticker}`),
            fetch(`${API_URL}/hybrid/price/${ticker}`)
        ]);

        const ctaData = await ctaResponse.json();
        const sectorData = await sectorResponse.json();
        const biasData = await biasResponse.json();
        const flowData = await flowResponse.json();
        const signalsData = await signalsResponse.json();
        const priceData = await priceResponse.json();

        // Populate CTA Zone Card
        const ctaAnalysis = ctaData.cta_analysis || {};
        const zoneStatus = document.getElementById('contextZoneStatus');
        const zoneSMAs = document.getElementById('contextZoneSMAs');

        if (zoneStatus) {
            const zoneLabel = ctaAnalysis.cta_zone || 'UNKNOWN';
            let zoneClass = 'zone-neutral';
            if (zoneLabel === 'MAX_LONG') zoneClass = 'zone-max-long';
            else if (zoneLabel === 'RISK_ON') zoneClass = 'zone-risk-on';
            else if (zoneLabel === 'NEUTRAL') zoneClass = 'zone-neutral';
            else if (zoneLabel === 'RISK_OFF') zoneClass = 'zone-risk-off';
            else if (zoneLabel === 'CAPITULATION') zoneClass = 'zone-capitulation';

            zoneStatus.innerHTML = `<span class="zone-label ${zoneClass}">${zoneLabel}</span>`;
        }

        if (zoneSMAs) {
            document.getElementById('sma20').textContent = ctaAnalysis.sma20 ? `$${ctaAnalysis.sma20.toFixed(2)}` : '--';
            document.getElementById('sma50').textContent = ctaAnalysis.sma50 ? `$${ctaAnalysis.sma50.toFixed(2)}` : '--';
            document.getElementById('sma120').textContent = ctaAnalysis.sma120 ? `$${ctaAnalysis.sma120.toFixed(2)}` : '--';
        }

        // Populate Sector Info Card
        const meta = sectorData.metadata || {};
        document.getElementById('sectorName').textContent = meta.sector || '--';
        document.getElementById('sectorETF').textContent = meta.sector_etf || '--';

        // Populate Bias Alignment Card
        const dailyBias = biasData?.data?.daily?.level || '';
        const dailyIsToro = dailyBias.includes('TORO');

        const longAlignment = document.getElementById('longAlignment');
        const shortAlignment = document.getElementById('shortAlignment');

        if (longAlignment) {
            longAlignment.textContent = dailyIsToro ? 'Aligned' : 'Divergent';
            longAlignment.className = 'alignment-status ' + (dailyIsToro ? 'aligned' : 'divergent');
        }

        if (shortAlignment) {
            shortAlignment.textContent = !dailyIsToro ? 'Aligned' : 'Divergent';
            shortAlignment.className = 'alignment-status ' + (!dailyIsToro ? 'aligned' : 'divergent');
        }

        // Populate Risk Levels Card
        const price = priceData.price || 0;
        const atr = ctaAnalysis.atr || 0;

        document.getElementById('atrValue').textContent = atr ? `$${atr.toFixed(2)}` : '--';
        document.getElementById('stopDistance').textContent = atr ? `$${(atr * 2).toFixed(2)}` : '--';
        document.getElementById('targetDistance').textContent = atr ? `$${(atr * 3).toFixed(2)}` : '--';

        // Populate Recent Flow Card
        const flowSummary = document.getElementById('contextFlowSummary');
        if (flowData.flow && flowData.flow.length > 0) {
            const recentFlow = flowData.flow.slice(0, 3);
            flowSummary.innerHTML = recentFlow.map(f => `
                <div class="flow-item">
                    <span class="flow-direction ${f.sentiment === 'BULLISH' ? 'bullish' : 'bearish'}">
                        ${f.sentiment === 'BULLISH' ? 'BULL' : 'BEAR'} ${f.type}
                    </span>
                    <span class="flow-score">${f.notability_score}/100</span>
                </div>
            `).join('');
        } else {
            flowSummary.innerHTML = '<p class="flow-empty">No recent flow data</p>';
        }

        // Populate Recent Signals Card
        const signalsSummary = document.getElementById('contextSignalsSummary');
        if (signalsData.signals && signalsData.signals.length > 0) {
            const recentSignals = signalsData.signals.slice(0, 3);
            signalsSummary.innerHTML = recentSignals.map(s => `
                <div class="signal-item">
                    <span class="signal-strategy">${s.strategy_name}</span>
                    <span class="signal-direction ${s.direction === 'LONG' ? 'long' : 'short'}">
                        ${s.direction}
                    </span>
                </div>
            `).join('');
        } else {
            signalsSummary.innerHTML = '<p class="signals-empty">No recent signals</p>';
        }

        // Wire up action buttons
        const createIdeaBtn = document.getElementById('createTradeIdeaBtn');
        const addWatchlistBtn = document.getElementById('addToWatchlistBtn');

        if (createIdeaBtn) {
            createIdeaBtn.onclick = () => {
                console.log('Create trade idea for', ticker);
                // This would open a modal or navigate to trade idea creation
            };
        }

        if (addWatchlistBtn) {
            addWatchlistBtn.onclick = () => {
                addTickerToWatchlist(ticker);
            };
        }

    } catch (error) {
        console.error('Error in enhanced analyzer:', error);
        contextContainer.style.display = 'none';
    }
}


// ==========================================
// BTC BOTTOM SIGNALS DASHBOARD (ALL 9 AUTOMATED)
// ==========================================

let btcSignals = {};
let btcConfluence = {};
let btcRawData = {};
let btcApiStatus = {};
let btcApiKeys = {};
let btcApiErrors = {};

function getBtcUiTargets() {
    return [
        {
            summary: document.getElementById('btcConfluenceSummary'),
            apiStatus: document.getElementById('btcApiStatus'),
            grid: document.getElementById('btcSignalsGrid')
        },
        {
            summary: document.getElementById('cryptoBtcConfluenceSummary'),
            apiStatus: document.getElementById('cryptoBtcApiStatus'),
            grid: document.getElementById('cryptoBtcSignalsGrid')
        }
    ];
}

function initBtcSignals() {
    const hasBtcPanels = document.getElementById('btcSignalsGrid') || document.getElementById('cryptoBtcSignalsGrid');
    const sessionPill = document.getElementById('cryptoSessionStatus');
    if (!hasBtcPanels) {
        if (sessionPill) {
            loadBtcSessions();
            setInterval(loadBtcSessions, 10 * 60 * 1000);
        }
        return;
    }
    const refreshButtons = document.querySelectorAll('.btc-refresh-btn');
    const resetButtons = document.querySelectorAll('.btc-reset-btn');

    refreshButtons.forEach(btn => {
        if (!btn.dataset.label) {
            btn.dataset.label = btn.textContent.trim();
        }
        btn.addEventListener('click', refreshBtcSignals);
    });

    resetButtons.forEach(btn => {
        btn.addEventListener('click', resetBtcSignals);
    });
    
    // Initial load
    loadBtcSignals();
    loadBtcSessions();

    // Auto-refresh: signals every 5 min, sessions every 10 min
    setInterval(loadBtcSignals, 5 * 60 * 1000);
    setInterval(loadBtcSessions, 10 * 60 * 1000);
}

async function loadBtcSessions() {
    await renderBtcSessions();
}

async function renderBtcSessions() {
    const listEl = document.getElementById('cryptoBtcSessionList');
    const currentEl = document.getElementById('cryptoBtcSessionCurrent');
    const sessionPill = document.getElementById('cryptoSessionStatus');
    if (!listEl && !currentEl && !sessionPill) return;

    try {
        const response = await fetch(`${API_URL}/btc/sessions`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();

        const sessions = data.sessions || {};
        const currentSession = data.current_session || null;
        const resolvedSession = resolveActiveSession(currentSession, sessions);

        // Update the session pill in the bias bar
        updateCryptoSessionStatus(resolvedSession, sessions);

        // Update the current-session indicator inside the crypto panel.
        // The active styling is on .btc-session-current.active â€” toggle that class on the element.
        if (currentEl) {
            if (resolvedSession && resolvedSession.active) {
                currentEl.classList.add('active');
                currentEl.innerHTML = `<span class="session-status">NOW: ${escapeHtml(resolvedSession.name)}</span>`;
            } else {
                currentEl.classList.remove('active');
                const nextSession = getNextSessionBySchedule(sessions);
                const nextName = nextSession ? nextSession.name : null;
                currentEl.innerHTML = `<span class="session-status">No active session${nextName ? ` &middot; Next: ${escapeHtml(nextName)}` : ''}</span>`;
            }
        }

        // Render session list rows
        if (listEl) {
            const sessionIds = Object.keys(sessions);
            if (sessionIds.length === 0) {
                listEl.innerHTML = '<p class="empty-state">No sessions configured</p>';
                return;
            }
            listEl.innerHTML = sessionIds.map(id => {
                const s = sessions[id];
                const isActive = resolvedSession && resolvedSession.name === s.name;
                const localTime = s.utc_time ? formatUtcRangeToDenver(s.utc_time) : '';
                return `
                    <div class="btc-session-item${isActive ? ' active' : ''}">
                        <div class="session-name${isActive ? ' active' : ''}">${escapeHtml(s.name)}</div>
                        <div class="session-time">${escapeHtml(s.ny_time)} ET${localTime ? ` &middot; ${escapeHtml(localTime)}` : ''}</div>
                        <div class="session-note">${escapeHtml(s.trading_note || '')}</div>
                    </div>
                `;
            }).join('');
        }
    } catch (err) {
        console.error('Error loading BTC sessions:', err);
        if (listEl) listEl.innerHTML = '<p class="empty-state">Could not load sessions</p>';
        if (sessionPill) {
            sessionPill.innerHTML = '<span class="session-pill neutral">Session data unavailable</span>';
        }
    }
}

async function loadBtcSignals() {
    try {
        const response = await fetch(`${API_URL}/btc/bottom-signals`);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        
        btcSignals = data.signals || {};
        btcConfluence = data.confluence || {};
        btcRawData = data.raw_data || {};
        btcApiStatus = data.api_status || {};
        btcApiKeys = data.api_keys || {};
        btcApiErrors = data.api_errors || {};
        
        renderBtcSignals();
        renderBtcSummary();
        renderBtcApiStatus();
        
    } catch (error) {
        console.error('Error loading BTC signals:', error);
        getBtcUiTargets().forEach(target => {
            if (target.grid) {
                target.grid.innerHTML = '<p class="empty-state">Failed to load signals</p>';
            }
        });
    }
}

async function refreshBtcSignals() {
    const refreshButtons = document.querySelectorAll('.btc-refresh-btn');
    refreshButtons.forEach(btn => {
        btn.disabled = true;
        btn.textContent = 'Refreshing...';
    });
    
    try {
        const response = await fetch(`${API_URL}/btc/bottom-signals/refresh`, {
            method: 'POST'
        });
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const data = await response.json();
        
        btcSignals = data.signals || {};
        btcConfluence = data.confluence || {};
        btcRawData = data.raw_data || {};
        btcApiStatus = data.api_status || {};
        btcApiKeys = data.api_keys || {};
        btcApiErrors = data.api_errors || {};
        
        renderBtcSignals();
        renderBtcSummary();
        renderBtcApiStatus();
        
    } catch (error) {
        console.error('Error refreshing BTC signals:', error);
    } finally {
        refreshButtons.forEach(btn => {
            btn.disabled = false;
            btn.textContent = btn.dataset.label || ' Refresh';
        });
    }
}

function renderBtcSummary() {
    const firingCount = btcConfluence.firing || 0;
    const totalSignals = btcConfluence.total || 9;
    const verdict = btcConfluence.verdict || 'Checking signals...';
    const verdictLevel = btcConfluence.verdict_level || 'none';
    const bullishConfluence = firingCount >= 5 || verdictLevel === 'strong' || verdictLevel === 'moderate';

    getBtcUiTargets().forEach(target => {
        if (!target.summary) return;
        target.summary.innerHTML = `
            <div class="confluence-meter">
                <span class="confluence-count">${firingCount}/${totalSignals}</span>
                <span class="confluence-label">Signals Firing</span>
            </div>
            <div class="confluence-verdict ${verdictLevel}">${verdict}</div>
        `;

        const panel = target.summary.closest('.btc-signals-section, .crypto-btc-signals-panel');
        if (panel) {
            panel.classList.toggle('confluence-bullish', bullishConfluence);
        }
    });
}

function renderBtcApiStatus() {
    const apis = [
        { key: 'coinalyze', name: 'Coinalyze', signals: 'Funding, OI, Liqs, Term' },
        { key: 'deribit', name: 'Deribit', signals: '25d Skew' },
        { key: 'defillama', name: 'DeFiLlama', signals: 'Stablecoin APR' },
        { key: 'binance', name: 'Binance', signals: 'Orderbook, Basis' },
        { key: 'yfinance', name: 'yfinance', signals: 'VIX' }
    ];

    getBtcUiTargets().forEach(target => {
        if (!target.apiStatus) return;
        target.apiStatus.innerHTML = apis.map(api => {
            const available = !!btcApiStatus[api.key];
            const keyMissing = api.key === 'coinalyze' && btcApiKeys.coinalyze === false;
            const status = keyMissing ? 'key-missing' : (available ? 'connected' : 'disconnected');
            return `
                <span class="api-status-item ${status}" title="${api.signals}">
                    ${api.name}: ${status === 'connected' ? 'OK' : status === 'key-missing' ? 'KEY' : 'OFF'}
                </span>
            `;
        }).join('');
    });
}

function renderBtcSignals() {
    const signalIds = Object.keys(btcSignals);

    getBtcUiTargets().forEach(target => {
        if (!target.grid) return;
        if (signalIds.length === 0) {
            target.grid.innerHTML = '<p class="empty-state">No signals configured</p>';
            return;
        }

        target.grid.innerHTML = signalIds.map(id => {
        const signal = btcSignals[id];
        const status = signal.status || 'UNKNOWN';
        const isAuto = signal.auto !== false;
        const hasManualOverride = signal.manual_override === true;
        
        // Format timestamp
        let timestamp = '';
        if (signal.updated_at) {
            const date = new Date(signal.updated_at);
            timestamp = date.toLocaleTimeString('en-US', { 
                hour: '2-digit', 
                minute: '2-digit',
                timeZone: 'America/New_York'
            }) + ' ET';
        }
        
        // KB link for signal name
        const nameWithKb = `<span class="kb-term-dynamic" data-kb-term="btc-bottom-signals">${signal.name}</span>`;
        
        // Source indicator (ASCII only to avoid encoding artifacts)
        const sourceLabel = isAuto ? 'AUTO' : 'MANUAL';
        
        // Value display - use raw value if available and detailed
        const rawData = btcRawData[id] || {};
        const apiError = rawData.error || btcApiErrors[id];
        let displayValue = signal.value;
        if (displayValue === null || displayValue === undefined) {
            displayValue = '--';
        }
        
        return `
            <div class="btc-signal-card ${status} ${isAuto ? 'auto' : 'manual'}" data-signal-id="${id}">
                <div class="btc-signal-header">
                    <span class="btc-signal-name">${nameWithKb}</span>
                    <span class="btc-signal-status ${status}">${status}</span>
                </div>
                <div class="btc-signal-value-display">
                    <span class="signal-value-main">${displayValue}</span>
                </div>
                <div class="btc-signal-description">${signal.description}</div>
                ${apiError ? `<div class=\"btc-signal-error\">${escapeHtml(apiError)}</div>` : ''}
                <div class="btc-signal-footer">
                    <span class="btc-signal-source ${isAuto ? 'auto' : 'manual'}">${sourceLabel}</span>
                    <span class="btc-signal-timestamp">${timestamp}</span>
                </div>
                ${hasManualOverride ? '<div class="manual-override-badge">Override Active</div>' : ''}
            </div>
        `;
    }).join('');
    
        // Attach KB handlers
        attachDynamicKbHandlers(target.grid);
        
        // Attach click events for manual override toggle
        target.grid.querySelectorAll('.btc-signal-card').forEach(card => {
            card.addEventListener('click', (e) => {
                // Don't toggle if clicking a KB link
                if (e.target.classList.contains('kb-term-dynamic')) return;
                toggleBtcSignal(card.dataset.signalId);
            });
        });
    });
}

async function toggleBtcSignal(signalId) {
    const signal = btcSignals[signalId];
    if (!signal) return;
    
    const isAuto = signal.auto !== false;
    const hasManualOverride = signal.manual_override === true;
    
    // If currently has manual override, clear it
    if (hasManualOverride) {
        if (confirm('Clear manual override and return to auto-fetch?')) {
            try {
                await fetch(`${API_URL}/btc/bottom-signals/${signalId}/clear-override`, {
                    method: 'POST'
                });
                loadBtcSignals();
            } catch (error) {
                console.error('Error clearing override:', error);
            }
        }
        return;
    }
    
    // Otherwise, set a manual override
    const currentStatus = signal.status || 'UNKNOWN';
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
            loadBtcSignals();
        }
    } catch (error) {
        console.error('Error toggling BTC signal:', error);
    }
}

async function resetBtcSignals() {
    if (!confirm('Reset all signals to UNKNOWN and clear all manual overrides?')) return;
    
    try {
        await fetch(`${API_URL}/btc/bottom-signals/reset`, { method: 'POST' });
        // After reset, refresh to get fresh data from APIs
        await refreshBtcSignals();
    } catch (error) {
        console.error('Error resetting BTC signals:', error);
    }
}

// MOVED TO CRYPTO-SCALPER: BTC session functions relocated to dedicated crypto-scalper application
function getEasternTimeParts() {
    try {
        const formatter = new Intl.DateTimeFormat('en-US', {
            timeZone: 'America/New_York',
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            weekday: 'short'
        });
        const parts = formatter.formatToParts(new Date());
        const partMap = {};
        parts.forEach(part => {
            partMap[part.type] = part.value;
        });
        return {
            hour: Number(partMap.hour),
            minute: Number(partMap.minute),
            weekday: partMap.weekday
        };
    } catch (e) {
        console.warn('Unable to resolve Eastern time:', e);
        return null;
    }
}

function resolveActiveSession(currentSession, sessions) {
    if (currentSession && currentSession.active) return currentSession;
    return findActiveSessionClient(sessions) || currentSession;
}

function findActiveSessionClient(sessions) {
    if (!sessions) return null;
    const time = getEasternTimeParts();
    if (!time) return null;
    const { hour, minute, weekday } = time;

    if (hour >= 20 && hour < 21) {
        return { ...(sessions.asia_handoff || { name: 'Asia Handoff + Funding Reset' }), active: true };
    }
    if (hour >= 4 && hour < 6) {
        return { ...(sessions.london_open || { name: 'London Cash FX Open' }), active: true };
    }
    if (hour >= 11 && hour < 13) {
        return { ...(sessions.peak_volume || { name: 'Peak Global Volume' }), active: true };
    }
    if (hour >= 15 && hour < 16) {
        return { ...(sessions.etf_fixing || { name: 'ETF Fixing Window' }), active: true };
    }
    if (weekday === 'Fri' && hour === 15 && minute >= 55) {
        return { ...(sessions.friday_close || { name: 'Friday CME Close' }), active: true };
    }
    return null;
}

function parseNyStartTime(nyTime) {
    if (!nyTime) return null;
    let cleaned = nyTime.toLowerCase().trim();
    cleaned = cleaned.replace(/^\w{3}\s+/, ''); // remove "Fri " prefix
    const start = cleaned.split('-')[0]?.trim();
    if (!start) return null;
    const match = start.match(/(\d{1,2})(?::(\d{2}))?\s*(am|pm)/i);
    if (!match) return null;
    let hour = parseInt(match[1], 10);
    const minute = match[2] ? parseInt(match[2], 10) : 0;
    const meridian = match[3].toLowerCase();
    if (meridian === 'pm' && hour !== 12) hour += 12;
    if (meridian === 'am' && hour === 12) hour = 0;
    return hour * 60 + minute;
}

function getNextSessionBySchedule(sessions) {
    if (!sessions) return null;
    const time = getEasternTimeParts();
    if (!time) return null;
    const nowMinutes = (time.hour * 60) + time.minute;
    const isFriday = time.weekday === 'Fri';

    const sessionList = Object.values(sessions)
        .map(session => {
            const startMinutes = parseNyStartTime(session.ny_time);
            if (startMinutes === null) return null;
            const isFridayOnly = (session.ny_time || '').toLowerCase().startsWith('fri');
            if (isFridayOnly && !isFriday) return null;
            return { ...session, startMinutes };
        })
        .filter(Boolean)
        .sort((a, b) => a.startMinutes - b.startMinutes);

    if (sessionList.length === 0) return null;
    const upcoming = sessionList.find(session => session.startMinutes > nowMinutes);
    return upcoming || sessionList[0];
}

function updateCryptoSessionStatus(currentSession, sessions) {
    const statusEl = document.getElementById('cryptoSessionStatus');
    if (!statusEl) return;

    if (currentSession && currentSession.active) {
        const utcTime = currentSession.utc_time || '';
        const localTime = utcTime ? formatUtcRangeToDenver(utcTime) : '';
        statusEl.innerHTML = `
            <span class="session-pill">NOW: ${currentSession.name}${localTime ? `  ${localTime}` : ''}</span>
        `;
    } else {
        const nextSession = getNextSessionBySchedule(sessions);
        statusEl.innerHTML = `
            <span class="session-pill">No active BTC session${nextSession ? `  Next: ${nextSession.name}` : ''}</span>
        `;
    }
}

function formatUtcRangeToDenver(utcRange) {
    if (!utcRange) return '--';
    let range = utcRange.trim();
    let dayPrefix = null;
    const dayMatch = range.match(/^(Sun|Mon|Tue|Wed|Thu|Fri|Sat)\s+/);
    if (dayMatch) {
        dayPrefix = dayMatch[1];
        range = range.slice(dayMatch[0].length);
    }

    const [startStr, endStr] = range.split('-');
    if (!startStr || !endStr) return utcRange;

    const parseTime = (timeStr) => {
        const match = timeStr.trim().match(/^([01]?\d|2[0-3]):([0-5]\d)$/);
        if (!match) {
            return null;
        }
        return { hours: Number(match[1]), minutes: Number(match[2]) };
    };

    const getBaseDate = () => {
        const now = new Date();
        const base = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
        if (!dayPrefix) return base;
        const dayMap = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
        const targetDay = dayMap[dayPrefix];
        const offset = (targetDay - base.getUTCDay() + 7) % 7;
        base.setUTCDate(base.getUTCDate() + offset);
        return base;
    };

    const baseDate = getBaseDate();
    const startTime = parseTime(startStr);
    const endTime = parseTime(endStr);
    if (!startTime || !endTime) return utcRange;

    const startDate = new Date(Date.UTC(
        baseDate.getUTCFullYear(),
        baseDate.getUTCMonth(),
        baseDate.getUTCDate(),
        startTime.hours,
        startTime.minutes
    ));
    const endDate = new Date(Date.UTC(
        baseDate.getUTCFullYear(),
        baseDate.getUTCMonth(),
        baseDate.getUTCDate(),
        endTime.hours,
        endTime.minutes
    ));
    if (endDate <= startDate) {
        endDate.setUTCDate(endDate.getUTCDate() + 1);
    }

    const formatter = new Intl.DateTimeFormat('en-US', {
        timeZone: 'America/Denver',
        hour: 'numeric',
        minute: '2-digit'
    });

    return `${formatter.format(startDate)}-${formatter.format(endDate)} MT`;
}


// ==========================================
// OPTIONS FLOW (Unusual Whales)
// ==========================================

let flowHotTickers = [];
let flowRecentAlerts = [];

function initOptionsFlow() {
    const refreshBtn = document.getElementById('refreshFlowBtn');
    
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadFlowData);
    }
    
    // Check connection status and load data
    checkFlowStatus();
    loadFlowData();
}

async function checkFlowStatus() {
    const statusEl = document.getElementById('flowStatus');
    if (!statusEl) return;
    
    try {
        const response = await fetch(`${API_URL}/flow/status`);
        const data = await response.json();
        
        if (data.configured && data.source === 'discord_bot') {
            statusEl.textContent = `Live (${data.active_tickers} tickers)`;
            statusEl.classList.add('connected');
        } else if (data.configured) {
            statusEl.textContent = 'Connected';
            statusEl.classList.add('connected');
        } else {
            statusEl.textContent = 'Manual Mode';
            statusEl.classList.remove('connected');
        }
    } catch (error) {
        statusEl.textContent = 'Offline';
        statusEl.classList.remove('connected');
    }
}

async function loadFlowData() {
    await Promise.all([
        loadHotTickers(),
        loadRecentAlerts()
    ]);
}

async function loadHotTickers() {
    try {
        const response = await fetch(`${API_URL}/flow/hot`);
        const data = await response.json();
        
        flowHotTickers = data.tickers || [];
        renderHotTickers();
    } catch (error) {
        console.error('Error loading hot tickers:', error);
    }
}

function renderHotTickers() {
    const container = document.getElementById('flowHotList');
    if (!container) return;
    
    if (flowHotTickers.length === 0) {
        container.innerHTML = '<p class="empty-state">No flow data yet - add manually or connect Unusual Whales</p>';
        return;
    }
    
    container.innerHTML = flowHotTickers.map(ticker => {
        const premium = ticker.total_premium || 0;
        const premiumStr = premium >= 1000000 
            ? `$${(premium / 1000000).toFixed(1)}M` 
            : `$${(premium / 1000).toFixed(0)}K`;
        const score = ticker.unusualness_score ? Math.round(ticker.unusualness_score) : null;
        const alertCount = ticker.alert_count || ticker.unusual_count || 0;
        const callPrem = ticker.call_premium || 0;
        const putPrem = ticker.put_premium || 0;
        const dte = ticker.avg_dte ? `${Math.round(ticker.avg_dte)}d` : '';
        
        return `
            <div class="flow-hot-card ${ticker.sentiment}" data-ticker="${ticker.ticker}">
                <div class="flow-hot-top">
                    <div class="flow-hot-ticker">${ticker.ticker}</div>
                    ${score ? `<div class="flow-hot-score">${score}</div>` : ''}
                </div>
                <div class="flow-hot-sentiment ${ticker.sentiment}">${ticker.sentiment}</div>
                <div class="flow-hot-premium">${premiumStr}</div>
                <div class="flow-hot-details">
                    ${alertCount ? `<span class="flow-hot-count">${alertCount} alert${alertCount > 1 ? 's' : ''}</span>` : ''}
                    ${dte ? `<span class="flow-hot-dte">${dte}</span>` : ''}
                </div>
                ${(callPrem || putPrem) ? `
                    <div class="flow-hot-breakdown">
                        <span class="flow-calls">C: $${(callPrem / 1000).toFixed(0)}K</span>
                        <span class="flow-puts">P: $${(putPrem / 1000).toFixed(0)}K</span>
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
    
    // Click to view on chart
    container.querySelectorAll('.flow-hot-card').forEach(card => {
        card.addEventListener('click', () => {
            changeChartSymbol(card.dataset.ticker);
        });
    });
}

async function loadRecentAlerts() {
    try {
        const response = await fetch(`${API_URL}/flow/recent?limit=10`);
        const data = await response.json();
        
        flowRecentAlerts = data.alerts || [];
        renderRecentAlerts();
    } catch (error) {
        console.error('Error loading recent alerts:', error);
    }
}

function renderRecentAlerts() {
    const container = document.getElementById('flowAlertsList');
    if (!container) return;
    
    if (flowRecentAlerts.length === 0) {
        container.innerHTML = '<p class="empty-state">No recent alerts</p>';
        return;
    }
    
    container.innerHTML = flowRecentAlerts.map(alert => {
        const time = new Date(alert.received_at || alert.timestamp).toLocaleTimeString();
        const premium = alert.premium ? (alert.premium >= 1000000 
            ? `$${(alert.premium / 1000000).toFixed(1)}M` 
            : `$${(alert.premium / 1000).toFixed(0)}K`) : '-';
        const score = alert.unusualness_score ? Math.round(alert.unusualness_score) : null;
        const strike = alert.strike ? `$${alert.strike}` : '';
        const expiry = alert.expiry || '';
        const optType = alert.option_type || '';
        const dte = alert.avg_dte ? `${Math.round(alert.avg_dte)}DTE` : '';
        const count = alert.unusual_count || 0;
        const source = alert.source === 'discord_bot' ? 'UW' : (alert.source === 'manual' ? 'Manual' : '');
        
        // Build detail chips
        let details = [];
        if (strike && optType) details.push(`${optType} ${strike}`);
        else if (strike) details.push(strike);
        if (expiry) details.push(expiry);
        if (dte) details.push(dte);
        if (count > 1) details.push(`${count}x`);
        
        return `
            <div class="flow-alert-item" data-ticker="${alert.ticker}">
                <div class="flow-alert-left">
                    <span class="flow-alert-ticker">${alert.ticker}</span>
                    <span class="flow-alert-type ${alert.type || ''}">${alert.type || 'FLOW'}</span>
                    <span class="flow-alert-sentiment ${alert.sentiment}">${alert.sentiment}</span>
                    ${score ? `<span class="flow-alert-score">${score}</span>` : ''}
                </div>
                <div class="flow-alert-center">
                    ${details.length > 0 ? details.map(d => `<span class="flow-alert-detail">${d}</span>`).join('') : ''}
                </div>
                <div class="flow-alert-right">
                    <div class="flow-alert-premium">${premium}</div>
                    <div class="flow-alert-meta">
                        <span class="flow-alert-time">${time}</span>
                        ${source ? `<span class="flow-alert-source">${source}</span>` : ''}
                    </div>
                </div>
            </div>
        `;
    }).join('');
    
    // Click alert to view ticker on chart
    container.querySelectorAll('.flow-alert-item').forEach(item => {
        item.addEventListener('click', () => {
            const ticker = item.dataset.ticker;
            if (ticker) changeChartSymbol(ticker);
        });
    });
}

// Flow Entry Modal State
let flowModalData = {
    ticker: '',
    sentiment: null,
    type: null,
    premium: null,
    expiry: null,
    voloi: null,
    repeat: null,
    notes: ''
};

function initFlowModal() {
    const openBtn = document.getElementById('openFlowModalBtn');
    const closeBtn = document.getElementById('closeFlowModalBtn');
    const cancelBtn = document.getElementById('cancelFlowBtn');
    const submitBtn = document.getElementById('submitFlowBtn');
    const overlay = document.getElementById('flowModalOverlay');
    
    if (openBtn) {
        openBtn.addEventListener('click', openFlowModal);
    }
    
    if (closeBtn) {
        closeBtn.addEventListener('click', closeFlowModal);
    }
    
    if (cancelBtn) {
        cancelBtn.addEventListener('click', closeFlowModal);
    }
    
    if (submitBtn) {
        submitBtn.addEventListener('click', submitFlowFromModal);
    }
    
    if (overlay) {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeFlowModal();
        });
    }
    
    // Ticker input
    const tickerInput = document.getElementById('modalFlowTicker');
    if (tickerInput) {
        tickerInput.addEventListener('input', (e) => {
            flowModalData.ticker = e.target.value.toUpperCase();
            calculateFlowScore();
        });
    }
    
    // Notes input
    const notesInput = document.getElementById('modalFlowNotes');
    if (notesInput) {
        notesInput.addEventListener('input', (e) => {
            flowModalData.notes = e.target.value;
        });
    }
    
    // Option buttons
    document.querySelectorAll('.flow-option-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const field = btn.dataset.field;
            const value = btn.dataset.value;
            
            // Remove selected from siblings
            btn.parentElement.querySelectorAll('.flow-option-btn').forEach(b => {
                b.classList.remove('selected');
            });
            
            // Select this one
            btn.classList.add('selected');
            
            // Update data
            flowModalData[field] = value;
            
            // Recalculate score
            calculateFlowScore();
        });
    });
}

function openFlowModal() {
    // Reset data
    flowModalData = {
        ticker: '',
        sentiment: null,
        type: null,
        premium: null,
        expiry: null,
        voloi: null,
        repeat: null,
        notes: ''
    };
    
    // Reset UI
    document.getElementById('modalFlowTicker').value = '';
    document.getElementById('modalFlowNotes').value = '';
    document.querySelectorAll('.flow-option-btn').forEach(btn => {
        btn.classList.remove('selected');
    });
    
    // Reset score display
    updateScoreDisplay(0, 'Fill in details below', '');
    updateVerdict('');
    document.getElementById('submitFlowBtn').disabled = true;
    
    // Show modal
    document.getElementById('flowModalOverlay').classList.add('active');
}

function closeFlowModal() {
    document.getElementById('flowModalOverlay').classList.remove('active');
}

function calculateFlowScore() {
    let score = 0;
    let factors = [];
    
    // Premium scoring (0-30 points)
    const premiumScores = {
        '25000': 5,
        '75000': 15,
        '150000': 25,
        '500000': 30
    };
    if (flowModalData.premium) {
        score += premiumScores[flowModalData.premium] || 0;
        if (flowModalData.premium === '500000') factors.push('Large premium');
        else if (flowModalData.premium === '150000') factors.push('Good size');
    }
    
    // Type scoring (0-25 points)
    const typeScores = {
        'SWEEP': 25,
        'BLOCK': 20,
        'UNUSUAL_VOLUME': 15,
        'DARK_POOL': 10
    };
    if (flowModalData.type) {
        score += typeScores[flowModalData.type] || 0;
        if (flowModalData.type === 'SWEEP') factors.push('Aggressive sweep');
    }
    
    // Expiry scoring (0-20 points) - sweet spot is 2-4 weeks
    const expiryScores = {
        '0dte': 5,      // Too short, could be gambling
        'week': 15,     // Good
        '2-4weeks': 20, // Optimal
        'monthly': 10,  // OK
        'leaps': 0      // Too far out
    };
    if (flowModalData.expiry) {
        score += expiryScores[flowModalData.expiry] || 0;
        if (flowModalData.expiry === '2-4weeks') factors.push('Optimal expiry');
        if (flowModalData.expiry === 'leaps') factors.push('LEAPS (less urgent)');
    }
    
    // Volume vs OI scoring (0-15 points)
    const voloiScores = {
        'low': 0,
        'normal': 5,
        'high': 12,
        'extreme': 15
    };
    if (flowModalData.voloi) {
        score += voloiScores[flowModalData.voloi] || 0;
        if (flowModalData.voloi === 'extreme') factors.push('Extreme volume');
    }
    
    // Repeat activity (0-10 points)
    if (flowModalData.repeat === 'yes') {
        score += 10;
        factors.push('Repeat hits');
    }
    
    // Determine label and class
    let label, scoreClass, verdictClass, verdict;
    
    if (score >= 80) {
        label = 'EXCEPTIONAL - Must track!';
        scoreClass = 'exceptional';
        verdictClass = 'must-add';
        verdict = 'This is significant institutional activity. Definitely add this!';
    } else if (score >= 60) {
        label = 'HIGH - Worth tracking';
        scoreClass = 'high';
        verdictClass = 'add';
        verdict = 'Notable flow that could move the stock. Add it!';
    } else if (score >= 40) {
        label = 'MEDIUM - Maybe track';
        scoreClass = 'medium';
        verdictClass = 'maybe';
        verdict = 'Decent activity but not exceptional. Add if it matches your thesis.';
    } else {
        label = 'LOW - Probably skip';
        scoreClass = 'low';
        verdictClass = 'skip';
        verdict = 'Likely noise. Skip unless you have other conviction.';
    }
    
    // Add factors to label
    if (factors.length > 0) {
        label += '\n' + factors.join(' | ');
    }
    
    updateScoreDisplay(score, label, scoreClass);
    updateVerdict(verdict, verdictClass);
    
    // Enable submit if we have required fields and decent score
    const hasRequired = flowModalData.ticker && flowModalData.sentiment && 
                       flowModalData.type && flowModalData.premium;
    document.getElementById('submitFlowBtn').disabled = !hasRequired;
}

function updateScoreDisplay(score, label, scoreClass) {
    const circle = document.getElementById('flowScoreCircle');
    const value = document.getElementById('flowScoreValue');
    const labelEl = document.getElementById('flowScoreLabel');
    
    value.textContent = score;
    labelEl.textContent = label;
    
    // Update classes
    circle.className = 'flow-score-circle ' + scoreClass;
    labelEl.className = 'flow-score-label ' + scoreClass;
}

function updateVerdict(text, verdictClass = '') {
    const verdict = document.getElementById('flowVerdict');
    verdict.textContent = text;
    verdict.className = 'flow-verdict ' + verdictClass;
}

async function submitFlowFromModal() {
    const ticker = flowModalData.ticker.trim().toUpperCase();
    
    if (!ticker || !flowModalData.sentiment || !flowModalData.type || !flowModalData.premium) {
        alert('Please fill in all required fields');
        return;
    }
    
    try {
        const response = await fetch(`${API_URL}/flow/manual`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ticker,
                sentiment: flowModalData.sentiment,
                flow_type: flowModalData.type,
                premium: parseInt(flowModalData.premium),
                notes: flowModalData.notes || `Expiry: ${flowModalData.expiry || 'N/A'}, Vol/OI: ${flowModalData.voloi || 'N/A'}, Repeat: ${flowModalData.repeat || 'N/A'}`
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
            closeFlowModal();
            loadFlowData();
            console.log(`ðŸ‹ Added flow: ${ticker} ${flowModalData.sentiment} (Score: calculated)`);
        }
    } catch (error) {
        console.error('Error adding flow:', error);
        alert('Failed to add flow. Please try again.');
    }
}

// Initialize modal on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initFlowModal, 1200);
});

// Check flow confirmation for a signal
async function checkFlowConfirmation(ticker, direction) {
    try {
        const response = await fetch(`${API_URL}/flow/confirm/${ticker}?direction=${direction}`);
        const data = await response.json();
        return data;
    } catch (error) {
        console.error('Error checking flow confirmation:', error);
        return null;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initOptionsFlow, 1100);
});


// ==========================================
// STRATEGY FILTER SYSTEM
// ==========================================

const strategyFilters = {
    strategies: new Set([
        'golden_touch', 'pullback_entry', 'taurus_signal', 'triple_line',
        'two_close_vol', 'zone_upgrade', 'exhaustion', 'ursa_signal',
        'apis_call', 'kodiak_call'
    ]),
    directions: new Set(['LONG', 'SHORT']),
    minScore: 1
};

function initStrategyFilters() {
    const selectAllBtn = document.getElementById('selectAllStrategies');
    const clearAllBtn = document.getElementById('clearAllStrategies');
    const scoreInput = document.getElementById('scoreThreshold');
    const filterLong = document.getElementById('filterLong');
    const filterShort = document.getElementById('filterShort');
    const strategyCheckboxes = document.querySelectorAll('.strategy-checkbox');

    // Select All button
    if (selectAllBtn) {
        selectAllBtn.addEventListener('click', () => {
            strategyCheckboxes.forEach(checkbox => {
                checkbox.checked = true;
                strategyFilters.strategies.add(checkbox.dataset.strategy);
            });
            updateFilterSummary();
            applyFiltersAndRefresh();
        });
    }

    // Clear All button
    if (clearAllBtn) {
        clearAllBtn.addEventListener('click', () => {
            strategyCheckboxes.forEach(checkbox => {
                checkbox.checked = false;
            });
            strategyFilters.strategies.clear();
            updateFilterSummary();
            applyFiltersAndRefresh();
        });
    }

    // Strategy checkboxes
    strategyCheckboxes.forEach(checkbox => {
        checkbox.addEventListener('change', (e) => {
            const strategy = e.target.dataset.strategy;
            if (e.target.checked) {
                strategyFilters.strategies.add(strategy);
            } else {
                strategyFilters.strategies.delete(strategy);
            }
            updateFilterSummary();
            applyFiltersAndRefresh();
        });
    });

    // Score input
    if (scoreInput) {
        scoreInput.addEventListener('input', (e) => {
            let value = parseInt(e.target.value) || 1;
            // Clamp value between 1 and 100
            value = Math.max(1, Math.min(100, value));
            strategyFilters.minScore = value;
            document.getElementById('activeMinScore').textContent = value;
            applyFiltersAndRefresh();
        });
    }

    // Direction filters
    if (filterLong) {
        filterLong.addEventListener('change', (e) => {
            if (e.target.checked) {
                strategyFilters.directions.add('LONG');
            } else {
                strategyFilters.directions.delete('LONG');
            }
            updateFilterSummary();
            applyFiltersAndRefresh();
        });
    }

    if (filterShort) {
        filterShort.addEventListener('change', (e) => {
            if (e.target.checked) {
                strategyFilters.directions.add('SHORT');
            } else {
                strategyFilters.directions.delete('SHORT');
            }
            updateFilterSummary();
            applyFiltersAndRefresh();
        });
    }

    // Initial summary
    updateFilterSummary();
}

function updateFilterSummary() {
    const strategyCountEl = document.getElementById('activeStrategyCount');
    const directionsEl = document.getElementById('activeDirections');
    const minScoreEl = document.getElementById('activeMinScore');

    if (strategyCountEl) {
        strategyCountEl.textContent = strategyFilters.strategies.size;
    }

    if (directionsEl) {
        const dirs = Array.from(strategyFilters.directions);
        if (dirs.length === 2) {
            directionsEl.textContent = 'LONG + SHORT';
        } else if (dirs.length === 1) {
            directionsEl.textContent = dirs[0];
        } else {
            directionsEl.textContent = 'NONE';
        }
    }

    if (minScoreEl) {
        minScoreEl.textContent = strategyFilters.minScore;
    }
}

function applyFiltersAndRefresh() {
    // Filter and re-render trade ideas
    filterTradeIdeas();
}

function filterTradeIdeas() {
    // Get all signals
    const currentSignals = activeAssetType === 'equity' ? signals.equity : signals.crypto;

    // Apply filters
    const filtered = currentSignals.filter(signal => {
        // Check strategy
        const signalStrategy = signal.strategy_name ? signal.strategy_name.toLowerCase().replace(/\s+/g, '_').replace(/\+/g, '') : '';
        const matchesStrategy = strategyFilters.strategies.size === 0 || strategyFilters.strategies.has(signalStrategy);

        // Check direction
        const matchesDirection = strategyFilters.directions.has(signal.direction);

        // Check score
        const matchesScore = (signal.score || 0) >= strategyFilters.minScore;

        return matchesStrategy && matchesDirection && matchesScore;
    });

    // Update display
    renderFilteredSignals(filtered);
    updateEmptyState(filtered.length);
}

function renderFilteredSignals(filtered) {
    // Use the existing renderSignals logic but with filtered data
    const container = document.getElementById('tradeSignals');
    if (!container) return;

    if (filtered.length === 0) {
        container.innerHTML = '<p class="empty-state">No signals match current filters</p>';
        return;
    }

    // Render top 10 signals
    const top10 = filtered.slice(0, 10);
    container.innerHTML = top10.map(signal => createSignalCard(signal)).join('');
}

function updateEmptyState(count) {
    const container = document.getElementById('tradeSignals');
    if (!container) return;

    if (count === 0) {
        container.innerHTML = '<p class="empty-state">No signals match current filters</p>';
    }
}

// Initialize strategy filters on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initStrategyFilters, 500);
});


// ==========================================
// POSITION MANAGEMENT
// ==========================================

let openPositions = [];
let pendingPositionSignal = null;
let pendingPositionCard = null;
let closingPosition = null;
let currentPrices = {};  // Cache of current prices for P&L calculation
let priceUpdateInterval = null;
let currentTradeType = 'equity';  // 'equity' or 'options'

function initPositionModals() {
    // Entry modal
    const closeEntryBtn = document.getElementById('closePositionModalBtn');
    const cancelEntryBtn = document.getElementById('cancelPositionBtn');
    const confirmEntryBtn = document.getElementById('confirmPositionBtn');
    const entryModal = document.getElementById('positionEntryModal');
    
    if (closeEntryBtn) closeEntryBtn.addEventListener('click', closePositionEntryModal);
    if (cancelEntryBtn) cancelEntryBtn.addEventListener('click', closePositionEntryModal);
    if (confirmEntryBtn) confirmEntryBtn.addEventListener('click', confirmPositionEntry);
    if (entryModal) {
        entryModal.addEventListener('click', (e) => {
            if (e.target === entryModal) closePositionEntryModal();
        });
    }
    
    // Entry price/qty inputs for live summary update
    const entryPriceInput = document.getElementById('positionEntryPrice');
    const qtyInput = document.getElementById('positionQuantity');
    if (entryPriceInput) entryPriceInput.addEventListener('input', updatePositionSummary);
    if (qtyInput) qtyInput.addEventListener('input', updatePositionSummary);
    
    // Trade type toggle (Equity / Options)
    const tradeTypeEquity = document.getElementById('tradeTypeEquity');
    const tradeTypeOptions = document.getElementById('tradeTypeOptions');
    if (tradeTypeEquity) tradeTypeEquity.addEventListener('click', () => setTradeType('equity'));
    if (tradeTypeOptions) tradeTypeOptions.addEventListener('click', () => setTradeType('options'));
    
    // Options fields - live summary update
    const optPremium = document.getElementById('optPositionPremium');
    const optContracts = document.getElementById('optPositionContracts');
    const optMaxLoss = document.getElementById('optPositionMaxLoss');
    const optStrategy = document.getElementById('optPositionStrategy');
    if (optPremium) optPremium.addEventListener('input', updateOptionsSummary);
    if (optContracts) optContracts.addEventListener('input', updateOptionsSummary);
    if (optMaxLoss) optMaxLoss.addEventListener('input', updateOptionsSummary);
    if (optStrategy) optStrategy.addEventListener('change', updateOptionsSummary);
    
    // Add leg button
    const addLegBtn = document.getElementById('optPositionAddLeg');
    if (addLegBtn) addLegBtn.addEventListener('click', addOptionsLeg);
    
    // Close modal
    const closeCloseBtn = document.getElementById('closeCloseModalBtn');
    const cancelCloseBtn = document.getElementById('cancelCloseBtn');
    const confirmCloseBtn = document.getElementById('confirmCloseBtn');
    const closeModal = document.getElementById('positionCloseModal');
    
    if (closeCloseBtn) closeCloseBtn.addEventListener('click', closePositionCloseModal);
    if (cancelCloseBtn) cancelCloseBtn.addEventListener('click', closePositionCloseModal);
    if (confirmCloseBtn) confirmCloseBtn.addEventListener('click', confirmPositionClose);
    if (closeModal) {
        closeModal.addEventListener('click', (e) => {
            if (e.target === closeModal) closePositionCloseModal();
        });
    }
    
    // Exit price/qty inputs for live P&L update
    const exitPriceInput = document.getElementById('positionExitPrice');
    const closeQtyInput = document.getElementById('closeQuantity');
    if (exitPriceInput) exitPriceInput.addEventListener('input', updateCloseSummary);
    if (closeQtyInput) closeQtyInput.addEventListener('input', updateCloseSummary);
    
    // Load existing positions
    loadOpenPositionsEnhanced();
    
    // Start price updates for P&L
    startPriceUpdates();
}

function openPositionEntryModal(signal, card) {
    pendingPositionSignal = signal;
    pendingPositionCard = card;
    
    // Populate modal
    document.getElementById('positionTickerDisplay').textContent = signal.ticker;
    const dirDisplay = document.getElementById('positionDirectionDisplay');
    dirDisplay.textContent = signal.direction;
    dirDisplay.className = 'position-direction-display ' + signal.direction;
    
    // Set label based on asset class
    const qtyLabel = document.getElementById('positionQtyLabel');
    if (signal.asset_class === 'CRYPTO') {
        qtyLabel.textContent = 'Quantity (Tokens) *';
    } else {
        qtyLabel.textContent = 'Quantity (Shares) *';
    }
    
    // Pre-fill entry price from signal
    document.getElementById('positionEntryPrice').value = signal.entry_price?.toFixed(2) || '';
    document.getElementById('positionQuantity').value = '';
    
    // Update summary
    document.getElementById('summaryStop').textContent = '$' + (signal.stop_loss?.toFixed(2) || '--');
    document.getElementById('summaryTarget').textContent = '$' + (signal.target_1?.toFixed(2) || '--');
    document.getElementById('summarySize').textContent = '$--';
    document.getElementById('summaryRisk').textContent = '$--';
    
    // Reset to equity mode
    setTradeType('equity');
    
    // Pre-fill options direction based on signal direction
    const optDirection = signal.direction === 'LONG' ? 'BULLISH' : 'BEARISH';
    
    // Pre-fill options strategy suggestion based on direction
    const optStrategySelect = document.getElementById('optPositionStrategy');
    if (optStrategySelect) {
        optStrategySelect.value = signal.direction === 'LONG' ? 'LONG_CALL' : 'LONG_PUT';
    }
    
    // Reset options fields
    resetOptionsFields();
    
    // Pre-fill first leg type based on direction
    const firstLegType = document.querySelector('#optPositionLegs .opt-leg-type');
    if (firstLegType) {
        firstLegType.value = signal.direction === 'LONG' ? 'CALL' : 'PUT';
    }
    
    // Set default expiry to ~30 days out
    const firstLegExpiry = document.querySelector('#optPositionLegs .opt-leg-expiry');
    if (firstLegExpiry) {
        const defaultExpiry = new Date();
        defaultExpiry.setDate(defaultExpiry.getDate() + 30);
        firstLegExpiry.value = defaultExpiry.toISOString().split('T')[0];
    }
    
    // Pre-fill strike near entry price (round to nearest 0.5)
    const firstLegStrike = document.querySelector('#optPositionLegs .opt-leg-strike');
    if (firstLegStrike && signal.entry_price) {
        firstLegStrike.value = (Math.round(signal.entry_price * 2) / 2).toFixed(1);
    }
    
    // Show modal
    document.getElementById('positionEntryModal').classList.add('active');
}

function closePositionEntryModal() {
    document.getElementById('positionEntryModal').classList.remove('active');
    pendingPositionSignal = null;
    pendingPositionCard = null;
    currentTradeType = 'equity';
}

function updatePositionSummary() {
    if (!pendingPositionSignal) return;
    
    const entryPrice = parseFloat(document.getElementById('positionEntryPrice').value) || 0;
    const qty = parseFloat(document.getElementById('positionQuantity').value) || 0;
    const stopLoss = pendingPositionSignal.stop_loss || 0;
    
    const positionSize = entryPrice * qty;
    const riskPerShare = Math.abs(entryPrice - stopLoss);
    const totalRisk = riskPerShare * qty;
    
    document.getElementById('summarySize').textContent = '$' + positionSize.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    document.getElementById('summaryRisk').textContent = '$' + totalRisk.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
}

async function confirmPositionEntry() {
    if (!pendingPositionSignal) return;

    if (currentTradeType === 'options') {
        await confirmOptionsPositionEntry();
        return;
    }

    // Save signal reference before modal close nulls it
    const signal = pendingPositionSignal;
    const card = pendingPositionCard;

    const entryPrice = parseFloat(document.getElementById('positionEntryPrice').value);
    const qty = parseFloat(document.getElementById('positionQuantity').value);

    if (!entryPrice || !qty) {
        alert('Please enter both entry price and quantity');
        return;
    }

    try {
        // Accept signal via new API endpoint (includes full logging)
        const response = await fetch(`${API_URL}/signals/${signal.signal_id}/accept`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                signal_id: signal.signal_id,
                actual_entry_price: entryPrice,
                quantity: qty,
                stop_loss: signal.stop_loss,
                target_1: signal.target_1,
                target_2: signal.target_2,
                notes: `Accepted via Trade Ideas UI`
            })
        });

        const data = await response.json();

        if (data.status === 'accepted' || data.position_id) {
            // Remove signal card with animation
            if (card) {
                card.style.opacity = '0';
                card.style.transform = 'translateX(-20px)';
                setTimeout(() => {
                    card.remove();
                    // Auto-refill Trade Ideas list
                    refillTradeIdeas();
                }, 300);
            }

            // Close modal
            closePositionEntryModal();

            // Reload positions
            await loadOpenPositionsEnhanced();

            // Add ticker to chart tabs
            addPositionChartTab(signal.ticker);

            // Store price levels for chart display
            storePriceLevels(signal.ticker, {
                entry: entryPrice,
                stop: signal.stop_loss,
                target1: signal.target_1,
                target2: signal.target_2
            });

            console.log(`Position accepted: ${signal.ticker} ${signal.direction} @ $${entryPrice}`);
        } else {
            alert('Failed to accept signal: ' + (data.detail || data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error accepting signal:', error);
        alert('Failed to accept signal');
    }
}

// ==========================================
// TRADE TYPE TOGGLE (Equity / Options)
// ==========================================

function setTradeType(type) {
    currentTradeType = type;
    const equityBtn = document.getElementById('tradeTypeEquity');
    const optionsBtn = document.getElementById('tradeTypeOptions');
    const equityFields = document.getElementById('equityFields');
    const optionsFields = document.getElementById('optionsFields');
    const modalContainer = document.getElementById('positionModalContainer');
    const modalTitle = document.getElementById('positionModalTitle');
    const confirmBtn = document.getElementById('confirmPositionBtn');
    
    if (type === 'equity') {
        equityBtn.classList.add('active');
        optionsBtn.classList.remove('active');
        equityFields.style.display = 'block';
        optionsFields.style.display = 'none';
        modalContainer.classList.remove('options-mode');
        modalTitle.textContent = 'Open Position';
        confirmBtn.textContent = 'Open Position';
    } else {
        equityBtn.classList.remove('active');
        optionsBtn.classList.add('active');
        equityFields.style.display = 'none';
        optionsFields.style.display = 'block';
        modalContainer.classList.add('options-mode');
        modalTitle.textContent = 'Open Options Position';
        confirmBtn.textContent = 'Open Options Position';
        updateOptionsSummary();
    }
}

function resetOptionsFields() {
    // Reset strategy
    const strategySelect = document.getElementById('optPositionStrategy');
    if (strategySelect) strategySelect.selectedIndex = 0;
    
    // Clear numeric inputs
    const fieldsToReset = ['optPositionPremium', 'optPositionMaxProfit', 'optPositionMaxLoss', 'optPositionBreakeven', 'optPositionThesis'];
    fieldsToReset.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    
    // Reset contracts to 1
    const contracts = document.getElementById('optPositionContracts');
    if (contracts) contracts.value = '1';
    
    // Reset legs to single default leg
    const legsContainer = document.getElementById('optPositionLegs');
    if (legsContainer) {
        legsContainer.innerHTML = `
            <div class="opt-leg-row" data-leg="1">
                <div class="opt-leg-fields">
                    <select class="opt-leg-action position-input-sm">
                        <option value="BUY">BUY</option>
                        <option value="SELL">SELL</option>
                    </select>
                    <select class="opt-leg-type position-input-sm">
                        <option value="CALL">CALL</option>
                        <option value="PUT">PUT</option>
                    </select>
                    <input type="number" class="opt-leg-strike position-input-sm" placeholder="Strike" step="0.5">
                    <input type="date" class="opt-leg-expiry position-input-sm">
                    <input type="number" class="opt-leg-qty position-input-sm" placeholder="Qty" value="1" min="1" step="1">
                    <input type="number" class="opt-leg-premium position-input-sm" placeholder="Premium" step="0.01">
                </div>
            </div>
        `;
    }
}

function addOptionsLeg() {
    const legsContainer = document.getElementById('optPositionLegs');
    if (!legsContainer) return;
    
    const legCount = legsContainer.querySelectorAll('.opt-leg-row').length + 1;
    
    const legHTML = `
        <div class="opt-leg-row" data-leg="${legCount}">
            <div class="opt-leg-fields">
                <select class="opt-leg-action position-input-sm">
                    <option value="BUY">BUY</option>
                    <option value="SELL">SELL</option>
                </select>
                <select class="opt-leg-type position-input-sm">
                    <option value="CALL">CALL</option>
                    <option value="PUT">PUT</option>
                </select>
                <input type="number" class="opt-leg-strike position-input-sm" placeholder="Strike" step="0.5">
                <input type="date" class="opt-leg-expiry position-input-sm">
                <input type="number" class="opt-leg-qty position-input-sm" placeholder="Qty" value="1" min="1" step="1">
                <input type="number" class="opt-leg-premium position-input-sm" placeholder="Premium" step="0.01">
            </div>
        </div>
    `;
    
    legsContainer.insertAdjacentHTML('beforeend', legHTML);
}

function collectOptionsLegs() {
    const legRows = document.querySelectorAll('#optPositionLegs .opt-leg-row');
    const legs = [];
    
    legRows.forEach(row => {
        const action = row.querySelector('.opt-leg-action')?.value;
        const optionType = row.querySelector('.opt-leg-type')?.value;
        const strike = parseFloat(row.querySelector('.opt-leg-strike')?.value);
        const expiry = row.querySelector('.opt-leg-expiry')?.value;
        const qty = parseInt(row.querySelector('.opt-leg-qty')?.value) || 1;
        const premium = parseFloat(row.querySelector('.opt-leg-premium')?.value);
        
        if (strike && expiry) {
            legs.push({
                action: action,
                option_type: optionType,
                strike: strike,
                expiration: expiry,
                quantity: qty,
                premium: premium || 0
            });
        }
    });
    
    return legs;
}

function updateOptionsSummary() {
    if (!pendingPositionSignal) return;
    
    const strategy = document.getElementById('optPositionStrategy')?.value || '--';
    const premium = parseFloat(document.getElementById('optPositionPremium')?.value) || 0;
    const contracts = parseInt(document.getElementById('optPositionContracts')?.value) || 1;
    const maxLoss = parseFloat(document.getElementById('optPositionMaxLoss')?.value);
    
    // Strategy display name
    const strategyNames = {
        'LONG_CALL': 'Long Call', 'LONG_PUT': 'Long Put',
        'BULL_CALL_SPREAD': 'Bull Call Spread', 'BEAR_PUT_SPREAD': 'Bear Put Spread',
        'BULL_PUT_SPREAD': 'Bull Put Spread', 'BEAR_CALL_SPREAD': 'Bear Call Spread',
        'IRON_CONDOR': 'Iron Condor', 'STRADDLE': 'Straddle',
        'STRANGLE': 'Strangle', 'CUSTOM': 'Custom'
    };
    
    // Direction from signal
    const direction = pendingPositionSignal.direction === 'LONG' ? 'BULLISH' : 'BEARISH';
    
    document.getElementById('optSummaryStrategy').textContent = strategyNames[strategy] || strategy;
    document.getElementById('optSummaryDirection').textContent = direction;
    
    // Net premium (total = per-contract premium * contracts * 100 for standard options)
    const totalPremium = premium * contracts;
    const premiumStr = totalPremium !== 0 ? '$' + Math.abs(totalPremium).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) : '$--';
    document.getElementById('optSummaryPremium').textContent = (premium < 0 ? '-' : '+') + premiumStr;
    
    // Max risk
    if (maxLoss) {
        document.getElementById('optSummaryRisk').textContent = '$' + Math.abs(maxLoss).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    } else if (premium < 0) {
        // For debit positions, max risk is the premium paid
        document.getElementById('optSummaryRisk').textContent = '$' + Math.abs(totalPremium).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
    } else {
        document.getElementById('optSummaryRisk').textContent = '$--';
    }
}

async function confirmOptionsPositionEntry() {
    if (!pendingPositionSignal) return;
    
    const strategy = document.getElementById('optPositionStrategy')?.value;
    const premium = parseFloat(document.getElementById('optPositionPremium')?.value);
    const contracts = parseInt(document.getElementById('optPositionContracts')?.value) || 1;
    const legs = collectOptionsLegs();
    
    // Validate required fields
    if (!strategy) {
        alert('Please select an options strategy');
        return;
    }
    if (isNaN(premium)) {
        alert('Please enter the net premium');
        return;
    }
    if (legs.length === 0) {
        alert('Please fill in at least one option leg (strike and expiry required)');
        return;
    }
    
    const direction = pendingPositionSignal.direction === 'LONG' ? 'BULLISH' : 'BEARISH';
    const maxProfit = parseFloat(document.getElementById('optPositionMaxProfit')?.value) || null;
    const maxLoss = parseFloat(document.getElementById('optPositionMaxLoss')?.value) || null;
    const breakevenStr = document.getElementById('optPositionBreakeven')?.value || '';
    const breakeven = breakevenStr ? breakevenStr.split(',').map(s => parseFloat(s.trim())).filter(n => !isNaN(n)) : null;
    const thesis = document.getElementById('optPositionThesis')?.value || '';
    
    try {
        // Step 1: Create options position
        const optResponse = await fetch(`${API_URL}/signals/${pendingPositionSignal.signal_id}/accept-options`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                signal_id: pendingPositionSignal.signal_id,
                underlying: pendingPositionSignal.ticker,
                strategy_type: strategy,
                direction: direction,
                legs: legs,
                net_premium: premium,
                contracts: contracts,
                max_profit: maxProfit,
                max_loss: maxLoss,
                breakeven: breakeven,
                thesis: thesis,
                notes: `Accepted via Trade Ideas UI (Options: ${strategy})`
            })
        });
        
        const data = await optResponse.json();
        
        if (data.status === 'success' || data.status === 'accepted' || data.position_id) {
            // Remove signal card with animation
            if (pendingPositionCard) {
                pendingPositionCard.style.opacity = '0';
                pendingPositionCard.style.transform = 'translateX(-20px)';
                setTimeout(() => {
                    pendingPositionCard.remove();
                    refillTradeIdeas();
                }, 300);
            }
            
            // Close modal
            closePositionEntryModal();
            
            // Reload positions (both equity and options)
            await loadOpenPositionsEnhanced();
            
            // Add ticker to chart tabs
            addPositionChartTab(pendingPositionSignal.ticker);
            
            console.log(`ðŸ“Š Options position accepted: ${pendingPositionSignal.ticker} ${strategy} - Premium: $${premium}`);
        } else {
            alert('Failed to accept signal as options: ' + (data.detail || data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error accepting signal as options:', error);
        alert('Failed to accept signal as options position');
    }
}

// Store price levels for chart sidebar display
function storePriceLevels(ticker, levels) {
    if (!window.activePriceLevels) {
        window.activePriceLevels = {};
    }
    window.activePriceLevels[ticker] = levels;
    
    // Update panel if currently viewing this ticker
    if (currentSymbol === ticker) {
        updatePriceLevelsPanel(ticker);
    }
}

async function loadOpenPositionsEnhanced() {
    try {
        // Try v2 API first, fall back to v1
        let response = await fetch(`${API_URL}/v2/positions?status=OPEN`);
        let data = await response.json();

        if (data.positions) {
            openPositions = data.positions;
            renderPositionsEnhanced();
            updatePositionsCount();
            updatePositionChartTabs();
            loadPortfolioSummary();
            return;
        }

        // Fallback to v1
        response = await fetch(`${API_URL}/positions/open`);
        data = await response.json();
        if (data.status === 'success') {
            openPositions = data.positions || [];
            renderPositionsEnhanced();
            updatePositionsCount();
            updatePositionChartTabs();
        }
    } catch (error) {
        console.error('Error loading positions:', error);
    }
}

async function loadPortfolioSummary() {
    try {
        const response = await fetch(`${API_URL}/v2/positions/summary`);
        const data = await response.json();
        renderPortfolioSummaryWidget(data);
    } catch (error) {
        console.error('Error loading portfolio summary:', error);
    }
}

function renderPortfolioSummaryWidget(summary) {
    const widget = document.getElementById('portfolio-summary-widget');
    if (!widget) return;

    const balanceStr = '$' + (summary.account_balance || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
    const riskStr = '$' + (summary.capital_at_risk || 0).toLocaleString('en-US', {minimumFractionDigits: 0, maximumFractionDigits: 0});
    const riskPct = (summary.capital_at_risk_pct || 0).toFixed(1);
    const riskClass = summary.capital_at_risk_pct > 40 ? 'risk-high' : summary.capital_at_risk_pct > 25 ? 'risk-medium' : 'risk-low';

    const directionEmoji = summary.net_direction === 'BULLISH' ? 'BULL' : summary.net_direction === 'BEARISH' ? 'BEAR' : 'FLAT';
    const dirClass = summary.net_direction === 'BULLISH' ? 'direction-bull' : summary.net_direction === 'BEARISH' ? 'direction-bear' : 'direction-flat';

    let expiryLine = '';
    if (summary.nearest_dte !== null && summary.nearest_dte !== undefined) {
        const urgency = summary.nearest_dte <= 7 ? 'dte-urgent' : summary.nearest_dte <= 14 ? 'dte-soon' : 'dte-ok';
        expiryLine = `<div class="portfolio-stat"><span class="stat-label">Nearest Exp</span><span class="stat-value ${urgency}">${summary.nearest_dte} DTE</span></div>`;
    }

    widget.innerHTML = `
        <div class="portfolio-summary-grid">
            <div class="portfolio-stat">
                <span class="stat-label">Balance</span>
                <span class="stat-value">${balanceStr}</span>
            </div>
            <div class="portfolio-stat">
                <span class="stat-label">Positions</span>
                <span class="stat-value">${summary.position_count || 0}</span>
            </div>
            <div class="portfolio-stat">
                <span class="stat-label">At Risk</span>
                <span class="stat-value ${riskClass}">${riskStr} (${riskPct}%)</span>
            </div>
            <div class="portfolio-stat">
                <span class="stat-label">Lean</span>
                <span class="stat-value ${dirClass}">${directionEmoji}</span>
            </div>
            ${expiryLine}
        </div>
    `;
}

function updatePositionsCount() {
    const countEl = document.getElementById('positionsCount');
    if (countEl) {
        countEl.textContent = openPositions.length;
    }
}

function renderPositionsEnhanced() {
    const container = document.getElementById('openPositions');
    if (!container) return;

    if (!openPositions || openPositions.length === 0) {
        container.innerHTML = '<p class="empty-state">No open positions</p>';
        return;
    }

    // Sort by DTE (soonest first), then by ticker
    const sorted = [...openPositions].sort((a, b) => {
        const dteA = a.dte ?? 9999;
        const dteB = b.dte ?? 9999;
        if (dteA !== dteB) return dteA - dteB;
        return (a.ticker || '').localeCompare(b.ticker || '');
    });

    container.innerHTML = sorted.map(pos => {
        const posId = pos.position_id || pos.id || pos.signal_id;

        // P&L display
        const pnl = pos.unrealized_pnl || 0;
        const pnlClass = pnl >= 0 ? 'positive' : 'negative';
        const pnlStr = (pnl >= 0 ? '+' : '-') + '$' + Math.abs(pnl).toFixed(2);

        // Structure badge
        const structure = pos.structure || pos.strategy || 'EQUITY';
        const structureDisplay = structure.replace(/_/g, ' ').toUpperCase();

        // Strikes + DTE line for options
        let strikeLine = '';
        if (pos.long_strike || pos.short_strike) {
            const strikes = [pos.long_strike, pos.short_strike].filter(Boolean).join('/');
            const expiryStr = pos.expiry ? new Date(pos.expiry + 'T00:00:00').toLocaleDateString('en-US', {month: 'numeric', day: 'numeric'}) : '';
            const dteStr = pos.dte !== null && pos.dte !== undefined ? `${pos.dte} DTE` : '';
            const dteBadge = pos.dte !== null && pos.dte <= 7 ? 'dte-urgent' : pos.dte <= 14 ? 'dte-soon' : '';
            strikeLine = `<div class="position-strikes">${strikes} ${expiryStr} <span class="${dteBadge}">${dteStr}</span></div>`;
        } else if (pos.expiry) {
            const expiryStr = new Date(pos.expiry + 'T00:00:00').toLocaleDateString('en-US', {month: 'numeric', day: 'numeric'});
            const dteStr = pos.dte !== null && pos.dte !== undefined ? `${pos.dte} DTE` : '';
            strikeLine = `<div class="position-strikes">${expiryStr} <span>${dteStr}</span></div>`;
        }

        // Max loss bar
        let maxLossBar = '';
        if (pos.max_loss && pos.max_loss > 0) {
            const lossConsumed = Math.min(100, Math.max(0, (Math.abs(pnl) / pos.max_loss) * 100));
            const barClass = pnl < 0 ? (lossConsumed > 75 ? 'loss-severe' : lossConsumed > 50 ? 'loss-warning' : 'loss-ok') : 'loss-ok';
            maxLossBar = `
                <div class="max-loss-bar-wrap">
                    <div class="max-loss-bar ${barClass}" style="width: ${lossConsumed}%"></div>
                    <span class="max-loss-label">Max loss: $${pos.max_loss.toFixed(0)}</span>
                </div>`;
        }

        return `
            <div class="position-card" data-position-id="${posId}">
                <button class="position-remove-btn" data-position-id="${posId}" title="Remove position">x</button>
                <div class="position-card-header">
                    <span class="position-ticker" data-ticker="${pos.ticker}">${pos.ticker}</span>
                    <span class="position-structure-badge">${structureDisplay}</span>
                </div>
                ${strikeLine}
                <div class="position-details">
                    <div class="position-detail">
                        <div class="position-detail-label">Entry</div>
                        <div class="position-detail-value">$${pos.entry_price?.toFixed(2) || '--'}</div>
                    </div>
                    <div class="position-detail">
                        <div class="position-detail-label">Qty</div>
                        <div class="position-detail-value">${pos.quantity || '--'}</div>
                    </div>
                    <div class="position-detail">
                        <div class="position-detail-label">Stop</div>
                        <div class="position-detail-value">${pos.stop_loss ? '$' + pos.stop_loss.toFixed(2) : '--'}</div>
                    </div>
                    <div class="position-detail">
                        <div class="position-detail-label">Target</div>
                        <div class="position-detail-value">${pos.target_1 ? '$' + pos.target_1.toFixed(2) : '--'}</div>
                    </div>
                </div>
                ${maxLossBar}
                <div class="position-pnl">
                    <span class="pnl-label">Unrealized P&L</span>
                    <span class="pnl-value ${pnlClass}">${pnlStr}</span>
                </div>
                <div class="position-actions">
                    <button class="position-btn-small edit-btn" data-position-id="${posId}">Edit</button>
                    <button class="position-btn-small close-btn" data-position-id="${posId}">Close</button>
                </div>
            </div>
        `;
    }).join('');
    
    // Attach events
    container.querySelectorAll('.position-ticker').forEach(el => {
        el.addEventListener('click', (e) => {
            e.stopPropagation();
            changeChartSymbol(e.target.dataset.ticker);
        });
    });

    container.querySelectorAll('.close-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const positionId = btn.dataset.positionId;
            const position = openPositions.find(p => (p.position_id || p.id || p.signal_id) == positionId);
            if (position) openPositionCloseModal(position);
        });
    });

    container.querySelectorAll('.edit-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const positionId = btn.dataset.positionId;
            const position = openPositions.find(p => (p.position_id || p.id || p.signal_id) == positionId);
            if (position) openPositionEditModal(position);
        });
    });

    container.querySelectorAll('.position-remove-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const positionId = btn.dataset.positionId;
            const position = openPositions.find(p => (p.position_id || p.id || p.signal_id) == positionId)
            if (position) openPositionRemoveModal(position);
        });
    });
}

function calculatePnL(position, currentPrice) {
    if (!position.entry_price || !position.quantity || !currentPrice) return 0;
    
    if (position.direction === 'LONG') {
        return (currentPrice - position.entry_price) * position.quantity;
    } else {
        return (position.entry_price - currentPrice) * position.quantity;
    }
}

function openPositionCloseModal(position) {
    closingPosition = position;
    
    document.getElementById('closeTickerDisplay').textContent = position.ticker;
    document.getElementById('positionExitPrice').value = '';
    document.getElementById('closeQuantity').value = position.quantity;
    document.getElementById('closeQtyHint').textContent = `You have ${position.quantity} ${position.asset_class === 'CRYPTO' ? 'tokens' : 'shares'}`;
    document.getElementById('closeEntryPrice').textContent = '$' + (position.entry_price?.toFixed(2) || '--');
    document.getElementById('closeRealizedPnL').textContent = '$--';
    document.getElementById('closeRealizedPnL').className = '';
    
    document.getElementById('positionCloseModal').classList.add('active');
}

function closePositionCloseModal() {
    document.getElementById('positionCloseModal').classList.remove('active');
    closingPosition = null;
}

function openPositionRemoveModal(position) {
    const modal = document.createElement('div');
    modal.className = 'signal-modal-overlay active';
    modal.innerHTML = `
        <div class="signal-modal remove-modal">
            <div class="modal-header">
                <h3>Remove ${position.ticker} Position</h3>
                <button class="modal-close">&times;</button>
            </div>
            <div class="modal-body">
                <p class="warning-text">THIS TRADE WILL NOT BE ARCHIVED FOR BACKTESTING</p>
                <p>Use this only for glitched positions or trades you do not want logged.</p>
            </div>
            <div class="modal-actions">
                <button class="modal-btn cancel">Cancel</button>
                <button class="modal-btn remove-position">Remove Position</button>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    modal.querySelector('.modal-close').addEventListener('click', () => modal.remove());
    modal.querySelector('.modal-btn.cancel').addEventListener('click', () => modal.remove());
    modal.querySelector('.modal-btn.remove-position').addEventListener('click', async () => {
        modal.remove();
        await removePositionWithoutArchive(position);
    });

    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
}

async function removePositionWithoutArchive(position) {
    try {
        const posId = position.position_id || position.id;
        if (!posId) {
            alert('Cannot remove position: missing id');
            return;
        }
        // Try v2 first, fall back to v1
        let response;
        if (position.position_id) {
            response = await fetch(`${API_URL}/v2/positions/${posId}`, { method: 'DELETE' });
        } else {
            response = await fetch(`${API_URL}/positions/${posId}`, { method: 'DELETE' });
        }
        const data = await response.json();

        if (data.status === 'deleted' || data.status === 'removed') {
            openPositions = openPositions.filter(p => (p.position_id || p.id || p.signal_id) !== posId);
            renderPositionsEnhanced();
            updatePositionsCount();
            updatePositionChartTabs();
        } else {
            alert('Failed to remove position: ' + (data.detail || data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error removing position:', error);
        alert('Failed to remove position');
    }
}

function updateCloseSummary() {
    if (!closingPosition) return;
    
    const exitPrice = parseFloat(document.getElementById('positionExitPrice').value) || 0;
    const closeQty = parseFloat(document.getElementById('closeQuantity').value) || 0;
    
    if (exitPrice && closeQty) {
        let pnl;
        if (closingPosition.direction === 'LONG') {
            pnl = (exitPrice - closingPosition.entry_price) * closeQty;
        } else {
            pnl = (closingPosition.entry_price - exitPrice) * closeQty;
        }
        
        const pnlStr = (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2);
        const pnlEl = document.getElementById('closeRealizedPnL');
        pnlEl.textContent = pnlStr;
        pnlEl.className = pnl >= 0 ? 'positive' : 'negative';
    }
}

async function confirmPositionClose() {
    if (!closingPosition) return;
    
    const exitPrice = parseFloat(document.getElementById('positionExitPrice').value);
    const closeQty = parseFloat(document.getElementById('closeQuantity').value);
    
    if (!exitPrice || !closeQty) {
        alert('Please enter exit price and quantity');
        return;
    }
    
    if (closeQty > closingPosition.quantity) {
        alert('Cannot close more than you own');
        return;
    }
    
    // Calculate P&L to determine if this is a loss
    const entryPrice = closingPosition.entry_price || 0;
    let pnl;
    if (closingPosition.direction === 'LONG') {
        pnl = (exitPrice - entryPrice) * closeQty;
    } else {
        pnl = (entryPrice - exitPrice) * closeQty;
    }
    
    // Determine trade outcome
    let tradeOutcome;
    if (pnl > 0) {
        tradeOutcome = 'WIN';
    } else if (pnl < 0) {
        tradeOutcome = 'LOSS';
    } else {
        tradeOutcome = 'BREAKEVEN';
    }
    
    // If it's a loss, show loss classification modal
    if (tradeOutcome === 'LOSS') {
        showLossClassificationModal(closingPosition, exitPrice, closeQty, pnl);
        return;
    }
    
    // Otherwise, proceed with close
    await executePositionClose(closingPosition.id, exitPrice, closeQty, tradeOutcome, null, null);
}

function showLossClassificationModal(position, exitPrice, closeQty, pnl) {
    const modal = document.createElement('div');
    modal.className = 'signal-modal-overlay active';
    modal.innerHTML = `
        <div class="signal-modal loss-modal">
            <div class="modal-header">
                <h3>Loss Classification - ${position.ticker}</h3>
                <button class="modal-close">&times;</button>
            </div>
            <div class="modal-body">
                <div class="loss-summary">
                    <p class="loss-amount">Loss: <span class="negative">$${Math.abs(pnl).toFixed(2)}</span></p>
                </div>
                <p>What caused this loss? (for backtesting analysis)</p>
                <div class="loss-reasons">
                    <label class="loss-reason setup-failed">
                        <input type="radio" name="lossReason" value="SETUP_FAILED">
                        <span>Setup Failed</span>
                        <small>The trade thesis was wrong - the setup didn't work as expected</small>
                    </label>
                    <label class="loss-reason execution-error">
                        <input type="radio" name="lossReason" value="EXECUTION_ERROR">
                        <span>Execution Error</span>
                        <small>I made a mistake - bad entry, moved stop, over-leveraged, etc.</small>
                    </label>
                    <label class="loss-reason market-conditions">
                        <input type="radio" name="lossReason" value="MARKET_CONDITIONS" checked>
                        <span>Market Conditions</span>
                        <small>Unexpected news, volatility, or market-wide move against position</small>
                    </label>
                </div>
                <div class="modal-field">
                    <label>Notes (optional)</label>
                    <textarea id="lossNotes" placeholder="What did you learn from this trade?"></textarea>
                </div>
                <div class="modal-field">
                    <label>
                        <input type="checkbox" id="stopHitCheck">
                        Stop loss was hit (triggered automatically)
                    </label>
                </div>
            </div>
            <div class="modal-actions">
                <button class="modal-btn cancel">Cancel</button>
                <button class="modal-btn close-position">Confirm Close</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
    
    // Handle close
    modal.querySelector('.modal-close').addEventListener('click', () => modal.remove());
    modal.querySelector('.modal-btn.cancel').addEventListener('click', () => modal.remove());
    
    // Handle confirm
    modal.querySelector('.modal-btn.close-position').addEventListener('click', async () => {
        const lossReason = modal.querySelector('input[name="lossReason"]:checked')?.value || 'MARKET_CONDITIONS';
        const notes = modal.querySelector('#lossNotes').value;
        const stopHit = modal.querySelector('#stopHitCheck').checked;
        
        modal.remove();
        await executePositionClose(position.id, exitPrice, closeQty, 'LOSS', lossReason, notes, stopHit);
    });
    
    // Close on backdrop click
    modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.remove();
    });
}

async function executePositionClose(positionId, exitPrice, closeQty, tradeOutcome, lossReason, notes, stopHit = false) {
    try {
        // Save reference before modal close might null it
        const position = closingPosition;

        // Try v2 close endpoint first (creates trade record automatically)
        let response;
        let data;
        if (position && position.position_id) {
            response = await fetch(`${API_URL}/v2/positions/${position.position_id}/close`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    exit_price: exitPrice,
                    notes: [lossReason, notes].filter(Boolean).join(' | ') || null
                })
            });
            data = await response.json();
        } else {
            // Fallback to v1
            response = await fetch(`${API_URL}/positions/close`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    position_id: positionId,
                    exit_price: exitPrice,
                    quantity_closed: closeQty,
                    trade_outcome: tradeOutcome,
                    loss_reason: lossReason,
                    actual_stop_hit: stopHit,
                    notes: notes
                })
            });
            data = await response.json();
        }

        if (data.status === 'success' || data.status === 'closed' || data.status === 'partial_close') {
            closePositionCloseModal();
            await loadOpenPositionsEnhanced();

            // Remove chart tab if fully closed
            if (position && closeQty >= position.quantity) {
                removePositionChartTab(position.ticker);
                if (window.activePriceLevels) {
                    delete window.activePriceLevels[position.ticker];
                }
            }

            const outcome = data.trade_outcome || tradeOutcome;
            console.log(`Position closed: ${position?.ticker} - ${outcome} - P&L: $${data.realized_pnl?.toFixed(2) || '--'}`);
        } else {
            alert('Failed to close position: ' + (data.detail || data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error closing position:', error);
        alert('Failed to close position');
    }
}

// ==========================================
// UNIFIED POSITION ENTRY FORM (Brief 10 — C3)
// ==========================================

function openUnifiedPositionModal() {
    let modal = document.getElementById('unifiedPositionModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'unifiedPositionModal';
        modal.className = 'signal-modal-overlay';
        modal.innerHTML = `
            <div class="signal-modal unified-position-modal">
                <div class="modal-header">
                    <h3>Add Position</h3>
                    <button class="modal-close" id="closeUnifiedPositionModal">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-row">
                        <label>Ticker</label>
                        <input type="text" id="upTicker" placeholder="SPY" style="text-transform: uppercase;">
                    </div>
                    <div class="form-row">
                        <label>Structure</label>
                        <select id="upStructure">
                            <option value="stock">Stock</option>
                            <option value="long_call">Long Call</option>
                            <option value="long_put">Long Put</option>
                            <option value="put_credit_spread" selected>Put Credit Spread</option>
                            <option value="put_debit_spread">Put Debit Spread</option>
                            <option value="call_credit_spread">Call Credit Spread</option>
                            <option value="call_debit_spread">Call Debit Spread</option>
                            <option value="iron_condor">Iron Condor</option>
                            <option value="iron_butterfly">Iron Butterfly</option>
                            <option value="straddle">Straddle</option>
                            <option value="strangle">Strangle</option>
                            <option value="custom">Custom (enter below)</option>
                        </select>
                    </div>
                    <div class="form-row custom-structure-field" style="display:none;">
                        <label>Custom Structure Name</label>
                        <input type="text" id="upCustomStructure" placeholder="e.g. broken_wing_butterfly">
                    </div>
                    <div class="form-row spread-fields">
                        <label>Long Strike</label>
                        <input type="number" id="upLongStrike" step="0.5" placeholder="48">
                    </div>
                    <div class="form-row spread-fields">
                        <label>Short Strike</label>
                        <input type="number" id="upShortStrike" step="0.5" placeholder="50">
                    </div>
                    <div class="form-row options-fields">
                        <label>Expiry</label>
                        <input type="date" id="upExpiry">
                    </div>
                    <div class="form-row">
                        <label>Net Premium / Entry Price</label>
                        <input type="number" id="upEntryPrice" step="0.01" placeholder="0.35">
                    </div>
                    <div class="form-row">
                        <label>Quantity</label>
                        <input type="number" id="upQuantity" value="1" min="1">
                    </div>
                    <div class="form-row">
                        <label>Stop Loss</label>
                        <input type="number" id="upStopLoss" step="0.01" placeholder="Optional">
                    </div>
                    <div class="form-row">
                        <label>Target</label>
                        <input type="number" id="upTarget" step="0.01" placeholder="Optional">
                    </div>
                    <div class="form-row">
                        <label>Notes</label>
                        <input type="text" id="upNotes" placeholder="Optional">
                    </div>
                    <div class="risk-calc-preview" id="upRiskPreview"></div>
                </div>
                <div class="modal-actions">
                    <button class="modal-btn cancel" id="upCancel">Cancel</button>
                    <button class="modal-btn accept" id="upSubmit">Add Position</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        // Events
        document.getElementById('closeUnifiedPositionModal').addEventListener('click', () => modal.classList.remove('active'));
        document.getElementById('upCancel').addEventListener('click', () => modal.classList.remove('active'));
        modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('active'); });
        document.getElementById('upSubmit').addEventListener('click', submitUnifiedPosition);
        document.getElementById('upStructure').addEventListener('change', updateUnifiedFormFields);

        // Auto-calculate risk on input change
        ['upLongStrike', 'upShortStrike', 'upEntryPrice', 'upQuantity'].forEach(id => {
            document.getElementById(id).addEventListener('input', updateRiskPreview);
        });
    }

    // Clear form on each open
    document.getElementById('upTicker').value = '';
    document.getElementById('upStructure').value = 'put_credit_spread';
    document.getElementById('upLongStrike').value = '';
    document.getElementById('upShortStrike').value = '';
    document.getElementById('upExpiry').value = '';
    document.getElementById('upEntryPrice').value = '';
    document.getElementById('upQuantity').value = '1';
    document.getElementById('upStopLoss').value = '';
    document.getElementById('upTarget').value = '';
    document.getElementById('upNotes').value = '';
    const customInput = document.getElementById('upCustomStructure');
    if (customInput) customInput.value = '';
    updateUnifiedFormFields();
    document.getElementById('upRiskPreview').innerHTML = '';
    modal.classList.add('active');
}

function updateUnifiedFormFields() {
    const structure = document.getElementById('upStructure').value;
    const isCustom = structure === 'custom';
    const multiStrike = ['straddle', 'strangle', 'iron_condor', 'iron_butterfly'];
    const isSpread = structure.includes('spread') || multiStrike.includes(structure) || isCustom;
    const isOptions = structure !== 'stock';

    document.querySelectorAll('.spread-fields').forEach(el => el.style.display = isSpread ? '' : 'none');
    document.querySelectorAll('.options-fields').forEach(el => el.style.display = isOptions ? '' : 'none');
    document.querySelectorAll('.custom-structure-field').forEach(el => el.style.display = isCustom ? '' : 'none');
}

function updateRiskPreview() {
    const structure = document.getElementById('upStructure').value;
    const longStrike = parseFloat(document.getElementById('upLongStrike').value) || 0;
    const shortStrike = parseFloat(document.getElementById('upShortStrike').value) || 0;
    const entryPrice = parseFloat(document.getElementById('upEntryPrice').value) || 0;
    const quantity = parseInt(document.getElementById('upQuantity').value) || 1;
    const preview = document.getElementById('upRiskPreview');

    if (!entryPrice) { preview.innerHTML = ''; return; }

    const isSpread = structure.includes('spread') || structure === 'iron_condor' || structure === 'iron_butterfly' || structure === 'custom';
    const isStock = structure === 'stock';

    if (isStock) {
        const maxLoss = entryPrice * quantity;
        preview.innerHTML = `<div class="risk-preview-line">Max Loss: $${maxLoss.toFixed(2)} (full position)</div>`;
        return;
    }

    if (isSpread && longStrike && shortStrike) {
        const width = Math.abs(shortStrike - longStrike);
        const isCredit = structure.includes('credit');
        const premium = Math.abs(entryPrice);
        const maxLoss = isCredit ? (width - premium) * 100 * quantity : premium * 100 * quantity;
        const maxProfit = isCredit ? premium * 100 * quantity : (width - premium) * 100 * quantity;
        preview.innerHTML = `
            <div class="risk-preview-line">Max Loss: $${maxLoss.toFixed(2)}</div>
            <div class="risk-preview-line">Max Profit: $${maxProfit.toFixed(2)}</div>
        `;
    } else if (!isStock) {
        const premium = Math.abs(entryPrice);
        const maxLoss = premium * 100 * quantity;
        preview.innerHTML = `<div class="risk-preview-line">Max Loss: $${maxLoss.toFixed(2)} (premium paid)</div>`;
    }
}

async function submitUnifiedPosition() {
    const ticker = document.getElementById('upTicker').value.trim().toUpperCase();
    if (!ticker) { alert('Enter a ticker'); return; }

    let structure = document.getElementById('upStructure').value;
    if (structure === 'custom') {
        structure = document.getElementById('upCustomStructure').value.trim().toLowerCase().replace(/\s+/g, '_');
        if (!structure) { alert('Enter a custom structure name'); return; }
    }
    const entryPrice = parseFloat(document.getElementById('upEntryPrice').value);
    if (!entryPrice && entryPrice !== 0) { alert('Enter an entry price/premium'); return; }

    const body = {
        ticker: ticker,
        asset_type: structure === 'stock' ? 'EQUITY' : 'OPTION',
        structure: structure,
        entry_price: entryPrice,
        quantity: parseInt(document.getElementById('upQuantity').value) || 1,
        source: 'MANUAL',
    };

    const longStrike = parseFloat(document.getElementById('upLongStrike').value);
    const shortStrike = parseFloat(document.getElementById('upShortStrike').value);
    const expiry = document.getElementById('upExpiry').value;
    const stopLoss = parseFloat(document.getElementById('upStopLoss').value);
    const target = parseFloat(document.getElementById('upTarget').value);
    const notes = document.getElementById('upNotes').value.trim();

    if (longStrike) body.long_strike = longStrike;
    if (shortStrike) body.short_strike = shortStrike;
    if (expiry) body.expiry = expiry;
    if (stopLoss) body.stop_loss = stopLoss;
    if (target) body.target_1 = target;
    if (notes) body.notes = notes;

    try {
        const response = await fetch(`${API_URL}/v2/positions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        const data = await response.json();

        if (data.status === 'created') {
            document.getElementById('unifiedPositionModal').classList.remove('active');
            await loadOpenPositionsEnhanced();
            addPositionChartTab(ticker);
        } else {
            alert('Failed to create position: ' + (data.detail || JSON.stringify(data)));
        }
    } catch (error) {
        console.error('Error creating position:', error);
        alert('Failed to create position');
    }
}

// ==========================================
// POSITION EDIT MODAL (Brief 10 — C2)
// ==========================================

function openPositionEditModal(position) {
    let modal = document.getElementById('positionEditModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'positionEditModal';
        modal.className = 'signal-modal-overlay';
        modal.innerHTML = `
            <div class="signal-modal">
                <div class="modal-header">
                    <h3 id="editModalTitle">Edit Position</h3>
                    <button class="modal-close" id="closeEditModal">&times;</button>
                </div>
                <div class="modal-body">
                    <div class="form-row">
                        <label>Stop Loss</label>
                        <input type="number" id="editStopLoss" step="0.01">
                    </div>
                    <div class="form-row">
                        <label>Target</label>
                        <input type="number" id="editTarget" step="0.01">
                    </div>
                    <div class="form-row">
                        <label>Current Price</label>
                        <input type="number" id="editCurrentPrice" step="0.01">
                    </div>
                    <div class="form-row">
                        <label>Notes</label>
                        <input type="text" id="editNotes">
                    </div>
                </div>
                <div class="modal-actions">
                    <button class="modal-btn cancel" id="editCancel">Cancel</button>
                    <button class="modal-btn accept" id="editSave">Save</button>
                </div>
            </div>
        `;
        document.body.appendChild(modal);

        document.getElementById('closeEditModal').addEventListener('click', () => modal.classList.remove('active'));
        document.getElementById('editCancel').addEventListener('click', () => modal.classList.remove('active'));
        modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('active'); });
    }

    document.getElementById('editModalTitle').textContent = `Edit ${position.ticker}`;
    document.getElementById('editStopLoss').value = position.stop_loss || '';
    document.getElementById('editTarget').value = position.target_1 || '';
    document.getElementById('editCurrentPrice').value = position.current_price || '';
    document.getElementById('editNotes').value = position.notes || '';

    // Rebind save button
    const saveBtn = document.getElementById('editSave');
    const newSaveBtn = saveBtn.cloneNode(true);
    saveBtn.parentNode.replaceChild(newSaveBtn, saveBtn);
    newSaveBtn.addEventListener('click', async () => {
        const posId = position.position_id || position.id;
        const updates = {};
        const slVal = document.getElementById('editStopLoss').value.trim();
        const tgtVal = document.getElementById('editTarget').value.trim();
        const cpVal = document.getElementById('editCurrentPrice').value.trim();
        const notes = document.getElementById('editNotes').value.trim();
        if (slVal !== '') updates.stop_loss = parseFloat(slVal);
        if (tgtVal !== '') updates.target_1 = parseFloat(tgtVal);
        if (cpVal !== '') updates.current_price = parseFloat(cpVal);
        if (notes) updates.notes = notes;

        if (Object.keys(updates).length === 0) { alert('No changes'); return; }

        try {
            const response = await fetch(`${API_URL}/v2/positions/${posId}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(updates)
            });
            const data = await response.json();
            if (data.status === 'updated') {
                modal.classList.remove('active');
                await loadOpenPositionsEnhanced();
            } else {
                alert('Failed to update: ' + (data.detail || JSON.stringify(data)));
            }
        } catch (error) {
            console.error('Error updating position:', error);
            alert('Failed to update position');
        }
    });

    modal.classList.add('active');
}

// Chart tabs for open positions
function addPositionChartTab(ticker) {
    const tabsContainer = document.getElementById('chartTabs');
    if (!tabsContainer) return;
    
    // Check if tab already exists
    const existing = tabsContainer.querySelector(`[data-symbol="${ticker}"]`);
    if (existing) return;
    
    const tab = document.createElement('button');
    tab.className = 'chart-tab position-tab';
    tab.dataset.symbol = ticker;
    tab.textContent = ticker;
    tab.addEventListener('click', () => changeChartSymbol(ticker));
    
    tabsContainer.appendChild(tab);
}

function removePositionChartTab(ticker) {
    const tabsContainer = document.getElementById('chartTabs');
    if (!tabsContainer) return;
    
    // Don't remove default tabs
    if (['SPY', 'VIX', 'BTCUSD'].includes(ticker)) return;
    
    // Check if any other position still has this ticker
    const stillHasPosition = openPositions.some(p => p.ticker === ticker);
    if (stillHasPosition) return;
    
    const tab = tabsContainer.querySelector(`[data-symbol="${ticker}"]`);
    if (tab && tab.classList.contains('position-tab')) {
        tab.remove();
    }
}

function updatePositionChartTabs() {
    // Add tabs for all open positions
    openPositions.forEach(pos => {
        addPositionChartTab(pos.ticker);
    });
}

// Price updates for real-time P&L
function startPriceUpdates() {
    // Update every 30 seconds
    priceUpdateInterval = setInterval(updateCurrentPrices, 30000);
    // Initial update
    updateCurrentPrices();
}

async function updateCurrentPrices() {
    if (openPositions.length === 0) return;
    
    const tickers = [...new Set(openPositions.map(p => p.ticker))];
    
    for (const ticker of tickers) {
        try {
            // Try to get price from hybrid scanner (it's fast)
            const response = await fetch(`${API_URL}/hybrid/price/${ticker}`);
            const data = await response.json();
            if (data.price) {
                currentPrices[ticker] = data.price;
            }
        } catch (error) {
            // Silently fail - we'll use entry price as fallback
        }
    }
    
    // Re-render with updated prices
    renderPositionsEnhanced();
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initPositionModals, 1300);
    setTimeout(initManualPositionModal, 1400);
    setTimeout(initKnowledgebase, 1500);
});


// ============================================
// MANUAL POSITION ENTRY
// ============================================

function initManualPositionModal() {
    const modal = document.getElementById('manualPositionModal');
    const closeBtn = document.getElementById('closeManualPositionBtn');
    const cancelBtn = document.getElementById('cancelManualPositionBtn');
    const confirmBtn = document.getElementById('confirmManualPositionBtn');
    
    document.querySelectorAll('[data-action="add-manual-position"]').forEach((btn) => {
        btn.addEventListener('click', () => {
            openUnifiedPositionModal();
        });
    });
    
    if (closeBtn) closeBtn.addEventListener('click', closeManualPositionModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeManualPositionModal);
    if (confirmBtn) confirmBtn.addEventListener('click', submitManualPosition);
    
    if (modal) {
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeManualPositionModal();
        });
    }
    
    // Auto-uppercase ticker input
    const tickerInput = document.getElementById('manualTicker');
    if (tickerInput) {
        tickerInput.addEventListener('input', (e) => {
            e.target.value = e.target.value.toUpperCase();
        });
    }
    
    console.log('ðŸ“ Manual position modal initialized');
}

function openManualPositionModal(context = 'equity') {
    const modal = document.getElementById('manualPositionModal');
    const tickerEl = document.getElementById('manualTicker');
    const quantityEl = document.getElementById('manualQuantity');
    const accountEl = document.getElementById('manualAccount');
    const assetClassEl = document.getElementById('manualAssetClass');

    manualPositionContext = (context || 'equity').toLowerCase();

    if (modal) {
        // Clear form
        tickerEl.value = '';
        document.getElementById('manualDirection').value = 'LONG';
        document.getElementById('manualEntryPrice').value = '';
        quantityEl.value = '';
        document.getElementById('manualStopLoss').value = '';
        document.getElementById('manualTarget').value = '';
        document.getElementById('manualNotes').value = '';

        if (manualPositionContext === 'crypto') {
            if (accountEl) accountEl.value = 'BREAKOUT';
            if (assetClassEl) assetClassEl.value = 'CRYPTO';
            if (tickerEl) tickerEl.placeholder = 'BTCUSDT';
            if (quantityEl) {
                quantityEl.step = '0.001';
                quantityEl.placeholder = '0.010';
            }
        } else {
            if (accountEl) accountEl.value = 'MANUAL';
            if (assetClassEl) assetClassEl.value = 'EQUITY';
            if (tickerEl) tickerEl.placeholder = 'AAPL';
            if (quantityEl) {
                quantityEl.step = '1';
                quantityEl.placeholder = '100';
            }
        }
        
        modal.classList.add('active');
        tickerEl.focus();
    }
}

function closeManualPositionModal() {
    const modal = document.getElementById('manualPositionModal');
    if (modal) {
        modal.classList.remove('active');
    }
}

async function submitManualPosition() {
    const ticker = document.getElementById('manualTicker').value.trim().toUpperCase();
    const direction = document.getElementById('manualDirection').value;
    const entryPrice = parseFloat(document.getElementById('manualEntryPrice').value);
    const quantity = parseFloat(document.getElementById('manualQuantity').value);
    const stopLoss = parseFloat(document.getElementById('manualStopLoss').value) || null;
    const target = parseFloat(document.getElementById('manualTarget').value) || null;
    const notes = document.getElementById('manualNotes').value.trim();
    const account = document.getElementById('manualAccount')?.value || (manualPositionContext === 'crypto' ? 'BREAKOUT' : 'MANUAL');
    const selectedAssetClass = document.getElementById('manualAssetClass')?.value || 'EQUITY';
    
    // Validation
    if (!ticker) {
        alert('Please enter a ticker symbol');
        return;
    }
    if (isNaN(entryPrice) || entryPrice <= 0) {
        alert('Please enter a valid entry price');
        return;
    }
    if (isNaN(quantity) || quantity <= 0) {
        alert('Please enter a valid quantity');
        return;
    }
    
    // Determine asset class
    const cryptoTickers = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'AVAX', 'DOGE', 'DOT', 'LINK', 'MATIC', 'LTC', 'UNI'];
    const isCrypto = selectedAssetClass === 'CRYPTO'
        || manualPositionContext === 'crypto'
        || cryptoTickers.some(c => ticker.includes(c));
    const strategy = account === 'BREAKOUT' ? 'Breakout Manual' : 'Manual Entry';
    
    const positionData = {
        ticker: ticker,
        direction: direction,
        entry_price: entryPrice,
        quantity: quantity,
        stop_loss: stopLoss,
        target_1: target,
        strategy: strategy,
        asset_class: isCrypto ? 'CRYPTO' : 'EQUITY',
        signal_type: 'MANUAL',
        notes: notes,
        account: account
    };
    
    try {
        const response = await fetch(`${API_URL}/positions/manual`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(positionData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            console.log('âœ… Manual position created:', result);
            closeManualPositionModal();
            
            // Add to local positions and refresh UI
            if (result.position) {
                openPositions.push(result.position);
                _open_positions_cache.push(result.position);
                renderPositions(openPositions);
                renderCryptoPositions();
                
                // Store price levels for chart
                if (result.position.stop_loss || result.position.target_1) {
                    storePriceLevels(result.position.ticker, {
                        entry_price: result.position.entry_price,
                        stop_loss: result.position.stop_loss,
                        target_1: result.position.target_1
                    });
                }
            }
            
            // Refresh positions from server
            await loadOpenPositionsEnhanced();
        } else {
            alert(`Error: ${result.detail || 'Failed to create position'}`);
        }
    } catch (error) {
        console.error('Error creating manual position:', error);
        alert('Failed to create position. Please try again.');
    }
}

// ============================================
// KNOWLEDGEBASE POPUP FUNCTIONALITY
// ============================================

let kbTermMap = {};
let kbPopupModal = null;

async function initKnowledgebase() {
    // Load term map for making UI terms clickable
    try {
        const response = await fetch(`${API_URL}/knowledgebase/term-map`);
        const data = await response.json();
        kbTermMap = data.termMap || {};
        console.log(`ðŸ“š Loaded ${Object.keys(kbTermMap).length} knowledgebase terms`);
    } catch (error) {
        console.error('Error loading knowledgebase term map:', error);
    }
    
    // Initialize popup modal
    kbPopupModal = document.getElementById('kbPopupModal');
    
    // Close button
    const closeBtn = document.getElementById('closeKbPopupBtn');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeKbPopup);
    }
    
    // Close on backdrop click
    if (kbPopupModal) {
        kbPopupModal.addEventListener('click', (e) => {
            if (e.target === kbPopupModal) closeKbPopup();
        });
    }
    
    // Close on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && kbPopupModal?.classList.contains('active')) {
            closeKbPopup();
        }
    });
    
    // Initialize all KB links and info icons in the page
    initKbClickHandlers();
}

// Initialize click handlers for all KB links and info icons
function initKbClickHandlers() {
    // Handle .kb-link elements (clickable text headers/labels)
    document.querySelectorAll('.kb-link[data-kb-term]').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const termId = el.dataset.kbTerm;
            if (termId) openKbPopup(termId);
        });
    });
    
    // Handle .kb-info-icon elements (â“˜ icons)
    document.querySelectorAll('.kb-info-icon[data-kb-term]').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const termId = el.dataset.kbTerm;
            if (termId) openKbPopup(termId);
        });
    });
    
    // Handle .kb-factor-link elements (clickable factor names in settings modals)
    document.querySelectorAll('.kb-factor-link[data-kb-term]').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const termId = el.dataset.kbTerm;
            if (termId) openKbPopup(termId);
        });
    });
    
    console.log('ðŸ“š KB click handlers initialized');
}

// Map strategy/signal names to KB term IDs
const KB_TERM_MAP = {
    // Strategies
    'TRIPLE_LINE': 'triple-line-trend',
    'TRIPLE LINE': 'triple-line-trend',
    'CTA': 'cta-scanner',
    'CTA_GOLDEN': 'cta-scanner',
    'CTA_TWOCLOSE': 'cta-scanner',
    'CTA_PULLBACK': 'cta-scanner',
    'GOLDEN_TOUCH': 'cta-scanner',
    'GOLDEN TOUCH': 'cta-scanner',
    'TWO_CLOSE': 'cta-scanner',
    'TWO-CLOSE': 'cta-scanner',
    'PULLBACK': 'cta-scanner',
    'HUNTER': 'hunter-scanner',
    'URSA': 'hunter-scanner',
    'TAURUS': 'hunter-scanner',
    'EXHAUSTION': 'trade-ideas',
    'EXHAUSTION_BULL': 'trade-ideas',
    'EXHAUSTION_BEAR': 'trade-ideas',
    
    // Signal types
    'LONG': 'risk-on',
    'SHORT': 'risk-off',
    'BULLISH': 'toro-major',
    'BEARISH': 'ursa-major',
    
    // CTA Zones
    'MAX_LONG': 'max-long',
    'MAX LONG': 'max-long',
    'DE_LEVERAGING': 'de-leveraging',
    'DE-LEVERAGING': 'de-leveraging',
    'DELEVERAGING': 'de-leveraging',
    'WATERFALL': 'waterfall',
    'CAPITULATION': 'capitulation',
    
    // Bias levels
    'TORO_MAJOR': 'toro-major',
    'TORO_MINOR': 'toro-minor',
    'URSA_MAJOR': 'ursa-major',
    'URSA_MINOR': 'ursa-minor',
    'NEUTRAL': 'neutral',
    
    // BTC signals
    '25-DELTA SKEW': 'btc-bottom-signals',
    'QUARTERLY BASIS': 'btc-bottom-signals',
    'PERP FUNDING': 'btc-bottom-signals',
    'STABLECOIN APRS': 'btc-bottom-signals',
    'TERM STRUCTURE': 'btc-bottom-signals',
    'OPEN INTEREST': 'btc-bottom-signals',
    'LIQUIDATION': 'btc-bottom-signals',
    'ORDERBOOK SKEW': 'btc-bottom-signals',
    'VIX SPIKE': 'vix-term-structure',
    
    // Options flow
    'SWEEP': 'trade-ideas',
    'BLOCK': 'trade-ideas',
    'DARK_POOL': 'trade-ideas',
    'UNUSUAL_VOLUME': 'trade-ideas'
};

// Helper to get KB term ID from a name
function getKbTermId(name) {
    if (!name) return null;
    const normalized = name.toUpperCase().trim();
    return KB_TERM_MAP[normalized] || null;
}

// Helper to wrap text with KB link if a mapping exists
function wrapWithKbLink(text, customTermId = null) {
    const termId = customTermId || getKbTermId(text);
    if (termId) {
        return `<span class="kb-term-dynamic" data-kb-term="${termId}">${text}</span>`;
    }
    return text;
}

// Attach click handlers to dynamically created KB links
function attachDynamicKbHandlers(container) {
    if (!container) return;
    container.querySelectorAll('.kb-term-dynamic[data-kb-term]').forEach(el => {
        // Remove existing listener to avoid duplicates
        el.removeEventListener('click', handleDynamicKbClick);
        el.addEventListener('click', handleDynamicKbClick);
    });
}

function handleDynamicKbClick(e) {
    e.preventDefault();
    e.stopPropagation();
    const termId = e.currentTarget.dataset.kbTerm;
    if (termId) openKbPopup(termId);
}

async function openKbPopup(termId) {
    if (!kbPopupModal) return;
    
    try {
        // Load popup data
        const response = await fetch(`${API_URL}/knowledgebase/popup/${termId}`);
        if (!response.ok) throw new Error('Term not found');
        
        const data = await response.json();
        
        // Populate popup
        document.getElementById('kbPopupCategory').textContent = data.category || 'General';
        document.getElementById('kbPopupTitle').textContent = data.term;
        
        // Format short description with paragraphs
        const formattedDesc = formatPopupDescription(data.shortDescription || '');
        document.getElementById('kbPopupBody').innerHTML = formattedDesc;
        
        // Related terms
        const relatedContainer = document.getElementById('kbPopupRelated');
        if (data.relatedTerms && data.relatedTerms.length > 0) {
            let relatedHtml = '<span style="color: var(--text-secondary); font-size: 12px;">Related: </span>';
            data.relatedTerms.slice(0, 4).forEach(relatedId => {
                // Find term name from map
                const termName = Object.keys(kbTermMap).find(k => kbTermMap[k] === relatedId) || relatedId;
                relatedHtml += `<span class="related-tag" data-term-id="${relatedId}">${termName}</span>`;
            });
            relatedContainer.innerHTML = relatedHtml;
            
            // Add click handlers for related terms
            relatedContainer.querySelectorAll('.related-tag').forEach(tag => {
                tag.addEventListener('click', () => {
                    openKbPopup(tag.dataset.termId);
                });
            });
        } else {
            relatedContainer.innerHTML = '';
        }
        
        // More info link
        const moreInfoLink = document.getElementById('kbMoreInfoLink');
        moreInfoLink.href = `/knowledgebase?entry=${termId}`;
        
        // Show modal
        kbPopupModal.classList.add('active');
        
    } catch (error) {
        console.error('Error loading knowledgebase popup:', error);
    }
}

function closeKbPopup() {
    if (kbPopupModal) {
        kbPopupModal.classList.remove('active');
    }
}

function formatPopupDescription(text) {
    if (!text) return '';
    
    // Split by double newlines for paragraphs
    let html = text;
    
    // Bold text
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    
    // Convert newlines to paragraphs
    const paragraphs = html.split('\n\n');
    html = paragraphs.map(p => {
        p = p.trim();
        if (!p) return '';
        // Handle single-line list items
        if (p.startsWith('- ')) {
            return '<p>' + p.replace(/^- /, '- ') + '</p>';
        }
        return '<p>' + p.replace(/\n/g, '<br>') + '</p>';
    }).join('');
    
    return html;
}

// Make a specific term clickable
function makeTermClickable(element, termId) {
    element.classList.add('kb-term');
    element.setAttribute('data-kb-term', termId);
    element.style.cursor = 'pointer';
    element.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        openKbPopup(termId);
    });
}

// Utility function to find and make terms clickable in an element
function linkKnowledgebaseTerms(containerSelector) {
    const container = document.querySelector(containerSelector);
    if (!container) return;
    
    // For each term in our map, find it in the container and make it clickable
    Object.entries(kbTermMap).forEach(([term, id]) => {
        // Skip if term is too short (to avoid matching partial words)
        if (term.length < 4) return;
        
        // Find text nodes containing this term
        const walker = document.createTreeWalker(
            container,
            NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        let node;
        while (node = walker.nextNode()) {
            if (node.nodeValue.includes(term) && !node.parentElement.classList.contains('kb-term')) {
                // Wrap the term in a clickable span
                const regex = new RegExp(`(${escapeRegExp(term)})`, 'gi');
                if (regex.test(node.nodeValue)) {
                    const span = document.createElement('span');
                    span.innerHTML = node.nodeValue.replace(regex, `<span class="kb-term" data-kb-term="${id}">$1</span>`);
                    node.parentNode.replaceChild(span, node);
                }
            }
        }
    });
    
    // Add click handlers
    container.querySelectorAll('.kb-term[data-kb-term]').forEach(el => {
        el.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            openKbPopup(el.dataset.kbTerm);
        });
    });
}

function escapeRegExp(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Export for use in other parts of the app
window.openKbPopup = openKbPopup;
window.makeTermClickable = makeTermClickable;
window.linkKnowledgebaseTerms = linkKnowledgebaseTerms;

// =========================================================================
// OPTIONS POSITION MANAGEMENT
// =========================================================================

let currentLegCount = 1;

function initOptionsTab() {
    // Tab switching for Equities/Options
    document.querySelectorAll('.asset-toggle .toggle-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            const asset = e.target.dataset.asset;
            switchAssetTab(asset);
        });
    });

    // Modal controls
    document.getElementById('openOptionsModalBtn')?.addEventListener('click', openOptionsModal);
    document.getElementById('closeOptionsModalBtn')?.addEventListener('click', closeOptionsModal);
    document.getElementById('cancelOptionsBtn')?.addEventListener('click', closeOptionsModal);
    document.getElementById('saveOptionsBtn')?.addEventListener('click', saveOptionsPosition);
    document.getElementById('addLegBtn')?.addEventListener('click', addLeg);

    // Strategy change updates direction and leg count
    document.getElementById('optStrategy')?.addEventListener('change', onStrategyChange);

    // Set default entry date to today
    const entryDateInput = document.getElementById('optEntryDate');
    if (entryDateInput) {
        entryDateInput.value = new Date().toISOString().split('T')[0];
    }

    // Close modal on overlay click
    const overlay = document.getElementById('optionsModalOverlay');
    if (overlay) {
        overlay.addEventListener('click', (e) => {
            if (e.target === overlay) closeOptionsModal();
        });
    }

    console.log('Options tab initialized');
}

function switchAssetTab(asset) {
    // Update toggle buttons
    document.querySelectorAll('.asset-toggle .toggle-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.asset === asset);
    });

    // Show/hide content
    const equityContent = document.getElementById('tradeSignals');
    const optionsContent = document.getElementById('optionsTabContent');

    if (asset === 'options') {
        if (equityContent) equityContent.style.display = 'none';
        if (optionsContent) optionsContent.style.display = '';
        loadOptionsPositions();
    } else {
        if (equityContent) equityContent.style.display = '';
        if (optionsContent) optionsContent.style.display = 'none';
    }
}

function openOptionsModal() {
    document.getElementById('optionsModalOverlay').style.display = 'flex';
    currentLegCount = 1;
    // Set default entry date
    const entryDateInput = document.getElementById('optEntryDate');
    if (entryDateInput) {
        entryDateInput.value = new Date().toISOString().split('T')[0];
    }
}

function closeOptionsModal() {
    document.getElementById('optionsModalOverlay').style.display = 'none';
    resetOptionsForm();
}

function resetOptionsForm() {
    const fields = ['optUnderlying', 'optNetPremium', 'optMaxProfit', 'optMaxLoss', 'optBreakeven', 'optThesis'];
    fields.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });

    const optStrategy = document.getElementById('optStrategy');
    if (optStrategy) optStrategy.value = 'LONG_CALL';

    const optDirection = document.getElementById('optDirection');
    if (optDirection) optDirection.value = 'BULLISH';

    // Reset to single leg
    const container = document.getElementById('optLegsContainer');
    if (container) {
        container.innerHTML = createLegHTML(1);
    }
    currentLegCount = 1;
}

function onStrategyChange(e) {
    const strategy = e.target.value;
    const directionSelect = document.getElementById('optDirection');

    // Auto-set direction based on strategy
    const directionMap = {
        'LONG_CALL': 'BULLISH',
        'LONG_PUT': 'BEARISH',
        'BULL_CALL_SPREAD': 'BULLISH',
        'BEAR_PUT_SPREAD': 'BEARISH',
        'BULL_PUT_SPREAD': 'BULLISH',
        'BEAR_CALL_SPREAD': 'BEARISH',
        'IRON_CONDOR': 'NEUTRAL',
        'STRADDLE': 'VOLATILITY',
        'STRANGLE': 'VOLATILITY'
    };

    if (directionMap[strategy] && directionSelect) {
        directionSelect.value = directionMap[strategy];
    }

    // Auto-set leg count based on strategy
    const legCountMap = {
        'LONG_CALL': 1,
        'LONG_PUT': 1,
        'BULL_CALL_SPREAD': 2,
        'BEAR_PUT_SPREAD': 2,
        'BULL_PUT_SPREAD': 2,
        'BEAR_CALL_SPREAD': 2,
        'IRON_CONDOR': 4,
        'STRADDLE': 2,
        'STRANGLE': 2,
        'CUSTOM': 1
    };

    const targetLegs = legCountMap[strategy] || 1;
    setLegCount(targetLegs);
}

function setLegCount(count) {
    const container = document.getElementById('optLegsContainer');
    if (!container) return;

    container.innerHTML = '';
    for (let i = 1; i <= count; i++) {
        container.innerHTML += createLegHTML(i);
    }
    currentLegCount = count;
}

function createLegHTML(legNum) {
    return `
        <div class="leg-row" data-leg="${legNum}">
            <div class="leg-header">
                <span class="leg-number">Leg ${legNum}</span>
                ${legNum > 1 ? `<button type="button" class="remove-leg-btn" onclick="removeLeg(${legNum})">X</button>` : ''}
            </div>
            <div class="leg-fields">
                <select class="leg-action form-select-sm">
                    <option value="BUY">BUY</option>
                    <option value="SELL">SELL</option>
                </select>
                <select class="leg-type form-select-sm">
                    <option value="CALL">CALL</option>
                    <option value="PUT">PUT</option>
                </select>
                <input type="number" class="leg-strike form-input-sm" placeholder="Strike" step="0.5">
                <input type="date" class="leg-expiry form-input-sm">
                <input type="number" class="leg-qty form-input-sm" placeholder="Qty" value="1" min="1">
                <input type="number" class="leg-premium form-input-sm" placeholder="Premium" step="0.01">
            </div>
        </div>
    `;
}

function addLeg() {
    currentLegCount++;
    const container = document.getElementById('optLegsContainer');
    if (container) {
        container.innerHTML += createLegHTML(currentLegCount);
    }
}

function removeLeg(legNum) {
    const legRow = document.querySelector(`.leg-row[data-leg="${legNum}"]`);
    if (legRow) {
        legRow.remove();
        currentLegCount--;
        // Renumber remaining legs
        document.querySelectorAll('.leg-row').forEach((row, idx) => {
            row.dataset.leg = idx + 1;
            row.querySelector('.leg-number').textContent = `Leg ${idx + 1}`;
        });
    }
}

async function saveOptionsPosition() {
    const underlying = document.getElementById('optUnderlying')?.value.trim().toUpperCase();
    const strategy = document.getElementById('optStrategy')?.value;
    const direction = document.getElementById('optDirection')?.value;
    const netPremium = parseFloat(document.getElementById('optNetPremium')?.value) || 0;
    const maxProfit = parseFloat(document.getElementById('optMaxProfit')?.value) || null;
    const maxLoss = parseFloat(document.getElementById('optMaxLoss')?.value) || null;
    const breakevenStr = document.getElementById('optBreakeven')?.value;
    const entryDate = document.getElementById('optEntryDate')?.value;
    const thesis = document.getElementById('optThesis')?.value;

    if (!underlying) {
        alert('Please enter an underlying ticker');
        return;
    }

    // Collect legs
    const legs = [];
    document.querySelectorAll('.leg-row').forEach(row => {
        const action = row.querySelector('.leg-action')?.value;
        const optionType = row.querySelector('.leg-type')?.value;
        const strike = parseFloat(row.querySelector('.leg-strike')?.value);
        const expiry = row.querySelector('.leg-expiry')?.value;
        const qty = parseInt(row.querySelector('.leg-qty')?.value) || 1;
        const premium = parseFloat(row.querySelector('.leg-premium')?.value) || 0;

        if (strike && expiry) {
            legs.push({
                action: action,
                option_type: optionType,
                strike: strike,
                expiration: expiry,
                quantity: qty,
                premium: premium
            });
        }
    });

    if (legs.length === 0) {
        alert('Please add at least one leg with strike and expiration');
        return;
    }

    // Parse breakeven
    let breakeven = [];
    if (breakevenStr) {
        breakeven = breakevenStr.split(',').map(b => parseFloat(b.trim())).filter(b => !isNaN(b));
    }

    const payload = {
        underlying: underlying,
        strategy_type: strategy,
        direction: direction,
        legs: legs,
        entry_date: entryDate,
        net_premium: netPremium,
        max_profit: maxProfit,
        max_loss: maxLoss,
        breakeven: breakeven,
        thesis: thesis
    };

    try {
        const response = await fetch(`${API_URL}/options/positions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (data.status === 'success') {
            closeOptionsModal();
            loadOptionsPositions();
            console.log(`Options position added: ${underlying} ${strategy}`);
        } else {
            alert('Error saving position: ' + (data.detail || 'Unknown error'));
        }
    } catch (e) {
        console.error('Error saving options position:', e);
        alert('Error saving position');
    }
}

async function loadOptionsPositions() {
    try {
        const response = await fetch(`${API_URL}/options/positions?status=OPEN`);
        const data = await response.json();

        const positions = data.positions || [];
        renderOptionsPositions(positions);
        updateOptionsSummary(positions);

    } catch (e) {
        console.error('Error loading options positions:', e);
    }
}

function renderOptionsPositions(positions) {
    const container = document.getElementById('optionsPositionsList');
    if (!container) return;

    if (!positions || positions.length === 0) {
        container.innerHTML = '<p class="empty-state">No open options positions</p>';
        return;
    }

    container.innerHTML = positions.map(pos => {
        const metrics = pos.metrics || {};
        const dte = metrics.days_to_expiry;
        const dteClass = dte > 14 ? 'safe' : (dte > 7 ? 'warning' : 'danger');
        const pnl = metrics.unrealized_pnl;
        const pnlClass = pnl > 0 ? 'positive' : (pnl < 0 ? 'negative' : '');

        // Build legs summary
        const legsSummary = pos.legs.map(leg =>
            `${leg.action} ${leg.quantity}x ${leg.strike} ${leg.option_type} ${leg.expiration}`
        ).join(' | ');

        const pnlDisplay = pnl !== null ? ((pnl >= 0 ? '+' : '-') + '$' + Math.abs(pnl).toFixed(2)) : '--';
        const thetaDisplay = metrics.net_theta ? metrics.net_theta.toFixed(2) : '--';

        return `
            <div class="options-position-card" data-position-id="${pos.position_id}">
                <div class="position-header">
                    <div class="position-ticker">
                        <span class="ticker-symbol">${pos.underlying}</span>
                        <span class="strategy-badge ${pos.direction.toLowerCase()}">${pos.strategy_display || pos.strategy_type}</span>
                    </div>
                    <div class="position-dte ${dteClass}">
                        <span class="dte-value">${dte !== null ? dte : '--'}</span>
                        <span class="dte-label">DTE</span>
                    </div>
                </div>
                <div class="position-legs">
                    <span class="legs-summary">${legsSummary}</span>
                </div>
                <div class="position-metrics">
                    <div class="metric">
                        <span class="metric-label">Entry</span>
                        <span class="metric-value">${pos.net_premium >= 0 ? '+' : ''}${pos.net_premium?.toFixed(2) || '0.00'}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">P&L</span>
                        <span class="metric-value ${pnlClass}">${pnlDisplay}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Delta</span>
                        <span class="metric-value">${metrics.net_delta || '--'}</span>
                    </div>
                    <div class="metric">
                        <span class="metric-label">Theta</span>
                        <span class="metric-value">${thetaDisplay}/day</span>
                    </div>
                </div>
                ${pos.thesis ? `<div class="position-thesis">"${pos.thesis}"</div>` : ''}
                <div class="position-actions">
                    <button class="position-btn" onclick="viewPositionDetails('${pos.position_id}')">Details</button>
                    <button class="position-btn" onclick="closeOptionsPosition('${pos.position_id}')">Close</button>
                </div>
            </div>
        `;
    }).join('');
}

function updateOptionsSummary(positions) {
    const countEl = document.getElementById('optionsCount');
    const pnlEl = document.getElementById('optionsTotalPnl');
    const deltaEl = document.getElementById('optionsNetDelta');
    const thetaEl = document.getElementById('optionsDailyTheta');

    if (countEl) countEl.textContent = positions.length;

    let totalPnl = 0;
    let totalDelta = 0;
    let totalTheta = 0;

    positions.forEach(pos => {
        const metrics = pos.metrics || {};
        if (metrics.unrealized_pnl !== null && metrics.unrealized_pnl !== undefined) {
            totalPnl += metrics.unrealized_pnl;
        }
        if (metrics.net_delta) totalDelta += metrics.net_delta;
        if (metrics.net_theta) totalTheta += metrics.net_theta;
    });

    if (pnlEl) {
        pnlEl.textContent = '$' + (totalPnl >= 0 ? '+' : '') + totalPnl.toFixed(2);
        pnlEl.className = 'stat-value ' + (totalPnl >= 0 ? 'positive' : 'negative');
    }

    if (deltaEl) deltaEl.textContent = totalDelta.toFixed(0);
    if (thetaEl) thetaEl.textContent = '$' + totalTheta.toFixed(2);
}

async function viewPositionDetails(positionId) {
    try {
        const response = await fetch(`${API_URL}/options/positions/${positionId}`);
        const data = await response.json();
        console.log('Position details:', data);
        // Could open a detail modal here
    } catch (e) {
        console.error('Error fetching position details:', e);
    }
}

async function closeOptionsPosition(positionId) {
    const exitPremium = prompt('Enter exit premium (positive for credit, negative for debit):');
    if (exitPremium === null) return;

    const outcome = prompt('Outcome? (WIN, LOSS, BREAKEVEN, EXPIRED_WORTHLESS, ASSIGNED)');
    if (!outcome) return;

    try {
        const response = await fetch(`${API_URL}/options/positions/${positionId}/close`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                position_id: positionId,
                exit_premium: parseFloat(exitPremium),
                outcome: outcome.toUpperCase()
            })
        });

        const data = await response.json();

        if (data.status === 'success') {
            loadOptionsPositions();
            console.log(`Position closed - P&L: $${data.realized_pnl?.toFixed(2)}`);
        }
    } catch (e) {
        console.error('Error closing position:', e);
    }
}

// Make functions globally available
window.removeLeg = removeLeg;
window.viewPositionDetails = viewPositionDetails;
window.closeOptionsPosition = closeOptionsPosition;

// Initialize options tab on page load
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initOptionsTab, 1600);
});





