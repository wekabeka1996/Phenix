# SPDX-License-Identifier: MIT
# SPDX-License-Identifier: MIT
# Copyright (c) 2025 LLA Project

"""
Acceptance and blackbox telemetry emitter.
"""
import json, os, time
from pathlib import Path

def emit_acceptance(run_dir: str, r0_passed: bool, r1_passed: bool, metrics: dict):
    """Write acceptance.json into run_dir/logs/"""
    logs = Path(run_dir) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    out = {
        "r0_acceptance": {
            "passed": r0_passed,
            "band_violations": metrics.get("band_violations", 0),
            "duty_cycle_peak": metrics.get("duty_cycle_peak", 0.0),
            "action_ratio_pct_5m_all": {
                "min": metrics.get("ratio_min", 0.0),
                "max": metrics.get("ratio_max", 0.0)
            }
        },
        "r1_acceptance": {
            "passed": r1_passed,
            "win_rate": metrics.get("win_rate", 0.0)
        },
        "cert": "LLA-R0R1-READY-20250828",
        "ts": time.time()
    }
    with open(logs / "acceptance.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

def log_blackbox(run_dir: str, event: dict):
    """Append an event dict to blackbox.jsonl"""
    logs = Path(run_dir) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False)
    with open(logs / "blackbox.jsonl", "a", encoding="utf-8") as f:
        f.write(line + "\n")