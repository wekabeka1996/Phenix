from __future__ import annotations

import logging
import shutil
import socket
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
import yaml

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    get_failure_outcome_total,
    reset_failure_outcomes,
)
from apps.reference.domains.shadow_telemetry import main_bridge
from apps.reference.domains.shadow_telemetry.ipc import (
    ShadowTapDeliveryFailure,
    _classify_shadow_tap_delivery_failure,
)
from apps.reference.domains.shadow_telemetry.main_bridge import (
    ShadowEventTapPublisher,
    ShadowTapDeliveryCriticalError,
    ShadowTapPublishOutcome,
)
from apps.reference.main import build_emit_with_monitoring
from apps.reference.telemetry.metrics import generate_latest


CONFIG_DIR = Path("config/aurora")


def _metric_value(metric_name: str, **labels: str) -> float:
    exposition = generate_latest().decode("utf-8")
    for line in exposition.splitlines():
        if labels:
            if not line.startswith(f"{metric_name}{{"):
                continue
            if not all(f'{key}="{value}"' in line for key, value in labels.items()):
                continue
        elif not line.startswith(f"{metric_name} "):
            continue
        return float(line.rsplit(" ", 1)[1])
    return 0.0


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(CONFIG_DIR, cfg_dir)
    return cfg_dir


def _load_config(
    tmp_path: Path,
    *,
    required_for_mode: bool | None = None,
) -> tuple[Any, Path]:
    cfg_dir = _copy_config_to_tmp(tmp_path)
    if required_for_mode is not None:
        domains_path = cfg_dir / "domains.yaml"
        domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
        domains["shadow_telemetry"]["required_for_mode"] = required_for_mode
        domains_path.write_text(
            yaml.safe_dump(domains, sort_keys=False, allow_unicode=True),
            encoding="utf-8",
        )
    return ConfigLoader(config_dir=cfg_dir).load_config(), cfg_dir


class _FakeTapClient:
    instances: list["_FakeTapClient"] = []

    def __init__(
        self,
        *,
        endpoint: str,
        queue_maxsize: int,
        overflow_policy: str,
        stop_timeout_ms: int,
        logger: logging.Logger | None = None,
        name: str = "shadow_event_tap_client",
        failure_reporter=None,
    ) -> None:
        self.endpoint = endpoint
        self.queue_maxsize = int(queue_maxsize)
        self.overflow_policy = overflow_policy
        self.stop_timeout_ms = int(stop_timeout_ms)
        self.logger = logger
        self.name = name
        self.failure_reporter = failure_reporter
        self.started = False
        self.stopped = False
        self.probe_failure: ShadowTapDeliveryFailure | None = None
        self.enqueue_results: list[bool] = []
        self._last_failure: ShadowTapDeliveryFailure | None = None
        self._failure_count = 0
        self._queue_depth = 0
        _FakeTapClient.instances.append(self)

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def probe_endpoint(self, timeout_sec: float = 0.25) -> ShadowTapDeliveryFailure | None:
        return self.probe_failure

    def queue_depth(self) -> int:
        return int(self._queue_depth)

    def enqueue(self, payload: dict[str, Any]) -> bool:
        if self.enqueue_results:
            return self.enqueue_results.pop(0)
        return True

    def mark_delivery_failure(self, failure: ShadowTapDeliveryFailure) -> None:
        self._failure_count += 1
        self._last_failure = failure

    def last_delivery_failure(self) -> ShadowTapDeliveryFailure | None:
        return self._last_failure

    def delivery_failure_count(self) -> int:
        return int(self._failure_count)


def _build_publisher(
    monkeypatch,
    tmp_path: Path,
    *,
    required_for_mode: bool | None = None,
) -> tuple[ShadowEventTapPublisher, _FakeTapClient]:
    config, _cfg_dir = _load_config(
        tmp_path, required_for_mode=required_for_mode)
    monkeypatch.setattr(main_bridge, "JsonlTcpQueueClient", _FakeTapClient)
    _FakeTapClient.instances.clear()
    publisher = ShadowEventTapPublisher(
        config.domains.shadow_telemetry,
        logger=logging.getLogger("tests.shadow_tap"),
    )
    assert _FakeTapClient.instances, "fake client not constructed"
    return publisher, _FakeTapClient.instances[-1]


def test_shadow_tap_uses_configured_endpoint_from_yaml(monkeypatch, tmp_path: Path) -> None:
    publisher, client = _build_publisher(monkeypatch, tmp_path)

    assert client.endpoint == publisher._endpoint
    assert client.endpoint == "tcp://127.0.0.1:7101"


def test_shadow_tap_start_records_endpoint_unavailable_and_remains_nonfatal_when_not_required(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    reset_failure_outcomes()
    publisher, client = _build_publisher(
        monkeypatch, tmp_path, required_for_mode=False)
    client.probe_failure = ShadowTapDeliveryFailure(
        failure_class="endpoint_unavailable",
        phase="startup",
        error_type="ConnectionRefusedError",
        error_message="connection refused",
        endpoint=client.endpoint,
    )

    with caplog.at_level(logging.WARNING, logger=publisher.logger.name):
        publisher.start()

    assert client.started is True
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code=FailureReasonCode.BRIDGE_UNAVAILABLE,
    ) == 1
    assert _metric_value(
        "shadow_tap_delivery_failures_total",
        component="shadow_event_tap_client",
        failure_class="endpoint_unavailable",
        required_for_mode="false",
    ) == 1.0
    assert any(
        "endpoint_unavailable" in record.message for record in caplog.records)
    assert any("degraded_observability" in record.message or "Shadow event tap delivery degraded" in record.message for record in caplog.records)


def test_shadow_tap_start_fails_closed_when_required_and_endpoint_unavailable(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    reset_failure_outcomes()
    publisher, client = _build_publisher(
        monkeypatch, tmp_path, required_for_mode=True)
    client.probe_failure = ShadowTapDeliveryFailure(
        failure_class="endpoint_unavailable",
        phase="startup",
        error_type="ConnectionRefusedError",
        error_message="connection refused",
        endpoint=client.endpoint,
    )

    with caplog.at_level(logging.CRITICAL, logger=publisher.logger.name):
        with pytest.raises(ShadowTapDeliveryCriticalError):
            publisher.start()

    assert client.started is False
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code=FailureReasonCode.BRIDGE_UNAVAILABLE,
    ) == 1
    assert _metric_value(
        "shadow_tap_delivery_failures_total",
        component="shadow_event_tap_client",
        failure_class="endpoint_unavailable",
        required_for_mode="true",
    ) == 1.0
    assert any(
        "required_for_mode=true" in record.message.lower()
        for record in caplog.records
    )


def test_shadow_tap_queue_overflow_is_counted_and_nonfatal_when_not_required(
    monkeypatch,
    tmp_path: Path,
) -> None:
    reset_failure_outcomes()
    publisher, client = _build_publisher(
        monkeypatch, tmp_path, required_for_mode=False)
    client.enqueue_results = [False]

    outcome = publisher.publish(
        event_name="EVT:FEATURES_CALCULATED",
        payload={"symbol": "XRPUSDT"},
        why="shadow_tap_overflow_test",
    )

    assert outcome.accepted is False
    assert outcome.fatal is False
    assert outcome.degraded_observability is True
    assert outcome.failure_class == "queue_overflow"
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.DEGRADED_OBSERVABILITY,
        reason_code=FailureReasonCode.BRIDGE_UNAVAILABLE,
    ) == 1
    assert _metric_value(
        "shadow_tap_delivery_failures_total",
        component="shadow_event_tap_client",
        failure_class="queue_overflow",
        required_for_mode="false",
    ) == 1.0


def test_shadow_tap_publish_success_remains_clean(
    monkeypatch,
    tmp_path: Path,
) -> None:
    reset_failure_outcomes()
    publisher, client = _build_publisher(
        monkeypatch, tmp_path, required_for_mode=False)

    publisher.start()
    outcome = publisher.publish(
        event_name="EVT:FEATURES_CALCULATED",
        payload={"symbol": "XRPUSDT"},
        why="shadow_tap_success_test",
    )

    assert client.started is True
    assert outcome.accepted is True
    assert outcome.fatal is False
    assert outcome.degraded_observability is False
    assert outcome.failure_class is None
    assert _metric_value("shadow_tap_delivery_failures_total") == 0.0


def test_shadow_tap_repeated_failures_are_bounded(
    monkeypatch,
    tmp_path: Path,
    caplog,
) -> None:
    reset_failure_outcomes()
    publisher, _client = _build_publisher(
        monkeypatch, tmp_path, required_for_mode=False)
    publisher._delivery_failure_log_every_n = 1_000
    publisher._delivery_failure_log_interval_sec = 9_999.0
    failure_metric_before = _metric_value(
        "shadow_tap_delivery_failures_total",
        component="shadow_event_tap_client",
        failure_class="endpoint_unavailable",
        required_for_mode="false",
    )
    suppressed_metric_before = _metric_value(
        "shadow_tap_delivery_log_suppressed_total",
        component="shadow_event_tap_client",
        failure_class="endpoint_unavailable",
    )

    failure = ShadowTapDeliveryFailure(
        failure_class="endpoint_unavailable",
        phase="startup",
        error_type="ConnectionRefusedError",
        error_message="connection refused",
        endpoint="tcp://127.0.0.1:7101",
    )

    with caplog.at_level(logging.WARNING, logger=publisher.logger.name):
        for _idx in range(5):
            publisher._record_delivery_failure(
                failure,
                source="startup",
                required_for_mode=False,
            )

    failure_logs = [
        record for record in caplog.records
        if "Shadow event tap delivery" in record.message
    ]
    assert len(failure_logs) == 1
    assert _metric_value(
        "shadow_tap_delivery_failures_total",
        component="shadow_event_tap_client",
        failure_class="endpoint_unavailable",
        required_for_mode="false",
    ) == failure_metric_before + 5.0
    assert _metric_value(
        "shadow_tap_delivery_log_suppressed_total",
        component="shadow_event_tap_client",
        failure_class="endpoint_unavailable",
    ) == suppressed_metric_before + 4.0


@pytest.mark.parametrize(
    "exc, phase, expected",
    [
        (ConnectionRefusedError(111, "Connection refused"),
         "startup", "endpoint_unavailable"),
        (socket.timeout("timed out"), "connect", "timeout"),
        (OSError("connect failed"), "connect", "connect_failed"),
        (BrokenPipeError("broken pipe"), "send", "send_failed"),
        (RuntimeError("boom"), "send", "unknown"),
    ],
)
def test_shadow_tap_delivery_failure_classification_helper(
    exc: BaseException,
    phase: str,
    expected: str,
) -> None:
    failure = _classify_shadow_tap_delivery_failure(
        exc,
        phase=phase,
        endpoint="tcp://127.0.0.1:7101",
    )
    assert failure.failure_class == expected
    assert failure.endpoint == "tcp://127.0.0.1:7101"
    assert failure.phase == phase


def test_shadow_tap_wrapper_blocks_required_mode_before_emit() -> None:
    entropy_monitor = MagicMock()
    original_emit = MagicMock(return_value="ok")

    class _FatalPublisher:
        required_for_mode = True

        def preflight(self, event_name: str) -> ShadowTapPublishOutcome:
            return ShadowTapPublishOutcome(
                accepted=False,
                fatal=True,
                degraded_observability=True,
                failure_class="endpoint_unavailable",
                endpoint="tcp://127.0.0.1:7101",
                reason="prior_delivery_failure",
            )

        def publish(self, **kwargs: Any) -> ShadowTapPublishOutcome:
            raise AssertionError(
                "publish should not be called when preflight fails")

    wrapped_emit = build_emit_with_monitoring(
        original_emit=original_emit,
        entropy_monitor=entropy_monitor,
        shadow_event_tap_getter=lambda: _FatalPublisher(),
        logger=MagicMock(),
    )

    with pytest.raises(ShadowTapDeliveryCriticalError):
        wrapped_emit("EVT:FEATURES_CALCULATED", payload={"x": 1}, why="test")

    original_emit.assert_not_called()
    entropy_monitor.track_event.assert_called_once()


def test_shadow_tap_wrapper_remains_nonfatal_when_not_required(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config, _cfg_dir = _load_config(tmp_path, required_for_mode=False)
    monkeypatch.setattr(main_bridge, "JsonlTcpQueueClient", _FakeTapClient)
    _FakeTapClient.instances.clear()
    publisher = ShadowEventTapPublisher(
        config.domains.shadow_telemetry, logger=MagicMock())
    client = _FakeTapClient.instances[-1]
    client.enqueue_results = [False]

    original_emit = MagicMock(return_value="ok")
    entropy_monitor = MagicMock()
    wrapped_emit = build_emit_with_monitoring(
        original_emit=original_emit,
        entropy_monitor=entropy_monitor,
        shadow_event_tap_getter=lambda: publisher,
        logger=MagicMock(),
    )

    result = wrapped_emit("EVT:FEATURES_CALCULATED",
                          payload={"x": 1}, why="test")

    assert result == "ok"
    original_emit.assert_called_once()
    assert entropy_monitor.track_event.call_count == 1


def test_build_emit_with_monitoring_canonicalizes_neocortex_shadow_event_message() -> None:
    original_emit = MagicMock(return_value="ok")
    entropy_monitor = MagicMock()
    wrapped_emit = build_emit_with_monitoring(
        original_emit=original_emit,
        entropy_monitor=entropy_monitor,
        shadow_event_tap_getter=lambda: None,
        logger=MagicMock(),
    )

    payload = {
        "decision_id": "decision-1",
        "rid": "rid-1",
        "symbol": "BTCUSDT",
        "action": "ALLOW",
    }

    result = wrapped_emit(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload=payload,
        why="shadow_protocol_alignment",
        rid="rid-1",
    )

    assert result == "ok"
    original_emit.assert_called_once_with(
        "SHADOW:NEOCORTEX_DECISION_LOGGED",
        payload,
        "shadow_protocol_alignment",
        data_ref=None,
        rid="rid-1",
    )

    tracked_message = entropy_monitor.track_event.call_args.args[0]
    assert tracked_message.op == "EVT"
    assert tracked_message.verb == "NEOCORTEX_DECISION_LOGGED"
    assert tracked_message.rid == "rid-1"
    assert tracked_message.pld == payload
