"""Who wrote into the regime engine, and when (R-IV.442(b)).

A factor POST is a WRITE INTO THE COMPOSITE. It changes a score the engine reads, the
composite recomputes on the spot, and until now it left no trace: the reading itself records a
`source` string the caller chose, which answers "what does this claim to be" and not "who sent
it". Those are different questions, and only the second one can be checked.

So every accepted write gets a line: the endpoint, the factor, the caller as far as the
request reveals it, the auth mode it came in under, and the time. Rejected writes are not
audited here -- they never reached the engine -- and the line is written AFTER acceptance, so
the audit cannot become a way to make a failed write look real.

ONE RULE THIS MODULE KEEPS ABSOLUTELY: it never stores or logs the credential. FastAPI's auth
dependency returns the API KEY ITSELF on the header path, so a caller identity built by
passing that value through would write a live secret into a database table and into every log
line quoting it. `auth_mode()` maps it to a word -- api_key / session / none -- and the value
goes no further.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

SESSION = "session"
API_KEY = "api_key"
NONE = "none"


def auth_mode(dependency_result: Any) -> str:
    """The WORD for how a request authenticated. Never the credential."""
    if dependency_result == SESSION:
        return SESSION
    return API_KEY if dependency_result else NONE


def caller_of(request) -> str:
    """The caller as far as the request reveals it, in one short string.

    Not an identity claim. A client address and a user agent are what a server actually
    knows about an unnamed caller, and naming them is the difference between "something
    wrote this" and "this wrote it".
    """
    try:
        host = getattr(getattr(request, "client", None), "host", None) or "unknown-host"
        agent = (request.headers.get("user-agent") or "unknown-agent")[:120]
        named = request.headers.get("x-caller")
        return f"{named}@{host} ({agent})" if named else f"{host} ({agent})"
    except Exception:
        return "unreadable-request"


async def record_factor_write(endpoint: str, *, factor_id: Optional[str] = None,
                              caller: str = "unknown", auth: str = NONE,
                              source: Optional[str] = None,
                              score: Optional[float] = None) -> None:
    """Write the audit line. Never raises -- an audit must not fail the write it observes."""
    try:
        from database.postgres_client import get_postgres_client
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO factor_write_audit
                       (endpoint, factor_id, caller, auth_mode, claimed_source, score)
                   VALUES ($1, $2, $3, $4, $5, $6)""",
                endpoint, factor_id, caller, auth, source,
                float(score) if score is not None else None)
    except Exception as exc:
        # The log line is the fallback record: losing the row must not lose the fact.
        logger.warning("factor write audit not persisted (%s) — endpoint=%s factor=%s "
                       "caller=%s auth=%s", type(exc).__name__, endpoint, factor_id,
                       caller, auth)
    else:
        logger.info("factor write accepted — endpoint=%s factor=%s caller=%s auth=%s "
                    "claimed_source=%s", endpoint, factor_id, caller, auth, source)
