from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.reference.config_contract import ConfigContractError
from apps.reference.config_loader import get_config
from apps.reference.domains.risk_management import daily_gate as daily_gate_mod
from apps.reference.domains.risk_management.daily_gate import (
    DailyRiskState,
    _d,
    _fmt_pct,
    _fmt_usd,
)
from apps.reference.domains.risk_management.risk_management import RiskManagement
from vfoundation.core.protocol import Message


class _DummyFsm:
    def __init__(self) -> None:
        self.emitted: list[dict] = []

    def emit(self, event_name: str, payload=None, why: str = "", data_ref=None, rid=None) -> None:
        self.emitted.append(
            {
                "event_name": event_name,
                "payload": payload,
                "why": why,
                "data_ref": data_ref,
                "rid": rid,
            }
        )

    def listen(self, *_a, **_k) -> None:
        return


def _cfg_live(enabled: bool = True):
    cfg = get_config()
    return cfg.model_copy(
        deep=True,
        update={
            "trading_mode": "live",
            "trading": cfg.trading.model_copy(
                update={
                    "risk": {
                        **cfg.trading.risk,
                        "daily": {
                            **cfg.trading.risk["daily"],
                            "enabled": enabled,
                        },
                    }
                }
            ),
        },
    )


def test_daily_helpers_parse_and_format_fallbacks() -> None:
    assert str(_d("bad")) == "0"
    assert _fmt_pct("bad") == "0.0"
    assert _fmt_pct(object()) == "0.0"
    assert _fmt_usd("10") == "10"
    assert _fmt_usd("10.50") == "10.5"
    assert _fmt_usd(object()) == "0"


def test_daily_gate_open_property_and_active_date_before_reset(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AURORA_RISK_GATE_STATE_PATH", str(tmp_path / "risk_gate_state.json"))
    gate = DailyRiskState(_cfg_live(enabled=False))
    assert gate.is_gate_open is True

    gate.cfg.reset_h = 23
    gate.cfg.reset_m = 59
    before_reset = datetime(2026, 2, 24, 0, 1, tzinfo=timezone.utc)
    assert gate._active_trading_date(before_reset).isoformat() == "2026-02-23"


def test_daily_load_state_non_persist_and_save_exception(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AURORA_RISK_GATE_STATE_PATH", str(tmp_path / "risk_gate_state.json"))

    cfg_backtest = get_config().model_copy(deep=True, update={"trading_mode": "backtest"})
    gate = DailyRiskState(cfg_backtest)
    gate._load_state()  # non-persist branch

    class _Log:
        def __init__(self):
            self.called = False

        def exception(self, *_a, **_k):
            self.called = True

    gate2 = DailyRiskState(_cfg_live(enabled=True), logger=_Log())
    monkeypatch.setattr(daily_gate_mod.json, "dumps", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("x")))
    gate2._save_state()
    assert gate2.log.called is True


def test_daily_load_state_corrupt_unlink_error_path(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "risk_gate_state.json"
    monkeypatch.setenv("AURORA_RISK_GATE_STATE_PATH", str(state_path))
    state_path.write_text("{bad-json", encoding="utf-8")

    original_unlink = Path.unlink

    def _raise_unlink(self, missing_ok=False):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "unlink", _raise_unlink)
    try:
        gate = DailyRiskState(_cfg_live(enabled=True))
        allowed, reason = gate.can_open()
        assert allowed is False
        assert reason.get("detail") == "NO_EQUITY"
    finally:
        monkeypatch.setattr(Path, "unlink", original_unlink)


def test_daily_trading_mode_and_risk_cfg_exception_paths(monkeypatch) -> None:
    class _CfgNoTrading:
        trading_mode = "live"

        @property
        def trading(self):
            raise AttributeError("missing")

    with pytest.raises(ConfigContractError):
        DailyRiskState(_CfgNoTrading())

    class _CfgBadTradingMode:
        def __getattr__(self, name):
            if name == "trading_mode":
                raise RuntimeError("boom")
            raise AttributeError(name)

        @property
        def trading(self):
            raise AttributeError("missing")

    with pytest.raises(ConfigContractError):
        DailyRiskState(_CfgBadTradingMode())


def test_daily_state_dict_config_rejected() -> None:
    with pytest.raises(TypeError):
        DailyRiskState({"trading": {"risk": {"daily": {"enabled": True}}}})


def test_daily_state_missing_enabled_raises() -> None:
    cfg = get_config().model_copy(
        deep=True,
        update={
            "trading_mode": "live",
            "trading": get_config().trading.model_copy(
                update={
                    "risk": {
                        **get_config().trading.risk,
                        "daily": {
                            "max_drawdown_pct": "8",
                            "reset_time_utc": "00:00",
                        },
                    }
                }
            ),
        },
    )
    with pytest.raises(ConfigContractError):
        DailyRiskState(cfg)


def test_daily_state_enabled_missing_required_fields_raises() -> None:
    cfg = get_config().model_copy(
        deep=True,
        update={
            "trading_mode": "live",
            "trading": get_config().trading.model_copy(
                update={
                    "risk": {
                        **get_config().trading.risk,
                        "daily": {
                            "enabled": True,
                        },
                    }
                }
            ),
        },
    )
    with pytest.raises(ConfigContractError):
        DailyRiskState(cfg)


def test_daily_load_state_branches(monkeypatch, tmp_path: Path) -> None:
    state_path = tmp_path / "risk_gate_state.json"
    monkeypatch.setenv("AURORA_RISK_GATE_STATE_PATH", str(state_path))

    fixed_now = datetime(2026, 2, 24, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(daily_gate_mod, "_now_utc", lambda: fixed_now)

    cfg = _cfg_live(enabled=True)

    # Branch: existing file, but no last_reset_date -> reset()
    state_path.write_text(json.dumps({"reference_equity": "1000"}), encoding="utf-8")
    gate = DailyRiskState(cfg)
    assert gate.reference_equity == _d("0")

    # Branch: stale last_reset_date -> reset()
    state_path.write_text(
        json.dumps({"reference_equity": "1000", "last_reset_date": "2026-02-20"}),
        encoding="utf-8",
    )
    gate2 = DailyRiskState(cfg)
    assert gate2.reference_equity == _d("0")

    # Branch: valid load path
    state_path.write_text(
        json.dumps(
            {
                "reference_equity": "1234.5",
                "last_reset_date": "2026-02-24",
                "is_gate_open": True,
            }
        ),
        encoding="utf-8",
    )
    gate3 = DailyRiskState(cfg)
    assert gate3.reference_equity == _d("1234.5")


def test_daily_reference_equity_setter_and_update_alias(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AURORA_RISK_GATE_STATE_PATH", str(tmp_path / "risk_gate_state.json"))
    gate = DailyRiskState(_cfg_live(enabled=True))

    gate.reference_equity = "1500"
    gate.update_portfolio({"equity_cross_usdt": "1500"}, now=datetime(2026, 2, 24, 12, 0, tzinfo=timezone.utc))

    assert gate.reference_equity == _d("1500")


def test_risk_init_rejects_dict_config() -> None:
    with pytest.raises(TypeError):
        RiskManagement(fsm=_DummyFsm(), config={"bad": True})


def test_alert_manager_unavailable_branch(monkeypatch) -> None:
    class _BrokenAlertManager:
        def __init__(self, *_a, **_k):
            raise RuntimeError("boom")

    from apps.reference.domains.risk_management import risk_management as rm_mod

    monkeypatch.setattr(rm_mod, "AlertManager", _BrokenAlertManager)
    rm = RiskManagement(fsm=_DummyFsm(), config=get_config())
    assert rm.alert_manager is None


def test_risk_init_debug_emit_exception_branch() -> None:
    class _RaisingFsm(_DummyFsm):
        def emit(self, *_a, **_k):
            raise RuntimeError("emit-fail")

    cfg = get_config().model_copy(
        deep=True,
        update={
            "domains": get_config().domains.model_copy(
                update={
                    "debug": get_config().domains.debug.model_copy(
                        update={"disable_daily_loss_limit": True}
                    )
                }
            )
        },
    )
    rm = RiskManagement(fsm=_RaisingFsm(), config=cfg)
    assert rm._debug_disable_daily_loss_limit is True


def test_on_portfolio_state_updated_timestamp_parsing_paths(monkeypatch) -> None:
    rm = RiskManagement(fsm=_DummyFsm(), config=get_config())
    calls: list[datetime | None] = []

    def _capture(_pld, now=None):
        calls.append(now)

    monkeypatch.setattr(rm.daily_risk_state, "on_portfolio", _capture)

    # ms timestamp
    rm.on_portfolio_state_updated(
        Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", src="t", dst="any", pld={"event_time_ms": 1700000000000}, why="t")
    )
    assert calls[-1] is not None

    # sec timestamp fallback branch
    rm.on_portfolio_state_updated(
        Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", src="t", dst="any", pld={"ts": 1700000000}, why="t")
    )
    assert calls[-1] is not None

    # invalid timestamp -> None branch
    rm.on_portfolio_state_updated(
        Message(op="EVT", verb="PORTFOLIO_STATE_UPDATED", src="t", dst="any", pld={"ts": "bad"}, why="t")
    )
    assert calls[-1] is None


def test_risk_management_methods_and_validation_branches() -> None:
    rm = RiskManagement(fsm=_DummyFsm(), config=get_config())
    rm.start()
    rm.stop()
    assert isinstance(rm._get_use_absorption_penalty(), bool)

    result = rm.validate_risk_thresholds()
    assert "valid" in result
    assert "warnings" in result


def test_test_risk_thresholds_default_and_error_paths() -> None:
    rm = RiskManagement(fsm=_DummyFsm(), config=get_config())

    # default scenarios path
    out_default = rm.test_risk_thresholds()
    assert "results" in out_default

    # exception path in scenario loop
    out_bad = rm.test_risk_thresholds(
        [
            {
                "name": "bad_case",
                "features": {"delta_price_pct": 0.1},
                "expected_trading_allowed": True,
                "expected_risk_range": [0.0, 1.0],
            }
        ]
    )
    assert out_bad["all_tests_passed"] is False
    assert "error" in out_bad["results"][0]


def test_on_features_calculated_exception_alert_paths() -> None:
    rm = RiskManagement(fsm=_DummyFsm(), config=get_config())

    class _Alert:
        def __init__(self):
            self.calls = 0

        def raise_alert(self, **_k):
            self.calls += 1
            raise RuntimeError("alert-fail")

    rm.alert_manager = _Alert()
    out = rm.on_features_calculated(None)  # type: ignore[arg-type]
    assert out["is_trading_allowed"] is False
    assert rm.alert_manager.calls == 1


def test_get_risk_score_weights_and_max_score_error_branches() -> None:
    rm = RiskManagement(fsm=_DummyFsm(), config=get_config())

    rm.domain_config = SimpleNamespace(risk_score_weights=None)
    with pytest.raises(ConfigContractError):
        rm._get_risk_score_weights()

    rm.config = SimpleNamespace(domains=SimpleNamespace())
    with pytest.raises(ConfigContractError):
        rm._get_max_risk_score()


def test_risk_score_high_and_price_invalid_paths(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("AURORA_RISK_GATE_STATE_PATH", str(tmp_path / "risk_gate_state.json"))
    cfg = _cfg_live(enabled=False)
    rm = RiskManagement(fsm=_DummyFsm(), config=cfg)

    # risk_score_high warning path
    rm.config = cfg.model_copy(
        deep=True,
        update={
            "domains": cfg.domains.model_copy(
                update={
                    "risk_management": cfg.domains.risk_management.model_copy(
                        update={
                            "trading_allowed_thresholds": cfg.domains.risk_management.trading_allowed_thresholds.model_copy(
                                update={"max_risk_score": 0.01}
                            )
                        }
                    )
                }
            )
        },
    )

    out = rm._calculate_risk_parameters(
        {
            "price": "100",
            "delta_price": "2",
            "obi": "0.9",
            "tfi": "0.9",
            "absorption": "0.1",
        }
    )
    assert out["is_trading_allowed"] is False

    # invalid price path
    with pytest.raises(ValueError):
        rm._calculate_risk_parameters(
            {
                "price": "0",
                "delta_price": "1",
                "obi": "0",
                "tfi": "0",
                "absorption": "0",
            }
        )


def test_risk_debug_override_emit_exception_and_clamp_paths(monkeypatch) -> None:
    class _RaisingFsm(_DummyFsm):
        def emit(self, *_a, **_k):
            raise RuntimeError("emit-fail")

    cfg = get_config().model_copy(
        deep=True,
        update={
            "domains": get_config().domains.model_copy(
                update={
                    "debug": get_config().domains.debug.model_copy(
                        update={"disable_daily_loss_limit": True}
                    )
                }
            )
        },
    )
    rm = RiskManagement(fsm=_RaisingFsm(), config=cfg)

    class _Daily:
        def can_open(self):
            return False, {}

    rm.daily_risk_state = _Daily()
    rm._use_absorption_penalty = True

    # clamp > 1 path
    out_hi = rm._calculate_risk_parameters(
        {
            "price": "1",
            "delta_price": "100",
            "obi": "10",
            "tfi": "10",
            "absorption": "0",
        }
    )
    assert out_hi["risk_score"] == 1.0

    # clamp < 0 path (absorption > 1 with other terms near zero)
    out_lo = rm._calculate_risk_parameters(
        {
            "price": "100",
            "delta_price": "0",
            "obi": "0",
            "tfi": "0",
            "absorption": "2",
        }
    )
    assert out_lo["risk_score"] == 0.0


def test_validate_risk_thresholds_error_branches() -> None:
    rm = RiskManagement(fsm=_DummyFsm(), config=get_config())

    class _DumpObj(SimpleNamespace):
        def model_dump(self, mode="json"):
            return dict(self.__dict__)

    rm.domain_config = SimpleNamespace(
        trading_allowed_thresholds=_DumpObj(),
        risk_score_weights=_DumpObj(
            delta_price_pct="-1",
            obi="bad",
            # tfi missing intentionally
            absorption_inverse="0.1",
        ),
        validation=SimpleNamespace(total_weight_min=0.9, total_weight_max=1.1),
    )

    out = rm.validate_risk_thresholds()
    assert out["valid"] is False
    assert any("Missing required threshold" in issue for issue in out["issues"])
    assert any("Missing required risk weight" in issue for issue in out["issues"])
    assert any("Invalid risk weight value" in issue for issue in out["issues"])
