# Repository structure overview

The repository combines the Aurora reference implementation in `apps/` with a handful of supporting folders (`config`, `configs`, `bridge`, `vfoundation`) and a global log sink. The sections below describe how each directory is laid out as of this commit.

## Directory skeleton

```
config/
├── aurora/
├── _schemas/
confsig/               # not a live folder; see notes below for where signatures live
bridge/
├── bridge_feature_collection.py
├── live_feature_collector.py
vfoundation/
├── adapters/
├── cli/
├── core/
├── dataref/
├── dictionaries/
├── dr/
├── examples/
├── obs/
├── schemas/
├── security/
├── services/
├── configs/
├── config.py
└── errors.py
```

Commentary on the green folders follows in the detailed sections below.

## Full skeletons

### apps/clean_TP_SL/

```
apps/clean_TP_SL/
├── __init__.py
├── order_guardian.py
├── order_ledger.py
└── __pycache__/
    ├── __init__.cpython-311.pyc
    ├── __init__.cpython-314.pyc
    ├── order_guardian.cpython-311.pyc
    ├── order_guardian.cpython-314.pyc
    ├── order_ledger.cpython-311.pyc
    └── order_ledger.cpython-314.pyc
```

### apps/reference/

```
apps/reference/
├── config_exposure_policy.py
├── config_loader.py
├── config_models.py
├── config_symbols.py
├── dr_loader.py
├── main.py
├── main.py.bak
├── numeric_context.py
├── __init__.py
├── adapters/
│   ├── __init__.py
│   ├── binance_adapter.py
│   ├── sdk_adapter_binance.py
│   └── exchange/
│       ├── __init__.py
│       └── acl.py
├── alpha_discovery/
│   ├── __init__.py
│   ├── backtest_engine.py
│   └── example_backtest.py
├── api/
│   ├── __init__.py
│   ├── main.py
│   └── metrics.py
├── bootstrap/
│   └── preflight.py
├── data/
│   ├── __init__.py
│   └── feature_store.py
├── dictionaries/
│   └── global_v2_2.yaml
├── domains/
│   ├── account_balance/
│   │   ├── __init__.py
│   │   ├── account_connector.py
│   │   └── Readme/
│   │       ├── ANALYSIS_SUMMARY.md
│   │       ├── API_DEPENDENCIES.md
│   │       ├── EVENTS.md
│   │       ├── README.md
│   │       └── TESTING.md
│   ├── account_observer/
│   │   ├── __init__.py
│   │   ├── account_observer.py
│   │   ├── domain_dict.json
│   │   └── Readme/
│   │       ├── ANALYSIS_SUMMARY.md
│   │       ├── EVENTS.md
│   │       ├── README.md
│   │       └── TESTING.md
│   ├── alpha_search/
│   │   ├── __init__.py
│   │   ├── alpha_model.py
│   │   ├── ANALYSIS_SUMMARY.md
│   │   ├── API_DEPENDENCIES.md
│   │   ├── ensemble.py
│   │   ├── EVENTS.md
│   │   ├── README.md
│   │   ├── TESTING.md
│   │   └── models/
│   │       ├── __init__.py
│   │       ├── mean_reversion.py
│   │       ├── momentum.py
│   │       └── volatility.py
│   ├── decision_making/
│   │   ├── __init__.py
│   │   ├── ANALYSIS_SUMMARY.md
│   │   ├── API_DEPENDENCIES.md
│   │   ├── decision_making.py
│   │   ├── deferred_scheduler.py
│   │   ├── dm_log_adapter.py
│   │   ├── domain_dict.json
│   │   ├── EVENTS.md
│   │   ├── normalized_reject_reasons.py
│   │   ├── README.md
│   │   ├── TESTING.md
│   │   ├── why_codes.py
│   │   └── schemas/
│   │       └── trade_intent_v1.json
│   ├── execution_management/
│   │   ├── __init__.py
│   │   ├── ANALYSIS_SUMMARY.md
│   │   ├── API_DEPENDENCIES.md
│   │   ├── EVENTS.md
│   │   ├── execution_management.py
│   │   ├── README.md
│   │   └── TESTING.md
│   ├── execution_position/
│   │   ├── __init__.py
│   │   ├── adapter_factory.py
│   │   ├── agg_oco_introspection.py
│   │   ├── algo_order_index.py
│   │   ├── aurora_log_adapter.py
│   │   ├── binance_execution_adapter.py
│   │   ├── brackets_config.py
│   │   ├── config.py
│   │   ├── contracts.py
│   │   ├── drift_monitor.py
│   │   ├── execution_adapter.py
│   │   ├── EXECUTION_POSITION_INVARIANTS.md
│   │   ├── exposure_guard.py
│   │   ├── fsm_close.py
│   │   ├── fsm_manage.py
│   │   ├── fsm_open.py
│   │   ├── idempotent_cancel.py
│   │   ├── internal_types.py
│   │   ├── legacy/
│   │   ├── manage_config.py
│   │   ├── metrics_aggregator.py
│   │   ├── metrics_collector.py
│   │   ├── order_index.py
│   │   ├── runtime_factory.py
│   │   ├── shadow_execpos/
│   │   │   ├── __init__.py
│   │   │   ├── ab_replay.py
│   │   │   ├── agg_oco_replay.py
│   │   │   ├── async_manager.py
│   │   │   ├── bracket_service.py
│   │   │   ├── close_flow.py
│   │   │   ├── event_adapter.py
│   │   │   ├── execution_service.py
│   │   │   ├── exposure_bridge.py
│   │   │   ├── gatekeeper.py
│   │   │   ├── idempotency.py
│   │   │   ├── logging_v2.py
│   │   │   ├── position_model.py
│   │   │   ├── price_enricher.py
│   │   │   ├── runtime.py
│   │   │   ├── trailing.py
│   │   │   ├── types.py
│   │   │   ├── wal_writer.py
│   │   │   └── watchdog.py
│   │   ├── simulated_adapter.py
│   │   ├── soft_clip.py
│   │   ├── utils.py
│   │   ├── utils_event_bus.py
│   │   ├── watchdog.py
│   │   └── docs/
│   │       └── ...
│   │   # ExecPosRuntimeV2 (shadow_execpos) is the default runtime.
│   │   # Legacy FSMs (fsm_open/manage/close) are deprecated/historical.
│   ├── feature_engineering/
│   │   ├── __init__.py
│   │   ├── ANALYSIS_SUMMARY.md
│   │   ├── API_DEPENDENCIES.md
│   │   ├── config.py
│   │   ├── domain_dict.json
│   │   ├── EVENTS.md
│   │   ├── feature_engineering.py
│   │   ├── feature_engineering_phase1.py
│   │   ├── README.md
│   │   ├── TESTING.md
│   │   └── schemas/
│   │       └── features_calculated_v1.json
│   ├── market_data/
│   │   ├── __init__.py
│   │   ├── ANALYSIS_SUMMARY.md
│   │   ├── API_DEPENDENCIES.md
│   │   ├── CHANGELOG.md
│   │   ├── DEPLOYMENT.md
│   │   ├── EVENTS.md
│   │   ├── market_data_connector.py
│   │   ├── README.md
│   │   ├── TESTING.md
│   │   ├── TROUBLESHOOTING.md
│   │   └── websocket_aggregator.py
│   ├── position_tracking/
│   │   ├── __init__.py
│   │   ├── ANALYSIS_SUMMARY.md
│   │   ├── API_DEPENDENCIES.md
│   │   ├── CHANGELOG.md
│   │   ├── DEPLOYMENT.md
│   │   ├── domain_dict.json
│   │   ├── EVENTS.md
│   │   ├── position_tracking.py
│   │   ├── README.md
│   │   ├── TESTING.md
│   │   ├── TROUBLESHOOTING.md
│   │   └── schemas/
│   │       ├── portfolio_state_v1.json
│   │       └── trade_executed_v1.json
│   ├── regime_detector/
│   │   ├── __init__.py
│   │   ├── ANALYSIS_SUMMARY.md
│   │   ├── API_DEPENDENCIES.md
│   │   ├── config.py
│   │   ├── domain_dict.json
│   │   ├── EVENTS.md
│   │   ├── README.md
│   │   ├── regime_detector.py
│   │   ├── TESTING.md
│   │   └── schemas/
│   │       └── regime_detected_v1.json
│   ├── risk_management/
│   │   ├── __init__.py
│   │   ├── ANALYSIS_SUMMARY.md
│   │   ├── API_DEPENDENCIES.md
│   │   ├── daily_gate.py
│   │   ├── domain_dict.json
│   │   ├── EVENTS.md
│   │   ├── README.md
│   │   ├── risk_management.py
│   │   ├── TESTING.md
│   │   └── schemas/
│   │       └── risk_assessment_v1.json
│   └── snapshot_scheduler/
│       ├── __init__.py
│       └── snapshot_scheduler.py
├── monitoring/
│   └── performance_monitor.py
├── orchestrator/
│   ├── __init__.py
│   ├── orchestrator_fsm.py
│   ├── types.py
│   └── utils_event_bus.py
├── schemas/
│   └── order_logger_v1.json
├── services/
│   ├── __init__.py
│   ├── ledger_store_adapter.py
│   └── order_guardian.py
├── telemetry/
│   ├── alerts.py
│   ├── audit_logger.py
│   ├── metrics.py
│   └── order_logger.py
└── utils/
    ├── __init__.py
    ├── tp_sl_calculator.py
    ├── trade_cooldowns.py
    └── trading_modes.py
```

### config/aurora/

```
config/aurora/
├── regime.yaml
├── system.yaml
├── trading.yaml
├── trading.staging.override.yaml
└── trading_v0.2.yaml
```

### config/_schemas/

```
config/_schemas/
├── aurora_system.schema.json
├── aurora_trading.schema.json
├── backtest.schema.json
├── obs_jobs.schema.json
├── ops_dr.schema.json
├── ops_monitoring.schema.json
├── ops_orchestration.schema.json
├── ops_security.schema.json
├── ops_testing.schema.json
├── portfolio.schema.json
├── scalp_system.schema.json
├── scalp_trading.schema.json
└── frozen/
    └── aurora_trading_20251030.json
```

### configs/

```
configs/
├── master_config_v1.yaml
├── testnet_exchangeinfo.json
└── frozen/
    └── master_config_v1_20251030.yaml
```

### bridge/

```
bridge/
├── bridge_feature_collection.py
└── live_feature_collector.py
```

### vfoundation/

```
vfoundation/
├── adapters/
│   ├── __init__.py
│   ├── binance_adapter.py
│   ├── sdk_adapter_binance.py
│   └── exchange/
│       ├── __init__.py
│       └── acl.py
├── cli/
│   └── vfound/
│       ├── __init__.py
│       └── __main__.py
├── core/
│   ├── __init__.py
│   ├── degradation.py
│   ├── fsm.py
│   ├── fsm_core.py
│   ├── fsm_emit_compat.py
│   ├── meta_fsm.py
│   ├── protocol.py
│   ├── retry_cb.py
│   ├── routing.py
│   ├── ttl.py
│   └── why_codes.py
├── dataref/
│   ├── signed_urls_stub.py
│   └── streaming_io.py
├── dictionaries/
│   ├── global_v2_2.yaml
│   └── global_v2_2_framework.yaml
├── dr/
│   ├── merkle.py
│   ├── replay.py
│   ├── snapshot.py
│   ├── wal.py
│   └── wal_gc.py
├── examples/
│   └── flow.yaml
├── obs/
│   ├── correlation.py
│   ├── debug_api.py
│   ├── logger.py
│   ├── order_logger.py
│   ├── tracing.py
│   └── why.py
├── schemas/
│   └── README.md
├── security/
│   ├── ratelimits.py
│   ├── rbac_abac.py
│   ├── redaction.py
│   └── signing_ed25519.py
├── services/
│   └── price_service.py
├── configs/
│   ├── adapter.yaml
│   └── idempotency.yaml
├── config.py
├── errors.py
├── README.md
├── pyproject.toml
├── pytest.ini
├── mypy.ini
├── ruff.toml
├── py.typed
└── __init__.py
```

## apps/

`apps/` holds the runtime pieces for testing and running Aurora behaviors. Two packages live directly under `apps/`: `clean_TP_SL/` (TP/SL guardian scripts) and `reference/` (the orchestrated Aurora stack that pulls in adapters, domains, services, telemetry, and orchestrator helpers).

```
apps/
├── clean_TP_SL/
│   ├── order_guardian.py
│   ├── order_ledger.py
│   └── (package helpers)
└── reference/
    ├── adapters/
    ├── alpha_discovery/
    ├── api/
    ├── bootstrap/
    ├── domains/
    ├── monitoring/
    ├── orchestrator/
    ├── schemas/
    ├── services/
    ├── telemetry/
    ├── utils/
    ├── main.py
    └── dr_loader.py
```

### clean_TP_SL/

A lightweight package for Take Profit / Stop Loss guard rails. The two top-level modules, `order_guardian.py` and `order_ledger.py`, implement the basic safety checks and ledger exports. The folder keeps the logic isolated from the heavier reference implementation so it can be run independently.

### reference/

The `reference` package is the full Aurora stack used in staging and production playbooks. Key subcomponents include:

- `adapters/` (Binance adapters, SDK bindings, ACL helpers under `exchange/`).
- `alpha_discovery/` (backtest engine plus sample backtests).
- `api/` (REST surface where `main.py` and `metrics.py` live).
- `bootstrap/` plus `preflight.py` for readiness checks.
- `domains/` which contains FSM-powered workstreams (account balance/observer, alpha search, decision making, execution management, execution position, feature engineering, market data, position tracking, regime detector, risk management, snapshot scheduler).
- `monitoring/`, `telemetry/`, `services/`, and `utils/` for shared helpers, alerts, loggers, and trading-mode calculations.
- `orchestrator/` for FSM utilities, event buses, and helper types.
- `schemas/` for JSON schema artifacts such as `order_logger_v1.json`.
- `dr_loader.py` which bootstraps disaster recovery configurations.

`apps/reference/domains/execution_position/` deserves special mention: it bundles FSM implementations (`fsm.py`, `fsm_open.py`, `fsm_manage.py`, `fsm_close.py`), adapters (`aurora_log_adapter.py`, `binance_execution_adapter.py`, `simulated_adapter.py`), telemetry (`metrics_collector.py`, `metrics_aggregator.py`), config helpers (`manage_config.py`, `brackets_config.py`), guards (`exposure_guard.py`, `order_guardian.py`), and documentation/tests (`README.md`, `TESTING.md`, `ANALYSIS_SUMMARY.md`, plus unit tests for binance adapters and order index). This folder is the most active locus for execution logic.

## config/

`config/` centralizes the YAML and schema definitions that drive the reference stack. It currently exposes:

- `aurora/` with runtime configuration files (`regime.yaml`, `system.yaml`, `trading.yaml`, `trading_v0.2.yaml`, `trading.staging.override.yaml`).
- `_schemas/` with JSON Schema files (`aurora_system.schema.json`, `aurora_trading.schema.json`, `backtest.schema.json`, `obs_jobs.schema.json`, `ops_dr.schema.json`, `ops_monitoring.schema.json`, `ops_orchestration.schema.json`, `ops_security.schema.json`, `ops_testing.schema.json`, `portfolio.schema.json`, `scalp_system.schema.json`, `scalp_trading.schema.json`). These schemas double as the configuration signatures used by tooling.

## configs/

`configs/` gathers canonical snapshots and exchange metadata:

- `master_config_v1.yaml` is the consolidated reference config for Aurora.
- `testnet_exchangeinfo.json` mirrors Binance testnet exchange information.
- `frozen/master_config_v1_20251030.yaml` archives the previous master configuration.

## confsig (schema/signature support)

There is no dedicated `confsig/` directory today. Configuration signatures are maintained inside `config/_schemas/` and through the frozen snapshots in `configs/frozen/`. If a dedicated folder for serialized signatures is required later, it should track those artifacts.

## bridge/

`bridge/` contains auxiliary collectors that run outside the main executor:

- `bridge_feature_collection.py` collects historical feature data for downstream analysis.
- `live_feature_collector.py` gathers live features for diagnostics or feature-driven monitoring.

## vfoundation/

`vfoundation/` is the shared Python library consumed by the reference stack (and other packages). Its key contents are:

- Core packages: `adapters/`, `cli/`, `core/`, `dataref/`, `dictionaries/`, `dr/`, `examples/`, `obs/`, `schemas/`, `security/`, `services/`.
- Shared config helpers in `vfoundation/configs/` plus top-level modules `config.py` and `errors.py`.
- Project metadata (`pyproject.toml`, `pytest.ini`, `mypy.ini`, `ruff.toml`, `py.typed`) to keep typing and tooling in sync.

## logs/

Production and local logs now live at the repository root `logs/`. The folder keeps rotated Aurora logs (`aurora_core.log`, `aurora_core.log.1`, etc.), domain-specific files (`domain_execution_management.log`, `domain_risk_management.log`, `domain_feature_engineering.log`, `order_guardian.log`), plus structured outputs like `order_log_v1.jsonl`.

## Running the reference stack

Use the reference entry point to exercise the Aurora stack:

```bash
python -m apps.reference.main
```
