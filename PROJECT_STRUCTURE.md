# Project Structure Overview

## Root Directory (Essential Files Only)

- **README.md** - Project documentation
- **JOURNAL.md** - Development activity log (RID-based)
- **TODO.md** - Active tasks and roadmap
- **TASK.md** - Current sprint focus
- **requirements.txt** - Python dependencies
- **pytest.ini** - Test configuration
- **mypy.ini** - Type checking configuration
- **package.json** - npm dependencies
- **.env** / **.env.example** - Environment configuration
- **.gitignore** - Git exclusions
- **.copilotignore** - Copilot exclusions
- **.geminiignore** - Gemini exclusions

## Core Directories

### `vfoundation/` - FSM Core Library
```
vfoundation/
├── core/                    # FSM engine, routing, TTL/idempotency
├── infrastructure/          # DR (WAL, Merkle, snapshot), observability
├── security/               # Ed25519 signing, RBAC
└── contrib/                # AWS Lambda, CloudEvents adapters
```

### `apps/reference/` - Federated FSM Demo Application
```
apps/reference/
├── domains/               # Business domains (Risk, Execution, Analysis)
│   ├── execution_position/    # 3-FSM architecture (Order, Position, Bracket)
│   ├── risk_strategy/         # Safety/sizing decisions
│   ├── analyzer/              # Signal aggregation, regime-based decisions
│   ├── xai_audit/             # Explainability & compliance
│   ├── data_monitoring/       # Feature/market data monitoring
│   ├── reward_alysha/         # Reinforcement learning rewards
│   └── rl_core/               # RL agent core
├── adapters/              # External integrations (Binance, Redis, etc.)
├── config_loader.py       # Configuration management
└── routes.py              # FastAPI endpoints
```

### `tests/` - Test Suite (1224 tests)
```
tests/
├── order_guardian/        # OrderGuardian service tests
├── domains/               # Domain-specific integration tests
├── units/                 # Unit tests by component
├── integration/           # End-to-end tests
├── conftest.py            # pytest fixtures
└── test_*.py              # Test modules (93 files total)
```

### `schemas/` - Contract Definitions
```
schemas/
├── *.json                 # JSON Schema 2020-12 format
└── (auto-generated from dictionaries/)
```

### `dictionaries/` - YAML Specifications
```
dictionaries/
├── acl.yaml               # Message ACL definitions
├── events.yaml            # Event schemas
├── commands.yaml          # Command contracts
└── *.yaml                 # Domain specifications
```

### `configs/` - Configuration Templates
```
configs/
├── master_config_v1.yaml  # Production profile
├── frozen/                # Immutable runtime configs
└── aurora/                # Trading profiles
```

### `tools/` - Utility Scripts
```
tools/
├── check_orders.py        # Order verification
├── duckdb_stub.py         # Test database stub
├── measure_api_latency.py # Performance measurement
└── smoke_tidy_gate.py     # Quick smoke test
```

### `scripts/` - Automation
```
scripts/
├── *.py                   # Automation workflows
└── *.sh                   # Shell scripts
```

### `docs/` - Documentation
```
docs/
├── ROADMAP_DELTA_EMPTY_BRANCH.md
├── CENTRAL_FSM_SPEC.md
├── FIX_PLAN_ORPHANED_BRACKETS.md
├── PROJECT_ATLAS.md
└── *.md                   # Technical specifications
```

## Files Structure Rationale

### What's in Root (16 files)
✅ **Preserved**: Only essential files that developers need immediate access to:
- Configuration files
- Environment setup
- Documentation entry points
- Project metadata

### What's Moved to `tests/`
✅ **Consolidated**: All 93 test files now organized in one location:
- Previously scattered across root
- Unit tests, integration tests, domain tests
- Now easily discoverable and runnable

### What's Moved to `tools/`
✅ **Organized**: Utility and diagnostic scripts:
- check_orders.py (order verification)
- duckdb_stub.py (test database mock)
- measure_api_latency.py (performance measurement)
- smoke_tidy_gate.py (quick validation)

### What's Removed (62 files)
❌ **Deleted**: Deprecated/legacy files:
- Old migration scripts (Pydantic v1→v2 migration complete)
- Debug temporary files (*.json analyses, *.txt outputs)
- Session summaries (Phase 1-7 complete)
- Legacy READMEs (consolidated into main docs)

## Quick Commands

```bash
# Run all tests
pytest tests/ -v

# Run smoke tests
pytest tests/ -k "smoke or ci" -v

# Collect all tests (verify structure)
pytest tests/ --collect-only -q

# Type checking
mypy apps/ vfoundation/ --config-file=mypy.ini

# Check project structure
python -c "import os; print('\\n'.join(sorted([d for d in os.listdir('.') if os.path.isdir(d) and not d.startswith('.')])))"
```

## Key Metrics

- **Total Tests**: 1,224
- **Test Modules**: 93 files
- **Root Files**: 16 (down from 82)
- **Main Packages**: 7 (vfoundation, apps, tests, schemas, tools, scripts, docs)
- **FSM Domains**: 7
- **Coverage Target**: 90% (FSM modules)

## For Developers

1. **Start here**: README.md for project overview
2. **Check status**: JOURNAL.md for latest updates
3. **Run tests**: `pytest tests/`
4. **Find code**: Check `apps/` for features, `vfoundation/` for infrastructure
5. **Check contracts**: Review `schemas/` and `dictionaries/` for data formats
6. **Debug**: Use `tools/` scripts for diagnostics

---

**Last Updated**: 2025-11-09
**Cleanup Status**: ✅ Complete
