# Project Structure: Olimp_v1

This document outlines the complete structure of the Olimp_v1 project, focusing on key directories and files. The project is a migration of QuantumTraderX to a federated FSM architecture on vFoundation.

## Overview
- **Repository**: Olimp_v1
- **Owner**: wekabeka1996
- **Current Branch**: feat/vfoundation-aurora-integration
- **Default Branch**: main
- **Python Version**: 3.11.9
- **Test Coverage Target**: ≥90% (FSM components)
- **Hot Path SLO**: p95 ≤50ms, timeout_rate ≤1%, WHY-coverage ≥95%

## Key Directories and Files

### Root Level
- `apps/` - Application layer with domain implementations
- `aurora/` - Legacy Aurora components (being migrated)
- `config/` - Configuration management and schemas
- `docs/` - Documentation and project guides
- `htmlcov/` - HTML coverage reports
- `htmlcov_decision/` - Coverage reports for decision components
- `htmlcov_idemp/` - Coverage reports for idempotency components
- `logs/` - Application log files
- `ops/` - Operations and tooling
- `schemas/` - Generated JSON schemas (JSON Schema 2020-12)
- `scripts/` - Utility scripts
- `tests/` - Comprehensive test suite (80+ test files)
- `vfoundation/` - Core vFoundation library
- `AUDIT_REPORT.md` - Audit report
- `AUDIT_REPORT_V2.md` - Updated audit report
- `conftest.py` - Pytest configuration with dev defaults
- `coverage.xml` - Coverage report data
- `GEMINI.md` - Gemini integration documentation
- `JOURNAL.md` - Action journaling with RID tracking
- `JOURNAL_Aurora.md` - Aurora-specific development journal
- `mypy.ini` - MyPy static type checking configuration
- `pytest.ini` - Pytest configuration with asyncio support
- `README.md` - Project README with setup instructions
- `TASK.md` - Task documentation
- `TODO.md` - Task tracking with GitHub task lists
- `vFoundation Implementation Status Report.md` - Implementation status report

Note: Documentation and project listings ignore temporary and generated 'junk' folders such as `__pycache__/`, `htmlcov/`, and local virtual environment directories like `.venv/` unless specifically relevant.

### apps/
- `__init__.py`
- `reference/` - Reference Aurora application implementation
  - `__init__.py`
  - `main.py` - Application entry point with FSM orchestration
  - `config_loader.py` - YAML configuration loading with environment overrides
  - `numeric_context.py` - Decimal arithmetic context for financial calculations
  - `api/` - FastAPI endpoints for debugging and monitoring
    - `main.py` - API server with /debug, /metrics, /replay endpoints
    - `__init__.py`
  - `domains/` - Domain-specific FSM implementations (federated architecture)
    - `__init__.py`
    - `account_balance/` - Account balance monitoring domain
      - `account_connector.py` - Binance API integration for balance/position data
      - `account_observer.py` - AccountObserver FSM for trade monitoring
      - `domain_dict.json` - Domain configuration
      - `__init__.py`
      - `schemas/` - Domain-specific schemas
    - `decision_making/` - Trading decision domain
      - `decision_making.py` - DecisionMaking FSM aggregating signals/risk/portfolio
      - `domain_dict.json` - Domain configuration
      - `__init__.py`
      - `schemas/` - Domain-specific schemas
    - `execution_position/` - Position execution domain (Order/Position/Bracket FSMs)
      - `contracts.py` - Contract definitions
      - `drift_monitor.py` - Drift detection and monitoring
      - `fsm_close.py` - Position close FSM
      - `fsm_manage.py` - Position management FSM
      - `fsm_open.py` - Position open FSM
      - `fsm.py` - Main execution FSM
      - `__init__.py`
    - `feature_engineering/` - Feature engineering domain
      - `feature_engineering.py` - FeatureEngineering FSM for signal calculation
      - `domain_dict.json` - Domain configuration
      - `__init__.py`
      - `schemas/` - Domain-specific schemas
    - `market_data/` - Market data domain
      - `market_data_connector.py` - WebSocket connector for Binance market data
      - `domain_dict.json` - Domain configuration
      - `__init__.py`
      - `schemas/` - Domain-specific schemas
        - `market_tick_v1.json` - Market tick schema
    - `position_tracking/` - Position tracking domain
      - `position_tracking.py` - PositionTracking FSM for portfolio state management
      - `domain_dict.json` - Domain configuration
      - `__init__.py`
      - `schemas/` - Domain-specific schemas
    - `regime_detector/` - Market regime detection domain
      - `regime_detector.py` - RegimeDetector class: detects TREND_UP, TREND_DOWN, MEAN_REVERSION, HIGH_VOLATILITY
      - `domain_dict.json` - Domain contract describing events (imports/exports)
      - `__init__.py`
      - `schemas/` - Domain event schemas
        - `regime_detected_v1.json` - Schema for EVT:REGIME_DETECTED
    - `risk_management/` - Risk management domain (Safety + Sizing FSMs)
      - `risk_management.py` - RiskManagement FSM for position sizing and risk assessment
      - `domain_dict.json` - Domain configuration
      - `__init__.py`
      - `schemas/` - Domain-specific schemas

### aurora/
- `__init__.py`
- `aur_main.py` - Main Aurora application
- `loader.py` - Configuration loader
- `risk_manager.py` - Risk management component
- `calibrator/` - Calibration components
- `decision/` - Decision making components
- `features/` - Feature engineering components
- `governance/` - Governance components
- `obs/` - Observability components
- `positions/` - Position management components
- `regime/` - Regime detection components
- `risk/` - Risk assessment components
- `scalp_daemon/` - Scalping daemon components
- `signal/` - Signal processing components
- `tca/` - Transaction cost analysis components

### config/
- `__init__.py`
- `_schemas/` - Schema storage
  - `aurora/` - Aurora schemas

### docs/
- `DR_IMPLEMENTATION_SUMMARY.md` - Disaster recovery implementation summary
- `DR_PLAYBOOK.md` - Disaster recovery playbook
- `project_structure.md` - This file
- `docs_vfoundation/` - vFoundation-specific documentation
- ` �   � � �   � � �/` - Additional documentation

### ops/
- `reports/` - Operational reports
- `wal/` - Write-Ahead Logging data

### schemas/
- `message_v1.json` - Generated message schema

### scripts/
- Utility scripts (specific files not detailed)

### tests/
- **Total**: 80+ test files with comprehensive coverage
- `conftest.py` - Pytest fixtures and dev environment setup
- `domains/` - Domain-specific integration tests
  - `test_account_observer.py` - AccountObserver FSM tests (10 tests)
  - `test_config_loader.py` - Configuration loading tests (18 tests)
  - `test_decision_making.py` - DecisionMaking FSM tests (4 tests)
  - `test_feature_engineering.py` - FeatureEngineering FSM tests (3 tests)
  - `test_market_data.py` - MarketData connector tests (4 tests, 1 failed - import issue)
  - `test_position_tracking.py` - PositionTracking FSM tests (9 tests)
  - `test_risk_management.py` - RiskManagement FSM tests (1 test)
  - `test_integration_three_domains.py` - Multi-domain integration tests (2 tests)
- `adapters/` - Adapter component tests (15+ files)
  - `test_execution_adapter_*.py` - Execution adapter tests (stream, dry-run, env, etc.)
  - `test_sdk_adapter_binance*.py` - Binance SDK adapter tests (10+ tests)
  - `test_idempotency_ledger_stats.py` - Idempotency ledger tests
- `idempotency/` - Idempotency system tests (15+ files)
  - `test_functional.py` - Core idempotency functionality (7 tests)
  - `test_error_paths.py` - Error handling and edge cases (17 tests)
  - `test_cb_*.py` - Circuit breaker tests (5+ files)
  - `test_race.py` - Concurrency and race condition tests (2 tests)
  - `test_ttl_resilience.py` - TTL and timeout handling (2 tests)
- `integration/` - End-to-end integration tests
  - `test_aurora_core_flow.py` - Full Aurora flow test (1 test)
  - `test_real_config_integration.py` - Real config integration (4 tests)
- Core vFoundation tests (40+ files):
  - `test_wal_*.py` - WAL functionality tests (15+ files, 40+ tests)
  - `test_config_env_overrides.py` - Configuration tests (20 tests)
  - `test_why_chain.py` - WHY explanation chain tests (6 tests)
  - `test_debug_*.py` - Debug and monitoring tests (5+ files)
  - `test_*_coverage.py` - Coverage and edge case tests
  - `test_*_smoke.py` - Smoke tests for basic functionality
  - `test_acl_*.py` - Access control tests
  - `test_rbac.py` - Role-based access control tests
  - `test_security_*.py` - Security component tests
  - `test_metrics_*.py` - Metrics and observability tests
  - `test_cli_*.py` - CLI tool tests
  - `test_contracts.py` - Contract validation tests
  - `test_fail_closed_behavior.py` - Fail-closed behavior tests
  - `test_circuit_breaker.py` - Circuit breaker tests
  - FSM tests: `test_fsm_*.py` - FSM lifecycle tests
  - Routing tests: `test_routing_*.py` - Message routing tests
  - Cache tests: `test_ttl_cache.py` - TTL cache tests

### vfoundation/
- `README.md` - Library README
- `pyproject.toml` - Python project configuration
- `mypy.ini` - MyPy configuration
- `pytest.ini` - Pytest configuration
- `ruff.toml` - Ruff linting configuration
- `apps/` - Application templates
  - `reference/`
    - `domains/`
      - `execution_position/`
        - `__init__.py`
- `cli/` - Command-line interface
  - `vfound/`
    - `__init__.py`
    - `__main__.py`
- `configs/` - Configuration files
  - `adapter.yaml`
  - `idempotency.yaml`
- `dictionaries/` - Schema dictionaries
  - `global_v2_2.yaml`
  - `domain/`
    - `audit_xai.yaml`
    - `execution_position.yaml`
    - `risk_strategy.yaml`
- `examples/` - Example configurations
  - `flow.yaml`
- `schemas/` - Schema generation output
  - `README.md`
- `vfoundation/` - Core library modules
  - `__init__.py`
  - `config.py`
  - `py.typed`
  - `adapters/` - Exchange adapters
    - `exchange/`
      - `acl.py`
      - `__init__.py`
  - `apps/` - Application framework
    - `__init__.py`
    - `reference/`
      - `__init__.py`
      - `domains/`
        - `__init__.py`
        - `execution_position/`
          - `__init__.py`
  - `core/` - Core FSM components
    - `degradation.py`
    - `fsm.py`
    - `idempotency.py`
    - `meta_fsm.py`
    - `protocol.py`
    - `retry_cb.py`
    - `routing.py`
    - `ttl.py`
    - `adapters/` - Core adapters
      - `execution_adapter.py`
      - `execution_exceptions.py`
      - `idempotency_ledger.py`
      - `sdk_adapter_binance.py`
      - `__init__.py`
    - `cache/` - TTL cache
      - `ttl_cache.py`
      - `__init__.py`
    - `idempotency/` - Idempotency management
      - `errors.py`
      - `store.py`
      - `__init__.py`
      - `backends/` - Storage backends
        - `redis_protocol.py`
        - `redis_store.py`
        - `simple_redis_store.py`
        - `__init__.py`
  - `dataref/` - Data reference utilities
    - `signed_urls_stub.py`
    - `streaming_io.py`
  - `dr/` - Disaster Recovery
    - `merkle.py`
    - `replay.py`
    - `snapshot.py`
    - `wal.py`
  - `obs/` - Observability
    - `debug_api.py`
    - `logging.py`
    - `tracing.py`
    - `why.py`
  - `security/` - Security components
    - `ratelimits.py`
    - `rbac_abac.py`
    - `redaction.py`
    - `signing_ed25519.py`

### dictionaries/
- `global_v2_2.yaml` - Global dictionary
- `domain/` - Domain-specific dictionaries
  - `audit_xai.yaml`
  - `execution_position.yaml`
  - `risk_strategy.yaml`

## Domain Order & Implementation Status (v1)

### Implemented Domains (FSMP-OBSERVE-T01 completed):
1. **account_balance** ✅ - Account balance monitoring (AccountObserver FSM)
   - Status: ✅ Implemented, tested, integrated
   - Components: account_connector.py, account_observer.py
   - Tests: 10/10 passing, 88% coverage

2. **decision_making** ✅ - Trading decision aggregation (DecisionMaking FSM)
   - Status: ✅ Implemented, tested, integrated
   - Components: decision_making.py (aggregates features + risk + portfolio)
   - Tests: 4/4 passing (fixed critical state management bug)

3. **feature_engineering** ✅ - Signal calculation (FeatureEngineering FSM)
   - Status: ✅ Implemented, tested, integrated
   - Components: feature_engineering.py
   - Tests: 3/3 passing

4. **position_tracking** ✅ - Portfolio state management (PositionTracking FSM)
   - Status: ✅ Implemented, tested, integrated
   - Components: position_tracking.py
   - Tests: 9/9 passing

5. **risk_management** ✅ - Risk assessment and sizing (RiskManagement FSM)
   - Status: ✅ Implemented, tested, integrated
   - Components: risk_management.py
   - Tests: 1/1 passing

### Partially Implemented:
6. **market_data** ⚠️ - Market data streaming
   - Status: ⚠️ Connector implemented, tests failing (import issue)
   - Components: market_data_connector.py (WebSocket integration)
   - Tests: 4 tests, 1 failing due to import path issues

### Planned Domains (Next phases):
7. **execution_position** - Order/Position/Bracket (3 FSMs)
8. **risk_strategy** - Safety + Sizing (2 FSMs)
9. **analyzer** - Signal + Regime (2 FSMs)
10. **xai_audit** (1 FSM)
11. **data_monitoring** (2 FSMs)
12. **reward_alysha** (1 FSM)
13. **rl_core** (3 FSMs)

## Architecture Components

### Core FSM Components
- **OrchestratorFSM**: RID lifecycle, why_chain, TTL/CB/idempotency coordination
- **MetaFSM**: Registry, schema canary, freeze management
- **Domain FSMs**: Federated domain-specific state machines

### Data Flow Architecture
- **TRADE → FEATURES** → **RISK ASSESSMENT** → **PORTFOLIO STATE** → **DECISION** → **EXECUTION**
- Event-driven communication via Message protocol
- WHY chain explanations for all decisions
- Idempotency guarantees with distributed ledger

### Contracts & Schemas
- **JSON Schema 2020-12** with `$id` required for all schemas
- **Additive-only versioning** (no breaking changes)
- Schema generation: `vfound schema` command
- Generated schemas in `schemas/` directory

### Security & Reliability
- **Ed25519 signing** for high-risk DEC/CMD operations (OPEN/CLOSE/ADJUST)
- **RBAC/ABAC** access control with admin tokens
- **Circuit breakers** with configurable thresholds
- **Idempotency** with TTL-based cleanup and conflict resolution
- **WAL (Write-Ahead Logging)** with Merkle tree integrity
- **Fail-closed behavior** with detailed error logging

### Observability & Debugging
- **Structured JSONL logging** to stdout
- **WHY explanations** with 95%+ coverage target
- **Tracing and metrics** via FastAPI endpoints (`/debug`, `/metrics`, `/replay`)
- **Drift detection** and replay capabilities
- **Debug API** for runtime inspection

## Quality Assurance Status

### Test Coverage (80+ test files analyzed)
- **Domains**: 6/7 implemented domains fully tested ✅
- **Core Components**: WAL, Idempotency, Circuit Breakers, Routing ✅
- **Integration**: End-to-end Aurora flows tested ✅
- **Adapters**: Binance SDK, Execution adapters tested ✅
- **Configuration**: Environment overrides, validation tested ✅

### Code Quality
- **Linting**: Ruff checks passing ✅
- **Type Checking**: MyPy strict mode passing ✅
- **Import Order**: E402 errors fixed ✅
- **Test Execution**: 95%+ tests passing ✅

### Known Issues
- **market_data import**: Path resolution issue in test environment
- **Async cleanup**: Some tests leave background threads (non-critical)
- **Type compatibility**: Minor float/Decimal mixing warnings

## Build and Test

### Commands
- **Schema generation**: `vfound schema`
- **Run tests**: `pytest -q` (target ≥90% coverage, FSM components)
- **Linting**: `ruff check` + `mypy --strict`
- **Coverage**: `pytest --cov` with HTML reports

### Performance Targets
- **Hot path SLO**: p95 ≤50ms overall, ≤100ms end-to-end
- **Timeout rate**: ≤1% of operations
- **WHY coverage**: ≥95% of decisions explained
- **Test coverage**: ≥90% for FSM components

### Development Workflow
- **Contracts first**: Define schemas → Generate code → Implement FSMs
- **Task tracking**: `TODO.md` with GitHub task lists
- **Journaling**: `JOURNAL.md` with RID and WHY for all actions
- **Commits**: Conventional commits with FSMP prefixes

## Current Development Status

### ✅ Completed Phases
- **FSMP-OBSERVE-T01**: AccountObserver implementation and testing
  - Account balance monitoring via Binance API
  - Trade event processing and payload transformation
  - Comprehensive test suite (10/10 tests passing)
  - Integration with Aurora core FSM federation

### 🔄 In Progress
- **FSMP-DEEP-T01**: Regime detection and signal processing
  - Feature engineering for market signals
  - Risk assessment and position sizing
  - Decision making aggregation logic
  - Multi-domain integration testing

### 📋 Next Phases (Planned)
- **FSMP-EXECUTE-T01**: Position execution and management
- **FSMP-LEARN-T01**: Reinforcement learning integration
- **FSMP-DR-T01**: Disaster recovery and replay systems
- **FSMP-OBSERVE-T02**: Enhanced observability and monitoring

### 📊 Project Metrics
- **Lines of Code**: ~15K+ across Python modules
- **Test Files**: 80+ with comprehensive coverage
- **Domains Implemented**: 6/13 core domains
- **Schema Coverage**: 95%+ of data contracts defined
- **Integration Tests**: End-to-end Aurora flows validated

## Dependencies & Environment

### Core Dependencies
- **Python 3.11.9** - Runtime environment
- **vFoundation** - Core FSM and infrastructure library
- **FastAPI** - API endpoints for debugging/monitoring
- **PyYAML** - Configuration file parsing
- **python-binance** - Exchange API integration
- **redis** - Distributed caching and idempotency
- **pydantic** - Data validation and serialization

### Development Tools
- **pytest** - Testing framework with asyncio support
- **mypy** - Static type checking
- **ruff** - Fast Python linter
- **coverage.py** - Code coverage reporting

### Environment Variables
- `RBAC_ADMIN_TOKENS` - Admin access tokens (dev defaults provided)
- `SIGNING_KEY` - Ed25519 signing key (dev defaults provided)
- `WORKER_ID` - Worker identification (auto-generated)
- `EXECUTION_MODE` - dry_run/paper/live execution modes
- `WAL_DIR` - Write-ahead log directory
- `REDIS_URL` - Redis connection string