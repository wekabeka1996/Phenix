# ExecPos Close & Trailing Analysis

**Purpose:** Capture legacy intent and current gaps to inform CloseFlowService / TrailingStopService / PositionModel designs.  
**Canonical runtime:** ExecPosRuntimeV2 (see `docs/EXEC_POS_V2_RUNTIME_SPEC.md`).

## Legacy Behaviors (source: fsm_close.py, fsm_manage trailing rules)
- Close reasons: manual intent, force/risk close, TP/SL hits, trailing hits, time-based exits.
- Close FSM states: `FLAT -> OPENED -> CLOSE_COND -> EMIT_DEC_CLOSE -> DONE/ERROR`.
- Trailing rules (_check_rules):
  - Trail activation after price moves in favor by configured distance.
  - Breakeven: move SL to entry after reward/risk threshold.
  - Time-stop: exit if position age exceeds threshold.
- Position model assumptions:
  - avg_entry_price maintained across scale-ins.
  - partial closes update realized PnL; flips re-anchor entry.

## V2 Gaps (from `EXEC_POS_V2_RUNTIME_SPEC.md`)
- `_handle_close_intent` is a thin adapter call; no close-flow semantics.
- No trailing/breakeven/time-stop logic.
- Position model sets entry only on first open; no averaging on scale-in/scale-out; no realized PnL.
- Watchdog detects bracket issues only; no auto-actions.

## Design Implications for New Services
- CloseFlowService: produce deterministic CLOSE_FULL / CLOSE_PARTIAL / NOOP decisions with reason codes; no side effects.
- TrailingStopService: maintain trail/breakeven/time-exit state; emit exit/SL move recommendations; no order placement.
- PositionModel: deterministic state transitions for fills (open, scale-in, partial close, flip) with avg price + realized PnL.

## Boundaries
- Services are runtime-agnostic and can be consumed by ExecPosRuntimeV2 later.
- No adapter/WAL/exposure calls inside these services.
- Deterministic given inputs (position, price ctx, config, state).
