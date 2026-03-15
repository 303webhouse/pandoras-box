# Adding Components

Read this when adding a new factor, signal source, API endpoint, or analytics feature.

---

## New Factor

1. Create `backend/bias_engine/factors/factor_[name].py` with `compute_score() → float | None`
2. Register in `backend/bias_engine/composite.py` with weight and timeframe category
3. **Weight sum must remain 1.00** — adjust existing weights. Assertion fails on import if sum ≠ 1.00.
4. Factor returns `None` when data unavailable (NOT 0.0)
5. Add collector/cron if factor needs periodic data refresh
6. Add to frontend factor display if user-visible
7. Classify as MACRO, TECHNICAL, FLOW, or BREADTH

## New Signal Source

1. Create webhook handler in `backend/webhooks/[name].py`
2. Register route in `backend/main.py`
3. Add signal type to scoring pipeline
4. Ask Nick if this signal type should go through committee review
5. Update Discord alert formatting

## New v2 Position Endpoint

1. Add to `backend/api/unified_positions.py`
2. **Route ordering matters** — fixed paths (`/summary`, `/greeks`) BEFORE parameterized (`/{position_id}`)
3. Add models to `backend/positions/models.py` if new request/response shapes needed
4. Update committee context in `committee_context.py` if position data affects analysis

## New Analytics Feature

1. Add database tables/queries in `backend/analytics/db.py`
2. Add computation logic in `backend/analytics/computations.py`
3. Add API endpoint in `backend/api/analytics.py`
4. Add UI tab/component in `frontend/analytics.js`
