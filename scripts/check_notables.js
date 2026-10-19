#!/usr/bin/env node
/**
 * R-IV.1259(i)'s pre-deploy gate: load /app?notables=1 in headless Chrome, assert zero real
 * console errors, and assert the mock surface actually rendered.
 *
 * WHAT IT ASSERTS BEYOND "no errors". A page that silently fetched nothing has no console
 * error and no cards either, and "clean" would read as "working". So the markers cover the
 * block's own wrapper, the ticker helper's class, every card type, every state, and the MOCK
 * badge -- the badge especially, because an UNLABELLED mock on a page served from the live hub
 * is the one failure mode (i) is guarding against.
 *
 * Usage: node scripts/check_notables.js [baseUrl]
 * Exit 0 only when the control fires, the page is clean, and every marker is present.
 */
'use strict';

const { runGate } = require('./lib/cdp_gate');

const MARKERS = {
  'the NOTABLE block': 'nb-wrap',
  'the MOCK badge': 'nb-badge',
  'the ticker helper': 'nb-sym',
  'a card': 'nb-card',
  'the up/down tally': 'nb-tally',
  'counter-evidence': 'nb-against',
  'the stale line': 'nb-stale',
  'the option rung strip': 'nb-rungs',
  'the compact strip': 'nb-compact',
  'the pinned loud move': 'nb-loud',
  'a context strip': 'nb-ctxstrip',
  'the aging state': 'nb-aged',
  'the quiet-day state': 'nb-quiet',
  'the cap-reached state': 'nb-capline',
  'the states reference': 'nb-caption',
  'the your-book footer': 'nb-tilefoot',
};

async function main() {
  const base = (process.argv[2] || 'https://pandoras-box-production.up.railway.app').replace(/\/$/, '');
  const ok = await runGate({
    url: base + '/app?notables=1',
    markers: MARKERS,
    settleMs: 11000,
    count: { 'ticker symbols rendered': 'nb-sym', 'inert mock buttons': 'nb-btn' },
  });
  process.exit(ok ? 0 : 1);
}

main().catch((e) => { console.error('GATE ERROR: ' + e.message); process.exit(2); });
