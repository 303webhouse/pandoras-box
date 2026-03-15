/**
 * laboratory.js - Laboratory tab for the Abacus analytics view.
 *
 * Deep-dive investigation tools: Journal, Signals, Factors, Backtest, Footprint, Oracle.
 * Depends on window.analyticsUtils (set by cockpit.js which loads first).
 */
(function () {
    'use strict';

    /* ── Shared utility imports from cockpit.js ─────────────────────── */
    var u = window.analyticsUtils || {};
    var byId = u.byId || function (id) { return document.getElementById(id); };
    var escapeHtml = u.escapeHtml || function (v) { return String(v == null ? '' : v); };
    var slugToLabel = u.slugToLabel || function (v) { return String(v || ''); };
    var asNumber = u.asNumber || function (v, fb) { var n = parseFloat(v); return isNaN(n) ? (fb === undefined ? 0 : fb) : n; };
    var safeArray = u.safeArray || function (v) { return Array.isArray(v) ? v : []; };
    var formatPercent = u.formatPercent || function (v, d) {
        if (v === null || v === undefined || isNaN(Number(v))) return '--';
        return (Number(v) * 100).toFixed(d === undefined ? 1 : d) + '%';
    };
    var formatRawPercent = u.formatRawPercent || function (v, d) {
        if (v === null || v === undefined || isNaN(Number(v))) return '--';
        return Number(v).toFixed(d === undefined ? 1 : d) + '%';
    };
    var formatDollar = u.formatDollar || function (v, d) {
        if (v === null || v === undefined || isNaN(Number(v))) return '--';
        var n = Number(v);
        var sign = n > 0 ? '+' : '';
        return sign + '$' + n.toFixed(d === undefined ? 2 : d);
    };
    var formatRatio = u.formatRatio || function (v) {
        if (v === null || v === undefined || isNaN(Number(v))) return '--';
        return Math.abs(Number(v)).toFixed(2) + ':1';
    };
    var formatDate = u.formatDate || function (v) {
        if (!v) return '--';
        try { return new Date(v).toLocaleDateString(); } catch (_) { return '--'; }
    };
    var formatDateTime = u.formatDateTime || function (v) {
        if (!v) return '--';
        try { return new Date(v).toLocaleString(); } catch (_) { return String(v); }
    };
    var metricClass = u.metricClass || function (v) {
        var n = asNumber(v, 0);
        if (n > 0) return 'positive';
        if (n < 0) return 'negative';
        return '';
    };
    var fetchJson = u.fetchJson;

    var API_BASE = window.location.origin + '/api/analytics';

    var SOURCE_COLORS = ['#14b8a6', '#fbbf24', '#f87171', '#60a5fa', '#a78bfa', '#9fb7ff', '#e5370e', '#26c6da', '#7e57c2', '#8bc34a'];
    var REGIME_ORDER = ['MAJOR_URSA', 'MINOR_URSA', 'NEUTRAL', 'MINOR_TORO', 'MAJOR_TORO'];

    /* ── Local helpers not in shared utils ────────────────────────────── */

    function fetchForm(path, formData, options) {
        var opts = options || {};
        var url = API_BASE + path;
        return fetch(url, {
            method: opts.method || 'POST',
            body: formData,
            headers: opts.headers || {}
        }).then(function (response) {
            if (!response.ok) {
                return response.json().catch(function () { return {}; }).then(function (payload) {
                    var detail = (payload && payload.detail) || (response.status + ' ' + response.statusText);
                    throw new Error(detail);
                });
            }
            return response.json();
        });
    }

    function localUpsertChart(chartKey, canvasId, config) {
        var canvas = byId(canvasId);
        if (!canvas || typeof Chart === 'undefined') return;
        var ctx = canvas.getContext('2d');
        if (!ctx) return;
        if (state.charts[chartKey]) {
            state.charts[chartKey].destroy();
        }
        state.charts[chartKey] = new Chart(ctx, config);
    }

    function normalizeTradeOrigin(v) {
        var origin = String(v || 'manual').trim().toLowerCase();
        if (origin === 'signal_driven' || origin === 'signal') return 'signal_driven';
        if (origin === 'imported' || origin === 'import') return 'imported';
        return 'manual';
    }

    function renderOriginTag(v) {
        var origin = normalizeTradeOrigin(v);
        if (origin === 'signal_driven') return '<span class="origin-tag origin-tag-signal">Signal</span>';
        if (origin === 'imported') return '<span class="origin-tag origin-tag-imported">Imported</span>';
        return '<span class="origin-tag origin-tag-manual">Manual</span>';
    }

    function normalizeRegime(v) {
        var raw = String(v || '').toUpperCase().trim();
        if (!raw) return 'UNKNOWN';
        if (raw === 'URSA_MAJOR' || raw === 'MAJOR URSA') return 'MAJOR_URSA';
        if (raw === 'URSA_MINOR' || raw === 'MINOR URSA') return 'MINOR_URSA';
        if (raw === 'TORO_MINOR' || raw === 'MINOR TORO') return 'MINOR_TORO';
        if (raw === 'TORO_MAJOR' || raw === 'MAJOR TORO') return 'MAJOR_TORO';
        return raw.replace(/\s+/g, '_');
    }

    function buildFactorValueMap(rows, key, valueKey) {
        var out = {};
        safeArray(rows).forEach(function (row) {
            var k = String(row[key] || '').slice(0, 10);
            if (!k) return;
            out[k] = asNumber(row[valueKey], 0);
        });
        return out;
    }

    function linearReferenceSeries(length, finalValue) {
        if (length <= 0) return [];
        if (!isFinite(finalValue)) return new Array(length).fill(0);
        if (length === 1) return [finalValue];
        var out = [];
        for (var i = 0; i < length; i += 1) {
            out.push((finalValue * i) / (length - 1));
        }
        return out;
    }

    function computeDrawdownSeries(curve) {
        var peak = -Infinity;
        return curve.map(function (value) {
            var n = asNumber(value, 0);
            if (n > peak) peak = n;
            return n - peak;
        });
    }

    function valOrDash(v) {
        return (v !== null && v !== undefined) ? String(v) : '--';
    }

    /* ── Sub-tab constants ──────────────────────────────────────────── */
    var LAB_TABS = ['journal', 'signals', 'factors', 'backtest', 'footprint', 'oracle'];

    /* ── Top-level tab constants ────────────────────────────────────── */
    var TAB_TO_PANE = {
        cockpit: 'analyticsPaneCockpit',
        laboratory: 'analyticsPaneLaboratory'
    };

    /* ── State ──────────────────────────────────────────────────────── */
    var state = {
        initialized: false,
        activeTab: 'cockpit',
        labActiveSubTab: 'journal',
        journal: {
            filters: { account: '', direction: '', structure: '', origin: '', signal_source: '', days: 90, search: '' },
            rows: [],
            selectedTradeId: null,
            pendingImportPreview: null
        },
        signalExplorer: {
            sortBy: 'timestamp',
            sortDir: 'desc',
            rows: [],
            selectedSignalId: null
        },
        factorLab: {
            factors: [],
            selectedFactor: '',
            compareFactor: '',
            days: 60
        },
        backtest: { primary: null, compare: null },
        charts: {},
        journalDebounce: null,
        signalDebounce: null,
        selectedSignalSource: null
    };

    /* ══════════════════════════════════════════════════════════════════
       TOP-LEVEL TAB SWITCHING  (Cockpit vs Laboratory)
       ══════════════════════════════════════════════════════════════════ */

    function setActiveTab(tabName) {
        var tab = TAB_TO_PANE[tabName] ? tabName : 'cockpit';
        state.activeTab = tab;

        document.querySelectorAll('.analytics-subtab').forEach(function (button) {
            var isActive = button.dataset.analyticsTab === tab;
            button.classList.toggle('active', isActive);
            button.setAttribute('aria-selected', String(isActive));
        });

        Object.keys(TAB_TO_PANE).forEach(function (name) {
            var paneId = TAB_TO_PANE[name];
            var pane = byId(paneId);
            if (!pane) return;
            var active = name === tab;
            pane.classList.toggle('active', active);
            pane.hidden = !active;
        });

        if (tab === 'cockpit') {
            if (window.cockpitUI && window.cockpitUI.loadCockpit) {
                window.cockpitUI.loadCockpit();
            }
            document.dispatchEvent(new CustomEvent('pandora:modechange', { detail: { mode: 'analytics' } }));
        }

        if (tab === 'laboratory') {
            setLabSubTab(state.labActiveSubTab);
        }
    }

    /* ══════════════════════════════════════════════════════════════════
       LAB SUB-TAB SWITCHING
       ══════════════════════════════════════════════════════════════════ */

    function setLabSubTab(tabName) {
        var tab = LAB_TABS.indexOf(tabName) >= 0 ? tabName : 'journal';
        state.labActiveSubTab = tab;

        document.querySelectorAll('.lab-subtab').forEach(function (btn) {
            btn.classList.toggle('active', btn.dataset.labTab === tab);
        });

        LAB_TABS.forEach(function (name) {
            var pane = byId('labPane_' + name);
            if (pane) pane.hidden = (name !== tab);
        });

        if (tab === 'journal') loadChronicle();
        if (tab === 'signals') loadSignalExplorer();
        if (tab === 'factors') loadFactorLab();
        if (tab === 'backtest') initBacktestDefaults();
        if (tab === 'footprint') loadFootprintCorrelation();
        if (tab === 'oracle') loadOracleNarrative();
    }

    /* ══════════════════════════════════════════════════════════════════
       1. JOURNAL / CHRONICLE  SUB-TAB
       ══════════════════════════════════════════════════════════════════ */

    function getJournalFilters() {
        var acctEl = byId('journalFilterAccount');
        var dirEl = byId('journalFilterDirection');
        var strEl = byId('journalFilterStructure');
        var origEl = byId('journalFilterOrigin');
        var srcEl = byId('journalFilterSource');
        var daysEl = byId('journalFilterDays');
        var searchEl = byId('journalSearchTicker');
        return {
            account: acctEl ? acctEl.value : '',
            direction: dirEl ? dirEl.value : '',
            structure: strEl ? strEl.value : '',
            origin: origEl ? origEl.value : '',
            signal_source: srcEl ? srcEl.value : '',
            days: asNumber(daysEl ? daysEl.value : 90, 90),
            search: searchEl ? (searchEl.value || '').trim() : ''
        };
    }

    function refreshSourceFilterOptions(sources) {
        var seen = {};
        safeArray(sources).forEach(function (v) {
            var s = String(v || '').trim();
            if (s) seen[s] = true;
        });
        var sorted = Object.keys(seen).sort(function (a, b) { return a.localeCompare(b); });

        var targets = [
            { id: 'journalFilterSource', label: 'Signal Source: All' },
            { id: 'signalFilterSource', label: 'Source: All' }
        ];
        targets.forEach(function (meta) {
            var select = byId(meta.id);
            if (!select) return;
            var currentValue = select.value;
            select.innerHTML = '<option value="">' + meta.label + '</option>';
            sorted.forEach(function (source) {
                var option = document.createElement('option');
                option.value = source;
                option.textContent = slugToLabel(source);
                select.appendChild(option);
            });
            if (sorted.indexOf(currentValue) >= 0) {
                select.value = currentValue;
            }
        });
    }

    function renderJournalTable(rows) {
        var tbody = byId('journalTableBody');
        if (!tbody) return;

        var trades = safeArray(rows);
        if (!trades.length) {
            tbody.innerHTML = '<tr><td colspan="13" class="analytics-empty">Collecting data - metrics will appear after signals accumulate.</td></tr>';
            return;
        }

        tbody.innerHTML = trades.map(function (trade) {
            var id = asNumber(trade.id, 0);
            var pnl = asNumber(trade.pnl_dollars, 0);
            var status = String(trade.status || '').toLowerCase();
            var rowClass = status === 'open' ? 'trade-open' : (pnl >= 0 ? 'trade-win' : 'trade-loss');
            var entry = trade.entry_price !== null && trade.entry_price !== undefined ? Number(trade.entry_price).toFixed(2) : '--';
            var exit = trade.exit_price !== null && trade.exit_price !== undefined ? Number(trade.exit_price).toFixed(2) : '--';
            var signal = trade.signal_source || trade.linked_signal_strategy || '--';
            var bias = trade.bias_at_entry || trade.linked_signal_bias || '--';
            var origin = trade.origin || 'manual';

            return '<tr class="' + rowClass + '" data-trade-id="' + id + '">' +
                '<td>' + escapeHtml(formatDate(trade.opened_at || trade.closed_at)) + '</td>' +
                '<td>' + escapeHtml(String(trade.ticker || '--').toUpperCase()) + '</td>' +
                '<td>' + escapeHtml(String(trade.direction || '--').toUpperCase()) + '</td>' +
                '<td>' + escapeHtml(String(trade.structure || '--')) + '</td>' +
                '<td>' + escapeHtml(entry + ' -> ' + exit) + '</td>' +
                '<td>' + escapeHtml(formatDollar(trade.pnl_dollars)) + '</td>' +
                '<td>' + escapeHtml(formatRawPercent(trade.pnl_percent)) + '</td>' +
                '<td>' + escapeHtml(formatRatio(trade.rr_achieved)) + '</td>' +
                '<td>' + escapeHtml(String(trade.account || '--').toUpperCase()) + '</td>' +
                '<td>' + escapeHtml(String(bias)) + '</td>' +
                '<td>' + renderOriginTag(origin) + '</td>' +
                '<td>' + escapeHtml(slugToLabel(signal)) + '</td>' +
                '<td>' + escapeHtml(String(trade.exit_reason || '--')) + '</td>' +
                '</tr>';
        }).join('');

        tbody.querySelectorAll('tr[data-trade-id]').forEach(function (row) {
            row.addEventListener('click', function () {
                var tradeId = asNumber(row.getAttribute('data-trade-id'), 0);
                if (!tradeId) return;
                loadTradeDetails(tradeId);
            });
        });
    }

    function renderJournalSummary(stats, visibleCount) {
        var summary = byId('journalSummary');
        if (!summary) return;

        var totalTrades = asNumber(stats ? stats.total_trades : 0, visibleCount);
        var closed = asNumber(stats ? stats.closed : 0, 0);
        var wins = Math.round(asNumber(stats ? stats.win_rate : 0, 0) * closed);
        var losses = Math.max(0, closed - wins);
        var totalPnl = stats && stats.pnl ? stats.pnl.total_dollars : null;
        var avgRR = stats && stats.pnl ? stats.pnl.avg_rr_achieved : null;
        var sharpe = stats && stats.risk_metrics ? stats.risk_metrics.sharpe_ratio : null;

        summary.textContent = 'Total: ' + totalTrades + ' trades | Wins: ' + wins +
            ' | Losses: ' + losses + ' | Win Rate: ' + formatPercent(stats ? stats.win_rate : null) +
            ' | Total P&L: ' + formatDollar(totalPnl) + ' | Avg R:R: ' + formatRatio(avgRR) +
            ' | Sharpe: ' + asNumber(sharpe, 0).toFixed(2);
    }

    function renderKeyMetrics(stats) {
        var container = byId('analyticsKeyMetrics');
        if (!container) return;

        var pnl = (stats && stats.pnl) || {};
        var risk = (stats && stats.risk_metrics) || {};
        var byOrigin = (stats && stats.by_origin) || {};
        var signalOrigin = byOrigin.signal_driven || {};
        var importedOrigin = byOrigin.imported || {};
        var originBreakdown = asNumber(signalOrigin.trades) + ' signal (' + formatPercent(signalOrigin.win_rate) + ') vs ' + asNumber(importedOrigin.trades) + ' imported (' + formatPercent(importedOrigin.win_rate) + ')';

        var metrics = [
            { label: 'Total P&L', value: formatDollar(pnl.total_dollars), className: metricClass(pnl.total_dollars) },
            { label: 'Win Rate', value: formatPercent(stats ? stats.win_rate : null), className: metricClass(((stats ? stats.win_rate : 0) || 0) - 0.5) },
            { label: 'Avg R:R', value: formatRatio(pnl.avg_rr_achieved), className: metricClass(pnl.avg_rr_achieved) },
            { label: 'Sharpe', value: asNumber(risk.sharpe_ratio).toFixed(2), className: metricClass(risk.sharpe_ratio) },
            { label: 'Profit Factor', value: asNumber(risk.profit_factor).toFixed(2), className: metricClass((risk.profit_factor || 0) - 1) },
            { label: 'Max Drawdown', value: formatRawPercent(risk.max_drawdown_pct), className: metricClass(risk.max_drawdown_pct) },
            { label: 'Expectancy', value: formatDollar(pnl.expectancy_per_trade), className: metricClass(pnl.expectancy_per_trade) },
            { label: 'Open Trades', value: String(asNumber(stats ? stats.open : 0, 0)), className: '' },
            { label: 'Origin Mix', value: originBreakdown, className: '' },
            { label: 'Best Trade', value: formatDollar(pnl.largest_win), className: metricClass(pnl.largest_win) },
            { label: 'Worst Trade', value: formatDollar(pnl.largest_loss), className: metricClass(pnl.largest_loss) }
        ];

        container.innerHTML = metrics.map(function (item) {
            return '<div class="analytics-metric-item">' +
                '<span class="analytics-metric-label">' + escapeHtml(item.label) + '</span>' +
                '<span class="analytics-metric-value ' + escapeHtml(item.className) + '">' + escapeHtml(item.value) + '</span>' +
                '</div>';
        }).join('');
    }

    function renderEquityChart(stats) {
        var points = safeArray(stats ? stats.equity_curve : []);
        var labels = points.map(function (p) { return String(p.date || ''); });
        var pnlSeries = points.map(function (p) { return asNumber(p.cumulative_pnl, 0); });

        var benchmarks = (stats && stats.benchmarks) || {};
        var benchmarkSpy = linearReferenceSeries(labels.length, asNumber(benchmarks.spy_buy_hold_return_pct, 0));
        var benchmarkBias = linearReferenceSeries(labels.length, asNumber(benchmarks.bias_follow_return_pct, 0));
        var drawdowns = computeDrawdownSeries(pnlSeries);

        localUpsertChart('equity', 'analyticsEquityChart', {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    { label: 'Your P&L', data: pnlSeries, borderColor: '#14b8a6', backgroundColor: 'rgba(20,184,166,0.12)', fill: false, tension: 0.25, pointRadius: 0, borderWidth: 2 },
                    { label: 'SPY B&H (ref)', data: benchmarkSpy, borderColor: '#9fb7ff', fill: false, borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5 },
                    { label: 'Bias-Follow (ref)', data: benchmarkBias, borderColor: '#fbc02d', fill: false, borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5 },
                    { label: 'Drawdown', data: drawdowns, yAxisID: 'y1', borderColor: 'rgba(229,55,14,0.35)', backgroundColor: 'rgba(229,55,14,0.12)', fill: true, pointRadius: 0, borderWidth: 1, tension: 0.2 }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#9fb7ff' } } },
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: { ticks: { color: '#89a1c8', maxTicksLimit: 9 }, grid: { color: 'rgba(38,53,85,0.35)' } },
                    y: { ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.35)' } },
                    y1: { display: false, grid: { drawOnChartArea: false } }
                }
            }
        });
    }

    function parseContext(value) {
        if (!value) return {};
        if (typeof value === 'object') return value;
        if (typeof value === 'string') {
            try { return JSON.parse(value); } catch (_) { return { raw: value }; }
        }
        return {};
    }

    function renderLegsTable(legs) {
        var rows = safeArray(legs);
        if (!rows.length) return '<div class="analytics-empty">No legs recorded.</div>';

        var body = rows.map(function (leg) {
            return '<tr>' +
                '<td>' + escapeHtml(formatDateTime(leg.timestamp)) + '</td>' +
                '<td>' + escapeHtml(String(leg.action || '--')) + '</td>' +
                '<td>' + escapeHtml(String(leg.direction || '--')) + '</td>' +
                '<td>' + escapeHtml(valOrDash(leg.quantity)) + '</td>' +
                '<td>' + escapeHtml(valOrDash(leg.price)) + '</td>' +
                '<td>' + escapeHtml(valOrDash(leg.strike)) + '</td>' +
                '<td>' + escapeHtml(valOrDash(leg.expiry)) + '</td>' +
                '<td>' + escapeHtml(valOrDash(leg.leg_type)) + '</td>' +
                '</tr>';
        }).join('');

        return '<table class="journal-legs-table">' +
            '<thead><tr><th>Time</th><th>Action</th><th>Dir</th><th>Qty</th><th>Price</th><th>Strike</th><th>Expiry</th><th>Type</th></tr></thead>' +
            '<tbody>' + body + '</tbody></table>';
    }

    function loadTradeDetails(tradeId) {
        state.journal.selectedTradeId = tradeId;

        var detailContainer = byId('journalTradeDetails');
        if (!detailContainer) return;
        detailContainer.innerHTML = '<div class="analytics-empty">Loading trade details...</div>';

        var trade = null;
        for (var i = 0; i < state.journal.rows.length; i++) {
            if (asNumber(state.journal.rows[i].id, 0) === tradeId) {
                trade = state.journal.rows[i];
                break;
            }
        }
        if (!trade) {
            detailContainer.innerHTML = '<div class="analytics-empty">Trade not found in current table.</div>';
            return;
        }

        fetchJson('/trade/' + tradeId + '/legs').then(function (legPayload) {
            return safeArray(legPayload ? legPayload.rows : []);
        }).catch(function () {
            return [];
        }).then(function (legs) {
            var context = parseContext(trade.full_context);
            var contextText = escapeHtml(JSON.stringify(context, null, 2)).slice(0, 8000);

            detailContainer.innerHTML =
                '<div class="journal-detail-block">' +
                    '<h4>Overview</h4>' +
                    '<div><strong>' + escapeHtml(String(trade.ticker || '').toUpperCase()) + '</strong> ' +
                        escapeHtml(String(trade.direction || '--').toUpperCase()) + ' ' + escapeHtml(String(trade.structure || '--')) + '</div>' +
                    '<div>Status: ' + escapeHtml(String(trade.status || '--')) + ' | Opened: ' + escapeHtml(formatDateTime(trade.opened_at)) +
                        ' | Closed: ' + escapeHtml(formatDateTime(trade.closed_at)) + '</div>' +
                    '<div>Entry: ' + escapeHtml(valOrDash(trade.entry_price)) + ' | Stop: ' + escapeHtml(valOrDash(trade.stop_loss)) +
                        ' | Target 1: ' + escapeHtml(valOrDash(trade.target_1)) + '</div>' +
                    '<div>P&L: ' + escapeHtml(formatDollar(trade.pnl_dollars)) + ' (' + escapeHtml(formatRawPercent(trade.pnl_percent)) +
                        ') | R:R: ' + escapeHtml(formatRatio(trade.rr_achieved)) + '</div>' +
                '</div>' +
                '<div class="journal-detail-block">' +
                    '<h4>Trade Legs</h4>' + renderLegsTable(legs) +
                '</div>' +
                '<div class="journal-detail-block">' +
                    '<h4>Pivot Recommendation</h4>' +
                    '<div>Conviction: <strong>' + escapeHtml(String(trade.pivot_conviction || '--')) + '</strong></div>' +
                    '<div>' + escapeHtml(String(trade.pivot_recommendation || 'No recommendation stored.')) + '</div>' +
                '</div>' +
                '<div class="journal-detail-block">' +
                    '<h4>Context Snapshot</h4>' +
                    '<pre style="white-space:pre-wrap;word-break:break-word;max-height:220px;overflow:auto;">' + (contextText || '{}') + '</pre>' +
                '</div>' +
                '<div class="journal-detail-block">' +
                    '<h4>Notes</h4>' +
                    '<div>' + escapeHtml(String(trade.notes || '--')) + '</div>' +
                '</div>';

            var jtb = byId('journalTableBody');
            if (jtb) {
                jtb.querySelectorAll('tr[data-trade-id]').forEach(function (row) {
                    row.classList.toggle('selected', asNumber(row.getAttribute('data-trade-id'), 0) === tradeId);
                });
            }
        });
    }

    function loadTradeJournal() {
        var filters = getJournalFilters();
        state.journal.filters = filters;

        var body = byId('journalTableBody');
        if (body) {
            body.innerHTML = '<tr><td colspan="13" class="analytics-empty">Loading trades...</td></tr>';
        }

        Promise.all([
            fetchJson('/trades', {
                account: filters.account,
                direction: filters.direction,
                structure: filters.structure,
                origin: filters.origin,
                signal_source: filters.signal_source,
                days: filters.days,
                search: filters.search,
                limit: 400,
                offset: 0
            }),
            fetchJson('/trade-stats', {
                account: filters.account,
                ticker: filters.search,
                direction: filters.direction,
                structure: filters.structure,
                origin: filters.origin,
                signal_source: filters.signal_source,
                days: filters.days
            })
        ]).then(function (results) {
            var tradesPayload = results[0];
            var statsPayload = results[1];
            var rows = safeArray(tradesPayload ? tradesPayload.rows : []);
            state.journal.rows = rows;
            renderJournalTable(rows);
            renderJournalSummary(statsPayload, rows.length);

            var sourceOptions = rows
                .map(function (row) { return row.signal_source || row.linked_signal_strategy; })
                .filter(Boolean);
            refreshSourceFilterOptions(sourceOptions);

            if (state.journal.selectedTradeId) {
                var stillPresent = rows.some(function (row) { return asNumber(row.id, 0) === state.journal.selectedTradeId; });
                if (stillPresent) {
                    loadTradeDetails(state.journal.selectedTradeId);
                } else {
                    state.journal.selectedTradeId = null;
                    var details = byId('journalTradeDetails');
                    if (details) details.innerHTML = '<div class="analytics-empty">Click a trade row to view legs, recommendation, and context.</div>';
                }
            }
        }).catch(function (error) {
            console.error('Trade journal load failed:', error);
            if (body) {
                body.innerHTML = '<tr><td colspan="13" class="analytics-empty">Trade journal error: ' + escapeHtml(error.message || 'unknown') + '</td></tr>';
            }
        });
    }

    function loadChronicle() {
        loadTradeJournal();

        var acctEl = byId('analyticsEquityAccount');
        var rangeEl = byId('analyticsEquityRange');
        var account = acctEl ? acctEl.value : '';
        var days = asNumber(rangeEl ? rangeEl.value : 30, 30);

        fetchJson('/trade-stats', { days: days, account: account }).then(function (tradeStats) {
            renderKeyMetrics(tradeStats || {});
            renderEquityChart(tradeStats || {});
        }).catch(function (e) {
            console.warn('Chronicle equity load failed:', e);
        });
    }

    /* ── Trade form helpers ──────────────────────────────────────────── */

    function collectTradeFormPayload() {
        var tickerEl = byId('journalFormTicker');
        var dirEl = byId('journalFormDirection');
        var strEl = byId('journalFormStructure');
        var entryEl = byId('journalFormEntry');
        var stopEl = byId('journalFormStop');
        var t1El = byId('journalFormTarget1');
        var qtyEl = byId('journalFormQuantity');
        var acctEl = byId('journalFormAccount');
        var srcEl = byId('journalFilterSource');
        var notesEl = byId('journalFormNotes');

        var ticker = tickerEl ? (tickerEl.value || '').trim().toUpperCase() : '';
        var direction = dirEl ? dirEl.value : '';
        var structure = strEl ? (strEl.value || '').trim() : '';
        var entryPrice = entryEl ? entryEl.value : '';
        var stopLoss = stopEl ? stopEl.value : '';
        var target1 = t1El ? t1El.value : '';
        var quantity = qtyEl ? qtyEl.value : '';

        var entry = entryPrice === '' ? null : asNumber(entryPrice, NaN);
        var stop = stopLoss === '' ? null : asNumber(stopLoss, NaN);
        var qty = quantity === '' ? null : asNumber(quantity, NaN);

        var riskAmount = null;
        if (isFinite(entry) && isFinite(stop) && isFinite(qty)) {
            riskAmount = Math.abs(entry - stop) * Math.abs(qty);
        }

        return {
            ticker: ticker,
            direction: direction || null,
            structure: structure || null,
            account: acctEl ? acctEl.value || null : null,
            signal_source: srcEl ? srcEl.value || null : null,
            entry_price: isFinite(entry) ? entry : null,
            stop_loss: isFinite(stop) ? stop : null,
            target_1: target1 === '' ? null : asNumber(target1, NaN),
            quantity: isFinite(qty) ? qty : null,
            notes: notesEl ? (notesEl.value || '').trim() || null : null,
            status: 'open',
            risk_amount: isFinite(riskAmount) ? Number(riskAmount.toFixed(4)) : null,
            full_context: {}
        };
    }

    function clearTradeForm() {
        var ids = [
            'journalFormTicker', 'journalFormDirection', 'journalFormStructure',
            'journalFormEntry', 'journalFormStop', 'journalFormTarget1',
            'journalFormTarget2', 'journalFormQuantity', 'journalFormAccount',
            'journalFormNotes'
        ];
        ids.forEach(function (id) {
            var node = byId(id);
            if (!node) return;
            if (node.tagName === 'SELECT') { node.selectedIndex = 0; }
            else { node.value = ''; }
        });
    }

    function submitTradeForm() {
        var payload = collectTradeFormPayload();
        if (!payload.ticker) {
            window.alert('Ticker is required.');
            return;
        }
        fetchJson('/log-trade', {}, { method: 'POST', body: payload }).then(function () {
            clearTradeForm();
            var card = byId('journalLogTradeCard');
            if (card) card.hidden = true;
            loadTradeJournal();
        }).catch(function (error) {
            console.error('Trade save failed:', error);
            window.alert('Failed to save trade: ' + (error.message || 'unknown error'));
        });
    }

    /* ── Import / CSV helpers ────────────────────────────────────────── */

    function renderImportPreview(preview, importResult) {
        var container = byId('journalImportPreview');
        var confirmBtn = byId('journalImportConfirmBtn');
        if (!container) return;

        if (importResult) {
            if (confirmBtn) confirmBtn.disabled = true;
            var errors = safeArray(importResult.errors);
            container.innerHTML =
                '<div class="analytics-summary-row">' +
                    'Imported: ' + asNumber(importResult.imported) +
                    ' | Signal matched: ' + asNumber(importResult.signal_matched) +
                    ' | Duplicates skipped: ' + asNumber(importResult.duplicates_skipped) +
                    ' | Open positions: ' + asNumber(importResult.open_positions) +
                    ' | Total P&L: ' + formatDollar(importResult.total_pnl) +
                '</div>' +
                (errors.length
                    ? '<div class="analytics-empty">Errors: ' + escapeHtml(errors.join(' | ')) + '</div>'
                    : '<div class="analytics-empty">Import complete.</div>');
            return;
        }

        var closedTrades = safeArray(preview ? preview.trades : []);
        var openTrades = safeArray(preview ? preview.open_positions : []);
        var combined = closedTrades.concat(openTrades);
        var warnings = safeArray(preview ? preview.warnings : []);
        if (!combined.length) {
            if (confirmBtn) confirmBtn.disabled = true;
            container.innerHTML = '<div class="analytics-empty">No trades parsed. Upload a CSV or paste trades, then click Parse.</div>';
            return;
        }

        if (confirmBtn) confirmBtn.disabled = false;
        var previewRows = combined.slice(0, 40).map(function (trade, idx) {
            var ticker = String(trade.ticker || '--').toUpperCase();
            var structure = String(trade.structure || '--');
            var entry = formatDate(trade.entry_date || trade.opened_at);
            var exit = (trade.exit_date || trade.closed_at) ? formatDate(trade.exit_date || trade.closed_at) : '--';
            var pnl = trade.pnl_dollars !== null && trade.pnl_dollars !== undefined ? formatDollar(trade.pnl_dollars) : '--';
            var status = String(trade.status || (trade.exit_date ? 'closed' : 'open')).toLowerCase();
            return '<tr>' +
                '<td>' + (idx + 1) + '</td>' +
                '<td>' + escapeHtml(ticker) + '</td>' +
                '<td>' + escapeHtml(structure) + '</td>' +
                '<td>' + escapeHtml(entry) + '</td>' +
                '<td>' + escapeHtml(exit) + '</td>' +
                '<td>' + escapeHtml(pnl) + '</td>' +
                '<td>' + escapeHtml(status) + '</td>' +
                '</tr>';
        }).join('');

        var warningHtml = warnings.length
            ? '<div class="analytics-empty">' + warnings.map(function (w) { return escapeHtml(String(w)); }).join('<br>') + '</div>'
            : '';

        container.innerHTML =
            '<div class="analytics-summary-row">' +
                'Format: ' + escapeHtml(preview ? preview.format_detected || 'unknown' : 'unknown') +
                ' | Raw rows: ' + asNumber(preview ? preview.raw_transactions : 0) +
                ' | Parsed legs: ' + asNumber(preview ? preview.filtered_transactions : 0) +
                ' | Grouped trades: ' + asNumber(preview ? preview.grouped_trades : 0) +
            '</div>' +
            '<div class="analytics-summary-row">' +
                'Closed trades: ' + closedTrades.length + ' | Open positions: ' + openTrades.length +
            '</div>' +
            '<div class="analytics-table-wrap journal-import-preview">' +
                '<table class="analytics-table">' +
                    '<thead><tr><th>#</th><th>Ticker</th><th>Structure</th><th>Entry</th><th>Exit</th><th>P&L $</th><th>Status</th></tr></thead>' +
                    '<tbody>' + previewRows + '</tbody>' +
                '</table>' +
            '</div>' +
            warningHtml;
    }

    function parseImportTradesInput() {
        var fileInput = byId('journalImportCsv');
        var textInput = byId('journalImportText');
        var confirmBtn = byId('journalImportConfirmBtn');
        var csvFile = (fileInput && fileInput.files && fileInput.files[0]) || null;
        var pastedText = textInput ? (textInput.value || '').trim() : '';

        if (confirmBtn) confirmBtn.disabled = true;
        if (!csvFile && !pastedText) {
            renderImportPreview(null);
            return;
        }

        var promise;
        if (csvFile) {
            var formData = new FormData();
            formData.append('file', csvFile);
            promise = fetchForm('/parse-robinhood-csv', formData);
        } else {
            var payload = null;
            try {
                var parsed = JSON.parse(pastedText);
                if (Array.isArray(parsed)) {
                    payload = {
                        format_detected: 'json_array',
                        raw_transactions: parsed.length,
                        filtered_transactions: parsed.length,
                        grouped_trades: parsed.length,
                        trades: parsed,
                        open_positions: [],
                        warnings: ['Parsed as JSON array.']
                    };
                }
            } catch (_) { /* fall through */ }

            if (payload) {
                promise = Promise.resolve(payload);
            } else {
                var fd = new FormData();
                var blob = new Blob([pastedText], { type: 'text/csv' });
                fd.append('file', blob, 'pasted_trades.csv');
                promise = fetchForm('/parse-robinhood-csv', fd);
            }
        }

        promise.then(function (preview) {
            state.journal.pendingImportPreview = preview;
            renderImportPreview(preview);
        }).catch(function (error) {
            console.error('Trade import parse failed:', error);
            state.journal.pendingImportPreview = null;
            if (confirmBtn) confirmBtn.disabled = true;
            var container = byId('journalImportPreview');
            if (container) {
                container.innerHTML = '<div class="analytics-empty">Parse failed: ' + escapeHtml(error.message || 'unknown') + '</div>';
            }
        });
    }

    function confirmImportTrades() {
        var preview = state.journal.pendingImportPreview;
        if (!preview) {
            window.alert('Parse trades first.');
            return;
        }
        var trades = safeArray(preview.trades).concat(safeArray(preview.open_positions));
        if (!trades.length) {
            window.alert('No parsed trades to import.');
            return;
        }

        fetchJson('/import-trades', {}, {
            method: 'POST',
            body: { account: 'robinhood', trades: trades }
        }).then(function (result) {
            renderImportPreview(preview, result);
            state.journal.pendingImportPreview = null;
            var fileInput = byId('journalImportCsv');
            var textInput = byId('journalImportText');
            if (fileInput) fileInput.value = '';
            if (textInput) textInput.value = '';
            loadTradeJournal();
        }).catch(function (error) {
            console.error('Trade import failed:', error);
            window.alert('Import failed: ' + (error.message || 'unknown error'));
        });
    }

    /* ══════════════════════════════════════════════════════════════════
       2. SIGNAL EXPLORER  SUB-TAB
       ══════════════════════════════════════════════════════════════════ */

    function getSignalFilters() {
        var srcEl = byId('signalFilterSource');
        var sourceValue = srcEl ? srcEl.value : '';
        var source = sourceValue || state.selectedSignalSource || '';
        var tickerEl = byId('signalFilterTicker');
        var dirEl = byId('signalFilterDirection');
        var convEl = byId('signalFilterConviction');
        var regEl = byId('signalFilterRegime');
        var dayEl = byId('signalFilterDay');
        var hourEl = byId('signalFilterHour');
        var daysEl = byId('signalFilterDays');
        return {
            source: source,
            ticker: tickerEl ? (tickerEl.value || '').trim().toUpperCase() : '',
            direction: dirEl ? dirEl.value : '',
            conviction: convEl ? convEl.value : '',
            bias_regime: regEl ? regEl.value : '',
            day_of_week: dayEl ? dayEl.value : '',
            hour_of_day: hourEl ? hourEl.value : '',
            days: asNumber(daysEl ? daysEl.value : 30, 30),
            sort_by: state.signalExplorer.sortBy,
            sort_dir: state.signalExplorer.sortDir,
            limit: 250,
            offset: 0
        };
    }

    function renderSignalStatsPanel(stats) {
        var panel = byId('signalStatsPanel');
        if (!panel) return;

        var accuracy = (stats && stats.accuracy) || {};
        var accuracyByDay = accuracy.by_day_of_week || {};
        var accuracyByHour = accuracy.by_hour || {};
        var accuracyByRegime = accuracy.by_regime || {};

        var dayEntries = Object.keys(accuracyByDay).map(function (k) { return [String(k), asNumber(accuracyByDay[k], 0)]; });
        var hourEntries = Object.keys(accuracyByHour).map(function (k) { return [String(k), asNumber(accuracyByHour[k], 0)]; });
        var regimeEntries = Object.keys(accuracyByRegime).map(function (k) { return [String(k), asNumber(accuracyByRegime[k], 0)]; });

        var bestDay = dayEntries.sort(function (a, b) { return b[1] - a[1]; })[0];
        var worstDay = dayEntries.sort(function (a, b) { return a[1] - b[1]; })[0];
        var bestHour = hourEntries.sort(function (a, b) { return b[1] - a[1]; })[0];
        var worstHour = hourEntries.sort(function (a, b) { return a[1] - b[1]; })[0];
        var bestRegime = regimeEntries.sort(function (a, b) { return b[1] - a[1]; })[0];
        var worstRegime = regimeEntries.sort(function (a, b) { return a[1] - b[1]; })[0];

        var excursion = (stats && stats.excursion) || {};
        var convergence = (stats && stats.convergence) || {};

        var metrics = [
            ['Signals', String(asNumber(stats ? stats.total_signals : 0, 0))],
            ['Accuracy', formatPercent(accuracy.overall)],
            ['False Signal Rate', formatPercent(stats ? stats.false_signal_rate : null)],
            ['Avg MFE', formatRawPercent(excursion.avg_mfe_pct)],
            ['Avg MAE', formatRawPercent(excursion.avg_mae_pct)],
            ['MFE/MAE Ratio', asNumber(excursion.mfe_mae_ratio).toFixed(2)],
            ['Avg Time to MFE', asNumber(stats ? stats.avg_time_to_mfe_hours : 0).toFixed(2) + 'h'],
            ['Convergence Accuracy', formatPercent(convergence.convergence_accuracy)],
            ['Solo Accuracy', formatPercent(convergence.solo_accuracy)],
            ['Best Day', bestDay ? bestDay[0] + ' (' + (bestDay[1] * 100).toFixed(1) + '%)' : '--'],
            ['Worst Day', worstDay ? worstDay[0] + ' (' + (worstDay[1] * 100).toFixed(1) + '%)' : '--'],
            ['Best Hour', bestHour ? bestHour[0] + ' (' + (bestHour[1] * 100).toFixed(1) + '%)' : '--'],
            ['Worst Hour', worstHour ? worstHour[0] + ' (' + (worstHour[1] * 100).toFixed(1) + '%)' : '--'],
            ['Best Regime', bestRegime ? bestRegime[0] + ' (' + (bestRegime[1] * 100).toFixed(1) + '%)' : '--'],
            ['Worst Regime', worstRegime ? worstRegime[0] + ' (' + (worstRegime[1] * 100).toFixed(1) + '%)' : '--']
        ];

        panel.innerHTML = metrics.map(function (m) {
            return '<div class="analytics-metric-item">' +
                '<span class="analytics-metric-label">' + escapeHtml(m[0]) + '</span>' +
                '<span class="analytics-metric-value">' + escapeHtml(m[1]) + '</span>' +
                '</div>';
        }).join('');
    }

    function buildHistogram(values, bucketSize, minBound, maxBound) {
        if (bucketSize === undefined) bucketSize = 0.5;
        if (minBound === undefined) minBound = -3;
        if (maxBound === undefined) maxBound = 3;
        var bins = [];
        for (var b = minBound; b < maxBound; b += bucketSize) {
            bins.push({ min: b, max: b + bucketSize, count: 0 });
        }
        safeArray(values).forEach(function (value) {
            var n = asNumber(value, NaN);
            if (!isFinite(n)) return;
            for (var i = 0; i < bins.length; i++) {
                if (n >= bins[i].min && n < bins[i].max) {
                    bins[i].count += 1;
                    return;
                }
            }
            if (n === maxBound && bins.length) {
                bins[bins.length - 1].count += 1;
            }
        });
        return bins;
    }

    function renderSignalExplorerCharts(signalRows, stats) {
        var rows = safeArray(signalRows);
        var mfeValues = rows.map(function (row) { return asNumber(row.mfe_pct, 0); });
        var maeValues = rows.map(function (row) { return -Math.abs(asNumber(row.mae_pct, 0)); });
        var mfeBins = buildHistogram(mfeValues, 0.5, -3, 5);
        var maeBins = buildHistogram(maeValues, 0.5, -5, 3);
        var labels = mfeBins.map(function (bin) { return bin.min.toFixed(1) + '..' + bin.max.toFixed(1); });

        localUpsertChart('signalMfeMae', 'signalMfeMaeChart', {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [
                    { label: 'MFE', data: mfeBins.map(function (b) { return b.count; }), backgroundColor: 'rgba(0, 230, 118, 0.55)' },
                    { label: 'MAE', data: maeBins.map(function (b) { return b.count; }), backgroundColor: 'rgba(229, 55, 14, 0.55)' }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { ticks: { color: '#89a1c8', maxTicksLimit: 10 }, grid: { color: 'rgba(38,53,85,0.25)' } },
                    y: { ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.25)' } }
                },
                plugins: { legend: { labels: { color: '#9fb7ff' } } }
            }
        });

        var byHour = (stats && stats.accuracy) ? stats.accuracy.by_hour || {} : {};
        var hourLabels = ['9', '10', '11', '12', '13', '14', '15', '16'];
        var hourValues = hourLabels.map(function (hour) { return asNumber(byHour[hour], 0) * 100; });
        var barColors = hourValues.map(function (v) {
            return 'rgba(' + Math.round(229 - (v * 1.7)) + ', ' + Math.round(55 + (v * 1.8)) + ', 120, 0.75)';
        });

        localUpsertChart('signalAccuracyHour', 'signalAccuracyHourChart', {
            type: 'bar',
            data: {
                labels: hourLabels,
                datasets: [{ label: 'Accuracy %', data: hourValues, backgroundColor: barColors, borderColor: '#2d3b59', borderWidth: 1 }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.25)' } },
                    y: { min: 0, max: 100, ticks: { color: '#89a1c8', callback: function (v) { return v + '%'; } }, grid: { color: 'rgba(38,53,85,0.25)' } }
                },
                plugins: { legend: { labels: { color: '#9fb7ff' } } }
            }
        });
    }

    function renderSignalTable(rows) {
        var tbody = byId('signalExplorerTableBody');
        var meta = byId('signalTableMeta');
        if (!tbody) return;

        var signals = safeArray(rows);
        if (meta) {
            meta.textContent = signals.length + ' rows | sort: ' + state.signalExplorer.sortBy + ' (' + state.signalExplorer.sortDir + ')';
        }

        if (!signals.length) {
            tbody.innerHTML = '<tr><td colspan="9" class="analytics-empty">Collecting data - metrics will appear after signals accumulate.</td></tr>';
            return;
        }

        tbody.innerHTML = signals.map(function (row) {
            var accurate = row.signal_accuracy;
            var accurateText = accurate === true ? '\u2705' : accurate === false ? '\u274C' : '--';
            var accuracyClass = accurate === true ? 'signal-accurate' : accurate === false ? 'signal-inaccurate' : '';
            var conviction = row.conviction || '--';
            var tradedText = row.traded ? 'Yes' : 'No';
            return '<tr class="' + accuracyClass + '" data-signal-id="' + escapeHtml(row.signal_id) + '">' +
                '<td>' + escapeHtml(formatDateTime(row.timestamp)) + '</td>' +
                '<td>' + escapeHtml(String(row.ticker || '--').toUpperCase()) + '</td>' +
                '<td>' + escapeHtml(String(row.direction || '--').toUpperCase()) + '</td>' +
                '<td>' + escapeHtml(slugToLabel(row.source || row.strategy || row.signal_type)) + '</td>' +
                '<td>' + escapeHtml(conviction) + '</td>' +
                '<td>' + escapeHtml(formatRawPercent(row.mfe_pct)) + '</td>' +
                '<td>' + escapeHtml(formatRawPercent(row.mae_pct)) + '</td>' +
                '<td>' + escapeHtml(accurateText) + '</td>' +
                '<td>' + escapeHtml(tradedText) + '</td>' +
                '</tr>';
        }).join('');

        tbody.querySelectorAll('tr[data-signal-id]').forEach(function (row) {
            row.addEventListener('click', function () {
                var signalId = row.getAttribute('data-signal-id');
                state.signalExplorer.selectedSignalId = signalId;
                renderSignalDetail(signalId);
                tbody.querySelectorAll('tr').forEach(function (tr) { tr.classList.remove('selected'); });
                row.classList.add('selected');
            });
        });
    }

    function renderSignalDetail(signalId) {
        var panel = byId('signalDetailPanel');
        if (!panel) return;
        var row = null;
        for (var i = 0; i < state.signalExplorer.rows.length; i++) {
            if (String(state.signalExplorer.rows[i].signal_id) === String(signalId)) {
                row = state.signalExplorer.rows[i];
                break;
            }
        }
        if (!row) {
            panel.innerHTML = '<div class="analytics-empty">Signal not found.</div>';
            return;
        }
        var payload = {
            signal_id: row.signal_id,
            strategy: row.strategy,
            signal_type: row.signal_type,
            direction: row.direction,
            conviction: row.conviction,
            timeframe: row.timeframe,
            bias_level: row.bias_level,
            entry_price: row.entry_price,
            stop_loss: row.stop_loss,
            target_1: row.target_1,
            target_2: row.target_2,
            score: row.score,
            notes: row.notes
        };
        var triggering = row.triggering_factors || {};
        var marketState = row.bias_at_signal || {};
        var convergenceIds = safeArray(row.convergence_ids);
        panel.innerHTML =
            '<div class="journal-detail-block">' +
                '<h4>Signal Payload</h4>' +
                '<pre style="white-space:pre-wrap;word-break:break-word;max-height:160px;overflow:auto;">' + escapeHtml(JSON.stringify(payload, null, 2)) + '</pre>' +
            '</div>' +
            '<div class="journal-detail-block">' +
                '<h4>Market State Snapshot</h4>' +
                '<pre style="white-space:pre-wrap;word-break:break-word;max-height:160px;overflow:auto;">' + escapeHtml(JSON.stringify(marketState, null, 2)) + '</pre>' +
            '</div>' +
            '<div class="journal-detail-block">' +
                '<h4>Factor Scores</h4>' +
                '<pre style="white-space:pre-wrap;word-break:break-word;max-height:140px;overflow:auto;">' + escapeHtml(JSON.stringify(triggering, null, 2)) + '</pre>' +
            '</div>' +
            '<div class="journal-detail-block">' +
                '<h4>Convergence IDs</h4>' +
                '<div>' + (convergenceIds.length ? convergenceIds.map(function (id) { return '<span class="signal-tag">' + escapeHtml(id) + '</span>'; }).join('') : 'None') + '</div>' +
            '</div>';
    }

    function loadSignalExplorer() {
        var filters = getSignalFilters();
        var srcSelect = byId('signalFilterSource');
        if (state.selectedSignalSource && srcSelect && !srcSelect.value) {
            srcSelect.value = state.selectedSignalSource;
        }

        Promise.all([
            fetchJson('/signals', filters),
            fetchJson('/signal-stats', filters)
        ]).then(function (results) {
            var rawPayload = results[0];
            var stats = results[1];
            var rows = safeArray(rawPayload ? rawPayload.rows : []);
            state.signalExplorer.rows = rows;
            renderSignalTable(rows);
            renderSignalStatsPanel(stats || {});
            renderSignalExplorerCharts(rows, stats || {});
            var sourceOptions = rows.map(function (row) { return row.source || row.strategy || row.signal_type; }).filter(Boolean);
            refreshSourceFilterOptions(sourceOptions);

            if (state.signalExplorer.selectedSignalId) {
                renderSignalDetail(state.signalExplorer.selectedSignalId);
            } else if (rows.length) {
                state.signalExplorer.selectedSignalId = rows[0].signal_id;
                renderSignalDetail(rows[0].signal_id);
            }
        }).catch(function (error) {
            console.error('Signal explorer load failed:', error);
            var tbody = byId('signalExplorerTableBody');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="9" class="analytics-empty">Signal explorer error: ' + escapeHtml(error.message || 'unknown') + '</td></tr>';
            }
            var panel = byId('signalStatsPanel');
            if (panel) panel.innerHTML = '<div class="analytics-empty">Unable to load stats.</div>';
        });
    }

    /* ══════════════════════════════════════════════════════════════════
       3. FACTOR LAB  SUB-TAB
       ══════════════════════════════════════════════════════════════════ */

    function normalizeFactor(v) { return String(v || '').trim(); }

    function populateFactorSelectors(factors) {
        var factorSelect = byId('factorLabFactorSelect');
        var compareSelect = byId('factorLabCompareSelect');
        if (!factorSelect || !compareSelect) return;

        var factorNames = safeArray(factors).map(function (f) { return normalizeFactor(f.name); }).filter(Boolean);
        if (!factorNames.length) return;
        if (!state.factorLab.selectedFactor) {
            state.factorLab.selectedFactor = factorNames[0];
        }

        var renderOptions = function (select, label) {
            var current = select.value;
            select.innerHTML = '<option value="">' + label + '</option>';
            factorNames.forEach(function (name) {
                var opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                select.appendChild(opt);
            });
            if (factorNames.indexOf(current) >= 0) {
                select.value = current;
            }
        };

        renderOptions(factorSelect, 'Select Factor');
        renderOptions(compareSelect, 'Compare With (Optional)');

        factorSelect.value = state.factorLab.selectedFactor;
        if (state.factorLab.compareFactor) {
            compareSelect.value = state.factorLab.compareFactor;
        }
    }

    function renderFactorTimelineChart(factor, compareFactor, spyRows) {
        var mainTimeline = safeArray(factor ? factor.timeline : []);
        var compareTimeline = safeArray(compareFactor ? compareFactor.timeline : []);
        var dateSet = {};
        mainTimeline.forEach(function (row) { dateSet[String(row.date)] = true; });
        compareTimeline.forEach(function (row) { dateSet[String(row.date)] = true; });
        safeArray(spyRows).forEach(function (row) { dateSet[String(row.date)] = true; });
        var labels = Object.keys(dateSet).sort(function (a, b) { return new Date(a) - new Date(b); });

        var mainMap = buildFactorValueMap(mainTimeline, 'date', 'score');
        var compareMap = buildFactorValueMap(compareTimeline, 'date', 'score');
        var spyMap = buildFactorValueMap(spyRows, 'date', 'close');

        var mainValues = labels.map(function (d) { return d in mainMap ? mainMap[d] : null; });
        var compareValues = labels.map(function (d) { return d in compareMap ? compareMap[d] : null; });
        var spyValues = labels.map(function (d) { return d in spyMap ? spyMap[d] : null; });

        var correctness = labels.map(function (date, idx) {
            var score = mainValues[idx];
            var currentClose = spyValues[idx];
            var nextClose = spyValues[idx + 1];
            if (!isFinite(score) || !isFinite(currentClose) || !isFinite(nextClose)) return null;
            var nextMove = nextClose - currentClose;
            var match = (score < 0 && nextMove < 0) || (score > 0 && nextMove > 0);
            return match ? 2 : null;
        });

        var datasets = [
            { label: (factor ? factor.name : 'factor') + ' score', data: mainValues, stepped: true, borderColor: '#14b8a6', backgroundColor: 'rgba(20,184,166,0.08)', borderWidth: 2, yAxisID: 'y', pointRadius: 0 },
            { label: 'Correct Direction', data: correctness, type: 'bar', yAxisID: 'shade', backgroundColor: 'rgba(0, 230, 118, 0.08)', borderWidth: 0 },
            { label: 'SPY Close', data: spyValues, borderColor: '#9fb7ff', borderWidth: 1.8, tension: 0.2, yAxisID: 'y1', pointRadius: 0 }
        ];

        if (compareFactor) {
            datasets.push({
                label: compareFactor.name + ' score', data: compareValues, stepped: true,
                borderColor: '#fbc02d', borderWidth: 1.8, yAxisID: 'y', pointRadius: 0
            });
        }

        localUpsertChart('factorTimeline', 'factorLabTimelineChart', {
            type: 'line',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true, maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: { ticks: { color: '#89a1c8', maxTicksLimit: 10 }, grid: { color: 'rgba(38,53,85,0.25)' } },
                    y: { min: -2, max: 2, ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.25)' } },
                    y1: { position: 'right', ticks: { color: '#89a1c8' }, grid: { drawOnChartArea: false } },
                    shade: { display: false, min: 0, max: 2, stacked: true }
                },
                plugins: { legend: { labels: { color: '#9fb7ff' } } }
            }
        });
    }

    function renderFactorStats(factor) {
        var accuracyCard = byId('factorLabAccuracyCard');
        var staleCard = byId('factorLabStaleCard');
        var regimeCard = byId('factorLabBestRegimeCard');
        var corrCard = byId('factorLabCorrelationCard');
        if (!factor || !accuracyCard || !staleCard || !regimeCard || !corrCard) return;

        accuracyCard.innerHTML =
            '<div class="analytics-card-header"><h3>Accuracy</h3></div>' +
            '<div class="factor-stat-line">When URSA: ' + (asNumber(factor.accuracy_when_ursa) * 100).toFixed(1) + '%</div>' +
            '<div class="factor-stat-line">When TORO: ' + (asNumber(factor.accuracy_when_toro) * 100).toFixed(1) + '%</div>' +
            '<div class="factor-stat-line">Overall: ' + (((asNumber(factor.accuracy_when_ursa) + asNumber(factor.accuracy_when_toro)) / 2) * 100).toFixed(1) + '%</div>';

        staleCard.innerHTML =
            '<div class="analytics-card-header"><h3>Stale Rate</h3></div>' +
            '<div class="factor-stat-line">' + (asNumber(factor.stale_pct) * 100).toFixed(2) + '% stale readings</div>' +
            '<div class="factor-stat-line">Last stale: ' + escapeHtml(factor.last_stale_date || '--') + '</div>';

        regimeCard.innerHTML =
            '<div class="analytics-card-header"><h3>Best Regime</h3></div>' +
            '<div class="factor-stat-line">' + escapeHtml(String(factor.best_regime || '--')) + '</div>' +
            '<div class="factor-stat-line">Avg score: ' + asNumber(factor.avg_score).toFixed(2) + '</div>';

        corrCard.innerHTML =
            '<div class="analytics-card-header"><h3>Correlation</h3></div>' +
            '<div class="factor-stat-line">Strongest: ' + escapeHtml(String(factor.most_correlated_with || '--')) + '</div>' +
            '<div class="factor-stat-line">SPY next-day r: ' + asNumber(factor.correlation_with_spy_next_day).toFixed(2) + '</div>';
    }

    function correlationColor(value) {
        var v = Math.max(-1, Math.min(1, asNumber(value, 0)));
        if (v >= 0) {
            var g = Math.round(120 + (v * 100));
            var r = Math.round(255 - (v * 160));
            var b = Math.round(255 - (v * 180));
            return 'rgb(' + r + ', ' + g + ', ' + b + ')';
        }
        var n = Math.abs(v);
        return 'rgb(' + Math.round(170 + (n * 70)) + ', ' + Math.round(160 - (n * 120)) + ', ' + Math.round(160 - (n * 120)) + ')';
    }

    function renderCorrelationMatrix(matrix) {
        var container = byId('factorLabCorrelationMatrix');
        if (!container) return;
        var names = Object.keys(matrix || {});
        if (!names.length) {
            container.innerHTML = '<div class="analytics-empty">Collecting data - matrix will appear after factor history accumulates.</div>';
            return;
        }
        var header = names.map(function (name) { return '<th>' + escapeHtml(name) + '</th>'; }).join('');
        var rows = names.map(function (rowName) {
            var cols = names.map(function (colName) {
                var value = rowName === colName ? 1.0 : asNumber(matrix[rowName] ? matrix[rowName][colName] : 0, 0);
                var bg = correlationColor(value);
                return '<td style="background:' + bg + '" title="' + escapeHtml(rowName + ' vs ' + colName + ': ' + value.toFixed(3)) + '">' + value.toFixed(2) + '</td>';
            }).join('');
            return '<tr><td class="corr-header">' + escapeHtml(rowName) + '</td>' + cols + '</tr>';
        }).join('');
        container.innerHTML =
            '<table class="correlation-table">' +
                '<thead><tr><th></th>' + header + '</tr></thead>' +
                '<tbody>' + rows + '</tbody>' +
            '</table>';
    }

    function loadFactorLab() {
        var daysEl = byId('factorLabDays');
        var days = asNumber(daysEl ? daysEl.value : 60, 60);
        state.factorLab.days = days;

        fetchJson('/factor-performance', { days: days }).then(function (perf) {
            var factors = safeArray(perf ? perf.factors : []);
            if (!factors.length) {
                var matrixEl = byId('factorLabCorrelationMatrix');
                if (matrixEl) matrixEl.innerHTML = '<div class="analytics-empty">Collecting data - metrics will appear after factor history accumulates.</div>';
                return;
            }

            state.factorLab.factors = factors;
            populateFactorSelectors(factors);
            var fSelect = byId('factorLabFactorSelect');
            var cSelect = byId('factorLabCompareSelect');
            state.factorLab.selectedFactor = (fSelect ? fSelect.value : '') || state.factorLab.selectedFactor || factors[0].name;
            state.factorLab.compareFactor = cSelect ? cSelect.value : '';
            var mainFactor = null;
            var compareFactor = null;
            for (var i = 0; i < factors.length; i++) {
                if (factors[i].name === state.factorLab.selectedFactor) mainFactor = factors[i];
                if (factors[i].name === state.factorLab.compareFactor) compareFactor = factors[i];
            }
            if (!mainFactor) mainFactor = factors[0];

            return fetchJson('/price-data', { ticker: 'SPY', timeframe: 'D', days: days }).then(function (pricePayload) {
                renderFactorTimelineChart(mainFactor, compareFactor, safeArray(pricePayload ? pricePayload.rows : []));
                renderFactorStats(mainFactor);
                renderCorrelationMatrix((perf && perf.correlation_matrix) || {});
            });
        }).catch(function (error) {
            console.error('Factor lab load failed:', error);
            var matrixEl = byId('factorLabCorrelationMatrix');
            if (matrixEl) matrixEl.innerHTML = '<div class="analytics-empty">Factor lab error: ' + escapeHtml(error.message || 'unknown') + '</div>';
        });
    }

    /* ══════════════════════════════════════════════════════════════════
       4. BACKTEST  SUB-TAB
       ══════════════════════════════════════════════════════════════════ */

    function initBacktestDefaults() {
        var now = new Date();
        var end = now.toISOString().slice(0, 10);
        var startDate = new Date(now.getTime() - (1000 * 60 * 60 * 24 * 120)).toISOString().slice(0, 10);
        ['backtestEndDate', 'backtestCompareEndDate'].forEach(function (id) {
            var node = byId(id);
            if (node && !node.value) node.value = end;
        });
        ['backtestStartDate', 'backtestCompareStartDate'].forEach(function (id) {
            var node = byId(id);
            if (node && !node.value) node.value = startDate;
        });
    }

    function collectBacktestPayload(compare) {
        var pfx = compare ? 'backtestCompare' : 'backtest';
        var stratEl = byId(pfx + 'Strategy');
        var tickerEl = byId(pfx + 'Ticker');
        var dirEl = byId(pfx + 'Direction');
        var startEl = byId(pfx + 'StartDate');
        var endEl = byId(pfx + 'EndDate');
        var stopEl = byId(pfx + 'StopPct');
        var targetEl = byId(pfx + 'TargetPct');
        var riskEl = byId(pfx + 'RiskPerTrade');
        var convEl = byId(pfx + 'MinConviction');
        var convgEl = byId(pfx + 'RequireConvergence');
        var biasEl = byId(pfx + 'BiasAlign');

        return {
            source: stratEl ? stratEl.value || 'whale_hunter' : 'whale_hunter',
            ticker: tickerEl ? (tickerEl.value || '').trim().toUpperCase() || null : null,
            direction: dirEl ? dirEl.value || null : null,
            start_date: startEl ? startEl.value : '',
            end_date: endEl ? endEl.value : '',
            params: {
                entry: 'signal_price',
                stop_distance_pct: asNumber(stopEl ? stopEl.value : 0.5, 0.5),
                target_distance_pct: asNumber(targetEl ? targetEl.value : 1.0, 1.0),
                risk_per_trade: asNumber(riskEl ? riskEl.value : 235, 235),
                min_conviction: convEl ? convEl.value || null : null,
                require_convergence: convgEl ? !!convgEl.checked : false,
                bias_must_align: biasEl ? !!biasEl.checked : false
            }
        };
    }

    function renderBacktestTrades(rows) {
        var tbody = byId('backtestTradesBody');
        if (!tbody) return;
        var trades = safeArray(rows);
        if (!trades.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="analytics-empty">No simulated trades for this configuration.</td></tr>';
            return;
        }
        tbody.innerHTML = trades.map(function (row) {
            var pnl = asNumber(row.pnl, 0);
            var cls = pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
            return '<tr>' +
                '<td>' + escapeHtml(String(row.entry_date || '--')) + '</td>' +
                '<td>' + escapeHtml(valOrDash(row.entry_price)) + '</td>' +
                '<td>' + escapeHtml(valOrDash(row.exit_price)) + '</td>' +
                '<td class="' + cls + '">' + escapeHtml(formatDollar(pnl)) + '</td>' +
                '<td>' + escapeHtml(String(row.exit_reason || '--')) + '</td>' +
                '</tr>';
        }).join('');
    }

    function renderBacktestEquityChart(primary, compare) {
        var primaryCurve = safeArray(primary && primary.results ? primary.results.equity_curve : []);
        var compareCurve = safeArray(compare && compare.results ? compare.results.equity_curve : []);
        var dateSet = {};
        primaryCurve.forEach(function (p) { dateSet[String(p.date)] = true; });
        compareCurve.forEach(function (p) { dateSet[String(p.date)] = true; });
        var labels = Object.keys(dateSet).sort(function (a, b) { return new Date(a) - new Date(b); });
        var mainMap = buildFactorValueMap(primaryCurve, 'date', 'cumulative_pnl');
        var compareMap = buildFactorValueMap(compareCurve, 'date', 'cumulative_pnl');

        var datasets = [
            { label: 'Primary', data: labels.map(function (d) { return d in mainMap ? mainMap[d] : null; }), borderColor: '#14b8a6', borderWidth: 2, pointRadius: 0, tension: 0.25 }
        ];
        if (compare) {
            datasets.push({
                label: 'Compare',
                data: labels.map(function (d) { return d in compareMap ? compareMap[d] : null; }),
                borderColor: '#fbc02d', borderWidth: 2, pointRadius: 0, tension: 0.25
            });
        }
        localUpsertChart('backtestEquity', 'backtestEquityChart', {
            type: 'line',
            data: { labels: labels, datasets: datasets },
            options: {
                responsive: true, maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#9fb7ff' } } },
                scales: {
                    x: { ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.25)' } },
                    y: { ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.25)' } }
                }
            }
        });
    }

    function renderBacktestSummary(primary, compare) {
        var panel = byId('backtestResultsPanel');
        if (!panel) return;
        var a = (primary && primary.results) || {};
        var b = (compare && compare.results) || null;
        panel.innerHTML =
            '<div class="analytics-summary-row">' +
                'Trades: ' + asNumber(a.total_trades) + ' | Win Rate: ' + (asNumber(a.win_rate) * 100).toFixed(1) + '% | Total P&L: ' + formatDollar(a.total_pnl) +
                ' | Sharpe: ' + asNumber(a.sharpe).toFixed(2) + ' | Max DD: ' + formatDollar(a.max_drawdown) + ' | Avg R:R: ' + asNumber(a.avg_rr).toFixed(2) +
            '</div>' +
            (b
                ? '<div class="analytics-summary-row">Compare -> Trades: ' + asNumber(b.total_trades) + ' | Win Rate: ' + (asNumber(b.win_rate) * 100).toFixed(1) + '% | Total P&L: ' + formatDollar(b.total_pnl) +
                  ' | Sharpe: ' + asNumber(b.sharpe).toFixed(2) + ' | Max DD: ' + formatDollar(b.max_drawdown) + ' | Avg R:R: ' + asNumber(b.avg_rr).toFixed(2) + '</div>'
                : '');
    }

    function runBacktest(compare) {
        var payload = collectBacktestPayload(compare);
        if (!payload.start_date || !payload.end_date) {
            window.alert('Backtest requires start and end dates.');
            return;
        }
        var panel = byId('backtestResultsPanel');
        if (panel) panel.innerHTML = '<div class="analytics-empty">Running backtest...</div>';

        fetchJson('/backtest', {}, { method: 'POST', body: payload }).then(function (result) {
            if (compare) {
                state.backtest.compare = result;
            } else {
                state.backtest.primary = result;
                state.backtest.compare = null;
                var compareBtn = byId('backtestCompareBtn');
                if (compareBtn) compareBtn.hidden = false;
            }
            renderBacktestSummary(state.backtest.primary, state.backtest.compare);
            renderBacktestEquityChart(state.backtest.primary, state.backtest.compare);
            renderBacktestTrades((state.backtest.primary && state.backtest.primary.results) ? state.backtest.primary.results.trades || [] : []);
            var eqWrap = byId('backtestEquityWrap');
            if (eqWrap) eqWrap.hidden = false;
            var trWrap = byId('backtestTradesWrap');
            if (trWrap) trWrap.hidden = false;
        }).catch(function (error) {
            console.error('Backtest failed:', error);
            if (panel) panel.innerHTML = '<div class="analytics-empty">Backtest error: ' + escapeHtml(error.message || 'unknown') + '</div>';
        });
    }

    /* ══════════════════════════════════════════════════════════════════
       5. FOOTPRINT  SUB-TAB
       ══════════════════════════════════════════════════════════════════ */

    var _fpInterval = null;

    function loadFootprintCorrelation() {
        var BASE = window.location.origin;
        var endDate = new Date('2026-03-28T23:59:59Z');
        var cdEl = byId('footprintCountdown');
        if (cdEl) {
            var now = new Date();
            var daysLeft = Math.max(0, Math.ceil((endDate - now) / 86400000));
            cdEl.textContent = daysLeft > 0
                ? 'Forward test: ' + daysLeft + ' days remaining (ends Mar 28)'
                : 'Forward test period complete \u2014 review results';
        }

        fetch(BASE + '/api/analytics/footprint-correlation?days=14&window_minutes=30')
            .then(function (res) {
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            })
            .then(function (data) {
                renderFootprintBuckets(data.buckets);
                renderFootprintTable(data.signals);
            })
            .catch(function (e) {
                console.error('Footprint correlation load failed:', e);
            });

        if (_fpInterval) clearInterval(_fpInterval);
        _fpInterval = setInterval(function () {
            var pane = byId('labPane_footprint');
            if (pane && !pane.hidden) loadFootprintCorrelation();
            else { clearInterval(_fpInterval); _fpInterval = null; }
        }, 60000);
    }

    function renderFootprintBuckets(buckets) {
        var render = function (elId, bucket) {
            var el = byId(elId);
            if (!el) return;
            var b = bucket || {};
            var countEl = el.querySelector('.footprint-bucket-count');
            if (countEl) countEl.textContent = b.count || 0;
            var wrEl = el.querySelector('.footprint-bucket-wr');
            var wr = b.win_rate != null ? b.win_rate + '% win rate' : (b.pending || 0) + ' pending';
            if (wrEl) wrEl.textContent = wr;
            if (b.win_rate != null) {
                el.style.borderColor = b.win_rate >= 50 ? 'rgba(124,255,107,0.5)' : 'rgba(255,107,53,0.5)';
            }
        };
        if (buckets) {
            render('fpBucketWhale', buckets.whale_solo);
            render('fpBucketFootprint', buckets.footprint_solo);
            render('fpBucketConfluence', buckets.confluence);
        }
    }

    function renderFootprintTable(signals) {
        var tbody = document.querySelector('#footprintSignalsTable tbody');
        if (!tbody) return;
        if (!signals || signals.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--text-secondary);padding:20px;">No signals yet \u2014 waiting for footprint alerts</td></tr>';
            return;
        }
        var sourceLabel = { 'DARK_POOL': 'Whale', 'FOOTPRINT': 'Footprint' };
        var outcomeColor = { win: '#7CFF6B', loss: '#FF6B35', pending: 'var(--text-secondary)', expired: '#94a3b8' };
        tbody.innerHTML = signals.map(function (s) {
            var time = s.created_at ? new Date(s.created_at).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '-';
            var dirClass = s.direction === 'LONG' ? 'color:#7CFF6B' : s.direction === 'SHORT' ? 'color:#FF6B35' : '';
            return '<tr>' +
                '<td>' + time + '</td>' +
                '<td><strong>' + (s.ticker || '') + '</strong></td>' +
                '<td>' + (sourceLabel[s.category] || s.category || '') + '</td>' +
                '<td style="' + dirClass + '">' + (s.direction || '-') + '</td>' +
                '<td>' + (s.bucket === 'confluence' ? '<strong style="color:#14b8a6">Confluence</strong>' : s.bucket === 'whale_solo' ? 'Whale Solo' : 'Footprint Solo') + '</td>' +
                '<td style="color:' + (outcomeColor[s.outcome] || 'inherit') + '">' + (s.outcome || '-') + '</td>' +
                '</tr>';
        }).join('');
    }

    /* ══════════════════════════════════════════════════════════════════
       6. ORACLE  SUB-TAB
       ══════════════════════════════════════════════════════════════════ */

    function loadOracleNarrative(assetClass) {
        var BASE = window.location.origin;
        var acParam = assetClass ? '&asset_class=' + assetClass : '';

        fetch(BASE + '/api/analytics/oracle?days=30' + acParam)
            .then(function (res) {
                if (!res.ok) return null;
                return res.json();
            })
            .then(function (data) {
                if (!data) return;
                var el = byId('oracleNarrative');
                if (el && data.narrative) {
                    el.innerHTML = '<p>"' + escapeHtml(data.narrative) + '"</p><cite>\u2014 The Oracle</cite>';
                }
                renderStrategyScorecards(data.strategy_scorecards || []);
                renderPrometheus(data.decision_quality || {});
                renderCassandra(data.decision_quality || {});
                renderOracleRiskDetails(data);
            })
            .catch(function (e) {
                console.warn('Oracle load failed:', e);
            });

        // Also load risk budget
        fetch(BASE + '/api/analytics/risk-budget')
            .then(function (res) { return res.ok ? res.json() : null; })
            .then(function (data) {
                if (!data) return;
                renderRiskBudget(data);
            })
            .catch(function (e) { console.warn('Risk budget load failed:', e); });
    }

    function renderStrategyScorecards(scorecards) {
        var container = byId('strategyScorecards');
        if (!container) return;
        if (!scorecards.length) {
            container.innerHTML = '<div class="analytics-empty">No strategy data yet.</div>';
            return;
        }

        var sorted = scorecards.slice().sort(function (a, b) { return asNumber(b.expectancy, 0) - asNumber(a.expectancy, 0); });
        var gradeColors = { A: '#22c55e', B: '#3b82f6', C: '#f59e0b', F: '#ef4444' };

        container.innerHTML = sorted.map(function (s) {
            var color = gradeColors[s.grade] || '#6b7280';
            var pnl = asNumber(s.total_pnl, 0);
            var exp = asNumber(s.expectancy, 0);
            return '<div class="analytics-health-card">' +
                '<div class="analytics-health-card-header">' +
                    '<span class="scorecard-grade" style="background:' + color + '">' + escapeHtml(s.grade) + '</span>' +
                    '<span class="analytics-health-source">' + escapeHtml(s.display_name || s.strategy) + '</span>' +
                '</div>' +
                '<div class="analytics-health-card-stats">' +
                    '<span>' + (s.wins || 0) + 'W / ' + (s.losses || 0) + 'L</span>' +
                    '<span class="' + (pnl >= 0 ? 'positive' : 'negative') + '">' + (pnl >= 0 ? '+' : '') + '$' + pnl.toFixed(0) + '</span>' +
                    '<span>Exp: $' + exp.toFixed(2) + '</span>' +
                '</div>' +
                '</div>';
        }).join('');
    }

    function renderPrometheus(dq) {
        var el = byId('prometheusContent');
        if (!el) return;
        if (!dq.total_decisions) {
            el.innerHTML = '<div class="analytics-empty">No decision data yet.</div>';
            return;
        }

        var overrideWR = asNumber(dq.override_win_rate, 0) * 100;
        var agreementRate = asNumber(dq.committee_agreement_rate, 0) * 100;
        var overridePnl = asNumber(dq.override_net_pnl, 0);

        el.innerHTML =
            '<div class="analytics-metric-row"><span>Total Decisions</span><span>' + dq.total_decisions + '</span></div>' +
            '<div class="analytics-metric-row"><span>Overrides</span><span>' + (dq.overrides || 0) + '</span></div>' +
            '<div class="analytics-metric-row"><span>Override Win Rate</span><span>' + overrideWR.toFixed(1) + '%</span></div>' +
            '<div class="analytics-metric-row"><span>Override Net P&L</span><span class="' + (overridePnl >= 0 ? 'positive' : 'negative') + '">' + (overridePnl >= 0 ? '+' : '') + '$' + overridePnl.toFixed(0) + '</span></div>' +
            '<div class="analytics-metric-row"><span>Committee Agreement</span><span>' + agreementRate.toFixed(1) + '%</span></div>' +
            (dq.best_override ? '<div class="analytics-metric-row"><span>Best Override</span><span>' + escapeHtml(dq.best_override.ticker) + ' +$' + asNumber(dq.best_override.pnl, 0).toFixed(0) + '</span></div>' : '') +
            (dq.worst_override ? '<div class="analytics-metric-row"><span>Worst Override</span><span>' + escapeHtml(dq.worst_override.ticker) + ' $' + asNumber(dq.worst_override.pnl, 0).toFixed(0) + '</span></div>' : '');
    }

    function renderCassandra(dq) {
        var el = byId('cassandraContent');
        if (!el) return;
        var wins = asNumber(dq.passed_would_have_won, 0);
        var losses = asNumber(dq.passed_would_have_lost, 0);
        if (!wins && !losses) {
            el.innerHTML = '<div class="analytics-empty">No counterfactual data yet. Dismissed signals will be tracked here.</div>';
            return;
        }

        el.innerHTML =
            '<div class="analytics-metric-row"><span>Passed signals that would have WON</span><span class="positive">' + wins + '</span></div>' +
            '<div class="analytics-metric-row"><span>Passed signals that would have LOST</span><span class="negative">' + losses + '</span></div>' +
            '<div class="analytics-metric-row"><span>Pass accuracy</span><span>' + ((losses / (wins + losses)) * 100).toFixed(0) + '% correctly avoided</span></div>';
    }

    function renderRiskBudget(data) {
        var eqEl = byId('riskBudgetEquity');
        if (eqEl && data.equity) {
            var eq = data.equity;
            eqEl.innerHTML =
                '<div class="analytics-metric-row"><span>Open Positions</span><span>' + eq.open_positions + '</span></div>' +
                '<div class="analytics-metric-row"><span>Total Max Loss</span><span class="negative">$' + asNumber(eq.total_max_loss, 0).toFixed(0) + '</span></div>';
        }

        var crEl = byId('riskBudgetCrypto');
        if (crEl && data.crypto) {
            var cr = data.crypto;
            var ddPct = Math.min(100, (asNumber(cr.total_max_loss, 0) / 1500) * 100);
            crEl.innerHTML =
                '<div class="analytics-metric-row"><span>Open Positions</span><span>' + cr.open_positions + ' / ' + cr.max_concurrent + '</span></div>' +
                '<div class="risk-budget-bar-wrap">' +
                    '<label>Static DD Used</label>' +
                    '<div class="risk-budget-bar"><div class="risk-budget-bar-fill ' + (ddPct > 80 ? 'danger' : ddPct > 50 ? 'warn' : '') + '" style="width:' + ddPct + '%"></div></div>' +
                    '<span>$' + asNumber(cr.breakout_static_dd_remaining, 0).toFixed(0) + ' remaining</span>' +
                '</div>' +
                '<div class="risk-budget-bar-wrap">' +
                    '<label>Daily Limit Used</label>' +
                    '<div class="risk-budget-bar"><div class="risk-budget-bar-fill" style="width:0%"></div></div>' +
                    '<span>$' + asNumber(cr.breakout_daily_remaining, 0).toFixed(0) + ' remaining</span>' +
                '</div>' +
                '<div class="analytics-metric-row"><span>Can Open New</span><span class="' + (cr.can_open_new ? 'positive' : 'negative') + '">' + (cr.can_open_new ? 'YES' : 'NO') + '</span></div>';
        }
    }

    function renderOracleRiskDetails(data) {
        var h = data.system_health || {};
        var trajEl = byId('oracleTrajectory');
        if (trajEl) {
            var t = String(h.trajectory || 'STABLE').toUpperCase();
            var arrow = t === 'IMPROVING' ? '\u25B2' : t === 'DECLINING' ? '\u25BC' : '\u2014';
            trajEl.textContent = arrow + ' ' + t.charAt(0) + t.slice(1).toLowerCase();
            trajEl.className = 'trajectory ' + t.toLowerCase();
        }
    }

    /* ══════════════════════════════════════════════════════════════════
       CONTROL BINDING
       ══════════════════════════════════════════════════════════════════ */

    function bindJournalControls() {
        var filterIds = [
            'journalFilterAccount', 'journalFilterDirection', 'journalFilterStructure',
            'journalFilterOrigin', 'journalFilterSource', 'journalFilterDays', 'journalSearchTicker'
        ];

        filterIds.forEach(function (id) {
            var element = byId(id);
            if (!element) return;
            var evt = id === 'journalSearchTicker' ? 'input' : 'change';
            element.addEventListener(evt, function () {
                window.clearTimeout(state.journalDebounce);
                state.journalDebounce = window.setTimeout(function () {
                    loadTradeJournal();
                }, 240);
            });
        });

        var toggleFormBtn = byId('journalToggleFormBtn');
        var cancelFormBtn = byId('journalCancelFormBtn');
        var saveTradeBtn = byId('journalSaveTradeBtn');
        var importBtn = byId('journalImportTradesBtn');
        var importCancelBtn = byId('journalImportCancelBtn');
        var importParseBtn = byId('journalImportParseBtn');
        var importConfirmBtn = byId('journalImportConfirmBtn');
        if (importConfirmBtn) importConfirmBtn.disabled = true;

        if (toggleFormBtn) {
            toggleFormBtn.addEventListener('click', function () {
                var card = byId('journalLogTradeCard');
                if (!card) return;
                card.hidden = !card.hidden;
                var importCard = byId('journalImportCard');
                if (importCard && !card.hidden) importCard.hidden = true;
            });
        }

        if (cancelFormBtn) {
            cancelFormBtn.addEventListener('click', function () {
                var card = byId('journalLogTradeCard');
                if (card) card.hidden = true;
            });
        }

        if (saveTradeBtn) {
            saveTradeBtn.addEventListener('click', function () { submitTradeForm(); });
        }

        if (importBtn) {
            importBtn.addEventListener('click', function () {
                var card = byId('journalImportCard');
                if (!card) return;
                card.hidden = !card.hidden;
                if (!card.hidden && importConfirmBtn) importConfirmBtn.disabled = true;
                var logCard = byId('journalLogTradeCard');
                if (logCard && !card.hidden) logCard.hidden = true;
            });
        }

        if (importCancelBtn) {
            importCancelBtn.addEventListener('click', function () {
                var card = byId('journalImportCard');
                if (card) card.hidden = true;
                state.journal.pendingImportPreview = null;
                var preview = byId('journalImportPreview');
                if (preview) preview.innerHTML = '<div class="analytics-empty">Upload a CSV or paste trades, then click Parse.</div>';
                if (importConfirmBtn) importConfirmBtn.disabled = true;
            });
        }

        if (importParseBtn) {
            importParseBtn.addEventListener('click', function () { parseImportTradesInput(); });
        }

        if (importConfirmBtn) {
            importConfirmBtn.addEventListener('click', function () { confirmImportTrades(); });
        }

        // Equity chart controls
        var acctEl = byId('analyticsEquityAccount');
        var rangeEl = byId('analyticsEquityRange');
        if (acctEl) {
            acctEl.addEventListener('change', function () { loadChronicle(); });
        }
        if (rangeEl) {
            rangeEl.addEventListener('change', function () { loadChronicle(); });
        }
    }

    function bindSignalExplorerControls() {
        var filterIds = [
            'signalFilterSource', 'signalFilterTicker', 'signalFilterDirection',
            'signalFilterConviction', 'signalFilterRegime', 'signalFilterDay',
            'signalFilterHour', 'signalFilterDays'
        ];

        filterIds.forEach(function (id) {
            var node = byId(id);
            if (!node) return;
            var evt = id === 'signalFilterTicker' ? 'input' : 'change';
            node.addEventListener(evt, function () {
                window.clearTimeout(state.signalDebounce);
                state.signalDebounce = window.setTimeout(function () {
                    loadSignalExplorer();
                }, 220);
            });
        });

        var table = byId('signalExplorerTable');
        if (table) {
            table.querySelectorAll('th[data-sort]').forEach(function (th) {
                th.addEventListener('click', function () {
                    var sortBy = th.getAttribute('data-sort') || 'timestamp';
                    if (state.signalExplorer.sortBy === sortBy) {
                        state.signalExplorer.sortDir = state.signalExplorer.sortDir === 'asc' ? 'desc' : 'asc';
                    } else {
                        state.signalExplorer.sortBy = sortBy;
                        state.signalExplorer.sortDir = sortBy === 'timestamp' ? 'desc' : 'asc';
                    }
                    loadSignalExplorer();
                });
            });
        }
    }

    function bindFactorLabControls() {
        ['factorLabFactorSelect', 'factorLabCompareSelect', 'factorLabDays'].forEach(function (id) {
            var node = byId(id);
            if (!node) return;
            node.addEventListener('change', function () { loadFactorLab(); });
        });
    }

    function bindBacktestControls() {
        var runBtn = byId('backtestRunBtn');
        if (runBtn) {
            runBtn.addEventListener('click', function () { runBacktest(false); });
        }
        var compareBtn = byId('backtestCompareBtn');
        if (compareBtn) {
            compareBtn.addEventListener('click', function () {
                var panel = byId('backtestComparePanel');
                if (!panel) return;
                panel.hidden = !panel.hidden;
            });
        }
        var runCompareBtn = byId('backtestRunCompareBtn');
        if (runCompareBtn) {
            runCompareBtn.addEventListener('click', function () { runBacktest(true); });
        }
    }

    /* ══════════════════════════════════════════════════════════════════
       INIT
       ══════════════════════════════════════════════════════════════════ */

    function init() {
        if (state.initialized) return;
        state.initialized = true;

        // Wire top-level tab buttons (Cockpit / Laboratory)
        document.querySelectorAll('.analytics-subtab').forEach(function (btn) {
            btn.addEventListener('click', function () {
                setActiveTab(btn.dataset.analyticsTab || 'cockpit');
            });
        });

        // Wire lab sub-tab buttons
        document.querySelectorAll('.lab-subtab').forEach(function (btn) {
            btn.addEventListener('click', function () {
                setLabSubTab(btn.dataset.labTab);
            });
        });

        // Wire cockpitUI._switchToLab so cockpit can navigate here
        if (window.cockpitUI) {
            window.cockpitUI._switchToLab = function () {
                setActiveTab('laboratory');
            };
        }

        bindJournalControls();
        bindSignalExplorerControls();
        bindFactorLabControls();
        bindBacktestControls();
    }

    document.addEventListener('DOMContentLoaded', init);

    /* ── Export on window ─────────────────────────────────────────────── */
    window.laboratoryUI = {
        setActiveTab: setActiveTab,
        setLabSubTab: setLabSubTab,
        loadJournal: loadTradeJournal,
        loadChronicle: loadChronicle,
        loadSignals: loadSignalExplorer,
        loadFactors: loadFactorLab,
        loadBacktest: runBacktest,
        loadFootprint: loadFootprintCorrelation,
        loadOracle: loadOracleNarrative
    };

})();
