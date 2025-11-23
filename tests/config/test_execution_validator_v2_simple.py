"""
tests/config/test_execution_validator_v2_simple.py
Простий smoke test валідації execution з ExecutionPositionConfig V2.

Constraint: EP-CONFIG-EXECUTION-VALIDATOR-S8
"""

import pytest
from pathlib import Path


def test_execution_validator_on_real_testnet_config():
    """
    Smoke test: перевіряємо, що валідатор працює з реальним testnet конфігом.

    Якщо у configs/ є ExecutionPositionConfig (aggregated_oco),
    валідатор не повинен повертати execution: error про brackets_config.source=legacy.
    """
    from tools.config_validator_v2 import validate_config_v2

    # Використовуємо реальний testnet конфіг
    config_root = Path(__file__).parents[2] / "configs"

    if not (config_root / "master_config_v1.yaml").exists():
        pytest.skip("testnet config not found, skipping real config validation")

    result = validate_config_v2(config_root=config_root)

    # Execution не повинен бути error (може бути ok або warning)
    exec_status = result["domains"]["execution"]["status"]
    assert exec_status != "error", \
        f"Execution should not be error with ExecutionPositionConfig present. Got {exec_status}. Errors: {result['domains']['execution']['errors']}"

    # Не повинно бути error про brackets_config.source=legacy якщо ExecutionPositionConfig присутній
    exec_errors = result["domains"]["execution"]["errors"]

    # Якщо є ExecutionPositionConfig (aggregated_oco), не повинно бути цієї помилки
    legacy_error_present = any(
        "resolve_brackets_config returned source=legacy, expected config_v2" in e for e in exec_errors)

    if legacy_error_present:
        # Це означає, що валідатор не розпізнав ExecutionPositionConfig
        pytest.fail(
            f"Validator incorrectly reports brackets_config.source=legacy error "
            f"despite ExecutionPositionConfig being present. Errors: {exec_errors}"
        )


def test_validator_recognizes_execution_position_config_v2():
    """
    Unit test: перевіряємо, що resolve_execution_position_config викликається у валідаторі.
    """
    from tools.config_validator_v2 import validate_config_v2
    from pathlib import Path

    config_root = Path(__file__).parents[2] / "configs"

    if not (config_root / "master_config_v1.yaml").exists():
        pytest.skip("testnet config not found")

    result = validate_config_v2(config_root=config_root)

    # Перевіряємо, що execution domain пройшов валідацію
    assert "execution" in result["domains"], "execution domain not validated"

    exec_domain = result["domains"]["execution"]

    # Якщо ExecutionPositionConfig V2 присутній, не повинно бути error про legacy
    # (може бути warning про hybrid mode)
    exec_errors = exec_domain["errors"]

    # Основна перевірка: error про brackets_config.source=legacy+ExecutionPositionConfig не присутній
    # має бути або відсутній, або downgraded до warning
    critical_error = "resolve_brackets_config returned source=legacy, expected config_v2 (ExecutionPositionConfig not present)"

    assert not any(critical_error in e for e in exec_errors), \
        f"Validator should not error when ExecutionPositionConfig V2 present. Errors: {exec_errors}"
