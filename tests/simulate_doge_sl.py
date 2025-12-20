
import yaml
import sys
from decimal import Decimal

def main():
    try:
        with open("/home/wekabeka/Музыка/Phenix/config/aurora/trading.yaml", "r") as f:
            cfg = yaml.safe_load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        return

    # Extract DOGE settings
    try:
        doge_cfg = cfg["trading"]["mean_reversion"]["assets"]["DOGEUSDT"]
        sl_pct = doge_cfg.get("sl_pct")
        print(f"Loaded DOGE Config:")
        print(f"  sl_pct: {sl_pct}")
        
        if sl_pct is None:
            print("ERROR: sl_pct is Missing!")
            return

        # Simulate
        entry_price = Decimal("0.1400")
        sl_pct_dec = Decimal(str(sl_pct))
        
        # MEAN_REVERSION strategy usually uses sl_pct for stop price calculation in Handler
        stop_price_long = entry_price * (Decimal("1") - sl_pct_dec)
        stop_price_short = entry_price * (Decimal("1") + sl_pct_dec)
        
        print(f"\nSimulation at Price {entry_price}:")
        print(f"  SL %: {sl_pct*100}%")
        print(f"  Calculated STOP (Long): {stop_price_long:.5f}")
        print(f"  Calculated STOP (Short): {stop_price_short:.5f}")
        
        # Check against user report
        user_sl = Decimal("0.1000")
        diff = abs(stop_price_long - user_sl)
        print(f"\nUser Reported SL: {user_sl}")
        print(f"Difference: {diff:.5f}")
        
        if diff < 0.01:
            print("MATCH: The config explains the 0.1000 SL.")
        else:
            print("MISMATCH: The current config acts differently from the user's observation.")
            print("Likely cause: User observation is from OLD orders/config.")

    except KeyError as e:
        print(f"Config Key Error: {e}")

if __name__ == "__main__":
    main()
