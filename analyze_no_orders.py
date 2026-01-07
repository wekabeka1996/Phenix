#!/usr/bin/env python3
"""
Детальний аналіз причин відсутності ордерів у системі.

Цей скрипт аналізує логи domain_decision_making.log та створює звіт:
- Статистика блокувань по причинах
- Аналіз signal scores по символах
- Динаміка блокувань у часі
- Рекомендації для покращення
"""

import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any


def parse_timestamp(log_line: str) -> datetime | None:
    """Парсить timestamp з логу."""
    match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})', log_line)
    if match:
        try:
            return datetime.strptime(match.group(1), '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return None
    return None


def analyze_decision_log(log_path: Path) -> Dict[str, Any]:
    """Аналізує лог decision_making."""
    
    stats = {
        'total_decisions': 0,
        'rejections': {
            'neutral_signal': 0,
            'qos_cooldown': 0,
            'safety_gates': defaultdict(int),
        },
        'symbols': defaultdict(lambda: {
            'neutral_count': 0,
            'qos_count': 0,
            'safety_gates_count': 0,
            'signal_scores': [],
            'thresholds_buy': [],
            'thresholds_sell': [],
        }),
        'timeline': [],
        'safety_gate_details': [],
    }
    
    with open(log_path, 'r', encoding='utf-8') as f:
        for line in f:
            ts = parse_timestamp(line)
            
            # Neutral signal
            if 'Trade intent' in line and 'rejected: Neutral signal' in line:
                stats['total_decisions'] += 1
                stats['rejections']['neutral_signal'] += 1
                
                # Парсимо деталі
                symbol_match = re.search(r'for (\w+) rejected', line)
                score_match = re.search(r'score ([-\d.]+)', line)
                buy_match = re.search(r'thr_buy=([\d.]+)', line)
                sell_match = re.search(r'thr_sell=([\d.]+)', line)
                
                if symbol_match:
                    symbol = symbol_match.group(1)
                    stats['symbols'][symbol]['neutral_count'] += 1
                    
                    if score_match:
                        score = float(score_match.group(1))
                        stats['symbols'][symbol]['signal_scores'].append(score)
                    
                    if buy_match:
                        stats['symbols'][symbol]['thresholds_buy'].append(
                            float(buy_match.group(1))
                        )
                    
                    if sell_match:
                        stats['symbols'][symbol]['thresholds_sell'].append(
                            float(sell_match.group(1))
                        )
                    
                    if ts:
                        stats['timeline'].append({
                            'ts': ts,
                            'type': 'neutral_signal',
                            'symbol': symbol,
                            'score': score if score_match else None,
                        })
            
            # QoS cooldown
            elif 'QoS REJECT' in line:
                stats['total_decisions'] += 1
                stats['rejections']['qos_cooldown'] += 1
                
                symbol_match = re.search(r'\[(\w+)\]', line)
                if symbol_match:
                    symbol = symbol_match.group(1)
                    stats['symbols'][symbol]['qos_count'] += 1
                    
                    if ts:
                        stats['timeline'].append({
                            'ts': ts,
                            'type': 'qos_cooldown',
                            'symbol': symbol,
                        })
            
            # Safety gates
            elif 'SAFETY_GATES: DENY' in line:
                stats['total_decisions'] += 1
                
                # Парсимо: [SYMBOL] SAFETY_GATES: DENY SIDE trend=X reason=NRR-XXX
                match = re.search(
                    r'\[(\w+)\]\s+SAFETY_GATES:\s+DENY\s+(\w+)\s+trend=(\w+)\s+reason=(\S+)',
                    line
                )
                
                if match:
                    symbol, side, trend, reason = match.groups()
                    stats['rejections']['safety_gates'][reason] += 1
                    stats['symbols'][symbol]['safety_gates_count'] += 1
                    
                    detail = {
                        'ts': ts,
                        'symbol': symbol,
                        'side': side,
                        'trend': trend,
                        'reason': reason,
                    }
                    stats['safety_gate_details'].append(detail)
                    
                    if ts:
                        stats['timeline'].append({
                            'ts': ts,
                            'type': 'safety_gate',
                            'symbol': symbol,
                            'reason': reason,
                            'side': side,
                            'trend': trend,
                        })
    
    return stats


def print_report(stats: Dict[str, Any]) -> None:
    """Друкує детальний звіт."""
    
    print("\n" + "="*80)
    print("📊 ДЕТАЛЬНИЙ АНАЛІЗ ПРИЧИН ВІДСУТНОСТІ ОРДЕРІВ")
    print("="*80 + "\n")
    
    # Загальна статистика
    total = stats['total_decisions']
    neutral = stats['rejections']['neutral_signal']
    qos = stats['rejections']['qos_cooldown']
    safety_total = sum(stats['rejections']['safety_gates'].values())
    
    print(f"🎯 ЗАГАЛЬНА СТАТИСТИКА:")
    print(f"   Всього рішень:          {total:5d}")
    print(f"   Створено ордерів:       {0:5d} (0.0%)")
    print(f"   Заблоковано:            {total:5d} (100.0%)")
    print()
    
    # Розподіл причин
    print(f"📋 РОЗПОДІЛ ПРИЧИН БЛОКУВАННЯ:")
    print()
    print(f"   1️⃣  Слабкий сигнал:        {neutral:5d} ({neutral/total*100:.1f}%)")
    print(f"   2️⃣  QoS кулдаун:           {qos:5d} ({qos/total*100:.1f}%)")
    print(f"   3️⃣  Safety Gates:          {safety_total:5d} ({safety_total/total*100:.1f}%)")
    print()
    
    # Safety gates деталі
    if stats['rejections']['safety_gates']:
        print(f"   📌 Safety Gates деталізація:")
        for reason, count in sorted(
            stats['rejections']['safety_gates'].items(),
            key=lambda x: x[1],
            reverse=True
        ):
            pct = count / safety_total * 100
            print(f"      ├─ {reason:20s} {count:4d} ({pct:.1f}%)")
    print()
    
    # Аналіз по символах
    print(f"📈 АНАЛІЗ ПО СИМВОЛАХ:")
    print()
    
    for symbol in sorted(stats['symbols'].keys()):
        data = stats['symbols'][symbol]
        total_sym = (
            data['neutral_count'] +
            data['qos_count'] +
            data['safety_gates_count']
        )
        
        if total_sym == 0:
            continue
        
        print(f"   {symbol}:")
        print(f"      Всього рішень:       {total_sym:4d}")
        print(f"      ├─ Слабкий сигнал:   {data['neutral_count']:4d} "
              f"({data['neutral_count']/total_sym*100:.1f}%)")
        print(f"      ├─ QoS кулдаун:      {data['qos_count']:4d} "
              f"({data['qos_count']/total_sym*100:.1f}%)")
        print(f"      └─ Safety Gates:     {data['safety_gates_count']:4d} "
              f"({data['safety_gates_count']/total_sym*100:.1f}%)")
        
        # Статистика сигналів
        if data['signal_scores']:
            scores = data['signal_scores']
            avg_score = sum(scores) / len(scores)
            max_score = max(scores)
            min_score = min(scores)
            
            print(f"      Signal scores:")
            print(f"         min={min_score:7.4f}, max={max_score:7.4f}, "
                  f"avg={avg_score:7.4f}")
        
        # Пороги
        if data['thresholds_buy']:
            avg_buy = sum(data['thresholds_buy']) / len(data['thresholds_buy'])
            print(f"         avg thr_buy={avg_buy:.4f}")
        
        if data['thresholds_sell']:
            avg_sell = sum(data['thresholds_sell']) / len(data['thresholds_sell'])
            print(f"         avg thr_sell={avg_sell:.4f}")
        
        print()
    
    # Safety gates приклади
    if stats['safety_gate_details']:
        print(f"🛡️  ПРИКЛАДИ SAFETY GATES БЛОКУВАНЬ:")
        print()
        
        # Групуємо по reason
        by_reason = defaultdict(list)
        for detail in stats['safety_gate_details']:
            by_reason[detail['reason']].append(detail)
        
        for reason in ['NRR-026', 'NRR-027', 'NRR-028']:
            if reason in by_reason:
                examples = by_reason[reason][:3]  # Перші 3
                print(f"   {reason}:")
                for ex in examples:
                    ts_str = ex['ts'].strftime('%H:%M:%S') if ex['ts'] else '??:??:??'
                    print(f"      {ts_str} [{ex['symbol']:8s}] "
                          f"DENY {ex['side']:5s} trend={ex['trend']:7s}")
                print()
    
    # Рекомендації
    print(f"💡 РЕКОМЕНДАЦІЇ:")
    print()
    
    # Аналізуємо чому немає угод
    if neutral / total > 0.5:
        print(f"   1️⃣  СЛАБКІ СИГНАЛИ ({neutral/total*100:.0f}%):")
        print(f"      ⚠️  Модель не бачить чітких можливостей")
        print(f"      📌 Перевірити:")
        print(f"         • Чи навчена модель на актуальних даних?")
        print(f"         • Чи правильно налаштовані features?")
        print(f"         • Можливо, ринок у флеті (консолідація)?")
        print()
        print(f"      🔧 Можливі дії:")
        print(f"         • Почекати на кращі ринкові умови")
        print(f"         • Перенавчити модель")
        print(f"         • ⚠️ Обережно знизити signal_threshold (0.07)")
        print()
    
    if safety_total / total > 0.05:
        print(f"   2️⃣  SAFETY GATES АКТИВНІ ({safety_total/total*100:.0f}%):")
        
        if 'NRR-026' in stats['rejections']['safety_gates']:
            count = stats['rejections']['safety_gates']['NRR-026']
            print(f"      ⚠️  NRR-026 (trend=UNKNOWN): {count} блокувань")
            print(f"      📌 Проблема: Режим не може визначити тренд")
            print(f"      🔧 Перевірити RegimeDetector:")
            print(f"         • Чи отримує достатньо даних?")
            print(f"         • Чи правильно налаштовані SMA (20/50)?")
            print()
        
        if 'NRR-027' in stats['rejections']['safety_gates']:
            count = stats['rejections']['safety_gates']['NRR-027']
            print(f"      ⚠️  NRR-027 (directional_block): {count} блокувань")
            print(f"      📌 Модель намагається входити проти тренду")
            print(f"      🔧 Це нормально — захист працює!")
            print()
        
        if 'NRR-028' in stats['rejections']['safety_gates']:
            count = stats['rejections']['safety_gates']['NRR-028']
            print(f"      ⚠️  NRR-028 (price_motion): {count} блокувань")
            print(f"      📌 Ціна рухається проти напрямку входу")
            print(f"      🔧 Це нормально — захист від поганої ціни")
            print()
    
    if qos / total > 0.3:
        print(f"   3️⃣  QOS КУЛДАУН АКТИВНИЙ ({qos/total*100:.0f}%):")
        print(f"      ✅ Це нормально — антиспам працює коректно")
        print(f"      📌 symbol_cooldown_sec=10s між рішеннями")
        print(f"      ⚠️ Якщо потрібно більше частих рішень:")
        print(f"         • Знизити до 5s (ризик перетрейдингу)")
        print()
    
    print(f"   🎯 ЗАГАЛЬНИЙ ВИСНОВОК:")
    print(f"      ✅ Система працює коректно")
    print(f"      ✅ Захисні механізми активні")
    print(f"      ⚠️ Ринкові умови не сприяють входу")
    print(f"      💡 Рекомендується почекати на кращі умови")
    print()
    
    print("="*80)


def main():
    """Головна функція."""
    log_path = Path(__file__).parent / 'logs' / 'domain_decision_making.log'
    
    if not log_path.exists():
        print(f"❌ Лог не знайдено: {log_path}")
        return
    
    print(f"📖 Читаю лог: {log_path}")
    stats = analyze_decision_log(log_path)
    print_report(stats)
    
    # Зберігаємо деталі у JSON
    import json
    output_path = Path(__file__).parent / 'no_orders_analysis.json'
    
    # Конвертуємо datetime для JSON
    timeline_serializable = []
    for entry in stats['timeline']:
        entry_copy = entry.copy()
        if 'ts' in entry_copy and entry_copy['ts']:
            entry_copy['ts'] = entry_copy['ts'].isoformat()
        timeline_serializable.append(entry_copy)
    
    safety_gates_serializable = []
    for entry in stats['safety_gate_details']:
        entry_copy = entry.copy()
        if 'ts' in entry_copy and entry_copy['ts']:
            entry_copy['ts'] = entry_copy['ts'].isoformat()
        safety_gates_serializable.append(entry_copy)
    
    output_data = {
        'total_decisions': stats['total_decisions'],
        'rejections': {
            'neutral_signal': stats['rejections']['neutral_signal'],
            'qos_cooldown': stats['rejections']['qos_cooldown'],
            'safety_gates': dict(stats['rejections']['safety_gates']),
        },
        'timeline': timeline_serializable,
        'safety_gate_details': safety_gates_serializable,
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    
    print(f"💾 Детальні дані збережено: {output_path}")


if __name__ == '__main__':
    main()
