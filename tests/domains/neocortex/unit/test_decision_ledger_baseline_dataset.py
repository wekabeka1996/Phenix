from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
MODULE_PATH = (
    REPO_ROOT
    / "apps"
    / "reference"
    / "domains"
    / "neocortex"
    / "experiments"
    / "_decision_ledger_baseline.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "neocortex_decision_ledger_baseline", MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


def test_prepare_dataset_uses_synthetic_fallback_when_ledger_missing(
    tmp_path: Path,
) -> None:
    module = _load_module()

    result = module.prepare_dataset(
        ledger_path=tmp_path / "missing_decision_ledger_v1.jsonl",
        min_real_rows=5,
        synthetic_rows=5,
        seed=7,
    )

    assert result.metadata["ledger_exists"] is False
    assert result.metadata["used_synthetic_fallback"] is True
    assert result.metadata["synthetic_rows"] == 5
    assert "ledger_missing" in result.metadata["synthetic_reasons"]
    assert result.frame["source_kind"].eq("synthetic").all()
    assert result.frame["decision_ts_ms"].is_monotonic_increasing
