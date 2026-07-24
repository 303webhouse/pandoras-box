#!/usr/bin/env python3
"""AEGIS rotation rejection-test helper (S3 verification).

Reads ONE connection string from stdin, attempts a short-timeout connect, and
prints EXACTLY one token: `ACCEPTED` or `REJECTED (<reason-class>)`.

Prime directive: the connection string and any secret it carries are NEVER
echoed. The raw driver error is never printed either (it can contain host/user);
only a coarse reason CLASS derived from it is emitted.

Usage (the DSN is piped in; it never appears on a command line or on screen):
    printf '%s' "$DSN" | python scripts/aegis_conn_test.py
    git show <blob>:scripts/reconcile_rh.py | grep -oE 'postgres[^"]+' | python scripts/aegis_conn_test.py
"""
import sys


def main() -> int:
    dsn = sys.stdin.readline().strip()
    if not dsn:
        print("REJECTED (no-input)")
        return 2
    try:
        import psycopg2
    except Exception:
        print("REJECTED (psycopg2-missing)")
        return 3
    try:
        conn = psycopg2.connect(dsn, connect_timeout=8)
        conn.close()
        print("ACCEPTED")
        return 0
    except Exception as exc:  # noqa: BLE001 - we intentionally classify, never surface
        msg = str(exc).lower()
        if "password authentication failed" in msg or "authentication" in msg:
            reason = "auth-failed"
        elif "role" in msg and "does not exist" in msg:
            reason = "no-such-role"
        elif "database" in msg and "does not exist" in msg:
            reason = "no-such-db"
        elif "timeout" in msg or "could not connect" in msg or "connection refused" in msg or "could not translate" in msg:
            reason = "unreachable"
        else:
            reason = type(exc).__name__
        print(f"REJECTED ({reason})")
        return 1


if __name__ == "__main__":
    sys.exit(main())
