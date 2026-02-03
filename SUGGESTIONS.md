**Current State**
Trade Ideas are displayed from the active signal feed, and positions are tracked in-memory with database persistence for open positions. Signal archiving is handled via the `signals` table, and positions are captured in the `positions` table. The UI flow covers signal accept/dismiss and position close with P&L calculations.

**Issues / Inefficiencies**
1. Trade Ideas pagination and the primary active feed are backed by different query paths (Redis/merged vs. DB-only), which can surface inconsistencies for deduping, scoring, and ordering.
2. Closed position history is only stored in memory (`_closed_trades`) for the API, which means history is lost on restart and forces DB/archival queries outside the UI.
3. Bias summary coverage is limited (Savita only) while other bias indicators are calculated elsewhere, reducing archival completeness and clarity.
4. Signal display can show multiple strategy variants without a unified grouping strategy across all endpoints, which can clutter the Trade Ideas list.
5. Data integrity depends on in-memory IDs when DB inserts fail, which can break downstream actions after reloads.

**Recommended Improvements (Prioritized)**
1. Unify Trade Ideas sourcing by creating a single pagination-aware endpoint that handles scoring, deduping, and ordering consistently for both initial load and “Reload previous”.
2. Add a database-backed closed positions endpoint and update the UI to use it (ensures persistence and improves backtesting consistency).
3. Expand `/api/bias/summary` to include VIX, put/call, breadth, and other existing bias filters for richer archival snapshots.
4. Standardize signal grouping rules (by ticker + timeframe + strategy) to reduce duplicates and make the feed more actionable.
5. Add a safe fallback when DB writes fail (expose status in UI) so users know if a trade won’t be archived.

**Quick Wins**
1. Show “has more”/count metadata in the Trade Ideas UI so users know how many older ideas remain.
2. Add a “View archived positions” quick link in the Open Positions panel.
3. Cache bias snapshots for a short TTL to reduce repeated bias-summary computation during high alert bursts.
