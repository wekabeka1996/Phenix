import sqlite3
import json
from pathlib import Path

# Цільові інциденти
TARGET_ORDERS = {
    "ETH": "8668181482",
    "BNB": "1348445581",
    "BTC": "13083061912"
}

DB_PATH = Path("data/order_ledger.db")
LOG_PATHS = [
    Path("logs/order_log_v1.jsonl"),
    Path("tmp_phase2_debug/trade_lifecycle.jsonl"),
    Path("logs/event_chain.log")
]

def analyze_sqlite_ledger():
    print("="*80)
    print("📂 PHASE 1: SQLite Order Ledger (Venue Truth Reconstruction)")
    print("="*80)
    
    if not DB_PATH.exists():
        print(f"❌ База даних не знайдена: {DB_PATH}")
        return

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        for asset, order_id in TARGET_ORDERS.items():
            print(f"\n🔍 Шукаю Parent Order: {asset} (ID: {order_id})")
            
            # Шукаємо сам ордер
            cursor.execute("SELECT * FROM orders WHERE exchange_order_id = ? OR client_order_id LIKE ?", (order_id, f"%{order_id}%"))
            parent = cursor.fetchone()
            
            if not parent:
                print(f"   [!] Parent Order {order_id} НЕ ЗНАЙДЕНО в локальній БД.")
            else:
                print(f"   [+] Parent Status: {parent['status']} | Type: {parent['order_type']} | Qty: {parent['quantity']}")
                client_id = parent['client_order_id']
                
                # Шукаємо дочірні ордери (SL/TP) за client_id (зазвичай вони містять parent_id + суфікс _sl / _tp)
                cursor.execute("SELECT * FROM orders WHERE client_order_id LIKE ?", (f"%{client_id}%_sl%",))
                sl_orders = cursor.fetchall()
                print(f"   [+] Child SL Orders found: {len(sl_orders)}")
                for sl in sl_orders:
                    print(f"       -> SL Status: {sl['status']} | Exchange ID: {sl['exchange_order_id']} | Price: {sl['price']}")

                cursor.execute("SELECT * FROM orders WHERE client_order_id LIKE ?", (f"%{client_id}%_tp%",))
                tp_orders = cursor.fetchall()
                print(f"   [+] Child TP Orders found: {len(tp_orders)}")
                for tp in tp_orders:
                    print(f"       -> TP Status: {tp['status']} | Exchange ID: {tp['exchange_order_id']} | Price: {tp['price']}")

        conn.close()
    except sqlite3.Error as e:
        print(f"Помилка читання БД: {e}")

def analyze_jsonl_logs():
    print("\n" + "="*80)
    print("📜 PHASE 2: JSONL Lifecycle Trace (Observability & Anomaly Audit)")
    print("="*80)

    target_ids = set(TARGET_ORDERS.values())
    found_events = {oid: [] for oid in target_ids}

    for log_path in LOG_PATHS:
        if not log_path.exists():
            continue
            
        print(f"Читаю: {log_path.name}...")
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                for oid in target_ids:
                    # Шукаємо будь-яку згадку цільового ID у рядку
                    if oid in line:
                        try:
                            event = json.loads(line)
                            verb = event.get("verb") or event.get("event_type") or "UNKNOWN"
                            found_events[oid].append((verb, event))
                        except json.JSONDecodeError:
                            pass

    for asset, oid in TARGET_ORDERS.items():
        print(f"\n🔬 Хронологія для {asset} ({oid}):")
        events = found_events[oid]
        if not events:
            print("   [!] Жодної події не знайдено в логах.")
            continue
            
        # Спрощена хронологія
        for verb, evt in events:
            payload = evt.get("pld", evt.get("payload", {}))
            reason = payload.get("reason", payload.get("deny_reason", payload.get("reject_reason", "")))
            print(f"   -> {verb} | Reason: {str(reason)[:60]}")

if __name__ == "__main__":
    analyze_sqlite_ledger()
    analyze_jsonl_logs()