import sqlite3
import json
from pathlib import Path
import time
from collections import defaultdict
from pprint import pprint

# Шляхи до поточних артефактів
DB_PATH = Path("data/order_ledger.db")
LOG_PATHS = [
    Path("logs/trade_lifecycle.jsonl"),
    Path("logs/order_log_v1.jsonl"),
    Path("logs/aurora_core.log")
]

def analyze_current_runtime():
    print("="*80)
    print("🔬 CURRENT RUNTIME FORENSIC AUDIT (Last 12+ Hours)")
    print("="*80)

    # 1. Збір даних з SQLite (order_ledger.db)
    db_orders = {}
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Беремо останні 500 ордерів (приблизно поточний рантайм)
            cursor.execute("SELECT * FROM orders ORDER BY rowid DESC LIMIT 500")
            for row in cursor.fetchall():
                db_orders[row['client_order_id']] = dict(row)
            conn.close()
            print(f"[+] Завантажено {len(db_orders)} останніх ордерів з order_ledger.db")
        except Exception as e:
            print(f"[!] Помилка читання БД: {e}")
    else:
        print(f"[!] БД не знайдена: {DB_PATH}")

    # 2. Парсинг JSONL логів
    events_by_rid = defaultdict(list)
    global_errors = []
    
    # Ключові слова для пошуку
    error_keywords = ["-1111", "Precision is over the maximum", "BRACKET_PLACEMENT_FAILED", "force_reduce_only_close"]

    for log_path in LOG_PATHS:
        if not log_path.exists():
            continue
        print(f"[+] Парсинг {log_path.name}...")
        
        is_jsonl = log_path.suffix == '.jsonl'
        with open(log_path, 'r', encoding='utf-8') as f:
            for line in f:
                if not line.strip(): continue
                
                # Пошук глобальних помилок (навіть якщо рядок не JSON)
                for kw in error_keywords:
                    if kw in line:
                        global_errors.append((log_path.name, line.strip()[:200]))

                if is_jsonl:
                    try:
                        evt = json.loads(line)
                        pld = evt.get("pld", evt.get("payload", evt))
                        
                        # Визначаємо кореляційний ID (rid або clientOrderId)
                        rid = str(pld.get("rid") or evt.get("rid") or pld.get("clientOrderId") or pld.get("client_order_id") or "")
                        if rid:
                            verb = evt.get("verb") or evt.get("event_type") or evt.get("event_name") or "UNKNOWN"
                            events_by_rid[rid].append((verb, pld))
                    except json.JSONDecodeError:
                        pass

    # 3. Аналіз Життєвого Циклу (Lifecycle Analysis)
    print("\n" + "="*80)
    print("📊 TRADE LIFECYCLE TABLE (Current Runtime)")
    print(f"{'SYMBOL':<12} | {'SIDE':<5} | {'ENTRY_ID':<25} | {'FILLED':<6} | {'PENDING_BRACKETS':<16} | {'CHILD_SL':<10} | {'CHILD_TP':<10} | {'REJECTS / ANOMALIES'}")
    print("-" * 120)

    # Групуємо події по rid (вважаємо rid ідентифікатором Entry ордера)
    for rid, events in events_by_rid.items():
        # Відфільтровуємо тільки ті rid, де була спроба входу (TRADE_INTENT_PROPOSED або ORDER_STATE_CHANGED)
        verbs = [e[0] for e in events]
        if "TRADE_INTENT_PROPOSED" not in verbs and "ORDER_STATE_CHANGED" not in verbs and "EVT:TRADE_INTENT_PROPOSED" not in verbs:
            continue

        symbol = "UNKNOWN"
        side = "UNK"
        filled = "No"
        pending_brackets = "No"
        child_sl = "Unknown"
        child_tp = "Unknown"
        anomalies = []

        for verb, pld in events:
            symbol = pld.get("symbol", symbol)
            side = pld.get("side", side)
            
            if verb in ["ORDER_STATE_CHANGED", "EVT:ORDER_STATE_CHANGED"]:
                status = pld.get("status", "")
                if status == "FILLED": filled = "Yes"
                if status in ["CANCELED", "REJECTED", "EXPIRED"]: filled = f"No({status})"
            
            if verb in ["PENDING_BRACKETS_STORED", "EVT:PENDING_BRACKETS_STORED"]:
                pending_brackets = "Yes"
            
            if verb in ["PENDING_BRACKETS_CLEARED", "EVT:PENDING_BRACKETS_CLEARED"]:
                anomalies.append("CLEARED")
                
            if verb in ["BRACKET_PLACEMENT_FAILED", "EVT:BRACKET_PLACEMENT_FAILED"]:
                anomalies.append("BRACKET_FAIL")
                
            if verb in ["ORDER_REJECTED", "EVT:ORDER_REJECTED"]:
                reason = pld.get("reason") or pld.get("deny_reason", "")
                anomalies.append(f"REJECT:{str(reason)[:20]}")

        # Перевірка в SQLite для підтвердження дочірніх ордерів
        sl_found = False
        tp_found = False
        for db_cid, db_row in db_orders.items():
            if rid in db_cid and db_cid != rid:
                if "_sl" in db_cid.lower() or "stop_loss" in db_cid.lower(): sl_found = True
                if "_tp" in db_cid.lower() or "take_profit" in db_cid.lower(): tp_found = True
        
        if sl_found: child_sl = "Yes"
        elif pending_brackets == "Yes": child_sl = "Missing"
        
        if tp_found: child_tp = "Yes"
        elif pending_brackets == "Yes": child_tp = "Missing"

        anomaly_str = ", ".join(anomalies) if anomalies else "None"
        print(f"{symbol:<12} | {side:<5} | {rid:<25} | {filled:<6} | {pending_brackets:<16} | {child_sl:<10} | {child_tp:<10} | {anomaly_str}")

    print("\n" + "="*80)
    print("🚨 GLOBAL ERRORS & PRECISION DEFECTS (Targeted Search)")
    print("="*80)
    if global_errors:
        for source, err in global_errors:
            print(f"[{source}] {err}")
    else:
        print("[+] Жодної згадки про -1111, Precision errors або force_reduce_only_close не знайдено.")

if __name__ == "__main__":
    analyze_current_runtime()
