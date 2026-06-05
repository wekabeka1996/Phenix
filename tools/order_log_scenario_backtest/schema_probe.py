from __future__ import annotations

import json
from pathlib import Path
from typing import Any


TARGET_FAMILIES: tuple[tuple[str, str], ...] = (
    ("BOOT", ""),
    ("ORDER_INTENT", "ExposureGuard"),
    ("ORDER_INTENT", "DecisionMaking"),
    ("ORDER_INTENT", "ExecPosFSM"),
    ("ORDER_PLACED", ""),
    ("ORDER_FILLED", ""),
    ("POSITION_CLOSED", ""),
)


def _match_family(payload: dict[str, Any], family: tuple[str, str]) -> bool:
    event_type = str(payload.get("event_type") or "")
    source_fsm = str(payload.get("source_fsm") or "")
    if event_type != family[0]:
        return False
    if family[1]:
        return source_fsm == family[1]
    return True


def probe_schema(
    order_log_path: Path,
    report_root: Path,
    *,
    max_lines: int = 5000,
) -> dict[str, Any]:
    report_root.mkdir(parents=True, exist_ok=True)
    remaining = set(TARGET_FAMILIES)
    samples: list[dict[str, Any]] = []
    lines_read = 0

    with order_log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_no, raw_line in enumerate(handle, start=1):
            lines_read = line_no
            if line_no > max_lines and not remaining:
                break
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            family = next((item for item in remaining if _match_family(payload, item)), None)
            if family is None:
                continue
            samples.append(
                {
                    "line_no": line_no,
                    "event_type": family[0],
                    "source_fsm": family[1],
                    "sample": payload,
                }
            )
            remaining.remove(family)
            if not remaining and line_no >= max_lines:
                break

    payload = {
        "order_log_path": str(order_log_path),
        "max_lines": max_lines,
        "lines_read": lines_read,
        "target_families": [
            {"event_type": family[0], "source_fsm": family[1]} for family in TARGET_FAMILIES
        ],
        "captured_families": samples,
        "missing_families": [
            {"event_type": family[0], "source_fsm": family[1]} for family in sorted(remaining)
        ],
    }
    (report_root / "schema_probe.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return payload
