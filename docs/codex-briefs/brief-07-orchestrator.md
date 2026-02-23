# Brief 07 — Orchestrator Guide for Claude Code

**Read this first.** This tells you how to split the work across sub-agents.

## Dependency Graph

```
Phase 1 (SERIAL — must complete first):
  07-P1: Database migrations (4 new tables + seed data)

Phase 2 (PARALLEL — all independent, run simultaneously):
  07-A: RH CSV parser + CLI import script
  07-B: Portfolio API endpoints (backend/api/portfolio.py)
  07-C: "Pivot II" → "Pivot" rename (text-only, no code logic)
  07-D: Pivot screenshot parsing rules doc (standalone markdown)

Phase 3 (SERIAL — needs 07-B's API endpoints):
  07-E: Frontend UI (account balance box + positions table)

Phase 4: Deploy + verify
```

## Sub-Brief Files

All sub-briefs are at `docs/codex-briefs/brief-07-*`:

| File | Sub-agent | Touches |
|------|-----------|--------|
| `brief-07-P1-db-migrations.md` | Phase 1 | `backend/database/postgres_client.py` |
| `brief-07-A-rh-csv-parser.md` | Phase 2 | `backend/importers/` (new dir) |
| `brief-07-B-portfolio-api.md` | Phase 2 | `backend/api/portfolio.py` (new), `backend/main.py` |
| `brief-07-C-rename-pivot.md` | Phase 2 | All `.md`, `.py`, `.html`, `.js` files |
| `brief-07-D-screenshot-rules.md` | Phase 2 | `docs/pivot-knowledge/` (new dir, VPS deploy later) |
| `brief-07-E-frontend-ui.md` | Phase 3 | `frontend/index.html`, `frontend/app.js`, `frontend/styles.css` |

## Critical Context for All Sub-Agents

- **Repo:** `303webhouse/pandoras-box`, branch `main`
- **Local clone:** `C:\trading-hub` — the ONLY one
- **Railway auto-deploys on push to `main`**
- **Router pattern in `main.py`:** `from api.X import router as X_router` → `app.include_router(X_router, prefix="/api", tags=["tag"])`
- **DB init:** `backend/database/postgres_client.py` has `init_database()` called at startup — add CREATE TABLE IF NOT EXISTS there
- **Existing positions files:** `backend/api/positions.py` (70KB) and `backend/api/options_positions.py` (18KB) already exist. The NEW portfolio endpoints go in a SEPARATE file `backend/api/portfolio.py` to avoid conflicts
- **Frontend files are huge:** `index.html` (121KB), `app.js` (361KB), `styles.css` (197KB). Use targeted edits, not full rewrites
- **Auth pattern:** `PIVOT_API_KEY` in `X-API-Key` header
- **Commit convention:** `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`

## Conflict Zones

These files are touched by multiple sub-agents — coordinate carefully:

| File | Touched By | Risk |
|------|-----------|------|
| `backend/main.py` | 07-B (add router) | Low — just add 2 import lines + 1 include_router |
| `backend/database/postgres_client.py` | 07-P1 (add tables) | Low — append to init_database() |
| `CLAUDE.md` | 07-C (rename) | Low — text replace only |
| `DEVELOPMENT_STATUS.md` | 07-C (rename) + post-build update | Medium — do rename first |

## Verification After All Phases

```bash
# 1. Tables exist
curl https://pandoras-box-production.up.railway.app/api/portfolio/balances
# Should return 4 account rows

# 2. Positions endpoint works
curl https://pandoras-box-production.up.railway.app/api/portfolio/positions
# Should return empty array (no positions seeded yet)

# 3. No "Pivot II" references
grep -r "Pivot II\|Pivot 2" --include="*.md" --include="*.py" --include="*.html" --include="*.js" .
# Should return nothing

# 4. Frontend loads with new balance box
# Visit https://pandoras-box-production.up.railway.app/app and verify layout
```
