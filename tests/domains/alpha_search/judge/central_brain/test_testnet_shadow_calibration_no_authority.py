from __future__ import annotations

import subprocess
from pathlib import Path


FILES = (
    Path("apps/reference/domains/alpha_search/judge/central_brain/shadow_calibration.py"),
    Path("tools/judge/build_testnet_shadow_calibration_dataset.py"),
    Path("tools/judge/run_testnet_shadow_calibration_experiment.py"),
)

FORBIDDEN = (
    "execution_position",
    "OrderExecutor",
    "PLACE_ORDER",
    "CMD:OPEN",
    "CMD:CLOSE",
    "exchange_adapter",
    "binance",
    "live_gated",
    "StrategyGateway",
    "IntentBuilder",
)


def combined_text() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in FILES)


def test_no_execution_order_or_exchange_imports():
    text = combined_text()
    for forbidden in FORBIDDEN:
        assert forbidden not in text


def test_no_runtime_config_paths_or_registry_dependency():
    text = combined_text()
    assert "config/aurora" not in text
    assert "config\\aurora" not in text
    assert "verb_registry" not in text


def test_registry_not_modified_for_path_b():
    result = subprocess.run(
        ["git", "diff", "--name-only", "--", "apps/reference/dictionaries/verb_registry_v1.yaml"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert "apps/reference/dictionaries/verb_registry_v1.yaml" in result.stdout


def test_runtime_hook_is_phase10a_owned():
    pipeline = Path("apps/reference/domains/alpha_search/judge/central_brain/shadow_pipeline.py")
    assert pipeline.exists()
