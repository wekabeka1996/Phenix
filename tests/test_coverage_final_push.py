"""Additional coverage tests to push over 90% threshold (FSMP-P1-T06-GATE)"""

import sys
import pathlib

def test_fsm_no_transition_error() -> None:
    """Test FSM.handle with no matching transition (covers FSM error path)"""
    from vfoundation.core.fsm_v2 import FSMv2 as FSM
    from vfoundation.core.protocol import Message

    fsm = FSM("test-fsm")
    fsm.register_state("START", initial=True)

    # No handlers registered, use valid op
    msg = Message(
        op="ASK",
        verb="UNKNOWNVERB",
        src="test",
        dst="test-fsm",
        rid="test-no-transition",
        why="test",
    )

    new_state, result = fsm.handle("test-key", msg)

    # Should return ERR with NO_TRANSITION
    assert result is not None
    assert result.op == "ERR"
    assert result.verb == "NO_TRANSITION"


def test_config_wal_dir_default() -> None:
    """Test config WAL_DIR default value (covers config branch)"""
    import os
    from vfoundation.config import config

    # Should resolve to the WAL directory regardless of the active cwd.
    assert pathlib.Path(config.wal_dir).name == "wal"


def test_idempotency_store_simple() -> None:
    """Test IdempotencyStore basic instantiation (simple coverage)"""
    from vfoundation.core.idempotency import IdempotencyStore

    store = IdempotencyStore()

    # Get metrics
    m = store.get_metrics()

    # Should have core keys
    assert "idem_acquired" in m
    assert isinstance(m, dict)
