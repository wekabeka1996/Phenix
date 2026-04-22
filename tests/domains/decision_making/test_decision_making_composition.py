from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import apps.reference.domains.decision_making.decision_making as dm_module
from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.decision_making.dm_config_spec import DMConfigSpec
from apps.reference.domains.decision_making.dm_state import DMState


class FixedClock:
    def __init__(self, now_ms: int = 1_700_000_000_000) -> None:
        self._now_ms = now_ms

    def now_ms(self) -> int:
        return self._now_ms

    def now_sec(self) -> float:
        return self._now_ms / 1000.0


class RecordingFSM:
    def __init__(self) -> None:
        self.listen_calls: list[tuple[str, object]] = []

    def listen(self, event_name: str, handler: object) -> None:
        self.listen_calls.append((event_name, handler))


def test_decision_making_registers_listeners_in_exact_runtime_order(monkeypatch) -> None:
    config = ConfigLoader().load_config()
    fsm = RecordingFSM()
    bridge_events: list[tuple[str, object, object | None]] = []

    class RecordingBridge:
        def __init__(self, domain_name: str, *, bus: object) -> None:
            bridge_events.append(("init", domain_name, bus))

        def register_health_fn(self, fn: object) -> None:
            bridge_events.append(("register_health_fn", fn, None))

    monkeypatch.setattr(dm_module, "DomainBridge", RecordingBridge)

    dm = DecisionMaking(fsm=fsm, config=config, clock=FixedClock())

    assert [event_name for event_name, _handler in fsm.listen_calls] == [
        "EVT:FEATURES_CALCULATED",
        "EVT:RISK_ASSESSMENT_COMPLETED",
        "EVT:PORTFOLIO_STATE_UPDATED",
        "EVT:REGIME_DETECTED",
        "EVT:POSITION_CLOSED",
        "EVT:EXPOSURE_SUMMARY_UPDATED",
        "EVT:STRATEGY_SIGNAL_PRODUCED",
        "EVT:SYSTEM_STRESS_STATE_UPDATED",
    ]
    assert bridge_events[0] == ("init", "decision_making", fsm)
    assert bridge_events[1][0] == "register_health_fn"
    health_fn = bridge_events[1][1]
    assert getattr(health_fn, "__self__", None) is dm
    assert getattr(health_fn, "__func__", None) is DecisionMaking.is_healthy


def test_dm_config_spec_matches_decision_making_runtime_projection() -> None:
    config = ConfigLoader().load_config()
    fsm = MagicMock()
    fsm.listen = MagicMock()

    spec = DMConfigSpec.load(config)
    dm = DecisionMaking(fsm=fsm, config=config, clock=FixedClock())

    assert spec.strategies_registry == dm.strategies_registry
    assert spec.tca_prefs == dm._tca_prefs
    assert spec.risk_budgets == dm._risk_budgets
    assert spec.fail_closed_on_degraded_context == dm._fail_closed_on_degraded_context
    assert spec.degraded_context_critical_keys == dm._degraded_context_critical_keys
    assert (
        spec.degraded_context_critical_keys_by_strategy
        == dm._degraded_context_critical_keys_by_strategy
    )
    assert (
        spec.degraded_context_contracts_by_strategy
        == dm._degraded_context_contracts_by_strategy
    )
    assert spec.min_pos_size_usd == dm.min_pos_size_usd
    assert spec.liq_cap_usd == dm.liq_cap_usd
    assert spec.qos_exposure_block_cooldown_sec == dm.qos_exposure_block_cooldown_sec
    assert (
        spec.qos_max_intents_per_minute_per_symbol
        == dm.qos_max_intents_per_minute_per_symbol
    )
    assert spec.qos_mode == dm.qos_mode
    assert spec.default_symbol_cooldown_sec == dm._default_symbol_cooldown_sec
    assert spec.qos_enforce == dm.qos_enforce
    assert spec.qos_apply_to_strategies == dm._qos_apply_to_strategies
    assert spec.arming_require_regime_warmup == dm.arming_require_regime_warmup
    assert spec.arming_retry_backoff_ms == dm.arming_retry_backoff_ms
    assert spec.arming_max_attempts == dm.arming_max_attempts
    assert spec.features_ttl_sec == dm.features_ttl_sec
    assert spec.flip_global_enabled == dm.flip_global_enabled
    assert spec.bar_gating_enabled == dm._bar_gating_enabled
    assert spec.bar_ms == dm._bar_ms
    assert spec.behavior_enabled == dm._behavior_enabled
    assert spec.normalize_signals_mode == dm.normalize_signals_mode


def test_decision_making_uses_constructor_domain_resolver_seam_for_config_spec(
    monkeypatch,
) -> None:
    config = ConfigLoader().load_config()
    fsm = MagicMock()
    fsm.listen = MagicMock()

    fake_dm_cfg = SimpleNamespace(
        qos=SimpleNamespace(
            exposure_block_cooldown_sec=17,
            max_intents_per_minute_per_symbol=23,
            mode="compat-shadow",
            symbol_cooldown_sec=29,
            enforce=True,
            apply_to_strategies=["aurora", "mean_reversion"],
        ),
        position_sizing=SimpleNamespace(
            min_position_size_usd="123",
            liquidity_based_cap_usd="456",
        ),
        arming=SimpleNamespace(
            require_regime_warmup=False,
            retry_backoff_ms=31,
            max_attempts=37,
        ),
        features=SimpleNamespace(ttl_sec=41.0),
        flip=SimpleNamespace(enabled=False),
        bar_gating=SimpleNamespace(enable=False, bar_ms=43_000),
        behavior_fsm=SimpleNamespace(enable=False),
        fail_closed_on_degraded_context=False,
        degraded_context_critical_keys=[],
        degraded_context_critical_keys_by_strategy={},
        degraded_context_contracts_by_strategy={},
    )

    class FakeResolver:
        def __init__(self, cfg: object) -> None:
            assert cfg is config

        def get_decision_making(self) -> object:
            return fake_dm_cfg

    monkeypatch.setattr(dm_module, "DomainConfigResolver", FakeResolver)

    dm = DecisionMaking(fsm=fsm, config=config, clock=FixedClock())

    assert dm.min_pos_size_usd == 123
    assert dm.liq_cap_usd == 456
    assert dm.qos_mode == "compat-shadow"
    assert dm.qos_exposure_block_cooldown_sec == 17
    assert dm.qos_max_intents_per_minute_per_symbol == 23
    assert dm._default_symbol_cooldown_sec == 29
    assert dm.qos_enforce is True
    assert dm._qos_apply_to_strategies == {"aurora", "mean_reversion"}


def test_dm_state_factory_matches_decision_making_initial_state_shapes() -> None:
    config = ConfigLoader().load_config()
    clock = FixedClock()
    state = DMState.new(clock)
    fsm = MagicMock()
    fsm.listen = MagicMock()

    dm = DecisionMaking(fsm=fsm, config=config, clock=clock)

    assert dm._shared == state.shared_state
    assert dm._per_symbol_regimes == state.per_symbol_regimes == {}
    assert dm._system_stress_states == state.system_stress_states == {}
    assert dm._side_intent_window == state.side_intent_window == {}
    assert dm._pending_flips == state.pending_flips == {}
    assert dm._arb_window_winner == state.arb_window_winner == {}
    assert dm._arb_signal_buffer == state.arb_signal_buffer == {}
    assert dm.intents_seen_total == state.intents_seen_total == 0
    assert dm.intents_blocked_total == state.intents_blocked_total == 0
    assert dm.last_alert_check_time == state.last_alert_check_time == clock.now_sec()
    assert dm._last_bar_index == state.last_bar_index == {}
    assert dm._behavior_state == state.behavior_state == {}

    symbol = "BTCUSDT"
    assert dm.symbol_states[symbol] == state.symbol_states[symbol] == {
        "features": None,
        "risk": None,
    }

    strategy_id = "aurora"
    assert dm._qos_state[strategy_id]["last_exposure_block"] == state.qos_state[strategy_id]["last_exposure_block"] == 0.0
    assert dm._qos_state[strategy_id]["symbol_cooldowns"] == state.qos_state[strategy_id]["symbol_cooldowns"] == {}
    assert (
        dm._qos_state[strategy_id]["symbol_intent_counts"][symbol]
        == state.qos_state[strategy_id]["symbol_intent_counts"][symbol]
        == {"count": 0, "window_start": 0.0}
    )
    assert dm._qos_next_allowed_ts[strategy_id] == state.qos_next_allowed_ts[strategy_id] == {
    }
