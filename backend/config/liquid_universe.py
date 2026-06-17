"""L0.2 — Liquid-ticker allowlist.

The single maintained source of truth for "is this ticker in the liquid
universe?" The L0 foundation uses this to route signal_types whose edge is
liquidity-conditional (per the signal-edge validation).

Why an allowlist (not a fire-time liquidity calc): the `signals` table has no
liquidity / ADV field, so there is nothing to threshold at fire time. The
validation found the edge lives in a small, stable set of large-cap / index
names, so a curated allowlist is both sufficient and auditable. `non-liquid`
is defined as **NOT in this list** — there is no middle state.

Membership source (docs are the source of truth, not memory):
  - `docs/strategy-reviews/signal-edge-validation-2026-06-16.md` (T10 sector cut):
      * index_macro  : SPY, QQQ, IWM, HYG, TLT, FXI   (exhaustive in the doc)
      * semis_ai_tech: "incl. MSFT/XLK/GOOGL/ZS"        (the +0.817 bucket)
  - The exhaustive semis_ai_tech ticker list from the T10 SQL was NOT committed
    to the repo. The semis/tech members below are the curated reconstruction
    from `docs/codex-briefs/2026-06-17-L0-foundation-build-brief.md` §L0.2,
    consistent with the doc's category ("mega-cap software + semi/tech ETFs +
    NVDA/semis/memory") and its explicitly-named members. Treat the semis/tech
    set as **provisional — ratify against the original T10 query before the
    L0.1a enforce flip.** index_macro is doc-exhaustive and settled.

Consumers:
  - L0.1a suppression gate: `RESISTANCE_REJECTION` is suppressed only when
    `not is_liquid(ticker)` (+0.73 liquid / -1.76 single-name — the universe
    effect is signal_type-specific, see the CTA decompose doc).
  - L0.3 (later): `APIS_CALL` fires on non-liquid only (the opposite effect).
"""

from __future__ import annotations

from typing import Optional

# Index / macro ETFs — exhaustive per the validation doc (57.8% WR, +0.784, n=427).
INDEX_MACRO: frozenset[str] = frozenset({
    "SPY", "QQQ", "IWM", "HYG", "TLT", "FXI",
})

# Semis / AI / mega-cap tech — the +0.817 bucket (n=563). PROVISIONAL
# reconstruction (see module docstring); ratify against the T10 query before
# enforce. Doc-named members (MSFT, XLK, GOOGL, ZS) plus the brief's §L0.2 list.
SEMIS_AI_TECH: frozenset[str] = frozenset({
    "NVDA", "SMH", "XLK", "MSFT", "META", "AMZN", "GOOGL",
    "AAPL", "AVGO", "AMD", "TSLA", "ISRG", "INTU", "ZS",
})

# The full liquid universe = union of the validated positive buckets.
LIQUID_UNIVERSE: frozenset[str] = INDEX_MACRO | SEMIS_AI_TECH


def normalize_ticker(ticker: Optional[str]) -> str:
    """Normalize a raw ticker for allowlist comparison.

    Upper-cases and strips surrounding whitespace. Returns "" for None / blank
    so callers get a deterministic miss rather than an exception.
    """
    if not ticker:
        return ""
    return ticker.strip().upper()


def is_liquid(ticker: Optional[str]) -> bool:
    """True iff `ticker` is in the liquid universe (case-insensitive).

    A blank / None ticker is treated as non-liquid (returns False).
    """
    return normalize_ticker(ticker) in LIQUID_UNIVERSE


def apis_eligible(ticker: Optional[str]) -> bool:
    """L0.3 — whether a ticker is eligible for the APIS_CALL label.

    APIS edge is non-liquid-only (LIVE 2026-06-17: liquid n=93 avg -0.126;
    non-liquid n=62 avg +1.273), so eligibility is simply `not is_liquid`.
    A blank/None ticker is treated as non-liquid → eligible.
    """
    return not is_liquid(ticker)
