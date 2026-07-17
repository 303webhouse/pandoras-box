# TITANS BRIEF — PYTHIA MP feed reliability: per-name freshness monitor + feed-shed root-cause

**Date:** 2026-06-29 · **Lane:** Foundation / committee-feed reliability · **Status:** FOR TITANS REVIEW (not yet built)
**Origin:** Olympus verdict on the L1a week-1 review (`docs/strategy-reviews/2026-06-29-L1a-week1-shadow-review.md`). Re-arming the v2.4 watchlist alert is **triage**; this brief is the **durable fix**.
**Recon anchor:** `origin/main` @ `2617c31`.

## Problem (evidenced)
The PYTHIA Market-Profile feed (TradingView Pine v2.4 → `/webhook/tradingview` → `pythia_events`) **silently decayed from 191 distinct tickers/day (2026-06-10) to 23 (2026-06-29)** — a ~12–15 tickers/day bleed. SPY's last MP event was **2026-06-17** (dead 12 days), HYG since April; 13 of the 20 L1a-liquid names went dark. This starved the L1a auction half (`fresh_accepted` = 2/53 in shadow week 1, `pass` fired once). **It went undetected for 19 days** because the only monitor — the L1a/Chunk-3 feed-down watchdog (`config/l1_gate.py::_maybe_mp_feed_down_alarm`, mirrored from the flow watchdog) — checks **GLOBAL** `MAX(timestamp) FROM pythia_events`. The surviving megacaps (AAPL/AMZN/NVDA/QQQ/META/AVGO/XLK) kept the global timestamp fresh, so the alarm never fired while 90% of the watchlist died. This is the second decay (the B4 closure note, `docs/strategy-reviews/b4-pythia-feed-closure-note-2026-06-10.md`, recorded a prior decay to 3 tickers, re-armed to 190) → recurring, not a one-off.

## Objective — two parts
### Part 1 — Per-name MP-freshness monitor (alerting only; no gate behavior change)
- Detect when a **tracked** name (priority: the 20 in `config/liquid_universe.LIQUID_UNIVERSE`) goes stale even while other names are fresh — the blind spot the global alarm has.
- Likely shape: an independent watchdog (mirror the Chunk-3 `flow_deadfeed_watchdog_loop` in `main.py`), RTH-gated, debounced, **per-name latch**, reusing `bias_engine.anomaly_alerts.send_alert`. Alarm when a liquid-20 name's latest `pythia_events` age exceeds a threshold during RTH (threshold configurable; start ~1 trading session / propose in Phase-0). Recovery alert on restore.
- AEGIS: alarm bodies carry ticker + age only — no secrets/DSN/payloads.

### Part 2 — Feed-shed root-cause + mitigation
- Investigate **why** the TradingView watchlist alert sheds symbols over days. Hypotheses to confirm/reject: Pine `request.security()` per-script call cap (~40–64 in v5/v6) so a 190-symbol scan can't all compute; TradingView alert runtime/expiry limits; watchlist-symbol cap; account alert-tier cap. The decay floor (~20–50) is a clue.
- Deliverable: identified mechanism + a mitigation that holds coverage durably — candidates: split into N alerts under the per-script cap; reduce the watchlist to a stable priority set (liquid-20 + committee names) within limits; a scheduled auto-re-arm; or migrate MP computation hub-side (compute profile from UW/bars rather than depend on a TradingView alert at all — largest scope, flag for separate evaluation).

## Guardrails
- Part 1 is **alerting only** — does NOT change L1a gate logic or any signal path. Part 2 root-cause is read-only investigation; any Pine/alert change is operational (Nick-side TradingView), code changes (if any) shadow-by-default.
- No UW budget impact (`pythia_events` is webhook-fed, not UW). No new credential surface (reuses existing webhook + `send_alert`).
- Do NOT couple this to the L1a enforce decision — L1a stays shadow regardless (Olympus).

## Titans review requested
- **ATLAS** (feed reliability / data integrity — the monitor design + the root-cause mitigation tradeoffs; is hub-side MP computation worth scoping?).
- **AEGIS** (alarm hygiene, no-secrets, debounce/latch correctness).
- **HELIOS** abstain (no Agora surface).

## Out of scope (explicitly)
- The immediate **re-arm** (Olympus directed it as triage — Nick-side TradingView delete+recreate of the v2.4 alert).
- **Option B** (decouple L1a auction → flow-primary) — Olympus is HOLDING B; when revisited, its merge gate is **"`fired_mode` recorded on every gate pass."**
