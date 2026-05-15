"""Read-only namespace.

Every symbol re-exported here is verified to be a read-only operation.
The MCP module imports ONLY from this namespace; the lint check at
scripts/lint_mcp_imports.py fails the build if backend/mcp/* imports any
module outside backend.services.read_only that has write capability.

Adding a new re-export: confirm the source function does not mutate any
storage (no INSERT/UPDATE/DELETE in SQL, no Redis SET/DEL except
opportunistic caching of its own read result), then add it here AND to
the lint script's allowlist.
"""
