
(function () {
    'use strict';

    const API_BASE = `${window.location.origin}/api/analytics`;
    const DASHBOARD_REFRESH_MS = 60 * 1000;
    const REGIME_ORDER = ['MAJOR_URSA', 'MINOR_URSA', 'NEUTRAL', 'MINOR_TORO', 'MAJOR_TORO'];
    const SOURCE_COLORS = [
        '#14b8a6', '#00e676', '#fbc02d', '#ff9800', '#66bb6a',
        '#9fb7ff', '#e5370e', '#26c6da', '#7e57c2', '#8bc34a'
    ];

    const TAB_TO_PANE = {
        dashboard: 'analyticsPaneDashboard',
        'trade-journal': 'analyticsPaneTradeJournal',
        'signal-explorer': 'analyticsPaneSignalExplorer',
        'factor-lab': 'analyticsPaneFactorLab',
        backtest: 'analyticsPaneBacktest',
        risk: 'analyticsPaneRisk'
    };

    const state = {
        initialized: false,
        mode: document.body?.dataset?.mode || 'hub',
        activeTab: 'dashboard',
        selectedSignalSource: null,
        dashboard: {
            account: '',
            days: 30
        },
        journal: {
            filters: {
                account: '',
                direction: '',
                structure: '',
                signal_source: '',
                days: 90,
                search: ''
            },
            rows: [],
            selectedTradeId: null
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
        backtest: {
            primary: null,
            compare: null
        },
        risk: {
            account: 'robinhood',
            days: 30
        },
        charts: {},
        dashboardTimer: null,
        journalDebounce: null,
        signalDebounce: null
    };

    function byId(id) {
        return document.getElementById(id);
    }

    function escapeHtml(value) {
        if (value === null || value === undefined) return '';
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function slugToLabel(value) {
        return String(value || 'unknown')
            .replace(/[_-]+/g, ' ')
            .trim()
            .toUpperCase();
    }

    function asNumber(value, fallback = 0) {
        const n = Number(value);
        return Number.isFinite(n) ? n : fallback;
    }

    function safeArray(value) {
        return Array.isArray(value) ? value : [];
    }

    function formatPercent(value, digits = 1) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
        return `${(Number(value) * 100).toFixed(digits)}%`;
    }

    function formatRawPercent(value, digits = 1) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
        return `${Number(value).toFixed(digits)}%`;
    }

    function formatDollar(value, digits = 2) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
        const n = Number(value);
        const sign = n > 0 ? '+' : '';
        return `${sign}$${n.toFixed(digits)}`;
    }

    function formatRatio(value) {
        if (value === null || value === undefined || Number.isNaN(Number(value))) return '--';
        return `${Math.abs(Number(value)).toFixed(2)}:1`;
    }

    function formatDate(value) {
        if (!value) return '--';
        const dt = new Date(value);
        if (Number.isNaN(dt.getTime())) return String(value).slice(0, 10);
        return dt.toLocaleDateString();
    }

    function formatDateTime(value) {
        if (!value) return '--';
        const dt = new Date(value);
        if (Number.isNaN(dt.getTime())) return String(value);
        return dt.toLocaleString();
    }

    function normalizeRegime(value) {
        const raw = String(value || '').toUpperCase().trim();
        if (!raw) return 'UNKNOWN';
        if (raw === 'URSA_MAJOR' || raw === 'MAJOR URSA') return 'MAJOR_URSA';
        if (raw === 'URSA_MINOR' || raw === 'MINOR URSA') return 'MINOR_URSA';
        if (raw === 'TORO_MINOR' || raw === 'MINOR TORO') return 'MINOR_TORO';
        if (raw === 'TORO_MAJOR' || raw === 'MAJOR TORO') return 'MAJOR_TORO';
        return raw.replace(/\s+/g, '_');
    }

    async function fetchJson(path, params = {}, options = {}) {
        const url = new URL(`${API_BASE}${path}`);
        for (const [key, value] of Object.entries(params || {})) {
            if (value === null || value === undefined || value === '') continue;
            url.searchParams.set(key, String(value));
        }

        const response = await fetch(url.toString(), {
            method: options.method || 'GET',
            headers: {
                'Content-Type': 'application/json',
                ...(options.headers || {})
            },
            body: options.body ? JSON.stringify(options.body) : undefined
        });

        if (!response.ok) {
            let detail = `${response.status} ${response.statusText}`;
            try {
                const payload = await response.json();
                if (payload && payload.detail) detail = payload.detail;
            } catch (_) {
                // ignore parsing errors
            }
            throw new Error(detail);
        }

        return response.json();
    }

    function setActiveTab(tabName) {
        const tab = TAB_TO_PANE[tabName] ? tabName : 'dashboard';
        state.activeTab = tab;

        document.querySelectorAll('.analytics-subtab').forEach((button) => {
            const isActive = button.dataset.analyticsTab === tab;
            button.classList.toggle('active', isActive);
            button.setAttribute('aria-selected', String(isActive));
        });

        Object.entries(TAB_TO_PANE).forEach(([name, paneId]) => {
            const pane = byId(paneId);
            if (!pane) return;
            const active = name === tab;
            pane.classList.toggle('active', active);
            pane.hidden = !active;
        });

        if (tab === 'dashboard') {
            startDashboardTimer();
            loadDashboard();
        } else {
            stopDashboardTimer();
        }

        if (tab === 'trade-journal') {
            loadTradeJournal();
        }

        if (tab === 'signal-explorer') {
            loadSignalExplorer();
        }

        if (tab === 'factor-lab') {
            loadFactorLab();
        }

        if (tab === 'backtest') {
            initBacktestDefaults();
        }

        if (tab === 'risk') {
            loadRiskTab();
        }
    }

    function startDashboardTimer() {
        stopDashboardTimer();
        state.dashboardTimer = window.setInterval(() => {
            if (state.mode === 'analytics' && state.activeTab === 'dashboard') {
                loadDashboard({ silent: true });
            }
        }, DASHBOARD_REFRESH_MS);
    }

    function stopDashboardTimer() {
        if (state.dashboardTimer) {
            window.clearInterval(state.dashboardTimer);
            state.dashboardTimer = null;
        }
    }

    function onModeChange(mode) {
        state.mode = mode;
        if (mode === 'analytics') {
            if (state.activeTab === 'dashboard') {
                startDashboardTimer();
            }
            refreshAll();
        } else {
            stopDashboardTimer();
        }
    }

    function bindTabs() {
        document.querySelectorAll('.analytics-subtab').forEach((button) => {
            button.addEventListener('click', () => {
                setActiveTab(button.dataset.analyticsTab || 'dashboard');
            });
        });
    }

    function bindDashboardControls() {
        const account = byId('analyticsEquityAccount');
        const range = byId('analyticsEquityRange');
        if (account) {
            account.addEventListener('change', () => {
                state.dashboard.account = account.value || '';
                loadDashboard();
            });
        }
        if (range) {
            range.addEventListener('change', () => {
                state.dashboard.days = asNumber(range.value, 30);
                loadDashboard();
            });
        }
    }

    function bindJournalControls() {
        const filterIds = [
            'journalFilterAccount',
            'journalFilterDirection',
            'journalFilterStructure',
            'journalFilterSource',
            'journalFilterDays',
            'journalSearchTicker'
        ];

        filterIds.forEach((id) => {
            const element = byId(id);
            if (!element) return;
            const evt = id === 'journalSearchTicker' ? 'input' : 'change';
            element.addEventListener(evt, () => {
                window.clearTimeout(state.journalDebounce);
                state.journalDebounce = window.setTimeout(() => {
                    loadTradeJournal();
                }, 240);
            });
        });

        const toggleFormBtn = byId('journalToggleFormBtn');
        const cancelFormBtn = byId('journalCancelFormBtn');
        const saveTradeBtn = byId('journalSaveTradeBtn');

        if (toggleFormBtn) {
            toggleFormBtn.addEventListener('click', () => {
                const card = byId('journalLogTradeCard');
                if (!card) return;
                card.hidden = !card.hidden;
            });
        }

        if (cancelFormBtn) {
            cancelFormBtn.addEventListener('click', () => {
                const card = byId('journalLogTradeCard');
                if (card) card.hidden = true;
            });
        }

        if (saveTradeBtn) {
            saveTradeBtn.addEventListener('click', async () => {
                await submitTradeForm();
            });
        }
    }

    function bindSignalExplorerControls() {
        const filterIds = [
            'signalFilterSource',
            'signalFilterTicker',
            'signalFilterDirection',
            'signalFilterConviction',
            'signalFilterRegime',
            'signalFilterDay',
            'signalFilterHour',
            'signalFilterDays'
        ];

        filterIds.forEach((id) => {
            const node = byId(id);
            if (!node) return;
            const evt = id === 'signalFilterTicker' ? 'input' : 'change';
            node.addEventListener(evt, () => {
                window.clearTimeout(state.signalDebounce);
                state.signalDebounce = window.setTimeout(() => {
                    loadSignalExplorer();
                }, 220);
            });
        });

        byId('signalExplorerTable')?.querySelectorAll('th[data-sort]').forEach((th) => {
            th.addEventListener('click', () => {
                const sortBy = th.getAttribute('data-sort') || 'timestamp';
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

    function bindFactorLabControls() {
        ['factorLabFactorSelect', 'factorLabCompareSelect', 'factorLabDays'].forEach((id) => {
            const node = byId(id);
            if (!node) return;
            node.addEventListener('change', () => {
                loadFactorLab();
            });
        });
    }

    function bindBacktestControls() {
        byId('backtestRunBtn')?.addEventListener('click', async () => {
            await runBacktest(false);
        });
        byId('backtestCompareBtn')?.addEventListener('click', () => {
            const panel = byId('backtestComparePanel');
            if (!panel) return;
            panel.hidden = !panel.hidden;
        });
        byId('backtestRunCompareBtn')?.addEventListener('click', async () => {
            await runBacktest(true);
        });
    }

    function bindRiskControls() {
        byId('riskHistoryAccount')?.addEventListener('change', () => {
            loadRiskHistoryChart();
        });
        byId('riskHistoryDays')?.addEventListener('change', () => {
            loadRiskHistoryChart();
        });
    }

    function getJournalFilters() {
        return {
            account: byId('journalFilterAccount')?.value || '',
            direction: byId('journalFilterDirection')?.value || '',
            structure: byId('journalFilterStructure')?.value || '',
            signal_source: byId('journalFilterSource')?.value || '',
            days: asNumber(byId('journalFilterDays')?.value, 90),
            search: byId('journalSearchTicker')?.value?.trim() || ''
        };
    }

    function getCardTrendText(grade, expectancy) {
        const g = String(grade || '').toUpperCase();
        if (g === 'F') return 'unproven';
        if (g === 'D' || g === 'C') return 'degraded';
        if (asNumber(expectancy, 0) > 0) return 'stable';
        return 'mixed';
    }

    function renderHealthCards(rows, payload) {
        const container = byId('analyticsHealthCards');
        const asOf = byId('analyticsHealthAsOf');
        if (!container) return;

        const grades = safeArray(rows);
        if (!grades.length) {
            container.innerHTML = '<div class="analytics-empty">Collecting data - metrics will appear after signals accumulate.</div>';
            if (asOf) asOf.textContent = 'No strategy grades yet';
            return;
        }

        const latestTs = grades
            .map((row) => row?.computed_at)
            .filter(Boolean)
            .sort()
            .slice(-1)[0];

        if (asOf) {
            const unresolved = asNumber(payload?.unresolved_alerts, 0);
            asOf.textContent = `As of ${formatDateTime(latestTs)} | Unresolved alerts: ${unresolved}`;
        }

        const html = grades
            .sort((a, b) => String(a.source || '').localeCompare(String(b.source || '')))
            .map((row) => {
                const grade = String(row.grade || 'F').toUpperCase();
                const source = row.source || 'unknown';
                const cardClass = `analytics-health-card grade-${grade.toLowerCase()}`;
                const signalsCount = asNumber(row.signals_count, 0);
                const accuracy = formatPercent(row.accuracy, 1);
                const trend = getCardTrendText(grade, row.expectancy);
                return `
                    <div class="${cardClass}" data-source="${escapeHtml(source)}">
                        <div class="analytics-health-source">${escapeHtml(slugToLabel(source))}</div>
                        <div class="analytics-health-grade">${escapeHtml(grade)}</div>
                        <div class="analytics-health-metric">${accuracy} acc</div>
                        <div class="analytics-health-metric">${signalsCount} signals</div>
                        <div class="analytics-health-trend">&#8250; ${escapeHtml(trend)}</div>
                    </div>
                `;
            })
            .join('');

        container.innerHTML = html;
        container.querySelectorAll('.analytics-health-card').forEach((node) => {
            node.addEventListener('click', () => {
                state.selectedSignalSource = node.getAttribute('data-source');
                setActiveTab('signal-explorer');
            });
        });
    }

    async function dismissAlert(alertId) {
        await fetchJson(`/health-alert/${alertId}/dismiss`, {}, { method: 'PUT' });
        const alerts = await fetchJson('/health-alerts', { resolved: false, limit: 20 });
        renderAlerts(safeArray(alerts?.rows));
    }

    function renderAlerts(rows) {
        const container = byId('analyticsAlertsList');
        if (!container) return;

        const alerts = safeArray(rows);
        if (!alerts.length) {
            container.innerHTML = '<div class="analytics-empty">No active alerts.</div>';
            return;
        }

        container.innerHTML = alerts
            .map((row) => {
                const grade = String(row.new_grade || '').toLowerCase();
                const severity = `severity-${grade || 'c'}`;
                const message = row.message || `${slugToLabel(row.source)} grade moved ${row.previous_grade || '--'} -> ${row.new_grade || '--'}`;
                return `
                    <div class="analytics-alert-row ${severity}" data-alert-id="${row.id}">
                        <div>
                            <div class="analytics-alert-meta">${escapeHtml(formatDateTime(row.created_at))} | ${escapeHtml(slugToLabel(row.source))}</div>
                            <div>${escapeHtml(message)}</div>
                        </div>
                        <button class="analytics-btn analytics-btn-ghost" data-alert-dismiss="${row.id}">Dismiss</button>
                    </div>
                `;
            })
            .join('');

        container.querySelectorAll('[data-alert-dismiss]').forEach((btn) => {
            btn.addEventListener('click', async (event) => {
                const id = asNumber(event.currentTarget.getAttribute('data-alert-dismiss'), 0);
                if (!id) return;
                try {
                    await dismissAlert(id);
                } catch (error) {
                    console.error('Failed to dismiss alert:', error);
                }
            });
        });
    }

    function metricClass(value) {
        const n = asNumber(value, 0);
        if (n > 0) return 'positive';
        if (n < 0) return 'negative';
        return '';
    }

    function renderKeyMetrics(stats) {
        const container = byId('analyticsKeyMetrics');
        if (!container) return;

        const pnl = stats?.pnl || {};
        const risk = stats?.risk_metrics || {};

        const metrics = [
            { label: 'Total P&L', value: formatDollar(pnl.total_dollars), className: metricClass(pnl.total_dollars) },
            { label: 'Win Rate', value: formatPercent(stats?.win_rate), className: metricClass((stats?.win_rate || 0) - 0.5) },
            { label: 'Avg R:R', value: formatRatio(pnl.avg_rr_achieved), className: metricClass(pnl.avg_rr_achieved) },
            { label: 'Sharpe', value: asNumber(risk.sharpe_ratio).toFixed(2), className: metricClass(risk.sharpe_ratio) },
            { label: 'Profit Factor', value: asNumber(risk.profit_factor).toFixed(2), className: metricClass((risk.profit_factor || 0) - 1) },
            { label: 'Max Drawdown', value: formatRawPercent(risk.max_drawdown_pct), className: metricClass(risk.max_drawdown_pct) },
            { label: 'Expectancy', value: formatDollar(pnl.expectancy_per_trade), className: metricClass(pnl.expectancy_per_trade) },
            { label: 'Open Trades', value: String(asNumber(stats?.open, 0)), className: '' },
            { label: 'Best Trade', value: formatDollar(pnl.largest_win), className: metricClass(pnl.largest_win) },
            { label: 'Worst Trade', value: formatDollar(pnl.largest_loss), className: metricClass(pnl.largest_loss) }
        ];

        container.innerHTML = metrics
            .map((item) => `
                <div class="analytics-metric-item">
                    <span class="analytics-metric-label">${escapeHtml(item.label)}</span>
                    <span class="analytics-metric-value ${escapeHtml(item.className)}">${escapeHtml(item.value)}</span>
                </div>
            `)
            .join('');
    }

    function linearReferenceSeries(length, finalValue) {
        if (length <= 0) return [];
        if (!Number.isFinite(finalValue)) return new Array(length).fill(0);
        if (length === 1) return [finalValue];
        const out = [];
        for (let i = 0; i < length; i += 1) {
            out.push((finalValue * i) / (length - 1));
        }
        return out;
    }

    function computeDrawdownSeries(curve) {
        let peak = Number.NEGATIVE_INFINITY;
        return curve.map((value) => {
            const n = asNumber(value, 0);
            if (n > peak) peak = n;
            return n - peak;
        });
    }

    function upsertChart(chartKey, canvasId, config) {
        const canvas = byId(canvasId);
        if (!canvas || typeof Chart === 'undefined') return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        if (state.charts[chartKey]) {
            state.charts[chartKey].destroy();
        }
        state.charts[chartKey] = new Chart(ctx, config);
    }

    function renderEquityChart(stats) {
        const points = safeArray(stats?.equity_curve);
        const labels = points.map((p) => String(p.date || ''));
        const pnlSeries = points.map((p) => asNumber(p.cumulative_pnl, 0));

        const benchmarkSpy = linearReferenceSeries(labels.length, asNumber(stats?.benchmarks?.spy_buy_hold_return_pct, 0));
        const benchmarkBias = linearReferenceSeries(labels.length, asNumber(stats?.benchmarks?.bias_follow_return_pct, 0));
        const drawdowns = computeDrawdownSeries(pnlSeries);

        upsertChart('equity', 'analyticsEquityChart', {
            type: 'line',
            data: {
                labels,
                datasets: [
                    {
                        label: 'Your P&L',
                        data: pnlSeries,
                        borderColor: '#14b8a6',
                        backgroundColor: 'rgba(20,184,166,0.12)',
                        fill: false,
                        tension: 0.25,
                        pointRadius: 0,
                        borderWidth: 2
                    },
                    {
                        label: 'SPY B&H (ref)',
                        data: benchmarkSpy,
                        borderColor: '#9fb7ff',
                        fill: false,
                        borderDash: [6, 4],
                        pointRadius: 0,
                        borderWidth: 1.5
                    },
                    {
                        label: 'Bias-Follow (ref)',
                        data: benchmarkBias,
                        borderColor: '#fbc02d',
                        fill: false,
                        borderDash: [6, 4],
                        pointRadius: 0,
                        borderWidth: 1.5
                    },
                    {
                        label: 'Drawdown',
                        data: drawdowns,
                        yAxisID: 'y1',
                        borderColor: 'rgba(229,55,14,0.35)',
                        backgroundColor: 'rgba(229,55,14,0.12)',
                        fill: true,
                        pointRadius: 0,
                        borderWidth: 1,
                        tension: 0.2
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: '#9fb7ff' } }
                },
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: {
                        ticks: { color: '#89a1c8', maxTicksLimit: 9 },
                        grid: { color: 'rgba(38,53,85,0.35)' }
                    },
                    y: {
                        ticks: { color: '#89a1c8' },
                        grid: { color: 'rgba(38,53,85,0.35)' }
                    },
                    y1: {
                        display: false,
                        grid: { drawOnChartArea: false }
                    }
                }
            }
        });
    }

    function renderAccuracyChart(sourceStats) {
        const sourceSeries = safeArray(sourceStats);
        const allDates = new Set();

        sourceSeries.forEach((item) => {
            safeArray(item?.data?.timeline).forEach((point) => {
                if (point?.date) allDates.add(String(point.date));
            });
        });

        const labels = [...allDates].sort((a, b) => new Date(a) - new Date(b));
        const datasets = sourceSeries.map((item, index) => {
            const lookup = {};
            safeArray(item?.data?.timeline).forEach((point) => {
                lookup[String(point.date)] = asNumber(point.accurate, 0) / Math.max(1, asNumber(point.signals, 0));
            });

            return {
                label: slugToLabel(item.source),
                data: labels.map((day) => {
                    if (Object.prototype.hasOwnProperty.call(lookup, day)) {
                        return Number((lookup[day] * 100).toFixed(2));
                    }
                    return null;
                }),
                borderColor: SOURCE_COLORS[index % SOURCE_COLORS.length],
                tension: 0.25,
                pointRadius: 0,
                borderWidth: 2,
                spanGaps: true
            };
        });

        datasets.push(
            {
                label: 'A Threshold',
                data: labels.map(() => 65),
                borderColor: 'rgba(0,230,118,0.5)',
                borderDash: [5, 5],
                pointRadius: 0,
                borderWidth: 1,
                tension: 0
            },
            {
                label: 'D Threshold',
                data: labels.map(() => 40),
                borderColor: 'rgba(229,55,14,0.5)',
                borderDash: [5, 5],
                pointRadius: 0,
                borderWidth: 1,
                tension: 0
            }
        );

        upsertChart('accuracy', 'analyticsAccuracyChart', {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: '#9fb7ff' } },
                    tooltip: {
                        callbacks: {
                            label(context) {
                                const label = context.dataset.label || '';
                                const value = context.parsed.y;
                                if (value === null || value === undefined) return label;
                                return `${label}: ${Number(value).toFixed(1)}%`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        ticks: { color: '#89a1c8', maxTicksLimit: 8 },
                        grid: { color: 'rgba(38,53,85,0.35)' }
                    },
                    y: {
                        min: 0,
                        max: 100,
                        ticks: { color: '#89a1c8', callback: (v) => `${v}%` },
                        grid: { color: 'rgba(38,53,85,0.35)' }
                    }
                }
            }
        });
    }

    function renderRegimeChart(sourceStats) {
        const sourceSeries = safeArray(sourceStats);
        const datasets = sourceSeries.map((item, index) => {
            const byRegime = item?.data?.accuracy?.by_regime || {};
            const regimeMap = {};
            Object.entries(byRegime).forEach(([key, value]) => {
                regimeMap[normalizeRegime(key)] = asNumber(value, 0);
            });
            return {
                label: slugToLabel(item.source),
                data: REGIME_ORDER.map((regime) => Number((asNumber(regimeMap[regime], 0) * 100).toFixed(2))),
                backgroundColor: `${SOURCE_COLORS[index % SOURCE_COLORS.length]}CC`,
                borderColor: SOURCE_COLORS[index % SOURCE_COLORS.length],
                borderWidth: 1
            };
        });

        upsertChart('regime', 'analyticsRegimeChart', {
            type: 'bar',
            data: {
                labels: REGIME_ORDER.map((regime) => regime.replace('_', ' ')),
                datasets
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: '#9fb7ff' } }
                },
                scales: {
                    x: {
                        ticks: { color: '#89a1c8' },
                        grid: { color: 'rgba(38,53,85,0.2)' }
                    },
                    y: {
                        min: 0,
                        max: 100,
                        ticks: { color: '#89a1c8', callback: (v) => `${v}%` },
                        grid: { color: 'rgba(38,53,85,0.35)' }
                    }
                }
            }
        });
    }

    function refreshSourceFilterOptions(sources) {
        const normalized = new Set(
            safeArray(sources)
                .map((value) => String(value || '').trim())
                .filter(Boolean)
        );
        const sorted = [...normalized].sort((a, b) => a.localeCompare(b));

        [
            { id: 'journalFilterSource', label: 'Signal Source: All' },
            { id: 'signalFilterSource', label: 'Source: All' }
        ].forEach((meta) => {
            const select = byId(meta.id);
            if (!select) return;
            const currentValue = select.value;
            select.innerHTML = `<option value="">${meta.label}</option>`;
            sorted.forEach((source) => {
                const option = document.createElement('option');
                option.value = source;
                option.textContent = slugToLabel(source);
                select.appendChild(option);
            });
            if (sorted.includes(currentValue)) {
                select.value = currentValue;
            }
        });
    }

    async function loadDashboard(options = {}) {
        if (state.mode !== 'analytics') return;

        const account = byId('analyticsEquityAccount')?.value || '';
        const days = asNumber(byId('analyticsEquityRange')?.value, 30);
        state.dashboard.account = account;
        state.dashboard.days = days;

        if (!options.silent) {
            const metrics = byId('analyticsKeyMetrics');
            if (metrics) metrics.innerHTML = '<div class="analytics-empty">Loading metrics...</div>';
        }

        try {
            const [health, alerts, tradeStats] = await Promise.all([
                fetchJson('/strategy-health', { days }),
                fetchJson('/health-alerts', { resolved: false, limit: 20 }),
                fetchJson('/trade-stats', { days, account })
            ]);

            renderHealthCards(health?.grades, health);
            renderAlerts(alerts?.rows);
            renderKeyMetrics(tradeStats || {});
            renderEquityChart(tradeStats || {});

            let sources = safeArray(health?.grades)
                .map((row) => row?.source)
                .filter(Boolean);

            if (!sources.length) {
                const strategy = await fetchJson('/strategy-comparison', { days });
                sources = safeArray(strategy?.strategies).map((row) => row?.source).filter(Boolean);
            }

            sources = [...new Set(sources)].slice(0, 8);
            refreshSourceFilterOptions(sources);

            const sourceStats = (await Promise.all(
                sources.map(async (source) => {
                    try {
                        const data = await fetchJson('/signal-stats', { source, days });
                        return { source, data };
                    } catch (error) {
                        console.warn('Signal stats load failed for source:', source, error);
                        return null;
                    }
                })
            )).filter(Boolean);

            renderAccuracyChart(sourceStats);
            renderRegimeChart(sourceStats);
        } catch (error) {
            console.error('Dashboard load failed:', error);
            const metrics = byId('analyticsKeyMetrics');
            if (metrics) metrics.innerHTML = `<div class="analytics-empty">Dashboard error: ${escapeHtml(error.message || 'unknown')}</div>`;
            const alerts = byId('analyticsAlertsList');
            if (alerts) alerts.innerHTML = '<div class="analytics-empty">Unable to load alerts.</div>';
        }
    }

    function renderJournalTable(rows) {
        const tbody = byId('journalTableBody');
        if (!tbody) return;

        const trades = safeArray(rows);
        if (!trades.length) {
            tbody.innerHTML = '<tr><td colspan="12" class="analytics-empty">Collecting data - metrics will appear after signals accumulate.</td></tr>';
            return;
        }

        tbody.innerHTML = trades
            .map((trade) => {
                const id = asNumber(trade.id, 0);
                const pnl = asNumber(trade.pnl_dollars, 0);
                const status = String(trade.status || '').toLowerCase();
                const rowClass = status === 'open' ? 'trade-open' : (pnl >= 0 ? 'trade-win' : 'trade-loss');
                const entry = trade.entry_price !== null && trade.entry_price !== undefined ? Number(trade.entry_price).toFixed(2) : '--';
                const exit = trade.exit_price !== null && trade.exit_price !== undefined ? Number(trade.exit_price).toFixed(2) : '--';
                const signal = trade.signal_source || trade.linked_signal_strategy || '--';
                const bias = trade.bias_at_entry || trade.linked_signal_bias || '--';

                return `
                    <tr class="${rowClass}" data-trade-id="${id}">
                        <td>${escapeHtml(formatDate(trade.opened_at || trade.closed_at))}</td>
                        <td>${escapeHtml(String(trade.ticker || '--').toUpperCase())}</td>
                        <td>${escapeHtml(String(trade.direction || '--').toUpperCase())}</td>
                        <td>${escapeHtml(String(trade.structure || '--'))}</td>
                        <td>${escapeHtml(`${entry} -> ${exit}`)}</td>
                        <td>${escapeHtml(formatDollar(trade.pnl_dollars))}</td>
                        <td>${escapeHtml(formatRawPercent(trade.pnl_percent))}</td>
                        <td>${escapeHtml(formatRatio(trade.rr_achieved))}</td>
                        <td>${escapeHtml(String(trade.account || '--').toUpperCase())}</td>
                        <td>${escapeHtml(String(bias))}</td>
                        <td>${escapeHtml(slugToLabel(signal))}</td>
                        <td>${escapeHtml(String(trade.exit_reason || '--'))}</td>
                    </tr>
                `;
            })
            .join('');

        tbody.querySelectorAll('tr[data-trade-id]').forEach((row) => {
            row.addEventListener('click', () => {
                const tradeId = asNumber(row.getAttribute('data-trade-id'), 0);
                if (!tradeId) return;
                loadTradeDetails(tradeId);
            });
        });
    }

    function renderJournalSummary(stats, visibleCount) {
        const summary = byId('journalSummary');
        if (!summary) return;

        const totalTrades = asNumber(stats?.total_trades, visibleCount);
        const closed = asNumber(stats?.closed, 0);
        const wins = Math.round(asNumber(stats?.win_rate, 0) * closed);
        const losses = Math.max(0, closed - wins);
        const totalPnl = stats?.pnl?.total_dollars;
        const avgRR = stats?.pnl?.avg_rr_achieved;
        const sharpe = stats?.risk_metrics?.sharpe_ratio;

        summary.textContent = `Total: ${totalTrades} trades | Wins: ${wins} | Losses: ${losses} | Win Rate: ${formatPercent(stats?.win_rate)} | Total P&L: ${formatDollar(totalPnl)} | Avg R:R: ${formatRatio(avgRR)} | Sharpe: ${asNumber(sharpe, 0).toFixed(2)}`;
    }

    function parseContext(value) {
        if (!value) return {};
        if (typeof value === 'object') return value;
        if (typeof value === 'string') {
            try {
                return JSON.parse(value);
            } catch (_) {
                return { raw: value };
            }
        }
        return {};
    }

    function renderLegsTable(legs) {
        const rows = safeArray(legs);
        if (!rows.length) return '<div class="analytics-empty">No legs recorded.</div>';

        const body = rows
            .map((leg) => `
                <tr>
                    <td>${escapeHtml(formatDateTime(leg.timestamp))}</td>
                    <td>${escapeHtml(String(leg.action || '--'))}</td>
                    <td>${escapeHtml(String(leg.direction || '--'))}</td>
                    <td>${escapeHtml(String(leg.quantity ?? '--'))}</td>
                    <td>${escapeHtml(String(leg.price ?? '--'))}</td>
                    <td>${escapeHtml(String(leg.strike ?? '--'))}</td>
                    <td>${escapeHtml(String(leg.expiry ?? '--'))}</td>
                    <td>${escapeHtml(String(leg.leg_type ?? '--'))}</td>
                </tr>
            `)
            .join('');

        return `
            <table class="journal-legs-table">
                <thead>
                    <tr><th>Time</th><th>Action</th><th>Dir</th><th>Qty</th><th>Price</th><th>Strike</th><th>Expiry</th><th>Type</th></tr>
                </thead>
                <tbody>${body}</tbody>
            </table>
        `;
    }

    async function loadTradeDetails(tradeId) {
        state.journal.selectedTradeId = tradeId;

        const detailContainer = byId('journalTradeDetails');
        if (!detailContainer) return;
        detailContainer.innerHTML = '<div class="analytics-empty">Loading trade details...</div>';

        const trade = state.journal.rows.find((row) => asNumber(row.id, 0) === tradeId);
        if (!trade) {
            detailContainer.innerHTML = '<div class="analytics-empty">Trade not found in current table.</div>';
            return;
        }

        let legs = [];
        try {
            const legPayload = await fetchJson(`/trade/${tradeId}/legs`);
            legs = safeArray(legPayload?.rows);
        } catch (error) {
            console.warn('Trade legs load failed:', error);
        }

        const context = parseContext(trade.full_context);
        const contextText = escapeHtml(JSON.stringify(context, null, 2)).slice(0, 8000);

        detailContainer.innerHTML = `
            <div class="journal-detail-block">
                <h4>Overview</h4>
                <div><strong>${escapeHtml(String(trade.ticker || '').toUpperCase())}</strong> ${escapeHtml(String(trade.direction || '--').toUpperCase())} ${escapeHtml(String(trade.structure || '--'))}</div>
                <div>Status: ${escapeHtml(String(trade.status || '--'))} | Opened: ${escapeHtml(formatDateTime(trade.opened_at))} | Closed: ${escapeHtml(formatDateTime(trade.closed_at))}</div>
                <div>Entry: ${escapeHtml(String(trade.entry_price ?? '--'))} | Stop: ${escapeHtml(String(trade.stop_loss ?? '--'))} | Target 1: ${escapeHtml(String(trade.target_1 ?? '--'))}</div>
                <div>P&L: ${escapeHtml(formatDollar(trade.pnl_dollars))} (${escapeHtml(formatRawPercent(trade.pnl_percent))}) | R:R: ${escapeHtml(formatRatio(trade.rr_achieved))}</div>
            </div>
            <div class="journal-detail-block">
                <h4>Trade Legs</h4>
                ${renderLegsTable(legs)}
            </div>
            <div class="journal-detail-block">
                <h4>Pivot Recommendation</h4>
                <div>Conviction: <strong>${escapeHtml(String(trade.pivot_conviction || '--'))}</strong></div>
                <div>${escapeHtml(String(trade.pivot_recommendation || 'No recommendation stored.'))}</div>
            </div>
            <div class="journal-detail-block">
                <h4>Context Snapshot</h4>
                <pre style="white-space:pre-wrap;word-break:break-word;max-height:220px;overflow:auto;">${contextText || '{}'}</pre>
            </div>
            <div class="journal-detail-block">
                <h4>Notes</h4>
                <div>${escapeHtml(String(trade.notes || '--'))}</div>
            </div>
        `;

        byId('journalTableBody')?.querySelectorAll('tr[data-trade-id]').forEach((row) => {
            row.classList.toggle('selected', asNumber(row.getAttribute('data-trade-id'), 0) === tradeId);
        });
    }

    async function loadTradeJournal() {
        if (state.mode !== 'analytics') return;

        const filters = getJournalFilters();
        state.journal.filters = filters;

        const body = byId('journalTableBody');
        if (body) {
            body.innerHTML = '<tr><td colspan="12" class="analytics-empty">Loading trades...</td></tr>';
        }

        try {
            const [tradesPayload, statsPayload] = await Promise.all([
                fetchJson('/trades', {
                    account: filters.account,
                    direction: filters.direction,
                    structure: filters.structure,
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
                    signal_source: filters.signal_source,
                    days: filters.days
                })
            ]);

            const rows = safeArray(tradesPayload?.rows);
            state.journal.rows = rows;
            renderJournalTable(rows);
            renderJournalSummary(statsPayload, rows.length);

            const sourceOptions = rows
                .map((row) => row.signal_source || row.linked_signal_strategy)
                .filter(Boolean);
            refreshSourceFilterOptions(sourceOptions);

            if (state.journal.selectedTradeId) {
                const stillPresent = rows.some((row) => asNumber(row.id, 0) === state.journal.selectedTradeId);
                if (stillPresent) {
                    loadTradeDetails(state.journal.selectedTradeId);
                } else {
                    state.journal.selectedTradeId = null;
                    const details = byId('journalTradeDetails');
                    if (details) details.innerHTML = '<div class="analytics-empty">Click a trade row to view legs, recommendation, and context.</div>';
                }
            }
        } catch (error) {
            console.error('Trade journal load failed:', error);
            if (body) {
                body.innerHTML = `<tr><td colspan="12" class="analytics-empty">Trade journal error: ${escapeHtml(error.message || 'unknown')}</td></tr>`;
            }
        }
    }

    function collectTradeFormPayload() {
        const ticker = byId('journalFormTicker')?.value?.trim().toUpperCase() || '';
        const direction = byId('journalFormDirection')?.value || '';
        const structure = byId('journalFormStructure')?.value?.trim() || '';
        const entryPrice = byId('journalFormEntry')?.value;
        const stopLoss = byId('journalFormStop')?.value;
        const target1 = byId('journalFormTarget1')?.value;
        const quantity = byId('journalFormQuantity')?.value;

        const entry = entryPrice === '' ? null : asNumber(entryPrice, NaN);
        const stop = stopLoss === '' ? null : asNumber(stopLoss, NaN);
        const qty = quantity === '' ? null : asNumber(quantity, NaN);

        let riskAmount = null;
        if (Number.isFinite(entry) && Number.isFinite(stop) && Number.isFinite(qty)) {
            riskAmount = Math.abs(entry - stop) * Math.abs(qty);
        }

        return {
            ticker,
            direction: direction || null,
            structure: structure || null,
            account: byId('journalFormAccount')?.value || null,
            signal_source: byId('journalFilterSource')?.value || null,
            entry_price: Number.isFinite(entry) ? entry : null,
            stop_loss: Number.isFinite(stop) ? stop : null,
            target_1: target1 === '' ? null : asNumber(target1, NaN),
            quantity: Number.isFinite(qty) ? qty : null,
            notes: byId('journalFormNotes')?.value?.trim() || null,
            status: 'open',
            risk_amount: Number.isFinite(riskAmount) ? Number(riskAmount.toFixed(4)) : null,
            full_context: {}
        };
    }

    function clearTradeForm() {
        [
            'journalFormTicker',
            'journalFormDirection',
            'journalFormStructure',
            'journalFormEntry',
            'journalFormStop',
            'journalFormTarget1',
            'journalFormTarget2',
            'journalFormQuantity',
            'journalFormAccount',
            'journalFormNotes'
        ].forEach((id) => {
            const node = byId(id);
            if (!node) return;
            if (node.tagName === 'SELECT') {
                node.selectedIndex = 0;
            } else {
                node.value = '';
            }
        });
    }

    async function submitTradeForm() {
        const payload = collectTradeFormPayload();
        if (!payload.ticker) {
            window.alert('Ticker is required.');
            return;
        }

        try {
            await fetchJson('/log-trade', {}, { method: 'POST', body: payload });
            clearTradeForm();
            const card = byId('journalLogTradeCard');
            if (card) card.hidden = true;
            await loadTradeJournal();
        } catch (error) {
            console.error('Trade save failed:', error);
            window.alert(`Failed to save trade: ${error.message || 'unknown error'}`);
        }
    }

    function getSignalFilters() {
        const sourceValue = byId('signalFilterSource')?.value || '';
        const source = sourceValue || state.selectedSignalSource || '';
        return {
            source,
            ticker: byId('signalFilterTicker')?.value?.trim().toUpperCase() || '',
            direction: byId('signalFilterDirection')?.value || '',
            conviction: byId('signalFilterConviction')?.value || '',
            bias_regime: byId('signalFilterRegime')?.value || '',
            day_of_week: byId('signalFilterDay')?.value || '',
            hour_of_day: byId('signalFilterHour')?.value || '',
            days: asNumber(byId('signalFilterDays')?.value, 30),
            sort_by: state.signalExplorer.sortBy,
            sort_dir: state.signalExplorer.sortDir,
            limit: 250,
            offset: 0
        };
    }

    function renderSignalStatsPanel(stats) {
        const panel = byId('signalStatsPanel');
        if (!panel) return;

        const accuracyByDay = stats?.accuracy?.by_day_of_week || {};
        const accuracyByHour = stats?.accuracy?.by_hour || {};
        const accuracyByRegime = stats?.accuracy?.by_regime || {};
        const dayEntries = Object.entries(accuracyByDay).map(([k, v]) => [String(k), asNumber(v, 0)]);
        const hourEntries = Object.entries(accuracyByHour).map(([k, v]) => [String(k), asNumber(v, 0)]);
        const regimeEntries = Object.entries(accuracyByRegime).map(([k, v]) => [String(k), asNumber(v, 0)]);

        const bestDay = dayEntries.sort((a, b) => b[1] - a[1])[0];
        const worstDay = dayEntries.sort((a, b) => a[1] - b[1])[0];
        const bestHour = hourEntries.sort((a, b) => b[1] - a[1])[0];
        const worstHour = hourEntries.sort((a, b) => a[1] - b[1])[0];
        const bestRegime = regimeEntries.sort((a, b) => b[1] - a[1])[0];
        const worstRegime = regimeEntries.sort((a, b) => a[1] - b[1])[0];

        const metrics = [
            ['Signals', String(asNumber(stats?.total_signals, 0))],
            ['Accuracy', formatPercent(stats?.accuracy?.overall)],
            ['False Signal Rate', formatPercent(stats?.false_signal_rate)],
            ['Avg MFE', formatRawPercent(stats?.excursion?.avg_mfe_pct)],
            ['Avg MAE', formatRawPercent(stats?.excursion?.avg_mae_pct)],
            ['MFE/MAE Ratio', asNumber(stats?.excursion?.mfe_mae_ratio).toFixed(2)],
            ['Avg Time to MFE', `${asNumber(stats?.avg_time_to_mfe_hours).toFixed(2)}h`],
            ['Convergence Accuracy', formatPercent(stats?.convergence?.convergence_accuracy)],
            ['Solo Accuracy', formatPercent(stats?.convergence?.solo_accuracy)],
            ['Best Day', bestDay ? `${bestDay[0]} (${(bestDay[1] * 100).toFixed(1)}%)` : '--'],
            ['Worst Day', worstDay ? `${worstDay[0]} (${(worstDay[1] * 100).toFixed(1)}%)` : '--'],
            ['Best Hour', bestHour ? `${bestHour[0]} (${(bestHour[1] * 100).toFixed(1)}%)` : '--'],
            ['Worst Hour', worstHour ? `${worstHour[0]} (${(worstHour[1] * 100).toFixed(1)}%)` : '--'],
            ['Best Regime', bestRegime ? `${bestRegime[0]} (${(bestRegime[1] * 100).toFixed(1)}%)` : '--'],
            ['Worst Regime', worstRegime ? `${worstRegime[0]} (${(worstRegime[1] * 100).toFixed(1)}%)` : '--']
        ];

        panel.innerHTML = metrics.map(([label, value]) => `
            <div class="analytics-metric-item">
                <span class="analytics-metric-label">${escapeHtml(label)}</span>
                <span class="analytics-metric-value">${escapeHtml(value)}</span>
            </div>
        `).join('');
    }

    function buildHistogram(values, bucketSize = 0.5, minBound = -3, maxBound = 3) {
        const bins = [];
        for (let b = minBound; b < maxBound; b += bucketSize) {
            bins.push({ min: b, max: b + bucketSize, count: 0 });
        }
        safeArray(values).forEach((value) => {
            const n = asNumber(value, NaN);
            if (!Number.isFinite(n)) return;
            for (const bin of bins) {
                if (n >= bin.min && n < bin.max) {
                    bin.count += 1;
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
        const rows = safeArray(signalRows);
        const mfeValues = rows.map((row) => asNumber(row.mfe_pct, 0));
        const maeValues = rows.map((row) => -Math.abs(asNumber(row.mae_pct, 0)));
        const mfeBins = buildHistogram(mfeValues, 0.5, -3, 5);
        const maeBins = buildHistogram(maeValues, 0.5, -5, 3);
        const labels = mfeBins.map((bin) => `${bin.min.toFixed(1)}..${bin.max.toFixed(1)}`);

        upsertChart('signalMfeMae', 'signalMfeMaeChart', {
            type: 'bar',
            data: {
                labels,
                datasets: [
                    {
                        label: 'MFE',
                        data: mfeBins.map((bin) => bin.count),
                        backgroundColor: 'rgba(0, 230, 118, 0.55)'
                    },
                    {
                        label: 'MAE',
                        data: maeBins.map((bin) => bin.count),
                        backgroundColor: 'rgba(229, 55, 14, 0.55)'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { ticks: { color: '#89a1c8', maxTicksLimit: 10 }, grid: { color: 'rgba(38,53,85,0.25)' } },
                    y: { ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.25)' } }
                },
                plugins: { legend: { labels: { color: '#9fb7ff' } } }
            }
        });

        const byHour = stats?.accuracy?.by_hour || {};
        const hourLabels = ['9', '10', '11', '12', '13', '14', '15', '16'];
        const hourValues = hourLabels.map((hour) => asNumber(byHour[hour], 0) * 100);
        const barColors = hourValues.map((v) => `rgba(${Math.round(229 - (v * 1.7))}, ${Math.round(55 + (v * 1.8))}, 120, 0.75)`);

        upsertChart('signalAccuracyHour', 'signalAccuracyHourChart', {
            type: 'bar',
            data: {
                labels: hourLabels,
                datasets: [{
                    label: 'Accuracy %',
                    data: hourValues,
                    backgroundColor: barColors,
                    borderColor: '#2d3b59',
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    x: { ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.25)' } },
                    y: {
                        min: 0,
                        max: 100,
                        ticks: { color: '#89a1c8', callback: (v) => `${v}%` },
                        grid: { color: 'rgba(38,53,85,0.25)' }
                    }
                },
                plugins: { legend: { labels: { color: '#9fb7ff' } } }
            }
        });
    }

    function renderSignalTable(rows) {
        const tbody = byId('signalExplorerTableBody');
        const meta = byId('signalTableMeta');
        if (!tbody) return;

        const signals = safeArray(rows);
        if (meta) {
            meta.textContent = `${signals.length} rows | sort: ${state.signalExplorer.sortBy} (${state.signalExplorer.sortDir})`;
        }

        if (!signals.length) {
            tbody.innerHTML = '<tr><td colspan="9" class="analytics-empty">Collecting data - metrics will appear after signals accumulate.</td></tr>';
            return;
        }

        tbody.innerHTML = signals.map((row) => {
            const accurate = row.signal_accuracy;
            const accurateText = accurate === true ? '✅' : accurate === false ? '❌' : '--';
            const accuracyClass = accurate === true ? 'signal-accurate' : accurate === false ? 'signal-inaccurate' : '';
            const conviction = row.conviction || '--';
            const tradedText = row.traded ? 'Yes' : 'No';
            return `
                <tr class="${accuracyClass}" data-signal-id="${escapeHtml(row.signal_id)}">
                    <td>${escapeHtml(formatDateTime(row.timestamp))}</td>
                    <td>${escapeHtml(String(row.ticker || '--').toUpperCase())}</td>
                    <td>${escapeHtml(String(row.direction || '--').toUpperCase())}</td>
                    <td>${escapeHtml(slugToLabel(row.source || row.strategy || row.signal_type))}</td>
                    <td>${escapeHtml(conviction)}</td>
                    <td>${escapeHtml(formatRawPercent(row.mfe_pct))}</td>
                    <td>${escapeHtml(formatRawPercent(row.mae_pct))}</td>
                    <td>${escapeHtml(accurateText)}</td>
                    <td>${escapeHtml(tradedText)}</td>
                </tr>
            `;
        }).join('');

        tbody.querySelectorAll('tr[data-signal-id]').forEach((row) => {
            row.addEventListener('click', () => {
                const signalId = row.getAttribute('data-signal-id');
                state.signalExplorer.selectedSignalId = signalId;
                renderSignalDetail(signalId);
                tbody.querySelectorAll('tr').forEach((tr) => tr.classList.remove('selected'));
                row.classList.add('selected');
            });
        });
    }

    function renderSignalDetail(signalId) {
        const panel = byId('signalDetailPanel');
        if (!panel) return;
        const row = state.signalExplorer.rows.find((item) => String(item.signal_id) === String(signalId));
        if (!row) {
            panel.innerHTML = '<div class="analytics-empty">Signal not found.</div>';
            return;
        }
        const payload = {
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
        const triggering = row.triggering_factors || {};
        const marketState = row.bias_at_signal || {};
        const convergenceIds = safeArray(row.convergence_ids);
        panel.innerHTML = `
            <div class="journal-detail-block">
                <h4>Signal Payload</h4>
                <pre style="white-space:pre-wrap;word-break:break-word;max-height:160px;overflow:auto;">${escapeHtml(JSON.stringify(payload, null, 2))}</pre>
            </div>
            <div class="journal-detail-block">
                <h4>Market State Snapshot</h4>
                <pre style="white-space:pre-wrap;word-break:break-word;max-height:160px;overflow:auto;">${escapeHtml(JSON.stringify(marketState, null, 2))}</pre>
            </div>
            <div class="journal-detail-block">
                <h4>Factor Scores</h4>
                <pre style="white-space:pre-wrap;word-break:break-word;max-height:140px;overflow:auto;">${escapeHtml(JSON.stringify(triggering, null, 2))}</pre>
            </div>
            <div class="journal-detail-block">
                <h4>Convergence IDs</h4>
                <div>${convergenceIds.length ? convergenceIds.map((id) => `<span class="signal-tag">${escapeHtml(id)}</span>`).join('') : 'None'}</div>
            </div>
        `;
    }

    async function loadSignalExplorer() {
        if (state.mode !== 'analytics') return;
        const filters = getSignalFilters();
        if (state.selectedSignalSource && !byId('signalFilterSource')?.value) {
            const sourceSelect = byId('signalFilterSource');
            if (sourceSelect) sourceSelect.value = state.selectedSignalSource;
        }
        try {
            const [rawPayload, stats] = await Promise.all([
                fetchJson('/signals', filters),
                fetchJson('/signal-stats', filters)
            ]);
            const rows = safeArray(rawPayload?.rows);
            state.signalExplorer.rows = rows;
            renderSignalTable(rows);
            renderSignalStatsPanel(stats || {});
            renderSignalExplorerCharts(rows, stats || {});
            const sourceOptions = rows.map((row) => row.source || row.strategy || row.signal_type).filter(Boolean);
            refreshSourceFilterOptions(sourceOptions);

            if (state.signalExplorer.selectedSignalId) {
                renderSignalDetail(state.signalExplorer.selectedSignalId);
            } else if (rows.length) {
                state.signalExplorer.selectedSignalId = rows[0].signal_id;
                renderSignalDetail(rows[0].signal_id);
            }
        } catch (error) {
            console.error('Signal explorer load failed:', error);
            const tbody = byId('signalExplorerTableBody');
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="9" class="analytics-empty">Signal explorer error: ${escapeHtml(error.message || 'unknown')}</td></tr>`;
            }
            const panel = byId('signalStatsPanel');
            if (panel) panel.innerHTML = '<div class="analytics-empty">Unable to load stats.</div>';
        }
    }

    function buildFactorValueMap(rows, key, valueKey) {
        const out = {};
        safeArray(rows).forEach((row) => {
            const k = String(row[key] || '').slice(0, 10);
            if (!k) return;
            out[k] = asNumber(row[valueKey], 0);
        });
        return out;
    }

    function normalizeFactor(value) {
        return String(value || '').trim();
    }

    function populateFactorSelectors(factors) {
        const factorSelect = byId('factorLabFactorSelect');
        const compareSelect = byId('factorLabCompareSelect');
        if (!factorSelect || !compareSelect) return;

        const factorNames = safeArray(factors).map((f) => normalizeFactor(f.name)).filter(Boolean);
        if (!factorNames.length) return;
        if (!state.factorLab.selectedFactor) {
            state.factorLab.selectedFactor = factorNames[0];
        }

        const renderOptions = (select, label) => {
            const current = select.value;
            select.innerHTML = `<option value="">${label}</option>`;
            factorNames.forEach((name) => {
                const opt = document.createElement('option');
                opt.value = name;
                opt.textContent = name;
                select.appendChild(opt);
            });
            if (factorNames.includes(current)) {
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
        const mainTimeline = safeArray(factor?.timeline);
        const compareTimeline = safeArray(compareFactor?.timeline);
        const allDates = new Set(mainTimeline.map((row) => String(row.date)));
        compareTimeline.forEach((row) => allDates.add(String(row.date)));
        safeArray(spyRows).forEach((row) => allDates.add(String(row.date)));
        const labels = [...allDates].sort((a, b) => new Date(a) - new Date(b));

        const mainMap = buildFactorValueMap(mainTimeline, 'date', 'score');
        const compareMap = buildFactorValueMap(compareTimeline, 'date', 'score');
        const spyMap = buildFactorValueMap(spyRows, 'date', 'close');

        const mainValues = labels.map((date) => mainMap[date] ?? null);
        const compareValues = labels.map((date) => compareMap[date] ?? null);
        const spyValues = labels.map((date) => spyMap[date] ?? null);

        const correctness = labels.map((date, idx) => {
            const score = mainValues[idx];
            const currentClose = spyValues[idx];
            const nextClose = spyValues[idx + 1];
            if (!Number.isFinite(score) || !Number.isFinite(currentClose) || !Number.isFinite(nextClose)) return null;
            const nextMove = nextClose - currentClose;
            const match = (score < 0 && nextMove < 0) || (score > 0 && nextMove > 0);
            return match ? 2 : null;
        });

        const datasets = [
            {
                label: `${factor?.name || 'factor'} score`,
                data: mainValues,
                stepped: true,
                borderColor: '#14b8a6',
                backgroundColor: 'rgba(20,184,166,0.08)',
                borderWidth: 2,
                yAxisID: 'y',
                pointRadius: 0
            },
            {
                label: 'Correct Direction',
                data: correctness,
                type: 'bar',
                yAxisID: 'shade',
                backgroundColor: 'rgba(0, 230, 118, 0.08)',
                borderWidth: 0
            },
            {
                label: 'SPY Close',
                data: spyValues,
                borderColor: '#9fb7ff',
                borderWidth: 1.8,
                tension: 0.2,
                yAxisID: 'y1',
                pointRadius: 0
            }
        ];

        if (compareFactor) {
            datasets.push({
                label: `${compareFactor.name} score`,
                data: compareValues,
                stepped: true,
                borderColor: '#fbc02d',
                borderWidth: 1.8,
                yAxisID: 'y',
                pointRadius: 0
            });
        }

        upsertChart('factorTimeline', 'factorLabTimelineChart', {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: 'index', intersect: false },
                scales: {
                    x: { ticks: { color: '#89a1c8', maxTicksLimit: 10 }, grid: { color: 'rgba(38,53,85,0.25)' } },
                    y: { min: -2, max: 2, ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.25)' } },
                    y1: {
                        position: 'right',
                        ticks: { color: '#89a1c8' },
                        grid: { drawOnChartArea: false }
                    },
                    shade: { display: false, min: 0, max: 2, stacked: true }
                },
                plugins: { legend: { labels: { color: '#9fb7ff' } } }
            }
        });
    }

    function renderFactorStats(factor) {
        const accuracyCard = byId('factorLabAccuracyCard');
        const staleCard = byId('factorLabStaleCard');
        const regimeCard = byId('factorLabBestRegimeCard');
        const corrCard = byId('factorLabCorrelationCard');
        if (!factor || !accuracyCard || !staleCard || !regimeCard || !corrCard) return;

        accuracyCard.innerHTML = `
            <div class="analytics-card-header"><h3>Accuracy</h3></div>
            <div class="factor-stat-line">When URSA: ${(asNumber(factor.accuracy_when_ursa) * 100).toFixed(1)}%</div>
            <div class="factor-stat-line">When TORO: ${(asNumber(factor.accuracy_when_toro) * 100).toFixed(1)}%</div>
            <div class="factor-stat-line">Overall: ${(((asNumber(factor.accuracy_when_ursa) + asNumber(factor.accuracy_when_toro)) / 2) * 100).toFixed(1)}%</div>
        `;
        staleCard.innerHTML = `
            <div class="analytics-card-header"><h3>Stale Rate</h3></div>
            <div class="factor-stat-line">${(asNumber(factor.stale_pct) * 100).toFixed(2)}% stale readings</div>
            <div class="factor-stat-line">Last stale: ${escapeHtml(factor.last_stale_date || '--')}</div>
        `;
        regimeCard.innerHTML = `
            <div class="analytics-card-header"><h3>Best Regime</h3></div>
            <div class="factor-stat-line">${escapeHtml(String(factor.best_regime || '--'))}</div>
            <div class="factor-stat-line">Avg score: ${asNumber(factor.avg_score).toFixed(2)}</div>
        `;
        corrCard.innerHTML = `
            <div class="analytics-card-header"><h3>Correlation</h3></div>
            <div class="factor-stat-line">Strongest: ${escapeHtml(String(factor.most_correlated_with || '--'))}</div>
            <div class="factor-stat-line">SPY next-day r: ${asNumber(factor.correlation_with_spy_next_day).toFixed(2)}</div>
        `;
    }

    function correlationColor(value) {
        const v = Math.max(-1, Math.min(1, asNumber(value, 0)));
        if (v >= 0) {
            const g = Math.round(120 + (v * 100));
            const r = Math.round(255 - (v * 160));
            const b = Math.round(255 - (v * 180));
            return `rgb(${r}, ${g}, ${b})`;
        }
        const n = Math.abs(v);
        const r = Math.round(170 + (n * 70));
        const g = Math.round(160 - (n * 120));
        const b = Math.round(160 - (n * 120));
        return `rgb(${r}, ${g}, ${b})`;
    }

    function renderCorrelationMatrix(matrix) {
        const container = byId('factorLabCorrelationMatrix');
        if (!container) return;
        const names = Object.keys(matrix || {});
        if (!names.length) {
            container.innerHTML = '<div class="analytics-empty">Collecting data - matrix will appear after factor history accumulates.</div>';
            return;
        }
        const header = names.map((name) => `<th>${escapeHtml(name)}</th>`).join('');
        const rows = names.map((rowName) => {
            const cols = names.map((colName) => {
                const value = rowName === colName ? 1.0 : asNumber(matrix?.[rowName]?.[colName], 0);
                const bg = correlationColor(value);
                return `<td style="background:${bg}" title="${escapeHtml(`${rowName} vs ${colName}: ${value.toFixed(3)}`)}">${value.toFixed(2)}</td>`;
            }).join('');
            return `<tr><td class="corr-header">${escapeHtml(rowName)}</td>${cols}</tr>`;
        }).join('');
        container.innerHTML = `
            <table class="correlation-table">
                <thead><tr><th></th>${header}</tr></thead>
                <tbody>${rows}</tbody>
            </table>
        `;
    }

    async function loadFactorLab() {
        if (state.mode !== 'analytics') return;
        const days = asNumber(byId('factorLabDays')?.value, 60);
        state.factorLab.days = days;
        try {
            const perf = await fetchJson('/factor-performance', { days });
            const factors = safeArray(perf?.factors);
            if (!factors.length) {
                byId('factorLabCorrelationMatrix').innerHTML = '<div class="analytics-empty">Collecting data - metrics will appear after factor history accumulates.</div>';
                return;
            }

            state.factorLab.factors = factors;
            populateFactorSelectors(factors);
            state.factorLab.selectedFactor = byId('factorLabFactorSelect')?.value || state.factorLab.selectedFactor || factors[0].name;
            state.factorLab.compareFactor = byId('factorLabCompareSelect')?.value || '';
            const mainFactor = factors.find((f) => f.name === state.factorLab.selectedFactor) || factors[0];
            const compareFactor = factors.find((f) => f.name === state.factorLab.compareFactor) || null;

            const pricePayload = await fetchJson('/price-data', { ticker: 'SPY', timeframe: 'D', days });
            renderFactorTimelineChart(mainFactor, compareFactor, safeArray(pricePayload?.rows));
            renderFactorStats(mainFactor);
            renderCorrelationMatrix(perf?.correlation_matrix || {});
        } catch (error) {
            console.error('Factor lab load failed:', error);
            byId('factorLabCorrelationMatrix').innerHTML = `<div class="analytics-empty">Factor lab error: ${escapeHtml(error.message || 'unknown')}</div>`;
        }
    }

    function initBacktestDefaults() {
        const now = new Date();
        const end = now.toISOString().slice(0, 10);
        const startDate = new Date(now.getTime() - (1000 * 60 * 60 * 24 * 120)).toISOString().slice(0, 10);
        ['backtestEndDate', 'backtestCompareEndDate'].forEach((id) => {
            const node = byId(id);
            if (node && !node.value) node.value = end;
        });
        ['backtestStartDate', 'backtestCompareStartDate'].forEach((id) => {
            const node = byId(id);
            if (node && !node.value) node.value = startDate;
        });
    }

    function collectBacktestPayload(compare = false) {
        const pfx = compare ? 'backtestCompare' : 'backtest';
        return {
            source: byId(`${pfx}Strategy`)?.value || 'whale_hunter',
            ticker: byId(`${pfx}Ticker`)?.value?.trim().toUpperCase() || null,
            direction: byId(`${pfx}Direction`)?.value || null,
            start_date: byId(`${pfx}StartDate`)?.value,
            end_date: byId(`${pfx}EndDate`)?.value,
            params: {
                entry: 'signal_price',
                stop_distance_pct: asNumber(byId(`${pfx}StopPct`)?.value, 0.5),
                target_distance_pct: asNumber(byId(`${pfx}TargetPct`)?.value, 1.0),
                risk_per_trade: asNumber(byId(`${pfx}RiskPerTrade`)?.value, 235),
                min_conviction: byId(`${pfx}MinConviction`)?.value || null,
                require_convergence: Boolean(byId(`${pfx}RequireConvergence`)?.checked),
                bias_must_align: Boolean(byId(`${pfx}BiasAlign`)?.checked)
            }
        };
    }

    function renderBacktestTrades(rows) {
        const tbody = byId('backtestTradesBody');
        if (!tbody) return;
        const trades = safeArray(rows);
        if (!trades.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="analytics-empty">No simulated trades for this configuration.</td></tr>';
            return;
        }
        tbody.innerHTML = trades.map((row) => {
            const pnl = asNumber(row.pnl, 0);
            const cls = pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
            return `
                <tr>
                    <td>${escapeHtml(String(row.entry_date || '--'))}</td>
                    <td>${escapeHtml(String(row.entry_price ?? '--'))}</td>
                    <td>${escapeHtml(String(row.exit_price ?? '--'))}</td>
                    <td class="${cls}">${escapeHtml(formatDollar(pnl))}</td>
                    <td>${escapeHtml(String(row.exit_reason || '--'))}</td>
                </tr>
            `;
        }).join('');
    }

    function renderBacktestEquityChart(primary, compare) {
        const primaryCurve = safeArray(primary?.results?.equity_curve);
        const compareCurve = safeArray(compare?.results?.equity_curve);
        const allDates = new Set(primaryCurve.map((p) => String(p.date)));
        compareCurve.forEach((p) => allDates.add(String(p.date)));
        const labels = [...allDates].sort((a, b) => new Date(a) - new Date(b));
        const mainMap = buildFactorValueMap(primaryCurve, 'date', 'cumulative_pnl');
        const compareMap = buildFactorValueMap(compareCurve, 'date', 'cumulative_pnl');

        const datasets = [
            {
                label: 'Primary',
                data: labels.map((d) => mainMap[d] ?? null),
                borderColor: '#14b8a6',
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.25
            }
        ];
        if (compare) {
            datasets.push({
                label: 'Compare',
                data: labels.map((d) => compareMap[d] ?? null),
                borderColor: '#fbc02d',
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.25
            });
        }
        upsertChart('backtestEquity', 'backtestEquityChart', {
            type: 'line',
            data: { labels, datasets },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#9fb7ff' } } },
                scales: {
                    x: { ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.25)' } },
                    y: { ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.25)' } }
                }
            }
        });
    }

    function renderBacktestSummary(primary, compare) {
        const panel = byId('backtestResultsPanel');
        if (!panel) return;
        const a = primary?.results || {};
        const b = compare?.results || null;
        panel.innerHTML = `
            <div class="analytics-summary-row">
                Trades: ${asNumber(a.total_trades)} | Win Rate: ${(asNumber(a.win_rate) * 100).toFixed(1)}% | Total P&L: ${formatDollar(a.total_pnl)} | Sharpe: ${asNumber(a.sharpe).toFixed(2)} | Max DD: ${formatDollar(a.max_drawdown)} | Avg R:R: ${asNumber(a.avg_rr).toFixed(2)}
            </div>
            ${b ? `<div class="analytics-summary-row">Compare -> Trades: ${asNumber(b.total_trades)} | Win Rate: ${(asNumber(b.win_rate) * 100).toFixed(1)}% | Total P&L: ${formatDollar(b.total_pnl)} | Sharpe: ${asNumber(b.sharpe).toFixed(2)} | Max DD: ${formatDollar(b.max_drawdown)} | Avg R:R: ${asNumber(b.avg_rr).toFixed(2)}</div>` : ''}
        `;
    }

    async function runBacktest(compare = false) {
        const payload = collectBacktestPayload(compare);
        if (!payload.start_date || !payload.end_date) {
            window.alert('Backtest requires start and end dates.');
            return;
        }
        const panel = byId('backtestResultsPanel');
        if (panel) panel.innerHTML = '<div class="analytics-empty">Running backtest...</div>';
        try {
            const result = await fetchJson('/backtest', {}, { method: 'POST', body: payload });
            if (compare) {
                state.backtest.compare = result;
            } else {
                state.backtest.primary = result;
                state.backtest.compare = null;
                const compareBtn = byId('backtestCompareBtn');
                if (compareBtn) compareBtn.hidden = false;
            }
            renderBacktestSummary(state.backtest.primary, state.backtest.compare);
            renderBacktestEquityChart(state.backtest.primary, state.backtest.compare);
            renderBacktestTrades(state.backtest.primary?.results?.trades || []);
            byId('backtestEquityWrap').hidden = false;
            byId('backtestTradesWrap').hidden = false;
        } catch (error) {
            console.error('Backtest failed:', error);
            if (panel) panel.innerHTML = `<div class="analytics-empty">Backtest error: ${escapeHtml(error.message || 'unknown')}</div>`;
        }
    }

    function renderRiskCards(payload) {
        const container = byId('riskAccountCards');
        if (!container) return;
        const accounts = payload?.accounts || {};
        const names = Object.keys(accounts);
        if (!names.length) {
            container.innerHTML = '<div class="analytics-empty">Collecting data - risk cards will appear after snapshots accumulate.</div>';
            return;
        }
        container.innerHTML = names.map((name) => {
            const card = accounts[name] || {};
            const warning = card.warning ? `<div class="risk-warning">${escapeHtml(card.warning)}</div>` : '';
            return `
                <div class="risk-account-card">
                    <div class="risk-account-title">${escapeHtml(name)}</div>
                    <div class="risk-account-line">Balance: ${card.balance !== null && card.balance !== undefined ? formatDollar(card.balance) : '--'}</div>
                    <div class="risk-account-line">Open: ${asNumber(card.open_positions)} positions</div>
                    <div class="risk-account-line">At Risk: ${formatDollar(card.total_risk)} (${formatRawPercent(card.risk_pct)})</div>
                    <div class="risk-account-line">Net Delta: ${asNumber(card.net_delta).toFixed(2)}</div>
                    <div class="risk-account-line">Correlated: ${asNumber(card.correlated_positions)} | Max cluster: ${formatDollar(card.max_correlated_loss)}</div>
                    ${warning}
                </div>
            `;
        }).join('');
    }

    function renderRiskCharts(payload) {
        const directionRisk = payload?.direction_risk || {};
        const longRisk = asNumber(directionRisk.LONG, 0);
        const shortRisk = asNumber(directionRisk.SHORT, 0);
        upsertChart('riskDirection', 'riskDirectionChart', {
            type: 'doughnut',
            data: {
                labels: ['LONG', 'SHORT'],
                datasets: [{
                    data: [longRisk, shortRisk],
                    backgroundColor: ['rgba(0,230,118,0.65)', 'rgba(229,55,14,0.65)'],
                    borderColor: ['#00e676', '#e5370e'],
                    borderWidth: 1
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#9fb7ff' } } }
            }
        });

        const exposure = safeArray(payload?.ticker_exposure).slice(0, 12);
        upsertChart('riskTickerExposure', 'riskTickerExposureChart', {
            type: 'bar',
            data: {
                labels: exposure.map((row) => row.ticker),
                datasets: [{
                    label: '$ at Risk',
                    data: exposure.map((row) => asNumber(row.risk, 0)),
                    backgroundColor: exposure.map((row) => row.direction === 'LONG' ? 'rgba(0,230,118,0.65)' : 'rgba(229,55,14,0.65)')
                }]
            },
            options: {
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: '#9fb7ff' } } },
                scales: {
                    x: { ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.25)' } },
                    y: { ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.25)' } }
                }
            }
        });
    }

    function renderRiskCorrelation(payload) {
        const tbody = byId('riskCorrelationTableBody');
        const recommendation = byId('riskCorrelationRecommendation');
        if (!tbody || !recommendation) return;
        const groups = safeArray(payload?.correlated_groups);
        if (!groups.length) {
            tbody.innerHTML = '<tr><td colspan="5" class="analytics-empty">No correlated clusters detected.</td></tr>';
            recommendation.textContent = 'No immediate concentration warning.';
            return;
        }
        tbody.innerHTML = groups.map((group) => `
            <tr>
                <td>${escapeHtml(String(group.account || '--'))}</td>
                <td>${escapeHtml(String(group.direction || '--'))}</td>
                <td>${escapeHtml(safeArray(group.tickers).join(', '))}</td>
                <td>${escapeHtml(formatDollar(group.combined_risk))}</td>
                <td>${escapeHtml(formatDollar(group.estimated_1pct_move_impact))}</td>
            </tr>
        `).join('');
        recommendation.textContent = groups[0]?.recommendation || 'Monitor correlated exposure.';
    }

    async function loadRiskHistoryChart() {
        const account = byId('riskHistoryAccount')?.value || 'robinhood';
        const days = asNumber(byId('riskHistoryDays')?.value, 30);
        try {
            const payload = await fetchJson('/risk-history', { account, days });
            const rows = safeArray(payload?.rows);
            const labels = rows.map((row) => row.date);
            const riskPct = rows.map((row) => asNumber(row.risk_pct, 0));
            upsertChart('riskHistory', 'riskHistoryChart', {
                type: 'line',
                data: {
                    labels,
                    datasets: [
                        {
                            label: 'Risk %',
                            data: riskPct,
                            borderColor: '#14b8a6',
                            borderWidth: 2,
                            tension: 0.25,
                            pointRadius: 0
                        },
                        {
                            label: '15% threshold',
                            data: labels.map(() => 15),
                            borderColor: 'rgba(251, 192, 45, 0.7)',
                            borderDash: [4, 4],
                            borderWidth: 1,
                            pointRadius: 0
                        },
                        {
                            label: '25% threshold',
                            data: labels.map(() => 25),
                            borderColor: 'rgba(229, 55, 14, 0.7)',
                            borderDash: [4, 4],
                            borderWidth: 1,
                            pointRadius: 0
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { labels: { color: '#9fb7ff' } } },
                    scales: {
                        x: { ticks: { color: '#89a1c8' }, grid: { color: 'rgba(38,53,85,0.25)' } },
                        y: {
                            ticks: { color: '#89a1c8', callback: (v) => `${v}%` },
                            grid: { color: 'rgba(38,53,85,0.25)' }
                        }
                    }
                }
            });
        } catch (error) {
            console.error('Risk history load failed:', error);
        }
    }

    async function loadRiskTab() {
        if (state.mode !== 'analytics') return;
        try {
            const payload = await fetchJson('/portfolio-risk');
            renderRiskCards(payload || {});
            renderRiskCharts(payload || {});
            renderRiskCorrelation(payload || {});
            await loadRiskHistoryChart();
        } catch (error) {
            console.error('Risk tab load failed:', error);
            byId('riskAccountCards').innerHTML = `<div class="analytics-empty">Risk load error: ${escapeHtml(error.message || 'unknown')}</div>`;
        }
    }

    function refreshAll() {
        if (state.mode !== 'analytics') return;
        if (state.activeTab === 'dashboard') loadDashboard();
        if (state.activeTab === 'trade-journal') loadTradeJournal();
        if (state.activeTab === 'signal-explorer') loadSignalExplorer();
        if (state.activeTab === 'factor-lab') loadFactorLab();
        if (state.activeTab === 'risk') loadRiskTab();
    }

    function init() {
        if (state.initialized) return;
        state.initialized = true;

        bindTabs();
        bindDashboardControls();
        bindJournalControls();
        bindSignalExplorerControls();
        bindFactorLabControls();
        bindBacktestControls();
        bindRiskControls();

        document.addEventListener('pandora:modechange', (event) => {
            const mode = event?.detail?.mode || 'hub';
            onModeChange(mode);
        });

        state.mode = document.body?.dataset?.mode || state.mode;
        setActiveTab('dashboard');

        if (state.mode === 'analytics') {
            refreshAll();
        }

        window.analyticsUI = {
            refreshAll,
            loadDashboard,
            loadTradeJournal,
            loadSignalExplorer,
            loadFactorLab,
            loadRiskTab,
            activateTab: setActiveTab
        };
    }

    document.addEventListener('DOMContentLoaded', init);
})();
