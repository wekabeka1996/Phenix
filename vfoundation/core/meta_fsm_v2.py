"""
MetaFSM v2 — Cross-domain coordinator powered by FSMv2 and EntropyMonitor.

Replaces the deprecated MetaFSM skeleton.

States: NORMAL → LOW_RISK → COOLDOWN → NORMAL (+ DEGRADED for partial outages)
Reacts to: EntropyMonitor spikes, topology drift, manual overrides.

Usage:
    from vfoundation.obs.entropy_monitor import EntropyMonitor
    from vfoundation.core.meta_fsm_v2 import MetaFSMv2

    entropy = EntropyMonitor(volume_threshold=100)
    meta = MetaFSMv2(entropy_monitor=entropy)

    # Called periodically (e.g., in a timer / after each bar):
    state, response = meta.tick()
    if response:
        bus.emit(f"{response.op}:{response.verb}", response.pld, response.why)
"""
from __future__ import annotations

import logging
import time
from typing import Optional, Tuple

from .fsm_v2 import FSMv2
from .protocol import Message

LOG = logging.getLogger(__name__)

# ── Default thresholds ──────────────────────────────────────────────

DEFAULT_COOLDOWN_SEC = 120  # 2 min cooldown before returning to NORMAL
DEFAULT_DEGRADED_TIMEOUT_SEC = 300  # 5 min in DEGRADED before forced recovery


class MetaFSMv2:
    """
    Cross-domain meta-coordinator.

    Integrates EntropyMonitor spike detection with formal FSMv2 state machine.

    States:
        NORMAL     — default, no anomalies
        LOW_RISK   — activated after entropy spike, restricts risky operations
        COOLDOWN   — transitional period after LOW_RISK, waiting for stabilization
        DEGRADED   — partial system outage / topology drift

    Transitions:
        NORMAL   + entropy spike    → LOW_RISK
        NORMAL   + topology drift   → DEGRADED
        LOW_RISK + stabilization    → COOLDOWN
        COOLDOWN + timeout elapsed  → NORMAL
        DEGRADED + recovery signal  → COOLDOWN

    Constitution v2.2 §8.4:
        - Activate safe policy (CMD:SWITCH_TO_LOW_RISK_MODE)
        - Freeze non-critical operations in LOW_RISK/DEGRADED
    """

    def __init__(
        self,
        entropy_monitor: Optional[object] = None,
        cooldown_sec: float = DEFAULT_COOLDOWN_SEC,
        degraded_timeout_sec: float = DEFAULT_DEGRADED_TIMEOUT_SEC,
    ) -> None:
        self._entropy = entropy_monitor
        self._cooldown_sec = cooldown_sec
        self._degraded_timeout_sec = degraded_timeout_sec

        # Track when we entered certain states
        self._state_entered_at: float = time.time()

        # Build the FSM
        self._fsm = FSMv2("meta")
        self._fsm.register_state("NORMAL", initial=True, on_enter=self._on_enter_normal)
        self._fsm.register_state("LOW_RISK", on_enter=self._on_enter_low_risk)
        self._fsm.register_state("COOLDOWN", on_enter=self._on_enter_cooldown)
        self._fsm.register_state("DEGRADED", on_enter=self._on_enter_degraded)

        # Transitions
        self._fsm.register_transition(
            "NORMAL", "EVT:ENTROPY_SPIKE", "LOW_RISK",
            action=self._action_switch_low_risk,
        )
        self._fsm.register_transition(
            "NORMAL", "EVT:TOPOLOGY_DRIFT_DETECTED", "DEGRADED",
            action=self._action_degraded,
        )
        self._fsm.register_transition(
            "LOW_RISK", "EVT:STABILIZED", "COOLDOWN",
        )
        self._fsm.register_transition(
            "COOLDOWN", "EVT:COOLDOWN_ELAPSED", "NORMAL",
            action=self._action_resume_normal,
        )
        self._fsm.register_transition(
            "DEGRADED", "EVT:RECOVERY_SIGNAL", "COOLDOWN",
        )
        # Allow direct recovery from DEGRADED to NORMAL via manual override
        self._fsm.register_transition(
            "DEGRADED", "CMD:FORCE_RECOVER", "NORMAL",
            action=self._action_resume_normal,
        )
        # Allow manual override from LOW_RISK to NORMAL
        self._fsm.register_transition(
            "LOW_RISK", "CMD:FORCE_RECOVER", "NORMAL",
            action=self._action_resume_normal,
        )

        # Initialize the meta key
        self._KEY = "meta_singleton"
        self._fsm.handle(
            self._KEY,
            Message(op="EVT", verb="INIT", src="meta", dst="meta", why="bootstrap"),
        )
        # Force to NORMAL immediately (INIT has no transition, so state stays NORMAL by default)

    # ── Public API ───────────────────────────────────────────────────

    @property
    def state(self) -> str:
        """Current meta-FSM state."""
        return self._fsm.get_state(self._KEY) or "NORMAL"

    @property
    def mode(self) -> str:
        """Alias for backward compatibility."""
        return self.state.lower()

    def tick(self) -> Tuple[str, Optional[Message]]:
        """
        Evaluate system state and fire transitions if needed.

        Call this periodically (e.g., after each bar, or on a timer).

        Returns:
            (current_state, optional_response_message)
        """
        now = time.time()
        current = self.state

        # Check entropy monitor
        if self._entropy and current == "NORMAL":
            spike, reason = self._entropy.detect_spike()  # type: ignore[union-attr]
            if spike:
                LOG.warning("MetaFSMv2: entropy spike detected — %s", reason)
                return self._fsm.handle(
                    self._KEY,
                    Message(
                        op="EVT", verb="ENTROPY_SPIKE",
                        src="entropy_monitor", dst="meta",
                        pld={"reason": reason},
                        why=f"entropy spike: {reason[:60]}",
                    ),
                )

        # Check stabilization in LOW_RISK (no more spikes)
        if self._entropy and current == "LOW_RISK":
            spike, _ = self._entropy.detect_spike()  # type: ignore[union-attr]
            if not spike:
                LOG.info("MetaFSMv2: entropy stabilized, entering COOLDOWN")
                return self._fsm.handle(
                    self._KEY,
                    Message(
                        op="EVT", verb="STABILIZED",
                        src="entropy_monitor", dst="meta",
                        why="no spike detected",
                    ),
                )

        # Check cooldown timeout
        if current == "COOLDOWN":
            elapsed = now - self._state_entered_at
            if elapsed >= self._cooldown_sec:
                LOG.info("MetaFSMv2: cooldown elapsed (%.1fs), resuming NORMAL", elapsed)
                return self._fsm.handle(
                    self._KEY,
                    Message(
                        op="EVT", verb="COOLDOWN_ELAPSED",
                        src="meta_timer", dst="meta",
                        why=f"cooldown {elapsed:.0f}s",
                    ),
                )

        return current, None

    def inject_event(self, op: str, verb: str, why: str = "manual") -> Tuple[str, Optional[Message]]:
        """
        Inject an arbitrary event into the meta-FSM (for external signals).

        Args:
            op: Message op (EVT, CMD, etc.)
            verb: Message verb
            why: Reason string
        """
        return self._fsm.handle(
            self._KEY,
            Message(op=op, verb=verb, src="external", dst="meta", why=why),
        )

    def get_metrics(self) -> dict:
        """Return meta-FSM metrics."""
        return {
            "state": self.state,
            "fsm_metrics": {
                "transitions": self._fsm.metrics.transitions,
                "rejected": self._fsm.metrics.rejected,
                "guard_rejected": self._fsm.metrics.guard_rejected,
            },
        }

    # ── Callbacks ────────────────────────────────────────────────────

    def _on_enter_normal(self, key: str, state: str, msg: Message) -> None:
        self._state_entered_at = time.time()
        LOG.info("MetaFSMv2 → NORMAL")

    def _on_enter_low_risk(self, key: str, state: str, msg: Message) -> None:
        self._state_entered_at = time.time()
        LOG.warning("MetaFSMv2 → LOW_RISK (reason: %s)", msg.why)

    def _on_enter_cooldown(self, key: str, state: str, msg: Message) -> None:
        self._state_entered_at = time.time()
        LOG.info("MetaFSMv2 → COOLDOWN")

    def _on_enter_degraded(self, key: str, state: str, msg: Message) -> None:
        self._state_entered_at = time.time()
        LOG.warning("MetaFSMv2 → DEGRADED (reason: %s)", msg.why)

    # ── Actions (return Messages to be emitted) ─────────────────────

    @staticmethod
    def _action_switch_low_risk(msg: Message) -> Message:
        return Message(
            op="CMD",
            verb="SWITCH_TO_LOW_RISK_MODE",
            src="meta_fsm",
            dst="risk_strategy",
            pld={"trigger": msg.pld.get("reason", "entropy_spike")},
            why=f"meta: {msg.why[:60]}",
        )

    @staticmethod
    def _action_degraded(msg: Message) -> Message:
        return Message(
            op="CMD",
            verb="SWITCH_TO_LOW_RISK_MODE",
            src="meta_fsm",
            dst="risk_strategy",
            pld={"trigger": "topology_drift", "reason": msg.why},
            why=f"meta degraded: {msg.why[:50]}",
        )

    @staticmethod
    def _action_resume_normal(msg: Message) -> Message:
        return Message(
            op="EVT",
            verb="NORMAL_MODE_RESTORED",
            src="meta_fsm",
            dst="risk_strategy",
            why="meta: system stable",
        )
