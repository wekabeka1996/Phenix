## Domains overview

- `feature_engineering` (`apps/reference/domains/feature_engineering/feature_engineering.py` lines 1-120) listens to `EVT:MARKET_TICK_RECEIVED`, resolves `resolve_feature_engineering_config`, keeps per-symbol state, and produces the enriched `EVT:FEATURES_CALCULATED` bundle (base + Phase-1 metrics) that feeds alpha, regime, and risk domains.
- `alpha_search` (`apps/reference/domains/alpha_search/alpha_model.py` + `ensemble.py` lines 1-382) hosts the `AlphaScore` contract, registries, ensemble weighting, and three concrete models; DecisionMaking imports these classes to calculate alpha scores on every feature update while also emitting `EVT:ALPHA_SCORE_CALCULATED` with WAL tracing.
- `regime_detector` (`apps/reference/domains/regime_detector/regime_detector.py` lines 1-420) applies volatility -> mean-reversion -> SMA trend detectors per `resolve_regime_detector_config`, attaches confidence, and emits `EVT:REGIME_DETECTED` (schema in `schemas/regime_detected_v1.json`) for DecisionMaking to apply regime thresholds and behavior gates.
- `risk_management` (`apps/reference/domains/risk_management/risk_management.py` lines 1-200 plus `daily_gate.py` lines 1-200) listens to features and portfolio frames, resolves risk score weights/thresholds, emits `EVT:RISK_ASSESSMENT_COMPLETED`, and tracks daily limits that may veto new intents via `DailyRiskState`.
- `decision_making` (`apps/reference/domains/decision_making/decision_making.py` lines 1-1500) glues the streams: it stores features/risk/regime, enforces QoS/exposure/regime filters, leverages `resolve_decision_policy`, `resolve_brackets_config`, and `config/domains/{decision,sizing,regimes}.yaml` to tune `signal_thresholds`, `regime_threshold_multipliers`, and position sizing, and finally emits `EVT:TRADE_INTENT_PROPOSED` (schema in `schemas/trade_intent_v1.json`).

## Files by domain

### alpha_search
| domain | file | short description | STATUS |
| --- | --- | --- | --- |
| `alpha_search` | `apps/reference/domains/alpha_search/alpha_model.py` | Defines `AlphaScore`, the `AlphaModel` ABC, and `AlphaModelRegistry` (lines 1-170) that DecisionMaking reuses when features arrive and before emitting `EVT:ALPHA_SCORE_CALCULATED`. | UNKNOWN |
| `alpha_search` | `apps/reference/domains/alpha_search/ensemble.py` | Combines registered models, tracks performance, and rebalances risk-adjusted weights every few days (lines 1-382) to produce ensembled scores consumed downstream. | UNKNOWN |
| `alpha_search` | `apps/reference/domains/alpha_search/models/momentum.py` | Momentum model (lines 1-140) scoring weighted price/volume momentum, RSI, and MACD consistency with confidence calibration. | UNKNOWN |
| `alpha_search` | `apps/reference/domains/alpha_search/models/mean_reversion.py` | Mean reversion model (lines 1-200) using Bollinger, SMA deviations, RSI, stochastic, and volume filters to deliver [-1,1] scores. | UNKNOWN |
| `alpha_search` | `apps/reference/domains/alpha_search/models/volatility.py` | Volatility model (lines 1-170) monitors ATR ratios, BB width change, realized vol trends, and volume/volatility correlation for breakout/range signals. | UNKNOWN |
| `alpha_search` | `apps/reference/domains/alpha_search/README.md` | Domain overview (lines 1-190) describing the alpha pipeline, supported models, `EVT:ALPHA_SCORE_CALCULATED`, and integration with FeatureEngineering/DecisionMaking. | UNKNOWN |
| `alpha_search` | `apps/reference/domains/alpha_search/ANALYSIS_SUMMARY.md` | Architectural assessment (lines 1-120) that highlights modular design, ensemble weighting, validation, and event observability. | UNKNOWN |
| `alpha_search` | `apps/reference/domains/alpha_search/API_DEPENDENCIES.md` | Lists vFoundation dependencies and configuration expectations for alpha FSMs (lines 1-80). | UNKNOWN |
| `alpha_search` | `apps/reference/domains/alpha_search/EVENTS.md` | Supplies the `EVT:ALPHA_SCORE_CALCULATED` schema/payload samples, weight tracking code, and performance notes (lines 1-250). | UNKNOWN |
| `alpha_search` | `apps/reference/domains/alpha_search/TESTING.md` | Enumerates unit/integration tests for models, ensemble, and backtest coverage (lines 1-120). | UNKNOWN |

### regime_detector
| domain | file | short description | STATUS |
| --- | --- | --- | --- |
| `regime_detector` | `apps/reference/domains/regime_detector/regime_detector.py` | Handles `EVT:FEATURES_CALCULATED`, runs volatility/sideways/trend detectors in priority order, calculates confidences, and emits `EVT:REGIME_DETECTED` with metadata (lines 1-410). | UNKNOWN |
| `regime_detector` | `apps/reference/domains/regime_detector/config.py` | Typed dataclasses + helpers (lines 1-262) behind `resolve_regime_detector_config`, feeding thresholds, confidence caps, and legacy fallbacks to the runtime. | UNKNOWN |
| `regime_detector` | `apps/reference/domains/regime_detector/README.md` | Documents supported regimes (TREND_UP/DOWN, SIDEWAYS, HIGH/LOW_VOLATILITY), event flow, and configuration snippets (lines 1-100). | UNKNOWN |
| `regime_detector` | `apps/reference/domains/regime_detector/ANALYSIS_SUMMARY.md` | Notes architectural strengths (multi-model detection, confidence scoring, event-driven processing). | UNKNOWN |
| `regime_detector` | `apps/reference/domains/regime_detector/API_DEPENDENCIES.md` | Lists vFoundation imports and config dependencies for the detector FSM (lines 1-90). | UNKNOWN |
| `regime_detector` | `apps/reference/domains/regime_detector/EVENTS.md` | Describes `EVT:REGIME_DETECTED` schema/payload plus expected input `FEATURES_CALCULATED` format. | UNKNOWN |
| `regime_detector` | `apps/reference/domains/regime_detector/TESTING.md` | Summarizes unit tests that cover volatility, mean reversion, and trend edge cases. | UNKNOWN |
| `regime_detector` | `apps/reference/domains/regime_detector/domain_dict.json` | Declares that the domain imports `EVT:FEATURES_CALCULATED` and exports `EVT:REGIME_DETECTED` per schema. | UNKNOWN |
| `regime_detector` | `apps/reference/domains/regime_detector/schemas/regime_detected_v1.json` | JSON schema (lines 1-50) for regime detection results (ts, symbol, regime, confidence, source_model). | UNKNOWN |

### decision_making
| domain | file | short description | STATUS |
| --- | --- | --- | --- |
| `decision_making` | `apps/reference/domains/decision_making/decision_making.py` | Core FSM (lines 1-1500) that listens to features/risk/portfolio/regime, calculates signal score, applies QoS/exposure/regime gates, resolves decision policy/brackets, and emits `EVT:TRADE_INTENT_PROPOSED` with regime/risk metadata. | UNKNOWN |
| `decision_making` | `apps/reference/domains/decision_making/deferred_scheduler.py` | Schedules single retry callbacks when QoS/exposure cooldowns delay a decision, preventing tight loops (lines 1-80). | UNKNOWN |
| `decision_making` | `apps/reference/domains/decision_making/dm_log_adapter.py` | Writes structured DecisionLog entries (timestamp, event, rid, payload) to `logs/domain_decision_making.log` for observability. | UNKNOWN |
| `decision_making` | `apps/reference/domains/decision_making/normalized_reject_reasons.py` | Normalizes reject strings to standard NRR codes (lines 1-180) so QoS/risk hits can be traced and logged consistently. | UNKNOWN |
| `decision_making` | `apps/reference/domains/decision_making/why_codes.py` | Enumerates WHY codes (REGIME, RISK, GUARD, SIGNAL, etc.) used throughout decision logging to explain accept/reject outcomes. | UNKNOWN |
| `decision_making` | `apps/reference/domains/decision_making/README.md` | Provides domain overview, feedback loops, QoS guards, and integration expectations for DecisionMaking. | UNKNOWN |
| `decision_making` | `apps/reference/domains/decision_making/ANALYSIS_SUMMARY.md` | Executive summary praising the FSM architecture, multi-stream signal fusion, and transparency metrics (lines 1-120). | UNKNOWN |
| `decision_making` | `apps/reference/domains/decision_making/API_DEPENDENCIES.md` | Lists vFoundation, configuration access helpers, and alert/risk hooks that the domain relies on (lines 1-120). | UNKNOWN |
| `decision_making` | `apps/reference/domains/decision_making/EVENTS.md` | Captures the `EVT:TRADE_INTENT_PROPOSED` schema/payload, why chain examples, and expected consumer actions. | UNKNOWN |
| `decision_making` | `apps/reference/domains/decision_making/TESTING.md` | Enumerates QoS and rejection tests (15 total) that validate symbol cooldowns, deferrals, and normalized reject reasons. | UNKNOWN |
| `decision_making` | `apps/reference/domains/decision_making/domain_dict.json` | Declares imports (`FEATURES_CALCULATED`, `RISK_ASSESSMENT_COMPLETED`, `PORTFOLIO_STATE_UPDATED`) and the export `EVT:TRADE_INTENT_PROPOSED` with schema reference. | UNKNOWN |
| `decision_making` | `apps/reference/domains/decision_making/schemas/trade_intent_v1.json` | JSON schema (lines 1-200) for the emitted trade intent, including risk, TCA, size, and order sections. | UNKNOWN |

### feature_engineering
| domain | file | short description | STATUS |
| --- | --- | --- | --- |
| `feature_engineering` | `apps/reference/domains/feature_engineering/feature_engineering.py` | Resolves config, maintains per-symbol buffers, and reacts to `EVT:MARKET_TICK_RECEIVED` to compute core metrics like OBI/TFI/delta price/liquidity_kappa before emitting `EVT:FEATURES_CALCULATED`. | UNKNOWN |
| `feature_engineering` | `apps/reference/domains/feature_engineering/feature_engineering_phase1.py` | Phase 1 extension (lines 1-130) that adds EMA bias, volume spike, volatility state, depth imbalance, and macro sync penging new metrics via the same tick pipeline. | UNKNOWN |
| `feature_engineering` | `apps/reference/domains/feature_engineering/config.py` | Typed config loader with defaults for EMA/volume/volatility/liquidity/macro settings, keeping the domain decoupled from raw YAML. | UNKNOWN |
| `feature_engineering` | `apps/reference/domains/feature_engineering/README.md` | Explains domain goals, supported metrics, and config snippets for enabling Phase 1 features (lines 1-120). | UNKNOWN |
| `feature_engineering` | `apps/reference/domains/feature_engineering/ANALYSIS_SUMMARY.md` | Highlights quality metrics, testing status, and extensibility of the feature pipeline. | UNKNOWN |
| `feature_engineering` | `apps/reference/domains/feature_engineering/API_DEPENDENCIES.md` | Lists vFoundationDependencies such as `Message`, `FSMCore`, and `deque` for stateful processing (lines 1-80). | UNKNOWN |
| `feature_engineering` | `apps/reference/domains/feature_engineering/EVENTS.md` | Documents `EVT:MARKET_TICK_RECEIVED` and `EVT:FEATURES_CALCULATED` payloads plus formulas for each metric. | UNKNOWN |
| `feature_engineering` | `apps/reference/domains/feature_engineering/TESTING.md` | Notes the 5/5 unit tests and baseline coverage for new metrics. | UNKNOWN |
| `feature_engineering` | `apps/reference/domains/feature_engineering/domain_dict.json` | Maps the market tick input to the features output event to clarify wiring. | UNKNOWN |
| `feature_engineering` | `apps/reference/domains/feature_engineering/schemas/features_calculated_v1.json` | Schema (lines 1-60) for `EVT:FEATURES_CALCULATED` (ts, symbol, features object with OBI/TFI/delta/absorption). | UNKNOWN |

### risk_management
| domain | file | short description | STATUS |
| --- | --- | --- | --- |
| `risk_management` | `apps/reference/domains/risk_management/risk_management.py` | Subscribes to features/portfolio, resolves risk weights/thresholds, calculates Kelly/CVaR/drawdown params, and emits `EVT:RISK_ASSESSMENT_COMPLETED` plus logging (lines 1-220). | UNKNOWN |
| `risk_management` | `apps/reference/domains/risk_management/daily_gate.py` | Tracks daily equity/drawdown limits via `DailyConfig`, resets per UTC clock, and exposes `can_open()` metadata consumed before allowing intents. | UNKNOWN |
| `risk_management` | `apps/reference/domains/risk_management/README.md` | Describes the two-layer guarding system (daily gate + instrument risk scoring) and the relevant input/output events (lines 1-70). | UNKNOWN |
| `risk_management` | `apps/reference/domains/risk_management/ANALYSIS_SUMMARY.md` | Summarizes architecture, gating logic, and runtime instrumentation for risk decisions. | UNKNOWN |
| `risk_management` | `apps/reference/domains/risk_management/API_DEPENDENCIES.md` | Lists vFoundation, `Decimal`, and datetime utilities that the domain relies on (lines 1-80). | UNKNOWN |
| `risk_management` | `apps/reference/domains/risk_management/EVENTS.md` | Defines `EVT:RISK_ASSESSMENT_COMPLETED`, `EVT:PORTFOLIO_STATE_UPDATED`, and `EVT:DAILY_RISK_LIMIT` payloads with why strings. | UNKNOWN |
| `risk_management` | `apps/reference/domains/risk_management/TESTING.md` | Mentions the 17 risk tests with 11 skipped scenarios, covering low/medium/high risk cases. | UNKNOWN |
| `risk_management` | `apps/reference/domains/risk_management/domain_dict.json` | Declares imports (`FEATURES_CALCULATED`) and `EVT:RISK_ASSESSMENT_COMPLETED` exports, confirming the runtime contract. | UNKNOWN |
| `risk_management` | `apps/reference/domains/risk_management/schemas/risk_assessment_v1.json` | Schema (lines 1-60) for risk assessment payloads (symbol, ts, risk_parameters including Kelly, CVaR, drawdown, and trading flag). | UNKNOWN |

## Relevant configs

| config | short description | STATUS |
| --- | --- | --- |
| `config/domains/regimes.yaml` | v2 regime definition (window, min duration, debouncing, regime buckets) that `resolve_regime_detector_config` uses for detection thresholds. | UNKNOWN |
| `config/domains/features.yaml` | Feature engineering windows/clamps (EMA, volume, volatility, macro sync) that drive `resolve_feature_engineering_config` and therefore every downstream signal. | UNKNOWN |
| `config/domains/decision.yaml` | Decision thresholds (`signal_threshold`, `neutral_threshold`) and QoS caps consumed by `resolve_decision_policy` in DecisionMaking. | UNKNOWN |
| `config/domains/sizing.yaml` | Global sizing defaults + regime multipliers (HIGH_VOLATILITY, LOW_VOLATILITY, etc.) used by DecisionMaking for `regime_threshold_multipliers` and sizing metadata. | UNKNOWN |
| `config/instruments.yaml` | Base instrument profiles (precision, limits, leverage) that DecisionMaking, ExecutionPosition, and risk sizing reference when computing quantities. | UNKNOWN |
| `config/overrides.yaml` | Symbol overrides (e.g., leverage = 125) and per-instrument regime sizing adjustments that layer on top of base profiles. | UNKNOWN |
| `docs/config_analysis/config_contract_map.md` | Maps config files to resolvers (`resolve_decision_policy`, `resolve_risk_*`, `resolve_regime_detector_config`, `resolve_brackets_config`, etc.) and lists consuming domains for the alpha/regime/decision stack. | UNKNOWN |
| `docs/For_GPT/CONFIG_REFERENCE.md` | High-level narrative of how the v2 config tree (modes, domains, execution, feature, risk) ties into `resolve_*` helpers and the Aurora `ConfigLoader`. | UNKNOWN |
