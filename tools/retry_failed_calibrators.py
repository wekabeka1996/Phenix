"""Retry calibrators that failed for fixable reasons (PYTHONPATH, arg names)."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "reports" / "calibration_run_2026-05-21"

START = "2026-03-22"
END = "2026-05-21"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "SOLUSDT", "XRPUSDT"]

env = os.environ.copy()
env["PYTHONPATH"] = str(REPO) + os.pathsep + env.get("PYTHONPATH", "")

RETRIES = [
    {
        "name": "01_aurora_thresholds",
        "args": [
            sys.executable, "tools/calibration/calibrate_aurora_thresholds.py",
            "--symbols", *SYMBOLS,
            "--from-date", START, "--to-date", END,
            "--input-source", "recorder-features-v2",
            "--threshold-source-mode", "asset-override-only",
            "--out-dir", str(OUT_DIR / "01_aurora_thresholds_artifacts"),
            "--emit-overlay",
        ],
        "timeout": 900,
    },
    {
        "name": "04_aurora_signal_weights",
        "args": [
            sys.executable, "tools/calibration/calibrate_aurora_signal_weights.py",
            "--symbols", *SYMBOLS,
            "--start", START, "--end", END,
            "--recorder-dir", "data/recorder",
        ],
        "timeout": 600,
    },
    {
        "name": "06_low_vol_cost_floor",
        "args": [
            sys.executable, "scripts/calibration/calibrate_low_vol_cost_floor.py",
            "--data-dir", "data",
            "--logs-dir", "logs",
            "--reports-dir", "reports",
            "--regime", "LOW_VOLATILITY",
            "--out-dir", str(OUT_DIR / "06_low_vol_cost_floor_artifacts"),
        ],
        "timeout": 600,
    },
    {
        "name": "07_nrr062_historical",
        "args": [
            sys.executable, "calibrators/policy_gates/calibrate_nrr062_historical.py",
        ],
        "timeout": 600,
    },
    {
        "name": "10_confidence_calibration",
        "args": [
            sys.executable, "tools/forensics/confidence_calibration.py",
            "--log-dir", "logs",
            "--output-dir", str(OUT_DIR /
                                "10_confidence_calibration_artifacts"),
            "--horizon", "5",
            "--n-bins", "10",
        ],
        "timeout": 600,
    },
]


def main() -> int:
    retried = []
    for r in RETRIES:
        print(f"[retry] >>> {r['name']}")
        t0 = time.time()
        try:
            proc = subprocess.run(
                r["args"],
                cwd=str(REPO),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=r["timeout"],
                env=env,
            )
            rec = {
                "name": r["name"],
                "status": "ok" if proc.returncode == 0 else "failed",
                "returncode": proc.returncode,
                "duration_sec": round(time.time() - t0, 2),
                "command": " ".join(shlex.quote(a) for a in r["args"]),
                "stdout_tail": "\n".join((proc.stdout or "").splitlines()[-80:]),
                "stderr_tail": "\n".join((proc.stderr or "").splitlines()[-80:]),
            }
        except subprocess.TimeoutExpired:
            rec = {
                "name": r["name"], "status": "timeout", "returncode": None,
                "duration_sec": r["timeout"], "command": " ".join(r["args"]),
                "stdout_tail": "", "stderr_tail": f"TIMEOUT {r['timeout']}s",
            }
        except Exception as exc:
            rec = {
                "name": r["name"], "status": "error", "returncode": None,
                "duration_sec": round(time.time() - t0, 2),
                "command": " ".join(r["args"]),
                "stdout_tail": "", "stderr_tail": f"{type(exc).__name__}: {exc}",
            }

        # Rewrite per-calibrator MD with retry header
        p = OUT_DIR / f"{r['name']}.md"
        existing = p.read_text(encoding="utf-8") if p.exists() else ""
        retry_block = [
            "",
            "---",
            "",
            f"## RETRY (PYTHONPATH+fixed args)",
            "",
            f"- **Status**: `{rec['status']}`",
            f"- **Return code**: {rec['returncode']}",
            f"- **Duration**: {rec['duration_sec']}s",
            "",
            "### Command",
            "",
            "```bash",
            f"PYTHONPATH=. {rec['command']}",
            "```",
            "",
        ]
        if rec["stdout_tail"]:
            retry_block += ["### stdout (tail)", "",
                            "```", rec["stdout_tail"], "```", ""]
        if rec["stderr_tail"]:
            retry_block += ["### stderr (tail)", "",
                            "```", rec["stderr_tail"], "```", ""]
        p.write_text(existing + "\n".join(retry_block), encoding="utf-8")

        retried.append(rec)
        print(
            f"[retry]     status={rec['status']} rc={rec['returncode']} t={rec['duration_sec']}s")

    (OUT_DIR / "retry_results.json").write_text(
        json.dumps(retried, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
