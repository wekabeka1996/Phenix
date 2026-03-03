"""
Contract test: FeatureEngineeringConfig startup validation (Tier 3).

FE-CONFIG-STARTUP-VALIDATION-01:
_validate_contracts() must eagerly surface broken config at __init__ time,
not lazily during the first trading tick. This is the "fail-fast at startup"
contract: better to crash at startup with a clear error than silently
trade on wrong parameters.

Tests verify:
  - _validate_contracts() passes with a valid config
  - _validate_contracts() raises ValueError when absorption is enabled but
    dp_cap_pct is absent
  - _validate_contracts() passes when absorption_mode == 'disabled'
  - __init__ actually calls _validate_contracts() (AST check)
"""
import ast
import pathlib
import pytest
from unittest.mock import MagicMock


def _make_minimal_inner_cfg() -> MagicMock:
    """
    Build a mock _cfg that satisfies all _validate_contracts() checks:
      - warmup_enforcement_mode  → works (fallback via try/except AttributeError)
      - readiness_registry_declared_keys → returns a real list
      - absorption_mode == 'disabled' → skip dp_cap_pct check
      - macro_resid_enabled == False → skip beta/mad checks
    """
    mock = MagicMock()
    # warmup — straightforward string return
    mock.warmup.enforcement_mode = "fail_fast"
    # readiness_registry — provide a real list so list() doesn't fail
    mock.readiness_registry.declared_keys = ["obi", "tfi", "delta_price"]
    # absorption disabled: None → absorption_mode returns "disabled"
    mock.absorption = None
    # macro_resid disabled → skip eager beta/mad check
    mock.macro_resid.enabled = False
    return mock


def _make_instance(inner_cfg: MagicMock):
    """Build FeatureEngineeringConfig bypassing _resolve_config."""
    from apps.reference.domains.feature_engineering.types import FeatureEngineeringConfig
    instance = object.__new__(FeatureEngineeringConfig)
    instance._cfg = inner_cfg
    return instance


class TestStartupValidationContracts:

    def test_validate_contracts_passes_with_valid_config(self):
        """_validate_contracts() must not raise when all required fields are present."""
        instance = _make_instance(_make_minimal_inner_cfg())
        # Should not raise
        instance._validate_contracts()

    def test_validate_contracts_raises_absorption_proxy_no_dp_cap(self):
        """
        When absorption mode='proxy' and dp_cap_pct is None, startup must fail
        with ValueError. Absence of dp_cap_pct causes division-by-zero in scoring.
        """
        inner = _make_minimal_inner_cfg()
        inner.absorption = MagicMock()
        inner.absorption.mode = "proxy"
        inner.absorption.dp_cap_pct = None   # missing required field

        instance = _make_instance(inner)
        with pytest.raises(ValueError, match="absorption.dp_cap_pct"):
            instance._validate_contracts()

    def test_validate_contracts_raises_absorption_full_no_dp_cap(self):
        """
        When absorption mode='full' and dp_cap_pct is None, startup must fail.
        Same root cause as proxy mode.
        """
        inner = _make_minimal_inner_cfg()
        inner.absorption = MagicMock()
        inner.absorption.mode = "full"
        inner.absorption.dp_cap_pct = None

        instance = _make_instance(inner)
        with pytest.raises(ValueError, match="absorption.dp_cap_pct"):
            instance._validate_contracts()

    def test_validate_contracts_passes_absorption_proxy_with_dp_cap(self):
        """When mode='proxy' and dp_cap_pct is set, startup must proceed normally."""
        inner = _make_minimal_inner_cfg()
        inner.absorption = MagicMock()
        inner.absorption.mode = "proxy"
        inner.absorption.dp_cap_pct = 0.02

        instance = _make_instance(inner)
        # Should not raise
        instance._validate_contracts()

    def test_validate_contracts_absorption_disabled_never_checks_dp_cap(self):
        """
        When absorption is disabled (mode='disabled' or None), dp_cap_pct is
        irrelevant and _validate_contracts must NOT raise even if it's missing.
        """
        inner = _make_minimal_inner_cfg()
        inner.absorption = None   # disabled path

        instance = _make_instance(inner)
        # Should not raise regardless of missing dp_cap_pct
        instance._validate_contracts()

    def test_validate_contracts_called_from_init(self):
        """
        AST guard: FeatureEngineeringConfig.__init__ must call _validate_contracts().
        If this call is removed, fail-fast behavior silently disappears.
        """
        source = pathlib.Path(
            "apps/reference/domains/feature_engineering/types.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            if node.name != "FeatureEngineeringConfig":
                continue
            for item in node.body:
                if not isinstance(item, ast.FunctionDef):
                    continue
                if item.name != "__init__":
                    continue
                init_src = "\n".join(ast.unparse(s) for s in item.body)
                assert "_validate_contracts" in init_src, (
                    "FeatureEngineeringConfig.__init__ does not call _validate_contracts(). "
                    "Tier 3 fail-fast startup validation has been removed — restore it."
                )
                return

        pytest.fail(
            "FeatureEngineeringConfig class or __init__ not found in types.py"
        )
