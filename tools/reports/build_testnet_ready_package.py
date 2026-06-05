from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_HALT_CONDITIONS = (
    "Cumulative drawdown exceeds configured testnet guardrail.",
    "Three consecutive losing trades without explained parity-consistent cause.",
    "Fee share exceeds configured ceiling over the review window.",
)

DEFAULT_ROLLBACK_CONDITIONS = (
    "Parity harness regression after config snapshot freeze.",
    "OOS stability proof drops below required threshold on the frozen window.",
    "Observed testnet behavior diverges materially from retained parity assumptions.",
)


def build_testnet_ready_report(
    *,
    oos_report_path: str,
    parity_summary_path: str,
    config_snapshot_path: str,
    output_path: str,
) -> Path:
    oos_path = Path(oos_report_path)
    parity_path = Path(parity_summary_path)
    config_path = Path(config_snapshot_path)
    out_path = Path(output_path)

    oos_payload = json.loads(oos_path.read_text(encoding="utf-8")) if oos_path.suffix == ".json" else {"path": str(oos_path)}
    parity_payload = json.loads(parity_path.read_text(encoding="utf-8")) if parity_path.suffix == ".json" else {"path": str(parity_path)}

    lines = [
        "# TESTNET_READY_PACKAGE_V1",
        "",
        f"Generated at UTC: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Inputs",
        f"- OOS proof: `{oos_path}`",
        f"- Parity summary: `{parity_path}`",
        f"- Exact config snapshot: `{config_path}`",
        "",
        "## Assertions",
        "- Delivery target is testnet-ready only.",
        "- Live canary remains out of scope for this package.",
        "- Parity limitations must be carried forward into operator review.",
        "",
        "## OOS Summary",
        f"- Payload: `{json.dumps(oos_payload, ensure_ascii=False)[:800]}`",
        "",
        "## Parity Summary",
        f"- Payload: `{json.dumps(parity_payload, ensure_ascii=False)[:800]}`",
        "",
        "## Halt Conditions",
    ]
    lines.extend(f"- {item}" for item in DEFAULT_HALT_CONDITIONS)
    lines.extend(
        [
            "",
            "## Rollback Conditions",
        ]
    )
    lines.extend(f"- {item}" for item in DEFAULT_ROLLBACK_CONDITIONS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oos-report", required=True)
    parser.add_argument("--parity-summary", required=True)
    parser.add_argument("--config-snapshot", required=True)
    parser.add_argument("--output", default="reports/TESTNET_READY_PACKAGE_V1.md")
    args = parser.parse_args(argv)
    out_path = build_testnet_ready_report(
        oos_report_path=args.oos_report,
        parity_summary_path=args.parity_summary,
        config_snapshot_path=args.config_snapshot,
        output_path=args.output,
    )
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
