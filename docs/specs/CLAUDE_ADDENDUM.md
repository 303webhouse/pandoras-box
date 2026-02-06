# CLAUDE.md — Addendum (Feb 2026 Bias Engine Rebuild)

> **Add this section to the existing CLAUDE.md**

## Active Build: Composite Bias Engine

The bias system is being rebuilt. Read these specs before working on ANY bias-related code:

| Spec | Location | What it covers |
|------|----------|---------------|
| Architecture & Rules | `PROJECT_RULES.md` | Updated with Composite Bias Engine section — read first |
| Composite Engine | `docs/specs/composite-bias-engine.md` | Backend scoring logic, data models, API endpoints, Redis/Postgres schema |
| Factor Scoring | `docs/specs/factor-scoring.md` | How each of the 8 factors computes its -1.0 to +1.0 score |
| Pivot Data Collector | `docs/specs/pivot-data-collector.md` | What the OpenClaw agent pulls and when |
| Bias Frontend | `docs/specs/bias-frontend.md` | UI changes, CSS, JS rendering logic |

### Build Order (recommended)
1. **Composite Engine** — `backend/bias_engine/composite.py` + DB table + API endpoints
2. **Factor Scoring** — Add `compute_score()` to each `backend/bias_filters/*.py`
3. **Frontend** — Update bias display to read from `/api/bias/composite`
4. **Pivot integration** — Connect OpenClaw data collector (separate system)

### Key Architecture Decisions
- **New directory:** `backend/bias_engine/` — do NOT put composite logic in existing `bias_filters/`
- **New endpoints:** Add to existing `backend/api/bias.py` — don't create new router file
- **Existing endpoints:** Do NOT remove `/api/bias/{timeframe}` — keep backward compatible
- **Existing bias_filters:** Do NOT modify their current behavior — add `compute_score()` as a NEW function alongside existing code
- **All factor scores:** -1.0 (max bearish) to +1.0 (max bullish), mapped to 5-level system
- **Graceful degradation:** System MUST work with any subset of factors (redistribute weights)

### New API Endpoints
```
GET  /api/bias/composite          — Full composite bias with factor breakdown
POST /api/bias/factor-update      — Pivot POSTs new factor data (triggers recompute)
POST /api/bias/override           — Manual bias override
DELETE /api/bias/override         — Clear override
GET  /api/bias/history?hours=72   — Historical readings
POST /api/bias/health             — Pivot heartbeat
```

### New WebSocket Message
```json
{"type": "BIAS_UPDATE", "data": {"bias_level": "URSA_MAJOR", "composite_score": -0.68, ...}}
```
