import json
import collections
from pathlib import Path
import sys

def analyze_rejects(log_paths):
    reject_counts = collections.Counter()
    nrr_counts = collections.Counter()
    total_events = 0
    reject_events = 0

    target_events = {
        "TRADE_INTENT_REJECTED", "EVT:TRADE_INTENT_REJECTED",
        "DECISION_BLOCKED", "EVT:DECISION_BLOCKED",
        "EXECUTION_GUARD_BLOCKED", "EVT:EXECUTION_GUARD_BLOCKED",
        "ORDER_REJECTED", "EVT:ORDER_REJECTED",
        "INTENT_DEFERRED", "EVT:INTENT_DEFERRED"
    }

    for log_path in log_paths:
        path = Path(log_path)
        if not path.exists():
            continue
            
        print(f"Аналізую файл: {path.name}...")
        
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                try:
                    event = json.loads(line)
                    total_events += 1
                    
                    event_type = event.get("event_type") or event.get("event_name") or event.get("verb")
                    if event.get("op") == "EVT" and event_type and not event_type.startswith("EVT:"):
                        event_type = f"EVT:{event_type}"
                        
                    if event_type in target_events:
                        reject_events += 1
                        
                        # Extract payload and metadata
                        payload = event.get("payload") or event.get("pld") or event
                        payload_dict = payload if isinstance(payload, dict) else {}
                        metadata = event.get("metadata", {})
                        
                        # Extract NRR Code if available
                        nrr = payload_dict.get("nrr_code") or metadata.get("nrr_code") or payload_dict.get("reason_code")
                        if nrr:
                            nrr_counts[nrr] += 1
                            
                        # Extract text reason
                        reason = (
                            payload_dict.get("reason") or 
                            payload_dict.get("reject_reason") or 
                            payload_dict.get("deny_reason") or 
                            metadata.get("reject_reason") or 
                            event.get("why") or 
                            "UNKNOWN_REASON"
                        )
                        
                        # Clean up 'why' chains if it's a list
                        if isinstance(reason, list):
                            reason = " -> ".join([str(x) for x in reason])
                            
                        reject_counts[str(reason)[:100]] += 1 # Truncate very long reasons
                        
                except json.JSONDecodeError:
                    continue

    print("\n" + "="*60)
    print("📊 ЗВІТ ПО ВІДХИЛЕННЯХ (REJECT ANALYSIS REPORT)")
    print("="*60)
    print(f"Всього оброблено подій: {total_events}")
    print(f"Знайдено подій відхилення/блокування: {reject_events}")
    
    if reject_events == 0:
        print("\nВідхилень не знайдено в наданих логах.")
        return

    print("\n🔴 ТОП-15 Причин Відхилення (Text Reasons):")
    print("-" * 60)
    for reason, count in reject_counts.most_common(15):
        pct = (count / reject_events) * 100
        print(f"[{count:5d} | {pct:5.1f}%] {reason}")

    if nrr_counts:
        print("\n🔢 Розподіл за NRR Кодами (Normalized Reject Reasons):")
        print("-" * 60)
        for nrr, count in nrr_counts.most_common(10):
            pct = (count / reject_events) * 100
            print(f"[{count:5d} | {pct:5.1f}%] {nrr}")

if __name__ == "__main__":
    # Шукаємо найімовірніші лог-файли з ордерами
    potential_logs = [
        "logs/order_log_v1.jsonl",
        "tmp_phase2_debug/trade_lifecycle.jsonl",
        "logs/shadow_telemetry/decision_ledger_v1.jsonl",
        "logs/event_chain.log"
    ]
    analyze_rejects(potential_logs)
