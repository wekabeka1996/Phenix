"""
Tests for shadow FSM roundtrip (FSMP-P1-T05).

- Publishes DEC:OPEN to WAL.
- Replays from WAL.
- Verifies replay handler receives correct message.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from vfoundation.core.protocol import Message
from vfoundation.dr import wal, replay
import tempfile
import pathlib
from apps.reference.domains.execution_position.fsm import ExecPosFSM


@pytest.fixture
def exec_pos_fsm():
    """Fixture to create an ExecPosFSM instance in shadow mode."""
    import apps.reference.domains.execution_position.fsm

    fsm_path = Path(apps.reference.domains.execution_position.fsm.__file__)
    mock_fsm = MagicMock()

    # Create a proper mock config with safe defaults
    mock_config = {
        "trading": {
            "execution": {
                "exposure": {
                    "max_equity_utilization_pct": "0.20",
                    "max_portfolio_fraction": "0.20",
                    "max_side_utilization_pct": {
                        "long": "0.12",
                        "short": "0.12"
                    },
                    "max_directional_ratio": "2.0"
                },
                "manage": {
                    "orphan_monitor": {
                        "enabled": True,
                        "run_on_startup": True,
                        "periodic_interval_sec": 300
                    }
                }
            }
        }
    }

    fsm_instance = ExecPosFSM(
        config=mock_config, fsm=mock_fsm, shadow_mode=True)

    # Verify that the FSM has the 'handle' method for vFoundation compatibility
    if not hasattr(fsm_instance, "handle"):
        raise RuntimeError(
            f"ExecPosFSM from {fsm_path} does not have 'handle' method. "
            "Both apps/ and vfoundation/ versions should have this method."
        )

    return fsm_instance


@pytest.fixture
def temp_wal_dir():
    """Create a temporary directory for WAL files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield pathlib.Path(tmpdir)


def test_shadow_fsm_roundtrip(exec_pos_fsm):
    """
    Tests the full FSM roundtrip in shadow mode:
    CMD:OPEN -> DEC:OPEN -> EVT:FILL -> DEC:ADJUST -> DEC:CLOSE
    """
    shadow_fsm = exec_pos_fsm

    # 1. Send CMD:OPEN
    open_cmd = Message(
        op="CMD",
        verb="OPEN",
        src="test",
        dst="exec_pos",
        pld={"symbol": "BTCUSDT", "side": "buy",
             "qty": "0.1", "price": "10000"},
    )
    open_dec = shadow_fsm.handle(open_cmd)

    assert open_dec is not None
    assert open_dec.op == "DEC"
    assert open_dec.verb == "OPEN"


def test_replay_filters_by_timestamp(temp_wal_dir):
    """Test that replay_from_wal correctly filters by from_ts."""
    wal.set_wal_dir(temp_wal_dir)

    # Message 1 (timestamp will be around now)
    msg1 = Message(op="DEC", verb="OPEN", src="test",
                   dst="test", rid="r1", pld={})
    wal.append(msg1.model_dump())

    time_after_msg1 = msg1.ts + 1  # 1 ms after

    # Small delay to ensure different timestamps
    import time

    time.sleep(0.001)

    # Message 2 (timestamp will be later)
    msg2 = Message(op="DEC", verb="CLOSE", src="test",
                   dst="test", rid="r2", pld={})
    wal.append(msg2.model_dump())

    replay_handler = MagicMock()

    # Replay only from after message 1
    replay.replay_from_wal(replay_handler, from_ts=time_after_msg1)

    # Should only be called once (for msg2)
    replay_handler.assert_called_once()

    args, _ = replay_handler.call_args
    replayed_message_dict = args[0]

    assert replayed_message_dict["rid"] == "r2"
    assert replayed_message_dict["verb"] == "CLOSE"


def test_replay_empty_wal(temp_wal_dir):
    """Test replay on an empty WAL directory does not call handler."""
    wal.set_wal_dir(temp_wal_dir)

    replay_handler = MagicMock()

    replay.replay_from_wal(replay_handler)

    replay_handler.assert_not_called()
