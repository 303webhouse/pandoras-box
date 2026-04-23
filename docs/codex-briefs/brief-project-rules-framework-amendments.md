# PROJECT_RULES.md Framework Amendments — CC Brief

**Type:** DOCUMENTATION UPDATE
**Target file:** `PROJECT_RULES.md` (repo root)
**Estimated runtime:** 5–10 min
**Output:** Updated PROJECT_RULES.md committed to main

---

## 1. Purpose

Olympus committee review of the Raschke Strategy Evaluation (2026-04-22) ratified the anti-bloat framework with 7 amendments. These amendments govern all future strategy additions, Olympus reviews, and Titans briefs. They must be added to `PROJECT_RULES.md` so CC inherits them in every session without needing to re-read the Olympus review each time.

---

## 2. Task

Add the following section to `PROJECT_RULES.md`. Place it under an existing "Strategy Design" or "Signal System" heading if one exists. If not, create a new top-level section titled **"Strategy Anti-Bloat Framework (Olympus-Ratified 2026-04-22)"** and place it near the top of the file — these rules have equal weight to core project conventions.

**If PROJECT_RULES.md has a table of contents, update it accordingly.**

---

## 3. Content to Add (copy verbatim, preserve markdown)

```markdown
## Strategy Anti-Bloat Framework (Olympus-Ratified 2026-04-22)

All proposed strategy additions, Olympus reviews, and Titans briefs must comply with these rules. Source: `docs/strategy-reviews/raschke/olympus-review-2026-04-22.md` Pass 1 consensus.

### Core Classification

Every candidate strategy must be classified as one of:

- **REPLACES** — deprecates an existing signal
- **ELEVATES** — becomes a filter/gate on top of an existing signal
- **ADDS** — genuinely orthogonal edge (requires backtest proof)
- **REJECTED** — no clean case for inclusion

### Confluence Caps

- **Cash factors:** maximum of 3 per setup (ADX, price level, structure, etc.)
- **Derivatives factors:** maximum of 2 per setup (IV rank, skew, GEX, max pain) — ADDITIVE to the cash cap, not subject to it
- **4+ factor override:** setups with 4+ factors in a single layer require written orthogonality justification AND must pass a higher backtest bar (Sharpe > 1.0 vs. standard > 0.7)

### Filter Rules

- Filters must SUBTRACT signals, not add them
- Measurable rule: a filter is subtractive ONLY if it reduces weekly signal count by ≥30% while holding or improving expectancy
- Filters that redistribute signals across buckets without reducing total count are additive disguised as subtractive — reject

### ADD Requirements

- Every ADD is PROVISIONAL until backtest module validates it; shadow-mode acceptable in the interim
- Every ADD requires a named deprecation target (one-in-one-out is MANDATORY, not soft)
- Deprecations can be "banked" against future ADDs if Olympus identifies them outside the context of a specific new strategy

### Location-Quality Multiplier (PYTHIA)

All signals are graded against their trigger location relative to the value area:

- **At VA edge (extension zone):** grade +0.5
- **Mid-VA (chop zone):** grade -0.5
- **Use PRIOR-SESSION developing VA** at signal time — cumulative VA introduces lookahead bias

This multiplier is applied to grades in Olympus reviews and to scoring in the live pipeline.

### Sector-Rotation Regime Specification (THALES)

- Every ADD must declare which sector-rotation regimes it targets (concentrated leadership, rotation, or regime-agnostic)
- Backtest segments results by rotation state
- Signals firing in the wrong regime for their profile receive a 0.75x position-size penalty automatically

### Signal Enrichment at Trigger Time

Every signal emitted by any scanner/strategy must include:

- Sector-rotation state tag (via lookup against `sector_rs` scanner output)
- Auction state tag (balanced / one-timeframing / trend day) via PYTHIA
- Prior-session VA-relative context (inside / at edge / outside)
- IV rank (for options-structure selection, payload-only — not used as a filter by default)

### Grandfather Clause

Existing strategies at the time of ratification are grandfathered against the confluence cap. Strategies flagged in the 2026-04-22 review with factor counts at or above the cap:

- **`wh_reversal`** (4 factors: WH-ACCUMULATION + 5-day return + VAL proximity + flow sentiment) — under the new location-quality multiplier, VAL proximity is reclassified as a grade modifier (not a factor). Effective count: 3. Compliant.

Grandfathered strategies auto-surface for review at each Olympus cadence (quarterly minimum) regardless of performance grade, to verify framework compliance holds.

### Grade Decay Auto-Flag

Any strategy scoring below B- for 3 consecutive Olympus reviews → mandatory deprecation review.
```

---

## 4. Constraints

- Do not modify any other content in PROJECT_RULES.md
- Preserve existing section ordering unless the "Strategy Anti-Bloat Framework" section logically fits elsewhere (use judgment; if unsure, place near top)
- Commit message: `docs: add Olympus-ratified anti-bloat framework to PROJECT_RULES.md`
- Push to main

---

## 5. When Done

Reply with:
1. The commit SHA
2. Confirmation of any ToC updates if applicable
3. Diff summary of what was added
