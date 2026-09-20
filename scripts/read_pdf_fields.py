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

Usage, from the repo root:

    python scripts/read_pdf_fields.py STATEMENT.pdf \\
        --field "Total Account Value::money" \\
        --field "Confirmation Number::ref" \\
        --field "Trade Date::date"

    python scripts/read_pdf_fields.py STATEMENT.pdf --profile scripts/pdf_profiles/example.json

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
        shown = r["value"] if r["value"] is not None else (r["note"] or "ABSENT")
        print(f"{r['field']} [{r['type']}] {where}: {shown}")


def main(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pdf")
    ap.add_argument("--field", action="append", default=[], metavar="Label::type",
                    help="a whitelisted field and the type its value must be")
    ap.add_argument("--profile", help="JSON file: {\"fields\": [\"Label::type\", ...]}")
    ap.add_argument("--pages", default="", help="1,3,5-7 (default: all)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    specs = list(args.field)
    if args.profile:
        specs += json.loads(open(args.profile, encoding="utf-8").read()).get("fields", [])
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
