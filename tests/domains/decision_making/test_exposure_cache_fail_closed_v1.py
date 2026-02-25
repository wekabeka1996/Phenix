"""
T2: Exposure Cache FAIL-CLOSED Test (TDD RED -> GREEN)

DM-SAFETY-BYPASSES-P1: Verifies exposure cache precheck uses fail-closed behavior.

Tests:
- T2a: cache=None => BLOCK with EXPOSURE_CACHE_UNAVAILABLE
- T2b: cache stale (>30s) => BLOCK with EXPOSURE_CACHE_UNAVAILABLE
- T2c: exception during cache read => BLOCK with EXPOSURE_CACHE_UNAVAILABLE
- T2d: valid cache, within limits => ALLOW
- T2e: valid cache, exceeds limits => BLOCK with EXPOSURE_LIMIT_EXCEEDED
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, PropertyMock


class FakeClock:
    """Fake clock for deterministic testing."""
    
    def __init__(self, now_sec_value: float = 1700000000.0):
        self._now_sec = now_sec_value
    
    def now_sec(self) -> float:
        return self._now_sec
    
    def now_ms(self) -> int:
        return int(self._now_sec * 1000)
    
    def set_now_sec(self, value: float):
        self._now_sec = value


def _mk_dm_for_exposure():
    """Create DecisionMaking mock for exposure cache tests."""
    from apps.reference.domains.decision_making.decision_making import DecisionMaking
    from apps.reference.domains.decision_making.readiness_gates import ReadinessGates
    from unittest.mock import MagicMock

    clock = FakeClock()

    with patch.object(DecisionMaking, "__init__", lambda *_args, **_kwargs: None):
        dm = DecisionMaking.__new__(DecisionMaking)

    dm.logger = MagicMock()
    dm._clock = clock
    dm._shared = {
        "exposure_cache": None,
        "exposure_cache_timestamp": 0.0,
    }

    dm._readiness = ReadinessGates(
        clock=clock,
        config=MagicMock(),
        features_ttl_sec=60,
        symbol_states={},
        per_symbol_regimes={},
        get_portfolio=lambda: None,
        get_exposure_cache=lambda: (dm._exposure_cache, dm._exposure_cache_timestamp),
        emit_intent_deferred_v1=lambda **kw: None,
        record_blocked_intent=lambda s: None,
        fail_closed_on_degraded_context=False,
        degraded_context_critical_keys=set(),
        degraded_context_critical_keys_by_strategy={},
        logger=MagicMock())

    return dm, clock


class TestExposureCacheFailClosed:
    """DM-SAFETY-BYPASSES-P1: Exposure cache precheck must be FAIL-CLOSED."""

    def test_no_cache_blocks_trade(self):
        """T2a: _exposure_cache=None => return False (BLOCK)."""
        dm, clock = _mk_dm_for_exposure()
        
        dm._exposure_cache = None
        
        result = dm._precheck_exposure_cache("BTCUSDT", "BUY", 10000.0)
        
        assert result is False, "Missing exposure cache should BLOCK (fail-closed)"

    def test_stale_cache_blocks_trade(self):
        """T2b: cache older than 30s => return False (BLOCK)."""
        dm, clock = _mk_dm_for_exposure()
        
        # Set cache but make it stale (>30 seconds old)
        dm._exposure_cache = {
            "BTCUSDT": {"current_exposure_usd": 5000.0, "max_exposure_usd": 100000.0}
        }
        dm._exposure_cache_timestamp = clock.now_sec() - 35.0  # 35 seconds ago
        
        result = dm._precheck_exposure_cache("BTCUSDT", "BUY", 10000.0)
        
        assert result is False, "Stale exposure cache should BLOCK (fail-closed)"

    def test_cache_exception_blocks_trade(self):
        """T2c: exception during cache read => return False (BLOCK)."""
        dm, clock = _mk_dm_for_exposure()
        
        # Set up cache that will raise exception when accessed
        dm._exposure_cache = MagicMock()
        dm._exposure_cache.__bool__ = MagicMock(return_value=True)  # Cache "exists"
        dm._exposure_cache_timestamp = clock.now_sec()  # Fresh
        dm._exposure_cache.__getitem__ = MagicMock(side_effect=RuntimeError("Cache error"))
        dm._exposure_cache.__contains__ = MagicMock(return_value=True)
        
        result = dm._precheck_exposure_cache("BTCUSDT", "BUY", 10000.0)
        
        assert result is False, "Exception in cache should BLOCK (fail-closed)"

    def test_valid_cache_within_limits_allows(self):
        """T2d: valid fresh cache, within exposure limits => ALLOW."""
        dm, clock = _mk_dm_for_exposure()
        
        dm._exposure_cache = {
            "BTCUSDT": {"current_exposure_usd": 5000.0, "max_exposure_usd": 100000.0}
        }
        dm._exposure_cache_timestamp = clock.now_sec()  # Fresh (0 seconds ago)
        
        result = dm._precheck_exposure_cache("BTCUSDT", "BUY", 10000.0)
        
        assert result is True, "Valid cache within limits should ALLOW"

    def test_valid_cache_exceeds_limits_blocks(self):
        """T2e: valid fresh cache, exceeds exposure => BLOCK (existing reason)."""
        dm, clock = _mk_dm_for_exposure()
        
        dm._exposure_cache = {
            "BTCUSDT": {"current_exposure_usd": 95000.0, "max_exposure_usd": 100000.0}
        }
        dm._exposure_cache_timestamp = clock.now_sec()
        
        # Request 10k would push to 105k > 100k max
        result = dm._precheck_exposure_cache("BTCUSDT", "BUY", 10000.0)
        
        assert result is False, "Exceeding exposure limit should BLOCK"
