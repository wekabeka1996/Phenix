"""
tests/config/test_execution_validator_v2_simple.py
Простий smoke test валідації execution з ExecutionPositionConfig V2.

Constraint: EP-CONFIG-EXECUTION-VALIDATOR-S8
"""

import pytest
from pathlib import Path


def test_execution_validator_on_real_testnet_config():
    """
    Smoke test: перевіряємо, що валідатор працює з V2 конфігом.
    """
    from tools.config_validator_v2 import validate_config_v2
    import tempfile
    import yaml
    import os
    from unittest.mock import patch

    # Create a temporary directory with a valid V2 config
    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)
        config_dir = project_root / "config"
        config_dir.mkdir()
        domains_dir = config_dir / "domains"
        domains_dir.mkdir()

        # Create execution.yaml with valid V2 config
        execution_config = {
            "manage": {
                "auto": True,
                "brackets": {
                    "aggregated_oco": {
                        "enabled": True,
                        "aggregated_only_mode": True,
                        "recalc_on_partial_close": True
                    }
                }
            }
        }
        (domains_dir / "execution.yaml").write_text(yaml.dump(execution_config))

        # Create dummy core.yaml to satisfy loader
        (config_dir / "core.yaml").write_text("env: testnet\n")

        # Patch AURORA_PROJECT_ROOT so ConfigLoader finds our temp config
        with patch.dict(os.environ, {"AURORA_PROJECT_ROOT": str(project_root)}):
            # We pass config_root as the project root, but ConfigLoader expects config_dir for legacy
            # However, for V2 it uses project_root/config.
            # validate_config_v2 calls load_config(config_root).
            # load_config passes it as config_dir.
            # But _load_config_v2 uses project_root/config.
            # So setting AURORA_PROJECT_ROOT is key.
            result = validate_config_v2(config_root=project_root)

        # Execution не повинен бути error
        exec_status = result["domains"]["execution"]["status"]
        assert exec_status != "error", \
            f"Execution should not be error with ExecutionPositionConfig present. Got {exec_status}. Errors: {result['domains']['execution']['errors']}"

        # Не повинно бути error про brackets_config.source=legacy
        exec_errors = result["domains"]["execution"]["errors"]
        legacy_error_present = any(
            "resolve_brackets_config returned source=legacy" in e for e in exec_errors)

        assert not legacy_error_present, \
            f"Validator incorrectly reports brackets_config.source=legacy error. Errors: {exec_errors}"


def test_validator_recognizes_execution_position_config_v2():
    """
    Unit test: перевіряємо, що resolve_execution_position_config викликається у валідаторі.
    """
    from tools.config_validator_v2 import validate_config_v2
    import tempfile
    import yaml
    import os
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as temp_dir:
        project_root = Path(temp_dir)
        config_dir = project_root / "config"
        config_dir.mkdir()
        domains_dir = config_dir / "domains"
        domains_dir.mkdir()

        # Create execution.yaml with valid V2 config
        execution_config = {
            "manage": {
                "auto": True,
                "brackets": {
                    "aggregated_oco": {
                        "enabled": True,
                        "aggregated_only_mode": True,
                        "recalc_on_partial_close": True
                    }
                }
            }
        }
        (domains_dir / "execution.yaml").write_text(yaml.dump(execution_config))
        (config_dir / "core.yaml").write_text("env: testnet\n")

        with patch.dict(os.environ, {"AURORA_PROJECT_ROOT": str(project_root)}):
            result = validate_config_v2(config_root=project_root)

        # Перевіряємо, що execution domain пройшов валідацію
        assert "execution" in result["domains"], "execution domain not validated"

        exec_domain = result["domains"]["execution"]
        exec_errors = exec_domain["errors"]

        critical_error = "resolve_brackets_config returned source=legacy, expected config_v2 (ExecutionPositionConfig not present)"

        assert not any(critical_error in e for e in exec_errors), \
            f"Validator should not error when ExecutionPositionConfig V2 present. Errors: {exec_errors}"
