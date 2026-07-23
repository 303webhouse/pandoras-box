# STATER SWAP v2 (S-6) — MOCKUP CONCEPT PLAN

**Authored:** 2026-07-22, coordination lane
**For:** `docs/strategy-reviews/stater-swap-redesign/helios-mockup-track.md` — pass one of the HELIOS gate
**Status:** design plan complete. **Rendering pending — execute in a fresh session with full budget.**
**Gate requirement:** ≥3 rendered concepts → Nick reaction pass → iterate → sign-off recorded → *then* S-6 brief may be authored.

---

## THE BRIEF, PINNED

**Subject:** the crypto trading surface for a solo full-time trader on a prop-firm account, covering six symbols across three tiers on a 24/7 tape partitioned into ASIA / LONDON / NY sessions.

**Audience:** one person. ADHD. Typically at the screen around 6:30–7:30 MDT with coffee, and from 2026-08-04 to 08-15 on a phone with no ability to deploy code.

**The page's single job:** *Is there a trade right now, and does discipline permit it?*

That is a **go/no-go surface, not a data browse.** Every concept below is judged on how fast it answers that question, not on how much it displays.

---

## CONSTRAINT THAT SHAPES EVERYTHING: THIS IS A PORT

S-6 ports Stater Swap into the **existing Agora v2 design system.** The palette, type scale, chip and drawer patterns are **inherited, not chosen.** A concept that invents a new visual language fails the gate on arrival.

**So the three concepts differ in layout philosophy, not in aesthetics.** That is the real decision in front of Nick, and collapsing it into a palette choice would waste the gate.

Rendering note for the next session: pull the actual tokens from `frontend/v2.html` and `frontend/v2.js` before drawing. Do not invent hex values — the regime band, chip, and drawer patterns already exist and the concepts should visibly reuse them.

---

## SURFACE INVENTORY (all seven required in each concept)

1. **Regime header** — regime label + CTA zone
2. **Tape-health strip** — SPOT_LED / PERP_LED / MIXED, spot vs perp CVD split
3. **Signal feed** — crypto signals as they fire
4. **Cycle Extremes single-axis dial** — ⚠️ **S-5, not yet built.** Render as an honest seam, not a stub
5. **Collapsed macro band** — funding, OI, basis, liquidations
6. **Discipline chips** — session, concurrent-position count, daily cap, distance-to-floor
7. **Six-symbol switcher** with a full Tier-3 FARTCOIN view

**Two seams every concept must show honestly rather than paper over:**

- **`breakout_prop` is invisible.** Distance-to-floor cannot be computed. It renders as *unavailable with a reason*, never as a zero or a full ring.
- **FARTCOIN degrades per-block.** Its basis and liquidations return `null`/degraded while funding, OI, regime, and tape are fine. **This is the hardest state in the whole surface and it is the real test of each layout.** Any concept that can only show a symbol as wholly healthy or wholly broken has failed.

---

## THE THREE CONCEPTS

### C1 — COMMAND RAIL · *symbol-first*

Persistent left rail carries the six-symbol switcher; the body is a single scrolling column for the selected symbol. Regime header pinned at top, tape-health strip beneath it, signal feed below, macro band collapsed by default.

**Mental model:** pick a symbol, read it top to bottom.

**Signature element — per-symbol health dots in the rail.** Each of the six entries carries a small cluster encoding block-level health, so FARTCOIN's degraded basis and liquidations are visible *before* you click into it. Degradation becomes navigational information rather than a surprise on arrival.

**Strong at:** deep single-symbol work; pre-session orientation; showing per-block degradation honestly, which is the hardest requirement.
**Weak at:** cross-symbol comparison — "where's the action" costs six clicks.

---

### C2 — COCKPIT GRID · *scan-first*

All six symbols visible at once as a 2×3 grid of compact cards, each carrying its own regime, tape state, and cycle position. Detail opens in the existing v2 drawer pattern.

**Mental model:** see the whole book, then drill.

**Signature element — the distance-to-floor ring** on each card, tying every symbol back to the one constraint that governs all of them. **Which currently renders as an empty ring with a reason, because `breakout_prop` is invisible** — making the concept's own signature element the most honest possible statement of the system's current limitation.

**Strong at:** fastest "where is anything happening"; genuinely six-symbol rather than one-at-a-time.
**Weak at:** small cards make per-block degradation hard to show without clutter — FARTCOIN is the stress case. Worst of the three on a phone.

---

### C3 — TAPE-FIRST · *event-first*

The signal feed **is** the page. Everything else collapses around it: regime and cycle compress to a thin always-visible band, the six-symbol switcher becomes filter chips on the feed itself, macro opens on demand.

**Mental model:** you are not browsing state, you are waiting for something to fire.

**Signature element — session-partition gutters.** Visible ASIA / LONDON / NY bands running down the feed's timeline, so you can see at a glance which session produced which signals. Specific to crypto's 24/7 tape, and it makes a genuine property of this market visible in a way no equity surface needs to.

**Strong at:** active-session monitoring; **by far the best of the three on a phone**, which matters directly for 08-04 → 08-15.
**Weak at:** poor for pre-session orientation — a quiet tape shows you an empty page.

---

## THE DECISION IN FRONT OF NICK

Not "which looks best" but **which failure mode you can live with:**

| | C1 Command Rail | C2 Cockpit Grid | C3 Tape-First |
|---|---|---|---|
| Answers *"is there a trade?"* | slowly, thoroughly | fastest | only when one exists |
| Cross-symbol scan | 6 clicks | native | filter chips |
| Per-block degradation (FARTCOIN) | **best** | worst | adequate |
| Phone, 08-04 → 08-15 | adequate | **worst** | **best** |
| Pre-session orientation | **best** | good | **worst** |

**A hybrid is legitimate and likely** — C1's rail health dots and C3's session gutters are not mutually exclusive. Say so during the reaction pass rather than picking one whole.

---

## RENDERING INSTRUCTIONS FOR THE NEXT SESSION

1. Read `frontend/v2.html` and `frontend/v2.js` for the real tokens — palette, type scale, chip and drawer patterns. **Do not invent styling.**
2. Render all three as frames in one Figma file, `Stater Swap v2 — Concepts`, so they can be compared side by side.
3. **Populate with real live values, not lorem.** BTC funding 0.0100 NEUTRAL · OI $2.10B, divergence none · basis −2.68% · liquidations $11.17M, 32.8% long, balanced · regime CHOP · tape PERP_LED (spot CVD +13,893 / perp CVD −14,696,028) · cta_zone CAPITULATION. Session NY. Post-fix POC: BTC 65,973 · ETH 1,922 · SOL 77.17 · HYPE 58.55 · ZEC 512.63 · FARTCOIN 0.14 (precision-blocked).
4. **Render FARTCOIN's degraded state in every concept.** It is the acceptance test, not an edge case.
5. **Render distance-to-floor as unavailable-with-reason** in every concept. Never a zero, never a filled ring.
6. Record the file link in `helios-mockup-track.md` with the date, and mark the concept-session prerequisite satisfied.

---

## AFTER THE REACTION PASS

Sign-off recorded in the track file → S-6 brief authored → Titans final review → CC build → **post-deploy screenshot comparison against the approved mockup.**

HELIOS holds a standing veto on that final comparison. It is not optional, and per his Pass 2 position, S-6 either deploys by **2026-07-31** with the comparison on **08-03**, or it does not deploy this window — an unverified UI should not sit unaccepted through an 11-day no-code period.
