import json
import os
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Config
DATA_RECORDER_DIR = Path("data/recorder")
TP_BPS = 80
SL_BPS = 40
MAX_HOLD_MINUTES = 999999  # Disable timeout as per user request
NOTIONAL_USD = 5000

def load_market_data(symbol, start_ts_ms):
    # Convert ms to date
    dt = datetime.fromtimestamp(start_ts_ms / 1000.0, tz=timezone.utc)
    date_str = dt.strftime("%Y-%m-%d")
    
    # Try multiple timeframes, preference for 180 (3m) or 300 (5m)
    for tf in [180, 300]:
        fpath = DATA_RECORDER_DIR / date_str / f"{symbol}_{tf}.csv"
        if fpath.exists():
            df = pd.read_csv(fpath)
            # Find the index of the bar containing or following start_ts_ms
            # The recorder usually has open_time or similar
            # Let's check headers first in the actual loop
            return df, fpath
    return None, None

def simulate_trade(symbol, side, entry_price, entry_ts_ms):
    df, fpath = load_market_data(symbol, entry_ts_ms)
    if df is None:
        return "NO_DATA", 0.0, 0
    
    # Identify time column - usually 'timestamp' or 'open_time'
    time_col = 'timestamp' if 'timestamp' in df.columns else 'open_time'
    if time_col not in df.columns:
        # Try finding anything with 'time'
        time_cols = [c for c in df.columns if 'time' in c.lower()]
        if time_cols: time_col = time_cols[0]
        else: return "NO_TIME_COL", 0.0, 0

    # Filter for bars after entry
    df[time_col] = pd.to_numeric(df[time_col], errors='coerce')
    post_entry = df[df[time_col] >= entry_ts_ms].sort_values(by=time_col)
    if post_entry.empty:
        return "NO_FUTURE_BARS", 0.0, 0

    tp_price = entry_price * (1 + TP_BPS/10000.0) if side == 'BUY' else entry_price * (1 - TP_BPS/10000.0)
    sl_price = entry_price * (1 - SL_BPS/10000.0) if side == 'BUY' else entry_price * (1 + SL_BPS/10000.0)
    
    bars_held = 0
    for idx, row in post_entry.iterrows():
        bars_held += 1
        high = row['high']
        low = row['low']
        close = row['close']
        
        if side == 'BUY':
            if high >= tp_price:
                return "TP", (tp_price / entry_price - 1) * 100, bars_held
            if low <= sl_price:
                return "SL", (sl_price / entry_price - 1) * 100, bars_held
        else: # SELL
            if low <= tp_price:
                return "TP", (entry_price / tp_price - 1) * 100, bars_held
            if high >= sl_price:
                return "SL", (entry_price / sl_price - 1) * 100, bars_held
        
        # Timeout
        if bars_held * (post_entry.iloc[1][time_col] - post_entry.iloc[0][time_col]) / 1000.0 > MAX_HOLD_MINUTES * 60:
            return "TIMEOUT", (close / entry_price - 1 if side == 'BUY' else entry_price / close - 1) * 100, bars_held
            
    return "OPEN", (post_entry.iloc[-1]['close'] / entry_price - 1 if side == 'BUY' else entry_price / post_entry.iloc[-1]['close'] - 1) * 100, bars_held

def main():
    log_path = "logs/order_log_v1.jsonl"
    results = []
    
    with open(log_path, 'r') as f:
        for line in f:
            event = json.loads(line)
            if event.get('event_type') == 'DECISION_INTENT_REJECTED':
                symbol = event.get('symbol')
                side = event.get('side')
                ts = event.get('timestamp')
                # Price is often missing in rejection, need to find it from recorder at that time
                
                # Load data to get entry price
                df, _ = load_market_data(symbol, ts)
                if df is not None:
                    time_cols = [c for c in df.columns if 'time' in c.lower()]
                    if not time_cols: continue
                    time_col = time_cols[0]
                    df[time_col] = pd.to_numeric(df[time_col], errors='coerce')
                    # Find closest bar
                    df['diff'] = (df[time_col] - ts).abs()
                    closest_bar = df.sort_values(by='diff').iloc[0]
                    entry_price = closest_bar['close']
                    
                    outcome, pnl_pct, bars = simulate_trade(symbol, side, entry_price, ts)
                    pnl_usd = NOTIONAL_USD * (pnl_pct / 100.0)
                    
                    results.append({
                        "rid": event.get('rid'),
                        "symbol": symbol,
                        "side": side,
                        "entry_price": entry_price,
                        "reason": event.get('why'),
                        "outcome": outcome,
                        "pnl_pct": pnl_pct,
                        "pnl_usd": pnl_usd,
                        "bars": bars,
                        "ts": ts
                    })

    df_results = pd.DataFrame(results)
    if not df_results.empty:
        print(df_results.groupby(['symbol', 'outcome']).size())
        print("\nAvg PnL by Outcome:")
        print(df_results.groupby('outcome')['pnl_pct'].mean())
        df_results.to_csv("reports/forensics/counterfactual_replay.csv", index=False)
        print("\nSaved to reports/forensics/counterfactual_replay.csv")

if __name__ == "__main__":
    main()
