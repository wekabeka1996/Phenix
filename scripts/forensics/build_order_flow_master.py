#!/usr/bin/env python3
"""
Canonical Order Flow Forensics Master Script
Implements memory-safe streaming, explicit confidence modeling, scope-inventory,
and strictly separates outcome lifecycle from reconstruction provenance.
"""

import os
import re
import csv
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Iterator, Generator
import heapq
import logging

ROOT_DIR = Path(__file__).parent.parent.parent
LOGS_DIR = ROOT_DIR / "logs"
DATA_RECORDER_DIR = ROOT_DIR / "data/recorder"
REPORTS_DIR = ROOT_DIR / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ─── REGEX PATTERNS ────────────────────────
TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}(?:[.,]\d{3,6})?(?:Z)?)")

REJECT_STRATEGY = re.compile(r"STRATEGY_SIGNAL_GATEWAY: (BLOCK|REJECT)\s*-\s*(.+)")
REJECT_DECISION = re.compile(r"SAFETY_GATES.*DENY|GATE_ANTI_FLAT.*Blocking|ANTI_FOMO|DIRECTIONAL_SANITY|PRICE_MOTION|Risk Gate Violation")
REJECT_EXEC_GUARD = re.compile(r"EXPOSURE_FAIL_CLOSED|QOS_BLOCK|HOLDING_PERIOD|ARBITRATION_REJECT|GATE_BLOCKED")

# ─── TYPING ─────────────────────────────
CONFIDENCE_EXACT = "exact"
CONFIDENCE_STRONG = "strong"
CONFIDENCE_WEAK = "weak"
CONFIDENCE_UNLINKED = "unlinked"

OUTCOME_EXECUTED = "executed"
OUTCOME_STRATEGY_BLOCKED = "strategy_blocked"
OUTCOME_DECISION_REJECTED = "decision_rejected"
OUTCOME_EXEC_GUARD_BLOCKED = "execution_guard_blocked"
OUTCOME_ORDER_REJECTED = "order_rejected"
OUTCOME_TIMEOUT_NON_FILL = "timeout_non_fill"
OUTCOME_PENDING = "pending_or_open"
OUTCOME_UNKNOWN = "unknown_terminal"

def parse_ts(ts_str: str) -> Optional[datetime]:
    ts_str = ts_str.replace("T", " ").replace("Z", "").strip().replace(",", ".")
    try:
        if '.' in ts_str:
            return datetime.strptime(ts_str[:26], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
        return datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None

def extract_ts_from_line(line: str) -> Optional[datetime]:
    if line.startswith('{'):
        try:
            d = json.loads(line)
            ts_val = d.get('timestamp') or d.get('Timestamp') or d.get('timestamp_utc')
            if ts_val:
                if isinstance(ts_val, (int, float)):
                    if ts_val > 1000000000000:
                        return datetime.fromtimestamp(ts_val / 1000.0, tz=timezone.utc)
                    else:
                        return datetime.fromtimestamp(ts_val, tz=timezone.utc)
                return parse_ts(ts_val)
        except Exception:
            pass
    m = TS_RE.search(line)
    if m:
        return parse_ts(m.group(1))
    return None

def scan_file_boundaries(filepath: Path) -> Tuple[Optional[datetime], Optional[datetime], int]:
    min_ts, max_ts = None, None
    fail_count = 0
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            lines = [next(f) for _ in range(500)]
            for line in lines:
                ts = extract_ts_from_line(line)
                if ts:
                    min_ts = ts
                    break
                fail_count += 1
            
            # fast forward to end
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size > 10000:
                f.seek(size - 10000, os.SEEK_SET)
            else:
                f.seek(0)
            end_lines = f.readlines()
            for line in reversed(end_lines):
                if not line.strip(): continue
                ts = extract_ts_from_line(line)
                if ts:
                    max_ts = ts
                    break
    except Exception:
        fail_count += 1
        
    return min_ts, max_ts, fail_count

def generate_source_inventory() -> Tuple[Dict[str, Path], datetime, datetime]:
    print("--> Building Source Inventory...")
    inventory_records = []
    
    global_min: Optional[datetime] = None
    global_max: Optional[datetime] = None
    
    valid_files: Dict[str, Path] = {}
    
    for fpath in LOGS_DIR.glob("**/*"):
        if not fpath.is_file(): continue
        if not fpath.name.endswith(".log") and not ".log." in fpath.name and not fpath.name.endswith(".jsonl"): continue

        min_ts, max_ts, fail_count = scan_file_boundaries(fpath)
        
        inc = False
        if min_ts and max_ts:
            inc = True
            valid_files[fpath.name] = fpath
            if global_min is None or min_ts < global_min: global_min = min_ts
            if global_max is None or max_ts > global_max: global_max = max_ts
            
        inventory_records.append({
            "source_path": fpath.name,
            "source_type": fpath.suffix.replace('.', '') or "log_rolling",
            "min_ts_seen": min_ts.isoformat() if min_ts else None,
            "max_ts_seen": max_ts.isoformat() if max_ts else None,
            "parse_fail_count": fail_count,
            "included_in_final_scope": inc
        })

    with open(REPORTS_DIR / "source_inventory.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=inventory_records[0].keys())
        writer.writeheader()
        writer.writerows(inventory_records)
        
    assert global_min and global_max, "Could not determine temporal scope."
    print(f"    Global Scope: {global_min} to {global_max}")
    return valid_files, global_min, global_max

# ─── DATA MODELS ─────────────────────────

class Event:
    __slots__ = ('ts', 'source', 'payload', 'raw_line', 'is_json')
    def __init__(self, ts: datetime, source: str, raw_line: str):
        self.ts = ts
        self.source = source
        self.raw_line = raw_line.strip()
        self.is_json = self.raw_line.startswith('{')
        self.payload = None
        if self.is_json:
            try:
                self.payload = json.loads(self.raw_line)
            except Exception:
                self.is_json = False

    def __lt__(self, other):
        return self.ts < other.ts

class AttemptRecord:
    def __init__(self, ts: datetime, attempt_id: str, symbol: str, side: str, price: float):
        self.intent_ts = ts
        self.attempt_id = attempt_id
        self.symbol = symbol
        self.side = side
        self.intent_price = price
        
        self.outcome = OUTCOME_UNKNOWN # default
        self.confidence = CONFIDENCE_UNLINKED
        self.reject_reason = ""
        self.trace_synthetic = False
        self.order_instance_id = "" # links to exchange order id if known
        self.regime = ""
        
        # Package B Extensions
        self.exit_ts = None
        self.exit_price = 0.0
        self.realized_pnl = 0.0
        self.commission = 0.0
        self.is_exact_roundtrip = False
        
    def to_row(self):
        return {
            "attempt_id": self.attempt_id,
            "synthetic_id": self.trace_synthetic,
            "symbol": self.symbol,
            "side": self.side,
            "regime": self.regime,
            "intent_price": self.intent_price,
            "intent_ts": self.intent_ts.isoformat(),
            "outcome": self.outcome,
            "confidence": self.confidence,
            "reject_reason": self.reject_reason,
            "order_instance_id": self.order_instance_id,
            "exit_ts": self.exit_ts.isoformat() if self.exit_ts else "",
            "exit_price": self.exit_price,
            "realized_pnl": self.realized_pnl,
            "commission": self.commission,
            "exact_roundtrip": self.is_exact_roundtrip
        }

# ─── STREAMING ENGINE ─────────────────────────

def file_event_generator(fpath: Path, min_bound: datetime, max_bound: datetime) -> Generator[Event, None, None]:
    source_name = fpath.name
    with open(fpath, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if not line.strip(): continue
            ts = extract_ts_from_line(line)
            if not ts: continue
            if min_bound <= ts <= max_bound:
                yield Event(ts, source_name, line)

def _generate_synthetic_id(ts: datetime, symbol: str, side: str) -> str:
    h = hashlib.sha256(f"{ts.isoformat()}|{symbol}|{side}".encode()).hexdigest()
    return f"SYN_{h[:12]}"

class Engine:
    def __init__(self):
        self.active_attempts: List[AttemptRecord] = []
        self.finalized_attempts: List[AttemptRecord] = []
        self.index_by_attempt_id: Dict[str, AttemptRecord] = {}
        self.index_by_order_id: Dict[str, AttemptRecord] = {}
        self.coverage = {
            "attempts": 0, "ambiguous": 0, "unlinked_rows": 0, "weak_join_rows": 0
        }
        
    def find_best_candidate(self, ts: datetime, symbol: str, side: str=None) -> Tuple[Optional[AttemptRecord], str]:
        # Nearest neighbor heuristics (active intents in last 10s)
        candidates = [a for a in self.active_attempts if (ts - a.intent_ts).total_seconds() < 10.0 and a.symbol == symbol]
        if side:
            candidates = [a for a in candidates if a.side.upper() == side.upper()]
            
        if not candidates:
            return None, CONFIDENCE_UNLINKED
            
        if len(candidates) == 1:
            diff = abs((ts - candidates[0].intent_ts).total_seconds())
            if diff < 0.005: 
                return candidates[0], CONFIDENCE_STRONG
            return candidates[0], CONFIDENCE_WEAK
            
        # Collision tie-break
        candidates.sort(key=lambda x: abs((ts - x.intent_ts).total_seconds()))
        best = candidates[0]
        second = candidates[1]
        t1 = abs((ts - best.intent_ts).total_seconds())
        t2 = abs((ts - second.intent_ts).total_seconds())
        
        if abs(t1 - t2) < 0.001:
            best.confidence = CONFIDENCE_UNLINKED
            best.reject_reason = "collision_discarded"
            return best, CONFIDENCE_UNLINKED
            
        return best, CONFIDENCE_WEAK

    def process_stream(self, file_dict: Dict[str, Path], min_ts: datetime, max_ts: datetime):
        print("--> Streaming and Joining Events...")
        generators = [file_event_generator(p, min_ts, max_ts) for p in file_dict.values()]
        merged_stream = heapq.merge(*generators)

        for i, ev in enumerate(merged_stream):
            
            # Prune active window > 60s
            while self.active_attempts and (ev.ts - self.active_attempts[0].intent_ts).total_seconds() > 60:
                old = self.active_attempts.pop(0)
                if old.outcome == OUTCOME_UNKNOWN:
                    old.outcome = OUTCOME_TIMEOUT_NON_FILL
                self.finalized_attempts.append(old)
            
            # 1. ATTEMPT EXISTENCE
            is_order_intent = ev.is_json and ev.payload and ev.payload.get("event_type") == "ORDER_INTENT"
            if "TRADE_INTENT_PROPOSED" in ev.raw_line or "decision.intent_proposed" in ev.raw_line or is_order_intent:
                # Need to parse details
                syn = "UNKNOWN"
                side = "UNKNOWN"
                px = 0.0
                trace_id = None
                regime = ""
                if ev.is_json and ev.payload:
                    d = ev.payload.get("data", ev.payload)
                    syn = d.get('symbol') or d.get('Symbol', 'UNKNOWN')
                    side = d.get('side') or d.get('IntentSide', 'UNKNOWN')
                    px = d.get('price', 0.0)
                    trace_id = d.get('trace_id') or d.get("lifecycle_id") or d.get("rid")
                    regime = d.get("regime", "")
                    
                else:
                    mc = re.search(r"symbol=(\w+).*?side=(\w+).*?price=([\d.]+)", ev.raw_line)
                    if mc:
                        syn, side, px = mc.groups()
                    else:
                        # Fallback for [SOLUSDT] STRATEGY_SIGNAL_GATEWAY...
                        msym = re.search(r"\[((?:BTC|ETH|SOL|XRP)[A-Z0-9_-]+)\]", ev.raw_line)
                        if msym: syn = msym.group(1)
                        if "SELL" in ev.raw_line: side = "SELL"
                        elif "BUY" in ev.raw_line: side = "BUY"
                        
                        mrid = re.search(r"rid=([\w-]+)", ev.raw_line)
                        if mrid: trace_id = mrid.group(1)
                        
                at_id = trace_id or _generate_synthetic_id(ev.ts, syn, side)
                att = AttemptRecord(ev.ts, at_id, syn, side, float(px))
                if not trace_id:
                    att.trace_synthetic = True
                att.regime = regime
                
                self.coverage["attempts"] += 1
                self.active_attempts.append(att)
                if at_id:
                    self.index_by_attempt_id[at_id] = att
                
            # 2. EXACT JSON ORDER ACTIONS (Order log has highest fidelity)
            elif "order_log" in ev.source and ev.is_json and ev.payload:
                event_t = ev.payload.get("event_type", "")
                sym = ev.payload.get("symbol", "UNKNOWN")
                oid = ev.payload.get("client_order_id", "") or ev.payload.get("rid", "")
                
                if event_t == "ORDER_PLACED" or event_t == "ORDER_INTENT":
                    cand, conf = self.find_best_candidate(ev.ts, sym)
                    if cand:
                        cand.outcome = OUTCOME_PENDING
                        if event_t == "ORDER_PLACED":
                            cand.order_instance_id = oid
                            if oid:
                                self.index_by_order_id[oid] = cand
                        if cand.confidence != CONFIDENCE_EXACT:
                            cand.confidence = conf
                        
                elif event_t == "ORDER_REJECTED":
                    cand, conf = self.find_best_candidate(ev.ts, sym)
                    if cand:
                        cand.outcome = OUTCOME_ORDER_REJECTED
                        if cand.confidence != CONFIDENCE_EXACT:
                            cand.confidence = conf
                
                elif event_t == "DECISION_INTENT_REJECTED":
                    meta = ev.payload.get("metadata", {})
                    why = ev.payload.get("why", "") or meta.get("reject_reason", "")
                    cand, conf = self.find_best_candidate(ev.ts, sym)
                    if not cand:
                        cand = AttemptRecord(ev.ts, ev.payload.get("rid", "unlinked"), sym, ev.payload.get("side", "UNKNOWN"), 0.0)
                        self.active_attempts.append(cand)
                        self.coverage["attempts"] += 1
                        conf = CONFIDENCE_STRONG

                    if "SAFETY" in why or "REGIME" in why or "DENY" in why:
                        cand.outcome = OUTCOME_DECISION_REJECTED
                    else:
                        cand.outcome = OUTCOME_STRATEGY_BLOCKED
                    cand.reject_reason = why
                    
                    if cand.confidence != CONFIDENCE_EXACT:
                        cand.confidence = conf
                    if oid:
                        cand.order_instance_id = oid
                
                elif event_t == "ORDER_FILLED":
                    # EXACT TRUTH OF EXECUTION - using O(1) lookup
                    l_id = ev.payload.get("lifecycle_id", "")
                    meta = ev.payload.get("metadata", {})
                    close_reason = ev.payload.get("close_reason", "")
                    
                    tgt = None
                    if oid and oid in self.index_by_order_id:
                        tgt = self.index_by_order_id[oid]
                    elif l_id and l_id in self.index_by_attempt_id:
                        tgt = self.index_by_attempt_id[l_id]
                    
                    if tgt:
                        if close_reason in ("TP", "SL", "TL", "EXPIRED", "SIGNAL") or meta.get("realized_pnl", 0.0) != 0.0:
                            # It's an EXIT fill
                            tgt.exit_ts = ev.ts
                            tgt.exit_price = float(ev.payload.get("price", 0.0))
                            tgt.realized_pnl += float(meta.get("realized_pnl", 0.0))
                            tgt.commission += float(meta.get("commission", 0.0))
                            tgt.is_exact_roundtrip = True
                        else:
                            # It's an ENTRY fill
                            tgt.outcome = OUTCOME_EXECUTED
                            tgt.confidence = CONFIDENCE_EXACT
                
            # 3. STRATEGY BLOCKED (Text Logs)
            elif REJECT_STRATEGY.search(ev.raw_line):
                m = REJECT_STRATEGY.search(ev.raw_line)
                typ, reason = m.group(1), m.group(2)
                
                # We often don't have symbol printed clearly in STRATEGY gateway logs unless we regex precisely
                msym = re.search(r"((?:BTC|ETH|SOL|XRP)[A-Z0-9_-]+)", ev.raw_line)
                sym = msym.group(1) if msym else "UNKNOWN"
                
                cand, conf = self.find_best_candidate(ev.ts, sym)
                if cand and cand.outcome == OUTCOME_UNKNOWN:
                    cand.outcome = OUTCOME_STRATEGY_BLOCKED
                    cand.reject_reason = f"{typ}-{reason}"
                    cand.confidence = conf

            # 4. DECISION REJECTED (Text Logs)
            elif REJECT_DECISION.search(ev.raw_line):
                msym = re.search(r"((?:BTC|ETH|SOL|XRP)[A-Z0-9_-]+)", ev.raw_line)
                sym = msym.group(1) if msym else "UNKNOWN"
                cand, conf = self.find_best_candidate(ev.ts, sym)
                if cand and cand.outcome == OUTCOME_UNKNOWN:
                    cand.outcome = OUTCOME_DECISION_REJECTED
                    cand.reject_reason = REJECT_DECISION.search(ev.raw_line).group(0)
                    cand.confidence = conf
                    
            # 5. EXEC GUARD BLOCKED (Text Logs)
            elif REJECT_EXEC_GUARD.search(ev.raw_line):
                msym = re.search(r"((?:BTC|ETH|SOL|XRP)[A-Z0-9_-]+)", ev.raw_line)
                sym = msym.group(1) if msym else "UNKNOWN"
                cand, conf = self.find_best_candidate(ev.ts, sym)
                if cand and cand.outcome == OUTCOME_UNKNOWN:
                    cand.outcome = OUTCOME_EXEC_GUARD_BLOCKED
                    cand.reject_reason = REJECT_EXEC_GUARD.search(ev.raw_line).group(0)
                    cand.confidence = conf

            if i > 0 and i % 50000 == 0:
                print(f"      ... processed {i} events. Active window size: {len(self.active_attempts)}")

        # Flush remaining
        self.finalized_attempts.extend(self.active_attempts)
        self.active_attempts = []

    def build_coverage_ledger(self):
        print("--> Generating Coverage Ledger...")
        import pandas as pd
        rows = [a.to_row() for a in self.finalized_attempts]
        if not rows:
            print("WARNING: No rows extracted.")
            return

        df = pd.DataFrame(rows)
        
        # 1. Compute totals
        self.coverage["unlinked_rows"] = len(df[df['confidence'] == CONFIDENCE_UNLINKED])
        self.coverage["weak_join_rows"] = len(df[df['confidence'] == CONFIDENCE_WEAK])
        self.coverage["ambiguous"] = len(df[df['outcome'] == OUTCOME_UNKNOWN])
        
        # 2. Cross tab
        crosstab = pd.crosstab(df['outcome'], df['confidence'], margins=True)
        crosstab.to_csv(REPORTS_DIR / "coverage_ledger.csv")
        
        df[df['outcome'] == OUTCOME_EXECUTED].to_csv(REPORTS_DIR / "executed_trades_master.csv", index=False)
        df[df['outcome'] != OUTCOME_EXECUTED].to_csv(REPORTS_DIR / "rejected_attempts_master.csv", index=False)
        df.to_csv(REPORTS_DIR / "order_attempts_master.csv", index=False)
        
        print("\nLedger Extract:")
        print(crosstab)
        print(f"\nWeak Join Count: {self.coverage['weak_join_rows']}")
        print(f"Unlinked Target Count: {self.coverage['unlinked_rows']}")

def main():
    if not LOGS_DIR.exists():
        print(f"ERROR: Log directory {LOGS_DIR} not found.")
        return

    valid_files, min_ts, max_ts = generate_source_inventory()
    eng = Engine()
    eng.process_stream(valid_files, min_ts, max_ts)
    eng.build_coverage_ledger()
    print("--> Complete.")

if __name__ == "__main__":
    main()
