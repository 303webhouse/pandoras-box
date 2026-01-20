# Pandora's Box - To-Do List

## Aesthetic & Quality of Life Improvements
**No backend structure changes required**

### Custom Signal Icons
- [ ] **APIS CALL** icon
  - Design: Bright lime green (#7CFF6B)
  - Theme: Bullish/upward momentum
  - Style: Dark teal aesthetic, modern, scalable SVG
  
- [ ] **BULLISH TRADE** icon
  - Design: Darker green (#4CAF50)
  - Theme: Moderate bullish
  - Style: Matches app palette
  
- [ ] **KODIAK CALL** icon
  - Design: Bright orange (#FF6B35)
  - Theme: Bearish/downward momentum
  - Style: Bold, powerful bear symbolism
  
- [ ] **BEAR CALL** icon
  - Design: Darker orange (#FF8C42)
  - Theme: Moderate bearish
  - Style: Subtle bear theme

**Implementation**: Drop SVG files into `frontend/assets/icons/` and reference in CSS

---

### Pandora's Box Logo
- [ ] Custom logo design
  - Color palette: Dark teal + lime/orange accents
  - Style: Modern, tech-forward
  - Formats needed: SVG (scalable), PNG (192x192, 512x512 for PWA)
  - Placement: Header, PWA icon, favicon

**Implementation**: Replace placeholder in `frontend/index.html` header

---

### UI Polish
- [ ] Add loading skeletons for signal cards
- [ ] Smooth scroll animations
- [ ] Toast notifications for signal actions
- [ ] Confetti animation on trade selection (optional fun)
- [ ] Dark mode toggle (currently fixed dark theme)
- [ ] Customizable accent colors in settings

---

### Mobile Optimization
- [ ] Haptic feedback on button presses (iOS/Android)
- [ ] Swipe-to-dismiss gesture for signals
- [ ] Pull-to-refresh on signal lists
- [ ] Bottom navigation bar for easier thumb reach
- [ ] Landscape mode optimization for tablets

---

### User Experience
- [ ] Onboarding tutorial for first-time users
- [ ] Keyboard shortcuts (desktop)
- [ ] Signal preview tooltip on hover
- [ ] Watchlist quick-edit modal
- [ ] Export positions to CSV
- [ ] Share signals via link/QR code

---

### Performance Monitoring
- [ ] Display latency metrics in footer
- [ ] Signal processing time badge
- [ ] WebSocket connection quality indicator
- [ ] Backend health dashboard

---

## Notes
- All items above can be implemented without touching backend Python code
- Focus is on visual polish and UX refinement
- Priority: Icons > Logo > UI Polish > Mobile > UX > Monitoring
