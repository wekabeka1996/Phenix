#!/usr/bin/env python3
"""
TEST RUN REALISTIC - Тест з реалістичними цінами що хітатимуть TP/SL

Генерує ордери та цінові рухи що насправді виконуватимуть TP/SL
"""

import json
import time
import subprocess
import threading
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).parent
LOG_FILE = BASE_DIR.parent / "logs" / "event_chain.log"
RESULTS_FILE = BASE_DIR / "results.jsonl"
ACTIVE_FILE = BASE_DIR / "active_orders.json"

def generate_realistic_test_events():
    """Генерує рішистичні события з ордерами та цінами"""
    events = []

    # СЦЕНАРІЙ 1: SOLUSDT - ціна йде вверх (WIN для більшості варіантів)
    # Entry: 250, SL: 247.5 (базово), TP: 251 (Conservative) до 253.75 (Scalp)
    events.append({
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "EVT:ORDER_OPENED",
        "rid": "test-order-sol-001",
        "symbol": "SOLUSDT",
        "entry_price": 250.0,
        "stage": "test"
    })

    # Цінові рухи - перевіряємо послідовно
    prices_sol = [
        250.25,  # +0.25
        250.50,  # +0.50
        251.00,  # +1.00 - хітає Conservative TP
        251.50,  # +1.50 - хітає Balanced-Low TP
        252.50,  # +2.50 - хітає Balanced-High TP
        253.00,  # +3.00 - хітає Aggressive-Tight TP
        253.75,  # +3.75 - хітає Scalp TP
    ]

    for price in prices_sol:
        events.append({
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "EVT:PRICE_UPDATE",
            "symbol": "SOLUSDT",
            "price": price,
            "stage": "test"
        })
        time.sleep(0.05)

    # Невеликий перерва
    time.sleep(0.2)

    # СЦЕНАРІЙ 2: ETHUSDT - ціна йде вниз (LOSS для більшості варіантів)
    # Entry: 2800, SL варіює від 2779 (Scalp) до 2793 (Conservative)
    events.append({
        "timestamp": datetime.utcnow().isoformat(),
        "event_type": "EVT:ORDER_OPENED",
        "rid": "test-order-eth-001",
        "symbol": "ETHUSDT",
        "entry_price": 2800.0,
        "stage": "test"
    })

    # Цінові рухи вниз
    prices_eth = [
        2799.0,   # -1
        2797.0,   # -3
        2793.0,   # -7 - хітає Scalp SL
        2788.8,   # -11.2 - хітає Aggressive-Tight SL
        2786.0,   # -14 - хітає Balanced-Low та Balanced-High SL
        2779.0,   # -21 - хітає Conservative SL
    ]

    for price in prices_eth:
        events.append({
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "EVT:PRICE_UPDATE",
            "symbol": "ETHUSDT",
            "price": price,
            "stage": "test"
        })
        time.sleep(0.05)

    # Запишемо в лог
    with open(LOG_FILE, 'a') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')

    return len(events)

def run_simulator():
    """Запускає симулятор на 15 секунд"""
    proc = subprocess.Popen(
        ["python", "monitor.py"],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    time.sleep(15)
    proc.terminate()

    try:
        stdout, stderr = proc.communicate(timeout=5)
        return stdout.decode(), stderr.decode()
    except subprocess.TimeoutExpired:
        proc.kill()
        return "", "Timeout"

def show_results():
    """Показує результати симуляції"""
    print("\n" + "="*80)
    print("РЕЗУЛЬТАТИ РЕАЛІСТИЧНОГО ТЕСТУ")
    print("="*80)

    # Активні ордери
    if ACTIVE_FILE.exists():
        with open(ACTIVE_FILE) as f:
            active = json.load(f)
        print(f"\nАктивні ордери: {len(active)}")
        for order_id, positions in active.items():
            print(f"  {order_id}:")
            for pos in positions:
                print(f"    - {pos['variant_id']}: {pos['status']} (TP: {pos['tp_price']:.2f}, SL: {pos['sl_price']:.2f})")

    # Результати
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            results = [json.loads(line) for line in f if line.strip()]

        print(f"\nЗакритих позицій: {len(results)}")

        wins = [r for r in results if r['result'] == 'WIN']
        losses = [r for r in results if r['result'] == 'LOSS']

        print(f"\n  WIN: {len(wins)}")
        for r in wins:
            print(f"    {r['variant_name']}: {r['symbol']} @ {r['close_price']:.2f} | PNL: {r['pnl']:+.2f}")

        print(f"\n  LOSS: {len(losses)}")
        for r in losses:
            print(f"    {r['variant_name']}: {r['symbol']} @ {r['close_price']:.2f} | PNL: {r['pnl']:+.2f}")

        # Статистика по варіантах
        from collections import defaultdict
        by_variant = defaultdict(lambda: {"wins": 0, "losses": 0, "total_pnl": 0})

        for r in results:
            variant = r['variant_name']
            by_variant[variant]["wins" if r['result'] == 'WIN' else "losses"] += 1
            by_variant[variant]["total_pnl"] += r['pnl']

        print("\n📊 СТАТИСТИКА ПО ВАРІАНТАХ:")
        print(f"{'Варіант':<20} {'W':<3} {'L':<3} {'WR%':<8} {'PNL':<10}")
        print("-" * 50)
        for variant in sorted(by_variant.keys()):
            stats = by_variant[variant]
            total = stats["wins"] + stats["losses"]
            wr = (stats["wins"] / total * 100) if total > 0 else 0
            print(f"{variant:<20} {stats['wins']:<3} {stats['losses']:<3} {wr:<8.1f} {stats['total_pnl']:+<10.2f}")

if __name__ == "__main__":
    print("📊 Реалістичний Тест Order Simulator")
    print("="*80)

    # Очищуємо попередні результати
    RESULTS_FILE.unlink(missing_ok=True)
    ACTIVE_FILE.unlink(missing_ok=True)

    print("\n1️⃣  Генерування реалістичних подій...")
    num_events = generate_realistic_test_events()
    print(f"   ✅ Генеровано {num_events} подій")
    print(f"   📝 SOLUSDT: Entry 250 → ціна йде вверх (WIN)")
    print(f"   📝 ETHUSDT: Entry 2800 → ціна йде вниз (LOSS)")

    print("\n2️⃣  Запуск симулятора на 15 секунд...")
    stdout, stderr = run_simulator()

    print("\n3️⃣  Вихідні дані симулятора:")
    if stderr:
        # Показуємо останні 10 рядків логу
        lines = stderr.split('\n')
        for line in lines[-10:]:
            if line.strip():
                print(f"   {line}")

    print("\n4️⃣  Показання результатів...")
    show_results()
    print("\n" + "="*80)
