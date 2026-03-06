"""
Lens Categories — Maps strategies to analytical lens types.

Two signals from the SAME lens are redundant, not confirming.
Two signals from DIFFERENT lenses are confirmation.
Adjacent lenses count as CONFIRMED but at reduced weight toward CONVICTION.
"""

# Strategy name (as it appears in signals.strategy column) -> lens category
LENS_MAP = {
    # Server-side scanners
    "CTA Scanner": "TREND_STRUCTURE",
    "Crypto Scanner": "TREND_STRUCTURE",
    "Exhaustion": "REVERSAL_DETECTION",

    # TradingView webhook strategies
    "Holy_Grail": "MOMENTUM_CONTINUATION",
    "holy_grail": "MOMENTUM_CONTINUATION",
    "Sniper": "MEAN_REVERSION",          # Hub Sniper (VWAP bands)
    "ScoutSniper": "REVERSAL_DETECTION",
    "Scout": "REVERSAL_DETECTION",
    "Whale": "INSTITUTIONAL_FOOTPRINT",
    "absorption_wall": "ORDER_FLOW_BALANCE",
    "AbsorptionWall": "ORDER_FLOW_BALANCE",

    # Context sources (not trade signals yet, but ready for future)
    "UW": "OPTIONS_FLOW",
}

# All CTA Scanner sub-types are ONE lens (TREND_STRUCTURE)
# PULLBACK_ENTRY, RESISTANCE_REJECTION, TWO_CLOSE_VOLUME, GOLDEN_TOUCH,
# TRAPPED_SHORTS, TRAPPED_LONGS, BEARISH_BREAKDOWN, DEATH_CROSS
# = all TREND_STRUCTURE

# Adjacent lens pairs: count as CONFIRMED but NOT as 2 independent lenses
# toward CONVICTION. These strategies measure overlapping things.
ADJACENT_LENSES = {
    frozenset({"TREND_STRUCTURE", "MOMENTUM_CONTINUATION"}),  # CTA + Holy Grail overlap
}

# Fully independent lenses (highest confluence value)
INDEPENDENT_LENSES = {
    "TREND_STRUCTURE",
    "MEAN_REVERSION",
    "REVERSAL_DETECTION",
    "INSTITUTIONAL_FOOTPRINT",
    "ORDER_FLOW_BALANCE",
    "OPTIONS_FLOW",
}


def get_lens(strategy: str) -> str:
    """Map a strategy name to its lens category."""
    return LENS_MAP.get(strategy, "UNKNOWN")


def count_independent_lenses(lenses: set) -> int:
    """
    Count truly independent lenses, treating adjacent pairs as 1.
    
    Example: {TREND_STRUCTURE, MOMENTUM_CONTINUATION, MEAN_REVERSION}
    TREND + MOMENTUM are adjacent (count as 1), MEAN_REVERSION is independent.
    Result: 2 independent lenses.
    """
    independent = len(lenses)
    for adj_pair in ADJACENT_LENSES:
        if adj_pair.issubset(lenses):
            independent -= 1  # Adjacent pair counts as 1, not 2
    return independent
