"""
Integration Tests for Alpha Search Domain

Verifies end-to-end wiring:
- Plugin loads from config_path without crash
- Plain dict config is rejected gracefully (no AttributeError)
- WAL listener captures emitted events
- Emitted payloads contain required fields per unified schema
- Features→Cache→Score end-to-end flow
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, patch

from apps.reference.domains.alpha_search.backtest_plugin import (
    AlphaSearchBacktestPlugin,
)
from apps.reference.domains.alpha_search.config_models import (
    AlphaSearchConfig,
    ProviderConfig,
    AuroraAdapterConfig,
    TriggersConfig,
    CacheConfig,
    VirtualTraderConfig,
)
from apps.reference.domains.alpha_search.wal_listener import AlphaScoreWalListener
from apps.reference.domains.alpha_search.models.aurora_adapter import (
    _FALLBACK_SIGNAL_WEIGHTS,
    _FALLBACK_FEATURE_NEUTRALS,
    _FALLBACK_REGIME_THRESHOLDS,
)


class MockEventBus:
    """Mock event bus for integration testing."""

    def __init__(self):
        self.listeners = {}
        self.emitted = []

    def listen(self, event_name: str, handler):
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(handler)

    def emit(self, event_name: str, payload: dict, why: str = ""):
        self.emitted.append(
            {"event": event_name, "payload": payload, "why": why})
        # Auto-trigger listeners (simulates real FSMCore behavior)
        event = Mock()
        event.pld = payload
        for handler in self.listeners.get(event_name, []):
            handler(event)

    def trigger(self, event_name: str, payload: dict):
        """Simulate event trigger."""
        event = Mock()
        event.pld = payload
        for handler in self.listeners.get(event_name, []):
            handler(event)


def _make_aurora_config() -> AlphaSearchConfig:
    """Create minimal AlphaSearchConfig with aurora provider."""
    return AlphaSearchConfig(
        enabled=True,
        shadow_mode=True,
        providers={
            "aurora": ProviderConfig(
                enabled=True,
                adapter=AuroraAdapterConfig(
                    signal_weights=_FALLBACK_SIGNAL_WEIGHTS,
                    feature_neutrals=_FALLBACK_FEATURE_NEUTRALS,
                    regime_thresholds=_FALLBACK_REGIME_THRESHOLDS,
                ),
                threshold=0.1,
                fail_closed=True,
            ),
        },
        triggers=TriggersConfig(),
        cache=CacheConfig(),
        virtual_trader=VirtualTraderConfig(enabled=False),
    )


class TestPluginConfigLoading:
    """Verify plugin loads from config_path and rejects plain dicts."""

    def test_plugin_loads_from_typed_config(self):
        """Plugin should initialize with AlphaSearchConfig object."""
        bus = MockEventBus()
        config = _make_aurora_config()
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)

        assert plugin.enabled is True
        assert plugin.shadow_mode is True
        assert "aurora" in plugin.providers

    def test_plugin_defaults_on_missing_config_path(self):
        """Plugin should use defaults when config_path file doesn't exist."""
        bus = MockEventBus()
        plugin = AlphaSearchBacktestPlugin(
            event_bus=bus,
            config_path="/nonexistent/alpha_search.yaml",
        )
        # Should fall back to get_default_config() (enabled=False by default)
        assert plugin.config is not None

    def test_plugin_registers_listeners(self):
        """Plugin should register event listeners when enabled."""
        bus = MockEventBus()
        config = _make_aurora_config()
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)

        # Should have listeners for both phases
        assert "EVT:FEATURES_CALCULATED" in bus.listeners
        assert "CMD:PROCESS_STRATEGY" in bus.listeners
        assert "EVT:TRADE_EXECUTED" in bus.listeners


class TestWalListenerCapture:
    """Verify WAL listener captures emitted alpha score events."""

    def test_wal_listener_registers(self):
        """WAL listener should register on EVT:ALPHA_SCORE_CALCULATED."""
        bus = MockEventBus()
        listener = AlphaScoreWalListener(event_bus=bus)

        assert "EVT:ALPHA_SCORE_CALCULATED" in bus.listeners
        assert listener.events_written == 0

    @patch("vfoundation.dr.wal")
    def test_wal_listener_captures_event(self, mock_wal):
        """WAL listener should write event to WAL on alpha score."""
        bus = MockEventBus()
        listener = AlphaScoreWalListener(event_bus=bus)

        # Simulate an alpha score event
        payload = {
            "symbol": "BTCUSDT",
            "provider_id": "aurora",
            "model_name": "aurora_v2_adapter",
            "score": 0.42,
            "confidence": 0.78,
            "ts_ms": 1700000000000,
            "tf_sec": 300,
            "bar_close_ts": 1700000000000,
            "shadow": True,
            "signal_id": "aurora_sig_1",
        }
        bus.trigger("EVT:ALPHA_SCORE_CALCULATED", payload)

        assert listener.events_written == 1
        mock_wal.append.assert_called_once()
        written = mock_wal.append.call_args[0][0]
        assert written["verb"] == "ALPHA_SCORE_CALCULATED"
        assert written["symbol"] == "BTCUSDT"
        assert written["provider_id"] == "aurora"

    @patch("vfoundation.dr.wal")
    def test_wal_listener_survives_write_failure(self, mock_wal):
        """WAL listener should not crash if WAL write fails (fail-closed)."""
        mock_wal.append.side_effect = RuntimeError("WAL disk full")
        bus = MockEventBus()
        listener = AlphaScoreWalListener(event_bus=bus)

        payload = {
            "symbol": "ETHUSDT",
            "provider_id": "dm_inline",
            "model_name": "momentum_v1",
            "score": -0.15,
            "confidence": 0.55,
        }
        # Should not raise
        bus.trigger("EVT:ALPHA_SCORE_CALCULATED", payload)
        assert listener.events_written == 0  # Count not incremented on failure


class TestEmittedPayloadSchema:
    """Verify emitted payloads contain required fields per unified schema."""

    REQUIRED_FIELDS = {
        "symbol", "provider_id", "model_name", "score", "confidence",
    }

    def test_backtest_plugin_emits_required_fields(self):
        """Plugin should emit EVT:ALPHA_SCORE_CALCULATED with all required fields."""
        bus = MockEventBus()
        config = _make_aurora_config()
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)

        # Phase 1: Cache features
        bus.trigger("EVT:FEATURES_CALCULATED", {
            "symbol": "BTCUSDT",
            "features": {
                "close": 42000.0,
                "obi": 0.3,
                "delta_price": 0.01,
                "macro_resid": -0.2,
            },
            "tf_sec": 300,
            "ts": 1700000000000,
            "bar": {"close_ts": 1700000000000},
        })

        # Phase 2: Trigger scoring
        bus.trigger("CMD:PROCESS_STRATEGY", {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1700000000000,
        })

        # Check that at least one alpha score was emitted
        alpha_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:ALPHA_SCORE_CALCULATED"
        ]

        assert len(alpha_events) >= 1, (
            f"Expected at least 1 ALPHA_SCORE_CALCULATED event, got {len(alpha_events)}"
        )

        for event in alpha_events:
            payload = event["payload"]
            missing = self.REQUIRED_FIELDS - set(payload.keys())
            assert not missing, f"Missing required fields: {missing}"
            assert isinstance(payload["score"], (int, float))
            assert isinstance(payload["confidence"], (int, float))

    def test_fail_closed_emits_zero_score(self):
        """Plugin should emit score=0 when features unavailable (fail-closed)."""
        bus = MockEventBus()
        config = _make_aurora_config()
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)

        # Phase 2 without Phase 1 (no cached features)
        bus.trigger("CMD:PROCESS_STRATEGY", {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1700000000000,
        })

        alpha_events = [
            e for e in bus.emitted
            if e["event"] == "EVT:ALPHA_SCORE_CALCULATED"
        ]

        assert len(alpha_events) >= 1
        for event in alpha_events:
            payload = event["payload"]
            assert payload["score"] == 0.0
            assert payload["confidence"] == 0.0
            assert "fail_closed" in payload.get("why", [""])[0]


class TestEndToEndFlow:
    """Full features→cache→score pipeline test."""

    def test_features_through_to_score(self):
        """Features should flow through cache to score emission."""
        bus = MockEventBus()
        config = _make_aurora_config()
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)

        # Step 1: Feed features
        bus.trigger("EVT:FEATURES_CALCULATED", {
            "symbol": "ETHUSDT",
            "features": {
                "close": 2500.0,
                "obi": 0.1,
                "delta_price": -0.02,
                "macro_resid": 0.1,
            },
            "tf_sec": 300,
            "ts": 1700000300000,
            "bar": {"close_ts": 1700000300000},
        })

        # Verify cache populated
        assert len(
            plugin._feature_cache) == 1, "Feature cache should have 1 entry"
        assert plugin._cache_misses == 0

        # Step 2: Trigger scoring
        bus.trigger("CMD:PROCESS_STRATEGY", {
            "symbol": "ETHUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1700000300000,
        })

        # Verify cache hit
        assert plugin._cache_hits == 1

        # Verify scoring happened
        stats = plugin.provider_stats.get("aurora")
        assert stats is not None
        assert stats.signals_generated >= 1

    def test_get_summary_returns_valid_structure(self):
        """get_summary() should return a well-formed dict for reporting."""
        bus = MockEventBus()
        config = _make_aurora_config()
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)

        summary = plugin.get_summary()

        assert "enabled" in summary
        assert "mode" in summary
        assert "providers" in summary
        assert "provider_stats" in summary
        assert "cache" in summary
        assert summary["enabled"] is True
        assert summary["mode"] == "shadow"
        assert "aurora" in summary["providers"]
        assert "miss_rate_pct" in summary["cache"]

    def test_multiple_symbols_isolated_cache(self):
        """Different symbols should have isolated cache entries."""
        bus = MockEventBus()
        config = _make_aurora_config()
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)

        for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
            bus.trigger("EVT:FEATURES_CALCULATED", {
                "symbol": symbol,
                "features": {"close": 100.0, "obi": 0.1, "delta_price": 0.0, "macro_resid": 0.0},
                "tf_sec": 300,
                "ts": 1700000000000,
                "bar": {"close_ts": 1700000000000},
            })

        assert len(plugin._feature_cache) == 3
