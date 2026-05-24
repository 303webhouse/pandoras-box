"""
Phase 0 Investigation 2 — standalone OAuth-storage chain reproducer.

Reconstructs the exact storage chain Phase C.1-rev2 used:

    Redis.from_url(REDIS_URL,
                   health_check_interval=30,
                   retry_on_timeout=True,
                   socket_keepalive=True,
                   decode_responses=False)
      -> RedisStore(client=...)
        -> FernetEncryptionWrapper(raise_on_decryption_error=False)

Goal: isolate which layer caused rev2's write-read inconsistency
(POST /register returned 201 with client_id; GET /authorize 1 second
later said the same client_id was unregistered). With single-worker
confirmed (Phase 0 Investigation 1), H1 is ruled out — so the failure
must be at the storage chain itself: H2 (RedisStore async ordering),
H3 (Fernet wrapper write-side bug), or H4 (`client=` vs `url=` internal
difference).

Three scenarios, run fast-first:
  1. Immediate put-then-get (microseconds apart — the rev2 case exactly)
  3. Two concurrent put/get cycles via asyncio.gather (async-ordering test)
  2. Put -> 10-min idle -> get (Upstash idle-drop test for the keepalive cfg)

Output: PASS/FAIL per scenario + elapsed milliseconds. No URL, no values,
no key material in any output.

This script uses a script-local Fernet key — it does NOT touch the
production OAuth Fernet key or the production OAuth collection. Writes
go to a separate `phase0-repro` collection.

Refs: Brief D rev2 § 5b. Throwaway after Phase 0.

Run:
    railway run python scripts/repro_oauth_storage.py
    railway run python scripts/repro_oauth_storage.py --skip-idle  # fast subset

Exit code: 0 if all run scenarios pass, 1 if any fail or REDIS_URL missing.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time

from cryptography.fernet import Fernet
from key_value.aio.stores.redis import RedisStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper
from redis.asyncio import Redis

COLLECTION = "phase0-repro"
KEY_BASE = "test-write-read"
VALUE = {"foo": "bar"}
IDLE_SECONDS = 600  # 10 minutes — matches rev1's empirical failure threshold


def _build_chain() -> FernetEncryptionWrapper:
    """Build the rev2 storage chain. Reads REDIS_URL from env; never logs it."""
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        print("FAIL: REDIS_URL not set. Cannot proceed.", file=sys.stderr)
        sys.exit(1)

    client = Redis.from_url(
        redis_url,
        health_check_interval=30,
        retry_on_timeout=True,
        socket_keepalive=True,
        decode_responses=False,
    )
    store = RedisStore(client=client, default_collection=COLLECTION)

    # Deterministic-for-this-process Fernet key. Generated locally; not
    # related to and does not touch the production OAuth Fernet key.
    fernet = Fernet(Fernet.generate_key())
    wrapped = FernetEncryptionWrapper(
        store, fernet=fernet, raise_on_decryption_error=False
    )
    return wrapped


async def _safe_put_get(chain, key: str) -> tuple[bool, str]:
    """Put VALUE under `key`, get it back. Returns (matches, error_label)."""
    try:
        await chain.put(key=key, value=VALUE)
    except Exception as exc:
        return False, f"put raised {type(exc).__name__}"
    try:
        got = await chain.get(key=key)
    except Exception as exc:
        return False, f"get raised {type(exc).__name__}"
    if got is None:
        return False, "get returned None (key absent)"
    if got != VALUE:
        return False, "value mismatch"
    return True, ""


async def scenario_1_immediate(chain) -> tuple[bool, float, str]:
    start = time.monotonic()
    ok, err = await _safe_put_get(chain, f"{KEY_BASE}-1")
    return ok, (time.monotonic() - start) * 1000, err


async def scenario_3_concurrent(chain) -> tuple[bool, float, str]:
    start = time.monotonic()
    try:
        results = await asyncio.gather(
            _safe_put_get(chain, f"{KEY_BASE}-3a"),
            _safe_put_get(chain, f"{KEY_BASE}-3b"),
        )
    except Exception as exc:
        return False, (time.monotonic() - start) * 1000, f"gather raised {type(exc).__name__}"
    elapsed = (time.monotonic() - start) * 1000
    failures = [err for ok, err in results if not ok]
    if failures:
        return False, elapsed, "; ".join(failures)
    return True, elapsed, ""


async def scenario_2_idle(chain) -> tuple[bool, float, str]:
    key = f"{KEY_BASE}-2"
    start = time.monotonic()
    try:
        await chain.put(key=key, value=VALUE)
    except Exception as exc:
        return False, (time.monotonic() - start) * 1000, f"put raised {type(exc).__name__}"
    await asyncio.sleep(IDLE_SECONDS)
    try:
        got = await chain.get(key=key)
    except Exception as exc:
        return False, (time.monotonic() - start) * 1000, f"get raised {type(exc).__name__}"
    elapsed = (time.monotonic() - start) * 1000
    if got is None:
        return False, elapsed, "get returned None (key absent after idle)"
    if got != VALUE:
        return False, elapsed, "value mismatch after idle"
    return True, elapsed, ""


def _report(name: str, ok: bool, elapsed_ms: float, err: str) -> None:
    verdict = "PASS" if ok else "FAIL"
    suffix = f" ({err})" if err else ""
    print(f"{name}: {verdict} ({elapsed_ms:.1f} ms){suffix}")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 0 Investigation 2 reproducer")
    parser.add_argument(
        "--skip-idle",
        action="store_true",
        help=f"Skip scenario 2 (the {IDLE_SECONDS}-second idle test).",
    )
    args = parser.parse_args()

    chain = _build_chain()

    # Fast scenarios first so failures surface quickly.
    ok1, ms1, err1 = await scenario_1_immediate(chain)
    _report("Scenario 1 (immediate put-then-get)", ok1, ms1, err1)

    ok3, ms3, err3 = await scenario_3_concurrent(chain)
    _report("Scenario 3 (two concurrent put/get cycles)", ok3, ms3, err3)

    if args.skip_idle:
        print(f"Scenario 2 ({IDLE_SECONDS}s idle): SKIPPED (--skip-idle)")
        return 0 if (ok1 and ok3) else 1

    ok2, ms2, err2 = await scenario_2_idle(chain)
    _report(f"Scenario 2 (put -> {IDLE_SECONDS}s idle -> get)", ok2, ms2, err2)

    return 0 if (ok1 and ok3 and ok2) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
