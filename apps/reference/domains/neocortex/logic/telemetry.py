"""
Telemetry Logger for Neocortex

Centralized metrics logging to CSV for system health visualization.

Logs:
- Training losses (VAE, WM, PPO)
- Buffer/Episode statistics
- Shadow intent distribution
- PnL and rewards

Output: logs/neocortex_metrics.csv (can be opened in Excel/Pandas)
"""

import csv
import time
import logging
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from collections import deque

logger = logging.getLogger(__name__)


class TelemetryLogger:
    """
    Centralized metrics logger for Neocortex system health.

    Writes metrics to CSV file for easy analysis in Excel/Pandas.
    Thread-safe and flushes immediately for real-time visibility.
    """

    # CSV Column definitions
    COLUMNS = [
        "timestamp",
        "datetime",
        "step",
        # Training losses
        "vae_loss",
        "vae_mse",
        "vae_kld",
        "wm_loss",
        "ppo_loss_pi",
        "ppo_loss_v",
        "ppo_entropy",
        # Buffer/Memory stats
        "buffer_size",
        "episodes_collected",
        "episodes_processed",
        # Shadow intent stats
        "shadow_action",
        "shadow_action_name",
        "shadow_confidence",
        "shadow_value",
        # Regime Oracle stats
        "predicted_regime",
        "realized_regime",
        "oracle_reward",
        "oracle_correct",
        # PnL/Reward
        "last_reward",
        "last_pnl",
        "cumulative_reward",
        # Graph stats
        "graph_nodes",
        "graph_edges",
        # System stats
        "samples_since_train",
        "total_train_steps"
    ]

    def __init__(
        self,
        log_dir: Path = None,
        filename: str = "neocortex_metrics.csv",
        max_memory_buffer: int = 1000,
        max_file_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 5,
    ):
        """
        Initialize the telemetry logger.

        Args:
            log_dir: Directory for CSV file (default: ./logs)
            filename: CSV filename
            max_memory_buffer: Max rows to keep in memory for rolling stats
        """
        self.log_dir = Path(log_dir) if log_dir else Path("logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.filepath = self.log_dir / filename
        self._max_file_bytes = int(max_file_bytes)
        self._backup_count = int(backup_count)
        self._lock = threading.Lock()
        self._step = 0
        self._cumulative_reward = 0.0

        # Memory buffer for rolling statistics
        self._memory_buffer: deque = deque(maxlen=max_memory_buffer)

        # Initialize CSV file with headers if new
        self._init_csv()

        logger.info(f"TelemetryLogger initialized: {self.filepath}")

    def _init_csv(self):
        """Initialize CSV file with headers if it doesn't exist."""
        if not self.filepath.exists():
            with self._lock:
                with open(self.filepath, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=self.COLUMNS)
                    writer.writeheader()
                logger.info(f"Created new metrics CSV: {self.filepath}")

    def _rotate_if_needed(self) -> None:
        try:
            if not self.filepath.exists():
                return
            if self.filepath.stat().st_size < self._max_file_bytes:
                return

            for idx in range(self._backup_count - 1, 0, -1):
                src = Path(f"{self.filepath}.{idx}")
                dst = Path(f"{self.filepath}.{idx + 1}")
                if src.exists():
                    src.replace(dst)

            self.filepath.replace(Path(f"{self.filepath}.1"))

            with open(self.filepath, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.COLUMNS)
                writer.writeheader()
            logger.info("Telemetry CSV rotated: %s", self.filepath)
        except Exception as e:
            logger.warning("Failed to rotate telemetry CSV: %s",
                           e, exc_info=True)

    def log_step(self, metrics: Dict[str, Any]):
        """
        Log a single step of metrics to CSV.

        Args:
            metrics: Dict of metric values (missing keys will be empty)
        """
        self._step += 1

        # Build row with all columns
        row = {col: "" for col in self.COLUMNS}

        # Timestamps
        now = time.time()
        row["timestamp"] = f"{now:.3f}"
        row["datetime"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        row["step"] = self._step

        # Copy provided metrics
        for key, value in metrics.items():
            if key in self.COLUMNS:
                if value is not None:
                    row[key] = self._format_value(value)

        # Update cumulative reward
        if "last_reward" in metrics and metrics["last_reward"]:
            try:
                self._cumulative_reward += float(metrics["last_reward"])
            except (ValueError, TypeError):
                pass
        row["cumulative_reward"] = f"{self._cumulative_reward:.4f}"

        # Write to CSV
        with self._lock:
            self._rotate_if_needed()
            with open(self.filepath, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=self.COLUMNS)
                writer.writerow(row)
                f.flush()  # Immediate flush for real-time visibility

        # Store in memory buffer
        self._memory_buffer.append(row)

    def _format_value(self, value: Any) -> str:
        """Format value for CSV output."""
        if isinstance(value, float):
            return f"{value:.6f}"
        elif isinstance(value, int):
            return str(value)
        elif isinstance(value, str):
            return value
        elif value is None:
            return ""
        else:
            return str(value)

    def log_training(
        self,
        vae_loss: float = None,
        vae_mse: float = None,
        vae_kld: float = None,
        wm_loss: float = None,
        ppo_loss_pi: float = None,
        ppo_loss_v: float = None,
        ppo_entropy: float = None,
        train_step: int = None
    ):
        """
        Log training metrics.

        Convenience method for logging training losses.
        """
        metrics = {
            "vae_loss": vae_loss,
            "vae_mse": vae_mse,
            "vae_kld": vae_kld,
            "wm_loss": wm_loss,
            "ppo_loss_pi": ppo_loss_pi,
            "ppo_loss_v": ppo_loss_v,
            "ppo_entropy": ppo_entropy,
            "total_train_steps": train_step
        }
        self.log_step({k: v for k, v in metrics.items() if v is not None})

    def log_shadow_intent(
        self,
        action: int,
        action_name: str,
        confidence: float,
        value: float
    ):
        """
        Log shadow intent emission.

        Args:
            action: Action index (0=LONG, 1=SHORT, 2=FLAT)
            action_name: Human-readable action
            confidence: Log probability / confidence
            value: Value estimate
        """
        self.log_step({
            "shadow_action": action,
            "shadow_action_name": action_name,
            "shadow_confidence": confidence,
            "shadow_value": value
        })

    def log_oracle_prediction(
        self,
        predicted_regime: int,
        realized_regime: int,
        oracle_reward: float,
        oracle_correct: bool,
    ):
        """
        Log a settled Regime Oracle prediction.

        Args:
            predicted_regime: PPO action index (0-4) that was predicted H bars ago.
            realized_regime: Ground-truth regime index from RegimeLabeler.
            oracle_reward: Reward assigned to this prediction.
            oracle_correct: Whether predicted == realized.
        """
        self.log_step({
            "predicted_regime": predicted_regime,
            "realized_regime": realized_regime,
            "oracle_reward": oracle_reward,
            "oracle_correct": int(oracle_correct),
            "last_reward": oracle_reward,
        })

    def log_episode(
        self,
        reward: float,
        pnl: float = None,
        symbol: str = None
    ):
        """
        Log completed episode with reward.

        Args:
            reward: Normalized reward
            pnl: Raw PnL value
            symbol: Trading symbol
        """
        self.log_step({
            "last_reward": reward,
            "last_pnl": pnl
        })

    def log_buffer_stats(
        self,
        buffer_size: int,
        episodes_collected: int = None,
        episodes_processed: int = None,
        samples_since_train: int = None
    ):
        """
        Log buffer/memory statistics.
        """
        self.log_step({
            "buffer_size": buffer_size,
            "episodes_collected": episodes_collected,
            "episodes_processed": episodes_processed,
            "samples_since_train": samples_since_train
        })

    def log_graph_stats(
        self,
        nodes: int,
        edges: int
    ):
        """
        Log CausalGraph statistics.
        """
        self.log_step({
            "graph_nodes": nodes,
            "graph_edges": edges
        })

    def get_recent_stats(self, n: int = 100) -> Dict[str, Any]:
        """
        Get statistics from recent entries.

        Args:
            n: Number of recent entries to analyze

        Returns:
            Dict with aggregated statistics
        """
        if not self._memory_buffer:
            return {}

        recent = list(self._memory_buffer)[-n:]

        # Calculate averages for numeric columns
        stats = {}

        numeric_cols = [
            "vae_loss", "wm_loss", "ppo_loss_pi", "ppo_loss_v",
            "ppo_entropy", "last_reward", "shadow_confidence"
        ]

        for col in numeric_cols:
            values = []
            for row in recent:
                try:
                    if row.get(col):
                        values.append(float(row[col]))
                except (ValueError, TypeError):
                    pass

            if values:
                stats[f"{col}_mean"] = sum(values) / len(values)
                stats[f"{col}_min"] = min(values)
                stats[f"{col}_max"] = max(values)

        # Action distribution
        action_counts = {"LONG": 0, "SHORT": 0, "FLAT": 0}
        for row in recent:
            action = row.get("shadow_action_name")
            if action in action_counts:
                action_counts[action] += 1

        total_actions = sum(action_counts.values())
        if total_actions > 0:
            stats["action_dist_long"] = action_counts["LONG"] / total_actions
            stats["action_dist_short"] = action_counts["SHORT"] / total_actions
            stats["action_dist_flat"] = action_counts["FLAT"] / total_actions

        stats["total_entries"] = len(self._memory_buffer)
        stats["cumulative_reward"] = self._cumulative_reward

        return stats

    def get_health_report(self) -> str:
        """
        Generate a human-readable health report.

        Returns:
            Formatted string with system health summary
        """
        stats = self.get_recent_stats()

        if not stats:
            return "No telemetry data available yet."

        report = [
            "=== NEOCORTEX HEALTH REPORT ===",
            f"Total entries: {stats.get('total_entries', 0)}",
            f"Cumulative reward: {stats.get('cumulative_reward', 0):.4f}",
            "",
            "--- Training Losses (avg) ---",
            f"  VAE: {stats.get('vae_loss_mean', 'N/A')}",
            f"  WM: {stats.get('wm_loss_mean', 'N/A')}",
            f"  PPO Policy: {stats.get('ppo_loss_pi_mean', 'N/A')}",
            f"  PPO Value: {stats.get('ppo_loss_v_mean', 'N/A')}",
            "",
            "--- Action Distribution ---",
            f"  LONG: {stats.get('action_dist_long', 0)*100:.1f}%",
            f"  SHORT: {stats.get('action_dist_short', 0)*100:.1f}%",
            f"  FLAT: {stats.get('action_dist_flat', 0)*100:.1f}%",
            "==============================="
        ]

        return "\n".join(report)

    @property
    def filepath_str(self) -> str:
        """Get filepath as string."""
        return str(self.filepath)

    @property
    def step_count(self) -> int:
        """Get total logged steps."""
        return self._step


# Singleton instance for global access
_telemetry_instance: Optional[TelemetryLogger] = None


def get_telemetry(log_dir: Path = None) -> TelemetryLogger:
    """
    Get or create the global telemetry logger instance.

    Args:
        log_dir: Log directory (only used on first call)

    Returns:
        TelemetryLogger singleton
    """
    global _telemetry_instance

    if _telemetry_instance is None:
        _telemetry_instance = TelemetryLogger(log_dir=log_dir)

    return _telemetry_instance
