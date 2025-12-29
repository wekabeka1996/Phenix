# AGGREGATOR OCO — CODE MAP (v1.0)

> **PHASE 0 — Inventory Only | NO behaviour changes**
>
> Created: 2025-01-XX | Author: Copilot
> Search strategy: `grep_search` for `bracket|OCO|STOP_MARKET|TAKE_PROFIT|closePosition|tp_sl`

---

## 0. PURPOSE

This document is a **complete inventory** of all production code locations that participate in:
- TP (Take Profit) calculation and placement
- SL (Stop Loss) calculation and placement
- Bracket orchestration (lifecycle, throttling, cancellation)
- Aggregated OCO logic

**Goal**: Before any refactoring, have a single source of truth for "where is the bracket logic?"

---

## 1. HIGH-LEVEL INDEX

| # | File | Lines | Purpose | Status |
|---|------|-------|---------|--------|
| 1 | `bracket_service.py` | 1–1343 | Pure computation: build state, evaluate invariants, produce BracketPlan | ✅ SSOT for logic |
| 2 | `bracket_aggregator.py` | 1–100 | TP/SL price calculation from position params | ✅ vfoundation |
| 3 | `runtime.py` | 1580–2130 | Bracket orchestration: throttle, call service, apply plan | ⚠️ Coupled |
| 4 | `executor_pool.py` | 295–400 | Non-blocking bracket execution via rate limiter | ✅ Clean |
| 5 | `symbol_executor.py` | 1–558 | Entry-only executor (NO bracket logic since Phase 3) | ✅ Decoupled |
| 6 | `binance_adapter.py` | 1183–1413, 1837–1852 | Exchange API: STOP_MARKET, TAKE_PROFIT_MARKET | ✅ Transport |
| 7 | `config.py` | 74–150 | AggregatedOcoConfig dataclass | ✅ Config |
| 8 | `brackets_config.py` | 1–120 | resolve_brackets_config(), ResolvedBrackets | ✅ Config |
| 9 | `manage_config.py` | ~200–280 | BracketsMetaConfig, aggregated_oco resolver | ✅ Config |
| 10 | `tp_sl_math.py` | 1–70 | Core math: compute_tpsl_levels() | ✅ Utils |

---

## 2. PER-FILE BREAKDOWN

### 2.1 bracket_service.py — Pure Computation Layer

**Path**: `shadow_execpos/bracket_service.py`
**Lines**: 1343 total

#### Data Models (L1–375)

```
L127-158:  @dataclass PositionView
           - symbol, side, qty, entry_price, unrealized_pnl
           - aggregated_bracket_levels: Optional[AggregatedBracketLevels]

L160-198:  @dataclass OrderView
           - symbol, order_id, client_order_id, side, type, stop_price, status
           - is_stop_market, is_take_profit_market (properties)

L200-218:  @dataclass BracketLeg
           - leg_type: "SL" | "TP"
           - target_price, current_order, status

L221-247:  @dataclass BracketSet
           - stop_loss: Optional[BracketLeg]
           - take_profit: Optional[BracketLeg]

L249-281:  @dataclass BracketState
           - symbol, position: Optional[PositionView]
           - orders: List[OrderView]
           - bracket_set: Optional[BracketSet]
           - flat: bool

L283-313:  @dataclass BracketAction
           - action: "PLACE_SL" | "PLACE_TP" | "CANCEL" | "ADJUST" | "NOOP"
           - order_id, target_price, leg_type, why

L315-355:  @dataclass BracketPlan
           - symbol
           - actions: List[BracketAction]
           - suppressed: bool
           - why: str

L358-375:  @dataclass BracketRulesConfig
           - sl_pct, tp_rr, trailing_enabled, price_tolerance_pct
```

#### BracketService Class (L378–end)

```
L378-413:  class BracketService:
           __init__(config, adapter, order_index)

L416-520:  build_state(symbol) -> BracketState
           - Fetches position from config.positions
           - Fetches orders from order_index by symbol
           - Identifies SL/TP legs from order types
           - Computes aggregated bracket levels if position exists

L523-620:  evaluate(state: BracketState) -> BracketPlan
           - Main invariant checker
           - If flat: return orphan cleanup plan
           - If missing SL: PLACE_SL action
           - If missing TP: PLACE_TP action
           - If price drift > tolerance: ADJUST action

L623-680:  plan_orphan_cleanup(state: BracketState) -> BracketPlan
           - For flat positions with lingering brackets
           - Generates CANCEL actions for all bracket orders

L683-750:  plan_reverse_cleanup(old_side, new_side, symbol) -> BracketPlan
           - When position flips direction
           - Cancel old-side brackets, wait for new state

L753-800:  _compute_target_prices(position: PositionView) -> tuple[float, float]
           - Calls bracket_aggregator.compute_aggregated_brackets()
           - Returns (sl_price, tp_price)

L862-930:  _compute_desired_levels(state, cfg) -> Dict[str, Decimal]
           - **Phase 7**: Delegates to `core_math.compute_desired_levels()` (thin wrapper)
           - No longer contains duplicate SL/TP formulas
           - Returns {"sl_price": Decimal, "tp_price": Decimal}

L803-850:  _find_existing_leg(orders, leg_type) -> Optional[OrderView]
           - Scans orders for STOP_MARKET (SL) or TAKE_PROFIT_MARKET (TP)

L853-900:  _check_price_drift(current_price, target_price) -> bool
           - Returns True if drift > price_tolerance_pct
```

---

### 2.2 bracket_aggregator.py — TP/SL Price Calculation

**Path**: `vfoundation/strategy/bracket_aggregator.py`
**Lines**: ~100

```
L1-20:     Imports: TpslParams, TpslLevels, compute_tpsl_levels from tp_sl_math

L22-36:    @dataclass AggregatedBracketLevels:
           - tp_price: Optional[float]
           - sl_price: Optional[float]
           - why: str

L39-73:    def compute_aggregated_brackets(
               entry_price: float,
               side: str,
               sl_pct: float,
               tp_rr: float,
           ) -> AggregatedBracketLevels:

           Logic:
           1. Create TpslParams(entry_price, sl_pct, tp_rr)
           2. Call compute_tpsl_levels(params, side)
           3. Round prices to tick_size precision
           4. Return AggregatedBracketLevels

L76-100:   Helper functions for price rounding
```

---

### 2.3 runtime.py — Bracket Orchestration

**Path**: `shadow_execpos/runtime.py`
**Lines**: ~2200 total, bracket-related: 1580–2130

#### Imports & Setup (L28–162)

```
L28-38:    from .bracket_service import (
               BracketService, BracketState, BracketPlan, BracketAction,
               PositionView, OrderView, BracketLeg, BracketSet,
           )

L87-101:   @dataclass BracketStatus:
           - last_evaluation_ts: float
           - last_plan: Optional[BracketPlan]
           - suppressed_until: float

           @dataclass BracketEvalContext:
           - symbol: str
           - trigger: str  # "TRADE_EXECUTED" | "TIMER" | "MANUAL"
           - position_snapshot: dict

L120-121:  BRACKET_THROTTLE_SEC = 2.0   # Min interval between evaluations
           BRACKET_SUPPRESSION_SEC = 10.0  # Post-error cooldown

L147-162:  self._bracket_service = BracketService(
               config=self._bracket_rules_config,
               adapter=self._adapter,
               order_index=self._order_index,
           )
           self._bracket_status: Dict[str, BracketStatus] = {}
           self._symbol_locks: Dict[str, threading.Lock] = {}  # Phase 5
```

#### Throttling State (L220–254)

```
L220-230:  _get_symbol_lock(symbol) -> threading.Lock
           - Creates per-symbol lock if not exists

L232-254:  _should_throttle_bracket(symbol) -> bool
           - Checks if last_evaluation_ts + throttle_sec > now
           - Returns True if should skip evaluation
```

#### Main Bracket Evaluation (L1580–1790)

```
L1588-1617:  _build_bracket_context(symbol, trigger) -> BracketEvalContext
             - Snapshots current position state
             - Used for logging/debugging

L1626-1680:  _evaluate_and_apply_brackets_for_symbol(symbol, trigger):
             Main flow:
             1. Acquire symbol lock
             2. Check throttle → skip if too soon
             3. Call _bracket_service.build_state(symbol)
             4. Call _bracket_service.evaluate(state)
             5. If plan.suppressed → log & exit
             6. Call _apply_bracket_plan(plan)
             7. Update _bracket_status[symbol]

L1683-1758:  _evaluate_brackets(symbols: List[str], trigger: str):
             - Entry point called from event handlers
             - Iterates symbols, calls _evaluate_and_apply_brackets_for_symbol
             - Handles exceptions per-symbol (non-blocking)

L1760-1790:  _cleanup_orphan_brackets_for_flat(symbol):
             - Called when position goes flat
             - Calls _bracket_service.plan_orphan_cleanup()
             - Applies resulting CANCEL actions
```

#### Reverse Cleanup (L1790–1890)

```
L1830-1890:  _handle_reverse_cleanup(symbol, old_side, new_side):
             - Called when position flips (LONG→SHORT or vice versa)
             - Calls _bracket_service.plan_reverse_cleanup()
             - Cancels old brackets
             - Waits for confirmation
             - Triggers fresh evaluation for new direction
```

#### Apply Bracket Plan (L1890–2130)

```
L1890-1950:  _apply_bracket_plan(plan: BracketPlan):
             Main execution loop:
             for action in plan.actions:
                 if action.action == "CANCEL":
                     → call adapter.cancel_order()
                 elif action.action == "PLACE_SL":
                     → call _place_stop_loss()
                 elif action.action == "PLACE_TP":
                     → call _place_take_profit()
                 elif action.action == "ADJUST":
                     → call _adjust_bracket_order()

L1953-2020:  _place_stop_loss(symbol, price, qty):
             - Calls adapter.place_stop_market_close_position(
                   symbol=symbol,
                   side=opposite_side,
                   stop_price=price,
                   closePosition=True,  # ← KEY FLAG
               )
             - Updates OrderIndex mirror

L2023-2090:  _place_take_profit(symbol, price, qty):
             - Calls adapter.place_take_profit_market_close_position(
                   symbol=symbol,
                   side=opposite_side,
                   stop_price=price,
                   closePosition=True,  # ← KEY FLAG
               )
             - Updates OrderIndex mirror

L2093-2130:  _adjust_bracket_order(action: BracketAction):
             - Cancel existing order
             - Place new order at updated price
             - Used for trailing or price drift corrections
```

---

### 2.4 executor_pool.py — Non-Blocking Execution

**Path**: `shadow_execpos/executor_pool.py`
**Lines**: ~420, bracket-related: 295–400

```
L295-350:  async def execute_bracket(
               symbol: str,
               action: BracketAction,
           ) -> ExecutionResult:

           Logic:
           1. Check rate_limiter.try_acquire(symbol)
           2. If rate limited → return retry_after_ms
           3. Route action to appropriate adapter method:
              - PLACE_SL → adapter.place_stop_market_close_position
              - PLACE_TP → adapter.place_take_profit_market_close_position
              - CANCEL → adapter.cancel_order
              - ADJUST → cancel + place
           4. Return ExecutionResult

L355-400:  async def execute_batch(
               actions: List[BracketAction],
           ) -> List[ExecutionResult]:

           Logic:
           1. Sort: CANCELs first, then PLACE_SL, then PLACE_TP
           2. Execute sequentially (preserve order for safety)
           3. Collect results
```

---

### 2.5 binance_adapter.py — Exchange Transport

**Path**: `adapters/binance_adapter.py`
**Lines**: ~2100, bracket-related: 1183–1413, 1837–1852

```
L1183-1230:  async def place_stop_market_close_position(
                 symbol: str,
                 side: str,
                 stop_price: str,
                 closePosition: bool = True,
             ) -> dict:

             Binance payload:
             {
                 "symbol": symbol,
                 "side": side,
                 "type": "STOP_MARKET",
                 "stopPrice": stop_price,
                 "closePosition": "true",  # String!
             }

L1250-1300:  async def place_take_profit_market_close_position(
                 symbol: str,
                 side: str,
                 stop_price: str,
                 closePosition: bool = True,
             ) -> dict:

             Binance payload:
             {
                 "symbol": symbol,
                 "side": side,
                 "type": "TAKE_PROFIT_MARKET",
                 "stopPrice": stop_price,
                 "closePosition": "true",
             }

L1310-1360:  _validate_bracket_params(symbol, side, stop_price):
             - Checks price precision
             - Validates side is opposite to position

L1363-1413:  _round_bracket_price(symbol, price) -> str:
             - Rounds to tickSize from exchangeInfo

L1837-1852:  _handle_bracket_error(error, context):
             - Logs bracket-specific errors
             - Returns structured error dict
```

---

### 2.6 Configuration Files

#### config.py (L74–150)

```
L74-95:    @dataclass AggregatedOcoConfig:
           - enabled: bool = True
           - sl_pct: float = 0.02  # 2%
           - tp_rr: float = 2.0    # Risk:Reward ratio
           - trailing_enabled: bool = False
           - trailing_step_pct: float = 0.005

L97-120:   Throttling params (Phase 5):
           - throttle_sec: float = 2.0
           - suppression_sec: float = 10.0
           - max_retries: int = 3

L122-150:  Validation methods:
           - validate_sl_pct()
           - validate_tp_rr()
```

#### brackets_config.py (L1–120)

```
L15-40:    @dataclass ResolvedBrackets:
           - sl_pct: float
           - tp_rr: float
           - enabled: bool
           - source: str  # "symbol" | "domain" | "global"

L43-90:    def resolve_brackets_config(
               symbol: str,
               domain_config: dict,
               global_config: dict,
           ) -> ResolvedBrackets:

           Priority: symbol → domain → global

L93-120:   Helper functions for config merging
```

#### manage_config.py (~L200–280)

```
L200-240:  @dataclass BracketsMetaConfig:
           - default_sl_pct: float
           - default_tp_rr: float
           - symbol_overrides: Dict[str, dict]

L243-280:  def get_aggregated_oco_config(symbol) -> AggregatedOcoConfig:
           - Resolves symbol-specific overrides
           - Falls back to domain defaults
```

---

### 2.7 tp_sl_math.py — Core Math

**Path**: `utils/tp_sl_math.py`
**Lines**: ~70

```
L5-20:     @dataclass TpslParams:
           - entry_price: float
           - sl_pct: float      # e.g., 0.02 for 2%
           - tp_rr: float       # e.g., 2.0 for 1:2 R:R

L22-35:    @dataclass TpslLevels:
           - tp_price: float
           - sl_price: float
           - risk_amount: float

L38-70:    def compute_tpsl_levels(
               params: TpslParams,
               side: str,  # "BUY" | "SELL"
           ) -> TpslLevels:

           For LONG (side=BUY):
             sl_price = entry_price * (1 - sl_pct)
             risk = entry_price - sl_price
             tp_price = entry_price + (risk * tp_rr)

           For SHORT (side=SELL):
             sl_price = entry_price * (1 + sl_pct)
             risk = sl_price - entry_price
             tp_price = entry_price - (risk * tp_rr)
```

---

## 3. DATA FLOW DIAGRAM

```
┌──────────────────────────────────────────────────────────────────┐
│                     EVENT TRIGGER                                 │
│  (TRADE_EXECUTED / TIMER / MANUAL)                               │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  runtime._evaluate_brackets(symbols, trigger)                    │
│  ├── Acquire symbol_lock                                         │
│  ├── Check throttle (2.0s)                                       │
│  └── Call bracket_service.build_state(symbol)                    │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  BracketService.build_state()                                    │
│  ├── Fetch position from config.positions                       │
│  ├── Fetch orders from order_index                               │
│  ├── Identify existing SL/TP legs                                │
│  └── compute_aggregated_brackets() for target prices             │
│       └── tp_sl_math.compute_tpsl_levels()                       │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  BracketService.evaluate(state) → BracketPlan                   │
│  ├── If flat → plan_orphan_cleanup()                            │
│  ├── If missing SL → PLACE_SL action                            │
│  ├── If missing TP → PLACE_TP action                            │
│  └── If price drift → ADJUST action                             │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  runtime._apply_bracket_plan(plan)                               │
│  └── For each action:                                            │
│       ├── CANCEL → adapter.cancel_order()                        │
│       ├── PLACE_SL → adapter.place_stop_market_close_position()  │
│       ├── PLACE_TP → adapter.place_take_profit_market_close_position()
│       └── ADJUST → cancel + re-place                             │
└────────────────────────┬─────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────┐
│  binance_adapter                                                 │
│  ├── STOP_MARKET with closePosition=true                        │
│  └── TAKE_PROFIT_MARKET with closePosition=true                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## 4. KNOWN ISSUES & GAPS

### 4.1 Fragmentation

| Issue | Location | Impact |
|-------|----------|--------|
| Bracket logic split across 3+ files | runtime.py, bracket_service.py, executor_pool.py | Hard to trace bugs |
| Config resolution in multiple places | config.py, brackets_config.py, manage_config.py | Inconsistent defaults |
| Math duplicated | tp_sl_math.py + bracket_aggregator.py | Potential drift |

### 4.2 Race Conditions (Potential)

| Issue | Location | Mitigation |
|-------|----------|------------|
| Symbol lock doesn't cover adapter calls | runtime._apply_bracket_plan | May cause double-placement |
| OrderIndex update after adapter call | runtime L2015–2020 | Brief inconsistency window |

### 4.3 Missing Functionality

| Feature | Status | Notes |
|---------|--------|-------|
| Multi-position aggregation | ❌ Not implemented | Each position gets own brackets |
| Trailing stop adjustment | ⚠️ Config only | Logic stub exists |
| OCO native order type | ❌ | Using separate STOP_MARKET + TAKE_PROFIT_MARKET |

### 4.4 Legacy Code

| File | Lines | Status |
|------|-------|--------|
| `SyncOrderExecutor` | DELETED in Phase 3 | ✅ Clean |
| `symbol_executor.py` bracket methods | REMOVED in Phase 3 | ✅ Clean |

---

## 5. QUESTIONS FOR NEXT PHASE

1. **Should BracketService own the execution?**
   Currently: runtime.py calls service.evaluate() then applies plan itself.
   Alternative: service.execute(plan) for better encapsulation.

2. **Should we use Binance OCO order type?**
   Current approach uses separate STOP_MARKET + TAKE_PROFIT_MARKET.
   Native OCO would be atomic but has different semantics.

3. **Per-position vs aggregated brackets?**
   Current: each position gets own SL/TP.
   Aggregated: single SL/TP for all positions in symbol (not implemented).

4. **Trailing stop implementation?**
   Config exists (`trailing_enabled`, `trailing_step_pct`).
   Logic is stubbed but not active.

---

## 6. SEARCH PATTERNS USED

```powershell
# Bracket service
grep -r "bracket|BracketService|BracketPlan" shadow_execpos/

# OCO config
grep -r "AggregatedOco|aggregated_oco" .

# Binance calls
grep -r "STOP_MARKET|TAKE_PROFIT_MARKET|closePosition" adapters/

# TP/SL math
grep -r "compute_tpsl|TpslParams|TpslLevels" .

# Throttling
grep -r "throttle|suppression|BRACKET_THROTTLE" .
```

---

## 7. CONTRACT FILES (Phase 1-3 → Phase 8)

| File | Purpose | Phase |
|------|---------|-------|
| `AGGREGATOR_OCO_CONTRACT.md` | Text contract: Purpose, Inputs/Outputs, Invariants | Phase 1 |
| `contracts.py` | Python dataclasses matching the contract | Phase 1+2 |
| `__init__.py` | Package exports for contract types | Phase 1 |
| `engine.py` | Contract entrypoint: `compute_bracket_plan()` + core planner | **Phase 3 → Phase 9** |
| `core_math.py` | Pure SL/TP math extraction: `compute_desired_levels()` | **Phase 6** |

### Phase 9: Engine Architecture (bracket_service retirement)

```
engine.py (Phase 9):
├── compute_bracket_plan(agg_input, cfg)      # Main entrypoint
│   └── _compute_bracket_plan_core()          # Core planner (NO bracket_service)
│       └── core_math.compute_desired_levels() # SL/TP calculation
│
├── compute_bracket_plan_from_views(...)      # Runtime adapter
│   ├── IF bracket_service provided:          # Legacy path (for test compat)
│   │   └── bracket_service.build_state + evaluate
│   └── IF bracket_service=None:              # Core path (future production)
│       └── _view_to_*_snapshot() → AggregatorInput → _compute_bracket_plan_core()
│
├── _view_to_position_snapshot()              # Phase 9: Legacy → Contract adapter
├── _view_to_order_snapshot()                 # Phase 9: Legacy → Contract adapter
│
├── _position_snapshot_to_view()              # TEST-ONLY: Contract → Legacy adapter
├── _order_snapshot_to_view()                 # TEST-ONLY: Contract → Legacy adapter
├── _classify_order_leg()                     # TEST-ONLY: Order classification
├── _build_bracket_set()                      # TEST-ONLY: Build bracket set
└── _build_bracket_state()                    # TEST-ONLY: Build bracket state
```

**Key change in Phase 9**:
- `compute_bracket_plan_from_views()` can now use core planner directly (when `bracket_service=None`)
- Added `_view_to_position_snapshot()` and `_view_to_order_snapshot()` adapters
- Removed `_get_bracket_service()` singleton
- Legacy adapters marked as DEPRECATED / TEST-ONLY

**Phase 10 TODO**: Refactor tests to mock input data, remove bracket_service from runtime call.

**Tests**:
- `tests/domains/execution_position/aggregator_oco/test_contracts_shape.py` — Contract shape tests (Phase 1)
- `tests/domains/execution_position/aggregator_oco/test_engine_shadow.py` — Engine shadow tests (Phase 3)
- `tests/domains/execution_position/aggregator_oco/test_core_math_golden.py` — Golden-master tests (Phase 6)

---

## 8. BEHAVIOR SPECIFICATION (Phase 5)

| File | Purpose | Phase |
|------|---------|-------|
| `AGGREGATOR_OCO_BEHAVIOR.md` | Behavior spec: Invariants INV-1..8, Scenario table A1..D4 | **Phase 5** |

**Tests**:
- `tests/domains/execution_position/aggregator_oco/test_engine_scenarios.py` — Scenario-based behavior tests (Phase 5)

### Test Coverage Summary

| Scenario | Description | Status |
|----------|-------------|--------|
| A1 | LONG, no orders → PLACE_SL + PLACE_TP | ✅ |
| A2 | SHORT, no orders → PLACE_SL + PLACE_TP | ✅ |
| B1 | Perfect brackets → NOOP | ✅ |
| B2 | Missing TP → PLACE_TP only | ✅ |
| B3 | Missing SL → PLACE_SL only | ✅ |
| C2 | Flat position → CANCEL orphans | ✅ |
| D3 | Duplicate SL → system handles | ✅ |
| INV-4 | LONG: SL < entry < TP | ✅ |
| INV-5 | SHORT: TP < entry < SL | ✅ |
| INV-6 | why field ≤ 80 chars | ✅ |
| Formula | Parametrized LONG/SHORT SL/TP | ✅ |

**Total**: 18 scenario tests + 47 contract tests + 10 shadow tests + **180 golden tests** = **255 tests**

---

## 9. PURE MATH MODULE (Phase 6)

### 9.1 core_math.py — Pure SL/TP Calculation

**Path**: `apps/reference/domains/execution_position/aggregator_oco/core_math.py`
**Lines**: ~250

```
L1-60:     Module docstring, imports (Decimal, dataclass, Optional)
           Side = Literal["LONG", "SHORT"]

L62-90:    @dataclass(frozen=True) DesiredLevels:
           - side: Side
           - entry_price: Decimal
           - sl_price: Decimal
           - tp_price: Decimal
           - sl_pct: Decimal
           - tp_rr: Decimal
           - why: str = "core_math_v1"

L93-115:   @dataclass(frozen=True) PriceConstraints:
           - tick_size: Optional[Decimal]
           - min_price: Optional[Decimal]
           - max_price: Optional[Decimal]

L118-200:  def compute_desired_levels(
               side: Side,
               entry_price: Decimal,
               sl_pct: Decimal,
               tp_rr: Decimal,
               constraints: Optional[PriceConstraints] = None,
           ) -> DesiredLevels:

           Logic:
           1. Input validation (side, entry_price > 0, sl_pct > 0, tp_rr > 0)
           2. For LONG:
              sl = entry × (1 - sl_pct)
              tp = entry × (1 + sl_pct × tp_rr)
           3. For SHORT:
              sl = entry × (1 + sl_pct)
              tp = entry × (1 - sl_pct × tp_rr)
           4. Apply rounding if constraints provided
           5. Return frozen DesiredLevels

L203-230:  def compute_desired_levels_from_position(
               position_side: Side,
               position_entry_price: Decimal,
               sl_pct: Decimal,
               tp_rr: Decimal,
               constraints: Optional[PriceConstraints] = None,
           ) -> DesiredLevels:

           Convenience wrapper for position-based input.

L233-250:  def verify_level_invariants(levels: DesiredLevels) -> bool:
           - For LONG: sl < entry < tp
           - For SHORT: tp < entry < sl
```

### 9.2 Golden-Master Tests

**Path**: `tests/domains/execution_position/aggregator_oco/test_core_math_golden.py`
**Lines**: ~400

**Test Structure**:
```
TestGoldenMasterBasic (3 tests):
  - test_long_basic_matches_legacy
  - test_short_basic_matches_legacy
  - test_btc_like_price_matches_legacy

test_long_grid_matches_legacy (80 parametrized):
  - entry_price × sl_pct × tp_rr combinations

test_short_grid_matches_legacy (80 parametrized):
  - entry_price × sl_pct × tp_rr combinations

TestInvariants (7 tests):
  - INV-4: LONG sl < entry < tp
  - INV-5: SHORT tp < entry < sl
  - INV-6: why field ≤ 80 chars

TestInputValidation (5 tests):
  - invalid side, zero/negative entry, zero sl_pct, zero tp_rr

TestRounding (2 tests):
  - tick_size rounding, no constraints

TestConvenienceFunctions (1 test):
  - compute_from_position matches direct

TestDataPreservation (2 tests):
  - inputs preserved, frozen immutability
```

---

## 10. PHASE 10 — bracket_service RETIREMENT

> **Status**: COMPLETE (2025-11-30)
>
> bracket_service is now **TEST-ONLY** — not used in production runtime.

### 10.1 Runtime Bracket Planning Path

```
ExecPosRuntimeV2._evaluate_brackets_impl()
         ↓
compute_bracket_plan_from_views(pos_view, order_views, cfg, symbol, side, rid)
         ↓ (ALWAYS core planner path)
engine._view_to_*_snapshot() → AggregatorInput → _compute_bracket_plan_core()
         ↓
core_math.compute_desired_levels() + core_math._compute_bracket_plan_impl()
         ↓
BracketPlan with actions: PLACE_SL, PLACE_TP, CANCEL_SL, etc.
```

### 10.2 bracket_service Usage (Tests-Only)

| File | Purpose | Status |
|------|---------|--------|
| `shadow_execpos/bracket_service.py` | Legacy computation (types, build_state, evaluate) | **DEPRECATED — test harness only** |
| `shadow_execpos/runtime.py` (L148) | Creates instance for cleanup methods only | ⚠️ Cleanup methods still use |
| `shadow_execpos/runtime.py` (L1797) | `plan_orphan_cleanup()` | ⚠️ Legacy cleanup |
| `shadow_execpos/runtime.py` (L1856) | `plan_reverse_cleanup()` | ⚠️ Legacy cleanup |
| `tests/**/test_bracket_*.py` | Test harness for mock state | ✅ Test-only |

### 10.3 Removed from Production

| Change | File | Line |
|--------|------|------|
| `bracket_service` param removed | `engine.py` | `compute_bracket_plan_from_views()` |
| Legacy path removed | `engine.py` | No more `bracket_service.build_state + evaluate` |
| Call site updated | `runtime.py` | L1680 — no `bracket_service=` param |

### 10.4 Feature Gaps (xfail tests)

| Config Option | Core Planner Behavior | Test Status |
|---------------|----------------------|-------------|
| `allow_unprotected_position=True` | Core always generates SL/TP | `@pytest.mark.xfail` |
| `recreate_missing_brackets=False` | Core always recreates | `@pytest.mark.xfail` |

### 10.5 Test Results After Phase 10

```
aggregator_oco:  245 passed ✅
shadow_execpos:  354 passed, 2 failed (logging), 4 xfailed ✅
```

---

## APPENDIX A: FILE CHECKSUMS

| File | Line Count | Last Modified |
|------|------------|---------------|
| bracket_service.py | 1343 | **Phase 10: TEST-ONLY** |
| bracket_aggregator.py | ~100 | v1 |
| runtime.py | ~2450 | **Phase 10** |
| executor_pool.py | ~420 | Phase 5 |
| binance_adapter.py | ~2100 | Phase 4 |
| tp_sl_math.py | ~70 | v1 |
| **contracts.py** | ~410 | **Phase 1+2** |
| **engine.py** | ~350 | **Phase 10** |
| **core_math.py** | ~250 | **Phase 6** |
| **AGGREGATOR_OCO_CONTRACT.md** | ~250 | **Phase 1** |
| **AGGREGATOR_OCO_BEHAVIOR.md** | ~350 | **Phase 10** |
| **test_engine_scenarios.py** | ~600 | **Phase 5** |
| **test_core_math_golden.py** | ~400 | **Phase 6** |

---

*End of CODE_MAP v1.3 (Phase 10)*

