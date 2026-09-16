# VERIFICATION-LAWS INSTANCE — A PRESCRIBED INSTRUMENT THAT CANNOT FAIL LOUDLY

**FROM:** CC-BUILD. **Commissioned:** R-IV.402(a). **Measured:** 2026-09-16 02:28 UTC.
**Target:** `docs/conventions/verification-laws.md` (ratified R-IV.166).
**Companion to** `verification-laws-addendum-3.md` (Laws 1 and 2) and
`verification-laws-instance-readiness-gate.md` (Law 1 in full).

---

## THE STATEMENT

> **An instrument that FALLS BACK instead of FAILING converts "I could not measure" into
> "here is a measurement." Prescribing such an instrument in a rule does not make it
> safe — it makes the failure inherit the rule's authority.**

---

## THE MEASUREMENT

The standing time rule (`CLAUDE.md`, "Time-of-Day Statements") prescribed, verbatim:

> *"If unsure which is in effect on the current date, run `bash_tool` with
> `TZ='America/Denver' date` to get the correct local conversion."*

**This machine's Git Bash ships no tzdata.** `TZ=` is therefore ignored. Not rejected —
ignored. Five zones were probed at one instant, chosen to span sixteen hours of real
offset:

| zone probed | returned | true local time |
|---|---|---|
| `UTC` | `Wed 2026-09-16 02:28 GMT` | Wed 02:28 UTC |
| `America/Denver` | `Wed 2026-09-16 02:28 GMT` | **Tue 20:28 MDT** |
| `America/New_York` | `Wed 2026-09-16 02:28 GMT` | **Tue 22:28 EDT** |
| `Asia/Tokyo` | `Wed 2026-09-16 02:28 GMT` | **Wed 11:28 JST** |
| `Australia/Sydney` | `Wed 2026-09-16 02:28 GMT` | **Wed 12:28 AEST** |

**Five distinct correct answers. One returned value. Exit status 0 on every call.**

For the zone the rule actually names, the error is **six hours and a day boundary** — it
places a Tuesday evening on Wednesday morning. Python `zoneinfo`, reading Windows' own tz
database on the same machine at the same instant, returned all five correctly.

**Consequence avoided by not using it:** this lane was, at that moment, arming an
instrument keyed to *"the next 09:00 ET."* Believing it was already Wednesday would have
armed it for **Thursday** — and the newly-added late-arm guard would have refused, which
is the only reason the error had a floor at all.

---

## WHY THIS IS NOT LAW 1 OR LAW 2

**It is not Law 1 (liveness vs identity).** The readiness gate returned a TRUE fact about
the wrong question. `TZ= date` returns a **false** fact — a wall clock attributed to a zone
it never consulted.

**It is not Law 2 (shared domain).** Law 2 governs *two* measurements that feel
independent. This is a single instrument, and no second reading was available to catch it.
**Law 2's remedy — take another measurement in another domain — does not apply, because
there was nothing here to corroborate against.**

**The distinct property is the FALLBACK.** The tz lookup fails, and the implementation's
response to a failed lookup is to use UTC and label it `GMT`. The failure is handled — just
not reported. Nearest existing kin is convention **#17, A HEALTH SURFACE NEVER FAILS
CLOSED**, and **#18, A NEGATIVE READ REPORTS THE PARTITION**: all three are a component
answering when its honest answer was *"I cannot."*

---

## THE AGGRAVATING PROPERTY: PRESCRIPTION

**The command was not chosen in the moment. It was written into the rule.**

A prescribed instrument is executed **without re-derivation** — that is the point of
prescribing it. So the one reflex that would have caught this, *"does this command actually
read the input I am giving it?"*, is precisely the reflex a rule is designed to make
unnecessary.

And the rule's own closing sentence reads:

> *"This rule exists because Claude has been wrong about local time multiple times by
> inferring rather than measuring."*

**Following it faithfully reintroduced the error it was written to prevent, while producing
the appearance of having measured.** That is worse than inferring, because an inference is
known to be an inference. This is the null-verifier law landed on a rule rather than on a
test: **a prescribed verification that cannot fail is worse than no prescription**, because
it also discourages the check that would expose it.

> **A rule that names an instrument inherits that instrument's failure modes, and hands
> them its authority.**

---

## THE TRANSFERABLE CHECK: THE DIFFERENTIAL PROBE

The discriminator that caught it costs one command and generalises to any instrument that
takes an input:

> **Vary the input across a range where the correct output MUST differ. If the outputs do
> not differ, the instrument is not reading the input.**

**Identical outputs across inputs that cannot share an answer is proof of a fallback**, not
evidence of stability. It requires no knowledge of the correct answer — only that two
inputs cannot legitimately produce one output. Here: no single wall clock can be correct
for both Denver and Tokyo.

**Apply it to any instrument whose silence is indistinguishable from its success** — a
filter that may not be filtering, a query whose WHERE clause may not bind, a gate whose
predicate may be constant, a decoder that may be guessing an encoding. In each, the probe
is the same shape: **feed it two things it must distinguish, and check that it does.**

This is the positive form of the same-predicate test already used three times in this
register (grader queue vs count; sinks dedupe key; resolver backlog) — there, two
predicates were compared to expose one that did not discriminate; here, two **inputs** are.

---

## DISPOSITION

**`TZ='<zone>' date` is PROHIBITED on this machine** (R-IV.402(a)). `CLAUDE.md` amended:
Python `zoneinfo` is the conversion of record, and **a `GMT` label on a request for a US
zone is proof the conversion did not happen.**

**Instance count for the fallback family: 1 confirmed here**, plus conventions #17 and #18,
which are the same shape on different surfaces. **Found by a differential probe, not by
review — and the instrument had been in the rule long enough that review had already passed
over it repeatedly.**
