"""
Message v1↔v2 Compatibility Layer — Phase 16.2.

Provides transparent migration between Message v=1 (current runtime)
and v=2 (Constitution §5.2 target). This module is a prerequisite
for Phase 14.3 (message envelope refactor).

Per ADR-003:
- v=1 messages remain fully functional (backward compat)
- v=2 messages have stricter contract enforcement
- Trading-specific top-level fields migrate to pld in v=2
"""
from __future__ import annotations

import warnings
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from vfoundation.core.protocol import Message

# Trading-specific fields that belong in pld, not at top-level.
# These are tracked per ADR-003 and Constitution §5.2.
TRADING_ENVELOPE_FIELDS = (
    "oco_group_id",
    "parent_client_order_id",
    "link_ack_id",
    "link_fill_id",
)


def upgrade_v1_to_v2(msg: "Message") -> "Message":
    """
    Upgrade a v=1 Message to v=2 format.

    Changes:
    - Sets v=2
    - Ensures span_id is populated (defaults to rid if missing)
    - Copies trading-specific top-level fields into pld

    v=2 messages are returned unchanged.
    Emits DeprecationWarning for v=1 messages.

    Args:
        msg: Message instance to upgrade.

    Returns:
        New Message instance with v=2 fields.
    """
    if msg.v >= 2:
        return msg

    warnings.warn(
        f"Message v={msg.v} is deprecated. Use v=2. "
        f"See ADR-003-message-protocol-drift.md",
        DeprecationWarning,
        stacklevel=2,
    )

    update: dict = {"v": 2}

    # Ensure span_id is populated
    if not msg.span_id:
        update["span_id"] = msg.rid

    # Migrate trading-specific fields into pld
    pld_additions: dict = {}
    for field_name in TRADING_ENVELOPE_FIELDS:
        value = getattr(msg, field_name, None)
        if value is not None and field_name not in msg.pld:
            pld_additions[field_name] = value

    if pld_additions:
        merged_pld = {**msg.pld, **pld_additions}
        update["pld"] = merged_pld

    return msg.model_copy(update=update)


def validate_v2_contract(msg: "Message") -> List[str]:
    """
    Validate that a message meets Constitution §5.2 v=2 requirements.

    Returns list of issues found. Empty list = valid.
    """
    issues: List[str] = []

    if msg.v < 2:
        issues.append(f"v={msg.v}, expected >=2")

    if not msg.why:
        issues.append("why is required for v=2 messages")

    if not msg.rid:
        issues.append("rid is required")

    # Check that trading-specific fields are NOT at top-level in v=2
    for field_name in TRADING_ENVELOPE_FIELDS:
        value = getattr(msg, field_name, None)
        if value is not None:
            issues.append(
                f"Trading field '{field_name}' should be in pld, not at top-level"
            )

    return issues


def is_backward_compatible(v1_msg: "Message", v2_msg: "Message") -> bool:
    """
    Check if a v=2 message preserves v=1 semantics.

    Verifies that core routing fields (rid, op, verb, src, dst) and
    payload content are preserved during upgrade.
    """
    return all([
        v1_msg.rid == v2_msg.rid,
        v1_msg.op == v2_msg.op,
        v1_msg.verb == v2_msg.verb,
        v1_msg.src == v2_msg.src,
        v1_msg.dst == v2_msg.dst,
        # pld must be superset (may gain fields from top-level migration)
        all(v1_msg.pld.get(k) == v for k, v in v1_msg.pld.items()),
    ])
