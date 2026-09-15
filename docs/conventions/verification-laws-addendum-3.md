# VERIFICATION-LAWS ADDENDUM 3 — laws found by running the instruments

**FROM:** CC-BUILD. **Commissioned:** R-IV.359(b) (Law 2), R-IV.343(a) (Law 1).
**Target:** `docs/conventions/verification-laws.md` (ratified R-IV.166).
**Both laws below were produced by a verification failing in production, not by review.**

**NOTE ON NUMBERING:** Law 1 was filed on 2026-09-10 as its own artifact,
`docs/conventions/verification-laws-instance-readiness-gate.md`, before this addendum
existed. **It is not restated here** — this file cites it so the numbering is explicit
rather than invented, and the two are not maintained in duplicate (conventions #9).

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
