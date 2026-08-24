# T7-ADJUDICATION · v1.3

Supersedes v1.2 whole. Delta log: one line added to F4 (neutral-interval statement
per R-IV.38(c)); all else byte-identical to graded v1.2.

Row basis: `docs/edge/results/2026-08-20-T7-TRACKA-RESULTS.md`.

## F1 — collapse shape

Last-persisted rows stagger across sources (19:22 / 19:30 / 20:25 on 08-17 ·
04:12 on 08-18) = per-source emission schedules × onset of per-row payload
rejection.

**RULING OF RECORD (R-IV.29(b)): the writer never died.** A healthy writer
rejecting poisoned $19/$20 payloads row-by-row. Exact census 459 lost
(249 / 210 / 0). Poison-entry bracket (07:17Z, 13:23:37.8Z] on 08-18.

Struck lineage: v1.0 "rolling shutdown" (artifact-refuted); v1.1 "single writer
death" (no writer death occurred — the bracket dates poison entry).

## F2 — ae99def EXONERATED

Grounds: **TOPOLOGY, code-asserted** (CR-1 closed, R-IV.29(c)). L0 membership is
read-side only — 2 sites repo-wide, reachable solely via `evaluate_l0_gate()`,
1 production caller; `should_divert()` has 0 production call sites. A frozenset
removal cannot reach any write path.

Strike lineage, preserved per convention: v1.0 temporal precedence (struck — the
death bracket contained the deploy); v1.1 mechanism-location (struck — enrichment
attribution falsified; source UNATTRIBUTED). The conclusion held across three
grounds; only the code-asserted one is load-bearing, and only it is cited as such.

## F3 — blast radius

Writes succeeded through the window in `triton_flow_shadow` (16:34–16:41Z 08-18)
and `signal_outcomes` — **CODE-CONFIRMED**: the outcomes writer carries no JSON
payload and is immune to the poison class.

Blast radius = JSON-payload-bearing signals / enrichment writes (R-IV.26(b)
ruling, sharpened).

Side-note carried: 2,232 ungraded shadow rows, oldest 07-02 — shadow logging
without a grading loop.

## F4 — crypto_scanner split

Split per R-IV.26(c): its own outage 08-15 05:54 → 08-18, then shared
poison-orphaning 08-18/19. 22:30:31Z = restoration edge (T1-EARLY supersedes
T7-3c for resumption dating), not in-window survival.

Poison DEATH is undatable within (22:02:11, 22:30:31] — zero attempts in the gap;
**the neutral interval statement governs (R-IV.38(c)).**

Graveyard += crypto_engine (07-22), crypto_cvd_engine (07-24), unordered.

## F5 — certification margin

TA-100w boundary (id 18305) is upstream of the entire poison bracket; certification
margin intact.

## LESSONS (conventions, verbatim)

A last row bounds aliveness from below; only a missed expected event dates a death
— generalized (credit CC-QUERY): **an absence dates nothing until you establish
the expected event rate across it.**

A verdict cites its argument class; struck arguments remain listed as struck.
