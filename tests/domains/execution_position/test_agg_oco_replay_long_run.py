import json
import pytest
from pathlib import Path
from typing import List, Dict, Any

from apps.reference.domains.execution_position.shadow_execpos.agg_oco_replay import (
    AggOcoReplayEnforcer,
)

REPLAY_FILE = Path("docs") / "OCO_REPLAY_SAMPLE.json"

def load_replay_sample() -> List[Dict[str, Any]]:
    if not REPLAY_FILE.exists():
        pytest.skip(f"Replay file not found: {REPLAY_FILE}")
    
    text = REPLAY_FILE.read_text(encoding="utf-8")
    data = json.loads(text)
    assert isinstance(data, list)
    return data

def is_sl(order: Dict[str, Any]) -> bool:
    """Check if order is Stop Loss."""
    otype = order.get("type", "").upper()
    cid = str(order.get("clientOrderId", "")).upper()
    
    if "STOP" in otype:
        return True
    if "-SL-" in cid:
        return True
    return False

def is_tp(order: Dict[str, Any]) -> bool:
    """Check if order is Take Profit."""
    otype = order.get("type", "").upper()
    cid = str(order.get("clientOrderId", "")).upper()
    
    if "TAKE_PROFIT" in otype:
        return True
    if "-TP-" in cid:
        return True
    return False

def assert_bracket_invariants(frame: Dict[str, Any]) -> None:
    pos_qty = float(frame.get("position_qty", 0.0))
    symbol = frame.get("symbol", "UNKNOWN")
    side = frame.get("side", "UNKNOWN")
    orders = frame.get("orders", [])
    ts = frame.get("ts", "UNKNOWN")

    tp_orders = [o for o in orders if is_tp(o)]
    sl_orders = [o for o in orders if is_sl(o)]

    # INV-1: no brackets for flat position
    if pos_qty == 0:
        assert not tp_orders, f"[{ts}] {symbol}/{side} flat but TP exists: {tp_orders}"
        assert not sl_orders, f"[{ts}] {symbol}/{side} flat but SL exists: {sl_orders}"
        return

    # For non-flat position:
    # INV-2: at most 1 SL + 1 TP
    assert len(tp_orders) <= 1, f"[{ts}] {symbol}/{side} more than 1 TP: {len(tp_orders)}"
    assert len(sl_orders) <= 1, f"[{ts}] {symbol}/{side} more than 1 SL: {len(sl_orders)}"

    # INV-3: sum qty of brackets <= position_qty * (1 + epsilon)
    eps = 1e-6
    # Note: Assuming orders list contains ALL open orders, we filter for this symbol/side implicitly
    # by the nature of the snapshot frame (it is per symbol).
    # However, we should check if the order side matches the closing side for the position.
    # Position LONG -> Order SELL. Position SHORT -> Order BUY.
    # The replay frame generator should have already filtered relevant orders, 
    # but let's assume 'orders' in frame are the ones relevant to this bracket context.
    
    total_sl_qty = sum(float(o.get("qty", 0)) for o in sl_orders)
    total_tp_qty = sum(float(o.get("qty", 0)) for o in tp_orders)
    
    # Check SL sum
    assert total_sl_qty <= pos_qty * (1 + eps), (
        f"[{ts}] {symbol}/{side} SL qty {total_sl_qty} > pos {pos_qty}"
    )
    
    # Check TP sum
    assert total_tp_qty <= pos_qty * (1 + eps), (
        f"[{ts}] {symbol}/{side} TP qty {total_tp_qty} > pos {pos_qty}"
    )

def test_agg_oco_replay_long_run_invariants():
    """
    Iterate over replay frames and verify OCO invariants.
    Expected to FAIL on real logs if bugs exist (duplicate TP/SL, size mismatch).
    """
    frames = load_replay_sample()
    
    failures = []
    enforcer = AggOcoReplayEnforcer()
    
    for i, frame in enumerate(frames):
        repaired, repairs = enforcer.apply_frame(frame)
        try:
            assert_bracket_invariants(repaired)
        except AssertionError as e:
            suffix = ""
            if repairs or repaired.get("orphan_orders"):
                suffix = f" | repairs={repairs or []} orphans={len(repaired.get('orphan_orders', []))}"
            failures.append(f"Frame {i}: {str(e)}{suffix}")
            
    if failures:
        pytest.fail(f"Invariant violations found in {len(failures)} frames:\n" + "\n".join(failures[:10]))

def load_real_replay_sample() -> List[Dict[str, Any]]:
    path = Path("docs") / "OCO_REPLAY_REAL_SAMPLE.json"
    if not path.exists():
        pytest.skip(f"Real replay file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    return data

def test_agg_oco_real_replay_invariants():
    """
    Analyze real replay sample for invariant violations.
    This test is EXPECTED TO FAIL if the sample contains bugs.
    It prints violations to stdout for reporting.
    """
    frames = load_real_replay_sample()
    violations = []
    enforcer = AggOcoReplayEnforcer()

    for idx, frame in enumerate(frames):
        repaired, repairs = enforcer.apply_frame(frame)
        try:
            assert_bracket_invariants(repaired)
        except AssertionError as exc:
            violations.append(
                (
                    idx,
                    repaired.get("symbol"),
                    repaired.get("side"),
                    f"{exc}",
                    repairs or [],
                )
            )

    # Print violations for report generation
    if violations:
        print(f"\n[REAL_REPLAY_ANALYSIS] Found {len(violations)} violations:")
        for idx, symbol, side, msg, repairs in violations[:20]:
            suffix = f" repairs={repairs}" if repairs else ""
            print(f"[VIOLATION] idx={idx} {symbol}/{side}: {msg}{suffix}")
            
    # Fail if violations found (to signal RED state as requested)
    assert not violations, f"Found {len(violations)} invariant violations in real replay sample"
