"""Additional coverage tests to push over 90% threshold (FSMP-P1-T06-GATE)"""

import sys
import pathlib

# Add vfoundation to path
_test_root = pathlib.Path(__file__).parent.parent.resolve()
_vfoundation_root = _test_root / "vfoundation"
if str(_vfoundation_root) not in sys.path:
    sys.path.insert(0, str(_vfoundation_root))


def test_fsm_no_transition_error() -> None:
    """Test FSM.handle with no matching transition (covers FSM error path)"""
    from vfoundation.core.fsm import FSM
    from vfoundation.core.protocol import Message

    fsm = FSM("test-fsm")

    # No handlers registered, use valid op
    msg = Message(
        op="ASK",
        verb="UNKNOWNVERB",
        src="test",
        dst="test-fsm",
        rid="test-no-transition",
        why="test",
    )

    result = fsm.handle(msg)

    # Should return ERR with NO_TRANSITION
    assert result is not None
    assert result.op == "ERR"
    assert result.verb == "NO_TRANSITION"


def test_config_wal_dir_default() -> None:
    """Test config WAL_DIR default value (covers config branch)"""
    import os
    from vfoundation.config import Config

    # Save and clear
    old_val = os.environ.pop("WAL_DIR", None)

    try:
        cfg = Config()
        # Should use default (may be Path object)
        assert str(cfg.wal_dir) == "ops/wal" or str(cfg.wal_dir) == "ops\\wal"
    finally:
        if old_val:
            os.environ["WAL_DIR"] = old_val


def test_idempotency_store_simple() -> None:
    """Test IdempotencyStore basic instantiation (simple coverage)"""
    from vfoundation.core.idempotency import IdempotencyStore

    store = IdempotencyStore()

    # Get metrics
    m = store.get_metrics()

    # Should have core keys
    assert "idem_acquired" in m
    assert isinstance(m, dict)
