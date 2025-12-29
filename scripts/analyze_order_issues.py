"""
Аналіз причин чому нові ордери не відкриваються.
Парсимо domain_execution_management.log та aurora_core.log
"""
import re
from collections import defaultdict, Counter
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"

def parse_timestamp(ts_str: str) -> datetime:
    """Parse log timestamp."""
    try:
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S,%f")
    except:
        return None

def analyze_execution_log():
    """Аналіз domain_execution_management.log"""
    log_file = LOG_DIR / "domain_execution_management.log"
    if not log_file.exists():
        print(f"❌ Файл не знайдено: {log_file}")
        return

    print("=" * 80)
    print("📊 АНАЛІЗ domain_execution_management.log")
    print("=" * 80)

    content = log_file.read_text(encoding='utf-8', errors='ignore')
    lines = content.split('\n')

    # Лічильники
    entry_intents = []  # (timestamp, symbol, side, qty, price)
    place_success = []
    place_failures = []
    cancel_success = []
    watchdog_violations = []
    skip_brackets = []
    apply_brackets = []

    # Паттерни
    entry_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*ENTRY_INTENT received: symbol=(\w+) side=(\w+) qty=([\d.]+)')
    place_cmd_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*execute_command verb=PLACE symbol=(\w+).*price.*?\'([\d.]+)\'')
    place_success_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*SHADOW_EXEC_POS_PLACE_SUCCESS')
    cancel_success_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*SHADOW_EXEC_POS_CANCEL_SUCCESS')
    watchdog_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*WATCHDOG_VIOLATION_DETECTED')
    skip_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*SKIP_BRACKETS_LOW_PRIORITY symbol=(\w+) blocked_reason=(\w+) in_flight_reason=(\w+) dt=([\d.]+)s')
    apply_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*APPLY_BRACKETS symbol=(\w+) reason=(\w+) actions_count=(\d+)')

    for line in lines:
        if m := entry_pattern.search(line):
            entry_intents.append({
                'ts': m.group(1),
                'symbol': m.group(2),
                'side': m.group(3),
                'qty': m.group(4)
            })
        elif m := place_success_pattern.search(line):
            place_success.append(m.group(1))
        elif m := cancel_success_pattern.search(line):
            cancel_success.append(m.group(1))
        elif m := watchdog_pattern.search(line):
            watchdog_violations.append(m.group(1))
        elif m := skip_pattern.search(line):
            skip_brackets.append({
                'ts': m.group(1),
                'symbol': m.group(2),
                'blocked_reason': m.group(3),
                'in_flight_reason': m.group(4),
                'dt_sec': float(m.group(5))
            })
        elif m := apply_pattern.search(line):
            apply_brackets.append({
                'ts': m.group(1),
                'symbol': m.group(2),
                'reason': m.group(3),
                'actions_count': int(m.group(4))
            })

    # --- Статистика ---
    print(f"\n📈 СТАТИСТИКА ЗА СЕСІЮ:")
    print(f"   ENTRY_INTENT отримано:     {len(entry_intents)}")
    print(f"   PLACE_SUCCESS:             {len(place_success)}")
    print(f"   CANCEL_SUCCESS:            {len(cancel_success)}")
    print(f"   WATCHDOG_VIOLATION:        {len(watchdog_violations)}")
    print(f"   SKIP_BRACKETS:             {len(skip_brackets)}")
    print(f"   APPLY_BRACKETS:            {len(apply_brackets)}")

    # --- Entry Intents по символах ---
    print(f"\n📊 ENTRY_INTENT по символах:")
    symbol_counts = Counter(e['symbol'] for e in entry_intents)
    for sym, cnt in symbol_counts.most_common():
        print(f"   {sym}: {cnt}")

    # --- SKIP_BRACKETS аналіз ---
    if skip_brackets:
        print(f"\n⚠️  SKIP_BRACKETS_LOW_PRIORITY (ордери пропущені):")
        blocked_reasons = Counter(s['blocked_reason'] for s in skip_brackets)
        in_flight_reasons = Counter(s['in_flight_reason'] for s in skip_brackets)
        avg_dt = sum(s['dt_sec'] for s in skip_brackets) / len(skip_brackets)
        max_dt = max(s['dt_sec'] for s in skip_brackets)

        print(f"   blocked_reason розподіл:")
        for reason, cnt in blocked_reasons.most_common():
            print(f"      {reason}: {cnt}")
        print(f"   in_flight_reason розподіл:")
        for reason, cnt in in_flight_reasons.most_common():
            print(f"      {reason}: {cnt}")
        print(f"   Середній dt: {avg_dt:.1f} сек")
        print(f"   Макс dt:     {max_dt:.1f} сек")

    # --- APPLY_BRACKETS аналіз ---
    if apply_brackets:
        print(f"\n🔄 APPLY_BRACKETS (спроби накласти brackets):")
        reasons = Counter(a['reason'] for a in apply_brackets)
        for reason, cnt in reasons.most_common():
            print(f"   {reason}: {cnt}")

    # --- Головні проблеми ---
    print("\n" + "=" * 80)
    print("🚨 ГОЛОВНІ ПРОБЛЕМИ:")
    print("=" * 80)

    issues = []

    # 1. Багато WATCHDOG порушень
    if len(watchdog_violations) > 5:
        issues.append(f"🔴 WATCHDOG_VIOLATION x{len(watchdog_violations)} — система не встигає обробляти snapshot/bracket")

    # 2. SKIP_BRACKETS з великим dt
    long_skips = [s for s in skip_brackets if s['dt_sec'] > 30]
    if long_skips:
        issues.append(f"🔴 SKIP_BRACKETS з dt > 30s x{len(long_skips)} — ордери застрягли в черзі brackets")

    # 3. Постійні CANCEL/PLACE цикли для brackets
    if len(apply_brackets) > len(entry_intents) * 2:
        issues.append(f"🟡 BRACKET_CHURN — занадто багато APPLY_BRACKETS ({len(apply_brackets)}) відносно нових ордерів ({len(entry_intents)})")

    # 4. ENTRY_INTENT без відповідних PLACE_SUCCESS
    # (потрібно детальніший аналіз пар)

    for issue in issues:
        print(f"   {issue}")

    if not issues:
        print("   ✅ Явних проблем не виявлено")

def analyze_aurora_log():
    """Аналіз aurora_core.log на предмет помилок"""
    log_file = LOG_DIR / "aurora_core.log"
    if not log_file.exists():
        print(f"❌ Файл не знайдено: {log_file}")
        return

    print("\n" + "=" * 80)
    print("📊 АНАЛІЗ aurora_core.log")
    print("=" * 80)

    content = log_file.read_text(encoding='utf-8', errors='ignore')
    lines = content.split('\n')

    # Шукаємо помилки
    errors = []
    timestamp_errors = []
    api_errors = []

    for line in lines:
        if 'ERROR' in line:
            errors.append(line)
        if '-1021' in line or 'Timestamp' in line and 'recvWindow' in line:
            timestamp_errors.append(line)
        if 'BinanceAPIError' in line:
            api_errors.append(line)

    print(f"\n📈 ПОМИЛКИ:")
    print(f"   ERROR записів:         {len(errors)}")
    print(f"   -1021 (timestamp):     {len(timestamp_errors)}")
    print(f"   BinanceAPIError:       {len(api_errors)}")

    if timestamp_errors:
        print(f"\n⚠️  Останні -1021 помилки:")
        for err in timestamp_errors[-5:]:
            # Обрізаємо до 120 символів
            print(f"   {err[:150]}...")

    if api_errors:
        print(f"\n⚠️  Останні BinanceAPIError:")
        for err in api_errors[-5:]:
            print(f"   {err[:150]}...")

def analyze_order_flow():
    """Аналіз потоку ордерів: Intent → Gatekeeper → Adapter → Response"""
    log_file = LOG_DIR / "domain_execution_management.log"
    if not log_file.exists():
        return

    print("\n" + "=" * 80)
    print("📊 АНАЛІЗ ПОТОКУ ОРДЕРІВ")
    print("=" * 80)

    content = log_file.read_text(encoding='utf-8', errors='ignore')

    # Рахуємо час від ENTRY_INTENT до PLACE_SUCCESS
    entry_times = {}
    success_times = []

    entry_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*ENTRY_INTENT received: symbol=(\w+)')
    place_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*execute_command verb=PLACE symbol=(\w+)')
    success_pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}).*SHADOW_EXEC_POS_PLACE_SUCCESS')

    lines = content.split('\n')

    pending_place = None
    place_times = []

    for line in lines:
        if m := place_pattern.search(line):
            pending_place = parse_timestamp(m.group(1))
        elif m := success_pattern.search(line):
            if pending_place:
                success_ts = parse_timestamp(m.group(1))
                if success_ts and pending_place:
                    delta = (success_ts - pending_place).total_seconds()
                    place_times.append(delta)
                pending_place = None

    if place_times:
        avg_time = sum(place_times) / len(place_times)
        max_time = max(place_times)
        min_time = min(place_times)

        print(f"\n⏱️  ЧАС ВИКОНАННЯ PLACE → SUCCESS:")
        print(f"   Середній: {avg_time:.2f} сек")
        print(f"   Мін:      {min_time:.2f} сек")
        print(f"   Макс:     {max_time:.2f} сек")
        print(f"   Кількість: {len(place_times)}")

        # Розподіл по бакетах
        buckets = defaultdict(int)
        for t in place_times:
            if t < 1:
                buckets['< 1s'] += 1
            elif t < 5:
                buckets['1-5s'] += 1
            elif t < 30:
                buckets['5-30s'] += 1
            else:
                buckets['> 30s'] += 1

        print(f"\n   Розподіл:")
        for bucket in ['< 1s', '1-5s', '5-30s', '> 30s']:
            if bucket in buckets:
                pct = buckets[bucket] / len(place_times) * 100
                print(f"      {bucket}: {buckets[bucket]} ({pct:.1f}%)")

        if buckets['> 30s'] > 0:
            print(f"\n   🔴 КРИТИЧНО: {buckets['> 30s']} ордерів виконувались > 30 сек!")

def print_recommendations():
    """Рекомендації на основі аналізу"""
    print("\n" + "=" * 80)
    print("💡 РЕКОМЕНДАЦІЇ")
    print("=" * 80)

    print("""
1. 🔴 WATCHDOG_VIOLATION частий
   → Перевірте чи не блокується event loop
   → Збільште watchdog timeout або вимкніть його тимчасово

2. 🔴 SKIP_BRACKETS_LOW_PRIORITY з великим dt
   → Brackets блокуються через in_flight операції
   → Можливо варто відключити bracket auto-management тимчасово

3. 🟡 BRACKET_CHURN (постійні CANCEL/PLACE циклі)
   → Bracket engine перевстановлює TP/SL при кожному snapshot
   → Перевірте чи правильно порівнюються поточні vs бажані brackets

4. 🔴 Повільні PLACE операції (> 30s)
   → Перевірте мережу до Binance
   → Можливо є rate limiting
   → Перевірте time sync (-1021)

5. ⚠️ Missing instrument specs
   → Gatekeeper використовує fallback значення
   → Завантажте правильні specs з exchangeInfo
""")

def main():
    print("🔍 АНАЛІЗ ПРИЧИН ЧОМУ НОВІ ОРДЕРИ НЕ ВІДКРИВАЮТЬСЯ")
    print(f"📁 Директорія логів: {LOG_DIR}")
    print()

    analyze_execution_log()
    analyze_aurora_log()
    analyze_order_flow()
    print_recommendations()

if __name__ == "__main__":
    main()
