# Semantic Configuration Passport: `config/aurora/domains.yaml`

> **AUDIT SUMMARY**
> - **Document path:** `config/docs/domains_passport.md`
> - **Audit date:** 2026-03-18
> - **Audit mode:** Code-driven sync (auto-generated document)
> - **Major drifts found:** 
>   1. The `account_observer` domain has been completely removed from the codebase (TASK-ACCOUNT-OBSERVER-REACHABILITY-DELETE-01), matching its absence in this document.
>   2. `shadow_telemetry` and `objective_engine` domains are present in `domains.yaml` and actively used as Phase 2/3 subsystems, but are **missing from this auto-generated passport**.
>   3. `domains.decision_making.qos` and `domains.decision_making.directional_sanity` parameters match the SSOT definition.
>   4. `domains.feature_engineering.macro_resid` and `absorption` confirm Phase 9.
> - **Overall confidence:** HIGH (with known generated omissions noted)

Цей документ описує **`domains.yaml` як Active SSOT**: доменні параметри, які реально читаються runtime-кодом як `config.domains.*`.

## SSOT Supremacy — доказ трасуванням
- **Завантаження тільки з `domains.yaml`:** `apps/reference/config_loader.py:286` (CFG-DOMAINS-STEP-01) мержить `domains.yaml` у root `config.domains` і **забороняє** `trading.domains`.
- **Resolver читає лише canonical шлях:** `apps/reference/domain_config.py:79` (`DomainConfigResolver._resolve_domains`) **не має fallback** на `trading.domains` (fail-closed).
- **Депрекейт і fail-fast для дублювань:** `apps/reference/config_loader.py:904` забороняє `feature_engineering` у `trading.yaml` (SSOT тільки тут).
- **Market Data не належить `domains.yaml`:** у `domains.yaml` **немає** домену `market_data`; runtime читає налаштування market data з `config.trading.market_data.*` (тобто SSOT для market_data — `trading.yaml`, не `domains.yaml`). (`apps/reference/domains/market_data/market_data_connector.py:78`)

**Дата генерації:** `2026-02-03`  
**Leaf keys (включно з пустими мапами):** `217`

---
## Domain: `debug`
### `domains.debug.disable_daily_loss_limit`
- **Type:** `bool`
- **Logic Owner:** `debug`
- **Code Reference:** apps/reference/config_loader.py:1048 (func: load_config validation) ; apps/reference/domains/risk_management/risk_management.py:74 (RiskManagement.__init__)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.debug.disable_positions_stale_gate`
- **Type:** `bool`
- **Logic Owner:** `debug`
- **Code Reference:** apps/reference/config_loader.py:1048 (func: load_config validation) ; apps/reference/domains/risk_management/risk_management.py:74 (RiskManagement.__init__)
- **Mathematical/Architectural Role:**
    > Intended DEV/SHADOW override to bypass portfolio-freshness gate.
    > **No runtime consumer found**: flag is validated (and forbidden in live) but not checked by DecisionMaking/ExecutionPosition gates.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **UNKNOWN** (no runtime consumer or only logged)

---
## Domain: `decision_making`
Цей домен задає **гейти безпеки** (directional/price-motion), QoS та SSOT-параметри сайзингу.
### `domains.decision_making.arming.max_attempts`
- **Type:** `int`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:305 (DecisionMaking.__init__) ; apps/reference/main.py:1205 (RetryScheduler wiring)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше повторних спроб/довше чекання перед відмовою.
    - 🔽 **Too Low:** Lower ⇒ швидше 'give up' (менше шансів на recovery при тимчасових збоях).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.arming.require_regime_warmup`
- **Type:** `bool`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:305 (DecisionMaking.__init__) ; apps/reference/main.py:1205 (RetryScheduler wiring)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.arming.retry_backoff_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:305 (DecisionMaking.__init__) ; apps/reference/main.py:1205 (RetryScheduler wiring)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.bar_gating.bar_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:333 (DecisionMaking.__init__)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.bar_gating.enable`
- **Type:** `bool`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:333 (DecisionMaking.__init__)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.behavior_fsm.enable`
- **Type:** `bool`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:2299 (func: on_regime)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.behavior_fsm.high_vol_multiplier`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:2299 (func: on_regime)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.behavior_fsm.low_vol_multiplier`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:2299 (func: on_regime)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.degraded_context_critical_keys`
- **Type:** `list`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:246 (DecisionMaking.__init__) ; apps/reference/domains/decision_making/decision_making.py:3630 (func: _degraded_context_gate_should_defer)
- **Mathematical/Architectural Role:**
    > List/allowlist that influences readiness and computation coverage.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший список ⇒ більше coverage/строгіша ready-умова/більше навантаження.
    - 🔽 **Too Low:** Менший список ⇒ простіше/легше, але менше coverage.
- **Invariant/Constraints:** List content must match expected schema; empty lists may mean 'no overrides' or can break readiness if treated as required.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.degraded_context_critical_keys_by_strategy`
- **Type:** `object`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:246 (DecisionMaking.__init__) ; apps/reference/domains/decision_making/decision_making.py:3630 (func: _degraded_context_gate_should_defer)
- **Mathematical/Architectural Role:**
    > Mapping of overrides/registry; empty means no overrides.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більше overrides ⇒ більше специфічної поведінки.
    - 🔽 **Too Low:** Порожньо ⇒ глобальні дефолти/без overrides.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.directional_sanity.consecutive_bars`
- **Type:** `int`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/config_loader.py:1075 (func: _validate_directional_sanity_for_live) ; apps/reference/domains/decision_making/decision_making.py:2805 (safety gate)
- **Mathematical/Architectural Role:**
    > Directional sanity gate: denies opening trades when recent `delta_price` does not confirm trend.
    > Uses `consecutive_bars` and `min_abs_delta_price` as noise filter; compares `effective_confidence` to `min_confidence`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.directional_sanity.enabled`
- **Type:** `bool`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/config_loader.py:1075 (func: _validate_directional_sanity_for_live) ; apps/reference/domains/decision_making/decision_making.py:2805 (safety gate)
- **Mathematical/Architectural Role:**
    > Directional sanity gate: denies opening trades when recent `delta_price` does not confirm trend.
    > Uses `consecutive_bars` and `min_abs_delta_price` as noise filter; compares `effective_confidence` to `min_confidence`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.directional_sanity.min_abs_delta_price`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/config_loader.py:1075 (func: _validate_directional_sanity_for_live) ; apps/reference/domains/decision_making/decision_making.py:2805 (safety gate)
- **Mathematical/Architectural Role:**
    > Directional sanity gate: denies opening trades when recent `delta_price` does not confirm trend.
    > Uses `consecutive_bars` and `min_abs_delta_price` as noise filter; compares `effective_confidence` to `min_confidence`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.directional_sanity.min_confidence`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/config_loader.py:1075 (func: _validate_directional_sanity_for_live) ; apps/reference/domains/decision_making/decision_making.py:2805 (safety gate)
- **Mathematical/Architectural Role:**
    > Directional sanity gate: denies opening trades when recent `delta_price` does not confirm trend.
    > Uses `consecutive_bars` and `min_abs_delta_price` as noise filter; compares `effective_confidence` to `min_confidence`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.directional_sanity.min_regime_confidence`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:2823 (regime confidence gate) ; apps/reference/domains/decision_making/decision_making.py:2841 (reject emission)
- **Mathematical/Architectural Role:**
    > Directional sanity gate: блокує відкриття угод, якщо `regime_confidence` нижче порогу (noise filter).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше блокувань у low/mid-confidence режимах, менше входів.
    - 🔽 **Too Low:** Lower ⇒ більше входів у шумних або невизначених режимах.
- **Invariant/Constraints:** `0.0` вимикає gate; `None`/missing `regime_confidence` трактується як нижче порогу.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.entry_plan.atr_period`
- **Type:** `int`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1104 (func: _on_strategy_signal_gateway) ; apps/reference/domains/decision_making/entry_plan.py:93 (func: EntryPlan.compute)
- **Mathematical/Architectural Role:**
    > Lookback/buffer window length; larger windows smooth more but require more warmup.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.entry_plan.enabled`
- **Type:** `bool`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1104 (func: _on_strategy_signal_gateway) ; apps/reference/domains/decision_making/entry_plan.py:93 (func: EntryPlan.compute)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.entry_plan.entry_k_atr`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1104 (func: _on_strategy_signal_gateway) ; apps/reference/domains/decision_making/entry_plan.py:93 (func: EntryPlan.compute)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.entry_plan.obi_missing_policy`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1104 (func: _on_strategy_signal_gateway) ; apps/reference/domains/decision_making/entry_plan.py:93 (func: EntryPlan.compute)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш permissive значення ⇒ ширша поведінка.
    - 🔽 **Too Low:** Більш strict значення ⇒ жорсткіша поведінка.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.entry_plan.obi_mod_clamp_max`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1104 (func: _on_strategy_signal_gateway) ; apps/reference/domains/decision_making/entry_plan.py:93 (func: EntryPlan.compute)
- **Mathematical/Architectural Role:**
    > Clamping/capping parameter to limit outliers and avoid unstable math.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ ширший допустимий діапазон (менше clamp/not_ready).
    - 🔽 **Too Low:** Lower ⇒ жорсткіший bound (більше clamp/not_ready).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.entry_plan.obi_mod_clamp_min`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1104 (func: _on_strategy_signal_gateway) ; apps/reference/domains/decision_making/entry_plan.py:93 (func: EntryPlan.compute)
- **Mathematical/Architectural Role:**
    > Clamping/capping parameter to limit outliers and avoid unstable math.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ ширший допустимий діапазон (менше clamp/not_ready).
    - 🔽 **Too Low:** Lower ⇒ жорсткіший bound (більше clamp/not_ready).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.entry_plan.obi_weight`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1104 (func: _on_strategy_signal_gateway) ; apps/reference/domains/decision_making/entry_plan.py:93 (func: EntryPlan.compute)
- **Mathematical/Architectural Role:**
    > Scalar weight in a composite metric (higher ⇒ more influence).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ цей терм домінує у метриці.
    - 🔽 **Too Low:** Lower ⇒ цей терм менш впливовий.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.entry_plan.require_atr`
- **Type:** `bool`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1104 (func: _on_strategy_signal_gateway) ; apps/reference/domains/decision_making/entry_plan.py:93 (func: EntryPlan.compute)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.entry_plan.sl_k_atr`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1104 (func: _on_strategy_signal_gateway) ; apps/reference/domains/decision_making/entry_plan.py:93 (func: EntryPlan.compute)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.entry_plan.tp_k_atr`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1104 (func: _on_strategy_signal_gateway) ; apps/reference/domains/decision_making/entry_plan.py:93 (func: EntryPlan.compute)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.fail_closed_on_degraded_context`
- **Type:** `bool`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:246 (DecisionMaking.__init__) ; apps/reference/domains/decision_making/decision_making.py:3630 (func: _degraded_context_gate_should_defer)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.features.ttl_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:998 (TTL gate in _on_strategy_signal_gateway)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.flip.enabled`
- **Type:** `bool`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1901 (func: _get_flip_config)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.position_sizing.liquidity_based_cap_usd`
- **Type:** `int` *(USD/USDT)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:277 (DecisionMaking.__init__) ; apps/reference/domains/decision_making/sizing_margin_first.py:32 (func: compute_notional_target)
- **Mathematical/Architectural Role:**
    > Global SSOT knobs for margin-first sizing:
    > - `liquidity_based_cap_usd` caps `notional_target` (global notional cap).
    > - `min_position_size_usd` is a post-rounding minimum notional filter (reject if below).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ ширший допустимий діапазон (менше clamp/not_ready).
    - 🔽 **Too Low:** Lower ⇒ жорсткіший bound (більше clamp/not_ready).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.position_sizing.min_position_size_usd`
- **Type:** `int` *(USD/USDT)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:277 (DecisionMaking.__init__) ; apps/reference/domains/decision_making/sizing_margin_first.py:32 (func: compute_notional_target)
- **Mathematical/Architectural Role:**
    > Global SSOT knobs for margin-first sizing:
    > - `liquidity_based_cap_usd` caps `notional_target` (global notional cap).
    > - `min_position_size_usd` is a post-rounding minimum notional filter (reject if below).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.price_motion_sanity.bleed_threshold_norm`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/config_loader.py:1112 (func: _validate_price_motion_sanity_for_live) ; apps/reference/domains/feature_engineering/feature_engineering.py:106 (FeatureEngineering.__init__)
- **Mathematical/Architectural Role:**
    > Price-motion sanity SSOT used in TWO places:
    > 1) FeatureEngineering computes `pm_norm_*` using `k_vol` and `pm_norm_clip_abs`.
    > 2) DecisionMaking denies entries when `pm_norm` breaches thresholds on configured windows.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ gate looser (більше проходів).
    - 🔽 **Too Low:** Lower ⇒ gate stricter (більше блоків).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.price_motion_sanity.bleed_window_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/config_loader.py:1112 (func: _validate_price_motion_sanity_for_live) ; apps/reference/domains/feature_engineering/feature_engineering.py:106 (FeatureEngineering.__init__)
- **Mathematical/Architectural Role:**
    > Price-motion sanity SSOT used in TWO places:
    > 1) FeatureEngineering computes `pm_norm_*` using `k_vol` and `pm_norm_clip_abs`.
    > 2) DecisionMaking denies entries when `pm_norm` breaches thresholds on configured windows.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.price_motion_sanity.enabled`
- **Type:** `bool`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/config_loader.py:1112 (func: _validate_price_motion_sanity_for_live) ; apps/reference/domains/feature_engineering/feature_engineering.py:106 (FeatureEngineering.__init__)
- **Mathematical/Architectural Role:**
    > Price-motion sanity SSOT used in TWO places:
    > 1) FeatureEngineering computes `pm_norm_*` using `k_vol` and `pm_norm_clip_abs`.
    > 2) DecisionMaking denies entries when `pm_norm` breaches thresholds on configured windows.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.price_motion_sanity.flash_threshold_norm`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/config_loader.py:1112 (func: _validate_price_motion_sanity_for_live) ; apps/reference/domains/feature_engineering/feature_engineering.py:106 (FeatureEngineering.__init__)
- **Mathematical/Architectural Role:**
    > Price-motion sanity SSOT used in TWO places:
    > 1) FeatureEngineering computes `pm_norm_*` using `k_vol` and `pm_norm_clip_abs`.
    > 2) DecisionMaking denies entries when `pm_norm` breaches thresholds on configured windows.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ gate looser (більше проходів).
    - 🔽 **Too Low:** Lower ⇒ gate stricter (більше блоків).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.price_motion_sanity.flash_window_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/config_loader.py:1112 (func: _validate_price_motion_sanity_for_live) ; apps/reference/domains/feature_engineering/feature_engineering.py:106 (FeatureEngineering.__init__)
- **Mathematical/Architectural Role:**
    > Price-motion sanity SSOT used in TWO places:
    > 1) FeatureEngineering computes `pm_norm_*` using `k_vol` and `pm_norm_clip_abs`.
    > 2) DecisionMaking denies entries when `pm_norm` breaches thresholds on configured windows.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.price_motion_sanity.k_vol`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/config_loader.py:1112 (func: _validate_price_motion_sanity_for_live) ; apps/reference/domains/feature_engineering/feature_engineering.py:106 (FeatureEngineering.__init__)
- **Mathematical/Architectural Role:**
    > Price-motion sanity SSOT used in TWO places:
    > 1) FeatureEngineering computes `pm_norm_*` using `k_vol` and `pm_norm_clip_abs`.
    > 2) DecisionMaking denies entries when `pm_norm` breaches thresholds on configured windows.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.price_motion_sanity.pm_norm_clip_abs`
- **Type:** `float`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/config_loader.py:1112 (func: _validate_price_motion_sanity_for_live) ; apps/reference/domains/feature_engineering/feature_engineering.py:106 (FeatureEngineering.__init__)
- **Mathematical/Architectural Role:**
    > Price-motion sanity SSOT used in TWO places:
    > 1) FeatureEngineering computes `pm_norm_*` using `k_vol` and `pm_norm_clip_abs`.
    > 2) DecisionMaking denies entries when `pm_norm` breaches thresholds on configured windows.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ ширший допустимий діапазон (менше clamp/not_ready).
    - 🔽 **Too Low:** Lower ⇒ жорсткіший bound (більше clamp/not_ready).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.price_motion_sanity.require_bleed_ready`
- **Type:** `bool`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/config_loader.py:1112 (func: _validate_price_motion_sanity_for_live) ; apps/reference/domains/feature_engineering/feature_engineering.py:106 (FeatureEngineering.__init__)
- **Mathematical/Architectural Role:**
    > Price-motion sanity SSOT used in TWO places:
    > 1) FeatureEngineering computes `pm_norm_*` using `k_vol` and `pm_norm_clip_abs`.
    > 2) DecisionMaking denies entries when `pm_norm` breaches thresholds on configured windows.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.qos.apply_to_strategies`
- **Type:** `list[string]`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1277 (func: _qos_allow)
- **Mathematical/Architectural Role:**
    > QoS gate (anti-spam / rate-limit) applied in Strategy Signal Gateway:
    > - exposure cooldown (`exposure_block_cooldown_sec`)
    > - per-symbol cooldown (`symbol_cooldown_sec`, with per-instrument override in strategies)
    > - max intents per minute (`max_intents_per_minute_per_symbol`)
    > Behavior depends on `mode`/`enforce`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший список ⇒ більше coverage/строгіша ready-умова/більше навантаження.
    - 🔽 **Too Low:** Менший список ⇒ простіше/легше, але менше coverage.
- **Invariant/Constraints:** List content must match expected schema; empty lists may mean 'no overrides' or can break readiness if treated as required.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.qos.enforce`
- **Type:** `bool`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1277 (func: _qos_allow)
- **Mathematical/Architectural Role:**
    > QoS gate (anti-spam / rate-limit) applied in Strategy Signal Gateway:
    > - exposure cooldown (`exposure_block_cooldown_sec`)
    > - per-symbol cooldown (`symbol_cooldown_sec`, with per-instrument override in strategies)
    > - max intents per minute (`max_intents_per_minute_per_symbol`)
    > Behavior depends on `mode`/`enforce`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.qos.exposure_block_cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1277 (func: _qos_allow)
- **Mathematical/Architectural Role:**
    > QoS gate (anti-spam / rate-limit) applied in Strategy Signal Gateway:
    > - exposure cooldown (`exposure_block_cooldown_sec`)
    > - per-symbol cooldown (`symbol_cooldown_sec`, with per-instrument override in strategies)
    > - max intents per minute (`max_intents_per_minute_per_symbol`)
    > Behavior depends on `mode`/`enforce`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.qos.max_intents_per_minute_per_symbol`
- **Type:** `int`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1277 (func: _qos_allow)
- **Mathematical/Architectural Role:**
    > QoS gate (anti-spam / rate-limit) applied in Strategy Signal Gateway:
    > - exposure cooldown (`exposure_block_cooldown_sec`)
    > - per-symbol cooldown (`symbol_cooldown_sec`, with per-instrument override in strategies)
    > - max intents per minute (`max_intents_per_minute_per_symbol`)
    > Behavior depends on `mode`/`enforce`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.qos.mode`
- **Type:** `string`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1277 (func: _qos_allow)
- **Mathematical/Architectural Role:**
    > QoS gate (anti-spam / rate-limit) applied in Strategy Signal Gateway:
    > - exposure cooldown (`exposure_block_cooldown_sec`)
    > - per-symbol cooldown (`symbol_cooldown_sec`, with per-instrument override in strategies)
    > - max intents per minute (`max_intents_per_minute_per_symbol`)
    > Behavior depends on `mode`/`enforce`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш permissive значення ⇒ ширша поведінка.
    - 🔽 **Too Low:** Більш strict значення ⇒ жорсткіша поведінка.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.qos.symbol_cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:1277 (func: _qos_allow)
- **Mathematical/Architectural Role:**
    > QoS gate (anti-spam / rate-limit) applied in Strategy Signal Gateway:
    > - exposure cooldown (`exposure_block_cooldown_sec`)
    > - per-symbol cooldown (`symbol_cooldown_sec`, with per-instrument override in strategies)
    > - max intents per minute (`max_intents_per_minute_per_symbol`)
    > Behavior depends on `mode`/`enforce`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.risk_gate.min_intents_for_check`
- **Type:** `int`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3860 (func: _check_and_emit_risk_gate_alert)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.risk_gate.threshold_pct_production`
- **Type:** `float` *(percent)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3860 (func: _check_and_emit_risk_gate_alert)
- **Mathematical/Architectural Role:**
    > Threshold for a gate/health check; crossing changes allow/deny behavior.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ gate looser (більше проходів).
    - 🔽 **Too Low:** Lower ⇒ gate stricter (більше блоків).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.risk_gate.threshold_pct_testnet`
- **Type:** `float` *(percent)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3860 (func: _check_and_emit_risk_gate_alert)
- **Mathematical/Architectural Role:**
    > Threshold for a gate/health check; crossing changes allow/deny behavior.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ gate looser (більше проходів).
    - 🔽 **Too Low:** Lower ⇒ gate stricter (більше блоків).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.risk_skew.defer_cooldown_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:701 (risk skew gate) ; apps/reference/domains/decision_making/decision_making.py:4309 (func: _get_risk_skew_config)
- **Mathematical/Architectural Role:**
    > Risk-skew guard: compares timestamps of latest risk assessment vs latest features:
    > `skew_sec = abs(features_ts - risk_ts)/1000` and deny/defer if `skew_sec > max_skew_sec`.
    > Uses `defer_*` counters/window to escalate to NO_TRADE_UNTIL_REFRESH.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.risk_skew.defer_window_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:701 (risk skew gate) ; apps/reference/domains/decision_making/decision_making.py:4309 (func: _get_risk_skew_config)
- **Mathematical/Architectural Role:**
    > Risk-skew guard: compares timestamps of latest risk assessment vs latest features:
    > `skew_sec = abs(features_ts - risk_ts)/1000` and deny/defer if `skew_sec > max_skew_sec`.
    > Uses `defer_*` counters/window to escalate to NO_TRADE_UNTIL_REFRESH.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.risk_skew.max_defer_count`
- **Type:** `int`
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:701 (risk skew gate) ; apps/reference/domains/decision_making/decision_making.py:4309 (func: _get_risk_skew_config)
- **Mathematical/Architectural Role:**
    > Risk-skew guard: compares timestamps of latest risk assessment vs latest features:
    > `skew_sec = abs(features_ts - risk_ts)/1000` and deny/defer if `skew_sec > max_skew_sec`.
    > Uses `defer_*` counters/window to escalate to NO_TRADE_UNTIL_REFRESH.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.risk_skew.max_skew_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:701 (risk skew gate) ; apps/reference/domains/decision_making/decision_making.py:4309 (func: _get_risk_skew_config)
- **Mathematical/Architectural Role:**
    > Risk-skew guard: compares timestamps of latest risk assessment vs latest features:
    > `skew_sec = abs(features_ts - risk_ts)/1000` and deny/defer if `skew_sec > max_skew_sec`.
    > Uses `defer_*` counters/window to escalate to NO_TRADE_UNTIL_REFRESH.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.decision_making.risk_skew.until_refresh_retry_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `decision_making`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:701 (risk skew gate) ; apps/reference/domains/decision_making/decision_making.py:4309 (func: _get_risk_skew_config)
- **Mathematical/Architectural Role:**
    > Risk-skew guard: compares timestamps of latest risk assessment vs latest features:
    > `skew_sec = abs(features_ts - risk_ts)/1000` and deny/defer if `skew_sec > max_skew_sec`.
    > Uses `defer_*` counters/window to escalate to NO_TRADE_UNTIL_REFRESH.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
## Domain: `feature_engineering`
Цей домен задає **памʼять/вікна/фʼюзи** фіч. Багато параметрів прямо визначають, коли `warmup.full_ready=true`.
### `domains.feature_engineering.absorption.clip`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:404 (func: compute_absorption)
- **Mathematical/Architectural Role:**
    > Absorption experimental feature (proxy):
    > `proxy = (sum_buy - sum_sell)/(sum_buy + sum_sell + eps)` with dedup correlation guard vs TFI.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ ширший допустимий діапазон (менше clamp/not_ready).
    - 🔽 **Too Low:** Lower ⇒ жорсткіший bound (більше clamp/not_ready).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.absorption.dedup.enabled`
- **Type:** `bool`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:404 (func: compute_absorption)
- **Mathematical/Architectural Role:**
    > Absorption experimental feature (proxy):
    > `proxy = (sum_buy - sum_sell)/(sum_buy + sum_sell + eps)` with dedup correlation guard vs TFI.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.absorption.dedup.threshold`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:404 (func: compute_absorption)
- **Mathematical/Architectural Role:**
    > Absorption experimental feature (proxy):
    > `proxy = (sum_buy - sum_sell)/(sum_buy + sum_sell + eps)` with dedup correlation guard vs TFI.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ gate looser (більше проходів).
    - 🔽 **Too Low:** Lower ⇒ gate stricter (більше блоків).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.absorption.dedup.window`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:404 (func: compute_absorption)
- **Mathematical/Architectural Role:**
    > Absorption experimental feature (proxy):
    > `proxy = (sum_buy - sum_sell)/(sum_buy + sum_sell + eps)` with dedup correlation guard vs TFI.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.absorption.mode`
- **Type:** `string`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:404 (func: compute_absorption)
- **Mathematical/Architectural Role:**
    > Absorption experimental feature (proxy):
    > `proxy = (sum_buy - sum_sell)/(sum_buy + sum_sell + eps)` with dedup correlation guard vs TFI.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш permissive значення ⇒ ширша поведінка.
    - 🔽 **Too Low:** Більш strict значення ⇒ жорсткіша поведінка.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.absorption.neutral`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:404 (func: compute_absorption)
- **Mathematical/Architectural Role:**
    > Absorption experimental feature (proxy):
    > `proxy = (sum_buy - sum_sell)/(sum_buy + sum_sell + eps)` with dedup correlation guard vs TFI.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.absorption.proxy.eps`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:404 (func: compute_absorption)
- **Mathematical/Architectural Role:**
    > Absorption experimental feature (proxy):
    > `proxy = (sum_buy - sum_sell)/(sum_buy + sum_sell + eps)` with dedup correlation guard vs TFI.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.absorption.proxy.source`
- **Type:** `string`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:404 (func: compute_absorption)
- **Mathematical/Architectural Role:**
    > Absorption experimental feature (proxy):
    > `proxy = (sum_buy - sum_sell)/(sum_buy + sum_sell + eps)` with dedup correlation guard vs TFI.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш permissive значення ⇒ ширша поведінка.
    - 🔽 **Too Low:** Більш strict значення ⇒ жорсткіша поведінка.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.absorption.proxy.window`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:404 (func: compute_absorption)
- **Mathematical/Architectural Role:**
    > Absorption experimental feature (proxy):
    > `proxy = (sum_buy - sum_sell)/(sum_buy + sum_sell + eps)` with dedup correlation guard vs TFI.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.defaults.correlation_default`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:826 (props: neutral_value/zero_value/ms_per_sec)
- **Mathematical/Architectural Role:**
    > Configured key exists in SSOT schema but has **no effective runtime consumer** (or is only logged).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **UNKNOWN** (no runtime consumer or only logged)

---
### `domains.feature_engineering.defaults.ms_per_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:826 (props: neutral_value/zero_value/ms_per_sec)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.defaults.neutral_value`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:826 (props: neutral_value/zero_value/ms_per_sec)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.defaults.zero_value`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:826 (props: neutral_value/zero_value/ms_per_sec)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.delta_price.spike_filter_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:722 (delta_price spike filter)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.depth_imbalance.use_laplace_smoothing`
- **Type:** `bool`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:846 (func: compute_depth_imbalance)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.ema.period_long`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:268 (props: ema_short_alpha/ema_long_alpha)
- **Mathematical/Architectural Role:**
    > Lookback/buffer window length; larger windows smooth more but require more warmup.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.ema.period_short`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:268 (props: ema_short_alpha/ema_long_alpha)
- **Mathematical/Architectural Role:**
    > Lookback/buffer window length; larger windows smooth more but require more warmup.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.ema_bias.clamp_max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:752 (ema_bias compute)
- **Mathematical/Architectural Role:**
    > Clamping/capping parameter to limit outliers and avoid unstable math.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ ширший допустимий діапазон (менше clamp/not_ready).
    - 🔽 **Too Low:** Lower ⇒ жорсткіший bound (більше clamp/not_ready).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.ema_bias.clamp_min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:752 (ema_bias compute)
- **Mathematical/Architectural Role:**
    > Clamping/capping parameter to limit outliers and avoid unstable math.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ ширший допустимий діапазон (менше clamp/not_ready).
    - 🔽 **Too Low:** Lower ⇒ жорсткіший bound (більше clamp/not_ready).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.enable_new_metrics`
- **Type:** `bool`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/config_models.py:2206 (model: DomainsConfig)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.enabled_timeframes_sec`
- **Type:** `list[int]` *(seconds)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/config_models.py:2206 (model: DomainsConfig)
- **Mathematical/Architectural Role:**
    > Configured key exists in SSOT schema but has **no effective runtime consumer** (or is only logged).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший список ⇒ більше coverage/строгіша ready-умова/більше навантаження.
    - 🔽 **Too Low:** Менший список ⇒ простіше/легше, але менше coverage.
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **UNKNOWN** (no runtime consumer or only logged)

---
### `domains.feature_engineering.feature_sanity.enabled`
- **Type:** `bool`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.absorption.max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.absorption.min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.depth_imbalance.max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.depth_imbalance.min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.ema_bias.max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.ema_bias.min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.large_trade_imbalance.max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.large_trade_imbalance.min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.liquidity_kappa.max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.liquidity_kappa.min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.macro_resid.max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.macro_resid.min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.macro_sync.max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.macro_sync.min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.obi.max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.obi.min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.spread_bps.max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.spread_bps.min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.tfi.max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.tfi.min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.volatility_state.max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.volatility_state.min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.volume_spike.max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.volume_spike.min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.volume_zscore.max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.feature_bounds.volume_zscore.min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:575 (prop: feature_sanity_bounds) ; apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.feature_sanity.nan_inf_behavior`
- **Type:** `string`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:52 (func: sanitize_feature)
- **Mathematical/Architectural Role:**
    > Feature sanity firewall (P0-3):
    > - NaN/Inf handling per `nan_inf_behavior`
    > - per-feature bounds from `feature_bounds` (clamp + mark not_ready)
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш permissive значення ⇒ ширша поведінка.
    - 🔽 **Too Low:** Більш strict значення ⇒ жорсткіша поведінка.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.large_trade_imbalance.enabled`
- **Type:** `bool`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/large_trade_imbalance.py:44 (class: LargeTradeImbalanceCalculator)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.large_trade_imbalance.eps`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/large_trade_imbalance.py:44 (class: LargeTradeImbalanceCalculator)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.large_trade_imbalance.min_trades`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/large_trade_imbalance.py:44 (class: LargeTradeImbalanceCalculator)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.large_trade_imbalance.use_notional`
- **Type:** `bool` *(USD/USDT)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/large_trade_imbalance.py:44 (class: LargeTradeImbalanceCalculator)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.large_trade_imbalance.window_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/large_trade_imbalance.py:44 (class: LargeTradeImbalanceCalculator)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.liquidity.depth_half`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:735 (liq_kappa computation)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.liquidity.kappa_max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:735 (liq_kappa computation)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.liquidity.kappa_min`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:735 (liq_kappa computation)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_resid.beta_window`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:317 (func: compute_macro_resid)
- **Mathematical/Architectural Role:**
    > Macro residual (SIGNED) feature: `resid = r_asset - beta*r_anchor`.
    > Beta estimated on rolling window; scaled by MAD; clipped to `±clip`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_resid.clip`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:317 (func: compute_macro_resid)
- **Mathematical/Architectural Role:**
    > Macro residual (SIGNED) feature: `resid = r_asset - beta*r_anchor`.
    > Beta estimated on rolling window; scaled by MAD; clipped to `±clip`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ ширший допустимий діапазон (менше clamp/not_ready).
    - 🔽 **Too Low:** Lower ⇒ жорсткіший bound (більше clamp/not_ready).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_resid.enabled`
- **Type:** `bool`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:317 (func: compute_macro_resid)
- **Mathematical/Architectural Role:**
    > Macro residual (SIGNED) feature: `resid = r_asset - beta*r_anchor`.
    > Beta estimated on rolling window; scaled by MAD; clipped to `±clip`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_resid.mad_window`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:317 (func: compute_macro_resid)
- **Mathematical/Architectural Role:**
    > Macro residual (SIGNED) feature: `resid = r_asset - beta*r_anchor`.
    > Beta estimated on rolling window; scaled by MAD; clipped to `±clip`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_resid.neutral`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:317 (func: compute_macro_resid)
- **Mathematical/Architectural Role:**
    > Macro residual (SIGNED) feature: `resid = r_asset - beta*r_anchor`.
    > Beta estimated on rolling window; scaled by MAD; clipped to `±clip`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_resid.scale_floor`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:317 (func: compute_macro_resid)
- **Mathematical/Architectural Role:**
    > Macro residual (SIGNED) feature: `resid = r_asset - beta*r_anchor`.
    > Beta estimated on rolling window; scaled by MAD; clipped to `±clip`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_resid.var_floor`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:317 (func: compute_macro_resid)
- **Mathematical/Architectural Role:**
    > Macro residual (SIGNED) feature: `resid = r_asset - beta*r_anchor`.
    > Beta estimated on rolling window; scaled by MAD; clipped to `±clip`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_resid.winsor_percentile`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:317 (func: compute_macro_resid)
- **Mathematical/Architectural Role:**
    > Macro residual (SIGNED) feature: `resid = r_asset - beta*r_anchor`.
    > Beta estimated on rolling window; scaled by MAD; clipped to `±clip`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_sync.align_mode`
- **Type:** `string`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:124 (MacroSyncResampler init) ; apps/reference/domains/feature_engineering/calculation_engine.py:915 (func: compute_macro_sync)
- **Mathematical/Architectural Role:**
    > Macro-sync feature configuration:
    > Computes correlation of symbol returns vs anchors; readiness requires buffers and fresh anchor ticks (TTL).
    > Some parameters feed MacroSyncResampler (binning/ttl/max_gap) and alignment logic.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш permissive значення ⇒ ширша поведінка.
    - 🔽 **Too Low:** Більш strict значення ⇒ жорсткіша поведінка.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_sync.anchor_update_from_ticks`
- **Type:** `bool`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:124 (MacroSyncResampler init) ; apps/reference/domains/feature_engineering/calculation_engine.py:915 (func: compute_macro_sync)
- **Mathematical/Architectural Role:**
    > Macro-sync feature configuration:
    > Computes correlation of symbol returns vs anchors; readiness requires buffers and fresh anchor ticks (TTL).
    > Some parameters feed MacroSyncResampler (binning/ttl/max_gap) and alignment logic.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_sync.anchors`
- **Type:** `list[string]`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:124 (MacroSyncResampler init) ; apps/reference/domains/feature_engineering/calculation_engine.py:915 (func: compute_macro_sync)
- **Mathematical/Architectural Role:**
    > Macro-sync feature configuration:
    > Computes correlation of symbol returns vs anchors; readiness requires buffers and fresh anchor ticks (TTL).
    > Some parameters feed MacroSyncResampler (binning/ttl/max_gap) and alignment logic.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший список ⇒ більше coverage/строгіша ready-умова/більше навантаження.
    - 🔽 **Too Low:** Менший список ⇒ простіше/легше, але менше coverage.
- **Invariant/Constraints:** List content must match expected schema; empty lists may mean 'no overrides' or can break readiness if treated as required.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_sync.bin_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:124 (MacroSyncResampler init) ; apps/reference/domains/feature_engineering/calculation_engine.py:915 (func: compute_macro_sync)
- **Mathematical/Architectural Role:**
    > Macro-sync feature configuration:
    > Computes correlation of symbol returns vs anchors; readiness requires buffers and fresh anchor ticks (TTL).
    > Some parameters feed MacroSyncResampler (binning/ttl/max_gap) and alignment logic.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_sync.enabled`
- **Type:** `bool`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:124 (MacroSyncResampler init) ; apps/reference/domains/feature_engineering/calculation_engine.py:915 (func: compute_macro_sync)
- **Mathematical/Architectural Role:**
    > Macro-sync feature configuration:
    > Computes correlation of symbol returns vs anchors; readiness requires buffers and fresh anchor ticks (TTL).
    > Some parameters feed MacroSyncResampler (binning/ttl/max_gap) and alignment logic.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_sync.eps`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:124 (MacroSyncResampler init) ; apps/reference/domains/feature_engineering/calculation_engine.py:915 (func: compute_macro_sync)
- **Mathematical/Architectural Role:**
    > Macro-sync feature configuration:
    > Computes correlation of symbol returns vs anchors; readiness requires buffers and fresh anchor ticks (TTL).
    > Some parameters feed MacroSyncResampler (binning/ttl/max_gap) and alignment logic.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_sync.max_gap_bins`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:124 (MacroSyncResampler init) ; apps/reference/domains/feature_engineering/calculation_engine.py:915 (func: compute_macro_sync)
- **Mathematical/Architectural Role:**
    > Macro-sync feature configuration:
    > Computes correlation of symbol returns vs anchors; readiness requires buffers and fresh anchor ticks (TTL).
    > Some parameters feed MacroSyncResampler (binning/ttl/max_gap) and alignment logic.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_sync.max_late_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:124 (MacroSyncResampler init) ; apps/reference/domains/feature_engineering/calculation_engine.py:915 (func: compute_macro_sync)
- **Mathematical/Architectural Role:**
    > Macro-sync feature configuration:
    > Computes correlation of symbol returns vs anchors; readiness requires buffers and fresh anchor ticks (TTL).
    > Some parameters feed MacroSyncResampler (binning/ttl/max_gap) and alignment logic.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_sync.min_buffer_size`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:124 (MacroSyncResampler init) ; apps/reference/domains/feature_engineering/calculation_engine.py:915 (func: compute_macro_sync)
- **Mathematical/Architectural Role:**
    > Macro-sync feature configuration:
    > Computes correlation of symbol returns vs anchors; readiness requires buffers and fresh anchor ticks (TTL).
    > Some parameters feed MacroSyncResampler (binning/ttl/max_gap) and alignment logic.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_sync.time_diff_threshold_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:124 (MacroSyncResampler init) ; apps/reference/domains/feature_engineering/calculation_engine.py:915 (func: compute_macro_sync)
- **Mathematical/Architectural Role:**
    > Macro-sync feature configuration:
    > Computes correlation of symbol returns vs anchors; readiness requires buffers and fresh anchor ticks (TTL).
    > Some parameters feed MacroSyncResampler (binning/ttl/max_gap) and alignment logic.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_sync.ttl_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:124 (MacroSyncResampler init) ; apps/reference/domains/feature_engineering/calculation_engine.py:915 (func: compute_macro_sync)
- **Mathematical/Architectural Role:**
    > Macro-sync feature configuration:
    > Computes correlation of symbol returns vs anchors; readiness requires buffers and fresh anchor ticks (TTL).
    > Some parameters feed MacroSyncResampler (binning/ttl/max_gap) and alignment logic.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.macro_sync.window`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:124 (MacroSyncResampler init) ; apps/reference/domains/feature_engineering/calculation_engine.py:915 (func: compute_macro_sync)
- **Mathematical/Architectural Role:**
    > Macro-sync feature configuration:
    > Computes correlation of symbol returns vs anchors; readiness requires buffers and fresh anchor ticks (TTL).
    > Some parameters feed MacroSyncResampler (binning/ttl/max_gap) and alignment logic.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.readiness_registry.declared_keys`
- **Type:** `list[string]`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:434 (func: compute_warmup_full_ready_for_symbol) ; apps/reference/config_loader.py:1156 (func: _validate_essential_features_readiness_contract)
- **Mathematical/Architectural Role:**
    > List/allowlist that influences readiness and computation coverage.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший список ⇒ більше coverage/строгіша ready-умова/більше навантаження.
    - 🔽 **Too Low:** Менший список ⇒ простіше/легше, але менше coverage.
- **Invariant/Constraints:** List content must match expected schema; empty lists may mean 'no overrides' or can break readiness if treated as required.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.spread_bps.health_gate.enabled`
- **Type:** `bool`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:118 (func: check_book_health)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.spread_bps.health_gate.max_age_sec`
- **Type:** `float` *(seconds)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:118 (func: check_book_health)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.spread_bps.health_gate.min_trades_count`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:118 (func: check_book_health)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.spread_bps.health_gate.min_update_events`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:118 (func: check_book_health)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.spread_bps.health_gate.window_sec`
- **Type:** `float` *(seconds)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:118 (func: check_book_health)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.volatility.sma_length`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:309 (props: volatility_* accessors)
- **Mathematical/Architectural Role:**
    > Lookback/buffer window length; larger windows smooth more but require more warmup.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.volatility.window_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:309 (props: volatility_* accessors)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.volatility_state.cap_max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:732 (func: compute_volatility_state)
- **Mathematical/Architectural Role:**
    > Clamping/capping parameter to limit outliers and avoid unstable math.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ ширший допустимий діапазон (менше clamp/not_ready).
    - 🔽 **Too Low:** Lower ⇒ жорсткіший bound (більше clamp/not_ready).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.volatility_state.division_eps`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:732 (func: compute_volatility_state)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.volatility_state.tick_floor`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/calculation_engine.py:732 (func: compute_volatility_state)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.volume.min_window_volume_usd`
- **Type:** `float` *(USD/USDT)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:292 (props: volume_* accessors)
- **Mathematical/Architectural Role:**
    > Lookback/buffer window length; larger windows smooth more but require more warmup.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.volume.sma_length`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:292 (props: volume_* accessors)
- **Mathematical/Architectural Role:**
    > Lookback/buffer window length; larger windows smooth more but require more warmup.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.volume.window_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:292 (props: volume_* accessors)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.volume_input_mode`
- **Type:** `string`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/config_models.py:2206 (model: DomainsConfig)
- **Mathematical/Architectural Role:**
    > Configured key exists in SSOT schema but has **no effective runtime consumer** (or is only logged).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш permissive значення ⇒ ширша поведінка.
    - 🔽 **Too Low:** Більш strict значення ⇒ жорсткіша поведінка.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **UNKNOWN** (no runtime consumer or only logged)

---
### `domains.feature_engineering.volume_spike.cap_max`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:744 (volume_spike update/compute)
- **Mathematical/Architectural Role:**
    > Clamping/capping parameter to limit outliers and avoid unstable math.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ ширший допустимий діапазон (менше clamp/not_ready).
    - 🔽 **Too Low:** Lower ⇒ жорсткіший bound (більше clamp/not_ready).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.volume_spike.eps`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:744 (volume_spike update/compute)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.volume_spike.sma_len`
- **Type:** `int`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:744 (volume_spike update/compute)
- **Mathematical/Architectural Role:**
    > Lookback/buffer window length; larger windows smooth more but require more warmup.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.volume_zscore.clip_sigma`
- **Type:** `float`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/utils.py:263 (func: compute_z_score)
- **Mathematical/Architectural Role:**
    > Clamping/capping parameter to limit outliers and avoid unstable math.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ ширший допустимий діапазон (менше clamp/not_ready).
    - 🔽 **Too Low:** Lower ⇒ жорсткіший bound (більше clamp/not_ready).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.feature_engineering.warmup.check_full_ready_invariant`
- **Type:** `bool`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/types.py:421 (prop: warmup_check_full_ready_invariant)
- **Mathematical/Architectural Role:**
    > Configured key exists in SSOT schema but has **no effective runtime consumer** (or is only logged).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **UNKNOWN** (no runtime consumer or only logged)

---
### `domains.feature_engineering.warmup.enforcement_mode`
- **Type:** `string`
- **Logic Owner:** `feature_engineering`
- **Code Reference:** apps/reference/domains/feature_engineering/feature_engineering.py:1149 (CMD:PROCESS_STRATEGY gate)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш permissive значення ⇒ ширша поведінка.
    - 🔽 **Too Low:** Більш strict значення ⇒ жорсткіша поведінка.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
## Domain: `risk_management`
Цей домен є SSOT для **risk score** (ваги + пороги). Legacy `trading.risk.score_weights.*` не використовується.
### `domains.risk_management.risk_score_weights.absorption_inverse`
- **Type:** `float`
- **Logic Owner:** `risk_management`
- **Code Reference:** apps/reference/domains/risk_management/risk_management.py:240 (func: _calculate_risk_parameters)
- **Mathematical/Architectural Role:**
    > Weight in linear risk score (RiskManagement):
    > `risk_score = delta_price_pct*w_delta + abs(obi)*w_obi + abs(tfi)*w_tfi + (1-absorption)*w_abs_inv`
    > Then clamped to `[0,1]` and compared to `domains.risk_management.trading_allowed_thresholds.max_risk_score`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ absorption_inverse contributes more to risk_score ⇒ більше блоків.
    - 🔽 **Too Low:** Lower ⇒ absorption_inverse contributes less ⇒ менше блоків.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.risk_management.risk_score_weights.delta_price_pct`
- **Type:** `float` *(percent)*
- **Logic Owner:** `risk_management`
- **Code Reference:** apps/reference/domains/risk_management/risk_management.py:240 (func: _calculate_risk_parameters)
- **Mathematical/Architectural Role:**
    > Weight in linear risk score (RiskManagement):
    > `risk_score = delta_price_pct*w_delta + abs(obi)*w_obi + abs(tfi)*w_tfi + (1-absorption)*w_abs_inv`
    > Then clamped to `[0,1]` and compared to `domains.risk_management.trading_allowed_thresholds.max_risk_score`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ delta_price_pct contributes more to risk_score ⇒ більше блоків.
    - 🔽 **Too Low:** Lower ⇒ delta_price_pct contributes less ⇒ менше блоків.
- **Invariant/Constraints:** Percentage semantics where applicable; ExposureGuard divides `_pct` fields by 100.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.risk_management.risk_score_weights.obi`
- **Type:** `float`
- **Logic Owner:** `risk_management`
- **Code Reference:** apps/reference/domains/risk_management/risk_management.py:240 (func: _calculate_risk_parameters)
- **Mathematical/Architectural Role:**
    > Weight in linear risk score (RiskManagement):
    > `risk_score = delta_price_pct*w_delta + abs(obi)*w_obi + abs(tfi)*w_tfi + (1-absorption)*w_abs_inv`
    > Then clamped to `[0,1]` and compared to `domains.risk_management.trading_allowed_thresholds.max_risk_score`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ obi contributes more to risk_score ⇒ більше блоків.
    - 🔽 **Too Low:** Lower ⇒ obi contributes less ⇒ менше блоків.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.risk_management.risk_score_weights.tfi`
- **Type:** `float`
- **Logic Owner:** `risk_management`
- **Code Reference:** apps/reference/domains/risk_management/risk_management.py:240 (func: _calculate_risk_parameters)
- **Mathematical/Architectural Role:**
    > Weight in linear risk score (RiskManagement):
    > `risk_score = delta_price_pct*w_delta + abs(obi)*w_obi + abs(tfi)*w_tfi + (1-absorption)*w_abs_inv`
    > Then clamped to `[0,1]` and compared to `domains.risk_management.trading_allowed_thresholds.max_risk_score`.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ tfi contributes more to risk_score ⇒ більше блоків.
    - 🔽 **Too Low:** Lower ⇒ tfi contributes less ⇒ менше блоків.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.risk_management.trading_allowed_thresholds.max_risk_score`
- **Type:** `float`
- **Logic Owner:** `risk_management`
- **Code Reference:** apps/reference/domains/risk_management/risk_management.py:240 (func: _calculate_risk_parameters)
- **Mathematical/Architectural Role:**
    > Hard threshold for trading permission: allow only if `risk_score <= max_risk_score`.
    > Fail-closed on missing config (`ConfigContractError`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ more trades pass risk gate (less conservative).
    - 🔽 **Too Low:** Lower ⇒ more intents blocked by risk score.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.risk_management.use_absorption_penalty`
- **Type:** `bool`
- **Logic Owner:** `risk_management`
- **Code Reference:** apps/reference/domains/risk_management/risk_management.py:240 (func: _calculate_risk_parameters)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.risk_management.validation.total_weight_max`
- **Type:** `float`
- **Logic Owner:** `risk_management`
- **Code Reference:** apps/reference/domains/risk_management/risk_management.py:240 (func: _calculate_risk_parameters)
- **Mathematical/Architectural Role:**
    > Scalar weight in a composite metric (higher ⇒ more influence).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ цей терм домінує у метриці.
    - 🔽 **Too Low:** Lower ⇒ цей терм менш впливовий.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.risk_management.validation.total_weight_min`
- **Type:** `float`
- **Logic Owner:** `risk_management`
- **Code Reference:** apps/reference/domains/risk_management/risk_management.py:240 (func: _calculate_risk_parameters)
- **Mathematical/Architectural Role:**
    > Scalar weight in a composite metric (higher ⇒ more influence).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ цей терм домінує у метриці.
    - 🔽 **Too Low:** Lower ⇒ цей терм менш впливовий.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
## Domain: `position_tracking`
### `domains.position_tracking.enable_market_tick_subscription`
- **Type:** `bool`
- **Logic Owner:** `position_tracking`
- **Code Reference:** apps/reference/domains/position_tracking/position_tracking.py:71 (PositionTracking.__init__)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.position_tracking.positions_stale_ttl_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `position_tracking`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:814 (portfolio freshness defer) ; apps/reference/domains/decision_making/decision_making.py:4129 (func: _portfolio_is_stale)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.position_tracking.precision.decimal_places`
- **Type:** `int`
- **Logic Owner:** `position_tracking`
- **Code Reference:** apps/reference/domains/position_tracking/position_tracking.py:71 (PositionTracking.__init__)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.position_tracking.precision.flat_position_threshold`
- **Type:** `float`
- **Logic Owner:** `position_tracking`
- **Code Reference:** apps/reference/domains/position_tracking/position_tracking.py:71 (PositionTracking.__init__)
- **Mathematical/Architectural Role:**
    > Threshold for a gate/health check; crossing changes allow/deny behavior.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ gate looser (більше проходів).
    - 🔽 **Too Low:** Lower ⇒ gate stricter (більше блоків).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.position_tracking.precision.quantity_min_threshold`
- **Type:** `float`
- **Logic Owner:** `position_tracking`
- **Code Reference:** apps/reference/domains/position_tracking/position_tracking.py:71 (PositionTracking.__init__)
- **Mathematical/Architectural Role:**
    > Threshold for a gate/health check; crossing changes allow/deny behavior.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ gate looser (більше проходів).
    - 🔽 **Too Low:** Lower ⇒ gate stricter (більше блоків).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
## Domain: `execution_position`
Цей домен є **канонічним джерелом hard-guard параметрів** для виконання (ExposureGuard, Guardian, дедуп, TTL, retry).
### `domains.execution_position.bracket_placement.retry_backoff_ms`
- **Type:** `list[int]` *(milliseconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:3214 (TP widen/backoff)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший список ⇒ більше coverage/строгіша ready-умова/більше навантаження.
    - 🔽 **Too Low:** Менший список ⇒ простіше/легше, але менше coverage.
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.bracket_placement.tp_widen_first_bps`
- **Type:** `int` *(basis points)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:3214 (TP widen/backoff)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.bracket_placement.tp_widen_second_bps`
- **Type:** `int` *(basis points)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:3214 (TP widen/backoff)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.event_dedup.max_size`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:400 (ExecPosFSM.__init__)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більша памʼять/менше повторів (менше дублюючих евентів).
    - 🔽 **Too Low:** Lower ⇒ менша памʼять/більше повторів або колізій.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.event_dedup.ttl_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:400 (ExecPosFSM.__init__)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.exposure_guard.max_concentration_pct`
- **Type:** `float` *(percent)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/exposure_guard.py:79 (ExposureGuard.__init__) ; apps/reference/domains/execution_position/exposure_guard.py:648 (func: can_open)
- **Mathematical/Architectural Role:**
    > Per-symbol MARGIN concentration cap:
    > - `projected_symbol_margin = current_symbol_margin + pending_symbol_m + post_symbol_m + order_margin`
    > - `limit = equity_free_usdt * (max_concentration_pct/100)`
    > Block if breached (`CONCENTRATION_BREACH`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ allows larger per-symbol concentration.
    - 🔽 **Too Low:** Lower ⇒ more `CONCENTRATION_BREACH` blocks.
- **Invariant/Constraints:** Percentage semantics where applicable; ExposureGuard divides `_pct` fields by 100.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.exposure_guard.max_directional_ratio`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/exposure_guard.py:79 (ExposureGuard.__init__) ; apps/reference/domains/execution_position/exposure_guard.py:648 (func: can_open)
- **Mathematical/Architectural Role:**
    > Directional ratio gate (margin-based):
    > - `ratio = max(new_long_m, new_short_m) / min(new_long_m, new_short_m)` (when min>0)
    > Block if `ratio > max_directional_ratio` (`DIRECTIONAL_RATIO_BREACH`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.exposure_guard.max_equity_utilization_pct`
- **Type:** `float` *(percent)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/exposure_guard.py:79 (ExposureGuard.__init__) ; apps/reference/domains/execution_position/exposure_guard.py:648 (func: can_open)
- **Mathematical/Architectural Role:**
    > Hard gate for MARGIN utilization in `ExposureGuard.can_open()`: 
    > - `order_margin = order_notional_abs / leverage`
    > - `total_margin_used = open_positions_margin_usd + total_pending_margin + order_margin`
    > - `equity_margin_limit = equity_free_usdt * (max_equity_utilization_pct / 100)`
    > Block if `total_margin_used > equity_margin_limit` (`EQUITY_UTILIZATION_BREACH`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ allows more margin usage before blocking (higher tail risk).
    - 🔽 **Too Low:** Lower ⇒ more frequent rejects (`EQUITY_UTILIZATION_BREACH`).
- **Invariant/Constraints:** Percentage semantics where applicable; ExposureGuard divides `_pct` fields by 100.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.exposure_guard.max_long_utilization_pct`
- **Type:** `float` *(percent)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/exposure_guard.py:79 (ExposureGuard.__init__) ; apps/reference/domains/execution_position/exposure_guard.py:648 (func: can_open)
- **Mathematical/Architectural Role:**
    > Side-specific MARGIN gate (LONG side):
    > - `new_long_m = long_margin + pending_long_m + post_long_m + (order_margin if BUY)`
    > - `long_limit = equity_free_usdt * (max_long_utilization_pct/100)`
    > Block if `new_long_m > long_limit` (`LONG_UTILIZATION_BREACH`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ allows larger LONG-side margin utilisation.
    - 🔽 **Too Low:** Lower ⇒ more `LONG_UTILIZATION_BREACH` blocks.
- **Invariant/Constraints:** Percentage semantics where applicable; ExposureGuard divides `_pct` fields by 100.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.exposure_guard.max_portfolio_fraction`
- **Type:** `float`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/exposure_guard.py:79 (ExposureGuard.__init__) ; apps/reference/domains/execution_position/exposure_guard.py:648 (func: can_open)
- **Mathematical/Architectural Role:**
    > Hard gate for NOTIONAL-based cap in `ExposureGuard.can_open()`: 
    > - `projected_notional = open_positions_usd + pending_notional + post_notional + order_notional_abs`
    > - `p_frac_limit = equity_free_usdt * max_portfolio_fraction`
    > Block if `projected_notional > p_frac_limit` (`PORTFOLIO_FRACTION_BREACH`).
    > ⚠️ Semantics note: unlike `_pct` fields, this value is NOT divided by 100 in code; treat as multiplier/ratio.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ allows larger projected notional vs equity (can effectively disable gate if set huge).
    - 🔽 **Too Low:** Lower ⇒ blocks growth in total notional sooner (`PORTFOLIO_FRACTION_BREACH`).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.exposure_guard.max_short_utilization_pct`
- **Type:** `float` *(percent)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/exposure_guard.py:79 (ExposureGuard.__init__) ; apps/reference/domains/execution_position/exposure_guard.py:648 (func: can_open)
- **Mathematical/Architectural Role:**
    > Side-specific MARGIN gate (SHORT side):
    > - `new_short_m = short_margin + pending_short_m + post_short_m + (order_margin if SELL)`
    > - `short_limit = equity_free_usdt * (max_short_utilization_pct/100)`
    > Block if `new_short_m > short_limit` (`SHORT_UTILIZATION_BREACH`).
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ allows larger SHORT-side margin utilisation.
    - 🔽 **Too Low:** Lower ⇒ more `SHORT_UTILIZATION_BREACH` blocks.
- **Invariant/Constraints:** Percentage semantics where applicable; ExposureGuard divides `_pct` fields by 100.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.exposure_guard.pending_ttl_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/exposure_guard.py:79 (ExposureGuard.__init__) ; apps/reference/domains/execution_position/exposure_guard.py:648 (func: can_open)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.exposure_guard.post_fill_ttl_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/exposure_guard.py:79 (ExposureGuard.__init__) ; apps/reference/domains/execution_position/exposure_guard.py:648 (func: can_open)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.exposure_guard.stale_ttl_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/exposure_guard.py:79 (ExposureGuard.__init__) ; apps/reference/domains/execution_position/exposure_guard.py:648 (func: can_open)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.fallback.backoff_ms`
- **Type:** `list[int]` *(milliseconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/exposure_guard.py:173 (func: _load_fallback_config) ; apps/reference/domains/execution_position/exposure_guard.py:460 (func: can_open)
- **Mathematical/Architectural Role:**
    > Fallback-mode parameter for ExposureGuard (used when portfolio truth is degraded / API issues).
    > Note: some subfields are currently only logged unless fallback policy wiring is fixed.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший список ⇒ більше coverage/строгіша ready-умова/більше навантаження.
    - 🔽 **Too Low:** Менший список ⇒ простіше/легше, але менше coverage.
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **UNKNOWN** (no runtime consumer or only logged)

---
### `domains.execution_position.fallback.policy`
- **Type:** `string`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/exposure_guard.py:173 (func: _load_fallback_config) ; apps/reference/domains/execution_position/exposure_guard.py:460 (func: can_open)
- **Mathematical/Architectural Role:**
    > Selects fallback behavior when ExposureGuard enters fallback mode.
    > ⚠️ **Implementation mismatch:** runtime checks for `policy == 'risk_reduction'` but schema allows `reduce_exposure`; therefore non-`fail_closed` path is currently unreachable.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більш permissive значення ⇒ ширша поведінка.
    - 🔽 **Too Low:** Більш strict значення ⇒ жорсткіша поведінка.
- **Invariant/Constraints:** Enum: `fail_closed|reduce_exposure` (⚠️ runtime currently checks `risk_reduction`, so `reduce_exposure` is effectively ignored until fixed).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.fallback.risk_reduction_pct`
- **Type:** `float` *(percent)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/exposure_guard.py:173 (func: _load_fallback_config) ; apps/reference/domains/execution_position/exposure_guard.py:460 (func: can_open)
- **Mathematical/Architectural Role:**
    > Fallback-mode parameter for ExposureGuard (used when portfolio truth is degraded / API issues).
    > Note: some subfields are currently only logged unless fallback policy wiring is fixed.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Percentage semantics where applicable; ExposureGuard divides `_pct` fields by 100.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.fsm_open.idempotency_window_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm_open.py:164 (OpenFlowFSM.__init__)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.guardian.cleanup_ttl_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:777 (func: _resolve_guardian_config)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.guardian.emit_tidy_event`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:777 (func: _resolve_guardian_config)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.guardian.poll_interval_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:777 (func: _resolve_guardian_config)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.guardian.symbol_cooldown_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:777 (func: _resolve_guardian_config)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.guardian.unified`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:777 (func: _resolve_guardian_config)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.idempotent_cancel.max_retries`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:176 (ExecPosFSM.__init__)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.inflight_reconcile.inflight_ttl_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/main.py:1142 (InFlightConfig.from_ssot) ; apps/reference/domains/inflight_reconcile/config.py:34 (func: from_ssot)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.inflight_reconcile.max_ttl_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/main.py:1142 (InFlightConfig.from_ssot) ; apps/reference/domains/inflight_reconcile/config.py:34 (func: from_ssot)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.inflight_reconcile.reconcile_interval_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/main.py:1142 (InFlightConfig.from_ssot) ; apps/reference/domains/inflight_reconcile/config.py:34 (func: from_ssot)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.inflight_reconcile.verbose_logging`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/main.py:1142 (InFlightConfig.from_ssot) ; apps/reference/domains/inflight_reconcile/config.py:34 (func: from_ssot)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.maker_only_entry.enabled`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm_open.py:302 (Maker-only enforcement)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.metrics_collector.recent_rejections_minutes`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:162 (ExecPosFSM.__init__)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.metrics_collector.window_size_minutes`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:162 (ExecPosFSM.__init__)
- **Mathematical/Architectural Role:**
    > Lookback/buffer window length; larger windows smooth more but require more warmup.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.order_capabilities.supported_order_types`
- **Type:** `list[string]`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3161 (ORDER-POLICY-01)
- **Mathematical/Architectural Role:**
    > Clamping/capping parameter to limit outliers and avoid unstable math.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший список ⇒ більше coverage/строгіша ready-умова/більше навантаження.
    - 🔽 **Too Low:** Менший список ⇒ простіше/легше, але менше coverage.
- **Invariant/Constraints:** List content must match expected schema; empty lists may mean 'no overrides' or can break readiness if treated as required.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.order_capabilities.supported_tif`
- **Type:** `list[string]`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3161 (ORDER-POLICY-01)
- **Mathematical/Architectural Role:**
    > Clamping/capping parameter to limit outliers and avoid unstable math.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Більший список ⇒ більше coverage/строгіша ready-умова/більше навантаження.
    - 🔽 **Too Low:** Менший список ⇒ простіше/легше, але менше coverage.
- **Invariant/Constraints:** List content must match expected schema; empty lists may mean 'no overrides' or can break readiness if treated as required.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.order_index.ttl_sec`
- **Type:** `int` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/main.py:221 (wire OrderIndex) ; apps/reference/domains/execution_position/fsm.py:1414 (OrderIndex use)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.order_lifecycle.fill_settlement_delay_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:1699 (fill cleanup delay) ; apps/reference/domains/execution_position/fsm.py:2224 (close cleanup delay)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.order_lifecycle.position_close_cleanup_delay_ms`
- **Type:** `int` *(milliseconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:1699 (fill cleanup delay) ; apps/reference/domains/execution_position/fsm.py:2224 (close cleanup delay)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.pending_entry_ttl.cancel_on_panic`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3239 (EP-01.3 valid_for_ms) ; apps/reference/domains/execution_position/fsm.py:2447 (EP-01.3 supersede)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.pending_entry_ttl.cancel_on_regime_change`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3239 (EP-01.3 valid_for_ms) ; apps/reference/domains/execution_position/fsm.py:2447 (EP-01.3 supersede)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.pending_entry_ttl.cancel_on_supersede`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3239 (EP-01.3 valid_for_ms) ; apps/reference/domains/execution_position/fsm.py:2447 (EP-01.3 supersede)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.pending_entry_ttl.enabled`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3239 (EP-01.3 valid_for_ms) ; apps/reference/domains/execution_position/fsm.py:2447 (EP-01.3 supersede)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.pending_entry_ttl.reject_unknown_tf`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3239 (EP-01.3 valid_for_ms) ; apps/reference/domains/execution_position/fsm.py:2447 (EP-01.3 supersede)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.pending_entry_ttl.supersede_cancel_timeout_sec`
- **Type:** `float` *(seconds)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3239 (EP-01.3 valid_for_ms) ; apps/reference/domains/execution_position/fsm.py:2447 (EP-01.3 supersede)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Float seconds; Pydantic validates: `1.0 <= value <= 60.0` (strict SSOT).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.pending_entry_ttl.ttl_by_tf_sec.180`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3239 (EP-01.3 valid_for_ms) ; apps/reference/domains/execution_position/fsm.py:2447 (EP-01.3 supersede)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.pending_entry_ttl.ttl_by_tf_sec.300`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3239 (EP-01.3 valid_for_ms) ; apps/reference/domains/execution_position/fsm.py:2447 (EP-01.3 supersede)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.pending_entry_ttl.ttl_by_tf_sec.900`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/decision_making/decision_making.py:3239 (EP-01.3 valid_for_ms) ; apps/reference/domains/execution_position/fsm.py:2447 (EP-01.3 supersede)
- **Mathematical/Architectural Role:**
    > Time constant for gating/backoff/staleness; trades off lag vs churn.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ більше lag/буфера (менше churn).
    - 🔽 **Too Low:** Lower ⇒ менше lag (більше churn/ризик rate-limit/false positives).
- **Invariant/Constraints:** Must be > 0 for meaningful operation; some critical paths are fail-closed on missing/invalid values.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.shadow_check.absolute_threshold_usd`
- **Type:** `float` *(USD/USDT)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:3871 (sampling) ; apps/reference/domains/execution_position/fsm.py:4140 (threshold compare)
- **Mathematical/Architectural Role:**
    > Threshold for a gate/health check; crossing changes allow/deny behavior.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ gate looser (більше проходів).
    - 🔽 **Too Low:** Lower ⇒ gate stricter (більше блоків).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.shadow_check.check_every_n_requests`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:3871 (sampling) ; apps/reference/domains/execution_position/fsm.py:4140 (threshold compare)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.shadow_check.enabled`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:3871 (sampling) ; apps/reference/domains/execution_position/fsm.py:4140 (threshold compare)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.shadow_check.large_portfolio_threshold_usd`
- **Type:** `float` *(USD/USDT)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:3871 (sampling) ; apps/reference/domains/execution_position/fsm.py:4140 (threshold compare)
- **Mathematical/Architectural Role:**
    > Threshold for a gate/health check; crossing changes allow/deny behavior.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ gate looser (більше проходів).
    - 🔽 **Too Low:** Lower ⇒ gate stricter (більше блоків).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.shadow_check.tolerance_pct`
- **Type:** `float` *(percent)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:3871 (sampling) ; apps/reference/domains/execution_position/fsm.py:4140 (threshold compare)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Percentage semantics where applicable; ExposureGuard divides `_pct` fields by 100.
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.shadow_check.use_absolute_for_large_portfolios`
- **Type:** `bool`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/fsm.py:3871 (sampling) ; apps/reference/domains/execution_position/fsm.py:4140 (threshold compare)
- **Mathematical/Architectural Role:**
    > Boolean gate/feature flag controlling whether a logic branch is active.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** `true` ⇒ гілка активна (більше enforcement/compute).
    - 🔽 **Too Low:** `false` ⇒ гілка неактивна (менше enforcement/compute).
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.utils.basis_points_base`
- **Type:** `float` *(basis points)*
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/utils.py:151 (func: generate_client_order_id) ; apps/reference/domains/execution_position/utils.py:235 (func: calc_tp_sl_from_mark)
- **Mathematical/Architectural Role:**
    > Domain-specific scalar used by runtime logic as configured SSOT.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ підсилює відповідний ефект/допуск цього параметра.
    - 🔽 **Too Low:** Lower ⇒ послаблює ефект/допуск цього параметра.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---
### `domains.execution_position.utils.client_order_id_max_length`
- **Type:** `int`
- **Logic Owner:** `execution_position`
- **Code Reference:** apps/reference/domains/execution_position/utils.py:151 (func: generate_client_order_id) ; apps/reference/domains/execution_position/utils.py:235 (func: calc_tp_sl_from_mark)
- **Mathematical/Architectural Role:**
    > Lookback/buffer window length; larger windows smooth more but require more warmup.
- **Tuning Sensitivity:**
    - 🔼 **Too High:** Higher ⇒ smooth + стабільніше, але довший warmup.
    - 🔽 **Too Low:** Lower ⇒ реактивніше, але шумніше.
- **Invariant/Constraints:** Strict schema: unknown fields forbidden (Pydantic `extra='forbid'`).
- **SSOT Status:** **CONFIRMED** (canonical `config.domains.*` SSOT)

---

## Domain: `shadow_telemetry`
Цей домен задає параметри інфраструктури відслідковування тіньових інцидентів (LLM microstructure).

### `domains.shadow_telemetry.enabled`
- **Type:** `bool`
- **Logic Owner:** `shadow_telemetry`
- **Mathematical/Architectural Role:**
    > Master toggle для shadow_telemetry системи.

### `domains.shadow_telemetry.api.write.enabled`
- **Type:** `bool`
- **Logic Owner:** `shadow_telemetry`
- **Mathematical/Architectural Role:**
    > Дозволяє API записувати intents від LLM, що перетворює тіньовий режим з read-only на інтерактивний/write.

## Domain: `objective_engine`
Цей домен задає глобальні налаштування для Objective Engine, математичного апарату оцінки якості сигналів.

### `domains.objective_engine.enabled`
- **Type:** `bool`
- **Logic Owner:** `objective_engine`
- **Mathematical/Architectural Role:**
    > Master toggle для Objective Engine. Якщо `false`, движок повертає `multiplier=1.0` (пропуск).
- **Invariant/Constraints:** Pydantic `extra='forbid'`.

### `domains.objective_engine.data_requirements.strict_fail_closed`
- **Type:** `bool`
- **Logic Owner:** `objective_engine`
- **Mathematical/Architectural Role:**
    > Встановлює політику fail-closed для рушія. Якщо не вистачає даних для оцінки (наприклад, volatility або spread), система блокуватиме сигнал, а не пропускатиме його.

### `domains.objective_engine.components.cost`
- **Type:** `ObjectiveComponentConfig`
- **Logic Owner:** `objective_engine`
- **Mathematical/Architectural Role:**
    > Увімкнення (`enabled: true`) та налаштування штрафів за Cost (spread, fee, slippage).
    > - `alpha_fee`: Чутливість штрафу до `base_fee_bps`.
    > - `alpha_slippage`: Чутливість до очікуваного сліпеджу.
    > - `alpha_spread`: Експоненційна або лінійна чутливість до поточного спреду.
    > - `base_fee_bps` та `slippage_from_spread_ratio`: Базові параметри калькуляції витрат.

### `domains.objective_engine.components.risk`
- **Type:** `ObjectiveComponentConfig`
- **Logic Owner:** `objective_engine`
- **Mathematical/Architectural Role:**
    > Увімкнення квадратичних штрафів за Risk (inventory utilization, volatility state).
    > - `phi_inventory`: Множник квадратичного штрафу при наближенні до максимального розміру позиції.
    > - `phi_volatility`: Чутливість до аномальної волатильності.
    > - `phi_overflow`: Штраф за перевищення лімітів (якщо застосовно).

### `domains.objective_engine.components.edge`
- **Type:** `ObjectiveComponentConfig`
- **Logic Owner:** `objective_engine`
- **Mathematical/Architectural Role:**
    > Увімкнення винагороди за математичний Edge (силу початкового сигналу).
    > - `omega_rr`, `omega_threshold_margin`, `phi_stop_distance`, `phi_rr_consistency`: Параметри оцінки якості setup-у, відстані до стопа та Risk/Reward.

### `domains.objective_engine.components.execution`
- **Type:** `ObjectiveComponentConfig`
- **Logic Owner:** `objective_engine`
- **Mathematical/Architectural Role:**
    > Увімкнення винагороди за якість Execution (ліквідність стакану).
    > - `omega_liquidity`: Винагорода за достатню ліквідність у стакані.
    > - `phi_spread_drag`, `phi_notional_pressure`: Штрафи за тиск об'єму на стакан та розширення спреду під час виконання.

### `domains.objective_engine.components.information`
- **Type:** `ObjectiveComponentConfig`
- **Logic Owner:** `objective_engine`
- **Mathematical/Architectural Role:**
    > Увімкнення штрафів за старіння інформації (regime staleness).
    > - `phi_staleness`: Лінійний штраф за кожну годину з моменту останньої зміни режиму (decaying confidence).
    > - `omega_regime_confidence`, `omega_readiness`: Оцінка впевненості у поточному ринковому режимі.

### `domains.objective_engine.components.behavior`
- **Type:** `ObjectiveComponentConfig`
- **Logic Owner:** `objective_engine`
- **Mathematical/Architectural Role:**
    > Оцінка поведінки агента (churn, rate limits).
    > - `phi_cancel_replace`, `phi_blocked_intents`, `phi_reentry`: Штрафи за надмірні скасування, заблоковані наміри або швидкі перезаходи у вікні `window_sec`.

