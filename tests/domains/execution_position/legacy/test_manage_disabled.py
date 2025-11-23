import pytest
from types import SimpleNamespace
from vfoundation.core.protocol import Message

pytestmark = pytest.mark.execpos_legacy



def test_manage_disabled_emits_skipped(monkeypatch):
    # Импортируем класс Manage FSM из проекта
    from apps.reference.domains.execution_position.legacy.fsm_manage import ManageFlowFSM

    fsm = ManageFlowFSM(config={"execution": {"manage": {"auto": False}}})
    msg = Message(
        op="EVT",
        verb="TICK",
        intent="OBSERVATION",
        src="x",
        dst="y",
        rid="r1",
        pld={"symbol": "ETHUSDT"},
        why="test",
    )
    # вызови основной обработчик (укажи корректный метод вашего FSM)
    result = fsm.handle(msg)  # при необходимости подстрой точное имя метода

    assert result is not None
    assert result.verb == "MANAGE_SKIPPED"
    assert result.pld["symbol"] == "ETHUSDT"
    assert result.pld["reason"] == "auto_manage_disabled"

