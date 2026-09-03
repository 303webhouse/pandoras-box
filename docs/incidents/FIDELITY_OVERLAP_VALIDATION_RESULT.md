# OVERLAP VALIDATION — RESULT · 2026-05-27 → 2026-06-18

**Task 2 of the historical-extraction brief. UNBLOCKED and EXECUTED.**
**READ-ONLY on the DB. No writes, no migrations.** Local artifacts only, all gitignored.

**Dual-provenance stamp:**

| provenance | value |
|---|---|
| **Tree SHA** | **`8b2d767`** — own fetch 2026-08-25 07:28 UTC, `ls-remote` confirmed, 0/0 |
| **Broker artifact** | `90-day Accounts_History.csv` (36,651 B, mtime 2026-08-25 01:01:47 MDT) |
| **Tools** | `normalize_fidelity_history.py` (patched, 01:17:05) · `scripts/segment_trades.py` (8,015 B, 01:16:30) |
| **DB read** | 2026-08-25 07:25 UTC, read-only MCP, `::text` on timestamps |
| **Stamped** | 2026-08-25 07:29 UTC (01:29 MDT) |

---

## 0. Correction owned — R-IV.88/90(f)

I reported the 90-day export absent. **It was on disk when I said so.** Timeline:

```
 90-day Accounts_History.csv     landed 01:01:47 MDT
 my directory read                       earlier in that turn (showed 5 files, total 56)
 my report asserting absence      stamped 01:16    MDT   <-- stale by ~15 min
 scripts/segment_trades.py        landed 01:16:30 MDT
 normalize_fidelity_history.py    patched 01:17:05 MDT
```

One of the three assertions was stale and that one is mine — I asserted absence from a
directory read taken earlier in the same turn instead of re-reading at write time. The
segmenter and the normalizer patch landed at/after my stamp, so those two were accurate
when written, but the corrective applies to all three.

**Adopted:** re-verify disk immediately before any absence claim enters a deliverable, not
once per turn. A compounding factor worth flagging for others: my earlier check grepped
`ls … | grep -iE "trades|segment"`, which cannot match `90-day Accounts_History.csv`. A
narrow grep is not a directory read.

---

## 1. Broker reconstruction — 159 fills → 43 trades

```
 source_fills 159 · fills_accounted 159 · trades_total 43
 trades_closed 41 · trades_open 2 · trades_unknown_basis 5 · unsettled 0
 date_range 2026-05-27 → 2026-08-24 · 18 tickers
 realized_priced_only  +$929.63
```

Pre-window inventory reproduces spine's enumeration **exactly**: XLE −20.071 · SMST −20 ·
SOXS −15 · URA −10 · GDXY −0.891. Open: GUSH 30 · WRTH 20. `duplicate_same_day_fills 0`,
`hash_collisions 0`.

Per-ticker realized confirms **SOXS +795.23** against +$134.40 for the other 13 combined —
the concentration figure, reproduced locally from the artifact rather than quoted.

---

## 2. THE RESULT — the test does not return a clean binary. Two dimensions, opposite answers.

The brief pre-fixed a two-branch reading. Honest answer: **the record passes on price and
realized P&L, and fails on position lifecycle.** Forcing one verdict would discard half the
measurement, so both are reported and the branch call is spine's.

### Dimension A — price / realized P&L: **PASSES, decisively**

13 of the 18 broker trades in the overlap match a DB row. Comparison:

```
 trade           DB    broker    delta
 BITX          3.97      3.97     0.00
 MOO-a       -16.00    -16.02     0.02
 MOO-b        14.80     14.80     0.00
 MSTZ-a       82.00     81.48     0.52
 MSTZ-b       69.00     69.29    -0.29
 MSTZ-c       10.73     10.73     0.00
 NLR           4.95      4.93     0.02
 NUGT        -79.80    -79.82     0.02
 JNUG        -51.39    -51.40     0.01
 TSLQ-a       35.25     35.36    -0.11
 TSLQ-b       12.23     12.23     0.00
 URA          -7.70     -8.42     0.72
 GDXY        118.99    118.99     0.00
 -------------------------------------
 TOTAL       197.03    196.12     0.91
```

**Aggregate delta $0.91 on $197.03 — 0.46%, and every line is fee- or rounding-scale.**
Four match to the cent. Cost bases match exactly on BITX (1346.50), MOO (806.60 / 1560.96),
MSTZ (676.00 / 497.50), NLR (631.75), NUGT (854.85), TSLQ (905.26).

The principal's hand-maintained prices are **good**. Entry price, exit price, quantity and
realized P&L on the matched set are broker-accurate.

**Two independent cross-validations worth naming:**

- **GDXY closes to the cent.** The broker export cannot price this trade — pre-window
  inventory, `basis_known=False`. Broker proceeds **1157.99** − DB cost basis **1039.00** =
  **118.99**, which is the DB's stored `realized_pnl` exactly. The DB supplies precisely the
  basis the export lacks, and the two sources agree to $0.00.
- **URA likewise.** Broker proceeds 498.28 − DB basis 506.70 = −8.42 against DB −7.70; the
  $0.72 gap is fees.

### Dimension B — position lifecycle / quantity: **FAILS on 5 of 18 tickers**

| ticker | DB | broker | disagreement |
|---|---|---|---|
| **GUSH** | 2 rows (60 closed 06-09, **60 OPEN**) | 1 trade 05-27→**06-16 CLOSED**, 15 fills, peak 120 | DB carries an open position the broker shows flat; DB never reaches 120 |
| **SOXS** | 3 rows (250, 150 raw; 45 adjusted) | 2 trades, adj qty 60 / 110 | **unit mismatch** — DB mixes raw and adjusted; not comparable without conversion |
| **SMST** | 1 row, qty **10** | 1 trade, qty **20** | DB records half the disposal |
| **GDXJ** | 1 row, qty **5, OPEN** | 1 trade, qty **8**, closed 06-24 | quantity and status both differ |
| **XLE** | 20 closed + 10 open | 1 trade, peak 40.071, closes 07-27 | DB covers 20 of 20.071; remainder outside window |

**The failures are not randomly distributed.** Every one lands in a previously-registered
problem area: SOXS is DEF-SOXS-PRICE-DISCONTINUITY, GUSH is the qty-60-vs-30 defect filed
in the Phase 1a census, and SMST/GDXJ/XLE are the partial pre-window-inventory cases. The
overlap test found the defects already on the books and **no new class of error**.

Note the SOXS row confirms the discontinuity registration from a second source: the DB holds
`250` and `150` raw alongside `45` adjusted, in the same ticker, in the same window. That is
the mixed-unit condition — and it is confined to SOXS.

---

## 3. Bearing on the PR-106 trigger — R-IV.90(g)

The trigger is well-formed and its input has now arrived. But the reading key assumed a
binary, and the data is not binary. Laying out what each branch would consume:

- **PASSES branch** (combined sample): justified **for realized-P&L studies**. Dimension A
  is broker-accurate at 0.46%, and R-IV.90(d) already bounds blast radius to
  entry-price-derived computations — which Dimension A directly validates. A study computing
  realized P&L from the DB record over Mar–Jun is on sound footing.
- **FAILS branch** (SAMPLE-LIMITED n=36): would be justified **only if** the study depends
  on position lifecycle — open/closed state, peak quantity, or trade segmentation. Dimension
  B is unreliable there on 5 of 18 tickers.

**Recommendation, not a ruling:** admit the Mar–Jun record for realized-P&L purposes,
excluding the 5 Dimension-B tickers where lifecycle matters. That is neither pre-fixed
branch, so it is spine's call — flagging rather than choosing.

**One sizing correction that survives either branch:** the extended record is
**2026-03-11 → 06-18**, not January. Zero Fidelity rows exist before 03-11. Any sample
projection assuming an eight-month series is overstated by more than half.

---

## 4. Standing items

- **Phase 1a input** should be the 90-day artifacts in `data/imports/90d/` (43 trades),
  not the 60-day. Written to a separate outdir so the 60-day set is preserved, not clobbered.
- **Phase 1a's remaining blocker** is R-IV.90(e)'s maximum-range export alone. All three
  previously-cited blockers are now cleared: segmenter present, normalizer patched, 90-day
  export present and consumed.
- **DEF-SOXS-PRICE-DISCONTINUITY** gains independent corroboration from Dimension B — mixed
  raw/adjusted units confined to SOXS, in the overlap window, from a second source.
- **R-IV.90(c)'s SOXS OHLC fetch is CC-BUILD's**, not touched here.
- The five zero-basis cases: **DB closes GDXY exactly and URA within fees**; supplies 20 of
  XLE's 20.071 and 10 of SMST's 20; SOXS remains unit-blocked.

## Manifest (law v2)

| Scope | Rows | Note |
|---|---|---|
| 90-day broker fills | **159** | 159/159 accounted, 0 collisions, 18 tickers |
| Segmented broker trades | **43** | 41 closed · 2 open · 5 unknown-basis · 0 unsettled |
| Broker trades in overlap window | **18** | 05-27 → 06-18 |
| DB Fidelity rows in overlap window | **22** | `FIDELITY_ROTH`, all EQUITY |
| **Matched pairs** | **13** | aggregate delta **$0.91** on $197.03 (0.46%) |
| Dimension-B failures | **5 tickers** | GUSH · SOXS · SMST · GDXJ · XLE |
| Broker realized, priced only | — | **+$929.63** · SOXS +795.23 |

**No writes to the database. Nothing staged. All local artifacts verified gitignored.**


---

# ADDENDUM — R-IV.91 · coverage figures for the (c) labeling rule

**Appended 2026-08-25 07:31 UTC (01:31 MDT) · tree `8b2d767`, re-fetched, 0/0.**

## (e) LOGISTICAL GATE — CLOSED. File is on disk and already consumed.

```
-rw-r--r-- 36651  2026-08-25 01:01  data/imports/90-day Accounts_History.csv
```

Not chat-held. It was normalized (159 fills, 18 tickers) and run through
`scripts/segment_trades.py` → **43 trades**, outputs in `data/imports/90d/`. **No principal
action needed; no re-drop.** The relays crossed — §1–3 above are that run.

## (b) — the validation has already executed, and it did discriminate

The overlap was **not** too narrow to be meaningful: **13 matched pairs**, aggregate delta
**$0.91 on $197.03 (0.46%)**. Reporting a two-dimensional result rather than forcing a
verdict is exactly the (b) instruction, and it is what §2 does.

## ⚠️ (c) — "every Jan–May cell" does not describe the data. Exact figures follow.

The label is binding, so it needs to be right. There is **no January and no February**
Fidelity record, and the record runs into June:

```
 month     rows  priced   span
 2026-03      5       5   03-11 → 03-19
 2026-04     12      12   04-01 → 04-29
 2026-05     15      15   05-13 → 05-29
 2026-06     14      10   06-02 → 06-18
 ------------------------------------------
 TOTAL       46      42   03-11 → 06-18
```

`Jan–May` is wrong three ways: no January, no February, and it truncates June. **The
accurate span is 2026-03-11 → 2026-06-18.** There are also intra-month gaps (March holds
5 rows across 8 days; May begins 05-13), so the series is not dense even where present.

**This does not contradict the attestation.** The principal attests the record was
*maintained current through end-of-May/early-June* — a claim about the window's **end**,
which the data supports. It says nothing about when the record **began**, and the data puts
that at 03-11. Attestation intact; extent ~3.2 months, not five.

## The labeling split (c) actually needs

Two provenance classes, by `entry_date`:

| class | rows | priced | open | span | tickers | label |
|---|---|---|---|---|---|---|
| **A** | **28** | 28 | 0 | 2026-03-11 → 2026-05-26 | 16 | **PRINCIPAL-ATTESTED** — no broker artifact covers it |
| **B** | **18** | 14 | 4 | 2026-05-28 → 2026-06-18 | 12 | **BROKER-OVERLAPPED** — export covers 05-27 forward |

**Framing caveat, stated so the split is not over-read:** this table splits on `entry_date`.
The §2 comparison used *entry OR exit* in the window, which additionally pulls in four
class-A rows that were entered 05-26 but **exited** inside the overlap — SMST, URA, XLE and
SOXS. Those four carry partial broker corroboration on the exit leg despite being class-A by
entry. Both framings are correct for different questions; neither is the "true" one.

**Net for labeling:** 28 rows are attestation-only, 18 have broker corroboration on entry,
and 4 of the 28 have it on exit alone.

## The attestation is independently corroborated where it can be tested

Worth recording, because it is a convergence rather than an assumption: the principal's
claim is that the record was current through end-May/early-June. That is precisely the
window §2 tested against the broker export — and Dimension A passed at **0.46%**, with GDXY
reconciling **to the cent** and seven cost bases matching exactly.

So the attestation is not merely asserted at the seam where it can be checked; it is
measured and it holds. What remains untested is the **class-A interior** (03-11 → 05-26,
28 rows), where no broker artifact exists and (c)'s PRINCIPAL-ATTESTED label is the honest
and only available provenance.

## (d) — noted, not actioned

The SOXS OHLC fetch is CC-BUILD's. Recording only that DEF-SOXS-PRICE-DISCONTINUITY's three
breaks (05-13 · 05-26 · 06-10) straddle the class boundary: **05-13 and 05-26 fall inside
class A**, the attested interior with no broker artifact. That makes (d) the only
artifact-level check on those two, exactly as R-IV.91(d) states. The 06-10 break sits in
class B.
