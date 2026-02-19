"""
Robinhood trade import parser.

Supports:
- Official Robinhood account statement CSV
- robin_stocks export CSV
"""

from __future__ import annotations

import csv
import io
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple


IGNORE_TRANS_CODES = {
    "CDIV",  # cash dividend
    "DIV",
    "INT",
    "SLIP",
    "SPL",
    "CONV",
    "ACH",
    "FEE",
    "XFER",
    "TRANSFER",
}

ASSIGNMENT_CODES = {"OASGN", "ASSIGN", "EXERCISE"}


@dataclass
class ParsedLeg:
    ticker: str
    timestamp: datetime
    action: str
    direction: str
    quantity: float
    price: float
    strike: Optional[float] = None
    expiry: Optional[str] = None
    option_type: Optional[str] = None
    leg_type: Optional[str] = None
    trans_code: Optional[str] = None


def detect_csv_format(header_row: Sequence[str]) -> str:
    headers = {str(h).strip() for h in header_row}
    if {"Activity Date", "Trans Code"}.issubset(headers):
        return "robinhood_statement"
    if {"chain_symbol", "opening_strategy"}.issubset(headers):
        return "robin_stocks"
    return "unknown"


def parse_option_instrument(instrument_str: str) -> Optional[Dict[str, Any]]:
    """
    Parse option descriptions in two formats:
      Format A: "SPY 03/07/2026 680.00 Put"     (strike before type)
      Format B: "NFLX 5/15/2026 Call $82.00"     (type before strike - Robinhood)
    """
    text = (instrument_str or "").strip()
    parts = text.split()
    if len(parts) < 4:
        return None

    # Both formats: parts[0] = ticker, parts[1] = date
    try:
        ticker = parts[0].upper()
        expiry = datetime.strptime(parts[1], "%m/%d/%Y").strftime("%Y-%m-%d")
    except Exception:
        return None

    if parts[2].lower() in {"put", "call"}:
        # Format B: TICKER DATE TYPE STRIKE (Robinhood)
        option_type = parts[2].lower()
        try:
            strike = float(parts[3].replace("$", ""))
        except Exception:
            return None
    elif parts[-1].lower() in {"put", "call"}:
        # Format A: TICKER DATE STRIKE TYPE (original)
        option_type = parts[-1].lower()
        try:
            strike = float(parts[2].replace("$", ""))
        except Exception:
            return None
    else:
        return None

    return {
        "ticker": ticker,
        "expiry": expiry,
        "strike": strike,
        "option_type": option_type,
    }


def _as_float(value: Any, default: float = 0.0) -> float:
    """Parse a numeric value, handling $, commas, and accounting-style (negative) parens."""
    try:
        if value is None:
            return default
        text = str(value).strip()
        if not text:
            return default
        # Strip dollar signs and commas
        text = text.replace("$", "").replace(",", "")
        # Handle accounting-style negatives: ($160.04) -> -160.04
        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]
        return float(text)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except Exception:
        return default


def _parse_statement_timestamp(row: Dict[str, Any]) -> Optional[datetime]:
    date_text = str(row.get("Activity Date") or "").strip()
    if not date_text:
        return None
    try:
        return datetime.strptime(date_text, "%m/%d/%Y")
    except Exception:
        return None


def _parse_robinstocks_timestamp(row: Dict[str, Any]) -> Optional[datetime]:
    raw = str(row.get("order_created_at") or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _infer_direction_for_structure(structure: str, option_type: Optional[str], side: str) -> str:
    s = (structure or "").lower()
    if "put_spread" in s:
        return "BEARISH" if "long" in s else "BULLISH"
    if "call_spread" in s:
        return "BULLISH" if "long" in s else "BEARISH"
    if option_type == "put":
        return "BEARISH" if side == "buy" else "BULLISH"
    if option_type == "call":
        return "BULLISH" if side == "buy" else "BEARISH"
    return "BULLISH"


def _build_trade_from_spread_legs(
    *,
    ticker: str,
    quantity: float,
    option_type: str,
    open_buy: ParsedLeg,
    open_sell: ParsedLeg,
    close_sell: Optional[ParsedLeg],
    close_buy: Optional[ParsedLeg],
) -> Dict[str, Any]:
    long_strike = open_buy.strike
    short_strike = open_sell.strike
    direction = "UNKNOWN"
    structure = "complex"

    if option_type == "put" and long_strike is not None and short_strike is not None:
        if long_strike > short_strike:
            direction = "BEARISH"
            structure = "put_spread"
        else:
            direction = "BULLISH"
            structure = "put_spread"
    elif option_type == "call" and long_strike is not None and short_strike is not None:
        if long_strike < short_strike:
            direction = "BULLISH"
            structure = "call_spread"
        else:
            direction = "BEARISH"
            structure = "call_spread"

    entry_net = max(0.0, open_buy.price - open_sell.price)
    exit_net: Optional[float] = None
    status = "open"
    exit_date = None
    pnl_dollars: Optional[float] = None
    pnl_percent: Optional[float] = None

    if close_sell and close_buy:
        exit_net = close_sell.price - close_buy.price
        status = "closed"
        exit_date = close_sell.timestamp.date().isoformat()
        pnl_dollars = (exit_net - entry_net) * quantity * 100.0
        if entry_net > 0:
            pnl_percent = (exit_net - entry_net) / entry_net * 100.0

    return {
        "ticker": ticker,
        "direction": direction,
        "structure": structure,
        "entry_date": open_buy.timestamp.date().isoformat(),
        "exit_date": exit_date,
        "entry_price": round(entry_net, 4),
        "exit_price": round(exit_net, 4) if exit_net is not None else None,
        "strike": long_strike,
        "short_strike": short_strike,
        "long_strike": long_strike,
        "expiry": open_buy.expiry,
        "quantity": int(quantity),
        "status": status,
        "pnl_dollars": round(pnl_dollars, 2) if pnl_dollars is not None else None,
        "pnl_percent": round(pnl_percent, 2) if pnl_percent is not None else None,
        "legs": [
            open_buy.__dict__,
            open_sell.__dict__,
            *( [close_sell.__dict__] if close_sell else [] ),
            *( [close_buy.__dict__] if close_buy else [] ),
        ],
    }


def _statement_rows_to_legs(rows: List[Dict[str, Any]]) -> Tuple[List[ParsedLeg], List[str], int]:
    legs: List[ParsedLeg] = []
    warnings: List[str] = []
    filtered_out = 0
    skipped_by_reason: Dict[str, int] = defaultdict(int)

    for row in rows:
        trans_code = str(row.get("Trans Code") or "").strip().upper()
        description = str(row.get("Description") or "").strip()
        instrument = str(row.get("Instrument") or "").strip()
        timestamp = _parse_statement_timestamp(row)
        if not timestamp:
            skipped_by_reason["invalid_date"] += 1
            filtered_out += 1
            continue

        if trans_code in IGNORE_TRANS_CODES or any(token in description.upper() for token in ("DIVIDEND", "INTEREST", "TRANSFER")):
            skipped_by_reason["non_trade"] += 1
            filtered_out += 1
            continue

        quantity = abs(_as_float(row.get("Quantity"), 0.0))
        price = _as_float(row.get("Price"), 0.0)
        if quantity <= 0 or price <= 0:
            skipped_by_reason["invalid_qty_price"] += 1
            filtered_out += 1
            continue

        # Try Instrument field first, then fall back to Description for option details.
        # Robinhood puts just the ticker in Instrument but full option info in Description.
        opt = parse_option_instrument(instrument)
        if not opt:
            opt = parse_option_instrument(description)
        if opt:
            if trans_code in {"BTO"}:
                action = "buy_to_open"
                side = "buy"
            elif trans_code in {"STO"}:
                action = "sell_to_open"
                side = "sell"
            elif trans_code in {"STC"}:
                action = "sell_to_close"
                side = "sell"
            elif trans_code in {"BTC"}:
                action = "buy_to_close"
                side = "buy"
            elif trans_code in ASSIGNMENT_CODES:
                action = "assignment"
                side = "sell"
            else:
                skipped_by_reason["unsupported_option_code"] += 1
                filtered_out += 1
                continue

            direction = "BULLISH"
            if opt["option_type"] == "put":
                direction = "BEARISH" if side == "buy" else "BULLISH"
            elif opt["option_type"] == "call":
                direction = "BULLISH" if side == "buy" else "BEARISH"

            legs.append(
                ParsedLeg(
                    ticker=opt["ticker"],
                    timestamp=timestamp,
                    action=action,
                    direction=direction,
                    quantity=quantity,
                    price=price,
                    strike=opt["strike"],
                    expiry=opt["expiry"],
                    option_type=opt["option_type"],
                    leg_type="option",
                    trans_code=trans_code,
                )
            )
            continue

        # Stock legs
        if trans_code in {"BUY"}:
            action = "buy"
            direction = "BULLISH"
        elif trans_code in {"SELL"}:
            action = "sell"
            direction = "BEARISH"
        else:
            skipped_by_reason["unsupported_stock_code"] += 1
            filtered_out += 1
            continue

        legs.append(
            ParsedLeg(
                ticker=instrument.upper(),
                timestamp=timestamp,
                action=action,
                direction=direction,
                quantity=quantity,
                price=price,
                leg_type="shares",
                trans_code=trans_code,
            )
        )

    if skipped_by_reason.get("non_trade"):
        warnings.append(f"Skipped {skipped_by_reason['non_trade']} non-trade transactions")
    if skipped_by_reason.get("unsupported_option_code"):
        warnings.append(f"Skipped {skipped_by_reason['unsupported_option_code']} unsupported option rows")
    if skipped_by_reason.get("unsupported_stock_code"):
        warnings.append(f"Skipped {skipped_by_reason['unsupported_stock_code']} unsupported stock rows")
    if skipped_by_reason.get("invalid_qty_price"):
        warnings.append(f"Skipped {skipped_by_reason['invalid_qty_price']} rows with invalid quantity/price")
    return legs, warnings, filtered_out


def _robinstocks_rows_to_legs(rows: List[Dict[str, Any]]) -> Tuple[List[ParsedLeg], List[str], int]:
    legs: List[ParsedLeg] = []
    warnings: List[str] = []
    filtered_out = 0
    for row in rows:
        ticker = str(row.get("chain_symbol") or "").strip().upper()
        expiry = str(row.get("expiration_date") or "").strip() or None
        option_type = str(row.get("option_type") or "").strip().lower() or None
        side = str(row.get("side") or "").strip().lower()
        timestamp = _parse_robinstocks_timestamp(row)
        qty = _as_float(row.get("processed_quantity") or row.get("order_quantity"), 0.0)
        price = _as_float(row.get("price"), 0.0)
        strategy = str(row.get("opening_strategy") or row.get("closing_strategy") or "").strip().lower()

        if not ticker or not timestamp or qty <= 0 or price <= 0:
            filtered_out += 1
            continue

        action = "buy_to_open" if side == "buy" else "sell_to_open"
        if row.get("closing_strategy"):
            action = "buy_to_close" if side == "buy" else "sell_to_close"

        direction = _infer_direction_for_structure(strategy, option_type, side)
        legs.append(
            ParsedLeg(
                ticker=ticker,
                timestamp=timestamp,
                action=action,
                direction=direction,
                quantity=qty,
                price=price,
                strike=_as_float(row.get("strike_price"), 0.0) or None,
                expiry=expiry,
                option_type=option_type,
                leg_type=strategy or "option",
                trans_code=str(row.get("direction") or ""),
            )
        )
    return legs, warnings, filtered_out


def _group_legs_into_trades(legs: List[ParsedLeg]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    warnings: List[str] = []
    closed_trades: List[Dict[str, Any]] = []
    open_trades: List[Dict[str, Any]] = []

    option_legs = [leg for leg in legs if leg.leg_type and leg.leg_type != "shares"]
    stock_legs = [leg for leg in legs if leg.leg_type == "shares"]

    # 1) Try to detect vertical spread pairs by day/ticker/expiry/type/qty.
    open_groups: Dict[Tuple[str, str, str, float, str], List[ParsedLeg]] = defaultdict(list)
    close_groups: Dict[Tuple[str, str, float, str], List[ParsedLeg]] = defaultdict(list)
    singles: List[ParsedLeg] = []

    for leg in option_legs:
        if not leg.expiry or not leg.option_type:
            singles.append(leg)
            continue
        key = (leg.timestamp.date().isoformat(), leg.ticker, leg.expiry, float(leg.quantity), leg.option_type)
        close_key = (leg.ticker, leg.expiry, float(leg.quantity), leg.option_type)
        if leg.action in {"buy_to_open", "sell_to_open"}:
            open_groups[key].append(leg)
        elif leg.action in {"buy_to_close", "sell_to_close"}:
            close_groups[close_key].append(leg)
        else:
            singles.append(leg)

    used_close_keys: set[Tuple[str, str, float, str]] = set()
    for close_key in close_groups:
        close_groups[close_key].sort(key=lambda x: x.timestamp)
    for key, open_legs in open_groups.items():
        buy_open = [x for x in open_legs if x.action == "buy_to_open"]
        sell_open = [x for x in open_legs if x.action == "sell_to_open"]
        if not buy_open or not sell_open:
            singles.extend(open_legs)
            continue
        buy_open.sort(key=lambda x: x.timestamp)
        sell_open.sort(key=lambda x: x.timestamp)
        pair_count = min(len(buy_open), len(sell_open))
        for i in range(pair_count):
            o_buy = buy_open[i]
            o_sell = sell_open[i]
            close_key = (o_buy.ticker, o_buy.expiry or "", float(min(o_buy.quantity, o_sell.quantity)), o_buy.option_type or "")
            close_legs = close_groups.get(close_key, [])
            c_sell_idx = next(
                (
                    idx
                    for idx, x in enumerate(close_legs)
                    if x.action == "sell_to_close" and x.timestamp >= max(o_buy.timestamp, o_sell.timestamp)
                ),
                None,
            )
            c_buy_idx = next(
                (
                    idx
                    for idx, x in enumerate(close_legs)
                    if x.action == "buy_to_close" and x.timestamp >= max(o_buy.timestamp, o_sell.timestamp)
                ),
                None,
            )
            c_sell = close_legs[c_sell_idx] if c_sell_idx is not None else None
            c_buy = close_legs[c_buy_idx] if c_buy_idx is not None else None
            if c_sell and c_buy:
                used_close_keys.add(close_key)
                # remove in descending index order to keep indexes valid
                remove_indexes = sorted({c_sell_idx, c_buy_idx}, reverse=True)
                for idx in remove_indexes:
                    if idx is not None and 0 <= idx < len(close_legs):
                        close_legs.pop(idx)
            trade = _build_trade_from_spread_legs(
                ticker=o_buy.ticker,
                quantity=min(o_buy.quantity, o_sell.quantity),
                option_type=o_buy.option_type or "put",
                open_buy=o_buy,
                open_sell=o_sell,
                close_sell=c_sell,
                close_buy=c_buy,
            )
            if trade["status"] == "closed":
                closed_trades.append(trade)
            else:
                open_trades.append(trade)

    for key, remaining_close_legs in close_groups.items():
        if key not in used_close_keys or remaining_close_legs:
            singles.extend(remaining_close_legs)

    # 2) Single-leg options (FIFO by same contract).
    single_open: Dict[Tuple[str, Optional[str], Optional[float], Optional[str]], List[ParsedLeg]] = defaultdict(list)
    for leg in sorted(singles, key=lambda x: x.timestamp):
        key = (leg.ticker, leg.expiry, leg.strike, leg.option_type)
        if leg.action in {"buy_to_open", "sell_to_open"}:
            single_open[key].append(leg)
            continue
        if leg.action in {"buy_to_close", "sell_to_close"} and single_open[key]:
            opened = single_open[key].pop(0)
            qty = min(opened.quantity, leg.quantity)
            is_long = opened.action == "buy_to_open"
            entry = opened.price
            exit_px = leg.price
            pnl = (exit_px - entry) * qty * 100.0 if is_long else (entry - exit_px) * qty * 100.0
            direction = "BEARISH" if opened.option_type == "put" and is_long else "BULLISH"
            if opened.option_type == "call":
                direction = "BULLISH" if is_long else "BEARISH"
            closed_trades.append(
                {
                    "ticker": opened.ticker,
                    "direction": direction,
                    "structure": opened.option_type or "option",
                    "entry_date": opened.timestamp.date().isoformat(),
                    "exit_date": leg.timestamp.date().isoformat(),
                    "entry_price": round(entry, 4),
                    "exit_price": round(exit_px, 4),
                    "strike": opened.strike,
                    "short_strike": None,
                    "long_strike": opened.strike if is_long else None,
                    "expiry": opened.expiry,
                    "quantity": int(qty),
                    "status": "closed",
                    "pnl_dollars": round(pnl, 2),
                    "pnl_percent": round(((exit_px - entry) / entry) * 100.0, 2) if entry else None,
                    "legs": [opened.__dict__, leg.__dict__],
                }
            )
            continue

    orphan_option_legs = 0
    for key, opens in single_open.items():
        for opened in opens:
            orphan_option_legs += 1
            direction = "BEARISH" if opened.option_type == "put" and opened.action == "buy_to_open" else "BULLISH"
            if opened.option_type == "call":
                direction = "BULLISH" if opened.action == "buy_to_open" else "BEARISH"
            open_trades.append(
                {
                    "ticker": opened.ticker,
                    "direction": direction,
                    "structure": opened.option_type or "option",
                    "entry_date": opened.timestamp.date().isoformat(),
                    "exit_date": None,
                    "entry_price": round(opened.price, 4),
                    "exit_price": None,
                    "strike": opened.strike,
                    "short_strike": None,
                    "long_strike": opened.strike if opened.action == "buy_to_open" else None,
                    "expiry": opened.expiry,
                    "quantity": int(opened.quantity),
                    "status": "open",
                    "pnl_dollars": None,
                    "pnl_percent": None,
                    "legs": [opened.__dict__],
                }
            )
    if orphan_option_legs:
        warnings.append(f"{orphan_option_legs} orphaned option legs imported as open positions")

    # 3) Stocks (simple FIFO long/short aware).
    stock_lots: Dict[str, List[ParsedLeg]] = defaultdict(list)
    for leg in sorted(stock_legs, key=lambda x: x.timestamp):
        ticker = leg.ticker
        open_lots = stock_lots[ticker]
        if leg.action == "buy":
            # If short lot exists, this buy closes short first.
            short_lot_idx = next((i for i, l in enumerate(open_lots) if l.direction == "BEARISH"), None)
            if short_lot_idx is not None:
                opened = open_lots.pop(short_lot_idx)
                qty = min(opened.quantity, leg.quantity)
                pnl = (opened.price - leg.price) * qty
                closed_trades.append(
                    {
                        "ticker": ticker,
                        "direction": "BEARISH",
                        "structure": "shares",
                        "entry_date": opened.timestamp.date().isoformat(),
                        "exit_date": leg.timestamp.date().isoformat(),
                        "entry_price": round(opened.price, 4),
                        "exit_price": round(leg.price, 4),
                        "strike": None,
                        "short_strike": None,
                        "long_strike": None,
                        "expiry": None,
                        "quantity": int(qty),
                        "status": "closed",
                        "pnl_dollars": round(pnl, 2),
                        "pnl_percent": round(((opened.price - leg.price) / opened.price) * 100.0, 2) if opened.price else None,
                        "legs": [opened.__dict__, leg.__dict__],
                    }
                )
            else:
                open_lots.append(leg)
        elif leg.action == "sell":
            long_lot_idx = next((i for i, l in enumerate(open_lots) if l.direction == "BULLISH"), None)
            if long_lot_idx is not None:
                opened = open_lots.pop(long_lot_idx)
                qty = min(opened.quantity, leg.quantity)
                pnl = (leg.price - opened.price) * qty
                closed_trades.append(
                    {
                        "ticker": ticker,
                        "direction": "BULLISH",
                        "structure": "shares",
                        "entry_date": opened.timestamp.date().isoformat(),
                        "exit_date": leg.timestamp.date().isoformat(),
                        "entry_price": round(opened.price, 4),
                        "exit_price": round(leg.price, 4),
                        "strike": None,
                        "short_strike": None,
                        "long_strike": None,
                        "expiry": None,
                        "quantity": int(qty),
                        "status": "closed",
                        "pnl_dollars": round(pnl, 2),
                        "pnl_percent": round(((leg.price - opened.price) / opened.price) * 100.0, 2) if opened.price else None,
                        "legs": [opened.__dict__, leg.__dict__],
                    }
                )
            else:
                # Opening short stock position.
                leg.direction = "BEARISH"
                open_lots.append(leg)

    for ticker, lots in stock_lots.items():
        for lot in lots:
            open_trades.append(
                {
                    "ticker": ticker,
                    "direction": lot.direction,
                    "structure": "shares",
                    "entry_date": lot.timestamp.date().isoformat(),
                    "exit_date": None,
                    "entry_price": round(lot.price, 4),
                    "exit_price": None,
                    "strike": None,
                    "short_strike": None,
                    "long_strike": None,
                    "expiry": None,
                    "quantity": int(lot.quantity),
                    "status": "open",
                    "pnl_dollars": None,
                    "pnl_percent": None,
                    "legs": [lot.__dict__],
                }
            )

    return closed_trades, open_trades, warnings


def parse_robinhood_csv_text(csv_text: str) -> Dict[str, Any]:
    reader = csv.DictReader(io.StringIO(csv_text))
    headers = reader.fieldnames or []
    fmt = detect_csv_format(headers)
    rows = list(reader)

    if fmt == "unknown":
        return {
            "format_detected": "unknown",
            "raw_transactions": len(rows),
            "filtered_transactions": 0,
            "grouped_trades": 0,
            "trades": [],
            "open_positions": [],
            "warnings": ["Unknown CSV format. Expected Robinhood statement or robin_stocks export."],
        }

    if fmt == "robinhood_statement":
        legs, parse_warnings, filtered_out = _statement_rows_to_legs(rows)
    else:
        legs, parse_warnings, filtered_out = _robinstocks_rows_to_legs(rows)

    closed_trades, open_trades, grouping_warnings = _group_legs_into_trades(legs)
    warnings = [*parse_warnings, *grouping_warnings]

    return {
        "format_detected": fmt,
        "raw_transactions": len(rows),
        "filtered_transactions": len(legs),
        "grouped_trades": len(closed_trades) + len(open_trades),
        "trades": closed_trades,
        "open_positions": open_trades,
        "warnings": warnings,
    }


def parse_robinhood_csv_bytes(raw: bytes) -> Dict[str, Any]:
    text = raw.decode("utf-8-sig", errors="replace")
    return parse_robinhood_csv_text(text)
