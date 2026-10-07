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
  // R-IV.705(g): "sample data", in those words, on the face of every block that is still the
  // fixture. It used to read "mock" and, worse, the renderers SUPPRESSED it and leaned on the page
  // banner instead — which was fine while the whole page was mock and is misleading now that most
  // of it is live. A section the reader has to infer is sample data is a section that gets read as
  // real.
  function blockChip(block, liveLabel) {
    if (isMock(block)) return chip('unknown', 'sample data', 'Invented figures. This block has no live source yet.');
    return chip('fresh', block.computed_at ? (liveLabel || 'computed') + ' ' + mtTime(block.computed_at) : (liveLabel || 'live'));
  }
  // The window a live figure was drawn over, on its face (R-IV.705(b)). A figure without its span
  // is the other half of a figure without its n: both invite a reader to apply it to a period it
  // was not measured over.
  const spanTxt = (s) => (s && s.from && s.to
    ? ' · ' + shortDate(s.from) + ' → ' + shortDate(s.to)
    : '');

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
    const mock = blocks.filter(isMock);
    const b = $('abBanner');
    if (!mock.length) { b.hidden = true; return; }
    b.hidden = false;
    // R-IV.705(g): COUNT them, and say which. "Mock data — layout and behaviour only" was true of
    // the whole page and is now true of five leak lines and one breakdown; left as it was, it would
    // have told the principal to disbelieve figures that are his own book.
    b.textContent = 'Most of this page is live from the hub. ' + mock.length + ' of ' + blocks.length
      + ' blocks are still sample data, and each says so on its face.';
  }
  function renderStats(d) {
    $('abStats').innerHTML = (d.stats || []).map((s) => {
      const q = s.qualifier ? ' ' + chip(s.qualifier.state, s.qualifier.label) : '';
      const nTxt = (s.n != null ? ' · n=' + s.n : '') + (s.date ? ' · trough ' + shortDate(s.date) : '')
        + spanTxt(s.span);
      return `<div class="ab-stat" data-key="${esc(s.key)}">
        <span class="ab-v ${tone(s.value, s.format)}">${esc(fmt(s.value, s.format))}${q}</span>
        <span class="ab-l">${esc(s.label)}${esc(nTxt)} ${blockChip(s)}${coverageChip(s.coverage)}</span>
        ${s.meaning ? `<details><summary>what it means</summary>${esc(s.meaning)}</details>` : ''}
      </div>`;
    }).join('');
  }
  // ── R-IV.650(b)3 · per account, and combined ──────────────────────────────────────────────
  // The combined row is POOLED over every counted trade, which is what "weighted by trade
  // count" means; averaging the per-account rates would weight a six-trade book like a
  // forty-trade one. Every rate prints its own n, and the two n's differ on purpose: a trade
  // whose basis the book never recorded has a P&L but no return.
  let acctFilter = 'all';
  function acctLabel(a) {
    // A key is not a label. Where the hub served no name, say so rather than printing the key.
    return a.account_display || (a.account ? '(unnamed account)' : 'Unattributed');
  }
  function renderAccounts(d) {
    const list = (d.accounts || []).filter(Boolean);
    const card = $('abAccountsCard');
    if (!card) return;
    if (!list.length) { card.hidden = true; return; }
    card.hidden = false;
    const chipHost = $('abAccountsChip');
    if (chipHost) chipHost.innerHTML = blockChip({ source: 'live', computed_at: new Date().toISOString() }, 'live');

    const btn = (k, t) => `<button type="button" data-abacct="${esc(k)}" aria-pressed="${acctFilter === k}">${esc(t)}</button>`;
    $('abAccountFilter').innerHTML = btn('all', 'All')
      + list.map((a) => btn(a.account == null ? '__none__' : a.account, acctLabel(a))).join('');

    const key = (a) => (a.account == null ? '__none__' : a.account);
    const shown = acctFilter === 'all' ? list : list.filter((a) => key(a) === acctFilter);
    const rowHtml = (a, cls) => `<tr class="${cls || ''}">
        <td>${esc(acctLabel(a))}</td>
        <td class="ab-num">${esc(fmt(a.net_profit, 'usd'))}</td>
        <td class="ab-num">${esc(fmt(a.win_rate, 'pct'))}<span class="ab-n">n=${a.win_rate_n}</span></td>
        <td class="ab-num">${esc(fmt(a.expected_return, 'pct'))}<span class="ab-n">n=${a.expected_return_n}</span></td>
      </tr>`;
    // Every account stays in the table even when one is filtered to, so the one he picked can
    // be read against the others; the filter dims the rest rather than hiding them.
    const body = list.map((a) => rowHtml(a, shown.indexOf(a) < 0 ? 'ab-dim' : '')).join('');
    const combined = { account: null, account_display: 'All accounts',
                       net_profit: pick(d, 'net_profit'), win_rate: pick(d, 'win_rate'),
                       win_rate_n: pickN(d, 'win_rate'),
                       expected_return: pick(d, 'expected_return'), expected_return_n: pickN(d, 'expected_return') };
    $('abAccounts').innerHTML = `<table>
        <thead><tr><th>Account</th><th class="ab-num">Net profit</th><th class="ab-num">Win rate</th><th class="ab-num">Expected return</th></tr></thead>
        <tbody>${body}${rowHtml(combined, 'ab-total')}</tbody></table>`;
    $('abAccountsNote').textContent = d.combined_is_pooled
      ? 'All accounts is pooled over every counted trade, so it is weighted by trade count — not an average of the rates above it.'
      : '';
  }
  const pick = (d, k) => { const s = (d.stats || []).find((x) => x.key === k); return s ? s.value : null; };
  const pickN = (d, k) => { const s = (d.stats || []).find((x) => x.key === k); return s && s.n != null ? s.n : 0; };

  // ── R-IV.705(c)/(d) · ONE CURVE PER ACCOUNT, EACH WITH ITS OWN SPAN ─────────────────────
  // There is no combined line, and that is the point. The accounts' snapshots begin on different
  // days — the 401(a)'s first row is months after the Roth's — so a single summed line would step
  // up on the day a new account joined and read as a gain. Each curve says how many days it has.
  //
  // And every line is labelled "balance — includes deposits/withdrawals", because that is what it
  // is: a balance rises when money is paid in. Drawdown and Sharpe are computed from returns NET of
  // recorded cash events, and where the ledger's events do not reach back to the curve's first day
  // they are not shown at all, with the reason in their place.
  const axisTick = (v) => (Math.abs(v) >= 1000 ? (v / 1000).toFixed(Math.abs(v) >= 10000 ? 0 : 1) + 'k' : String(Math.round(v)));
  function curveSvg(a, W) {
    const vals = a.points.map((p) => p.v);
    const H = 170, L = 46, R = W - 10, T = 16, B = 134;
    const min = Math.min(...vals), max = Math.max(...vals);
    // A step that gives three or four lines whatever the account is worth: the old fixed $1,000
    // grid drew one line for an 800-dollar sleeve and ninety for a retirement account.
    const raw = Math.max((max - min) / 3, 1);
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 5, 10].map((m) => m * mag).find((s) => s >= raw) || mag * 10;
    const lo = Math.floor(min / step) * step, hi = Math.ceil(max / step) * step;
    const span = Math.max(hi - lo, 1);
    const x = (i) => L + (i * (R - L)) / Math.max(a.points.length - 1, 1);
    const y = (v) => B - ((v - lo) * (B - T)) / span;
    const ticks = [];
    for (let v = lo; v <= hi + 1e-6; v += step) ticks.push(v);
    const grid = ticks.map((v, i) => `<line class="ab-eq-grid${i > 0 && i < ticks.length - 1 ? ' mid' : ''}" x1="${L}" y1="${y(v).toFixed(1)}" x2="${R}" y2="${y(v).toFixed(1)}"/>`
      + `<text class="ab-eq-axis" x="4" y="${(y(v) + 4).toFixed(1)}">${esc(axisTick(v))}</text>`).join('');
    let dd = '';
    const dr = a.drawdown;
    if (dr && dr.from_index != null && dr.to_index != null) {
      const x0 = x(dr.from_index), x1 = x(dr.to_index);
      dd = `<rect class="ab-eq-dd" x="${x0.toFixed(1)}" y="${T}" width="${Math.max(x1 - x0, 1).toFixed(1)}" height="${B - T}"/>`
        + `<text class="ab-eq-ddl" x="${(x0 + 6).toFixed(1)}" y="${T + 14}">${esc(fmt(dr.pct, 'pct'))}</text>`;
    }
    const line = a.points.map((p, i) => x(i).toFixed(1) + ',' + y(p.v).toFixed(1)).join(' ');
    const label = `${a.account_display || a.account}: balance from ${fmt(vals[0], 'usd_plain')} on ${a.from}`
      + ` to ${fmt(vals[vals.length - 1], 'usd_plain')} on ${a.to}, including deposits and withdrawals`
      + (dr ? `. Worst fall net of deposits ${fmt(dr.pct, 'pct')}, ${dr.from} to ${dr.to}` : '');
    return `<svg class="ab-eq" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(label)}">${grid}${dd}<polyline class="ab-eq-line" points="${line}"/></svg>`;
  }
  function curveFoot(a) {
    if (a.off_reason) {
      return `<div class="ab-curve-off">${chip('unknown', 'no drawdown or Sharpe')} ${esc(a.off_reason)}</div>`;
    }
    const dr = a.drawdown, sh = a.sharpe, cov = a.covered;
    const bits = [];
    bits.push(dr
      ? `Worst fall <b class="ab-down">${esc(fmt(dr.pct, 'pct'))}</b> <span class="ab-sub">${esc(shortDate(dr.from))} → ${esc(shortDate(dr.to))}</span>`
      : 'No fall recorded on this curve');
    // R-IV.709(c): under thirty returns there is no Sharpe ratio here, and the COUNT stands in its
    // place. A number with the authority of a statistic and the content of noise is worse than a
    // blank, and a "rough" label beside it does not stop it being read as one.
    if (sh && sh.value != null) {
      bits.push(`Sharpe <b>${esc(Number(sh.value).toFixed(2))}</b> <span class="ab-sub">n=${esc(sh.n)}</span>`);
    } else if (sh && sh.insufficient) {
      bits.push(`Sharpe <span class="ab-amber">not enough history (n = ${esc(sh.n)})</span>`);
    } else if (sh) {
      bits.push(`Sharpe — <span class="ab-sub">n=${esc(sh.n)}: no spread in the returns to divide by</span>`);
    }
    // R-IV.709(b): when the cash ledger covers only part of the curve, the figures are measured over
    // the part it covers — and the card says which part, on its face, beside the figures themselves.
    const measured = cov
      ? `<div class="ab-curve-measured">${chip('stale', 'measured ' + shortDate(cov.from) + ' → ' + shortDate(cov.to))} `
        + `<span class="ab-sub">${esc(cov.days)} of ${esc(cov.days + cov.excluded_days)} days · ${esc(cov.reason)}</span></div>`
      : '';
    return `<div class="ab-curve-foot">${bits.join(' · ')}${measured}<div class="ab-sub">Computed from returns net of recorded deposits and withdrawals (${esc(a.cash.events)} events, first ${esc(shortDate(a.cash.first))}).</div></div>`;
  }
  function renderEquity(d) {
    const e = d.equity;
    $('abEquityChip').innerHTML = e ? blockChip(e, 'live') : '';
    const accts = (e && e.accounts) || [];
    if (!accts.length) { $('abEquity').innerHTML = '<span class="ab-dash">No equity series.</span>'; return; }
    const W = Math.max(280, Math.round($('abEquity').clientWidth || 800));
    $('abEquity').innerHTML = accts.map((a) => {
      const head = `<div class="ab-curve-head"><span class="ab-curve-name">${esc(a.account_display || a.account)}</span>`
        + (a.points.length
          ? `<span class="ab-sub">${esc(a.days)} days · ${esc(shortDate(a.from))} → ${esc(shortDate(a.to))}</span>`
            + `<span class="ab-curve-label">${esc(a.line_label)}</span>`
          : '') + '</div>';
      if (a.points.length < 2) {
        return `<div class="ab-curve">${head}<div class="ab-curve-off">${chip('unknown', 'no curve')} ${esc(a.off_reason || 'The hub holds fewer than two balance snapshots for this account.')}</div></div>`;
      }
      return `<div class="ab-curve">${head}${curveSvg(a, W)}${curveFoot(a)}</div>`;
    }).join('');
  }
  // R-IV.705(f)/(g): the items are no longer all the same kind. One is live and the other five
  // are sample data, so each carries its own chip rather than inheriting the block's.
  function renderLeaks(d) {
    const l = d.leaks;
    $('abLeaksChip').innerHTML = l ? blockChip(l) : '';
    $('abLeaks').innerHTML = ((l && l.items) || []).map((it) => {
      const live = it.source === 'live';
      // No dollar figure where none is claimed: a dash in a money column reads as zero.
      const amt = it.amount == null ? '' : ` <span class="ab-n">${esc(fmt(it.amount, 'usd'))}</span>`;
      const n = it.n != null
        ? 'n=' + esc(it.n) + (it.of_n != null ? ' of ' + esc(it.of_n) : '') + ' · '
        : '';
      return `<li class="${it.amount > 0 ? 'ok' : ''}">
      <span class="ab-k">${esc(it.label)}${amt} ${live ? chip('fresh', 'live') : chip('unknown', 'sample data', 'Invented figures. This line has no live source yet.')}</span>
      <span class="ab-d">${n}${esc(it.detail || '')}</span>
      ${it.href ? `<a href="${esc(it.href)}">see them</a>` : ''}
    </li>`;
    }).join('');
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
      ${b.key === activeTab ? '' : 'hidden'}><div class="ab-panel-chip">${blockChip(b)}${b.note ? ` <span class="ab-sub">${esc(b.note)}</span>` : ''}</div><div class="ab-panel-body"></div></div>`).join('');
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
    $('abSlot').innerHTML = `<h2 class="ab-h2">Strategy and filter success rates ${blockChip(s)}</h2>
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
    renderAccounts(d);
    renderEquity(d);
    renderLeaks(d);
    renderBreakdowns(d);
    renderSlot(d);
  }

  // One delegated handler; the filter re-renders from the data already in hand, so changing it
  // costs no request and cannot race the range control.
  document.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('[data-abacct]');
    if (!b || !lastData) return;
    acctFilter = b.dataset.abacct;
    renderAccounts(lastData);
  });

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
