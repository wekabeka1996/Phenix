# apps/reference/domains/execution_position/utils.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from enum import Enum
from typing import Any, Optional, Tuple

import hashlib
import re
import time

__all__ = [
    "quantize_stop_price",
    "validate_anti_2021",
    "make_execpos_client_order_id",
    "calc_tp_sl_from_mark",
    "validate_not_immediate",
    "opposite_side",
    "ClientOrderIntent",
    "ClientOrderIdMeta",
    "build_client_order_id",
    "build_bracket_client_ids",
    "parse_client_order_id",
    "BPS_DIVISOR",
]


CLIENT_ORDER_ID_VERSION = "v1"
CLIENT_ORDER_ID_DOMAIN = "ep"
CLIENT_ORDER_ID_PREFIX = f"{CLIENT_ORDER_ID_DOMAIN}{CLIENT_ORDER_ID_VERSION}"

# Basis points divisor: 10000 bps = 100%
BPS_DIVISOR: float = 10000.0
CLIENT_ORDER_ID_INTENT_TOKENS = {
    "entry": "en",
    "stop_loss": "sl",
    "take_profit": "tp",
    "close": "cl",
    "adjust": "ad",
    "unknown": "uk",
}
CLIENT_ORDER_ID_TOKEN_MAP = {
    token: intent for intent, token in CLIENT_ORDER_ID_INTENT_TOKENS.items()
}
CLIENT_ORDER_ID_REGEX = re.compile(
    r"^(?P<prefix>epv\d+)-(?P<intent>[a-z]{2})-(?P<seed>[a-z0-9]+)-(?P<nonce>[a-z0-9]+)$",
    re.IGNORECASE,
)


class ClientOrderIntent(str, Enum):
    """Canonical intent encoded into clientOrderId tokens."""

    ENTRY = "entry"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    CLOSE = "close"
    ADJUST = "adjust"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ClientOrderIdMeta:
    """Decoded metadata for clientOrderId contract."""

    raw: str
    intent: ClientOrderIntent
    version: str
    seed: str
    nonce: str
    prefix: str
    legacy: bool = False

    def bundle_key(self) -> Optional[str]:
        """Shared identifier for grouping SL/TP minted from the same entry seed."""

        clean_seed = self.seed.strip()
        if not clean_seed:
            return None
        return f"{self.prefix}:{clean_seed}"

# ---- price quantization helpers ----


def _round_to_tick(
    price: float | Decimal, tick_size: float | Decimal, mode: str = "floor"
) -> float:
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


def quantize_stop_price(
    stop_price: float, tick_size: float, *, side: Optional[str] = None
) -> float:
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


# ---- clientOrderId helpers ----


def _sanitize_component(value: Optional[str], *, default: str, max_len: int) -> str:
    cleaned = re.sub(r"[^a-z0-9]", "", (value or "").lower())
    if not cleaned:
        cleaned = default
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned


def _derive_seed(
    *,
    rid: Optional[str],
    symbol: Optional[str],
    decision_id: Optional[str],
    extra: Optional[str],
    max_len: int,
) -> str:
    parts = [rid, symbol, decision_id, extra]
    base = "|".join(part for part in parts if part)
    if not base:
        base = str(time.time_ns())
    digest = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return digest[:max_len]


def _encode_base36(value: int) -> str:
    if value <= 0:
        return "0"
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    chars: list[str] = []
    n = value
    while n > 0:
        n, rem = divmod(n, 36)
        chars.append(alphabet[rem])
    return "".join(reversed(chars)) or "0"


def _build_nonce(ts_ms: Optional[int], *, length: int) -> str:
    seed_ms = ts_ms if ts_ms is not None else int(time.time() * 1000)
    encoded = _encode_base36(max(seed_ms, 0))
    return encoded[-length:].rjust(length, "0")


def build_client_order_id(
    *,
    intent: ClientOrderIntent | str,
    rid: Optional[str] = None,
    symbol: Optional[str] = None,
    decision_id: Optional[str] = None,
    seed: Optional[str] = None,
    extra: Optional[str] = None,
    ts_ms: Optional[int] = None,
    max_len: int = 36,
) -> ClientOrderIdMeta:
    """Shared builder for execution_position clientOrderId contract."""

    intent_enum = (
        intent
        if isinstance(intent, ClientOrderIntent)
        else ClientOrderIntent(str(intent).lower())
    )
    token = CLIENT_ORDER_ID_INTENT_TOKENS[intent_enum.value]
    derived_seed = seed or _derive_seed(
        rid=rid,
        symbol=symbol,
        decision_id=decision_id,
        extra=extra,
        max_len=12,
    )
    seed_value = _sanitize_component(
        derived_seed,
        default="seed",
        max_len=12,
    )
    nonce_value = _build_nonce(ts_ms, length=6)
    cid = f"{CLIENT_ORDER_ID_PREFIX}-{token}-{seed_value}-{nonce_value}"

    if len(cid) > max_len:
        overflow = len(cid) - max_len
        if overflow > 0 and len(seed_value) > 4:
            trim = min(overflow, len(seed_value) - 4)
            seed_value = seed_value[:-trim]
            cid = f"{CLIENT_ORDER_ID_PREFIX}-{token}-{seed_value}-{nonce_value}"
            overflow = len(cid) - max_len
        if overflow > 0 and len(nonce_value) > 4:
            trim = min(overflow, len(nonce_value) - 4)
            nonce_value = nonce_value[trim:]
            cid = f"{CLIENT_ORDER_ID_PREFIX}-{token}-{seed_value}-{nonce_value}"
            overflow = len(cid) - max_len
        if overflow > 0:
            cid = cid[-max_len:]

    version = CLIENT_ORDER_ID_VERSION
    return ClientOrderIdMeta(
        raw=cid,
        intent=intent_enum,
        version=version,
        seed=seed_value,
        nonce=nonce_value,
        prefix=CLIENT_ORDER_ID_PREFIX,
        legacy=False,
    )


def make_execpos_client_order_id(
    *,
    intent: ClientOrderIntent | str,
    symbol: Optional[str],
    rid: Optional[str] = None,
    decision_id: Optional[str] = None,
    seed: Optional[str] = None,
    extra: Optional[str] = None,
    ts_ms: Optional[int] = None,
    max_len: int = 36,
) -> ClientOrderIdMeta:
    """
    Canonical builder for execution_position clientOrderIds.

    Thin wrapper over build_client_order_id with sensible defaults for ExecPos.
    """
    derived_seed = seed or _derive_seed(
        rid=rid,
        symbol=symbol,
        decision_id=decision_id,
        extra=extra,
        max_len=12,
    )
    return build_client_order_id(
        intent=intent,
        rid=rid,
        symbol=symbol,
        decision_id=decision_id,
        seed=derived_seed,
        extra=extra,
        ts_ms=ts_ms,
        max_len=max_len,
    )


def build_bracket_client_ids(
    *,
    rid: Optional[str],
    symbol: Optional[str],
    decision_id: Optional[str] = None,
    extra: Optional[str] = None,
    ts_ms: Optional[int] = None,
    max_len: int = 36,
) -> Tuple[ClientOrderIdMeta, ClientOrderIdMeta, ClientOrderIdMeta]:
    """Create (entry, SL, TP) ids that share the same bundle key."""

    shared_seed = _derive_seed(
        rid=rid,
        symbol=symbol,
        decision_id=decision_id,
        extra=extra,
        max_len=12,
    )
    entry = build_client_order_id(
        intent=ClientOrderIntent.ENTRY,
        rid=rid,
        symbol=symbol,
        decision_id=decision_id,
        seed=shared_seed,
        extra=extra,
        ts_ms=ts_ms,
        max_len=max_len,
    )
    sl = build_client_order_id(
        intent=ClientOrderIntent.STOP_LOSS,
        rid=rid,
        symbol=symbol,
        decision_id=decision_id,
        seed=shared_seed,
        extra=f"{extra or ''}#sl",
        ts_ms=ts_ms,
        max_len=max_len,
    )
    tp = build_client_order_id(
        intent=ClientOrderIntent.TAKE_PROFIT,
        rid=rid,
        symbol=symbol,
        decision_id=decision_id,
        seed=shared_seed,
        extra=f"{extra or ''}#tp",
        ts_ms=ts_ms,
        max_len=max_len,
    )
    return entry, sl, tp


def parse_client_order_id(client_order_id: Optional[str]) -> Optional[ClientOrderIdMeta]:
    """Decode clientOrderId into structured metadata (supports legacy fallbacks)."""

    if not client_order_id:
        return None
    cid = str(client_order_id).strip()
    if not cid:
        return None

    lowered = cid.lower()
    match = CLIENT_ORDER_ID_REGEX.match(cid)
    if match:
        token = match.group("intent").lower()
        intent_str = CLIENT_ORDER_ID_TOKEN_MAP.get(token, "unknown")
        intent = ClientOrderIntent(intent_str)
        prefix = match.group("prefix")
        version = prefix.replace(CLIENT_ORDER_ID_DOMAIN, "", 1)
        seed_value = match.group("seed")
        nonce_value = match.group("nonce")
        return ClientOrderIdMeta(
            raw=cid,
            intent=intent,
            version=version,
            seed=seed_value,
            nonce=nonce_value,
            prefix=prefix,
            legacy=False,
        )

    if lowered.endswith("_sl"):
        base = cid[:-3]
        return ClientOrderIdMeta(
            raw=cid,
            intent=ClientOrderIntent.STOP_LOSS,
            version="legacy",
            seed=base,
            nonce="legacy",
            prefix="legacy",
            legacy=True,
        )
    if lowered.endswith("_tp"):
        base = cid[:-3]
        return ClientOrderIdMeta(
            raw=cid,
            intent=ClientOrderIntent.TAKE_PROFIT,
            version="legacy",
            seed=base,
            nonce="legacy",
            prefix="legacy",
            legacy=True,
        )
    if lowered.startswith("entry"):
        return ClientOrderIdMeta(
            raw=cid,
            intent=ClientOrderIntent.ENTRY,
            version="legacy",
            seed=cid,
            nonce="legacy",
            prefix="legacy",
            legacy=True,
        )
    if lowered.startswith("close"):
        return ClientOrderIdMeta(
            raw=cid,
            intent=ClientOrderIntent.CLOSE,
            version="legacy",
            seed=cid,
            nonce="legacy",
            prefix="legacy",
            legacy=True,
        )

    # Handle SL- prefix (legacy/test)
    if lowered.startswith("sl-"):
        return ClientOrderIdMeta(
            raw=cid,
            intent=ClientOrderIntent.STOP_LOSS,
            version="legacy",
            seed=cid,
            nonce="legacy",
            prefix="legacy",
            legacy=True,
        )

    # Handle TP- prefix (legacy/test)
    if lowered.startswith("tp-"):
        return ClientOrderIdMeta(
            raw=cid,
            intent=ClientOrderIntent.TAKE_PROFIT,
            version="legacy",
            seed=cid,
            nonce="legacy",
            prefix="legacy",
            legacy=True,
        )

    return ClientOrderIdMeta(
        raw=cid,
        intent=ClientOrderIntent.UNKNOWN,
        version="legacy",
        seed="",
        nonce="",
        prefix="legacy",
        legacy=True,
    )


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
    tp_bps_f = _to_float(tp_bps, name="tp_bps")
    sl_bps_f = _to_float(sl_bps, name="sl_bps")

    s = (side or "").upper()
    if s == "LONG":
        tp = m * (1.0 + tp_bps_f / BPS_DIVISOR)
        sl = m * (1.0 - sl_bps_f / BPS_DIVISOR)
        # kвантування: TP ↑, SL ↓
        if tick_size and tick_size > 0:
            tp = _round_to_tick(tp, tick_size, mode="ceil")
            sl = _round_to_tick(sl, tick_size, mode="floor")
        # анти-2021
        if not (sl < m and tp > m):
            raise ValueError(
                f"anti-2021 (LONG) failed: sl={sl}, tp={tp}, mark={m}")
    elif s == "SHORT":
        tp = m * (1.0 - tp_bps_f / BPS_DIVISOR)
        sl = m * (1.0 + sl_bps_f / BPS_DIVISOR)
        if tick_size and tick_size > 0:
            tp = _round_to_tick(tp, tick_size, mode="floor")
            sl = _round_to_tick(sl, tick_size, mode="ceil")
        if not (sl > m and tp < m):
            raise ValueError(
                f"anti-2021 (SHORT) failed: sl={sl}, tp={tp}, mark={m}")
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
            raise ValueError(
                f"anti-2021 (LONG) failed: SL({sl_f}) >= mark({m})")
        if tp_f <= m:
            raise ValueError(
                f"anti-2021 (LONG) failed: TP({tp_f}) <= mark({m})")
    elif s == "SHORT":
        # SHORT: SL > mark, TP < mark
        if sl_f <= m:
            raise ValueError(
                f"anti-2021 (SHORT) failed: SL({sl_f}) <= mark({m})")
        if tp_f >= m:
            raise ValueError(
                f"anti-2021 (SHORT) failed: TP({tp_f}) >= mark({m})")
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
