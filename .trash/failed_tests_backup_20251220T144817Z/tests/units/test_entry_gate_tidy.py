import time
import pytest
from unittest.mock import MagicMock

from apps.reference.domains.execution_position.fsm import ExecPosFSM


def _mk_cfg(allow_gate: bool = True, ttl_ms: int = 6000, cooldown_ms: int = 4000):
    return {
        "execution": {
            "allow_trade_with_guardian_tidy_only": allow_gate,
        },
        "guardian": {
            "cleanup_ttl_ms": ttl_ms,
            "symbol_cooldown_ms": cooldown_ms,
        },
    }


def test_entry_gate_blocks_without_recent_tidy():
    cfg = _mk_cfg(allow_gate=True, ttl_ms=6000, cooldown_ms=5000)
    fsm = ExecPosFSM(config=cfg, fsm=MagicMock(), shadow_mode=True)

    sym = "BTCUSDT"
    # Ensure no tidy recorded and no cooldown expired yet
    fsm._symbol_last_tidy_ts[sym] = 0.0
    fsm._last_entry_block_ts[sym] = time.time()

    allowed = fsm._entry_tidy_gate_allow(sym)
    assert allowed is False


def test_entry_gate_allows_after_tidy_or_cooldown():
    cfg = _mk_cfg(allow_gate=True, ttl_ms=6000, cooldown_ms=100)
    fsm = ExecPosFSM(config=cfg, fsm=MagicMock(), shadow_mode=True)

    sym = "ETHUSDT"
    # Case 1: recent tidy makes it allowed
    fsm._symbol_last_tidy_ts[sym] = time.time()
    assert fsm._entry_tidy_gate_allow(sym) is True

    # Case 2: no tidy but cooldown passed since last block
    sym2 = "SOLUSDT"
    fsm._symbol_last_tidy_ts[sym2] = 0.0
    fsm._last_entry_block_ts[sym2] = time.time() - 1.0  # 1s ago > 100ms cooldown
    assert fsm._entry_tidy_gate_allow(sym2) is True

