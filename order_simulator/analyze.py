#!/usr/bin/env python3
"""
RESULTS ANALYZER - Аналізатор результатів симуляції

Читає results.jsonl та показує статистику по варіантах
"""

import json
from pathlib import Path
from collections import defaultdict
from datetime import datetime

BASE_DIR = Path(__file__).parent
RESULTS_FILE = BASE_DIR / "results.jsonl"

def load_results():
    """Завантажує всі результати"""
    if not RESULTS_FILE.exists():
        print(f"❌ Файл не знайдено: {RESULTS_FILE}")
        return []

    results = []
    with open(RESULTS_FILE) as f:
        for line in f:
            if line.strip():
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    return results

def analyze_by_variant(results):
    """Аналізує результати по варіантах"""
    by_variant = defaultdict(lambda: {
        "wins": 0,
        "losses": 0,
        "total_pnl": 0.0,
        "avg_pnl": 0.0,
        "max_win": float('-inf'),
        "max_loss": float('inf'),
        "pnl_list": []
    })

    for r in results:
        variant = r['variant_name']
        pnl = r['pnl']

        if r['result'] == 'WIN':
            by_variant[variant]["wins"] += 1
            by_variant[variant]["max_win"] = max(by_variant[variant]["max_win"], pnl)
        else:
            by_variant[variant]["losses"] += 1
            by_variant[variant]["max_loss"] = min(by_variant[variant]["max_loss"], pnl)

        by_variant[variant]["total_pnl"] += pnl
        by_variant[variant]["pnl_list"].append(pnl)

    # Розраховуємо середнє
    for variant, stats in by_variant.items():
        if stats["pnl_list"]:
            stats["avg_pnl"] = sum(stats["pnl_list"]) / len(stats["pnl_list"])
        # Очищуємо список (не потрібен більше)
        del stats["pnl_list"]

    return by_variant

def analyze_by_symbol(results):
    """Аналізує результати по символах"""
    by_symbol = defaultdict(lambda: {
        "total": 0,
        "wins": 0,
        "total_pnl": 0.0
    })

    for r in results:
        symbol = r['symbol']
        by_symbol[symbol]["total"] += 1
        if r['result'] == 'WIN':
            by_symbol[symbol]["wins"] += 1
        by_symbol[symbol]["total_pnl"] += r['pnl']

    return by_symbol

def print_summary(results):
    """Показує загальну статистику"""
    if not results:
        print("❌ Немає результатів для аналізу")
        return

    total = len(results)
    wins = sum(1 for r in results if r['result'] == 'WIN')
    losses = total - wins
    total_pnl = sum(r['pnl'] for r in results)
    avg_pnl = total_pnl / total if total > 0 else 0

    print("\n📊 ЗАГАЛЬНА СТАТИСТИКА")
    print("=" * 80)
    print(f"Всього результатів: {total}")
    print(f"Перемог (WIN):      {wins} ({wins/total*100:.1f}%)")
    print(f"Програшів (LOSS):   {losses} ({losses/total*100:.1f}%)")
    print(f"Загальний PNL:      {total_pnl:+.2f}")
    print(f"Середній PNL:       {avg_pnl:+.2f}")
    print(f"Profit Factor:      {abs(total_pnl) / max(abs(sum(r['pnl'] for r in results if r['pnl'] < 0)), 0.01):.2f}" if any(r['pnl'] < 0 for r in results) else "N/A")

def print_variant_stats(by_variant):
    """Показує статистику по варіантах"""
    print("\n🎯 СТАТИСТИКА ПО ВАРІАНТАХ")
    print("=" * 80)
    print(f"{'Варіант':<20} {'W':<4} {'L':<4} {'WR%':<8} {'Avg PNL':<10} {'Total PNL':<10} {'Max W':<8} {'Max L':<8}")
    print("-" * 80)

    for variant in sorted(by_variant.keys()):
        stats = by_variant[variant]
        total = stats["wins"] + stats["losses"]
        wr = (stats["wins"] / total * 100) if total > 0 else 0

        max_w = stats["max_win"] if stats["max_win"] != float('-inf') else 0
        max_l = stats["max_loss"] if stats["max_loss"] != float('inf') else 0

        print(f"{variant:<20} {stats['wins']:<4} {stats['losses']:<4} {wr:<8.1f} {stats['avg_pnl']:+<10.2f} {stats['total_pnl']:+<10.2f} {max_w:+<8.2f} {max_l:+<8.2f}")

    # Best variant
    best = max(by_variant.items(), key=lambda x: x[1]['total_pnl'])
    worst = min(by_variant.items(), key=lambda x: x[1]['total_pnl'])

    print("\n🏆 НАЙКРАЩИЙ: " + best[0] + f" ({best[1]['total_pnl']:+.2f} PNL)")
    print("⚠️  НАЙГІРШИЙ: " + worst[0] + f" ({worst[1]['total_pnl']:+.2f} PNL)")

def print_symbol_stats(by_symbol):
    """Показує статистику по символах"""
    print("\n💱 СТАТИСТИКА ПО СИМВОЛАХ")
    print("=" * 80)
    print(f"{'Символ':<15} {'Total':<8} {'Wins':<8} {'WR%':<8} {'Total PNL':<10}")
    print("-" * 80)

    for symbol in sorted(by_symbol.keys()):
        stats = by_symbol[symbol]
        wr = (stats["wins"] / stats["total"] * 100) if stats["total"] > 0 else 0
        print(f"{symbol:<15} {stats['total']:<8} {stats['wins']:<8} {wr:<8.1f} {stats['total_pnl']:+<10.2f}")

def print_top_trades(results, limit=10):
    """Показує топ трейдів"""
    sorted_results = sorted(results, key=lambda x: x['pnl'], reverse=True)

    print(f"\n🥇 ТОП {limit} НАЙКРАЩИХ ТРЕЙДІВ")
    print("=" * 80)
    print(f"{'#':<3} {'Вар.':<20} {'Символ':<12} {'Entry':<12} {'Close':<12} {'PNL':<10}")
    print("-" * 80)

    for i, r in enumerate(sorted_results[:limit], 1):
        print(f"{i:<3} {r['variant_name']:<20} {r['symbol']:<12} {r['entry_price']:<12.2f} {r['close_price']:<12.2f} {r['pnl']:+<10.2f}")

    print(f"\n🥉 ТОП {limit} НАЙГІРШИХ ТРЕЙДІВ")
    print("=" * 80)

    for i, r in enumerate(sorted_results[-limit:], 1):
        print(f"{i:<3} {r['variant_name']:<20} {r['symbol']:<12} {r['entry_price']:<12.2f} {r['close_price']:<12.2f} {r['pnl']:+<10.2f}")

def export_csv(results, filename="analysis.csv"):
    """Експортує результати в CSV"""
    csv_path = BASE_DIR / filename

    with open(csv_path, 'w') as f:
        f.write("timestamp,order_id,variant_id,variant_name,symbol,entry_price,tp_price,sl_price,close_price,result,pnl\n")

        for r in results:
            f.write(f"{r['timestamp']},{r['order_id']},{r['variant_id']},{r['variant_name']},{r['symbol']},{r['entry_price']},{r['tp_price']},{r['sl_price']},{r['close_price']},{r['result']},{r['pnl']}\n")

    print(f"\n📄 Експортовано в: {csv_path}")

if __name__ == "__main__":
    print("📊 Аналізатор результатів Order Simulator")
    print("=" * 80)

    results = load_results()

    if not results:
        print("❌ Немає результатів для аналізу. Запусти monitor.py або test_run.py")
        exit(1)

    # Аналізуємо
    by_variant = analyze_by_variant(results)
    by_symbol = analyze_by_symbol(results)

    # Показуємо результати
    print_summary(results)
    print_variant_stats(by_variant)
    print_symbol_stats(by_symbol)
    print_top_trades(results, limit=5)

    # Експортуємо в CSV
    export_csv(results)

    print("\n" + "=" * 80)
    print(f"✅ Аналіз завершено. Обробленo {len(results)} результатів.")
