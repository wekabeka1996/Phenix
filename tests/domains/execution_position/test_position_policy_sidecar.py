from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.config_models import PositionPolicySidecarConfig
from apps.reference.core.time import MockClock, get_clock
from apps.reference.domains.execution_position.flows.close.fsm_close import CloseState
from apps.reference.domains.execution_position.flows.manage.fsm_manage import ManageState
from apps.reference.domains.execution_position.sidecar.position_policy_sidecar import (
    PositionPolicySidecar,
)
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from vfoundation.core.protocol import Message


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

    def clear(self) -> None:
        self.events.clear()


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
        self._observed_fee_usd = None

    def has_active_lifecycle(self) -> bool:
        return self._active


def _sidecar_config(
    tmp_path: Path,
    *,
    mode: str = "shadow",
    recommend_soft_close_at: float = 0.70,
    profitability_guard_enabled: bool = True,
) -> PositionPolicySidecarConfig:
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
                "enabled": profitability_guard_enabled,
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
            "peak_giveback_close": {
                "enabled": False,
                "edge_arm_usd": 25.0,
                "giveback_trigger_pct": 50.0,
            },
            "shadow_percent_notional_arm": {
                "enabled": True,
                "candidate_pcts": [0.02, 0.05, 0.07],
            },
            "shadow_fee_aware_arm": {
                "enabled": True,
                "fee_source_priority": [
                    "realized_lifecycle_fee",
                    "order_log_fee",
                    "configured_fee_model",
                ],
                "candidate_fee_multiples": [1.0, 1.5, 2.0],
                "configured_fee_model": {
                    "enabled": False,
                    "round_trip_fee_bps": None,
                },
                "optional_pct_notional_floor": {
                    "enabled": True,
                    "candidate_pcts": [0.02, 0.05],
                },
            },
        }
    )


def _event(**payload):
    return SimpleNamespace(pld=payload)


def _topics(bus: RecordingBus) -> list[str]:
    return [topic for topic, _, _ in bus.events]


def _payloads(bus: RecordingBus, topic: str) -> list[dict]:
    return [payload for recorded_topic, payload, _ in bus.events if recorded_topic == topic]


def test_idle_suppression_is_rate_limited_with_heartbeat(tmp_path: Path) -> None:
    bus = RecordingBus()
    clock = MockClock(start_ms=1_000_000)
    module_path = (
        "apps.reference.domains.execution_position.sidecar."
        "position_policy_sidecar.get_clock"
    )

    with patch(module_path, return_value=clock):
        sidecar = PositionPolicySidecar(
            config=_sidecar_config(tmp_path, mode="shadow"),
            bus=bus,
            manage_flow_getter=lambda symbol: None,
            known_symbols_getter=lambda: {"BTCUSDT"},
        )
        event = _event(positions_last_ts_ms=clock.now_ms(), positions=[])
        sidecar.on_portfolio_state_updated(event)
        sidecar.on_portfolio_state_updated(event)

        suppressed = [
            payload
            for payload in _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")
            if payload.get("suppression_reason") == "no_manage_flow_for_symbol"
        ]
        assert len(suppressed) == 1

        clock.advance_ms(120_000)
        sidecar.on_portfolio_state_updated(
            _event(positions_last_ts_ms=clock.now_ms(), positions=[])
        )

    suppressed = [
        payload
        for payload in _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_SUPPRESSED")
        if payload.get("suppression_reason") == "no_manage_flow_for_symbol"
    ]
    assert len(suppressed) == 2
    assert suppressed[-1]["dedup_detail"]["suppressed_count"] == 1


def test_position_policy_sidecar_recommends_and_emits_bounded_close_request_in_enable_mode(tmp_path: Path) -> None:
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
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" in _topics(bus)
    assert "EVT:POSITION_POLICY_SIDECAR_ACTION_SKIPPED" not in _topics(bus)

    recommended = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")[-1]
    request = _payloads(bus, "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST")[-1]
    assert recommended["trace_id"] == request["trace_id"]
    assert request["request_id"].startswith("ppsreq:pps:BTCUSDT:")
    assert 0.0 <= recommended["score_snapshot"]["soft_close_pressure"] <= 1.0
    assert recommended["policy_source"] == "position_policy_sidecar"
    assert recommended["peak_giveback_snapshot"]["policy_enabled"] is False
    assert recommended["peak_giveback_snapshot"]["peak_giveback_state"] == "peak_giveback_disabled"
    assert request["policy_source"] == "position_policy_sidecar"
    assert request["requested_action"] == "SOFT_CLOSE"
    assert request["target_mode"] == "symbol_current_net_only"
    assert request["allowed_action_scope"]["soft_close_symbol_current_net_only"] is True
    assert request["allowed_action_scope"]["partial_reduce"] is False
    assert request["allowed_action_scope"]["bracket_mutation"] is False
    assert request["allowed_action_scope"]["exact_targeting"] is False

    log_lines = (
        tmp_path / "trade_lifecycle.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert any(
        '"record_kind": "position_policy_sidecar"' in line for line in log_lines)
    assert any(
        '"event_type": "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED"' in line
        for line in log_lines
    )


def test_position_policy_sidecar_shadow_mode_does_not_emit_close_request(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(
            tmp_path,
            mode="shadow",
            recommend_soft_close_at=0.30,
            profitability_guard_enabled=False,
        ),
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
                    "markPrice": "100.0",
                    "unrealizedProfit": "0.0",
                }
            ],
        )
    )
    sidecar.on_features_calculated(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 1,
               orderbook_imbalance=0.0, signal_score=0.0)
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2,
               regime="TREND_DOWN", confidence=0.10)
    )

    assert "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED" in _topics(bus)
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" not in _topics(bus)


def test_position_policy_sidecar_does_not_recommend_below_threshold(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(
            tmp_path,
            mode="shadow",
            profitability_guard_enabled=False,
        ),
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
                    "markPrice": "100.0",
                    "unrealizedProfit": "0.0",
                }
            ],
        )
    )
    sidecar.on_features_calculated(
        _event(
            symbol="BTCUSDT",
            ts_ms=now_ms + 1,
            orderbook_imbalance=0.0,
            signal_score=0.0,
        )
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2,
               regime="TREND_DOWN", confidence=0.10)
    )

    assert "EVT:POSITION_POLICY_SIDECAR_EVALUATED" in _topics(bus)
    assert "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED" not in _topics(bus)

    evaluated = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_EVALUATED")[-1]
    assert evaluated["score_snapshot"]["soft_close_pressure"] == 0.3


def test_position_policy_sidecar_recommends_at_threshold_boundary(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    now_ms = get_clock().now_ms()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(
            tmp_path,
            mode="shadow",
            recommend_soft_close_at=0.30,
            profitability_guard_enabled=False,
        ),
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
                    "markPrice": "100.0",
                    "unrealizedProfit": "0.0",
                }
            ],
        )
    )
    sidecar.on_features_calculated(
        _event(
            symbol="BTCUSDT",
            ts_ms=now_ms + 1,
            orderbook_imbalance=0.0,
            signal_score=0.0,
        )
    )
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2,
               regime="TREND_DOWN", confidence=0.10)
    )

    assert "EVT:POSITION_POLICY_SIDECAR_EVALUATED" in _topics(bus)
    assert "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED" in _topics(bus)

    recommended = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED")[-1]
    assert recommended["score_snapshot"]["soft_close_pressure"] == 0.3


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


def test_peak_giveback_snapshot_consumes_canonical_unrealized_pnl_fields(tmp_path: Path) -> None:
    bus = RecordingBus()
    manage_flow = DummyManageFlow(side="BUY", qty="1.0", entry_price="100.0")

    cfg = _sidecar_config(tmp_path, mode="enable")
    cfg.peak_giveback_close.enabled = True
    cfg.profitability_guard.enabled = False

    sidecar = PositionPolicySidecar(
        config=cfg,
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )

    sidecar.on_portfolio_state_updated(_event(positions=[
        {
            "symbol": "BTCUSDT",
            "net_position": "1.0",
            "avg_entry_price": "100.0",
            "markPrice": "110.0",
            "unrealizedPnl": "10.0",
            "unrealizedPnlPct": "10.0",
            "venues": ["binance"],
        }
    ]))
    sidecar.on_features_calculated(_event(symbol="BTCUSDT", signal_score=0.0))
    sidecar.on_regime_detected(
        _event(symbol="BTCUSDT", regime="MEAN_REVERSION", confidence=1.0))

    evaluated = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_EVALUATED")[-1]
    snapshot = evaluated["peak_giveback_snapshot"]

    assert snapshot["mark_price"] == 110.0
    assert snapshot["unrealized_pnl_usdt"] == 10.0
    assert snapshot["unrealized_pnl_pct"] == 10.0
    assert snapshot["current_edge_usd"] == 10.0
    assert snapshot["null_reasons"] == {}


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
    mode_active = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_MODE_ACTIVE")[-1]
    assert mode_active["sidecar_config_snapshot"]["mode"] == "shadow"
    assert mode_active["sidecar_config_snapshot"]["peak_giveback_close"] == {
        "enabled": False,
        "edge_arm_usd": 25.0,
        "giveback_trigger_pct": 50.0,
    }
    assert mode_active["sidecar_config_snapshot"]["freshness"] == {
        "portfolio_max_age_ms": 15_000,
        "features_max_age_ms": 15_000,
        "regime_max_age_ms": 15_000,
        "order_state_max_age_ms": 15_000,
    }

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


def test_execpos_position_policy_close_request_state_links_request_to_reconcile(fsm_config, tmp_path: Path) -> None:
    fsm_config.trading.execution.watchdog.check_interval_ms = 1_000
    fsm_config.trading.execution.watchdog.rps_limit = 10
    fsm_config.domains.execution_position.position_policy_sidecar = _sidecar_config(
        tmp_path, mode="enable", recommend_soft_close_at=0.45
    )

    bus = RecordingBus()
    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"), patch(
        "apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"
    ):
        fsm = ExecPosFSM(config=fsm_config, fsm=bus, shadow_mode=True)

    now_ms = get_clock().now_ms()
    manage_flow = fsm.manage_flow("BTCUSDT")
    manage_flow.state = ManageState.TRACKING
    manage_flow.symbol = "BTCUSDT"
    manage_flow.position_side = "BUY"
    manage_flow.position_qty = "0.10"
    manage_flow.position_entry_price = "100.0"
    manage_flow.position_open_ts = 1_000.0

    portfolio_payload = {
        "positions_last_ts_ms": now_ms,
        "positions": [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.10",
                "entryPrice": "100.0",
                "markPrice": "99.2",
                "unrealizedProfit": "-0.08",
            }
        ],
    }
    fsm._latest_portfolio_state = dict(portfolio_payload)

    sidecar = fsm._position_policy_sidecar
    assert sidecar is not None
    sidecar.on_portfolio_state_updated(_event(**portfolio_payload))
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

    request = _payloads(bus, "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST")[-1]
    states = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE")
    emitted = [row for row in states if row["request_state"]
               == "close_command_emitted"]
    assert len(emitted) == 1
    assert emitted[0]["request_id"] == request["request_id"]
    assert emitted[0]["trace_id"] == request["trace_id"]
    assert emitted[0]["policy_context"]["policy_source"] == "position_policy_sidecar"
    assert emitted[0]["policy_context"]["allowed_action_scope"]["soft_close_symbol_current_net_only"] is True
    assert emitted[0]["execution_shadow_mode"] is True
    assert emitted[0]["adapter_present"] is False
    close_flow = fsm.close_flow("BTCUSDT")
    assert close_flow.last_close_reason == "position_policy_sidecar_soft_close"
    assert close_flow.last_close_symbol == "BTCUSDT"
    assert close_flow.last_close_qty is None

    fsm._on_execution_close_reconciled(
        Message(
            op="EVT",
            verb="EXECUTION_CLOSE_RECONCILED",
            src="execution_position",
            dst="execution_position",
            rid=request["request_id"],
            why="guardian:close_reconciled",
            pld={
                "symbol": "BTCUSDT",
                "rid": request["request_id"],
                "source": "guardian_reconcile",
                "ts_ms": 1_000_100,
                "business_close_reconciled": True,
                "why": "guardian:close_reconciled",
            },
        )
    )

    reconciled = [
        row
        for row in _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE")
        if row["request_state"] == "reconciled"
    ]
    assert len(reconciled) == 1
    assert reconciled[0]["request_id"] == request["request_id"]
    assert reconciled[0]["business_close_reconciled"] is True
    assert reconciled[0]["reconcile_source"] == "guardian_reconcile"
    assert manage_flow.state == ManageState.FLAT
    assert manage_flow.has_active_lifecycle() is False
    assert close_flow.state == CloseState.FLAT
    assert close_flow.last_close_reason is None


def test_execpos_position_policy_close_request_suppresses_when_manage_flow_closing(fsm_config, tmp_path: Path) -> None:
    fsm_config.trading.execution.watchdog.check_interval_ms = 1_000
    fsm_config.trading.execution.watchdog.rps_limit = 10
    fsm_config.domains.execution_position.position_policy_sidecar = _sidecar_config(
        tmp_path, mode="enable", recommend_soft_close_at=0.45
    )

    bus = RecordingBus()
    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"), patch(
        "apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"
    ):
        fsm = ExecPosFSM(config=fsm_config, fsm=bus, shadow_mode=True)

    now_ms = get_clock().now_ms()
    manage_flow = fsm.manage_flow("BTCUSDT")
    manage_flow.state = ManageState.TRACKING
    manage_flow.symbol = "BTCUSDT"
    manage_flow.position_side = "BUY"
    manage_flow.position_qty = "0.10"
    manage_flow.position_entry_price = "100.0"
    manage_flow.position_open_ts = 1_000.0
    manage_flow._closing_position = True

    fsm._latest_portfolio_state = {
        "positions_last_ts_ms": now_ms,
        "positions": [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.10",
                "entryPrice": "100.0",
                "markPrice": "99.2",
                "unrealizedProfit": "-0.08",
            }
        ],
    }

    request_payload = {
        "ts_ms": now_ms + 10,
        "request_id": "ppsreq:test-closing",
        "trace_id": "pps:BTCUSDT:test-closing:1",
        "symbol": "BTCUSDT",
        "sidecar_version": "1.0.0",
        "mode": "enable",
        "evaluation_mode": "bounded_soft_close_policy",
        "event_type": "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
        "source_event_type": "POSITION_POLICY_SIDECAR_RECOMMENDED",
        "requested_action": "SOFT_CLOSE",
        "requested_qty": None,
        "target_mode": "symbol_current_net_only",
        "policy_source": "position_policy_sidecar",
        "action_package_version": "phase2_action_package_v1",
        "allowed_action_scope": {
            "soft_close_symbol_current_net_only": True,
            "partial_reduce": False,
            "bracket_mutation": False,
            "exact_targeting": False,
        },
        "reason_codes": ["trigger:regime_detected", "recommend_soft_close_threshold_met"],
        "score_snapshot": {"soft_close_pressure": 0.6},
        "position_snapshot": {"symbol": "BTCUSDT", "side": "BUY"},
        "feature_ref": {},
        "regime_ref": {},
        "freshness_snapshot": {},
        "fill_correlation": {},
        "portfolio_correlation": {},
    }

    fsm._position_policy_mediator.on_position_policy_close_request(
        _event(**request_payload))

    states = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE")
    suppressed = [
        row for row in states if row["request_state"] == "suppressed"]
    assert len(suppressed) == 1
    assert suppressed[0]["request_id"] == "ppsreq:test-closing"
    assert suppressed[0]["suppression_reason"] == "manage_flow_close_in_progress"
    assert suppressed[0]["incumbent_owner"] == "ManageFlowFSM"
    assert fsm.close_flow("BTCUSDT").last_close_reason is None


def test_execpos_position_policy_close_request_forbidden_capabilities_fail_closed(fsm_config, tmp_path: Path) -> None:
    fsm_config.trading.execution.watchdog.check_interval_ms = 1_000
    fsm_config.trading.execution.watchdog.rps_limit = 10
    fsm_config.domains.execution_position.position_policy_sidecar = _sidecar_config(
        tmp_path, mode="enable", recommend_soft_close_at=0.45
    )

    bus = RecordingBus()
    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"), patch(
        "apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"
    ):
        fsm = ExecPosFSM(config=fsm_config, fsm=bus, shadow_mode=True)

    manage_flow = fsm.manage_flow("BTCUSDT")
    manage_flow.state = ManageState.TRACKING
    manage_flow.symbol = "BTCUSDT"
    manage_flow.position_side = "BUY"
    manage_flow.position_qty = "0.10"
    manage_flow.position_entry_price = "100.0"
    manage_flow.position_open_ts = 1_000.0
    fsm._latest_portfolio_state = {
        "positions_last_ts_ms": 1_000_000,
        "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.10"}],
    }

    request_payload = {
        "ts_ms": 1_000_010,
        "request_id": "ppsreq:test-forbidden",
        "trace_id": "pps:BTCUSDT:1000010:1",
        "symbol": "BTCUSDT",
        "sidecar_version": "1.0.0",
        "mode": "enable",
        "evaluation_mode": "bounded_soft_close_policy",
        "event_type": "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
        "source_event_type": "POSITION_POLICY_SIDECAR_RECOMMENDED",
        "requested_action": "SOFT_CLOSE",
        "requested_qty": "0.01",
        "target_mode": "order_id_targeted",
        "policy_source": "position_policy_sidecar",
        "action_package_version": "phase2_action_package_v1",
        "allowed_action_scope": {
            "soft_close_symbol_current_net_only": True,
            "partial_reduce": False,
            "bracket_mutation": False,
            "exact_targeting": False,
        },
        "reason_codes": ["trigger:regime_detected", "recommend_soft_close_threshold_met"],
        "score_snapshot": {"soft_close_pressure": 0.6},
        "position_snapshot": {"symbol": "BTCUSDT", "side": "BUY"},
        "feature_ref": {},
        "regime_ref": {},
        "freshness_snapshot": {},
        "fill_correlation": {},
        "portfolio_correlation": {},
    }

    fsm._position_policy_mediator.on_position_policy_close_request(
        _event(**request_payload))

    states = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE")
    suppressed = [
        row for row in states if row["request_state"] == "suppressed"]
    assert len(suppressed) == 1
    assert suppressed[0]["request_id"] == "ppsreq:test-forbidden"
    assert suppressed[0]["suppression_reason"] == "exact_targeting_forbidden"
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" not in _topics(bus)


def test_execpos_position_policy_close_request_rejects_bracket_mutation_scope(fsm_config, tmp_path: Path) -> None:
    fsm_config.trading.execution.watchdog.check_interval_ms = 1_000
    fsm_config.trading.execution.watchdog.rps_limit = 10
    sidecar_cfg = _sidecar_config(
        tmp_path, mode="enable", recommend_soft_close_at=0.45)
    sidecar_cfg.allowed_actions.bracket_mutation = True
    fsm_config.domains.execution_position.position_policy_sidecar = sidecar_cfg

    bus = RecordingBus()
    with patch("apps.reference.domains.execution_position.fsm.OrderGuardian"), patch(
        "apps.reference.domains.execution_position.fsm.OrderTimeoutWatchdog"
    ):
        fsm = ExecPosFSM(config=fsm_config, fsm=bus, shadow_mode=True)

    manage_flow = fsm.manage_flow("BTCUSDT")
    manage_flow.state = ManageState.TRACKING
    manage_flow.symbol = "BTCUSDT"
    manage_flow.position_side = "BUY"
    manage_flow.position_qty = "0.10"
    manage_flow.position_entry_price = "100.0"
    manage_flow.position_open_ts = 1_000.0
    fsm._latest_portfolio_state = {
        "positions_last_ts_ms": 1_000_000,
        "positions": [{"symbol": "BTCUSDT", "positionAmt": "0.10"}],
    }

    request_payload = {
        "ts_ms": 1_000_010,
        "request_id": "ppsreq:test-bracket-mutation",
        "trace_id": "pps:BTCUSDT:1000010:2",
        "symbol": "BTCUSDT",
        "sidecar_version": "1.0.0",
        "mode": "enable",
        "evaluation_mode": "bounded_soft_close_policy",
        "event_type": "POSITION_POLICY_SIDECAR_CLOSE_REQUESTED",
        "source_event_type": "POSITION_POLICY_SIDECAR_RECOMMENDED",
        "requested_action": "SOFT_CLOSE",
        "requested_qty": None,
        "target_mode": "symbol_current_net_only",
        "policy_source": "position_policy_sidecar",
        "action_package_version": "phase2_action_package_v1",
        "allowed_action_scope": {
            "soft_close_symbol_current_net_only": True,
            "partial_reduce": False,
            "bracket_mutation": True,
            "exact_targeting": False,
        },
        "reason_codes": ["trigger:regime_detected", "recommend_soft_close_threshold_met"],
        "score_snapshot": {"soft_close_pressure": 0.6},
        "position_snapshot": {"symbol": "BTCUSDT", "side": "BUY"},
        "feature_ref": {},
        "regime_ref": {},
        "freshness_snapshot": {},
        "fill_correlation": {},
        "portfolio_correlation": {},
    }

    fsm._position_policy_mediator.on_position_policy_close_request(
        _event(**request_payload))

    states = _payloads(bus, "EVT:POSITION_POLICY_SIDECAR_CLOSE_REQUEST_STATE")
    suppressed = [
        row for row in states if row["request_state"] == "suppressed"]
    assert len(suppressed) == 1
    assert suppressed[0]["request_id"] == "ppsreq:test-bracket-mutation"
    assert suppressed[0]["suppression_reason"] == "bracket_mutation_forbidden"
    assert "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST" not in _topics(bus)


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
