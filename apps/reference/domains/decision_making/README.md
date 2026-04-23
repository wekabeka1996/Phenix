# Decision Making Domain

## Responsibility
Central decision engine that receives upstream data (features, risk, regime, portfolio, exposure),
dispatches to strategy handlers, and produces trade intents (proposed / rejected / deferred).

Owns: strategy dispatch, intent construction, safety gating, sizing, flip orchestration,
QoS rate control, and reject normalization (NRR).

## Contract SSOT Alignment
- **WhyCode**: re-exported from `vfoundation/core/why_codes.py` (canonical SSOT)
- **NRR**: `normalized_reject_reasons.py` (canonical SSOT)
- **Events**: registered in `verb_registry_v1.yaml` with `owner: decision_making`
- **Schemas**: `schemas/` directory (JSON Schema) + `schemas.py` / `schemas_decision_blocked.py` (Pydantic)
- See `docs/contracts/CONTRACT_ARCHITECTURE.md` for full rules

## File Map

### Core Orchestration
| File | Purpose |
|------|---------|
| `decision_making.py` | Thin facade: FSM event subscriptions, stress/exposure caching |
| `event_handlers.py` | DMEventHandlers: alpha score computation, ConfigContractError handling |
| `strategy_gateway.py` | Signal routing, degrade/flip dispatch |
| `intent_builder.py` | Trade intent construction, safety gates, CAS guard |
| `intent_emitter.py` | Event emission helpers (deferred, rejected, proposed) |
| `flip_orchestration.py` | Flip lifecycle (close-then-open) |
| `readiness_gates.py` | Warmup / readiness pre-checks |

### Strategy Handlers
| File | Purpose |
|------|---------|
| `aurora_handler.py` | Aurora strategy handler (5m bars) |
| `md_amr_handler.py` | MD-AMR strategy handler (5m bars, adaptive mean reversion) |
| `mean_reversion_handler.py` | MR strategy handler (1m/3m bars) |
| `strategy_bridge.py` | **Sanctioned DM-facing re-export facade** for strategy classes hosted in feature_engineering (FE-DM-BOUNDARY-STABILIZATION 2026-03-15) |

### Aurora Subsystem
| File | Purpose |
|------|---------|
| `aurora_decision.py` | Aurora decision logic, quadratic kernel, inception filter |
| `aurora_config_loader.py` | Aurora YAML config loading |
| `aurora_scoring_helpers.py` | Side bias, cooldown timer helpers |
| `aurora_holding_period.py` | Minimum holding period gate |
| `aurora_tpsl.py` | Take-profit / stop-loss calculation |

### Scoring
| File | Purpose |
|------|---------|
| `quadratic_scoring_kernel.py` | QuadraticScoringKernel, ScoringResult, SideBiasState |

### Gates & Shields
| File | Purpose |
|------|---------|
| `safety_gates.py` | Configurable safety gate pipeline |
| `execution_gate.py` | Exposure / hard-veto pre-checks |
| `inception_filter.py` | Regime + confidence eligibility |
| `shields/` | Base, ContextShield, DangerZone, MemoryShield, NullShield |

### Services & Utilities
| File | Purpose |
|------|---------|
| `normalized_reject_reasons.py` | NRR canonical SSOT (60 codes) |
| `why_codes.py` | Re-export shim from `vfoundation/core/why_codes.py` |
| `sizing_margin_first.py` | Margin-first position sizing |
| `instrument_quantizer.py` | Exchange lot/step size quantization |
| `decision_context.py` | DecisionContext builder |
| `deferred_scheduler.py` | QoS retry scheduling |
| `qos_rate_control.py` | Per-strategy rate limiting |
| `operational_mode.py` | Mode manager (live/paper) |
| `position_queries.py` | Portfolio position queries |
| `config_resolver.py` | Strategy config resolution |
| `entry_plan.py` | Entry plan builder (Entry/SL/TP, OBI modulation) |
| `exit_manager.py` | Exit condition evaluation |
| `regime_smoother.py` | EMA regime multiplier smoother |

### Observability
| File | Purpose |
|------|---------|
| `dm_log_adapter.py` | DecisionLog structured logging |
| `mean_reversion_logger.py` | MR-specific bar logging |
| `trade_intent_reject_wal.py` | WAL for rejected intents |
| `dashboard.py` | Telemetry dashboard snapshot |

## Event Map

### Consumed (13)
| Event | Source |
|-------|--------|
| CMD:PROCESS_STRATEGY | feature_engineering |
| EVT:BAR_CLOSED | market_data |
| EVT:EXPOSURE_SUMMARY_UPDATED | risk_management |
| EVT:FEATURES_CALCULATED | feature_engineering |
| EVT:ORDER_REJECTED | execution_position |
| EVT:ORDER_STATE_CHANGED | execution_position |
| EVT:PORTFOLIO_STATE_UPDATED | position_tracking |
| EVT:REGIME_DETECTED | regime_detector |
| EVT:RISK_ASSESSMENT_COMPLETED | risk_management |
| EVT:STRATEGY_SIGNAL_PRODUCED | self (internal routing) |
| EVT:SYSTEM_STRESS_STATE_UPDATED | system_stress |
| EVT:TRADE_EXECUTED | position_tracking |
| EVT:TRADE_INTENT_REJECTED | self (retry feedback) |

### Emitted (12)
| Event | Emitter |
|-------|---------|
| CMD:CLOSE | flip_orchestration.py |
| EVT:ALPHA_SCORES_AGGREGATED | event_handlers.py |
| EVT:DECISION_BLOCKED | event_handlers.py |
| EVT:DECISION_TRACE_EMITTED | decision_making.py, intent_builder.py |
| EVT:FEATURE_DEFER_EXPIRED | md_amr_handler.py |
| EVT:INTENT_DEFERRED | intent_emitter.py, intent_builder.py |
| EVT:QUADRATIC_KERNEL_CRASH | aurora_decision.py |
| EVT:REGIME_SHIFT_SUSPECTED | aurora_decision.py |
| EVT:STRATEGY_DECISION_BLOCKED | aurora_handler.py, mean_reversion_handler.py |
| EVT:STRATEGY_SIGNAL_PRODUCED | aurora_decision.py, md_amr_handler.py, mean_reversion_handler.py |
| EVT:TRADE_INTENT_PROPOSED | intent_builder.py |
| EVT:TRADE_INTENT_REJECTED | intent_emitter.py, md_amr_handler.py |

## Aurora Semantic Note
For Aurora, the current proven semantics are:

- `EVT:STRATEGY_DECISION_BLOCKED` is the dominant live no-trade class for ordinary
  policy/readiness outcomes such as regime allowlist denial or cold-start bars gating.
- `EVT:INTENT_DEFERRED` remains valid on the Aurora path, but it is currently a
  narrow anomaly/fail-closed class after the quadratic path is reached, not the
  dominant live "cannot trade now" outcome.

## Supplemental Docs
The `docs/` subdirectory contains auto-generated analysis documents from earlier audits.
Some reference deleted files and are partially stale. Treat the **this README** as the
authoritative domain reference.

- `docs/ARCHITECTURE.md` — internal architecture notes
- `docs/ALGORITHMS_AND_MATH.md` — scoring/sizing math
- `docs/EVENT_CONTRACTS.md` — event contract details
- `docs/QUALITY_AND_DEBT.md` — tech debt analysis
- `docs/TESTING.md` — test strategy notes

## Development Guidelines
- When modifying Aurora scoring: edit `quadratic_scoring_kernel.py` (math) or `aurora_handler.py` (state management)
- When adding new WhyCode members: add to `vfoundation/core/why_codes.py`, NOT to local `why_codes.py`
- When adding new NRR codes: add to `normalized_reject_reasons.py`
- When adding new events: register in `verb_registry_v1.yaml` first

## FE↔DM Boundary Policy (2026-03-15)

Strategy math cores (`MeanReversion1mStrategy`, `MDAMRStrategyV11`, `FlatRegime`, `regime_mapping`)
currently live in `feature_engineering/` for historical reasons but are **semantically owned by decision_making**.

### Sanctioned import path
DM production code MUST import strategy artifacts via the bridge facade:
```python
from apps.reference.domains.decision_making.strategy_bridge import (
    MeanReversion1mStrategy, MRSignal, MRSignalType, MRStrategyConfig,
    MDAMRStrategyV11, MDAMRSignal,
    FlatRegime, FlatRegimeThresholds, map_to_flat_regime, MRParameters,
)
```

### Forbidden patterns
- Do NOT import `apps.reference.domains.feature_engineering.mean_reversion_strategy` from DM production code
- Do NOT import `apps.reference.domains.feature_engineering.md_amr_strategy` from DM production code
- Do NOT import `apps.reference.domains.feature_engineering.regime_mapping` from DM production code
- Bar (`apps.reference.domains.feature_engineering.bar_resampler.Bar`) is a shared helper — use `apps.reference.shared.types.Bar`

### Future migration
A dedicated package will physically move strategy files to DM and replace `strategy_bridge.py`
with backward-compatible shims in FE.
