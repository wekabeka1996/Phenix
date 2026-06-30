"""
Phase 6 - Sidecar Action-Bearing Contract

Behavioral coverage for mode-specific sidecar emissions.
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from apps.reference.config_models import PositionPolicySidecarConfig
from apps.reference.core.time import get_clock
from apps.reference.domains.execution_position.flows.manage.fsm_manage import ManageState
from apps.reference.domains.execution_position.sidecar.position_policy_sidecar import (
    PositionPolicySidecar,
)


CLOSE_REQUEST_TOPIC = "CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST"


class RecordingBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict, dict]] = []

    def emit(self, topic, payload=None, **kwargs):
        self.events.append((topic, payload or {}, kwargs))


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
        self.state = SimpleNamespace(value=ManageState.TRACKING.value)
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
    peak_giveback_enabled: bool = False,
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
                "enabled": peak_giveback_enabled,
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


def _build_sidecar(
    tmp_path: Path,
    *,
    mode: str,
    recommend_soft_close_at: float = 0.45,
    profitability_guard_enabled: bool = True,
    peak_giveback_enabled: bool = False,
) -> tuple[PositionPolicySidecar, RecordingBus, DummyManageFlow]:
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    sidecar = PositionPolicySidecar(
        config=_sidecar_config(
            tmp_path,
            mode=mode,
            recommend_soft_close_at=recommend_soft_close_at,
            profitability_guard_enabled=profitability_guard_enabled,
            peak_giveback_enabled=peak_giveback_enabled,
        ),
        bus=bus,
        manage_flow_getter=lambda symbol: manage_flow if symbol == "BTCUSDT" else None,
        known_symbols_getter=lambda: {"BTCUSDT"},
    )
    return sidecar, bus, manage_flow


def test_close_request_emission_guarded_by_enable_check(tmp_path: Path) -> None:
    sidecar, bus, _ = _build_sidecar(
        tmp_path,
        mode="shadow",
        profitability_guard_enabled=False,
    )
    now_ms = get_clock().now_ms()

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
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2, regime="TREND_DOWN", confidence=0.10)
    )

    assert "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED" in _topics(bus)
    assert CLOSE_REQUEST_TOPIC not in _topics(bus)


def test_peak_giveback_close_command_also_guarded_by_enable(tmp_path: Path) -> None:
    sidecar, bus, _ = _build_sidecar(tmp_path, mode="shadow")
    state = sidecar._state("BTCUSDT")
    base_payload = sidecar._base_payload(
        symbol="BTCUSDT",
        trace_id="pps:BTCUSDT:test",
        trigger_event="REGIME_DETECTED",
        state=state,
        manage_flow=DummyManageFlow(),
    )

    sidecar._handle_peak_giveback_trigger(
        symbol="BTCUSDT",
        state=state,
        base_payload=base_payload,
        giveback_result={
            "peak_edge_usd": 35.0,
            "current_edge_usd": 12.0,
            "giveback_pct": 65.0,
            "threshold_pct": 50.0,
        },
        trigger_event="REGIME_DETECTED",
    )

    assert "EVT:POSITION_POLICY_SIDECAR_RECOMMENDED" in _topics(bus)
    assert CLOSE_REQUEST_TOPIC not in _topics(bus)


def test_disable_mode_causes_early_return_before_any_emit(tmp_path: Path) -> None:
    sidecar, bus, _ = _build_sidecar(tmp_path, mode="disable")
    now_ms = get_clock().now_ms()

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
        _event(symbol="BTCUSDT", ts_ms=now_ms + 2, regime="TREND_DOWN", confidence=0.10)
    )

    assert bus.events == []
