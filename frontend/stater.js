/* Stater Swap v2 — C2 Cockpit Grid · scaffold (SG-1 increment).
   Scope: S5.1 global chips row + S5.2 symbol grid, live-wired to backend /api/crypto/*
   and /api/analytics/risk-budget. Macro/tape/cycle/feed/drawer are placeholders pending
   the SG-1 layout gate. Client consumes backend /api/* only — never the Hub MCP (AEGIS).
   Honest-seam doctrine: fake-healthy is a P0 bug — unknown/absent renders N/A-with-reason.
   Discipline per SG-0 Option A: concurrent = advisory, daily/cooldown = honest N/A seams. */
(() => {
  'use strict';

  const SYMS = [
    { base: 'BTC',      tier: 1 },
    { base: 'ETH',      tier: 1 },
    { base: 'SOL',      tier: 2 },
    { base: 'HYPE',     tier: 3 },
    { base: 'ZEC',      tier: 3 },
    { base: 'FARTCOIN', tier: 3, precBlocked: true },
  ];
  const POLL_MS = 30000;
  let _last = { cycle: null, prices: {} };   // shared cache for the drawer

  // ── visibility-gated polling (mirrors v2.js managed-interval pattern) ────────
  let _timer = null;
  function startPolling(fn, ms) {
    const tick = () => { fn().catch(err => console.warn('[stater] refresh failed', err)); };
    if (document.visibilityState === 'visible') { tick(); _timer = setInterval(tick, ms); }
    document.addEventListener('visibilitychange', () => {
      const vis = document.visibilityState === 'visible';
      if (vis && _timer === null) { tick(); _timer = setInterval(tick, ms); }
      else if (!vis && _timer !== null) { clearInterval(_timer); _timer = null; }
    });
  }

  async function jget(path) {
    const r = await fetch(path, { headers: { 'Accept': 'application/json' } });
    if (!r.ok) throw new Error(`${path} → HTTP ${r.status}`);
    return r.json();
  }
  const settledVal = (r) => (r && r.status === 'fulfilled') ? r.value : null;

  // ── formatting helpers ──────────────────────────────────────────────────────
  function fmtPrice(v) {
    if (v == null || !isFinite(v)) return null;
    if (v >= 1000) return v.toLocaleString('en-US', { maximumFractionDigits: 0 });
    if (v >= 1)    return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    return v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  }
  function priceOf(market) {
    // Outlier-guarded: a vendor can return a cross-contaminated / stale price for a
    // symbol it does not actually list (e.g. binance_spot for a binance-unlisted token
    // — a fake-healthy trap). Reject any source that disagrees with the cohort median
    // by >25%, then prefer perp → coinbase → binance among the survivors.
    if (!market || !market.prices) return null;
    const p = market.prices;
    const num = (x) => { const n = Number(x); return (isFinite(n) && n > 0) ? n : null; };
    const perp = p.perps ? (num(p.perps.okx) ?? num(p.perps.binance) ?? num(p.perps.bybit)) : null;
    const cb = num(p.coinbase_spot);
    const bs = num(p.binance_spot);
    const cands = [perp, cb, bs].filter(v => v != null);
    if (!cands.length) return null;
    const sorted = [...cands].sort((a, b) => a - b);
    const ref = sorted[Math.floor(sorted.length / 2)];   // median
    const good = new Set(cands.filter(v => Math.abs(v - ref) / ref <= 0.25));
    for (const pick of [perp, cb, bs]) { if (pick != null && good.has(pick)) return pick; }
    return ref;
  }
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

  function fmtUsd(v) {
    const n = Number(v);
    if (!isFinite(n)) return null;
    const a = Math.abs(n), s = n < 0 ? '-' : '';
    if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(2)}B`;
    if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(2)}M`;
    if (a >= 1e3) return `${s}$${(a / 1e3).toFixed(1)}K`;
    return `${s}$${a.toFixed(2)}`;
  }
  function fmtPct(v) { const n = Number(v); return isFinite(n) ? `${n >= 0 ? '+' : ''}${n.toFixed(2)}%` : null; }
  function fmtNum(v) { const n = Number(v); return isFinite(n) ? n.toLocaleString('en-US', { maximumFractionDigits: 0 }) : null; }
  function mtTime(iso) {
    if (!iso) return '—';
    const d = new Date(/[Z]|[+-]\d\d:?\d\d$/.test(iso) ? iso : iso + 'Z');  // backend stores UTC, often tz-less
    if (isNaN(d)) return '—';
    return d.toLocaleTimeString('en-US', { timeZone: 'America/Denver', hour: '2-digit', minute: '2-digit', hour12: false }) + ' MT';
  }
  // /state envelope → {txt, cls}. Honest seam on na_reason / null / degraded — never fake-healthy.
  function envRow(env, valueKey, fmt) {
    if (!env) return { txt: 'N/A', cls: 'seam' };
    if (env.na_reason) return { txt: `N/A — ${env.na_reason}`, cls: 'seam' };
    const raw = env[valueKey];
    if (raw == null) return { txt: 'N/A', cls: 'seam' };
    const t = fmt(raw);
    if (t == null) return { txt: 'N/A', cls: 'seam' };
    return { txt: t, cls: (env.degraded || env.stale) ? 'seam stale' : '' };
  }

  // ── per-block health from cycle-extremes cells + regime/tape flags ───────────
  // LIVE → ok · DEGRADED/STALE → bad · NA/absent → na (dashed, never fake-healthy)
  function cellState(cyc, sigId) {
    if (!cyc) return 'na';
    const cells = [...(cyc.capitulation_cells || []), ...(cyc.froth_cells || [])];
    const c = cells.find(x => x.signal_id === sigId);
    if (!c) return 'na';
    if (c.state === 'LIVE') return 'ok';
    if (c.state === 'DEGRADED' || c.state === 'STALE') return 'bad';
    return 'na';
  }
  const cls = (st) => st === 'ok' ? 'ok' : (st === 'bad' ? 'bad' : 'na');

  function blocksFor(base, regSym, tapeSym, cyc) {
    const rg = regSym ? (regSym.degraded ? 'bad' : 'ok') : 'na';
    const tp = tapeSym ? ((tapeSym.degraded || tapeSym.stale || tapeSym.state === 'NA') ? 'bad' : 'ok') : 'na';
    return {
      FU: cellState(cyc, 'perp_funding'),
      OI: cellState(cyc, 'open_interest'),
      BA: cellState(cyc, 'quarterly_basis'),
      LQ: cellState(cyc, 'liquidations'),
      RG: rg,
      TP: tp,
    };
  }

  function setChipV(id, text, klass) {
    const el = document.getElementById(id);
    if (!el) return;
    const v = el.querySelector('.v');
    if (v) { v.textContent = text; v.className = 'v' + (klass ? ' ' + klass : ''); }
  }

  // ── S5.1 chips row ───────────────────────────────────────────────────────────
  function renderChips(regime, clock, risk) {
    // Regime — BTC master
    const master = regime && regime.master;
    setChipV('chipRegime', master ? `${master.regime_state} · BTC MASTER` : 'N/A', master ? '' : 'seam');

    // Session — straight from /clock partition (UI renders time, never computes it)
    const part = clock && clock.partition;
    const wknd = clock && clock.weekend_holiday_flag ? ' · THIN' : '';
    setChipV('chipSession', part ? `${part}${wknd}` : 'N/A', part ? '' : 'seam');
    const sc = document.getElementById('sessionChip');
    if (sc) sc.textContent = `SESSION · ${part || '—'}`;

    // Discipline — Option A honest-seam descope
    const cx = risk && risk.crypto;
    // CONCURRENT: real count, but advisory (no enforced gate) — labeled as such
    if (cx && cx.open_positions != null) {
      setChipV('chipConcurrent', `${cx.open_positions} / ${cx.max_concurrent ?? '?'} · adv`, 'adv');
    } else {
      setChipV('chipConcurrent', 'N/A', 'seam');
    }
    // DAILY: not tracked (static placeholder in backend) — honest seam, never a fake $0
    setChipV('chipDaily', 'N/A — not tracked', 'seam');
    // DIST-TO-FLOOR: breakout_prop untracked — empty with reason, never zero
    setChipV('chipFloor', 'N/A — breakout_prop not reported', 'seam');
  }

  // ── S5.2 symbol grid ──────────────────────────────────────────────────────────
  const BLOCK_ORDER = ['FU', 'OI', 'BA', 'LQ', 'RG', 'TP'];
  // header/badge severity: critical trio + regime + tape (LQ is informational only)
  const CRIT = ['FU', 'OI', 'BA', 'RG', 'TP'];
  const BADGE = ['FU', 'OI', 'BA', 'LQ'];
  const BADGE_LABEL = { FU: 'FUNDING', OI: 'OI', BA: 'BASIS', LQ: 'LIQS' };

  function tapeClass(state) {
    if (state === 'SPOT_LED') return 'up';
    if (state === 'PERP_LED') return 'down';
    if (state === 'MIXED')    return 'muted';
    return 'na';
  }

  function cardHTML(sym, regSym, tapeSym, cyc, price) {
    const base = sym.base;
    const tier = (regSym && regSym.tier) || sym.tier;
    const blk = blocksFor(base, regSym, tapeSym, cyc);
    const degraded = CRIT.some(k => blk[k] !== 'ok');

    const regState = regSym ? regSym.regime_state : null;
    const tapeState = tapeSym ? tapeSym.state : null;

    const priceStr = fmtPrice(price);
    const priceHTML = priceStr
      ? `${esc(priceStr)}${sym.precBlocked ? '<span class="prec">PREC-BLOCKED</span>' : ''}`
      : `<span class="prec">PRICE —</span>`;

    const dots = BLOCK_ORDER.map(k =>
      `<span class="blk ${cls(blk[k])}"><span class="d"></span>${k}</span>`).join('');

    const badBadge = BADGE.filter(k => blk[k] === 'bad' || blk[k] === 'na');
    const degradeRow = degraded
      ? `<div class="sc-degrade"><span class="partial-badge">PARTIAL DATA</span>` +
        (badBadge.length ? `<span class="degrade-note">${badBadge.map(k => BADGE_LABEL[k] + ' —').join(' · ')}</span>` : '') +
        `</div>`
      : '';

    return `
      <div class="sym-card${degraded ? ' degraded' : ''}" data-sym="${esc(base)}" role="button" tabindex="0">
        <div class="sc-head">
          <span class="sc-sym">${esc(base)}</span>
          <span class="tier-badge">T${esc(tier)}</span>
          <span class="health-dot ${degraded ? 'bad' : 'ok'}"></span>
        </div>
        <div class="sc-price">${priceHTML}</div>
        <div class="sc-chips">
          <span><span class="lab">REGIME · </span><span class="st ${regState ? 'muted' : 'na'}">${esc(regState || '—')}</span></span>
          <span><span class="lab">TAPE · </span><span class="st ${tapeClass(tapeState)}">${esc(tapeState || '—')}</span></span>
        </div>
        <div class="floor-ring seam">—</div>
        <div class="floor-ring-lab">FLOOR N/A</div>
        <div class="block-dots">${dots}</div>
        ${degradeRow}
      </div>`;
  }

  function renderGrid(regime, tape, cycle, prices) {
    const grid = document.getElementById('symbolGrid');
    if (!grid) return;
    const regBy = {};
    (regime && regime.symbols || []).forEach(s => { regBy[s.symbol.replace('-USD', '')] = s; });
    const tapeBy = (tape && tape.symbols) || {};
    const cycBy  = (cycle && cycle.symbols) || {};

    grid.innerHTML = SYMS.map(sym =>
      cardHTML(sym, regBy[sym.base], tapeBy[sym.base], cycBy[sym.base], prices[sym.base])
    ).join('');

    grid.querySelectorAll('.sym-card').forEach(card => {
      const open = () => openDrawer(card.getAttribute('data-sym'));
      card.addEventListener('click', open);
      card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
    });
  }

  // ── S5.5 macro band (BTC-master aggregates — render content, per P0.4-1) ─────
  function renderMacro(btc) {
    const el = document.getElementById('macroVals');
    if (!el) return;
    if (!btc) { el.innerHTML = '<span class="pending-note">N/A — BTC master unavailable</span>'; return; }
    const rows = [
      ['FUNDING', envRow(btc.funding, 'rate_pct', v => `${(v).toFixed(4)} · ${btc.funding?.signal || '—'}`)],
      ['OI', envRow(btc.open_interest, 'current_oi_usd', fmtUsd)],
      ['BASIS', envRow(btc.basis, 'basis_annualized_pct', fmtPct)],
      ['LIQS', envRow(btc.liquidations, 'total_usd', fmtUsd)],
      ['LONG', envRow(btc.liquidations, 'long_pct', v => `${v.toFixed(1)}% · ${(btc.liquidations?.composition || '—').toUpperCase()}`)],
    ];
    el.innerHTML = rows.map(([lab, r]) =>
      `<span class="mv"><span class="lab">${lab} </span><span class="val ${r.cls}">${esc(r.txt)}</span></span>`).join('');
  }

  // ── S5.3 tape-health master band (CVD split bar) ─────────────────────────────
  function renderTapeBand(btcTape) {
    const body = document.getElementById('tapeBody');
    const dot = document.getElementById('tapeBandDot');
    if (!body) return;
    if (!btcTape) { body.innerHTML = '<span class="pending-note">N/A — tape-health unavailable</span>'; if (dot) dot.className = 'health-dot bad'; return; }
    const st = btcTape.state || 'NA';
    const stCls = st === 'SPOT_LED' ? 'up' : st === 'PERP_LED' ? 'down' : st === 'MIXED' ? 'muted' : 'muted';
    const spot = Number(btcTape.spot_cvd), perp = Number(btcTape.perp_cvd);
    const aSpot = Math.abs(spot) || 0, aPerp = Math.abs(perp) || 0, tot = (aSpot + aPerp) || 1;
    // divergence derived honestly from spot/perp CVD sign agreement (no backend field exists)
    const div = (isFinite(spot) && isFinite(perp)) ? (Math.sign(spot) === Math.sign(perp) ? 'ALIGNED' : 'DIVERGENT') : '—';
    const stale = btcTape.degraded || btcTape.stale;
    if (dot) dot.className = 'health-dot ' + (stale ? 'stale' : 'ok');
    body.innerHTML =
      `<div class="tape-row1">
         <span class="tape-state-chip ${stCls}">${esc(st)}</span>
         <span class="tape-div">CVD · ${div}${stale ? ' · stale' : ''}</span>
       </div>
       <div class="cvd-bar"><span class="spot" style="width:${(aSpot / tot * 100).toFixed(1)}%"></span><span class="perp" style="width:${(aPerp / tot * 100).toFixed(1)}%"></span></div>
       <div class="cvd-legend">
         <span>SPOT CVD <span class="v ${spot >= 0 ? 'up' : 'down'}">${esc(fmtNum(spot) ?? '—')}</span></span>
         <span>PERP CVD <span class="v ${perp >= 0 ? 'up' : 'down'}">${esc(fmtNum(perp) ?? '—')}</span></span>
       </div>`;
  }

  // ── S5.4 cycle single-axis dial (live composite_score, per P0.4-2) ───────────
  function renderDial(cyc) {
    const el = document.getElementById('cycleDial');
    const cov = document.getElementById('cycleCoverage');
    if (!el) return;
    if (!cyc || cyc.composite_score == null) {
      el.innerHTML = '<span class="pending-note">N/A — cycle composite unavailable</span>';
      if (cov) cov.textContent = '';
      return;
    }
    const score = Math.max(-100, Math.min(100, Number(cyc.composite_score)));
    const pct = (score + 100) / 2;   // -100 CAPITULATION (left) → +100 FROTH (right)
    const lean = score < -10 ? cyc.capitulation_context_copy : score > 10 ? cyc.froth_context_copy : 'neutral';
    // S-10 ETF-flow input is S-5-deferred — surface it honestly
    const cells = [...(cyc.capitulation_cells || []), ...(cyc.froth_cells || [])];
    const s10 = cells.find(c => c.signal_id === 's10_etf_flow_exhaustion');
    const s10note = (s10 && s10.state === 'NA') ? ' · S-10 ETF-flow input deferred (S-5)' : '';
    if (cov) cov.textContent = cyc.coverage_note ? cyc.coverage_note.split('—')[0].trim() : '';
    el.innerHTML =
      `<div class="dial-top"><span class="score">${score.toFixed(0)}</span><span class="ctx">${esc(lean || '')}</span></div>
       <div class="dial-track"><span class="dial-marker" style="left:${pct.toFixed(1)}%"></span></div>
       <div class="dial-ends"><span>CAPITULATION</span><span>FROTH</span></div>
       <div class="dial-note">FROTH → "reduce new risk", never "sell"${esc(s10note)}</div>`;
  }

  // ── S5.7 signal feed (global crypto feed; honest-empty if none — C-A2) ───────
  function renderFeed(ideas) {
    const list = document.getElementById('feedList');
    const cnt = document.getElementById('feedCount');
    if (!list) return;
    const sigs = ((ideas && ideas.signals) || []).filter(s => s.asset_class === 'CRYPTO');
    sigs.sort((a, b) => String(b.created_at).localeCompare(String(a.created_at)));
    if (cnt) cnt.textContent = `${sigs.length} crypto`;
    if (!sigs.length) {
      list.innerHTML = '<div class="feed-empty">No live crypto signals — feed empty (source live, nothing firing).</div>';
      return;
    }
    list.innerHTML = sigs.slice(0, 8).map(s => {
      const dir = (s.direction || '').toLowerCase();
      const entry = s.entry_price != null ? `@ ${Number(s.entry_price).toLocaleString('en-US')}` : '';
      const inv = s.stop_loss != null ? ` · inv ${Number(s.stop_loss).toLocaleString('en-US')}` : '';
      // gating is dormant for crypto (shadow); funding-cost-over-hold & liq-ATR do not exist → seam
      return `<div class="feed-item">
          <span class="ft">${esc(s.signal_type || s.strategy || 'SIGNAL')} · ${esc(s.ticker || '')}</span>
          <span class="dir ${dir}">${esc((s.direction || '').toUpperCase())}</span>
          <span class="fctx">${esc(entry + inv)} · <span class="seam">funding-cost & liq-ATR n/a</span></span>
          <span class="feed-right"><span class="sig-tag shadow">SHADOW</span><span class="feed-time">${esc(mtTime(s.created_at))}</span></span>
        </div>`;
    }).join('');
  }

  // ── drawer: full per-symbol detail (fetches /state/{symbol} on open) ─────────
  function kvRow(label, r) { return `<div class="kv"><span class="k">${esc(label)}</span><span class="v ${r.cls}">${esc(r.txt)}</span></div>`; }
  async function openDrawer(base) {
    const d = document.getElementById('drawer'), bd = document.getElementById('drawerBackdrop');
    const title = document.getElementById('drawerTitle'), body = document.getElementById('drawerBody');
    if (!d || !title || !body) return;
    title.textContent = `${base} · DETAIL`;
    body.innerHTML = '<div class="feed-empty">loading…</div>';
    d.classList.add('open'); if (bd) bd.classList.add('open');
    let st = null;
    try { st = await jget(`/api/crypto/state/${encodeURIComponent(base)}`); } catch (e) { st = null; }
    if (!st) { body.innerHTML = '<div class="feed-empty">N/A — detail unavailable for this symbol.</div>'; return; }
    const cyc = (_last.cycle && _last.cycle.symbols && _last.cycle.symbols[base]) || null;
    const price = _last.prices[base];
    const tp = st.tape_health || {};
    const cycTxt = (cyc && cyc.composite_score != null)
      ? { txt: `${Number(cyc.composite_score).toFixed(0)} · ${cyc.composite_score < -10 ? 'CAPITULATION' : cyc.composite_score > 10 ? 'FROTH' : 'NEUTRAL'}`, cls: '' }
      : { txt: 'N/A', cls: 'seam' };
    body.innerHTML =
      `<div class="dwr-sec">DERIVATIVES</div>` +
      kvRow('Funding', envRow(st.funding, 'rate_pct', v => `${v.toFixed(4)} · ${st.funding?.signal || '—'}`)) +
      kvRow('Open interest', envRow(st.open_interest, 'current_oi_usd', fmtUsd)) +
      kvRow('Basis (ann.)', envRow(st.basis, 'basis_annualized_pct', fmtPct)) +
      kvRow('Liquidations 24h', envRow(st.liquidations, 'total_usd', fmtUsd)) +
      kvRow('Long share', envRow(st.liquidations, 'long_pct', v => `${v.toFixed(1)}% · ${(st.liquidations?.composition || '—').toUpperCase()}`)) +
      kvRow('ATR', envRow(st.atr, 'atr', v => Number(v).toLocaleString('en-US'))) +
      `<div class="dwr-sec">TAPE</div>` +
      kvRow('CVD state', tp.state ? { txt: tp.state + (tp.degraded ? '' : ''), cls: tp.degraded ? 'seam stale' : '' } : { txt: 'N/A', cls: 'seam' }) +
      kvRow('Spot CVD', { txt: fmtNum(tp.spot_cvd) ?? 'N/A', cls: tp.spot_cvd == null ? 'seam' : '' }) +
      kvRow('Perp CVD', { txt: fmtNum(tp.perp_cvd) ?? 'N/A', cls: tp.perp_cvd == null ? 'seam' : '' }) +
      `<div class="dwr-sec">CYCLE &amp; PRICE</div>` +
      kvRow('Cycle position', cycTxt) +
      kvRow('Price', { txt: fmtPrice(price) ?? 'N/A', cls: price == null ? 'seam' : '' }) +
      kvRow('Distance-to-floor', { txt: 'N/A — breakout_prop not reported', cls: 'seam' });
  }
  function closeDrawer() {
    document.getElementById('drawer')?.classList.remove('open');
    document.getElementById('drawerBackdrop')?.classList.remove('open');
  }

  // ── health dot for the page ──────────────────────────────────────────────────
  function setPageHealth(anyLive, anyFail) {
    const dot = document.getElementById('pageHealthDot');
    if (!dot) return;
    dot.className = 'health-dot ' + (anyFail && !anyLive ? 'bad' : (anyFail ? 'stale' : 'ok'));
  }

  // ── refresh cycle ────────────────────────────────────────────────────────────
  async function refresh() {
    const [regimeR, clockR, tapeR, cycleR, riskR, btcStateR, ideasR] = await Promise.allSettled([
      jget('/api/crypto/regime'),
      jget('/api/crypto/clock'),
      jget('/api/crypto/tape-health'),
      jget('/api/crypto/cycle-extremes'),
      jget('/api/analytics/risk-budget'),
      jget('/api/crypto/state/BTC'),            // macro band + master tape band
      jget('/api/trade-ideas?limit=50'),        // signal feed (filtered to crypto client-side)
    ]);
    const regime = settledVal(regimeR), clock = settledVal(clockR),
          tape = settledVal(tapeR), cycle = settledVal(cycleR), risk = settledVal(riskR),
          btcState = settledVal(btcStateR), ideas = settledVal(ideasR);

    // price fan-out (per-symbol /market). NOTE: deployed-polling fetch strategy
    // (batched vs fan-out) is a perf item to settle before SG-2.
    const marketRs = await Promise.allSettled(
      SYMS.map(s => jget(`/api/crypto/market?symbol=${encodeURIComponent(s.base)}`)));
    const prices = {};
    SYMS.forEach((s, i) => { prices[s.base] = priceOf(settledVal(marketRs[i])); });
    _last = { cycle, prices };

    renderChips(regime, clock, risk);
    renderGrid(regime, tape, cycle, prices);
    renderMacro(btcState);
    renderTapeBand(tape && tape.symbols && tape.symbols.BTC);
    renderDial(cycle && cycle.symbols && cycle.symbols.BTC);
    renderFeed(ideas);

    const results = [regimeR, clockR, tapeR, cycleR, riskR, btcStateR, ideasR];
    setPageHealth(results.some(r => r.status === 'fulfilled'), results.some(r => r.status === 'rejected'));
  }

  // ── boot ─────────────────────────────────────────────────────────────────────
  document.getElementById('drawerClose')?.addEventListener('click', closeDrawer);
  document.getElementById('drawerBackdrop')?.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });
  startPolling(refresh, POLL_MS);
})();
