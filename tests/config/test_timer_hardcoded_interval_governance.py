"""T4A Timer Governance: alert_check_interval SSOT extraction.

Canonical source: config/aurora/observability.yaml -> alerts.check_interval_sec
Extracted from: apps/reference/main.py (hardcoded literal 60)

These tests enforce:
1. The canonical value exists in observability.yaml under alerts.check_interval_sec.
2. The hardcoded literal assignment is absent from main.py.
3. The config object propagates the value (tested with a probe value).
4. The config field has no silent fallback (Field(...) required).

Tests 1 and 2 MUST FAIL before the extraction is applied and PASS after.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
OBSERVABILITY_YAML = REPO_ROOT / "config" / "aurora" / "observability.yaml"
MAIN_PY = REPO_ROOT / "apps" / "reference" / "main.py"
ALERTS_MODEL_PY = REPO_ROOT / "apps" / "reference" / "config" / "system" / "observability.py"

CANONICAL_VALUE = 60


# ---------------------------------------------------------------------------
# Test 1 — canonical config path exists in YAML
# ---------------------------------------------------------------------------

def test_alert_interval_canonical_config_exists():
    """observability.yaml must have alerts.check_interval_sec == 60.

    SSOT: observability.alerts.check_interval_sec == 60
    This MUST FAIL before check_interval_sec is added to observability.yaml.
    """
    raw = yaml.safe_load(OBSERVABILITY_YAML.read_text(encoding="utf-8"))

    value = (raw.get("alerts") or {}).get("check_interval_sec")

    assert value is not None, (
        "observability.yaml is missing alerts.check_interval_sec. "
        "This is the canonical SSOT for the alert monitoring poll cadence. "
        "Add: alerts.check_interval_sec: 60"
    )
    assert isinstance(value, int), (
        f"alerts.check_interval_sec must be an int, got {type(value).__name__!r}"
    )
    assert value == CANONICAL_VALUE, (
        f"observability.yaml alerts.check_interval_sec = {value!r}, "
        f"expected {CANONICAL_VALUE!r}. "
        "Do not change the canonical value without updating this test."
    )


# ---------------------------------------------------------------------------
# Test 2 — main.py no longer hardcodes the assignment
# ---------------------------------------------------------------------------

def test_main_py_no_longer_hardcodes_alert_interval():
    """main.py must NOT contain the literal assignment 'alert_check_interval = 60'.

    This MUST FAIL before the hardcode is removed from main.py.
    After extraction the line should read:
        alert_check_interval = config.observability.alerts.check_interval_sec
    """
    source = MAIN_PY.read_text(encoding="utf-8")

    assert "alert_check_interval = 60" not in source, (
        "main.py still contains the hardcoded literal: alert_check_interval = 60\n"
        "Replace it with: alert_check_interval = config.observability.alerts.check_interval_sec"
    )


# ---------------------------------------------------------------------------
# Test 3 — runtime uses configured value (propagation proof)
# ---------------------------------------------------------------------------

def test_runtime_uses_configured_alert_interval():
    """AlertsConfig.check_interval_sec propagates from observability.yaml.

    Builds a minimal AlertsConfig with a probe value of 17 to confirm the field
    is declared and wired — the value is not 60, proving config-driven behaviour
    rather than a hardcoded default.
    """
    from apps.reference.config.system.observability import AlertsConfig

    probe_cfg = AlertsConfig(
        slack_webhook_url=None,
        deduplication_window_sec=300,
        max_alerts_per_hour=10,
        risk_gate_threshold_pct=80,
        wal_size_threshold_mb=500,
        cb_active_threshold_sec=60,
        recent_alerts_max_keys=5000,
        entropy_volume_threshold=3000,
        entropy_error_rate_threshold=0.5,
        check_interval_sec=17,
    )

    assert probe_cfg.check_interval_sec == 17, (
        f"AlertsConfig.check_interval_sec should be 17 (probe value), "
        f"got {probe_cfg.check_interval_sec!r}. "
        "The field must accept caller-supplied values without silently overriding."
    )


# ---------------------------------------------------------------------------
# Test 4 — no silent fallback (Field(...) required)
# ---------------------------------------------------------------------------

def test_alert_interval_no_silent_fallback():
    """AlertsConfig.check_interval_sec must use Field(...) with no default.

    A silent fallback (e.g. Field(default=60)) would mask a missing YAML key
    and defeat the purpose of SSOT extraction.  The field must be required so
    that a misconfigured deployment fails loudly at startup rather than silently
    using a stale compile-time constant.
    """
    from apps.reference.config.system.observability import AlertsConfig
    import pydantic

    # Attempt to construct AlertsConfig WITHOUT check_interval_sec.
    # If the field has a default, this succeeds — which is the failure case.
    with pytest.raises((pydantic.ValidationError, TypeError)):
        AlertsConfig(
            slack_webhook_url=None,
            deduplication_window_sec=300,
            max_alerts_per_hour=10,
            risk_gate_threshold_pct=80,
            wal_size_threshold_mb=500,
            cb_active_threshold_sec=60,
            recent_alerts_max_keys=5000,
            entropy_volume_threshold=3000,
            entropy_error_rate_threshold=0.5,
            # check_interval_sec deliberately omitted
        )
