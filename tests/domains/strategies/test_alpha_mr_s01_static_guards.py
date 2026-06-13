from __future__ import annotations

from pathlib import Path


def test_alpha_mr_s01_runtime_has_no_direct_execution_imports():
    runtime_dir = Path("apps/reference/domains/strategies/runtimes/alpha_mr_s01")
    text = "\n".join(path.read_text(encoding="utf-8") for path in runtime_dir.glob("*.py"))
    forbidden = [
        "binance",
        "execution_position",
        "CMD:OPEN",
        "CMD:CLOSE",
        "on_external_open_request",
    ]
    for token in forbidden:
        assert token not in text
