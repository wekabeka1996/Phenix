# apps/reference/domains/execution_position/utils.py
from __future__ import annotations
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from typing import Optional, Tuple, Any
import hashlib, time, re, math

__all__ = ["quantize_stop_price", "validate_anti_2021", "generate_client_order_id", "calc_tp_sl_from_mark", "validate_not_immediate", "opposite_side"]

# ---- price quantization helpers ----

def _round_to_tick(price: float | Decimal, tick_size: float | Decimal, mode: str = "floor") -> float:
    p = Decimal(str(price))
    t = Decimal(str(tick_size))
    if t <= 0:
        return float(p)
    if mode == "floor":
        q = (p / t).to_integral_value(rounding=ROUND_DOWN)
    elif mode == "ceil":
        q = (p / t).to_integral_value(rounding=ROUND_UP)
    else:
        # Binance зазвичай приймає floor; "nearest" не використовуємо для стопів
        q = (p / t).to_integral_value(rounding=ROUND_DOWN)
    return float(q * t)

def quantize_stop_price(stop_price: float, tick_size: float, *, side: Optional[str] = None) -> float:
    """
    Квантує stopPrice до кратності tick_size.
    Для SELL краще floor, для BUY — ceil, щоб уникати рівності тригеру.
    """
    s = (side or "").upper()
    mode = "floor" if s == "SELL" else "ceil" if s == "BUY" else "floor"
    return _round_to_tick(stop_price, tick_size, mode=mode)

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

    def nudge_down(px: float) -> float: return px - eps
    def nudge_up(px: float) -> float:   return px + eps

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
        if (s == "SELL" and t.startswith("STOP")) or (s == "BUY" and t.startswith("TAKE_PROFIT")):
            sp_q -= float(tick_size)
        else:
            sp_q += float(tick_size)
        adjusted = True
        reason_parts.append("nudge one tick away from trigger")

    return float(sp_q), adjusted, "; ".join(reason_parts)

# ---- clientOrderId helper (<=36 chars) ----

def generate_client_order_id(prefix: str, decision_id: str, extra: str | None = None, *, max_len: int = 32) -> str:
    """
    Створює короткий детермінований clientOrderId (Binance: <36 симв.).
    """
    base = f"{prefix}:{decision_id}:{extra or ''}:{int(time.time()*1000)}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]
    cid = f"{prefix}-{h}"
    if len(cid) > max_len:
        cid = cid[:max_len]
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

    Returns:
        (tp_price, sl_price)
    """
    m = _to_float(mark, name="mark")
    b = 10000.0
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
    return 'SELL' if side == 'BUY' else 'BUY'