# Phase R2 Addendum: Telemetry Logger

**Date:** 2026-01-11
**Author:** Antigravity AI
**Phase:** R2 (Advisor - Telemetry)

---

## Overview

Implemented centralized `TelemetryLogger` that dumps all Neocortex metrics
to `logs/neocortex_metrics.csv` for easy analysis in Excel/Pandas.

---

## Files Created

| File | Purpose |
|------|---------|
| `logic/telemetry.py` | TelemetryLogger class with CSV output |
| `tests/test_ppo_telemetry.py` | 16 tests for telemetry |

## Files Modified

| File | Changes |
|------|---------|
| `transport/adapter.py` | Added telemetry logging at key points |

---

## CSV Schema

**File:** `logs/neocortex_metrics.csv`

| Column | Description |
|--------|-------------|
| `timestamp` | Unix timestamp |
| `datetime` | Human-readable datetime |
| `step` | Logging step counter |
| `vae_loss` | VAE reconstruction loss |
| `vae_mse` | VAE MSE component |
| `vae_kld` | VAE KL divergence |
| `wm_loss` | World Model loss |
| `ppo_loss_pi` | PPO policy loss |
| `ppo_loss_v` | PPO value loss |
| `ppo_entropy` | Policy entropy |
| `buffer_size` | Episodic buffer size |
| `episodes_collected` | Episodes waiting for dream |
| `episodes_processed` | Episodes processed this step |
| `shadow_action` | Action index (0/1/2) |
| `shadow_action_name` | LONG/SHORT/FLAT |
| `shadow_confidence` | Action log probability |
| `shadow_value` | Value estimate |
| `last_reward` | Most recent episode reward |
| `last_pnl` | Most recent PnL |
| `cumulative_reward` | Running total reward |
| `graph_nodes` | CausalGraph node count |
| `graph_edges` | CausalGraph edge count |
| `samples_since_train` | Samples since last train |
| `total_train_steps` | Total training steps |

---

## Logging Points in Adapter

1. **Training Complete:**
   ```python
   self._telemetry.log_training(
       vae_loss=..., vae_mse=..., vae_kld=..., wm_loss=...
   )
   ```

2. **Shadow Intent Emitted:**
   ```python
   self._telemetry.log_shadow_intent(
       action=..., action_name=..., confidence=..., value=...
   )
   ```

3. **Episode Completed:**
   ```python
   self._telemetry.log_episode(reward=..., pnl=...)
   ```

4. **PPO Training Complete:**
   ```python
   self._telemetry.log_step({
       "ppo_loss_pi": ..., "ppo_loss_v": ..., "ppo_entropy": ...
   })
   ```

---

## Usage Example

### View in Pandas

```python
import pandas as pd

df = pd.read_csv("logs/neocortex_metrics.csv")

# Plot losses over time
df[['vae_loss', 'wm_loss']].plot()

# Check action distribution
df['shadow_action_name'].value_counts()

# See cumulative reward
df['cumulative_reward'].plot()
```

### View in Excel

1. Open `logs/neocortex_metrics.csv`
2. Select data range
3. Insert → Chart → Line chart
4. Track Brain Health visually

---

## Health Report

Call `get_health_report()` for console summary:

```
=== NEOCORTEX HEALTH REPORT ===
Total entries: 1000
Cumulative reward: 15.6789

--- Training Losses (avg) ---
  VAE: 6.5
  WM: 0.002
  PPO Policy: 0.05
  PPO Value: 0.10

--- Action Distribution ---
  LONG: 35.0%
  SHORT: 30.0%
  FLAT: 35.0%
===============================
```

---

## Test Results

```
tests/test_ppo_telemetry.py: 16 passed ✅

- TestTelemetryLogger (11 tests)
- TestTelemetrySingleton (1 test)
- TestPPOTelemetryIntegration (2 tests)
- TestCSVFormat (2 tests)
```

---

## Definition of Done ✅

- [x] PPO weights update (from previous step)
- [x] `logs/neocortex_metrics.csv` grows with real data
- [x] User can open CSV in Excel/Pandas
- [x] CSV format is standard
- [x] Missing metrics handled (empty string, not NaN)
