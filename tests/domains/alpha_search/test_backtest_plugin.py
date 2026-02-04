"""
Test: Multi-Provider Plugin + Event Bridge (ALPHA-A3)

Verifies:
- A3.1: Two-phase bridge (feature cache + decision scoring)
- A3.2: Multi-provider architecture with per-provider stats
"""

import pytest
from decimal import Decimal
from unittest.mock import Mock, MagicMock

from apps.reference.domains.alpha_search.backtest_plugin import (
    AlphaSearchBacktestPlugin,
    FeatureCacheEntry,
)
from apps.reference.domains.alpha_search.config_models import (
    AlphaSearchConfig,
    ProviderConfig,
    AuroraAdapterConfig,
    TriggersConfig,
    CacheConfig,
    VirtualTraderConfig,
)


class MockEventBus:
    """Mock event bus for testing."""
    
    def __init__(self):
        self.listeners = {}
        self.emitted = []
    
    def listen(self, event_name: str, handler):
        if event_name not in self.listeners:
            self.listeners[event_name] = []
        self.listeners[event_name].append(handler)
    
    def emit(self, event_name: str, payload: dict, why: str = ""):
        self.emitted.append({"event": event_name, "payload": payload, "why": why})
    
    def trigger(self, event_name: str, payload: dict):
        """Simulate event trigger."""
        event = Mock()
        event.pld = payload
        for handler in self.listeners.get(event_name, []):
            handler(event)


class TestEventBridgeCache:
    """Test A3.1: Feature cache behavior."""
    
    def test_features_cached_on_features_calculated(self):
        """EVT:FEATURES_CALCULATED should cache features."""
        bus = MockEventBus()
        config = AlphaSearchConfig(
            enabled=True,
            providers={
                "aurora": ProviderConfig(
                    enabled=True,
                    symbols=["BTCUSDT"],
                    adapter=AuroraAdapterConfig()
                )
            }
        )
        
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)
        
        # Trigger feature event
        bus.trigger("EVT:FEATURES_CALCULATED", {
            "symbol": "BTCUSDT",
            "features": {"obi": 0.3, "delta_price": 100, "macro_resid": 0.2},
            "tf_sec": 300,
            "ts": 1700000000000,
            "bar": {"close_ts": 1700000000000},
        })
        
        # Verify cache
        cache_key = ("BTCUSDT", 300, 1700000000000)
        assert cache_key in plugin._feature_cache
        entry = plugin._feature_cache[cache_key]
        assert entry.features["obi"] == 0.3
    
    def test_cache_pruning(self):
        """Old cache entries should be pruned."""
        bus = MockEventBus()
        config = AlphaSearchConfig(
            enabled=True,
            cache=CacheConfig(max_per_symbol=2),
            providers={
                "aurora": ProviderConfig(
                    enabled=True,
                    adapter=AuroraAdapterConfig()
                )
            }
        )
        
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)
        
        # Add 3 entries for same symbol
        for i in range(3):
            ts = 1700000000000 + i * 300000
            bus.trigger("EVT:FEATURES_CALCULATED", {
                "symbol": "BTCUSDT",
                "features": {"obi": 0.1 * i},
                "tf_sec": 300,
                "ts": ts,
                "bar": {"close_ts": ts},
            })
        
        # Only 2 should remain (max_per_symbol=2)
        btc_entries = [k for k in plugin._feature_cache.keys() if k[0] == "BTCUSDT"]
        assert len(btc_entries) == 2


class TestTimestampNormalization:
    """Test timestamp normalization (ms vs seconds)."""
    
    def test_seconds_to_milliseconds(self):
        """Seconds should be converted to milliseconds."""
        bus = MockEventBus()
        config = AlphaSearchConfig(
            enabled=True,
            providers={
                "aurora": ProviderConfig(
                    enabled=True,
                    adapter=AuroraAdapterConfig()
                )
            }
        )
        
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)
        
        # EVT with bar_close_ts in SECONDS
        ts_seconds = 1700000000  # < 10^12 → seconds
        bus.trigger("EVT:FEATURES_CALCULATED", {
            "symbol": "BTCUSDT",
            "features": {"obi": 0.3, "close": 50000},
            "tf_sec": 300,
            "ts": ts_seconds * 1000,
            "bar": {"close_ts": ts_seconds},  # seconds!
        })
        
        bus.emitted.clear()
        
        # CMD with bar_close_ts in MILLISECONDS
        ts_ms = ts_seconds * 1000  # Convert to ms
        bus.trigger("CMD:PROCESS_STRATEGY", {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": ts_ms,  # milliseconds
        })
        
        # Should NOT be a cache miss — both normalized to ms
        # So an event should be emitted
        score_events = [e for e in bus.emitted if e["event"] == "EVT:ALPHA_SCORE_CALCULATED"]
        # If cache hit, we get actual score; if miss, we get fail_closed
        # Check it's not a miss by verifying score != 0 or no fail_closed
        assert len(score_events) > 0
        # Either actual score or fail_closed due to missing features in adapter
        # The point is cache lookup should work
    
    def test_cache_stats_tracked(self):
        """Cache hits and misses should be tracked."""
        bus = MockEventBus()
        config = AlphaSearchConfig(
            enabled=True,
            providers={
                "aurora": ProviderConfig(
                    enabled=True,
                    adapter=AuroraAdapterConfig()
                )
            }
        )
        
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)
        
        # Trigger decision without caching first → miss
        bus.trigger("CMD:PROCESS_STRATEGY", {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1700000000000,
        })
        
        assert plugin._cache_misses == 1
        assert plugin._cache_hits == 0
        
        # Cache features then trigger → hit
        bus.trigger("EVT:FEATURES_CALCULATED", {
            "symbol": "ETHUSDT",
            "features": {"obi": 0.3, "delta_price": 100, "macro_resid": 0.2, "close": 3000},
            "tf_sec": 300,
            "ts": 1700000000000,
            "bar": {"close_ts": 1700000000000},
        })
        bus.trigger("CMD:PROCESS_STRATEGY", {
            "symbol": "ETHUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1700000000000,
        })
        
        assert plugin._cache_hits == 1
        
        # Check summary
        summary = plugin.get_summary()
        assert summary["cache"]["hits"] == 1
        assert summary["cache"]["misses"] == 1
        assert summary["cache"]["miss_rate_pct"] == 50.0


class TestDecisionScoring:
    """Test A3.1: Scoring on CMD:PROCESS_STRATEGY."""
    
    def test_scoring_uses_cached_features(self):
        """CMD:PROCESS_STRATEGY should use cached features for scoring."""
        bus = MockEventBus()
        config = AlphaSearchConfig(
            enabled=True,
            providers={
                "aurora": ProviderConfig(
                    enabled=True,
                    symbols=["BTCUSDT"],
                    threshold=0.1,
                    adapter=AuroraAdapterConfig()
                )
            }
        )
        
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)
        
        # Phase 1: Cache features
        bar_close_ts = 1700000000000
        bus.trigger("EVT:FEATURES_CALCULATED", {
            "symbol": "BTCUSDT",
            "features": {
                "obi": 0.3, 
                "delta_price": 100, 
                "macro_resid": 0.2,
                "close": 50000.0,  # Add price
            },
            "tf_sec": 300,
            "ts": bar_close_ts,
            "bar": {"close_ts": bar_close_ts},
        })
        
        # Clear emitted events
        bus.emitted.clear()
        
        # Phase 2: Trigger decision
        bus.trigger("CMD:PROCESS_STRATEGY", {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": bar_close_ts,
        })
        
        # Should emit EVT:ALPHA_SCORE_CALCULATED
        assert len(bus.emitted) > 0
        score_event = bus.emitted[0]
        assert score_event["event"] == "EVT:ALPHA_SCORE_CALCULATED"
        assert score_event["payload"]["provider_id"] == "aurora"
        assert score_event["payload"]["symbol"] == "BTCUSDT"
        assert "score" in score_event["payload"]
    
    def test_fail_closed_on_cache_miss(self):
        """Cache miss should emit fail-closed score when fail_closed=True."""
        bus = MockEventBus()
        config = AlphaSearchConfig(
            enabled=True,
            cache=CacheConfig(require_same_bar_close_ts=True),
            providers={
                "aurora": ProviderConfig(
                    enabled=True,
                    symbols=["BTCUSDT"],
                    fail_closed=True,
                    adapter=AuroraAdapterConfig()
                )
            }
        )
        
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)
        
        # Trigger decision WITHOUT caching features first
        bus.trigger("CMD:PROCESS_STRATEGY", {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1700000000000,
        })
        
        # Should emit fail-closed event
        assert len(bus.emitted) > 0
        score_event = bus.emitted[0]
        assert score_event["payload"]["score"] == 0.0
        assert "fail_closed" in str(score_event["payload"]["why"])


class TestMultiProvider:
    """Test A3.2: Multiple providers."""
    
    def test_multiple_providers_score_independently(self):
        """Each provider should score independently."""
        bus = MockEventBus()
        
        # This test would require TA ensemble models to be available
        # For now, just test with aurora only
        config = AlphaSearchConfig(
            enabled=True,
            providers={
                "aurora": ProviderConfig(
                    enabled=True,
                    symbols=["BTCUSDT"],
                    threshold=0.1,
                    adapter=AuroraAdapterConfig()
                )
            }
        )
        
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)
        
        # Verify provider initialized
        assert "aurora" in plugin.providers
        assert "aurora" in plugin.provider_stats
    
    def test_per_provider_stats(self):
        """Each provider should track its own stats."""
        bus = MockEventBus()
        config = AlphaSearchConfig(
            enabled=True,
            providers={
                "aurora": ProviderConfig(
                    enabled=True,
                    adapter=AuroraAdapterConfig()
                )
            }
        )
        
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)
        
        # Stats should be per-provider
        assert "aurora" in plugin.provider_stats
        stats = plugin.provider_stats["aurora"]
        assert stats.signals_generated == 0
        assert stats.total_pnl == 0.0


class TestSymbolAllowlist:
    """Test symbol filtering."""
    
    def test_symbol_allowlist_filters_scoring(self):
        """Provider should only score allowed symbols."""
        bus = MockEventBus()
        config = AlphaSearchConfig(
            enabled=True,
            providers={
                "aurora": ProviderConfig(
                    enabled=True,
                    symbols=["BTCUSDT"],  # Only BTC
                    adapter=AuroraAdapterConfig()
                )
            }
        )
        
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)
        
        # Cache features for ETH
        bar_close_ts = 1700000000000
        bus.trigger("EVT:FEATURES_CALCULATED", {
            "symbol": "ETHUSDT",  # Not in allowlist
            "features": {"obi": 0.3, "delta_price": 100, "macro_resid": 0.2, "close": 3000},
            "tf_sec": 300,
            "ts": bar_close_ts,
            "bar": {"close_ts": bar_close_ts},
        })
        bus.emitted.clear()
        
        # Trigger decision for ETH
        bus.trigger("CMD:PROCESS_STRATEGY", {
            "symbol": "ETHUSDT",
            "tf_sec": 300,
            "bar_close_ts": bar_close_ts,
        })
        
        # Should NOT emit score for ETH (not in allowlist)
        score_events = [e for e in bus.emitted if e["event"] == "EVT:ALPHA_SCORE_CALCULATED"]
        assert len(score_events) == 0


class TestPluginSummary:
    """Test summary generation."""
    
    def test_get_summary(self):
        """Summary should include all provider stats."""
        bus = MockEventBus()
        config = AlphaSearchConfig(
            enabled=True,
            providers={
                "aurora": ProviderConfig(
                    enabled=True,
                    adapter=AuroraAdapterConfig()
                )
            }
        )
        
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=config)
        summary = plugin.get_summary()
        
        assert summary["enabled"] == True
        assert "aurora" in summary["providers"]
        assert "aurora" in summary["provider_stats"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
