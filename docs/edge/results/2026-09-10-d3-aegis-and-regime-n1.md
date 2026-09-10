# D3 · AEGIS SCAN · REGIME n=1 — 2026-09-10

**FROM:** CC-BUILD · **TO:** spine · **cc:** EDGE
**Read:** 2026-09-10, read-only.

---

## D3 — PASSES

**The acceptance test for the whole grader-precondition build.**

```
last deploy      c38df2d9   2026-09-08 20:02:31 UTC  (16:02 ET Tue)
deploys since    NONE       Wed 09-09 and Thu 09-10 both deploy-free

grader run       session_date 2026-09-10
                 started  20:39:01.795  finished 20:39:06.108   (4.3 s)
                 status   ok
                 timeouts {count: 0}
sentinel         registered true · status ok · last_persist_age_s 6647
```

**A scheduled pass ran on a day with no deploy in the window.** That is the criterion,
and it is met — **on the second consecutive deploy-free day**, not the first.

**This is the first time the grader has been shown to run on the SCHEDULE rather than on a
RESTART**, which was the whole defect. Since 07-31 every observed pass had a deploy behind
it; the proof `GRADE_LIMIT`=1000 against 1,862 rows graded on 08-27 is what made the
restart-driven hypothesis measurable. **Today it ran with nothing behind it.**

### The backlog is growing, and that is the OTHER defect working correctly

```
2026-09-08   skip_reason no_regular_session_bars=650
2026-09-10   skip_reason no_regular_session_bars=944      +294
```

**The grader is healthy and grading nothing**, because `DEF-UW-OHLC-DEAD` is still live and
the grader is on Path A. **The two defects remain separately visible**, which is the
property R-IV.288(b)/R-IV.310 preserved by refusing to merge them. **T4's reason is what
makes the growth legible at all** — without it this reads as 944 rows nobody looked at.

---

## AEGIS SCAN (R-IV.338(c)) — CLEAN, after a near-miss worth recording

**Result: 0 hits across 15 served files, 1,348,269 bytes** — `app.js`, `index.html`,
`styles.css`, `cockpit.js`, `laboratory.js`, `knowledgebase.js`, manifest, assets.

Patterns: OpenAI-style keys, GitHub/GitLab/Slack tokens, AWS access-key ids, bearer
headers, `key|secret|token|password` assignments, Postgres and Redis DSNs, PEM private-key
headers, and the account identifier.

### THE NEAR-MISS — the first scan reported 26 hits, and every one was false

**The first pass used `(sk-|ghp_|…)[A-Za-z0-9_\\-]{8,}` with no left boundary. It matched
`sk-` INSIDE the word `risk-`:**

```
.risk-calc-preview     ->  matched as "sk-calc-preview"
.risk-preview-line     ->  matched as "sk-preview-line"
```

**26 CSS class names, reported as API keys.** Filing that would have opened a credential
incident over a stylesheet.

**Corrected by requiring a left boundary** — `(?<![A-Za-z0-9_-])sk-[A-Za-z0-9]{20,}` — and
a realistic key length. **Result went 26 → 0.**

**Probe-coverage family, and the most dangerous instance yet**, because the artifact was
FALSE POSITIVE on a security surface rather than a false negative. **A scan that cries wolf
is retired by its readers**, and the next real hit goes unread.

---

## REGIME n=1 (R-IV.340(a)(2)) — and it is not n=2, it is ONE

**Live, 2026-09-10:**

```
regime_label  "RISK-OFF"
breadth       total 1 · up_3 0 · down_3 0
              pct_above_50dma 0.0 · pct_above_200dma 0.0 · pct_above_20dma 0.0
```

**The label is derived from ONE ticker.** `pct_above_50dma = 0.0` is 0 of 1, which is below
the 40 threshold, which yields **RISK-OFF**. **A single instrument below its 50-day average
is currently producing the board's regime.**

### FEED or FILTER — answered: the filter is correct, its input is starved

`get_regime_read()` (`scoring.py:198-228`) computes breadth from **`stable_metrics` at
`MAX(date)`**, joined to `stable_universe`, excluding `Benchmark`, `Scan Only`,
`Sector ETF`. **The exclusion list is deliberate and correct.** `total = 1` means the
metrics table holds **one qualifying row at its latest date.**

**That points straight at `DEF-STABLE-NIGHTLY-SUCCEEDS-WITHOUT-ADVANCING`** (filed
2026-09-09): the nightly reports success while `stable_daily_bars` ends 09-04. **A metrics
table with one row at MAX(date) is what a partially-written day looks like.** Not proven
here to be the same cause; named because the two are one day apart and the shapes match.

### Do THEME scores share that universe? Yes on one anchor, unverified on the other

**PROVISIONAL anchor — YES, BY CONSTRUCTION.**
`compute_provisional_theme_scores()` (`live.py:69-105`) filters once and uses it twice:

```
live.py:75    base = base[base["ticker"].isin(live.keys())]     <- the filter
live.py:88    scan = base[~base["theme"].isin(EXCLUDED_THEMES)]  -> breadth_counts
live.py:105   for theme, group in base.groupby("theme")          -> theme scores
```

**One DataFrame, seventeen lines apart.** Whatever starves the breadth count starves every
theme score computed on that anchor, identically and silently.

**CLOSE anchor — NOT VERIFIED HERE.** The served `dominant`/`emerging` lists come from
stored `stable_theme_scores` rows, and **which anchor is served on this endpoint was not
established.** Stated as a gap rather than assumed either way — this lane has been wrong
twice this week by inferring a runtime path from a static read (conventions #14).

**What the payload shows regardless:** confident theme scores served alongside a breadth
count of 1 — `Crypto Equities 77.6 DOMINANT`, `Metals 69.3 EMERGING`, `Memory 58.5`,
`Nuclear 44.9`. **Nothing in the payload tells a reader the breadth behind them is one
ticker.**
