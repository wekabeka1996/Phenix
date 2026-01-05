# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""
Telemetry module.

SPEC Telemetry:
- class Observation(BaseModel): ts:float, gpu_temp_c:float, gpu_util_pct:float, gpu_mem_used_gb:float,
  cpu_load_pct:float, io_wait_pct:float, fan_pct:float, throttling:bool
- class Telemetry: poll()->Observation; stream_to_jsonl(path)
- Detect and normalize units; NVML optional with graceful fallback to psutil/mock.
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from collections import deque
from pathlib import Path
from typing import Deque, List

import psutil
from pydantic import BaseModel

log = logging.getLogger(__name__)


class Observation(BaseModel):
    """Single telemetry snapshot.

    Args/Fields:
        ts: Unix timestamp seconds.
        gpu_temp_c: GPU temperature in Celsius.
        gpu_util_pct: GPU utilization percent [0..100].
        gpu_mem_used_gb: GPU memory used in GB.
        cpu_load_pct: CPU utilization percent [0..100].
        io_wait_pct: IO wait percent [0..100] if available else 0.
        fan_pct: Fan speed percent [0..100] if available else 0.
        throttling: Whether GPU is currently throttling (best-effort).
    """

    ts: float
    gpu_temp_c: float
    gpu_util_pct: float
    gpu_mem_used_gb: float
    cpu_load_pct: float
    io_wait_pct: float
    fan_pct: float
    throttling: bool


class LiveBuffer:
    """Ring buffer to store last N observations."""

    def __init__(self, max_size: int):
        self._buf: Deque[Observation] = deque(maxlen=max_size)

    def add(self, obs: Observation) -> None:
        self._buf.append(obs)

    def get_all(self) -> List[Observation]:
        return list(self._buf)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._buf)


class Telemetry:
    """Telemetry provider using NVML (if available) with psutil fallback.

    On Windows or systems without NVML/GPU, the provider gracefully degrades to
    CPU-only metrics and synthesizes GPU/fan values in mock mode.
    """

    def __init__(self, use_nvml: bool = True, mock_mode: bool = False):
        self.mock_mode = mock_mode or bool(os.getenv("MOCK_NVML", ""))
        self.use_nvml = use_nvml and not self.mock_mode

        self._nvml = None
        self._gpu_handle = None
        self._gpu_mem_total_gb = 0.0

        if self.use_nvml:
            try:
                import pynvml  # type: ignore

                self._nvml = pynvml
                self._nvml.nvmlInit()
                count = self._nvml.nvmlDeviceGetCount()
                if count > 0:
                    self._gpu_handle = self._nvml.nvmlDeviceGetHandleByIndex(0)
                    mem_info = self._nvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
                    self._gpu_mem_total_gb = mem_info.total / (1024 ** 3)
                    log.info("NVML initialized, GPU 0 detected.")
                else:
                    log.warning("NVML initialized but no GPUs found. Falling back to psutil.")
                    self._disable_nvml()
            except Exception as e:  # Broad except to prevent hard crash
                log.warning(f"NVML unavailable ({e!r}). Falling back to psutil/mock.")
                self._disable_nvml()
        else:
            if self.mock_mode:
                log.info("Telemetry running in MOCK mode.")
            else:
                log.info("Telemetry running without NVML (CPU-only).")

        # Prime psutil to avoid first-call zeroes
        try:
            psutil.cpu_percent(interval=None)
        except Exception:
            pass

        self._obs_log_path: Path | None = None

    def _disable_nvml(self) -> None:
        self.use_nvml = False
        self._nvml = None
        self._gpu_handle = None
        self._gpu_mem_total_gb = 0.0

    def poll(self) -> Observation:
        """Polls sensors and returns an Observation. Backoff ~1s is handled by caller."""
        ts = time.time()

        # Defaults
        gpu_temp_c = 0.0
        gpu_util_pct = 0.0
        gpu_mem_used_gb = 0.0
        fan_pct = 0.0
        throttling = False

        if self.use_nvml and self._nvml and self._gpu_handle is not None:
            try:
                temp = self._nvml.nvmlDeviceGetTemperature(
                    self._gpu_handle, self._nvml.NVML_TEMPERATURE_GPU
                )
                util = self._nvml.nvmlDeviceGetUtilizationRates(self._gpu_handle)
                mem = self._nvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)

                gpu_temp_c = float(temp)
                gpu_util_pct = float(util.gpu)
                gpu_mem_used_gb = mem.used / (1024 ** 3)

                try:
                    fan_pct = float(self._nvml.nvmlDeviceGetFanSpeed(self._gpu_handle))
                except Exception:
                    fan_pct = 0.0

                try:
                    reasons = self._nvml.nvmlDeviceGetCurrentClocksThrottleReasons(self._gpu_handle)
                    throttling = reasons != 0
                except Exception:
                    throttling = False
            except Exception as e:
                log.warning(f"NVML polling failed ({e!r}). Degrading to psutil/mock.")
                self._disable_nvml()

        # CPU metrics via psutil
        try:
            cpu_load_pct = float(psutil.cpu_percent(interval=None))
        except Exception:
            cpu_load_pct = 0.0

        # IO wait percent is not always available on Windows; try cpu_times_percent
        io_wait_pct = 0.0
        try:
            ctp = psutil.cpu_times_percent(interval=None)
            # Some platforms have iowait attribute
            if hasattr(ctp, "iowait") and ctp.iowait is not None:
                io_wait_pct = float(ctp.iowait)
        except Exception:
            pass

        if self.mock_mode and not self.use_nvml:
            # Synthesize reasonable GPU metrics from CPU load
            base = cpu_load_pct / 2
            gpu_util_pct = min(100.0, max(0.0, base + random.uniform(-5, 5)))
            gpu_temp_c = min(95.0, max(25.0, 35.0 + 0.6 * gpu_util_pct + random.uniform(-3, 3)))
            fan_pct = min(100.0, max(0.0, 20.0 + 0.8 * (gpu_temp_c - 30.0)))
            # Assume an 8 GB device mock
            gpu_mem_used_gb = max(0.1, min(8.0, 0.5 + 0.02 * gpu_util_pct + random.uniform(-0.1, 0.1)))
            throttling = gpu_temp_c > 80.0 or gpu_util_pct > 95.0

        obs = Observation(
            ts=ts,
            gpu_temp_c=gpu_temp_c,
            gpu_util_pct=gpu_util_pct,
            gpu_mem_used_gb=gpu_mem_used_gb,
            cpu_load_pct=cpu_load_pct,
            io_wait_pct=io_wait_pct,
            fan_pct=fan_pct,
            throttling=throttling,
        )

        if self._obs_log_path is not None:
            try:
                with open(self._obs_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(obs.dict()) + "\n")
            except Exception as e:
                log.warning(f"Failed to write observation to JSONL: {e!r}")

        return obs

    def stream_to_jsonl(self, path: str | Path) -> None:
        """Enable streaming observations to a JSONL file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        self._obs_log_path = p

    def cleanup(self) -> None:  # pragma: no cover - trivial
        """Cleanup resources (e.g., NVML shutdown)."""
        if self._nvml is not None:
            try:
                self._nvml.nvmlShutdown()
            except Exception:
                pass
        self._nvml = None
        self._gpu_handle = None


# Minimal smoke-test
if __name__ == "__main__":  # pragma: no cover - manual
    t = Telemetry(use_nvml=True, mock_mode=False)
    t.stream_to_jsonl("obs.jsonl")
    for _ in range(5):
        print(t.poll().dict())
        time.sleep(0.5)