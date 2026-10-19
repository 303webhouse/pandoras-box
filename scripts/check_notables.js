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

// R-IV.1259(i) step 2: `?notables=1` is now LIVE, so the markers below must be the ones a
// LIVE render produces. The mock-only ones -- the states gallery, the aging and quiet-day
// cards, the option rung strip -- moved to MOCK_MARKERS and are checked against
// `?notables=mock`, which is still served because it is what Nick approved and what the layout
// is judged against. Checking the live page for a mock marker would have been a gate that
// passes only while the page is still a mock.
const MOCK_MARKERS = {
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

// What a LIVE render must produce. Deliberately short: the live page shows the cards the tape
// actually made, and asserting a card type that nothing fired today would make the gate fail on
// a quiet market. So the markers are the FRAME -- the block, the live chip, the tally, the
// your-book footer -- plus the injected stylesheet. Those are present whatever the tape did,
// and their absence means the render broke.
const LIVE_MARKERS = {
  'the NOTABLE block': 'nb-wrap',
  'the LIVE chip': '>LIVE<',
  'the up/down tally': 'nb-tally',
  'the your-book footer': 'nb-tilefoot',
  'the injected stylesheet': 'nb-css',
};

async function main() {
  const base = (process.argv[2] || 'https://pandoras-box-production.up.railway.app').replace(/\/$/, '');
  const live = await runGate({
    url: base + '/app?notables=1',
    markers: LIVE_MARKERS,
    settleMs: 13000,
    count: {
      'live cards rendered': 'class="mono nb-sym"',
      'inputs not evaluated': 'input(s) not evaluated',
    },
  });
  console.log('');
  const ok = await runGate({
    url: base + '/app?notables=mock',
    markers: MOCK_MARKERS,
    settleMs: 11000,
    // COUNTED ON THE RENDERED ATTRIBUTE, not the bare class name. `runGate` counts substring
    // occurrences in the whole DOM, and the injected stylesheet contains `.nb-sym{…}` and
    // `.nb-btns{…}` too -- so counting "nb-sym" reported 9 symbols for 8 cards, and "nb-btn"
    // reported 8 buttons for 5. A count that includes its own CSS rule is a caption lying
    // about its field, however harmless the number.
    count: {
      'ticker symbols rendered': 'class="mono nb-sym"',
      'inert mock buttons': '<button class="nb-btn"',
    },
  });
  process.exit(live && ok ? 0 : 1);
}

main().catch((e) => { console.error('GATE ERROR: ' + e.message); process.exit(2); });
