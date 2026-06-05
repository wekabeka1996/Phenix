"""Tests for Phase 14.2 FSM Split — Strangler Fig micro-extractions.

Validates that:
1. ExecPosFSM is still importable from original path (backward compat)
2. All 4 extraction sub-modules exist and are importable
3. Mixin methods are accessible on ExecPosFSM class via MRO
"""
import importlib

import pytest


class TestFSMSplitBackwardCompat:
    """Phase 14.2: Ensure ExecPosFSM imports are not broken."""

    def test_execposfsm_importable_from_original_path(self):
        """ExecPosFSM must remain importable from its original location."""
        mod = importlib.import_module(
            "apps.reference.domains.execution_position.fsm"
        )
        assert hasattr(mod, "ExecPosFSM"), (
            "ExecPosFSM class missing from fsm.py module"
        )


class TestSubModulesExist:
    """Phase 14.2: Verify all extraction sub-modules are importable."""

    @pytest.mark.parametrize(
        "module_path,class_name",
        [
            (
                "apps.reference.domains.execution_position.config_resolver",
                "ConfigResolverMixin",
            ),
            (
                "apps.reference.domains.execution_position.async_scheduling",
                "AsyncSchedulingMixin",
            ),
            (
                "apps.reference.domains.execution_position.adapter_init",
                "AdapterInitMixin",
            ),
            (
                "apps.reference.domains.execution_position.health_metrics",
                "HealthMetricsMixin",
            ),
        ],
    )
    def test_sub_module_importable(self, module_path: str, class_name: str):
        """Each extraction mixin module must be importable with its class."""
        mod = importlib.import_module(module_path)
        assert hasattr(mod, class_name), (
            f"{class_name} missing from {module_path}"
        )

    def test_execposfsm_inherits_mixins(self):
        """ExecPosFSM must inherit from all 4 extraction mixins."""
        from apps.reference.domains.execution_position.fsm import ExecPosFSM
        from apps.reference.domains.execution_position.config_resolver import ConfigResolverMixin
        from apps.reference.domains.execution_position.async_scheduling import AsyncSchedulingMixin
        from apps.reference.domains.execution_position.adapter_init import AdapterInitMixin
        from apps.reference.domains.execution_position.health_metrics import HealthMetricsMixin

        assert issubclass(ExecPosFSM, ConfigResolverMixin)
        assert issubclass(ExecPosFSM, AsyncSchedulingMixin)
        assert issubclass(ExecPosFSM, AdapterInitMixin)
        assert issubclass(ExecPosFSM, HealthMetricsMixin)
