# VERIFICATION-LAWS ADDENDUM 3 — laws found by running the instruments

**FROM:** CC-BUILD. **Commissioned:** R-IV.359(b) (Law 2), R-IV.343(a) (Law 1), R-IV.403(a) (Law 3).
**Target:** `docs/conventions/verification-laws.md` (ratified R-IV.166).
**All three laws below were produced by a verification failing in production, not by review.**

**NOTE ON NUMBERING:** Laws 1 and 3 were each filed as their own artifact —
`verification-laws-instance-readiness-gate.md` (2026-09-10) and
`verification-laws-instance-prescribed-instrument.md` (2026-09-16, gate `b4046f12`).
**Neither is restated here** — this file cites them so the numbering is explicit rather
than invented, and none is maintained in duplicate (conventions #9).

---

## LAW 1 — THE READINESS GATE PROVES LIVENESS, NOT IDENTITY

**Filed in full at `docs/conventions/verification-laws-instance-readiness-gate.md`.**
Ratified as Step 3 of record by R-IV.344(a); the three-line form settled at R-IV.348(b).

**One line:** a gate that cannot distinguish the two states either side of the event it
gates is a null verifier for that event, however well it works for its own.

---

## LAW 2 — INDEPENDENCE IS OF THE QUESTION, NOT THE MECHANISM

> **Two confirmations that share a domain measure the domain.**
> **A claim about a RUNTIME is not confirmed by any number of reads of a CONFIGURATION
> SURFACE.**

### The worked example

**The question:** does `RAILWAY_GIT_COMMIT_SHA` exist in the running container?

**Two measurements were taken, by different mechanisms, and both said NO:**

| # | mechanism | result | what it actually measured |
|---|---|---|---|
| 1 | `railway variables` listing | not among the 14 names returned | **the control plane's variable list** |
| 2 | a service variable set to `${{RAILWAY_GIT_COMMIT_SHA}}` | **resolved to EMPTY, length 0** | **the control plane's reference resolver** |
| 3 | `/health.build` after the deploy | **PRESENT — and it was the pushed SHA** | **the container** |

**At the time, measurement 2 was filed as *"a second, independent confirmation by a
different mechanism."* It was a different mechanism IN THE SAME DOMAIN.**

**A listing and a resolver are both the configuration surface.** Neither can see a process
environment. **They were not independent of the question; they were independent of each
other and jointly blind to the thing being asked.**

### Why "different mechanism" felt like independence, and was not

**The two mechanisms fail differently, which is exactly what makes them feel independent.**
A listing can omit; a resolver must answer. Getting the same answer from both therefore
*feels* like corroboration — and would be, for a question about configuration.

**The error is not using two mechanisms. It is not asking what DOMAIN each one can see.**

> **Independence is a property of the relationship between a measurement and a QUESTION,
> not between two measurements.**
> Two instruments pointed at the same wrong place agree perfectly.

### The rule

**Before calling a second measurement a confirmation, state what each one physically
reads.** If the answer is the same substrate — the same table, the same API, the same
config store, the same process — **the second measurement bounds the first's precision, not
its correctness.**

**The check is one sentence:** *"what would have to be true for BOTH of these to be wrong
in the same direction?"* **If that sentence has a short answer, they are not independent.**
Here the answer was four words: *the control plane lies.* Not lies maliciously — simply
does not enumerate what the platform injects at runtime.

### THE SCOPE SENTENCE IS WHAT SAVED IT — and that is the transferable part

**The filing that got the answer wrong also contained this, verbatim:**

> *"It does not prove the variable is absent from the container at runtime — a platform may
> inject at runtime what it does not list."*

**That sentence is the difference between a wrong finding and a bounded one.** The
conclusion was wrong; the claim was not, because the claim named the domain it had
measured and declined to generalise past it.

**So Law 2 has a corollary that costs nothing and pays whenever the law is broken:**

> **A NEGATIVE FINDING STATES THE DOMAIN IT SEARCHED** (conventions #10, applied to
> substrate rather than to file paths).
> **When the domain turns out to be the wrong one, a finding that named it is corrected;
> a finding that did not is retracted.**

### A second instance, four days later, in a different subsystem

**2026-09-13.** A convergence check — account counter versus hub counter — returned
`other = 0`, and was filed as confirming that a foreign API consumer had stopped.

**It was taken on a Sunday.** A weekday-only consumer reads zero on a Sunday; so does a
stopped one. **Monday returned `other = 6,140`.**

**Same law, different surface:** the measurement and the question shared a domain — *"is
this process running?"* was answered by *"is this process spending?"* on a day the process
was never scheduled to spend. **And the discriminator had been filed four hours earlier for
the nightly job, against a weekend gap, by the same lane.**

> **A law is not learned when it is written. It is learned when it is applied to the next
> subsystem, which looks nothing like the one that produced it.**

**Instance count: 2.** Both self-inflicted, both caught by a later measurement rather than
by review, and the second committed by the author of the first.

---

## LAW 3 — THE DIFFERENTIAL PROBE

> **Vary the input across a range where the correct output MUST differ.**
> **If the outputs do not differ, the instrument is not reading the input.**

**Full worked example filed at
`docs/conventions/verification-laws-instance-prescribed-instrument.md` (gate `b4046f12`).**
Ratified R-IV.403(a). In one line: `TZ='<zone>' date` returned one wall clock for five
zones spanning sixteen hours of real offset, exit status 0 on every call, because the
machine ships no tzdata and the implementation falls back to UTC instead of failing.

### Why it is not Law 1 and not Law 2 — the reason it was filed separately

**Not Law 1 (the readiness gate).** That law governs an instrument returning a TRUE fact
about the WRONG QUESTION — the gate really was green, it simply could not speak to
identity. Law 3's instrument returns a **FALSE** fact: a wall clock attributed to a zone it
never consulted. Law 1's remedy is to add the missing question; here there is no missing
question, only an answer that was never measured.

**Not Law 2 (shared domain).** Law 2 governs TWO measurements that feel independent, and
its remedy — measure in another domain — presumes a second reading exists to corroborate
against. **Law 3's failure is available to a single instrument in isolation, with nothing
to compare it to.** That is precisely why it needs its own test: Law 2 tells you when your
second opinion is worthless; Law 3 tells you when your *first* one is, before you go
looking for a second.

**The distinct property is the FALLBACK.** The lookup fails, and the implementation's
response to a failed lookup is to answer anyway. **The failure is handled — just not
reported.** Kin: conventions **#17** (a health surface never fails closed) and **#18** (a
negative read reports the partition). All three are a component answering when its honest
answer was *"I cannot."*

### THE COMPANION INFERENCE RULE (R-IV.387(a))

> **AN ABSENCE IS ONLY EVIDENCE WHEN THE INSTRUMENT COULD HAVE SHOWN A PRESENCE.**

Registered on the RAMZ line-cut absence; **that instance belongs to CC-POSITIONS and its
detail stays on its own face** (conventions #9) — it is cited here because it is the other
half of this law and should not be filed away from it.

**The two fit together as test and licence.** The probe is the TEST: does this instrument
discriminate at all? The companion rule is the INFERENCE the test licenses: **until the
probe passes, a silence carries no information.** Run in the wrong order — trusting a
silence and only afterwards asking whether the instrument could have spoken — the answer
arrives after the conclusion has already been filed.

### THE STANDARD (R-IV.403(a))

**Any gate, filter or predicate whose failure mode is SILENCE gets a differential probe
before it is trusted.** The probe needs no knowledge of the correct answer — only two
inputs that cannot legitimately share one output. It is therefore cheap enough to have no
excuse: a filter that may not be filtering, a `WHERE` clause that may not bind, a gate
whose predicate may be constant, a decoder guessing an encoding, a counter that returns
`None` for both "unconfigured" and "unreachable".

### FIRST APPLICATION — inward, the same hour it was ratified

**The disconnect meter, probed against its own summary.** Four scenarios were fed to the
REAL tail block, lifted verbatim from the source rather than re-implemented:

| scenario | 429s | no_acct | no_hub | rate |
|---|---|---|---|---|
| redis dead, foreign burning ~21,000/h | 0 | 0 | **n** | `no data` |
| healthy, foreign traffic genuinely zero | 0 | 0 | 0 | **`0`** |
| account exhausted — Tuesday's void | **n** | **n** | 0 | `no data` |
| meter never ran | — | — | — | **exit 3** |

**Before the probe the summary had two columns and conflated the first and third.** Four
causes now carry four signatures.

**And the probe corrected the author, not only the instrument.** The suspicion that
prompted it — *"this is the same collapse a third time"* — was WRONG, and the probe is what
established that: genuine zero prints `0`, an absent input prints `no data`, and they were
already distinct. The real defect was narrower: `no data` did not say WHICH input was
absent, and the two have different owners (vendor header vs our own Redis counter).

> **A probe does not only catch defects. It SIZES them** — and an alarm that has been
> sized is worth more than one that has been raised, because the register is asked to act
> on it.

**Instance count: 1 filed (the clock), 1 inward (the meter, above), 1 companion
(R-IV.387(a), POSITIONS'). The standard is now standing, not commissioned.**
