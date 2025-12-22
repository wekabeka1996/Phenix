import logging
import decimal

from apps.reference.config_loader import get_config
from apps.reference.domains.decision_making.decision_making import DecisionMaking


class _Bus:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict]] = []

    def listen(self, _event: str, _handler) -> None:
        return

    def emit(self, event_name: str, payload: dict | None = None, *_a, **_k) -> None:
        self.emitted.append((event_name, payload or {}))


def test_task47_btc_dual_strategy_can_emit_intents_in_different_windows() -> None:
    cfg = get_config()
    bus = _Bus()
    dm = DecisionMaking(fsm=bus, config=cfg)
    dm.logger = logging.getLogger("tests.task47.dm")

    # Bypass warmup for this unit-style test: focus on arbitration/eligibility.
    dm._warmup_gate_before_trade_intent = lambda **_k: False
    dm._record_blocked_intent = lambda *_a, **_k: None
    dm._record_accepted_intent = lambda *_a, **_k: None

    # Ensure arbitration registry is present and BTC has both strategies assigned.
    assert cfg.strategies_registry is not None
    assert set(cfg.strategies_registry.assignments["BTCUSDT"]) == {"aurora", "mean_reversion"}

    dm.latest_portfolio = {"equity": "1000", "positions": [], "positions_last_ts_ms": 1_700_000_000_000}

    dm._propose_trade_intent(
        symbol="BTCUSDT",
        side="BUY",
        qty=decimal.Decimal("1"),
        price=decimal.Decimal("100"),
        why_chain=["test"],
        rid="rid-mr",
        reduce_only=False,
        strategy_id="mean_reversion",
        decision_ts_ms=1_700_000_000_000,
    )

    dm._propose_trade_intent(
        symbol="BTCUSDT",
        side="BUY",
        qty=decimal.Decimal("1"),
        price=decimal.Decimal("100"),
        why_chain=["test"],
        rid="rid-aurora",
        reduce_only=False,
        strategy_id="aurora",
        decision_ts_ms=1_700_000_002_000,  # different window_id
    )

    intents = [pld for (evt, pld) in bus.emitted if evt == "EVT:TRADE_INTENT_PROPOSED"]
    assert {i["strategy"] for i in intents} == {"aurora", "mean_reversion"}
