
import sys
import decimal
from decimal import Decimal

# Add project root to path
sys.path.append("/home/wekabeka/Музыка/Phenix")

from apps.reference.domains.decision_making.sizing_margin_first import (
    compute_notional_target,
    compute_qty,
    validate_exchange_constraints,
)

def verify_sizing():
    # Scenario
    equity = Decimal("1000.00")
    margin_pct = Decimal("0.09")
    target_leverage = 50
    min_notional = Decimal("100.00")
    price = Decimal("27000.00")
    step_size = Decimal("0.001")
    min_qty = Decimal("0.001")

    print(f"--- SCENARIO ---")
    print(f"Equity: ${equity}")
    print(f"Margin %: {margin_pct}")
    print(f"Leverage: {target_leverage}x")
    print(f"Min Notional: ${min_notional}")
    print(f"Price: ${price}")
    print(f"----------------")

    # 1. Compute Margin & Notional
    print("\n[Step 1] compute_notional_target...")
    margin_usdt, notional_target = compute_notional_target(
        equity=equity,
        margin_pct=margin_pct,
        leverage=target_leverage,
    )
    print(f"  Result Margin USDT: ${margin_usdt}")
    print(f"  Result Notional Target: ${notional_target}")
    
    # 2. Compute Qty
    print("\n[Step 2] compute_qty...")
    raw_qty, rounded_qty = compute_qty(
        notional_target=notional_target,
        price=price,
        step_size=step_size,
    )
    print(f"  Raw Qty: {raw_qty}")
    print(f"  Rounded Qty: {rounded_qty}")

    # 3. Calculate Final Order Notional
    final_order_notional = rounded_qty * price
    print(f"  Final Order Notional: ${final_order_notional}")

    # 4. Check Constraints
    print("\n[Step 3] validate_exchange_constraints...")
    reject_code, reason = validate_exchange_constraints(
        qty=rounded_qty,
        price=price,
        min_qty=min_qty,
        min_notional=min_notional,
    )
    
    if reject_code:
        print(f"  ❌ REJECTED: {reject_code} - {reason}")
    else:
        print(f"  ✅ ACCEPTED: Order passes constraints.")
        if final_order_notional >= min_notional:
            print(f"  Logic Check: Notional ${final_order_notional} >= Min ${min_notional}")
        else:
            print(f"  FAIL: Logic Mismatch!")

if __name__ == "__main__":
    verify_sizing()
