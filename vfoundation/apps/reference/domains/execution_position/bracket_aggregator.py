from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Literal


PositionSide = Literal["LONG", "SHORT"]


@dataclass(frozen=True)
class AggregatedOcoRiskConfig:
    """
    Логічний контракт ризик-параметрів для Aggregated OCO v1.

    sl_pct:
        Відстань до стоп-лосу в частках від ціни (0.01 = 1%).
    tp_rr:
        Відношення reward/risk. TP відстань = sl_pct * tp_rr.
    """

    sl_pct: Decimal
    tp_rr: Decimal


@dataclass(frozen=True)
class InstrumentPriceConstraints:
    """
    Мінімальний набір обмежень по ціні інструменту, який потрібен для
    коректного розрахунку TP/SL.

    tick_size:
        Крок ціни (Binance tick size).
    min_price:
        Мінімально допустима ціна для ордерів по інструменту.
    """

    tick_size: Decimal
    min_price: Decimal


@dataclass(frozen=True)
class AggregatedBracketLevels:
    """
    Результуючі рівні TP/SL для aggregated-позиції.

    tp_price, sl_price:
        Ціни, приведені до tick_size та min_price.
    why:
        Коротке XAI-пояснення (≤80 символів).
    """

    tp_price: Decimal
    sl_price: Decimal
    why: str


class AggregatedOcoError(ValueError):
    """Базова помилка для Aggregated OCO розрахунків."""


def compute_aggregated_brackets(
    position_amt: Decimal,
    avg_entry_price: Decimal,
    side: PositionSide,
    risk_cfg: AggregatedOcoRiskConfig,
    constraints: InstrumentPriceConstraints,
    why: str = "agg_oco_v1_from_pct_rr",
) -> AggregatedBracketLevels:
    """
    Обчислює aggregated TP/SL для позиції за простою моделлю:
    - SL на відстані sl_pct від ціни входу;
    - TP на відстані sl_pct * tp_rr від ціни входу.

    Для LONG:
        sl = price * (1 - sl_pct)
        tp = price * (1 + sl_pct * tp_rr)

    Для SHORT:
        sl = price * (1 + sl_pct)
        tp = price * (1 - sl_pct * tp_rr)

    Далі ціни округлюються по tick_size (ROUND_DOWN) і не опускаються нижче min_price.

    ПРИМІТКА:
        Цей модуль НЕ знає нічого про:
        - Binance-адаптер;
        - OrderGuardian;
        - FSM.
        Він оперує тільки числами та простими DTO.
    """
    _validate_inputs(position_amt, avg_entry_price,
                     side, risk_cfg, constraints)

    sl_pct = risk_cfg.sl_pct
    tp_rr = risk_cfg.tp_rr

    if side == "LONG":
        raw_sl = avg_entry_price * (Decimal("1") - sl_pct)
        raw_tp = avg_entry_price * (Decimal("1") + sl_pct * tp_rr)
    elif side == "SHORT":
        raw_sl = avg_entry_price * (Decimal("1") + sl_pct)
        raw_tp = avg_entry_price * (Decimal("1") - sl_pct * tp_rr)
    else:
        # Теоретично не має статись через тип PositionSide, але лишаємо перевірку.
        raise AggregatedOcoError(f"Unsupported side: {side!r}")

    sl_price = _apply_price_constraints(raw_sl, constraints)
    tp_price = _apply_price_constraints(raw_tp, constraints)

    # XAI: гарантуємо довжину why ≤ 80 символів
    safe_why = why if len(why) <= 80 else why[:80]

    return AggregatedBracketLevels(
        tp_price=tp_price,
        sl_price=sl_price,
        why=safe_why,
    )


def _validate_inputs(
    position_amt: Decimal,
    avg_entry_price: Decimal,
    side: PositionSide,
    risk_cfg: AggregatedOcoRiskConfig,
    constraints: InstrumentPriceConstraints,
) -> None:
    if position_amt <= 0:
        raise AggregatedOcoError("position_amt must be > 0")

    if avg_entry_price <= 0:
        raise AggregatedOcoError("avg_entry_price must be > 0")

    if risk_cfg.sl_pct <= 0:
        raise AggregatedOcoError("risk_cfg.sl_pct must be > 0")

    if risk_cfg.tp_rr <= 0:
        raise AggregatedOcoError("risk_cfg.tp_rr must be > 0")

    if constraints.tick_size <= 0:
        raise AggregatedOcoError("constraints.tick_size must be > 0")

    if constraints.min_price <= 0:
        raise AggregatedOcoError("constraints.min_price must be > 0")

    if side not in ("LONG", "SHORT"):
        raise AggregatedOcoError(f"Unsupported side: {side!r}")


def _apply_price_constraints(
    raw_price: Decimal,
    constraints: InstrumentPriceConstraints,
) -> Decimal:
    """
    Приводить ціну до:
    - не нижче min_price;
    - кратної tick_size (ROUND_DOWN).
    """
    if raw_price <= 0:
        raise AggregatedOcoError("raw_price must be > 0 before constraints")

    price = raw_price
    if price < constraints.min_price:
        price = constraints.min_price

    return _round_down_to_tick(price, constraints.tick_size)


def _round_down_to_tick(price: Decimal, tick_size: Decimal) -> Decimal:
    """
    Округлення ціни вниз до найближчого кроку tick_size.

    Використовуємо ROUND_DOWN як просту та детерміновану стратегію:
    - для LONG SL це трохи збільшує ризик (на один tick),
      але гарантує, що ціна не вийде за межі біржових правил;
    - для TP це трохи «притягує» ціль ближче до поточної ціни,
      що fail-closed по відношенню до нереалізованого профіту.
    """
    ticks = (price / tick_size).to_integral_value(rounding=ROUND_DOWN)
    return ticks * tick_size
