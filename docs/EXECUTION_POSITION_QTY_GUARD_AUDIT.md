## 1. Overview

The `execution_position` domain drives lifecycle management for Binance Futures positions (open, manage, close) in aggregated-only mode, meaning entries/exits are emitted without inline TP/SL and protection is delegated to the Aggregated OCO layer (ManageFlowFSM + OrderGuardian + watchdog). Exposure sizing in this stack is constrained by the exposure guards (`max_equity_utilization_pct`, directional ratios, per-symbol caps) and the `qty_guard`, which normalizes reduce-only quantities before aggregated SL/TP orders are emitted. In practice, qty_guard sits next to aggregated bracket placement so it can reject amounts that violate the instrument profile (`min_qty`, `step_size`, `min_notional`), preventing “soft” orders (e.g., those that would round to zero). This document assembles the configuration, code, call sites, aggregated-only context, and runtime evidence needed for the architect to understand how position size and exposure flow from configuration to DEC/ORDER.

## 2. Конфігурація експозиції та плеча (risk + instruments)

- **PATH: config/domains/execution.yaml** – exposure defaults applied before any instrument-specific overrides:
  ```yaml
  exposure:
    max_equity_utilization_pct: 200.0      # allow up to 200% of equity (testnet)
    max_side_utilization_pct:
      long: 150.0
      short: 150.0
    max_directional_ratio: 3.0
    per_symbol_cap_pct: 8.0
    leverage_defaults:
      SOLUSDT: 125
      ETHUSDT: 125
      __default__: 125
  manage:
    mode: aggregated_only
    brackets:
      aggregated_oco:
        enabled: true
        aggregated_only_mode: true
        recalc_on_scale_in: true
        recalc_on_partial_close: true
        ttl_protect_new_bracket_ms: 3000
        allow_unprotected_position: false
        watchdog:
          enabled: true
          interval_sec: 5
          auto_heal_orphans: true
  ```
  These values feed ExposureGuard (`apps/reference/domains/execution_position/exposure_guard.py`) and lock aggregated-only behavior systemwide.

- **PATH: config/domains/risk.yaml** – soft limit profile shared across domains:
  ```yaml
  soft_limits:
    mode: "clip"
    clip_min_notional_usdt: 10.0
    directional_ratio_max: 3.0
    side_exposure_usdt: 600.0
    margin_exposure_usdt: 1100.0
  ```
  `directional_ratio_max` caps the ratio between the sum of long and short margin exposures (see `apps/reference/domains/execution_position/exposure_guard.py` lines ~30–150 and `soft_clip.py`).

- **PATH: config/instruments.yaml** – instrument-level caps for SOLUSDT / BNBUSDT:
  ```yaml
  instruments:
    SOLUSDT:
      precision:
        quantity: 2
        price: 2
      limits:
        min_notional: 10.0
        min_qty: 0.01
        step_size: 0.01
        max_position_size: 5.0
        max_leverage: 20
    BNBUSDT:
      precision:
        quantity: 2
        price: 2
      limits:
        min_notional: 10.0
        min_qty: 0.01
        step_size: 0.01
        max_position_size: 5.0
        max_leverage: 20
  ```
  `qty_guard` consults these per-symbol limits when normalizing aggregated SL/TP amounts.

- **PATH: config/overrides.yaml** – testnet overrides that lift leverage to 125:
  ```yaml
  symbols:
    SOLUSDT:
      limits:
        max_leverage: 125
    BNBUSDT:
      limits:
        max_leverage: 125
  ```
  This ensures the exposure guard sees 125× leverage for SOL and BNB while still respecting other caps.

## 3. Реалізація qty_guard (повний код)

PATH: apps/reference/domains/execution_position/qty_guard.py

```python
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from typing import Any, Callable, Dict, Optional

from apps.reference.config_symbols import resolve_instrument_profile

DEFAULT_STEP_SIZE = Decimal("0.000001")
DEFAULT_MIN_QTY = Decimal("0.000001")
DEFAULT_MIN_NOTIONAL = Decimal("5")


@dataclass(frozen=True)
class QtyGuardResult:
    """Outcome of a quantity guard evaluation."""

    allowed: bool
    normalized_qty: Optional[Decimal]
    raw_qty: Optional[Decimal]
    reason: Optional[str] = None
    metadata: Dict[str, str] = field(default_factory=dict)

    def qty_str(self) -> Optional[str]:
        """Return normalized quantity formatted for DEC payloads."""
        if self.normalized_qty is None:
            return None
        return format(self.normalized_qty.normalize(), "f")


class ExecutionQtyGuard:
    """Quantization guard that fail-closes unsafe DEC quantities."""

    def __init__(
        self,
        *,
        config: Any = None,
        instrument_lookup: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._config = config
        self._instrument_lookup = instrument_lookup
        self._profile_cache: Dict[str, Any] = {}

    def evaluate(
        self,
        *,
        symbol: str,
        qty: Any,
        price: Any | None = None,
    ) -> QtyGuardResult:
        """Validate and normalize a reduce-only quantity."""

        symbol_key = symbol.upper()
        raw_qty = self._to_decimal(qty, "qty")
        if raw_qty <= 0:
            return QtyGuardResult(
                allowed=False,
                normalized_qty=None,
                raw_qty=raw_qty,
                reason="non_positive_qty",
                metadata={"symbol": symbol_key, "raw_qty": str(raw_qty)},
            )

        profile = self._resolve_instrument_profile(symbol_key)
        step_size = self._extract_decimal(
            profile, "step_size", DEFAULT_STEP_SIZE)
        min_qty = self._extract_decimal(profile, "min_qty", DEFAULT_MIN_QTY)
        min_notional = self._extract_decimal(
            profile, "min_notional", DEFAULT_MIN_NOTIONAL
        )

        metadata = {
            "symbol": symbol_key,
            "raw_qty": self._decimal_to_str(raw_qty),
            "step_size": self._decimal_to_str(step_size),
            "min_qty": self._decimal_to_str(min_qty),
            "min_notional": self._decimal_to_str(min_notional),
            "profile_source": self._extract_str(profile, "source", "unknown"),
        }

        if raw_qty < min_qty:
            metadata["violation"] = "below_min_qty"
            return QtyGuardResult(
                allowed=False,
                normalized_qty=None,
                raw_qty=raw_qty,
                reason="below_min_qty",
                metadata=metadata,
            )

        normalized_qty = self._round_to_step(raw_qty, step_size)
        metadata["normalized_qty"] = self._decimal_to_str(normalized_qty)

        if normalized_qty <= 0:
            metadata["violation"] = "qty_rounds_to_zero"
            return QtyGuardResult(
                allowed=False,
                normalized_qty=None,
                raw_qty=raw_qty,
                reason="qty_rounds_to_zero",
                metadata=metadata,
            )

        if normalized_qty < min_qty:
            metadata["violation"] = "below_min_qty"
            return QtyGuardResult(
                allowed=False,
                normalized_qty=None,
                raw_qty=raw_qty,
                reason="below_min_qty",
                metadata=metadata,
            )

        price_dec = self._to_decimal(
            price, "price") if price is not None else None
        if price_dec is not None and price_dec > 0:
            metadata["price"] = self._decimal_to_str(price_dec)
            notional = normalized_qty * price_dec
            metadata["notional"] = self._decimal_to_str(notional)
            if notional < min_notional:
                metadata["violation"] = "below_min_notional"
                return QtyGuardResult(
                    allowed=False,
                    normalized_qty=None,
                    raw_qty=raw_qty,
                    reason="below_min_notional",
                    metadata=metadata,
                )

        return QtyGuardResult(
            allowed=True,
            normalized_qty=normalized_qty,
            raw_qty=raw_qty,
            metadata=metadata,
        )

    def invalidate(self, symbol: str) -> None:
        """Drop cached instrument metadata for symbol."""
        self._profile_cache.pop(symbol.upper(), None)

    def _resolve_instrument_profile(self, symbol: str) -> Any:
        if symbol in self._profile_cache:
            return self._profile_cache[symbol]

        profile = None
        if self._instrument_lookup:
            try:
                profile = self._instrument_lookup(symbol)
            except Exception:
                profile = None

        if profile is None and self._config is not None:
            try:
                profile = resolve_instrument_profile(self._config, symbol)
            except Exception:
                profile = None

        if profile is not None:
            self._profile_cache[symbol] = profile
        return profile

    @staticmethod
    def _round_to_step(qty: Decimal, step_size: Decimal) -> Decimal:
        if step_size <= 0:
            return qty
        steps = (qty / step_size).to_integral_value(rounding=ROUND_DOWN)
        return (steps * step_size).normalize()

    @staticmethod
    def _extract_decimal(source: Any, field: str, default: Decimal) -> Decimal:
        value = ExecutionQtyGuard._extract_value(source, field)
        if value is None:
            return default
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError, TypeError):
            return default

    @staticmethod
    def _extract_str(source: Any, field: str, default: str) -> str:
        value = ExecutionQtyGuard._extract_value(source, field)
        if value is None:
            return default
        return str(value)

    @staticmethod
    def _extract_value(source: Any, field: str) -> Any:
        if source is None:
            return None
        if isinstance(source, dict):
            return source.get(field)
        try:
            return getattr(source, field)
        except AttributeError:
            return None

    @staticmethod
    def _to_decimal(value: Any, field: str) -> Decimal:
        if value is None:
            raise ValueError(f"{field} cannot be None")
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str):
            try:
                return Decimal(value)
            except InvalidOperation as exc:
                raise ValueError(f"{field} must be numeric: {value}") from exc
        raise ValueError(f"Unsupported {field} type: {type(value).__name__}")

    @staticmethod
    def _decimal_to_str(value: Decimal) -> str:
        return format(value.normalize(), "f")
```

**Описание:** `ExecutionQtyGuard` exposes `evaluate(symbol, qty, price=None)` and returns `QtyGuardResult` with boolean `allowed`, normalized `Decimal` quantity and metadata (`step_size`, `min_qty`, optional reason). It rounds down to the symbol’s `step_size` and rejects:
* `qty <= 0`
* `qty < min_qty`
* `normalized_qty` rounds to zero
* `normalized_qty < min_qty` after rounding
* `notional < min_notional` when price is provided
When allowed, `qty_str()` yields the decimal string for DEC payloads. The guard caches instrument profiles resolved via `apps.reference.config_symbols.resolve_instrument_profile`.

## 4. Використання qty_guard у FSM / ExecPos

### 4.1. Імпорти qty_guard

- `apps/reference/domains/execution_position/fsm_manage.py` imports `ExecutionQtyGuard` at the module level so ManageFlowFSM can create a guard when none is injected:
  ```python
  from apps.reference.domains.execution_position.qty_guard import ExecutionQtyGuard
  ```
  No other modules import `ExecutionQtyGuard` in production code (tests instantiate it for harnesses).

### 4.2. Виклики qty_guard

- Call site `apps/reference/domains/execution_position/fsm_manage.py::_normalize_reduce_only_qty` (excerpt):
  ```python
  def _normalize_reduce_only_qty(...):
      if not getattr(self, "_aggregated_only_mode", False):
          return str(qty)
      if not getattr(self, "_qty_guard", None):
          return str(qty)

      qty_abs = abs(Decimal(str(qty)))
      guard_result = self._qty_guard.evaluate(
          symbol=symbol or "UNKNOWN",
          qty=qty_abs,
          price=price,
      )
      if not guard_result.allowed or not guard_result.qty_str():
          agg_oco_logger.warning("AGG_SL_SKIPPED_MIN_QTY", extra={...})
          return None
      return guard_result.qty_str()
  ```
*Stage:* after aggregated bracket levels are computed (`levels.sl_price`, `levels.tp_price`), but before emitting DEC for SL/TP. QtyGuard only runs when aggregated-only mode is active and a guard instance exists.
*Effect:* It normalizes the reduce-only quantity (`qty_abs`) by rounding down to the instrument’s `step_size`, checks `min_qty` and `min_notional` (via price) and rejects the DEC when the normalized qty would round to zero. When guard rejects, ManageFlowFSM logs `AGG_SL_SKIPPED_MIN_QTY` and `DEC:PLACE_ORDER` is skipped (no SL/TP for that iteration).

### 4.3. Порядок викликів: risk → sizing → qty_guard → DEC/ORDER

  1. `ExecPosFSM.handle(CMD:OPEN)` → `OpenFlowFSM` validates command and emits `DEC:OPEN`.
  2. `_execute_decision` performs exposure checks:
     * `ExposureGuard.can_open` uses `config/domains/execution.yaml` and `config/domains/risk.yaml` (see `apps/reference/domains/execution_position/exposure_guard.py`); logs like `CAN_OPEN_DEBUG` show notional/portfolios.
     * `DecisionMaking` and `_on_portfolio_state_updated` update internal state before ManageFlow sees fills.
  3. Entry fills arrive as `EVT:TRADE_EXECUTED` → ManageFlowFSM updates `position_qty`/entry price.
  4. Aggregated bracket calculation runs (`_compute_aggregated_brackets` → `levels`), then `qty_guard` normalizes the `qty` derived from `position_qty` before `_emit_place_order`.
  5. When guard allows, ManageFlow emits `DEC:PLACE_ORDER` for SL/TP (STOP_MARKET/LIMIT). ExecPosFSM executes those via `BinanceAdapter` (stop/tp calls with `reduceOnly/closePosition`).

Thus, `qty_guard` sits downstream of risk gating but upstream of DEC/ORDER, preventing DEC emission for fractional quantities while leaving exposure guard and decision-making unaffected.

## 5. Поведінка Aggregated OCO (короткий зріз)

- Aggregated-only mode is configured in `config/domains/execution.yaml` (`manage.mode=aggregated_only` and `brackets.aggregated_oco.aggregated_only_mode=true`). `ExecPosFSM` sets `_aggregated_only_mode` from the same config (see `apps/reference/domains/execution_position/fsm.py` lines 228–233), so both ExecPosFSM and ManageFlowFSM agree.
- In this mode:
  * inline TP/SL placement inside `_execute_decision` is skipped (`if self._aggregated_only_mode: return` at `apps/reference/domains/execution_position/fsm.py:3003`).
  * ManageFlowFSM’s `_place_brackets` routes only to `_place_brackets_aggregated`.
  * All protection is delivered via ManageFlowFSM + OrderGuardian `BracketSetMeta` state and the watchdog validator (`agg_oco_watchdog.py`).
- Aggregated OCO config also enforces `recalc_on_partial_close=true`, `allow_unprotected_position=false`, and TTL protection (`ttl_protect_new_bracket_ms=3000`).
- Watchdog invariants (`agg_oco_watchdog.py`) ensure:
  * `NO_SL_FOR_OPEN_POSITION`
  * `ORPHAN_SL_FOR_ZERO_POSITION`
  * `MULTIPLE_META_SETS`
  These invariants are logged as `AGG_OCO_WATCHDOG` warnings in `logs/aurora_core.log` (lines 895–910 and subsequent blocks). The watchdog auto-heals orphan SLs by calling `order_guardian.cleanup_orphans()` and `clear_bracket_set_for_position`.
- The code path `_convert_position_side` raises `AggregatedOcoError` if `position_side` is not BUY/SELL, logging `f"Unsupported position side for aggregated OCO: {self.position_side}"` in `apps/reference/domains/execution_position/fsm_manage.py` line 979, which surfaces when aggregated metadata lacks canonical LONG/SHORT.

## 6. Відомі рантайм-симптоми (з логів)

1. **BNBUSDT notional after exposure guard:**  
   Source: `logs/domain_execution_management.log` lines 101–111.  
   ```text
   2025-11-18 02:59:48,633 - ExposureGuard - CAN_OPEN_DEBUG: symbol=BNBUSDT, notional=226.85750 ... 
   2025-11-18 02:59:48,634 - ExposureGuard - 💧 MARGIN_BREAKDOWN for BNBUSDT: open_positions=3.92 ...
   2025-11-18 02:59:48,638 - ExecPosFSM - GUARD_PASSED ... qty=0.25 ...
   2025-11-18 02:59:49,620 - ExecPosFSM - ✅ MARKET entry placed: ... 'symbol': 'BNBUSDT', 'origQty': '0.25'
   ```
   *Takeaway:* Exposure guard allows 0.25 BNB (~$226) at 125× leverage by consulting `max_leverage` overrides, and ManageFlow uses that qty to emit aggregated SL/TP.

2. **AGG_OCO_WATCHDOG warnings:**  
   Source: `logs/aurora_core.log` around lines 895–910.  
   ```text
   2025-11-18 02:58:22,489 - ExecPosFSM - WARNING - AGG_OCO_WATCHDOG
   2025-11-18 02:58:23,340 - httpx - INFO - GET /fapi/v1/order?symbol=ETHUSDT...
   2025-11-18 02:58:28,123 - ExecPosFSM - WARNING - AGG_OCO_WATCHDOG
   2025-11-18 02:58:28,155 - httpx - INFO - GET /fapi/v1/order?symbol=ETHUSDT...
   ```
   *Takeaway:* Watchdog runs repeatedly while pulling open orders to validate SL coverage; every warning correlates with a REST `get_open_orders` cycle before auto-heal.

3. **Quantity round-to-zero failure:**  
   Source: `logs/domain_execution_management.log` top lines (22:57 UTC).  
   ```text
   2025-11-17 22:57:35,365 - ExecPosFSM - ERROR - DECISION_EXECUTION_FAILED
   ...
   ValueError: Quantity rounds to zero with stepSize
   2025-11-17 22:57:35,370 - ExecPosFSM - ERROR - ❌ Adapter failed to execute decision PLACE_ORDER for BTCUSDT: Quantity rounds to zero with stepSize
   ```
   *Takeaway:* The same failure arises inside `BinanceAdapter.quantize_quantity`. `qty_guard` would have rejected earlier if aggregated-only mode were active; this log exemplifies why the guard is necessary.

4. **Order clipping on SOLUSDT:**  
   Source: `logs/order_log_v1.jsonl` lines 12–15.  
   ```json
   {"event_type": "ORDER_CLIPPED", "symbol": "SOLUSDT", "original_notional": 231.6399, "clipped_notional": 231.6399, "reason": "DIRECTIONAL_RATIO"}
   {"event_type": "ORDER_PLACED", "symbol": "SOLUSDT", "order_id": "1419157428", "quantity": 1.77, "side": "SELL"}
   {"event_type": "ORDER_PLACED", "symbol": "SOLUSDT", "order_id": "1419157927", "quantity": 1.0, "side": "SELL"}
   ```
   *Takeaway:* Risk clips around 231 USD at the clipping stage, but aggregated order placements still go through with the residual quantity (1.77, later 1.0) that qty_guard and aggregated OCO will protect.

## 7. Підсумок для архітектора

- `ExecutionQtyGuard` is located in `apps/reference/domains/execution_position/qty_guard.py`; it only rounds **down** (ROUND_DOWN) and can only **remove** marginal decimals, never inflate qty.
- ManageFlowFSM invokes qty_guard during aggregated-only SL/TP placement (`_normalize_reduce_only_qty`), so any failed guard (below `min_qty` or `min_notional`) prevents `DEC:PLACE_ORDER`.
- Exposure guard (`ExposureGuard`) runs earlier in ExecPosFSM, clamping notional/ratio thresholds described in `config/domains/execution.yaml` and `config/domains/risk.yaml` before ManageFlow consumes fills.
- `qty_guard` sits **after** aggregated bracket calculation and **before** DEC emission, ensuring aggregated-only SL/TP orders respect instrument `step_size`.
- Aggregated-only configuration (`aggregated_only_mode=true`, `aggregated_oco.enabled=true`) enforces that inline TP/SL logic in ExecPosFSM is skipped (see `fsm.py:3003`) and all protection flows through ManageFlow + OrderGuardian.
- The watchdog (`agg_oco_watchdog.py`) repeatedly logs `AGG_OCO_WATCHDOG` warnings and auto-heals via `cleanup_orphans`; any missing SL triggers `ORPHAN_SL_FOR_ZERO_POSITION`.
- `OrderGuardian` keeps a single `BracketSetMeta` per `(symbol, side)` and logs registration events (`order_guardian.log`), so `qty_guard` never touches more than the current `position_qty`.
- `max_leverage` overrides (125× for SOL/BNB) plus `max_position_size` (5 SOL/BNB) explain how small quantities (1.77 SOL) can cascade into notional levels (`~231 USD`) before aggregated OCO guard filters them.
- `Quantity rounds to zero with stepSize` failures occur before aggregated guards, highlighting the importance of conservative `min_qty` / `step_size` enforcement at both adapter and guard layers.
- For new exposures (SOL ~1.77 at $130, BNB 0.25 at ~$907), all configuration elements (risk, execution, instrument) align to cap side/utilization while allowing aggregated-only OCO to manage SL/TP.
