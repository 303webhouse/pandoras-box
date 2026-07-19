# M1 — milestone circles + notecard dots · Fable review · 2026-07-13

**Branch:** `m1-milestones` @ `44afe2f`, reviewed via the read pipe (full patch).
**Merge state:** NOT pre-authorized — merge on Nick's word after the R1 fold
(recommendation below on compressing the cycle).
**Place this file at:** `docs/m1-review-fable.md`.

## Verdict

**REQUIRED — 1** (small), **3 advisories**, two doc promotions. No
data-loss-class findings; no architecture findings; zero-schema confirmed
(the celebration memory isn't even localStorage — a module-level set,
app-load-scoped by design). S0 was executed exactly as the brief gated and
is documented in `store/milestones.ts`'s header: `BeatNote.status` carries a
genuine terminal value (`'complete'`), `setBeatStatus` remains Plan-side and
untouched, and `JournalEntry.beatId` is the only attachment signal read. The
projection is provably read-only. The cross-project scope catch (bare
framework-authored beat ids shared verbatim across projects) is the
standout — fixture 3 reproduces both failure directions, false-celebration
and swallowed-celebration. Best-engineered ticket of the arc.

## Required

### R1 — Project mode must not eat the session timer
`Timer: On` is an independent toggle designed to survive every progress
value — with `Progress: Off`, `ProgressBar` renders hidden-track purely to
carry the ⏱ clock in its `rightSlot`. `showMilestones` replaces
`ProgressBar` wholesale, so `Timer: On` + `Progress: Project` silently loses
the clock. **Fix:** give the milestone branch the same right-hand slot —
either a `rightSlot` prop on `MilestoneBar` (mirroring `ProgressBar`'s) or
the timer span rendered beside it in `ModeStage`'s incentive row. Page
number (`p.N`) should ride along for consistency.
**Harness:** one check — `Timer: On` + `Progress: Project` on a plan-linked
page renders both `.mode-milestone` circles and `.mode-timer`.

## Advisories — record, don't change

- **A1 — the cold-path approximation, qualify the comment.** The baseline
  claim in `useMilestoneCelebration`'s header ("a beat that turns lit while
  no celebration-consumer is looking still celebrates exactly once, on
  whichever surface shows it next") holds only when the plan's scope was
  established *before* the transition. If the writer completes a beat while
  on `Words` and switches to `Project` later in the same app-load, first
  observation seeds it as baseline — lit, no pulse. This is inherent to
  storage-free session memory and **errs in the correct direction** (no
  false celebrations, the worse lie). Amend the comment's claim with that
  qualification; do not add storage — persisted seen-state would trade this
  for cross-device false pulses, which is worse.
- **A2 — the interrupted-celebration re-pulse is deliberate.** Navigating
  away mid-pulse leaves the id uncommitted, so the next surface re-pulses
  in full. Occasional double pulse on a fast navigation is the accepted
  cost of never silently consuming an unpainted celebration. Recorded so a
  future pass doesn't "fix" it into the worse bug.
- **A3 — `started` folds to empty on the circle-bar.** The writing-surface
  vocabulary is attachment-driven (`kindled` = pages attached), so a beat
  marked `started` Plan-side with nothing attached shows an empty ring.
  Correct per the canon's coverage-not-verdict rule; noted for the device
  pass in case it reads oddly against the Board's half-dot.

## Ruling on the Board-dot interpretation

The canon's Q4 phrase "in the same three states" was loose drafting. The
build kept the Board's **pre-existing** `empty/started/done` status
vocabulary and added only celebration-on-transition — the conservative,
compose-don't-rebuild reading, and the right one: overwriting Plan-authored
`started` with attachment-driven `kindled` would have destroyed information
on the one surface where status is authored. **Ratified.** The canon text
stands; this paragraph is the interpretation of record.

## Doc promotions (commit with the R1 fold)

1. **AGENTS.md — the harness seeding law** (new short paragraph under
   "Harness scenarios persist"): raw-localStorage seeding must happen while
   OFF any surface with a flush handler — `flushNow()` re-serializes every
   collection from the in-memory cache unconditionally and will overwrite a
   raw seed — then reload to hydrate the cache from the seed before any
   further app action can schedule a stale flush. (Discovered in M1;
   currently documented only in `m1.mjs` comments and CC's private memory —
   chat-only-equivalent. This is load-bearing for every future harness.)
2. **`docs/open-threads.md` — HORIZON item:** App.tsx force-renders the
   whole routed tree on every persistence write (its sync/reactive-screens
   subscription). Harmless at current scale; a real perf ceiling eventually.
   M1's deferred-seen-commit is the local workaround pattern. No ticket —
   on the map.

## Merge / close protocol (recommendation)

R1 is a one-slot fix. To spare a full round-trip, Nick can give a
**contingent merge word** with the fold relay — the W2 rhythm: CC folds R1 +
the comment amendment (A1) + the two doc promotions + the one harness check,
re-runs the full suite + `m1.mjs`, merges, deploys (zero-schema — no server
files anywhere in this diff), pushes; Fable's delta spot-check runs
post-merge, fix-forward if anything surfaces. Or classic mode: fold, push,
spot-check, then the word. Nick's call. Either way: **ledger** gains the M1
item (IN FLIGHT → DONE at merge, item-6 pattern) and item 2 gains a ninth
cluster —

> - M1 · S25 + desktop: circle legibility at 10px on the slate, kindled vs
>   lit distinguishability at arm's length, the celebration pulse's felt
>   weight on both surfaces, windowed edge-fade readability, and whether
>   `started`-as-empty-ring reads oddly against the Board's half-dot (A3).

`docs/w1-close-handoff.md`: strike Step 4 as executed on merge — the
handoff is then fully spent; archive-header it like the runbook.

— Fable
