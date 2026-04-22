import json
import csv
import os

LOG_FILE = "logs/order_log_v1.jsonl"
OUTPUT_TIMING = "confidence_timing_master.csv"
OUTPUT_DECOMP = "gate_block_decomposition.csv"
OUTPUT_SUMMARY = "regime_epoch_latency_summary.csv"

def analyze_r1():
    timing_data = []
    decomp_data = []
    
    if not os.path.exists(LOG_FILE):
        print(f"Log file {LOG_FILE} not found")
        return

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            try:
                event = json.loads(line)
            except:
                continue
                
            event_type = event.get("event_type")
            symbol = event.get("symbol")
            ts_ms = event.get("timestamp")
            
            if event_type == "DECISION_INTENT_REJECTED":
                prov = event.get("regime_provenance", {}).get("detector_event", {})
                metadata = event.get("metadata", {})
                
                decomp_data.append({
                    "symbol": symbol,
                    "ts_ms": ts_ms,
                    "regime": event.get("regime"),
                    "regime_confidence": event.get("regime_confidence"),
                    "effective_confidence": event.get("effective_confidence"),
                    "score": event.get("signal_score"),
                    "gate_failed": event.get("why"),
                    "why_code": event.get("nrr_code"),
                })
                
                # Extract timing info if available
                if prov:
                    timing_data.append({
                        "symbol": symbol,
                        "strategy_id": "aurora",
                        "raw_regime": prov.get("raw_regime"),
                        "stable_regime": prov.get("regime"),
                        "raw_regime_start_ts": prov.get("ts_ms"), # Approximation
                        "stable_regime_start_ts": ts_ms,
                        "bars_raw_to_stable": prov.get("hysteresis_confirm_count"),
                        "raw_regime_confidence_at_start": prov.get("raw_confidence"),
                        "confidence_cross_min_regime_ts": ts_ms if metadata.get("threshold_verdict") == "PASS" else None,
                        "price_at_stable_start": event.get("price"),
                    })

    # Write CSVs
    if decomp_data:
        keys = decomp_data[0].keys()
        with open(OUTPUT_DECOMP, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(decomp_data)

    if timing_data:
        keys = timing_data[0].keys()
        with open(OUTPUT_TIMING, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(timing_data)

    print(f"R1 analysis complete. Created {OUTPUT_TIMING} and {OUTPUT_DECOMP}")

if __name__ == "__main__":
    analyze_r1()
