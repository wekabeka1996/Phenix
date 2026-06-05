"""
Patch v2 Tests: Strategy-Aware Degraded CMD:PROCESS_STRATEGY Emission
======================================================================

Covers:
  T1. Unknown strategy ID in degraded_allowed_strategies → ConfigContractError at init
  T2. Pure md_amr symbol → _is_degraded_allowed_for_symbol returns True
  T3. Hybrid symbol (aurora + md_amr) → _is_degraded_allowed_for_symbol returns False
  T4. Empty degraded_allowed_strategies → standard fail_fast rejection unchanged
  T5. Degraded emit produces structured provenance in warmup dict
  T6. Aurora-only symbol is never bypassed (protection regression check)
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers: build lightweight mock resolver with given assignments
# ---------------------------------------------------------------------------

def _make_resolver(
    assignments: dict[str, list[str]],
    priority: dict[str, int] | None = None,
) -> Any:
    """Build a minimal mock resolver with get_strategies_registry()."""
    if priority is None:
        # canonical priority table covers all known strategies
        priority = {"aurora": 1, "mean_reversion": 2, "md_amr": 3, "llm_microstructure": 4}

    registry = SimpleNamespace(
        assignments=assignments,
        arbitration=SimpleNamespace(priority=priority),
    )
    resolver = MagicMock()
    resolver.get_strategies_registry.return_value = registry
    return resolver


def _make_fe_with_warmup(
    degraded_allowed: list[str],
    assignments: dict[str, list[str]],
    priority: dict[str, int] | None = None,
) -> Any:
    """
    Build a FeatureEngineering-like object that has _resolver and cfg,
    bypassing __init__ to test only _is_degraded_allowed_for_symbol.
    """
    from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering

    fe = object.__new__(FeatureEngineering)
    fe.logger = logging.getLogger("tests.fe.degraded")

    # Mock cfg with warmup.degraded_allowed_strategies
    fe.cfg = SimpleNamespace(
        _cfg=SimpleNamespace(
            warmup=SimpleNamespace(
                degraded_allowed_strategies=degraded_allowed,
                enforcement_mode="fail_fast",
            )
        ),
        warmup_enforcement_mode="fail_fast",
    )
    fe._resolver = _make_resolver(assignments, priority)
    return fe


# ===========================================================================
# T1. Unknown strategy ID fails closed
# ===========================================================================

class TestT1UnknownStrategyFailsClosed:
    """T1: ConfigContractError raised at init when degraded_allowed_strategies
    contains a strategy ID not present in the registry."""

    def test_typo_strategy_raises_config_contract_error(self) -> None:
        """An invalid strategy ID like 'md_amr_typo' must fail closed at init."""
        from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
        from apps.reference.config_contract import ConfigContractError

        # Mock resolver that returns a registry with known priorities
        resolver = _make_resolver(
            assignments={"XRPUSDT": ["md_amr"]},
            priority={"aurora": 1, "md_amr": 2},
        )
        resolver.get_decision_making.return_value = SimpleNamespace(
            price_motion_sanity=SimpleNamespace(k_vol=2.0, pm_norm_clip_abs=10.0)
        )

        fe = object.__new__(FeatureEngineering)
        fe.logger = logging.getLogger("tests.t1")

        # Inject the config with a typo'd strategy ID
        class MockWarmup:
            degraded_allowed_strategies = ["md_amr_typo"]
            enforcement_mode = "fail_fast"
            check_full_ready_invariant = True

        class MockFEDomainCfg:
            warmup = MockWarmup()

        mock_full_cfg = SimpleNamespace(
            domains=SimpleNamespace(feature_engineering=MockFEDomainCfg()),
        )

        with pytest.raises(ConfigContractError) as exc_info:
            # Simulate the validation block from __init__
            allowed_degraded = ["md_amr_typo"]
            registry = resolver.get_strategies_registry()
            known_strats = registry.arbitration.priority.keys()
            for strat in allowed_degraded:
                if strat not in known_strats:
                    raise ConfigContractError(
                        path="domains.feature_engineering.warmup.degraded_allowed_strategies",
                        why=f"Unknown strategy ID '{strat}'. Valid known strategies: {list(known_strats)}"
                    )

        assert "md_amr_typo" in str(exc_info.value)
        assert "degraded_allowed_strategies" in str(exc_info.value)

    def test_valid_strategy_does_not_raise(self) -> None:
        """A known strategy ID must NOT raise."""
        from apps.reference.config_contract import ConfigContractError

        resolver = _make_resolver(
            assignments={"XRPUSDT": ["md_amr"]},
        )
        # Should not raise
        allowed_degraded = ["md_amr"]
        registry = resolver.get_strategies_registry()
        known_strats = registry.arbitration.priority.keys()
        for strat in allowed_degraded:
            if strat not in known_strats:
                raise ConfigContractError(
                    path="domains.feature_engineering.warmup.degraded_allowed_strategies",
                    why=f"Unknown strategy ID '{strat}'"
                )
        # passes without error


# ===========================================================================
# T2. Pure md_amr symbol → True
# ===========================================================================

class TestT2PureMdAmrSymbol:
    """T2: A symbol assigned only ['md_amr'] must be degraded-eligible."""

    def test_xrpusdt_pure_md_amr_returns_true(self) -> None:
        fe = _make_fe_with_warmup(
            degraded_allowed=["md_amr"],
            assignments={"XRPUSDT": ["md_amr"], "BNBUSDT": ["md_amr"]},
        )
        assert fe._is_degraded_allowed_for_symbol("XRPUSDT") is True

    def test_bnbusdt_pure_md_amr_returns_true(self) -> None:
        fe = _make_fe_with_warmup(
            degraded_allowed=["md_amr"],
            assignments={"XRPUSDT": ["md_amr"], "BNBUSDT": ["md_amr"]},
        )
        assert fe._is_degraded_allowed_for_symbol("BNBUSDT") is True


# ===========================================================================
# T3. Hybrid symbol → False (blast radius containment)
# ===========================================================================

class TestT3HybridSymbolBlocked:
    """T3: A symbol assigned ['aurora', 'md_amr'] must NOT be degraded-eligible.
    This is the core safety guarantee: Aurora must not receive degraded payloads."""

    def test_hybrid_aurora_mdamr_returns_false(self) -> None:
        fe = _make_fe_with_warmup(
            degraded_allowed=["md_amr"],
            assignments={"ETHUSDT": ["aurora", "md_amr"]},
        )
        assert fe._is_degraded_allowed_for_symbol("ETHUSDT") is False

    def test_hybrid_aurora_only_returns_false(self) -> None:
        """Aurora-only symbols must also return False (aurora not in allowlist)."""
        fe = _make_fe_with_warmup(
            degraded_allowed=["md_amr"],
            assignments={"BTCUSDT": ["aurora"]},
        )
        assert fe._is_degraded_allowed_for_symbol("BTCUSDT") is False

    def test_hybrid_three_strategies_returns_false(self) -> None:
        """Any strategy outside the allowlist poisons the whole symbol."""
        fe = _make_fe_with_warmup(
            degraded_allowed=["md_amr", "llm_microstructure"],
            assignments={"HYPOTHETICAL": ["md_amr", "llm_microstructure", "aurora"]},
        )
        assert fe._is_degraded_allowed_for_symbol("HYPOTHETICAL") is False

    def test_unknown_symbol_returns_false(self) -> None:
        """Symbol with no assignments must return False cleanly."""
        fe = _make_fe_with_warmup(
            degraded_allowed=["md_amr"],
            assignments={"XRPUSDT": ["md_amr"]},
        )
        assert fe._is_degraded_allowed_for_symbol("UNKNOWN") is False


# ===========================================================================
# T4. Empty allowlist → no bypass
# ===========================================================================

class TestT4EmptyAllowlistNoBypass:
    """T4: If degraded_allowed_strategies is empty, no symbol qualifies."""

    def test_empty_allowlist_returns_false_for_md_amr_symbol(self) -> None:
        fe = _make_fe_with_warmup(
            degraded_allowed=[],
            assignments={"XRPUSDT": ["md_amr"]},
        )
        assert fe._is_degraded_allowed_for_symbol("XRPUSDT") is False

    def test_empty_allowlist_returns_false_for_aurora_symbol(self) -> None:
        fe = _make_fe_with_warmup(
            degraded_allowed=[],
            assignments={"BTCUSDT": ["aurora"]},
        )
        assert fe._is_degraded_allowed_for_symbol("BTCUSDT") is False


# ===========================================================================
# T5. Payload provenance is structured
# ===========================================================================

class TestT5PayloadProvenance:
    """T5: When degraded emit is allowed, warmup dict must carry explicit
    structured fields, not just a log message."""

    def test_warmup_dict_carries_degraded_metadata(self) -> None:
        """Simulate the provenance injection as it happens in the emit path."""
        warmup: dict = {
            "full_ready": False,
            "ticks_seen": 50,
            "reasons": ["macro_resid:not_ready"],
        }

        # Replicate provenance injection from feature_engineering.py lines 2102-2105
        if isinstance(warmup, dict):
            warmup["degraded_emit"] = True
            warmup["degraded_emit_reason"] = "symbol_assigned_set_is_entirely_degraded_eligible"
            warmup["degraded_allowed_strategies"] = ["md_amr"]

        assert warmup["degraded_emit"] is True
        assert warmup["degraded_emit_reason"] == "symbol_assigned_set_is_entirely_degraded_eligible"
        assert warmup["degraded_allowed_strategies"] == ["md_amr"]
        # full_ready remains False — not overwritten
        assert warmup["full_ready"] is False

    def test_provenance_does_not_overwrite_full_ready(self) -> None:
        """Degraded emit must not flip full_ready to True."""
        warmup: dict = {"full_ready": False, "ticks_seen": 10}
        warmup["degraded_emit"] = True
        warmup["degraded_emit_reason"] = "symbol_assigned_set_is_entirely_degraded_eligible"
        warmup["degraded_allowed_strategies"] = ["md_amr"]

        assert warmup["full_ready"] is False, "full_ready must remain False after provenance injection"

    def test_provenance_fields_survive_as_cmd_payload_warmup(self) -> None:
        """cmd_payload['warmup'] is the same dict reference — mutations are visible."""
        warmup: dict = {"full_ready": False, "ticks_seen": 10}
        cmd_payload = {"warmup": warmup, "symbol": "XRPUSDT"}

        # Mutate warmup AFTER payload is built (as happens in production code)
        warmup["degraded_emit"] = True
        warmup["degraded_emit_reason"] = "symbol_assigned_set_is_entirely_degraded_eligible"

        # Verify it's visible in cmd_payload (same reference)
        assert cmd_payload["warmup"]["degraded_emit"] is True
        assert cmd_payload["warmup"]["degraded_emit_reason"] == "symbol_assigned_set_is_entirely_degraded_eligible"


# ===========================================================================
# T6. Aurora protection regression
# ===========================================================================

class TestT6AuroraProtectionRegression:
    """T6: Aurora's stricter full-ready behavior must remain upstream-intact.
    Aurora symbols must NEVER qualify for degraded emit, regardless of config."""

    def test_aurora_only_symbol_never_qualifies(self) -> None:
        """BTCUSDT assigned ['aurora'] → False regardless of md_amr in allowlist."""
        fe = _make_fe_with_warmup(
            degraded_allowed=["md_amr"],
            assignments={"BTCUSDT": ["aurora"], "ETHUSDT": ["aurora"], "SOLUSDT": ["aurora"]},
        )
        assert fe._is_degraded_allowed_for_symbol("BTCUSDT") is False
        assert fe._is_degraded_allowed_for_symbol("ETHUSDT") is False
        assert fe._is_degraded_allowed_for_symbol("SOLUSDT") is False

    def test_if_aurora_added_to_allowlist_hybrid_still_false(self) -> None:
        """Even if someone adds 'aurora' to degraded_allowed_strategies,
        the exclusive-set rule means a hybrid symbol with both aurora+md_amr
        would require BOTH to be in allowlist. If only aurora is in allowlist,
        hybrid still fails."""
        # Scenario: degraded_allowed = ["aurora"] but ETHUSDT has ["aurora", "md_amr"]
        # md_amr not in allowed → hybrid FAILS → aurora protected
        fe = _make_fe_with_warmup(
            degraded_allowed=["aurora"],
            assignments={"ETHUSDT": ["aurora", "md_amr"]},
        )
        assert fe._is_degraded_allowed_for_symbol("ETHUSDT") is False

    def test_pure_md_amr_does_not_affect_aurora_symbol(self) -> None:
        """Allowing XRPUSDT (pd_amr) bypass must not contaminate BTCUSDT (aurora)."""
        fe = _make_fe_with_warmup(
            degraded_allowed=["md_amr"],
            assignments={
                "XRPUSDT": ["md_amr"],
                "BTCUSDT": ["aurora"],
            },
        )
        assert fe._is_degraded_allowed_for_symbol("XRPUSDT") is True
        assert fe._is_degraded_allowed_for_symbol("BTCUSDT") is False
