"""
Online Normalization Utilities

WelfordNormalizer implements a running (per-feature) mean/variance estimator
using Welford's algorithm, suitable for online z-score normalization.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import threading

import numpy as np


@dataclass
class WelfordState:
    count: int
    mean: np.ndarray
    m2: np.ndarray


class WelfordNormalizer:
    """
    Running z-score normalizer (per-feature) using Welford algorithm.

    State is persisted so normalization statistics survive restarts.
    """

    def __init__(self, dim: int, eps: float = 1e-8):
        if dim <= 0:
            raise ValueError(f"dim must be > 0, got {dim}")
        self._dim = int(dim)
        self._eps = np.float32(eps)
        self._lock = threading.Lock()

        self._count: int = 0
        self._mean = np.zeros((self._dim,), dtype=np.float32)
        self._m2 = np.zeros((self._dim,), dtype=np.float32)

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def count(self) -> int:
        return self._count

    def state(self) -> WelfordState:
        with self._lock:
            return WelfordState(
                count=int(self._count),
                mean=self._mean.copy(),
                m2=self._m2.copy(),
            )

    def update(self, x: np.ndarray) -> None:
        """
        Update running stats with a single observation vector `x` (shape: (dim,)).
        """
        x = np.asarray(x, dtype=np.float32).reshape(-1)
        if x.shape[0] != self._dim:
            raise ValueError(f"x has dim {x.shape[0]}, expected {self._dim}")

        with self._lock:
            self._count += 1
            if self._count == 1:
                self._mean = x.copy()
                self._m2.fill(np.float32(0.0))
                return

            delta = x - self._mean
            self._mean = self._mean + (delta / np.float32(self._count))
            delta2 = x - self._mean
            self._m2 = self._m2 + (delta * delta2)

    def _variance(self) -> np.ndarray:
        if self._count < 2:
            return np.zeros((self._dim,), dtype=np.float32)
        return self._m2 / np.float32(self._count - 1)

    def normalize(self, x: np.ndarray) -> np.ndarray:
        """
        Normalize vector `x` using current running stats.
        Returns float32 vector of shape (dim,).
        """
        x = np.asarray(x, dtype=np.float32).reshape(-1)
        if x.shape[0] != self._dim:
            raise ValueError(f"x has dim {x.shape[0]}, expected {self._dim}")

        with self._lock:
            mean = self._mean.copy()
            var = self._variance()

        std = np.sqrt(var + self._eps, dtype=np.float32)
        std = np.where(std > 0, std, np.float32(1.0)).astype(np.float32)
        return ((x - mean) / std).astype(np.float32)

    def save_state(self, path: Path) -> None:
        """
        Persist state to `path` as an npz (atomic write).
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")

        st = self.state()
        with open(tmp_path, "wb") as f:
            np.savez(
                f,
                count=np.asarray([st.count], dtype=np.int64),
                mean=st.mean.astype(np.float32),
                m2=st.m2.astype(np.float32),
                dim=np.asarray([self._dim], dtype=np.int64),
                eps=np.asarray([float(self._eps)], dtype=np.float32),
            )
        tmp_path.replace(path)

    def load_state(self, path: Path) -> bool:
        """
        Load persisted state from `path`.
        Returns True if loaded, False if file missing.
        """
        path = Path(path)
        if not path.exists():
            return False

        with np.load(path, allow_pickle=False) as data:
            count = int(np.asarray(data["count"]).reshape(-1)[0])
            dim = int(np.asarray(data["dim"]).reshape(-1)[0])
            mean = np.asarray(data["mean"], dtype=np.float32).reshape(-1)
            m2 = np.asarray(data["m2"], dtype=np.float32).reshape(-1)

        if dim != self._dim or mean.shape[0] != self._dim or m2.shape[0] != self._dim:
            raise ValueError(
                f"Normalizer state dim mismatch: file_dim={dim} mean_dim={mean.shape[0]} "
                f"expected={self._dim}"
            )

        with self._lock:
            self._count = count
            self._mean = mean
            self._m2 = m2

        return True
