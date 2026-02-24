# apps/reference/domains/execution_position/utils.py
from __future__ import annotations
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Optional, Tuple, Any
import hashlib, re, math
# DET-BT-11: Use get_clock() for deterministic backtest
from apps.reference.core.time import get_clock

__all__ = [
    "quantize_stop_price",
    "quantize_stop_price_dec",
    "validate_anti_2021",
    "generate_client_order_id",
    "calc_tp_sl_from_mark",
    "validate_not_immediate",
    "opposite_side",
    "BoundedEventDeduper",
]

# ---- price quantization helpers ----


def _round_to_tick(
    price: float | Decimal, tick_size: float | Decimal, mode: str = "floor"
) -> float:
    return float(_round_to_tick_dec(price, tick_size, mode=mode))


def _round_to_tick_dec(
    price: float | Decimal, tick_size: float | Decimal, mode: str = "floor"
) -> Decimal:
    p = Decimal(str(price))
    t = Decimal(str(tick_size))
    if t <= 0:
        return p
    if mode == "floor":
        q = (p / t).to_integral_value(rounding=ROUND_DOWN)
    elif mode == "ceil":
        q = (p / t).to_integral_value(rounding=ROUND_UP)
    else:
        # Binance зазвичай приймає floor; "nearest" не використовуємо для стопів
        q = (p / t).to_integral_value(rounding=ROUND_DOWN)
    return q * t


def quantize_stop_price(
    stop_price: float, tick_size: float, *, side: Optional[str] = None
) -> float:
    """
    Quantize stopPrice to tick_size multiples.

    FIXED LOGIC:
    - side="BUY" (SL for Short, Price > Market): Round UP (CEIL) to avoid premature trigger.
    - side="SELL" (SL for Long, Price < Market): Round DOWN (FLOOR) to avoid premature trigger.
    - side=None: Defaults to legacy behavior (FLOOR), but logs warning if debug enabled.
    """
    return float(
        quantize_stop_price_dec(
            Decimal(str(stop_price)),
            Decimal(str(tick_size)),
            side=side,
        )
    )


def quantize_stop_price_dec(
    stop_price: Decimal, tick_size: Decimal, *, side: Optional[str] = None
) -> Decimal:
    """Decimal-safe stopPrice quantization without float round-trips."""
    if side:
        s = side.upper()
        if s == "BUY":
            return _round_to_tick_dec(stop_price, tick_size, mode="ceil")
        if s == "SELL":
            return _round_to_tick_dec(stop_price, tick_size, mode="floor")

    # Fallback / Default behavior (now safe-guarded by explicit side logic above)
    return _round_to_tick_dec(stop_price, tick_size, mode="floor")


# ---- anti-2021 guard ----


def validate_anti_2021(
    side: str,
    order_type: str,
    stop_price: float,
    trigger_price: float,
    tick_size: float,
) -> Tuple[float, bool, str]:
    """
    Перевіряє та (за потреби) зсуває stop_price на правильний бік відносно trigger_price,
    щоб уникнути Binance -2021 ("Order would immediately trigger").

    Повертає: (коригований_stop_price, чи_було_змінено, причина)
    """
    s = (side or "").upper()
    t = (order_type or "").upper()
    adjusted = False
    reason_parts: list[str] = []

    # 1 тик або мінімальний мікро-зсув
    eps = max(float(tick_size), float(trigger_price) * 1e-9)

    def nudge_down(px: float) -> float:
        return px - eps

    def nudge_up(px: float) -> float:
        return px + eps

    if t in {"STOP", "STOP_MARKET", "TAKE_PROFIT", "TAKE_PROFIT_MARKET"}:
        if s == "SELL":
            if t.startswith("STOP"):
                # SL для LONG: має бути СТРОГО < trigger
                if not (stop_price < trigger_price):
                    stop_price = nudge_down(trigger_price)
                    adjusted = True
                    reason_parts.append("sell STOP must be < trigger")
            else:
                # TP для LONG: має бути СТРОГО > trigger
                if not (stop_price > trigger_price):
                    stop_price = nudge_up(trigger_price)
                    adjusted = True
                    reason_parts.append("sell TP must be > trigger")
        elif s == "BUY":
            if t.startswith("STOP"):
                # SL для SHORT: має бути СТРОГО > trigger
                if not (stop_price > trigger_price):
                    stop_price = nudge_up(trigger_price)
                    adjusted = True
                    reason_parts.append("buy STOP must be > trigger")
            else:
                # TP для SHORT: має бути СТРОГО < trigger
                if not (stop_price < trigger_price):
                    stop_price = nudge_down(trigger_price)
                    adjusted = True
                    reason_parts.append("buy TP must be < trigger")

    # Квантуємо з урахуванням напряму
    sp_q = quantize_stop_price(stop_price, tick_size, side=s)

    # Якщо після округлення дорівнює тригеру — зсунь ще на 1 тик
    if abs(sp_q - trigger_price) < 1e-15:
        if (s == "SELL" and t.startswith("STOP")) or (
            s == "BUY" and t.startswith("TAKE_PROFIT")
        ):
            sp_q -= float(tick_size)
        else:
            sp_q += float(tick_size)
        adjusted = True
        reason_parts.append("nudge one tick away from trigger")

    return float(sp_q), adjusted, "; ".join(reason_parts)


# ---- clientOrderId helper (<=35 chars) ----


def _build_hashed_client_order_id(role: str, stable_key: str, symbol: str) -> str:
    raw_str = f"{stable_key}|{role}|{symbol}"
    hash_part = hashlib.md5(raw_str.encode("utf-8")).hexdigest()[:12]
    return f"{role}-{hash_part}"


def generate_client_order_id(
    prefix: str,
    decision_id: str,
    extra: str | None = None,
    *,
    idempotent_key: str | None = None,
    max_len: int = 32,
    config: Optional[Any] = None,
) -> str:
    """
    Створює короткий детермінований clientOrderId (Binance: <=35 симв.).
    """
    # Try to get max_len from domains config if provided
    if config:
        try:
            if hasattr(config, 'domains') and hasattr(config.domains, 'execution_position'):
                max_len = config.domains.execution_position.utils.client_order_id_max_length
        except (AttributeError, TypeError):
            pass  # Use provided/default value
    
    role_set = {"ENTRY", "SL", "TP", "CLOSE"}
    binance_max_len = 35

    # Deterministic mode:
    # - If idempotent_key is explicitly provided, derive a stable clientOrderId from it.
    # - Also support stable IDs for legacy callers that pass (role, rid, extra=symbol).
    if idempotent_key is not None:
        role = str(prefix)
        symbol = str(decision_id)
        cid = _build_hashed_client_order_id(
            role=role,
            stable_key=str(idempotent_key),
            symbol=symbol,
        )
    elif extra is not None and str(prefix).upper() in role_set:
        role = str(prefix).upper()
        stable_key = str(decision_id)
        symbol = str(extra)
        cid = _build_hashed_client_order_id(
            role=role,
            stable_key=stable_key,
            symbol=symbol,
        )
    else:
        # DET-BT-11: Use get_clock() for deterministic backtest
        base = f"{prefix}:{decision_id}:{extra or ''}:{get_clock().now_ms()}"
        h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
        cid = f"{prefix}-{h}"

    try:
        effective_max_len = int(max_len)
    except (TypeError, ValueError):
        effective_max_len = binance_max_len
    effective_max_len = max(1, min(effective_max_len, binance_max_len))

    if len(cid) > effective_max_len:
        cid = cid[:effective_max_len]
    # тільки дозволені символи
    return re.sub(r"[^A-Za-z0-9_\-]", "", cid)


# ---- additional utilities ----


def _to_float(val: Any, *, name: str = "value") -> float:
    """
    Robustly convert mark-like value to float. Accepts dict/str/Decimal/float/int.
    If dict is provided, looks for common keys.
    """
    if val is None:
        raise ValueError(f"{name} is None")
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, str):
        return float(val)
    if isinstance(val, dict):
        for k in ("markPrice", "price", "last", "lastPrice", "indexPrice"):
            v = val.get(k)
            if v is not None:
                return float(v)
    raise TypeError(f"Expected number-like for {name}, got {type(val)}: {val}")


def calc_tp_sl_from_mark(
    mark: Any,
    side: str,
    tp_bps: Any,
    sl_bps: Any,
    tick_size: Optional[float] = None,
    config: Optional[Any] = None,
) -> tuple[float, float]:
    """
    Розрахунок TP/SL від MARK_PRICE.
    Приймає mark як dict/str/float/Decimal. tp_bps/sl_bps можуть бути стрічками або числами.

    Args:
        mark: mark price або словник з ключем 'markPrice'/'price'/'last'.
        side: 'LONG' або 'SHORT'
        tp_bps: take-profit в б.п. (100 б.п. = 1%)
        sl_bps: stop-loss в б.п.
        tick_size: опційно — крок квантування ціни.
        config: опційно — configuration object

    Returns:
        (tp_price, sl_price)
    """
    m = _to_float(mark, name="mark")
    
    # Try to get basis_points_base from domains config
    b = 10000.0  # default
    if config:
        try:
            if hasattr(config, 'domains') and hasattr(config.domains, 'execution_position'):
                b = config.domains.execution_position.utils.basis_points_base
        except (AttributeError, TypeError):
            pass  # Use default
    
    tp_bps_f = _to_float(tp_bps, name="tp_bps")
    sl_bps_f = _to_float(sl_bps, name="sl_bps")

    s = (side or "").upper()
    if s == "LONG":
        tp = m * (1.0 + tp_bps_f / b)
        sl = m * (1.0 - sl_bps_f / b)
        # kвантування: TP ↑, SL ↓
        if tick_size and tick_size > 0:
            tp = _round_to_tick(tp, tick_size, mode="ceil")
            sl = _round_to_tick(sl, tick_size, mode="floor")
        # анти-2021
        if not (sl < m and tp > m):
            raise ValueError(f"anti-2021 (LONG) failed: sl={sl}, tp={tp}, mark={m}")
    elif s == "SHORT":
        tp = m * (1.0 - tp_bps_f / b)
        sl = m * (1.0 + sl_bps_f / b)
        if tick_size and tick_size > 0:
            tp = _round_to_tick(tp, tick_size, mode="floor")
            sl = _round_to_tick(sl, tick_size, mode="ceil")
        if not (sl > m and tp < m):
            raise ValueError(f"anti-2021 (SHORT) failed: sl={sl}, tp={tp}, mark={m}")
    else:
        raise ValueError("Side must be 'LONG' or 'SHORT'")

    return float(tp), float(sl)


def validate_not_immediate(side: str, tp, sl, mark) -> float:
    """
    Анти-2021 перевірка: тригер не має спрацювати одразу.
    Повертає нормалізований mark (float) для подальшого логування.
    """
    m = _to_float(mark, name="mark")
    tp_f = _to_float(tp, name="tp")
    sl_f = _to_float(sl, name="sl")

    s = (side or "").upper()
    if s == "LONG":
        # LONG: SL < mark, TP > mark
        if sl_f >= m:
            raise ValueError(f"anti-2021 (LONG) failed: SL({sl_f}) >= mark({m})")
        if tp_f <= m:
            raise ValueError(f"anti-2021 (LONG) failed: TP({tp_f}) <= mark({m})")
    elif s == "SHORT":
        # SHORT: SL > mark, TP < mark
        if sl_f <= m:
            raise ValueError(f"anti-2021 (SHORT) failed: SL({sl_f}) <= mark({m})")
        if tp_f >= m:
            raise ValueError(f"anti-2021 (SHORT) failed: TP({tp_f}) >= mark({m})")
    else:
        raise ValueError(f"Unknown side: {side}")

    return m


def opposite_side(side: str) -> str:
    """
    Get opposite side.

    Args:
        side: 'BUY' or 'SELL'.

    Returns:
        Opposite side.
    """
    return "SELL" if side == "BUY" else "BUY"


class BoundedEventDeduper(set):
    """
    Bounded idempotency tracker with TTL and MaxSize.
    Inherits from set to maintain compatibility with existing tests and FSM logic.
    """

    def __init__(self, max_size: int = 100000, ttl_ms: int = 86400000):
        super().__init__()
        from collections import OrderedDict
        self.max_size = max_size
        self.ttl_ms = ttl_ms
        self._ts: OrderedDict[str, int] = OrderedDict()

    def seen(self, event_key: str) -> bool:
        """Check if event was already processed."""
        return event_key in self

    def add(self, event_key: str, now_ms: int | None = None):
        """Mark event as processed and prune old entries."""
        if now_ms is None:
            # DET-BT-11: Use get_clock() for deterministic backtest
            now_ms = get_clock().now_ms()
        
        super().add(event_key)
        if event_key in self._ts:
            self._ts.move_to_end(event_key)
        self._ts[event_key] = now_ms
        self.prune(now_ms)

    def prune(self, now_ms: int):
        """Evict by TTL and then by MaxSize."""
        # 1. TTL Prune (Oldest first)
        while self._ts:
            first_key = next(iter(self._ts))
            first_ts = self._ts[first_key]
            if now_ms - first_ts > self.ttl_ms:
                self._ts.popitem(last=False)
                if first_key in self:
                    super().remove(first_key)
            else:
                break

        # 2. Size Prune
        while len(self._ts) > self.max_size:
            evict_key, _ = self._ts.popitem(last=False)
            if evict_key in self:
                super().remove(evict_key)
