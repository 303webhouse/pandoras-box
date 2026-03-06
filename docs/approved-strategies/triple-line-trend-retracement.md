# Triple Line Trend Retracement — SCRAPPED

**Status:** REJECTED (March 6, 2026)

This strategy has been scrapped. It never generated a single Trade Idea — no PineScript webhook was ever built for it, and the backend handler (`process_triple_line_signal`) received zero signals.

See `docs/strategy-backlog.md` for details.

## Dead Code to Remove

- `backend/strategies/triple_line.py` — validation logic (3.4KB)
- `backend/webhooks/tradingview.py` — `process_triple_line_signal()` handler and `from strategies.triple_line import validate_triple_line_signal` import
- `backend/bias_filters/tick_breadth.py` — `check_bias_alignment()` is only called by the Triple Line handler
