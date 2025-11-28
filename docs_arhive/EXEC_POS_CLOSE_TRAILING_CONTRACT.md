# ExecPos Close / Trailing / Position Model Contract

**Scope:** Pure services (no runtime wiring yet).  
**Implements:** [EP-PORT-CLOSE-TRAILING-S1]

## Data Models

### PositionState
- `symbol: str`
- `qty: float` (signed; >0 long, <0 short)
- `avg_entry_price: float`
- `realized_pnl: float`
- `unrealized_pnl: float`
- `open_time: Optional[float]`
- `last_update_time: Optional[float]`
- `scale_in_count: int`
- `scale_out_count: int`
- `side (property)`: LONG/SHORT/FLAT

### TrailingState
- `activated: bool`
- `breakeven_hit: bool`
- `high_watermark: float` (long)
- `low_watermark: float` (short)
- `sl_price: Optional[float]`
- `last_update_time: Optional[float]`
- `status: str` (INACTIVE | ACTIVE | BREAKEVEN | EXIT_SIGNAL)

### TrailingConfig
- `trail_distance_bps: float` (default 100 bps)
- `activate_after_bps: float`
- `breakeven_rr: float` (multiples of trail distance)
- `hard_time_exit_sec: Optional[float]`

### CloseContext
- `reason: str` (MANUAL | FORCE_RISK | RULE_TRIGGER | TRAIL_HIT | TIME_EXIT)
- `requested_qty: Optional[float]`
- `price: Optional[float]`
- `timestamp: Optional[float]`

### CloseConfig
- `allow_partial: bool`
- `min_close_qty: float`

### CloseDecision
- `action: str` (CLOSE_FULL | CLOSE_PARTIAL | IGNORE | NOOP)
- `target_qty: float`
- `reason_code: str`
- `why: str`
- `timestamp: float`

### TrailingDecision
- `sl_price: Optional[float]`
- `trail_state: TrailingState`
- `reason_code: str`
- `why: str`
- `exit: bool`
- `timestamp: float`

## APIs

### PositionModel
- `apply_fill(state: PositionState, side: str, quantity: float, price: float, ts: Optional[float]) -> PositionState`
  - Open new position (sets avg_entry_price, open_time).
  - Scale-in adjusts `avg_entry_price` weighted by size.
  - Partial close updates `realized_pnl`, decrements qty, increments `scale_out_count`.
  - Flip closes old side (realized PnL) and re-anchors new entry at flip price.

### CloseFlowService
- `plan_close(position: PositionState, ctx: CloseContext, cfg: Optional[CloseConfig]) -> CloseDecision`
  - Returns NOOP if flat.
  - Returns IGNORE if requested qty below `min_close_qty`.
  - CLOSE_PARTIAL if `allow_partial` and requested_qty < abs(qty); else CLOSE_FULL.
  - Reason codes: FORCE_CLOSE, MANUAL_CLOSE, RULE_CLOSE, TRAIL_CLOSE, TIME_CLOSE, CLOSE (fallback), ALREADY_FLAT, BELOW_MIN_QTY.
   - **Runtime wiring:** ExecPosRuntimeV2 calls `plan_close` in `_handle_close_intent` and translates CLOSE_FULL/PARTIAL into `ExecutionService.close_position`. Decision errors default to NOOP/IGNORE + log.

### TrailingStopService
- `eval_trailing(position: PositionState, price: float, trail_state: TrailingState, cfg: TrailingConfig, now: Optional[float]) -> TrailingDecision`
  - Maintains high/low watermarks and trailing SL.
  - Breakeven: after `breakeven_rr * trail_distance_bps` move, SL >= entry (long) or <= entry (short).
  - Trail: SL follows watermark with `trail_distance_bps`.
  - Exit when price crosses trailing SL or when `hard_time_exit_sec` exceeded.
  - Deterministic and side-effect free.
   - **Runtime wiring:** ExecPosRuntimeV2 invokes `eval_trailing` after fills; decisions are logged/metrics only (no auto-exit yet).

## Non-Goals / Out of Scope
- No order placement/cancel; decisions are intents for upstream runtime.
- No WAL/exposure logging.
- No runtime configuration resolution; configs are passed in explicitly.
- Wiring status: PositionState, CloseFlowService, and TrailingStopService are invoked by `ExecPosRuntimeV2`; actions still limited to logging/close_position calls (no bracket/auto-exit wiring).
