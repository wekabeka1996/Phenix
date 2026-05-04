# INSTRUMENTS PASSPORT
## Aurora / Phenix — canonical instruments SSOT, execution leverage, sizing, and flip orchestration

> AUDIT SUMMARY
> - Document path: config/docs/instruments_passport.md
> - Audit date: 2026-03-18
> - Audit mode: code-driven sync
> - Major drifts found:
>   None. The document is strictly accurate against current YAML and Pydantic models.
>   1. `instruments.<SYM>.symbol` metadata field remains present, while the true canonical symbol registry remains the map keys.
>   2. Execution leverage SSOT correctly reflects `instruments.<SYM>.execution.*`.
>   3. `max_notional_utilization` is still validated but has no active runtime consumer.
>   4. 7 authoritative assets are actively configured, exactly matching the current `instruments.yaml` snapshot.
> - Overall confidence: HIGH

---

## 1. Scope

This passport covers exactly one configuration surface: `config/aurora/instruments.yaml`.

It traces:

1. Canonical loading into `config.instruments`.
2. Pydantic contract and field constraints.
3. Symbol registry ownership.
4. Quantity and price normalization.
5. Live execution leverage / margin control.
6. Margin-first sizing.
7. Per-symbol flip orchestration.
8. Optional startup validation against exchange filters.

Authoritative sources traced for this passport:

- YAML: config/aurora/instruments.yaml.
- Pydantic: apps/reference/config_models.py.
- Loader: apps/reference/config_loader.py.
- Runtime: apps/reference/config_symbols.py, apps/reference/main.py, apps/reference/domains/execution_position/qty_normalizer.py, apps/reference/domains/execution_position/fsm_open.py, apps/reference/domains/execution_position/fsm.py, apps/reference/domains/execution_position/fsm_manage.py, apps/reference/domains/execution_position/leverage_service.py, apps/reference/domains/execution_position/leverage_config.py, apps/reference/domains/execution_position/bootstrapping/leverage_bootstrapper.py, apps/reference/domains/execution_position/exposure_guard.py, apps/reference/domains/decision_making/sizing_margin_first.py, apps/reference/domains/decision_making/decision_making.py.
- Startup validation: apps/reference/domains/exchange_filters/validator.py, apps/reference/main.py.
- Tests: tests/contracts/test_exchange_filters_validation.py, tests/integration/test_startup_filters_wiring.py, tests/domains/execution_position/test_task50_qty_normalizer.py, tests/domains/decision_making/test_sizing_margin_first.py, tests/domains/execution_position/test_exposure_guard_matrix_v1.py.

---

## 2. Loader and namespace wiring

### config/aurora/instruments.yaml
- Type: canonical instruments SSOT
- Logic Owner: ConfigLoader + AuroraConfig root contract
- Runtime Role: provides the root `config.instruments` map used by market-data symbol enumeration, decision-making, execution-position, exposure, and startup validation.
- Actual Runtime Semantics:
  - ConfigLoader always loads `instruments.yaml`.
  - If the file contains a top-level `instruments:` map, that map is attached to `config.instruments`.
  - Empty or missing instruments config is a startup error.
- Constraints / Invariants:
  - `trading.instruments` is explicitly forbidden and raises `ConfigContractError`.
- Status: ACTIVE

### config.instruments
- Type: `Dict[str, InstrumentPrecisionSpec]`
- Logic Owner: AuroraConfig root model
- Runtime Role: canonical runtime namespace for per-symbol precision, execution, sizing, and flip config.
- Actual Runtime Semantics:
  - The map keys are the canonical trading-symbol registry used across runtime.
  - Current configured keys are:
    - `SOLUSDT`
    - `ETHUSDT`
    - `BTCUSDT`
    - `DOGEUSDT`
    - `XRPUSDT`
    - `BNBUSDT`
    - `1000PEPEUSDT`
- Status: ACTIVE

---

## 3. Symbol registry ownership

### instruments.<SYM>.symbol
- Type: string metadata field
- Logic Owner: InstrumentPrecisionSpec
- Runtime Role: duplicated symbol label inside each per-symbol map entry.
- Actual Runtime Semantics:
  - Runtime symbol enumeration uses `list(config.instruments.keys())`.
  - `config_symbols.get_trading_symbols()` and several startup flows trust map keys, not the nested `symbol` field.
  - `validate_instruments_on_startup()` checks that `symbol` exists before building SSOTFilters, but the symbol identity passed to validation still comes from the map key.
- Constraints / Invariants:
  - No explicit Pydantic validator was found enforcing `instruments.<KEY>.symbol == <KEY>`.
- Status: METADATA / DUPLICATE

### symbol list ownership
- Type: runtime registry synthesis
- Logic Owner: config_loader + config_symbols + main
- Runtime Role: defines which symbols are seen by symbol-driven subsystems.
- Actual Runtime Semantics:
  - `get_trading_symbols()` is fail-closed and returns keys from `config.instruments`.
  - Main startup and several warmup loops iterate `config.instruments.keys()`.
- Status: ACTIVE

---

## 4. Precision and exchange constraints

### instruments.<SYM>.tick_size
- Type: positive Decimal
- Logic Owner: InstrumentPrecisionSpec + execution_position
- Runtime Role: price-grid SSOT for stop/TP quantization.
- Actual Runtime Semantics:
  - Used in execution-position stop-price quantization paths.
  - BUY stop prices are rounded upward and SELL stop prices downward by the quantizer path referenced from execution-position.
  - Missing symbol config in the relevant execution path causes fail-closed behavior.
- Constraints / Invariants:
  - Pydantic requires `tick_size > 0`.
  - Exchange filter validation can detect drift versus exchange reality at startup.
- Status: ACTIVE

### instruments.<SYM>.step_size
- Type: positive Decimal
- Logic Owner: InstrumentPrecisionSpec + qty_normalizer + sizing_margin_first
- Runtime Role: quantity-grid SSOT.
- Actual Runtime Semantics:
  - `floor_to_step()` uses strict ROUND_DOWN.
  - `normalize_qty()` uses strict ROUND_DOWN and never silently bumps quantity upward.
- Constraints / Invariants:
  - Pydantic requires `step_size > 0`.
  - If SSOT is more permissive than exchange reality, startup filter validation can fail closed when enabled.
- Status: ACTIVE

### instruments.<SYM>.min_qty
- Type: positive Decimal
- Logic Owner: InstrumentPrecisionSpec + qty_normalizer + sizing_margin_first
- Runtime Role: hard lower bound for allowed order quantity.
- Actual Runtime Semantics:
  - `normalize_qty()` rejects with `NRR-QTY-BELOW-MIN_QTY` if rounded quantity is below `min_qty`.
  - `validate_exchange_constraints()` returns `MIN_QTY` on the decision-making side.
- Status: ACTIVE

### instruments.<SYM>.min_notional
- Type: positive Decimal
- Logic Owner: InstrumentPrecisionSpec + qty_normalizer + sizing_margin_first
- Runtime Role: hard lower bound for order notional.
- Actual Runtime Semantics:
  - `normalize_qty()` rejects with `NRR-NOTIONAL-BELOW-MIN` when `qty * price < min_notional`.
  - `validate_exchange_constraints()` returns `MIN_NOTIONAL` in decision-making.
  - No silent bump-up policy exists in the traced normalization contract.
- Status: ACTIVE

---

## 5. Startup exchange filter validation

### system.validate_instruments_on_startup + validate_instruments_on_startup()
- Type: optional startup guard
- Logic Owner: main + exchange_filters validator
- Runtime Role: validates SSOT instrument constraints against exchangeInfo before runtime fully starts.
- Actual Runtime Semantics:
  - Main executes this guard only when `config.system.validate_instruments_on_startup` is true.
  - The validator compares SSOT step/min filters against exchange filters.
  - In live/production, `warn_only_filters=true` is ignored and fail-closed behavior is enforced.
  - On mismatch, `FilterMismatchError` leads to `SystemExit(1)` in startup wiring tests.
- Constraints / Invariants:
  - This is a startup guard, not a per-order runtime consumer.
- Status: ACTIVE / CONDITIONAL

---

## 6. Execution leverage contract

### instruments.<SYM>.execution.margin_mode
- Type: enum `isolated | cross`
- Logic Owner: InstrumentExecutionConfig + LeverageService + LeverageBootstrapper
- Runtime Role: expected exchange margin mode for the symbol.
- Actual Runtime Semantics:
  - `fsm_open.handle_async()` reads it before `CMD:OPEN` when leverage verification is enabled.
  - `LeverageService.set_and_verify()` sets margin mode before leverage.
  - Leverage bootstrap also syncs margin mode first.
- Status: ACTIVE

### instruments.<SYM>.execution.target_leverage
- Type: int `1..125`
- Logic Owner: InstrumentExecutionConfig + ExposureGuard + LeverageService + LeverageConfigManager
- Runtime Role: canonical leverage SSOT for execution and exposure.
- Actual Runtime Semantics:
  - Read directly by the leverage gate before `DEC:OPEN`.
  - Used by `ExposureGuard.resolve_symbol_leverage()` with no silent fallback.
  - Used by leverage bootstrap collection from `instruments.yaml`.
  - Tests confirm leverage resolution from instruments SSOT and clamp-to-one safety behavior in ExposureGuard.
- Constraints / Invariants:
  - Pydantic enforces `1 <= target_leverage <= 125`.
- Status: ACTIVE

### instruments.<SYM>.execution.leverage_policy
- Type: enum `verify_only | set_and_verify`
- Logic Owner: InstrumentExecutionConfig + fsm_open
- Runtime Role: selects whether pre-open leverage handling only verifies exchange state or actively sets it.
- Actual Runtime Semantics:
  - `verify_only` calls `LeverageService.verify()`.
  - `set_and_verify` calls `LeverageService.set_and_verify()`.
  - Failed verification or set leads to leverage-gate rejection before order emission.
- Status: ACTIVE

### instruments.<SYM>.execution.max_notional_utilization
- Type: float `0.0..1.0`
- Logic Owner: InstrumentExecutionConfig + ConfigLoader live validation
- Runtime Role: live contract field with no confirmed downstream runtime consumer in traced code.
- Actual Runtime Semantics:
  - Required by `_validate_execution_config_for_live()` for active symbols.
  - No concrete execution-position, exposure, or decision-making gate was found reading it after startup validation.
- Status: DECLARED BUT NOT USED

### leverage SSOT precedence
- Type: runtime authority rule
- Logic Owner: LeverageConfigManager
- Runtime Role: resolves conflict between legacy strategy-side leverage and instruments execution leverage.
- Actual Runtime Semantics:
  - Leverage bootstrap now collects values from `instruments.<SYM>.execution.target_leverage`.
  - `validate_ssot_consistency()` logs warnings when strategy-level leverage in Aurora or Mean Reversion assets disagrees with instruments SSOT.
  - Mismatching strategy-side leverage is explicitly treated as ignored legacy/stale data.
- Status: ACTIVE

---

## 7. Margin-first sizing

### instruments.<SYM>.sizing.margin_pct
- Type: float `(0, 1]`
- Logic Owner: InstrumentSizingConfig + sizing_margin_first + ConfigLoader live validation
- Runtime Role: per-symbol isolated margin budget.
- Actual Runtime Semantics:
  - `compute_notional_target()` calculates:
    `safe_equity = equity * (1 - fee_buffer)`
    `margin_usdt = safe_equity * margin_pct`
    `notional_target = margin_usdt * leverage`
  - `compute_qty()` then floors quantity to `step_size`.
  - Live validation requires this field for active symbols.
- Constraints / Invariants:
  - Pydantic enforces `0 < margin_pct <= 1`.
- Status: ACTIVE

---

## 8. Flip orchestration

### instruments.<SYM>.flip.enabled
- Type: required bool
- Logic Owner: FlipOrchestrationConfig + DecisionMaking
- Runtime Role: per-symbol enable switch for close-first flip orchestration.
- Actual Runtime Semantics:
  - If the global flip killswitch is disabled in domains config, DecisionMaking returns `(False, 1.0)` and per-symbol flip config is bypassed.
  - If global flip is enabled, missing symbol config or missing `flip` block is fail-closed.
  - When present, `flip.enabled` governs whether flip orchestration is active for that symbol.
- Status: ACTIVE

### instruments.<SYM>.flip.hysteresis_mult
- Type: required float `>= 1.0`
- Logic Owner: FlipOrchestrationConfig + DecisionMaking
- Runtime Role: requires a stronger opposite signal before reduce-only close during flip.
- Actual Runtime Semantics:
  - DecisionMaking clamps the runtime value with `max(1.0, float(...))`.
  - The hysteresis value is part of the per-symbol flip contract and is required whenever the symbol exists in `config.instruments`.
- Constraints / Invariants:
  - Pydantic enforces `hysteresis_mult >= 1.0`.
- Status: ACTIVE

---

## 9. Current configured snapshot

Current instrument keys and notable execution parameters in `instruments.yaml`:

- `SOLUSDT`: integer lot sizing, leverage `20`, margin mode `isolated`, `margin_pct=0.11`
- `ETHUSDT`: leverage `41`, margin mode `isolated`, `margin_pct=0.11`
- `BTCUSDT`: leverage `25`, margin mode `isolated`, `margin_pct=0.10`, `tick_size=0.1`, `min_notional=100`
- `DOGEUSDT`: `tick_size=0.00001`, leverage `20`, margin mode `isolated`, integer lot sizing
- `XRPUSDT`: `tick_size=0.0001`, leverage `20`, margin mode `isolated`, `step_size=0.1`
- `BNBUSDT`: leverage `20`, margin mode `isolated`, `margin_pct=0.11`
- `1000PEPEUSDT`: leverage `20`, margin mode `isolated`, very fine `tick_size=0.0000001`

---

## 10. Legacy and drift ledger

### instruments.<SYM>.symbol as canonical identity
- Type: stale assumption
- Actual Runtime Semantics:
  - Canonical symbol identity comes from the map key, not the nested `symbol` field.
- Status: LEGACY

### strategy-side leverage as runtime SSOT
- Type: stale assumption
- Actual Runtime Semantics:
  - Strategy leverage can still exist in strategy configs, but execution bootstrap now treats instruments execution leverage as the authority.
- Status: LEGACY

### max_notional_utilization
- Type: typed live-contract field
- Actual Runtime Semantics:
  - Enforced at startup validation only; no active runtime consumer found.
- Status: DECLARED BUT NOT USED

### exchange filter matching as unconditional runtime rule
- Type: corrected assumption
- Actual Runtime Semantics:
  - Validation is conditional on `system.validate_instruments_on_startup`.
  - When enabled in live/prod, mismatches are fail-closed.
- Status: PARTIAL

---

## 11. Final verdict

`config/aurora/instruments.yaml` is a verified, fully up-to-date SSOT for:

1. the canonical symbol registry via `config.instruments` keys,
2. exchange-facing quantity and price constraints,
3. pre-open leverage and margin-mode enforcement,
4. margin-first sizing inputs,
5. per-symbol flip orchestration,
6. optional startup exchange-filter validation.

This document contains no major out-of-date information against current YAML and Pydantic behaviors.
