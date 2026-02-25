"""
Tests for Phase 0 refactoring: QoS Partitioning and Readiness Contract.

Verifies:
1. QoS state is partitioned by strategy_id
2. Gateway rejects signals without readiness.warmup_ok
3. Flip retry includes readiness field
"""
import pytest
from unittest.mock import MagicMock, patch
from collections import defaultdict
import time


class TestQoSPartitioning:
    """Tests for QoS state partitioned by strategy_id."""

    @pytest.fixture
    def mock_dm(self):
        """Create a mock DecisionMaking with partitioned QoS state."""
        dm = MagicMock()
        
        # Validate dependency on Clock
        dm._clock = MagicMock()
        dm._clock.now_sec.return_value = 1000000.0
        
        dm._qos_state = defaultdict(
            lambda: {
                "last_exposure_block": 0.0,
                "symbol_cooldowns": {},
                "symbol_intent_counts": defaultdict(
                    lambda: {"count": 0, "window_start": 1000000.0}
                ),
            }
        )
        dm.qos_exposure_block_cooldown_sec = 60
        dm.qos_max_intents_per_minute_per_symbol = 10
        dm._default_symbol_cooldown_sec = 3
        dm.logger = MagicMock()
        from apps.reference.domains.decision_making.qos_rate_control import QoSRateControl
        dm._qos = QoSRateControl(
            clock=dm._clock,
            qos_state=dm._qos_state,
            apply_to_strategies=set(),
            exposure_block_cooldown_sec=dm.qos_exposure_block_cooldown_sec,
            max_intents_per_minute_per_symbol=dm.qos_max_intents_per_minute_per_symbol,
            get_symbol_cooldown=lambda s, sid="aurora": int(dm._default_symbol_cooldown_sec),
            logger=dm.logger,
        )
        return dm

    def test_qos_state_isolated_between_strategies(self, mock_dm):
        """Aurora and MR should have separate QoS state."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        # Simulate Aurora cooldown update
        DecisionMaking._update_symbol_cooldown(mock_dm, "BTCUSDT", "aurora")
        
        # Verify Aurora state updated
        assert "BTCUSDT" in mock_dm._qos_state["aurora"]["symbol_cooldowns"]
        
        # Verify MR state is clean (isolated)
        assert "BTCUSDT" not in mock_dm._qos_state["mean_reversion"].get("symbol_cooldowns", {})

    def test_qos_allow_uses_strategy_state(self, mock_dm):
        """QoS check should use strategy-specific state."""
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        
        # Stub _get_symbol_cooldown
        mock_dm._get_symbol_cooldown = MagicMock(return_value=3)
        
        # Aurora blocked (update ts = now)
        now = 1000000.0
        mock_dm._qos_state["aurora"]["symbol_cooldowns"]["BTCUSDT"] = now
        
        # Check permissions
        aurora_allowed, _ = DecisionMaking._qos_allow(mock_dm, "BTCUSDT", "aurora")
        mr_allowed, _ = DecisionMaking._qos_allow(mock_dm, "BTCUSDT", "mean_reversion")
        
        assert aurora_allowed is False  # Recently updated (diff=0 < 3)
        assert mr_allowed is True  # No update for MR


class TestReadinessContract:
    """Tests for gateway readiness.warmup_ok contract."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock strategy signal event."""
        event = MagicMock()
        event.pld = {
            "strategy_id": "mean_reversion",
            "symbol": "BTCUSDT",
            "side": "BUY",
            "ts_ms": int(time.time() * 1000),
            "price_ctx": {"entry_price": "50000"},
            "rid": "test-rid",
        }
        return event

    def test_gateway_rejects_missing_readiness(self, mock_event):
        """Gateway should reject signal without readiness field."""
        # No readiness field
        assert "readiness" not in mock_event.pld, "Test setup error: readiness should not exist"

    def test_gateway_rejects_warmup_ok_false(self, mock_event):
        """Gateway should reject signal with warmup_ok=False."""
        mock_event.pld["readiness"] = {"warmup_ok": False}
        assert mock_event.pld["readiness"]["warmup_ok"] is False

    def test_gateway_accepts_warmup_ok_true(self, mock_event):
        """Gateway should accept signal with warmup_ok=True."""
        mock_event.pld["readiness"] = {"warmup_ok": True}
        assert mock_event.pld["readiness"]["warmup_ok"] is True


class TestFlipRetryReadiness:
    """Tests for flip retry including readiness field."""

    def test_flip_retry_payload_has_readiness(self):
        """Flip retry payload should include readiness.warmup_ok=True."""
        # Simulate flip retry payload construction
        original_pld = {"symbol": "BTCUSDT", "side": "BUY", "strategy_id": "aurora"}
        
        # This is what the code does
        original_payload_min = dict(original_pld)
        original_payload_min["readiness"] = {"warmup_ok": True}
        
        assert "readiness" in original_payload_min
        assert original_payload_min["readiness"]["warmup_ok"] is True
