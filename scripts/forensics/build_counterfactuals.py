import os
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta, timezone

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
REPORTS_DIR = ROOT_DIR / "reports"
DATA_DIR = ROOT_DIR / "data" / "recorder"

def parse_ts(ts_str):
    try:
        return pd.to_datetime(ts_str, utc=True)
    except:
        return None

def find_ohlcv_file(ts: datetime, symbol: str) -> Path:
    date_str = ts.strftime("%Y-%m-%d")
    expected_path = DATA_DIR / date_str / f"{symbol}_180.csv"
    if expected_path.exists():
        return expected_path
    
    # Check surrounding days if edge
    prev_date = (ts - timedelta(days=1)).strftime("%Y-%m-%d")
    expected_path = DATA_DIR / prev_date / f"{symbol}_180.csv"
    if expected_path.exists():
         return expected_path
         
    return None

def compute_excursion(symbol, intent_ts, side, intent_price, window_minutes=45):
    filepath = find_ohlcv_file(intent_ts, symbol)
    if not filepath:
        return None, None, None, "missing_data"

    try:
        df = pd.read_csv(filepath)
        df['dt'] = pd.to_datetime(df['datetime'], utc=True)
        
        # Filter window
        end_ts = intent_ts + timedelta(minutes=window_minutes)
        window = df[(df['dt'] >= intent_ts) & (df['dt'] <= end_ts)]
        
        if window.empty:
            return None, None, None, "missing_window"
            
        real_intent_price = intent_price
        if real_intent_price == 0.0:
            # Fallback to the opening price of the first bar in the window
            real_intent_price = window.iloc[0]['open']
            
        max_high = window['high'].max()
        min_low = window['low'].min()
        
        # Max Favorable Excursion vs Max Adverse Excursion
        if side.upper() == 'BUY':
            mfe_pct = (max_high - real_intent_price) / real_intent_price * 100
            mae_pct = (min_low - real_intent_price) / real_intent_price * 100
        else:
            mfe_pct = (real_intent_price - min_low) / real_intent_price * 100
            mae_pct = (real_intent_price - max_high) / real_intent_price * 100
            
        # Classification
        # Suppose a 2x stop strategy, e.g., if price adverse goes > 0.5%, it's "saved", but if MFE > 0.5%, it's "missed profit".
        if mae_pct < -0.4 and mfe_pct < 0.4:
            classification = "Saved Capital"
        elif mfe_pct > 0.4 and mae_pct > -0.4:
            classification = "Missed Profit"
        elif mae_pct < -0.4 and mfe_pct > 0.4:
            classification = "Stopped Out Early / Whipsaw"
        else:
            classification = "Indeterminate / Flat"
            
        return mfe_pct, mae_pct, max_high if side.upper() == 'BUY' else min_low, classification
        
    except Exception as e:
        return None, None, None, f"error_{e}"

def main():
    print("--> Starting Counterfactual Analysis for Rejected Attempts...")
    rejects_path = REPORTS_DIR / "rejected_attempts_master.csv"
    if not rejects_path.exists():
        print("Missing rejects file!")
        return

    df = pd.read_csv(rejects_path)
    
    # We only care about actual rejections, not unlinked timeouts
    # Let's filter out `timeout_non_fill` if they are unlinked
    mask = df['outcome'].isin(['decision_rejected', 'execution_guard_blocked', 'strategy_blocked', 'order_rejected'])
    df_eval = df[mask].copy()
    
    print(f"Processing {len(df_eval)} rejected intents...")
    
    results = []
    
    for idx, row in df_eval.iterrows():
        ts = parse_ts(row['intent_ts'])
        if not ts:
            continue
            
        mfe, mae, extremum, cls = compute_excursion(
            row['symbol'], ts, row['side'], float(row['intent_price'])
        )
        
        r = row.to_dict()
        r['mfe_pct'] = mfe if mfe else 0.0
        r['mae_pct'] = mae if mae else 0.0
        r['excursion_classification'] = cls
        results.append(r)
        
    out_df = pd.DataFrame(results)
    out_path = REPORTS_DIR / "rejected_counterfactuals.csv"
    out_df.to_csv(out_path, index=False)
    
    print(f"--> Done! Total counterfactuals processed: {len(results)}")
    
    print("\nSummary by Classification:")
    if 'excursion_classification' in out_df:
        print(out_df.groupby('excursion_classification').size())
    else:
        print("No classified rows produced.")

if __name__ == "__main__":
    main()
