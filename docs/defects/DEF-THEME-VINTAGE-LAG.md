# DEF-THEME-VINTAGE-LAG

**Severity:** P3 · **Filed:** 2026-08-17 · **Status:** OPEN
**Surface:** Stable Engine — `hub_get_stable_themes` vs `hub_get_stable_theme_members`

## Symptom
2026-08-05 03:00Z-ish reads: themes table `as_of 2026-08-05T01:02Z`
(post-Tuesday recompute) while theme-members served `as_of 2026-08-04T00:00Z`
(~29h old, Monday basis). Sibling tables answering the same question from
different sessions; member `ret_1d` was Monday's return while theme
`score_delta_1d` was Tuesday's — mixed vintage in one logical view.

## Why it matters
Honest-labeled but easy to misread under pressure; any consumer joining themes
to members inherits a silent one-day skew. (This misled the melt-up review for
several minutes before reconciliation caught it.)

## Verification / fix path
1. Confirm member-table recompute schedule vs themes recompute; align into one
   transaction/batch or stamp both with a shared batch_id.
2. Hub tool: when sibling vintages diverge >6h, surface a `vintage_mismatch`
   warning in the payload (display-older rule already exists for columns —
   extend to sibling tables).
