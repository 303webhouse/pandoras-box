/* Abacus P&L dashboard — R-IV.1315(c). Preview, behind ?pnl=v1.
 *
 * DISPLAY ONLY (#42). Every figure here is the server's; this file does no money arithmetic, not
 * even a subtraction, because a second author of "what the realized total is" is a second place
 * for it to drift from the book.
 *
 * REALIZED AND UNREALIZED NEVER MIX. They are separate keys in the payload and separate tiles
 * here, and nothing adds them.
 *
 * Loaded BEFORE abacus.js so it can claim the page before the summary view renders: it sets
 * `window.__ABACUS_PNL` and abacus.js's boot checks that flag. Without the flag the two views
 * would both paint into #abPage and the loser would be whichever finished its fetch second.
 */
(function () {
  'use strict';

  // R-IV.1356(c), Nick 20:05 MT 2026-10-22 ("Ship the previews"): THIS IS THE DEFAULT ABACUS VIEW.
  //
  // The old summary view is kept behind `?view=summary` for ONE WEEK and then removed:
  //   ROLLBACK FLAG EXPIRES 2026-10-29. On that date, delete this branch, delete abacus.js's
  //   `window.__ABACUS_PNL` guard, and retire the summary renderers.
  // The date is written here rather than only in the lane file because the person who deletes it
  // will be reading this line, not that one. `?pnl=v1` still works, so every link already shared
  // keeps resolving to the same page.
  var params = new URLSearchParams(location.search);
  if (params.get('view') === 'summary' && params.get('pnl') !== 'v1') return;
  window.__ABACUS_PNL = true;

  var state = { period: params.get('period') || 'month', account: (params.get('account') || 'ALL').toUpperCase() };

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  var MINUS = '−';
  // Cents, always. The mock rounded to whole dollars, which on this book turns a +$0.31 month into
  // "+$0" and a 60-cent total into nothing at all: these figures are small and the rounding was a
  // property of the mock, not of the money.
  function usd(v, signed) {
    if (v === null || v === undefined) return null;
    var n = Number(v);
    if (!isFinite(n)) return null;
    var body = '$' + Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (n < 0) return MINUS + body;
    return (signed && n > 0 ? '+' : '') + body;
  }
  function pct(v) { return v === null || v === undefined ? null : Math.round(Number(v) * 100) + '%'; }
  function tone(v) { return v === null || v === undefined ? 'pnl-flat' : (Number(v) > 0 ? 'pnl-up' : (Number(v) < 0 ? 'pnl-dn' : 'pnl-flat')); }
  // The one phrase for "the hub cannot answer this yet". Never a 0, never an em dash on its own.
  function na(why) {
    return '<span class="pnl-na">not available yet</span>'
      + (why ? ' <span class="pnl-sub">— ' + esc(why) + '</span>' : '');
  }
  function val(v, cls) {
    return v === null || v === undefined ? '<span class="pnl-na">unknown</span>'
      : '<span class="' + (cls || '') + '">' + esc(v) + '</span>';
  }

  // The rows behind the unbooked line, named so the figure can be acted on rather than merely
  // noticed: a count the reader cannot trace is a count they have to come and ask about.
  function unbookedRows(eu) {
    return (eu.rows || []).map(function (r) {
      return r.ticker + (r.account_display ? ' (' + r.account_display + ')' : '')
        + ' ' + (usd(r.cost_basis) || '?')
        + (r.days_past != null ? ', ' + r.days_past + 'd past expiry' : '');
    }).join(' · ');
  }

  function kpi(label, body, sub, title) {
    return '<section class="ab-card pnl-kpi"' + (title ? ' title="' + esc(title) + '"' : '') + '>'
      + '<span class="k">' + esc(label) + '</span>'
      + '<span class="v">' + body + '</span>'
      + '<span class="sub">' + (sub || '') + '</span></section>';
  }

  function tabs(name, items, active) {
    return '<div class="pnl-tabs" role="group" aria-label="' + esc(name) + '">'
      + items.map(function (it) {
        return '<button type="button" data-' + name + '="' + esc(it.key) + '" aria-pressed="'
          + (String(it.key).toUpperCase() === String(active).toUpperCase()) + '">' + esc(it.label) + '</button>';
      }).join('') + '</div>';
  }

  /* The curve. Bars are each week's net, the line is the running total.
   * Drawn from the payload's own cumulative figures -- this file never accumulates them itself. */
  function curve(c) {
    if (!c || !c.points || !c.points.length) {
      return '<div class="pnl-na">' + esc((c && c.empty_reason) || 'no closes with a trade date this year') + '</div>';
    }
    var W = 560, H = 200, pad = 26;
    var cums = c.points.map(function (p) { return Number(p.cumulative); });
    var nets = c.points.map(function (p) { return Number(p.net); });
    var lo = Math.min(0, Math.min.apply(null, cums), Math.min.apply(null, nets));
    var hi = Math.max(0, Math.max.apply(null, cums), Math.max.apply(null, nets));
    if (hi === lo) { hi = lo + 1; }
    var y = function (v) { return pad + (hi - v) / (hi - lo) * (H - pad * 2); };
    var x = function (i) { return pad + (c.points.length < 2 ? (W - pad * 2) / 2 : i * (W - pad * 2) / (c.points.length - 1)); };
    var zero = y(0);
    var bw = Math.max(3, Math.min(11, (W - pad * 2) / Math.max(c.points.length, 1) * 0.55));
    var bars = c.points.map(function (p, i) {
      var v = Number(p.net), top = Math.min(y(v), zero), h = Math.abs(y(v) - zero);
      return '<rect x="' + (x(i) - bw / 2).toFixed(1) + '" y="' + top.toFixed(1) + '" width="' + bw.toFixed(1)
        + '" height="' + Math.max(h, 0.6).toFixed(1) + '" fill="' + (v < 0 ? 'var(--down)' : 'var(--up)')
        + '" opacity=".45"><title>' + esc(p.week + ': ' + (usd(p.net, true) || 'n/a') + ' over ' + p.closes + ' close(s)') + '</title></rect>';
    }).join('');
    var line = c.points.map(function (p, i) { return x(i).toFixed(1) + ',' + y(Number(p.cumulative)).toFixed(1); }).join(' ');
    var last = c.points[c.points.length - 1];
    // R-IV.1365(b)3: THE AXIS LABELS ARE HTML, NOT SVG TEXT. They were <text font-size="9">, and
    // raising that to 12 would have been a FALSE FIX: text inside a 560-wide viewBox scaled into
    // a ~332px container paints at about 59% of its attribute, so "12" would still have rendered
    // near 7px while a computed-style check read 12 and passed. Outside the SVG, 12px is 12px.
    return '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Cumulative realized, year to date">'
      + '<line x1="0" y1="' + zero.toFixed(1) + '" x2="' + W + '" y2="' + zero.toFixed(1) + '" stroke="var(--border-strong)" stroke-dasharray="3 3"></line>'
      + bars
      + '<polyline points="' + line + '" fill="none" stroke="var(--text)" stroke-width="1.8"></polyline>'
      + '<circle cx="' + x(c.points.length - 1).toFixed(1) + '" cy="' + y(Number(last.cumulative)).toFixed(1) + '" r="3.5" fill="' + (Number(last.cumulative) < 0 ? 'var(--down)' : 'var(--up)') + '"></circle>'
      + '</svg>'
      + '<div class="pnl-axis pnl-sub"><span>' + esc(c.points[0].week) + '</span>'
      + '<span>the dashed line is $0</span>'
      + '<span>' + esc(last.week) + '</span></div>';
  }

  function acctRows(list) {
    if (!list || !list.length) return '<div class="pnl-na">no account rows</div>';
    var mx = Math.max.apply(null, list.map(function (a) { return Math.abs(Number(a.realized || 0)); }).concat([1]));
    return list.map(function (a) {
      var v = a.realized, w = Math.round(Math.abs(Number(v || 0)) / mx * 100);
      return '<div class="pnl-row"><span>' + esc(a.account_display || a.account) + '</span>'
        // The bar is this page's own ".ab-bar > i", which abacus.js already uses -- not a second
        // bar component with a different inner element.
        + '<span class="ab-bar" role="img" aria-label="' + esc(usd(v, true) || 'unknown')
        + '"><i style="width:' + w + '%;background:'
        + (Number(v || 0) < 0 ? 'var(--down)' : 'var(--up)') + '"></i></span>'
        + '<span class="r ' + tone(v) + '">' + (usd(v, true) || '<span class="pnl-na">unknown</span>') + '</span>'
        + '<span class="r pnl-sub">' + a.closes + ' cl</span>'
        + '<span class="r pnl-sub">' + (pct(a.win_rate) || 'n/a') + '</span></div>';
    }).join('');
  }

  function closes(list) {
    if (!list || !list.length) return '<div class="pnl-na">no closes in this window</div>';
    return '<div class="pnl-closes pnl-sub"><span>DATE</span><span>TICKER</span><span>WHAT</span>'
      + '<span class="r">P&amp;L</span><span class="r">DAYS</span></div>'
      + list.map(function (r) {
        // DAYS HELD IS PER LOT. When a close relieved lots of different ages the RANGE is shown,
        // because the single number the mock drew does not exist for 13 of October's closes.
        var days = r.days != null ? String(r.days)
          : (r.days_range ? r.days_range[0] + '–' + r.days_range[1]
            : '<span class="pnl-na">?</span>');
        var t = r.days_range ? 'this close relieved ' + r.lots + ' lots held for different lengths: '
          + r.days_range[0] + ' to ' + r.days_range[1] + ' days'
          : (r.days_unavailable || (r.lots > 1 ? r.lots + ' lots, all held ' + r.days + ' days' : ''));
        return '<div class="pnl-closes"' + (t ? ' title="' + esc(t) + '"' : '') + '>'
          + '<span>' + esc(String(r.trade_date).slice(5)) + '</span>'
          + '<span>' + esc(r.ticker) + '</span>'
          + '<span class="pnl-sub">' + esc(r.what) + '</span>'
          + '<span class="r ' + tone(r.realized) + '">' + (usd(r.realized, true) || '?') + '</span>'
          + '<span class="r">' + days + '</span></div>';
      }).join('');
  }

  function render(d) {
    var host = document.getElementById('abPnl');
    if (!host) return;
    var p = d.period || {};
    var u = d.unrealized || {};
    var b = d.by_bucket || {};
    var dk = d.date_unknown || {};
    var eu = d.expired_unbooked || {};

    // R-IV.1356(b). THE UNIT IS THE POSITION, counted once per period by its realized in that
    // period — not the closing record, which made one XLF position read as fourteen losses.
    // The closure count stays visible as the sample the money came from, and a position that also
    // booked in another period is named, so these read as position-PERIODS and not as completed
    // trades.
    var winSub = d.win_rate_n
      ? d.wins + ' of ' + d.win_rate_n + ' positions'
        + (d.scratches ? ' · ' + d.scratches + ' scratch' + (d.scratches === 1 ? '' : 'es') + ' excluded' : '')
        + ' · ' + d.closes + ' closes'
        + (d.also_booked_elsewhere
          ? ' · ' + d.also_booked_elsewhere + ' of ' + d.positions + ' also booked in another period'
          : '')
      : 'nothing decided in this window';
    var priorSub = d.prior
      ? esc(d.prior.label) + ' ' + (usd(d.prior.realized, true) || 'no closes')
      : 'no prior period for "all"';
    // THE UNREALIZED TILE CARRIES ITS OWN LIMITS: the coverage when rows are unpriced, and the
    // OLDEST mark rather than one time, because the marks do not share one.
    //
    // NOT a "≥". A floor marker claims the true figure is at LEAST this, which is a statement
    // about order -- and it does not hold for a SIGNED total, because the unpriced rows could
    // move it either way. The Book tile's balance can carry a floor because a balance is
    // positive; a P&L cannot. So the tile states what it COVERS instead.
    var uBody = u.unavailable ? na(u.unavailable) : (usd(u.value, true) || '');
    var uSub = u.unavailable ? ''
      : (u.positions + ' position' + (u.positions === 1 ? '' : 's')
        + (u.unpriced ? ' · covers ' + u.priced + ' of ' + u.positions + ', ' + u.unpriced + ' unpriced' : '')
        + (u.oldest_mark_age_hours != null ? ' · oldest mark ' + u.oldest_mark_age_hours + 'h old' : ''));

    host.innerHTML =
      '<div class="pnl-banner" role="note">Live figures from the hub, '
      + 'display only (#42). Realized P&amp;L counts each closed lot on its <b>trade date</b>, after '
      + 'fees. Open positions are shown separately as unrealized and never mix into the realized '
      + 'totals. Wins and losses count a <b>position</b> once per period, by its realized in that '
      + 'period; the closure count is shown beside it as the sample.' + (dk.count ? ' <b>Date unknown: ' + dk.count + ' closure'
        + (dk.count === 1 ? '' : 's') + ', ' + esc(usd(dk.total, true) || '?')
        + '</b> — outside every figure here, in every period.' : '')
      // R-IV.1349(b): the same pattern, for money the broker has moved past while the book still
      // carries its size. Neither realized nor unrealized: UNBOOKED. It is NOT windowed — a row
      // past its expiry is wrong in every period, and narrowing it to the selected month would
      // hide it the moment the month turned. This line exists because eight Robinhood expiries
      // sat unbooked from 10-16 to 10-22 and October read $485.03 better than it was.
      + (eu.count ? ' <b>Expired, not yet booked: ' + eu.count + ' position'
        + (eu.count === 1 ? '' : 's') + ', cost ' + esc(usd(eu.cost) || '?')
        + '</b> — outside every total here. ' + esc(unbookedRows(eu)) : '') + '</div>'

      + '<div class="pnl-head"><span class="pnl-title">P&amp;L</span>'
      + '<span class="pnl-sub">realized, by trade date · ' + esc(p.from || '?') + ' → ' + esc(p.to || '?') + '</span>'
      + '<span style="flex:1"></span>'
      + tabs('period', [{ key: 'week', label: 'Week' }, { key: 'month', label: 'Month' },
        { key: 'year', label: 'Year' }, { key: 'all', label: 'All' }], state.period)
      + tabs('account', (d.accounts || []), state.account)
      + '</div>'

      + '<div class="pnl-kpis">'
      + kpi('REALIZED · ' + (p.label || ''), '<span class="' + tone(d.realized) + '">'
        + (usd(d.realized, true) || '<span class="pnl-na">no closes</span>') + '</span>',
        priorSub, d.realized_basis)
      + kpi('WIN RATE', val(pct(d.win_rate)), winSub,
        'wins / (wins + losses). A scratch is exactly zero: neither a win nor a loss, so it is out of this denominator.')
      + kpi('AVG WIN / AVG LOSS',
        (usd(d.avg_win) ? '<span class="pnl-up">' + usd(d.avg_win) + '</span>' : '<span class="pnl-na">—</span>')
        + ' <span class="pnl-sub">/</span> '
        + (usd(d.avg_loss) ? '<span class="pnl-dn">' + usd(d.avg_loss) + '</span>' : '<span class="pnl-na">—</span>'),
        d.payoff != null ? 'payoff ' + d.payoff + '× · ' + d.avg_win_n + 'W / ' + d.avg_loss_n + 'L'
          : 'no payoff ratio without both a winner and a loser')
      + kpi('PROFIT FACTOR', val(d.profit_factor != null ? d.profit_factor.toFixed(2) : null),
        d.profit_factor != null ? 'gross wins ÷ gross losses' : esc(d.profit_factor_note || ''),
        'gross wins divided by gross losses, over the same closes')
      + kpi('OPEN · UNREALIZED', '<span class="' + tone(u.value) + '">' + uBody + '</span>', uSub, u.basis)
      + '</div>'

      + '<div class="pnl-main">'
      + '<section class="ab-card pnl-curve"><h2 class="ab-h2">Cumulative realized · '
      + esc(String(d.curve && d.curve.year || '')) + '<span class="pnl-sub"> · bars are each week</span></h2>'
      + curve(d.curve)
      + '<h2 class="ab-h2">By account · ' + esc(p.label || '') + '</h2>' + acctRows(d.by_account)
      + '</section>'
      + '<div class="pnl-side">'
      + '<section class="ab-card"><h2 class="ab-h2">By bucket · ' + esc(p.label || '') + '</h2>'
      + (b.unavailable
        ? na(b.why) + '<div class="pnl-sub" style="margin-top:6px">'
          + b.closes_with_a_bucket + ' of ' + b.closes_total + ' closes in this window carry a bucket'
          + (b.vocabulary && b.vocabulary.length ? ' · values in use: ' + esc(b.vocabulary.join(', ')) : '')
          + '</div>'
        : (b.rows || []).map(function (r) {
          return '<div class="pnl-row" style="grid-template-columns:90px minmax(60px,1fr) 92px"><span>'
            + esc(r.bucket) + '</span><span class="ab-bar"><i style="width:100%;background:var(--up)"></i></span><span class="r ' + tone(r.realized) + '">'
            + esc(usd(r.realized, true)) + '</span></div>';
        }).join(''))
      + '</section>'
      + '<section class="ab-card pnl-closes-card"><h2 class="ab-h2">Recent closes</h2>'
      + '<div class="pnl-closes-wrap">' + closes(d.recent) + '</div></section>'
      + '</div></div>';
  }

  async function load() {
    var host = document.getElementById('abPnl');
    host.innerHTML = '<div class="pnl-sub">reading your book…</div>';
    var q = '/api/abacus/pnl?period=' + encodeURIComponent(state.period)
      + '&account=' + encodeURIComponent(state.account);
    try {
      var r = await fetch(q, { credentials: 'same-origin', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (r.status === 401) { host.innerHTML = '<div class="pnl-na">Sign in to see your P&amp;L.</div>'; return; }
      if (!r.ok) { host.innerHTML = '<div class="pnl-na">The hub answered HTTP ' + r.status + '. Nothing here is current.</div>'; return; }
      render(await r.json());
    } catch (e) {
      host.innerHTML = '<div class="pnl-na">Could not reach the hub: ' + esc(String(e && e.message || e)) + '</div>';
    }
  }

  function boot() {
    var page = document.getElementById('abPage');
    if (!page) return;
    // The summary view's own sections are hidden rather than removed, so ?pnl=v1 is reversible by
    // editing the address and nothing about the other view is destroyed.
    Array.prototype.forEach.call(page.children, function (el) { el.hidden = true; });
    var host = document.createElement('div');
    host.id = 'abPnl';
    host.style.display = 'flex';
    host.style.flexDirection = 'column';
    host.style.gap = '12px';
    page.appendChild(host);
    page.addEventListener('click', function (e) {
      var t = e.target.closest ? e.target.closest('[data-period],[data-account]') : null;
      if (!t) return;
      if (t.dataset.period) state.period = t.dataset.period;
      if (t.dataset.account) state.account = t.dataset.account;
      load();
    });
    load();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();
