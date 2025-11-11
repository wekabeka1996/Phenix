# Alpha Search: Full Integration and Implementation Plan (FSM, No Defaults)

Status: draft v1
Owner: alpha_search domain lead
Date: 2025-11-11
Scope: Analysis-driven plan to fully enable alpha_search as an FSM domain in QuantumTraderX/vFoundation without defaults/fallbacks; contracts-first with JSON Schema 2020-12; no code changes done yet.

---

## 0. Executive summary

- Current state: alpha_search exists as a library of models + ensemble, but it is not an FSM domain yet (no event handler, no emission, ensemble uses empty features). Contracts and docs exist, but implementation gaps block production use.
- Goal: turn alpha_search into a first-class FSM domain that consumes FEATURES_CALCULATED events, produces ALPHA_SCORE_CALCULATED events, integrates cleanly with DecisionMaking and RiskManagement, and runs without defaults/fallbacks.
- Strategy: contracts-first (schemas + dictionaries), feature readiness gating, strict validation, deterministic event payloads, and safe QoS. Phased rollout to avoid cascading failures.

---

## 1. Domain role and dataflow (contracts-first)

Alpha Search domain computes alpha scores ([-1,+1]) per symbol from feature vectors, with calibrated confidence [0,1] and explainability (why-chain). It:
- Consumes EVT:FEATURES_CALCULATED from FeatureEngineering
- Emits EVT:ALPHA_SCORE_CALCULATED to DecisionMaking
- Optionally ingests Risk context for weighting/filters

High-level flow:
1) FeatureEngineering → EVT:FEATURES_CALCULATED
2) AlphaSearch.FSM handler → validates features → runs registered models → ensemble combination → EVT:ALPHA_SCORE_CALCULATED
3) DecisionMaking consumes alpha_scores as an input to opportunity evaluation
4) RiskManagement feedback (PnL/hit-rate) updates ensemble weights asynchronously

Success criteria:
- Zero defaults/fallbacks in signal computation. If required features missing, model is skipped; if all skipped, no alpha event is emitted for that symbol/tick.
- Strict schema compliance and timestamp format consistency (ms as integer).
- WHY-chain coverage per model and ensemble (≤ 10 items, deterministic wording).

---

## 2. Contracts and schemas (JSON Schema 2020-12)

Place these under `apps/reference/domains/alpha_search/schemas/` (to be created):

### 2.1 Input event (consumed)
File: features_calculated_input_v1.json
- Canonical minimal projection of features event needed by alpha_search
- $id required, 2020-12 draft

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "alpha_search.features_input.v1.schema.json",
  "type": "object",
  "properties": {
    "ts": {"type": "integer", "minimum": 0},
    "symbol": {"type": "string", "pattern": "^[A-Z0-9]{1,20}$"},
    "features": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "price": {"type": ["string", "number"]},
        "ema_bias": {"type": ["string", "number"]},
        "volume_spike": {"type": ["string", "number"]},
        "volatility_state": {"type": ["string", "number"]},
        "depth_imbalance": {"type": ["string", "number"]},
        "macro_sync": {"type": ["string", "number"]},

        "price_momentum_5m": {"type": ["string", "number"]},
        "price_momentum_1h": {"type": ["string", "number"]},
        "price_momentum_1d": {"type": ["string", "number"]},
        "volume_momentum_5m": {"type": ["string", "number"]},
        "rsi_14": {"type": ["string", "number"]},
        "macd_signal": {"type": ["string", "number"]},
        "bb_position": {"type": ["string", "number"]},
        "bb_width": {"type": ["string", "number"]},
        "price_sma_20_deviation": {"type": ["string", "number"]},
        "volume_sma_ratio": {"type": ["string", "number"]},
        "stoch_k": {"type": ["string", "number"]},
        "stoch_d": {"type": ["string", "number"]},
        "atr_14": {"type": ["string", "number"]},
        "atr_ratio": {"type": ["string", "number"]},
        "bb_width_change": {"type": ["string", "number"]},
        "realized_volatility_1h": {"type": ["string", "number"]},
        "realized_volatility_1d": {"type": ["string", "number"]},
        "volume_volatility_ratio": {"type": ["string", "number"]},
        "price_range_ratio": {"type": ["string", "number"]}
      }
    }
  },
  "required": ["ts", "symbol", "features"]
}
```

Notes:
- Momentum/mean-reversion/volatility inputs are currently NOT produced by FeatureEngineering. They must be added (see §4.2).

### 2.2 Output event (emitted)
File: alpha_score_calculated_v1.json

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "alpha_search.alpha_score.v1.schema.json",
  "type": "object",
  "properties": {
    "ts": {"type": "integer", "minimum": 0},
    "rid": {"type": "string"},
    "model_name": {"type": "string"},
    "symbol": {"type": "string", "pattern": "^[A-Z0-9]{1,20}$"},
    "score": {"type": "number", "minimum": -1, "maximum": 1},
    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    "features_used": {"type": "array", "items": {"type": "string"}},
    "why": {"type": "array", "items": {"type": "string"}},
    "contributions": {
      "type": "object",
      "additionalProperties": {
        "type": "object",
        "properties": {
          "score": {"type": "number"},
          "weight": {"type": "number"},
          "contribution": {"type": "number"}
        },
        "required": ["score", "weight", "contribution"]
      }
    }
  },
  "required": ["ts", "model_name", "symbol", "score", "confidence"]
}
```

### 2.3 Config schema (domain-level)
File: alpha_search_config_v1.json

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "alpha_search.config.v1.schema.json",
  "type": "object",
  "properties": {
    "enabled": {"type": "boolean", "default": true},
    "models": {
      "type": "object",
      "properties": {
        "momentum_v1": {"type": "object", "properties": {"enabled": {"type": "boolean", "default": true}}},
        "mean_reversion_v1": {"type": "object", "properties": {"enabled": {"type": "boolean", "default": true}}},
        "volatility_v1": {"type": "object", "properties": {"enabled": {"type": "boolean", "default": true}}}
      },
      "additionalProperties": false
    },
    "ensemble": {
      "type": "object",
      "properties": {
        "enabled": {"type": "boolean", "default": true},
        "rebalance_frequency_days": {"type": "integer", "minimum": 1, "default": 7},
        "min_weight": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.0},
        "max_weight": {"type": "number", "minimum": 0, "maximum": 1, "default": 1.0},
        "performance_window_days": {"type": "integer", "minimum": 1, "default": 30},
        "risk_adjustment": {"type": "boolean", "default": true},
        "performance_source": {"type": "string", "enum": ["pnl", "hit_rate", "confidence"], "default": "pnl"}
      },
      "required": ["enabled"]
    },
    "qos": {
      "type": "object",
      "properties": {
        "max_compute_ms": {"type": "integer", "minimum": 1, "default": 20},
        "max_models": {"type": "integer", "minimum": 1, "default": 10},
        "require_features_ready": {"type": "boolean", "default": true},
        "emit_on_no_scores": {"type": "boolean", "default": false}
      }
    }
  },
  "required": ["enabled", "models", "ensemble"]
}
```

---

## 3. Dictionaries (feature dictionary v1)

Place under `dictionaries/alpha_features.yaml` (to be created): a single source of truth for feature names, units, windows, producers.

Example entries (non-exhaustive; FeatureEngineering must implement them):

```yaml
version: 1
namespace: alpha_search
features:
  price_momentum_5m:
    description: Rate of change over 5 minutes
    formula: (price_now - price_5m_ago)/price_5m_ago
    unit: ratio
    window: 5m
    producer: feature_engineering
  price_momentum_1h:
    description: Rate of change over 1 hour
    unit: ratio
    window: 1h
    producer: feature_engineering
  price_momentum_1d:
    description: Rate of change over 1 day
    unit: ratio
    window: 1d
    producer: feature_engineering
  volume_momentum_5m:
    description: Volume change vs SMA(5) on 1m bars aggregated to 5m
    unit: ratio
    window: 5m
    producer: feature_engineering
  rsi_14:
    description: Relative Strength Index (14)
    unit: index
    window: rolling
    producer: feature_engineering
  macd_signal:
    description: MACD line - signal line
    unit: index
    window: rolling
    producer: feature_engineering
  bb_position:
    description: Bollinger %B in [0,1]
    unit: fraction
    window: rolling
    producer: feature_engineering
  bb_width:
    description: Width (upper-lower)/middle
    unit: ratio
    window: rolling
    producer: feature_engineering
  price_sma_20_deviation:
    description: (price - SMA20)/SMA20
    unit: ratio
    window: 20 periods
    producer: feature_engineering
  volume_sma_ratio:
    description: volume/SMA(volume)
    unit: ratio
    window: rolling
    producer: feature_engineering
  stoch_k:
    description: Stochastic %K
    unit: percent
    window: rolling
    producer: feature_engineering
  stoch_d:
    description: Stochastic %D
    unit: percent
    window: rolling
    producer: feature_engineering
  atr_14:
    description: Average True Range 14
    unit: price
    window: 14
    producer: feature_engineering
  atr_ratio:
    description: ATR/SMA(ATR)
    unit: ratio
    window: rolling
    producer: feature_engineering
  bb_width_change:
    description: d(bb_width)/dt (1m diff)
    unit: ratio
    window: 1m
    producer: feature_engineering
  realized_volatility_1h:
    description: sqrt(sum(returns^2)) over 1h
    unit: sigma
    window: 1h
    producer: feature_engineering
  realized_volatility_1d:
    description: sqrt(sum(returns^2)) over 1d
    unit: sigma
    window: 1d
    producer: feature_engineering
  volume_volatility_ratio:
    description: volume z-score vs volatility z-score
    unit: ratio
    window: rolling
    producer: feature_engineering
  price_range_ratio:
    description: intraperiod range / SMA(range)
    unit: ratio
    window: rolling
    producer: feature_engineering
```

---

## 4. Gaps identified (must-fix before wiring)

1) FeatureEngineering does not produce required alpha features (momentum, RSI, MACD, BB, ATR, etc.).
   - Action: extend FeatureEngineering to compute and emit the dictionary features above (preserve current metrics; additive-only).
   - Blocker severity: critical – without this alpha_search cannot operate without defaults.

2) No FSM wrapper for alpha_search; no event listening/emission.
   - Action: implement `AlphaModelFSM` that subscribes to `EVT:FEATURES_CALCULATED`, validates input (against schema), runs models, emits `EVT:ALPHA_SCORE_CALCULATED` (v1 schema) with ms timestamp.

3) Ensemble currently feeds empty features `{}` into child models.
   - Action: pass through the exact `features` dict from the event; remove any use of defaults; models run only when `is_ready` true.

4) Output event mismatch: timestamp format (ISO vs ms) and missing `contributions`.
   - Action: standardize alpha event to ms integer; include `contributions` for ensemble; add `rid` for tracing.

5) Weighting proxy uses `confidence` instead of real outcomes.
   - Action: define a `performance_source` config. For production: use PnL or hit-rate from Risk/Execution telemetry; fall back to confidence only in dev.

6) Config presence: no domain-level config in YAML.
   - Action: add `trading.domain_configuration.alpha_search.trading_mode` and `trading.alpha_search` block mirroring the JSON schema (§2.3). Ensure ConfigLoader maps to Pydantic model.

---

## 5. Integration plan (phased, additive-only)

### Phase A: Contracts and wiring (no behavior change elsewhere)
- A1. Add schemas under `apps/reference/domains/alpha_search/schemas/` (input/output/config). Register them in docs.
- A2. Add dictionary `dictionaries/alpha_features.yaml`.
- A3. Implement `AlphaModelFSM` (new file) with:
  - subscribe: `EVT:FEATURES_CALCULATED`
  - validate payload via schema (reject if invalid; no defaults)
  - build `AlphaModelRegistry` from config (enabled models only)
  - compute per-model scores (only if `is_ready`)
  - if at least one score -> combine via EnsembleModel → emit `EVT:ALPHA_SCORE_CALCULATED` (schema v1), else no-op
  - attach `rid`, `ts` (ms), `why`
- A4. Configure domain activation in `config/aurora/trading.yaml`:
  - `domain_configuration.alpha_search.trading_mode: "live"` (read-only)
  - `trading.alpha_search`: section per §2.3
- A5. Logging and metrics: create `logs/domain_alpha_search.log`, counters for model readiness, emissions, duration.

### Phase B: FeatureEngineering extension (additive)
- B1. Compute and emit all dictionary features with stable names.
- B2. Respect windows and sampling; use existing MarketData sources (bookTicker/trades/klines) and cached bars.
- B3. Ensure `EVT:FEATURES_CALCULATED` includes these features (stringified decimals allowed, but numeric-parsable), unchanged existing fields.
- B4. Add unit tests for each feature formula (happy path + edge cases).

### Phase C: Ensemble performance source
- C1. Define adapter to consume PnL/hit-rate from Risk/Execution (e.g., `EVT:TRADE_CLOSED`, `EVT:ORDER_FILLED`).
- C2. Maintain rolling performance windows per model; rebalance weights by config.
- C3. Guardrails: clamp weights, re-normalize, freeze on missing telemetry.

### Phase D: QoS and safety nets
- D1. Timeouts per model evaluation (max_compute_ms). If timeout → skip model (no default score), log reason.
- D2. Backpressure: drop alpha computation if FeatureEngineering lags (configurable), to avoid cascades.
- D3. Circuit breaker: if error rate > threshold → disable model temporarily.

---

## 6. Causal chains and cascade analysis

Potential cascades and mitigations:
- Missing features → model defaulting → bad signals → DecisionMaking churn → ExposureGuard rejections.
  - Mitigation: no defaults; readiness gate; emit nothing if not ready.
- High compute latency → backlog in alpha → DecisionMaking stale inputs.
  - Mitigation: per-model timeout, skip late symbols, metrics & alerts.
- Weight drift from surrogate metrics → systematic bias.
  - Mitigation: production performance source (PnL/hit-rate) + bounds + periodic reset.
- Schema drift → event parsing failures.
  - Mitigation: additive-only schema versioning; `$id` bump; canary validation.

Dependency map during runtime:
- FeatureEngineering → AlphaSearch (input dependency)
- Risk/Execution telemetry → AlphaSearch (performance feedback) [optional but recommended]
- AlphaSearch → DecisionMaking (consumer dependency)

Failure containment:
- AlphaSearch failure should not block FeatureEngineering or DecisionMaking; on failure, it emits nothing, logs error, and the system continues with other signals.

---

## 7. Config changes (to be added)

In `config/aurora/trading.yaml` (additive):

```yaml
trading:
  alpha_search:
    enabled: true
    models:
      momentum_v1: { enabled: true }
      mean_reversion_v1: { enabled: true }
      volatility_v1: { enabled: true }
    ensemble:
      enabled: true
      rebalance_frequency_days: 7
      min_weight: 0.0
      max_weight: 1.0
      performance_window_days: 30
      risk_adjustment: true
      performance_source: pnl  # or hit_rate/confidence
    qos:
      max_compute_ms: 20
      max_models: 10
      require_features_ready: true
      emit_on_no_scores: false

# Domain activation
domain_configuration:
  alpha_search:
    trading_mode: "live"  # read features and emit signals (no writes)
```

---

## 8. Test plan (unit + integration)

All tests go under `tests/alpha_search/`.

### 8.1 Unit tests (models)
- `test_momentum_model_ready_and_bounds.py`
  - test_ready_true_when_all_required_features_present
  - score_range_in_minus1_to_plus1
  - confidence_in_0_to_1
  - volume_confirmation_amplifies_or_dampens
  - consistency_factor_mapping
- `test_mean_reversion_model_combination.py`
  - bb_position_extremes_drive_direction
  - rsi_extremes_override
  - sma_deviation_normalization
  - volume_multiplier_effects
  - confidence_agreement_logic
- `test_volatility_model_signals.py`
  - atr_ratio_centering_and_clamp
  - bb_width_change_amplification
  - realized_vol_trend_normalization
  - volatility_level_filter
  - final_clamp_and_confidence

### 8.2 Unit tests (registry & ensemble)
- `test_registry_register_and_calculate.py`
  - register_models_and_list
  - calculate_all_alpha_only_when_ready
  - handle_model_exceptions_gracefully
- `test_ensemble_combine_and_weights.py`
  - combine_scores_with_weights_and_contributions
  - rebalance_by_performance_source_mock
  - clamp_and_normalize_weights

### 8.3 FSM unit tests (handler logic)
- `test_alpha_fsm_validates_and_emits.py`
  - accepts_valid_features_event_and_emits_alpha_event
  - skips_when_no_models_ready
  - attaches_rid_ts_and_why
  - no_defaults_on_missing_features
  - respects_max_compute_ms_timeout

### 8.4 Integration tests (pipeline)
- `test_pipeline_features_to_alpha_to_decision.py`
  - simulate_FEATURES_CALCULATED_with_full_feature_set
  - assert_ALPHA_SCORE_CALCULATED_emitted_with_schema_validation
  - ensure_decision_making_receives_and_consumes_score
- `test_performance_feedback_reweights.py`
  - mock_trade_outcomes_events_update_weights
  - observe_weight_changes_and_effect_on_combination

### 8.5 Non-functional tests
- `test_latency_p95_under_50ms.py` (ensemble 3 models, 1 symbol)
- `test_memory_no_unbounded_growth.py`
- `test_schema_backward_compatibility_additive.py`

---

## 9. Observability & compliance

- Logging: `domain_alpha_search.log` with structured JSONL; include `rid`, `symbol`, `model`, `duration_ms`, `why_count`.
- Metrics: counters (events_in, events_out), gauges (models_ready), timers (calc_ms), error rates, CB state.
- Tracing: span around model evaluation; include symbol and RID.
- WHY-chain coverage ≥ 95% of events.

---

## 10. Acceptance criteria (green gates)

- Build: PASS (lint/typecheck, no new warnings)
- Schemas: present, valid 2020-12, with `$id`; validation hooks in FSM
- Features: FeatureEngineering emits all dictionary features; unit tests pass
- FSM: AlphaModelFSM subscribes and emits correctly; unit tests pass
- Ensemble: no defaults; uses real features; contributions present
- DecisionMaking: consumes ALPHA_SCORE_CALCULATED in integration test
- Risk feedback: performance_source configurable; rebalance observed under tests
- SLO: p95 ≤ 50 ms per symbol (ensemble 3 models)

---

## 11. Work breakdown (tasks)

- T1: Add schemas (input/output/config) and dictionary file (no code) – contracts
- T2: Implement AlphaModelFSM (subscribe/emit/validate/metrics)
- T3: Extend FeatureEngineering to compute dictionary features (additive)
- T4: Wire config (YAML → Pydantic) for alpha_search
- T5: Ensemble: pass-through features, add contributions in output
- T6: Performance feedback adapter (PnL/hit-rate) and weight rebalance
- T7: QoS/CB/timeouts + observability
- T8: Unit & integration tests in `tests/alpha_search/`
- T9: Canary run (shadow read), then limited enablement

Dependencies: T1→T2/T3; T3→T4/T5/T8; T6 after MVP works.

---

## 12. Open items / missing artifacts

- Missing: FeatureEngineering implementations for all dictionary features (momentum, RSI, MACD, BB, ATR, realized vol, etc.).
- Missing: FSM wrapper (`AlphaModelFSM`) implementation file in repo.
- Missing: JSON Schema files directory and registration in build.
- Missing: Domain config block `trading.alpha_search` in YAML and Pydantic model mapping.
- Missing: Performance feedback stream (PnL/hit-rate) and adapter.
- Missing: DecisionMaking consumption of `EVT:ALPHA_SCORE_CALCULATED` (currently imports registry; needs event consumer path or keep registry path explicitly).

If any of the above remain missing, alpha_search cannot run without defaults/fallbacks; contracts must be fulfilled first.

---

## 13. Risks and mitigations

- Risk: Feature calc complexity increases FE latency
  - Mitigation: cache, batch bars, compute-on-change
- Risk: Schema churn breaks consumers
  - Mitigation: additive versioning, keep v1 stable; add v2 later
- Risk: Overfitting ensemble to noisy feedback
  - Mitigation: windowing, caps, regularization of weights
- Risk: DecisionMaking logic expects registry (not events)
  - Mitigation: dual-path: keep registry inside DecisionMaking while adding FSM path; converge later

---

## 14. Rollout strategy

1) Contracts + FSM + unit tests
2) FeatureEngineering additions + feature unit tests
3) Shadow-mode: consume features, emit alpha events to log only
4) Canary-mode: 10–20% consumption in DecisionMaking
5) Full cutover; monitor SLOs; enable performance feedback reweighting

---

## 15. Appendix: Example event payloads

### 15.1 FEATURES_CALCULATED (input)
```json
{
  "ts": 1731336000123,
  "symbol": "BTCUSDT",
  "features": {
    "price": "36750.1",
    "price_momentum_5m": 0.0032,
    "price_momentum_1h": 0.012,
    "price_momentum_1d": 0.045,
    "volume_momentum_5m": 0.25,
    "rsi_14": 62.3,
    "macd_signal": 0.004,
    "bb_position": 0.62,
    "bb_width": 0.034,
    "price_sma_20_deviation": 0.008,
    "volume_sma_ratio": 1.2,
    "stoch_k": 61,
    "stoch_d": 58,
    "atr_14": 215.2,
    "atr_ratio": 1.18,
    "bb_width_change": 0.0012,
    "realized_volatility_1h": 0.021,
    "realized_volatility_1d": 0.017,
    "volume_volatility_ratio": 1.1,
    "price_range_ratio": 1.3
  }
}
```

### 15.2 ALPHA_SCORE_CALCULATED (output)
```json
{
  "ts": 1731336000124,
  "rid": "RID-20251111-ABC123",
  "model_name": "ensemble_3_models",
  "symbol": "BTCUSDT",
  "score": 0.64,
  "confidence": 0.78,
  "features_used": ["price_momentum_5m", "price_momentum_1h", "rsi_14", "bb_position"],
  "why": [
    "Momentum alignment across 5m/1h",
    "RSI supports bullish bias",
    "BB position > 0.6"
  ],
  "contributions": {
    "momentum_v1": {"score": 0.8, "weight": 0.4, "contribution": 0.32},
    "mean_reversion_v1": {"score": 0.1, "weight": 0.3, "contribution": 0.03},
    "volatility_v1": {"score": 0.6, "weight": 0.3, "contribution": 0.18}
  }
}
```
