#!/usr/bin/env python3
"""
TP/SL Calculator CLI (legacy wrapper) delegating to canonical tp_sl_math.
"""

import argparse
import json
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict

from apps.reference.utils.tp_sl_math import TpslParams, TpslConstraints, compute_tpsl_levels


class TPSLCalculator:
    """Wrapper around canonical TP/SL math for CLI usage."""

    def __init__(self, entry_price: float, sl_bps: int, side: str = "long"):
        self.entry = Decimal(str(entry_price))
        self.sl_bps = Decimal(str(sl_bps))
        self.side = side.lower()
        if self.side not in ["long", "short"]:
            raise ValueError("side must be 'long' or 'short'")

    def _constraints(self) -> TpslConstraints:
        return TpslConstraints(
            tick_size=Decimal("0.00000001"),
            min_price=Decimal("0"),
        )

    def calculate_sl(self):
        params = TpslParams(
            side="LONG" if self.side == "long" else "SHORT",
            avg_entry_price=self.entry,
            position_qty=Decimal("1"),
            sl_pct=self.sl_bps / Decimal("10000"),
            tp_rr=Decimal("1"),
        )
        levels = compute_tpsl_levels(params, self._constraints())
        dist_pct = abs((levels.sl_price - self.entry) / self.entry * Decimal("100"))
        return float(levels.sl_price), float(dist_pct)

    def calculate_tp(self, tp_ratio: float):
        params = TpslParams(
            side="LONG" if self.side == "long" else "SHORT",
            avg_entry_price=self.entry,
            position_qty=Decimal("1"),
            sl_pct=self.sl_bps / Decimal("10000"),
            tp_rr=Decimal(str(tp_ratio)),
        )
        levels = compute_tpsl_levels(params, self._constraints())
        dist_pct = abs((levels.tp_price - self.entry) / self.entry * Decimal("100"))
        return float(levels.tp_price), float(dist_pct)

    def calculate_all(self, tp_low_ratio: float = 0.6, tp_high_ratio: float = 1.0) -> Dict:
        sl_price, sl_dist = self.calculate_sl()
        tp_low_price, tp_low_dist = self.calculate_tp(tp_low_ratio)
        tp_high_price, tp_high_dist = self.calculate_tp(tp_high_ratio)

        payoff_ratio = tp_high_ratio
        tp_low_bps = self.sl_bps * Decimal(str(tp_low_ratio))
        tp_high_bps = self.sl_bps * Decimal(str(tp_high_ratio))

        return {
            "entry_price": float(self.entry),
            "side": self.side,
            "stop_loss": {
                "bps": int(self.sl_bps),
                "price": sl_price,
                "distance_pct": round(sl_dist, 4),
                "description": f"Stop Loss {sl_dist:.2f}% {'below' if self.side == 'long' else 'above'} entry"
            },
            "take_profit_low": {
                "bps": int(tp_low_bps),
                "ratio": tp_low_ratio,
                "price": tp_low_price,
                "distance_pct": round(tp_low_dist, 4),
                "description": f"Take Profit (low) {tp_low_dist:.2f}% {'above' if self.side == 'long' else 'below'} entry"
            },
            "take_profit_high": {
                "bps": int(tp_high_bps),
                "ratio": tp_high_ratio,
                "price": tp_high_price,
                "distance_pct": round(tp_high_dist, 4),
                "description": f"Take Profit (high) {tp_high_dist:.2f}% {'above' if self.side == 'long' else 'below'} entry"
            },
            "payoff_ratio": payoff_ratio,
            "risk_reward": {
                "low": round(tp_low_ratio, 2),
                "high": round(tp_high_ratio, 2),
                "description": f"Risk/Reward {tp_low_ratio:.2f} to {tp_high_ratio:.2f}"
            }
        }


def format_result(result: Dict) -> str:
    output = []
    output.append("\n" + "="*60)
    output.append("TP/SL CALCULATION RESULT")
    output.append("="*60)

    output.append(
        f"\nENTRY: {result['entry_price']} ({result['side'].upper()})")

    output.append(f"\nSTOP LOSS (SL)")
    output.append(f"   Bps: {result['stop_loss']['bps']}")
    output.append(f"   Price: {result['stop_loss']['price']:.8f}")
    output.append(f"   Distance: {result['stop_loss']['distance_pct']:.4f}%")
    output.append(f"   Note: {result['stop_loss']['description']}")

    output.append(
        f"\nTAKE PROFIT LOW (k={result['take_profit_low']['ratio']})")
    output.append(f"   Bps: {result['take_profit_low']['bps']}")
    output.append(f"   Price: {result['take_profit_low']['price']:.8f}")
    output.append(
        f"   Distance: {result['take_profit_low']['distance_pct']:.4f}%")
    output.append(f"   Note: {result['take_profit_low']['description']}")

    output.append(
        f"\nTAKE PROFIT HIGH (k={result['take_profit_high']['ratio']})")
    output.append(f"   Bps: {result['take_profit_high']['bps']}")
    output.append(f"   Price: {result['take_profit_high']['price']:.8f}")
    output.append(
        f"   Distance: {result['take_profit_high']['distance_pct']:.4f}%")
    output.append(f"   Note: {result['take_profit_high']['description']}")

    output.append(f"\nPAYOFF RATIO")
    output.append(f"   Ratio: {result['payoff_ratio']}")
    output.append(
        f"   Range: {result['risk_reward']['low']} to {result['risk_reward']['high']}")
    output.append(f"   Note: {result['risk_reward']['description']}")

    output.append("\n" + "="*60 + "\n")

    return "\n".join(output)


def main():
    parser = argparse.ArgumentParser(
        description="TP/SL Calculator CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:

  python -m apps.reference.utils.tp_sl_calculator --entry 45000 --sl-bps 50 --tp-low 0.6 --tp-high 1.0 --side long
  python -m apps.reference.utils.tp_sl_calculator --entry 3.5 --sl-bps 75 --tp-low 0.5 --tp-high 1.25 --side short
  python -m apps.reference.utils.tp_sl_calculator --entry 45000 --sl-bps 20 --side long
  python -m apps.reference.utils.tp_sl_calculator --entry 45000 --sl-bps 100 --tp-low 0.4 --tp-high 1.5 --side long
  python -m apps.reference.utils.tp_sl_calculator --entry 45000 --sl-bps 50 --json
        """
    )

    parser.add_argument("--entry", type=float,
                        required=True, help="Entry price")
    parser.add_argument("--sl-bps", type=int, default=50,
                        help="Stop Loss in basis points (default: 50)")
    parser.add_argument("--tp-low", type=float, default=0.6,
                        help="TP low ratio k (default: 0.6)")
    parser.add_argument("--tp-high", type=float, default=1.0,
                        help="TP high ratio k (default: 1.0)")
    parser.add_argument("--side", type=str, default="long",
                        choices=["long", "short"], help="Side (default: long)")
    parser.add_argument("--json", action="store_true", help="Output JSON")

    args = parser.parse_args()

    calc = TPSLCalculator(args.entry, args.sl_bps, args.side)
    result = calc.calculate_all(args.tp_low, args.tp_high)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(format_result(result))


if __name__ == "__main__":
    main()
