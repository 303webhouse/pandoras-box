/* TV (R-IV.1371(e), R-IV.1440, default since R-IV.1444). Loaded by v2.html's loader on a desktop unless
 * the page carries ?tv=off.
 *
 * One tile in the square Nick cleared in Agora's top-right corner (columns 9-11, rows 0-11 of the
 * 12-column grid). It places itself only if that square is EMPTY and never moves another tile; if
 * the square is taken it says so on the layout status line and stays out.
 *
 * 1. Official live streams that play without an account, embedded through youtube-nocookie.com,
 *    muted, with a switcher. Each entry is the channel's OWN live stream (owner checked 10-25:
 *    "Bloomberg Television" UCIALMKvObZNtJ6AmdCLP7Lg, "Yahoo Finance" UCEAZeUIeJs0IjQiqTCdVSIg). By
 *    video id: Bloomberg's channel-wide live_stream embed answers "This video is unavailable", so a
 *    restarted stream means a new id here.
 * 2. CNBC and Fox Business: YouTube TV sends X-Frame-Options: SAMEORIGIN and needs a sign-in, so it
 *    cannot be embedded. Their buttons open YouTube TV in a small window placed over this tile. The
 *    per-channel tv.youtube.com address can't be read signed out, so each button opens YouTube TV's
 *    live guide until a channel's own address is pasted once ("link"); that is kept in this browser.
 * 3. Muted, no autoplay with sound, desktop only (also hidden by CSS at Agora's 768px breakpoint).
 * The tile is locked (no move, no resize) and v2.js leaves it out of the saved layout row.
 */
(function () {
  'use strict';
  var STREAMS = [
    { key: 'bloomberg', label: 'Bloomberg', owner: 'Bloomberg Television', video: 'QB5BNdBFujE' },
    { key: 'yahoo', label: 'Yahoo Finance', owner: 'Yahoo Finance', video: 'KQp-e_XQnDE' },
  ];
  var YTV = [{ key: 'cnbc', label: 'CNBC' }, { key: 'fbn', label: 'Fox Business' }];
  var YTV_GUIDE = 'https://tv.youtube.com/live';
  var YTV_RE = /^https:\/\/tv\.youtube\.com\/[^\s"'<>]*$/;
  var AREA = { x: 9, y: 0, w: 3, h: 12 };
  var PHONE = window.matchMedia('(max-width: 768px)');

  function get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } }
  function put(k, v) {
    try { if (v == null) localStorage.removeItem(k); else localStorage.setItem(k, v); } catch (_) { /* per-view only */ }
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function stream() {
    var k = get('tv.stream');
    return STREAMS.filter(function (s) { return s.key === k; })[0] || STREAMS[0];
  }
  function src(s) {
    return 'https://www.youtube-nocookie.com/embed/' + encodeURIComponent(s.video)
      + '?autoplay=1&mute=1&playsinline=1&rel=0';
  }
  function status(text) { var el = document.getElementById('layoutStatus'); if (el) el.textContent = text; }

  var tile = null, frame = null;

  function setStream(s) {
    put('tv.stream', s.key);
    if (frame && !PHONE.matches) frame.src = src(s);
    if (frame) frame.title = s.owner + ' live stream';
    var line = tile && tile.querySelector('.tv-src');
    if (line) line.textContent = 'Official live stream: ' + s.owner + ' on YouTube · muted, unmute in the player';
    Array.prototype.forEach.call(tile ? tile.querySelectorAll('[data-tv-s]') : [], function (b) {
      var on = b.getAttribute('data-tv-s') === s.key;
      b.classList.toggle('on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
  }

  // A small separate window over this tile: the tile's own rectangle, in screen coordinates.
  function openYtv(key) {
    var url = get('tv.ytv.' + key) || YTV_GUIDE;
    var r = tile.getBoundingClientRect();
    var left = Math.round(window.screenX + Math.max(0, window.outerWidth - window.innerWidth) / 2 + r.left);
    var top = Math.round(window.screenY + Math.max(0, window.outerHeight - window.innerHeight) + r.top);
    var w = window.open(url, 'pandora-ytv', 'popup=yes,width=' + Math.round(r.width) + ',height='
      + Math.round(r.height) + ',left=' + left + ',top=' + top);
    if (w) { try { w.opener = null; } catch (_) { /* already cross-origin */ } }
  }

  function setLink(key, label) {
    var cur = get('tv.ytv.' + key) || '';
    var v = window.prompt('Paste ' + label + '’s address from YouTube TV (it starts with https://tv.youtube.com/).'
      + ' Leave it empty to go back to the live guide.', cur);
    if (v == null) return;
    v = v.trim();
    if (!v) { put('tv.ytv.' + key, null); paintLinks(); return; }
    if (!YTV_RE.test(v)) { window.alert('Not saved: only a https://tv.youtube.com/ address is accepted.'); return; }
    put('tv.ytv.' + key, v);
    paintLinks();
  }
  function paintLinks() {
    YTV.forEach(function (c) {
      var b = tile.querySelector('[data-tv-y="' + c.key + '"]');
      if (!b) return;
      b.title = get('tv.ytv.' + c.key)
        ? 'Opens ' + c.label + ' on YouTube TV (your saved link) in a small window over this tile'
        : 'Opens YouTube TV’s live guide in a small window over this tile; pick ' + c.label
          + ' there, or save its address with “link”';
    });
  }

  function build() {
    var el = document.createElement('div');
    el.className = 'grid-stack-item';
    el.setAttribute('gs-id', 'tv');
    el.innerHTML = '<div class="grid-stack-item-content"><div class="tile tv-tile">'
      + '<div class="tile-header"><span class="tile-title">TV</span>'
      + '<span class="spacer"></span><span class="tv-sw" role="group" aria-label="live stream">'
      + STREAMS.map(function (x) {
          return '<button type="button" class="tv-b" data-tv-s="' + esc(x.key) + '">' + esc(x.label) + '</button>';
        }).join('') + '</span></div>'
      + '<div class="tile-body pad-0 tv-body">'
      + '<div class="tv-frame"><iframe allow="autoplay; encrypted-media; picture-in-picture; fullscreen"'
      + ' allowfullscreen referrerpolicy="strict-origin-when-cross-origin"></iframe></div>'
      + '<div class="tv-src"></div>'
      + '<div class="tv-ytv"><span class="tv-ytv-h">YouTube TV · opens a small window</span>'
      + YTV.map(function (c) {
          return '<span class="tv-yrow"><button type="button" class="tv-b" data-tv-y="' + c.key + '">' + esc(c.label)
            + ' ↗</button><button type="button" class="tv-link" data-tv-l="' + c.key + '">link</button></span>';
        }).join('') + '</div>'
      + '</div></div></div>';
    tile = el;
    frame = el.querySelector('iframe');
    Array.prototype.forEach.call(el.querySelectorAll('[data-tv-s]'), function (b) {
      b.addEventListener('click', function () {
        setStream(STREAMS.filter(function (x) { return x.key === b.getAttribute('data-tv-s'); })[0]);
      });
    });
    YTV.forEach(function (c) {
      el.querySelector('[data-tv-y="' + c.key + '"]').addEventListener('click', function () { openYtv(c.key); });
      el.querySelector('[data-tv-l="' + c.key + '"]').addEventListener('click', function () { setLink(c.key, c.label); });
    });
    setStream(stream());
    paintLinks();
    return el;
  }

  function place(grid) {
    if (!grid || tile || PHONE.matches || grid.getColumn() !== 12) return;
    if (!grid.isAreaEmpty(AREA.x, AREA.y, AREA.w, AREA.h)) {
      status('TV not placed: the top-right square is taken');
      return;
    }
    // GridStack 11: append, then makeWidget (the two-argument addWidget(el, opts) form is gone).
    var el = build();
    grid.el.appendChild(el);
    grid.makeWidget(el, { x: AREA.x, y: AREA.y, w: AREA.w, h: AREA.h, id: 'tv',
      noMove: true, noResize: true, locked: true });
  }

  // Narrowed to phone width: CSS hides the tile, and the stream stops instead of playing unseen.
  PHONE.addEventListener('change', function () {
    if (!frame) return;
    if (PHONE.matches) frame.removeAttribute('src');
    else frame.src = src(stream());
  });

  if (window.__agoraGrid) place(window.__agoraGrid);
  else document.addEventListener('agora:grid-ready', function (e) { place(e.detail && e.detail.grid); }, { once: true });
})();
