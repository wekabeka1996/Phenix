from __future__ import annotations

import asyncio
import logging
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

import apps.reference.domains.neocortex.main as neocortex_main
from apps.reference.domains.decision_making.schemas.control_decision import (
    ControlDecisionAction,
)
from apps.reference.domains.neocortex.config_models import load_config as load_neocortex_config
from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    get_failure_outcome_total,
    reset_failure_outcomes,
)
from apps.reference.domains.neocortex.logic.gates import ShadowGateViolationError
from tests.domains.neocortex.test_neocortex_main_bootstrap import (
    _feature_payload,
    _write_baseline_artifact,
)


class _CustomStr:
    def __str__(self) -> str:
        return "custom-value"


@pytest.fixture
def runtime_bundle(tmp_path: Path):
    model_path = tmp_path / "baseline_logreg_v1.pkl"
    _write_baseline_artifact(model_path)
    shadow_events: list[tuple[str, dict, str]] = []
    runtime, _ = neocortex_main.build_shadow_baseline_runtime(
        model_path=model_path,
        shadow_emit_fn=lambda event_name, payload, why: shadow_events.append(
            (event_name, payload, why)
        ),
    )
    return runtime, shadow_events


def test_main_helpers_and_setup_logging(tmp_path: Path) -> None:
    assert neocortex_main._first_text(None, "  ", "alpha") == "alpha"
    assert neocortex_main._first_text(
        None, "  ", default="fallback") == "fallback"

    payload = neocortex_main._jsonable(
        {
            "arr": np.array([1, 2]),
            "nested": {"x": {3}},
            "custom": _CustomStr(),
        }
    )

    assert payload["arr"] == [1, 2]
    assert sorted(payload["nested"]["x"]) == [3]
    assert payload["custom"] == "custom-value"

    args = neocortex_main._parse_args(
        ["--event-tap-endpoint", "tcp://127.0.0.1:7200"]
    )
    assert args.event_tap_endpoint == "tcp://127.0.0.1:7200"

    for log_to_file in (False, True):
        config = SimpleNamespace(
            system=SimpleNamespace(
                log_to_file=log_to_file,
                data_dir=tmp_path,
                log_level="INFO",
            )
        )
        logger = neocortex_main.setup_logging(config)
        assert logger.name == "neocortex.main"

    assert (tmp_path / "neocortex.log").exists()


def test_shadow_gate_and_aurora_loader_paths() -> None:
    ready_config = SimpleNamespace(
        neuro=SimpleNamespace(
            shadow_gates=SimpleNamespace(startup_enforcement="strict")
        )
    )
    ready_report = SimpleNamespace(
        overall_status="ready",
        model_dump_json=lambda: '{"overall_status":"ready"}',
    )
    logger = MagicMock()
    with patch.object(
        neocortex_main.ShadowGateEvaluator,
        "evaluate",
        return_value=ready_report,
    ):
        assert (
            neocortex_main.evaluate_startup_shadow_gates(
                ready_config,
                logger=logger,
                evaluated_at_ms=123,
            )
            is ready_report
        )
    logger.info.assert_called_once()

    not_ready_report = SimpleNamespace(
        overall_status="not_ready",
        blocking_gate_ids=["semantic.manifest_contracts"],
        model_dump_json=lambda: '{"overall_status":"not_ready"}',
    )
    with patch.object(
        neocortex_main.ShadowGateEvaluator,
        "evaluate",
        return_value=not_ready_report,
    ):
        with pytest.raises(ShadowGateViolationError):
            neocortex_main.evaluate_startup_shadow_gates(
                ready_config,
                evaluated_at_ms=123,
            )

    def _aurora_config(
        *, mode: str = "shadow", enabled: bool = True, source: str = "ipc_tap"
    ) -> SimpleNamespace:
        return SimpleNamespace(
            domains=SimpleNamespace(
                decision_making=SimpleNamespace(
                    neocortex_enforcement_mode=mode
                ),
                shadow_telemetry=SimpleNamespace(
                    enabled=enabled,
                    ingest=SimpleNamespace(
                        source=source,
                        ipc_endpoint="tcp://127.0.0.1:7101",
                    ),
                ),
            )
        )

    with patch(
        "apps.reference.domains.neocortex.main.ConfigLoader.load_config",
        return_value=_aurora_config(),
    ):
        runtime_config = neocortex_main.load_aurora_shadow_runtime_config(
            Path("ignored")
        )
    assert runtime_config.enforcement_mode == "shadow"
    assert runtime_config.event_tap_endpoint == "tcp://127.0.0.1:7101"

    for fake_config, match_text in [
        (_aurora_config(mode="live"), "shadow"),
        (_aurora_config(enabled=False), "enabled"),
        (_aurora_config(source="other"), "ipc_tap"),
    ]:
        with patch(
            "apps.reference.domains.neocortex.main.ConfigLoader.load_config",
            return_value=fake_config,
        ):
            with pytest.raises(RuntimeError, match=match_text):
                neocortex_main.load_aurora_shadow_runtime_config(
                    Path("ignored"))


def test_bootstrap_failure_modes_cover_config_and_baseline_errors(tmp_path: Path, monkeypatch) -> None:
    reset_failure_outcomes()

    monkeypatch.setattr(
        neocortex_main,
        "load_config",
        MagicMock(side_effect=FileNotFoundError("missing config")),
    )
    with pytest.raises(neocortex_main.FatalStartupError) as excinfo:
        neocortex_main.build_shadow_baseline_runtime(
            neocortex_config_dir=tmp_path)
    assert excinfo.value.reason_code == "CONFIG_MISSING"

    monkeypatch.setattr(
        neocortex_main,
        "load_config",
        MagicMock(side_effect=ValueError("invalid config")),
    )
    with pytest.raises(neocortex_main.FatalStartupError) as excinfo:
        neocortex_main.build_shadow_baseline_runtime(
            neocortex_config_dir=tmp_path)
    assert excinfo.value.reason_code == "CONFIG_INVALID"

    valid_config = load_neocortex_config(
        Path("apps/reference/domains/neocortex/config"))
    monkeypatch.setattr(neocortex_main, "load_config",
                        MagicMock(return_value=valid_config))
    monkeypatch.setattr(
        neocortex_main,
        "load_aurora_shadow_runtime_config",
        MagicMock(side_effect=RuntimeError("aurora disabled")),
    )
    with pytest.raises(neocortex_main.FatalStartupError) as excinfo:
        neocortex_main.build_shadow_baseline_runtime(
            neocortex_config_dir=tmp_path)
    assert excinfo.value.reason_code == "AURORA_CONFIG_INVALID"

    monkeypatch.setattr(
        neocortex_main,
        "load_aurora_shadow_runtime_config",
        MagicMock(side_effect=FileNotFoundError("aurora config missing")),
    )
    with pytest.raises(neocortex_main.FatalStartupError) as excinfo:
        neocortex_main.build_shadow_baseline_runtime(
            neocortex_config_dir=tmp_path)
    assert excinfo.value.reason_code == "AURORA_CONFIG_MISSING"

    monkeypatch.setattr(
        neocortex_main,
        "load_aurora_shadow_runtime_config",
        MagicMock(
            return_value=SimpleNamespace(
                enforcement_mode="shadow",
                event_tap_endpoint="tcp://127.0.0.1:7101",
            )
        ),
    )
    monkeypatch.setattr(
        neocortex_main,
        "BaselineController",
        MagicMock(side_effect=neocortex_main.BaselinePredictionError(
            "baseline unavailable")),
    )
    with pytest.raises(neocortex_main.FatalStartupError) as excinfo:
        neocortex_main.build_shadow_baseline_runtime(
            neocortex_config_dir=tmp_path)
    assert excinfo.value.reason_code == "BASELINE_UNAVAILABLE"


def test_append_shadow_decision_to_wal_success_and_invalid_event() -> None:
    reset_failure_outcomes()

    with pytest.raises(ValueError):
        neocortex_main.append_shadow_decision_to_wal("BAD_EVENT", {}, "why")

    captured: list[dict[str, object]] = []
    with patch(
        "apps.reference.domains.neocortex.main.wal.append",
        side_effect=lambda payload: captured.append(payload),
    ):
        neocortex_main.append_shadow_decision_to_wal(
            neocortex_main.SHADOW_DECISION_EVENT,
            {"decision_id": "decision-1", "rid": "rid-1"},
            "test_append",
        )

    assert captured and captured[0]["verb"] == "NEOCORTEX_DECISION_LOGGED"
    assert captured[0]["rid"] == "rid-1"


def test_shadow_runtime_handle_event_frame_paths(runtime_bundle) -> None:
    runtime, shadow_events = runtime_bundle

    reset_failure_outcomes()
    runtime.aggregator.ingest_event = MagicMock(return_value=None)
    assert asyncio.run(runtime.handle_event_frame({"payload": {}})) is None

    with pytest.raises(ValueError):
        runtime._emit_shadow_decision("BAD_EVENT", {}, "why")

    non_trainable_snapshot = SimpleNamespace(
        trainable=False,
        event_time_is_causal=False,
        dataset_visibility="diagnostics_only",
        symbol="BTCUSDT",
        trigger_event_type="EVT:FEATURES_CALCULATED",
    )
    runtime.aggregator.ingest_event = MagicMock(
        return_value=non_trainable_snapshot)
    assert asyncio.run(runtime.handle_event_frame({"payload": {}})) is None
    assert (
        get_failure_outcome_total(
            taxonomy=FailureOutcomeTaxonomy.BLOCK,
            reason_code="NON_CAUSAL_TIME",
        )
        == 1
    )

    snapshot = SimpleNamespace(
        trainable=True,
        event_time_is_causal=True,
        dataset_visibility="trainable",
        symbol="BTCUSDT",
        trigger_event_type="EVT:FEATURES_CALCULATED",
        tick_ts_ms=1_700_000_000_000,
        feature_event_ts_ms=1_700_000_000_000,
        feature_time_provenance=neocortex_main.CausalTimeProvenance.AURORA_EVENT,
        regime_event_ts_ms=None,
        portfolio_event_ts_ms=None,
        observation=SimpleNamespace(
            features_vector=np.arange(
                len(runtime.config.ingest.feature_list), dtype=np.float32
            ),
            mid_price=100.0,
            volatility=0.5,
            obi=0.25,
            normalized=True,
        ),
        state_vector=np.arange(13, dtype=np.float32),
        context_vector=np.arange(11, dtype=np.float32),
        regime_label="TREND_UP",
        regime_confidence=0.75,
        position_side="LONG",
        intent_side="BUY",
    )
    runtime.aggregator.ingest_event = MagicMock(return_value=snapshot)

    request = runtime._build_control_request(
        snapshot,
        _feature_payload(runtime),
    )
    response = asyncio.run(
        runtime.authority_bridge.request_authority(request, timeout_ms=50)
    )
    assert response.action == ControlDecisionAction.ALLOW
    assert response.shadow_logged is True
    assert runtime.decisions_logged == 0
    assert shadow_events

    fallback_response = SimpleNamespace(
        action=ControlDecisionAction.FALLBACK,
        shadow_logged=False,
        model_action=ControlDecisionAction.BLOCK,
        enforcement_mode="shadow",
    )
    runtime.authority_bridge.request_authority = AsyncMock(
        return_value=fallback_response
    )
    response = asyncio.run(
        runtime.handle_event_frame(_feature_payload(runtime)))
    assert response.action == ControlDecisionAction.FALLBACK
    assert runtime.shadow_fallbacks == 1
    assert runtime.decisions_logged == 0

    block_response = SimpleNamespace(
        action=ControlDecisionAction.BLOCK,
        shadow_logged=False,
        model_action=ControlDecisionAction.BLOCK,
        enforcement_mode="shadow",
    )
    runtime.authority_bridge.request_authority = AsyncMock(
        return_value=block_response
    )
    with pytest.raises(RuntimeError, match="hard BLOCK returned"):
        asyncio.run(runtime.handle_event_frame(_feature_payload(runtime)))


def test_shadow_runtime_normalize_build_request_and_snapshot(runtime_bundle) -> None:
    runtime, _shadow_events = runtime_bundle

    normalized = runtime._normalize_event_frame(
        {
            "op": "EVT",
            "event_type": "BAR_CLOSED",
            "captured_ts_ms": 1_700_000_000_123,
            "payload": {"side": "BUY"},
        }
    )
    assert normalized["event_type"] == "EVT:BAR_CLOSED"
    assert normalized["payload"]["event_ts_ms"] == 1_700_000_000_123
    assert normalized["payload"]["time_provenance"] == (
        neocortex_main.CausalTimeProvenance.CAPTURED_WALLCLOCK.value
    )

    snapshot = SimpleNamespace(
        symbol="BTCUSDT",
        tick_ts_ms=1_700_000_000_500,
        trigger_event_type="EVT:FEATURES_CALCULATED",
        event_time_is_causal=True,
        trainable=True,
        dataset_visibility="trainable",
        feature_event_ts_ms=1_700_000_000_111,
        feature_time_provenance=neocortex_main.CausalTimeProvenance.AURORA_EVENT,
        regime_event_ts_ms=None,
        portfolio_event_ts_ms=None,
        observation=SimpleNamespace(
            features_vector=np.arange(
                len(runtime.config.ingest.feature_list), dtype=np.float32
            ),
            mid_price=101.0,
            volatility=0.25,
            obi=0.1,
            normalized=True,
        ),
        state_vector=np.arange(13, dtype=np.float32),
        context_vector=np.arange(11, dtype=np.float32),
        regime_label=None,
        regime_confidence=None,
        position_side=None,
        intent_side=None,
    )

    request = runtime._build_control_request(
        snapshot,
        {
            "frame_id": "frame-1",
            "payload": {"deadline_ms": 1},
        },
    )
    assert request.decision_id == "frame-1"
    assert request.rid == "frame-1"
    assert request.proposed_action == "OBSERVE"
    assert request.deadline_ms >= snapshot.tick_ts_ms

    payload = runtime._snapshot_payload(
        snapshot,
        {
            "frame_id": "frame-1",
            "payload": {"side": "BUY", "quantity": 0.01},
        },
    )
    assert payload["source_frame"]["frame_id"] == "frame-1"
    assert payload["observation"]["features"][
        runtime.config.ingest.feature_list[0]
    ] == 0.0
    assert payload["neocortex_state"]["state_vector_dim"] == 13


@pytest.mark.asyncio
async def test_event_tap_server_start_stop_and_on_frame(runtime_bundle) -> None:
    runtime, _shadow_events = runtime_bundle
    server = neocortex_main.NeocortexEventTapServer(
        runtime=runtime,
        endpoint="tcp://127.0.0.1:7101",
        logger=logging.getLogger("neocortex.test.tap.start_stop"),
    )
    server._server.start = MagicMock()
    server._server.stop = MagicMock()
    runtime.handle_event_frame = AsyncMock(return_value=None)

    server.start()
    loop_calls: list[tuple[str, dict[str, object]]] = []

    class _LoopProbe:
        def is_closed(self) -> bool:
            return False

        def call_soon_threadsafe(self, callback, frame):
            loop_calls.append((callback.__name__, frame))
            callback(frame)

    server._loop = _LoopProbe()
    server._on_frame({"frame_id": "frame-1", "payload": {}})
    await asyncio.sleep(0)
    server.stop()

    server._server.start.assert_called_once()
    server._server.stop.assert_called_once()
    assert loop_calls and loop_calls[0][0] == "_schedule_frame"


@pytest.mark.asyncio
async def test_main_reactor_heartbeat_and_success_path(runtime_bundle, monkeypatch) -> None:
    runtime, _shadow_events = runtime_bundle

    started: list[str] = []
    stopped: list[str] = []

    class _FakeServer:
        def __init__(self, *, runtime, endpoint, logger):
            self.runtime = runtime
            self.endpoint = endpoint
            self.logger = logger

        def start(self) -> None:
            started.append(self.endpoint)

        def stop(self) -> None:
            stopped.append(self.endpoint)

    sleep_calls = {"count": 0}

    async def _sleep_once(_seconds: float) -> None:
        sleep_calls["count"] += 1
        if sleep_calls["count"] >= 2:
            raise asyncio.CancelledError
        return None

    monkeypatch.setattr(neocortex_main, "NeocortexEventTapServer", _FakeServer)
    monkeypatch.setattr(neocortex_main.asyncio, "sleep", _sleep_once)

    with pytest.raises(asyncio.CancelledError):
        await neocortex_main.main_reactor(
            runtime,
            event_tap_endpoint="tcp://127.0.0.1:7101",
            logger=logging.getLogger("neocortex.test.reactor.heartbeat"),
        )

    assert started == ["tcp://127.0.0.1:7101"]
    assert stopped == ["tcp://127.0.0.1:7101"]
    assert sleep_calls["count"] >= 2

    fake_aurora = SimpleNamespace(
        enforcement_mode="shadow",
        event_tap_endpoint="tcp://127.0.0.1:7101",
    )
    monkeypatch.setattr(
        neocortex_main,
        "build_shadow_baseline_runtime",
        MagicMock(return_value=(runtime, fake_aurora)),
    )
    monkeypatch.setattr(
        neocortex_main,
        "setup_logging",
        MagicMock(return_value=logging.getLogger("neocortex.test.main")),
    )
    main_reactor = AsyncMock(return_value=None)
    monkeypatch.setattr(neocortex_main, "main_reactor", main_reactor)
    monkeypatch.setattr(
        neocortex_main,
        "_parse_args",
        lambda argv=None: SimpleNamespace(
            config_dir=Path("config"),
            aurora_config_dir=Path("config/aurora"),
            model_path=Path("model.pkl"),
            event_tap_endpoint=None,
        ),
    )

    await neocortex_main.main([])
    main_reactor.assert_awaited_once()


def test_module_main_guard_executes(monkeypatch) -> None:
    def _noop_run(coro):
        coro.close()
        return None

    monkeypatch.setattr(asyncio, "run", _noop_run)
    runpy.run_path(str(Path(neocortex_main.__file__)), run_name="__main__")


@pytest.mark.asyncio
async def test_shadow_event_tap_reactor_entrypoint_and_run_paths(runtime_bundle, monkeypatch) -> None:
    runtime, _shadow_events = runtime_bundle

    server = neocortex_main.NeocortexEventTapServer(
        runtime=runtime,
        endpoint="tcp://127.0.0.1:7101",
        logger=logging.getLogger("neocortex.test.tap"),
    )
    server._on_frame({"payload": {}})

    async def _noop_handle(_frame):
        return None

    server._loop = asyncio.get_running_loop()
    runtime.handle_event_frame = AsyncMock(side_effect=_noop_handle)
    server._schedule_frame({"frame_id": "frame-1"})
    await asyncio.sleep(0)

    cancelled_task = asyncio.create_task(asyncio.sleep(10))
    cancelled_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_task
    server._log_task_failure(cancelled_task)

    async def _boom() -> None:
        raise RuntimeError("boom")

    boom_task = asyncio.create_task(_boom())
    with pytest.raises(RuntimeError):
        await boom_task
    server._log_task_failure(boom_task)

    started: list[str] = []
    stopped: list[str] = []

    class _FakeServer:
        def __init__(self, *, runtime, endpoint, logger):
            self.runtime = runtime
            self.endpoint = endpoint
            self.logger = logger

        def start(self) -> None:
            started.append(self.endpoint)

        def stop(self) -> None:
            stopped.append(self.endpoint)

    async def _raise_cancelled(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(neocortex_main, "NeocortexEventTapServer", _FakeServer)
    monkeypatch.setattr(neocortex_main.asyncio, "sleep", _raise_cancelled)
    with pytest.raises(asyncio.CancelledError):
        await neocortex_main.main_reactor(
            runtime,
            event_tap_endpoint="tcp://127.0.0.1:7101",
            logger=logging.getLogger("neocortex.test.reactor"),
        )
    assert started == ["tcp://127.0.0.1:7101"]
    assert stopped == ["tcp://127.0.0.1:7101"]

    fake_report = SimpleNamespace(
        blocking_gate_ids=["shadow_gate"],
        model_dump_json=lambda: '{"blocking_gate_ids":["shadow_gate"]}',
    )
    monkeypatch.setattr(
        neocortex_main,
        "_parse_args",
        lambda argv=None: SimpleNamespace(
            config_dir=Path("config"),
            aurora_config_dir=Path("config/aurora"),
            model_path=Path("model.pkl"),
            event_tap_endpoint=None,
        ),
    )
    monkeypatch.setattr(
        neocortex_main,
        "build_shadow_baseline_runtime",
        MagicMock(side_effect=ShadowGateViolationError(fake_report)),
    )
    with pytest.raises(SystemExit) as excinfo:
        await neocortex_main.main([])
    assert excinfo.value.code == 1

    monkeypatch.setattr(
        neocortex_main,
        "build_shadow_baseline_runtime",
        MagicMock(
            side_effect=neocortex_main.FatalStartupError(
                "CONFIG_INVALID", "boom")
        ),
    )
    with pytest.raises(SystemExit) as excinfo:
        await neocortex_main.main([])
    assert excinfo.value.code == 1

    def _raise_keyboard_interrupt(coro):
        coro.close()
        raise KeyboardInterrupt

    monkeypatch.setattr(neocortex_main.asyncio, "run",
                        _raise_keyboard_interrupt)
    with pytest.raises(SystemExit) as excinfo:
        neocortex_main.run()
    assert excinfo.value.code == 0
