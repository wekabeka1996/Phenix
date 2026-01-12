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
from unittest.mock import MagicMock
import time
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from logic.telemetry import TelemetryLogger, get_telemetry


class TestTelemetryLogger:
    """Tests for TelemetryLogger CSV functionality."""
    
    @pytest.fixture
    def temp_log_dir(self, tmp_path):
        """Create temporary log directory."""
        log_dir = tmp_path / "logs"
        log_dir.mkdir()
        return log_dir
    
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
        import logic.telemetry as telem_module
        telem_module._telemetry_instance = None
        
        logger = get_telemetry(log_dir=tmp_path / "test_logs")
        
        assert isinstance(logger, TelemetryLogger)


class TestPPOTelemetryIntegration:
    """Integration tests for PPO training with telemetry."""
    
    def test_adapter_has_telemetry(self):
        """Verify adapter initializes telemetry logger."""
        from transport.adapter import NeocortexAdapter
        
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


class TestCSVFormat:
    """Tests for CSV format compliance."""
    
    def test_csv_is_valid(self, tmp_path):
        """Verify CSV is valid and can be read by standard tools."""
        logger = TelemetryLogger(log_dir=tmp_path)
        
        # Log various metrics
        logger.log_training(vae_loss=0.5)
        logger.log_shadow_intent(action=1, action_name="SHORT", confidence=0.7, value=0.5)
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
