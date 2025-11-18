## RegimeDetector overview

- `RegimeDetector` instantiates with `resolve_regime_detector_config` (dual-mode config resolver in `apps/reference/config_regimes.py`) and exposes `handle_event` that processes incoming `EVT:FEATURES_CALCULATED` payloads before emitting `EVT:REGIME_DETECTED` (see `apps/reference/domains/regime_detector/regime_detector.py:32-410`). The class caches `self.model_name` and logs resolved settings for traceability.
- Documentation mirrors the implementation: `apps/reference/domains/regime_detector/README.md` outlines supported regimes, `ANALYSIS_SUMMARY.md` praises the multi-model architecture, and `EVENTS.md` describes the expected input/output payloads. `domain_dict.json` states imports/exports (`FEATURES_CALCULATED` → `REGIME_DETECTED`), while `schemas/regime_detected_v1.json` guarantees the emitted payload structure.

## Input data & algorithms

- **Features consumed**: `handle_event` requires `symbol`, `ts`, `price`, `sma_short`, and `sma_long` from the feature payload (lines 323-350), plus optional volatility inputs `atr_14` and `atr_14_sma_100` (lines 351-360). `_safe_decimal_parse` (lines 297-320) normalizes these values to `Decimal`.
- **Regime detection order**:
  1. **Volatility regimes** (`_detect_volatility`, lines 114-191): compares ATR14 to ATR100 SMA, uses configurable `threshold_multiplier` and `low_vol_multiplier` to emit `HIGH_VOLATILITY` or `LOW_VOLATILITY`, and scales confidence via linear formulas capped by `confidence_max`.
  2. **Mean-reversion / sideways** (`_detect_sideways`, lines 193-263): measures `sma_spread`, `price_deviation_short`, and `price_deviation_long` against `deviation_threshold` (default 0.02); tighter clustering raises confidence through `tightness * confidence_multiplier`.
  3. **Trend detection** (`_detect_trend`, lines 264-295): simple SMA crossover with `price` guard, reusing `_calculate_confidence` (lines 62-94) based on relative SMA spread.
- The first non-`UNCERTAIN` result short-circuits the chain; if a regime fires, `handle_event` builds `payload` with `regime`, stringified `confidence`, unversioned `model`, and `source_model` before emitting `EVT:REGIME_DETECTED` and logging the detection (lines 373-412).

## EVT:REGIME_DETECTED contract

- Schema (`apps/reference/domains/regime_detector/schemas/regime_detected_v1.json`) mandates `ts`, `symbol`, `regime`, `confidence`, and `source_model`, while allowing `model` as the human-friendly alias (lines 1-40). `EVENTS.md` provides the same structure plus sample payloads for `TREND_UP`, `TREND_DOWN`, `SIDEWAYS`, etc.
- The emitted payload stores the original timestamp from the feature event and includes a `why` string on emission (line 405) for debugging. `domain_dict.json` confirms the event export and schema for consumers.

## Integration (who listens / who uses)

- **Trigger**: `EVT:FEATURES_CALCULATED` from `feature_engineering` feeds into `RegimeDetector.handle_event`, so every features packet may produce a regime classification if the required fields are present (lines 323-366).
- **Consumers**: `DecisionMaking` registers `fsm.listen("EVT:REGIME_DETECTED", self.on_regime)` (line 452) and stores the latest regime for gating and sizing; its `why_codes` even include `INFO_REGIME_DETECTED` for instrumentation. No other domains currently register this event, so DecisionMaking is the primary downstream consumer.
- **Config**: `resolve_regime_detector_config` (`apps/reference/config_regimes.py:162-202`) sources thresholds from `config/domains/regimes.yaml` and falls back to legacy files when needed; the typed dataclasses in `apps/reference/domains/regime_detector/config.py` validate thresholds, confidence caps, and enable flags before the FSM runs.

## STATUS matrix

| component | file:line | status | notes |
| --- | --- | --- | --- |
| `RegimeDetector.handle_event` | `apps/reference/domains/regime_detector/regime_detector.py:323-415` | IMPLEMENTED_ACTIVE | Listens for `EVT:FEATURES_CALCULATED`, validates required inputs, runs detection chain, and emits `EVT:REGIME_DETECTED` plus logging. |
| `_detect_volatility` | `apps/reference/domains/regime_detector/regime_detector.py:114-191` | IMPLEMENTED_ACTIVE | ATR ratio thresholds trigger `HIGH_VOLATILITY`/`LOW_VOLATILITY`; configurable bases/multipliers compute confidence. |
| `_detect_sideways` | `apps/reference/domains/regime_detector/regime_detector.py:193-263` | IMPLEMENTED_ACTIVE | Tight `sma`/`price` clusters trigger `SIDEWAYS` with thresholds from `sideways` config section. |
| `_detect_trend` | `apps/reference/domains/regime_detector/regime_detector.py:264-295` | IMPLEMENTED_ACTIVE | SMA crossover rules produce `TREND_UP`/`TREND_DOWN`, reusing `_calculate_confidence`. |
| Config resolver | `apps/reference/config_regimes.py:162-202` | IMPLEMENTED_ACTIVE | Builds `RegimeDetectorConfig` from v2 `regimes` settings (`config/domains/regimes.yaml`) plus legacy fallbacks. |
| Schema contract | `apps/reference/domains/regime_detector/schemas/regime_detected_v1.json:1-40` | IMPLEMENTED_ACTIVE | Enforces required fields (`ts`, `symbol`, `regime`, `confidence`, `source_model`) for `EVT:REGIME_DETECTED`. |
| `domain_dict.json` | `apps/reference/domains/regime_detector/domain_dict.json` | DOC_ONLY | Documents the feature → regime event wiring for consumers. |
| README / EVENTS / ANALYSIS | `apps/reference/domains/regime_detector/README.md`, `EVENTS.md`, `ANALYSIS_SUMMARY.md` | DOC_ONLY | Explain the supported regimes, payload, detection pipeline, and test coverage but do not drive runtime logic. |
