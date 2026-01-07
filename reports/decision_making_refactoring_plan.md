# Decision Making Refactoring Plan — v7 (Final Corrected)

**Status**: Approved (Draft v7)  
**Date**: 2026-01-05

---

## Executive Summary

Decouple Aurora strategy logic from `decision_making.py` into a **Pure Scoring Kernel** and a **Stateful Handler**, promoting `DecisionMaking` to a **Generic Gateway**.

**Key Fixes in v7**:
- **Warmup Contract**: Gateway enforces `readiness` field in signal payload (Fail-Closed).
- **Flip Routing**: All strategies (Aurora + MR) retry flips via `EVT:STRATEGY_SIGNAL_PRODUCED`.
- **Config SSOT**: `legacy_tick_path_enabled` lives in `strategies.aurora` config section.

---

## 1. Scope & Architecture

### 1.1 Target Architecture

```
┌─────────────────────────────────────────────────────────┐
│              DecisionMaking (Generic Gateway)           │
│                                                         │
│  State:                                                 │
│   - QoS State: {strategy_id: {symbol: {counts...}}}     │
│   - Position State (Central SSOT)                       │
│                                                         │
│  ┌────────────────────────┐   ┌─────────────────────┐   │
│  │ _qos_allow(s, id, ...) │   │ _on_strategy_signal │   │
│  └───────────┬────────────┘   └──────────┬──────────┘   │
│              ▼                           │              │
│       [Dynamic Config]                   ▼              │
│    (strategies.<id>.*)         [Generic Gates & Sizing] │
│                                (Checks readiness=True)  │
│                                          ▼              │
│                            EVT:TRADE_INTENT_PROPOSED    │
└──────────────────────────────────────────▲──────────────┘
                                           │
┌─────────────────────────┐      ┌─────────────────────────┐
│     AuroraHandler       │      │       MRHandler         │
│ State:                  │      │                         │
│  - Regime/Warmup Cache  │      │                         │
│  - Side Bias State      │      │                         │
│            │            │      └─────────────────────────┘
│            ▼            │
│   AuroraScoringKernel   │
│  (Pure: f(feat, cfg))   │
│            │            │
│ EVT:STRATEGY_SIGNAL_... │
│  (readiness: ok=True)   │
└─────────────────────────┘
```

---

## 2. Implementation Phases

### Phase 0: Make Gateway Truly Generic
**Goal**: Remove "Aurora-first" assumptions and support partitioned QoS.

1.  **QoS Partitioning**:
    - Refactor `_qos_state` to `{strategy_id: {symbol: ...}}`.
    - Update `_qos_allow(symbol, strategy_id)` and helpers.
2.  **Generic Warmup Gate**:
    - **Change**: Gateway checks `payload.readiness.warmup_ok` (or similar field).
    - **Fail-Closed**: If field missing or False → REJECT ("STRATEGY_NOT_READY").
    - **Deprecate**: `_warmup_gate_before_trade_intent` usage of `_per_symbol_regimes`.

### Phase 1: Extract AuroraScoringKernel (Pure)
**Goal**: Logic extraction without side effects.

**Input**: `features`, `config`, `regime`, `side_bias_params`.
**Output**: `ScoringResult(score, side, thresholds, why_chain)`.

### Phase 2: Create AuroraHandler (Stateful)
**Location**: `domains/decision_making/aurora_handler.py`

**Responsibilities**:
1.  **State**:
    - Listen to `EVT:REGIME_DETECTED`, cache per-symbol `regime` and `warmup_state`.
    - Maintain `_side_bias_state`.
2.  **Emission**:
    - **Check Warmup**: Verify local cache `full_ready`.
    - **Exec Kernel**: Compute score.
    - **Emit**: `EVT:STRATEGY_SIGNAL_PRODUCED`.
      - **Field**: `readiness={"warmup_ok": True, "regime": ...}`.

### Phase 3: Shadow Mode (Internal)
**Config**: `strategies.aurora.shadow_mode.enabled`.

**Strategy**: Internal execution inside `_make_decision_for_symbol` (Legacy Path) to guarantee identical inputs.

### Phase 4: Wiring & Activation

**Config SSOT**: `strategies.aurora.legacy_tick_path_enabled` (Default: True).
Location: `config/aurora/strategies/aurora.yaml` under `aurora:`.

1.  **Wiring**: `aurora_builtin.py` returns real `AuroraHandler`.
2.  **Handler Logic**:
    ```python
    if self.config.strategies.aurora.legacy_tick_path_enabled:
        return  # Kill-switch active
    ```
3.  **Flip Retry Routing**:
    - **ALL Non-Aurora**: Use `original_event="EVT:STRATEGY_SIGNAL_PRODUCED"`.
    - **Aurora**:
      - If legacy enabled: `EVT:FEATURES_CALCULATED`.
      - If legacy disabled: `EVT:STRATEGY_SIGNAL_PRODUCED`.

### Phase 5: Cleanup
1.  Set `legacy_tick_path_enabled = False`.
2.  Delete Legacy methods/loops (`_make_decision_for_symbol`, trigger loops).

---

## 3. Signal Contract (Final Corrected)

**Event**: `EVT:STRATEGY_SIGNAL_PRODUCED`

| Field | Requirement | Reason |
| :--- | :--- | :--- |
| `symbol` | Required | Routing |
| `side` | Required | Direction |
| `ts_ms` | Required | Staleness |
| `strategy_id` | Required | QoS Partition |
| `price_ctx.entry_price` | Required | Sizing |
| `readiness.warmup_ok` | **Required** | Generic Warmup Gate |
| `signal_score` | Optional* | *Flip Hysteresis |
| `thr_buy/sell` | Optional* | *Flip Hysteresis |

---

## 4. Summary of Fixes (v7)

1.  **Warmup**: Gateway enforces `readiness.warmup_ok` in payload (Fail-Closed). Handler supplies it based on cached state.
2.  **Flip Routing**: Configurable event name for retries. Non-Aurora strategies always route to Gateway signal path.
3.  **Config SSOT**: `strategies.aurora.legacy_tick_path_enabled` defined in `aurora.yaml`.
4.  **QoS**: Partitioned by `strategy_id`.
