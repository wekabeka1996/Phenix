# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

# FIX: Added missing imports: time, psutil

import logging
import time
import psutil
from collections import deque
from pathlib import Path
from typing import Deque, List, Optional

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from .config import ViabilityConfig
from .telemetry import LiveBuffer, Observation

log = logging.getLogger(__name__)

class OneClassAE(nn.Module):
    """A simple one-class autoencoder for anomaly detection on telemetry data."""
    def __init__(self, input_dim: int = 6, latent_dim: int = 16):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 32),
            nn.ReLU(),
            nn.Linear(32, latent_dim)
        )
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 32),
            nn.ReLU(),
            nn.Linear(32, input_dim)
        )
        self.input_dim = input_dim

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass through the autoencoder."""
        encoded = self.encoder(x)
        decoded = self.decoder(encoded)
        return decoded

class ConformalCalibrator:
    """Calculates the viability threshold 'tau' using conformal prediction."""
    def __init__(self, alpha: float, window: int, min_count: int):
        if not 0 < alpha < 1:
            raise ValueError("alpha must be between 0 and 1")
        self.alpha = alpha
        self.window_size = window
        self.min_count = min_count
        self.error_buffer: Deque[float] = deque(maxlen=self.window_size)
        self._current_tau: Optional[float] = None

    def add_error(self, error: float):
        """Adds a new reconstruction error to the buffer."""
        self.error_buffer.append(error)

    def calibrate(self) -> Optional[float]:
        """
        Updates tau if the buffer has enough data.
        Returns the new tau value or the last known value if not enough data.
        """
        if len(self.error_buffer) < self.min_count:
            if self._current_tau is None:
                log.warning(
                    f"Not enough data to calibrate tau (have {len(self.error_buffer)}, need {self.min_count}). "
                    f"Viability checks will be disabled until calibrated."
                )
            else:
                log.warning(
                    f"Not enough data to re-calibrate tau. Using last known value: {self._current_tau:.4f}"
                )
            return self._current_tau

        errors = np.array(list(self.error_buffer))
        raw_tau = np.quantile(errors, 1 - self.alpha)
        # tau_floor will be applied externally (ViabilityModel) if available; store raw first
        self._current_tau = raw_tau
        log.info(f"Conformal tau calibrated (raw) to {self._current_tau:.4f} from {len(errors)} samples.")
        return self._current_tau

    @property
    def tau(self) -> Optional[float]:
        """Returns the current viability threshold."""
        return self._current_tau

    def count(self) -> int:
        """Returns number of calibration samples currently buffered."""
        return len(self.error_buffer)


class ViabilityModel:
    """
    Manages the agent's viability by combining an autoencoder for anomaly detection
    with a conformal calibrator for setting dynamic thresholds.
    """
    def __init__(self, config: ViabilityConfig, device: str = 'cpu'):
        self.config = config
        self.device = torch.device(device)
        # Assuming 6 key features from Observation for the AE
        self.model = OneClassAE(input_dim=6).to(self.device)
        self.calibrator = ConformalCalibrator(
            alpha=config.alpha,
            window=config.window,
            min_count=config.min_count
        )
        self.optimizer = optim.Adam(self.model.parameters(), lr=1e-3)
        self.criterion = nn.MSELoss()
        self.tau_history: List[dict] = []
        self._last_fit_time = 0.0

    @staticmethod
    def _obs_to_tensor(obs: Observation) -> torch.Tensor:
        """Extracts and normalizes features from an Observation."""
        # A simple normalization, can be improved with running stats
        features = torch.tensor([
            obs.gpu_temp_c / 100.0,
            obs.gpu_util_pct / 100.0,
            obs.gpu_mem_used_gb / 16.0, # Assuming 16GB max
            obs.cpu_load_pct / 100.0,
            obs.io_wait_pct / 100.0,
            obs.fan_pct / 100.0,
        ], dtype=torch.float32)
        return features.unsqueeze(0)

    def fit(self, buffer: LiveBuffer, force: bool = False) -> None:
        """
        Fits the autoencoder on the live buffer data if enough time has passed
        or if forced.
        """
        now = time.time()
        if not force and (now - self._last_fit_time < self.config.retrain_every_s):
            return

        observations = buffer.get_all()
        if len(observations) < self.calibrator.min_count:
            log.warning(f"Skipping ViabilityModel fit: not enough data in buffer.")
            return

        log.info("Fitting ViabilityModel autoencoder...")
        dataset = torch.cat([self._obs_to_tensor(obs) for obs in observations]).to(self.device)
        
        # Simple training loop
        self.model.train()
        for epoch in range(5): # A few epochs for online learning
            self.optimizer.zero_grad()
            reconstructions = self.model(dataset)
            loss = self.criterion(reconstructions, dataset)
            loss.backward()
            self.optimizer.step()
        
        log.info(f"ViabilityModel fit complete. Final loss: {loss.item():.6f}")
        self._last_fit_time = now
        # Recalibrate with new errors
        self.recalibrate_on_buffer(buffer)

    def recalibrate_on_buffer(self, buffer: LiveBuffer):
        """Recalculates errors for the entire buffer and recalibrates tau."""
        log.info("Recalibrating tau on the full buffer...")
        observations = buffer.get_all()
        for obs in observations:
            error = self.score(obs)
            self.calibrator.add_error(error)
        
        new_tau = self.calibrator.calibrate()
        if new_tau is not None:
            old_tau = self.tau_history[-1]['tau'] if self.tau_history else None
            # Apply tau_floor from config if present
            try:
                floor = getattr(self.config, 'tau_floor', None)
                if floor is not None:
                    clamped = max(new_tau, floor)
                    if clamped != new_tau:
                        log.info(f"Applied tau_floor {floor:.4f}: tau clamped from {new_tau:.6f} to {clamped:.6f}")
                    new_tau = clamped
                    self.calibrator._current_tau = new_tau  # sync back
            except Exception as e:
                log.warning(f"tau_floor application failed: {e}")
            now_ts = time.time()
            self.tau_history.append({"ts": now_ts, "tau": new_tau})
            # Emit structured line for downstream drift summarizer (JSONL style via logger)
            if old_tau is not None:
                drift = abs(new_tau - old_tau)
                log.info(f"VIABILITY_TAU_UPDATE old={old_tau:.6f} new={new_tau:.6f} drift_abs={drift:.6f}")

    def score(self, obs: Observation) -> float:
        """Calculates the reconstruction error for a single observation."""
        self.model.eval()
        with torch.no_grad():
            features = self._obs_to_tensor(obs).to(self.device)
            reconstruction = self.model(features)
            error = self.criterion(reconstruction, features).item()
        return error

    def is_alive(self, obs: Observation) -> bool:
        """
        Checks if the agent is in a viable state based on the conformal threshold.
        Also updates the error buffer for future calibrations.
        """
        tau = self.calibrator.tau
        if tau is None:
            return True # Fail open if not calibrated

        error = self.score(obs)
        self.calibrator.add_error(error) # Add error for ongoing calibration
        return error <= tau

    def dump_tau_series(self, log_dir: Path):
        """Saves the history of tau values to a file."""
        import json
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / "viability_tau.jsonl"
        with open(path, "a") as f:
            for entry in self.tau_history:
                f.write(json.dumps(entry) + "\n")
        self.tau_history.clear()

# Example usage
if __name__ == '__main__':
    from .telemetry import Telemetry
    # Create dummy config
    cfg = ViabilityConfig()
    vm = ViabilityModel(cfg)
    telemetry = Telemetry(mock_mode=True)
    live_buffer = LiveBuffer(max_size=cfg.window)

    print("Populating buffer with initial 'healthy' data...")
    for _ in range(cfg.min_count):
        live_buffer.add(telemetry.poll())
    
    vm.fit(live_buffer, force=True)
    print(f"Initial Tau: {vm.calibrator.tau}")

    print("\nSimulating a high-load event...")
    # A bit of a hack to simulate anomaly in mock mode
    psutil.cpu_percent() # reset
    time.sleep(0.1)
    # create a fake high load to influence mock telemetry
    _ = [x*x for x in range(10**6)] 
    
    anomaly_obs = telemetry.poll()
    is_ok = vm.is_alive(anomaly_obs)
    print(f"Observation: {anomaly_obs.dict()}")
    print(f"Reconstruction error: {vm.score(anomaly_obs):.4f}")
    print(f"Is alive? {is_ok} (Threshold tau: {vm.calibrator.tau:.4f})")