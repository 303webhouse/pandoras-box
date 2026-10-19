#!/usr/bin/env node
/**
 * R-IV.1257(b)2's pre-deploy gate: load /app?pop=v2 in headless Chrome, collect REAL console
 * errors and uncaught exceptions over CDP, and assert all nine pop-out sections rendered.
 *
 * WHY CDP AND NOT --dump-dom. The first version of this gate scraped Chrome's stderr for
 * "ERROR:CONSOLE". ITS POSITIVE CONTROL REFUSED TO FIRE, which is the only reason the gate is
 * not vacuous: Chrome logs EVERY page console message as `INFO:CONSOLE` regardless of
 * severity, so the filter could never have seen a page error, and a clean-looking PASS would
 * have meant nothing. Chrome's own stderr also carries `ERROR:` lines about GCM registration
 * and policy managers that have nothing to do with the page — this repo has already shipped a
 * guard that counted log lines and reported six errors when the truth was zero.
 *
 * So: the DevTools protocol, where `Runtime.consoleAPICalled` carries a real `type` and
 * `Runtime.exceptionThrown` is unambiguous. No dependency — node 22+ has a global WebSocket.
 *
 * Usage: node scripts/check_pop_v2.js [baseUrl]
 * Exit 0 only when the control fires AND the page is clean AND all nine sections render.
 */
'use strict';

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const CHROMES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
];

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

function chromePath() {
  for (const p of CHROMES) if (fs.existsSync(p)) return p;
  throw new Error('no Chrome or Edge binary found; the headless gate cannot run');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function withBrowser(fn) {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'popv2-'));
  const port = 9222 + Math.floor(Math.random() * 500);
  const proc = spawn(chromePath(), [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--mute-audio',
    '--no-first-run', '--no-default-browser-check',
    '--disable-features=Translate,MediaRouter,OptimizationHints',
    '--user-data-dir=' + profile,
    '--remote-debugging-port=' + port,
    'about:blank',
  ], { stdio: ['ignore', 'ignore', 'ignore'] });
  try {
    let target = null;
    for (let i = 0; i < 60 && !target; i++) {
      await sleep(250);
      try {
        const r = await fetch('http://127.0.0.1:' + port + '/json/version');
        if (r.ok) target = (await r.json()).webSocketDebuggerUrl;
      } catch (_) { /* not up yet */ }
    }
    if (!target) throw new Error('headless Chrome did not open a debugger port');
    return await fn(target);
  } finally {
    proc.kill();
    try { fs.rmSync(profile, { recursive: true, force: true }); } catch (_) {}
  }
}

/** Open ONE page, navigate, and collect errors + the settled DOM. */
function visit(browserWsUrl, url, settleMs) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(browserWsUrl);
    const errors = [];
    let id = 0;
    const pending = new Map();
    let sessionId = null;
    const send = (method, params, sid) => new Promise((res) => {
      const msgId = ++id;
      pending.set(msgId, res);
      ws.send(JSON.stringify({ id: msgId, method, params: params || {}, sessionId: sid }));
    });

    const fail = (e) => { try { ws.close(); } catch (_) {} reject(e); };
    const timer = setTimeout(() => fail(new Error('timed out driving the page')), 120000);

    ws.onerror = () => fail(new Error('could not connect to the debugger'));
    ws.onmessage = async (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (_) { return; }
      if (msg.id && pending.has(msg.id)) { pending.get(msg.id)(msg.result || {}); pending.delete(msg.id); return; }
      if (msg.method === 'Runtime.consoleAPICalled' && msg.params) {
        // The REAL severity, which stderr scraping could not see.
        if (msg.params.type === 'error' || msg.params.type === 'assert') {
          errors.push('console.' + msg.params.type + ': '
            + (msg.params.args || []).map((a) => a.value || a.description || a.type).join(' '));
        }
      }
      if (msg.method === 'Runtime.exceptionThrown' && msg.params) {
        const d = msg.params.exceptionDetails || {};
        errors.push('uncaught: ' + (d.exception && (d.exception.description || d.exception.value)
          || d.text || 'unknown'));
      }
    };

    ws.onopen = async () => {
      try {
        const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
        const attached = await send('Target.attachToTarget', { targetId, flatten: true });
        sessionId = attached.sessionId;
        await send('Runtime.enable', {}, sessionId);
        await send('Page.enable', {}, sessionId);
        await send('Page.navigate', { url }, sessionId);
        await sleep(settleMs);
        const dom = await send('Runtime.evaluate', {
          expression: 'document.documentElement.outerHTML', returnByValue: true,
        }, sessionId);
        clearTimeout(timer);
        ws.close();
        resolve({ dom: (dom.result && dom.result.value) || '', errors });
      } catch (e) { clearTimeout(timer); fail(e); }
    };
  });
}

async function main() {
  const base = process.argv[2] || 'https://pandoras-box-production.up.railway.app';
  const url = base.replace(/\/$/, '') + '/app?pop=v2';
  let bad = false;

  await withBrowser(async (wsUrl) => {
    // THE CONTROL FIRST. A page that throws and logs console.error must be caught, or every
    // result below is vacuous. The previous gate failed exactly here, and that is the whole
    // reason it was rewritten.
    const ctrlPath = path.join(os.tmpdir(), 'popv2-control.html');
    fs.writeFileSync(ctrlPath,
      '<!doctype html><title>control</title><script>'
      + "console.error('CONTROL console.error');"
      + "setTimeout(function(){ throw new Error('CONTROL throw'); }, 10);"
      + '</script>', 'utf8');
    const ctrl = await visit(wsUrl, 'file:///' + ctrlPath.replace(/\\/g, '/'), 1200);
    process.stdout.write('CONTROL: a page that errors ... ');
    if (!ctrl.errors.length) {
      console.log('NOT CAUGHT');
      console.log('  the collector is dead; every result below would be vacuous');
      bad = true;
      return;
    }
    console.log('caught ' + ctrl.errors.length + ', so the collector is live');

    console.log('LOADING ' + url);
    const page = await visit(wsUrl, url, 9000);
    console.log('  dom bytes: ' + page.dom.length);

    if (page.errors.length) {
      bad = true;
      console.log('  CONSOLE ERRORS: ' + page.errors.length);
      page.errors.slice(0, 12).forEach((e) => console.log('    ' + e.slice(0, 220)));
    } else {
      console.log('  console errors: 0');
    }

    const missing = Object.entries(SECTIONS)
      .filter(([, marker]) => !page.dom.includes(marker))
      .map(([name]) => name);
    if (missing.length) {
      bad = true;
      console.log('  SECTIONS MISSING: ' + missing.join(', '));
    } else {
      console.log('  all 9 sections rendered');
    }
    const na = (page.dom.match(/pv-na/g) || []).length;
    console.log('  sections reporting unavailable: ' + na);
  });

  console.log('RESULT: ' + (bad ? 'FAIL' : 'PASS'));
  process.exit(bad ? 1 : 0);
}

main().catch((e) => { console.error('GATE ERROR: ' + e.message); process.exit(2); });
