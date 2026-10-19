"""`GET /api/book-reality` — B7's Book Reality Check, BEHIND A FLAG THAT IS OFF.

R-IV.1239(e)4: ships OFF. (e)5: QUERY then recomputes three rows independently -- one stock,
one debit spread, one short-premium -- each to match within 1% or $1, whichever is larger.
(e)6: the flag flips only after SPINE rules on that check.

THOSE TWO REQUIREMENTS PULL IN OPPOSITE DIRECTIONS, so the resolution is explicit rather than
implied: with the flag OFF this route computes NOTHING and returns a disabled payload, so no
modelled figure can reach the screen. QUERY's check needs the figures, so a deliberate
`?verify=1` computes the grid and labels it NOT ON SCREEN. The parameter is the only way to
make numbers while the flag is off, it is gated like every book read, and the payload says
what it is -- rather than the flag silently meaning "hidden but served", which is how a
surface goes live by accident.

GATED: it reads `unified_positions`. Every figure is labelled "model estimate".
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query

from models import book_reality_b7 as br
from utils.pivot_auth import require_api_key

logger = logging.getLogger("api_book_reality")

router = APIRouter(prefix="/book-reality", tags=["book-reality"])

#: B7'S OWN QUERY, R-IV.1246(f). It reused `SET_B_SQL`, which Position Watch wrote for a
#: different job and which carries NO expiry and NO strikes -- so `years_to_expiry` returned
#: None for every option, `price_structure` refused it, and B7 modelled 17 of 29 rows with
#: EVERY OPTION EXCLUDED. QUERY found it; the grid looked plausible because the stock rows were
#: right and the exclusions each carried a reason, so nothing read as broken.
#:
#: THE LESSON IS THE REUSE, not the three columns. A query written for one consumer's needs is
#: not a book reader, and borrowing it silently inherits its omissions. B7 selects what B7
#: prices, and a test now asserts that every column `price_structure` and `solve_iv` read is in
#: this list.
B7_SQL = """
SELECT ticker, structure, classification, bucket, account, quantity,
       entry_price, current_price, unrealized_pnl,
       expiry, long_strike, short_strike
  FROM unified_positions
 WHERE UPPER(COALESCE(status, '')) = 'OPEN'
   AND UPPER(COALESCE(status, '')) <> 'DUPLICATE_OF'
"""

#: R-IV.1239(e)4. Flipped only after SPINE rules on QUERY's three-row check (e)6. A constant,
#: not an env var: the wire coming up because a deploy variable was set is not the same event
#: as SPINE having ruled.
B7_ENABLED = False

#: Beta: 60 sessions of daily returns against SPY, Blume-adjusted 0.67b + 0.33, which is the
#: strategy-lab's own convention (§3.3) rather than a new one invented here.
BETA_SESSIONS = 60
BETA_MIN_SESSIONS = 50


def _betas_and_spots(tickers: List[str]) -> Dict[str, Any]:
    """One batched yfinance call: a spot and an adjusted beta per ticker.

    A ticker with fewer than 50 valid sessions gets beta None -- NOT 1.0. A beta defaulted to
    1 would model SQQQ as SPY, which is wrong by a factor of about three and in the wrong
    direction. The lab's own rule flags a fallback; here the position is simply not modelled.
    """
    import yfinance as yf

    syms = sorted({t.upper() for t in tickers} | {"SPY"})
    frame = yf.download(syms, period="120d", interval="1d", auto_adjust=True,
                        progress=False, threads=False, group_by="ticker")
    closes: Dict[str, List[float]] = {}
    if frame is None or getattr(frame, "empty", True):
        return {"spots": {}, "betas": {}, "note": "yfinance returned nothing"}
    for sym in syms:
        try:
            sub = frame[sym] if len(syms) > 1 else frame
        except Exception:                                           # noqa: BLE001
            continue
        if sub is None or getattr(sub, "empty", True):
            continue
        vals = []
        for _, row in sub.sort_index().iterrows():
            try:
                v = float(row["Close"])
                if v == v and v > 0:
                    vals.append(v)
            except Exception:                                       # noqa: BLE001
                continue
        if vals:
            closes[sym] = vals

    def rets(v: List[float]) -> List[float]:
        return [(v[i] / v[i - 1]) - 1.0 for i in range(1, len(v))]

    spy = rets(closes.get("SPY", []))[-BETA_SESSIONS:]
    spots = {s: v[-1] for s, v in closes.items()}
    betas: Dict[str, Optional[float]] = {}
    for sym, v in closes.items():
        r = rets(v)[-BETA_SESSIONS:]
        n = min(len(r), len(spy))
        if n < BETA_MIN_SESSIONS:
            betas[sym] = None
            continue
        x, y = spy[-n:], r[-n:]
        mx = sum(x) / n
        my = sum(y) / n
        var = sum((a - mx) ** 2 for a in x)
        if var <= 0:
            betas[sym] = None
            continue
        raw = sum((a - mx) * (b - my) for a, b in zip(x, y)) / var
        betas[sym] = 0.67 * raw + 0.33
    return {"spots": spots, "betas": betas,
            "note": "beta: %d sessions vs SPY, Blume-adjusted 0.67b + 0.33 (strategy-lab "
                    "3.3); fewer than %d sessions means NO beta, never 1.0"
                    % (BETA_SESSIONS, BETA_MIN_SESSIONS)}


async def _rate() -> (float, str):
    """The 3-month Treasury as the risk-free rate, from B3's own FRED read.

    Reused rather than re-fetched, and when FRED cannot answer the grid is NOT computed with a
    guessed rate: a made-up r would silently shift every option price.
    """
    from integrations import fred_series as fred

    pts = await asyncio.to_thread(fred.fetch_series, "DGS3MO")
    as_of, level = fred.latest(pts)
    if level is None:
        raise RuntimeError("no DGS3MO observation: the risk-free rate is unavailable")
    return level / 100.0, "FRED DGS3MO %.2f%% as of %s" % (level, as_of)


@router.get("")
async def get_book_reality(verify: int = Query(0),
                           _: str = Depends(require_api_key)) -> Dict[str, Any]:
    if not B7_ENABLED and not verify:
        return {
            "enabled": False,
            "note": ("B7 ships with its flag OFF (R-IV.1239(e)4). Nothing is computed on this "
                     "call. The flag flips only after QUERY recomputes three rows "
                     "independently and SPINE rules on that check (R-IV.1239(e)5-6)."),
            "verification_hint": ("?verify=1 computes the grid for QUERY's check and labels it "
                                  "NOT ON SCREEN"),
            "label": br.MODEL_LABEL,
            "vol_mode": br.VOL_MODE,
        }
    try:
        from database.postgres_client import get_postgres_client

        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            # B7's OWN query (R-IV.1246(f)), not Position Watch's.
            book = [dict(r) for r in await conn.fetch(B7_SQL)]
        tickers = sorted({str(p.get("ticker", "")).upper() for p in book if p.get("ticker")})
        r, r_basis = await _rate()
        md = await asyncio.to_thread(_betas_and_spots, tickers)
        g = br.grid(book, spots=md["spots"], betas=md["betas"], r=r)
        g.update({
            "enabled": bool(B7_ENABLED),
            "on_screen": bool(B7_ENABLED),
            "banner": None if B7_ENABLED else (
                "NOT ON SCREEN — a verification read for QUERY's three-row check under "
                "R-IV.1239(e)5. The flag is OFF."),
            "rate": r_basis,
            "beta_basis": md["note"],
            "positions_read": len(book),
            "as_of": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "field_origin": {"rows": "derived", "worst": "derived", "not_modelled": "derived"},
        })
        return g
    except Exception as exc:                                        # noqa: BLE001
        logger.error("[book-reality] failed: %s", type(exc).__name__)
        return {"enabled": bool(B7_ENABLED), "error": "%s" % type(exc).__name__,
                "rows": [], "note": "the Book Reality computation failed; no figure is served"}
