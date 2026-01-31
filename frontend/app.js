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

// Cyclical Bias Factor State
let cyclicalBiasFullData = null;
let cyclicalBiasFactorStates = {
    sma_200_positions: true,
    yield_curve: true,
    credit_spreads: true,
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
    
    // Update price levels panel for this symbol
    updatePriceLevelsPanel(symbol);
    
    // Reinitialize widget with new symbol
    initTradingViewWidget();
}

function updatePriceLevelsPanel(symbol) {
    const panel = document.getElementById('priceLevelsPanel');
    if (!panel) return;
    
    // Check if we have price levels for this symbol
    const levels = window.activePriceLevels?.[symbol];
    
    if (levels) {
        // Show panel with levels
        panel.style.display = 'block';
        document.getElementById('priceLevelsTicker').textContent = symbol;
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
        const position = openPositions.find(p => p.ticker === symbol);
        if (position) {
            panel.style.display = 'block';
            document.getElementById('priceLevelsTicker').textContent = symbol;
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
            break;
        case 'POSITION_UPDATE':
            updatePosition(message.data);
            break;
    }
}

function handleNewSignal(signalData) {
    // Add to appropriate signal list
    if (signalData.asset_class === 'EQUITY' || !signalData.asset_class) {
        // Check if this signal should jump into top 10
        const currentLowestScore = getLowestDisplayedScore();
        const newScore = signalData.score || 0;
        
        if (newScore > currentLowestScore || signals.equity.length < 10) {
            // Insert at correct position based on score
            insertSignalByScore(signalData, 'equity');
            renderSignals();
            
            // Highlight new signal with animation
            highlightNewSignal(signalData.signal_id);
        } else {
            // Add to queue but don't display
            signals.equity.push(signalData);
        }
    } else {
        signals.crypto.push(signalData);
        renderSignals();
    }
}

function handlePrioritySignal(signalData) {
    // High-priority signal - insert at top with animation
    console.log('🔥 Priority signal received:', signalData.ticker, signalData.score);
    
    if (signalData.asset_class === 'EQUITY' || !signalData.asset_class) {
        // Remove if already exists
        signals.equity = signals.equity.filter(s => s.signal_id !== signalData.signal_id);
        // Insert at top (newest signals always first)
        signals.equity.unshift(signalData);
    }
    
    renderSignals();
    highlightNewSignal(signalData.signal_id);
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
    
    // Hybrid Scanner
    initHybridScanner();
    
    // Bias Factor Settings Modals
    initWeeklyBiasSettings();
    initDailyBiasSettings();
    initCyclicalBiasSettings();
    
    // Savita Update Modal
    initSavitaUpdateModal();
    
    // Personal Bias & Override Controls
    initPersonalBiasControls();
}

// Data Loading
async function loadInitialData() {
    await Promise.all([
        loadSignals(),
        loadBiasData(),
        loadOpenPositions()
    ]);
    
    // Set up auto-refresh for bias shift status every 5 minutes
    setInterval(() => {
        fetchBiasShiftStatus();
    }, 5 * 60 * 1000); // 5 minutes
}

async function loadSignals() {
    try {
        const response = await fetch(`${API_URL}/signals/active`);
        const data = await response.json();
        
        console.log('📡 Loaded signals:', data);
        
        if (data.status === 'success' && data.signals) {
            // Separate equity and crypto signals (be more flexible with asset_class matching)
            const cryptoTickers = ['BTC', 'ETH', 'SOL', 'XRP', 'ADA', 'AVAX', 'DOGE', 'DOT', 'LINK', 'MATIC', 'LTC', 'UNI'];
            
            signals.equity = data.signals.filter(s => {
                // If explicitly marked as EQUITY
                if (s.asset_class === 'EQUITY') return true;
                // If no asset_class but ticker doesn't look like crypto
                if (!s.asset_class) {
                    const tickerBase = (s.ticker || '').toUpperCase().replace(/USD.*/, '');
                    return !cryptoTickers.includes(tickerBase);
                }
                return false;
            });
            
            signals.crypto = data.signals.filter(s => {
                // If explicitly marked as CRYPTO
                if (s.asset_class === 'CRYPTO') return true;
                // If no asset_class but ticker looks like crypto
                if (!s.asset_class) {
                    const tickerBase = (s.ticker || '').toUpperCase().replace(/USD.*/, '');
                    return cryptoTickers.includes(tickerBase);
                }
                return false;
            });
            
            console.log(`📊 Signals loaded: ${signals.equity.length} equity, ${signals.crypto.length} crypto`);
            console.log('🪙 Crypto signals:', signals.crypto);
            
            // Force render signals with a small delay to ensure DOM is ready
            setTimeout(() => renderSignals(), 100);
        } else {
            console.warn('No signals in response or error:', data);
        }
    } catch (error) {
        console.error('Error loading signals:', error);
    }
}

async function loadBiasData() {
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
}

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
    
    const cyclicalBullish = isBullishBias(cyclicalLevel);
    const cyclicalBearish = isBearishBias(cyclicalLevel);
    const weeklyBullish = isBullishBias(weeklyLevel);
    const weeklyBearish = isBearishBias(weeklyLevel);
    
    // Check alignment
    if (cyclicalBullish && weeklyBullish) {
        container.classList.add('bias-aligned-bullish');
        if (alignmentText) alignmentText.textContent = 'BULLISH ALIGNED';
        console.log('Bias alignment: BULLISH (Cyclical + Weekly both bullish)');
    } else if (cyclicalBearish && weeklyBearish) {
        container.classList.add('bias-aligned-bearish');
        if (alignmentText) alignmentText.textContent = 'BEARISH ALIGNED';
        console.log('Bias alignment: BEARISH (Cyclical + Weekly both bearish)');
    } else {
        // Not aligned - no outline
        if (alignmentText) alignmentText.textContent = 'MIXED';
        console.log('Bias alignment: MIXED (Cyclical and Weekly not aligned)');
    }
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
                        currentInfo.innerHTML = `<strong>⚠️ DISABLED (${daysSince}d old)</strong> - Savita not affecting score until updated`;
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
                trendIcon = '↑';
                trendText = `vs ${(previousLevel || 'N/A').replace('_', ' ')}`;
                break;
            case 'DECLINING':
                trendIcon = '↓';
                trendText = `vs ${(previousLevel || 'N/A').replace('_', ' ')}`;
                break;
            case 'STABLE':
                trendIcon = '→';
                trendText = 'unchanged';
                break;
            default:
                trendIcon = '•';
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
        
        detailsElement.innerHTML = `
            <span class="trend-indicator trend-${trend.toLowerCase()}">${trendIcon}</span> ${trendText}
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
    const totalFactors = 6;
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
    updateWarningBadge(enabledCount);
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
        console.log('🔄 New day detected - reset all weekly bias factors to enabled');
    }
}

// Load factor states from localStorage
function loadFactorStatesFromStorage() {
    const stored = localStorage.getItem('weeklyBiasFactors');
    if (stored) {
        try {
            weeklyBiasFactorStates = JSON.parse(stored);
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
function updateWarningBadge(enabledCount, timeframe = 'weekly') {
    const levelElement = document.getElementById(`${timeframe}Level`);
    if (!levelElement) return;
    
    // Remove existing warning badge
    const existingBadge = levelElement.querySelector('.bias-warning-badge');
    if (existingBadge) {
        existingBadge.remove();
    }
    
    // Add warning if not all factors enabled
    if (enabledCount < 6) {
        const badge = document.createElement('span');
        badge.className = 'bias-warning-badge';
        badge.textContent = '⚠️';
        badge.title = `${enabledCount} of 6 factors active`;
        levelElement.appendChild(badge);
    }
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
    const totalFactors = 7;  // Updated to 7 to include TICK Breadth
    const scaleFactor = enabledCount / totalFactors;
    const majorThreshold = Math.round(8 * scaleFactor);  // Adjusted for 7 factors
    const minorThreshold = Math.round(4 * scaleFactor);  // Adjusted for 7 factors
    
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
    updateWarningBadge(enabledCount, 'daily');
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
    const totalFactors = 6;
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
    updateWarningBadge(enabledCount, 'cyclical');
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
            renderSignals();
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
            renderSignals();
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

function saveCyclicalFactorStatesToStorage() {
    localStorage.setItem('cyclicalBiasFactors', JSON.stringify(cyclicalBiasFactorStates));
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
            shiftIcon = '▲';
            shiftClass = 'bias-shift-improving';
            shiftText = shiftDirection === 'STRONGLY_IMPROVING' ? 'strongly improving' : 'improving';
            break;
        case 'DETERIORATING':
        case 'STRONGLY_DETERIORATING':
            shiftIcon = '▼';
            shiftClass = 'bias-shift-deteriorating';
            shiftText = shiftDirection === 'STRONGLY_DETERIORATING' ? 'strongly deteriorating' : 'deteriorating';
            break;
        case 'STABLE':
        default:
            shiftIcon = '—';
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
                    Vote: ${totalVote}/12 • Long-term macro<br>
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
    
    // Attach KB link handlers to dynamically created content
    attachDynamicKbHandlers(container);
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
    const biasAlignmentIcon = isAligned ? '✓' : (biasAlignment.includes('COUNTER') ? '⚠' : '○');
    const biasAlignmentText = biasAlignment.replace('_', ' ');
    
    // Safe number formatting
    const formatPrice = (val) => val ? parseFloat(val).toFixed(2) : '-';
    const formatRR = (val) => val ? `${parseFloat(val).toFixed(1)}:1` : '-';
    
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
    
    return `
        <div class="signal-card ${signal.signal_type || ''} ${biasAlignmentClass} ${pulseClass}" 
             data-signal-id="${signal.signal_id}" 
             data-signal='${JSON.stringify(signal).replace(/'/g, "&#39;")}'>
            
            <div class="signal-header">
                <div>
                    <div class="signal-type ${signal.signal_type || ''}">${typeWithKb}</div>
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
                <button class="action-btn dismiss-btn" data-action="dismiss">✕ Dismiss</button>
                <button class="action-btn select-btn" data-action="select">✓ Accept</button>
            </div>
        </div>
    `;
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
    
    if (action === 'SELECT') {
        // Open position entry modal instead of directly selecting
        const signal = JSON.parse(card.dataset.signal.replace(/&#39;/g, "'"));
        openPositionEntryModal(signal, card);
        return;
    }
    
    if (action === 'DISMISS') {
        // Open dismiss modal with reason selection
        const signal = JSON.parse(card.dataset.signal.replace(/&#39;/g, "'"));
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
    modal.className = 'signal-modal-overlay';
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
            
            // Re-render
            renderSignals();
            
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

let watchlistSectors = {};
let sectorStrength = {};

async function loadWatchlist() {
    try {
        const response = await fetch(`${API_URL}/watchlist`);
        const data = await response.json();
        
        if (data.status === 'success') {
            watchlistTickers = data.tickers || [];
            watchlistSectors = data.sectors || {};
            sectorStrength = data.sector_strength || {};
            renderWatchlist();
        }
    } catch (error) {
        console.error('Error loading watchlist:', error);
        document.getElementById('watchlistTickers').innerHTML = 
            '<p class="empty-state">Failed to load watchlist</p>';
    }
}

async function renderWatchlist() {
    const container = document.getElementById('watchlistTickers');
    const countEl = document.getElementById('watchlistCount');

    if (!container) return;

    countEl.textContent = watchlistTickers.length;

    if (watchlistTickers.length === 0) {
        container.innerHTML = '<p class="empty-state">No tickers in watchlist</p>';
        return;
    }

    // Show loading state
    container.innerHTML = '<p class="empty-state">Loading prices...</p>';

    try {
        // Fetch prices and signals in parallel
        const pricePromises = watchlistTickers.map(ticker =>
            fetch(`${API_URL}/hybrid/price/${ticker}`)
                .then(r => r.json())
                .then(data => ({ ticker, price: data.price, change_pct: data.change_pct }))
                .catch(() => ({ ticker, price: null, change_pct: null }))
        );

        const signalsResponse = await fetch(`${API_URL}/signals/active`);
        const signalsData = await signalsResponse.json();
        const activeSignals = signalsData.signals || [];

        const priceData = await Promise.all(pricePromises);

        // Build card-based HTML
        let html = '<div class="watchlist-cards">';

        for (const data of priceData) {
            const ticker = data.ticker;
            const price = data.price;
            const changePct = data.change_pct;

            // Find active signals for this ticker
            const tickerSignals = activeSignals.filter(s => s.ticker === ticker);

            let signalBadges = '';
            tickerSignals.forEach(signal => {
                const badgeClass = signal.direction === 'LONG' ? 'signal-badge-long' : 'signal-badge-short';
                signalBadges += `<span class="signal-badge ${badgeClass}">${signal.direction}</span>`;
            });

            const changeClass = changePct >= 0 ? 'price-up' : 'price-down';
            const changeSign = changePct >= 0 ? '+' : '';

            html += `
                <div class="watchlist-ticker-card" data-ticker="${ticker}">
                    <div class="ticker-main">
                        <div class="ticker-symbol">${ticker}</div>
                        <div class="ticker-signals">${signalBadges || '<span class="no-signal">—</span>'}</div>
                    </div>
                    <div class="ticker-price">
                        <div class="current-price">${price ? `$${price.toFixed(2)}` : '—'}</div>
                        <div class="price-change ${changeClass}">
                            ${changePct !== null ? `${changeSign}${changePct.toFixed(2)}%` : '—'}
                        </div>
                    </div>
                    <div class="ticker-actions">
                        <button class="ticker-action-btn analyze" data-ticker="${ticker}" title="Analyze">🔬</button>
                        <button class="ticker-action-btn chart" data-ticker="${ticker}" title="Chart">📊</button>
                        <button class="ticker-action-btn remove" data-ticker="${ticker}" title="Remove">✕</button>
                    </div>
                </div>
            `;
        }

        html += '</div>';
        container.innerHTML = html;

        // Attach event listeners
        container.querySelectorAll('.ticker-action-btn.analyze').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const ticker = e.target.dataset.ticker;
                analyzeTicker(ticker);
            });
        });

        container.querySelectorAll('.ticker-action-btn.chart').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const ticker = e.target.dataset.ticker;
                showChart(ticker);
            });
        });

        container.querySelectorAll('.ticker-action-btn.remove').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const ticker = e.target.dataset.ticker;
                removeFromWatchlist(ticker);
            });
        });

    } catch (error) {
        console.error('Error rendering watchlist:', error);
        container.innerHTML = '<p class="empty-state">Error loading watchlist</p>';
    }
}

// Helper functions for watchlist actions
function analyzeTicker(ticker) {
    // Populate the analyzer input and trigger analysis
    const input = document.getElementById('analyzeTickerInput');
    const btn = document.getElementById('analyzeTickerBtn');

    if (input && btn) {
        input.value = ticker;
        btn.click();
    }
}

function showChart(ticker) {
    changeChartSymbol(ticker);
}

function removeFromWatchlist(ticker) {
    removeTickerFromWatchlist(ticker);
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
    const gaugesContainer = document.getElementById('analyzerGauges');
    const aggregateContainer = document.getElementById('analyzerAggregate');
    const ticker = input.value.trim().toUpperCase();
    
    if (!ticker) return;
    
    resultsContainer.innerHTML = '<p class="empty-state">Analyzing...</p>';
    if (gaugesContainer) gaugesContainer.style.display = 'none';
    if (aggregateContainer) aggregateContainer.style.display = 'none';
    
    try {
        // Fetch Hunter analysis, CTA analysis, Hybrid gauges, and current bias in parallel
        const [hunterResponse, ctaResponse, hybridResponse, biasResponse] = await Promise.all([
            fetch(`${API_URL}/scanner/analyze/${ticker}`),
            fetch(`${API_URL}/cta/analyze/${ticker}`),
            fetch(`${API_URL}/hybrid/combined/${ticker}`),
            fetch(`${API_URL}/bias-auto/status`)
        ]);
        
        const hunterData = await hunterResponse.json();
        const ctaData = await ctaResponse.json();
        const hybridData = await hybridResponse.json();
        const biasData = await biasResponse.json();
        
        // Merge CTA analysis into Hunter data for unified display
        if (ctaData && ctaData.cta_analysis) {
            hunterData.cta_analysis = ctaData.cta_analysis;
        }
        
        // Render ticker info/metrics (now includes CTA data)
        renderAnalyzerResults(hunterData);
        
        // Render Hybrid gauges (Technical + Analyst)
        if (hybridData.status === 'success') {
            renderHybridAnalysis(hybridData);
            if (gaugesContainer) gaugesContainer.style.display = 'flex';
        }
        
        // Calculate and render aggregate verdict with bias alignment
        renderAggregateVerdict(ticker, hunterData, hybridData, biasData);

        // Populate enhanced context cards
        await analyzeTickerEnhanced(ticker);

        // Also switch chart to this ticker
        changeChartSymbol(ticker);
        
    } catch (error) {
        console.error('Error analyzing ticker:', error);
        resultsContainer.innerHTML = '<p class="empty-state">Analysis failed</p>';
    }
}

function renderAggregateVerdict(ticker, hunterData, hybridData, biasData) {
    const container = document.getElementById('analyzerAggregate');
    if (!container) return;
    
    // Calculate aggregate score from all sources
    let totalScore = 0;
    let maxScore = 0;
    
    // 1. Technical Gauge Score (weight: 3)
    const techSignal = hybridData?.technical_gauge?.signal || '';
    const techScore = hybridData?.technical_gauge?.score || {};
    if (techSignal) {
        maxScore += 3;
        if (techSignal.includes('STRONG_BUY')) totalScore += 3;
        else if (techSignal.includes('BUY')) totalScore += 2;
        else if (techSignal.includes('STRONG_SELL')) totalScore -= 3;
        else if (techSignal.includes('SELL')) totalScore -= 2;
        // Neutral = 0
    }
    
    // 2. Analyst Gauge Score (weight: 2)
    const analystConsensus = hybridData?.analyst_gauge?.consensus || '';
    const analystUpside = hybridData?.analyst_gauge?.upside_pct || 0;
    if (analystConsensus) {
        maxScore += 2;
        if (analystConsensus.toLowerCase().includes('strong_buy') || analystConsensus.toLowerCase() === 'buy') {
            totalScore += 2;
        } else if (analystConsensus.toLowerCase().includes('hold')) {
            totalScore += 0;
        } else if (analystConsensus.toLowerCase().includes('sell')) {
            totalScore -= 2;
        }
    }
    // Analyst upside bonus (weight: 1)
    if (analystUpside !== null && analystUpside !== undefined) {
        maxScore += 1;
        if (analystUpside > 15) totalScore += 1;
        else if (analystUpside < -10) totalScore -= 1;
    }
    
    // 3. Hunter/CTA Analysis Score (weight: 2)
    const hunterVerdict = hunterData?.overall_verdict || '';
    const ctaZone = hunterData?.cta_analysis?.cta_zone || '';
    if (hunterVerdict) {
        maxScore += 2;
        if (hunterVerdict === 'TAURUS_SIGNAL') totalScore += 2;
        else if (hunterVerdict === 'URSA_SIGNAL') totalScore -= 2;
    }
    // CTA Zone bonus
    if (ctaZone) {
        maxScore += 1;
        if (ctaZone === 'MAX_LONG') totalScore += 1;
        else if (ctaZone === 'CAPITULATION' || ctaZone === 'WATERFALL') totalScore -= 1;
    }
    
    // 4. Price vs Weighted SMAs (swing-trade weighted: SMA50 > SMA200 > SMA20)
    const metrics = hunterData?.current_metrics || {};
    const ctaAnalysis = hunterData?.cta_analysis || {};
    const price = metrics.price;
    const sma20 = ctaAnalysis.sma20 || metrics.sma20;
    const sma50 = ctaAnalysis.sma50 || metrics.sma50;
    const sma200 = ctaAnalysis.sma200 || metrics.sma_200;
    
    // Weighted SMA scoring for swing trades:
    // SMA 50 (medium-term): weight 1.0 - most important for swing trades
    // SMA 200 (long-term): weight 0.5 - macro trend confirmation  
    // SMA 20 (short-term): weight 0.5 - entry timing
    if (price) {
        if (sma50) {
            maxScore += 1;
            totalScore += price > sma50 ? 1 : -1;
        }
        if (sma200) {
            maxScore += 0.5;
            totalScore += price > sma200 ? 0.5 : -0.5;
        }
        if (sma20) {
            maxScore += 0.5;
            totalScore += price > sma20 ? 0.5 : -0.5;
        }
    }
    
    // Force non-neutral: if score is exactly 0, use technical tiebreaker
    if (totalScore === 0 && techScore.buy !== undefined) {
        totalScore = (techScore.buy > techScore.sell) ? 0.5 : -0.5;
    }
    
    // Determine verdict level (6-level system like bias)
    const scorePercent = maxScore > 0 ? (totalScore / maxScore) * 100 : 0;
    let verdict, verdictClass;
    
    if (scorePercent >= 50) {
        verdict = 'MAJOR TORO';
        verdictClass = 'major-toro';
    } else if (scorePercent >= 25) {
        verdict = 'MINOR TORO';
        verdictClass = 'minor-toro';
    } else if (scorePercent > 0) {
        verdict = 'LEAN TORO';
        verdictClass = 'lean-toro';
    } else if (scorePercent <= -50) {
        verdict = 'MAJOR URSA';
        verdictClass = 'major-ursa';
    } else if (scorePercent <= -25) {
        verdict = 'MINOR URSA';
        verdictClass = 'minor-ursa';
    } else {
        verdict = 'LEAN URSA';
        verdictClass = 'lean-ursa';
    }
    
    // Get bias levels for swing trade alignment (Weekly weighted more than Daily for swing trades)
    const dailyBias = biasData?.data?.daily?.level || '';
    const weeklyBias = biasData?.data?.weekly?.level || '';
    const cyclicalBias = biasData?.data?.cyclical?.level || '';
    
    // Convert 1-6 scale to -2.5 to +2.5 scale for weighted average
    // 6 (MAJOR_TORO) = +2.5, 5 = +1.5, 4 = +0.5, 3 = -0.5, 2 = -1.5, 1 (MAJOR_URSA) = -2.5
    const toSwingScore = (level) => {
        const val = getBiasValue(level);
        return (val - 3.5); // Converts 1-6 to -2.5 to +2.5
    };
    
    // Calculate weighted swing bias: Weekly 50%, Daily 30%, Cyclical 20%
    let swingBiasScore = 0;
    let biasAvailable = false;
    let totalWeight = 0;
    
    if (weeklyBias) {
        biasAvailable = true;
        swingBiasScore += toSwingScore(weeklyBias) * 0.5;
        totalWeight += 0.5;
    }
    if (dailyBias) {
        biasAvailable = true;
        swingBiasScore += toSwingScore(dailyBias) * 0.3;
        totalWeight += 0.3;
    }
    if (cyclicalBias) {
        biasAvailable = true;
        swingBiasScore += toSwingScore(cyclicalBias) * 0.2;
        totalWeight += 0.2;
    }
    
    // Normalize if not all biases available
    if (totalWeight > 0 && totalWeight < 1) {
        swingBiasScore = swingBiasScore / totalWeight;
    }
    
    // Determine swing bias level from weighted score (-2.5 to +2.5 scale)
    let swingBiasLevel;
    if (swingBiasScore >= 2) swingBiasLevel = 'MAJOR_TORO';
    else if (swingBiasScore >= 1) swingBiasLevel = 'MINOR_TORO';
    else if (swingBiasScore > 0) swingBiasLevel = 'LEAN_TORO';
    else if (swingBiasScore <= -2) swingBiasLevel = 'MAJOR_URSA';
    else if (swingBiasScore <= -1) swingBiasLevel = 'MINOR_URSA';
    else swingBiasLevel = 'LEAN_URSA';
    
    const isToro = verdict.includes('TORO');
    const biasIsToro = swingBiasLevel.includes('TORO');
    
    let alignmentStatus, alignmentClass;
    if (!biasAvailable) {
        alignmentStatus = 'Bias loading...';
        alignmentClass = 'unknown';
    } else if (isToro === biasIsToro) {
        alignmentStatus = `✅ ALIGNED (${swingBiasLevel.replace('_', ' ')})`;
        alignmentClass = 'aligned';
    } else {
        alignmentStatus = `⚠️ DIVERGENT (${swingBiasLevel.replace('_', ' ')})`;
        alignmentClass = 'divergent';
    }
    
    // Update UI
    document.getElementById('aggregateTicker').textContent = ticker;
    
    const signalEl = document.getElementById('aggregateSignal');
    signalEl.textContent = verdict;
    signalEl.className = `aggregate-signal ${verdictClass}`;
    
    document.getElementById('aggregateScore').textContent = `Score: ${totalScore > 0 ? '+' : ''}${totalScore.toFixed(1)} / ${maxScore}`;
    
    const alignmentEl = document.getElementById('biasAlignmentStatus');
    alignmentEl.textContent = alignmentStatus;
    alignmentEl.className = `alignment-status ${alignmentClass}`;
    
    // Update container class for styling
    const verdictContainer = document.getElementById('aggregateVerdict');
    verdictContainer.className = `aggregate-verdict ${verdictClass}`;
    
    container.style.display = 'flex';
}

function renderAnalyzerResults(data) {
    const container = document.getElementById('analyzerResults');
    
    if (!container) return;
    
    if (data.error) {
        container.innerHTML = `<p class="empty-state">${data.error}</p>`;
        return;
    }
    
    const metrics = data.current_metrics || {};
    const ursaCriteria = data.criteria_breakdown?.ursa_bearish || {};
    const taurusCriteria = data.criteria_breakdown?.taurus_bullish || {};
    const ctaAnalysis = data.cta_analysis || {};
    
    // CTA Zone info for display
    const ctaZone = ctaAnalysis.cta_zone || 'N/A';
    const ctaBias = ctaAnalysis.bias || '';
    
    // Get SMA values from CTA analysis (primary) or metrics (fallback)
    const sma20 = ctaAnalysis.sma20 ?? metrics.sma20 ?? null;
    const sma50 = ctaAnalysis.sma50 ?? metrics.sma50 ?? null;
    const sma120 = ctaAnalysis.sma120 ?? null;
    const sma200 = ctaAnalysis.sma200 ?? metrics.sma_200 ?? null;
    
    // Wrap CTA zone with KB link
    const ctaZoneWithKb = wrapWithKbLink(ctaZone) || ctaZone;
    
    let html = `
        <div class="analyzer-metrics">
            <div class="analyzer-metric">
                <div class="analyzer-metric-label">Price</div>
                <div class="analyzer-metric-value">$${metrics.price?.toFixed(2) ?? '-'}</div>
            </div>
            <div class="analyzer-metric">
                <div class="analyzer-metric-label">SMA 20</div>
                <div class="analyzer-metric-value">${sma20 ? '$' + sma20.toFixed(2) : '-'}</div>
            </div>
            <div class="analyzer-metric">
                <div class="analyzer-metric-label">SMA 50</div>
                <div class="analyzer-metric-value">${sma50 ? '$' + sma50.toFixed(2) : '-'}</div>
            </div>
            <div class="analyzer-metric">
                <div class="analyzer-metric-label"><span class="kb-term-dynamic" data-kb-term="cta-scanner">CTA Zone</span></div>
                <div class="analyzer-metric-value zone-${ctaZone.toLowerCase().replace(' ', '-')}">${ctaZoneWithKb}</div>
            </div>
            <div class="analyzer-metric">
                <div class="analyzer-metric-label"><span class="kb-term-dynamic" data-kb-term="rsi">RSI</span></div>
                <div class="analyzer-metric-value">${metrics.rsi?.toFixed(1) ?? '-'}</div>
            </div>
            <div class="analyzer-metric">
                <div class="analyzer-metric-label">ADX</div>
                <div class="analyzer-metric-value">${metrics.adx?.toFixed(1) ?? '-'}</div>
            </div>
            <div class="analyzer-metric">
                <div class="analyzer-metric-label">RVOL</div>
                <div class="analyzer-metric-value">${metrics.rvol?.toFixed(2) ?? '-'}x</div>
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
    const hunterVerdict = data.overall_verdict || 'NO_SIGNAL';
    if (hunterVerdict === 'NO_SIGNAL' && data.near_miss) {
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
    
    // Attach KB handlers to dynamically created links
    attachDynamicKbHandlers(container);
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
                    <div class="cta-metric-value">${setup.rr_ratio || '-'}:1</div>
                </div>
            </div>
            <div class="cta-card-footer">
                Zone: ${zoneWithKb} • Vol: ${context.volume_ratio?.toFixed(1) || '-'}x
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
            longAlignment.textContent = dailyIsToro ? '✅ Aligned' : '⚠️ Divergent';
            longAlignment.className = 'alignment-status ' + (dailyIsToro ? 'aligned' : 'divergent');
        }

        if (shortAlignment) {
            shortAlignment.textContent = !dailyIsToro ? '✅ Aligned' : '⚠️ Divergent';
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
                        ${f.sentiment === 'BULLISH' ? '🟢' : '🔴'} ${f.type}
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
                addTickerToWatchlist();
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

function initBtcSignals() {
    const refreshBtn = document.getElementById('refreshBtcSignalsBtn');
    const resetBtn = document.getElementById('resetBtcSignalsBtn');
    
    if (refreshBtn) {
        // Force refresh fetches fresh data from APIs
        refreshBtn.addEventListener('click', refreshBtcSignals);
    }
    
    if (resetBtn) {
        resetBtn.addEventListener('click', resetBtcSignals);
    }
    
    // Initial load
    loadBtcSignals();
    loadBtcSessions();
    
    // Auto-refresh every 5 minutes
    setInterval(loadBtcSignals, 5 * 60 * 1000);
}

async function loadBtcSignals() {
    try {
        const response = await fetch(`${API_URL}/btc/bottom-signals`);
        const data = await response.json();
        
        btcSignals = data.signals || {};
        btcConfluence = data.confluence || {};
        btcRawData = data.raw_data || {};
        btcApiStatus = data.api_status || {};
        
        renderBtcSignals();
        renderBtcSummary();
        renderBtcApiStatus();
        
    } catch (error) {
        console.error('Error loading BTC signals:', error);
        document.getElementById('btcSignalsGrid').innerHTML = 
            '<p class="empty-state">Failed to load signals</p>';
    }
}

async function refreshBtcSignals() {
    const refreshBtn = document.getElementById('refreshBtcSignalsBtn');
    if (refreshBtn) {
        refreshBtn.disabled = true;
        refreshBtn.textContent = 'Refreshing...';
    }
    
    try {
        const response = await fetch(`${API_URL}/btc/bottom-signals/refresh`, {
            method: 'POST'
        });
        const data = await response.json();
        
        btcSignals = data.signals || {};
        btcConfluence = data.confluence || {};
        btcRawData = data.raw_data || {};
        btcApiStatus = data.api_status || {};
        
        renderBtcSignals();
        renderBtcSummary();
        renderBtcApiStatus();
        
    } catch (error) {
        console.error('Error refreshing BTC signals:', error);
    } finally {
        if (refreshBtn) {
            refreshBtn.disabled = false;
            refreshBtn.textContent = 'Refresh All';
        }
    }
}

function renderBtcSummary() {
    const container = document.getElementById('btcConfluenceSummary');
    if (!container) return;
    
    const firingCount = btcConfluence.firing || 0;
    const totalSignals = btcConfluence.total || 9;
    const verdict = btcConfluence.verdict || 'Checking signals...';
    const verdictLevel = btcConfluence.verdict_level || 'none';
    
    container.innerHTML = `
        <div class="confluence-meter">
            <span class="confluence-count">${firingCount}/${totalSignals}</span>
            <span class="confluence-label">Signals Firing</span>
        </div>
        <div class="confluence-verdict ${verdictLevel}">${verdict}</div>
    `;
}

function renderBtcApiStatus() {
    const container = document.getElementById('btcApiStatus');
    if (!container) return;
    
    const apis = [
        { key: 'coinalyze', name: 'Coinalyze', signals: 'Funding, OI, Liqs, Term' },
        { key: 'deribit', name: 'Deribit', signals: '25d Skew' },
        { key: 'defillama', name: 'DeFiLlama', signals: 'Stablecoin APR' },
        { key: 'binance', name: 'Binance', signals: 'Orderbook, Basis' },
        { key: 'yfinance', name: 'yfinance', signals: 'VIX' }
    ];
    
    container.innerHTML = apis.map(api => {
        const status = btcApiStatus[api.key] ? 'connected' : 'disconnected';
        return `
            <span class="api-status-item ${status}" title="${api.signals}">
                ${api.name}: ${status === 'connected' ? 'OK' : 'OFF'}
            </span>
        `;
    }).join('');
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
        
        // Source indicator
        const sourceIcon = isAuto ? '⚡' : '✋';
        const sourceLabel = isAuto ? 'AUTO' : 'MANUAL';
        
        // Value display - use raw value if available and detailed
        const rawData = btcRawData[id] || {};
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
                <div class="btc-signal-footer">
                    <span class="btc-signal-source ${isAuto ? 'auto' : 'manual'}">${sourceIcon} ${sourceLabel}</span>
                    <span class="btc-signal-timestamp">${timestamp}</span>
                </div>
                ${hasManualOverride ? '<div class="manual-override-badge">Override Active</div>' : ''}
            </div>
        `;
    }).join('');
    
    // Attach KB handlers
    attachDynamicKbHandlers(container);
    
    // Attach click events for manual override toggle
    container.querySelectorAll('.btc-signal-card').forEach(card => {
        card.addEventListener('click', (e) => {
            // Don't toggle if clicking a KB link
            if (e.target.classList.contains('kb-term-dynamic')) return;
            toggleBtcSignal(card.dataset.signalId);
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
/*
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
*/


// ==========================================
// OPTIONS FLOW (Unusual Whales)
// ==========================================

let flowHotTickers = [];
let flowRecentAlerts = [];

function initOptionsFlow() {
    const refreshBtn = document.getElementById('refreshFlowBtn');
    const addBtn = document.getElementById('addFlowBtn');
    
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadFlowData);
    }
    
    if (addBtn) {
        addBtn.addEventListener('click', addManualFlow);
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
        
        if (data.configured) {
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
    
    container.innerHTML = flowHotTickers.map(ticker => `
        <div class="flow-hot-card ${ticker.sentiment}" data-ticker="${ticker.ticker}">
            <div class="flow-hot-ticker">${ticker.ticker}</div>
            <div class="flow-hot-sentiment ${ticker.sentiment}">${ticker.sentiment}</div>
            <div class="flow-hot-premium">$${(ticker.total_premium / 1000).toFixed(0)}K</div>
        </div>
    `).join('');
    
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
        const premium = alert.premium ? `$${(alert.premium / 1000).toFixed(0)}K` : '-';
        
        return `
            <div class="flow-alert-item">
                <div class="flow-alert-left">
                    <span class="flow-alert-ticker">${alert.ticker}</span>
                    <span class="flow-alert-type ${alert.type}">${alert.type}</span>
                    <span class="flow-alert-sentiment ${alert.sentiment}">${alert.sentiment}</span>
                </div>
                <div class="flow-alert-right">
                    <div class="flow-alert-premium">${premium}</div>
                    <div class="flow-alert-time">${time}</div>
                </div>
            </div>
        `;
    }).join('');
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
        if (flowModalData.premium === '500000') factors.push('💰 Large premium');
        else if (flowModalData.premium === '150000') factors.push('💵 Good size');
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
        if (flowModalData.type === 'SWEEP') factors.push('🔥 Aggressive sweep');
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
        if (flowModalData.expiry === '2-4weeks') factors.push('📅 Optimal expiry');
        if (flowModalData.expiry === 'leaps') factors.push('⚠️ LEAPS (less urgent)');
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
        if (flowModalData.voloi === 'extreme') factors.push('📊 Extreme volume');
    }
    
    // Repeat activity (0-10 points)
    if (flowModalData.repeat === 'yes') {
        score += 10;
        factors.push('🔁 Repeat hits');
    }
    
    // Determine label and class
    let label, scoreClass, verdictClass, verdict;
    
    if (score >= 80) {
        label = '🚨 EXCEPTIONAL - Must track!';
        scoreClass = 'exceptional';
        verdictClass = 'must-add';
        verdict = '🐋 This is significant institutional activity. Definitely add this!';
    } else if (score >= 60) {
        label = '✅ HIGH - Worth tracking';
        scoreClass = 'high';
        verdictClass = 'add';
        verdict = '👍 Notable flow that could move the stock. Add it!';
    } else if (score >= 40) {
        label = '🟡 MEDIUM - Maybe track';
        scoreClass = 'medium';
        verdictClass = 'maybe';
        verdict = '🤔 Decent activity but not exceptional. Add if it matches your thesis.';
    } else {
        label = '⚪ LOW - Probably skip';
        scoreClass = 'low';
        verdictClass = 'skip';
        verdict = '👎 Likely noise. Skip unless you have other conviction.';
    }
    
    // Add factors to label
    if (factors.length > 0) {
        label += '\n' + factors.join(' • ');
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
            console.log(`🐋 Added flow: ${ticker} ${flowModalData.sentiment} (Score: calculated)`);
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
    
    // Show modal
    document.getElementById('positionEntryModal').classList.add('active');
}

function closePositionEntryModal() {
    document.getElementById('positionEntryModal').classList.remove('active');
    pendingPositionSignal = null;
    pendingPositionCard = null;
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
    
    const entryPrice = parseFloat(document.getElementById('positionEntryPrice').value);
    const qty = parseFloat(document.getElementById('positionQuantity').value);
    
    if (!entryPrice || !qty) {
        alert('Please enter both entry price and quantity');
        return;
    }
    
    try {
        // Accept signal via new API endpoint (includes full logging)
        const response = await fetch(`${API_URL}/signals/${pendingPositionSignal.signal_id}/accept`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                signal_id: pendingPositionSignal.signal_id,
                actual_entry_price: entryPrice,
                quantity: qty,
                stop_loss: pendingPositionSignal.stop_loss,
                target_1: pendingPositionSignal.target_1,
                target_2: pendingPositionSignal.target_2,
                notes: `Accepted via Trade Ideas UI`
            })
        });
        
        const data = await response.json();
        
        if (data.status === 'accepted' || data.position_id) {
            // Remove signal card with animation
            if (pendingPositionCard) {
                pendingPositionCard.style.opacity = '0';
                pendingPositionCard.style.transform = 'translateX(-20px)';
                setTimeout(() => {
                    pendingPositionCard.remove();
                    // Auto-refill Trade Ideas list
                    refillTradeIdeas();
                }, 300);
            }
            
            // Close modal
            closePositionEntryModal();
            
            // Reload positions
            await loadOpenPositionsEnhanced();
            
            // Add ticker to chart tabs
            addPositionChartTab(pendingPositionSignal.ticker);
            
            // Store price levels for chart display
            storePriceLevels(pendingPositionSignal.ticker, {
                entry: entryPrice,
                stop: pendingPositionSignal.stop_loss,
                target1: pendingPositionSignal.target_1,
                target2: pendingPositionSignal.target_2
            });
            
            console.log(`📈 Position accepted: ${pendingPositionSignal.ticker} ${pendingPositionSignal.direction} @ $${entryPrice}`);
        } else {
            alert('Failed to accept signal: ' + (data.detail || data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error accepting signal:', error);
        alert('Failed to accept signal');
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
        const response = await fetch(`${API_URL}/positions/open`);
        const data = await response.json();
        
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
    
    container.innerHTML = openPositions.map(pos => {
        const currentPrice = currentPrices[pos.ticker] || pos.entry_price;
        const pnl = calculatePnL(pos, currentPrice);
        const pnlClass = pnl >= 0 ? 'positive' : 'negative';
        const pnlStr = (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(2);
        const pnlPct = ((currentPrice - pos.entry_price) / pos.entry_price * 100);
        const pnlPctStr = (pnlPct >= 0 ? '+' : '') + pnlPct.toFixed(2) + '%';
        
        // Format entry time as "Jan 28, 1:45 PM" (convert from UTC)
        let entryTimeStr = '';
        if (pos.entry_time) {
            try {
                // Server stores UTC without 'Z', so add it for proper parsing
                let timeStr = pos.entry_time;
                if (!timeStr.endsWith('Z') && !timeStr.includes('+') && !timeStr.includes('-', 10)) {
                    timeStr += 'Z';  // Treat as UTC
                }
                const entryDate = new Date(timeStr);
                const options = { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit', hour12: true };
                entryTimeStr = entryDate.toLocaleString('en-US', options);
            } catch (e) {
                entryTimeStr = '';
            }
        }
        
        // Strategy/Signal info
        const strategyInfo = pos.strategy || pos.signal_type || 'MANUAL';
        
        return `
            <div class="position-card" data-position-id="${pos.id || pos.signal_id}">
                <div class="position-card-header">
                    <span class="position-ticker" data-ticker="${pos.ticker}">${pos.ticker}</span>
                    <span class="position-direction ${pos.direction}">${pos.direction}</span>
                </div>
                ${entryTimeStr ? `<div class="position-timestamp">${entryTimeStr}</div>` : ''}
                ${strategyInfo !== 'MANUAL' ? `<div class="position-strategy">${strategyInfo}</div>` : ''}
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
                        <div class="position-detail-value">$${pos.stop_loss?.toFixed(2) || '--'}</div>
                    </div>
                    <div class="position-detail">
                        <div class="position-detail-label">Target</div>
                        <div class="position-detail-value">$${pos.target_1?.toFixed(2) || '--'}</div>
                    </div>
                </div>
                <div class="position-pnl">
                    <span class="pnl-label">Unrealized P&L</span>
                    <span class="pnl-value ${pnlClass}">${pnlStr} (${pnlPctStr})</span>
                </div>
                <div class="position-actions">
                    <button class="position-btn-small close-btn" data-position-id="${pos.id || pos.signal_id}">Close Position</button>
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
            const position = openPositions.find(p => (p.id || p.signal_id) == positionId);
            if (position) openPositionCloseModal(position);
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
    modal.className = 'signal-modal-overlay';
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
        const response = await fetch(`${API_URL}/positions/close`, {
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
        
        const data = await response.json();
        
        if (data.status === 'success' || data.status === 'closed' || data.status === 'partial_close') {
            closePositionCloseModal();
            await loadOpenPositionsEnhanced();
            
            // Remove chart tab if fully closed
            if (closeQty >= closingPosition.quantity) {
                removePositionChartTab(closingPosition.ticker);
                // Remove price levels
                if (window.activePriceLevels) {
                    delete window.activePriceLevels[closingPosition.ticker];
                }
            }
            
            const emoji = tradeOutcome === 'WIN' ? '🎯' : tradeOutcome === 'LOSS' ? '❌' : '➖';
            console.log(`${emoji} Position closed: ${closingPosition.ticker} - ${tradeOutcome} - P&L: $${data.realized_pnl?.toFixed(2) || '--'}`);
        } else {
            alert('Failed to close position: ' + (data.detail || data.message || 'Unknown error'));
        }
    } catch (error) {
        console.error('Error closing position:', error);
        alert('Failed to close position');
    }
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
    const addBtn = document.getElementById('addPositionBtn');
    const modal = document.getElementById('manualPositionModal');
    const closeBtn = document.getElementById('closeManualPositionBtn');
    const cancelBtn = document.getElementById('cancelManualPositionBtn');
    const confirmBtn = document.getElementById('confirmManualPositionBtn');
    
    if (addBtn) {
        addBtn.addEventListener('click', openManualPositionModal);
    }
    
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
    
    console.log('📝 Manual position modal initialized');
}

function openManualPositionModal() {
    const modal = document.getElementById('manualPositionModal');
    if (modal) {
        // Clear form
        document.getElementById('manualTicker').value = '';
        document.getElementById('manualDirection').value = 'LONG';
        document.getElementById('manualEntryPrice').value = '';
        document.getElementById('manualQuantity').value = '';
        document.getElementById('manualStopLoss').value = '';
        document.getElementById('manualTarget').value = '';
        document.getElementById('manualNotes').value = '';
        
        modal.classList.add('active');
        document.getElementById('manualTicker').focus();
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
    const isCrypto = cryptoTickers.some(c => ticker.includes(c));
    
    const positionData = {
        ticker: ticker,
        direction: direction,
        entry_price: entryPrice,
        quantity: quantity,
        stop_loss: stopLoss,
        target_1: target,
        strategy: notes || 'Manual Entry',
        asset_class: isCrypto ? 'CRYPTO' : 'EQUITY',
        signal_type: 'MANUAL',
        notes: notes
    };
    
    try {
        const response = await fetch(`${API_URL}/positions/manual`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(positionData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            console.log('✅ Manual position created:', result);
            closeManualPositionModal();
            
            // Add to local positions and refresh UI
            if (result.position) {
                openPositions.push(result.position);
                renderPositions();
                
                // Store price levels for chart
                if (result.position.stop_loss || result.position.target_1) {
                    storePriceLevels(result.position);
                }
            }
            
            // Refresh positions from server
            await loadOpenPositions();
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
        console.log(`📚 Loaded ${Object.keys(kbTermMap).length} knowledgebase terms`);
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
    
    // Handle .kb-info-icon elements (ⓘ icons)
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
    
    console.log('📚 KB click handlers initialized');
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
            return '<p>' + p.replace(/^- /, '• ') + '</p>';
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
                ${legNum > 1 ? `<button type="button" class="remove-leg-btn" onclick="removeLeg(${legNum})">✕</button>` : ''}
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

        const pnlDisplay = pnl !== null ? ((pnl >= 0 ? '+' : '') + pnl.toFixed(2)) : '--';
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
