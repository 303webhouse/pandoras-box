"""
Position risk calculator — pure functions for max loss, max profit, breakeven, direction.
Used by the unified positions API and by the Pivot position manager skill.
"""

from typing import Optional


def _is_debit_iron_condor(legs: list) -> bool:
    """
    Detect whether an iron condor is debit (long) or credit (short) from leg actions.

    Debit IC: BUY the inner strikes (higher put, lower call), SELL the outer strikes.
    Credit IC: SELL the inner strikes, BUY the outer strikes.

    Returns True if debit (long), False if credit (short/standard).
    """
    put_legs = [l for l in legs if l.get("option_type", "").upper() == "PUT"]
    call_legs = [l for l in legs if l.get("option_type", "").upper() == "CALL"]

    if len(put_legs) < 2 or len(call_legs) < 2:
        return False  # can't determine, assume credit

    # Sort puts by strike descending (higher = inner for IC)
    put_legs_sorted = sorted(put_legs, key=lambda l: l["strike"], reverse=True)
    # Sort calls by strike ascending (lower = inner for IC)
    call_legs_sorted = sorted(call_legs, key=lambda l: l["strike"])

    inner_put_action = (put_legs_sorted[0].get("action") or "").upper()
    inner_call_action = (call_legs_sorted[0].get("action") or "").upper()

    # If inner strikes are bought → debit iron condor
    return inner_put_action == "BUY" and inner_call_action == "BUY"


def calculate_position_risk(
    structure: str,
    entry_price: float,
    quantity: int,
    long_strike: Optional[float] = None,
    short_strike: Optional[float] = None,
    legs: Optional[list] = None,
) -> dict:
    """
    Calculate max_loss, max_profit, breakeven, and direction from position structure.

    Args:
        structure: Position type (e.g. "long_call", "put_credit_spread", "iron_condor", "stock")
        entry_price: Net premium per contract (positive = credit received, negative = debit paid)
                     For stock: price per share.
        quantity: Number of contracts (options) or shares (stock)
        long_strike: Protective leg strike (for spreads)
        short_strike: Risk leg strike (for spreads)
        legs: Raw leg data for iron condors (list of dicts with strike, option_type, action)

    Returns:
        dict with max_loss, max_profit, breakeven (list), direction
    """
    s = structure.lower().replace("-", "_").replace(" ", "_") if structure else "unknown"
    multiplier = 100  # options contract multiplier

    # --- Stock positions ---
    if s in ("stock", "stock_long", "long_stock"):
        return {
            "max_loss": round(entry_price * quantity, 2),  # full loss if goes to 0
            "max_profit": None,  # unlimited upside
            "breakeven": [entry_price],
            "direction": "LONG",
        }

    if s in ("stock_short", "short_stock"):
        return {
            "max_loss": None,  # unlimited (price can go to infinity)
            "max_profit": round(entry_price * quantity, 2),  # max if goes to 0
            "breakeven": [entry_price],
            "direction": "SHORT",
        }

    # --- Single options ---
    if s in ("long_call",):
        premium = abs(entry_price)
        return {
            "max_loss": round(premium * multiplier * quantity, 2),
            "max_profit": None,  # unlimited
            "breakeven": [round(long_strike + premium, 2)] if long_strike else [],
            "direction": "LONG",
        }

    if s in ("long_put",):
        premium = abs(entry_price)
        return {
            "max_loss": round(premium * multiplier * quantity, 2),
            "max_profit": round((long_strike - premium) * multiplier * quantity, 2) if long_strike else None,
            "breakeven": [round(long_strike - premium, 2)] if long_strike else [],
            "direction": "SHORT",
        }

    if s in ("short_call", "naked_call"):
        premium = abs(entry_price)
        return {
            "max_loss": None,  # unlimited — flag high risk
            "max_profit": round(premium * multiplier * quantity, 2),
            "breakeven": [round(short_strike + premium, 2)] if short_strike else [],
            "direction": "SHORT",
        }

    if s in ("short_put", "naked_put", "cash_secured_put"):
        premium = abs(entry_price)
        return {
            "max_loss": round((short_strike - premium) * multiplier * quantity, 2) if short_strike else None,
            "max_profit": round(premium * multiplier * quantity, 2),
            "breakeven": [round(short_strike - premium, 2)] if short_strike else [],
            "direction": "LONG",
        }

    # --- Vertical spreads ---
    if s in ("put_credit_spread", "bull_put_spread"):
        # Sell higher put, buy lower put — bullish
        if long_strike is not None and short_strike is not None:
            width = abs(short_strike - long_strike)
            premium = abs(entry_price)
            return {
                "max_loss": round((width - premium) * multiplier * quantity, 2),
                "max_profit": round(premium * multiplier * quantity, 2),
                "breakeven": [round(short_strike - premium, 2)],
                "direction": "LONG",
            }

    if s in ("put_debit_spread", "bear_put_spread"):
        # Buy higher put, sell lower put — bearish
        if long_strike is not None and short_strike is not None:
            width = abs(long_strike - short_strike)
            premium = abs(entry_price)
            return {
                "max_loss": round(premium * multiplier * quantity, 2),
                "max_profit": round((width - premium) * multiplier * quantity, 2),
                "breakeven": [round(long_strike - premium, 2)],
                "direction": "SHORT",
            }

    if s in ("call_credit_spread", "bear_call_spread"):
        # Sell lower call, buy higher call — bearish
        if long_strike is not None and short_strike is not None:
            width = abs(long_strike - short_strike)
            premium = abs(entry_price)
            return {
                "max_loss": round((width - premium) * multiplier * quantity, 2),
                "max_profit": round(premium * multiplier * quantity, 2),
                "breakeven": [round(short_strike + premium, 2)],
                "direction": "SHORT",
            }

    if s in ("call_debit_spread", "bull_call_spread"):
        # Buy lower call, sell higher call — bullish
        if long_strike is not None and short_strike is not None:
            width = abs(short_strike - long_strike)
            premium = abs(entry_price)
            return {
                "max_loss": round(premium * multiplier * quantity, 2),
                "max_profit": round((width - premium) * multiplier * quantity, 2),
                "breakeven": [round(long_strike + premium, 2)],
                "direction": "LONG",
            }

    if s in ("iron_condor",):
        # Detect debit vs credit from leg actions.
        # Credit IC (standard): SELL inner strikes, BUY outer → collect premium
        #   max_loss = wider_wing - premium,  max_profit = premium
        # Debit IC (long): BUY inner strikes, SELL outer → pay premium
        #   max_loss = premium,  max_profit = wider_wing - premium
        if legs and len(legs) >= 4:
            put_legs = [l for l in legs if l.get("option_type", "").upper() == "PUT"]
            call_legs = [l for l in legs if l.get("option_type", "").upper() == "CALL"]
            put_width = abs(put_legs[0]["strike"] - put_legs[1]["strike"]) if len(put_legs) >= 2 else 0
            call_width = abs(call_legs[0]["strike"] - call_legs[1]["strike"]) if len(call_legs) >= 2 else 0
            wider_wing = max(put_width, call_width)
            premium = abs(entry_price)
            is_debit = _is_debit_iron_condor(legs)
            if is_debit:
                # Debit IC: paid premium, profit on big moves
                return {
                    "max_loss": round(premium * multiplier * quantity, 2),
                    "max_profit": round((wider_wing - premium) * multiplier * quantity, 2),
                    "breakeven": [],
                    "direction": "MIXED",
                }
            else:
                # Credit IC: received premium, profit if price stays in range
                return {
                    "max_loss": round((wider_wing - premium) * multiplier * quantity, 2),
                    "max_profit": round(premium * multiplier * quantity, 2),
                    "breakeven": [],
                    "direction": "MIXED",
                }
        # Fallback if legs not provided but strikes are
        if long_strike is not None and short_strike is not None:
            width = abs(short_strike - long_strike)
            premium = abs(entry_price)
            return {
                "max_loss": round((width - premium) * multiplier * quantity, 2),
                "max_profit": round(premium * multiplier * quantity, 2),
                "breakeven": [],
                "direction": "MIXED",
            }

    if s in ("covered_call",):
        premium = abs(entry_price)
        return {
            "max_loss": None,  # stock can go to 0 minus premium received
            "max_profit": round(premium * multiplier * quantity, 2) if short_strike is None else round(((short_strike - entry_price) + premium) * quantity, 2),
            "breakeven": [],
            "direction": "LONG",
        }

    # --- Fallback for unknown structures ---
    return {
        "max_loss": None,
        "max_profit": None,
        "breakeven": [],
        "direction": "UNKNOWN",
    }


def infer_direction(structure: str) -> str:
    """Infer trade direction from structure name."""
    s = structure.lower().replace("-", "_").replace(" ", "_") if structure else ""
    bullish = ("long_call", "bull_call", "call_debit", "put_credit", "bull_put",
               "cash_secured_put", "covered_call", "stock_long", "long_stock", "stock")
    bearish = ("long_put", "bear_put", "put_debit", "call_credit", "bear_call",
               "short_call", "naked_call", "stock_short", "short_stock", "short_put", "naked_put")
    mixed = ("iron_condor", "iron_butterfly", "straddle", "strangle")
    for b in bullish:
        if b in s:
            return "LONG"
    for b in bearish:
        if b in s:
            return "SHORT"
    for m in mixed:
        if m in s:
            return "MIXED"
    return "UNKNOWN"
