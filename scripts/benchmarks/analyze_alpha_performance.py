
import sys
import json
import argparse
from typing import List, Dict, Any, Tuple
from datetime import datetime
from collections import defaultdict
import glob
import os
import math

class AlphaAnalyzer:
    def __init__(self):
        self.alpha_events = []
        self.prices = defaultdict(list)
        self.stats = {
            "total_events": 0,
            "matched_events": 0,
            "errors": 0  # To be populated if error logs are found
        }
        
    def parse_logs(self, log_path: str):
        """Parse logs to extract Alpha Scores and Price Updates."""
        print(f"Reading logs from: {log_path}")
        files = glob.glob(log_path)
        if not files:
            print("No files found.")
            return

        count = 0
        for file_path in files:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    try:
                        line = line.strip()
                        if not line: continue
                        
                        # Try extracting JSON
                        json_str = line
                        if "{" in line:
                            json_str = line[line.find("{"):]
                        
                        data = json.loads(json_str)
                        payload = data.get("payload", data)
                        op = data.get("op", "")
                        verb = data.get("verb", "")
                        
                        # 1. Capture Alpha Scores
                        if verb == "ALPHA_SCORE_CALCULATED" or op == "EVT:ALPHA_SCORE_CALCULATED":
                            ts = payload.get("timestamp", 0) / 1000.0
                            symbol = payload.get("symbol")
                            scores = payload.get("scores", [])
                            for score in scores:
                                self.alpha_events.append({
                                    "ts": ts,
                                    "symbol": symbol,
                                    "model": score.get("model_name"),
                                    "score": float(score.get("score", 0)),
                                    "confidence": float(score.get("confidence", 0))
                                })
                                
                        # 2. Capture Prices
                        if verb in ["MARKET_TICK", "PRICE_UPDATE", "TRADE_TICK"] or "price" in payload:
                            sym = payload.get("symbol")
                            p = payload.get("price") or payload.get("close")
                            ts = payload.get("timestamp", 0) / 1000.0
                            if sym and p and ts:
                                self.prices[sym].append((ts, float(p)))
                        
                        # 3. Capture Errors (Optional)
                        if "alpha_model_errors_total" in line:
                             self.stats["errors"] += 1
                                
                        count += 1
                    except Exception:
                        continue

        self.stats["total_events"] = len(self.alpha_events)
        print(f"Parsed {count} lines. Found {len(self.alpha_events)} alpha events.")
        
        # Sort prices
        for sym in self.prices:
            self.prices[sym].sort(key=lambda x: x[0])

    def analyze(self, horizon_sec: int = 300) -> Dict:
        """Analyze alpha performance."""
        # Key: (model, symbol) -> {correct, total, ...}
        results = defaultdict(lambda: {"correct": 0, "total": 0, "return_sum": 0.0})
        # Key: (model, conf_bucket) -> {correct, total}
        conf_results = defaultdict(lambda: {"correct": 0, "total": 0})
        
        matched_count = 0
        
        for event in self.alpha_events:
            symbol = event["symbol"]
            model = event["model"]
            ts = event["ts"]
            score = event["score"]
            conf = event["confidence"]
            
            if symbol not in self.prices:
                continue
                
            # Find prices
            sym_prices = self.prices[symbol]
            curr_p = self._find_price(sym_prices, ts, tolerance=5.0)
            future_p = self._find_price_after(sym_prices, ts + horizon_sec)
            
            if curr_p is None or future_p is None:
                continue
                
            matched_count += 1
            
            # Outcome
            ret = (future_p - curr_p) / curr_p
            is_bullish = score > 0.05
            is_bearish = score < -0.05
            is_correct = False
            
            if is_bullish and ret > 0: is_correct = True
            elif is_bearish and ret < 0: is_correct = True
            
            matches_direction = is_correct
            # Note: Neutral scores (abs < 0.05) are ignored for directional accuracy unless return is 0?
            # Let's count them in Total but not Correct if return != 0.
            # Actually standard practice: Only evaluate Signal != 0.
            
            if abs(score) > 0.05:
                key = (model, symbol)
                results[key]["total"] += 1
                results[key]["return_sum"] += ret * (1 if is_bullish else -1) # Long/Short return
                if matches_direction:
                    results[key]["correct"] += 1
                
                # Confidence Buckets
                bucket = math.floor(conf * 5) / 5.0  # 0.0, 0.2, 0.4...
                bucket_key = (model, f"{bucket:.1f}-{bucket+0.2:.1f}")
                conf_results[bucket_key]["total"] += 1
                if matches_direction:
                    conf_results[bucket_key]["correct"] += 1
        
        self.stats["matched_events"] = matched_count
        return results, conf_results

    def _find_price(self, prices, ts, tolerance):
        # Naive linear search ok for script
        for pts, p in prices:
            if abs(pts - ts) <= tolerance:
                return p
            if pts > ts + tolerance:
                break
        return None
        
    def _find_price_after(self, prices, ts):
        for pts, p in prices:
            if pts >= ts:
                return p
        return None

    def generate_markdown(self, results, conf_results, out_path):
        """Generate MD report."""
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write("# Alpha Evaluation Report\n\n")
            f.write(f"**Date:** {datetime.utcnow().isoformat()}\n")
            f.write(f"**Total Events:** {self.stats['total_events']}\n")
            f.write(f"**Matched Outcomes:** {self.stats['matched_events']}\n")
            f.write(f"**Errors Detected:** {self.stats['errors']}\n\n")
            
            f.write("## 1. Performance by Symbol & Model\n\n")
            f.write("| Model | Symbol | Events | Hit Rate | Avg Trade Return |\n")
            f.write("|---|---|---|---|---|\n")
            
            # Sort by Hit Rate desc
            sorted_res = sorted(results.items(), key=lambda x: x[1]['correct']/x[1]['total'] if x[1]['total']>0 else 0, reverse=True)
            
            for (model, symbol), stats in sorted_res:
                total = stats['total']
                if total == 0: continue
                acc = (stats['correct'] / total) * 100
                avg_ret = (stats['return_sum'] / total) * 10000  # bps?
                f.write(f"| {model} | {symbol} | {total} | **{acc:.1f}%** | {avg_ret:.2f} bp |\n")
                
            f.write("\n## 2. Confidence Analysis\n\n")
            f.write("| Model | Confidence | Events | Hit Rate |\n")
            f.write("|---|---|---|---|\n")
            
            sorted_conf = sorted(conf_results.items(), key=lambda x: (x[0][0], x[0][1]))
            
            for (model, bucket), stats in sorted_conf:
                total = stats['total']
                if total == 0: continue
                acc = (stats['correct'] / total) * 100
                f.write(f"| {model} | {bucket} | {total} | **{acc:.1f}%** |\n")
                
            f.write("\n## 3. Top/Bottom Performers\n\n")
            if sorted_res:
                best = sorted_res[0]
                worst = sorted_res[-1]
                f.write(f"- **Best:** {best[0][0]} on {best[0][1]} ({best[1]['correct']/best[1]['total']*100:.1f}%)\n")
                f.write(f"- **Worst:** {worst[0][0]} on {worst[0][1]} ({worst[1]['correct']/worst[1]['total']*100:.1f}%)\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Path to log files", required=True)
    parser.add_argument("--out-md", help="Output Markdown path", required=True)
    args = parser.parse_args()
    
    analyzer = AlphaAnalyzer()
    analyzer.parse_logs(args.input)
    res, conf_res = analyzer.analyze()
    analyzer.generate_markdown(res, conf_res, args.out_md)
