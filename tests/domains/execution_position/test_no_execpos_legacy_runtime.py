import pytest
import yaml
from pathlib import Path
from unittest.mock import Mock, MagicMock

from apps.reference.domains.execution_position.runtime_factory import build_execution_runtime


class TestNoLegacyRuntime:
    """
    CI Guard to ensure ExecPosFSM and legacy runtime mode are not reintroduced.
    """

    def test_execpos_fsm_module_removed(self):
        """Ensure apps.reference.domains.execution_position.fsm does not exist or cannot be imported."""
        with pytest.raises(ImportError):
            import apps.reference.domains.execution_position.fsm

    def test_runtime_factory_rejects_legacy_mode(self):
        """Ensure runtime_factory raises ValueError for runtime_mode='legacy'."""
        config = Mock()
        config.to_dict.return_value = {
            "execution_position": {
                "runtime_mode": "legacy"
            }
        }

        # Should raise ValueError now, not return FSM
        with pytest.raises(ValueError, match="ExecPosFSM \(legacy mode\) has been removed"):
            build_execution_runtime(config, fsm=Mock())

    def test_runtime_factory_defaults_to_v2(self):
        """Ensure runtime_factory builds V2 by default."""
        config = Mock()
        config.to_dict.return_value = {}  # No runtime_mode

        runtime = build_execution_runtime(config, fsm=Mock())

        # Should be the V2 facade
        assert runtime.__class__.__name__ == "V2RuntimeFacade"
        assert runtime.runtime.__class__.__name__ == "ExecPosRuntimeV2"

    def test_config_does_not_contain_legacy_mode(self):
        """Scan execution.yaml to ensure runtime_mode: legacy is not present."""
        # Find config file relative to this test
        project_root = Path(__file__).parents[4]
        config_path = project_root / "config" / "domains" / "execution.yaml"

        if not config_path.exists():
            pytest.skip("execution.yaml not found")

        with open(config_path, "r") as f:
            content = yaml.safe_load(f)

        # Check if runtime_mode is present and set to legacy
        # It might be removed entirely (which is fine) or set to v2
        if "runtime_mode" in content:
            assert content["runtime_mode"] != "legacy", "Config contains forbidden 'runtime_mode: legacy'"

        # Also check raw text for commented out legacy instructions if we want to be strict,
        # but checking parsed yaml is the critical part.

    def test_legacy_module_removed(self):
        """Ensure legacy module has been completely removed."""
        with pytest.raises(ImportError):
            import apps.reference.domains.execution_position.legacy.fsm_manage
