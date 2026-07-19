"""
Section 4.3 production verification: dual-close race against Railway prod.
"""
import asyncio
import sys
import os
import httpx
import asyncpg

BASE_URL = "https://pandoras-box-production.up.railway.app"
API_KEY = "rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk"
DB_HOST = "trolley.proxy.rlwy.net"
DB_PORT = 25012
DB_NAME = "railway"
DB_USER = "postgres"
DB_PASSWORD = os.getenv("DB_PASSWORD", "sioMAUjhdgNYWwZMZbkbcSyaAcwdJMty")


async def api(client, method, path, **kwargs):
    resp = await getattr(client, method)(
        f"{BASE_URL}{path}",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        timeout=30.0,
        **kwargs,
    )
    try:
        return resp.status_code, resp.json()
    except Exception:
        return resp.status_code, {"raw": resp.text}


async def main():
    print("=== Section 4.3: Production dual-close verification ===")

    async with httpx.AsyncClient() as client:
        # 1. Create synthetic test position
        print("\n1. Creating synthetic test position on Railway prod...")
        code, body = await api(client, "post", "/api/v2/positions", json={
            "ticker": "TEST_C1",
            "direction": "LONG",
            "asset_type": "EQUITY",
            "structure": "stock",
            "entry_price": 50.00,
            "quantity": 1,
            "account": "ROBINHOOD",
            "notes": "PROD_C1_VERIFICATION - safe to delete",
        })
        if code not in (200, 201):
            print(f"  FAIL: create returned HTTP {code}: {body}")
            sys.exit(1)
        position_id = body.get("position", {}).get("position_id") or body.get("position_id")
        print(f"  Created: {position_id}")

        # 2. Dual concurrent close
        print("\n2. Firing two concurrent close requests...")
        results = await asyncio.gather(
            api(client, "post", f"/api/v2/positions/{position_id}/close",
                json={"exit_price": 55.00, "close_reason": "c1_prod_test"}),
            api(client, "post", f"/api/v2/positions/{position_id}/close",
                json={"exit_price": 55.00, "close_reason": "c1_prod_test"}),
            return_exceptions=True,
        )

        statuses = [r[0] if isinstance(r, tuple) else -1 for r in results]
        bodies   = [r[1] if isinstance(r, tuple) else str(r) for r in results]
        for i, (s, b) in enumerate(zip(statuses, bodies)):
            print(f"  Request {i+1}: HTTP {s}  ->  {b}")

        count_200 = statuses.count(200)
        count_409 = statuses.count(409)
        print(f"\n  200s: {count_200}  |  409s: {count_409}")

        # 3. GET /close-attempts via API
        print("\n3. GET /close-attempts...")
        code2, attempts = await api(client, "get", f"/api/v2/positions/{position_id}/close-attempts")
        print(f"  HTTP {code2}: {attempts}")

    # 4. DB verification
    print("\n4. DB verification...")
    conn = await asyncpg.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME,
        user=DB_USER, password=DB_PASSWORD,
    )
    try:
        pos_rows = await conn.fetch(
            "SELECT position_id, status, exit_price, trade_outcome FROM unified_positions WHERE position_id = $1",
            position_id,
        )
        attempt_rows = await conn.fetch(
            "SELECT id, status, error_message FROM close_attempts WHERE position_id = $1 ORDER BY id",
            position_id,
        )
    finally:
        await conn.close()

    print(f"  unified_positions: {[dict(r) for r in pos_rows]}")
    print(f"  close_attempts:    {[dict(r) for r in attempt_rows]}")

    # 5. Pass/fail
    print("\n5. Result:")
    closed_rows = [r for r in pos_rows if r["status"] == "CLOSED"]
    passed = (
        count_200 == 1 and
        count_409 == 1 and
        len(closed_rows) == 1 and
        len(attempt_rows) == 2
    )
    if passed:
        print("  PASS -- production double-close correctly blocked")
    else:
        print("  FAIL:")
        if count_200 != 1: print(f"    want 1x200 got {count_200}")
        if count_409 != 1: print(f"    want 1x409 got {count_409}")
        if len(closed_rows) != 1: print(f"    want 1 CLOSED got {len(closed_rows)}")
        if len(attempt_rows) != 2: print(f"    want 2 close_attempts got {len(attempt_rows)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
