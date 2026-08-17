# STRIKE-SPEC-03 — Compression Flag

**Status:** DRAFT-FILED (pre-Titans) · **Family:** D (Compression → Expansion)
**Raschke basis:** Rule 11 / Principle Four — the market alternates between
range expansion and range contraction.
**Build class:** Nightly batch job on daily bars. Zero new data infrastructure.
No UI. Titans review — ATLAS lead, DAEDALUS consulted (options-expression
consumer).

---

## 1. Problem

Compression is the one condition where the lane's friction math flips
favorable: when realized range contracts, options premium tends to cheapen,
and a $100–300 long-premium clip can survive its own spread. The system
currently has no notion of compression anywhere. This spec adds a
**non-directional flag**, not a trade signal — direction comes from the break
(SPEC-01 IB events, SPEC-02 strong closes, SPEC-04 PDH/PDL events).

## 2. Definitions

- **NR7:** narrowest true range of the last 7 sessions.
- **Inside day:** high < prior high AND low > prior low.
- **ATR-percentile:** ATR14 today vs its own trailing 126-session distribution.

## 3. Scope

Nightly job over the same universe as SPEC-02:

- **Compression score (0–100):** NR7 → +40; inside day → +25 (stacking with
  NR7 allowed: NR7+inside = classic coil); ATR-percentile ≤ 20% → +35 (≤ 10%
  → +45).
- **Flag emission:** score ≥ 60 → `COMPRESSION_FLAG` row (sidecar table,
  same design decision as SPEC-02's tag) with score, components, and a
  2-session TTL refreshed nightly while conditions persist.
- **Consumers:**
  1. Scoring modifier (Family E): any directional STRIKE signal on a
     flagged ticker gets +10 (breaks out of compression carry higher odds of
     range expansion — the Raschke principle mechanized).
  2. **DAEDALUS expression selector:** flag live → long-premium structures
     (singles / narrow debit spreads) are viable at clip size; flag absent
     and IV elevated → defined-risk spreads only. This consumption rule gets
     encoded in DAEDALUS's committee reference at promotion time, not before.

## 4. Non-goals

No IV data dependency in v1 (realized-range proxies only — UW options-chain IV
enrichment is a v2 candidate once the UW quota/Governor posture is settled).
No directional emission. No live scoring.

## 5. Promotion gate

n ≥ 100 flag instances; post-flag expansion measured descriptively (range next
3 sessions vs trailing) — note: this measurement is **descriptive
characterization of the flag**, not an edge claim; any edge claim requires
pre-registration per charter law. Titans re-review + Nick GO.

## 6. Open questions for ATLAS review

1. Sidecar table design shared with SPEC-02 tags (one `strike_tags` table for
   both?).
2. Whether the trade-ideas scorer can accept external modifiers today or needs
   a hook (this determines whether consumer #1 is wiring or a build).
