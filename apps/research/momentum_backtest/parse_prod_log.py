import json
import pandas as pd
import sys
from pathlib import Path

def parse_order_log(log_path, output_path, symbol_filter="BNBUSDT"):
    print(f"Parsing {log_path} for symbol {symbol_filter}...")
    
    data = []
    with open(log_path, 'r') as f:
        for line in f:
            try:
                entry = json.loads(line)
                
                # Filter by symbol
                if entry.get('symbol') != symbol_filter:
                    continue
                
                ts = pd.to_datetime(entry['timestamp'], unit='ms')
                event_type = entry.get('event_type')
                
                signal = 0
                score = None
                
                if event_type == 'ORDER_INTENT':
                    side = entry.get('side')
                    if side == 'BUY':
                        signal = 1
                    elif side == 'SELL':
                        signal = -1
                    # Score is usually not in metadata for intents in this version, 
                    # but we know it crossed threshold. Leave None or infer? 
                    # Let's leave None.
                    
                elif event_type == 'ORDER_REJECTED':
                    signal = 0
                    metadata = entry.get('metadata', {})
                    # Extract score if available
                    if 'signal_score' in metadata:
                        score = float(metadata['signal_score'])
                    
                    # If rejection was due to neutral signal, we have the score.
                    # If rejection was due to risk/liquidity, we might not have score, 
                    # or signal might have been 1/-1 but rejected.
                    # But for parity check of the *signal logic*, we care about the raw signal.
                    # If it was rejected by risk, the "signal_prod" from decision_making perspective 
                    # might have been 1, but the system output was 0 (no order).
                    # However, the user wants to check "signal logic".
                    # If decision_making emitted an intent that got rejected later, 
                    # we should count it as a signal.
                    # But ORDER_REJECTED usually comes from DecisionMaking itself or downstream?
                    # The log says "source_fsm": "DecisionMaking".
                    # So if it says "Neutral signal score", signal is 0.
                    # If it says "Liquidity filter", signal might have been 1 but filtered.
                    # For now, let's trust "signal_prod" as the final decision of the component.
                    
                data.append({
                    'ts': ts,
                    'signal_prod': signal,
                    'score_prod': score
                })
                
            except Exception as e:
                continue
    
    if not data:
        print("No matching rows found!")
        return
    
    df = pd.DataFrame(data)
    df.sort_values('ts', inplace=True)
    
    # Drop duplicates by ts if any
    df.drop_duplicates(subset=['ts'], inplace=True)
    
    print(f"Extracted {len(df)} rows.")
    print(df.head())
    
    df.to_csv(output_path, index=False)
    print(f"Saved to {output_path}")

if __name__ == "__main__":
    parse_order_log(
        "logs/order_log_v1.jsonl", 
        "apps/research/momentum_backtest/data/runtime_log.csv",
        "BNBUSDT"
    )
