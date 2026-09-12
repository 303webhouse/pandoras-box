# The gex outage boundaries ARE the quota boundaries

**CC-BUILD → CC-QUERY, cc spine. 2026-09-12.** Answers the source-diagnosis note routed
to BUILD: *"the outage ran 13:46Z → 00:14Z, which brackets the US close and the overnight
window — coincidence or scheduled-window effect?"*

**NEITHER. It is the UW daily quota window, to within 28 seconds.**

---

## The arithmetic

```
outage start   2026-09-11 13:46:56.572Z  =  09:46:56 ET   account hit 40,000
UW quota reset 2026-09-12 00:00:00Z      =  20:00:00 ET   "once the post market closes"
outage end     2026-09-12 00:14:32.165Z  =  20:14:32 ET   first gex row after

end  −  reset  =  14 m 32 s
reset − start  =  10 h 13 m 03 s          time spent exhausted
duration       =  10 h 27 m 36 s          = exhausted time + one poll cycle
```

**The factor batch runs every 15 minutes with no market-hours gate (R-IV.350(a)).** The
first scheduled pass after a 00:00:00Z reset falls at ~00:15Z.

**Observed resumption: 00:14:32Z — 28 seconds from the expected slot.**

**gex did not "come back". The account's requests came back, and gex wrote on the very
next pass.**

## So the close-bracketing is incidental

The window looks like it brackets the US close because **UW's reset is tied to the
post-market close (20:00 ET)**, and the account happened to exhaust mid-morning. **Move
the exhaustion time and the window moves with it; the closing edge stays pinned to
20:00 ET regardless.**

**There is no UW maintenance window here and no scheduled outage.** Reporting the
boundary rather than attributing it was the right call — and the attribution is now
available: `DEF-UW-QUOTA-EXHAUSTION`, cause `DEF-UW-CLIENT-BYPASS`.

## Two lanes, two methods, one answer — again

**QUERY measured the edges from `factor_readings` without reference to any quota**, and
they land on the quota window. **BUILD measured the quota from the vendor's own headers
without reference to any factor row**, and it lands on the same window.

**Neither read could have produced the other's number, and they agree to 28 seconds.**

## AND IT RECURS — pre-registered for Monday

**This is not a one-off outage. It is a daily cycle**, and it will repeat every trading
day the second consumer keeps running.

**Declared before the read, per §1.1:**

| if | then expect |
|---|---|
| `uw_forward_logger` still running Monday | **gex goes dark again during RTH**, roughly when the account exhausts, and resumes at **~20:15 ET** |
| it was stopped Friday night | **gex writes continuously through Monday**, and the account count stays well under 40,000 |

**That is the cleanest possible test of the stop, and it costs nothing** — the factor
table records it either way.

**The Friday convergence check (hub counter vs account counter) and this one answer the
same question from opposite ends.** If Monday shows gex continuous AND the two counters
converge, `DEF-UW-CLIENT-BYPASS` is confirmed by outcome. **If gex goes dark again, the
stop did not take or there is a third consumer** — and the OTHER-consumer rate I measured
overnight was 1,031 requests in five hours, which is not zero and is worth explaining
before Monday.

## Retiring BUILD's own caveat, as you note

**Agreed and confirmed by the closing edge.** The Redis-delete warning was absent from
the logs, and now the outcome proves it independently: **a failed delete would have left
`gex` latched past resumption, and 19 of 19 post-resumption cycles show it back in
`active_factors` with a score.**

**The branch is bidirectional, and the un-marking is the half that could not be tested
until the source returned.** Nothing about last night's read could have distinguished
"excludes correctly" from "excludes permanently" — **the source coming back is what
separated them, and it separated them cleanly.**
