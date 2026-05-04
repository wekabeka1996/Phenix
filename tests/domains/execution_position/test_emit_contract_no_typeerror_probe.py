from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
TARGET_FILES = [
    REPO_ROOT / "vfoundation/core/fsm_emit_compat.py",
    REPO_ROOT / "apps/reference/domains/execution_position/terminal_order_contracts.py",
    REPO_ROOT / "apps/reference/domains/execution_position/event_handlers.py",
    REPO_ROOT / "apps/reference/domains/execution_position/trade_intent_reject_contracts.py",
]


def test_emit_contract_helpers_do_not_probe_signature_via_typeerror() -> None:
    offenders: list[str] = []
    for path in TARGET_FILES:
        text = path.read_text(encoding="utf-8")
        if "except TypeError" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == [], (
        "Emit contract helpers must not infer call shape via `except TypeError`: "
        + ", ".join(offenders)
    )
