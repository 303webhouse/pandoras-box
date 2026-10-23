r"""R-IV.1315(c) + R-IV.1319(c) — the P&L preview, and Abacus at full width.

Run it:   python tests/test_r1315_pnl_preview.py            (Chromium)
          ENGINE=webkit python tests/test_r1315_pnl_preview.py
          SHOTS=1 python tests/test_r1315_pnl_preview.py     (also write the screenshots)

THE PAYLOAD IS BUILT BY THE REAL LOADER, not hand-written here. `api.abacus_pnl.load_pnl` runs
against a fake pool holding rows shaped like the book's, so what the page is tested against is the
module's own output. A hand-written fixture tests the page against a shape I assumed, and the two
drift the first time the loader changes a key -- which is how the R-IV.900 suite could have passed
while BUILD served something else (R-IV.934).

WHAT IS PINNED HERE:
  * the five KPIs render, and each one that the book cannot support says so IN WORDS;
  * realized and unrealized never appear in the same figure (R-IV.1315(c));
  * a scratch is excluded from the win-rate denominator and SAID;
  * a multi-lot close whose lots were held for different lengths shows the RANGE, never one number;
  * "by bucket" says "not available yet" with its fill rate, and never draws a chart of the tagged few;
  * the undated closures are named and declared outside every figure;
  * at 1920, 2560 and 1366 the page fills the width: no horizontal scroll, and no empty side gutter.
"""
import io
import json
import os
import subprocess
import sys
import threading
import http.server
import socketserver
from datetime import date, datetime, timedelta, timezone

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(REPO, 'frontend')
sys.path.insert(0, os.path.join(REPO, 'backend'))

fails = []


def say(*p):
    print(' '.join(str(x) for x in p).encode('ascii', 'replace').decode('ascii'))


def check(n, c, x=''):
    say(('PASS ' if c else 'FAIL ') + n + (' >> ' + str(x)[:300] if x and not c else ''))
    if not c:
        fails.append(n)


for name in ('abacus.js', os.path.join('assets', 'abacus-pnl.js')):
    r = subprocess.run(['node', '--check', os.path.join(ROOT, name)], capture_output=True, text=True)
    check('parses: ' + name, r.returncode == 0, (r.stderr or '')[:300])

# ── the fake pool, holding rows in the book's own shape ────────────────────────────────────────
TODAY = date.today()
M1 = TODAY.replace(day=1)


def _utc(d):
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def clo(cid, pos, acct, tkr, struct, realized, trade_d, acquired, bucket=None, qty=1):
    return {'id': cid, 'realized': realized, 'trade_date': trade_d, 'qty': qty,
            'position_id': pos, 'account': acct, 'ticker': tkr, 'structure': struct,
            'bucket': bucket, 'acquired_at': _utc(acquired)}


CLOSURES = [
    # A MULTI-LOT CLOSE whose two lots were held for DIFFERENT lengths: the case the mock's single
    # "days" column cannot express.
    clo(1, 'POS_SQQQ_1', 'FIDELITY_ROTH', 'SQQQ', 'stock', 40.00, M1 + timedelta(days=19), M1 + timedelta(days=16)),
    clo(2, 'POS_SQQQ_1', 'FIDELITY_ROTH', 'SQQQ', 'stock', 24.00, M1 + timedelta(days=19), M1 - timedelta(days=3)),
    # A SCRATCH: exactly zero, neither a win nor a loss.
    clo(3, 'POS_GLD_1', 'FIDELITY_ROTH', 'GLD', 'stock', 0.00, M1 + timedelta(days=12), M1 + timedelta(days=5)),
    clo(4, 'POS_XLF_1', 'ROBINHOOD', 'XLF', 'put_debit_spread', -41.00, M1 + timedelta(days=16), M1 + timedelta(days=7), 'B2'),
    clo(5, 'POS_PDBC_1', 'FIDELITY_401A', 'PDBC', 'stock', 118.00, M1 + timedelta(days=15), M1 - timedelta(days=7)),
    clo(6, 'POS_IWM_1', 'ROBINHOOD', 'IWM', 'long_call', -73.00, M1 + timedelta(days=14), M1 + timedelta(days=10)),
    # A prior-period close, so the comparison has something to compare.
    clo(7, 'POS_TLT_1', 'ROBINHOOD', 'TLT', 'long_put', -186.00, M1 - timedelta(days=10), M1 - timedelta(days=20)),
]
OPEN = [
    {'position_id': 'POS_A', 'account': 'ROBINHOOD', 'ticker': 'QQQ', 'structure': 'put_debit_spread',
     'bucket': None, 'bucket_reason': None, 'unrealized_pnl': -120.00, 'current_price': 1.2,
     'mark_as_of': None, 'price_updated_at': datetime.now(timezone.utc) - timedelta(hours=38),
     'mark_status': 'STALE'},
    {'position_id': 'POS_B', 'account': 'FIDELITY_ROTH', 'ticker': 'GUSH', 'structure': 'stock',
     'bucket': None, 'bucket_reason': None, 'unrealized_pnl': -118.00, 'current_price': 49.7,
     'mark_as_of': datetime.now(timezone.utc) - timedelta(minutes=20),
     'price_updated_at': datetime.now(timezone.utc) - timedelta(minutes=45), 'mark_status': 'OK'},
    # UNPRICED: so the unrealized sum covers 2 of 3 and must render as a floor.
    {'position_id': 'POS_C', 'account': 'FIDELITY_401A', 'ticker': 'GDXJ', 'structure': 'stock',
     'bucket': None, 'bucket_reason': None, 'unrealized_pnl': None, 'current_price': None,
     'mark_as_of': None, 'price_updated_at': None, 'mark_status': None},
]
UNDATED = [
    {'id': 1942, 'realized': -13.08, 'account': 'ROBINHOOD', 'ticker': 'IWM'},
    {'id': 1943, 'realized': -44.18, 'account': 'ROBINHOOD', 'ticker': 'NVDA'},
]


# R-IV.1349(b): a row past its expiry with size still on the book. One row, as the book has today.
UNBOOKED = [
    {'id': 1004, 'ticker': 'IWM', 'account': 'ROBINHOOD', 'status': 'EXPIRED',
     'structure': 'long_call', 'expiry': date(2026, 10, 19), 'cost_basis': 14.08,
     'open_qty': 2, 'days_past': 3},
]


class _Pool:
    """Routed on the SQL, never on call order -- the fault R-IV.1281 fixed in the other fixture."""

    async def fetchrow(self, sql, *a):
        if 'MIN(trade_date)' in sql:
            return {'d': min(c['trade_date'] for c in CLOSURES)}
        raise AssertionError('no fetchrow route: ' + ' '.join(sql.split())[:120])

    async def fetch(self, sql, *a):
        if 'trade_date IS NULL' in sql:
            return [dict(r) for r in UNDATED]
        # Routed on limb 6's own predicate text, so a change to it fails here rather than
        # silently returning the closure rows.
        if 'expiry < current_date' in sql:
            return [dict(r) for r in UNBOOKED]
        if 'position_lot_closures' in sql:
            return [dict(r) for r in CLOSURES]
        if "= 'OPEN'" in sql:
            return [dict(r) for r in OPEN]
        raise AssertionError('no fetch route: ' + ' '.join(sql.split())[:120])


import asyncio  # noqa: E402

from api.abacus_pnl import load_pnl  # noqa: E402

PAYLOAD = asyncio.get_event_loop().run_until_complete(load_pnl(_Pool(), 'month', 'ALL'))
say('payload built by the real loader: realized=%s closes=%s scratches=%s'
    % (PAYLOAD['realized'], PAYLOAD['closes'], PAYLOAD['scratches']))


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def translate_path(self, p):
        return os.path.join(ROOT, p.split('?')[0].lstrip('/') or 'abacus.html')


srv = socketserver.TCPServer(('127.0.0.1', 0), H)
PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d/' % PORT

SHOTS = os.environ.get('SHOTS') == '1'
SHOTDIR = os.path.join(REPO, 'docs', 'screenshots')
if SHOTS:
    os.makedirs(SHOTDIR, exist_ok=True)


def route(r):
    u = r.request.url

    def j(o, s=200):
        r.fulfill(status=s, content_type='application/json', body=json.dumps(o))

    if '/api/abacus/pnl' in u:
        return j(PAYLOAD)
    if '/api/abacus/summary' in u:
        return j({'version': 1, 'mock': True, 'stats': [], 'breakdowns': [], 'accounts': [],
                  'scope': {'source': 'live'}, 'equity': {'accounts': []},
                  'leaks': {'items': []}, 'strategies': {'note': ''},
                  'range': {'key': '90d', 'from': '2026-07-23', 'to': '2026-10-21'},
                  'combined_is_pooled': True})
    return j({}, 404)


def page(b, path, w, h):
    ctx = b.new_context(viewport={'width': w, 'height': h})
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append('pageerror: ' + str(e)))
    pg.on('console', lambda m: errs.append('console: ' + m.text[:140])
          if m.type == 'error' and 'Failed to load resource' not in m.text else None)
    pg.route('**/api/**', route)
    pg.goto(BASE + path, wait_until='domcontentloaded')
    pg.wait_for_timeout(1400)
    return pg, ctx, errs


with sync_playwright() as p:
    ENGINE = os.environ.get('ENGINE', 'chromium')
    say('engine: ' + ENGINE)
    b = getattr(p, ENGINE).launch()

    # ── the preview's content ───────────────────────────────────────────────────
    # R-IV.1356(c): the P&L view is THE DEFAULT now -- opened with no query string at all.
    pg, ctx, errs = page(b, 'abacus.html', 1920, 1080)
    body = pg.evaluate("() => document.body.innerText")
    check('the P&L view is the DEFAULT, with no query string',
          'P&L' in body and 'realized, by trade date' in body, body[:160])
    check('...and no longer calls itself a preview', 'Preview (?pnl=v1)' not in body, body[:200])
    check('the summary view did NOT also paint',
          pg.evaluate("() => !!document.getElementById('abPnl') && [...document.getElementById('abPage').children]"
                      ".filter(e => e.id !== 'abPnl').every(e => e.hidden)"))
    kpis = pg.evaluate("() => [...document.querySelectorAll('.pnl-kpi')].map(e => e.innerText)")
    check('all five KPIs rendered', len(kpis) == 5, len(kpis))
    blob = '\n'.join(kpis)
    check('realized carries its prior period', 'REALIZED' in blob and 'realized, by trade date' in body, blob[:140])
    check('the SCRATCH is excluded from the win rate and said so',
          'scratch' in blob and 'excluded' in blob, blob[:200])
    # R-IV.1356(b): THE UNIT IS THE POSITION. The stub's SQQQ position holds TWO closures
    # (+40.00 and +24.00); counted by closure that is two wins, by position it is one.
    check('wins and losses count POSITIONS, not closing records',
          'of 4 positions' in blob, blob[:280])
    check('...and the closure count stays visible as the sample',
          '6 closes' in blob, blob[:280])
    check('...and the banner states the unit on the page itself',
          'count a position once per period' in body.replace('\n', ' '), body[:420])
    # NOT a floor. A floor marker claims the true figure is at least this, which is a statement
    # about order, and an unpriced row can move a SIGNED total either way. The tile states its
    # COVERAGE instead, which is the claim that actually holds.
    check('the unrealized tile states what it covers while a row is unpriced',
          'covers 2 of 3' in blob and 'unpriced' in blob, blob[:280])
    check('...and does NOT mark a signed total with a floor symbol', '≥' not in blob, blob[:280])
    check('...and it shows the OLDEST mark age, not one mark time',
          'oldest mark' in blob, blob[:260])
    check('realized and unrealized are separate tiles, never one figure',
          sum(1 for k in kpis if 'UNREALIZED' in k) == 1
          and all(not ('REALIZED ·' in k and 'UNREALIZED' in k) for k in kpis), kpis)
    check('by bucket says "not available yet" with its fill rate',
          'not available yet' in body and 'carry a bucket' in body,
          [l for l in body.split('\n') if 'bucket' in l.lower()][:3])
    # THE REAL CLAIM is structural: while the bucket block is unavailable it must draw no bar
    # rows at all. The first version of this check looked for the words core/tactical/lotto in the
    # page text, which is the same weak proxy as grepping the rendered text for a threshold -- it
    # can match anything and it proves nothing about what was drawn.
    bucket_rows = pg.evaluate("""() => {
        const card = [...document.querySelectorAll('.ab-card')].find(
            (e) => /By bucket/i.test(e.textContent));
        return card ? card.querySelectorAll('.pnl-row').length : -1; }""")
    check('...and draws no bucket bar while it is unavailable', bucket_rows == 0, bucket_rows)
    # R-IV.1349(b): UNBOOKED money, in the same pattern and with the same discipline.
    check('the expired-but-unbooked line is on the page, with its count and cost',
          'Expired, not yet booked: 1 position, cost $14.08' in body, body[:400])
    check('...declared outside every total', 'outside every total here' in body, body[:400])
    check('...and names the row, so the count can be traced',
          'IWM (Robinhood) $14.08, 3d past expiry' in body, body[:420])
    check('...and its cost is NOT added to any figure',
          not any('14.08' in k for k in kpis), kpis)

    check('the undated closures are named and declared outside every figure',
          'Date unknown: 2 closures' in body and 'every period' in body,
          [l for l in body.split('\n') if 'unknown' in l.lower()][:2])
    rows = pg.evaluate("() => [...document.querySelectorAll('.pnl-closes')].map(e => e.innerText)")
    check('a multi-lot close whose lots differ shows a RANGE, not one number',
          any('–' in r and 'SQQQ' in r for r in rows), [r for r in rows if 'SQQQ' in r])
    check('no console or page errors', not errs, errs)
    ctx.close()

    # THE ROLLBACK FLAG (R-IV.1356(c)), which expires 2026-10-29. Tested because a flag nobody
    # exercises is a flag that has already broken by the time someone needs it.
    pg, ctx, errs = page(b, 'abacus.html?view=summary', 1920, 1080)
    check('?view=summary still reaches the OLD summary view',
          pg.evaluate("() => !document.getElementById('abPnl')"))
    check('...and the summary sections are not hidden',
          pg.evaluate("() => [...document.getElementById('abPage').children].some(e => !e.hidden)"))
    check('rollback path: no errors', not errs, errs)
    ctx.close()

    # And the old address keeps working, so links already shared do not break.
    pg, ctx, errs = page(b, 'abacus.html?pnl=v1', 1920, 1080)
    check('?pnl=v1 still resolves to the P&L view',
          'realized, by trade date' in pg.evaluate("() => document.body.innerText"))

    # ── R-IV.1319(c) · full width at three sizes, both views ────────────────────
    for (w, h) in ((1920, 1080), (2560, 1440), (1366, 768)):
        for path, tag in (('abacus.html?pnl=v1', 'pnl'), ('abacus.html', 'summary')):
            pp, pctx, perrs = page(b, path, w, h)
            geo = pp.evaluate("""() => {
                const d = document.documentElement, m = document.querySelector('.ab-page');
                const cs = m ? getComputedStyle(m) : null;
                const r = m ? m.getBoundingClientRect() : null;
                return {scrollW: d.scrollWidth, clientW: d.clientWidth,
                        pageW: r ? Math.round(r.width) : null,
                        left: r ? Math.round(r.left) : null,
                        padL: cs ? cs.paddingLeft : null, maxW: cs ? cs.maxWidth : null}; }""")
            check('%dx%d %s: no horizontal scroll' % (w, h, tag),
                  geo['scrollW'] <= geo['clientW'] + 1, geo)
            # NO EMPTY SIDE GUTTER: the container spans the viewport apart from its own padding.
            check('%dx%d %s: the page fills the width (no centred column)' % (w, h, tag),
                  geo['maxW'] == 'none' and geo['pageW'] is not None
                  and geo['pageW'] >= geo['clientW'] - 2, geo)
            check('%dx%d %s: no errors' % (w, h, tag), not perrs, perrs)
            if SHOTS:
                f = os.path.join(SHOTDIR, 'r1315-%s-%dx%d.png' % (tag, w, h))
                pp.screenshot(path=f, full_page=False)
                say('   shot: ' + os.path.relpath(f, REPO))
            pctx.close()
    ctx.close()
    b.close()

say('')
say('%d checks failed' % len(fails))
for f in fails:
    say('  - ' + f)
sys.exit(1 if fails else 0)
