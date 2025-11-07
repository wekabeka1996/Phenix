# apps/reference/orchestrator/orchestrator_fsm.py
"""
OrchestratorFSM - Centralized coordinator for Phenix v1.

Responsibilities:
- RID lifecycle management (EVAL → OPEN → MONITOR → CLOSED)
- WHY chain aggregation and preservation
- TTL/GC registration and cleanup
- Circuit breaker for error handling
- Idempotency checks
- Ed25519 signing for high-risk DEC/CMD operations
"""

from vfoundation.dr import wal
from vfoundation.core.fsm_emit_compat import Message, emit_compat
from .utils_event_bus import LocalBus
from .types import (
    RIDLifecycle,
    OrchestratorEvent,
    OrchestratorState,
    OrchestratorConfig
)
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

try:
    from vfoundation.security import signing_ed25519 as _signing_ed25519
    SIGNING_AVAILABLE = True
except ImportError:
    SIGNING_AVAILABLE = False
    _signing_ed25519 = None  # type: ignore

signing_ed25519 = _signing_ed25519


try:
    from apps.reference.monitoring.performance_monitor import PerformanceMonitor as _PerformanceMonitor, SLOConfig as _SLOConfig
    PERFORMANCE_MONITORING_AVAILABLE = True
except ImportError:
    PERFORMANCE_MONITORING_AVAILABLE = False
    _PerformanceMonitor = None  # type: ignore
    _SLOConfig = None  # type: ignore

# Assign with proper fallback
PerformanceMonitor = _PerformanceMonitor
SLOConfig = _SLOConfig


class OrchestratorFSM:
    """
    Centralized orchestrator for trade lifecycle coordination.

    Manages RID states, aggregates WHY chains, handles signing,
    circuit breaker, and cleanup operations.
    """

    def __init__(
        self,
        config: OrchestratorConfig,
        fsm=None,  # Event bus (FSMCore or LocalBus)
        logger: Optional[logging.Logger] = None
    ):
        self.config = config
        self.logger = logger or logging.getLogger(__name__)

        # Event bus setup
        if fsm and hasattr(fsm, "listen") and hasattr(fsm, "emit"):
            self.bus = fsm
            self.logger.debug("OrchestratorFSM using provided event bus")
        else:
            self.bus = LocalBus()
            self.logger.debug("OrchestratorFSM using LocalBus fallback")

        # RID state storage (in-memory for now, could be Redis/DB later)
        self._rid_states: Dict[str, OrchestratorState] = {}

        # Circuit breaker state
        self._error_counts: Dict[str, int] = {}  # domain -> error count
        self._circuit_breaker_reset_time: Dict[str, datetime] = {}

        # Performance monitoring
        self.performance_monitor: Optional[PerformanceMonitor] = None
        if PERFORMANCE_MONITORING_AVAILABLE:
            slo_config = SLOConfig(
                p95_target_ms=50.0,  # 50ms p95 target
                p95_overall_target_ms=100.0,  # 100ms overall target
                timeout_rate_target=0.01,  # 1% timeout rate
                why_coverage_target=0.95  # 95% WHY coverage
            )
            self.performance_monitor = PerformanceMonitor(
                slo_config=slo_config,
                logger=self.logger.getChild("performance")
            )
            self.logger.info("Performance monitoring enabled")

        # Background cleanup task
        self._cleanup_task: Optional[asyncio.Task] = None

        # Register event listeners
        self.bus.listen("EVT:TRADE_INTENT_PROPOSED",
                        self._on_trade_intent_proposed)
        self.bus.listen("EVT:ORDER_EXECUTED", self._on_order_executed)
        self.bus.listen("EVT:POSITION_CLOSED", self._on_position_closed)
        self.bus.listen("EVT:ORDER_TIMEOUT", self._on_timeout)
        self.bus.listen("EVT:ORDER_REJECTED", self._on_error)

    async def start(self) -> None:
        """Start the orchestrator."""
        self.logger.info("Starting OrchestratorFSM")
        # Start background cleanup
        self._cleanup_task = asyncio.create_task(self._background_cleanup())

        # Start performance monitoring
        if self.performance_monitor:
            await self.performance_monitor.start_monitoring()

    async def stop(self) -> None:
        """Stop the orchestrator."""
        self.logger.info("Stopping OrchestratorFSM")

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # Stop performance monitoring
        if self.performance_monitor:
            await self.performance_monitor.stop_monitoring()

    def _on_trade_intent_proposed(self, message: Dict[str, Any]) -> None:
        """Handle TRADE_INTENT_PROPOSED event."""
        try:
            rid = message.get('rid', '')
            if not rid:
                self.logger.warning(
                    f"TRADE_INTENT_PROPOSED without RID: {message}")
                return

            # Start performance timing
            timing_id = None
            if self.performance_monitor:
                timing_id = self.performance_monitor.start_decision(rid)

            # Check circuit breaker BEFORE creating state
            if self._is_circuit_breaker_active("trading"):
                self.logger.warning(
                    f"Circuit breaker active for trading, rejecting RID {rid}")
                self._emit_error(message, "CIRCUIT_BREAKER_ACTIVE")
                # End timing with failure
                if self.performance_monitor and timing_id:
                    self.performance_monitor.end_decision(
                        timing_id, success=False, error_message="CIRCUIT_BREAKER_ACTIVE"
                    )
                return

            # Check idempotency
            idempotency_key = message.get('pld', {}).get("idempotency_key")
            if idempotency_key and self._is_duplicate(idempotency_key):
                self.logger.warning(
                    f"Duplicate request for key {idempotency_key}, RID {rid}")
                self._emit_error(message, "DUPLICATE_REQUEST")
                # End timing with failure
                if self.performance_monitor and timing_id:
                    self.performance_monitor.end_decision(
                        timing_id, success=False, error_message="DUPLICATE_REQUEST"
                    )
                return

            # Get or create RID state
            state = self._get_or_create_rid_state(rid)

            self.logger.info(f"Processing trade intent for RID {state.rid}")

            # Update lifecycle
            state.lifecycle = RIDLifecycle.EVAL
            state.updated_at = datetime.now()

            # Aggregate WHY chain
            intent_why = message.get('pld', {}).get("why", [])
            if isinstance(intent_why, str):
                intent_why = [intent_why]
            state.why_chain.extend(intent_why)

            # Store idempotency key
            state.idempotency_key = idempotency_key

            # Create signed CMD:OPEN
            self._create_signed_open_command(message, state)

            # Update lifecycle to OPEN
            state.lifecycle = RIDLifecycle.OPEN

            # End timing with success
            if self.performance_monitor and timing_id:
                self.performance_monitor.end_decision(
                    timing_id, success=True, why_chain_length=len(state.why_chain)
                )

            # Log to WAL
            self._log_to_wal("ORCHESTRATOR_EVAL_COMPLETED", {
                "rid": state.rid,
                "lifecycle": state.lifecycle.value,
                "why_chain_length": len(state.why_chain)
            })

        except Exception as e:
            self.logger.error(f"Error in _on_trade_intent_proposed: {e}")
            self._record_error("orchestrator", str(e))
            # End timing with failure
            if self.performance_monitor and timing_id:
                self.performance_monitor.end_decision(
                    timing_id, success=False, error_message=str(e)
                )

    def _on_order_executed(self, message: Dict[str, Any]) -> None:
        """Handle ORDER_EXECUTED event."""
        try:
            rid = message.get('rid', '')
            if not rid:
                return

            state = self._rid_states.get(rid)
            if not state:
                return

            self.logger.info(f"Order executed for RID {state.rid}")

            # Update lifecycle
            state.lifecycle = RIDLifecycle.MONITOR
            state.updated_at = datetime.now()

            # Extend WHY chain
            execution_why = message.get('pld', {}).get("why", [])
            if isinstance(execution_why, str):
                execution_why = [execution_why]
            state.why_chain.extend(execution_why)

            # Log to WAL
            self._log_to_wal("ORCHESTRATOR_ORDER_EXECUTED", {
                "rid": state.rid,
                "lifecycle": state.lifecycle.value,
                "order_id": message.get('pld', {}).get("order_id")
            })

        except Exception as e:
            self.logger.error(f"Error in _on_order_executed: {e}")

    def _on_position_closed(self, message: Dict[str, Any]) -> None:
        """Handle POSITION_CLOSED event."""
        try:
            rid = message.get('rid', '')
            if not rid:
                return

            state = self._rid_states.get(rid)
            if not state:
                return

            self.logger.info(f"Position closed for RID {state.rid}")

            # Update lifecycle
            state.lifecycle = RIDLifecycle.CLOSED
            state.updated_at = datetime.now()

            # Final WHY aggregation
            close_why = message.get('pld', {}).get("why", [])
            if isinstance(close_why, str):
                close_why = [close_why]
            state.why_chain.extend(close_why)

            # Log completion
            self._log_to_wal("ORCHESTRATOR_POSITION_CLOSED", {
                "rid": state.rid,
                "lifecycle": state.lifecycle.value,
                "final_why_chain": state.why_chain
            })

        except Exception as e:
            self.logger.error(f"Error in _on_position_closed: {e}")

    def _on_timeout(self, msg: Message) -> None:
        """Handle TIMEOUT event."""
        try:
            rid = msg.rid
            if not rid:
                return

            state = self._rid_states.get(rid)
            if not state:
                return

            self.logger.warning(f"Timeout for RID {state.rid}")

            # Record timeout in performance monitor
            if self.performance_monitor:
                self.performance_monitor.record_timeout(rid)

            # Record error for circuit breaker
            self._record_error("timeout", f"RID {state.rid} timed out")

            # Update state
            state.error_count += 1
            state.updated_at = datetime.now()

        except Exception as e:
            self.logger.error(f"Error in _on_timeout: {e}")

    def _on_error(self, msg: Message) -> None:
        """Handle ERROR event."""
        try:
            rid = msg.rid
            if not rid:
                return

            state = self._rid_states.get(rid)
            if not state:
                return

            error_msg = msg.pld.get("error", "Unknown error")
            self.logger.error(f"Error for RID {state.rid}: {error_msg}")

            # Record error
            self._record_error("execution", error_msg)

            # Update state
            state.error_count += 1
            state.updated_at = datetime.now()

        except Exception as e:
            self.logger.error(f"Error in _on_error: {e}")

    def _create_signed_open_command(self, message: Dict[str, Any], state: OrchestratorState) -> None:
        """Create and sign CMD:OPEN command."""
        try:
            # Extract intent data
            intent = message.get('pld', {})

            # Create command payload
            cmd_payload = {
                "command": "OPEN",
                "symbol": intent.get("symbol"),
                "side": intent.get("side"),
                "quantity": str(intent.get("quantity", 0)),
                "price": str(intent.get("price", 0)),
                "why_chain": state.why_chain,
                "data_ref": message.get('data_ref', []),
            }

            # Sign if enabled
            if self.config.enable_signing and SIGNING_AVAILABLE:
                # Convert to string for signing
                sign_data = str(cmd_payload)
                signature = signing_ed25519.sign(sign_data.encode())
                cmd_payload["signature"] = signature.hex()
            elif self.config.enable_signing:
                self.logger.warning("Signing requested but nacl not available")

            # Emit command
            self.bus.emit(
                "CMD:OPEN",
                cmd_payload,
                f"OrchestratorFSM signed command for RID {state.rid}",
                state.why_chain
            )

        except Exception as e:
            self.logger.error(
                f"Failed to create signed command for RID {state.rid}: {e}")

    def _get_or_create_rid_state(self, rid: str) -> OrchestratorState:
        """Get existing RID state or create new one."""
        if rid not in self._rid_states:
            self._rid_states[rid] = OrchestratorState(
                rid=rid,
                lifecycle=RIDLifecycle.EVAL,
                created_at=datetime.now(),
                updated_at=datetime.now()
            )
        return self._rid_states[rid]

    def _is_circuit_breaker_active(self, domain: str) -> bool:
        """Check if circuit breaker is active for domain."""
        now = datetime.now()
        reset_time = self._circuit_breaker_reset_time.get(domain)

        # Reset counter if window expired
        if reset_time and now > reset_time:
            self._error_counts[domain] = 0
            del self._circuit_breaker_reset_time[domain]

        error_count = self._error_counts.get(domain, 0)
        return error_count >= self.config.circuit_breaker_threshold

    def _is_duplicate(self, idempotency_key: str) -> bool:
        """Check if request is duplicate based on idempotency key."""
        # Simple in-memory check (should be Redis/DB in production)
        for state in self._rid_states.values():
            if state.idempotency_key == idempotency_key:
                return True
        return False

    def _record_error(self, domain: str, error: str) -> None:
        """Record error for circuit breaker."""
        self._error_counts[domain] = self._error_counts.get(domain, 0) + 1

        # Set reset time (1 hour window)
        if domain not in self._circuit_breaker_reset_time:
            self._circuit_breaker_reset_time[domain] = datetime.now(
            ) + timedelta(hours=1)

        self.logger.warning(f"Error recorded for domain {domain}: {error}")

    def _emit_error(self, original_message: Dict[str, Any], error_code: str) -> None:
        """Emit error event."""
        self.bus.emit(
            "EVT:ORCHESTRATOR_ERROR",
            {
                "error_code": error_code,
                "original_rid": original_message.get('rid', ''),
                "original_payload": original_message.get('pld', {})
            },
            f"OrchestratorFSM error: {error_code}"
        )

    def _log_to_wal(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log event to WAL."""
        try:
            wal_record = {
                "event_type": event_type,
                "timestamp": datetime.now().isoformat(),
                "data": data
            }
            wal.append(wal_record)
        except Exception as e:
            self.logger.error(f"Failed to log to WAL: {e}")

    async def _background_cleanup(self) -> None:
        """Background task for cleaning up expired RIDs."""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes

                now = datetime.now()
                expired_rids = []

                for rid, state in self._rid_states.items():
                    if now - state.updated_at > timedelta(seconds=state.ttl_seconds):
                        expired_rids.append(rid)

                for rid in expired_rids:
                    self.logger.info(f"Cleaning up expired RID {rid}")
                    del self._rid_states[rid]

                if expired_rids:
                    self._log_to_wal("ORCHESTRATOR_CLEANUP", {
                        "expired_rids": expired_rids,
                        "total_cleaned": len(expired_rids)
                    })

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in background cleanup: {e}")

    def get_rid_trace(self, rid: str) -> Optional[Dict[str, Any]]:
        """Get full trace for RID (used by /debug/{rid})."""
        state = self._rid_states.get(rid)
        if not state:
            return None

        return {
            "rid": state.rid,
            "lifecycle": state.lifecycle.value,
            "why_chain": state.why_chain,
            "created_at": state.created_at.isoformat(),
            "updated_at": state.updated_at.isoformat(),
            "error_count": state.error_count,
            "circuit_breaker_active": False  # Not implemented per RID yet
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics."""
        base_stats = {
            "active_rids": len(self._rid_states),
            "error_counts": dict(self._error_counts),
            "circuit_breaker_domains": list(self._circuit_breaker_reset_time.keys())
        }

        # Add performance metrics if available
        if self.performance_monitor:
            metrics = self.performance_monitor.get_current_metrics()
            slo_status = self.performance_monitor.check_slo_compliance()

            base_stats["performance"] = {
                "metrics": {
                    "total_decisions": metrics.total_decisions,
                    "successful_decisions": metrics.successful_decisions,
                    "failed_decisions": metrics.failed_decisions,
                    "timeouts": metrics.timeouts,
                    "p50_latency_ms": metrics.p50_latency_ms,
                    "p95_latency_ms": metrics.p95_latency_ms,
                    "p99_latency_ms": metrics.p99_latency_ms,
                    "timeout_rate": metrics.timeout_rate,
                    "slo_violations": metrics.slo_violations,
                    "why_coverage": metrics.why_coverage
                },
                "slo_status": slo_status
            }

        return base_stats
