"""FastAPI server for the Stable Market Board.

Run with:  python -m stable.server
Opens on:  http://localhost:8000
"""

from __future__ import annotations

import math
import json
import asyncio
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import db, scoring, settings as settings_mod, ingest, metrics


app = FastAPI(title="Stable Market Board")

FRONTEND_DIR = Path(__file__).parent / "frontend"

# Track refresh state so concurrent clicks don't trigger overlapping runs
_refresh_state = {
    "in_progress": False,
    "last_started": None,
    "last_completed": None,
    "last_error": None,
    "last_summary": None,
}


def clean_floats(obj):
    """Recursively replace NaN/inf floats with None for JSON serialization."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: clean_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean_floats(v) for v in obj]
    if isinstance(obj, (pd.Timestamp,)):
        return obj.strftime("%Y-%m-%d")
    return obj


@app.get("/api/regime")
def get_regime():
    return JSONResponse(clean_floats(scoring.get_regime_read()))


@app.get("/api/themes")
def get_themes():
    df = scoring.compute_theme_scores()
    if df.empty:
        return JSONResponse({"themes": [], "as_of": None})
    as_of = df["date"].iloc[0].strftime("%Y-%m-%d") if "date" in df.columns else None
    df = df.drop(columns=["date"], errors="ignore")
    return JSONResponse(clean_floats({
        "as_of": as_of,
        "themes": df.to_dict("records"),
    }))


@app.get("/api/themes/{theme_name}")
def get_theme(theme_name: str):
    df = scoring.get_theme_constituents(theme_name)
    return JSONResponse(clean_floats({
        "theme": theme_name,
        "constituents": df.to_dict("records"),
    }))


@app.get("/api/extension")
def get_extension():
    return JSONResponse(clean_floats(scoring.get_extension_lists()))


@app.get("/api/etf_pulse")
def etf_pulse():
    return JSONResponse(clean_floats(scoring.get_etf_pulse()))


@app.get("/api/vol_regime")
def vol_regime():
    return JSONResponse(clean_floats(scoring.get_vol_regime()))


@app.get("/api/theme_rotation")
def theme_rotation():
    return JSONResponse(clean_floats(scoring.get_theme_rotation(lookback_days=5)))


@app.get("/api/breadth_series")
def breadth_series(lookback: str = "3M", theme: str | None = None, tiers: str = "Core,Active"):
    """Time series of breadth metrics for the Breadth tab.

    Query params:
      - lookback: "1M" | "3M" | "6M" | "1Y" (default 3M)
      - theme: optional theme name to filter; omit or "All" for all themes ex-benchmark
      - tiers: comma-separated tier names (default "Core,Active")
    """
    tier_tuple = tuple(t.strip() for t in tiers.split(",") if t.strip())
    if not tier_tuple:
        tier_tuple = ("Core", "Active")
    payload = scoring.get_breadth_series(
        lookback=lookback,
        theme=None if (theme is None or theme == "All") else theme,
        tiers=tier_tuple,
    )
    return JSONResponse(clean_floats(payload))


@app.get("/api/momentum_scan")
def momentum_scan(
    min_dollar_vol: float = 100_000_000.0,
    above_mas: str = "20,50",
    tiers: str = "Core,Active",
    exclude_benchmark: bool = True,
    top_n: int = 25,
):
    """Momentum scanner: top-N tickers by 1M / 3M / 6M absolute momentum.

    Query params:
      - min_dollar_vol: minimum 20-day average dollar volume (default 100M)
      - above_mas: comma-separated MA periods the ticker must be above (default "20,50")
                   Use empty string for no MA filter
      - tiers: comma-separated tier names (default "Core,Active")
      - exclude_benchmark: exclude Benchmark theme ETFs (default True)
      - top_n: how many to return per window (default 25)
    """
    above_mas_tuple = tuple(
        int(m.strip()) for m in above_mas.split(",") if m.strip().isdigit()
    )
    tier_tuple = tuple(t.strip() for t in tiers.split(",") if t.strip())
    if not tier_tuple:
        tier_tuple = ("Core", "Active")
    payload = scoring.get_momentum_scan(
        min_dollar_vol=float(min_dollar_vol),
        above_mas=above_mas_tuple,
        tiers=tier_tuple,
        exclude_benchmark=bool(exclude_benchmark),
        top_n=int(top_n),
    )
    return JSONResponse(clean_floats(payload))


@app.get("/api/live_overlay")
def live_overlay():
    """Live intraday price overlay.

    Fetches a full-market snapshot from Polygon (15-min delayed on the Starter
    plan) and overlays current prices on the stored daily metrics. The heavy
    structural analysis stays anchored to the last daily close; this just adds
    a live price layer with live distances from the daily moving averages.
    """
    payload = scoring.get_live_overlay()
    return JSONResponse(clean_floats(payload))


@app.get("/api/health")
def health():
    with db.connect(read_only=True) as conn:
        latest = conn.execute("SELECT MAX(date) FROM metrics").fetchone()[0]
        n_tickers = conn.execute("SELECT COUNT(DISTINCT ticker) FROM metrics").fetchone()[0]
    # Include refresh status so the UI can show last-refreshed time
    return {
        "status": "ok",
        "latest_date": str(latest),
        "tickers": n_tickers,
        "refresh": {
            "in_progress": _refresh_state["in_progress"],
            "last_started": _refresh_state["last_started"],
            "last_completed": _refresh_state["last_completed"],
            "last_error": _refresh_state["last_error"],
        },
    }


def _run_refresh_sync() -> dict:
    """Synchronously run ingestion + metrics. Returns a summary dict.
    This is called in a thread executor by the refresh endpoint to avoid
    blocking the event loop.
    """
    ingest_summary = ingest.ingest(workers=10)
    metrics_summary = metrics.compute_metrics()
    return {
        "ingest": {
            "attempted": ingest_summary.get("tickers_attempted"),
            "updated": ingest_summary.get("tickers_with_new_data"),
            "skipped": ingest_summary.get("tickers_skipped_already_current"),
            "errors": ingest_summary.get("tickers_with_errors"),
        },
        "metrics": {
            "tickers": metrics_summary.get("tickers_processed"),
            "rows": metrics_summary.get("rows_written"),
        },
    }


@app.post("/api/refresh")
async def refresh_data():
    """Re-run ingestion + metrics in the background. Returns 202 if already running."""
    if _refresh_state["in_progress"]:
        return JSONResponse(
            {"status": "in_progress", "message": "Refresh already running"},
            status_code=202,
        )

    _refresh_state["in_progress"] = True
    _refresh_state["last_started"] = datetime.now().isoformat(timespec="seconds")
    _refresh_state["last_error"] = None
    _refresh_state["last_summary"] = None

    loop = asyncio.get_event_loop()
    try:
        summary = await loop.run_in_executor(None, _run_refresh_sync)
        _refresh_state["last_summary"] = summary
        _refresh_state["last_completed"] = datetime.now().isoformat(timespec="seconds")
        return JSONResponse({
            "status": "ok",
            "started": _refresh_state["last_started"],
            "completed": _refresh_state["last_completed"],
            "summary": summary,
        })
    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        _refresh_state["last_error"] = err
        _refresh_state["last_completed"] = datetime.now().isoformat(timespec="seconds")
        return JSONResponse(
            {
                "status": "error",
                "error": err,
                "trace": traceback.format_exc(),
            },
            status_code=500,
        )
    finally:
        _refresh_state["in_progress"] = False


@app.get("/api/settings")
def get_settings():
    """Return current settings + the set of allowed values for selectable fields."""
    return JSONResponse({
        "current": settings_mod.load(),
        "options": {
            "ma_periods_allowed": settings_mod.ALLOWED_MA_PERIODS,
        },
    })


@app.post("/api/settings")
async def post_settings(request: Request):
    """Save new settings. Returns the saved (validated) settings."""
    body = await request.json()
    saved = settings_mod.save(body)
    return JSONResponse({"saved": saved})


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")


# Serve the rest of the frontend assets
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="assets")


def main():
    import uvicorn
    print()
    print("=" * 60)
    print(" Stable Market Board")
    print(" Open in your browser: http://localhost:8000")
    print("=" * 60)
    print()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
