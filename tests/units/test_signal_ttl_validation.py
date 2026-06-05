from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from decimal import Decimal

from apps.reference.domains.decision_making.core.facade import DecisionMaking


@dataclass
class _Event:
    pld: dict


class _MockSystemMarketData:
    bar_ttl_ms = 10000
    bar_event_age_mode = "received"


class _MockSystem:
    market_data = _MockSystemMarketData()


class _MockFeaturesConfig:
    ttl_sec = 2.0


class _MockDomainConfig:
    def __init__(self) -> None:
        self.features = _MockFeaturesConfig()
        self.arming = MagicMock()
        self.qos = MagicMock()
        self.position_sizing = MagicMock()
        self.risk_skew = MagicMock()
        self.flip = SimpleNamespace(enabled=True)
        self.regime_thresholds = {}
        self.regime_threshold_multipliers = {}
        self.gates = MagicMock()
        self.behavior_fsm = MagicMock()
        self.bar_gating = MagicMock()

        self.arming.require_regime_warmup = False
        self.arming.retry_backoff_ms = 100
        self.arming.max_attempts = 1
        self.features.ttl_sec = 2.0
        self.qos.mode = "performance"
        self.qos.symbol_cooldown_sec = 0
        self.qos.enforce = False
        self.position_sizing.min_position_size_usd = 10.0
        self.position_sizing.max_position_notional = 1000.0
        self.position_sizing.min_notional_hard_stop = 5.0
        self.position_sizing.liquidity_based_cap_usd = 50000.0
        self.position_sizing.max_position_notional_hard_stop = 2000.0
        self.risk_skew.enabled = False


class _MockDomainsConfig:
    risk_management = MagicMock()
    position_tracking = MagicMock()
    decision_making = MagicMock()


class _MockConfig:
    system = _MockSystem()
    trading = MagicMock()
    strategies_registry = None
    domains = _MockDomainsConfig()


class _MockClock:
    def __init__(self) -> None:
        self._now = 1705000000000

    def now_ms(self) -> int:
        return self._now

    def now_sec(self) -> float:
        return self._now / 1000.0


def test_ttl_gate_uses_signal_ts_ms() -> None:
    clock = _MockClock()

    with patch(
        "apps.reference.domains.decision_making.core.facade.DomainConfigResolver"
    ) as mock_resolver:
        mock_resolver.return_value.get_decision_making.return_value = _MockDomainConfig()

        dm = DecisionMaking(MagicMock(), _MockConfig())
        dm._clock = clock
        dm.latest_portfolio = {"equity": "1000"}

        dm._record_blocked_intent = MagicMock()
        dm._emit_trade_intent_rejected = MagicMock()
        dm._emit_intent_deferred_v1 = MagicMock()
        dm._check_strategy_arbitration = MagicMock(return_value={"allowed": True})
        dm._calculate_position_size = MagicMock(
            return_value=(Decimal("1"), "ok", None, {})
        )
        dm._precheck_exposure_cache = MagicMock(return_value=True)
        dm._warmup_gate_before_trade_intent = MagicMock(return_value=False)
        dm._get_aurora_instrument_cfg = MagicMock(return_value=None)
        dm._degraded_context_gate_should_defer = MagicMock(return_value=False)
        dm._handle_flip_orchestration = MagicMock(return_value=None)
        dm._qos_enabled_for_strategy = MagicMock(return_value=False)
        dm.logger = MagicMock()
        dm._gateway.logger = dm.logger  # sync: gateway captures logger at init time

        dm.symbol_states["BTCUSDT"]["risk"] = {
            "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0}
        }

        stale_ts = clock.now_ms() - 20000
        evt = _Event(
            pld={
                "strategy_id": "aurora",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "rid": "rid-1",
                "why_chain": [],
                "readiness": {"warmup_ok": True},
                "price_ctx": {"entry_price": "100.0"},
                "ts_ms": stale_ts,
                "tf_sec": 300,
            }
        )

        dm._on_strategy_signal_gateway(evt)

        dm._record_blocked_intent.assert_called_with("BTCUSDT")
        dm.logger.info.assert_called()