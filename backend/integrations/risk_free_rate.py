"""Risk-free rate constant for Black-Scholes computation.

Sourced from US Treasury daily T-bill rates (3-month / 13-week).
Source URL: https://home.treasury.gov/resource-center/data-chart-center/interest-rates/

ROTATION DISCIPLINE: update this constant quarterly (or after significant
Fed moves). Last updated: 2026-05-29. Next review: 2026-08-29.

Why a constant and not a live fetch: keeps Greeks computation credential-free
and dependency-free. Quarterly drift on the 3M T-bill is small enough (a few
basis points) that it doesn't meaningfully affect Greeks for the DTE range
DAEDALUS reads (typically <90 days). Live-fetching would add a new caller path
and undermine the "no new credentials" virtue of Tier 2.
"""

# 3-month T-bill (13-week) bank discount rate as of 2026-05-29: 3.68%
RISK_FREE_RATE_3M: float = 0.0368
