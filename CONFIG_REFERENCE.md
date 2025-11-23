# Configuration Reference

**QuantumTraderX Configuration Guide**

---

## Overview

This document provides a comprehensive reference for all configuration options in QuantumTraderX. The system uses YAML-based configuration with Pydantic validation to ensure type safety and correctness.

## Configuration Structure

```yaml
domains:
  execution:
    manage:
      brackets:
        aggregated_oco: {...}  # Position protection settings
    trailing: {...}            # Trailing stop configuration
    close: {...}               # Position close policies
```

---

## Execution Position Configuration

The `execution_position` domain controls position management, bracket orders (stop-loss, take-profit), trailing stops, and close policies. Configuration is validated via `ExecutionPositionConfig` (Pydantic).

### Configuration Profiles

QuantumTraderX provides three pre-configured risk profiles:

#### 🛡️ **Safe Profile** (Conservative)
- **File**: [`config/examples/execution_position_safe.yaml`](./config/examples/execution_position_safe.yaml)
- **Risk Level**: Low
- **Characteristics**:
  - Stop-Loss: **1.5%** (wider, more forgiving)
  - Take-Profit Risk-Reward: **1.5x** (conservative targets)
  - Trailing Distance: **80 bps** (tight trailing)
  - Max Legs: **1 SL / 1 TP** (no pyramiding)
  - Policy: **strict** (requires explicit reasons for closes)
  - Watchdog: **15s interval** (moderate monitoring)
- **Use Cases**:
  - Capital preservation strategies
  - Low-volatility markets
  - Learning phase / testing new strategies
  - Risk-averse traders

#### ⚖️ **Moderate Profile** (Balanced)
- **File**: [`config/examples/execution_position_moderate.yaml`](./config/examples/execution_position_moderate.yaml)
- **Risk Level**: Medium
- **Characteristics**:
  - Stop-Loss: **2.0%** (standard risk)
  - Take-Profit Risk-Reward: **2.0x** (balanced targets)
  - Trailing Distance: **100 bps** (moderate trailing)
  - Max Legs: **2 SL / 3 TP** (basic pyramiding)
  - Policy: **default** (standard close policies)
  - Watchdog: **10s interval** (active monitoring)
- **Use Cases**:
  - Standard production trading
  - Most cryptocurrency instruments
  - Balanced risk/reward scenarios
  - Default recommended profile

#### ⚡ **Aggressive Profile** (High-Risk)
- **File**: [`config/examples/execution_position_aggressive.yaml`](./config/examples/execution_position_aggressive.yaml)
- **Risk Level**: High
- **Characteristics**:
  - Stop-Loss: **1.0%** (tight, high precision required)
  - Take-Profit Risk-Reward: **3.0x** (ambitious targets)
  - Trailing Distance: **150 bps** (wide trailing)
  - Max Legs: **3 SL / 5 TP** (full pyramiding)
  - Policy: **permissive** (flexible close reasons)
  - Watchdog: **5s interval** (very tight monitoring)
  - Advanced: `recalc_on_partial_close: true` (dynamic bracket recalculation)
- **Use Cases**:
  - High conviction trades
  - Trending markets with strong momentum
  - Experienced traders with tight risk management
  - Scalping / intraday strategies

---

### Key Configuration Parameters

#### `aggregated_oco` (Bracket Orders)

Stop-Loss and Take-Profit configuration for position protection.

| Parameter | Type | Default | Constraint | Description |
|-----------|------|---------|------------|-------------|
| `sl_pct` | float | 0.02 | (0, 1.0) | Stop-Loss percentage (e.g., 0.02 = 2%) |
| `tp_rr` | float | 2.0 | [0.1, 100] | Take-Profit risk-reward ratio |
| `max_sl_legs` | int | 1 | >= 1 | Max stop-loss ladder legs |
| `max_tp_legs` | int | 1 | >= 1 | Max take-profit ladder legs |
| `recalc_on_scale_in` | bool | false | — | Recalculate brackets on scale-in |
| `recalc_on_partial_close` | bool | false | — | Recalculate brackets on partial TP |
| `allow_unprotected_position` | bool | false | — | Allow positions without brackets |
| `ttl_protect_new_bracket_ms` | int | 5000 | >= 0 | TTL for new bracket orders |

##### Watchdog Subsection

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `enabled` | bool | true | Enable watchdog monitoring |
| `interval_sec` | int | 10 | Check interval in seconds |
| `grace.enabled` | bool | true | Enable grace period |
| `grace.period_sec` | float | 3.0 | Grace period before escalation |
| `grace.allow_kinds` | list[str] | [] | Allowed order kinds during grace |

#### `trailing` (Trailing Stop)

Dynamic stop-loss that follows price movement.

| Parameter | Type | Default | Constraint | Description |
|-----------|------|---------|------------|-------------|
| `trail_distance_bps` | float | 100.0 | >= 0 | Trailing distance in basis points |
| `activate_after_bps` | float | 0.0 | >= 0 | Profit threshold to activate trailing |
| `hard_time_exit_sec` | float | null | >= 0 (optional) | Max time before forced exit |

#### `close` (Position Close Policies)

Rules for closing positions.

| Parameter | Type | Default | Constraint | Description |
|-----------|------|---------|------------|-------------|
| `max_hold_time_sec` | int | 86400 | >= 0 | Max position hold time (default: 24h) |
| `reason_policy` | str | "default" | ["default", "strict", "permissive"] | Close reason validation policy |

---

### Using Example Profiles

#### Option 1: Direct Reference

Copy the desired profile to your main config:

```bash
cp config/examples/execution_position_moderate.yaml config/domains/execution.yaml
```

#### Option 2: Import (YAML Anchors)

Reference profiles via YAML anchors (if your config loader supports it):

```yaml
domains:
  execution: !include execution_position_moderate.yaml
```

#### Option 3: Override Specific Parameters

Start with a profile and override:

```yaml
domains:
  execution:
    manage:
      brackets:
        aggregated_oco:
          sl_pct: 0.015        # Override: tighter SL
          tp_rr: 2.5           # Override: higher RR
          # ... rest from safe.yaml
```

---

### Profile Comparison Table

| Metric | Safe | Moderate | Aggressive |
|--------|------|----------|------------|
| **Stop-Loss %** | 1.5% | 2.0% | 1.0% |
| **TP Risk-Reward** | 1.5x | 2.0x | 3.0x |
| **Trailing (bps)** | 80 | 100 | 150 |
| **Max SL Legs** | 1 | 2 | 3 |
| **Max TP Legs** | 1 | 3 | 5 |
| **Recalc on Close** | ❌ | ❌ | ✅ |
| **Watchdog Interval** | 15s | 10s | 5s |
| **Policy** | strict | default | permissive |
| **Risk Level** | Low | Medium | High |

---

## Validation and Type Safety

All configuration is validated at load time using **Pydantic 2.x**:

- ✅ **Type checking**: `sl_pct` must be `float`, `max_sl_legs` must be `int`
- ✅ **Range validation**: `sl_pct` in (0, 1.0), `tp_rr` in [0.1, 100]
- ✅ **Immutability**: Config objects are frozen (cannot be modified after creation)
- ✅ **Graceful degradation**: Invalid configs log warnings but don't crash the system

### Testing Your Config

Run roundtrip tests to validate custom configs:

```bash
pytest tests/config/test_execution_position_examples.py -v
```

Expected output:
```
16 passed in 1.41s  # All profiles load successfully
```

---

## Migration Guide

### From Legacy Config (v1)

Old path: `config.execution.manage.brackets.aggregated_oco`
New path: Same, but now validated via `ExecutionPositionConfig`

**No code changes required** – the new typed config layer is **additive-only** and backward-compatible.

### Runtime Adoption (Phase 3)

**Current Status**: Config loader builds `execution_position_cfg` field (Phase 2 ✅)
**Next Step**: Domain code (`bracket_service`, `order_guardian`) will consume typed config

---

## Troubleshooting

### Common Errors

#### ValidationError: `sl_pct must be > 0`
```yaml
# ❌ Invalid
aggregated_oco:
  sl_pct: 0  # Must be positive

# ✅ Valid
aggregated_oco:
  sl_pct: 0.015  # 1.5%
```

#### ValidationError: `tp_rr must be in [0.1, 100]`
```yaml
# ❌ Invalid
aggregated_oco:
  tp_rr: 0.05  # Too low (< 0.1)

# ✅ Valid
aggregated_oco:
  tp_rr: 1.5  # 1.5x risk-reward
```

#### ValidationError: `Invalid reason_policy`
```yaml
# ❌ Invalid
close:
  reason_policy: "custom"  # Not in allowed list

# ✅ Valid
close:
  reason_policy: "strict"  # Or "default", "permissive"
```

### Checking Loaded Config

Use FastAPI debug endpoints:

```bash
curl http://localhost:8000/debug/config | jq .execution_position_cfg
```

---

## Related Documentation

### Core Documentation
- **📋 Configuration Map**: [`docs/EXECUTION_POSITION_CONFIG_MAP.md`](./docs/EXECUTION_POSITION_CONFIG_MAP.md) — Complete config reference (sources, paths, migration)
- **Technical Spec**: [`docs/EP_CONFIG_SSOT_REPORT.md`](./docs/EP_CONFIG_SSOT_REPORT.md) — Implementation details
- **Pydantic Models**: [`apps/reference/domains/execution_position/config.py`](./apps/reference/domains/execution_position/config.py)
- **Resolver**: [`apps/reference/config/execution_position.py`](./apps/reference/config/execution_position.py)

### Examples & Tests
- **Example Configs**: [`config/examples/`](./config/examples/) — Safe/Moderate/Aggressive profiles
- **Tests**: [`tests/config/test_execution_position_*.py`](./tests/config/) — 48 test scenarios

---

## Support

For questions or issues:
- **Config Questions**: See [`docs/EXECUTION_POSITION_CONFIG_MAP.md`](./docs/EXECUTION_POSITION_CONFIG_MAP.md) (Section 4: Troubleshooting)
- **GitHub Issues**: [QuantumTraderX Issues](https://github.com/your-org/quantum-trader-x/issues)
- **Main Documentation**: [README.md](./README.md)
