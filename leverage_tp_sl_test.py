#!/usr/bin/env python3
"""
Тестовий розрахунок ордерів з різними налаштуваннями плеча та TP/SL
Базується на реальних цінах з логів системи
"""

from decimal import Decimal, ROUND_DOWN
import math


def quantize_price(price: float, tick_size: float) -> float:
    """Квантування ціни до tick_size"""
    return float(Decimal(str(price)).quantize(Decimal(str(tick_size)), rounding=ROUND_DOWN))


def quantize_quantity(qty: float, step_size: float) -> float:
    """Квантування кількості до step_size"""
    return float(Decimal(str(qty)).quantize(Decimal(str(step_size)), rounding=ROUND_DOWN))


def calculate_brackets(entry_price: float, side: str, sl_bps: float, tp_bps: float, tick_size: float):
    """Розрахунок TP/SL цін"""
    if side.upper() == "BUY":
        # Long position
        sl_price = entry_price * (1 - sl_bps / 10000)  # SL нижче
        tp_price = entry_price * (1 + tp_bps / 10000)  # TP вище
    else:
        # Short position
        sl_price = entry_price * (1 + sl_bps / 10000)  # SL вище
        tp_price = entry_price * (1 - tp_bps / 10000)  # TP нижче

    return {
        'sl_price': quantize_price(sl_price, tick_size),
        'tp_price': quantize_price(tp_price, tick_size)
    }


def calculate_position_size(equity: float, leverage: int, price: float, risk_pct: float = 0.01, step_size: float = 0.01):
    """Розрахунок розміру позиції"""
    # Доступний маржин
    margin_available = equity * risk_pct  # 1% від equity для однієї позиції

    # Розмір позиції в USD
    position_usd = margin_available * leverage

    # Кількість монет
    qty = position_usd / price

    return {
        'margin_used': margin_available,
        'position_usd': position_usd,
        'qty_raw': qty,
        'qty_quantized': quantize_quantity(qty, step_size),
        'notional': quantize_quantity(qty, step_size) * price
    }


def main():
    print("🔬 Тестовий розрахунок ордерів з різними налаштуваннями")
    print("=" * 60)

    # Реальні дані з логів
    symbol = "SOLUSDT"
    current_price = 165.47  # з логів: price=$165.4700
    equity = 2616.66  # з логів: Equity: 2616.66043263
    tick_size = 0.01
    step_size = 0.01

    print(f"📊 Параметри з логів:")
    print(f"   Символ: {symbol}")
    print(f"   Поточна ціна: ${current_price}")
    print(f"   Equity: ${equity}")
    print(f"   Tick size: {tick_size}")
    print(f"   Step size: {step_size}")
    print()

    # Поточні налаштування
    current_leverage = 125
    current_sl_bps = 50
    current_tp_bps = 100

    # Нові налаштування
    new_leverage = 75
    new_sl_bps = 37.5  # 50 * 0.75
    new_tp_bps = 75    # 100 * 0.75

    scenarios = [
        ("ПОТОЧНІ НАЛАШТУВАННЯ", current_leverage, current_sl_bps, current_tp_bps),
        ("НОВІ НАЛАШТУВАННЯ (x75, TP/SL -25%)",
         new_leverage, new_sl_bps, new_tp_bps)
    ]

    for scenario_name, leverage, sl_bps, tp_bps in scenarios:
        print(f"🎯 {scenario_name}")
        print("-" * 40)

        # Розрахунок для LONG позиції
        pos_calc = calculate_position_size(
            equity, leverage, current_price, step_size=step_size)
        brackets = calculate_brackets(
            current_price, "BUY", sl_bps, tp_bps, tick_size)

        print("📈 LONG позиція:")
        print(f"   Плече: {leverage}x")
        print(f"   Використаний маржин: ${pos_calc['margin_used']:.2f}")
        print(f"   Розмір позиції USD: ${pos_calc['position_usd']:.2f}")
        print(f"   Кількість монет: {pos_calc['qty_quantized']:.4f}")
        print(f"   SL ціна: ${brackets['sl_price']:.2f}")
        print(f"   TP ціна: ${brackets['tp_price']:.2f}")
        print()

        # Розрахунок прибутку/збитку
        qty = pos_calc['qty_quantized']
        entry_cost = qty * current_price

        sl_pnl = (brackets['sl_price'] - current_price) * qty
        tp_pnl = (brackets['tp_price'] - current_price) * qty

        # Ризик vs Нагорода
        risk = abs(sl_pnl)
        reward = abs(tp_pnl)
        rr_ratio = reward / risk if risk > 0 else 0

        print("💰 P&L розрахунок:")
        print(f"   Вартість входу: ${entry_cost:.2f}")
        print(f"   SL P&L: ${sl_pnl:.2f}")
        print(f"   TP P&L: ${tp_pnl:.2f}")
        print(f"   R:R відношення: 1:{rr_ratio:.1f}")
        print()

        print("⚖️  Risk/Reward:")
        print(f"   Ризик (SL): ${risk:.2f}")
        print(f"   Нагорода (TP): ${reward:.2f}")
        print(f"   R:R відношення: 1:{rr_ratio:.1f}")
        print()


if __name__ == "__main__":
    main()
