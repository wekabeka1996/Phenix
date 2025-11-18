## Config keys related to alpha/regimes

- `config/domains/regimes.yaml` exposes the `detector` block (`window_minutes`, `min_regime_duration_min`, `debounce_changes`), the named `regimes` with `vol_std_bps_*` ranges, and the `hotreload.allowed` list that the detector enforces. | IMPLEMENTED_ACTIVE (regime detector reads). |
- `config/domains/features.yaml` defines the `global.enable_new_metrics` flag, the `windows` section for EMA/volume/volatility buffers, `features.*` clamps (bias, spikes, ratios), and `macro_sync` anchors/window that feed FeatureEngineering. | IMPLEMENTED_ACTIVE (feature engineering consumes). |
- `config/domains/decision.yaml` carries `thresholds.signal_threshold`, `thresholds.neutral_threshold`, and `qos.*` entries that become the base thresholds/QoS caps in DecisionMaking via `resolve_decision_policy`. | IMPLEMENTED_ACTIVE (decision policy). |
- `config/domains/sizing.yaml` declares `defaults` (mode, max risk %, caps, Kelly params), optional `symbols.<symbol>` overrides, and `regimes.<name>` multipliers for size adjustments. | IMPLEMENTED_ACTIVE (sizing resolver connected). |
- `config/instruments.yaml` + `config/overrides.yaml` form the v2 instrument profile (precision, limits, `tp_sl`, regime multipliers, risk fraction). | PARTIALLY IMPLEMENTED: profiles resolved but `regime_multipliers` currently unused by any domain. Documentation expects execution/decision/risk to read them. | 
- `docs/config_analysis/config_contract_map.md` / `CONFIG_REFERENCE.md` describe the canonical resolvers (`resolve_regime_detector_config`, `resolve_feature_engineering_config`, `resolve_decision_policy`, `resolve_sizing_policy`, `resolve_instrument_profile`) and list the domains that must use them (`regime_detector`, `decision_making`, `execution_position`, `feature_engineering`, `risk_management`). | DOC_ONLY (contract doc). |

## Resolvers & consumers

- `resolve_regime_detector_config` (`apps/reference/config_regimes.py:162-202`) first tries v2 `regimes` section for window/min_duration/debounce, hotreload whitelist, and detector models; the typed dataclasses in `apps/reference/domains/regime_detector/config.py` validate these before the FSM applies thresholds. Consumer: `RegimeDetector.handle_event`. | IMPLEMENTED_ACTIVE |
- `resolve_feature_engineering_config` (`apps/reference/config_features.py:15-122`) requires `domains/features.yaml` and exposes EMA/volume/volatility window sizes, clamps, and macro-sync anchors to `FeatureEngineering`. | IMPLEMENTED_ACTIVE |
- `resolve_decision_policy` (`apps/reference/config_decision.py:1-83`) pulls `thresholds.*` and `qos.*` from `domains/decision.yaml` (falling back to `trading.decision`) so `DecisionMaking` knows the base signal/neutral thresholds and QoS limits. | IMPLEMENTED_ACTIVE |
- `resolve_sizing_policy` (`apps/reference/config_sizing.py:1-136` + `137-210`) merges `defaults`, `symbols.<sym>`, and `regimes.<name>` from `domains/sizing.yaml` to supply regime-aware sizing multipliers and Kelly overrides. Consumer: `DecisionMaking._make_decision_for_symbol` (applies `regime_multiplier` to the base notional). | IMPLEMENTED_ACTIVE |
- `resolve_instrument_profile` (`apps/reference/config_symbols.py:222-359`) builds profiles from `config/instruments.yaml` and `config/overrides.yaml`, merging precision/limits and regime/risk fields. Intended consumers (`execution_position`, `decision_making`, `risk_management`) are enumerated in `docs/config_analysis/config_contract_map.md`, but the only code that references the `regime_multipliers` field remains absent. | PARTIALLY IMPLEMENTED |

## STATUS (real usage vs. doc-only)

| config_key | resolver | domain/usage | STATUS |
| --- | --- | --- | --- |
| `config/domains/regimes.yaml::detector, regimes, hotreload` | `resolve_regime_detector_config` (`apps/reference/config_regimes.py:162-202`) | `regime_detector` reads thresholds/confidence caps inside `_detect_*` logic | IMPLEMENTED_ACTIVE |
| `config/domains/features.yaml::global`, `windows`, `features`, `macro_sync` | `resolve_feature_engineering_config` (`apps/reference/config_features.py:15-122`) | `feature_engineering` uses the resolved values for EMA/volume/volatility/macros, producing `EVT:FEATURES_CALCULATED` | IMPLEMENTED_ACTIVE |
| `config/domains/decision.yaml::thresholds, qos` | `resolve_decision_policy` (`apps/reference/config_decision.py:1-83`) | `decision_making` applies the policy when comparing `signal_score` to `signal_threshold` and in QoS guards | IMPLEMENTED_ACTIVE |
| `config/domains/sizing.yaml::defaults, symbols, regimes` | `resolve_sizing_policy` (`apps/reference/config_sizing.py:136-210`) | `decision_making` multiplies notional by `regime_multiplier` plus Kelly overrides before emitting intents | IMPLEMENTED_ACTIVE |
| `config/instruments.yaml` + `config/overrides.yaml::precision, limits, tp_sl, risk, regime_multipliers` | `resolve_instrument_profile` (`apps/reference/config_symbols.py:222-359`) | `execution_position`/`decision_making`/`risk_management` expect the unified profile (`docs/config_analysis/config_contract_map.md:103`) but no code currently instantiates/regulates `regime_multipliers` beyond storing them. | PARTIALLY_IMPLEMENTED (regime_multipliers unused) |
| `docs/config_analysis/config_contract_map.md`, `CONFIG_REFERENCE.md` | — | Enumerate the resolvers/consumers for the v2 files listed above | DOC_ONLY |

