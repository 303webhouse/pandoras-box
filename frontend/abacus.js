/* Abacus (v2) — R-IV.429. Renders /api/abacus/summary into the build-from mockup's layout.
   Honest-seam rules this page keeps:
   - A block whose source is "mock" never wears a fresh chip; the page banner stays up while
     any block is mock.
   - Unknown renders as an em dash, never 0.
   - Every rate carries its n.
   - A 401 asks for sign-in; it never renders as empty panels. */
(function () {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const MINUS = '−';

  // ── Fetch with a sign-in gate (the v2 apiFetch contract) ────────────────────
  async function apiFetch(url) {
    const r = await fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    if (r.status === 401) showLogin();
    return r;
  }
  function showLogin() {
    const box = $('abLogin');
    if (!box || !box.hidden) return;
    box.hidden = false;
    $('abPw').focus();
    $('abLoginForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      $('abLoginErr').textContent = '';
      try {
        const r = await fetch('/api/auth/login', {
          method: 'POST', credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: JSON.stringify({ password: $('abPw').value }),
        });
        if (r.ok) location.reload();
        else $('abLoginErr').textContent = r.status === 401 ? 'Invalid password' : 'Login unavailable';
      } catch (_) { $('abLoginErr').textContent = 'Network error'; }
    });
  }

  // ── Formatting ───────────────────────────────────────────────────────────────
  const int = (v) => Math.round(Math.abs(v)).toLocaleString('en-US');
  function fmt(v, format) {
    if (v == null || (typeof v === 'number' && !Number.isFinite(v))) return '—';
    switch (format) {
      case 'usd': return (v > 0 ? '+' : v < 0 ? MINUS : '') + '$' + int(v);
      case 'usd_cents': return (v > 0 ? '+' : v < 0 ? MINUS : '') + '$' + Math.abs(v).toFixed(2);
      case 'usd_plain': return (v < 0 ? MINUS : '') + '$' + int(v);
      case 'usd_pair': return Array.isArray(v) ? fmt(v[0], 'usd_plain') + ' / ' + fmt(v[1], 'usd_plain') : '—';
      case 'pct': return Math.round(v * 100) + '%';
      case 'ratio': return Number(v).toFixed(1);
      case 'int': return String(v);
      default: return String(v);
    }
  }
  function tone(v, format) {
    if (typeof v !== 'number' || !Number.isFinite(v)) return '';
    if (format !== 'usd' && format !== 'usd_cents') return '';
    return v > 0 ? 'ab-up' : v < 0 ? 'ab-down' : '';
  }
  // An ISO calendar date ("2026-08-03") as "Aug 3". Read in UTC so the day never shifts.
  const shortDate = (iso) => {
    const t = Date.parse(String(iso || '') + 'T00:00:00Z');
    return Number.isFinite(t) ? new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' }).format(new Date(t)) : '';
  };
  const SUMMARY_VERSION = 1;
  const chip = (state, label, title) => `<span class="ab-chip" data-state="${esc(state)}"${title ? ` title="${esc(title)}"` : ''}>${esc(label)}</span>`;
  // R-IV.484(c) — the census beside a live stat: how many closed/expired positions in the
  // window were counted, and why the rest were not (basis-incomplete, return past -100% of
  // basis, or a realized_pnl the book never recorded). Those rows are never averaged in
  // silently, so the chip is how the reader sees that they existed.
  function coverageChip(cov) {
    if (!cov) return '';
    const ex = cov.excluded || {};
    const flagged = (ex.basis_incomplete || 0) + (ex.return_below_neg100pct || 0) + (ex.no_realized_pnl || 0);
    if (!cov.total) return ' ' + chip('unknown', 'no closed positions in range');
    if (!flagged) return ' ' + chip('fresh', 'n=' + cov.counted + ' of ' + cov.total);
    const parts = [];
    if (ex.basis_incomplete) parts.push(ex.basis_incomplete + ' basis incomplete');
    if (ex.return_below_neg100pct) parts.push(ex.return_below_neg100pct + ' return past -100% of basis');
    if (ex.no_realized_pnl) parts.push(ex.no_realized_pnl + ' never recorded a result');
    return ' ' + chip('stale', 'n=' + cov.counted + ' of ' + cov.total,
      flagged + ' excluded, never averaged in: ' + parts.join(', '));
  }
  const isMock = (block) => !block || block.source !== 'live';
  // A block's own chip: mock is "unknown", never fresh. Live shows when it was computed (MT).
  const mtTime = (iso) => new Intl.DateTimeFormat('en-US', { timeZone: 'America/Denver', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(iso)) + ' MT';
  function blockChip(block, liveLabel) {
    if (isMock(block)) return chip('unknown', 'mock');
    return chip('fresh', block.computed_at ? (liveLabel || 'computed') + ' ' + mtTime(block.computed_at) : (liveLabel || 'live'));
  }

  // ── Range control ────────────────────────────────────────────────────────────
  const state = { range: '90d', from: null, to: null };
  function summaryUrl() {
    const q = new URLSearchParams();
    if (state.from && state.to) { q.set('from', state.from); q.set('to', state.to); }
    else q.set('range', state.range);
    return '/api/abacus/summary?' + q.toString();
  }
  function paintRange(r) {
    document.querySelectorAll('#abRange button').forEach((b) =>
      b.setAttribute('aria-pressed', String(!!r && r.key === b.dataset.range)));
    if (r) { $('abFrom').value = r.from || ''; $('abTo').value = r.to || ''; }
  }
  function wireRange() {
    document.querySelectorAll('#abRange button').forEach((b) => b.addEventListener('click', () => {
      state.range = b.dataset.range; state.from = null; state.to = null;
      load();
    }));
    const onDate = () => {
      const f = $('abFrom').value, t = $('abTo').value;
      if (f && t) { state.from = f; state.to = t; load(); }
    };
    $('abFrom').addEventListener('change', onDate);
    $('abTo').addEventListener('change', onDate);
  }

  // ── Renderers ────────────────────────────────────────────────────────────────
  function renderHead(d) {
    const s = d.scope || {};
    const n = s.closed_positions != null ? s.closed_positions + ' closed positions in range' : 'closed positions: —';
    $('abAsof').innerHTML = `<span>${esc(s.label || '—')} · ${esc(n)}</span> ${blockChip(s)}`;
  }
  function allBlocks(d) {
    return [d.scope, d.equity, d.leaks, d.strategies].concat(d.stats || [], d.breakdowns || []).filter(Boolean);
  }
  function renderBanner(d) {
    const blocks = allBlocks(d);
    const mockCount = blocks.filter(isMock).length;
    const b = $('abBanner');
    if (!d.mock && !mockCount) { b.hidden = true; return; }
    b.hidden = false;
    b.textContent = 'Mock data — layout and behaviour only. Each metric loses this banner as its source goes live.'
      + (mockCount ? ' ' + mockCount + ' of ' + blocks.length + ' blocks are still mock.' : '')
      + (d.range_applied === false ? ' The range control is wired, but the figures do not change with it yet.' : '');
  }
  function renderStats(d) {
    $('abStats').innerHTML = (d.stats || []).map((s) => {
      const q = s.qualifier ? ' ' + chip(s.qualifier.state, s.qualifier.label) : '';
      const nTxt = (s.n != null ? ' · n=' + s.n : '') + (s.date ? ' · trough ' + shortDate(s.date) : '');
      return `<div class="ab-stat" data-key="${esc(s.key)}">
        <span class="ab-v ${tone(s.value, s.format)}">${esc(fmt(s.value, s.format))}${q}</span>
        <span class="ab-l">${esc(s.label)}${esc(nTxt)}${isMock(s) ? '' : ' ' + blockChip(s)}${coverageChip(s.coverage)}</span>
        ${s.meaning ? `<details><summary>what it means</summary>${esc(s.meaning)}</details>` : ''}
      </div>`;
    }).join('');
  }
  function renderEquity(d) {
    const e = d.equity;
    $('abEquityChip').innerHTML = e ? blockChip(e, 'live') : '';
    const pts = (e && e.points) || [];
    if (pts.length < 2) { $('abEquity').innerHTML = '<span class="ab-dash">No equity series.</span>'; return; }
    // The viewBox takes the container's real width, so the 11px axis text stays 11px on a
    // phone instead of scaling down with the drawing (re-rendered on resize).
    const W = Math.max(280, Math.round($('abEquity').clientWidth || 800));
    const H = 200, L = 40, R = W - 10, T = 20, B = 160;
    const lo = Math.floor(Math.min(...pts) / 1000) * 1000;
    const hi = Math.ceil(Math.max(...pts) / 1000) * 1000;
    const span = Math.max(hi - lo, 1);
    const x = (i) => L + (i * (R - L)) / (pts.length - 1);
    const y = (v) => B - ((v - lo) * (B - T)) / span;
    const ticks = [];
    for (let v = lo; v <= hi; v += 1000) ticks.push(v);
    const grid = ticks.map((v, i) => `<line class="ab-eq-grid${i > 0 && i < ticks.length - 1 ? ' mid' : ''}" x1="${L}" y1="${y(v).toFixed(1)}" x2="${R}" y2="${y(v).toFixed(1)}"/>`
      + `<text class="ab-eq-axis" x="4" y="${(y(v) + 4).toFixed(1)}">${Math.round(v / 1000)}k</text>`).join('');
    let dd = '';
    const dr = e.drawdown;
    if (dr && dr.from_index != null && dr.to_index != null) {
      const x0 = x(dr.from_index), x1 = x(dr.to_index);
      dd = `<rect class="ab-eq-dd" x="${x0.toFixed(1)}" y="${T}" width="${(x1 - x0).toFixed(1)}" height="${B - T}"/>`
        + `<text class="ab-eq-ddl" x="${(x0 + 6).toFixed(1)}" y="${T + 16}">${esc(fmt(dr.amount, 'usd'))}${dr.date ? ' · ' + esc(shortDate(dr.date)) : ''}</text>`;
    }
    const line = pts.map((v, i) => x(i).toFixed(1) + ',' + y(v).toFixed(1)).join(' ');
    const label = `Equity curve${isMock(e) ? ', mock' : ''}: ${fmt(pts[0], 'usd_plain')} to ${fmt(pts[pts.length - 1], 'usd_plain')}`
      + (dr ? `, max drawdown ${fmt(dr.amount, 'usd')}${dr.date ? ' at ' + dr.date : ''}` : '');
    $('abEquity').innerHTML = `<svg class="ab-eq" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">${grid}${dd}<polyline class="ab-eq-line" points="${line}"/></svg>`;
  }
  function renderLeaks(d) {
    const l = d.leaks;
    $('abLeaksChip').innerHTML = l ? blockChip(l) : '';
    $('abLeaks').innerHTML = ((l && l.items) || []).map((it) => `<li class="${it.amount > 0 ? 'ok' : ''}">
      <span class="ab-k">${esc(it.label)} <span class="ab-n">${esc(fmt(it.amount, 'usd'))}</span></span>
      <span class="ab-d">${it.n != null ? 'n=' + esc(it.n) + ' · ' : ''}${esc(it.detail || '')}</span>
      ${it.href ? `<a href="${esc(it.href)}">see them</a>` : ''}
    </li>`).join('');
  }

  function cell(v, type) {
    if (type === 'text') return `<td>${esc(v)}</td>`;
    if (type === 'chip') return `<td>${v ? chip(v.state, v.label) : '—'}</td>`;
    if (type === 'bar') {
      const w = typeof v === 'number' && Number.isFinite(v) ? Math.max(0, Math.min(100, v * 100)) : 0;
      return `<td><div class="ab-bar" role="img" aria-label="${esc(fmt(v, 'pct'))}"><i style="width:${w.toFixed(0)}%"></i></div></td>`;
    }
    const f = type === 'int' ? 'int' : type;
    return `<td class="ab-num ${tone(v, f)}">${esc(fmt(v, f))}</td>`;
  }
  const sortKey = (v) => (v == null ? -Infinity : typeof v === 'object' && !Array.isArray(v) ? String(v.label || '') : v);
  function tableHtml(t, sort) {
    const cols = t.columns || [];
    let rows = (t.rows || []).slice();
    if (sort && sort.col != null) {
      rows.sort((a, b) => {
        const x = sortKey(a[sort.col]), y = sortKey(b[sort.col]);
        const c = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y));
        return sort.dir === 'asc' ? c : -c;
      });
    }
    const head = cols.map(([name, type], i) => {
      const s = sort && sort.col === i ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none';
      return `<th tabindex="0" data-col="${i}" aria-sort="${s}" class="${type === 'text' || type === 'chip' || type === 'bar' ? '' : 'ab-num'}">${esc(name)}</th>`;
    }).join('');
    const body = rows.map((r) => '<tr>' + cols.map(([, type], i) => cell(r[i], type)).join('') + '</tr>').join('');
    return `<div class="ab-scroll"><table class="ab-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }
  function wireSort(host, t) {
    let sort = null;
    const paint = () => {
      host.innerHTML = tableHtml(t, sort);
      host.querySelectorAll('th[data-col]').forEach((th) => {
        const go = () => {
          const col = Number(th.dataset.col);
          sort = sort && sort.col === col ? { col, dir: sort.dir === 'asc' ? 'desc' : 'asc' } : { col, dir: 'desc' };
          paint();
          const again = host.querySelector(`th[data-col="${col}"]`);
          if (again) again.focus();
        };
        th.addEventListener('click', go);
        th.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); go(); } });
      });
    };
    paint();
  }

  let activeTab = null;
  function renderBreakdowns(d) {
    const list = d.breakdowns || [];
    if (!list.some((b) => b.key === activeTab)) activeTab = list.length ? list[0].key : null;
    const tabs = $('abTabs'), panels = $('abPanels');
    tabs.innerHTML = list.map((b) => `<button type="button" role="tab" id="abTab-${esc(b.key)}"
      aria-controls="abPanel-${esc(b.key)}" aria-selected="${b.key === activeTab}" tabindex="${b.key === activeTab ? 0 : -1}"
      data-t="${esc(b.key)}">${esc(b.label)}</button>`).join('');
    panels.innerHTML = list.map((b) => `<div role="tabpanel" id="abPanel-${esc(b.key)}" aria-labelledby="abTab-${esc(b.key)}"
      ${b.key === activeTab ? '' : 'hidden'}><div class="ab-panel-chip">${isMock(b) ? '' : blockChip(b)}</div><div class="ab-panel-body"></div></div>`).join('');
    list.forEach((b) => wireSort(panels.querySelector(`#abPanel-${CSS.escape(b.key)} .ab-panel-body`), b));
    const select = (key, focus) => {
      activeTab = key;
      tabs.querySelectorAll('button[role="tab"]').forEach((btn) => {
        const on = btn.dataset.t === key;
        btn.setAttribute('aria-selected', String(on));
        btn.tabIndex = on ? 0 : -1;
        if (on && focus) btn.focus();
      });
      panels.querySelectorAll('[role="tabpanel"]').forEach((p) => { p.hidden = p.id !== 'abPanel-' + key; });
    };
    tabs.querySelectorAll('button[role="tab"]').forEach((btn, i, all) => {
      btn.addEventListener('click', () => select(btn.dataset.t, false));
      btn.addEventListener('keydown', (e) => {
        if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
        const next = all[(i + (e.key === 'ArrowRight' ? 1 : all.length - 1)) % all.length];
        select(next.dataset.t, true);
      });
    });
  }
  function renderSlot(d) {
    const s = d.strategies;
    if (!s) { $('abSlot').hidden = true; return; }
    $('abSlot').hidden = false;
    $('abSlot').innerHTML = `<h2 class="ab-h2">Strategy and filter success rates ${isMock(s) ? '' : blockChip(s)}</h2>
      <div>${esc(s.note || '')}</div><div class="ab-slot-body"></div>`;
    wireSort($('abSlot').querySelector('.ab-slot-body'), s);
  }

  let lastData = null;
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => { if (lastData) renderEquity(lastData); }, 150);
  });

  function render(d) {
    lastData = d;
    $('abError').hidden = true;
    paintRange(d.range);
    renderHead(d);
    renderBanner(d);
    renderStats(d);
    renderEquity(d);
    renderLeaks(d);
    renderBreakdowns(d);
    renderSlot(d);
  }

  let seq = 0;
  async function load() {
    const mine = ++seq;
    let r;
    try { r = await apiFetch(summaryUrl()); } catch (_) { r = null; }
    if (mine !== seq) return;               // a newer request superseded this one
    if (r && r.status === 401) { $('abAsof').innerHTML = chip('unknown', 'sign-in required'); return; }
    if (!r || !r.ok) {
      $('abError').hidden = false;
      $('abError').textContent = 'Abacus summary unavailable' + (r ? ' (HTTP ' + r.status + ')' : ' (network)') + '. Nothing below is current.';
      $('abAsof').innerHTML = chip('unknown', 'unavailable');
      return;
    }
    let d = null;
    try { d = await r.json(); } catch (_) { d = null; }
    if (!d || d.version !== SUMMARY_VERSION) {
      // A contract this page does not know is not rendered at all: a wrong field silently read
      // is a wrong number on the principal's screen.
      $('abError').hidden = false;
      $('abError').textContent = 'Abacus summary has an unexpected shape (version ' + (d && d.version != null ? d.version : '?')
        + ', page expects ' + SUMMARY_VERSION + '). Nothing below is current.';
      $('abAsof').innerHTML = chip('unknown', 'unavailable');
      return;
    }
    render(d);
  }

  wireRange();
  load();
})();
