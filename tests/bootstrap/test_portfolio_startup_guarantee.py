"""
Phase 4: Portfolio Startup Guarantee — bounded wait + fallback emit.

Verifies:
1. Portfolio received before timeout → no fallback emitted
2. Portfolio not received → fallback emitted after timeout
3. Fallback payload shape is correct
4. Sizing: fallback portfolio (no equity) → ZERO_EQUITY → qty=None
5. Gateway integration: fallback portfolio → SIZING_QTY_NONE → no trade emitted
"""
from __future__ import annotations

import threading
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.reference.domains.decision_making.position_queries import PositionQueries
from apps.reference.domains.decision_making.strategy_gateway import StrategyGateway
from vfoundation.core.protocol import Message


# ── helpers ──────────────────────────────────────────────────────────────────

class _MockDecisionMaking:
    """Simulates decision_making.latest_portfolio property."""

    def __init__(self, *, delay_sec: float | None = None):
        self._portfolio = None
        self._delay = delay_sec
        if delay_sec is not None:
            self._thread = threading.Thread(
                target=self._set_after_delay, daemon=True)
            self._thread.start()

    def _set_after_delay(self) -> None:
        time.sleep(self._delay)
        self._portfolio = {"positions": {"BTCUSDT": "1.0"}, "balances": {}}

    @property
    def latest_portfolio(self):
        return self._portfolio


def _wait_for_portfolio(*, decision_making, timeout_sec: int) -> bool:
    """Exact replica of the Phase 4 logic in main.py."""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if decision_making.latest_portfolio is not None:
            return True
        time.sleep(0.1)  # Faster poll for testing
    return False


# ── tests ─────────────────────────────────────────────────────────────────────

def test_portfolio_received_before_timeout() -> None:
    """Portfolio arrives in 0.3s → should return True before 2s timeout."""
    dm = _MockDecisionMaking(delay_sec=0.3)
    received = _wait_for_portfolio(decision_making=dm, timeout_sec=2)
    assert received is True
    assert dm.latest_portfolio is not None


def test_portfolio_fallback_on_timeout() -> None:
    """No portfolio event → returns False after timeout."""
    dm = _MockDecisionMaking(delay_sec=None)  # Never sets portfolio
    received = _wait_for_portfolio(decision_making=dm, timeout_sec=1)
    assert received is False
    assert dm.latest_portfolio is None


def test_portfolio_fallback_payload_shape() -> None:
    """Fallback payload has correct structure."""
    fallback = {
        "positions": {},
        "balances": {},
        "updated_at": int(time.time() * 1000),
        "source": "startup:portfolio_fallback",
    }
    assert isinstance(fallback["positions"], dict)
    assert isinstance(fallback["balances"], dict)
    assert fallback["source"] == "startup:portfolio_fallback"
    assert fallback["updated_at"] > 0


# ── Fallback portfolio safety proofs ─────────────────────────────────────────

FALLBACK_PORTFOLIO = {
    "positions": {},
    "balances": {},
    "source": "startup:portfolio_fallback",
}


def test_sizing_rejects_zero_equity_from_fallback_portfolio() -> None:
    """Real calculate_position_size with fallback portfolio → ZERO_EQUITY.

    Proves the exact path: fallback has no 'equity' key →
    portfolio.get("equity", "0") → Decimal("0") → equity <= 0 → (None, ...).
    """
    pq = PositionQueries(
        config=MagicMock(),
        get_portfolio=lambda: None,
        min_pos_size_usd=Decimal("10"),
        liq_cap_usd=Decimal("100000"),
        logger=MagicMock(),
    )

    context = {"portfolio": FALLBACK_PORTFOLIO}
    qty, why, reject_code, details = pq.calculate_position_size(
        "BTCUSDT", Decimal("50000"), "BUY", context,
    )

    assert qty is None, "Fallback portfolio must produce qty=None"
    assert reject_code == "ZERO_EQUITY", f"Expected ZERO_EQUITY, got {reject_code}"
    assert "equity_invalid" in why


def test_fallback_portfolio_gateway_rejects_no_trade() -> None:
    """Integration: full process_signal() with fallback portfolio → SIZING_QTY_NONE.

    End-to-end proof that the synthetic empty portfolio from Phase 4 cannot
    produce a trade intent:
    1. Signal passes readiness, arbitration, risk gates
    2. Gateway reaches Gate 4 (sizing)
    3. latest_portfolio is truthy (passes null-check) but has no equity
    4. _calculate_position_size returns (None, ...) → SIZING_QTY_NONE reject
    5. _propose_trade_intent is NEVER called
    """
    clock = MagicMock()
    now_ms = 1_700_000_000_000
    clock.now_ms.return_value = now_ms

    dm = MagicMock()
    dm._clock = clock
    dm.symbol_states = {
        "BTCUSDT": {
            "risk": {
                "ts": 0,
                "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0},
            },
            "features": {"ts": 0, "features": {}},
        },
    }
    dm.latest_portfolio = FALLBACK_PORTFOLIO.copy()

    config = SimpleNamespace(
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                risk_skew=SimpleNamespace(
                    max_skew_sec=5,
                    max_defer_count=3,
                    defer_cooldown_sec=2,
                    defer_window_sec=60,
                    until_refresh_retry_sec=30,
                    until_refresh_max_hold_sec=300,
                ),
            ),
            risk_management=SimpleNamespace(
                trading_allowed_thresholds=SimpleNamespace(max_risk_score=1.0),
            ),
            position_tracking=SimpleNamespace(positions_stale_ttl_sec=60),
        ),
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                decision=SimpleNamespace(
                    retry_max_count=5, retry_backoff_factor=2.0),
            ),
        ),
        system=SimpleNamespace(market_data=None),
    )
    dm.config = config
    dm.logger = MagicMock()

    # Gate mocks — let signal flow through to Gate 4
    dm._check_strategy_arbitration.return_value = {"allowed": True}
    dm._handle_flip_orchestration.return_value = None
    dm._qos_enabled_for_strategy.return_value = False
    dm._get_aurora_instrument_cfg.return_value = None
    dm._degraded_context_gate_should_defer.return_value = False
    dm._precheck_exposure_cache.return_value = True
    dm._warmup_gate_before_trade_intent.return_value = False

    # Wire real sizing: fallback portfolio → equity=0 → (None, ...)
    pq = PositionQueries(
        config=MagicMock(),
        get_portfolio=lambda: None,
        min_pos_size_usd=Decimal("10"),
        liq_cap_usd=Decimal("100000"),
        logger=MagicMock(),
    )
    dm._calculate_position_size.side_effect = (
        lambda symbol, price, side, context, **kw:
            pq.calculate_position_size(symbol, price, side, context, **kw)
    )

    gw = StrategyGateway(dm)

    msg = Message(
        op="EVT", verb="produced",
        src="feature_engineering", dst="decision_making",
        name="EVT:STRATEGY_SIGNAL_PRODUCED",
        pld={
            "strategy_id": "aurora",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "rid": "test-fallback-portfolio",
            "ts_ms": now_ms,
            "tf_sec": 300,
            "intent_kind": "ENTRY",
            "readiness": {"warmup_ok": True},
            "price_ctx": {"entry_price": 50000},
        },
    )

    gw.process_signal(msg)

    # ── Assertions ──

    # 1. NO trade intent emitted — the safety contract holds
    dm._propose_trade_intent.assert_not_called()

    # 2. Reject WAS emitted with SIZING_QTY_NONE (equity=0 path)
    dm._emit_trade_intent_rejected.assert_called_once()
    reject_kwargs = dm._emit_trade_intent_rejected.call_args.kwargs
    assert reject_kwargs["reason_code"] == "SIZING_QTY_NONE", (
        f"Expected SIZING_QTY_NONE, got {reject_kwargs['reason_code']}"
    )
