#!/usr/bin/env node
/**
 * R-IV.1257(b)2's pre-deploy gate: load /app?pop=v2 in headless Chrome, collect REAL console
 * errors and uncaught exceptions over CDP, and assert all nine pop-out sections rendered.
 *
 * THE COLLECTOR MOVED OUT. R-IV.1259(i) needed the same gate on a second surface, and a copied
 * gate is a second place for this one's original fault to come back: the first version scraped
 * Chrome's stderr for "ERROR:CONSOLE" and was VACUOUS, because Chrome logs every page console
 * message as `INFO:CONSOLE` regardless of severity. Only the positive control revealed it. The
 * browser driving, the CDP collector and that control now live in `scripts/lib/cdp_gate.js`
 * and both gates share them; this file is the pop-out's markers and nothing else.
 *
 * Usage: node scripts/check_pop_v2.js [baseUrl]
 * Exit 0 only when the control fires AND the page is clean AND all nine sections render.
 */
'use strict';

const { runGate } = require('./lib/cdp_gate');

// The nine sections (b)2 requires. A section may say "unavailable"; it may not be ABSENT.
const SECTIONS = {
  '1 hero': 'pv-hero',
  '2 ribbon': 'pv-ribbon',
  '3 lamps': 'pv-lamps',
  '4 flip meter': 'pv-flip',
  '5 credit': 'pv-credit',
  '6 breadth': 'pv-breadth',
  '7 leadership': 'pv-lead',
  '8 rates': 'pv-rates',
  '9 auction': 'pv-auction',
};

async function main() {
  const base = (process.argv[2] || 'https://pandoras-box-production.up.railway.app').replace(/\/$/, '');
  const ok = await runGate({
    url: base + '/app?pop=v2',
    markers: SECTIONS,
    settleMs: 9000,
    count: { 'sections reporting unavailable': 'pv-na' },
  });
  process.exit(ok ? 0 : 1);
}

main().catch((e) => { console.error('GATE ERROR: ' + e.message); process.exit(2); });
