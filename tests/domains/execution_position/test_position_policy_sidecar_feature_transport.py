import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.config_models import PositionPolicySidecarConfig
from apps.reference.core.time import MockClock, get_clock
from apps.reference.domains.execution_position.sidecar.position_policy_sidecar import PositionPolicySidecar
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
            handler(SimpleNamespace(pld=payload, verb=topic.split(":")[-1], rid=payload.get("rid")))

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

def _sidecar_config(tmp_path: Path) -> PositionPolicySidecarConfig:
    return PositionPolicySidecarConfig.model_validate(
        {
            "mode": "shadow",
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
                "enabled": False,
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
                "recommend_soft_close_at": 0.3,
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

def test_feature_transport_ts_key(tmp_path: Path) -> None:
    """Verify that features calculation event payload with 'ts' (milliseconds epoch)
    is correctly parsed/cached by Sidecar instead of using get_clock().now_ms() fallback.
    """
    bus = RecordingBus()
    manage_flow = DummyManageFlow()
    
    clock = MockClock(start_ms=100_000)
    module_path = "apps.reference.domains.execution_position.sidecar.position_policy_sidecar.get_clock"
    
    with patch(module_path, return_value=clock):
        sidecar = PositionPolicySidecar(
            config=_sidecar_config(tmp_path),
            bus=bus,
            manage_flow_getter=lambda symbol: manage_flow,
            known_symbols_getter=lambda: {"BTCUSDT"},
        )
        
        # 1. Update portfolio (synchronized to clock time 100_000)
        sidecar.on_portfolio_state_updated(
            _event(
                positions_last_ts_ms=100_000,
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
        
        # 2. Receive feature calculation event with historical timestamp ts = 95_000.
        # Note: We pass 'ts' (the canonical schema key) and NOT 'ts_ms'.
        sidecar.on_features_calculated(
            _event(
                symbol="BTCUSDT",
                ts=95_000,
                features={
                    "obi": "-0.5",
                    "tfi": "0.1",
                    "delta_price": "0.0",
                    "absorption": "0.0",
                    "price": "99.5",
                },
                warmup={"full_ready": True, "ticks_seen": 100},
                price_motion={"ret_10s": 0.0, "ret_60s": 0.0, "ret_300s": 0.0},
            )
        )
        
        # Under pre-patch, ts=95_000 is ignored, and fallback is get_clock().now_ms() = 100_000.
        # Under post-patch, ts=95_000 should be parsed as 95_000.
        state = sidecar._state("BTCUSDT")
        assert state.features.ts_ms == 95_000, f"Expected 95000, got {state.features.ts_ms}"
