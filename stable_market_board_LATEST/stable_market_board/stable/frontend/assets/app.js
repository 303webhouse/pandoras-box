/* Stable Market Board - frontend logic */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

/* ============================================================
   FORMATTERS
   ============================================================ */
const fmtPct = (v, decimals = 2) => {
  if (v === null || v === undefined || isNaN(v)) return '—';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${(v * 100).toFixed(decimals)}%`;
};

const fmtNum = (v, decimals = 2) => {
  if (v === null || v === undefined || isNaN(v)) return '—';
  const sign = v > 0 ? '+' : '';
  return `${sign}${v.toFixed(decimals)}`;
};

const fmtInt = (v) => {
  if (v === null || v === undefined || isNaN(v)) return '—';
  return v.toLocaleString();
};

const heatClass = (v, scale = 'pct') => {
  if (v === null || v === undefined || isNaN(v)) return 'h-neu';
  // pct: typical -10% to +10% range
  let t1, t2, t3;
  if (scale === 'pct') {
    t1 = 0.005; t2 = 0.02; t3 = 0.05;
  } else if (scale === 'pct_big') {
    t1 = 0.01; t2 = 0.05; t3 = 0.15;
  } else if (scale === 'rs') {
    t1 = 0.01; t2 = 0.03; t3 = 0.08;
  } else {
    t1 = 0.005; t2 = 0.02; t3 = 0.05;
  }
  if (v >= t3) return 'h-pos-3';
  if (v >= t2) return 'h-pos-2';
  if (v >= t1) return 'h-pos-1';
  if (v <= -t3) return 'h-neg-3';
  if (v <= -t2) return 'h-neg-2';
  if (v <= -t1) return 'h-neg-1';
  return 'h-neu';
};

const scoreClass = (score) => {
  if (score >= 90) return 's-90';
  if (score >= 75) return 's-75';
  if (score >= 60) return 's-60';
  if (score >= 45) return 's-45';
  if (score >= 30) return 's-30';
  if (score >= 15) return 's-15';
  return 's-00';
};

const atrClass = (v) => {
  if (v === null || v === undefined || isNaN(v)) return 'atr-cool';
  if (v >= 8) return 'atr-hot';
  if (v >= 5) return 'atr-warm';
  if (v <= -3) return 'atr-cold';
  return 'atr-cool';
};

const statusClass = (status) => {
  // CSS-friendly version of the status string
  return 'status-' + status.replace(/[\/ ]/g, '-');
};

/* ============================================================
   TAB SWITCHING
   ============================================================ */
$$('.tab').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    $$('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    $$('.tab-pane').forEach(p => p.classList.toggle('active', p.dataset.pane === tab));
  });
});

/* ============================================================
   API
   ============================================================ */
async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`API error: ${path} -> ${r.status}`);
  return r.json();
}

/* ============================================================
   REGIME (top of board)
   ============================================================ */
function renderRegime(regime, themesData) {
  const breadth = regime.breadth || {};
  const total = breadth.total || 1;
  const pctAbove50 = (breadth.above_50 / total) * 100;
  const pctAbove200 = (breadth.above_200 / total) * 100;
  const bigMovePct = (regime.thresholds && regime.thresholds.big_move_pct) || 4;
  const bigMovePctLabel = bigMovePct % 1 === 0 ? bigMovePct.toFixed(0) : bigMovePct.toFixed(1);

  // Read SPY/QQQ/IWM
  const benches = (regime.benchmarks || []).reduce((acc, b) => {
    acc[b.ticker] = b;
    return acc;
  }, {});

  // Determine regime label heuristically
  let regimeLabel = 'NEUTRAL';
  let regimeColor = 'h-neu';
  if (pctAbove50 >= 60 && pctAbove200 >= 55) {
    regimeLabel = 'RISK-ON';
    regimeColor = 'h-pos-2';
  } else if (pctAbove50 >= 50) {
    regimeLabel = 'RISK-ON / NARROW';
    regimeColor = 'h-pos-1';
  } else if (pctAbove50 <= 35) {
    regimeLabel = 'RISK-OFF';
    regimeColor = 'h-neg-2';
  } else {
    regimeLabel = 'MIXED';
    regimeColor = 'h-neu';
  }

  // Theme summary: dominant, emerging, fading
  const themes = themesData.themes || [];
  const dominant = themes.filter(t => ['DOMINANT', 'STRONG / HOT', 'STRONG'].includes(t.status))
                          .slice(0, 3).map(t => t.theme).join(', ') || '—';
  const emerging = themes.filter(t => ['EMERGING', 'IMPROVING'].includes(t.status))
                          .slice(0, 3).map(t => t.theme).join(', ') || '—';
  const fading = themes.filter(t => ['FADING', 'DETERIORATING', 'WEAK'].includes(t.status))
                          .slice(0, 3).map(t => t.theme).join(', ') || '—';

  $('#regime-asof').textContent = `AS OF ${regime.as_of}`;
  $('#header-sub').textContent = `${regime.as_of} · ${total} TICKERS · UNIVERSE V1`;

  $('#regime-body').innerHTML = `
    <div class="regime-cell">
      <div class="regime-label">Regime</div>
      <div class="regime-value ${regimeColor}">${regimeLabel}</div>
      <div class="regime-sub">${pctAbove50.toFixed(0)}% > 50DMA · ${pctAbove200.toFixed(0)}% > 200DMA</div>
    </div>
    <div class="regime-cell">
      <div class="regime-label">Dominant</div>
      <div class="regime-value h-pos-2" style="font-size:14px">${dominant.split(', ').slice(0,1)[0] || '—'}</div>
      <div class="regime-sub">${dominant !== '—' ? dominant.split(', ').slice(1).join(' · ') : 'no themes scored above 75'}</div>
    </div>
    <div class="regime-cell">
      <div class="regime-label">Emerging</div>
      <div class="regime-value" style="font-size:14px;color:var(--accent-bright)">${emerging.split(', ').slice(0,1)[0] || '—'}</div>
      <div class="regime-sub">${emerging !== '—' ? emerging.split(', ').slice(1).join(' · ') : 'no themes improving'}</div>
    </div>
    <div class="regime-cell">
      <div class="regime-label">Fading</div>
      <div class="regime-value h-neg-2" style="font-size:14px">${fading.split(', ').slice(0,1)[0] || '—'}</div>
      <div class="regime-sub">${fading !== '—' ? fading.split(', ').slice(1).join(' · ') : 'no themes deteriorating'}</div>
    </div>
    <div class="regime-cell">
      <div class="regime-label">New Highs / Lows</div>
      <div class="regime-value">
        <span class="h-pos-2">${breadth.new_high_20d || 0}</span>
        <span style="color:var(--fg-3); font-size:14px;"> / </span>
        <span class="h-neg-2">${(breadth.total - (breadth.above_20 || 0)) || 0}</span>
      </div>
      <div class="regime-sub">52w highs: ${breadth.new_high_52w || 0}</div>
    </div>
    <div class="regime-cell">
      <div class="regime-label">Up ${bigMovePctLabel}% / Down ${bigMovePctLabel}%</div>
      <div class="regime-value">
        <span class="h-pos-2">${breadth.up_big || 0}</span>
        <span style="color:var(--fg-3); font-size:14px;"> / </span>
        <span class="h-neg-2">${breadth.down_big || 0}</span>
      </div>
      <div class="regime-sub">impulse / volatility</div>
    </div>
  `;

  // Render benchmarks row
  const benchOrder = ['SPY', 'QQQ', 'IWM', 'RSP', 'DIA'];
  const benchRows = benchOrder.filter(t => benches[t]).map(t => {
    const b = benches[t];
    return `
      <div class="index-cell">
        <div class="index-tk">${b.ticker}</div>
        <div class="index-sub">${b.subtheme}</div>
        <div class="index-row">
          <span class="label">1D</span>
          <span class="val ${heatClass(b.ret_1d)}">${fmtPct(b.ret_1d)}</span>
        </div>
        <div class="index-row">
          <span class="label">5D</span>
          <span class="val ${heatClass(b.ret_5d, 'pct_big')}">${fmtPct(b.ret_5d)}</span>
        </div>
        <div class="index-row">
          <span class="label">>50DMA</span>
          <span class="val ${heatClass(b.dist_ma50_pct, 'pct_big')}">${fmtPct(b.dist_ma50_pct, 1)}</span>
        </div>
        <div class="index-row">
          <span class="label">ATR EXT</span>
          <span class="val ${atrClass(b.atr_ext_50ma)}">${fmtNum(b.atr_ext_50ma, 1)}</span>
        </div>
      </div>
    `;
  }).join('');
  $('#indices-body').innerHTML = benchRows || '<div class="loading">no benchmark data</div>';

  // Universe breadth grid
  $('#breadth-body').innerHTML = `
    <div class="breadth-row"><span class="label">% > 20DMA</span><span class="val">${((breadth.above_20/total)*100).toFixed(1)}%</span></div>
    <div class="breadth-row"><span class="label">% > 50DMA</span><span class="val">${pctAbove50.toFixed(1)}%</span></div>
    <div class="breadth-row"><span class="label">% > 200DMA</span><span class="val">${pctAbove200.toFixed(1)}%</span></div>
    <div class="breadth-row"><span class="label">Total names</span><span class="val">${total}</span></div>
    <div class="breadth-row"><span class="label">New 20D highs</span><span class="val">${breadth.new_high_20d || 0}</span></div>
    <div class="breadth-row"><span class="label">New 52W highs</span><span class="val">${breadth.new_high_52w || 0}</span></div>
    <div class="breadth-row"><span class="label">Up ${bigMovePctLabel}%+</span><span class="val">${breadth.up_big || 0}</span></div>
    <div class="breadth-row"><span class="label">Down ${bigMovePctLabel}%+</span><span class="val">${breadth.down_big || 0}</span></div>
  `;
}

/* ============================================================
   THEME LIST CARDS (board view)
   ============================================================ */
function renderDominantThemes(themes) {
  const top = themes.slice(0, 8);
  $('#dominant-themes').innerHTML = top.map(t => `
    <div class="theme-row" data-theme="${t.theme}">
      <div class="theme-rank">${t.rank}</div>
      <div class="theme-name">${t.theme}<span class="n">${t.n_names}</span></div>
      <div class="theme-score ${scoreClass(t.score)}">${t.score.toFixed(0)}</div>
      <div class="theme-delta ${heatClass(t.score_1d_delta/100, 'pct')}">${fmtNum(t.score_1d_delta, 1)}</div>
      <div class="theme-status ${statusClass(t.status)}">${t.status}</div>
    </div>
  `).join('');

  $$('#dominant-themes .theme-row').forEach(r => {
    r.addEventListener('click', () => goToTheme(r.dataset.theme));
  });
}

function renderEmergingFading(themes) {
  // Sort by absolute delta, take biggest movers
  const movers = [...themes]
    .filter(t => Math.abs(t.score_1d_delta || 0) > 0.5)
    .sort((a, b) => Math.abs(b.score_1d_delta || 0) - Math.abs(a.score_1d_delta || 0))
    .slice(0, 8);

  if (movers.length === 0) {
    $('#emerging-fading').innerHTML = `<div class="loading">no significant 1-day theme moves</div>`;
    return;
  }

  $('#emerging-fading').innerHTML = movers.map(t => `
    <div class="theme-row" data-theme="${t.theme}">
      <div class="theme-rank">${t.rank}</div>
      <div class="theme-name">${t.theme}<span class="n">${t.n_names}</span></div>
      <div class="theme-score ${scoreClass(t.score)}">${t.score.toFixed(0)}</div>
      <div class="theme-delta ${heatClass(t.score_1d_delta/100, 'pct')}">${fmtNum(t.score_1d_delta, 1)}</div>
      <div class="theme-status ${statusClass(t.status)}">${t.status}</div>
    </div>
  `).join('');

  $$('#emerging-fading .theme-row').forEach(r => {
    r.addEventListener('click', () => goToTheme(r.dataset.theme));
  });
}

/* ============================================================
   ALL THEMES TABLE
   ============================================================ */
function renderThemesTable(themes) {
  const tbody = $('#themes-table tbody');
  tbody.innerHTML = themes.map(t => `
    <tr class="clickable" data-theme="${t.theme}">
      <td class="rank">${t.rank}</td>
      <td class="left"><span class="tk">${t.theme}</span></td>
      <td>${t.n_names}</td>
      <td class="score-cell ${scoreClass(t.score)}">${t.score.toFixed(0)}</td>
      <td class="${heatClass((t.score_1d_delta || 0)/100, 'pct')}">${fmtNum(t.score_1d_delta, 1)}</td>
      <td>${t.breadth.toFixed(0)}</td>
      <td>${t.leadership.toFixed(0)}</td>
      <td>${t.momentum.toFixed(0)}</td>
      <td>${t.pct_above_20ma.toFixed(0)}%</td>
      <td>${t.pct_above_50ma.toFixed(0)}%</td>
      <td>${t.pct_new_high_20d.toFixed(0)}%</td>
      <td class="${heatClass(t.avg_ret_5d, 'pct_big')}">${fmtPct(t.avg_ret_5d)}</td>
      <td class="${heatClass(t.avg_ret_20d, 'pct_big')}">${fmtPct(t.avg_ret_20d)}</td>
      <td class="${atrClass(t.avg_atr_ext_50ma)}">${fmtNum(t.avg_atr_ext_50ma, 1)}</td>
      <td class="${heatClass(t.avg_rs_qqq_20d, 'rs')}">${fmtPct(t.avg_rs_qqq_20d)}</td>
      <td><span class="theme-status ${statusClass(t.status)}">${t.status}</span></td>
    </tr>
  `).join('');

  $$('#themes-table tbody tr').forEach(r => {
    r.addEventListener('click', () => goToTheme(r.dataset.theme));
  });
}

/* ============================================================
   THEME DETAIL (constituent table)
   ============================================================ */
async function goToTheme(theme) {
  // Switch to themes tab, show detail card
  $$('.tab').forEach(b => b.classList.toggle('active', b.dataset.tab === 'themes'));
  $$('.tab-pane').forEach(p => p.classList.toggle('active', p.dataset.pane === 'themes'));

  const data = await api(`/api/themes/${encodeURIComponent(theme)}`);
  $('#theme-detail-title').textContent = `${theme.toUpperCase()} — CONSTITUENTS (${data.constituents.length})`;

  $('#theme-constituents-table tbody').innerHTML = data.constituents.map(c => `
    <tr>
      <td class="left"><span class="tk">${c.ticker}</span></td>
      <td class="left">${c.name}</td>
      <td class="${heatClass(c.ret_1d)}">${fmtPct(c.ret_1d)}</td>
      <td class="${heatClass(c.ret_5d, 'pct_big')}">${fmtPct(c.ret_5d)}</td>
      <td class="${heatClass(c.ret_20d, 'pct_big')}">${fmtPct(c.ret_20d)}</td>
      <td class="${heatClass(c.dist_ma50_pct, 'pct_big')}">${fmtPct(c.dist_ma50_pct, 1)}</td>
      <td class="${atrClass(c.atr_ext_50ma)}">${fmtNum(c.atr_ext_50ma, 1)}</td>
      <td>${fmtNum(c.vol_ratio, 2)}</td>
      <td class="${c.new_high_20d ? 'flag-on' : 'flag-off'}">${c.new_high_20d ? '●' : '·'}</td>
      <td class="${c.new_high_52w ? 'flag-on' : 'flag-off'}">${c.new_high_52w ? '●' : '·'}</td>
      <td class="${heatClass(c.rs_qqq_20d, 'rs')}">${fmtPct(c.rs_qqq_20d)}</td>
      <td><span class="tier tier-${c.liquidity_tier}">${c.liquidity_tier.toUpperCase()}</span></td>
    </tr>
  `).join('');

  $('#theme-detail-card').classList.remove('hidden');
  $('#theme-detail-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

$('#close-theme-detail').addEventListener('click', () => {
  $('#theme-detail-card').classList.add('hidden');
});

/* ============================================================
   EXTENSION TAB
   ============================================================ */
function renderExtension(data) {
  const tooHotRows = (data.too_hot || []).map(r => `
    <tr>
      <td class="left"><span class="tk">${r.ticker}</span></td>
      <td class="left"><span class="theme-tag">${r.theme}</span></td>
      <td class="left subtheme-tag">${r.subtheme || ''}</td>
      <td class="${heatClass(r.ret_1d)}">${fmtPct(r.ret_1d)}</td>
      <td class="${heatClass(r.ret_5d, 'pct_big')}">${fmtPct(r.ret_5d)}</td>
      <td class="${heatClass(r.dist_ma50_pct, 'pct_big')}">${fmtPct(r.dist_ma50_pct, 1)}</td>
      <td class="${atrClass(r.atr_ext_50ma)}">${fmtNum(r.atr_ext_50ma, 1)}</td>
      <td>${fmtNum(r.vol_ratio, 2)}</td>
      <td class="${r.new_high_20d ? 'flag-on' : 'flag-off'}">${r.new_high_20d ? '●' : '·'}</td>
      <td class="${heatClass(r.rs_qqq_20d, 'rs')}">${fmtPct(r.rs_qqq_20d)}</td>
    </tr>
  `).join('');
  $('#too-hot-table tbody').innerHTML = tooHotRows ||
    '<tr><td colspan="10" class="loading">no names ≥ 8 ATR extended right now</td></tr>';

  const fadingRows = (data.fading || []).map(r => `
    <tr>
      <td class="left"><span class="tk">${r.ticker}</span></td>
      <td class="left"><span class="theme-tag">${r.theme}</span></td>
      <td class="left subtheme-tag">${r.subtheme || ''}</td>
      <td class="${heatClass(r.ret_1d)}">${fmtPct(r.ret_1d)}</td>
      <td class="${heatClass(r.ret_5d, 'pct_big')}">${fmtPct(r.ret_5d)}</td>
      <td class="${heatClass(r.dist_ma50_pct, 'pct_big')}">${fmtPct(r.dist_ma50_pct, 1)}</td>
      <td class="${atrClass(r.atr_ext_50ma)}">${fmtNum(r.atr_ext_50ma, 1)}</td>
      <td>${fmtNum(r.vol_ratio, 2)}</td>
      <td class="${heatClass(r.rs_qqq_20d, 'rs')}">${fmtPct(r.rs_qqq_20d)}</td>
    </tr>
  `).join('');
  $('#fading-table tbody').innerHTML = fadingRows ||
    '<tr><td colspan="9" class="loading">no fading names</td></tr>';
}

/* ============================================================
   CLEAN MOMENTUM TAB
   ============================================================ */
function renderMomentum(data) {
  // Update header meta to reflect current thresholds
  const t = data._thresholds || {};
  if (t.clean_atr_min !== undefined) {
    const meta = document.getElementById('momentum-meta');
    if (meta) {
      meta.textContent =
        `ABOVE 20/50DMA · 5D > ${(t.clean_min_ret_5d * 100).toFixed(1)}% · ` +
        `ATR EXT ${t.clean_atr_min}-${t.clean_atr_max} · ` +
        `VOL R > ${t.clean_min_vol} · SORTED BY RS QQQ`;
    }
  }
  const rows = (data.clean_momentum || []).map(r => `
    <tr>
      <td class="left"><span class="tk">${r.ticker}</span></td>
      <td class="left">${r.name}</td>
      <td class="left"><span class="theme-tag">${r.theme}</span></td>
      <td class="left subtheme-tag">${r.subtheme || ''}</td>
      <td class="${heatClass(r.ret_1d)}">${fmtPct(r.ret_1d)}</td>
      <td class="${heatClass(r.ret_5d, 'pct_big')}">${fmtPct(r.ret_5d)}</td>
      <td class="${heatClass(r.ret_20d, 'pct_big')}">${fmtPct(r.ret_20d)}</td>
      <td class="${heatClass(r.dist_ma50_pct, 'pct_big')}">${fmtPct(r.dist_ma50_pct, 1)}</td>
      <td class="${atrClass(r.atr_ext_50ma)}">${fmtNum(r.atr_ext_50ma, 1)}</td>
      <td>${fmtNum(r.vol_ratio, 2)}</td>
      <td class="${r.new_high_20d ? 'flag-on' : 'flag-off'}">${r.new_high_20d ? '●' : '·'}</td>
      <td class="${r.new_high_52w ? 'flag-on' : 'flag-off'}">${r.new_high_52w ? '●' : '·'}</td>
      <td class="${heatClass(r.rs_qqq_20d, 'rs')}">${fmtPct(r.rs_qqq_20d)}</td>
    </tr>
  `).join('');
  $('#momentum-table tbody').innerHTML = rows ||
    '<tr><td colspan="13" class="loading">no clean momentum candidates today</td></tr>';
}

/* ============================================================
   ETF PULSE - Style / Risk / Sector cards
   ============================================================ */
function renderStyleRotation(items) {
  const rows = items.map(item => {
    const v5 = item.ret_5d, v20 = item.ret_20d;
    return `
      <div class="etf-row">
        <span class="etf-pair">${item.label}</span>
        <span></span>
        <span class="etf-label">5D</span>
        <span class="etf-val ${heatClass(v5, 'pct_big')}">${fmtPct(v5, 1)}</span>
        <span class="etf-val ${heatClass(v20, 'pct_big')}">${fmtPct(v20, 1)}</span>
      </div>
    `;
  }).join('');
  $('#style-rotation-body').innerHTML = rows + `
    <div class="etf-row" style="background:var(--bg-2);">
      <span class="etf-context" style="font-size:9.5px;letter-spacing:0.1em;font-weight:700;">RATIO</span>
      <span></span>
      <span></span>
      <span class="etf-label">5D</span>
      <span class="etf-label">20D</span>
    </div>
  `;
  // move the legend to top by reordering
  $('#style-rotation-body').innerHTML = `
    <div class="etf-row" style="background:var(--bg-2);">
      <span class="etf-context" style="font-size:9.5px;letter-spacing:0.1em;font-weight:700;color:var(--fg-1);">PAIR</span>
      <span></span>
      <span class="etf-label" style="color:var(--fg-2);">5D</span>
      <span class="etf-label" style="color:var(--fg-2);">20D</span>
      <span class="etf-label"></span>
    </div>
  ` + items.map(item => {
    const v5 = item.ret_5d, v20 = item.ret_20d;
    return `
      <div class="etf-row">
        <span class="etf-pair">${item.label}</span>
        <span></span>
        <span class="etf-val ${heatClass(v5, 'pct_big')}">${fmtPct(v5, 1)}</span>
        <span class="etf-val ${heatClass(v20, 'pct_big')}">${fmtPct(v20, 1)}</span>
        <span class="etf-label"></span>
      </div>
    `;
  }).join('');
}

function renderRiskPulse(items) {
  const rows = items.map(item => {
    const v5 = item.ret_5d;
    return `
      <div class="etf-row">
        <span class="etf-pair">${item.label}</span>
        <span class="etf-context">${item.context || ''}</span>
        <span class="etf-label">5D</span>
        <span class="etf-val ${heatClass(v5, 'pct_big')}">${fmtPct(v5, 1)}</span>
        <span class="etf-label"></span>
      </div>
    `;
  }).join('');
  $('#risk-pulse-body').innerHTML = rows;
}

function renderSectorRotation(items) {
  // Find max abs RS to scale bars
  const maxAbs = Math.max(0.001, ...items.map(s => Math.abs(s.rs_spy_20d || 0)));

  const rows = items.map(s => {
    const rs = s.rs_spy_20d || 0;
    const widthPct = Math.min(48, Math.abs(rs / maxAbs) * 48);
    const isPos = rs >= 0;
    return `
      <div class="sector-row">
        <span class="sector-tk">${s.ticker}</span>
        <div class="sector-bar-wrap">
          <div class="midline"></div>
          <div class="sector-bar ${isPos ? 'pos' : 'neg'}" style="width:${widthPct}%;"></div>
        </div>
        <span class="sector-val ${heatClass(rs, 'pct_big')}">${fmtPct(rs, 1)}</span>
      </div>
    `;
  }).join('');
  $('#sector-rotation-body').innerHTML = rows;
}

async function loadEtfPulse() {
  try {
    const data = await api('/api/etf_pulse');
    renderStyleRotation(data.style_rotation || []);
    renderRiskPulse(data.risk_pulse || []);
    renderSectorRotation(data.sector_rotation || []);
  } catch (e) {
    console.error('etf_pulse error', e);
  }
}

/* ============================================================
   THEME ROTATION (5-day climbers / fallers)
   ============================================================ */
function renderThemeRotation(data) {
  const meta = $('#rotation-meta');
  if (data.from_date && data.as_of) {
    meta.textContent = `FROM ${data.from_date} TO ${data.as_of} · ${data.lookback_days}D LOOKBACK`;
  }

  const climbersHtml = (data.climbers || []).map(c => {
    const rankDelta = c.rank_delta || 0;
    const rankStr = rankDelta > 0 ? `+${rankDelta} ranks` : `${rankDelta} ranks`;
    return `
      <div class="rotation-row" data-theme="${c.theme}">
        <span class="rotation-theme">${c.theme}</span>
        <span class="rotation-scores">${(c.score_then || 0).toFixed(0)} → ${(c.score || 0).toFixed(0)}</span>
        <span class="rotation-arrow up">+${(c.score_delta || 0).toFixed(1)}</span>
        <span class="rotation-rankdelta">${rankStr}</span>
      </div>
    `;
  }).join('');

  const fallersHtml = (data.fallers || []).map(c => {
    const rankDelta = c.rank_delta || 0;
    const rankStr = rankDelta > 0 ? `+${rankDelta} ranks` : `${rankDelta} ranks`;
    return `
      <div class="rotation-row" data-theme="${c.theme}">
        <span class="rotation-theme">${c.theme}</span>
        <span class="rotation-scores">${(c.score_then || 0).toFixed(0)} → ${(c.score || 0).toFixed(0)}</span>
        <span class="rotation-arrow down">${(c.score_delta || 0).toFixed(1)}</span>
        <span class="rotation-rankdelta">${rankStr}</span>
      </div>
    `;
  }).join('');

  $('#rotation-body').innerHTML = `
    <div class="rotation-col">
      <div class="rotation-col-head">↑ CLIMBERS</div>
      ${climbersHtml || '<div class="loading">no climbers</div>'}
    </div>
    <div class="rotation-col">
      <div class="rotation-col-head">↓ FALLERS</div>
      ${fallersHtml || '<div class="loading">no fallers</div>'}
    </div>
  `;

  $$('#rotation-body .rotation-row').forEach(r => {
    r.addEventListener('click', () => goToTheme(r.dataset.theme));
  });
}

async function loadThemeRotation() {
  try {
    const data = await api('/api/theme_rotation');
    renderThemeRotation(data);
  } catch (e) {
    console.error('theme_rotation error', e);
  }
}

/* ============================================================
   SETTINGS PANEL
   ============================================================ */
let _initialSettings = null;

async function openSettings() {
  const data = await api('/api/settings');
  _initialSettings = JSON.parse(JSON.stringify(data.current));  // deep copy for change detection
  populateSettings(data.current, data.options);
  $('#settings-overlay').classList.remove('hidden');
}

function closeSettings() {
  $('#settings-overlay').classList.add('hidden');
  $('#ma-warning').classList.add('hidden');
}

function populateSettings(current, options) {
  // MA periods checkboxes
  const allowedPeriods = options.ma_periods_allowed || [10, 20, 21, 50, 200];
  const selectedPeriods = new Set(current.metrics.ma_periods);
  $('#ma-periods-group').innerHTML = allowedPeriods.map(p => `
    <label class="settings-checkbox">
      <input type="checkbox" data-ma-period="${p}" ${selectedPeriods.has(p) ? 'checked' : ''}>
      <span class="checkbox-mark"></span>
      <span class="checkbox-label">${p}</span>
    </label>
  `).join('');

  // Numeric inputs
  $('#big-move-input').value = (current.breadth.big_move_threshold * 100).toFixed(1);
  $('#too-hot-input').value = current.extension.too_hot_atr_threshold;
  $('#cm-atr-min-input').value = current.extension.clean_momentum_atr_min;
  $('#cm-atr-max-input').value = current.extension.clean_momentum_atr_max;
  $('#cm-vol-input').value = current.extension.clean_momentum_min_vol_ratio;
  $('#cm-ret-input').value = (current.extension.clean_momentum_min_ret_5d * 100).toFixed(1);

  // Watch MA checkboxes for changes to show the recompute warning
  $$('#ma-periods-group input[type=checkbox]').forEach(cb => {
    cb.addEventListener('change', checkMaChanged);
  });
}

function checkMaChanged() {
  if (!_initialSettings) return;
  const initial = new Set(_initialSettings.metrics.ma_periods);
  const current = collectMaPeriods();
  const changed = initial.size !== current.length || current.some(p => !initial.has(p));
  $('#ma-warning').classList.toggle('hidden', !changed);
}

function collectMaPeriods() {
  return [...$$('#ma-periods-group input[type=checkbox]:checked')]
    .map(cb => parseInt(cb.dataset.maPeriod, 10))
    .sort((a, b) => a - b);
}

async function saveSettings() {
  const periods = collectMaPeriods();
  if (periods.length === 0) {
    alert('Pick at least one MA period.');
    return;
  }

  const payload = {
    metrics: {
      ma_periods: periods,
    },
    breadth: {
      big_move_threshold: parseFloat($('#big-move-input').value) / 100,
    },
    extension: {
      too_hot_atr_threshold: parseFloat($('#too-hot-input').value),
      clean_momentum_atr_min: parseFloat($('#cm-atr-min-input').value),
      clean_momentum_atr_max: parseFloat($('#cm-atr-max-input').value),
      clean_momentum_min_vol_ratio: parseFloat($('#cm-vol-input').value),
      clean_momentum_min_ret_5d: parseFloat($('#cm-ret-input').value) / 100,
    },
  };

  try {
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const result = await r.json();

    closeSettings();
    // Reload all data to reflect new threshold-based settings
    await init();

    // If MA periods changed, surface the recompute reminder
    const initial = new Set(_initialSettings.metrics.ma_periods);
    const newPeriods = result.saved.metrics.ma_periods;
    const maChanged = initial.size !== newPeriods.length || newPeriods.some(p => !initial.has(p));
    if (maChanged) {
      alert('Saved. MA periods changed — run "python -m stable.metrics" in your terminal to recompute, then refresh this page.');
    }
  } catch (e) {
    alert('Save failed: ' + e.message);
  }
}

async function resetSettings() {
  if (!confirm('Reset all settings to defaults?')) return;
  // POST an empty object to get defaults via _deep_merge
  try {
    const r = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    closeSettings();
    await init();
  } catch (e) {
    alert('Reset failed: ' + e.message);
  }
}

$('#settings-btn').addEventListener('click', openSettings);
$('#settings-close-btn').addEventListener('click', closeSettings);
$('#settings-save-btn').addEventListener('click', saveSettings);
$('#settings-reset-btn').addEventListener('click', resetSettings);
$('#settings-overlay').addEventListener('click', (e) => {
  if (e.target.id === 'settings-overlay') closeSettings();
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !$('#settings-overlay').classList.contains('hidden')) {
    closeSettings();
  }
});

/* ============================================================
   REFRESH BUTTON
   ============================================================ */
async function handleRefresh() {
  const btn = $('#refresh-btn');
  const label = btn.querySelector('.refresh-label');
  const statusText = $('#status-text');

  if (btn.disabled) return;

  // Set loading state
  btn.disabled = true;
  btn.classList.remove('is-success', 'is-error');
  btn.classList.add('is-loading');
  const originalLabel = label.textContent;
  label.textContent = 'PULLING...';
  statusText.textContent = 'Refreshing data...';

  // Track elapsed time for the progress label
  const startTime = Date.now();
  const labelInterval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - startTime) / 1000);
    if (elapsed < 10) {
      label.textContent = `PULLING ${elapsed}s`;
    } else if (elapsed < 25) {
      label.textContent = `COMPUTING ${elapsed}s`;
    } else {
      label.textContent = `WORKING ${elapsed}s`;
    }
  }, 1000);

  try {
    const r = await fetch('/api/refresh', { method: 'POST' });
    clearInterval(labelInterval);

    if (!r.ok && r.status !== 202) {
      const body = await r.json().catch(() => ({}));
      throw new Error(body.error || `HTTP ${r.status}`);
    }

    const result = await r.json();

    if (result.status === 'in_progress') {
      // Another refresh is already running; just reload the data
      label.textContent = originalLabel;
      btn.classList.remove('is-loading');
      btn.disabled = false;
      await init();
      return;
    }

    // Success - briefly flash success state, then reload
    btn.classList.remove('is-loading');
    btn.classList.add('is-success');
    label.textContent = 'DONE';

    // Show a quick summary in status bar
    const s = result.summary || {};
    const updated = s.ingest?.updated ?? 0;
    const errors = s.ingest?.errors ?? 0;
    const errStr = errors > 0 ? `, ${errors} errors` : '';
    statusText.textContent = `${updated} updated${errStr}`;

    // Reload all dashboard data
    await init();

    setTimeout(() => {
      btn.classList.remove('is-success');
      label.textContent = originalLabel;
      btn.disabled = false;
    }, 1800);

  } catch (e) {
    clearInterval(labelInterval);
    btn.classList.remove('is-loading');
    btn.classList.add('is-error');
    label.textContent = 'ERROR';
    statusText.textContent = `Refresh failed: ${e.message}`;
    console.error('refresh failed', e);

    setTimeout(() => {
      btn.classList.remove('is-error');
      label.textContent = originalLabel;
      btn.disabled = false;
    }, 4000);
  }
}

$('#refresh-btn').addEventListener('click', handleRefresh);

// Keyboard shortcut: press R to refresh (when not typing in an input)
document.addEventListener('keydown', (e) => {
  if (e.key === 'r' || e.key === 'R') {
    const tag = (document.activeElement?.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea') return;
    if ($('#settings-overlay') && !$('#settings-overlay').classList.contains('hidden')) return;
    e.preventDefault();
    handleRefresh();
  }
});

/* ============================================================
   BREADTH TAB - three Chart.js charts
   ============================================================ */
const _breadthState = {
  participation: { window: '3M', theme: 'All', chart: null },
  impulse: { window: '1M', chart: null },
  adline: { window: '6M', chart: null },
  themesLoaded: false,
};

// Chart.js global config: dark theme defaults
function applyChartDefaults() {
  if (typeof Chart === 'undefined') return;
  Chart.defaults.font.family = "'JetBrains Mono', monospace";
  Chart.defaults.font.size = 10.5;
  Chart.defaults.color = '#a8b3c2';
  Chart.defaults.borderColor = '#1d2633';
  Chart.defaults.plugins.legend.display = false;
}

function trimToWindow(series, days) {
  // For charts that share a long-lookback payload (A/D line), client-side trim
  if (!series || !series.dates) return series;
  const n = Math.min(days, series.dates.length);
  const out = {};
  for (const key of Object.keys(series)) {
    if (Array.isArray(series[key])) {
      out[key] = series[key].slice(-n);
    } else {
      out[key] = series[key];
    }
  }
  return out;
}

async function populateThemeDropdown() {
  if (_breadthState.themesLoaded) return;
  try {
    const data = await api('/api/themes');
    const themes = (data.themes || []).map(t => t.theme).sort();
    const select = $('#breadth-theme-select');
    themes.forEach(t => {
      const opt = document.createElement('option');
      opt.value = t;
      opt.textContent = t;
      select.appendChild(opt);
    });
    _breadthState.themesLoaded = true;
  } catch (e) {
    console.error('failed to load themes for dropdown', e);
  }
}

// Color tokens read from CSS for chart palette consistency
function chartColors() {
  const root = getComputedStyle(document.documentElement);
  return {
    bg0: root.getPropertyValue('--bg-0').trim() || '#0a0e14',
    bg1: root.getPropertyValue('--bg-1').trim() || '#0f141c',
    bg3: root.getPropertyValue('--bg-3').trim() || '#1d2633',
    fg1: root.getPropertyValue('--fg-1').trim() || '#a8b3c2',
    fg2: root.getPropertyValue('--fg-2').trim() || '#6c7689',
    accent: root.getPropertyValue('--accent-bright').trim() || '#6aafff',
    good: root.getPropertyValue('--good-bright').trim() || '#4cc97a',
    bad: root.getPropertyValue('--bad-bright').trim() || '#e85a58',
    warn: root.getPropertyValue('--warn-bright').trim() || '#f0c560',
  };
}

function renderParticipationChart(data) {
  const colors = chartColors();
  const p = data.participation || {};
  const ctx = document.getElementById('chart-participation');
  if (!ctx) return;

  // Destroy previous instance if it exists
  if (_breadthState.participation.chart) {
    _breadthState.participation.chart.destroy();
  }

  _breadthState.participation.chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: p.dates,
      datasets: [
        {
          label: '% > 20DMA',
          data: p.pct_above_20,
          borderColor: colors.warn,
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.15,
        },
        {
          label: '% > 50DMA',
          data: p.pct_above_50,
          borderColor: colors.accent,
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.15,
        },
        {
          label: '% > 200DMA',
          data: p.pct_above_200,
          borderColor: colors.good,
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.15,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          grid: { color: colors.bg3, drawTicks: false },
          ticks: { maxTicksLimit: 8, color: colors.fg2 },
        },
        y: {
          beginAtZero: true,
          max: 100,
          grid: { color: colors.bg3 },
          ticks: {
            color: colors.fg2,
            callback: (v) => v + '%',
          },
        },
      },
      plugins: {
        tooltip: {
          backgroundColor: colors.bg1,
          borderColor: colors.bg3,
          borderWidth: 1,
          titleColor: '#e6eaf0',
          bodyColor: '#e6eaf0',
          padding: 10,
          callbacks: {
            label: (ctx) => ` ${ctx.dataset.label}: ${ctx.parsed.y.toFixed(1)}%`,
          },
        },
      },
    },
    plugins: [{
      id: 'breadthZones',
      beforeDraw(chart) {
        // Reference zone lines at 30% and 70%
        const { ctx, chartArea, scales } = chart;
        if (!chartArea) return;
        const y30 = scales.y.getPixelForValue(30);
        const y70 = scales.y.getPixelForValue(70);
        ctx.save();
        ctx.strokeStyle = colors.bg3;
        ctx.setLineDash([3, 4]);
        ctx.lineWidth = 1;
        [y30, y70].forEach(y => {
          ctx.beginPath();
          ctx.moveTo(chartArea.left, y);
          ctx.lineTo(chartArea.right, y);
          ctx.stroke();
        });
        ctx.restore();
      },
    }],
  });

  // Update legend with latest values
  const latest20 = p.pct_above_20[p.pct_above_20.length - 1];
  const latest50 = p.pct_above_50[p.pct_above_50.length - 1];
  const latest200 = p.pct_above_200[p.pct_above_200.length - 1];
  $('#participation-legend').innerHTML = `
    <span class="legend-item">
      <span class="legend-swatch" style="background:${colors.warn}"></span>
      % > 20DMA <span class="legend-val">${latest20?.toFixed(1)}%</span>
    </span>
    <span class="legend-item">
      <span class="legend-swatch" style="background:${colors.accent}"></span>
      % > 50DMA <span class="legend-val">${latest50?.toFixed(1)}%</span>
    </span>
    <span class="legend-item">
      <span class="legend-swatch" style="background:${colors.good}"></span>
      % > 200DMA <span class="legend-val">${latest200?.toFixed(1)}%</span>
    </span>
    <span class="legend-item" style="color:var(--fg-2)">
      N=${p.total_names} · ${data.theme}
    </span>
  `;
}

function renderImpulseChart(data) {
  const colors = chartColors();
  const i = data.impulse || {};
  const ctx = document.getElementById('chart-impulse');
  if (!ctx) return;

  // Slice for the user's window selection
  const days = _breadthState.impulse.window === '1M' ? 22 : 60;
  const trimmed = trimToWindow(i, days);

  // Bar colors: green if adv-dec positive, red if negative
  const barColors = trimmed.adv_minus_dec.map(v =>
    v >= 0 ? colors.good : colors.bad
  );
  const barBg = trimmed.adv_minus_dec.map(v =>
    v >= 0 ? 'rgba(58, 161, 99, 0.6)' : 'rgba(214, 59, 57, 0.6)'
  );

  if (_breadthState.impulse.chart) {
    _breadthState.impulse.chart.destroy();
  }

  _breadthState.impulse.chart = new Chart(ctx, {
    data: {
      labels: trimmed.dates,
      datasets: [
        {
          type: 'bar',
          label: 'Adv − Dec',
          data: trimmed.adv_minus_dec,
          backgroundColor: barBg,
          borderColor: barColors,
          borderWidth: 1,
          yAxisID: 'y',
          order: 2,
        },
        {
          type: 'line',
          label: 'New 20D Highs',
          data: trimmed.new_high_20d,
          borderColor: colors.accent,
          backgroundColor: 'transparent',
          borderWidth: 1.8,
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.2,
          yAxisID: 'y2',
          order: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          grid: { color: colors.bg3, drawTicks: false },
          ticks: { maxTicksLimit: 8, color: colors.fg2 },
        },
        y: {
          position: 'left',
          grid: { color: colors.bg3 },
          ticks: { color: colors.fg2 },
          title: { display: true, text: 'ADV − DEC', color: colors.fg2, font: { size: 9 } },
        },
        y2: {
          position: 'right',
          grid: { display: false },
          ticks: { color: colors.accent },
          title: { display: true, text: 'NH20', color: colors.accent, font: { size: 9 } },
        },
      },
      plugins: {
        tooltip: {
          backgroundColor: colors.bg1,
          borderColor: colors.bg3,
          borderWidth: 1,
          titleColor: '#e6eaf0',
          bodyColor: '#e6eaf0',
          padding: 10,
        },
      },
    },
  });
}

function renderAdLineChart(data) {
  const colors = chartColors();
  const a = data.ad_line || {};
  const ctx = document.getElementById('chart-adline');
  if (!ctx) return;

  // Slice for the user's window selection (3M=63, 6M=126, 1Y=252)
  const winMap = { '3M': 63, '6M': 126, '1Y': 252 };
  const days = winMap[_breadthState.adline.window] || 126;
  const trimmed = trimToWindow(a, days);

  if (_breadthState.adline.chart) {
    _breadthState.adline.chart.destroy();
  }

  _breadthState.adline.chart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: trimmed.dates,
      datasets: [
        {
          label: 'Cumulative A/D',
          data: trimmed.cumulative_ad,
          borderColor: colors.accent,
          backgroundColor: 'transparent',
          borderWidth: 2,
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.1,
          yAxisID: 'y',
        },
        {
          label: 'SPY Close',
          data: trimmed.spy_close,
          borderColor: colors.warn,
          backgroundColor: 'transparent',
          borderWidth: 1.5,
          pointRadius: 0,
          pointHoverRadius: 4,
          tension: 0.1,
          yAxisID: 'y2',
          borderDash: [4, 3],
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 250 },
      interaction: { mode: 'index', intersect: false },
      scales: {
        x: {
          grid: { color: colors.bg3, drawTicks: false },
          ticks: { maxTicksLimit: 8, color: colors.fg2 },
        },
        y: {
          position: 'left',
          grid: { color: colors.bg3 },
          ticks: { color: colors.accent },
          title: { display: true, text: 'CUM A/D', color: colors.accent, font: { size: 9 } },
        },
        y2: {
          position: 'right',
          grid: { display: false },
          ticks: { color: colors.warn, callback: (v) => '$' + v.toFixed(0) },
          title: { display: true, text: 'SPY', color: colors.warn, font: { size: 9 } },
        },
      },
      plugins: {
        tooltip: {
          backgroundColor: colors.bg1,
          borderColor: colors.bg3,
          borderWidth: 1,
          titleColor: '#e6eaf0',
          bodyColor: '#e6eaf0',
          padding: 10,
        },
      },
    },
  });
}

async function loadBreadthData() {
  applyChartDefaults();
  await populateThemeDropdown();

  // We make two API calls because the A/D chart needs 1Y of context regardless
  // of the participation chart's selected window
  try {
    const [pData, aData] = await Promise.all([
      api(`/api/breadth_series?lookback=${_breadthState.participation.window}&theme=${encodeURIComponent(_breadthState.participation.theme)}`),
      api(`/api/breadth_series?lookback=1Y&theme=All`),
    ]);

    renderParticipationChart(pData);
    renderImpulseChart(pData);   // impulse data lives in the same payload as participation
    renderAdLineChart(aData);
  } catch (e) {
    console.error('breadth load failed', e);
  }
}

// Window toggle handlers
document.addEventListener('click', (e) => {
  const btn = e.target.closest('.win-btn');
  if (!btn) return;
  const wrapper = btn.closest('.window-toggle');
  if (!wrapper) return;
  // Update active state
  wrapper.querySelectorAll('.win-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  const target = wrapper.dataset.target;
  const window = btn.dataset.window;
  if (target === 'participation') {
    _breadthState.participation.window = window;
    // Refetch (different lookback returns different series length)
    api(`/api/breadth_series?lookback=${window}&theme=${encodeURIComponent(_breadthState.participation.theme)}`)
      .then(d => renderParticipationChart(d))
      .catch(err => console.error('refresh participation failed', err));
  } else if (target === 'impulse') {
    _breadthState.impulse.window = window;
    // Reuse the participation API response data we already have - simpler: just re-fetch
    api(`/api/breadth_series?lookback=${_breadthState.participation.window}&theme=${encodeURIComponent(_breadthState.participation.theme)}`)
      .then(d => renderImpulseChart(d))
      .catch(err => console.error('refresh impulse failed', err));
  } else if (target === 'adline') {
    _breadthState.adline.window = window;
    // A/D always uses 1Y data and trims client-side
    api(`/api/breadth_series?lookback=1Y&theme=All`)
      .then(d => renderAdLineChart(d))
      .catch(err => console.error('refresh adline failed', err));
  }
});

// Theme dropdown change
document.addEventListener('change', (e) => {
  if (e.target.id !== 'breadth-theme-select') return;
  _breadthState.participation.theme = e.target.value;
  api(`/api/breadth_series?lookback=${_breadthState.participation.window}&theme=${encodeURIComponent(e.target.value)}`)
    .then(d => {
      renderParticipationChart(d);
      renderImpulseChart(d);
    })
    .catch(err => console.error('theme change failed', err));
});

// Load breadth data when the Breadth tab is first activated
let _breadthLoaded = false;
document.addEventListener('click', (e) => {
  const tab = e.target.closest('.tab');
  if (!tab || tab.dataset.tab !== 'breadth') return;
  if (!_breadthLoaded) {
    _breadthLoaded = true;
    setTimeout(loadBreadthData, 50);  // small delay so the tab is visible first
  }
});

/* ============================================================
   MOMENTUM SCANNER tab
   ============================================================ */
const _momScanState = {
  loaded: false,
  filters: {
    dvolM: 100,        // dollar volume in millions
    above: new Set([20, 50]),
    tiers: new Set(['Core', 'Active', 'Watch']),
  },
};

function fmtDollarVol(v) {
  if (v === null || v === undefined || isNaN(v)) return '—';
  if (v >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  if (v >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
}

function fmtAbsMom(v) {
  // Absolute momentum already in percent
  if (v === null || v === undefined || isNaN(v)) return '—';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${v.toFixed(1)}%`;
}

function absMomHeatClass(v) {
  if (v === null || v === undefined || isNaN(v)) return 'h-neu';
  if (v >= 50) return 'h-pos-3';
  if (v >= 25) return 'h-pos-2';
  if (v >= 10) return 'h-pos-1';
  if (v <= -25) return 'h-neg-3';
  if (v <= -10) return 'h-neg-2';
  if (v <= -3) return 'h-neg-1';
  return 'h-neu';
}

function renderMomScan1WTable(rows) {
  // The 1-week table has its own column layout: it leads with 1W absolute and
  // relative momentum, then a 1-day return column (the noise check), then
  // absolute momentum for the longer windows for context.
  const tbody = document.querySelector('#momscan-1W-table tbody');
  if (!tbody) return;
  if (!rows || rows.length === 0) {
    tbody.innerHTML = '<tr><td colspan="14" class="loading">No tickers pass the current filters</td></tr>';
    return;
  }
  tbody.innerHTML = rows.map(r => {
    const abs1w = r.mom_1W_abs, rel1w = r.mom_1W_rel, r1d = r.ret_1d;
    const abs1 = r.mom_1M_abs, abs3 = r.mom_3M_abs, abs6 = r.mom_6M_abs;
    const d50 = r.dist_ma50_pct, atr = r.atr_ext_50ma, vr = r.vol_ratio;

    // If most of the weekly move happened in one day, flag it. A 5-day move
    // where the 1-day return is more than ~60% of the weekly absolute move
    // is effectively a single-day spike rather than a sustained grind.
    let spikeFlag = '';
    if (r1d !== null && r1d !== undefined && abs1w) {
      const oneDayShare = (r1d * 100) / abs1w;
      if (oneDayShare >= 0.6) {
        spikeFlag = ' <span class="spike-flag" title="Most of the weekly move was a single day">1D SPIKE</span>';
      }
    }

    return `
      <tr>
        <td class="rank">${r.rank}</td>
        <td class="left"><span class="tk">${r.ticker}</span></td>
        <td class="left">${r.name || ''}</td>
        <td class="left"><span class="theme-tag">${r.theme || ''}</span></td>
        <td class="${absMomHeatClass(abs1w)}">${fmtAbsMom(abs1w)}</td>
        <td class="${heatClass(rel1w, 'pct_big')}">${fmtPct(rel1w, 2)}</td>
        <td class="${heatClass(r1d, 'pct_big')}">${fmtPct(r1d, 2)}${spikeFlag}</td>
        <td class="${absMomHeatClass(abs1)}">${fmtAbsMom(abs1)}</td>
        <td class="${absMomHeatClass(abs3)}">${fmtAbsMom(abs3)}</td>
        <td class="${absMomHeatClass(abs6)}">${fmtAbsMom(abs6)}</td>
        <td>${fmtDollarVol(r.dollar_vol_20d)}</td>
        <td class="${heatClass(d50, 'pct_big')}">${fmtPct(d50, 1)}</td>
        <td class="${atrClass(atr)}">${fmtNum(atr, 1)}</td>
        <td>${fmtNum(vr, 2)}</td>
      </tr>
    `;
  }).join('');
}

function renderMomScanTable(tableId, rows, primaryWin) {
  const tbody = document.querySelector(`#${tableId} tbody`);
  if (!tbody) return;
  if (!rows || rows.length === 0) {
    const colspan = 14;
    tbody.innerHTML = `<tr><td colspan="${colspan}" class="loading">No tickers pass the current filters</td></tr>`;
    return;
  }
  tbody.innerHTML = rows.map(r => {
    const abs1 = r.mom_1M_abs, abs3 = r.mom_3M_abs, abs6 = r.mom_6M_abs;
    const rel1 = r.mom_1M_rel, rel3 = r.mom_3M_rel, rel6 = r.mom_6M_rel;
    const d50 = r.dist_ma50_pct;
    const atr = r.atr_ext_50ma;
    const vr = r.vol_ratio;
    // Column order per primary window: primary first, then the others
    const order =
      primaryWin === '1M' ? [abs1, rel1, abs3, rel3, abs6, rel6] :
      primaryWin === '3M' ? [abs3, rel3, abs1, rel1, abs6, rel6] :
                            [abs6, rel6, abs3, rel3, abs1, rel1];
    const absCells = `
      <td class="${absMomHeatClass(order[0])}">${fmtAbsMom(order[0])}</td>
      <td class="${heatClass(order[1], 'pct_big')}">${fmtPct(order[1], 2)}</td>
      <td class="${absMomHeatClass(order[2])}">${fmtAbsMom(order[2])}</td>
      <td class="${heatClass(order[3], 'pct_big')}">${fmtPct(order[3], 2)}</td>
      <td class="${absMomHeatClass(order[4])}">${fmtAbsMom(order[4])}</td>
      <td class="${heatClass(order[5], 'pct_big')}">${fmtPct(order[5], 2)}</td>
    `;
    return `
      <tr>
        <td class="rank">${r.rank}</td>
        <td class="left"><span class="tk">${r.ticker}</span></td>
        <td class="left">${r.name || ''}</td>
        <td class="left"><span class="theme-tag">${r.theme || ''}</span></td>
        ${absCells}
        <td>${fmtDollarVol(r.dollar_vol_20d)}</td>
        <td class="${heatClass(d50, 'pct_big')}">${fmtPct(d50, 1)}</td>
        <td class="${atrClass(atr)}">${fmtNum(atr, 1)}</td>
        <td>${fmtNum(vr, 2)}</td>
      </tr>
    `;
  }).join('');
}

async function loadMomScan() {
  const f = _momScanState.filters;
  const params = new URLSearchParams({
    min_dollar_vol: (f.dvolM * 1_000_000).toString(),
    above_mas: [...f.above].sort((a, b) => a - b).join(','),
    tiers: [...f.tiers].join(','),
    exclude_benchmark: 'true',
    top_n: '25',
  });

  try {
    const data = await api(`/api/momentum_scan?${params.toString()}`);
    const meta = $('#mom-scan-meta');
    if (meta) {
      meta.textContent = `${data.universe_size_after_filter} of ${data.universe_size_before_filter} pass · AS OF ${data.as_of}`;
    }
    renderMomScan1WTable(data.by_window['1W'] || []);
    renderMomScanTable('momscan-1M-table', data.by_window['1M'] || [], '1M');
    renderMomScanTable('momscan-3M-table', data.by_window['3M'] || [], '3M');
    renderMomScanTable('momscan-6M-table', data.by_window['6M'] || [], '6M');
  } catch (e) {
    console.error('momentum scan load failed', e);
  }
}

// Dollar volume preset buttons + custom input
document.addEventListener('click', (e) => {
  const preset = e.target.closest('.momscan-preset');
  if (preset) {
    document.querySelectorAll('.momscan-preset').forEach(b => b.classList.remove('active'));
    preset.classList.add('active');
    const val = parseFloat(preset.dataset.dvol);
    _momScanState.filters.dvolM = val;
    const input = $('#mom-dvol-input');
    if (input) input.value = val;
  }
});

document.addEventListener('input', (e) => {
  if (e.target.id !== 'mom-dvol-input') return;
  const val = parseFloat(e.target.value);
  if (!isNaN(val) && val >= 0) {
    _momScanState.filters.dvolM = val;
    // Match preset highlight if exact
    document.querySelectorAll('.momscan-preset').forEach(b => {
      b.classList.toggle('active', parseFloat(b.dataset.dvol) === val);
    });
  }
});

// MA and tier checkboxes
document.addEventListener('change', (e) => {
  if (e.target.matches('.momscan-checkbox input[data-ma]')) {
    const ma = parseInt(e.target.dataset.ma, 10);
    if (e.target.checked) _momScanState.filters.above.add(ma);
    else _momScanState.filters.above.delete(ma);
  } else if (e.target.matches('.momscan-checkbox input[data-tier]')) {
    const tier = e.target.dataset.tier;
    if (e.target.checked) _momScanState.filters.tiers.add(tier);
    else _momScanState.filters.tiers.delete(tier);
  }
});

// Apply button
document.addEventListener('click', (e) => {
  if (e.target.id !== 'momscan-apply') return;
  loadMomScan();
});

// Auto-load when tab is first opened
document.addEventListener('click', (e) => {
  const tab = e.target.closest('.tab');
  if (!tab || tab.dataset.tab !== 'momentum-scan') return;
  if (!_momScanState.loaded) {
    _momScanState.loaded = true;
    setTimeout(loadMomScan, 50);
  }
});

/* ============================================================
   LIVE INTRADAY OVERLAY
   ============================================================ */
const _liveState = {
  on: false,
  data: {},          // by_ticker map from the last snapshot
  pollTimer: null,
  pollInterval: 60_000,   // refetch every 60s while live is on
};

function fmtLivePrice(px) {
  if (px === null || px === undefined || isNaN(px)) return '';
  return px.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

// Decorate every .tk ticker span on the page with a live price chip
function applyLiveDecorations() {
  const spans = document.querySelectorAll('span.tk');
  spans.forEach(span => {
    const ticker = (span.textContent || '').trim();
    // Remove any prior decoration first
    const existing = span.parentElement.querySelector('.live-px-wrap');
    if (existing) existing.remove();

    if (!_liveState.on) return;

    const live = _liveState.data[ticker];
    if (!live || live.last_price === null || live.last_price === undefined) return;

    const chg = live.change_pct;
    const dirClass = chg > 0.0005 ? 'live-px-up'
                   : chg < -0.0005 ? 'live-px-down'
                   : 'live-px-flat';
    const arrow = chg > 0.0005 ? '\u25b2' : chg < -0.0005 ? '\u25bc' : '\u2192';
    const chgStr = chg !== null && chg !== undefined
      ? `${chg >= 0 ? '+' : ''}${(chg * 100).toFixed(2)}%`
      : '';

    const wrap = document.createElement('span');
    wrap.className = 'live-px-wrap';
    wrap.innerHTML = `
      <span class="live-px ${dirClass}" title="Live price (15-min delayed) ${chgStr}">
        ${arrow} ${fmtLivePrice(live.last_price)}
      </span>`;

    // MA cross chips
    if (live.crossed && live.crossed.length) {
      live.crossed.forEach(c => {
        const cls = c.direction === 'above' ? 'live-chip-cross-up' : 'live-chip-cross-down';
        const maNum = c.ma.replace('ma', '');
        const chip = document.createElement('span');
        chip.className = `live-chip ${cls}`;
        chip.textContent = `${c.direction === 'above' ? '\u2191' : '\u2193'}${maNum}DMA`;
        chip.title = `Crossed ${c.direction} the ${maNum}-day MA today`;
        wrap.appendChild(chip);
      });
    }

    span.parentElement.appendChild(wrap);
  });
}

function updateLiveBar(meta) {
  const bar = $('#live-bar');
  const ageEl = $('#live-bar-age');
  const textEl = $('#live-bar-text');
  if (!bar) return;

  if (!_liveState.on) {
    bar.classList.add('hidden');
    return;
  }
  bar.classList.remove('hidden');

  const age = meta.snapshot_age_min;
  if (age !== null && age !== undefined) {
    ageEl.textContent = `snapshot ${age.toFixed(0)} min old`;
    // Flag stale data (market closed, or feed lagging badly)
    if (age > 25) {
      bar.classList.add('is-stale');
      textEl.textContent = meta.market_status === 'closed'
        ? 'Market closed - showing last available prices'
        : 'Live prices (delayed feed)';
    } else {
      bar.classList.remove('is-stale');
      textEl.textContent = 'Live prices on';
    }
  } else {
    ageEl.textContent = '';
  }

  const count = meta.ticker_count || 0;
  textEl.textContent += ` · ${count} tickers`;
}

async function fetchLiveOverlay() {
  const btn = $('#live-btn');
  btn.classList.add('is-loading');
  try {
    const data = await api('/api/live_overlay');
    _liveState.data = data.by_ticker || {};
    btn.classList.remove('is-loading', 'is-error');
    updateLiveBar(data);
    applyLiveDecorations();
  } catch (e) {
    console.error('live overlay fetch failed', e);
    btn.classList.remove('is-loading');
    btn.classList.add('is-error');
    const textEl = $('#live-bar-text');
    if (textEl) textEl.textContent = 'Live fetch failed - will retry';
  }
}

function startLivePolling() {
  if (_liveState.pollTimer) clearInterval(_liveState.pollTimer);
  _liveState.pollTimer = setInterval(fetchLiveOverlay, _liveState.pollInterval);
}

function stopLivePolling() {
  if (_liveState.pollTimer) {
    clearInterval(_liveState.pollTimer);
    _liveState.pollTimer = null;
  }
}

async function toggleLive() {
  const btn = $('#live-btn');
  const label = $('#live-label');
  _liveState.on = !_liveState.on;

  if (_liveState.on) {
    btn.classList.add('is-on');
    label.textContent = 'LIVE ON';
    await fetchLiveOverlay();
    startLivePolling();
  } else {
    btn.classList.remove('is-on', 'is-error');
    label.textContent = 'LIVE OFF';
    stopLivePolling();
    _liveState.data = {};
    updateLiveBar({});
    applyLiveDecorations();  // clears decorations
  }
}

$('#live-btn').addEventListener('click', toggleLive);

// Re-apply decorations after any tab switch or table re-render.
// MutationObserver catches dynamically rendered table rows.
const _liveObserver = new MutationObserver(() => {
  if (_liveState.on) {
    // Debounce: re-decorate shortly after DOM settles
    clearTimeout(_liveState._decorateTimer);
    _liveState._decorateTimer = setTimeout(applyLiveDecorations, 120);
  }
});
_liveObserver.observe(document.body, { childList: true, subtree: true });

/* ============================================================
   BOOTSTRAP
   ============================================================ */
async function init() {
  try {
    const [regime, themesData, extensionData] = await Promise.all([
      api('/api/regime'),
      api('/api/themes'),
      api('/api/extension'),
    ]);

    renderRegime(regime, themesData);
    renderDominantThemes(themesData.themes || []);
    renderEmergingFading(themesData.themes || []);
    renderThemesTable(themesData.themes || []);
    renderExtension(extensionData);
    renderMomentum(extensionData);

    // Load ETF Pulse and Theme Rotation in parallel (non-blocking, separate concerns)
    loadEtfPulse();
    loadThemeRotation();

    $('#status-text').textContent = `${regime.as_of}`;
  } catch (e) {
    console.error(e);
    $('#status-text').textContent = 'ERROR';
    $('#regime-body').innerHTML = `<div class="loading" style="grid-column: span 6">Error loading data: ${e.message}</div>`;
  }
}

init();
