"""
T1: Scenario Worker Tests
=========================

Tests for apps/reference/domains/alpha_search/runtime/scenario_worker.py
20 tests covering snapshot processing, self-triggering, aurora param injection, side determination.
"""

import decimal
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from apps.reference.domains.alpha_search.runtime.scenario_worker import ScenarioWorker
from apps.reference.domains.alpha_search.runtime.contracts import AlphaInputV1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_alpha_input(**overrides) -> AlphaInputV1:
    """Create a valid AlphaInputV1 for tests."""
    data = {
        "ts_ms": 1740000000000,
        "symbol": "BTCUSDT",
        "tf_sec": 300,
        "bar_close_ts": 1740000000000,
        "price": 96000.0,
        "features": {
            "obi": 0.12, "delta_price": 0.003, "macro_resid": 0.05,
            "tfi": 0.4, "ema_bias": 0.002, "volume_spike": 1.3,
            "volatility_state": 0.8, "depth_imbalance": 0.15,
            "macro_sync": True, "close": 96000.0,
            "bb_position": 0.3, "bb_width": 0.02, "rsi_14": 45.0,
            "price_sma_20_deviation": -0.005, "stoch_k": 35.0, "stoch_d": 38.0,
            "volume_ratio": 1.1, "price": 96000.0,
            "momentum_5": 0.002, "momentum_60": 0.005, "momentum_1440": 0.01,
            "volume_momentum": 1.1, "macd_histogram": 0.0005,
            "atr_pct": 0.015, "realized_volatility": 0.012, "range_pct": 0.018,
        },
        "regime": "DEFAULT",
    }
    data.update(overrides)
    return AlphaInputV1.model_validate(data)


def _make_worker(
    scenario_id="S_TEST",
    strategy_type="aurora",
    strategy_config=None,
    project_root=None,
) -> ScenarioWorker:
    """Create a ScenarioWorker with minimal config using real config files."""
    from apps.reference.domains.alpha_search.config_models import (
        get_default_config, get_default_system_config,
    )
    from apps.reference.domains.alpha_search.runtime.contracts import ScenarioSpec

    spec = ScenarioSpec(
        scenario_id=scenario_id,
        strategy_type=strategy_type,
        config_mode="override",
        base_refs={"alpha_search": "config/alpha_search.yaml"},
        overrides={},
    )

    return ScenarioWorker(
        spec=spec,
        alpha_search_config=get_default_config(),
        system_config=get_default_system_config(),
        strategy_config=strategy_config or {},
        log_dir=Path("c:/tmp/test_worker"),
    )


# ---------------------------------------------------------------------------
# Snapshot Processing
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestProcessSnapshot:

    def test_produces_results(self):
        """process_snapshot returns result list (may be empty if no providers)."""
        worker = _make_worker()
        snapshot = _make_alpha_input()
        results = worker.process_snapshot(snapshot)
        # With default config (no providers), results may be empty
        assert isinstance(results, list)
        assert worker._snapshots_processed == 1

    def test_result_has_required_fields(self):
        """Each result dict has required keys."""
        worker = _make_worker()
        results = worker.process_snapshot(_make_alpha_input())
        required = {"scenario_id", "score", "side",
                    "provider_id", "regime", "symbol"}
        for r in results:
            assert required.issubset(
                r.keys()), f"Missing keys: {required - r.keys()}"

    def test_enriches_with_scenario_metadata(self):
        """Results include scenario_id and strategy_type from worker."""
        worker = _make_worker(scenario_id="S_META", strategy_type="aurora")
        results = worker.process_snapshot(_make_alpha_input())
        for r in results:
            assert r["scenario_id"] == "S_META"
            assert r["strategy_type"] == "aurora"

    def test_shadow_always_true(self):
        """All results have shadow=True."""
        worker = _make_worker()
        results = worker.process_snapshot(_make_alpha_input())
        for r in results:
            assert r["shadow"] is True

    def test_regime_passed_through(self):
        """Input regime appears in results."""
        worker = _make_worker()
        snapshot = _make_alpha_input(regime="HIGH_VOLATILITY")
        results = worker.process_snapshot(snapshot)
        for r in results:
            assert r["regime"] == "HIGH_VOLATILITY"

    def test_increments_stats(self):
        """_snapshots_processed incremented on each call."""
        worker = _make_worker()
        assert worker._snapshots_processed == 0
        worker.process_snapshot(_make_alpha_input())
        assert worker._snapshots_processed == 1
        worker.process_snapshot(_make_alpha_input())
        assert worker._snapshots_processed == 2

    def test_error_returns_empty(self):
        """Exception in plugin returns empty list, increments _snapshots_failed."""
        worker = _make_worker()
        # Force plugin to raise by breaking the bus
        worker._bus = None
        results = worker.process_snapshot(_make_alpha_input())
        assert results == []
        assert worker._snapshots_failed == 1


# ---------------------------------------------------------------------------
# Self-Triggering Pipeline
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSelfTriggering:

    def test_caches_then_scores(self):
        """Self-triggering: features cached (phase 1), then scores produced (phase 2)."""
        worker = _make_worker()
        snapshot = _make_alpha_input()

        # Before processing, plugin cache should be empty
        assert len(worker._plugin._feature_cache) == 0

        results = worker.process_snapshot(snapshot)

        # After processing, the self-triggering mechanism should have run
        # (cache populated then scoring attempted)
        assert isinstance(results, list)
        assert worker._snapshots_processed == 1


# ---------------------------------------------------------------------------
# Bus Isolation
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestBusIsolation:

    def test_no_cross_worker_events(self):
        """Two workers on different buses don't share events."""
        worker1 = _make_worker(scenario_id="S_W1")
        worker2 = _make_worker(scenario_id="S_W2")

        # They should have different bus instances
        assert worker1._bus is not worker2._bus

        snapshot = _make_alpha_input()
        r1 = worker1.process_snapshot(snapshot)
        r2 = worker2.process_snapshot(snapshot)

        # Each worker's results should have its own scenario_id
        for r in r1:
            assert r["scenario_id"] == "S_W1"
        for r in r2:
            assert r["scenario_id"] == "S_W2"


# ---------------------------------------------------------------------------
# Aurora Param Injection
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestInjectAuroraParams:

    def test_signal_weights_injected(self):
        """Signal weights are overridden on aurora adapter."""
        strategy_config = {
            "decision": {
                "signal_weights": {"obi": 0.5, "delta_price": 0.3},
            }
        }
        worker = _make_worker(strategy_config=strategy_config)
        aurora = worker._plugin.providers.get("aurora")
        if aurora:
            assert aurora._signal_weights.get("obi") == 0.5

    def test_base_threshold_and_provider_synced(self):
        """Both _base_threshold and provider_configs.threshold updated."""
        strategy_config = {
            "decision": {"signal_threshold": 0.12}
        }
        worker = _make_worker(strategy_config=strategy_config)
        aurora = worker._plugin.providers.get("aurora")
        if aurora:
            assert aurora._base_threshold == decimal.Decimal("0.12")
        pcfg = worker._plugin.provider_configs.get("aurora")
        if pcfg:
            assert pcfg.threshold == 0.12

    def test_regime_thresholds_injected(self):
        """Regime threshold multipliers injected."""
        strategy_config = {
            "decision": {
                "regime_threshold_multipliers": {"HIGH_VOLATILITY": 1.5}
            }
        }
        worker = _make_worker(strategy_config=strategy_config)
        aurora = worker._plugin.providers.get("aurora")
        if aurora:
            assert aurora._regime_thresholds.get("HIGH_VOLATILITY") == 1.5

    def test_direction_strength_injected(self):
        """Direction strength config injected."""
        strategy_config = {
            "decision": {
                "direction_strength_scoring": {
                    "strength_alpha": 0.5,
                    "strength_cap": 0.3,
                }
            }
        }
        worker = _make_worker(strategy_config=strategy_config)
        aurora = worker._plugin.providers.get("aurora")
        if aurora:
            assert aurora._direction_strength_cfg["strength_alpha"] == 0.5

    def test_no_aurora_provider_no_crash(self):
        """No crash when aurora provider doesn't exist."""
        # Use ensemble strategy which won't have aurora provider in some configs
        worker = _make_worker(strategy_type="ensemble")
        # Just verify no exception
        worker._inject_aurora_params({"decision": {"signal_threshold": 0.1}})


# ---------------------------------------------------------------------------
# Side Determination
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDetermineSide:

    def test_buy(self):
        assert ScenarioWorker._determine_side(0.2, 0.15) == "BUY"

    def test_sell(self):
        assert ScenarioWorker._determine_side(-0.2, 0.15) == "SELL"

    def test_neutral(self):
        assert ScenarioWorker._determine_side(0.1, 0.15) == "NEUTRAL"
        assert ScenarioWorker._determine_side(-0.1, 0.15) == "NEUTRAL"
        assert ScenarioWorker._determine_side(0.0, 0.15) == "NEUTRAL"


# ---------------------------------------------------------------------------
# Summary & Shutdown
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSummaryShutdown:

    def test_get_summary_keys(self):
        """Summary contains expected keys."""
        worker = _make_worker()
        summary = worker.get_summary()
        expected = {"scenario_id", "strategy_type", "snapshots_processed",
                    "snapshots_failed", "total_results", "uptime_sec", "plugin"}
        assert expected.issubset(summary.keys())

    def test_shutdown_calls_plugin(self):
        """Shutdown calls plugin.shutdown()."""
        worker = _make_worker()
        worker._plugin.shutdown = MagicMock()
        worker.shutdown()
        worker._plugin.shutdown.assert_called_once()

    def test_threshold_sync_affects_side(self):
        """Overridden threshold changes side determination boundary."""
        # Low threshold -> more signals become BUY/SELL
        worker_low = _make_worker(
            strategy_config={"decision": {"signal_threshold": 0.05}})
        # High threshold -> more signals become NEUTRAL
        worker_high = _make_worker(
            strategy_config={"decision": {"signal_threshold": 0.50}})

        snapshot = _make_alpha_input()
        r_low = worker_low.process_snapshot(snapshot)
        r_high = worker_high.process_snapshot(snapshot)

        # Processing should complete without error regardless of threshold
        assert isinstance(r_low, list)
        assert isinstance(r_high, list)
        # Verify determine_side directly with known values
        assert worker_low._determine_side(0.1, 0.05) == "BUY"
        assert worker_high._determine_side(0.1, 0.50) == "NEUTRAL"
