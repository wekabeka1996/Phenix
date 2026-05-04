# 🛡️ DECISION MAKING: FORENSIC PROOF PACK REPORT

This document consolidates all proof pack artifacts generated during the deep forensic audit of the `decision_making` domain.

---

## 1. Safety Gates Defect Remediation
- **Files Changed:** 
  - `apps/reference/domains/decision_making/safety_gates.py` 
  - `tests/domains/decision_making/test_safety_gates_config_v1.py`
- **What changed:** 
  - Fixed a critical `try...except Exception` block in `_resolve_stress_policy` that swallowed config resolution / typing errors and returned a completely silent bypass (`"off", 1.0`).
  - Redefined the fail-state output to `"CONFIG_ERROR", 0.0`.
  - Upgraded the handler `_check_system_stress_gate` to treat `stress_policy == "CONFIG_ERROR"` as an absolute DENY returning `NRR-054` (`CONFIG_SAFETY_GATES_MISSING`).
- **Exact Tests Run:** 
  - `python -m pytest tests/domains/decision_making/test_safety_gates_config_v1.py`
- **Results:** 
  - 9/9 Passed (100% coverage on the new fail-closed block).
- **Remaining Risks (Safety Gates):** 
  - `price_motion_sanity` gates explicitly bypass validation if the configuration flags `is_backtest = True`. This poses a silent parity drift.

---

## 2. SSOT / CONFIG WIRING MATRIX

| Config Key | Declared In | Loaded By | Consumed By | Runtime Status | Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `domains.decision_making.risk_skew` | `domains.yaml` | `AuroraConfig` | `strategy_gateway.py`, `decision_making.py` | ACTIVE_RUNTIME | `strategy_gateway.py:46`, `decision_making.py:364` |
| `domains.decision_making.price_motion_sanity` | `domains.yaml` | `AuroraConfig` | `safety_gates.py` | ACTIVE_RUNTIME | `safety_gates.py:233` |
| `domains.decision_making.directional_sanity` | `domains.yaml` | `AuroraConfig` | `safety_gates.py` | ACTIVE_RUNTIME | `safety_gates.py:444` |
| `domains.decision_making.position_sizing` | `domains.yaml` | `AuroraConfig` | `aurora_handler.py`, `md_amr_handler.py`, `mean_reversion_handler.py` | ACTIVE_RUNTIME | `aurora_handler.py:82`, `md_amr_handler.py:81`, `mean_reversion_handler.py:165` |
| `domains.decision_making.risk_gate` | `domains.yaml` | `AuroraConfig` | `intent_emitter.py` | ACTIVE_RUNTIME | `intent_emitter.py:232` |
| `strategies.<id>.safety_gates.system_stress_policy` | `strategies/*.yaml` | `AuroraConfig` | `safety_gates.py` | ACTIVE_RUNTIME | `safety_gates.py:307` |
| `mean_reversion.enabled` | `strategies/mean_reversion.yaml` | `AuroraConfig` | `mean_reversion_handler.py` | LEGACY/SHADOWED | Treated as global kill-switch, but activation uses `strategies_registry.assignments` |
| `strategies.aurora.decision` | `strategies/aurora.yaml` | `AuroraConfig` | `aurora_handler.py` | ACTIVE_RUNTIME | Extensively mapped |

---

## 3. CONTRACT DRIFT TABLE

| Input/Output Contract | Schema/Model Location | Runtime Consumer/Emitter | Hidden Assumptions | Mismatch/Drift/Nullable Risk | Evidence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `CMD:PROCESS_STRATEGY` | `vfoundation.core.protocol.Message` | `DecisionMaking` (Facade) -> `StrategyGateway` | Assumes payload has `strategy_id`, `features`, `symbol`. | `features` can be missing (handled by missing data fallbacks, but risks silent drops if not gate-checked). | `strategy_gateway.py:12` |
| `EVT:TRADE_INTENT_PROPOSED` | `vfoundation.core.protocol.Message` | Emitter: `IntentBuilder` / Consumer: `Neocortex` | Assumes `lifecycle_id`, `why_chain`, `decision_ts_ms` are present. | `lifecycle_id` may drift if Phase 0 alignment (producer-side) isn't respected by neocortex. | `intent_emitter.py:248` |
| `EVT:FEATURES_CALCULATED` | `Message` | `StrategyGateway` -> Handlers | Assumes `price_motion` and `volatility` blocks exist in payload. | `pm_norm_10s` extracted by `_extract_price_motion` can raise `TypeError` if malformed, handled defensively. | `safety_gates.py:86` |
| `EVT:REGIME_DETECTED` | `Message` | `StrategyGateway` -> `AuroraHandler`, `MeanReversionHandler` | Assumes `regime` is string and `confidence` is float. | High risk if detector returns `"UNCERTAIN"` string, handled by fallback to default multiplier. | `aurora_handler.py:392` |
| `PORTFOLIO_STATE_PAYLOAD` | `schemas.py` | Emitter: Execution / Consumer: `DecisionMaking` | Assumes `equity` > 0. | if `equity` is 0 or missing, `sizing_margin_first.py` raises ValueError (Fail-closed). | `schemas.py:1` |

---

## 4. IMPORT / BOUNDARY MAP

### Who Imports Decision Making
- `apps/reference/core/engine/bus_router.py` (Wires events to `DecisionMaking` facade)
- `tests/domains/decision_making/*` (Tests)

### What Decision Making Imports
**Allowed/Expected Base Dependencies:**
- `vfoundation.core.protocol` (Message definitions)
- `vfoundation.dr` (WAL tracing)
- `apps.reference.config_models` (AuroraConfig validation limits)
- `apps.reference.telemetry.metrics` (Metric increments)

**Suspicious / Architectural Violations:**
- `from apps.reference.domains.feature_engineering.mean_reversion_strategy import MeanReversion1mStrategy` (`strategy_bridge.py:27`)
- `from apps.reference.domains.feature_engineering.md_amr_strategy import MDAMRStrategyV11` (`strategy_bridge.py:38`)
- `from apps.reference.domains.feature_engineering.regime_mapping import ...` (`strategy_bridge.py:44`)

**Assessment:** `decision_making` is directly coupling to `feature_engineering` strategy implementations, violating strict domain isolation. `decision_making` should only receive generic signals, feature vectors, or intent proposals via the event bus, rather than importing concrete strategy objects from FE. This is a significant modularity violation.

---

## 5. DEAD CODE / DEAD CONFIG REPORT

### Deprecated Scoring Paths
- `signal_score_v2.py`: The `SignalScoreV2` module is entirely superseded by `quadratic_scoring_kernel.py`. It remains in the tree as legacy fallback but is not actively sourced by modernized Aurora configurations.
- `scoring_direction_strength_v1.py`: Deprecated legacy mathematical scoring mechanism. No current runtime usages found in primary active branches (`aurora_handler.py`, `md_amr_handler.py`, `mean_reversion_handler.py`).

### Unused Modules
- `strategy_bridge.py`: Acts purely as an anti-pattern proxy importing `feature_engineering` models to DM handlers. It technically executes but represents "dead architecture" that violates domain isolation.

### Dead / Shadowed Flags
- `mean_reversion.enabled`: Exists in YAML config schemas, but `mean_reversion_handler.py` relies on `strategies_registry.assignments` contextually. It acts as a hard kill-switch but duplicates SSOT concepts structurally.

### Misleading Comments/Docs (Resolved)
- `safety_gates.py` at line 296 stated `Falls back to ("off", 1.0) on any missing/bad config — fail-open`. This comment and accompanying logic have been explicitly patched to `CONFIG_ERROR` fail-closed methodology.

---

## 6. LIVE / TESTNET / BACKTEST PARITY AUDIT

### Explicit Mode Branches

1. **`safety_gates.py` (Price Motion Insufficient Bypass)**:
   - `is_backtest = str(getattr(config, "trading_mode", "")).strip().lower() == "backtest"`
   - `if (... or is_backtest): return "ALLOW", None, "ok"`
   - *Risk:* Price motion gates are explicitly, and somewhat dangerously, bypassed during backtests. This introduces a parity gap where high-volatility flash/bleed rejection happens live/testnet but fails to constrain backtest profitability.

2. **`strategy_gateway.py` (Deferred Intents / Shadowing)**:
   - `if mode == "shadow":` (Silences intent emission strictly).
   - `if mode == "defer":` (Pushes through Deferred Intent Scheduler).
   - *Risk:* Shadow mode effectively runs everything but isolates mutation.

3. **`shields/memory_shield.py` (Deterministic RAM)**:
   - `storage_path=None → RAM-only (safe for backtest & default).`
   - *Risk:* Live relies on durable storage for unfamiliar regime states, while backtest uses memory. If instances crash, testnet drops memory shields while live retains them.

4. **`mean_reversion_handler.py` / `deferred_scheduler.py` (Deterministic Clocks)**:
   - `# DET-BT-09: Use get_clock() for deterministic backtest`
   - *Result:* High Parity. Using injected `clock.now_ms()` ensures clock synchronization between bar timestamps and evaluator times, preventing future-peeking in backtests.

5. **`md_amr_handler.py` (API Environmental Split)**:
   - `api_env = self.config.binance_api.live if mode == "live" else self.config.binance_api.testnet`
   - *Result:* Explicitly correctly segregated.

**Assessment:** The system exhibits aggressive clock determinism (`get_clock()`). However, the manual exclusion of `price_motion_sanity` gates in purely `backtest` scenarios artificially inflates simulated yield against historical tapes. This is the **primary parity risk**.

---

## 7. TEST GAP MAP

### Coverage of Critical Subsystems
| Subsystem | Existing Tests | Gap / Missing | Priority |
| :--- | :--- | :--- | :--- |
| **Safety Gates** | `test_safety_gates_config_v1.py`, `test_directional_sanity_gate.py` | Lacks integration test combining all gates under extreme conditions (Gate 0 + 1 + 2 + 3 combined stress test). | Medium |
| **Aurora Scoring** | `test_aurora_quadratic_logging.py`, `test_aurora_volatility_logic.py`, `test_aurora_vol_adj_gates.py` | Missing branch coverage for `NullShield` explicit bypass logic (`if not True`). | Low |
| **Flip Orchestrator** | `test_flip_orchestration_v1.py`, `test_flip_initiate_direct_cmd_close.py` | Deeply covered. Extensive suite verifying hysteresis, anti-pyramiding, and event emits. | None |
| **Sizing Margin First** | `test_sizing_margin_first.py` | Lacks tests handling `leverage < 1` bounds specifically when `margin_pct` == 1. | Medium |
| **Readiness Gates** | `test_aurora_runtime_readiness_contract.py`, `test_md_amr_runtime_readiness.py` | Extensively covered. All combinations of TTL and warmup flags validated. | None |
| **Config Resolution Fail-Closed** | `test_safety_gates_config_v1.py:TestSystemStressPolicyFailClosed` | Missing tests for `md_amr_handler` resolving `position_sizing` block if entirely absent. | High |

### Highest Priority Additions
1. **Config Absence Tests for Adapters**: Ensure `md_amr_handler` and `mean_reversion_handler` fail-closed strictly when completely missing `position_sizing` configurations from the central SSOT.
2. **Price Motion Bypass Test**: Test explicitly validating the backtest disparity mechanism within `safety_gates.price_motion_sanity`.

---

## 8. JOURNAL / TODO Updates Required
1. **[Architecture Refactor]:** Deprecate `strategy_bridge.py` and remove direct imports of `feature_engineering.mean_reversion_strategy` from DM handlers. DM should only receive message schemas (`Message`), not concrete class implementations.
2. **[Testing]:** Add missing integration test for completely absent `position_sizing` config blocks acting against the generic `AuroraConfig` parser.
3. **[Cleanup]:** Delete `signal_score_v2.py` and `scoring_direction_strength_v1.py` as they are provably dead code paths with no active references across registry bounds.
