# RELAY — CC-CLOUD → CC-BUILD · Overnight futures feed + session on RTH envelopes (2026-09-30)

**From:** CC-CLOUD (cloud session). Nick asked for this to be built here while the local lanes were rate-limited.
**To:** CC-BUILD (backend owner), cc CC-ABACUS (frontend half), SPINE
**Branch:** `claude/sharp-faraday-pd9x1j`. Nothing is merged or deployed; it is held for the PM conflict review.
**Why you care:** everything below is in your files. Review it before it merges.

## Nick's ask
"A lot of day traders I follow seem to pay a lot of attention to overnight futures." He chose:
- % moves are measured from the **4 PM ET stock close**.
- The Agora index bar **turns into a futures bar outside regular hours and flips back at the open**.
- Tiles that stop updating after hours **grey out**.

## What changed (by function)
| File | Change |
|---|---|
| `stable_engine/ext_hours.py` | **New.** |
| `stable_engine/db.py` | New table `stable_ext_quotes`, added with `CREATE TABLE IF NOT EXISTS` (additive). One row per symbol; `spark` is JSON text. A separate table because `stable_live_strip` is keyed on symbol alone, so an extended-hours SPY row there would overwrite the regular one. |
| `jobs/stable_jobs.py` | `stable_ext_hours_loop()`: every 300 s when `session_at(now) != regular` and `window_open(now)`. Wrapped in `_record("ext_hours", …)`. |
| `main.py` | Starts the loop beside the other stable loops. |
| `stable_engine/job_status.py` | `SLO_SECONDS["ext_hours"] = 30 min`, `JOB_FEEDS["ext_hours"]`, and `OFF_HOURS_FEEDS` + `_off_hours_flatline()`. |
| `api/stable.py` | **New `GET /api/stable/futures`.** |
| `stable_engine/sessions.py` | `envelope_session_fields(instant=None)` → `{market_session, session}`. |
| `services/read_only/stable.py` | `_envelope(..., feed="strip"|"movers")` now adds `market_session` + `session`. Affected reads: index-strip, sector-divergence, rates, fx, movers. |
| `services/read_only/board.py` | `get_tide()` adds the same two fields. |
| `tests/test_ext_hours.py` | **New.** 22 tests. |

**`stable_engine/ext_hours.py`:**
- `fetch()` makes 2 batched yfinance calls per tick: 5-minute bars with extended hours for ES/NQ/RTY/YM/CL/ZN futures plus SPY/QQQ/IWM/DIA, and a daily frame for the ETFs' official closes.
- `compute_rows()` is pure, so it can be tested on recorded frames.
- `base_session()`, `window_open()`, `futures_open()` answer "measured from which close" and "is there anything to fetch / are futures open".
- `run_ext_hours_update()` is the entry point the loop calls.
- Zero UW calls. It adds about 400 Yahoo requests on a weekday (2 per tick).

**`stable_engine/job_status.py`:** the feed is flagged dead only when it should be flowing (outside RTH, fetch window open) and has been quiet past the SLO since the window re-opened. An unreadable calendar exempts it rather than accusing it.

**`GET /api/stable/futures`:**
- Returns `futures[]`, `etfs[]`, `market_session` (THE calendar, now) and `session` (the futures market's own open/closed).
- Also `data_delay_minutes: 10`, `base_session_expected`, `stale_base[]` and `unresolved[]`.
- `as_of` = newest futures bar.
- It uses `feed="ext_hours"` for the flatline check.

**`services/read_only/stable.py`:** the `session` word is `'open'|'closed'|null`, the vocabulary v2.js `healthState` already reads. It fixes the known "every dot turns amber after hours" finding; nothing changes for nightly feeds.

**`tests/test_ext_hours.py`:** 22 tests covering:
- which close the base comes from: Tue night, Mon pre-market, Sunday, the day after Labor Day, and 16:00:00 exactly;
- the fetch and futures windows;
- that the base is the bar ending at 16:00, with a fallback limited to 15:45–15:55;
- the delayed-feed wait;
- the ETF official close read by date;
- no zeros for missing data;
- the off-hours flatline.

## Decisions baked in (flag any you disagree with)
1. **Futures base** = the close of the 5-minute bar that ends at 16:00 ET (stamped 15:55). That is the price at the stock close, not the CME settlement. Measured 09-29: ES 7732.50 vs settlement 7732.00.
2. **ETF base** = the official daily close for that session, read by DATE. Converting Yahoo's midnight daily stamp through UTC lands on the previous day, which was a real bug in the first draft; a test now covers it.
3. **Base recomputed every tick** from the bars, never stored, so a restart or a late 15:55 bar cannot strand a stale base.
4. **Waiting at the close.** A futures bar newer than the base doesn't exist yet in roughly the first 10 minutes after 16:00, because of the delay. The row then carries a reason starting `ext_hours.WAITING`, and the read does not degrade on it.
5. **Loop gate** uses `sessions.session_at` (THE calendar), not `stable_jobs.is_rth`, whose disagreement with the calendar is documented in `sessions.py`. A `None` session fetches anyway, since a wasted request is cheaper than a dark bar.

## Known limits
- The data is about 10 minutes delayed. Pre- and after-hours ETF volume is thin.
- A quarterly contract roll inside the window jumps by the calendar spread.
- Early closes aren't modelled (the calendar doesn't model them either).
- CME holiday hours aren't modelled; the reading's own age shows the quiet.

## Local environment note (not a code finding)
In the cloud container, `pip install -r backend/requirements.txt` resolves to `yfinance 0.2.59` + `websockets==12.0`. yfinance then fails to import (`websockets.asyncio` missing; it needs websockets ≥ 13).

Production's strip works, so Railway evidently resolves a compatible pair. The pin is worth checking the next time requirements are rebuilt.

## Verification done
- `pytest tests/test_ext_hours.py`: 22 passed.
- Full backend suite, before vs after: identical failure set (44 failed / 456 errors, all from the container having no DB or `pandas_ta`), with +22 passes.
- Live dry run of `ext_hours.fetch()` from the container, with no DB writes: all 10 rows resolved (ES +0.13%, SPY after-hours +0.25% vs the 764.20 official close).
- `/api/stable/futures` exercised against a fake pool.
