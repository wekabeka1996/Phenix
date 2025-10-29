"""
vFoundation Core Module

Provides core FSM functionality for event-driven applications.
"""

from .fsm_core import FSMCore
from .protocol import Message

__all__ = ["FSMCore", "Message"]