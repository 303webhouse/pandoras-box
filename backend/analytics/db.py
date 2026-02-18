"""
Analytics data-access layer entrypoint.
"""

from __future__ import annotations

from database.postgres_client import get_postgres_client

__all__ = ["get_postgres_client"]

