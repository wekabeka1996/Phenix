# TIMER-FORENSIC-001: Reentry/Flip Timers Audit

**Date:** 2026-01-11
**Investigator:** AntiGravity (Senior Forensic Analyst)
**Scope:** AuroraHandler & DecisionMaking Timer Logic

## 1. Timer Map

| Component | Timer/Cooldown | Source Config | Clock Source | Logic Location | Description |
|-----------|----------------|---------------|--------------|----------------|-------------|
| **AuroraHandler** | `min_duration_sec` | `aurora.holding_period.min_duration_sec` | `_monotonic()` | `_should_suppress_soft_exit` | Prevents exit/flip if position held < min duration. Regime-aware. |
| **AuroraHandler** | `reentry_cooldown_sec` | `aurora.decision.reentry_cooldown_sec` | `_monotonic()` | `on_features` (pre-entry check) | Strategy-internal check based on `state.last_exit_timestamp`. |
| **AuroraHandler** | `side_bias_window` | `aurora.decision.side_bias_window_sec` | `_monotonic()` | `_get_side_bias_state` | Sliding window for counting recent buy/sell intents. |
| **AuroraHandler** | `regime_inertia` | `aurora.decision.regime_inertia` | `_monotonic()` | `on_regime_detected` | Delays transition to "better" regime (Risk-On). |
| **DecisionMaking** | `reentry_cooldown` | `aurora.decision.reentry_cooldown_sec` | `time.monotonic()` | `_on_strategy_signal_gateway` | System-level check based on portfolio exit detection (`_last_exit_mono_ts`). |
| **DecisionMaking** | `qos_rate_limit` | `aurora.decision.qos` | `time.time()` | `_check_qos_gate` | Wall-clock window (60s) for max intents/min. |

## 2. Event Path & State Updates

### A. Entry Path
1. `EVT:STRATEGY_SIGNAL_PRODUCED` (Aurora) -> `AuroraHandler._track_entry` updates `state.entry_timestamp` (`monotonic`).
2. This timestamp is used by `_should_suppress_soft_exit` to enforce `min_duration_sec`.

### B. Exit Path (Strategy)
1. Neutral signal produced -> `AuroraHandler` detects `state.position_side` was set but now signal is empty.
2. Updates `state.last_exit_timestamp` (`monotonic`).
3. Clears `state.position_side`.
4. Subsequent entries checked against `time_since_exit < reentry_cooldown`.

### C. Exit Path (System/Portfolio)
1. `EVT:PORTFOLIO_STATE_UPDATED` -> `DecisionMaking.on_portfolio`.
2. Compares `prev_qty` vs `current_qty`.
3. If goes to 0 -> updates `self._last_exit_mono_ts[symbol]` (`time.monotonic()`).
4. `_on_strategy_signal_gateway` checks `time.monotonic() - last_exit_ts < cooldown`.

## 3. Conflict Analysis (Double Gating)

**Observation:** There are TWO reentry cooldowns:
1. `AuroraHandler` (Internal): Relies on strategy *thinking* it exited.
2. `DecisionMaking` (System): Relies on *portfolio* actually confirming exit.

**Pros:** Defense in depth. If strategy emits exit signal, it enters internal cooldown immediately. If stop-loss triggers (strategy didn't emit exit), System cooldown catches it after portfolio update.

**Cons:** Config `reentry_cooldown_sec` is applied in BOTH places independently. This is acceptable as long as they use the same monotonic clock source, which they do.

## 4. Regime-Aware Multipliers

Found in `AuroraHandler._get_time_multiplier`:
- Multiplies `min_duration_sec` and `reentry_cooldown_sec`.
- Uses `regime_effective` (result of inertia logic).
- Defaults to 1.0 if not configured.

## 5. Potential Issues / Test Plan

1. **Verify Regime Inertia:** Ensure `regime_effective` lags correctly behind `regime_raw` using monotonic time.
2. **Verify Multipliers:** Ensure regime multipliers are applied to holding period.
3. **Verify System Cooldown:** Ensure `DecisionMaking` cooldown works even if `AuroraHandler` state is desynced (e.g. after restart).

## 6. Testing Strategy

I will create deterministic tests injecting a mocked `monotonic` clock to verify:
- `I-REENTRY-01`
- `I-FLIP-01`
- `I-FLIP-02`

