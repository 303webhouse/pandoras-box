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
    REGIME: 'Composite bias regime and score',
    COMPOSITE: 'Composite bias score (weighted factor blend)',
    DOM: 'Dominant theme — score >= 75',
    EMG: 'Emerging / improving theme',
    FAD: 'Fading / deteriorating theme',
    TIDE: 'Market tide — net options-flow direction (wired in B2b)',
    HL: 'New 20-day / 52-week highs across the scored universe',
    BREADTH50: 'Percent of the scored universe above its 50-day moving average',
    KILL: 'Kill-switch / circuit-breaker state (wired in B2b)',
    R: 'Regime alignment', F: 'Flow confirmation',
    L: 'At a Pythia level (VAH/VAL/POC)', C: 'Crowding — consensus positioning, size down',
    VAH: 'Value-area high', VAL: 'Value-area low', POC: 'Point of control',
  };
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
  function setHealth(el, ageSec, degraded) {
    if (!el) return;
    let cls = 'health-dot', txt = 'fresh';
    if (degraded || ageSec == null) { cls += ' down'; txt = 'unknown / degraded'; }
    else if (ageSec > 900) { cls += ' stale'; txt = 'stale ' + ageLabel(ageSec); }
    else { cls += ' ok'; txt = 'fresh ' + ageLabel(ageSec); }
    el.className = cls;
    el.setAttribute('title', txt);
  }

  const _health = { regime: null, movers: null };
  function updateGlobalHealth() {
    const vals = Object.values(_health).filter((v) => v !== null);
    const worst = vals.includes('down') ? 'down' : vals.includes('stale') ? 'stale' : vals.length ? 'ok' : '';
    const dot = $('dataHealthDot');
    dot.className = 'health-dot' + (worst ? ' ' + worst : '');
    dot.setAttribute('title', GLOSSARY.HEALTH + ' — ' + (worst || 'no data'));
  }

  // ── Regime band ─────────────────────────────────────────────────────────────
  async function loadRegimeBand() {
    let composite = null, regime = null;
    try { const r = await apiFetch('/api/bias/composite'); if (r.ok) composite = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/stable/regime'); if (r.ok) regime = await r.json(); } catch (_) {}
    renderRegimeBand(composite, regime);

    const age = regime && regime.data_age_seconds != null ? regime.data_age_seconds : null;
    const degraded = regime ? regime.degraded : true;
    _health.regime = (degraded || age == null) ? 'down' : age > 900 ? 'stale' : 'ok';
    updateGlobalHealth();
  }

  function themeChips(list, cls, limit) {
    if (!list || !list.length) return '<span class="chip muted">none</span>';
    return list.slice(0, limit || 3).map((t) =>
      `<span class="chip ${cls}">${esc(t.theme)} <b>${t.score != null ? Math.round(t.score) : ''}</b></span>`).join(' ');
  }

  function renderRegimeBand(composite, regime) {
    const band = $('regimeBand');
    const bias = composite ? (composite.bias_level || composite.level || 'UNKNOWN') : 'UNKNOWN';
    const score = composite && composite.composite_score != null ? Number(composite.composite_score).toFixed(2) : '--';
    const conf = composite ? (composite.confidence || '') : '';
    const biasCls = bias.includes('TORO') || bias.includes('BULL') ? 'val-up' : bias.includes('URSA') || bias.includes('BEAR') ? 'val-down' : 'val-teal';

    const breadth = (regime && regime.breadth) || {};
    const regimeLabel = regime ? (regime.regime_label || 'UNKNOWN') : 'UNKNOWN';
    const p50 = breadth.pct_above_50dma;

    band.innerHTML = `
      <div class="regime-cell" data-drawer="regime">
        <span class="label" data-gloss="REGIME">Regime · Composite</span>
        <div class="big ${biasCls}">${esc(bias.replace(/_/g, ' '))}</div>
        <div class="sub">stable: ${esc(regimeLabel)} · score <span class="num">${score}</span>${conf ? ' · ' + esc(conf) : ''}</div>
      </div>
      <div class="regime-cell" data-drawer="themes">
        <span class="label">Dominant · Emerging · Fading</span>
        <div class="row">${themeChips(regime && regime.dominant, 'dom', 2)} ${themeChips(regime && regime.emerging, 'emg', 2)} ${themeChips(regime && regime.fading, 'fad', 2)}</div>
      </div>
      <div class="regime-cell">
        <span class="label" data-gloss="TIDE">Tide</span>
        <div class="big val-muted">—</div>
        <div class="sub">flow tide · B2b</div>
      </div>
      <div class="regime-cell" data-drawer="breadth">
        <span class="label" data-gloss="HL">New Highs</span>
        <div class="row"><span class="big num">${breadth.new_high_20d != null ? breadth.new_high_20d : '--'}</span></div>
        <div class="sub">20d · 52w <span class="num">${breadth.new_high_52w != null ? breadth.new_high_52w : '--'}</span> · ±3% <span class="val-up num">${breadth.up_3 != null ? breadth.up_3 : '--'}</span>/<span class="val-down num">${breadth.down_3 != null ? breadth.down_3 : '--'}</span></div>
      </div>
      <div class="regime-cell" data-drawer="breadth">
        <span class="label" data-gloss="BREADTH50">% &gt; 50DMA</span>
        <div class="big num ${p50 != null && p50 >= 60 ? 'val-up' : p50 != null && p50 <= 40 ? 'val-down' : 'val-teal'}">${p50 != null ? p50.toFixed(0) + '%' : '--'}</div>
        <div class="gauge"><span style="width:${p50 != null ? Math.max(0, Math.min(100, p50)) : 0}%"></span></div>
      </div>
      <div class="regime-cell">
        <span class="label" data-gloss="KILL">Kill-switch</span>
        <div class="big val-muted">—</div>
        <div class="sub">circuit breaker · B2b</div>
      </div>`;
    applyGlossary(band);
    band.querySelectorAll('[data-drawer]').forEach((c) => c.addEventListener('click', () => openDrawer(c.dataset.drawer, { composite, regime })));
  }

  // ── Movers tape ──────────────────────────────────────────────────────────────
  async function loadMoversTape() {
    let data = null;
    try { const r = await apiFetch('/api/stable/movers'); if (r.ok) data = await r.json(); } catch (_) {}
    renderMoversTape(data);
    const age = data && data.data_age_seconds != null ? data.data_age_seconds : null;
    const degraded = data ? data.degraded : true;
    setHealth($('moversHealthDot'), age, degraded);
    $('moversAge').textContent = degraded ? 'stale ' + ageLabel(age) : ageLabel(age) + ' old';
    _health.movers = (degraded || age == null) ? 'down' : age > 900 ? 'stale' : 'ok';
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
    } else {
      title.textContent = 'Regime detail';
      const c = ctx.composite || {}, r = ctx.regime || {};
      body.innerHTML = kv('Composite bias', c.bias_level || c.level || '—') + kv('Composite score', c.composite_score != null ? c.composite_score : '—') +
        kv('Confidence', c.confidence || '—') + kv('Stable regime', r.regime_label || '—') + kv('% > 50DMA', (r.breadth || {}).pct_above_50dma) +
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

  // ── Boot ────────────────────────────────────────────────────────────────────
  function boot() {
    applyGlossary(document);
    initGrid();
    loadRegimeBand(); managedInterval(loadRegimeBand, 60 * 1000);
    loadMoversTape(); managedInterval(loadMoversTape, 5 * 60 * 1000);
    $('drawerClose').addEventListener('click', closeDrawer);
    $('drawerBackdrop').addEventListener('click', closeDrawer);
    $('tvPopClose').addEventListener('click', closeTvPopover);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeDrawer(); closeTvPopover(); } });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
