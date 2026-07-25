# Component — Pandora mobile deck bar

**Canonical source for the shared bottom deck bar.** One component, two lanes, zero drift.

- **Owner:** Mobile Shell lane (`docs/codex-briefs/2026-07-24-brief-pandora-mobile-shell.md`, T1.4)
- **Consumers:** `frontend/v2.html` + `frontend/v2.css` (Agora), `frontend/index.html` + `frontend/styles.css` (legacy/Abacus), and — after 2026-08-03 — `frontend/stater.html` + `frontend/stater.css` via the **S-6M** lane.
- **Rule:** copy this verbatim. If it needs to change, change it *here* first, then propagate to every consumer in the same commit.

## Why it is duplicated rather than imported

The three surfaces load three separate stylesheets and share no build step (vanilla JS PWA, no bundler). A shared file would mean a fourth `<link>` and a fourth cache-bust axis on every page. Duplication with one written-down canonical copy is the cheaper correct answer at this size.

The CSS uses `var(--token, fallback)` throughout **because the consumers do not share a token vocabulary** — `v2.css` defines `--panel-2`/`--border`/`--teal`/`--text-3`/`--mono`, `styles.css` does not. The fallbacks are load-bearing on the legacy page; do not strip them.

## Markup

Place immediately before the closing `</body>`, after all page content.

```html
<!-- Mobile deck bar — canonical source: docs/components/pandora-deck-bar.md -->
<nav class="deck-bar" aria-label="Decks">
  <a class="deck-tab" href="/app"><span class="deck-ico" aria-hidden="true">◧</span><span>Agora</span></a>
  <a class="deck-tab" href="/app/stater"><span class="deck-ico" aria-hidden="true">◈</span><span>Stater</span></a>
  <a class="deck-tab" href="/app/analytics"><span class="deck-ico" aria-hidden="true">▤</span><span>Abacus</span></a>
</nav>
<script>
  /* Active-tab state from the real path. No framework, no derived hrefs. */
  (function () {
    var p = window.location.pathname;
    Array.prototype.forEach.call(document.querySelectorAll('.deck-bar .deck-tab'), function (a) {
      var href = a.getAttribute('href');
      var on = href === '/app' ? (p === '/app' || p === '/app/v2') : p.indexOf(href) === 0;
      a.classList.toggle('is-active', on);
      if (on) { a.setAttribute('aria-current', 'page'); } else { a.removeAttribute('aria-current'); }
    });
  })();
</script>
```

## CSS

```css
/* Deck bar — mobile only. Canonical source: docs/components/pandora-deck-bar.md */
.deck-bar { display: none; }

@media (max-width: 768px) {
  .deck-bar {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 90;
    display: flex; align-items: stretch;
    background: var(--panel-2, #0d152b);
    border-top: 1px solid var(--border, #1b2745);
    /* Clears the iPhone home indicator. Requires viewport-fit=cover on the page's
       viewport meta, or this resolves to 0 and the bar sits under the indicator. */
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }
  .deck-tab {
    flex: 1 1 0; min-height: 52px;
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px;
    text-decoration: none; color: var(--text-3, #5b6b85);
    font-family: var(--mono, ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace);
    font-size: 10px; letter-spacing: 1.4px; text-transform: uppercase;
    border-top: 2px solid transparent;
  }
  .deck-tab .deck-ico { font-size: 15px; line-height: 1; }
  .deck-tab.is-active {
    color: var(--teal, #14b8a6);
    border-top-color: var(--teal, #14b8a6);
    background: rgba(20, 184, 166, 0.07);
  }
  .deck-tab:active { background: rgba(20, 184, 166, 0.12); }
}
```

## Per-consumer integration requirements

Each consumer must do **all three**, or the bar is broken in a way that is easy to miss:

1. **`viewport-fit=cover`** on the page's viewport meta:
   `<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">`
   Without it `env(safe-area-inset-bottom)` is `0` and the bar sits under the home indicator.

2. **Content-occlusion reserve** on the page's scroll container, inside a `max-width: 768px` media query — the bar is `position: fixed`, so it occludes the last element otherwise:
   ```css
   padding-bottom: calc(64px + env(safe-area-inset-bottom, 0px));
   ```
   Applied to `.v2-page` in `v2.css` and `.container` in `styles.css`.

3. **Cache-bust** the page's CSS and JS `?v=` on every change to this component.

## Known temporary gap (time-boxed, do not "fix" out of lane)

`stater.html` has no bar until the **S-6M** lane lands it after its 2026-08-03 SG-3 comparison. Navigating Agora → Stater is therefore **one-way** on a phone: the Stater surface has no way back except the browser's back gesture. This is accepted and deliberate — the Mobile Shell brief writes nothing to `stater.html`/`stater.css` in any phase (Ruling 8). When S-6M adds the bar, this note is retired.

## Route constraint (standing)

The three hrefs are **hardcoded on purpose**. Do not derive them from `window.location` or reuse `app.js`'s `buildModePath()` — on `/app/legacy` that helper emits two-segment paths like `/app/legacy/analytics`, which the single-segment `/app/{mode}` route cannot match and which return **404 on reload**.

Any *future* deck route must be declared **above** the `/app/{mode}` catch-all in `backend/main.py` (currently line 1864), or FastAPI swallows it and serves the legacy dashboard with a 200 — a silent wrong-page failure.
