# VERIFICATION-LAWS INSTANCE — AN ABSENCE AND THE INSTRUMENT THAT COULD NOT SHOW IT

**FROM:** CC-POSITIONS. **Commissioned:** R-IV.387(a) (registration), R-IV.448(d) (second instance),
R-IV.458(f) (third instance).
**Target:** `docs/conventions/verification-laws.md` (ratified R-IV.166).
**Companion to** `verification-laws-addendum-3.md` → LAW 3 → *THE COMPANION INFERENCE RULE*,
which registers the rule and directs that these instances stay on this face (conventions #9).

---

## THE RULE, as registered

> **AN ABSENCE IS ONLY EVIDENCE WHEN THE INSTRUMENT COULD HAVE SHOWN A PRESENCE.**

Three instances follow. The first two came ten days apart, in the same lane, against the same
class of artifact. **They differ in one respect only, and it is the whole lesson: the first fired
after the conclusion was filed, the second before.** The third is a different instrument failing
the same way: **a search keyed on a mark that the event did not have to leave.**

---

## INSTANCE 1 — THE LINE CUT (RAMZ, 2026-09-05 → corrected 2026-09-07)

**The claim filed:** *"NO OPENING LINE EXISTS in any export on disk"* — written onto
`unified_positions` id 429 as the justification for leaving its `cost_basis` NULL and
classifying it a coverage-gap instance.

**The instrument:** a `grep` whose output was cut at 190 characters per line.

**Why it could not have shown a presence.** The Robinhood export's `Description` field carries
an **embedded newline** — the instrument name, then `CUSIP: …`. The RAMZ row's quantity, price
and amount all sit past that break, beyond the 190-character cut. **The line was in the file
the entire time.** The search could return the row and still never display the fields the
claim was about.

```
 rh-8.31.2026.csv, 8/31/2026:  RAMZ  Buy  18 @ $17.28  amount -311.04  settle 9/1/2026
```

**Cost:** a row sat with a NULL basis and a wrong note for two days, and a real position was
miscounted as an unsourceable orphan. Corrected at R-IV.386(b): basis 311.04, sold 09-01 at
17.60, **realized +5.76**, both sides zero-delta against the export.

---

## INSTANCE 2 — GREP OVER BINARY (Fidelity confirmations, 2026-09-17)

**The situation:** R-IV.446 cited nine Fidelity confirmations by reference number
(`26257-PBS5D3`), price (`142.3601`, `86.6430`, `19.7876`, `50.735`) and date. None of those
values had ever been seen in this lane.

**The instrument:** `grep -rl "<value>" data/ docs/` — run over the repository to check whether
the documents were present.

**Every one returned zero files.**

**Why it could not have shown a presence.** The confirmations are **PDFs**. Their text lives in
FlateDecode-compressed streams, so the literal `26257-PBS5D3` does not appear as bytes anywhere
in the file. **`grep` cannot read a PDF.** A zero result was guaranteed whether the documents
were on disk or not.

**What was done instead:** a directory listing. It found **all nine**, at
`data/imports/fidelity 9.1 to 9.17/`, written the same day. The refs were then extracted with
`pypdf` and every one of the cited values confirmed — `26257-PBS5D3` is the 60-share SOXS sale
at 50.7350 that resolved a 40-share error in the book.

**Cost: none.** The zero-hit result was not filed as a finding, because the instrument was
recognised as unfit before the silence was read as information.

---

## WHY THE PAIR IS WORTH KEEPING TOGETHER

**Same lane, same law, same artifact class, ten days apart.**

| | instance 1 | instance 2 |
|---|---|---|
| instrument | grep, line-truncated | grep, over binary |
| could it show a presence? | **no** — field past the cut | **no** — text is compressed |
| silence read as evidence? | **YES** | **no** |
| when the unfitness was noticed | **after** the claim was filed | **before** |
| cost | two days of a wrong NULL basis and a misclassified row | nothing |

The law did not prevent instance 2 by being known — it was known during instance 1 too, and
did not prevent that. **What changed was the order of operations:** asking *"could this search
have displayed the thing I am looking for?"* **before** treating the empty result as an answer.

That ordering is exactly what Addendum 3 states about the probe and the companion rule: *run
in the wrong order — trusting a silence and only afterwards asking whether the instrument
could have spoken — the answer arrives after the conclusion has already been filed.*

**Both instances are grep.** Not because grep is unusually unreliable, but because it is
unusually convenient: it is the default reach for "is this here?", it returns cleanly on
failure, and **its exit status cannot distinguish "not present" from "not readable."**

---

## INSTANCE 3 — A SIGNATURE THE EVENT DID NOT HAVE TO LEAVE (cash drift, 2026-09-18)

**Filed at R-IV.458(f).** The instrument was CC-BUILD's (b4a905b). It is filed on this face
because the rule is this face's, not to assign the error.

**The claim:** *"the recompute's signature -- an edit changing quantity or entry followed within
seconds by a change to cost_basis alone -- appears ONCE since 2026-08-26 ... Before 08-26 there
is no trail to read."*

**The instrument:** a search of `position_sync_audit` for a quantity/entry edit followed by a
second audit row changing `cost_basis` alone.

**Why it could not have shown a presence.** The cash code fires when an edit to an OPEN row
changes quantity x entry x multiplier against the old basis; it moves the cash, then writes
`cost_basis` in a second UPDATE. **If the caller's own PATCH already carried the new basis, that
second UPDATE changes nothing, and the audit trigger -- which writes only when OLD differs from
NEW -- writes no row.** Cash moves; the signature never appears. **Inside the continuous trail, four of
the five OPEN-row quantity/entry edits have exactly that shape**: `cost_basis` changed in the
same statement, to exactly quantity x entry x multiplier. (Nine of twelve if two CSV-sync runs'
own records from before the trail are counted -- see the correction below.)

**CORRECTED 2026-09-19 (R-IV.463(f)) -- a correction this lane made to the scope was itself wrong.**
R-IV.458 recorded "the trail starts 2026-05-26, not 08-26" on this lane's word. The 05-26 figure
was `min(executed_at)`: it found the earliest row, and could not show whether the rows after it
were continuous. **They are not.** Before **2026-08-26 21:02:24 UTC** the table holds only two
CSV-sync runs' own records (`sync_run_id` and `csv_paths` set): 7 rows at 05-26 21:41:38 and 13 at
07-19 06:40:09, each run a single instant. **The continuous, trigger-written trail starts 08-26
21:02 UTC, as BUILD said.** The same rule, turned on the lane that filed it: a first row is a
presence, and it says nothing about the gaps after it.

**What was done instead:** each of the twelve edits attributed to the path that wrote it, and the
daily cash series read where a path could have moved cash.

| edits | path that wrote it | cash moved as a record correction? |
|---|---|---|
| audit ids 5-7 (05-26), 18-21 (07-19) | two CSV-sync runs' own records, from before the trail -- not the per-row PATCH | no |
| 2149 TJX, 09-03 | partial-close path (the row's note: "Partial close 1/2 @ 0.9") | a fill, not a correction |
| 2724 SOXS, 09-04 | add path (quantity, entry, basis and max_loss in one statement) | a fill, not a correction |
| 3319 SOXS, 3322 WEAT, 09-08 | this lane's direct-SQL corrections (r313.py) -- never reach the API | **no**: `balance_snapshots` cash flat 09-07 -> 09-09 (FIDELITY_ROTH 4,623.81, ROBINHOOD 596.31) |
| 6503 NVDA 415, 09-18 | the PATCH recompute | **yes, -16.00**, reversed by cash adjustment #1 |

**Result: the conclusion was right and the instrument could not have shown it.** "Once" was
true of the population and unproven by the search. Net drift inside the trail is **0.00**;
before 2026-08-26 21:02 UTC it is **UNKNOWN**. Ruled at R-IV.458(f): the per-edit check is the finding of
record.

**What it adds to the first two.** Neither grep nor a truncated display: the unfitness is
structural. **A signature search answers "how many events left this mark?" -- never "how many
events happened?"** The second question needs the mechanism: the code that moves the money, read
for every way it can fire, and a count of the edits that match each way.

---

## THE CHECK THIS LANE NOW RUNS

Before any absence claim, name the artifact that WOULD have matched and confirm the instrument
could have rendered it:

- **truncated output** — could the matching field be past the cut?
- **binary or compressed input** — is the text stored as literal bytes at all?
- **narrow pattern** — would the real filename/field spelling match? *(a prior instance: a
  `grep -iE "trades|segment"` could never have matched `90-day Accounts_History.csv`)*
- **stale read** — was the listing taken before the file landed?
- **signature search** — can the event happen without leaving the mark the search keys on?
  *(instance 3: a cash move whose follow-up write was a no-op, so no audit row)*
- **a first row is not a trail** — `min(timestamp)` shows where the earliest row is, never that
  the rows after it are continuous. *(instance 3: this lane read 05-26 from `min()` and used it
  to "correct" a scope that was right; before 08-26 21:02 UTC there are only 20 rows from two
  CSV-sync runs)*

When the answer to any of these is uncertain, **the silence is not evidence** — a second
instrument is, and a directory listing or a format-aware reader is usually one command away.
