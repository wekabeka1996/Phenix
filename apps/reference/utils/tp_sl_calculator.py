#!/usr/bin/env python3
"""
TP/SL Calculator - Обчислюй точні ціни Take Profit і Stop Loss

Використання:
    from apps.reference.utils.tp_sl_calculator import TPSLCalculator

    calc = TPSLCalculator(entry_price=45000, sl_bps=50, side="long")
    result = calc.calculate_all(tp_low_ratio=0.6, tp_high_ratio=1.0)
"""

import argparse
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Tuple


class TPSLCalculator:
    """Калькулятор для TP/SL розрахунків"""

    def __init__(self, entry_price: float, sl_bps: int, side: str = "long"):
        """
        Args:
            entry_price: Ціна входу (entry price)
            sl_bps: Stop Loss в basis points (0.01%)
            side: "long" або "short"
        """
        self.entry = Decimal(str(entry_price))
        self.sl_bps = Decimal(str(sl_bps))
        self.side = side.lower()

        if self.side not in ["long", "short"]:
            raise ValueError("side must be 'long' or 'short'")

    def calculate_sl(self) -> Tuple[float, float]:
        """Обчисли ціну Stop Loss і дистанцію від entry"""
        multiplier = (Decimal("1") - self.sl_bps / Decimal("10000")
                      ) if self.side == "long" else (Decimal("1") + self.sl_bps / Decimal("10000"))
        sl_price = self.entry * multiplier
        distance_pct = abs((sl_price - self.entry) /
                           self.entry * Decimal("100"))

        return float(sl_price), float(distance_pct)

    def calculate_tp(self, tp_ratio: float) -> Tuple[float, float]:
        """Обчисли ціну Take Profit і дистанцію від entry"""
        tp_ratio_dec = Decimal(str(tp_ratio))
        tp_bps = self.sl_bps * tp_ratio_dec
        distance_per_bps = self.entry / Decimal("10000")
        tp_price_offset = tp_bps * distance_per_bps

        if self.side == "long":
            tp_price = self.entry + tp_price_offset
        else:
            tp_price = self.entry - tp_price_offset

        distance_pct = abs((tp_price - self.entry) /
                           self.entry * Decimal("100"))

        return float(tp_price), float(distance_pct)

    def calculate_all(self, tp_low_ratio: float = 0.6, tp_high_ratio: float = 1.0) -> Dict:
        """Обчисли всі параметри скопом"""
        sl_price, sl_dist = self.calculate_sl()
        tp_low_price, tp_low_dist = self.calculate_tp(tp_low_ratio)
        tp_high_price, tp_high_dist = self.calculate_tp(tp_high_ratio)

        # Обчисли payoff ratio
        payoff_ratio = tp_high_ratio  # Наближення: TP_bps / SL_bps

        # Обчисли кількість BPS для TP
        tp_low_bps = self.sl_bps * Decimal(str(tp_low_ratio))
        tp_high_bps = self.sl_bps * Decimal(str(tp_high_ratio))

        return {
            "entry_price": float(self.entry),
            "side": self.side,
            "stop_loss": {
                "bps": int(self.sl_bps),
                "price": sl_price,
                "distance_pct": round(sl_dist, 4),
                "description": f"Stop Loss на {sl_dist:.2f}% {'нижче' if self.side == 'long' else 'вище'} entry"
            },
            "take_profit_low": {
                "bps": int(tp_low_bps),
                "ratio": tp_low_ratio,
                "price": tp_low_price,
                "distance_pct": round(tp_low_dist, 4),
                "description": f"Take Profit (low) на {tp_low_dist:.2f}% {'вище' if self.side == 'long' else 'нижче'} entry"
            },
            "take_profit_high": {
                "bps": int(tp_high_bps),
                "ratio": tp_high_ratio,
                "price": tp_high_price,
                "distance_pct": round(tp_high_dist, 4),
                "description": f"Take Profit (high) на {tp_high_dist:.2f}% {'вище' if self.side == 'long' else 'нижче'} entry"
            },
            "payoff_ratio": payoff_ratio,
            "risk_reward": {
                "low": round(tp_low_ratio, 2),
                "high": round(tp_high_ratio, 2),
                "description": f"Risk/Reward від {tp_low_ratio:.2f} до {tp_high_ratio:.2f}"
            }
        }


def format_result(result: Dict) -> str:
    """Форматуй результати для виводу"""
    output = []
    output.append("\n" + "="*60)
    output.append("📊 TP/SL CALCULATION RESULT")
    output.append("="*60)

    output.append(
        f"\n🎯 ENTRY: {result['entry_price']} ({result['side'].upper()})")

    output.append(f"\n🛑 STOP LOSS (SL)")
    output.append(f"   Bps: {result['stop_loss']['bps']}")
    output.append(f"   Price: {result['stop_loss']['price']:.8f}")
    output.append(f"   Distance: {result['stop_loss']['distance_pct']:.4f}%")
    output.append(f"   Note: {result['stop_loss']['description']}")

    output.append(
        f"\n📈 TAKE PROFIT LOW (k₁={result['take_profit_low']['ratio']})")
    output.append(f"   Bps: {result['take_profit_low']['bps']}")
    output.append(f"   Price: {result['take_profit_low']['price']:.8f}")
    output.append(
        f"   Distance: {result['take_profit_low']['distance_pct']:.4f}%")
    output.append(f"   Note: {result['take_profit_low']['description']}")

    output.append(
        f"\n📈 TAKE PROFIT HIGH (k₂={result['take_profit_high']['ratio']})")
    output.append(f"   Bps: {result['take_profit_high']['bps']}")
    output.append(f"   Price: {result['take_profit_high']['price']:.8f}")
    output.append(
        f"   Distance: {result['take_profit_high']['distance_pct']:.4f}%")
    output.append(f"   Note: {result['take_profit_high']['description']}")

    output.append(f"\n⚖️ PAYOFF RATIO")
    output.append(f"   Ratio: {result['payoff_ratio']}")
    output.append(
        f"   Range: {result['risk_reward']['low']} to {result['risk_reward']['high']}")
    output.append(f"   Note: {result['risk_reward']['description']}")

    output.append("\n" + "="*60 + "\n")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="TP/SL Calculator для трейдинг системи",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Приклади:

  # BTC LONG з SL=50bps, TP_low=0.6, TP_high=1.0
  python -m apps.reference.utils.tp_sl_calculator --entry 45000 --sl-bps 50 --tp-low 0.6 --tp-high 1.0 --side long

  # ETH SHORT з SL=75bps, TP_low=0.5, TP_high=1.25
  python -m apps.reference.utils.tp_sl_calculator --entry 3.5 --sl-bps 75 --tp-low 0.5 --tp-high 1.25 --side short

  # Мікро-ризик LONG (SL=20bps)
  python -m apps.reference.utils.tp_sl_calculator --entry 45000 --sl-bps 20 --side long

  # Агресивний LONG (SL=100bps)
  python -m apps.reference.utils.tp_sl_calculator --entry 45000 --sl-bps 100 --tp-low 0.4 --tp-high 1.5 --side long

  # JSON вивід (для скриптів)
  python -m apps.reference.utils.tp_sl_calculator --entry 45000 --sl-bps 50 --json
        """
    )

    parser.add_argument("--entry", type=float,
                        required=True, help="Entry price")
    parser.add_argument("--sl-bps", type=int, default=50,
                        help="Stop Loss в basis points (default: 50)")
    parser.add_argument("--tp-low", type=float, default=0.6,
                        help="TP low ratio k₁ (default: 0.6)")
    parser.add_argument("--tp-high", type=float, default=1.0,
                        help="TP high ratio k₂ (default: 1.0)")
    parser.add_argument("--side", type=str, default="long",
                        choices=["long", "short"], help="Side (default: long)")
    parser.add_argument("--json", action="store_true", help="JSON вивід")

    args = parser.parse_args()

    calc = TPSLCalculator(args.entry, args.sl_bps, args.side)
    result = calc.calculate_all(args.tp_low, args.tp_high)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_result(result))


if __name__ == "__main__":
    main()
