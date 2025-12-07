# New Alpha & Aurora Optuna – Technical Appendix

**Мета:**  
Дати максимально конкретний технічний гайд по реалізації Roadmap (`NEW_ALPHA_OPTUNA_PROD_ROADMAP.md`):  
– які файли/модулі змінювати,  
– які скелети коду/патчі потрібні,  
– як протестувати (unit + інтеграційно) нову логіку.

> УВАГА: це **проєкт патчів**, а не готовий diff. Код нижче – скелети/приклади для розробника.

---

## 1. Phase 0 – Per-Instrument Config Architecture (BLOCKING)

### 1.1. `config/aurora/trading.yaml` – Пер-інструментні overrides для Aurora

**Завдання:**  
Додати секцію з пер-asset параметрами для Aurora Phase 3+ (ETH/XRP/BTC/SOL/DOGE), не ламаючи існуючу структуру.

**Скелет YAML (патч-фрагмент):**

```yaml
trading:
  # ... існуючі поля (mode, decision, symbols_to_track, instruments, risk, qos, sizing_modifiers, kelly, etc.)

  # NEW: Aurora Phase3+ per-instrument overrides
  aurora_instruments:
    ETHUSDT:
      weights:
        ema: 0.058
        volume: 0.241
        macro: 0.131
        liquidity: 0.341
        obi: 0.155
        tfi: 0.093
        volatility: 0.036
        depth_imbalance: 0.256
        delta_price: 0.253

      side_bias:
        penalty_factor: 0.9
        window_sec: 600
        target_ratio: 0.6

      regime_thresholds:
        high_volatility_multiplier: 1.3
        low_volatility_multiplier: 0.85
        trend_multiplier: 1.05

      regime_sizing:
        high_volatility_multiplier: 0.3
        low_volatility_multiplier: 1.9
        mean_reversion_multiplier: 0.8
        base_size_usd: 1000.0

      exit:
        sl_pct: 0.019
        max_hold_sec: 900

      take_profit:
        tp_low_ratio: 0.4
        tp_high_ratio: 1.4
        partial_exit_pct: 0.7

      trailing_stop:
        enabled: false
        activation_pct: 0.005
        distance_pct: 0.004

      execution:
        cooldown_sec: 15

    XRPUSDT:
      # Аналогічно, з параметрами з aurora_optimal_full_v1.yaml

    BTCUSDT:
      # Аналогічно, з параметрами з aurora_optimal_full_v1.yaml
```

> Для SOL/DOGE – за потреби, зчитуючи з `aurora_optimal_production_v1.yaml` або `aurora_phase3_production.yaml`.

---

### 1.2. `apps/reference/config_models.py` – Моделі для aurora_instruments

**Завдання:**  
Додати Pydantic-моделі для нової секції `trading.aurora_instruments` і, за потреби, оновити Root `AuroraConfig`.

**Скелет (патч-фрагмент):**

```python
from typing import Dict, Optional
from pydantic import BaseModel


class AuroraSideBiasConfig(BaseModel):
    penalty_factor: Optional[float] = None
    window_sec: Optional[int] = None
    target_ratio: Optional[float] = None


class AuroraRegimeThresholdsConfig(BaseModel):
    high_volatility_multiplier: Optional[float] = None
    low_volatility_multiplier: Optional[float] = None
    trend_multiplier: Optional[float] = None


class AuroraRegimeSizingConfig(BaseModel):
    high_volatility_multiplier: Optional[float] = None
    low_volatility_multiplier: Optional[float] = None
    mean_reversion_multiplier: Optional[float] = None
    base_size_usd: Optional[float] = None


class AuroraExitConfig(BaseModel):
    sl_pct: Optional[float] = None
    max_hold_sec: Optional[int] = None


class AuroraTakeProfitConfig(BaseModel):
    tp_low_ratio: Optional[float] = None
    tp_high_ratio: Optional[float] = None
    partial_exit_pct: Optional[float] = None


class AuroraTrailingStopConfig(BaseModel):
    enabled: Optional[bool] = None
    activation_pct: Optional[float] = None
    distance_pct: Optional[float] = None


class AuroraExecutionConfig(BaseModel):
    cooldown_sec: Optional[int] = None


class AuroraInstrumentConfig(BaseModel):
    weights: Optional[Dict[str, float]] = None
    side_bias: Optional[AuroraSideBiasConfig] = None
    regime_thresholds: Optional[AuroraRegimeThresholdsConfig] = None
    regime_sizing: Optional[AuroraRegimeSizingConfig] = None
    exit: Optional[AuroraExitConfig] = None
    take_profit: Optional[AuroraTakeProfitConfig] = None
    trailing_stop: Optional[AuroraTrailingStopConfig] = None
    execution: Optional[AuroraExecutionConfig] = None


class TradingConfig(BaseModel):
    # ... існуючі поля
    aurora_instruments: Dict[str, AuroraInstrumentConfig] = {}
```

> У реальному коді потрібно вбудувати це в існуючу модель `TradingConfig` (назва може відрізнятись в `config_models.py`).

---

### 1.3. `apps/reference/domains/decision_making/decision_making.py` – Хелпер для per-symbol config

**Завдання:**  
Додати внутрішній метод, що безпечно витягає `AuroraInstrumentConfig` для символу з config.

**Скелет:**

```python
class DecisionMaking:
    # ...

    def _get_aurora_instrument_cfg(self, symbol: str):
        """
        Get per-instrument Aurora config (aurora_instruments.<SYMBOL>),
        fallback to {} if not present.
        """
        try:
            trading_cfg = self._safe_config_get("trading", default={}) or {}
            # Pydantic: trading_cfg.aurora_instruments
            if hasattr(trading_cfg, "aurora_instruments"):
                return trading_cfg.aurora_instruments.get(symbol)
            # dict-based fallback
            if isinstance(trading_cfg, dict):
                return (trading_cfg.get("aurora_instruments") or {}).get(symbol)
        except Exception:
            return None
```

Цей хелпер буде використовуватись далі для:
- `_get_signal_weights(symbol)`
- `_get_side_bias_params(symbol)`
- `_get_regime_thresholds(symbol)`
- `_get_regime_sizing(symbol)`

---

## 2. Track A – Aurora Phase 3+ (Execution & Decision)

### 2.1. `fsm_manage.py` – Per-Asset SL/TP, Partial Exit, Max Hold, Trailing

#### 2.1.1. Хелпер для читання per-symbol exit/TP/trailing

**Скелет:**

```python
from typing import Optional, Tuple


class ManageFlowFSM:
    """
    PATCH: Додати в існуючий __init__:
    
    def __init__(self, ...):
        # ... existing code ...
        self.symbol: Optional[str] = None  # NEW: cached symbol for per-asset config
        self._trailing_peak_price: Optional[Decimal] = None  # NEW: for trailing stop
    """

    def _get_symbol(self, msg: Message) -> Optional[str]:
        """Extract symbol from message payload or stored state."""
        if self.symbol:
            return self.symbol
        try:
            pld = msg.pld or {}
            symbol = pld.get("symbol")
            if symbol:
                self.symbol = symbol
                return symbol
        except Exception:
            return None
        return None

    def _get_aurora_instr_cfg(self, symbol: str):
        """Mirror of DecisionMaking._get_aurora_instrument_cfg for FSM side."""
        try:
            trading_cfg = getattr(self.config, "trading", None) or {}
            if hasattr(trading_cfg, "aurora_instruments"):
                return trading_cfg.aurora_instruments.get(symbol)
            if isinstance(trading_cfg, dict):
                return (trading_cfg.get("aurora_instruments") or {}).get(symbol)
        except Exception:
            return None

    def _get_exit_params(self, symbol: str) -> Tuple[Optional[float], Optional[int]]:
        """
        Return (sl_pct, max_hold_sec) for symbol.
        Falls back to global bps-based SL if per-asset not configured.
        """
        instr_cfg = self._get_aurora_instr_cfg(symbol)
        sl_pct = None
        max_hold_sec = None
        if instr_cfg and getattr(instr_cfg, "exit", None):
            sl_pct = getattr(instr_cfg.exit, "sl_pct", None)
            max_hold_sec = getattr(instr_cfg.exit, "max_hold_sec", None)
        return sl_pct, max_hold_sec

    def _get_take_profit_params(self, symbol: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """
        Return (tp_low_ratio, tp_high_ratio, partial_exit_pct) for symbol.
        """
        instr_cfg = self._get_aurora_instr_cfg(symbol)
        if instr_cfg and getattr(instr_cfg, "take_profit", None):
            tp = instr_cfg.take_profit
            return tp.tp_low_ratio, tp.tp_high_ratio, tp.partial_exit_pct
        return None, None, None

    def _get_trailing_params(self, symbol: str):
        instr_cfg = self._get_aurora_instr_cfg(symbol)
        if instr_cfg and getattr(instr_cfg, "trailing_stop", None):
            ts = instr_cfg.trailing_stop
            return bool(ts.enabled), ts.activation_pct, ts.distance_pct
        return False, None, None
```

---

#### 2.1.2. `_calculate_bracket_prices` – Нова версія з SL% і TP1/TP2

**Ідея:**  
– якщо є per-asset `sl_pct` → використовувати його;  
– якщо є `tp_low_ratio/tp_high_ratio` → порахувати TP1/TP2;  
– інакше fallback на глобальні `fixed_bps`.

**Скелет:**

```python
class ManageFlowFSM:
    # ...

    def _calculate_bracket_prices(self) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """
        Calculate SL, TP1, TP2 prices for current position.
        Returns (sl_price, tp1_price, tp2_price).
        TP2 or TP1 may be None if not configured.
        """
        if self.position_entry_price is None or self.position_side is None:
            return None, None, None

        entry_price = self.position_entry_price
        symbol = getattr(self, "symbol", None)

        sl_pct, _ = (None, None)
        tp_low_ratio = tp_high_ratio = partial_exit_pct = None

        if symbol:
            sl_pct, _ = self._get_exit_params(symbol)
            tp_low_ratio, tp_high_ratio, partial_exit_pct = self._get_take_profit_params(symbol)

        # ---------- SL ----------
        if sl_pct is not None:
            sl_pct_dec = Decimal(str(sl_pct))
            if self.position_side == "BUY":
                sl_price = entry_price * (Decimal("1") - sl_pct_dec)
            else:
                sl_price = entry_price * (Decimal("1") + sl_pct_dec)
        else:
            # Fallback: existing bps-based SL from trading.execution.manage.brackets
            sl_price = self._calculate_sl_from_bps(entry_price)

        # ---------- TP1/TP2 ----------
        tp1_price = tp2_price = None
        if sl_pct is not None and tp_low_ratio is not None:
            risk_pct = Decimal(str(sl_pct))  # відстань до SL в %
            tp1_off = risk_pct * Decimal(str(tp_low_ratio))
            tp2_off = risk_pct * Decimal(str(tp_high_ratio)) if tp_high_ratio is not None else None

            if self.position_side == "BUY":
                tp1_price = entry_price * (Decimal("1") + tp1_off)
                if tp2_off is not None:
                    tp2_price = entry_price * (Decimal("1") + tp2_off)
            else:
                tp1_price = entry_price * (Decimal("1") - tp1_off)
                if tp2_off is not None:
                    tp2_price = entry_price * (Decimal("1") - tp2_off)
        else:
            # Fallback: single TP from bps
            tp1_price = self._calculate_tp_from_bps(entry_price)

        # Quantize by tick_size
        sl_price, tp1_price, tp2_price = self._quantize_prices(symbol, sl_price, tp1_price, tp2_price)
        return sl_price, tp1_price, tp2_price

    def _calculate_sl_from_bps(self, entry_price: Decimal) -> Optional[Decimal]:
        """
        Fallback: calculate SL using existing bps config.
        Reads from: trading.execution.manage.brackets.sl.fixed_bps
        """
        if not self._manage_cfg or not self._manage_cfg.brackets:
            return None
        brackets = self._manage_cfg.brackets
        sl_bps = 50  # default
        if brackets.sl and brackets.sl.fixed_bps:
            sl_bps = brackets.sl.fixed_bps
        elif brackets.stop_loss_bps:
            sl_bps = brackets.stop_loss_bps
        
        if self.position_side == "BUY":
            return entry_price * (1 - Decimal(str(sl_bps)) / 10000)
        else:
            return entry_price * (1 + Decimal(str(sl_bps)) / 10000)

    def _calculate_tp_from_bps(self, entry_price: Decimal) -> Optional[Decimal]:
        """
        Fallback: calculate TP using existing bps config.
        Reads from: trading.execution.manage.brackets.tp.fixed_bps
        """
        if not self._manage_cfg or not self._manage_cfg.brackets:
            return None
        brackets = self._manage_cfg.brackets
        tp_bps = 100  # default
        if brackets.tp and brackets.tp.fixed_bps:
            tp_bps = brackets.tp.fixed_bps
        
        if self.position_side == "BUY":
            return entry_price * (1 + Decimal(str(tp_bps)) / 10000)
        else:
            return entry_price * (1 - Decimal(str(tp_bps)) / 10000)

    def _quantize_prices(self, symbol: Optional[str], sl: Optional[Decimal], 
                         tp1: Optional[Decimal], tp2: Optional[Decimal]
    ) -> Tuple[Optional[Decimal], Optional[Decimal], Optional[Decimal]]:
        """Quantize prices to tick_size from instruments config."""
        if not symbol or not self.config.trading.instruments:
            return sl, tp1, tp2
        inst = self.config.trading.instruments.get(symbol)
        if not inst or not inst.tick_size:
            return sl, tp1, tp2
        try:
            tick = Decimal(str(inst.tick_size))
            if sl:
                sl = (sl / tick).quantize(Decimal('1')) * tick
            if tp1:
                tp1 = (tp1 / tick).quantize(Decimal('1')) * tick
            if tp2:
                tp2 = (tp2 / tick).quantize(Decimal('1')) * tick
        except Exception:
            pass
        return sl, tp1, tp2
```

> Потрібно буде адаптувати `_place_brackets` під трійку `SL/TP1/TP2` (див. наступний пункт).

---

#### 2.1.3. `_place_brackets` – постановка SL + TP1/TP2

**Скелет логіки:**

```python
class ManageFlowFSM:
    # ...

    def _place_brackets(self, msg: Message) -> Optional[Message]:
        # ... існуючі anti-race перевірки ...

        symbol = self._get_symbol(msg)
        sl_price, tp1_price, tp2_price = self._calculate_bracket_prices()
        if sl_price is None or tp1_price is None:
            self.state = ManageState.TRACKING
            return None

        self.sl_price = sl_price
        self.tp_price = tp1_price  # для back-compat (TP1 як основний)

        # Формуємо два TP ордери, якщо є tp2_price
        qty_full = self.position_qty or Decimal("0")
        tp1_qty = qty_full
        tp2_qty = None

        tp_low_ratio, tp_high_ratio, partial_exit_pct = (None, None, None)
        if symbol:
            _, tp_low_ratio, partial_exit_pct = self._get_take_profit_params(symbol)

        if partial_exit_pct is not None and tp2_price is not None:
            frac = Decimal(str(partial_exit_pct))
            tp1_qty = qty_full * frac
            tp2_qty = qty_full - tp1_qty

        # Emit SL
        sl_msg = self._emit_place_order(
            msg=msg,
            client_id=f"{msg.pld.get('symbol')}_sl",
            order_type="STOP_MARKET",
            side=self._get_opposite_side(),
            qty=str(qty_full),
            price=str(sl_price),
            why="manage_place_sl",
        )

        # Emit TP1
        tp1_msg = self._emit_place_order(
            msg=msg,
            client_id=f"{msg.pld.get('symbol')}_tp1",
            order_type="TAKE_PROFIT_MARKET",
            side=self._get_opposite_side(),
            qty=str(tp1_qty),
            price=str(tp1_price),
            why="manage_place_tp1",
        )

        tp2_msg = None
        if tp2_price is not None and tp2_qty and tp2_qty > 0:
            tp2_msg = self._emit_place_order(
                msg=msg,
                client_id=f"{msg.pld.get('symbol')}_tp2",
                order_type="TAKE_PROFIT_MARKET",
                side=self._get_opposite_side(),
                qty=str(tp2_qty),
                price=str(tp2_price),
                why="manage_place_tp2",
            )

        # Далі – або повернути один Message, або створити batched механізм (як зараз)
        # Скелет: повернути SL, а TP1/TP2 віддати через додаткові події FSM
        # Реальну інтеграцію треба зробити з урахуванням існуючої fsm логіки.
        return sl_msg
```

> Тут головне – показати структуру; реальна імплементація має вписатися в існуючий механізм multi‑order placement.

---

#### 2.1.4. Обробка fill’ів TP1/TP2 + max_hold

**Скелет для max_hold (в `_check_rules`):**

```python
class ManageFlowFSM:
    # ...

    def _check_rules(self, msg: Message) -> Optional[Message]:
        # ... поточні правила ...

        # TIME-BASED EXIT (max_hold_sec per symbol)
        symbol = self._get_symbol(msg)
        if symbol and self.position_open_ts:
            _, max_hold_sec = self._get_exit_params(symbol)
            if max_hold_sec:
                now = time.time()
                if now - self.position_open_ts >= max_hold_sec:
                    # Emit DEC:ADJUST / CLOSE intent (скелет)
                    return self._emit_time_exit(msg)

        # Trailing stop – див. нижче
        # ...
        return None

    def _emit_time_exit(self, msg: Message) -> Message:
        """Force-close position due to max_hold_sec timeout."""
        # Скелет: згенерувати DEC:ADJUST або CMD:CLOSE в execution_position
        # Конкретний формат – як в існуючому протоколі FSM.
        ...
```

**TP1/TP2 fill handling (в `_on_bracket_placed` / іншому handlerі):**

```python
class ManageFlowFSM:
    # ...

    def _on_bracket_fill(self, msg: Message) -> Optional[Message]:
        """
        Handle fills for TP1/TP2/SL.
        Псевдокод:
          - якщо SL: повністю закрити позицію → state=FLAT
          - якщо TP1: зменшити position_qty, залишити state=TRACKING (чекаємо TP2/SL)
          - якщо TP2: повністю закрити → FLAT
        """
        pld = msg.pld or {}
        client_id = pld.get("clientOrderId", "")

        if "_sl" in client_id:
            # Full close
            self.position_qty = None
            self.state = ManageState.FLAT
        elif "_tp1" in client_id:
            # Partial close
            filled_qty = Decimal(str(pld.get("qty", "0")))
            if self.position_qty:
                self.position_qty -= filled_qty
        elif "_tp2" in client_id:
            self.position_qty = None
            self.state = ManageState.FLAT
        return None
```

> Реально у проєкті fill‑ів може бути інший шлях (через окремі FSM), але цей скелет показує очікувану поведінку.

---

#### 2.1.5. Trailing Stop skeleton

**Скелет:**

```python
class ManageFlowFSM:
    # ...

    def _update_trailing(self, msg: Message) -> None:
        """
        Update trailing SL based on current price and peak.
        Викликається з _check_rules(), якщо trailing enabled.
        """
        symbol = self._get_symbol(msg)
        enabled, activation_pct, distance_pct = self._get_trailing_params(symbol or "")
        if not enabled or not self.position_entry_price:
            return

        # Витягти поточну ціну з msg.pld
        try:
            price = Decimal(str((msg.pld or {}).get("price")))
        except Exception:
            return

        # Обчислити unrealized PnL у %
        entry = self.position_entry_price
        if self.position_side == "BUY":
            pnl_pct = (price - entry) / entry
        else:
            pnl_pct = (entry - price) / entry

        # Активація trailing
        if not self.trailing_activated and activation_pct is not None:
            if pnl_pct >= Decimal(str(activation_pct)):
                self.trailing_activated = True
                # Ініціалізувати peak price
                self._trailing_peak_price = price
                return

        if not self.trailing_activated:
            return

        # Оновлення піку
        if self.position_side == "BUY":
            if price > getattr(self, "_trailing_peak_price", price):
                self._trailing_peak_price = price
        else:
            if price < getattr(self, "_trailing_peak_price", price):
                self._trailing_peak_price = price

        # Обчислення нового SL
        if distance_pct is None:
            return

        dist = Decimal(str(distance_pct))
        if self.position_side == "BUY":
            new_sl = self._trailing_peak_price * (Decimal("1") - dist)
        else:
            new_sl = self._trailing_peak_price * (Decimal("1") + dist)

        # Modify SL if new_sl is better than current
        if self.sl_price is None or self._is_better_sl(new_sl, self.sl_price):
            self._pending_sl_update = new_sl
            # Actual modification happens in _check_rules via _apply_trailing_sl_update

    def _is_better_sl(self, new_sl: Decimal, current_sl: Decimal) -> bool:
        """Check if new_sl is more favorable (closer to current price, locking more profit)."""
        if self.position_side == "BUY":
            return new_sl > current_sl  # Higher SL = more profit locked
        else:
            return new_sl < current_sl  # Lower SL = more profit locked

    def _apply_trailing_sl_update(self, msg: Message) -> Optional[Message]:
        """
        Apply pending trailing SL update via CANCEL + NEW order.
        Called from _check_rules when _pending_sl_update is set.
        """
        if not hasattr(self, '_pending_sl_update') or self._pending_sl_update is None:
            return None
        
        new_sl = self._pending_sl_update
        self._pending_sl_update = None
        
        # Cancel existing SL order
        if self.sl_order_id:
            cancel_msg = self._emit_cancel_order(msg, self.sl_order_id, "trailing_sl_cancel")
            # After cancel confirmed, place new SL (simplified: emit both)
        
        # Place new SL at updated price
        symbol = self._get_symbol(msg)
        new_sl_msg = self._emit_place_order(
            msg=msg,
            client_id=f"{symbol}_sl_trail_{int(time.time())}",
            order_type="STOP_MARKET",
            side=self._get_opposite_side(),
            qty=str(self.position_qty),
            price=str(new_sl),
            why="trailing_sl_update",
        )
        self.sl_price = new_sl
        return new_sl_msg
```

**Integration point in `_check_rules`:**

```python
def _check_rules(self, msg: Message) -> Optional[Message]:
    # ... existing rules ...
    
    # TRAILING STOP UPDATE
    self._update_trailing(msg)  # Updates _pending_sl_update if needed
    trailing_msg = self._apply_trailing_sl_update(msg)
    if trailing_msg:
        return trailing_msg
    
    # MAX HOLD TIME CHECK
    symbol = self._get_symbol(msg)
    if symbol and self.position_open_ts:
        _, max_hold_sec = self._get_exit_params(symbol)
        if max_hold_sec and time.time() - self.position_open_ts >= max_hold_sec:
            return self._emit_time_exit(msg)
    
    return None
```

---

### 2.2. `decision_making.py` – per-asset weights, side-bias, regime thresholds/sizing

**Завдання:**  
Використати `aurora_instruments` для overrides над глобальними параметрами.

#### 2.2.1. Signal weights per symbol

**Скелет:**

```python
class DecisionMaking:
    # ...

    def _get_signal_weights(self, symbol: str) -> dict:
        """
        Return signal_weights for symbol.
        Priority:
          1) trading.aurora_instruments.<SYMBOL>.weights
          2) trading.decision.signal_weights (global)
        """
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg and getattr(instr_cfg, "weights", None):
            return instr_cfg.weights

        # Fallback: global
        try:
            trading_cfg = self._safe_config_get("trading", default={}) or {}
            if hasattr(trading_cfg, "decision") and getattr(trading_cfg.decision, "signal_weights", None):
                return trading_cfg.decision.signal_weights
            if isinstance(trading_cfg, dict):
                return (trading_cfg.get("decision") or {}).get("signal_weights", {}) or {}
        except Exception:
            return {}
```

**Integration point in `_make_decision_for_symbol` (around line ~1220):**

```python
# BEFORE (global weights):
# signal_weights = decision_config.get("signal_weights", {})

# AFTER (per-symbol with fallback):
signal_weights = self._get_signal_weights(symbol)

# Use signal_weights for score calculation:
for feature_name, weight in signal_weights.items():
    # ... existing score aggregation logic ...
```

---

#### 2.2.2. Per-asset side-bias, regime thresholds, sizing

**Скелет:**

```python
class DecisionMaking:
    # ...

    def _get_side_bias_params(self, symbol: str):
        """
        Return (window_sec, target_ratio, penalty_factor) with per-asset override.
        """
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg and getattr(instr_cfg, "side_bias", None):
            sb = instr_cfg.side_bias
            return sb.window_sec, sb.target_ratio, sb.penalty_factor

        # Fallback: global
        window_sec = self._safe_config_get("trading", "decision", "side_bias_window_sec", default=60)
        target_ratio = self._safe_config_get("trading", "decision", "side_bias_target_ratio", default=0.60)
        penalty_factor = self._safe_config_get("trading", "decision", "side_bias_penalty_factor", default=0.50)
        return window_sec, target_ratio, penalty_factor

    def _get_regime_thresholds(self, symbol: str) -> dict:
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg and getattr(instr_cfg, "regime_thresholds", None):
            rt = instr_cfg.regime_thresholds
            return {
                "HIGH_VOLATILITY": rt.high_volatility_multiplier,
                "LOW_VOLATILITY": rt.low_volatility_multiplier,
                "TREND": rt.trend_multiplier,
            }
        # Fallback: global regime_threshold_multipliers
        return self._safe_config_get("trading", "decision", "regime_threshold_multipliers", default={}) or {}

    def _get_regime_sizing(self, symbol: str) -> dict:
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg and getattr(instr_cfg, "regime_sizing", None):
            rs = instr_cfg.regime_sizing
            return {
                "HIGH_VOLATILITY": rs.high_volatility_multiplier,
                "LOW_VOLATILITY": rs.low_volatility_multiplier,
                "MEAN_REVERSION": rs.mean_reversion_multiplier,
                "BASE_SIZE_USD": rs.base_size_usd,
            }
        return self._safe_config_get("trading", "decision", "sizing_modifiers", default={}) or {}
```

**Integration points in `_make_decision_for_symbol`:**

```python
# === SIDE BIAS (around line ~1362) ===
# BEFORE:
# bias_window_sec = self._safe_config_get("trading", "decision", "side_bias_window_sec", default=60)
# sell_target_ratio = self._safe_config_get("trading", "decision", "side_bias_target_ratio", default=0.60)
# penalty_factor = self._safe_config_get("trading", "decision", "side_bias_penalty_factor", default=0.50)

# AFTER:
bias_window_sec, sell_target_ratio, penalty_factor = self._get_side_bias_params(symbol)

# === REGIME THRESHOLDS (around line ~1343) ===
# BEFORE:
# regime_thresholds_cfg = self._safe_config_get("trading", "decision", "regime_threshold_multipliers", default={})

# AFTER:
regime_thresholds_cfg = self._get_regime_thresholds(symbol)

# === REGIME SIZING (around line ~1634) ===
# BEFORE:
# sizing_mods = self._safe_config_get("trading", "decision", "sizing_modifiers", default={})

# AFTER:
sizing_mods = self._get_regime_sizing(symbol)
```

---

#### 2.2.3. Exit cooldown per symbol

**Ідея:**  
Схожа на QoS cooldown, але прив’язана до факту **виходу з позиції** (exit) і бере значення із `aurora_instruments.<SYMBOL>.execution.cooldown_sec`.

Скелет (мінімально):

```python
class DecisionMaking:
    # ...
    _exit_cooldown_ts: dict[str, float] = {}

    def _get_exit_cooldown_sec(self, symbol: str) -> int:
        instr_cfg = self._get_aurora_instrument_cfg(symbol)
        if instr_cfg and getattr(instr_cfg, "execution", None):
            return instr_cfg.execution.cooldown_sec or 0
        return 0

    def _register_exit(self, symbol: str) -> None:
        cooldown = self._get_exit_cooldown_sec(symbol)
        if cooldown > 0:
            self._exit_cooldown_ts[symbol] = time.time() + cooldown

    def _is_in_exit_cooldown(self, symbol: str) -> bool:
        ts = self._exit_cooldown_ts.get(symbol)
        if not ts:
            return False
        return time.time() < ts

    def _precheck_exit_cooldown(self, symbol: str) -> bool:
        """Return False if symbol is in exit cooldown window."""
        return not self._is_in_exit_cooldown(symbol)
```

Викликові місця:
- перед генерацією нового intent: перевіряти `_precheck_exit_cooldown(symbol)`;
- при логічному exit (коли позицію закрито) – викликати `_register_exit(symbol)`.

---

## 3. Track B – 1m Mean Reversion (окремий strategy-layer)

> Це окремий трек; тут лише скелети. Реальна інтеграція – після стабілізації Aurora Phase 3+.

### 3.1. `apps/reference/domains/feature_engineering/bar_resampler.py` – Resampler tick→1m

**Скелет нового модуля:**

```python
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Deque
from collections import deque
import time


@dataclass
class Bar:
    symbol: str
    timeframe_sec: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    start_ts_ms: int
    end_ts_ms: int


class BarResampler:
    """
    Tick → OHLCV bar resampler.
    Працює у пам'яті; інтегрується з FSM через події типу EVT:BAR_CLOSED.
    """

    def __init__(self, timeframe_sec: int = 60):
        self.timeframe_sec = timeframe_sec
        self.current_bar: Optional[Bar] = None
        self.completed_bars: Deque[Bar] = deque(maxlen=1000)

    def add_tick(self, symbol: str, price: Decimal, volume: Decimal, ts_ms: Optional[int] = None) -> Optional[Bar]:
        """
        Додати тик; повернути Bar, якщо бар закрито.
        """
        if ts_ms is None:
            ts_ms = int(time.time() * 1000)

        if not self.current_bar:
            self.current_bar = Bar(
                symbol=symbol,
                timeframe_sec=self.timeframe_sec,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
                start_ts_ms=ts_ms,
                end_ts_ms=ts_ms,
            )
            return None

        # Перевірка: чи новий бар
        if ts_ms - self.current_bar.start_ts_ms >= self.timeframe_sec * 1000:
            # Закриваємо поточний бар
            self.current_bar.end_ts_ms = ts_ms
            closed = self.current_bar
            self.completed_bars.append(closed)
            # Старт нового
            self.current_bar = Bar(
                symbol=symbol,
                timeframe_sec=self.timeframe_sec,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=volume,
                start_ts_ms=ts_ms,
                end_ts_ms=ts_ms,
            )
            return closed

        # Оновлюємо поточний бар
        self.current_bar.close = price
        self.current_bar.high = max(self.current_bar.high, price)
        self.current_bar.low = min(self.current_bar.low, price)
        self.current_bar.volume += volume
        self.current_bar.end_ts_ms = ts_ms
        return None
```

> Далі MarketData/FeatureEngineering можуть емітити `EVT:BAR_CLOSED` для 1m MR стратегії.

---

### 3.2. Bollinger/RSI у FeatureEngineering (опційно – окремий engine)

Скелети функцій (для використання з 1m барами):

```python
def compute_bollinger(
    closes: list[Decimal],
    window: int,
    num_std: float = 2.0,
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Return (upper, lower, mid) for останньої свічки.
    """
    ...


def compute_rsi(
    closes: list[Decimal],
    window: int = 14,
) -> Decimal:
    ...
```

> Реально ці функції можна залишити в R&D / окремому модулі `mean_reversion_features.py` і не змішувати з Aurora core.

---

### 3.3. Strategy-layer: `mean_reversion_1m_strategy.py`

**Скелет:**

```python
class MeanReversion1mStrategy:
    """
    Бар-базована стратегія:
      - входи по Bollinger Bands
      - allowed_regimes: FLAT_LOW/NORMAL/HIGH
      - fee-aware expected_pnl
    """

    def __init__(self, config: dict):
        self.config = config
        # зчитати bb_window, min_vol_atr, sl_pct, allowed_regimes, fees, etc.

    def should_enter_long(self, bar, regime: str) -> bool:
        """
        bar: структура з полями close, bb_upper, bb_lower, bb_mid, bb_width.
        """
        ...

    def should_enter_short(self, bar, regime: str) -> bool:
        ...
```

Інтеграція:
- У `decision_making.py` додати registry стратегій:
  - `self.strategies["mean_reversion_1m"] = MeanReversion1mStrategy(config_for_mr)`
- У `_make_decision_for_symbol`:
  - якщо символ/таймфрейм належить MR – делегувати прийняття рішення цій стратегії.

---

## 4. Testing Plan – Unit & Integration

### 4.1. Unit tests

#### 4.1.1. Per-instrument config models

**Файли:**
- `apps/reference/domains/decision_making/tests/test_aurora_instrument_config.py` (NEW)

**Тести:**
- Завантажити mini-YAML із `aurora_instruments` для 1-2 символів.
- Переконатися, що:
  - Pydantic моделі правильно парсять `weights`, `side_bias`, `regime_*`, `exit`, `take_profit`, `trailing_stop`, `execution`.
  - `_get_aurora_instrument_cfg(symbol)` повертає потрібний об’єкт.

#### 4.1.2. DecisionMaking overrides

**Файли:**
- `apps/reference/domains/decision_making/tests/test_per_instrument_overrides.py` (NEW)

**Тести:**
- Для символу ETHUSDT:
  - `_get_signal_weights("ETHUSDT")` → повертає weights з `aurora_instruments`.
  - `_get_side_bias_params("ETHUSDT")` → повертає 0.9/600/0.6.
  - `_get_regime_thresholds("ETHUSDT")` → повертає 1.3/0.85/1.05.
  - `_get_regime_sizing("ETHUSDT")` → повертає 0.3/1.9/0.8/base_size=1000.
- Для символу без override:
  - fallback на глобальні значення.

#### 4.1.3. ManageFlowFSM – `_calculate_bracket_prices` & partial exits

**Файли:**
- `apps/reference/domains/execution_position/tests/test_fsm_manage_brackets.py` (NEW)

**Тести:**
- GIVEN:
  - `position_entry_price = 100`, `position_side = "BUY"`, `position_qty = 1`.
  - `aurora_instruments.ETHUSDT.exit.sl_pct = 0.02`, `take_profit.tp_low_ratio=0.5`, `tp_high_ratio=1.5`, `partial_exit_pct=0.7`.
  - symbol = "ETHUSDT".
- WHEN:
  - `_calculate_bracket_prices()`  
- THEN:
  - SL = 98.0  
  - TP1 = 100 * (1 + 0.01) = 101.0  
  - TP2 = 100 * (1 + 0.03) = 103.0  
- І перевірити кількість та обсяг ордерів у `_place_brackets`:
  - SL qty = 1.0  
  - TP1 qty = 0.7  
  - TP2 qty = 0.3

#### 4.1.4. Max-hold time

**Тести:**
- Задати `position_open_ts` = now - 1000s, `max_hold_sec = 600`.
- `_check_rules(msg)` має згенерувати `_emit_time_exit`.
- Для позиції з shorter age – нічого не робити.

#### 4.1.5. Trailing stop

**Тести:**
- LONG кейс:
  - entry = 100, activation_pct=0.02, distance_pct=0.01.
  - Ціна росте до 103 → trailing_activated = True, peak=103.
  - Потім ціна падає до 102 → SL має бути ~101.97 (з урахуванням distance).
- SHORT кейс:
  - дзеркально.

#### 4.1.6. BarResampler

**Файл:**
- `apps/reference/domains/feature_engineering/tests/test_bar_resampler.py` (NEW)

**Тести:**
- Стрім тиков за 120с із кроком 1с:
  - Переконатися, що створюються рівно 2 закриті 60‑сек бари.
  - OHLCV барів співпадає з очікуваними (за руками/попередньо розрахованими значеннями).

---

### 4.2. Integration tests

#### 4.2.1. Aurora Phase 3+ – end-to-end per symbol

**Ідея:**
- Побудувати невеликий інтеграційний тест, що:
  - створює FSM core в пам’яті,
  - піднімає `DecisionMaking`, `ExecutionPosition (ManageFlowFSM)`,
  - підсовує синтетичні `FEATURES_CALCULATED` + `PORTFOLIO_STATE_UPDATED` + `EVT:PARTIAL_FILL/FILL` події,
  - перевіряє, що:
    - intent генерується з правильними signal_weights/threshold/sizing (по ETH/BTC/XRP),
    - ExecPosFSM + ManageFlowFSM ставлять SL/TP1/TP2 як у конфігах,
    - при спрацюванні TP1/TP2/SL FSM переходить у правильні стани.

**Файл:**
- `apps/reference/domains/decision_making/tests/test_aurora_phase3_integration.py` (NEW)

---

#### 4.2.2. 1m Mean Reversion (як окремий модуль)

**Ідея:**
- Без інтеграції в live Aurora, просто:
  - прогнати `BarResampler` на pre-recorded тиках з Jan 2024,
  - на основі bar‑фіч (BB/RSI/режим) прогнати `MeanReversion1mStrategy`,
  - перевірити, що результати (PnL/entries/exits) близькі до BacktestEngine1m (±5–10%).

---

### 4.3. Regression / Safety Checks

Перед деплоєм:
- Прогнати всі існуючі тести в `apps/reference/domains/decision_making/tests` і `feature_engineering/tests`.
- Додати окремий "smoke test" конфіг (наприклад, з лише одним символом і спрощеними параметрами), щоб:
  - запустити `apps/reference/main.py` в testnet‑режимі,
  - впевнитися, що нові поля в конфігах не ламають парсинг/ініціалізацію.

---

Цей Technical Appendix разом з `NEW_ALPHA_OPTUNA_PROD_ROADMAP.md` дає повну картину:  
– які саме модулі/файли треба розширити,  
– які скелети коду/патчі внести,  
– як покрити все unit та інтеграційними тестами,  
щоб перенести результати Optuna (Aurora Phase 3+ та 1m Mean Reversion) у production-код максимально безпечно. 

