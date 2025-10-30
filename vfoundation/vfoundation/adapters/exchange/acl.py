"""
Exchange ACL Adapter — Anti-Corruption Layer

Maps external exchange events/commands to internal Message protocol.
Shadow-mode: receives events, generates decisions, but NO live orders.

Responsibilities:
- Convert exchange DTOs → Message (EVT, UPD)
- Convert FSM decisions (DEC) → exchange commands (stub)
- Idempotency via deterministic key generation
- Fail-closed: reject invalid contracts before routing
- Metrics: events_rx/tx, rejects, latency, dedup
"""

from typing import Dict, Any, Optional, Iterator
from dataclasses import dataclass
import time
import hashlib
import json
from ...core.protocol import Message

# Metrics tracking
_acl_metrics = {
    "events_rx_total": 0,
    "events_tx_total": 0,
    "rejects_total": 0,
    "dedup_total": 0,
    "latency_p95_ms": 0.0,
}


@dataclass
class OrderCommand:
    """External command structure (exchange-agnostic)"""

    symbol: str
    side: str  # BUY/SELL
    qty: float
    order_type: str  # LIMIT/MARKET
    price: Optional[float] = None
    tif: str = "GTC"  # Time-In-Force
    client_order_id: Optional[str] = None


@dataclass
class OrderEvent:
    """External event from exchange"""

    event_type: str  # PLACED, PARTIAL_FILL, FILL, CANCELLED, REJECTED
    symbol: str
    side: str
    qty: float
    filled_qty: float
    price: Optional[float]
    order_id: str
    client_order_id: str
    timestamp_ms: int
    reason: Optional[str] = None  # For REJECTED


class ExchangeACL:
    """ACL Adapter for exchange integration (shadow-mode)"""

    def __init__(self, shadow_mode: bool = True):
        self.shadow_mode = shadow_mode
        self._latencies: list[float] = []

    def submit(self, cmd: Message) -> Message:
        """
        Submit command to exchange (shadow stub).

        Args:
            cmd: Message with op=CMD, verb=OPEN/CLOSE/ADJUST

        Returns:
            Message with op=EVT, verb=ORDER_PLACED (or REJECTED)
        """
        start_ms = time.time() * 1000

        # Validate contract
        if cmd.op != "CMD":
            _acl_metrics["rejects_total"] += 1
            return self._error_response(cmd, "INVALID_OP", "expected CMD")

        if cmd.verb not in ["OPEN", "CLOSE", "ADJUST"]:
            _acl_metrics["rejects_total"] += 1
            return self._error_response(cmd, "INVALID_VERB", f"unknown verb {cmd.verb}")

        # Check idempotency
        idem_key = self._generate_idempotent_key(cmd)
        if self._is_duplicate(idem_key):
            _acl_metrics["dedup_total"] += 1
            return self._cached_response(cmd, idem_key)

        # Shadow mode: stub response (no real order)
        if self.shadow_mode:
            response = self._stub_submit(cmd)
        else:
            # TODO: real exchange submission in P2
            response = self._stub_submit(cmd)

        # Record metrics
        latency_ms = (time.time() * 1000) - start_ms
        self._record_latency(latency_ms)
        _acl_metrics["events_tx_total"] += 1

        return response

    def cancel(self, cmd: Message) -> Message:
        """Cancel order (shadow stub)"""
        if cmd.verb != "CLOSE":
            _acl_metrics["rejects_total"] += 1
            return self._error_response(cmd, "INVALID_VERB", "expected CLOSE")

        # Shadow stub: immediate cancel
        return Message(
            op="EVT",
            verb="CANCELLED",
            src="exchange",
            dst=cmd.src,
            rid=cmd.rid,
            why="shadow cancel stub",
            pld={"order_id": f"stub-{cmd.rid}", "reason": "user_cancel"},
        )

    def stream_events(self) -> Iterator[Message]:
        """
        Stream exchange events (stub generator).
        In real implementation: websocket/REST poll.
        """
        # Stub: generate fake events for testing
        yield self._stub_event("PARTIAL_FILL", "BTCUSDT", "BUY", 0.5)
        yield self._stub_event("FILL", "BTCUSDT", "BUY", 1.0)

    def _stub_submit(self, cmd: Message) -> Message:
        """Stub exchange submission"""
        return Message(
            op="EVT",
            verb="ORDER_PLACED",
            src="exchange",
            dst=cmd.src,
            rid=cmd.rid,
            why="shadow stub placed",
            pld={
                "order_id": f"stub-{cmd.rid}",
                "symbol": cmd.pld.get("symbol", "UNKNOWN"),
                "side": cmd.pld.get("side", "UNKNOWN"),
                "qty": cmd.pld.get("qty", 0),
                "price": cmd.pld.get("price"),
                "status": "ACCEPTED",
            },
        )

    def _stub_event(self, event_type: str, symbol: str, side: str, filled_qty: float) -> Message:
        """Generate stub event"""
        return Message(
            op="EVT",
            verb=event_type,
            src="exchange",
            dst="execpos_fsm",
            rid=f"stub-{symbol}-{int(time.time() * 1000)}",
            why=f"stub {event_type.lower()}",
            pld={
                "symbol": symbol,
                "side": side,
                "filled_qty": filled_qty,
                "timestamp_ms": int(time.time() * 1000),
            },
        )

    def _generate_idempotent_key(self, cmd: Message) -> str:
        """Generate deterministic idempotent key"""
        # Key components: op, verb, symbol, qty, price, time_bucket (1min)
        ts_bucket = (cmd.ts // 60000) * 60000  # Round to minute
        pld = cmd.pld or {}
        key_data = {
            "op": cmd.op,
            "verb": cmd.verb,
            "symbol": pld.get("symbol", ""),
            "qty": pld.get("qty", 0),
            "price": pld.get("price"),
            "ts_bucket": ts_bucket,
        }
        key_str = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_str.encode()).hexdigest()[:16]

    def _is_duplicate(self, idem_key: str) -> bool:
        """Check if request is duplicate (stub: always false)"""
        # TODO: integrate with idempotency store in P2
        return False

    def _cached_response(self, cmd: Message, idem_key: str) -> Message:
        """Return cached response for duplicate"""
        return Message(
            op="EVT",
            verb="DEDUP",
            src="exchange_acl",
            dst=cmd.src,
            rid=cmd.rid,
            why="duplicate request",
            pld={"dedup": True, "idem_key": idem_key},
        )

    def _error_response(self, cmd: Message, error_code: str, reason: str) -> Message:
        """Generate error response"""
        return Message(
            op="ERR",
            verb=error_code,
            src="exchange_acl",
            dst=cmd.src,
            rid=cmd.rid,
            why=reason[:80],  # Enforce WHY-discipline
            pld={"error": error_code, "reason": reason},
        )

    def _record_latency(self, latency_ms: float) -> None:
        """Record latency for p95 calculation"""
        self._latencies.append(latency_ms)
        if len(self._latencies) > 100:
            self._latencies = sorted(self._latencies)[-100:]
            _acl_metrics["latency_p95_ms"] = self._latencies[94]  # p95 of last 100


def get_acl_metrics() -> Dict[str, Any]:
    """Get ACL adapter metrics"""
    return _acl_metrics.copy()
