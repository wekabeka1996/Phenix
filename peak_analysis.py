
import json
import os
import sys
import re
from datetime import datetime, timedelta
from collections import defaultdict

def parse_order_logs(file_path, symbols, start_ts):
    orders = []
    if not os.path.exists(file_path):
        return []
    with open(file_path, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                if data.get('event_type') == 'ORDER_PLACED' and \
                   data.get('side') == 'BUY' and \
                   data.get('symbol') in symbols and \
                   data.get('timestamp', 0) >= start_ts:
                    orders.append(data)
            except:
                continue
    return orders

def find_decision_evals(file_path, rids):
    evals = {}
    rids_set = set(rids)
    log_files = [file_path]
    for i in range(1, 6):
        p = f"{file_path}.{i}"
        if os.path.exists(p):
            log_files.append(p)
    
    for log_file in log_files:
        with open(log_file, 'r') as f:
            for line in f:
                if 'DECISION_EVAL' in line:
                    try:
                        idx = line.find('{')
                        if idx != -1:
                            data = json.loads(line[idx:])
                            if data.get('rid') in rids_set:
                                evals[data['rid']] = data
                    except:
                        continue
    return evals

def extract_features_from_domain_logs(log_path, symbol, start_ts, end_ts):
    """
    Since features/*.log lacks timestamps, we must use domain_feature_engineering.log.
    """
    features_history = []
    log_files = [log_path]
    for i in range(1, 4): # Check first few rotations
        p = f"{log_path}.{i}"
        if os.path.exists(p):
            log_files.append(p)
    
    # Sort files by age (heuristic: higher suffix is older)
    log_files.sort(key=lambda x: int(x.split('.')[-1]) if '.' in x and x.split('.')[-1].isdigit() else 0, reverse=True)

    for log_file in log_files:
        with open(log_file, 'r') as f:
            for line in f:
                if f"Calculated features for {symbol}:" in line:
                    try:
                        # 2026-01-04 16:16:19,865 - ... - Calculated features for SOLUSDT: {"obi": ...}
                        ts_str = line.split(' - ')[0]
                        # Assume format: 2026-01-04 16:16:19,865
                        dt = datetime.strptime(ts_str.split(',')[0], "%Y-%m-%d %H:%M:%S")
                        ms = int(ts_str.split(',')[1])
                        ts_ms = int(dt.timestamp() * 1000) + ms
                        
                        if start_ts <= ts_ms <= end_ts:
                            idx = line.find('{')
                            if idx != -1:
                                feats = json.loads(line[idx:])
                                feats['ts'] = ts_ms
                                features_history.append(feats)
                    except Exception as e:
                        continue
    # Sort by timestamp
    features_history.sort(key=lambda x: x['ts'])
    return features_history

def analyze_post_entry(features, entry_ts, window_ms=300000): # 5 min
    entry_price = None
    for f in features:
        if f['ts'] >= entry_ts:
            entry_price = float(f['price'])
            break
    
    if entry_price is None:
        return None
    
    max_price = entry_price
    min_price = entry_price
    max_drawdown = 0
    max_profit = 0
    
    for f in features:
        if entry_ts < f['ts'] <= entry_ts + window_ms:
            p = float(f['price'])
            max_price = max(max_price, p)
            min_price = min(min_price, p)
            
            # Drawdown from entry
            dd = (entry_price - p) / entry_price
            max_drawdown = max(max_drawdown, dd)
            
            # Profit from entry
            profit = (p - entry_price) / entry_price
            max_profit = max(max_profit, profit)
            
    return {
        "entry_price": entry_price,
        "max_profit_5m": max_profit,
        "max_drawdown_5m": max_drawdown,
        "final_price_5m": float(features[-1]['price']) if features and features[-1]['ts'] <= entry_ts + window_ms else None
    }

def main():
    symbols = ['BTCUSDT', 'SOLUSDT', 'ETHUSDT']
    # 72 hours back from now (well, using the timestamp in system metadata)
    now_ts = 1767543322000 
    start_ts = now_ts - (72 * 3600 * 1000)
    
    print(f"Analyzing from {datetime.fromtimestamp(start_ts/1000)} to {datetime.fromtimestamp(now_ts/1000)}")
    
    orders = parse_order_logs('logs/order_log_v1.jsonl', symbols, start_ts)
    print(f"Found {len(orders)} BUY orders for {symbols}")
    
    rids = [o['rid'] for o in orders]
    evals = find_decision_evals('logs/domain_decision_making.log', rids)
    print(f"Correlated {len(evals)} with Decision Eval logs")
    
    results = []
    for order in orders:
        rid = order['rid']
        symbol = order['symbol']
        ts = order['timestamp']
        
        # Get features history for context
        # We need a large enough window to see 10m before and 5m after
        feat_start = ts - 600000
        feat_end = ts + 300000
        history = extract_features_from_domain_logs('logs/domain_feature_engineering.log', symbol, feat_start, feat_end)
        
        if not history:
            continue
            
        post_entry = analyze_post_entry(history, ts)
        
        decision = evals.get(rid, {})
        psi = decision.get('psi', {})
        
        results.append({
            "ts": ts,
            "symbol": symbol,
            "rid": rid,
            "indicators": psi,
            "post_entry": post_entry,
            "features_at_entry": next((h for h in reversed(history) if h['ts'] <= ts), None)
        })

    # Summary Stats
    if not results:
        print("No results to analyze")
        return

    print("\n--- STATISTICAL OVERVIEW ---")
    total = len(results)
    success = sum(1 for r in results if r['post_entry'] and r['post_entry']['max_profit_5m'] > 0.005)
    failure = sum(1 for r in results if r['post_entry'] and r['post_entry']['max_drawdown_5m'] > 0.005)
    
    print(f"Total Signals: {total}")
    print(f"Success Rate (Profit > 0.5% in 5m): {success/total:.2%}")
    print(f"Failure Rate (Drawdown > 0.5% in 5m): {failure/total:.2%}")
    
    # Identify Peak Entry Pattern
    print("\n--- IDENTIFIED PEAK ENTRY PATTERNS ---")
    bad_results = [r for r in results if r['post_entry'] and r['post_entry']['max_drawdown_5m'] > r['post_entry']['max_profit_5m'] * 2]
    print(f"Analyzing {len(bad_results)} 'Peak Entries' (Drawdown > 2x Profit)")
    
    if bad_results:
        avg_delta_p = sum(float(r['indicators'].get('phi_DeltaP', 0)) for r in bad_results) / len(bad_results)
        avg_obi = sum(float(r['indicators'].get('phi_OBI', 0)) for r in bad_results) / len(bad_results)
        avg_vol_spike = sum(float(r['indicators'].get('phi_Volume_Spike', 0)) for r in bad_results) / len(bad_results)
        
        print(f"Avg phi_DeltaP at peak: {avg_delta_p:.4f}")
        print(f"Avg phi_OBI at peak: {avg_obi:.4f}")
        print(f"Avg phi_Volume_Spike at peak: {avg_vol_spike:.4f}")

    # Write to file
    with open('peak_forensic_report.json', 'w') as f:
        json.dump(results, f, indent=2)
    print("\nDetailed report saved to peak_forensic_report.json")

if __name__ == "__main__":
    main()
