# 🔍 Pydantic Migration - Quick Reference

**Document Type**: Developer Quick-Start Guide
**For**: Developers refactoring config access
**Status**: Ready

---

## 📍 Quick Navigation

- **Full Plan**: `docs/PYDANTIC_MIGRATION_PLAN.md` (comprehensive)
- **Checklist**: `docs/PYDANTIC_IMPLEMENTATION_CHECKLIST.md` (step-by-step)
- **This Doc**: Quick patterns & examples

---

## 🔄 Migration Pattern

### BEFORE (Dict-based, 677 places)
```python
# ❌ OLD PATTERN - Don't use anymore
config.get("trading", {}).get("decision", {}).get("kelly", {}).get("kelly_cap", 0.25)

# ❌ OLD PATTERN - Multiple .get() calls
bar_cfg = config.get("trading", {}).get("decision", {}).get("bar_gating", {})
em_cfg = config.get("execution", {}).get("manage", {}).get("emergency", {})
```

### AFTER (Pydantic typed, 677 → 0 patterns)
```python
# ✅ NEW PATTERN - Direct attribute access
config.trading.decision.kelly.kelly_cap  # Pydantic handles defaults

# ✅ NEW PATTERN - Clean and type-safe
bar_cfg = config.trading.decision.bar_gating or BarGatingConfig()
em_cfg = config.execution.manage.emergency if config.execution else {}

# ✅ WITH TYPE HINTS (bonus: IDE autocomplete!)
bar_cfg: Optional[BarGatingConfig] = config.trading.decision.bar_gating
```

---

## 📚 Config Structure (Type Map)

```
config: AuroraConfig
├── trading_mode: str ∈ {testnet, production, live}
├── trading: TradingConfig
│   ├── mode: str
│   ├── decision: DecisionConfig
│   │   ├── signal_threshold: float
│   │   ├── signal_weights: SignalWeights
│   │   ├── signals: SignalsConfig
│   │   ├── position_sizing: PositionSizingConfig
│   │   ├── kelly: KellyConfig (kelly_cap, kelly_alpha, ...)
│   │   ├── qos: QosConfig
│   │   ├── bar_gating: Optional[BarGatingConfig]
│   │   ├── behavior_fsm: Optional[BehaviorFsmConfig]
│   │   ├── sizing_modifiers: Dict[str, float]
│   │   └── regime_thresholds: Dict[str, float]
│   ├── execution: ExecutionConfig
│   │   ├── manage: ManageConfig
│   │   │   ├── brackets: Optional[BracketsConfig]
│   │   │   │   ├── sl: Optional[SLConfig]  # fixed_bps
│   │   │   │   ├── tp: Optional[TPConfig]  # fixed_bps
│   │   │   │   └── oco_emulation: bool
│   │   │   ├── emergency: Dict[str, Any]
│   │   │   └── auto: bool
│   │   ├── exposure: ExposureConfig
│   │   │   ├── max_equity_utilization_pct: float (0-1.0)
│   │   │   ├── max_portfolio_fraction: float (0-1.0)
│   │   │   ├── max_side_utilization_pct: Dict[str, float]
│   │   │   ├── leverage_defaults: Dict[str, int]
│   │   │   └── ... (more fields)
│   │   └── watchdog: Dict[str, Any]
│   ├── instruments: Dict[str, InstrumentSpec]
│   │   └── BTCUSDT: InstrumentSpec
│   │       ├── symbol: str
│   │       ├── step_size: str
│   │       ├── tick_size: str
│   │       ├── min_qty: str
│   │       └── min_notional: str
│   ├── market_data: MarketDataConfig
│   │   ├── poll_interval_sec: int
│   │   ├── websocket_streams: List[str]
│   │   └── macro_sync: MacroSyncConfig
│   └── feature_engineering: FeatureEngineeringConfig
├── binance_api: BinanceApiConfig
│   ├── live: BinanceApiEnv (api_key, api_secret, rest_url, ws_url)
│   └── testnet: BinanceApiEnv
├── account_observer: AccountObserverConfig
├── system: SystemConfig
│   └── logging: LoggingConfig
└── ops: OpsConfig
```

---

## 🎯 Common Refactoring Tasks

### Task 1: Access Kelly Configuration
```python
# BEFORE
kelly_cap = config.get("trading", {}).get("decision", {}).get("kelly", {}).get("kelly_cap", 0.25)
kelly_alpha = config.get("trading", {}).get("decision", {}).get("kelly", {}).get("kelly_alpha", 0.8)

# AFTER
kelly_config = config.trading.decision.kelly
kelly_cap = kelly_config.kelly_cap  # Type: float
kelly_alpha = kelly_config.kelly_alpha  # Type: float
```

### Task 2: Access Brackets Configuration
```python
# BEFORE
sl_bps = config.get("trading", {}).get("execution", {}).get("manage", {}).get("brackets", {}).get("sl", {}).get("fixed_bps", 50)
tp_bps = config.get("trading", {}).get("execution", {}).get("manage", {}).get("brackets", {}).get("tp", {}).get("fixed_bps", 100)

# AFTER
brackets = config.trading.execution.manage.brackets
if brackets:
    sl_bps = brackets.sl.fixed_bps if brackets.sl else 50  # Type: int
    tp_bps = brackets.tp.fixed_bps if brackets.tp else 100  # Type: int
else:
    sl_bps = tp_bps = None
```

### Task 3: Access Exposure Configuration
```python
# BEFORE
max_equity = float(config.get("trading", {}).get("execution", {}).get("exposure", {}).get("max_equity_utilization_pct", "0.20"))
max_side_long = float(config.get("trading", {}).get("execution", {}).get("exposure", {}).get("max_side_utilization_pct", {}).get("long", "0.12"))

# AFTER
exposure = config.trading.execution.exposure
max_equity = exposure.max_equity_utilization_pct  # Type: float
max_side_long = exposure.max_side_utilization_pct.get("long", 0.12)  # Type: float
```

### Task 4: Access Instrument Specifications
```python
# BEFORE
instruments = config.get("trading", {}).get("instruments", {})
btc_spec = instruments.get("BTCUSDT", {})
step_size = btc_spec.get("step_size", "0.001")

# AFTER
btc_spec = config.trading.instruments.get("BTCUSDT")  # Type: InstrumentSpec | None
if btc_spec:
    step_size = btc_spec.step_size  # Type: str
else:
    step_size = "0.001"
```

### Task 5: Conditional Config Access
```python
# BEFORE
emergency = config.get("execution", {}) if isinstance(config.get("execution", {}), dict) else {}
em_cfg = emergency.get("manage", {}) if isinstance(emergency, dict) else {}

# AFTER
em_cfg = config.execution.manage.emergency if config.execution and config.execution.manage else {}

# Or more safely:
try:
    em_cfg = config.execution.manage.emergency
except AttributeError:
    em_cfg = {}
```

---

## ⚠️ Common Mistakes (Don't Do This!)

### ❌ Mistake 1: Chaining .get() with Pydantic
```python
# WRONG - Pydantic models don't have nested dicts
config.trading.decision.get("kelly", {}).get("kelly_cap")

# RIGHT - Direct attribute access
config.trading.decision.kelly.kelly_cap
```

### ❌ Mistake 2: Forgetting Optional Fields
```python
# WRONG - Might raise AttributeError if bar_gating is None
bar_cfg = config.trading.decision.bar_gating
enable = bar_cfg.enable

# RIGHT - Check for None first
bar_cfg = config.trading.decision.bar_gating
enable = bar_cfg.enable if bar_cfg else False
```

### ❌ Mistake 3: Not Using Type Hints
```python
# WRONG - IDE can't help you
def calculate_kelly(config):
    return config.trading.decision.kelly.kelly_cap * 2

# RIGHT - Type hints enable autocomplete
def calculate_kelly(config: AuroraConfig) -> float:
    kelly_cfg = config.trading.decision.kelly
    return kelly_cfg.kelly_cap * 2
```

### ❌ Mistake 4: Mixed Access Patterns
```python
# WRONG - Mixes old and new patterns (confusing!)
kelly_cap = config.get("trading", {}).get("decision", {}).kelly.kelly_cap

# RIGHT - Use only new pattern
kelly_cap = config.trading.decision.kelly.kelly_cap
```

---

## 🧪 Testing Your Refactor

### Test 1: Config Loads Without Error
```bash
python -c "
from apps.reference.config_loader import get_config
config = get_config()
assert config.trading.mode in ('testnet', 'production', 'live')
print('✅ Config loads correctly')
"
```

### Test 2: Type Hints Work
```python
from apps.reference.config_models import AuroraConfig
from apps.reference.config_loader import get_config

config: AuroraConfig = get_config()
# Now VS Code shows autocomplete for:
# config.trading.decision.kelly.kelly_cap
# ^ Type: float
```

### Test 3: Values Are Correct
```bash
# After refactoring a file, run its tests:
pytest tests/domains/test_execution_position_fsm_manage.py -xvs

# Should pass 100%
```

### Test 4: No New .get() Calls
```bash
# After refactoring a file, check for new .get() patterns:
grep "\.get(" apps/reference/domains/execution_position/fsm_manage.py

# Should only see:
# - vfoundation library code
# - Pydantic internal calls
# - Legitimate dict.get() on non-config objects
```

---

## 🎓 Understanding the Type System

### Type Annotations Explained
```python
# Optional field (can be None)
kelly: Optional[KellyConfig] = None

# Required field
mode: str = "testnet"

# Field with default
signal_threshold: float = Field(default=0.2)

# Dictionary field
instruments: Dict[str, InstrumentSpec] = Field(default_factory=dict)

# List field
anchors: List[str] = Field(default_factory=list)
```

### Type Checking with Type Hints
```python
# ✅ Type-safe (IDE knows kelly_cap is float)
def calculate(config: AuroraConfig) -> float:
    return config.trading.decision.kelly.kelly_cap * 2.0

# ❌ Not type-safe (IDE doesn't know the type)
def calculate(config):
    return config.get("trading", {}).get("decision", {}).get("kelly", {}).get("kelly_cap", 0.25) * 2.0
```

---

## 🚀 Refactoring Workflow

### Step 1: Understand Current Pattern
```python
# Find .get() chains in the file
grep "\.get(" apps/reference/domains/execution_position/fsm_manage.py | head -20
```

### Step 2: Map to New Structure
```
OLD: config.get("trading", {}).get("decision", {}).get("kelly", {}).get("kelly_cap", 0.25)
NEW: config.trading.decision.kelly.kelly_cap

Type Chain:
config (AuroraConfig)
  .trading (TradingConfig)
    .decision (DecisionConfig)
      .kelly (KellyConfig)
        .kelly_cap (float)
```

### Step 3: Replace in Code
```python
# Use find-replace with care:
# Find: config\.get\("trading",\s*\{\}\)\.get\("decision",\s*\{\}\)\.get\("kelly",\s*\{\}\)\.get\("kelly_cap",\s*[0-9.]+\)
# Replace: config.trading.decision.kelly.kelly_cap

# Or do it manually to be safe
```

### Step 4: Add Type Hints
```python
def manage_order(self) -> None:
    kelly_cfg: Optional[KellyConfig] = self.config.trading.decision.kelly
    if not kelly_cfg:
        return

    kelly_fraction = self._calculate_kelly(kelly_cfg.kelly_cap)
    # ...
```

### Step 5: Test
```bash
pytest tests/domains/test_execution_position_fsm_manage.py -xvs
# All green? ✅
# New .get() calls? ❌ Remove them!
```

### Step 6: Commit
```bash
git add apps/reference/domains/execution_position/fsm_manage.py
git commit -m "refactor(execution): migrate fsm_manage to typed config [FSMP-CFG-TIER1-A]"
```

---

## 🔧 Utility Commands

```bash
# Count .get() calls before refactor
grep -o "\.get(" apps/reference/domains/execution_position/fsm_manage.py | wc -l

# Find all .get() calls in a file
grep -n "\.get(" apps/reference/domains/execution_position/fsm_manage.py

# Find only config.get() (not legitimate dict.get())
grep -n "config\.get(" apps/reference/domains/execution_position/fsm_manage.py

# Verify no new .get() calls after refactor
git diff HEAD -- apps/reference/domains/execution_position/fsm_manage.py | grep "^+.*\.get("

# Check type hints
mypy --strict apps/reference/domains/execution_position/fsm_manage.py

# Run file tests
pytest tests/domains/test_execution_position_fsm_manage.py -xvs

# Full domain test
pytest tests/domains/ -xvs
```

---

## 📞 Need Help?

### Q: Where's the config structure documented?
**A**: See type map above, or look at `apps/reference/config_models.py`

### Q: How do I handle Optional fields?
**A**: Use `if field:` check or use `.or` operator:
```python
bar_cfg = config.trading.decision.bar_gating or BarGatingConfig()
```

### Q: Do I still need to support .get()?
**A**: **No!** Legacy `.get()` is only for backward compat during migration.
After migration complete, use direct attribute access only.

### Q: What if a field is None?
**A**: Check before accessing:
```python
if config.trading.execution:
    exposure = config.trading.execution.exposure
    max_eq = exposure.max_equity_utilization_pct
```

### Q: Performance impact?
**A**: Negligible (<5% overhead). Pydantic validation happens once at startup.

### Q: Rollback if something breaks?
**A**: Changes are backward compatible. Old `.get()` still works.
Just revert the commit: `git revert COMMIT_SHA`

---

## 🏁 Completion Indicators

**Refactoring done when**:
- [x] All `.get()` calls replaced with typed attributes
- [x] Type hints added to methods
- [x] All tests pass
- [x] No new `.get()` anti-patterns
- [x] IDE autocomplete works
- [x] Docstrings updated

---

**Last Updated**: 2025-11-06
**Status**: Ready for Developer Use
