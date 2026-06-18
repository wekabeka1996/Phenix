from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import jsonschema

from apps.reference.domains.strategies.registry import (
    StrategyPluginRegistry,
    StrategyRuntime,
    build_strategy_registry_snapshot,
)
from tools.analysis.audit_order_log_v1_strategy_registry_coverage import (
    FINANCIAL_EVENT_TYPES,
    build_report,
)


ROOT = Path(__file__).resolve().parents[3]
STRATEGY_IDS = {
    "aurora",
    "mean_reversion",
    "alpha_mr_s01",
    "alpha_ta_ensemble",
    "md_amr",
    "llm_microstructure",
}


class _FSM:
    def listen(self, event: str, handler: object) -> None:
        del event, handler


@dataclass(frozen=True)
class _Handler:
    def register(self) -> None:
        return None


@dataclass(frozen=True)
class _Plugin:
    strategy_id: str

    def create_handler(self, *, fsm: _FSM, config: object) -> _Handler:
        del fsm, config
        return _Handler()


def _config() -> SimpleNamespace:
    strategies = SimpleNamespace(**{
        strategy_id: SimpleNamespace(enabled=True, mode="live", type="bar_driven")
        for strategy_id in STRATEGY_IDS
    })
    return SimpleNamespace(
        strategies=strategies,
        strategies_registry=SimpleNamespace(assignments={"BTCUSDT": sorted(STRATEGY_IDS)}),
    )


def _registry() -> StrategyPluginRegistry:
    registry = StrategyPluginRegistry()
    for strategy_id in sorted(STRATEGY_IDS):
        registry.register(_Plugin(strategy_id))
    return registry


def test_schema_accepts_non_financial_strategy_registry_snapshot() -> None:
    payload = build_strategy_registry_snapshot(
        config=_config(),  # type: ignore[arg-type]
        registry=_registry(),
        started_handlers={},
        assigned_ids=STRATEGY_IDS,
    )
    schema = json.loads(
        (ROOT / "apps/reference/schemas/order_logger_v1.json").read_text(encoding="utf-8")
    )

    jsonschema.validate(payload, schema)
    assert payload["non_financial"] is True
    assert payload["event_type"] not in FINANCIAL_EVENT_TYPES
    assert {item["strategy_id"] for item in payload["strategies"]} == STRATEGY_IDS


def test_runtime_snapshot_lists_configured_strategies_without_fake_trades() -> None:
    writes: list[dict] = []

    StrategyRuntime(
        fsm=_FSM(),
        config=_config(),  # type: ignore[arg-type]
        registry=_registry(),
        telemetry_writer=writes.append,
    ).start()

    assert len(writes) == 1
    snapshot = writes[0]
    assert {item["strategy_id"] for item in snapshot["strategies"]} == STRATEGY_IDS
    assert all(item["observed_in_current_runtime"] is True for item in snapshot["strategies"])
    assert all(item["financially_reachable"] is False for item in snapshot["strategies"])
    assert all(item["financial_blockers"] for item in snapshot["strategies"])
    assert not any(snapshot["event_type"] == event for event in FINANCIAL_EVENT_TYPES)


def test_snapshot_includes_configured_strategy_missing_from_runtime_registry() -> None:
    config = _config()
    config.strategies.configured_only = SimpleNamespace(
        enabled=True,
        mode="live",
        type="bar_driven",
    )

    snapshot = build_strategy_registry_snapshot(
        config=config,  # type: ignore[arg-type]
        registry=_registry(),
        started_handlers={},
        assigned_ids=STRATEGY_IDS,
    )
    strategies = {item["strategy_id"]: item for item in snapshot["strategies"]}

    assert strategies["configured_only"]["status"] == "historical_or_dead_code"
    assert strategies["configured_only"]["observed_in_current_runtime"] is False
    assert strategies["configured_only"]["can_emit_order_intent"] is False


def test_configured_inactive_strategy_is_visible_but_not_financially_active() -> None:
    snapshot = build_strategy_registry_snapshot(
        config=_config(),  # type: ignore[arg-type]
        registry=_registry(),
        started_handlers={},
        assigned_ids=STRATEGY_IDS,
    )
    report = build_report([snapshot], parse_errors=0)
    strategies = {item["strategy_id"]: item for item in report["strategies"]}

    assert strategies["alpha_ta_ensemble"]["seen_in_registry_snapshot"] is True
    assert strategies["alpha_ta_ensemble"]["financially_active"] is False
    assert report["financial_event_count"] == 0


def test_existing_order_log_rows_still_parse() -> None:
    path = ROOT / "logs/order_log_v1.jsonl"
    parsed = 0
    with path.open("r", encoding="utf-8") as handle:
        for raw in handle:
            assert isinstance(json.loads(raw), dict)
            parsed += 1
    assert parsed > 0
