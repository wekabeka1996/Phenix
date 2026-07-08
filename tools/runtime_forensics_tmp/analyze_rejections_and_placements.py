import json
from pathlib import Path
from datetime import datetime, timezone

PATCH_TS_MS = 1782845625000

def analyze():
    path = Path("logs/shadow_critical_event_journal_v1.jsonl")
    if not path.exists():
        print("shadow journal does not exist")
        return
    
    pre_stats = {}
    post_stats = {}
    
    pre_rejections = []
    post_rejections = []
    
    pre_traces = []
    post_traces = []
    
    with open(path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            ts = row.get("ts_ms")
            if not ts:
                continue
            
            event_name = row.get("event_name")
            strat = row.get("strategy_id") or (row.get("payload", {}).get("strategy_id") if isinstance(row.get("payload"), dict) else None)
            
            is_post = (ts >= PATCH_TS_MS)
            stats = post_stats if is_post else pre_stats
            
            # Count events by type and strategy
            key = (event_name, strat)
            stats[key] = stats.get(key, 0) + 1
            
            if event_name == "EVT:TRADE_INTENT_REJECTED":
                if is_post:
                    post_rejections.append(row)
                else:
                    pre_rejections.append(row)
            elif event_name == "EVT:GATE_CHAIN_TRACE":
                if is_post:
                    post_traces.append(row)
                else:
                    pre_traces.append(row)

    print("=== PRE-PATCH STATS (ts < 1782845625000) ===")
    for (name, strat), count in sorted(pre_stats.items(), key=lambda x: x[1], reverse=True):
         print(f"  Event: {name:<35} | Strategy: {str(strat):<15} | Count: {count}")
         
    print("\n=== POST-PATCH STATS (ts >= 1782845625000) ===")
    for (name, strat), count in sorted(post_stats.items(), key=lambda x: x[1], reverse=True):
         print(f"  Event: {name:<35} | Strategy: {str(strat):<15} | Count: {count}")

    print(f"\nTotal pre-patch rejections: {len(pre_rejections)}")
    print(f"Total post-patch rejections: {len(post_rejections)}")
    
    print("\n--- Details of Post-Patch Rejections ---")
    for r in post_rejections:
        dt = datetime.fromtimestamp(r["ts_ms"] / 1000.0, tz=timezone.utc).isoformat()
        pf = r.get("payload_fragment") or r.get("payload") or {}
        print(f"[{dt}] rid={r.get('rid')} symbol={r.get('symbol')} strategy={r.get('strategy_id')} side={pf.get('side') or r.get('side')}")
        print(f"  why={pf.get('why')} | reason_code={pf.get('reason_code')} | why_chain={pf.get('why_chain')}")
        
    print("\n--- Details of Post-Patch Traces ---")
    for t in post_traces:
        dt = datetime.fromtimestamp(t["ts_ms"] / 1000.0, tz=timezone.utc).isoformat()
        pf = t.get("payload_fragment") or t.get("payload") or {}
        print(f"[{dt}] rid={t.get('rid')} symbol={t.get('symbol')} strategy={t.get('strategy_id')}")
        print(f"  Trace: {json.dumps(pf)}")

if __name__ == "__main__":
    analyze()
