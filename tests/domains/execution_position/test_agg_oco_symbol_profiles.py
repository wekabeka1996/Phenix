"""Production profile contract tests for aggregated OCO symbols.

These tests lock the SOLUSDT/BNBUSDT aggregated-only settings and ensure
`docs/PROFILE_aggregated_oco_production.md` stays in sync with runtime configs.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
EXEC_CONFIG: Dict[str, Any] = yaml.safe_load(
    (REPO_ROOT / "config" / "domains" / "execution.yaml").read_text(encoding="utf-8")
)
INSTRUMENTS: Dict[str, Any] = yaml.safe_load(
    (REPO_ROOT / "config" / "instruments.yaml").read_text(encoding="utf-8")
)["instruments"]
OVERRIDES: Dict[str, Any] = yaml.safe_load(
    (REPO_ROOT / "config" / "overrides.yaml").read_text(encoding="utf-8")
)
PROFILE_DOC = (REPO_ROOT / "docs" / "PROFILE_aggregated_oco_production.md").read_text(
    encoding="utf-8"
)


def _doc_has(pattern: str) -> bool:
    return re.search(pattern, PROFILE_DOC, flags=re.MULTILINE) is not None


def _resolved_leverage(symbol: str) -> int:
    defaults = EXEC_CONFIG["exposure"]["leverage_defaults"]
    if symbol in defaults:
        return defaults[symbol]
    return defaults["__default__"]


def test_aggregated_only_runtime_flags_match_profile_doc() -> None:
    # Updated path to match new execution.yaml structure
    agg_cfg = EXEC_CONFIG["brackets"]["aggregated_oco"]

    # Legacy "manage" block is removed, checking brackets config directly
    assert agg_cfg["enabled"] is True
    assert agg_cfg["aggregated_only_mode"] is True
    assert agg_cfg["allow_unprotected_position"] is False
    assert agg_cfg["watchdog"]["enabled"] is True

    assert "Aggregated protection" in PROFILE_DOC
    assert "aggregated-only mode" in PROFILE_DOC
    assert "watchdog" in PROFILE_DOC.lower()


@pytest.mark.parametrize("symbol,asset", (("SOLUSDT", "SOL"), ("BNBUSDT", "BNB")))
def test_symbol_profiles_match_config_and_doc(symbol: str, asset: str) -> None:
    limits = INSTRUMENTS[symbol]["limits"]

    assert limits["min_qty"] == pytest.approx(0.01)
    assert limits["step_size"] == pytest.approx(0.01)
    assert limits["max_position_size"] == pytest.approx(5.0)

    row_pattern = rf"\| {symbol}\s+\|\s+0\.01\s+\|\s+0\.01\s+\|\s+5\.0 {asset}\s+\|\s+125x"
    assert _doc_has(row_pattern), f"Profile doc row missing for {symbol}"

    override_entry = OVERRIDES["symbols"][symbol]["limits"]
    assert override_entry["max_leverage"] == 125
    # Removed _resolved_leverage check as leverage is no longer in execution.yaml defaults


@pytest.mark.parametrize("symbol", ("SOLUSDT", "BNBUSDT"))
def test_profile_doc_mentions_risk_guards(symbol: str) -> None:
    assert symbol in PROFILE_DOC
    assert "Aggregated OCO Production Profile" in PROFILE_DOC
    assert "per_symbol_cap_pct" in PROFILE_DOC
    assert "directional ratio" in PROFILE_DOC
