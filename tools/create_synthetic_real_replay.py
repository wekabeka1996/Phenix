import json
from datetime import datetime, timedelta

def create_frame(ts, symbol, side, pos_qty, orders, plan):
    return {
        "ts": ts.isoformat() + "Z",
        "symbol": symbol,
        "side": side,
        "position_qty": pos_qty,
        "position_cycle_id": 1,
        "orders_snapshot_state": "FRESH",
        "orders": orders,
        "bracket_plan": plan
    }

def main():
    start_time = datetime(2025, 11, 24, 12, 0, 0)
    frames = []
    
    # Scenario 1: BTCUSDT - Normal Flow
    # 12:00 - Entry
    frames.append(create_frame(
        start_time, "BTCUSDT", "LONG", 1.0, 
        [], 
        [{"action_type": "PLACE_SL", "qty": 1.0}, {"action_type": "PLACE_TP", "qty": 1.0}]
    ))
    
    # 12:01 - Brackets Placed
    frames.append(create_frame(
        start_time + timedelta(minutes=1), "BTCUSDT", "LONG", 1.0, 
        [
            {"clientOrderId": "AUR-SL-1", "type": "STOP_MARKET", "qty": 1.0, "side": "SELL"},
            {"clientOrderId": "AUR-TP-1", "type": "TAKE_PROFIT_MARKET", "qty": 1.0, "side": "SELL"}
        ], 
        []
    ))

    # Scenario 2: ETHUSDT - Duplicate TP Bug
    # 12:10 - Normal
    frames.append(create_frame(
        start_time + timedelta(minutes=10), "ETHUSDT", "SHORT", 10.0, 
        [
            {"clientOrderId": "AUR-SL-2", "type": "STOP_MARKET", "qty": 10.0, "side": "BUY"},
            {"clientOrderId": "AUR-TP-2", "type": "TAKE_PROFIT_MARKET", "qty": 10.0, "side": "BUY"}
        ], 
        []
    ))
    
    # 12:11 - Duplicate TP appears (maybe manual place or race condition)
    frames.append(create_frame(
        start_time + timedelta(minutes=11), "ETHUSDT", "SHORT", 10.0, 
        [
            {"clientOrderId": "AUR-SL-2", "type": "STOP_MARKET", "qty": 10.0, "side": "BUY"},
            {"clientOrderId": "AUR-TP-2", "type": "TAKE_PROFIT_MARKET", "qty": 10.0, "side": "BUY"},
            {"clientOrderId": "AUR-TP-3", "type": "TAKE_PROFIT_MARKET", "qty": 10.0, "side": "BUY"} # Duplicate!
        ], 
        []
    ))

    # Scenario 3: SOLUSDT - Size Mismatch (Partial Close fail)
    # 12:20 - Position 50, Brackets 50
    frames.append(create_frame(
        start_time + timedelta(minutes=20), "SOLUSDT", "LONG", 50.0, 
        [
            {"clientOrderId": "AUR-SL-4", "type": "STOP_MARKET", "qty": 50.0, "side": "SELL"},
            {"clientOrderId": "AUR-TP-4", "type": "TAKE_PROFIT_MARKET", "qty": 50.0, "side": "SELL"}
        ], 
        []
    ))
    
    # 12:21 - Partial Close to 25, Brackets still 50
    frames.append(create_frame(
        start_time + timedelta(minutes=21), "SOLUSDT", "LONG", 25.0, 
        [
            {"clientOrderId": "AUR-SL-4", "type": "STOP_MARKET", "qty": 50.0, "side": "SELL"}, # Violation!
            {"clientOrderId": "AUR-TP-4", "type": "TAKE_PROFIT_MARKET", "qty": 50.0, "side": "SELL"} # Violation!
        ], 
        [{"action_type": "CANCEL_SL", "qty": 25.0}] # Plan might try to fix it
    ))

    with open("docs/OCO_REPLAY_REAL_SAMPLE.json", "w") as f:
        json.dump(frames, f, indent=2)
    
    print("Created docs/OCO_REPLAY_REAL_SAMPLE.json")

if __name__ == "__main__":
    main()
