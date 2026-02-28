import json
import sys

def analyze_logs(file_path, symbols=None):
    if symbols:
        symbols = [s.upper() for s in symbols]
    
    with open(file_path, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                verb = data.get('verb')
                if verb == 'MARKET_DATA':
                    continue
                
                # Check if any of our symbols are in the payload or anywhere in the data
                line_str = json.dumps(data)
                if symbols:
                    if not any(s in line_str for s in symbols):
                        continue
                
                print(f"TS: {data.get('ts') or data.get('timestamp')} | OP: {data.get('op')} | VERB: {verb} | WHY: {data.get('why')} | PLD: {json.dumps(data.get('pld'))}")
            except Exception as e:
                # Skip invalid lines
                continue

if __name__ == "__main__":
    file_path = sys.argv[1]
    symbols = sys.argv[2:] if len(sys.argv) > 2 else None
    analyze_logs(file_path, symbols)
