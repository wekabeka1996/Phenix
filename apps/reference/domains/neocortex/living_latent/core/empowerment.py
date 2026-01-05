# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project


# WRITE PRODUCTION-READY PYTHON 3.11.
# Follow this SPEC EXACTLY. type hints, pydantic for IO, no global state, dependency injection via constructors.
# Logging: structured JSON to logs/*.jsonl. Handle exceptions gracefully and continue.
# Every public function must have a docstring with Args/Returns/Raises.

# SPEC Empowerment:
# EmpowermentEstimator: compute_ba_bound(history)->float, proxy_success_rate()->float, select_mode().

import logging
from collections import deque
from typing import Deque, List, Optional

import numpy as np

from .config import EmpowermentConfig

log = logging.getLogger(__name__)

class EmpowermentEstimator:
    """Empowerment / intrinsic control estimator with tiered fallbacks.

    R0-05 Hardening Features:
    - Lightweight InfoNCE-based BA-bound approximation (online, O(k_neg ⋅ dim)).
    - Variance-based fallback chain: ba_bound -> proxy (plan success rate) -> gramian.
    - Internal stability tracking (exponential moving absolute difference of successive BA estimates).
    """

    def __init__(self, config: EmpowermentConfig):
        self.config = config
        self.mode = config.mode
        self.ba_bound_history: Deque[float] = deque(maxlen=256)
        self.plan_success_history: Deque[bool] = deque(maxlen=100)
        self.prev_empowerment: float = 0.0
        self.last_empowerment: float = 0.0
        # Buffers for InfoNCE BA-bound (latent/state transitions)
        self._enc_buf: Deque[np.ndarray] = deque(maxlen=512)
        self._dec_buf: Deque[np.ndarray] = deque(maxlen=512)
        self._last_infonce: Optional[float] = None
        self._last_infonce_var: float = 0.0

    # ---------------- InfoNCE BA-bound -----------------
    def add_transition(self, z_t: np.ndarray, z_tp1: np.ndarray) -> None:
        """Add a latent/state transition (z_t -> z_{t+1}) used for InfoNCE.

        Args:
            z_t: Current latent/state vector (1D array).
            z_tp1: Next latent/state vector (1D array).
        """
        if z_t.ndim != 1 or z_tp1.ndim != 1:
            return
        self._enc_buf.append(z_t.astype(np.float32))
        self._dec_buf.append(z_tp1.astype(np.float32))

    def _compute_infonce_ba_bound(self, k_neg: int = 16) -> Optional[float]:
        """Compute a single-sample InfoNCE lower bound approximation (BA-bound proxy).

        Returns None if insufficient data in buffers.
        """
        n = min(len(self._enc_buf), len(self._dec_buf))
        if n < k_neg + 2:
            return None
        idx = np.random.randint(0, n)
        z_t = self._enc_buf[idx]
        z_pos = self._dec_buf[idx]
        # Choose negatives
        pool = np.arange(n)
        np.random.shuffle(pool)
        neg_idx = [i for i in pool if i != idx][:k_neg]
        z_negs = np.stack([self._dec_buf[i] for i in neg_idx], axis=0)

        def cosine(a: np.ndarray, b: np.ndarray) -> float:
            return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8))

        temperature = 0.07
        pos_sim = cosine(z_t, z_pos) / temperature
        neg_sims = np.array([cosine(z_t, n_) / temperature for n_ in z_negs], dtype=np.float32)
        m = max(pos_sim, float(neg_sims.max()))
        exp_pos = np.exp(pos_sim - m)
        exp_negs = np.exp(neg_sims - m).sum()
        infonce_loss = -np.log(exp_pos / (exp_pos + exp_negs + 1e-12) + 1e-12)
        ba_est = float(1.0 / (1.0 + infonce_loss))  # map to (0,1]
        if self._last_infonce is not None:
            self._last_infonce_var = 0.9 * self._last_infonce_var + 0.1 * abs(self._last_infonce - ba_est)
        self._last_infonce = ba_est
        return ba_est

    def _get_proxy_success_rate(self) -> float:
        """Calculates the success rate of recent plans."""
        if not self.plan_success_history:
            return 0.0
        return sum(self.plan_success_history) / len(self.plan_success_history)
    
    def _compute_gramian_controllability(self, history: np.ndarray) -> float:
        """
        Ultimate fallback: computes controllability via Gramian of a simple AR(1) model.
        High determinant of the Gramian implies the system is controllable.
        
        Args:
            history: A numpy array of recent feature vectors (n_steps, n_features).
        """
        if history.shape[0] < 2:
            return 0.0
        try:
            # Fit a simple AR(1) model: x_t = A * x_{t-1}
            X_t = history[1:]
            X_t_minus_1 = history[:-1]
            A, _, _, _ = np.linalg.lstsq(X_t_minus_1, X_t, rcond=None)
            
            # For a simple discrete system, controllability Gramian is I + A*A.T + ...
            # We approximate with just the first term of the sum.
            # A simpler proxy is just how much A deviates from identity.
            gramian_proxy = np.linalg.det(A.T @ A)
            return np.clip(gramian_proxy, 0, 1.0)
        except np.linalg.LinAlgError:
            log.warning("Could not compute Gramian controllability due to singular matrix.")
            return 0.0


    def select_mode(self):
        """Switches estimation mode based on the stability of the BA-bound."""
        if len(self.ba_bound_history) > 30:
            variance = float(np.var(self.ba_bound_history))
            if variance > self.config.fallback_threshold:
                if self.mode == "ba_bound":
                    log.warning(
                        f"BA-bound variance ({variance:.3f}) exceeds threshold {self.config.fallback_threshold:.3f}. -> proxy"
                    )
                self.mode = "proxy"

        success_rate = self._get_proxy_success_rate()
        if self.mode == "proxy" and success_rate < self.config.proxy_min_valid:
             if len(self.plan_success_history) > 20:
                log.warning(
                    f"Plan success rate ({success_rate:.2f}) is below minimum. "
                    f"Using 'gramian' fallback."
                )
             self.mode = "gramian"
        
    def record_ba_bound(self, value: float):
        """Records a new value for the primary estimator."""
        self.ba_bound_history.append(value)

    def record_plan_outcome(self, success: bool):
        """Records the outcome of a recent plan execution."""
        self.plan_success_history.append(success)

    def compute(self, telemetry_history: np.ndarray) -> float:
        """
        Computes empowerment using the currently selected mode.

        Args:
            telemetry_history: A numpy array of recent (normalized) telemetry features.

        Returns:
            The estimated empowerment value.
        """
        self.select_mode()  # Update mode based on latest stats

        # remember previous value
        self.prev_empowerment = self.last_empowerment

        if self.mode == "ba_bound":
            # Try real InfoNCE estimate
            v = self._compute_infonce_ba_bound()
            if v is not None:
                self.record_ba_bound(v)
                value = v
            else:
                # Fallback: use last recorded or 0
                value = self.ba_bound_history[-1] if self.ba_bound_history else 0.0
        elif self.mode == "proxy":
            value = self._get_proxy_success_rate()
        else:  # gramian
            value = self._compute_gramian_controllability(telemetry_history)

        self.last_empowerment = float(value)
        return self.last_empowerment

# Example Usage
if __name__ == '__main__':
    cfg = EmpowermentConfig(fallback_threshold=0.1)
    estimator = EmpowermentEstimator(cfg)

    print("--- Simulating stable BA-bound ---")
    for _ in range(60):
        # simulate transitions and stable InfoNCE empowerment
        z_t = np.random.randn(16).astype(np.float32)
        z_tp1 = z_t + 0.05 * np.random.randn(16).astype(np.float32)
        estimator.add_transition(z_t, z_tp1)
        v = estimator._compute_infonce_ba_bound()
        if v is not None:
            estimator.record_ba_bound(v)
    
    emp_value = estimator.compute(np.random.rand(50, 6))
    print(f"Mode: {estimator.mode}, Empowerment: {emp_value:.3f}")

    print("\n--- Simulating UNSTABLE BA-bound ---")
    for _ in range(40):
        z_t = np.random.randn(16).astype(np.float32)
        z_tp1 = -z_t + np.random.randn(16).astype(np.float32)
        estimator.add_transition(z_t, z_tp1)
        v = estimator._compute_infonce_ba_bound()
        if v is not None:
            # Inject volatility
            estimator.record_ba_bound(min(1.0, max(0.0, v + np.random.uniform(-0.8, 0.8))))

    emp_value = estimator.compute(np.random.rand(50, 6))
    print(f"Mode: {estimator.mode}, Empowerment: {emp_value:.3f} (should switch to proxy)")

    print("\n--- Simulating FAILED plans ---")
    for _ in range(30):
        estimator.record_plan_outcome(False) # All plans fail
    
    emp_value = estimator.compute(np.random.rand(50, 6))
    print(f"Mode: {estimator.mode}, Empowerment: {emp_value:.3f} (should switch to gramian)")