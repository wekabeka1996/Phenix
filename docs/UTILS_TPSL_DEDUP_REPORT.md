# UTILS-TPSL-DEDUP-S1 — TP/SL Math Unification Report

## 1. Overview
- Goal: unify TP/SL math (SL pct, RR, levels) into a single canonical module reused by brackets, trailing, and close flows to eliminate drift.
- Scope (Phase 0 & 1): inventory all TP/SL math sites and propose a canonical API. No code changes yet.

## 2. Existing TP/SL Implementations

### 2.1 bracket_aggregator.py (vfoundation/apps/reference/domains/execution_position/bracket_aggregator.py)
- **Role:** Computes aggregated TP/SL levels for a position (Aggregated OCO).
- **Formulas:**
  - Long: `sl_price = avg_entry * (1 - sl_pct)`, `tp_price = avg_entry * (1 + sl_pct * tp_rr)`
  - Short: `sl_price = avg_entry * (1 + sl_pct)`, `tp_price = avg_entry * (1 - sl_pct * tp_rr)`
  - Rounds to `tick_size` (Decimal quantize, ROUND_DOWN) and enforces `min_price`.
- **Inputs:** `avg_entry_price`, `position_amt`, `side`, `AggregatedOcoRiskConfig(sl_pct, tp_rr)`, `InstrumentPriceConstraints(tick_size, min_price)`.
- **Outputs:** `AggregatedBracketLevels(tp_price, sl_price, why)`.
- **Status:** **CANON_CANDIDATE** (most complete, already used by BracketService).

### 2.2 trailing.py (apps/reference/domains/execution_position/shadow_execpos/trailing.py)
- **Role:** Trailing/breakeven/time-exit logic; maintains trailing SL watermark.
- **Formulas (SL geometry):**
  - Trail distance in bps: `trail_distance = trail_distance_bps / 10000`.
  - Long: `candidate_sl = high_watermark * (1 - trail_distance)` (max against existing SL).
  - Short: `candidate_sl = low_watermark * (1 + trail_distance)` (min against existing SL).
  - Breakeven: when move_bps ≥ `breakeven_rr * trail_distance_bps` → `sl_price = entry_price`.
  - Time-exit: if `now - open_time >= hard_time_exit_sec` → exit signal.
- **Inputs:** PositionState (qty, avg_entry_price), price, trailing state (watermarks, SL), `TrailingConfig(trail_distance_bps, breakeven_rr, hard_time_exit_sec, activate_after_bps)`.
- **Outputs:** `TrailingDecision(sl_price, trail_state, reason_code, exit flag)`.
- **Status:** **DUPLICATE** for baseline SL geometry (recomputes trail SL separately from bracket_aggregator). Needs canonical SL computation for base levels but keeps trailing-specific logic.

### 2.3 close_flow.py (apps/reference/domains/execution_position/shadow_execpos/close_flow.py)
- **Role:** Plans CLOSE_FULL/CLOSE_PARTIAL decisions; no TP/SL math (uses qty/reason only).
- **Formulas:** None (no price math).
- **Status:** **LEGACY/SHIM** with respect to TP/SL math (not a math provider).

### 2.4 tp_sl_calculator.py (apps/reference/utils/tp_sl_calculator.py)
- **Role:** CLI utility for TP/SL; independent of runtime.
- **Formulas:**
  - Uses `sl_bps` (basis points) and ratios.
  - Long SL: `entry * (1 - sl_bps/10000)`, Short SL: `entry * (1 + sl_bps/10000)`.
  - TP: `tp_bps = sl_bps * tp_ratio`; Long TP: `entry + tp_bps/10000 * entry`, Short TP: `entry - tp_bps/10000 * entry`.
  - No tick_size/min_price handling.
- **Inputs:** entry_price (Decimal), sl_bps, side, tp ratios (low/high).
- **Outputs:** dict of SL/TP prices, distances, payoff ratios.
- **Status:** **LEGACY** (CLI-only, no rounding/constraints, duplicative formulas).

### 2.5 Other references
- Trailing/Close do not introduce additional TP/SL geometry beyond the above.
- BracketService consumes `bracket_aggregator` outputs; no extra math inside.

## 3. Canonical TP/SL API (Proposal)
```python
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Optional

@dataclass(frozen=True)
class TpslParams:
    side: Literal["LONG", "SHORT"]
    avg_entry_price: Decimal
    position_qty: Decimal
    sl_pct: Decimal   # fraction (0.01 = 1%)
    tp_rr: Decimal    # reward/risk multiplier for TP relative to SL distance

@dataclass(frozen=True)
class TpslConstraints:
    tick_size: Decimal
    min_price: Decimal

@dataclass(frozen=True)
class TpslLevels:
    sl_price: Decimal
    tp_price: Decimal
    why: str  # short XAI label (<= 80 chars)

def compute_tpsl_levels(params: TpslParams, constraints: TpslConstraints) -> TpslLevels:
    ...
```

- Math:
  - Long: `sl = entry * (1 - sl_pct)`, `tp = entry * (1 + sl_pct * tp_rr)`
  - Short: `sl = entry * (1 + sl_pct)`, `tp = entry * (1 - sl_pct * tp_rr)`
  - Apply tick_size rounding (ROUND_DOWN) and enforce min_price.
- Usage targets:
  - **BracketService / bracket_aggregator**: delegate TP/SL level calc to canonical API.
  - **TrailingStopService**: use canonical SL/TP baseline (initial geometry), retain trailing/breakeven/time-exit on top.
  - **CloseFlowService**: optional for target-based exits (if needed later).
- Validation / constraints:
  - `sl_pct > 0`, `tp_rr > 0`.
  - Symmetric LONG/SHORT handling.
  - Rounding via `tick_size`; clamp to `min_price`.

Status tags:
- `compute_tpsl_levels` = intended **CANON**.
- `bracket_aggregator` = to become thin wrapper around canonical API.
- `tp_sl_calculator` = **LEGACY** or wrapper to canonical API.
- `trailing.py` = should consume canonical baseline SL/TP but keep trail-specific adjustments.


## 4. Implementation Summary (Phase 2)
- New canonical module: pps/reference/utils/tp_sl_math.py with TpslParams/TpslConstraints/TpslLevels + compute_tpsl_levels (pure, Decimal math, tick_size/min_price rounding).
- foundation/apps/reference/domains/execution_position/bracket_aggregator.py delegates TP/SL levels to the canonical module while keeping its public API intact.
- pps/reference/domains/execution_position/shadow_execpos/trailing.py seeds baseline SL using compute_tpsl_levels (trailing/breakeven/time-stop logic unchanged).
- pps/reference/utils/tp_sl_calculator.py is now a CLI wrapper over the canonical math (no user-facing contract changes).

## 5. Testing (Phase 3)
- Added 	ests/apps/reference/utils/test_tp_sl_math.py covering LONG/SHORT geometry, rounding/min_price, invalid params.
- Regression suites:
  - pytest tests/domains/execution_position/shadow_execpos/test_bracket_service.py -q`n  - pytest tests/domains/execution_position/shadow_execpos -q`n  - pytest tests/domains/execution_position -q`n- Current status: 334 passed, 2 skipped on full EP suite.

## 6. Final State & Adoption (Phase 4)
- Canonical: pps/reference/utils/tp_sl_math.py (compute_tpsl_levels).
- Wrappers/Consumers: racket_aggregator, 	p_sl_calculator, baseline SL seeding in 	railing.py.
- Legacy/do-not-extend: any ad-hoc TP/SL formulas elsewhere; new code should call the canonical module.

