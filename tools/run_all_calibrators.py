"""Run every calibrator in the project with sensible defaults and capture results.

Output:
- reports/calibration_run_2026-05-21/<name>.md per calibrator
- reports/calibration_run_2026-05-21/SUMMARY.md aggregated
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = REPO / "reports" / "calibration_run_2026-05-21"
OUT_DIR.mkdir(parents=True, exist_ok=True)

START = "2026-03-22"
END = "2026-05-21"
SYMBOLS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "SOLUSDT", "XRPUSDT"]


@dataclass
class Calibrator:
    name: str
    args: list[str]
    tier: str
    purpose: str
    timeout: int = 900
    cwd: Path = REPO
    skip_reason: str = ""


CALIBRATORS: list[Calibrator] = [
    # Tier 1 — strategy production
    Calibrator(
        name="01_aurora_thresholds",
        tier="T1-PROD",
        purpose="Aurora signal_threshold + regime_thresholds calibration",
        args=[
            sys.executable, "tools/calibration/calibrate_aurora_thresholds.py",
            "--symbols", *SYMBOLS,
            "--from-date", START, "--to-date", END,
            "--input-source", "recorder-features-v2",
            "--threshold-source-mode", "asset-override-only",
            "--out-dir", str(OUT_DIR / "01_aurora_thresholds_artifacts"),
            "--emit-overlay",
        ],
    ),
    Calibrator(
        name="02_md_amr_weights",
        tier="T1-PROD",
        purpose="MD-AMR strategy weight calibration",
        args=[
            sys.executable, "tools/calibration/calibrate_md_amr_weights.py",
            "--symbols", *SYMBOLS,
            "--start", START, "--end", END,
            "--tf-sec", "900",
            "--trials", "100",
            "--top-k", "5",
            "--out-dir", str(OUT_DIR / "02_md_amr_weights_artifacts"),
        ],
    ),
    Calibrator(
        name="03_mean_reversion_params",
        tier="T1-PROD",
        purpose="Mean Reversion parameter calibration",
        args=[
            sys.executable, "tools/calibration/calibrate_mean_reversion_params.py",
            "--symbols", "DOGEUSDT", "XRPUSDT",
            "--start", START, "--end", END,
            "--tf-sec", "300",
            "--trials", "80",
            "--out-dir", str(OUT_DIR / "03_mr_params_artifacts"),
        ],
    ),
    Calibrator(
        name="04_aurora_signal_weights",
        tier="T1-RESEARCH",
        purpose="Legacy Aurora signal weight surfaces (research only)",
        args=[
            sys.executable, "tools/calibration/calibrate_aurora_signal_weights.py",
            "--symbols", *SYMBOLS,
            "--start", START, "--end", END,
            "--recorder-dir", "data/recorder",
            "--out-dir", str(OUT_DIR / "04_aurora_signal_weights_artifacts"),
        ],
    ),
    Calibrator(
        name="05_aurora_regime_params",
        tier="T1-RESEARCH",
        purpose="Aurora regime overlay candidate search (research)",
        args=[
            sys.executable, "tools/calibration/calibrate_aurora_regime_params.py",
            "--symbols", *SYMBOLS,
            "--start", START, "--end", END,
            "--tf-sec", "300",
            "--n-trials", "120",
            "--out-dir", str(OUT_DIR / "05_aurora_regime_params_artifacts"),
        ],
    ),
    # Tier 2 — policy gates
    Calibrator(
        name="06_low_vol_cost_floor",
        tier="T2-POLICY",
        purpose="LOW_VOLATILITY cost-floor (NRR-062) calibration",
        args=[
            sys.executable, "scripts/calibration/calibrate_low_vol_cost_floor.py",
            "--data-dir", "data",
            "--logs-dir", "logs",
            "--reports-dir", "reports",
            "--regime", "LOW_VOLATILITY",
            "--out-dir", str(OUT_DIR / "06_low_vol_cost_floor_artifacts"),
        ],
    ),
    Calibrator(
        name="07_nrr062_historical",
        tier="T2-POLICY",
        purpose="NRR-062 historical klines calibration",
        args=[
            sys.executable, "calibrators/policy_gates/calibrate_nrr062_historical.py",
        ],
    ),
    Calibrator(
        name="08_system_stress_weights",
        tier="T2-POLICY",
        purpose="System stress weights (research mode)",
        args=[
            sys.executable, "tools/calibration/calibrate_system_stress_weights.py",
            "--mode", "research",
            "--symbols", *SYMBOLS,
            "--tf-sec", "900",
            "--start", START, "--end", END,
            "--out-dir", str(OUT_DIR / "08_system_stress_weights_artifacts"),
        ],
    ),
    # Tier 3 — meta
    Calibrator(
        name="09_objective_stack",
        tier="T3-META",
        purpose="Stage-2 objective stack search",
        args=[
            sys.executable, "tools/calibration/calibrate_objective_stack.py",
            "objective",
            "--recorder-dir", "data/recorder",
            "--symbols", *SYMBOLS,
            "--start", START, "--end", END,
            "--trials", "50",
            "--top-k", "5",
            "--out-dir", str(OUT_DIR / "09_objective_stack_artifacts"),
        ],
    ),
    # Tier 4 — forensics
    Calibrator(
        name="10_confidence_calibration",
        tier="T4-FORENSICS",
        purpose="Regime detector confidence (ECE, Brier)",
        args=[
            sys.executable, "tools/forensics/confidence_calibration.py",
            "--log-dir", "logs",
            "--output-dir", str(OUT_DIR /
                                "10_confidence_calibration_artifacts"),
            "--horizon-minutes", "5",
            "--n-bins", "10",
        ],
    ),
    Calibrator(
        name="11_full_surface",
        tier="T4-FORENSICS",
        purpose="Full-surface multi-strategy grid (hardcoded paths)",
        args=[sys.executable, "tools/forensics/full_surface_calibration.py"],
    ),
    Calibrator(
        name="12_mr_from_logs",
        tier="T4-FORENSICS",
        purpose="MR calibration from bars_300s.jsonl",
        args=[sys.executable, "tools/forensics/mr_calibration_from_logs.py"],
    ),
    Calibrator(
        name="13_shadow_regime_aurora",
        tier="T4-FORENSICS",
        purpose="Shadow regime Aurora enrichment (DOGE/XRP/BNB/PEPE)",
        args=[sys.executable, "tools/forensics/shadow_regime_aurora_calibration.py"],
    ),
    Calibrator(
        name="14_nrr027_per_regime",
        tier="T4-FORENSICS",
        purpose="NRR-027 per-regime safety gate (library, no __main__)",
        args=[sys.executable, "scripts/forensics/nrr027_per_regime_calibrator.py"],
        skip_reason="No __main__ block (library/utility module)",
    ),
    # Tier 5 — audits / utility
    Calibrator(
        name="15_t5e_post_calibration_monitor",
        tier="T5-AUDIT",
        purpose="T5E post-calibration monitor (no __main__)",
        args=[sys.executable, "tools/audits/t5e_post_calibration_monitor.py"],
        skip_reason="No __main__ block (audit utility)",
    ),
    Calibrator(
        name="16_phenix_03v_readonly",
        tier="T5-UTIL",
        purpose="03V read-only economics/sidecar artifact builder",
        args=[sys.executable, "artifacts/_tmp/phenix_03v_readonly_calibration.py"],
    ),
]


def run_one(c: Calibrator) -> dict:
    rec = {
        "name": c.name,
        "tier": c.tier,
        "purpose": c.purpose,
        "command": " ".join(shlex.quote(a) for a in c.args),
        "status": "skipped",
        "returncode": None,
        "duration_sec": 0.0,
        "stdout_tail": "",
        "stderr_tail": "",
        "skip_reason": c.skip_reason,
    }

    if c.skip_reason:
        return rec

    t0 = time.time()
    try:
        proc = subprocess.run(
            c.args,
            cwd=str(c.cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=c.timeout,
        )
        rec["returncode"] = proc.returncode
        rec["status"] = "ok" if proc.returncode == 0 else "failed"
        rec["stdout_tail"] = "\n".join((proc.stdout or "").splitlines()[-80:])
        rec["stderr_tail"] = "\n".join((proc.stderr or "").splitlines()[-80:])
    except subprocess.TimeoutExpired as exc:
        rec["status"] = "timeout"
        rec["stderr_tail"] = f"TIMEOUT after {c.timeout}s: {exc}"
    except Exception as exc:
        rec["status"] = "error"
        rec["stderr_tail"] = f"{type(exc).__name__}: {exc}"
    rec["duration_sec"] = round(time.time() - t0, 2)
    return rec


def write_per_calibrator_md(rec: dict) -> Path:
    p = OUT_DIR / f"{rec['name']}.md"
    lines = [
        f"# Calibrator: {rec['name']}",
        "",
        f"- **Tier**: {rec['tier']}",
        f"- **Purpose**: {rec['purpose']}",
        f"- **Status**: `{rec['status']}`",
        f"- **Return code**: {rec['returncode']}",
        f"- **Duration**: {rec['duration_sec']}s",
        "",
        "## Command",
        "",
        "```bash",
        rec["command"],
        "```",
        "",
    ]
    if rec["skip_reason"]:
        lines += ["## Skip reason", "", rec["skip_reason"], ""]
    if rec["stdout_tail"]:
        lines += ["## stdout (tail)", "", "```", rec["stdout_tail"], "```", ""]
    if rec["stderr_tail"]:
        lines += ["## stderr (tail)", "", "```", rec["stderr_tail"], "```", ""]
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def write_summary(recs: list[dict]) -> Path:
    p = OUT_DIR / "SUMMARY.md"
    by_status: dict[str, int] = {}
    for r in recs:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    lines = [
        "# Calibration Run Summary",
        "",
        f"- **Date**: {datetime.utcnow().isoformat()}Z",
        f"- **Window**: {START} → {END} (60 days)",
        f"- **Symbols**: {', '.join(SYMBOLS)}",
        f"- **Total calibrators**: {len(recs)}",
        "- **Status counts**: "
        + ", ".join(f"`{k}`={v}" for k, v in sorted(by_status.items())),
        "",
        "## Results table",
        "",
        "| # | Name | Tier | Status | rc | Duration (s) | Report |",
        "|---|------|------|--------|----|--------------|--------|",
    ]
    for i, r in enumerate(recs, 1):
        lines.append(
            f"| {i} | {r['name']} | {r['tier']} | `{r['status']}` | "
            f"{r['returncode']} | {r['duration_sec']} | [{r['name']}.md](./{r['name']}.md) |"
        )
    lines += ["", "## Per-calibrator details", ""]
    for r in recs:
        lines += [
            f"### {r['name']} ({r['tier']}) — `{r['status']}`",
            "",
            f"_{r['purpose']}_",
            "",
        ]
        if r["skip_reason"]:
            lines += [f"**Skipped**: {r['skip_reason']}", ""]
        else:
            err_preview = "\n".join(r["stderr_tail"].splitlines()[-10:])
            out_preview = "\n".join(r["stdout_tail"].splitlines()[-10:])
            if out_preview:
                lines += ["stdout tail:", "```", out_preview, "```", ""]
            if err_preview:
                lines += ["stderr tail:", "```", err_preview, "```", ""]
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def main() -> int:
    print(f"[runner] Output: {OUT_DIR}")
    recs: list[dict] = []
    for c in CALIBRATORS:
        print(f"[runner] >>> {c.name} ({c.tier})")
        rec = run_one(c)
        write_per_calibrator_md(rec)
        recs.append(rec)
        print(
            f"[runner]     status={rec['status']} rc={rec['returncode']} t={rec['duration_sec']}s")
    (OUT_DIR / "raw_results.json").write_text(
        json.dumps(recs, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_summary(recs)
    print(f"[runner] Summary: {OUT_DIR / 'SUMMARY.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
