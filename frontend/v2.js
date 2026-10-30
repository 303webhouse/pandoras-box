/* Dashboard v2 — "Judgment Layer" · Phase B2a shell.
   Grid + regime band + movers tape. All pollers via managedInterval (visibility-gated,
   idle budget < 10). Own module — no app.js / laboratory / analytics code loads here. */
(function () {
  'use strict';

  // ── Visibility-gated interval manager (P0 pattern) ─────────────────────────
  const _managed = new Map();
  let _seq = 0;
  function managedInterval(fn, ms) {
    const id = ++_seq;
    _managed.set(id, { fn, ms, timer: document.visibilityState === 'visible' ? setInterval(fn, ms) : null });
    return id;
  }
  document.addEventListener('visibilitychange', () => {
    const vis = document.visibilityState === 'visible';
    _managed.forEach((e) => {
      if (vis && e.timer === null) { e.timer = setInterval(e.fn, e.ms); try { e.fn(); } catch (_) {} }
      else if (!vis && e.timer !== null) { clearInterval(e.timer); e.timer = null; }
    });
  });

  // ── Central glossary (single source of truth for tooltips) ─────────────────
  const GLOSSARY = {
    HEALTH: 'Global data health — lime fresh, amber cannot confirm (unreadable or stale), grey market closed, vermilion source error, pulsing = dead feed',
    MOVERS: 'Top gainers/losers screener (Yahoo), filtered: last >= $2, avg vol >= 500k',
    REGIME: 'Two unrelated regime reads that share no inputs: Market mix (20 market-wide factors, every 15 min) and Theme breadth (one nightly number from your themed watchlist). Click for the detail.',
    COMPOSITE: 'Market mix — 20 market-wide factors (volatility, breadth, credit, trend, macro), recomputed every 15 min. Dial 0–100: under 20 URSA MAJOR · 20–39 URSA MINOR · 40–59 NEUTRAL · 60–79 TORO MINOR · 80+ TORO MAJOR. ▲/▼ = points to the next call.',
    STABLE: 'Theme breadth — % of your ~250-name themed watchlist above its 50-day average, computed nightly from the close. 70%+ STRONG BUY · 60–70 MODERATE BUY · 40–60 NEUTRAL · 30–40 MODERATE SELL · 30% or less STRONG SELL. (The backend still labels this RISK-ON / RISK-OFF at 60 / 40.)',
    DIVERGE: 'Lenses split — Market mix and Theme breadth point opposite ways by their own cut-offs. Size with caution.',
    DOM: 'Dominant theme — score >= 75',
    EMG: 'Emerging / improving theme',
    FAD: 'Fading / deteriorating theme',
    TIDE: 'Market tide — whole-market options flow since the open (UW, every 5 min in market hours). BULL FLOW = calls bought, puts sold · BEAR FLOW = the reverse · PREMIUM SELLING = both sides sold · TWO-WAY = mixed or light. A side counts at $25M+; the ± number is call minus put premium. Thresholds are provisional.',
    VOLCURVE: 'VIX ÷ VIX3M — near-term fear vs 3-month. Under 0.90 CALM · 0.90–0.99 FIRMING · 1.00+ STRESS (curve inverted). Calm is not a bullish call. Updates with the composite every 15 min.',
    BREADTH50: 'Percent of the scored universe above its 50-day moving average',
    BREADTH: 'Participation: % of universe above 20/50/200DMA, new highs/lows, ±3% movers',
    KILL: 'Kill switch (circuit breaker). ARMED = a market-risk breaker fired. CLEAR = the system confirmed no breaker is active this session. UNVERIFIED = no trip since the server started, but nothing proves the two TradingView alerts that arm it are alive (no heartbeat yet). UNKNOWN = the source could not be reached — not a clear.',
    THEMES: 'Ranked theme board: score, 1-day delta, and status (dominant/emerging/fading)',
    DIVERGENCE: 'Sectors vs SPY — each sector ETF’s 1-day % minus SPY’s, ranked. Leaders on top. The 1D/5D chart button opens the raw line chart.',
    INDEX: 'Major index 1-day % and ATR extension (how stretched vs typical range)',
    FUTURES: 'Overnight futures, shown whenever the stock market is not in its regular session (the server calendar decides; it flips back at the open). ES = S&P 500 · NQ = Nasdaq 100 · RTY = Russell 2000 · YM = Dow · plus crude oil and the 10-year note. Each % is measured from the futures price at the last 4 PM ET stock close (not the exchange settlement). The small line under each is the matching ETF in pre-market or after-hours. Yahoo data, about 10 minutes delayed: context for the open, not an entry trigger.',
    CURVE: 'Treasury yield curve with a 5-day-ago ghost line; bp = basis-point day change',
    USD: 'Dollar carry check — DXY and USD/JPY level and day change',
    BOOK: 'Open book: balance, day P&L, net Greeks, theme-concentration guardrail, and positions',
    ADD: 'Log a new position — calls the same create endpoint the legacy hub uses',
    KAIROS: 'Live actionable setups, ordered by grade / decision clock / regime fit',
    CLOCK: 'Decision clock — time left before this setup expires; pulses until you open it',
    GRADE: 'A = validated-cell match only (today: a liquid SHORT in a URSA regime); in NEUTRAL, no A is possible. B = ≥2 real evidence icons lit (R/F/L). C = fewer. Shadow setups never exceed their shadow tag. NOT the legacy score.',
    RIVER: 'Merged judged stream: signals, regime shifts, flow, catalysts, headlines',
    R: 'Regime alignment', F: 'Flow confirmation',
    L: 'At a Pythia level (VAH/VAL/POC) — evidence lights when price sits on a value-area level',
    C: 'Crowding — consensus positioning (post-flip metric; shown gray until wired, never faked)',
    VAH: 'Value-area high', VAL: 'Value-area low', POC: 'Point of control',
    GRIP: 'Drag to move · resize from the tile edges',
    DMA: 'Sector vs its moving averages — lime: above both 50 & 200DMA · vermilion: below both · gray: mixed',
    CONC: 'Theme concentration guardrail — turns vermilion when one theme exceeds 50% of at-risk book',
    FLOWTAG: "Today's options-flow screener sentiment for this name (▲ bullish / ▼ bearish premium) — only lights up for names the screener already tracks",
    KTAG: 'An active Kairos setup exists for this ticker right now — click to open committee context',
  };
  // Setup display map (UI-only; DB keys unchanged). shadow = never actionable A-grade.
  const SETUP_MAP = {
    ICARUS: { name: 'ICARUS', desc: 'Fade VAH' },
    HELEN: { name: 'HELEN', desc: 'Reclaim VA' },
    ARGO: { name: 'ARGO', desc: 'Range Break + Flow' },
    ACHILLES: { name: 'ACHILLES', desc: 'Sell the Rip' },   // Nick-approved 6th roster setup (sell_the_rip → codename Achilles)
    TRITON: { name: 'TRITON', desc: 'Whale Hunting', shadow: true },
    HERA: { name: 'HERA', desc: '3-10 Oscillator Cross', shadow: true },
    // R-IV.421 / R-IV.427(b): RIVER ONLY. Unbacktested shadow: never a Kairos card (Kairos is
    // for strategies with measured expectancy), never graded, never sized. Internal id
    // circes_stew; "Turtle Soup" is lineage only. Every fire carries the standing banner.
    CIRCES_STEW: { name: "CIRCE'S STEW", desc: 'Fade the Breakout', shadow: true, riverOnly: true,
      banner: "CIRCE'S STEW · SHADOW — unbacktested, no expectancy measured, do not size." },
  };
  // R-IV.421(d): above this many fires a day the trigger is too loose. The feed enforces the
  // limit; the River shows the count against it.
  const CIRCE_DAILY_CEILING = 10;
  // Calendar date in New York. A date label only: the session question belongs to the one
  // calendar server-side and is not asked here.
  const etDate = (ms) => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York' }).format(new Date(ms));
  function setupDisplay(key) {
    const k = String(key || '').toUpperCase();
    for (const id in SETUP_MAP) { if (k.indexOf(id) !== -1) return Object.assign({ roster: true }, SETUP_MAP[id]); }
    return { name: key || 'SETUP', desc: '', roster: false };
  }
  function applyGlossary(root) {
    (root || document).querySelectorAll('[data-gloss]').forEach((el) => {
      const g = GLOSSARY[el.getAttribute('data-gloss')];
      if (g) el.setAttribute('title', g);
    });
  }

  // ── Minimal fetch + login overlay (standalone auth, reuses /api/auth) ──────
  const _rawFetch = window.fetch.bind(window);
  let _loginShown = false;
  async function apiFetch(url, opts) {
    const r = await _rawFetch(url, opts);
    if (r.status === 401) showLogin();
    return r;
  }
  function showLogin() {
    if (_loginShown || document.getElementById('v2-login')) return;
    _loginShown = true;
    const ov = document.createElement('div');
    ov.id = 'v2-login';
    ov.style.cssText = 'position:fixed;inset:0;z-index:200;background:#050810;display:flex;align-items:center;justify-content:center;font-family:system-ui';
    ov.innerHTML = '<form style="background:#0b1122;padding:30px;border:1px solid #223258;border-radius:12px;display:flex;flex-direction:column;gap:12px;min-width:280px">'
      + '<div style="color:#14b8a6;font-weight:700;letter-spacing:2px">PANDORA</div>'
      + '<input id="v2pw" type="password" placeholder="Password" style="padding:10px;border-radius:6px;border:1px solid #223258;background:#050810;color:#e2e8f0">'
      + '<button type="submit" style="padding:10px;border:none;border-radius:6px;background:#14b8a6;color:#050810;font-weight:700;cursor:pointer">Sign in</button>'
      + '<div id="v2err" style="color:#ff5c33;font-size:12px;min-height:14px"></div></form>';
    document.body.appendChild(ov);
    ov.querySelector('#v2pw').focus();
    ov.querySelector('form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const r = await _rawFetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, body: JSON.stringify({ password: ov.querySelector('#v2pw').value }) });
      if (r.ok) location.reload();
      else ov.querySelector('#v2err').textContent = r.status === 401 ? 'Invalid password' : 'Login unavailable';
    });
  }

  // ── Helpers ────────────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const fmtPct = (v) => (v == null ? '--' : (v >= 0 ? '+' : '') + Number(v).toFixed(2) + '%');
  function ageLabel(sec) {
    if (sec == null) return 'unknown';
    if (sec < 90) return Math.round(sec) + 's';
    if (sec < 5400) return Math.round(sec / 60) + 'm';
    return Math.round(sec / 3600) + 'h';
  }
  // R-IV.410(c)/(d), R6+R7, design doc §7.7 -- the ruled four-state vintage chip. Shows the
  // ABSOLUTE instant a reading is true for; the relative age goes in the title only (relay
  // temporal-anchor law -- a bare "5m old" goes stale on a backgrounded PWA). Never red: an
  // unreachable/unreadable source is `unknown`, not the same alarm as a fired breaker (R7).
  // `unknownLabel`/`unknownTitle` let a caller say WHY it's unknown ("scope unknown", "balance
  // vintage not recorded") instead of the spec's generic "as of --" -- the two existing
  // callers keep their more specific text by passing it through here.
  function vintageChip({ iso, freshBoundSec, session, unknownLabel, unknownTitle } = {}) {
    if (session === 'closed') {
      const abs = iso && Number.isFinite(Date.parse(iso)) ? new Date(iso).toISOString().slice(11, 16) + 'Z' : null;
      return `<span class="vintage-chip" data-state="closed"${abs ? ` title="session closed ${esc(abs)}"` : ''}>closed${abs ? ' · ' + esc(abs) : ''}</span>`;
    }
    const t = iso ? Date.parse(iso) : NaN;
    if (!Number.isFinite(t)) {
      return `<span class="vintage-chip" data-state="unknown"${unknownTitle ? ` title="${esc(unknownTitle)}"` : ''}>${esc(unknownLabel || 'as of —')}</span>`;
    }
    const ageSec = Math.max(0, (Date.now() - t) / 1000);
    const bound = freshBoundSec || 900;
    const state = ageSec <= bound ? 'fresh' : 'stale';
    const abs = new Date(t).toISOString().slice(11, 16) + 'Z';
    const rel = ageLabel(ageSec);
    const title = state === 'fresh' ? `read ${rel} ago` : `${rel} old`;
    return `<span class="vintage-chip" data-state="${state}" data-fresh-s="${bound}" title="${esc(title)}">as of ${esc(abs)}</span>`;
  }
  // R-IV.413(e) — ONE mapping for every health dot AND every _health rank, so the two can
  // no longer disagree. v2.css:14-16 is the rule: amber means "we cannot confirm this";
  // vermilion means "confirmed bad"; an unreachable source is not a fired breaker.
  //   degraded === true   the payload REPORTED an error          -> 'down'        vermilion
  //   degraded == null    NO readable payload at all             -> 'unconfirmed' amber
  //   age null or > 900s  cannot confirm freshness               -> 'unconfirmed' amber
  //   flatline            pipe aged past its SLO (job record)    -> 'dead'        pulsing
  //   session 'closed'    market-hours feed outside the session  -> 'closed'      grey
  // Callers pass null for an absent payload. The old `data ? data.degraded : true` turned
  // "we received nothing" into "the source is broken", and no later code could undo it.
  //
  // R-IV.416(c) — CLOSED. A market-hours feed outside the session is correctly quiet, not
  // unconfirmed. `session` comes from the PAYLOAD ('open' | 'closed' | null), computed
  // server-side from THE market calendar (stable_engine/market_calendar.py). This file
  // never decides the session itself: a weekday/clock test here would be a second
  // calendar, which is the silent approximation that module exists to delete. An absent
  // or null session is NOT 'closed' -- it falls through to the age test.
  // R-IV.488(d) — `suspect`. Two plus two makes four before the dot turns green.
  // A served change that disagrees with its own served spot and prior close is not
  // a fresh number, whatever its timestamp says. On 2026-09-23 this dot read lime
  // 'fresh 8m' over QQQ +0.024% against a -0.69% tape: every input it had was
  // healthy, because none of them was the arithmetic. It ranks below 'down' (a
  // source that says it failed is worse than one whose sum does not close) and
  // above every freshness state, which can never redeem a number that is wrong.
  function healthState(ageSec, degraded, flatline, session, incoherent) {
    if (flatline) return 'dead';
    if (degraded === true) return 'down';
    if (incoherent) return 'suspect';
    if (degraded == null) return 'unconfirmed';
    if (session === 'closed') return 'closed';
    if (ageSec == null || ageSec > 900) return 'unconfirmed';
    return 'ok';
  }
  function paintDot(el, st) {
    el.className = 'health-dot' + (st ? ' ' + st : '');
  }
  function setHealth(el, ageSec, degraded, flatline, session, note, incoherent) {
    if (!el) return;
    const st = healthState(ageSec, degraded, flatline, session, incoherent && incoherent.length);
    let txt;
    if (st === 'dead') txt = 'DEAD — data pipe flatlined (aged past its SLO)';
    else if (st === 'suspect') txt = 'SUSPECT — ' + incoherent.join(', ') + ': the change shown does not equal spot / prior close - 1. Do not trade off these until it clears.';
    else if (st === 'down') txt = 'degraded — the source reported an error';
    else if (st === 'closed') txt = 'closed — market session not open' + (ageSec != null ? '; last update ' + ageLabel(ageSec) + ' ago' : '');
    else if (st === 'unconfirmed') {
      txt = degraded == null ? 'unknown — no readable payload; cannot confirm'
          : ageSec == null ? 'unknown age — cannot confirm freshness'
          : 'stale ' + ageLabel(ageSec) + ' — cannot confirm freshness';
    } else txt = 'fresh ' + ageLabel(ageSec);
    paintDot(el, st);
    el.setAttribute('title', note ? txt + ' · ' + note : txt);
  }

  const _health = { regime: null, movers: null };
  const _flat = {}; // feed -> flatline bool
  function updateGlobalHealth() {
    const anyFlat = Object.values(_flat).some(Boolean);
    const vals = Object.values(_health).filter((v) => v !== null);
    // 'closed' ranks below 'ok': one open, fresh feed makes the whole board 'ok'; the board
    // reads 'closed' only when every ranked feed is closed.
    const worst = (anyFlat || vals.includes('dead')) ? 'dead' : vals.includes('down') ? 'down' : vals.includes('suspect') ? 'suspect' : vals.includes('unconfirmed') ? 'unconfirmed' : vals.includes('ok') ? 'ok' : vals.length ? 'closed' : '';
    const dot = $('dataHealthDot');
    paintDot(dot, worst);
    // R-IV.1246(c)2: it monitors the WORST state across every ranked feed, so the
    // tooltip NAMES them. A dot whose tooltip gives only a verdict cannot be acted on:
    // "DEAD feed(s)" leaves the reader hunting for which one.
    const ranked = Object.keys(_health).filter((k) => _health[k] !== null);
    const flat = Object.keys(_flat).filter((k) => _flat[k]);
    const whichFlat = flat.length ? ' — flatlined: ' + flat.join(', ') : '';
    const watching = ranked.length ? '\n\nwatching: ' + ranked.sort().join(', ') : '';
    dot.setAttribute('title', GLOSSARY.HEALTH + whichFlat + ' — ' + (worst === 'dead' ? 'DEAD feed(s) — pipe flatlined' : worst === 'suspect' ? 'SUSPECT — a displayed change does not match its own spot and prior close' : worst === 'down' ? 'a source reported an error' : worst === 'unconfirmed' ? 'cannot confirm — a feed is unreadable or stale' : worst === 'closed' ? 'market session not open' : (worst || 'no data')) + watching);
  }
  // Record a feed's flatline state; adds exactly one River action item per incident
  // (River dedups by id) and removes it on recovery.
  function noteFlatline(feed, isFlat, label) {
    const was = !!_flat[feed]; _flat[feed] = !!isFlat;
    const id = 'flatline:' + feed;
    if (isFlat) {
      addRiverItems([{ id, type: 'regime', tier: 'action', sev: 'down', ts: Date.now(),
        text: `<b>DEAD · ${esc(label || feed)} feed flatlined</b> — data pipe aged past its SLO (not just stale). Check /health → stable_jobs.` }]);
    } else if (was) { _river.delete(id); _rvAcked.delete(id); }
    if (was !== !!isFlat) renderRiver();
    updateGlobalHealth();
  }

  // ── Regime band ─────────────────────────────────────────────────────────────
  // Composite score is on a -1..+1 scale; render as X/100 to match the legacy banner:
  const to100 = (s) => (s == null || !Number.isFinite(Number(s))) ? null : Math.round(((Number(s) + 1) / 2) * 100);
  let _lastRegime = { composite: null, regime: null, tide: null, kill: null };

  // When the kill-switch payload was last successfully READ. Distinct from the age
  // of the STATE: a two-hour-old CLEAR rendered as fresh is fail-open wearing a
  // valid 200, so the cell must be able to disclose how old its reading is.
  let _killReadAt = null;

  function fmtAge(sec) {
    if (sec == null || !Number.isFinite(Number(sec))) return null;
    const s = Math.max(0, Math.round(Number(sec)));
    if (s < 60) return s + 's';
    if (s < 3600) return Math.round(s / 60) + 'm';
    if (s < 86400) return (s / 3600).toFixed(s < 36000 ? 1 : 0) + 'h';
    return Math.round(s / 86400) + 'd';
  }

  // ── Kill-switch cell: five truthful states (DEF-KILLSWITCH-FAILOPEN) ────────
  // The old renderer collapsed a failed fetch AND a null payload into "CLEAR /
  // normal" — the operator-facing safety surface asserting all-clear from an
  // absence of information. It must never say CLEAR unless the system said CLEAR.
  //
  // Authority rule (A1): `active` comes from the backend's in-memory state, which
  // is what the enforcers (composite, bias_scheduler) actually act on. A persisted
  // Redis record is PROVENANCE ONLY and never promotes the cell to ARMED — a board
  // asserting protection the system isn't applying is worse than the original bug.
  function killCellView(kill, readAt) {
    // `kill` is null only when the fetch threw or returned non-200 (see loadRegimeBand).
    // Single return point below — an early return here would skip the shared tail
    // (size class, divergence, stale-read) and silently emit a broken class string.
    const unreachable = !kill || !kill.kill_switch;
    const k = (kill && kill.kill_switch) || {};
    const p = (kill && kill.provenance) || {};
    // No provenance (older backend) => cannot claim an event confirmed anything.
    // Degrade toward the non-asserting state rather than toward reassurance.
    const source = p.source || 'default-since-boot';
    const stateAge = fmtAge(p.age_seconds);

    // Reading age — surfaced once it is old enough to matter (backgrounded PWA).
    const readAge = readAt != null ? (Date.now() - readAt) / 1000 : null;
    const staleRead = readAge != null && readAge > 120 ? 'reading ' + fmtAge(readAge) + ' old' : null;

    // ONE detail line, not two. The regime band is a fixed-height grid whose row is
    // sized by its tallest cell: a fourth line here grew every cell 87px -> 98px and
    // overflowed the band, which would clip the provenance away. Wording is kept
    // compact so it holds one line at the 232px desktop cell width.
    // `state` drives the top-bar beacon; `display_state` from the payload is never read (it
    // says CLEAR even for default-since-boot, which is exactly the fail-open this avoids).
    let v;
    if (unreachable) {
      v = { state: 'unknown', label: 'UNKNOWN', cls: 'val-amber', pulse: '', num: '',
            prov: 'source unreachable — not a clear', provCls: 'val-amber' };
    } else if (k.active) {
      const pending = !!k.pending_reset;
      const firedAge = fmtAge(k.triggered_at ? (Date.now() - Date.parse(isoUtc(k.triggered_at))) / 1000 : p.age_seconds);
      const trig = esc(k.trigger || 'risk-off');
      v = {
        // pending_reset still means active=true — the breaker is still enforcing
        // caps/floors until an operator accepts. It stays in the ARMED family.
        state: 'armed', label: pending ? 'ARMED · PENDING' : 'ARMED',
        cls: 'val-down', pulse: ' pulse-vermilion', num: firedAge || '',
        prov: pending ? trig + ' · awaiting reset, still enforcing'
                      : trig + (firedAge ? ' · fired ' + firedAge + ' ago' : ''),
        provCls: 'val-down',
      };
      // The hub checks SPY itself on a fire; when its own reading does not confirm the
      // TradingView alert, say so rather than let a disputed trip read as a clean one.
      if (k.disputed) v.prov += ' · disputed: hub reading ' + esc(typeof k.disputed === 'string' ? k.disputed : (k.hub_reading != null ? k.hub_reading : 'does not confirm'));
    } else if (source === 'event-confirmed') {
      v = { state: 'clear', label: 'CLEAR', cls: 'val-teal', pulse: '', num: '',
            prov: 'confirmed this session' + (stateAge ? ' · ' + stateAge : ''), provCls: '' };
    } else if (source === 'restored-at-boot') {
      v = { state: 'clear', label: 'CLEAR', cls: 'val-teal', pulse: '', num: '',
            prov: 'restored at startup' + (stateAge ? ' · ' + stateAge : ''), provCls: '' };
    } else {
      // No trip recorded since the server started. That is ALSO exactly what a dead or expired
      // TradingView alert looks like: the only things that can arm this switch are two remote
      // alerts, and nothing yet proves they are alive (no heartbeat). So this is UNVERIFIED,
      // not a reassuring resting state (Olympus/Titans review 2026-09-30).
      v = { state: 'unverified', label: 'UNVERIFIED', cls: 'val-amber', pulse: '', num: '',
            prov: 'no trip since boot' + (stateAge ? ' ' + stateAge : '') + ' · watcher not proven alive', provCls: 'val-amber' };
    }

    // A1 divergence — disclosed as a provenance value, not a sixth visual state.
    // Provenance overlays apply only when we actually have a payload to describe.
    if (!unreachable) {
      if (p.divergence) { v.prov = esc(p.divergence); v.provCls = 'val-amber'; }
      else if (p.persisted_record === 'unreadable') { v.prov += ' · record unreadable'; v.provCls = 'val-amber'; }
      if (staleRead) { v.prov += ' · ' + staleRead; v.provCls = 'val-amber'; v.staleRead = true; }
    }
    v.source = unreachable ? null : source;
    return v;
  }

  // ── Kill switch: IN THE REGIME CARD, NOT THE HEADER (R-IV.1246(c)3) ─────────
  //
  // It was a permanent top-bar pill reading "KILL · CLEAR" — loud while saying everything was
  // fine, which is the alarm nobody reads. It now renders ONLY when armed, in the Regime
  // Strategy card's own badge and in its drawer, keeping the vermilion alarm pulse
  // R-IV.1209(d) ruled. When it is not armed, nothing renders: an absent badge is the honest
  // display of "not armed", and it leaves the card's header to the label.
  //
  // THE UNKNOWN STATE STILL SHOWS. "We cannot read the kill switch" is not "the kill switch is
  // clear", and collapsing the two would be fail-open with a tidier header.
  const _unesc = (s) => { const t = document.createElement('textarea'); t.innerHTML = String(s || ''); return t.value; };
  let _lastKillView = null;
  function renderKillBeacon(kill) {
    const v = killCellView(kill, _killReadAt);
    _lastKillView = v;
    const badge = $('rsKill');
    if (!badge) return;
    const show = v.state === 'armed' || v.state === 'unknown';
    badge.hidden = !show;
    if (!show) {
      badge.className = 'dead-badge';
      badge.removeAttribute('title');
      return;
    }
    badge.textContent = v.state === 'armed'
      ? ('KILL · ' + v.label + (v.num ? ' ' + v.num : '')) : 'KILL · ?';
    badge.className = 'dead-badge' + (v.state === 'armed' ? ' pulse-vermilion' : ' ks-unknown');
    badge.title = 'Kill switch: ' + v.label + ' — ' + _unesc(v.prov)
      + (v.source ? ' (' + v.source + ')' : '') + '\n\n' + GLOSSARY.KILL;
  }

  async function loadRegimeBand() {
    let composite = null, regime = null, tide = null, kill = null;
    try { const r = await apiFetch('/api/bias/composite'); if (r.ok) composite = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/stable/regime'); if (r.ok) regime = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/board/tide'); if (r.ok) tide = await r.json(); } catch (_) {}
    // A non-200 or a throw must leave `kill` null so the cell renders UNKNOWN.
    // Only stamp the read clock on an actual success.
    try { const r = await apiFetch('/api/board/kill-switch'); if (r.ok) { kill = await r.json(); _killReadAt = Date.now(); } } catch (_) {}
    _lastRegime = { composite, regime, tide, kill };
    quoteTick(composite && (composite.bias_level || composite.level));
    renderKillBeacon(kill);
    renderRegimeBand(composite, regime, tide, kill);
    renderBreadthPanel(regime);          // b3 shares the regime payload
    emitRegimeRiverItems(composite, regime, kill);

    const age = regime && regime.data_age_seconds != null ? regime.data_age_seconds : null;
    const degraded = regime ? !!regime.degraded : null;   // null = no payload (R-IV.413(e))
    _health.regime = healthState(age, degraded, regime && regime.flatline, regime && regime.session);
    noteFlatline('nightly', regime && regime.flatline, 'Regime / Themes');
    updateGlobalHealth();
  }

  // ── Regime views (pure: payload in, what to show out) ───────────────────────
  // Naive timestamps (no offset) from this backend are UTC. Date.parse reads a naive string as
  // LOCAL time, which in Mountain time puts a fresh reading 6 h in the future and pins its age
  // chip at "fresh" forever. Every new call site goes through this.
  function isoUtc(s) {
    if (!s) return null;
    const str = String(s);
    return /[zZ]$|[+-]\d\d:?\d\d$/.test(str) ? str : str + 'Z';
  }
  // Composite dial 0-100. floor, not round: the backend bands are score >= -0.60 / -0.20 /
  // +0.20 / +0.60 (composite.py score_to_bias) = dial [20, 40, 60, 80), so flooring keeps the
  // number inside the band its label names ("56 · ▲4 to TORO MINOR" lands exactly on 60).
  const dial100 = (s) => (s == null || !Number.isFinite(Number(s))) ? null : Math.floor((Number(s) + 1) * 50);
  const LENS1_CUTS = [20, 40, 60, 80];
  const levelWords = (l) => String(l || '').replace(/_/g, ' ');
  function levelForDial(d) { return d >= 80 ? 'TORO_MAJOR' : d >= 60 ? 'TORO_MINOR' : d >= 40 ? 'NEUTRAL' : d >= 20 ? 'URSA_MINOR' : 'URSA_MAJOR'; }
  const dirOfLevel = (l) => (/TORO|BULL/.test(l || '') ? 1 : /URSA|BEAR/.test(l || '') ? -1 : 0);

  // Lens 1 — MARKET MIX: the 20-factor composite, in the backend's own five words.
  function lens1View(c) {
    const lvl = c ? (c.bias_level || c.level || null) : null;
    if (!lvl) return { call: '—', cls: 'val-muted', num: '', dist: 'no reading', dir: 0,
                       held: false, pct: null };
    const d = dial100(c.composite_score), dir = dirOfLevel(lvl);
    const cls = dir > 0 ? 'val-up' : dir < 0 ? 'val-down' : 'val-teal';
    let dist = '', held = false;
    if (d != null && levelForDial(d) !== lvl) {
      // An override or a kill-switch cap/floor is holding the level away from what the score
      // implies, so a "distance to flip" would be a lie. Say what is holding it instead.
      held = true;
      const cb = c.circuit_breaker;
      dist = c.override ? 'held by override' : (cb && (cb.active || cb.bias_cap || cb.bias_floor)) ? 'held by kill-switch cap' : 'held (level differs from score)';
    } else if (d != null) {
      const up = LENS1_CUTS.find((e) => e > d);
      const down = LENS1_CUTS.filter((e) => e <= d).pop();
      const opts = [];
      if (up != null) opts.push({ n: up - d, txt: '▲' + (up - d) + ' to ' + levelWords(levelForDial(up)) });
      if (down != null) opts.push({ n: d - down + 1, txt: '▼' + (d - down + 1) + ' to ' + levelWords(levelForDial(down - 1)) });
      opts.sort((a, b) => a.n - b.n);
      dist = opts.length ? opts[0].txt : '';
    }
    // `pct` is the 0-100 dial the zone gauge sits on (A2). Returned rather than re-derived
    // in the renderer: two derivations of one position would eventually disagree.
    return { call: levelWords(lvl), cls, num: d != null ? String(d) : '', dist, dir, held,
             pct: d };
  }

  // Lens 2 — THEME BREADTH: % of the scored watchlist above its 50-day, in buy/sell words.
  // DISPLAY ONLY: the backend regime_label (RISK-ON / RISK-OFF, which Olympus reads via MCP) is
  // unchanged. The 60/40 lines are the backend's own (>= 60 / <= 40, stable.py); 70/30 add the
  // STRONG tier (Nick, 2026-09-30).
  /**
   * The four breadth cut-offs as gauge positions, FROM THE PAYLOAD. B1 (R-IV.1209(e)): "gauges
   * from the real thresholds". The backend owns 60/40 (`risk_on_pct_above_50dma` /
   * `risk_off_pct_above_50dma`) and can move them; 70/30 add the STRONG tier. A tick drawn at a
   * number the backend no longer uses is worse than no tick -- it is a scale that lies.
   *
   * The percentage IS the position here, because the gauge runs 0-100% above the 50-day.
   */
  function lens2Ticks(th) {
    const on = (th && th.risk_on_pct_above_50dma) || 60;
    const off = (th && th.risk_off_pct_above_50dma) || 40;
    return [30, off, on, 70].sort((a, b) => a - b);
  }

  function lens2Call(p, th) {
    const on = (th && th.risk_on_pct_above_50dma) || 60, off = (th && th.risk_off_pct_above_50dma) || 40;
    if (p >= 70) return ['STRONG BUY', 2];
    if (p >= on) return ['MODERATE BUY', 1];
    if (p > off) return ['NEUTRAL', 0];
    if (p > 30) return ['MODERATE SELL', -1];
    return ['STRONG SELL', -2];
  }
  function lens2View(r) {
    const p = r && r.breadth ? r.breadth.pct_above_50dma : null;
    if (p == null || !Number.isFinite(Number(p))) return { call: '—', cls: 'val-muted',
        num: '', dist: 'no reading', dir: 0, pct: null };
    const th = r.thresholds || {};
    const [call, lvl] = lens2Call(Number(p), th);
    // Distance to the nearer neighbouring call, in 0.1-point steps (integer tenths: no float drift).
    const t = Math.round(Number(p) * 10);
    let best = null;
    for (const sgn of [1, -1]) {
      for (let k = 1; k <= 1000; k++) {
        const q = (t + sgn * k) / 10;
        if (q < 0 || q > 100) break;
        const c2 = lens2Call(q, th);
        if (c2[0] !== call) { if (!best || k < best.k) best = { k, sgn, call: c2[0] }; break; }
      }
    }
    const dist = best ? (best.sgn > 0 ? '▲' : '▼') + (best.k / 10).toFixed(1) + ' to ' + best.call : '';
    return { call, cls: lvl > 0 ? 'val-up' : lvl < 0 ? 'val-down' : 'val-teal',
             num: Number(p).toFixed(1) + '%', dist, dir: Math.sign(lvl), pct: Number(p) };
  }
  // The lenses "split" only when they point opposite ways by their OWN cut-offs.
  const lensSplit = (v1, v2) => v1.dir !== 0 && v2.dir !== 0 && v1.dir !== v2.dir;

  // Tide as a flow TYPE, not a bare "calls > puts" sign. UW's net premium is ask-side minus
  // bid-side: negative means that side was net SOLD. PROVISIONAL thresholds, to be calibrated
  // from the market-hours audit (2026-09-30).
  const TIDE_MIN = 25e6, TIDE_STRONG = 100e6;
  const fmtMabs = (v) => '$' + Math.round(Math.abs(v) / 1e6) + 'M';
  const fmtMsigned = (v) => (v >= 0 ? '+' : '−') + Math.round(Math.abs(v) / 1e6) + 'M';
  function tideView(tide, quietSince, closed) {
    const t = tide && tide.tide;
    if (!t || t.net_call_premium == null || t.net_put_premium == null) {
      // The session is the server's answer (serverSession, R-IV.416(c)). Only when that is
      // unknown is "closed" inferred, from the market feeds having ALSO gone quiet.
      if (closed) return { word: 'NO READING', cls: 'val-muted', lean: '', line2: 'market closed · flow resumes at the open', chip: 'closed' };
      if (quietSince) return { word: 'NO READING', cls: 'val-muted', lean: '', line2: 'feeds quiet since ' + quietSince + ' (likely closed)', chip: 'closed?' };
      return { word: '—', cls: 'val-muted', lean: '', line2: 'no flow reading', chip: 'unknown' };
    }
    const nc = Number(t.net_call_premium), np = Number(t.net_put_premium);
    const cOn = Math.abs(nc) >= TIDE_MIN, pOn = Math.abs(np) >= TIDE_MIN;
    const lean = nc - np;
    let word;
    if (!cOn && !pOn) word = 'TWO-WAY';
    else if (cOn && pOn && nc > 0 && np < 0) word = 'BULL FLOW';
    else if (cOn && pOn && nc < 0 && np > 0) word = 'BEAR FLOW';
    else if (cOn && pOn && nc < 0 && np < 0) word = 'PREMIUM SELLING';
    else word = lean >= TIDE_STRONG ? 'BULL FLOW' : lean <= -TIDE_STRONG ? 'BEAR FLOW' : 'TWO-WAY';
    const cls = word === 'BULL FLOW' ? 'val-up' : word === 'BEAR FLOW' ? 'val-down' : word === 'PREMIUM SELLING' ? 'val-quiet' : 'val-dim';
    const side = (v, name) => name + ' ' + (v >= 0 ? 'bought ' : 'sold ') + fmtMabs(v);
    return { word, cls, lean: (word === 'BULL FLOW' || word === 'BEAR FLOW') ? fmtMsigned(lean) : '',
      line2: side(nc, 'calls') + ' · ' + side(np, 'puts'), chip: 'live' };
  }

  // VOL CURVE — VIX ÷ VIX3M from the composite's own vix_term factor (the same number the
  // kill switch will use). Classified on the DISPLAYED two decimals, so "0.90" never reads CALM.
  // CALM is --text, never lime: calm volatility is not a bullish call (HELIOS).
  // B1 (R-IV.1209(e)): ONE SOURCE FOR THE VOL BANDS. The WORDS came from 0.90 / 1.00 and the
  // gauge's ticks were hard-coded 33.33% / 66.67% in the markup -- two numbers for one
  // threshold, which drift the moment either is tuned. `volPct` is the only mapping from a
  // ratio to a gauge position, and the ticks are that mapping applied to the band edges.
  const VOL_FIRMING_AT = 0.90, VOL_STRESS_AT = 1.00;
  const VOL_GAUGE_LO = 0.80, VOL_GAUGE_SPAN = 0.30;
  const volPct = (r) => Math.max(0, Math.min(100, (r - VOL_GAUGE_LO) / VOL_GAUGE_SPAN * 100));
  const VOL_TICKS = [volPct(VOL_FIRMING_AT), volPct(VOL_STRESS_AT)];

  function volCurveView(c) {
    const f = c && c.factors && c.factors.vix_term;
    const raw = f && f.raw_data;
    const ratio = raw && Number.isFinite(Number(raw.ratio)) ? Number(raw.ratio) : null;
    if (ratio == null) return { value: '—', word: '', cls: 'val-muted', sub: 'VIX term structure not read', pct: null, iso: null, stale: true };
    const shown = Math.round(ratio * 100) / 100;
    const word = shown >= VOL_STRESS_AT ? 'STRESS'
      : shown >= VOL_FIRMING_AT ? 'FIRMING' : 'CALM';
    const stale = (c.stale_factors || []).includes('vix_term') || JSON.stringify(c.excluded_factors || []).includes('vix_term');
    return {
      value: shown.toFixed(2), word, cls: word === 'STRESS' ? 'val-down' : word === 'FIRMING' ? 'val-teal' : 'val-quiet',
      sub: 'VIX ' + (raw.vix != null ? Number(raw.vix).toFixed(1) : '--') + ' ÷ 3M ' + (raw.vix3m != null ? Number(raw.vix3m).toFixed(1) : '--'),
      pct: volPct(ratio), iso: isoUtc(f.timestamp), stale,
    };
  }

  // A reading that IS a close (nightly data): honest to call it closed, no clock needed.
  function closeChip(dateStr, bad, why) {
    const d = dateStr ? String(dateStr).slice(5, 10) : null;
    if (!d) return vintageChip({ unknownLabel: 'as of —' });
    return `<span class="vintage-chip" data-state="${bad ? 'stale' : 'closed'}" title="${esc(why || 'computed from the ' + dateStr + ' close; recomputes nightly ~9 PM ET')}">closed · ${esc(d)} close</span>`;
  }
  // "Feeds quiet since" — from the index strip's own age, the inference the Tide cell uses
  // only when the server's session answer is missing.
  let _ixData = null;
  let _ext = null;   // /api/stable/futures — overnight futures + pre/after-hours ETFs
  // THE session, as the server's calendar answers it (stable_engine/sessions.py). This page
  // never works it out from a clock (R-IV.416(c)); null = unknown, and unknown is not closed.
  function serverSession() {
    if (_ext && _ext.market_session !== undefined) return _ext.market_session;
    if (_ixData && _ixData.market_session !== undefined) return _ixData.market_session;
    return null;
  }
  const marketShut = () => { const s = serverSession(); return s != null && s !== 'regular'; };
  function feedsQuietSince() {
    const ix = _ixData;
    if (!ix || ix.data_age_seconds == null || ix.data_age_seconds <= 900 || !ix.as_of) return null;
    return riverTime(apiTime(ix.as_of));   // R-IV.611(b)1: the River's clock, never a second one
  }

  // Themes: every dominant / emerging / fading chip in priority order. Used by the themes
  // DRAWER only since A2 (R-IV.1209(c)) took the chip list off the Regime tile -- the
  // two-row fitter that used to trim them went with the cell it measured.
  function themeChipsAll(regime) {
    const groups = [['dom', (regime && regime.dominant) || []], ['emg', (regime && regime.emerging) || []], ['fad', (regime && regime.fading) || []]];
    const out = [];
    for (let i = 0; groups.some(([, l]) => i < l.length); i++) {
      groups.forEach(([cls, l]) => { if (l[i]) out.push(`<span class="chip ${cls}" data-gloss="${cls.toUpperCase()}">${esc(l[i].theme)} <b>${l[i].score != null ? Math.round(l[i].score) : ''}</b></span>`); });
    }
    return out.length ? out.join('') : '<span class="chip muted">none</span>';
  }
  // `fitThemeChips()` lived here and is GONE (A2, R-IV.1209(c)). Its only DOM target
  // was `#regimeBand .th-chips`, which the 2x2 grid removed, so it could only ever
  // return early -- and a function that silently does nothing reads to the next author
  // as a thing that works. Its resize listeners went with it: a listener calling a
  // no-op on every resize is cost with no effect.
  //
  // `themeChipsAll()` SURVIVES, because the themes DRAWER still renders chips from it.

  // ===========================================================================
  // A2 — the lean / outline / pulse engine (R-IV.1209(d)).
  //
  // FIVE READS LEAN, and the agreement check counts them: the Strategy label, Market mix,
  // Theme breadth, Tide and Vol curve. The yield curve is NOT counted ((d)6) and carries its
  // own EXTREME pulse (R-IV.1220(b) retired the word RARE; see B3 in docs/build-backlog.md).
  //
  // THE TWO THINGS MOST EASILY GOT WRONG, both stated in the ruling and both asserted in tests:
  //   - CALM and PREMIUM SELLING are 0, not bull. Calm is not a bull call ((d)1), and a quiet
  //     tape read as bullish is how a gauge starts lying in the direction its reader hopes.
  //   - "No reading" is 0, not absent. A read that cannot answer still occupies its slot in the
  //     count, so three leans out of five means three of FIVE -- not three of however many
  //     happened to report.
  // ===========================================================================

  //: lean -> numeric side and whether it is an extreme. (d)1.
  const LEAN_SCALE = {
    'strong-bear': { side: -1, extreme: true },
    'bear': { side: -1, extreme: false },
    'neutral': { side: 0, extreme: false },
    'notable': { side: 0, extreme: false },   // teal: neutral-but-notable
    'bull': { side: 1, extreme: false },
    'strong-bull': { side: 1, extreme: true },
  };

  // (d)1, verbatim. Keyed on the WORD each read already shows, so the mapping is auditable
  // against the ruling line by line rather than buried in conditionals.
  const LEAN_BY_WORD = {
    // Strategy (section 2's ten labels)
    'MELT-UP': 'strong-bull', 'MELT UP': 'strong-bull',
    'UPTREND': 'bull',
    'NARROW UPTREND': 'bull-mild', 'RECOVERY': 'bull-mild',
    'RANGE / CHOP': 'neutral', 'RANGE': 'neutral', 'CHOP': 'neutral',
    'CORRECTION': 'bear-mild', 'BEAR-MARKET RALLY': 'bear-mild', 'BEAR MARKET RALLY': 'bear-mild',
    'BREAKDOWN': 'bear', 'BEAR MARKET': 'bear',
    'CRASH': 'strong-bear', 'CRASH / LIQUIDATION': 'strong-bear',
    // Market mix
    'TORO MAJOR': 'strong-bull', 'TORO MINOR': 'bull',
    'NEUTRAL': 'neutral',
    'URSA MINOR': 'bear', 'URSA MAJOR': 'strong-bear',
    // Theme breadth
    'STRONG BUY': 'strong-bull', 'MODERATE BUY': 'bull',
    'MODERATE SELL': 'bear', 'STRONG SELL': 'strong-bear',
    // Tide -- NO EXTREME on this read ((d)1).
    'BULL FLOW': 'bull', 'BEAR FLOW': 'bear',
    'PREMIUM SELLING': 'notable', 'TWO-WAY': 'neutral', 'NO READING': 'neutral',
    // Vol curve
    'CALM': 'notable', 'FIRMING': 'bear-mild', 'STRESS': 'strong-bear',
    // R-IV.1369(d)3: WORDS THE CLEANED POP-OUT AND TILES USE THAT THE BAND NEVER NEEDED.
    // Mapped BY MEANING, as the ruling says: supports higher prices is bull, lower is bear,
    // neither is neutral. Each line names the read that produces the word, so the mapping can
    // be audited against its source rather than guessed at.
    //   200-day line (regime_ma200.side): SPY above its 200-day supports higher prices.
    'ABOVE': 'bull', 'BELOW': 'bear',
    //   Credit (regime_sections_b8, HY OAS): wide spreads are stress. CALM is NOT re-mapped
    //   here -- it is 'notable' above for the vol curve, and one word keeps one colour.
    'WIDE': 'bear', 'MIDDLING': 'neutral',
    //   Auction state (regime_sections_b8.auction): the three words it can produce.
    'ABOVE VALUE': 'bull', 'INSIDE VALUE': 'neutral', 'BELOW VALUE': 'bear',
    //   Crowd (crowd_b6.headline, its "CROWD " prefix dropped). BOTH crowded sides are
    //   'notable', not bear/bull (R-IV.1369(f)7): a crowded side is contrarian fuel.
    'MIXED': 'neutral', 'BEARS CROWDED': 'notable', 'BULLS CROWDED': 'notable',
    //   The STORED keys the ribbon and flip_triggers carry ('range_chop', 'crash_liquidation')
    //   read as these once the underscore goes. Without them those sessions fell through to the
    //   neutral fallback by accident -- right for range_chop, wrong for crash_liquidation.
    'RANGE CHOP': 'neutral', 'CRASH LIQUIDATION': 'strong-bear',
  };

  // ═══ R-IV.1369 · AGORA CLEANUP ROUND 1 ═════════════════════════════════════════════════════
  //
  // The Regime pop-out, the BOOK tile and the CROWD tile, rebuilt to Nick's approved boards
  // (10:22 MT 2026-10-23). DISPLAY ONLY (#42): nothing here computes a new figure, gates
  // anything or touches the kill switch. Every value is one a route already serves.
  //
  // SHIPPED AS THE DEFAULT (R-IV.1369(g), as R-IV.1354(a) did). `?clean=off` restores the old
  // three surfaces UNTIL 2026-11-06 -- REMOVE THE ROLLBACK ON OR AFTER THAT DATE, with the old
  // branches it guards, unless Nick says otherwise. The date is written here because "until"
  // in a ruling becomes "forever" in a codebase that does not record when it ends.
  const CLEAN = (() => {
    try { return new URLSearchParams(location.search).get('clean') !== 'off'; }
    catch (_) { return true; }
  })();

  // A stored regime key ('range_chop') as the word LEAN_BY_WORD is keyed on ('RANGE CHOP').
  const keyWord = (k) => String(k || '').replace(/_/g, ' ').trim().toUpperCase();
  // R-IV.1369(c)3: a NEUTRAL headline is --text, never --text-2, because a --text-2 headline
  // reads as disabled. Every other lean takes leanColor() exactly.
  const headColor = (lean) => (!lean || lean === 'neutral') ? 'var(--text)' : leanColor(lean);

  // The ruling's "mild" steps share a side with their full step but are not extremes. Folded
  // here so LEAN_SCALE stays the five ruled colours and nothing invents a sixth.
  function leanOf(word) {
    const raw = LEAN_BY_WORD[String(word || '').trim().toUpperCase()];
    if (!raw) return null;                     // unknown word: NOT silently neutral
    if (raw === 'bull-mild') return 'bull';
    if (raw === 'bear-mild') return 'bear';
    return raw;
  }

  function leanSide(lean) {
    const e = LEAN_SCALE[lean];
    return e ? e.side : 0;
  }

  function leanExtreme(lean, word) {
    const e = LEAN_SCALE[lean];
    if (!e || !e.extreme) return false;
    // (d)1: the Tide read has no extreme, whatever its word would otherwise map to.
    const w = String(word || '').trim().toUpperCase();
    if (w === 'BULL FLOW' || w === 'BEAR FLOW') return false;
    return true;
  }

  /**
   * The agreement verdict across the five reads. R-IV.1209(d)4.
   *
   * `reads` is [{word, lean}] -- five of them, including any that cannot answer, because a
   * read that reports nothing still counts as 0 and the threshold is "3 or more lean one way
   * and 0 lean the other".
   */
  function regimeAgreement(reads) {
    let bull = 0, bear = 0, extremeBull = false, extremeBear = false;
    (reads || []).forEach((r) => {
      const side = leanSide(r.lean);
      if (side > 0) bull++;
      if (side < 0) bear++;
      if (leanExtreme(r.lean, r.word)) {
        if (side > 0) extremeBull = true;
        if (side < 0) extremeBear = true;
      }
    });
    let side = 0;
    if (bull >= 3 && bear === 0) side = 1;
    else if (bear >= 3 && bull === 0) side = -1;
    const consistent = side !== 0;
    const sameSideExtreme = side > 0 ? extremeBull : side < 0 ? extremeBear : false;
    return {
      bull: bull, bear: bear, side: side, consistent: consistent,
      pulse: consistent && sameSideExtreme,
      outline: side > 0 ? 'bull' : side < 0 ? 'bear' : 'grey',
      // Stated so the tooltip can explain itself rather than leaving a reader to count dots.
      basis: consistent
        ? (bull >= 3 ? bull + ' of 5 lean bull, 0 bear' : bear + ' of 5 lean bear, 0 bull')
          + (sameSideExtreme ? ', with an extreme on that side' : '')
        : 'mixed: ' + bull + ' bull, ' + bear + ' bear',
    };
  }

  function renderRegimeBand(composite, regime, tide, kill) {
    const band = $('regimeBand');
    const r = regime || {}, b = r.breadth || {};
    const v1 = lens1View(composite), v2 = lens2View(regime), split = lensSplit(v1, v2);
    const shut = marketShut();
    const tv = tideView(tide, feedsQuietSince(), shut), vc = volCurveView(composite);

    // Age chips. Lens 1 recomputes every 15 min (fresh bound 20 min). Lens 2 IS a nightly close;
    // it goes amber only on a real problem, not on the themes snapshot's own degraded flag.
    const chip1 = composite ? vintageChip({ iso: isoUtc(composite.timestamp), freshBoundSec: 1200 }) : vintageChip({ unknownLabel: 'no reading' });
    const lag = r.anchor_lag && r.anchor_lag.sessions_behind;
    const chip2 = closeChip(r.metrics_date, !!r.degraded_reason || (lag != null && lag > 0),
      r.degraded_reason ? 'degraded: ' + r.degraded_reason : (lag > 0 ? lag + ' session(s) behind' : null));
    const chipTh = r.degraded ? `<span class="vintage-chip" data-state="stale" title="theme snapshot reported degraded">snapshot degraded</span>` : vintageChip({ iso: isoUtc(r.as_of), freshBoundSec: 8 * 3600 });
    const chipTide = tv.chip === 'closed?' ? `<span class="vintage-chip" data-state="closed" title="Inferred: the market feeds have also gone quiet. The server's session answer did not arrive.">closed?</span>`
      : tv.chip === 'closed' ? `<span class="vintage-chip" data-state="closed" title="Market closed (server calendar). Flow resumes at the open.">closed</span>`
      : tv.chip === 'unknown' ? vintageChip({ unknownLabel: 'no reading' }) : vintageChip({ iso: isoUtc(tide.as_of), freshBoundSec: 900, session: tide.session || (shut ? 'closed' : null) });
    const chipVc = vc.iso == null ? vintageChip({ unknownLabel: 'no reading' })
      : vc.stale ? `<span class="vintage-chip" data-state="stale" title="vix_term factor is stale or excluded">stale</span>` : vintageChip({ iso: vc.iso, freshBoundSec: 1200 });
    const total = b.total != null ? b.total : 250;

    // ── A2 (R-IV.1209(c)): a 2x2 grid of BIG labels, each with a zone gauge and a details
    // toggle holding today's fine print. The themes chip list is GONE from this tile, and the
    // Yield Curve has moved in beside the grid.
    //
    // THE FIFTH READ IS THE STRATEGY LABEL, which lives on the Strategy card and not in this
    // bar -- but it is counted in the agreement check ((d)1 lists five reads), so it is read
    // from the card's own last payload rather than re-derived here. Two derivations of one
    // label would eventually disagree, and the one on screen would be the untested one.
    const stratWord = (_rsLive && _rsLive.regime_label) || null;
    const reads = [
      { key: 'strategy', word: stratWord, lean: leanOf(stratWord) },
      { key: 'mix', word: v1.call, lean: leanOf(v1.call) },
      { key: 'breadth', word: v2.call, lean: leanOf(v2.call) },
      { key: 'tide', word: tv.word, lean: leanOf(tv.word) },
      { key: 'vol', word: vc.word, lean: leanOf(vc.word) },
    ];
    const agree = regimeAgreement(reads);
    const leanFor = (k) => (reads.find((r) => r.key === k) || {}).lean;
    const isExtreme = (k) => {
      const r = reads.find((x) => x.key === k) || {};
      return leanExtreme(r.lean, r.word);
    };
    // (d)3: a read at an extreme pulses its own label and its own box, whatever the others say.
    // (d)4: agreement outlines every box; agreement plus a same-side extreme pulses every box.
    const boxCls = (k) => {
      const own = isExtreme(k) ? ' rb-x rb-x-' + (leanSide(leanFor(k)) > 0 ? 'bull' : 'bear') : '';
      const grp = agree.pulse ? ' rb-grp-pulse rb-grp-' + agree.outline
        : agree.consistent ? ' rb-grp rb-grp-' + agree.outline : ' rb-grp-grey';
      return own + grp;
    };

    band.innerHTML = `
      <div class="rb-grid">
        ${rbCell('mix', 'MARKET MIX · 20 FACTORS', v1.call, v1.num, leanFor('mix'),
          boxCls('mix'), chip1 + (split ? '<span class="split-chip" data-gloss="DIVERGE">LENSES SPLIT</span>' : ''),
          v1.dist, 'regime', v1.pct, LENS1_CUTS)}
        ${rbCell('breadth', 'THEME BREADTH · &gt;50D', v2.call, v2.num, leanFor('breadth'),
          boxCls('breadth'), chip2, esc(total) + ' names · nightly · ' + v2.dist,
          'breadth', v2.pct, lens2Ticks(r.thresholds))}
        ${rbCell('tide', 'TIDE · OPTIONS FLOW', tv.word, tv.lean || '', leanFor('tide'),
          boxCls('tide'), chipTide, tv.line2, null, null, null)}
        ${rbCell('vol', 'VOL CURVE · VIX/VIX3M', vc.word, vc.value, leanFor('vol'),
          boxCls('vol'), chipVc, vc.sub, 'volcurve', vc.pct, VOL_TICKS)}
      </div>
      <div class="rb-curve" id="rbCurve">
        <div class="rb-ch"><span class="rb-cl">YIELD CURVE</span>
          <span class="yc-shape" id="ycShape" title="shape word: waiting for the FRED read">—</span>
          <span class="yc-flag" id="ycFlag"></span></div>
        <div class="yc-heads" id="ycHeads"></div>
        <div class="chart-host sm"><canvas id="curveChart"></canvas></div>
        <div class="mini-vals" id="curveVals"></div>
      </div>`;
    applyGlossary(band);
    // R-IV.1251: THE REPAINT THAT FIXES THE BLANK BOX. This function has just replaced the
    // band's innerHTML, which destroyed the yield-curve box's filled markup and put the empty
    // template back. `refreshMarket` is on a SEPARATE 60-second timer, so without this line
    // the box stays blank for up to a minute — and permanently, whenever the two timers settle
    // into band-last order, which is what Nick's screenshot caught mid-session.
    //
    // Painting from the CACHE, not fetching: this runs on every band tick and a fetch here
    // would turn one blank box into a request storm.
    paintYieldCurve();
    // The agreement basis rides on the grid so a reader can see WHY every box is outlined the
    // way it is, rather than counting dots to work it out.
    const gridEl = band.querySelector('.rb-grid');
    if (gridEl) gridEl.title = 'outlines: ' + agree.basis;
    band.querySelectorAll('[data-drawer]').forEach((c) => c.addEventListener('click', (e) => {
      if (e.target.closest('.rb-det')) return;      // the details toggle is not a drawer open
      openDrawer(c.dataset.drawer, { composite, regime, tide, kill }, c);
    }));
    band.querySelectorAll('.rb-det').forEach((b) => b.addEventListener('click', (e) => {
      e.stopPropagation();
      const box = b.parentElement && b.parentElement.querySelector('.rb-fine');
      if (!box) return;
      const open = box.hidden;
      box.hidden = !open;
      b.setAttribute('aria-expanded', String(open));
      b.textContent = open ? 'details ▴' : 'details ▾';
    }));
    // (d)5: the kill switch / an ACTIVE overlay keeps its red alarm pulse, and it beats (d)4.
    const tile = band.closest('.tile');
    if (tile) tile.classList.toggle('rb-alarm', !!(kill && String(kill.state || '').toUpperCase() === 'ARMED'));
  }

  /**
   * One cell of the 2x2 regime grid. A2 (R-IV.1209(c)).
   *
   * The label is BIG and in Orbit; the number sits beside it; the zone gauge shows where the
   * reading falls; and the fine print is behind a `details` toggle rather than printed under
   * every cell, which is what Nick's third tweak asked for.
   */
  function rbCell(key, cap, word, num, lean, cls, chip, fine, drawer, pct, ticks) {
    const col = leanColor(lean === 'notable' ? 'notable' : lean);
    return '<div class="rb-cell' + cls + '"' + (drawer ? ' data-drawer="' + drawer + '"' : '')
      + '>'
      + '<div class="rb-cap">' + cap + (chip || '') + '</div>'
      + '<div class="rb-lab-row">'
      + '<b class="rb-lab' + (lean && LEAN_SCALE[lean] && LEAN_SCALE[lean].extreme
        ? ' rb-lab-x' : '') + '" style="color:' + col + '">'
      + esc(word || '—') + '</b>'
      + (num ? '<span class="rb-num">' + esc(String(num)) + '</span>' : '')
      + '</div>'
      // B1: the TICKS are the real cut-offs that decide the word, so a reader can see how far
      // the marker sits from the next call rather than taking the word on trust. A gauge with
      // a marker and no scale shows a position against nothing.
      + (pct != null
        ? '<div class="vc-gauge rb-g" aria-hidden="true">'
          + (ticks || []).map((t) => '<i style="left:'
            + Math.max(0, Math.min(100, Number(t))).toFixed(2) + '%"></i>').join('')
          + '<b style="left:' + Math.max(0, Math.min(100, Number(pct))).toFixed(1)
          + '%"></b></div>'
        : '<div class="rb-g rb-g-none" aria-hidden="true"></div>')
      + '<button type="button" class="rb-det" aria-expanded="false">details ▾</button>'
      + '<div class="rb-fine" hidden>' + esc(fine || '') + '</div>'
      + '</div>';
  }

  // ── Movers tape ──────────────────────────────────────────────────────────────
  async function loadMoversTape() {
    let data = null;
    try { const r = await apiFetch('/api/stable/movers'); if (r.ok) data = await r.json(); } catch (_) {}
    renderMoversTape(data);
    const age = data && data.data_age_seconds != null ? data.data_age_seconds : null;
    const degraded = data ? !!data.degraded : null;   // null = no payload (R-IV.413(e))
    const flat = !!(data && data.flatline);
    const session = data && data.session;
    setHealth($('moversHealthDot'), age, degraded, flat, session);
    $('moversAge').textContent = flat ? 'DEAD · pipe stalled' : degraded === true ? 'degraded · ' + ageLabel(age) : degraded == null ? 'no data' : session === 'closed' ? 'closed' + (age != null ? ' · ' + ageLabel(age) + ' old' : '') : ageLabel(age) + ' old';
    $('moversAge').className = flat ? 'val-down' : '';
    _health.movers = healthState(age, degraded, flat, session);
    noteFlatline('movers', flat, 'Movers');
    updateGlobalHealth();
    // Flow/Kairos badges — batched, rides the same 5-min movers cadence (no new poller).
    if (data && ((data.gainers || []).length || (data.losers || []).length)) {
      const tickers = [...(data.gainers || []), ...(data.losers || [])].map((m) => m.ticker);
      fetchTickerContext(tickers).then((ctx) => annotateTickerBadges('#moversTape .mover', ctx));
    }
  }

  // ── Ticker-context badges (options-flow sentiment + active Kairos setup) ──────────────
  // Read-only batch call: flow reflects the EXISTING UW flow poller's own watchlist (lights
  // up only for names it already tracks — never fabricated for the rest); kairos reflects
  // whether an ACTIVE trade-idea exists for the ticker right now.
  async function fetchTickerContext(tickers) {
    const uniq = [...new Set(tickers.map((t) => (t || '').toUpperCase()).filter(Boolean))];
    if (!uniq.length) return {};
    try {
      const r = await apiFetch('/api/board/ticker-context?tickers=' + uniq.join(','));
      if (r.ok) return (await r.json()).context || {};
    } catch (_) {}
    return {};
  }
  function tickerBadgeHtml(ctx) {
    if (!ctx) return '';
    let html = '';
    if (ctx.flow && ctx.flow.sentiment) {
      const up = ctx.flow.sentiment === 'BULLISH';
      html += `<span class="flow-tag ${up ? 'up' : 'down'}" data-gloss="FLOWTAG">${up ? '▲' : '▼'}</span>`;
    }
    if (ctx.kairos) html += `<span class="kairos-tag" data-gloss="KTAG">K</span>`;
    return html;
  }
  function annotateTickerBadges(selector, ctxMap) {
    document.querySelectorAll(selector).forEach((el) => {
      const tk = (el.dataset.ticker || '').toUpperCase();
      const slot = el.querySelector('.badge-slot');
      if (!slot) return;
      const html = tickerBadgeHtml(ctxMap[tk]);
      if (html === slot.innerHTML) return;
      slot.innerHTML = html;
      applyGlossary(slot);
      slot.querySelectorAll('.kairos-tag').forEach((b) => b.addEventListener('click', (e) => {
        e.stopPropagation();
        const k = ctxMap[tk] && ctxMap[tk].kairos;
        openCommittee(tk, k ? k.signal_id : '', b);
      }));
    });
  }

  function moverEl(m, side) {
    const thm = m.theme ? ` <span class="sep">·</span> <span class="thm">${esc(m.theme)}</span>` : '';
    return `<span class="mover ${side}" data-ticker="${esc(m.ticker)}" data-chart="${esc(String(m.ticker || '').toUpperCase())}"><span class="tk">${esc(m.ticker)}</span> <span class="pct">${fmtPct(m.pct)}</span><span class="badge-slot"></span>${thm}</span>`;
  }
  function renderMoversTape(data) {
    const tape = $('moversTape');
    if (!data || (!(data.gainers || []).length && !(data.losers || []).length)) {
      tape.innerHTML = '<span class="mover"><span class="thm">movers feed unavailable — showing no data (not fake-fresh)</span></span>';
      return;
    }
    const g = (data.gainers || []).map((m) => moverEl(m, 'gain')).join(' <span class="sep">•</span> ');
    const l = (data.losers || []).map((m) => moverEl(m, 'lose')).join(' <span class="sep">•</span> ');
    const one = g + ' <span class="sep">•</span> ' + l;
    tape.innerHTML = one + ' <span class="sep">•</span> ' + one; // duplicate for seamless marquee
  }

  // ── Drawer ────────────────────────────────────────────────────────────────
  function openDrawer(kind, ctx, src) {
    const side = popSide(src, kind === 'committee' ? 'kairos' : kind === 'breadth' ? 'breadth' : kind === 'divergence' ? 'divergence' : 'regime-band');
    closePopup();   // was opening UNDER the member popup (z61 vs its z65 backdrop)
    // Replacing the sector chart drawer with another kind: its canvas is about to be destroyed.
    if (_divOpen && kind !== 'divergence') { _divOpen = false; if (_charts.divChart) { _charts.divChart.destroy(); delete _charts.divChart; } }
    setSide($('drawer'), side); syncTopbarH();
    const title = $('drawerTitle'), body = $('drawerBody');
    const kv = (k, v) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`;
    if (kind === 'themes' && ctx.regime) {
      title.textContent = 'Themes — dominant / emerging / fading';
      const sec = (name, arr, cls) => `<div style="margin:10px 0 4px;color:var(--text-3);font-family:var(--mono);font-size:11px;letter-spacing:1px">${name}</div>` +
        ((arr || []).map((t) => `<div class="kv"><span class="k"><span class="chip ${cls}">${esc(t.theme)}</span></span><span class="v">${t.score != null ? t.score : ''} · ${esc(t.status || '')}</span></div>`).join('') || '<div class="kv"><span class="k">none</span></div>');
      body.innerHTML = sec('DOMINANT', ctx.regime.dominant, 'dom') + sec('EMERGING', ctx.regime.emerging, 'emg') + sec('FADING', ctx.regime.fading, 'fad');
    } else if (kind === 'breadth' && ctx.regime) {
      title.textContent = 'Breadth';
      const b = ctx.regime.breadth || {};
      body.innerHTML = kv('Total (scored universe)', b.total) + kv('% > 20DMA', b.pct_above_20dma) + kv('% > 50DMA', b.pct_above_50dma) +
        kv('% > 200DMA', b.pct_above_200dma) + kv('New highs 20d', b.new_high_20d) + kv('New highs 52w', b.new_high_52w) +
        kv('New lows 20d', b.new_low_20d) + kv('New lows 52w', b.new_low_52w) +
        kv('Up > 3%', b.up_3) + kv('Down > 3%', b.down_3) + kv('As of (close)', ctx.regime.metrics_date);
    } else if (kind === 'volcurve') {
      title.textContent = 'Vol curve · VIX ÷ VIX3M';
      const vc = volCurveView(ctx.composite), raw = (((ctx.composite || {}).factors || {}).vix_term || {}).raw_data || {};
      body.innerHTML = kv('Ratio', raw.ratio != null ? Number(raw.ratio).toFixed(3) : '—') + kv('Reads', vc.word || '—') +
        kv('VIX', raw.vix != null ? Number(raw.vix).toFixed(2) : '—') + kv('VIX3M', raw.vix3m != null ? Number(raw.vix3m).toFixed(2) : '—') +
        kv('CALM', 'below 0.90 — near-term fear under longer-term') + kv('FIRMING', '0.90 – 0.99 — the curve is flattening') +
        kv('STRESS', '1.00 and up — near-term fear above longer-term (inverted)') +
        kv('Updates', 'with the composite, every 15 min (factor vix_term, yfinance)') +
        '<div style="margin-top:10px;font-size:11px;color:var(--text-3)">CALM is not a bullish call; it only says near-term volatility is priced below longer-term.</div>';
    } else if (kind === 'kill') {
      title.textContent = 'Kill switch';
      const v = killCellView(ctx.kill, _killReadAt);
      const k = (ctx.kill && ctx.kill.kill_switch) || {}, p = (ctx.kill && ctx.kill.provenance) || {};
      body.innerHTML = kv('State', v.label) + kv('Detail', _unesc(v.prov)) + kv('Source', p.source || '—') +
        kv('As of', p.as_of || '—') + kv('State age', fmtAge(p.age_seconds) || '—') + kv('Stored record', p.persisted_record || '—') +
        kv('Trigger', k.trigger || '—') + kv('Pending reset', k.pending_reset ? 'yes' : 'no') +
        kv('Disputed', k.disputed ? String(k.disputed) : 'no') + kv('Divergence', p.divergence || 'none') +
        kv('Readings', k.readings ? JSON.stringify(k.readings) : '—') +
        `<div style="margin-top:10px;font-size:12px;color:var(--text-2);line-height:1.45">${v.state === 'unverified'
          ? 'UNVERIFIED: no trip has been recorded since the server started. That is also what a dead or expired TradingView alert looks like: two remote alerts (SPY and VIX) are the only things that can arm this switch, and nothing yet proves they are alive. A heartbeat is a planned backend change.'
          : esc(GLOSSARY.KILL)}</div>`;
    } else if (kind === 'divergence') {
      title.textContent = 'Sectors · % change (1D / 5D)';
      body.innerHTML = `<div class="seg" id="divToggle"><button type="button" data-w="1d" class="${_divWindow === '1d' ? 'on' : ''}">1D</button><button type="button" data-w="5d" class="${_divWindow === '5d' ? 'on' : ''}">5D</button></div>
        <div class="chart-host drawer-chart"><canvas id="divChart"></canvas></div><div class="legend-row" id="divLegend"></div>
        <div style="margin-top:8px;font-size:11px;color:var(--text-3)">Each sector ETF's own % change (not vs SPY). Click a line or chip to isolate it. 1D is every 2 min in market hours; 5D is daily closes.</div>`;
      _divOpen = true;
      loadDivergence();
    } else if (kind === 'committee') {
      title.textContent = 'Committee · ' + (ctx.ticker || '');
      const tkRow = `<div class="kv"><span class="k">Ticker</span><span class="v">${ctx.ticker ? chartTk(ctx.ticker) : '—'}</span></div>`;
      body.innerHTML = tkRow + kv('Signal', ctx.sig || '—') +
        '<div style="margin:10px 0;color:var(--text-3);font-size:12px">Loading options context…</div>';
      (async () => {
        try {
          const r = await apiFetch('/api/committee/enrichment/' + encodeURIComponent(ctx.ticker));
          if (!r.ok) return;
          const e = (await r.json()).enrichment || {};
          const iv = e.iv_rank || {}, tide = e.market_tide || {}, mp = e.max_pain || {}, sf = e.sector_flow || {};
          body.innerHTML = tkRow + kv('Signal', ctx.sig || '—') +
            kv('IV rank', iv.iv_rank != null ? Number(iv.iv_rank).toFixed(0) : '—') +
            kv('Market tide (whole market)', (tide.net_call_premium != null && tide.net_put_premium != null) ? tideView({ tide }).word : '—') +
            kv('Max pain', mp.max_pain_strike != null ? mp.max_pain_strike + ' (' + mp.dte + 'dte)' : '—') +
            kv('Sector posture', sf.risk_posture || '—') +
            '<div style="margin-top:10px;font-size:11px;color:var(--text-3)">Foreground UW read (on-demand). Full committee review runs from the legacy analyzer.</div>';
        } catch (_) {}
      })();
    } else {
      title.textContent = 'Regime detail';
      const c = ctx.composite || {}, r = ctx.regime || {};
      const v1 = lens1View(ctx.composite), v2 = lens2View(ctx.regime);
      const tf = c.timeframe_scores || {};
      // TA-193 R1: NUMBERS ONLY on a sub-score, and the ACTIVE WEIGHT beside it. The label
      // was dropped because the call belongs to the composite; the weight was added because
      // a sub-score of -0.4 over 8% of the factor weight and one over 40% are not comparable,
      // and nothing on this panel said which it was.
      const tfRow = (name, key) => {
        const x = tf[key];
        if (!x) return kv(name, '—');
        const sc = x.sub_score != null ? (x.sub_score >= 0 ? '+' : '') + Number(x.sub_score).toFixed(3) : '—';
        const w = x.active_weight != null ? Math.round(x.active_weight * 100) + '% of factor weight' : 'weight unknown';
        const n = x.active_factor_count != null ? x.active_factor_count + ' active' : '';
        return kv(name, sc + ' · ' + w + (n ? ' · ' + n : ''));
      };
      const sec = (t) => `<div style="margin:12px 0 4px;color:var(--text-3);font-family:var(--mono);font-size:11px;letter-spacing:1px">${t}</div>`;
      // The kill switch has its own drawer (top-bar beacon); it is not repeated here, and never as
      // a bare CLEAR — that was the fail-open read of default-since-boot.
      body.innerHTML = sec('MARKET MIX · 20 FACTORS · EVERY 15 MIN') +
        kv('Call', v1.call + (v1.num ? ' · ' + v1.num : '')) + kv('Distance', v1.dist || '—') +
        // TA-193 R1: THIS ROW WAS CAPTIONED "Raw score" AND HELD THE MODIFIED ONE.
        // `composite_score` is the score after the velocity multiplier, RVOL and the circuit
        // breaker. Captioning it "raw" is what sent a reader to recompute the blend, get
        // -0.080 against a displayed -0.105, and report the engine as broken. Both figures are
        // shown now, and the stages between them are listed underneath.
        kv('Weighted blend', c.raw_score != null ? Number(c.raw_score).toFixed(3) : '—') +
        (c.score_modifiers || []).filter((m) => m.applied).map((m) =>
          kv('  × ' + String(m.name).replace(/_/g, ' '),
             String(m.value) + ' → ' + Number(m.score_after).toFixed(3)
             + (m.reason ? ' · ' + esc(String(m.reason)) : ''))).join('') +
        kv('Score after modifiers', c.composite_score != null ? Number(c.composite_score).toFixed(3) : '—') +
        tfRow('Intraday', 'intraday') + tfRow('Swing', 'swing') + tfRow('Macro', 'macro') +
        kv('Coverage', c.coverage_ratio != null ? Math.round(c.coverage_ratio * 100) + '% of factor weight' : '—') +
        kv('Stale factors', (c.stale_factors || []).length ? c.stale_factors.join(', ') : 'none') +
        kv('Confidence', c.confidence || '—') + kv('Override', c.override ? String(c.override) : 'none') +
        kv('Cut-offs (dial)', '20 / 40 / 60 / 80 = URSA MAJOR | URSA MINOR | NEUTRAL | TORO MINOR | TORO MAJOR') +
        sec('THEME BREADTH · % OF WATCHLIST ABOVE 50-DAY · NIGHTLY') +
        kv('Call', v2.call + (v2.num ? ' · ' + v2.num : '')) + kv('Distance', v2.dist || '—') +
        kv('Backend label', r.regime_label || '—') + kv('Names scored', (r.breadth || {}).total != null ? r.breadth.total : '—') +
        kv('Cut-offs (%)', '70 / 60 / 40 / 30 = STRONG BUY | MODERATE BUY | NEUTRAL | MODERATE SELL | STRONG SELL') +
        kv('As of (close)', r.metrics_date || '—') +
        '<div style="margin-top:10px;font-size:11px;color:var(--text-3);line-height:1.45">The two lenses share no inputs. Market mix blends 20 market-wide factors (volatility, breadth, credit, trend, macro) and recomputes every 15 minutes. Theme breadth is one nightly number: the share of your themed watchlist above its 50-day average.</div>';
    }
    $('drawerBackdrop').classList.add('open'); openedDrawerHistory();
    $('drawer').classList.add('open');
    placeChartSoon();
  }

  /**
   * A2 (R-IV.1209(c)): the Strategy card's "◂ DETAILS" drawer, slid in from the LEFT.
   *
   * The drawer already supported `from-left`, so this forces that side rather than letting
   * `popSide` pick -- the ruling says left, and the Strategy card is full width, which is
   * exactly the case where popSide falls back to whatever was clicked.
   *
   * PHASE A, SO THE SECTIONS ARE MOCK, and each one says so. The eight sections are board 8's,
   * in the synthesis's own vote order; B8 wires them one at a time, and each will report its
   * source and a sample row before it does.
   */
  // B8 §§2-5 (R-IV.1246(b)). One route, one payload, four sections -- the drawer opens once
  // and four routes would be four chances for a partial render.
  //
  // A SOURCE THAT FAILS SHOWS "unavailable" WITH ITS REASON, NEVER A MOCK VALUE. `_rsSections`
  // starts empty, so a drawer opened before the fetch lands says "loading" rather than drawing
  // zeros, which would read as a reading.
  let _rsSections = {};
  async function loadRegimeSections() {
    try {
      const r = await apiFetch('/api/regime-sections');
      if (r.ok) _rsSections = await r.json();
    } catch (_) { /* leaves the previous payload, and each section says if it is absent */ }
  }

  function naHtml(b, what) {
    if (!b) return '<div class="rd-na">' + esc(what) + ' · loading</div>';
    return '<div class="rd-na">unavailable — ' + esc(b.reason || 'no reason given') + '</div>';
  }

  // §6 (R-IV.1246(b)5). The PYTHIA snapshot, as stored. The BRACKET COUNTER is withheld
  // rather than greyed: board 8 asked for it greyed under 10 sessions, but the hub keeps only
  // the latest snapshot per ticker, so there is no count to grey and a "1 of 10" would be a
  // number about nothing.
  function auctionHtml(b) {
    if (!b || !b.available) return naHtml(b, 'auction state');
    const lvl = (k, v) => v == null ? '' : '<div class="kv"><span class="k">' + esc(k)
      + '</span><span class="v">' + Number(v).toFixed(2) + '</span></div>';
    return '<div class="rd-big"><b>' + esc(b.where || '—') + '</b></div>'
      + '<div class="rd-note" title="' + esc(b.where_basis || '') + '">'
      + esc(b.where_basis || '') + '</div>'
      + lvl('VAH', b.vah) + lvl('POC', b.poc) + lvl('VAL', b.val)
      + lvl('IB high', b.ib_high) + lvl('IB low', b.ib_low)
      + (b.va_migration ? '<div class="kv"><span class="k">VA migration</span>'
        + '<span class="v">' + esc(b.va_migration) + '</span></div>' : '')
      + (b.volume_quality ? '<div class="kv"><span class="k">Volume quality</span>'
        + '<span class="v">' + esc(b.volume_quality) + '</span></div>' : '')
      + '<div class="kv"><span class="k">Bracket counter</span>'
      + '<span class="v rd-na-inline" title="'
      + esc((b.bracket_counter || {}).reason || '') + '">unavailable</span></div>'
      + '<div class="rd-note rd-dim">' + esc(b.basis || '') + '</div>';
  }

  // §8 (R-IV.1246(b)6). A lamp is shown ONLY where a feed exists. An unlit overlay lamp would
  // read as "checked, nothing firing" — a claim — where "no feed" is the truth, and the rules
  // file's own words are quoted for it. The kill lamp comes from the card's existing read, not
  // a second one: two readers of the kill switch could disagree about whether it is armed.
  function lampsHtml(b) {
    if (!b) return naHtml(b, 'lamps');
    const v = _lastKillView;
    const killRow = v
      ? '<div class="kv"><span class="k">Kill switch</span><span class="v'
        + (v.state === 'armed' ? ' lamp-armed pulse-vermilion' : '')
        + (v.state === 'unknown' ? ' rd-na-inline' : '') + '">'
        + esc(v.state === 'armed' ? ('ARMED · ' + (v.label || ''))
          : (v.state === 'unknown' ? 'unreadable' : 'not armed')) + '</span></div>'
      : '<div class="kv"><span class="k">Kill switch</span>'
        + '<span class="v rd-na-inline">not read yet</span></div>';
    return killRow
      + '<div class="kv"><span class="k">Overlay lamps</span>'
      + '<span class="v rd-na-inline" title="' + esc((b.overlays || {}).reason || '')
      + '">unavailable — ' + esc((b.overlays || {}).reason || '') + '</span></div>'
      + '<div class="rd-note rd-dim">' + esc(b.basis || '') + '</div>';
  }

  function creditHtml(b) {
    if (!b || !b.available) return naHtml(b, 'HY OAS');
    const chg = b.change_20d_bp;
    return '<div class="rd-big"><b>' + esc(b.bp) + 'bp</b>'
      + '<span class="rd-word">' + esc(b.word) + '</span>'
      + (chg != null ? '<span class="rd-chg ' + (chg > 0 ? 'neg' : 'pos') + '">'
        + (chg > 0 ? '+' : '') + esc(chg) + 'bp / 20d</span>' : '')
      + (b.pct_rank != null ? '<span class="rd-pct">' + esc(b.pct_rank)
        + 'th pct</span>' : '') + '</div>'
      + '<div class="rd-note rd-dim" title="' + esc(b.basis || '') + '">as of '
      + esc(b.as_of || '—') + ' · ' + esc(b.series) + '</div>';
  }

  function ratesHtml(b) {
    if (!b || !b.available) return naHtml(b, 'rates');
    const rows = (b.rows || []).map((r) => {
      if (!r.available) {
        return '<div class="kv"><span class="k">' + esc(r.series)
          + '</span><span class="v rd-na-inline">unavailable</span></div>';
      }
      const chg = r.change_20d_bp;
      return '<div class="kv"><span class="k">'
        + esc(r.key === 'real_10y' ? '10y real (DFII10)' : '10y breakeven (T10YIE)')
        + '</span><span class="v">' + esc(r.pct) + '%'
        + (chg != null ? ' <i class="rd-chg ' + (chg > 0 ? 'neg' : 'pos') + '">'
          + (chg > 0 ? '+' : '') + esc(chg) + 'bp/20d</i>' : '') + '</span></div>';
    }).join('');
    const mv = b.move || {};
    const move = mv.available
      ? '<div class="kv"><span class="k">MOVE</span><span class="v">' + esc(mv.value)
        + '</span></div>'
      : '<div class="kv"><span class="k">MOVE</span>'
        + '<span class="v rd-na-inline" title="' + esc(mv.reason || '')
        + '">unavailable</span></div>';
    return rows + move
      + '<div class="rd-note rd-dim">' + esc(b.basis || '') + '</div>';
  }

  function leadershipHtml(b) {
    if (!b || !b.available) return naHtml(b, 'leadership ratios');
    const rows = (b.rows || []).map((r) => {
      if (!r.available) {
        return '<div class="kv"><span class="k">' + esc(r.name)
          + '</span><span class="v rd-na-inline" title="' + esc(r.reason || '')
          + '">unavailable</span></div>';
      }
      const dir = r.direction || '';
      return '<div class="kv" title="rising = ' + esc(r.rising_means || '') + '">'
        + '<span class="k">' + esc(r.name) + '</span><span class="v">'
        + '<i class="ld-' + esc(dir) + '">' + esc(dir) + '</i> '
        + (r.change_pct != null ? (r.change_pct > 0 ? '+' : '') + esc(r.change_pct) + '%' : '')
        + '</span></div>';
    }).join('');
    return '<div class="rd-big"><b>' + esc(b.headline || '') + '</b></div>' + rows
      + '<div class="rd-note rd-dim">' + esc(b.basis || '') + '</div>';
  }

  function zweigHtml(b) {
    if (!b) return naHtml(b, 'Zweig proxy');
    // PROXY, and the label is not optional: the hub stores no advance/decline line, so this is
    // a slower, broader series than Zweig's own measure. Shown on the row, not in a tooltip.
    const tag = '<span class="rd-proxy" title="' + esc(b.note || '') + '">PROXY</span>';
    if (!b.available) {
      return '<div class="kv"><span class="k">Zweig thrust ' + tag
        + '</span><span class="v rd-na-inline">unavailable — ' + esc(b.reason || '')
        + '</span></div>';
    }
    return '<div class="kv"><span class="k">Zweig thrust ' + tag + '</span>'
      + '<span class="v' + (b.fired ? ' ld-rising' : '') + '">'
      + (b.fired ? 'FIRED' : 'no') + '</span></div>'
      + '<div class="rd-note rd-dim" title="' + esc(b.note || '') + '">'
      + esc(b.fired ? ('low ' + b.low_in_window + '% to ' + b.now_pct + '% in '
        + b.window + ' sessions') : (b.reason || '')) + '</div>';
  }

  // B8 section 1 (R-IV.1243(e)). CONDITIONS WITH COUNTERS, and NO distance-to-flip: the v1
  // classifier takes a label when a SET of conditions holds, not when one score crosses a
  // line, so there is no number whose shrinking means closer. A points estimate would imply a
  // geometry the rules do not have, which is what the note in this file already said.
  // §3's live number. `pct_above_50dma` IS NOT A STORED KEY -- `_breadth_block` writes
  // `sectors_above_50dma` (a count) and `sectors_total`, so the old expression read a missing
  // field and this line has been showing a dash. The percentage is derived, and the count is
  // shown beside it so the reader can see the sample it came from: 5 of 11 and 45% are the
  // same fact, but only the first says how coarse it is.
  function breadthNow() {
    const br = ((_lastRegime.regime || {}).breadth) || {};
    if (br.pct_above_50dma != null) return br.pct_above_50dma + '%';
    const c = br.sectors_above_50dma, t = br.sectors_total;
    if (c != null && t) return c + ' of ' + t + ' sectors (' + Math.round(100 * c / t) + '%)';
    return '—';
  }

  function flipTriggersHtml(ft) {
    if (!ft || ft.error) {
      return '<div class="rd-mock">flip conditions unavailable'
        + (ft && ft.error ? ' (' + esc(ft.error) + ')' : '') + '</div>';
    }
    const row = (b, cls) => {
      if (!b) return '';
      const counter = b.counter
        ? '<b class="ft-count">' + esc(b.counter.text) + '</b>' : '';
      return '<div class="ft-row ' + cls + '" title="' + esc(b.closes_basis || '') + '">'
        + '<span class="ft-dir">' + esc(b.direction || '') + '</span>'
        + '<span class="ft-cond">' + esc(b.condition || b.headline || '') + '</span>'
        + (b.target_words ? '<span class="ft-to">' + esc(b.target_words) + '</span>' : '')
        + counter + '</div>';
    };
    return '<div class="ft-held">holding ' + esc(ft.shown)
      + (ft.held_sessions != null ? ' for ' + esc(ft.held_sessions) + ' session'
        + (Number(ft.held_sessions) === 1 ? '' : 's') : '')
      + (ft.min_hold != null ? ' · minimum hold ' + esc(ft.min_hold) : '') + '</div>'
      + row(ft.in_progress, 'ft-live')
      + row(ft.down_order, 'ft-ctx')
      + row(ft.up_order, 'ft-ctx')
      + '<div class="rd-note rd-dim">' + esc(ft.order_note || '') + '</div>'
      + '<div class="rd-note rd-dim">' + esc(ft.no_distance_estimate || '') + '</div>';
  }

  // B8 section 7 (R-IV.1239(h)). The last 40 SETTLED sessions, from the stored snapshots the
  // drawer's payload already carries. One square per session, flips marked.
  //
  // A SESSION WITH NO LABEL DRAWS A GAP, not a neutral square: the strip's job is to show how
  // long the current label has held, and a blank filled in with "neutral" would read as a
  // calm stretch that was really a hole in the record.
  function ribbonHtml(rb) {
    if (!rb || !rb.sessions || !rb.sessions.length) {
      return '<div class="rd-mock">no stored sessions'
        + (rb && rb.error ? ' (' + esc(rb.error) + ')' : '') + '</div>';
    }
    const sq = rb.sessions.map((s) => {
      if (!s.label) {
        return '<span class="rb-sq rb-gap" title="' + esc(s.as_of || '')
          + ' · no label stored"></span>';
      }
      const lean = leanOf(s.label);
      return '<span class="rb-sq' + (s.flipped ? ' rb-flip' : '')
        + (s.blocked ? ' rb-blocked' : '') + '" style="background:' + leanColor(lean)
        + '" title="' + esc(s.as_of || '') + ' · ' + esc(s.label)
        + (s.flipped ? ' · FLIPPED here' : '') + (s.blocked ? ' · blocked' : '') + '"></span>';
    }).join('');
    const flips = rb.sessions.filter((s) => s.flipped).length;
    return '<div class="rb-strip">' + sq + '</div>'
      + '<div class="rd-note">' + esc(rb.count) + ' of ' + esc(rb.asked_for)
      + ' sessions · ' + flips + ' flip' + (flips === 1 ? '' : 's')
      + (rb.short_history ? ' · SHORT HISTORY' : '') + '</div>'
      + '<div class="rd-note rd-dim" title="' + esc(rb.basis || '') + '">'
      + esc(rb.basis || '') + '</div>';
  }

  // ═══ REGIME POP-OUT v2 (R-IV.1252, behind ?pop=v2) ═══════════════════════
  //
  // BEHIND A SWITCH, and the current drawer stays the default (R-IV.1257(b)1). It renders only
  // for `?pop=v2`, so Nick can preview it beside the live one and it becomes the default in a
  // separate one-line deploy after he approves — not by my judgement of whether it looks right.
  //
  // EVERY VALUE COMES FROM THE ROUTES ALREADY BUILT. The mock's numbers are illustrative
  // (R-IV.1252(a)); nothing here carries a figure from it.
  //
  // THE TEXT IS BEHIND ⓘ (R-IV.1252(d)). Nothing on the face of the drawer runs longer than one
  // line, which is the whole complaint the redesign answers: the v1 drawer explained itself in
  // paragraphs and the reader had to find the number inside the prose.
  // R-IV.1354(a): SHIPPED AS THE DEFAULT (Nick, 20:05 MT 2026-10-22, "Ship the previews").
  // This read `=== 'v2'` and defaulted to FALSE. It now defaults to TRUE, and the v1 drawer
  // stays reachable at `?pop=v1` for ONE WEEK -- REMOVE THE ROLLBACK ON OR AFTER 2026-10-30,
  // along with the v1 branch in the opener below. The date is written down because "for one
  // week" in a ruling becomes "forever" in a codebase that does not record when the week ends.
  const POP_V2 = (() => {
    try { return new URLSearchParams(location.search).get('pop') !== 'v1'; }
    catch (_) { return true; }
  })();

  // R-IV.1354(a), AND A REGRESSION THIS CAUGHT BEFORE ANYONE SAW IT. `POP_V2` now defaults
  // TRUE, and `boot()` had `if (POP_V2) { ...openRegimeDetails() }` -- so making the v2 drawer
  // the default would also have made the drawer OPEN ITSELF over the dashboard on every single
  // page load. That auto-open was never part of the view: it exists so Nick can preview the
  // drawer from the URL alone and so the headless gate can assert nine rendered sections
  // without driving a click. "Ship the previews" means the v2 drawer is what you get WHEN YOU
  // OPEN IT, not that it opens unbidden.
  //
  // So the auto-open reads the parameter EXPLICITLY and is unaffected by the default.
  const POP_V2_EXPLICIT = (() => {
    try { return new URLSearchParams(location.search).get('pop') === 'v2'; }
    catch (_) { return false; }
  })();

  // The ⓘ affordance. `title` carries it on desktop AND on phone, where a long-press shows it:
  // one mechanism, so there is no second code path that can disagree about what the note says.
  function pvInfo(note) {
    return '<span class="pv-i" tabindex="0" role="img" aria-label="about this section" title="'
      + esc(note || '') + '">i</span>';
  }

  function pvHead(label, note, right) {
    return '<div class="pv-h"><span>' + esc(label) + '</span>'
      + '<span class="pv-hr">' + (right || '') + (note ? pvInfo(note) : '') + '</span></div>';
  }

  // "unavailable" is a FIRST-CLASS RENDERING, not an empty box: `pv-na` is what the headless
  // gate counts, and every section routes its absent case through here so none of them can
  // invent a quieter way to say nothing.
  function pvNa(reason) {
    return '<div class="pv-na">unavailable — ' + esc(reason || 'no reason given') + '</div>';
  }

  function pvSpark(vals, opts) {
    const o = opts || {};
    const pts = (vals || []).filter((v) => v != null && isFinite(v));
    if (pts.length < 2) return '';
    const w = o.w || 96, h = o.h || 20;
    const min = Math.min.apply(null, pts), max = Math.max.apply(null, pts);
    const rng = (max - min) || 1, step = w / (pts.length - 1);
    const d = pts.map((v, i) =>
      (i ? 'L' : 'M') + (i * step).toFixed(1) + ',' + (h - ((v - min) / rng) * h).toFixed(1)
    ).join(' ');
    // The shaded band is drawn FIRST so the line sits on top of it, and it is clipped to the
    // box: a band drawn above the data's range would imply the series had been there.
    let band = '';
    if (o.bandFrom != null && max > min) {
      const y = Math.max(0, Math.min(h, h - ((o.bandFrom - min) / rng) * h));
      band = '<rect x="0" y="0" width="' + w + '" height="' + y.toFixed(1)
        + '" class="pv-band"/>';
    }
    const dot = o.dot === false ? ''
      : '<circle cx="' + w + '" cy="'
        + (h - ((pts[pts.length - 1] - min) / rng) * h).toFixed(1) + '" r="2.2"/>';
    return '<svg class="pv-sp" viewBox="0 0 ' + w + ' ' + h + '" width="' + w + '" height="'
      + h + '" aria-hidden="true">' + band + '<path d="' + d + '"/>' + dot + '</svg>';
  }

  // ── 1. hero ──────────────────────────────────────────────────────────────
  function pvHero(ft) {
    if (!ft || ft.error) return '<div class="pv-hero" id="pv-hero">' + pvNa(ft && ft.error) + '</div>';
    const pending = !!ft.candidate_differs;
    const held = ft.held_sessions;
    return '<div class="pv-hero" id="pv-hero">'
      + '<div class="pv-lab o">' + esc(ft.shown || '—') + '</div>'
      + '<div class="pv-sub m">'
      + (held != null ? esc(held) + (Number(held) === 1 ? ' session' : ' sessions') : 'held —')
      + ' · min hold ' + esc(ft.min_hold != null ? ft.min_hold : '—') + '</div>'
      + (pending
        ? '<div class="pv-next"><span class="pv-nk m">PROPOSED NEXT</span>'
          + '<span class="pv-nv o pv-pend">' + esc(ft.candidate) + '</span></div>'
        : '')
      + '</div>';
  }

  // ── 2. ribbon ────────────────────────────────────────────────────────────
  function pvRibbon(rb, pending) {
    if (!rb || !rb.sessions || !rb.sessions.length) {
      return '<div id="pv-ribbon">' + pvHead('40 SESSIONS', 'One square per settled session, '
        + 'oldest left. From the stored snapshots, current generation only.')
        + pvNa(rb && rb.error) + '</div>';
    }
    const last = rb.sessions.length - 1;
    const sq = rb.sessions.map((s, i) => {
      if (!s.label) {
        return '<span class="pv-sq pv-gap" title="' + esc(s.as_of || '') + ' · no label stored">'
          + '</span>';
      }
      // Today's square pulses when a flip is pending (R-IV.1252(c)2) — the pulse is on the
      // square the reader is looking for, not on the whole strip.
      const isToday = i === last;
      return '<span class="pv-sq' + (s.flipped ? ' pv-flipped' : '')
        + (isToday && pending ? ' pv-pend' : '') + '" style="background:'
        + leanColor(leanOf(s.label)) + '" title="' + esc(s.as_of || '') + ' · ' + esc(s.label)
        + (s.flipped ? ' · FLIPPED here' : '') + '"></span>';
    }).join('');
    const flips = rb.sessions.filter((s) => s.flipped).length;
    return '<div id="pv-ribbon">'
      + pvHead(rb.count + ' SESSIONS', rb.basis)
      + '<div class="pv-strip">' + sq + '</div>'
      + '<div class="pv-note m">' + flips + ' flip' + (flips === 1 ? '' : 's')
      + (rb.short_history ? ' · short history' : '') + '</div>'
      + '</div>';
  }

  // ── 3. lamps + suits ─────────────────────────────────────────────────────
  function pvLamps(lamps) {
    const v = _lastKillView;
    const kill = v && v.state === 'armed'
      ? '<span class="pv-chip pv-armed pv-pend">KILL ARMED</span>'
      : (v && v.state === 'unknown'
        ? '<span class="pv-chip pv-warn">KILL UNREADABLE</span>'
        : '<span class="pv-chip pv-dim">kill clear</span>');
    const ov = (lamps && lamps.overlays && lamps.overlays.available)
      ? '<span class="pv-chip">overlays</span>'
      : '<span class="pv-chip pv-dim" title="'
        + esc((lamps && lamps.overlays && lamps.overlays.reason) || '') + '">no feed</span>';
    // The "suits" line as chips (c)3. Context, not advice — the wording is the card's own.
    const suits = ['debit spreads over naked longs', 'premium pricey',
                   'shorts only early or as a tail']
      .map((t) => '<span class="pv-chip pv-suit">' + esc(t) + '</span>').join('');
    return '<div id="pv-lamps">'
      + pvHead('LAMPS', 'A lamp is shown only where a feed exists. An unlit lamp would read as '
        + '"checked, nothing firing"; "no feed" is the honest display.')
      + '<div class="pv-chips">' + kill + ov + '</div>'
      + pvHead('SUITS', 'Context, not a signal. What this regime usually suits.')
      + '<div class="pv-chips">' + suits + '</div>'
      + '</div>';
  }

  // ── 4. flip meter ────────────────────────────────────────────────────────
  function pvFlip(ft) {
    if (!ft || ft.error) return '<div id="pv-flip">' + pvHead('WHAT WOULD FLIP IT', '')
      + pvNa(ft && ft.error) + '</div>';
    const ip = ft.in_progress;
    const need = ip && ip.counter ? ip.counter.needed : (ip ? ip.closes_needed : 2);
    const have = ip && ip.counter ? ip.counter.banked : 0;
    // Close pips: filled = banked, the next one pulsing = pending (c)4.
    let pips = '';
    for (let i = 0; i < (need || 0); i++) {
      pips += '<span class="pv-pip' + (i < have ? ' on' : (i === have ? ' pv-pend' : ''))
        + '"></span>';
    }
    const sec = ft.sectors || {};
    let segs = '';
    if (sec.above != null && sec.total) {
      for (let i = 1; i <= sec.total; i++) {
        const on = i <= sec.above;
        // The dashed segment sits at the rule's REAL threshold, from the rules file.
        const mark = (sec.threshold != null && i === sec.threshold) ? ' pv-seg-th' : '';
        segs += '<span class="pv-seg' + (on ? ' on' : '') + mark + '"></span>';
      }
    }
    const bear = '<div class="pv-side">'
      + '<div class="pv-sk m">' + esc(ip ? ip.target_words : 'no candidate') + '</div>'
      + '<div class="pv-pips">' + pips + '</div>'
      + '<div class="pv-note m">' + (ip && ip.counter ? esc(ip.counter.text) : 'not proposed')
      + '</div></div>';
    const bull = '<div class="pv-side pv-right">'
      + '<div class="pv-sk m">' + esc((ft.up_order && ft.up_order.target_words) || 'SECTORS')
      + '</div>'
      + (segs ? '<div class="pv-segs">' + segs + '</div>'
        : pvNa(sec.reason || 'no sector count'))
      + '<div class="pv-note m">'
      + (sec.above != null ? esc(sec.above) + ' of ' + esc(sec.total) + ' above 50d · rule '
        + esc(sec.threshold) : '') + '</div></div>';
    return '<div id="pv-flip">'
      + pvHead('WHAT WOULD FLIP IT', (ip ? ip.condition + ' — ' : '')
        + (ft.no_distance_estimate || ''))
      + '<div class="pv-meter">' + bear
      + '<div class="pv-mid o">' + esc(ft.shown || '—') + '</div>' + bull + '</div>'
      + '</div>';
  }

  // ── 5. credit ────────────────────────────────────────────────────────────
  function pvCredit(c) {
    if (!c || !c.available) return '<div id="pv-credit">' + pvHead('CREDIT · HY OAS', '')
      + pvNa(c && c.reason) + '</div>';
    const chg = c.change_20d_bp;
    const gauge = c.pct_rank != null
      ? '<div class="pv-gauge"><i style="left:' + Math.max(0, Math.min(100, c.pct_rank))
        + '%"></i></div><div class="pv-gk m"><span>calm</span><span>stress</span></div>'
      : '';
    return '<div id="pv-credit">'
      + pvHead('CREDIT · HY OAS', c.basis,
        '<span class="pv-chip">' + esc(c.word) + '</span>')
      + '<div class="pv-row"><b class="pv-big m">' + esc(c.bp) + 'bp</b>'
      + (chg != null ? '<span class="pv-chg m ' + signCls(chg) + '">' + (chg > 0 ? '+' : '')
        + esc(chg) + 'bp / 20d</span>' : '')
      + pvSpark(c.spark, { w: 120, h: 26, bandFrom: c.top5_bp }) + '</div>'
      + gauge
      + '</div>';
  }

  // ── 6. breadth ───────────────────────────────────────────────────────────
  function pvBreadth(z) {
    const br = ((_lastRegime.regime || {}).breadth) || {};
    const c = br.sectors_above_50dma, t = br.sectors_total;
    const pct = (c != null && t) ? Math.round(100 * c / t) : null;
    const bar = (label, value, reason) => '<div class="pv-brow">'
      + '<span class="pv-bk m">' + esc(label) + '</span>'
      + (value == null
        ? '<span class="pv-na-inline" title="' + esc(reason || '') + '">unavailable</span>'
        : '<span class="pv-bbar"><i style="width:' + Math.max(0, Math.min(100, value))
          + '%"></i></span><span class="pv-bv m">' + esc(value) + '%</span>')
      + '</div>';
    // 20d and 200d ARE NOT STORED. The snapshot carries the 50d sector count only, so those
    // two bars say unavailable rather than being drawn from the 50d number — three bars from
    // one series would be the same fact three times wearing different labels.
    const noMa = 'the stored snapshot carries the 50-day sector count only; no 20d or 200d '
      + 'breadth series is recorded, and drawing them from the 50d number would be the same '
      + 'fact three times';
    const track = (z && z.available)
      ? '<div class="pv-track" title="' + esc(z.note || '') + '">'
        + '<i class="pv-tlow" style="left:' + Math.max(0, Math.min(100, z.low_in_window))
        + '%"></i>'
        + '<i class="pv-tnow" style="left:' + Math.max(0, Math.min(100, z.now_pct)) + '%"></i>'
        + '<i class="pv-tth" style="left:' + z.to_pct + '%"></i></div>'
        + '<div class="pv-note m">Zweig proxy · low ' + esc(z.low_in_window) + '% → '
        + esc(z.now_pct) + '% · thrust line ' + esc(z.to_pct) + '%'
        + (z.fired ? ' · FIRED' : '') + '</div>'
      : pvNa((z && z.reason) || 'no breadth series');
    return '<div id="pv-breadth">'
      + pvHead('BREADTH', 'Sectors above their own 50-day average, from the stored snapshot.',
        pct != null ? '<span class="pv-chip">' + esc(c) + ' of ' + esc(t) + '</span>' : '')
      + '<div class="pv-row"><b class="pv-big m">' + (pct != null ? esc(pct) + '%' : '—')
      + '</b></div>'
      + bar('50d', pct) + bar('20d', null, noMa) + bar('200d', null, noMa)
      + pvHead('ZWEIG THRUST', (z && z.note) || '',
        '<span class="pv-chip pv-warn">PROXY</span>')
      + track
      + '</div>';
  }

  // ── 7. leadership ────────────────────────────────────────────────────────
  function pvLead(l) {
    if (!l || !l.available) return '<div id="pv-lead">' + pvHead('LEADERSHIP', '')
      + pvNa(l && l.reason) + '</div>';
    const live = (l.rows || []).filter((r) => r.available && r.change_pct != null);
    // ONE SHARED SCALE across the five bars (c)7, so the lengths are comparable. Scaling each
    // bar to its own range would make a 0.3% move look like a 6% one.
    const span = Math.max(1, ...live.map((r) => Math.abs(r.change_pct)));
    const rows = (l.rows || []).map((r) => {
      if (!r.available) {
        return '<div class="pv-lrow"><span class="pv-lk m">' + esc(r.name) + '</span>'
          + '<span class="pv-na-inline" title="' + esc(r.reason || '') + '">unavailable</span>'
          + '</div>';
      }
      const v = r.change_pct || 0;
      const w = Math.min(50, Math.abs(v) / span * 50);
      return '<div class="pv-lrow" title="rising = ' + esc(r.rising_means || '') + '">'
        + '<span class="pv-lk m">' + esc(r.name) + '</span>'
        + '<span class="pv-div"><i class="' + (v >= 0 ? 'pos' : 'neg') + '" style="'
        + (v >= 0 ? 'left:50%;width:' + w.toFixed(1) + '%'
          : 'right:50%;width:' + w.toFixed(1) + '%') + '"></i></span>'
        + pvSpark(r.spark, { w: 54, h: 16, dot: false })
        + '<span class="pv-lv m ' + signCls(v) + '">' + (v > 0 ? '+' : '') + esc(v) + '%</span>'
        + '</div>';
    }).join('');
    return '<div id="pv-lead">'
      + pvHead('LEADERSHIP', l.basis,
        '<span class="pv-chip">' + esc(l.headline || '') + '</span>')
      + '<div class="pv-lscale m"><span>lagging</span><span>leading</span></div>'
      + rows + '</div>';
  }

  // ── 8. rates ─────────────────────────────────────────────────────────────
  function pvRates(r) {
    if (!r) return '<div id="pv-rates">' + pvHead('RATES', '') + pvNa('not read yet') + '</div>';
    const name = { real_10y: '10y REAL', breakeven_10y: '10y BREAKEVEN' };
    const tiles = (r.rows || []).map((x) => {
      if (!x.available) {
        return '<div class="pv-tile pv-dim"><span class="pv-tk m">' + esc(x.series)
          + '</span>' + pvNa(x.reason) + '</div>';
      }
      const chg = x.change_20d_bp;
      return '<div class="pv-tile"><span class="pv-tk m">'
        + esc(name[x.key] || x.key) + '</span>'
        + '<b class="pv-big m">' + esc(x.pct) + '%</b>'
        + pvSpark(x.spark, { w: 72, h: 18, dot: false })
        + (chg != null ? '<span class="pv-chg m ' + signCls(chg) + '">' + (chg > 0 ? '+' : '')
          + esc(chg) + 'bp</span>' : '') + '</div>';
    }).join('');
    const mv = r.move || {};
    const moveTile = mv.available
      ? '<div class="pv-tile"><span class="pv-tk m">MOVE</span><b class="pv-big m">'
        + esc(mv.value) + '</b></div>'
      : '<div class="pv-tile pv-dim"><span class="pv-tk m">MOVE</span>'
        + pvNa(mv.reason) + '</div>';
    return '<div id="pv-rates">' + pvHead('RATES & CROSS-ASSET', r.basis)
      + '<div class="pv-tiles">' + tiles + moveTile + '</div></div>';
  }

  // ── 9. auction ───────────────────────────────────────────────────────────
  function pvAuction(a) {
    if (!a || !a.available) {
      return '<div id="pv-auction" class="pv-dim">'
        + pvHead('AUCTION STATE', 'From the PYTHIA market-profile snapshot.')
        + pvNa((a && a.reason) || 'no snapshot') + '</div>';
    }
    return '<div id="pv-auction">'
      + pvHead('AUCTION STATE', a.basis,
        '<span class="pv-chip">' + esc(a.where || '') + '</span>')
      + '<div class="pv-note m">' + esc(a.where_basis || '') + '</div></div>';
  }

  // R-IV.1364(c) · THE B9 MOCK IS GONE. B9 is live (R-IV.1431, /api/b9/world), so its fixture,
  // its `?b9=1` review flag and the mock renderer were removed in the no-mock sweep. This slot
  // only exists on the `?clean=off` rollback drawer; it carries the same #b9-mount element as the
  // cleaned pop-out (R-IV.1432(d)), so assets/b9/b9_live.js fills it with the LIVE section here
  // too. Until that script has filled it, the one honest line stays.
  function pvWorldSlot() {
    return '<div class="pv-card"><div id="b9-mount" class="rg-b9" data-mount="b9">'
      + 'Global markets returns here once its live data is wired.</div></div>';
  }

  // ═══ R-IV.1369(d) · THE REGIME POP-OUT, CLEANED ═══════════════════════════════════════════
  //
  // Three layers, top to bottom, for a reader who wants the answer first: 1 the market right
  // now, 2 what it means for you, 3 the evidence -- collapsed, one row open at a time. Every
  // section reads what `renderPopV2` already reads (_rsLive, _rsSections, _rsPlaybooks,
  // _lastRegime, _lastKillView); nothing here fetches or computes a new figure.

  const RC_DOW = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];
  // 'YYYY-MM-DD' -> 'TUE 10-20'. A CALENDAR date read at UTC noon, so no timezone can move it
  // across midnight -- this is naming a stored date, not working out a session from a clock.
  function rcDay(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ''));
    if (!m) return '';
    const d = new Date(Date.UTC(+m[1], +m[2] - 1, +m[3], 12));
    return RC_DOW[d.getUTCDay()] + ' ' + m[2] + '-' + m[3];
  }
  const rcMd = (iso) => { const m = /^\d{4}-(\d{2})-(\d{2})/.exec(String(iso || '')); return m ? m[1] + '-' + m[2] : ''; };

  // R-IV.1369(d)1: THE STALE CHIP. Today's two-staleness logic and wording, exactly as
  // `rsHeadline` decides it -- the bars stopping beats "no rule matched" -- and ONLY ITS
  // PLACEMENT CHANGES: here it is a chip under the held line instead of R-IV.1278(b)4's
  // headline swap, so the last label stays readable. The BAND keeps the swap; this does not
  // touch `rsHeadline`. "Never a silent old label" still holds: the chip says how old.
  function rcStaleChip(m) {
    const fresh = m.data_freshness || {}, held = m.held_no_match || {};
    if (fresh.headline || fresh.stale) {
      const n = fresh.lag_sessions;
      const txt = (n != null ? n + (Number(n) === 1 ? ' SESSION OLD' : ' SESSIONS OLD') : 'DATA STALE')
        + (fresh.newest_bar ? ' · ' + rcDay(fresh.newest_bar) : '');
      return '<span class="rg-chip rg-amber" title="' + esc((fresh.headline || '') + ' · '
        + (fresh.reason || '')) + '">' + esc(txt) + '</span>';
    }
    if (held.stale) {
      return '<span class="rg-chip rg-amber" title="' + esc(held.reason || '') + '">STALE'
        + (held.group_word ? ' · ' + esc(held.group_word) : '') + '</span>';
    }
    return '';
  }

  // The kill-switch and event-overlay chips, in their EXISTING states (pvLamps): armed is the
  // only alarm, unreadable is amber ("cannot confirm"), clear is quiet. Quiet is --text-2, not
  // the old opacity dim, because H-13 forbids opacity-dimmed readable text.
  function rcLampChips(lamps) {
    const v = _lastKillView;
    // ONE CHANGE FROM pvLamps, deliberately: a view that was NEVER READ (null) is amber "not
    // read", not "clear". pvLamps falls through to "kill clear" there, which states a fact
    // about a switch nobody has looked at -- the fake-healthy fault in the one chip where it
    // matters most.
    const kill = v && v.state === 'armed'
      ? '<span class="rg-chip rg-down">KILL ARMED</span>'
      : (!v ? '<span class="rg-chip rg-amber">Kill switch not read</span>'
        : (v.state === 'unknown'
          ? '<span class="rg-chip rg-amber">Kill switch unreadable</span>'
          : '<span class="rg-chip rg-quiet">Kill switch clear</span>'));
    // "no feed", not "no overlay": overlays are not computed in v1, and "No event overlay"
    // would claim one was checked and found absent.
    const o = (lamps && lamps.overlays) || {};
    const ov = o.available
      ? '<span class="rg-chip rg-teal">Event overlay on</span>'
      : '<span class="rg-chip rg-quiet" title="' + esc(o.reason || '') + '">Event overlay: no feed</span>';
    return kill + ov;
  }

  // R-IV.1369(d)1: one cell per session in its label's lean colour, a dashed outline for a
  // session with no reading, and a legend with counts. A SHORT history is drawn short and
  // flagged amber -- it is not padded out to 40 with invented "no reading" cells, which would
  // claim sessions were read and found empty when they were simply not in this generation.
  //
  // R-IV.1448(b)1: below RIBBON_MIN stored sessions there is NO strip at all -- the amber chip and
  // one line instead. A strip of one or two squares read as a stray mark on the 10-26 check, not
  // as a history; from RIBBON_MIN on it is drawn exactly as above.
  const RIBBON_MIN = 5;
  function rcRibbon(rb) {
    if (!rb || !rb.sessions || !rb.sessions.length) {
      return '<div class="rg-ribbon">' + pvNa((rb && rb.error) || 'no stored sessions') + '</div>';
    }
    if (rb.sessions.length < RIBBON_MIN) {
      return '<div class="rg-ribbon rg-ribbon-short"><div class="rg-legend"><span class="rg-chip rg-amber" title="'
        + esc(rb.basis || '') + '">SHORT HISTORY · ' + esc(rb.count != null ? rb.count : rb.sessions.length)
        + ' OF ' + esc(rb.asked_for || 40) + '</span></div><div class="rg-note">fills in nightly</div></div>';
    }
    const counts = new Map();
    const cells = rb.sessions.map((s) => {
      if (!s.label) {
        counts.set('', (counts.get('') || 0) + 1);
        return '<i class="rg-cell rg-none" title="' + esc((s.as_of || '') + ' · no reading') + '"></i>';
      }
      counts.set(s.label, (counts.get(s.label) || 0) + 1);
      return '<i class="rg-cell" style="background:' + leanColor(leanOf(keyWord(s.label)))
        + '" title="' + esc((s.as_of || '') + ' · ' + keyWord(s.label)) + '"></i>';
    }).join('');
    const legend = [...counts.entries()].map(([k, n]) => k
      ? '<span class="rg-leg"><i style="background:' + leanColor(leanOf(keyWord(k))) + '"></i>'
        + esc(keyWord(k).toLowerCase().replace(/^./, (c) => c.toUpperCase())) + ' ' + n + '</span>'
      : '<span class="rg-leg"><i class="rg-none"></i>No reading ' + n + '</span>').join('');
    const short = rb.short_history
      ? '<span class="rg-chip rg-amber" title="' + esc(rb.basis || '') + '">SHORT HISTORY · '
        + esc(rb.count) + ' OF ' + esc(rb.asked_for) + '</span>' : '';
    return '<div class="rg-ribbon"><div class="rg-cells">' + cells + '</div>'
      + '<div class="rg-legend">' + legend + short + '</div>'
      + '<div class="rg-note">last ' + esc(rb.count) + ' session' + (Number(rb.count) === 1 ? '' : 's') + '</div></div>';
  }

  function rcLayer1(m) {
    const ft = m.flip_triggers || {};
    const lab = m.regime_label || ft.shown || '—';
    const lean = leanOf(lab) || leanOf(keyWord(m.regime_key));
    const held = ft.held_sessions != null ? ft.held_sessions : m.held_sessions;
    const minHold = ft.min_hold;
    // "leaning toward <candidate>" only when the classifier IS proposing one; the clause is
    // dropped, not filled with "nothing", when it is not (R-IV.1369(d)1).
    const lean2 = ft.candidate_differs && ft.candidate
      ? ' · leaning toward <b class="rg-cand" style="color:' + leanColor(leanOf(ft.candidate))
        + '">' + esc(ft.candidate) + '</b>' : '';
    return '<section class="rg-l rg-l1">'
      + '<div class="rg-sec">1 · THE MARKET RIGHT NOW</div>'
      + '<div class="rg-hero" style="color:' + headColor(lean) + '">' + esc(lab) + '</div>'
      + '<div class="rg-held">Held ' + esc(held != null ? held : '—') + ' session'
      + (Number(held) === 1 ? '' : 's') + (minHold != null ? ' (minimum ' + esc(minHold) + ')' : '')
      + lean2 + '</div>'
      + '<div class="rg-chips">' + rcStaleChip(m) + rcLampChips((_rsSections || {}).lamps) + '</div>'
      + rcRibbon(m.ribbon)
      + '</section>';
  }

  // R-IV.1369(d)2(i): the playbook card, VERBATIM from playbooks.v2.json for the shown regime.
  // Premium in full at 90 characters or fewer; otherwise its first and last sentences, with
  // "more" for the rest. Sentences split only on punctuation FOLLOWED BY WHITESPACE, so
  // "0.15%" and "[MKT]." do not cut a sentence in half.
  function rcSentences(t) {
    return String(t || '').replace(/([.!?])\s+/g, '$1\u0000').split('\u0000').map((s) => s.trim()).filter(Boolean);
  }
  function rcPlaybook(m) {
    const pb = (((_rsPlaybooks || {}).regimes) || {})[m.regime_key];
    if (!pb) return '<div class="rg-card">' + pvNa('no registered playbook for ' + (m.regime_key || 'this label')) + '</div>';
    const prem = String(pb.premium || '');
    let premHtml = '';
    if (prem) {
      const ss = rcSentences(prem);
      premHtml = prem.length <= 90 || ss.length < 3
        ? '<p>Premium: ' + esc(prem) + '</p>'
        : '<p>Premium: <span class="rg-pshort">' + esc(ss[0] + ' ' + ss[ss.length - 1]) + '</span>'
          + '<span class="rg-pfull" hidden>' + esc(prem) + '</span> '
          + '<button type="button" class="rg-more" data-rg-more aria-expanded="false">more</button></p>';
    }
    const watch = (pb.matters_now || []).length
      ? '<p>Watch: ' + esc(pb.matters_now.join(' · ')) + '</p>' : '';
    return '<div class="rg-card rg-pb">'
      + '<div class="rg-ct">What usually works · ' + esc(pb.label || keyWord(m.regime_key)) + '</div>'
      + (pb.tape ? '<p>' + esc(pb.tape) + '</p>' : '') + premHtml + watch
      + '<div class="rg-foot">From the registered playbook · context, not a signal</div></div>';
  }

  // R-IV.1369(d)2(ii): B8's flip_triggers() in the new style, B8'S HONESTY RULES INTACT
  // (R-IV.1243(e)): no distance anywhere; a counter ONLY on the label the classifier is
  // proposing, drawn as segments; each neighbour's condition VERBATIM; a proposed label that is
  // also a neighbour shown ONCE; and B8's sector bar stays where B8 shows it, with the up side.
  function rcSegs(banked, needed, cls) {
    let s = '';
    for (let i = 0; i < (Number(needed) || 0); i++) s += '<i class="' + (i < banked ? 'on ' : '') + cls + '"></i>';
    return s;
  }
  function rcBlock(kind, b, ft, withSectors) {
    if (!b) return '';
    const proposing = !!(b.proposing && b.counter);
    const right = proposing
      ? '<span class="rg-bk">' + esc(b.counter.text) + ' closes</span>'
      : '<span class="rg-bk rg-dim">not in progress</span>';
    const segs = proposing
      ? '<div class="rg-segs" title="' + esc(b.closes_basis || '') + '">'
        + rcSegs(Math.min(Number(b.counter.banked) || 0, Number(b.counter.needed) || 0),
                 b.counter.needed, 'rg-seg') + '</div>' : '';
    const sec = ft.sectors || {};
    let sectors = '';
    if (withSectors && sec.above != null && sec.total) {
      let bar = '';
      for (let i = 1; i <= sec.total; i++) {
        bar += '<i class="rg-sseg' + (i <= sec.above ? ' on' : '') + (sec.threshold === i ? ' th' : '') + '"></i>';
      }
      sectors = '<div class="rg-sbar" title="' + esc(sec.basis || '') + '">' + bar + '</div>'
        + '<div class="rg-note">' + esc(sec.above) + ' of ' + esc(sec.total) + ' sectors above their 50-day · rule '
        + esc(sec.threshold) + '</div>';
    } else if (withSectors && sec.reason) {
      sectors = '<div class="rg-note">' + esc(sec.reason) + '</div>';
    }
    return '<div class="rg-blk">'
      + '<div class="rg-bh"><b style="color:' + leanColor(leanOf(b.target_words)) + '">' + esc(kind)
      + ' → ' + esc(b.target_words || '') + '</b>' + right + '</div>' + segs
      + '<div class="rg-cond">Shows when: ' + esc(b.condition || '') + '</div>' + sectors + '</div>';
  }
  function rcChange(ft) {
    if (!ft || ft.error) return '<div class="rg-card">' + pvNa(ft && ft.error) + '</div>';
    const ip = ft.in_progress;
    const same = (b) => ip && b && b.target === ip.target;
    return '<div class="rg-card rg-chg">'
      + '<div class="rg-ct">What would change it<span class="rg-ctr">counts, not distances'
      + pvInfo((ft.no_distance_estimate || '') + ' ' + (ft.order_note || '')) + '</span></div>'
      + (ip ? rcBlock('IN PROGRESS', ip, ft, false) : '')
      + (same(ft.down_order) ? '' : rcBlock('ONE STEP DOWN', ft.down_order, ft, false))
      + (same(ft.up_order) ? '' : rcBlock('ONE STEP UP', ft.up_order, ft, true))
      + '<div class="rg-foot">“One step up” means the next label in the hub’s list, not a safer one.</div></div>';
  }

  // R-IV.1369(d)2(iii): WARNING SIGNS ARE THE REGISTERED TAGS. The rules file lists them under
  // "Section 2: tags, not regimes" -- tags never change the label, which is exactly this
  // section's footnote. The payload's `tags` says which are lit. The list is the rules file's
  // `tags.available` (regime_rules.v2.1.json), and tests/test_r1369_agora_clean.py fails if the
  // two ever differ, so this cannot drift into a list nobody registered.
  const RC_TAGS = ['narrow', 'credit-stress', 'recession-backed', 'lens-split', 'index-divergence',
    'capitulation-day'];
  function rcWarnings(m) {
    const lit = new Set((m.tags || []).map(String));
    // A lit tag the list does not know is shown, never dropped: a new registered tag must
    // appear before anyone updates this file.
    const all = RC_TAGS.concat([...lit].filter((t) => RC_TAGS.indexOf(t) < 0));
    const human = (t) => t.replace(/-/g, ' ').replace(/^./, (c) => c.toUpperCase());
    return '<div class="rg-warn"><div class="rg-ct">Warning signs</div><div class="rg-chips">'
      + all.map((t) => lit.has(t)
        ? '<span class="rg-chip rg-teal">● ' + esc(human(t)) + '</span>'
        : '<span class="rg-chip rg-off">○ ' + esc(human(t)) + '</span>').join('')
      + '</div><div class="rg-foot">Warnings never change the label on their own.</div></div>';
  }

  // R-IV.1369(d)3: ONE COLLAPSED ROW PER FAMILY. Each row's status is the word that family's
  // read already produces; where it produces none, its key number is shown instead, and a
  // number takes no lean colour. The opened row reuses that family's existing section
  // renderer, so its sources come with it and nothing is re-derived.
  function rcEvidenceRows(m) {
    const S = _rsSections || {};
    const sign = (v) => (Number(v) > 0 ? '+' : Number(v) < 0 ? '−' : '') + Math.abs(Number(v));
    const rows = [];
    const r200 = m.ma200_row || {};
    rows.push({ k: 'ma200', name: '200-day line',
      word: r200.available ? r200.side : null,
      detail: r200.available
        ? 'SPY ' + Math.abs(Number(r200.pct)) + '% ' + (String(r200.side) === 'ABOVE' ? 'above' : 'below')
          + ' it · since ' + rcMd(r200.since)
        : (r200.reason || 'not available'),
      body: r200.available
        ? '<div class="rg-src">' + esc(r200.text || '') + '</div>'
          + (r200.caveat ? '<div class="rg-src">' + esc(r200.caveat) + '</div>' : '')
          + '<div class="rg-src rg-dim">' + esc(r200.basis || '') + '</div>'
        : pvNa(r200.reason) });
    const z = S.zweig || {};
    rows.push({ k: 'breadth', name: 'Breadth', number: breadthNow(),
      detail: z.available ? (z.reason || '') : (z.reason || 'not read yet'),
      body: pvBreadth(S.zweig) });
    const c = S.credit || {};
    rows.push({ k: 'credit', name: 'Credit',
      word: c.available ? c.word : null,
      detail: c.available
        ? 'High-yield spread ' + c.bp + 'bp · ' + sign(c.change_20d_bp) + 'bp in 20 days'
        : (c.reason || 'not read yet'),
      body: pvCredit(S.credit) });
    const rr = S.rates || {}, rrow = (k) => ((rr.rows || []).find((x) => x.key === k) || {});
    const real = rrow('real_10y'), be = rrow('breakeven_10y');
    rows.push({ k: 'rates', name: 'Rates',
      number: real.available ? Number(real.pct).toFixed(2) + '%' : null,
      // MOVE's absence is stated INSIDE the opened row (pvRates names it with its reason), not on
      // this one collapsed line: the line is the headline figure, and a third clause about a
      // missing series pushed it past one line on a phone.
      detail: rr.available
        ? '10y real yield' + (be.available ? ' · breakeven ' + Number(be.pct).toFixed(2) + '%' : '')
        : (rr.reason || 'not read yet'),
      body: pvRates(S.rates) });
    const vc = volCurveView(_lastRegime.composite);
    rows.push({ k: 'vol', name: 'Volatility',
      word: vc.word || null,
      detail: vc.word ? 'VIX against its 3-month: ' + vc.value + ' · ' + vc.sub : vc.sub,
      body: '<div class="rg-src">' + esc(vc.sub) + '</div><div class="rg-src rg-dim">'
        + esc(GLOSSARY.VOLCURVE || '') + '</div>' });
    const l = S.leadership || {};
    const live = (l.rows || []).filter((x) => x.available && x.change_pct != null);
    const top = live.slice().sort((a, b) => b.change_pct - a.change_pct);
    rows.push({ k: 'lead', name: 'Leadership',
      number: l.available ? (l.headline || null) : null,
      detail: top.length >= 2
        ? 'leading ' + top[0].name + ' · lagging ' + top[top.length - 1].name
        : (l.reason || 'not read yet'),
      body: pvLead(S.leadership) });
    const cr = (_agora || {}).crowd || null;
    const cw = cr && cr.headline ? String(cr.headline).replace(/^CROWD\s+/i, '') : null;
    rows.push({ k: 'crowd', name: 'Crowd', word: cw,
      detail: cr ? (cr.headline_basis || '') : 'the crowd read did not load',
      body: cr ? (cr.rows || []).map((x) => '<div class="rg-src"><b>' + esc(x.key) + '</b> '
        + esc(x.value == null ? '—' : x.value) + (x.pct_label ? ' · ' + esc(x.pct_label) : '')
        + ' · ' + esc(x.source || '') + '</div>').join('') : pvNa('the crowd read did not load') });
    const a = S.auction || {};
    rows.push({ k: 'auction', name: 'Auction state',
      word: a.available ? a.where : null,
      detail: a.available ? (a.where_basis || '') : (a.reason || 'no snapshot'),
      body: pvAuction(S.auction) });
    return rows;
  }
  let _rcOpenEv = null;
  function rcEvidence(m) {
    const rows = rcEvidenceRows(m).map((r) => {
      const open = _rcOpenEv === r.k;
      const lean = r.word ? leanOf(r.word) : null;
      const status = r.word
        ? '<span class="rg-st" style="color:' + headColor(lean) + ';border-color:' + headColor(lean) + '">' + esc(r.word) + '</span>'
        : (r.number != null && r.number !== '—'
          ? '<span class="rg-st rg-num">' + esc(r.number) + '</span>'
          : '<span class="rg-st rg-num" title="' + esc(r.detail || '') + '">—</span>');
      return '<div class="rg-ev' + (open ? ' open' : '') + '" data-ev="' + r.k + '">'
        + '<button type="button" class="rg-evh" data-rg-ev="' + r.k + '" aria-expanded="' + open + '">'
        + '<span class="rg-evn"><b>' + esc(r.name) + '</b><span>' + esc(r.detail || '') + '</span></span>'
        + status + '<span class="rg-chev" aria-hidden="true">›</span></button>'
        + '<div class="rg-evb"' + (open ? '' : ' hidden') + '>' + r.body + '</div></div>';
    }).join('');
    return '<section class="rg-l rg-l3"><div class="rg-sec">3 · THE EVIDENCE</div>'
      + '<div class="rg-hint">One line each. Tap a row for its detail and sources.</div>' + rows
      + '</section>';
  }

  // R-IV.1432(d): B9'S MOUNT POINT. BUILD's B9 section (R-IV.1431) replaces the CONTENT of
  // #b9-mount when it ships; the element, its id and its place below the evidence stay. Until
  // then it holds the one --text-3 line R-IV.1369(d)4 names.
  function rcB9Mount() {
    return '<div id="b9-mount" class="rg-b9" data-mount="b9">'
      + 'Global markets returns here once its live data is wired.</div>';
  }

  function renderPopClean(body) {
    const m = _rsLive || {};
    // R-IV.1357(b): the header still carries the rules version the payload reports.
    const ttl = $('drawerTitle');
    if (ttl) ttl.textContent = 'REGIME STRATEGY' + (m.rules_version ? ' ' + String(m.rules_version) : '');
    body.innerHTML = '<div class="rg">'
      + rcLayer1(m)
      + '<section class="rg-l rg-l2"><div class="rg-sec">2 · WHAT IT MEANS FOR YOU</div>'
      + rcPlaybook(m) + rcChange(m.flip_triggers) + rcWarnings(m) + '</section>'
      + rcEvidence(m) + rcB9Mount() + '</div>';
    if (!body.__rcWired) {
      body.__rcWired = true;
      body.addEventListener('click', (e) => {
        const ev = e.target.closest && e.target.closest('[data-rg-ev]');
        if (ev) {
          // ONE ROW OPEN AT A TIME: opening a row closes the last one, tapping it again closes it.
          const k = ev.getAttribute('data-rg-ev');
          _rcOpenEv = _rcOpenEv === k ? null : k;
          body.querySelectorAll('.rg-ev').forEach((row) => {
            const on = row.getAttribute('data-ev') === _rcOpenEv;
            row.classList.toggle('open', on);
            const h = row.querySelector('.rg-evh'), b = row.querySelector('.rg-evb');
            if (h) h.setAttribute('aria-expanded', String(on));
            if (b) b.hidden = !on;
          });
          return;
        }
        const more = e.target.closest && e.target.closest('[data-rg-more]');
        if (more) {
          const p = more.parentNode, on = more.getAttribute('aria-expanded') !== 'true';
          p.querySelector('.rg-pshort').hidden = on;
          p.querySelector('.rg-pfull').hidden = !on;
          more.setAttribute('aria-expanded', String(on));
          more.textContent = on ? 'less' : 'more';
        }
      });
    }
  }

  function renderPopV2(body) {
    const m = _rsLive || {};
    // R-IV.1357(b): THE HEADER CARRIES THE RULES VERSION THE PAYLOAD REPORTS, never a literal.
    // With no payload yet it carries NO version rather than a guessed one: an absent suffix
    // says "not read yet", and a wrong suffix says something false about which rules are live.
    const _ttl = $('drawerTitle');
    if (_ttl) {
      _ttl.textContent = 'REGIME STRATEGY'
        + (m.rules_version ? ' ' + String(m.rules_version) : '');
    }
    const ft = m.flip_triggers;
    const pending = !!(ft && ft.candidate_differs);
    const S = _rsSections || {};
    body.innerHTML =
      pvHero(ft)
      + '<div class="pv-card">' + pvRibbon(m.ribbon, pending) + '</div>'
      + '<div class="pv-card">' + pvLamps(S.lamps) + '</div>'
      + '<div class="pv-card">' + pvFlip(ft) + '</div>'
      + '<div class="pv-card">' + pvCredit(S.credit) + '</div>'
      + '<div class="pv-card">' + pvBreadth(S.zweig) + '</div>'
      + '<div class="pv-card">' + pvLead(S.leadership) + '</div>'
      // B9 sits HERE because the synthesis says "next to the leadership ratios".
      + pvWorldSlot()
      + '<div class="pv-card">' + pvRates(S.rates) + '</div>'
      + '<div class="pv-card">' + pvAuction(S.auction) + '</div>';
  }

  async function openRegimeDetails(src) {
    closePopup();
    // Fetched on open, not on a poll: the drawer is the only reader, and these are daily
    // series. An await here is why the sections say "loading" rather than drawing zeros.
    await loadRegimeSections();
    const d = $('drawer');
    // R-IV.1371(c)1: THE SIDE COMES FROM THE TILE, not from a literal.
    //
    // This read `setSide(d, 'left')`. Every other opener on the page already asks `popSide()`
    // -- the chart (919), BOOK (4476), the river (7852), positions (8062) -- and `popSide()`
    // has always judged the tile's centre against the viewport's. The regime drawer alone was
    // pinned left, so when Nick moved Regime Strategy to the RIGHT of his grid on 10-19 its
    // pop-out kept opening on the far side of the screen from the tile he had just tapped.
    //
    // `src` is the element tapped, so the side is judged AT TAP TIME and follows the tile when
    // it is dragged. 'regime-strategy' is the fallback gs-id for the case where the drawer is
    // opened by something other than a click inside the tile.
    setSide(d, popSide(src, 'regime-strategy'));
    syncTopbarH();
    const title = $('drawerTitle'), body = $('drawerBody');
    title.textContent = 'REGIME STRATEGY';

    // R-IV.1257(b)1: v2 renders ONLY for ?pop=v2, and v1 below is untouched. Branching
    // here rather than replacing the function keeps the default on the code Nick is
    // using all week, so the preview cannot regress what it is compared against.
    // R-IV.1369(g): the cleaned pop-out is the default; `?clean=off` falls through to the v2
    // drawer below, untouched. Same width class, same backdrop and history wiring as v2, so the
    // ✕, the backdrop and Android's back gesture behave exactly as R-IV.1364(a) measured.
    if (CLEAN && POP_V2) {
      d.classList.add('pv-wide');
      renderPopClean(body);
      $('drawerBackdrop').classList.add('open'); openedDrawerHistory();
      d.classList.add('open');
      const b3 = $('rsOpen');
      if (b3) b3.setAttribute('aria-expanded', 'true');
      return;
    }
    if (POP_V2) {
      // R-IV.1357(b): the version is NOT written here any more. It was the literal string
      // 'REGIME STRATEGY v2' while the payload's `rules_version` had been v2.1 since the
      // 2026-10-22 cutover -- a header disagreeing with the card beneath it about which rules
      // produced the label. `renderPopV2` sets it from the payload, and sets it again on its
      // own repaint, so it cannot be left stale by whichever paint happens first.
      d.classList.add('pv-wide');
      renderPopV2(body);
      $('drawerBackdrop').classList.add('open'); openedDrawerHistory();
      d.classList.add('open');
      const b2 = $('rsOpen');
      if (b2) b2.setAttribute('aria-expanded', 'true');
      return;
    }
    const m = _rsLive || {};
    const sec = (n, name) => '<div class="rd-sec">' + n + ' · ' + esc(name) + '</div>';
    const mock = (why) => '<div class="rd-mock">MOCK · ' + esc(why) + '</div>';
    const kv = (k, v) => '<div class="kv"><span class="k">' + esc(k)
      + '</span><span class="v">' + esc(v) + '</span></div>';

    body.innerHTML =
      // The live header: this part is NOT mock, it is the card's own stored label.
      '<div class="rd-head">'
      + '<b class="rd-lab" style="color:' + leanColor(leanOf(m.regime_label)) + '">'
      + esc(m.regime_label || '—') + '</b>'
      + '<span class="rd-sub">' + esc(m.settled_close || '—') + ' · '
      + esc(m.close_source || '') + ' · display only</span>'
      + (m.diff && m.diff.detail ? '<span class="rd-diff">' + esc(m.diff.detail)
        + '</span>' : '')
      + '</div>'
      + '<div class="rd-ctx">Usually suits: debit spreads over naked longs · premium '
      + 'pricey · shorts only early or as a tail. Context, not a signal.</div>'

      + sec('1', 'WHAT WOULD FLIP IT') + flipTriggersHtml(m.flip_triggers)
      + sec('2', 'CREDIT · HY SPREAD') + creditHtml(_rsSections.credit)
      + sec('3', 'BREADTH · % ABOVE 50D')
      + kv('Live now', breadthNow())
      + zweigHtml(_rsSections.zweig)
      + sec('4', 'LEADERSHIP · WHO IS CARRYING THE INDEX')
      + leadershipHtml(_rsSections.leadership)
      + sec('5', 'RATES & CROSS-ASSET') + ratesHtml(_rsSections.rates)
      + sec('6', 'AUCTION STATE') + auctionHtml(_rsSections.auction)
      + sec('7', 'REGIME RIBBON') + ribbonHtml(m.ribbon)
      + sec('8', 'LAMPS') + lampsHtml(_rsSections.lamps)
      // THE FOOTER COUNTS, rather than asserting. It said "the sections above are
      // placeholders" while section 7 was live -- a caption that stops being true the moment
      // a section is wired, which is the caption-lies-about-its-field fault. It now names
      // what is wired and what is not, so wiring section 8 changes the count and not this
      // sentence.
      // R-IV.1246(b): the "Phase A placeholders" footer is GONE, because none are left. All
      // eight sections are wired; where a source has no feed the SECTION says so in its own
      // row, which is where a reader is looking. A standing footer about placeholders would
      // now be the stale caption this one replaced.
      + '';

    $('drawerBackdrop').classList.add('open'); openedDrawerHistory();
    d.classList.add('open');
    const btn = $('rsOpen');
    if (btn) btn.setAttribute('aria-expanded', 'true');
  }
  // R-IV.1364(a): ANDROID'S BACK GESTURE CLOSES THE POP-OUT.
  //
  // On a phone the back gesture is how you leave anything that covers the screen, and the
  // drawer had no history entry -- so back left Agora entirely instead of closing the drawer.
  // Opening pushes one state; closing pops it only if it is still ours, so a close by the X or
  // by the backdrop does not eat a real navigation the user made in between.
  let _drawerHist = false;

  function openedDrawerHistory() {
    if (_drawerHist) return;
    try { history.pushState({ pandoraDrawer: true }, ''); _drawerHist = true; } catch (_) {}
  }

  function closeDrawer(fromPopstate) {
    $('drawerBackdrop').classList.remove('open'); $('drawer').classList.remove('open'); placeChartSoon();
    if (_divOpen) { _divOpen = false; if (_charts.divChart) { _charts.divChart.destroy(); delete _charts.divChart; } }
    if (_drawerHist) {
      _drawerHist = false;
      // NOT when the popstate IS the back gesture -- the entry is already gone, and calling
      // back() again would navigate off the page, which is the bug this fixes, inverted.
      if (!fromPopstate) { try { history.back(); } catch (_) {} }
    }
  }

  window.addEventListener('popstate', () => {
    if ($('drawer') && $('drawer').classList.contains('open')) closeDrawer(true);
  });

  // Escape closes it too. Free on desktop and costs nothing on a phone.
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if ($('drawer') && $('drawer').classList.contains('open')) closeDrawer();
  });

  // ── Pop-out sides ─────────────────────────────────────────────────────────
  // A pop-out opens on the side of the screen its source tile sits on, and follows the tile
  // when it is dragged across (recomputed on every open). At phone width every pop-out is
  // full width, so there is no side. A pop-out opened from inside another inherits its side.
  let _lastClick = { el: null, t: 0 };
  document.addEventListener('click', (e) => { _lastClick = { el: e.target, t: Date.now() }; }, true);
  function popSide(src, fallbackGsId) {
    const W = document.documentElement.clientWidth;
    if (W <= 820) return 'right';
    let el = src && src.isConnected ? src : null;
    if (!el && _lastClick.el && _lastClick.el.isConnected && Date.now() - _lastClick.t < 1000) el = _lastClick.el;
    const host = el && el.closest ? el.closest('.drawer.open, .member-popup.open, .rp-panel.open') : null;
    if (host) return host.classList.contains('from-left') || host.classList.contains('side-left') ? 'left' : 'right';
    let tile = el && el.closest ? el.closest('.grid-stack-item') : null;
    if (!tile && fallbackGsId) tile = document.querySelector('.grid-stack-item[gs-id="' + fallbackGsId + '"]');
    let r = tile ? tile.getBoundingClientRect() : null;
    // Full-width tiles (regime band, movers) have no side of their own: use what was clicked.
    if (r && r.width > W * 0.6 && el && el.getBoundingClientRect) { const er = el.getBoundingClientRect(); if (er.width > 0) r = er; }
    if (!r || r.width <= 0) return 'right';
    return (r.left + r.width / 2) < W / 2 ? 'left' : 'right';
  }
  // Swap a sliding panel's side without animating it across the screen: the class change
  // happens with transitions off, a reflow commits it, and only then may '.open' animate.
  function setSide(panel, side) {
    if (!panel) return;
    const left = side === 'left';
    if (panel.classList.contains('from-left') === left) return;
    panel.classList.add('no-anim');
    panel.classList.toggle('from-left', left);
    void panel.offsetWidth;
    panel.classList.remove('no-anim');
  }

  // ── Chart popup (click any ticker) ─────────────────────────────────────────
  // TradingView embed: the browser talks to TradingView directly, so opening a chart makes
  // zero hub or UW calls. Centred in the free space between whatever pop-outs are open, about
  // 50% x 45% of the window (~22% of the screen). Non-modal: another ticker click switches it.
  // Moving averages: EMA 9 + SMA 50 + SMA 200. EMA 9 because the composite's own trend factor
  // (spy_trend_intraday) scores price against a 9-EMA, so the chart and the hub agree (Olympus
  // recommendation, Nick deferred to it). The embed colours by study TYPE, not instance: the EMA
  // gets its own colour; the two SMAs share one and the legend names each length.
  const CHART_MA9_TYPE = 'EMA';
  const CHART_MAS = [[CHART_MA9_TYPE, 9], ['SMA', 50], ['SMA', 200]];
  const CHART_SYM = /^[A-Z0-9.:!^=\-\/]{1,24}$/;
  let _chartSym = null, _chartOpener = null, _placeTimer = null;
  function chartTk(t) {
    const sym = String(t || '').toUpperCase();
    return `<span class="tk-link" data-chart="${esc(sym)}" tabindex="0" role="button" aria-label="Chart ${esc(sym)}">${esc(t || '')}</span>`;
  }
  function openChart(sym, opener) {
    sym = String(sym || '').trim().toUpperCase();
    if (!CHART_SYM.test(sym)) return;
    const pop = $('tvPopover');
    _chartOpener = opener || document.activeElement;
    if (_chartSym !== sym || !pop.classList.contains('open')) {
      _chartSym = sym;
      $('tvPopTicker').textContent = sym;
      const key = document.querySelector('#tvPopover .tv-key');
      if (key) key.textContent = 'Daily · ' + CHART_MAS.map(([t, n]) => t + ' ' + n).join(' · ');
      $('tvPopHost').innerHTML = '<div id="tvPopHostInner" style="width:100%;height:100%"></div>';
      try {
        if (window.TradingView) {
          new TradingView.widget({
            container_id: 'tvPopHostInner', symbol: sym, interval: 'D', timezone: 'America/New_York',
            theme: 'dark', style: '1', locale: 'en', autosize: true,
            hide_top_toolbar: true, hide_side_toolbar: true, hide_volume: true, hide_legend: false,
            allow_symbol_change: false, save_image: false,
            studies: CHART_MAS.map(([t, n]) => ({ id: t === 'EMA' ? 'MAExp@tv-basicstudies' : 'MASimple@tv-basicstudies', inputs: { length: n } })),
            studies_overrides: {
              'moving average.plot.color': '#38bdf8', 'moving average.plot.linewidth': 2,
              'moving average exponential.plot.color': '#a78bfa', 'moving average exponential.plot.linewidth': 2,
            },
          });
        } else {
          $('tvPopHost').innerHTML = '<div class="tv-unavail">Chart library did not load (TradingView unreachable).</div>';
        }
      } catch (_) {}
    }
    pop.classList.add('open');
    placeChart();
    const x = $('tvPopClose'); if (x) { try { x.focus({ preventScroll: true }); } catch (_) {} }
  }
  function closeChart() {
    const pop = $('tvPopover');
    if (!pop || !pop.classList.contains('open')) return false;
    pop.classList.remove('open'); $('tvPopHost').innerHTML = ''; _chartSym = null;
    const o = _chartOpener; _chartOpener = null;
    if (o && o.isConnected && o.focus) { try { o.focus({ preventScroll: true }); } catch (_) {} }
    return true;
  }
  function placeChart() {
    const pop = $('tvPopover');
    if (!pop || !pop.classList.contains('open')) return;
    const W = document.documentElement.clientWidth, H = window.innerHeight;
    if (W <= 768) { pop.style.width = ''; pop.style.height = ''; pop.style.left = '2vw'; pop.style.top = ''; return; }
    // Free horizontal band = the window minus any open side pop-out.
    let L = 0, R = W;
    document.querySelectorAll('.drawer.open, .member-popup.open, .rp-panel.open, .pp-panel.open, .pos-modal.open').forEach((el) => {
      const r = el.getBoundingClientRect();
      if (r.width <= 0 || r.right <= 0 || r.left >= W) return;
      if (r.left + r.width / 2 < W / 2) L = Math.max(L, r.right); else R = Math.min(R, r.left);
    });
    let w = Math.max(480, Math.round(W * 0.5));
    const top0 = topbarH();                               // centre in the area below the top bar
    const h = Math.min(H - top0 - 32, Math.max(320, Math.round(H * 0.45)));
    const free = R - L - 32;
    let x;
    if (free >= 400) { w = Math.min(w, free); x = Math.min(Math.max(W / 2 - w / 2, L + 16), R - 16 - w); }
    else { w = Math.min(w, W - 32); x = (W - w) / 2; }   // no room beside the pop-outs: overlap, centred
    pop.style.width = w + 'px'; pop.style.height = h + 'px';
    pop.style.left = Math.round(x) + 'px'; pop.style.top = Math.round(top0 + (H - top0 - h) / 2) + 'px';
  }
  // Pop-outs and their backdrops start below the top bar (quote, full screen, future beacon
  // stay visible). The bar wraps on narrow screens, so its height is measured, not assumed.
  // Visible bottom edge of the top bar (0 once it has scrolled away), so a pop-out never
  // leaves a gap where the bar used to be.
  function topbarH() { const t = document.querySelector('.v2-topbar'); return t ? Math.max(0, Math.round(t.getBoundingClientRect().bottom)) : 0; }
  function syncTopbarH() { document.documentElement.style.setProperty('--topbar-h', topbarH() + 'px'); }
  let _tbRaf = 0;
  window.addEventListener('scroll', () => { if (!_tbRaf) _tbRaf = requestAnimationFrame(() => { _tbRaf = 0; syncTopbarH(); }); }, { passive: true });
  // Pop-outs slide for 0.22 s; re-place once they have settled.
  function placeChartSoon() { clearTimeout(_placeTimer); placeChart(); _placeTimer = setTimeout(placeChart, 260); }

  // ── Grid + layout persistence ───────────────────────────────────────────────
  let grid = null;
  let saveTimer = null;
  let saveArmed = false;

  // T1.1 — mobile collapse contract. 768px matches the CSS breakpoint exactly:
  // GridStack's breakpoint test is `width <= bp.w`, same as @media (max-width:768px).
  const MOBILE_MAX_W = 768;
  const MOBILE_MQ = window.matchMedia('(max-width: ' + MOBILE_MAX_W + 'px)');

  // Explicit phone stack order. GridStack's layout:'list' sorts by SAVED y/x, not
  // DOM order, so without this map the phone order would be dictated by whatever
  // desktop arrangement happens to be persisted. All 11 tiles are listed — no tile
  // is silently dropped from the mobile deck (Ruling 6).
  const MOBILE_ORDER = [
    // R-IV.1186(b): PHONE-FIRST means second, not last. An unlisted tile sorts AFTER the
    // known set (see applyMobileOrder), so leaving `regime-strategy` out would bury the one
    // card Nick is being asked to look at.
    'regime-band', 'regime-strategy', 'movers-tape', 'kairos', 'book', 'river',
    // A1 (R-IV.1209(c)): LISTED, because an unlisted tile sorts AFTER the known set -- so
    // leaving these out would bury the four new boards below every legacy tile on a phone,
    // which is the same trap `regime-strategy` was in.
    'event-strip', 'fear', 'crowd',
    'themes', 'divergence', 'breadth', 'index', 'curve', 'usd',
  ];

  function isCollapsed() {
    if (MOBILE_MQ.matches) return true;
    return !!grid && grid.getColumn() === 1;
  }

  const tileEls = () => Array.from(document.querySelectorAll('#v2Grid > .grid-stack-item[gs-id]'));

  // T1.2(a) — setStatic is the SINGLE interaction mechanism on mobile. Do not pair it
  // with enableMove()/enableResize(): those are unconditional no-ops once staticGrid is
  // truthy, so a belt-and-braces call silently does nothing. Static also removes the
  // touch-resize handles, which GridStack arms by default on any touch device
  // (alwaysShowResizeHandle:'mobile' resolves to true) — 5 handles × 11 tiles, each a
  // 3px drag away from a write.
  function syncStaticMode() {
    if (!grid) return;
    const collapsed = isCollapsed();
    grid.setStatic(collapsed);
    document.body.classList.toggle('is-mobile-grid', collapsed);
    if (collapsed) $('layoutStatus').textContent = 'mobile · layout locked';
  }

  // T1.1 — impose MOBILE_ORDER on the collapsed stack.
  //
  // Applied as inline CSS `order`, NOT by mutating GridStack's engine. T1.3 takes the
  // mobile stack out of GridStack's absolute positioning so tiles can size to their
  // content (the alternative is desktop-height tiles at phone width, i.e. a ~2,900px
  // stack of nested scrollers). Once the stack is in normal flex flow, engine y is
  // visually inert and CSS order is what actually decides sequence.
  //
  // The safety win is the point: this writes nothing through to GridStack's cached
  // desktop layout, so the layoutsNodesChange corruption path cannot fire on mobile
  // even in principle. MOBILE_ORDER stays the single source of truth for sequence.
  function applyMobileOrder() {
    const collapsed = isCollapsed();
    tileEls().forEach((el) => {
      if (!collapsed) { el.style.order = ''; return; }
      const i = MOBILE_ORDER.indexOf(el.getAttribute('gs-id'));
      // Unlisted tiles sort after the known set rather than jumping to the top.
      el.style.order = String(i === -1 ? MOBILE_ORDER.length : i);
    });
  }

  // T1.7 — tiles present in the markup but absent from the saved row must stay
  // visible. load() is called with addRemove=false (below), so they survive; this
  // parks them below the restored stack instead of leaving them overlapping.
  function reconcileMissingTiles(saved) {
    const savedIds = new Set((saved || []).map((n) => n && n.id).filter(Boolean));
    const missing = tileEls().filter((el) => !savedIds.has(el.getAttribute('gs-id')));
    if (!missing.length) return 0;
    let maxY = 0;
    tileEls().forEach((el) => {
      if (missing.indexOf(el) !== -1) return;
      const n = el.gridstackNode; if (!n) return;
      maxY = Math.max(maxY, (n.y || 0) + (n.h || 1));
    });
    grid.batchUpdate();
    missing.forEach((el) => {
      const h = (el.gridstackNode && el.gridstackNode.h) || 1;
      grid.update(el, { x: 0, y: maxY });
      maxY += h;
    });
    grid.batchUpdate(false);
    return missing.length;
  }

  // ── Regime Strategy card (R-IV.1186 v0, redesigned R-IV.1190 v0.1) ────────────────────
  //
  // MOCK ONLY. Two static files under /assets/regime/ and nothing else: no hub route, no
  // regime table, no kill-switch write. The kill-switch line is a DISPLAY of a value the
  // fixture carries (R-IV.1186(c)).
  //
  // Lens 2 is never the headline (§1, §5). In v0.1 the whole face of the card is visuals and
  // the lens reading is one labelled row; the base regime is the only headline.
  // `_rsLive`, renamed from `_rsMock` in B1 (R-IV.1209(e)). It has held the LIVE
  // /api/stable/regime-strategy payload since R-IV.1203 wired the designated close
  // source, and a variable called `Mock` holding live data is the caption-lies-about-
  // its-field fault in a place a reader trusts without checking.
  let _rsLive = null, _rsPlaybooks = null, _rsOpen = false;

  // R-IV.1190(b)2: the BEAR -> BULL order of the ten registered labels. A FIXED presentation
  // order, not per-reading data -- in v1 it must not vary with the reading, which is why it is
  // a constant here and not a fixture field.
  const RS_SLIDER = ['crash_liquidation', 'bear_market', 'bear_market_rally', 'breakdown',
    'correction', 'range_chop', 'recovery', 'narrow_uptrend', 'uptrend', 'melt_up'];
  // R-IV.1190(c). The regime's own colour; the alarm override is applied over it below.
  const RS_LIME = ['uptrend', 'melt_up', 'recovery'];
  const RS_VERMILION = ['breakdown', 'bear_market', 'bear_market_rally', 'crash_liquidation'];

  async function loadRegimeStrategy() {
    const host = $('regimeStrategy');
    if (!host) return;
    try {
      const [m, p] = await Promise.all([
        // R-IV.1195(b): LIVE. The v1 classifier's stored label for the settled close, not the
        // fixture. NO FALLBACK TO THE MOCK, deliberately: plausible numbers on a card that
        // looks healthy is the /api/crypto/market fault, where a sibling symbol's price was
        // served as binance_spot for weeks because the fallback was invisible.
        fetch('/api/stable/regime-strategy', { cache: 'no-store' }).then((r) => r.json()),
        // R-IV.1189(b): v2. The version is in the URL, so a reader of the card's "playbook vN"
        // line and a reader of the network tab see the same number.
        fetch('/assets/regime/playbooks.v2.json', { cache: 'no-store' }).then((r) => r.json()),
      ]);
      // R-IV.1309(b): the preview flag. `rs21MockState` is a no-op unless ?state= names
      // one of board 13s states, so the live path is byte-identical without the flag.
      rs21InjectCss();
      await rcLoad();          // R-IV.1318(c): no-op unless ?report=1
      _rsLive = await rs21MockState(m); _rsPlaybooks = p;
    } catch (e) {
      // Says what is missing. A card that renders an empty shell reads as "no regime", which
      // is a claim; "the read failed" is the fact.
      host.innerHTML = '<div class="rs-wait">the regime read failed \u2014 '
        + esc(String(e && e.message || e)) + '</div>';
      return;
    }
    if (_rsLive && _rsLive.available === false) {
      // The server said so itself, with a reason. Printing the reason beats an empty card:
      // "cannot confirm" plus why is a fact, an unpopulated card is an invitation to guess.
      host.innerHTML = '<div class="rs-wait">cannot confirm \u2014 '
        + esc(String(_rsLive.unavailable_reason || 'no label stored')) + '</div>';
      const stx = $('rsSettled');
      if (stx) stx.textContent = 'no settled label \u00b7 display only';
      const dotx = $('rsHealth');
      if (dotx) {
        dotx.className = 'health-dot unconfirmed';
        dotx.title = String(_rsLive.unavailable_reason || '');
      }
      return;
    }
    renderRegimeStrategy();
  }

  // The gauge scale, stated rather than left as a magic number: the three levels are spread
  // across the track with 6% of their own span as padding at each end, so the marker never
  // sits on the rail and the relative order is always legible.
  function rsScale(vals) {
    const lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    const pad = (hi - lo) * 0.06 || 1;
    const a = lo - pad, b = hi + pad;
    return (x) => Math.max(0, Math.min(100, (x - a) / (b - a) * 100));
  }

  const rsPct = (px, ma) => (px - ma) / ma * 100;
  const rsFmtPct = (v) => (v >= 0 ? '+' : '\u2212') + Math.abs(v).toFixed(1) + '%';

  // R-IV.1190(c): THE ALARM IS CHECKED FIRST. A Correction with the kill-switch active must
  // pulse vermilion rather than sit grey, and the override beating the regime colour is only
  // true if it is tested before it.
  function rsOutlineClass(m) {
    const killed = ((m.intraday || {}).kill_switch || '').toUpperCase() === 'ACTIVE';
    const anyActive = (m.overlays || []).some(
      (o) => String(o.state || '').toUpperCase() === 'ACTIVE');
    if (killed || anyActive) return 'rs-o-bear';
    if (RS_VERMILION.indexOf(m.regime_key) !== -1) return 'rs-o-bear';
    if (RS_LIME.indexOf(m.regime_key) !== -1) return 'rs-o-bull';
    return 'rs-o-mixed';
  }

  function renderRegimeStrategy() {
    const m = _rsLive, host = $('regimeStrategy');
    if (!host || !m) return;

    // header bits live outside the body, so they are written straight into their slots
    const tile = host.closest('.tile');
    if (tile) {
      tile.classList.remove('rs-o-bear', 'rs-o-bull', 'rs-o-mixed');
      tile.classList.add(rsOutlineClass(m));
    }
    const kill = $('rsKill');
    if (kill) {
      const on = ((m.intraday || {}).kill_switch || '').toUpperCase() === 'ACTIVE';
      // R-IV.1190(b)1: the tag shows ONLY while the switch is active. A permanent KILL chip
      // would be an alarm that is always on, which is an alarm nobody reads.
      kill.hidden = !on;
      kill.title = on ? ('kill-switch ACTIVE'
        + ((m.intraday || {}).trigger ? ' (' + (m.intraday || {}).trigger + ')' : '')
        + ' \u2014 shown, not touched by this card') : '';
    }
    const st = $('rsSettled');
    if (st) {
      // R-IV.1198(d): the settled line NAMES ITS CLOSE SOURCE until the designated one is
      // wired. Three candidates disagreed on 2026-10-16 and only one matched the Polygon
      // aggregate, so an unnamed close is the one a reader assumes is right. The tooltip
      // carries the rest; "display only" stays on the face (R-IV.1193(b)).
      st.textContent = 'settled ' + (m.settled_close || '\u2014')
        + (m.close_source ? ' \u00b7 ' + m.close_source : '')
        + ' \u00b7 display only';
      st.title = m.close_source_note || '';
    }
    const dot = $('rsHealth');
    if (dot) {
      dot.className = 'health-dot ' + (String(m.health || '').toLowerCase() === 'ok'
        ? 'ok' : 'unconfirmed');
      dot.title = (m.health || '') + (m.health_reason ? ' \u2014 ' + m.health_reason : '');
    }

    // ── regime call + the BEAR -> BULL slider ───────────────────────────────
    const at = RS_SLIDER.indexOf(m.regime_key);
    const ticks = RS_SLIDER.map((k, i) => '<i style="left:' + (i * 10 + 5) + '%"'
      + ' title="' + esc(((_rsPlaybooks.regimes || {})[k] || {}).label || k) + '"></i>').join('');
    const marker = at === -1 ? ''
      : '<b style="left:' + (at * 10 + 5) + '%" title="'
        + esc(m.regime_label || '') + '"></b>';
    const tw = m.tripwires || {};

    // ── index strip ─────────────────────────────────────────────────────────
    const strip = (m.per_index || []).map((ix) => {
      const pos = rsScale([ix.price, ix.ma50, ix.ma200]);
      const below = ix.price < ix.ma50;
      const cls = /DOWN|BEAR|BREAK/.test(String(ix.state).toUpperCase()) ? 'st-fad'
        : /RANGE|CORRECT/.test(String(ix.state).toUpperCase()) ? '' : 'st-dom';
      return '<div class="rs-ix">'
        + '<div class="rs-ix-top"><span class="rs-ix-t">' + esc(ix.ticker) + '</span>'
        +   '<span class="status-chip ' + cls + '">' + esc(ix.state)
        +   (ix.uncertain ? '<i class="rs-q" title="' + esc(ix.uncertain_why || '') + '">?</i>'
             : '') + '</span></div>'
        + '<div class="vc-gauge rs-g">'
        +   '<i style="left:' + pos(ix.ma200).toFixed(1) + '%" title="200d '
        +     esc(String(ix.ma200)) + '"></i>'
        +   '<i class="rs-t50" style="left:' + pos(ix.ma50).toFixed(1) + '%" title="50d '
        +     esc(String(ix.ma50)) + '"></i>'
        +   '<b class="' + (below ? 'rs-below' : 'rs-above') + '" style="left:'
        +     pos(ix.price).toFixed(1) + '%" title="' + esc(String(ix.price)) + '"></b>'
        + '</div>'
        + '<div class="rs-ix-foot"><span>200d ' + rsFmtPct(rsPct(ix.price, ix.ma200))
        +   '</span><span>50d ' + rsFmtPct(rsPct(ix.price, ix.ma50)) + '</span></div>'
        + '</div>';
    }).join('');

    // ── evidence: five dots and the overlay chips ───────────────────────────
    const fams = ((m.evidence || {}).families || []).map((f) => {
      const s2 = f.state === null || f.state === undefined ? 'nodata' : String(f.state);
      return '<span class="rs-fam" title="' + esc(f.why || (f.key + ': ' + s2)) + '">'
        + '<span class="rs-dot rs-' + esc(s2) + '"></span>' + esc(f.key) + '</span>';
    }).join('');
    const ovs = (m.overlays || []).map((o) => {
      const s2 = String(o.state || 'CLEAR').toUpperCase();
      const k = s2 === 'WATCH' ? 'emg' : s2 === 'ACTIVE' ? 'fad'
        : s2 === 'CANDIDATE' ? 'rs-cand' : 'rs-clear';
      return '<span class="chip ' + k + '" title="' + esc(o.short + ' ' + s2
        + (o.detail ? ' \u2014 ' + o.detail : '')) + '">' + esc(o.short) + '</span>';
    }).join('');

    // The server names which blocks have no feed in v1, so the card prints its reason instead
    // of an em-dash a reader has to interpret. One author for the caption and the gap.
    const noFeed = (k) => String((m.no_feed_in_v1 || {})[k] || 'no feed in v1');

    // ── since yesterday (R-IV.1195(b)) ──────────────────────────────────────
    // "Yesterday" is the previous STORED session, never as_of minus a day: a calendar day
    // before a Monday is a Sunday, which carries no label, so a diff against a date that does
    // not exist would report every Monday as a change. The server decides that; this only
    // prints it. Built as a variable rather than inline, because the first inline version was
    // a nested ternary inside a string concatenation and did not parse.
    let diffRow = '';
    if (m.diff) {
      const d = m.diff;
      const title = d.previous_as_of
        ? ('vs the previous stored session ' + d.previous_as_of)
        : 'no previous session stored';
      let text;
      if (d.changed === null || d.changed === undefined) {
        // NOT "no change". The first stored session has nothing to differ from, and saying
        // "no change" there is a claim about a comparison nobody made.
        text = 'first stored session · nothing to compare';
      } else {
        text = (d.changed ? 'Δ ' : 'since yesterday: ') + String(d.detail || '');
      }
      diffRow = '<div class="rs-diff" title="' + esc(title) + '">' + esc(text) + '</div>';
    }

    // ── the three lights ────────────────────────────────────────────────────
    const L = m.lights || {};
    const light = (key, label, cls) => {
      const l = L[key] || {};
      // An em-dash with an empty tooltip tells a reader nothing about WHY it is empty.
      return '<div class="rs-light"><span class="rs-lk">' + esc(label) + '</span>'
        + '<span class="rs-lv ' + (cls || '') + '" title="'
        + esc(l.basis || (l.value ? '' : noFeed('lights'))) + '">'
        + esc(l.value || '\u2014') + '</span></div>';
    };
    const prem = L.premium || {};
    const segs = Number(prem.bands || 3);
    // THE MARKER IS OMITTED WHEN THERE IS NO READING. `position_pct || 0` placed it at 0% --
    // hard against the bear end of the track -- which renders as a confident extreme reading
    // taken from nothing. An absent marker reads as absent, which is the truth. (R-IV.1195(b);
    // the v1 payload has no discipline feed, so this is the live path, not an edge case.)
    const hasPrem = prem.position_pct !== null && prem.position_pct !== undefined;
    const premGauge = '<div class="vc-gauge rs-prem"'
      + (hasPrem ? '' : ' title="' + esc(noFeed('lights')) + '"') + '>'
      + Array.from({ length: Math.max(0, segs - 1) }, (_, i) =>
          '<i style="left:' + ((i + 1) * (100 / segs)).toFixed(1) + '%"></i>').join('')
      + (hasPrem ? '<b style="left:' + Number(prem.position_pct).toFixed(1) + '%"></b>' : '')
      + '</div>';

    // R-IV.1309(b)2: state C dims the whole card, so it is applied to the HOST before
    // the body is written rather than to any one row.
    rs21Dim(host, m);
    // R-IV.1318(c): the report card is APPENDED to the card body, so it shares the tile
    // rather than needing new HTML -- and renders nothing at all without ?report=1.
    // THE SAME RENDERER DRAWS BOTH. A fixture rendered through its own path would approve a
    // layout the live read cannot produce, which is the one thing mock-first exists to stop.
    const rcHtml = rcRender(REPORT_MOCK ? _rcMock : (m && m.regime_report_card));
    host.innerHTML =
      '<div class="rs-call">'
      // The headline, the state chip and the two quiet lines are each decided in one
      // place (rsHeadline / rsStateChips / rsSubLines) rather than inline here: the
      // choice between the two stalenesses is the whole point, and three callers would
      // eventually disagree about it.
      +   rsHeadline(m)
      +   (m.tags || []).map((t) =>
            '<span class="chip rs-tag">' + esc(t) + '</span>').join('')
      +   rsStateChips(m)
      +   rs21DataChip(m)
      +   rsSubLines(m)
      +   rs21Decay(m)
      +   rs21Ma200(m)
      +   rs21Cost(m)
      + '</div>'
      + '<div class="vc-gauge rs-slider">' + ticks + marker + '</div>'
      + '<div class="rs-tw">'
      +   '<span class="rs-tw-bear" title="'
      +     esc((tw.bear || {}).basis || ((tw.bear || {}).text ? '' : noFeed('tripwires')))
      +     '">\u25c2 ' + esc((tw.bear || {}).text || '') + '</span>'
      +   '<span class="rs-tw-mid">BEAR \u00b7 \u00b7 \u00b7 BULL</span>'
      +   '<span class="rs-tw-bull" title="'
      +     esc((tw.bull || {}).basis || ((tw.bull || {}).text ? '' : noFeed('tripwires')))
      +     '">' + esc((tw.bull || {}).text || '') + ' \u25b8</span>'
      + '</div>'
      + diffRow
      + '<div class="rs-strip">' + strip + '</div>'
      + '<div class="rs-grid">'
      +   '<div class="rs-box rs-ev"><div class="rs-fams">' + fams + '</div>'
      +     '<div class="rs-ovs">' + ovs + '</div></div>'
      +   '<div class="rs-box rs-lights">'
      +     light('shorts', 'Shorts', 'rs-teal')
      +     light('longs', 'Longs', '')
      +     '<div class="rs-light rs-premrow"><span class="rs-lk">Premium</span>'
      +       premGauge
      +       '<span class="rs-lv" title="' + esc(prem.basis || '') + '">'
      +       esc(prem.value || '\u2014') + '</span></div>'
      +   '</div>'
      + '</div>'
      + '<div class="rs-lensrow" title="' + esc((m.lens_split || {}).headline_rule || '') + '">'
      +   '\u21c4 <span class="rs-lenslabel">Watchlist (high-beta) alarm</span> <b>'
      +   esc((m.lens_split || {}).watchlist_alarm || '\u2014') + '</b>'
      +   '<span class="rs-vs">vs macro</span> <b>'
      +   esc((m.lens_split || {}).macro || '\u2014') + '</b></div>'
    host.innerHTML += rcHtml;
  }

  // "Open" expands the CURRENT regime's playbook. Read-only: the texts come from the
  // versioned file and nothing on this page can edit them (R-IV.1186(b)). R-IV.1190(b)6: this
  // is where ALL the prose lives, so the face of the card carries none.
  function renderRegimePlaybook() {
    const box = $('rsPlaybook');
    if (!box || !_rsLive || !_rsPlaybooks) return;
    const r = (_rsPlaybooks.regimes || {})[_rsLive.regime_key];
    if (!r) { box.innerHTML = '<div class="rs-wait">no playbook for '
      + esc(_rsLive.regime_key || '?') + '</div>'; return; }
    box.innerHTML =
      '<div class="rs-pb-title">' + esc(r.label) + ' \u00b7 playbook '
      +   esc(_rsPlaybooks.version) + '</div>'
      + '<div class="rs-h">WHAT MATTERS NOW</div><ul class="rs-list">'
      +   (r.matters_now || []).map((x) => '<li>' + esc(x) + '</li>').join('') + '</ul>'
      + '<div class="rs-h">TAPE USUALLY REWARDS / PUNISHES</div>'
      + '<div class="rs-row">' + esc(r.tape || '') + '</div>'
      + '<div class="rs-h">PREMIUM POSTURE</div>'
      + '<div class="rs-row">' + esc(r.premium || '') + '</div>'
      + (r.held_sentences
          ? '<div class="rs-held">' + esc(String(r.held_sentences))
            + ' line(s) withheld: ' + esc(r.held_reason || '') + '</div>'
          : '')
      + '<div class="rs-h">ENDING SIGNS</div>'
      + '<div class="rs-row">' + esc(r.ending_signs || '') + '</div>'
      + '<div class="rs-h">WHAT WOULD PROVE THIS WRONG</div>'
      + '<div class="rs-row">' + esc(r.proves_wrong || '') + '</div>'
      // R-IV.1303(b): NO LINE MEANS NO BLOCK. This rendered the heading unconditionally and
      // the payload has never carried `costs`, so the live card has been showing
      // "COSTS, STATED" over an empty list -- which reads as a read that failed, not as
      // "there is no stated cost yet". The cost line now comes from the display config
      // (never the stamped rules file) and is empty until QUERY supplies v2.1's under
      // R-IV.1301(c), so the honest render is nothing at all.
      + ((_rsLive.costs || []).length
          ? '<div class="rs-h">COSTS, STATED</div><ul class="rs-list">'
            + (_rsLive.costs || []).map((c) => '<li>' + esc(c) + '</li>').join('') + '</ul>'
          : '')
      + '<div class="rs-foot">Excluded: '
      +   esc((_rsLive.excluded_inputs || []).join(', '))
      +   ' \u00b7 News watch: ' + esc(_rsLive.news_watch || '\u2014')
      +   ' \u00b7 ' + esc(_rsPlaybooks.not_a_signal || '') + '</div>';
  }

  function toggleRegimePlaybook() {
    const box = $('rsPlaybook'), btn = $('rsOpen');
    if (!box || !btn) return;
    _rsOpen = !_rsOpen;
    if (_rsOpen) renderRegimePlaybook();
    box.hidden = !_rsOpen;
    btn.setAttribute('aria-expanded', String(_rsOpen));
    btn.innerHTML = _rsOpen ? 'Close \u25be' : 'Open \u25b8';
  }

  // ===========================================================================
  // AGORA ADDITIONS, PHASE A1 (R-IV.1209(c)) \u2014 the four boards, as MOCK tiles.
  //
  // EVERY VALUE IN THESE FIXTURES IS FAKE (R-IV.1209(b)), and the MOCK chip is the
  // only honest thing on each tile until Phase B wires it. The chip is driven by the
  // FIXTURE'S OWN `_mock` flag rather than hard-coded in the markup: when B replaces a
  // fixture with a live read, the flag goes and the chip goes with it. A chip that had to
  // be removed by hand is a chip that outlives its truth.
  //
  // DISPLAY ONLY (#42). Nothing here gates, grades or feeds Kairos.
  // ===========================================================================

  const AGORA_FIXTURES = {
    bookStress: '/assets/agora/book_stress_mock.json',
  };
  // B4: the Event Strip is LIVE and no longer reads a fixture. The other three tiles are
  // still mocks and still say so through their own `_mock` flag — which is why the chip is
  // driven by the payload rather than the markup: these four tiles go live one at a time, and
  // a chip hard-coded per tile would be wrong for four different weeks.
  const AGORA_LIVE = {
    eventStrip: '/api/event-strip',   // B4
    fear: '/api/fear-price',          // B5
    crowd: '/api/crowd',              // B6 — all three rows live since R-IV.1318(b)
  };
  const _agora = { crowd: null, fear: null, bookStress: null, eventStrip: null };

  // The lean -> colour scale of R-IV.1209(d)2, as CSS custom-property expressions so the
  // mixes live in one place and follow the theme. Not hexes (R-IV.1190(b)).
  const LEAN_COLOR = {
    'strong-bear': 'var(--down)',
    'bear': 'color-mix(in srgb, var(--down) 60%, var(--text-2))',
    'neutral': 'var(--text-2)',
    'notable': 'var(--teal)',
    'bull': 'color-mix(in srgb, var(--up) 55%, var(--text-2))',
    'strong-bull': 'var(--up)',
  };

  // ── The regime card's headline, and the three quiet lines under it ──────────
  //
  // TWO STALENESSES, AND THEY ARE NOT THE SAME FACT. Deciding between them in one place, once,
  // because the decision is the whole point and three callers would eventually disagree:
  //
  //   data_freshness.headline  the BARS stopped arriving (R-IV.1278(b)4) -> "DATA STALE - ..."
  //   held_no_match.stale      the bars arrived and NO RULE MATCHED (registration s1 / R-IV.1277(b)) -> "STALE"
  //
  // The bar case wins when both hold: if the data stopped, "no rule matched" is a consequence
  // of having nothing to match against, and naming the consequence would send a reader looking
  // at section 2 instead of at the feed.
  //
  // AND A BLOCKED CANDIDATE IS NEITHER. When hysteresis holds a label that DOES match, the
  // card shows the normal label plus the blocked chip -- the mechanism working as designed is
  // not an alarm. `held_no_match.stale` is false in that case by construction, because the raw
  // label is not null.
  //
  // R-IV.1278(b)4's standing instruction, kept with the code that honours it, and kept ON ONE
  // LINE so it is greppable: "Never a silent old label."
  //
  // In either stale case the headline REPLACES the label rather than sitting beside it --
  // beside it, a reader takes the label as current, which is exactly what happened on
  // 2026-10-19 and 10-20. The last label stays reachable on hover, as a true fact about the
  // last session that WAS labelled rather than a reading to act on now.
  // R-IV.1309(b): the ?card=v21 PREVIEW. Two display-only additions behind one flag, so the
  // live card is untouched until Nick approves design board 13.
  //
  //   ?card=v21            the live payload, with the preview rows
  //   ?card=v21&state=A|B|C  board 13s three states from the fixture (mock-first)
  //
  // THE SAME RENDERER DRAWS BOTH. A preview that rendered the fixture through its own code
  // path would approve a layout the live read cannot produce -- which is the one thing
  // mock-first is for. The fixture carries the LIVE payload field names and
  // backend/services/regime_card_v21.py lints that from the suite.
  // R-IV.1354(a): SHIPPED AS THE DEFAULT. Was `=== 'v21'`, default FALSE. The pre-v2.1 card
  // stays reachable at `?card=v1` for ONE WEEK -- REMOVE THE ROLLBACK ON OR AFTER 2026-10-30.
  //
  // `?card=v21` KEEPS WORKING and is not a second spelling of the default: `?state=` is only
  // honoured when the flag resolves true, and every screenshot, relay and lane file written
  // during the preview cites `?card=v21`. A link in a ruling that silently stopped working
  // would be worse than a redundant parameter.
  const CARD_V21 = (() => {
    try { return new URLSearchParams(location.search).get('card') !== 'v1'; }
    catch (_) { return true; }
  })();
  const CARD_STATE = (() => {
    try {
      const s = new URLSearchParams(location.search).get('state');
      return (CARD_V21 && ['A', 'B', 'C'].indexOf(s) >= 0) ? s : null;
    } catch (_) { return null; }
  })();

  // INJECTED, not added to v2.css: that stylesheet is pinned INDEPENDENTLY by v2.html,
  // stater.html and abacus.html and the three values have already diverged, so a rule added
  // there ships three times or reaches a stale cache on the pages that were missed.
  const RS21_CSS = [
    '.rs-ma200{display:block;flex:0 0 100%;font-size:11px;letter-spacing:.3px;margin-top:6px}',
    '.rs-ma200 b{font-weight:600}',
    '.rs-ma200.above b{color:var(--up)}',
    '.rs-ma200.below b{color:var(--down)}',
    '.rs-ma200-note{display:block;flex:0 0 100%;font-size:9.5px;color:var(--text-3);margin-top:2px;line-height:1.35}',
    '.rs-cost21{margin-top:5px;border-top:1px solid var(--border);padding-top:4px}',
    '.rs-decay{display:flex;flex:0 0 100%;align-items:center;gap:4px;margin-top:6px;font-size:9.5px;color:var(--text-3)}',
    '.rs-decay i{width:12px;height:4px;border-radius:2px;background:var(--border);display:inline-block}',
    '.rs-decay i.on{background:var(--amber)}',
    '.rs-decay span{margin-left:4px;letter-spacing:.4px}',
    '.rs-dim{opacity:.55;filter:saturate(.6)}',
    '.rs-datachip{font-size:9px;letter-spacing:1.2px;color:var(--amber);border:1px solid var(--amber);border-radius:999px;padding:2px 6px;margin-left:6px}',
    '.rs-21mock{font-size:9px;letter-spacing:1.2px;color:var(--amber);border:1px solid var(--amber);border-radius:999px;padding:2px 6px;margin-left:6px}',
  ].join('');

  function rs21InjectCss() {
    if (!CARD_V21 || document.getElementById('rs21-css')) return;
    const s = document.createElement('style');
    s.id = 'rs21-css';
    s.textContent = RS21_CSS;
    document.head.appendChild(s);
  }

  // R-IV.1309(b)3. DISPLAY ONLY (#42): it returns a string and nothing reads it back.
  function rs21Ma200(m) {
    if (!CARD_V21) return '';
    const row = m.ma200_row || {};
    if (!row.available) {
      return '<span class="rs-ma200" title="' + esc(row.reason || 'not available')
        + '">SPY vs 200-day: <b>—</b></span>';
    }
    const cls = String(row.side) === 'ABOVE' ? 'above' : 'below';
    // THE TEXT COMES FROM THE PAYLOAD, built in models/regime_ma200.py, so the words and the
    // numbers cannot drift apart between the two renderers that show them.
    const txt = row.text || ('SPY vs 200-day: ' + row.side + ' since ' + (row.since || '?'));
    return '<span class="rs-ma200 ' + cls + '" title="' + esc(String(row.basis || ''))
      + '"><b>' + esc(txt) + '</b></span>'
      + (row.caveat ? '<span class="rs-ma200-note">' + esc(row.caveat) + '</span>' : '');
  }

  // R-IV.1309(b)2: the header chip for state C. The HEADLINE already replaces the label with
  // "DATA STALE ..." (R-IV.1278(b)4); board 13 adds the chip and the dim, so the whole card
  // reads as not-current rather than only its first line.
  function rs21DataChip(m) {
    if (!CARD_V21) return '';
    const f = m.data_freshness || {};
    if (!f.stale && !f.headline) return '';
    const txt = f.chip || f.headline || 'DATA STALE';
    return '<span class="rs-datachip" title="' + esc(f.reason || '') + '">'
      + esc(txt) + '</span>';
  }

  // The dim is on the HOST, not on a row: state C is a statement about everything on the card.
  function rs21Dim(host, m) {
    if (!host) return;
    const stale = !!((m.data_freshness || {}).stale || (m.data_freshness || {}).headline);
    host.classList.toggle('rs-dim', !!(CARD_V21 && stale));
  }

  // Mock-first (R-IV.1309(b)): one of board 13s three states, from the linted fixture. Merged
  // OVER a real payload so every field the preview does not exercise still comes from the live
  // read -- a fixture that replaced the whole payload would approve a layout against absences
  // the live card never has.
  async function rs21MockState(live) {
    if (!CARD_STATE) return live;
    try {
      const r = await fetch('/assets/regime/card_v21_mock.v1.json', { cache: 'no-store' });
      const f = await r.json();
      const st = ((f || {}).states || {})[CARD_STATE];
      if (!st) return live;
      return Object.assign({}, live || {}, st, { _cardMock: CARD_STATE });
    } catch (_) {
      return live;
    }
  }
  // R-IV.1309(b)4: the cost line ON THE CARD FACE.
  //
  // It already had a home -- the DETAILS drawer's "COSTS, STATED" list -- but that drawer is
  // closed by default, so a cost line that lives only there is a cost line almost nobody reads.
  // Board 13 lists it as item 4 of the CARD preview, beside the 200-day row, so it renders
  // here too. The drawer's own block is untouched; both read the same `costs` field, which
  // since R-IV.1303(b) comes from the display config and never from the stamped rules file.
  //
  // EMPTY MEANS NOTHING RENDERED, as everywhere else on this card: a heading over an empty
  // list reads as a read that failed. On main `cost_lines` is empty until the cutover branch
  // merges, so this is blank today and that is correct.
  function rs21Cost(m) {
    if (!CARD_V21) return '';
    const cs = (m.costs || []).filter(Boolean);
    if (!cs.length) return '';
    return cs.map((c) => '<span class="rs-ma200-note rs-cost21" title="'
      + esc('the stated cost of this classifier, as graded') + '">' + esc(c)
      + '</span>').join('');
  }
  // R-IV.1309(b)1: the 10-step decay bar under a STALE headline.
  function rs21Decay(m) {
    if (!CARD_V21) return '';
    const d = ((m.held_no_match || {}).decay) || {};
    const steps = Number(d.steps || 0);
    if (!steps) return '';
    const on = Math.max(0, Math.min(steps, Number(d.elapsed || 0)));
    let bar = '';
    for (let i = 0; i < steps; i++) bar += '<i class="' + (i < on ? 'on' : '') + '"></i>';
    return '<span class="rs-decay" title="'
      + esc('the held label gives way after ' + steps + ' sessions with no match')
      + '">' + bar + '<span>' + esc(d.text || '') + '</span></span>';
  }
  // R-IV.1318(c): the REGIME REPORT CARD skeleton, behind ?report=1. MOCK VALUES ONLY.
  //
  // QUERY is writing the scoring spec (R-IV.1316) and the wiring waits for it. The skeleton
  // ships first because a report card is the most trustable-looking surface on this hub -- a
  // plausible number on it gets believed immediately and questioned late, which is backwards
  // for a figure whose definition nobody has agreed yet. So the shape is reviewable now and
  // every value is visibly fake.
  //
  // Built from C:	emp\cc-query-handoff\AGORA-MOCK-RegimeReport.dc.html, sha256 ffd15cc3...,
  // verified byte-identical before anything was written.
  // ?report=1    the LIVE card, which is the EMPTY state until the v2.1 cutover deploys
  // ?report=mock the fixture, to review the populated layout before it can exist
  const REPORT_PARAM = (() => {
    try { return new URLSearchParams(location.search).get('report'); }
    catch (_) { return null; }
  })();
  // R-IV.1392(a) / R-IV.1354(a): THE REPORT CARD IS THE DEFAULT NOW. QUERY's checker
  // PASSED on the live payload (989f19f4 against spec 81a47dc1, 0 findings).
  //
  // `?report=off` restores the hidden state; `?report=mock` still renders the fixture,
  // which is how the populated layout was reviewed before one could exist and is the
  // only way to see it while the live card is empty.
  //
  // THE QUALIFICATION THAT TRAVELS WITH IT: the live card is E1 (`available: false`), so
  // no P11 scope clause has fired yet. The rule is proved against QUERY's controls, not
  // against a card that has actually scored a session. QUERY re-checks the first card
  // serving `available: true`.
  const REPORT_ON = REPORT_PARAM !== 'off';
  const REPORT_MOCK = REPORT_PARAM === 'mock';

  const RC_CSS = [
    '.rc-wrap{margin-top:14px;border-top:1px solid var(--border);padding-top:12px}',
    '.rc-h{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}',
    '.rc-h b{font-size:12px;letter-spacing:1.4px}',
    '.rc-h i{font-style:normal;font-size:9.5px;color:var(--text-3)}',
    '.rc-badge{font-size:9px;letter-spacing:1.1px;border-radius:999px;padding:2px 7px;border:1px solid var(--amber);color:var(--amber)}',
    '.rc-mock{font-size:9px;letter-spacing:1.2px;color:var(--amber);border:1px solid var(--amber);border-radius:999px;padding:2px 6px}',
    '.rc-panels{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:8px;margin-top:10px}',
    '.rc-p{border:1px solid var(--border);border-radius:6px;padding:7px 9px;position:relative}',
    '.rc-p>u{display:block;text-decoration:none;font-size:8.5px;letter-spacing:.9px;color:var(--text-3)}',
    '.rc-pb{margin-top:3px}',
    '.rc-pb b{font-size:18px;line-height:1.25}',
    '.rc-pb s{display:block;text-decoration:none;font-size:8.5px;color:var(--text-3);margin-top:1px}',
    '.rc-pb em,.rc-p>em{display:block;font-style:normal;font-size:8.5px;color:var(--text-3);margin-top:3px;line-height:1.35}',
    '.rc-na{color:var(--text-3)}',
    '.rc-v{display:inline-block;font-size:8px;letter-spacing:.7px;border-radius:999px;padding:1px 6px;margin-top:3px;border:1px solid currentColor}',
    '.rc-early{color:var(--amber)}',
    '.rc-nr{color:var(--text-3)}',
    '.rc-ok{color:var(--up)}',
    '.rc-dep{color:var(--down)}',
    '.rc-tt{margin-top:12px;font-size:9.5px;letter-spacing:.8px}',
    '.rc-tt i{font-style:normal;color:var(--text-3);letter-spacing:.3px}',
    '.rc-tbl{width:100%;border-collapse:collapse;margin-top:5px;font-size:9px}',
    '.rc-tbl th{text-align:left;font-weight:500;color:var(--text-3);font-size:8px;letter-spacing:.6px;padding:3px 5px;border-bottom:1px solid var(--border)}',
    '.rc-tbl td{padding:3px 5px;border-bottom:1px solid var(--border)}',
    '.rc-foot{margin-top:10px;font-size:8.5px;color:var(--text-3);line-height:1.45}',
  ].join('');

  let _rcMock = null;

  // R-IV.1364(c): the CSS and the fixture are SEPARATE. The CSS is needed whenever the card is
  // on; the fixture only under `?report=mock`. They used to share one gate, so every default load
  // fetched the mock just to get the stylesheet -- and a failed fetch left the LIVE card unstyled.
  async function rcLoad() {
    if (!REPORT_ON) return null;
    if (!document.getElementById('rc-css')) {
      const s = document.createElement('style');
      s.id = 'rc-css'; s.textContent = RC_CSS; document.head.appendChild(s);
    }
    if (!REPORT_MOCK || _rcMock) return _rcMock;
    try {
      const r = await fetch('/assets/regime/report_card_mock.v1.json', { cache: 'no-store' });
      _rcMock = await r.json();
    } catch (_) { _rcMock = null; }
    return _rcMock;
  }

  function rcVerdict(v) {
    if (!v || !v.text) return '';
    const st = String(v.state || '');
    const cls = st.indexOf('NOT REACHABLE') === 0 ? 'rc-nr'
      : st.indexOf('DEPARTS') === 0 ? 'rc-dep'
      : st.indexOf('CONSISTENT') === 0 ? 'rc-ok' : 'rc-early';
    return '<span class=\"rc-v ' + cls + ' \" title=\"' + esc(v.reason || '') + '\">'
      + esc(v.text) + '</span>';
  }

  // A panel with nothing to show says WHY. An empty panel reads as zero.
  function rcPanel(title, body, note, verdict) {
    return '<div class=\"rc-p\"><u>' + esc(title) + '</u>'
      + (verdict ? rcVerdict(verdict) : '')
      + '<div class=\"rc-pb\">' + body + '</div>'
      + (note ? '<em>' + esc(note) + '</em>' : '') + '</div>';
  }

  function rcNum(v, suffix) {
    return v == null ? '<b class=\"rc-na\">\u2014</b>'
      : '<b>' + esc(String(v)) + (suffix || '') + '</b>';
  }

  function rcHeld(b) {
    return rcNum(b.share, '%')
      + '<s>' + esc((b.held == null ? '?' : b.held) + ' of '
      + (b.checked == null ? '?' : b.checked) + ' checked \u00b7 '
      + (b.pending == null ? '?' : b.pending) + ' pending') + '</s>';
  }

  function rcRender(m) {
    if (!REPORT_ON || !m) return '';

    // R-IV.1321(b): THE EMPTY STATE until the cutover deploys. Each panel says what is
    // missing and why; none shows a zero, which would read as 'measured, and it was nil'.
    if (m.available === false) {
      const empties = ['FLIPS PER YEAR', 'SPY vs 200-DAY', 'WORST-DIP ORDER',
                       'WARNINGS THAT HELD', 'ALL-CLEARS THAT HELD']
        .map(function (t) {
          return rcPanel(t, '<b class=\"rc-na\">\u2014</b>',
                         'nothing scored yet', null);
        }).join('');
      return '<div class=\"rc-wrap\">'
        + '<div class=\"rc-h\"><b>REGIME REPORT CARD</b>'
        +   '<span class=\"rc-badge\">NO SCORED SESSIONS YET</span>'
        +   (m._mock ? '<span class=\"rc-mock\">MOCK</span>' : '')
        +   '<i>' + esc(m.reason || '') + '</i></div>'
        + '<div class=\"rc-panels\">' + empties + '</div>'
        + '<div class=\"rc-foot\">Scores only sessions after the v2.1 cutover; '
        +   'nothing is backfilled. Display only (#42); the scores never change the label or '
        +   'the kill switch.</div></div>';
    }

    const f = m.flips || {}, ma = m.ma200 || {}, dip = m.dip_order || {};
    const wh = m.warnings_held || {}, ac = m.all_clears_held || {};

    // FLIPS LEADS: ~1.3 years to a verdict, and the one figure with a stated target.
    const flipsBody = rcNum(f.per_year, '/yr')
      + '<s>' + esc('history ' + (f.history_per_year || '') + ' \u00b7 target '
      + String.fromCharCode(8804) + ' ' + (f.target_per_year || '')) + '</s>'
      + (f.annualised_is_grey
          ? '<em>annualised from under half a year, shown grey</em>' : '');

    // P7: UP-CROSSES / SCORED / PENDING. Never a bare whipsaw count.
    const maBody = '<b>' + esc(String(ma.up_crosses == null ? '\u2014' : ma.up_crosses)) + '</b>'
      + '<s>' + esc('up-crosses \u00b7 ' + ma.scored + ' scored \u00b7 '
      + ma.pending + ' pending') + '</s>'
      + (ma.whipsaws == null
          ? '<em>no whipsaw share until an up-cross finishes its 60 sessions</em>'
          : '<em>' + esc(ma.whipsaws + ' whipsaw(s) of ' + ma.scored + ' scored'
              + (ma.share == null ? '' : ' = ' + ma.share + '%')
              + ' \u00b7 history ' + ma.history_2013_pct + '% since 2013') + '</em>');

    // P10: added by the spec, and the only grading panel reachable this decade.
    const dipBody = (dip.stress_dip_median == null
        ? '<b class=\"rc-na\">\u2014</b>'
        : '<b>' + esc(dip.stress_dip_median + '% vs ' + dip.up_dip_median + '%') + '</b>')
      + '<s>' + esc('STRESS vs UP \u00b7 '
      + (dip.indep_stress == null ? '?' : dip.indep_stress) + ' and '
      + (dip.indep_up == null ? '?' : dip.indep_up) + ' independent windows') + '</s>'
      + (dip.order_holds == null ? ''
          : '<em>' + (dip.order_holds ? 'order holds: STRESS dips deeper'
                                      : 'order does NOT hold') + '</em>');

    const panels = rcPanel('FLIPS PER YEAR', flipsBody, f.basis, f.verdict)
      + rcPanel('SPY vs 200-DAY', maBody, ma.caption, ma.verdict)
      + rcPanel('WORST-DIP ORDER', dipBody, dip.question, dip.verdict)
      + rcPanel('WARNINGS THAT HELD', rcHeld(wh),
                'danger label to a dip of ' + (wh.threshold_pct || '3.09')
                + '%+ within 20 sessions', wh.verdict)
      + rcPanel('ALL-CLEARS THAT HELD', rcHeld(ac),
                'TREND-UP, then no new 60-session low', ac.verdict);

    // THE PER-LABEL TABLE IS LAST AND SMALLEST, with NO VERDICT COLUMN: a pooled verdict here
    // is ~14.6 years away and a per-label one further still.
    const rows = (m.by_label || []).map(function (r) {
      const share = r.share_higher == null ? '\u2014' : (r.share_higher + '%');
      const hist = r.history_available
        ? (r.history_share + '% (n=' + r.history_n + ')')
        : (r.history_note || '');
      return '<tr><td>' + esc(r.label) + '</td>'
        + '<td>' + esc(String(r.sessions)) + '</td>'
        + '<td>' + esc(String(r.checked)) + '</td>'
        + '<td>' + esc(String(r.pending)) + '</td>'
        + '<td>' + esc(String(r.indep == null ? '\u2014' : r.indep)) + '</td>'
        + '<td>' + esc(share) + '</td>'
        + '<td class=\"' + (r.history_available ? '' : 'rc-na') + '\">'
        +   esc(hist) + '</td>'
        + '<td>' + (r.reach ? rcVerdict(r.reach) : '') + '</td></tr>';
    }).join('');

    const head = ['LABEL', 'SESSIONS', 'CHECKED', 'PENDING', 'INDEP', 'HIGHER 20d',
                  'BASE RATE', 'REACHABILITY']
      .map(function (c) { return '<th>' + esc(c) + '</th>'; }).join('');

    return '<div class=\"rc-wrap\">'
      + '<div class=\"rc-h\"><b>' + esc(m.headline || 'REGIME REPORT CARD') + '</b>'
      +   (m._mock ? '<span class=\"rc-mock\">MOCK</span>' : '')
      +   '<i>' + esc(m.sub || '') + '</i></div>'
      + '<div class=\"rc-panels\">' + panels + '</div>'
      + '<div class=\"rc-tt\">BY LABEL <i>descriptive only, no verdict: a pooled '
      +   'verdict is about 14.6 years away (spec section 9)</i></div>'
      + '<table class=\"rc-tbl\"><thead><tr>' + head + '</tr></thead><tbody>'
      +   rows + '</tbody></table>'
      + '<div class=\"rc-foot\">' + esc(m.footer || '') + '</div>'
      + '</div>';
  }
  function rsHeadline(m) {
    const fresh = m.data_freshness || {};
    const held = m.held_no_match || {};
    if (fresh.headline) {
      return '<span class="rs-label rs-stale" title="'
        + esc((fresh.reason || '') + ' \u00b7 last label: ' + (m.regime_label || 'none'))
        + '">' + esc(fresh.headline) + '</span>';
    }
    if (held.stale) {
      const g = String(held.group || '');
      const cls = g === 'TREND-UP' ? 'g-up' : (g === 'RANGE' ? 'g-range' : 'g-down');
      return '<span class="rs-label rs-stale" title="'
        + esc((held.reason || '') + ' \u00b7 last label: ' + (m.regime_label || 'none'))
        + '">STALE</span>'
        // The group word is SMALL and COLOURED BY THE HELD LABEL'S GROUP, as the spec asks --
        // so a reader of a stale card still learns which way the last real reading leaned,
        // without the label itself claiming to be current.
        + (held.group_word
             ? '<span class="rs-last-reading ' + cls + '" title="'
               + esc('the group of the label still being held: ' + g) + '">'
               + esc(held.group_word) + '</span>'
             : '');
    }
    // R-IV.1277(b)/registration s1 / R-IV.1277(b): RECOVERY renders dark green. Keyed off the STORED label
    // rather than the display string, so a change to the words cannot silently drop the colour.
    const recovery = String(m.regime_key || '') === 'recovery';
    return '<span class="rs-label' + (recovery ? ' rs-recovery' : '') + '">'
      + esc(m.regime_label || '\u2014') + '</span>';
  }

  // The chips that belong beside the label: the held chip when no rule matched, and the
  // hysteresis chip when a candidate qualifies and is being held back. They are DIFFERENT
  // chips because they are different facts, and only one of them can be true at a time.
  function rsStateChips(m) {
    const held = m.held_no_match || {};
    let out = '';
    if (held.stale && held.chip) {
      out += '<span class="chip rs-tag" title="' + esc(held.reason || '') + '">'
        + esc(held.chip) + '</span>';
    }
    if (!held.stale && m.blocked) {
      // "RECOVERY qualifies, hold 3 of 5" -- the classifier's own words, not a paraphrase.
      out += '<span class="chip rs-tag" title="'
        + esc('a candidate qualifies and hysteresis is holding it; this is not stale')
        + '">' + esc(m.blocked) + '</span>';
    }
    return out;
  }

  // The two quiet lines under the label. Both DESCRIPTIVE, and neither gates anything (#42).
  function rsSubLines(m) {
    const dp = m.drift_prior || {};
    let out = '';
    if (m.tuned_for) {
      out += '<span class="rs-sub-line">' + esc(m.tuned_for) + '</span>';
    }
    // R-IV.1284(c): LAB's stamped drift prior. Values BLANK until LAB supplies them was the
    // earlier instruction; LAB has now stamped the table (c9a00aab...), so the figures are
    // real and carry their source, their n and the independence caveat in the same breath.
    // A label with NO row says so -- "never shown by v2" is not a prior of zero.
    if (dp.available) {
      out += '<span class="rs-sub-line rs-drift" title="' + esc(
        (dp.text || '') + ' \u00b7 ' + (dp.standing || '')
        + (dp.small_cell_note ? ' \u00b7 ' + dp.small_cell_note : '')) + '">'
        + esc('drift prior: ' + Number(dp.higher_pct).toFixed(1) + '% higher in '
              + dp.horizon_sessions + ' sessions, typical worst dip '
              + Number(dp.worst_dip_pct).toFixed(1) + '% \u00b7 n=' + dp.n
              + ' (' + (dp.independence || '') + ')')
        + '</span>';
    } else if (dp.reason) {
      out += '<span class="rs-sub-line rs-drift" title="' + esc(dp.reason) + '">'
        + esc('drift prior: none for this label') + '</span>';
    }
    return out;
  }

  function leanColor(lean) {
    return LEAN_COLOR[String(lean || 'neutral')] || LEAN_COLOR.neutral;
  }

  function setMockChip(id, fixture) {
    const el = $(id);
    if (!el) return;
    const isMock = !!(fixture && fixture._mock);
    el.hidden = !isMock;
    el.title = isMock
      ? 'Mock fixture (R-IV.1209(c) Phase A). Every value on this tile is fake.'
      : '';
  }

  async function loadAgoraMocks() {
    const keys = Object.keys(AGORA_FIXTURES);
    await Promise.all(keys.map(async (k) => {
      try {
        const r = await fetch(AGORA_FIXTURES[k], { cache: 'no-store' });
        _agora[k] = r.ok ? await r.json() : null;
      } catch (_) {
        // Left null. Each renderer says the fixture did not load rather than drawing an
        // empty shell, which would read as "no crowding" / "no events" \u2014 a claim.
        _agora[k] = null;
      }
    }));
    // And the live ones, through apiFetch. A failed live read is ALSO left null and the
    // renderer says so: it must never fall back to the fixture, because a mock served where
    // live data belongs looks exactly like the real thing.
    await Promise.all(Object.keys(AGORA_LIVE).map(async (k) => {
      try {
        const r = await apiFetch(AGORA_LIVE[k]);
        const d = r.ok ? await r.json() : null;
        _agora[k] = (d && !d.error) ? d : null;
      } catch (_) {
        _agora[k] = null;
      }
    }));
    renderCrowd();
    renderFearPrice();
    renderBookStress();
    renderEventStrip();
  }

  function agoraWait(host, what) {
    host.innerHTML = '<div class="rs-wait">' + esc(what)
      + ' fixture did not load</div>';
  }

  // R-IV.1369: a tile-header ⓘ, created once beside `anchorId` and re-titled on every paint.
  // What a cleaned tile moves off its face goes HERE, so nothing is deleted -- only moved.
  // The anchor itself is hidden: its text is one of the things the ⓘ now carries.
  function tileInfo(anchorId, id, note) {
    const a = $(anchorId);
    if (!a) return;
    let i = $(id);
    if (!i) {
      i = document.createElement('span');
      i.id = id; i.className = 'pv-i rg-tinfo'; i.tabIndex = 0;
      i.setAttribute('role', 'img'); i.setAttribute('aria-label', 'about this tile');
      i.textContent = 'i';
      a.parentNode.insertBefore(i, a);
    }
    i.title = note;
    a.hidden = true;
  }

  // ═══ R-IV.1369(f) · THE CROWD TILE, CLEANED ═══════════════════════════════════════════════
  //
  // One axis for every gauge: bears crowded on the LEFT, bulls crowded on the RIGHT. So each
  // row is plotted by what its high end MEANS (crowd_b6.CROWDED_SIDE_AT_HIGH): a high FUTURES
  // net is bulls crowded and sits right, at `pct`; a high PUT/CALL is bears crowded and sits
  // left, at `100 - pct`. Same rule the headline counts by, so the dot and the word cannot
  // disagree about which side is full.
  const CROWD_PLOT = { 'FUTURES': (p) => p, 'PUT/CALL': (p) => 100 - p };
  const CROWD_NAME = { 'FUTURES': 'Futures positioning', 'PUT/CALL': 'Put/call · UW flow' };
  function crowdGauge(r) {
    const plot = CROWD_PLOT[r.key];
    // The ticks and end zones sit at crowd_b6's EXTREME_LOW / EXTREME_HIGH (10 / 90).
    const track = '<i class="cg-z lo"></i><i class="cg-z hi"></i>'
      + '<i class="cg-t" style="left:10%"></i><i class="cg-t" style="left:50%"></i><i class="cg-t" style="left:90%"></i>';
    // No percentile, no marker: a dot at 0 would read as a reading.
    const mark = (r.pct != null && plot)
      ? '<b class="cg-m' + (r.thin ? ' thin' : '') + '" style="left:'
        + Math.max(0, Math.min(100, plot(Number(r.pct)))).toFixed(1) + '%"></b>' : '';
    return '<div class="cg-track" role="img" aria-label="' + esc((r.key || '') + ' ' + (r.pct_label || 'not ranked'))
      + '">' + track + mark + '</div>';
  }
  function crowdRow(r) {
    if (!CROWD_PLOT[r.key]) return '';
    // A row the payload did not carry is SAID to be missing. Dropping it would leave a tile
    // that looks complete with one of its two gauges gone.
    if (r._absent) {
      return '<div class="cg-row"><div class="cg-h"><b>' + esc(CROWD_NAME[r.key]) + '</b></div>'
        + '<div class="cg-line">— · the crowd read did not include this row</div></div>';
    }
    const n = r.history_n, full = r.history_full || 52;
    // "of the row's REAL window": the count crowd_b6 served, never an assumed 52.
    const win = n != null
      ? (r.key === 'FUTURES' ? 'the last ' + n + ' weekly readings' : 'the last ' + n + ' sessions ranked')
      : 'its ranked history';
    const cmp = r.pct == null ? 'not ranked yet'
      : (r.key === 'FUTURES' ? 'more long' : 'more puts') + ' than ' + r.pct + '% of ' + win;
    const value = r.key === 'FUTURES'
      ? esc(r.value || '—')
      : esc(r.value || '—') + ' over ' + esc(String((/(\d+)D/.exec(r.sub || '') || [])[1] || '?')) + ' days';
    let right = '';
    if (r.key === 'FUTURES') {
      // (f)4: the as-of ALWAYS shows, as its test requires; amber ONLY when a weekly release
      // was missed, which crowd_b6.release_missed decides on New York's calendar.
      right = '<span class="cg-asof' + (r.release_missed ? ' rg-amber-t' : '') + '" title="'
        + esc((r.staleness_note || '') + (r.release_missed ? ' · a weekly release was missed: expected '
          + (r.expected_as_of || '?') : '')) + '">AS OF ' + esc(rcDay(r.as_of) || '—') + '</span>';
    }
    if (r.thin) {
      right += '<span class="rg-chip rg-amber">SHORT HISTORY · ' + esc(n != null ? n : '?') + ' OF ' + esc(full) + '</span>';
    }
    return '<div class="cg-row' + (r.mock ? ' ag-row-mock' : '') + '" title="' + esc(r.source || '') + '">'
      + '<div class="cg-h"><b>' + esc(CROWD_NAME[r.key]) + '</b>'
      + (r.mock ? '<span class="ag-rmock" title="not wired">MOCK</span>' : '') + right + '</div>'
      + '<div class="cg-line"><span class="cg-v">' + value + '</span> · ' + esc(cmp) + '</div>'
      + crowdGauge(r) + '</div>';
  }
  function crowdShortRow(r) {
    if (!r) return '';
    // (f)5: shown, not counted -- no gauge, because it has no percentile.
    const flag = r.crowded_short === true
      ? '<span class="rg-chip rg-teal">CROWDED SHORT</span>' : '';
    return '<div class="cg-row cg-si" title="' + esc(r.cadence || '') + '">'
      + '<div class="cg-h"><b>Short interest</b>' + flag
      + (r.settlement_date ? '<span class="cg-asof">SETTLED ' + esc(rcMd(r.settlement_date)) + '</span>' : '') + '</div>'
      + '<div class="cg-line">' + (r.symbol ? esc(r.symbol) + ' ' : '')
      + '<span class="cg-v">' + esc(r.value == null ? '—' : r.value) + '</span> days to cover (flag at '
      + esc(r.crowded_short_at != null ? r.crowded_short_at : 5) + ') · shown, not counted'
      // R-IV.1318(b): FINRA's terms require it be named as owner and source WHEREVER its data
      // shows, so this stays on the face of the tile rather than moving behind the ⓘ.
      + (r.attribution ? ' · ' + esc(r.attribution) : '') + '</div></div>';
  }
  function renderCrowdClean(host, m) {
    const rows = m.rows || [];
    const word = m.headline ? String(m.headline).replace(/^CROWD\s+/i, '') : null;
    // (f)1: with no live percentile there is no headline word -- "—" and the basis say so.
    const basis = String(m.headline_basis || '').replace(/^./, (c) => c.toUpperCase());
    host.innerHTML = '<div class="cg">'
      + '<div class="cg-hero" style="color:' + headColor(m.headline_lean) + '">' + esc(word || '—') + '</div>'
      + '<div class="cg-basis">' + esc(basis) + '</div>'
      + '<div class="cg-axis"><span>◀ BEARS CROWDED</span><span>BULLS CROWDED ▶</span></div>'
      + crowdRow(rows.find((r) => r.key === 'FUTURES') || { key: 'FUTURES', _absent: true })
      + crowdRow(rows.find((r) => r.key === 'PUT/CALL') || { key: 'PUT/CALL', _absent: true })
      + crowdShortRow(rows.find((r) => r.key === 'SHORT INT'))
      + '<div class="cg-foot">Crowded means everyone is already positioned that way, which is fuel for a '
      + 'move the other way. Context, not a signal.</div></div>';
    // (f)8: sources and the full basis go behind the ⓘ, with the settled close the header
    // used to show -- moved, not deleted.
    tileInfo('crowdSettled', 'crowdInfo', ['Settled close ' + (m.settled_close || '—'),
      'Basis: ' + (m.headline_basis || '—')]
      .concat((m.footnotes || []).map((f) => 'Source: ' + f))
      .concat(m.caption ? [m.caption] : []).join('\n'));
  }

  // \u2500\u2500 board 1: Crowd \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  function renderCrowd() {
    // R-IV.1318(b): BOTH DATES ON EVERY VALUE. FINRA publishes twice monthly about 7 business
    // days after settlement, so this number can be three weeks old BY DESIGN -- today's is the
    // 2026-09-30 settlement, published 2026-10-12, because 2026-10-15 is not out yet. A
    // positioning figure printed bare reads as current, which is the one thing this tile's
    // siblings exist not to do. The publish date is OBSERVED (the file Last-Modified header),
    // never a rule-of-thumb date computed from the settlement.
    function agDates(r) {
      if (!r.settlement_date) return '';
      const t = 'settled ' + r.settlement_date
        + (r.publish_date ? ' \u00b7 published ' + r.publish_date : '');
      return '<span class="ag-dates" title="' + esc(r.cadence || '') + '">'
        + esc(t) + '</span>';
    }

    const host = $('crowdGauge');
    if (!host) return;
    const m = _agora.crowd;
    setMockChip('crowdMock', m);
    if (!m) return agoraWait(host, 'crowd');
    const st = $('crowdSettled');
    if (st) st.textContent = 'close ' + (m.settled_close || '\u2014');
    // R-IV.1369(f): the cleaned tile is the default; `?clean=off` keeps the rows below.
    if (CLEAN) { renderCrowdClean(host, m); return; }

    const rows = (m.rows || []).map((r) => {
      // A THIN HISTORY STARS THE PERCENTILE AND GOES AMBER. R-IV.1194(f): short history shows
      // amber "n / N" with the percentile starred -- amber is "cannot confirm", which is
      // exactly what a percentile over 9 weeks is.
      const cls = r.thin ? 'ag-thin' : (r.extreme ? 'ag-extreme' : '');
      // B6: THE MOCK MARK IS PER ROW. All three rows are live since R-IV.1318(b) -- CFTC, UW
      // flow and now FINRA short interest from the free twice-monthly file -- but the mark
      // stays per row, because "which rows are live" is a fact that has changed twice and
      // will change again. The row carries no gauge dot when it has no percentile: a dot at
      // 0 would read as a reading.
      const hasPct = r.pct != null;
      const pos = Math.max(0, Math.min(100, Number(r.pct) || 0));
      return '<div class="ag-row' + (r.mock ? ' ag-row-mock' : '') + '" title="'
        + esc(r.source || '') + (r.staleness_note ? ' · ' + esc(r.staleness_note) : '') + '">'
        + '<div class="ag-rk"><b>' + esc(r.key) + '</b>'
        + (r.mock ? '<span class="ag-rmock" title="not wired: see the footnote">MOCK</span>'
          : '')
        + '<i>' + esc(r.sub || '') + '</i>' + agDates(r) + '</div>'
        + '<div class="ag-rv">' + esc(r.value == null ? '—' : r.value) + '</div>'
        + '<div class="vc-gauge ag-g">'
        + (hasPct ? '<b class="' + cls + '" style="left:' + pos.toFixed(1) + '%"></b>' : '')
        + '</div>'
        + '<div class="ag-rp ' + cls + '">' + esc(r.pct_label || '—') + '</div>'
        + '</div>';
    }).join('');

    host.innerHTML =
      '<div class="ag-head" style="color:' + leanColor(m.headline_lean) + '">'
      + esc(m.headline || '\u2014') + '</div>'
      + '<div class="ag-sub">' + esc(m.headline_basis || '') + '</div>'
      + '<div class="ag-scale"><span>\u25c2 BEARS</span><span>BULLS \u25b8</span></div>'
      + rows
      + '<div class="ag-foot">' + (m.footnotes || []).map(esc).join(' \u00b7 ') + '</div>'
      // R-IV.1318(b): FINRA must be identified as owner and source wherever its data shows,
      // which its Equity Data terms require. Rendered from the ROW rather than hardcoded, so a
      // panel that stops carrying FINRA data stops claiming FINRA as a source.
      + (() => {
          const f = (m.rows || []).find((r) => r.attribution && r.settlement_date);
          return f ? '<div class="ag-attrib">' + esc(f.attribution) + ' \u00b7 '
            + esc(f.cadence || '') + '</div>' : '';
        })()
      + '<div class="ag-cap">' + esc(m.caption || '') + '</div>';
  }

  // \u2500\u2500 board 2: Fear Price \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  function renderFearPrice() {
    const host = $('fearPrice');
    if (!host) return;
    const m = _agora.fear;
    setMockChip('fearMock', m);
    if (!m) return agoraWait(host, 'fear price');
    const st = $('fearSettled');
    if (st) st.textContent = 'close ' + (m.settled_close || '\u2014');

    const gaps = (m.gaps || []).map((g) => {
      const pts = Number(g.pts) || 0;
      const w = Math.min(Math.abs(pts), 10) * 5;
      const left = pts >= 0 ? 50 : 50 - w;
      // Positive gap = implied over realized = premium rich. Teal, not lime: rich premium is
      // notable, not bullish (R-IV.1209(d)2's "neutral-but-notable").
      const col = pts >= 0 ? 'var(--teal)' : 'var(--text-2)';
      return '<div class="ag-gap">'
        + '<span class="ag-gt">' + esc(g.ticker) + '</span>'
        + '<span class="ag-gb"><i style="left:' + left.toFixed(1) + '%;width:'
        + w.toFixed(1) + '%;background:' + col + '"></i></span>'
        + '<span class="ag-gv">' + (pts >= 0 ? '+' : '\u2212')
        + Math.abs(pts).toFixed(1) + '</span>'
        + '</div>';
    }).join('');

    const cv = m.curve || {};
    const curve = (cv.tenors || []).map((t, i) => {
      const vals = cv.values || [];
      // NULL-SAFE, and it matters on live data: Math.min over [18.2, null] is 0, which would
      // squash every other bar to full height against a floor that is not in the data. A
      // tenor with no reading draws a stub and says so on hover.
      const have = vals.filter((v) => v != null);
      const v = vals[i];
      if (v == null) {
        return '<span class="ag-ct ag-ct-na" title="no reading for ' + esc(t)
          + '"><i style="height:2px"></i>' + esc(t) + '</span>';
      }
      const lo = Math.min.apply(null, have), hi = Math.max.apply(null, have);
      const h = hi > lo ? 6 + ((v - lo) / (hi - lo)) * 14 : 12;
      return '<span class="ag-ct" title="' + esc(t) + ' ' + Number(v).toFixed(2)
        + '"><i style="height:' + h.toFixed(1) + 'px"></i>' + esc(t) + '</span>';
    }).join('');

    const sk = m.skew || {};
    const em = m.expected_move || {};
    host.innerHTML =
      '<div class="ag-head" style="color:' + leanColor(m.headline_lean) + '">'
      + esc(m.headline || '\u2014') + '</div>'
      + '<div class="ag-sub">' + esc(m.headline_basis || '') + '</div>'
      + '<div class="ag-gaps"><span class="ag-ends">CHEAP</span>' + gaps
      + '<span class="ag-ends ag-right">RICH</span></div>'
      + '<div class="ag-blk"><span class="ag-bl">VIX CURVE</span>'
      + '<b>' + esc(cv.label || '\u2014') + '</b>'
      + '<span class="ag-curve">' + curve + '</span></div>'
      + '<div class="ag-blk"><span class="ag-bl">SKEW \u00b7 PUT DEMAND</span>'
      + '<b>' + esc(sk.pct_label || '\u2014') + '</b>'
      + '<span class="ag-sk"><span>' + esc(sk.left || '') + '</span>'
      + '<span>' + esc(sk.right || '') + '</span></span></div>'
      + '<div class="ag-blk" title="' + esc(em.basis || em.reason || '') + '">'
      + '<span class="ag-bl">' + esc(em.label || '') + '</span>'
      + '<b>' + (em.approx ? '\u2248 ' : '') + esc(em.value || '\u2014') + '</b>'
      + '<span class="ag-days">' + esc(em.days || '') + '</span></div>'
      + '<div class="ag-cap">' + esc(m.caption || '') + '</div>';
  }

  // \u2500\u2500 board 3: Book Reality Check (a SECTION inside BOOK) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  function renderBookStress() {
    const host = $('bookStress');
    if (!host) return;
    const m = _agora.bookStress;
    if (!m) { host.innerHTML = ''; return; }

    const all = [];
    (m.rows || []).forEach((r) => (r.cells || []).forEach((c) => all.push(Math.abs(c))));
    const max = all.length ? Math.max.apply(null, all) : 1;

    const rows = (m.rows || []).map((r) => {
      const cells = (r.cells || []).map((v) => {
        const a = Math.round(Math.min(Math.abs(v) / max, 1) * 55 + 8);
        const col = v >= 0 ? 'var(--up)' : 'var(--down)';
        const txt = (v >= 0 ? '+' : '\u2212') + '$'
          + Math.abs(v).toLocaleString('en-US');
        return '<span class="bs-c" style="background:color-mix(in srgb, ' + col + ' '
          + a + '%, var(--bg-2, #0b1122))">' + esc(txt) + '</span>';
      }).join('');
      return '<div class="bs-row' + (r.total ? ' bs-total' : '') + '">'
        + '<span class="bs-k">' + esc(r.key) + '</span>' + cells + '</div>';
    }).join('');

    const w = m.worst || {};
    const tr = m.trend || {};
    const trows = (tr.rows || []).map((t) => {
      const against = String(t.verdict).toUpperCase() === 'AGAINST';
      return '<div class="bs-t">'
        + '<span class="bs-tk">' + esc(t.ticker) + '</span>'
        + '<span class="bs-td">' + esc(t.dir) + '</span>'
        + '<span class="bs-dot ' + esc('bs-' + t.daily) + '"></span>'
        + '<span class="bs-dot ' + esc('bs-' + t.weekly) + '"></span>'
        + '<span class="bs-tv" style="color:'
        + (against ? 'var(--down)' : 'var(--text-2)') + '">' + esc(t.verdict) + '</span>'
        + '</div>';
    }).join('');

    host.innerHTML =
      '<div class="bs-head"><span class="bs-title">Reality Check</span>'
      + '<span class="mock-chip" title="Mock fixture (R-IV.1209(c) Phase A). Every value '
      + 'in this section is fake.">MOCK</span>'
      + '<span class="bs-vol">' + esc(m.vol_mode || '') + '</span></div>'
      + '<div class="bs-cols"><span class="bs-k">SPY</span>'
      + (m.columns || []).map((c) => '<span class="bs-col">' + esc(c) + '</span>').join('')
      + '</div>'
      + rows
      + '<div class="bs-worst"><span class="bs-wl">WORST</span>'
      + '<b>' + esc(w.value || '\u2014') + '</b>'
      + '<i>' + esc(w.where || '') + (w.pct_of_sleeve ? ' \u00b7 '
        + esc(w.pct_of_sleeve) : '') + '</i></div>'
      + '<div class="bs-trend"><span class="bs-wl">VS. ITS TREND</span>'
      + '<b>' + esc(tr.headline || '') + '</b><span class="bs-dw">D W</span></div>'
      + trows
      // NOT SILENTLY DROPPED (R-IV.1194(g)): anything unmodellable is listed as such.
      + ((m.not_modelled || []).length
        ? '<div class="bs-nm">not modelled: '
          + (m.not_modelled || []).map(esc).join(' \u00b7 ') + '</div>' : '')
      + '<div class="ag-cap">' + esc(m.caption || '') + '</div>';
  }

  // \u2500\u2500 board 4: Event Strip (full width) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
  function renderEventStrip() {
    const host = $('eventStrip');
    if (!host) return;
    const m = _agora.eventStrip;
    setMockChip('evMock', m);
    if (!m) return agoraWait(host, 'event strip');
    const t = $('evTitle');
    if (t && m.title) t.textContent = m.title;
    const op = $('evOpex');
    if (op) op.textContent = m.next_opex || '';

    const maxEarn = Math.max.apply(null,
      (m.days || []).map((d) => Number(d.earn) || 0).concat([1]));

    const days = (m.days || []).map((d, i, arr) => {
      const evs = (d.events || []).map((e) => {
        const k = String(e.kind || 'macro');
        return '<span class="ev-chip ev-' + esc(k) + '">' + esc(e.k) + '</span>';
      }).join('');
      const earn = Number(d.earn) || 0;
      const h = Math.max(2, Math.round((earn / maxEarn) * 16));
      const yours = Number(d.book_earn) || 0;
      return '<div class="ev-day' + (d.blackout ? ' ev-blackout' : '')
        + (i === arr.length - 1 ? ' ev-last' : '') + '">'
        + '<div class="ev-dow">' + esc(d.dow) + '<b>' + esc(d.dd) + '</b></div>'
        + '<div class="ev-evs">' + evs + '</div>'
        + '<div class="ev-earn"><i style="height:' + h + 'px;background:'
        + (yours ? 'var(--teal)' : 'var(--border-strong)') + '"></i>'
        + '<span>' + earn + (yours ? ' \u00b7 ' + yours + ' yours' : '') + '</span></div>'
        + '</div>';
    }).join('');

    host.innerHTML =
      '<div class="ev-legend">'
      + '<span class="ev-chip ev-macro">MACRO</span>'
      + '<span class="ev-chip ev-book">YOUR BOOK</span>'
      + '<span class="ev-bl">' + esc(m.blackout_label || '') + '</span>'
      + '</div>'
      + '<div class="ev-grid">' + days + '</div>'
      + '<div class="ag-cap">' + esc(m.caption || '') + '</div>';
  }

  function initGrid() {
    grid = GridStack.init({
      column: 12, cellHeight: 46, margin: 7, handle: '.tile-grip', float: false,
      resizable: { handles: 'e, se, s, sw, w' },
      // T1.1 — collapse to one column at <=768px.
      // breakpointForWindow:true is REQUIRED: without it GridStack measures the grid
      // element's clientWidth rather than the viewport, so the JS collapse and the CSS
      // media query fire at different widths. layout:'list' must be explicit — the
      // 11.1.2 default is 'moveScale', which scales tiles into one column by ratio
      // instead of stacking them in reading order.
      columnOpts: {
        breakpointForWindow: true,
        layout: 'list',
        breakpoints: [{ w: MOBILE_MAX_W, c: 1 }],
      },
    });

    // Lock interaction before the first await, so a phone cannot drag or resize
    // during the layout fetch.
    syncStaticMode();

    apiFetch('/api/layout').then((r) => r.ok ? r.json() : null).then((d) => {
      const saved = (d && Array.isArray(d.layout) && d.layout.length) ? d.layout : null;
      if (saved) {
        // T1.7 — addRemove MUST stay false. GridStack's default (true) deletes from
        // the DOM every tile whose gs-id is absent from the saved row, so any newly
        // shipped tile silently vanishes for anyone holding a layout. Never restore
        // the default; see reconcileMissingTiles() for the placement half.
        try { grid.load(saved, false); } catch (_) {}
        const orphans = reconcileMissingTiles(saved);
        if (d.updated_at) {
          $('layoutStatus').textContent = 'layout restored'
            + (orphans ? ' · ' + orphans + ' new tile' + (orphans > 1 ? 's' : '') : '');
        }
      }
    }).catch(() => {}).finally(() => {
      // Mobile order is applied AFTER any restore so it wins over persisted positions.
      applyMobileOrder();
      syncStaticMode();
      // ══ T1.2(c) LOAD-ORDER INVARIANT — DO NOT MOVE THIS ══════════════════════
      // GridStack dispatches 'change' twice during boot (constructor auto-parse and
      // load()). Wiring the handler HERE, after load() settles, is the only reason
      // those boot events don't reach saveLayout(). Hoisting this above the fetch, or
      // awaiting inside the handler, re-arms a cold-load overwrite of the desktop slot.
      // Acceptance: reload /app at phone width; /api/layout updated_at must not change.
      saveArmed = true;
      grid.on('change', () => {
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveLayout, 800);
      });
      // R-IV.1440: the TV preview tile (assets/tv/tv_tile.js, loaded only under ?tv=preview)
      // places itself AFTER the restore, so reconcileMissingTiles() never parks it at the bottom.
      window.__agoraGrid = grid;
      document.dispatchEvent(new CustomEvent('agora:grid-ready', { detail: { grid } }));
    });

    MOBILE_MQ.addEventListener('change', () => {
      syncStaticMode();
      applyMobileOrder();
    });
  }

  async function saveLayout() {
    // ══ T1.2(b) HARD GUARD ═══════════════════════════════════════════════════════
    // There is exactly ONE layout row (layout_key='default') and POST is an
    // unconditional upsert with no history, so any mobile-shaped write destroys the
    // desktop arrangement unrecoverably. Mobile is read-only against /api/layout,
    // always. Do not soften this to a confirm dialog or a separate mobile payload
    // without a server-side second slot to write into.
    if (isCollapsed()) { $('layoutStatus').textContent = 'mobile · layout locked'; return; }
    if (!saveArmed) return;
    try {
      // The TV preview tile is never written into the one layout row (R-IV.1440(c)1: a preview
      // leaves nothing behind once the flag is gone).
      const layout = grid.save(false).filter((n) => n && n.id !== 'tv'); // positions + gs-id, no content
      const r = await apiFetch('/api/layout', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, body: JSON.stringify({ layout }) });
      $('layoutStatus').textContent = r.ok ? 'layout saved ' + new Date().toLocaleTimeString() : (r.status === 401 ? 'sign in to save layout' : 'layout save failed');
    } catch (_) { $('layoutStatus').textContent = 'layout save failed'; }
  }

  // ═══ B2b modules ══════════════════════════════════════════════════════════
  const fmt$ = (v) => (v == null ? '--' : (v < 0 ? '-$' : '$') + Math.abs(Number(v)).toLocaleString('en-US', { maximumFractionDigits: 0 }));
  const signCls = (v) => (v == null ? '' : v > 0 ? 'val-up' : v < 0 ? 'val-down' : 'val-muted');
  function setDot(id, age, degraded, flatline, session, note, incoherent) { setHealth($(id), age, degraded, flatline, session, note, incoherent); }

  // ── b3 Breadth panel (shares the regime payload) ──────────────────────────
  function renderBreadthPanel(regime) {
    const el = $('breadthPanel'); if (!el) return;
    const b = (regime && regime.breadth) || {};
    // Breadth is computed from the last complete close (metrics_date), all day. The payload's
    // `anchor` describes the THEME snapshot ('provisional'), not these numbers, so it is not used.
    const lag = regime && regime.anchor_lag && regime.anchor_lag.sessions_behind;
    $('breadthAnchor').innerHTML = regime ? closeChip(regime.metrics_date, !!regime.degraded_reason || (lag != null && lag > 0)) : '';
    const gauge = (label, v, gloss) => {
      const w = v != null ? Math.max(0, Math.min(100, v)) : 0;
      const col = v != null && v >= 60 ? 'var(--up)' : v != null && v <= 40 ? 'var(--down)' : 'var(--teal)';
      return `<div class="breadth-gauge"><div class="lab"><span data-gloss="${gloss || ''}">${label}</span><b>${v != null ? v.toFixed(0) + '%' : '--'}</b></div>`
        + `<div class="bar-track"><span style="width:${w}%;background:${col}"></span></div></div>`;
    };
    el.innerHTML = gauge('% &gt; 20DMA', b.pct_above_20dma) + gauge('% &gt; 50DMA', b.pct_above_50dma, 'BREADTH50') + gauge('% &gt; 200DMA', b.pct_above_200dma)
      + `<div class="hl-counts">
           <div class="hl-box"><div class="t">New Highs</div><div class="v val-up">${b.new_high_20d != null ? b.new_high_20d : '--'} <span class="val-muted" style="font-size:10px">20d</span> · ${b.new_high_52w != null ? b.new_high_52w : '--'} <span class="val-muted" style="font-size:10px">52w</span></div></div>
           <div class="hl-box"><div class="t">New Lows</div><div class="v val-down">${b.new_low_20d != null ? b.new_low_20d : '--'} <span class="val-muted" style="font-size:10px">20d</span> · ${b.new_low_52w != null ? b.new_low_52w : '--'} <span class="val-muted" style="font-size:10px">52w</span></div></div>
           <div class="hl-box"><div class="t">Up &gt; 3%</div><div class="v val-up">${b.up_3 != null ? b.up_3 : '--'}</div></div>
           <div class="hl-box"><div class="t">Down &gt; 3%</div><div class="v val-down">${b.down_3 != null ? b.down_3 : '--'}</div></div>
         </div>`;
    applyGlossary(el);
  }

  // ── b1 Themes table ────────────────────────────────────────────────────────
  function statusClass(st) {
    const s = (st || '').toUpperCase();
    if (s.indexOf('DOMINANT') !== -1 || s.indexOf('STRONG') !== -1) return 'st-dom';
    if (s.indexOf('EMERG') !== -1 || s.indexOf('IMPROV') !== -1) return 'st-emg';
    if (s.indexOf('FAD') !== -1 || s.indexOf('DETERIOR') !== -1 || s.indexOf('WEAK') !== -1) return 'st-fad';
    return '';
  }
  async function loadThemes() {
    let data = null;
    try { const r = await apiFetch('/api/stable/themes'); if (r.ok) data = await r.json(); } catch (_) {}
    const el = $('themesTable'); if (!el) return;
    $('themesAsOf').textContent = data && data.date ? data.date : '';
    setDot('themesHealthDot', data && data.data_age_seconds, data ? !!data.degraded : null, data && data.flatline, data && data.session);
    noteFlatline('nightly', data && data.flatline, 'Themes');
    _health.themes = !data ? 'unconfirmed' : data.degraded ? 'down' : 'ok'; updateGlobalHealth();
    const themes = (data && data.themes) || [];
    if (!themes.length) { el.innerHTML = '<div class="th-row"><span class="nm val-muted">no theme snapshot</span></div>'; return; }
    let html = '<div class="th-row head"><span class="rk">#</span><span class="nm">Theme</span><span class="sc">Score</span><span class="dl">1d Δ</span><span>Status</span></div>';
    themes.forEach((t) => {
      const d = t.score_1d_delta;
      html += `<div class="th-row" data-theme="${esc(t.theme)}">
        <span class="rk">${t.rank}</span>
        <span class="nm">${esc(t.theme)} <span class="val-muted" style="font-size:10px">${t.n_names || ''}</span></span>
        <span class="sc">${t.score != null ? Number(t.score).toFixed(0) : '--'}</span>
        <span class="dl ${signCls(d)}">${d != null ? (d >= 0 ? '+' : '') + Number(d).toFixed(1) : '·'}</span>
        <span class="status-chip ${statusClass(t.status)}">${esc(t.status || '')}</span></div>`;
    });
    el.innerHTML = html;
    el.querySelectorAll('.th-row[data-theme]').forEach((r) => r.addEventListener('click', () => openThemeMembers(r.dataset.theme, r)));
    applyGlossary(el);
  }

  async function openThemeMembers(theme, src) {
    openPopup('Theme · ' + theme, '<div class="mem-sec">loading…</div>', src);
    let data = null;
    try { const r = await apiFetch('/api/stable/theme/' + encodeURIComponent(theme) + '/members'); if (r.ok) data = await r.json(); } catch (_) {}
    if (!data) { $('memberBody').innerHTML = '<div class="mem-sec">unavailable</div>'; return; }
    const row = (m) => {
      const rs = m.rs_qqq_20d;
      return `<div class="mem-row" data-ticker="${esc(m.ticker)}">
        <span class="mtk" data-ticker="${esc(m.ticker)}" data-chart="${esc(String(m.ticker || '').toUpperCase())}" tabindex="0" role="button">${esc(m.ticker)}</span>
        <span class="val-muted" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(m.name || m.subtheme || '')}</span>
        <span class="${signCls(m.ret_1d)}">${m.ret_1d != null ? (m.ret_1d >= 0 ? '+' : '') + (m.ret_1d * 100).toFixed(1) + '%' : '--'}</span>
        <span class="val-muted">${m.last_price != null ? '$' + Number(m.last_price).toFixed(2) : '--'}</span>
        <span class="badge-slot"></span>
        <button class="opt-btn" data-ticker="${esc(m.ticker)}">opt</button></div>`;
    };
    const sec = (name, arr) => `<div class="mem-sec">${name} <span class="val-muted">· RS vs QQQ</span></div>` + ((arr || []).map(row).join('') || '<div class="mem-row"><span class="val-muted">none</span></div>');
    // Freshness: live intraday (provisional) vs prior close — so stale close data is never mistaken for "now".
    const rb = String(data.ranking_basis || '');
    const fresh = data.anchor === 'provisional'
      ? (rb && rb !== 'live'
          ? `ranked @ ${rb.replace('close@', '')} close · prices live`
          : `ranked live · ${ageLabel(data.data_age_seconds)} old`)
      : data.anchor === 'close' ? `${String(data.as_of || '').slice(0, 10)} close` : 'unknown';
    const label = data.anchor === 'provisional' ? "today's move" : '1d';
    $('memberBody').innerHTML = `<div class="mem-sec" style="color:var(--text-3);border:none">as of ${esc(fresh)}</div>`
      + sec('Top · ' + label, data.top) + sec('Bottom · ' + label, data.bottom);
    $('memberBody').querySelectorAll('.opt-btn[data-ticker]').forEach((e) => e.addEventListener('click', () => loadOptionsContext(e)));
    // Flow/Kairos badges — on-demand for this popup only (not polled while closed).
    const memberTickers = [...(data.top || []), ...(data.bottom || [])].map((m) => m.ticker);
    fetchTickerContext(memberTickers).then((ctx) => annotateTickerBadges('#memberBody .mem-row', ctx));
  }

  // Options context — FOREGROUND UW read on explicit click only (never polled).
  async function loadOptionsContext(btn) {
    const tk = btn.dataset.ticker;
    const row = btn.closest('.mem-row');
    if (row.nextElementSibling && row.nextElementSibling.classList.contains('opt-ctx')) { row.nextElementSibling.remove(); return; }
    const ctx = document.createElement('div'); ctx.className = 'opt-ctx'; ctx.textContent = 'loading options context…';
    row.after(ctx);
    try {
      const r = await apiFetch('/api/committee/enrichment/' + encodeURIComponent(tk));
      if (!r.ok) { ctx.textContent = 'options context unavailable'; return; }
      const e = (await r.json()).enrichment || {};
      const iv = e.iv_rank || {}, tide = e.market_tide || {}, mp = e.max_pain || {};
      const parts = [];
      if (iv.iv_rank != null) parts.push('IV rank ' + Number(iv.iv_rank).toFixed(0));
      // NOTE: market_tide is WHOLE-MARKET (UW get_market_tide takes no ticker) — same for every
      // name. Label it "mkt-tide" so it is never mistaken for this ticker's own flow.
      if (tide.net_call_premium != null && tide.net_put_premium != null)
        parts.push('mkt-tide ' + (Number(tide.net_call_premium) > Number(tide.net_put_premium) ? 'bullish' : 'bearish'));
      if (mp.max_pain_strike != null) parts.push('max-pain ' + mp.max_pain_strike + ' (' + mp.dte + 'dte)');
      ctx.textContent = parts.length ? tk + ' · ' + parts.join(' · ') : tk + ' · no options context cached';
    } catch (_) { ctx.textContent = 'options context error'; }
  }

  // ── Charts (Chart.js) ──────────────────────────────────────────────────────
  const SECTOR_RAMP = ['#14b8a6', '#7CFF6B', '#ff5c33', '#38bdf8', '#a78bfa', '#f472b6', '#2dd4bf', '#94a3b8', '#fb7185', '#4ade80', '#60a5fa'];
  // Graded gray for divergence isolation mode, light → dark. '#3a4452' is the floor: it
  // stays legible above the grid color rgba(27,39,69,0.4). Do not extend darker.
  const DIV_GRAY = ['#9aa6ba', '#8d99ad', '#808ca0', '#737f93', '#667286', '#5a6679', '#4e5a6c', '#434e5f', '#3a4452'];
  const _charts = {};
  function makeLineChart(id, datasets, labels, opts) {
    if (typeof Chart === 'undefined') return;
    if (_charts[id]) { _charts[id].destroy(); }
    const ctx = document.getElementById(id); if (!ctx) return;
    _charts[id] = new Chart(ctx, {
      type: 'line',
      data: { labels, datasets },
      options: Object.assign({
        responsive: true, maintainAspectRatio: false, animation: false,
        interaction: { mode: 'index', intersect: false },
        plugins: { legend: { display: false }, tooltip: { enabled: true } },
        scales: {
          // DEF-V2-TEXT3-CONTRAST / R-IV.495(d) -- Chart.js takes a literal, not a CSS custom
          // property, so this has to be kept in sync with --text-3 (v2.css) by hand. Was
          // #5b6b85 (3.71/3.48/3.35:1, below the 4.5 AA bar); matches the raised token now.
          x: { ticks: { color: '#70829d', maxTicksLimit: 5, font: { size: 9 } }, grid: { color: 'rgba(27,39,69,0.4)' } },
          y: { ticks: { color: '#70829d', font: { size: 9 } }, grid: { color: 'rgba(27,39,69,0.4)' } },
        },
        elements: { point: { radius: 0 }, line: { borderWidth: 1.4, tension: 0.25 } },
      }, opts || {}),
    });
  }

  // ── b2 Sector divergence ────────────────────────────────────────────────────
  let _divWindow = '1d';
  // Isolation-mode selection, by symbol. Module scope on purpose: loadDivergence() rebuilds
  // legend.innerHTML and makeLineChart() destroys the chart on every 10-min refresh, so state
  // kept in the DOM or on the chart object would not survive. Keyed by symbol, not index, so
  // it also survives the sector list changing shape between fetches.
  const _divSel = new Set();
  let _divSectors = [];

  // Last non-null value of a series; null when the series is entirely null.
  function _divFinal(s) {
    const ser = (s && s.series) || [];
    for (let i = ser.length - 1; i >= 0; i--) { if (ser[i] && ser[i].value != null) return Number(ser[i].value); }
    return null;
  }

  // Rank the unselected sectors by final value, descending: lightest gray to the highest,
  // darkest to the lowest. Cycles when unselected count exceeds the ramp. All-null series
  // take the darkest stop.
  function _divGrays(sectors) {
    const ranked = [], nulls = [], map = {};
    sectors.forEach((s) => { if (!_divSel.has(s.symbol)) (_divFinal(s) == null ? nulls : ranked).push(s); });
    ranked.sort((a, b) => _divFinal(b) - _divFinal(a));
    ranked.forEach((s, i) => { map[s.symbol] = DIV_GRAY[i % DIV_GRAY.length]; });
    nulls.forEach((s) => { map[s.symbol] = DIV_GRAY[DIV_GRAY.length - 1]; });
    return map;
  }

  function _divToggle(sym) { if (!sym) return; if (_divSel.has(sym)) _divSel.delete(sym); else _divSel.add(sym); _divRender(); }
  function _divClear() { if (!_divSel.size) return; _divSel.clear(); _divRender(); }

  // The tile shows ranked bars vs SPY (always the 1D window); the old line chart lives in a
  // drawer and only fetches while that drawer is open.
  let _div1d = null, _divOpen = false;
  async function loadDivergence() {
    let d1 = null;
    try { const r = await apiFetch('/api/stable/sector-divergence?window=1d'); if (r.ok) d1 = await r.json(); } catch (_) {}
    _div1d = d1;
    renderSectorBars();
    if (!_divOpen) return;
    let data = d1;
    if (_divWindow !== '1d') {
      data = null;
      try { const r = await apiFetch('/api/stable/sector-divergence?window=' + _divWindow); if (r.ok) data = await r.json(); } catch (_) {}
    }
    const legend = $('divLegend'); if (!legend) return;
    if (!data || !data.sectors || data.degraded) {
      _divSectors = [];
      legend.innerHTML = '<span class="legend-chip val-muted">sector feed unavailable</span>';
      if (_charts.divChart) { _charts.divChart.destroy(); delete _charts.divChart; }
      return;
    }
    _divSectors = data.sectors.filter((s) => s.series && s.series.length);
    _divRender();
  }

  // ── Sectors vs SPY (tile) ────────────────────────────────────────────────────
  // Leadership only shows relative to the market: each sector ETF's 1-day % minus SPY's 1-day %,
  // ranked, as bars from zero capped at ±2 pp. Zero hub cost beyond reads the page already does.
  const SV_CAP = 2.0;
  function renderSectorBars() {
    const el = $('sectorBars'); if (!el) return;
    const d = _div1d, ix = _ixData;
    const asOf = $('divAsOf');
    if (!d || !d.sectors || d.degraded) {
      el.innerHTML = '<div class="sv-msg">Sector feed unavailable — showing no bars (not fake-fresh).</div>';
      if (asOf) asOf.innerHTML = vintageChip({ unknownLabel: 'no reading' });
      return;
    }
    const spyRow = ix && (ix.indices || []).find((r) => r.symbol === 'SPY');
    const spy = spyRow && spyRow.value != null ? Number(spyRow.value) : null;
    const spySuspect = ix && (ix.incoherent || []).includes('SPY');
    if (spy == null || spySuspect) {
      el.innerHTML = `<div class="sv-msg">SPY 1-day % ${spySuspect ? 'is flagged suspect (its own arithmetic does not close)' : 'is unavailable'}, so relative bars are not drawn.</div>`;
      if (asOf) asOf.innerHTML = vintageChip({ unknownLabel: 'no SPY' });
      return;
    }
    const rows = d.sectors.map((s) => {
      const ser = s.series || [];
      let last = null;
      for (let i = ser.length - 1; i >= 0; i--) { if (ser[i] && ser[i].value != null) { last = ser[i]; break; } }
      return last ? { sym: s.symbol, v: Number(last.value) - spy, ts: last.ts } : null;
    }).filter(Boolean).sort((a, b) => b.v - a.v);
    if (!rows.length) { el.innerHTML = '<div class="sv-msg">No sector readings yet.</div>'; return; }
    const lastTs = rows.map((r) => Date.parse(isoUtc(r.ts))).filter(Number.isFinite).sort((a, b) => b - a)[0];
    const spyTs = Date.parse(isoUtc(spyRow.as_of || ix.as_of));
    const mixed = Number.isFinite(lastTs) && Number.isFinite(spyTs) && Math.abs(lastTs - spyTs) > 120e3;
    if (asOf) {
      asOf.innerHTML = mixed
        ? `<span class="vintage-chip" data-state="stale" title="The sector and SPY readings are more than 2 minutes apart, so the gaps mix two moments.">mixed vintage</span>`
        : vintageChip({ iso: Number.isFinite(lastTs) ? new Date(lastTs).toISOString() : null, freshBoundSec: 900, session: d.session });
    }
    const fmt = (v) => (v >= 0 ? '+' : '−') + Math.abs(v).toFixed(2);
    const top = rows[0], bot = rows[rows.length - 1];
    el.innerHTML = `<div class="sv-sum"><span>Leading <b class="val-up">${esc(top.sym)} ${fmt(top.v)}</b></span><span>Lagging <b class="val-down">${esc(bot.sym)} ${fmt(bot.v)}</b></span><span class="val-muted">vs SPY ${fmt(spy)}%</span></div>`
      + rows.map((r) => {
        const w = Math.min(Math.abs(r.v), SV_CAP) / SV_CAP * 50;
        const bar = r.v >= 0 ? `left:50%;width:${w.toFixed(2)}%;background:var(--up)` : `left:${(50 - w).toFixed(2)}%;width:${w.toFixed(2)}%;background:var(--down)`;
        return `<div class="sv-row"><span class="sv-sym" data-chart="${esc(r.sym)}" tabindex="0" role="button">${esc(r.sym)}</span>`
          + `<span class="sv-track"><span class="sv-bar" style="${bar}"></span></span>`
          + `<span class="sv-val num ${signCls(r.v)}">${fmt(r.v)}</span><span class="sv-seam"></span></div>`;
      }).join('')
      + `<div class="sv-leg" title="Bar = sector ETF 1-day % minus SPY 1-day %, capped at ±${SV_CAP} pp. 5-day / 20-day dots and level states (BREAKOUT, LOST 50…) come with a later backend change.">bar = today vs SPY (±${SV_CAP} pp) · click a symbol for its chart</div>`;
  }

  // Pure re-render from _divSectors + _divSel. Called by the fetch and by every selection
  // change, so a click repaints without refetching.
  function _divRender() {
    const legend = $('divLegend'); if (!legend) return;
    const sectors = _divSectors; if (!sectors.length) return;
    // Isolation only when at least one selected symbol is actually in this payload. A sector
    // dropping out of the feed must not strand the tile all-gray with nothing lit; the symbol
    // stays in _divSel, so isolation resumes if it comes back.
    const iso = _divSel.size > 0 && sectors.some((s) => _divSel.has(s.symbol));
    const grays = iso ? _divGrays(sectors) : {};
    let labels = [];
    sectors.forEach((s) => { if (s.series.length > labels.length) labels = s.series.map((p) => (p.ts ? p.ts.slice(11, 16) : (p.date || '').slice(5))); });
    const datasets = sectors.map((s, i) => {
      const own = SECTOR_RAMP[i % SECTOR_RAMP.length];
      const on = !iso || _divSel.has(s.symbol);
      const d = {
        label: s.symbol, borderColor: on ? own : grays[s.symbol], backgroundColor: 'transparent',
        data: s.series.map((p) => (p.value != null ? Number(p.value).toFixed(3) : null)),
      };
      if (iso) d.borderWidth = on ? 2.2 : 0.9;  // omitted in normal mode so the shared default holds
      return d;
    });
    // Everything divergence-specific rides opts. makeLineChart is shared with curveChart and
    // is not touched. Object.assign is shallow, so plugins must be passed whole. The chart's
    // own `interaction` is deliberately left alone — hit-testing uses an explicit mode below,
    // so index-mode tooltips keep behaving exactly as they do today.
    makeLineChart('divChart', datasets, labels, {
      onClick: (evt, _els, chart) => {
        const c = chart || evt.chart; if (!c) return;
        // 'nearest' + intersect:false so a click *near* a line resolves; the chart's own
        // index-mode interaction is left untouched for tooltips.
        const hit = c.getElementsAtEventForMode(evt, 'nearest', { intersect: false }, true);
        if (!hit || !hit.length) return;
        const ds = c.data.datasets[hit[0].datasetIndex]; if (!ds) return;
        // Deferred: _divToggle re-renders, which destroys this chart. Doing that inside
        // Chart.js's own click dispatch tears the instance out from under it.
        setTimeout(() => _divToggle(ds.label), 0);
      },
      plugins: {
        legend: { display: false },
        tooltip: {
          enabled: true,
          filter: (item) => { if (!iso) return true; const s = sectors[item.datasetIndex]; return !!s && _divSel.has(s.symbol); },
        },
      },
    });
    const chips = sectors.map((s, i) => {
      const own = SECTOR_RAMP[i % SECTOR_RAMP.length];
      const on = !iso || _divSel.has(s.symbol);
      const dmaCls = s.above_50dma && s.above_200dma ? 'dma-up' : (s.above_50dma === false && s.above_200dma === false ? 'dma-down' : 'dma-mix');
      const cls = 'legend-chip div-chip' + (iso ? (on ? ' sel' : ' unsel') : '');
      const bg = iso && on ? ` style="background:${own}24"` : '';  // own color at ~14%
      return `<span class="${cls}"${bg} data-sym="${esc(s.symbol)}"><span class="dot" style="background:${on ? own : grays[s.symbol]}"></span>${esc(s.symbol)}<span class="dma ${dmaCls}" data-gloss="DMA"></span></span>`;
    }).join('');
    // "All" is always first and always present — it must not reflow the row on click.
    legend.innerHTML = `<span class="legend-chip div-chip div-all${iso ? '' : ' sel'}" data-all="1">ALL</span>` + chips;
    applyGlossary(legend);
  }

  // ── b4 Index strip ──────────────────────────────────────────────────────────
  async function loadIndexStrip() {
    let data = null, ext = null;
    const getJson = async (u) => { try { const r = await apiFetch(u); return r.ok ? await r.json() : null; } catch (_) { return null; } };
    [data, ext] = await Promise.all([getJson('/api/stable/index-strip'), getJson('/api/stable/futures')]);
    // The Sectors-vs-SPY bars and the Tide cell's closed inference both read this strip.
    _ixData = data;
    _ext = ext;
    renderSectorBars();
    if (_lastRegime.composite || _lastRegime.regime) renderRegimeBand(_lastRegime.composite, _lastRegime.regime, _lastRegime.tide, _lastRegime.kill);
    applyClosedTiles();
    const el = $('indexStrip'); if (!el) return;
    // Outside the regular session (the SERVER's answer) the index bar flips to futures, and
    // flips back at the open, on this same 60 s poll. Unknown session = the normal bar.
    const fut = marketShut() && ext && (ext.futures || []).length > 0;
    el.classList.toggle('fut', !!fut);
    if (fut) { renderFuturesBar(el, ext); return; }
    setIndexHeader(false);
    setDot('indexHealthDot', data && data.data_age_seconds, data ? !!data.degraded : null, data && data.flatline, data && data.session, null, data && data.incoherent);
    noteFlatline('strip', data && data.flatline, 'Index / strip');
    const order = ['SPY', 'QQQ', 'IWM', 'RSP', 'DIA'];
    // A suspect strip escalates the topbar dot. Only escalation is registered here:
    // the strip's routine freshness states stay out of the global roll-up, which is
    // how this tile behaved before, so nothing else on the board changes meaning.
    _health.index = (data && data.incoherent && data.incoherent.length) ? 'suspect' : null;
    updateGlobalHealth();
    const bad = new Set((data && data.incoherent) || []);
    const rows = (data && data.indices) || [];
    const map = {}; rows.forEach((r) => { map[r.symbol] = r; });
    el.innerHTML = order.map((sym) => {
      const r = map[sym]; const pct = r ? r.value : null; const ext = r ? r.atr_ext_50ma : null;
      // A percent the backend could not source arrives as null WITH a reason. It
      // renders as UNAVAILABLE carrying that reason, never as a dash that reads
      // like "flat" and never as a value computed from whatever bars were around.
      const why = r && r.reason ? String(r.reason) : (r ? '' : 'no row served for this symbol');
      // A number whose own arithmetic does not close is shown, but never shown plain:
      // the reader must be able to see that the board does not stand behind it.
      const sus = bad.has(sym);
      const susWhy = sus && r ? `SUSPECT — ${pct}% does not equal ${r.extra} / ${r.prior_close} - 1. Do not trade off this.` : '';
      const chg = pct != null
        ? `<span class="chg ${signCls(pct)}${sus ? ' ix-suspect' : ''}"${sus ? ` title="${esc(susWhy)}"` : ''}>${(pct >= 0 ? '+' : '') + Number(pct).toFixed(2)}%${sus ? ' ?' : ''}</span>`
        : `<span class="chg ix-unavail" title="${esc(why)}">UNAVAILABLE</span>`;
      return `<div class="ix-cell" data-ticker="${sym}" data-chart="${sym}" tabindex="0" role="button"${pct == null ? ` title="${esc(why)}"` : ''}><span class="sym">${sym}</span>`
        + chg
        + `<span class="ext">${ext != null ? (ext >= 0 ? '+' : '') + Number(ext).toFixed(1) + ' ATR' : ''}</span></div>`;
    }).join('');
  }

  // ── b4b Futures bar (outside the regular session) ─────────────────────────────
  // Each percent is measured from the price at 4 PM ET of `base_session` (the stock close,
  // not the exchange settlement), ~10 min delayed. Chart symbols are TradingView's
  // continuous front-month contracts.
  const FUT_SHORT = { 'ES=F': 'ES', 'NQ=F': 'NQ', 'RTY=F': 'RTY', 'YM=F': 'YM', 'CL=F': 'CRUDE', 'ZN=F': '10Y' };
  const FUT_CHART = { 'ES=F': 'ES1!', 'NQ=F': 'NQ1!', 'RTY=F': 'RTY1!', 'YM=F': 'YM1!', 'CL=F': 'CL1!', 'ZN=F': 'ZN1!' };
  const EXT_WORD = { pre_market: 'pre', after_hours: 'after' };
  // R-IV.611(b)1: every stamp goes through riverTime(), which adds the weekday or the date when
  // the stamp is not today — so a futures bar from yesterday says so instead of reading as this
  // afternoon. apiTime() subsumes isoUtc(): both read an offset-less string as UTC.
  const fmtMT = (iso) => riverTime(apiTime(iso)) || '';
  // "Tue" for a YYYY-MM-DD session date (a date label only; noon UTC keeps it on its day).
  const sessionDay = (d) => { try { return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', weekday: 'short' }).format(new Date(d + 'T12:00:00Z')); } catch (_) { return d; } };
  function setIndexHeader(fut, sub) {
    const t = $('indexTitle'), s = $('indexSub');
    if (t) { t.textContent = fut ? 'Futures' : 'Index'; t.setAttribute('data-gloss', fut ? 'FUTURES' : 'INDEX'); applyGlossary(t.parentNode); }
    if (s) s.textContent = fut ? (sub || '') : '';
  }
  function renderFuturesBar(el, ext) {
    const etf = {}; (ext.etfs || []).forEach((r) => { etf[r.symbol] = r; });
    const base = ext.base_session_expected || ((ext.futures || [])[0] || {}).base_session;
    const stale = (ext.stale_base || []).length > 0;
    setIndexHeader(true, (base ? 'since ' + sessionDay(base) + ' 4 PM ET' : 'since the 4 PM ET close')
      + ' · ~' + (ext.data_delay_minutes || 10) + ' min delayed' + (stale ? ' · updating' : ''));
    // The feed's stated delay is not staleness: the dot ages from the end of that delay.
    const delay = (ext.data_delay_minutes || 0) * 60;
    const age = ext.data_age_seconds != null ? Math.max(0, ext.data_age_seconds - delay) : null;
    setDot('indexHealthDot', age, !!ext.degraded, ext.flatline, ext.session, null, null);
    noteFlatline('ext_hours', !!ext.flatline, 'Overnight futures');
    _health.index = null;
    updateGlobalHealth();
    el.innerHTML = (ext.futures || []).map((f) => {
      const pct = f.pct;
      const waiting = /^waiting/.test(f.reason || '');
      const oldBase = base && f.base_session && f.base_session !== base;
      const chg = pct != null
        ? `<span class="chg ${signCls(pct)}">${fmtPct(pct)}</span>`
        : `<span class="chg ix-unavail" title="${esc(f.reason || 'no reading')}">${waiting ? 'WAITING' : 'UNAVAILABLE'}</span>`;
      const e = f.leads ? etf[f.leads] : null;
      const sub = e && e.pct != null ? `${esc(e.symbol)} ${EXT_WORD[e.ext_session] || 'ext'} ${fmtPct(e.pct)}` : esc(f.label || '');
      const path = sparkPath((f.spark || []).map((v) => ({ value: v })), 100, 14);
      const col = pct > 0 ? 'var(--up)' : pct < 0 ? 'var(--down)' : 'var(--text-3)';
      const title = `${f.label} futures${f.last != null ? ' ' + f.last : ''}`
        + (f.base != null ? ` vs ${f.base} at the ${f.base_session} 4 PM ET close` : '')
        + (f.bar_ts ? ` · last bar ${fmtMT(f.bar_ts)}` : '')
        + (oldBase ? ` · still measured from ${f.base_session}; refreshes within 5 min` : '')
        + (e && e.pct != null ? ` · ${e.symbol} ${e.ext_session === 'pre_market' ? 'pre-market' : 'after-hours'} ${e.last} vs ${e.base} close` : '');
      return `<div class="ix-cell fut-cell" data-chart="${esc(FUT_CHART[f.symbol] || '')}" tabindex="0" role="button" title="${esc(title)}">`
        + `<div class="fut-txt"><span class="sym">${esc(FUT_SHORT[f.symbol] || f.symbol)}</span>${chg}<span class="ext">${sub}</span></div>`
        + (path ? `<svg class="fut-spark" viewBox="0 0 100 14" preserveAspectRatio="none" aria-hidden="true"><path d="${path}" fill="none" stroke="${col}" stroke-width="1.4" vector-effect="non-scaling-stroke"/></svg>` : '')
        + '</div>';
    }).join('');
  }

  // ── Market-closed tiles ─────────────────────────────────────────────────────
  // Tiles whose feeds run in regular hours only (strip / movers / scanner jobs). Outside the
  // session they hold the last reading, so they say so instead of looking live. Nightly
  // tiles (Themes, Breadth) update after the close and are NOT listed; the River keeps
  // receiving news; the Book is out of scope. R-IV.527: no opacity dimming (it fails AA) —
  // a greyscale body, a dashed neutral border and a full-strength tag.
  const CLOSED_TILES = ['movers-tape', 'divergence', 'curve', 'usd', 'kairos'];
  const CLOSED_WORD = { pre_market: 'PRE-MARKET', after_hours: 'AFTER HOURS', closed: 'CLOSED' };
  function applyClosedTiles() {
    const s = serverSession();
    const shut = s != null && s !== 'regular';
    const since = _ixData && _ixData.as_of ? fmtMT(_ixData.as_of) : '';
    CLOSED_TILES.forEach((id) => {
      const it = document.querySelector(`#v2Grid > .grid-stack-item[gs-id="${id}"]`);
      if (!it) return;
      it.classList.toggle('tile-closed', shut);
      const hdr = it.querySelector('.tile-header'); if (!hdr) return;
      let tag = hdr.querySelector('.closed-tag');
      if (!shut) { if (tag) tag.remove(); return; }
      if (!tag) {
        tag = document.createElement('span'); tag.className = 'closed-tag';
        const title = hdr.querySelector('.tile-title');
        if (title && title.nextSibling) hdr.insertBefore(tag, title.nextSibling); else hdr.appendChild(tag);
      }
      tag.textContent = CLOSED_WORD[s] || 'CLOSED';
      tag.title = id === 'kairos'
        ? 'Outside the regular session (server calendar). New setups are held until the open.'
        : 'Outside the regular session (server calendar). This feed updates only in market hours; it shows the last reading'
          + (since ? ' (market feeds last wrote ' + since + ')' : '') + '. The Futures bar is live.';
    });
  }

  // ── b5 Yield curve mini ─────────────────────────────────────────────────────
  async function loadRates() {
    let data = null;
    try { const r = await apiFetch('/api/stable/rates'); if (r.ok) data = await r.json(); } catch (_) {}
    const vals = $('curveVals'); if (!vals) return;
    if (!data || !data.curve_points) { vals.innerHTML = '<span class="val-muted">rates unavailable</span>'; return; }
    const order = ['3M', '5Y', '10Y', '30Y'];
    const cp = data.curve_points || {}, ghost = data.curve_points_5d_ago || null;
    const yieldsBySym = {}; (data.yields || []).forEach((y) => { yieldsBySym[y.symbol] = y; });
    const labels = order.filter((s) => cp[s] != null);
    const datasets = [{ label: 'now', borderColor: '#14b8a6', backgroundColor: 'transparent', data: labels.map((s) => cp[s]) }];
    if (ghost) datasets.push({ label: '5d ago', borderColor: 'rgba(139,152,173,0.5)', borderDash: [4, 3], backgroundColor: 'transparent', data: labels.map((s) => ghost[s] != null ? ghost[s] : null) });
    makeLineChart('curveChart', datasets, labels);
    vals.innerHTML = order.map((s) => {
      const y = yieldsBySym[s]; const v = cp[s]; const bp = y ? y.day_change : null;
      return `<span class="mv"><span class="k">${s}</span><span class="v">${v != null ? Number(v).toFixed(2) + '%' : '--'}</span>${bp != null ? `<span class="bp ${signCls(bp)}">${bp >= 0 ? '+' : ''}${Number(bp).toFixed(1)}bp</span>` : ''}<span data-tenor="${s}"></span></span>`;
    }).join('');
  }

  // ── B3: the FRED curve block (R-IV.1220(b)) ───────────────────────────────
  //
  // EVERY LABEL CARRIES ITS MEASURED FIRES PER YEAR, which is the ruling's own requirement
  // and the reason the tooltip is assembled by the BACKEND rather than here: the figure is a
  // measurement over that series' history, not a constant, and a second copy of the sentence
  // in JS would drift from the number it describes.
  //
  // EXTREME pulses, UNUSUAL does not. "RARE" is retired (R-IV.1220(b)).
  function ycChip(b) {
    if (!b || !b.label) return '';
    const cls = b.label === 'EXTREME' ? 'yc-extreme' : 'yc-unusual';
    return '<span class="yc-lab ' + cls + (b.pulse ? ' yc-pulse' : '') + '" title="'
      + esc(b.tooltip || '') + '">' + esc(b.label) + '</span>';
  }

  function ycSpark(spark) {
    if (!spark || spark.length < 2) return '';
    const w = 72, h = 18;
    const min = Math.min.apply(null, spark), max = Math.max.apply(null, spark);
    const rng = (max - min) || 1, step = w / (spark.length - 1);
    const d = spark.map((v, i) =>
      (i ? 'L' : 'M') + (i * step).toFixed(1) + ',' + (h - ((v - min) / rng) * h).toFixed(1)
    ).join(' ');
    // The zero line is drawn only when zero is INSIDE the range: a baseline outside the data
    // would sit on the edge of the box and read as the series touching zero.
    const zero = (min < 0 && max > 0)
      ? '<line x1="0" y1="' + (h - ((0 - min) / rng) * h).toFixed(1) + '" x2="' + w
        + '" y2="' + (h - ((0 - min) / rng) * h).toFixed(1) + '" class="yc-zero"/>'
      : '';
    return '<svg class="yc-spark" viewBox="0 0 ' + w + ' ' + h + '" width="' + w
      + '" height="' + h + '" aria-hidden="true">' + zero
      + '<path d="' + d + '"/></svg>';
  }

  // R-IV.1251: THE BOX WENT BLANK DURING RTH, and the cause was a race nobody owned.
  //
  // `loadRegimeBand` REBUILDS the band's innerHTML — this box's markup included — on its own
  // 60-second timer, and `refreshMarket` FILLS the box on a SECOND, independent 60-second
  // timer. Whenever the band repaints after the fill, the box is left holding its empty
  // template until the next fill tick: a title, an em dash and nothing. That is exactly the
  // screenshot. B3 made it worse rather than causing it, by adding an `ycHeads` element that
  // starts empty and a second sequential await after the rebuild.
  //
  // THE FIX IS NOT A LONGER TIMER OR A RETRY. The payload is cached here and ONE painter draws
  // from the cache — called after every fetch AND immediately after every band rebuild, so the
  // box is repainted in the same tick its DOM is recreated, from data already in hand, with no
  // network wait. A box that can only be correct between two timers is a box that is
  // sometimes wrong.
  let _ycData = null;

  async function loadYieldCurve() {
    try {
      const r = await apiFetch('/api/yield-curve');
      if (r.ok) _ycData = await r.json();
    } catch (_) { /* the cache keeps the last good payload rather than blanking the box */ }
    paintYieldCurve();
  }

  function paintYieldCurve() {
    const d = _ycData;
    const shape = $('ycShape'), flag = $('ycFlag'), heads = $('ycHeads');
    if (!heads) return;
    // (e) R-IV.1246: OUTSIDE RTH the box shows the LAST AVAILABLE values at reduced opacity
    // with a CLOSED chip, matching USD CARRY. The session comes from the server's own answer
    // (`marketShut()`, which reads the server's own `market_session`) and NOT from the
    // browser's clock: a laptop in the wrong timezone would dim the box mid-session, and a
    // holiday would not dim it at all. R-IV.416(c) already made that a rule for this page.
    //
    // MY FIRST VERSION READ `_mktSession`, WHICH DOES NOT EXIST -- the second invented-name
    // fault of this session after `database.connection`. An undefined identifier here throws
    // and the whole tile stops rendering, so it is worth saying out loud: the accessor is
    // `serverSession()` / `marketShut()`, and unknown is NOT closed.
    //
    // THE VALUES STAY. Blanking them would lose the last close, which is exactly what a reader
    // wants outside the session; dimming says "not updating" without hiding it.
    const box = $('rbCurve');
    const closed = marketShut();
    if (box) box.classList.toggle('yc-closed', !!closed);
    // R-IV.1251(b): NEVER BLANK. With no payload at all it says so and names the route; with
    // a payload whose individual tenors failed, each ROW names its own series and reason
    // below. A reader can act on "5Y (DGS5) returned no usable observation" and cannot act on
    // a gap.
    if (!d || d.error || !d.spreads) {
      heads.innerHTML = '<span class="val-muted">yield curve unavailable — '
        + esc(d && d.error ? d.error : 'no reading yet from /api/yield-curve')
        + '</span>';
      if (shape) {
        shape.textContent = '—';
        shape.title = 'the FRED read has not returned a curve';
      }
      return;
    }
    if (closed && flag) {
      // The CLOSED chip replaces the UN-INVERTED flag's slot rather than crowding it: both
      // are single chips in the header, and the session fact outranks the flag outside hours.
      flag.textContent = 'CLOSED · as of ' + (d.as_of || '—');
      flag.title = 'outside the regular session (server calendar); these are the last '
        + 'available FRED values, as of ' + (d.as_of || 'an unknown date');
      flag.style.display = '';
      flag.className = 'yc-flag yc-flag-closed';
    }
    if (shape) {
      shape.textContent = (d.shape && d.shape.word) || '—';
      shape.title = (d.shape && d.shape.basis ? d.shape.basis + ' · ' : '')
        + 'as of ' + (d.as_of || 'unknown') + ' (FRED)';
      shape.className = 'yc-shape' + (d.shape && d.shape.word === 'INVERTED' ? ' yc-inv' : '');
    }
    const ui = (d.spreads['2s10s'] && d.spreads['2s10s'].un_inverted)
      || (d.spreads['3m10s'] && d.spreads['3m10s'].un_inverted);
    if (flag && !closed) {
      flag.textContent = ui ? ui.flag : '';
      flag.title = ui ? ui.basis : '';
      flag.style.display = ui ? '' : 'none';
      flag.className = 'yc-flag';
    }
    // (c) THE TENOR ROWS: 3M, 2Y, 5Y, 10Y, 30Y, each with its level and today's change in bp,
    // and UNUSUAL/EXTREME TINTING THE TENOR'S LABEL rather than sitting beside it. All five
    // come from /api/yield-curve, which is why 2Y has a row at last: the box drew its table
    // from /api/stable/rates (3M/5Y/10Y/30Y) while the labels came from the FRED route
    // (3M/2Y/10Y/30Y), so the two lists disagreed about which tenors the curve even has.
    const tenors = (d.tenors || []);
    // R-IV.1257(c): THE INTRADAY OVERLAY, beside the FRED figure and never instead of it. The
    // tick is styled apart and captioned "intra" so the two numbers on a row can never be read
    // as one: the FRED level is a settled close, the tick is not settled at all.
    //
    // Styled INLINE rather than through v2.css, which is pinned independently by v2.html,
    // stater.html and abacus.html at three already-diverged values -- a rule added there ships
    // three times or reaches a stale cache on the pages that were missed.
    const intra = (d.intraday && d.intraday.tenors) || {};
    const intraCell = (tenor) => {
      const b = intra[tenor];
      if (!b) return '';
      if (!b.verified) {
        // The ABSENCE IS SHOWN, not swallowed: 2Y has no intraday symbol at all, and a row
        // that silently lacked the tick would read as "unchanged today" (R-IV.1251(b), one
        // row down). No substitution, so the reason is the content.
        return '<span style="font-size:10px;color:#5d6b82;letter-spacing:.3px" title="'
          + esc(b.reason || 'no intraday reading') + '">FRED only</span>';
      }
      if (b.change_bp == null) return '';
      const sign = b.change_bp >= 0 ? '+' : '';
      return '<span style="font-size:10px;color:#8b98ad;letter-spacing:.3px" title="'
        + esc('intraday ' + (b.symbol || '') + ' (' + (b.vendor_name || 'unnamed')
              + '), 15-minute bars, today’s session only, as of '
              + (b.as_of || 'unknown') + ' — an unsettled tick, NOT a settled close; the '
              + '% beside it is FRED’s settled figure') + '">intra ' + sign
        + Number(b.change_bp).toFixed(1) + 'bp</span>';
    };
    // R-IV.1363(c): DURING MARKET HOURS THE HEADLINE IS THE LIVE YIELD, NOT FRED'S CLOSE.
    //
    // WHAT NICK SAW, measured at 13:37Z on 2026-10-23, seven minutes after the open. The box
    // showed `10Y 5.13%` as its biggest number with NO DATE ANYWHERE ON ITS FACE, because the
    // `CLOSED . as of <date>` chip only appears outside the session. 5.13% was FRED's
    // 2026-10-21 close. FRED had not yet published 10-22 (H.15 publishes the next business day
    // in the late ET afternoon), and on 10-22 the 10Y had fallen about 18bp: the live market
    // was at 4.965 and the box said 5.13, a 16.5bp gap, with nothing on screen to say the
    // number was two sessions old. He watches bond yields all day; of course it read as broken.
    //
    // The intraday tick was present and correct the whole time -- it was just rendered as a
    // small "intra -1.3bp" caption beside a large stale level. The data was never the problem;
    // the HIERARCHY was. So the two swap places while the session is open.
    //
    // THE TWO FIGURES ARE NEVER MERGED (R-IV.1257(c)). Each carries its own number, its own
    // change and its own timestamp: the live tick with its TIME, FRED's close with its DATE.
    // A reader can always tell which is which, and neither is ever computed from the other.
    //
    // LABELS AND Z-SCORES STAY ON FRED, per the ruling. `t.label`, `t.pulse` and the tooltip
    // are unchanged and still tint the tenor key -- an UNUSUAL/EXTREME call is a statement
    // about a settled series, and recomputing it on an unsettled tick would be a different
    // claim wearing the same word.
    // WHICH TENORS MAY TAKE THE LIVE HEADLINE, and this is MEASURED, not assumed. A tick may
    // only replace a FRED level if the two are on the SAME BASIS -- otherwise the headline
    // would change basis at every open and close, which is a new false alarm on the very box
    // this ruling is fixing.
    //
    // Measured 2026-10-23 over the six sessions 10-14..10-21, FRED minus Yahoo, in bp:
    //
    //    DGS5  vs ^FVX   mean +0.1   range -2.2 .. +1.1
    //    DGS10 vs ^TNX   mean +0.1   range -1.6 .. +1.4
    //    DGS30 vs ^TYX   mean -0.4   range -1.9 .. +0.8
    //    DGS3MO vs ^IRX  mean +19.0  range +18.0 .. +19.5   <-- EVERY SINGLE DAY
    //
    // The long end agrees to under 2bp: same quantity, so the tick is comparable and may
    // lead. **^IRX is the 13-week bill DISCOUNT rate and DGS3MO is a bond-equivalent yield**
    // -- a structural ~19bp difference, not staleness. Promoting it would drop the 3M row
    // 19bp at every open and jump it back at every close. So 3M keeps FRED as its headline
    // (with its date, which is the part that was missing) and its tick stays a caption.
    //
    // This NARROWS R-IV.1363(c) by one tenor and is reported as such. It serves the ruling's
    // purpose rather than bending it: (c) exists so the box stops showing a number the market
    // has left, and an ^IRX headline would show a number the market was never at on FRED's
    // basis. The right long-term home for this is the symbol map in the hub, beside the
    // vendor-name verification, not a constant in the view.
    const LIVE_HEADLINE_OK = { "5Y": true, "10Y": true, "30Y": true };

    const etTime = (iso) => {
      try {
        return new Intl.DateTimeFormat('en-GB', {
          timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false,
        }).format(new Date(iso)) + ' ET';
      } catch (_) { return ''; }
    };
    const fredAside = (t) => {
      // FRED'S DATE IS NOW ALWAYS ON THE FACE, in every state, which is the part that was
      // actually missing. Even where FRED remains the headline (the 2Y, or outside hours) the
      // row says WHEN that close is from.
      const chg = t.change_bp;
      const when = t.as_of ? ' \u00b7 ' + esc(String(t.as_of).slice(5)) : '';
      return '<span style="font-size:10px;color:#8b98ad;letter-spacing:.2px" title="'
        + esc('FRED ' + (t.series || '') + ' settled close, as of ' + (t.as_of || 'unknown')
              + '. The official level: labels and z-scores are computed on this series, never '
              + 'on the intraday tick beside it.')
        + '">FRED ' + Number(t.level_pct).toFixed(2) + '%'
        + (chg == null ? '' : (chg >= 0 ? ' +' : ' ') + Number(chg).toFixed(1) + 'bp')
        + when + '</span>';
    };
    const tenorRows = tenors.map((t) => {
      const tint = t.label === 'EXTREME' ? ' yc-t-extreme'
        : (t.label === 'UNUSUAL' ? ' yc-t-unusual' : '');
      if (t.level_pct == null) {
        return '<div class="yc-tr"><span class="yc-tk' + tint + '">' + esc(t.tenor)
          + '</span><span class="yc-tv rd-na-inline" title="'
          + esc(t.unavailable_reason || '') + '">unavailable</span></div>';
      }
      const b = intra[t.tenor];
      // THE LIVE HEADLINE NEEDS THE SESSION *AND* A VERIFIED TICK. `marketShut()` answers from
      // the server's own calendar and UNKNOWN IS NOT CLOSED, so `!closed` alone would promote a
      // stale tick to the headline on an unknown session -- which is why the time is rendered
      // beside the number in every case rather than only when it looks wrong.
      const liveHead = !closed && LIVE_HEADLINE_OK[t.tenor]
        && b && b.verified && b.last_pct != null;
      if (liveHead) {
        const ic = b.change_bp;
        return '<div class="yc-tr" title="' + esc(t.tooltip || '') + '">'
          + '<span class="yc-tk' + tint + (t.pulse ? ' yc-pulse' : '') + '">'
          + esc(t.tenor) + '</span>'
          + '<span class="yc-tv" title="'
          + esc('live intraday ' + (b.symbol || '') + ' (' + (b.vendor_name || 'unnamed')
                + '), 15-minute bars, as of ' + (b.as_of || 'unknown')
                + ' \u2014 an UNSETTLED tick, not a settled close. FRED\u2019s settled figure '
                + 'is beside it with its own date.')
          + '">' + Number(b.last_pct).toFixed(2) + '%</span>'
          + (ic == null ? '' : '<span class="yc-tc ' + signCls(ic) + '">'
            + (ic >= 0 ? '+' : '') + Number(ic).toFixed(1) + 'bp</span>')
          + '<span style="font-size:10px;color:#5d6b82;letter-spacing:.2px">'
          + esc(etTime(b.as_of)) + '</span>'
          + fredAside(t)
          + '</div>';
      }
      // FRED stays the headline: outside the session, or where there is no intraday symbol at
      // all (the 2Y). `intraCell` keeps saying WHY the tick is absent rather than leaving a gap
      // that reads as "unchanged today".
      const chg = t.change_bp;
      return '<div class="yc-tr" title="' + esc(t.tooltip || '') + '">'
        + '<span class="yc-tk' + tint + (t.pulse ? ' yc-pulse' : '') + '">'
        + esc(t.tenor) + '</span>'
        + '<span class="yc-tv">' + Number(t.level_pct).toFixed(2) + '%</span>'
        + (chg == null ? '' : '<span class="yc-tc ' + signCls(chg) + '">'
          + (chg >= 0 ? '+' : '') + Number(chg).toFixed(1) + 'bp</span>')
        + (t.as_of ? '<span style="font-size:10px;color:#5d6b82;letter-spacing:.2px" title="'
            + esc('FRED settled close, as of ' + t.as_of) + '">'
            + esc(String(t.as_of).slice(5)) + '</span>' : '')
        + intraCell(t.tenor)
        + '</div>';
    }).join('');
    // The chart: a dot per tenor now, and a DASHED line for a month ago (c). Drawn from the
    // same five tenors as the rows, so the two cannot disagree about the curve's shape.
    const drawn = tenors.filter((t) => t.level_pct != null);
    if (drawn.length) {
      const sets = [{ label: 'now', borderColor: '#14b8a6', backgroundColor: '#14b8a6',
                      pointRadius: 3, data: drawn.map((t) => t.level_pct) }];
      const ago = drawn.map((t) => (t.month_ago_pct == null ? null : t.month_ago_pct));
      // Only when a month of history exists. A dashed line drawn on top of the solid one
      // would say "unchanged in a month", which is a claim.
      if (ago.some((v) => v != null)) {
        sets.push({ label: '1 month ago', borderColor: 'rgba(139,152,173,0.65)',
                    borderDash: [4, 3], backgroundColor: 'transparent', pointRadius: 0,
                    data: ago });
      }
      // R-IV.1257(c): the intraday curve as a THIRD series, dotted, and only when at least two
      // tenors verified. One verified tenor is a point, not a curve, and a one-point line drawn
      // across five labels would imply four readings that do not exist. The 2Y gap stays a gap:
      // Chart.js skips a null rather than bridging it, which is the honest rendering of "no
      // intraday symbol for this tenor".
      const tick = drawn.map((t) => {
        const b = intra[t.tenor];
        return (b && b.verified && b.last_pct != null) ? b.last_pct : null;
      });
      if (tick.filter((v) => v != null).length >= 2) {
        sets.push({ label: 'intraday (unsettled)', borderColor: 'rgba(94,234,212,0.75)',
                    borderDash: [2, 2], backgroundColor: 'transparent', pointRadius: 2,
                    spanGaps: false, data: tick });
      }
      makeLineChart('curveChart', sets, drawn.map((t) => t.tenor));
    }
    const spreadRows = ['3m10s', '2s10s'].map((k) => {
      const b = d.spreads[k]; if (!b) return '';
      const bp = b.bp == null ? '--' : (b.bp > 0 ? '+' : '') + b.bp.toFixed(0);
      const ch = b.change_bp == null ? '' : '<span class="yc-ch ' + signCls(b.change_bp) + '">'
        + (b.change_bp >= 0 ? '+' : '') + b.change_bp.toFixed(1) + 'bp</span>';
      return '<div class="yc-head' + (b.inverted ? ' yc-inv' : '') + '">'
        + '<span class="yc-k">' + esc(k) + '</span>'
        + '<span class="yc-bp" title="' + esc(b.tooltip || '') + '">' + bp + 'bp</span>'
        + ch + ycChip(b)
        + '<span class="yc-sp" title="' + (b.spark_sessions || 0)
        + ' sessions, FRED ' + esc(b.series || '') + '">' + ycSpark(b.spark) + '</span>'
        + '</div>';
    }).join('');
    // (c)'s order: the tenor rows, the chart (drawn into its own canvas above), then the two
    // spreads BELOW them.
    heads.innerHTML = '<div class="yc-tenors">' + tenorRows + '</div>'
      + '<div class="yc-spreads">' + spreadRows + '</div>';
  }

  // ── b6 USD carry mini ───────────────────────────────────────────────────────
  function sparkPath(series, w, h) {
    if (!series || series.length < 2) return '';
    const vals = series.map((p) => Number(p.value)).filter((v) => Number.isFinite(v));
    if (vals.length < 2) return '';
    const min = Math.min(...vals), max = Math.max(...vals), rng = (max - min) || 1;
    const step = w / (vals.length - 1);
    return vals.map((v, i) => `${i === 0 ? 'M' : 'L'}${(i * step).toFixed(1)},${(h - ((v - min) / rng) * h).toFixed(1)}`).join(' ');
  }
  async function loadFx() {
    let data = null;
    try { const r = await apiFetch('/api/stable/fx'); if (r.ok) data = await r.json(); } catch (_) {}
    const el = $('fxWrap'); if (!el) return;
    const fx = (data && data.fx) || [];
    if (!fx.length) { el.innerHTML = '<span class="val-muted">FX unavailable</span>'; return; }
    el.innerHTML = fx.map((f) => {
      const chg = f.day_change_pct; const lvl = f.level;
      const path = sparkPath(f.series, 120, 24);
      const col = chg > 0 ? '#7CFF6B' : chg < 0 ? '#ff5c33' : '#8b98ad';
      return `<div class="fx-row"><span class="sym">${esc(f.symbol)}</span>`
        + `<span class="spark">${path ? `<svg width="100%" height="24" viewBox="0 0 120 24" preserveAspectRatio="none"><path d="${path}" fill="none" stroke="${col}" stroke-width="1.4"/></svg>` : ''}</span>`
        + `<span class="val">${lvl != null ? Number(lvl).toFixed(2) : '--'}</span>`
        + `<span class="chg ${signCls(chg)}">${chg != null ? (chg >= 0 ? '+' : '') + Number(chg).toFixed(2) + '%' : ''}</span></div>`;
    }).join('');
  }

  // ── b7 Book strip ───────────────────────────────────────────────────────────
  async function loadBook() {
    let balances = null, pnl = null, greeks = null, positions = null;
    try { const r = await apiFetch('/api/portfolio/balances'); if (r.ok) balances = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/portfolio/pnl'); if (r.ok) pnl = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/v2/positions/greeks'); if (r.ok) greeks = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/v2/positions?status=OPEN'); if (r.ok) positions = await r.json(); } catch (_) {}
    setBookExits(positions);
    noteAccounts(positions, balances);
    const el = $('bookStrip'); if (!el) return;
    const bookOk = !!(balances || pnl);
    const accts = Array.isArray(balances) ? balances : [];
    // R-IV.416(c) — no fabricated age (the old `bookOk ? 60 : null` asserted "fresh" for any
    // non-empty read), and no borrowed one either. account_balances.updated_at is NOT the
    // Balance's vintage: the position write path stamps it on cash-only adjustments
    // (unified_positions.py, `SET cash = cash + $1, updated_at = NOW()`) without re-reading
    // balance, so a fresh stamp can sit on a weeks-old balance. No field records when the
    // balance itself was read, so the age is unknown -> unconfirmed. The title still names
    // the row touched longest ago (R-IV.420(d) interim). /pnl carries no age of its own.
    const touched = accts.map((a) => ({ name: a.account_name, t: Date.parse(a.updated_at) }))
      .filter((a) => Number.isFinite(a.t)).sort((x, y) => x.t - y.t);
    const oldest = touched.length ? touched[0] : null;
    const bookNote = 'balance vintage not recorded'
      + (oldest ? '; row touched longest ago: ' + (oldest.name || '?') + ' at ' + new Date(oldest.t).toISOString().slice(0, 16) + 'Z' : '');
    setDot('bookHealthDot', null, bookOk ? false : null, false, null, bookNote);
    // The RANK ignores age, as themes does (4c76c5c): balances are not a streaming feed, so
    // a 900s bound would pin the global dot amber all day. The tile's own dot still shows
    // the honest age; the bound the book should be judged by is not yet ruled.
    _health.book = bookOk ? 'ok' : 'unconfirmed'; updateGlobalHealth();

    // R-IV.440(a) — the BALANCE is the tradeable book. Scope comes from the payload
    // (`in_scope`, set from config.accounts, the same vocabulary the MCP tool uses); this
    // file never keeps its own list of account names. If no row carries the field the
    // backend is older than this page: sum everything and SAY the scope is unknown rather
    // than publishing a total whose membership we cannot state.
    const scoped = accts.filter((a) => a.in_scope === true);
    const scopeKnown = accts.some((a) => typeof a.in_scope === 'boolean');
    const counted = scopeKnown ? scoped : accts;
    // R-IV.1262(b)2. The 0.00 this ruling names is `balance_stored`, which the route RETIRED and
    // does not serve as current (R-IV.560) -- so no zero reaches this tile, and my R-IV.1255 report
    // was wrong to imply one did. What the route DOES serve for FID 401A is a DERIVED 11,346.92
    // carrying `balance_partial: true` and a reason saying 2 positions could not be valued, "so
    // this figure is PARTIAL and understates the account" -- and this tile has been rendering that
    // as a plain dollar figure. An understated balance read as whole is the same failure the
    // ruling is about, so it is what gets fixed here.
    //
    // A row with NO balance renders "not recorded", never 0: a null is unknown and a zero is a
    // claim that the account is empty.
    const hasBal = (a) => a && a.balance != null;
    // R-IV.1382(d)2: the floor rule lives in ONE function, which the Positions panel's account
    // strip calls too -- so the tile and the panel cannot disagree about whether a total is whole.
    // A sum over partial parts is a FLOOR, exactly as the greeks below are. Same word, same mark.
    const bt = bookTotalOf(counted);
    const total = bt.total, balMissing = bt.missing, balPartial = bt.partial, balFloor = bt.floor;
    const day = pnl && pnl.daily ? pnl.daily : {};


    // ── DEF-GREEKS-ZERO ────────────────────────────────────────────────────────
    // A sum built from some of the legs is a FLOOR, not a total. Unavailable
    // greeks render N/A, never 0 and never a bare "--" that reads as flat —
    // an understated delta says the operator carries LESS risk than he does.
    const gTotals = (greeks && greeks.totals) || {};
    const gCov = (greeks && greeks.coverage) || null;
    const gPer = (gCov && gCov.per_greek) || {};
    const gUnreachable = !greeks;
    // ── (b) Day P&L never renders a number when nothing is priced ────────────────
    // A zero on the most-read figure in the app is the fake-fresh rule broken: it is
    // indistinguishable from a real flat day. When no leg is priced there is no
    // measurement, so the line says UNAVAILABLE and names the reason the source gave.
    const covLegs = gCov ? (gCov.legs_expected || 0) : 0;
    const covPriced = gCov ? (gCov.legs_priced || 0) : 0;
    const gStatus = greeks && greeks.status ? String(greeks.status) : null;
    const MARK_REASON = {
      no_api_key: 'marks unavailable — no vendor key',
      unavailable: 'marks unavailable — vendor unavailable',
      db_error: 'marks unavailable — database error',
      computation_error: 'marks unavailable — computation error',
    };
    let dayUnavailable = null;
    if (!pnl) dayUnavailable = 'source unreachable';
    else if (day.dollar == null) dayUnavailable = 'not reported';
    else if (gUnreachable) dayUnavailable = 'marks unavailable — greeks source unreachable';
    else if (gStatus && MARK_REASON[gStatus]) dayUnavailable = MARK_REASON[gStatus];
    else if (covLegs > 0 && covPriced === 0) dayUnavailable = 'no marks — 0 of ' + covLegs + ' legs priced';
    // The vintage of the Day P&L is not recorded anywhere (R-IV.420(d)); say so rather than
    // let an unlabelled figure read as current.
    const dayChip = vintageChip({
      unknownLabel: 'vintage not recorded',
      unknownTitle: dayUnavailable || 'no field records when this was computed',
    });
    const dayCell = dayUnavailable
      ? `<span class="v val-amber">UNAVAILABLE <span class="book-reason">${esc(dayUnavailable)}</span> ${dayChip}</span>`
      : `<span class="v ${signCls(day.dollar)}">${(day.dollar >= 0 ? '+' : '') + fmt$(day.dollar)}${day.pct != null ? ` <span style="font-size:10px">(${day.pct >= 0 ? '+' : ''}${Number(day.pct).toFixed(2)}%)</span>` : ''} ${dayChip}</span>`;
    const greekCell = (sym, name, decimals) => {
        const v = gTotals[name];
        if (gUnreachable || v == null) {
            return `<span class="g"><span class="k">${sym}</span><span class="g-na">N/A</span></span>`;
        }
        const c = gPer[name] || {};
        const exact = gCov && c.expected > 0 && c.priced === c.expected;
        const num = Number(v).toFixed(decimals);
        return exact
            ? `<span class="g"><span class="k">${sym}</span><span>${num}</span></span>`
            : `<span class="g"><span class="k">${sym}</span><span class="g-floor" title="floor only — ${c.priced} of ${c.expected} legs priced">≥${num}</span></span>`;
    };
    // Wording tracks the actual state: with zero legs priced there are no floors,
    // there is nothing. Calling that "floors" would be its own small lie.
    const greekNote = gUnreachable
        ? '<div class="book-greeks-note g-na">greeks source unreachable</div>'
        : (gCov && gCov.legs_expected && !gCov.complete)
            ? (gCov.legs_priced > 0
                ? `<div class="book-greeks-note g-floor">${gCov.legs_priced}/${gCov.legs_expected} legs priced — values are floors</div>`
                : `<div class="book-greeks-note g-na">0/${gCov.legs_expected} legs priced — no greeks available</div>`)
            : '';

    // Theme concentration: join open-position tickers -> theme, sum at-risk (current_value).
    const conc = computeConcentration(positions);

    // R-IV.1369(e): the cleaned tile is the default; `?clean=off` keeps the lines below. It is
    // handed the SAME values the old tile computed above -- the floor, the scope, the Day P&L
    // reason, the greeks coverage -- so the two cannot disagree about a single figure.
    if (CLEAN) {
      el.innerHTML = bookCleanHtml({ counted, total, hasBal, balFloor, balMissing, balPartial,
        scopeKnown, day, dayUnavailable, gTotals, gCov, gPer, gUnreachable, greeks, conc,
        positions });
      bookCleanChrome({ bookNote, balPartial, balMissing, scopeKnown, gTotals, gCov, greeks, conc });
      applyGlossary(el);
      _openPositions = (positions && positions.positions) || [];
      renderPositions();
      bookFold();
      bookAnnounce();
      return;
    }

    el.innerHTML = `
      <div class="book-line"><span class="k">Balance</span><span class="v">${counted.filter(hasBal).length ? (balFloor ? '≥' : '') + fmt$(total) : 'not recorded'}${scopeKnown ? '' : ' ' + vintageChip({ unknownLabel: 'scope unknown', unknownTitle: 'this backend does not report account scope; the total is every row' })}${balFloor ? ' ' + vintageChip({ unknownLabel: 'floor only', unknownTitle: [balPartial.length ? balPartial.length + ' account(s) serve a PARTIAL balance: ' + balPartial.map((a) => (a.account_display || a.account_name) + ' — ' + (a.balance_reason || 'partial, no reason given')).join('; ') : '', balMissing.length ? balMissing.length + ' account(s) have no balance recorded at all, and are not in this sum' : ''].filter(Boolean).join('. ') }) : ''}</span></div>
      <div class="book-line"><span class="k">Day P&amp;L</span>${dayCell}</div>
      <div class="book-greeks">
        ${greekCell('Δ', 'delta', 0)}
        ${greekCell('Γ', 'gamma', 1)}
        ${greekCell('Θ', 'theta', 0)}
        ${greekCell('V', 'vega', 0)}
      </div>
      ${greekNote}
      ${conc ? `<div class="conc-lamp ${conc.hot ? 'hot' : 'ok'}" data-gloss="CONC"><span>Concentration${conc.theme ? ' · ' + esc(conc.theme) : ''}</span><span>${conc.pct != null ? conc.pct + '%' : ''}${conc.skipped ? ' ' + vintageChip({ unknownLabel: conc.pct != null ? 'partial: ' + conc.skipped + ' of ' + conc.total + ' left out' : 'no figures: ' + conc.skipped + ' of ' + conc.total + ' left out', unknownTitle: conc.skipped + ' of ' + conc.total + ' positions have no dollar figure and are left out of this percentage; it covers only the rest, and stays partial until every row has one' }) : ''}</span></div>` : ''}
      <div class="acct-chips">${accts.filter((a) => a.in_scope !== false).map((a) => {
          const tag = esc(a.account_display || (a.broker || '').toUpperCase().slice(0, 4) || '');
          // Three states, deliberately distinguished: a figure, a PARTIAL figure, and none.
          if (a.balance == null) {
            return `<span class="acct-chip acct-chip-none" title="The hub has no balance recorded for this account. Shown as not recorded rather than as $0.00, which would claim the account is empty.">${tag ? tag + ' ' : ''}not recorded</span>`;
          }
          if (a.balance_partial === true) {
            return `<span class="acct-chip acct-chip-partial" title="${esc(a.balance_reason || 'The hub says this figure is partial.')}${a.balance_source ? ' Source: ' + esc(a.balance_source) + '.' : ''}">${tag ? tag + ' ' : ''}≥${fmt$(a.balance)}</span>`;
          }
          return `<span class="acct-chip">${tag ? tag + ' ' : ''}${fmt$(a.balance)}</span>`;
        }).join('')}</div>`;
    applyGlossary(el);
    _openPositions = (positions && positions.positions) || [];
    renderPositions();
    bookAnnounce();
  }

  // R-IV.1382(d)6: "after a close or an add succeeds, reload the book". Both forms already end in
  // refreshDesk() -> loadBook(); this tells the Positions panel the book was re-read, so it re-reads
  // too. An event, not a call into the other module, so neither reaches into the other's state.
  function bookAnnounce() {
    try { window.dispatchEvent(new CustomEvent('v2:book')); } catch (_) {}
  }

  // ═══ R-IV.1369(e) · THE BOOK TILE, CLEANED (as amended by R-IV.1381(e)) ═══════════════════
  //
  // COUNTS POSITIONS, NOT LEGS (R-IV.1381(e)1). The source is the mark job's own result -- the
  // SAME set the balance and its ≥ floor are built from: each account's
  // `balance_positions_counted` (valued) and `balance_positions_unvalued` (not). So the meter,
  // the floor and Day P&L can never disagree about what is priced. The old "10/22" counted
  // only option LEGS from a greeks snapshot up to a day old, which left every stock and ETF
  // invisible to it.

  const MT_HM = (() => {
    try { return new Intl.DateTimeFormat('en-US', { timeZone: 'America/Denver', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }); }
    catch (_) { return null; }
  })();
  // A stored INSTANT shown as Nick's clock reads it. Formatting a recorded time for display,
  // not working out a session from a clock (R-IV.416(c)).
  const mtHM = (iso) => {
    const t = Date.parse(iso || '');
    return (MT_HM && Number.isFinite(t)) ? MT_HM.format(new Date(t)) + ' MT' : null;
  };
  // R-IV.726's DAY-VERSUS-MOMENT rule for a cash anchor: an instant is a moment, converted to
  // Denver's calendar; a date-only anchor is a day, taken as written.
  const MT_DAY = (() => {
    try { return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Denver', year: 'numeric', month: '2-digit', day: '2-digit' }); }
    catch (_) { return null; }
  })();
  function anchorDay(ca) {
    if (!ca || !ca.as_of) return null;
    if (ca.as_of_is_instant && MT_DAY) {
      const t = Date.parse(ca.as_of);
      if (Number.isFinite(t)) return MT_DAY.format(new Date(t));
    }
    return String(ca.as_of).slice(0, 10);
  }

  // #35: LARGEST-REMAINDER rounding, so the account shares sum to exactly 100. Each share is
  // floored, then the points left over go to the largest fractional parts, ties to the larger
  // balance. A plain round() can sum to 99 or 101, and a column of percentages that does not
  // add up reads as an error even when every figure in it is right.
  function shares100(vals) {
    const tot = vals.reduce((s, v) => s + v, 0);
    if (!(tot > 0) || vals.some((v) => v < 0)) return null;
    const raw = vals.map((v) => (v / tot) * 100);
    const out = raw.map(Math.floor);
    let left = 100 - out.reduce((s, v) => s + v, 0);
    raw.map((v, i) => ({ i, r: v - Math.floor(v), v: vals[i] }))
      .sort((a, b) => (b.r - a.r) || (b.v - a.v))
      .forEach((x) => { if (left > 0) { out[x.i] += 1; left -= 1; } });
    return out;
  }

  // ── R-IV.1382(d)2/(d)5(ii): THE BOOK TILE'S RULES, SHARED WITH THE POSITIONS PANEL ──────────
  // One copy of each rule, called from both places, so the panel's account strip and its Day P&L
  // card cannot drift from the tile ("Share the BOOK tile's code; don't copy it").

  // The total and its floor: partial OR missing balances make the sum a floor.
  function bookTotalOf(accts) {
    const has = (a) => a && a.balance != null;
    const total = accts.filter(has).reduce((s, a) => s + Number(a.balance), 0);
    const missing = accts.filter((a) => !has(a));
    const partial = accts.filter((a) => has(a) && a.balance_partial === true);
    return { total, missing, partial, any: accts.some(has), floor: partial.length > 0 || missing.length > 0 };
  }
  function bookTotalHtml(t) {
    return t.any ? (t.floor ? '<span class="bk-floor" title="A floor: at least one account is partial or has no balance recorded.">≥</span>' : '')
      + fmt$(t.total) : '<span class="bk-nr">not recorded</span>';
  }
  // One account's balance, in its three states: a figure, a PARTIAL figure (≥), and none.
  function balanceHtml(a) {
    if (!a || a.balance == null) {
      return '<span class="bk-nr" title="The hub has no balance recorded for this account. Shown as not recorded rather than as $0.00, which would claim the account is empty.">not recorded</span>';
    }
    return (a.balance_partial === true ? '<span class="bk-floor" title="' + esc(a.balance_reason || 'The hub says this figure is partial.') + '">≥</span>' : '')
      + fmt$(a.balance);
  }
  // Day P&L. `d` is { known, N, M, day, dayUnavailable, open }. `explain` puts the waiting
  // reason on the face (the panel's card has room; the tile keeps it in the title).
  let _bookDayIn = null;
  function bookDayHtml(d, explain) {
    if (!d.known || d.N < d.M) {
      // R-IV.1381(e)2: "—" WHILE ANY POSITION IS UNPRICED. A day-over-day figure built from
      // part of the book reads as the whole book's day.
      return '<div class="bk-dayv bk-na" title="Day P&L waits until every position has a price">—</div>'
        + (explain ? '<div class="bk-why">waits until every position has a price</div>' : '');
    }
    if (d.dayUnavailable || d.day.dollar == null) {
      return '<div class="bk-dayv bk-na">—</div><div class="bk-why">' + esc(d.dayUnavailable || 'not reported') + '</div>';
    }
    const v = Number(d.day.dollar);
    // R-IV.1381(e)2: and when it IS a number, say how many positions carry a STALE mark --
    // those read FLAT in a day-over-day figure, and the reader should know which way that cuts.
    const stale = d.open.filter((p) => String(p.mark_status || '').toUpperCase() === 'STALE').length;
    return '<div class="bk-dayv ' + signCls(v) + '">' + (v >= 0 ? '+' : '−') + fmt$(Math.abs(v)) + '</div>'
      + (d.day.pct != null ? '<div class="bk-why ' + signCls(v) + '">' + (d.day.pct >= 0 ? '+' : '−')
        + Math.abs(Number(d.day.pct)).toFixed(1) + '%</div>' : '')
      + (stale ? '<div class="bk-why">' + stale + ' stale mark' + (stale === 1 ? ' counts' : 's count')
        + ' as no change today</div>' : '');
  }

  function bookCleanHtml(o) {
    const accts = o.counted;
    const name = (a) => a.account_display || a.account_name || '?';
    // (e)2 as amended: valued / unvalued per account, from the balance route's own result.
    const cov = accts.map((a) => {
      const n = a.balance_positions_counted;
      const un = Array.isArray(a.balance_positions_unvalued) ? a.balance_positions_unvalued.length : 0;
      return { a, n: n == null ? null : Number(n), un, m: n == null ? null : Number(n) + un };
    });
    const known = cov.length > 0 && cov.every((c) => c.n != null);
    const N = cov.reduce((s, c) => s + (c.n || 0), 0), M = cov.reduce((s, c) => s + (c.m || 0), 0);
    const inScope = new Set(accts.map((a) => a.account_name));
    const open = ((o.positions && o.positions.positions) || []).filter((p) => inScope.has(p.account));

    // ── top: total value and Day P&L (both through the shared rules above) ──
    const totalTxt = bookTotalHtml(bookTotalOf(accts));
    _bookDayIn = { known, N, M, day: o.day, dayUnavailable: o.dayUnavailable, open };
    const dayHtml = bookDayHtml(_bookDayIn, false);

    // ── the priced box, or the quiet all-priced line ──
    let priced;
    if (!known) {
      priced = '<div class="bk-box"><div class="bk-boxh">PRICING NOT REPORTED</div>'
        + '<div class="bk-boxt">The balance route did not say how many positions it valued, so this '
        + 'tile cannot say whether the total is whole. Day P&amp;L waits.</div></div>';
    } else if (N < M) {
      let segs = '';
      cov.forEach((c) => {
        for (let i = 0; i < c.n; i++) segs += '<i class="on"></i>';
        for (let i = 0; i < c.un; i++) segs += '<i title="' + esc(name(c.a)) + ': no live price"></i>';
      });
      const who = cov.filter((c) => c.un > 0);
      const U = M - N;
      const where = who.length === 1 ? ' in ' + name(who[0].a)
        : ' — ' + who.map((c) => c.un + ' in ' + name(c.a)).join(', ') + ' —';
      priced = '<div class="bk-box"><div class="bk-boxh">PARTIAL · ' + N + ' OF ' + M + ' POSITIONS PRICED</div>'
        + '<div class="bk-segs" role="img" aria-label="' + N + ' of ' + M + ' positions priced">' + segs + '</div>'
        + '<div class="bk-boxt">' + U + ' position' + (U === 1 ? '' : 's') + esc(where) + ' '
        + (U === 1 ? 'has' : 'have') + ' no live price yet. The total is a floor, and Day P&amp;L waits until '
        + (U === 1 ? 'it does' : 'they do') + '.</div></div>';
    } else {
      // "HH:MM MT" is when the mark job last LOOKED -- the newest mark_checked_at -- because
      // that is the moment "every position is priced" was last true by measurement.
      const t = open.map((p) => p.mark_checked_at).filter(Boolean).sort().pop();
      const hm = mtHM(t);
      priced = '<div class="bk-ok"><b>✓</b> All ' + M + ' position' + (M === 1 ? '' : 's') + ' priced'
        + (hm ? ' · ' + esc(hm) : '') + '</div>';
    }

    // ── one row per in-scope account ──
    const sh = shares100(accts.filter((a) => a.balance != null).map((a) => Number(a.balance)));
    let si = 0;
    const rows = cov.map((c) => {
      const a = c.a;
      const has = a.balance != null;
      const pct = has && sh ? sh[si++] : null;
      const val = balanceHtml(a);
      return '<button type="button" class="bk-acct" data-bk-acct="' + esc(a.account_name) + '">'
        + '<span class="bk-an"><b>' + esc(name(a)) + '</b>'
        + (c.un > 0 ? '<span class="bk-np">' + c.n + ' of ' + c.m + ' priced</span>' : '') + '</span>'
        + '<span class="bk-av">' + val + '</span><span class="rg-chev" aria-hidden="true">›</span>'
        + (pct != null ? '<span class="bk-sh"><i style="width:' + pct + '%"></i></span><span class="bk-pc">' + pct + '%</span>' : '')
        + '</button>';
    }).join('');

    // ── cash: part of the total, and when it last matched the brokers ──
    // Summed in INTEGER CENTS from each account's served `balance_cash`, so no float tail can
    // creep into the figure (the page has always summed the balance the same way).
    const cashVals = accts.map((a) => a.balance_cash).filter((v) => v != null);
    const cash = cashVals.length ? cashVals.reduce((s, v) => s + Math.round(Number(v) * 100), 0) / 100 : null;
    const anchors = accts.map((a) => anchorDay(a.cash_anchor));
    // "matches brokers <date>" is only true of EVERY account as of the OLDEST of their latest
    // re-anchors, so that is the date shown. An account never re-anchored makes the line amber.
    const never = anchors.some((d) => !d);
    const oldest = never ? null : anchors.slice().sort()[0];
    const cashLine = never
      ? '<span class="rg-amber-t">not checked against brokers</span>'
      : 'Part of the total · matches brokers <span class="bk-nw">' + esc(rcMd(oldest)) + '</span>';
    const cashRow = '<button type="button" class="bk-acct bk-cash" data-bk-cash>'
      + '<span class="bk-an"><b>Cash</b><span class="bk-sub">' + cashLine + '</span></span>'
      + '<span class="bk-av">' + (cash == null ? '<span class="bk-nr">not recorded</span>'
        : (cashVals.length < accts.length ? '<span class="bk-floor">≥</span>' : '') + fmt$(cash)) + '</span>'
      + '<span class="rg-chev" aria-hidden="true">›</span></button>';

    // ── risk: the greeks on one line, and the concentration lamp ──
    const per = o.gPer || {};
    const gv = (k, dp) => {
      const v = (o.gTotals || {})[k];
      if (v == null) return null;
      const c = per[k] || {};
      const floor = o.gCov && c.expected > 0 && c.priced !== c.expected;
      const n = Number(v);
      return (floor ? '≥' : '') + (n > 0 ? '+' : n < 0 ? '−' : '') + Math.abs(n).toFixed(dp);
    };
    let greeksHtml;
    if (o.gUnreachable) {
      greeksHtml = '<div class="bk-greeks bk-dim">Greeks unavailable · the greeks source did not answer</div>';
    } else {
      const d = gv('delta', 0), t = gv('theta', 0), vg = gv('vega', 0);
      const partial = !!(o.gCov && o.gCov.legs_expected && !o.gCov.complete);
      // (e)5 as amended: the greeks keep THEIR OWN fraction, "N of M legs", in legs.
      //
      // THE GREEKS ROUTE'S OWN COUNT, WHICH IS READ FROM position_legs. The amendment asks for M
      // from position_legs, and that is where the route counts legs since BUILD's c94742bc ("count
      // real legs"): one read of the table for every open row, falling back to the strike pair
      // only for a position with no rows there. So this page takes the route's fraction and does
      // no counting of its own. The tempting page-side substitute -- each row's `legs` field -- is
      // the trap R-IV.697(c)1 names: that jsonb is NOT the table, and on the live book
      // (2026-10-24) it is null or a string on every option row. tests/test_r1369_agora_clean.py
      // pins that the row field is never read.
      //
      // (This comment and the tag's title said, at first, that the route did NOT yet read the
      // table. c94742bc was already in the base this was built on; the claim came from a relay
      // naming the leg count as "BUILD's next job", and the code was not re-read. Corrected.)
      const legsPriced = o.gCov ? Number(o.gCov.legs_priced) || 0 : 0;
      const legsExpected = o.gCov ? Number(o.gCov.legs_expected) || 0 : 0;
      const parts = [d != null ? 'Delta ' + d : null,
        t != null ? 'Theta ' + t.replace(/(\d)/, '$$$1') + '/day' : null,
        vg != null ? 'Vega ' + vg : null].filter(Boolean);
      // Each greek is one unbreakable unit, so a narrow tile wraps BETWEEN them, never inside
      // "Vega ≥+72" -- a value stranded on the line under its name reads as a different figure.
      greeksHtml = '<div class="bk-greeks' + (partial ? ' bk-dim' : '') + '">'
        + '<span>' + (parts.length ? parts.map((x) => '<span class="bk-nw">' + esc(x) + '</span>').join(' · ')
          : 'Greeks —') + '</span>'
        + (partial ? '<span class="bk-ptag" title="' + esc(legsPriced + ' of the ' + legsExpected
          + ' legs the book holds are priced, as the greeks route counts them from position_legs. A position '
          + 'with no rows there is counted by its strike pair.') + '">partial · '
          + legsPriced + ' of ' + legsExpected + ' legs</span>' : '')
        + '</div>';
    }
    const cc = o.conc;
    const concHtml = cc ? '<div class="bk-conc' + (cc.hot ? ' hot' : '') + '" data-gloss="CONC">'
      + '<div class="bk-cl"><span>Concentration' + (cc.theme ? ' · ' + esc(cc.theme) : '') + '</span>'
      + '<span>' + (cc.pct != null ? cc.pct + '% of book' : '—')
      + (cc.skipped ? ' <span class="bk-ptag" title="' + esc(cc.skipped + ' of ' + cc.total
        + ' positions have no dollar figure and are left out of this percentage') + '">partial</span>' : '')
      + '</span></div>'
      + (cc.pct != null ? '<div class="bk-cbar"><i style="width:' + Math.max(0, Math.min(100, cc.pct)) + '%"></i></div>' : '')
      + '</div>' : '';

    const now = mtHM(new Date().toISOString());
    return '<div class="bk">'
      + '<div class="bk-top"><div><div class="bk-k">Total value</div><div class="bk-total">' + totalTxt + '</div></div>'
      + '<div class="bk-day"><div class="bk-k">Day P&amp;L</div>' + dayHtml + '</div></div>'
      + priced + rows + cashRow + greeksHtml + concHtml
      + '<div class="bk-foot"><span>' + (now ? 'updated ' + esc(now) : '') + '</span>'
      + '<button type="button" class="bk-pos" data-bk-pos>Positions ›</button></div></div>';
  }

  // (e)8: what the cleaned tile no longer shows moves behind the header ⓘ -- nothing deleted.
  function bookCleanChrome(o) {
    const g = (o.gTotals || {}).gamma;
    const lines = [o.bookNote,
      'Day P&L: vintage not recorded (no field records when it was computed)',
      o.scopeKnown ? null : 'Scope unknown: this backend does not report account scope; the total is every row',
      o.balPartial.length ? 'Floor: ' + o.balPartial.map((a) => (a.account_display || a.account_name)
        + ' — ' + (a.balance_reason || 'partial, no reason given')).join('; ') : null,
      o.balMissing.length ? o.balMissing.length + ' account(s) have no balance recorded and are not in the total' : null,
      g != null ? 'Gamma ' + Number(g).toFixed(1) : null,
      o.gCov ? 'Greeks coverage: ' + o.gCov.legs_priced + ' of ' + o.gCov.legs_expected + ' legs priced by the greeks route'
        + (o.greeks && o.greeks.stale ? ' (served from its stale cache)' : '') : null,
      o.greeks && (o.greeks.computed_at || o.greeks.as_of) ? 'Greeks computed ' + (o.greeks.computed_at || o.greeks.as_of) : null,
    ].filter(Boolean);
    tileInfo('bookPanelBtn', 'bookInfo', lines.join('\n'));
    // (e)7: the book-stress section (book_stress_mock.json) stays off this tile until B7
    // serves real data.
    const bs = $('bookStress');
    if (bs) bs.hidden = true;
  }

  // THE OPEN-POSITIONS LIST. Under R-IV.1369 it FOLDED rather than leaving, because its rows were
  // the only Close. R-IV.1382 gives the Positions panel CLOSE, ADD and CHART, so the list now
  // LEAVES the tile, as R-IV.1369(e)8 asked -- into Positions, behind the tile's account rows and
  // its "Positions ›" link. Under `?pos=v1` the old panel comes back WITHOUT Close, so the fold
  // comes back with it: the rollback must not strand the only Close button.
  const POS_V1_TILE = (() => {
    try { return new URLSearchParams(location.search).get('pos') === 'v1'; } catch (_) { return false; }
  })();
  let _bkFoldOpen = false;
  function bookFold() {
    const list = $('bookPositions');
    if (!list) return;
    if (!POS_V1_TILE) {
      list.hidden = true;
      const old = $('bookFoldBtn');
      if (old) old.remove();
      return;
    }
    let btn = $('bookFoldBtn');
    if (!btn) {
      btn = document.createElement('button');
      btn.type = 'button'; btn.id = 'bookFoldBtn'; btn.className = 'bk-fold';
      list.parentNode.insertBefore(btn, list);
      btn.addEventListener('click', () => { _bkFoldOpen = !_bkFoldOpen; bookFold(); });
    }
    const n = (_openPositions || []).length;
    btn.setAttribute('aria-expanded', String(_bkFoldOpen));
    btn.innerHTML = 'Open positions · ' + n + '<span class="rg-chev" aria-hidden="true">'
      + (_bkFoldOpen ? '⌄' : '›') + '</span>';
    list.hidden = !_bkFoldOpen;
  }

  // The tile's own doorways into Positions (R-IV.555): an account row, the cash row and the
  // footer link. They press the existing #bookPanelBtn, so the panel opens through its one
  // existing path. The account and the tab ride along on window; R-IV.1382's panel reads them
  // (an account row opens filtered to that account, the cash row opens the CASH tab).
  document.addEventListener('click', (e) => {
    const t = e.target.closest && e.target.closest('#bookStrip [data-bk-acct], #bookStrip [data-bk-cash], #bookStrip [data-bk-pos]');
    if (!t) return;
    window.__ppAcct = t.hasAttribute('data-bk-acct') ? t.getAttribute('data-bk-acct') : null;
    window.__ppTab = t.hasAttribute('data-bk-cash') ? 'cash' : null;
    const b = $('bookPanelBtn');
    if (b) b.click();
  });

  // ── c5: Book positions (same source as legacy Ledger: GET /api/v2/positions?status=OPEN) ──
  let _openPositions = [];
  // The drawer's earnings words, ONE function for the drawer and the Positions panel's facts
  // (R-IV.1382(d)6, "Earnings, as the drawer reads it"). /chronos/next-earnings-batch answers an
  // ETF with its EARLIEST HOLDING's date (`is_etf`, `component`): an ETF reports no earnings, so
  // that date is named as the holding's rather than read as the fund's own.
  function earningsWords(en) {
    if (!en || !en.date) return 'none scheduled';
    return en.date + (en.timing ? ' · ' + en.timing : '')
      + (en.is_etf && en.component ? ' (' + en.component + ', a holding)' : '');
  }

  window.__v2 = { openPositionDrawerAt: (i) => openPositionDrawer(_openPositions[i]), apiFetch: (u, o) => apiFetch(u, o), popSide, setSide, openChart, placeChartSoon,
    // R-IV.1382: what the Positions panel SHARES with the Book module instead of copying it --
    // the floor rule, the Day P&L rule, the four forms and the drawer's own readings. Every entry
    // is an arrow resolved at CALL time: several of these are declared further down this file as
    // const/let, and naming them directly here would throw at page load (temporal dead zone).
    bookTotalHtml: (rows) => bookTotalHtml(bookTotalOf(rows || [])),
    bookTotalFloor: (rows) => bookTotalOf(rows || []).floor,
    balanceHtml: (a) => balanceHtml(a),
    bookDay: (explain) => (_bookDayIn ? bookDayHtml(_bookDayIn, explain) : null),
    openAddForm: () => openAddForm(),
    openCloseForm: (p) => openCloseForm(p),
    openAddToPositionForm: (p) => openAddToPositionForm(p),
    addPosEligible: (p) => ADD_POS_ELIGIBLE(p),
    pnlPct: (p) => pnlPct(p),
    basisSuspect: (p, pct) => basisSuspect(p, pct),
    themeOf: (t) => ((_themeMap || {})[String(t || '').toUpperCase()] || null),
    earningsWords: (en) => earningsWords(en),
  };
  const OPT_PUT = /put/i, OPT_CALL = /call/i;
  // ── R-IV.662(c)/668(c) · WHAT IS OPEN IS `open_quantity`, NEVER `quantity` ────────────────
  // `quantity` is the size the position was OPENED at. After a partial exit it is not what is
  // still held, and HYG 516 is the case: its stored quantity only looks right today because it
  // is wrong. BUILD serves `open_quantity` with an `open_quantity_basis` saying where the figure
  // came from (`lots`, `unknown: the position has no lots`, `0: the position is not open`).
  //
  // A NULL open_quantity IS UNKNOWN, AND IT DOES NOT FALL BACK. Falling back to `quantity` is
  // exactly the silent wrong number this replaces, so an unreadable size renders as unknown and
  // says why.
  const openQty = (p) => {
    const v = p && p.open_quantity;
    if (v == null) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  const openQtyWhy = (p) => (p && p.open_quantity_basis) || 'the hub did not say how many are open';

  function structureStr(p) {
    if ((p.asset_type || '').toUpperCase() === 'EQUITY' || (p.structure || '') === 'stock') {
      return '×' + (openQty(p) != null ? openQty(p) : '?') + ' sh';
    }
    const exp = p.expiry ? new Date(p.expiry + 'T00:00:00').toLocaleDateString('en-US', { month: '2-digit', day: '2-digit' }) : '';
    const strikes = [p.long_strike, p.short_strike].filter((x) => x != null).join('/');
    const type = OPT_PUT.test(p.structure || '') ? 'P' : OPT_CALL.test(p.structure || '') ? 'C' : '';
    const qty = openQty(p) != null ? ' ×' + openQty(p) : '';
    return `${exp} ${strikes}${type}${qty}`.trim();
  }
  // R-IV.540 (BUILD gap 1) -- a money field is null WITH a reason (derived.basis_reason), and a dash
  // reads as zero at a glance. So a null figure renders the reason as an unknown-state chip, the reason
  // in full in its title. `field` matters: "no live mark" explains a missing P&L, not a missing max loss.
  function noMoney(p, field) {
    const why = p && p.derived && p.derived.basis_reason ? String(p.derived.basis_reason) : '';
    const markOnly = /no live mark/i.test(why);
    const label = /no lots|open remainder/i.test(why) ? 'no lots'
      : markOnly ? (field === 'pnl' ? 'no mark' : 'not recorded')
      : why ? 'not recorded' : 'no reason sent';
    return vintageChip({ unknownLabel: label, unknownTitle: why || 'the source sent no figure and no reason for its absence' });
  }
  // R-IV.1181(c)1 — A FIGURE THAT IS NOT SET READS AS AN EM DASH, never as $0.00. Zero is a
  // measurement: it says the worst case IS nothing, which is true of a credit-opened debit
  // structure and false of a row whose lots never arrived. The reason is kept in the tooltip
  // rather than discarded, because "not set" and "not set BECAUSE there are no lots" are
  // different things to a reader deciding whether to go and fix it.
  // R-IV.1181(c)3 — A CREDIT OPENING MUST NOT READ AS A COST.
  //
  // R-IV.1181(b): `entry_price` is an unsigned MAGNITUDE and stays one. It cannot say which
  // way the money went, so a bare "Entry 0.10" reads as "it cost 0.10" on a position that was
  // PAID 0.10 -- and row 978 is exactly that, a put_debit_spread opened for a net credit.
  // The direction comes from `cost_basis`, which is signed and correct: positive paid,
  // negative received.
  function entryLine(p) {
    if (p.entry_price == null) return '—';
    const cb = p.cost_at_remainder != null ? Number(p.cost_at_remainder)
             : p.cost_basis != null ? Number(p.cost_basis) : null;
    if (cb != null && cb < 0) return 'credit ' + Math.abs(Number(p.entry_price));
    return p.entry_price;
  }

  function notSet(p, field) {
    const why = p && p.derived && p.derived.basis_reason ? String(p.derived.basis_reason) : '';
    const title = why || 'the source sent no figure and no reason for its absence';
    return `<span class="not-set" title="${esc(title)}">\u2014</span>`;
  }

  function pnlPct(p) {
    // R-IV.1181(c)2: PREFER THE SERVED FIGURE. The server computes the percent from the same
    // cash basis as the P&L itself, at the open remainder. What this function used to do --
    // divide a lot-derived GROSS P&L by the row's stored CASH `cost_basis` -- mixed two bases
    // in one ratio, and on a partly-closed row two scopes too, because the stored column is
    // the size OPENED (convention #29) while the numerator is what is still held.
    if (p.unrealized_pnl_pct != null) return Number(p.unrealized_pnl_pct);
    // Fallback for a payload that predates the field. Kept deliberately rather than returning
    // null -- an older server should still show a number -- and it is the OLD arithmetic, so
    // it stays wrong in the old way instead of being wrong in a new one.
    const cb = Math.abs(Number(p.cost_at_remainder != null ? p.cost_at_remainder
                                                           : p.cost_basis) || 0);
    if (!cb || p.unrealized_pnl == null) return null;
    return (Number(p.unrealized_pnl) / cb) * 100;
  }
  // R-IV.440(c) — a defined-risk debit structure cannot lose more than it cost, so a return
  // below -100% is arithmetic about a basis that is wrong (DEF-COST-BASIS-NOT-RESCALED), not
  // a loss. The figure is struck through and flagged; a plausible-looking wrong number is
  // worse than a visibly broken one. The upper bound is only checked where a max is known:
  // a long call's gain is unbounded, so there is nothing to check it against.
  const DEF_BASIS_URL = 'https://github.com/303webhouse/pandoras-box/blob/main/docs/defects/DEF-COST-BASIS-NOT-RESCALED.md';
  function basisSuspect(p, pct) {
    if (pct == null) return null;
    const debit = Number(p.cost_basis) > 0;
    if (debit && pct < -100) return 'below -100% on a defined-risk debit structure';
    const maxGain = p.max_gain != null ? Number(p.max_gain) : null;
    const cb = Math.abs(Number(p.cost_basis) || 0);
    if (maxGain != null && cb > 0 && pct > (maxGain / cb) * 100 + 0.5) return 'above the structure\u2019s maximum gain';
    return null;
  }
  const basisChip = (why) => `<a class="basis-chip" href="${DEF_BASIS_URL}" target="_blank" rel="noopener"`
    + ` title="${esc(why)} — the cost basis is under review (DEF-COST-BASIS-NOT-RESCALED)">BASIS UNDER REVIEW</a>`;

  // R-IV.440(d) — INTERIM, until the legs model lands. The screen shows the same structure
  // twice today; grouping by (ticker, expiry, structure) at least says so out loud. It does
  // NOT decide whether those rows are one position or several — that is the legs model's
  // answer, and the count is the honest way to show the question.
  function groupPositions(list) {
    const groups = new Map();
    (list || []).forEach((p, i) => {
      // R-IV.479(c) — account + instrument + structure + strikes + expiry. The first key
      // (ticker+expiry+structure) collapsed rows that differ by ACCOUNT or by STRIKES, so
      // two positions in two accounts, or two different spreads on one expiry, counted as
      // duplicates of each other. Measured on the live book: the short key found 5 groups,
      // this one finds 3, and the difference was never duplication.
      const key = [
        (p.account || '?').toUpperCase(),
        (p.ticker || '').toUpperCase(),
        p.structure || '-',
        p.long_strike == null ? '-' : String(p.long_strike),
        p.short_strike == null ? '-' : String(p.short_strike),
        p.expiry || '-',
      ].join('|');
      if (!groups.has(key)) groups.set(key, { key, rows: [], idx: i });
      groups.get(key).rows.push(p);
    });
    return [...groups.values()].map((g) => {
      const rows = g.rows;
      const pnls = rows.map((r) => (r.unrealized_pnl == null ? null : Number(r.unrealized_pnl)));
      const anyPnl = pnls.some((v) => v != null);
      const pnl = anyPnl ? pnls.reduce((a, v) => a + (v || 0), 0) : null;
      const cb = rows.reduce((a, r) => a + Math.abs(Number(r.cost_basis) || 0), 0);
      const pct = anyPnl && cb ? (pnl / cb) * 100 : null;
      const nullRow = rows.find((r) => r.unrealized_pnl == null) || null;
      return { head: rows[0], rows, idx: g.idx, count: rows.length, pnl, pct, nullRow, partial: anyPnl && !!nullRow,
               suspect: rows.map((r) => basisSuspect(r, pnlPct(r))).find(Boolean) || null };
    });
  }
  function renderPositions() {
    const el = $('bookPositions'); if (!el) return;
    // R-IV.650(b)2: one filter and one sort, shared by every list of positions on the page.
    const ctl = acctControlHtml();
    const ctlHtml = ctl ? `<div class="acct-ctl">${ctl}</div>` : '';
    const list = _openPositions.filter((p) => inAcct(p.account));
    if (!_openPositions.length) { el.innerHTML = ctlHtml + '<div class="pos-empty">no open positions</div>'; return; }
    if (!list.length) {
      const who = (_acctOptions.find((a) => a.key === _acctFilter) || {}).label || 'that account';
      el.innerHTML = ctlHtml + `<div class="pos-empty">no open positions in ${esc(who)}</div>`;
      return;
    }
    let rows = groupPositions(list);
    if (_acctSort) rows = rows.slice().sort((a, b) =>
      acctRank(a.head.account) - acctRank(b.head.account) || String(a.head.ticker || '').localeCompare(String(b.head.ticker || '')));
    el.innerHTML = ctlHtml + rows.map((g) => {
      const p = g.head;
      const pnl = g.pnl;
      const pct = g.pct;
      const dteCls = p.dte != null && p.dte <= 7 ? 'urgent' : p.dte != null && p.dte <= 14 ? 'soon' : '';
      const dteStr = p.dte != null ? p.dte + ' DTE' : (p.asset_type === 'EQUITY' ? 'equity' : '');
      const pctTxt = pct != null ? (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%' : '';
      return `<div class="pos-row" data-pi="${g.idx}">
        <span class="ptk">${acctChip(p.account, p.account_display)}${esc(p.ticker)}${g.count > 1 ? `<span class="dup-count" title="${g.count} rows share this ticker, expiry and structure — the legs model decides whether that is one position or several">×${g.count}</span>` : ''}</span>
        <span class="pmid"><span class="pstruct">${esc(structureStr(p))}</span><span class="pdte ${dteCls}">${dteStr}</span></span>
        <span class="ppnl ${g.suspect ? '' : signCls(pnl)}"><span class="amt">${pnl != null ? (pnl >= 0 ? '+' : '-') + '$' + Math.abs(pnl).toFixed(0) : noMoney(g.nullRow || p, 'pnl')}${g.partial ? vintageChip({ unknownLabel: 'partial', unknownTitle: 'some rows in this group have no figure; the sum leaves them out, so it is a floor' }) : ''}</span>${g.suspect ? `<span class="pct struck">${esc(pctTxt)}</span>${basisChip(g.suspect)}` : `<span class="pct">${pctTxt}</span>`}</span>
      </div>`;
    }).join('');
    el.querySelectorAll('.pos-row[data-pi]').forEach((r) => r.addEventListener('click', () => openPositionDrawer(_openPositions[+r.dataset.pi])));
  }

  async function openPositionDrawer(p) {
    if (!p) return;
    const title = $('drawerTitle'), body = $('drawerBody');
    title.textContent = p.ticker + ' · position';
    const kv = (k, v) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`;
    const kvh = (k, html) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${html}</span></div>`;
    const pnl = p.unrealized_pnl != null ? Number(p.unrealized_pnl) : null; const pct = pnlPct(p);
    const suspect = basisSuspect(p, pct);
    const tm = _themeMap[(p.ticker || '').toUpperCase()];
    body.innerHTML =
      kv('Structure', structureStr(p) + (p.structure ? '  (' + String(p.structure).replace(/_/g, ' ') + ')' : '')) +
      kv('Direction', p.direction || '—') + kv('Account', p.account_display || '—') +
      kv('Entry', entryLine(p)) + kv('Current', p.current_price != null ? p.current_price : '—') +
      kv('Stop', p.stop_loss != null ? p.stop_loss : '—') + kv('Target', p.target_1 != null ? p.target_1 : '—') +
      (openQty(p) != null
        ? kv('Open qty', openQty(p))
        : kvh('Open qty', vintageChip({ unknownLabel: 'unknown', unknownTitle: openQtyWhy(p) }))) +
      kv('DTE', p.dte != null ? p.dte : '—') +
      kv('Cost basis', p.cost_basis != null ? '$' + Number(p.cost_basis).toFixed(2) : '—') +
      (p.max_loss != null ? kv('Max loss', '$' + Number(p.max_loss).toFixed(2))
                          : kvh('Max loss', notSet(p, 'max_loss'))) +
      `<div class="kv"><span class="k">Unrealized P&amp;L</span><span class="v ${suspect ? '' : signCls(pnl)}">${pnl != null ? (pnl >= 0 ? '+' : '-') + '$' + Math.abs(pnl).toFixed(2) : noMoney(p, 'pnl')}${pct != null ? (suspect ? ' <span class="struck">(' + (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%)</span> ' + basisChip(suspect) : ' (' + (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%)') : ''}</span></div>` +
      kv('Bucket', p.bucket || '—') + kv('Theme', tm && tm.theme ? (tm.theme + (tm.inverse ? ' (inverse)' : '')) : '—') +
      '<div id="posEarn" class="kv"><span class="k">Earnings</span><span class="v">…</span></div>' +
      `<div class="drawer-actions">
         <button type="button" class="btn-danger" id="posCloseBtn">Close position</button>
         ${ADD_POS_ELIGIBLE(p) ? '<button type="button" class="btn-secondary add-pos-btn" id="posAddBtn">Add to position</button>' : ''}
         <button type="button" class="btn-secondary" id="posChartBtn">Chart</button>
       </div>`;
    closePopup(); setSide($('drawer'), popSide(null, 'book')); syncTopbarH();
    $('drawerBackdrop').classList.add('open'); openedDrawerHistory(); $('drawer').classList.add('open'); placeChartSoon();
    $('posCloseBtn').addEventListener('click', () => openCloseForm(p));
    $('posChartBtn').addEventListener('click', (e) => openChart(p.ticker, e.target));
    // R-IV.1178(b): bound only when the button was drawn. Querying an element that a
    // template chose not to render returns null, and `null.addEventListener` would throw
    // and take the rest of this function -- the earnings fetch included -- down with it.
    if ($('posAddBtn')) $('posAddBtn').addEventListener('click', () => openAddToPositionForm(p));
    // Earnings surface (CHRONOS) — single earnings source from P0
    try {
      const r = await apiFetch('/api/chronos/next-earnings-batch?tickers=' + encodeURIComponent(p.ticker));
      if (r.ok) {
        const e = (await r.json()).earnings || {}; const en = e[(p.ticker || '').toUpperCase()];
        const cell = $('posEarn');
        if (cell) cell.querySelector('.v').textContent = earningsWords(en);
      }
    } catch (_) {}
  }

  // ── R-IV.606(a) · the expiry field has to work where there is no date picker ──────────
  // MEASURED, not assumed: in a WebKit build at 390px the `type="date"` attribute does not
  // stick — `input.type` reads back "text" — so the field renders as a bare empty box with no
  // picker and no hint of what to type. Whatever was typed then went STRAIGHT to the write
  // endpoint unvalidated, and `unified_positions` swallows an unparseable expiry in a bare
  // `except: pass`. So "12/18/2026" created the position with NO EXPIRY and said "created".
  // A silently dropped expiry on an options position is the worst of the three outcomes.
  //
  // The standard feature test, not a user-agent sniff: a real date input REJECTS an invalid
  // value by sanitising it to ''. A text input keeps it.
  const DATE_INPUT_SUPPORTED = (() => {
    try {
      const i = document.createElement('input');
      i.setAttribute('type', 'date');
      if (i.type !== 'date') return false;
      i.value = 'not-a-date';
      return i.value === '';
    } catch (_) { return false; }
  })();
  // ONE validator, read by the picker path and the typed path alike, so the fallback cannot
  // drift into accepting something the picker would never produce. Rejects 2026-02-31: the
  // regex alone would pass it and the Date would roll it over to March.
  const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;
  // R-IV.651(c)2 — a date can be TYPED with whatever keyboard appears. An iOS numeric pad has
  // no hyphen and no slash, so YYYY-MM-DD cannot be typed on one at all; 121826 and 12182026
  // can. Every shape below resolves to the SAME ISO string and goes through the same validator,
  // so the fallback can never accept something the picker would not produce.
  //   121826      MMDDYY        12182026   MMDDYYYY
  //   12/18/2026  MM/DD/YYYY    2026-12-18 ISO (and 2026/12/18)
  // A two-digit year is read as 20YY: these are expiries, and a 19xx option expiry is not a
  // thing. Anything else — including a day-first date, which cannot be told from month-first —
  // is REFUSED rather than guessed.
  function parseExpiry(raw) {
    const t = String(raw == null ? '' : raw).trim();
    if (!t) return null;
    let y, m, d;
    let mm = t.match(/^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$/);
    if (mm) { y = +mm[1]; m = +mm[2]; d = +mm[3]; }
    if (!mm && (mm = t.match(/^(\d{1,2})[-/](\d{1,2})[-/](\d{2}|\d{4})$/))) {
      m = +mm[1]; d = +mm[2]; y = +mm[3]; if (y < 100) y += 2000;
    }
    if (!mm && (mm = t.match(/^(\d{2})(\d{2})(\d{2})$/))) { m = +mm[1]; d = +mm[2]; y = 2000 + (+mm[3]); }
    if (!mm && (mm = t.match(/^(\d{2})(\d{2})(\d{4})$/))) { m = +mm[1]; d = +mm[2]; y = +mm[3]; }
    if (!mm) return null;
    const iso = String(y).padStart(4, '0') + '-' + String(m).padStart(2, '0') + '-' + String(d).padStart(2, '0');
    return isIsoDate(iso) ? iso : null;      // rejects 2026-02-31 and a month of 13
  }
  // The date it UNDERSTOOD, with its weekday, so a mis-typed date is caught before Create and
  // not after. Formatted in UTC: an expiry is a calendar date, not an instant.
  // R-IV.662(b) — TA-083: a position logged late carried the LOGGING day, not the trading day.
  // Both forms now ask, and both default to today so the common case is one tap.
  //
  // Today in Denver, because that is the day the principal means when he says "today". The
  // positions panel has its own `todayMT` for the cash form's date — it is in a different IIFE
  // and cannot reach this one; the duplication is scope, not drift, and both answer the same
  // question the same way.
  const todayMT = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Denver' }).format(new Date());

  // The same shape as the expiry field: typable on any keyboard, a native picker beside it where
  // there is one, and a read-back naming the weekday. `max` is today — a trade cannot be logged
  // as having happened tomorrow.
  function dateFieldHtml(id, label, hint) {
    const today = todayMT();
    return `<div class="fld"><label for="${id}">${esc(label)}</label>
      <div class="fld-row">
        <input id="${id}" type="text" inputmode="numeric" autocomplete="off" maxlength="10"
               value="${today}" placeholder="12/18/2026" aria-describedby="${id}_echo">
        ${DATE_INPUT_SUPPORTED ? `<input id="${id}_pick" type="date" max="${today}" aria-label="Pick ${esc(label)} from a calendar">` : ''}
      </div>
      <div class="fld-echo" id="${id}_echo" role="status"></div>
      ${hint ? `<div class="fld-echo">${esc(hint)}</div>` : ''}</div>`;
  }
  // Returns the parsed ISO, or null when it cannot be read or is in the future. `quiet` is for
  // the live echo; the submit path asks for the message instead.
  function readDateField(id) {
    const el = $(id); if (!el) return { iso: null, err: null, raw: '' };
    const raw = (el.value || '').trim();
    if (!raw) return { iso: null, err: null, raw };
    const iso = parseExpiry(raw);
    if (!iso) return { iso: null, err: 'That date could not be read. Try 12/18/2026, 12182026 or 2026-12-18.', raw };
    if (iso > todayMT()) return { iso: null, err: 'That date is in the future. A trade is logged on the day it happened, or earlier.', raw };
    return { iso: iso, err: null, raw };
  }
  function wireDateField(id) {
    const el = $(id), pick = $(id + '_pick'), echo = $(id + '_echo');
    if (!el || !echo) return;
    const show = () => {
      const r = readDateField(id);
      if (!r.raw) { echo.textContent = ''; echo.className = 'fld-echo'; return; }
      if (r.iso) { echo.textContent = expiryEcho(r.iso); echo.className = 'fld-echo ok'; }
      else { echo.textContent = r.err; echo.className = 'fld-echo bad'; }
    };
    el.addEventListener('input', show);
    if (pick) pick.addEventListener('change', () => { if (pick.value) { el.value = pick.value; show(); } });
    show();
  }

  function expiryEcho(iso) {
    const t = Date.parse(iso + 'T00:00:00Z');
    if (!Number.isFinite(t)) return '';
    return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', weekday: 'long', day: 'numeric',
      month: 'long', year: 'numeric' }).format(new Date(t));
  }
  function isIsoDate(v) {
    if (!ISO_DATE.test(v)) return false;
    const t = Date.parse(v + 'T00:00:00Z');
    return Number.isFinite(t) && new Date(t).toISOString().slice(0, 10) === v;
  }

  // ── c5: add / close via the EXISTING write endpoints (call, never modify) ──
  const STRUCTURES = ['stock', 'long_call', 'long_put', 'call_debit_spread', 'put_debit_spread', 'call_credit_spread', 'put_credit_spread'];
  function openModal(title, html) { closeChart(); $('modalTitle').textContent = title; $('modalBody').innerHTML = html; $('modalBackdrop').classList.add('open'); $('posModal').classList.add('open'); }
  function closeModal() { $('modalBackdrop').classList.remove('open'); $('posModal').classList.remove('open'); }

  // R-IV.651(c)3 / R-IV.650(b)2 — THE ACCOUNT LIST IS SERVED, NEVER HARD-CODED. The old form
  // offered ROBINHOOD and FIDELITY; since R-IV.638(b)3 `canonical_account` REFUSES a Fidelity
  // name (two Fidelity accounts, so a name is not an identity), which means every Fidelity add
  // from this form failed, and FIDELITY_401A could not be chosen at all.
  //
  // Each entry is {key, label}: the LABEL is the served `account_display`, the KEY is what the
  // write sends. A key is never shown. An account the hub lists but has served no display name
  // for is offered DISABLED with a plain reason rather than labelled with its key or dropped
  // silently — dropping it is how an account becomes unreachable without anyone noticing.
  let _acctOptions = [];
  // ── R-IV.650 · every position says which account it is in, and one filter governs them all ──
  // The filter is GENERATED from the accounts the hub serves, so a fourth account appears
  // without a code change. 'all' is the default and is not an account.
  let _acctFilter = 'all';
  // R-IV.650(b)4: NEUTRAL chips. On this surface lime means a gain, vermilion a loss and amber
  // "we cannot confirm this" — giving each account a fixed hue would teach a second meaning for
  // the same three. The NAME identifies it; teal marks only the one being filtered to.
  const acctChip = (key, display) => {
    const label = display || (_acctOptions.find((a) => a.key === key) || {}).label;
    if (!label) return '';          // never a key: a key is not a label (R-IV.650(a))
    return `<span class="pos-acct${_acctFilter === key ? ' on' : ''}">${esc(label)}</span>`;
  };
  const inAcct = (key) => _acctFilter === 'all' || key === _acctFilter;
  // Sorted by account, the lists group in the order the hub served them, then by ticker.
  const acctRank = (key) => { const i = _acctOptions.findIndex((a) => a.key === key); return i < 0 ? 99 : i; };
  function acctControlHtml() {
    const named = _acctOptions.filter((a) => a.label);
    if (named.length < 2) return '';      // one account needs no filter
    const btn = (k, t) => `<button type="button" data-acctf="${esc(k)}" aria-pressed="${_acctFilter === k}">${esc(t)}</button>`;
    return `<span class="seg acct-seg" role="group" aria-label="Filter positions by account">`
      + btn('all', 'All') + named.map((a) => btn(a.key, a.label)).join('')
      + `</span><button type="button" class="btn-add acct-sort" data-acctsort="1" aria-pressed="${_acctSort}"
           title="Group the list by account instead of by size">by account</button>`;
  }
  let _acctSort = false;
  // One delegated handler for every surface that renders the control.
  document.addEventListener('click', (e) => {
    const f = e.target.closest && e.target.closest('[data-acctf]');
    if (f) { _acctFilter = f.dataset.acctf; loadBook(); renderRiver(); return; }
    const so = e.target.closest && e.target.closest('[data-acctsort]');
    if (so) { _acctSort = !_acctSort; loadBook(); renderRiver(); }
  });
  function noteAccounts(positions, balances) {
    const seen = new Map();
    const add = (key, label) => {
      if (!key) return;
      const k = String(key);
      if (!seen.has(k)) seen.set(k, { key: k, label: null });
      if (label && !seen.get(k).label) seen.get(k).label = String(label);
    };
    const rows = (positions && (positions.positions || positions.rows)) || (Array.isArray(positions) ? positions : []);
    (rows || []).forEach((p) => add(p && p.account, p && p.account_display));
    (Array.isArray(balances) ? balances : []).forEach((b) => {
      if (b && b.in_scope !== false) add(b.account_name || b.account, b.account_display);
    });
    if (seen.size) _acctOptions = [...seen.values()];
  }

  function openAddForm() {
    const fld = (id, label, attrs) => `<div class="fld"><label for="${id}">${label}</label><input id="${id}" ${attrs || ''}></div>`;
    openModal('Add position', `
      <div class="form-grid">
        ${fld('f_ticker', 'Ticker', 'placeholder="AAPL" autocomplete="off"')}
        <div class="fld"><label for="f_account">Account</label><select id="f_account">
          <option value="" selected>Choose an account…</option>
          ${_acctOptions.map((a) => (a.label
            ? `<option value="${esc(a.key)}">${esc(a.label)}</option>`
            : '<option value="" disabled>(an account the hub has not named yet)</option>')).join('')}
          ${_acctOptions.length ? '' : '<option value="" disabled>(no accounts read yet)</option>'}
        </select></div>
        <div class="fld"><label for="f_structure">Structure</label><select id="f_structure">${STRUCTURES.map((s) => `<option value="${s}">${s.replace(/_/g, ' ')}</option>`).join('')}</select></div>
        ${dateFieldHtml('f_trade_date', 'Trade date', 'the day the trade happened — today unless you say otherwise')}
        ${fld('f_qty', 'Quantity', 'type="number" min="1" value="1"')}
        ${fld('f_entry', 'Entry price', 'type="number" step="any" placeholder="0.00"')}
        <div class="fld"><label for="f_expiry">Expiry</label>
          <div class="fld-row">
            <input id="f_expiry" type="text" inputmode="numeric" autocomplete="off" maxlength="10"
                   placeholder="12/18/2026" aria-describedby="f_expiry_echo">
            ${DATE_INPUT_SUPPORTED ? '<input id="f_expiry_pick" type="date" aria-label="Pick the expiry from a calendar">' : ''}
          </div>
          <div class="fld-echo" id="f_expiry_echo" role="status"></div></div>
        ${fld('f_long', 'Long strike', 'type="number" step="any"')}
        ${fld('f_short', 'Short strike', 'type="number" step="any"')}
        ${fld('f_stop', 'Stop', 'type="number" step="any"')}
        ${fld('f_target', 'Target', 'type="number" step="any"')}
        <div class="fld full">${'<label for="f_notes">Notes</label><input id="f_notes" placeholder="optional">'}</div>
      </div>
      <div class="form-foot">
        <div class="form-msg" id="f_msg"></div>
        <div class="form-actions"><button type="button" class="btn-primary" id="f_submit">Create</button><button type="button" class="btn-secondary" id="f_cancel">Cancel</button></div>
      </div>`);
    $('f_cancel').addEventListener('click', closeModal);
    $('f_submit').addEventListener('click', submitAdd);
    // The echo updates as he types, so a mis-read date is caught BEFORE Create, not after.
    const xp = $('f_expiry'), pick = $('f_expiry_pick'), echo = $('f_expiry_echo');
    function showEcho() {
      const raw = (xp.value || '').trim();
      if (!raw) { echo.textContent = ''; echo.className = 'fld-echo'; return; }
      const iso = parseExpiry(raw);
      if (iso) { echo.textContent = expiryEcho(iso); echo.className = 'fld-echo ok'; }
      else { echo.textContent = 'Not a date yet — try 12/18/2026, 12182026 or 2026-12-18.'; echo.className = 'fld-echo bad'; }
    }
    xp.addEventListener('input', showEcho);
    if (pick) pick.addEventListener('change', () => { if (pick.value) { xp.value = pick.value; showEcho(); } });
    wireDateField('f_trade_date');
  }
  async function submitAdd() {
    const val = (id) => { const e = $(id); return e && e.value !== '' ? e.value : null; };
    const num = (id) => { const v = val(id); return v == null ? null : Number(v); };
    const ticker = (val('f_ticker') || '').toUpperCase().trim();
    const structure = val('f_structure');
    if (!ticker) { $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'Ticker is required'; return; }
    // Nothing is preselected, so an account must be CHOSEN — a trade cannot land in the wrong
    // one by default (R-IV.651(c)3).
    if (!val('f_account')) { $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'Choose an account.'; return; }
    // TA-083: the trading day, not the logging day. Sent as `entry_date`, which the write path
    // already takes (`unified_positions.py` _when/entry_date) and uses for the lot's fill time.
    const td = readDateField('f_trade_date');
    if (td.err) { $('f_msg').className = 'form-msg err'; $('f_msg').textContent = td.err; return; }
    if (!td.iso) { $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'Enter the trade date.'; return; }
    const body = {
      ticker, asset_type: structure === 'stock' ? 'EQUITY' : 'OPTION', structure,
      entry_price: num('f_entry'), quantity: parseInt(val('f_qty'), 10) || 1, source: 'MANUAL', account: val('f_account'),
    };
    if (num('f_long') != null) body.long_strike = num('f_long');
    if (num('f_short') != null) body.short_strike = num('f_short');
    // Validated on EVERY engine, not just the one without a picker: the endpoint drops an
    // expiry it cannot parse without telling anyone, so the page refuses before it can.
    // Whatever was typed becomes ONE ISO string, then goes through the same validator as before.
    const rawExpiry = val('f_expiry');
    const expiry = rawExpiry ? parseExpiry(rawExpiry) : null;
    if (rawExpiry && !expiry) {
      $('f_msg').className = 'form-msg err';
      $('f_msg').textContent = 'That expiry could not be read. Try 12/18/2026, 12182026 or 2026-12-18.';
      return;
    }
    if (expiry && !isIsoDate(expiry)) {
      $('f_msg').className = 'form-msg err';
      $('f_msg').textContent = 'Expiry must be a real date written YYYY-MM-DD, like 2026-12-18.';
      return;
    }
    if (expiry) body.expiry = expiry;
    body.entry_date = td.iso;
    if (num('f_stop') != null) body.stop_loss = num('f_stop');
    if (num('f_target') != null) body.target_1 = num('f_target');
    if (val('f_notes')) body.notes = val('f_notes');
    // R-IV.767(c): the principal ticked "I made this trade twice", so send it with the entry.
    // Read and CLEARED here, so a confirm is spent on the one submit it was given for and
    // cannot sit armed for the next entry — which would reinstate the defect with a tick in it.
    if (addConfirmDuplicate) { body.confirm_duplicate = true; addConfirmDuplicate = false; }
    $('f_msg').className = 'form-msg'; $('f_msg').textContent = 'saving…';
    // The button is disabled for the WHOLE round trip and re-enabled in `finally`, so a failed
    // save leaves a usable form. The two SOXS writes were ten seconds apart, so this alone
    // would not have stopped them -- the server guard is the half that does. It stops the
    // double-click, which is a different mistake with the same result.
    const btn = $('f_submit');
    const label = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'saving…'; }
    try {
      const r = await apiFetch('/api/v2/positions', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, body: JSON.stringify(body) });
      if (r.ok) { $('f_msg').className = 'form-msg ok'; $('f_msg').textContent = 'created'; setTimeout(() => { closeModal(); refreshDesk(); }, 500); }
      else if (r.status === 401) { $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'sign in to add positions'; showLogin(); }
      else {
        const d = await r.json().catch(() => ({}));
        // A 409 from the duplicate guard is the one refusal the principal can overrule, so it
        // gets the sentence in full and a way through, not a status code.
        if (r.status === 409 && typeof d.detail === 'string' && /same entry twice/.test(d.detail)) {
          showDuplicateRefusal(d.detail);
        } else {
          $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'failed: ' + (d.detail || r.status);
        }
      }
    } catch (_) { $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'network error'; }
    finally { if (btn) { btn.disabled = false; btn.textContent = label; } }
  }

  // R-IV.767(c). The refusal, with the one action that answers it. Nothing is pre-ticked and
  // nothing re-sends by itself: the principal has to say a second time that the trade really
  // happened twice, which is the whole value of the refusal.
  let addConfirmDuplicate = false;
  function showDuplicateRefusal(detail) {
    addConfirmDuplicate = false;
    const msg = $('f_msg');
    if (!msg) return;
    msg.className = 'form-msg err';
    msg.textContent = '';
    const text = document.createElement('div');
    // The sentence the server wrote, verbatim. The page does not paraphrase a refusal: a
    // second wording is a second thing to keep true.
    text.textContent = detail;
    const again = document.createElement('button');
    again.type = 'button';
    again.className = 'btn-secondary';
    again.style.marginTop = '6px';
    again.textContent = 'I really did make this trade twice — save it anyway';
    again.addEventListener('click', () => { addConfirmDuplicate = true; submitAdd(); });
    msg.appendChild(text);
    msg.appendChild(again);
  }

  // ── Add to position (R-IV.1173 STEP 1, surfaced here by R-IV.1178(b)) ───────────────────
  //
  // PREVIEW ONLY. Confirm is disabled and NOTHING is bound to it. The arithmetic below is the
  // same arithmetic the write path will do in Python, which is the reason the two sets of
  // structure names are mirrored explicitly rather than guessed: if they ever disagree, the
  // principal confirms one trade and the book records another, and each side looks internally
  // consistent while they differ.
  //
  // A CREDIT STRUCTURE IS PAID ON OPEN, so adding to one CREDITS cash and everything else
  // debits it. Mirrored from `backend/api/unified_positions.py` CREDIT_STRUCTURES.
  const ADD_POS_CREDIT_STRUCTURES = new Set(['credit_spread', 'put_credit_spread', 'bull_put_spread',
    'call_credit_spread', 'bear_call_spread', 'iron_condor', 'iron_butterfly',
    'short_call', 'naked_call', 'short_put', 'naked_put', 'cash_secured_put', 'covered_call']);
  // Decides the multiplier. Getting this wrong makes every options preview wrong by 100x.
  const ADD_POS_STOCK_STRUCTURES = new Set(['stock', 'shares', 'equity', 'long_stock', 'short_stock']);

  // R-IV.1173(e): a closed row has nothing to add to, so the button is not drawn at all. A
  // control that appears and then refuses is worse than one that is absent.
  const ADD_POS_ELIGIBLE = (p) => String((p && p.status) || '').toUpperCase() === 'OPEN';

  const addPosStructure = (p) => String((p && p.structure) || '').toLowerCase();
  const addPosMultiplier = (p) => ADD_POS_STOCK_STRUCTURES.has(addPosStructure(p)) ? 1 : 100;
  const addPosIsCredit = (p) => ADD_POS_CREDIT_STRUCTURES.has(addPosStructure(p));

  // Multi-leg structures can only be added in whole units: adding 3 contracts to a 2-leg
  // spread is not a bigger spread, it is a different position. Refused with the alternative
  // named, because a bare "invalid" leaves nowhere to go.
  function addPosLegRatioProblem(p, qty) {
    const legs = Number(p && p.legs_count);
    if (!Number.isFinite(legs) || legs <= 1) return null;
    if (!Number.isFinite(qty) || qty <= 0) return null;
    return null;  // whole-unit quantities are what the field collects; kept for STEP 2
  }

  function openAddToPositionForm(p) {
    const held = openQty(p);
    const credit = addPosIsCredit(p);
    const mult = addPosMultiplier(p);
    openModal('Add to ' + p.ticker, `
      <div class="add-pos-locked">
        <div><span class="add-pos-lock-label">Position</span>${esc(p.ticker + ' · ' + structureStr(p))}</div>
        <div><span class="add-pos-lock-label">Account</span>${esc(p.account_display || '—')}</div>
        <div><span class="add-pos-lock-label">Held</span>${held != null ? esc(String(held)) : 'unknown'}</div>
      </div>
      <div class="form-grid">
        <div class="fld"><label for="a_qty">Quantity to add</label>
          <input id="a_qty" type="number" min="1" step="1"></div>
        <div class="fld"><label for="a_price">Price per ${mult === 1 ? 'share' : 'contract'}</label>
          <input id="a_price" type="number" step="any"></div>
        <div class="fld"><label for="a_cost">Exact total <span class="add-pos-optional">(optional)</span></label>
          <input id="a_cost" type="number" step="any"></div>
        ${dateFieldHtml('a_when', 'Date added', '')}
        <div class="fld full"><label for="a_note">Note</label><input id="a_note"></div>
      </div>
      <div class="add-pos-preview">
        <div class="add-pos-preview-title">What this would do</div>
        <div id="a_preview" class="add-pos-preview-wait">Enter a quantity and a price.</div>
      </div>
      <div class="add-pos-refusal" id="a_refusal"></div>
      <div class="form-foot">
        <div class="form-msg" id="a_msg"></div>
        <div class="form-actions">
          <button type="button" class="btn-primary" id="a_submit" disabled>Confirm add</button>
          <button type="button" class="btn-secondary" id="a_cancel">Cancel</button>
        </div>
      </div>`);
    $('a_cancel').addEventListener('click', closeModal);
    // STEP 2 (R-IV.1243(d)): the handler exists now. Nick checked the preview on 2026-10-18 at
    // 23:54 MT and it works, which was the gate step 1 was waiting on.
    //
    // THE BUTTON STAYS `disabled` UNTIL THE PREVIEW IS VALID, and the preview is what enables
    // it -- so the enabling condition is the same computation Nick checked, not a second
    // opinion about whether the numbers are usable.
    $('a_submit').addEventListener('click', () => submitAddToPosition(p));
    ['a_qty', 'a_price', 'a_cost'].forEach((id) => {
      const el = $(id);
      if (el) el.addEventListener('input', () => updateAddToPositionPreview(p));
    });
    wireDateField('a_when');
    updateAddToPositionPreview(p);
  }

  function updateAddToPositionPreview(p) {
    const out = $('a_preview'), refusal = $('a_refusal');
    if (!out) return;
    const qty = Number($('a_qty') && $('a_qty').value);
    const price = Number($('a_price') && $('a_price').value);
    const exact = $('a_cost') && $('a_cost').value !== '' ? Number($('a_cost').value) : null;
    if (refusal) { refusal.textContent = ''; refusal.classList.remove('active'); }
    // STEP 2 (R-IV.1243(d)): THE PREVIEW OWNS THE BUTTON. Every path that cannot produce a
    // preview also disables the save, so the enabling condition is the same computation Nick
    // checked rather than a second opinion about whether the numbers are usable. It starts
    // disabled on every keystroke and is re-enabled only at the end, where the preview
    // succeeded -- a guard that has to be remembered at each early return is a guard that
    // gets missed at one of them.
    const okBtn = $('a_submit');
    if (okBtn) okBtn.disabled = true;

    if (!Number.isFinite(qty) || qty <= 0 || !Number.isFinite(price) || price <= 0) {
      out.className = 'add-pos-preview-wait';
      out.textContent = 'Enter a quantity and a price.';
      return;
    }
    const problem = addPosLegRatioProblem(p, qty);
    if (problem && refusal) {
      refusal.textContent = problem + ' Open it as a new position instead.';
      refusal.classList.add('active');
      out.className = 'add-pos-preview-wait';
      out.textContent = 'Nothing to preview while the quantity cannot be applied.';
      return;
    }

    const mult = addPosMultiplier(p);
    const credit = addPosIsCredit(p);
    const addCost = exact != null ? Math.abs(exact) : price * mult * qty;
    const held = openQty(p);
    const basisNow = p.cost_basis != null ? Math.abs(Number(p.cost_basis)) : null;
    const money = (v) => '$' + Number(v).toFixed(2);
    const lines = [];

    // Quantity: only stated when what is held is actually known. #29 -- `quantity` is the
    // size OPENED and `open_quantity` is what is held, and guessing between them here would
    // put a wrong number in front of a decision.
    if (held != null && Number.isFinite(Number(held))) {
      lines.push('Quantity goes from ' + held + ' to ' + (Number(held) + qty) + '.');
    } else {
      lines.push('Quantity goes up by ' + qty + ' — what is held now is unknown, so the new total cannot be shown.');
    }
    if (basisNow != null) {
      const newBasis = basisNow + addCost;
      lines.push('Cost basis goes from ' + money(basisNow) + ' to ' + money(newBasis) + '.');
      if (held != null && Number(held) > 0) {
        const perNow = basisNow / (Number(held) * mult);
        const perNew = newBasis / ((Number(held) + qty) * mult);
        lines.push('Average cost per ' + (mult === 1 ? 'share' : 'contract') + ' goes from '
          + money(perNow * mult) + ' to ' + money(perNew * mult) + '.');
      }
    } else {
      lines.push('Cost basis goes up by ' + money(addCost) + ' — the current basis is not recorded, so the new total cannot be shown.');
    }
    lines.push('Cash in ' + esc(p.account_display || 'this account') + ' '
      + (credit ? 'goes UP by ' + money(addCost) + ' (a credit structure is paid to you on open).'
                : 'goes DOWN by ' + money(addCost) + '.'));
    if (exact != null) {
      const perUnit = Math.abs(exact) / (mult * qty);
      lines.push('Total taken from the figure you entered: ' + money(Math.abs(exact)) + '.');
      // Stated because the SAVED price is not the price typed above. The route has no field
      // for a total, so the exact figure is recorded as the per-unit price that reproduces it
      // -- the same money, a different number in the price column, and a reader comparing the
      // lot against the ticket would otherwise find a discrepancy nobody explained.
      lines.push('Recorded price per ' + (mult === 1 ? 'share' : 'contract') + ' will be '
        + money(perUnit * mult) + ', which is that total divided by the quantity.');
    } else {
      lines.push('Total derived as ' + money(price) + ' x ' + (mult === 1 ? '' : mult + ' x ')
        + qty + ' = ' + money(addCost) + ' (derived_from_cost_basis).');
    }
    out.className = 'add-pos-preview-list';
    out.innerHTML = '<ul>' + lines.map((l) => '<li>' + l + '</li>').join('') + '</ul>';
    if (okBtn) okBtn.disabled = false;
  }

  // STEP 2's write (R-IV.1243(d)). POST one lot to the position's own route, which derives
  // quantity, entry price and cost basis from the lot set rather than taking an aggregate.
  //
  // THE DOUBLE-SUBMIT IS THE RISK HERE AND IT IS ONLY HALF-GUARDED, which is worth saying
  // plainly rather than burying: `position_lots` has NO server-side duplicate guard for a
  // manual add -- the route's guard fires only when a `broker_ref` is supplied, and a hand
  // entry has none. That is the filed defect where cash_flows refuses a duplicate same-day
  // movement and position_lots does not, leaving basis > cash with the two stores disagreeing
  // as the only detector. So this disables the button for the WHOLE round trip and holds an
  // in-flight flag as well: the flag stops a second click that arrives before the browser has
  // repainted, which `disabled` alone does not. Neither is a substitute for a server guard,
  // and the gap is reported.
  let addLotInFlight = false;
  async function submitAddToPosition(p) {
    if (addLotInFlight) return;
    const msg = $('a_msg'), btn = $('a_submit');
    const qty = Number($('a_qty') && $('a_qty').value);
    const price = Number($('a_price') && $('a_price').value);
    const exact = $('a_cost') && $('a_cost').value !== '' ? Number($('a_cost').value) : null;
    if (!Number.isFinite(qty) || qty <= 0 || !Number.isFinite(price) || price <= 0) return;
    const when = (val('a_when') || '').trim();
    const body = {
      // The route renamed these in 2026-09 and deliberately does NOT accept the old names,
      // so a stale body gets a 422 naming the field. These are the current ones.
      fill_time: when ? when : new Date().toISOString().slice(0, 10),
      qty: qty,
      price: price,
      source: 'MANUAL',
    };
    // THE EXACT TOTAL HAS NO FIELD ON THIS ROUTE, and finding that out mattered:
    // `AddLotRequest` carries fill_time / qty / price / fees / source / broker_ref / reason /
    // actor and NO cost_basis, so a `cost_basis` key would have been silently dropped by
    // Pydantic and the basis derived from price x qty instead -- the user's own broker figure
    // ignored without a word. Instead the exact total is carried as the PER-UNIT PRICE that
    // reproduces it, which is the same money by construction, and the preview says that is
    // what will be recorded.
    if (exact != null && qty > 0) {
      body.price = Math.abs(exact) / (addPosMultiplier(p) * qty);
    }
    const note = (val('a_note') || '').trim();
    if (note) body.reason = note;
    addLotInFlight = true;
    const label = btn ? btn.textContent : '';
    if (btn) { btn.disabled = true; btn.textContent = 'saving…'; }
    if (msg) { msg.className = 'form-msg'; msg.textContent = 'saving…'; }
    try {
      const r = await apiFetch('/api/v2/positions/' + encodeURIComponent(p.position_id)
        + '/lots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json',
                   'X-Requested-With': 'XMLHttpRequest' },
        body: JSON.stringify(body),
      });
      if (r.ok) {
        if (msg) { msg.className = 'form-msg ok'; msg.textContent = 'added'; }
        setTimeout(() => { closeModal(); refreshDesk(); }, 500);
      } else if (r.status === 401) {
        if (msg) { msg.className = 'form-msg err'; msg.textContent = 'sign in to add'; }
        showLogin();
      } else {
        const d = await r.json().catch(() => ({}));
        // The refusal in full, not a status code: every refusal this route gives names the
        // field or the rule it is refusing on, and shortening it to "failed" throws that away.
        if (msg) {
          msg.className = 'form-msg err';
          msg.textContent = 'refused: ' + (d.detail || r.status);
        }
      }
    } catch (_) {
      if (msg) { msg.className = 'form-msg err'; msg.textContent = 'network error'; }
    } finally {
      addLotInFlight = false;
      if (btn) { btn.disabled = false; btn.textContent = label; }
    }
  }

  function openCloseForm(p) {
    const mult = (p.asset_type || '').toUpperCase() === 'EQUITY' ? 1 : 100;
    openModal('Close ' + p.ticker, `
      <div class="form-grid">
        <div class="fld"><label>Position</label><input value="${esc(p.ticker + ' · ' + structureStr(p))}" disabled></div>
        <div class="fld"><label for="c_exit">Exit price</label><input id="c_exit" type="number" step="any" placeholder="${p.current_price != null ? p.current_price : '0.00'}"></div>
        <div class="fld"><label for="c_qty">Quantity</label>
          <input id="c_qty" type="number" min="1" value="${openQty(p) != null ? openQty(p) : ''}"
                 placeholder="${openQty(p) != null ? '' : 'how many are you closing?'}">
          <div class="fld-echo${openQty(p) != null ? '' : ' bad'}">${openQty(p) != null
            ? esc(openQty(p) + ' open · from ' + openQtyWhy(p))
            : esc('How many are open is unknown — ' + openQtyWhy(p) + '. Enter what you are closing.')}</div></div>
        ${dateFieldHtml('c_close_date', 'Close date', 'the day you closed it — today unless you say otherwise')}
        <div class="fld"><label for="c_reason">Reason</label><select id="c_reason"><option value="manual">manual</option><option value="profit">profit</option><option value="loss">loss</option></select></div>
        <div class="fld full"><label for="c_notes">Notes</label><input id="c_notes" placeholder="optional"></div>
      </div>
      <div class="form-foot">
        <div class="form-msg" id="c_msg"></div>
        <div class="form-actions"><button type="button" class="btn-danger" id="c_submit">Close position</button><button type="button" class="btn-secondary" id="c_cancel">Cancel</button></div>
      </div>`);
    $('c_cancel').addEventListener('click', closeModal);
    $('c_submit').addEventListener('click', () => submitClose(p, mult));
    wireDateField('c_close_date');
  }
  async function submitClose(p, mult) {
    const exit = $('c_exit').value !== '' ? Number($('c_exit').value) : null;
    if (exit == null) { $('c_msg').className = 'form-msg err'; $('c_msg').textContent = 'Exit price required'; return; }
    // No fallback to `quantity`: closing the size it was OPENED at, when part is already sold,
    // is the write this whole field exists to prevent.
    const qty = parseInt($('c_qty').value, 10);
    if (!Number.isFinite(qty) || qty <= 0) {
      $('c_msg').className = 'form-msg err';
      $('c_msg').textContent = 'Enter how many you are closing.';
      return;
    }
    const oq = openQty(p);
    if (oq != null && qty > oq) {
      $('c_msg').className = 'form-msg err';
      $('c_msg').textContent = 'That is more than the ' + oq + ' still open.';
      return;
    }
    const reason = $('c_reason').value;
    // R-IV.662(b)2 / TA-083: the day it was CLOSED, not the day it was recorded. Sent as
    // `exit_date`, which the close path takes (R-IV.660(c)2).
    const cd = readDateField('c_close_date');
    if (cd.err) { $('c_msg').className = 'form-msg err'; $('c_msg').textContent = cd.err; return; }
    if (!cd.iso) { $('c_msg').className = 'form-msg err'; $('c_msg').textContent = 'Enter the close date.'; return; }
    const pnl = p.unrealized_pnl != null ? Number(p.unrealized_pnl) : null;   // null is unknown, never a $0 breakeven
    const body = {
      exit_price: exit, quantity: qty, exit_value: exit * mult * qty,
      trade_outcome: pnl == null ? null : pnl > 0 ? 'WIN' : pnl < 0 ? 'LOSS' : 'BREAKEVEN',
      close_reason: reason, notes: $('c_notes').value || null, exit_date: cd.iso,
    };
    $('c_msg').className = 'form-msg'; $('c_msg').textContent = 'closing…';
    try {
      const r = await apiFetch('/api/v2/positions/' + encodeURIComponent(p.position_id) + '/close', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, body: JSON.stringify(body) });
      if (r.ok) { $('c_msg').className = 'form-msg ok'; $('c_msg').textContent = 'closed'; setTimeout(() => { closeModal(); closeDrawer(); refreshDesk(); }, 500); }
      else if (r.status === 401) { $('c_msg').className = 'form-msg err'; $('c_msg').textContent = 'sign in to close'; showLogin(); }
      else { const d = await r.json().catch(() => ({})); $('c_msg').className = 'form-msg err'; $('c_msg').textContent = 'failed: ' + (d.detail || r.status); }
    } catch (_) { $('c_msg').className = 'form-msg err'; $('c_msg').textContent = 'network error'; }
  }

  let _themeMap = {}; // ticker -> {theme, theme_score, theme_status}
  function computeConcentration(positions) {
    const list = (positions && positions.positions) || [];
    if (!list.length) return null;
    const byTheme = {}, invTheme = {}; let totalRisk = 0, skipped = 0;   // R-IV.544: rows with no figure are counted, never silent
    list.forEach((p) => {
      const risk = Math.abs(Number(p.current_value != null ? p.current_value : (p.cost_basis != null ? p.cost_basis : p.max_loss)) || 0);
      if (!risk) { skipped++; return; }
      const tm = _themeMap[(p.ticker || '').toUpperCase()];
      const theme = (tm && tm.theme) || 'Unmapped';
      byTheme[theme] = (byTheme[theme] || 0) + risk; totalRisk += risk;
      if (tm && tm.inverse) invTheme[theme] = (invTheme[theme] || 0) + risk;
    });
    if (!totalRisk) return { theme: null, pct: null, hot: false, skipped, total: list.length };
    let top = null;
    Object.keys(byTheme).forEach((t) => { if (!top || byTheme[t] > byTheme[top]) top = t; });
    const pct = Math.round((byTheme[top] / totalRisk) * 100);
    // Netting is deferred (post-flip): if the top theme is majority-inverse, say so rather
    // than imply long exposure. This is honest labeling, not direction-aware offsetting.
    const invHeavy = (invTheme[top] || 0) > byTheme[top] / 2;
    return { theme: top + (invHeavy ? ' (inverse)' : ''), pct, hot: pct > 50 && top !== 'Unmapped', skipped, total: list.length };
  }
  async function refreshThemeMap(positions) {
    const list = (positions && positions.positions) || [];
    const tickers = [...new Set(list.map((p) => (p.ticker || '').toUpperCase()).filter(Boolean))];
    if (!tickers.length) { _themeMap = {}; return; }
    try {
      const r = await apiFetch('/api/stable/enrich?tickers=' + tickers.join(','));
      if (r.ok) { const d = await r.json(); _themeMap = d.enrichment || {}; }
    } catch (_) {}
  }

  // ── b8 Kairos module ────────────────────────────────────────────────────────
  function gradeFromScore(s) { return s == null ? '·' : s >= 80 ? 'A' : s >= 65 ? 'B' : s >= 50 ? 'C' : 'D'; }
  // Decision-clock TTL: minutes remaining until a setup's expiry, or null if it carries no TTL.
  function ttlMinutes(s) {
    const raw = s.expires_at || s.decision_deadline || s.ttl_at;
    if (!raw) return null;
    const t = Date.parse(String(raw).replace('Z', '+00:00').replace(/([+-]\d{2}:\d{2})?$/, (m) => m || '+00:00'));
    if (isNaN(t)) return null;
    return Math.round((t - Date.now()) / 60000);
  }
  function ttlLabel(m) {
    if (m <= 0) return 'expiring';
    if (m < 60) return m + 'm';
    const h = Math.floor(m / 60); return h + 'h' + (m % 60 ? ' ' + (m % 60) + 'm' : '');
  }
  // Grade v1 — validated-cell table (promotions are a data edit, not code). A ONLY on a
  // validated cell; else B if ≥2 real evidence icons lit, C otherwise. Shadow never exceeds shadow.
  const VALIDATED_A_CELLS = [{ side: 'SHORT', regime: 'URSA', liquid: true }];
  // The table in words, for the Actionable lane's empty reason. Read off the table so a
  // promotion (a data edit) rewrites the sentence with it.
  const validatedCellText = () => VALIDATED_A_CELLS.map((c) =>
    (c.liquid === true ? 'liquid ' : c.liquid === false ? 'illiquid ' : '') + String(c.side || '').toLowerCase() + ' in ' + c.regime).join(', or a ');
  // currentRegime() collapses a missing read to NEUTRAL, which is the safe direction for GRADING
  // (no A) and the wrong one for SAYING WHY: "no A is possible in NEUTRAL" would assert a regime
  // nobody read. Anything that prints the reason asks this first.
  const regimeKnown = () => !!(_lastRegime.composite && (_lastRegime.composite.bias_level || _lastRegime.composite.level));
  function currentRegime() {
    const bias = (_lastRegime.composite && (_lastRegime.composite.bias_level || _lastRegime.composite.level)) || '';
    return /URSA|BEAR/.test(bias) ? 'URSA' : /TORO|BULL/.test(bias) ? 'TORO' : 'NEUTRAL';
  }
  function gradeV1(s, litCount) {
    const side = (s.direction || '').toUpperCase();
    const reg = currentRegime();
    const isA = VALIDATED_A_CELLS.some((c) =>
      c.side === side && c.regime === reg && (c.liquid === undefined || c.liquid === !!s.is_liquid));
    if (isA) return 'A';
    return litCount >= 2 ? 'B' : 'C';
  }
  // Shared evidence eval (post-L-deepening): R = regime align, F = flow, L = at a Pythia level; C reserved.
  function evalEvidence(s, levelMap, bull, bear) {
    const side = (s.direction || '').toUpperCase();
    const rOk = (side === 'LONG' && bull) || (side === 'SHORT' && bear);
    const rWarn = (side === 'LONG' && bear) || (side === 'SHORT' && bull);
    const rCls = rOk ? 'ev-ok' : rWarn ? 'ev-warn' : 'ev-off';
    const ed = s.enrichment_data || {};
    const fCls = ed.flow || ed.market_structure ? 'ev-ok' : 'ev-off';
    let lCls = 'ev-off', lChar = '·';
    const lv = levelMap && levelMap[(s.ticker || '').toUpperCase()];
    if (lv && lv.available && lv.levels) {
      const px = s.entry_price != null ? Number(s.entry_price) : lv.levels.price_at_event;
      const cands = [lv.levels.vah, lv.levels.val, lv.levels.poc].filter((x) => x != null).map(Number);
      if (px && cands.length && Math.min(...cands.map((x) => Math.abs(px - x))) / px < 0.004) { lCls = 'ev-ok'; lChar = '✓'; }
    }
    const litCount = [rCls, fCls, lCls].filter((c) => c === 'ev-ok').length;
    return { side, rOk, rWarn, rCls, fCls, lCls, lChar, litCount };
  }

  // ── R-IV.569 · the River in lanes ──────────────────────────────────────────
  // The five lanes read the same rows the classic stream reads; what changes is that each row
  // is placed by what the principal can DO with it. `_laneData` is the last measurement
  // loadKairos took — the graded roster, the classes that never grade, and the counts the
  // lanes are obliged to disclose (what was read, and what was excluded).
  let _laneData = null;
  // R-IV.606(b) — the two halves of "Your book" arrive on DIFFERENT reads. `touches` rides on a
  // signal row (`/api/trade-ideas`); `exit` rides on a position row (`/api/v2/positions`). This
  // is the join, keyed by position_id, refreshed from whichever read last returned positions.
  // `null` means no position read has succeeded — which is NOT the same as a position with no
  // written plan, and the lane says so rather than reading both as "No exit written".
  let _bookExits = null;
  function setBookExits(positions) {
    const rows = (positions && (positions.positions || positions.rows)) || (Array.isArray(positions) ? positions : null);
    if (!rows) return;                       // a failed read leaves the last good map alone
    const m = {};
    rows.forEach((p) => { if (p && p.position_id) m[p.position_id] = { exit: p.exit || null, ticker: p.ticker, structure: p.structure }; });
    _bookExits = m;
  }
  const LANE_LEVEL_MAX = 24;      // how many names one cycle reads level evidence for
  // Level evidence is one read per ticker and the desk refreshes every two minutes, so reading
  // 24 names every cycle would put 24 concurrent requests against a pool of 10. Cache each
  // ticker's levels briefly and fetch a few at a time; MP levels move on Pine events, not on
  // this page's clock, and nothing displays a time taken from them.
  const LEVEL_TTL_MS = 4 * 60 * 1000, LEVEL_CONCURRENCY = 4;
  const _levelCache = new Map();   // TICKER -> { at, data }
  async function readLevels(tickers) {
    const now = Date.now(), out = {}, todo = [];
    tickers.forEach((tk) => {
      const hit = _levelCache.get(tk);
      if (hit && now - hit.at < LEVEL_TTL_MS) { if (hit.data) out[tk] = hit.data; } else todo.push(tk);
    });
    for (let i = 0; i < todo.length; i += LEVEL_CONCURRENCY) {
      await Promise.all(todo.slice(i, i + LEVEL_CONCURRENCY).map(async (tk) => {
        let d = null;
        try { const r = await apiFetch('/api/board/levels/' + encodeURIComponent(tk)); if (r.ok) d = await r.json(); } catch (_) {}
        _levelCache.set(tk, { at: Date.now(), data: d });
        if (d) out[tk] = d;
      }));
    }
    return out;
  }
  const LANE_CONTEXT_MAX = 12;    // how many context items the Context lane shows
  const RIVER_VIEW_KEY = 'agora.river.view';
  let _riverView = 'lanes';
  try { const v = localStorage.getItem(RIVER_VIEW_KEY); if (v === 'classic' || v === 'lanes') _riverView = v; } catch (_) {}

  // R-IV.579(a)1 — the page's crypto FILTER is gone. The server excludes crypto from every feed
  // from one author (`backend/config/asset_class.py`, RV4), and two filters for one rule is how a
  // regression gets hidden twice and therefore never noticed. What is left is the opposite of a
  // filter: a test that says a row SHOULD NOT BE HERE, so the row is shown with an error on it.
  //
  // Exactly the server's predicate (`COALESCE(asset_class,'') <> 'CRYPTO'`) and nothing looser:
  // the ticker-shape fallback is gone with the filter, because painting an error on a row the
  // server never claimed was crypto would be a false alarm about a regression that did not happen.
  const isCryptoLeak = (s) => String(s.asset_class == null ? '' : s.asset_class).trim().toUpperCase() === 'CRYPTO';

  // R-IV.579(a)3 — WHERE A ROW GOES is the server's claim (`strategy_class`, R-IV.577(b)), not a
  // guess read off `codename`. `codename` is a DISPLAY field that is null when unmapped, so
  // "not on the roster" and "the display layer did not run" used to arrive as one thing. It still
  // names the row; it no longer places it.
  //
  // A missing class is not quietly re-inferred. The field is documented as never null, so its
  // absence is a server regression, and the row goes to Unproven and says so — because inferring
  // it again here would restore, silently, exactly the fragility the field was added to remove.
  const STRATEGY_CLASSES = ['roster', 'shadow', 'non-roster'];
  const strategyClass = (s) => {
    const c = String(s.strategy_class == null ? '' : s.strategy_class).trim().toLowerCase();
    return STRATEGY_CLASSES.indexOf(c) >= 0 ? c : null;
  };

  // The feed serves 50 rows a page, ordered by score, and crypto can fill a whole page — so a
  // single page is not "today's ideas", it is "today's crypto". Page until the feed is read out
  // or the ceiling is hit, dedupe, and hand back what was read AND what the feed says exists,
  // so a truncated read can be said out loud instead of looking like a quiet day.
  const IDEA_PAGE = 50, IDEA_MAX_PAGES = 3;
  async function fetchIdeaPages() {
    const seen = new Set(), out = [];
    let total = null, pages = 0, answered = false;
    for (let p = 0; p < IDEA_MAX_PAGES; p++) {
      let d = null;
      try {
        const r = await apiFetch('/api/trade-ideas?status=ACTIVE&limit=' + IDEA_PAGE + '&offset=' + (p * IDEA_PAGE));
        if (r.ok) d = await r.json();
      } catch (_) {}
      if (!d) break;
      answered = true; pages++;
      if (total == null && d.total != null && Number.isFinite(Number(d.total))) total = Number(d.total);
      const rows = d.signals || [];
      rows.forEach((s) => { const k = s.signal_id || (s.ticker + ':' + s.timestamp); if (!seen.has(k)) { seen.add(k); out.push(s); } });
      if (rows.length < IDEA_PAGE) break;
    }
    return { signals: out, read: out.length, total: total, pages, answered };
  }

  async function loadKairos() {
    const feed = await fetchIdeaPages();
    const el = $('kairosCards'); if (!el) return;
    // Nothing is dropped here any more. Every row the feed returned is rendered; the ones that
    // should not have come are rendered WITH THEIR ERROR.
    const signals = feed.signals;
    const cryptoLeak = signals.filter(isCryptoLeak);
    const tickers = [...new Set(signals.map((s) => (s.ticker || '').toUpperCase()).filter(Boolean))];
    let smap = {};
    if (tickers.length) { try { const r = await apiFetch('/api/stable/enrich?tickers=' + tickers.join(',')); if (r.ok) smap = (await r.json()).enrichment || {}; } catch (_) {} }
    // R-IV.593(b)1: rank by the server's one score. R-IV.593(b)2: an UNSCORED row sorts last
    // rather than as a zero — `|| 0` would have put it above any row the server scored below
    // nothing, and would have made "nobody scored this" indistinguishable from "this scored 0".
    const scoreOf = canonicalScore;
    const byScore = (a, b) => {
      const x = scoreOf(a), y = scoreOf(b);
      if (x == null && y == null) return 0;
      if (x == null) return 1;
      if (y == null) return -1;
      return y - x;
    };

    // Placement, from the server's class. `roster` grades and can reach Actionable; `shadow` and
    // `non-roster` never grade and sit in Unproven; a row with no class the server recognises is
    // `unclassed` — held with the ungraded rows and disclosed, never promoted on a guess.
    //
    // The display map still gets a veto in ONE direction: a family it marks shadow is not graded
    // even if the server calls it roster. Refusing to grade something the page believes is shadow
    // is the safe way to disagree; grading something it believes is shadow is not.
    const roster = [], shadow = [], nonRoster = [], unclassed = [];
    signals.forEach((s) => {
      const cls = strategyClass(s);
      const d = setupDisplay(s.codename || s.signal_type || s.strategy);
      if (cls === null) unclassed.push(s);
      else if (cls === 'shadow' || d.shadow) shadow.push(s);
      else if (cls === 'roster') roster.push(s);
      else nonRoster.push(s);
    });
    roster.sort(byScore);

    // L-evidence for every roster row the LANES will print, not just the top cards: the Watch
    // lane shows each row's grade, and a grade computed without its L evidence can read one step
    // low. Capped — a row past the cap says "grade pending" rather than a grade it cannot stand.
    const lvlTickers = [...new Set(roster.map((s) => (s.ticker || '').toUpperCase()).filter(Boolean))].slice(0, LANE_LEVEL_MAX);
    const lvlAsked = new Set(lvlTickers);
    const levelMap = await readLevels(lvlTickers);
    const bias = _lastRegime.composite ? (_lastRegime.composite.bias_level || '') : '';
    const biasBull = /TORO|BULL/.test(bias), biasBear = /URSA|BEAR/.test(bias);

    // Grade + evidence per roster signal; order by grade (A>B>C) then score.
    const gradeRank = { A: 3, B: 2, C: 1 };
    roster.forEach((s) => {
      s._ev = evalEvidence(s, levelMap, biasBull, biasBear);
      s._grade = gradeV1(s, s._ev.litCount);   // shadow never reaches this list (split above)
      // A is decided by the validated cell alone, and B is already reached on R+F — so only a C
      // computed WITHOUT this ticker's levels is in doubt (its L could have been the second icon).
      s._gradePending = s._grade === 'C' && !lvlAsked.has((s.ticker || '').toUpperCase());
    });
    roster.sort((a, b) => (gradeRank[b._grade] || 0) - (gradeRank[a._grade] || 0) || byScore(a, b));

    const visible = roster.slice(0, 3), queued = roster.length - visible.length;
    const ungraded = shadow.length + nonRoster.length + unclassed.length;
    $('kairosQueued').textContent = [queued > 0 ? '+' + queued + ' queued' : null,
      ungraded ? '+' + ungraded + ' ungraded → river' : null].filter(Boolean).join(' · ');
    el.innerHTML = visible.length ? visible.map((s) => card(s, smap)).join('')
      : '<div class="k-card"><span class="val-muted">no roster setups' + (ungraded ? ' — ' + ungraded + ' ungraded in river' : '') + '</span></div>';
    applyGlossary(el);
    el.querySelectorAll('.btn-committee[data-ticker]').forEach((b) => b.addEventListener('click', () => {
      const c = b.closest('.k-card'); if (c) c.classList.add('acked');  // acknowledge -> stop the decision-clock pulse
      openCommittee(b.dataset.ticker, b.dataset.sig, b);
    }));

    // The classic stream: the top graded rows plus every row that never grades. Which ITEM
    // BUILDER a row gets is a display question, not a placement one — a class the display map
    // knows keeps its name and its standing banner (CIRCE'S STEW must carry its banner on every
    // fire, R-IV.427(b)); only a class the map has never heard of appears under a raw identifier.
    const streamRow = (s) => (setupDisplay(s.codename || s.signal_type || s.strategy).roster
      ? signalRiverItem(s, smap) : nonRosterRiverItem(s));
    addRiverItems(visible.map((s) => signalRiverItem(s, smap)));
    addRiverItems([...shadow, ...nonRoster, ...unclassed].map(streamRow));
    // A row with an error is never cut by the top-3 gate. The gate is an attention budget for
    // ideas; a regression is not an idea, and a stream that drops it is the second place it hides.
    addRiverItems(roster.filter((s) => visible.indexOf(s) < 0 && rowError(s)).map((s) => signalRiverItem(s, smap)));
    // What the lanes render, and the disclosures they owe: this is a MEASUREMENT of one read,
    // never a carry-over. A failed read publishes read:0 and answered:false, and the Actionable
    // lane says the feed did not answer instead of naming a regime as the reason.
    _laneData = {
      at: Date.now(), roster, shadow, nonRoster, unclassed,
      cryptoLeak, read: feed.read, total: feed.total,
      // A row the server could not score sorts last and shows no number. Said out loud, because
      // otherwise it is just a row that quietly sank — and a field that stopped arriving at all
      // would look exactly the same from the top of the lane.
      unscored: signals.filter((x) => canonicalScore(x) == null).length,
      pages: feed.pages, answered: feed.answered,
      levelCapped: Math.max(0, new Set(roster.map((s) => (s.ticker || '').toUpperCase())).size - LANE_LEVEL_MAX),
    };
    renderRiver();

    function card(s, smap) {
      const disp = setupDisplay(s.codename || s.signal_type || s.strategy);
      const ttl = ttlMinutes(s);
      const ev = s._ev; const side = ev.side;
      const sideCls = side === 'LONG' ? 'side-long' : side === 'SHORT' ? 'side-short' : '';
      const tm = smap[(s.ticker || '').toUpperCase()];
      const themeTag = tm && tm.theme ? `${esc(tm.theme)}${tm.theme_score != null ? ' ' + Math.round(tm.theme_score) : ''}${tm.theme_status ? ' ' + String(tm.theme_status).slice(0, 3).toLowerCase() : ''}${tm.inverse ? ' (inv)' : ''}` : '';
      const shadow = disp.shadow;
      const grade = s._grade;
      // R-IV.900(b): the upgrade keeps the strategy's own name and adds a tag and an outline. The
      // pulse is on only while the signal is fresh, per the principal's approved option.
      const up = upgradeOf(s);
      const upCls = up ? ` upgraded ${UPGRADE_CLASS[up]}${isFresh(s) ? ' fresh' : ''}` : '';
      return `<div class="k-card${shadow ? ' shadow' : ''}${upCls}">
        <div class="top"><span class="nm">${signalTitle(s, disp)}</span>${up ? `<span class="upgrade-tag">${esc(up)}</span>` : ''}
          <span class="grade ${grade === 'A' ? 'val-up' : ''}" data-gloss="GRADE">${grade}</span></div>
        <div class="lvls"><span class="tkr" data-ticker="${esc(s.ticker)}" data-chart="${esc(String(s.ticker || '').toUpperCase())}" tabindex="0" role="button">${esc(s.ticker)}</span>
          <span class="${sideCls}">${side || ''} ${s.entry_price != null ? Number(s.entry_price).toFixed(2) : ''}</span>
          ${s.target_1 != null ? `<span>T ${Number(s.target_1).toFixed(2)}</span>` : ''}
          ${s.stop_loss != null ? `<span>S ${Number(s.stop_loss).toFixed(2)}</span>` : ''}
          ${s.timeframe ? `<span class="val-muted">${esc(s.timeframe)}</span>` : ''}</div>
        <div class="k-evidence"><span class="${ev.rCls}" data-gloss="R">R${ev.rOk ? '✓' : ev.rWarn ? '⚠' : '·'}</span>
          <span class="${ev.fCls}" data-gloss="F">F${ev.fCls === 'ev-ok' ? '✓' : '·'}</span>
          <span class="${ev.lCls}" data-gloss="L">L${ev.lChar}</span><span class="ev-off" data-gloss="C">C·</span></div>
        <div class="foot">${themeTag ? `<span class="k-theme">${themeTag}</span>` : ''}${shadow ? '<span class="shadow-tag">shadow</span>' : (ttl != null ? `<span class="clock-chip pulse-teal" data-gloss="CLOCK">⏱ ${ttlLabel(ttl)}</span>` : '')}
          <button class="btn-committee" data-ticker="${esc(s.ticker)}" data-sig="${esc(s.signal_id || '')}">Committee</button></div>
      </div>`;
    }
  }
  function openCommittee(ticker, sig, src) {
    openDrawer('committee', { ticker, sig }, src);
  }

  // ── b9 River ────────────────────────────────────────────────────────────────
  const _river = new Map();  // id -> item
  const _rvAcked = new Set(); // acknowledged action-item ids (pulse stops)
  // ── River notices (BUILD's contract) ───────────────────────────────────────
  // GET /api/trade-ideas/notices -> {notices:[{id, since, until, title, body}]}. An empty
  // list, an unreadable payload, or a route that is not there yet all mean the same thing:
  // nothing to show. A notice is an operator message about the feed, never an alarm, so it
  // never raises an error state in the River.
  let _notices = [];
  function parseNotices(data) {
    const list = data && Array.isArray(data.notices) ? data.notices : [];
    return list.filter((n) => n && n.id && (n.title || n.body)).map((n) => ({
      id: String(n.id), title: n.title == null ? '' : String(n.title),
      body: n.body == null ? '' : String(n.body), since: n.since, until: n.until,
    }));
  }
  // A missing or unparseable bound is an OPEN bound: the server sent the notice, so the
  // default is to show it. Only a bound we can read is allowed to hide one.
  function activeNotices(now) {
    const ms = (v) => { const t = Date.parse(v); return Number.isFinite(t) ? t : null; };
    return _notices.filter((n) => {
      const a = ms(n.since), b = ms(n.until);
      return !(a != null && now < a) && !(b != null && now > b);
    });
  }
  async function loadNotices() {
    let data = null;
    try { const r = await apiFetch('/api/trade-ideas/notices'); if (r.ok) data = await r.json(); } catch (_) {}
    _notices = parseNotices(data);
    renderRiver();
  }
  let _riverFilter = 'all';
  // R-IV.563 (RV2/RV3) -- the River's clock. An item's time is the time IT carries, or nothing:
  // never Date.now() at poll time (that made every item "new" at any hour and re-stamped it on
  // every refresh). Anything without a time reads "time unknown", sorts last, and stays that way.
  const OFFSETLESS_TS = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?$/;
  function apiTime(v) {
    if (v == null || v === '') return null;
    if (typeof v === 'number') return Number.isFinite(v) ? (v > 1e11 ? v : v * 1000) : null;
    const s = String(v).trim();
    // The API's timestamps are UTC. A browser reads an offset-less "2026-09-24T19:45:00" as LOCAL
    // time, hours off; say UTC explicitly. (BUILD's RV1 will add the offset; this is right either way.)
    if (OFFSETLESS_TS.test(s)) { const t = Date.parse(s.replace(' ', 'T') + 'Z'); return Number.isFinite(t) ? t : null; }
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;      // a date with no time of day is not a time
    const t = Date.parse(s); return Number.isFinite(t) ? t : null;
  }
  const firstTime = (...vals) => { for (const v of vals) { const t = apiTime(v); if (t != null) return t; } return null; };
  // "1:45 PM MT"; with the day when it is not today (Denver's day): "Wed 1:45 PM MT".
  function riverTime(ms) {
    if (ms == null) return null;
    const tz = 'America/Denver', d = new Date(ms);
    const ymd = (t) => new Intl.DateTimeFormat('en-CA', { timeZone: tz }).format(new Date(t));
    const clock = new Intl.DateTimeFormat('en-US', { timeZone: tz, hour: 'numeric', minute: '2-digit', hour12: true }).format(d).replace(/[\u202f\u00a0]/g, ' ');
    if (ymd(ms) === ymd(Date.now())) return clock + ' MT';
    const recent = Math.abs(Date.now() - ms) < 6 * 864e5;
    const pre = new Intl.DateTimeFormat('en-US', recent ? { timeZone: tz, weekday: 'short' } : { timeZone: tz, month: 'short', day: 'numeric' }).format(d);
    return pre + ' ' + clock + ' MT';
  }
  // ── R-IV.591 · a signal that was HELD says when it actually fired ──────────
  // BUILD holds a signal fired outside the regular session to the next open (R-IV.587(b)):
  // `release_at` is the hold, `fired_at` is when the setup appeared, and the fire time is never
  // rewritten to the release.
  //
  // THE TEST IS `release_at`, NOT `held`. The feed only serves rows whose hold has passed
  // (`SERVE_RELEASED_SQL`: release_at IS NULL OR release_at <= NOW()), and `held` means "still
  // waiting" — so on this page `held` is ALWAYS false, and a label built on it would never
  // render once. A non-null `release_at` is the durable record that this row WAS held.
  const heldRelease = (s) => apiTime(s && s.release_at);
  // R-IV.585(c): the phrase per session, and only these. `regular` gets the label with NO phrase
  // (a held signal that fired in the regular session was held for some other reason, and the
  // label must not imply one); a null — or any spelling this page does not know — gets NO LABEL,
  // because "the market was shut" and "nobody knows" are different claims.
  const SESSION_PHRASE = { after_hours: 'after the close', pre_market: 'before the open',
    closed: 'while the market was closed', regular: '' };
  // R-IV.585(b)/591(b): ONE formatter. riverTime() verbatim, never a second time format.
  function heldLabel(s) {
    if (heldRelease(s) == null) return '';
    const sess = String(s.session == null ? '' : s.session).trim().toLowerCase();
    if (!Object.prototype.hasOwnProperty.call(SESSION_PHRASE, sess)) return '';
    const t = riverTime(firstTime(s.fired_at, s.timestamp, s.created_at));
    if (t == null) return '';                  // no fire time to state, so nothing is stated
    return 'fired ' + t + (SESSION_PHRASE[sess] ? ' · ' + SESSION_PHRASE[sess] : '');
  }
  // R-IV.591(b): the row sits where it became actionable. Both are stamps the row carries, so
  // R-IV.563 holds either way — this is not a substituted time, it is the other real one.
  const rowTime = (s) => { const r = heldRelease(s); return r != null ? r : firstTime(s.fired_at, s.timestamp, s.created_at); };

  // ── R-IV.832(a) / R-IV.900(b) · "FIGURE | Description", and the APIS/KODIAK upgrade ───────
  //
  // ONE SERVED STRING. `display_label` is the backend's single author of names (R-IV.833).
  // IT IS NOT SERVED YET -- nothing in backend/ mentions the field -- so this falls back to the
  // name and description the page already holds, which is what R-IV.832(c) directs. The approved
  // FORMAT applies either way; what the fallback cannot supply is a name for a strategy
  // `SETUP_MAP` has no entry for, and MIDAS, HECTOR and NEMESIS are those: they render their raw
  // identifier today, exactly as they do now, until the field arrives.
  //
  // Nothing here derives a name. The pipe is a separator, not a value.
  function titleParts(s, disp) {
    const served = s && typeof s.display_label === 'string' ? s.display_label.trim() : '';
    if (served) {
      const i = served.indexOf('|');
      return i < 0 ? { figure: served, what: '' }
                   : { figure: served.slice(0, i).trim(), what: served.slice(i + 1).trim() };
    }
    return { figure: disp.name || 'SETUP', what: disp.desc || '' };
  }
  // R-IV.938(b): the CODENAME is shown in capitals and the description is not, which is what the
  // principal approved. It is done by STYLING, not by upper-casing the string: BUILD keeps serving
  // Title Case, the page keeps rendering what it was served, and a copy/paste still carries the
  // served spelling. So the figure gets a span of its own to carry that rule.
  function signalTitle(s, disp) {
    const p = titleParts(s, disp);
    const fig = '<span class="figure">' + esc(p.figure) + '</span>';
    if (!p.what) return fig;
    return fig + ' <span class="sep">|</span> <span class="what">' + esc(p.what) + '</span>';
  }

  // The tag is the SERVER's word. An unrecognised one gets no treatment rather than the wrong
  // one: a bull glow on a bear tag would be worse than no glow at all.
  const UPGRADE_CLASS = { APIS: 'apis', KODIAK: 'kodiak' };
  function upgradeOf(s) {
    const t = String((s && s.upgrade_tag) || '').trim().toUpperCase();
    return UPGRADE_CLASS[t] ? t : null;
  }

  // FRESH, for the approved "pulse while fresh". Keyed on `rowTime` -- the instant the card
  // already shows -- which for a HELD signal is its RELEASE (R-IV.585(a)). A setup that fired at
  // 4am and reached the desk at 9:30 is new at 9:30; keying on the fire time would mean the rows
  // that most need attention never pulse at all.
  //
  // This reads the clock against a served instant, exactly as the row's own time label does. It
  // is not a derived FIELD: a server-side `is_fresh` would be stale between polls, which is the
  // argument for computing it at render.
  const FRESH_MINUTES = 15;
  function isFresh(s) {
    const t = rowTime(s);
    return t != null && (Date.now() - t) < FRESH_MINUTES * 60000;
  }

  function addRiverItems(items) { (items || []).forEach((it) => { if (it && it.id) _river.set(it.id, it); }); }
  function signalRiverItem(s, smap) {
    const disp = setupDisplay(s.codename || s.signal_type || s.strategy);
    const shadow = disp.shadow;
    const side = (s.direction || '').toUpperCase();
    const grade = s._grade;  // grade v1 (attached in loadKairos) — never the legacy score
    return {
      id: 'sig:' + (s.signal_id || s.ticker + s.timestamp), type: 'signal',
      // A bannered shadow keeps full opacity: the .shadow tier's 0.5 opacity would drop the
      // amber banner to 3.08:1 on --panel, and a warning nobody can read is not a warning.
      tier: disp.banner ? 'shadow-banner' : shadow ? 'shadow' : (grade === 'A' || grade === 'B' ? 'action' : 'info'),
      sev: side === 'LONG' ? 'up' : side === 'SHORT' ? 'down' : 'teal',
      ts: rowTime(s),
      riverOnly: !!disp.riverOnly,
      text: `<b>${esc(disp.name)}</b> ${chartTk(s.ticker)} ${side}${s.entry_price != null ? ' @ ' + Number(s.entry_price).toFixed(2) : ''}${grade ? ' · grade ' + grade : ''}`
        // The same flag in the other view: one River, and neither view is the one that omits it.
        + (s.high_score === true ? ` · <span class="rv-high" title="${esc(canonicalScore(s) == null ? 'Scores high, but not a validated setup. Actionable needs an A.' : 'Scores ' + canonicalScore(s) + ': high, but not a validated setup. Actionable needs an A.')}">high score${canonicalScore(s) == null ? '' : ' ' + canonicalScore(s)}</span>` : '')
        + (disp.banner ? `<div class="rv-banner">${esc(disp.banner)}</div>` : '')
        + (heldLabel(s) ? `<div class="rv-held">${esc(heldLabel(s))}</div>` : '')
        // R-IV.579(a)2: the same error the lanes show, so neither view is the one that hides it.
        + (rowError(s) ? `<div class="rv-err">${esc(rowError(s))}</div>` : ''),
    };
  }
  // Non-roster classes never render as Kairos cards — they surface here under their raw name.
  function nonRosterRiverItem(s) {
    const raw = s.signal_type || s.strategy || 'SETUP';
    const side = (s.direction || '').toUpperCase();
    return {
      id: 'nr:' + (s.signal_id || raw + (s.ticker || '')), type: 'signal', tier: 'info',
      sev: side === 'LONG' ? 'up' : side === 'SHORT' ? 'down' : null,
      ts: rowTime(s),
      text: `<span class="rv-raw">${esc(raw)}</span> ${chartTk(s.ticker)} ${side}${s.entry_price != null ? ' @ ' + Number(s.entry_price).toFixed(2) : ''} <span class="val-muted">· non-roster</span>`
        + (heldLabel(s) ? `<div class="rv-held">${esc(heldLabel(s))}</div>` : ''),
    };
  }
  function emitRegimeRiverItems(composite, regime, kill) {
    // Lenses split — the same rule as the band's chip: opposite calls by each lens's OWN
    // cut-offs (was 55/45 on the dial, which fired while the composite label still read NEUTRAL).
    if (composite && regime) {
      const v1 = lens1View(composite), v2 = lens2View(regime);
      if (lensSplit(v1, v2)) {
        // Timed by the composite read that produced it, so it ranks among the newest context
        // items instead of sinking below the lane's cut as a no-time item.
        addRiverItems([{ id: 'split:' + v1.dir + ':' + v2.dir, type: 'regime', tier: 'action', sev: 'teal', ts: apiTime(composite.timestamp),
          text: `<b>Lenses split</b> — Market mix ${esc(v1.call)} vs Theme breadth ${esc(v2.call)}. Size with caution.` }]);
      }
    }
    const k = kill && kill.kill_switch;
    if (k && k.active) {
      addRiverItems([{ id: 'kill:' + (k.trigger || '') + ':' + (k.triggered_at || ''), type: 'regime', tier: 'action', sev: 'down', ts: apiTime(k.triggered_at),
        text: `<b>Kill-switch ARMED</b> — ${esc(k.trigger || 'risk-off')}${k.description ? ' · ' + esc(k.description) : ''}` }]);
    }
    renderRiver();
  }
  async function loadDeskStreams() {
    // flow radar (position flow + headlines) + hermes catalysts
    let flow = null, hermes = null;
    try { const r = await apiFetch('/api/flow/radar'); if (r.ok) flow = await r.json(); } catch (_) {}
    try { const r = await apiFetch('/api/hermes/alerts?limit=12'); if (r.ok) hermes = await r.json(); } catch (_) {}
    const items = [];
    if (flow) {
      (flow.position_flow || []).slice(0, 8).forEach((f, i) => {
        const align = (f.alignment || '').toUpperCase();
        if (align === 'NEUTRAL' || !align) return;
        items.push({ id: 'flow:' + (f.ticker || i) + ':' + align, type: 'flow',
          tier: f.strength === 'STRONG' ? 'action' : 'info', sev: align === 'CONFIRMING' ? 'up' : 'down', ts: null,
          text: `<b>${chartTk(f.ticker)}</b> flow ${align.toLowerCase()}${f.strength ? ' (' + esc(f.strength.toLowerCase()) + ')' : ''} vs your position` });
      });
      (flow.watchlist_unusual || []).slice(0, 5).forEach((w, i) => {
        items.push({ id: 'unusual:' + (w.ticker || i), type: 'flow', tier: 'info', sev: 'teal', ts: null,
          text: `Unusual flow · <b>${chartTk(w.ticker)}</b>${w.sentiment ? ' ' + esc(w.sentiment) : ''}` });
      });
      (flow.headlines || []).slice(0, 6).forEach((h, i) => {
        const hl = h.headline || h.title || ''; if (!hl) return;
        items.push({ id: 'hl:' + hl.slice(0, 40), type: 'headline', tier: 'info', sev: null,
          ts: apiTime(h.created_at), text: esc(hl) });
      });
    }
    if (hermes) {
      (hermes.alerts || []).forEach((a) => {
        items.push({ id: 'herm:' + (a.id || a.trigger_ticker), type: 'catalyst',
          tier: (a.tier <= 1 ? 'action' : 'info'), sev: 'down', ts: apiTime(a.created_at),
          text: `<b>${chartTk(a.trigger_ticker)}</b> ${esc(a.headline_summary || a.event_type || 'catalyst')}` });
      });
    }
    // Cowork stable digest (optional — render only if present)
    try {
      const r = await _rawFetch('/stable_digest.md', { cache: 'no-store' });
      if (r.ok) {
        const txt = (await r.text()).trim();
        if (txt && txt[0] !== '<') items.push({ id: 'stable:digest', type: 'stable', tier: 'info', sev: 'teal', ts: apiTime(r.headers.get('Last-Modified')), text: '<b>Stable digest</b> · ' + esc(txt.split('\n')[0].slice(0, 160)) });
      }
    } catch (_) {}
    addRiverItems(items);
    renderRiver();
  }
  // Notice rows belong to the River, not to one of its views: both render them at the top.
  function noticeRowsHtml(now) {
    return activeNotices(now).map((n) =>
      `<div class="rv-notice" data-nid="${esc(n.id)}">`
      + (n.title ? `<span class="rv-notice-t">${esc(n.title)}</span>` : '')
      + (n.body ? `<span class="rv-notice-b">${esc(n.body)}</span>` : '')
      + '</div>').join('');
  }

  // Two views of one River. `hidden` alone is not enough: .river and .river-lanes set display,
  // which beats the UA's [hidden] rule — the CSS carries the matching [hidden] resets (the
  // sign-in overlay shipped covering the page for exactly this reason). And the lanes are the
  // default only where there IS a lanes container: a browser holding a cached copy of the older
  // markup must get the stream it can render, not an empty tile.
  const lanesView = () => _riverView === 'lanes' && !!$('riverLanes');
  function applyRiverView() {
    const lanes = lanesView();
    const L = $('riverLanes'), S = $('riverStream'), P = $('riverPills'), B = $('riverViewBtn');
    if (L) L.hidden = !lanes;
    if (S) S.hidden = lanes;
    if (P) P.hidden = lanes;
    if (B) {
      B.textContent = lanes ? 'Classic view' : 'Lanes';
      B.title = lanes ? 'Show the classic single stream instead of the five lanes. Same items, one list.'
        : 'Show the five lanes: Actionable, Your book, Watch, Unproven, Context.';
      B.setAttribute('aria-pressed', String(!lanes));
    }
  }
  function setRiverView(v) {
    _riverView = v === 'classic' ? 'classic' : 'lanes';
    try { localStorage.setItem(RIVER_VIEW_KEY, _riverView); } catch (_) {}
    renderRiver();
  }
  document.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('#riverViewBtn');
    if (b) { e.preventDefault(); setRiverView(_riverView === 'lanes' ? 'classic' : 'lanes'); }
  });

  function renderRiver() {
    applyRiverView();
    if (lanesView()) renderLanes(); else renderClassicRiver();
  }

  // ── The five lanes (R-IV.569) ─────────────────────────────────────────────
  // Placement, not new data: every row here is a row the classic stream also has. A lane says
  // what the row is FOR — act on it, defend the book, watch it, or just know it.
  function laneShell(title, count, body, opts) {
    const o = opts || {};
    const head = `<span class="rl-t">${esc(title)}</span>`
      + `<span class="rl-count${o.countUnknown ? ' unknown' : ''}"${o.countTitle ? ` title="${esc(o.countTitle)}"` : ''}>${esc(String(count))}</span>`
      + (o.note ? `<span class="rl-note">${esc(o.note)}</span>` : '');
    if (o.collapsed) return `<details class="rl-lane" data-lane="${esc(o.key || title)}"${o.open ? ' open' : ''}><summary>${head}</summary>${body}</details>`;
    return `<section class="rl-lane" data-lane="${esc(o.key || title)}"><h3 class="rl-h">${head}</h3>${body}</section>`;
  }
  function laneTime(s) {
    const t = riverTime(rowTime(s));
    if (!t) return vintageChip({ unknownLabel: 'time unknown', unknownTitle: 'This idea carries no time of its own, so none is shown.' });
    // A held row shows TWO real times — when it was released, and when it fired — so the one on
    // the row says which it is. Two unlabelled times beside each other would read as a
    // contradiction rather than a disclosure.
    const rel = heldRelease(s) != null;
    return `<span class="rl-time"${rel ? ' title="When this signal was released to the desk. It fired earlier, outside the regular session; the line below says when."' : ''}>${rel ? 'released ' : ''}${esc(t)}</span>`;
  }
  // R-IV.588 — the high-score badge. `high_score` is the SERVER's flag (R-IV.584(b)): the
  // 85-point threshold that used to divert a signal out of the feed entirely now only marks it,
  // and the row stays. The page never recomputes it — one author for the fact.
  //
  // R-IV.593(b)1 — ONE number. `canonical_score` is what the server ranks by AND what it flags
  // on (`models.signal_score`, R-IV.590(c)), so the badge, the tooltip and the order are all the
  // same figure. The page's own coalesce is gone: three expressions were live at once and none
  // was named, which is how DE read 93 on its badge and 85 in its position. Recomputing it here
  // would be the second author all over again.
  //
  // NULL IS NULL, NOT ZERO (R-IV.593(b)2). The SQL coalesces to 0 so it can sort; the served
  // field does not, because a row nobody scored and a row scoring zero are different claims.
  const canonicalScore = (s) => {
    const v = s && s.canonical_score;
    if (v == null) return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };
  // Quiet: the same neutral chip as the grade, in --text-2. Teal is "attention" in this palette
  // and a badge that shouts is not a quiet badge (R-IV.588(a)).
  //
  // R-IV.588(b): the tooltip is the whole point. A 92 sitting in Watch next to an empty Actionable
  // looks like a bug unless the page says why — the A grade turns on the validated cell, not on
  // the score, and R-IV.588(c) keeps it that way: this touches neither the grade nor the lane.
  function highBadge(s) {
    if (!s || s.high_score !== true) return '';
    const n = canonicalScore(s);
    const tip = n == null
      ? 'Scores high, but not a validated setup. Actionable needs an A.'
      : `Scores ${n}: high, but not a validated setup. Actionable needs an A.`;
    return `<span class="rl-high" title="${esc(tip)}">high score${n == null ? '' : ' ' + n}</span>`;
  }
  function laneGrade(s) {
    if (s._gradePending) return `<span class="rl-grade pending" title="This row's level evidence was not read this cycle (the read is capped at ${LANE_LEVEL_MAX} names), so its grade would be a guess between B and C.">grade pending</span>`;
    return `<span class="rl-grade${s._grade === 'A' ? ' a' : ''}" data-gloss="GRADE">grade ${esc(s._grade)}</span>`;
  }
  // R-IV.579(a)2 — a row the server should have excluded is SHOWN, carrying what is wrong with
  // it. Vermilion, not amber: this is not "we cannot confirm", it is a confirmed regression in a
  // filter that is supposed to hold.
  function rowError(s) {
    if (isCryptoLeak(s)) return 'crypto — the feed should not be serving this (RV4)';
    if (strategyClass(s) === null) return 'no strategy_class — the feed should always state one (R-IV.577(b))';
    return '';
  }
  function laneSigRow(s, opts) {
    const o = opts || {};
    const disp = setupDisplay(s.codename || s.signal_type || s.strategy);
    const side = (s.direction || '').toUpperCase();
    // R-IV.900(b) · the NAME comes from the same author as the card's (`display_label` when it is
    // served), but this row is NOT reformatted: its description already sits after the price, and
    // folding it into the title would reorder a row the ruling did not approve a change to.
    // R-IV.943(a): the codename is capitals HERE TOO, by the same means as the card -- a class
    // the stylesheet acts on, never a transformed string. The principal's naming rule holds on
    // every surface; R-IV.900 protected this row's CONTENT, not its case, and the content is
    // byte-for-byte what it was.
    const name = o.raw ? `<span class="rl-raw">${esc(s.signal_type || s.strategy || 'SETUP')}</span>` : `<b class="figure">${esc(titleParts(s, disp).figure)}</b>`;
    const err = rowError(s);
    return `<div class="rl-row${err ? ' rl-bad' : ''}" data-sid="${esc(s.signal_id || '')}">
        <div class="rl-main">${name} <span class="rl-tkr" data-chart="${esc(String(s.ticker || '').toUpperCase())}" tabindex="0" role="button">${esc(s.ticker || '')}</span> <span class="rl-dir">${esc(side)}</span>${s.entry_price != null ? ' @ ' + Number(s.entry_price).toFixed(2) : ''}${disp.desc && !o.raw ? ` <span class="rl-desc">${esc(disp.desc)}</span>` : ''}</div>
        <div class="rl-sub">${err ? `<span class="rl-err" title="This row is being shown, not hidden, so the regression is visible: the page no longer filters it.">${esc(err)}</span>` : ''}${o.grade ? laneGrade(s) : ''}${highBadge(s)}${o.why ? `<span class="rl-why">${esc(o.why)}</span>` : ''}${laneTime(s)}</div>
        ${heldLabel(s) ? `<div class="rl-held">${esc(heldLabel(s))}</div>` : ''}
        ${disp.banner ? `<div class="rl-banner">${esc(disp.banner)}</div>` : ''}
      </div>`;
  }
  // Why the Actionable lane is empty, computed from the read that produced it — never a stock
  // sentence. The order is the order the constraints actually bind in.
  function actionableReason(d, graded) {
    if (!d.answered) return 'The idea feed did not answer this cycle, so nothing could be graded. This is not a quiet day; it is an unread one.';
    if (!d.read) return 'The idea feed answered with no active ideas at all.';
    if (!regimeKnown()) return 'The regime has not been read this cycle, and the grade turns on it — so no idea can be graded A yet. Nothing here is a judgement about the ideas.';
    const reg = currentRegime();
    const cell = validatedCellText();
    if (!VALIDATED_A_CELLS.some((c) => c.regime === reg)) {
      return `Nothing actionable: no validated setup is possible in a ${reg} regime. The one validated cell is a ${cell}.`;
    }
    const want = VALIDATED_A_CELLS.filter((c) => c.regime === reg);
    const sided = graded.filter((s) => want.some((c) => c.side === (s.direction || '').toUpperCase()));
    if (!sided.length) return `Nothing actionable: the regime is ${reg} and the validated cell is a ${cell}, but no setup on that side fired today.`;
    const liquid = sided.filter((s) => want.some((c) => c.side === (s.direction || '').toUpperCase() && (c.liquid === undefined || c.liquid === !!s.is_liquid)));
    if (!liquid.length) return `Nothing actionable: ${sided.length} setup${sided.length === 1 ? '' : 's'} fired on the validated side, ${sided.length === 1 ? 'and it is' : 'and every one is'} outside the liquid universe. The validated cell is a ${cell}.`;
    return 'Nothing actionable: no idea cleared the A grade this cycle.';
  }
  // ── R-IV.606(b) · Your book ────────────────────────────────────────────────
  // `touches` is a LIST and it is ABSENT, not empty, when the ticker is not in the book. One
  // signal can touch two positions on different structures and one may confirm while the other
  // contradicts, so each TOUCH is its own row — collapsing them to the signal would hide exactly
  // the disagreement this lane exists to show.
  function bookEntries(d) {
    const out = [];
    [...d.roster, ...d.shadow, ...d.nonRoster, ...d.unclassed].forEach((s) => {
      const t = s.touches;
      if (!Array.isArray(t) || !t.length) return;
      // R-IV.650(b)2: the same account filter governs this lane. `touches` carries the account.
      t.forEach((h) => { if (h && h.position_id && inAcct(h.account)) out.push({ s, h }); });
    });
    // CONTRADICTS first — the ruling's order, and the reason the lane is read at all.
    const rank = (r) => (r === 'CONTRADICTS' ? 0 : r === 'CONFIRMS' ? 1 : 2);
    out.sort((a, b) => rank(a.h.relation) - rank(b.h.relation)
      || (_acctSort ? acctRank(a.h.account) - acctRank(b.h.account) : 0)
      || ((rowTime(b.s) || 0) - (rowTime(a.s) || 0)));
    return out;
  }
  // "Your exit: …" from the position's own block. `written` is the ONE field to test, as the
  // relay asks. `stop` and `stop_type` can legitimately disagree — a resting broker order under
  // a plan that calls for none — so both are shown rather than one hidden behind the other.
  function exitLine(positionId) {
    if (_bookExits == null) {
      return `<div class="rl-exit unknown">Your exit: <b>not read</b> — the position list has not answered this cycle, so this is not "no exit written".</div>`;
    }
    const rec = _bookExits[positionId];
    if (!rec) return `<div class="rl-exit unknown">Your exit: <b>not read</b> — this position was not in the last book read.</div>`;
    const x = rec.exit;
    if (!x || x.written !== true) return '<div class="rl-exit none">Your exit: <b>No exit written</b></div>';
    const bits = [];
    if (x.stop != null && Number.isFinite(Number(x.stop))) bits.push('broker stop $' + Number(x.stop).toFixed(2));
    if (x.stop_type) bits.push('stop type ' + String(x.stop_type).replace(/_/g, ' '));
    if (x.invalidation) bits.push('invalidation: ' + x.invalidation);
    if (x.time_stop) bits.push('time stop ' + x.time_stop);
    return `<div class="rl-exit">Your exit: ${esc(bits.join(' · '))}</div>`;
  }
  function bookRow(e) {
    const s = e.s, h = e.h;
    const disp = setupDisplay(s.codename || s.signal_type || s.strategy);
    const side = (s.direction || '').toUpperCase();
    const bad = h.relation === 'CONTRADICTS';
    // A null relation is NOT a third badge (the relay is explicit) — no badge at all. The row
    // still belongs here, because it names an open position and carries that position's exit.
    const badge = h.relation
      ? `<span class="rl-verdict${bad ? ' bad' : ''}">${esc(h.relation)}</span>`
      : `<span class="rl-verdict quiet" title="${esc(h.position_direction ? 'The signal\u2019s own direction could not be read, so no verdict is claimed.' : 'This position\u2019s structure could not be read, so no verdict is claimed.')}">no verdict</span>`;
    return `<div class="rl-row${bad ? ' rl-contra' : ''}" data-sid="${esc(s.signal_id || '')}" data-pos="${esc(h.position_id)}">
        <div class="rl-main">${badge}${acctChip(h.account, h.account_display)} <b>${esc(s.ticker || '')}</b> <span class="rl-dir">${esc(side)}</span> ${esc(disp.name)}
          <span class="rl-pos">your ${esc(String(h.structure || 'position').replace(/_/g, ' '))}${h.position_direction ? ' (' + esc(h.position_direction) + ')' : ''}</span></div>
        ${exitLine(h.position_id)}
        <div class="rl-sub">${laneTime(s)}</div>
      </div>`;
  }

  // ── NOTABLES v2 · the MOCK step ─────────────────────────────────────────────
  //
  // R-IV.1259(i): behind `?notables=1`, MOCK-labelled cards, for Nick to see IN PLACE. The
  // approved mocks (Main 3bfb1943…, States d78757ee…, both verified by hash) are standalone
  // pages; this renders their card set inside River's own lanes, which is the only way to
  // judge whether a card belongs where (d) puts it.
  //
  // PLACEMENT IS THE RULING'S, NOT THE MOCK'S (d): ticker cards go in WATCH under "NOTABLE",
  // market-wide cards go in CONTEXT, and NOTHING goes in Actionable. A held position stays in
  // Your book, which is why the footer says so on the face of the block rather than in a note.
  //
  // EVERY STRING COMES FROM `frontend/assets/notables/notables_mock.v1.json`, which the Python
  // lint reads too (`services/notables.py`). One author for the text: a card worded here and
  // checked there would be two texts wearing one name, and the unchecked one is the one that
  // ships an instruction.
  //
  // EVERY FIGURE IS BRACKETED `[MOCK …]`. The approved Main mock printed plain numbers on its
  // VALUE MOVED card; plain numbers on a page served from the live hub are the one thing a
  // reader could take for a live read, and (i) asks for MOCK-labelled cards. Fidelity to the
  // mock's typography, not to its unlabelled figures.
  //
  // NOTHING IS WRITTEN AND NOTHING IS SENT. (h) puts the two logs in the deploy that first
  // writes to them, so neither table exists yet; the three buttons are inert and say so on
  // hover.
  // R-IV.1259(i) step 2: `?notables=1` is LIVE and `?notables=mock` renders the approved card
  // set. `NOTABLES_MOCK` therefore means "render the fixture", which is now the mock value
  // only -- the name is kept because the fixture renderers below are all named for it, and a
  // rename across twelve functions buys nothing a comment does not.
  const NOTABLES_MOCK = (() => {
    try { return new URLSearchParams(location.search).get('notables') === 'mock'; }
    catch (_) { return false; }
  })();

  // INJECTED, not added to v2.css. That stylesheet is pinned INDEPENDENTLY by v2.html,
  // stater.html and abacus.html and the three values have already diverged, so a rule added
  // there has to be shipped three times or it reaches a stale cache on the pages that were
  // missed. A rule the renderer carries ships with the renderer's own pin.
  const NB_CSS = `
.nb-wrap{display:flex;flex-direction:column;gap:14px;padding:12px 0 4px}
.nb-badge{font-size:10px;letter-spacing:1.4px;color:#f5a524;border:1px solid #f5a524;border-radius:999px;padding:3px 8px;white-space:nowrap}
.nb-card{background:#0b1122;border:1px solid #1b2745;border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:10px}
.nb-card.nb-loud{border-color:#14b8a6;box-shadow:0 0 0 3px rgba(20,184,166,.12)}
.nb-card.nb-aged{opacity:.5}
.nb-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.nb-sym{font-size:26px;font-weight:700;letter-spacing:.5px}
.nb-move{font-size:13px;font-weight:700;border-radius:6px;padding:2px 7px;background:#1b2745;color:#e2e8f0}
.nb-move.up{background:#7CFF6B;color:#050810}
.nb-move.down{background:#ff5c33;color:#050810}
.nb-big{font-size:26px;font-weight:700}
.nb-big.up{color:#7CFF6B}
.nb-big.down{color:#ff5c33}
.nb-kind{font-size:11px;letter-spacing:1.5px}
.nb-kind.up{color:#7CFF6B}
.nb-kind.down{color:#ff5c33}
.nb-kind.muted{color:#70829d}
.nb-when{font-size:11px;color:#8b98ad;margin-left:auto}
.nb-sub{font-size:12px;color:#8b98ad}
.nb-chips{display:flex;gap:6px;flex-wrap:wrap}
.nb-chip{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:10px;letter-spacing:1.2px;padding:3px 7px;border-radius:999px;border:1px solid #223258;color:#70829d}
.nb-chip.on{border-color:#14b8a6;color:#5eead4;background:rgba(20,184,166,.12)}
.nb-note{display:flex;align-items:center;gap:10px;border-radius:8px;padding:8px 10px;font-size:13px}
.nb-note .dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.nb-note.amber{background:rgba(245,165,36,.08);border:1px solid rgba(245,165,36,.45);color:#f5c46a}
.nb-note.amber .dot{background:#f5a524}
.nb-note.red{background:rgba(255,92,51,.08);border:1px solid rgba(255,92,51,.45)}
.nb-note.red .dot{background:#ff5c33}
.nb-note.teal{background:#0d152b}
.nb-note.teal .dot{background:#14b8a6}
.nb-note .why{font-size:11px;color:#8b98ad}
.nb-cols{display:flex;gap:6px}
.nb-col{flex:1 1 0;display:flex;flex-direction:column;gap:4px}
.nb-col h4{margin:0;font-size:10px;letter-spacing:1px;color:#70829d;font-weight:400}
.nb-bar{display:flex;gap:4px;align-items:center;font-size:11px}
.nb-bar i{height:8px;border-radius:2px;display:block}
.nb-bar i.up{background:#7CFF6B}
.nb-bar i.down{background:#ff5c33}
.nb-vp{position:relative;height:92px;background:#0d152b;border-radius:8px;overflow:hidden}
.nb-vp .lab{position:absolute;font-size:10px}
.nb-against{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
.nb-against b{font-size:10px;letter-spacing:1px;color:#70829d;font-weight:400}
.nb-against span{font-size:12px;color:#c8d3e3;border:1px dashed #223258;border-radius:6px;padding:3px 7px}
.nb-stale{font-size:12px;color:#8b98ad}
.nb-strip{border-top:1px solid #1b2745;padding-top:12px;display:flex;flex-direction:column;gap:10px}
.nb-strip-head{display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:12px}
.nb-ivr{font-size:10px;letter-spacing:1px;border-radius:999px;padding:2px 8px;margin-left:auto;white-space:nowrap}
/* R-IV.1265(c): the bands are IV LOW / IV MID / IV HIGH. rich and neutral were
   (f)'s words and are gone with it; models/notables_strip.py owns the edges.
   And no backtick may appear in here: this block is a TEMPLATE LITERAL, so one ends it. */
.nb-ivr.low{color:#7CFF6B;border:1px solid rgba(124,255,107,.5)}
.nb-ivr.mid{color:#8b98ad;border:1px solid #223258}
.nb-ivr.high{color:#ff5c33;border:1px solid rgba(255,92,51,.55)}
.nb-rungs{position:relative;height:118px}
.nb-rungs .axis{position:absolute;left:4%;right:4%;top:15px;height:2px;background:#223258}
.nb-rungs .em{position:absolute;left:4%;width:46%;top:9px;height:14px;background:rgba(20,184,166,.18);border-radius:3px}
.nb-rungs .tail{position:absolute;right:4%;top:15px;height:2px;background:repeating-linear-gradient(90deg,#70829d 0 3px,transparent 3px 7px)}
.nb-rungs .now{position:absolute;left:4%;top:4px;width:2px;height:24px;background:#e2e8f0}
.nb-rungs .nowlab{position:absolute;left:4%;top:32px;font-size:10px;color:#8b98ad}
.nb-rungs .taillab{position:absolute;left:87%;top:0;font-size:9px;letter-spacing:1px;color:#70829d}
.nb-rungs .tick{position:absolute;top:8px;width:2px;height:16px;background:#5eead4}
.nb-rungs .tick.far{background:#8b98ad}
.nb-rung{position:absolute;top:30px;transform:translateX(-50%);text-align:center;display:flex;flex-direction:column;gap:2px;white-space:nowrap}
.nb-rung .m{font-size:10px;color:#70829d}
.nb-rung .q{font-size:12px}
.nb-rung .o{font-size:11px;color:#c8d3e3}
.nb-rung .b{font-size:10px;color:#8b98ad}
.nb-rung.far .q,.nb-rung.far .o{color:#8b98ad}
.nb-rung.far .b{color:#70829d}
.nb-foot{display:flex;gap:14px;flex-wrap:wrap;align-items:center;font-size:12px}
.nb-foot .lite{display:flex;gap:6px;align-items:center}
.nb-foot .lite i{width:8px;height:8px;border-radius:50%;display:block}
.nb-foot .lite i.green{background:#7CFF6B}
.nb-foot .lite i.amber{background:#f5a524}
.nb-foot .lite i.red{background:#ff5c33}
.nb-foot .unknown{color:#f5c46a}
.nb-compact{display:flex;align-items:center;gap:10px;background:#0d152b;border-radius:8px;padding:8px 10px;flex-wrap:wrap;font-size:12px}
.nb-btns{display:flex;gap:8px}
.nb-btn{font:inherit;font-size:12px;color:#8b98ad;background:transparent;border:1px solid #223258;border-radius:6px;padding:0 12px;height:32px;cursor:not-allowed}
.nb-tally{display:flex;align-items:center;gap:10px;font-size:11px}
.nb-tally .up{color:#7CFF6B}
.nb-tally .down{color:#ff5c33}
.nb-tally .meter{flex-grow:1;height:6px;border-radius:3px;display:flex;overflow:hidden;background:#1b2745}
.nb-tally .meter i{display:block}
.nb-tally .meter i.up{background:#7CFF6B}
.nb-tally .meter i.down{background:#ff5c33}
.nb-tally .cap{font-size:10px;color:#70829d}
.nb-quiet{background:#0b1122;border:1px dashed #223258;border-radius:10px;padding:22px 14px;display:flex;flex-direction:column;gap:6px;align-items:center;text-align:center}
.nb-quiet b{letter-spacing:2px;color:#70829d;font-size:13px;font-weight:400}
.nb-capline{background:#0b1122;border:1px solid #1b2745;border-radius:10px;padding:12px 14px;display:flex;align-items:center;gap:10px;font-size:12px}
.nb-caption{font-size:10px;letter-spacing:2px;color:#70829d;padding-top:6px}
.nb-tilefoot{font-size:10px;letter-spacing:1px;color:#70829d;text-align:center;padding-top:4px}
.nb-strips{display:flex;flex-wrap:wrap;gap:8px}
.nb-ctxstrip{background:#0b1122;border:1px solid #1b2745;border-radius:8px;padding:8px 10px;display:flex;gap:8px;align-items:center;font-size:12px}
.nb-ctxstrip b{font-size:10px;letter-spacing:1px;color:#70829d;font-weight:400}
.nb-ctxstrip .up{color:#7CFF6B}
.nb-ctxstrip .down{color:#ff5c33}
`;

  function nbStyle() {
    if (document.getElementById('nb-css')) return;
    const st = document.createElement('style');
    st.id = 'nb-css';
    st.textContent = NB_CSS;
    document.head.appendChild(st);
  }

  // THE ONE HELPER THAT EMITS A TICKER. (b) requires 26px mono bold on every card type and
  // every state; six separate strings would have to agree, and one of them eventually would
  // not. One helper makes the requirement structural.
  function nbSym(t) { return '<span class="mono nb-sym">' + esc(t || '') + '</span>'; }

  let _nbMock = null;
  function nbLoad() {
    if (_nbMock) return Promise.resolve(_nbMock);
    return fetch('/assets/notables/notables_mock.v1.json', { cache: 'no-store' })
      .then((r) => r.json()).then((j) => { _nbMock = j; return j; })
      .catch(() => null);
  }

  const nbDirClass = (d) => (d === 'up' ? 'up' : d === 'down' ? 'down' : d === 'muted' ? 'muted' : '');

  function nbChips(chips) {
    if (!chips || !chips.length) return '';
    return '<div class="nb-chips">'
      + chips.map((c) => '<span class="nb-chip' + (c.on ? ' on' : '') + '">' + esc(c.label) + '</span>').join('')
      + '</div>';
  }

  function nbAgainst(list) {
    if (!list || !list.length) return '';
    return '<div class="nb-against"><b>AGAINST</b>'
      + list.map((a) => '<span>' + esc(a) + '</span>').join('') + '</div>';
  }

  function nbStale(text) {
    if (!text) return '';
    return '<div class="nb-stale">' + esc(text)
      + ' · <i>a fact about this card, not a stop</i></div>';
  }

  function nbButtons(labels) {
    if (!labels || !labels.length) return '';
    return '<div class="nb-btns">' + labels.map((l) =>
      '<button class="nb-btn" type="button" disabled title="MOCK — this button does nothing yet'
      + '; the log it would write does not exist until the deploy that writes to it">'
      + esc(l) + '</button>').join('') + '</div>';
  }

  function nbNote(n) {
    if (!n) return '';
    return '<div class="nb-note ' + esc(n.tone || 'teal') + '"><span class="dot"></span>'
      + '<span>' + esc(n.text || '') + '</span>'
      + (n.detail ? '<span class="why">' + esc(n.detail) + '</span>' : '') + '</div>';
  }

  function nbLoudCard(c, badge) {
    const d = nbDirClass(c.dir);
    const col = (title, rows, dir) => '<div class="nb-col"><h4>' + esc(title) + '</h4>'
      + (rows || []).map((r) => '<div class="nb-bar"><i class="' + dir + '" style="width:'
        + Math.max(3, Math.min(100, Number(r.w) || 3)) + 'px"></i><span class="mono">'
        + esc(r.label) + '</span></div>').join('') + '</div>';
    const why = c.why && c.why.state === 'known'
      ? nbNote({ tone: 'teal', text: c.why.text })
      : nbNote({ tone: 'amber', text: c.why ? c.why.text : '' });
    return '<div class="nb-card nb-loud">'
      + '<div class="nb-head"><span class="mono nb-kind" style="color:#5eead4">LOUD MOVE</span>'
      + (c.pinned ? '<span class="mono nb-sub">' + esc(c.pinned) + '</span>' : '')
      + (badge ? '<span class="mono nb-badge">' + esc(badge) + '</span>' : '')
      + '<span class="mono nb-when">' + esc(c.time || '') + '</span></div>'
      + '<div class="nb-head">' + nbSym(c.ticker)
      + '<span class="mono nb-big ' + d + '">' + esc(c.move || '') + '</span>'
      + '<span class="mono nb-sub">' + esc(c.scale || '') + '</span></div>'
      + (c.leading || c.lagging ? '<div class="nb-cols">'
          + col('LEADING', c.leading, 'up') + col('LAGGING', c.lagging, 'down') + '</div>' : '')
      + why + '</div>';
  }

  function nbRungs(strip) {
    const rungs = strip.rungs || [];
    return '<div class="nb-rungs">'
      + '<div class="axis"></div><div class="em"></div><div class="tail"></div>'
      + '<div class="now"></div><div class="mono nowlab">now</div>'
      + '<div class="mono taillab">' + esc(strip.tail_label || 'TAIL ONLY') + '</div>'
      + rungs.map((r) => '<div class="tick' + (r.tone === 'far' ? ' far' : '')
          + '" style="left:' + Number(r.at) + '%"></div>').join('')
      + rungs.map((r) => '<div class="nb-rung mono' + (r.tone === 'far' ? ' far' : '')
          + '" style="left:' + Number(r.at) + '%">'
          + '<span class="m">' + esc(r.mult) + '</span>'
          + '<span class="q">' + esc(r.quote) + '</span>'
          + '<span class="o">' + esc(r.odds) + '</span>'
          + '<span class="b">' + esc(r.be) + '</span></div>').join('')
      + '</div>';
  }

  function nbStrip(strip) {
    if (!strip) return '';
    const ivr = strip.iv_rank || {};
    const liq = strip.liquidity || {};
    const earn = strip.earnings || {};
    return '<div class="nb-strip">'
      + '<div class="nb-strip-head mono"><span>' + esc(strip.expiry || '') + '</span>'
      + '<span style="color:#8b98ad">·</span><span>' + esc(strip.em || '') + '</span>'
      + (ivr.label ? '<span class="nb-ivr ' + esc(ivr.tone || '') + '">'
          + esc(ivr.label) + '</span>' : '') + '</div>'
      + nbRungs(strip)
      + '<div class="nb-foot">'
      + (liq.text ? '<span class="lite"><i class="' + esc(liq.light || 'green') + '"></i>'
          + esc(liq.text) + '</span>' : '')
      + (strip.wait ? '<span>' + esc(strip.wait) + '</span>' : '')
      + (earn.text ? '<span class="lite' + (earn.tone === 'unknown' ? ' unknown' : '') + '">'
          + (earn.tone === 'unknown' ? '<i class="amber"></i>' : '') + esc(earn.text) + '</span>' : '')
      + '</div>'
      + (strip.structure ? '<div class="nb-stale">' + esc(strip.structure) + '</div>' : '')
      + '</div>';
  }

  function nbCompact(cs) {
    if (!cs) return '';
    const liq = cs.liquidity || {};
    const ivr = cs.iv_rank || {};
    const earn = cs.earnings || {};
    return '<div class="nb-compact">'
      + '<span class="mono">' + esc(cs.expiry || '') + '</span>'
      + (liq.text ? '<span class="lite" style="display:flex;gap:5px;align-items:center">'
          + '<i class="' + esc(liq.light || 'green') + '" style="width:8px;height:8px;border-radius:50%;display:block"></i>'
          + esc(liq.text) + '</span>' : '')
      + (ivr.label ? '<span class="mono nb-ivr ' + esc(ivr.tone || '')
          + '" style="margin-left:0">' + esc(ivr.label) + '</span>' : '')
      + (earn.text ? '<span style="color:#8b98ad">' + esc(earn.text) + '</span>' : '')
      + (cs.macro ? '<span style="color:#f5c46a">' + esc(cs.macro) + '</span>' : '')
      + (cs.more ? '<button class="nb-btn" type="button" disabled style="height:28px;margin-left:auto"'
          + ' title="MOCK — the strike table is not wired yet">' + esc(cs.more) + '</button>' : '')
      + '</div>';
  }

  function nbValueCard(c, badge) {
    const L = c.levels || {};
    return '<div class="nb-card">'
      + '<div class="nb-head">' + nbSym(c.ticker)
      + '<span class="mono nb-move ' + nbDirClass(c.dir) + '">' + esc(c.move || '') + '</span>'
      + '<span class="mono nb-kind ' + nbDirClass(c.dir) + '">' + esc(c.headline || '') + '</span>'
      + (badge ? '<span class="mono nb-badge">' + esc(badge) + '</span>' : '')
      + '<span class="mono nb-when">' + esc(c.time || '') + '</span></div>'
      + nbChips((c.chips || []).concat(c.pythia ? [{ label: c.pythia, on: false }] : []))
      + '<div class="nb-vp">'
      + '<svg width="100%" height="92" viewBox="0 0 528 92" preserveAspectRatio="none" aria-hidden="true">'
      + '<line x1="0" y1="72" x2="528" y2="72" stroke="#70829d" stroke-dasharray="3 4" stroke-width="1"></line>'
      + '<rect x="0" y="34" width="528" height="16" fill="rgba(20,184,166,.10)"></rect>'
      + '<line x1="0" y1="42" x2="528" y2="42" stroke="#14b8a6" stroke-width="1"></line>'
      + '<polyline points="' + esc(c.spark || '') + '" fill="none" stroke="#7CFF6B" stroke-width="2"></polyline>'
      + '</svg>'
      + '<span class="mono lab" style="left:8px;top:74px;color:#8b98ad">' + esc(L.prior_edge || '') + '</span>'
      + '<span class="mono lab" style="left:8px;top:30px;color:#5eead4">' + esc(L.value || '') + '</span>'
      + '<span class="mono lab" style="right:8px;top:4px;font-size:11px;color:#e2e8f0">' + esc(L.last || '') + '</span>'
      + '</div>'
      + nbAgainst(c.against) + nbStale(c.stale) + nbStrip(c.strip) + nbButtons(c.buttons)
      + '</div>';
  }

  function nbFailedCard(c, badge) {
    return '<div class="nb-card">'
      + '<div class="nb-head">' + nbSym(c.ticker)
      + '<span class="mono nb-move ' + nbDirClass(c.dir) + '">' + esc(c.move || '') + '</span>'
      + '<span class="mono nb-kind down">' + esc(c.headline || '') + '</span>'
      + (badge ? '<span class="mono nb-badge">' + esc(badge) + '</span>' : '')
      + '<span class="mono nb-when">' + esc(c.time || '') + '</span></div>'
      + nbChips(c.chips)
      + '<div style="display:flex;align-items:center;gap:12px">'
      + '<svg width="140" height="44" viewBox="0 0 140 44" aria-hidden="true">'
      + '<line x1="0" y1="14" x2="140" y2="14" stroke="#14b8a6" stroke-dasharray="3 3"></line>'
      + '<polyline points="' + esc(c.spark || '') + '" fill="none" stroke="#ff5c33" stroke-width="2"></polyline>'
      + '</svg><div style="font-size:13px;line-height:1.45">' + esc(c.body || '') + '</div></div>'
      + nbAgainst(c.against) + nbStale(c.stale) + nbCompact(c.compact_strip)
      + '</div>';
  }

  function nbTrendCard(c, badge) {
    const t = c.transition || {};
    return '<div class="nb-card">'
      + '<div class="nb-head">' + nbSym(c.ticker)
      + '<span class="mono nb-move">' + esc(c.move || '') + '</span>'
      + '<span class="mono nb-kind down">' + esc(c.headline || '') + '</span>'
      + (badge ? '<span class="mono nb-badge">' + esc(badge) + '</span>' : '')
      + '<span class="mono nb-when">' + esc(c.time || '') + '</span></div>'
      + nbChips(c.chips)
      + '<div class="nb-head mono" style="font-size:12px">'
      + '<span style="border:1px solid #223258;border-radius:6px;padding:4px 8px">' + esc(t.from || '') + '</span>'
      + '<span style="color:#8b98ad">→</span>'
      + '<span style="color:#ff5c33;border:1px solid rgba(255,92,51,.6);border-radius:6px;padding:4px 8px">'
      + esc(t.to || '') + '</span>'
      + (t.detail || []).map((d) => '<span style="color:#8b98ad">' + esc(d) + '</span>').join('')
      + '</div>'
      + nbAgainst(c.against) + nbStale(c.stale) + nbCompact(c.compact_strip)
      + '</div>';
  }

  function nbStateCard(s, badge) {
    const head = '<div class="nb-head">'
      + (s.ticker ? nbSym(s.ticker) : '')
      + (s.move ? '<span class="mono nb-big ' + nbDirClass(s.dir) + '">' + esc(s.move) + '</span>' : '')
      + (s.headline ? '<span class="mono nb-kind ' + nbDirClass(s.dir) + '">' + esc(s.headline) + '</span>' : '')
      + (badge ? '<span class="mono nb-badge">' + esc(badge) + '</span>' : '')
      + (s.time ? '<span class="mono nb-when">' + esc(s.time) + '</span>' : '')
      + '</div>';
    if (s.kind === 'state_quiet') {
      return '<div class="nb-quiet"><b class="mono">' + esc(s.headline || '') + '</b>'
        + '<div class="nb-sub">' + esc(s.body || '') + '</div></div>';
    }
    if (s.kind === 'state_cap') {
      return '<div class="nb-capline"><span class="mono">' + esc(s.headline || '') + '</span>'
        + '<span class="nb-sub">' + esc(s.body || '') + '</span></div>';
    }
    if (s.kind === 'state_loud_known') {
      return nbLoudCard(s, badge);
    }
    return '<div class="nb-card' + (s.kind === 'state_aging' ? ' nb-aged' : '') + '">'
      + head + nbChips(s.chips) + nbNote(s.notice)
      + (s.body ? '<div class="nb-sub">' + esc(s.body) + '</div>' : '')
      + '</div>';
  }

  function nbTickerCard(c, badge) {
    if (c.kind === 'value_moved') return nbValueCard(c, badge);
    if (c.kind === 'failed_break') return nbFailedCard(c, badge);
    if (c.kind === 'trend_change') return nbTrendCard(c, badge);
    return '';
  }

  function nbTally(m) {
    const t = m.tally || {}, cap = m.cap || {};
    const up = Number(t.up) || 0, down = Number(t.down) || 0, tot = up + down || 1;
    return '<div class="nb-tally mono"><span class="up">Up ' + up + '</span>'
      + '<span class="meter"><i class="up" style="width:' + ((up / tot) * 100).toFixed(0) + '%"></i>'
      + '<i class="down" style="width:' + ((down / tot) * 100).toFixed(0) + '%"></i></span>'
      + '<span class="down">Down ' + down + '</span>'
      + '<span class="cap">' + esc((cap.shown != null ? cap.shown : '?') + ' of '
          + (cap.max != null ? cap.max : '?') + ' today · time order only, never ranked') + '</span>'
      + '</div>';
  }

  // The WATCH half: ticker cards under "NOTABLE", plus the states as a collapsed reference
  // sheet. The states are a DESIGN reference, not today's cards, so they sit behind a summary
  // rather than in the stream where they would read as six more notables.
  function nbWatchBlock(m) {
    if (!m) return '';
    const badge = m.badge || '';
    const cards = (m.watch || []).map((c) => nbTickerCard(c, badge)).filter(Boolean).join('');
    const states = (m.states || []).map((s) =>
      '<div class="mono nb-caption">' + esc(s.caption || '') + '</div>' + nbStateCard(s, badge)
    ).join('');
    return '<div class="nb-wrap">'
      + '<div class="nb-head"><span class="mono nb-kind" style="color:#14b8a6;letter-spacing:2px">NOTABLE</span>'
      + '<span class="mono nb-badge">' + esc(badge) + '</span>'
      + '<span class="mono nb-when">' + esc(m.stamp || '') + '</span></div>'
      + nbTally(m)
      + (cards || '<div class="nb-sub">no mock ticker card in the fixture</div>')
      + '<details class="nb-card" style="gap:6px"><summary class="mono nb-sub" style="cursor:pointer">'
      + 'CARD STATES · design reference, not today’s cards</summary>' + states + '</details>'
      + '<div class="mono nb-tilefoot">' + esc(m.footer || '') + '</div>'
      + '</div>';
  }

  // The CONTEXT half: the pinned LOUD MOVE and the market-wide strips. (c)1 pins it at the top
  // of Context and keeps it out of the cap; (c)5 makes rotation a Context LINE, not a card.
  function nbContextBlock(m) {
    if (!m) return '';
    const ctx = m.context || {};
    const strips = (ctx.strips || []).map((s) => '<div class="nb-ctxstrip mono"><b>'
      + esc(s.label) + '</b>'
      + (s.items || []).map((it, i) => '<span class="'
          + esc(((s.dirs || [])[i]) || '') + '">' + esc(it) + '</span>').join('')
      + '</div>').join('');
    return '<div class="nb-wrap">'
      + (ctx.loud_move ? nbLoudCard(ctx.loud_move, m.badge) : '')
      + (strips ? '<div class="nb-strips">' + strips + '</div>' : '')
      + '</div>';
  }
  // ── end notables ────────────────────────────────────────────────────────────
  // ── NOTABLES: the LIVE read ─────────────────────────────────────────────────
  //
  // R-IV.1259(i): "Then wire it live behind the same flag." So `?notables=1` is now LIVE and
  // `?notables=mock` still renders the approved card set — the mock stays reachable because it
  // is what Nick approved and what the layout is judged against, and deleting it would leave
  // nothing to compare a live card to.
  //
  // ONE RENDERER, TWO SOURCES. The live payload's cards are mapped into the SAME shapes the
  // fixture uses, rather than given renderers of their own: two renderers for one card would
  // drift, and the one that drifted would be the live one — the only one anybody acts on.
  // R-IV.1354(a): SHIPPED AS THE DEFAULT. This returned null -- the cards OFF -- unless
  // `?notables=1` was given. It now defaults to 'live', with the cards hidden at
  // `?notables=off` for ONE WEEK -- REMOVE THE ROLLBACK ON OR AFTER 2026-10-30.
  //
  // THREE STATES, NOT TWO, AND 'mock' SURVIVES THE CHANGE. `?notables=mock` renders the
  // approved fixture in place and is how the card was signed off; it is also the only way to
  // see the layout when the live read is empty. Folding it into the default would have removed
  // the one view that can be compared against the approval.
  const NOTABLES_SOURCE = (() => {
    try {
      const v = new URLSearchParams(location.search).get('notables');
      if (v === 'mock') return 'mock';
      if (v === 'off') return null;
      return 'live';
    } catch (_) { return 'live'; }
  })();

  let _nbLiveData = null;
  function nbLoadLive() {
    if (_nbLiveData) return Promise.resolve(_nbLiveData);
    return fetch('/api/stable/notables', { cache: 'no-store' })
      .then((r) => r.json()).then((j) => { _nbLiveData = j; return j; })
      .catch(() => null);
  }

  const nbPct = (v) => (v == null ? '' : (v > 0 ? '+' : '') + Number(v).toFixed(1) + '%');
  const nbArrow = (d) => (d === 'up' ? ' ▲' : d === 'down' ? ' ▼' : '');

  // The chips a live card lights. The fixture spells all four and marks which are on; a live
  // card carries only the ones that fired, so the full set is reconstructed here and the rest
  // are shown OFF rather than omitted — a missing chip and an unlit chip say different things.
  const NB_CHIP_SET = ['STRUCTURE', 'FLOW', 'TREND', 'SECTOR'];
  function nbLiveChips(card) {
    const on = new Set((card.reasons || []).map((r) => String(r).toUpperCase()));
    return NB_CHIP_SET.map((label) => ({ label, on: on.has(label) }));
  }

  // EVERY LIVE FIGURE IS REAL, so none of them is bracketed. The MOCK badge is replaced by a
  // LIVE chip carrying the read's as-of, because a card with no provenance at all is the thing
  // the mock badge existed to prevent.
  function nbLiveStripNote(payload) {
    const s = (payload && payload.strip) || {};
    if (s.available) return null;
    return { tone: 'amber', text: s.reason || 'Options data unavailable — chart only' };
  }

  function nbFromLive(card, payload) {
    const kind = card.card_kind;
    const common = {
      ticker: card.ticker,
      dir: card.direction || 'flat',
      time: '',
      chips: nbLiveChips(card),
      against: card.counter_evidence || [],
      stale: card.stale_if || '',
    };
    if (kind === 'LOUD_MOVE') {
      return Object.assign({}, common, {
        kind: 'loud_move',
        move: nbPct(card.move_pct),
        pinned: 'PINNED · NOT COUNTED IN CAP',
        scale: (card.reasons || []).join(' · '),
        why: card.why,
      });
    }
    if (kind === 'VALUE_MOVED') {
      return Object.assign({}, common, {
        kind: 'value_moved',
        move: nbPct(card.move_pct),
        headline: 'VALUE MOVED' + nbArrow(card.direction),
        levels: {
          prior_edge: card.level == null ? '' : 'prior value edge ' + Number(card.level).toFixed(2),
          value: card.basis || '',
          last: card.close == null ? '' : Number(card.close).toFixed(2),
        },
        spark: '',
        strip: null,
        notice: nbLiveStripNote(payload),
        buttons: ['Dismiss', 'Pin', 'Send to journal'],
      });
    }
    if (kind === 'FAILED_BREAK') {
      return Object.assign({}, common, {
        kind: 'failed_break',
        move: '',
        headline: (card.event === 'GAP_FADED' ? 'GAP FADED' : 'FAILED BREAK') + nbArrow(card.direction),
        spark: '',
        body: card.basis || '',
        notice: nbLiveStripNote(payload),
      });
    }
    if (kind === 'TREND_CHANGE') {
      return Object.assign({}, common, {
        kind: 'trend_change',
        move: 'last close',
        headline: 'TREND CHANGE' + nbArrow(card.direction),
        transition: {
          from: card.stack_prior || '—',
          to: card.stack_class || '—',
          detail: (card.basis || '').split(' · '),
        },
        notice: nbLiveStripNote(payload),
      });
    }
    return null;
  }

  // The live WATCH block. The states gallery is MOCK-ONLY: it is a design reference, and
  // showing it beside live cards would put six invented cards in a lane of real ones.
  function nbLiveWatchBlock(payload) {
    if (!payload) return '';
    const cards = (((payload.cards || {}).watch) || [])
      .map((c) => nbFromLive(c, payload)).filter(Boolean)
      .map((c) => nbTickerCard(c, '')).join('');
    const counts = payload.counts || {};
    const shown = counts.shown != null ? counts.shown : '?';
    const cap = counts.cap != null ? counts.cap : '?';
    const cand = counts.candidates != null ? counts.candidates : null;
    const up = (((payload.cards || {}).watch) || [])
      .filter((c) => c.direction === 'up').length;
    const down = (((payload.cards || {}).watch) || [])
      .filter((c) => c.direction === 'down').length;
    const tot = (up + down) || 1;
    const head = '<div class="nb-head">'
      + '<span class="mono nb-kind" style="color:#14b8a6;letter-spacing:2px">NOTABLE</span>'
      + '<span class="mono nb-badge" style="color:#5eead4;border-color:#14b8a6">LIVE</span>'
      + '<span class="mono nb-when">' + esc(payload.as_of || '') + '</span></div>';
    const tally = '<div class="nb-tally mono"><span class="up">Up ' + up + '</span>'
      + '<span class="meter"><i class="up" style="width:' + ((up / tot) * 100).toFixed(0) + '%"></i>'
      + '<i class="down" style="width:' + ((down / tot) * 100).toFixed(0) + '%"></i></span>'
      + '<span class="down">Down ' + down + '</span>'
      + '<span class="cap">' + esc(shown + ' of ' + cap + ' today'
          + (cand == null ? '' : ' · ' + cand + ' candidate(s) considered')
          + ' · time order only, never ranked') + '</span></div>';
    // THE QUIET STATE AND THE CANNOT-LOOK STATE ARE DIFFERENT, and the payload tells them
    // apart: `hours_ok` false is outside the window, `inputs_missing` is a read that failed,
    // and neither is "nothing notable happened".
    let body = cards;
    if (!cards) {
      if (payload.hours_ok === false) {
        body = '<div class="nb-capline"><span class="mono">OUTSIDE HOURS</span>'
          + '<span class="nb-sub">' + esc(payload.reason || '09:45–15:30 ET') + '</span></div>';
      } else if (Object.keys(payload.inputs_missing || {}).length) {
        body = '<div class="nb-note amber"><span class="dot"></span><span>'
          + 'Could not look — not the same as a quiet day</span></div>';
      } else {
        body = '<div class="nb-quiet"><b class="mono">NOTHING NOTABLE YET</b>'
          + '<div class="nb-sub">' + esc(shown + ' of ' + cap
              + ' today · quiet is information too') + '</div></div>';
      }
    }
    const missing = Object.entries(payload.inputs_missing || {});
    const missingBlock = !missing.length ? '' :
      '<details class="nb-card" style="gap:6px"><summary class="mono nb-sub" style="cursor:pointer">'
      + esc(missing.length + ' input(s) not evaluated') + '</summary>'
      + missing.map(([k, v]) => '<div class="nb-sub"><b class="mono">' + esc(k) + '</b> — '
          + esc(v) + '</div>').join('') + '</details>';
    return '<div class="nb-wrap">' + head + tally + body + missingBlock
      + '<div class="mono nb-tilefoot">'
      + esc(payload.display_only || 'display only') + '</div></div>';
  }

  function nbLiveContextBlock(payload) {
    if (!payload) return '';
    const ctx = ((payload.cards || {}).context) || [];
    const loud = ctx.filter((c) => c.card_kind === 'LOUD_MOVE')
      .map((c) => nbLoudCard(nbFromLive(c, payload), '')).join('');
    const lines = ctx.filter((c) => c.card_kind === 'ROTATION_SHIFT').map((c) =>
      '<div class="nb-ctxstrip mono"><b>ROTATION SHIFT</b>'
      + (c.items || []).map((i) => '<span>' + esc(i) + '</span>').join('')
      + (c.suppressed_themes && c.suppressed_themes.length
          ? '<span style="color:#f5c46a">' + esc(c.suppressed_themes.length
              + ' held back for a data-quality warning') + '</span>' : '')
      + '</div>').join('');
    if (!loud && !lines) return '';
    return '<div class="nb-wrap">' + loud
      + (lines ? '<div class="nb-strips">' + lines + '</div>' : '') + '</div>';
  }
  // ── end notables live ───────────────────────────────────────────────────────


  function renderLanes() {
    const el = $('riverLanes'); if (!el) return;
    const now = Date.now();
    // R-IV.1259(i): the mock cards, in place, behind `?notables=1`. The fixture is fetched
    // ONCE and the lanes are repainted when it lands, so the first paint is never blocked on
    // it -- and a fetch that fails leaves the lanes exactly as they are today rather than
    // replacing them with an error. `nbLoad` resolves null on failure for that reason.
    if (NOTABLES_SOURCE) {
      nbStyle();
      if (NOTABLES_SOURCE === 'mock' && !_nbMock) {
        nbLoad().then((m) => { if (m) renderLanes(); });
      }
      if (NOTABLES_SOURCE === 'live' && !_nbLiveData) {
        nbLoadLive().then((d) => { if (d) renderLanes(); });
      }
    }
    const nbWatch = NOTABLES_SOURCE === 'live' ? nbLiveWatchBlock(_nbLiveData)
      : (NOTABLES_MOCK && _nbMock ? nbWatchBlock(_nbMock) : '');
    const nbCtx = NOTABLES_SOURCE === 'live' ? nbLiveContextBlock(_nbLiveData)
      : (NOTABLES_MOCK && _nbMock ? nbContextBlock(_nbMock) : '');
    const notices = noticeRowsHtml(now);
    const d = _laneData;
    if (!d) { el.innerHTML = notices + '<div class="rl-seam">The idea feed has not been read yet this session.</div>'; return; }

    const graded = d.roster;                       // only `roster` rows grade (R-IV.577(b))
    const actionable = graded.filter((s) => s._grade === 'A');
    const watch = graded.filter((s) => s._grade !== 'A');
    // Shadow is kept apart from the strategies that trade, as BUILD's relay asks, by sitting in
    // Unproven rather than in Watch — and it is labelled there, by its own standing banner.
    const unproven = [...d.shadow, ...d.nonRoster, ...d.unclassed];
    const ctx = [..._river.values()].filter((i) => i.type !== 'signal')
      .sort((a, b) => ((a.ts == null) - (b.ts == null)) || ((b.ts || 0) - (a.ts || 0))).slice(0, LANE_CONTEXT_MAX);

    const empty = (msg) => `<div class="rl-empty">${esc(msg)}</div>`;
    // R-IV.606(b): the seam is retired — `touches` and `exit` are live. A count of 0 is now a
    // MEASUREMENT (no idea touched the book this cycle), not the unknown it used to be.
    const book = bookEntries(d);
    const bookBody = book.length ? book.map(bookRow).join('')
      : empty(d.answered ? ('No idea in the feed touches an open position'
            + (_acctFilter === 'all' ? '' : ' in ' + ((_acctOptions.find((a) => a.key === _acctFilter) || {}).label || 'that account'))
            + ' this cycle.')
                         : 'The idea feed did not answer, so nothing could be matched against your book.');

    const circeToday = [..._river.values()].filter((i) => i.riverOnly && i.ts && etDate(i.ts) === etDate(now)).length;
    const circeRow = circeToday
      ? `<div class="rl-meter${circeToday > CIRCE_DAILY_CEILING ? ' over' : ''}">CIRCE'S STEW · SHADOW · ${circeToday} seen today (ET)`
        + (circeToday > CIRCE_DAILY_CEILING ? ` — above the ~${CIRCE_DAILY_CEILING}/day ceiling: the trigger is too loose (R-IV.421(d))` : '') + '</div>'
      : '';

    // R-IV.579(a)2 — the regression banner. A leaked row lands in Unproven, which is COLLAPSED,
    // so the row's own chip is not enough on its own: this sits above every lane, and the lane
    // holding the bad rows is opened. Nothing here is hidden behind a click.
    const bad = [...d.cryptoLeak, ...d.unclassed];
    const badNames = [...new Set(bad.map((s) => (s.ticker || '?').toUpperCase()))].slice(0, 6).join(', ');
    const errBanner = bad.length
      ? `<div class="rl-alert" role="alert"><b>The feed is serving rows it should not.</b> `
        + (d.cryptoLeak.length ? `${d.cryptoLeak.length} crypto row${d.cryptoLeak.length === 1 ? '' : 's'} — the server excludes crypto from every feed (RV4), so these are a regression, not a filter this page dropped. ` : '')
        + (d.unclassed.length ? `${d.unclassed.length} row${d.unclassed.length === 1 ? ' carries' : 's carry'} no <code>strategy_class</code>, which the feed states is never null (R-IV.577(b)); ${d.unclassed.length === 1 ? 'it is' : 'they are'} held out of Watch rather than guessed into it. ` : '')
        + `Each is shown on its own row, with its error: ${esc(badNames)}${bad.length > 6 ? ' …' : ''}.</div>`
      : '';

    const foot = [
      d.answered
        ? `${d.read} idea${d.read === 1 ? '' : 's'} read` + (d.total != null && d.total > d.read ? ` of ${d.total} active — the feed serves ${IDEA_PAGE} a page and ${d.pages} were taken; the rest score lower` : '')
        : 'the idea feed did not answer',
      d.levelCapped ? `${d.levelCapped} name${d.levelCapped === 1 ? '' : 's'} past the ${LANE_LEVEL_MAX}-name evidence read show "grade pending"` : '',
      d.unscored ? `${d.unscored} row${d.unscored === 1 ? ' carries' : 's carry'} no score, so ${d.unscored === 1 ? 'it sorts' : 'they sort'} last — not as a zero` : '',
      'read ' + (riverTime(d.at) || ''),
    ].filter(Boolean).join(' · ');

    el.innerHTML = notices + errBanner
      + laneShell('Actionable', actionable.length, actionable.length
          ? actionable.map((s) => laneSigRow(s, { grade: true })).join('')
          : empty(actionableReason(d, graded)), { key: 'actionable', note: 'A grade only' })
      + laneShell('Your book', d.answered ? book.length : '—', bookBody,
          { key: 'book', countUnknown: !d.answered, note: 'contradictions first',
            countTitle: d.answered ? 'Ideas touching an open position. One signal can touch two positions, and each is its own row.'
                                   : 'Unknown, not zero: the idea feed did not answer this cycle.' })
      // NOTABLE goes ABOVE the graded rows, not inside them (R-IV.1259(d)): a notable is not a
      // signal with a grade, and interleaving the two would make the lane's "grade shown" note
      // a claim about cards that have none.
      + laneShell('Watch', watch.length, nbWatch + (watch.length
          ? watch.map((s) => laneSigRow(s, { grade: true })).join('')
          : empty('No roster setup below A fired this cycle.')), { key: 'watch', note: 'grade shown; gates later' })
      + laneShell('Unproven', unproven.length, circeRow + (unproven.length
          // A display-mapped class keeps its name even when it never grades (shadow, river-only);
          // only a class the roster does not know surfaces under its raw DB identifier.
          ? unproven.map((s) => laneSigRow(s, { raw: !setupDisplay(s.codename || s.signal_type || s.strategy).roster })).join('')
          : empty('No shadow or non-roster class fired this cycle.')),
          // Open on an error: a row shown inside a collapsed lane is a row still hidden.
          { key: 'unproven', collapsed: true, open: bad.length > 0, note: 'no measured expectancy' })
      // The LOUD MOVE is PINNED at the top of Context (R-IV.1259(c)1), which is why the mock
      // block is prepended rather than appended: pinned means first, and a card placed after
      // the stream would be pinned in name only.
      + laneShell('Context', ctx.length, nbCtx + (ctx.length
          ? ctx.map((i) => `<div class="rl-row" data-rid="${esc(i.id)}"><div class="rl-main"><span class="rl-k">${esc(i.type)}</span>${i.text}</div><div class="rl-sub">${riverTime(i.ts) ? `<span class="rl-time">${esc(riverTime(i.ts))}</span>` : vintageChip({ unknownLabel: 'time unknown', unknownTitle: 'This item carries no time of its own, so none is shown.' })}</div></div>`).join('')
          : empty('Nothing in context yet.')), { key: 'context', note: 'not trades' })
      + `<div class="rl-foot">${esc(foot)}</div>`;
    applyGlossary(el);
  }

  function renderClassicRiver() {
    const el = $('riverStream'); if (!el) return;
    let items = [..._river.values()];
    if (_riverFilter !== 'all') items = items.filter((i) => i.type === _riverFilter);
    items.sort((a, b) => ((a.ts == null) - (b.ts == null)) || ((b.ts || 0) - (a.ts || 0)));
    items = items.slice(0, 60);
    // pills
    const types = ['all', 'signal', 'flow', 'catalyst', 'regime', 'headline'];
    $('riverPills').innerHTML = types.map((t) => `<button type="button" data-rt="${t}" class="${_riverFilter === t ? 'on' : ''}">${t}</button>`).join('');
    $('riverPills').querySelectorAll('button[data-rt]').forEach((b) => b.addEventListener('click', () => { _riverFilter = b.dataset.rt; renderRiver(); }));
    // R-IV.427(b): the daily count is the rate-limit surface. It counts fires THIS PAGE has
    // seen today (New York date): the ACTIVE feed it reads drops expired ideas, so this is a
    // floor on the day's fires, and the label says so.
    const today = etDate(Date.now());
    const circeToday = [..._river.values()].filter((i) => i.riverOnly && i.ts && etDate(i.ts) === today).length;
    const noticeRows = noticeRowsHtml(Date.now());
    // A regression belongs to the whole River, not to one of its views.
    const nBad = _laneData ? _laneData.cryptoLeak.length + _laneData.unclassed.length : 0;
    const cryptoRow = nBad
      ? `<div class="rv-alert" role="alert">The feed is serving ${nBad} row${nBad === 1 ? '' : 's'} it should not — crypto, or with no strategy_class. They are in the stream, not filtered out; switch to the lanes to see which.</div>` : '';
    const countRow = circeToday && (_riverFilter === 'all' || _riverFilter === 'signal')
      ? `<div class="rv-count${circeToday > CIRCE_DAILY_CEILING ? ' over' : ''}">CIRCE'S STEW · SHADOW · ${circeToday} seen today (ET)`
        + (circeToday > CIRCE_DAILY_CEILING ? ` — above the ~${CIRCE_DAILY_CEILING}/day ceiling: the trigger is too loose (R-IV.421(d))` : '') + '</div>'
      : '';
    if (!items.length) { el.innerHTML = noticeRows + countRow + cryptoRow + '<div class="rv-item info"><span class="rv-txt val-muted">stream quiet</span></div>'; return; }
    el.innerHTML = noticeRows + countRow + cryptoRow + items.map((it) => {
      const rt = riverTime(it.ts);
      const hh = rt ? rt : vintageChip({ unknownLabel: 'time unknown', unknownTitle: 'This item carries no time of its own, so none is shown.' });
      const acked = _rvAcked.has(it.id);
      const pulse = acked ? '' : (it.sev === 'down' ? ' pulse-vermilion' : it.sev === 'up' ? ' pulse-lime' : ' pulse-teal');
      const cls = it.tier === 'action' ? 'action sev-' + (it.sev === 'up' ? 'up' : it.sev === 'down' ? 'down' : 'teal') + pulse + (acked ? ' acked' : '') : it.tier;
      return `<div class="rv-item ${cls}" data-rid="${esc(it.id)}"><div class="rv-head"><span class="rv-dot t-${it.type}"></span><span class="rv-type">${it.type}</span><span class="rv-time">${hh}</span>${it.tier === 'shadow' ? '<span class="shadow-tag">shadow</span>' : ''}</div><div class="rv-txt">${it.text}</div></div>`;
    }).join('');
    // Click an action item to acknowledge — stops its pulse (nothing pulses forever).
    el.querySelectorAll('.rv-item.action[data-rid]').forEach((n) => n.addEventListener('click', (e) => { if (e.target.closest('[data-chart]')) return; _rvAcked.add(n.dataset.rid); renderRiver(); }));
  }

  // ── Popup helpers ───────────────────────────────────────────────────────────
  function openPopup(title, html, src) {
    const pop = $('memberPopup'), side = popSide(src, 'themes');
    syncTopbarH();
    pop.classList.toggle('side-left', side === 'left'); pop.classList.toggle('side-right', side !== 'left');
    $('memberTitle').textContent = title; $('memberBody').innerHTML = html; $('popupBackdrop').classList.add('open'); pop.classList.add('open');
    placeChartSoon();
  }
  function closePopup() {
    const was = $('memberPopup').classList.contains('open');
    $('popupBackdrop').classList.remove('open'); $('memberPopup').classList.remove('open');
    if (was) placeChartSoon();
  }

  // ── Polling groups (idle interval budget: 4 << 10) ──────────────────────────
  // loadYieldCurve runs AFTER loadRates: it writes the per-tenor chips into the slots
  // that table draws, and a chip written before its slot exists is a chip nobody sees.
  function refreshMarket() {
    loadThemes(); loadDivergence(); loadIndexStrip(); loadFx();
    loadRates().then(loadYieldCurve);
  }
  async function refreshDesk() {
    let positions = null;
    try { const r = await apiFetch('/api/v2/positions?status=OPEN'); if (r.ok) positions = await r.json(); } catch (_) {}
    setBookExits(positions);
    noteAccounts(positions, null);
    await refreshThemeMap(positions);
    loadBook(); loadKairos(); loadDeskStreams(); loadNotices();
  }

  // ── Top-bar quote ─────────────────────────────────────────────────────────
  // v1's regime-matched trader quotes, restored. The mood follows the composite regime; a new
  // quote every 10 minutes, no repeats within a day (ET), click for another. Rides the regime
  // poll (60 s, paused when the tab is hidden), so it adds no timer and no request.
  const QUOTE_MOOD = { TORO_MAJOR: 'greedy', TORO_MINOR: 'optimistic', NEUTRAL: 'pragmatic', URSA_MINOR: 'pessimistic', URSA_MAJOR: 'cynical' };
  const QUOTE_ROTATE_MS = 10 * 60 * 1000;
  const QUOTE_KEY = 'agora.quote.v1';
  let _qMem = null, _qMood = null, _qPending = null;
  function qLoad() { try { const v = JSON.parse(localStorage.getItem(QUOTE_KEY) || 'null'); if (v) return v; } catch (_) {} return _qMem; }
  function qSave(v) { _qMem = v; try { localStorage.setItem(QUOTE_KEY, JSON.stringify(v)); } catch (_) {} }
  // R-IV.611(b)1: `etDate` at the top of this file is already this exact formatter.
  const etDay = () => etDate(Date.now());
  function quoteTick(bias, advance) {
    const btn = $('v2Quote'), Q = window.AGORA_QUOTES;
    if (!btn) return;
    if (!Q) { btn.hidden = true; return; }
    // A failed read never moves the mood, and a new mood must be read twice in a row, so a
    // score sitting on a threshold does not churn the quote.
    const m = bias ? QUOTE_MOOD[String(bias).toUpperCase()] : null;
    if (m) {
      if (_qMood === null || m === _qMood) { _qMood = m; _qPending = null; }
      else if (_qPending === m) { _qMood = m; _qPending = null; }
      else _qPending = m;
    }
    let st = qLoad();
    const mood = _qMood || (st && st.cur && st.cur.mood) || 'pragmatic';
    const pool = Q[mood] || [];
    if (!pool.length) { btn.hidden = true; return; }
    const day = etDay(), now = Date.now();
    if (!st || st.day !== day) st = { day, seen: {}, cur: null };
    const keep = st.cur && st.cur.mood === mood && st.cur.i < pool.length && now - st.cur.at < QUOTE_ROTATE_MS;
    if (keep && !advance) {
      if (btn.dataset.key !== mood + ':' + st.cur.i) renderQuote(pool[st.cur.i], mood, st.cur.i, false);
      return;
    }
    let seen = (st.seen[mood] || []).filter((i) => i < pool.length);
    if (seen.length >= pool.length) seen = [];
    const left = pool.map((_, i) => i).filter((i) => seen.indexOf(i) < 0);
    const i = left[Math.floor(Math.random() * left.length)];
    seen.push(i); st.seen[mood] = seen; st.cur = { mood, i, at: now }; qSave(st);
    renderQuote(pool[i], mood, i, !btn.hidden);
  }
  function renderQuote(q, mood, i, animate) {
    const btn = $('v2Quote');
    const apply = () => {
      btn.querySelector('.q-text').textContent = '“' + q[0] + '”';
      btn.querySelector('.q-author').textContent = '— ' + q[1] + (q[2] ? ' · ' + q[2] + ' pick' : '');
      btn.dataset.mood = mood; btn.dataset.key = mood + ':' + i;
      btn.title = '“' + q[0] + '” — ' + q[1] + (q[2] ? '\n' + q[2] + "'s pick for its lane (source in assets/agora-quotes.js)" : '') + '\n\nQuote mood: ' + mood + ' (follows the composite regime). Click for another.';
      btn.hidden = false; btn.classList.remove('q-fade');
      syncTopbarH();
    };
    const still = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (animate && !still) { btn.classList.add('q-fade'); setTimeout(apply, 250); } else apply();
  }

  // ── Full-screen mode ────────────────────────────────────────────────────────
  // The page root goes full screen (not the grid), so drawers, popups and the chart stay
  // visible. Hidden where the browser cannot do it (iPhone Safari; an installed iOS app is
  // already chromeless).
  function initFullscreen() {
    const b = $('fsBtn'); if (!b) return;
    const d = document, root = d.documentElement;
    if (!(d.fullscreenEnabled || d.webkitFullscreenEnabled)) { b.hidden = true; return; }
    const cur = () => d.fullscreenElement || d.webkitFullscreenElement;
    const sync = () => {
      const on = !!cur();
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
      b.title = on ? 'Exit full screen (Esc)' : 'Full screen';
      b.classList.toggle('on', on);
    };
    b.addEventListener('click', () => {
      try {
        if (cur()) (d.exitFullscreen || d.webkitExitFullscreen).call(d);
        else { const pr = (root.requestFullscreen || root.webkitRequestFullscreen).call(root); if (pr && pr.catch) pr.catch(() => {}); }
      } catch (_) {}
    });
    d.addEventListener('fullscreenchange', sync); d.addEventListener('webkitfullscreenchange', sync);
    b.hidden = false; sync();
  }

  // ── Boot ────────────────────────────────────────────────────────────────────
  function boot() {
    applyGlossary(document);
    initGrid();
    loadRegimeBand(); managedInterval(loadRegimeBand, 60 * 1000);
    // R-IV.1257(b): with ?pop=v2 the drawer OPENS ITSELF once the data is in. Neither
    // reason is convenience: Nick previews it from the URL alone, and the headless gate
    // asserts nine rendered sections without driving a click. It awaits the band and the
    // sections first, so what opens is the live payload rather than an empty shell that
    // fills a second later -- the race that blanked the yield box.
    if (POP_V2_EXPLICIT) {
      (async () => {
        await loadRegimeBand();
        await loadRegimeSections();
        const btn = $('rsOpen');
        if (btn) openRegimeDetails(btn);
      })();
    }
    // R-IV.1186 v0: loaded ONCE and never polled. It is a fixture -- a refresh interval on a
    // static file would imply the card is tracking something, which is the impression v0 must
    // not give. The Open button is bound here rather than inline so the markup carries no
    // behaviour.
    loadRegimeStrategy();
    // A1 (R-IV.1209(c)): the four Agora boards as mock fixtures. Loaded ONCE and never polled,
    // for the same reason as the regime card above -- a refresh interval on a static file would
    // imply the tiles are tracking something, and in Phase A they are not.
    loadAgoraMocks();
    // A2 (R-IV.1209(c)): "Open" became "<DETAILS" and opens the LEFT drawer. The inline
    // playbook box it used to toggle is gone from the card; its content moves into the drawer
    // across B8.
    const rso = $('rsOpen');
    if (rso) rso.addEventListener('click', () => openRegimeDetails(rso));
    // The themes DRAWER was reachable only from the regime cell A2 removed, so its route moved
    // to the Themes tile (R-IV.1210(b)'s census). Bound here rather than inline, so the markup
    // carries no behaviour.
    const thb = $('themesDrawerBtn');
    if (thb) thb.addEventListener('click', () => openDrawer('themes',
      { composite: _lastRegime.composite, regime: _lastRegime.regime,
        tide: _lastRegime.tide, kill: _lastRegime.kill }, thb));
    loadMoversTape(); managedInterval(loadMoversTape, 5 * 60 * 1000);
    refreshMarket(); managedInterval(refreshMarket, 60 * 1000);
    refreshDesk(); managedInterval(refreshDesk, 2 * 60 * 1000);
    // The sector line chart (1D/5D toggle + isolation chips) lives in a drawer that is rebuilt
    // on every open, so its controls are delegated from the drawer body, not bound once.
    $('drawerBody').addEventListener('click', (e) => {
      if (!_divOpen) return;
      const w = e.target.closest('#divToggle button[data-w]');
      if (w) {
        _divWindow = w.dataset.w;
        $('divToggle').querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === w));
        loadDivergence(); return;
      }
      const chip = e.target.closest('#divLegend .div-chip'); if (!chip) return;
      if (chip.dataset.all) _divClear(); else _divToggle(chip.dataset.sym);
    });
    const dpb = $('divPopBtn');
    if (dpb) dpb.addEventListener('click', () => openDrawer('divergence', {}, dpb));
    // The card's badge is the way into the kill drawer now that the header pill is gone
    // (R-IV.1246(c)3). It is only clickable when it is shown, which is only when armed or
    // unreadable — the two states worth opening.
    const kb = $('rsKill');
    if (kb) {
      kb.setAttribute('role', 'button');
      kb.setAttribute('tabindex', '0');
      kb.addEventListener('click', () => openDrawer('kill', { kill: _lastRegime.kill }, kb));
    }
    // The Breadth tile is the only way into the breadth drawer now that the band's duplicate
    // New H/L and % > 50DMA cells are gone.
    const bp = $('breadthPanel');
    if (bp) {
      bp.setAttribute('role', 'button'); bp.setAttribute('tabindex', '0'); bp.title = 'Open breadth detail';
      const openB = () => openDrawer('breadth', { regime: _lastRegime.regime }, bp);
      bp.addEventListener('click', openB);
      bp.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openB(); } });
    }
    $('drawerClose').addEventListener('click', closeDrawer);
    $('drawerBackdrop').addEventListener('click', closeDrawer);
    $('tvPopClose').addEventListener('click', () => closeChart());
    $('memberClose').addEventListener('click', closePopup);
    $('popupBackdrop').addEventListener('click', closePopup);
    $('bookAdd').addEventListener('click', openAddForm);
    $('modalClose').addEventListener('click', closeModal);
    $('modalBackdrop').addEventListener('click', closeModal);
    // Any ticker marked data-chart opens the chart: one delegated handler, so tiles that
    // re-render every poll need no re-wiring. Buttons inside a ticker row keep their own job.
    document.addEventListener('click', (e) => {
      const t = e.target.closest && e.target.closest('[data-chart]');
      if (!t || t.closest('#tvPopover')) return;
      if (e.target.closest('button, a, .opt-btn, .btn-committee, .kairos-tag, .flow-tag')) return;
      e.preventDefault();
      openChart(t.dataset.chart, t);
    });
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const t = e.target.closest && e.target.closest('[data-chart]');
      if (!t || e.target !== t) return;
      e.preventDefault(); openChart(t.dataset.chart, t);
    });
    // Escape closes only the chart when one is open (capture phase, so the page-wide close
    // below does not also fire). Once focus is inside the TradingView frame, use the ✕.
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !document.getElementById('v2-login') && closeChart()) { e.stopImmediatePropagation(); e.preventDefault(); }
    }, true);
    syncTopbarH();
    window.addEventListener('resize', () => { syncTopbarH(); placeChart(); });
    document.addEventListener('fullscreenchange', () => { syncTopbarH(); placeChartSoon(); });
    // 'Layout saved' is a receipt, not a status: fade it after 5 s.
    const ls = $('layoutStatus');
    if (ls && window.MutationObserver) {
      let lt = null;
      new MutationObserver(() => {
        ls.classList.remove('faded'); clearTimeout(lt);
        if (ls.textContent && !/locked/.test(ls.textContent)) lt = setTimeout(() => ls.classList.add('faded'), 5000);
      }).observe(ls, { childList: true, characterData: true, subtree: true });
    }
    // Escape peels one layer at a time: chart (above) → modal → theme popup → drawer →
    // divergence selection. The River preview and Positions panel keep their own handlers.
    // The sign-in overlay is never dismissed.
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape' || document.getElementById('v2-login')) return;
      if ($('posModal').classList.contains('open')) closeModal();
      else if ($('memberPopup').classList.contains('open')) closePopup();
      else if ($('drawer').classList.contains('open')) closeDrawer();
      else _divClear();
    });
    initFullscreen();
    const qb = $('v2Quote');
    if (qb) qb.addEventListener('click', () => { const c = _lastRegime.composite; quoteTick(c && (c.bias_level || c.level), true); });
    try { window.__mgd = _managed.size; } catch (_) {}  // idle interval count (acceptance check)
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

/* Positions panel, R-IV.509, LIVE since R-IV.697 (the "mock data only" this line used to say stopped
   being true then, and a stale header is how a reader gets the module wrong). Redesigned by R-IV.1382,
   with `?pos=v1` restoring the R-IV.697 layout until 2026-11-06. */
(function () {
  'use strict';
// ── The live book (R-IV.697) ─────────────────────────────────────────────────────────────────
// This panel read MOCK data until now. The scope (R-IV.691(c)) found that for identity, money,
// marks, lots, legs and the closed history the endpoints already existed and were already proven
// by the Book lane — so what follows is a read, not a new contract. Four rules come from
// R-IV.697(c), and each one is the fix for a trap that was MEASURED in the book, not guessed:
//
//   1. LEGS COME FROM `/legs` (the `position_legs` table), never from the position row's `legs`
//      jsonb column. The jsonb is populated on 2 of 28 open rows; the table covers 19. Same
//      name, two sources, and the nearly-empty one is the one sitting on the row you already
//      have — which is exactly why it gets read by mistake.
//   2. HISTORY ASKS FOR `CLOSED` AND `EXPIRED` BY NAME. `status=ALL` also returns
//      `DUPLICATE_OF` — 78 rows that are the same trade recorded twice. Naming the two statuses
//      excludes them structurally, rather than by remembering to filter.
//   3. EVIDENCE COMES FROM THE LOTS. Position-level `broker_ref` is 0 of 28, while 52 of the 61
//      lots on open rows carry one. Reading the position field would report no evidence at all
//      for a book that is largely evidenced.
//   4. THE BUCKET LEGEND IS GENERATED FROM THE TAGS SERVED, as the account filter is. The old
//      hardcoded legend listed CORE, HEDGE and B3, which nothing serves, and omitted CONVEXITY,
//      which is served.
//
// Two further rules about absence, because they are what keeps the seam honest:
//
//   * The discipline fields — stop, invalidation, time stop, tags — have columns, a CHECK
//     constraint, a parser and a reader, and NO WRITER (BUILD gap 3). They read "not captured
//     yet", never "none": "none" asserts there is no stop, and the truth is that nothing has ever
//     been able to record one.
//   * Anything with no source at all is ABSENT, not mocked. The sleeve-ceiling gauge, the roll
//     chain and the ticket's invented headroom figures are gone. A bar needs a ceiling, and
//     there is no ceiling anywhere in the schema.
//
// No money arithmetic happens on this page. The unrealized P&L is the hub's lot-derived figure,
// not `mark − cost`, and the realized total and win rate come from the hub's own census
// (`/api/abacus/summary`, which runs the one predicate). The single exception is the at-risk sum,
// which has no server-side figure at all — so it is shown with its n on its face, as R-IV.697
// requires of a total over a partly populated column.

const HIST_N = 12;                       // the list shows the most recent N; the census is the hub's
const BK = {
  open: { status: 'idle', err: null, rows: [], age: null },
  hist: { status: 'idle', err: null, rows: [], total: 0, stats: null, range: null },
  sub: {},                               // position_id -> { status, err, lots, legs, agrees, storedQty, mergedInto }
};
const bkApi = () => (window.__v2 && window.__v2.apiFetch) || window.fetch.bind(window);
async function bkJson(path) {
  const r = await bkApi()(path, { credentials: 'same-origin' });
  if (!r.ok) throw new Error(r.status === 401 ? 'your session has expired — sign in again to see your book' : 'the hub answered HTTP ' + r.status);
  return r.json();
}
const bkNum = (v) => (v === null || v === undefined || v === '' || Number.isNaN(Number(v)) ? null : Number(v));
// `mark_status` is the hub's own word for whether the price can be trusted. OK / STALE /
// UNAVAILABLE are the three it serves; anything else is treated as unconfirmed rather than fresh.
const MARK_STATE = { OK: 'fresh', STALE: 'stale', UNAVAILABLE: 'unknown' };

function viewRow(r) {
  const d = r.derived || {};
  return {
    id: r.id, pid: r.position_id, account: r.account || null, acct: r.account_display || null,
    ticker: r.ticker || '', assetType: String(r.asset_type || '').toUpperCase(),
    structure: String(r.structure || r.asset_type || '').replace(/_/g, ' '),
    strikes: [r.long_strike, r.short_strike].filter((x) => x != null).map(bkNum).join('/'),
    expiry: r.expiry ? String(r.expiry).slice(0, 10) : null, dte: bkNum(r.dte),
    // R-IV.662(c)/668(c): what is OPEN is `open_quantity`, and it NEVER falls back to `quantity`
    // (the size the position was opened at). A null reads as unknown and says why.
    qty: bkNum(r.open_quantity),
    qtyWhy: r.open_quantity_basis || 'this feed does not serve open_quantity yet (BUILD, R-IV.696(c))',
    cost: bkNum(r.cost_basis),
    mark: bkNum(r.current_price),
    markState: MARK_STATE[String(r.mark_status || '').toUpperCase()] || 'unknown',
    markWhy: r.mark_reason || null, markAt: r.mark_checked_at || null,
    // R-IV.1262(b)3 / R-IV.943(c): the mark's OWN instant and the hub's OWN verdict, both served
    // now. `mark_as_of` is an exact UTC instant (never a day) and is on 3 of 29 rows;
    // `price_updated_at` is on 23 and is the only age most rows have. `mark_checked_at` is when the
    // job LOOKED, which is not when the price was good -- a row checked a minute ago can hold a
    // four-day-old price, so it is kept but never used as the age.
    markAsOf: r.mark_as_of || null,
    priceAt: r.price_updated_at || null,
    markIntegrity: r.mark_integrity ? String(r.mark_integrity).toLowerCase() : null,
    markIntegrityWhy: r.mark_integrity_reason || null,
    // The hub's lot-derived figure. `mark − cost` on the page was wrong for every spread and
    // right by accident for single legs.
    pnl: bkNum(r.unrealized_pnl), pnlWhy: d.basis_reason || r.basis_incomplete_reason || null,
    maxLoss: bkNum(r.max_loss), maxLossWhy: d.basis_reason || null,
    prov: String(r.provenance || 'UNKNOWN').toUpperCase(),
    basisIncomplete: r.basis_incomplete_reason || null,
    bucket: r.strategy_tag || null,
    stopType: r.stop_type || null, stopLevel: bkNum(r.stop_loss),
    invalidation: r.invalidation || null,
    timeStop: r.time_stop ? String(r.time_stop).slice(0, 10) : null,
    tags: Array.isArray(r.tags) ? r.tags.filter(Boolean) : [],
  };
}

function histRow(r) {
  return {
    id: r.id, pid: r.position_id, ticker: r.ticker || '',
    structure: String(r.structure || r.asset_type || '').replace(/_/g, ' '),
    account: r.account || null, acct: r.account_display || null,
    closedAt: r.exit_date ? String(r.exit_date) : '', closed: r.exit_date ? String(r.exit_date).slice(0, 10) : null,
    realized: bkNum(r.realized_pnl), why: r.trade_outcome || null,
    prov: String(r.provenance || 'UNKNOWN').toUpperCase(),
    status: String(r.status || '').toUpperCase(),
    // ONLY what the hub states on the row. The census's third exclusion — a return past −100% of
    // basis — is a RATIO, and deciding it here would be a second implementation of the server's
    // predicate, free to drift from it. Its COUNT comes from the hub's coverage block; no row is
    // labelled with it by this page.
    flag: r.basis_incomplete_reason ? 'basis incomplete' : (bkNum(r.realized_pnl) === null ? 'no realized P&L recorded' : null),
  };
}

// One bucket per account served, in a stable order, with an unattributed row last and never
// given a name nobody served (R-IV.650(a)).
function accountsOf(rows) {
  const by = new Map();
  rows.forEach((p) => {
    const k = p.account || null;
    if (!by.has(k)) by.set(k, { account: k, acct: p.acct, rows: [] });
    by.get(k).rows.push(p);
  });
  return [...by.values()].sort((a, b) => (a.account === null) - (b.account === null)
    || String(a.acct || a.account || '').localeCompare(String(b.acct || b.account || '')));
}

async function loadOpen() {
  if (BK.open.status === 'loading') return;
  BK.open.status = 'loading'; BK.open.err = null; if (st.open) render();
  try {
    const d = await bkJson('/api/v2/positions?status=OPEN');
    BK.open.rows = (d.positions || []).map(viewRow);
    // R-IV.1382(d)6: the RAW row is kept beside the view row, because the Book module's Close and
    // Add forms read the /api/v2/positions row itself -- handing them a view row would be a copy.
    BK.open.raw = new Map((d.positions || []).map((r) => [r.position_id, r]));
    BK.open.age = bkNum(d.cache_age_seconds);
    BK.open.status = 'ok';
  } catch (e) { BK.open.status = 'error'; BK.open.err = String((e && e.message) || e); }
  if (st.open) render();
}

async function loadHist() {
  if (BK.hist.status === 'loading') return;
  BK.hist.status = 'loading'; BK.hist.err = null; if (st.open) render();
  try {
    // The census comes from `/api/abacus/summary`, which runs `_load_book_realized` — the one
    // predicate. If it cannot be read the rows still show; the panel then says it has no census
    // rather than adding up the column itself.
    const [closed, expired, sum] = await Promise.all([
      bkJson('/api/v2/positions?status=CLOSED'),
      bkJson('/api/v2/positions?status=EXPIRED'),
      bkJson('/api/abacus/summary?range=all').catch(() => null),
    ]);
    const rows = [...(closed.positions || []), ...(expired.positions || [])].map(histRow)
      .sort((a, b) => b.closedAt.localeCompare(a.closedAt));
    BK.hist.total = rows.length;
    BK.hist.rows = rows.slice(0, HIST_N);
    BK.hist.stats = sum ? (sum.stats || []).filter((t) => t && t.source === 'live') : null;
    BK.hist.range = sum ? sum.range : null;
    BK.hist.status = 'ok';
  } catch (e) { BK.hist.status = 'error'; BK.hist.err = String((e && e.message) || e); }
  if (st.open) render();
}

// Lots and legs, per position, on demand — and only once per position per session unless a read
// failed. Two requests, because they are two tables with two provenance stories.
async function loadSub(p) {
  if (!p || !p.pid) return;
  const cur = BK.sub[p.pid];
  if (cur && (cur.status === 'loading' || cur.status === 'ok')) return;
  BK.sub[p.pid] = { status: 'loading', err: null, lots: [], legs: [] }; if (st.open) render();
  try {
    const path = '/api/v2/positions/' + encodeURIComponent(p.pid);
    const [lots, legs] = await Promise.all([bkJson(path + '/lots'), bkJson(path + '/legs')]);
    BK.sub[p.pid] = {
      status: 'ok', err: null,
      lots: lots.lots || [], legs: legs.legs || [],
      // The hub says whether the lots and the stored quantity agree. Where they do not, the row
      // is an aggregate that has drifted from its own fills, and both figures are shown.
      agrees: lots.agrees_with_stored === true, agreesKnown: typeof lots.agrees_with_stored === 'boolean',
      lotQty: lots.derived && bkNum(lots.derived.qty), storedQty: bkNum(lots.stored_quantity),
      mergedInto: (legs.migration && legs.migration.merged_into) || null,
    };
  } catch (e) { BK.sub[p.pid] = { status: 'error', err: String((e && e.message) || e), lots: [], legs: [] }; }
  if (st.open) render();
}

const X = (function () {
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const MINUS = '−';
  const usd = (v, signed) => v == null ? '—' : (v < 0 ? MINUS : (signed && v > 0 ? '+' : '')) + '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: 2 });
  const pct = (v) => v == null ? '—' : (v * 100).toFixed(1) + '%';
  const tone = (v) => v == null ? '' : v > 0 ? 'pp-up' : v < 0 ? 'pp-down' : '';

  const PROV = {
    UNKNOWN: ['unknown', 'unknown', 'Lowest rung: nothing says where this came from.'],
    BROKER_VERIFIED: ['verified', 'broker verified', 'A broker record backs this row (reference on file).'],
    SCREEN_VERIFIED: ['screen', 'screen read', 'Read off a broker screen; an import or broker record will supersede it.'],
    PRINCIPAL_REPORTED: ['reported', 'reported', 'Reported by the principal; no broker evidence yet.'],
    IMPORTED: ['imported', 'imported', 'Loaded from an export file; ranks above a screen read, below a broker-referenced record.'],
  };
  const prov = (p) => { const [s, l, t] = PROV[p] || ['reported', p, '']; return `<span class="pp-chip" data-state="${s}" title="${esc(t)}">${esc(l)}</span>`; };
  const chip = (state, label, title) => `<span class="pp-chip" data-state="${state}"${title ? ` title="${esc(title)}"` : ''}>${esc(label)}</span>`;
  const LADDER = ['UNKNOWN', 'PRINCIPAL_REPORTED', 'SCREEN_VERIFIED', 'IMPORTED', 'BROKER_VERIFIED'];
  const ladder = () => `<div class="pp-ladder">Provenance, weakest to strongest: ${LADDER.map((k) => prov(k)).join(' <span class="pp-dim">&lt;</span> ')}</div>`;

  // Generated from what the hub serves (R-IV.697(c)), so a bucket nobody uses is not advertised
  // and one that is used cannot be missing. The notes are the playbook's own words for the three
  // numbered buckets; a tag this page has no words for is listed bare rather than described.
  const BUCKET_NOTE = { B1: 'multi-week thesis', B2: 'tactical, 3–5 days', B3: 'intraday scalp' };
  function servedBuckets() {
    const s = new Set();
    BK.open.rows.concat(BK.hist.rows).forEach((p) => { if (p.bucket) s.add(p.bucket); });
    return [...s].sort();
  }
  const buckets = () => {
    const b = servedBuckets();
    return `<div class="pp-ladder">Buckets, as served on your own rows: ${b.length
      ? b.map((n) => `<span class="pp-tag">${esc(n)}${BUCKET_NOTE[n] ? ' · ' + esc(BUCKET_NOTE[n]) : ''}</span>`).join(' ')
      : '<span class="pp-amber">none served yet</span>'}</div>`;
  };

  // "not captured yet" is NOT "none". The column exists and nothing can write to it, so the hub
  // has nothing to serve — which is a different fact from the principal having left it empty.
  const GAP3 = ' has a column, a constraint and a reader, but no writer yet (BUILD gap 3) — so the hub has nothing to serve for it.';
  const notCaptured = (what) => chip('unknown', 'not captured yet', what + GAP3);

  // One shape for every "the hub has not answered yet" state, so a failure can never read as an
  // empty book: an error says so, and offers the read again.
  function state(s, busyText, what, retry) {
    if (s.status === 'error') return `<div class="pp-note pp-warn" role="alert">Could not read ${esc(what)}: ${esc(s.err)}<div><button type="button" class="pp-btn" data-bk-retry="${esc(retry)}">Try again</button></div></div>`;
    return `<div class="pp-note">${esc(busyText)}</div>`;
  }

  const acctLabel = (p) => p.acct ? p.acct : (p.account ? 'name not served' : 'Unattributed');

  function qtyCell(p) {
    if (p.qty == null) return `<span class="pp-amber" title="${esc(p.qtyWhy)}">unknown</span>`;
    return String(p.qty);
  }
  // ── R-IV.1262(b)3 · EVERY MARK-DERIVED FIGURE SHOWS ITS MARK'S AGE ───────────────────────────
  //
  // The treatment drafted and parked under R-IV.943(e); its two blocking fields are served now.
  // Three rules from that draft, each with its reason, so neither survives as a mere habit:
  //
  //   1. THE AGE SHOWS IN EVERY STATE, not only when something is wrong. An age that appears only
  //      on a bad row teaches its absence to mean "fine", and then a field that stops arriving
  //      looks like good news.
  //   2. THE PAGE PICKS NO THRESHOLD. "Stale" is the hub's word (`mark_integrity`, else
  //      `mark_status`); this file renders the verdict and the raw age and judges neither. The
  //      26-hour line is the hub's, set in one backend place (R-IV.943(c)); the B2 gate's
  //      post-close rule is a different question about the same price (Convention #38).
  //   3. "AGE UNKNOWN" IS NOT "NO PRICE". The first says the hub could not tell us when, the
  //      second that there is nothing to show. One phrase for both hides which happened.
  //
  // AND THE P&L CARRIES IT TOO, which is the point the draft was written for: the Book row has no
  // mark column, so when the price is a day old the P&L is a day old and nothing on that row says
  // so. The P&L here IS the mark-derived figure.
  const MARK_VERDICT = { ok: 'verified', stale: 'unknown', wide: 'unknown', unknown: 'unknown' };
  function markAge(p) {
    // `mark_as_of` first because it is the authored instant for the mark itself; `price_updated_at`
    // is the fallback and is NAMED as such, so a reader can tell which clock they are being shown.
    const iso = p.markAsOf || p.priceAt || null;
    const src = p.markAsOf ? 'mark' : (p.priceAt ? 'price' : null);
    if (!iso) return null;
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return null;
    const ms = Date.now() - t;
    if (ms < 0) return { txt: 'timed ahead of now', iso: iso, src: src, odd: true };
    const m = Math.floor(ms / 60000);
    const txt = m < 1 ? 'seconds old' : m < 60 ? m + ' min old'
      : m < 1440 ? Math.floor(m / 60) + ' h old' : Math.floor(m / 1440) + ' d old';
    return { txt: txt, iso: iso, src: src, odd: false };
  }
  // The age's VERDICT and its WHY, shared by the chip below and by R-IV.1382's AGE cell, so the
  // two places that show a mark's age cannot explain the same age two ways.
  function ageVerdict(p) {
    return p.markIntegrity ? (MARK_VERDICT[p.markIntegrity] || 'unknown')
      : (p.markState === 'fresh' ? 'verified' : 'unknown');
  }
  function ageUnknownWhy(p) {
    return 'The hub served no time for this price, so how old it is cannot be stated. That is not the '
      + 'same as having no price: this row HAS one.'
      + (p.markIntegrityWhy ? ' The hub says: ' + p.markIntegrityWhy : '');
  }
  function ageWhy(p, a) {
    const word = p.markIntegrity || (p.markState === 'fresh' ? null : p.markState);
    return [
      a.src === 'mark' ? 'From `mark_as_of`, the mark\'s own instant.'
                       : 'From `price_updated_at` — this row carries no `mark_as_of`, so the age is the price\'s, not the mark\'s.',
      'Timed ' + when(a.iso) + '.',
      word ? 'The hub calls this mark ' + String(word).toUpperCase() + '.' : 'The hub calls this mark current.',
      p.markIntegrityWhy || p.markWhy || '',
      a.odd ? 'The hub timed it AHEAD of now, which is a clock disagreement, not a fresh price.' : '',
    ].filter(Boolean).join(' ');
  }
  function ageChip(p) {
    const a = markAge(p);
    if (!a) return ' ' + chip('unknown', 'age unknown', ageUnknownWhy(p));
    return ' ' + chip(a.odd ? 'unknown' : ageVerdict(p), a.txt, ageWhy(p, a));
  }
  // R-IV.1382(d)4 AGE, as a short cell: "N min" / "N h" / "N d" in --text-2; amber when the hub's
  // verdict is not current; amber "age unknown" when the hub served no time; "—" with no price.
  // R-IV.1262(b)3: this one cell carries the age for BOTH the mark and the P&L on its row.
  function ageInfo(p) {
    if (p.mark == null) return { txt: '—', amber: false, why: 'No price, so there is no age to show.' };
    const a = markAge(p);
    if (!a) return { txt: 'age unknown', amber: true, why: ageUnknownWhy(p) };
    const txt = a.odd ? 'ahead of now' : a.txt === 'seconds old' ? '<1 min' : a.txt.replace(/ old$/, '');
    return { txt, amber: a.odd || ageVerdict(p) !== 'verified', why: ageWhy(p, a), words: a.txt };
  }
  function markCell(p) {
    if (p.mark == null) return `<span class="pp-amber" title="${esc(p.markWhy || 'the hub served no mark for this position')}">no mark</span>`;
    const v = usd(p.mark);
    if (p.markState === 'stale') return `${v} ${chip('unknown', 'stale mark', 'The hub marks this price STALE' + (p.markWhy ? ': ' + p.markWhy : '') + ', so it cannot be read as current.')}${ageChip(p)}`;
    if (p.markState !== 'fresh') return `${v} ${chip('unknown', 'unconfirmed', 'The hub does not call this mark current' + (p.markWhy ? ': ' + p.markWhy : '') + '.')}${ageChip(p)}`;
    return v + ageChip(p);
  }
  function pnlCell(p) {
    if (p.pnl == null) return `<span class="pp-amber" title="${esc(p.pnlWhy || 'the hub derived no P&L for this row')}">no P&amp;L</span>`;
    // The age rides with the figure it qualifies. A P&L drawn from a four-day-old price is a
    // four-day-old P&L, and this row is the only place the reader sees it.
    return `<span class="${tone(p.pnl)}">${usd(p.pnl, true)}</span>${ageChip(p)}`;
  }

  // The sleeve line. There is NO ceiling anywhere in the schema, so there is no gauge: a bar
  // without a limit draws a judgement the hub cannot make.
  //
  // R-IV.719(c): AND THERE IS NO AT-RISK TOTAL EITHER, for now. It was shown with the count it was
  // drawn from, which answered how MANY rows carry a max loss and not whether the values are right.
  // They are not: on the closed book 31 losing trades are recorded as having lost MORE than their
  // own defined maximum, which cannot happen to a defined-risk trade. Summing a column like that
  // produces a figure the principal would size positions against.
  //
  // The lesson, written where the next person will be tempted: PUBLISHING n DOES NOT FIX A WRONG
  // DENOMINATOR. A coverage chip answers "how much of the sample is this", never "are these true".
  function sleeveLine(g) {
    return `<div class="pp-sleeve">
      <span>At risk <span class="pp-amber" title="The hub's max_loss is unreliable: losing trades are recorded as having lost more than their own defined maximum, so a sum of that column cannot be trusted. Returns when BUILD's fix lands (R-IV.714(d)).">not reliable yet</span>
        ${chip('unknown', 'withheld', 'No figure from max_loss is shown anywhere until BUILD’s R-IV.714(d) fix lands.')}</span>
      <span>Ceiling ${chip('unknown', 'no source', 'No sleeve ceiling or cash floor exists anywhere in the schema, so none is drawn. The playbook’s rule has never been recorded as data.')}</span>
    </div>`;
  }

  function stopLine(p) {
    if (!p.stopType) return notCaptured('The stop');
    const map = { broker_order: 'verified', 'broker order': 'verified', daily_close: 'screen', 'daily-close': 'screen', none: 'reported' };
    const note = { broker_order: 'Rests at the broker; fires on its own.', daily_close: 'Watched at the close; fires only if someone acts.', none: 'Recorded as having no stop.' };
    const k = String(p.stopType).toLowerCase();
    return chip(map[k] || 'reported', 'stop: ' + String(p.stopType).replace(/_/g, ' '), note[k] || '')
      + (p.stopLevel != null ? ` <span class="pp-dim">${esc(usd(p.stopLevel))}</span>` : '');
  }

  function bookRow(p, attrs) {
    return `<tr class="pp-row" ${attrs || ''} data-id="${p.id}">
      <td><b>${esc(p.ticker)}</b><div class="pp-dim">${p.bucket ? esc(p.bucket) : 'no bucket served'}</div></td>
      <td>${esc(p.structure)}${p.strikes ? ' ' + esc(p.strikes) : ''}${p.expiry ? `<div class="pp-dim">exp ${esc(p.expiry.slice(5))}${p.dte != null ? ' · ' + p.dte + 'd' : ''}</div>` : ''}</td>
      <td class="pp-num">${qtyCell(p)}</td><td class="pp-num">${usd(p.cost)}</td><td class="pp-num">${markCell(p)}</td>
      <td class="pp-num">${pnlCell(p)}</td><td>${prov(p.prov)}</td></tr>`;
  }
  const bookHead = `<thead><tr><th>Position</th><th>Structure</th><th class="pp-num">Open</th><th class="pp-num">Cost</th><th class="pp-num">Mark</th><th class="pp-num">P&amp;L</th><th>Provenance</th></tr></thead>`;
  function bookTable(account, rowAttrs) {
    const rows = BK.open.rows.filter((p) => (p.account || null) === account);
    if (!rows.length) return `<div class="pp-note">The hub reports no open positions in this account.</div>`;
    return `<table class="pp-table">${bookHead}<tbody>${rows.map((p) => bookRow(p, rowAttrs ? rowAttrs(p) : '')).join('')}</tbody></table>`;
  }

  function detail(p) {
    const s = BK.sub[p.pid] || { status: 'idle', lots: [], legs: [] };
    const head = `<h3>${esc(p.ticker)} · ${esc(p.structure)}${p.strikes ? ' ' + esc(p.strikes) : ''} ${prov(p.prov)}</h3>
      <div class="pp-dim">${esc(acctLabel(p))}${p.expiry ? ' · expires ' + esc(p.expiry) : ''}</div>
      ${p.basisIncomplete ? `<div class="pp-note pp-warn">Basis under review — ${esc(p.basisIncomplete)}</div>` : ''}
      <div class="pp-kv">
        <div><span class="pp-k">Stop</span>${stopLine(p)}</div>
        <div><span class="pp-k">Time stop</span>${p.timeStop ? esc(p.timeStop) : notCaptured('The time stop')}</div>
        <div class="pp-wide"><span class="pp-k">Invalidation</span>${p.invalidation ? esc(p.invalidation) : notCaptured('The invalidation')}</div>
        <div class="pp-wide"><span class="pp-k">Tags</span>${p.tags.length ? p.tags.map((t) => `<span class="pp-tag">${esc(t)}</span>`).join(' ') : notCaptured('Tags')}</div>
        <div><span class="pp-k">Max loss</span><span class="pp-amber" title="The hub's max_loss is unreliable (R-IV.719(c)): losing trades are recorded as having lost more than their own defined maximum, so no figure from it is shown until BUILD's R-IV.714(d) fix lands.">not reliable yet</span></div>
      </div>`;
    if (s.status !== 'ok') return `<div class="pp-detail">${head}${state(s, 'Reading this position’s lots and legs…', 'lots and legs', p.pid)}</div>`;

    const lots = s.lots.map((l) => `<tr><td>${esc(when(l.fill_time))}</td><td class="pp-num">${esc(l.qty)}</td><td class="pp-num">${esc(l.price)}</td><td class="pp-num">${l.fees == null ? '—' : esc(l.fees)}</td><td>${prov(String(l.provenance || 'UNKNOWN').toUpperCase())}</td><td class="pp-dim">${l.broker_ref ? esc(l.broker_ref) : 'no reference'}</td></tr>`).join('');
    const legs = s.legs.map((g) => `<tr><td>${esc(g.leg_seq)}</td><td>${esc(g.side || '')}</td><td>${esc(g.option_type || '')}</td><td class="pp-num">${g.strike == null ? '—' : esc(g.strike)}</td><td class="pp-num">${g.qty == null ? '—' : esc(g.qty)}</td><td class="pp-num">${g.price == null ? '<span class="pp-amber">unpriced</span>' : esc(g.price)}</td></tr>`).join('');
    // The evidence IS the lots (R-IV.697(c)). A count first, so "how much of this is backed by a
    // broker record" is answerable without reading every line.
    const refs = s.lots.filter((l) => l.broker_ref).length;
    const drift = s.agreesKnown && !s.agrees
      ? `<div class="pp-note pp-warn">The lots sum to ${esc(s.lotQty)} and the row stores ${esc(s.storedQty)}: this position's stored quantity has drifted from its own fills, and the hub says so rather than reconciling it silently.</div>`
      : '';
    return `<div class="pp-detail">${head}${drift}
      <h4>Lots <span class="pp-dim">${s.lots.length} · ${refs} with a broker reference</span></h4>
      ${s.lots.length ? `<table class="pp-table pp-sm"><thead><tr><th>Filled</th><th class="pp-num">Qty</th><th class="pp-num">Price</th><th class="pp-num">Fees</th><th>Provenance</th><th>Reference</th></tr></thead><tbody>${lots}</tbody></table>`
        : '<div class="pp-note">The hub holds no lots for this position, so its basis cannot be derived from fills.</div>'}
      <h4>Legs</h4>
      ${s.legs.length ? `<table class="pp-table pp-sm"><thead><tr><th>#</th><th>Side</th><th>Type</th><th class="pp-num">Strike</th><th class="pp-num">Qty</th><th class="pp-num">Price</th></tr></thead><tbody>${legs}</tbody></table>`
        : `<div class="pp-note">${s.mergedInto ? 'The legs for this position are recorded on ' + esc(s.mergedInto) + '.' : 'The hub holds no legs for this position.'}</div>`}
      <h4>Evidence</h4>
      <ul class="pp-evid"><li>${refs} of ${s.lots.length} lots carry a broker reference${refs < s.lots.length ? '; the rest are backed by their own provenance rung only' : ''}.</li>
        <li>This row's own <code>broker_ref</code> field is not read: it is empty on every open position, while the lots behind them are not. The evidence lives at the fill.</li>
        ${p.markAt ? `<li>Mark last checked ${esc(when(p.markAt))}${p.markWhy ? ' — ' + esc(p.markWhy) : ''}.</li>` : ''}</ul>
    </div>`;
  }
  // R-IV.726: THE SAME DAY-VERSUS-MOMENT RULE, ON THIS SIDE. `position_lots.fill_time` is a
  // `timestamptz` holding both kinds: 1392 of the book's 1416 lots sit at exactly midnight UTC,
  // which is a DAY someone wrote down, and 24 carry a real fill time. Formatting a day in Mountain
  // Time printed "6:00 PM" on the PREVIOUS day — a time nobody recorded, against the wrong date.
  // A day is therefore rendered as a day, with no time at all, and only a real moment gets a clock.
  const when = (iso) => {
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return String(iso || '—');
    const d = new Date(t);
    if (!d.getUTCHours() && !d.getUTCMinutes() && !d.getUTCSeconds() && !d.getUTCMilliseconds()) {
      return new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric' }).format(d);
    }
    return new Intl.DateTimeFormat('en-US', { timeZone: 'America/Denver', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(d) + ' MT';
  };

  function actions(p) {
    const A = [
      ['Edit', 'Change tags, stop, invalidation, time stop.', 'Waits on the capture path: these columns have no writer yet (BUILD gap 3).', true],
      ['Add a lot', 'Record another fill into this position.', 'Needs: fill time, qty, price, fees — and a broker reference or a screen capture.', false],
      ['Close', 'End the position and record the result.', 'Use Close on the Book row: it posts to the hub today. Result is recomputed from lots.', false],
      ['Roll', 'Close this and open the next as one linked trade.', 'Waits on R-IV.452, and on a link field: nothing in the schema records that one position followed another.', true],
    ];
    return `<div class="pp-actions"><h4>Actions on ${esc(p.ticker)} #${p.id}</h4>${A.map(([n, d, need, off]) => `<div class="pp-act${off ? ' off' : ''}"><button type="button" class="pp-btn" ${off ? 'disabled' : ''}>${esc(n)}</button><div><div>${esc(d)}</div><div class="pp-need">${esc(need)}</div></div></div>`).join('')}</div>`;
  }

  // The ticket is still a SAMPLE that saves nothing — there is no ticket, checklist or discipline
  // table in the schema at all. What has gone is every invented figure it used to show: a tape
  // state, and two chips claiming headroom against a ceiling that does not exist.
  function ticket() {
    const b = servedBuckets();
    return `<form class="pp-ticket" onsubmit="return false"><h4>Pre-trade ticket <span class="pp-dim">— a sample of a planned form (X8)</span></h4>
      <div class="pp-sample" role="note"><b>This is a sample form. It saves nothing, and no position you type here is recorded.</b>
        To add a real position, close this panel and use <b>+ add</b> on the Book tile.</div>
      <label>Trade direction<select><option>bearish</option><option>bullish</option><option>neutral</option></select></label>
      <label>Bucket<select>${b.length ? b.map((n) => `<option>${esc(n)}${BUCKET_NOTE[n] ? ' — ' + esc(BUCKET_NOTE[n]) : ''}</option>`).join('') : '<option>no bucket served yet</option>'}</select></label>
      <label>Ticker / structure<input placeholder="e.g. IWM put debit spread 215/210"></label>
      <label>Max loss<input placeholder="$120"></label>
      <label>Stop written<select><option>broker order</option><option>daily-close</option><option>none — say why</option></select></label>
      <label>Invalidation<input placeholder="what makes this wrong"></label>
      <label>Time stop<input placeholder="date or DTE"></label>
      <div class="pp-need">Nothing on this form can be checked against a sleeve ceiling or a cash floor, because neither is recorded anywhere. A ticket will save onto the position row once the capture path exists (BUILD gap 3).</div>
      <button type="button" class="pp-btn primary" disabled aria-disabled="true" title="This sample form saves nothing. Use + add on the Book tile to record a position.">Save ticket — sample, saves nothing</button></form>`;
  }

  function history() {
    const h = BK.hist;
    if (h.status !== 'ok') return `<div class="pp-history"><h4>History</h4>${state(h, 'Reading your closed trades…', 'your closed trades', 'hist')}</div>`;
    const stat = (k) => (h.stats || []).find((t) => t.key === k) || null;
    const np = stat('net_profit'), wr = stat('win_rate'), er = stat('expected_return');
    const cov = (t) => {
      if (!t || !t.coverage) return '';
      const c = t.coverage, ex = c.excluded || {};
      const out = (ex.basis_incomplete || 0) + (ex.return_below_neg100pct || 0) + (ex.no_realized_pnl || 0);
      return chip(out ? 'reported' : 'verified', `n=${c.counted} of ${c.total}`,
        out ? `${out} counted in the census and never averaged in: ${ex.basis_incomplete || 0} basis incomplete, ${ex.return_below_neg100pct || 0} return past −100% of basis, ${ex.no_realized_pnl || 0} with no realized P&L. Predicate: ${c.predicate}` : `Predicate: ${c.predicate}`);
    };
    const figures = h.stats
      ? `<div class="pp-hstats">
          <span>Realized <b class="${tone(np && np.value)}">${np ? usd(np.value, true) : '—'}</b> ${cov(np)}</span>
          <span>Win rate <b>${wr ? pct(wr.value) : '—'}</b> ${cov(wr)}</span>
          <span>Per trade <b>${er ? pct(er.value) : '—'}</b> ${er ? chip(er.n === (wr && wr.n) ? 'verified' : 'reported', `n=${er.n}`, 'A trade whose cost basis the book never recorded has a P&L but no return, which is why this count can be lower than the win rate’s.') : ''}</span>
        </div>
        <div class="pp-dim">Those three are the hub’s own census over ${h.range ? esc(h.range.key === 'all' ? 'the whole book' : h.range.key) : 'its own window'}${h.range && h.range.from ? ' (' + esc(h.range.from) + ' to ' + esc(h.range.to) + ')' : ''}, not a sum of the rows below.</div>`
      : `<div class="pp-note pp-warn">The hub’s census could not be read, so no total is shown. The rows below are the most recent closes, not a result.</div>`;
    const rows = h.rows.map((r) => `<tr class="${r.flag ? 'pp-flagged' : ''}"><td>#${r.id}</td>
      <td><b>${esc(r.ticker)}</b> <span class="pp-dim">${esc(r.structure)}</span></td>
      <td>${esc(r.closed || '—')}${r.status === 'EXPIRED' ? ' <span class="pp-dim">expired</span>' : ''}</td>
      <td class="pp-num">${r.realized == null ? '<span class="pp-amber">none recorded</span>' : `<span class="${tone(r.realized)}">${usd(r.realized, true)}</span>`}</td>
      <td>${esc(r.why || '—')}${r.flag ? ' ' + chip('reported', r.flag, 'Counted in the census and never averaged into a result.') : ''}</td>
      <td>${prov(r.prov)}</td></tr>`).join('');
    return `<div class="pp-history"><h4>History <span class="pp-dim">closed &amp; expired, newest first</span></h4>
      ${figures}
      <table class="pp-table"><thead><tr><th>#</th><th>Position</th><th>Closed</th><th class="pp-num">Realized</th><th>Why</th><th>Provenance</th></tr></thead><tbody>${rows}</tbody></table>
      <div class="pp-dim">Showing the ${h.rows.length} most recent of ${h.total} closed and expired positions. Positions recorded twice (status DUPLICATE_OF) are not read here at all.</div></div>`;
  }

  // What this panel still cannot show, measured rather than remembered (R-IV.691(c)).
  const GAPS = [
    'stop, invalidation, time stop and tags: the columns exist with a constraint, and nothing can write to them yet (BUILD gap 3). 2 of 28 open rows carry a stop type.',
    'sleeve ceiling and cash floor: no table anywhere, so no gauge is drawn and no headroom is claimed.',
    'roll chain: nothing in the schema records that one position followed another, so no chain is shown.',
    'structured evidence: notes are prose. The evidence here is the lots, which is where the broker references are.',
    'pre-trade ticket: no ticket, checklist or discipline table exists.',
    'open_quantity on this feed: served on /summary and on a single position, not on the list this panel reads (BUILD, R-IV.696(c)). Until it is, sizes read unknown rather than falling back to the opening quantity.',
  ];
  function missing() {
    return `<details class="pp-missing"><summary>What this panel still cannot show (${GAPS.length})</summary><ul>${GAPS.map((m) => `<li>${esc(m)}</li>`).join('')}</ul>
      <div class="pp-dim">Live here: the open book, marks with their status, lot-derived P&amp;L and max loss, provenance, lots, legs, the closed history with the hub’s census, and cash.</div></details>`;
  }

  // R-IV.1382: the provenance rung as [state, label, why] -- the row's 7px dot is the SAME
  // ::before that .pp-chip draws, so it takes the chip's state and the chip's words.
  const provInfo = (p) => PROV[p] || ['reported', String(p || ''), ''];
  return { ladder, buckets, esc, usd, pct, prov, chip, tone, state, acctLabel, qtyCell, markCell, pnlCell, sleeveLine, stopLine, bookTable, bookRow, bookHead, detail, actions, ticket, history, missing, notCaptured,
    markAge, ageInfo, provInfo, when, BUCKET_NOTE, GAP_COUNT: () => GAPS.length };
})();

  // ── Panel ────────────────────────────────────────────────────────────────
  const mq = window.matchMedia('(max-width: 820px)');
  // R-IV.1382(g): the redesigned panel is the DEFAULT. `?pos=v1` restores today's panel UNTIL
  // 2026-11-06 -- REMOVE THE ROLLBACK ON OR AFTER THAT DATE, with the v1 builders it keeps alive
  // (head, desktop, phone, summaryCard, card, the ticket), unless Nick says otherwise.
  const POS_V1 = (() => {
    try { return new URLSearchParams(location.search).get('pos') === 'v1'; } catch (_) { return false; }
  })();
  const st = { cb: { status: 'idle', accounts: {}, scope: [], names: {}, error: null }, cash: null, open: false, id: null, tab: 'Detail', mtab: 'Book', card: null, actions: false, opener: null };
  let backdrop = null, panel = null;
  const TABS = ['Detail', 'Actions', 'New', 'History'];
  const MTABS = ['Book', 'New', 'History'];
  const byId = (id) => BK.open.rows.find((p) => p.id === Number(id)) || null;
  // R-IV.1382(d)11: #positions, #positions/<id>, #positions/closed and #positions/cash. The old
  // addresses keep working: /detail and /actions open the picked row, /history opens CLOSED, and
  // /new opens the plain list (the sample ticket is gone from the panel).
  const hashFor = () => (!POS_V1
    ? '#positions' + (st.id ? '/' + st.id : pq.view === 'closed' ? '/closed' : pq.view === 'cash' ? '/cash' : '')
    : '#positions' + (st.id ? '/' + st.id : '') + (st.id && st.tab !== 'Detail' ? '/' + st.tab.toLowerCase() : ''));
  function readHash() {
    if (!POS_V1) {
      const q = /^#positions(?:\/(\d+))?(?:\/(detail|actions|new|history|closed|cash))?$/.exec(location.hash || '');
      if (!q) return null;
      const tail = q[2] || '';
      const view = tail === 'closed' || tail === 'history' ? 'closed' : tail === 'cash' ? 'cash' : 'open';
      const qid = q[1] ? Number(q[1]) : null;
      return { id: Number.isFinite(qid) && view === 'open' ? qid : null, tab: 'Detail', view };
    }
    const m = /^#positions(?:\/(\d+))?(?:\/(detail|actions|new|history))?$/.exec(location.hash || '');
    if (!m) return null;
    const id = m[1] ? Number(m[1]) : null;
    const tab = m[2] ? m[2][0].toUpperCase() + m[2].slice(1) : 'Detail';
    return { id: Number.isFinite(id) ? id : null, tab };
  }
  function setHash(replace) {
    const h = hashFor(), url = location.pathname + location.search + h;
    if (location.hash === h) return;
    history[replace ? 'replaceState' : 'pushState'](null, '', url);
  }
  // R-IV.527 #2: how far the Book tile must slide to clear the panel, measured from its real rectangle
  // (offsets, so an in-flight transition cannot skew it). None if it is already clear: tiles move and
  // the layout is saved, so the right third is not a safe assumption.
  function liftBook() {
    const root = document.documentElement;
    const tile = document.querySelector('.grid-stack-item[gs-id="book"]');
    if (!tile || !st.open || mq.matches || !panel) { root.style.removeProperty('--pp-shift'); return; }
    const parent = tile.offsetParent ? tile.offsetParent.getBoundingClientRect().left : 0;
    const left = parent + tile.offsetLeft, right = left + tile.offsetWidth;
    const panelLeft = document.documentElement.clientWidth - panel.offsetWidth;
    const need = right - (panelLeft - 14);
    const shift = Math.max(0, Math.min(need, left));
    root.style.setProperty('--pp-shift', String(Math.round(shift)));
  }
  // ── Cash actions (R-IV.550) — LIVE ──────────────────────────────────────────
  // These two forms write real money through BUILD's routes (relay f689efb70dbce557da6d):
  //   POST /api/portfolio/cash-entry     deposit / withdrawal / other, idempotent on the form's key
  //   POST /api/portfolio/cash-reanchor  "set cash to my broker's figure"; returns the difference
  //   GET  /api/portfolio/cash-balance   the ledger's derived balance (the stored figure is retired, R-IV.560)
  // Rules kept here: NO arithmetic on the page (every figure shown is the server's), NO write to
  // account_balances (neither route touches it), the CSRF header on every mutation, every refusal's
  // `detail` shown as sent, and one confirmation. The rest of the panel is still mock.
  const money2 = (v) => (v < 0 ? '−' : '') + '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const signed2 = (v) => (v === 0 ? '$0.00 (no difference)' : (v < 0 ? '−' : '+') + '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  const todayMT = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'America/Denver' }).format(new Date());
  const newKey = () => (window.crypto && crypto.randomUUID ? crypto.randomUUID() : 'k-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10));
  const CASH_AMOUNT = /^\d+(\.\d{1,2})?$/;                    // typed positive, cents at most; the sign comes from the control
  const cleanAmt = (s) => String(s == null ? '' : s).replace(/[$,\s]/g, '');
  const cashApi = () => (window.__v2 && window.__v2.apiFetch) || window.fetch.bind(window);

  // What the hub says each account's cash is. `derivable:false` is not an error and not zero.
  async function loadCash() {
    if (st.cb.status === 'loading') return;
    st.cb.status = 'loading'; st.cb.error = null; if (st.open) render();
    try {
      const api = cashApi();
      const [rc, rb] = await Promise.all([api('/api/portfolio/cash-balance', { credentials: 'same-origin' }), api('/api/portfolio/balances', { credentials: 'same-origin' })]);
      if (!rc.ok) throw new Error(rc.status === 401 ? 'sign in to see the hub\'s cash' : 'cash: HTTP ' + rc.status);
      if (!rb.ok) throw new Error(rb.status === 401 ? 'sign in to see your accounts' : 'accounts: HTTP ' + rb.status);
      const d = await rc.json(), bal = await rb.json();
      st.cb.accounts = (d && d.accounts) || {};
      const rows = Array.isArray(bal) ? bal : [];
      // R-IV.1382(d)2: the whole balance rows, so the account strip can hand each one to the BOOK
      // tile's own floor rule (window.__v2.balanceHtml) rather than re-deciding it here.
      st.cb.balances = rows;
      st.cb.scope = rows.filter((a) => a && a.in_scope === true).map((a) => a.account_name);
      // R-IV.704(b): the NAME comes from the balances row, joined on `account_name`. /cash-balance
      // is keyed by the name and carries no label, so the join is what names a cash card — and it
      // is the only source that can name an account with CASH BUT NO OPEN POSITIONS.
      st.cb.names = {};
      rows.forEach((a) => { if (a && a.account_name && a.account_display) st.cb.names[a.account_name] = a.account_display; });
      st.cb.status = 'ok';
    } catch (e) { st.cb.status = 'error'; st.cb.error = String(e && e.message || e); }
    if (st.open) render();
  }
  function refusal(status, body, err) {
    if (err) return { text: 'Could not reach the hub' + (err.name === 'AbortError' ? ' (timed out)' : '') + '. The entry may or may not have been recorded. Press Confirm again to retry: the same key means it cannot be booked twice.', retry: true };
    let d = body && body.detail;
    if (Array.isArray(d)) d = d.map((x) => (x && x.msg) || JSON.stringify(x)).join('; ');
    if (status === 401) return { text: 'Your session has expired. Sign in, then press Confirm again.', retry: true };
    if (status >= 500) return { text: 'The hub had an error (HTTP ' + status + ')' + (d ? ': ' + d : '') + '. The entry may or may not have been recorded. Press Confirm again to retry: the same key means it cannot be booked twice.', retry: true };
    return { text: d ? String(d) : 'The hub refused this (HTTP ' + status + ').', retry: false };
  }
  async function postCash(path, payload) {
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 20000);
    try {
      const r = await cashApi()(path, { method: 'POST', credentials: 'same-origin', signal: ctl.signal,
        headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, body: JSON.stringify(payload) });
      let body = null; try { body = await r.json(); } catch (_) {}
      return { ok: r.ok, status: r.status, body };
    } catch (err) { return { ok: false, status: 0, body: null, err }; } finally { clearTimeout(timer); }
  }
  // `o.noAcct` (R-IV.1382(d)8): the form opens UNDER its own account's row, so the account picker
  // would ask a question the placement already answered. Everything else -- the steps, the CSRF
  // header, the one confirmation, the key and every word -- is unchanged (R-IV.550).
  function cashPanel(s, o) {
    const k = st.cash;
    if (!k || k.acct !== s.account) return '';
    const v = k.v, accts = st.cb.scope.map((n) => `<option value="${X.esc(n)}"${n === k.acct ? ' selected' : ''}>${X.esc(acctName(n))}</option>`).join('');
    const flow = k.kind === 'flow';
    const head = `<h4>${flow ? 'Add deposit / withdrawal' : "Set cash to my broker's figure"} ${X.chip('verified', 'live', 'This writes to the hub')}</h4>`;
    if (k.step === 'result') return `<div class="pp-ticket pp-cashform" data-cash-form><div>${head}</div>${k.resultHtml}<button type="button" class="pp-btn" data-cash-done="1">Done</button></div>`;
    if (k.step === 'confirm') {
      const a = cleanAmt(v.amount), signedAmt = flow ? money2(Number(a)) : money2(Number(a));
      const direction = v.type === 'withdrawal' || (v.type === 'other' && v.dir === 'out') ? 'out' : 'in';
      const kindWord = v.type === 'other' ? 'Other movement' : v.type === 'withdrawal' ? 'Withdraw' : 'Deposit';
      const cb = st.cb.accounts[k.acct], noBal = !(cb && cb.derived && cb.derived.derivable);
      const q = flow
        ? `${kindWord} ${signedAmt} ${direction === 'out' ? 'out of' : 'into'} ${X.esc(acctName(k.acct))}, dated ${X.esc(v.date)}${v.note ? ` (“${X.esc(v.note)}”)` : ''}?`
        : `Set ${X.esc(acctName(k.acct))} cash to ${signedAmt} as of now?${noBal ? ' The hub has no balance for this account, so this becomes its first anchor: there will be nothing to compare against.' : ' The hub will show what it had and the difference.'}`;
      return `<div class="pp-ticket pp-cashform" data-cash-form><div>${head}</div><div class="pp-cash-q">${q}<div class="pp-dim">This writes money to the hub. One confirmation.</div></div>
        ${k.err ? `<div class="pp-cash-err" role="alert">${X.esc(k.err)}</div>` : ''}
        <div class="pp-cash-btns"><button type="button" class="pp-btn primary" data-cash-confirm="1"${k.busy ? ' disabled aria-busy="true"' : ''}>${k.busy ? 'Recording…' : (k.err ? 'Confirm again' : 'Confirm and record')}</button><button type="button" class="pp-btn" data-cash-back="1"${k.busy ? ' disabled' : ''}>Back</button></div></div>`;
    }
    return `<div class="pp-ticket pp-cashform" data-cash-form role="group" aria-label="${flow ? 'Add deposit or withdrawal' : 'Set cash to broker figure'}"><div>${head}</div>
      ${o && o.noAcct ? '' : `<label>Account<select data-cf="acct">${accts}</select></label>`}
      ${flow ? `<label>Type<select data-cf="type"><option value="deposit"${v.type === 'deposit' ? ' selected' : ''}>Deposit</option><option value="withdrawal"${v.type === 'withdrawal' ? ' selected' : ''}>Withdrawal</option><option value="other"${v.type === 'other' ? ' selected' : ''}>Other</option></select></label>
        ${v.type === 'other' ? `<label>Direction<select data-cf="dir"><option value="in"${v.dir === 'in' ? ' selected' : ''}>Money in (+)</option><option value="out"${v.dir === 'out' ? ' selected' : ''}>Money out (−)</option></select></label>` : ''}` : ''}
      ${flow ? '' : '<div class="pp-cash-q">Enter any trades you haven\'t recorded yet first — the figure you type should already include them.</div>'}
      <label>${flow ? 'Amount ($)' : "Broker's cash figure ($)"}<input data-cf="amount" inputmode="decimal" autocomplete="off" value="${X.esc(v.amount)}" placeholder="0.00"></label>
      ${flow ? `<label>Date the money moved<input data-cf="date" type="date" value="${X.esc(v.date)}"></label>` : ''}
      <label>Note<input data-cf="note" value="${X.esc(v.note)}" placeholder="optional"></label>
      ${k.err ? `<div class="pp-cash-err" role="alert">${X.esc(k.err)}</div>` : ''}
      <div class="pp-cash-btns"><button type="button" class="pp-btn primary" data-cash-review="1">Continue</button><button type="button" class="pp-btn" data-cash-cancel="1">Cancel</button></div></div>`;
  }
  // R-IV.560: ONE card per account. A plain name, one large live figure (Cash) with one small line
  // saying where it came from, a movement line only when there has been movement since, and the two
  // actions as small text buttons. Every figure is the server's; nothing here is invented. There is
  // deliberately no stored figure and no "difference" on the card: a difference appears only as the
  // result of "Set cash".
  const acctName = (n) => {
    const key = String(n || '');
    // 1. the balances row's own `account_display` (R-IV.704(b)) — the right source for a cash card,
    //    and the only one that can name an account with no open positions.
    if (st.cb.names && st.cb.names[key]) return st.cb.names[key];
    // 2. the same name as served on a position, so the two cards cannot disagree.
    const served = BK.open.rows.find((p) => p.account === key && p.acct);
    if (served) return served.acct;
    // 3. last resort: derived from the key. A guess, so it is never dressed up as a served name.
    return key.toLowerCase().split('_').filter(Boolean).map((w) => w[0].toUpperCase() + w.slice(1)).join(' ');
  };
  const TYPE_WORD = { TRADE_DEBIT: 'trades', TRADE_CREDIT: 'trades', TRANSFER_IN: 'deposits', TRANSFER_OUT: 'withdrawals', DIVIDEND: 'dividends', INTEREST: 'interest', FEE: 'fees', ADJUSTMENT: 'adjustments', OTHER: 'other movements' };
  const whenMT = (iso) => { const t = Date.parse(iso); return Number.isFinite(t) ? new Intl.DateTimeFormat('en-US', { timeZone: 'America/Denver', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(new Date(t)) + ' MT' : null; };
  const dayLabel = (ymd) => { const t = Date.parse(String(ymd || '') + 'T00:00:00Z'); return Number.isFinite(t) ? new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(t)) : null; };
  // Where the figure came from. R-IV.574(c): the read now SAYS — `derived.anchor.kind` is
  // `broker_figure` or `statement` (R-IV.566(d)) — so the line no longer infers it from whether
  // this browser happened to set the figure, and the session-scoped guess is gone.
  //
  // `as_of_is_instant` decides the precision, not the kind: an anchor written before that column
  // existed carries only a date, and no time is invented for it. A null kind means nobody wrote
  // down where the figure came from, so the card says NOTHING about the source rather than
  // choosing one — and a kind this page does not recognise is treated the same way.
  const ANCHOR_WORDS = { broker_figure: 'set from your broker figure', statement: 'from your statement' };
  function sourceLine(d) {
    const a = d && d.anchor;
    const what = a && ANCHOR_WORDS[a.kind];
    if (!what) return '';
    const when = a.as_of_is_instant ? whenMT(a.as_of) : dayLabel(String(a.as_of || '').slice(0, 10));
    return when ? what + ' · ' + when : what;
  }
  // The movement since the anchor, as words. ONE builder for the card's line (moveLine) and for
  // R-IV.1382's CASH row, which joins it onto the source line.
  function moveParts(d) {
    if (d.movement_since_opening == null || d.movement_since_opening === 0) return null;
    const words = []; Object.keys(d.by_type || {}).forEach((t) => { const w = TYPE_WORD[t] || String(t).toLowerCase(); if (words.indexOf(w) < 0) words.push(w); });
    const detail = Object.keys(d.by_type || {}).map((t) => (TYPE_WORD[t] || t) + ' ' + money2(d.by_type[t])).join(', ');
    const sign = d.movement_since_opening > 0 ? 'pp-up' : 'pp-down';
    const text = `${d.movement_since_opening > 0 ? '+' : ''}${money2(d.movement_since_opening)}${words.length ? ' from ' + X.esc(words.join(', ')) : ''} since`;
    return { sign, detail, text };
  }
  function moveLine(d) {
    const m = moveParts(d);
    return m ? `<div class="pp-acct-mv ${m.sign}" title="${X.esc(m.detail)}">${m.text}</div>` : '';
  }
  function cashCard(name) {
    if (!name) return '';
    const cb = st.cb, k = st.cash, mine = k && k.acct === name, off = mine && k.busy ? ' disabled' : '';
    let body;
    if (cb.status === 'loading' || cb.status === 'idle') body = '<div class="pp-acct-fig pp-dim">…</div>';
    else if (cb.status === 'error') body = `<div class="pp-acct-nofig">Cash unavailable</div><div class="pp-acct-src">${X.esc(cb.error)} <button type="button" class="pp-tbtn" data-cash-reload="1">Retry</button></div>`;
    else {
      const a = cb.accounts[name], d = (a && a.derived) || {};
      if (!a) body = '<div class="pp-acct-nofig">No record</div><div class="pp-acct-src">The hub returned nothing for this account.</div>';
      // No source line at all when the anchor does not say where the figure came from: an empty
      // line would still be a line, and this card's job is to stop short of a claim nobody wrote.
      else if (d.derivable) { const src = sourceLine(d); body = `<div class="pp-acct-fig">${money2(d.balance)}</div>${src ? `<div class="pp-acct-src">${X.esc(src)}</div>` : ''}${moveLine(d)}`; }
      else body = `<div class="pp-acct-nofig">No balance yet</div><div class="pp-acct-src" title="${X.esc(d.reason || '')}">Nothing has told the hub where this account started. Use “Set cash to my broker's figure” to give it a starting point.</div>`;
    }
    return `<div class="pp-acct" data-acct-card="${X.esc(name)}"><div class="pp-acct-name">${X.esc(acctName(name))}</div><div class="pp-k">Cash</div>${body}
      <div class="pp-acct-actions"><button type="button" class="pp-tbtn" data-cash-open="flow" data-acct="${X.esc(name)}"${off}>Deposit / withdrawal</button><button type="button" class="pp-tbtn" data-cash-open="set" data-acct="${X.esc(name)}"${off}>Set cash to my broker's figure</button></div>${cashPanel({ account: name })}</div>`;
  }
  function cashCards() {
    const cb = st.cb;
    if (cb.scope.length) return cb.scope.map(cashCard).join('');
    if (cb.status === 'error') return '<div class="pp-acct"><div class="pp-acct-nofig">Cash unavailable</div><div class="pp-acct-src">' + X.esc(cb.error || '') + ' <button type="button" class="pp-tbtn" data-cash-reload="1">Retry</button></div></div>';
    return cb.status === 'ok' ? '<div class="pp-acct"><div class="pp-acct-nofig">No accounts</div></div>' : '<div class="pp-acct"><div class="pp-acct-fig pp-dim">…</div></div>';
  }
  function cashInput(e) {
    const f = e.target.closest && e.target.closest('[data-cf]');
    if (!f || !st.cash || st.cash.busy) return;
    const name = f.dataset.cf;
    st.cash.v[name] = f.value;
    if (name === 'acct') { st.cash.acct = f.value; st.cash.focus = 'acct'; render(); }
    else if (name === 'type') { st.cash.focus = 'type'; render(); }
  }
  // The result of a successful call, in words. Server figures only.
  function entryResult(k, r) {
    const b = r.body;
    if (b.status === 'already_recorded' && b.conflict) {
      const rows = Object.keys(b.conflict).map((f) => { const c = b.conflict[f] || {}; return `<li>${X.esc(f)}: recorded ${X.esc(c.recorded)}, this press sent ${X.esc(c.sent)}</li>`; }).join('');
      return `<div class="pp-cash-res pp-cash-warn" role="alert"><b>Not booked: this key already recorded a different movement.</b><ul>${rows}</ul>${X.esc(b.conflict_note || '')}<div class="pp-dim">The first entry stands and nothing was changed.</div></div><button type="button" class="pp-btn" data-cash-newkey="1">Book this one as a new movement</button>`;
    }
    const what = b.status === 'recorded' ? 'Recorded' : 'Already recorded: the same entry, nothing was booked twice';
    return `<div class="pp-cash-res" role="status"><b>${what}.</b> ${X.esc(acctName(b.account_name))} ${X.esc(String(b.kind || '').toLowerCase())} of ${money2(b.amount)} dated ${X.esc(b.event_date)}.</div>`;
  }
  function reanchorResult(k, r, sentAmt) {
    const b = r.body;
    if (b.status === 'already_reanchored') {
      const changed = k.attempts.length > 1 && k.attempts.some((x) => x !== sentAmt);
      return `<div class="pp-cash-res pp-cash-warn" role="status"><b>Already recorded under this entry's key: nothing was written this time.</b>${changed ? ` <b>You sent a different figure than an earlier press of this same entry, so the recorded figure may not be ${money2(sentAmt)}.</b>` : ''}<div class="pp-dim">A repeat shows no difference: the hub reports the figure it holds now, not the gap the first press revealed.</div></div>${changed ? '<button type="button" class="pp-btn" data-cash-newkey="1">Set it as a new entry</button>' : ''}`;
    }
    const line = b.derived_before == null
      ? `First balance: nothing to compare. The hub had no balance to compare with; you entered ${money2(b.entered)}.`
      : `Hub had ${money2(b.derived_before)}; you entered ${money2(b.entered)}; difference ${signed2(b.difference)}.`;
    return `<div class="pp-cash-res" role="status"><b>${line}</b>${b.difference_note ? `<div class="pp-dim">${X.esc(b.difference_note)}</div>` : ''}</div>`;
  }
  async function cashSubmit(k) {
    const flow = k.kind === 'flow', a = cleanAmt(k.v.amount);
    let path, payload;
    if (flow) {
      const neg = k.v.type === 'withdrawal' || (k.v.type === 'other' && k.v.dir === 'out');
      path = '/api/portfolio/cash-entry';
      payload = { account_name: k.acct, kind: k.v.type.toUpperCase(), amount: neg ? -Number(a) : Number(a), event_date: k.v.date, idempotency_key: k.key, note: k.v.note || null };
    } else {
      path = '/api/portfolio/cash-reanchor';
      payload = { account_name: k.acct, cash: Number(a), as_of: new Date().toISOString(), idempotency_key: k.key, note: k.v.note || null };
    }
    k.attempts.push(a);
    const r = await postCash(path, payload);
    k.busy = false;
    if (r.ok && r.body && (r.body.status || '').indexOf('already_') !== 0 && r.body.status !== 'recorded' && r.body.status !== 'reanchored') { k.err = 'The hub answered with an unexpected status (' + r.body.status + '); check the ledger before repeating.'; render(); return; }
    if (!r.ok) { const f = refusal(r.status, r.body, r.err); k.err = f.text; k.focus = null; render(); return; }
    if (r.body.derived) st.cb.accounts[k.acct] = { derived: r.body.derived, flow: r.body.flow, event_count: r.body.event_count };
    k.resultHtml = flow ? entryResult(k, r) : reanchorResult(k, r, a);
    k.step = 'result'; k.err = null; render();
  }
  function cashClick(t) {
    if (t.closest('[data-cash-reload]')) { loadCash(); return true; }
    const open = t.closest('[data-cash-open]');
    if (open) { if (st.cash && st.cash.busy) return true; st.cash = { acct: open.dataset.acct, kind: open.dataset.cashOpen, step: 'form', err: null, busy: false, focus: 'amount', key: newKey(), attempts: [], resultHtml: '', v: { type: 'deposit', dir: 'in', amount: '', date: todayMT(), note: '' } }; render(); return true; }
    if (!st.cash) return false;
    const k = st.cash;
    if (t.closest('[data-cash-newkey]')) { k.key = newKey(); k.attempts = []; k.step = 'confirm'; k.err = null; render(); return true; }
    if (t.closest('[data-cash-cancel],[data-cash-done]')) { if (!k.busy) { st.cash = null; render(); } return true; }
    if (t.closest('[data-cash-back]')) { if (!k.busy) { k.step = 'form'; k.err = null; k.focus = 'amount'; render(); } return true; }
    if (t.closest('[data-cash-review]')) {
      const a = cleanAmt(k.v.amount), flow = k.kind === 'flow', cb = st.cb.accounts[k.acct];
      const derivable = !!(cb && cb.derived && cb.derived.derivable);
      if (a === '') k.err = 'Enter an amount.';
      else if (!CASH_AMOUNT.test(a)) k.err = 'Enter a plain amount in dollars and cents, like 88.15. The direction comes from the Type, not a minus sign.';
      else if (flow && Number(a) === 0) k.err = 'The amount must be above zero.';
      else if (flow && !/^\d{4}-\d{2}-\d{2}$/.test(k.v.date || '')) k.err = 'Pick the date the money moved.';
      else if (flow && k.v.date > todayMT()) k.err = 'The date cannot be in the future.';
      else if (flow && derivable && (k.v.type === 'withdrawal' || (k.v.type === 'other' && k.v.dir === 'out')) && Number(a) > cb.derived.balance) k.err = 'That is more than the ' + money2(cb.derived.balance) + ' the hub derives for this account.';
      else { k.err = null; k.step = 'confirm'; }
      k.focus = k.err ? 'amount' : null; render(); return true;
    }
    if (t.closest('[data-cash-confirm]')) {
      if (k.busy) return true;                       // a second press is ignored, not queued
      k.busy = true; k.err = null; render();
      cashSubmit(k);
      return true;
    }
    return false;
  }
  function build() {
    if (panel) return;
    backdrop = document.createElement('div'); backdrop.className = 'pp-backdrop';
    panel = document.createElement('aside'); panel.className = 'pp-panel';
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true'); panel.setAttribute('aria-label', 'Positions');
    document.body.appendChild(backdrop); document.body.appendChild(panel);
    backdrop.addEventListener('click', close);
    panel.addEventListener('click', onPanelClick);
    panel.addEventListener('input', cashInput);
    panel.addEventListener('change', cashInput);
    panel.addEventListener('submit', (e) => e.preventDefault());
    // Escape closes the panel -- but NOT while one of the Book's forms is open over it. Close and
    // Add now open FROM the panel (R-IV.1382(d)6); without this, Escape took the panel away from
    // underneath an open form.
    //
    // CAPTURE phase, deliberately. The page-wide Escape handler (registered at boot, bubble phase)
    // closes the form FIRST, so a bubble-phase check here saw no open form and closed the panel
    // too -- one keypress, two layers. Capturing reads the form's state before anything changes
    // it. The chart's own capture handler is registered earlier, so it still runs first and still
    // stops the event when it closes a chart.
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && st.open && !document.querySelector('.pos-modal.open')) close(); }, true);
    mq.addEventListener('change', () => { if (st.open) { render(); liftBook(); } });
    if (!POS_V1) {
      // R-IV.1382: the scoping class for its CSS, which also lifts the Close/Add forms above
      // the panel on a phone (both sat at z-index 95, and the panel came later in the page).
      panel.classList.add('pq');
      // Two columns <-> one as the PANEL crosses 900px (d)9.
      window.addEventListener('resize', () => { if (st.open && pqWide() !== pq.lastWide) render(); });
      // (d)6 "After a close or an add succeeds, reload the book": the Book module announces each
      // re-read (`v2:book`). NOT while a cash form is open or a field has focus -- a re-render
      // under someone typing would take the field away from them.
      window.addEventListener('v2:book', () => {
        if (!st.open || st.cash) return;
        const a = document.activeElement;
        if (a && panel.contains(a) && /^(INPUT|SELECT|TEXTAREA)$/.test(a.tagName)) return;
        loadOpen(); loadCash();
      });
    }
  }
  function head() {
    // R-IV.697: the banner names what is live and what has no source, because "sample data" was
    // about to become false for most of this panel and a stale disclaimer is its own dishonesty.
    const age = BK.open.age;
    const asOf = BK.open.status === 'ok'
      ? `read ${age == null ? 'just now' : age < 60 ? Math.round(age) + 's ago' : Math.round(age / 60) + 'm ago'}`
      : BK.open.status === 'error' ? 'not read' : 'reading…';
    return `<div class="pp-head"><h2>Positions</h2>${X.chip(BK.open.status === 'error' ? 'unknown' : 'verified', 'live · ' + asOf, 'Your book, marks, lots, legs, the closed history and cash all come from the hub.')}<button type="button" class="pp-x" aria-label="Close positions panel">✕</button></div>
      <div class="pp-banner">Live from the hub: your open book, marks with their status, lot-derived P&amp;L, provenance, lots, legs, the closed history and cash. Stops, invalidations, time stops and tags read “not captured yet”: the columns exist and nothing can write to them. Sleeve ceilings and roll chains have no source, so nothing is drawn for them.</div>
`;
  }
  function legend() { return `<details class="pp-legend"><summary>Legend: provenance ladder and the buckets your rows use</summary>${X.ladder()}${X.buckets()}</details>`; }
  // Desktop arrangement (R-IV.520). Column 1, at the screen's center: the chosen position's
  // summary card, or the book list until one is chosen. Column 2: the work pane. Two columns
  // need a viewport of 1400px or more (CSS); narrower, they stack inside the same 50% panel.
  function summaryCard(p) {
    const cell = (k, v) => `<div class="pp-sc"><span class="pp-k">${k}</span><span class="pp-sv">${v}</span></div>`;
    // The "Rule now" line is GONE. It was a computed discipline verdict with no source, and
    // S-6 SG-0 descoped the endpoint that would have computed one. An absence is shown as an
    // absence (the stop line below), never as a sentence telling the principal what a rule says.
    return `<div class="pp-sum pp-card">
      <div class="pp-sum-top"><span class="pp-sum-tk">${X.esc(p.ticker)}</span>${X.prov(p.prov)}</div>
      <div class="pp-sum-sub">${p.bucket ? X.esc(p.bucket) + ' · ' : ''}${X.esc(X.acctLabel(p))}</div>
      <div class="pp-sum-st">${X.esc(p.structure)}${p.strikes ? ' ' + X.esc(p.strikes) : ''}${p.expiry ? ' · exp ' + X.esc(p.expiry.slice(5)) : ''}</div>
      <div class="pp-sum-grid">${cell('Open', X.qtyCell(p))}${cell('Cost', X.usd(p.cost))}${cell('Mark', X.markCell(p))}${cell('P&amp;L', X.pnlCell(p))}</div>
      <div class="pp-sum-stop">${X.stopLine(p)}</div>
      <button type="button" class="pp-btn pp-link" data-allpos="1">← All positions</button>
    </div>${st.cb.scope.indexOf(p.account) >= 0 ? cashCard(p.account) : ''}`;
  }
  function desktop() {
    const sel = byId(st.id);
    const none = '<div class="pp-dim">Pick a position in the Book strip.</div>';
    const pane = st.tab === 'Detail' ? (sel ? X.detail(sel) : none) : st.tab === 'Actions' ? (sel ? X.actions(sel) : none) : st.tab === 'New' ? X.ticket() : X.history();
    // One card per account THE HUB SERVES. The old list was hardcoded to two accounts and would
    // have hidden the third (FIDELITY_401A, 4 open positions) entirely. Names come from
    // `account_display`; a key is never printed as a name.
    const pending = !sel && st.id != null && BK.open.status !== 'ok';
    const gone = !sel && st.id != null && BK.open.status === 'ok';
    const col1 = sel ? summaryCard(sel)
      : pending ? X.state(BK.open, 'Reading your book…', 'your book', 'open')
      : gone ? `<div class="pp-note pp-warn">Position #${X.esc(st.id)} is not in your open book. It may have been closed, or the address may be old.<div><button type="button" class="pp-btn pp-link" data-allpos="1">← All positions</button></div></div>`
      : cashCards() + (BK.open.status !== 'ok' ? X.state(BK.open, 'Reading your book…', 'your book', 'open')
        : accountsOf(BK.open.rows).map((g) => `<div class="pp-card"><h3 class="pp-h"><span class="pp-name">${X.esc(X.acctLabel(g.rows[0]))}</span> <span class="pp-dim">${g.rows.length} open</span></h3>${X.sleeveLine(g)}<div class="pp-scroll">${X.bookTable(g.account)}</div></div>`).join('')
        || '<div class="pp-note">The hub reports no open positions.</div>');
    return `<div class="pp-cols"><div class="pp-col1">${col1}</div>
      <div class="pp-col2 pp-card"><div class="pp-tabs" role="tablist">${TABS.map((t) => `<button type="button" role="tab" aria-selected="${t === st.tab}" data-tab="${t}">${t === 'New' ? 'New (ticket)' : t}</button>`).join('')}</div>${pane}</div></div>${legend()}${X.missing()}`;
  }
  function card(p) {
    const on = st.card === p.id;
    return `<div class="pp-pcard" data-card="${p.id}"><header><span><b>${X.esc(p.ticker)}</b> <span class="pp-dim">${p.bucket ? X.esc(p.bucket) + ' · ' : ''}${X.esc(p.structure)}</span></span>${X.prov(p.prov)}</header>
      <div class="pp-line"><span>open ${X.qtyCell(p)} · cost ${X.usd(p.cost)}</span><span>mark ${X.markCell(p)}</span></div>
      ${on ? `<div class="pp-sheet">${X.detail(p)}<div style="margin-top:8px"><button type="button" class="pp-btn" data-toggle-actions="1">${st.actions ? 'Hide actions' : 'Actions'}</button></div>${st.actions ? X.actions(p) : ''}</div>` : ''}</div>`;
  }
  function phone() {
    const v = st.mtab === 'Book' ? cashCards() + (BK.open.status !== 'ok' ? X.state(BK.open, 'Reading your book…', 'your book', 'open')
        : accountsOf(BK.open.rows).map((g) => `<h3 class="pp-h"><span class="pp-name">${X.esc(X.acctLabel(g.rows[0]))}</span> <span class="pp-dim">${g.rows.length} open</span></h3>${X.sleeveLine(g)}` + g.rows.map(card).join('')).join('')
        || '<div class="pp-note">The hub reports no open positions.</div>')
      : st.mtab === 'New' ? `<div class="pp-card">${X.ticket()}</div>` : `<div class="pp-card">${X.history()}</div>`;
    return `<div class="pp-tabs" role="tablist">${MTABS.map((t) => `<button type="button" role="tab" aria-selected="${t === st.mtab}" data-mtab="${t}">${t === 'New' ? 'New (ticket)' : t}</button>`).join('')}</div>${v}${legend()}${X.missing()}`;
  }

  // ═══ R-IV.1382 · THE POSITIONS PANEL, REDESIGNED ════════════════════════════════════════
  //
  // Nick's approved boards (13:27 MT 2026-10-23). His complaint: the panel made "very
  // inefficient use of space" -- cash cards filled the left column and pushed the book below the
  // fold, while the right column sat empty until a row was picked. Positions first, no empty
  // column, and every button really works. Display only (#42): nothing new gates, and the kill
  // switch is untouched.
  //
  // The honesty rules carried over, each cited where it is kept below: R-IV.662(c)/668(c),
  // R-IV.1262(b)3, R-IV.719(c), R-IV.726, R-IV.697, R-IV.704(b) and R-IV.550.
  const pq = { view: 'open', acctF: null, sortK: 'days', sortD: 1, noPrice: null, info: false, glance: false,
    earn: {}, earnState: 'idle', earnSeq: -1, openSeq: 0, lastWide: null, folds: pqLoadFolds() };

  // A folded group is REMEMBERED per account, in localStorage, inside try/catch: a private window
  // or blocked storage must cost the memory, never the panel.
  function pqLoadFolds() {
    try { const v = JSON.parse(localStorage.getItem('pq-folds-v1') || '[]'); return new Set(Array.isArray(v) ? v : []); }
    catch (_) { return new Set(); }
  }
  function pqSaveFolds() { try { localStorage.setItem('pq-folds-v1', JSON.stringify([...pq.folds])); } catch (_) {} }

  // Two columns only when the PANEL is at least 900px wide (d)9 -- the panel, not the window.
  function pqWide() {
    if (mq.matches) return false;
    const w = panel ? panel.getBoundingClientRect().width : window.innerWidth * 0.5;
    return w >= 900;
  }
  const PQ_MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  // 'YYYY-MM-DD' -> 'Nov 20'. A stored date named as written; no clock is involved.
  const pqMonD = (ymd) => { const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(ymd || '')); return m ? PQ_MON[+m[2] - 1] + ' ' + (+m[3]) : ''; };
  const PQ_STRUCT = { 'put debit spread': 'Put spread', 'put credit spread': 'Put spread', 'call debit spread': 'Call spread',
    'call credit spread': 'Call spread', 'long put': 'Long put', 'long call': 'Long call', 'short put': 'Short put', 'short call': 'Short call' };
  // WHAT: the structure and strikes, then the expiry as "Mon D". Equity rows read "Shares".
  function pqWhat(p) {
    if (p.assetType === 'EQUITY' || /^(stock|equity|shares?)$/i.test(p.structure)) return 'Shares';
    const s = String(p.structure || '').toLowerCase();
    const w = PQ_STRUCT[s] || (s ? s.charAt(0).toUpperCase() + s.slice(1) : 'Position');
    return w + (p.strikes ? ' ' + p.strikes : '') + (p.expiry ? ' · ' + pqMonD(p.expiry) : '');
  }
  // MARK per unit, no $ sign; as many places as the price needs, never fewer than two.
  const pqMark = (v) => (Math.abs(v) >= 1 ? v.toFixed(2) : String(Number(v.toFixed(4)) < 0.01 ? Number(v.toFixed(4)) : v.toFixed(2)));
  const pqName = (key) => (key ? acctName(key) : 'Unattributed');
  const pqBal = (key) => (st.cb.balances || []).find((a) => a && a.account_name === key) || null;
  const pqOpenIn = (key) => BK.open.rows.filter((p) => key == null || p.account === key).length;

  // ── header (d)1 ──
  function pqAgeWords(short) {
    const age = BK.open.age;
    if (BK.open.status === 'error') return 'not read';
    if (BK.open.status !== 'ok') return 'reading…';
    if (age == null) return short ? 'now' : 'just now';
    const t = age < 60 ? Math.round(age) + 's' : Math.round(age / 60) + 'm';
    return short ? t : t + ' ago';
  }
  // Edit and Roll have no writer, so they are not drawn as buttons (d)6; they are listed here,
  // with the gaps they wait on, instead of being deleted.
  const PQ_GAPS_MORE = [
    'Edit (tags, stop, invalidation, time stop) waits on the capture path: those columns have no writer yet (BUILD gap 3). Not shown as a button until it has one.',
    'Roll (close this and open the next as one linked trade) waits on R-IV.452, and on a link field: nothing in the schema records that one position followed another. Not shown as a button until it has one.',
  ];
  // (d)1: the banner, the legend, the GAPS and the evidence note MOVE behind the ⓘ. Nothing is
  // deleted; it moves.
  function pqInfo() {
    return `<div class="pq-info" role="note">
      <p>Live from the hub: your open book, marks with their status, lot-derived P&amp;L, provenance, lots, legs, the closed history and cash. Stops, invalidations, time stops and tags read “not captured yet”: the columns exist and nothing can write to them. Sleeve ceilings and roll chains have no source, so nothing is drawn for them.</p>
      ${X.ladder()}${X.buckets()}
      <p>This row’s own <code>broker_ref</code> field is not read: it is empty on every open position, while the lots behind them are not. The evidence lives at the fill.</p>
      ${X.missing()}
      <ul class="pq-gx">${PQ_GAPS_MORE.map((g) => '<li>' + X.esc(g) + '</li>').join('')}</ul></div>`;
  }
  function pqHead() {
    const ok = BK.open.status !== 'error';
    const live = mq.matches
      ? `<span class="pq-live${ok ? '' : ' bad'}" title="live · read ${X.esc(pqAgeWords(false))}"><i aria-hidden="true"></i>${X.esc(pqAgeWords(true))}</span>`
      : X.chip(ok ? 'verified' : 'unknown', 'live · read ' + pqAgeWords(false), 'Your book, marks, lots, legs, the closed history and cash all come from the hub.');
    return `<div class="pp-head pq-head"><h2>Positions</h2>${live}<span class="pq-sp"></span>
      <button type="button" class="pq-ib" data-pq-info aria-expanded="${pq.info}" aria-label="About this panel">i</button>
      <button type="button" class="pp-x pq-x" aria-label="Close positions panel">✕</button></div>${pq.info ? pqInfo() : ''}`;
  }

  // ── account strip (d)2 ──
  // Line 2 is the BOOK tile's own floor rule, called through window.__v2 (shared, not copied).
  // Line 3's cash is the server's derived figure, to the cent, never rounded or summed here.
  // R-IV.704(b)/R-IV.697: names come from account_display and are never uppercased.
  function pqStrip() {
    const v2 = window.__v2 || {};
    const scope = st.cb.scope.length ? st.cb.scope : accountsOf(BK.open.rows).map((g) => g.account).filter(Boolean);
    const rows = scope.map(pqBal).filter(Boolean);
    const btn = (key, name, bal, l3) => `<button type="button" class="pq-acct" data-pq-acct="${X.esc(key)}" aria-pressed="${key ? pq.acctF === key : pq.acctF == null}">`
      + `<span class="pq-an">${X.esc(name)}</span><span class="pq-ab">${bal}</span>${mq.matches ? '' : `<span class="pq-a3">${l3}</span>`}</button>`;
    const floor = v2.bookTotalFloor ? v2.bookTotalFloor(rows) : false;
    const all = btn('', 'All accounts', v2.bookTotalHtml ? v2.bookTotalHtml(rows) : '—',
      (floor ? '<span class="pq-amb">floor only</span> · ' : '') + pqOpenIn(null) + ' open');
    const each = scope.map((n) => {
      const cb = st.cb.accounts[n], d = cb && cb.derived;
      const cash = d && d.derivable ? 'cash ' + money2(d.balance) : (st.cb.status === 'ok' ? 'cash —' : 'cash …');
      return btn(n, pqName(n), v2.balanceHtml ? v2.balanceHtml(pqBal(n)) : '—', X.esc(cash) + ' · ' + pqOpenIn(n) + ' open');
    }).join('');
    return `<div class="pq-strip" role="group" aria-label="Accounts">${all}${each}</div>`;
  }

  // ── tab row (d)3 ──
  function pqRows() {
    let rows = BK.open.rows;
    if (pq.acctF) rows = rows.filter((p) => p.account === pq.acctF);
    if (pq.noPrice != null) rows = rows.filter((p) => p.mark == null && (pq.noPrice === '*' || (p.account || '') === pq.noPrice));
    return rows;
  }
  function pqTabs() {
    const n = BK.open.status === 'ok' ? pqRows().length : null;
    const tab = (k, label, count) => `<button type="button" role="tab" data-pq-view="${k}" aria-selected="${pq.view === k}">${label}${count != null ? ' <span>' + count + '</span>' : ''}</button>`;
    // + ADD POSITION opens the Book module's own form (exposed, not duplicated).
    const add = mq.matches ? '<button type="button" class="pq-addp" data-pq-add aria-label="Add position">+</button>'
      : '<button type="button" class="pq-add" data-pq-add>+ Add position</button>';
    return `<div class="pq-tabs" role="tablist">${tab('open', 'Open', n)}${tab('closed', 'Closed')}${tab('cash', 'Cash')}<span class="pq-sp"></span>${add}</div>`;
  }

  // ── OPEN: one table grouped by account (d)4 ──
  // Sort: DAYS ascending by default, soonest expiry first, no-expiry rows last; ties by P&L
  // descending; within each group. A missing figure sorts LAST in both directions -- it is not
  // the smallest or the largest value, it is no value.
  const PQ_SORT = { ticker: (p) => p.ticker, what: (p) => pqWhat(p), qty: (p) => p.qty, mark: (p) => p.mark,
    age: (p) => { const a = X.markAge(p); return a ? Date.now() - Date.parse(a.iso) : null; }, pnl: (p) => p.pnl, days: (p) => p.dte };
  function pqSort(rows) {
    const f = PQ_SORT[pq.sortK] || PQ_SORT.days, d = pq.sortD;
    const tie = (a, b) => (a.pnl == null && b.pnl == null ? 0 : a.pnl == null ? 1 : b.pnl == null ? -1 : b.pnl - a.pnl);
    return rows.slice().sort((a, b) => {
      const x = f(a), y = f(b);
      if (x == null && y == null) return tie(a, b);
      if (x == null) return 1;
      if (y == null) return -1;
      const c = typeof x === 'string' ? x.localeCompare(y) : x - y;
      return (c * d) || tie(a, b);
    });
  }
  function pqDot(p) {
    const [s, l, t] = X.provInfo(p.prov);
    return `<span class="pp-chip pq-dot" data-state="${s}" title="${X.esc(l + (t ? ': ' + t : ''))}"></span>`;
  }
  function pqPnl(p, cls) {
    // P&L: the hub's unrealized_pnl. Null is "—" in --text-3 with its reason, never 0.
    if (p.pnl == null) return `<span class="pq-na ${cls || ''}" title="${X.esc(p.pnlWhy || 'the hub derived no P&L for this row')}">—</span>`;
    return `<span class="${X.tone(p.pnl)} ${cls || ''}" title="${X.esc(X.usd(p.pnl, true))}">${X.usd(Math.round(p.pnl), true)}</span>`;
  }
  function pqMarkCell(p) {
    return p.mark == null ? `<span class="pq-amb" title="${X.esc(p.markWhy || 'the hub served no mark for this position')}">no price</span>` : X.esc(pqMark(p.mark));
  }
  function pqRow(p) {
    const age = X.ageInfo(p), w = pqWhat(p);
    // QTY is open_quantity or an amber "unknown" -- it never falls back to quantity (R-IV.662(c)/668(c)).
    return `<tr class="pp-row pq-row${p.id === st.id ? ' sel' : ''}" data-pq-row data-id="${p.id}">`
      + `<td class="pq-tk">${pqDot(p)}<b>${X.esc(p.ticker)}</b></td>`
      + `<td class="pq-what" title="${X.esc(w)}">${X.esc(w)}</td>`
      + `<td class="pp-num">${X.qtyCell(p)}</td><td class="pp-num">${pqMarkCell(p)}</td>`
      + `<td class="pp-num pq-age${age.amber ? ' amb' : ''}" title="${X.esc(age.why)}">${X.esc(age.txt)}</td>`
      + `<td class="pp-num">${pqPnl(p)}</td><td class="pp-num">${p.dte == null ? '—' : X.esc(p.dte)}</td></tr>`;
  }
  function pqGroupHead(g, cols) {
    const key = g.account || '', folded = pq.folds.has(key);
    const np = g.rows.filter((p) => p.mark == null).length;
    const nopnl = g.rows.filter((p) => p.mark != null && p.pnl == null).length;
    // The group's P&L sum appears ONLY when every row in the group has one: a sum over some of
    // the rows reads as the account's figure.
    const sum = g.rows.every((p) => p.pnl != null) ? g.rows.reduce((s, p) => s + p.pnl, 0) : null;
    const flags = (np ? np + ' no price' : '') + (nopnl ? (np ? ' · ' : '') + nopnl + ' no P&amp;L' : '');
    const inner = `<span class="pq-gn">${X.esc(pqName(g.account))}</span><span class="pq-gc">${g.rows.length} open${folded ? ' · folded' : ''}</span>`
      + `<span class="pq-sp"></span>${flags ? `<span class="pq-gnp">${flags}</span>` : ''}`
      + (sum != null ? `<span class="pq-gs ${X.tone(sum)}">${X.usd(Math.round(sum), true)}</span>` : '')
      + `<span class="pq-gch" aria-hidden="true">${folded ? '›' : '⌄'}</span>`;
    const b = `<button type="button" class="pq-gbtn" data-pq-fold="${X.esc(key)}" aria-expanded="${!folded}">${inner}</button>`;
    return cols ? `<tr class="pq-grp"><td colspan="${cols}">${b}</td></tr>` : `<div class="pq-grp">${b}</div>`;
  }
  const PQ_COLS = [['ticker', 'Ticker', 0], ['what', 'What', 0], ['qty', 'Qty', 1], ['mark', 'Mark', 1], ['age', 'Age', 1], ['pnl', 'P&L', 1], ['days', 'Days', 1]];
  function pqTable() {
    if (BK.open.status !== 'ok') return X.state(BK.open, 'Reading your book…', 'your book', 'open');
    const groups = accountsOf(pqRows());
    if (!groups.length) return `<div class="pp-note">${pq.noPrice != null ? 'Every position in view has a price.' : pq.acctF ? 'The hub reports no open positions in this account.' : 'The hub reports no open positions.'}</div>`;
    const head = '<thead><tr>' + PQ_COLS.map(([k, l, n]) => {
      const on = pq.sortK === k;
      return `<th class="${n ? 'pp-num' : ''}" aria-sort="${on ? (pq.sortD > 0 ? 'ascending' : 'descending') : 'none'}">`
        + `<button type="button" class="pq-sort${on ? ' on' : ''}" data-pq-sort="${k}">${X.esc(l)}${on ? (pq.sortD > 0 ? ' ▴' : ' ▾') : ''}</button></th>`;
    }).join('') + '</tr></thead>';
    const body = groups.map((g) => pqGroupHead(g, 7) + (pq.folds.has(g.account || '') ? '' : pqSort(g.rows).map(pqRow).join(''))).join('');
    return `<table class="pq-table">${head}<tbody>${body}</tbody></table>`;
  }
  // Phone (d)10: rows of 56px on two lines instead of a table.
  function pqPhoneList() {
    if (BK.open.status !== 'ok') return X.state(BK.open, 'Reading your book…', 'your book', 'open');
    const groups = accountsOf(pqRows());
    if (!groups.length) return '<div class="pp-note">The hub reports no open positions here.</div>';
    return groups.map((g) => pqGroupHead(g, 0) + (pq.folds.has(g.account || '') ? '' : pqSort(g.rows).map((p) => {
      const age = X.ageInfo(p);
      const right2 = p.mark == null ? pqMarkCell(p)
        : `<span title="${X.esc(age.why)}" class="${age.amber ? 'pq-amb' : ''}">${X.esc(pqMark(p.mark))} · ${X.esc(age.txt)}</span>`;
      return `<button type="button" class="pq-prow${p.id === st.id ? ' sel' : ''}" data-pq-row data-id="${p.id}">`
        + `<span class="pq-l1">${pqDot(p)}<b>${X.esc(p.ticker)}</b><span class="pq-x2">×${p.qty == null ? '?' : X.esc(p.qty)}</span><span class="pq-sp"></span>${pqPnl(p)}</span>`
        + `<span class="pq-l2"><span class="pq-w">${X.esc(pqWhat(p))}${p.dte != null ? ' · ' + X.esc(p.dte) + 'd' : ''}</span><span class="pq-sp"></span>${right2}</span></button>`;
    }).join(''))).join('');
  }

  // ── AT A GLANCE (d)5 ──
  // Earnings: ONE call per panel open, to /api/chronos/next-earnings-batch -- a database read of
  // earnings_calendar, no vendor call. An ETF's date is its earliest HOLDING's, and is said so.
  function pqEarnItems() {
    const out = [], seen = new Set();
    BK.open.rows.filter((p) => p.expiry && p.assetType !== 'EQUITY').forEach((p) => {
      const T = String(p.ticker || '').toUpperCase(), en = pq.earn[T];
      if (!en || !en.date || en.date > p.expiry) return;          // only ON or BEFORE the expiry
      const k = T + '|' + p.expiry;
      if (seen.has(k)) return;
      seen.add(k);
      out.push({ T, en, exp: p.expiry, text: en.is_etf && en.component
        ? `${X.esc(en.component)}, held in ${X.esc(T)}, reports earnings before ${X.esc(T)}’s ${pqMonD(p.expiry)} expiry.`
        : `${X.esc(T)} reports earnings before its ${pqMonD(p.expiry)} expiry.` });
    });
    return out;
  }
  function pqNeeds() {
    const items = accountsOf(BK.open.rows.filter((p) => p.mark == null)).map((g) => {
      const n = g.rows.length;
      return `<li class="amb"><span>${n} ${X.esc(pqName(g.account))} position${n === 1 ? ' has' : 's have'} no price, so ${n === 1 ? 'its' : 'their'} P&amp;L is blank. `
        + `<button type="button" class="pq-tl" data-pq-noprice="${X.esc(g.account || '')}">Show ${n === 1 ? 'it' : 'them'} ›</button></span></li>`;
    });
    pqEarnItems().forEach((e) => items.push(`<li class="tl"><span>${e.text}</span></li>`));
    let tail = '';
    if (pq.earnState === 'loading') tail = '<div class="pq-t3">Checking earnings…</div>';
    else if (pq.earnState === 'error') tail = '<div class="pq-t3">Earnings could not be read, so none are listed.</div>';
    return `<div class="pq-card"><div class="pq-ct">Needs a look</div>${items.length ? `<ul class="pq-needs">${items.join('')}</ul>`
      : (pq.earnState === 'loading' ? '' : '<div class="pq-t3">Nothing needs a look.</div>')}${tail}</div>`;
  }
  function pqDayCard() {
    // The BOOK tile's figure and rules EXACTLY, from the same shared code (R-IV.1369(e)1 as amended
    // by R-IV.1381(e)2). If the tile has not read the book yet, this says so rather than guessing.
    const v2 = window.__v2 || {};
    const d = v2.bookDay ? v2.bookDay(true) : null;
    return `<div class="pq-card pq-day"><div class="pq-ct">Day P&amp;L</div>${d || '<div class="bk-why">the Book tile has not read the book yet</div>'}</div>`;
  }
  function pqExp() {
    // Positions, not legs. Days come from the served `dte`, never from this page's clock.
    const opt = BK.open.rows.filter((p) => p.expiry && p.assetType !== 'EQUITY');
    const by = new Map();
    opt.forEach((p) => by.set(p.expiry, (by.get(p.expiry) || 0) + 1));
    const ks = [...by.keys()].sort(), max = Math.max(1, ...by.values());
    const dte = (e) => { const p = opt.find((x) => x.expiry === e && x.dte != null); return p ? p.dte : null; };
    const shares = BK.open.rows.filter((p) => !p.expiry).length;
    return `<div class="pq-card"><div class="pq-ct">Expirations</div>`
      + (ks.map((e) => `<div class="pq-ex"><span>${pqMonD(e)}${dte(e) != null ? ' · ' + dte(e) + ' days' : ''}</span>`
        + `<span class="pq-eb"><i style="width:${Math.round(by.get(e) / max * 100)}%"></i></span><span class="pp-num">${by.get(e)}</span></div>`).join('')
        || '<div class="pq-t3">No option positions.</div>')
      + `<div class="pq-ex pq-ex0"><span>Shares, no expiry</span><span></span><span class="pp-num">${shares}</span></div></div>`;
  }
  function pqGlance() {
    return `<div class="pq-glance"><div class="pq-gh">At a glance</div>${pqNeeds()}${pqDayCard()}${pqExp()}`
      + '<div class="pq-t3">Click a row and this side shows that position.</div></div>';
  }
  // Narrow and phone: AT A GLANCE as one line above the list; its chevron opens the full cards.
  function pqGlanceStrip() {
    const np = BK.open.rows.filter((p) => p.mark == null).length, e = pqEarnItems()[0];
    const bits = [];
    if (np) bits.push(`<span class="amb">● ${np} ha${np === 1 ? 's' : 've'} no price</span>`);
    if (e) bits.push(`<span class="tl">● ${X.esc(e.en.is_etf && e.en.component ? e.en.component : e.T)} earnings first</span>`);
    return `<button type="button" class="pq-gstrip" data-pq-glance aria-expanded="${pq.glance}">${bits.join('') || '<span class="pq-t3">Nothing needs a look</span>'}`
      + `<span class="pq-sp"></span><span aria-hidden="true">${pq.glance ? '⌄' : '›'}</span></button>`;
  }

  // ── a picked row (d)6 ──
  // R-IV.726: a lot's fill_time is a DAY when it sits at exactly midnight UTC (taken as written)
  // and a MOMENT otherwise (converted to Mountain Time).
  function pqLotDay(iso) {
    const t = Date.parse(iso);
    if (!Number.isFinite(t)) return String(iso || '—');
    const d = new Date(t);
    const day = !d.getUTCHours() && !d.getUTCMinutes() && !d.getUTCSeconds() && !d.getUTCMilliseconds();
    return new Intl.DateTimeFormat('en-US', { timeZone: day ? 'UTC' : 'America/Denver', month: 'short', day: 'numeric' }).format(d);
  }
  const pqCap = (s) => String(s || '').replace(/^./, (c) => c.toUpperCase());
  function pqExitPlan(p) {
    if (p.stopType) return X.stopLine(p);
    const bits = [p.timeStop ? 'time stop ' + X.esc(p.timeStop) : '', p.invalidation ? X.esc(p.invalidation) : '',
      p.tags.length ? p.tags.map((t) => X.esc(t)).join(', ') : ''].filter(Boolean);
    return bits.length ? bits.join(' · ') : '<span class="pq-t2">not captured yet</span>';
  }
  function pqPicked(p, narrow) {
    const v2 = window.__v2 || {}, raw = BK.open.raw ? BK.open.raw.get(p.pid) : null;
    const s = BK.sub[p.pid] || { status: 'idle', lots: [], legs: [] };
    const age = X.ageInfo(p);
    const pct = raw && v2.pnlPct ? v2.pnlPct(raw) : null;
    const sus = raw && v2.basisSuspect ? v2.basisSuspect(raw, pct) : null;
    const back = narrow ? '← All positions' : '← At a glance';
    const theme = v2.themeOf ? v2.themeOf(p.ticker) : null;
    const en = pq.earn[String(p.ticker || '').toUpperCase()];
    const bucket = p.bucket ? X.chip('verified', p.bucket + (X.BUCKET_NOTE[p.bucket] ? ' · ' + X.BUCKET_NOTE[p.bucket] : '')) : '';
    const stat = (k, v, cls) => `<div class="pq-stat"><span class="pq-sk">${k}</span><span class="pq-sv ${cls || ''}">${v}</span></div>`;
    const pnlV = p.pnl == null ? `<span class="pq-na" title="${X.esc(p.pnlWhy || '')}">—</span>`
      : `<span class="${sus ? 'pq-sus' : X.tone(p.pnl)}" title="${X.esc(sus ? 'Basis looks wrong: ' + sus : X.usd(p.pnl, true))}">${X.usd(Math.round(p.pnl), true)}</span>`
        + (pct != null ? ` <span class="pq-pct ${sus ? 'pq-sus' : X.tone(p.pnl)}">${pct >= 0 ? '+' : '−'}${Math.abs(pct).toFixed(0)}%</span>` : '')
        + (sus ? '<span class="pq-amb"> basis suspect</span>' : '');
    // Actions call the Book module's OWN forms with the RAW row; ADD only when the Book's rule
    // allows it. Edit and Roll are not drawn (they wait on writers; listed under ⓘ).
    const eligible = raw && v2.addPosEligible ? v2.addPosEligible(raw) : false;
    const noRaw = raw ? '' : ' disabled title="the raw row is not loaded yet"';
    const acts = `<div class="pq-acts"><button type="button" class="pq-ab pq-close" data-pq-act="close"${noRaw}>Close</button>`
      + (eligible ? '<button type="button" class="pq-ab" data-pq-act="add">Add</button>' : '')
      + '<button type="button" class="pq-ab" data-pq-act="chart">Chart</button></div>';
    const warns = [p.basisIncomplete ? 'Basis under review — ' + X.esc(p.basisIncomplete) : '',
      s.agreesKnown && !s.agrees ? `The lots sum to ${X.esc(s.lotQty)} and the row stores ${X.esc(s.storedQty)}: this position’s stored quantity has drifted from its own fills.` : '',
      s.mergedInto ? 'The legs for this position are recorded on ' + X.esc(s.mergedInto) + '.' : ''].filter(Boolean)
      .map((w) => `<div class="pq-warn">${w}</div>`).join('');
    let lotsLegs;
    if (s.status !== 'ok') lotsLegs = X.state(s, 'Reading this position’s lots and legs…', 'lots and legs', p.pid);
    else {
      const refs = s.lots.filter((l) => l.broker_ref).length;
      const lots = s.lots.map((l) => {
        const pv = X.provInfo(String(l.provenance || 'UNKNOWN').toUpperCase());
        return `<div class="pq-li"><span title="${X.esc(X.when(l.fill_time))}">${X.esc(pqLotDay(l.fill_time))} · ${X.esc(l.qty)} at ${X.esc(l.price)}</span><span>${l.fees == null ? '—' : X.esc(l.fees)}</span></div>`
          + `<div class="pq-li2">${X.esc(pv[1])} · ${l.broker_ref ? X.esc(l.broker_ref) : 'no reference'}</div>`;
      }).join('') || '<div class="pq-t3">The hub holds no lots for this position.</div>';
      const legs = s.legs.map((g) => `<div class="pq-li"><span>${X.esc(pqCap(String(g.side || '').toLowerCase()))} ${X.esc(String(g.option_type || '').toLowerCase())} ${g.strike == null ? '—' : X.esc(g.strike)} · ×${g.qty == null ? '—' : X.esc(g.qty)}</span>`
        + `<span>${g.price == null ? '<span class="pq-amb">unpriced</span>' : X.esc(g.price)}</span></div>`).join('')
        || `<div class="pq-t3">${s.mergedInto ? 'Recorded on ' + X.esc(s.mergedInto) + '.' : 'The hub holds no legs for this position.'}</div>`;
      lotsLegs = `<div class="pq-sh"><span>Lots</span><span>${s.lots.length} · ${refs} with a broker reference</span></div>${lots}`
        + `<div class="pq-sh"><span>Legs</span></div>${legs}`;
    }
    return `<div class="pq-pick"><button type="button" class="pq-back" data-allpos="1">${back}</button>`
      + `<div class="pq-ptk">${X.esc(p.ticker)}</div>`
      + `<div class="pq-psub">${X.esc(pqWhat(p))} · ×${p.qty == null ? '?' : X.esc(p.qty)}</div>`
      + `<div class="pq-pchips">${X.prov(p.prov)}${X.chip('screen', pqName(p.account))}${bucket}</div>`
      + `<div class="pq-stats">${stat('Cost', X.usd(p.cost))}`
      + stat('Mark · ' + X.esc(age.words || age.txt), p.mark == null ? pqMarkCell(p) : X.esc(pqMark(p.mark)), age.amber ? 'pq-amb' : '')
      + stat('P&amp;L', pnlV) + stat('Days left', p.dte == null ? '—' : X.esc(p.dte)) + '</div>'
      + warns + acts
      + `<div class="pq-kv"><span>Earnings</span><span>${en !== undefined || pq.earnState === 'ok' ? X.esc(v2.earningsWords ? v2.earningsWords(en) : '—') : (pq.earnState === 'error' ? 'could not be read' : '…')}</span></div>`
      + `<div class="pq-kv"><span>Theme</span><span>${theme && theme.theme ? X.esc(theme.theme) : '<span class="pq-t2">no theme mapped</span>'}</span></div>`
      + `<div class="pq-kv"><span>Exit plan</span><span>${pqExitPlan(p)}</span></div>`
      + lotsLegs
      + (p.markAt ? `<div class="pq-t3 pq-chk">Mark checked ${X.esc(X.when(p.markAt))}${p.markWhy ? ' — ' + X.esc(p.markWhy) : ''}</div>` : '')
      + '</div>';
  }

  // ── CLOSED (d)7 and CASH (d)8 ──
  function pqClosed() { return `<div class="pq-closed">${X.history()}</div>`; }
  function pqCash() {
    const cb = st.cb;
    if (!cb.scope.length) return `<div class="pq-cash">${cashCards()}</div>`;
    const rows = cb.scope.map((n) => {
      const a = cb.accounts[n], d = (a && a.derived) || {}, k = st.cash, off = k && k.acct === n && k.busy ? ' disabled' : '';
      let fig = '<span class="pq-t3">…</span>', line2 = '';
      if (cb.status === 'error') { fig = '<span class="pq-t2">Cash unavailable</span>'; line2 = X.esc(cb.error || ''); }
      else if (cb.status === 'ok' && !a) { fig = '<span class="pq-t2">No record</span>'; line2 = 'The hub returned nothing for this account.'; }
      else if (cb.status === 'ok' && d.derivable) {
        const src = sourceLine(d), mv = moveParts(d);
        fig = money2(d.balance);
        line2 = [src ? X.esc(pqCap(src)) : '', mv ? `<span class="${mv.sign}" title="${X.esc(mv.detail)}">${mv.text}</span>` : ''].filter(Boolean).join(' · ');
      } else if (cb.status === 'ok') {
        fig = '<span class="pq-t2">No balance yet</span>';
        line2 = `<span title="${X.esc(d.reason || '')}">Nothing has told the hub where this account started. Use “Set to broker’s figure” to give it a starting point.</span>`;
      }
      return `<div class="pq-crow" data-acct-card="${X.esc(n)}"><div class="pq-c1"><b>${X.esc(pqName(n))}</b><span class="pq-cf">${fig}</span></div>`
        + `<div class="pq-c2"><span class="pq-cl">${line2}</span><span class="pq-ca"><button type="button" class="pq-tl" data-cash-open="flow" data-acct="${X.esc(n)}"${off}>Deposit / withdrawal</button>`
        + `<button type="button" class="pq-tl" data-cash-open="set" data-acct="${X.esc(n)}"${off}>Set to broker’s figure</button></span></div>`
        + `${cashPanel({ account: n }, { noAcct: true })}</div>`;
    }).join('');
    return `<div class="pq-cash">${rows}<div class="pq-cfoot">Set to broker’s figure replaces the hub’s cash with your broker’s number. Do it after your broker history is booked, so nothing counts twice.</div></div>`;
  }

  // ── the two layouts ──
  function pqMissingPick() {
    if (st.id == null || byId(st.id)) return '';
    if (BK.open.status !== 'ok') return X.state(BK.open, 'Reading your book…', 'your book', 'open');
    return `<div class="pp-note pp-warn">Position #${X.esc(st.id)} is not in your open book. It may have been closed, or the address may be old.<div><button type="button" class="pq-back" data-allpos="1">← All positions</button></div></div>`;
  }
  function pqDesktop() {
    const sel = byId(st.id), wide = pqWide();
    const top = pqStrip() + pqTabs();
    if (pq.view === 'closed') return top + pqClosed();
    if (pq.view === 'cash') return top + pqCash();
    const chip = pq.noPrice != null ? '<button type="button" class="pq-npc" data-pq-clear-noprice>No price ✕</button>' : '';
    const list = chip + pqTable() + '<div class="pq-t3 pq-hint">Click a row for its detail · click a group to fold it · click a column to sort</div>';
    if (wide) {
      const side = sel ? pqPicked(sel, false) : (pqMissingPick() || pqGlance());
      return top + `<div class="pq-cols"><div class="pq-main">${list}</div><aside class="pq-side">${side}</aside></div>`;
    }
    // Narrow: one column. A picked row opens IN PLACE of the list, with "← All positions".
    if (sel) return top + pqPicked(sel, true);
    return top + (pqMissingPick() || '') + pqGlanceStrip() + (pq.glance ? pqGlance() : '') + list;
  }
  function pqPhone() {
    const sel = byId(st.id);
    // A picked row is a FULL-PANEL sheet with ← back; the back gesture closes it, because picking
    // pushed a history entry (see the row handler).
    if (sel) return `<div class="pq-sheet">${pqPicked(sel, true)}</div>`;
    const top = pqStrip() + pqTabs();
    if (pq.view === 'closed') return top + pqClosed();
    if (pq.view === 'cash') return top + pqCash();
    const chip = pq.noPrice != null ? '<button type="button" class="pq-npc" data-pq-clear-noprice>No price ✕</button>' : '';
    return top + (pqMissingPick() || '') + pqGlanceStrip() + (pq.glance ? pqGlance() : '') + chip + pqPhoneList();
  }

  // ── clicks, for the redesigned panel only ──
  function pqClick(t) {
    // On a phone the pick PUSHED a history entry, so "← All positions" steps BACK through it:
    // replacing it would leave a dead entry for the back gesture to walk through next.
    if (t.closest('[data-allpos]') && mq.matches && /^#positions\/\d+/.test(location.hash)) { history.back(); return true; }
    if (t.closest('[data-pq-info]')) { pq.info = !pq.info; render(); return true; }
    const ac = t.closest('[data-pq-acct]');
    if (ac) { pq.acctF = ac.dataset.pqAcct || null; pq.noPrice = null; render(); return true; }
    const vw = t.closest('[data-pq-view]');
    if (vw) { pq.view = vw.dataset.pqView; st.id = null; setHash(true); wantTab(); render(); return true; }
    if (t.closest('[data-pq-add]')) { const v = window.__v2; if (v && v.openAddForm) v.openAddForm(); return true; }
    const so = t.closest('[data-pq-sort]');
    if (so) { const k = so.dataset.pqSort; if (pq.sortK === k) pq.sortD = -pq.sortD; else { pq.sortK = k; pq.sortD = 1; } render(); return true; }
    const fo = t.closest('[data-pq-fold]');
    if (fo) { const k = fo.dataset.pqFold; if (pq.folds.has(k)) pq.folds.delete(k); else pq.folds.add(k); pqSaveFolds(); render(); return true; }
    const np = t.closest('[data-pq-noprice]');
    if (np) { pq.noPrice = np.dataset.pqNoprice; pq.view = 'open'; pq.glance = false; st.id = null; setHash(true); render(); return true; }
    if (t.closest('[data-pq-clear-noprice]')) { pq.noPrice = null; render(); return true; }
    if (t.closest('[data-pq-glance]')) { pq.glance = !pq.glance; render(); return true; }
    const act = t.closest('[data-pq-act]');
    if (act) {
      const p = byId(st.id), v = window.__v2 || {};
      const raw = p && BK.open.raw ? BK.open.raw.get(p.pid) : null;
      if (act.dataset.pqAct === 'chart') { if (p && v.openChart) v.openChart(p.ticker, act); }
      else if (act.dataset.pqAct === 'close') { if (raw && v.openCloseForm) v.openCloseForm(raw); }
      else if (act.dataset.pqAct === 'add') { if (raw && v.openAddToPositionForm) v.openAddToPositionForm(raw); }
      return true;
    }
    const row = t.closest('[data-pq-row]');
    if (row) {
      st.id = Number(row.dataset.id);
      // On a phone the pick PUSHES a history entry, so Android's back gesture closes the sheet;
      // on a desktop it replaces, so back leaves the panel rather than walking every pick.
      setHash(!mq.matches);
      wantSub(); render(); return true;
    }
    return false;
  }

  // Earnings, once per panel open (d)5(i).
  async function pqLoadEarn() {
    if (pq.earnSeq === pq.openSeq) return;
    pq.earnSeq = pq.openSeq;
    const tks = [...new Set(BK.open.rows.map((p) => String(p.ticker || '').toUpperCase()).filter(Boolean))];
    if (!tks.length) { pq.earnState = 'ok'; return; }
    pq.earnState = 'loading'; if (st.open) render();
    try {
      const d = await bkJson('/api/chronos/next-earnings-batch?tickers=' + encodeURIComponent(tks.join(',')));
      pq.earn = (d && d.earnings) || {}; pq.earnState = 'ok';
    } catch (_) { pq.earnState = 'error'; }
    if (st.open) render();
  }

  function render() {
    if (!panel) return;
    const prev = panel.querySelector('.pp-body');
    const keepTop = prev ? prev.scrollTop : 0;
    if (POS_V1) panel.innerHTML = head() + `<div class="pp-body">${mq.matches ? phone() : desktop()}</div>`;
    else {
      pq.lastWide = pqWide();
      panel.innerHTML = pqHead() + `<div class="pp-body pq-body">${mq.matches ? pqPhone() : pqDesktop()}</div>`;
    }
    panel.querySelectorAll('tr.pp-row').forEach((r) => r.classList.toggle('sel', Number(r.dataset.id) === st.id));
    const body = panel.querySelector('.pp-body'); if (body) body.scrollTop = keepTop;
    if (st.cash && st.cash.focus) { const el = panel.querySelector('[data-cf="' + st.cash.focus + '"]'); if (el) el.focus(); st.cash.focus = null; }
  }
  function onPanelClick(e) {
    const t = e.target;
    if (t.closest('.pp-x')) return close();
    if (cashClick(t)) return;
    if (!POS_V1 && pqClick(t)) return;
    const retry = t.closest('[data-bk-retry]');
    if (retry) {
      const k = retry.dataset.bkRetry;
      if (k === 'open') loadOpen(); else if (k === 'hist') loadHist();
      else { const p = BK.open.rows.find((x) => x.pid === k); if (p) { delete BK.sub[k]; loadSub(p); } }
      return;
    }
    if (t.closest('[data-allpos]')) { st.id = null; st.card = null; if (st.tab === 'Detail' || st.tab === 'Actions') st.tab = 'Detail'; setHash(true); return render(); }
    const tab = t.closest('[data-tab]');
    if (tab) { st.tab = tab.dataset.tab; setHash(true); wantTab(); return render(); }
    const mtab = t.closest('[data-mtab]');
    if (mtab) { st.mtab = mtab.dataset.mtab; wantTab(); return render(); }
    if (t.closest('[data-toggle-actions]')) { st.actions = !st.actions; return render(); }
    const tr = t.closest('tr.pp-row');
    if (tr) { st.id = Number(tr.dataset.id); if (st.tab === 'New' || st.tab === 'History') st.tab = 'Detail'; setHash(true); wantSub(); return render(); }
    const c = t.closest('.pp-pcard');
    if (c && !t.closest('.pp-sheet')) { const id = Number(c.dataset.card); st.card = st.card === id ? null : id; st.id = st.card; st.actions = false; setHash(true); wantSub(); return render(); }
  }
  // Only what the open view needs. The closed history is 500-odd rows and the drawer's lots and
  // legs are two requests per position, so neither is fetched until something asks to see it.
  function wantTab() {
    // R-IV.1382(d)7: CLOSED still loads only when opened.
    const onHistory = !POS_V1 ? pq.view === 'closed' : mq.matches ? st.mtab === 'History' : st.tab === 'History';
    if (onHistory && BK.hist.status === 'idle') loadHist();
  }
  function wantSub() {
    const p = byId(st.id);
    if (p) loadSub(p);
  }
  function show(opts) {
    build();
    if (!st.open) pq.openSeq += 1;                 // one earnings read per panel OPEN, not per paint
    st.open = true;
    if (opts.id != null) { st.id = opts.id; st.card = opts.id; }
    if (opts.tab) st.tab = opts.tab;
    if (mq.matches && opts.id != null) st.mtab = 'Book';
    if (!POS_V1) {
      if (opts.view) pq.view = opts.view;
      // The BOOK tile's doorways (R-IV.1369(e)3/(e)4) hand over which account and which tab: an
      // account row opens filtered to it, the cash row opens CASH, the footer link clears both.
      if ('__ppAcct' in window) {
        pq.acctF = window.__ppAcct || null;
        pq.view = window.__ppTab === 'cash' ? 'cash' : 'open';
        pq.noPrice = null;
        try { delete window.__ppAcct; delete window.__ppTab; } catch (_) { window.__ppAcct = undefined; }
      }
    }
    render();
    liftBook();
    loadCash();
    loadOpen().then(() => { wantSub(); if (!POS_V1) pqLoadEarn(); });
    wantTab();
    const first = !panel.classList.contains('open');
    requestAnimationFrame(() => { backdrop.classList.add('open'); panel.classList.add('open'); document.documentElement.classList.add('pp-open'); if (first) { const x = panel.querySelector('.pp-x'); if (x) x.focus(); } });
  }
  function open(opts, push) {
    opts = opts || {};
    const was = st.open;
    if (!was) st.opener = document.activeElement;
    show(opts);
    if (push !== false) setHash(was);
  }
  function hide() {
    st.open = false;
    if (backdrop) { backdrop.classList.remove('open'); panel.classList.remove('open'); }
    document.documentElement.classList.remove('pp-open');
    document.documentElement.style.removeProperty('--pp-shift');
    if (st.opener && st.opener.focus) { try { st.opener.focus(); } catch (_) {} }
  }
  function close() {
    if (!st.open) return;
    hide();
    if (/^#positions/.test(location.hash)) history.pushState(null, '', location.pathname + location.search);
  }
  function sync() {
    const h = readHash();
    if (h) {
      if (!st.open) show({ id: h.id, tab: h.tab, view: h.view });
      else {
        st.id = h.id; st.tab = h.tab;
        // A popped pick (the back gesture closing a phone sheet) lands here with id null.
        if (!POS_V1 && h.view) { pq.view = h.view; wantTab(); wantSub(); }
        render();
      }
    }
    else if (st.open) hide();
  }
  // The doorway (R-IV.555): the "Positions" button on the Book tile, or the #positions address. A Book row is NOT a
  // doorway: it opens the live position drawer (Close position lives there), exactly as before the panel existed.
  document.addEventListener('click', (e) => {
    if (e.target.closest && e.target.closest('#bookPanelBtn')) { e.preventDefault(); open({}); }
  });
  window.addEventListener('popstate', sync);
  window.addEventListener('hashchange', sync);
  function init() {
    window.addEventListener('resize', () => { if (st.open) liftBook(); });
    sync();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();

/* River preview, R-IV.564 -- a MOCKUP on SAMPLE DATA of the Olympus review's wave 2. It reads nothing from the
   hub and changes nothing: the live River (#riverStream) is untouched. Opened from the River tile's "Preview"
   button or the #river-preview address. Nothing on it pulses. */
(function () {
  'use strict';
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  // Every number, name and time below is invented for the preview.
  const REC = {
    pullback: { n: 41, hit: 58, r: '+0.34R' }, retest: { n: 33, hit: 55, r: '+0.21R' }, fade: { n: 52, hit: 61, r: '+0.40R' },
    range: { n: 12, hit: 50, r: '+0.05R' }, tritonRec: null,
  };
  const recText = (r) => (r ? `record: ${r.n} trades · ${r.hit}% won · ${r.r} each${r.n < 20 ? ' · too few to trust' : ''}` : 'unproven');
  const GATES = ['against tape', 'regime degraded', 'earnings in 2d', 'illiquid', 'unproven'];
  // Signals. `gates` = the gates it fails in each sample day (an empty list passes them all). `on` = the sample days it exists on.
  const SIGNALS = [
    { id: 'nvda', t: 'NVDA', d: 'LONG', s: 'Trend Pullback', rec: REC.pullback, f: 'up', time: '1:45 PM MT', on: ['riskon'], gates: { riskon: [] } },
    { id: 'iwm', t: 'IWM', d: 'SHORT', s: 'Failed Bounce', rec: REC.fade, f: null, time: '1:20 PM MT', on: ['riskon'], gates: { riskon: ['against tape'] } },
    { id: 'xle', t: 'XLE', d: 'LONG', s: 'Trend Pullback', rec: REC.pullback, f: null, time: '12:50 PM MT', on: ['riskon'], gates: { riskon: ['earnings in 2d'] } },
    { id: 'msft', t: 'MSFT', d: 'LONG', s: 'Breakdown Retest', rec: REC.retest, f: 'up', time: '12:10 PM MT', on: ['riskon'], gates: { riskon: ['illiquid'] } },
    { id: 'tsla', t: 'TSLA', d: 'LONG', s: 'Trend Pullback', rec: REC.pullback, f: null, time: '11:40 AM MT', on: ['riskon'], gates: { riskon: ['regime degraded'] } },
    { id: 'qqq', t: 'QQQ', d: 'LONG', s: 'Range Break', rec: REC.range, f: 'down', time: '1:05 PM MT', on: ['neutral', 'riskon'], gates: { neutral: ['unproven'], riskon: ['unproven'] } },
    { id: 'triton', t: 'SPY', d: 'LONG', s: 'TRITON (shadow)', rec: null, f: null, time: '1:30 PM MT', on: ['neutral', 'riskon'], gates: { neutral: [], riskon: [] } },
    { id: 'hera', t: 'QQQ', d: 'SHORT', s: 'HERA (shadow)', rec: null, f: null, time: '10:55 AM MT', on: ['neutral', 'riskon'], gates: { neutral: [], riskon: [] } },
    { id: 'circe', t: 'IWM', d: 'SHORT', s: "CIRCE'S STEW (shadow)", rec: null, f: 'up', time: '9:40 AM MT', on: ['neutral', 'riskon'], gates: { neutral: [], riskon: [] } },
  ];
  // Items that touch an open position. `v`: CONTRADICTS or CONFIRMS what the position needs.
  const BOOK = [
    { id: 'b1', t: 'HYG', pos: 'put spread 76/73 (bearish hedge)', v: 'CONTRADICTS', why: 'Credit spreads tightened to 3.0: the stress the hedge is paid for is fading.', f: null, time: '1:00 PM MT' },
    { id: 'b2', t: 'AVGO', pos: 'put debit spread 300/290 (bearish)', v: 'CONTRADICTS', why: 'An unproven AVGO LONG setup leans against your bearish spread.', f: 'up', time: '12:30 PM MT' },
    { id: 'b3', t: 'PDBC', pos: 'commodity fund, long', v: 'CONFIRMS', why: 'Supply-cut headline supports the position.', f: 'up', time: '11:15 AM MT' },
  ];
  const CONTEXT = [
    { id: 'c1', k: 'regime', text: (day) => day === 'neutral' ? 'Regime NEUTRAL · composite 50 · the stable lens reads RISK-ON: the two lenses disagree.' : 'Regime RISK-ON · composite 68 · both lenses agree.', time: '9:30 AM MT' },
    { id: 'c2', k: 'unusual flow', text: () => 'Unusual flow on your watchlist: NVDA, call-heavy. (Not on a position, so it is context, not an alert.)', time: '1:10 PM MT' },
    { id: 'c3', k: 'headline', text: () => 'Fed speakers scheduled 2:00 PM MT.', time: '12:00 PM MT' },
    { id: 'c4', k: 'digest', text: () => 'Stable digest: breadth 61%, 3 of 5 sleeves above their 50-day.', time: '8:05 AM MT' },
  ];
  const EMPTY_REASON = { neutral: 'Nothing actionable: no validated setup is possible in a NEUTRAL regime.', riskon: 'Nothing actionable: every validated setup today fails a gate, and each one is in Watch with its reason.' };
  let day = 'neutral', open = false, backdrop = null, panel = null, opener = null;

  const fBadge = (f) => f ? `<span class="rp-f" title="Options flow ${f === 'up' ? 'agrees with' : 'disagrees with'} this idea (a badge, not a River item)">F${f === 'up' ? '▲' : '▼'}</span>` : '';
  function sigRow(s, kind) {
    const gates = s.gates[day] || [];
    const gate = kind === 'watch' ? `<span class="rp-gate" title="The one gate this idea fails">${esc(gates[0])}</span>` : '';
    return `<div class="rp-row"><div class="rp-main"><b>${esc(s.t)}</b> <span class="rp-dir">${esc(s.d)}</span> · ${esc(s.s)} ${fBadge(s.f)}${gate}</div>
      <div class="rp-sub"><span class="${s.rec ? '' : 'rp-unproven'}">${esc(recText(s.rec))}</span> · ${esc(s.time)}</div></div>`;
  }
  function bookRow(b) {
    const bad = b.v === 'CONTRADICTS';
    return `<div class="rp-row ${bad ? 'rp-bad' : 'rp-ok'}"><div class="rp-main"><span class="rp-tag ${bad ? 'rp-tag-bad' : 'rp-tag-ok'}">${b.v}</span> <b>${esc(b.t)}</b> · your ${esc(b.pos)} ${fBadge(b.f)}</div>
      <div class="rp-sub">${esc(b.why)} · ${esc(b.time)}</div></div>`;
  }
  function lane(title, count, body, opts) {
    const o = opts || {};
    const head = `<span class="rp-lane-t">${esc(title)}</span><span class="rp-count">${count}</span>${o.note ? `<span class="rp-note">${esc(o.note)}</span>` : ''}`;
    if (o.collapsed) return `<details class="rp-lane"><summary>${head}</summary>${body}</details>`;
    return `<section class="rp-lane"><h3 class="rp-h">${head}</h3>${body}</section>`;
  }
  function render() {
    const sigs = SIGNALS.filter((s) => s.on.indexOf(day) >= 0);
    const proven = sigs.filter((s) => s.rec);
    const actionable = proven.filter((s) => (s.gates[day] || []).length === 0 && s.rec.n >= 20);
    const watch = sigs.filter((s) => (s.gates[day] || []).length === 1);
    const unproven = sigs.filter((s) => !s.rec);
    const book = BOOK.slice().sort((a, b) => (a.v === 'CONTRADICTS' ? 0 : 1) - (b.v === 'CONTRADICTS' ? 0 : 1));
    const ctx = CONTEXT;
    const empty = (msg) => `<div class="rp-empty">${esc(msg)}</div>`;
    panel.innerHTML = `<div class="rp-head"><h2>River preview</h2><span class="rp-chip">mockup · sample data</span><button type="button" class="rp-x" aria-label="Close the River preview">✕</button></div>
      <div class="rp-banner">Mockup on sample data. Nothing here is live and nothing here changes your River. Every name, number and time is invented.</div>
      <div class="rp-body">
        <div class="rp-days" role="group" aria-label="Sample day"><span class="rp-dim">Sample day:</span>
          <button type="button" data-day="neutral" aria-pressed="${day === 'neutral'}">Neutral regime</button>
          <button type="button" data-day="riskon" aria-pressed="${day === 'riskon'}">Risk-on regime</button></div>
        ${lane('Actionable', actionable.length, actionable.length ? actionable.map((s) => sigRow(s, 'act')).join('') : empty(EMPTY_REASON[day]))}
        ${lane('Your book', book.length, book.map(bookRow).join(''), { note: 'contradictions first' })}
        ${lane('Watch', watch.length, watch.length ? watch.map((s) => sigRow(s, 'watch')).join('') : empty('Nothing on watch.'), { note: 'the one gate each fails' })}
        ${lane('Unproven', unproven.length, unproven.map((s) => sigRow(s, 'unproven')).join(''), { collapsed: true, note: 'strategies with no record yet' })}
        ${lane('Context', ctx.length, ctx.map((c) => `<div class="rp-row"><div class="rp-main"><span class="rp-k">${esc(c.k)}</span> ${esc(c.text(day))}</div><div class="rp-sub">${esc(c.time)}</div></div>`).join(''), { note: 'not trades' })}
      </div>`;
  }
  function build() {
    if (panel) return;
    backdrop = document.createElement('div'); backdrop.className = 'rp-backdrop';
    panel = document.createElement('aside'); panel.className = 'rp-panel';
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true'); panel.setAttribute('aria-label', 'River preview (mockup, sample data)');
    document.body.appendChild(backdrop); document.body.appendChild(panel);
    backdrop.addEventListener('click', close);
    panel.addEventListener('click', (e) => {
      if (e.target.closest('.rp-x')) return close();
      const d = e.target.closest('[data-day]'); if (d) { day = d.dataset.day; render(); }
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && open) close(); });
  }
  function show() {
    build(); open = true; render();
    // Open on the River tile's side (follows the tile if it is dragged across).
    const v2 = window.__v2;
    if (v2 && v2.setSide) v2.setSide(panel, v2.popSide(opener && opener.isConnected ? opener : null, 'river'));
    requestAnimationFrame(() => { backdrop.classList.add('open'); panel.classList.add('open'); if (v2 && v2.placeChartSoon) v2.placeChartSoon(); const x = panel.querySelector('.rp-x'); if (x) x.focus(); });
  }
  function hide() { open = false; if (backdrop) { backdrop.classList.remove('open'); panel.classList.remove('open'); if (window.__v2 && window.__v2.placeChartSoon) window.__v2.placeChartSoon(); } if (opener && opener.focus) { try { opener.focus(); } catch (_) {} } }
  function openIt() { if (open) return; opener = document.activeElement; show(); if (location.hash !== '#river-preview') history.pushState(null, '', location.pathname + location.search + '#river-preview'); }
  function close() { if (!open) return; hide(); if (location.hash === '#river-preview') history.pushState(null, '', location.pathname + location.search); }
  function sync() { if (location.hash === '#river-preview') { if (!open) show(); } else if (open) hide(); }
  document.addEventListener('click', (e) => { if (e.target.closest && e.target.closest('#riverPreviewBtn')) { e.preventDefault(); openIt(); } });
  // R-IV.1364(c): a mockup on sample data does not sit on the default screen. The button ships
  // `hidden` in v2.html and comes back only for `?river=preview`, like the other review flags.
  function revealPreviewBtn() {
    try {
      if (new URLSearchParams(location.search).get('river') !== 'preview') return;
      const b = document.getElementById('riverPreviewBtn');
      if (b) b.hidden = false;
    } catch (_) { /* stays hidden */ }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', revealPreviewBtn);
  else revealPreviewBtn();
  window.addEventListener('popstate', sync); window.addEventListener('hashchange', sync);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', sync); else sync();
})();

/* ===========================================================================
   A3 — POSITION WATCH (R-IV.1209(c), boards 5 and 6). MOCK LIST ONLY.
   =========================================================================== */
(() => {
  'use strict';

  // NO PUSH IS SENT FROM THIS FILE, and nothing here can send one. The phone block is a
  // PICTURE of a notification. The live path -- ntfy, the 30-minute per-ticker throttle, the
  // 20-a-day cap -- is B2's, server side, under R-IV.1209(f).
  //
  // THE NTFY TOPIC IS NEVER PRINTED OR LOGGED (R-IV.1209(f)6, R-IV.901(b)1). It is not in this
  // file, it is not in the fixture, and it cannot be: the browser never learns it.
  //
  // WHAT THE WORDING MAY SAY (f)5: "tighten / trim" and "review stop". NEVER buy, sell or
  // reverse. Every row carries its shown_regime and the panel says "alerts, not signals" --
  // and the backend test runs the EXISTING no-orders lint over every string in the fixture,
  // the same lint that guards the registered playbooks.
  //
  // NOT A SIGNAL, EVER (f)6: nothing here writes to `signals`, nothing is graded, and the rows
  // do not reach Kairos or the River's actionable lanes.

  const LIVE = '/api/position-watch';
  // Kept for reference only: A3's mock fixture. `load()` does NOT read it.
  const FIXTURE = '/assets/agora/position_watch_mock.json';
  let panel = null, backdrop = null, data = null, tab = 'held', opener = null, isOpen = false;

  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function rowHtml(r) {
    const against = !!r.against;
    return '<div class="pw-row' + (against ? ' pw-against' : '') + '">'
      + '<div class="pw-time">' + esc(r.time) + '<i>' + esc(r.source) + '</i></div>'
      + '<div class="pw-icon pw-' + esc(r.glyph_lean || 'neutral') + '">'
      + esc(r.glyph) + '</div>'
      + '<div class="pw-main">'
      + '<div class="pw-top"><b>' + esc(r.ticker) + '</b>'
      + '<span class="pw-ev">' + esc(r.event) + '</span>'
      + '<span class="pw-tf">' + esc(r.tf) + '</span>'
      // R-IV.1215(b)5: the row KEEPS the words it was written with and carries a tag saying a
      // later bar changed what they mean. A number that silently becomes a different number
      // is the thing a log exists to prevent.
      + (r.revised ? '<span class="pw-revised" title="a later bar superseded this reading: '
        + 'the gap did not hold">REVISED</span>' : '')
      + (r.gap_held === null && r.gap_open
        ? '<span class="pw-pending" title="' + esc(r.gap_held_reason || '') + '">UNCONFIRMED'
          + '</span>' : '')
      + '</div>'
      + '<div class="pw-det">' + esc(r.detail) + '</div>'
      + '</div>'
      // AGAINST / WITH is the whole routing decision ((f)3-4), so it is the loudest thing on
      // the row after the ticker.
      + '<div class="pw-rel' + (against ? ' pw-rel-a' : ' pw-rel-w') + '">'
      + (against ? 'AGAINST YOU' : 'WITH YOU') + '</div>'
      // (f)5: every alert is tagged with shown_regime.
      + '<div class="pw-reg" title="the regime label at the time of the alert">'
      + esc(r.shown_regime || '—') + '</div>'
      + '<div class="pw-act' + (r.pushed ? ' pw-pushed' : '') + '">'
      + esc(r.action) + '</div>'
      + '</div>';
  }

  // R-IV.1215(b)3 + R-IV.1228(d): the footer. Built from the payload's OWN resolution of
  // Set B, which is the same resolution the detector ran on, so the panel cannot claim to
  // watch a ticker the job skipped. Every exclusion shows its ruled reason: a ticker missing
  // from a watch list with no reason reads as an oversight.
  function footerHtml(f) {
    if (!f) return '';
    const watched = (f.watched || []);
    const via = f.watched_via || {};
    const nw = f.not_watched || {};
    const chips = watched.map((t) => {
      const through = (via[t] || []).filter((v) => v !== t);
      const title = through.length ? t + ' — watched through ' + through.join(', ') : t;
      return '<span class="pw-w" title="' + esc(title) + '">' + esc(t)
        + (through.length ? '<i>via ' + esc(through.join(', ')) + '</i>' : '') + '</span>';
    }).join('');
    const outs = Object.keys(nw).map((t) =>
      '<span class="pw-nw" title="' + esc(nw[t]) + '">' + esc(t) + '</span>').join('');
    return '<div class="pw-foot">'
      + '<div class="pw-fl"><b>WATCHED · ' + watched.length + '</b>' + chips + '</div>'
      + (outs ? '<div class="pw-fl pw-fl-out"><b>NOT WATCHED · '
        + Object.keys(nw).length + '</b>' + outs + '</div>' : '')
      // The ruled phone line is NOT repeated here: it is rendered once in the chain above,
      // from the one string the backend test binds to `PANEL_FOOTER_PHONE_LINE`. Two copies
      // of a sentence drift, and this one is ruled verbatim.
      + '</div>';
  }

  function pushHtml(p) {
    return '<div class="pw-push">'
      + '<div class="pw-ph"><span class="pw-pi">P</span>'
      + '<span class="pw-pn">PANDORA · POSITION WATCH</span>'
      + '<span class="pw-pa">' + esc(p.ago) + '</span></div>'
      + '<div class="pw-pt">' + esc(p.title) + '</div>'
      + '<div class="pw-pb">' + esc(p.body) + '</div>'
      + '<div class="pw-pf"><span class="pw-rel pw-rel-a">AGAINST YOU</span>'
      + '<span class="pw-ptag">' + esc(p.tag) + '</span></div>'
      + '</div>';
  }

  function render() {
    if (!panel) return;
    if (!data) {
      panel.innerHTML = '<div class="pw-head"><h3>Position Watch</h3>'
        + '<span class="x pw-x">✕</span></div>'
        + '<div class="pw-body"><div class="rs-wait">'
        + 'the Position Watch fixture did not load</div></div>';
      return;
    }
    const rows = (data.rows || []);
    const held = tab === 'held';
    panel.innerHTML =
      '<div class="pw-head">'
      + '<h3>Position Watch</h3>'
      + (data._mock
        ? '<span class="mock-chip" title="A3 is a mock list (R-IV.1209(c)). Every value is '
          + 'fake and NO PUSH IS SENT.">MOCK</span>'
        // The chip follows the PAYLOAD, not the markup. A live panel still wearing a MOCK
        // chip trains Nick to ignore the chip, which is worse than having none.
        : '<span class="mock-chip pw-live" title="B2 is live: these rows are stored events '
          + 'from position_watch_events, and the phone wire is '
          + ((data.footer && data.footer.pushes_enabled) ? 'ON' : 'OFF') + '.">LIVE</span>')
      + '<div class="pw-tabs">'
      + '<button type="button" class="pw-tab' + (held ? ' on' : '') + '" data-tab="held">'
      + 'HELD · ' + esc(data.held_count) + '</button>'
      + '<button type="button" class="pw-tab' + (held ? '' : ' on') + '" data-tab="quiet">'
      + 'QUIET · ' + esc(data.quiet_count) + '</button>'
      + '</div>'
      + '<span class="x pw-x" title="Close">✕</span>'
      + '</div>'
      + '<div class="pw-body">'
      + (held
        ? rows.map(rowHtml).join('')
        // (f)4: a non-held ticker goes to the QUIET tab and is never pushed. The tab shows the
        // COUNT and says so, rather than listing alerts about things Nick does not own as if
        // they were his.
        : '<div class="pw-quiet">' + esc(data.quiet_note || '') + '</div>')
      + '<div class="pw-cap">' + esc(data.caption || '') + '</div>'
      + '<div class="pw-sec">PHONE · LOCK SCREEN · MOCK</div>'
      + '<div class="pw-pushes">' + (data.pushes || []).map(pushHtml).join('') + '</div>'
      + '<div class="pw-cap">' + esc(data.push_rule || '') + '</div>'
      // R-IV.1228(d), VERBATIM. NOT from the mock fixture: it is a standing rule about the
      // live path, not a fake value, and `models.position_watch.PANEL_FOOTER_PHONE_LINE`
      // holds the same string with a test binding the two so they cannot drift apart.
      + '<div class="pw-cap pw-phone-rule">Phone: one alert per ticker per day, '
      + 'against-you only</div>'
      + (data._mock
        ? '<div class="pw-cap pw-warn">A3 sends nothing. The block above is a picture of a '
          + 'notification, not a notification — the live path is B2.</div>'
        : footerHtml(data.footer))
      + '</div>';
  }

  function build() {
    if (panel) return;
    backdrop = document.createElement('div');
    backdrop.className = 'rp-backdrop pw-backdrop';
    panel = document.createElement('aside');
    panel.className = 'rp-panel pw-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', 'Position Watch (mock list, no live pushes)');
    document.body.appendChild(backdrop);
    document.body.appendChild(panel);
    backdrop.addEventListener('click', close);
    panel.addEventListener('click', (e) => {
      if (e.target.closest('.pw-x')) return close();
      const t = e.target.closest('[data-tab]');
      if (t) { tab = t.dataset.tab; render(); }
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && isOpen) close(); });
  }

  async function load() {
    if (data) return;
    // B2 IS LIVE, so the live route is the source and THE MOCK IS NOT A FALLBACK. If the read
    // fails, render() says so; drawing the fixture instead would show Nick fake alerts that
    // look exactly like real ones, and drawing an empty list would assert "no alerts", which
    // is a claim. The mock fixture stays on disk for the A3 layout, not as a safety net.
    try {
      const r = await apiFetch(LIVE);
      data = r.ok ? await r.json() : null;
    } catch (_) {
      data = null;
    }
    if (data && data.error) { data = null; }
  }

  async function openIt() {
    if (isOpen) return;
    opener = document.activeElement;
    build();
    await load();
    isOpen = true;
    render();
    const v2 = window.__v2;
    if (v2 && v2.setSide) {
      v2.setSide(panel, v2.popSide(opener && opener.isConnected ? opener : null, 'book'));
    }
    requestAnimationFrame(() => {
      backdrop.classList.add('open');
      panel.classList.add('open');
      const x = panel.querySelector('.pw-x');
      if (x) x.focus();
    });
  }

  function close() {
    if (!isOpen) return;
    isOpen = false;
    if (backdrop) { backdrop.classList.remove('open'); panel.classList.remove('open'); }
    if (opener && opener.focus) { try { opener.focus(); } catch (_) {} }
  }

  document.addEventListener('click', (e) => {
    if (e.target.closest && e.target.closest('#posWatchBtn')) { e.preventDefault(); openIt(); }
  });
})();
