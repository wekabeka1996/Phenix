#!/usr/bin/env python3
"""Neocortex standalone Stage 0.3 shadow-baseline entry point."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
import uuid
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Literal, Optional

from pydantic import ValidationError

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.authority_bridge import (
    NeocortexAuthorityBridge,
)
from apps.reference.domains.decision_making.schemas.control_decision import (
    ControlDecisionAction,
    ControlDecisionRequest,
    ControlDecisionResponse,
)
from apps.reference.domains.neocortex.config_models import NeocortexConfig, load_config
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    record_failure_outcome,
)
from apps.reference.domains.neocortex.contracts.observation_envelope import (
    ObservationEnvelope,
)
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
)
from apps.reference.domains.neocortex.logic.brain.baseline_inference import (
    BaselineArtifactError,
    BaselineController,
    BaselinePredictionError,
    DEFAULT_BASELINE_MODEL_PATH,
)
from apps.reference.domains.neocortex.logic.gates import (
    ShadowGateEvaluator,
    ShadowGateViolationError,
)
from apps.reference.domains.neocortex.logic.ingest.state_aggregator_v2 import (
    NeocortexStateAggregator,
    NeocortexStateSnapshot,
)
from apps.reference.domains.shadow_telemetry.ipc import JsonlTcpServer
from vfoundation.core.protocol import Message, truncate_why
from vfoundation.dr import wal


REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_NEOCORTEX_CONFIG_DIR = Path(__file__).resolve().parent / "config"
DEFAULT_AURORA_CONFIG_DIR = REPO_ROOT / "config" / "aurora"
SHADOW_DECISION_EVENT = "SHADOW:NEOCORTEX_DECISION_LOGGED"

ShadowEmitFn = Callable[[str, dict[str, object], str], None]


@dataclass(frozen=True, slots=True)
class AuroraShadowRuntimeConfig:
    enforcement_mode: Literal["shadow"]
    event_tap_endpoint: str


class FatalStartupError(RuntimeError):
    def __init__(self, reason_code: str, message: str):
        self.reason_code = str(reason_code).strip().upper() or "UNKNOWN"
        super().__init__(message)


def _now_ms() -> int:
    return int(time.time() * 1000)


def _raise_fatal_startup(
    reason_code: str,
    *,
    location: str,
    error: Exception,
) -> None:
    record_failure_outcome(
        FailureOutcomeTaxonomy.FATAL_STARTUP,
        reason_code,
        location=location,
        detail=type(error).__name__,
    )
    raise FatalStartupError(reason_code, f"{location}: {error}") from error


def _first_text(*values: Any, default: str | None = None) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return default


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return str(value)


def setup_logging(config: NeocortexConfig) -> logging.Logger:
    """Configure standalone Neocortex logging from the domain config."""

    log_format = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    if config.system.log_to_file:
        config.system.data_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            RotatingFileHandler(
                config.system.data_dir / "neocortex.log",
                maxBytes=20 * 1024 * 1024,
                backupCount=100,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=str(config.system.log_level),
        format=log_format,
        handlers=handlers,
        force=True,
    )
    return logging.getLogger("neocortex.main")


def evaluate_startup_shadow_gates(
    config: NeocortexConfig,
    *,
    logger: logging.Logger | None = None,
    evaluated_at_ms: int | None = None,
):
    """Evaluate and enforce Neocortex production-shadow startup gates."""

    evaluator = ShadowGateEvaluator()
    report = evaluator.evaluate(config, evaluated_at_ms=evaluated_at_ms)
    if logger is not None:
        logger.info("Neocortex shadow gate report: %s",
                    report.model_dump_json())
    if (
        config.neuro.shadow_gates.startup_enforcement == "strict"
        and report.overall_status != "ready"
    ):
        raise ShadowGateViolationError(report)
    return report


def load_aurora_shadow_runtime_config(
    aurora_config_dir: Path = DEFAULT_AURORA_CONFIG_DIR,
) -> AuroraShadowRuntimeConfig:
    """Load the Aurora SSOT and fail unless Neocortex authority is shadow-only."""

    aurora_config = ConfigLoader(Path(aurora_config_dir)).load_config()
    mode = str(
        aurora_config.domains.decision_making.neocortex_enforcement_mode
    ).strip()
    if mode != "shadow":
        raise RuntimeError(
            "Standalone Neocortex refuses to boot unless "
            "decision_making.neocortex_enforcement_mode='shadow'"
        )

    shadow_cfg = aurora_config.domains.shadow_telemetry
    if not bool(shadow_cfg.enabled):
        raise RuntimeError(
            "Standalone Neocortex requires shadow_telemetry.enabled=true")
    if str(shadow_cfg.ingest.source) != "ipc_tap":
        raise RuntimeError(
            "Standalone Neocortex requires shadow_telemetry.ingest.source='ipc_tap'")

    return AuroraShadowRuntimeConfig(
        enforcement_mode="shadow",
        event_tap_endpoint=str(shadow_cfg.ingest.ipc_endpoint),
    )


def append_shadow_decision_to_wal(event_name: str, payload: dict[str, object], why: str) -> None:
    """Default standalone sink: append a shadow decision event to the WAL."""

    if event_name != SHADOW_DECISION_EVENT:
        raise ValueError(f"unexpected shadow event: {event_name!r}")

    rid = str(payload.get("rid") or payload.get(
        "decision_id") or f"neo-{_now_ms()}")
    message = Message(
        op="EVT",
        verb="NEOCORTEX_DECISION_LOGGED",
        src="neocortex_standalone",
        dst="shadow_telemetry_ledger",
        rid=rid,
        pld={"event_name": event_name, **payload},
        why=truncate_why(why, 80) or "neocortex_shadow_decision",
    )
    try:
        wal.append(message.model_dump())
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        record_failure_outcome(
            FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
            "HANDLER_FAILURE",
            location="neocortex.main.append_shadow_decision_to_wal",
            detail=type(error).__name__,
        )
        logging.getLogger("neocortex.main").exception(
            "Failed to append %s to WAL rid=%s", event_name, rid, exc_info=error
        )


class NeocortexShadowRuntime:
    """Stage 0.3 runtime: causal state aggregation plus dumb-baseline shadow logging."""

    def __init__(
        self,
        *,
        config: NeocortexConfig,
        aggregator: NeocortexStateAggregator,
        baseline_controller: BaselineController,
        shadow_emit_fn: ShadowEmitFn,
        logger: logging.Logger,
    ) -> None:
        self.config = config
        self.aggregator = aggregator
        self.baseline_controller = baseline_controller
        self.enforcement_mode: Literal["shadow"] = "shadow"
        self.logger = logger
        self._feature_names = list(config.ingest.feature_list)
        self._shadow_emit_fn = shadow_emit_fn
        self.authority_bridge = NeocortexAuthorityBridge(
            baseline_controller=baseline_controller,
            enforcement_mode="shadow",
            shadow_emit_fn=self._emit_shadow_decision,
            logger=logger.getChild("authority"),
        )
        self.events_seen = 0
        self.snapshots_emitted = 0
        self.decisions_logged = 0
        self.shadow_fallbacks = 0

    async def handle_event_frame(
        self, frame: dict[str, object]
    ) -> ControlDecisionResponse | None:
        """Consume one shadow telemetry/WAL frame and emit a shadow decision if it ticks."""

        self.events_seen += 1
        event = self._normalize_event_frame(frame)
        snapshot = self.aggregator.ingest_event(event)
        if snapshot is None:
            return None
        if not snapshot.trainable:
            record_failure_outcome(
                FailureOutcomeTaxonomy.BLOCK,
                "NON_CAUSAL_TIME" if not snapshot.event_time_is_causal else "MISSING_REQUIRED_STATE",
                location="neocortex.main.NeocortexShadowRuntime.handle_event_frame",
                detail=snapshot.dataset_visibility,
            )
            self.logger.warning(
                "Skipping non-trainable snapshot symbol=%s trigger=%s visibility=%s",
                snapshot.symbol,
                snapshot.trigger_event_type,
                snapshot.dataset_visibility,
            )
            return None

        self.snapshots_emitted += 1
        request = self._build_control_request(snapshot, frame)
        response = await self.authority_bridge.request_authority(request, timeout_ms=50)
        if response.action == ControlDecisionAction.BLOCK:
            raise RuntimeError(
                "shadow runtime invariant breach: hard BLOCK returned")
        if response.action == ControlDecisionAction.FALLBACK:
            self.shadow_fallbacks += 1
        if response.shadow_logged:
            self.decisions_logged += 1
        return response

    def _emit_shadow_decision(self, event_name: str, payload: dict[str, object], why: str) -> None:
        if event_name != SHADOW_DECISION_EVENT:
            raise ValueError(f"unexpected shadow event: {event_name!r}")
        self._shadow_emit_fn(event_name, payload, why)

    def _normalize_event_frame(self, frame: dict[str, object]) -> dict[str, object]:
        payload = frame.get("payload") or frame.get("pld")
        payload_dict = dict(payload) if isinstance(
            payload, dict) else dict(frame)
        event_name = _first_text(
            frame.get("event_name"),
            frame.get("event_type"),
            payload_dict.get("event_type"),
            frame.get("verb"),
            default="UNKNOWN",
        )
        if frame.get("op") == "EVT" and event_name and not event_name.upper().startswith("EVT:"):
            event_name = f"EVT:{event_name}"

        if not any(
            key in payload_dict
            for key in ("event_ts_ms", "timestamp_ms", "timestamp", "ts_ms", "ts")
        ):
            captured_ts_ms = frame.get("captured_ts_ms") or frame.get("ts")
            if captured_ts_ms is not None:
                payload_dict["event_ts_ms"] = captured_ts_ms
                payload_dict["time_provenance"] = CausalTimeProvenance.CAPTURED_WALLCLOCK.value

        if not any(
            key in payload_dict
            for key in ("time_provenance", "causal_time_provenance", "event_time_provenance")
        ):
            payload_dict["time_provenance"] = (
                CausalTimeProvenance.BAR_END.value
                if event_name in {"BAR_CLOSED", "EVT:BAR_CLOSED"}
                else CausalTimeProvenance.AURORA_EVENT.value
            )

        normalized = dict(frame)
        normalized["event_type"] = event_name
        normalized["payload"] = payload_dict
        return normalized

    def _build_control_request(
        self, snapshot: NeocortexStateSnapshot, source_frame: dict[str, object]
    ) -> ControlDecisionRequest:
        payload = source_frame.get("payload") or source_frame.get("pld")
        payload_dict = dict(payload) if isinstance(payload, dict) else {}
        frame_id = _first_text(source_frame.get("frame_id"))
        decision_id = _first_text(
            payload_dict.get("decision_id"),
            payload_dict.get("intent_id"),
            payload_dict.get("idempotency_key"),
            frame_id,
            default=f"neo-{uuid.uuid4().hex}",
        )
        assert decision_id is not None
        rid = _first_text(
            payload_dict.get("rid"),
            payload_dict.get("request_id"),
            source_frame.get("rid"),
            decision_id,
            default=decision_id,
        )
        assert rid is not None
        proposed_action = _first_text(
            payload_dict.get("proposed_action"),
            payload_dict.get("action"),
            payload_dict.get("side"),
            default="OBSERVE",
        )
        assert proposed_action is not None

        now_ms = _now_ms()
        deadline_ms = int(payload_dict.get("deadline_ms") or now_ms + 50)
        if deadline_ms <= now_ms:
            deadline_ms = now_ms + 50

        return ControlDecisionRequest(
            decision_id=decision_id,
            rid=rid,
            symbol=snapshot.symbol,
            proposed_action=proposed_action,
            deadline_ms=deadline_ms,
            decision_basis_ts=int(snapshot.tick_ts_ms),
            causal_state_snapshot=self._snapshot_payload(
                snapshot, source_frame),
        )

    def _snapshot_payload(
        self, snapshot: NeocortexStateSnapshot, source_frame: dict[str, object]
    ) -> dict[str, object]:
        feature_values: dict[str, object] = {
            name: _jsonable(snapshot.observation.features_vector[index])
            for index, name in enumerate(self._feature_names)
            if index < len(snapshot.observation.features_vector)
        }
        payload = source_frame.get("payload") or source_frame.get("pld")
        payload_dict = dict(payload) if isinstance(payload, dict) else {}

        return _jsonable(
            {
                "snapshot_contract": "neocortex_state_aggregator_v2",
                "symbol": snapshot.symbol,
                "tick_ts_ms": int(snapshot.tick_ts_ms),
                "trigger_event_type": snapshot.trigger_event_type,
                "feature_event_ts_ms": int(snapshot.feature_event_ts_ms),
                "feature_time_provenance": snapshot.feature_time_provenance.value,
                "regime_event_ts_ms": snapshot.regime_event_ts_ms,
                "portfolio_event_ts_ms": snapshot.portfolio_event_ts_ms,
                "observation": {
                    "mid_price": snapshot.observation.mid_price,
                    "volatility": snapshot.observation.volatility,
                    "obi": snapshot.observation.obi,
                    "features": feature_values,
                    "normalized": bool(snapshot.observation.normalized),
                },
                "neocortex_state": {
                    "state_vector": snapshot.state_vector,
                    "context_vector": snapshot.context_vector,
                    "state_vector_dim": int(len(snapshot.state_vector)),
                },
                "regime_state": {
                    "label": snapshot.regime_label,
                    "confidence": snapshot.regime_confidence,
                },
                "portfolio_position": {
                    "side": snapshot.position_side,
                },
                "intent": {
                    "side": snapshot.intent_side or payload_dict.get("side"),
                    "proposed_action": payload_dict.get("proposed_action")
                    or payload_dict.get("action"),
                    "strategy_id": payload_dict.get("strategy_id"),
                    "quantity": payload_dict.get("quantity"),
                    "reduce_only": payload_dict.get("reduce_only"),
                },
                "source_frame": {
                    "frame_id": source_frame.get("frame_id"),
                    "captured_ts_ms": source_frame.get("captured_ts_ms"),
                    "event_name": source_frame.get("event_name"),
                },
            }
        )


def build_shadow_baseline_runtime(
    *,
    neocortex_config_dir: Path = DEFAULT_NEOCORTEX_CONFIG_DIR,
    aurora_config_dir: Path = DEFAULT_AURORA_CONFIG_DIR,
    model_path: Path = DEFAULT_BASELINE_MODEL_PATH,
    shadow_emit_fn: ShadowEmitFn | None = None,
    logger: logging.Logger | None = None,
) -> tuple[NeocortexShadowRuntime, AuroraShadowRuntimeConfig]:
    """Load configs and fail-fast construct the Stage 0.3 shadow-baseline runtime."""

    try:
        config = load_config(Path(neocortex_config_dir))
    except FileNotFoundError as error:
        _raise_fatal_startup(
            "CONFIG_MISSING",
            location="neocortex.main.build_shadow_baseline_runtime.load_config",
            error=error,
        )
    except (ValidationError, ValueError, TypeError) as error:
        _raise_fatal_startup(
            "CONFIG_INVALID",
            location="neocortex.main.build_shadow_baseline_runtime.load_config",
            error=error,
        )
    runtime_logger = logger or logging.getLogger("neocortex.main")
    evaluate_startup_shadow_gates(config, logger=runtime_logger)
    try:
        aurora_shadow_config = load_aurora_shadow_runtime_config(
            Path(aurora_config_dir)
        )
    except FileNotFoundError as error:
        _raise_fatal_startup(
            "AURORA_CONFIG_MISSING",
            location="neocortex.main.build_shadow_baseline_runtime.load_aurora_shadow_runtime_config",
            error=error,
        )
    except (ValidationError, ValueError, TypeError, RuntimeError) as error:
        _raise_fatal_startup(
            "AURORA_CONFIG_INVALID",
            location="neocortex.main.build_shadow_baseline_runtime.load_aurora_shadow_runtime_config",
            error=error,
        )
    aggregator = NeocortexStateAggregator(
        config.ingest,
        strict_clock=True,
        neocortex_enforcement_mode=aurora_shadow_config.enforcement_mode,
    )
    try:
        baseline_controller = BaselineController(model_path=Path(model_path))
    except (OSError, BaselineArtifactError) as error:
        _raise_fatal_startup(
            "MODEL_ARTIFACT_MISMATCH",
            location="neocortex.main.build_shadow_baseline_runtime.BaselineController",
            error=error,
        )
    except (BaselinePredictionError, ValueError, TypeError) as error:
        _raise_fatal_startup(
            "BASELINE_UNAVAILABLE",
            location="neocortex.main.build_shadow_baseline_runtime.BaselineController",
            error=error,
        )
    runtime = NeocortexShadowRuntime(
        config=config,
        aggregator=aggregator,
        baseline_controller=baseline_controller,
        shadow_emit_fn=shadow_emit_fn or append_shadow_decision_to_wal,
        logger=runtime_logger,
    )
    return runtime, aurora_shadow_config


class NeocortexEventTapServer:
    """Threaded JSONL TCP tap that schedules frame handling onto the asyncio loop."""

    def __init__(
        self,
        *,
        runtime: NeocortexShadowRuntime,
        endpoint: str,
        logger: logging.Logger,
    ) -> None:
        self.runtime = runtime
        self.endpoint = endpoint
        self.logger = logger
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: set[asyncio.Task[ControlDecisionResponse | None]] = set()
        self._server = JsonlTcpServer(
            endpoint=endpoint,
            handler=self._on_frame,
            logger=logger.getChild("ipc"),
            name="neocortex_shadow_event_tap_server",
        )

    def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._server.start()
        self.logger.info(
            "Neocortex shadow event tap listening on %s", self.endpoint)

    def stop(self) -> None:
        self._server.stop()
        for task in list(self._tasks):
            task.cancel()

    def _on_frame(self, frame: dict[str, Any]) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            self.logger.warning(
                "Dropped frame before Neocortex event loop was ready")
            return
        loop.call_soon_threadsafe(self._schedule_frame, frame)

    def _schedule_frame(self, frame: dict[str, Any]) -> None:
        task = asyncio.create_task(self.runtime.handle_event_frame(frame))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(self._log_task_failure)

    def _log_task_failure(self, task: asyncio.Task[ControlDecisionResponse | None]) -> None:
        if task.cancelled():
            return
        error = task.exception()
        if error is not None:
            record_failure_outcome(
                FailureOutcomeTaxonomy.FALLBACK,
                "HANDLER_FAILURE",
                location="neocortex.main.NeocortexEventTapServer._log_task_failure",
                detail=type(error).__name__,
            )
            self.logger.exception(
                "Neocortex frame handling failed", exc_info=error)


async def main_reactor(
    runtime: NeocortexShadowRuntime,
    *,
    event_tap_endpoint: str,
    logger: logging.Logger,
) -> None:
    """Run the standalone Stage 0.3 shadow-baseline process."""

    server = NeocortexEventTapServer(
        runtime=runtime,
        endpoint=event_tap_endpoint,
        logger=logger.getChild("tap"),
    )
    try:
        logger.info("=" * 80)
        logger.info("NEOCORTEX DOMAIN - STAGE 0.3 SHADOW BASELINE")
        logger.info("Enforcement mode: shadow-only")
        logger.info("Model path: %s", runtime.baseline_controller.model_path)
        logger.info("=" * 80)
        server.start()
        while True:
            await asyncio.sleep(10)
            logger.debug(
                "Heartbeat: events=%s snapshots=%s decisions=%s fallbacks=%s",
                runtime.events_seen,
                runtime.snapshots_emitted,
                runtime.decisions_logged,
                runtime.shadow_fallbacks,
            )
    except asyncio.CancelledError:
        logger.info("Neocortex shadow reactor received cancellation")
        raise
    finally:
        server.stop()
        logger.info("Neocortex shadow reactor shutdown complete")


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config-dir", type=Path,
                        default=DEFAULT_NEOCORTEX_CONFIG_DIR)
    parser.add_argument("--aurora-config-dir", type=Path,
                        default=DEFAULT_AURORA_CONFIG_DIR)
    parser.add_argument("--model-path", type=Path,
                        default=DEFAULT_BASELINE_MODEL_PATH)
    parser.add_argument("--event-tap-endpoint", type=str, default=None)
    return parser.parse_args(argv)


async def main(argv: Optional[list[str]] = None) -> None:
    """Application entry point with fail-closed bootstrap."""

    args = _parse_args(argv)
    logger = logging.getLogger("neocortex.main")
    try:
        runtime, aurora_shadow_config = build_shadow_baseline_runtime(
            neocortex_config_dir=args.config_dir,
            aurora_config_dir=args.aurora_config_dir,
            model_path=args.model_path,
            logger=logger,
        )
        logger = setup_logging(runtime.config)
        endpoint = args.event_tap_endpoint or aurora_shadow_config.event_tap_endpoint
        await main_reactor(runtime, event_tap_endpoint=endpoint, logger=logger)
    except ShadowGateViolationError as error:
        record_failure_outcome(
            FailureOutcomeTaxonomy.FATAL_STARTUP,
            "SHADOW_GATE_BLOCK",
            location="neocortex.main.main",
            detail="shadow_gates",
        )
        logger.error("Production-shadow startup blocked: %s",
                     error.report.model_dump_json())
        raise SystemExit(1) from error
    except FatalStartupError as error:
        logger.exception("Fatal Neocortex startup error: %s", error)
        raise SystemExit(1) from error


def run() -> None:
    """Wrapper for asyncio.run with graceful KeyboardInterrupt handling."""

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nReceived KeyboardInterrupt - shutting down gracefully...")
        raise SystemExit(0) from None


if __name__ == "__main__":
    run()
