#!/usr/bin/env python3
"""
TEST RUN - Тестування симулятора з фейковими даними

Цей скрипт:
1. Генерує фейкові ордери в лог
2. Запускає симулятор на 10 секунд
3. Показує результати
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


def generate_test_events():
    """Генерує фейкові события з ордерами"""
    events = [
        # Ордер 1: SOLUSDT @ 150
        {
            "timestamp": datetime.utcnow().isoformat(),
            "level": "INFO",
            "logger": "event_chain",
            "message": "Test order opened",
            "event_type": "EVT:ORDER_OPENED",
            "rid": "test-order-001",
            "symbol": "SOLUSDT",
            "entry_price": 150.0,
            "stage": "test"
        },
        # Цінові оновлення для SOLUSDT
        {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "EVT:PRICE_UPDATE",
            "symbol": "SOLUSDT",
            "price": 152.5,
            "stage": "test"
        },
        {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "EVT:PRICE_UPDATE",
            "symbol": "SOLUSDT",
            "price": 155.0,
            "stage": "test"
        },
        # Ордер 2: ETHUSDT @ 2800
        {
            "timestamp": datetime.utcnow().isoformat(),
            "level": "INFO",
            "logger": "event_chain",
            "message": "Test order opened",
            "event_type": "EVT:ORDER_OPENED",
            "rid": "test-order-002",
            "symbol": "ETHUSDT",
            "entry_price": 2800.0,
            "stage": "test"
        },
        # Цінові оновлення для ETHUSDT
        {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": "EVT:PRICE_UPDATE",
            "symbol": "ETHUSDT",
            "price": 2799.0,
            "stage": "test"
        },
    ]

    with open(LOG_FILE, 'a') as f:
        for event in events:
            f.write(json.dumps(event) + '\n')
            time.sleep(0.1)


def run_simulator():
    """Запускає симулятор на 10 секунд"""
    proc = subprocess.Popen(
        ["python", "monitor.py"],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    time.sleep(10)
    proc.terminate()

    stdout, stderr = proc.communicate(timeout=5)
    return stdout.decode(), stderr.decode()


def show_results():
    """Показує результати симуляції"""
    print("\n" + "="*80)
    print("РЕЗУЛЬТАТИ ТЕСТУВАННЯ")
    print("="*80)

    # Активні ордери
    if ACTIVE_FILE.exists():
        with open(ACTIVE_FILE) as f:
            active = json.load(f)
        print(f"\nАктивні ордери: {len(active)}")
        for order_id, positions in active.items():
            print(f"  {order_id}:")
            for pos in positions:
                print(
                    f"    - {pos['variant_id']}: {pos['status']} (TP: {pos['tp_price']}, SL: {pos['sl_price']})")

    # Результати
    if RESULTS_FILE.exists():
        with open(RESULTS_FILE) as f:
            results = [json.loads(line) for line in f if line.strip()]

        print(f"\nЗакритих позицій: {len(results)}")

        wins = [r for r in results if r['result'] == 'WIN']
        losses = [r for r in results if r['result'] == 'LOSS']

        print(f"  WIN: {len(wins)}")
        print(f"  LOSS: {len(losses)}")

        if wins:
            print("\n  Переможні варіанти:")
            for r in wins:
                print(
                    f"    {r['variant_name']}: {r['symbol']} @ {r['close_price']} (PNL: {r['pnl']:.2f})")

        if losses:
            print("\n  Програшні варіанти:")
            for r in losses:
                print(
                    f"    {r['variant_name']}: {r['symbol']} @ {r['close_price']} (PNL: {r['pnl']:.2f})")


if __name__ == "__main__":
    print("📊 Тест Order Simulator")
    print("="*80)

    # Очищуємо попередні результати
    RESULTS_FILE.unlink(missing_ok=True)
    ACTIVE_FILE.unlink(missing_ok=True)

    print("\n1️⃣  Генерування фейкових подій...")
    generate_test_events()
    print(f"   ✅ {LOG_FILE.stat().st_size} bytes in log")

    print("\n2️⃣  Запуск симулятора на 10 секунд...")
    stdout, stderr = run_simulator()

    print("\n3️⃣  Симулятор вихідні дані:")
    if stdout:
        print("   STDOUT:")
        for line in stdout.split('\n')[-5:]:
            if line:
                print(f"     {line}")
    if stderr:
        print("   STDERR:")
        for line in stderr.split('\n')[-5:]:
            if line:
                print(f"     {line}")

    print("\n4️⃣  Показання результатів...")
    show_results()
    print("\n" + "="*80)
