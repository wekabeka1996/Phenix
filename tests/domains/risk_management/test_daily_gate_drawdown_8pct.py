from datetime import datetime, timezone, date

from apps.reference.config_loader import get_config
from apps.reference.domains.risk_management.daily_gate import DailyRiskState
from apps.reference.domains.risk_management.risk_management import RiskManagement


class _DummyFsm:
    def emit(self, *_a, **_k) -> None:
        return

    def listen(self, *_a, **_k) -> None:
        return


def test_daily_gate_uses_equity_cross_usdt_and_blocks_at_8pct_drawdown() -> None:
    cfg = get_config()
    cfg = cfg.model_copy(
        deep=True,
        update={
            "trading": cfg.trading.model_copy(
                update={
                    "risk": {
                        **cfg.trading.risk,
                        "daily": {
                            **cfg.trading.risk["daily"],
                            "enabled": True,
                        },
                    }
                }
            )
        },
    )
    gate = DailyRiskState(cfg)

    now = datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)
    gate.on_portfolio({"equity_free_usdt": "800", "equity_cross_usdt": "1000"}, now=now)

    allowed, _ = gate.can_open()
    assert allowed is True

    # 1000 -> 920 is exactly 8% drawdown => block (dd >= 8.0)
    gate.on_portfolio({"equity_free_usdt": "700", "equity_cross_usdt": "920"}, now=now)
    allowed, reason = gate.can_open()
    assert allowed is False
    assert reason.get("detail") == "MAX_DRAWDOWN"
    assert reason.get("limit_pct") == "8.0"


def test_daily_gate_allows_below_8pct_drawdown_boundary() -> None:
    cfg = get_config()
    cfg = cfg.model_copy(
        deep=True,
        update={
            "trading": cfg.trading.model_copy(
                update={
                    "risk": {
                        **cfg.trading.risk,
                        "daily": {
                            **cfg.trading.risk["daily"],
                            "enabled": True,
                        },
                    }
                }
            )
        },
    )
    gate = DailyRiskState(cfg)

    now = datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)
    gate.on_portfolio({"equity_cross_usdt": "1000"}, now=now)

    # 1000 -> 921 is 7.9% drawdown => allow
    gate.on_portfolio({"equity_cross_usdt": "921"}, now=now)
    allowed, reason = gate.can_open()
    assert allowed is True
    assert reason.get("why") == "daily_risk_checks_passed"


def test_daily_gate_fail_closed_without_equity() -> None:
    cfg = get_config()
    cfg = cfg.model_copy(
        deep=True,
        update={
            "trading": cfg.trading.model_copy(
                update={
                    "risk": {
                        **cfg.trading.risk,
                        "daily": {
                            **cfg.trading.risk["daily"],
                            "enabled": True,
                        },
                    }
                }
            )
        },
    )
    gate = DailyRiskState(cfg)

    allowed, reason = gate.can_open()
    assert allowed is False
    assert reason.get("detail") == "NO_EQUITY"


def test_daily_gate_reset_time_logic_hour_gt_minute_lt_is_past_reset() -> None:
    cfg = get_config()
    cfg = cfg.model_copy(
        deep=True,
        update={
            "trading": cfg.trading.model_copy(
                update={
                    "risk": {
                        **cfg.trading.risk,
                        "daily": {
                            **cfg.trading.risk["daily"],
                            "enabled": True,
                            "reset_time_utc": "12:30",
                        },
                    }
                }
            )
        },
    )
    gate = DailyRiskState(cfg)

    now = datetime(2026, 1, 1, 13, 0, tzinfo=timezone.utc)  # hour > 12, minute < 30
    gate.on_portfolio({"equity_cross_usdt": "1000"}, now=now)
    assert gate._last_reset_date == date(2026, 1, 1)


def test_risk_management_blocks_trading_when_daily_drawdown_exceeded() -> None:
    cfg = get_config()
    cfg = cfg.model_copy(
        deep=True,
        update={
            "trading": cfg.trading.model_copy(
                update={
                    "risk": {
                        **cfg.trading.risk,
                        "daily": {
                            **cfg.trading.risk["daily"],
                            "enabled": True,
                        },
                    }
                }
            )
        },
    )
    rm = RiskManagement(fsm=_DummyFsm(), config=cfg)

    now = datetime(2026, 1, 1, 0, 1, tzinfo=timezone.utc)
    rm.daily_risk_state.on_portfolio({"equity_cross_usdt": "1000"}, now=now)
    rm.daily_risk_state.on_portfolio({"equity_cross_usdt": "920"}, now=now)

    out = rm._calculate_risk_parameters({})
    assert out.get("is_trading_allowed") is False


def test_daily_gate_can_be_disabled_via_config() -> None:
    cfg = get_config()
    gate = DailyRiskState(cfg)

    allowed, reason = gate.can_open()
    assert allowed is True
    assert reason.get("why") == "daily_gate_disabled"
