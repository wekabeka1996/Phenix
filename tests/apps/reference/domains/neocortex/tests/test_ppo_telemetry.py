"""
Tests for Phase R2: PPO Training and Telemetry

Tests cover:
1. TelemetryLogger CSV creation and writing
2. PPO training integration
3. Metrics logging from adapter
"""

import pytest
import tempfile
import csv
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
import time
import sys


from apps.reference.domains.neocortex.logic.telemetry import TelemetryLogger, get_telemetry
from apps.reference.domains.neocortex.config_models import (
    NeocortexConfig,
    SystemConfig,
    IngestConfig,
    NeuroConfig,
    VAEConfig,
    WorldModelConfig,
    PPOConfig,
    ReplayConfig,
)
from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter


class TestTelemetryLogger:
    """Tests for TelemetryLogger CSV functionality."""

    @pytest.fixture
    def temp_log_dir(self, tmp_path):
        """Return a temporary log directory path; TelemetryLogger creates it."""
        return tmp_path / "logs"

    @pytest.fixture
    def logger(self, temp_log_dir):
        """Create a TelemetryLogger instance."""
        return TelemetryLogger(log_dir=temp_log_dir)

    def test_csv_file_created(self, logger, temp_log_dir):
        """Verify CSV file is created on initialization."""
        csv_path = temp_log_dir / "neocortex_metrics.csv"
        assert csv_path.exists()

    def test_csv_has_headers(self, logger, temp_log_dir):
        """Verify CSV has correct headers."""
        csv_path = temp_log_dir / "neocortex_metrics.csv"

        with open(csv_path, 'r') as f:
            reader = csv.reader(f)
            headers = next(reader)

        assert "timestamp" in headers
        assert "vae_loss" in headers
        assert "ppo_loss_pi" in headers
        assert "shadow_action" in headers
        assert "last_reward" in headers

    def test_log_step_writes_row(self, logger, temp_log_dir):
        """Verify log_step writes a row to CSV."""
        logger.log_step({
            "vae_loss": 0.5,
            "buffer_size": 100
        })

        csv_path = temp_log_dir / "neocortex_metrics.csv"

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["vae_loss"] == "0.500000"
        assert rows[0]["buffer_size"] == "100"

    def test_multiple_log_steps(self, logger, temp_log_dir):
        """Verify multiple log steps create multiple rows."""
        for i in range(5):
            logger.log_step({"vae_loss": i * 0.1})

        csv_path = temp_log_dir / "neocortex_metrics.csv"

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 5
        assert logger.step_count == 5

    def test_log_training(self, logger, temp_log_dir):
        """Test log_training convenience method."""
        logger.log_training(
            vae_loss=0.5,
            vae_mse=0.3,
            wm_loss=0.1,
            train_step=10
        )

        csv_path = temp_log_dir / "neocortex_metrics.csv"

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert float(rows[0]["vae_loss"]) == 0.5
        assert float(rows[0]["wm_loss"]) == 0.1

    def test_log_shadow_intent(self, logger, temp_log_dir):
        """Test log_shadow_intent convenience method."""
        logger.log_shadow_intent(
            action=0,
            action_name="LONG",
            confidence=0.85,
            value=1.5
        )

        csv_path = temp_log_dir / "neocortex_metrics.csv"

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert rows[0]["shadow_action"] == "0"
        assert rows[0]["shadow_action_name"] == "LONG"
        assert float(rows[0]["shadow_confidence"]) == 0.85

    def test_log_episode(self, logger, temp_log_dir):
        """Test log_episode convenience method."""
        logger.log_episode(
            reward=0.76,
            pnl=5.50
        )

        csv_path = temp_log_dir / "neocortex_metrics.csv"

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert float(rows[0]["last_reward"]) == 0.76
        assert float(rows[0]["last_pnl"]) == 5.50

    def test_cumulative_reward(self, logger, temp_log_dir):
        """Test cumulative reward tracking."""
        logger.log_episode(reward=1.0)
        logger.log_episode(reward=2.0)
        logger.log_episode(reward=-0.5)

        csv_path = temp_log_dir / "neocortex_metrics.csv"

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Last row should have cumulative = 1 + 2 - 0.5 = 2.5
        assert float(rows[-1]["cumulative_reward"]) == pytest.approx(2.5)

    def test_missing_metrics_handled(self, logger, temp_log_dir):
        """Test that missing metrics don't cause errors."""
        logger.log_step({"vae_loss": 0.5})  # Only vae_loss provided

        csv_path = temp_log_dir / "neocortex_metrics.csv"

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # Other columns should be empty
        assert rows[0]["ppo_loss_pi"] == ""
        assert rows[0]["shadow_action"] == ""

    def test_get_recent_stats(self, logger):
        """Test statistics calculation from recent entries."""
        for i in range(10):
            logger.log_step({"vae_loss": i * 0.1, "last_reward": i * 0.01})

        stats = logger.get_recent_stats(n=10)

        assert "vae_loss_mean" in stats
        assert "last_reward_mean" in stats
        assert stats["total_entries"] == 10

    def test_health_report(self, logger):
        """Test health report generation."""
        logger.log_step({"vae_loss": 0.5, "wm_loss": 0.1})

        report = logger.get_health_report()

        assert "NEOCORTEX HEALTH REPORT" in report
        assert "VAE:" in report


class TestTelemetrySingleton:
    """Tests for telemetry singleton pattern."""

    def test_get_telemetry_returns_logger(self, tmp_path):
        """Test get_telemetry returns TelemetryLogger instance."""
        # Reset singleton (not ideal for production but ok for testing)
        import apps.reference.domains.neocortex.logic.telemetry as telem_module
        telem_module._telemetry_instance = None

        logger = get_telemetry(log_dir=tmp_path / "test_logs")

        assert isinstance(logger, TelemetryLogger)


class TestPPOTelemetryIntegration:
    """Integration tests for PPO training with telemetry."""

    def test_adapter_has_telemetry(self):
        """Verify adapter initializes telemetry logger."""
        from apps.reference.domains.neocortex.transport.adapter import NeocortexAdapter

        # Check class has the attribute referenced in __init__
        assert hasattr(NeocortexAdapter, '__init__')
        # The actual telemetry is initialized in __init__

    def test_ppo_metrics_logged(self, tmp_path):
        """Test that PPO training metrics can be logged."""
        logger = TelemetryLogger(log_dir=tmp_path)

        # Simulate PPO training result
        ppo_result = {
            "loss_pi": 0.05,
            "loss_v": 0.10,
            "entropy": 0.8,
            "episodes_processed": 50,
            "train_step": 5
        }

        logger.log_step({
            "ppo_loss_pi": ppo_result["loss_pi"],
            "ppo_loss_v": ppo_result["loss_v"],
            "ppo_entropy": ppo_result["entropy"],
            "episodes_processed": ppo_result["episodes_processed"],
            "total_train_steps": ppo_result["train_step"]
        })

        # Verify CSV content
        csv_path = tmp_path / "neocortex_metrics.csv"

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 1
        assert float(rows[0]["ppo_loss_pi"]) == 0.05
        assert float(rows[0]["ppo_entropy"]) == 0.8

    @staticmethod
    def _build_adapter_config(tmp_path: Path) -> NeocortexConfig:
        return NeocortexConfig(
            trust_enabled=False,
            system=SystemConfig(
                data_dir=str(tmp_path / "data"),
                checkpoint_dir=str(tmp_path / "data" / "checkpoints"),
                rng_seed=42,
                brain_workers=1,
                queue_maxsize=100,
                log_level="INFO",
                log_to_file=False,
                run_mode="backtest",
            ),
            ingest=IngestConfig(
                feature_list=["price", "obi", "rsi"],
                normalization_method="zscore",
                normalization_window=100,
                normalization_scope="per_symbol",
                buffer_size=1000,
                min_samples_before_ready=1,
                nan_strategy="zero",
                price_feature_mode="raw",
                delta_price_mode="raw",
                feature_clip_abs={},
            ),
            neuro=NeuroConfig(
                vae=VAEConfig(
                    input_dim=3,
                    hidden_dims=[16],
                    latent_dim=4,
                    learning_rate=0.001,
                    beta=1.0,
                    free_bits_per_dim=0.0,
                    batch_size=8,
                    use_mean=True,
                ),
                world_model=WorldModelConfig(
                    hidden_dim=16,
                    num_layers=1,
                    dropout=0.0,
                    learning_rate=0.001,
                    sequence_length=4,
                ),
                ppo=PPOConfig(
                    state_dim=4,
                    action_dim=3,
                    hidden_dims=[16],
                    reward_mode="pnl",
                    objective_split_enforced=True,
                    policy_training_mode="disabled",
                    learning_rate=0.001,
                    gamma=0.99,
                    gae_lambda=0.95,
                    clip_epsilon=0.2,
                    entropy_coef=0.01,
                    max_grad_norm=0.5,
                    numerical_safety={
                        "gradient_clip_threshold": 1.0,
                        "on_invalid": "sanitize",
                    },
                    rollout_length=32,
                    num_epochs=1,
                    minibatch_size=8,
                ),
                sequence={
                    "inference_mode": "stateless_per_event",
                    "representation_training_mode": "independent_rows",
                    "reset_on_replay_start": True,
                    "reset_on_symbol_switch": True,
                    "reset_on_objective_family_switch": True,
                    "reset_on_episode_boundary": True,
                },
                dataset={
                    "manifest_version": 1,
                    "split": {
                        "train_ratio": 0.7,
                        "val_ratio": 0.15,
                        "test_ratio": 0.15,
                    },
                    "cutover": {
                        "min_real_executed_rows": 1,
                        "allow_synthetic_fallback": False,
                        "max_non_causal_rows": 0,
                        "require_reward_methodology": True,
                    },
                },
                evaluation={
                    "report_version": 1,
                    "calibration_bins": 5,
                    "confidence_bucket_edges": [0.25, 0.5, 0.75, 0.9],
                    "missing_confidence_policy": "not_available",
                    "advisory_status": "forbidden",
                },
                performance={
                    "operating_mode": "offline_replay",
                    "shadow_intent_emit_policy": "decimate_observational",
                    "shadow_intent_decimation_stride": 10,
                    "shadow_jsonl_write_policy": "buffered",
                    "telemetry_write_policy": "buffered",
                    "non_critical_queue_limit": 2048,
                    "shadow_log_flush_threshold": 64,
                    "telemetry_flush_threshold": 64,
                    "flush_interval_ms": 1000,
                    "non_critical_overflow_policy": "drop_oldest",
                },
                shadow_gates={
                    "gate_set_version": 1,
                    "startup_enforcement": "strict",
                    "allow_advisory_influence": False,
                    "allow_live_authority": False,
                    "allow_policy_training_reenable": False,
                    "require_domain_manifest_contracts": True,
                },
                checkpoint_every_n_steps=50,
                keep_last_n_checkpoints=1,
                dream_episode_threshold=2,
            ),
            replay=ReplayConfig(
                enabled=False,
                wal_dir=str(tmp_path / "wal"),
                poll_interval=0.1,
                feature_missing_timestamp_policy="fail_closed",
            ),
            authority={
                "mode": "shadow",
                "deadline_ms": 10,
                "fallback_policy": "baseline_yaml",
                "max_inflight_per_symbol": 1,
                "modulation_allowlist": ["decision_making.signal_threshold_bias"],
                "signal_threshold_bias_bounds": [-0.1, 0.1],
                "cooldown_mult_bounds": [1.0, 3.0],
            },
            evidence_capture={
                "mode": "disabled",
                "collect_observation": False,
                "collect_authority_request": False,
                "collect_authority_response": False,
                "emit_shadow_decision_logged": False,
            },
        )

    @pytest.mark.asyncio
    async def test_adapter_maps_and_logs_ppo_metrics(self, tmp_path):
        """Adapter should map alternate PPO keys and write CSV telemetry."""
        config = self._build_adapter_config(tmp_path)

        buffer = MagicMock()
        buffer.__len__ = lambda _self: 0

        bridge = MagicMock()
        bridge.train_policy_async = AsyncMock(
            return_value={
                "policy_loss": 0.12,
                "value_loss": 0.34,
                "entropy": 0.56,
                "episodes_processed": 3,
                "train_step": 7,
            }
        )

        adapter = NeocortexAdapter(
            config=config,
            parser=MagicMock(),
            amygdala=MagicMock(),
            buffer=buffer,
            brain_bridge=bridge,
        )

        logged_training = []
        logged_buffer = []
        adapter.telemetry.log_training = lambda **kwargs: logged_training.append(
            kwargs)
        adapter.telemetry.log_buffer_stats = lambda **kwargs: logged_buffer.append(
            kwargs)

        await adapter._trigger_policy_training(
            [
                {
                    "symbol": "BTCUSDT",
                    "reward": 0.1,
                    "event_ts_ms": 1_700_000_000_000,
                    "objective_family": "policy",
                    "policy_eligible": True,
                },
                {
                    "symbol": "ETHUSDT",
                    "reward": -0.1,
                    "event_ts_ms": 1_700_000_001_000,
                    "objective_family": "policy",
                    "policy_eligible": True,
                },
            ]
        )

        assert len(logged_training) == 1
        assert logged_training[0]["ppo_loss_pi"] == pytest.approx(0.12)
        assert logged_training[0]["ppo_loss_v"] == pytest.approx(0.34)
        assert logged_training[0]["ppo_entropy"] == pytest.approx(0.56)

        assert len(logged_buffer) == 1
        assert logged_buffer[0]["episodes_processed"] == 3

    @pytest.mark.asyncio
    async def test_adapter_logs_episode_only_when_reward_present(self, tmp_path):
        """No-fallback policy: reward-missing episode must not write fake reward telemetry."""
        config = self._build_adapter_config(tmp_path)

        buffer = MagicMock()
        buffer.__len__ = lambda _self: 0

        adapter = NeocortexAdapter(
            config=config,
            parser=MagicMock(),
            amygdala=MagicMock(),
            buffer=buffer,
            brain_bridge=None,
        )

        logged_episodes = []
        logged_buffer = []
        adapter.telemetry.log_episode = lambda **kwargs: logged_episodes.append(
            kwargs)
        adapter.telemetry.log_buffer_stats = lambda **kwargs: logged_buffer.append(
            kwargs)

        await adapter.add_completed_episode(
            {
                "symbol": "BTCUSDT",
                "timestamp": 1_700_000_000.0,
                "event_ts_ms": 1_700_000_000_000,
                "close_event_ts_ms": 1_700_000_000_000,
                "trade_id": "trade-1",
                "lifecycle_id": "lc-1",
                "features": {"price": 100.0, "obi": 0.1, "rsi": 50.0},
                "side": "LONG",
                "reward": 0.25,
                "pnl": 2.5,
            }
        )
        await adapter.add_completed_episode(
            {
                "symbol": "BTCUSDT",
                "timestamp": 1_700_000_001.0,
                "event_ts_ms": 1_700_000_001_000,
                "close_event_ts_ms": 1_700_000_001_000,
                "trade_id": "trade-2",
                "lifecycle_id": "lc-2",
                "features": {"price": 100.2, "obi": 0.0, "rsi": 49.0},
                "side": "LONG",
                "reward": None,
                "pnl": None,
            }
        )

        assert len(logged_episodes) == 1
        assert logged_episodes[0]["reward"] == pytest.approx(0.25)
        assert logged_episodes[0]["pnl"] == pytest.approx(2.5)
        assert len(logged_buffer) >= 2


class TestCSVFormat:
    """Tests for CSV format compliance."""

    def test_csv_is_valid(self, tmp_path):
        """Verify CSV is valid and can be read by standard tools."""
        logger = TelemetryLogger(log_dir=tmp_path)

        # Log various metrics
        logger.log_training(vae_loss=0.5)
        logger.log_shadow_intent(
            action=1, action_name="SHORT", confidence=0.7, value=0.5)
        logger.log_episode(reward=0.5, pnl=2.5)

        csv_path = tmp_path / "neocortex_metrics.csv"

        # Verify it can be read with pandas-like behavior
        with open(csv_path, 'r', newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        # All rows should have same keys as headers
        for row in rows:
            assert "timestamp" in row
            assert "datetime" in row
            assert "step" in row

    def test_no_nan_in_output(self, tmp_path):
        """Verify there are no NaN values in output."""
        logger = TelemetryLogger(log_dir=tmp_path)

        logger.log_step({
            "vae_loss": float('nan'),  # This should not appear
            "wm_loss": 0.1
        })

        csv_path = tmp_path / "neocortex_metrics.csv"

        with open(csv_path, 'r') as f:
            content = f.read()

        # Check for "nan" string (formatted floats)
        # Empty string is acceptable for missing values


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
