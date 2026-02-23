"""
Robinhood CSV Trade History Parser.

Parses RH account statement CSVs into structured trade records and cash flows.
Pure parsing logic — no database access.
"""

import csv
import hashlib
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

OPTION_CODES = {"BTO", "STC", "STO", "BTC"}
STOCK_CODES = {"Buy", "Sell"}
EXPIRATION_CODES = {"OEXP"}
CASH_FLOW_CODES = {"ACH"}
SKIP_CODES = {"SLIP", "GOLD", "MTM", "INT", "FUTSWP"}

OPTION_DESC_RE = re.compile(
    r"^(\w+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(Call|Put)\s+\$(\d+\.?\d*)$"
)


def parse_amount(raw: str) -> Decimal:
    """Parse RH amount: '($160.04)' -> Decimal('-160.04'), '$479.95' -> Decimal('479.95')"""
    raw = raw.strip()
    if not raw:
        return Decimal("0")
    if raw.startswith("(") and raw.endswith(")"):
        return -Decimal(raw[1:-1].replace("$", "").replace(",", ""))
    return Decimal(raw.replace("$", "").replace(",", ""))


def parse_price(raw: str) -> Optional[Decimal]:
    """Parse price field, stripping $ prefix. Returns None if empty."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return Decimal(raw.replace("$", "").replace(",", ""))
    except InvalidOperation:
        return None


def parse_date(raw: str) -> Optional[date]:
    """Parse date field in MM/DD/YYYY format."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%m/%d/%Y").date()
    except ValueError:
        return None


def parse_option_description(desc: str) -> Optional[dict]:
    """Parse 'AAPL 03/21/2026 Put $220.00' -> {ticker, expiry, option_type, strike}"""
    cleaned = desc.strip()
    # OEXP rows have prefix: "Option Expiration for TICKER ..."
    if cleaned.startswith("Option Expiration for "):
        cleaned = cleaned[len("Option Expiration for "):]
    m = OPTION_DESC_RE.match(cleaned)
    if not m:
        return None
    return {
        "ticker": m.group(1),
        "expiry": datetime.strptime(m.group(2), "%m/%d/%Y").date(),
        "option_type": m.group(3),
        "strike": Decimal(m.group(4)),
    }


def parse_oexp_quantity(raw: str) -> tuple[int, str]:
    """Parse OEXP quantity: '2S' -> (2, 'short'), '2L' or '2' -> (2, 'long')"""
    raw = raw.strip()
    if not raw:
        return 0, "long"
    if raw.endswith("S"):
        return int(raw[:-1]), "short"
    elif raw.endswith("L"):
        return int(raw[:-1]), "long"
    return int(raw), "long"


def parse_rh_csv(filepath: str) -> dict:
    """
    Parse entire RH CSV file.

    Returns:
        {
            'trades': list of trade dicts,
            'cash_flows': list of cash flow dicts,
            'expirations': list of expiration dicts,
            'skipped': int count of skipped rows,
        }
    """
    trades = []
    cash_flows = []
    expirations = []
    skipped = 0

    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            activity_date_raw = (row.get("Activity Date") or "").strip()
            if not activity_date_raw:
                continue

            activity_date = parse_date(activity_date_raw)
            if not activity_date:
                skipped += 1
                continue

            settle_date = parse_date((row.get("Settle Date") or "").strip())
            instrument = (row.get("Instrument") or "").strip()
            description = (row.get("Description") or "").strip()
            trans_code = (row.get("Trans Code") or "").strip()
            quantity_raw = (row.get("Quantity") or "").strip()
            price_raw = (row.get("Price") or "").strip()
            amount_raw = (row.get("Amount") or "").strip()

            amount = parse_amount(amount_raw)

            if trans_code in SKIP_CODES:
                skipped += 1
                continue

            if trans_code in CASH_FLOW_CODES:
                cash_flows.append({
                    "flow_type": trans_code,
                    "amount": amount,
                    "description": description,
                    "activity_date": activity_date,
                })
                continue

            if trans_code in OPTION_CODES:
                opt = parse_option_description(description)
                ticker = opt["ticker"] if opt else instrument
                price = parse_price(price_raw)
                quantity = int(Decimal(quantity_raw)) if quantity_raw else None

                trades.append({
                    "activity_date": activity_date,
                    "settle_date": settle_date,
                    "ticker": ticker,
                    "description": description,
                    "trans_code": trans_code,
                    "quantity": quantity,
                    "price": price,
                    "amount": amount,
                    "is_option": True,
                    "option_type": opt["option_type"] if opt else None,
                    "strike": opt["strike"] if opt else None,
                    "expiry": opt["expiry"] if opt else None,
                    "trade_group_id": None,
                })
                continue

            if trans_code in STOCK_CODES:
                price = parse_price(price_raw)
                quantity = Decimal(quantity_raw) if quantity_raw else None

                trades.append({
                    "activity_date": activity_date,
                    "settle_date": settle_date,
                    "ticker": instrument,
                    "description": description,
                    "trans_code": trans_code,
                    "quantity": quantity,
                    "price": price,
                    "amount": amount,
                    "is_option": False,
                    "option_type": None,
                    "strike": None,
                    "expiry": None,
                    "trade_group_id": None,
                })
                continue

            if trans_code in EXPIRATION_CODES:
                opt = parse_option_description(description)
                qty, side = parse_oexp_quantity(quantity_raw)

                expirations.append({
                    "activity_date": activity_date,
                    "settle_date": settle_date,
                    "ticker": opt["ticker"] if opt else instrument,
                    "description": description,
                    "trans_code": trans_code,
                    "quantity": qty,
                    "side": side,
                    "price": None,
                    "amount": amount,
                    "is_option": True,
                    "option_type": opt["option_type"] if opt else None,
                    "strike": opt["strike"] if opt else None,
                    "expiry": opt["expiry"] if opt else None,
                    "trade_group_id": None,
                })
                continue

            # Unknown trans code — skip
            skipped += 1

    return {
        "trades": trades,
        "cash_flows": cash_flows,
        "expirations": expirations,
        "skipped": skipped,
    }


def group_spread_legs(trades: list) -> list:
    """
    Group option trades into spreads by matching legs.

    Matching criteria: same activity_date + ticker + expiry,
    one buy leg (BTO/BTC) and one sell leg (STO/STC), same quantity.
    Assigns shared trade_group_id to paired legs.
    """
    from collections import defaultdict

    # Only group option trades
    option_trades = [t for t in trades if t["is_option"] and t.get("expiry")]
    stock_trades = [t for t in trades if not t["is_option"]]

    # Group by (date, ticker, expiry)
    groups = defaultdict(list)
    for t in option_trades:
        key = (t["activity_date"], t["ticker"], t["expiry"])
        groups[key].append(t)

    for key, legs in groups.items():
        if len(legs) < 2:
            continue

        buy_legs = [l for l in legs if l["trans_code"] in ("BTO", "BTC")]
        sell_legs = [l for l in legs if l["trans_code"] in ("STO", "STC")]

        # Try to match buy+sell pairs with same quantity
        matched_buys = set()
        matched_sells = set()

        for bi, buy in enumerate(buy_legs):
            for si, sell in enumerate(sell_legs):
                if si in matched_sells:
                    continue
                if buy.get("quantity") == sell.get("quantity"):
                    # Generate group ID
                    hash_input = (
                        f"{key[0]}_{key[1]}_{key[2]}_"
                        f"{buy.get('strike')}_{sell.get('strike')}"
                    )
                    group_id = "grp_" + hashlib.md5(
                        hash_input.encode()
                    ).hexdigest()[:12]

                    buy["trade_group_id"] = group_id
                    sell["trade_group_id"] = group_id
                    matched_buys.add(bi)
                    matched_sells.add(si)
                    break

    return option_trades + stock_trades
