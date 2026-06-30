from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from apps.reference.config_contract import ConfigContractError
from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import (
    ExecutionPositionRestoreArtifactConfig,
    ExecutionPositionRestoreArtifactMode,
    ExecutionPositionStartupTruthArtifactConfig,
    ExecutionPositionStartupTruthArtifactMode,
)
from apps.reference.domains.execution_position.adapters.config_resolver import ConfigResolverMixin
from apps.reference.domains.execution_position.guardian.order_guardian import (
    InMemoryStore,
    OrderGuardian,
)
from apps.reference.domains.execution_position.state.restore_artifact import (
    BRACKET_STATE_UNKNOWN,
    ExecutionPositionRestoreEnvelope,
    ExecutionPositionRestoreLifecycleRecord,
    TRUTH_SOURCE_RUNTIME_LOCAL,
    TRUTH_SOURCE_UNKNOWN,
)


class _Node:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _ResolverProbe(ConfigResolverMixin):
    def __init__(self, config):
        self.config = config


def _copy_tree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.rglob("*"):
        relative = item.relative_to(src)
        target = dst / relative
        if item.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(item, target)


def _configure_authoritative(fsm, tmp_path: Path, *, age_ms: int | None = None) -> Path:
    path = tmp_path / "execution_restore.json"
    fsm.config.domains.execution_position.restore_artifact = ExecutionPositionRestoreArtifactConfig(
        mode=ExecutionPositionRestoreArtifactMode.AUTHORITATIVE,
        storage_path=str(path),
        flush_interval_ms=30000,
        dark_read_max_artifact_age_ms=age_ms,
    )
    fsm._startup_truth_orchestrator._restore_artifact_writer = (
        fsm._startup_truth_orchestrator._create_restore_artifact_writer()
    )
    fsm._startup_truth_orchestrator._restore_artifact_dark_reader = (
        fsm._startup_truth_orchestrator._create_restore_artifact_dark_reader()
    )
    return path


def _configure_startup_truth_writer(fsm, tmp_path: Path) -> Path:
    path = tmp_path / "startup_truth.jsonl"
    fsm.config.domains.execution_position.startup_truth_artifact = (
        ExecutionPositionStartupTruthArtifactConfig(
            mode=ExecutionPositionStartupTruthArtifactMode.WRITER_ONLY,
            storage_path=str(path),
        )
    )
    fsm._startup_truth_orchestrator._startup_truth_artifact_writer = (
        fsm._startup_truth_orchestrator._create_startup_truth_artifact_writer()
    )
    return path


def _write_envelope(path: Path, symbol: str) -> None:
    record = ExecutionPositionRestoreLifecycleRecord.model_validate(
        {
            "symbol": symbol,
            "manage_phase": "TRACKING",
            "manage_truth_source": TRUTH_SOURCE_RUNTIME_LOCAL,
            "close_phase": "OPENED",
            "bracket_state": BRACKET_STATE_UNKNOWN,
            "bracket_truth_source": TRUTH_SOURCE_UNKNOWN,
            "live_reconcile_required": True,
        }
    )
    envelope = ExecutionPositionRestoreEnvelope(
        schema_version="1.0.0",
        artifact_type="execution_position_restore_envelope_v1",
        generated_at_ms=4_102_444_800_000,
        writer_component="execution_position",
        requires_live_reconcile=True,
        active_lifecycles=[record],
    )
    path.write_text(
        json.dumps(envelope.model_dump(
            mode="json", exclude_none=True), sort_keys=True),
        encoding="utf-8",
    )


def _load_startup_truth_rows(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_collect_guardian_symbols_uses_active_symbols_before_root_instruments() -> None:
    config = _Node(
        trading=_Node(symbols_to_track=["btcusdt", "ETHUSDT"]),
        strategies_registry=_Node(assignments={"SOLUSDT": ["aurora"]}),
        instruments={"BTCUSDT": object(), "DOGEUSDT": object()},
    )

    symbols = _ResolverProbe(config)._collect_guardian_symbols()

    assert symbols == {"BTCUSDT", "ETHUSDT"}


def test_collect_guardian_symbols_rejects_non_empty_legacy_trading_instruments() -> None:
    config = _Node(
        trading=_Node(instruments={"DOGEUSDT": object()}),
        instruments={"BTCUSDT": object()},
    )

    with pytest.raises(ValueError, match="trading.instruments"):
        _ResolverProbe(config)._collect_guardian_symbols()


def test_collect_guardian_symbols_current_repo_uses_active_strategy_universe() -> None:
    config = ConfigLoader(Path("config/aurora")).load_config()

    symbols = _ResolverProbe(config)._collect_guardian_symbols()

    assert symbols == set(config.trading.symbols_to_track)
    assert symbols
    assert "DOGEUSDT" in symbols
    assert "DOGEUSDT" in config.instruments


def test_config_loader_still_rejects_forbidden_trading_instruments(tmp_path: Path) -> None:
    repo_config_dir = (Path(__file__).resolve(
    ).parents[3] / "config" / "aurora").resolve()
    _copy_tree(repo_config_dir, tmp_path)

    trading_path = tmp_path / "trading.yaml"
    trading_obj = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
    trading_obj["trading"]["instruments"] = {
        "DOGEUSDT": {"symbol": "DOGEUSDT"}}
    trading_path.write_text(
        yaml.safe_dump(trading_obj, sort_keys=False),
        encoding="utf-8",
    )

    with pytest.raises(ConfigContractError, match="trading.instruments"):
        ConfigLoader(tmp_path).load_config()


def test_order_guardian_seed_symbols_use_active_configured_universe() -> None:
    config = _Node(
        trading=_Node(symbols_to_track=["BTCUSDT", "ethusdt"]),
        instruments={"BTCUSDT": object(), "ETHUSDT": object(),
                     "DOGEUSDT": object()},
    )

    guardian = OrderGuardian(
        adapter=None,
        store=InMemoryStore(),
        poll_interval_ms=0,
        config=config,
    )

    assert guardian.get_metrics()["guardian_known_symbols"] == [
        "BTCUSDT", "ETHUSDT"]


@pytest.mark.asyncio
async def test_startup_truth_excludes_seed_only_symbols_from_unknown_rows(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, config = fsm_harness
    config.trading.symbols_to_track = ["BTCUSDT"]
    config.instruments["DOGEUSDT"] = MagicMock()
    _configure_authoritative(fsm, tmp_path)
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)

    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(return_value=[])
    fsm.adapter.get_open_orders = AsyncMock(side_effect=[[], []])

    await fsm._startup_order_guardian_reconcile()

    linked_symbols = {
        call.args[0] for call in fsm.order_guardian.link_existing_from_rest.await_args_list
    }
    rows = _load_startup_truth_rows(startup_truth_path)
    row = rows[0]

    assert linked_symbols == {"BTCUSDT"}
    assert row["input_snapshot"]["guardian_link_existing_invoked"] is True
    assert row["input_snapshot"]["guardian_symbols_observed"] == []
    assert row["symbols_considered"] == []
    assert row["unknown_truth_records"] == []


@pytest.mark.asyncio
async def test_startup_truth_keeps_observed_and_authoritative_symbols_not_seed_only(
    fsm_harness,
    tmp_path: Path,
) -> None:
    fsm, _, config = fsm_harness
    config.trading.symbols_to_track = ["BTCUSDT"]
    config.instruments["DOGEUSDT"] = MagicMock()
    restore_path = _configure_authoritative(fsm, tmp_path, age_ms=None)
    _write_envelope(restore_path, "BNBUSDT")
    startup_truth_path = _configure_startup_truth_writer(fsm, tmp_path)

    fsm.order_guardian.cleanup_orphans = AsyncMock(return_value=None)
    fsm.order_guardian.link_existing_from_rest = AsyncMock(return_value=None)
    fsm.adapter = AsyncMock()
    fsm.adapter.get_open_positions = AsyncMock(
        return_value=[{"symbol": "SOLUSDT", "positionAmt": "0.10"}]
    )
    fsm.adapter.get_open_orders = AsyncMock(
        side_effect=[[{"symbol": "XRPUSDT", "orderId": "pre-1"}], []]
    )

    await fsm._startup_order_guardian_reconcile()

    linked_symbols = {
        call.args[0] for call in fsm.order_guardian.link_existing_from_rest.await_args_list
    }
    row = _load_startup_truth_rows(startup_truth_path)[0]

    assert linked_symbols == {"BNBUSDT", "BTCUSDT", "SOLUSDT", "XRPUSDT"}
    assert row["symbols_considered"] == ["BNBUSDT", "SOLUSDT", "XRPUSDT"]
    assert row["input_snapshot"]["position_symbols_observed"] == ["SOLUSDT"]
    assert row["input_snapshot"]["pre_cleanup_order_symbols_observed"] == [
        "XRPUSDT"]
    assert row["input_snapshot"]["guardian_symbols_observed"] == []
    assert "BTCUSDT" not in row["symbols_considered"]
    assert "DOGEUSDT" not in row["symbols_considered"]
