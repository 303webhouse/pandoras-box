"""R-IV.1382 -- the Positions panel, redesigned. Desktop, narrow panel, and phone.

Run:  python tests/test_r1382_positions.py            (ENGINE=webkit for the WebKit pass)

EVERY FIXTURE HERE IS INVENTED: accounts, balances, positions, lots, legs, cash and earnings are
synthetic, because the repo is public and the real book must never be committed (R-IV.1382(c)).
Widths: 1920 (a 960px panel: two columns), 1440 (720px: one column), 360/384/412 (phone).
"""
import io
import json
import os
import re
import sys
import threading
import http.server
import socketserver

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(REPO, 'frontend')
fails = []


def say(*p):
    print(' '.join(str(x) for x in p).encode('ascii', 'replace').decode('ascii'))


def check(n, c, x=''):
    say(('PASS ' if c else 'FAIL ') + n + (' >> ' + str(x)[:300] if x and not c else ''))
    if not c:
        fails.append(n)


JS = io.open(os.path.join(ROOT, 'v2.js'), encoding='utf-8').read()
CSS = io.open(os.path.join(ROOT, 'assets', 'positions-clean.css'), encoding='utf-8').read()
HTML = io.open(os.path.join(ROOT, 'v2.html'), encoding='utf-8').read()
css_code = re.sub(r'/\*.*?\*/', '', CSS, flags=re.S)
check('positions-clean.css carries no hex literal (D6)', not re.findall(r'#[0-9a-fA-F]{3,8}\b', css_code))
check('positions-clean.css loads after v2.css', 0 < HTML.find('/v2.css?v=') < HTML.find('/assets/positions-clean.css?v='))
check('the ?pos=v1 rollback and its date are written down', "get('pos') === 'v1'" in JS and '2026-11-06' in JS)

# ── synthetic fixtures ───────────────────────────────────────────────────────────────────
BAL = [
    {'account_name': 'ACCT_A', 'account_display': 'Account A', 'balance': 2141.0, 'balance_partial': True,
     'balance_reason': 'synthetic partial', 'balance_cash': 1520.0, 'balance_positions_counted': 3,
     'balance_positions_unvalued': ['POS_2'], 'in_scope': True, 'cash_anchor': {'as_of': '2026-09-24', 'as_of_is_instant': False}},
    {'account_name': 'ACCT_B', 'account_display': 'Account B', 'balance': 11830.0, 'balance_partial': False,
     'balance_cash': 8315.0, 'balance_positions_counted': 2, 'balance_positions_unvalued': [], 'in_scope': True,
     'cash_anchor': {'as_of': '2026-09-24', 'as_of_is_instant': False}},
    {'account_name': 'ACCT_C', 'account_display': 'Account C', 'balance': 11700.0, 'balance_partial': False,
     'balance_cash': 9030.0, 'balance_positions_counted': 1, 'balance_positions_unvalued': [], 'in_scope': True,
     'cash_anchor': {'as_of': '2026-09-24', 'as_of_is_instant': False}},
]


def row(i, acct, tkr, struct, asset, expiry, dte, qty, mark, pnl, status='OK', prov='IMPORTED', strikes=(None, None), bucket=None):
    return {'id': 700 + i, 'position_id': 'POS_%d' % i, 'ticker': tkr, 'account': acct,
            'account_display': {'ACCT_A': 'Account A', 'ACCT_B': 'Account B', 'ACCT_C': 'Account C'}[acct],
            'asset_type': asset, 'structure': struct, 'status': 'OPEN', 'expiry': expiry, 'dte': dte,
            'open_quantity': qty, 'open_quantity_basis': 'lots' if qty is not None else 'unknown: the position has no lots',
            'quantity': 9, 'cost_basis': 345.0, 'current_price': mark, 'unrealized_pnl': pnl,
            'unrealized_pnl_pct': (pnl / 345.0 * 100) if pnl is not None else None,
            'mark_status': status if mark is not None else None, 'mark_reason': 'synthetic reason',
            'price_updated_at': '2026-10-24T20:00:00Z' if mark is not None else None,
            'mark_checked_at': '2026-10-24T20:02:00Z', 'provenance': prov,
            'long_strike': strikes[0], 'short_strike': strikes[1], 'strategy_tag': bucket, 'tags': [],
            'derived': {}}


OPEN = [
    row(1, 'ACCT_A', 'KRE', 'long_put', 'OPTION', '2026-12-18', 56, 3, 0.95, -60.0, strikes=(58, None), bucket='B1'),
    row(2, 'ACCT_A', 'QQQ', 'put_debit_spread', 'OPTION', '2026-11-20', 28, 1, None, None, strikes=(560, 550)),
    row(3, 'ACCT_A', 'XLF', 'put_debit_spread', 'OPTION', '2026-11-20', 28, 6, 0.42, 54.0, strikes=(50, 47)),
    row(4, 'ACCT_A', 'AMD', 'put_debit_spread', 'OPTION', '2026-11-20', 28, None, 0.30, 12.0, status='STALE', strikes=(220, 210)),
    row(5, 'ACCT_B', 'VTI', 'stock', 'EQUITY', None, None, 4, 306.5, 66.0),
    row(6, 'ACCT_B', 'XLU', 'stock', 'EQUITY', None, None, 8, 85.1, 21.0),
    row(7, 'ACCT_C', 'GDXJ', 'stock', 'EQUITY', None, None, 4, 86.5, 14.0),
]
CASH = {'accounts': {
    'ACCT_A': {'derived': {'derivable': True, 'balance': 1520.0, 'movement_since_opening': 1048.41,
                           'by_type': {'TRANSFER_IN': 1500.0, 'TRADE_DEBIT': -451.59},
                           'anchor': {'kind': 'broker_figure', 'as_of': '2026-09-24T23:55:39Z', 'as_of_is_instant': True}}},
    'ACCT_B': {'derived': {'derivable': True, 'balance': 8315.0, 'movement_since_opening': 0,
                           'anchor': {'kind': 'statement', 'as_of': '2026-09-24', 'as_of_is_instant': False}}},
    'ACCT_C': {'derived': {'derivable': True, 'balance': 9030.0, 'movement_since_opening': 0,
                           'anchor': {'kind': 'statement', 'as_of': '2026-09-24', 'as_of_is_instant': False}}},
}}
EARN = {'earnings': {'AMD': {'date': '2026-11-04', 'timing': 'AMC'},
                     'XLF': {'date': '2026-11-10', 'timing': 'BMO', 'component': 'JPM', 'is_etf': True},
                     'KRE': {'date': '2027-01-20', 'timing': 'BMO'}}}
LOTS = {'lots': [{'fill_time': '2026-10-02T00:00:00Z', 'qty': 3, 'price': 1.15, 'fees': 0.12, 'provenance': 'IMPORTED',
                  'broker_ref': 'SYN-REF-1'}], 'agrees_with_stored': True, 'derived': {'qty': 3}, 'stored_quantity': 3}
LEGS = {'legs': [{'leg_seq': 1, 'side': 'LONG', 'option_type': 'PUT', 'strike': 58, 'qty': 3, 'price': 0.95}]}
SEEN = []


def route(r):
    u = r.request.url
    SEEN.append(u)

    def j(o, s=200):
        r.fulfill(status=s, content_type='application/json', body=json.dumps(o))

    if '/api/portfolio/balances' in u:
        return j(BAL)
    if '/api/portfolio/cash-balance' in u:
        return j(CASH)
    if '/api/portfolio/pnl' in u:
        return j({'daily': {'dollar': None}, 'accounts_partial': ['ACCT_A']})
    if '/api/chronos/next-earnings-batch' in u:
        return j(EARN)
    if re.search(r'/api/v2/positions/POS_\d+/lots', u):
        return j(LOTS)
    if re.search(r'/api/v2/positions/POS_\d+/legs', u):
        return j(LEGS)
    if '/api/v2/positions/greeks' in u:
        return j({'status': 'ok', 'totals': {}, 'coverage': None})
    if '/api/v2/positions' in u:
        if 'status=OPEN' in u:
            return j({'positions': OPEN, 'count': len(OPEN), 'cache_age_seconds': 5})
        return j({'positions': [], 'count': 0})
    if '/api/abacus/summary' in u:
        return j({'stats': [], 'range': {'key': 'all'}})
    return j({}, 404)


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def translate_path(self, p):
        return os.path.join(ROOT, p.split('?')[0].lstrip('/') or 'v2.html')


srv = socketserver.TCPServer(('127.0.0.1', 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d/' % srv.server_address[1]
SHOTDIR = os.environ.get('SHOTDIR')


def page(b, w, h, q='', hashpart=''):
    ctx = b.new_context(viewport={'width': w, 'height': h}, is_mobile=w < 500, has_touch=w < 500)
    pg = ctx.new_page()
    errs = []

    def own(e):
        st = getattr(e, 'stack', '') or ''
        if 'tradingview' in st.lower() and '127.0.0.1' not in st:
            return
        errs.append('pageerror: ' + str(e))
    pg.on('pageerror', own)
    pg.route('**/api/**', route)
    pg.route('**/stable_digest.md', lambda r: r.fulfill(status=404, body=''))
    pg.goto(BASE + 'v2.html' + q + hashpart, wait_until='domcontentloaded')
    pg.wait_for_timeout(2600)
    return pg, ctx, errs


def open_panel(pg):
    pg.evaluate("() => { const b = document.getElementById('bookPanelBtn'); if (b) b.click(); }")
    pg.wait_for_selector('.pp-panel.open', timeout=8000)
    pg.wait_for_timeout(900)


def shot(pg, name):
    if SHOTDIR:
        os.makedirs(SHOTDIR, exist_ok=True)
        pg.screenshot(path=os.path.join(SHOTDIR, name + '.png'))


TAPS = """() => [...document.querySelectorAll('.pp-panel button')].filter((b) => { const r = b.getBoundingClientRect();
  const s = getComputedStyle(b); return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden'
  && !b.closest('details'); }).filter((b) => b.getBoundingClientRect().height < 44)
  .map((b) => (b.textContent||'').trim().slice(0,18) + ' ' + Math.round(b.getBoundingClientRect().height))"""
SMALL = """() => { const out = []; document.querySelectorAll('.pp-panel *').forEach((e) => {
  if (e.children.length || !(e.textContent || '').trim() || e.closest('details') || e.closest('.pq-info')) return;
  const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return;
  const r = e.getBoundingClientRect(); if (!r.width) return;
  const px = parseFloat(s.fontSize); if (px && px < 12) out.push((e.textContent||'').trim().slice(0,18) + ' @' + px); });
  return out.slice(0, 6); }"""

with sync_playwright() as p:
    ENGINE = os.environ.get('ENGINE', 'chromium')
    say('engine: ' + ENGINE)
    b = getattr(p, ENGINE).launch()

    # ══ DESKTOP, a 960px panel: two columns ═════════════════════════════════════════════
    pg, ctx, errs = page(b, 1920, 1080)
    open_panel(pg)
    d = pg.evaluate("""() => { const q = (s) => document.querySelector(s), t = (s) => ((q(s) || {}).innerText || '').replace(/\\s+/g, ' ').trim();
      const bh = (s) => { const e = q(s); return e ? Math.round(e.getBoundingClientRect().height) : null; };
      return { pq: !!q('.pp-panel.pq'), head: t('.pq-head'), banner: !!q('.pp-panel > .pp-banner') || /Live from the hub/.test(t('.pq-body')),
        ib: bh('.pq-ib'), x: bh('.pq-x'), panelW: Math.round(q('.pp-panel').getBoundingClientRect().width),
        accts: [...document.querySelectorAll('.pq-acct')].map((a) => ({ t: a.innerText.replace(/\\s+/g, ' ').trim(), p: a.getAttribute('aria-pressed'),
          amber: !!a.querySelector('.bk-floor, .pq-amb') })),
        tabs: [...document.querySelectorAll('.pq-tabs [role=tab]')].map((x) => x.innerText.replace(/\\s+/g, ' ').trim()),
        add: t('.pq-add'), cols: [...document.querySelectorAll('.pq-table thead .pq-sort')].map((x) => x.innerText.trim()),
        groups: [...document.querySelectorAll('.pq-gbtn')].map((x) => x.innerText.replace(/\\s+/g, ' ').trim()),
        rows: [...document.querySelectorAll('.pq-row')].map((r) => [...r.cells].map((c) => c.innerText.trim())),
        side: !!q('.pq-side'), glance: t('.pq-side'), dot: (() => { const e = q('.pq-row .pq-dot'); return e ? Math.round(e.getBoundingClientRect().width) : null; })() }; }""")
    check('desktop: the redesigned panel is the DEFAULT (.pq)', d['pq'], d)
    check('desktop: header is POSITIONS + a live chip; the banner is NOT on the face', 'live' in d['head'].lower() and not d['banner'], d['head'])
    check('desktop: the ⓘ and the ✕ are both 44px', d['ib'] == 44 and d['x'] == 44, (d['ib'], d['x']))
    check('desktop: the panel stays 50vw (960 at 1920)', d['panelW'] == 960, d['panelW'])
    names = [a['t'] for a in d['accts']]
    check('desktop: "All accounts" first, then one button per in-scope account, names NOT uppercased',
          len(names) == 4 and names[0].startswith('All accounts') and 'Account A' in names[1] and 'ACCOUNT' not in ' '.join(names), names)
    check('desktop: a partial account shows the amber ≥ floor (the BOOK tile\'s own rule)',
          '≥$2,141' in names[1] and d['accts'][1]['amber'], names[1])
    check('desktop: line 3 is the server cash TO THE CENT and the open count', 'cash $1,520.00 · 4 open' in names[1], names[1])
    check('desktop: All accounts reads "floor only - N open" when the total is a floor', 'floor only · 7 open' in names[0], names[0])
    check('desktop: All accounts is pressed by default', d['accts'][0]['p'] == 'true', d['accts'][0])
    check('desktop: tabs OPEN (count) - CLOSED - CASH and "+ Add position"',
          [x.upper() for x in d['tabs']] == ['OPEN 7', 'CLOSED', 'CASH'] and 'ADD POSITION' in d['add'].upper(), (d['tabs'], d['add']))
    check('desktop: columns TICKER WHAT QTY MARK AGE P&L DAYS, DAYS sorted ascending',
          [c.replace(' ▴', '').upper() for c in d['cols']] == ['TICKER', 'WHAT', 'QTY', 'MARK', 'AGE', 'P&L', 'DAYS']
          and d['cols'][-1].endswith('▴'), d['cols'])
    check('desktop: grouped by account in accountsOf order', [g.split(' ')[0] + ' ' + g.split(' ')[1] for g in d['groups']] == ['Account A', 'Account B', 'Account C'], d['groups'])
    check('desktop: a group with an unpriced row says "N NO PRICE" and shows NO sum', 'no price' in d['groups'][0].lower()
          and '$' not in d['groups'][0], d['groups'][0])
    check('desktop: a group where every row has a P&L shows its sum', '+$87' in d['groups'][1], d['groups'][1])
    tick = [r[0] for r in d['rows']]
    check('desktop: soonest expiry first, no-expiry last, ties by P&L descending', tick[:4] == ['XLF', 'AMD', 'QQQ', 'KRE'], tick)
    rows = {r[0]: r for r in d['rows']}
    check('desktop: WHAT reads "Put spread 50/47 - Nov 20"; equity reads "Shares"',
          rows['XLF'][1] == 'Put spread 50/47 · Nov 20' and rows['VTI'][1] == 'Shares', (rows['XLF'][1], rows['VTI'][1]))
    check('desktop: QTY "unknown" when open_quantity is null (never the opening quantity)', rows['AMD'][2] == 'unknown', rows['AMD'])
    check('desktop: MARK "no price" and P&L "—" when the hub served none', rows['QQQ'][3] == 'no price' and rows['QQQ'][5] == '—', rows['QQQ'])
    check('desktop: MARK carries no $ sign', rows['XLF'][3] == '0.42', rows['XLF'][3])
    check('desktop: AGE reads as minutes/hours/days, "—" with no price', re.match(r'^(<1 min|\d+ (min|h|d))$', rows['XLF'][4])
          and rows['QQQ'][4] == '—', (rows['XLF'][4], rows['QQQ'][4]))
    check('desktop: the provenance dot is 7px (the .pp-chip ::before)', d['dot'] == 7, d['dot'])
    check('desktop: the right column is AT A GLANCE when nothing is picked', d['side'] and 'AT A GLANCE' in d['glance'].upper(), d['glance'][:80])
    check('desktop: needs-a-look names the unpriced account rows', '1 Account A position has no price' in d['glance'], d['glance'])
    check('desktop: an earnings date on/before expiry is listed; an ETF names its HOLDING',
          'AMD reports earnings before its Nov 20 expiry' in d['glance'] and 'JPM, held in XLF' in d['glance']
          and 'KRE reports' not in d['glance'], d['glance'])
    check('desktop: the Day P&L card is the BOOK tile\'s, waiting while a position is unpriced',
          'Day P&L' in d['glance'] and 'waits until every position has a price' in d['glance'], d['glance'])
    check('desktop: Expirations counts positions per expiry, then shares',
          'Nov 20 · 28 days' in d['glance'] and 'Shares, no expiry 3' in d['glance'], d['glance'])
    check('desktop: earnings is ONE batch call per panel open', sum(1 for u in SEEN if 'next-earnings-batch' in u) == 1,
          sum(1 for u in SEEN if 'next-earnings-batch' in u))
    shot(pg, 'pq-1920-list')
    # ⓘ: what moved, nothing deleted.
    pg.click('.pq-ib'); pg.wait_for_timeout(200)
    info = pg.evaluate("() => (document.querySelector('.pq-info') || {}).innerText || ''")
    check('desktop: the ⓘ holds the banner, the legend, the GAPS, the broker_ref note, Edit and Roll',
          'Live from the hub' in info and 'Provenance' in info and 'What this panel still cannot show' in info
          and 'broker_ref' in info and 'Edit' in info and 'Roll' in info, info[:200])
    pg.click('.pq-ib'); pg.wait_for_timeout(150)
    # Sort and fold.
    pg.click('[data-pq-sort="days"]'); pg.wait_for_timeout(150)
    lab = pg.evaluate("() => document.querySelector('[data-pq-sort=\"days\"]').innerText")
    check('desktop: clicking the active column flips it to ▾', lab.endswith('▾'), lab)
    pg.click('[data-pq-sort="days"]'); pg.wait_for_timeout(150)
    pg.click('[data-pq-fold="ACCT_B"]'); pg.wait_for_timeout(150)
    fold = pg.evaluate("() => ({ vti: !![...document.querySelectorAll('.pq-row')].find((r) => r.innerText.includes('VTI')), "
                       "ls: localStorage.getItem('pq-folds-v1') })")
    check('desktop: a group header folds its rows and REMEMBERS it', not fold['vti'] and 'ACCT_B' in (fold['ls'] or ''), fold)
    pg.click('[data-pq-fold="ACCT_B"]'); pg.wait_for_timeout(150)
    # Account filter.
    pg.click('[data-pq-acct="ACCT_B"]'); pg.wait_for_timeout(200)
    f = pg.evaluate("() => ({ rows: [...document.querySelectorAll('.pq-row b')].map((x) => x.textContent), "
                    "p: document.querySelector('[data-pq-acct=\"ACCT_B\"]').getAttribute('aria-pressed') })")
    check('desktop: an account button filters the list to that account (aria-pressed)', f['p'] == 'true' and sorted(f['rows']) == ['VTI', 'XLU'], f)
    pg.click('[data-pq-acct=""]'); pg.wait_for_timeout(200)
    # Show them / No price chip.
    pg.click('[data-pq-noprice]'); pg.wait_for_timeout(200)
    npv = pg.evaluate("() => ({ rows: [...document.querySelectorAll('.pq-row b')].map((x) => x.textContent), chip: !!document.querySelector('[data-pq-clear-noprice]') })")
    check('desktop: "Show them" filters to the unpriced rows, with a "No price ✕" chip', npv['rows'] == ['QQQ'] and npv['chip'], npv)
    pg.click('[data-pq-clear-noprice]'); pg.wait_for_timeout(200)
    # Pick a row.
    pg.click('.pq-row:has-text("KRE")'); pg.wait_for_timeout(900)
    k = pg.evaluate("""() => { const q = (s) => document.querySelector(s), t = (s) => ((q(s) || {}).innerText || '').replace(/\\s+/g, ' ').trim();
      const tk = q('.pq-ptk'), ts = tk ? getComputedStyle(tk) : {};
      return { sel: !!q('.pq-row.sel'), back: t('.pq-side .pq-back'), tk: tk ? tk.textContent : null, font: ts.fontFamily, px: ts.fontSize,
        sub: t('.pq-psub'), chips: t('.pq-pchips'), stats: [...document.querySelectorAll('.pq-stat')].map((s) => s.innerText.replace(/\\s+/g, ' ').trim()),
        acts: [...document.querySelectorAll('.pq-acts .pq-ab')].map((a) => [a.innerText.trim(), Math.round(a.getBoundingClientRect().height)]),
        kv: [...document.querySelectorAll('.pq-kv')].map((x) => x.innerText.replace(/\\s+/g, ' ').trim()),
        lots: t('.pq-side'), maxloss: /max loss/i.test(document.querySelector('.pp-panel').innerText) }; }""")
    check('desktop: a picked row stays lit and its detail sits in the right column', k['sel'] and k['back'] == '← At a glance', k['back'])
    check('desktop: the picked ticker is Orbit at --tile-hero (32px)', k['tk'] == 'KRE' and 'Orbit' in (k['font'] or '') and k['px'] == '32px', (k['font'], k['px']))
    check('desktop: "<structure strikes> - <Mon D> - x<qty>"', k['sub'] == 'Long put 58 · Dec 18 · ×3', k['sub'])
    check('desktop: chips are provenance, account, and the bucket with its note', 'imported' in k['chips'] and 'Account A' in k['chips']
          and 'B1 · multi-week thesis' in k['chips'], k['chips'])
    check('desktop: four stat cards: Cost, Mark - age, P&L with its %, Days left',
          len(k['stats']) == 4 and k['stats'][0].startswith('Cost') and k['stats'][1].startswith('Mark ·')
          and '%' in k['stats'][2] and k['stats'][3] == 'Days left 56', k['stats'])
    check('desktop: CLOSE, ADD, CHART as three equal 44px buttons', [a[0] for a in k['acts']] == ['CLOSE', 'ADD', 'CHART']
          and all(a[1] >= 44 for a in k['acts']), k['acts'])
    check('desktop: facts are Earnings, Theme and Exit plan ("not captured yet")',
          k['kv'][0].startswith('Earnings') and k['kv'][1].startswith('Theme') and k['kv'][2] == 'Exit plan not captured yet', k['kv'])
    check('desktop: LOTS "N - M with a broker reference", a day as written, the reference on line 2',
          '1 · 1 with a broker reference' in k['lots'] and 'Oct 2 · 3 at 1.15' in k['lots'] and 'SYN-REF-1' in k['lots'], k['lots'][:300])
    check('desktop: LEGS read "<side> <type> <strike> - x<qty>"', 'Long put 58 · ×3' in k['lots'], k['lots'][-200:])
    check('desktop: no max-loss figure anywhere on the panel (R-IV.719(c))', not k['maxloss'])
    shot(pg, 'pq-1920-picked')
    pg.click('.pq-acts [data-pq-act="close"]'); pg.wait_for_timeout(600)
    modal = pg.evaluate("() => { const m = [...document.querySelectorAll('.pos-modal')].find((e) => getComputedStyle(e).display !== 'none'); return m ? m.innerText.slice(0, 80) : null; }")
    check('desktop: CLOSE opens the Book module\'s own close form, with the raw row', modal is not None and 'KRE' in modal, modal)
    # Escape must close the FORM's world, not the panel under it: the panel stays open.
    pg.keyboard.press('Escape'); pg.wait_for_timeout(200)
    check('desktop: Escape with the Close form open does NOT close the panel underneath', pg.evaluate("() => !!document.querySelector('.pp-panel.open')"))
    pg.evaluate("() => { const c = document.getElementById('c_cancel'); if (c) c.click(); }"); pg.wait_for_timeout(300)
    # CLOSED loads only when opened; CASH rows.
    before = sum(1 for u in SEEN if 'status=CLOSED' in u)
    pg.click('[data-pq-view="closed"]'); pg.wait_for_timeout(700)
    after = sum(1 for u in SEEN if 'status=CLOSED' in u)
    check('desktop: CLOSED loads only when it is opened', before == 0 and after == 1, (before, after))
    pg.click('[data-pq-view="cash"]'); pg.wait_for_timeout(500)
    c = pg.evaluate("""() => ({ rows: [...document.querySelectorAll('.pq-crow')].map((r) => r.innerText.replace(/\\s+/g, ' ').trim()),
      foot: (document.querySelector('.pq-cfoot') || {}).innerText || '', hash: location.hash })""")
    check('desktop: CASH has one row per account: name and cash to the cent on one line',
          len(c['rows']) == 3 and c['rows'][0].startswith('Account A $1,520.00'), c['rows'][:1])
    check('desktop: the source line and the movement join on line 2',
          'Set from your broker figure' in c['rows'][0] and '+$1,048.41 from deposits, trades since' in c['rows'][0], c['rows'][0])
    check('desktop: CASH footer, and #positions/cash', 'replaces the hub’s cash' in c['foot'] and c['hash'] == '#positions/cash', (c['foot'], c['hash']))
    pg.click('.pq-crow [data-cash-open="flow"]'); pg.wait_for_timeout(300)
    form = pg.evaluate("() => { const f = document.querySelector('.pq-cash .pp-cashform'); return f ? { acct: !!f.querySelector('[data-cf=acct]'), "
                       "type: !!f.querySelector('[data-cf=type]'), date: !!f.querySelector('[data-cf=date]'), note: !!f.querySelector('[data-cf=note]') } : null; }")
    check('desktop: the cash form opens under its own row with no Account picker', form and not form['acct'] and form['type'] and form['date'] and form['note'], form)
    check('desktop 1920: no errors', not errs, errs)
    ctx.close()

    # ══ ADDRESSES, the BOOK doorways, and the tile ═══════════════════════════════════════
    for (h, want) in (('#positions/closed', 'closed'), ('#positions/history', 'closed'), ('#positions/cash', 'cash'), ('#positions/new', 'open')):
        pg, ctx, errs = page(b, 1920, 1080, hashpart=h)
        v = pg.evaluate("() => (document.querySelector('.pq-tabs [aria-selected=true]') || {}).dataset ? document.querySelector('.pq-tabs [aria-selected=true]').dataset.pqView : null")
        check('address %s opens %s' % (h, want.upper()), v == want, v)
        ctx.close()
    pg, ctx, errs = page(b, 1920, 1080, hashpart='#positions/701')
    check('address #positions/<id> opens the picked row', pg.evaluate("() => (document.querySelector('.pq-ptk') || {}).textContent") == 'KRE')
    ctx.close()
    pg, ctx, errs = page(b, 1920, 1080)
    tile = pg.evaluate("() => ({ list: document.getElementById('bookPositions').hidden, fold: !!document.getElementById('bookFoldBtn') })")
    check('BOOK: the in-tile list has LEFT the tile for Positions (Close is in the panel now)', tile['list'] is True and not tile['fold'], tile)
    pg.click('.bk-acct[data-bk-acct="ACCT_C"]'); pg.wait_for_timeout(900)
    door = pg.evaluate("() => ({ p: (document.querySelector('[data-pq-acct=\"ACCT_C\"]') || {}).getAttribute ? document.querySelector('[data-pq-acct=\"ACCT_C\"]').getAttribute('aria-pressed') : null, "
                       "rows: [...document.querySelectorAll('.pq-row b')].map((x) => x.textContent) })")
    check('BOOK: an account row opens Positions filtered to that account', door['p'] == 'true' and door['rows'] == ['GDXJ'], door)
    ctx.close()
    pg, ctx, errs = page(b, 1920, 1080)
    pg.click('.bk-cash'); pg.wait_for_timeout(900)
    check('BOOK: the cash row opens the CASH tab', pg.evaluate("() => document.querySelector('.pq-tabs [aria-selected=true]').dataset.pqView") == 'cash')
    ctx.close()

    # ══ A NARROW PANEL (1440 -> 720px): one column ═══════════════════════════════════════
    pg, ctx, errs = page(b, 1440, 900)
    open_panel(pg)
    n = pg.evaluate("() => ({ side: !!document.querySelector('.pq-side'), strip: !!document.querySelector('.pq-gstrip'), table: !!document.querySelector('.pq-table') })")
    check('1440: one column -- no side column, AT A GLANCE as a one-line strip above the table', not n['side'] and n['strip'] and n['table'], n)
    shot(pg, 'pq-1440-list')
    pg.click('.pq-row:has-text("XLF")'); pg.wait_for_timeout(700)
    n2 = pg.evaluate("() => ({ table: !!document.querySelector('.pq-table'), back: ((document.querySelector('.pq-back') || {}).innerText || '').trim() })")
    check('1440: a picked row opens IN PLACE of the list, with "← All positions"', not n2['table'] and n2['back'] == '← All positions', n2)
    pg.click('.pq-back'); pg.wait_for_timeout(300)
    check('1440: "← All positions" returns to the list', pg.evaluate("() => !!document.querySelector('.pq-table')"))
    check('1440: no errors', not errs, errs)
    ctx.close()

    # ══ PHONE ════════════════════════════════════════════════════════════════════════════
    for (w, h) in ((360, 780), (384, 832), (412, 915)):
        pg, ctx, errs = page(b, w, h)
        open_panel(pg)
        ph = pg.evaluate("""() => { const q = (s) => document.querySelector(s);
          const strip = q('.pq-strip'), body = q('.pp-panel .pp-body'), plus = q('.pq-addp');
          const rows = [...document.querySelectorAll('.pq-prow')];
          return { live: !!q('.pq-live'), stripScroll: strip.scrollWidth > strip.clientWidth, acctW: Math.round(q('.pq-acct').getBoundingClientRect().width),
            bodyOver: body.scrollWidth - body.clientWidth, plus: plus ? [Math.round(plus.getBoundingClientRect().height), plus.getAttribute('aria-label')] : null,
            rowH: rows.length ? Math.min(...rows.map((r) => Math.round(r.getBoundingClientRect().height))) : null, nrows: rows.length,
            glance: !!q('.pq-gstrip') }; }""")
        check('%dpx: header has the live dot with its age' % w, ph['live'], ph)
        check('%dpx: the account strip scrolls sideways INSIDE itself, 138px buttons' % w, ph['stripScroll'] and ph['acctW'] == 138, ph)
        check('%dpx: no sideways scroll in the panel body' % w, ph['bodyOver'] <= 1, ph['bodyOver'])
        check('%dpx: a 44px "+" labelled "Add position"' % w, ph['plus'] == [44, 'Add position'], ph['plus'])
        check('%dpx: rows are at least 56px, two lines' % w, ph['nrows'] == 7 and ph['rowH'] >= 56, (ph['nrows'], ph['rowH']))
        check('%dpx: the one-line needs-a-look strip' % w, ph['glance'])
        check('%dpx: every tap target in the panel is at least 44px' % w, not pg.evaluate(TAPS), pg.evaluate(TAPS))
        tiny = pg.evaluate(SMALL)
        check('%dpx: no text in the panel under 12px' % w, not tiny, tiny)
        # The last row is reachable and not covered.
        last = pg.evaluate("""() => { const b = document.querySelector('.pp-panel .pp-body'); b.scrollTop = b.scrollHeight;
          const r = [...document.querySelectorAll('.pq-prow')].pop().getBoundingClientRect();
          const at = document.elementFromPoint(Math.round(r.left + r.width / 2), Math.round(r.top + r.height / 2));
          return { onRow: !!(at && at.closest('.pq-prow')), bottom: Math.round(r.bottom), vh: window.innerHeight }; }""")
        check('%dpx: the last row is on screen and nothing covers it' % w, last['onRow'] and last['bottom'] <= last['vh'], last)
        if w == 360:
            shot(pg, 'pq-360-list')
        pg.evaluate("() => { const b = document.querySelector('.pp-panel .pp-body'); b.scrollTop = 0; }")
        pg.click('.pq-prow:has-text("KRE")'); pg.wait_for_timeout(800)
        sh = pg.evaluate("() => ({ sheet: !!document.querySelector('.pq-sheet'), strip: !!document.querySelector('.pq-strip'), hash: location.hash, "
                         "back: ((document.querySelector('.pq-sheet .pq-back') || {}).innerText || '').trim() })")
        check('%dpx: a tapped row opens as a full-panel sheet with ← back' % w, sh['sheet'] and not sh['strip'] and sh['back'] == '← All positions', sh)
        if w == 360:
            shot(pg, 'pq-360-sheet')
        pg.go_back(); pg.wait_for_timeout(700)
        gb = pg.evaluate("() => ({ sheet: !!document.querySelector('.pq-sheet'), open: !!document.querySelector('.pp-panel.open'), list: document.querySelectorAll('.pq-prow').length })")
        check('%dpx: the back gesture closes the sheet and keeps the panel open' % w, not gb['sheet'] and gb['open'] and gb['list'] == 7, gb)
        pg.click('.pq-prow:has-text("XLF")'); pg.wait_for_timeout(600)
        pg.click('.pq-sheet [data-pq-act="close"]'); pg.wait_for_timeout(700)
        top = pg.evaluate("""() => { const m = [...document.querySelectorAll('.pos-modal')].find((e) => getComputedStyle(e).display !== 'none');
          if (!m) return null; const r = m.getBoundingClientRect(); const at = document.elementFromPoint(Math.round(r.left + r.width / 2), Math.round(r.top + 60));
          return { onModal: !!(at && at.closest('.pos-modal')) }; }""")
        check('%dpx: the Close form opens ABOVE the panel, not under it' % w, top and top['onModal'], top)
        check('%dpx: no errors' % w, not errs, errs)
        ctx.close()

    # ══ ROLLBACK ═════════════════════════════════════════════════════════════════════════
    pg, ctx, errs = page(b, 1920, 1080, '?pos=v1')
    open_panel(pg)
    rb = pg.evaluate("() => ({ pq: !!document.querySelector('.pp-panel.pq'), banner: !!document.querySelector('.pp-banner'), "
                     "fold: !!document.getElementById('bookFoldBtn') })")
    check('?pos=v1 restores today\'s panel, and the tile\'s folded list comes back with it', not rb['pq'] and rb['banner'] and rb['fold'], rb)
    check('?pos=v1: no errors', not errs, errs)
    ctx.close()
    b.close()

say('')
say('%d checks failed' % len(fails))
for f in fails:
    say('  - ' + f)
sys.exit(1 if fails else 0)
