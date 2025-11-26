import argparse
import json
import sys
from typing import List, Dict, Any, Optional


def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parse a single log line to extract BRACKET_EVAL_SNAPSHOT frame.

    Supports two formats:
    1. New format (V2): event_kind=BRACKET_EVAL_SNAPSHOT with snapshot field
    2. Legacy format: message contains BRACKET_EVAL_SNAPSHOT with snapshot in extra/properties
    """
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        # Skip non-JSON lines
        return None

    # Check if this is a BRACKET_EVAL_SNAPSHOT event (V2 format)
    event_kind = record.get("event_kind", "")
    if event_kind == "BRACKET_EVAL_SNAPSHOT":
        # V2 format: snapshot is directly in the record
        snapshot_str = record.get("snapshot")

        if snapshot_str:
            try:
                if isinstance(snapshot_str, str):
                    snapshot_data = json.loads(snapshot_str)
                else:
                    snapshot_data = snapshot_str

                # Extract timestamp (V2 uses 'ts' key)
                ts = record.get("ts") or record.get(
                    "timestamp") or record.get("time")

                # Construct the replay frame
                frame = {
                    "ts": ts,
                    "symbol": snapshot_data.get("symbol"),
                    "side": snapshot_data.get("side"),
                    "position_qty": snapshot_data.get("position_qty"),
                    "position_cycle_id": snapshot_data.get("position_cycle_id"),
                    "orders_snapshot_state": snapshot_data.get("orders_snapshot_state"),
                    "orders": snapshot_data.get("open_brackets", []),
                    "bracket_plan": snapshot_data.get("bracket_plan", [])
                }
                return frame
            except Exception:
                # Ignore parsing errors for individual lines
                return None

    # Legacy format: check message field
    message = record.get("message", "")
    if "BRACKET_EVAL_SNAPSHOT" not in message:
        return None

    # Look for snapshot payload in legacy locations
    snapshot_str = record.get("snapshot")

    if not snapshot_str:
        if "extra" in record and isinstance(record["extra"], dict):
            snapshot_str = record["extra"].get("snapshot")
        elif "properties" in record and isinstance(record["properties"], dict):
            snapshot_str = record["properties"].get("snapshot")

    if not snapshot_str:
        return None

    try:
        if isinstance(snapshot_str, str):
            snapshot_data = json.loads(snapshot_str)
        else:
            snapshot_data = snapshot_str

        # Extract timestamp from log record (legacy keys)
        ts = record.get("timestamp") or record.get(
            "time") or record.get("ts") or record.get("asctime")

        # Construct the replay frame
        frame = {
            "ts": ts,
            "symbol": snapshot_data.get("symbol"),
            "side": snapshot_data.get("side"),
            "position_qty": snapshot_data.get("position_qty"),
            "position_cycle_id": snapshot_data.get("position_cycle_id"),
            "orders_snapshot_state": snapshot_data.get("orders_snapshot_state"),
            "orders": snapshot_data.get("open_brackets", []),
            "bracket_plan": snapshot_data.get("bracket_plan", [])
        }
        return frame

    except Exception:
        # Ignore parsing errors for individual lines
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Extract OCO replay frames from logs.")
    parser.add_argument("--runtime-logs", required=True,
                        help="Path to input log file (JSONL)")
    parser.add_argument("--out", required=True,
                        help="Path to output JSON file")

    args = parser.parse_args()

    frames = []

    try:
        with open(args.runtime_logs, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                frame = parse_log_line(line)
                if frame:
                    frames.append(frame)
    except FileNotFoundError:
        print(f"Error: File not found {args.runtime_logs}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        sys.exit(1)

    # Sort by timestamp if available
    # We assume ISO strings or comparable values. If mixed or missing, this might be unstable.
    # We'll put frames with 'None' ts at the end or beginning.
    frames.sort(key=lambda x: x.get("ts") or "")

    try:
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump(frames, f, indent=2)
        print(f"Extracted {len(frames)} frames to {args.out}")
    except Exception as e:
        print(f"Error writing output: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
