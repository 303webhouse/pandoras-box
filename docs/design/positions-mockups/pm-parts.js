/* Shared renderers for the three positions-screen layouts. MOCK DATA only (pm-data.js). */
(function () {
  const P = window.PM;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const MINUS = '−';
  const usd = (v, signed) => v == null ? '—' : (v < 0 ? MINUS : (signed && v > 0 ? '+' : '')) + '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: 2 });
  const tone = (v) => v == null ? '' : v > 0 ? 'pm-up' : v < 0 ? 'pm-down' : '';

  const PROV = {
    UNKNOWN: ['unknown', 'unknown', 'Lowest rung: nothing says where this came from.'],
    BROKER_VERIFIED: ['verified', 'broker verified', 'A broker record backs this row (reference on file).'],
    SCREEN_VERIFIED: ['screen', 'screen read', 'Read off a broker screen; an import or broker record will supersede it.'],
    PRINCIPAL_REPORTED: ['reported', 'reported', 'Reported by the principal; no broker evidence yet.'],
    IMPORTED: ['imported', 'imported', 'Loaded from an export file; ranks above a screen read, below a broker-referenced record.'],
  };
  const prov = (p) => { const [s, l, t] = PROV[p] || ['reported', p, '']; return `<span class="pm-chip" data-state="${s}" title="${esc(t)}">${esc(l)}</span>`; };
  const chip = (state, label, title) => `<span class="pm-chip" data-state="${state}"${title ? ` title="${esc(title)}"` : ''}>${esc(label)}</span>`;
  const ladder = () => `<div class="pm-ladder">Provenance, weakest to strongest: ${P.ladder.map((k) => prov(k)).join(' <span class="pm-dim">&lt;</span> ')}</div>`;
  const buckets = () => `<div class="pm-ladder">Buckets: ${P.buckets.map(([n, d]) => `<span class="pm-tag">${esc(n)}${d ? ' · ' + esc(d) : ''}</span>`).join(' ')}</div>`;
  const mockBanner = () => `<div class="pm-banner">Mock data — layout only · ${esc(P.label)} · every figure is invented, the principal approves or adjusts the layout</div>${ladder()}${buckets()}`;

  function markCell(p) {
    if (p.mark == null) return `<span class="pm-amber" title="no mark: the source could not price this position">UNAVAILABLE</span>`;
    const v = usd(p.mark);
    return p.markState === 'stale' ? `${v} ${chip('unknown', 'stale mark', 'Mark is older than its bound; cannot confirm it is current.')}` : v;
  }
  function pnlCell(p) {
    if (p.mark == null) return `<span class="pm-amber">—</span>`;
    if (p.basisIncomplete) return `<span class="pm-amber" title="${esc(p.basisIncomplete)}">basis under review</span>`;
    const d = p.mark - p.cost; return `<span class="${tone(d)}">${usd(d, true)}</span>`;
  }

  function gauge(s) {
    const scale = Math.max(s.ceiling, s.atRisk) * 1.15;
    const pct = (v) => Math.min(100, (v / scale) * 100).toFixed(1);
    const headroom = s.ceiling - s.atRisk;
    const floor = s.cashFloor != null;
    const cashOk = !floor || s.cash >= s.cashFloor;
    return `<div class="pm-gauge" role="img" aria-label="${esc(s.account)}: ${esc(s.measure)} ${usd(s.atRisk)} of ${usd(s.ceiling)}${floor ? '; cash ' + usd(s.cash) + ' against a ' + usd(s.cashFloor) + ' floor' : ''}">
      <div class="pm-g-head"><span class="pm-g-name">${esc(s.account)} <span class="pm-dim">${esc(s.kind)}</span> ${chip('unknown', 'mock', 'Invented figures')}</span>
        <span class="pm-g-fig">${usd(s.atRisk)} ${esc(s.measure)} of ${usd(s.ceiling)} · headroom <b class="${headroom < 0 ? 'pm-down' : ''}">${usd(headroom)}</b></span></div>
      <div class="pm-dim">${esc(s.rule)}</div>
      <div class="pm-g-track"><i class="pm-g-fill" style="width:${pct(s.atRisk)}%"></i><b class="pm-g-ceil" style="left:${pct(s.ceiling)}%" title="limit ${usd(s.ceiling)}"></b></div>
      <div class="pm-g-foot"><span>${floor ? `Cash ${usd(s.cash)} vs $200 always-in-cash floor ${cashOk ? chip('verified', 'above floor') : chip('reported', 'BELOW FLOOR')}` : `Cash ${usd(s.cash)}`}</span><span class="pm-dim">balance ${usd(s.balance)}</span></div>
    </div>`;
  }

  function stopBadge(st) {
    const map = { 'broker order': 'verified', 'daily-close': 'screen', none: 'reported' };
    const note = { 'broker order': 'Rests at the broker; fires on its own.', 'daily-close': 'Watched at the close; fires only if someone acts.', none: 'No stop written.' };
    return chip(map[st.type] || 'reported', st.type === 'none' ? 'no stop' : 'stop: ' + st.type, note[st.type]) + (st.level && st.level !== '—' ? ` <span class="pm-dim">${esc(st.level)}</span>` : '');
  }

  function bookRow(p, attrs) {
    return `<tr class="pm-row" ${attrs || ''} data-id="${p.id}">
      <td><b>${esc(p.ticker)}</b><div class="pm-dim">${esc(p.bucket)}</div></td>
      <td>${esc(p.structure)}${p.expiry ? `<div class="pm-dim">exp ${esc(p.expiry.slice(5))}</div>` : ''}</td>
      <td class="pm-num">${p.qty}</td><td class="pm-num">${usd(p.cost)}</td><td class="pm-num">${markCell(p)}</td>
      <td class="pm-num">${pnlCell(p)}</td><td>${prov(p.prov)}</td></tr>`;
  }
  const bookHead = `<thead><tr><th>Position</th><th>Structure</th><th class="pm-num">Qty</th><th class="pm-num">Cost</th><th class="pm-num">Mark</th><th class="pm-num">P&amp;L</th><th>Provenance</th></tr></thead>`;
  function bookTable(account, rowAttrs) {
    const rows = P.open.filter((p) => p.account === account);
    return `<table class="pm-table">${bookHead}<tbody>${rows.map((p) => bookRow(p, rowAttrs ? rowAttrs(p) : '')).join('')}</tbody></table>`;
  }

  function detail(p) {
    const lots = p.lots.map((l) => `<tr><td>${esc(l.when)}</td><td class="pm-num">${l.qty}</td><td class="pm-num">${l.price.toFixed(2)}</td><td class="pm-num">${l.fees.toFixed(2)}</td><td>${prov(l.prov)}</td><td class="pm-dim">${esc(l.ref)}</td></tr>`).join('');
    const legs = p.legs.length ? p.legs.map((g) => `<tr><td>${g.seq}</td><td>${esc(g.side)}</td><td>${esc(g.type)}</td><td class="pm-num">${g.strike}</td><td class="pm-num">${g.price == null ? '<span class="pm-amber">unpriced</span>' : g.price.toFixed(2)}</td></tr>`).join('') : '';
    return `<div class="pm-detail">
      <h3>${esc(p.ticker)} · ${esc(p.structure)} ${prov(p.prov)}</h3>
      ${p.basisIncomplete ? `<div class="pm-note pm-warn">Basis under review — ${esc(p.basisIncomplete)}</div>` : ''}
      <div class="pm-kv">
        <div><span class="pm-k">Stop</span>${stopBadge(p.stop)}</div>
        <div><span class="pm-k">Time stop</span>${esc(p.timeStop)}</div>
        <div class="pm-wide"><span class="pm-k">Invalidation</span>${p.invalidation === 'not written' ? '<span class="pm-amber">not written</span>' : esc(p.invalidation)}</div>
        <div class="pm-wide"><span class="pm-k">Tags</span>${p.tags.length ? p.tags.map((t) => `<span class="pm-tag">${esc(t)}</span>`).join(' ') : '<span class="pm-dim">none</span>'}</div>
      </div>
      <h4>Lots</h4><table class="pm-table pm-sm"><thead><tr><th>When</th><th class="pm-num">Qty</th><th class="pm-num">Price</th><th class="pm-num">Fees</th><th>Provenance</th><th>Ref</th></tr></thead><tbody>${lots}</tbody></table>
      ${legs ? `<h4>Legs</h4><table class="pm-table pm-sm"><thead><tr><th>#</th><th>Side</th><th>Type</th><th class="pm-num">Strike</th><th class="pm-num">Price</th></tr></thead><tbody>${legs}</tbody></table>` : ''}
      <h4>Evidence <span class="pm-dim">(beside the verdict, #23)</span></h4><ul class="pm-evid">${p.evidence.map((e) => `<li>${esc(e)}</li>`).join('')}</ul>
    </div>`;
  }

  function actions(p) {
    const rolled = p.rolledFrom ? ` (follows #${p.rolledFrom})` : '';
    const A = [
      ['Edit', 'Change tags, stop, invalidation, time stop.', 'Needs: what changed and why (one line).', false],
      ['Add a lot', 'Record another fill into this position.', 'Needs: fill time, qty, price, fees — and a broker reference or a screen capture.', false],
      ['Close', 'End the position and record the result.', 'Needs: exit price, close time, and the closing fill reference (or screen capture). Result recomputed from lots.', false],
      ['Roll' + rolled, 'Close this and open the next as one linked trade.', 'Needs: both fills, linked. Waits on R-IV.452 — not landed.', true],
    ];
    return `<div class="pm-actions"><h4>Actions on ${esc(p.ticker)} #${p.id}</h4>${A.map(([n, d, need, off]) => `<div class="pm-act${off ? ' off' : ''}"><button type="button" class="pm-btn" ${off ? 'disabled' : ''}>${esc(n)}</button><div><div>${esc(d)}</div><div class="pm-need">${esc(need)}</div></div></div>`).join('')}</div>`;
  }

  function ticket() {
    const t = P.ticket;
    return `<form class="pm-ticket" onsubmit="return false"><h4>Pre-trade ticket <span class="pm-dim">— the only way a new position enters (X8)</span></h4>
      <div class="pm-tape">Tape: ${chip('reported', t.tape.state)} <span class="pm-dim">${esc(t.tape.detail)}</span></div>
      <label>Trade direction<select><option>bearish (with the tape)</option><option>bullish (AGAINST the tape)</option><option>neutral</option></select></label>
      <label>Bucket<select>${P.buckets.map(([n, d]) => `<option>${esc(n)}${d ? ' — ' + esc(d) : ''}</option>`).join('')}</select></label>
      <label>Ticker / structure<input value="e.g. IWM put debit spread 215/210"></label>
      <label>Max loss<input value="$120"></label>
      <div class="pm-caps">${chip('verified', 'within sleeve ceiling: headroom $556 (mock)')} ${chip('verified', 'cash stays above $200 (mock)')}</div>
      <label>Stop written<select><option>broker order</option><option>daily-close</option><option>none — say why</option></select></label>
      <label>Invalidation<input value="what makes this wrong"></label>
      <label>Time stop<input value="date or DTE"></label>
      <label>Zweig rule strained<select><option>none</option><option>the tape sets direction</option><option>another rule…</option></select></label>
      <div class="pm-need">A ticket saves onto the position row. A trade against the tape, or with no stop, shows amber above and asks for a reason before it can be submitted.</div>
      <button type="button" class="pm-btn primary">Save ticket &amp; enter position</button></form>`;
  }

  function history() {
    const h = P.history, c = h.coverage;
    const ex = c.excluded, flagged = ex.basis_incomplete + ex.return_below_neg100pct + ex.no_realized_pnl;
    const counted = h.rows.filter((r) => !r.flag && r.realized != null);
    const net = counted.reduce((s, r) => s + r.realized, 0);
    const wins = counted.filter((r) => r.realized > 0).length;
    const cov = chip(flagged ? 'reported' : 'verified', `n=${c.counted} of ${c.total}`, `${flagged} excluded, never averaged in: ${ex.basis_incomplete} basis incomplete, ${ex.return_below_neg100pct} return past −100% of basis`);
    const rows = h.rows.map((r) => `<tr class="${r.flag ? 'pm-flagged' : ''}"><td>#${r.id}</td><td><b>${esc(r.ticker)}</b> <span class="pm-dim">${esc(r.structure)}</span></td><td>${esc(r.closed)}</td><td class="pm-num">${r.realized == null ? '<span class="pm-amber">null</span>' : `<span class="${tone(r.realized)}">${usd(r.realized, true)}</span>`}</td><td>${esc(r.why)}${r.flag ? ' ' + chip('reported', r.flag) : ''}</td><td>${prov(r.prov)}</td></tr>`).join('');
    const chain = h.chains.map((k) => `<div class="pm-chain"><b>${esc(k.label)}</b> — ${k.legs.map((l) => l.open ? `#${l.id} <span class="pm-dim">open</span>` : `#${l.id} ${usd(l.realized, true)}`).join(' → ')} · <span class="${tone(k.net)}">${usd(k.net, true)}</span> <span class="pm-dim">${esc(k.note)}</span></div>`).join('');
    return `<div class="pm-history"><h4>History <span class="pm-dim">closed &amp; expired, windowed on close date</span></h4>
      <div class="pm-hstats"><span>Realized <b class="${tone(net)}">${usd(net, true)}</b> ${cov}</span><span>Win rate <b>${Math.round(wins / counted.length * 100)}%</b> <span class="pm-dim">n=${counted.length}</span> ${cov}</span></div>
      ${chain}<table class="pm-table"><thead><tr><th>#</th><th>Position</th><th>Closed</th><th class="pm-num">Realized</th><th>Why</th><th>Provenance</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function missing() {
    return `<details class="pm-missing"><summary>Endpoints and fields found missing (${P.missing.length})</summary><ul>${P.missing.map((m) => `<li>${esc(m)}</li>`).join('')}</ul>
      <div class="pm-dim">Exist today: list, summary, single, lots (list/add), legs (list/add/edit), verify / screen-verify, close, reduce, patch, correct-realized, closed-from-evidence.</div></details>`;
  }

  window.PMP = { ladder, buckets, esc, usd, prov, chip, mockBanner, gauge, bookTable, bookRow, bookHead, detail, actions, ticket, history, missing, sleeves: P.sleeves, open: P.open };
})();
