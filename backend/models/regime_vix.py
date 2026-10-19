"""The VIX pair §2's CRASH row reads. R-IV.1260(c)5.

WHAT CRASH ACTUALLY READS, which (c)5 asked me to report if it was not a single VIX input: it
needs BOTH `vix.vix` and `vix.vix3m`, and its hard requirement is BACKWARDATION ON THE CLOSE --
VIX above VIX3M. A VIX level alone cannot answer it, so VIXCLS by itself would have left the row
NOT EVALUABLE exactly as before.

BOTH SERIES VERIFIED AT THE SOURCE, by FRED's own page titles rather than by assuming an id:

    VIXCLS   "CBOE Volatility Index: VIX"                  http 200
    VXVCLS   "CBOE S&P 500 3-Month Volatility Index"       http 200
    VIX3M    not a FRED id                                 http 404

So VXVCLS is the 3-month companion, and the plausible-looking `VIX3M` does not exist. No
substitution: a crash row fed a 1-month VIX as its 3-month leg would read backwardation on every
session, and a row that fires every day is worse than one that never fires.

Free, like the rest of the FRED series this hub already reads, and the key is never printed.
"""

from __future__ import annotations

import datetime as _dt
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("regime_vix")

VIX_SERIES = "VIXCLS"
VIX3M_SERIES = "VXVCLS"

#: Enough history to cover the 302-session re-seed with a margin.
YEARS = 3


def by_date(years: int = YEARS) -> Tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """({'YYYY-MM-DD': {'vix': x, 'vix3m': y}}, report). Only dates where BOTH are present.

    BOTH, OR NEITHER. A date with one leg is dropped rather than carried with a null: the row
    tests one against the other, so a half-filled date is not a weaker reading of the crash
    test, it is no reading at all -- and leaving it in would make `_need` pass on a pair that
    cannot be compared.
    """
    from integrations import fred_series as fred

    out: Dict[str, Dict[str, Any]] = {}
    report: Dict[str, Any] = {"series": [VIX_SERIES, VIX3M_SERIES]}
    try:
        vix = dict((d.isoformat(), v) for d, v in fred.fetch_series(VIX_SERIES, years=years)
                   if v is not None)
        v3m = dict((d.isoformat(), v) for d, v in fred.fetch_series(VIX3M_SERIES, years=years)
                   if v is not None)
    except Exception as exc:                                        # noqa: BLE001
        report["error"] = "%s" % type(exc).__name__
        return {}, report
    report["vix_observations"] = len(vix)
    report["vix3m_observations"] = len(v3m)
    for day, v in vix.items():
        other = v3m.get(day)
        if other is None:
            continue
        out[day] = {"vix": v, "vix3m": other}
    report["paired_dates"] = len(out)
    report["dropped_unpaired"] = len(vix) - len(out)
    report["basis"] = ("FRED %s and %s, paired by date; a date carrying one leg only is dropped "
                       "because the row compares them" % (VIX_SERIES, VIX3M_SERIES))
    if not out:
        report["reason"] = ("no date carries both legs; the CRASH row stays NOT EVALUABLE, "
                            "which is not the same as 'not a crash'")
    return out, report
