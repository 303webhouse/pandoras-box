/* Dashboard v2 — "Judgment Layer" · Phase B2a shell.
   Grid + regime band + movers tape. All pollers via managedInterval (visibility-gated,
   idle budget < 10). Own module — no app.js / laboratory / analytics code loads here. */
(function () {
  'use strict';

  // ── Visibility-gated interval manager (P0 pattern) ─────────────────────────
  const _managed = new Map();
  let _seq = 0;
  function managedInterval(fn, ms) {
    const id = ++_seq;
    _managed.set(id, { fn, ms, timer: document.visibilityState === 'visible' ? setInterval(fn, ms) : null });
    return id;
  }
  document.addEventListener('visibilitychange', () => {
    const vis = document.visibilityState === 'visible';
    _managed.forEach((e) => {
      if (vis && e.timer === null) { e.timer = setInterval(e.fn, e.ms); try { e.fn(); } catch (_) {} }
      else if (!vis && e.timer !== null) { clearInterval(e.timer); e.timer = null; }
    });
  });

  // ── Central glossary (single source of truth for tooltips) ─────────────────
  const GLOSSARY = {
    HEALTH: 'Global data health — lime fresh, teal stale, vermilion feed down',
    MOVERS: 'Top gainers/losers screener (Yahoo), filtered: last >= $2, avg vol >= 500k',
    REGIME: 'Two lenses: Composite (weighted factor bias, X/100) vs Stable engine read (breadth-based)',
    COMPOSITE: 'Composite bias score on a 0–100 scale (50 = neutral); the weighted factor blend',
    STABLE: 'Stable engine regime — RISK-ON/NEUTRAL/RISK-OFF from % of universe above 50DMA',
    DIVERGE: 'The Composite and Stable lenses disagree on direction — size with caution',
    DOM: 'Dominant theme — score >= 75',
    EMG: 'Emerging / improving theme',
    FAD: 'Fading / deteriorating theme',
    TIDE: 'Market tide — net options-flow direction (net call vs put premium, cached UW read)',
    HL: 'New 20-day / 52-week highs (H) and lows (L) across the scored universe',
    BREADTH50: 'Percent of the scored universe above its 50-day moving average',
    BREADTH: 'Participation: % of universe above 20/50/200DMA, new highs/lows, ±3% movers',
    KILL: 'Kill-switch / circuit-breaker state — ARMED means a market-risk breaker fired',
    THEMES: 'Ranked theme board: score, 1-day delta, and status (dominant/emerging/fading)',
    DIVERGENCE: 'Sector ETF %-change spread — which sectors lead/lag; dot = above both 50/200DMA',
    INDEX: 'Major index 1-day % and ATR extension (how stretched vs typical range)',
    CURVE: 'Treasury yield curve with a 5-day-ago ghost line; bp = basis-point day change',
    USD: 'Dollar carry check — DXY and USD/JPY level and day change',
    BOOK: 'Open book: balance, day P&L, net Greeks, theme-concentration guardrail, and positions',
    ADD: 'Log a new position — calls the same create endpoint the legacy hub uses',
    KAIROS: 'Live actionable setups, ordered by grade / decision clock / regime fit',
    CLOCK: 'Decision clock — time left before this setup expires; pulses until you open it',
    RIVER: 'Merged judged stream: signals, regime shifts, flow, catalysts, headlines',
    R: 'Regime alignment', F: 'Flow confirmation',
    L: 'At a Pythia level (VAH/VAL/POC) — evidence lights when price sits on a value-area level',
    C: 'Crowding — consensus positioning (post-flip metric; shown gray until wired, never faked)',
    VAH: 'Value-area high', VAL: 'Value-area low', POC: 'Point of control',
    GRIP: 'Drag to move · resize from the tile edges',
    DMA: 'Sector vs its moving averages — lime: above both 50 & 200DMA · vermilion: below both · gray: mixed',
    CONC: 'Theme concentration guardrail — turns vermilion when one theme exceeds 50% of at-risk book',
  };
  // Setup display map (UI-only; DB keys unchanged). shadow = never actionable A-grade.
  const SETUP_MAP = {
    ICARUS: { name: 'ICARUS', desc: 'Fade VAH' },
    HELEN: { name: 'HELEN', desc: 'Reclaim VA' },
    ARGO: { name: 'ARGO', desc: 'Range Break + Flow' },
    TRITON: { name: 'TRITON', desc: 'Whale Hunting', shadow: true },
    HERA: { name: 'HERA', desc: '3-10 Oscillator Cross', shadow: true },
  };
  function setupDisplay(key) {
    const k = String(key || '').toUpperCase();
    for (const id in SETUP_MAP) { if (k.indexOf(id) !== -1) return SETUP_MAP[id]; }
    return { name: key || 'SETUP', desc: '' };
  }
  function applyGlossary(root) {
    (root || document).querySelectorAll('[data-gloss]').forEach((el) => {
      const g = GLOSSARY[el.getAttribute('data-gloss')];
      if (g) el.setAttribute('title', g);
    });
  }

  // ── Minimal fetch + login overlay (standalone auth, reuses /api/auth) ──────
  const _rawFetch = window.fetch.bind(window);
  let _loginShown = false;
  async function apiFetch(url, opts) {
    const r = await _rawFetch(url, opts);
    if (r.status === 401) showLogin();
    return r;
  }
  function showLogin() {
    if (_loginShown || document.getElementById('v2-login')) return;
    _loginShown = true;
    const ov = document.createElement('div');
    ov.id = 'v2-login';
    ov.style.cssText = 'position:fixed;inset:0;z-index:200;background:#050810;display:flex;align-items:center;justify-content:center;font-family:system-ui';
    ov.innerHTML = '<form style="background:#0b1122;padding:30px;border:1px solid #223258;border-radius:12px;display:flex;flex-direction:column;gap:12px;min-width:280px">'
      + '<div style="color:#14b8a6;font-weight:700;letter-spacing:2px">PANDORA v2</div>'
      + '<input id="v2pw" type="password" placeholder="Password" style="padding:10px;border-radius:6px;border:1px solid #223258;background:#050810;color:#e2e8f0">'
      + '<button type="submit" style="padding:10px;border:none;border-radius:6px;background:#14b8a6;color:#050810;font-weight:700;cursor:pointer">Sign in</button>'
      + '<div id="v2err" style="color:#ff5c33;font-size:12px;min-height:14px"></div></form>';
    document.body.appendChild(ov);
    ov.querySelector('#v2pw').focus();
    ov.querySelector('form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const r = await _rawFetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, body: JSON.stringify({ password: ov.querySelector('#v2pw').value }) });
      if (r.ok) location.reload();
      else ov.querySelector('#v2err').textContent = r.status === 401 ? 'Invalid password' : 'Login unavailable';
    });
  }

  // ── Helpers ────────────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const fmtPct = (v) => (v == null ? '--' : (v >= 0 ? '+' : '') + Number(v).toFixed(2) + '%');
  function ageLabel(sec) {
    if (sec == null) return 'unknown';
    if (sec < 90) return Math.round(sec) + 's';
    if (sec < 5400) return Math.round(sec / 60) + 'm';
    return Math.round(sec / 3600) + 'h';
  }
  function setHealth(el, ageSec, degraded, flatline) {
    if (!el) return;
    let cls = 'health-dot', txt = 'fresh';
    if (flatline) { cls += ' dead'; txt = 'DEAD — data pipe flatlined (aged past its SLO)'; }
    else if (degraded || ageSec == null) { cls += ' down'; txt = 'unknown / degraded'; }
    else if (ageSec > 900) { cls += ' stale'; txt = 'stale ' + ageLabel(ageSec); }
    else { cls += ' ok'; txt = 'fresh ' + ageLabel(ageSec); }
    el.className = cls;
    el.setAttribute('title', txt);
  }

  const _health = { regime: null, movers: null };
  const _flat = {}; // feed -> flatline bool
  function updateGlobalHealth() {
    const anyFlat = Object.values(_flat).some(Boolean);
    const vals = Object.values(_health).filter((v) => v !== null);
    const worst = anyFlat ? 'dead' : vals.includes('down') ? 'down' : vals.includes('stale') ? 'stale' : vals.length ? 'ok' : '';
    const dot = $('dataHealthDot');
    dot.className = 'health-dot' + (worst ? ' ' + worst : '');
    dot.setAttribute('title', GLOSSARY.HEALTH + ' — ' + (worst === 'dead' ? 'DEAD feed(s) — pipe flatlined' : (worst || 'no data')));
  }
  // Record a feed's flatline state; adds exactly one River action item per incident
  // (River dedups by id) and removes it on recovery.
  function noteFlatline(feed, isFlat, label) {
    const was = !!_flat[feed]; _flat[feed] = !!isFlat;
    const id = 'flatline:' + feed;
    if (isFlat) {
      addRiverItems([{ id, type: 'regime', tier: 'action', sev: 'down', ts: Date.now(),
        text: `<b>DEAD · ${esc(label || feed)} feed flatlined</b> — data pipe aged past its SLO (not just stale). Check /health → stable_jobs.` }]);
    } else if (was) { _river.delete(id); _rvAcked.delete(id); }
    if (was !== !!isFlat) renderRiver();
    updateGlobalHealth();
  }

  // ── Regime band ─────────────────────────────────────────────────────────────
  // Composite score is on a -1..+1 scale; render as X/100 to match the legacy banner:
  const to100 = (s) => (s == null || !Number.isFinite(Number(s))) ? null : Math.round(((Number(s) + 1) / 2) * 100);
  let _lastRegime = { composite: null, regime: null, tide: null, kill: null };

  async function loadRegimeBand() {
    let composite = null, regime = null, tide = null, kill = null;
    try { const r = await apiFetch('/api/bias/composite'); if (r.ok) composite = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/stable/regime'); if (r.ok) regime = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/board/tide'); if (r.ok) tide = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/board/kill-switch'); if (r.ok) kill = await r.json(); } catch (_) {}
    _lastRegime = { composite, regime, tide, kill };
    renderRegimeBand(composite, regime, tide, kill);
    renderBreadthPanel(regime);          // b3 shares the regime payload
    emitRegimeRiverItems(composite, regime, kill);

    const age = regime && regime.data_age_seconds != null ? regime.data_age_seconds : null;
    const degraded = regime ? regime.degraded : true;
    _health.regime = (regime && regime.flatline) ? 'down' : (degraded || age == null) ? 'down' : age > 900 ? 'stale' : 'ok';
    noteFlatline('nightly', regime && regime.flatline, 'Regime / Themes');
    updateGlobalHealth();
  }

  function themeChips(list, cls, limit) {
    if (!list || !list.length) return '<span class="chip muted">none</span>';
    return list.slice(0, limit || 3).map((t) =>
      `<span class="chip ${cls}">${esc(t.theme)} <b>${t.score != null ? Math.round(t.score) : ''}</b></span>`).join(' ');
  }

  function renderRegimeBand(composite, regime, tide, kill) {
    const band = $('regimeBand');

    // ── Cell 1: two regime lenses, rendered distinctly ──
    const bias = composite ? (composite.bias_level || composite.level || 'UNKNOWN') : 'UNKNOWN';
    const comp100 = composite ? to100(composite.composite_score) : null;
    const biasCls = bias.includes('TORO') || bias.includes('BULL') ? 'val-up' : bias.includes('URSA') || bias.includes('BEAR') ? 'val-down' : 'val-teal';
    const breadth = (regime && regime.breadth) || {};
    const regimeLabel = regime ? (regime.regime_label || 'UNKNOWN') : 'UNKNOWN';
    const p50 = breadth.pct_above_50dma;
    const stableCls = regimeLabel === 'RISK-ON' ? 'val-up' : regimeLabel === 'RISK-OFF' ? 'val-down' : 'val-teal';
    // Divergence: one lens leans bullish while the other leans bearish
    const compDir = comp100 == null ? 0 : comp100 >= 55 ? 1 : comp100 <= 45 ? -1 : 0;
    const stableDir = regimeLabel === 'RISK-ON' ? 1 : regimeLabel === 'RISK-OFF' ? -1 : 0;
    const diverge = compDir !== 0 && stableDir !== 0 && compDir !== stableDir;

    // ── Cell 3: Tide ──
    const t = tide && tide.tide;
    const tideDir = t && t.direction ? t.direction : null;
    const tideCls = tideDir === 'BULLISH' ? 'val-up' : tideDir === 'BEARISH' ? 'val-down' : 'val-muted';
    const fmtM = (v) => (v == null ? '--' : '$' + (Number(v) / 1e6).toFixed(0) + 'M');
    const tideSub = t ? `call ${fmtM(t.net_call_premium)} · put ${fmtM(t.net_put_premium)}`
      : (tide && tide.degraded ? 'no cached flow' : '—');

    // ── Cell 6: Kill-switch ──
    const k = kill && kill.kill_switch;
    const armed = k && k.active;
    const pending = k && k.pending_reset;
    const killLabel = armed ? (pending ? 'PENDING' : 'ARMED') : 'CLEAR';
    const killCls = armed ? (pending ? 'val-teal' : 'val-down') : 'val-teal';
    const killPulse = armed && !pending ? ' pulse-vermilion' : '';
    const killSub = armed ? esc(k.trigger || 'risk-off') : 'normal';

    const hl = (h, l) => `<span class="val-up num">${h != null ? h : '--'}</span><span class="val-muted"> / </span><span class="val-down num">${l != null ? l : '--'}</span>`;

    band.innerHTML = `
      <div class="regime-cell" data-drawer="regime">
        <span class="label" data-gloss="REGIME">Regime · two lenses</span>
        <div class="sub"><span class="chip emg" data-gloss="COMPOSITE">C</span> <span class="${biasCls}">${esc(bias.replace(/_/g, ' '))}</span> <b class="num">${comp100 != null ? comp100 + '/100' : '--'}</b></div>
        <div class="sub"><span class="chip emg" data-gloss="STABLE">S</span> <span class="${stableCls}">${esc(regimeLabel)}</span> <span class="num">${p50 != null ? p50.toFixed(0) + '% &gt;50d' : ''}</span>${diverge ? ' <span class="val-teal" data-gloss="DIVERGE">⚠ divergence</span>' : ''}</div>
      </div>
      <div class="regime-cell" data-drawer="themes">
        <span class="label">Dominant · Emerging · Fading</span>
        <div class="row">${themeChips(regime && regime.dominant, 'dom', 2)} ${themeChips(regime && regime.emerging, 'emg', 2)} ${themeChips(regime && regime.fading, 'fad', 2)}</div>
      </div>
      <div class="regime-cell">
        <span class="label" data-gloss="TIDE">Tide</span>
        <div class="big ${tideCls}">${tideDir || '—'}</div>
        <div class="sub">${tideSub}</div>
      </div>
      <div class="regime-cell" data-drawer="breadth">
        <span class="label" data-gloss="HL">New H / L</span>
        <div class="sub">20d ${hl(breadth.new_high_20d, breadth.new_low_20d)}</div>
        <div class="sub">52w ${hl(breadth.new_high_52w, breadth.new_low_52w)} <span class="val-muted">·</span> ±3% <span class="val-up num">${breadth.up_3 != null ? breadth.up_3 : '--'}</span>/<span class="val-down num">${breadth.down_3 != null ? breadth.down_3 : '--'}</span></div>
      </div>
      <div class="regime-cell" data-drawer="breadth">
        <span class="label" data-gloss="BREADTH50">% &gt; 50DMA</span>
        <div class="big num ${p50 != null && p50 >= 60 ? 'val-up' : p50 != null && p50 <= 40 ? 'val-down' : 'val-teal'}">${p50 != null ? p50.toFixed(0) + '%' : '--'}</div>
        <div class="gauge"><span style="width:${p50 != null ? Math.max(0, Math.min(100, p50)) : 0}%"></span></div>
      </div>
      <div class="regime-cell${killPulse}">
        <span class="label" data-gloss="KILL">Kill-switch</span>
        <div class="big ${killCls}">${killLabel}</div>
        <div class="sub">${killSub}</div>
      </div>`;
    applyGlossary(band);
    band.querySelectorAll('[data-drawer]').forEach((c) => c.addEventListener('click', () => openDrawer(c.dataset.drawer, { composite, regime, tide, kill })));
  }

  // ── Movers tape ──────────────────────────────────────────────────────────────
  async function loadMoversTape() {
    let data = null;
    try { const r = await apiFetch('/api/stable/movers'); if (r.ok) data = await r.json(); } catch (_) {}
    renderMoversTape(data);
    const age = data && data.data_age_seconds != null ? data.data_age_seconds : null;
    const degraded = data ? data.degraded : true;
    const flat = !!(data && data.flatline);
    setHealth($('moversHealthDot'), age, degraded, flat);
    $('moversAge').textContent = flat ? 'DEAD · pipe stalled' : degraded ? 'stale ' + ageLabel(age) : ageLabel(age) + ' old';
    $('moversAge').className = flat ? 'val-down' : '';
    _health.movers = flat ? 'down' : (degraded || age == null) ? 'down' : age > 900 ? 'stale' : 'ok';
    noteFlatline('movers', flat, 'Movers');
    updateGlobalHealth();
  }

  function moverEl(m, side) {
    const thm = m.theme ? ` <span class="sep">·</span> <span class="thm">${esc(m.theme)}</span>` : '';
    return `<span class="mover ${side}" data-ticker="${esc(m.ticker)}"><span class="tk">${esc(m.ticker)}</span> <span class="pct">${fmtPct(m.pct)}</span>${thm}</span>`;
  }
  function renderMoversTape(data) {
    const tape = $('moversTape');
    if (!data || (!(data.gainers || []).length && !(data.losers || []).length)) {
      tape.innerHTML = '<span class="mover"><span class="thm">movers feed unavailable — showing no data (not fake-fresh)</span></span>';
      return;
    }
    const g = (data.gainers || []).map((m) => moverEl(m, 'gain')).join(' <span class="sep">•</span> ');
    const l = (data.losers || []).map((m) => moverEl(m, 'lose')).join(' <span class="sep">•</span> ');
    const one = g + ' <span class="sep">•</span> ' + l;
    tape.innerHTML = one + ' <span class="sep">•</span> ' + one; // duplicate for seamless marquee
    tape.querySelectorAll('.mover[data-ticker]').forEach((el) => el.addEventListener('click', () => openTvPopover(el.dataset.ticker, el)));
  }

  // ── Drawer ────────────────────────────────────────────────────────────────
  function openDrawer(kind, ctx) {
    const title = $('drawerTitle'), body = $('drawerBody');
    const kv = (k, v) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`;
    if (kind === 'themes' && ctx.regime) {
      title.textContent = 'Themes — dominant / emerging / fading';
      const sec = (name, arr, cls) => `<div style="margin:10px 0 4px;color:var(--text-3);font-family:var(--mono);font-size:11px;letter-spacing:1px">${name}</div>` +
        ((arr || []).map((t) => `<div class="kv"><span class="k"><span class="chip ${cls}">${esc(t.theme)}</span></span><span class="v">${t.score != null ? t.score : ''} · ${esc(t.status || '')}</span></div>`).join('') || '<div class="kv"><span class="k">none</span></div>');
      body.innerHTML = sec('DOMINANT', ctx.regime.dominant, 'dom') + sec('EMERGING', ctx.regime.emerging, 'emg') + sec('FADING', ctx.regime.fading, 'fad');
    } else if (kind === 'breadth' && ctx.regime) {
      title.textContent = 'Breadth';
      const b = ctx.regime.breadth || {};
      body.innerHTML = kv('Total (scored universe)', b.total) + kv('% > 20DMA', b.pct_above_20dma) + kv('% > 50DMA', b.pct_above_50dma) +
        kv('% > 200DMA', b.pct_above_200dma) + kv('New highs 20d', b.new_high_20d) + kv('New highs 52w', b.new_high_52w) +
        kv('Up > 3%', b.up_3) + kv('Down > 3%', b.down_3) + kv('as of (metrics)', ctx.regime.metrics_date);
    } else if (kind === 'committee') {
      title.textContent = 'Committee · ' + (ctx.ticker || '');
      body.innerHTML = kv('Ticker', ctx.ticker || '—') + kv('Signal', ctx.sig || '—') +
        '<div style="margin:10px 0;color:var(--text-3);font-size:12px">Loading options context…</div>';
      (async () => {
        try {
          const r = await apiFetch('/api/committee/enrichment/' + encodeURIComponent(ctx.ticker));
          if (!r.ok) return;
          const e = (await r.json()).enrichment || {};
          const iv = e.iv_rank || {}, tide = e.market_tide || {}, mp = e.max_pain || {}, sf = e.sector_flow || {};
          body.innerHTML = kv('Ticker', ctx.ticker) + kv('Signal', ctx.sig || '—') +
            kv('IV rank', iv.iv_rank != null ? Number(iv.iv_rank).toFixed(0) : '—') +
            kv('Market tide', (tide.net_call_premium != null && tide.net_put_premium != null) ? (Number(tide.net_call_premium) > Number(tide.net_put_premium) ? 'bullish' : 'bearish') : '—') +
            kv('Max pain', mp.max_pain_strike != null ? mp.max_pain_strike + ' (' + mp.dte + 'dte)' : '—') +
            kv('Sector posture', sf.risk_posture || '—') +
            '<div style="margin-top:10px;font-size:11px;color:var(--text-3)">Foreground UW read (on-demand). Full committee review runs from the legacy analyzer.</div>';
        } catch (_) {}
      })();
    } else {
      title.textContent = 'Regime detail';
      const c = ctx.composite || {}, r = ctx.regime || {};
      const t = ctx.tide && ctx.tide.tide, k = ctx.kill && ctx.kill.kill_switch;
      const c100 = to100(c.composite_score);
      body.innerHTML = kv('Composite bias', c.bias_level || c.level || '—') + kv('Composite (0–100)', c100 != null ? c100 + '/100' : '—') +
        kv('Composite raw', c.composite_score != null ? Number(c.composite_score).toFixed(3) : '—') +
        kv('Confidence', c.confidence || '—') + kv('Stable regime', r.regime_label || '—') + kv('% > 50DMA', (r.breadth || {}).pct_above_50dma) +
        kv('Tide', t && t.direction ? t.direction : '—') + kv('Kill-switch', k ? (k.active ? (k.pending_reset ? 'PENDING RESET' : 'ARMED · ' + (k.trigger || '')) : 'CLEAR') : '—') +
        kv('Anchor', r.anchor || '—') + kv('Data age (s)', r.data_age_seconds != null ? Math.round(r.data_age_seconds) : '—');
    }
    $('drawerBackdrop').classList.add('open');
    $('drawer').classList.add('open');
  }
  function closeDrawer() { $('drawerBackdrop').classList.remove('open'); $('drawer').classList.remove('open'); }

  // ── TV popover ────────────────────────────────────────────────────────────
  let _tvWidget = null;
  function openTvPopover(ticker, anchorEl) {
    const pop = $('tvPopover');
    $('tvPopTicker').textContent = ticker;
    $('tvPopHost').innerHTML = '<div id="tvPopHostInner" style="width:100%;height:100%"></div>';
    // position near the click, clamped to viewport
    const r = anchorEl.getBoundingClientRect();
    const w = 520, h = 360;
    pop.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left)) + 'px';
    pop.style.top = Math.max(8, Math.min(window.innerHeight - h - 8, r.bottom + 8)) + 'px';
    pop.classList.add('open');
    try {
      if (window.TradingView) {
        _tvWidget = new TradingView.widget({
          container_id: 'tvPopHostInner', symbol: ticker, interval: 'D', theme: 'dark',
          style: '1', autosize: true, hide_top_toolbar: true, hide_legend: true, save_image: false,
        });
      }
    } catch (_) {}
  }
  function closeTvPopover() { $('tvPopover').classList.remove('open'); $('tvPopHost').innerHTML = ''; }

  // ── Grid + layout persistence ───────────────────────────────────────────────
  let grid = null;
  let saveTimer = null;
  function initGrid() {
    grid = GridStack.init({ column: 12, cellHeight: 46, margin: 7, handle: '.tile-grip', float: false,
      resizable: { handles: 'e, se, s, sw, w' } });
    // Load persisted layout (positions only), then wire save-on-change.
    apiFetch('/api/layout').then((r) => r.ok ? r.json() : null).then((d) => {
      if (d && d.layout && Array.isArray(d.layout) && d.layout.length) {
        try { grid.load(d.layout); } catch (_) {}
        if (d.updated_at) $('layoutStatus').textContent = 'layout restored';
      }
    }).catch(() => {}).finally(() => {
      grid.on('change', () => {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveLayout, 800);
      });
    });
  }
  async function saveLayout() {
    try {
      const layout = grid.save(false); // positions + gs-id, no content
      const r = await apiFetch('/api/layout', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, body: JSON.stringify({ layout }) });
      $('layoutStatus').textContent = r.ok ? 'layout saved ' + new Date().toLocaleTimeString() : (r.status === 401 ? 'sign in to save layout' : 'layout save failed');
    } catch (_) { $('layoutStatus').textContent = 'layout save failed'; }
  }

  // ═══ B2b modules ══════════════════════════════════════════════════════════
  const fmt$ = (v) => (v == null ? '--' : (v < 0 ? '-$' : '$') + Math.abs(Number(v)).toLocaleString('en-US', { maximumFractionDigits: 0 }));
  const signCls = (v) => (v == null ? '' : v > 0 ? 'val-up' : v < 0 ? 'val-down' : 'val-muted');
  function setDot(id, age, degraded, flatline) { setHealth($(id), age, degraded, flatline); }

  // ── b3 Breadth panel (shares the regime payload) ──────────────────────────
  function renderBreadthPanel(regime) {
    const el = $('breadthPanel'); if (!el) return;
    const b = (regime && regime.breadth) || {};
    $('breadthAnchor').textContent = regime ? (regime.anchor || '') : '';
    const gauge = (label, v, gloss) => {
      const w = v != null ? Math.max(0, Math.min(100, v)) : 0;
      const col = v != null && v >= 60 ? 'var(--up)' : v != null && v <= 40 ? 'var(--down)' : 'var(--teal)';
      return `<div class="breadth-gauge"><div class="lab"><span data-gloss="${gloss || ''}">${label}</span><b>${v != null ? v.toFixed(0) + '%' : '--'}</b></div>`
        + `<div class="bar-track"><span style="width:${w}%;background:${col}"></span></div></div>`;
    };
    el.innerHTML = gauge('% &gt; 20DMA', b.pct_above_20dma) + gauge('% &gt; 50DMA', b.pct_above_50dma, 'BREADTH50') + gauge('% &gt; 200DMA', b.pct_above_200dma)
      + `<div class="hl-counts">
           <div class="hl-box"><div class="t">New Highs</div><div class="v val-up">${b.new_high_20d != null ? b.new_high_20d : '--'} <span class="val-muted" style="font-size:10px">20d</span> · ${b.new_high_52w != null ? b.new_high_52w : '--'} <span class="val-muted" style="font-size:10px">52w</span></div></div>
           <div class="hl-box"><div class="t">New Lows</div><div class="v val-down">${b.new_low_20d != null ? b.new_low_20d : '--'} <span class="val-muted" style="font-size:10px">20d</span> · ${b.new_low_52w != null ? b.new_low_52w : '--'} <span class="val-muted" style="font-size:10px">52w</span></div></div>
           <div class="hl-box"><div class="t">Up &gt; 3%</div><div class="v val-up">${b.up_3 != null ? b.up_3 : '--'}</div></div>
           <div class="hl-box"><div class="t">Down &gt; 3%</div><div class="v val-down">${b.down_3 != null ? b.down_3 : '--'}</div></div>
         </div>`;
    applyGlossary(el);
  }

  // ── b1 Themes table ────────────────────────────────────────────────────────
  function statusClass(st) {
    const s = (st || '').toUpperCase();
    if (s.indexOf('DOMINANT') !== -1 || s.indexOf('STRONG') !== -1) return 'st-dom';
    if (s.indexOf('EMERG') !== -1 || s.indexOf('IMPROV') !== -1) return 'st-emg';
    if (s.indexOf('FAD') !== -1 || s.indexOf('DETERIOR') !== -1 || s.indexOf('WEAK') !== -1) return 'st-fad';
    return '';
  }
  async function loadThemes() {
    let data = null;
    try { const r = await apiFetch('/api/stable/themes'); if (r.ok) data = await r.json(); } catch (_) {}
    const el = $('themesTable'); if (!el) return;
    $('themesAsOf').textContent = data && data.date ? data.date : '';
    setDot('themesHealthDot', data && data.data_age_seconds, data ? data.degraded : true, data && data.flatline);
    noteFlatline('nightly', data && data.flatline, 'Themes');
    _health.themes = (!data || data.degraded) ? 'down' : 'ok'; updateGlobalHealth();
    const themes = (data && data.themes) || [];
    if (!themes.length) { el.innerHTML = '<div class="th-row"><span class="nm val-muted">no theme snapshot</span></div>'; return; }
    let html = '<div class="th-row head"><span class="rk">#</span><span class="nm">Theme</span><span class="sc">Score</span><span class="dl">1d Δ</span><span>Status</span></div>';
    themes.forEach((t) => {
      const d = t.score_1d_delta;
      html += `<div class="th-row" data-theme="${esc(t.theme)}">
        <span class="rk">${t.rank}</span>
        <span class="nm">${esc(t.theme)} <span class="val-muted" style="font-size:10px">${t.n_names || ''}</span></span>
        <span class="sc">${t.score != null ? Number(t.score).toFixed(0) : '--'}</span>
        <span class="dl ${signCls(d)}">${d != null ? (d >= 0 ? '+' : '') + Number(d).toFixed(1) : '·'}</span>
        <span class="status-chip ${statusClass(t.status)}">${esc(t.status || '')}</span></div>`;
    });
    el.innerHTML = html;
    el.querySelectorAll('.th-row[data-theme]').forEach((r) => r.addEventListener('click', () => openThemeMembers(r.dataset.theme)));
    applyGlossary(el);
  }

  async function openThemeMembers(theme) {
    openPopup('Theme · ' + theme, '<div class="mem-sec">loading…</div>');
    let data = null;
    try { const r = await apiFetch('/api/stable/theme/' + encodeURIComponent(theme) + '/members'); if (r.ok) data = await r.json(); } catch (_) {}
    if (!data) { $('memberBody').innerHTML = '<div class="mem-sec">unavailable</div>'; return; }
    const row = (m) => {
      const rs = m.rs_qqq_20d;
      return `<div class="mem-row">
        <span class="mtk" data-ticker="${esc(m.ticker)}">${esc(m.ticker)}</span>
        <span class="val-muted" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(m.name || m.subtheme || '')}</span>
        <span class="${signCls(m.ret_1d)}">${m.ret_1d != null ? (m.ret_1d >= 0 ? '+' : '') + (m.ret_1d * 100).toFixed(1) + '%' : '--'}</span>
        <span class="val-muted">${m.last_price != null ? '$' + Number(m.last_price).toFixed(2) : '--'}</span>
        <button class="opt-btn" data-ticker="${esc(m.ticker)}">opt</button></div>`;
    };
    const sec = (name, arr) => `<div class="mem-sec">${name} <span class="val-muted">· RS vs QQQ</span></div>` + ((arr || []).map(row).join('') || '<div class="mem-row"><span class="val-muted">none</span></div>');
    $('memberBody').innerHTML = sec('Top by 1d', data.top) + sec('Bottom by 1d', data.bottom);
    $('memberBody').querySelectorAll('.mtk[data-ticker]').forEach((e) => e.addEventListener('click', () => { closePopup(); openTvPopover(e.dataset.ticker, e); }));
    $('memberBody').querySelectorAll('.opt-btn[data-ticker]').forEach((e) => e.addEventListener('click', () => loadOptionsContext(e)));
  }

  // Options context — FOREGROUND UW read on explicit click only (never polled).
  async function loadOptionsContext(btn) {
    const tk = btn.dataset.ticker;
    const row = btn.closest('.mem-row');
    if (row.nextElementSibling && row.nextElementSibling.classList.contains('opt-ctx')) { row.nextElementSibling.remove(); return; }
    const ctx = document.createElement('div'); ctx.className = 'opt-ctx'; ctx.textContent = 'loading options context…';
    row.after(ctx);
    try {
      const r = await apiFetch('/api/committee/enrichment/' + encodeURIComponent(tk));
      if (!r.ok) { ctx.textContent = 'options context unavailable'; return; }
      const e = (await r.json()).enrichment || {};
      const iv = e.iv_rank || {}, tide = e.market_tide || {}, mp = e.max_pain || {};
      const parts = [];
      if (iv.iv_rank != null) parts.push('IV rank ' + Number(iv.iv_rank).toFixed(0));
      if (tide.net_call_premium != null && tide.net_put_premium != null)
        parts.push('tide ' + (Number(tide.net_call_premium) > Number(tide.net_put_premium) ? 'bullish' : 'bearish'));
      if (mp.max_pain_strike != null) parts.push('max-pain ' + mp.max_pain_strike + ' (' + mp.dte + 'dte)');
      ctx.textContent = parts.length ? tk + ' · ' + parts.join(' · ') : tk + ' · no options context cached';
    } catch (_) { ctx.textContent = 'options context error'; }
  }

  // ── Charts (Chart.js) ──────────────────────────────────────────────────────
  const SECTOR_RAMP = ['#14b8a6', '#7CFF6B', '#ff5c33', '#38bdf8', '#a78bfa', '#f472b6', '#2dd4bf', '#94a3b8', '#fb7185', '#4ade80', '#60a5fa'];
  const _charts = {};
  function makeLineChart(id, datasets, labels, opts) {
    if (typeof Chart === 'undefined') return;
    if (_charts[id]) { _charts[id].destroy(); }
    const ctx = document.getElementById(id); if (!ctx) return;
    _charts[id] = new Chart(ctx, {
      type: 'line',
      data: { labels, datasets },
      options: Object.assign({
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false }, tooltip: { enabled: true } },
        scales: {
          x: { ticks: { color: '#5b6b85', maxTicksLimit: 5, font: { size: 9 } }, grid: { color: 'rgba(27,39,69,0.4)' } },
          y: { ticks: { color: '#5b6b85', font: { size: 9 } }, grid: { color: 'rgba(27,39,69,0.4)' } },
        },
        elements: { point: { radius: 0 }, line: { borderWidth: 1.4, tension: 0.25 } },
      }, opts || {}),
    });
  }

  // ── b2 Sector divergence ────────────────────────────────────────────────────
  let _divWindow = '1d';
  async function loadDivergence() {
    let data = null;
    try { const r = await apiFetch('/api/stable/sector-divergence?window=' + _divWindow); if (r.ok) data = await r.json(); } catch (_) {}
    const legend = $('divLegend'); if (!legend) return;
    if (!data || !data.sectors || data.degraded) {
      legend.innerHTML = '<span class="legend-chip val-muted">divergence feed unavailable</span>';
      if (_charts.divChart) { _charts.divChart.destroy(); delete _charts.divChart; }
      return;
    }
    const sectors = data.sectors.filter((s) => s.series && s.series.length);
    let labels = [];
    sectors.forEach((s) => { if (s.series.length > labels.length) labels = s.series.map((p) => (p.ts ? p.ts.slice(11, 16) : (p.date || '').slice(5))); });
    const datasets = sectors.map((s, i) => ({
      label: s.symbol, borderColor: SECTOR_RAMP[i % SECTOR_RAMP.length], backgroundColor: 'transparent',
      data: s.series.map((p) => (p.value != null ? Number((_divWindow === '1d' ? p.value : p.value)).toFixed(3) : null)),
    }));
    makeLineChart('divChart', datasets, labels);
    legend.innerHTML = sectors.map((s, i) => {
      const dmaCls = s.above_50dma && s.above_200dma ? 'dma-up' : (s.above_50dma === false && s.above_200dma === false ? 'dma-down' : 'dma-mix');
      return `<span class="legend-chip"><span class="dot" style="background:${SECTOR_RAMP[i % SECTOR_RAMP.length]}"></span>${esc(s.symbol)}<span class="dma ${dmaCls}" data-gloss="DMA"></span></span>`;
    }).join('');
    applyGlossary(legend);
  }

  // ── b4 Index strip ──────────────────────────────────────────────────────────
  async function loadIndexStrip() {
    let data = null;
    try { const r = await apiFetch('/api/stable/index-strip'); if (r.ok) data = await r.json(); } catch (_) {}
    const el = $('indexStrip'); if (!el) return;
    setDot('indexHealthDot', data && data.data_age_seconds, data ? data.degraded : true, data && data.flatline);
    noteFlatline('strip', data && data.flatline, 'Index / strip');
    const order = ['SPY', 'QQQ', 'IWM', 'RSP', 'DIA'];
    const rows = (data && data.indices) || [];
    const map = {}; rows.forEach((r) => { map[r.symbol] = r; });
    el.innerHTML = order.map((sym) => {
      const r = map[sym]; const pct = r ? r.value : null; const ext = r ? r.atr_ext_50ma : null;
      return `<div class="ix-cell" data-ticker="${sym}"><span class="sym">${sym}</span>`
        + `<span class="chg ${signCls(pct)}">${pct != null ? (pct >= 0 ? '+' : '') + Number(pct).toFixed(2) + '%' : '--'}</span>`
        + `<span class="ext">${ext != null ? (ext >= 0 ? '+' : '') + Number(ext).toFixed(1) + ' ATR' : ''}</span></div>`;
    }).join('');
    el.querySelectorAll('.ix-cell[data-ticker]').forEach((c) => c.addEventListener('click', () => openTvPopover(c.dataset.ticker, c)));
  }

  // ── b5 Yield curve mini ─────────────────────────────────────────────────────
  async function loadRates() {
    let data = null;
    try { const r = await apiFetch('/api/stable/rates'); if (r.ok) data = await r.json(); } catch (_) {}
    const vals = $('curveVals'); if (!vals) return;
    if (!data || !data.curve_points) { vals.innerHTML = '<span class="val-muted">rates unavailable</span>'; return; }
    const order = ['3M', '5Y', '10Y', '30Y'];
    const cp = data.curve_points || {}, ghost = data.curve_points_5d_ago || null;
    const yieldsBySym = {}; (data.yields || []).forEach((y) => { yieldsBySym[y.symbol] = y; });
    const labels = order.filter((s) => cp[s] != null);
    const datasets = [{ label: 'now', borderColor: '#14b8a6', backgroundColor: 'transparent', data: labels.map((s) => cp[s]) }];
    if (ghost) datasets.push({ label: '5d ago', borderColor: 'rgba(139,152,173,0.5)', borderDash: [4, 3], backgroundColor: 'transparent', data: labels.map((s) => ghost[s] != null ? ghost[s] : null) });
    makeLineChart('curveChart', datasets, labels);
    vals.innerHTML = order.map((s) => {
      const y = yieldsBySym[s]; const v = cp[s]; const bp = y ? y.day_change : null;
      return `<span class="mv"><span class="k">${s}</span><span class="v">${v != null ? Number(v).toFixed(2) + '%' : '--'}</span>${bp != null ? `<span class="bp ${signCls(bp)}">${bp >= 0 ? '+' : ''}${Number(bp).toFixed(1)}bp</span>` : ''}</span>`;
    }).join('');
  }

  // ── b6 USD carry mini ───────────────────────────────────────────────────────
  function sparkPath(series, w, h) {
    if (!series || series.length < 2) return '';
    const vals = series.map((p) => Number(p.value)).filter((v) => Number.isFinite(v));
    if (vals.length < 2) return '';
    const min = Math.min(...vals), max = Math.max(...vals), rng = (max - min) || 1;
    const step = w / (vals.length - 1);
    return vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(h - ((v - min) / rng) * h).toFixed(1)}`).join(' ');
  }
  async function loadFx() {
    let data = null;
    try { const r = await apiFetch('/api/stable/fx'); if (r.ok) data = await r.json(); } catch (_) {}
    const el = $('fxWrap'); if (!el) return;
    const fx = (data && data.fx) || [];
    if (!fx.length) { el.innerHTML = '<span class="val-muted">FX unavailable</span>'; return; }
    el.innerHTML = fx.map((f) => {
      const chg = f.day_change_pct; const lvl = f.level;
      const path = sparkPath(f.series, 120, 24);
      const col = chg > 0 ? '#7CFF6B' : chg < 0 ? '#ff5c33' : '#8b98ad';
      return `<div class="fx-row"><span class="sym">${esc(f.symbol)}</span>`
        + `<span class="spark">${path ? `<svg width="100%" height="24" viewBox="0 0 120 24" preserveAspectRatio="none"><path d="${path}" fill="none" stroke="${col}" stroke-width="1.4"/></svg>` : ''}</span>`
        + `<span class="val">${lvl != null ? Number(lvl).toFixed(2) : '--'}</span>`
        + `<span class="chg ${signCls(chg)}">${chg != null ? (chg >= 0 ? '+' : '') + Number(chg).toFixed(2) + '%' : ''}</span></div>`;
    }).join('');
  }

  // ── b7 Book strip ───────────────────────────────────────────────────────────
  async function loadBook() {
    let balances = null, pnl = null, greeks = null, positions = null;
    try { const r = await apiFetch('/api/portfolio/balances'); if (r.ok) balances = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/portfolio/pnl'); if (r.ok) pnl = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/v2/positions/greeks'); if (r.ok) greeks = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/v2/positions?status=OPEN'); if (r.ok) positions = await r.json(); } catch (_) {}
    const el = $('bookStrip'); if (!el) return;
    const bookOk = !!(balances || pnl);
    setDot('bookHealthDot', bookOk ? 60 : null, !bookOk);
    _health.book = bookOk ? 'ok' : 'down'; updateGlobalHealth();

    const accts = Array.isArray(balances) ? balances : [];
    const total = accts.reduce((s, a) => s + (Number(a.balance) || 0), 0);
    const day = pnl && pnl.daily ? pnl.daily : {};
    const g = greeks && (greeks.totals || greeks.portfolio) ? (greeks.totals || {}) : {};
    const gv = (k1, k2) => { const v = (greeks && greeks.totals && greeks.totals[k1] != null) ? greeks.totals[k1] : (greeks && greeks.portfolio ? greeks.portfolio[k2] : null); return v; };
    const delta = gv('delta', 'net_delta'), theta = gv('theta', 'net_theta'), vega = gv('vega', 'net_vega'), gamma = gv('gamma', 'net_gamma');

    // Theme concentration: join open-position tickers -> theme, sum at-risk (current_value).
    const conc = computeConcentration(positions);

    el.innerHTML = `
      <div class="book-line"><span class="k">Balance</span><span class="v">${accts.length ? fmt$(total) : '--'}</span></div>
      <div class="book-line"><span class="k">Day P&amp;L</span><span class="v ${signCls(day.dollar)}">${day.dollar != null ? (day.dollar >= 0 ? '+' : '') + fmt$(day.dollar) : '--'}${day.pct != null ? ` <span style="font-size:10px">(${day.pct >= 0 ? '+' : ''}${Number(day.pct).toFixed(2)}%)</span>` : ''}</span></div>
      <div class="book-greeks">
        <span class="g"><span class="k">Δ</span><span>${delta != null ? Number(delta).toFixed(0) : '--'}</span></span>
        <span class="g"><span class="k">Γ</span><span>${gamma != null ? Number(gamma).toFixed(1) : '--'}</span></span>
        <span class="g"><span class="k">Θ</span><span>${theta != null ? Number(theta).toFixed(0) : '--'}</span></span>
        <span class="g"><span class="k">V</span><span>${vega != null ? Number(vega).toFixed(0) : '--'}</span></span>
      </div>
      ${conc ? `<div class="conc-lamp ${conc.hot ? 'hot' : 'ok'}" data-gloss="CONC"><span>Concentration · ${esc(conc.theme)}</span><span>${conc.pct}%</span></div>` : ''}
      <div class="acct-chips">${accts.map((a) => `<span class="acct-chip">${esc((a.broker || a.account_name || '').slice(0, 4).toUpperCase())} ${fmt$(a.balance)}</span>`).join('')}</div>`;
    applyGlossary(el);
    _openPositions = (positions && positions.positions) || [];
    renderPositions();
  }

  // ── c5: Book positions (same source as legacy Ledger: GET /api/v2/positions?status=OPEN) ──
  let _openPositions = [];
  const OPT_PUT = /put/i, OPT_CALL = /call/i;
  function structureStr(p) {
    if ((p.asset_type || '').toUpperCase() === 'EQUITY' || (p.structure || '') === 'stock') {
      return '×' + (p.quantity != null ? p.quantity : '') + ' sh';
    }
    const exp = p.expiry ? new Date(p.expiry + 'T00:00:00').toLocaleDateString('en-US', { month: '2-digit', day: '2-digit' }) : '';
    const strikes = [p.long_strike, p.short_strike].filter((x) => x != null).join('/');
    const type = OPT_PUT.test(p.structure || '') ? 'P' : OPT_CALL.test(p.structure || '') ? 'C' : '';
    const qty = p.quantity != null ? ' ×' + p.quantity : '';
    return `${exp} ${strikes}${type}${qty}`.trim();
  }
  function pnlPct(p) {
    const cb = Math.abs(Number(p.cost_basis) || 0);
    if (!cb || p.unrealized_pnl == null) return null;
    return (Number(p.unrealized_pnl) / cb) * 100;
  }
  function renderPositions() {
    const el = $('bookPositions'); if (!el) return;
    const list = _openPositions;
    if (!list.length) { el.innerHTML = '<div class="pos-empty">no open positions</div>'; return; }
    el.innerHTML = list.map((p, i) => {
      const pnl = p.unrealized_pnl != null ? Number(p.unrealized_pnl) : null;
      const pct = pnlPct(p);
      const dteCls = p.dte != null && p.dte <= 7 ? 'urgent' : p.dte != null && p.dte <= 14 ? 'soon' : '';
      const dteStr = p.dte != null ? p.dte + ' DTE' : (p.asset_type === 'EQUITY' ? 'equity' : '');
      return `<div class="pos-row" data-pi="${i}">
        <span class="ptk">${esc(p.ticker)}</span>
        <span class="pmid"><span class="pstruct">${esc(structureStr(p))}</span><span class="pdte ${dteCls}">${dteStr}</span></span>
        <span class="ppnl ${signCls(pnl)}"><span class="amt">${pnl != null ? (pnl >= 0 ? '+' : '-') + '$' + Math.abs(pnl).toFixed(0) : '--'}</span><span class="pct">${pct != null ? (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%' : ''}</span></span>
      </div>`;
    }).join('');
    el.querySelectorAll('.pos-row[data-pi]').forEach((r) => r.addEventListener('click', () => openPositionDrawer(_openPositions[+r.dataset.pi])));
  }

  async function openPositionDrawer(p) {
    if (!p) return;
    const title = $('drawerTitle'), body = $('drawerBody');
    title.textContent = p.ticker + ' · position';
    const kv = (k, v) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`;
    const pnl = p.unrealized_pnl != null ? Number(p.unrealized_pnl) : null; const pct = pnlPct(p);
    const tm = _themeMap[(p.ticker || '').toUpperCase()];
    body.innerHTML =
      kv('Structure', structureStr(p) + (p.structure ? '  (' + String(p.structure).replace(/_/g, ' ') + ')' : '')) +
      kv('Direction', p.direction || '—') + kv('Account', p.account || '—') +
      kv('Entry', p.entry_price != null ? p.entry_price : '—') + kv('Current', p.current_price != null ? p.current_price : '—') +
      kv('Stop', p.stop_loss != null ? p.stop_loss : '—') + kv('Target', p.target_1 != null ? p.target_1 : '—') +
      kv('Qty', p.quantity != null ? p.quantity : '—') + kv('DTE', p.dte != null ? p.dte : '—') +
      kv('Cost basis', p.cost_basis != null ? '$' + Number(p.cost_basis).toFixed(2) : '—') +
      kv('Max loss', p.max_loss != null ? '$' + Number(p.max_loss).toFixed(2) : '—') +
      `<div class="kv"><span class="k">Unrealized P&amp;L</span><span class="v ${signCls(pnl)}">${pnl != null ? (pnl >= 0 ? '+' : '-') + '$' + Math.abs(pnl).toFixed(2) : '—'}${pct != null ? ' (' + (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%)' : ''}</span></div>` +
      kv('Bucket', p.bucket || '—') + kv('Theme', tm && tm.theme ? (tm.theme + (tm.inverse ? ' (inverse)' : '')) : '—') +
      '<div id="posEarn" class="kv"><span class="k">Earnings</span><span class="v">…</span></div>' +
      `<div class="drawer-actions">
         <button type="button" class="btn-danger" id="posCloseBtn">Close position</button>
         <button type="button" class="btn-secondary" id="posChartBtn">Chart</button>
       </div>`;
    $('drawerBackdrop').classList.add('open'); $('drawer').classList.add('open');
    $('posCloseBtn').addEventListener('click', () => openCloseForm(p));
    $('posChartBtn').addEventListener('click', (e) => { closeDrawer(); openTvPopover(p.ticker, e.target); });
    // Earnings surface (CHRONOS) — single earnings source from P0
    try {
      const r = await apiFetch('/api/chronos/next-earnings-batch?tickers=' + encodeURIComponent(p.ticker));
      if (r.ok) {
        const e = (await r.json()).earnings || {}; const en = e[(p.ticker || '').toUpperCase()];
        const cell = $('posEarn');
        if (cell) cell.querySelector('.v').textContent = en && en.date ? en.date + (en.timing ? ' · ' + en.timing : '') : 'none scheduled';
      }
    } catch (_) {}
  }

  // ── c5: add / close via the EXISTING write endpoints (call, never modify) ──
  const STRUCTURES = ['stock', 'long_call', 'long_put', 'call_debit_spread', 'put_debit_spread', 'call_credit_spread', 'put_credit_spread'];
  function openModal(title, html) { $('modalTitle').textContent = title; $('modalBody').innerHTML = html; $('modalBackdrop').classList.add('open'); $('posModal').classList.add('open'); }
  function closeModal() { $('modalBackdrop').classList.remove('open'); $('posModal').classList.remove('open'); }

  function openAddForm() {
    const fld = (id, label, attrs) => `<div class="fld"><label for="${id}">${label}</label><input id="${id}" ${attrs || ''}></div>`;
    openModal('Add position', `
      <div class="form-grid">
        ${fld('f_ticker', 'Ticker', 'placeholder="AAPL" autocomplete="off"')}
        <div class="fld"><label for="f_account">Account</label><select id="f_account"><option>ROBINHOOD</option><option>FIDELITY</option></select></div>
        <div class="fld"><label for="f_structure">Structure</label><select id="f_structure">${STRUCTURES.map((s) => `<option value="${s}">${s.replace(/_/g, ' ')}</option>`).join('')}</select></div>
        ${fld('f_qty', 'Quantity', 'type="number" min="1" value="1"')}
        ${fld('f_entry', 'Entry price', 'type="number" step="any" placeholder="0.00"')}
        ${fld('f_expiry', 'Expiry', 'type="date"')}
        ${fld('f_long', 'Long strike', 'type="number" step="any"')}
        ${fld('f_short', 'Short strike', 'type="number" step="any"')}
        ${fld('f_stop', 'Stop', 'type="number" step="any"')}
        ${fld('f_target', 'Target', 'type="number" step="any"')}
        <div class="fld full">${'<label for="f_notes">Notes</label><input id="f_notes" placeholder="optional">'}</div>
      </div>
      <div class="form-actions"><button type="button" class="btn-primary" id="f_submit">Create</button><button type="button" class="btn-secondary" id="f_cancel">Cancel</button></div>
      <div class="form-msg" id="f_msg"></div>`);
    $('f_cancel').addEventListener('click', closeModal);
    $('f_submit').addEventListener('click', submitAdd);
  }
  async function submitAdd() {
    const val = (id) => { const e = $(id); return e && e.value !== '' ? e.value : null; };
    const num = (id) => { const v = val(id); return v == null ? null : Number(v); };
    const ticker = (val('f_ticker') || '').toUpperCase().trim();
    const structure = val('f_structure');
    if (!ticker) { $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'Ticker is required'; return; }
    const body = {
      ticker, asset_type: structure === 'stock' ? 'EQUITY' : 'OPTION', structure,
      entry_price: num('f_entry'), quantity: parseInt(val('f_qty'), 10) || 1, source: 'MANUAL', account: val('f_account'),
    };
    if (num('f_long') != null) body.long_strike = num('f_long');
    if (num('f_short') != null) body.short_strike = num('f_short');
    if (val('f_expiry')) body.expiry = val('f_expiry');
    if (num('f_stop') != null) body.stop_loss = num('f_stop');
    if (num('f_target') != null) body.target_1 = num('f_target');
    if (val('f_notes')) body.notes = val('f_notes');
    $('f_msg').className = 'form-msg'; $('f_msg').textContent = 'saving…';
    try {
      const r = await apiFetch('/api/v2/positions', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, body: JSON.stringify(body) });
      if (r.ok) { $('f_msg').className = 'form-msg ok'; $('f_msg').textContent = 'created'; setTimeout(() => { closeModal(); refreshDesk(); }, 500); }
      else if (r.status === 401) { $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'sign in to add positions'; showLogin(); }
      else { const d = await r.json().catch(() => ({})); $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'failed: ' + (d.detail || r.status); }
    } catch (_) { $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'network error'; }
  }

  function openCloseForm(p) {
    const mult = (p.asset_type || '').toUpperCase() === 'EQUITY' ? 1 : 100;
    openModal('Close ' + p.ticker, `
      <div class="form-grid">
        <div class="fld"><label>Position</label><input value="${esc(p.ticker + ' · ' + structureStr(p))}" disabled></div>
        <div class="fld"><label for="c_exit">Exit price</label><input id="c_exit" type="number" step="any" placeholder="${p.current_price != null ? p.current_price : '0.00'}"></div>
        <div class="fld"><label for="c_qty">Quantity</label><input id="c_qty" type="number" min="1" value="${p.quantity != null ? p.quantity : 1}"></div>
        <div class="fld"><label for="c_reason">Reason</label><select id="c_reason"><option value="manual">manual</option><option value="profit">profit</option><option value="loss">loss</option></select></div>
        <div class="fld full"><label for="c_notes">Notes</label><input id="c_notes" placeholder="optional"></div>
      </div>
      <div class="form-actions"><button type="button" class="btn-danger" id="c_submit">Close position</button><button type="button" class="btn-secondary" id="c_cancel">Cancel</button></div>
      <div class="form-msg" id="c_msg"></div>`);
    $('c_cancel').addEventListener('click', closeModal);
    $('c_submit').addEventListener('click', () => submitClose(p, mult));
  }
  async function submitClose(p, mult) {
    const exit = $('c_exit').value !== '' ? Number($('c_exit').value) : null;
    if (exit == null) { $('c_msg').className = 'form-msg err'; $('c_msg').textContent = 'Exit price required'; return; }
    const qty = parseInt($('c_qty').value, 10) || p.quantity || 1;
    const reason = $('c_reason').value;
    const pnl = p.unrealized_pnl != null ? Number(p.unrealized_pnl) : 0;
    const body = {
      exit_price: exit, quantity: qty, exit_value: exit * mult * qty,
      trade_outcome: pnl > 0 ? 'WIN' : pnl < 0 ? 'LOSS' : 'BREAKEVEN',
      close_reason: reason, notes: $('c_notes').value || null,
    };
    $('c_msg').className = 'form-msg'; $('c_msg').textContent = 'closing…';
    try {
      const r = await apiFetch('/api/v2/positions/' + encodeURIComponent(p.position_id) + '/close', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, body: JSON.stringify(body) });
      if (r.ok) { $('c_msg').className = 'form-msg ok'; $('c_msg').textContent = 'closed'; setTimeout(() => { closeModal(); closeDrawer(); refreshDesk(); }, 500); }
      else if (r.status === 401) { $('c_msg').className = 'form-msg err'; $('c_msg').textContent = 'sign in to close'; showLogin(); }
      else { const d = await r.json().catch(() => ({})); $('c_msg').className = 'form-msg err'; $('c_msg').textContent = 'failed: ' + (d.detail || r.status); }
    } catch (_) { $('c_msg').className = 'form-msg err'; $('c_msg').textContent = 'network error'; }
  }

  let _themeMap = {}; // ticker -> {theme, theme_score, theme_status}
  function computeConcentration(positions) {
    const list = (positions && positions.positions) || [];
    if (!list.length) return null;
    const byTheme = {}, invTheme = {}; let totalRisk = 0;
    list.forEach((p) => {
      const risk = Math.abs(Number(p.current_value != null ? p.current_value : (p.cost_basis != null ? p.cost_basis : p.max_loss)) || 0);
      if (!risk) return;
      const tm = _themeMap[(p.ticker || '').toUpperCase()];
      const theme = (tm && tm.theme) || 'Unmapped';
      byTheme[theme] = (byTheme[theme] || 0) + risk; totalRisk += risk;
      if (tm && tm.inverse) invTheme[theme] = (invTheme[theme] || 0) + risk;
    });
    if (!totalRisk) return null;
    let top = null;
    Object.keys(byTheme).forEach((t) => { if (!top || byTheme[t] > byTheme[top]) top = t; });
    const pct = Math.round((byTheme[top] / totalRisk) * 100);
    // Netting is deferred (post-flip): if the top theme is majority-inverse, say so rather
    // than imply long exposure. This is honest labeling, not direction-aware offsetting.
    const invHeavy = (invTheme[top] || 0) > byTheme[top] / 2;
    return { theme: top + (invHeavy ? ' (inverse)' : ''), pct, hot: pct > 50 && top !== 'Unmapped' };
  }
  async function refreshThemeMap(positions) {
    const list = (positions && positions.positions) || [];
    const tickers = [...new Set(list.map((p) => (p.ticker || '').toUpperCase()).filter(Boolean))];
    if (!tickers.length) { _themeMap = {}; return; }
    try {
      const r = await apiFetch('/api/stable/enrich?tickers=' + tickers.join(','));
      if (r.ok) { const d = await r.json(); _themeMap = d.enrichment || {}; }
    } catch (_) {}
  }

  // ── b8 Kairos module ────────────────────────────────────────────────────────
  function gradeFromScore(s) { return s == null ? '·' : s >= 80 ? 'A' : s >= 65 ? 'B' : s >= 50 ? 'C' : 'D'; }
  // Decision-clock TTL: minutes remaining until a setup's expiry, or null if it carries no TTL.
  function ttlMinutes(s) {
    const raw = s.expires_at || s.decision_deadline || s.ttl_at;
    if (!raw) return null;
    const t = Date.parse(String(raw).replace('Z', '+00:00').replace(/([+-]\d{2}:\d{2})?$/, (m) => m || '+00:00'));
    if (isNaN(t)) return null;
    return Math.round((t - Date.now()) / 60000);
  }
  function ttlLabel(m) {
    if (m <= 0) return 'expiring';
    if (m < 60) return m + 'm';
    const h = Math.floor(m / 60); return h + 'h' + (m % 60 ? ' ' + (m % 60) + 'm' : '');
  }
  async function loadKairos() {
    let data = null;
    try { const r = await apiFetch('/api/trade-ideas?status=ACTIVE&limit=30'); if (r.ok) data = await r.json(); } catch (_) {}
    const el = $('kairosCards'); if (!el) return;
    let signals = (data && data.signals) || [];
    // enrich theme for signal tickers (reuses the stable enrich read)
    const tickers = [...new Set(signals.map((s) => (s.ticker || '').toUpperCase()).filter(Boolean))];
    let smap = {};
    if (tickers.length) { try { const r = await apiFetch('/api/stable/enrich?tickers=' + tickers.join(',')); if (r.ok) smap = (await r.json()).enrichment || {}; } catch (_) {} }
    const scoreOf = (s) => (s.adjusted_score != null ? s.adjusted_score : s.score_v2 != null ? s.score_v2 : s.score);
    signals.sort((a, b) => (scoreOf(b) || 0) - (scoreOf(a) || 0));
    // L-evidence: fetch Pythia value-area levels for the visible tickers only (cheap DB reads).
    const visTickers = [...new Set(signals.slice(0, 3).map((s) => (s.ticker || '').toUpperCase()).filter(Boolean))];
    const levelMap = {};
    await Promise.all(visTickers.map(async (tk) => {
      try { const r = await apiFetch('/api/board/levels/' + encodeURIComponent(tk)); if (r.ok) levelMap[tk] = await r.json(); } catch (_) {}
    }));
    const bias = _lastRegime.composite ? (_lastRegime.composite.bias_level || '') : '';
    const biasBull = /TORO|BULL/.test(bias), biasBear = /URSA|BEAR/.test(bias);
    if (!signals.length) { el.innerHTML = '<div class="k-card"><span class="val-muted">no active setups</span></div>'; $('kairosQueued').textContent = ''; return; }
    const visible = signals.slice(0, 3), queued = signals.length - visible.length;
    $('kairosQueued').textContent = queued > 0 ? '+' + queued + ' queued' : '';
    el.innerHTML = visible.map((s) => card(s, smap, biasBull, biasBear, levelMap)).join('');
    applyGlossary(el);
    el.querySelectorAll('.btn-committee[data-ticker]').forEach((b) => b.addEventListener('click', () => {
      const card = b.closest('.k-card'); if (card) card.classList.add('acked');  // acknowledge -> stop the decision-clock pulse
      openCommittee(b.dataset.ticker, b.dataset.sig);
    }));
    el.querySelectorAll('.k-card .tkr[data-ticker]').forEach((t) => t.addEventListener('click', () => openTvPopover(t.dataset.ticker, t)));
    // feed the river with the top signals
    addRiverItems(signals.slice(0, 8).map((s) => signalRiverItem(s, smap)));
    renderRiver();

    function card(s, smap, bull, bear, levelMap) {
      const disp = setupDisplay(s.codename || s.signal_type || s.strategy);
      const sc = scoreOf(s); const grade = gradeFromScore(sc);
      const ttl = ttlMinutes(s);
      const side = (s.direction || '').toUpperCase();
      const sideCls = side === 'LONG' ? 'side-long' : side === 'SHORT' ? 'side-short' : '';
      const tm = smap[(s.ticker || '').toUpperCase()];
      const themeTag = tm && tm.theme ? `${esc(tm.theme)}${tm.theme_score != null ? ' ' + Math.round(tm.theme_score) : ''}${tm.theme_status ? ' ' + String(tm.theme_status).slice(0, 3).toLowerCase() : ''}` : '';
      // Evidence (honest: gray-off when unknown, never a fake check)
      const rOk = (side === 'LONG' && bull) || (side === 'SHORT' && bear);
      const rWarn = (side === 'LONG' && bear) || (side === 'SHORT' && bull);
      const rCls = rOk ? 'ev-ok' : rWarn ? 'ev-warn' : 'ev-off';
      const ed = s.enrichment_data || {};
      const fCls = ed.flow || ed.market_structure ? 'ev-ok' : 'ev-off';
      // L evidence: price sitting on a Pythia value-area level (VAH/VAL/POC). Gray when no MP data.
      let lCls = 'ev-off', lChar = '·';
      const lv = levelMap && levelMap[(s.ticker || '').toUpperCase()];
      if (lv && lv.available && lv.levels) {
        const px = s.entry_price != null ? Number(s.entry_price) : lv.levels.price_at_event;
        const cands = [lv.levels.vah, lv.levels.val, lv.levels.poc].filter((x) => x != null).map(Number);
        if (px && cands.length) {
          const nearest = Math.min(...cands.map((x) => Math.abs(px - x)));
          if (nearest / px < 0.004) { lCls = 'ev-ok'; lChar = '✓'; }
        }
      }
      const shadow = disp.shadow;
      const gradeShown = shadow ? '—' : grade;
      return `<div class="k-card${shadow ? ' shadow' : ''}">
        <div class="top"><span class="nm">${esc(disp.name)}</span><span class="desc">${esc(disp.desc)}</span>
          <span class="grade ${gradeShown === 'A' ? 'val-up' : ''}">${gradeShown}</span></div>
        <div class="lvls"><span class="tkr" data-ticker="${esc(s.ticker)}">${esc(s.ticker)}</span>
          <span class="${sideCls}">${side || ''} ${s.entry_price != null ? Number(s.entry_price).toFixed(2) : ''}</span>
          ${s.target_1 != null ? `<span>T ${Number(s.target_1).toFixed(2)}</span>` : ''}
          ${s.stop_loss != null ? `<span>S ${Number(s.stop_loss).toFixed(2)}</span>` : ''}
          ${s.timeframe ? `<span class="val-muted">${esc(s.timeframe)}</span>` : ''}</div>
        <div class="k-evidence"><span class="${rCls}" data-gloss="R">R${rOk ? '✓' : rWarn ? '⚠' : '·'}</span>
          <span class="${fCls}" data-gloss="F">F${fCls === 'ev-ok' ? '✓' : '·'}</span>
          <span class="${lCls}" data-gloss="L">L${lChar}</span><span class="ev-off" data-gloss="C">C·</span></div>
        <div class="foot">${themeTag ? `<span class="k-theme">${themeTag}</span>` : ''}${shadow ? '<span class="shadow-tag">shadow</span>' : (ttl != null ? `<span class="clock-chip pulse-teal" data-gloss="CLOCK">⏱ ${ttlLabel(ttl)}</span>` : '')}
          <button class="btn-committee" data-ticker="${esc(s.ticker)}" data-sig="${esc(s.signal_id || '')}">Committee</button></div>
      </div>`;
    }
  }
  function openCommittee(ticker, sig) {
    openDrawer('committee', { ticker, sig });
  }

  // ── b9 River ────────────────────────────────────────────────────────────────
  const _river = new Map();  // id -> item
  const _rvAcked = new Set(); // acknowledged action-item ids (pulse stops)
  let _riverFilter = 'all';
  function addRiverItems(items) { (items || []).forEach((it) => { if (it && it.id) _river.set(it.id, it); }); }
  function signalRiverItem(s, smap) {
    const disp = setupDisplay(s.codename || s.signal_type || s.strategy);
    const sc = s.adjusted_score != null ? s.adjusted_score : s.score_v2 != null ? s.score_v2 : s.score;
    const shadow = disp.shadow;
    const side = (s.direction || '').toUpperCase();
    return {
      id: 'sig:' + (s.signal_id || s.ticker + s.timestamp), type: 'signal',
      tier: shadow ? 'shadow' : (sc >= 65 ? 'action' : 'info'),
      sev: side === 'LONG' ? 'up' : side === 'SHORT' ? 'down' : 'teal',
      ts: s.timestamp ? Date.parse(s.timestamp) : (s.created_at ? Date.parse(s.created_at) : Date.now()),
      text: `<b>${esc(disp.name)}</b> ${esc(s.ticker)} ${side}${s.entry_price != null ? ' @ ' + Number(s.entry_price).toFixed(2) : ''}${sc != null ? ' · grade ' + gradeFromScore(sc) : ''}`,
    };
  }
  function emitRegimeRiverItems(composite, regime, kill) {
    // stable-vs-composite divergence
    if (composite && regime) {
      const c100 = to100(composite.composite_score);
      const rl = regime.regime_label;
      const cDir = c100 == null ? 0 : c100 >= 55 ? 1 : c100 <= 45 ? -1 : 0;
      const sDir = rl === 'RISK-ON' ? 1 : rl === 'RISK-OFF' ? -1 : 0;
      if (cDir && sDir && cDir !== sDir) {
        addRiverItems([{ id: 'div:' + rl + ':' + cDir, type: 'regime', tier: 'action', sev: 'teal', ts: Date.now(),
          text: `<b>Lens divergence</b> — Composite ${c100}/100 vs Stable ${esc(rl)}. Size with caution.` }]);
      }
    }
    const k = kill && kill.kill_switch;
    if (k && k.active) {
      addRiverItems([{ id: 'kill:' + (k.trigger || '') + ':' + (k.triggered_at || ''), type: 'regime', tier: 'action', sev: 'down', ts: k.triggered_at ? Date.parse(k.triggered_at) : Date.now(),
        text: `<b>Kill-switch ARMED</b> — ${esc(k.trigger || 'risk-off')}${k.description ? ' · ' + esc(k.description) : ''}` }]);
    }
    renderRiver();
  }
  async function loadDeskStreams() {
    // flow radar (position flow + headlines) + hermes catalysts
    let flow = null, hermes = null;
    try { const r = await apiFetch('/api/flow/radar'); if (r.ok) flow = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/hermes/alerts?limit=12'); if (r.ok) hermes = await r.json(); } catch (_) {}
    const items = [];
    if (flow) {
      (flow.position_flow || []).slice(0, 8).forEach((f, i) => {
        const align = (f.alignment || '').toUpperCase();
        if (align === 'NEUTRAL' || !align) return;
        items.push({ id: 'flow:' + (f.ticker || i) + ':' + align, type: 'flow',
          tier: f.strength === 'STRONG' ? 'action' : 'info', sev: align === 'CONFIRMING' ? 'up' : 'down', ts: Date.now(),
          text: `<b>${esc(f.ticker || '')}</b> flow ${align.toLowerCase()}${f.strength ? ' (' + esc(f.strength.toLowerCase()) + ')' : ''} vs your position` });
      });
      (flow.watchlist_unusual || []).slice(0, 5).forEach((w, i) => {
        items.push({ id: 'unusual:' + (w.ticker || i), type: 'flow', tier: 'info', sev: 'teal', ts: Date.now(),
          text: `Unusual flow · <b>${esc(w.ticker || '')}</b>${w.sentiment ? ' ' + esc(w.sentiment) : ''}` });
      });
      (flow.headlines || []).slice(0, 6).forEach((h, i) => {
        const hl = h.headline || h.title || ''; if (!hl) return;
        items.push({ id: 'hl:' + hl.slice(0, 40), type: 'headline', tier: 'info', sev: null,
          ts: h.created_at ? Date.parse(h.created_at) : Date.now(), text: esc(hl) });
      });
    }
    if (hermes) {
      (hermes.alerts || []).forEach((a) => {
        items.push({ id: 'herm:' + (a.id || a.trigger_ticker), type: 'catalyst',
          tier: (a.tier <= 1 ? 'action' : 'info'), sev: 'down', ts: a.created_at ? Date.parse(a.created_at) : Date.now(),
          text: `<b>${esc(a.trigger_ticker || '')}</b> ${esc(a.headline_summary || a.event_type || 'catalyst')}` });
      });
    }
    // Cowork stable digest (optional — render only if present)
    try {
      const r = await _rawFetch('/stable_digest.md', { cache: 'no-store' });
      if (r.ok) {
        const txt = (await r.text()).trim();
        if (txt && txt[0] !== '<') items.push({ id: 'stable:digest', type: 'stable', tier: 'info', sev: 'teal', ts: Date.now(), text: '<b>Stable digest</b> · ' + esc(txt.split('\n')[0].slice(0, 160)) });
      }
    } catch (_) {}
    addRiverItems(items);
    renderRiver();
  }
  function renderRiver() {
    const el = $('riverStream'); if (!el) return;
    let items = [..._river.values()];
    if (_riverFilter !== 'all') items = items.filter((i) => i.type === _riverFilter);
    items.sort((a, b) => (b.ts || 0) - (a.ts || 0));
    items = items.slice(0, 60);
    // pills
    const types = ['all', 'signal', 'flow', 'catalyst', 'regime', 'headline'];
    $('riverPills').innerHTML = types.map((t) => `<button type="button" data-rt="${t}" class="${_riverFilter === t ? 'on' : ''}">${t}</button>`).join('');
    $('riverPills').querySelectorAll('button[data-rt]').forEach((b) => b.addEventListener('click', () => { _riverFilter = b.dataset.rt; renderRiver(); }));
    if (!items.length) { el.innerHTML = '<div class="rv-item info"><span class="rv-txt val-muted">stream quiet</span></div>'; return; }
    el.innerHTML = items.map((it) => {
      const t = new Date(it.ts || Date.now());
      const hh = isNaN(t) ? '' : t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const acked = _rvAcked.has(it.id);
      const pulse = acked ? '' : (it.sev === 'down' ? ' pulse-vermilion' : it.sev === 'up' ? ' pulse-lime' : ' pulse-teal');
      const cls = it.tier === 'action' ? 'action sev-' + (it.sev === 'up' ? 'up' : it.sev === 'down' ? 'down' : 'teal') + pulse + (acked ? ' acked' : '') : it.tier;
      return `<div class="rv-item ${cls}" data-rid="${esc(it.id)}"><div class="rv-head"><span class="rv-dot t-${it.type}"></span><span class="rv-type">${it.type}</span><span class="rv-time">${hh}</span></div><div class="rv-txt">${it.text}</div></div>`;
    }).join('');
    // Click an action item to acknowledge — stops its pulse (nothing pulses forever).
    el.querySelectorAll('.rv-item.action[data-rid]').forEach((n) => n.addEventListener('click', () => { _rvAcked.add(n.dataset.rid); renderRiver(); }));
  }

  // ── Popup helpers ───────────────────────────────────────────────────────────
  function openPopup(title, html) { $('memberTitle').textContent = title; $('memberBody').innerHTML = html; $('popupBackdrop').classList.add('open'); $('memberPopup').classList.add('open'); }
  function closePopup() { $('popupBackdrop').classList.remove('open'); $('memberPopup').classList.remove('open'); }

  // ── Polling groups (idle interval budget: 4 << 10) ──────────────────────────
  function refreshMarket() { loadThemes(); loadDivergence(); loadIndexStrip(); loadRates(); loadFx(); }
  async function refreshDesk() {
    let positions = null;
    try { const r = await apiFetch('/api/v2/positions?status=OPEN'); if (r.ok) positions = await r.json(); } catch (_) {}
    await refreshThemeMap(positions);
    loadBook(); loadKairos(); loadDeskStreams();
  }

  // ── Boot ────────────────────────────────────────────────────────────────────
  function boot() {
    applyGlossary(document);
    initGrid();
    loadRegimeBand(); managedInterval(loadRegimeBand, 60 * 1000);
    loadMoversTape(); managedInterval(loadMoversTape, 5 * 60 * 1000);
    refreshMarket(); managedInterval(refreshMarket, 10 * 60 * 1000);
    refreshDesk(); managedInterval(refreshDesk, 2 * 60 * 1000);
    // divergence window toggle
    const dt = $('divToggle');
    if (dt) dt.querySelectorAll('button[data-w]').forEach((b) => b.addEventListener('click', () => {
      _divWindow = b.dataset.w; dt.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b)); loadDivergence();
    }));
    $('drawerClose').addEventListener('click', closeDrawer);
    $('drawerBackdrop').addEventListener('click', closeDrawer);
    $('tvPopClose').addEventListener('click', closeTvPopover);
    $('memberClose').addEventListener('click', closePopup);
    $('popupBackdrop').addEventListener('click', closePopup);
    $('bookAdd').addEventListener('click', openAddForm);
    $('modalClose').addEventListener('click', closeModal);
    $('modalBackdrop').addEventListener('click', closeModal);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeDrawer(); closeTvPopover(); closePopup(); closeModal(); } });
    try { window.__mgd = _managed.size; } catch (_) {}  // idle interval count (acceptance check)
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
