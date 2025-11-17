#!/usr/bin/env python3
"""
TEST: $40 wallet, 60x leverage, ETHUSDT, single order with TP/SL
+ MICRO variant: 0.068 ETH (10x менше)
"""

from decimal import Decimal
import json
import copy

from apps.reference.domains.execution_position.brackets_config import (
    resolve_brackets_config,
)

# ============================================================================
# КОНФІГ З config/aurora/trading.yaml
# ============================================================================

CONFIG = {
    "trading": {
        "execution": {
            "manage": {
                "brackets": {
                    "enable": True,
                    "stop_loss_bps": 50,
                    "take_profit_low_ratio": 0.6,
                    "take_profit_high_ratio": 1.0,
                }
            }
        },
        "instruments": {
            "ETHUSDT": {
                "step_size": "0.001",
                "min_notional": "10"
            }
        }
    }
}

# ============================================================================
# ПАРАМЕТРИ ТЕСТУ
# ============================================================================

WALLET = 40.0  # USD
LEVERAGE = 60  # x
SYMBOL = "ETHUSDT"
SIDE = "LONG"
MARK_PRICE = 3500.0  # Наближена поточна ціна

# ============================================================================
# РОЗРАХУНКИ
# ============================================================================


def calculate_order(wallet: float, leverage: float, mark_price: float, symbol: str, config: dict, side: str = "LONG"):
    """Розрахунок ордера"""

    # 1. Notional
    notional = wallet * leverage

    # 2. Quantity (з урахуванням step_size)
    step_size_str = (
        config["trading"]["instruments"][symbol]["step_size"]
    )
    step_size = Decimal(step_size_str)

    qty_decimal = Decimal(str(notional)) / Decimal(str(mark_price))
    # Round down до step_size
    qty_quantized = (qty_decimal / step_size).to_integral_value() * step_size

    # 3. Realisticna notional
    real_notional = float(qty_quantized) * mark_price

    # 4. SL/TP calculation
    # Resolve canonical TP/SL once for consistency across code paths
    resolved_brackets = resolve_brackets_config(config, symbol=symbol)

    # Derive high TP (prefers take_profit_high_ratio when present)
    sl_bps = float(resolved_brackets.sl_bps)
    tp_high_bps = float(resolved_brackets.tp_bps)

    # Derive low TP by disabling the high-ratio override while leaving low ratio intact
    cfg_low = copy.deepcopy(config)
    try:
        cfg_low["trading"]["execution"]["manage"]["brackets"].pop(
            "take_profit_high_ratio", None
        )
    except Exception:
        pass
    low_brackets = resolve_brackets_config(cfg_low, symbol=symbol)
    tp_low_bps = float(low_brackets.tp_bps)

    # SL price
    sl_price = mark_price * (1.0 - sl_bps / 10000.0)

    tp_low_price = mark_price * (1.0 + tp_low_bps / 10000.0)
    tp_high_price = mark_price * (1.0 + tp_high_bps / 10000.0)

    # Risk/Reward
    risk = abs(mark_price - sl_price) * float(qty_quantized)
    reward_low = abs(tp_low_price - mark_price) * float(qty_quantized)
    reward_high = abs(tp_high_price - mark_price) * float(qty_quantized)

    order_data = {
        "symbol": symbol,
        "side": side,
        "order_type": "MARKET",
        "quantity": float(qty_quantized),
        "entry_price": mark_price,
        "brackets": {
            "sl": {
                "price": float(Decimal(str(sl_price)).quantize(Decimal(str(step_size)))),
                "bps": int(sl_bps),
            },
            "tp_low": {
                "price": float(Decimal(str(tp_low_price)).quantize(Decimal(str(step_size)))),
                "bps": int(tp_low_bps),
                "ratio": float(tp_low_bps / sl_bps) if sl_bps else 0,
            },
            "tp_high": {
                "price": float(Decimal(str(tp_high_price)).quantize(Decimal(str(step_size)))),
                "bps": int(tp_high_bps),
                "ratio": float(tp_high_bps / sl_bps) if sl_bps else 0,
            }
        },
        "wallet": wallet,
        "leverage": leverage,
        "notional": real_notional,
        "risk_usd": risk,
        "reward_usd": reward_high,
        "risk_reward": {
            "low": round(reward_low / risk, 2) if risk > 0 else 0,
            "high": round(reward_high / risk, 2) if risk > 0 else 0
        }
    }

    return order_data

# ============================================================================
# ЗАПУСК
# ============================================================================


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🔧 ТЕСТ: FULL vs MICRO POSITION")
    print("=" * 70)

    # ========== FULL POSITION ==========
    print("\n" + "─" * 70)
    print("ВАРІАНТ 1: FULL POSITION")
    print("─" * 70)
    print("Config: min_position_size_usd: 10 (default)")
    print()

    order_full = calculate_order(
        wallet=WALLET,
        leverage=LEVERAGE,
        mark_price=MARK_PRICE,
        symbol=SYMBOL,
        config=CONFIG,
        side=SIDE
    )

    print(f"✅ FULL ORDER:")
    print(json.dumps(order_full, indent=2))

    # ========== MICRO POSITION ==========
    print("\n" + "─" * 70)
    print("ВАРІАНТ 2: MICRO POSITION (10x менше)")
    print("─" * 70)
    print("Config: min_position_size_usd: 1, liquidity_kappa: 0.1")
    print()

    # Micro = 10x менше
    micro_wallet = WALLET / 10  # $4

    order_micro = calculate_order(
        wallet=micro_wallet,
        leverage=LEVERAGE,
        mark_price=MARK_PRICE,
        symbol=SYMBOL,
        config=CONFIG,
        side=SIDE
    )

    print(f"✅ MICRO ORDER:")
    print(json.dumps(order_micro, indent=2))

    # ========== ПОРІВНЯННЯ ==========
    print("\n" + "=" * 70)
    print("📊 ПОРІВНЯННЯ")
    print("=" * 70)

    print(f"""
{'ПОЗИЦІЯ':<40} {'FULL':<30} {'MICRO':<30}
{'═' * 100}
{'Wallet USD':<40} ${order_full['wallet']:<29.2f} ${order_micro['wallet']:<29.2f}
{'Leverage':<40} {order_full['leverage']:<29}x {order_micro['leverage']:<29}x
{'Notional USD':<40} ${order_full['notional']:<29.2f} ${order_micro['notional']:<29.2f}
{'Кількість ETH':<40} {order_full['quantity']:<29} {order_micro['quantity']:<29}
{'Entry Price USD':<40} ${order_full['entry_price']:<29.2f} ${order_micro['entry_price']:<29.2f}

{'PRICES (TP/SL)':<40} {'─' * 60}
{'SL Price':<40} ${order_full['brackets']['sl']['price']:<29.2f} ${order_micro['brackets']['sl']['price']:<29.2f}
{'  └─ Distance from Entry':<40} {(order_full['entry_price'] - order_full['brackets']['sl']['price']):<29.2f} bps {(order_micro['entry_price'] - order_micro['brackets']['sl']['price']):<29.2f} bps
{'TP LOW Price (k₁≈0.6)':<40} ${order_full['brackets']['tp_low']['price']:<29.2f} ${order_micro['brackets']['tp_low']['price']:<29.2f}
{'  └─ Distance from Entry':<40} {(order_full['brackets']['tp_low']['price'] - order_full['entry_price']):<29.2f} bps {(order_micro['brackets']['tp_low']['price'] - order_micro['entry_price']):<29.2f} bps
{'TP HIGH Price (k₂≈1.0)':<40} ${order_full['brackets']['tp_high']['price']:<29.2f} ${order_micro['brackets']['tp_high']['price']:<29.2f}
{'  └─ Distance from Entry':<40} {(order_full['brackets']['tp_high']['price'] - order_full['entry_price']):<29.2f} bps {(order_micro['brackets']['tp_high']['price'] - order_micro['entry_price']):<29.2f} bps

{'P&L (PROFIT/LOSS)':<40} {'─' * 60}
{'❌ RISK at SL (Loss USD)':<40} ${order_full['risk_usd']:<29.2f} ${order_micro['risk_usd']:<29.2f}
{'  └─ % of Wallet':<40} {(order_full['risk_usd']/order_full['wallet']*100):<29.2f}% {(order_micro['risk_usd']/order_micro['wallet']*100):<29.2f}%
{'✅ PROFIT at TP LOW (USD)':<40} ${(order_full['brackets']['tp_low']['price'] - order_full['entry_price']) * order_full['quantity']:<29.2f} ${(order_micro['brackets']['tp_low']['price'] - order_micro['entry_price']) * order_micro['quantity']:<29.2f}
{'  └─ % of Wallet':<40} {((order_full['brackets']['tp_low']['price'] - order_full['entry_price']) * order_full['quantity'] / order_full['wallet'] * 100):<29.2f}% {((order_micro['brackets']['tp_low']['price'] - order_micro['entry_price']) * order_micro['quantity'] / order_micro['wallet'] * 100):<29.2f}%
{'✅ PROFIT at TP HIGH (USD)':<40} ${order_full['reward_usd']:<29.2f} ${order_micro['reward_usd']:<29.2f}
{'  └─ % of Wallet':<40} {(order_full['reward_usd']/order_full['wallet']*100):<29.2f}% {(order_micro['reward_usd']/order_micro['wallet']*100):<29.2f}%

{'RISK/REWARD RATIO':<40} {'─' * 60}
{'R:R (TP LOW / Risk)':<40} {order_full['risk_reward']['low']:<29.2f} {order_micro['risk_reward']['low']:<29.2f}
{'R:R (TP HIGH / Risk)':<40} {order_full['risk_reward']['high']:<29.2f} {order_micro['risk_reward']['high']:<29.2f}
""")

    # ========== КОНФІГ ==========
    print("=" * 70)
    print("🔧 КОНФІГ ДЛЯ MICRO ПОЗИЦІЙ")
    print("=" * 70)
    print("""
Файл: config/aurora/trading.yaml

БУЛО (FULL):
─────────────────────────────────────
decision:
  position_sizing:
    min_position_size_usd: 10
    liquidity_kappa: 1.0

СТАЄ (MICRO):
─────────────────────────────────────
decision:
  position_sizing:
    min_position_size_usd: 1          # ← ЗМІНИТИ з 10 на 1
    liquidity_kappa: 0.1              # ← ЗМІНИТИ з 1.0 на 0.1

РЕЗУЛЬТАТ:
─────────────────────────────────────
✅ Система дозволятиме позиції від $1 (замість $10)
✅ Капсул по liquidity буде в 10 разів менше
✅ Позиції будуть мікро-розміру (0.068 ETH замість 0.686)
""")
