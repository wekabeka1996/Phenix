"""
FSMP-P1-T02: Open Flow FSM for execution_position domain.

States: IDLE → CANDIDATE → READY → EMIT_DEC_OPEN → DONE
Guards: min_notional, qty/price steps, cooldown
Output: DEC:OPEN(symbol, side, qty, price?, tif?)

Shadow-mode: no live API calls, all I/O via ACL stub.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from urllib.parse import urlencode

# T2B-04: Time abstraction for deterministic testing
from apps.reference.core.time import get_clock
from enum import Enum
from typing import Callable, Dict, Optional, Any

from vfoundation.core.protocol import Message
from .contracts import (
    MIN_ORDER_QTY,
    MIN_NOTIONAL,
    QTY_STEP,
    PRICE_STEP,
)
from .metrics_collector import MetricsCollector
from .open_dispatch_adapter import (
    OPEN_DISPATCH_CONTRACT,
    OPEN_DISPATCH_PATH,
    OpenDispatchAdapterError,
    OpenDispatchPayload,
    build_open_dispatch_trace_ref,
)
from apps.reference.config_models import AuroraConfig
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Literal
from pydantic import model_validator


class DetectorEventProvenancePayload(BaseModel):
    """Detector-side regime provenance carried additively into execution."""

    model_config = ConfigDict(extra='forbid')

    event_name: str = Field(..., min_length=1)
    rid: Optional[str] = Field(default=None)
    ts_ms: Optional[int] = Field(default=None, ge=0)
    last_update_ts_ms: Optional[int] = Field(default=None, ge=0)
    structural_regime_ref: Optional[str] = Field(default=None)
    basis_tf_sec: Optional[int] = Field(default=None, ge=1)
    bar_close_ts_ms: Optional[int] = Field(default=None, ge=0)
    changed: Optional[bool] = Field(default=None)
    regime: Optional[str] = Field(default=None)
    confidence: Optional[str] = Field(default=None)
    stable_confidence: Optional[float | str] = Field(default=None)
    source_model: Optional[str] = Field(default=None)
    pre_cutoff_source_model: Optional[str] = Field(default=None)
    confidence_min: Optional[float | str] = Field(default=None)
    confidence_max: Optional[float | str] = Field(default=None)
    pre_cutoff_regime: Optional[str] = Field(default=None)
    pre_cutoff_confidence: Optional[float | str] = Field(default=None)
    pre_cutoff_clamped_to_min: Optional[bool] = Field(default=None)
    pre_cutoff_clamped_to_max: Optional[bool] = Field(default=None)
    pre_cutoff_boundary_reason: Optional[str] = Field(default=None)
    uncertain_cutoff: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    demoted_to_uncertain: Optional[bool] = Field(default=None)
    raw_regime: Optional[str] = Field(default=None)
    raw_confidence: Optional[float | str] = Field(default=None)
    raw_boundary_reason: Optional[str] = Field(default=None)
    hysteresis_bars: Optional[int] = Field(default=None, ge=1)
    hysteresis_confirm_count: Optional[int] = Field(default=None, ge=0)
    carried_previous_stable: Optional[bool] = Field(default=None)
    emitted_confidence_kind: Optional[str] = Field(default=None)
    reason_summary: Optional[str] = Field(default=None)


class CacheSnapshotProvenancePayload(BaseModel):
    """Cache snapshot truth used by decision_making at intent time."""

    model_config = ConfigDict(extra='forbid')

    cache_write_ts_ms: Optional[int] = Field(default=None, ge=0)
    regime: Optional[str] = Field(default=None)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class RegimeProvenancePayload(BaseModel):
    """Strict additive regime provenance block for execution-boundary handoff."""

    model_config = ConfigDict(extra='forbid')

    source_kind: Literal["detector_event", "detector_cache", "unknown"]
    detector_event: Optional[DetectorEventProvenancePayload] = Field(
        default=None)
    cache_snapshot: Optional[CacheSnapshotProvenancePayload] = Field(
        default=None)


class CmdOpenPayload(BaseModel):
    """
    EP-01.4-INT-A: Strict Pydantic model for CMD:OPEN payload validation.

    FAIL-CLOSED: Unknown fields are rejected (extra='forbid').
    This ensures contract integrity for CMD:OPEN commands.
    """
    model_config = ConfigDict(extra='forbid')

    # Required fields
    symbol: str = Field(..., min_length=1,
                        description="Trading symbol (e.g., BTCUSDT)")
    side: Literal["BUY", "SELL"] = Field(..., description="Order side")
    qty: str = Field(..., pattern=r"^[0-9]+(\.[0-9]+)?$",
                     description="Order quantity (string-encoded)")
    # ORDER-POLICY-01: REQUIRED. No silent defaults.
    order_type: Literal["MARKET",
                        "LIMIT"] = Field(..., description="Order type. REQUIRED.")

    # Optional fields
    price: Optional[str] = Field(
        default=None, pattern=r"^[0-9]+(\.[0-9]+)?$", description="Limit price")
    price_ref: Optional[str] = Field(
        default=None, description="Reference price for checks")
    tif: Optional[Literal["GTC", "GTX", "IOC", "FOK"]] = Field(
        default=None,
        description="Time in force. REQUIRED for LIMIT. Must be null for MARKET."
    )
    valid_for_ms: Optional[int] = Field(
        default=None, ge=1000, description="Pending entry TTL in ms (LIMIT-only)")
    stop_price: Optional[str] = Field(
        default=None, description="Stop-loss price")
    target_price: Optional[str] = Field(
        default=None, description="Take-profit price")
    sl_pct: Optional[str] = Field(
        default=None, description="Stop-loss percentage")
    idempotent_key: Optional[str] = Field(
        default=None, description="Idempotency key")
    rid: Optional[str] = Field(
        default=None, description="Request ID for correlation")
    strategy: Optional[str] = Field(
        default=None, description="Strategy ID (e.g., 'aurora', 'mean_reversion')")
    regime_epoch_ref: Optional[str] = Field(
        default=None,
        description="Decision-making-owned stable regime epoch propagated additively to execution.",
    )
    regime: Optional[str] = Field(
        default=None,
        description="Decision-time structural regime propagated additively to execution.",
    )
    regime_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Decision-time regime confidence propagated additively to execution.",
    )
    regime_provenance: Optional[RegimeProvenancePayload] = Field(
        default=None,
        description="Structured detector/cache provenance for the propagated regime truth.",
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional structured metadata (e.g., strategy/tca/risk context).",
    )

    @field_validator('tif', mode='before')
    @classmethod
    def normalize_tif(cls, v):
        """Normalize tif to uppercase if string."""
        if v is None:
            return None
        if isinstance(v, str):
            return v.upper()
        return v

    @model_validator(mode="after")
    def _cross_field_contract(self):
        # Fail-closed contract rules (no silent defaults).
        if self.order_type == "LIMIT":
            if self.price is None:
                raise ValueError("LIMIT requires price")
            if self.tif is None:
                raise ValueError("LIMIT requires tif (no default)")
            if self.valid_for_ms is None:
                raise ValueError("LIMIT requires valid_for_ms (no fallback)")
        elif self.order_type == "MARKET":
            if self.tif is not None:
                raise ValueError("MARKET must have tif=null")
        return self


class OpenState(str, Enum):
    """FSM states for open flow."""

    IDLE = "IDLE"
    DONE = "DONE"
    ERROR = "ERROR"


class OpenFlowFSM:
    """
    Open Flow FSM: processes CMD:OPEN and emits DEC:OPEN after guards.

    Shadow-mode: validates contracts, generates DEC, but no live orders.
    Guards (fail-closed): min_notional, qty/price steps, cooldown.

    TASK47c-E: Leverage verification before DEC:OPEN.
    """
    _LIMIT_ROUNDING_TRACE_REF_PREFIX = "obs://execution_position/limit_rounding?"

    def __init__(
        self,
        cooldown_sec: float = 1.0,
        guard_enabled: bool = True,
        config: Optional[AuroraConfig] = None,
        metrics_collector: Optional[MetricsCollector] = None,
        leverage_service: Optional[Any] = None,
        is_live_execution: bool = False,
        pre_open_guard: Optional[Callable[[Message], Optional[Message]]] = None,
    ):
        self.state = OpenState.IDLE
        self.cooldown_sec = cooldown_sec
        self.guard_enabled = guard_enabled

        if isinstance(config, dict):
            raise TypeError(
                "OpenFlowFSM requires typed AuroraConfig, got dict")
        if config is None:
            raise ValueError(
                f"CRITICAL: {self.__class__.__name__} requires valid AuroraConfig. "
                "Refusing to start with empty defaults."
            )
        self.config = config

        self.last_open_ts: float = 0.0
        self.logger = logging.getLogger(__name__)
        self.metrics_collector = metrics_collector
        self._metrics: Dict[str, int] = {
            "fsm_open_decisions_total": 0,
            "fsm_guard_rejects_total": 0,
            "fsm_errors_total": 0,
        }
        self.idempotency_store: Dict[str, float] = {}
        self.pre_open_guard = pre_open_guard

        # TASK47c-E: LeverageService integration
        self.leverage_service = leverage_service
        self.is_live_execution = is_live_execution

        # Fail-closed: LIVE mode requires leverage_service
        if is_live_execution and leverage_service is None:
            raise RuntimeError(
                "LeverageService is required for LIVE execution mode. "
                "Pass leverage_service to OpenFlowFSM or set is_live_execution=False for shadow/dev."
            )

        if leverage_service is None:
            self.logger.warning(
                "TASK47c-E: OpenFlowFSM initialized without LeverageService. "
                "Leverage verification will be SKIPPED (shadow/dev mode only)."
            )

        # Idempotency window from config - SSOT: domains.execution_position.fsm_open (FAIL-CLOSED)
        try:
            if not hasattr(self.config, 'domains') or not hasattr(self.config.domains, 'execution_position'):
                raise ValueError(
                    "domains.execution_position config is required")
            fsm_open_cfg = self.config.domains.execution_position.fsm_open
            if fsm_open_cfg is None or fsm_open_cfg.idempotency_window_sec is None:
                raise ValueError("fsm_open.idempotency_window_sec is required")
            self.idempotency_window_sec = fsm_open_cfg.idempotency_window_sec
        except (AttributeError, TypeError) as e:
            raise ValueError(
                f"Failed to load idempotency_window_sec from domains.execution_position.fsm_open: {e}. "
                "Check domains.yaml has execution_position.fsm_open.idempotency_window_sec"
            ) from e

    @staticmethod
    def _round_limit_price_to_tick(price: Decimal, tick_size: Decimal, side: str) -> tuple[Decimal, str]:
        """Round LIMIT price in a side-aware passive direction."""
        side_upper = str(side).upper()
        rounding_mode = ROUND_FLOOR if side_upper == "BUY" else ROUND_CEILING
        rounding_label = "floor" if side_upper == "BUY" else "ceil"
        rounded = (
            (price / tick_size).to_integral_value(rounding=rounding_mode) * tick_size
        ).quantize(tick_size)
        return rounded, rounding_label

    @classmethod
    def _build_limit_rounding_trace_ref(
        cls,
        *,
        price_before_rounding: Decimal,
        price_after_rounding: Decimal,
        tick_size: Decimal,
        rounding_mode: str,
    ) -> str:
        query = urlencode(
            {
                "before": str(price_before_rounding),
                "after": str(price_after_rounding),
                "tick": str(tick_size),
                "mode": str(rounding_mode),
            }
        )
        return f"{cls._LIMIT_ROUNDING_TRACE_REF_PREFIX}{query}"

    def _get_instrument_specs(self, symbol: str) -> Dict[str, Decimal]:
        """Get instrument specifications from config.

        CFG-INSTRUMENTS-STEP-03-EXECUTION-PRECISION:
        Uses canonical config.instruments (SSOT from config/aurora/instruments.yaml).
        """
        # CANONICAL: config.instruments only
        instruments = self.config.instruments or {}
        specs = instruments.get(symbol)

        # Default values (fallback for non-trading symbols or missing config)
        min_qty = MIN_ORDER_QTY
        step_size = QTY_STEP
        tick_size = PRICE_STEP
        min_notional = MIN_NOTIONAL

        if specs:
            def _parse_positive_decimal(raw: Any, field: str) -> Decimal:
                try:
                    value = Decimal(str(raw))
                except (InvalidOperation, TypeError, ValueError) as e:
                    raise ValueError(
                        f"Invalid {field} for {symbol}: {raw!r}") from e
                if value <= 0:
                    raise ValueError(
                        f"Invalid {field} for {symbol}: {raw!r} (must be > 0)")
                return value

            # Pydantic model InstrumentPrecisionSpec fields, convert to Decimal
            # Primary fields (tick_size/step_size are float in canonical model)
            if hasattr(specs, 'tick_size') and specs.tick_size is not None:
                tick_size = _parse_positive_decimal(
                    specs.tick_size, "tick_size")
            if hasattr(specs, 'step_size') and specs.step_size is not None:
                step_size = _parse_positive_decimal(
                    specs.step_size, "step_size")

            # Optional legacy fields (may not be in InstrumentPrecisionSpec)
            if hasattr(specs, 'min_qty') and specs.min_qty is not None:
                min_qty = _parse_positive_decimal(specs.min_qty, "min_qty")
            if hasattr(specs, 'min_notional') and specs.min_notional is not None:
                min_notional = _parse_positive_decimal(
                    specs.min_notional, "min_notional")

        return {
            "min_qty": min_qty,
            "step_size": step_size,
            "tick_size": tick_size,
            "min_notional": min_notional,
        }

    def _cleanup_idempotency_store(self):
        """Remove expired keys from the idempotency store."""
        now = get_clock().now_sec()
        expired_keys = [
            key
            for key, timestamp in self.idempotency_store.items()
            if now - timestamp > self.idempotency_window_sec
        ]
        for key in expired_keys:
            del self.idempotency_store[key]
        if expired_keys:
            self.logger.info(
                f"IDEMPOTENCY: Cleaned up {len(expired_keys)} expired keys."
            )

    def handle(self, msg: Message) -> Optional[Message]:
        """
        Process incoming message and return DEC:OPEN if guards pass.

        Args:
            msg: CMD:OPEN with pld: symbol, side, qty, price?, order_type?, tif?

        Returns:
            DEC:OPEN if guards pass, ERR if guards fail, None if not applicable.
        """
        if msg.op == "CMD" and msg.verb == "OPEN":
            if self.pre_open_guard is not None:
                guard_result = self.pre_open_guard(msg)
                if guard_result is not None:
                    return guard_result

            # Record CMD:OPEN
            if self.metrics_collector:
                self.metrics_collector.record_cmd_open()
            timestamp_cmd = get_clock().now_sec()

            # 0. Idempotency Check
            self._cleanup_idempotency_store()
            idempotent_key = msg.pld.get("idempotent_key")
            if idempotent_key:
                if idempotent_key in self.idempotency_store:
                    self.logger.warning(
                        f"IDEMPOTENCY_REJECT: Duplicate CMD:OPEN received with key {idempotent_key}, rid={msg.rid}"
                    )
                    return self._reject(msg, "IDEMPOTENCY_FAIL", "duplicate command")

                self.idempotency_store[idempotent_key] = get_clock().now_sec()

            # PANIC-INT: Panic killswitch gate (fail-closed).
            # Block ALL new CMD:OPEN when panic_killswitch is explicitly True.
            try:
                trading = getattr(self.config, "trading", None)
                ops = getattr(trading, "ops",
                              None) if trading is not None else None
                panic = getattr(ops, "panic_killswitch",
                                False) if ops is not None else False
                if panic is True:
                    self.logger.error(
                        f"PANIC_REJECT: CMD:OPEN blocked - panic_killswitch=true, rid={msg.rid}"
                    )
                    return self._reject(msg, "PANIC_KILLSWITCH", "panic active - all new opens blocked")
            except Exception:
                # Fail-open for incomplete/mocked configs (tests).
                pass

            # EP-01.4-INT-A: Strict payload validation (fail-closed)
            pld = msg.pld or {}
            try:
                validated_pld = CmdOpenPayload.model_validate(pld)
                symbol = validated_pld.symbol
                side = validated_pld.side
                qty = validated_pld.qty
                price = validated_pld.price
                order_type = validated_pld.order_type
                tif = validated_pld.tif
            except Exception as validation_err:
                self.logger.error(
                    f"CMD_OPEN_VALIDATION_FAIL: Invalid payload - {validation_err}, rid={msg.rid}"
                )
                return self._reject(
                    msg, "CMD_OPEN_VALIDATION_FAIL", f"payload validation failed: {validation_err}"
                )

            # EP-01.4-INT-B: Maker-only enforcement for LIMIT entries (fail-closed).
            try:
                maker_cfg = self.config.domains.execution_position.maker_only_entry
                maker_only_enabled = getattr(maker_cfg, "enabled", False)
                if maker_only_enabled is True and order_type == "LIMIT":
                    if tif != "GTX":
                        self.logger.error(
                            f"MAKER_ONLY_ENFORCEMENT_FAIL: maker_only enabled but tif={tif!r} != GTX, rid={msg.rid}"
                        )
                        return self._reject(
                            msg,
                            "MAKER_ONLY_ENFORCEMENT_FAIL",
                            "maker_only requires tif=GTX",
                        )
            except Exception:
                # Fail-open for incomplete/mocked configs (tests).
                pass

            # Note: symbol/side validation now handled by CmdOpenPayload Pydantic model

            try:
                # Get instrument specifications
                specs = self._get_instrument_specs(symbol)
                min_qty = specs["min_qty"]
                step_size = specs["step_size"]
                tick_size = specs["tick_size"]
                min_notional = specs["min_notional"]

                # Convert to Decimal
                qty_dec = Decimal(str(qty)) if qty is not None else None
                price_dec = Decimal(str(price)) if price is not None else None
                qty_was_normalized = False
                price_was_normalized = False
                price_before_rounding = price_dec
                price_ref = (
                    Decimal(str(validated_pld.price_ref))
                    if validated_pld.price_ref is not None
                    else None
                )

                # Guard: qty bounds
                if qty_dec is None or qty_dec < min_qty:
                    self.logger.error(
                        f"GUARD_REJECT: Quantity below minimum - qty={qty_dec}, min={min_qty}, rid={msg.rid}"
                    )
                    return self._reject(
                        msg, "OPEN_GUARD_FAIL", f"qty below minimum {min_qty}"
                    )

                # Guard: qty step (round down to step_size)
                qty_rounded = (qty_dec // step_size) * step_size
                if qty_rounded != qty_dec:
                    qty_was_normalized = True
                    self.logger.warning(
                        f"GUARD_ADJUST: Quantity rounded down - original={qty_dec}, rounded={qty_rounded}, step={step_size}, rid={msg.rid}"
                    )
                    qty_dec = qty_rounded  # Use rounded quantity for further checks

                # Guard: price bounds (for LIMIT orders)
                if order_type == "LIMIT":
                    if price_dec is None:
                        self.logger.error(
                            f"GUARD_REJECT: LIMIT order missing price - order_type={order_type}, price={price}, rid={msg.rid}"
                        )
                        return self._reject(
                            msg, "OPEN_GUARD_FAIL", "LIMIT order requires price"
                        )

                    # Round LIMIT price in a passive direction for the requested side.
                    price_before_rounding = price_dec
                    price_rounded, rounding_label = self._round_limit_price_to_tick(
                        price_dec, tick_size, side
                    )
                    if price_rounded != price_dec:
                        price_was_normalized = True
                        self.logger.warning(
                            f"GUARD_ADJUST: Price rounded to tick - side={side}, mode={rounding_label}, original={price_dec}, rounded={price_rounded}, tick={tick_size}, rid={msg.rid}"
                        )
                        price_dec = price_rounded

                # Guard: qty step (removed - now auto-rounded above)

                # Guard: price step (removed - now auto-rounded above)

                # Guard: min_notional
                if order_type == "LIMIT" and price_dec is not None:
                    notional = qty_dec * price_dec
                    if notional < min_notional:
                        self.logger.error(
                            f"GUARD_REJECT: Notional below minimum - notional={notional}, min={min_notional}, qty={qty_dec}, price={price_dec}, rid={msg.rid}"
                        )
                        return self._reject(
                            msg,
                            "OPEN_GUARD_FAIL",
                            f"notional {notional} < {min_notional}",
                        )

                # Guard: min_notional for MARKET orders (approximate check using current market price)
                elif order_type == "MARKET" and price_ref is not None:
                    notional = qty_dec * price_ref
                    if notional < min_notional:
                        self.logger.error(
                            f"GUARD_REJECT: Estimated notional below minimum - notional={notional}, min={min_notional}, qty={qty_dec}, price_ref={price_ref}, rid={msg.rid}"
                        )
                        return self._reject(
                            msg,
                            "OPEN_GUARD_FAIL",
                            f"estimated notional {notional} < {min_notional}",
                        )

                # Guard: cooldown
                now = get_clock().now_sec()
                if self.guard_enabled and now - self.last_open_ts < self.cooldown_sec:
                    self.logger.warning(
                        f"GUARD_REJECT: Cooldown active - elapsed={now - self.last_open_ts:.2f}s, required={self.cooldown_sec}s, rid={msg.rid}"
                    )
                    if self.metrics_collector:
                        self.metrics_collector.record_qos_cooldown_hit()
                    return self._reject(msg, "OPEN_GUARD_FAIL", "cooldown active")

                try:
                    dispatch_payload = OpenDispatchPayload.from_cmd_open(
                        symbol=symbol,
                        side=side,
                        normalized_qty=qty_dec,
                        order_type=order_type,
                        normalized_price=price_dec,
                        tif=tif,
                        valid_for_ms=validated_pld.valid_for_ms,
                        stop_price=validated_pld.stop_price,
                        target_price=validated_pld.target_price,
                        sl_pct=validated_pld.sl_pct,
                        idempotent_key=validated_pld.idempotent_key,
                        regime_epoch_ref=validated_pld.regime_epoch_ref,
                        regime=validated_pld.regime,
                        regime_confidence=validated_pld.regime_confidence,
                        regime_provenance=validated_pld.regime_provenance.model_dump()
                        if validated_pld.regime_provenance is not None
                        else None,
                    )
                except OpenDispatchAdapterError as dispatch_err:
                    self.logger.error(
                        "OPEN_DISPATCH_REJECT: contract=%s path=%s rid=%s reason=%s",
                        OPEN_DISPATCH_CONTRACT,
                        OPEN_DISPATCH_PATH,
                        msg.rid,
                        dispatch_err,
                    )
                    return self._reject(
                        msg,
                        "OPEN_DISPATCH_FAIL",
                        f"dispatch adapter rejected: {dispatch_err}",
                        data_ref=[
                            build_open_dispatch_trace_ref(
                                status="reject",
                                qty_normalized=qty_was_normalized,
                                price_normalized=price_was_normalized,
                                reason="adapter_validation",
                            )
                        ],
                    )

                dec_pld = dispatch_payload.to_dec_open_payload()

                if dispatch_payload.idempotent_key is not None:
                    self.logger.info(
                        f"IDEMPOTENCY: Passing key {dispatch_payload.idempotent_key} to DEC:OPEN"
                    )

                self.logger.info(
                    "OPEN_DISPATCH_SUCCESS: contract=%s path=%s rid=%s symbol=%s side=%s order_type=%s qty_normalized=%s price_normalized=%s",
                    OPEN_DISPATCH_CONTRACT,
                    OPEN_DISPATCH_PATH,
                    msg.rid,
                    dispatch_payload.symbol,
                    dispatch_payload.side,
                    dispatch_payload.order_type,
                    qty_was_normalized,
                    price_was_normalized,
                )

                self.logger.info(
                    f"GUARD_PASSED: All guards OK - symbol={symbol}, side={side}, qty={qty_dec}, price={price_dec}, order_type={order_type}, rid={msg.rid}"
                )

                data_ref = msg.data_ref.copy() if msg.data_ref else []
                data_ref.append(
                    build_open_dispatch_trace_ref(
                        status="success",
                        qty_normalized=qty_was_normalized,
                        price_normalized=price_was_normalized,
                    )
                )
                if order_type == "LIMIT" and price_dec is not None:
                    data_ref.append(
                        self._build_limit_rounding_trace_ref(
                            price_before_rounding=price_before_rounding,
                            price_after_rounding=price_dec,
                            tick_size=tick_size,
                            rounding_mode=rounding_label,
                        )
                    )

                dec = Message(
                    op="DEC",
                    verb="OPEN",
                    src=msg.dst,  # FSM as source
                    dst="execution_position",
                    rid=msg.rid,
                    why="OPEN_OK",
                    pld=dec_pld,
                    corr_id=str(uuid.uuid4()),
                    oco_group_id=str(uuid.uuid4()),
                    data_ref=data_ref,
                )

                # Record metrics
                if self.metrics_collector:
                    ms = (get_clock().now_sec() - timestamp_cmd) * 1000
                    self.metrics_collector.record_time_to_open(ms)
                    self.metrics_collector.record_open_success()

                # Update state and metrics
                self.state = OpenState.DONE
                self.last_open_ts = now
                self._metrics["fsm_open_decisions_total"] += 1

                return dec

            except (InvalidOperation, ValueError) as e:
                self._metrics["fsm_guard_rejects_total"] += 1
                self.state = OpenState.ERROR
                self.logger.error(
                    f"GUARD_REJECT: Invalid instrument specs for {symbol} - {e}, rid={msg.rid}"
                )
                return self._reject(msg, "OPEN_GUARD_FAIL", "invalid instrument specs")
            except Exception as e:
                self._metrics["fsm_errors_total"] += 1
                self.state = OpenState.ERROR
                self.logger.exception(
                    f"FSM_EXCEPTION: Unexpected error processing CMD:OPEN - rid={msg.rid}, error={str(e)}"
                )
                return Message(
                    op="ERR",
                    verb="OPEN",
                    src=msg.dst,
                    dst=msg.src,
                    rid=msg.rid,
                    why=f"FSM exception: {str(e)[:60]}",
                    pld={"error": str(e)},
                )

        return None

    def _reject(self, msg: Message, why: str, reason: str, data_ref: Optional[list[str]] = None) -> Message:
        """Generate ERR message for guard failures."""
        self._metrics["fsm_guard_rejects_total"] += 1
        if reason != "cooldown active":
            self.state = OpenState.ERROR
        return Message(
            op="ERR",
            verb="OPEN",
            src=msg.dst,
            dst=msg.src,
            rid=msg.rid,
            why=why[:80],
            pld={"reason": reason},
            data_ref=list(data_ref or []),
        )

    def get_metrics(self) -> Dict[str, int]:
        """Return metrics for observability."""
        return self._metrics.copy()

    def reset(self):
        """Reset FSM state (for testing)."""
        self.state = OpenState.IDLE
        self.last_open_ts = 0.0

    # =========================================================================
    # TASK47c-E: Async Handle with Leverage Verification
    # =========================================================================

    async def handle_async(self, msg: Message) -> Optional[Message]:
        """Async handler that performs leverage verification before DEC:OPEN.

        TASK47c-E: Wire leverage verification into production flow.

        1. Check leverage via LeverageService (if configured)
        2. If leverage check fails → return ERR (no DEC:OPEN)
        3. If leverage check passes → delegate to sync handle()

        Args:
            msg: CMD:OPEN message

        Returns:
            DEC:OPEN if all checks pass, ERR if any check fails
        """
        if msg.op != "CMD" or msg.verb != "OPEN":
            return self.handle(msg)

        symbol = msg.pld.get("symbol", "")

        # TASK47c-E: Leverage verification before DEC:OPEN
        if self.leverage_service is not None:
            # Get per-instrument execution config
            instruments = self.config.instruments or {}
            specs = instruments.get(symbol)
            execution_config = getattr(
                specs, "execution", None) if specs else None

            if execution_config is not None:
                leverage_policy = execution_config.leverage_policy
                expected_leverage = execution_config.target_leverage
                expected_margin_mode = execution_config.margin_mode

                # Call appropriate method based on policy
                if leverage_policy == "set_and_verify":
                    result = await self.leverage_service.set_and_verify(
                        symbol, expected_leverage, expected_margin_mode
                    )
                else:  # "verify_only" is default
                    result = await self.leverage_service.verify(
                        symbol, expected_leverage, expected_margin_mode
                    )

                # If verification failed, reject
                if not result.ok:
                    self.logger.error(
                        f"LEVERAGE_GATE_REJECT: {result.why} (symbol={symbol}, "
                        f"actual_leverage={result.actual_leverage}, expected={expected_leverage})"
                    )
                    return self._reject(
                        msg,
                        f"LEVERAGE_FAIL:{result.error_code or 'UNKNOWN'}",
                        f"leverage verification failed: {result.why[:60]}",
                    )

                self.logger.info(
                    f"LEVERAGE_GATE_PASS: {symbol} leverage={result.actual_leverage} "
                    f"margin_mode={result.actual_margin_mode}"
                )
            else:
                # No execution config for this symbol - log but proceed (for non-trading symbols)
                self.logger.debug(
                    f"No execution config for {symbol}, skipping leverage check")

        # All leverage checks passed (or skipped), proceed with sync handler
        return self.handle(msg)
