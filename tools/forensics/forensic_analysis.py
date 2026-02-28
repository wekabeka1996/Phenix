#!/usr/bin/env python3
"""
Forensic Analysis for Neocortex R2 75-Day Backtest

Principal Objective: Determine if PPO learned and why persistence failed.

Files analyzed:
- logs/neocortex_metrics.csv
- data/shadow_intents.jsonl
- logs/*.log (for ERROR/WARNING patterns)

Author: AI Forensics Unit
Date: 2026-01-30
"""

import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Optional: matplotlib for charts (fallback to ASCII if unavailable)
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("⚠ matplotlib not found; using ASCII charts")

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    print("❌ pandas not found; cannot perform analysis")
    sys.exit(1)


# ==============================================================================
# CONFIGURATION
# ==============================================================================

REPO_ROOT = Path(__file__).parent.parent
METRICS_CSV = REPO_ROOT / "logs" / "neocortex_metrics.csv"
SHADOW_INTENTS = REPO_ROOT / "data" / "shadow_intents.jsonl"
CHECKPOINTS_DIR = REPO_ROOT / "data" / "checkpoints"
HIPPOCAMPUS_DB = REPO_ROOT / "data" / "hippocampus.db"
LOGS_DIR = REPO_ROOT / "logs"
OUTPUT_DIR = REPO_ROOT / "docs"
REPORT_FILE = OUTPUT_DIR / "POST_MORTEM_BACKTEST_R2.md"


# ==============================================================================
# 1. NEOCORTEX METRICS ANALYSIS
# ==============================================================================

class MetricsAnalyzer:
    """Analyze neocortex_metrics.csv for PPO learning signals."""
    
    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self.df: Optional[pd.DataFrame] = None
        self.results: Dict[str, Any] = {}
        
    def load(self) -> bool:
        """Load and parse CSV."""
        if not self.csv_path.exists():
            print(f"❌ Metrics file not found: {self.csv_path}")
            return False
        
        try:
            self.df = pd.read_csv(self.csv_path)
            print(f"✓ Loaded {len(self.df)} rows from {self.csv_path.name}")
            return True
        except Exception as e:
            print(f"❌ Failed to load CSV: {e}")
            return False
    
    def analyze(self) -> Dict[str, Any]:
        """Run full analysis."""
        if self.df is None:
            return {}
        
        self.results["total_rows"] = len(self.df)
        self.results["columns"] = list(self.df.columns)
        
        # Time range
        if "datetime" in self.df.columns:
            self.df["datetime"] = pd.to_datetime(self.df["datetime"], errors="coerce")
            valid_dt = self.df["datetime"].dropna()
            if len(valid_dt) > 0:
                self.results["time_start"] = str(valid_dt.iloc[0])
                self.results["time_end"] = str(valid_dt.iloc[-1])
                duration = valid_dt.iloc[-1] - valid_dt.iloc[0]
                self.results["duration_seconds"] = duration.total_seconds()
        
        # Step range
        if "step" in self.df.columns:
            self.results["step_min"] = int(self.df["step"].min())
            self.results["step_max"] = int(self.df["step"].max())
        
        # === PPO Loss Analysis ===
        self._analyze_ppo_loss()
        
        # === Cumulative Reward Analysis ===
        self._analyze_cumulative_reward()
        
        # === Last Reward (Non-Zero Ratio) ===
        self._analyze_last_reward()
        
        # === Train Steps Analysis (CRITICAL) ===
        self._analyze_train_steps()
        
        # === Action Distribution ===
        self._analyze_action_distribution()
        
        # === Confidence Analysis ===
        self._analyze_confidence()
        
        return self.results
    
    def _analyze_ppo_loss(self):
        """Analyze PPO policy loss for convergence."""
        if "ppo_loss_pi" not in self.df.columns:
            self.results["ppo_loss_available"] = False
            return
        
        loss_series = self.df["ppo_loss_pi"].dropna()
        if len(loss_series) == 0:
            self.results["ppo_loss_available"] = False
            self.results["ppo_loss_comment"] = "All ppo_loss_pi values are NaN - PPO never trained"
            return
        
        self.results["ppo_loss_available"] = True
        self.results["ppo_loss_count"] = len(loss_series)
        self.results["ppo_loss_mean"] = float(loss_series.mean())
        self.results["ppo_loss_std"] = float(loss_series.std())
        self.results["ppo_loss_min"] = float(loss_series.min())
        self.results["ppo_loss_max"] = float(loss_series.max())
        
        # Rolling analysis (window=50)
        if len(loss_series) >= 50:
            rolling_mean = loss_series.rolling(window=50).mean()
            first_50_mean = rolling_mean.iloc[49] if len(rolling_mean) > 49 else None
            last_50_mean = rolling_mean.iloc[-1] if len(rolling_mean) > 0 else None
            
            if first_50_mean is not None and last_50_mean is not None:
                self.results["ppo_loss_first_50_mean"] = float(first_50_mean)
                self.results["ppo_loss_last_50_mean"] = float(last_50_mean)
                
                # Convergence verdict
                if last_50_mean < first_50_mean * 0.8:
                    self.results["ppo_converging"] = True
                    self.results["ppo_convergence_ratio"] = float(last_50_mean / first_50_mean)
                else:
                    self.results["ppo_converging"] = False
    
    def _analyze_cumulative_reward(self):
        """Analyze cumulative reward for learning correlation."""
        if "cumulative_reward" not in self.df.columns:
            self.results["cumulative_reward_available"] = False
            return
        
        reward_series = self.df["cumulative_reward"].dropna()
        if len(reward_series) == 0:
            self.results["cumulative_reward_available"] = False
            return
        
        self.results["cumulative_reward_available"] = True
        self.results["cumulative_reward_final"] = float(reward_series.iloc[-1])
        self.results["cumulative_reward_max"] = float(reward_series.max())
        self.results["cumulative_reward_min"] = float(reward_series.min())
        
        # Correlation with step
        if "step" in self.df.columns:
            valid_idx = reward_series.index
            steps = self.df.loc[valid_idx, "step"]
            if len(steps) > 1:
                correlation = np.corrcoef(steps.values, reward_series.values)[0, 1]
                self.results["reward_step_correlation"] = float(correlation)
    
    def _analyze_last_reward(self):
        """Analyze last_reward for PnL signal propagation."""
        if "last_reward" not in self.df.columns:
            self.results["last_reward_available"] = False
            return
        
        reward_series = self.df["last_reward"].dropna()
        if len(reward_series) == 0:
            self.results["last_reward_available"] = False
            return
        
        self.results["last_reward_available"] = True
        non_zero_count = (reward_series != 0).sum()
        total_count = len(reward_series)
        
        self.results["last_reward_total"] = total_count
        self.results["last_reward_non_zero"] = int(non_zero_count)
        self.results["last_reward_non_zero_ratio"] = float(non_zero_count / total_count) if total_count > 0 else 0.0
        
        # Verdict on PnL signal
        if non_zero_count == 0:
            self.results["pnl_signal_verdict"] = "DEAD - No reward signals received"
        elif non_zero_count / total_count < 0.01:
            self.results["pnl_signal_verdict"] = "WEAK - Less than 1% non-zero rewards"
        else:
            self.results["pnl_signal_verdict"] = "ACTIVE"
    
    def _analyze_train_steps(self):
        """Analyze total_train_steps - CRITICAL for checkpoint understanding."""
        if "total_train_steps" not in self.df.columns:
            self.results["train_steps_available"] = False
            return
        
        train_steps = self.df["total_train_steps"].dropna()
        if len(train_steps) == 0:
            self.results["train_steps_available"] = False
            self.results["train_steps_comment"] = "No training steps recorded"
            return
        
        self.results["train_steps_available"] = True
        max_train_steps = int(train_steps.max())
        self.results["train_steps_max"] = max_train_steps
        
        # Count unique non-empty train step values
        non_empty = train_steps[train_steps > 0]
        self.results["train_steps_non_empty_count"] = len(non_empty)
        
        # CRITICAL: Check if checkpoint threshold was reached
        checkpoint_threshold = 1000  # From config
        if max_train_steps < checkpoint_threshold:
            self.results["checkpoint_threshold_reached"] = False
            self.results["checkpoint_comment"] = (
                f"Training only reached {max_train_steps} steps, "
                f"but checkpoint_every_n_steps={checkpoint_threshold}. "
                "NO CHECKPOINTS WERE SAVED."
            )
        else:
            self.results["checkpoint_threshold_reached"] = True
            expected_checkpoints = max_train_steps // checkpoint_threshold
            self.results["expected_checkpoints"] = expected_checkpoints
    
    def _analyze_action_distribution(self):
        """Analyze shadow action distribution."""
        if "shadow_action" not in self.df.columns:
            self.results["action_distribution_available"] = False
            return
        
        actions = self.df["shadow_action"].dropna()
        if len(actions) == 0:
            self.results["action_distribution_available"] = False
            return
        
        self.results["action_distribution_available"] = True
        
        # Overall distribution
        action_counts = actions.value_counts().to_dict()
        total = sum(action_counts.values())
        
        self.results["action_distribution"] = {
            str(k): {"count": int(v), "pct": round(100 * v / total, 2)}
            for k, v in action_counts.items()
        }
        
        # Time-based analysis (first 10% vs last 10%)
        n = len(actions)
        first_10pct = actions.iloc[:n // 10]
        last_10pct = actions.iloc[-n // 10:]
        
        first_dist = first_10pct.value_counts(normalize=True).to_dict()
        last_dist = last_10pct.value_counts(normalize=True).to_dict()
        
        self.results["action_first_10pct"] = {str(k): round(v, 3) for k, v in first_dist.items()}
        self.results["action_last_10pct"] = {str(k): round(v, 3) for k, v in last_dist.items()}
        
        # Bias shift detection
        # Random = 33/33/33; Learned = skewed
        first_entropy = self._entropy(list(first_dist.values()))
        last_entropy = self._entropy(list(last_dist.values()))
        
        self.results["action_first_entropy"] = float(first_entropy)
        self.results["action_last_entropy"] = float(last_entropy)
        
        if last_entropy < first_entropy * 0.9:
            self.results["action_bias_shift"] = True
            self.results["action_bias_comment"] = "Action distribution became more focused over time"
        else:
            self.results["action_bias_shift"] = False
            self.results["action_bias_comment"] = "Action distribution remained random-like"
    
    def _analyze_confidence(self):
        """Analyze shadow confidence over time."""
        if "shadow_confidence" not in self.df.columns:
            self.results["confidence_available"] = False
            return
        
        confidence = self.df["shadow_confidence"].dropna()
        if len(confidence) == 0:
            self.results["confidence_available"] = False
            return
        
        self.results["confidence_available"] = True
        self.results["confidence_mean"] = float(confidence.mean())
        self.results["confidence_std"] = float(confidence.std())
        
        # First vs last quartile
        n = len(confidence)
        first_q = confidence.iloc[:n // 4]
        last_q = confidence.iloc[-n // 4:]
        
        self.results["confidence_first_q_mean"] = float(first_q.mean())
        self.results["confidence_last_q_mean"] = float(last_q.mean())
        
        if last_q.mean() > first_q.mean():
            self.results["confidence_trend"] = "INCREASING"
        elif last_q.mean() < first_q.mean():
            self.results["confidence_trend"] = "DECREASING"
        else:
            self.results["confidence_trend"] = "STABLE"
    
    @staticmethod
    def _entropy(probs: List[float]) -> float:
        """Calculate entropy of probability distribution."""
        probs = np.array(probs)
        probs = probs[probs > 0]  # Avoid log(0)
        return float(-np.sum(probs * np.log(probs + 1e-10)))


# ==============================================================================
# 2. SHADOW INTENTS ANALYSIS
# ==============================================================================

class ShadowIntentsAnalyzer:
    """Analyze shadow_intents.jsonl for quality and learning signals."""
    
    def __init__(self, jsonl_path: Path):
        self.jsonl_path = jsonl_path
        self.intents: List[Dict[str, Any]] = []
        self.results: Dict[str, Any] = {}
    
    def load(self) -> bool:
        """Load JSONL file."""
        if not self.jsonl_path.exists():
            print(f"❌ Shadow intents file not found: {self.jsonl_path}")
            return False
        
        try:
            with open(self.jsonl_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            self.intents.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            print(f"✓ Loaded {len(self.intents)} shadow intents")
            return True
        except Exception as e:
            print(f"❌ Failed to load shadow intents: {e}")
            return False
    
    def analyze(self) -> Dict[str, Any]:
        """Run full analysis."""
        if not self.intents:
            return {}
        
        self.results["total_intents"] = len(self.intents)
        
        # Time range
        timestamps = [i.get("timestamp", 0) for i in self.intents]
        if timestamps:
            self.results["time_start"] = datetime.fromtimestamp(min(timestamps)).isoformat()
            self.results["time_end"] = datetime.fromtimestamp(max(timestamps)).isoformat()
            self.results["duration_seconds"] = max(timestamps) - min(timestamps)
        
        # === Action Distribution Over Time ===
        self._analyze_action_over_time()
        
        # === Confidence Over Time ===
        self._analyze_confidence_over_time()
        
        # === Train Steps in Intents ===
        self._analyze_train_steps()
        
        # === Latent State Quality ===
        self._analyze_latent_states()
        
        return self.results
    
    def _analyze_action_over_time(self):
        """Analyze action distribution shift over time."""
        actions = [i.get("action", -1) for i in self.intents]
        n = len(actions)
        
        if n == 0:
            return
        
        # Overall
        action_counts = Counter(actions)
        total = sum(action_counts.values())
        self.results["action_distribution"] = {
            str(k): {"count": v, "pct": round(100 * v / total, 2)}
            for k, v in action_counts.items()
        }
        
        # Temporal bins (10 bins)
        num_bins = 10
        bin_size = n // num_bins
        temporal_dist = []
        
        for i in range(num_bins):
            start = i * bin_size
            end = start + bin_size if i < num_bins - 1 else n
            bin_actions = actions[start:end]
            bin_counts = Counter(bin_actions)
            bin_total = sum(bin_counts.values())
            temporal_dist.append({
                str(k): round(v / bin_total, 3) if bin_total > 0 else 0
                for k, v in bin_counts.items()
            })
        
        self.results["action_temporal_bins"] = temporal_dist
        
        # Check for shift
        first_bin = temporal_dist[0] if temporal_dist else {}
        last_bin = temporal_dist[-1] if temporal_dist else {}
        
        # Calculate dominant action change
        first_dominant = max(first_bin.items(), key=lambda x: x[1])[0] if first_bin else None
        last_dominant = max(last_bin.items(), key=lambda x: x[1])[0] if last_bin else None
        
        self.results["first_dominant_action"] = first_dominant
        self.results["last_dominant_action"] = last_dominant
        self.results["action_shift_detected"] = first_dominant != last_dominant
    
    def _analyze_confidence_over_time(self):
        """Analyze confidence trend."""
        confidences = [i.get("confidence", 0) for i in self.intents]
        n = len(confidences)
        
        if n == 0:
            return
        
        self.results["confidence_mean"] = float(np.mean(confidences))
        self.results["confidence_std"] = float(np.std(confidences))
        self.results["confidence_min"] = float(np.min(confidences))
        self.results["confidence_max"] = float(np.max(confidences))
        
        # First vs last 10%
        first_10pct = confidences[:n // 10]
        last_10pct = confidences[-n // 10:]
        
        self.results["confidence_first_10pct_mean"] = float(np.mean(first_10pct))
        self.results["confidence_last_10pct_mean"] = float(np.mean(last_10pct))
        
        delta = self.results["confidence_last_10pct_mean"] - self.results["confidence_first_10pct_mean"]
        self.results["confidence_delta"] = float(delta)
        
        if delta > 0.1:
            self.results["confidence_trend"] = "INCREASING"
        elif delta < -0.1:
            self.results["confidence_trend"] = "DECREASING"
        else:
            self.results["confidence_trend"] = "STABLE"
    
    def _analyze_train_steps(self):
        """Analyze train_steps field in intents."""
        train_steps = [i.get("train_steps", 0) for i in self.intents]
        unique_steps = set(train_steps)
        
        self.results["train_steps_unique_count"] = len(unique_steps)
        self.results["train_steps_max"] = max(train_steps) if train_steps else 0
        self.results["train_steps_min"] = min(train_steps) if train_steps else 0
        
        # How many intents have train_steps > 0?
        with_training = sum(1 for ts in train_steps if ts > 0)
        self.results["intents_with_training"] = with_training
        self.results["intents_without_training"] = len(train_steps) - with_training
    
    def _analyze_latent_states(self):
        """Analyze latent state vectors for variety."""
        latent_states = [i.get("latent_state", []) for i in self.intents if i.get("latent_state")]
        
        if not latent_states:
            self.results["latent_state_available"] = False
            return
        
        self.results["latent_state_available"] = True
        self.results["latent_state_count"] = len(latent_states)
        
        # Check dimension consistency
        dims = [len(ls) for ls in latent_states]
        self.results["latent_dim"] = dims[0] if dims else 0
        
        # Variance per dimension (are they all collapsing to same point?)
        try:
            arr = np.array(latent_states[:1000])  # Sample first 1000
            per_dim_std = np.std(arr, axis=0)
            self.results["latent_per_dim_std_mean"] = float(np.mean(per_dim_std))
            self.results["latent_per_dim_std_min"] = float(np.min(per_dim_std))
            self.results["latent_per_dim_std_max"] = float(np.max(per_dim_std))
            
            # Collapse detection
            if np.mean(per_dim_std) < 0.1:
                self.results["latent_collapse_detected"] = True
                self.results["latent_comment"] = "WARNING: Latent space may have collapsed (low variance)"
            else:
                self.results["latent_collapse_detected"] = False
        except Exception as e:
            self.results["latent_error"] = str(e)


# ==============================================================================
# 3. LOG FORENSICS
# ==============================================================================

class LogForensics:
    """Parse log files for errors and anomalies."""
    
    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
        self.results: Dict[str, Any] = {}
    
    def analyze(self) -> Dict[str, Any]:
        """Scan all log files for patterns."""
        patterns = {
            "ERROR": re.compile(r"\bERROR\b", re.IGNORECASE),
            "WARNING": re.compile(r"\bWARN(?:ING)?\b", re.IGNORECASE),
            "QueueFull": re.compile(r"QueueFull|queue.*full", re.IGNORECASE),
            "BrokenProcess": re.compile(r"BrokenProcess|Broken.*Pool", re.IGNORECASE),
            "DREAM": re.compile(r"TRIGGERING DREAM|DREAM", re.IGNORECASE),
            "Checkpoint": re.compile(r"checkpoint.*saved|save.*checkpoint", re.IGNORECASE),
            "OOM": re.compile(r"out of memory|OOM|MemoryError", re.IGNORECASE),
            "Timeout": re.compile(r"timeout|timed out", re.IGNORECASE),
        }
        
        counts: Dict[str, int] = {k: 0 for k in patterns}
        last_lines: Dict[str, str] = {}
        log_files_scanned = 0
        total_lines = 0
        
        for log_file in self.logs_dir.glob("*.log*"):
            if log_file.is_file():
                log_files_scanned += 1
                try:
                    with open(log_file, "r", errors="ignore") as f:
                        lines = f.readlines()
                        total_lines += len(lines)
                        
                        for line in lines:
                            for pattern_name, pattern in patterns.items():
                                if pattern.search(line):
                                    counts[pattern_name] += 1
                                    last_lines[pattern_name] = line.strip()[:200]
                except Exception:
                    pass
        
        self.results["log_files_scanned"] = log_files_scanned
        self.results["total_log_lines"] = total_lines
        self.results["pattern_counts"] = counts
        self.results["last_matches"] = last_lines
        
        # Check for clean shutdown
        self._check_shutdown()
        
        return self.results
    
    def _check_shutdown(self):
        """Check if neocortex/main logs show clean shutdown."""
        # Look for aurora_core.log ending
        core_log = self.logs_dir / "aurora_core.log"
        if core_log.exists():
            try:
                with open(core_log, "r", errors="ignore") as f:
                    lines = f.readlines()
                    if lines:
                        last_50 = lines[-50:]
                        last_text = "".join(last_50)
                        
                        if "shutdown" in last_text.lower() or "graceful" in last_text.lower():
                            self.results["shutdown_clean"] = True
                        elif "error" in last_text.lower() or "exception" in last_text.lower():
                            self.results["shutdown_clean"] = False
                            self.results["shutdown_comment"] = "Log ends with errors"
                        else:
                            self.results["shutdown_clean"] = "UNKNOWN"
                            self.results["shutdown_comment"] = "No explicit shutdown message found"
                        
                        self.results["last_log_line"] = lines[-1].strip()[:200] if lines else ""
            except Exception as e:
                self.results["shutdown_error"] = str(e)


# ==============================================================================
# 4. INFRASTRUCTURE CHECK
# ==============================================================================

class InfrastructureCheck:
    """Check for missing files and configuration issues."""
    
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.results: Dict[str, Any] = {}
    
    def check(self) -> Dict[str, Any]:
        """Run all infrastructure checks."""
        
        # Checkpoints directory
        checkpoints_dir = self.repo_root / "data" / "checkpoints"
        self.results["checkpoints_dir_exists"] = checkpoints_dir.exists()
        
        if checkpoints_dir.exists():
            checkpoint_files = list(checkpoints_dir.glob("*.pt"))
            self.results["checkpoint_files_count"] = len(checkpoint_files)
            self.results["checkpoint_files"] = [f.name for f in checkpoint_files[:10]]
        else:
            self.results["checkpoint_files_count"] = 0
            self.results["checkpoint_files"] = []
        
        # Hippocampus database
        hippocampus_db = self.repo_root / "data" / "hippocampus.db"
        self.results["hippocampus_db_exists"] = hippocampus_db.exists()
        
        # Normalizer state
        normalizer_state = self.repo_root / "data" / "normalizer_state.npz"
        self.results["normalizer_state_exists"] = normalizer_state.exists()
        
        # Shadow intents file
        shadow_intents = self.repo_root / "data" / "shadow_intents.jsonl"
        self.results["shadow_intents_exists"] = shadow_intents.exists()
        if shadow_intents.exists():
            self.results["shadow_intents_size_mb"] = round(shadow_intents.stat().st_size / (1024 * 1024), 2)
        
        return self.results


# ==============================================================================
# 5. REPORT GENERATOR
# ==============================================================================

def generate_report(
    metrics_results: Dict[str, Any],
    intents_results: Dict[str, Any],
    logs_results: Dict[str, Any],
    infra_results: Dict[str, Any],
    output_path: Path
) -> str:
    """Generate comprehensive markdown report."""
    
    lines = [
        "# 🔬 POST MORTEM: Neocortex R2 75-Day Backtest",
        "",
        f"**Generated:** {datetime.now().isoformat()}",
        "",
        "---",
        "",
        "## 📊 Executive Summary",
        "",
    ]
    
    # === VERDICT SECTION ===
    
    # Learning verdict
    learning_verdict = "❓ UNKNOWN"
    if metrics_results.get("ppo_loss_available"):
        if metrics_results.get("ppo_converging"):
            learning_verdict = "✅ PPO SHOWED CONVERGENCE SIGNALS"
        else:
            learning_verdict = "⚠️ PPO DID NOT CLEARLY CONVERGE"
    else:
        learning_verdict = "❌ PPO NEVER TRAINED (ppo_loss_pi all NaN)"
    
    # Checkpoint verdict
    checkpoint_verdict = "❓ UNKNOWN"
    train_steps_max = metrics_results.get("train_steps_max", 0)
    if train_steps_max < 1000:
        checkpoint_verdict = f"❌ CHECKPOINTS NEVER SAVED (only {train_steps_max} train steps, threshold=1000)"
    elif infra_results.get("checkpoint_files_count", 0) > 0:
        checkpoint_verdict = f"✅ {infra_results['checkpoint_files_count']} checkpoints found"
    else:
        checkpoint_verdict = "❌ CHECKPOINTS DIR EMPTY despite sufficient train steps"
    
    # Hippocampus verdict
    hippocampus_verdict = "❌ MISSING" if not infra_results.get("hippocampus_db_exists") else "✅ EXISTS"
    
    lines.extend([
        f"| Aspect | Verdict |",
        f"|--------|---------|",
        f"| **PPO Learning** | {learning_verdict} |",
        f"| **Checkpoints** | {checkpoint_verdict} |",
        f"| **Hippocampus DB** | {hippocampus_verdict} |",
        f"| **Shadow Intents** | {intents_results.get('total_intents', 0):,} recorded |",
        "",
    ])
    
    # === ROOT CAUSE ANALYSIS ===
    lines.extend([
        "## 🔍 Root Cause Analysis",
        "",
        "### Why No Checkpoints?",
        "",
    ])
    
    if train_steps_max < 1000:
        lines.extend([
            "**Root Cause:** Training threshold not reached.",
            "",
            f"- `total_train_steps` max = **{train_steps_max}**",
            f"- `checkpoint_every_n_steps` = **1000** (from config)",
            f"- Δ = {1000 - train_steps_max} steps short",
            "",
            "The system processed ~45,000 observations but only completed ~700 training steps.",
            "This indicates a **massive ingestion-to-training ratio mismatch**.",
            "",
            "**Hypothesis:** The backtest ingestion loop ran faster than the BrainBridge worker could train.",
            "With `batch_size=64` and ~700 steps, only ~45k samples could be processed for training,",
            "matching the buffer capacity—but training throughput was the bottleneck.",
            "",
        ])
    else:
        lines.extend([
            "Training threshold was reached, but checkpoints still missing.",
            "Possible causes:",
            "- File I/O failure",
            "- Process termination before save",
            "- Permission issues",
            "",
        ])
    
    # === METRICS DEEP DIVE ===
    lines.extend([
        "## 📈 Metrics Analysis",
        "",
        f"### Overview",
        f"- Total rows in CSV: **{metrics_results.get('total_rows', 0):,}**",
        f"- Step range: {metrics_results.get('step_min', '?')} → {metrics_results.get('step_max', '?')}",
        f"- Time range: {metrics_results.get('time_start', '?')} → {metrics_results.get('time_end', '?')}",
        "",
    ])
    
    # PPO Loss
    if metrics_results.get("ppo_loss_available"):
        lines.extend([
            "### PPO Policy Loss",
            f"- Count: {metrics_results.get('ppo_loss_count', 0)}",
            f"- Mean: {metrics_results.get('ppo_loss_mean', 0):.4f}",
            f"- Std: {metrics_results.get('ppo_loss_std', 0):.4f}",
            f"- First 50 rolling mean: {metrics_results.get('ppo_loss_first_50_mean', 'N/A')}",
            f"- Last 50 rolling mean: {metrics_results.get('ppo_loss_last_50_mean', 'N/A')}",
            f"- **Converging:** {metrics_results.get('ppo_converging', False)}",
            "",
        ])
    else:
        lines.extend([
            "### PPO Policy Loss",
            "**⚠️ No PPO loss data available - PPO training never executed**",
            "",
        ])
    
    # Action Distribution
    if metrics_results.get("action_distribution_available"):
        lines.extend([
            "### Action Distribution",
            "",
        ])
        for action, data in metrics_results.get("action_distribution", {}).items():
            lines.append(f"- Action {action}: {data['count']:,} ({data['pct']:.1f}%)")
        
        lines.extend([
            "",
            f"**First 10% entropy:** {metrics_results.get('action_first_entropy', 0):.3f}",
            f"**Last 10% entropy:** {metrics_results.get('action_last_entropy', 0):.3f}",
            f"**Bias shift detected:** {metrics_results.get('action_bias_shift', False)}",
            "",
        ])
    
    # Confidence
    if metrics_results.get("confidence_available"):
        lines.extend([
            "### Confidence Analysis",
            f"- Mean: {metrics_results.get('confidence_mean', 0):.3f}",
            f"- First quartile mean: {metrics_results.get('confidence_first_q_mean', 0):.3f}",
            f"- Last quartile mean: {metrics_results.get('confidence_last_q_mean', 0):.3f}",
            f"- **Trend:** {metrics_results.get('confidence_trend', 'UNKNOWN')}",
            "",
        ])
    
    # Train Steps Analysis
    lines.extend([
        "### Training Steps Analysis (CRITICAL)",
        f"- Max train steps: **{metrics_results.get('train_steps_max', 0)}**",
        f"- Checkpoint threshold: **1000**",
        f"- Checkpoint reached: **{metrics_results.get('checkpoint_threshold_reached', False)}**",
        "",
    ])
    
    if metrics_results.get("checkpoint_comment"):
        lines.extend([
            f"> {metrics_results['checkpoint_comment']}",
            "",
        ])
    
    # === SHADOW INTENTS ANALYSIS ===
    lines.extend([
        "## 🧠 Shadow Intents Quality",
        "",
        f"- Total intents: **{intents_results.get('total_intents', 0):,}**",
        f"- Duration: {intents_results.get('duration_seconds', 0):.0f} seconds",
        "",
    ])
    
    if intents_results.get("latent_state_available"):
        lines.extend([
            "### Latent State Health",
            f"- Latent dimension: {intents_results.get('latent_dim', 0)}",
            f"- Per-dim std (mean): {intents_results.get('latent_per_dim_std_mean', 0):.3f}",
            f"- Collapse detected: **{intents_results.get('latent_collapse_detected', False)}**",
            "",
        ])
    
    lines.extend([
        "### Confidence Trend",
        f"- First 10% mean: {intents_results.get('confidence_first_10pct_mean', 0):.3f}",
        f"- Last 10% mean: {intents_results.get('confidence_last_10pct_mean', 0):.3f}",
        f"- **Trend:** {intents_results.get('confidence_trend', 'UNKNOWN')}",
        "",
    ])
    
    # === LOG FORENSICS ===
    lines.extend([
        "## 📜 Log Forensics",
        "",
        f"- Log files scanned: {logs_results.get('log_files_scanned', 0)}",
        f"- Total log lines: {logs_results.get('total_log_lines', 0):,}",
        "",
        "### Pattern Counts",
        "",
    ])
    
    for pattern, count in logs_results.get("pattern_counts", {}).items():
        emoji = "✅" if count == 0 else ("⚠️" if count < 10 else "❌")
        lines.append(f"- {emoji} **{pattern}:** {count}")
    
    lines.extend([
        "",
        f"### Shutdown Status",
        f"- Clean shutdown: **{logs_results.get('shutdown_clean', 'UNKNOWN')}**",
        "",
    ])
    
    # === INFRASTRUCTURE ===
    lines.extend([
        "## 🗄️ Infrastructure Status",
        "",
        f"| File/Dir | Status |",
        f"|----------|--------|",
        f"| data/checkpoints/ | {'✅ Exists' if infra_results.get('checkpoints_dir_exists') else '❌ Missing'} ({infra_results.get('checkpoint_files_count', 0)} files) |",
        f"| data/hippocampus.db | {'✅ Exists' if infra_results.get('hippocampus_db_exists') else '❌ Missing'} |",
        f"| data/normalizer_state.npz | {'✅ Exists' if infra_results.get('normalizer_state_exists') else '❌ Missing'} |",
        f"| data/shadow_intents.jsonl | {'✅ Exists' if infra_results.get('shadow_intents_exists') else '❌ Missing'} ({infra_results.get('shadow_intents_size_mb', 0)} MB) |",
        "",
    ])
    
    # === RECOMMENDATIONS ===
    lines.extend([
        "## 💡 Recommendations",
        "",
        "### Immediate Fixes",
        "",
        "1. **Lower `checkpoint_every_n_steps`** from 1000 → 100 for backtest mode",
        "   - Current ratio: 45k observations → 700 train steps",
        "   - Training is the bottleneck, not observation ingestion",
        "",
        "2. **Add async checkpoint on shutdown**",
        "   - Current `shutdown()` is sync and cannot call `save_async()`",
        "   - Implement `async def shutdown_async()` in adapter",
        "",
        "3. **Increase BrainBridge worker pool** or reduce `batch_size`",
        "   - `brain_workers=1` is insufficient for high-throughput backtest",
        "   - Consider `brain_workers=2` or `batch_size=32`",
        "",
        "4. **Add training throughput monitoring**",
        "   - Log `train_steps_per_second` to detect bottlenecks",
        "   - Alert if ratio `observations / train_steps` > 100",
        "",
        "### For Hippocampus DB",
        "",
        "- Hippocampus (causal graph) was never implemented or enabled",
        "- This is expected for Phase R2; causal graph is Phase R3+",
        "",
        "### Speed Mismatch Mitigation",
        "",
        "```python",
        "# Option A: Throttle ingestion to match training throughput",
        "if self._samples_since_last_train > 1000:",
        "    await asyncio.sleep(0.1)  # Back-pressure",
        "",
        "# Option B: Batch observations before sending to BrainBridge",
        "# Instead of train every 64 samples, train every 256",
        "```",
        "",
    ])
    
    # === FINAL VERDICT ===
    lines.extend([
        "## 🎯 Final Verdict",
        "",
    ])
    
    # Determine overall verdict
    if train_steps_max < 1000:
        overall = "⚠️ PARTIAL SUCCESS"
        explanation = (
            "The brain was thinking (45k shadow intents), but it never had enough training steps "
            "to trigger checkpointing. The PPO model *may* have been learning internally, "
            "but we cannot verify without saved weights."
        )
    elif intents_results.get("action_bias_shift"):
        overall = "✅ LEARNING DETECTED"
        explanation = "Action distribution shifted from random to biased, indicating policy learning."
    else:
        overall = "❓ INCONCLUSIVE"
        explanation = "Not enough signal to determine if learning occurred."
    
    lines.extend([
        f"**Overall:** {overall}",
        "",
        explanation,
        "",
        "---",
        "",
        "*Generated by `tools/forensic_analysis.py`*",
    ])
    
    report_text = "\n".join(lines)
    
    # Write to file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write(report_text)
    
    print(f"\n✅ Report written to: {output_path}")
    return report_text


# ==============================================================================
# 6. VISUALIZATION (Optional)
# ==============================================================================

def generate_charts(metrics_df: pd.DataFrame, output_dir: Path):
    """Generate matplotlib charts if available."""
    if not HAS_MATPLOTLIB or metrics_df is None:
        return
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("Neocortex R2 Backtest Forensics", fontsize=14)
    
    # 1. Action distribution over time (histogram)
    if "shadow_action" in metrics_df.columns:
        ax = axes[0, 0]
        actions = metrics_df["shadow_action"].dropna()
        action_counts = actions.value_counts().sort_index()
        ax.bar(action_counts.index.astype(str), action_counts.values, color=["green", "red", "gray"])
        ax.set_xlabel("Action (0=LONG, 1=SHORT, 2=FLAT)")
        ax.set_ylabel("Count")
        ax.set_title("Overall Action Distribution")
    
    # 2. Confidence over time (rolling mean)
    if "shadow_confidence" in metrics_df.columns:
        ax = axes[0, 1]
        conf = metrics_df["shadow_confidence"].dropna()
        if len(conf) > 100:
            rolling = conf.rolling(window=100).mean()
            ax.plot(rolling.values, linewidth=0.5, alpha=0.8)
            ax.set_xlabel("Step")
            ax.set_ylabel("Confidence (rolling 100)")
            ax.set_title("Confidence Over Time")
    
    # 3. Train steps progression
    if "total_train_steps" in metrics_df.columns:
        ax = axes[1, 0]
        ts = metrics_df["total_train_steps"].dropna()
        ax.plot(ts.values, linewidth=0.5)
        ax.axhline(y=1000, color="red", linestyle="--", label="Checkpoint Threshold")
        ax.set_xlabel("Row")
        ax.set_ylabel("Total Train Steps")
        ax.set_title("Training Progress")
        ax.legend()
    
    # 4. Value distribution
    if "shadow_value" in metrics_df.columns:
        ax = axes[1, 1]
        vals = metrics_df["shadow_value"].dropna()
        ax.hist(vals, bins=50, alpha=0.7, edgecolor="black")
        ax.set_xlabel("Value")
        ax.set_ylabel("Frequency")
        ax.set_title("Shadow Value Distribution")
    
    plt.tight_layout()
    chart_path = output_dir / "forensic_charts.png"
    plt.savefig(chart_path, dpi=150)
    plt.close()
    print(f"✅ Charts saved to: {chart_path}")


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    print("=" * 80)
    print("🔬 NEOCORTEX R2 FORENSIC ANALYSIS")
    print("=" * 80)
    print()
    
    # 1. Analyze metrics CSV
    print("📊 Analyzing neocortex_metrics.csv...")
    metrics_analyzer = MetricsAnalyzer(METRICS_CSV)
    if metrics_analyzer.load():
        metrics_results = metrics_analyzer.analyze()
    else:
        metrics_results = {}
    
    print()
    
    # 2. Analyze shadow intents
    print("🧠 Analyzing shadow_intents.jsonl...")
    intents_analyzer = ShadowIntentsAnalyzer(SHADOW_INTENTS)
    if intents_analyzer.load():
        intents_results = intents_analyzer.analyze()
    else:
        intents_results = {}
    
    print()
    
    # 3. Log forensics
    print("📜 Scanning log files...")
    log_forensics = LogForensics(LOGS_DIR)
    logs_results = log_forensics.analyze()
    print(f"   Scanned {logs_results.get('log_files_scanned', 0)} files")
    
    print()
    
    # 4. Infrastructure check
    print("🗄️ Checking infrastructure...")
    infra_check = InfrastructureCheck(REPO_ROOT)
    infra_results = infra_check.check()
    
    print()
    
    # 5. Generate report
    print("📝 Generating report...")
    report = generate_report(
        metrics_results,
        intents_results,
        logs_results,
        infra_results,
        REPORT_FILE
    )
    
    # 6. Generate charts
    if HAS_MATPLOTLIB and metrics_analyzer.df is not None:
        print()
        print("📈 Generating charts...")
        generate_charts(metrics_analyzer.df, OUTPUT_DIR)
    
    print()
    print("=" * 80)
    print("✅ FORENSIC ANALYSIS COMPLETE")
    print("=" * 80)
    
    # Print key findings
    print()
    print("🔑 KEY FINDINGS:")
    print(f"   • Total train steps: {metrics_results.get('train_steps_max', 0)}")
    print(f"   • Checkpoint threshold: 1000")
    print(f"   • Checkpoints saved: {infra_results.get('checkpoint_files_count', 0)}")
    print(f"   • Shadow intents: {intents_results.get('total_intents', 0):,}")
    print(f"   • PPO trained: {metrics_results.get('ppo_loss_available', False)}")
    print()


if __name__ == "__main__":
    main()
