(function () {
    'use strict';

    /* ------------------------------------------------------------------ */
    /*  API + fetch helper                                                */
    /* ------------------------------------------------------------------ */

    const API_BASE = `${window.location.origin}/api/analytics`;

    async function fetchJson(path) {
        const res = await fetch(API_BASE + path);
        if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
        return res.json();
    }

    /* ------------------------------------------------------------------ */
    /*  Shared utility functions (exported on window.analyticsUtils)       */
    /* ------------------------------------------------------------------ */

    function byId(id) { return document.getElementById(id); }

    function escapeHtml(value) {
        if (value === null || value === undefined) return '';
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function slugToLabel(val) {
        return (val || '').replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
    }

    function asNumber(val, fallback) {
        if (fallback === undefined) fallback = 0;
        var n = parseFloat(val);
        return isNaN(n) ? fallback : n;
    }

    function safeArray(val) { return Array.isArray(val) ? val : []; }

    function formatPercent(val, digits) {
        if (digits === undefined) digits = 1;
        if (val === null || val === undefined || isNaN(Number(val))) return '--';
        return (Number(val) * 100).toFixed(digits) + '%';
    }

    function formatRawPercent(val, digits) {
        if (digits === undefined) digits = 1;
        if (val === null || val === undefined || isNaN(Number(val))) return '--';
        return asNumber(val).toFixed(digits) + '%';
    }

    function formatDollar(val, digits) {
        if (digits === undefined) digits = 0;
        if (val === null || val === undefined || isNaN(Number(val))) return '--';
        var n = asNumber(val);
        var sign = n >= 0 ? '+' : '';
        return sign + '$' + Math.abs(n).toLocaleString('en-US', {
            minimumFractionDigits: digits,
            maximumFractionDigits: digits
        });
    }

    function formatRatio(val) {
        if (val === null || val === undefined || isNaN(Number(val))) return '--';
        return asNumber(val).toFixed(2);
    }

    function formatDate(val) {
        if (!val) return '\u2014';
        try { return new Date(val).toLocaleDateString(); } catch (_) { return '\u2014'; }
    }

    function formatDateTime(val) {
        if (!val) return '\u2014';
        try { return new Date(val).toLocaleString(); } catch (_) { return '\u2014'; }
    }

    function metricClass(val) {
        var n = asNumber(val, 0);
        if (n > 0) return 'positive';
        if (n < 0) return 'negative';
        return '';
    }

    function safeDivide(a, b, fallback) {
        if (fallback === undefined) fallback = 0;
        var denom = asNumber(b, 0);
        return denom === 0 ? fallback : asNumber(a, 0) / denom;
    }

    /* ------------------------------------------------------------------ */
    /*  Chart helper                                                       */
    /* ------------------------------------------------------------------ */

    var charts = {};

    function upsertChart(chartKey, canvasId, config) {
        var canvas = byId(canvasId);
        if (!canvas || typeof Chart === 'undefined') return;
        var ctx = canvas.getContext('2d');
        if (!ctx) return;
        if (charts[chartKey]) charts[chartKey].destroy();
        charts[chartKey] = new Chart(ctx, config);
    }

    /* ------------------------------------------------------------------ */
    /*  State                                                              */
    /* ------------------------------------------------------------------ */

    var state = {
        initialized: false,
        pnlPeriod: 'all',
        tradeStats: null,
        cashFlows: [],
        biasAccuracy: null,
        signalStats: null
    };

    /* ------------------------------------------------------------------ */
    /*  1. loadCockpit — master orchestrator                              */
    /* ------------------------------------------------------------------ */

    async function loadCockpit() {
        var results = await Promise.all([
            fetchJson('/trade-stats?days=9999').catch(function () { return null; }),
            fetchJson('/signal-stats?days=90').catch(function () { return null; }),
            fetchJson('/bias-accuracy?days=30').catch(function () { return null; }),
            fetchJson('/cash-flows').catch(function () { return []; }),
            fetchJson('/oracle?days=30&asset_class=EQUITY').catch(function () { return null; })
        ]);

        var tradeStats  = results[0];
        var signalStats = results[1];
        var biasAcc     = results[2];
        var cashFlows   = results[3];
        var oracleData  = results[4];

        state.tradeStats   = tradeStats;
        state.signalStats  = signalStats;
        state.biasAccuracy = biasAcc;
        state.cashFlows    = safeArray(cashFlows);

        renderHeroMetrics(tradeStats);
        renderQuickStats(tradeStats);
        renderPnlChart(tradeStats, state.cashFlows);
        renderStrategyScorecards(tradeStats, signalStats);
        renderBiasHealth(biasAcc);
        renderActiveTestBanner();
        renderStreak(oracleData);
    }

    /* ------------------------------------------------------------------ */
    /*  2. renderHeroMetrics                                               */
    /* ------------------------------------------------------------------ */

    function renderHeroMetrics(stats) {
        var container = byId('cockpitHeroMetrics');
        if (!container) return;

        var pnl = (stats && stats.pnl) || {};
        var s   = (stats && stats.stats) || stats || {};

        var realized   = asNumber(pnl.total_dollars, 0);
        var unrealized = asNumber(pnl.unrealized_pnl, 0);
        var wins  = asNumber(s.wins, 0);
        var losses = asNumber(s.losses, 0);

        container.innerHTML =
            '<div style="text-align:center">' +
                '<div class="' + metricClass(realized) + '" style="font-size:2.5rem;font-weight:700;line-height:1.2">' +
                    escapeHtml(formatDollar(realized, 2)) +
                '</div>' +
                '<div style="font-size:0.85rem;color:var(--text-muted);margin-top:2px">Realized P&L</div>' +
                '<div class="' + metricClass(unrealized) + '" style="font-size:1.2rem;margin-top:8px">' +
                    escapeHtml(formatDollar(unrealized, 2)) + ' unrealized' +
                '</div>' +
                '<div style="font-size:1rem;margin-top:6px;color:var(--text-secondary)">' +
                    escapeHtml(String(wins)) + 'W / ' + escapeHtml(String(losses)) + 'L' +
                '</div>' +
            '</div>';
    }

    /* ------------------------------------------------------------------ */
    /*  3. renderQuickStats                                                */
    /* ------------------------------------------------------------------ */

    function renderQuickStats(stats) {
        var container = byId('cockpitQuickStats');
        if (!container) return;

        var pnl  = (stats && stats.pnl)          || {};
        var risk = (stats && stats.risk_metrics)  || {};
        var s    = (stats && stats.stats)         || stats || {};

        var wins   = asNumber(s.wins, 0);
        var losses = asNumber(s.losses, 0);
        var total  = wins + losses;
        var winRate = safeDivide(wins, total);

        var rows = [
            { label: 'Win Rate',      value: formatRawPercent(winRate * 100, 1), cls: metricClass(winRate - 0.5) },
            { label: 'Avg Win',       value: formatDollar(pnl.avg_win, 2),      cls: 'positive' },
            { label: 'Avg Loss',      value: formatDollar(pnl.avg_loss, 2),     cls: 'negative' },
            { label: 'Expectancy',    value: formatDollar(pnl.expectancy_per_trade, 2), cls: metricClass(pnl.expectancy_per_trade) },
            { label: 'Profit Factor', value: formatRatio(risk.profit_factor),    cls: metricClass(asNumber(risk.profit_factor, 0) - 1) },
            { label: 'Sharpe Ratio',  value: formatRatio(risk.sharpe_ratio),     cls: metricClass(risk.sharpe_ratio) },
            { label: 'Max Drawdown',  value: formatDollar(risk.max_drawdown_dollars, 0) + ' (' + formatRawPercent(risk.max_drawdown_pct, 1) + ')', cls: 'negative' },
            { label: 'Best Trade',    value: formatDollar(pnl.largest_win, 2),   cls: 'positive' },
            { label: 'Worst Trade',   value: formatDollar(pnl.largest_loss, 2),  cls: 'negative' }
        ];

        var html = '';
        for (var i = 0; i < rows.length; i++) {
            var r = rows[i];
            html +=
                '<div class="analytics-metric-item">' +
                    '<span class="analytics-metric-label">' + escapeHtml(r.label) + '</span>' +
                    '<span class="analytics-metric-value ' + (r.cls || '') + '">' + escapeHtml(r.value) + '</span>' +
                '</div>';
        }
        container.innerHTML = html;
    }

    /* ------------------------------------------------------------------ */
    /*  4. renderPnlChart                                                  */
    /* ------------------------------------------------------------------ */

    function renderPnlChart(stats, cashFlows) {
        var points = safeArray(stats && stats.equity_curve);
        if (!points.length) {
            var canvas = byId('cockpitPnlChart');
            if (canvas) canvas.parentElement.innerHTML = '<p style="color:var(--text-muted);text-align:center;padding:2rem 0">No equity curve data yet.</p>';
            return;
        }

        var labels    = [];
        var pnlSeries = [];
        for (var i = 0; i < points.length; i++) {
            labels.push(String(points[i].date || ''));
            pnlSeries.push(asNumber(points[i].cumulative_pnl, 0));
        }

        // Build withdrawal markers from cashFlows
        var withdrawalPoints = [];
        var cfMap = {};
        for (var j = 0; j < cashFlows.length; j++) {
            var cf = cashFlows[j];
            if (asNumber(cf.amount, 0) < 0) {
                var dateStr = String(cf.date || cf.created_at || '').slice(0, 10);
                cfMap[dateStr] = cf;
            }
        }
        var markerData = [];
        for (var k = 0; k < labels.length; k++) {
            if (cfMap[labels[k]]) {
                markerData.push(pnlSeries[k]);
            } else {
                markerData.push(null);
            }
        }

        var datasets = [
            {
                label: 'Cumulative P&L',
                data: pnlSeries,
                borderColor: '#14b8a6',
                backgroundColor: 'rgba(20,184,166,0.10)',
                fill: true,
                tension: 0.25,
                pointRadius: 0,
                borderWidth: 2
            }
        ];

        // Add withdrawal markers if any exist
        var hasWithdrawals = markerData.some(function (v) { return v !== null; });
        if (hasWithdrawals) {
            datasets.push({
                label: 'Withdrawal',
                data: markerData,
                borderColor: 'transparent',
                backgroundColor: '#ff9800',
                pointStyle: 'triangle',
                pointRadius: 7,
                pointBorderColor: '#ff9800',
                showLine: false
            });
        }

        upsertChart('cockpitEquity', 'cockpitPnlChart', {
            type: 'line',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                plugins: {
                    legend: { display: hasWithdrawals, labels: { color: '#ccc', boxWidth: 12 } },
                    tooltip: {
                        callbacks: {
                            label: function (ctx) {
                                if (ctx.dataset.label === 'Withdrawal') return 'Withdrawal';
                                return ctx.dataset.label + ': ' + formatDollar(ctx.parsed.y, 2);
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#888', maxTicksLimit: 12 },
                        grid: { color: 'rgba(255,255,255,0.04)' }
                    },
                    y: {
                        ticks: {
                            color: '#888',
                            callback: function (v) { return formatDollar(v, 0); }
                        },
                        grid: { color: 'rgba(255,255,255,0.06)' }
                    }
                }
            }
        });
    }

    /* ------------------------------------------------------------------ */
    /*  5. renderStrategyScorecards                                        */
    /* ------------------------------------------------------------------ */

    function renderStrategyScorecards(tradeStats, signalStats) {
        var container = byId('cockpitStrategyScorecards');
        if (!container) return;

        var bySource = (tradeStats && tradeStats.by_signal_source) || {};
        var signalBySource = {};
        var signalSources = safeArray(signalStats && signalStats.by_source);
        for (var s = 0; s < signalSources.length; s++) {
            var src = signalSources[s];
            if (src && src.source) signalBySource[src.source] = src;
        }

        var keys = Object.keys(bySource);
        if (!keys.length) {
            container.innerHTML = '<p style="color:var(--text-muted)">No strategy data yet.</p>';
            return;
        }

        var html = '';
        for (var i = 0; i < keys.length; i++) {
            var key  = keys[i];
            var data = bySource[key] || {};
            var pnl  = (data.pnl && data.pnl.total_dollars) || (data.total_pnl) || 0;
            var w    = asNumber(data.wins || (data.stats && data.stats.wins), 0);
            var l    = asNumber(data.losses || (data.stats && data.stats.losses), 0);
            var net  = asNumber(pnl, 0);
            var borderColor = net >= 0 ? '#14b8a6' : '#e5370e';

            var sigInfo = signalBySource[key];
            var accLine = '';
            if (sigInfo && sigInfo.accuracy != null) {
                accLine = '<div style="font-size:0.8rem;color:var(--text-muted);margin-top:4px">Signal accuracy: ' +
                    escapeHtml(formatRawPercent(asNumber(sigInfo.accuracy, 0) * 100, 1)) + '</div>';
            }

            html +=
                '<div class="analytics-card" style="border-left:3px solid ' + borderColor + ';padding:10px 14px;margin-bottom:8px">' +
                    '<div style="font-weight:600;font-size:0.95rem">' + escapeHtml(slugToLabel(key)) + '</div>' +
                    '<div style="margin-top:4px">' +
                        '<span style="margin-right:12px">' + escapeHtml(String(w)) + 'W / ' + escapeHtml(String(l)) + 'L</span>' +
                        '<span class="' + metricClass(net) + '">' + escapeHtml(formatDollar(net, 2)) + '</span>' +
                    '</div>' +
                    accLine +
                '</div>';
        }
        container.innerHTML = html;
    }

    /* ------------------------------------------------------------------ */
    /*  6. renderBiasHealth                                                */
    /* ------------------------------------------------------------------ */

    function renderBiasHealth(data) {
        var container = byId('cockpitBiasHealth');
        if (!container) return;

        if (!data) {
            container.innerHTML = '<p style="color:var(--text-muted)">Bias accuracy data unavailable.</p>';
            return;
        }

        var dir  = (data.directional_accuracy) || {};
        var gate = (data.gatekeeper)           || {};
        var overall = dir.overall;
        var daysCollected = asNumber(data.days_collected || data.days, 0);

        var html = '';

        // Overall accuracy
        html +=
            '<div class="analytics-metric-item">' +
                '<span class="analytics-metric-label">Directional Accuracy</span>' +
                '<span class="analytics-metric-value ' + metricClass(asNumber(overall, 0) - 0.5) + '">' +
                    escapeHtml(overall != null ? formatRawPercent(asNumber(overall, 0) * 100, 1) : '--') +
                '</span>' +
            '</div>';

        // Gatekeeper stats
        html +=
            '<div class="analytics-metric-item">' +
                '<span class="analytics-metric-label">Signals Blocked</span>' +
                '<span class="analytics-metric-value">' + escapeHtml(String(asNumber(gate.signals_blocked, 0))) + '</span>' +
            '</div>' +
            '<div class="analytics-metric-item">' +
                '<span class="analytics-metric-label">Filter Accuracy</span>' +
                '<span class="analytics-metric-value">' +
                    escapeHtml(gate.filter_accuracy != null ? formatRawPercent(asNumber(gate.filter_accuracy, 0) * 100, 1) : '--') +
                '</span>' +
            '</div>';

        if (daysCollected > 0 && daysCollected < 14) {
            html += '<div style="font-size:0.8rem;color:var(--text-muted);margin-top:6px;font-style:italic">' +
                'Collecting data (' + String(daysCollected) + ' of 14 days minimum)</div>';
        }

        container.innerHTML = html;
    }

    /* ------------------------------------------------------------------ */
    /*  7. renderActiveTestBanner                                          */
    /* ------------------------------------------------------------------ */

    function renderActiveTestBanner() {
        var container = byId('cockpitActiveTest');
        if (!container) return;

        var tests = [
            { name: 'Footprint', end: '2026-03-28' }
        ];

        var now = new Date();
        var html = '';

        for (var i = 0; i < tests.length; i++) {
            var t = tests[i];
            var end = new Date(t.end + 'T23:59:59');
            var daysLeft = Math.ceil((end - now) / (1000 * 60 * 60 * 24));
            if (daysLeft < 0) continue;

            html +=
                '<div class="analytics-card" style="border-left:3px solid #fbc02d;padding:8px 14px;margin-bottom:6px;cursor:pointer" ' +
                    'onclick="if(window.cockpitUI&&window.cockpitUI._switchToLab)window.cockpitUI._switchToLab()">' +
                    '<span style="font-weight:600">' + escapeHtml(t.name) + '</span>' +
                    '<span style="margin-left:8px;color:var(--text-muted)">' + String(daysLeft) + ' days remaining</span>' +
                    '<span style="margin-left:8px;font-size:0.8rem;color:#fbc02d">View in Laboratory &rarr;</span>' +
                '</div>';
        }

        if (!html) {
            container.innerHTML = '';
            return;
        }

        container.innerHTML =
            '<div style="margin-bottom:4px;font-size:0.85rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.5px">Active Tests</div>' +
            html;
    }

    /* ------------------------------------------------------------------ */
    /*  8. renderStreak                                                    */
    /* ------------------------------------------------------------------ */

    function renderStreak(oracleData) {
        var container = byId('cockpitStreak');
        if (!container) return;

        var health = (oracleData && oracleData.system_health) || {};
        var streak = health.current_streak;

        if (!streak) {
            container.innerHTML = '';
            return;
        }

        var count = asNumber(streak.count || streak.length, 0);
        var type  = String(streak.type || streak.direction || '').toUpperCase();

        if (!count || !type) {
            container.innerHTML = '';
            return;
        }

        var isWin   = type === 'W' || type === 'WIN';
        var display = (isWin ? 'W' : 'L') + String(count);
        var emoji   = isWin && count >= 3 ? ' \uD83D\uDD25' : '';
        var cls     = isWin ? 'positive' : 'negative';

        container.innerHTML =
            '<span class="' + cls + '" style="font-size:1.3rem;font-weight:700">' +
                escapeHtml(display) + emoji +
            '</span>';
    }

    /* ------------------------------------------------------------------ */
    /*  9. P&L period toggle                                               */
    /* ------------------------------------------------------------------ */

    function setPnlPeriod(period) {
        state.pnlPeriod = period;
        document.querySelectorAll('.pnl-toggle-btn').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.period === period);
        });

        var daysMap = { daily: 1, weekly: 7, monthly: 30, all: 9999 };
        var days = daysMap[period] || 9999;

        fetchJson('/trade-stats?days=' + days)
            .then(function (data) {
                renderPnlChart(data, state.cashFlows);
            })
            .catch(function () {
                // silently ignore refresh errors
            });
    }

    /* ------------------------------------------------------------------ */
    /*  10. init — wire up on DOMContentLoaded                             */
    /* ------------------------------------------------------------------ */

    function init() {
        if (state.initialized) return;
        state.initialized = true;

        // Bind P&L toggle buttons
        document.querySelectorAll('.pnl-toggle-btn').forEach(function (btn) {
            btn.addEventListener('click', function () {
                setPnlPeriod(btn.dataset.period);
            });
        });

        // Listen for analytics mode activation
        document.addEventListener('pandora:modechange', function (e) {
            if (e && e.detail && e.detail.mode === 'analytics') {
                loadCockpit();
            }
        });
    }

    document.addEventListener('DOMContentLoaded', init);

    /* ------------------------------------------------------------------ */
    /*  Window exports                                                     */
    /* ------------------------------------------------------------------ */

    window.analyticsUtils = {
        byId: byId,
        escapeHtml: escapeHtml,
        slugToLabel: slugToLabel,
        asNumber: asNumber,
        safeArray: safeArray,
        formatPercent: formatPercent,
        formatRawPercent: formatRawPercent,
        formatDollar: formatDollar,
        formatRatio: formatRatio,
        formatDate: formatDate,
        formatDateTime: formatDateTime,
        metricClass: metricClass,
        upsertChart: upsertChart,
        charts: charts,
        fetchJson: fetchJson
    };

    window.cockpitUI = {
        loadCockpit: loadCockpit,
        setPnlPeriod: setPnlPeriod,
        _switchToLab: null  // to be wired by app.js for tab switching
    };

})();
