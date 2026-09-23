# TRITON FORWARD-WINDOW REGISTRATION — AMENDMENT 2 (BAR VENDOR PINNED)

**FROM:** CC-BUILD
**TO:** SPINE
**Applies to:** `docs/edge/preregistrations/2026-09-03-triton-forward-window-registration-JOINT.md`
**Commissioned:** R-IV.489(a) — "File R-IV.485 on the registration face in the same pass."
**Prior:** Amendment 1 (declared observational strata, R-IV.275).
**Status:** filed for ratification. Nothing here changes the criterion, the endpoint, the
population handles, or any threshold. It names an instrument property that was already
operative and was, until now, held by accident.

---

## A2.0 · What this amendment does, in one sentence

It declares the **bar vendor** a pinned property of this window's measuring instrument, states
the evidence that it was already yfinance from T_clock, records that the pin has now been built
in code with a date, and discloses — with the count — whether any in-window row was graded on
any other vendor.

## A2.1 · The fact the registration already carries

This is not a new constraint being introduced mid-window. The JOINT manifest's own P1 evidence,
declared on its face at T0, reads:

> | **the fallback** | `no_regular_session_bars` **absent** (1,000 on 09-11); yfinance path
> entered and provider recorded per row | 2026-09-14 |

So the window opened with the yfinance path entered and the provider recorded per row.
**T_clock = Tue 2026-09-15.** The vendor was named in the preconditions; what was never
declared is that it must *stay* named, which is what this amendment supplies.

## A2.2 · Why it needs declaring — the accident, and the end of it

From **2026-09-14** every Triton row took the R-IV.324 fallback, because UW yielded no usable
regular-session bar. That was never a decision. It was a defect standing in for one:
`_get_bars_via_uw` read a `start_time` key that UW does not send, so every bar was skipped and
the fallback fired for every ticker on every call (**R-IV.477's diagnosis was wrong — it was our
parser, not a vendor outage**; retraction recorded at R-IV.489(e)).

Commit `04f6480` repaired the UW path for **every consumer** on 2026-09-23 at 15:54Z. That
repair silently removed the only thing holding this window on one vendor.

**Measured on production at 2026-09-23 19:1xZ, after that deploy:**

```
vendor_substitution.consumers["triton_grader.bars"]
    state = primary   primary_ok = 27   substitutions = 0
```

Triton was back on UW with the window open. Tonight's 20:00 ET grader run would have graded
in-window rows on a vendor the registration does not name.

`triton_flow_shadow`, all graded rows, provenance only:

| provider | rows | first graded | last graded |
|---|---|---|---|
| uw | 6,855 | 2026-07-08 | 2026-09-07 |
| yfinance | 1,209 | 2026-09-14 | 2026-09-22 |

## A2.3 · DISCLOSURE — in-window rows by vendor

The question §6 forces: were the threshold and the test measured by the same instrument?

Query scope: `fired_at >= 2026-09-15` (T_clock), `graded_at IS NOT NULL`. **Provenance columns
only — no outcome column was read**, per R-IV.489(a).

| provider | rows in window | id range | fired range |
|---|---|---|---|
| **yfinance** | **40** | 460533 – 461833 | 2026-09-15 13:31:52Z – 14:25:24Z |
| **uw** | **0** | — | — |

**Zero in-window rows have been graded on UW.** The window's instrument is unbroken as of
2026-09-23 20:0xZ. The pin was built before the first run that would have broken it, so this is
a disclosure of an averted breach, not of a breach.

**Stated as the limit it is:** this counts rows already *graded*. It is not a claim about rows
yet to be graded, which is exactly what the pin exists to govern.

## A2.4 · The pin, as built

`backend/jobs/triton_shadow_common.py`, commit `f6e700b`:

```python
TRITON_BARS_PIN_UNTIL = date(2026, 11, 6)      # inclusive
```

Properties, each chosen against a failure mode:

1. **Checked BEFORE the UW call.** Not "try UW, fall back" — no UW request is made at all. A
   pin implemented as a fallback is defeated the moment UW returns good bars, which is
   precisely the case the accident never covered.
2. **An empty yfinance result SKIPS.** It does not fall through to UW. Falling through is the
   breach.
3. **Recorded as `record_primary(yfinance)`, not as a substitution.** Under the pin yfinance is
   not a fallback, and `triton_grader.bars` is therefore *not* a statement about UW's health.
   R-IV.489(a) places the `primary_ok = 1` check on the other consumers for this reason.
4. **Data, not logic.** A date readable against this registration without running anything.
5. **Lapses on its own.** A pin that needs a second deploy to remove is a pin that outlives its
   window.
6. **The clock is ET.** The grader runs 20:00 ET, already the next UTC day; a UTC date would
   lapse the pin a day early and hand the window's last session to UW.

Tests: `backend/tests/test_triton_bars_pin.py` — the load-bearing one asserts the pin holds
**when UW is healthy and returning good `r` bars**, since that is the state the accident never
exercised. R-IV.324's fallback tests are not weakened; they are dated past the window so they
keep asserting UW is preferred once the pin lapses. One file tests that UW is preferred, the
other that it is refused.

## A2.5 · Open question for SPINE — the pin's end date vs the window's

`TRITON_BARS_PIN_UNTIL = 2026-11-06` is taken from R-IV.489(a)'s "through 11-06". The JOINT
manifest states the window `end = Fri 2026-10-30`, with extension mechanics at §4. **If 11-06
reflects an EXTEND, the anti-drift clause applies** — *"No third EXTEND without a new instrument
class: a leg, not more of the same"* (§8, carried verbatim). This amendment does not assert
which it is; it flags that the two dates differ and that the difference is the registration's to
resolve, not the build's.

**A second edge, flagged not fixed:** the pin keys on the *run* date, not the *row's* session.
A grader run occurring after 11-06 that grades in-window rows would use UW. Closing that
requires keying the vendor per row's session, a larger change. It cannot bite before 11-06.

---

END — one amendment, one disclosure, two open questions.
