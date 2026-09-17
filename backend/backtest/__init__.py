"""The backtest module — v1 (R-IV.429(b); Titans review 2026-04-23, locked architecture).

It GRADES WHAT THE SHADOWS HAVE ALREADY COLLECTED, and it runs a pure strategy over history.
Two acceptance tests are its founding requirements, not later hardening:

  #1 (R-IV.423(d))  it grades the 3-10 and Pass 9 shadows, whose figures CC-QUERY has measured
                    independently (R-IV.424) -- the module is accepted when an independent read
                    agrees with it, not when its own tests pass.
  #2 (R-IV.425(a), R-IV.428(d))  it reports the TRUE return across corporate actions: the six
                    known-answer cases BKNG, KORU, CRWD, SPGI, APH, FUBO.

FOUNDING RULES (DEF-ADJUSTED-BARS-VS-RAW-ENTRY, R-IV.428(a)):
  * Every bar fetch states its adjustment. The basis is recorded on every graded row.
  * A raw entry price is never compared with an adjusted series. It is converted onto the
    fetched series' basis, and the conversion is VERIFIED against the fire session's own bar
    rather than trusted from the vendor's calendar (which lists at least one factor its own
    closes do not carry).
  * A grade, once written, is never rewritten. A row graded on another basis is left alone
    and counted.
  * A missing bar is a missing bar: no neighbouring close is borrowed, and a vendor hole on
    a trading day is reported as one.

LAYERS
  sessions     anchor session and T+n, from the one market calendar
  bars         yfinance daily, split-adjusted, dividends excluded, with the split calendar
  basis        entry conversion and its verification; the adjustment-seam detector
  grade        return-type and walk-type grades (pure)
  metrics      cell summaries, R metrics, block bootstraps, strata (pure)
  populations  which rows each shadow collected, and their cells
  store        shadow_grades (insert-only), backtest_runs, backtest_results
  engine       a pure strategy over history, bar by bar (no lookahead by construction)
  job          the post-close grading pass
  __main__     CLI: python -m backtest ...
"""

GRADER_VERSION = "sg-v1"
