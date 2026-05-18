"""Test fixtures for the MCP module.

The MCP module reads MCP_BEARER_TOKEN at request time, never at import,
so tests can set/unset it freely. Tool tests mock the read_only namespace
directly — no live Redis or Postgres needed.
"""

import os
import sys
from pathlib import Path

import pytest

# Add backend/ to sys.path so the MCP package imports resolve the same way
# they do under uvicorn (Procfile cd's into backend/ before launch).
_BACKEND = Path(__file__).resolve().parent.parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


@pytest.fixture(autouse=True)
def _set_mcp_token(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "test-token-abc123")
