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
    pg, ctx, errs, assets = open_page(b, 'abacus.html')
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
    pg, ctx, errs, assets = open_page(b, 'abacus.html')
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
    pg, ctx, errs, assets = open_page(b, 'v2.html')
    chips = pg.evaluate("""() => [...document.querySelectorAll('.acct-chip')].map((e) => ({
        cls: e.className, text: e.textContent.trim(), title: e.getAttribute('title') || '' }))""")
    none_chip = [c for c in chips if 'acct-chip-none' in c['cls']]
    part_chip = [c for c in chips if 'acct-chip-partial' in c['cls']]
    check('an account with NO balance renders "not recorded", never $0.00',
          len(none_chip) == 1 and 'not recorded' in none_chip[0]['text']
          and '0.00' not in none_chip[0]['text'], none_chip)
    check('...and says why in its title', none_chip and 'no balance recorded' in none_chip[0]['title'],
          none_chip)
    check('a PARTIAL balance is marked as a floor, not shown as a whole figure',
          len(part_chip) == 1 and part_chip[0]['text'].count('≥') == 1, part_chip)
    check('...carrying the hub\'s own reason', part_chip and 'understates' in part_chip[0]['title'],
          part_chip)
    bal = pg.evaluate("""() => {
        const l = [...document.querySelectorAll('.book-line')].find(
            (e) => (e.textContent || '').indexOf('Balance') === 0);
        return l ? l.textContent.trim() : null; }""")
    check('the Balance TOTAL is a floor while any part is partial or absent',
          bal and '≥' in bal and 'floor only' in bal, bal)

    ctx.close()

    # The positions panel has its own doorway: the `#positions` address (v2.js:5429). Opening it
    # renders the Book table from the stubbed payload, so the cells under test are the ones the
    # principal actually sees -- not functions called in isolation.
    pg, ctx, errs, assets = open_page(b, 'v2.html#positions')
    pg.wait_for_timeout(1200)
    cells = pg.evaluate("""() => {
      const out = {};
      document.querySelectorAll('tr').forEach((tr) => {
        const t = (tr.textContent || '');
        const cellOf = (i) => {
          const td = tr.querySelectorAll('td')[i];
          return td ? {text: td.textContent.trim(),
                       titles: [...td.querySelectorAll('[title]')].map((e) => e.getAttribute('title')).join(' | ')}
                    : null; };
        const tds = tr.querySelectorAll('td');
        if (!tds.length) return;
        const key = ['GUSH', 'BX', 'VIX', 'SQQQ'].find((k) => t.indexOf(k) >= 0);
        if (!key) return;
        const all = [...tds].map((td) => ({text: td.textContent.trim(),
          titles: [...td.querySelectorAll('[title]')].map((e) => e.getAttribute('title')).join(' | ')}));
        out[key] = all;
      });
      return out; }""")
    check('the positions panel opened and drew a row per stubbed position',
          sorted(cells) == ['BX', 'GUSH', 'SQQQ', 'VIX'], sorted(cells))

    def cellpair(key):
        """The Mark cell and the P&L cell of a row, found by content rather than by index: a
        column order this test hard-codes is a test that breaks when a column is added."""
        tds = cells.get(key) or []
        blob = ' '.join(c['text'] + ' ' + c['titles'] for c in tds)
        mark = next((c for c in tds if 'old' in c['text'] or 'no mark' in c['text']
                     or 'age unknown' in c['text'] or 'stale mark' in c['text']), None)
        pnl = next((c for c in tds if 'no P&L' in c['text']
                    or (('$' in c['text'] or '-' in c['text']) and c is not mark
                        and ('old' in c['text'] or 'unknown' in c['text']))), None)
        return blob, (mark or {'text': '', 'titles': ''}), (pnl or {'text': '', 'titles': ''})

    gush, g_mark, g_pnl = cellpair('GUSH')
    check('(b)3 a mark with `mark_as_of` shows its age', 'min old' in g_mark['text'], g_mark)
    check('...naming mark_as_of as the clock it used', 'own instant' in g_mark['titles'], g_mark)
    check('...and the age shows even though the mark is FRESH (rule 1 of the draft)',
          'min old' in g_mark['text'], g_mark)
    check('...and the P&L drawn from it carries an age too', 'old' in g_pnl['text'], g_pnl)

    bx, b_mark, b_pnl = cellpair('BX')
    check('a row with only `price_updated_at` still shows an age', 'd old' in b_mark['text'], b_mark)
    check('...and says it is the PRICE\'s clock, not the mark\'s',
          'not the mark' in b_mark['titles'], b_mark)
    check('...and keeps the hub\'s own STALE verdict beside it', 'stale mark' in b_mark['text'],
          b_mark)
    check('...and its P&L carries the age too, which is the whole point',
          'old' in b_pnl['text'], b_pnl)

    vix, v_mark, _vp = cellpair('VIX')
    check('a priced row with NO time reads "age unknown"', 'age unknown' in v_mark['text'], v_mark)
    check('...and says that is not the same as having no price',
          'not the same as having no price' in v_mark['titles'], v_mark)

    sq, s_mark, s_pnl = cellpair('SQQQ')
    check('a row with no mark still says "no mark", not "age unknown"',
          'no mark' in s_mark['text'] and 'age unknown' not in s_mark['text'], s_mark)
    check('...and its row shows no age at all, having no price to age',
          'old' not in sq.replace('no mark', ''), sq[:200])

    # THE PAGE PICKS NO THRESHOLD (R-IV.943(c)): "stale" is the hub's word, and this file renders
    # the verdict it was given. Asserted on the SOURCE of the two functions, which is where such a
    # rule would have to live -- an earlier version of this check looked for "26" in the rendered
    # text and matched a cost basis and a year, passing and failing for reasons unrelated to the
    # rule. A proxy that can match anything proves nothing.
    src = io.open(os.path.join(ROOT, 'v2.js'), encoding='utf-8').read()
    fn = src[src.index('function markAge(p)'):src.index('function markCell(p)')]
    import re as _re
    nums = [n for n in _re.findall(r'\b\d+\b', fn) if n not in ('0', '1', '60', '1440', '60000')]
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
