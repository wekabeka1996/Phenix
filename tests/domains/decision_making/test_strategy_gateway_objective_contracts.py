import decimal
import logging
from types import SimpleNamespace
from unittest.mock import patch

from apps.reference.domains.decision_making.gateway.strategy_gateway import StrategyGateway


class _StubEvent:
    def __init__(self, payload):
        self.pld = payload


class _DMStub:
    def __init__(self) -> None:
        self.logger = logging.getLogger("tests.gateway.objective")
        self._clock = SimpleNamespace(now_ms=lambda: 1_700_000_000_000)
        self.fsm = SimpleNamespace(emit=lambda *_args, **_kwargs: None)
        self.features_ttl_sec = 30
        self.symbol_states = {
            "DOGEUSDT": {
                "risk_skew_guard": {},
                "risk": {
                    "risk_parameters": {
                        "is_trading_allowed": True,
                        "risk_score": 0.25,
                    },
                    "tca_budget": {
                        "max_slippage_bps": 10,
                        "max_latency_ms": 250,
                    },
                },
                "features": {"ts": 1_700_000_000_000, "features": {}},
            }
        }
        self.latest_portfolio = {
            "equity_free_usdt": "1000",
            "open_positions_usd": "0",
        }
        self.proposals = []
        self.rejections = []
        self.blocked = []
        self.config = SimpleNamespace(
            domains=SimpleNamespace(
                decision_making=SimpleNamespace(
                    risk_skew=SimpleNamespace(until_refresh_retry_sec=1)
                ),
                risk_management=SimpleNamespace(
                    trading_allowed_thresholds=SimpleNamespace(
                        max_risk_score=0.9)
                ),
                position_tracking=SimpleNamespace(positions_stale_ttl_sec=30),
            ),
            system=SimpleNamespace(
                market_data=SimpleNamespace(bar_ttl_ms=600_000)
            ),
            strategies=SimpleNamespace(mean_reversion=SimpleNamespace(
                enabled=True,
                mode="runtime",
                execution=SimpleNamespace(entry_order_type="MARKET", entry_tif="GTC"),
                decision=SimpleNamespace(),
                safety_gates=SimpleNamespace(enabled=True),
            )),
        )

    def _emit_trade_intent_rejected(self, **kwargs):
        self.rejections.append(kwargs)

    def _record_blocked_intent(self, symbol: str):
        self.blocked.append(symbol)

    def _check_strategy_arbitration(self, symbol: str, strategy_id: str, ts_ms=None, commit=True):
        return {"allowed": True, "reason": None}

    def _emit_reduce_only_close(self, **kwargs):
        raise AssertionError(
            "mean_reversion entry test should not route to reduce-only close")

    def _get_portfolio_position_qty_signed(self, symbol: str):
        return decimal.Decimal("0"), {"symbol": symbol}

    def _get_aurora_instrument_cfg(self, symbol: str):
        return None

    def _degraded_context_gate_should_defer(self, **kwargs):
        return False

    def _handle_flip_orchestration(self, **kwargs):
        return False

    def _qos_enabled_for_strategy(self, strategy_id: str) -> bool:
        return False

    def _calculate_position_size(self, symbol, entry_price_dec, side, sizing_ctx, margin_pct_mult=None):
        return decimal.Decimal("1.0"), "sizing_ok", None, {"order_notional": decimal.Decimal("100.0")}

    def _precheck_exposure_cache(self, symbol: str, side: str, order_notional: float) -> bool:
        return True

    def _warmup_gate_before_trade_intent(self, **kwargs):
        return False

    def _propose_trade_intent(self, **kwargs):
        self.proposals.append(kwargs)


def _objective_trace() -> dict:
    return {
        "trace_id": "obj-mr-1",
        "multiplier": 0.92,
        "objective_score": 0.61,
        "components": {"edge": 0.3, "cost": -0.1},
        "raw_metrics": {"spread_bps": 1.8},
    }


def test_mean_reversion_entry_preserves_canonical_objective_trace_through_gateway() -> None:
    dm = _DMStub()
    gateway = StrategyGateway(dm)

    event = _StubEvent(
        {
            "strategy_id": "mean_reversion",
            "symbol": "DOGEUSDT",
            "side": "BUY",
            "readiness": {"warmup_ok": True},
            "runtime_permissions": {
                "can_manage_existing_risk": True,
                "can_open_new_risk": True,
                "mode": "OPEN_AND_MANAGE",
            },
            "score": 0.61,
            "scoring": {
                "score": 0.61,
                "decision_score": 0.61,
                "thr_buy": 0.5,
                "thr_sell": 0.45,
                "psi_vector": {"threshold_factor": 0.2},
                "objective": _objective_trace(),
                "regime": "FLAT_NORMAL",
            },
            "price_ctx": {
                "entry_price": "0.12345",
                "stop_price": "0.12000",
                "target_price": "0.13000",
            },
            "regime": "FLAT_NORMAL",
            "bar_close_ts": 1_700_000_000_299,
            "tf_sec": 300,
            "ts_ms": 1_700_000_000_000,
            "rid": "mr-entry-objective-1",
            "why_chain": ["bb_lower_touch"],
        }
    )

    with patch(
        "apps.reference.domains.decision_making.gateway.strategy_gateway.resolve_strategy_entry_prices",
        return_value=("0.12000", "0.13000", {"src": "test"}),
    ):
        gateway.process_signal(event)

    assert not dm.rejections
    assert len(dm.proposals) == 1
    proposal = dm.proposals[0]
    assert proposal["strategy_id"] == "mean_reversion"
    assert proposal["strategy_trace"]["objective"]["trace_id"] == "obj-mr-1"
    assert proposal["strategy_trace"]["signal_score"] == 0.61
    assert proposal["strategy_trace"]["signal_score_abs"] == 0.61
    assert proposal["strategy_trace"]["active_threshold"] == 0.5
    assert proposal["strategy_trace"]["aurora_threshold_factor"] == 0.2
    assert proposal["strategy_trace"]["aurora_pillar_confidence_candidate"] == 1.0
    assert proposal["strategy_trace"]["aurora_raw_score_to_threshold_ratio"] == 3.05
    assert proposal["strategy_trace"]["features_ts_ms"] == 1_700_000_000_000
    assert proposal["strategy_trace"]["detector_event"]["bar_close_ts_ms"] == 1_700_000_000_299
    assert proposal["strategy_trace"]["score_lineage"]["path"]
    lineage_fields = {
        record["field"]
        for record in proposal["strategy_trace"]["score_lineage"]["records"]
    }
    assert {"signal_score", "final_score_raw", "aurora_pillar_confidence_candidate"}.issubset(
        lineage_fields
    )


def test_mean_reversion_invalid_objective_trace_fails_closed() -> None:
    dm = _DMStub()
    gateway = StrategyGateway(dm)

    event = _StubEvent(
        {
            "strategy_id": "mean_reversion",
            "symbol": "DOGEUSDT",
            "side": "BUY",
            "readiness": {"warmup_ok": True},
            "runtime_permissions": {
                "can_manage_existing_risk": True,
                "can_open_new_risk": True,
                "mode": "OPEN_AND_MANAGE",
            },
            "score": 0.61,
            "scoring": {
                "score": 0.61,
                "objective": {
                    "trace_id": "",
                    "multiplier": 0.92,
                    "objective_score": 0.61,
                    "components": {"edge": 0.3},
                    "raw_metrics": {"spread_bps": 1.8},
                },
                "regime": "FLAT_NORMAL",
            },
            "price_ctx": {"entry_price": "0.12345"},
            "regime": "FLAT_NORMAL",
            "tf_sec": 300,
            "ts_ms": 1_700_000_000_000,
            "rid": "mr-entry-objective-invalid",
            "why_chain": [],
        }
    )

    gateway.process_signal(event)

    assert len(dm.rejections) == 1
    assert dm.rejections[0]["reason_code"] == "WAL_TRACE_INVALID"
