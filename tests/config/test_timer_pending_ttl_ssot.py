"""T3 Timer Governance: pending_ttl_sec SSOT enforcement.

Canonical source: domains.execution_position.exposure_guard.pending_ttl_sec
Noncanonical duplicates (pre-T3): system.yaml execution.exposure,
                                   trading.yaml trading.execution.exposure

These tests enforce:
1. The canonical value exists in domains.yaml with the correct value.
2. The noncanonical duplicates are absent from system.yaml and trading.yaml.
   (This test MUST FAIL before cleanup and PASS after.)
3. ExposureGuard reads pending_ttl_sec from ExposureGuardConfig (domains.yaml),
   not from ExposureConfig (trading/system YAML path).
4. ExposureConfig.pending_ttl_sec is no longer a required field, so the YAML
   keys can be safely omitted.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DOMAINS_YAML = REPO_ROOT / "config" / "aurora" / "domains.yaml"
SYSTEM_YAML = REPO_ROOT / "config" / "aurora" / "system.yaml"
TRADING_YAML = REPO_ROOT / "config" / "aurora" / "trading.yaml"

CANONICAL_VALUE = 90


def test_canonical_pending_ttl_sec_exists():
    """Canonical pending_ttl_sec must exist in domains.yaml at the correct path.

    SSOT: domains.execution_position.exposure_guard.pending_ttl_sec == 90
    """
    raw = yaml.safe_load(DOMAINS_YAML.read_text(encoding="utf-8"))

    # domains.yaml may have a top-level 'domains:' wrapper or not
    cfg = raw.get("domains", raw)

    value = (
        (cfg.get("execution_position") or {})
        .get("exposure_guard", {})
        .get("pending_ttl_sec")
    )

    assert value is not None, (
        "domains.yaml is missing execution_position.exposure_guard.pending_ttl_sec. "
        "This is the canonical SSOT path for pending_ttl_sec — do not remove it."
    )
    assert value == CANONICAL_VALUE, (
        f"domains.execution_position.exposure_guard.pending_ttl_sec = {value!r}, "
        f"expected {CANONICAL_VALUE!r}. "
        "Do not change the canonical value without updating this test."
    )


def test_noncanonical_yaml_paths_absent():
    """pending_ttl_sec MUST NOT appear in system.yaml or trading.yaml.

    This test FAILS before the T3 cleanup (duplicates still present) and
    PASSES after (duplicates removed).

    Canonical source: domains.execution_position.exposure_guard.pending_ttl_sec
    Noncanonical paths removed by T3:
      - system.yaml  execution.exposure.pending_ttl_sec      (AuroraConfig.execution.exposure)
      - trading.yaml trading.execution.exposure.pending_ttl_sec (AuroraConfig.trading.execution.exposure)
    """
    system_cfg = yaml.safe_load(SYSTEM_YAML.read_text(encoding="utf-8"))
    trading_cfg = yaml.safe_load(TRADING_YAML.read_text(encoding="utf-8"))

    violations: list[str] = []

    # system.yaml: execution.exposure.pending_ttl_sec
    system_exposure = (system_cfg.get("execution") or {}).get("exposure") or {}
    if "pending_ttl_sec" in system_exposure:
        violations.append(
            f"system.yaml: execution.exposure.pending_ttl_sec = "
            f"{system_exposure['pending_ttl_sec']!r}  [NONCANONICAL DUPLICATE]"
        )

    # trading.yaml: trading.execution.exposure.pending_ttl_sec
    trading_exposure = (
        (trading_cfg.get("trading") or {}).get("execution") or {}
    ).get("exposure") or {}
    if "pending_ttl_sec" in trading_exposure:
        violations.append(
            f"trading.yaml: trading.execution.exposure.pending_ttl_sec = "
            f"{trading_exposure['pending_ttl_sec']!r}  [NONCANONICAL DUPLICATE]"
        )

    assert not violations, (
        "Noncanonical pending_ttl_sec copies found. "
        "SSOT is domains.execution_position.exposure_guard.pending_ttl_sec. "
        "Remove these duplicates:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


def test_exposure_guard_consumes_canonical_value():
    """ExposureGuard reads pending_ttl_sec from ExposureGuardConfig (domains.yaml).

    The wiring must go through DomainConfigResolver.get_exposure_guard() which
    returns ExposureGuardConfig loaded from domains.execution_position.exposure_guard.
    ExposureGuard must NOT read pending_ttl_sec from ExposureConfig (legacy path).
    """
    import inspect

    from apps.reference.domains.execution_position.guards.exposure_guard import (
        ExposureGuard,
    )

    src = inspect.getsource(ExposureGuard.__init__)

    # Canonical assignment must appear: self.pending_ttl_sec = eg_config.pending_ttl_sec
    assert "eg_config.pending_ttl_sec" in src, (
        "ExposureGuard.__init__ does not assign pending_ttl_sec from eg_config. "
        "Expected: self.pending_ttl_sec = eg_config.pending_ttl_sec "
        "where eg_config = resolver.get_exposure_guard() (ExposureGuardConfig)."
    )

    # resolver.get_exposure_guard() must precede the assignment
    eg_config_pos = src.find("eg_config = resolver.get_exposure_guard()")
    pending_ttl_pos = src.find("eg_config.pending_ttl_sec")
    assert 0 <= eg_config_pos < pending_ttl_pos, (
        "resolver.get_exposure_guard() must be called before eg_config.pending_ttl_sec "
        "is accessed in ExposureGuard.__init__."
    )

    # Must NOT read from the legacy execution_cfg.exposure path for pending_ttl_sec
    assert "execution_cfg.exposure.pending_ttl_sec" not in src, (
        "ExposureGuard.__init__ reads pending_ttl_sec from execution_cfg.exposure "
        "(legacy noncanonical path). This must be removed."
    )


def test_noncanonical_config_field_is_not_required():
    """ExposureConfig.pending_ttl_sec must not be a required field.

    If ExposureConfig.pending_ttl_sec is Required (Field(...)), it forces
    system.yaml and trading.yaml to provide the noncanonical duplicate.
    After T3, it must be Optional (default=None) or fully removed.

    If the field has been fully removed from ExposureConfig, this test skips
    with a note that the cleanup is complete.
    """
    from apps.reference.config_models import ExposureConfig

    field_info = ExposureConfig.model_fields.get("pending_ttl_sec")

    if field_info is None:
        pytest.skip(
            "ExposureConfig.pending_ttl_sec has been fully removed from the model. "
            "T3 SSOT enforcement is complete."
        )
        return

    is_required = field_info.is_required()
    assert not is_required, (
        "ExposureConfig.pending_ttl_sec is still Required (Field(...)). "
        "This forces system.yaml / trading.yaml to provide the noncanonical duplicate. "
        "Fix: change to Optional[int] = Field(default=None) in config_models.py ExposureConfig."
    )
