# Neocortex Domain

**Autonomous Learning System for Aurora Trading Platform**

---

## Overview

Neocortex is a **Shadow Mode** domain that learns market patterns using Variational Autoencoders (VAE) and Proximal Policy Optimization (PPO). It observes trading decisions without influencing them, building latent representations and learning optimal decision patterns.

**Architecture:** vFoundation (AsyncIO + Multiprocessing)  
**Status:** Phase 0 Complete - Foundation established  
**Type:** Observer (Non-trading)

---

## Quick Start

### 1. Install Dependencies
```bash
pip install pydantic pyyaml pytest
```

### 2. Run Tests
```bash
cd apps/reference/domains/neocortex
python3 -m pytest tests/test_config.py -v
```

**Expected:** 9 tests passing ✅

### 3. Start Domain
```bash
python3 main.py
```

**Expected Output:**
```
Loading configuration from: .../config
✓ Configuration validation passed
NEOCORTEX DOMAIN - SHADOW MODE
Features to ingest: 9
VAE latent dimensions: 16
PPO state dimensions: 20
Phase 0: Initialization complete. Entering idle loop...
```

Press `Ctrl+C` to stop.

---

## Configuration

All configuration is **strict and fail-closed** (no hidden defaults).

### Files

- `config/system.yaml` - Paths, multiprocessing, logging
- `config/ingest.yaml` - Feature selection, normalization
- `config/neuro.yaml` - VAE & PPO hyperparameters

### Example: Changing Feature List

Edit `config/ingest.yaml`:
```yaml
feature_list:
  - rsi
  - bb_percent
  - obi
  - liquidity_kappa
  # Add more features here
```

**IMPORTANT:** Update `vae.input_dim` in `config/neuro.yaml` to match!

---

## Architecture

```
┌─────────────────────────────────────────┐
│          Aurora Event Bus               │
│  (EVT:FEATURES_CALCULATED, etc.)        │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│        Neocortex Main Process           │
│         (AsyncIO Reactor)               │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │  Transport (Event Adapter)        │  │
│  └──────────────┬────────────────────┘  │
│                 │                        │
│                 ▼                        │
│  ┌───────────────────────────────────┐  │
│  │  Logic/Ingest (Feature Buffer)   │  │
│  │  - Normalization                 │  │
│  │  - Buffering                     │  │
│  └──────────────┬────────────────────┘  │
│                 │                        │
│                 ▼                        │
│  ┌───────────────────────────────────┐  │
│  │  IPC Queue                        │  │
│  └──────────────┬────────────────────┘  │
└─────────────────┼────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│       Brain Worker Process              │
│      (Multiprocessing Isolated)         │
│                                         │
│  ┌───────────────────────────────────┐  │
│  │  Logic/Brain                      │  │
│  │  - VAE Encoder/Decoder            │  │
│  │  - PPO Policy Network             │  │
│  │  - Model Checkpointing            │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

---

## Event Contract

### Imports (Consumes)
- `EVT:FEATURES_CALCULATED` - Market features from feature_engineering
- `EVT:TRADE_INTENT_PROPOSED` - Trade decisions from decision_making
- `EVT:POSITION_CLOSED` - Position outcomes for reward calculation

### Exports (Produces)
- `EVT:NEOCORTEX_STATE_UPDATED` - Latent state, learning progress
- `EVT:NEOCORTEX_ALERT` - Anomaly detection, insights

---

## Development Phases

### ✅ Phase 0: Foundation (COMPLETE)
- Directory structure
- Configuration contract (Pydantic V2)
- Domain contract (`domain.yaml`)
- Entry point skeleton
- Test suite (9/9 passing)

### 🔄 Phase 1: Ingestion (Next)
- Feature buffer implementation
- Normalization engine
- Event adapter
- Integration tests

### 📋 Phase 2: VAE Learning
- Latent space encoder/decoder
- Training loop
- Checkpoint management

### 📋 Phase 3: PPO Integration
- Integrate `PPO/` library
- Policy network
- Reward shaping

### 📋 Phase 4: Event Transport
- Event bus integration
- State emission
- Monitoring hooks

### 📋 Phase 5: Production Validation
- End-to-end testing
- Performance benchmarks
- Shadow mode validation

---

## Testing

### Configuration Tests
```bash
pytest tests/test_config.py -v
```

**Coverage:**
- Valid config loads ✅
- Missing fields rejected ✅
- Extra fields rejected ✅
- Type mismatches rejected ✅
- Cross-validation enforced ✅
- Immutability enforced ✅

### Future Tests
- `tests/test_ingest.py` - Feature buffering, normalization
- `tests/test_vae.py` - Latent encoding/decoding
- `tests/test_ppo.py` - Policy network forward pass
- `tests/test_integration.py` - End-to-end event flow

---

## Configuration Philosophy

**Fail-Closed, Explicit, Auditable**

1. ❌ **No Hidden Defaults** - All hyperparameters explicit in YAML
2. ✅ **Strict Validation** - `extra='forbid'` rejects unknown fields
3. ✅ **Type Safety** - Pydantic enforces types at runtime
4. ✅ **Immutability** - Configs frozen after loading
5. ✅ **Cross-Validation** - Dimensional consistency enforced

**Example:**
```python
# ❌ BAD: Hidden default
class VAEConfig:
    latent_dim: int = 16  # Hidden default!

# ✅ GOOD: Explicit required field
class VAEConfig:
    latent_dim: int = Field(
        ge=2, le=512,
        description="Latent space dimensionality"
    )
```

---

## File Structure

```
neocortex/
├── config/               # YAML configurations
├── logic/                # Business logic
│   ├── ingest/          # Data parsing (Phase 1)
│   ├── brain/           # ML core (Phase 2-3)
│   └── memory/          # Storage (Phase 1)
├── transport/            # Event adapters (Phase 4)
├── tests/                # Test suite
├── docs/                 # Documentation
│   └── PHASE_0_COMPLETION.md
├── PPO/                  # Original PPO library (to be integrated)
├── living_latent/       # Reference code (to be refactored)
├── domain.yaml          # vFoundation contract
├── config_models.py     # Pydantic schemas
├── main.py              # Entry point
├── JOURNAL_neocortex.md # Development journal
└── README.md            # This file
```

---

## Key Metrics (Phase 0)

- **Test Coverage:** 9/9 (100%)
- **Startup Time:** < 0.3s
- **Config Validation:** < 0.1s
- **Lines of Code:** ~900 (production foundation)

---

## References

- **Journal:** `JOURNAL_neocortex.md` - Development log
- **Completion Report:** `docs/PHASE_0_COMPLETION.md`
- **Domain Contract:** `domain.yaml`
- **vFoundation Spec:** (Aurora architecture docs)

---

## Contact / Support

See `JOURNAL_neocortex.md` for development history and design decisions.

**Status:** Phase 0 Complete ✅  
**Next:** Phase 1 - Data Ingestion Pipeline
