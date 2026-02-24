#!/usr/bin/env python3
"""
REJECT-AUDIT-72H v2: Forensic analysis of ORDER_REJECTED events (last N hours).

Data source SSOT: logs/order_log_v1.jsonl  +  text logs (supplemental).

Outputs:
  1. Top-10 reject reasons (nrr_code + why + count + % of all intents)
  2. Total intents generated vs total rejected
  3. % rejected per gate group (QoS, Safety, Price Motion, Directional Sanity, etc.)
  4. Intents that passed all gates (ORDER_PLACED) but were NOT filled
     (ORDER_TIMEOUT + ORDER_CANCELLED)

Usage:
    python -m tools.forensics.reject_audit_72h
    python -m tools.forensics.reject_audit_72h --hours 48 --out reports/reject_audit.md
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

LOGS_DIR = Path("logs")

# Лог-файли, які треба сканувати (порядок важливий для хрон. злиття)
DM_LOGS = [
    "domain_decision_making.log.100",
    "domain_decision_making.log.1",
    "domain_decision_making.log",
]
RISK_LOGS = [
    "domain_risk_management.log.6",
    "domain_risk_management.log.5",
    "domain_risk_management.log.4",
    "domain_risk_management.log.3",
    "domain_risk_management.log.2",
    "domain_risk_management.log.1",
    "domain_risk_management.log",
]
EVENT_LOGS = [
    "event_chain.log.2",
    "event_chain.log.1",
    "event_chain.log",
]
ORDER_GUARDIAN_LOGS = ["order_guardian.log"]
ORDER_LOG_JSONL = "order_log_v1.jsonl"

# Ключові слова для фільтрації рядків
KEYWORDS = re.compile(
    r"INTENT_REJECTED|ARBITRATION_REJECT|GATE_BLOCKED|QOS_BLOCK|"
    r"RISK_GATE|SAFETY_GATE(?:S)?|PRICE_MOTION|DIRECTIONAL_SANITY|"
    r"ANTI_FLAT|ANTI_FOMO|HOLDING_PERIOD|ORDER_INTENT|INTENT_CANCEL|"
    r"ORDER_CANCEL|LIMIT_CANCEL|NRR-\d+"
)

# Патерни timestamp
TS_PATTERN = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})")

# Групи гейтів → regex-мітки (порядок важливий: більш специфічні — першими)
GATE_GROUPS: dict[str, re.Pattern] = {
    # --- Price Motion: NRR-028/029/030 (explicit кодам пріоритет) ---
    "Price Motion":          re.compile(r"PRICE_MOTION|\bNRR-028\b|\bNRR-029\b|\bNRR-030\b"),
    # --- Directional Sanity: NRR-026/027 ---
    "Directional Sanity":    re.compile(r"DIRECTIONAL_SANITY|\bNRR-026\b|\bNRR-027\b"),
    # --- Anti patterns ---
    "Anti-Flat / Anti-FOMO": re.compile(r"ANTI_FLAT|ANTI_FOMO|\bNRR-031\b|\bNRR-032\b|\bNRR-033\b"),
    # --- Holding Period ---
    "Holding Period":        re.compile(r"HOLDING_PERIOD|\bNRR-034\b|\bNRR-035\b"),
    # --- Risk Gate ---
    "Risk Gate":             re.compile(r"RISK_GATE|\bNRR-04\d\b|\bNRR-05\d\b"),
    # --- Safety Gates (загальні) ---
    "Safety Gates":          re.compile(r"SAFETY_GATE|GATE_BLOCKED"),
    # --- QoS / Arbitration (широкий fallback для ранніх NRR) ---
    "QoS / Arbitration":     re.compile(r"QOS_BLOCK|ARBITRATION_REJECT|\bNRR-00[1-9]\b|\bNRR-0[12][0-9]\b"),
    # --- Intent Rejected (generic) ---
    "Intent Rejected":       re.compile(r"INTENT_REJECTED"),
}

# NRR-code → human-readable group label (fallback)
NRR_GROUP: dict[str, str] = {
    "NRR-026": "Directional Sanity",
    "NRR-027": "Directional Sanity",
    "NRR-028": "Price Motion",
    "NRR-029": "Price Motion",
    "NRR-030": "Price Motion",
}

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------


def parse_ts(line: str) -> Optional[datetime]:
    m = TS_PATTERN.match(line)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def extract_why(line: str) -> str:
    """Extract why-code / NRR code from a log line."""
    # reason=NRR-029
    m = re.search(r"reason=(NRR-\d+)", line)
    if m:
        return m.group(1)
    # why=NRR-029 or why=some_text
    m = re.search(r"why=([^\s,}\]]+)", line)
    if m:
        return m.group(1)
    # Bare NRR code
    m = re.search(r"NRR-\d+", line)
    if m:
        return m.group(0)
    # Inline keyword after DENY / BLOCK
    for kw in ("PRICE_MOTION", "DIRECTIONAL_SANITY", "ANTI_FLAT", "ANTI_FOMO",
               "HOLDING_PERIOD", "QOS_BLOCK", "RISK_GATE", "SAFETY_GATE",
               "GATE_BLOCKED", "ARBITRATION_REJECT", "INTENT_REJECTED"):
        if kw in line:
            return kw
    return "UNKNOWN"


def collect_lines(log_files: list[str], cutoff: datetime) -> list[str]:
    """
    Read log files and return only lines with ts >= cutoff that match KEYWORDS.
    Skips lines with no parseable timestamp (assumed in-range if file mtime > cutoff).
    """
    result: list[str] = []
    for fname in log_files:
        fpath = LOGS_DIR / fname
        if not fpath.exists():
            continue
        # Quick mtime check: if file last-modified < cutoff, skip entirely
        mtime = datetime.fromtimestamp(fpath.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            continue
        try:
            with fpath.open("r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if not KEYWORDS.search(line):
                        continue
                    ts = parse_ts(line)
                    if ts is None or ts >= cutoff:
                        result.append(line.rstrip())
        except Exception as e:
            print(f"  [WARN] cannot read {fname}: {e}")
    return result


def parse_ts_ms(ts_ms: int | None) -> Optional[datetime]:
    if not ts_ms:
        return None
    return datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)


# NRR code → gate group (explicit mapping, highest priority)
NRR_TO_GROUP: dict[str, str] = {
    "NRR-026": "Directional Sanity",
    "NRR-027": "Directional Sanity",
    "NRR-028": "Price Motion",
    "NRR-029": "Price Motion",
    "NRR-030": "Price Motion",
    "NRR-031": "Anti-Flat / Anti-FOMO",
    "NRR-032": "Anti-Flat / Anti-FOMO",
    "NRR-033": "Anti-Flat / Anti-FOMO",
    "NRR-034": "Holding Period",
    "NRR-035": "Holding Period",
    "NRR-015": "Exchange Rejection",
    "NRR-016": "Exchange Rejection",
    "NRR-018": "Exchange (MAKER_ONLY)",
    "NRR-019": "Exchange Rejection",
    "NRR-040": "Risk Gate",
    "NRR-041": "Risk Gate",
    "NRR-042": "Risk Gate",
    "NRR-043": "Risk Gate",
    "NRR-001": "QoS / Arbitration",
    "NRR-002": "QoS / Arbitration",
    "NRR-003": "QoS / Arbitration",
    "NRR-004": "QoS / Arbitration",
    "NRR-005": "QoS / Arbitration",
}

WHY_TO_GROUP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"SAFETY_GATES|SAFETY_GATE"),  "Safety Gates"),
    (re.compile(r"PRICE_MOTION"),               "Price Motion"),
    (re.compile(r"DIRECTIONAL_SANITY"),         "Directional Sanity"),
    (re.compile(r"ANTI_FLAT|ANTI_FOMO"),        "Anti-Flat / Anti-FOMO"),
    (re.compile(r"HOLDING_PERIOD"),             "Holding Period"),
    (re.compile(r"RISK_GATE"),                  "Risk Gate"),
    (re.compile(r"QOS_BLOCK|ARBITRATION"),      "QoS / Arbitration"),
    (re.compile(r"MAKER_ONLY"),                 "Exchange (MAKER_ONLY)"),
    (re.compile(r"Margin is insufficient"),     "Exchange Rejection"),
    (re.compile(r"GATE_BLOCKED"),               "Gate Blocked"),
]


def classify_group(nrr_code: str, why: str) -> str:
    if nrr_code and nrr_code in NRR_TO_GROUP:
        return NRR_TO_GROUP[nrr_code]
    m = re.match(r"NRR-(\d+)", nrr_code or "")
    if m:
        n = int(m.group(1))
        if 26 <= n <= 27:
            return "Directional Sanity"
        if 28 <= n <= 30:
            return "Price Motion"
        if 31 <= n <= 33:
            return "Anti-Flat / Anti-FOMO"
        if 34 <= n <= 35:
            return "Holding Period"
        if 40 <= n <= 59:
            return "Risk Gate"
        if 1 <= n <= 9:
            return "QoS / Arbitration"
        if 10 <= n <= 25:
            return "Exchange / Execution"
    for pat, grp in WHY_TO_GROUP:
        if pat.search(why or ""):
            return grp
    return "Other / Unknown"


# ---------------------------------------------------------------------------
# ANALYSIS FUNCTIONS
# ---------------------------------------------------------------------------

def analyze_text_logs(cutoff: datetime) -> tuple[Counter, int]:
    """Supplemental: count reject-keyword lines from text logs."""
    all_files = DM_LOGS + RISK_LOGS + EVENT_LOGS + ORDER_GUARDIAN_LOGS
    lines_matched = collect_lines(all_files, cutoff)
    group_counter: Counter = Counter()
    for line in lines_matched:
        nrr_m = re.search(r"NRR-(\d+)", line)
        nrr_code = f"NRR-{nrr_m.group(1)}" if nrr_m else ""
        grp = classify_group(nrr_code, line)
        group_counter[grp] += 1
    return group_counter, len(lines_matched)


def analyze_jsonl(cutoff: datetime) -> dict:
    """
    Analyse order_log_v1.jsonl for all reject/place/fill/cancel events in window.
    Uses correct event types: ORDER_REJECTED, ORDER_PLACED, ORDER_TIMEOUT,
    ORDER_CANCELLED, ORDER_FILL_DISCOVERED.
    """
    fpath = LOGS_DIR / ORDER_LOG_JSONL
    if not fpath.exists():
        return {}

    intents: list[dict] = []
    rejected: list[dict] = []
    placed: list[dict] = []
    timeouts: list[dict] = []
    cancelled: list[dict] = []
    fills: list[dict] = []

    placed_rids: set[str] = set()

    with fpath.open("r", encoding="utf-8", errors="replace") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue
            ts = parse_ts_ms(obj.get("timestamp"))
            if ts is None or ts < cutoff:
                continue
            ev = obj.get("event_type", "")
            if ev == "ORDER_INTENT":
                intents.append(obj)
            elif ev == "ORDER_REJECTED":
                rejected.append(obj)
            elif ev == "ORDER_PLACED":
                placed.append(obj)
                placed_rids.add(obj.get("rid", ""))
            elif ev == "ORDER_TIMEOUT":
                timeouts.append(obj)
            elif ev == "ORDER_CANCELLED":
                cancelled.append(obj)
            elif ev == "ORDER_FILL_DISCOVERED":
                fills.append(obj)

    # why/nrr breakdown
    why_counter: Counter = Counter()
    group_counter: Counter = Counter()
    for r in rejected:
        nrr = r.get("nrr_code", "") or ""
        why = r.get("why", "") or ""
        meta = r.get("metadata", {}) or {}
        if not nrr:
            nrr = meta.get("deny_reason", "") or ""
        label = f"{nrr} | {why}" if nrr and why else (nrr or why or "UNKNOWN")
        why_counter[label] += 1
        group_counter[classify_group(nrr, why)] += 1

    timeout_rids = {r.get("rid", "") for r in timeouts}
    cancelled_rids = {r.get("rid", "") for r in cancelled}
    fill_rids = {r.get("rid", "") for r in fills}

    placed_then_timeout = [r for r in placed if r.get(
        "rid", "") in timeout_rids and r.get("rid", "") not in cancelled_rids]
    placed_then_cancel = [r for r in placed if r.get(
        "rid", "") in cancelled_rids and r.get("rid", "") not in timeout_rids]
    placed_then_both = [r for r in placed if r.get(
        "rid", "") in timeout_rids and r.get("rid", "") in cancelled_rids]
    placed_then_fill = [r for r in placed if r.get("rid", "") in fill_rids]

    return {
        "total_intents":       len(intents),
        "total_rejected":      len(rejected),
        "total_placed":        len(placed),
        "total_timeouts":      len(timeouts),
        "total_cancelled":     len(cancelled),
        "total_fills":         len(fills),
        "why_counter":         why_counter,
        "group_counter":       group_counter,
        "placed_then_timeout": placed_then_timeout,
        "placed_then_cancel":  placed_then_cancel,
        "placed_then_fill":    placed_then_fill,
        "placed_then_both":    placed_then_both,
        "standalone_timeouts": timeouts,
        "standalone_cancelled": cancelled,
    }


# ---------------------------------------------------------------------------
# REPORT RENDERER
# ---------------------------------------------------------------------------

def render_report(
    cutoff: datetime,
    data: dict,
    txt_groups: Counter,
    txt_lines: int,
    hours: int,
) -> str:
    now = datetime.now(tz=timezone.utc)

    total_intents = data["total_intents"]
    total_rejected = data["total_rejected"]
    total_placed = data["total_placed"]
    total_fills = data["total_fills"]
    total_timeouts = data["total_timeouts"]
    total_cancelled = data["total_cancelled"]
    why_counter = data["why_counter"]
    group_counter = data["group_counter"]
    placed_then_timeout = data["placed_then_timeout"]
    placed_then_cancel = data["placed_then_cancel"]
    placed_then_fill = data["placed_then_fill"]
    placed_then_both = data.get("placed_then_both", [])

    pct_rej = (total_rejected / total_intents * 100) if total_intents else 0
    pct_place = (total_placed / total_intents * 100) if total_intents else 0
    total_group = sum(group_counter.values())

    ls: list[str] = []
    ls.append(f"# REJECT AUDIT — LAST {hours}h")
    ls.append(
        f"**Period:** `{cutoff.strftime('%Y-%m-%d %H:%M UTC')}` → `{now.strftime('%Y-%m-%d %H:%M UTC')}`")
    ls.append(
        f"**Source:** `{ORDER_LOG_JSONL}` (authoritative) + text logs (supplemental)")
    ls.append("")

    # ── Block 2: Intents vs Rejected ──
    ls.append("---")
    ls.append("## 2. Total Intents Generated vs Rejected")
    ls.append("")
    ls.append("| Metric | Count | % |")
    ls.append("|--------|------:|--:|")
    ls.append(
        f"| ORDER_INTENT generated       | **{total_intents:,}** | 100% |")
    ls.append(
        f"| ORDER_REJECTED (all reasons) | **{total_rejected:,}** | **{pct_rej:.1f}%** |")
    ls.append(
        f"| Passed → ORDER_PLACED        | **{total_placed:,}** | {pct_place:.1f}% |")
    other = total_intents - total_rejected - total_placed
    if other > 0:
        ls.append(
            f"| In-flight / unresolved       | {other:,} | {(other/total_intents*100):.1f}% |")
    ls.append("")

    # ── Block 1: Top-10 why-codes ──
    ls.append("---")
    ls.append("## 1. Top-10 Reject Reasons")
    ls.append("")
    ls.append("| # | NRR / Why | Count | % of intents | % of rejects |")
    ls.append("|---|-----------|------:|-------------:|-------------:|")
    for i, (code, cnt) in enumerate(why_counter.most_common(10), 1):
        p_int = (cnt / total_intents * 100) if total_intents else 0
        p_rej = (cnt / total_rejected * 100) if total_rejected else 0
        label = code if len(code) <= 80 else code[:77] + "..."
        ls.append(
            f"| {i} | `{label}` | {cnt:,} | {p_int:.1f}% | {p_rej:.1f}% |")
    ls.append("")

    # ── Block 3: Gate groups ──
    ls.append("---")
    ls.append("## 3. Rejected per Gate Group")
    ls.append("")
    ls.append("| Gate Group | Rejected | % of rejects | % of intents |")
    ls.append("|------------|--------:|-------------:|-------------:|")
    for grp, cnt in group_counter.most_common():
        p_g = (cnt / total_group * 100) if total_group else 0
        p_gi = (cnt / total_intents * 100) if total_intents else 0
        ls.append(f"| {grp} | {cnt:,} | {p_g:.1f}% | {p_gi:.1f}% |")
    ls.append("")

    if txt_lines > 0:
        ls.append("<details>")
        ls.append(
            "<summary>Supplemental from text logs (non-deduplicated)</summary>")
        ls.append(f"\nText-log matched lines: **{txt_lines:,}**\n")
        ls.append("| Gate Group (text) | Count |")
        ls.append("|-------------------|------:|")
        for grp, cnt in txt_groups.most_common():
            ls.append(f"| {grp} | {cnt:,} |")
        ls.append("\n</details>")
        ls.append("")

    # ── Block 4: Passed but not filled ──
    ls.append("---")
    ls.append("## 4. Passed All Gates But Not Filled (Limit Order Fate)")
    ls.append("")
    ls.append("| Metric | Count | % of placed |")
    ls.append("|--------|------:|------------:|")
    ls.append(
        f"| ORDER_PLACED (limit orders)         | **{total_placed:,}** | 100% |")
    ls.append(
        f"| ORDER_FILL_DISCOVERED               | **{total_fills:,}** | {(total_fills/total_placed*100 if total_placed else 0):.1f}% |")
    n_to = len(placed_then_timeout)
    n_can = len(placed_then_cancel)
    n_both = len(placed_then_both)
    total_not_filled = n_to + n_can + n_both
    ls.append(
        f"| ORDER_TIMEOUT (never filled)        | **{n_to + n_both:,}** | {((n_to+n_both)/total_placed*100 if total_placed else 0):.1f}% |")
    ls.append(
        f"| ORDER_CANCELLED after OPEN          | **{n_can + n_both:,}** | {((n_can+n_both)/total_placed*100 if total_placed else 0):.1f}% |")
    ls.append(
        f"| **Total not filled** (deduplicated) | **{total_not_filled:,}** | **{(total_not_filled/total_placed*100 if total_placed else 0):.1f}%** |")
    no_match = total_placed - len(placed_then_fill) - total_not_filled
    if no_match > 0:
        ls.append(
            f"| Still open / unaccounted            | {no_match:,} | {(no_match/total_placed*100 if total_placed else 0):.1f}% |")
    ls.append("")
    ls.append(
        f"> Standalone ORDER_TIMEOUT in window: **{total_timeouts}**, ORDER_CANCELLED: **{total_cancelled}**")
    ls.append("")

    # Sample not-filled
    samples = (placed_then_cancel +
               placed_then_timeout + placed_then_both)[:10]
    if samples:
        ls.append("### Sample Limit Orders That Were Not Filled (first 10)")
        ls.append("```")
        cancel_set = {r.get("rid", "")
                      for r in placed_then_cancel + placed_then_both}
        both_set = {r.get("rid", "") for r in placed_then_both}
        for r in samples:
            ts = parse_ts_ms(r.get("timestamp"))
            ts_s = ts.strftime("%Y-%m-%d %H:%M:%S") if ts else "?"
            fate = ("TO+CANCEL" if r.get("rid", "") in both_set
                    else "CANCELLED" if r.get("rid", "") in cancel_set
                    else "TIMEOUT")
            ls.append(
                f"  [{ts_s}] {r.get('symbol','?'):<12} {r.get('side','?'):<5}"
                f" qty={str(r.get('quantity','?')):<8} price={str(r.get('price','?')):<10}"
                f" fate={fate}  rid={r.get('rid','?')[:36]}"
            )
        ls.append("```")
        ls.append("")

    # ── Appendix ──
    ls.append("---")
    ls.append("## Appendix: Raw Event Counts (JSONL Source of Truth)")
    ls.append("")
    ls.append("| Event Type | Count |")
    ls.append("|------------|------:|")
    ls.append(f"| ORDER_INTENT           | {total_intents:,} |")
    ls.append(f"| ORDER_REJECTED         | {total_rejected:,} |")
    ls.append(f"| ORDER_PLACED           | {total_placed:,} |")
    ls.append(f"| ORDER_FILL_DISCOVERED  | {total_fills:,} |")
    ls.append(f"| ORDER_TIMEOUT          | {total_timeouts:,} |")
    ls.append(f"| ORDER_CANCELLED        | {total_cancelled:,} |")
    ls.append("")

    return "\n".join(ls)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reject forensic audit for last N hours")
    parser.add_argument("--hours", type=int, default=72)
    parser.add_argument("--out", type=str, default=None)
    args = parser.parse_args()

    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(hours=args.hours)

    print(
        f"[reject_audit_72h v2] Window: {cutoff.strftime('%Y-%m-%d %H:%M UTC')} → {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"[reject_audit_72h v2] Lookback: {args.hours}h\n")

    data = analyze_jsonl(cutoff)
    print(f"  ORDER_INTENT:    {data.get('total_intents', 0):,}")
    print(f"  ORDER_REJECTED:  {data.get('total_rejected', 0):,}")
    print(f"  ORDER_PLACED:    {data.get('total_placed', 0):,}")
    print(f"  ORDER_TIMEOUT:   {data.get('total_timeouts', 0):,}")
    print(f"  ORDER_CANCELLED: {data.get('total_cancelled', 0):,}")
    print(f"  ORDER_FILL:      {data.get('total_fills', 0):,}")
    print()

    txt_groups, txt_lines = analyze_text_logs(cutoff)
    print(f"  Text-log matched: {txt_lines:,} lines (supplemental)")
    print()

    report = render_report(cutoff, data, txt_groups, txt_lines, args.hours)
    print(report)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report, encoding="utf-8")
        print(f"\n[reject_audit_72h v2] Report saved → {out_path}")


if __name__ == "__main__":
    main()
