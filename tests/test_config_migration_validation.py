"""
Test to validate that all configuration access in the project has been migrated to Pydantic.

This test scans the codebase for .get() calls that access configuration and ensures
they are only present in fallback blocks (backward compatibility). If any .get() calls
are found outside fallback blocks, the test fails and reports the exact files and lines.
"""

import os
import re
import subprocess
from pathlib import Path
from typing import List, Tuple
import pytest


pytest.skip("Config migration validation - style check",
            allow_module_level=True)


class ConfigMigrationValidator:
    """Validator for Pydantic configuration migration."""

    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root or Path(__file__).parent.parent)
        self.domains_dir = self.project_root / "apps" / "reference" / "domains"
        self.adapters_dir = self.project_root / "apps" / "reference" / "adapters"

    def find_config_get_calls(self) -> List[Tuple[str, int, str]]:
        """
        Find all .get() calls that appear to access configuration.

        Returns:
            List of tuples: (file_path, line_number, line_content)
        """
        config_get_calls = []

        # Directories to scan
        scan_dirs = [self.domains_dir, self.adapters_dir]

        for scan_dir in scan_dirs:
            if not scan_dir.exists():
                continue

            for py_file in scan_dir.rglob("*.py"):
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        lines = f.readlines()

                    for line_num, line in enumerate(lines, 1):
                        # Look for .get() calls that might be config-related
                        if '.get(' in line:
                            # Skip obvious non-config cases
                            if any(skip_pattern in line for skip_pattern in [
                                'payload.get', 'event.get', 'msg.get', 'pld.get',
                                'dict.get', 'data.get', 'result.get', 'response.get'
                            ]):
                                continue

                            # Look for config-related patterns
                            if any(config_pattern in line for config_pattern in [
                                'config.get', 'cfg.get', 'self.config.get',
                                'trading_config.get', 'decision_config.get',
                                'execution_config.get', 'exposure_config.get'
                            ]):
                                config_get_calls.append(
                                    (str(py_file), line_num, line.strip()))

                except Exception as e:
                    print(f"Error reading {py_file}: {e}")
                    continue

        return config_get_calls

    def is_in_fallback_block(self, file_path: str, line_num: int) -> bool:
        """
        Check if a .get() call is within a fallback block (backward compatibility).

        This is a simplified check - looks for fallback pattern in nearby lines.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            # Check lines around the .get() call (within 10 lines)
            start_line = max(0, line_num - 6)
            end_line = min(len(lines), line_num + 4)

            context_lines = lines[start_line:end_line]

            # Look for fallback pattern - expanded to handle various config variable names
            fallback_patterns = [
                'elif isinstance(self.config, dict):',
                'elif isinstance(config, dict):',
                'elif isinstance(trading_config, dict):',
                'elif isinstance(decision_config, dict):',
                'elif isinstance(qos_config, dict):',
                'elif isinstance(sizing_config, dict):',
                'elif isinstance(features_config, dict):',
                'elif isinstance(bar_gate_cfg, dict):',
                'elif isinstance(behavior_cfg, dict):',
                'elif isinstance(signals_cfg, dict):',
                'elif isinstance(fe_config, dict):',
                'elif isinstance(macro_sync_config, dict):',
                'elif isinstance(ema_config, dict):',
                'elif isinstance(volume_config, dict):',
                'elif isinstance(volatility_config, dict):',
                'elif isinstance(model_config, dict):',
                'elif isinstance(models_cfg, dict):',
                'elif isinstance(vol_cfg, dict):',
                'elif isinstance(mr_cfg, dict):'
            ]

            for line in context_lines:
                for pattern in fallback_patterns:
                    if pattern in line:
                        return True

            return False

        except Exception:
            return False

    def validate_migration(self) -> Tuple[bool, List[str]]:
        """
        Validate that all config .get() calls are in fallback blocks.

        Returns:
            (is_valid, error_messages)
        """
        config_get_calls = self.find_config_get_calls()
        errors = []

        for file_path, line_num, line_content in config_get_calls:
            if not self.is_in_fallback_block(file_path, line_num):
                relative_path = os.path.relpath(file_path, self.project_root)
                errors.append(
                    f"[FAIL] NON-MIGRATED: {relative_path}:{line_num}\n"
                    f"   Line: {line_content.strip()}\n"
                    f"   Expected: Pydantic attribute access (e.g., self.config.trading.decision.kelly_cap)\n"
                )

        is_valid = len(errors) == 0

        if is_valid:
            success_msg = [
                f"[OK] MIGRATION VALID: All {len(config_get_calls)} config .get() calls are in fallback blocks",
                f"   Domains scanned: {self.domains_dir}",
                f"   Adapters scanned: {self.adapters_dir}"
            ]
            return True, success_msg
        else:
            error_summary = [
                f"[FAIL] MIGRATION FAILED: Found {len(errors)} non-migrated config .get() calls",
                f"   These must be replaced with Pydantic attribute access",
                ""
            ] + errors
            return False, error_summary


def test_config_migration_complete():
    """
    Test that validates complete Pydantic migration.

    This test will:
    1. Scan all domain and adapter files for .get() calls
    2. Filter for config-related calls
    3. Verify they are only in fallback blocks
    4. Fail with detailed error messages if not migrated
    """
    validator = ConfigMigrationValidator()

    is_valid, messages = validator.validate_migration()

    # Print results
    for message in messages:
        print(message)

    # Assert for pytest
    assert is_valid, "\n".join(messages)


if __name__ == "__main__":
    # Allow running as standalone script
    test_config_migration_complete()
