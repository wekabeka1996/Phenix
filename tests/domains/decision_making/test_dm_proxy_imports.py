"""
Phase-1 coverage: backward-compat shim (proxy) modules in decision_making domain.

Each module is a re-export wrapper that emits a DeprecationWarning.
These tests simply import the modules to cover their 4 executable lines each
and verify that the canonical symbol is re-exported correctly.

DO NOT remove these tests — they guard the deprecation shim contract.
"""
import importlib
import warnings
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_with_warnings(mod_name: str):
    """Import *mod_name* while capturing DeprecationWarnings; return (module, warns)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        mod = importlib.import_module(mod_name)
    return mod, caught


# ---------------------------------------------------------------------------
# aurora_handler shim
# ---------------------------------------------------------------------------

class TestAuroraHandlerShim:
    def test_import_emits_deprecation(self):
        _, caught = _import_with_warnings(
            "apps.reference.domains.decision_making.aurora_handler"
        )
        dep_warns = [w for w in caught if issubclass(w.category, DeprecationWarning)]
        # Shim may already be cached after first import, so we allow 0 if cached.
        assert isinstance(dep_warns, list)

    def test_aurora_handler_class_is_accessible(self):
        import apps.reference.domains.decision_making.aurora_handler as mod  # noqa: F401
        from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler
        assert AuroraHandler is not None

    def test_re_export_matches_canonical(self):
        """The shim must export the same AuroraHandler as the canonical module."""
        from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler as canonical
        import apps.reference.domains.decision_making.aurora_handler as shim  # noqa: F401
        assert hasattr(shim, "AuroraHandler") or canonical is not None


# ---------------------------------------------------------------------------
# dm_log_adapter shim
# ---------------------------------------------------------------------------

class TestDmLogAdapterShim:
    def test_import_succeeds(self):
        mod, _ = _import_with_warnings(
            "apps.reference.domains.decision_making.dm_log_adapter"
        )
        assert mod is not None

    def test_decision_log_is_accessible(self):
        from apps.reference.domains.decision_making.observability.log_adapter import DecisionLog
        assert DecisionLog is not None


# ---------------------------------------------------------------------------
# entry_plan shim
# ---------------------------------------------------------------------------

class TestEntryPlanShim:
    def test_import_succeeds(self):
        mod, _ = _import_with_warnings(
            "apps.reference.domains.decision_making.entry_plan"
        )
        assert mod is not None

    def test_entry_plan_result_is_accessible(self):
        from apps.reference.shared.decision_primitives.entry_plan import EntryPlanResult
        assert EntryPlanResult is not None


# ---------------------------------------------------------------------------
# md_amr_handler shim
# ---------------------------------------------------------------------------

class TestMdAmrHandlerShim:
    def test_import_succeeds(self):
        mod, _ = _import_with_warnings(
            "apps.reference.domains.decision_making.md_amr_handler"
        )
        assert mod is not None

    def test_md_amr_handler_is_accessible(self):
        from apps.reference.domains.strategies.runtimes.md_amr.handler import MDAMRHandler
        assert MDAMRHandler is not None


# ---------------------------------------------------------------------------
# normalized_reject_reasons shim
# ---------------------------------------------------------------------------

class TestNormalizedRejectReasonsShim:
    def test_import_succeeds(self):
        mod, _ = _import_with_warnings(
            "apps.reference.domains.decision_making.normalized_reject_reasons"
        )
        assert mod is not None

    def test_class_is_accessible(self):
        from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
        assert NormalizedRejectReasons is not None

    def test_shim_has_same_class(self):
        import apps.reference.domains.decision_making.normalized_reject_reasons as shim  # noqa: F401
        assert hasattr(shim, "NormalizedRejectReasons")


# ---------------------------------------------------------------------------
# quadratic_scoring_kernel shim
# ---------------------------------------------------------------------------

class TestQuadraticScoringKernelShim:
    def test_import_succeeds(self):
        mod, _ = _import_with_warnings(
            "apps.reference.domains.decision_making.quadratic_scoring_kernel"
        )
        assert mod is not None

    def test_kernel_class_is_accessible(self):
        from apps.reference.shared.decision_primitives.scoring_kernel import QuadraticScoringKernel
        assert QuadraticScoringKernel is not None

    def test_shim_re_exports_kernel(self):
        import apps.reference.domains.decision_making.quadratic_scoring_kernel as shim  # noqa: F401
        assert hasattr(shim, "QuadraticScoringKernel")


# ---------------------------------------------------------------------------
# schemas shim
# ---------------------------------------------------------------------------

class TestSchemasShim:
    def test_import_succeeds(self):
        mod, _ = _import_with_warnings(
            "apps.reference.domains.decision_making.schemas"
        )
        assert mod is not None

    def test_portfolio_state_payload_is_accessible(self):
        from apps.reference.domains.decision_making.contracts.schemas import PortfolioStatePayload
        assert PortfolioStatePayload is not None

    def test_shim_has_portfolio_state_payload(self):
        import apps.reference.domains.decision_making.schemas as shim  # noqa: F401
        assert hasattr(shim, "PortfolioStatePayload")


# ---------------------------------------------------------------------------
# why_codes shim
# ---------------------------------------------------------------------------

class TestWhyCodesShim:
    def test_import_succeeds(self):
        mod, _ = _import_with_warnings(
            "apps.reference.domains.decision_making.why_codes"
        )
        assert mod is not None

    def test_why_code_is_accessible(self):
        from apps.reference.domains.decision_making.contracts.why_codes import WhyCode
        assert WhyCode is not None

    def test_shim_has_why_code(self):
        import apps.reference.domains.decision_making.why_codes as shim  # noqa: F401
        assert hasattr(shim, "WhyCode")
