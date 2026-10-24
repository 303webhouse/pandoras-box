/* B9 · GLOBAL MARKETS, LIVE — SPEC-B9.md Monday's cut (R-IV.1431). Display only (#42).
 *
 * Self-contained so it can sit in the Regime pop-out's B9 slot without sharing state with the
 * pop-out's own code: `PandoraB9.mount(el)` fetches /api/b9/world and renders into `el`.
 *
 * ABSENT IS SHOWN AS ABSENT: every value the backend could not compute renders "—" with its
 * reason in the tooltip. Never a blank, never a zero, never the mock fixture.
 */
(function () {
  'use strict';
  var BENCH_KEY = 'b9.bench';
  var esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  var NA = function (why) { return '<span class="b9l-na" title="' + esc(why || 'not available') + '">—</span>'; };
  var ARROW = { up: '↗', down: '↘', flat: '→' };

  function spark(vals) {
    var pts = (vals || []).filter(function (v) { return v != null && isFinite(v); });
    if (pts.length < 2) return NA('no ratio history');
    var w = 92, h = 20, min = Math.min.apply(null, pts), max = Math.max.apply(null, pts);
    var rng = (max - min) || 1, step = w / (pts.length - 1);
    var d = pts.map(function (v, i) {
      return (i ? 'L' : 'M') + (i * step).toFixed(1) + ',' + (h - ((v - min) / rng) * h).toFixed(1);
    }).join(' ');
    var cy = (h - ((pts[pts.length - 1] - min) / rng) * h).toFixed(1);
    return '<svg class="b9l-sp" viewBox="0 0 ' + w + ' ' + h + '" width="' + w + '" height="' + h
      + '" aria-label="1-year ratio"><path d="' + d + '"/><circle cx="' + w + '" cy="' + cy + '" r="2"/></svg>';
  }

  function arrows(ch) {
    return ['1M', '3M', '12M'].map(function (k) {
      var c = (ch || {})[k] || {};
      if (c.pct == null) return '<span class="b9l-ar">' + k + ' ' + NA(c.why) + '</span>';
      var cls = c.arrow === 'up' ? 'b9l-up' : c.arrow === 'down' ? 'b9l-dn' : 'b9l-fl';
      return '<span class="b9l-ar ' + cls + '" title="' + esc(k + ': ' + c.pct.toFixed(2) + '%') + '">'
        + k + ' ' + (ARROW[c.arrow] || '→') + '</span>';
    }).join('');
  }

  // `suffix` names the benchmark on the leadership chip, so a row reading "RANGE" twice says
  // which RANGE is the trend (price) and which is leadership (ratio).
  function chip(state, why, kind, suffix, tip) {
    if (!state) return '<span class="b9l-chip b9l-chip-na" title="' + esc(why || '') + '">' + esc(kind) + ' —</span>';
    var cls = { UP: 'up', LEADING: 'up', DOWN: 'dn', LAGGING: 'dn' }[state] || 'fl';
    return '<span class="b9l-chip b9l-chip-' + cls + '" title="' + esc(tip || '') + '">' + esc(state)
      + (suffix ? ' <i>' + esc(suffix) + '</i>' : '') + '</span>';
  }

  function flag(mv, what) {
    if (!mv || !mv.flag) return '';
    return '<span class="b9l-flag b9l-flag-' + (mv.flag === 'EXTREME' ? 'x' : 'u') + '" title="'
      + esc(what + ' move z ' + mv.z + ' (' + mv.change_pct + '% today). ' + (mv.tooltip || '')) + '">'
      + esc(mv.flag) + '</span>';
  }

  function row(r, bench) {
    if (r.missing) {
      return '<div class="b9l-row"><span class="b9l-name">' + esc(r.name) + ' <i>' + esc(r.ticker)
        + '</i></span>' + NA(r.missing) + '</div>';
    }
    var v = (r.vs || {})[bench] || {};
    var p = r.price || {};
    if (v.missing) {
      return '<div class="b9l-row"><span class="b9l-name">' + esc(r.name) + ' <i>' + esc(r.ticker)
        + '</i></span>' + NA(v.missing) + '</div>';
    }
    return '<div class="b9l-row">'
      + '<div class="b9l-l1"><span class="b9l-name">' + esc(r.name) + ' <i>' + esc(r.ticker) + '</i></span>'
      + spark(v.spark) + '</div>'
      + '<div class="b9l-l2">' + arrows(v.changes)
      + chip(p.trend, p.trend_why, 'TREND', null, 'Trend on ' + r.ticker + "'s own price")
      + chip(v.leadership, v.leadership_why, 'vs ' + bench, 'vs ' + bench,
             'Leadership: the same trend test on the ratio ' + r.ticker + ' / ' + bench)
      + flag(p.move, 'Price') + flag(v.move, 'Ratio vs ' + bench) + '</div>'
      + '</div>';
  }

  function ctx(c) {
    if (c.missing) {
      return '<div class="b9l-row"><span class="b9l-name">' + esc(c.name) + ' <i>' + esc(c.ticker)
        + '</i></span>' + NA(c.missing) + '</div>';
    }
    var p = c.price || {};
    return '<div class="b9l-row b9l-ctx"><div class="b9l-l1"><span class="b9l-name">' + esc(c.name)
      + ' <i>' + esc(c.ticker) + '</i></span>'
      + chip(p.trend, p.trend_why, 'TREND', null, 'Trend on ' + c.ticker + "'s own price") + '</div>'
      + '<div class="b9l-l2">' + arrows(p.changes) + flag(p.move, 'Price') + '</div></div>';
  }

  function render(el, env) {
    if (!el) return;
    var d = env && env.data;
    if (!d) {
      el.innerHTML = '<div class="b9l"><div class="b9l-h">GLOBAL MARKETS</div>'
        + '<div class="b9l-un">' + NA((env && env.reason) || 'not read yet')
        + ' <span>' + esc((env && env.reason) || 'Global markets data has not been read yet.') + '</span></div></div>';
      return;
    }
    var bench = 'SPY';
    try { bench = localStorage.getItem(BENCH_KEY) === 'QQQ' ? 'QQQ' : 'SPY'; } catch (_) { /* default */ }
    var md = d.meltdown || {};
    el.innerHTML = '<div class="b9l">'
      + '<div class="b9l-h">GLOBAL MARKETS'
      + '<span class="b9l-tg" role="group" aria-label="ratio benchmark">'
      + ['SPY', 'QQQ'].map(function (b) {
          return '<button type="button" data-b9b="' + b + '"' + (b === bench ? ' class="on" aria-pressed="true"' : ' aria-pressed="false"')
            + '>vs ' + b + '</button>';
        }).join('') + '</span></div>'
      + '<div class="b9l-basis" title="' + esc(d.basis_note || '') + '">' + esc(d.basis_label || '')
      + ' · as of ' + esc(d.as_of || '—') + '</div>'
      + '<div class="b9l-md' + (md.armed ? ' b9l-armed' : '') + '">' + esc(md.text || '—') + '</div>'
      + (d.rows || []).map(function (r) { return row(r, bench); }).join('')
      + '<div class="b9l-h2">COMMODITIES · context</div>'
      + (d.context || []).map(ctx).join('')
      + '<div class="b9l-foot">' + esc(d.trend_rule || '') + ' ' + esc(d.flag_rule || '')
      + ' Display only.</div>'
      + '</div>';
    Array.prototype.forEach.call(el.querySelectorAll('[data-b9b]'), function (btn) {
      btn.addEventListener('click', function () {
        try { localStorage.setItem(BENCH_KEY, btn.getAttribute('data-b9b')); } catch (_) { /* per-view only */ }
        render(el, env);
      });
    });
  }

  var _env = null;
  function mount(el) {
    if (!el) return;
    if (_env) { render(el, _env); return; }
    render(el, null);
    fetch('/api/b9/world', { cache: 'no-store' })
      .then(function (r) { return r.json(); })
      .then(function (j) { _env = j; render(el, j); })
      .catch(function () { render(el, { data: null, reason: 'the global markets read failed' }); });
  }

  window.PandoraB9 = { mount: mount, render: render };
})();
