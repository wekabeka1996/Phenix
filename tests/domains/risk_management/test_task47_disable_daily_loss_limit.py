import logging

from apps.reference.config_loader import get_config
from apps.reference.domains.risk_management.risk_management import RiskManagement


class _DummyFsm:
    def __init__(self):
        self.emitted: list[tuple[str, dict]] = []

    def emit(self, event_name: str, payload=None, *_a, **_k) -> None:
        self.emitted.append((event_name, payload or {}))

    def listen(self, _event_name: str, _cb) -> None:
        return


def test_task47_daily_loss_limit_blocks_by_default_when_no_equity_data() -> None:
    fsm = _DummyFsm()
    cfg = get_config()
    rm = RiskManagement(fsm=fsm, config=cfg)
    rm.logger = logging.getLogger("tests.task47.risk")

    out = rm._calculate_risk_parameters({"price": 100, "obi": 0, "tfi": 0, "delta_price": 0, "absorption": 0})
    assert out.get("is_trading_allowed") is False


def test_task47_daily_loss_limit_can_be_disabled_in_debug() -> None:
    fsm = _DummyFsm()
    cfg = get_config()
    cfg = cfg.model_copy(
        deep=True,
        update={
            "domains": cfg.domains.model_copy(
                update={
                    "debug": cfg.domains.debug.model_copy(
                        update={"disable_daily_loss_limit": True}
                    )
                }
            )
        },
    )

    rm = RiskManagement(fsm=fsm, config=cfg)
    rm.logger = logging.getLogger("tests.task47.risk")

    out = rm._calculate_risk_parameters({"price": 100, "obi": 0, "tfi": 0, "delta_price": 0, "absorption": 0})
    assert out.get("is_trading_allowed") is True
    assert any(name == "EVT:CONFIG_DEBUG_OVERRIDE_ACTIVE" for name, _ in fsm.emitted)

