"""R-IV.1369 -- the Regime pop-out, BOOK tile and CROWD tile, cleaned (as amended by R-IV.1381(e)).

Run:  python tests/test_r1369_agora_clean.py            (ENGINE=webkit for the WebKit pass)

EVERY FIXTURE HERE IS INVENTED. The account names, balances, positions and greeks are synthetic,
because the repo is public and the real book must never be committed (R-IV.1369(b)). The market
reads (regime, sections, crowd) are synthetic too, shaped like the live payloads. The one real
file is the registered playbook, served from the repo, so "verbatim" is checked against source.

Standing widths: 360x780 and 384x832 (Nick's Galaxy S25), 412x915, and 1920x1080.
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
    # This console is cp1252; a stray glyph would kill the run after the checks had passed.
    print(' '.join(str(x) for x in p).encode('ascii', 'replace').decode('ascii'))


def check(n, c, x=''):
    say(('PASS ' if c else 'FAIL ') + n + (' >> ' + str(x)[:300] if x and not c else ''))
    if not c:
        fails.append(n)


# ── static checks ────────────────────────────────────────────────────────────────────────
JS = io.open(os.path.join(ROOT, 'v2.js'), encoding='utf-8').read()
CSS = io.open(os.path.join(ROOT, 'assets', 'agora-clean.css'), encoding='utf-8').read()
HTML = io.open(os.path.join(ROOT, 'v2.html'), encoding='utf-8').read()

# R-IV.1369(d)2(iii): the warning signs ARE the registered tags, and cannot drift from them.
rules = json.load(io.open(os.path.join(REPO, 'backend', 'config', 'regime_rules.v2.1.json'), encoding='utf-8'))
m = re.search(r"const RC_TAGS = \[([^\]]*)\]", JS)
rc_tags = re.findall(r"'([^']+)'", m.group(1)) if m else None
check('RC_TAGS is exactly the rules file\'s tags.available', rc_tags == rules['tags']['available'],
      (rc_tags, rules['tags']['available']))

# D6: tokens only. Comments are stripped first, so a ruling number in prose cannot trip it.
css_code = re.sub(r'/\*.*?\*/', '', CSS, flags=re.S)
hexes = re.findall(r'#[0-9a-fA-F]{3,8}\b', css_code)
check('agora-clean.css carries no hex literal (D6)', not hexes, hexes)
check('the two new tokens are defined, at the ruled sizes',
      '--regime-hero: 40px' in CSS and '--tile-hero: 32px' in CSS)
check('the stylesheet loads AFTER v2.css on v2.html',
      0 < HTML.find('/v2.css?v=') < HTML.find('/assets/agora-clean.css?v='))
check('the rollback flag and its date are written down',
      "get('clean') !== 'off'" in JS and '2026-11-06' in JS)
check('B9 has a named mount point holding the ruled line',
      'id="b9-mount"' in JS and 'Global markets returns here once its live data is wired.' in JS)

# ── synthetic fixtures ───────────────────────────────────────────────────────────────────
FLIP = {
    'shown': 'RANGE CHOP', 'candidate': 'CORRECTION', 'candidate_differs': True,
    'held_sessions': 5, 'min_hold': 5,
    'in_progress': {'direction': 'in progress', 'target': 'correction', 'target_words': 'CORRECTION',
                    'condition': 'SYNTHETIC CONDITION FOR CORRECTION', 'closes_needed': 2,
                    'closes_basis': '2 settled closes', 'counter': {'banked': 1, 'needed': 2, 'text': '1 of 2'},
                    'proposing': True},
    'sectors': {'above': 5, 'total': 11, 'threshold': 5, 'basis': 'synthetic sectors'},
    'up_order': {'direction': 'one step up', 'target': 'melt_up', 'target_words': 'MELT UP',
                 'condition': 'SYNTHETIC CONDITION FOR MELT UP', 'closes_needed': 2, 'counter': None,
                 'proposing': False},
    'order_note': 'synthetic order note', 'no_distance_estimate': 'synthetic no-distance note',
}
# The proposed label IS also the down neighbour -- B8's "shown once" case.
FLIP['down_order'] = dict(FLIP['in_progress'], direction='one step down')
RIBBON = [('2026-10-13', 'correction'), ('2026-10-14', 'correction'), ('2026-10-15', None),
          ('2026-10-16', 'range_chop'), ('2026-10-19', 'range_chop'), ('2026-10-20', 'range_chop')]
REGIME = {
    'available': True, 'as_of': '2026-10-20', 'settled_close': '2026-10-20', 'regime_key': 'range_chop',
    'regime_label': 'RANGE / CHOP', 'rules_version': 'v2.1', 'tags': ['narrow', 'index-divergence'],
    'held_sessions': 5, 'flip_triggers': FLIP,
    'data_freshness': {'stale': True, 'newest_bar': '2026-10-20', 'lag_sessions': 3,
                       'headline': 'DATA STALE - last settled 2026-10-20', 'reason': 'synthetic lag'},
    'held_no_match': {'stale': False},
    'ma200_row': {'available': True, 'side': 'ABOVE', 'since': '2026-04-08', 'pct': 5.9,
                  'text': 'SPY vs 200-day: ABOVE since 2026-04-08', 'caveat': 'synthetic caveat',
                  'basis': 'synthetic basis'},
    'ribbon': {'sessions': [{'as_of': d, 'label': l, 'flipped': False} for d, l in RIBBON],
               'count': len(RIBBON), 'asked_for': 40, 'short_history': True, 'basis': 'synthetic'},
}
SECTIONS = {
    'live': True,
    'lamps': {'overlays': {'available': False, 'reason': 'not computed in v1'}},
    'credit': {'available': True, 'bp': 340.0, 'word': 'MIDDLING', 'change_20d_bp': 67.0, 'pct_rank': 99,
               'as_of': '2026-10-22', 'spark': [300.0, 320.0, 340.0]},
    'rates': {'available': True, 'rows': [
        {'key': 'real_10y', 'available': True, 'pct': 2.64, 'spark': [2.7, 2.64], 'change_20d_bp': 1.0},
        {'key': 'breakeven_10y', 'available': True, 'pct': 2.34, 'spark': [2.3, 2.34], 'change_20d_bp': -1.0}],
        'move': {'available': False, 'reason': 'no free source'}, 'basis': 'synthetic'},
    'leadership': {'available': True, 'headline': '1 of 3 ratios rising', 'basis': 'synthetic', 'rows': [
        {'name': 'RSP/SPY', 'available': True, 'change_pct': 4.1, 'spark': [1, 2], 'rising_means': 'x'},
        {'name': 'IWM/SPY', 'available': True, 'change_pct': -0.7, 'spark': [2, 1], 'rising_means': 'x'},
        {'name': 'SMH/SPY', 'available': True, 'change_pct': -11.6, 'spark': [2, 1], 'rising_means': 'x'}]},
    'zweig': {'available': True, 'fired': False, 'now_pct': 45.5, 'low_in_window': 27.3, 'from_pct': 40.0,
              'to_pct': 61.5, 'window': 10, 'reason': 'no thrust: synthetic', 'note': 'PROXY'},
    'auction': {'available': False, 'reason': 'synthetic: no snapshot'},
}
FUT = {'key': 'FUTURES', 'sub': 'CFTC - ES+NQ', 'value': 'net +12,345', 'pct': 85, 'pct_label': '85th',
       'extreme': False, 'thin': False, 'as_of': '2026-10-20', 'release_missed': False,
       'expected_as_of': '2026-10-20', 'history_n': 52, 'history_full': 52, 'mock': False,
       'staleness_note': 'synthetic', 'source': 'CFTC synthetic'}
PC = {'key': 'PUT/CALL', 'sub': 'UW FLOW \u00b7 5D \u00b7 20 tickers', 'value': '0.72', 'pct': 64,
      'pct_label': '64th', 'extreme': False, 'thin': True, 'as_of': '2026-10-23', 'history_n': 31,
      'history_full': 52, 'mock': False, 'source': 'UW flow synthetic'}
SI = {'key': 'SHORT INT', 'value': '3.03', 'pct': None, 'thin': True, 'mock': False, 'crowded_short': False,
      'crowded_short_at': 5.0, 'symbol': 'SPY', 'settlement_date': '2026-09-30', 'publish_date': '2026-10-12',
      'attribution': 'Source: FINRA', 'cadence': 'twice-monthly', 'source': 'FINRA synthetic'}
CROWD_A = {'live': True, 'headline': 'CROWD MIXED', 'headline_lean': 'neutral',
           'headline_basis': 'no live row at an extreme, 0 of 2 live rows', 'rows': [PC, FUT, SI],
           'settled_close': '2026-10-23', 'footnotes': ['synthetic footnote A'], 'caption': 'percentile'}
CROWD_B = dict(CROWD_A, headline='BEARS CROWDED', headline_lean='notable',
               headline_basis='1 at a bears-crowded extreme, 1 of 2 live rows',
               rows=[dict(PC, pct=95, thin=False, history_n=52), dict(FUT, release_missed=True, as_of='2026-10-13'),
                     dict(SI, value='6.10', crowded_short=True)])


def accts(full):
    """Three SYNTHETIC accounts. `full` = every position valued."""
    def a(name, disp, bal, cash, counted, unval, anchor):
        return {'account_name': name, 'account_display': disp, 'balance': bal, 'balance_cash': cash,
                'balance_positions_counted': counted, 'balance_positions_unvalued': unval,
                'balance_partial': bool(unval), 'balance_reason': 'synthetic partial' if unval else None,
                'cash_anchor': anchor, 'in_scope': True, 'updated_at': '2026-10-20T12:00:00Z'}
    return [
        # Fully priced, the formerly unvalued positions are COUNTED: the set is the same 24.
        a('ACCT_A', 'Account A', 2000.0, 1500.25, 10 if full else 9, [] if full else ['POS_A1'],
          {'as_of': '2026-09-24T23:55:39Z', 'as_of_is_instant': True}),
        a('ACCT_B', 'Account B', 12000.0, 8000.10, 6, [],
          {'as_of': '2026-09-24T23:59:59+00:00', 'as_of_is_instant': True}),
        a('ACCT_C', 'Account C', 11500.0, 9000.40, 8 if full else 6, [] if full else ['POS_C1', 'POS_C2'],
          {'as_of': '2026-09-22', 'as_of_is_instant': False}),
    ]


def pos(i, acct, status, legs):
    return {'id': 900 + i, 'position_id': 'POS_SYN_%d' % i, 'ticker': 'SYN%d' % i, 'account': acct,
            'account_display': acct, 'asset_type': 'OPTION' if legs else 'EQUITY',
            'structure': 'put_debit_spread' if legs else 'stock', 'open_quantity': 2, 'quantity': 2,
            'current_price': 1.0, 'unrealized_pnl': 5.0, 'cost_basis': 100.0, 'entry_price': 0.5,
            'mark_status': status, 'mark_checked_at': '2026-10-23T20:02:00Z', 'expiry': '2026-11-20',
            'dte': 27, 'legs': [{'leg_seq': n} for n in range(legs)]}


# Row 4 carries a 99-entry `legs` field ON PURPOSE. That jsonb is NOT the position_legs table
# (R-IV.697(c)1) -- on the live book it is null or a string on every option row -- so the tile must
# never count it. If it ever does, the greeks fraction below moves off "4 of 6" and the check fails.
POSITIONS = {'positions': [pos(1, 'ACCT_A', 'OK', 2), pos(2, 'ACCT_A', 'STALE', 2), pos(3, 'ACCT_B', 'OK', 0),
                           pos(4, 'ACCT_C', 'OK', 99), pos(5, 'ACCT_C', 'OK', 0)], 'count': 5}
GREEKS = {'status': 'ok', 'stale': True, 'computed_at': '2026-10-23T20:00:00Z',
          'totals': {'delta': -47.98, 'gamma': 5.5616, 'theta': -39.46, 'vega': 71.81},
          'coverage': {'legs_expected': 6, 'legs_priced': 4, 'complete': False, 'tickers_unavailable': 0,
                       'per_greek': {k: {'priced': 4, 'expected': 6} for k in ('delta', 'gamma', 'theta', 'vega')}}}
STATE = {'full': False, 'crowd': CROWD_A, 'anchorless': False}


def route(r):
    u = r.request.url

    def j(o, s=200):
        r.fulfill(status=s, content_type='application/json', body=json.dumps(o))

    if '/api/stable/regime-strategy' in u:
        return j(REGIME)
    if '/api/regime-sections' in u:
        return j(SECTIONS)
    if '/api/crowd' in u:
        return j(STATE['crowd'])
    if '/api/portfolio/balances' in u:
        b = accts(STATE['full'])
        if STATE['anchorless']:
            b[2]['cash_anchor'] = None
        return j(b)
    if '/api/portfolio/pnl' in u:
        return j({'daily': ({'dollar': -88.43, 'pct': -0.36} if STATE['full'] else {'dollar': None, 'pct': None}),
                  'accounts_partial': None if STATE['full'] else ['ACCT_A', 'ACCT_C']})
    if '/api/v2/positions/greeks' in u:
        return j(GREEKS)
    if '/api/v2/positions' in u:
        return j(POSITIONS if 'OPEN' in u else {'positions': [], 'count': 0})
    if '/api/board/kill-switch' in u:
        return j({'kill_switch': {'active': False}, 'provenance': {'source': 'event', 'age_seconds': 30}})
    if '/api/bias/composite' in u:
        return j({'bias_level': 'NEUTRAL', 'composite_score': 0.1,
                  'factors': {'vix_term': {'raw_data': {'ratio': 0.88, 'vix': 15.1, 'vix3m': 17.2},
                                           'timestamp': '2026-10-23T20:00:00Z'}}})
    return j({}, 404)


class H(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def translate_path(self, p):
        return os.path.join(ROOT, p.split('?')[0].lstrip('/') or 'v2.html')


srv = socketserver.TCPServer(('127.0.0.1', 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:%d/' % srv.server_address[1]
# Opt-in: SHOTDIR=<dir> saves each surface at each phone width, on these SYNTHETIC fixtures,
# for a human to look at. Never pointed inside the repo by default.
SHOTDIR = os.environ.get('SHOTDIR')


def shot(pg, sel, name):
    if not SHOTDIR:
        return
    os.makedirs(SHOTDIR, exist_ok=True)
    try:
        pg.locator(sel).first.screenshot(path=os.path.join(SHOTDIR, name + '.png'))
    except Exception as e:  # a missing screenshot must not fail the suite
        say('   (shot %s skipped: %s)' % (name, str(e)[:80]))


PB = json.load(io.open(os.path.join(ROOT, 'assets', 'regime', 'playbooks.v2.json'), encoding='utf-8'))['regimes']['range_chop']


def page(b, w, h, q=''):
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
    pg.goto(BASE + 'v2.html' + q, wait_until='domcontentloaded')
    pg.wait_for_timeout(2600)
    return pg, ctx, errs


def open_pop(pg):
    pg.evaluate("() => { const b = document.getElementById('rsOpen'); if (b) { b.scrollIntoView(); b.click(); } }")
    pg.wait_for_selector('#drawer.open', timeout=8000)
    pg.wait_for_timeout(500)


SMALL = """(sel) => { const out = []; document.querySelectorAll(sel).forEach((root) => {
  root.querySelectorAll('*').forEach((e) => {
    // An icon glyph (the ⓘ, role="img" with an aria-label) is not readable text.
    // #b9-mount's CONTENTS are BUILD's B9 section, styled by BUILD's b9_live.css; its sizes are
    // reported to BUILD, not asserted by this lane's suite.
    if (e.closest('.rg-evb') || e.closest('#b9-mount') || e.closest('[role="img"]') || e.children.length || !(e.textContent || '').trim()) return;
    const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return;
    const px = parseFloat(s.fontSize); if (px && px < 12) out.push((e.textContent||'').trim().slice(0,18) + ' @' + px); }); });
  return out.slice(0, 6); }"""
TAPS = """(sel) => [...document.querySelectorAll(sel)].filter((b) => { const r = b.getBoundingClientRect();
  const s = getComputedStyle(b); return r.width > 0 && s.display !== 'none' && s.visibility !== 'hidden'; })
  .filter((b) => b.getBoundingClientRect().height < 44)
  .map((b) => (b.textContent||'').trim().slice(0,16) + ' ' + Math.round(b.getBoundingClientRect().height))"""
OVER = """(sel) => { const e = document.querySelector(sel); return e ? e.scrollWidth - e.clientWidth : null; }"""

with sync_playwright() as p:
    ENGINE = os.environ.get('ENGINE', 'chromium')
    say('engine: ' + ENGINE)
    b = getattr(p, ENGINE).launch()

    # ══ 1. THE REGIME POP-OUT ═══════════════════════════════════════════════════════════
    pg, ctx, errs = page(b, 1920, 1080)
    open_pop(pg)
    pop = pg.evaluate("""() => {
      const q = (s) => document.querySelector(s), t = (s) => (q(s) || {}).innerText || '';
      const hero = q('.rg-hero'), hs = hero ? getComputedStyle(hero) : {};
      return { has: !!q('.rg'), hero: hero ? hero.textContent.trim() : null, heroPx: hs.fontSize,
        heroFont: hs.fontFamily, heroColor: hs.color, text: getComputedStyle(document.body).color,
        held: t('.rg-held'), cand: (q('.rg-cand') || {}).textContent, candColor: q('.rg-cand') ? getComputedStyle(q('.rg-cand')).color : null,
        chips: [...document.querySelectorAll('.rg-l1 .rg-chip')].map((c) => ({t: c.textContent.trim(), amber: c.classList.contains('rg-amber')})),
        cells: document.querySelectorAll('.rg-cell').length, none: document.querySelectorAll('.rg-cell.rg-none').length,
        legend: t('.rg-legend'), pb: t('.rg-pb'), chg: t('.rg-chg'),
        blocks: [...document.querySelectorAll('.rg-blk .rg-bh b')].map((x) => x.textContent.trim()),
        segs: document.querySelectorAll('.rg-seg').length, segsOn: document.querySelectorAll('.rg-seg.on').length,
        sbar: document.querySelectorAll('.rg-sseg').length,
        warn: [...document.querySelectorAll('.rg-warn .rg-chip')].map((c) => ({t: c.textContent.trim(), lit: c.classList.contains('rg-teal')})),
        warnFoot: t('.rg-warn .rg-foot'),
        ev: [...document.querySelectorAll('.rg-ev')].map((r) => ({k: r.dataset.ev, open: r.classList.contains('open'),
              st: (r.querySelector('.rg-st') || {}).textContent, stColor: getComputedStyle(r.querySelector('.rg-st')).color})),
        b9: q('#b9-mount') ? q('#b9-mount').textContent.trim() : null,
        b9After: !!(q('#b9-mount') && q('.rg-l3') && (q('.rg-l3').compareDocumentPosition(q('#b9-mount')) & 4)),
        title: t('#drawerTitle') };
    }""")
    check('pop-out: the cleaned view is the DEFAULT, with no query string', pop['has'], pop)
    check('pop-out: the headline is the label, NOT swapped for "DATA STALE"', pop['hero'] == 'RANGE / CHOP', pop['hero'])
    check('pop-out: the headline is Orbit at --regime-hero (40px)',
          pop['heroPx'] == '40px' and 'Orbit' in (pop['heroFont'] or ''), (pop['heroPx'], pop['heroFont']))
    check('pop-out: a NEUTRAL headline is --text, not --text-2', pop['heroColor'] == pop['text'], (pop['heroColor'], pop['text']))
    check('pop-out: "Held 5 sessions (minimum 5) - leaning toward CORRECTION"',
          'Held 5 sessions (minimum 5)' in pop['held'] and 'leaning toward' in pop['held'] and pop['cand'] == 'CORRECTION', pop['held'])
    check('pop-out: the candidate takes its lean colour', pop['candColor'] and pop['candColor'] != pop['text'], pop['candColor'])
    stale = [c for c in pop['chips'] if 'SESSIONS OLD' in c['t']]
    check('pop-out: the stale chip reads "3 SESSIONS OLD - TUE 10-20", amber, under the line',
          len(stale) == 1 and stale[0]['amber'] and stale[0]['t'].replace('\u00b7', '-') == '3 SESSIONS OLD - TUE 10-20', pop['chips'])
    check('pop-out: the kill and overlay chips are present, overlay says "no feed"',
          any('Kill switch' in c['t'] or 'KILL' in c['t'] for c in pop['chips'])
          and any('Event overlay: no feed' == c['t'] for c in pop['chips']), pop['chips'])
    check('pop-out: one ribbon cell per stored session, a SHORT history drawn short (not padded to 40)',
          pop['cells'] == len(RIBBON), pop['cells'])
    check('pop-out: a session with no reading is a dashed cell, and the legend counts it',
          pop['none'] == 1 and 'No reading 1' in pop['legend'] and 'SHORT HISTORY' in pop['legend'], pop['legend'])
    check('pop-out: playbook tape is VERBATIM from playbooks.v2.json', PB['tape'] in pop['pb'], pop['pb'][:160])
    check('pop-out: a premium over 90 chars shows first + last sentence and "more"',
          'more' in pop['pb'] and "sellers' market." in pop['pb'] and 'Long options decay without paying.' in pop['pb']
          and 'leveraged ETFs' not in pop['pb'], pop['pb'])
    check('pop-out: "Watch: " joins matters_now with " - "', ('Watch: ' + ' \u00b7 '.join(PB['matters_now'])) in pop['pb'])
    check('pop-out: the playbook footnote', 'From the registered playbook' in pop['pb'] and 'context, not a signal' in pop['pb'])
    check('pop-out: the proposed label that is ALSO the down neighbour is shown ONCE',
          [x for x in pop['blocks'] if 'CORRECTION' in x] == ['IN PROGRESS \u2192 CORRECTION'], pop['blocks'])
    check('pop-out: the up neighbour shows, "not in progress", with NO counter of its own',
          'ONE STEP UP \u2192 MELT UP' in pop['blocks'] and 'not in progress' in pop['chg'], pop['chg'][:300])
    check('pop-out: the counter is drawn as segments, banked of needed (1 of 2)',
          pop['segs'] == 2 and pop['segsOn'] == 1 and '1 of 2 closes' in pop['chg'], (pop['segs'], pop['segsOn']))
    check('pop-out: B8\'s sector bar stays, with the up side (11 segments)', pop['sbar'] == 11, pop['sbar'])
    check('pop-out: each neighbour\'s condition is VERBATIM',
          'SYNTHETIC CONDITION FOR CORRECTION' in pop['chg'] and 'SYNTHETIC CONDITION FOR MELT UP' in pop['chg'])
    check('pop-out: the "one step up" footnote', 'means the next label in the hub' in pop['chg'])
    lit = [w['t'] for w in pop['warn'] if w['lit']]
    check('pop-out: warning signs are the six registered tags, the lit ones teal with a filled dot',
          len(pop['warn']) == 6 and sorted(lit) == ['\u25cf Index divergence', '\u25cf Narrow'], pop['warn'])
    check('pop-out: "Warnings never change the label on their own."', pop['warnFoot'] == 'Warnings never change the label on their own.')
    check('pop-out: eight evidence families, every one collapsed', [r['k'] for r in pop['ev']] ==
          ['ma200', 'breadth', 'credit', 'rates', 'vol', 'lead', 'crowd', 'auction'] and not any(r['open'] for r in pop['ev']),
          [r['k'] for r in pop['ev']])
    ev = {r['k']: r for r in pop['ev']}
    check('pop-out: status words come from the reads (ABOVE, MIDDLING, CALM, MIXED)',
          ev['ma200']['st'] == 'ABOVE' and ev['credit']['st'] == 'MIDDLING' and ev['vol']['st'] == 'CALM'
          and ev['crowd']['st'] == 'MIXED', {k: v['st'] for k, v in ev.items()})
    check('pop-out: a family with no word shows its key number (rates, leadership)',
          ev['rates']['st'] == '2.64%' and ev['lead']['st'] == '1 of 3 ratios rising', (ev['rates']['st'], ev['lead']['st']))
    check('pop-out: an unavailable family shows "\u2014", not a guess', ev['auction']['st'] == '\u2014', ev['auction']['st'])
    check('pop-out: ABOVE takes the bull lean, not --text', ev['ma200']['stColor'] != pop['text'], ev['ma200']['stColor'])
    # One open at a time.
    pg.click('[data-rg-ev="credit"]'); pg.wait_for_timeout(150)
    a1 = pg.evaluate("() => [...document.querySelectorAll('.rg-ev.open')].map((r) => r.dataset.ev)")
    pg.click('[data-rg-ev="rates"]'); pg.wait_for_timeout(150)
    a2 = pg.evaluate("() => [...document.querySelectorAll('.rg-ev.open')].map((r) => r.dataset.ev)")
    pg.click('[data-rg-ev="rates"]'); pg.wait_for_timeout(150)
    a3 = pg.evaluate("() => [...document.querySelectorAll('.rg-ev.open')].map((r) => r.dataset.ev)")
    check('pop-out: tapping opens a row IN PLACE, one at a time, and tapping again closes it',
          a1 == ['credit'] and a2 == ['rates'] and a3 == [], (a1, a2, a3))
    pg.click('[data-rg-more]'); pg.wait_for_timeout(150)
    full = pg.evaluate("() => (document.querySelector('.rg-pfull') || {}).hidden === false")
    check('pop-out: "more" reveals the full premium', full)
    # BUILD's B9 (R-IV.1431) now FILLS the mount, as R-IV.1432(d) intended, so it holds either the
    # ruled line (B9 not loaded) or B9's own section. What this lane owns is the mount: its id, and
    # its place below the evidence.
    check('pop-out: #b9-mount sits below the evidence, holding the ruled line or B9\'s section',
          pop['b9After'] and (pop['b9'] == 'Global markets returns here once its live data is wired.'
                              or 'global markets' in (pop['b9'] or '').lower()), pop['b9'])
    check('pop-out: the header still carries the rules version', 'v2.1' in pop['title'], pop['title'])
    check('pop-out 1920: no errors', not errs, errs)
    ctx.close()

    # R-IV.1448(b)1: under 5 stored sessions, NO strip -- the amber chip and "fills in nightly".
    # From 5 on, the strip as above. Both sides of the boundary, because "4" and "5" are where an
    # off-by-one would hide.
    FULL_RIBBON = REGIME['ribbon']
    for n, drawn in ((1, False), (4, False), (5, True)):
        REGIME['ribbon'] = dict(FULL_RIBBON, sessions=FULL_RIBBON['sessions'][-n:], count=n)
        pg, ctx, errs = page(b, 1920, 1080)
        open_pop(pg)
        rb = pg.evaluate("""() => { const r = document.querySelector('.rg-ribbon');
          return { cells: document.querySelectorAll('.rg-cell').length, text: r ? r.innerText : '',
            chip: [...document.querySelectorAll('.rg-ribbon .rg-chip')].map((c) => ({t: c.textContent.trim(), amber: c.classList.contains('rg-amber')})) }; }""")
        chip = [c for c in rb['chip'] if c['t'].startswith('SHORT HISTORY')]
        check('ribbon, %d stored: the amber chip reads "SHORT HISTORY - %d OF 40"' % (n, n),
              len(chip) == 1 and chip[0]['amber'] and chip[0]['t'].replace('\u00b7', '-') == 'SHORT HISTORY - %d OF 40' % n, rb)
        if drawn:
            check('ribbon, %d stored: the strip IS drawn, one cell per session' % n, rb['cells'] == n, rb)
            check('...without the "fills in nightly" line', 'fills in nightly' not in rb['text'], rb['text'])
        else:
            check('ribbon, %d stored: NO strip is drawn' % n, rb['cells'] == 0, rb)
            check('...and the line says "fills in nightly"', 'fills in nightly' in rb['text'], rb['text'])
        check('ribbon, %d stored: no errors' % n, not errs, errs)
        ctx.close()
    REGIME['ribbon'] = FULL_RIBBON

    # ══ 2. THE BOOK TILE ════════════════════════════════════════════════════════════════
    BOOK = """() => { const q = (s) => document.querySelector(s), t = (s) => (q(s) || {}).innerText || '';
      return { has: !!q('.bk'), total: t('.bk-total'), day: t('.bk-dayv'), dayWhy: t('.bk-day'), box: t('.bk-box'),
        segs: document.querySelectorAll('.bk-segs i').length, segsOn: document.querySelectorAll('.bk-segs i.on').length,
        ok: t('.bk-ok'), rows: [...document.querySelectorAll('.bk-acct:not(.bk-cash)')].map((r) => ({
          n: (r.querySelector('.bk-an b') || {}).textContent, np: (r.querySelector('.bk-np') || {}).textContent || null,
          pc: (r.querySelector('.bk-pc') || {}).textContent || null, v: (r.querySelector('.bk-av') || {}).textContent })),
        cash: t('.bk-cash'), cashAmber: !!q('.bk-cash .rg-amber-t'), greeks: t('.bk-greeks'),
        info: (q('#bookInfo') || {}).title || '', panelBtnHidden: (q('#bookPanelBtn') || {}).hidden,
        stressHidden: (q('#bookStress') || {}).hidden, fold: t('#bookFoldBtn'), listHidden: (q('#bookPositions') || {}).hidden,
        foot: t('.bk-foot') }; }"""
    STATE.update(full=False)
    pg, ctx, errs = page(b, 1920, 1080)
    bk = pg.evaluate(BOOK)
    check('BOOK: the cleaned tile is the DEFAULT', bk['has'], bk)
    check('BOOK partial: "PARTIAL - 21 OF 24 POSITIONS PRICED" (positions, not legs)',
          'PARTIAL \u00b7 21 OF 24 POSITIONS PRICED' in bk['box'], bk['box'])
    check('BOOK partial: one segment per open position, 3 unpriced',
          bk['segs'] == 24 and bk['segsOn'] == 21, (bk['segs'], bk['segsOn']))
    check('BOOK partial: the sentence names the accounts and says Day P&L waits',
          'Account A' in bk['box'] and 'Account C' in bk['box'] and 'Day P&L waits' in bk['box'], bk['box'])
    check('BOOK partial: Day P&L is "\u2014" while any position is unpriced', bk['day'] == '\u2014', bk['day'])
    check('BOOK partial: the total keeps its \u2265 floor', bk['total'].startswith('\u2265'), bk['total'])
    rows = {r['n']: r for r in bk['rows']}
    check('BOOK partial: "n of m priced" ONLY where an account has unpriced positions',
          rows['Account A']['np'] == '9 of 10 priced' and rows['Account C']['np'] == '6 of 8 priced'
          and rows['Account B']['np'] is None, bk['rows'])
    shares = [int(r['pc'].rstrip('%')) for r in bk['rows'] if r['pc']]
    check('BOOK: account shares use largest remainder and sum to exactly 100 (#35)',
          len(shares) == 3 and sum(shares) == 100, shares)
    check('BOOK: a partial account keeps its \u2265 marker', rows['Account A']['v'].startswith('\u2265'), rows['Account A']['v'])
    check('BOOK: cash is part of the total and matches brokers as of the OLDEST anchor (09-22)',
          'Part of the total' in bk['cash'] and 'matches brokers 09-22' in bk['cash'], bk['cash'])
    # The fraction is the greeks route's own (4 of 6) -- and the route counts legs from
    # position_legs since BUILD's c94742bc. The 99-leg row above must not move it.
    tag_title = pg.evaluate("() => (document.querySelector('.bk-ptag') || {}).title || ''")
    check('BOOK: the greeks tag says its legs are read from position_legs, and never "not yet"',
          'from position_legs' in tag_title and 'not yet' not in tag_title, tag_title)
    check('BOOK partial: the greeks keep their floors and their own "partial - 4 of 6 legs"',
          '\u2265' in bk['greeks'] and 'partial \u00b7 4 of 6 legs' in bk['greeks'] and 'Theta \u2265\u2212$39/day' in bk['greeks'],
          bk['greeks'])
    check('BOOK: the row\'s `legs` jsonb is NEVER counted (a 99-leg row leaves "4 of 6" unmoved)',
          '99' not in bk['greeks'] and 'of 105' not in bk['greeks'], bk['greeks'])
    check('BOOK: Gamma moved behind the \u24d8, with the vintage note', 'Gamma 5.6' in bk['info']
          and 'vintage' in bk['info'], bk['info'][:200])
    check('BOOK: the header Positions button gives way to the footer link', bk['panelBtnHidden'] is True
          and 'Positions' in bk['foot'] and 'updated' in bk['foot'], bk['foot'])
    check('BOOK: the book-stress mock stays off the tile (e)7', bk['stressHidden'] is True)
    # R-IV.1382 put CLOSE in the Positions panel, so the live list LEAVES the tile (R-IV.1369(e)8)
    # instead of folding. The fold comes back only under ?pos=v1, whose panel has no Close.
    check('BOOK: the live positions list has left the tile for Positions -- no fold by default',
          not bk['fold'] and bk['listHidden'] is True, bk['fold'])
    _v1, _v1ctx, _v1errs = page(b, 1920, 1080, '?pos=v1')
    check('BOOK ?pos=v1: the old panel has no Close, so the list folds on the tile again',
          'Open positions' in _v1.evaluate("() => (document.getElementById('bookFoldBtn') || {}).innerText || ''"))
    _v1.click('#bookFoldBtn'); _v1.wait_for_timeout(200)
    check('BOOK ?pos=v1: the fold opens the list', _v1.evaluate("() => document.getElementById('bookPositions').hidden") is False)
    _v1ctx.close()
    pg.click('.bk-acct[data-bk-acct="ACCT_C"]'); pg.wait_for_timeout(500)
    # The panel CONSUMES the hand-off (R-IV.1382), so assert what the reader sees: Positions open,
    # filtered to the account whose row was tapped.
    opened = pg.evaluate("() => ({ open: !!document.querySelector('.pp-panel.open'), "
                         "acct: (document.querySelector('[data-pq-acct][aria-pressed=\"true\"]') || {}).dataset ? "
                         "document.querySelector('[data-pq-acct][aria-pressed=\"true\"]').dataset.pqAcct : null })")
    check('BOOK: an account row opens Positions filtered to its account', opened['open'] and opened['acct'] == 'ACCT_C', opened)
    check('BOOK partial 1920: no errors', not errs, errs)
    ctx.close()

    STATE.update(full=True)
    pg, ctx, errs = page(b, 1920, 1080)
    bk = pg.evaluate(BOOK)
    check('BOOK full: the box gives way to "All 24 positions priced - HH:MM MT"',
          not bk['box'] and re.search(r'All 24 positions priced \u00b7 \d\d:\d\d MT', bk['ok']), bk['ok'])
    check('BOOK full: Day P&L is a number', bk['day'] in ('\u2212$88',), bk['day'])
    check('BOOK full: the STALE marks are counted aloud', '1 stale mark counts as no change today' in bk['dayWhy'], bk['dayWhy'])
    check('BOOK full: no \u2265 on the total once every position is priced', not bk['total'].startswith('\u2265'), bk['total'])
    ctx.close()
    STATE.update(anchorless=True)
    pg, ctx, errs = page(b, 1920, 1080)
    bk = pg.evaluate(BOOK)
    check('BOOK: an account never re-anchored makes the cash line amber "not checked against brokers"',
          bk['cashAmber'] and 'not checked against brokers' in bk['cash'], bk['cash'])
    ctx.close()
    STATE.update(anchorless=False, full=False)

    # ══ 3. THE CROWD TILE ═══════════════════════════════════════════════════════════════
    CROWD = """() => { const q = (s) => document.querySelector(s), t = (s) => (q(s) || {}).innerText || '';
      const hero = q('.cg-hero'), hs = hero ? getComputedStyle(hero) : {};
      const rows = [...document.querySelectorAll('.cg-row')].map((r) => { const m = r.querySelector('.cg-m');
        return { h: (r.querySelector('.cg-h') || {}).innerText, line: (r.querySelector('.cg-line') || {}).innerText,
          left: m ? parseFloat(m.style.left) : null, thin: m ? m.classList.contains('thin') : null,
          asofAmber: !!r.querySelector('.cg-asof.rg-amber-t'), chip: (r.querySelector('.rg-chip') || {}).textContent || null }; });
      return { has: !!q('.cg'), hero: hero ? hero.textContent : null, heroPx: hs.fontSize, heroFont: hs.fontFamily,
        heroColor: hs.color, text: getComputedStyle(document.body).color, teal: getComputedStyle(document.documentElement).getPropertyValue('--teal'),
        basis: t('.cg-basis'), axis: t('.cg-axis'), rows, foot: t('.cg-foot'), info: (q('#crowdInfo') || {}).title || '',
        settledHidden: (q('#crowdSettled') || {}).hidden }; }"""
    STATE.update(crowd=CROWD_A)
    pg, ctx, errs = page(b, 1920, 1080)
    cg = pg.evaluate(CROWD)
    check('CROWD: the cleaned tile is the DEFAULT', cg['has'], cg)
    check('CROWD: the headline drops "CROWD ", Orbit at --tile-hero (32px)',
          cg['hero'] == 'MIXED' and cg['heroPx'] == '32px' and 'Orbit' in (cg['heroFont'] or ''), (cg['hero'], cg['heroPx']))
    check('CROWD: a neutral headline is --text', cg['heroColor'] == cg['text'], (cg['heroColor'], cg['text']))
    check('CROWD: one basis sentence under it', cg['basis'] == 'No live row at an extreme, 0 of 2 live rows', cg['basis'])
    check('CROWD: the one-axis legend', cg['axis'].replace('\n', ' ').startswith('\u25c0 BEARS CROWDED')
          and cg['axis'].strip().endswith('BULLS CROWDED \u25b6'), cg['axis'])
    fut, pc, si = cg['rows'][0], cg['rows'][1], cg['rows'][2]
    check('CROWD: FUTURES plots at pct (85)', fut['left'] == 85.0, fut)
    check('CROWD: PUT/CALL plots at 100 - pct (36): more puts means bears crowded, LEFT', pc['left'] == 36.0, pc)
    check('CROWD: FUTURES always shows its as-of, not amber when no release was missed',
          'AS OF TUE 10-20' in fut['h'] and not fut['asofAmber'], fut['h'])
    check('CROWD: "more long than 85% of the last 52 weekly readings"', 'more long than 85% of the last 52 weekly readings' in fut['line'], fut['line'])
    check('CROWD: PUT/CALL keeps its UW-flow label and is never called CBOE',
          'UW flow' in pc['h'] and 'CBOE' not in pc['h'] + pc['line'], pc['h'])
    check('CROWD: "0.72 over 5 days - more puts than 64% of the last 31 sessions ranked"',
          '0.72 over 5 days' in pc['line'] and 'more puts than 64% of the last 31 sessions ranked' in pc['line'], pc['line'])
    check('CROWD: a thin history turns the marker amber with "SHORT HISTORY - 31 OF 52"',
          pc['thin'] is True and pc['chip'] == 'SHORT HISTORY \u00b7 31 OF 52', pc)
    check('CROWD: SHORT INT has no gauge, "shown, not counted", and keeps "Source: FINRA" on its face',
          si['left'] is None and 'shown, not counted' in si['line'] and 'Source: FINRA' in si['line'] and 'SETTLED 09-30' in si['h'], si)
    check('CROWD: the footer, verbatim', cg['foot'] == 'Crowded means everyone is already positioned that way, which is '
          'fuel for a move the other way. Context, not a signal.', cg['foot'])
    check('CROWD: sources and the settled close moved behind the \u24d8',
          'synthetic footnote A' in cg['info'] and 'Settled close 2026-10-23' in cg['info'] and cg['settledHidden'] is True, cg['info'])
    check('CROWD 1920: no errors', not errs, errs)
    ctx.close()
    STATE.update(crowd=CROWD_B)
    pg, ctx, errs = page(b, 1920, 1080)
    cg = pg.evaluate(CROWD)
    fut, pc, si = cg['rows'][0], cg['rows'][1], cg['rows'][2]
    check('CROWD: BEARS CROWDED is teal (notable), not the bear colour', cg['hero'] == 'BEARS CROWDED'
          and cg['heroColor'] != cg['text'], cg['heroColor'])
    check('CROWD: the FUTURES as-of turns amber when a weekly release was missed', fut['asofAmber'] and 'AS OF TUE 10-13' in fut['h'], fut['h'])
    check('CROWD: days to cover at 5 or more shows the teal CROWDED SHORT chip', si['chip'] == 'CROWDED SHORT', si)
    ctx.close()
    STATE.update(crowd=CROWD_A)

    # ══ 4. PHONE, AND THE STANDING WIDTHS ═══════════════════════════════════════════════
    for (w, h) in ((360, 780), (384, 832), (412, 915)):
        pg, ctx, errs = page(b, w, h)
        for host in ('#bookStrip', '#crowdGauge'):
            check('%dpx: %s does not scroll sideways' % (w, host), (pg.evaluate(OVER, host) or 0) <= 1, pg.evaluate(OVER, host))
        check('%dpx: every BOOK button is at least 44px tall' % w, not pg.evaluate(TAPS, '#bookStrip button, #bookFoldBtn'),
              pg.evaluate(TAPS, '#bookStrip button, #bookFoldBtn'))
        tiny = pg.evaluate(SMALL, '#bookStrip, #crowdGauge')
        check('%dpx: no BOOK or CROWD text under 12px' % w, not tiny, tiny)
        shot(pg, '[gs-id="book"] .tile', 'book-%d' % w)
        shot(pg, '[gs-id="crowd"] .tile', 'crowd-%d' % w)
        open_pop(pg)
        shot(pg, '#drawer', 'popout-%d' % w)
        check('%dpx: the pop-out body does not scroll sideways' % w, (pg.evaluate(OVER, '#drawerBody') or 0) <= 1,
              pg.evaluate(OVER, '#drawerBody'))
        check('%dpx: every pop-out button is at least 44px tall' % w, not pg.evaluate(TAPS, '#drawer button, #drawerClose'),
              pg.evaluate(TAPS, '#drawer button, #drawerClose'))
        tiny = pg.evaluate(SMALL, '#drawerBody .rg')
        check('%dpx: no pop-out text under 12px (collapsed rows)' % w, not tiny, tiny)
        # R-IV.1381(e)3: scrolled to the end, the last line CLEARS the deck bar -- the arithmetic
        # that "the body reached its end" is not the same claim as "the end is on screen".
        clr = pg.evaluate("""() => { const b = document.getElementById('drawerBody'); b.scrollTop = b.scrollHeight;
          const bar = document.querySelector('.deck-bar'); if (!bar || getComputedStyle(bar).display === 'none') return {bar: false};
          let low = 0; b.querySelectorAll('*').forEach((e) => { if (e.children.length || !(e.textContent||'').trim()) return;
            const r = e.getBoundingClientRect(); if (r.height && r.bottom > low) low = r.bottom; });
          return {bar: true, gap: Math.round(bar.getBoundingClientRect().top - low)}; }""")
        check('%dpx: the pop-out\'s last line clears the deck bar' % w, (not clr['bar']) or clr['gap'] >= 0, clr)
        check('%dpx: no errors' % w, not errs, errs)
        ctx.close()

    # ══ 5. THE ROLLBACK: ?clean=off restores all three old surfaces ═════════════════════
    pg, ctx, errs = page(b, 1920, 1080, '?clean=off')
    old = pg.evaluate("() => ({ book: !!document.querySelector('#bookStrip .book-line'), bk: !!document.querySelector('.bk'),"
                      " crowd: !!document.querySelector('#crowdGauge .ag-head'), cg: !!document.querySelector('.cg') })")
    open_pop(pg)
    old['pv'] = pg.evaluate("() => !!document.querySelector('#pv-hero')")
    old['rc'] = pg.evaluate("() => !!document.querySelector('.rg')")
    check('?clean=off restores the old BOOK, CROWD and pop-out, and none of the new',
          old['book'] and old['crowd'] and old['pv'] and not (old['bk'] or old['cg'] or old['rc']), old)
    check('?clean=off: no errors', not errs, errs)
    ctx.close()
    b.close()

say('')
say('%d checks failed' % len(fails))
for f in fails:
    say('  - ' + f)
sys.exit(1 if fails else 0)
