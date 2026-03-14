# Documentation Forensics Audit Report: Instruments Passport

**Date:** 2026-03-13
**Target Document:** config/docs/instruments_passport.md
**Auditor:** Principal Code Auditor / Documentation Forensics Engineer

## 1. Scope

This audit re-traced exactly one document: config/docs/instruments_passport.md.

The trace covered:

1. Loader wiring of `instruments.yaml` into `config.instruments`.
2. Typed contract for precision, execution, sizing, and flip fields.
3. Quantity normalization and exchange-constraint validation.
4. Leverage verification/bootstrap logic.
5. Margin-first sizing.
6. Flip orchestration.
7. Startup exchange-filter validation.

## 2. Files traced

### YAML
- config/aurora/instruments.yaml

### Pydantic / config contracts
- apps/reference/config_models.py

### Runtime consumers
- apps/reference/config_loader.py
- apps/reference/config_symbols.py
- apps/reference/main.py
- apps/reference/domains/execution_position/qty_normalizer.py
- apps/reference/domains/execution_position/fsm.py
- apps/reference/domains/execution_position/fsm_open.py
- apps/reference/domains/execution_position/fsm_manage.py
- apps/reference/domains/execution_position/leverage_service.py
- apps/reference/domains/execution_position/leverage_config.py
- apps/reference/domains/execution_position/bootstrapping/leverage_bootstrapper.py
- apps/reference/domains/execution_position/exposure_guard.py
- apps/reference/domains/decision_making/sizing_margin_first.py
- apps/reference/domains/decision_making/decision_making.py
- apps/reference/domains/exchange_filters/validator.py

### Tests
- tests/contracts/test_exchange_filters_validation.py
- tests/integration/test_startup_filters_wiring.py
- tests/domains/execution_position/test_task50_qty_normalizer.py
- tests/domains/decision_making/test_sizing_margin_first.py
- tests/domains/execution_position/test_exposure_guard_matrix_v1.py

## 3. Confirmed claims

1. `instruments.yaml` is loaded into root `config.instruments`.
2. `trading.instruments` is forbidden as deprecated duplicate config.
3. `step_size`, `min_qty`, and `min_notional` are actively enforced fail-closed in normalization and decision-making sizing checks.
4. `tick_size` is actively consumed in execution-position price quantization paths.
5. `margin_mode`, `target_leverage`, and `leverage_policy` are live execution fields.
6. `margin_pct` is active in margin-first sizing.
7. `flip.enabled` and `flip.hysteresis_mult` are part of the required typed instrument contract.
8. Exchange filter drift can fail startup when startup validation is enabled.
9. ExposureGuard resolves leverage from instruments SSOT without silent fallback.

## 4. Corrected claims

1. The old passport treated `symbol` too strongly as the instrument identity source; runtime primarily uses map keys.
2. The old passport described exchange filter matching like a blanket invariant without making the startup toggle explicit.
3. The old passport did not document current SSOT precedence between instruments execution leverage and legacy strategy-side leverage.
4. The old passport understated the fact that per-symbol flip config is required and fail-closed when global flip is on.
5. The old passport did not clearly mark `max_notional_utilization` as typed but unconsumed at runtime.
6. The old passport did not frame `instruments.yaml` as a broader multi-surface SSOT covering symbol registry, leverage, sizing, and flip orchestration together.

## 5. Removed stale claims

1. `instruments.<SYM>.symbol` as a hard validated identity constraint.
2. Strategy-side leverage as the effective execution bootstrap authority.

## 6. Added missing sections

1. Startup exchange-filter validation toggle semantics.
2. Leverage SSOT precedence and strategy mismatch warnings.
3. Flip contract fail-closed behavior.
4. Current configured snapshot for all active symbols.
5. Declared-but-unused status of `max_notional_utilization`.
6. Canonical symbol registry ownership by `config.instruments` keys.

## 7. Dead / legacy / declared-but-unused fields

1. `instruments.<SYM>.symbol` is largely duplicate metadata from a runtime identity perspective.
2. Strategy-side leverage values are legacy/stale if they disagree with instruments SSOT.
3. `execution.max_notional_utilization` is declared and validated but no traced runtime gate consumes it.

## 8. Final verdict

The instruments passport is now synchronized to current runtime behavior.

The key architectural correction is that `instruments.yaml` is not just a precision file. It is a root SSOT spanning symbol identity by map keys, exchange constraints, leverage and margin-mode enforcement, margin-first sizing, flip orchestration, and optional startup exchange-filter validation.

**Status: DONE**
