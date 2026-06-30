"""Read-only, bounded Aurora-to-agent context bridge."""

from .contracts import AgentFeedPacket
from .reducer import AgentFeedReducer

__all__ = ["AgentFeedPacket", "AgentFeedReducer"]
