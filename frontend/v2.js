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
    REGIME: 'Two lenses: Composite (weighted factor bias, X/100) vs Stable engine read (breadth-based)',
    COMPOSITE: 'Composite bias score on a 0–100 scale (50 = neutral); the weighted factor blend',
    STABLE: 'Stable engine regime — RISK-ON/NEUTRAL/RISK-OFF from % of universe above 50DMA',
    DIVERGE: 'The Composite and Stable lenses disagree on direction — size with caution',
    DOM: 'Dominant theme — score >= 75',
    EMG: 'Emerging / improving theme',
    FAD: 'Fading / deteriorating theme',
    TIDE: 'Market tide — net options-flow direction (net call vs put premium, cached UW read)',
    HL: 'New 20-day / 52-week highs (H) and lows (L) across the scored universe',
    BREADTH50: 'Percent of the scored universe above its 50-day moving average',
    BREADTH: 'Participation: % of universe above 20/50/200DMA, new highs/lows, ±3% movers',
    KILL: 'Kill-switch / circuit-breaker state. ARMED = a market-risk breaker fired. CLEAR = the system confirmed no breaker is active. NO TRIP ON RECORD = healthy resting state, nothing stored (the breaker only writes when it fires). UNKNOWN = the source could not be reached — not a clear',
    THEMES: 'Ranked theme board: score, 1-day delta, and status (dominant/emerging/fading)',
    DIVERGENCE: 'Sector ETF %-change spread — which sectors lead/lag; dot = above both 50/200DMA',
    INDEX: 'Major index 1-day % and ATR extension (how stretched vs typical range)',
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
      + '<div style="color:#14b8a6;font-weight:700;letter-spacing:2px">PANDORA v2</div>'
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
    dot.setAttribute('title', GLOSSARY.HEALTH + ' — ' + (worst === 'dead' ? 'DEAD feed(s) — pipe flatlined' : worst === 'suspect' ? 'SUSPECT — a displayed change does not match its own spot and prior close' : worst === 'down' ? 'a source reported an error' : worst === 'unconfirmed' ? 'cannot confirm — a feed is unreadable or stale' : worst === 'closed' ? 'market session not open' : (worst || 'no data')));
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
    let v;
    if (unreachable) {
      v = { label: 'UNKNOWN', cls: 'val-amber', pulse: '',
            prov: 'source unreachable — not a clear', provCls: 'val-amber' };
    } else if (k.active) {
      const pending = !!k.pending_reset;
      const firedAge = fmtAge(k.triggered_at ? (Date.now() - Date.parse(k.triggered_at)) / 1000 : p.age_seconds);
      const trig = esc(k.trigger || 'risk-off');
      v = {
        // pending_reset still means active=true — the breaker is still enforcing
        // caps/floors until an operator accepts. It stays in the ARMED family.
        label: pending ? 'ARMED · PENDING' : 'ARMED',
        cls: 'val-down', pulse: ' pulse-vermilion',
        prov: pending ? trig + ' · awaiting reset, still enforcing'
                      : trig + (firedAge ? ' · fired ' + firedAge + ' ago' : ''),
        provCls: 'val-down',
      };
    } else if (source === 'event-confirmed') {
      v = { label: 'CLEAR', cls: 'val-teal', pulse: '',
            prov: 'confirmed this session' + (stateAge ? ' · ' + stateAge : ''), provCls: '' };
    } else if (source === 'restored-at-boot') {
      v = { label: 'CLEAR', cls: 'val-teal', pulse: '',
            prov: 'restored at startup' + (stateAge ? ' · ' + stateAge : ''), provCls: '' };
    } else {
      // Healthy resting state: the breaker writes only on events, so no record is
      // the normal condition. Calm and affirmative — NOT "NO DATA", which implies
      // breakage and trains the operator to ignore a working safety surface.
      v = { label: 'NO TRIP ON RECORD', cls: 'val-quiet', pulse: '',
            prov: 'nothing stored' + (stateAge ? ' · since startup ' + stateAge : ''), provCls: '' };
    }

    // A1 divergence — disclosed as a provenance value, not a sixth visual state.
    // Provenance overlays apply only when we actually have a payload to describe.
    if (!unreachable) {
      if (p.divergence) { v.prov = esc(p.divergence); v.provCls = 'val-amber'; }
      else if (p.persisted_record === 'unreadable') { v.prov += ' · record unreadable'; v.provCls = 'val-amber'; }
      if (staleRead) { v.prov += ' · ' + staleRead; v.provCls = 'val-amber'; }
    }
    // Long labels ("NO TRIP ON RECORD") cannot hold the 22px/19px display size in a
    // half-width phone cell; step them down rather than let them clip or overflow.
    v.sizeCls = v.label.length > 8 ? ' big-long' : '';
    return v;
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
    renderRegimeBand(composite, regime, tide, kill);
    renderBreadthPanel(regime);          // b3 shares the regime payload
    emitRegimeRiverItems(composite, regime, kill);

    const age = regime && regime.data_age_seconds != null ? regime.data_age_seconds : null;
    const degraded = regime ? !!regime.degraded : null;   // null = no payload (R-IV.413(e))
    _health.regime = healthState(age, degraded, regime && regime.flatline, regime && regime.session);
    noteFlatline('nightly', regime && regime.flatline, 'Regime / Themes');
    updateGlobalHealth();
  }

  function themeChips(list, cls, limit) {
    if (!list || !list.length) return '<span class="chip muted">none</span>';
    return list.slice(0, limit || 3).map((t) =>
      `<span class="chip ${cls}">${esc(t.theme)} <b>${t.score != null ? Math.round(t.score) : ''}</b></span>`).join(' ');
  }

  function renderRegimeBand(composite, regime, tide, kill) {
    const band = $('regimeBand');

    // ── Cell 1: two regime lenses, rendered distinctly ──
    const bias = composite ? (composite.bias_level || composite.level || 'UNKNOWN') : 'UNKNOWN';
    const comp100 = composite ? to100(composite.composite_score) : null;
    const biasCls = bias.includes('TORO') || bias.includes('BULL') ? 'val-up' : bias.includes('URSA') || bias.includes('BEAR') ? 'val-down' : 'val-teal';
    const breadth = (regime && regime.breadth) || {};
    const regimeLabel = regime ? (regime.regime_label || 'UNKNOWN') : 'UNKNOWN';
    const p50 = breadth.pct_above_50dma;
    const stableCls = regimeLabel === 'RISK-ON' ? 'val-up' : regimeLabel === 'RISK-OFF' ? 'val-down' : 'val-teal';
    // Divergence: one lens leans bullish while the other leans bearish
    const compDir = comp100 == null ? 0 : comp100 >= 55 ? 1 : comp100 <= 45 ? -1 : 0;
    const stableDir = regimeLabel === 'RISK-ON' ? 1 : regimeLabel === 'RISK-OFF' ? -1 : 0;
    const diverge = compDir !== 0 && stableDir !== 0 && compDir !== stableDir;

    // ── Cell 3: Tide ──
    const t = tide && tide.tide;
    const tideDir = t && t.direction ? t.direction : null;
    const tideCls = tideDir === 'BULLISH' ? 'val-up' : tideDir === 'BEARISH' ? 'val-down' : 'val-muted';
    const fmtM = (v) => (v == null ? '--' : '$' + (Number(v) / 1e6).toFixed(0) + 'M');
    const tideSub = t ? `call ${fmtM(t.net_call_premium)} · put ${fmtM(t.net_put_premium)}`
      : (tide && tide.degraded ? 'no cached flow' : '—');

    // ── Cell 6: Kill-switch (five truthful states — see killCellView) ──
    const kv6 = killCellView(kill, _killReadAt);

    const hl = (h, l) => `<span class="val-up num">${h != null ? h : '--'}</span><span class="val-muted"> / </span><span class="val-down num">${l != null ? l : '--'}</span>`;

    band.innerHTML = `
      <div class="regime-cell" data-drawer="regime">
        <span class="label" data-gloss="REGIME">Regime · two lenses</span>
        <div class="sub"><span class="chip emg" data-gloss="COMPOSITE">C</span> <span class="${biasCls}">${esc(bias.replace(/_/g, ' '))}</span> <b class="num">${comp100 != null ? comp100 + '/100' : '--'}</b></div>
        <div class="sub"><span class="chip emg" data-gloss="STABLE">S</span> <span class="${stableCls}">${esc(regimeLabel)}</span> <span class="num">${p50 != null ? p50.toFixed(0) + '% &gt;50d' : ''}</span>${diverge ? ' <span class="val-teal" data-gloss="DIVERGE">⚠ divergence</span>' : ''}</div>
      </div>
      <div class="regime-cell" data-drawer="themes">
        <span class="label">Dominant · Emerging · Fading</span>
        <div class="row">${themeChips(regime && regime.dominant, 'dom', 2)} ${themeChips(regime && regime.emerging, 'emg', 2)} ${themeChips(regime && regime.fading, 'fad', 2)}</div>
      </div>
      <div class="regime-cell">
        <span class="label" data-gloss="TIDE">Tide</span>
        <div class="big ${tideCls}">${tideDir || '—'}</div>
        <div class="sub">${tideSub}</div>
      </div>
      <div class="regime-cell" data-drawer="breadth">
        <span class="label" data-gloss="HL">New H / L</span>
        <div class="sub">20d ${hl(breadth.new_high_20d, breadth.new_low_20d)}</div>
        <div class="sub">52w ${hl(breadth.new_high_52w, breadth.new_low_52w)} <span class="val-muted">·</span> ±3% <span class="val-up num">${breadth.up_3 != null ? breadth.up_3 : '--'}</span>/<span class="val-down num">${breadth.down_3 != null ? breadth.down_3 : '--'}</span></div>
      </div>
      <div class="regime-cell" data-drawer="breadth">
        <span class="label" data-gloss="BREADTH50">% &gt; 50DMA</span>
        <div class="big num ${p50 != null && p50 >= 60 ? 'val-up' : p50 != null && p50 <= 40 ? 'val-down' : 'val-teal'}">${p50 != null ? p50.toFixed(0) + '%' : '--'}</div>
        <div class="gauge"><span style="width:${p50 != null ? Math.max(0, Math.min(100, p50)) : 0}%"></span></div>
      </div>
      <div class="regime-cell kill-cell${kv6.pulse}">
        <span class="label" data-gloss="KILL">Kill-switch</span>
        <div class="big ${kv6.cls}${kv6.sizeCls}">${kv6.label}</div>
        <div class="sub kill-prov ${kv6.provCls}">${kv6.prov}</div>
      </div>`;
    applyGlossary(band);
    band.querySelectorAll('[data-drawer]').forEach((c) => c.addEventListener('click', () => openDrawer(c.dataset.drawer, { composite, regime, tide, kill })));
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
        openCommittee(tk, k ? k.signal_id : '');
      }));
    });
  }

  function moverEl(m, side) {
    const thm = m.theme ? ` <span class="sep">·</span> <span class="thm">${esc(m.theme)}</span>` : '';
    return `<span class="mover ${side}" data-ticker="${esc(m.ticker)}"><span class="tk">${esc(m.ticker)}</span> <span class="pct">${fmtPct(m.pct)}</span><span class="badge-slot"></span>${thm}</span>`;
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
    tape.querySelectorAll('.mover[data-ticker]').forEach((el) => el.addEventListener('click', () => openTvPopover(el.dataset.ticker, el)));
  }

  // ── Drawer ────────────────────────────────────────────────────────────────
  function openDrawer(kind, ctx) {
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
        kv('Up > 3%', b.up_3) + kv('Down > 3%', b.down_3) + kv('as of (metrics)', ctx.regime.metrics_date);
    } else if (kind === 'committee') {
      title.textContent = 'Committee · ' + (ctx.ticker || '');
      body.innerHTML = kv('Ticker', ctx.ticker || '—') + kv('Signal', ctx.sig || '—') +
        '<div style="margin:10px 0;color:var(--text-3);font-size:12px">Loading options context…</div>';
      (async () => {
        try {
          const r = await apiFetch('/api/committee/enrichment/' + encodeURIComponent(ctx.ticker));
          if (!r.ok) return;
          const e = (await r.json()).enrichment || {};
          const iv = e.iv_rank || {}, tide = e.market_tide || {}, mp = e.max_pain || {}, sf = e.sector_flow || {};
          body.innerHTML = kv('Ticker', ctx.ticker) + kv('Signal', ctx.sig || '—') +
            kv('IV rank', iv.iv_rank != null ? Number(iv.iv_rank).toFixed(0) : '—') +
            kv('Market tide', (tide.net_call_premium != null && tide.net_put_premium != null) ? (Number(tide.net_call_premium) > Number(tide.net_put_premium) ? 'bullish' : 'bearish') : '—') +
            kv('Max pain', mp.max_pain_strike != null ? mp.max_pain_strike + ' (' + mp.dte + 'dte)' : '—') +
            kv('Sector posture', sf.risk_posture || '—') +
            '<div style="margin-top:10px;font-size:11px;color:var(--text-3)">Foreground UW read (on-demand). Full committee review runs from the legacy analyzer.</div>';
        } catch (_) {}
      })();
    } else {
      title.textContent = 'Regime detail';
      const c = ctx.composite || {}, r = ctx.regime || {};
      const t = ctx.tide && ctx.tide.tide, k = ctx.kill && ctx.kill.kill_switch;
      const c100 = to100(c.composite_score);
      body.innerHTML = kv('Composite bias', c.bias_level || c.level || '—') + kv('Composite (0–100)', c100 != null ? c100 + '/100' : '—') +
        kv('Composite raw', c.composite_score != null ? Number(c.composite_score).toFixed(3) : '—') +
        kv('Confidence', c.confidence || '—') + kv('Stable regime', r.regime_label || '—') + kv('% > 50DMA', (r.breadth || {}).pct_above_50dma) +
        kv('Tide', t && t.direction ? t.direction : '—') + kv('Kill-switch', k ? (k.active ? (k.pending_reset ? 'PENDING RESET' : 'ARMED · ' + (k.trigger || '')) : 'CLEAR') : '—') +
        kv('Anchor', r.anchor || '—') + kv('Data age (s)', r.data_age_seconds != null ? Math.round(r.data_age_seconds) : '—');
    }
    $('drawerBackdrop').classList.add('open');
    $('drawer').classList.add('open');
  }
  function closeDrawer() { $('drawerBackdrop').classList.remove('open'); $('drawer').classList.remove('open'); }

  // ── TV popover ────────────────────────────────────────────────────────────
  let _tvWidget = null;
  function openTvPopover(ticker, anchorEl) {
    const pop = $('tvPopover');
    $('tvPopTicker').textContent = ticker;
    $('tvPopHost').innerHTML = '<div id="tvPopHostInner" style="width:100%;height:100%"></div>';
    // position near the click, clamped to viewport
    const r = anchorEl.getBoundingClientRect();
    const w = 520, h = 360;
    pop.style.left = Math.max(8, Math.min(window.innerWidth - w - 8, r.left)) + 'px';
    pop.style.top = Math.max(8, Math.min(window.innerHeight - h - 8, r.bottom + 8)) + 'px';
    pop.classList.add('open');
    try {
      if (window.TradingView) {
        _tvWidget = new TradingView.widget({
          container_id: 'tvPopHostInner', symbol: ticker, interval: 'D', theme: 'dark',
          style: '1', autosize: true, hide_top_toolbar: true, hide_legend: true, save_image: false,
        });
      }
    } catch (_) {}
  }
  function closeTvPopover() { $('tvPopover').classList.remove('open'); $('tvPopHost').innerHTML = ''; }

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
    'regime-band', 'movers-tape', 'kairos', 'book', 'river',
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
      const layout = grid.save(false); // positions + gs-id, no content
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
    $('breadthAnchor').textContent = regime ? (regime.anchor || '') : '';
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
    el.querySelectorAll('.th-row[data-theme]').forEach((r) => r.addEventListener('click', () => openThemeMembers(r.dataset.theme)));
    applyGlossary(el);
  }

  async function openThemeMembers(theme) {
    openPopup('Theme · ' + theme, '<div class="mem-sec">loading…</div>');
    let data = null;
    try { const r = await apiFetch('/api/stable/theme/' + encodeURIComponent(theme) + '/members'); if (r.ok) data = await r.json(); } catch (_) {}
    if (!data) { $('memberBody').innerHTML = '<div class="mem-sec">unavailable</div>'; return; }
    const row = (m) => {
      const rs = m.rs_qqq_20d;
      return `<div class="mem-row" data-ticker="${esc(m.ticker)}">
        <span class="mtk" data-ticker="${esc(m.ticker)}">${esc(m.ticker)}</span>
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
    $('memberBody').querySelectorAll('.mtk[data-ticker]').forEach((e) => e.addEventListener('click', () => { closePopup(); openTvPopover(e.dataset.ticker, e); }));
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

  async function loadDivergence() {
    let data = null;
    try { const r = await apiFetch('/api/stable/sector-divergence?window=' + _divWindow); if (r.ok) data = await r.json(); } catch (_) {}
    const legend = $('divLegend'); if (!legend) return;
    if (!data || !data.sectors || data.degraded) {
      _divSectors = [];
      legend.innerHTML = '<span class="legend-chip val-muted">divergence feed unavailable</span>';
      if (_charts.divChart) { _charts.divChart.destroy(); delete _charts.divChart; }
      return;
    }
    _divSectors = data.sectors.filter((s) => s.series && s.series.length);
    _divRender();
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
    let data = null;
    try { const r = await apiFetch('/api/stable/index-strip'); if (r.ok) data = await r.json(); } catch (_) {}
    const el = $('indexStrip'); if (!el) return;
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
      return `<div class="ix-cell" data-ticker="${sym}"${pct == null ? ` title="${esc(why)}"` : ''}><span class="sym">${sym}</span>`
        + chg
        + `<span class="ext">${ext != null ? (ext >= 0 ? '+' : '') + Number(ext).toFixed(1) + ' ATR' : ''}</span></div>`;
    }).join('');
    el.querySelectorAll('.ix-cell[data-ticker]').forEach((c) => c.addEventListener('click', () => openTvPopover(c.dataset.ticker, c)));
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
      return `<span class="mv"><span class="k">${s}</span><span class="v">${v != null ? Number(v).toFixed(2) + '%' : '--'}</span>${bp != null ? `<span class="bp ${signCls(bp)}">${bp >= 0 ? '+' : ''}${Number(bp).toFixed(1)}bp</span>` : ''}</span>`;
    }).join('');
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
    const total = counted.reduce((s, a) => s + (Number(a.balance) || 0), 0);
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

    el.innerHTML = `
      <div class="book-line"><span class="k">Balance</span><span class="v">${counted.length ? fmt$(total) : '--'}${scopeKnown ? '' : ' ' + vintageChip({ unknownLabel: 'scope unknown', unknownTitle: 'this backend does not report account scope; the total is every row' })}</span></div>
      <div class="book-line"><span class="k">Day P&amp;L</span>${dayCell}</div>
      <div class="book-greeks">
        ${greekCell('Δ', 'delta', 0)}
        ${greekCell('Γ', 'gamma', 1)}
        ${greekCell('Θ', 'theta', 0)}
        ${greekCell('V', 'vega', 0)}
      </div>
      ${greekNote}
      ${conc ? `<div class="conc-lamp ${conc.hot ? 'hot' : 'ok'}" data-gloss="CONC"><span>Concentration · ${esc(conc.theme)}</span><span>${conc.pct}%</span></div>` : ''}
      <div class="acct-chips">${accts.filter((a) => a.in_scope !== false).map((a) => {
          const tag = esc((a.broker || a.account_name || '').slice(0, 4).toUpperCase());
          return `<span class="acct-chip">${tag} ${fmt$(a.balance)}</span>`;
        }).join('')}</div>`;
    applyGlossary(el);
    _openPositions = (positions && positions.positions) || [];
    renderPositions();
  }

  // ── c5: Book positions (same source as legacy Ledger: GET /api/v2/positions?status=OPEN) ──
  let _openPositions = [];
  window.__v2 = { openPositionDrawerAt: (i) => openPositionDrawer(_openPositions[i]) };
  const OPT_PUT = /put/i, OPT_CALL = /call/i;
  function structureStr(p) {
    if ((p.asset_type || '').toUpperCase() === 'EQUITY' || (p.structure || '') === 'stock') {
      return '×' + (p.quantity != null ? p.quantity : '') + ' sh';
    }
    const exp = p.expiry ? new Date(p.expiry + 'T00:00:00').toLocaleDateString('en-US', { month: '2-digit', day: '2-digit' }) : '';
    const strikes = [p.long_strike, p.short_strike].filter((x) => x != null).join('/');
    const type = OPT_PUT.test(p.structure || '') ? 'P' : OPT_CALL.test(p.structure || '') ? 'C' : '';
    const qty = p.quantity != null ? ' ×' + p.quantity : '';
    return `${exp} ${strikes}${type}${qty}`.trim();
  }
  function pnlPct(p) {
    const cb = Math.abs(Number(p.cost_basis) || 0);
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
      return { head: rows[0], rows, idx: g.idx, count: rows.length, pnl, pct,
               suspect: rows.map((r) => basisSuspect(r, pnlPct(r))).find(Boolean) || null };
    });
  }
  function renderPositions() {
    const el = $('bookPositions'); if (!el) return;
    const list = _openPositions;
    if (!list.length) { el.innerHTML = '<div class="pos-empty">no open positions</div>'; return; }
    el.innerHTML = groupPositions(list).map((g) => {
      const p = g.head;
      const pnl = g.pnl;
      const pct = g.pct;
      const dteCls = p.dte != null && p.dte <= 7 ? 'urgent' : p.dte != null && p.dte <= 14 ? 'soon' : '';
      const dteStr = p.dte != null ? p.dte + ' DTE' : (p.asset_type === 'EQUITY' ? 'equity' : '');
      const pctTxt = pct != null ? (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%' : '';
      return `<div class="pos-row" data-pi="${g.idx}">
        <span class="ptk">${esc(p.ticker)}${g.count > 1 ? `<span class="dup-count" title="${g.count} rows share this ticker, expiry and structure — the legs model decides whether that is one position or several">×${g.count}</span>` : ''}</span>
        <span class="pmid"><span class="pstruct">${esc(structureStr(p))}</span><span class="pdte ${dteCls}">${dteStr}</span></span>
        <span class="ppnl ${g.suspect ? '' : signCls(pnl)}"><span class="amt">${pnl != null ? (pnl >= 0 ? '+' : '-') + '$' + Math.abs(pnl).toFixed(0) : '--'}</span>${g.suspect ? `<span class="pct struck">${esc(pctTxt)}</span>${basisChip(g.suspect)}` : `<span class="pct">${pctTxt}</span>`}</span>
      </div>`;
    }).join('');
    el.querySelectorAll('.pos-row[data-pi]').forEach((r) => r.addEventListener('click', () => openPositionDrawer(_openPositions[+r.dataset.pi])));
  }

  async function openPositionDrawer(p) {
    if (!p) return;
    const title = $('drawerTitle'), body = $('drawerBody');
    title.textContent = p.ticker + ' · position';
    const kv = (k, v) => `<div class="kv"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`;
    const pnl = p.unrealized_pnl != null ? Number(p.unrealized_pnl) : null; const pct = pnlPct(p);
    const suspect = basisSuspect(p, pct);
    const tm = _themeMap[(p.ticker || '').toUpperCase()];
    body.innerHTML =
      kv('Structure', structureStr(p) + (p.structure ? '  (' + String(p.structure).replace(/_/g, ' ') + ')' : '')) +
      kv('Direction', p.direction || '—') + kv('Account', p.account || '—') +
      kv('Entry', p.entry_price != null ? p.entry_price : '—') + kv('Current', p.current_price != null ? p.current_price : '—') +
      kv('Stop', p.stop_loss != null ? p.stop_loss : '—') + kv('Target', p.target_1 != null ? p.target_1 : '—') +
      kv('Qty', p.quantity != null ? p.quantity : '—') + kv('DTE', p.dte != null ? p.dte : '—') +
      kv('Cost basis', p.cost_basis != null ? '$' + Number(p.cost_basis).toFixed(2) : '—') +
      kv('Max loss', p.max_loss != null ? '$' + Number(p.max_loss).toFixed(2) : '—') +
      `<div class="kv"><span class="k">Unrealized P&amp;L</span><span class="v ${suspect ? '' : signCls(pnl)}">${pnl != null ? (pnl >= 0 ? '+' : '-') + '$' + Math.abs(pnl).toFixed(2) : '—'}${pct != null ? (suspect ? ' <span class="struck">(' + (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%)</span> ' + basisChip(suspect) : ' (' + (pct >= 0 ? '+' : '') + pct.toFixed(1) + '%)') : ''}</span></div>` +
      kv('Bucket', p.bucket || '—') + kv('Theme', tm && tm.theme ? (tm.theme + (tm.inverse ? ' (inverse)' : '')) : '—') +
      '<div id="posEarn" class="kv"><span class="k">Earnings</span><span class="v">…</span></div>' +
      `<div class="drawer-actions">
         <button type="button" class="btn-danger" id="posCloseBtn">Close position</button>
         <button type="button" class="btn-secondary" id="posChartBtn">Chart</button>
       </div>`;
    $('drawerBackdrop').classList.add('open'); $('drawer').classList.add('open');
    $('posCloseBtn').addEventListener('click', () => openCloseForm(p));
    $('posChartBtn').addEventListener('click', (e) => { closeDrawer(); openTvPopover(p.ticker, e.target); });
    // Earnings surface (CHRONOS) — single earnings source from P0
    try {
      const r = await apiFetch('/api/chronos/next-earnings-batch?tickers=' + encodeURIComponent(p.ticker));
      if (r.ok) {
        const e = (await r.json()).earnings || {}; const en = e[(p.ticker || '').toUpperCase()];
        const cell = $('posEarn');
        if (cell) cell.querySelector('.v').textContent = en && en.date ? en.date + (en.timing ? ' · ' + en.timing : '') : 'none scheduled';
      }
    } catch (_) {}
  }

  // ── c5: add / close via the EXISTING write endpoints (call, never modify) ──
  const STRUCTURES = ['stock', 'long_call', 'long_put', 'call_debit_spread', 'put_debit_spread', 'call_credit_spread', 'put_credit_spread'];
  function openModal(title, html) { $('modalTitle').textContent = title; $('modalBody').innerHTML = html; $('modalBackdrop').classList.add('open'); $('posModal').classList.add('open'); }
  function closeModal() { $('modalBackdrop').classList.remove('open'); $('posModal').classList.remove('open'); }

  function openAddForm() {
    const fld = (id, label, attrs) => `<div class="fld"><label for="${id}">${label}</label><input id="${id}" ${attrs || ''}></div>`;
    openModal('Add position', `
      <div class="form-grid">
        ${fld('f_ticker', 'Ticker', 'placeholder="AAPL" autocomplete="off"')}
        <div class="fld"><label for="f_account">Account</label><select id="f_account"><option>ROBINHOOD</option><option>FIDELITY</option></select></div>
        <div class="fld"><label for="f_structure">Structure</label><select id="f_structure">${STRUCTURES.map((s) => `<option value="${s}">${s.replace(/_/g, ' ')}</option>`).join('')}</select></div>
        ${fld('f_qty', 'Quantity', 'type="number" min="1" value="1"')}
        ${fld('f_entry', 'Entry price', 'type="number" step="any" placeholder="0.00"')}
        ${fld('f_expiry', 'Expiry', 'type="date"')}
        ${fld('f_long', 'Long strike', 'type="number" step="any"')}
        ${fld('f_short', 'Short strike', 'type="number" step="any"')}
        ${fld('f_stop', 'Stop', 'type="number" step="any"')}
        ${fld('f_target', 'Target', 'type="number" step="any"')}
        <div class="fld full">${'<label for="f_notes">Notes</label><input id="f_notes" placeholder="optional">'}</div>
      </div>
      <div class="form-actions"><button type="button" class="btn-primary" id="f_submit">Create</button><button type="button" class="btn-secondary" id="f_cancel">Cancel</button></div>
      <div class="form-msg" id="f_msg"></div>`);
    $('f_cancel').addEventListener('click', closeModal);
    $('f_submit').addEventListener('click', submitAdd);
  }
  async function submitAdd() {
    const val = (id) => { const e = $(id); return e && e.value !== '' ? e.value : null; };
    const num = (id) => { const v = val(id); return v == null ? null : Number(v); };
    const ticker = (val('f_ticker') || '').toUpperCase().trim();
    const structure = val('f_structure');
    if (!ticker) { $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'Ticker is required'; return; }
    const body = {
      ticker, asset_type: structure === 'stock' ? 'EQUITY' : 'OPTION', structure,
      entry_price: num('f_entry'), quantity: parseInt(val('f_qty'), 10) || 1, source: 'MANUAL', account: val('f_account'),
    };
    if (num('f_long') != null) body.long_strike = num('f_long');
    if (num('f_short') != null) body.short_strike = num('f_short');
    if (val('f_expiry')) body.expiry = val('f_expiry');
    if (num('f_stop') != null) body.stop_loss = num('f_stop');
    if (num('f_target') != null) body.target_1 = num('f_target');
    if (val('f_notes')) body.notes = val('f_notes');
    $('f_msg').className = 'form-msg'; $('f_msg').textContent = 'saving…';
    try {
      const r = await apiFetch('/api/v2/positions', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' }, body: JSON.stringify(body) });
      if (r.ok) { $('f_msg').className = 'form-msg ok'; $('f_msg').textContent = 'created'; setTimeout(() => { closeModal(); refreshDesk(); }, 500); }
      else if (r.status === 401) { $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'sign in to add positions'; showLogin(); }
      else { const d = await r.json().catch(() => ({})); $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'failed: ' + (d.detail || r.status); }
    } catch (_) { $('f_msg').className = 'form-msg err'; $('f_msg').textContent = 'network error'; }
  }

  function openCloseForm(p) {
    const mult = (p.asset_type || '').toUpperCase() === 'EQUITY' ? 1 : 100;
    openModal('Close ' + p.ticker, `
      <div class="form-grid">
        <div class="fld"><label>Position</label><input value="${esc(p.ticker + ' · ' + structureStr(p))}" disabled></div>
        <div class="fld"><label for="c_exit">Exit price</label><input id="c_exit" type="number" step="any" placeholder="${p.current_price != null ? p.current_price : '0.00'}"></div>
        <div class="fld"><label for="c_qty">Quantity</label><input id="c_qty" type="number" min="1" value="${p.quantity != null ? p.quantity : 1}"></div>
        <div class="fld"><label for="c_reason">Reason</label><select id="c_reason"><option value="manual">manual</option><option value="profit">profit</option><option value="loss">loss</option></select></div>
        <div class="fld full"><label for="c_notes">Notes</label><input id="c_notes" placeholder="optional"></div>
      </div>
      <div class="form-actions"><button type="button" class="btn-danger" id="c_submit">Close position</button><button type="button" class="btn-secondary" id="c_cancel">Cancel</button></div>
      <div class="form-msg" id="c_msg"></div>`);
    $('c_cancel').addEventListener('click', closeModal);
    $('c_submit').addEventListener('click', () => submitClose(p, mult));
  }
  async function submitClose(p, mult) {
    const exit = $('c_exit').value !== '' ? Number($('c_exit').value) : null;
    if (exit == null) { $('c_msg').className = 'form-msg err'; $('c_msg').textContent = 'Exit price required'; return; }
    const qty = parseInt($('c_qty').value, 10) || p.quantity || 1;
    const reason = $('c_reason').value;
    const pnl = p.unrealized_pnl != null ? Number(p.unrealized_pnl) : 0;
    const body = {
      exit_price: exit, quantity: qty, exit_value: exit * mult * qty,
      trade_outcome: pnl > 0 ? 'WIN' : pnl < 0 ? 'LOSS' : 'BREAKEVEN',
      close_reason: reason, notes: $('c_notes').value || null,
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
    const byTheme = {}, invTheme = {}; let totalRisk = 0;
    list.forEach((p) => {
      const risk = Math.abs(Number(p.current_value != null ? p.current_value : (p.cost_basis != null ? p.cost_basis : p.max_loss)) || 0);
      if (!risk) return;
      const tm = _themeMap[(p.ticker || '').toUpperCase()];
      const theme = (tm && tm.theme) || 'Unmapped';
      byTheme[theme] = (byTheme[theme] || 0) + risk; totalRisk += risk;
      if (tm && tm.inverse) invTheme[theme] = (invTheme[theme] || 0) + risk;
    });
    if (!totalRisk) return null;
    let top = null;
    Object.keys(byTheme).forEach((t) => { if (!top || byTheme[t] > byTheme[top]) top = t; });
    const pct = Math.round((byTheme[top] / totalRisk) * 100);
    // Netting is deferred (post-flip): if the top theme is majority-inverse, say so rather
    // than imply long exposure. This is honest labeling, not direction-aware offsetting.
    const invHeavy = (invTheme[top] || 0) > byTheme[top] / 2;
    return { theme: top + (invHeavy ? ' (inverse)' : ''), pct, hot: pct > 50 && top !== 'Unmapped' };
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

  async function loadKairos() {
    let data = null;
    try { const r = await apiFetch('/api/trade-ideas?status=ACTIVE&limit=50'); if (r.ok) data = await r.json(); } catch (_) {}
    const el = $('kairosCards'); if (!el) return;
    const signals = (data && data.signals) || [];
    const tickers = [...new Set(signals.map((s) => (s.ticker || '').toUpperCase()).filter(Boolean))];
    let smap = {};
    if (tickers.length) { try { const r = await apiFetch('/api/stable/enrich?tickers=' + tickers.join(',')); if (r.ok) smap = (await r.json()).enrichment || {}; } catch (_) {} }
    const scoreOf = (s) => (s.adjusted_score != null ? s.adjusted_score : s.score_v2 != null ? s.score_v2 : s.score);

    // Roster gate: only display-map classes render as CARDS; everything else → River rows.
    // River-only shadow classes (R-IV.427(b)) take neither path: no card, no raw-name row.
    const roster = [], nonRoster = [], riverOnly = [];
    signals.forEach((s) => {
      const d = setupDisplay(s.codename || s.signal_type || s.strategy);
      (d.riverOnly ? riverOnly : d.roster ? roster : nonRoster).push(s);
    });
    roster.sort((a, b) => (scoreOf(b) || 0) - (scoreOf(a) || 0));

    // L-evidence for the roster cards we might show (top ~6).
    const visTickers = [...new Set(roster.slice(0, 6).map((s) => (s.ticker || '').toUpperCase()).filter(Boolean))];
    const levelMap = {};
    await Promise.all(visTickers.map(async (tk) => { try { const r = await apiFetch('/api/board/levels/' + encodeURIComponent(tk)); if (r.ok) levelMap[tk] = await r.json(); } catch (_) {} }));
    const bias = _lastRegime.composite ? (_lastRegime.composite.bias_level || '') : '';
    const biasBull = /TORO|BULL/.test(bias), biasBear = /URSA|BEAR/.test(bias);

    // Grade + evidence per roster signal; order by grade (A>B>C) then score.
    const gradeRank = { A: 3, B: 2, C: 1 };
    roster.forEach((s) => {
      const disp = setupDisplay(s.codename || s.signal_type || s.strategy);
      s._ev = evalEvidence(s, levelMap, biasBull, biasBear);
      s._grade = disp.shadow ? '—' : gradeV1(s, s._ev.litCount);
    });
    roster.sort((a, b) => (gradeRank[b._grade] || 0) - (gradeRank[a._grade] || 0) || (scoreOf(b) || 0) - (scoreOf(a) || 0));

    const visible = roster.slice(0, 3), queued = roster.length - visible.length;
    $('kairosQueued').textContent = [queued > 0 ? '+' + queued + ' queued' : null,
      nonRoster.length ? '+' + nonRoster.length + ' non-roster → river' : null].filter(Boolean).join(' · ');
    el.innerHTML = visible.length ? visible.map((s) => card(s, smap)).join('')
      : '<div class="k-card"><span class="val-muted">no roster setups' + (nonRoster.length ? ' — ' + nonRoster.length + ' non-roster in river' : '') + '</span></div>';
    applyGlossary(el);
    el.querySelectorAll('.btn-committee[data-ticker]').forEach((b) => b.addEventListener('click', () => {
      const c = b.closest('.k-card'); if (c) c.classList.add('acked');  // acknowledge -> stop the decision-clock pulse
      openCommittee(b.dataset.ticker, b.dataset.sig);
    }));
    el.querySelectorAll('.k-card .tkr[data-ticker]').forEach((t) => t.addEventListener('click', () => openTvPopover(t.dataset.ticker, t)));

    // River: roster cards as signal items + every non-roster class as a plain row under its raw name.
    addRiverItems(visible.map((s) => signalRiverItem(s, smap)));
    addRiverItems(nonRoster.map((s) => nonRosterRiverItem(s)));
    addRiverItems(riverOnly.map((s) => signalRiverItem(s, smap)));
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
      return `<div class="k-card${shadow ? ' shadow' : ''}">
        <div class="top"><span class="nm">${esc(disp.name)}</span><span class="desc">${esc(disp.desc)}</span>
          <span class="grade ${grade === 'A' ? 'val-up' : ''}" data-gloss="GRADE">${grade}</span></div>
        <div class="lvls"><span class="tkr" data-ticker="${esc(s.ticker)}">${esc(s.ticker)}</span>
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
  function openCommittee(ticker, sig) {
    openDrawer('committee', { ticker, sig });
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
      ts: s.timestamp ? Date.parse(s.timestamp) : (s.created_at ? Date.parse(s.created_at) : Date.now()),
      riverOnly: !!disp.riverOnly,
      text: `<b>${esc(disp.name)}</b> ${esc(s.ticker)} ${side}${s.entry_price != null ? ' @ ' + Number(s.entry_price).toFixed(2) : ''}${grade ? ' · grade ' + grade : ''}`
        + (disp.banner ? `<div class="rv-banner">${esc(disp.banner)}</div>` : ''),
    };
  }
  // Non-roster classes never render as Kairos cards — they surface here under their raw name.
  function nonRosterRiverItem(s) {
    const raw = s.signal_type || s.strategy || 'SETUP';
    const side = (s.direction || '').toUpperCase();
    return {
      id: 'nr:' + (s.signal_id || raw + (s.ticker || '')), type: 'signal', tier: 'info',
      sev: side === 'LONG' ? 'up' : side === 'SHORT' ? 'down' : null,
      ts: s.timestamp ? Date.parse(s.timestamp) : (s.created_at ? Date.parse(s.created_at) : Date.now()),
      text: `<span class="rv-raw">${esc(raw)}</span> ${esc(s.ticker)} ${side}${s.entry_price != null ? ' @ ' + Number(s.entry_price).toFixed(2) : ''} <span class="val-muted">· non-roster</span>`,
    };
  }
  function emitRegimeRiverItems(composite, regime, kill) {
    // stable-vs-composite divergence
    if (composite && regime) {
      const c100 = to100(composite.composite_score);
      const rl = regime.regime_label;
      const cDir = c100 == null ? 0 : c100 >= 55 ? 1 : c100 <= 45 ? -1 : 0;
      const sDir = rl === 'RISK-ON' ? 1 : rl === 'RISK-OFF' ? -1 : 0;
      if (cDir && sDir && cDir !== sDir) {
        addRiverItems([{ id: 'div:' + rl + ':' + cDir, type: 'regime', tier: 'action', sev: 'teal', ts: Date.now(),
          text: `<b>Lens divergence</b> — Composite ${c100}/100 vs Stable ${esc(rl)}. Size with caution.` }]);
      }
    }
    const k = kill && kill.kill_switch;
    if (k && k.active) {
      addRiverItems([{ id: 'kill:' + (k.trigger || '') + ':' + (k.triggered_at || ''), type: 'regime', tier: 'action', sev: 'down', ts: k.triggered_at ? Date.parse(k.triggered_at) : Date.now(),
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
          tier: f.strength === 'STRONG' ? 'action' : 'info', sev: align === 'CONFIRMING' ? 'up' : 'down', ts: Date.now(),
          text: `<b>${esc(f.ticker || '')}</b> flow ${align.toLowerCase()}${f.strength ? ' (' + esc(f.strength.toLowerCase()) + ')' : ''} vs your position` });
      });
      (flow.watchlist_unusual || []).slice(0, 5).forEach((w, i) => {
        items.push({ id: 'unusual:' + (w.ticker || i), type: 'flow', tier: 'info', sev: 'teal', ts: Date.now(),
          text: `Unusual flow · <b>${esc(w.ticker || '')}</b>${w.sentiment ? ' ' + esc(w.sentiment) : ''}` });
      });
      (flow.headlines || []).slice(0, 6).forEach((h, i) => {
        const hl = h.headline || h.title || ''; if (!hl) return;
        items.push({ id: 'hl:' + hl.slice(0, 40), type: 'headline', tier: 'info', sev: null,
          ts: h.created_at ? Date.parse(h.created_at) : Date.now(), text: esc(hl) });
      });
    }
    if (hermes) {
      (hermes.alerts || []).forEach((a) => {
        items.push({ id: 'herm:' + (a.id || a.trigger_ticker), type: 'catalyst',
          tier: (a.tier <= 1 ? 'action' : 'info'), sev: 'down', ts: a.created_at ? Date.parse(a.created_at) : Date.now(),
          text: `<b>${esc(a.trigger_ticker || '')}</b> ${esc(a.headline_summary || a.event_type || 'catalyst')}` });
      });
    }
    // Cowork stable digest (optional — render only if present)
    try {
      const r = await _rawFetch('/stable_digest.md', { cache: 'no-store' });
      if (r.ok) {
        const txt = (await r.text()).trim();
        if (txt && txt[0] !== '<') items.push({ id: 'stable:digest', type: 'stable', tier: 'info', sev: 'teal', ts: Date.now(), text: '<b>Stable digest</b> · ' + esc(txt.split('\n')[0].slice(0, 160)) });
      }
    } catch (_) {}
    addRiverItems(items);
    renderRiver();
  }
  function renderRiver() {
    const el = $('riverStream'); if (!el) return;
    let items = [..._river.values()];
    if (_riverFilter !== 'all') items = items.filter((i) => i.type === _riverFilter);
    items.sort((a, b) => (b.ts || 0) - (a.ts || 0));
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
    const noticeRows = activeNotices(Date.now()).map((n) =>
      `<div class="rv-notice" data-nid="${esc(n.id)}">`
      + (n.title ? `<span class="rv-notice-t">${esc(n.title)}</span>` : '')
      + (n.body ? `<span class="rv-notice-b">${esc(n.body)}</span>` : '')
      + '</div>').join('');
    const countRow = circeToday && (_riverFilter === 'all' || _riverFilter === 'signal')
      ? `<div class="rv-count${circeToday > CIRCE_DAILY_CEILING ? ' over' : ''}">CIRCE'S STEW · SHADOW · ${circeToday} seen today (ET)`
        + (circeToday > CIRCE_DAILY_CEILING ? ` — above the ~${CIRCE_DAILY_CEILING}/day ceiling: the trigger is too loose (R-IV.421(d))` : '') + '</div>'
      : '';
    if (!items.length) { el.innerHTML = noticeRows + countRow + '<div class="rv-item info"><span class="rv-txt val-muted">stream quiet</span></div>'; return; }
    el.innerHTML = noticeRows + countRow + items.map((it) => {
      const t = new Date(it.ts || Date.now());
      const hh = isNaN(t) ? '' : t.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const acked = _rvAcked.has(it.id);
      const pulse = acked ? '' : (it.sev === 'down' ? ' pulse-vermilion' : it.sev === 'up' ? ' pulse-lime' : ' pulse-teal');
      const cls = it.tier === 'action' ? 'action sev-' + (it.sev === 'up' ? 'up' : it.sev === 'down' ? 'down' : 'teal') + pulse + (acked ? ' acked' : '') : it.tier;
      return `<div class="rv-item ${cls}" data-rid="${esc(it.id)}"><div class="rv-head"><span class="rv-dot t-${it.type}"></span><span class="rv-type">${it.type}</span><span class="rv-time">${hh}</span></div><div class="rv-txt">${it.text}</div></div>`;
    }).join('');
    // Click an action item to acknowledge — stops its pulse (nothing pulses forever).
    el.querySelectorAll('.rv-item.action[data-rid]').forEach((n) => n.addEventListener('click', () => { _rvAcked.add(n.dataset.rid); renderRiver(); }));
  }

  // ── Popup helpers ───────────────────────────────────────────────────────────
  function openPopup(title, html) { $('memberTitle').textContent = title; $('memberBody').innerHTML = html; $('popupBackdrop').classList.add('open'); $('memberPopup').classList.add('open'); }
  function closePopup() { $('popupBackdrop').classList.remove('open'); $('memberPopup').classList.remove('open'); }

  // ── Polling groups (idle interval budget: 4 << 10) ──────────────────────────
  function refreshMarket() { loadThemes(); loadDivergence(); loadIndexStrip(); loadRates(); loadFx(); }
  async function refreshDesk() {
    let positions = null;
    try { const r = await apiFetch('/api/v2/positions?status=OPEN'); if (r.ok) positions = await r.json(); } catch (_) {}
    await refreshThemeMap(positions);
    loadBook(); loadKairos(); loadDeskStreams(); loadNotices();
  }

  // ── Boot ────────────────────────────────────────────────────────────────────
  function boot() {
    applyGlossary(document);
    initGrid();
    loadRegimeBand(); managedInterval(loadRegimeBand, 60 * 1000);
    loadMoversTape(); managedInterval(loadMoversTape, 5 * 60 * 1000);
    refreshMarket(); managedInterval(refreshMarket, 60 * 1000);
    refreshDesk(); managedInterval(refreshDesk, 2 * 60 * 1000);
    // divergence window toggle
    const dt = $('divToggle');
    if (dt) dt.querySelectorAll('button[data-w]').forEach((b) => b.addEventListener('click', () => {
      _divWindow = b.dataset.w; dt.querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b)); loadDivergence();
    }));
    // divergence isolation: delegate on the container — chips are destroyed and rebuilt on
    // every refresh, so per-chip listeners would be lost and re-added each cycle.
    const dl = $('divLegend');
    if (dl) dl.addEventListener('click', (e) => {
      const chip = e.target.closest('.div-chip'); if (!chip) return;
      if (chip.dataset.all) _divClear(); else _divToggle(chip.dataset.sym);
    });
    $('drawerClose').addEventListener('click', closeDrawer);
    $('drawerBackdrop').addEventListener('click', closeDrawer);
    $('tvPopClose').addEventListener('click', closeTvPopover);
    $('memberClose').addEventListener('click', closePopup);
    $('popupBackdrop').addEventListener('click', closePopup);
    $('bookAdd').addEventListener('click', openAddForm);
    $('modalClose').addEventListener('click', closeModal);
    $('modalBackdrop').addEventListener('click', closeModal);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeDrawer(); closeTvPopover(); closePopup(); closeModal(); _divClear(); } });
    try { window.__mgd = _managed.size; } catch (_) {}  // idle interval count (acceptance check)
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot);
  else boot();
})();

/* Positions panel, R-IV.509. A slide-over on Agora, MOCK DATA ONLY until BUILD's backend scope is ruled (R-IV.511(d)).
   One panel: layout B on desktop, layout C on phone. */
(function () {
  'use strict';
const PM = {
  label: 're-derived 09-23',
  sleeves: [
    // mock figures. RH ceiling ~10% of (FIDELITY_ROTH + ROBINHOOD), $200 always in cash.
    // FIDELITY_ROTH's cap: max losses within 20% of its own balance.
    { account: 'ROBINHOOD', kind: 'options sleeve', rule: 'ceiling ≈ 10% of combined balance', measure: 'at risk', ceiling: 968, atRisk: 412, cashFloor: 200, cash: 223.69, balance: 835.69 },
    { account: 'FIDELITY_ROTH', kind: 'equity sleeve', rule: 'cap: max losses within 20% of its balance', measure: 'max loss', ceiling: 1768, atRisk: 1210, cashFloor: null, cash: 1980.0, balance: 8842.09 },
  ],
  open: [
    { id: 517, account: 'ROBINHOOD', ticker: 'AVGO', bucket: 'B2 tactical', structure: 'put debit spread 300/290', qty: 2, cost: 148, mark: 171, markState: 'fresh', prov: 'BROKER_VERIFIED', expiry: '2026-10-16',
      stop: { type: 'daily-close', level: 'close < 305' }, invalidation: 'Daily close above 312 voids the bearish read', timeStop: '09-29 (5 days, B2 window)', tags: ['semis', 'committee'],
      lots: [{ id: 1, when: '09-22 10:41', qty: 2, price: 0.74, fees: 1.30, prov: 'BROKER_VERIFIED', ref: 'RH-…7f2a' }],
      legs: [{ seq: 1, side: 'long', type: 'put', strike: 300, price: 3.10 }, { seq: 2, side: 'short', type: 'put', strike: 290, price: 2.36 }],
      evidence: ['Broker fill 09-22 10:41: BUY 2 AVGO 10/16 300P @3.10, SELL 2 290P @2.36 (broker_ref RH-…7f2a)', 'Cost check: (3.10 − 2.36) × 2 × 100 = 148.00, matches recorded basis'] },
    { id: 519, account: 'ROBINHOOD', ticker: 'TSLA', bucket: 'B2 tactical', structure: 'put debit spread 260/250', qty: 1, cost: 96, mark: null, markState: 'unknown', prov: 'SCREEN_VERIFIED', expiry: '2026-10-16',
      stop: { type: 'none', level: '—' }, invalidation: 'not written', timeStop: 'not set', tags: [],
      lots: [{ id: 2, when: '09-22 11:05', qty: 1, price: 0.96, fees: 0.65, prov: 'SCREEN_VERIFIED', ref: '—' }],
      legs: [{ seq: 1, side: 'long', type: 'put', strike: 260, price: null }, { seq: 2, side: 'short', type: 'put', strike: 250, price: null }],
      evidence: ['Read from a broker screen (fields + capture time recorded); no fill reference yet', 'Export line will supersede this and promote it to BROKER_VERIFIED'] },
    { id: 520, account: 'ROBINHOOD', ticker: 'NVDA', bucket: 'B1 thesis', structure: '3-leg put fly 415', qty: 1, cost: 168, mark: 121, markState: 'stale', prov: 'PRINCIPAL_REPORTED', expiry: '2026-11-20', basisIncomplete: 'quantity 3, basis covers 2 structures; third has no recorded fill',
      stop: { type: 'broker order', level: 'stop @ 60% of debit' }, invalidation: 'Thesis dead if NVDA reclaims 430 on volume', timeStop: '11-06', tags: ['thesis'],
      lots: [{ id: 3, when: '09-15', qty: 1, price: 1.68, fees: 0, prov: 'PRINCIPAL_REPORTED', ref: '—' }],
      legs: [{ seq: 1, side: 'long', type: 'put', strike: 425, price: null }, { seq: 2, side: 'short', type: 'put', strike: 415, price: null }, { seq: 3, side: 'long', type: 'put', strike: 405, price: null }],
      evidence: ['Basis incomplete by ruling — counted in the census, never averaged into realized or win rate'] },
    { id: 516, account: 'ROBINHOOD', ticker: 'HYG', bucket: 'HEDGE', structure: 'put debit spread 76/73', qty: 5, cost: 70, mark: 96, markState: 'fresh', prov: 'BROKER_VERIFIED', expiry: '2026-11-20', rolledFrom: 218,
      stop: { type: 'daily-close', level: 'close < 77.2' }, invalidation: 'Credit spreads tighten below 3.1', timeStop: '11-13',
      tags: ['credit', 'roll'],
      lots: [{ id: 4, when: '09-22 09:58', qty: 3, price: 0.14, fees: 0.9, prov: 'BROKER_VERIFIED', ref: 'RH-…1c90' }, { id: 5, when: '09-22 10:02', qty: 2, price: 0.13, fees: 0.6, prov: 'BROKER_VERIFIED', ref: 'RH-…1c91' }],
      legs: [{ seq: 1, side: 'long', type: 'put', strike: 76, price: 0.58 }, { seq: 2, side: 'short', type: 'put', strike: 73, price: 0.39 }],
      evidence: ['Roll: closed #218 (−110.00) and opened #516 in one motion', 'Roll cost 30.00 recorded on lot 1 only'] },
    { id: 601, account: 'FIDELITY_ROTH', ticker: 'PDBC', bucket: 'CORE', structure: 'equity', qty: 50, cost: 690, mark: 702, markState: 'fresh', prov: 'BROKER_VERIFIED', expiry: null,
      stop: { type: 'daily-close', level: 'close < 13.2' }, invalidation: 'Commodity sleeve breaks its 200-day', timeStop: 'none (holding)', tags: ['commodity'],
      lots: [{ id: 6, when: '09-01', qty: 50, price: 13.80, fees: 0, prov: 'BROKER_VERIFIED', ref: 'FID-…22b0' }], legs: [],
      evidence: ['Fidelity confirmation 09-01: BUY 50 PDBC @13.80'] },
    { id: 602, account: 'FIDELITY_ROTH', ticker: 'SOXS', bucket: 'HEDGE', structure: 'equity', qty: 25, cost: 420, mark: 391, markState: 'fresh', prov: 'BROKER_VERIFIED', expiry: null,
      stop: { type: 'broker order', level: 'stop @ 14.40' }, invalidation: 'Semis trend resumes: SMH closes above its 20-day', timeStop: 'review when SMH resets', tags: ['semis', 'inverse'],
      lots: [{ id: 7, when: '09-10', qty: 25, price: 16.80, fees: 0, prov: 'BROKER_VERIFIED', ref: 'FID-…31c4' }], legs: [],
      evidence: ['Fidelity confirmation 09-10: BUY 25 SOXS @16.80'] },
  ],
  history: {
    coverage: { total: 8, counted: 6, excluded: { basis_incomplete: 1, return_below_neg100pct: 1, no_realized_pnl: 0 } },
    rows: [
      { id: 480, ticker: 'QQQ', structure: 'call debit spread', closed: '09-19', realized: 74.0, prov: 'BROKER_VERIFIED', why: 'target' },
      { id: 471, ticker: 'SPY', structure: 'put debit spread', closed: '09-17', realized: -52.0, prov: 'BROKER_VERIFIED', why: 'stop' },
      { id: 465, ticker: 'XLF', structure: 'call debit spread', closed: '09-12', realized: 31.0, prov: 'SCREEN_VERIFIED', why: 'time stop' },
      { id: 452, ticker: 'ORCL', structure: 'put debit spread', closed: '09-09', realized: -88.0, prov: 'BROKER_VERIFIED', why: 'stop' },
      { id: 447, ticker: 'SOXS', structure: 'equity', closed: '09-08', realized: 19.0, prov: 'IMPORTED', why: 'target' },
      { id: 440, ticker: 'UVXY', structure: 'call', closed: '09-05', realized: -40.0, prov: 'BROKER_VERIFIED', why: 'expired' },
      { id: 433, ticker: 'NVDA', structure: '3-leg put fly', closed: '09-03', realized: null, prov: 'PRINCIPAL_REPORTED', why: 'basis under review', flag: 'basis incomplete' },
      { id: 429, ticker: 'IBIT', structure: 'put debit spread', closed: '09-02', realized: -190.0, prov: 'IMPORTED', why: 'return past −100% of basis', flag: 'return < −100%' },
    ],
    chains: [
      { label: 'HYG roll chain', legs: [{ id: 218, closed: '09-22', realized: -110.0 }, { id: 516, open: true }], net: -110.0, note: 'reads as ONE trade: roll cost 30.00 on lot 1, chain result −110.00 so far' },
    ],
  },
  buckets: [['B1 thesis','multi-week'],['B2 tactical','3–5 days'],['B3 scalp','intraday'],['CORE',''],['HEDGE',''],['TAIL','']],
  ladder: ['UNKNOWN','PRINCIPAL_REPORTED','SCREEN_VERIFIED','IMPORTED','BROKER_VERIFIED'],
  ticket: {
    tape: { state: 'DOWN', detail: 'SPY below 20-day, breadth 38%' },
    fields: ['tape vs trade direction', 'bucket', 'max loss vs caps', 'stop written', 'invalidation', 'time stop', 'Zweig rule strained'],
  },
  missing: [
    'roll route (R-IV.452, not landed) — Roll button shows disabled state',
    'stop type / invalidation / time stop / bucket have no columns (bucket lives inside notes text)',
    'pre-trade ticket has no route or storage: X8 needs fields on the position row',
    'sleeve ceiling and cash floor have no read endpoint (figures here are mock)',
    'evidence lines are stored as prose in notes; a structured list needs a source',
  ],
};

const X = (function () {
  const P = PM;
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const MINUS = '−';
  const usd = (v, signed) => v == null ? '—' : (v < 0 ? MINUS : (signed && v > 0 ? '+' : '')) + '$' + Math.abs(v).toLocaleString('en-US', { minimumFractionDigits: v % 1 ? 2 : 0, maximumFractionDigits: 2 });
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
  const ladder = () => `<div class="pp-ladder">Provenance, weakest to strongest: ${P.ladder.map((k) => prov(k)).join(' <span class="pp-dim">&lt;</span> ')}</div>`;
  const buckets = () => `<div class="pp-ladder">Buckets: ${P.buckets.map(([n, d]) => `<span class="pp-tag">${esc(n)}${d ? ' · ' + esc(d) : ''}</span>`).join(' ')}</div>`;
  const mockBanner = () => `<div class="pp-banner">Mock data — layout only · ${esc(P.label)} · every figure is invented, the principal approves or adjusts the layout</div>${ladder()}${buckets()}`;

  function markCell(p) {
    if (p.mark == null) return `<span class="pp-amber" title="no mark: the source could not price this position">UNAVAILABLE</span>`;
    const v = usd(p.mark);
    return p.markState === 'stale' ? `${v} ${chip('unknown', 'stale mark', 'Mark is older than its bound; cannot confirm it is current.')}` : v;
  }
  function pnlCell(p) {
    if (p.mark == null) return `<span class="pp-amber">—</span>`;
    if (p.basisIncomplete) return `<span class="pp-amber" title="${esc(p.basisIncomplete)}">basis under review</span>`;
    const d = p.mark - p.cost; return `<span class="${tone(d)}">${usd(d, true)}</span>`;
  }

  function gauge(s) {
    const scale = Math.max(s.ceiling, s.atRisk) * 1.15;
    const pct = (v) => Math.min(100, (v / scale) * 100).toFixed(1);
    const headroom = s.ceiling - s.atRisk;
    const floor = s.cashFloor != null;
    const cashOk = !floor || s.cash >= s.cashFloor;
    return `<div class="pp-gauge" role="img" aria-label="${esc(s.account)}: ${esc(s.measure)} ${usd(s.atRisk)} of ${usd(s.ceiling)}${floor ? '; cash ' + usd(s.cash) + ' against a ' + usd(s.cashFloor) + ' floor' : ''}">
      <div class="pp-g-head"><span class="pp-g-name">${esc(s.account)} <span class="pp-dim">${esc(s.kind)}</span> ${chip('unknown', 'mock', 'Invented figures')}</span>
        <span class="pp-g-fig">${usd(s.atRisk)} ${esc(s.measure)} of ${usd(s.ceiling)} · headroom <b class="${headroom < 0 ? 'pp-down' : ''}">${usd(headroom)}</b></span></div>
      <div class="pp-dim">${esc(s.rule)}</div>
      <div class="pp-g-track"><i class="pp-g-fill" style="width:${pct(s.atRisk)}%"></i><b class="pp-g-ceil" style="left:${pct(s.ceiling)}%" title="limit ${usd(s.ceiling)}"></b></div>
      <div class="pp-g-foot"><span>${floor ? `Cash ${usd(s.cash)} vs $200 always-in-cash floor ${cashOk ? chip('verified', 'above floor') : chip('reported', 'BELOW FLOOR')}` : `Cash ${usd(s.cash)}`}</span><span class="pp-dim">balance ${usd(s.balance)}</span></div>
    </div>`;
  }

  function stopBadge(st) {
    const map = { 'broker order': 'verified', 'daily-close': 'screen', none: 'reported' };
    const note = { 'broker order': 'Rests at the broker; fires on its own.', 'daily-close': 'Watched at the close; fires only if someone acts.', none: 'No stop written.' };
    return chip(map[st.type] || 'reported', st.type === 'none' ? 'no stop' : 'stop: ' + st.type, note[st.type]) + (st.level && st.level !== '—' ? ` <span class="pp-dim">${esc(st.level)}</span>` : '');
  }

  function bookRow(p, attrs) {
    return `<tr class="pp-row" ${attrs || ''} data-id="${p.id}">
      <td><b>${esc(p.ticker)}</b><div class="pp-dim">${esc(p.bucket)}</div></td>
      <td>${esc(p.structure)}${p.expiry ? `<div class="pp-dim">exp ${esc(p.expiry.slice(5))}</div>` : ''}</td>
      <td class="pp-num">${p.qty}</td><td class="pp-num">${usd(p.cost)}</td><td class="pp-num">${markCell(p)}</td>
      <td class="pp-num">${pnlCell(p)}</td><td>${prov(p.prov)}</td></tr>`;
  }
  const bookHead = `<thead><tr><th>Position</th><th>Structure</th><th class="pp-num">Qty</th><th class="pp-num">Cost</th><th class="pp-num">Mark</th><th class="pp-num">P&amp;L</th><th>Provenance</th></tr></thead>`;
  function bookTable(account, rowAttrs) {
    const rows = P.open.filter((p) => p.account === account);
    return `<table class="pp-table">${bookHead}<tbody>${rows.map((p) => bookRow(p, rowAttrs ? rowAttrs(p) : '')).join('')}</tbody></table>`;
  }

  function detail(p) {
    const lots = p.lots.map((l) => `<tr><td>${esc(l.when)}</td><td class="pp-num">${l.qty}</td><td class="pp-num">${l.price.toFixed(2)}</td><td class="pp-num">${l.fees.toFixed(2)}</td><td>${prov(l.prov)}</td><td class="pp-dim">${esc(l.ref)}</td></tr>`).join('');
    const legs = p.legs.length ? p.legs.map((g) => `<tr><td>${g.seq}</td><td>${esc(g.side)}</td><td>${esc(g.type)}</td><td class="pp-num">${g.strike}</td><td class="pp-num">${g.price == null ? '<span class="pp-amber">unpriced</span>' : g.price.toFixed(2)}</td></tr>`).join('') : '';
    return `<div class="pp-detail">
      <h3>${esc(p.ticker)} · ${esc(p.structure)} ${prov(p.prov)}</h3>
      ${p.basisIncomplete ? `<div class="pp-note pp-warn">Basis under review — ${esc(p.basisIncomplete)}</div>` : ''}
      <div class="pp-kv">
        <div><span class="pp-k">Stop</span>${stopBadge(p.stop)}</div>
        <div><span class="pp-k">Time stop</span>${esc(p.timeStop)}</div>
        <div class="pp-wide"><span class="pp-k">Invalidation</span>${p.invalidation === 'not written' ? '<span class="pp-amber">not written</span>' : esc(p.invalidation)}</div>
        <div class="pp-wide"><span class="pp-k">Tags</span>${p.tags.length ? p.tags.map((t) => `<span class="pp-tag">${esc(t)}</span>`).join(' ') : '<span class="pp-dim">none</span>'}</div>
      </div>
      <h4>Lots</h4><table class="pp-table pp-sm"><thead><tr><th>When</th><th class="pp-num">Qty</th><th class="pp-num">Price</th><th class="pp-num">Fees</th><th>Provenance</th><th>Ref</th></tr></thead><tbody>${lots}</tbody></table>
      ${legs ? `<h4>Legs</h4><table class="pp-table pp-sm"><thead><tr><th>#</th><th>Side</th><th>Type</th><th class="pp-num">Strike</th><th class="pp-num">Price</th></tr></thead><tbody>${legs}</tbody></table>` : ''}
      <h4>Evidence <span class="pp-dim">(beside the verdict, #23)</span></h4><ul class="pp-evid">${p.evidence.map((e) => `<li>${esc(e)}</li>`).join('')}</ul>
    </div>`;
  }

  function actions(p) {
    const rolled = p.rolledFrom ? ` (follows #${p.rolledFrom})` : '';
    const A = [
      ['Edit', 'Change tags, stop, invalidation, time stop.', 'Needs: what changed and why (one line).', false],
      ['Add a lot', 'Record another fill into this position.', 'Needs: fill time, qty, price, fees — and a broker reference or a screen capture.', false],
      ['Close', 'End the position and record the result.', 'Needs: exit price, close time, and the closing fill reference (or screen capture). Result recomputed from lots.', false],
      ['Roll' + rolled, 'Close this and open the next as one linked trade.', 'Needs: both fills, linked. Waits on R-IV.452 — not landed.', true],
    ];
    return `<div class="pp-actions"><h4>Actions on ${esc(p.ticker)} #${p.id}</h4>${A.map(([n, d, need, off]) => `<div class="pp-act${off ? ' off' : ''}"><button type="button" class="pp-btn" ${off ? 'disabled' : ''}>${esc(n)}</button><div><div>${esc(d)}</div><div class="pp-need">${esc(need)}</div></div></div>`).join('')}</div>`;
  }

  function ticket() {
    const t = P.ticket;
    return `<form class="pp-ticket" onsubmit="return false"><h4>Pre-trade ticket <span class="pp-dim">— the only way a new position enters (X8)</span></h4>
      <div class="pp-tape">Tape: ${chip('reported', t.tape.state)} <span class="pp-dim">${esc(t.tape.detail)}</span></div>
      <label>Trade direction<select><option>bearish (with the tape)</option><option>bullish (AGAINST the tape)</option><option>neutral</option></select></label>
      <label>Bucket<select>${P.buckets.map(([n, d]) => `<option>${esc(n)}${d ? ' — ' + esc(d) : ''}</option>`).join('')}</select></label>
      <label>Ticker / structure<input value="e.g. IWM put debit spread 215/210"></label>
      <label>Max loss<input value="$120"></label>
      <div class="pp-caps">${chip('verified', 'within sleeve ceiling: headroom $556 (mock)')} ${chip('verified', 'cash stays above $200 (mock)')}</div>
      <label>Stop written<select><option>broker order</option><option>daily-close</option><option>none — say why</option></select></label>
      <label>Invalidation<input value="what makes this wrong"></label>
      <label>Time stop<input value="date or DTE"></label>
      <label>Zweig rule strained<select><option>none</option><option>the tape sets direction</option><option>another rule…</option></select></label>
      <div class="pp-need">A ticket saves onto the position row. A trade against the tape, or with no stop, shows amber above and asks for a reason before it can be submitted.</div>
      <button type="button" class="pp-btn primary">Save ticket (mock: saves nothing)</button></form>`;
  }

  function history() {
    const h = P.history, c = h.coverage;
    const ex = c.excluded, flagged = ex.basis_incomplete + ex.return_below_neg100pct + ex.no_realized_pnl;
    const counted = h.rows.filter((r) => !r.flag && r.realized != null);
    const net = counted.reduce((s, r) => s + r.realized, 0);
    const wins = counted.filter((r) => r.realized > 0).length;
    const cov = chip(flagged ? 'reported' : 'verified', `n=${c.counted} of ${c.total}`, `${flagged} excluded, never averaged in: ${ex.basis_incomplete} basis incomplete, ${ex.return_below_neg100pct} return past −100% of basis`);
    const rows = h.rows.map((r) => `<tr class="${r.flag ? 'pp-flagged' : ''}"><td>#${r.id}</td><td><b>${esc(r.ticker)}</b> <span class="pp-dim">${esc(r.structure)}</span></td><td>${esc(r.closed)}</td><td class="pp-num">${r.realized == null ? '<span class="pp-amber">null</span>' : `<span class="${tone(r.realized)}">${usd(r.realized, true)}</span>`}</td><td>${esc(r.why)}${r.flag ? ' ' + chip('reported', r.flag) : ''}</td><td>${prov(r.prov)}</td></tr>`).join('');
    const chain = h.chains.map((k) => `<div class="pp-chain"><b>${esc(k.label)}</b> — ${k.legs.map((l) => l.open ? `#${l.id} <span class="pp-dim">open</span>` : `#${l.id} ${usd(l.realized, true)}`).join(' → ')} · <span class="${tone(k.net)}">${usd(k.net, true)}</span> <span class="pp-dim">${esc(k.note)}</span></div>`).join('');
    return `<div class="pp-history"><h4>History <span class="pp-dim">closed &amp; expired, windowed on close date</span></h4>
      <div class="pp-hstats"><span>Realized <b class="${tone(net)}">${usd(net, true)}</b> ${cov}</span><span>Win rate <b>${Math.round(wins / counted.length * 100)}%</b> <span class="pp-dim">n=${counted.length}</span> ${cov}</span></div>
      ${chain}<table class="pp-table"><thead><tr><th>#</th><th>Position</th><th>Closed</th><th class="pp-num">Realized</th><th>Why</th><th>Provenance</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }

  function missing() {
    return `<details class="pp-missing"><summary>Endpoints and fields found missing (${P.missing.length})</summary><ul>${P.missing.map((m) => `<li>${esc(m)}</li>`).join('')}</ul>
      <div class="pp-dim">Exist today: list, summary, single, lots (list/add), legs (list/add/edit), verify / screen-verify, close, reduce, patch, correct-realized, closed-from-evidence.</div></details>`;
  }

  return { ladder, buckets, esc, usd, prov, chip, mockBanner, gauge, bookTable, bookRow, bookHead, detail, actions, ticket, history, missing, sleeves: P.sleeves, open: P.open };
})();

  // ── Panel ────────────────────────────────────────────────────────────────
  const mq = window.matchMedia('(max-width: 820px)');
  const st = { open: false, id: null, tab: 'Detail', mtab: 'Book', card: null, actions: false, note: null, live: null, opener: null };
  let backdrop = null, panel = null;
  const TABS = ['Detail', 'Actions', 'New', 'History'];
  const MTABS = ['Book', 'New', 'History'];
  const byId = (id) => X.open.find((p) => p.id === Number(id)) || null;
  const hashFor = () => '#positions' + (st.id ? '/' + st.id : '') + (st.id && st.tab !== 'Detail' ? '/' + st.tab.toLowerCase() : '');
  function readHash() {
    const m = /^#positions(?:\/(\d+))?(?:\/(detail|actions|new|history))?$/.exec(location.hash || '');
    if (!m) return null;
    const p = m[1] ? byId(m[1]) : null;
    const tab = m[2] ? m[2][0].toUpperCase() + m[2].slice(1) : 'Detail';
    return { id: p ? p.id : null, tab };
  }
  function setHash(replace) {
    const h = hashFor(), url = location.pathname + location.search + h;
    if (location.hash === h) return;
    history[replace ? 'replaceState' : 'pushState'](null, '', url);
  }
  function build() {
    if (panel) return;
    backdrop = document.createElement('div'); backdrop.className = 'pp-backdrop';
    panel = document.createElement('aside'); panel.className = 'pp-panel';
    panel.setAttribute('role', 'dialog'); panel.setAttribute('aria-modal', 'true'); panel.setAttribute('aria-label', 'Positions (mock data)');
    document.body.appendChild(backdrop); document.body.appendChild(panel);
    backdrop.addEventListener('click', close);
    panel.addEventListener('click', onPanelClick);
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && st.open) close(); });
    mq.addEventListener('change', () => { if (st.open) render(); });
  }
  function head() {
    return `<div class="pp-head"><h2>Positions</h2>${X.chip('unknown', 'mock', 'Every figure here is invented')}<span class="pp-dim">skeleton · no live data</span><button type="button" class="pp-x" aria-label="Close positions panel">✕</button></div>
      <div class="pp-banner">Mock data — a working skeleton. Nothing here is your book. The roll action stays disabled until R-IV.452 lands.</div>
      ${st.note ? `<div class="pp-note pp-warn">${X.esc(st.note)}${st.live != null ? ` <button type="button" class="pp-btn pp-link" data-live="${st.live}">Open the live detail</button>` : ''}</div>` : ''}`;
  }
  function legend() { return `<details class="pp-legend"><summary>Legend: provenance ladder and buckets</summary>${X.ladder()}${X.buckets()}</details>`; }
  function desktop() {
    const sel = byId(st.id);
    const none = '<div class="pp-dim">Pick a row.</div>';
    const pane = st.tab === 'Detail' ? (sel ? X.detail(sel) : none) : st.tab === 'Actions' ? (sel ? X.actions(sel) : none) : st.tab === 'New' ? X.ticket() : X.history();
    const books = X.sleeves.map((s) => `<div class="pp-card"><h3 class="pp-h">${X.esc(s.account)} · open</h3><div class="pp-scroll">${X.bookTable(s.account)}</div></div>`).join('');
    return `<div class="pp-split"><div class="pp-left">${X.sleeves.map(X.gauge).join('')}${books}</div>
      <div class="pp-side pp-card"><div class="pp-tabs" role="tablist">${TABS.map((t) => `<button type="button" role="tab" aria-selected="${t === st.tab}" data-tab="${t}">${t === 'New' ? 'New (ticket)' : t}</button>`).join('')}</div>${pane}</div></div>${legend()}${X.missing()}`;
  }
  function card(p) {
    const on = st.card === p.id;
    return `<div class="pp-pcard" data-card="${p.id}"><header><span><b>${X.esc(p.ticker)}</b> <span class="pp-dim">${X.esc(p.bucket)} · ${X.esc(p.structure)}</span></span>${X.prov(p.prov)}</header>
      <div class="pp-line"><span>qty ${p.qty} · cost ${X.usd(p.cost)}</span><span>mark ${p.mark == null ? '<span class="pp-amber">UNAVAILABLE</span>' : X.usd(p.mark)}</span></div>
      ${on ? `<div class="pp-sheet">${X.detail(p)}<div style="margin-top:8px"><button type="button" class="pp-btn" data-toggle-actions="1">${st.actions ? 'Hide actions' : 'Actions'}</button></div>${st.actions ? X.actions(p) : ''}</div>` : ''}</div>`;
  }
  function phone() {
    const v = st.mtab === 'Book' ? X.sleeves.map((s) => X.gauge(s) + X.open.filter((p) => p.account === s.account).map(card).join('')).join('')
      : st.mtab === 'New' ? `<div class="pp-card">${X.ticket()}</div>` : `<div class="pp-card">${X.history()}</div>`;
    return `<div class="pp-tabs" role="tablist">${MTABS.map((t) => `<button type="button" role="tab" aria-selected="${t === st.mtab}" data-mtab="${t}">${t === 'New' ? 'New (ticket)' : t}</button>`).join('')}</div>${v}${legend()}${X.missing()}`;
  }
  function render() {
    if (!panel) return;
    const prev = panel.querySelector('.pp-body');
    const keepTop = prev ? prev.scrollTop : 0;
    panel.innerHTML = head() + `<div class="pp-body">${mq.matches ? phone() : desktop()}</div>`;
    panel.querySelectorAll('tr.pp-row').forEach((r) => r.classList.toggle('sel', Number(r.dataset.id) === st.id));
    const body = panel.querySelector('.pp-body'); if (body) body.scrollTop = keepTop;
  }
  function onPanelClick(e) {
    const t = e.target;
    if (t.closest('.pp-x')) return close();
    const live = t.closest('[data-live]');
    if (live) { const fn = window.__v2 && window.__v2.openPositionDrawerAt; if (fn) { close(); fn(Number(live.dataset.live)); } return; }
    const tab = t.closest('[data-tab]');
    if (tab) { st.tab = tab.dataset.tab; setHash(true); return render(); }
    const mtab = t.closest('[data-mtab]');
    if (mtab) { st.mtab = mtab.dataset.mtab; return render(); }
    if (t.closest('[data-toggle-actions]')) { st.actions = !st.actions; return render(); }
    const tr = t.closest('tr.pp-row');
    if (tr) { st.id = Number(tr.dataset.id); if (st.tab === 'New' || st.tab === 'History') st.tab = 'Detail'; setHash(true); return render(); }
    const c = t.closest('.pp-pcard');
    if (c && !t.closest('.pp-sheet')) { const id = Number(c.dataset.card); st.card = st.card === id ? null : id; st.id = st.card; st.actions = false; setHash(true); return render(); }
  }
  function show(opts) {
    build();
    st.open = true;
    st.note = opts.note || null; st.live = opts.live != null ? opts.live : null;
    if (opts.id != null) { st.id = opts.id; st.card = opts.id; }
    if (opts.tab) st.tab = opts.tab;
    if (!st.id && !mq.matches) st.id = X.open[0].id;
    if (mq.matches && opts.id != null) st.mtab = 'Book';
    render();
    requestAnimationFrame(() => { backdrop.classList.add('open'); panel.classList.add('open'); const x = panel.querySelector('.pp-x'); if (x) x.focus(); });
  }
  function open(opts, push) {
    opts = opts || {};
    st.opener = document.activeElement;
    show(opts);
    if (push !== false) setHash(false);
  }
  function hide() {
    st.open = false;
    if (backdrop) { backdrop.classList.remove('open'); panel.classList.remove('open'); }
    if (st.opener && st.opener.focus) { try { st.opener.focus(); } catch (_) {} }
  }
  function close() {
    if (!st.open) return;
    hide();
    if (/^#positions/.test(location.hash)) history.pushState(null, '', location.pathname + location.search);
  }
  function sync() {
    const h = readHash();
    if (h) { if (!st.open) show({ id: h.id, tab: h.tab }); else { st.id = h.id; st.tab = h.tab; render(); } }
    else if (st.open) hide();
  }
  // The doorway: the Book strip, or a row in it. Capture phase, so it precedes the live drawer's own row handler.
  function realTicker(row) { const n = row.querySelector('.ptk'); return n && n.firstChild ? String(n.firstChild.textContent || '').trim().toUpperCase() : ''; }
  document.addEventListener('click', (e) => {
    const row = e.target.closest && e.target.closest('#bookPositions .pos-row');
    if (row) {
      e.preventDefault(); e.stopPropagation();
      const tk = realTicker(row), m = X.open.find((p) => p.ticker === tk);
      open(m ? { id: m.id } : { note: (tk || 'That position') + ' is not in the mock data. This skeleton shows invented positions only.', live: row.dataset.pi != null ? Number(row.dataset.pi) : null });
      return;
    }
    if (e.target.closest && e.target.closest('#bookStrip')) { e.preventDefault(); open({}); }
  }, true);
  document.addEventListener('keydown', (e) => {
    if (e.target && e.target.id === 'bookStrip' && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); open({}); }
  });
  window.addEventListener('popstate', sync);
  window.addEventListener('hashchange', sync);
  function init() {
    const strip = document.getElementById('bookStrip');
    if (strip) { strip.setAttribute('tabindex', '0'); strip.setAttribute('role', 'button'); strip.setAttribute('aria-label', 'Open the positions panel (mock data)'); strip.classList.add('pp-door'); }
    const pos = document.getElementById('bookPositions'); if (pos) pos.classList.add('pp-door');
    sync();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
