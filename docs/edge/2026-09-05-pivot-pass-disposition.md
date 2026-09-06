# R-IV.273 · PIVOT PASS DISPOSITION — principal ruled

**Filed by** CC-BUILD under R-IV.274(b), 2026-09-05. **Authority** SPINE (Fable 2).

**The ruling text below is VERBATIM and is not this lane's words.** It is reproduced
between the two rules with nothing added, removed, or reflowed. Gate over the verbatim
region only: `0427de59`, `2000` bytes UTF-8, **LF-normalised**. Re-hash the region between
the rules to check it. The gate names the LF tree: this repo checks out CRLF on Windows, so a
fresh working copy hashes differently and that is not a mismatch — normalise CRLF→LF first
(conventions, *A GATE VALUE NAMES ITS TREE*).

**Execution record, this lane's words, outside the verbatim region:**

| clause | disposition |
|---|---|
| (a) EXTEND SHADOW | recorded; no build action |
| (b) SEVEN-WEEK TEST + Amendment 1 | **spine-authored, pending the R-IV.269 census.** Precondition order is Amendment 1 filed → P1/P2 verify live → clock starts |
| (c) SPEND — PAUSE | **`Execution of (c)` belowUTED 2026-09-05.** See `Execution of (c)` below |
| (d) BUILD ORDER | grader P1/P2 → sinks + backfill → ledger integrity; ledger brief drafts in parallel |
| (e) book items ①–⑧ | Trade Analysis's; not this lane's |

---

R-IV.273 · SPINE (Fable 2) · PIVOT PASS DISPOSITION — principal ruled
2026-09-05 (Triton track; book items transferred to Trade Analysis)
(a) EXTEND SHADOW — BLESSED, relabeled: the seven-week window tests the
sweep leg of the Moby Dick Hunter; the Hunter is the composite of legs
entering by registration, one instrument class at a time, per the anti-
drift clause.
(b) SEVEN-WEEK TEST — BLESSED AS REGISTERED (criteria unchanged, verdict
semantics unchanged, anti-drift verbatim) PLUS AMENDMENT 1, spine-
authored after the R-IV.269 census returns: declared OBSERVATIONAL strata
recorded per row from the first window session — sector, instrument
class (index ETF / sector ETF / single), day-of-week, DXY trend sign,
footprint-present, tide sign when the sink exists — and 10d/20d
horizons; face-labeled "hypothesis generation, not verdict."
PRECONDITION ORDER: Amendment 1 filed → P1/P2 verify live → window
clock starts. The amendment never lands after the clock.
(c) SPEND — PAUSE, executed now (R-IV.270(d)'s word is given): dark-pool
and market-tide pollers pause by flag. Watch = 48h OR through the first
full RTH session (Tue 09-08 close), whichever is later — a hidden
consumer that only runs in market hours can't reveal itself on a
holiday weekend. Breakage = diagnostic, not failure. Sinks build at
position 2 with backfill from UW history on ship; nothing is lost by
the pause. The re-scope §4 clause's state of record: "condition fired
09-03 · ruled 09-05 · PAUSED by principal · resume on sink ship."
(d) BUILD ORDER CONFIRMED by principal: grader P1/P2 → sinks + backfill
→ ledger integrity. Ledger brief drafts in parallel on paper.
(e) Book items ①–⑧ of the pass are Trade Analysis's; not decided here.
Closing accounting, as written: six days of machinery, one exposure
event caught in twenty-five seconds by its own tripwire, a premise
neither killed nor promoted, and an instrument set now clean enough
that the next answer will be believable.

---

## Execution of (c) — CC-BUILD, 2026-09-05

Recorded here because a ruling that orders an act should carry the act's evidence on the
same face.

**Form.** Environment flags read at the top of each poller cycle, through one shared
helper `backend/jobs/poller_pause.py` rather than a check copied into each loop. The copy-forward is how the
weekday-approximation family reached five instances; a second pause idiom would start
the same sequence.

| poller | site | flag | spend paused |
|---|---|---|---|
| market tide | `stable_jobs.py::stable_tide_warmer_loop` | `PAUSE_TIDE_POLLER` | ~1 UW call / 5 min, RTH only — **~78 calls/RTH day** |
| dark pool | `main.py::wh_accumulation_loop` | `PAUSE_DARKPOOL_POLLER` | 25 tickers / hour, RTH only — **~175 calls/RTH day** |

**~253 UW calls per RTH day**, against the k/burn artifact's measured ~251/day dark-pool
and ~71/day tide. Both loops were already session-gated, so **the pause changes nothing
until the first RTH session — Tuesday 09-08, because Monday 09-07 is Labor Day.** The
ruling's watch window already accounts for this.

**Fail-open, deliberately.** Only the exact string `true` pauses; unset, empty, or any
other value runs. A pause that could arrive by omission — a dropped variable, a typo, a
bad default — would silently stop collection, which is the failure this board has now
registered under several names. **Stopping collection must be an act, never an omission.**
Two mutations of that rule were tested; both kill tests.

**Confirmed from the running process, not the dashboard**, as the ruling requires:
`/health.paused_pollers` reports what the process actually read. A Railway variable is a claim about
configuration; the health field is evidence about behaviour. The pause deliberately does
**not** drive the health verdict — an intended state that degrades health teaches readers
to discount the signal, which is `DEF-PYTHIA-ALARM-NOT-ACTIONED`'s mechanism arriving from the other end.

**Expected emptying, so the watch can separate intended from unintended.** `board:tide:latest` carries
a 1800 s TTL, so the v2 board tide cell goes dark ~30 min after the last warm; dark-pool
promotions from the accumulation scanner stop. **Those two are the pause working.**
Anything else that errors or empties through Tue 09-08 close is the hidden consumer the
re-scope clause predicted, and is diagnostic.

**Not paused, deliberately:** the on-demand consumers — `committee_bridge.py:248-249`, `sectors.py:624`, and the
signal-pipeline enrichment — which spend only when something asks. Pausing those would
break reads without saving poll spend.

### A second reading of a docstring already on the record

`backend/jobs/stable_jobs.py` opens with **"yfinance-only (zero UW calls)"**. Yesterday's outage diagnosis
cited that line as evidence yfinance is a *declared primary* rather than a fallback.
Filing this pause required editing the same module, and the sentence is false on a second
count: **this module hosts the tide warmer, which is a UW call every five minutes of
RTH** — the very spend clause (c) pauses. One sentence, two wrong claims, and the second
was invisible until a task happened to touch it.
