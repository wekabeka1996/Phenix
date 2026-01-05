# SPDX-License-Identifier: MIT
"""
LLA Panic Stop Mechanism
Provides safe halt functionality for emergency situations.
"""

import os
import time
from pathlib import Path
from typing import Dict, Any
from living_latent.telemetry.acceptance import log_blackbox


# Panic stop file location (Windows-safe path)
PANIC_FILE = r"C:\ProgramData\LLA\state\PANIC_STOP"


def panic_guard(run_dir: str, state: Dict[str, Any]) -> None:
    """
    Check for panic stop file and halt injections if present.

    Args:
        run_dir: Current run directory path
        state: Runtime state dict to modify

    Raises:
        SystemExit: When panic stop is triggered
    """
    if os.path.exists(PANIC_FILE):
        # Stop all injections
        state["rate_limit_per_min"] = 0
        state["force_no_op"] = True

        # Log panic event
        log_blackbox(run_dir, {
            "event": "PANIC_STOP",
            "ts": time.time(),
            "message": "Emergency stop triggered via panic file"
        })

        print("[PANIC] Emergency stop activated. Halting all injections.")
        raise SystemExit(0)


def create_panic_file() -> bool:
    """
    Create the panic stop file to trigger emergency halt.
    Returns True if file was created successfully.
    """
    try:
        panic_path = Path(PANIC_FILE)
        panic_path.parent.mkdir(parents=True, exist_ok=True)
        panic_path.touch()
        return True
    except Exception as e:
        print(f"[PANIC] Failed to create panic file: {e}")
        return False


def remove_panic_file() -> bool:
    """
    Remove the panic stop file to resume normal operation.
    Returns True if file was removed successfully.
    """
    try:
        if os.path.exists(PANIC_FILE):
            os.remove(PANIC_FILE)
            return True
        return False
    except Exception as e:
        print(f"[PANIC] Failed to remove panic file: {e}")
        return False