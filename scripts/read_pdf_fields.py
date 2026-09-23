"""Read NAMED FIELDS out of a PDF. Nothing else is ever printed (R-IV.465(f)).

**A mask fails open on what it has not anticipated; a field parser fails closed.**

A mask reads the whole document and hides what it recognises as sensitive, so anything it does
not recognise -- a name in a header, an account number in a footer, a reference beside the figure
you wanted -- reaches the transcript. Two instances are on record: CC-BUILD grepped a line that
held a live credential and printed it (SECURITY-DEFERRED S13), and CC-POSITIONS read a broker PDF
and printed a name and an identifier (R-IV.465(f)).

This reader inverts it. You name the fields you want and the TYPE each one must be; it returns
those values and nothing else. A label that is not whitelisted is never read. A whitelisted label
whose value is not of the declared type is reported as absent rather than returned as free text.
**There is no flag that prints the document.**

A TRADE LINE is a shape rather than a label (R-IV.470(c)): a confirmation or an activity
statement lists fills as rows, not as "Label: value" pairs. `--trade-lines` reads those rows under
the same discipline -- five named fields, each of a declared type, and nothing else off the line.
A row that is not a fill is never emitted; a fill missing the symbol or the reference reports it
ABSENT.

**PROVISIONAL, AND NOT THE READER OF RECORD (R-IV.477(d)).** On the 2026-09-18 and 2026-09-21
Fidelity confirmations this shape read **0 of 7 fills**, emitted about fourteen all-ABSENT rows
per file, and -- worse -- emitted disclosure prose as trades (symbol=STOP, reference=cannot).
Emitting page text that is not a fill breaks the whitelist's one promise. CC-POSITIONS' whitelist
parser read 7 of 7 and is the reader of record until this one clears the bar: 7/7 on both files,
every earlier confirmation matched fill for fill, and a disclosure page alone emitting nothing.
A row now needs BOTH a quantity and a price to be a fill at all, which is what kept the prose out
in the fixture here -- but the 0-of-7 miss is a shape this reader has never seen, and it is not
fixed by guessing.

Usage, from the repo root:

    python scripts/read_pdf_fields.py STATEMENT.pdf \\
        --field "Total Account Value::money" \\
        --field "Confirmation Number::ref" \\
        --field "Trade Date::date"

    python scripts/read_pdf_fields.py STATEMENT.pdf --profile scripts/pdf_profiles/example.json

    python scripts/read_pdf_fields.py CONFIRM.pdf --trade-lines

Every occurrence of a whitelisted label is reported, in document order, with its page. A label
that never occurs prints ABSENT: an honest absence is a reading, and silence is not.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Sequence, Tuple

# A value must BE one of these shapes. Free text is not a value: that is the fail-closed half.
FIELD_TYPES: Dict[str, str] = {
    "money": r"-?\(?\$?\s?-?\d{1,3}(?:,\d{3})*(?:\.\d{2})\)?|-?\$?\s?-?\d+\.\d{2}",
    "decimal": r"-?\d{1,3}(?:,\d{3})*\.\d+|-?\d+\.\d+",
    "int": r"-?\d{1,3}(?:,\d{3})*|-?\d+",
    "date": r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}",
    "ref": r"[A-Z0-9]{4,}(?:-[A-Z0-9]+)*",
    "percent": r"-?\d+(?:\.\d+)?\s?%",
}
WINDOW = 80          # how far past a label a value may sit, in characters

# --- the trade-line shape (R-IV.470(c)) ------------------------------------------------------
# Five fields, each a token of its own type. The ACTION word is what makes a row a fill; without
# one, the row is not read at all -- which is how free text (a name, an address, a message from
# the broker) stays out of the output even though it sits on the same page.
ACTIONS = {
    "BUY": "BUY", "BOUGHT": "BUY", "BOT": "BUY", "YOU BOUGHT": "BUY", "PURCHASE": "BUY",
    "SELL": "SELL", "SOLD": "SELL", "SLD": "SELL", "YOU SOLD": "SELL", "SALE": "SELL",
}
TRADE_FIELDS = ("action", "quantity", "price", "symbol", "reference")
_ACTION_RE = re.compile(r"\b(YOU BOUGHT|YOU SOLD|BOUGHT|PURCHASE|BUY|BOT|SOLD|SALE|SELL|SLD)\b",
                        re.IGNORECASE)
_QTY_RE = re.compile(r"(?<![\w.$])(\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)(?![\w.%])")
_PRICE_RE = re.compile(r"\$\s?-?\d{1,3}(?:,\d{3})*\.\d{2,4}|(?<![\w.$])-?\d+\.\d{2,4}(?![\w%])")
# A symbol is a ticker, optionally with an option description after it (strike, C/P, a date).
_SYMBOL_RE = re.compile(r"\b([A-Z]{1,6})(?:\s+(\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}))?"
                        r"(?:\s+\$?(\d+(?:\.\d+)?)\s*([CP]))?\b")
_REF_RE = re.compile(r"\b(?:REF|CONF(?:IRMATION)?|ORDER|TRADE)\s*#?\s*([A-Z0-9][A-Z0-9-]{3,})\b",
                     re.IGNORECASE)
_NOT_A_SYMBOL = {"BUY", "SELL", "BOUGHT", "SOLD", "BOT", "SLD", "YOU", "REF", "CONF", "ORDER",
                 "TRADE", "SHARES", "SHS", "AT", "USD", "PURCHASE", "SALE", "CONFIRMATION"}


def parse_field(spec: str) -> Tuple[str, str]:
    """'Total Value::money' -> ('Total Value', 'money'). The type is required: a field with no
    declared type would accept anything, which is the mask's failure in another costume."""
    label, _, kind = spec.partition("::")
    label, kind = label.strip(), kind.strip().lower()
    if not label or kind not in FIELD_TYPES:
        raise ValueError(f"field must be 'Label::type' with type in {sorted(FIELD_TYPES)}: {spec!r}")
    return label, kind


def extract_fields(pages: Sequence[str], fields: Sequence[Tuple[str, str]]) -> List[Dict[str, Any]]:
    """Every occurrence of each whitelisted label, with the first value of its declared type.

    Pure: `pages` is a list of page texts, so the whole reader is testable without a PDF. The
    returned value is the ONLY thing a caller may print -- it holds no surrounding text.
    """
    out: List[Dict[str, Any]] = []
    for label, kind in fields:
        pattern = re.compile(re.escape(label), re.IGNORECASE)
        value_re = re.compile(FIELD_TYPES[kind])
        found = 0
        for page_no, text in enumerate(pages, 1):
            for hit in pattern.finditer(text or ""):
                window = (text or "")[hit.end(): hit.end() + WINDOW]
                m = value_re.search(window)
                found += 1
                out.append({
                    "field": label, "type": kind, "page": page_no,
                    "value": m.group(0).strip() if m else None,
                    "note": None if m else f"no {kind} value within {WINDOW} characters",
                })
        if not found:
            out.append({"field": label, "type": kind, "page": None, "value": None,
                        "note": "ABSENT: the label does not occur in this document"})
    return out


def extract_trade_lines(pages: Sequence[str]) -> List[Dict[str, Any]]:
    """Fills, one record per row that carries an ACTION word. Pure, like extract_fields.

    Only the five fields are returned. Everything else on the row -- a name, a note, an address,
    a balance the reader did not ask for -- is never part of a record, because a record is built
    from typed tokens rather than from the line.
    """
    out: List[Dict[str, Any]] = []
    for page_no, text in enumerate(pages, 1):
        for raw in (text or "").splitlines():
            line = raw.strip()
            action_hit = _ACTION_RE.search(line)
            if not action_hit:
                continue
            after = line[action_hit.end():]
            price = _PRICE_RE.search(after) or _PRICE_RE.search(line)
            qty = None
            for m in _QTY_RE.finditer(after):
                if price and m.start() >= price.start() and m.end() <= price.end():
                    continue            # the price is not the quantity
                qty = m
                break
            symbol = None
            for m in _SYMBOL_RE.finditer(after):
                if m.group(1) in _NOT_A_SYMBOL:
                    continue
                symbol = m
                break
            ref = _REF_RE.search(line)
            if qty is None or price is None:
                # R-IV.477(d): a fill has a quantity AND a price. Without both, the row is prose
                # that happens to contain an action word -- the class that leaked disclosure text.
                continue
            record = {
                "page": page_no,
                "action": ACTIONS.get(action_hit.group(1).upper(), action_hit.group(1).upper()),
                "quantity": qty.group(1) if qty else None,
                "price": price.group(0).strip() if price else None,
                "symbol": symbol.group(1) if symbol else None,
                "reference": ref.group(1) if ref else None,
            }
            record["absent"] = [f for f in TRADE_FIELDS if record.get(f) is None]
            out.append(record)
    return out


def read_pages(path: str, pages: str = "") -> List[str]:
    """Page texts from the PDF. Returned to extract_fields and to nothing else."""
    from pypdf import PdfReader          # imported here so --help works without the dependency
    reader = PdfReader(path)
    wanted = _page_numbers(pages, len(reader.pages))
    return [reader.pages[i - 1].extract_text() or "" if i in wanted else "" for i in
            range(1, len(reader.pages) + 1)]


def _page_numbers(spec: str, total: int) -> set:
    if not spec:
        return set(range(1, total + 1))
    out: set = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return {p for p in out if 1 <= p <= total}


def _emit(rows: List[Dict[str, Any]], as_json: bool) -> None:
    """The one place anything is printed. It prints values of whitelisted fields, and nothing
    else -- no line, no context, no page text."""
    if as_json:
        print(json.dumps(rows, indent=2))
        return
    for r in rows:
        where = f"p{r['page']}" if r["page"] else "-"
        if "action" in r:            # a trade line: the five fields, and what was absent
            parts = " ".join(f"{f}={r[f]}" for f in TRADE_FIELDS if r.get(f) is not None)
            absent = f" ABSENT: {', '.join(r['absent'])}" if r["absent"] else ""
            print(f"trade {where}: {parts}{absent}")
            continue
        shown = r["value"] if r["value"] is not None else (r["note"] or "ABSENT")
        print(f"{r['field']} [{r['type']}] {where}: {shown}")


def main(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pdf")
    ap.add_argument("--field", action="append", default=[], metavar="Label::type",
                    help="a whitelisted field and the type its value must be")
    ap.add_argument("--profile", help="JSON file: {\"fields\": [\"Label::type\", ...]}")
    ap.add_argument("--trade-lines", action="store_true",
                    help="read fills by shape: action, quantity, price, symbol, reference")
    ap.add_argument("--pages", default="", help="1,3,5-7 (default: all)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    specs = list(args.field)
    if args.profile:
        specs += json.loads(open(args.profile, encoding="utf-8").read()).get("fields", [])
    if args.trade_lines:
        pages = read_pages(args.pdf, args.pages)
        rows = extract_trade_lines(pages)
        if specs:
            rows += extract_fields(pages, [parse_field(s) for s in specs])
        _emit(rows, args.json)
        return 0
    if not specs:
        print("no fields named: this reader returns only fields you whitelist", file=sys.stderr)
        return 2
    try:
        fields = [parse_field(s) for s in specs]
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    _emit(extract_fields(read_pages(args.pdf, args.pages), fields), args.json)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
