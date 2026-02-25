# DEBUG: Phase 6 Regression Analysis

**Date:** 2026-01-18  
**Analyst:** Systems Analyst Agent  
**Status:** 🔴 ROOT CAUSE IDENTIFIED

---

## Executive Summary

The Neocortex system is printing **"PHASE 6 (UNIFIED WAL TAILING)"** instead of entering **Phase 7 (Multi-Source Ingestion)** because:

1. **`load_config()` never loads `replay.yaml`** - The function only loads `system.yaml`, `ingest.yaml`, and `neuro.yaml`
2. **`ReplayConfig` defaults to `enabled=False`** when not provided explicitly
3. **`main.py` only imports `WalTailer`** (Phase 6) and never imports `MultiTailer` (Phase 7)
4. **No conditional logic exists** in `main.py` to choose between Phase 6 and Phase 7

---

## 1. Configuration Analysis

### 1.1 `config/replay.yaml` (Phase 7 Config)

```yaml
# Neocortex Multi-Source Ingestion Configuration (Phase 7)

enabled: true

# Log paths (relative to project root)
features_dir: "logs/features"
orders_file: "logs/order_log_v1.jsonl"
core_log: "logs/aurora_core.log"

# Processing parameters
batch_size: 100
poll_interval: 0.1

# Symbols to monitor
symbols:
  - BTCUSDT
  - ETHUSDT
  - SOLUSDT
  - DOGEUSDT
  - XRPUSDT
```

✅ **`replay.yaml` has `enabled: true`** and is configured for Phase 7 multi-source ingestion.
✅ **File exists** at `apps/reference/domains/neocortex/config/replay.yaml`

### 1.2 `config_models.py::load_config()` (Lines 351-398)

```python
def load_config(config_dir: Path) -> NeocortexConfig:
    # Load individual YAML files (fail if missing)
    system_path = config_dir / "system.yaml"
    ingest_path = config_dir / "ingest.yaml"
    neuro_path = config_dir / "neuro.yaml"
    
    # ... file existence checks ...
    
    with open(system_path) as f:
        system_data = yaml.safe_load(f)
    with open(ingest_path) as f:
        ingest_data = yaml.safe_load(f)
    with open(neuro_path) as f:
        neuro_data = yaml.safe_load(f)
    
    # Pydantic validation (fail on extra fields, missing fields, type errors)
    return NeocortexConfig(
        system=system_data,
        ingest=ingest_data,
        neuro=neuro_data
        # ❌ 'replay' is NEVER passed!
    )
```

🔴 **BUG:** `load_config()` does NOT load `replay.yaml`  
🔴 **BUG:** `NeocortexConfig` is instantiated without `replay` parameter

### 1.3 `NeocortexConfig` Default for `replay` (Line 316-318)

```python
class NeocortexConfig(BaseModel):
    # ...
    replay: ReplayConfig = Field(
        default_factory=lambda: ReplayConfig(enabled=False),  # ← DEFAULT!
        description="Historical WAL replay settings"
    )
```

🔴 **RESULT:** When `replay` is not passed, `ReplayConfig(enabled=False)` is used.

---

## 2. `main.py` Logic Flow

### 2.1 Imports (Lines 17-21, 51)

```python
from logic.ingest.parser import FeatureParser
from logic.amygdala.valuation import ValuationEngine
from logic.memory.buffer import EpisodicBuffer
from logic.brain.bridge import BrainBridge
from transport.adapter import NeocortexAdapter

from logic.ingest.tailer import WalTailer   # ← Phase 6 import
# ❌ NO IMPORT: from logic.ingest.multi_tailer import MultiTailer
```

🔴 **BUG:** `MultiTailer` (Phase 7) is never imported.

### 2.2 `main_reactor()` Decision Logic (Lines 58-135)

```python
async def main_reactor(config: NeocortexConfig, logger: logging.Logger):
    """
    Main async event loop.
    Phase 6: Unified WAL Tailing (history + live).   # ← Docstring says "Phase 6"
    """
    # ... initialization ...
    
    logger.info("=" * 80)
    logger.info("NEOCORTEX DOMAIN - PHASE 6 (UNIFIED WAL TAILING)")  # ← Hardcoded!
    logger.info("=" * 80)
    
    # ... component initialization ...
    
    # 3. Start WAL Tailer (if enabled)
    if config.replay.enabled:
        logger.info("Starting WalTailer (Unified Mode)...")
        
        state_path = config.system.data_dir / "tailer_state.json"
        
        tailer = WalTailer(                    # ← Always uses WalTailer (Phase 6)
            config=config.replay,
            handler=adapter.handle_features,
            state_path=state_path,
            wal_dir=config.replay.wal_dir
        )
        tailer_task = asyncio.create_task(tailer.run())
        logger.info(f"✓ WalTailer started (Dir: {config.replay.wal_dir})")
    else:
        logger.info("WAL Tailing disabled")    # ← This is what prints!
    
    # 4. Main Loop
    logger.info("")
    logger.info("Phase 6: Pipeline Active. Unified Tailing Ready.")  # ← Hardcoded!
```

### Issues Found:

| Line | Issue | Impact |
|------|-------|--------|
| 69-70 | Hardcoded "Phase 6" log message | Misleading output |
| 116 | `config.replay.enabled` is `False` due to loading bug | Enters `else` branch |
| 121-127 | Always uses `WalTailer`, never `MultiTailer` | Phase 7 never activates |
| 129-130 | Prints "WAL Tailing disabled" | **This is what user sees!** |

---

## 3. Root Cause Summary

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ROOT CAUSE CHAIN                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. load_config() does NOT read replay.yaml                                  │
│                     ↓                                                        │
│ 2. NeocortexConfig.replay uses default: ReplayConfig(enabled=False)         │
│                     ↓                                                        │
│ 3. main_reactor(): config.replay.enabled == False                           │
│                     ↓                                                        │
│ 4. else branch executes: logger.info("WAL Tailing disabled")                │
│                     ↓                                                        │
│ 5. No tailer is started at all                                              │
│                     ↓                                                        │
│ 6. Even if enabled=True, code ONLY instantiates WalTailer (Phase 6)         │
│                     ↓                                                        │
│ 7. MultiTailer (Phase 7) is never imported or used                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Expected vs Actual Behavior

| Aspect | Expected (Phase 7) | Actual (Phase 6) |
|--------|-------------------|------------------|
| Config loaded | `replay.yaml` with `multi_source: true` | `replay.yaml` ignored |
| `config.replay.enabled` | `True` | `False` (default) |
| Tailer class | `MultiTailer` | `WalTailer` (if enabled) |
| Data sources | Features + Orders + Core | WAL files only |
| Log output | "PHASE 7 (MULTI-SOURCE INGESTION)" | "PHASE 6 (UNIFIED WAL TAILING)" |

---

## 5. Required Fixes (DO NOT APPLY - FOR REFERENCE ONLY)

### Fix 1: Update `load_config()` to load `replay.yaml`

```python
# In config_models.py::load_config()

def load_config(config_dir: Path) -> NeocortexConfig:
    # ... existing code ...
    
    # ADD: Load replay config (optional - don't fail if missing)
    replay_path = config_dir / "replay.yaml"
    replay_data = None
    if replay_path.exists():
        with open(replay_path) as f:
            replay_data = yaml.safe_load(f)
    
    return NeocortexConfig(
        system=system_data,
        ingest=ingest_data,
        neuro=neuro_data,
        replay=replay_data  # ADD THIS
    )
```

### Fix 2: Update `main.py` to use `MultiTailer` for Phase 7

```python
# In main.py

# Add import
from logic.ingest.multi_tailer import MultiTailer, MultiSourceConfig

# In main_reactor():
if config.replay.enabled:
    # Check if multi-source config is present (Phase 7 indicator)
    if hasattr(config.replay, 'features_dir'):
        # Phase 7: Multi-Source Ingestion
        logger.info("NEOCORTEX DOMAIN - PHASE 7 (MULTI-SOURCE INGESTION)")
        
        multi_config = MultiSourceConfig(
            enabled=True,
            features_dir=config.replay.features_dir,
            orders_file=config.replay.orders_file,
            core_log=config.replay.core_log,
            symbols=config.replay.symbols,
            batch_size=config.replay.batch_size,
            poll_interval=config.replay.poll_interval
        )
        
        tailer = MultiTailer(
            config=multi_config,
            feature_handler=adapter.handle_features,
            episode_handler=adapter.handle_episode,  # If exists
            state_path=config.system.data_dir / "multi_tailer_state.json"
        )
    else:
        # Phase 6: Legacy WAL Tailing
        tailer = WalTailer(...)
```

### Fix 3: Update `ReplayConfig` Pydantic Model

The current `ReplayConfig` (lines 267-301) is designed for **Phase 6** (WAL files) but `replay.yaml` has **Phase 7** fields (`features_dir`, `orders_file`, `core_log`, `symbols`).

These fields will be **REJECTED** by Pydantic's `extra='forbid'` unless added to the model.

---

## 6. Verification Command

Once fixes are applied, run:

```bash
cd /home/wekabeka/Музыка/Phenix/apps/reference/domains/neocortex
./venv/bin/python main.py
```

Expected output should now contain:
```
NEOCORTEX DOMAIN - PHASE 7 (MULTI-SOURCE INGESTION)
✓ MultiTailer started
  Features: logs/features
  Orders: logs/order_log_v1.jsonl
  Core: logs/aurora_core.log
```

---

## 7. Architecture Gap Analysis

```
Current State:
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   replay.yaml    │ ✗   │   load_config()  │     │    main.py       │
│ (Phase 7 config) │────▶│ (doesn't load)   │────▶│ (uses WalTailer) │
│ enabled: true    │     │                  │     │                  │
└──────────────────┘     └──────────────────┘     └──────────────────┘

Desired State:
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│   replay.yaml    │ ✓   │   load_config()  │     │    main.py       │
│ (Phase 7 config) │────▶│  (loads file)    │────▶│ (MultiTailer)    │
│ enabled: true    │     │  replay=data     │     │ Phase 7 active   │
└──────────────────┘     └──────────────────┘     └──────────────────┘
```

---

**END OF REPORT**
