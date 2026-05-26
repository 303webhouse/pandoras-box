"""
RH CSV Sync -> unified_positions
================================

Reconcile the `unified_positions` table against Robinhood activity CSV exports.

Modes
-----
- `--csv-only`  Parse + reconstruct the open book from CSV only. No DB access.
                Use this to validate CSV inputs and inspect the derived book
                before running against the database.
- (default)     Dry-run: read DB state, compute diff, print report. No writes.
- `--apply`     Execute INSERT/UPDATE/CLOSE inside a single DB transaction,
                with one row per operation in `position_sync_audit`.

The CSV walker is chronological. Per the brief:
  - Spreads are matched by (date, ticker, expiry, option_type) leg pairs.
  - HYG-style multi-leg structures (broken-wing put ratio) are special-cased
    via MULTI_LEG_HINTS — all same-(date, expiry, option_type) opens for that
    ticker collapse into one structure event. The full leg set is preserved in
    the `legs` JSONB column; the 2-leg-aware price-updater reads `long_strike`
    / `short_strike` as before (per the schema limitation documented in
    PROJECT_RULES.md).
  - Closures (BTC/STC, OEXP) reduce qty against the open book.
  - Decimal arithmetic throughout; no floats.

Account scope: RH only (`account='ROBINHOOD'`). Fidelity Roth is a future brief.

Usage
-----
    python scripts/sync_rh_csv.py data/rh_csv/                  # dry-run + DB diff
    python scripts/sync_rh_csv.py data/rh_csv/ --csv-only       # offline sanity check
    python scripts/sync_rh_csv.py data/rh_csv/ --apply          # execute writes

The CSV argument can be a single file or a directory. All CSVs are
chronologically merged (de-duplicated on activity-date/ticker/code/qty/price).
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]

getcontext().prec = 12

logger = logging.getLogger("sync_rh_csv")

# ── Trans-code classification ─────────────────────────────────────────

OPEN_OPT_CODES = {"BTO", "STO"}
CLOSE_OPT_CODES = {"BTC", "STC"}
OEXP_CODE = "OEXP"

STOCK_OPEN_CODES = {"Buy"}
STOCK_CLOSE_CODES = {"Sell"}

# Cash-flow, fee, dividend, etc. — ignored by the position walker.
SKIP_CODES = {
    "DCF", "FUTSWP", "MTM", "SLIP", "ACH", "MINT", "SPLD", "MISC", "SS",
}

# Tickers whose multi-leg opens collapse into one structure event (rather than
# being decomposed into 2-leg verticals). Value is a descriptive structure label
# (stored in notes), and the canonical mapped `structure` for unified_positions.
MULTI_LEG_HINTS: Dict[str, Tuple[str, str]] = {
    # ticker -> (descriptive_label, mapped_structure)
    # HYG: -1×low put + 1×mid put + 1×high put per unit. We compress to
    # put_debit_spread for the schema's 2-leg aware columns and keep the
    # middle leg in `legs` JSONB.
    "HYG": ("broken_wing_put_ratio_1_1_1", "put_debit_spread"),
}

# ── Regex ─────────────────────────────────────────────────────────────

OPTION_DESC_RE = re.compile(
    r"^\s*(\S+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(Call|Put)\s+\$([\d.]+)\s*$",
    re.IGNORECASE,
)

EXPIRY_DESC_RE = re.compile(
    r"^\s*Option Expiration for\s+(\S+)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(Call|Put)\s+\$([\d.]+)\s*$",
    re.IGNORECASE,
)


# ── Dataclasses ───────────────────────────────────────────────────────

@dataclass
class Txn:
    """One parsed transaction row."""

    activity_date: date
    ticker: str
    trans_code: str
    quantity: int
    short_side: bool                # quantity ended with "S" (long leg of an OEXP per RH convention)
    price: Optional[Decimal]
    amount: Decimal
    description: str
    option_type: Optional[str] = None   # 'call' | 'put'
    expiry: Optional[date] = None
    strike: Optional[Decimal] = None
    csv_path: str = ""
    csv_row: int = 0

    @property
    def is_option(self) -> bool:
        return self.option_type is not None

    def dedup_key(self) -> Tuple:
        return (
            self.activity_date,
            self.ticker,
            self.trans_code,
            self.quantity,
            self.short_side,
            str(self.price) if self.price is not None else "",
            self.description,
        )


@dataclass(frozen=True)
class PositionKey:
    """Identifies a unique position in the book (and a row in unified_positions)."""

    ticker: str
    structure: str                  # put_debit_spread, bull_call_spread, long_put, long_call, ...
    expiry: Optional[date]
    long_strike: Optional[Decimal]
    short_strike: Optional[Decimal]

    def display(self) -> str:
        # Use %m/%d/%y (zero-padded) for cross-platform compatibility — %-m / %-d
        # are POSIX-only and crash on Windows.
        exp = self.expiry.strftime("%m/%d/%y") if self.expiry else "n/a"
        if self.short_strike is None and self.long_strike is not None:
            opt = "Call" if "call" in self.structure else "Put"
            return f"{self.ticker} {exp} ${self.long_strike:g} {opt} long"
        if self.long_strike is not None and self.short_strike is not None:
            return f"{self.ticker} {exp} ${self.long_strike:g}/${self.short_strike:g} {self.structure}"
        return f"{self.ticker} {exp} {self.structure}"


@dataclass
class PositionState:
    """Reconstructed position state from CSV transactions."""

    key: PositionKey
    quantity: int = 0
    opens: List[Tuple[date, int, Decimal]] = field(default_factory=list)        # (date, qty_added, net_debit_per_unit)
    closes: List[Tuple[date, int, Decimal, str]] = field(default_factory=list)  # (date, qty_removed, net_credit_per_unit, reason)
    full_legs: List[Dict[str, Any]] = field(default_factory=list)
    notes: Optional[str] = None

    @property
    def last_open_date(self) -> Optional[date]:
        return self.opens[-1][0] if self.opens else None

    @property
    def first_open_date(self) -> Optional[date]:
        return self.opens[0][0] if self.opens else None

    @property
    def last_close_date(self) -> Optional[date]:
        return self.closes[-1][0] if self.closes else None

    @property
    def total_open_qty(self) -> int:
        return sum(q for _, q, _ in self.opens)

    def avg_entry_debit(self) -> Decimal:
        """Weighted average entry debit (positive = paid premium per unit)."""
        total_qty = self.total_open_qty
        if total_qty == 0:
            return Decimal(0)
        weighted = sum(Decimal(q) * d for _, q, d in self.opens)
        return weighted / Decimal(total_qty)


@dataclass
class Action:
    """One pending DB action computed by the diff stage."""

    op: str                          # INSERT, UPDATE, CLOSE, NO_OP_FLAG
    position_key: PositionKey
    csv_state: Optional[PositionState] = None
    db_row: Optional[Dict[str, Any]] = None
    notes: str = ""


# ── Parsing ───────────────────────────────────────────────────────────

def _parse_money(s: str) -> Decimal:
    if not s:
        return Decimal(0)
    s = s.strip()
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    s = s.replace("$", "").replace(",", "")
    if not s:
        return Decimal(0)
    val = Decimal(s)
    return -val if neg else val


def _parse_price(s: str) -> Optional[Decimal]:
    if not s:
        return None
    s = s.strip().replace("$", "").replace(",", "")
    if not s:
        return None
    return Decimal(s)


def _parse_qty(raw: str) -> Tuple[int, bool]:
    """Return (quantity, short_side). RH appends 'S' to OEXP qty on the long leg."""
    if not raw:
        return 0, False
    raw = raw.strip()
    short = raw.endswith("S")
    if short:
        raw = raw[:-1]
    if not raw:
        return 0, short
    try:
        return int(Decimal(raw)), short
    except Exception:
        return 0, short


def _parse_date(s: str) -> date:
    return datetime.strptime(s.strip(), "%m/%d/%Y").date()


def _parse_option_description(desc: str) -> Optional[Tuple[str, date, str, Decimal]]:
    """Parse 'TICKER M/D/YYYY Call|Put $STRIKE' from option transaction descriptions."""
    if not desc:
        return None
    desc = desc.strip()
    # Handle multi-line (stock CUSIP continuation) — keep only first line.
    desc = desc.splitlines()[0].strip()
    m = OPTION_DESC_RE.match(desc)
    if not m:
        # Try expiry description
        m = EXPIRY_DESC_RE.match(desc)
        if not m:
            return None
    ticker = m.group(1).upper()
    expiry = _parse_date(m.group(2))
    opt_type = m.group(3).lower()
    strike = Decimal(m.group(4))
    return ticker, expiry, opt_type, strike


def parse_csv_file(path: Path) -> List[Txn]:
    """Parse one RH activity CSV into Txn objects (one per row, post-filter)."""
    txns: List[Txn] = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        # RH CSVs sometimes have multi-line cells (CUSIP on second line of
        # Description for stock rows). csv.reader handles quoted newlines.
        reader = csv.reader(f)
        rows = list(reader)

    if not rows:
        return []

    header = [c.strip() for c in rows[0]]
    # Expected: Activity Date, Process Date, Settle Date, Instrument,
    #           Description, Trans Code, Quantity, Price, Amount
    expected = {"Activity Date", "Trans Code", "Quantity", "Price", "Amount", "Description", "Instrument"}
    missing = expected - set(header)
    if missing:
        raise ValueError(f"CSV {path} is missing expected columns: {missing}")

    col = {name: idx for idx, name in enumerate(header)}

    for row_idx, row in enumerate(rows[1:], start=2):
        if not row or all(not c.strip() for c in row):
            continue
        try:
            activity_date_raw = row[col["Activity Date"]].strip()
            if not activity_date_raw:
                continue
            trans_code = row[col["Trans Code"]].strip()
            if not trans_code or trans_code in SKIP_CODES:
                continue
            instrument = row[col["Instrument"]].strip()
            description = row[col["Description"]].strip()
            qty_raw = row[col["Quantity"]].strip()
            price_raw = row[col["Price"]].strip()
            amount_raw = row[col["Amount"]].strip()
        except IndexError:
            logger.warning("Skipping malformed row %d in %s", row_idx, path)
            continue

        # Footer rows are mostly empty; skip
        if trans_code == "":
            continue

        try:
            activity_date = _parse_date(activity_date_raw)
        except ValueError:
            continue

        quantity, short_side = _parse_qty(qty_raw)
        price = _parse_price(price_raw)
        amount = _parse_money(amount_raw)

        parsed_opt = _parse_option_description(description)
        option_type = expiry = strike = None
        ticker = instrument.upper()
        if parsed_opt:
            ticker_p, expiry, option_type, strike = parsed_opt
            # When instrument is blank but description has a ticker, prefer description.
            if not ticker and ticker_p:
                ticker = ticker_p

        if not ticker:
            # Cash-flow rows without ticker — skip
            continue

        txns.append(Txn(
            activity_date=activity_date,
            ticker=ticker,
            trans_code=trans_code,
            quantity=quantity,
            short_side=short_side,
            price=price,
            amount=amount,
            description=description,
            option_type=option_type,
            expiry=expiry,
            strike=strike,
            csv_path=str(path),
            csv_row=row_idx,
        ))

    return txns


def gather_csvs(input_path: Path) -> List[Path]:
    """Return list of CSV files from a file or directory path."""
    if input_path.is_file():
        return [input_path]
    if input_path.is_dir():
        return sorted(input_path.glob("*.csv"))
    raise FileNotFoundError(f"CSV input not found: {input_path}")


def parse_all(csv_paths: List[Path]) -> Tuple[List[Txn], str]:
    """Parse all CSVs and return chronologically-sorted txns + sha256 of contents.

    NOTE: We deliberately do NOT dedup by row content. Two identical-looking
    rows in an RH CSV (same date, ticker, code, qty, price) represent two
    separate trades — RH groups multi-contract orders into per-leg rows and
    repeats identical rows when a ticker is traded multiple times at the same
    price the same day. Dedup at content level eats legitimate trades.

    Cross-CSV overlap (the same actual trade appearing in two CSV exports)
    SHOULD be deduped — but that requires the input not to overlap. We warn
    if the input CSVs cover overlapping date ranges instead of auto-deduping.
    """
    sha = hashlib.sha256()
    all_txns: List[Txn] = []
    for path in csv_paths:
        sha.update(path.name.encode())
        sha.update(b"\n")
        with open(path, "rb") as f:
            sha.update(f.read())
        all_txns.extend(parse_csv_file(path))

    # Overlap check
    by_file: Dict[str, Tuple[date, date]] = {}
    for t in all_txns:
        cur = by_file.get(t.csv_path)
        if cur is None:
            by_file[t.csv_path] = (t.activity_date, t.activity_date)
        else:
            by_file[t.csv_path] = (min(cur[0], t.activity_date), max(cur[1], t.activity_date))
    ranges = sorted(by_file.items(), key=lambda kv: kv[1][0])
    for i in range(1, len(ranges)):
        prev_path, (prev_lo, prev_hi) = ranges[i - 1]
        cur_path, (cur_lo, cur_hi) = ranges[i]
        if cur_lo <= prev_hi:
            logger.warning(
                "CSV date ranges overlap: %s [%s, %s] and %s [%s, %s]. "
                "Duplicate trades may be double-counted. Trim the inputs.",
                Path(prev_path).name, prev_lo, prev_hi,
                Path(cur_path).name, cur_lo, cur_hi,
            )

    sorted_txns = sorted(all_txns, key=lambda t: (t.activity_date, t.ticker, t.csv_path, t.csv_row))
    return sorted_txns, sha.hexdigest()


# ── State reconstruction ──────────────────────────────────────────────

def _structure_from_legs(opt_type: str, long_strike: Decimal, short_strike: Decimal) -> str:
    """For a 2-leg vertical, return the canonical unified_positions `structure` label.

    Convention (matches existing DB rows in this repo): use `*_debit_spread` /
    `*_credit_spread`, not `bull_*` / `bear_*`. Existing aliases are normalized
    on read via STRUCTURE_ALIASES.
    """
    if opt_type == "call":
        if long_strike < short_strike:
            return "call_debit_spread"   # = bull_call_spread
        return "call_credit_spread"      # = bear_call_spread
    # put
    if long_strike > short_strike:
        return "put_debit_spread"        # = bear_put_spread
    return "put_credit_spread"           # = bull_put_spread


# Map alternate structure names to their canonical form so DB rows written with
# old conventions still match the CSV-derived key.
STRUCTURE_ALIASES: Dict[str, str] = {
    "bull_call_spread": "call_debit_spread",
    "bear_call_spread": "call_credit_spread",
    "bear_put_spread": "put_debit_spread",
    "bull_put_spread": "put_credit_spread",
}


def _canon_structure(s: Optional[str]) -> str:
    s = (s or "").lower()
    return STRUCTURE_ALIASES.get(s, s)


# Structures that store naked single-leg options. The existing schema convention
# is to leave BOTH strike columns NULL for these (price-updater limitation —
# see PROJECT_RULES.md). When matching keys, treat strike as "don't care" for
# these structures so a CSV row with long_strike=$4 matches a DB row with NULLs.
NAKED_SINGLE_LEG = frozenset({"long_call", "long_put", "naked_call", "naked_put",
                              "short_call", "short_put"})


def _pair_legs_greedy(opens_or_closes: List[Txn]) -> List[Tuple[Txn, Txn]]:
    """Pair BTO with STO (or BTC with STC) greedily by qty for vertical spreads.

    Returns list of paired (long_leg, short_leg) tuples. Unpaired legs are
    *returned in `unpaired_legs` of the caller via leftovers* — but for the
    purpose of leg matching, we just emit what we matched. Caller handles rest.
    """
    longs = [t for t in opens_or_closes if t.trans_code in ("BTO", "BTC")]
    shorts = [t for t in opens_or_closes if t.trans_code in ("STO", "STC")]

    # Sort by qty descending so larger contracts get matched first
    longs.sort(key=lambda t: t.quantity, reverse=True)
    shorts.sort(key=lambda t: t.quantity, reverse=True)

    pairs: List[Tuple[Txn, Txn]] = []
    used_short: set = set()
    for lo in longs:
        # Match exact qty first
        match_idx = None
        for i, sh in enumerate(shorts):
            if i in used_short:
                continue
            if sh.quantity == lo.quantity:
                match_idx = i
                break
        if match_idx is None:
            # Any short with same qty? Otherwise pick first remaining
            for i, sh in enumerate(shorts):
                if i not in used_short:
                    match_idx = i
                    break
        if match_idx is not None:
            pairs.append((lo, shorts[match_idx]))
            used_short.add(match_idx)
    return pairs


def _make_vertical_position_key(long_leg: Txn, short_leg: Txn) -> Tuple[PositionKey, Decimal, int]:
    """For an open pair, return (position_key, net_debit_per_unit, qty)."""
    structure = _structure_from_legs(long_leg.option_type, long_leg.strike, short_leg.strike)
    is_debit = structure in ("bull_call_spread", "put_debit_spread")
    # Net debit per unit (positive when we paid premium; negative if we received)
    if long_leg.price is None or short_leg.price is None:
        net = Decimal(0)
    else:
        net = long_leg.price - short_leg.price  # debit = pay long - receive short
    if not is_debit:
        # Credit spread: we sold the more expensive leg, so net flipped to negative.
        # Store as positive premium received (entry_price column = abs value per Brief 05b).
        # For our purposes we keep entry_price = abs(net).
        pass
    qty = min(long_leg.quantity, short_leg.quantity)
    key = PositionKey(
        ticker=long_leg.ticker,
        structure=structure,
        expiry=long_leg.expiry,
        long_strike=long_leg.strike,
        short_strike=short_leg.strike,
    )
    return key, net, qty


def _make_multi_leg_position(ticker: str, opt_type: str, expiry: date,
                             opens_by_date_legs: List[Txn]) -> Tuple[PositionKey, Decimal, int, List[Dict[str, Any]], str]:
    """Construct a multi-leg structure (HYG-style) from same-date opens.

    All legs must share the same expiry + option_type. We pick the outermost
    long + short strikes for the 2-leg schema columns, and store the full leg
    set in `legs` JSONB.
    """
    label, mapped_structure = MULTI_LEG_HINTS[ticker]

    # Per-leg net cost: BTO contributes +price (paid), STO contributes -price (received)
    legs_payload: List[Dict[str, Any]] = []
    long_strikes: List[Decimal] = []
    short_strikes: List[Decimal] = []
    net_per_unit = Decimal(0)
    qty = None
    for t in opens_by_date_legs:
        side = "long" if t.trans_code in ("BTO", "BTC") else "short"
        legs_payload.append({
            "strike": float(t.strike),
            "side": side,
            "qty": t.quantity,
            "option_type": opt_type,
        })
        if side == "long":
            long_strikes.append(t.strike)
            net_per_unit += (t.price or Decimal(0))
        else:
            short_strikes.append(t.strike)
            net_per_unit -= (t.price or Decimal(0))
        if qty is None:
            qty = t.quantity
        else:
            qty = min(qty, t.quantity)

    # Outermost long, outermost short (for the 2-leg compressed schema)
    if opt_type == "put":
        # Put structure: long = highest, short = lowest
        long_strike = max(long_strikes) if long_strikes else None
        short_strike = min(short_strikes) if short_strikes else None
    else:
        # Call: long = lowest, short = highest
        long_strike = min(long_strikes) if long_strikes else None
        short_strike = max(short_strikes) if short_strikes else None

    key = PositionKey(
        ticker=ticker,
        structure=mapped_structure,
        expiry=expiry,
        long_strike=long_strike,
        short_strike=short_strike,
    )
    return key, net_per_unit, (qty or 0), legs_payload, label


def _option_groups(txns_on_date: List[Txn]) -> Dict[Tuple[str, date, str], List[Txn]]:
    """Group same-date option txns by (ticker, expiry, option_type)."""
    out: Dict[Tuple[str, date, str], List[Txn]] = defaultdict(list)
    for t in txns_on_date:
        if not t.is_option:
            continue
        if t.expiry is None or t.option_type is None:
            continue
        out[(t.ticker, t.expiry, t.option_type)].append(t)
    return out


def build_open_book(txns: List[Txn]) -> Dict[PositionKey, PositionState]:
    """Walk transactions chronologically and reconstruct the currently-open book."""
    book: Dict[PositionKey, PositionState] = {}
    warnings: List[str] = []

    # Group by date
    by_date: Dict[date, List[Txn]] = defaultdict(list)
    for t in txns:
        by_date[t.activity_date].append(t)

    for d in sorted(by_date.keys()):
        groups = _option_groups(by_date[d])

        # Handle OPENS first
        for (ticker, expiry, opt_type), group in groups.items():
            opens = [t for t in group if t.trans_code in OPEN_OPT_CODES]
            if not opens:
                continue

            if ticker in MULTI_LEG_HINTS:
                key, net, qty, legs_payload, label = _make_multi_leg_position(
                    ticker, opt_type, expiry, opens
                )
                if qty <= 0:
                    continue
                state = book.setdefault(key, PositionState(key=key, full_legs=legs_payload,
                                                          notes=f"Structure: {label}"))
                state.quantity += qty
                state.opens.append((d, qty, net))
                # Keep full_legs from first open (they should match across days; if RH
                # changes leg structure across opens, that's a flag worth noting).
                if not state.full_legs:
                    state.full_legs = legs_payload
                continue

            # Standard vertical pairing
            btos = [t for t in opens if t.trans_code == "BTO"]
            stos = [t for t in opens if t.trans_code == "STO"]
            if btos and stos:
                pairs = _pair_legs_greedy(opens)
                for lo, sh in pairs:
                    key, net, qty = _make_vertical_position_key(lo, sh)
                    if qty <= 0:
                        continue
                    state = book.setdefault(key, PositionState(key=key))
                    state.quantity += qty
                    state.opens.append((d, qty, abs(net)))  # Store as positive (debit paid OR credit received)
                # Detect unpaired leftovers
                paired_long_ids = {id(p[0]) for p in pairs}
                paired_short_ids = {id(p[1]) for p in pairs}
                unpaired = [t for t in btos if id(t) not in paired_long_ids] + \
                           [t for t in stos if id(t) not in paired_short_ids]
                if unpaired:
                    warnings.append(
                        f"Unpaired open legs on {d} for {ticker} {expiry} {opt_type}: "
                        + ", ".join(f"{t.trans_code} ${t.strike}x{t.quantity}" for t in unpaired)
                    )
            elif btos and not stos:
                # Naked long opens. Existing DB convention is long_strike=NULL
                # for long_call/long_put (per the schema limitation in
                # PROJECT_RULES.md). Match that convention in the key so we
                # don't double-count against existing DB rows, but preserve the
                # strike in legs JSONB.
                for t in btos:
                    structure = f"long_{opt_type}"
                    key = PositionKey(
                        ticker=ticker, structure=structure,
                        expiry=expiry, long_strike=None, short_strike=None,
                    )
                    state = book.setdefault(key, PositionState(key=key))
                    state.quantity += t.quantity
                    state.opens.append((d, t.quantity, t.price or Decimal(0)))
                    # Track the actual strike in legs JSONB
                    if not state.full_legs:
                        state.full_legs = [{
                            "strike": float(t.strike), "side": "long",
                            "qty": t.quantity, "option_type": opt_type,
                        }]
                    else:
                        # additive — sum qty for same strike
                        existing = next((l for l in state.full_legs
                                         if Decimal(str(l["strike"])) == t.strike), None)
                        if existing:
                            existing["qty"] += t.quantity
                        else:
                            state.full_legs.append({
                                "strike": float(t.strike), "side": "long",
                                "qty": t.quantity, "option_type": opt_type,
                            })
            elif stos and not btos:
                # Naked short opens — not currently in scope but record + warn
                for t in stos:
                    structure = f"naked_{opt_type}"
                    key = PositionKey(
                        ticker=ticker, structure=structure,
                        expiry=expiry, long_strike=None, short_strike=t.strike,
                    )
                    state = book.setdefault(key, PositionState(key=key))
                    state.quantity += t.quantity
                    state.opens.append((d, t.quantity, -(t.price or Decimal(0))))
                warnings.append(f"Naked short opens on {d} for {ticker}: review schema modeling")

        # Handle CLOSES + EXPIRIES
        for (ticker, expiry, opt_type), group in groups.items():
            # OEXP
            oexps = [t for t in group if t.trans_code == OEXP_CODE]
            for t in oexps:
                # Match an OPEN position whose strikes/structure contain this strike
                matched = _match_close(book, ticker, expiry, opt_type, t.strike, t.quantity, expiry_only=True)
                if matched:
                    pkey, qty = matched
                    state = book[pkey]
                    # OEXP rows come paired (one per leg), so we only want to count
                    # quantity reduction once per position. Use first-match-only
                    # semantics: if this OEXP qty matches state.quantity exactly,
                    # and a previous OEXP on this date already reduced it, skip.
                    # Simpler: only reduce when current quantity > 0 AND last close
                    # on this date wasn't already at full-position size.
                    already_oexp_today = (state.last_close_date == d
                                          and any(r == "OEXP" for _, _, _, r in state.closes
                                                  if _ == d))
                    if not already_oexp_today:
                        reduce_by = min(qty, state.quantity)
                        state.quantity -= reduce_by
                        state.closes.append((d, reduce_by, Decimal(0), "OEXP"))

            # Closes
            closes = [t for t in group if t.trans_code in CLOSE_OPT_CODES]
            if not closes:
                continue

            if ticker in MULTI_LEG_HINTS:
                # Match by ticker/expiry/option_type. Find the open multi-leg position.
                matched = _match_multi_leg_close(book, ticker, expiry, opt_type)
                if matched:
                    pkey = matched
                    state = book[pkey]
                    # Net credit per unit = sum of close prices (longs received credit by STC,
                    # shorts paid by BTC). For multi-leg use first leg's qty as the unit.
                    btcs = [t for t in closes if t.trans_code == "BTC"]
                    stcs = [t for t in closes if t.trans_code == "STC"]
                    qty = 0
                    if btcs or stcs:
                        qty = min((min(t.quantity for t in btcs) if btcs else 999),
                                  (min(t.quantity for t in stcs) if stcs else 999))
                    net_credit = Decimal(0)
                    for t in stcs:
                        net_credit += (t.price or Decimal(0))
                    for t in btcs:
                        net_credit -= (t.price or Decimal(0))
                    reduce_by = min(qty, state.quantity)
                    state.quantity -= reduce_by
                    state.closes.append((d, reduce_by, net_credit, "CLOSE"))
                continue

            # Standard vertical close: aggregate by strike+side, then pair.
            # RH sometimes splits a single multi-contract close into one row per
            # contract (e.g., IWM 5/21: BTC 240×2 paired against STC 250×1 + STC 250×1).
            # Row-by-row greedy pairing drops the second row; aggregation fixes that.
            btcs = [t for t in closes if t.trans_code == "BTC"]
            stcs = [t for t in closes if t.trans_code == "STC"]
            if btcs and stcs:
                # Aggregate qty + weighted prices by strike
                stc_qty: Dict[Decimal, int] = defaultdict(int)
                btc_qty: Dict[Decimal, int] = defaultdict(int)
                stc_premium: Dict[Decimal, Decimal] = defaultdict(lambda: Decimal(0))
                btc_premium: Dict[Decimal, Decimal] = defaultdict(lambda: Decimal(0))
                for t in stcs:
                    stc_qty[t.strike] += t.quantity
                    stc_premium[t.strike] += (t.price or Decimal(0)) * Decimal(t.quantity)
                for t in btcs:
                    btc_qty[t.strike] += t.quantity
                    btc_premium[t.strike] += (t.price or Decimal(0)) * Decimal(t.quantity)

                stc_strikes = sorted(stc_qty.keys())
                btc_strikes = sorted(btc_qty.keys())

                if len(stc_strikes) == 1 and len(btc_strikes) == 1:
                    # Standard single-vertical close
                    stc_k = stc_strikes[0]
                    btc_k = btc_strikes[0]
                    structure = _structure_from_legs(opt_type, stc_k, btc_k)
                    key = PositionKey(
                        ticker=ticker, structure=structure,
                        expiry=expiry, long_strike=stc_k, short_strike=btc_k,
                    )
                    if key not in book:
                        alt = PositionKey(
                            ticker=ticker, structure=structure,
                            expiry=expiry, long_strike=btc_k, short_strike=stc_k,
                        )
                        if alt in book:
                            key = alt
                    if key not in book:
                        warnings.append(f"Close on {d} has no matching open: {key.display()}")
                    else:
                        qty = min(stc_qty[stc_k], btc_qty[btc_k])
                        state = book[key]
                        reduce_by = min(qty, state.quantity)
                        if reduce_by > 0:
                            avg_stc = stc_premium[stc_k] / Decimal(stc_qty[stc_k])
                            avg_btc = btc_premium[btc_k] / Decimal(btc_qty[btc_k])
                            net_credit = avg_stc - avg_btc
                            state.quantity -= reduce_by
                            state.closes.append((d, reduce_by, net_credit, "CLOSE"))
                else:
                    # Multi-strike close (stacked verticals on same day). Warn —
                    # not seen in current data; if needed, this is the place to
                    # build a strike-pairing heuristic.
                    warnings.append(
                        f"Multi-strike close on {d} for {ticker} {expiry} {opt_type}: "
                        f"STC strikes={stc_strikes}, BTC strikes={btc_strikes}. "
                        "Single-pair handler skipped; review manually."
                    )
            elif btcs and not stcs:
                # Closing a naked short
                for t in btcs:
                    structure = f"naked_{opt_type}"
                    key = PositionKey(ticker=ticker, structure=structure,
                                      expiry=expiry, long_strike=None, short_strike=t.strike)
                    if key in book:
                        state = book[key]
                        reduce_by = min(t.quantity, state.quantity)
                        state.quantity -= reduce_by
                        state.closes.append((d, reduce_by, -(t.price or Decimal(0)), "CLOSE"))
            elif stcs and not btcs:
                # Closing naked long
                for t in stcs:
                    structure = f"long_{opt_type}"
                    key = PositionKey(ticker=ticker, structure=structure,
                                      expiry=expiry, long_strike=t.strike, short_strike=None)
                    if key in book:
                        state = book[key]
                        reduce_by = min(t.quantity, state.quantity)
                        state.quantity -= reduce_by
                        state.closes.append((d, reduce_by, t.price or Decimal(0), "CLOSE"))

    if warnings:
        for w in warnings:
            logger.warning(w)

    return book


def _match_close(book: Dict[PositionKey, "PositionState"],
                 ticker: str, expiry: date, opt_type: str, strike: Optional[Decimal],
                 qty: int, expiry_only: bool = False) -> Optional[Tuple[PositionKey, int]]:
    """Find a candidate open position that this close transaction touches."""
    for key, state in book.items():
        if key.ticker != ticker or key.expiry != expiry:
            continue
        if state.quantity <= 0:
            continue
        struct = key.structure
        if opt_type not in struct and not (
            (opt_type == "call" and "call" in struct)
            or (opt_type == "put" and "put" in struct)
        ):
            continue
        if expiry_only:
            return key, qty
        if strike is not None and strike not in (key.long_strike, key.short_strike):
            continue
        return key, qty
    return None


def _match_multi_leg_close(book: Dict[PositionKey, "PositionState"],
                           ticker: str, expiry: date, opt_type: str) -> Optional[PositionKey]:
    for key, state in book.items():
        if key.ticker == ticker and key.expiry == expiry and state.quantity > 0:
            struct = key.structure
            if (opt_type == "put" and "put" in struct) or (opt_type == "call" and "call" in struct):
                return key
    return None


def filter_open_book(
    book: Dict[PositionKey, PositionState],
    today: Optional[date] = None,
) -> Dict[PositionKey, PositionState]:
    """Drop positions whose qty walked to zero (fully closed) or whose expiry
    is past `today` (the auto-expire-sweep in the API would mark them EXPIRED
    anyway, and inserting them as OPEN would be churn).

    `today` defaults to date.today() and can be overridden in tests.
    """
    today = today or date.today()
    out: Dict[PositionKey, PositionState] = {}
    dropped_expired: List[str] = []
    for k, s in book.items():
        if s.quantity <= 0:
            continue
        if k.expiry is not None and k.expiry < today:
            dropped_expired.append(f"{k.display()} qty={s.quantity}")
            continue
        out[k] = s
    if dropped_expired:
        logger.info(
            "Filtered %d position(s) past expiry (handled by auto-expire-sweep): %s",
            len(dropped_expired), "; ".join(dropped_expired),
        )
    return out


# ── Reporting ─────────────────────────────────────────────────────────

def format_csv_book_report(book: Dict[PositionKey, PositionState],
                           csv_paths: List[Path], csv_sha: str,
                           today: date) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append("RH CSV Sync — Derived Open Book (account=ROBINHOOD)")
    lines.append("=" * 70)
    lines.append(f"CSVs:")
    for p in csv_paths:
        lines.append(f"  - {p}")
    lines.append(f"CSV sha256: {csv_sha[:16]}…")
    lines.append(f"As of: {today.isoformat()}")
    lines.append("")

    if not book:
        lines.append("No open positions reconstructed from CSV.")
        return "\n".join(lines)

    # Sort by expiry then ticker
    sorted_keys = sorted(book.keys(), key=lambda k: (k.expiry or date.max, k.ticker))
    for key in sorted_keys:
        state = book[key]
        avg = state.avg_entry_debit()
        if key.short_strike is None and key.long_strike is not None:
            disp = f"{key.ticker} {key.expiry} ${key.long_strike:g} {key.structure}"
        elif key.long_strike is not None and key.short_strike is not None:
            disp = f"{key.ticker} {key.expiry} ${key.long_strike:g}/${key.short_strike:g} {key.structure}"
        else:
            disp = f"{key.ticker} {key.expiry} {key.structure}"
        lines.append(f"  {disp} × {state.quantity}  @ ${avg:.4f} avg debit")
        if state.full_legs:
            lines.append(f"      legs: {state.full_legs}")
        opens_str = ", ".join(f"{d.isoformat()} ×{q} @${dp:.4f}" for d, q, dp in state.opens)
        lines.append(f"      opens: {opens_str}")
        if state.closes:
            closes_str = ", ".join(f"{d.isoformat()} ×{q} @${cp:.4f} ({r})" for d, q, cp, r in state.closes)
            lines.append(f"      closes (partial): {closes_str}")
    lines.append("")
    lines.append(f"Total open positions: {len(book)}")
    return "\n".join(lines)


# ── DB diff + apply ───────────────────────────────────────────────────

def _normalize_db_row_to_key(row: Dict[str, Any]) -> PositionKey:
    """Build a PositionKey from a DB row using the same canonicalization the
    parser uses, so dict lookups match across:
      - structure aliases (bull_call_spread / call_debit_spread, etc.)
      - naked single-leg strike conventions (DB stores NULL; parser normalizes
        to NULL as well so they match).
    """
    expiry = row.get("expiry")
    if isinstance(expiry, datetime):
        expiry = expiry.date()
    elif isinstance(expiry, str):
        try:
            expiry = date.fromisoformat(expiry[:10])
        except Exception:
            expiry = None
    structure = _canon_structure(row.get("structure"))
    long_strike = Decimal(str(row["long_strike"])) if row.get("long_strike") is not None else None
    short_strike = Decimal(str(row["short_strike"])) if row.get("short_strike") is not None else None
    if structure in NAKED_SINGLE_LEG:
        long_strike = None
        short_strike = None
    return PositionKey(
        ticker=(row.get("ticker") or "").upper(),
        structure=structure,
        expiry=expiry,
        long_strike=long_strike,
        short_strike=short_strike,
    )


def fetch_db_open_positions(conn) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT position_id, ticker, structure, direction, quantity,
                   entry_price, cost_basis, max_loss, max_profit,
                   long_strike, short_strike, expiry, status,
                   entry_date, legs, source, account, notes
              FROM unified_positions
             WHERE account = 'ROBINHOOD' AND status = 'OPEN'
            """
        )
        cols = [d[0] for d in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return rows


def compute_diff(csv_book: Dict[PositionKey, PositionState],
                 db_rows: List[Dict[str, Any]]) -> List[Action]:
    """Diff CSV-derived book against DB rows. Return list of Actions."""
    db_by_key: Dict[PositionKey, Dict[str, Any]] = {}
    for r in db_rows:
        db_by_key[_normalize_db_row_to_key(r)] = r

    actions: List[Action] = []

    # Positions in CSV but not in DB -> INSERT
    # Positions in CSV and DB -> check qty/entry_price -> UPDATE if different
    # Positions in DB but not in CSV -> flag for manual review (NO_OP_FLAG)
    seen_keys: set = set()
    for csv_key, csv_state in csv_book.items():
        seen_keys.add(csv_key)
        db_row = db_by_key.get(csv_key)
        if db_row is None:
            actions.append(Action(op="INSERT", position_key=csv_key, csv_state=csv_state))
        else:
            db_qty = int(db_row.get("quantity") or 0)
            db_entry = Decimal(str(db_row.get("entry_price") or 0))
            csv_qty = csv_state.quantity
            csv_entry = csv_state.avg_entry_debit().quantize(Decimal("0.0001"))
            if csv_qty != db_qty or csv_entry != db_entry.quantize(Decimal("0.0001")):
                actions.append(Action(
                    op="UPDATE", position_key=csv_key,
                    csv_state=csv_state, db_row=db_row,
                    notes=f"qty {db_qty}->{csv_qty}, entry ${db_entry}->${csv_entry}",
                ))

    for db_key, db_row in db_by_key.items():
        if db_key in seen_keys:
            continue
        # DB has OPEN row that CSV didn't reconstruct -> it must have closed.
        # If the position has expiry < today, the existing auto-expire-sweep
        # will catch it; but we should still flag it explicitly.
        actions.append(Action(
            op="CLOSE", position_key=db_key, db_row=db_row,
            notes="In DB as OPEN; CSV walk does not show it open as of now",
        ))

    return actions


def format_diff_report(actions: List[Action], csv_paths: List[Path],
                       csv_sha: str, today: date, mode: str) -> str:
    lines = []
    lines.append("=" * 70)
    lines.append(f"RH CSV Sync — Diff Report  [{mode}]")
    lines.append("=" * 70)
    lines.append(f"CSVs:")
    for p in csv_paths:
        lines.append(f"  - {p}")
    lines.append(f"CSV sha256: {csv_sha[:16]}…")
    lines.append(f"DB queried at: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Mode: {mode}")
    lines.append("")

    counts = defaultdict(int)
    for a in actions:
        counts[a.op] += 1

    lines.append("Summary:")
    for op in ("INSERT", "UPDATE", "CLOSE", "NO_OP_FLAG"):
        lines.append(f"  {op}: {counts[op]}")
    lines.append("")

    for op_filter in ("INSERT", "UPDATE", "CLOSE", "NO_OP_FLAG"):
        ops = [a for a in actions if a.op == op_filter]
        if not ops:
            continue
        lines.append(f"--- {op_filter} ({len(ops)}) ---")
        for a in ops:
            key = a.position_key
            lines.append(f"  {key.display()}")
            if a.csv_state:
                lines.append(f"    csv: qty={a.csv_state.quantity} avg=${a.csv_state.avg_entry_debit():.4f}")
            if a.db_row:
                lines.append(f"    db:  qty={a.db_row.get('quantity')} entry=${a.db_row.get('entry_price')} pid={a.db_row.get('position_id')}")
            if a.notes:
                lines.append(f"    note: {a.notes}")
        lines.append("")

    if mode == "DRY-RUN":
        lines.append("DRY-RUN: no changes applied. Re-run with --apply to execute.")
    return "\n".join(lines)


# ── Apply ─────────────────────────────────────────────────────────────

def _gen_position_id(ticker: str, entry_date: date, key: "PositionKey") -> str:
    """Generate a unique position_id.

    The existing convention is `POS_<TICKER>_<YYYYMMDD>_<HHMMSS>` where the
    time portion was the wall-clock time when the API minted the row. For
    sync-batch INSERTs that all happen in the same second, we instead derive
    a 6-hex-char suffix from a hash of the position key, so two positions for
    the same ticker opened on the same day (e.g. IBIT 5/29 and IBIT 7/17, both
    opened 5/22) get distinct, deterministic IDs.
    """
    key_repr = "|".join((
        key.ticker,
        key.structure,
        key.expiry.isoformat() if key.expiry else "",
        str(key.long_strike) if key.long_strike is not None else "",
        str(key.short_strike) if key.short_strike is not None else "",
    ))
    h = hashlib.sha256(key_repr.encode()).hexdigest()[:6]
    return f"POS_{ticker.upper()}_{entry_date.strftime('%Y%m%d')}_{h}"


def _structure_to_direction(structure: str) -> str:
    s = structure.lower()
    if s in ("long_call", "bull_call_spread", "put_credit_spread", "bull_put_spread"):
        return "LONG"
    if s in ("long_put", "bear_call_spread", "bear_put_spread", "put_debit_spread"):
        return "SHORT"
    if s in ("naked_call", "short_call", "naked_put", "short_put"):
        return "SHORT" if "call" in s else "LONG"
    return "MIXED"


def apply_actions(conn, actions: List[Action], run_id: uuid.UUID,
                  csv_paths: List[Path], csv_sha: str) -> None:
    """Apply all actions in a single DB transaction. Audit each operation."""
    csv_paths_joined = ",".join(p.name for p in csv_paths)

    with conn:  # transaction
        with conn.cursor() as cur:
            for a in actions:
                if a.op == "INSERT":
                    _apply_insert(cur, a, run_id, csv_paths_joined, csv_sha)
                elif a.op == "UPDATE":
                    _apply_update(cur, a, run_id, csv_paths_joined, csv_sha)
                elif a.op == "CLOSE":
                    _apply_close(cur, a, run_id, csv_paths_joined, csv_sha)
                # NO_OP_FLAG: audit only, no DB write to unified_positions
                else:
                    _audit(cur, run_id, csv_paths_joined, csv_sha, a.op, None,
                           a.position_key.ticker, a.position_key.structure,
                           None, None, a.notes)


def _apply_insert(cur, a: Action, run_id, csv_paths_joined: str, csv_sha: str) -> None:
    key = a.position_key
    state = a.csv_state
    assert state is not None

    avg_entry = state.avg_entry_debit().quantize(Decimal("0.0001"))
    qty = state.quantity
    is_naked = key.short_strike is None
    # Cost basis: abs(entry) * qty * 100 for options
    cost_basis = (abs(avg_entry) * qty * Decimal(100)).quantize(Decimal("0.01"))

    direction = _structure_to_direction(key.structure)

    # Max loss for debit verticals = total debit; for naked long = total premium paid
    max_loss = cost_basis if key.structure in (
        "put_debit_spread", "bull_call_spread", "long_call", "long_put",
    ) else None
    # Max profit for debit vertical = (width - debit) * 100 * qty
    max_profit = None
    if key.long_strike is not None and key.short_strike is not None and key.structure in (
        "put_debit_spread", "bull_call_spread",
    ):
        width = abs(key.long_strike - key.short_strike)
        max_profit = ((width - abs(avg_entry)) * Decimal(100) * qty).quantize(Decimal("0.01"))

    entry_date = state.first_open_date or date.today()
    position_id = _gen_position_id(key.ticker, entry_date, key)
    legs_json = json.dumps(state.full_legs) if state.full_legs else None

    notes = state.notes or ""
    if state.opens and len(state.opens) > 1:
        ops = "; ".join(f"{d.isoformat()} ×{q} @${dp:.4f}" for d, q, dp in state.opens)
        notes = (notes + (" | " if notes else "") + f"opens: {ops}").strip()

    cur.execute(
        """
        INSERT INTO unified_positions (
            position_id, ticker, asset_type, structure, direction, legs,
            entry_price, entry_date, quantity, cost_basis,
            max_loss, max_profit,
            expiry, long_strike, short_strike,
            source, account, notes, status
        ) VALUES (
            %s, %s, 'OPTION', %s, %s, %s::jsonb,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            'CSV_SYNC', 'ROBINHOOD', %s, 'OPEN'
        )
        RETURNING position_id
        """,
        (
            position_id, key.ticker, key.structure, direction, legs_json,
            float(abs(avg_entry)), entry_date, qty, float(cost_basis),
            float(max_loss) if max_loss is not None else None,
            float(max_profit) if max_profit is not None else None,
            key.expiry,
            float(key.long_strike) if key.long_strike is not None else None,
            float(key.short_strike) if key.short_strike is not None else None,
            notes or None,
        ),
    )
    new_pid = cur.fetchone()[0]
    _audit(cur, run_id, csv_paths_joined, csv_sha, "INSERT", new_pid,
           key.ticker, key.structure, None, _state_to_jsonable(state, key), a.notes)


def _apply_update(cur, a: Action, run_id, csv_paths_joined: str, csv_sha: str) -> None:
    state = a.csv_state
    db_row = a.db_row
    assert state is not None and db_row is not None
    pid = db_row["position_id"]

    avg_entry = state.avg_entry_debit().quantize(Decimal("0.0001"))
    qty = state.quantity
    cost_basis = (abs(avg_entry) * qty * Decimal(100)).quantize(Decimal("0.01"))

    before = {k: _jsonable(v) for k, v in db_row.items()}

    cur.execute(
        """
        UPDATE unified_positions
           SET quantity = %s,
               entry_price = %s,
               cost_basis = %s,
               legs = COALESCE(%s::jsonb, legs),
               updated_at = NOW()
         WHERE position_id = %s
         RETURNING quantity, entry_price, cost_basis
        """,
        (
            qty, float(abs(avg_entry)), float(cost_basis),
            json.dumps(state.full_legs) if state.full_legs else None,
            pid,
        ),
    )
    new_q, new_e, new_cb = cur.fetchone()
    after = {**before, "quantity": new_q, "entry_price": float(new_e), "cost_basis": float(new_cb)}
    _audit(cur, run_id, csv_paths_joined, csv_sha, "UPDATE", pid,
           a.position_key.ticker, a.position_key.structure, before, after, a.notes)


def _apply_close(cur, a: Action, run_id, csv_paths_joined: str, csv_sha: str) -> None:
    db_row = a.db_row
    assert db_row is not None
    pid = db_row["position_id"]
    before = {k: _jsonable(v) for k, v in db_row.items()}

    today_dt = datetime.now(timezone.utc)
    cur.execute(
        """
        UPDATE unified_positions
           SET status = 'CLOSED',
               exit_date = %s,
               updated_at = NOW()
         WHERE position_id = %s
         RETURNING status, exit_date
        """,
        (today_dt, pid),
    )
    cur.fetchone()
    after = {**before, "status": "CLOSED", "exit_date": today_dt.isoformat()}
    _audit(cur, run_id, csv_paths_joined, csv_sha, "CLOSE", pid,
           a.position_key.ticker, a.position_key.structure, before, after, a.notes)


def _audit(cur, run_id, csv_paths_joined: str, csv_sha: str,
           op: str, pid: Optional[str], ticker: str, structure: str,
           before: Optional[Dict[str, Any]], after: Optional[Dict[str, Any]],
           notes: str) -> None:
    cur.execute(
        """
        INSERT INTO position_sync_audit (
            sync_run_id, csv_paths, csv_sha256, operation,
            position_id, ticker, structure,
            before_state, after_state, notes
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)
        """,
        (
            str(run_id), csv_paths_joined, csv_sha, op,
            pid, ticker, structure,
            json.dumps(before) if before is not None else None,
            json.dumps(after) if after is not None else None,
            notes or None,
        ),
    )


def _jsonable(v: Any) -> Any:
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def _state_to_jsonable(state: PositionState, key: PositionKey) -> Dict[str, Any]:
    return {
        "ticker": key.ticker,
        "structure": key.structure,
        "expiry": key.expiry.isoformat() if key.expiry else None,
        "long_strike": float(key.long_strike) if key.long_strike is not None else None,
        "short_strike": float(key.short_strike) if key.short_strike is not None else None,
        "quantity": state.quantity,
        "avg_entry_debit": float(state.avg_entry_debit()),
        "opens": [{"date": d.isoformat(), "qty": q, "debit_per_unit": float(dp)} for d, q, dp in state.opens],
        "full_legs": state.full_legs or None,
    }


# ── CLI ───────────────────────────────────────────────────────────────

def main(argv: Optional[List[str]] = None) -> int:
    # Windows console defaults to cp1252; report output uses unicode (×, —, …).
    # Force stdout/stderr to UTF-8 so printing doesn't UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except Exception:
            pass

    parser = argparse.ArgumentParser(description="Reconcile unified_positions against RH CSV exports.")
    parser.add_argument("csv_path", help="Path to a CSV file or a directory containing CSVs.")
    parser.add_argument("--csv-only", action="store_true",
                        help="Parse CSV and print derived book only. No DB access.")
    parser.add_argument("--apply", action="store_true",
                        help="Execute the diff against the database. Default is dry-run.")
    parser.add_argument("--account", default="ROBINHOOD",
                        help="Account scope. RH-only in v1 (default).")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.account.upper() != "ROBINHOOD":
        logger.error("Only --account ROBINHOOD is supported in v1.")
        return 2

    csv_input = Path(args.csv_path)
    csv_paths = gather_csvs(csv_input)
    if not csv_paths:
        logger.error("No CSV files found at %s", csv_input)
        return 2

    txns, csv_sha = parse_all(csv_paths)
    logger.info("Parsed %d transactions from %d CSV file(s)", len(txns), len(csv_paths))

    book = filter_open_book(build_open_book(txns))
    logger.info("Reconstructed %d currently-open positions", len(book))

    today = date.today()

    if args.csv_only:
        print(format_csv_book_report(book, csv_paths, csv_sha, today))
        return 0

    # DB access required for both dry-run and --apply
    try:
        import psycopg2
    except ImportError:
        logger.error("psycopg2 not installed; install it or use --csv-only.")
        return 2

    db_url = os.environ.get("DATABASE_PUBLIC_URL") or os.environ.get("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_PUBLIC_URL/DATABASE_URL not set. Use --csv-only for offline check.")
        return 2

    conn = psycopg2.connect(db_url, connect_timeout=15)
    try:
        db_rows = fetch_db_open_positions(conn)
        logger.info("Fetched %d open positions from unified_positions (account=ROBINHOOD)", len(db_rows))

        actions = compute_diff(book, db_rows)
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(format_diff_report(actions, csv_paths, csv_sha, today, mode))

        if args.apply:
            run_id = uuid.uuid4()
            logger.info("Applying %d actions in single transaction. sync_run_id=%s", len(actions), run_id)
            apply_actions(conn, actions, run_id, csv_paths, csv_sha)
            print(f"\nAPPLIED. sync_run_id = {run_id}")
            print(f"Audit rows written to position_sync_audit.")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
