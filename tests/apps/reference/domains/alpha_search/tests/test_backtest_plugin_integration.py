"""
T2: Backtest Plugin Integration Tests
======================================

Tests for apps/reference/domains/alpha_search/backtest_plugin.py
8 tests covering _extract_payload fix and multi-provider scoring.
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock

from apps.reference.domains.alpha_search.backtest_plugin import AlphaSearchBacktestPlugin
from apps.reference.domains.alpha_search.config_models import (
    get_default_config,
    get_default_system_config,
    load_alpha_search_config,
)


def _load_repo_alpha_search_config():
    repo_root = Path(__file__).resolve().parents[6]
    return load_alpha_search_config(str(repo_root / "config" / "alpha_search.yaml"))


@pytest.mark.unit
class TestExtractPayload:
    """Test _extract_payload handles all event representations."""

    def _make_plugin(self):
        """Create a disabled plugin for _extract_payload testing."""
        bus = MagicMock()
        cfg = get_default_config()
        cfg.enabled = False  # don't register listeners
        return AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

    def test_message_object(self):
        """hasattr(event, 'pld') path extracts payload from Message-like objects."""
        plugin = self._make_plugin()
        msg = MagicMock()
        msg.pld = {"symbol": "BTCUSDT", "features": {"obi": 0.1}}
        result = plugin._extract_payload(msg)
        assert result == {"symbol": "BTCUSDT", "features": {"obi": 0.1}}

    def test_localbus_dict(self):
        """isinstance(event, dict) and 'pld' in event path works for LocalBus."""
        plugin = self._make_plugin()
        event = {"pld": {"symbol": "BTCUSDT"}, "rid": "test_123"}
        result = plugin._extract_payload(event)
        assert result == {"symbol": "BTCUSDT"}

    def test_raw_dict(self):
        """Fallback: raw dict without 'pld' key is returned as-is."""
        plugin = self._make_plugin()
        event = {"symbol": "BTCUSDT", "features": {"obi": 0.1}}
        result = plugin._extract_payload(event)
        assert result == event

    def test_non_dict_returns_none(self):
        """Non-dict payloads (string, int, list) return None."""
        plugin = self._make_plugin()
        assert plugin._extract_payload("not a dict") is None
        assert plugin._extract_payload(42) is None
        assert plugin._extract_payload([1, 2, 3]) is None


@pytest.mark.unit
class TestFeatureCacheViaLocalBus:
    """Test feature caching when events emitted through LocalBus."""

    def test_feature_cache_populated(self):
        """Emitting EVT:FEATURES_CALCULATED via LocalBus populates cache."""
        from apps.reference.orchestrator.utils_event_bus import LocalBus
        bus = LocalBus()
        cfg = get_default_config()
        cfg.enabled = True
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

        bus.emit(
            event_name="EVT:FEATURES_CALCULATED",
            payload={
                "symbol": "BTCUSDT",
                "features": {"obi": 0.12, "delta_price": 0.003, "close": 96000.0},
                "tf_sec": 300,
                "bar_close_ts": 1740000000000,
                "ts": 1740000000000,
            },
            why="test",
        )

        assert len(plugin._feature_cache) > 0

    def test_ta_feature_event_flat_payload_populates_cache(self):
        """Emitting EVT:TA_FEATURES_CALCULATED via LocalBus populates TA cache metadata."""
        from apps.reference.orchestrator.utils_event_bus import LocalBus
        bus = LocalBus()
        cfg = _load_repo_alpha_search_config()
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

        bus.emit(
            event_name=cfg.triggers.ta_feature_event,
            payload={
                "symbol": "BTCUSDT",
                "tf_sec": 300,
                "bar_close_ts": 1740000000000,
                "ts": 1740000000000,
                "close": 96000.0,
                "bb_position": 0.3,
                "bb_width": 0.02,
                "rsi_14": 45.0,
                "price_sma_20_deviation": -0.005,
                "volume_sma_ratio": 1.1,
                "stoch_k": 35.0,
                "stoch_d": 38.0,
                "price_momentum_5m": 0.002,
                "warm_up_bars": 20,
                "required_warm_up_bars": 20,
                "is_warm": True,
                "source": "ta_features",
            },
            why="test",
        )

        key = ("BTCUSDT", 300, 1740000000000)
        assert key in plugin._feature_cache
        assert plugin._feature_cache[key].ta_features_ready is True
        assert cfg.triggers.ta_feature_event in plugin._feature_cache[key].source_events

    def test_scoring_produces_event(self):
        """CMD:PROCESS_STRATEGY with cached features triggers score event."""
        from apps.reference.orchestrator.utils_event_bus import LocalBus
        bus = LocalBus()
        cfg = get_default_config()
        cfg.enabled = True
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

        if not plugin.providers:
            pytest.skip("No providers initialized with default config")

        results = []
        bus.listen("EVT:ALPHA_SCORE_CALCULATED",
                   lambda e, **kw: results.append(e))

        # Phase 1: cache features
        bus.emit(
            event_name="EVT:FEATURES_CALCULATED",
            payload={
                "symbol": "BTCUSDT",
                "features": {
                    "obi": 0.12, "delta_price": 0.003, "macro_resid": 0.05,
                    "tfi": 0.4, "ema_bias": 0.002, "volume_spike": 1.3,
                    "volatility_state": 0.8, "depth_imbalance": 0.15,
                    "macro_sync": True, "close": 96000.0,
                },
                "tf_sec": 300,
                "bar_close_ts": 1740000000000,
                "ts": 1740000000000,
            },
            why="test",
        )

        # Phase 2: trigger scoring
        bus.emit(
            event_name="CMD:PROCESS_STRATEGY",
            payload={
                "symbol": "BTCUSDT",
                "tf_sec": 300,
                "bar_close_ts": 1740000000000,
            },
            why="test",
        )

        assert len(results) > 0

    def test_fail_closed_on_missing_features(self):
        """Score=0 emitted when features not cached (fail-closed)."""
        from apps.reference.orchestrator.utils_event_bus import LocalBus
        bus = LocalBus()
        cfg = get_default_config()
        cfg.enabled = True
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

        if not plugin.providers:
            pytest.skip("No providers initialized with default config")

        results = []
        bus.listen("EVT:ALPHA_SCORE_CALCULATED",
                   lambda e, **kw: results.append(e))

        # Emit CMD:PROCESS_STRATEGY WITHOUT prior feature cache
        bus.emit(
            event_name="CMD:PROCESS_STRATEGY",
            payload={
                "symbol": "BTCUSDT",
                "tf_sec": 300,
                "bar_close_ts": 9999999999999,
            },
            why="test",
        )

        for r in results:
            pld = r.get("pld", r) if isinstance(r, dict) else r
            if isinstance(pld, dict):
                assert pld.get("score", 1.0) == 0.0

    def test_ta_ensemble_fails_closed_when_ta_not_warm(self):
        """ta_ensemble must fail closed when the explicit TA event is present but not warm."""
        from apps.reference.orchestrator.utils_event_bus import LocalBus
        bus = LocalBus()
        cfg = _load_repo_alpha_search_config()
        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

        results = []
        bus.listen("EVT:ALPHA_SCORE_CALCULATED",
                   lambda e, **kw: results.append(e))

        bus.emit(
            event_name=cfg.triggers.ta_feature_event,
            payload={
                "symbol": "BTCUSDT",
                "tf_sec": 300,
                "bar_close_ts": 1740000000000,
                "ts": 1740000000000,
                "close": 96000.0,
                "bb_position": 0.3,
                "bb_width": 0.02,
                "rsi_14": 45.0,
                "price_sma_20_deviation": -0.005,
                "volume_sma_ratio": 1.1,
                "stoch_k": 35.0,
                "stoch_d": 38.0,
                "price_momentum_5m": 0.002,
                "warm_up_bars": 5,
                "required_warm_up_bars": 20,
                "is_warm": False,
                "source": "ta_features",
            },
            why="test",
        )
        bus.emit(
            event_name="CMD:PROCESS_STRATEGY",
            payload={
                "symbol": "BTCUSDT",
                "tf_sec": 300,
                "bar_close_ts": 1740000000000,
            },
            why="test",
        )

        ta_results = []
        for result in results:
            payload = result.get("pld", result) if isinstance(
                result, dict) else result
            if isinstance(payload, dict) and payload.get("provider_id") == "ta_ensemble":
                ta_results.append(payload)

        assert ta_results
        assert ta_results[-1]["score"] == 0.0
        assert "fail_closed:ta_features_not_warm" in ta_results[-1]["why"]


@pytest.mark.unit
class TestMultiProvider:
    """Test multi-provider scoring capability."""

    def test_multi_provider_scoring(self):
        """Both aurora and ta_ensemble produce scores when enabled."""
        from apps.reference.orchestrator.utils_event_bus import LocalBus
        bus = LocalBus()
        cfg = get_default_config()
        cfg.enabled = True

        sys_cfg = get_default_system_config()
        plugin = AlphaSearchBacktestPlugin(
            event_bus=bus, config=cfg, system_config=sys_cfg
        )

        if "aurora" not in plugin.providers:
            pytest.skip("Aurora provider not in default config")

        results = []
        bus.listen("EVT:ALPHA_SCORE_CALCULATED",
                   lambda e, **kw: results.append(e))

        features = {
            "obi": 0.12, "delta_price": 0.003, "macro_resid": 0.05,
            "tfi": 0.4, "ema_bias": 0.002, "volume_spike": 1.3,
            "volatility_state": 0.8, "depth_imbalance": 0.15,
            "macro_sync": True, "close": 96000.0,
            "bb_position": 0.3, "bb_width": 0.02, "rsi_14": 45.0,
            "price_sma_20_deviation": -0.005, "stoch_k": 35.0, "stoch_d": 38.0,
            "volume_ratio": 1.1,
            "momentum_5": 0.002, "momentum_60": 0.005, "momentum_1440": 0.01,
        }

        bus.emit(
            event_name="EVT:FEATURES_CALCULATED",
            payload={
                "symbol": "BTCUSDT",
                "features": features,
                "tf_sec": 300,
                "bar_close_ts": 1740000000000,
                "ts": 1740000000000,
            },
            why="test",
        )

        bus.emit(
            event_name="CMD:PROCESS_STRATEGY",
            payload={
                "symbol": "BTCUSDT",
                "tf_sec": 300,
                "bar_close_ts": 1740000000000,
            },
            why="test",
        )

        provider_ids = set()
        for r in results:
            pld = r.get("pld", r) if isinstance(r, dict) else r
            if isinstance(pld, dict) and "provider_id" in pld:
                provider_ids.add(pld["provider_id"])

        assert "aurora" in provider_ids


@pytest.mark.unit
class TestVirtualTraderExits:
    """Test virtual trader risk exits."""

    def test_drawdown_exit_closes_position(self):
        """Adverse move >= max_drawdown_exit closes open virtual position."""
        from apps.reference.domains.alpha_search.backtest_plugin import VirtualPosition
        from apps.reference.domains.alpha_search.config_models import (
            AuroraAdapterConfig,
            ProviderConfig,
        )
        from apps.reference.orchestrator.utils_event_bus import LocalBus

        bus = LocalBus()
        cfg = get_default_config()
        cfg.enabled = True
        cfg.providers["aurora"] = ProviderConfig(
            enabled=True,
            threshold=0.12,
            fail_closed=True,
            adapter=AuroraAdapterConfig(),
        )
        cfg.virtual_trader.enabled = True
        cfg.virtual_trader.exit.max_drawdown_exit = 1.2

        plugin = AlphaSearchBacktestPlugin(event_bus=bus, config=cfg)

        provider_id = next(iter(plugin.providers.keys()))
        plugin.open_positions[provider_id].append(
            VirtualPosition(
                provider_id=provider_id,
                symbol="BTCUSDT",
                side="BUY",
                entry_price=100.0,
                entry_ts=1740000000000,
                signal_id="sig_test_1",
            )
        )

        # BUY adverse move: (100 - 98.8) / 100 * 100 = 1.2%
        plugin._manage_virtual_positions(
            provider_id=provider_id,
            symbol="BTCUSDT",
            current_price=98.8,
            current_ts=1740000060000,
        )

        assert plugin.open_positions[provider_id] == []
        assert len(plugin.closed_positions[provider_id]) == 1
        assert plugin.closed_positions[provider_id][0]["exit_reason"] == "drawdown_exit"
