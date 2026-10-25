"""R-IV.1440 / R-IV.1371(e), default since R-IV.1444 -- the TV tile in Agora's top-right square.

Rules (each has a breakage proof): ON by default on a desktop; ?tv=off loads nothing; ?tv=preview
is harmless; never on phones; placed only in an EMPTY top-right square, moving nothing; and never
written into the saved layout, even when another tile's move triggers a save.

Run:  python tests/test_r1440_tv_preview.py

No network to YouTube: youtube-nocookie.com and tv.youtube.com are answered by a stub, so this checks
OUR side (flag gate, placement, muted embed, switcher, the YouTube TV window, phones) and never
whether a stream is live today. The layout below is the SHAPE of the saved Agora layout row read on
2026-10-25 (tile ids and grid positions only; nothing about the book).
"""
import json
import os
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


# ── static checks ────────────────────────────────────────────────────────────────────────
html = open(os.path.join(ROOT, 'v2.html'), encoding='utf-8').read()
js = open(os.path.join(ROOT, 'assets', 'tv', 'tv_tile.js'), encoding='utf-8').read()
check('v2.html names the TV script and stylesheet only inside its loader',
      html.count('/assets/tv/tv_tile.js') == 1 and html.count('/assets/tv/tv_tile.css') == 1
      and '<script src="/assets/tv/' not in html and 'href="/assets/tv/' not in html)
check('v2.html loads no YouTube player script and names no YouTube host',
      not any(h in html.lower() for h in ('youtube.com', 'youtube-nocookie', 'youtu.be', 'iframe_api')))
check('the embed host is youtube-nocookie.com only',
      'youtube-nocookie.com/embed/' in js and 'www.youtube.com/embed' not in js)
check('the embed asks for mute=1 and never mute=0', 'mute=1' in js and 'mute=0' not in js)

LAYOUT = [
    {'h': 9, 'w': 6, 'x': 0, 'y': 0, 'id': 'regime-band'}, {'h': 9, 'w': 3, 'x': 6, 'y': 0, 'id': 'regime-strategy'},
    {'h': 3, 'w': 6, 'x': 0, 'y': 9, 'id': 'index'}, {'h': 3, 'w': 3, 'x': 6, 'y': 9, 'id': 'usd'},
    {'w': 12, 'x': 0, 'y': 12, 'id': 'movers-tape'}, {'h': 7, 'w': 2, 'x': 0, 'y': 14, 'id': 'divergence'},
    {'h': 7, 'w': 2, 'x': 2, 'y': 14, 'id': 'crowd'}, {'h': 7, 'w': 3, 'x': 4, 'y': 14, 'id': 'breadth'},
    {'h': 14, 'w': 2, 'x': 7, 'y': 14, 'id': 'kairos'}, {'h': 21, 'w': 3, 'x': 9, 'y': 14, 'id': 'river'},
    {'h': 14, 'w': 2, 'x': 0, 'y': 21, 'id': 'book'}, {'h': 8, 'w': 2, 'x': 2, 'y': 21, 'id': 'fear'},
    {'h': 8, 'w': 3, 'x': 4, 'y': 21, 'id': 'themes'}, {'h': 6, 'w': 7, 'x': 2, 'y': 29, 'id': 'event-strip'},
]
# The same row with USD moved into the corner: the tile must stay out and move nothing.
TAKEN = [dict(n, x=9, y=0) if n['id'] == 'usd' else n for n in LAYOUT]
STATE = {'layout': LAYOUT, 'posts': 0, 'bodies': []}
STUB = '<!doctype html><html><body style="background:#000;color:#fff">stub</body></html>'


def route(r):
    u = r.request.url
    if '/api/layout' in u:
        if r.request.method == 'POST':
            STATE['posts'] += 1
            STATE['bodies'].append(r.request.post_data or '')
            return r.fulfill(status=200, content_type='application/json', body='{"ok":true}')
        return r.fulfill(status=200, content_type='application/json',
                         body=json.dumps({'layout': STATE['layout'], 'updated_at': '2026-10-23T21:29:57Z'}))
    return r.fulfill(status=404, content_type='application/json', body='{}')


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def translate_path(self, p):
        return os.path.join(ROOT, p.split('?')[0].lstrip('/') or 'v2.html')


srv = socketserver.TCPServer(('127.0.0.1', 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d/' % srv.server_address[1]

NODES = """() => Object.fromEntries(Array.from(document.querySelectorAll('#v2Grid > .grid-stack-item[gs-id]'))
  .map(e => [e.getAttribute('gs-id'), e.gridstackNode ? [e.gridstackNode.x, e.gridstackNode.y, e.gridstackNode.w,
  e.gridstackNode.h] : null]))"""


def page(b, w, h, q, mobile=False):
    ctx = b.new_context(viewport={'width': w, 'height': h}, is_mobile=mobile, has_touch=mobile)
    pg = ctx.new_page()
    seen, errs = [], []
    pg.on('request', lambda r: seen.append(r.url))
    pg.on('pageerror', lambda e: errs.append(str(e)) if 'tradingview' not in (getattr(e, 'stack', '') or '').lower() else None)
    ctx.route('**/api/**', route)
    ctx.route('**/stable_digest.md', lambda r: r.fulfill(status=404, body=''))
    ctx.route('https://www.youtube-nocookie.com/**', lambda r: r.fulfill(status=200, content_type='text/html', body=STUB))
    ctx.route('https://tv.youtube.com/**', lambda r: r.fulfill(status=200, content_type='text/html', body=STUB))
    pg.goto(BASE + 'v2.html' + q, wait_until='domcontentloaded')
    pg.wait_for_timeout(3000)
    return pg, ctx, seen, errs


def tv_requests(seen):
    return [u for u in seen if '/assets/tv/' in u or 'youtube' in u]


with sync_playwright() as p:
    b = p.chromium.launch()

    # 1. ?tv=off is the permanent off switch: nothing of the tile loads, wherever it sits in the query.
    for q in ('?tv=off', '?x=1&tv=off'):
        STATE['layout'] = LAYOUT
        pg, ctx, seen, errs = page(b, 1920, 1080, q)
        check('off (%r): no TV script, stylesheet or YouTube request' % q, not tv_requests(seen), tv_requests(seen))
        check('off (%r): no TV tile' % q, pg.evaluate("() => !document.querySelector('[gs-id=tv]')"))
        ctx.close()

    # 1b. The old preview bookmark is harmless: the tile is simply there.
    STATE['layout'] = LAYOUT
    pg, ctx, seen, errs = page(b, 1920, 1080, '?tv=preview')
    check('?tv=preview still works: the tile is there',
          pg.evaluate(NODES).get('tv') == [9, 0, 3, 12], pg.evaluate(NODES).get('tv'))
    ctx.close()

    # 2. NO FLAG, on a desktop, against the saved layout's shape: on by default.
    STATE['layout'], STATE['posts'], STATE['bodies'] = LAYOUT, 0, []
    pg, ctx, seen, errs = page(b, 1920, 1080, '')
    pg.wait_for_timeout(1500)                 # past v2.js's 800ms save debounce
    nodes = pg.evaluate(NODES)
    check('the tile sits in the top-right square: x9 y0 w3 h12', nodes.get('tv') == [9, 0, 3, 12], nodes.get('tv'))
    moved = {n['id']: (nodes.get(n['id']), [n['x'], n['y'], n.get('w'), n.get('h')]) for n in LAYOUT
             if nodes.get(n['id']) and nodes[n['id']][:2] != [n['x'], n['y']]}
    check('no other tile moved', not moved, moved)
    check('nothing was written to the layout row', STATE['posts'] == 0, STATE['posts'])
    # A real save: resize another tile, which fires GridStack's change and v2.js's saveLayout.
    pg.evaluate("() => { const g = document.getElementById('v2Grid').gridstack;"
                " g.update(document.querySelector('[gs-id=event-strip]'), {w: 6}); }")
    pg.wait_for_timeout(1500)
    saved = [json.loads(x) for x in STATE['bodies'] if x]
    ids = [n.get('id') for n in (saved[-1]['layout'] if saved else [])]
    check('a save triggered by another tile writes the layout WITHOUT the TV tile',
          STATE['posts'] >= 1 and 'event-strip' in ids and 'tv' not in ids, {'posts': STATE['posts'], 'ids': ids})
    f = pg.evaluate("() => { const i = document.querySelector('[gs-id=tv] iframe'); return i && {src: i.src,"
                    " allow: i.getAttribute('allow'), ref: i.getAttribute('referrerpolicy')}; }")
    check('the embed is youtube-nocookie.com, muted, Bloomberg first',
          f and f['src'].startswith('https://www.youtube-nocookie.com/embed/QB5BNdBFujE?') and 'mute=1' in f['src'], f)
    check('the embed keeps its referrer (YouTube refuses a referrer-less embed)',
          f and f['ref'] == 'strict-origin-when-cross-origin', f)
    small = pg.evaluate("""() => Array.from(document.querySelectorAll('[gs-id=tv] .tile *')).filter(e =>
        e.children.length === 0 && e.textContent.trim() && e.tagName !== 'IFRAME'
        && parseFloat(getComputedStyle(e).fontSize) < 12).map(e => e.textContent.trim().slice(0, 30))""")
    check('no text in the tile under 12px', not small, small)
    pg.click('[data-tv-s=yahoo]')
    src2 = pg.evaluate("() => document.querySelector('[gs-id=tv] iframe').src")
    check('the switcher moves the embed to Yahoo Finance, still muted',
          src2.startswith('https://www.youtube-nocookie.com/embed/KQp-e_XQnDE?') and 'mute=1' in src2, src2)
    rect = pg.evaluate("() => { const r = document.querySelector('[gs-id=tv] .tile').getBoundingClientRect();"
                       " return [Math.round(r.width), Math.round(r.height)]; }")
    with ctx.expect_page() as pop:
        pg.click('[data-tv-y=cnbc]')
    w = pop.value
    w.wait_for_load_state()
    check('CNBC opens YouTube TV (the live guide until a link is saved) in a separate window',
          w.url == 'https://tv.youtube.com/live', w.url)
    size = w.evaluate('() => [outerWidth, outerHeight]')
    check('the window is the tile\'s size (within 40px)',
          abs(size[0] - rect[0]) <= 40 and abs(size[1] - rect[1]) <= 40, {'window': size, 'tile': rect})
    check('the window has no handle back to the hub', w.evaluate('() => window.opener === null'))
    w.close()
    check('default desktop: no errors', not errs, errs)

    # Narrowed to phone width: hidden, and the stream stopped.
    pg.set_viewport_size({'width': 700, 'height': 900})
    pg.wait_for_timeout(800)
    nar = pg.evaluate("() => { const t = document.querySelector('[gs-id=tv]'); const i = t && t.querySelector('iframe');"
                      " return {shown: !!t && getComputedStyle(t).display !== 'none', src: i && i.getAttribute('src')}; }")
    check('narrowed to 700px: the tile is hidden and the stream stops', not nar['shown'] and not nar['src'], nar)
    ctx.close()

    # 3. The square is taken: the tile stays out and moves nothing.
    STATE['layout'], STATE['posts'] = TAKEN, 0
    pg, ctx, seen, errs = page(b, 1920, 1080, '')
    nodes = pg.evaluate(NODES)
    check('square taken: no TV tile', 'tv' not in nodes, nodes.get('tv'))
    check('square taken: USD stays where the layout put it', nodes.get('usd', [None, None])[:2] == [9, 0], nodes.get('usd'))
    check('square taken: says so on the status line',
          'TV not placed' in pg.evaluate("() => document.getElementById('layoutStatus').textContent"))
    ctx.close()

    # 4. Phones: nothing loads, flag or not (narrow, and a touch pointer held sideways).
    for (w_, h_, q) in ((390, 844, ''), (915, 412, ''), (390, 844, '?tv=preview')):
        STATE['layout'] = LAYOUT
        pg, ctx, seen, errs = page(b, w_, h_, q, mobile=True)
        check('phone %dx%d %r: no TV request, no tile' % (w_, h_, q),
              not tv_requests(seen) and pg.evaluate("() => !document.querySelector('[gs-id=tv]')"), tv_requests(seen))
        ctx.close()
    b.close()

say('')
say('%d checks failed' % len(fails))
for f_ in fails:
    say('  - ' + f_)
sys.exit(1 if fails else 0)
