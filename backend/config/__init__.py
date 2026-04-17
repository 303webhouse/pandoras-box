"""Shared backend configuration helpers."""
import os

# ZEUS Phase 3: Tiered Feed Routing
# Set ZEUS_TIERED_ROUTING=false to roll back to pre-ZEUS flat feed behavior.
ZEUS_TIERED_ROUTING_ENABLED = os.getenv("ZEUS_TIERED_ROUTING", "true").lower() == "true"
