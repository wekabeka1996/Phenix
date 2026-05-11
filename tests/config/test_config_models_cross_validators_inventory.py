"""Cross-validator inventory test for ``AuroraConfig``.

CONFIG_MODELS Phase 0 (2026-04-18). Companion to the public-surface
manifest test. See [CONFIG_MODELS_ROADMAP.md](../../CONFIG_MODELS_ROADMAP.md)
sections 13.4 and 14 (Validation doctrine).

The 7 root cross-validators on ``AuroraConfig`` enforce Aurora-wide
invariants that span sub-trees of the assembly. Frozen boundary F2 of
the roadmap requires that they remain attached to ``AuroraConfig`` for
the lifetime of the decomposition initiative. This test pins the
inventory so that a future package cannot silently drop one.

Existing negative-path coverage (Phase 0 mapping):

| Validator                                       | Covered by |
|-------------------------------------------------|------------|
| validate_trading_mode_consistency               | tests/config/test_trading_mode_ssot.py |
| _activate_root_execution_alias                  | tests/config/test_execution_root_removal.py (fail-closed: split-brain + missing trading.execution) |
| _fail_closed_validate_aurora_tpsl_ssot          | tests/config/test_task53_numeric_params_reach_runtime.py |
| _validate_md_amr_assignments                    | tests/config/test_md_amr_package_c3_config_contract.py et al. |
| _validate_mean_reversion_assignments            | tests/config/test_mean_reversion_yaml_contract.py et al. |
| _validate_strategy_objective_regime_coverage    | tests/config/test_objective_engine_contracts.py |
| _validate_llm_strategy_contract                 | tests/config/test_llm_strategy_contract_fail_closed.py |

EX-REMOVE-ROOT-2026-05-09: _backcompat_root_execution_alias renamed to
_activate_root_execution_alias and converted from silent alias to fail-closed guard.
"""
from __future__ import annotations

from apps.reference.config_models import AuroraConfig

REQUIRED_CROSS_VALIDATORS = (
    "validate_trading_mode_consistency",
    "_activate_root_execution_alias",
    "_fail_closed_validate_aurora_tpsl_ssot",
    "_validate_md_amr_assignments",
    "_validate_mean_reversion_assignments",
    "_validate_strategy_objective_regime_coverage",
    "_validate_llm_strategy_contract",
)


def test_all_seven_root_cross_validators_present() -> None:
    missing = [
        name for name in REQUIRED_CROSS_VALIDATORS
        if not hasattr(AuroraConfig, name)
    ]
    assert not missing, (
        "AuroraConfig is missing one or more root cross-validators "
        "frozen by CONFIG_MODELS_ROADMAP boundary F2: "
        f"{missing}. They cannot be removed without an explicit roadmap "
        "addendum."
    )


def test_root_cross_validators_are_callable() -> None:
    non_callable = [
        name for name in REQUIRED_CROSS_VALIDATORS
        if not callable(getattr(AuroraConfig, name, None))
    ]
    assert not non_callable, (
        f"Root cross-validators present but not callable: {non_callable}"
    )
