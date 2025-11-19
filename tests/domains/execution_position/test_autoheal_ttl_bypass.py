import time
import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal
from vfoundation.core.protocol import Message
from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM, ManageState


class TestAutoHealTTLBypass:
    @pytest.fixture
    def manage_flow(self):
        config = {
            "trading": {
                "execution": {
                    "manage": {
                        "mode": "aggregated_only",  # Set mode to aggregated_only
                        "brackets": {
                            "enable": True,
                            "aggregated_oco": {
                                "enabled": True,
                                "aggregated_only_mode": True,
                                "ttl_protect_new_bracket_ms": 5000,  # 5s TTL
                                "allow_unprotected_position": False,
                                "recalc_on_partial_close": True,  # Required for aggregated_only
                                "recalc_on_scale_in": True
                            },
                            "sl": {"fixed_bps": 50},
                            "tp": {"fixed_bps": 100}
                        }
                    }
                },
                "instruments": {
                    "SOLUSDT": {"tick_size": "0.01", "min_price": "0.01"}
                }
            }
        }
        fsm = ManageFlowFSM(config=config, symbol="SOLUSDT")
        fsm.position_qty = Decimal("1.0")
        fsm.position_entry_price = Decimal("100.0")
        fsm.position_side = "BUY"
        fsm.sl_order_id = "sl_123"
        fsm.tp_order_id = "tp_123"
        fsm._aggregated_last_place_ts = int(
            time.time() * 1000) - 1000  # 1s ago (within 5s TTL)
        return fsm

    def test_ttl_blocks_normal_recalc(self, manage_flow):
        """Verify TTL blocks normal recalc when brackets exist."""
        msg = Message(op="EVT", verb="FILL", src="test",
                      dst="manage", pld={"symbol": "SOLUSDT"})

        # Mock _place_brackets_aggregated to verify it's NOT called
        with patch.object(manage_flow, '_place_brackets_aggregated') as mock_place:
            result = manage_flow._recalc_aggregated_brackets(
                msg, reason="scale_in_fill")

            assert result is None
            mock_place.assert_not_called()

    def test_autoheal_bypasses_ttl(self, manage_flow):
        """Verify auto-heal bypasses TTL even if brackets exist."""
        msg = Message(
            op="EVT",
            verb="TRADE_EXECUTED",
            src="watchdog",
            dst="manage",
            pld={"symbol": "SOLUSDT"},
            why="watchdog_autoheal_no_sl"  # Magic string
        )

        # Mock _place_brackets_aggregated to verify it IS called
        with patch.object(manage_flow, '_place_brackets_aggregated') as mock_place:
            # Mock cancellation to avoid side effects
            with patch.object(manage_flow, '_cancel_active_brackets') as mock_cancel:
                manage_flow._recalc_aggregated_brackets(
                    msg, reason="scale_in_fill")

                mock_cancel.assert_called_once()
                mock_place.assert_called_once()

    def test_autoheal_reason_bypasses_ttl(self, manage_flow):
        """Verify auto-heal bypasses TTL via reason string."""
        msg = Message(op="EVT", verb="TRADE_EXECUTED",
                      src="watchdog", dst="manage", pld={"symbol": "SOLUSDT"})

        with patch.object(manage_flow, '_place_brackets_aggregated') as mock_place:
            with patch.object(manage_flow, '_cancel_active_brackets') as mock_cancel:
                manage_flow._recalc_aggregated_brackets(
                    msg, reason="autoheal_no_sl")

                mock_cancel.assert_called_once()
                mock_place.assert_called_once()
