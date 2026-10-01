# RELAY — CC-STATER → SPINE · first deliverable (R-IV.618) and Phase 0 start (R-IV.619)

Received R-IV.618. Received R-IV.619.

## Deliverable
- **Scope:** `docs/stater/STATER-SCOPE-2026-10-01.md` on branch **`claude/stater-scope`**. It covers
  what works, what is stubbed and what is broken; the framing mapped to what exists; phases 0–3 with
  what each needs; and the named free sources.
- **Mockup on sample data:** `docs/stater/mockups/stater-phase1-sample.html`
  (sha256 `fbc048cbd62fce78a54e2eb20347d9779305232101d6dc643d82548e4e0783ac`, raw bytes).
  - The principal has a private artifact copy; he can share the link with you.
  - Every panel is marked SAMPLE, and a full-width banner says so.
  - The page fetches nothing.
- **Nothing is wired, merged or deployed.**

## Phase 0
Started on **`claude/stater-phase0`** in your order (1 → 6). Progress is reported in
`docs/handoffs/lanes/CC-STATER.md` on that branch.

**UW baseline:** the governor's `GET /api/uw/health/by_caller` at 2026-10-01 05:59 UTC read
`outcome_resolver` 75 and total 489.
- Crypto bars share the `outcome_resolver` tag with the equity resolver.
- The "after" figure is therefore the counter drop after BUILD merges, plus a test that fails if
  any crypto GET reaches `_uw_request`.

## Cross-lane items (text only; owners insert)
- **BUILD:**
  - `docs/handoffs/lanes/README.md` needs a CC-STATER row in the ownership table. It inherits S-6M's
    ownership of `stater.*`, plus the crypto backend paths in R-IV.618(a).
  - Agora's mobile deck-bar link to `/app/stater` stays as is.
- **ABACUS:** the R-IV.420(e) relay asking "S-6M" to bump `stater.html`'s `v2.css` pin and recolour
  stale dots is now CC-STATER's. It will be done on a Stater branch, so no action is needed from
  ABACUS.
- **BUILD / QUERY:** until Phase 0 merges, any open Stater tab spends UW calls and writes about 17k
  log rows a day. Closing the tab stops it.

## Decisions for the principal (also in the scope doc, §5)
1. The mockup's layout.
2. Whether the stage thresholds are ruled first or tuned on history.
3. When, if ever, Phase 2 (paper) is considered.
