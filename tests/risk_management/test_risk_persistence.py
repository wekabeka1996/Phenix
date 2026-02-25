from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal


def test_daily_gate_persists_reference_equity_across_restarts(tmp_path, monkeypatch) -> None:
    from apps.reference.config_loader import get_config
    from apps.reference.domains.risk_management.daily_gate import DailyRiskState

    state_path = tmp_path / "risk_gate_state.json"
    monkeypatch.setenv("AURORA_RISK_GATE_STATE_PATH", str(state_path))

    cfg = get_config()
    cfg.trading_mode = "live" # Enable persistence for test
    gate = DailyRiskState(cfg)

    now = datetime.now(timezone.utc)
    gate.on_portfolio({"equity_cross_usdt": "10000"}, now=now)
    gate._save_state()

    restarted = DailyRiskState(cfg)
    assert restarted.reference_equity == Decimal("10000")


def test_risk_management_on_features_calculated_fail_closed(monkeypatch) -> None:
    from apps.reference.config_loader import get_config
    from apps.reference.domains.risk_management.risk_management import RiskManagement

    class _DummyFsm:
        def emit(self, *_a, **_k) -> None:
            return

        def listen(self, *_a, **_k) -> None:
            return

    cfg = get_config()
    rm = RiskManagement(fsm=_DummyFsm(), config=cfg)

    out = rm.on_features_calculated(None)  # type: ignore[arg-type]
    assert isinstance(out, dict)
    assert out.get("is_trading_allowed") is False
    assert out.get("reason") == "RISK_INTERNAL_ERROR"
