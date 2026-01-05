
import json
import os
import glob
from datetime import datetime
from collections import defaultdict

def get_latest_orders(limit=5):
    orders = []
    fname = 'logs/order_log_v1.jsonl'
    if not os.path.exists(fname):
        print(f"File not found: {fname}")
        return []
        
    with open(fname, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                if data.get('event_type') == 'ORDER_PLACED':
                    orders.append(data)
            except:
                continue
    
    # Sort by ts descending and existing
    orders.sort(key=lambda x: x.get('timestamp', 0), reverse=True)
    return orders[:limit]

def find_decision_log_entries(rids, symbol_ts_map):
    """
    Find DECISION_EVAL entries. 
    Fallback: If RID match fails, look for DECISION_EVAL for the SYMBOL within 1 second of order timestamp.
    """
    entries = {}
    rids_set = set(rids)
    
    # Get all decision logs
    files = glob.glob("logs/domain_decision_making.log*")
    print(f"Scanning {len(files)} decision log files...")
    
    found_count = 0
    for filepath in files:
        with open(filepath, 'r') as f:
            for line in f:
                if "DECISION_EVAL" not in line:
                    continue
                
                try:
                    # Extract JSON payload
                    json_part = line[line.find('{'):]
                    data = json.loads(json_part)
                    
                    # Check RID match
                    rid = data.get('rid')
                    if rid in rids_set:
                        entries[rid] = data
                        found_count += 1
                        continue
                        
                except Exception as e:
                    continue
                    
    print(f"Found {found_count} decision entries by RID.")
    return entries

def get_market_context_30m(symbol, order_ts):
    """
    Extract features from domain_feature_engineering for 30m prior to order.
    """
    start_ts = order_ts - (30 * 60 * 1000) # 30 min ms
    end_ts = order_ts
    
    features = []
    files = glob.glob("logs/domain_feature_engineering.log*")
    # Sort files to try to read sequentially (optional but good)
    files.sort(key=os.path.getmtime)
    
    # Optimization: Only read files modified after start_ts (rough check)
    # But files rotate, so better just scan all or check timestamp in filename if available (not here).
    
    for filepath in files:
        with open(filepath, 'r') as f:
            for line in f:
                if f"Calculated features for {symbol}" not in line:
                    continue
                    
                try:
                    # Parse timestamp from log line prefix 
                    # Format: 2026-01-04 16:16:19,865
                    ts_str = line.split(' - ')[0].strip()
                    dt = datetime.strptime(ts_str.split(',')[0], "%Y-%m-%d %H:%M:%S")
                    ms = int(ts_str.split(',')[1])
                    line_ts = int(dt.timestamp() * 1000) + ms
                    
                    if start_ts <= line_ts <= end_ts:
                        json_str = line[line.find('{'):]
                        feat = json.loads(json_str)
                        feat['ts'] = line_ts
                        features.append(feat)
                except:
                    continue
                    
    # Sort by TS
    features.sort(key=lambda x: x['ts'])
    return features

def analyze_context(features):
    if not features:
        return "No data"
        
    prices = [float(f['price']) for f in features]
    low = min(prices)
    high = max(prices)
    open_p = prices[0]
    close_p = prices[-1]
    
    change_pct = (close_p - open_p) / open_p * 100
    
    # Volatility trend
    vol_start = float(features[0].get('volatility_state', 0.5))
    vol_end = float(features[-1].get('volatility_state', 0.5))
    
    # Average OBI
    obis = [float(f.get('obi', 0)) for f in features]
    avg_obi = sum(obis)/len(obis)
    
    return {
        "price_change_pct": change_pct,
        "price_range_pct": (high - low) / low * 100,
        "volatility_trend": f"{vol_start:.2f} -> {vol_end:.2f}",
        "avg_obi_30m": avg_obi,
        "features_count": len(features)
    }

def main():
    print("Fetching latest orders...")
    orders = get_latest_orders(5)
    
    if not orders:
        print("No orders found.")
        return

    rids = [o['rid'] for o in orders]
    # Map Symbol+TS for fallback searching (not implemented yet, stick to RID for now)
    
    print("Correlating with Decision Logs...")
    decisions = find_decision_log_entries(rids, None)
    
    results = []
    
    for o in orders:
        rid = o['rid']
        symbol = o['symbol']
        ts = o['timestamp']
        dt_str = datetime.fromtimestamp(ts/1000).strftime('%Y-%m-%d %H:%M:%S')
        
        print(f"\nProcessing Order: {symbol} {o['side']} at {dt_str} (RID: {rid})")
        
        # 1. Decision Basis
        decision = decisions.get(rid)
        basis = "Unknown (Log missing)"
        metrics = {}
        score = None
        
        if decision:
            psi = decision.get('psi', {})
            score = decision.get('signal_score')
            threshold = decision.get('signal_threshold')
            
            # Extract key metrics
            metrics = {
                'score': score,
                'threshold': threshold,
                'obi': psi.get('obi'),
                'tfi': psi.get('tfi'),
                'ema_bias': psi.get('ema_bias'),
                'li_kappa': psi.get('liquidity_kappa'),
                'macro_sync': psi.get('macro_sync'),
                'vol_spike': psi.get('volume_spike')
            }
            basis = f"Signal Score {score:.4f} > Threshold {threshold:.4f}"
        
        # 2. Market Context (30m)
        print("analyzing market context...")
        features_hist = get_market_context_30m(symbol, ts)
        context_summary = analyze_context(features_hist)
        
        results.append({
            "order": o,
            "metrics": metrics,
            "basis": basis,
            "context": context_summary
        })
        
    # Output Report
    for res in results:
        o = res['order']
        m = res['metrics']
        c = res['context']
        
        print(f"\n==================================================")
        print(f"ORDER: {o['symbol']} {o['side']} ({o['quantity']} units)")
        print(f"TIME: {datetime.fromtimestamp(o['timestamp']/1000)}")
        print(f"BASIS: {res['basis']}")
        if m:
            print(f"KEY METRICS AT ENTRY:")
            print(f"  - Signal Score: {m.get('score', 'N/A')}")
            print(f"  - Liquidity Kappa: {m.get('li_kappa', 'N/A')} (Usually high weight)")
            print(f"  - EMA Bias: {m.get('ema_bias', 'N/A')} (Trend)")
            print(f"  - OBI: {m.get('obi', 'N/A')}")
            print(f"  - Macro Sync: {m.get('macro_sync', 'N/A')}")
            print(f"  - Volume Spike: {m.get('vol_spike', 'N/A')}")
            
        if isinstance(c, dict):
            print(f"MARKET CONTEXT (Last 30m):")
            print(f"  - Price Change: {c['price_change_pct']:.2f}%")
            print(f"  - Range Volatility: {c['price_range_pct']:.2f}%")
            print(f"  - Avg OBI: {c['avg_obi_30m']:.2f}")
            print(f"  - Volatility State Trend: {c['volatility_trend']}")
        else:
            print(f"MARKET CONTEXT: {c}")

if __name__ == "__main__":
    main()
