"""
Binance Futures Proxy
=====================
Lightweight FastAPI app to run on a VPS in a non-geo-restricted region.
Forwards requests from Railway → this proxy → fapi.binance.com.

Usage:
  pip install fastapi uvicorn httpx
  uvicorn binance_proxy:app --host 0.0.0.0 --port 8090

Then set on Railway:
  BINANCE_PROXY_URL=http://<vps-ip>:8090

Systemd unit example (save as /etc/systemd/system/binance-proxy.service):
  [Unit]
  Description=Binance Futures Proxy
  After=network.target

  [Service]
  ExecStart=/usr/bin/python3 -m uvicorn binance_proxy:app --host 0.0.0.0 --port 8090
  WorkingDirectory=/opt/binance-proxy
  Restart=always
  RestartSec=5

  [Install]
  WantedBy=multi-user.target
"""

import httpx
import logging
from fastapi import FastAPI, Request, Response

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Binance Futures Proxy", docs_url=None, redoc_url=None)

BINANCE_FUTURES_BASE = "https://fapi.binance.com"

# Optional: restrict which Railway IP can use this proxy.
# Leave empty to allow all (VPS is not public-facing beyond this port).
ALLOWED_IPS: list[str] = []


@app.get("/fapi/v1/{path:path}")
async def proxy_binance(path: str, request: Request):
    """Forward GET /fapi/v1/<path>?<params> to fapi.binance.com"""
    if ALLOWED_IPS and request.client.host not in ALLOWED_IPS:
        return Response(status_code=403, content="Forbidden")

    target_url = f"{BINANCE_FUTURES_BASE}/fapi/v1/{path}"
    params = dict(request.query_params)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(target_url, params=params)
            logger.info("Proxy: %s %s -> %s", request.method, path, resp.status_code)
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=resp.headers.get("content-type", "application/json"),
            )
    except Exception as exc:
        logger.error("Proxy error for %s: %s", path, exc)
        return Response(status_code=502, content=str(exc))


@app.get("/health")
async def health():
    return {"status": "ok", "proxy_target": BINANCE_FUTURES_BASE}
