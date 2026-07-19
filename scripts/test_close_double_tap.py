"""
Section 4.1 — Dual-close race test for the TOCTOU-safe close handler.

Sends two concurrent close requests against a live endpoint and verifies:
  - exactly one 200 (close accepted)
  - exactly one 409 (lock contention blocked)
  - exactly one row in unified_positions with status='CLOSED'
  - exactly two rows in close_attempts for the position

Usage:
    DB_HOST=trolley.proxy.rlwy.net DB_PORT=25012 DB_NAME=railway \
    DB_USER=postgres DB_PASSWORD=<pw> \
    python scripts/test_close_double_tap.py <base_url> <api_key> <position_id> <exit_price>

Example (from repo root with railway run):
    python scripts/test_close_double_tap.py \
        http://127.0.0.1:8080 rLl-7i2... POS_SOXS_20260428_065253 10.50
"""
import asyncio
import sys
import os
import httpx
import asyncpg


async def _fire_close(client: httpx.AsyncClient, url: str, api_key: str,
                      position_id: str, exit_price: float) -> tuple[int, dict]:
    resp = await client.post(
        f"{url}/api/v2/positions/{position_id}/close",
        json={"exit_price": exit_price, "close_reason": "test_double_tap"},
        headers={"X-API-Key": api_key},
        timeout=30.0,
    )
    try:
        body = resp.json()
    except Exception:
        body = {"raw": resp.text}
    return resp.status_code, body


async def main():
    if len(sys.argv) < 5:
        print("Usage: test_close_double_tap.py <base_url> <api_key> <position_id> <exit_price>")
        sys.exit(1)

    base_url, api_key, position_id, exit_price = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])

    db_host = os.getenv("DB_HOST") or "trolley.proxy.rlwy.net"
    db_port = int(os.getenv("DB_PORT") or 25012)
    db_name = os.getenv("DB_NAME") or "railway"
    db_user = os.getenv("DB_USER") or "postgres"
    db_password = os.getenv("DB_PASSWORD") or ""

    print(f"\n=== Section 4.1: dual-close race test ===")
    print(f"Target:     {base_url}/api/v2/positions/{position_id}/close")
    print(f"Exit price: {exit_price}")
    print(f"DB:         {db_host}:{db_port}/{db_name}\n")

    async with httpx.AsyncClient() as client:
        # Fire both requests concurrently
        results = await asyncio.gather(
            _fire_close(client, base_url, api_key, position_id, exit_price),
            _fire_close(client, base_url, api_key, position_id, exit_price),
            return_exceptions=True,
        )

    statuses = [r[0] if isinstance(r, tuple) else -1 for r in results]
    bodies   = [r[1] if isinstance(r, tuple) else str(r) for r in results]

    print("── HTTP results ─────────────────────────────────────────")
    for i, (s, b) in enumerate(zip(statuses, bodies)):
        print(f"  Request {i+1}: HTTP {s}  →  {b}")

    count_200 = statuses.count(200)
    count_409 = statuses.count(409)
    print(f"\n  200s: {count_200}  |  409s: {count_409}")

    # DB verification
    conn = await asyncpg.connect(
        host=db_host, port=db_port, database=db_name,
        user=db_user, password=db_password,
    )
    try:
        pos_rows = await conn.fetch(
            "SELECT position_id, status FROM unified_positions WHERE position_id = $1",
            position_id,
        )
        attempt_rows = await conn.fetch(
            "SELECT id, status, exit_price FROM close_attempts WHERE position_id = $1 ORDER BY attempted_at",
            position_id,
        )
    finally:
        await conn.close()

    print("\n── DB verification ──────────────────────────────────────")
    print(f"  unified_positions rows: {len(pos_rows)}")
    for r in pos_rows:
        print(f"    {dict(r)}")
    print(f"  close_attempts rows: {len(attempt_rows)}")
    for r in attempt_rows:
        print(f"    {dict(r)}")

    # Pass/fail
    print("\n── Test result ──────────────────────────────────────────")
    closed_rows  = [r for r in pos_rows if r["status"] == "CLOSED"]
    passed = (
        count_200 == 1 and
        count_409 == 1 and
        len(closed_rows) == 1 and
        len(attempt_rows) == 2
    )
    if passed:
        print("  PASS — double-close correctly blocked")
    else:
        print("  FAIL — unexpected state:")
        if count_200 != 1: print(f"    expected 1 x 200, got {count_200}")
        if count_409 != 1: print(f"    expected 1 x 409, got {count_409}")
        if len(closed_rows) != 1: print(f"    expected 1 CLOSED row, got {len(closed_rows)}")
        if len(attempt_rows) != 2: print(f"    expected 2 close_attempts rows, got {len(attempt_rows)}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
