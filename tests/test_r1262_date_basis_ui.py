r"""R-IV.1262(b) — the three display-only changes, in both engines.

Run it:   python tests/test_r1262_date_basis_ui.py            (Chromium)
          ENGINE=webkit python tests/test_r1262_date_basis_ui.py

WHAT IT GUARDS, and why each one needs a test rather than a look:

  R-IV.1270 UPDATE. `trade_date` is live, the realized window is `c.trade_date` alone, and the
  two undated closures are excluded and reported outside every total. So the (b)1 warning below is
  now EXPECTED TO BE ABSENT on live data, and the test that matters most is the one that was
  written for this moment: the label removes itself. Both states are still exercised, because the
  payload decides which one applies and a page that could only render the happy state would be
  untested the next time a backfill lags.

  (b)1  Every Abacus PERIOD figure states its date basis on its face, with the COUNT of rows whose
        write date and trade date differ. The count is in the visible label, not only a tooltip: a
        reader who must hover to learn that a figure is on the wrong date basis has been told
        nothing. The WITHHELD tile must NOT carry a basis -- there is no measurement behind it.
        And the whole treatment must DISAPPEAR BY ITSELF when `trade_date_exists` turns true, so
        that BUILD's column does not leave a stale warning behind to be hunted down.

  (b)2  A balance that is PARTIAL, and one that is absent, must not look like one that is known.
        The 0.00 the ruling names is `balance_stored`, which the route retired and does not serve;
        what it does serve for FID 401A is a DERIVED figure flagged `balance_partial` with a reason
        saying it understates the account. An understated balance read as whole is the same failure,
        so that is what is tested here, alongside a null rendering "not recorded" rather than $0.00.

  (b)3  Every mark-derived figure shows its mark's age -- the Mark cell AND the P&L, because the
        Book row has no mark column and its P&L IS the mark-derived figure. Four states are pinned:
        an age from `mark_as_of`, an age from `price_updated_at` (named as the fallback), "age
        unknown" where the hub served no time at all, and a row with no mark (which must keep
        saying "no mark", not "age unknown" -- they are different facts).

The page picks NO staleness threshold anywhere: the verdict word is the hub's (`mark_integrity`,
else `mark_status`). A test that asserted "26 hours is stale" would be asserting a judgement this
file is not allowed to make.
"""
import io
import json
import os
import subprocess
import sys
import threading
import http.server
import socketserver
from datetime import datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(REPO, 'frontend')

fails = []


def say(*parts):
    print(' '.join(str(p) for p in parts).encode('ascii', 'replace').decode('ascii'))


def check(n, c, x=''):
    say(('PASS ' if c else 'FAIL ') + n + (' >> ' + str(x)[:300] if x and not c else ''))
    if not c:
        fails.append(n)


# ── the parse test, first: a page that does not parse renders nothing at all ──────────────────
for name in ('abacus.js', 'v2.js'):
    r = subprocess.run(['node', '--check', os.path.join(ROOT, name)],
                       capture_output=True, text=True)
    check('parses: ' + name, r.returncode == 0, (r.stderr or '')[:300])

NOW = datetime.now(timezone.utc)


def iso(**kw):
    return (NOW - timedelta(**kw)).isoformat().replace('+00:00', 'Z')


BASIS = {
    'label': 'by the day each closure row was WRITTEN, not the day the trade closed',
    'trade_date_exists': False,
    'column': 'position_lot_closures.created_at',
    'mixed': True,
    'mixed_detail': 'A row with closures is placed by the day its closure was WRITTEN.',
    'closure_rows': 839, 'rows_differing': 803, 'rows_agreeing': 35, 'rows_no_exit_date': 1,
    'earliest_exit_in_ledger': '2025-12-11', 'written_from': '2026-09-23', 'written_to': '2026-10-15',
    'meaning': 'On 803 of 839 closure rows the two days differ.',
    'fix': "BUILD's trade_date column and POSITIONS' backfill.",
}
LIVE = {'source': 'live', 'computed_at': NOW.isoformat().replace('+00:00', 'Z')}
SPAN = {'from': '2026-09-01', 'to': '2026-10-19'}
COV = {'counted': 100, 'total': 110, 'excluded': {'basis_incomplete': 10}}


def stat(key, label, fmt, value, basis=True):
    d = {'key': key, 'label': label, 'format': fmt, 'value': value, 'n': 100,
         'span': SPAN, 'coverage': COV, 'meaning': label + ' means this.', **LIVE}
    if basis:
        d['date_basis'] = BASIS
    return d


SUMMARY = {
    'version': 1, 'mock': True, 'combined_is_pooled': True,
    'range': {'key': '90d', 'from': '2026-07-21', 'to': '2026-10-19', 'label': '90 days'},
    'range_applied': True,
    'scope': {'label': 'Robinhood - FID ROTH - FID 401A', 'closed_positions': 110,
              'accounts': 3, **LIVE},
    'date_basis': BASIS,
    'accounts_date_basis': BASIS,
    'stats': [
        stat('net_profit', 'Net profit', 'usd', 1234.56),
        stat('win_rate', 'Win rate', 'pct', 0.51),
        stat('expectancy', 'Expectancy', 'usd', 11.22),
        stat('profit_factor', 'Profit factor', 'ratio', 1.3),
        stat('avg_win_loss', 'Average win / loss', 'usd', 40.0),
        stat('expected_return', 'Expected return per trade', 'pct', 0.02),
        # WITHHELD: no figure, so no basis. If this one ever grows a basis chip the page is
        # claiming a measurement it has explicitly taken down (R-IV.716(c)).
        {'key': 'loss_vs_risk', 'label': 'Loss vs risk', 'format': 'pct', 'value': None,
         'n': None, 'unavailable': 'max loss not reliable yet', 'span': SPAN,
         'meaning': 'Withheld: the max loss field is unreliable.', **LIVE},
    ],
    'accounts': [
        {'account': 'ROBINHOOD', 'account_display': 'Robinhood', 'net_profit': 211.53,
         'win_rate': 0.5, 'win_rate_n': 40, 'expected_return': 0.01,
         'expected_return_n': 38, 'coverage': COV},
        {'account': 'FIDELITY_ROTH', 'account_display': 'FID ROTH', 'net_profit': -422.82,
         'win_rate': 0.4, 'win_rate_n': 30, 'expected_return': -0.02,
         'expected_return_n': 29, 'coverage': COV},
    ],
    'equity': {'accounts': [], 'computed_at': LIVE['computed_at'], 'source': 'live'},
    'leaks': {'items': [], 'partly_live': True, **LIVE},
    'strategies': {'note': 'No figures yet.', 'source': 'mock',
                   'computed_at': '2026-01-01T00:00:00Z'},
    'breakdowns': [
        {'key': 'structure', 'label': 'By structure', 'columns': [['Structure', 'text']],
         'rows': [['vertical', 1]], 'note': 'n is the counted closes.', 'date_basis': BASIS, **LIVE},
        {'key': 'discipline', 'label': 'By discipline', 'columns': [['Rule', 'text']],
         'rows': [['stop honoured', 1]], 'note': 'Sample data.', 'source': 'mock',
         'computed_at': '2026-01-01T00:00:00Z'},
    ],
    'realized_fallback': {'count': 0, 'rows': []}, 'realized_excluded_no_date': [],
    # R-IV.1270(b). Two rows, both Robinhood expiries, outside every total.
    'realized_dating': {'basis': 'position_lot_closures.trade_date', 'note': 'the broker action date'},
    'realized_date_unknown': {
        'count': 2, 'total': -57.26, 'in_any_total': False,
        'by_account': {'ROBINHOOD': -57.26},
        'rows': [
            {'closure_id': 1942, 'position_id': 'POS_IWM_20261006_R652', 'ticker': 'IWM',
             'status': 'EXPIRED', 'account': 'ROBINHOOD', 'account_display': 'Robinhood',
             'realized': -13.08},
            {'closure_id': 1943, 'position_id': 'POS_NVDA_20261008_171815', 'ticker': 'NVDA',
             'status': 'EXPIRED', 'account': 'ROBINHOOD', 'account_display': 'Robinhood',
             'realized': -44.18},
        ],
        'note': 'closures with no trade_date, so no window can place them.',
    },
}

# Three accounts, one of each state the chips must tell apart.
BALANCES = [
    {'account_name': 'ROBINHOOD', 'account_display': 'Robinhood', 'broker': 'robinhood',
     'balance': 1635.42, 'in_scope': True, 'balance_source': 'derived'},
    {'account_name': 'FIDELITY_401A', 'account_display': 'FID 401A', 'broker': 'fidelity',
     'balance': 11346.92, 'in_scope': True, 'balance_source': 'derived',
     'balance_partial': True,
     'balance_reason': '2 position(s) could not be valued, so this figure is PARTIAL and understates the account'},
    {'account_name': 'FIDELITY_ROTH', 'account_display': 'FID ROTH', 'broker': 'fidelity',
     'balance': None, 'in_scope': True, 'balance_source': 'stored'},
]

# One row per mark-age state. `open_quantity`/`cost_basis` are present so the cells render.
POSITIONS = [
    {'id': 1, 'position_id': 'P_AS_OF', 'account': 'FIDELITY_ROTH', 'account_display': 'FID ROTH',
     'ticker': 'GUSH', 'asset_type': 'stock', 'structure': 'stock', 'open_quantity': 10,
     'cost_basis': 100.0, 'current_price': 49.73, 'mark': 49.73, 'mark_status': 'OK',
     'mark_as_of': iso(minutes=20), 'price_updated_at': iso(minutes=45),
     'mark_integrity': 'ok', 'mark_integrity_reason': 'quote within band',
     'unrealized_pnl': 12.5, 'provenance': 'IMPORTED'},
    {'id': 2, 'position_id': 'P_PRICE_ONLY', 'account': 'ROBINHOOD', 'account_display': 'Robinhood',
     'ticker': 'BX', 'asset_type': 'option', 'structure': 'long_put', 'open_quantity': 8,
     'cost_basis': 66.32, 'current_price': 0.4, 'mark_status': 'STALE',
     'price_updated_at': iso(days=4), 'mark_reason': 'no quote since Thursday',
     'unrealized_pnl': -30.0, 'provenance': 'IMPORTED'},
    {'id': 3, 'position_id': 'P_NO_TIME', 'account': 'ROBINHOOD', 'account_display': 'Robinhood',
     'ticker': 'VIX', 'asset_type': 'option', 'structure': 'long_call', 'open_quantity': 2,
     'cost_basis': 20.0, 'current_price': 1.1, 'mark_status': 'OK',
     'unrealized_pnl': 3.0, 'provenance': 'IMPORTED'},
    {'id': 4, 'position_id': 'P_NO_MARK', 'account': 'ROBINHOOD', 'account_display': 'Robinhood',
     'ticker': 'SQQQ', 'asset_type': 'stock', 'structure': 'stock', 'open_quantity': 5,
     'cost_basis': 50.0, 'mark_reason': 'no vendor price for this ticker',
     'provenance': 'IMPORTED'},
]


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def translate_path(self, path):
        return os.path.join(ROOT, path.split('?')[0].lstrip('/') or 'v2.html')


srv = socketserver.TCPServer(('127.0.0.1', 0), H)
port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d/' % port


def route(r):
    u = r.request.url

    def j(o, s=200):
        r.fulfill(status=s, content_type='application/json', body=json.dumps(o))

    if '/api/abacus/summary' in u:
        return j(SUMMARY)
    if '/api/v2/positions' in u:
        return j({'positions': POSITIONS, 'count': len(POSITIONS)})
    if '/api/portfolio/balances' in u:
        return j(BALANCES)
    if '/api/portfolio/cash-balance' in u:
        return j({'accounts': {}})
    if '/api/trade-ideas/notices' in u:
        return j({'notices': []})
    if '/api/trade-ideas' in u:
        return j({'signals': [], 'total': 0, 'limit': 50, 'offset': 0})
    if '/api/bias/composite' in u:
        return j({'bias_level': 'NEUTRAL', 'composite_score': 0.1})
    if '/api/board/levels/' in u:
        return j({'ticker': 'X', 'available': False, 'levels': None})
    if '/api/flow/radar' in u:
        return j({'position_flow': [], 'watchlist_unusual': [], 'headlines': []})
    if '/api/hermes/alerts' in u:
        return j({'alerts': []})
    if '/api/stable/enrich' in u:
        return j({'enrichment': {}})
    return j({}, 404)


def open_page(b, path):
    ctx = b.new_context(viewport={'width': 1440, 'height': 1200})
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))

    bad_assets = []

    def console(m):
        # The headless CONSOLE CHECK. Filtered on the stack's ORIGIN, never on the message text:
        # a third-party widget's own errors are not this page's, and matching on wording is how a
        # real error gets filtered out by accident.
        #
        # ONE EXCEPTION, and it is a category not a wording: "Failed to load resource" is the
        # browser reporting an HTTP STATUS, not script going wrong, and this suite's own stub
        # answers 404 on purpose for endpoints these pages never use. Those are counted below as
        # assets instead, where a real 404 on a real asset still fails the run.
        if m.type != 'error':
            return
        if 'Failed to load resource' in m.text:
            return
        loc = (m.location or {}).get('url') or ''
        if loc and '127.0.0.1' not in loc:
            return
        errs.append('console: ' + m.text[:160])

    def response(r):
        u = r.url
        # The suite 404s  on purpose, exactly as the R-IV.900 suite does:
        # it is a build artefact that does not exist in a checkout. Named here rather than matched
        # loosely, so a 404 on anything else still fails.
        if '127.0.0.1' not in u or '/api/' in u or u.endswith('stable_digest.md'):
            return
        if r.status >= 400:
            bad_assets.append('%s %s' % (r.status, u.split('127.0.0.1')[-1][:70]))

    pg.on('console', console)
    pg.on('response', response)
    pg.route('**/api/**', route)
    pg.route('**/stable_digest.md', lambda r: r.fulfill(status=404, body=''))
    pg.goto(BASE + path, wait_until='domcontentloaded')
    pg.wait_for_timeout(2400)
    return pg, ctx, errs, bad_assets


with sync_playwright() as p:
    ENGINE = os.environ.get('ENGINE', 'chromium')
    say('engine: ' + ENGINE)
    b = getattr(p, ENGINE).launch()

    # ── (b)1 · ABACUS ───────────────────────────────────────────────────────────
    # R-IV.1356 made the P&L view the DEFAULT, so `abacus.html` with no query no longer
    # renders the summary page these checks are about. They ask for it explicitly now.
    # THIS SUITE WENT RED AT R-IV.1356 AND I DID NOT NOTICE, because I ran the R-IV.1315
    # suite and the backend tests that turn and not this one. A test that is not run is
    # not a test; the lesson is to run every suite the change can reach, not the ones the
    # change was written against.
    pg, ctx, errs, assets = open_page(b, 'abacus.html?view=summary')
    tiles = pg.evaluate("""() => [...document.querySelectorAll('.ab-stat')].map((e) => ({
        key: e.dataset.key, basis: e.dataset.basis || null, text: e.textContent,
        chips: [...e.querySelectorAll('.ab-chip')].map((c) => c.textContent.trim()) }))""")
    live_keys = ['net_profit', 'win_rate', 'expectancy', 'profit_factor', 'avg_win_loss',
                 'expected_return']
    got = {t['key']: t for t in tiles}
    check('every live period tile rendered', all(k in got for k in live_keys), sorted(got))
    missing = [k for k in live_keys
               if not any('by write date' in c for c in got.get(k, {}).get('chips', []))]
    check('every live period tile states its date basis ON ITS FACE', not missing, missing)
    nocount = [k for k in live_keys
               if not any('803 of 839 rows differ' in c for c in got.get(k, {}).get('chips', []))]
    check('...and the COUNT is in the visible label, not only the tooltip', not nocount, nocount)
    check('...and the tile is marked for styling/selection', got.get('net_profit', {}).get('basis') == 'write-date',
          got.get('net_profit'))
    check('the WITHHELD tile carries NO basis, having no measurement behind it',
          not any('by write date' in c for c in got.get('loss_vs_risk', {}).get('chips', [])),
          got.get('loss_vs_risk'))

    note = pg.evaluate("() => (document.querySelector('#abAccountsNote') || {}).textContent || ''")
    check('the per-account card says the basis in full', 'dated by when the row was' in note, note[:160])
    check('...naming the count and the span the ledger was written over',
          '803 of 839' in note and 'written between' in note, note[:200])
    check('...and keeps the pooled sentence beside it', 'pooled' in note, note[:120])

    # R-IV.1270(b): MONEY NO WINDOW CAN PLACE must be on the page, with its count and its money,
    # and must say it is outside every total. A count on its own would not answer the question a
    # reader actually has, which is how much money is unplaced.
    note = pg.evaluate("() => (document.querySelector('#abAccountsNote') || {}).textContent || ''")
    check('the date-unknown money is on the page, with its count', 'Date unknown: 2 rows' in note,
          note[:240])
    check('...and its total', '-$57.26' in note or '\u2212$57.26' in note, note[:240])
    check('...and says it is outside every figure, in every range',
          'Outside every figure' in note and 'every range' in note, note[:240])
    check('...and names the rows that hold it',
          'IWM' in note and 'NVDA' in note, note[:300])

    panels = pg.evaluate("""() => [...document.querySelectorAll('.ab-panel-chip')].map(
        (e) => e.textContent)""")
    check('a live breakdown panel states the basis',
          any('by write date' in t for t in panels), panels)
    check('the SAMPLE-DATA breakdown does not claim a measured basis',
          sum(1 for t in panels if 'by write date' in t) < len(panels), panels)

    head = pg.evaluate("() => (document.querySelector('#abAsof') || {}).textContent || ''")
    check('the page header states the basis too', 'by write date' in head, head[:160])
    check('abacus: no console errors and no page errors', not errs, errs)
    check('abacus: every page asset loaded', not assets, assets)

    ctx.close()

    # THE TREATMENT MUST VANISH BY ITSELF once a real trade date exists -- tested end to end,
    # because the day BUILD's column lands, nobody should have to hunt a stale warning down.
    for d in [BASIS] + [b.get('date_basis') for b in SUMMARY['breakdowns'] if b.get('date_basis')]:
        d['trade_date_exists'] = True
    pg, ctx, errs, assets = open_page(b, 'abacus.html?view=summary')
    body = pg.evaluate("() => document.body.textContent || ''")
    check('once trade_date exists the basis treatment is GONE from the page',
          'by write date' not in body and 'dated by when the row was' not in body,
          [t for t in body.split('\n') if 'write date' in t][:2])
    check('...and the figures are still there', 'Net profit' in body, body[:120])
    # R-IV.1270(b): the warning going away must NOT take the unplaced money with it. They are
    # different claims -- "these figures are on the wrong date" and "this money is on no date" --
    # and the second outlives the first.
    check('...and the date-unknown money SURVIVES the label removing itself',
          'Date unknown: 2 rows' in body, body[:200])
    check('...with no console errors on that path', not errs, errs)
    for d in [BASIS] + [b2.get('date_basis') for b2 in SUMMARY['breakdowns'] if b2.get('date_basis')]:
        d['trade_date_exists'] = False
    ctx.close()

    # ── (b)2 and (b)3 · AGORA ───────────────────────────────────────────────────
    #
    # R-IV.1442(b): RE-POINTED, NOT RETIRED. These checks were written against the BOOK tile's
    # `.acct-chip`s and `.book-line`, and against the Positions panel's per-cell "... old" chips.
    # R-IV.1369 replaced that tile with account rows, and R-IV.1382 moved the mark's age into ONE
    # AGE cell that carries R-IV.1262(b)3 for both MARK and P&L on its row (R-IV.1382(d)4). The old
    # layouts live on only under ?clean=off / ?pos=v1 until 2026-11-06. The RULES are unchanged, so
    # each check now reads the screen Nick actually sees. They went red when #78 and #80 shipped
    # and nobody here ran this file; R-IV.1437(c)1 now requires all five root scripts before a push.
    pg, ctx, errs, assets = open_page(b, 'v2.html')
    rows = pg.evaluate("""() => [...document.querySelectorAll('#bookStrip .bk-acct:not(.bk-cash)')].map((r) => ({
        name: ((r.querySelector('.bk-an b') || {}).textContent || '').trim(),
        val: ((r.querySelector('.bk-av') || {}).textContent || '').trim(),
        nr: (r.querySelector('.bk-nr') || {}).title || '',
        floor: (r.querySelector('.bk-floor') || {}).title || '' }))""")
    none_row = [r for r in rows if r['name'] == 'FID ROTH']
    part_row = [r for r in rows if r['name'] == 'FID 401A']
    check('an account with NO balance renders "not recorded", never $0.00',
          len(none_row) == 1 and 'not recorded' in none_row[0]['val']
          and '0.00' not in none_row[0]['val'], rows)
    check('...and says why in its title', none_row and 'no balance recorded' in none_row[0]['nr'], none_row)
    check('a PARTIAL balance is marked as a floor, not shown as a whole figure',
          len(part_row) == 1 and part_row[0]['val'].count('≥') == 1, part_row)
    check('...carrying the hub\'s own reason', part_row and 'understates' in part_row[0]['floor'], part_row)
    tot = pg.evaluate("""() => { const t = document.querySelector('#bookStrip .bk-total');
        const f = t && t.querySelector('.bk-floor');
        return { text: t ? t.textContent.trim() : null, title: f ? f.title : '' }; }""")
    check('the Balance TOTAL is a floor while any part is partial or absent',
          bool(tot['text']) and tot['text'].startswith('≥') and 'floor' in tot['title'].lower(), tot)
    ctx.close()

    # The Positions panel opened by its `#positions` address. Cells are read BY COLUMN of the
    # R-IV.1382 table: TICKER WHAT QTY MARK AGE P&L DAYS.
    AGE_CELLS = """() => { const out = {};
      document.querySelectorAll('.pp-panel tr.pq-row').forEach((tr) => {
        const td = [...tr.cells];
        const key = ['GUSH', 'BX', 'VIX', 'SQQQ'].find((k) => (tr.textContent || '').indexOf(k) >= 0);
        if (!key) return;
        const c = (k) => { const e = td[k]; if (!e) return { text: '', title: '', amber: false };
          return { text: e.textContent.trim(),
                   title: [e.getAttribute('title') || ''].concat([...e.querySelectorAll('[title]')].map((x) => x.getAttribute('title'))).join(' | '),
                   amber: e.classList.contains('amb') || !!e.querySelector('.pq-amb') }; };
        out[key] = { mark: c(3), age: c(4), pnl: c(5), row: tr.textContent };
      }); return out; }"""
    pg, ctx, errs2, assets2 = open_page(b, 'v2.html#positions')
    pg.wait_for_timeout(1200)
    cells = pg.evaluate(AGE_CELLS)
    errs += errs2
    assets += assets2
    check('the positions panel opened and drew a row per stubbed position',
          sorted(cells) == ['BX', 'GUSH', 'SQQQ', 'VIX'], sorted(cells))
    import re as _re0
    g = cells.get('GUSH') or {}
    ga = g.get('age') or {}
    check('(b)3 a mark with `mark_as_of` shows its age', bool(_re0.match(r'^\d+ min$', ga.get('text', ''))), g)
    check('...naming mark_as_of as the clock it used', 'own instant' in ga.get('title', ''), ga)
    check('...and the age shows even though the mark is FRESH (rule 1 of the draft)',
          bool(_re0.match(r'^\d+ min$', ga.get('text', ''))) and not ga.get('amber'), ga)
    check('...and the P&L drawn from it shares that row\'s one AGE cell (R-IV.1382(d)4)',
          bool(g.get('pnl', {}).get('text')) and bool(ga.get('text')), g)
    x = cells.get('BX') or {}
    xa = x.get('age') or {}
    check('a row with only `price_updated_at` still shows an age', bool(_re0.match(r'^\d+ d$', xa.get('text', ''))), xa)
    check('...and says it is the PRICE\'s clock, not the mark\'s', 'not the mark' in xa.get('title', ''), xa)
    check('...and keeps the hub\'s own STALE verdict beside it (amber, the hub\'s word in its title)',
          xa.get('amber') and 'STALE' in xa.get('title', ''), xa)
    check('...and its P&L shares that age cell, which is the whole point',
          bool(x.get('pnl', {}).get('text')) and bool(xa.get('text')), x)
    v = cells.get('VIX') or {}
    va = v.get('age') or {}
    check('a priced row with NO time reads "age unknown"', va.get('text') == 'age unknown', va)
    check('...and says that is not the same as having no price', 'not the same as having no price' in va.get('title', ''), va)
    q = cells.get('SQQQ') or {}
    check('a row with no mark says "no price" (R-IV.1382\'s word), not "age unknown"',
          'no price' in q.get('mark', {}).get('text', '') and 'age unknown' not in q.get('row', ''), q)
    check('...and its row shows no age at all, having no price to age', q.get('age', {}).get('text') == '—', q)
    ctx.close()

    # CONTROL: the ?pos=v1 rollback still keeps (b)3 in ITS layout -- the per-cell chips -- until
    # 2026-11-06. One check, so the rollback cannot quietly lose the rule while it is still live.
    pg, ctx, errs3, assets3 = open_page(b, 'v2.html?pos=v1#positions')
    pg.wait_for_timeout(1200)
    v1 = pg.evaluate("""() => { const tr = [...document.querySelectorAll('.pp-panel tr')].find((r) => (r.textContent || '').indexOf('GUSH') >= 0);
        return tr ? tr.textContent : ''; }""")
    check('?pos=v1 control: the rollback panel still shows the mark\'s age per cell', 'min old' in v1, v1[:160])
    errs += errs3
    assets += assets3

    # THE PAGE PICKS NO THRESHOLD (R-IV.943(c)): "stale" is the hub's word, and this file renders
    # the verdict it was given. Asserted on the SOURCE of the two functions, which is where such a
    # rule would have to live -- an earlier version of this check looked for "26" in the rendered
    # text and matched a cost basis and a year, passing and failing for reasons unrelated to the
    # rule. A proxy that can match anything proves nothing.
    src = io.open(os.path.join(ROOT, 'v2.js'), encoding='utf-8').read()
    fn = src[src.index('function markAge(p)'):src.index('function markCell(p)')]
    import re as _re
    # COMMENTS ARE STRIPPED FIRST (R-IV.1442(b)): a ruling cited in prose -- "R-IV.1382(d)4" --
    # is not a threshold, and it was the only thing this scan found after #80. The scan tests
    # code; a number in a string is still code, and is still caught.
    code = _re.sub(r'/\*.*?\*/', '', fn, flags=_re.S)
    code = _re.sub(r'//[^\n]*', '', code)
    nums = [n for n in _re.findall(r'\b\d+\b', code) if n not in ('0', '1', '60', '1440', '60000')]
    check('no staleness threshold is hard-coded in the age code', not nums, nums)
    check('...and the verdict word comes from the hub\'s own fields',
          'mark_integrity' in src and 'MARK_VERDICT' in src, '')
    check('agora: no console errors and no page errors', not errs, errs)
    check('agora: every page asset loaded', not assets, assets)
    ctx.close()
    b.close()

say('')
say('%d checks failed' % len(fails))
for f in fails:
    say('  - ' + f)
sys.exit(1 if fails else 0)
