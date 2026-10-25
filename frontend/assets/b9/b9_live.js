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

  // R-IV.1436(e)3: THE RECOVERY RACE. Always shown, collapsed by default with the anchor date on
  // its summary line, and open by default while meltdown mode is armed. Every ticker -- SPY and QQQ
  // included -- is ranked and led the same way: the leader mark does not care who leads.
  function raceVal(key, r) {
    var v = r[key];
    if (key === 'back200' && r.back200_status === 'held') {
      return '<i title="above its own 200-day on the day of SPY’s low">held above</i>';
    }
    if (v == null) return NA(r[key + '_note'] || 'not available');
    if (key === 'gained' || key === 'fell') return (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%';
    return esc(v) + (r[key + '_note'] ? ' <i>' + esc(r[key + '_note']) + '</i>' : '');
  }
  function race(rc) {
    if (!rc) return '';
    var a = rc.anchor;
    var head = 'RECOVERY RACE · ' + (a && a.valid
      ? 'from SPY’s low ' + esc(a.date) + ' (' + esc(a.sessions_ago) + ' sessions ago)'
      : 'no anchor yet');
    var body;
    if (!a || !a.valid) {
      body = '<div class="b9l-un">' + esc(rc.reason || 'the race has no anchor') + '</div>';
    } else {
      var byT = {};
      (rc.rows || []).forEach(function (r) { byT[r.ticker] = r; });
      // R-IV.1441(b)1: ties are SHOWN as ties -- one shared place number on every tied market, a
      // "tie" mark on each, alphabetical inside the tie. Every market in first place is a leader.
      body = (rc.columns || []).map(function (c) {
        var order = (rc.order || {})[c.key] || [];
        var places = (rc.places || {})[c.key] || order.map(function (t, i) { return { rank: i + 1, tickers: [t], tie: false }; });
        var unranked = (rc.rows || []).filter(function (r) { return order.indexOf(r.ticker) < 0; });
        return '<div class="b9l-rc"><div class="b9l-rch" title="' + esc(c.rule) + '">' + esc(c.label)
          + (c.proxy ? ' <span class="b9l-proxy">proxy</span>' : '') + '</div><ol>'
          + places.map(function (p) {
              return p.tickers.map(function (t) {
                var r = byT[t] || {};
                return '<li value="' + esc(p.rank) + '"' + (p.rank === 1 ? ' class="b9l-lead"' : '') + '><b>' + esc(t)
                  + '</b> ' + raceVal(c.key, r)
                  + (p.tie ? ' <span class="b9l-tie" title="tied for place ' + esc(p.rank) + ' with '
                      + esc(p.tickers.filter(function (x) { return x !== t; }).join(', ')) + '">tie</span>' : '')
                  + '</li>';
              }).join('');
            }).join('') + '</ol>'
          + (unranked.length ? '<div class="b9l-rnu">not yet: ' + unranked.map(function (r) {
              return '<span title="' + esc(r.missing || r[c.key + '_note'] || '') + '">' + esc(r.ticker) + '</span>';
            }).join(', ') + '</div>' : '')
          + '</div>';
      }).join('')
        + '<div class="b9l-rnote">Anchor: ' + esc(a.rule) + '. ' + esc(rc.visibility || '') + '.</div>';
    }
    return '<details class="b9l-race"' + (rc.open_by_default ? ' open' : '') + '><summary>' + head
      + '</summary>' + body + '<div class="b9l-foot">' + esc(rc.footnote || '') + ' Display only.</div></details>';
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
      + race(d.race)
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

  // R-IV.1432(d): ABACUS's Regime pop-out renders `<div id="b9-mount">` holding a placeholder
  // line, and B9 REPLACES ITS CONTENT -- the element, its id and its place stay. The drawer is
  // re-rendered with innerHTML, so a fresh #b9-mount appears on every open; this watches for one
  // that has not been filled and fills it. No edit to the pop-out's own code is needed.
  function fillMounts() {
    var el = document.getElementById('b9-mount');
    if (el && !el.getAttribute('data-b9-live')) {
      el.setAttribute('data-b9-live', '1');
      mount(el);
    }
  }
  function watch() {
    fillMounts();
    if (window.MutationObserver && document.body) {
      new MutationObserver(fillMounts).observe(document.body, { childList: true, subtree: true });
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', watch);
  else watch();
})();
