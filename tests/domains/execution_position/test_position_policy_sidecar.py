from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.config_models import PositionPolicySidecarConfig
from apps.reference.core.time import get_clock
from apps.reference.domains.execution_position.position_policy_sidecar import (
    PositionPolicySidecar,
)
from apps.reference.domains.execution_position.fsm import ExecPosFSM


class RecordingBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, dict]] = []
        self.listeners: dict[str, list] = {}

    def listen(self, topic, handler):
        self.listeners.setdefault(topic, []).append(handler)

    def emit(self, topic, payload=None, **kwargs):
        payload = payload or {}
        self.events.append((topic, payload, kwargs))
        for handler in self.listeners.get(topic, []):
            handler(SimpleNamespace(pld=payload, verb=topic.split(
                ":")[-1], rid=payload.get("rid")))


class DummyManageFlow:
    def __init__(
        self,
        *,
        active: bool = True,
        closing: bool = False,
        side: str = "BUY",
        qty: str = "0.10",
        entry_price: str = "100.0",
    ) -> None:
        self.state = SimpleNamespace(value="TRACKING")
        self._active = active
        self._closing_position = closing
        self.position_side = side
        self.position_qty = qty
        self.position_entry_price = entry_price
        self.position_open_ts = 1_000.0
        self.symbol = "BTCUSDT"

    def has_active_lifecycle(self) -> bool:
        return self._active


def _sidecar_config(tmp_path: Path, *, mode: str = "shadow", recommend_soft_close_at: float = 0.70) -> PositionPolicySidecarConfig:
    return PositionPolicySidecarConfig.model_validate(
        {
            "mode": mode,
            "freshness": {
                "portfolio_max_age_ms": 15_000,
                "features_max_age_ms": 15_000,
                "regime_max_age_ms": 15_000,
                "order_state_max_age_ms": 15_000,
            },
            "startup_grace": {
                "startup_grace_ms": 0,
                "post_fill_grace_ms": 0,
                "min_portfolio_updates": 1,
                "min_feature_updates": 1,
                "min_regime_updates": 1,
            },
            "profitability_guard": {
                "enabled": True,
                "min_unrealized_pnl_pct": 0.25,
                "min_unrealized_pnl_usdt": 0.0,
            },
            "scoring": {
                "weights": {
                    "microstructure_adverse_pressure": 0.30,
                    "regime_exhaustion_hint": 0.30,
                    "conviction_decay": 0.15,
                    "unrealized_loss_pressure": 0.25,
                },
                "caps": {
                    "microstructure_adverse_pressure": 1.0,
                    "regime_exhaustion_hint": 1.0,
                    "conviction_decay": 1.0,
                    "unrealized_loss_pressure": 1.0,
                },
            },
            "thresholds": {
                "recommend_soft_close_at": recommend_soft_close_at,
                "loss_bps_full_pressure": 50.0,
                "adverse_price_distance_bps_full_pressure": 25.0,
                "book_imbalance_full_pressure": 0.35,
                "regime_confidence_floor": 0.55,
                "signal_score_floor": 0.0,
                "adverse_regimes_long": ["TREND_DOWN"],
                "adverse_regimes_short": ["TREND_UP"],
            },
            "logging": {
                "emit_internal_bus_events": True,
                "write_trade_lifecycle_jsonl": True,
                "trade_lifecycle_log_path": str(tmp_path / "trade_lifecycle.jsonl"),
                "include_score_payloads": True,
            },
            "allowed_actions": {
                "soft_close_symbol_current_net_only": True,
                "partial_reduce": False,
                "bracket_mutation": False,
                "exact_targeting": False,
            },
        }
    )


def _event(**payload):
    return SimpleNamespace(pld=payload)


def _topics(bus: RecordingBus) -> list[str]:
    return [topic for topic, _, _ in bus.events]


def _payloads(bus: RecordingBus, topic: str) -> list[dict]:
    return [payload for recorded_topic, payload, _ in bus.events if recorded_topic == topic]


def test_position_policy_sidecar_recommends_and_skips_action_in_enable_mode(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="enable",
                               recommend_soft_close_at=0.45),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(
        _event(
            positions_last_ts_ms=now_ms,
            positions=[
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.10",
                    "entryPrice": "100.0",
                    "markPrice": "99.2",
                    "unrealizedProfit": "-0.08",
                }
            ],
        )
    )
    sidecar.on_features_calculated(
        _event(
            symbol="BTCUSDT",
            ts_ms=now_ms + 1,
            orderbook_imbalance=-1.0,
            price_vs_vwap_bps=-80.0,
            signal_score=-0.5,
        )
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2,
               regime="TREND_DOWN", confidence=0.10)
    )

    assert "EVT:POSITION_POLICY_SIDECAR_SCORES" in _topics(bus)
    assert "EVT:POSITION_POLICY_SIDECAR_EVALUATED" in _topics(bus)
    assert "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED" in _topics(bus)
    assert "EVT:POSITION_POLICY_SIDECAR_ACTION_SKIPPED" in _topics(bus)

    recommended = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")[-1]
    skipped = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_ACTION_SKIPPED")[-1]
    assert recommended["trace_id"] == skipped["trace_id"]
    assert 0.0 <= recommended["score_snapshot"]["soft_close_pressure"] <= 1.0
    assert skipped["allowed_action_scope"]["soft_close_symbol_current_net_only"] is True

    log_lines = (
        tmp_path / "trade_lifecycle.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert any(
        '"record_kind": "position_policy_sidecar"' in line for line in log_lines)


def test_position_policy_sidecar_profitability_guard_suppresses(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="shadow"),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(
        _event(
            positions_last_ts_ms=now_ms,
            positions=[
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.10",
                    "entryPrice": "100.0",
                    "markPrice": "101.0",
                    "unrealizedProfit": "0.10",
                }
            ],
        )
    )
    sidecar.on_features_calculated(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 1,
               orderbook_imbalance=-0.2, signal_score=0.0)
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2,
               regime="TREND_DOWN", confidence=0.10)
    )

    suppressed = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")[-1]
    assert suppressed["suppression_reason"] == "profitability_guard_active"


def test_position_policy_sidecar_preserves_trade_executed_fill_correlation(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="shadow"),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_trade_executed(
        _event(
            symbol="BTCUSDT",
            rid="rid-sidecar-1",
            orderId="order-sidecar-1",
            clientOrderId="ENTRY-SIDECAR-1",
            fill_source="trade_executed",
            canonical_fill_trace_id="exec-fill:BTCUSDT:trade_executed:rid-sidecar-1:1",
            manage_flow_created=True,
            manage_state_before="FLAT",
            manage_state_after="TRACKING",
        )
    )

    suppressed = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")[-1]
    assert suppressed["trigger_event"] == "TRADE_EXECUTED"
    assert suppressed["fill_correlation"]["rid"] == "rid-sidecar-1"
    assert suppressed["fill_correlation"]["order_id"] == "order-sidecar-1"
    assert suppressed["fill_correlation"]["client_order_id"] == "ENTRY-SIDECAR-1"
    assert suppressed["fill_correlation"]["fill_source"] == "trade_executed"
    assert suppressed["fill_correlation"]["manage_flow_created"] is True
    assert suppressed["fill_correlation"]["manage_state_before"] == "FLAT"
    assert suppressed["fill_correlation"]["manage_state_after"] == "TRACKING"


def test_position_policy_sidecar_normalizes_structural_regime_aliases(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="shadow",
                               recommend_soft_close_at=0.45),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(
        _event(
            positions_last_ts_ms=now_ms,
            positions=[
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.10",
                    "entryPrice": "100.0",
                    "markPrice": "99.2",
                    "unrealizedProfit": "-0.08",
                }
            ],
        )
    )
    sidecar.on_features_calculated(
        _event(
            symbol="BTCUSDT",
            ts_ms=now_ms + 1,
            orderbook_imbalance=-1.0,
            price_vs_vwap_bps=-80.0,
            signal_score=-0.5,
        )
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2,
               regime="BEAR_TREND", confidence=0.10)
    )

    recommended = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")[-1]
    assert recommended["score_snapshot"]["regime_exhaustion_hint"] > 0.0


def test_position_policy_sidecar_stale_features_fail_closed(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="shadow"),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(
        _event(
            positions_last_ts_ms=now_ms,
            positions=[
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.10",
                    "entryPrice": "100.0",
                    "markPrice": "99.5",
                    "unrealizedProfit": "-0.05",
                }
            ],
        )
    )
    sidecar.on_features_calculated(
        _event(
            symbol="BTCUSDT",
            ts_ms=now_ms - 30_000,
            orderbook_imbalance=-0.5,
            signal_score=-0.1,
        )
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 1,
               regime="TREND_DOWN", confidence=0.10)
    )

    suppressed = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")[-1]
    assert suppressed["suppression_reason"] == "features_snapshot_missing_or_stale"


def test_position_policy_sidecar_normalizes_position_tracking_snapshot_for_nonzero_position(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="shadow",
                               recommend_soft_close_at=0.45),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(
        _event(
            positions_last_ts_ms=now_ms,
            positions=[
                {
                    "symbol": "BTCUSDT",
                    "net_position": "0.10",
                    "avg_entry_price": "100.0",
                }
            ],
        )
    )
    sidecar.on_features_calculated(
        _event(
            symbol="BTCUSDT",
            ts_ms=now_ms + 1,
            orderbook_imbalance=-1.0,
            price_vs_vwap_bps=-80.0,
            signal_score=-0.5,
        )
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2,
               regime="TREND_DOWN", confidence=0.10)
    )

    evaluated = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_EVALUATED")[-1]
    assert evaluated["position_snapshot"]["portfolio_position_amt"] == "0.10"
    assert evaluated["position_snapshot"]["portfolio_entry_price"] == "100.0"
    assert evaluated["position_snapshot"]["portfolio_snapshot_status"] == "present"
    assert evaluated["portfolio_correlation"]["positions_last_ts_ms"] == now_ms
    assert evaluated["portfolio_correlation"]["portfolio_position_amt"] == "0.10"


def test_position_policy_sidecar_retains_positions_last_ts_ms_for_symbol_snapshot(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="shadow"),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(
        _event(
            positions_last_ts_ms=now_ms,
            positions=[
                {
                    "symbol": "BTCUSDT",
                    "net_position": "0.10",
                    "avg_entry_price": "100.0",
                }
            ],
        )
    )

    suppressed = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")[-1]
    assert suppressed["portfolio_correlation"]["positions_last_ts_ms"] == now_ms
    assert suppressed["freshness_snapshot"]["portfolio_fresh"] is True


def test_position_policy_sidecar_present_zero_net_position_is_flat_not_missing(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="shadow"),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(
        _event(
            positions_last_ts_ms=now_ms,
            positions=[
                {
                    "symbol": "BTCUSDT",
                    "net_position": "0",
                    "avg_entry_price": "100.0",
                }
            ],
        )
    )
    sidecar.on_features_calculated(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 1,
               orderbook_imbalance=-0.5, signal_score=-0.1)
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2,
               regime="TREND_DOWN", confidence=0.10)
    )

    suppressed = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")[-1]
    assert suppressed["suppression_reason"] == "portfolio_flat_while_local_lifecycle_active"
    assert suppressed["position_snapshot"]["portfolio_position_amt"] == "0"
    assert suppressed["position_snapshot"]["portfolio_snapshot_status"] == "present"


def test_position_policy_sidecar_absent_symbol_fails_closed_without_zero_overwrite(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="shadow"),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(
        _event(
            positions_last_ts_ms=now_ms,
            positions=[
                {
                    "symbol": "ETHUSDT",
                    "net_position": "1.0",
                    "avg_entry_price": "2000.0",
                }
            ],
        )
    )
    sidecar.on_features_calculated(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 1,
               orderbook_imbalance=-0.5, signal_score=-0.1)
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2,
               regime="TREND_DOWN", confidence=0.10)
    )

    suppressed = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")[-1]
    assert suppressed["suppression_reason"] == "portfolio_snapshot_missing_or_stale"
    assert suppressed["position_snapshot"]["portfolio_position_amt"] is None
    assert suppressed["position_snapshot"]["portfolio_snapshot_status"] == "symbol_absent"
    assert suppressed["portfolio_correlation"]["portfolio_position_amt"] is None


def test_position_policy_sidecar_malformed_positions_payload_fails_closed(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="shadow"),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(
        _event(
            positions_last_ts_ms=now_ms,
            positions="bad-payload",
        )
    )
    sidecar.on_features_calculated(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 1,
               orderbook_imbalance=-0.5, signal_score=-0.1)
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2,
               regime="TREND_DOWN", confidence=0.10)
    )

    suppressed = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")[-1]
    assert suppressed["suppression_reason"] == "portfolio_snapshot_missing_or_stale"
    assert suppressed["position_snapshot"]["portfolio_position_amt"] is None
    assert suppressed["position_snapshot"]["portfolio_snapshot_status"] == "positions_malformed"


def test_position_policy_sidecar_empty_portfolio_remains_missing_snapshot(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="shadow"),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(
        _event(
            positions_last_ts_ms=now_ms,
            positions=[],
        )
    )
    sidecar.on_features_calculated(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 1,
               orderbook_imbalance=-0.5, signal_score=-0.1)
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2,
               regime="TREND_DOWN", confidence=0.10)
    )

    suppressed = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")[-1]
    assert suppressed["suppression_reason"] == "portfolio_snapshot_missing_or_stale"
    assert suppressed["position_snapshot"]["portfolio_position_amt"] is None
    assert suppressed["position_snapshot"]["portfolio_snapshot_status"] == "symbol_absent"


def test_position_policy_sidecar_malformed_payload_emits_fail_closed_suppression(tmp_path: Path) -> None:
    bus = RecordingBus()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(tmp_path, mode="shadow"),
        bus=bus,
        manage_flow_getter=lambda symbol: DummyManageFlow(),
        known_symbols_getter=lambda: set(),
    )

    sidecar.on_features_calculated(_event(ts_ms=123))

    suppressed = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")[-1]
    assert suppressed["symbol"] == "__UNKNOWN__"
    assert suppressed["suppression_reason"] == "malformed_payload:missing_symbol"


def test_execpos_position_policy_sidecar_mode_wiring_and_ordering(fsm_config, tmp_path: Path) -> None:
    fsm_config.trading.execution.watchdog.check_interval_ms = 1_000
    fsm_config.trading.execution.watchdog.rps_limit = 10
    fsm_config.domains.execution_position.position_policy_sidecar = _sidecar_config(
        tmp_path, mode="shadow")

    bus = RecordingBus()
    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"), patch(
        "apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"
    ):
        fsm = ExecPosFSM(config=fsm_config, fsm=bus, shadow_mode=True)

    assert fsm._position_policy_sidecar is not None
    assert "EVT:POSITION_POLICY_SIDECAR_MODE_ACTIVE" in _topics(bus)

    call_order: list[str] = []
    fsm._handle_cancel_event = lambda event: call_order.append("incumbent")
    fsm._position_policy_sidecar = SimpleNamespace(
        on_order_state_changed=lambda event: call_order.append("sidecar"),
        on_execution_close_reconciled=lambda event: call_order.append(
            "reconcile"),
        on_portfolio_state_updated=lambda event: None,
        on_order_fill=lambda event: None,
        on_features_calculated=lambda event: None,
        on_regime_detected=lambda event: None,
    )

    fsm._on_order_state_changed(
        _event(symbol="BTCUSDT", status="CANCELED", terminal_non_fill=True))
    fsm._on_execution_close_reconciled(_event(
        symbol="BTCUSDT", ts_ms=42, source="guardian", business_close_reconciled=True, why="test"))

    assert call_order == ["incumbent", "sidecar", "reconcile"]


def test_execpos_disable_mode_skips_sidecar_bootstrap(fsm_config, tmp_path: Path) -> None:
    fsm_config.trading.execution.watchdog.check_interval_ms = 1_000
    fsm_config.trading.execution.watchdog.rps_limit = 10
    fsm_config.domains.execution_position.position_policy_sidecar = _sidecar_config(
        tmp_path, mode="disable")

    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"), patch(
        "apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"
    ):
        fsm = ExecPosFSM(config=fsm_config,
                         fsm=RecordingBus(), shadow_mode=True)

    assert fsm._position_policy_sidecar is None
