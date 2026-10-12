r"""R-IV.900(b) / R-IV.911(b) — the signal title, the APIS/KODIAK tag, and the pulse-while-fresh.

Run it:   python tests/test_r900_signal_names_ui.py            (Chromium)
          ENGINE=webkit python tests/test_r900_signal_names_ui.py

WHY THIS LIVES IN THE REPO. R-IV.911(b) asks for these checks to be re-run "against the served
payload shape" once BUILD ships `display_label` and `upgrade_tag` (R-IV.907). A suite that only
exists in a session's scratchpad cannot be re-run by a later session, so it is here.

READ THIS BEFORE THE RE-RUN — RE-RUNNING IT UNCHANGED PROVES NOTHING ABOUT BUILD'S PAYLOAD.
Everything below STUBS the feed, so it tests the PAGE against a shape I assumed, and it will keep
passing no matter what BUILD actually serves. These are the assumptions it encodes:

  * `display_label` is ONE string containing a pipe, e.g. "ACHILLES | Sell the Rip". The page
    splits on the FIRST pipe; a label with no pipe renders whole, with no description.
  * `upgrade_tag` is the bare word "APIS" or "KODIAK" (compared upper-cased, so case does not
    matter). ANY other value is ignored on purpose.
  * both arrive on each row of `/api/trade-ideas`, beside `codename`.

To test the REAL shape, capture one authenticated `/api/trade-ideas` response to a file and point
this at it:

    R900_PAYLOAD=C:\path\to\trade-ideas.json python tests/test_r900_signal_names_ui.py

With that set, the WIRED pass serves the captured rows instead of the stub, and a mismatch between
BUILD's shape and the assumptions above shows up as a failing title or a missing tag rather than as
a green run. Without it, the suite says so in its first line of output.

── HOW TO TAKE THAT CAPTURE (R-IV.929(b)) ────────────────────────────────────────────────────────
SPINE granted ONE authenticated capture, and only once BUILD reports the two fields served. Its
terms: never print or store the credential; strip nothing but the auth header; run the suite in
Chromium AND WebKit; report whether the shape matches the four assumptions above.

  1. The route is gated by `utils.pivot_auth.require_api_key`, which accepts EITHER an
     `X-API-Key: <PIVOT_API_KEY>` header OR a signed `pivot_session` cookie.
  2. `PIVOT_API_KEY` comes only from `railway variables`, whose CLI token EXPIRES, and
     `railway login` is interactive — so a dead token means the principal has to run it. A dead
     token looks like a 401 on this route while /health still answers 200.
  3. Read the key into a shell variable and send it as a header. Do not echo it, do not write it
     into the captured file, do not paste it into a report. What is captured is the SIGNALS payload
     and nothing else: the auth header is the only thing stripped, because it is the only thing
     that is a credential.
  4. SPINE'S PERMISSION IS NOT THE HARNESS'S. An earlier attempt at exactly this call was refused
     by the tool-permission layer as a production read. That control is separate from the ruling,
     so expect a prompt and let the principal approve it. If it is refused, say so and stop — do
     not reach for another route to the same bytes.

Then run the suite twice, with ENGINE unset and ENGINE=webkit, and report PER ASSUMPTION rather
than as one pass/fail: which of the four held, and for any that did not, what the payload carried
instead.

Control: the pinned build (9beda308) shows the name and description as two separate spans, with no
pipe, no tag and no glow, however the feed is labelled.
"""
import io, json, threading, http.server, socketserver, os, sys, subprocess, time
from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROOT = os.path.join(REPO, 'frontend')
PINNED = '9beda308'
class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
    def translate_path(self, path): return os.path.join(ROOT, path.split('?')[0].lstrip('/') or 'v2.html')
srv = socketserver.TCPServer(('127.0.0.1', 0), H); port = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = f'http://127.0.0.1:{port}/v2.html'
OLD = {n: subprocess.check_output(['git', '-C', REPO, 'show', PINNED + ':frontend/' + n])
       for n in ('v2.js', 'v2.css')}

NOW = time.time()
def iso(sec_ago):
    return time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(NOW - sec_ago)) + 'Z'

def sig(sid, tkr, codename, stype, strategy, side, **kw):
    s = {'signal_id': sid, 'ticker': tkr, 'asset_class': 'EQUITY', 'direction': side,
         'entry_price': 100.0, 'is_liquid': False, 'strategy_class': 'roster', 'high_score': False,
         'signal_type': stype, 'strategy': strategy, 'codename': codename,
         'timestamp': iso(3600), 'fired_at': iso(3600), 'session': 'regular',
         'release_at': None, 'held': False, 'canonical_score': 60, 'touches': [],
         'target_1': 104.0, 'stop_loss': 98.0, 'timeframe': '15m'}
    s.update(kw)
    return s

# The feed as the backend serves it TODAY: no display_label, no upgrade_tag anywhere.
TODAY = [
    sig('a1', 'IWM', 'ACHILLES', 'SELL_RIP_EMA', 'sell_the_rip', 'SHORT'),
    sig('m1', 'GLD', 'MIDAS', 'MIDAS_LONG', 'midas', 'LONG'),          # no SETUP_MAP entry
]
# The same feed once LAB serves the two fields (R-IV.833) — proving the wiring, not the data.
WIRED = [
    sig('a1', 'IWM', 'ACHILLES', 'SELL_RIP_EMA', 'sell_the_rip', 'SHORT',
        display_label='ACHILLES | Sell the Rip', upgrade_tag='KODIAK',
        timestamp=iso(120), fired_at=iso(120)),                         # 2 min old -> FRESH
    sig('m1', 'GLD', 'MIDAS', 'MIDAS_LONG', 'midas', 'LONG',
        display_label='MIDAS | Golden Touch', upgrade_tag='APIS',
        timestamp=iso(3600), fired_at=iso(3600)),                       # 1 h old -> steady
    sig('p1', 'XLE', 'PERSEPHONE', 'PERSEPHONE_TURN', 'two_close_turn', 'LONG',
        display_label='PERSEPHONE | Two-Close Turn'),                   # no tag at all
    sig('h1', 'SPY', 'HECTOR', 'HECTOR_X', 'hector', 'LONG',
        display_label='HECTOR | Breadth Thrust', upgrade_tag='WHATEVER'),  # a tag we do not know
    sig('r1', 'QQQ', 'ACHILLES', 'SELL_RIP_EMA', 'sell_the_rip', 'SHORT',
        display_label='ACHILLES | Sell the Rip', upgrade_tag='APIS',
        release_at=iso(60), fired_at=iso(6 * 3600), held=False),        # HELD: released 1 min ago
]
# Split at the tile's 3-card cap, so every case is inside the window that actually renders.
WIRED_TAIL = [WIRED[3], WIRED[4], WIRED[2]]
WIRED = WIRED[:3]
# R-IV.911(b): a real captured payload overrides the stub, so the re-run can test BUILD's own
# shape rather than my assumption of it.
CAPTURED = None
_cap = os.environ.get('R900_PAYLOAD')
if _cap:
    with io.open(_cap, encoding='utf-8') as fh:
        _d = json.load(fh)
    CAPTURED = _d.get('signals') if isinstance(_d, dict) else _d
    if not CAPTURED:
        raise SystemExit('R900_PAYLOAD holds no signals: ' + _cap)
    _served = [r for r in CAPTURED if r.get('display_label') or r.get('upgrade_tag')]
    print('CAPTURED PAYLOAD: %d rows, %d carrying display_label or upgrade_tag' % (len(CAPTURED), len(_served)))
    if not _served:
        print('  !! none of them carries either field — the re-run cannot confirm the shape yet')
else:
    print('STUBBED FEED (no R900_PAYLOAD given): this run tests the PAGE, not BUILD\'s payload shape.')

FEED = {'rows': TODAY}

def route(r):
    u = r.request.url
    def j(o, s=200): r.fulfill(status=s, content_type='application/json', body=json.dumps(o))
    if '/api/trade-ideas/notices' in u: return j({'notices': []})
    if '/api/trade-ideas' in u: return j({'signals': FEED['rows'], 'total': len(FEED['rows']), 'limit': 50, 'offset': 0})
    if '/api/v2/positions' in u: return j({'positions': [], 'count': 0})
    if '/api/portfolio/balances' in u: return j([])
    if '/api/portfolio/cash-balance' in u: return j({'accounts': {}})
    if '/api/bias/composite' in u: return j({'bias_level': 'NEUTRAL', 'composite_score': 0.15})
    if '/api/board/levels/' in u: return j({'ticker': 'X', 'available': False, 'levels': None})
    if '/api/flow/radar' in u: return j({'position_flow': [], 'watchlist_unusual': [], 'headlines': []})
    if '/api/hermes/alerts' in u: return j({'alerts': []})
    if '/api/stable/enrich' in u: return j({'enrichment': {}})
    return j({}, 404)

fails = []
def check(n, c, x=''):
    line = ('PASS ' if c else 'FAIL ') + n + (' >> ' + str(x)[:300] if x and not c else '')
    print(line.encode('ascii', 'replace').decode('ascii'))
    if not c: fails.append(n)

def page(b, old=False, w=1440, motion='no-preference'):
    ctx = b.new_context(viewport={'width': w, 'height': 1200}, reduced_motion=motion)
    pg = ctx.new_page(); errs = []
    def own(e):
        st = e.stack or ''
        if st and 'tradingview' in st.lower() and '127.0.0.1' not in st: return
        errs.append(str(e))
    pg.on('pageerror', own)
    pg.route('**/api/**', route)
    pg.route('**/stable_digest.md', lambda r: r.fulfill(status=404, body=''))
    if old:
        def swap(name, ctype): return lambda r: r.fulfill(status=200, content_type=ctype, body=OLD[name])
        for n, ct in (('v2.js', 'application/javascript'), ('v2.css', 'text/css')):
            pg.route('**/%s*' % n, swap(n, ct))
    pg.goto(BASE, wait_until='domcontentloaded'); pg.wait_for_timeout(2400)
    return pg, ctx, errs

CARD = """(tkr) => {
  const c = [...document.querySelectorAll('.k-card')].find(e => e.textContent.includes(tkr));
  if (!c) return null;
  const nm = c.querySelector('.nm'), tag = c.querySelector('.upgrade-tag');
  const cs = getComputedStyle(c);
  return {nm: nm ? nm.textContent.trim() : null,
          hasSep: !!(nm && nm.querySelector('.sep')),
          hasWhat: !!(nm && nm.querySelector('.what')),
          desc: !!c.querySelector('.desc'),
          tag: tag ? tag.textContent.trim() : null,
          tagColor: tag ? getComputedStyle(tag).color : null,
          cls: c.className, anim: cs.animationName, shadow: cs.boxShadow};
}"""

with sync_playwright() as p:
    ENGINE = os.environ.get('ENGINE', 'chromium')
    print('engine:', ENGINE)
    b = getattr(p, ENGINE).launch()

    # ── CONTROL: the pinned page, same feed ──────────────────────────────────
    FEED['rows'] = WIRED
    po, pctx, _ = page(b, old=True)
    c = po.evaluate(CARD, 'IWM')
    check('CONTROL: the pinned page shows no pipe in the title', c and not c['hasSep'], c)
    check('CONTROL: ...keeps the description in a separate span', c and c['desc'], c)
    check('CONTROL: ...renders no tag even though the feed carries one', c and c['tag'] is None, c)
    check('CONTROL: ...and no glow', c and c['shadow'] in ('none', ''), c)
    pctx.close()

    # ── TODAY: the fields are not served. The format still applies; nothing is invented. ──
    FEED['rows'] = TODAY
    pg, ctx, errs = page(b)
    a = pg.evaluate(CARD, 'IWM')
    check('with no display_label, the title still reads FIGURE | Description from the fallback',
          a and a['nm'] == 'ACHILLES | Sell the Rip' and a['hasSep'], a)
    m = pg.evaluate(CARD, 'GLD')
    # MEASURED, not assumed: `setupDisplay` returns the SERVED codename when SETUP_MAP has no
    # entry, so the card shows the right NAME with no description. The gap for MIDAS, HECTOR and
    # NEMESIS is the missing description, not a raw identifier -- my first version of this check
    # expected 'MIDAS_LONG' and was wrong about the live page.
    check('a strategy SETUP_MAP has no entry for shows the served codename, with no description',
          m and m['nm'] == 'MIDAS' and not m['hasSep'] and not m['hasWhat'], m)
    check('...and no tag or glow is invented from an absent field',
          a and a['tag'] is None and 'upgraded' not in a['cls'] and a['shadow'] in ('none', ''), a)
    check('no page errors', not errs, errs)
    ctx.close()

    # ── WIRED: once the two fields are served ────────────────────────────────
    # A captured payload wins over the stub (R-IV.911(b)). Only the first three roster rows get a
    # card, so a capture is trimmed to what the tile will actually render.
    FEED['rows'] = CAPTURED[:3] if CAPTURED else WIRED
    if CAPTURED:
        print('   (the WIRED pass is running against the CAPTURED payload)')
    pg, ctx, errs = page(b)
    k = pg.evaluate(CARD, 'IWM')
    check('the served display_label is rendered whole', k and k['nm'] == 'ACHILLES | Sell the Rip', k)
    check('...split into the figure and the description, with the pipe between',
          k and k['hasSep'] and k['hasWhat'], k)
    check('...and the old separate desc span is gone', k and not k['desc'], k)
    check('KODIAK tags the card and keeps the strategy name', k and k['tag'] == 'KODIAK', k)
    check('...in the vermilion family', k and k['tagColor'] == 'rgb(255, 92, 51)', k)
    check('...with the glow on', k and 'kodiak' in k['cls'] and k['shadow'] not in ('none', ''), k)
    check('...and PULSING, because it fired two minutes ago',
          k and 'fresh' in k['cls'] and k['anim'] == 'kodiak-pulse', k)
    g = pg.evaluate(CARD, 'GLD')
    check('APIS tags the long, in the lime family', g and g['tag'] == 'APIS' and g['tagColor'] == 'rgb(124, 255, 107)', g)
    check('...and holds STEADY, because it is an hour old',
          g and 'fresh' not in g['cls'] and g['anim'] == 'none', g)
    x = pg.evaluate(CARD, 'XLE')
    check('a signal with no tag gets the title and nothing else',
          x and x['tag'] is None and 'upgraded' not in x['cls'], x)
    check('no page errors with the fields served', not errs, errs)
    ctx.close()

    # THE KAIROS TILE SHOWS ONLY THE FIRST THREE roster signals (`roster.slice(0, 3)`, v2.js:2467)
    # -- pre-existing, nothing to do with this change. The remaining cases therefore need their own
    # feed rather than positions 4 and 5 of one, which is how the first version of this suite
    # "failed": the cards it was asserting on were never rendered.
    FEED['rows'] = WIRED_TAIL
    pg, ctx, errs = page(b)
    h = pg.evaluate(CARD, 'SPY')
    check('an UNRECOGNISED tag gets no treatment rather than the wrong one',
          h and h['tag'] is None and 'upgraded' not in h['cls'] and h['shadow'] in ('none', ''), h)
    check('...and the title it does carry is still rendered',
          h and h['nm'] == 'HECTOR | Breadth Thrust', h)
    r = pg.evaluate(CARD, 'QQQ')
    check('a HELD signal released a minute ago pulses, though it fired six hours ago',
          r and 'fresh' in r['cls'] and r['anim'] == 'apis-pulse', r)
    check('no page errors on the second feed', not errs, errs)
    ctx.close()

    # ── reduced motion, and the phone ────────────────────────────────────────
    # Say which feed, rather than inheriting whatever the last block left: the previous version of
    # this suite ran these against the tail feed, where the card it names does not exist.
    FEED['rows'] = WIRED
    pr, rctx, _ = page(b, motion='reduce')
    rk = pr.evaluate(CARD, 'IWM')
    check('reduce motion: nothing pulses', rk and rk['anim'] == 'none', rk)
    check('reduce motion: ...but the outline stays', rk and rk['shadow'] not in ('none', ''), rk)
    rctx.close()

    for w in (390, 430):
        FEED['rows'] = WIRED
        pp, pctx2, perrs = page(b, w=w)
        hits = pp.evaluate("""() => {
          const out = [];
          document.querySelectorAll('.k-card').forEach((card, i) => {
            const leaves = [...card.querySelectorAll('*')].filter((e) => {
              if (e.children.length || !e.textContent.trim()) return false;
              const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; });
            const bx = leaves.map((e) => { const r = e.getBoundingClientRect();
              return {t: e.textContent.trim().slice(0, 18), l: r.left, rt: r.right, tp: r.top, b: r.bottom}; });
            for (let a = 0; a < bx.length; a++) for (let c = a + 1; c < bx.length; c++) {
              const ox = Math.min(bx[a].rt, bx[c].rt) - Math.max(bx[a].l, bx[c].l);
              const oy = Math.min(bx[a].b, bx[c].b) - Math.max(bx[a].tp, bx[c].tp);
              if (ox > 1 && oy > 1) out.push([i, bx[a].t, bx[c].t]); } });
          return out; }""")
        check('%dpx: no two text boxes in a card intersect (R-IV.719)' % w, not hits, hits)
        check('%dpx: no page errors' % w, not perrs, perrs)
        pctx2.close()
    b.close()

print('\n%d checks failed' % len(fails))
for f in fails: print('  - ' + f)
sys.exit(1 if fails else 0)
