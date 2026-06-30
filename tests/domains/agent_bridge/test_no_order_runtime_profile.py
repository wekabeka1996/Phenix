from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.domains.agent_bridge.execution_readiness import (
    build_execution_readiness_snapshot,
)
from apps.reference.bootstrap.domain_builder import build_live_domains
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.execution_position.adapters.adapter_init import (
    AdapterInitMixin,
)
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.runtime_profile import RuntimeLaunchProfile, resolve_runtime_launch_profile


def test_runtime_profile_is_typed_and_unknown_value_fails_closed() -> None:
    normal = resolve_runtime_launch_profile({})
    observation = resolve_runtime_launch_profile(
        {"AURORA_RUNTIME_PROFILE": "agent_bridge_observation_only"}
    )

    assert normal.name == "normal"
    assert normal.no_order_observation is False
    assert observation.no_order_observation is True
    with pytest.raises(ValueError, match="Unsupported AURORA_RUNTIME_PROFILE"):
        resolve_runtime_launch_profile({"AURORA_RUNTIME_PROFILE": "agent_bridge_observtion"})
    with pytest.raises(ValueError, match="must not be empty"):
        resolve_runtime_launch_profile({"AURORA_RUNTIME_PROFILE": "  "})


def test_adapter_initialization_is_unreachable_and_does_not_read_config() -> None:
    class SecretTrap:
        def __getattribute__(self, name):
            raise AssertionError(f"config or secret read: {name}")

    class Runtime(AdapterInitMixin):
        no_order_observation_mode = True
        shadow_mode = False
        adapter = object()
        config = SecretTrap()

    runtime = Runtime()
    runtime._initialize_adapter()

    assert runtime.shadow_mode is True
    assert runtime.adapter is None


def test_domain_builder_composes_execution_as_shadow_no_order() -> None:
    project_root = Path(__file__).resolve().parents[3]
    config = ConfigLoader(config_dir=project_root / "config" / "aurora").load_config()
    profile = RuntimeLaunchProfile(name="agent_bridge_observation_only")

    with patch("apps.reference.bootstrap.domain_builder.MarketDataConnector"), \
            patch("apps.reference.bootstrap.domain_builder.MarketDataProxy"), \
            patch("apps.reference.bootstrap.domain_builder.AccountConnector") as account_cls, \
            patch("apps.reference.bootstrap.domain_builder.ExecPosFSM") as exec_cls, \
            patch("apps.reference.bootstrap.domain_builder.CsvRecorder"):
        bundle = build_live_domains(
            config=config,
            fsm=MagicMock(),
            logger=MagicMock(),
            runtime_profile=profile,
        )

    assert exec_cls.call_args.kwargs["shadow_mode"] is True
    assert exec_cls.call_args.kwargs["is_live_execution"] is False
    assert exec_cls.call_args.kwargs["no_order_observation_mode"] is True
    assert bundle.account_balance is None
    account_cls.assert_not_called()


def test_consequential_entry_points_block_even_if_adapter_is_injected() -> None:
    class AdapterTrap:
        def __getattribute__(self, name):
            if name in {"create_order", "place_order", "cancel_order", "modify_order"}:
                raise AssertionError(f"consequential adapter reached: {name}")
            return object.__getattribute__(self, name)

    runtime = object.__new__(ExecPosFSM)
    runtime.no_order_observation_mode = True
    runtime.runtime_mode = "agent_bridge_observation_only"
    runtime.no_order_blocked_action_count = 0
    runtime.adapter = AdapterTrap()
    runtime._intent_router = SimpleNamespace(
        on_trade_intent_proposed=lambda _msg: (_ for _ in ()).throw(
            AssertionError("intent router reached")
        ),
        on_external_open_request=lambda _msg: (_ for _ in ()).throw(
            AssertionError("external open router reached")
        ),
        on_external_position_close_request=lambda _msg: (_ for _ in ()).throw(
            AssertionError("external close router reached")
        ),
        on_external_bracket_amend_request=lambda _msg: (_ for _ in ()).throw(
            AssertionError("external amend router reached")
        ),
    )

    runtime._on_trade_intent_proposed(SimpleNamespace())
    runtime._on_external_open_request(SimpleNamespace())
    runtime._on_external_position_close_request(SimpleNamespace())
    runtime._on_external_bracket_amend_request(SimpleNamespace())
    cancel_result = asyncio.run(runtime._cancel_order("BTCUSDT", "order-1"))
    asyncio.run(runtime._execute_decision(SimpleNamespace(verb="OPEN")))

    assert cancel_result["status"] == "BLOCKED"
    assert runtime.no_order_blocked_action_count == 6


def test_runtime_owned_readiness_proves_no_order_isolation_without_secrets() -> None:
    runtime = SimpleNamespace(
        no_order_observation_mode=True,
        shadow_mode=True,
        is_live_execution=False,
        adapter=None,
        no_order_blocked_action_count=0,
        exchange_filter_cache=None,
        _close_exec=object(),
        _idempotent_cancel_helper=object(),
        order_index=object(),
        _startup_truth_orchestrator=object(),
        manage_flows={},
        _bracket_ownership=object(),
        _symbol_brackets={},
        _symbol_bracket_truth_source={},
        correlation_store=object(),
    )

    snapshot = build_execution_readiness_snapshot(
        runtime=runtime,
        symbols=["BTCUSDT", "ETHUSDT"],
        produced_ts_ms=1_800_000_000_000,
        trace_available=True,
    )
    invariants = {item.name: item for item in snapshot.invariants}

    assert invariants["testnet_only_or_mode"].status == "ready"
    assert invariants["no_order_execution_isolation"].status == "ready"
    assert invariants["exchange_filter_readiness"].status == "missing"
    assert invariants["secret_isolation"].status == "ready"
