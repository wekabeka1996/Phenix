# AGENT_REPORT_V1

## Executive Summary
R7O реализован как shadow-only пакет: добавлен конфиг-контракт и телеметрия percent-of-notional arm-кандидатов в `peak_giveback_snapshot`, без изменения live `edge_arm_usd=25.0`, `giveback_trigger_pct=50.0`, без новых close requests из shadow-ветки.

## Problem Framing
R7M/R7N показали, что фиксированный live arm-порог `25.0 USDT` недостижим на наблюдаемом профиле позиции. Цель R7O: добавить наблюдаемость percent-of-notional arm-кандидатов (`0.02`, `0.05`, `0.07`) без вмешательства в live контур.

## FACTS
- В конфиг-контракте `position_policy_sidecar` добавлен strict-блок `shadow_percent_notional_arm` (`enabled`, `candidate_pcts`) с `extra='forbid'` и валидацией только положительных percent-значений.
- В каноническом конфиге `config/aurora/domains.yaml` добавлен блок:
  - `enabled: true`
  - `candidate_pcts: [0.02, 0.05, 0.07]`
- В runtime Sidecar добавлен nested snapshot:
  - `peak_giveback_shadow_arms.percent_notional`
  - candidates содержат `candidate_pct`, `arm_threshold_usd`, `is_armed`, `first_arm_ts_ms`, `peak_edge_usd`, `giveback_pct`, `threshold_met_under_current_giveback_trigger_pct`, `would_trigger`, `state`, `null_reasons`.
- Формула arming threshold: `arm_threshold_usd = notional_usdt * candidate_pct / 100`.
- Notional считается как `abs(qty) * entry_price`.
- При отсутствии economics (`unrealized_pnl_usdt`) notional/threshold не синтезируются, выставляется explicit null reason.
- При отсутствии валидного notional выставляется explicit null reason.
- Общая схема `peak_giveback_snapshot_v1` расширена полем `peak_giveback_shadow_arms`.
- Схема `POSITION_POLICY_SIDECAR_MODE_ACTIVE` расширена блоком `shadow_percent_notional_arm` в `sidecar_config_snapshot`.

## INFERENCES
- Добавленная телеметрия полностью изолирована от live decision/action path, так как:
  - live `_evaluate_peak_giveback` и `_handle_peak_giveback_trigger` не принимают решения из `peak_giveback_shadow_arms`;
  - shadow-результат только сериализуется в snapshot.
- Риск silent drift между runtime payload и schema снижен: обновлены schema-backed тесты и payload contract tests.

## ASSUMPTIONS
- `candidate_pcts` трактуются как percent units (не ratio).
- `position_snapshot` содержит достаточно данных (`entry_price`, `position_qty`/`portfolio_position_amt`) для notional, иначе фиксируется null reason.

## UNKNOWNS
- Runtime-доказательство на длительном live-срезе (несколько дней/режимов) не входит в R7O и требует отдельного observation package.
- Экономическая полезность конкретных candidate bands в production не утверждается этим пакетом.

## Runtime Telemetry Semantics
- Top-level:
  - `peak_giveback_shadow_arms.percent_notional.enabled`
  - `candidate_unit=percent`
  - `giveback_trigger_pct` (текущий live trigger, только для shadow comparison)
  - `candidates[]`
- На candidate:
  - `arm_threshold_usd = abs(qty)*entry_price*candidate_pct/100`
  - `is_armed`: shadow-state only
  - `first_arm_ts_ms`: timestamp первого shadow arm
  - `peak_edge_usd`: shadow peak для этого candidate
  - `giveback_pct`: от shadow peak
  - `threshold_met_under_current_giveback_trigger_pct`: bool/null
  - `would_trigger`: bool/null (non-actionable)
  - `state`: explainable state label
  - `null_reasons`: fail-closed причины отсутствия вычисления

## No-Live-Behavior-Change Proof
- Live policy constants unchanged:
  - `edge_arm_usd = 25.0` (без retune)
  - `giveback_trigger_pct = 50.0` (без retune)
- Shadow snapshot не вызывает `CMD:POSITION_POLICY_SIDECAR_CLOSE_REQUEST`.
- Тестами подтверждено:
  - shadow threshold met не приводит к close request;
  - shadow arm не выставляет live `state.is_armed`;
  - live `state.peak_edge_usd` не мутируется shadow-веткой вне штатной live-логики.

## Files / Areas Touched
- `apps/reference/config/domains/execution_position.py`
- `apps/reference/config_models.py`
- `config/aurora/domains.yaml`
- `apps/reference/domains/execution_position/sidecar/position_policy_sidecar.py`
- `apps/reference/domains/execution_position/contract_layer/schemas/common/peak_giveback_snapshot_v1.json`
- `apps/reference/domains/execution_position/schemas/position_policy_sidecar_mode_active_v1.json`
- `tests/config/test_position_policy_sidecar_config_contract.py`
- `tests/config/test_execution_position_contracts.py`
- `tests/config/_artifacts/execution_position_contract.generated.json`
- `tests/contracts/test_position_policy_sidecar_contracts.py`
- `tests/domains/execution_position/test_position_policy_sidecar_peak_giveback.py`
- `tests/domains/execution_position/test_position_policy_sidecar_schema_refs.py`
- `tests/domains/execution_position/test_position_policy_sidecar.py`
- `tests/domains/execution_position/test_position_policy_sidecar_recommendation_dedup.py`
- `tests/domains/execution_position/test_portfolio_field_splitbrain_fix.py`

## Validation Performed
См. `R7O_TEST_OUTPUTS.md`.

## Residual Risk
- Основной остаточный риск: отсутствие runtime long-window доказательства в production telemetry. Это осознанно отложено в observation package.

## What Remains Unproven
- Не доказано, что какой-либо из candidate bands оптимален для future live tuning.
- Не доказана стабильность candidate-сигнатур на расширенном cross-symbol/cross-regime периоде.

## Minimal Safe Verdict
R7O безопасно готов как shadow-only observability слой и не меняет live execution behavior.
