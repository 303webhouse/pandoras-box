# Brief: Committee-Approved Signal Pulse Animation

**Date:** 2026-04-22
**Priority:** P2 (quality-of-life + ADHD-aware UX improvement)
**Target:** Claude Code (VSCode)
**Estimated effort:** 45-60 min
**Origin:** Nick's request — ADHD-brain benefits from pre-attentive visual cues. Currently there's no at-a-glance distinction between committee-approved high-conviction signals and everything else on the Insights feed. Pulse animation on qualifying signal cards fixes this.

---

## Requirements

### Trigger logic

A signal card should pulse if ALL are true:
1. Committee has completed its run (`committee_data` exists and is non-null)
2. PIVOT conviction ≥ B+ (i.e., grade in {A+, A, A-, B+})
3. PIVOT action is directional (LONG or SHORT — not WATCHING, SKIP, or DISMISSED)
4. Signal is still ACTIVE in the feed (not EXPIRED, DISMISSED, ACCEPTED)

### Visual spec

- **Color:**
  - LONG signals: emerald-green glow (reuse existing `--accent-long` CSS var or `#10b981`)
  - SHORT signals: rose/red glow (`--accent-short` or `#f43f5e`)
- **Animation:** 2-second sine-wave pulse, ease-in-out, infinite
- **Max glow intensity:** 12-14px `box-shadow` blur at peak, fading to 0 at trough
- **Min glow intensity:** 0 (full fade-out each cycle — makes the card "breathe" rather than just ripple)
- **Outline width:** 2px, subtle
- **Border:** optional complementary 1px solid border in same color at constant low opacity (15%), so card has a baseline tint even at trough

### Accessibility

- Must respect `prefers-reduced-motion: reduce` — if user has this OS setting, fall back to static 1px border + subtle background tint instead of animated glow. No motion, but still visually distinguished.
- Pulse should NOT prevent hover / click states — all other interactive styles must still work.

### Performance

- CSS-only animation (no JavaScript timer loops)
- Use `animation-play-state: paused` when page visibility hidden (tab not in focus) to save GPU — attach to `document.visibilitychange` listener OR use `page-visibility` CSS media query if supported
- Ensure animation runs on GPU-accelerated property (`box-shadow` + `border-color` both work; avoid animating `width`/`height`/`top`/`left`)

---

## Implementation

### CSS (add to existing `app.js` inline styles or dedicated stylesheet)

```css
@keyframes committeePulseLong {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(16, 185, 129, 0);
    border-color: rgba(16, 185, 129, 0.15);
  }
  50% {
    box-shadow: 0 0 12px 2px rgba(16, 185, 129, 0.55);
    border-color: rgba(16, 185, 129, 0.85);
  }
}

@keyframes committeePulseShort {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(244, 63, 94, 0);
    border-color: rgba(244, 63, 94, 0.15);
  }
  50% {
    box-shadow: 0 0 12px 2px rgba(244, 63, 94, 0.55);
    border-color: rgba(244, 63, 94, 0.85);
  }
}

.insight-card.committee-approved-long {
  border: 1px solid rgba(16, 185, 129, 0.15);
  animation: committeePulseLong 2s ease-in-out infinite;
  animation-play-state: running;
}

.insight-card.committee-approved-short {
  border: 1px solid rgba(244, 63, 94, 0.15);
  animation: committeePulseShort 2s ease-in-out infinite;
}

/* Pause when tab hidden */
@media (document: hidden) {
  .insight-card.committee-approved-long,
  .insight-card.committee-approved-short {
    animation-play-state: paused;
  }
}

/* Reduced motion fallback */
@media (prefers-reduced-motion: reduce) {
  .insight-card.committee-approved-long {
    animation: none;
    border: 1.5px solid rgba(16, 185, 129, 0.6);
    background-color: rgba(16, 185, 129, 0.04);
  }
  .insight-card.committee-approved-short {
    animation: none;
    border: 1.5px solid rgba(244, 63, 94, 0.6);
    background-color: rgba(244, 63, 94, 0.04);
  }
}
```

### JS trigger logic (in `app.js`, inside the signal-card render function)

```javascript
// When rendering each signal card, determine pulse class
function getCommitteeApprovedClass(signal) {
  if (!signal.committee_data) return '';
  
  const conviction = signal.committee_data.pivot?.conviction || signal.committee_data.conviction;
  const action = signal.committee_data.pivot?.action || signal.committee_data.action;
  
  const QUALIFYING_CONVICTIONS = ['A+', 'A', 'A-', 'B+'];
  if (!QUALIFYING_CONVICTIONS.includes(conviction)) return '';
  
  if (action === 'LONG' || action === 'BUY') return 'committee-approved-long';
  if (action === 'SHORT' || action === 'SELL') return 'committee-approved-short';
  
  return '';  // WATCHING, SKIP, etc — no pulse
}

// In the card render:
const pulseClass = getCommitteeApprovedClass(signal);
const cardClass = `insight-card ${pulseClass}`;
// ... use cardClass in the element
```

### Optional: add a small "Committee ✓" badge inside pulsing cards

Reinforces the reason for the pulse — useful for the first 1-2 weeks while you build intuition around what the pulse means.

```javascript
const committeeBadge = pulseClass 
  ? `<span class="committee-badge">✓ Olympus ${conviction}</span>`
  : '';
```

---

## Open questions for Nick (NON-blocking — CC can ship with defaults)

1. **Should WATCHING/SKIP committee outputs get a different visual?** Default: no pulse, but maybe a muted gray border? If not, they look identical to un-reviewed signals, which obscures that committee actually ran. Default: add a subtle 1px solid gray-40 border to "committee-ran-but-not-actionable" cards.
2. **B+ threshold correct, or should it be B?** Currently B+. If too few cards qualify over first week, relax to B.
3. **Tier intensity by grade?** v1 is binary (pulse or not). v2 could vary pulse intensity by grade — A+ gets maximum glow, B+ gets subtle glow. Ship v1 first, evaluate later.

---

## Verification

1. Deploy change
2. Open Insights feed with at least one committee-approved LONG signal at B+ or higher — card should pulse green
3. Test with SHORT signal — should pulse red
4. Test with WATCHING or LOW-conviction committee output — should NOT pulse
5. Test with pre-committee signal (no `committee_data`) — should NOT pulse
6. Open OS system settings, enable "reduce motion," reload — pulse should be replaced with static border/tint
7. Open two browser tabs, watch performance — non-focused tab should have animation paused

---

## Out of scope

- Notification sound / haptic when new pulse appears (noise discipline rule from memory)
- Mobile-specific pulse adjustments (can iterate after v1)
- Pulsing the entire Insights column header when new committee-approved signals arrive (cool idea but separate brief)

---

## Done when

- [ ] CSS keyframes added, tied to signal-card class
- [ ] `getCommitteeApprovedClass()` helper written and called in render
- [ ] Reduced-motion fallback works (tested via OS setting or devtools emulation)
- [ ] Tab-hidden pause works (verified via `requestAnimationFrame` counter or visual check)
- [ ] Manual test passes for all 4 scenarios above
- [ ] No regressions on other signal card styles (hover, click, existing borders)
