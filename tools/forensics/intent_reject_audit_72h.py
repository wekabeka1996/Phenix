#!/usr/bin/env python3
"""
FORENSIC-INTENT-REJECT-72H
===========================
Аналіз всіх INTENT_REJECTED / gate-block подій за останні 72 години.

Виводить:
  1. Топ-10 причин reject (why-код + count + % від усіх intents)
  2. Загальна кількість intents proposed vs rejected
  3. % rejected через кожну групу гейтів
  4. Intents, що пройшли гейти, але cancelled (limit orders у WAL)

Джерела:
  - ops/wal/*.jsonl  (WAL, 72h window)
  - logs/domain_decision_making.log (текстовий fallback)
"""

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[2]
WAL_DIR = REPO_ROOT / "ops" / "wal"
DM_LOG = REPO_ROOT / "logs" / "domain_decision_making.log"
REPORT_MD = REPO_ROOT / "reports" / "intent_reject_audit_72h.md"

# ── Time window ──────────────────────────────────────────────────────────────
NOW_UTC = datetime(2026, 2, 18, 23, 59, 59, tzinfo=timezone.utc)
CUTOFF_TS = int((NOW_UTC - timedelta(hours=72)).timestamp() * 1000)  # ms

print(
    f"[INFO] Cutoff: {datetime.utcfromtimestamp(CUTOFF_TS/1000)} UTC  (72h window)")
print(f"[INFO] Now:    {NOW_UTC.strftime('%Y-%m-%d %H:%M:%S')} UTC")

# ── Gate-group classification ─────────────────────────────────────────────────
GATE_GROUPS = {
    # bar-only filter — NOT a real gate
    "Noise (tick-filter)":  re.compile(r"NRR-046", re.I),
    "QoS":                  re.compile(r"QOS|QoS|qos|ANTI_FOMO|ANTI_FLAT|HOLDING_PERIOD", re.I),
    "Regime":               re.compile(r"REGIME|ARBITRATION|arbitration", re.I),
    "Price Motion":         re.compile(r"PRICE_MOTION|PM_|FLASH|BLEED|NRR-028|NRR-029|NRR-030", re.I),
    "Directional Sanity":   re.compile(r"DIRECTIONAL|DIR_|NRR-02[67]", re.I),
    "Risk/Safety Gate":     re.compile(r"RISK_GATE|SAFETY_GATE", re.I),
    "Data/Infra":           re.compile(r"ATR_MISSING|DATA_NOT_READY|MISSING|EP-01", re.I),
    "Intent/Strategy":      re.compile(r"GATE_BLOCKED|STRATEGY|SCORE|CONF|alpha", re.I),
}

# ── Text-log patterns (domain_decision_making.log) ────────────────────────────
LOG_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"INTENT_REJECTED", r"ARBITRATION_REJECT", r"GATE_BLOCKED",
        r"QOS_BLOCK", r"RISK_GATE", r"SAFETY_GATE",
        r"PRICE_MOTION", r"DIRECTIONAL_SANITY", r"ANTI_FLAT",
        r"ANTI_FOMO", r"HOLDING_PERIOD",
    ]
]

# ─────────────────────────────────────────────────────────────────────────────
# PASS 1: WAL JSONL scan
# ─────────────────────────────────────────────────────────────────────────────
wal_proposed = 0
wal_rejected = 0
wal_opened = 0        # CMD:OPEN / ORDER_PLACED
wal_cancelled = 0        # ORDER_REJECTED after OPEN (limit cancel)

reject_why_codes: dict[str, int] = defaultdict(int)  # reason_code → count
reject_why_full:  dict[str, int] = defaultdict(int)  # full why-string → count
gate_group_counts: dict[str, int] = defaultdict(int)
opened_rids: set[str] = set()
cancel_details: list[dict] = []
log_gate_hits: dict[str, int] = defaultdict(int)     # from text logs

# Walk WAL files
wal_files = sorted(WAL_DIR.glob("*.jsonl"))
print(f"[INFO] WAL files found: {[f.name for f in wal_files]}")

for wal_file in wal_files:
    with wal_file.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue

            ts = rec.get("ts") or (rec.get("pld") or {}).get("ts_ms") or 0
            if ts and ts < CUTOFF_TS:
                continue

            verb = rec.get("verb", "")

            # ── Proposed intents ────────────────────────────────────────────
            if verb == "TRADE_INTENT_PROPOSED":
                wal_proposed += 1

            # ── Rejected intents ────────────────────────────────────────────
            elif verb == "TRADE_INTENT_REJECTED":
                wal_rejected += 1
                pld = rec.get("pld") or {}
                rc = pld.get("reason_code") or pld.get("stage") or "UNKNOWN"
                why = pld.get("why") or rec.get("why") or rc

                reject_why_codes[rc] += 1
                reject_why_full[why] += 1

                # Gate group
                classified = False
                for grp, pat in GATE_GROUPS.items():
                    if pat.search(rc) or pat.search(why):
                        gate_group_counts[grp] += 1
                        classified = True
                        break
                if not classified:
                    gate_group_counts["Other"] += 1

            # ── Opened / placed ─────────────────────────────────────────────
            elif verb in ("OPEN", "ORDER_PLACED", "PLACE_ORDER"):
                wal_opened += 1
                rid = rec.get("rid") or rec.get("parent_client_order_id") or ""
                if rid:
                    opened_rids.add(rid)

            # ── Cancelled / rejected orders ─────────────────────────────────
            elif verb == "ORDER_REJECTED":
                wal_cancelled += 1
                pld = rec.get("pld") or {}
                cancel_details.append({
                    "ts": ts,
                    "symbol": pld.get("symbol") or rec.get("symbol") or "?",
                    "reason": pld.get("reason") or rec.get("why") or "?",
                    "rid": rec.get("rid", ""),
                })


# ─────────────────────────────────────────────────────────────────────────────
# PASS 2: domain_decision_making.log — keyword scan (text fallback)
# ─────────────────────────────────────────────────────────────────────────────
dm_hits: dict[str, int] = defaultdict(int)

# Parse timestamp from log line "2026-02-18 20:46:02,392 - ..."
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

if DM_LOG.exists():
    # Read last 72h from domain_decision_making.log (may be large)
    # We scan from the end using a rolling window heuristic
    lines_to_check = []
    for log_path in [DM_LOG, DM_LOG.parent / "domain_decision_making.log.1"]:
        if log_path.exists():
            lines_to_check.extend(log_path.read_text(
                encoding="utf-8", errors="replace").splitlines())

    for line in lines_to_check:
        m = TS_RE.match(line)
        if m:
            try:
                lts = datetime.strptime(
                    m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if lts < (NOW_UTC - timedelta(hours=72)):
                    continue
            except ValueError:
                pass
        for pat in LOG_PATTERNS:
            kw = pat.pattern.strip(r"\\").upper()
            if pat.search(line):
                dm_hits[kw] += 1


# ─────────────────────────────────────────────────────────────────────────────
# PASS 3: domain_risk_management.log – RISK_GATE / SAFETY_GATE
# ─────────────────────────────────────────────────────────────────────────────
RISK_RE = re.compile(
    r"(RISK_GATE|SAFETY_GATE|QOS_BLOCK|ARBITRATION_REJECT|GATE_BLOCKED|HOLDING_PERIOD|ANTI_FLAT|ANTI_FOMO|PRICE_MOTION|DIRECTIONAL_SANITY)", re.I)
risk_log = REPO_ROOT / "logs" / "domain_risk_management.log"
risk_hits: dict[str, int] = defaultdict(int)

if risk_log.exists():
    for line in risk_log.read_text(encoding="utf-8", errors="replace").splitlines():
        m = TS_RE.match(line)
        if m:
            try:
                lts = datetime.strptime(
                    m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                if lts < (NOW_UTC - timedelta(hours=72)):
                    continue
            except ValueError:
                pass
        for hit in RISK_RE.findall(line):
            risk_hits[hit.upper()] += 1


# ─────────────────────────────────────────────────────────────────────────────
# Compute statistics
# ─────────────────────────────────────────────────────────────────────────────
# proposed = those that weren't blocked before reaching WAL
total_intents = wal_proposed + wal_rejected
total_intents_all = max(total_intents, 1)

# Top-10 why-codes
top10_codes = sorted(reject_why_codes.items(), key=lambda x: -x[1])[:10]

# Top-10 full why-strings
top10_full = sorted(reject_why_full.items(),  key=lambda x: -x[1])[:10]

# Gate groups
total_gated = sum(gate_group_counts.values()) or 1

# Limit cancel rate: orders opened but then ORDER_REJECTED
limit_cancel_rate = (wal_cancelled / wal_opened * 100) if wal_opened else 0.0

# ─────────────────────────────────────────────────────────────────────────────
# Console output
# ─────────────────────────────────────────────────────────────────────────────
SEP = "─" * 72

print(f"\n{SEP}")
print("  FORENSIC INTENT REJECT AUDIT — 72h Window")
print(f"  {(NOW_UTC - timedelta(hours=72)).strftime('%Y-%m-%d %H:%M')} UTC  →  {NOW_UTC.strftime('%Y-%m-%d %H:%M')} UTC")
print(SEP)

print(f"\n{'━'*72}")
print("  §1. TOP-10 ПРИЧИН REJECT (reason_code з WAL)")
print(f"{'━'*72}")
print(f"  {'Rank':<5} {'reason_code':<40} {'Count':>7} {'%':>8}")
print(f"  {'----':<5} {'-'*40:<40} {'------':>7} {'-------':>8}")
for i, (rc, cnt) in enumerate(top10_codes, 1):
    pct = cnt / total_intents_all * 100
    print(f"  {i:<5} {rc:<40} {cnt:>7,} {pct:>7.1f}%")

print(f"\n  Full why-string TOP-10:")
print(f"  {'Rank':<5} {'why':<55} {'Count':>7}")
print(f"  {'----':<5} {'-'*55:<55} {'------':>7}")
for i, (why, cnt) in enumerate(top10_full, 1):
    print(f"  {i:<5} {why[:55]:<55} {cnt:>7,}")

noise_count = reject_why_codes.get("NRR-046", 0)
real_rejected = wal_rejected - noise_count
real_total = wal_proposed + real_rejected
real_total_safe = max(real_total, 1)

print(f"\n{'━'*72}")
print("  §2. ЗАГАЛЬНА КІЛЬКІСТЬ INTENTS")
print(f"{'━'*72}")
print(f"  TRADE_INTENT_PROPOSED  : {wal_proposed:>8,}")
print(f"  TRADE_INTENT_REJECTED  : {wal_rejected:>8,}")
print(
    f"    ↳ NRR-046 (tick-noise): {noise_count:>7,}  ← bar-only filter, не реальний reject")
print(f"    ↳ Real gate rejects  : {real_rejected:>7,}")
print(
    f"  Rejected rate (all)    : {wal_rejected/total_intents_all*100:>7.1f}%")
print(f"  Rejected rate (real)   : {real_rejected/real_total_safe*100:>7.1f}%")
print(f"  Orders PLACED          : {wal_opened:>8,}")
print(f"  Orders REJECTED/cancel : {wal_cancelled:>8,}")

print(f"\n{'━'*72}")
print("  §3. % REJECTED ПО ГРУПАХ ГЕЙТІВ (без NRR-046 noise)")
print(f"{'━'*72}")
print(f"  {'Gate Group':<30} {'Count':>8} {'% of real rej':>15}")
print(f"  {'-'*30:<30} {'------':>8} {'-------------':>15}")
real_gated = sum(v for g, v in gate_group_counts.items()
                 if g != "Noise (tick-filter)") or 1
for grp, cnt in sorted(gate_group_counts.items(), key=lambda x: -x[1]):
    if grp == "Noise (tick-filter)":
        print(f"  {grp:<30} {cnt:>8,}  ← excluded from %")
        continue
    pct_rej = cnt / real_gated * 100
    print(f"  {grp:<30} {cnt:>8,} {pct_rej:>14.1f}%")

print(f"\n{'━'*72}")
print("  §4. INTENTS ЩО ПРОЙШЛИ ГЕЙТИ → LIMIT CANCELLED (ORDER_REJECTED)")
print(f"{'━'*72}")
print(f"  Orders placed          : {wal_opened:>8,}")
print(f"  Orders cancelled/rej   : {wal_cancelled:>8,}")
print(f"  Cancel rate            : {limit_cancel_rate:>7.1f}%")

if cancel_details:
    from collections import Counter
    top_cancel_reasons = Counter(d["reason"]
                                 for d in cancel_details).most_common(5)
    print(f"\n  Top-5 cancel reasons:")
    for reason, cnt in top_cancel_reasons:
        print(f"    [{cnt:>4}]  {reason[:70]}")

print(f"\n{'━'*72}")
print("  §5. TEXT-LOG GATE HITS (domain_decision_making.log)")
print(f"{'━'*72}")
for kw, cnt in sorted(dm_hits.items(), key=lambda x: -x[1]):
    print(f"  {kw:<35} {cnt:>8,}")

if risk_hits:
    print(f"\n  Risk log hits (domain_risk_management.log):")
    for kw, cnt in sorted(risk_hits.items(), key=lambda x: -x[1]):
        print(f"  {kw:<35} {cnt:>8,}")

print(f"\n{SEP}\n")

# ─────────────────────────────────────────────────────────────────────────────
# Write Markdown report
# ─────────────────────────────────────────────────────────────────────────────
REPORT_MD.parent.mkdir(parents=True, exist_ok=True)

md_lines = [
    f"# Intent Reject Audit — 72h Window",
    f"",
    f"> **Period:** {(NOW_UTC - timedelta(hours=72)).strftime('%Y-%m-%d %H:%M')} UTC → {NOW_UTC.strftime('%Y-%m-%d %H:%M')} UTC  ",
    f"> **Generated:** {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC",
    f"",
    f"---",
    f"",
    f"## §1 — Топ-10 причин REJECT (reason_code из WAL)",
    f"",
    f"| Rank | reason_code | Count | % of intents |",
    f"|-----:|:------------|------:|-------------:|",
]
for i, (rc, cnt) in enumerate(top10_codes, 1):
    pct = cnt / total_intents_all * 100
    md_lines.append(f"| {i} | `{rc}` | {cnt:,} | {pct:.1f}% |")

md_lines += [
    f"",
    f"### Full why-string",
    f"",
    f"| Rank | why | Count |",
    f"|-----:|:----|------:|",
]
for i, (why, cnt) in enumerate(top10_full, 1):
    md_lines.append(f"| {i} | `{why[:80]}` | {cnt:,} |")

md_lines += [
    f"",
    f"---",
    f"",
    f"## §2 — Загальна кількість Intents",
    f"",
    f"| Метрика | Значення |",
    f"|:--------|--------:|",
    f"| TRADE_INTENT_PROPOSED | {wal_proposed:,} |",
    f"| TRADE_INTENT_REJECTED | {wal_rejected:,} |",
    f"| **Rejected rate** | **{wal_rejected/total_intents_all*100:.1f}%** |",
    f"| Orders PLACED | {wal_opened:,} |",
    f"| Orders CANCELLED/REJECTED | {wal_cancelled:,} |",
    f"",
    f"---",
    f"",
    f"## §3 — % Rejected по групах гейтів",
    f"",
    f"| Gate Group | Count | % of rejected |",
    f"|:-----------|------:|--------------:|",
]
for grp, cnt in sorted(gate_group_counts.items(), key=lambda x: -x[1]):
    pct_rej = cnt / total_gated * 100
    md_lines.append(f"| {grp} | {cnt:,} | {pct_rej:.1f}% |")

md_lines += [
    f"",
    f"---",
    f"",
    f"## §4 — Intents, що пройшли гейти → Limit Cancelled (`ORDER_REJECTED`)",
    f"",
    f"| Метрика | Значення |",
    f"|:--------|--------:|",
    f"| Orders placed | {wal_opened:,} |",
    f"| Cancelled/rejected | {wal_cancelled:,} |",
    f"| **Cancel rate** | **{limit_cancel_rate:.1f}%** |",
]

if cancel_details:
    from collections import Counter
    top_cancel_reasons = Counter(d["reason"]
                                 for d in cancel_details).most_common(5)
    md_lines += [f"", f"### Top-5 cancel reasons", f"",
                 f"| Reason | Count |", f"|:-------|------:|"]
    for reason, cnt in top_cancel_reasons:
        md_lines.append(f"| `{reason[:80]}` | {cnt:,} |")

md_lines += [
    f"",
    f"---",
    f"",
    f"## §5 — Text-log Gate Hits",
    f"",
    f"### domain_decision_making.log",
    f"",
    f"| Keyword | Hits |",
    f"|:--------|-----:|",
]
for kw, cnt in sorted(dm_hits.items(), key=lambda x: -x[1]):
    md_lines.append(f"| `{kw}` | {cnt:,} |")

if risk_hits:
    md_lines += [f"", f"### domain_risk_management.log",
                 f"", f"| Keyword | Hits |", f"|:--------|-----:|"]
    for kw, cnt in sorted(risk_hits.items(), key=lambda x: -x[1]):
        md_lines.append(f"| `{kw}` | {cnt:,} |")

md_lines.append(
    f"\n---\n*Source: ops/wal/, logs/domain_decision_making.log, logs/domain_risk_management.log*")

REPORT_MD.write_text("\n".join(md_lines), encoding="utf-8")
print(f"[OK] Report written → {REPORT_MD.relative_to(REPO_ROOT)}")
