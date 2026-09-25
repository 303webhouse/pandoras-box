"""R-IV.566(e)2 / R-IV.577(a) — THE ONE AUTHOR of "this row is crypto".

WHY A MODULE FOR ONE PREDICATE. The exclusion has to hold on four separate SELECTs
and on the page. Written out four times it is four chances for one of them to be
edited, or for a fifth feed to be added without it, and the symptom is not an error:
the feed simply fills with crypto again, which is exactly the state this replaces.

MEASURED, both ends, independently:
  * the table: 51 of 78 ACTIVE signals were crypto, 43 of them one family
    (TRAPPED_SHORTS / Crypto Scanner);
  * the page (ABACUS): 71 of 95 ideas, and a 50-row page holding 45 crypto to 5
    equity -- which pushed HYG and AVGO, the only two rows that could ever grade A,
    off the page entirely.

The two counts differ because they were taken at different minutes on a table that
turns over in 24 hours. The SHAPE is the same and that is the finding.

THE PAGE-SIDE FILTER COMES OUT when this lands (R-IV.577(a)). That is the point of a
single author: with the server excluding crypto and the page not, a crypto row that
still arrives is an ERROR THE PAGE CAN SHOW, rather than something hidden twice and
therefore never noticed.

`COALESCE(asset_class, '')` because the column is nullable and `NULL <> 'CRYPTO'` is
NULL, not true -- a bare `<>` would drop every row whose asset class was never set,
which is most of the equity book.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

CRYPTO = "CRYPTO"

# The SQL predicate. Interpolated, never retyped.
EXCLUDE_CRYPTO_SQL = "COALESCE(asset_class, '') <> '%s'" % CRYPTO


def is_crypto(asset_class: Optional[str]) -> bool:
    """The Python twin of the predicate, for rows already in hand."""
    return (asset_class or "").strip().upper() == CRYPTO


def row_is_crypto(row: Mapping[str, Any]) -> bool:
    return is_crypto(row.get("asset_class") if hasattr(row, "get") else None)
