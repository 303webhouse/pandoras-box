# Brief: Dead Code Cleanup

**Priority:** LOW — Housekeeping, do after all active builds complete.
**Target:** Railway backend + docs
**Estimated time:** 30 minutes

---

## Items to Remove

### 1. Triple Line Strategy (CONFIRMED DEAD)

**Files to delete:**
- `backend/strategies/triple_line.py` (3.4KB) — validation logic, never called

**Code to remove from `backend/webhooks/tradingview.py`:**

Remove the import at the top:
```python
from strategies.triple_line import validate_triple_line_signal
```

Remove the route check in `receive_tradingview_alert()`:
```python
        elif "triple" in strategy_lower or "line" in strategy_lower:
            return await process_triple_line_signal(alert, start_time)
```

Remove the entire `process_triple_line_signal()` function.

Remove this import (ONLY if no other code uses it — grep first):
```python
from bias_filters.tick_breadth import check_bias_alignment
from scoring.rank_trades import classify_signal
```

**Verification before removing imports:**
```bash
grep -r "check_bias_alignment" backend/ --include="*.py" | grep -v "__pycache__"
grep -r "classify_signal" backend/ --include="*.py" | grep -v "__pycache__"
```
If only `tradingview.py` uses them (for the Triple Line handler), they're safe to remove.

### 2. Hybrid Scanner — VERIFY FIRST

The hybrid scanner UI was killed in Brief 09, but the backend is still mounted in `main.py`:
```python
from api.hybrid_scanner import router as hybrid_scanner_router
app.include_router(hybrid_scanner_router, prefix="/api", tags=["hybrid-scanner"])
```

**Before removing, verify no frontend calls:**
```bash
grep -r "hybrid" frontend/ --include="*.js" --include="*.html" | grep -v node_modules
grep -r "/api/hybrid" frontend/ --include="*.js" --include="*.html" | grep -v node_modules
```

If no callers found:
- Remove the two lines from `main.py`
- Move `backend/scanners/hybrid_scanner.py` to `backend/scanners/archive/hybrid_scanner.py` (don't delete — may have reusable logic)
- Move `backend/api/hybrid_scanner.py` to `backend/api/archive/hybrid_scanner.py`

### 3. Old Holy Grail PineScript

`docs/pinescript/holy_grail_pullback.pine` is superseded by `docs/pinescript/webhooks/holy_grail_webhook_v1.pine`.

Move to `docs/pinescript/archive/holy_grail_pullback.pine`.

### 4. Deprecated Functions in tradingview.py

Two functions are marked DEPRECATED:
- `_write_signal_outcome()` — "Use signals.pipeline.write_signal_outcome() instead"
- `apply_signal_scoring()` — "Use signals.pipeline.apply_scoring() instead"

**Before removing, verify they're not called:**
```bash
grep -r "_write_signal_outcome\|apply_signal_scoring" backend/ --include="*.py" | grep -v "__pycache__" | grep -v "DEPRECATED"
```

If only defined but never called from outside the file, they can be removed.

## Files Changed

- `backend/webhooks/tradingview.py` — Remove Triple Line handler + route + imports + deprecated functions
- `backend/strategies/triple_line.py` — DELETE
- `backend/main.py` — Remove hybrid scanner router (if verified dead)
- `docs/pinescript/holy_grail_pullback.pine` — MOVE to archive

## Deployment

Railway auto-deploy on push. Test after deploy:
```bash
curl -s https://pandoras-box-production.up.railway.app/health
```

If the import removal breaks anything, the health check will show `degraded` or the deploy will fail. All removed code is dead (verified in this session), so this should be clean.
