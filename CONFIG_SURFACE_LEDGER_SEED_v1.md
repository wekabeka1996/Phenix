# CONFIG_SURFACE_LEDGER_SEED_v1

**Date:** 2026-05-09
**Mode:** READ-ONLY AUDIT — initial seed entries only
**Purpose:** Canonical ledger of individual config surfaces by classification.
  Each row is a named config surface (file + YAML path + leaf or subtree).
**Companion:** CONFIG_OWNERSHIP_MAP_v1.md (family-level analysis)

---

## Classification Key

| Status Code | Meaning |
|-------------|---------|
| `active` | Loaded, typed, proven runtime consumer |
| `owner_split` | Same concept declared at two YAML paths |
| `legacy_compat` | Loader actively redirects or forbids this path |
| `dead_schema` | No loader reference, no runtime consumer |
| `metadata_only` | Loaded for schema/contract purposes only, not a tuning surface |
| `remove_or_repoint` | Should be deleted or redirected to canonical path |

---

## ACTIVE

| surface_id | file | yaml_path | owner | notes |
|------------|------|-----------|-------|-------|
| A-001 | `config/aurora/domains.yaml` | `domains.decision_making.*` | decision_making | QoS, entry_plan, gates, arming, risk_gate, neocortex mode, degraded_context |
| A-002 | `config/aurora/domains.yaml` | `domains.feature_engineering.*` | feature_engineering | EMA, volume, pillars, absorption, macro_sync, readiness_registry, warmup |
| A-003 | `config/aurora/domains.yaml` | `domains.risk_management.*` | risk_management | risk_score_weights, absorption_penalty, trading_allowed_thresholds |
| A-004 | `config/aurora/domains.yaml` | `domains.execution_position.*` | execution_position | exposure_guard, order_index, bracket, guardian, sidecar, restore_artifact |
| A-005 | `config/aurora/domains.yaml` | `domains.position_tracking.*` | position_tracking | precision, stale_ttl, market_tick_subscription |
| A-006 | `config/aurora/domains.yaml` | `domains.shadow_telemetry.*` | shadow_telemetry | ingest, api, egress, ledger, snapshot |
| A-007 | `config/aurora/domains.yaml` | `domains.objective_engine.*` | objective_engine | components (cost/risk/edge/execution/information/behavior), data_requirements |
| A-008 | `config/aurora/domains.yaml` | `domains.ta_features.*` | ta_features | enabled, timeframes_sec, warm_up_bars, buffer_max_bars |
| A-009 | `config/aurora/strategies.yaml` | `assignments.*` | strategies | Per-symbol strategy assignment list |
| A-010 | `config/aurora/strategies.yaml` | `arbitration.*` | strategies | mode, window_ms, priority ranks, logging policy |
| A-011 | `config/aurora/strategies/aurora.yaml` | `aurora.decision.*` | aurora_handler | signal_threshold, signal_weights, regime_thresholds, scoring_version |
| A-012 | `config/aurora/strategies/aurora.yaml` | `aurora.assets.*` | aurora_handler | Per-symbol weights, exit params, regime_tpsl, trailing, holding_period |
| A-013 | `config/aurora/strategies/aurora.yaml` | `aurora.objective.*` | aurora_handler | Per-regime objective weights and gate thresholds |
| A-014 | `config/aurora/strategies/aurora.yaml` | `aurora.execution.*` | aurora_handler | entry_order_type, entry_tif, gtx_retry_max |
| A-015 | `config/aurora/strategies/md_amr.yaml` | `md_amr.*` | md_amr_handler | All md_amr strategy params including assets, objective, execution |
| A-016 | `config/aurora/strategies/mean_reversion.yaml` | `mean_reversion.*` | mean_reversion_handler | BB strategy params, assets (only DOGEUSDT active) |
| A-017 | `config/aurora/strategies/llm_microstructure.yaml` | `llm_microstructure.*` | llm_microstructure_handler | Minimal 5-field profile |
| A-018 | `config/aurora/instruments.yaml` | `instruments.BTCUSDT.*` | execution_position | step_size, tick_size, min_qty, min_notional, leverage.target=25, sizing, flip |
| A-019 | `config/aurora/instruments.yaml` | `instruments.ETHUSDT.*` | execution_position | step_size, tick_size, min_qty, min_notional, leverage.target=20 |
| A-020 | `config/aurora/instruments.yaml` | `instruments.SOLUSDT.*` | execution_position | step_size=1 (integer qty), leverage.target=20 |
| A-021 | `config/aurora/instruments.yaml` | `instruments.XRPUSDT.*` | execution_position | step_size=0.1, leverage.target=20 |
| A-022 | `config/aurora/instruments.yaml` | `instruments.DOGEUSDT.*` | execution_position | step_size=1, leverage.target=10 |
| A-023 | `config/aurora/instruments.yaml` | `instruments.BNBUSDT.*` | execution_position | step_size=0.01, leverage.target=20 |
| A-024 | `config/aurora/instruments.yaml` | `instruments.1000PEPEUSDT.*` | execution_position | step_size=1, leverage.target=20, llm_microstructure symbol |
| A-025 | `config/aurora/observability.yaml` | `logging.*` | observability | All log paths, levels, rotation, per-domain logging |
| A-026 | `config/aurora/observability.yaml` | `alerts.*` | observability | slack_webhook, dedup_window, entropy thresholds, check_interval_sec |
| A-027 | `config/aurora/observability.yaml` | `shadow_journal.*` | observability | critical_events list, path, schema_version |
| A-028 | `config/aurora/trading.yaml` | `trading.mode` | trading_operations | trading mode declaration (see OWNER_SPLIT: OS-004) |
| A-029 | `config/aurora/trading.yaml` | `trading.binance_api.*` | trading_operations | API keys/URLs (env var refs); live + testnet |
| A-030 | `config/aurora/trading.yaml` | `trading.tca_prefs.*` | trading_operations | max_slippage_pct/bps, max_latency_ms, execution_priority |
| A-031 | `config/aurora/trading.yaml` | `trading.risk_budgets.*` | trading_operations | trade_cvar95_max_bps, session_cvar95_max_bps, max_portfolio_risk_pct |
| A-032 | `config/aurora/trading.yaml` | `trading.risk.*` | trading_operations | max_daily_drawdown, score_weights, soft_limits, regime_adaptation |
| A-033 | `config/aurora/trading.yaml` | `trading.market_data.*` | trading_operations | poll_interval_sec, websocket_streams, bar_aggregator timeframes |
| A-034 | `config/aurora/trading.yaml` | `trading.domain_configuration.*` | trading_operations | Per-domain trading_mode overrides for hybrid mode |
| A-035 | `config/aurora/trading.yaml` | `trading.execution.watchdog.*` | trading_operations | ack_ttl_ms, fill_ttl_ms, check_interval_ms, rps_limit (CANONICAL; watchdog removed from system.yaml per T5A.1-SSOT) |
| A-036 | `config/aurora/trading.yaml` | `trading.execution.order_guardian.*` | trading_operations | unified, ledger_db_path |
| A-037 | `config/aurora/trading.yaml` | `trading.execution.preflight_backoff_ms` | trading_operations | Backoff sequence for order preflight |
| A-038 | `config/aurora/trading.yaml` | `trading.llm_orchestration.*` | trading_operations | mode, llm_role, symbols_llm, intent_policy |
| A-039 | `config/aurora/regime.yaml` | `basis_tf_sec` | regime_detector | 5m basis timeframe |
| A-040 | `config/aurora/regime.yaml` | `basis_import_buffer` | regime_detector | SSOT buffer (strategy_compatibility_matrix reads this) |
| A-041 | `config/aurora/regime.yaml` | `models.*` | regime_detector | sma_trend, volatility, mean_reversion detection params |
| A-042 | `config/aurora/regime.yaml` | `system_stress.*` | regime_detector | stress detection thresholds, aggregation, state_mapping |
| A-043 | `apps/reference/domains/neocortex/config/neuro.yaml` | `vae.*`, `ppo.*`, `world_model.*` | neocortex | VAE/PPO architecture, training params (domain-embedded, not in config/aurora/) |
| A-044 | `apps/reference/domains/neocortex/config/replay.yaml` | `features_dir`, `orders_file` | neocortex | Log paths for offline replay ingestion |
| A-045 | `apps/reference/domains/neocortex/config/regime_oracle_reward.yaml` | `reward_matrix.*` | neocortex | PPO regime oracle reward matrix |

---

## OWNER_SPLIT

| surface_id | file_1 | yaml_path_1 | file_2 | yaml_path_2 | conflict_description | risk |
|------------|--------|-------------|--------|-------------|---------------------|------|
| OS-001 | `config/aurora/system.yaml` | `ops.panic_killswitch` | `config/aurora/trading.yaml` | `trading.ops.panic_killswitch` | Identical killswitch at two paths. Safety-critical. | HIGH |
| OS-002 | `config/aurora/system.yaml` | `ops.metrics_url` | `config/aurora/trading.yaml` | `trading.ops.metrics_url` | Duplicate. Metrics URL divergence causes split monitoring. | LOW |
| OS-003 | `config/aurora/system.yaml` | `ops.reports_dir` | `config/aurora/trading.yaml` | `trading.ops.reports_dir` | Duplicate. Lower risk but contributes to confusion. | LOW |
| OS-004 | `config/aurora/system.yaml` | `trading_mode` (root) | `config/aurora/trading.yaml` | `trading.mode` | Two YAML paths declare trading mode. Historical mismatch caused past bootstrap failures. | HIGH |
| OS-005 | `config/aurora/system.yaml` | `execution.manage.brackets.*` | `config/aurora/trading.yaml` | `trading.execution.manage.brackets.*` | Parallel bracket config. Migration in-progress (watchdog moved, rest not). | HIGH |
| OS-006 | `config/aurora/system.yaml` | `execution.manage.orphan_monitor.*` | `config/aurora/trading.yaml` | `trading.execution.manage.orphan_monitor.*` | Same orphan_monitor params at both paths. | MEDIUM |
| OS-007 | `config/aurora/system.yaml` | `execution.exposure.leverage_defaults.*` | `config/aurora/trading.yaml` | `trading.execution.exposure.leverage_defaults.*` | Duplicate. BTCUSDT 25 (instruments) vs 20 (both here) is a secondary conflict. | MEDIUM |
| OS-008 | `config/aurora/system.yaml` | `execution.order_guardian.*` | `config/aurora/trading.yaml` | `trading.execution.order_guardian.*` | Duplicate. | MEDIUM |
| OS-009 | `config/aurora/system.yaml` | `execution.order_params.*` | `config/aurora/trading.yaml` | `trading.execution.order_params.*` | Duplicate LIMIT/STOP_MARKET/TAKE_PROFIT_MARKET params. | LOW |
| OS-010 | `config/aurora/trading.yaml` | `trading.market_data.macro_sync.anchor_update_from_ticks` | `config/aurora/domains.yaml` | `domains.feature_engineering.macro_sync.anchor_update_from_ticks` | Contradicting values: false vs true. May affect feature consistency. | MEDIUM |
| OS-011 | `config/aurora/trading.yaml` | `trading.market_data.macro_sync.min_buffer_size` | `config/aurora/domains.yaml` | `domains.feature_engineering.macro_sync.min_buffer_size` | Different values: 3 vs 2. | LOW |
| OS-012 | `config/aurora/instruments.yaml` | `instruments.BTCUSDT.execution.target_leverage` (=25) | `config/aurora/trading.yaml` | `trading.execution.exposure.leverage_defaults.BTCUSDT` (=20) | Contradictory leverage values. Different semantics (exchange vs exposure math) but value difference is concerning for BTC. | MEDIUM |
| OS-013 | `config/aurora/instruments.yaml` | `instruments.DOGEUSDT.execution.target_leverage` (=10) | `config/aurora/trading.yaml` | `trading.execution.exposure.leverage_defaults.DOGEUSDT` (=20) | Contradictory leverage values for DOGE. | MEDIUM |
| OS-014 | `config/aurora/domains.yaml` | `domains.decision_making.qos` (mode=enforce, enforce=true) | `config/aurora/strategies/aurora.yaml` | `aurora.decision.qos` (mode=defer, enforce=false) | Semantic conflict. Domain says enforce, profile says defer. Which wins at runtime is unknown. | MEDIUM |

---

## LEGACY_COMPAT

| surface_id | file | yaml_path | reason |
|------------|------|-----------|--------|
| LC-001 | `config/aurora/trading.yaml` | `trading.instruments` | Loader raises ConfigContractError if present. Forbidden mirror of instruments.yaml. |
| LC-002 | `config/aurora/trading.yaml` | `trading.domains` | Loader raises ConfigContractError if present. domains.yaml is SSOT. |
| LC-003 | `config/aurora/system.yaml` | `execution.watchdog.*` | Removed per T5A.1-SSOT (2026-05-07). If re-added, creates split-brain with trading.execution.watchdog. |
| LC-004 | `config/aurora/trading.yaml` | `trading.execution.exposure.post_fill_hold_ttl_sec` | Removed per T3B-SSOT. Canonical path: domains.execution_position.exposure_guard.post_fill_ttl_sec. |

---

## DEAD_SCHEMA

| surface_id | file | yaml_path | evidence | disposal |
|------------|------|-----------|---------|---------|
| DS-001 | `config/aurora/archive/aurora_phase3_production.yaml` | entire file | Top-level key `aurora_phase3` has no loader reference. Superseded by strategies/aurora.yaml:assets. | Safe to delete. |
| DS-002 | `config/aurora/archive/features.yaml.deprecated` | entire file | Named `.deprecated`. No loader reference. | Safe to delete. |
| DS-003 | `config/alpha_search.yaml` | `alpha_search.legacy.*` | Block labeled "LEGACY: ignored by new code". | Remove from file. |
| DS-004 | `config/aurora/trading.yaml` | `trading.regime_tpsl: null` | Null stub. No Pydantic field confirmed to consume this. | Remove null stub. |
| DS-005 | `config/aurora/system.yaml` | `brackets: null` | Root-level null stub. | Remove null stub. |
| DS-006 | `config/aurora/strategies/aurora.yaml` | `aurora.decision.roi_exit: null` | Null stub. No active exit via ROI. | Remove null stub. |
| DS-007 | `config/aurora/strategies/aurora.yaml` | `aurora.decision.mean_reversion: null` | Null stub. | Remove null stub. |
| DS-008 | `config/aurora/strategies/aurora.yaml` | `aurora.decision.quadratic_rollout: null` | Null stub. | Remove null stub. |
| DS-009 | `config/aurora/strategies/aurora.yaml` | `aurora.decision.bar_gating: null` | Null override of domain config to null. Domain has enable=false anyway. | Remove null stub. |
| DS-010 | `config/aurora/strategies/aurora.yaml` | `aurora.decision.entry_plan: null` | Null stub. | Remove null stub. |
| DS-011 | `config/aurora/strategies/aurora.yaml` | `aurora.decision.money_management: null` | Null stub. | Remove null stub. |
| DS-012 | `config/aurora/strategies/aurora.yaml` | `aurora.decision.dashboard: null` | Null stub. | Remove null stub. |
| DS-013 | `config/aurora/strategies/aurora.yaml` | `aurora.decision.execution: null` | Null stub. | Remove null stub. |
| DS-014 | `config/alpha_search/scenario_matrix_v2_backup_20260224.yaml` | entire file | Dated backup. Not loaded. | Safe to delete. |

---

## METADATA_ONLY

| surface_id | file | yaml_path | purpose |
|------------|------|-----------|---------|
| M-001 | `apps/reference/dictionaries/verb_registry_v1.yaml` | entire file | Event contract registry. Schema/contract reference. Not a runtime tuning surface. |
| M-002 | `config/_schemas/*.schema.json` | all files | JSON schema validation artifacts. |
| M-003 | `config/docs/*.md` | all files | Passport documentation. Informational. |
| M-004 | `config/aurora/strategies.yaml` | `version: "1.0.0"` | Version marker. No runtime behavior. |

---

## REMOVE_OR_REPOINT

| surface_id | file | yaml_path | action |
|------------|------|-----------|--------|
| RR-001 | `config/aurora/system.yaml` | `ops.*` | Remove. Repoint any consumers to `trading.ops.*` OR elevate system.ops to SSOT and remove trading.ops.* (choose one). |
| RR-002 | `config/aurora/system.yaml` | `execution.*` (all except watchdog which is already removed) | Remove. Migration target: `trading.execution.*`. |
| RR-003 | `config/aurora/system.yaml` | `trading_mode:` at root | Remove after confirming `AuroraConfig.trading_mode` sources from this path. If this IS the canonical source, remove `trading.mode` from trading.yaml instead. Verify before acting. |
| RR-004 | `config/aurora/strategies/aurora.yaml` | `assets.DOGEUSDT.enabled: true` | Set to `false` to match strategies.yaml registry (DOGEUSDT commented out). |
| RR-005 | `config/aurora/trading.yaml` | `trading.market_data.macro_sync.anchor_update_from_ticks: false` | Align with `domains.feature_engineering.macro_sync.anchor_update_from_ticks: true` IF the two configs are meant to be consistent. Or document intentional divergence. |
| RR-006 | `config/alpha_search.yaml` | `alpha_search.legacy.*` | Remove the entire `legacy:` block. It is labeled as ignored. |
| RR-007 | `config/aurora/archive/aurora_phase3_production.yaml` | entire file | Delete. |
| RR-008 | `config/aurora/archive/features.yaml.deprecated` | entire file | Delete. |
| RR-009 | `config/alpha_search/scenario_matrix_v2_backup_20260224.yaml` | entire file | Delete. |
| RR-010 | `config/aurora/trading.yaml` | `trading.regime_tpsl: null` | Remove null stub. |
| RR-011 | `config/aurora/system.yaml` | `brackets: null` | Remove null stub. |

---

## Summary Counts

| classification | count |
|---------------|-------|
| active | 45 |
| owner_split | 14 |
| legacy_compat | 4 |
| dead_schema | 14 |
| metadata_only | 4 |
| remove_or_repoint | 11 |
| **total** | **92** |

---

## Final Verdict

```
SHARDING_BLOCKED_BY_SPLIT_BRAIN
```

14 confirmed owner_split surfaces across system.yaml/trading.yaml and instruments.yaml.
4 of these (OS-001, OS-004, OS-005, OS-010) are operationally risky.
Physical sharding cannot proceed until the split-brain surfaces are resolved.

The single bounded next task: resolve OS-001 (ops.panic_killswitch split-brain) as Step 1,
as described in CONFIG_OWNERSHIP_MAP_v1.md Section 8.
