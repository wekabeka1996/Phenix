#!/usr/bin/env python3
"""
Comprehensive Trade Log Analysis Script
Analyzes JSONL logs for:
1. Confidence Trap: High confidence (0.9-1.0) vs Medium confidence (0.5-0.7) trade outcomes
2. Exhaustion: Correlation between regime_age_sec and losses
3. Execution Health: GUARD_REJECT and other anomalies
"""

import json
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime
import statistics

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
LOGS_DIR = BASE_DIR / "logs"
WAL_DIR = BASE_DIR / "ops" / "wal"
BACKTEST_LOG = LOGS_DIR / "backtests" / "order_log_20260207_182300.jsonl"

def load_jsonl(filepath: Path) -> list:
    """Load JSONL file into list of dicts."""
    records = []
    if not filepath.exists():
        print(f"⚠️  File not found: {filepath}")
        return records
    
    with open(filepath, 'r') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"⚠️  JSON decode error at line {line_num}: {e}")
    return records


def analyze_confidence_trap(wal_records: list, order_records: list):
    """
    ПРОМПТ 1: Confidence Trap Analysis
    Find trades with highest confidence (0.9-1.0) and compare with medium confidence (0.5-0.7)
    """
    print("\n" + "="*80)
    print("📊 АНАЛІЗ CONFIDENCE TRAP (Пастка Високої Впевненості)")
    print("="*80)
    
    # Extract alpha scores with confidence
    high_conf_scores = []  # 0.9-1.0
    medium_conf_scores = []  # 0.5-0.7
    low_conf_scores = []  # < 0.5
    
    confidence_distribution = defaultdict(int)
    all_confidences = []
    
    for record in wal_records:
        if record.get("verb") == "ALPHA_SCORE_CALCULATED":
            scores = record.get("scores", [])
            for score_item in scores:
                conf = score_item.get("confidence", 0)
                all_confidences.append(conf)
                
                # Bucket by range
                bucket = int(conf * 10) / 10  # Round to nearest 0.1
                confidence_distribution[bucket] += 1
                
                if 0.9 <= conf <= 1.0:
                    high_conf_scores.append(score_item)
                elif 0.5 <= conf <= 0.7:
                    medium_conf_scores.append(score_item)
                elif conf < 0.5:
                    low_conf_scores.append(score_item)
    
    print(f"\n📈 Розподіл Confidence:")
    print(f"   • Високий (0.9-1.0): {len(high_conf_scores)} сигналів")
    print(f"   • Середній (0.5-0.7): {len(medium_conf_scores)} сигналів")
    print(f"   • Низький (<0.5): {len(low_conf_scores)} сигналів")
    
    if all_confidences:
        print(f"\n📊 Статистика Confidence:")
        print(f"   • Min: {min(all_confidences):.4f}")
        print(f"   • Max: {max(all_confidences):.4f}")
        print(f"   • Mean: {statistics.mean(all_confidences):.4f}")
        print(f"   • Median: {statistics.median(all_confidences):.4f}")
        print(f"   • Стд.відхил: {statistics.stdev(all_confidences):.4f}" if len(all_confidences) > 1 else "")
    
    print(f"\n📊 Розподіл по бакетах (0.1 кроком):")
    for bucket in sorted(confidence_distribution.keys()):
        count = confidence_distribution[bucket]
        bar = "█" * (count // 100)
        print(f"   {bucket:.1f}: {count:5d} {bar}")
    
    # Analyze order outcomes by regime confidence from rejected intents
    regime_conf_outcomes = {"high": [], "medium": [], "low": []}
    
    for record in wal_records:
        if record.get("verb") == "TRADE_INTENT_REJECTED":
            pld = record.get("pld", {})
            # Check for regime_confidence in metadata
            if "regime_confidence" in str(record):
                # Extract regime confidence if present in metadata
                metadata = record.get("metadata", {})
                regime_conf = metadata.get("regime_confidence", None)
                if regime_conf:
                    reason = pld.get("reason_code", "UNKNOWN")
                    if 0.9 <= regime_conf <= 1.0:
                        regime_conf_outcomes["high"].append({"conf": regime_conf, "reason": reason})
                    elif 0.5 <= regime_conf <= 0.7:
                        regime_conf_outcomes["medium"].append({"conf": regime_conf, "reason": reason})
    
    # Check order log for outcomes
    completed_orders = []
    for record in order_records:
        event_type = record.get("event_type", "")
        if event_type in ["ORDER_FILLED", "POSITION_CLOSED", "TRADE_COMPLETED"]:
            completed_orders.append(record)
    
    print(f"\n📋 Завершені угоди в логах: {len(completed_orders)}")
    
    # Look for ORDER_REJECTED with regime_confidence metadata
    rejected_with_conf = []
    for record in order_records:
        if record.get("event_type") == "ORDER_REJECTED":
            metadata = record.get("metadata", {})
            if "regime_confidence" in metadata:
                rejected_with_conf.append(record)
    
    print(f"📋 Відхилено з regime_confidence: {len(rejected_with_conf)}")
    
    # Висновок
    print("\n💡 ВИСНОВОК щодо Confidence Trap:")
    if len(high_conf_scores) == 0:
        print("   ⚠️  У логах НЕМАЄ сигналів з високим confidence (0.9-1.0)")
        print("   ℹ️  Максимальний confidence в логах: {:.4f}".format(max(all_confidences) if all_confidences else 0))
        print("   ➡️  Система коректно не генерує надто впевнених сигналів")
    else:
        print(f"   ⚠️  Знайдено {len(high_conf_scores)} сигналів з HIGH confidence")
        
    return high_conf_scores, medium_conf_scores


def analyze_regime_exhaustion(wal_records: list, order_records: list):
    """
    ПРОМПТ 2: Exhaustion Analysis
    Check correlation between regime_age_sec and losses
    """
    print("\n" + "="*80)
    print("⏱️  АНАЛІЗ REGIME EXHAUSTION (Виснаження Режиму)")
    print("="*80)
    
    # Look for regime changes and their durations
    regime_events = []
    regime_cancellations = defaultdict(list)
    
    for record in order_records:
        event_type = record.get("event_type", "")
        
        # Track regime-based cancellations
        if event_type == "ORDER_CANCELLED":
            reason = record.get("reason", "")
            context = record.get("context", "")
            if "regime" in reason.lower() or "regime" in context.lower():
                regime_cancellations[reason].append(record)
    
    print(f"\n📈 Скасування через зміну режиму:")
    for reason, orders in sorted(regime_cancellations.items()):
        print(f"   • {reason}: {len(orders)} ордерів")
        # Show context breakdown
        contexts = defaultdict(int)
        for order in orders:
            ctx = order.get("context", "unknown")
            contexts[ctx] += 1
        for ctx, count in sorted(contexts.items(), key=lambda x: -x[1])[:5]:
            print(f"      → {ctx}: {count}")
    
    # Analyze timestamps to estimate regime durations
    cancel_timestamps = []
    for orders in regime_cancellations.values():
        for order in orders:
            ts = order.get("timestamp", 0)
            if ts:
                cancel_timestamps.append(ts)
    
    if cancel_timestamps:
        cancel_timestamps.sort()
        # Calculate time between cancellations (approximate regime duration)
        if len(cancel_timestamps) > 1:
            durations = []
            for i in range(1, len(cancel_timestamps)):
                duration_sec = (cancel_timestamps[i] - cancel_timestamps[i-1]) / 1000
                if 0 < duration_sec < 86400:  # Less than 1 day
                    durations.append(duration_sec)
            
            if durations:
                print(f"\n📊 Час між скасуваннями (приблизна тривалість режиму):")
                print(f"   • Min: {min(durations):.1f} сек")
                print(f"   • Max: {max(durations):.1f} сек ({max(durations)/60:.1f} хв)")
                print(f"   • Mean: {statistics.mean(durations):.1f} сек")
                print(f"   • Median: {statistics.median(durations):.1f} сек")
    
    # Look for regime age in WAL logs
    regime_age_mentions = []
    for record in wal_records:
        record_str = json.dumps(record)
        if "regime_age" in record_str.lower():
            regime_age_mentions.append(record)
    
    print(f"\n📋 Записи з regime_age в WAL: {len(regime_age_mentions)}")
    
    # Висновок
    print("\n💡 ВИСНОВОК щодо Regime Exhaustion:")
    total_cancelled = sum(len(orders) for orders in regime_cancellations.values())
    if total_cancelled > 0:
        print(f"   📊 Всього скасовано через режим: {total_cancelled} ордерів")
        print(f"   ℹ️  Причина CANCEL_STALE_REGIME свідчить про швидку зміну режимів")
        print(f"   ⚠️  Якщо режими змінюються занадто часто - можливе перенастроювання")
    else:
        print("   ✅ Немає скасувань через виснаження режиму")
    
    return regime_cancellations


def analyze_execution_health(wal_records: list, order_records: list):
    """
    ПРОМПТ 3: Execution Health Analysis
    Check for GUARD_REJECT and other execution anomalies
    """
    print("\n" + "="*80)
    print("🛡️  АНАЛІЗ EXECUTION HEALTH (Здоров'я Виконання)")
    print("="*80)
    
    # Count rejection reasons from WAL
    rejection_reasons = defaultdict(int)
    rejection_examples = defaultdict(list)
    
    for record in wal_records:
        if record.get("verb") == "TRADE_INTENT_REJECTED":
            pld = record.get("pld", {})
            reason = pld.get("reason_code", "UNKNOWN")
            rejection_reasons[reason] += 1
            if len(rejection_examples[reason]) < 2:
                rejection_examples[reason].append(pld.get("why", ""))
    
    print(f"\n📋 Причини відхилення угод (TRADE_INTENT_REJECTED):")
    for reason, count in sorted(rejection_reasons.items(), key=lambda x: -x[1]):
        print(f"   • {reason}: {count}")
        for example in rejection_examples[reason]:
            if example:
                print(f"      ℹ️  {example[:80]}...")
    
    # Check for GUARD_REJECT specifically
    guard_rejects = []
    for record in order_records:
        event_type = record.get("event_type", "")
        reason = record.get("reason", "")
        metadata = record.get("metadata", {})
        
        if "guard" in event_type.lower() or "guard" in reason.lower():
            guard_rejects.append(record)
        if "guard" in str(metadata).lower():
            guard_rejects.append(record)
    
    # Check for ORDER_REJECTED events
    order_rejects = []
    for record in order_records:
        if record.get("event_type") == "ORDER_REJECTED":
            order_rejects.append(record)
    
    print(f"\n🛡️  GUARD_REJECT в order logs: {len(guard_rejects)}")
    print(f"📋 ORDER_REJECTED в order logs: {len(order_rejects)}")
    
    if order_rejects:
        reject_reasons = defaultdict(int)
        for rej in order_rejects:
            why = rej.get("why", rej.get("nrr_code", "UNKNOWN"))
            reject_reasons[why] += 1
        print(f"\n   Причини ORDER_REJECTED:")
        for reason, count in sorted(reject_reasons.items(), key=lambda x: -x[1]):
            print(f"      • {reason}: {count}")
    
    # Check for execution anomalies
    anomalies = {
        "timeout": 0,
        "connection_error": 0,
        "unknown_error": 0,
        "partial_fill": 0,
    }
    
    for record in order_records + wal_records:
        record_str = json.dumps(record).lower()
        if "timeout" in record_str:
            anomalies["timeout"] += 1
        if "connection" in record_str and "error" in record_str:
            anomalies["connection_error"] += 1
        if "partial" in record_str and "fill" in record_str:
            anomalies["partial_fill"] += 1
    
    print(f"\n⚠️  Виявлені аномалії:")
    for anomaly, count in anomalies.items():
        if count > 0:
            print(f"   • {anomaly}: {count}")
    
    if all(v == 0 for v in anomalies.values()):
        print("   ✅ Критичних аномалій виконання не виявлено")
    
    # Висновок
    print("\n💡 ВИСНОВОК щодо Execution Health:")
    if len(guard_rejects) == 0:
        print("   ✅ GUARD_REJECT помилок НЕ ВИЯВЛЕНО після останніх фіксів")
    else:
        print(f"   ⚠️  Виявлено {len(guard_rejects)} GUARD_REJECT подій - потребує уваги")
    
    safety_gates_count = rejection_reasons.get("NRR-027", 0)
    if safety_gates_count > 0:
        print(f"   ℹ️  Safety Gates (NRR-027): {safety_gates_count} блокувань")
    
    return rejection_reasons, guard_rejects, order_rejects


def main():
    print("="*80)
    print("🔍 КОМПЛЕКСНИЙ АНАЛІЗ ТОРГОВИХ ЛОГІВ")
    print(f"   Дата аналізу: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    # Load order log
    print(f"\n📂 Завантаження order log: {BACKTEST_LOG}")
    order_records = load_jsonl(BACKTEST_LOG)
    print(f"   → Завантажено {len(order_records)} записів")
    
    # Load latest WAL log
    wal_files = sorted(WAL_DIR.glob("*.jsonl"))
    if wal_files:
        latest_wal = wal_files[-1]
        print(f"\n📂 Завантаження WAL log: {latest_wal}")
        wal_records = load_jsonl(latest_wal)
        print(f"   → Завантажено {len(wal_records)} записів")
    else:
        print("⚠️  WAL файли не знайдено")
        wal_records = []
    
    # Run analyses
    analyze_confidence_trap(wal_records, order_records)
    analyze_regime_exhaustion(wal_records, order_records)
    analyze_execution_health(wal_records, order_records)
    
    print("\n" + "="*80)
    print("✅ АНАЛІЗ ЗАВЕРШЕНО")
    print("="*80)


if __name__ == "__main__":
    main()
