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

  // ── drawer (minimal; full per-symbol detail wired post-SG-1) ─────────────────
  function openDrawer(base) {
    const d = document.getElementById('drawer');
    const bd = document.getElementById('drawerBackdrop');
    const title = document.getElementById('drawerTitle');
    const body = document.getElementById('drawerBody');
    if (!d || !title || !body) return;
    title.textContent = `${base} · DETAIL`;
    body.innerHTML = `<div class="kv"><span class="k">detail</span><span class="v">pending SG-1 layout gate</span></div>`;
    d.classList.add('open'); if (bd) bd.classList.add('open');
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
    const [regimeR, clockR, tapeR, cycleR, riskR] = await Promise.allSettled([
      jget('/api/crypto/regime'),
      jget('/api/crypto/clock'),
      jget('/api/crypto/tape-health'),
      jget('/api/crypto/cycle-extremes'),
      jget('/api/analytics/risk-budget'),
    ]);
    const regime = settledVal(regimeR), clock = settledVal(clockR),
          tape = settledVal(tapeR), cycle = settledVal(cycleR), risk = settledVal(riskR);

    // price fan-out (per-symbol /market). NOTE: deployed-polling fetch strategy
    // (batched vs 6× fan-out) is a perf item to settle before SG-2.
    const marketRs = await Promise.allSettled(
      SYMS.map(s => jget(`/api/crypto/market?symbol=${encodeURIComponent(s.base)}`)));
    const prices = {};
    SYMS.forEach((s, i) => { prices[s.base] = priceOf(settledVal(marketRs[i])); });

    renderChips(regime, clock, risk);
    renderGrid(regime, tape, cycle, prices);

    const results = [regimeR, clockR, tapeR, cycleR, riskR];
    setPageHealth(results.some(r => r.status === 'fulfilled'), results.some(r => r.status === 'rejected'));
  }

  // ── boot ─────────────────────────────────────────────────────────────────────
  document.getElementById('drawerClose')?.addEventListener('click', closeDrawer);
  document.getElementById('drawerBackdrop')?.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDrawer(); });
  startPolling(refresh, POLL_MS);
})();
