#!/usr/bin/env python3
"""
Reject/Gate Forensics — останні 72 години
Аналізує: INTENT_REJECTED, ARBITRATION_REJECT, GATE_BLOCKED, QOS_BLOCK,
           RISK_GATE, SAFETY_GATE, PRICE_MOTION, DIRECTIONAL_SANITY,
           ANTI_FLAT, ANTI_FOMO, HOLDING_PERIOD

Виводить:
  1. Топ-10 причин reject (why-код + count + % від усіх intents)
  2. Загальна кількість intents vs rejected
  3. % rejected по групах гейтів
  4. Intents що пройшли всі гейти, але не заповнились (cancelled limit orders)
"""

import re
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collections import Counter
from typing import Optional

# ─────────────────────────── CONFIG ───────────────────────────
LOGS_DIR = Path(__file__).parent.parent / "logs"
WINDOW_HOURS = 72
NOW_UTC = datetime(2026, 2, 23, 10, 0, 0, tzinfo=timezone.utc)
CUTOFF_UTC = NOW_UTC - timedelta(hours=WINDOW_HOURS)

TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

# ─────────────────────────── PATTERNS ─────────────────────────
# STRATEGY_SIGNAL_GATEWAY patterns (primary source of truth)
RE_PROCESSING = re.compile(
    r"STRATEGY_SIGNAL_GATEWAY: Processing (BUY|SELL|LONG|SHORT) signal")
RE_GATE_PASSED = re.compile(r"STRATEGY_SIGNAL_GATEWAY: All gates passed")
RE_BLOCK = re.compile(r"STRATEGY_SIGNAL_GATEWAY: BLOCK - (.+)")
RE_REJECT = re.compile(r"STRATEGY_SIGNAL_GATEWAY: REJECT - (.+)")
RE_FLIP_BLOCK = re.compile(r"FLIP_ORCHESTRATION: BLOCK - (.+)")

# Cumulative counter from risk alert line (use last value)
RE_RISK_ALERT = re.compile(
    r"Risk gate alert: ([\d.]+)% intents blocked \((\d+)/(\d+)\)")

# Additional individual reject events
RE_SAFETY_DENY = re.compile(
    r"SAFETY_GATES[:\s]+DENY (LONG|SHORT).*?reason=(\S+)")
RE_SAFETY_FLASH = re.compile(r"SAFETY_GATES[:\s]+(flash \w+ blocks \w+)")
RE_SAFETY_MOTION = re.compile(r"SAFETY_GATES[:\s]+(price_motion \w+ \w+)")
RE_ANTI_FLAT = re.compile(
    r"GATE_ANTI_FLAT_SIGMA.*?motion=([\d.]+).*?threshold=([\d.]+)")
RE_RISK_GATE = re.compile(r"Risk Gate Violation")
RE_EXPOSURE_FAIL = re.compile(
    r"EXPOSURE_FAIL_CLOSED_OPEN_BLOCKED.*?reason=(\S+)")
RE_NRR = re.compile(r"\b(NRR-\d+)\b")
RE_SAFETY_GATE = re.compile(r"SAFETY_GATE[^S]")
RE_QOS_BLOCK = re.compile(r"QOS_BLOCK[:\s]+(\S+)")
RE_HOLDING = re.compile(r"HOLDING_PERIOD[:\s]+(\S+)")
RE_INTENT_REJ = re.compile(r"INTENT_REJECTED[:\s]+(\S+)")
RE_ARB_REJ = re.compile(r"ARBITRATION_REJECT[:\s]+(\S+)")
RE_GATE_BLOCKED = re.compile(r"GATE_BLOCKED[:\s]+(\S+)")
RE_PRICE_MOTION = re.compile(r"PRICE_MOTION[:\s]+(\S+)")
RE_DIR_SANITY = re.compile(r"DIRECTIONAL_SANITY[:\s]+(\S+)")
RE_ANTI_FOMO = re.compile(r"ANTI_FOMO[:\s]+(\S+)")

# Cancelled limit orders (order guardian + execution)
RE_ORPHAN_CANCEL = re.compile(r"Orphan bracket cancelled: (\d+)")
RE_LIMIT_CANCEL = re.compile(
    r"ORDER_STATUS.*CANCELED.*type=LIMIT", re.IGNORECASE)
RE_EXPIRE = re.compile(r"order.*expired|expired.*order", re.IGNORECASE)
RE_UNFILLED = re.compile(r"filled=0.*LIMIT|LIMIT.*filled=0", re.IGNORECASE)
RE_CANCEL_LIMIT = re.compile(
    r'"status"\s*:\s*"CANCELED".*"type"\s*:\s*"LIMIT"', re.IGNORECASE)
RE_EXEC_CANCEL = re.compile(r"EXECUTION.*CANCEL|CMD.*CANCEL", re.IGNORECASE)


def parse_ts(line: str) -> Optional[datetime]:
    m = TS_RE.match(line)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def get_all_log_files() -> list[Path]:
    """Повертає всі aurora_core.log* та decision_making/risk logs у вікні 72h."""
    candidates = []
    for pattern in [
        "aurora_core.log*",
        "domain_decision_making.log*",
        "domain_risk_management.log*",
        "order_guardian.log*",
        "event_chain.log*",
        "order_log_v1.jsonl",
    ]:
        candidates.extend(sorted(LOGS_DIR.glob(pattern)))

    # Фільтруємо тільки файли що мають рядки у вікні
    result = []
    for fpath in candidates:
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    ts = parse_ts(line)
                    if ts:
                        if ts >= CUTOFF_UTC:
                            result.append(fpath)
                        break  # перший рядок з відомим ts
        except Exception:
            pass
    return result


def classify_gate_group(why_code: str) -> str:
    wc = why_code.upper()
    if "QOS" in wc:
        return "QoS"
    if any(k in wc for k in ["RISK_GATE", "SAFETY_GATE", "NRR", "RISK GATE", "RISK_GATE_ALERT", "EXPOSURE_FAIL"]):
        return "Risk/Safety"
    if any(k in wc for k in ["ANTI_FLAT", "PRICE_MOTION", "FLASH", "MOTION", "SIGMA"]):
        return "Price Motion"
    if any(k in wc for k in ["DIRECTIONAL", "ANTI_FOMO", "DENY_LONG", "DENY_SHORT", "FOMO"]):
        return "Directional"
    if "HOLDING" in wc:
        return "Holding Period"
    if any(k in wc for k in ["ARBITRATION", "INTENT_REJECTED", "GATE_BLOCKED"]):
        return "Intent/Arb Reject"
    if any(k in wc for k in ["PYRAMIDING", "SAME-SIDE", "FLIP_ORCHESTRATION"]):
        return "Pyramiding/Flip"
    if any(k in wc for k in ["SIZING", "MARGIN", "CONFIG_REGIME"]):
        return "Config/Sizing"
    return "Other"


def extract_reject_code(line: str) -> Optional[str]:
    """Витягує найбільш специфічний why-код для reject рядка."""

    # STRATEGY_SIGNAL_GATEWAY: BLOCK - Same-side pyramiding not allowed
    m = RE_BLOCK.search(line)
    if m:
        reason = m.group(1).strip()
        # Normalize
        if "pyramiding" in reason.lower() or "same-side" in reason.lower():
            return "BLOCK/Same-side-pyramiding"
        return f"BLOCK/{reason[:60]}"

    # STRATEGY_SIGNAL_GATEWAY: REJECT - Sizing blocked (CONFIG_REGIME_SIZING_INVALID)
    m = RE_REJECT.search(line)
    if m:
        reason = m.group(1).strip()
        # CONFIG_REGIME_SIZING_INVALID: invalid_margin_pct_mult:0.0
        mc = re.search(r"\(([^)]+)\)", reason)
        if mc:
            return f"REJECT/{mc.group(1)}"
        return f"REJECT/{reason[:60]}"

    # FLIP_ORCHESTRATION: BLOCK
    m = RE_FLIP_BLOCK.search(line)
    if m:
        return f"FLIP_BLOCK/{m.group(1).strip()[:40]}"

    # SAFETY_GATES: DENY LONG/SHORT reason=NRR-xxx
    m = RE_SAFETY_DENY.search(line)
    if m:
        return f"SAFETY_GATES/DENY_{m.group(1)}/reason={m.group(2)}"

    # SAFETY_GATES: flash down blocks long / flash up blocks short
    m = RE_SAFETY_FLASH.search(line)
    if m:
        return f"SAFETY_GATES/{m.group(1)}"

    # SAFETY_GATES: price_motion flash insufficient
    m = RE_SAFETY_MOTION.search(line)
    if m:
        return f"SAFETY_GATES/{m.group(1)}"

    # GATE_ANTI_FLAT_SIGMA: Blocking entry (motion=X < threshold=Y)
    m = RE_ANTI_FLAT.search(line)
    if m:
        return f"GATE_ANTI_FLAT_SIGMA(motion<{m.group(2)})"

    # SAFETY_GATE (generic)
    if RE_SAFETY_GATE.search(line):
        return "SAFETY_GATE"

    # Risk Gate Violation (alert)
    if RE_RISK_GATE.search(line):
        return "RISK_GATE_ALERT"

    # EXPOSURE_FAIL_CLOSED_OPEN_BLOCKED
    m = RE_EXPOSURE_FAIL.search(line)
    if m:
        return f"EXPOSURE_FAIL/{m.group(1)}"

    # QOS_BLOCK
    m = RE_QOS_BLOCK.search(line)
    if m:
        return f"QOS_BLOCK/{m.group(1)}"
    if "QOS_BLOCK" in line:
        return "QOS_BLOCK"

    # HOLDING_PERIOD
    m = RE_HOLDING.search(line)
    if m:
        return f"HOLDING_PERIOD/{m.group(1)}"
    if "HOLDING_PERIOD" in line:
        return "HOLDING_PERIOD"

    # INTENT_REJECTED
    m = RE_INTENT_REJ.search(line)
    if m:
        return f"INTENT_REJECTED/{m.group(1)}"
    if "INTENT_REJECTED" in line:
        return "INTENT_REJECTED"

    # ARBITRATION_REJECT
    m = RE_ARB_REJ.search(line)
    if m:
        return f"ARBITRATION_REJECT/{m.group(1)}"
    if "ARBITRATION_REJECT" in line:
        return "ARBITRATION_REJECT"

    # GATE_BLOCKED
    m = RE_GATE_BLOCKED.search(line)
    if m:
        return f"GATE_BLOCKED/{m.group(1)}"
    if "GATE_BLOCKED" in line:
        return "GATE_BLOCKED"

    # PRICE_MOTION
    m = RE_PRICE_MOTION.search(line)
    if m:
        return f"PRICE_MOTION/{m.group(1)}"
    if "PRICE_MOTION" in line:
        return "PRICE_MOTION"

    # DIRECTIONAL_SANITY
    m = RE_DIR_SANITY.search(line)
    if m:
        return f"DIRECTIONAL_SANITY/{m.group(1)}"
    if "DIRECTIONAL_SANITY" in line:
        return "DIRECTIONAL_SANITY"

    # ANTI_FOMO
    m = RE_ANTI_FOMO.search(line)
    if m:
        return f"ANTI_FOMO/{m.group(1)}"
    if "ANTI_FOMO" in line:
        return "ANTI_FOMO"

    # NRR standalone
    m = RE_NRR.search(line)
    if m:
        return m.group(1)

    return None


def is_reject_line(line: str) -> bool:
    return bool(
        RE_BLOCK.search(line) or RE_REJECT.search(line) or RE_FLIP_BLOCK.search(line) or
        RE_SAFETY_DENY.search(line) or RE_SAFETY_FLASH.search(line) or
        RE_SAFETY_MOTION.search(line) or RE_ANTI_FLAT.search(line) or
        RE_SAFETY_GATE.search(line) or RE_RISK_GATE.search(line) or
        RE_EXPOSURE_FAIL.search(line) or RE_QOS_BLOCK.search(line) or
        "QOS_BLOCK" in line or RE_HOLDING.search(line) or "HOLDING_PERIOD" in line or
        RE_INTENT_REJ.search(line) or "INTENT_REJECTED" in line or
        RE_ARB_REJ.search(line) or "ARBITRATION_REJECT" in line or
        RE_GATE_BLOCKED.search(line) or "GATE_BLOCKED" in line or
        RE_PRICE_MOTION.search(line) or "PRICE_MOTION" in line or
        RE_DIR_SANITY.search(line) or "DIRECTIONAL_SANITY" in line or
        RE_ANTI_FOMO.search(line) or "ANTI_FOMO" in line
    )


def is_cancelled_limit(line: str) -> bool:
    return bool(
        RE_ORPHAN_CANCEL.search(line) or
        RE_LIMIT_CANCEL.search(line) or
        RE_EXPIRE.search(line) or
        RE_UNFILLED.search(line) or
        RE_CANCEL_LIMIT.search(line) or
        RE_EXEC_CANCEL.search(line)
    )


# ─────────────────────────── MAIN ──────────────────────────────
def main():
    reject_codes: Counter = Counter()
    gate_groups: Counter = Counter()
    total_intents_direct = 0      # with "Processing BUY/SELL signal"
    total_passed_direct = 0      # "All gates passed"
    total_rejects_direct = 0      # individual BLOCK/REJECT events
    cancelled_limits = 0
    lines_in_window = 0
    files_processed = []

    # Cumulative counter from risk alert (most authoritative)
    last_risk_alert_blocked = 0
    last_risk_alert_total = 0
    last_risk_alert_pct = 0.0

    print("  Скануємо лог файли...")
    all_files = get_all_log_files()
    print(f"  Знайдено {len(all_files)} файлів у вікні 72h\n")

    for fpath in all_files:
        files_processed.append(fpath.name)
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.rstrip()
                    if not line:
                        continue

                    ts = parse_ts(line)
                    if ts and ts < CUTOFF_UTC:
                        continue

                    lines_in_window += 1

                    # ── Intent processing counter ──────────────────────
                    if RE_PROCESSING.search(line):
                        total_intents_direct += 1

                    if RE_GATE_PASSED.search(line):
                        total_passed_direct += 1

                    # ── Risk alert cumulative counter ──────────────────
                    m = RE_RISK_ALERT.search(line)
                    if m:
                        blocked = int(m.group(2))
                        total = int(m.group(3))
                        pct = float(m.group(1))
                        if total > last_risk_alert_total:
                            last_risk_alert_blocked = blocked
                            last_risk_alert_total = total
                            last_risk_alert_pct = pct

                    # ── Reject events ──────────────────────────────────
                    if is_reject_line(line):
                        total_rejects_direct += 1
                        code = extract_reject_code(line)
                        if code:
                            reject_codes[code] += 1
                            gate_groups[classify_gate_group(code)] += 1
                        else:
                            reject_codes["UNKNOWN_REJECT"] += 1
                            gate_groups["Other"] += 1

                    # ── Cancelled limit orders ─────────────────────────
                    if is_cancelled_limit(line):
                        cancelled_limits += 1

        except Exception as e:
            print(f"  [WARN] Cannot read {fpath.name}: {e}")

    # ─── Вибираємо авторитетне джерело лічильників ────────────
    # "Risk gate alert: X% intents blocked (M/N)" — найточніший кумулятивний лічильник
    # але він може бути з іншого runу. Якщо є — використовуємо.
    use_alert_counters = last_risk_alert_total > 0

    if use_alert_counters:
        total_intents = last_risk_alert_total
        total_rejected = last_risk_alert_blocked
    else:
        total_intents = total_intents_direct
        total_rejected = total_rejects_direct

    # ─────────────── REPORT ───────────────────────────────────
    sep = "=" * 72
    print(sep)
    print("  REJECT / GATE FORENSICS — останні 72 годин")
    print(
        f"  Вікно: {CUTOFF_UTC.strftime('%Y-%m-%d %H:%M')} UTC  →  {NOW_UTC.strftime('%Y-%m-%d %H:%M')} UTC")
    print(sep)
    print(f"\n  Файлів оброблено   : {len(files_processed)}")
    print(f"  Рядків у вікні     : {lines_in_window:,}")
    if use_alert_counters:
        print(f"  Джерело лічильника : Risk gate alert (кумулятивний — найточніший)")
    else:
        print(f"  Джерело лічильника : поенко по рядках (cumulative alert не знайдено)")

    # ── 2. Intents vs Rejected ─────────────────────────────────
    print(f"\n{'─'*72}")
    print("  2. INTENTS vs REJECTED")
    print(f"{'─'*72}")
    rej_pct = (total_rejected / total_intents * 100) if total_intents else 0
    pass_cnt = max(total_intents - total_rejected, 0)
    pass_pct = (pass_cnt / total_intents * 100) if total_intents else 0

    print(f"  Всього intents згенеровано : {total_intents:>8,}")
    print(
        f"  ├─ Відхилено гейтами       : {total_rejected:>8,}  ({rej_pct:.1f}%)")
    print(f"  └─ Пройшло всі гейти       : {pass_cnt:>8,}  ({pass_pct:.1f}%)")
    if use_alert_counters:
        print(
            f"\n  [Alert snapshot]  {last_risk_alert_pct}% blocked  ({last_risk_alert_blocked}/{last_risk_alert_total})")
    print(f"\n  [Per-event scan]  intents={total_intents_direct:,}  passed={total_passed_direct:,}  "
          f"rejected_events={total_rejects_direct:,}")

    # ── 1. Топ-10 причин reject ────────────────────────────────
    print(f"\n{'─'*72}")
    print("  1. ТОП-10 ПРИЧИН REJECT (why-код)")
    print(f"{'─'*72}")
    top10 = reject_codes.most_common(10)
    all_reject_ev = sum(reject_codes.values())

    if top10:
        print(
            f"  {'#':<3}  {'WHY-КОД':<52}  {'N':>6}  {'% intents':>10}  {'% rejects':>10}")
        print(f"  {'─'*3}  {'─'*52}  {'─'*6}  {'─'*10}  {'─'*10}")
        for i, (code, cnt) in enumerate(top10, 1):
            pct_i = (cnt / total_intents * 100) if total_intents else 0
            pct_r = (cnt / all_reject_ev * 100) if all_reject_ev else 0
            trunc = code[:52]
            print(
                f"  {i:<3}  {trunc:<52}  {cnt:>6,}  {pct_i:>9.1f}%  {pct_r:>9.1f}%")
    else:
        print("  [!] Жодного reject-коду не знайдено у вікні 72h")

    # ── 3. % rejected по групах гейтів ────────────────────────
    print(f"\n{'─'*72}")
    print("  3. ГРУПИ ГЕЙТІВ — розподіл rejected events")
    print(f"{'─'*72}")
    total_gate_ev = sum(gate_groups.values())
    if gate_groups:
        ordered = sorted(gate_groups.items(), key=lambda x: x[1], reverse=True)
        print(
            f"  {'ГРУПА':<25}  {'N':>7}  {'% reject events':>16}  {'% від intents':>14}")
        print(f"  {'─'*25}  {'─'*7}  {'─'*16}  {'─'*14}")
        for grp, cnt in ordered:
            pct_r = (cnt / total_gate_ev * 100) if total_gate_ev else 0
            pct_i = (cnt / total_intents * 100) if total_intents else 0
            print(f"  {grp:<25}  {cnt:>7,}  {pct_r:>15.1f}%  {pct_i:>13.1f}%")
    else:
        print("  [!] Немає даних по групах гейтів")

    # ── 4. Cancelled limit orders ──────────────────────────────
    print(f"\n{'─'*72}")
    print("  4. INTENTS ЩО ПРОЙШЛИ ГЕЙТИ, АЛЕ НЕ ЗАПОВНИЛИСЬ")
    print(f"{'─'*72}")
    pct_canc = (cancelled_limits / total_intents * 100) if total_intents else 0
    pct_canc2 = (cancelled_limits / pass_cnt * 100) if pass_cnt else 0
    print(f"  Intents що пройшли всі гейти       : {pass_cnt:>8,}")
    print(f"  Cancelled / orphan / expired orders : {cancelled_limits:>8,}  "
          f"({pct_canc:.1f}% від intents  |  {pct_canc2:.1f}% від passed)")
    net_filled = max(pass_cnt - cancelled_limits, 0)
    net_pct = (net_filled / total_intents * 100) if total_intents else 0
    print(
        f"  Потенційно виконалось               : {net_filled:>8,}  ({net_pct:.1f}% від intents)")

    # ── Summary ───────────────────────────────────────────────
    print(f"\n{'─'*72}")
    print("  SUMMARY")
    print(f"{'─'*72}")
    if gate_groups:
        top_grp = max(gate_groups, key=gate_groups.get)
        top_grp_cnt = gate_groups[top_grp]
        top_grp_pct = (top_grp_cnt / total_gate_ev *
                       100) if total_gate_ev else 0

        top_code = reject_codes.most_common(
            1)[0] if reject_codes else ("N/A", 0)
    else:
        top_grp = "N/A"
        top_grp_cnt = 0
        top_grp_pct = 0
        top_code = ("N/A", 0)

    print(f"  · Всього intents       : {total_intents:,}")
    print(f"  · Відхилено гейтами    : {total_rejected:,}  ({rej_pct:.1f}%)")
    print(
        f"  · Unfilled after gates : {cancelled_limits:,}  ({pct_canc:.1f}%)")
    print(f"  · Виконано             : {net_filled:,}  ({net_pct:.1f}%)")
    print(
        f"\n  Домінантна група гейтів : [{top_grp}] — {top_grp_cnt:,} event(s) ({top_grp_pct:.1f}% reject events)")
    print(f"  №1 why-код              : [{top_code[0]}] — {top_code[1]:,}")

    print(f"\n{sep}\n")


if __name__ == "__main__":
    main()
