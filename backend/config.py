"""
ZEUS configuration flags.
"""
import os

# ZEUS Phase 3: Tiered Feed Routing
# When True, signals are routed by feed_tier in /main-feed and Discord.
# Set ZEUS_TIERED_ROUTING=false to roll back to pre-ZEUS flat feed behavior.
ZEUS_TIERED_ROUTING_ENABLED = os.getenv("ZEUS_TIERED_ROUTING", "true").lower() == "true"
