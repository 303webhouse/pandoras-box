'use strict';
/**
 * The headless-load gate, shared. Extracted from scripts/check_pop_v2.js when R-IV.1259(i)
 * asked for the same gate on a second surface.
 *
 * WHY IT IS SHARED RATHER THAN COPIED. The first version of the pop-out gate scraped Chrome's
 * stderr for "ERROR:CONSOLE" and WAS VACUOUS: Chrome logs every page console message as
 * `INFO:CONSOLE` regardless of severity, so the filter could never have seen a page error and
 * a clean-looking PASS meant nothing. Only the positive control revealed it. A copied gate is
 * a second place for that fault to come back, in the copy nobody re-reads.
 *
 * So: the DevTools protocol, where `Runtime.consoleAPICalled` carries a real `type` and
 * `Runtime.exceptionThrown` is unambiguous. No dependency -- node 22+ has a global WebSocket.
 *
 * THE CONTROL RUNS FIRST, ALWAYS. `runGate` refuses to report on a page until it has caught
 * errors on a page built to produce them. A gate whose collector is dead reports every surface
 * as clean.
 */

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const CHROMES = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
];

function chromePath() {
  for (const p of CHROMES) if (fs.existsSync(p)) return p;
  throw new Error('no Chrome or Edge binary found; the headless gate cannot run');
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function withBrowser(fn) {
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cdpgate-'));
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

/** Open ONE page, navigate, and collect real console errors plus the settled DOM. */
function visit(browserWsUrl, url, settleMs) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(browserWsUrl);
    const errors = [];
    let id = 0;
    const pending = new Map();
    const send = (method, params, sid) => new Promise((res) => {
      const msgId = ++id;
      pending.set(msgId, res);
      ws.send(JSON.stringify({ id: msgId, method, params: params || {}, sessionId: sid }));
    });

    const fail = (e) => { try { ws.close(); } catch (_) {} reject(e); };
    const timer = setTimeout(() => fail(new Error('timed out driving the page')), 120000);

    ws.onerror = () => fail(new Error('could not connect to the debugger'));
    ws.onmessage = (ev) => {
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
        const sessionId = attached.sessionId;
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

/** The control page: console.error plus an uncaught throw. Written to temp each run. */
async function control(wsUrl) {
  const p = path.join(os.tmpdir(), 'cdpgate-control.html');
  fs.writeFileSync(p,
    '<!doctype html><title>control</title><script>'
    + "console.error('CONTROL console.error');"
    + "setTimeout(function(){ throw new Error('CONTROL throw'); }, 10);"
    + '</script>', 'utf8');
  return visit(wsUrl, 'file:///' + p.replace(/\\/g, '/'), 1200);
}

/**
 * Run one gate.
 *   url        the page to load
 *   markers    {label: substring} every one of which must appear in the settled DOM
 *   settleMs   how long to let the page run before reading it
 *   count      optional {label: substring} reported as counts, never asserted on
 * Returns true on PASS. The control is asserted first; a dead collector is a FAIL.
 */
async function runGate({ url, markers, settleMs, count }) {
  let bad = false;
  await withBrowser(async (wsUrl) => {
    const ctrl = await control(wsUrl);
    process.stdout.write('CONTROL: a page that errors ... ');
    if (!ctrl.errors.length) {
      console.log('NOT CAUGHT');
      console.log('  the collector is dead; every result below would be vacuous');
      bad = true;
      return;
    }
    console.log('caught ' + ctrl.errors.length + ', so the collector is live');

    console.log('LOADING ' + url);
    const page = await visit(wsUrl, url, settleMs || 9000);
    console.log('  dom bytes: ' + page.dom.length);

    if (page.errors.length) {
      bad = true;
      console.log('  CONSOLE ERRORS: ' + page.errors.length);
      page.errors.slice(0, 12).forEach((e) => console.log('    ' + e.slice(0, 220)));
    } else {
      console.log('  console errors: 0');
    }

    const missing = Object.entries(markers || {})
      .filter(([, m]) => !page.dom.includes(m))
      .map(([name]) => name);
    if (missing.length) {
      bad = true;
      console.log('  MISSING: ' + missing.join(', '));
    } else {
      console.log('  all ' + Object.keys(markers || {}).length + ' required marker(s) present');
    }
    for (const [label, m] of Object.entries(count || {})) {
      console.log('  ' + label + ': ' + (page.dom.split(m).length - 1));
    }
  });
  console.log('RESULT: ' + (bad ? 'FAIL' : 'PASS'));
  return !bad;
}

module.exports = { withBrowser, visit, control, runGate, chromePath };
