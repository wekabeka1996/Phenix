"""
Intent Layer — QoS and prioritization based on Message.intent.

Constitution v2.2 §7:
    Intent Layer manages QoS / prioritization.

The intent field classifies messages by urgency:
    COMMAND      → highest priority (trade execution)
    DECLARATION  → high (decisions, DEC:OPEN)
    PROPOSAL     → medium (trade intents)
    OBSERVATION  → normal (EVT:BAR_CLOSED, feature data)
    INQUIRY      → lowest (health checks, read-only)

Usage:
    layer = IntentLayer()
    priority = layer.priority(msg)  # int, lower = higher priority
    should_process = layer.should_process(msg, degraded=True)
    ttl = layer.ttl_for(msg)
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from .protocol import IntentType, Message

LOG = logging.getLogger(__name__)

# Priority mapping: lower value = higher priority
# Constitution v2.2: INQUIRY can be dropped under degradation
INTENT_PRIORITY: Dict[str, int] = {
    "COMMAND": 0,
    "DECLARATION": 1,
    "PROPOSAL": 2,
    "OBSERVATION": 3,
    "INQUIRY": 4,
}

# TTL profiles per intent (Constitution v2.2 §6)
INTENT_TTL_MS: Dict[str, int] = {
    "COMMAND": 200,       # critical/fast
    "DECLARATION": 200,   # critical/fast
    "PROPOSAL": 2000,     # normal
    "OBSERVATION": 2000,  # normal
    "INQUIRY": 10000,     # ml_slow/background
}

# Intents to drop under degradation (Constitution §8.4)
DEGRADATION_DROP: frozenset[str] = frozenset({"INQUIRY"})


class IntentLayer:
    """
    QoS layer that classifies and filters messages by intent.

    Thread-safe: stateless, all methods are pure functions.
    """

    def priority(self, msg: Message) -> int:
        """
        Return priority for a message (lower = higher priority).

        Messages without intent default to OBSERVATION priority.
        """
        intent = msg.intent or self._infer_intent(msg)
        return INTENT_PRIORITY.get(intent, 3)

    def should_process(self, msg: Message, *, degraded: bool = False) -> bool:
        """
        Determine if a message should be processed.

        Args:
            msg: The message to evaluate
            degraded: If True, system is in degraded/LOW_RISK mode → drop low-priority

        Returns:
            True if the message should be processed.
        """
        if not degraded:
            return True

        intent = msg.intent or self._infer_intent(msg)
        if intent in DEGRADATION_DROP:
            LOG.info(
                "IntentLayer: dropping %s:%s (intent=%s) — system degraded",
                msg.op, msg.verb, intent,
            )
            return False
        return True

    def ttl_for(self, msg: Message) -> int:
        """
        Return recommended TTL (ms) for a message based on its intent.

        Uses message's own intent if set; otherwise infers from op.
        """
        intent = msg.intent or self._infer_intent(msg)
        return INTENT_TTL_MS.get(intent, 2000)

    def classify(self, msg: Message) -> str:
        """
        Return the effective intent string for a message.
        """
        return msg.intent or self._infer_intent(msg)

    @staticmethod
    def _infer_intent(msg: Message) -> str:
        """
        Infer intent from op when intent field is not explicitly set.

        Mapping:
            CMD → COMMAND
            DEC → DECLARATION
            ASK → INQUIRY
            EVT → OBSERVATION
            UPD → OBSERVATION
            ERR → OBSERVATION
        """
        op_to_intent: Dict[str, str] = {
            "CMD": "COMMAND",
            "DEC": "DECLARATION",
            "ASK": "INQUIRY",
            "EVT": "OBSERVATION",
            "UPD": "OBSERVATION",
            "ERR": "OBSERVATION",
        }
        return op_to_intent.get(msg.op, "OBSERVATION")
