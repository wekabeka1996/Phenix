import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from types import SimpleNamespace
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState
from apps.reference.domains.execution_position.contracts import PositionSide

@pytest.fixture
def mock_config():
    return {
        "execution": {
            "manage": {
                "mode": "aggregated_only",
                "auto": True,  # Enable auto-manage
                "brackets": {
                    "enable": True,
                    "aggregated_oco": {
                        "enabled": True,
                        "aggregated_only_mode": True,
                        "recalc_on_partial_close": True
                    },
                    "sl": {"fixed_bps": 100},
                    "tp": {"fixed_bps": 200}
                }
            }
        },
        "trading": {
            "instruments": {
                "BTCUSDT": {
                    "tick_size": "0.1",
                    "min_price": "0.1"
                }
            }
        }
    }

@pytest.fixture
def fsm(mock_config):
    fsm = ManageFlowFSM(config=mock_config, symbol="BTCUSDT")

    # Create a MagicMock for the config object returned by _manage_config()
    config_mock = MagicMock()
    config_mock.brackets.enable = True
    config_mock.brackets.aggregated_oco.enabled = True
    config_mock.brackets.aggregated_oco.aggregated_only_mode = True
    config_mock.brackets.aggregated_oco.recalc_on_partial_close = True
    config_mock.brackets.sl.fixed_bps = 100
    config_mock.brackets.tp.fixed_bps = 200

    # Patch _manage_config to return this mock
    fsm._manage_config = MagicMock(return_value=config_mock)

    # Mock dependencies
    fsm._live_position_provider = MagicMock(return_value={
        "symbol": "BTCUSDT",
        "qty": "1.0",
        "avg_price": "50000.0",
        "side": "LONG"
    })
    fsm._qty_guard = MagicMock()
    fsm._qty_guard.evaluate.return_value.allowed = True
    fsm._qty_guard.evaluate.return_value.qty_str.return_value = "1.0"
    return fsm

def test_agg_oco_logs_flow(fsm):
    """Verify AGG_OCO logs during normal fill handling."""

    # Ensure aggregated mode is on
    assert fsm._aggregated_only_mode is True

    msg = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="test_src",
        dst="test_dst",
        pld={
            "symbol": "BTCUSDT",
            "qty": "1.0",
            "price": "50000.0",
            "side": "BUY",
            "source": "test_source"
        }
    )

    with patch("apps.reference.domains.execution_position.fsm_manage.agg_oco_logger") as mock_logger:
        fsm.handle(msg)

        # 2. Check AGG_OCO_COMPUTE_BRACKETS_START
        start_calls = [c for c in mock_logger.info.call_args_list if c[0][0] == "AGG_OCO_COMPUTE_BRACKETS_START"]
        assert len(start_calls) > 0, f"AGG_OCO_COMPUTE_BRACKETS_START not logged. Calls: {mock_logger.info.call_args_list}"

        # 3. Check AGG_OCO_COMPUTE_BRACKETS_DONE
        done_calls = [c for c in mock_logger.info.call_args_list if c[0][0] == "AGG_OCO_COMPUTE_BRACKETS_DONE"]
        assert len(done_calls) > 0

        # 4. Check AGG_OCO_BEFORE_QTY_GUARD
        guard_calls = [c for c in mock_logger.info.call_args_list if c[0][0] == "AGG_OCO_BEFORE_QTY_GUARD"]
        assert len(guard_calls) > 0

def test_agg_oco_compute_failed(fsm):
    """Verify AGG_OCO_COMPUTE_FAILED log when computation raises exception."""

    assert fsm._aggregated_only_mode is True

    msg = Message(
        op="EVT",
        verb="TRADE_EXECUTED",
        src="test_src",
        dst="test_dst",
        pld={
            "symbol": "BTCUSDT",
            "qty": "1.0",
            "price": "50000.0",
            "side": "BUY"
        }
    )

    # Force an exception in _compute_aggregated_bracket_levels
    with patch.object(fsm, "_compute_aggregated_bracket_levels", side_effect=Exception("Boom")):
        with patch("apps.reference.domains.execution_position.fsm_manage.agg_oco_logger") as mock_logger:
            fsm.handle(msg)

            # Check AGG_OCO_COMPUTE_FAILED
            fail_calls = [c for c in mock_logger.exception.call_args_list if c[0][0] == "AGG_OCO_COMPUTE_FAILED"]
            assert len(fail_calls) > 0
            assert fail_calls[0].kwargs["extra"]["reason"] == "agg_first_entry"

def test_canonical_position_side_usage(fsm):
    """Verify usage of canonical PositionSide in aggregated mode."""

    # Setup state
    fsm.position_qty = Decimal("1.0")
    fsm.position_side = "BUY"
    fsm._agg_side = "LONG"

    # Verify _resolve_canonical_position_side returns PositionSide enum
    canonical = fsm._resolve_canonical_position_side()
    assert canonical == PositionSide.LONG
    assert isinstance(canonical, PositionSide)

    # Verify _convert_position_side returns string value of enum
    side_str = fsm._convert_position_side()
    assert side_str == "LONG"


def test_set_bracket_ids_registers_guardian_meta(fsm):
    """Ensure ExecPos bracket sync immediately registers a guardian meta set."""

    class StubGuardian:
        def __init__(self) -> None:
            self.calls = []

        def register_bracket_set(self, **kwargs):  # type: ignore[no-untyped-def]
            self.calls.append(kwargs)
            return SimpleNamespace(
                bracket_set_id=kwargs.get("bracket_set_id"),
                symbol=kwargs.get("symbol"),
                side=kwargs.get("side"),
                sl_order_id=kwargs.get("sl_order_id"),
                tp_order_id=kwargs.get("tp_order_id"),
                version=1,
            )

    fsm._order_guardian = StubGuardian()
    fsm.symbol = "BTCUSDT"
    fsm.position_qty = Decimal("2.5")
    fsm.position_entry_price = Decimal("50000")
    fsm.position_side = "BUY"
    fsm._agg_side = "LONG"
    fsm.sl_price = Decimal("49000")
    fsm.tp_price = Decimal("51000")
    fsm._current_bracket_set_id = "btc-long-1"
    fsm._pending_bracket_log = {
        "action": "create",
        "position_qty_before": "0",
        "position_qty_after": "2.5",
        "avg_price_before": None,
        "avg_price_after": "50000",
        "sl_price_before": None,
        "sl_price_after": "49000",
        "tp_price_before": None,
        "tp_price_after": "51000",
        "why": "agg_first_entry",
        "rid": "test",
    }

    with patch("apps.reference.domains.execution_position.fsm_manage.agg_oco_logger") as mock_logger:
        fsm.set_bracket_ids(sl_order_id="sl-123", tp_order_id="tp-456")

    assert fsm._order_guardian.calls, "OrderGuardian.register_bracket_set was not invoked"
    call_payload = fsm._order_guardian.calls[0]
    assert call_payload["symbol"] == "BTCUSDT"
    assert call_payload["side"] == "LONG"
    assert call_payload["sl_order_id"] == "sl-123"
    assert call_payload["tp_order_id"] == "tp-456"

    register_done_calls = [
        args for args in mock_logger.info.call_args_list if args[0][0] == "AGG_OCO_REGISTER_BRACKET_SET_DONE"
    ]
    assert register_done_calls, "Expected AGG_OCO_REGISTER_BRACKET_SET_DONE log entry"
