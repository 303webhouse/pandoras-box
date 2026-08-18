# DEF-L0-TESTS-STALE-HG1H

**Severity:** P2 · **Filed:** 2026-08-18 · **Status:** OPEN
**Surface:** `backend/tests/test_l0_routing.py`
**Introduced by:** `ae99def` (Phase-A A1 flip) — expected consequence, not a regression in behaviour

## Symptom

After the Phase-A A1 flip removed `HOLY_GRAIL_1H` from `SUPPRESS_ALWAYS`,
`pytest backend/tests/test_l0_routing.py` reports **4 failed, 26 passed**:

```
FAILED tests/test_l0_routing.py::test_unconditional_suppress[HOLY_GRAIL_1H]
FAILED tests/test_l0_routing.py::test_whitespace_signal_type_normalized
FAILED tests/test_l0_routing.py::test_default_mode_is_enforce
FAILED tests/test_l0_routing.py::test_should_divert_true_only_under_enforce
```

## Root cause

The suite uses `HOLY_GRAIL_1H` as its canonical "a suppressed signal_type"
fixture in four places, so the tests encode the *old* policy rather than the
gate's mechanics:

- `:15` — parametrize list includes `"HOLY_GRAIL_1H"`.
- `:61` — `_decide("  HOLY_GRAIL_1H  ")` asserts `would_suppress is True`
  (testing whitespace normalisation, not the set).
- `:83-86` — asserts `should_divert(d) is True` under default-enforce.
- `:119-120` — asserts `should_divert(d) is True` under explicit enforce.

The gate itself behaves correctly: `HOLY_GRAIL_1H` → `KEEP`/`would_suppress
False`; `HOLY_GRAIL_15M`, `PULLBACK_ENTRY`, `TRAPPED_LONGS`, `ARTEMIS_LONG` all
still → `SUPPRESS`. Verified by direct runtime assertion at flip time.

## Why it matters

`main` currently carries 4 failing tests. Railway's build does not run pytest
(railpack → uvicorn start command), so **this does not block deploys** — but it
leaves a red suite for the next lane and masks any genuine future L0 regression.

## Proposed minimal fix (NOT applied — Phase-A scope fence: one code line)

Mechanical, test-only, no production change:

1. `:15` — drop `"HOLY_GRAIL_1H"` from the parametrize list.
2. `:61`, `:83`, `:119` — swap the fixture to a still-suppressed type
   (`HOLY_GRAIL_15M` is the natural substitute; those three tests are asserting
   whitespace-normalisation / mode / divert semantics, not HG_1H specifically).
3. Optionally add a positive test asserting `HOLY_GRAIL_1H` now returns `KEEP`,
   so the Phase-A state is pinned and a silent re-suppression would fail.

**Reversal note:** if the A1 flip is rolled back per Committee Condition 4
(`git revert ae99def`), these 4 tests pass again with no action — do not fix
this ticket in a way that would then fail post-revert. Prefer step 3's explicit
pin over rewriting the semantics.
