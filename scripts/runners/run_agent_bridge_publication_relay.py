from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any, Dict

project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from apps.reference.domains.agent_bridge.publication import AgentBridgeRuntimePublisher
from apps.reference.domains.agent_bridge.reducer import bounded_tail_jsonl


LOG = logging.getLogger("agent_bridge.publication_relay")


def publish_latest(
    *,
    mirror_path: Path,
    output_dir: Path,
    symbols: list[str],
    tf_sec: int,
) -> Dict[str, Any]:
    rows, diagnostics = bounded_tail_jsonl(mirror_path, max_bytes=2 * 1024 * 1024, max_lines=1_000)
    wanted = set(symbols)
    latest: Dict[tuple[str, int], Dict[str, Any]] = {}
    for row in rows:
        symbol = str(row.get("symbol") or "").upper()
        try:
            row_tf = int(row.get("tf_sec") or 0)
            row_ts = int(row.get("ts_ms") or 0)
        except (TypeError, ValueError):
            continue
        if symbol not in wanted or row_tf != tf_sec:
            continue
        key = (symbol, row_tf)
        if row_ts >= int((latest.get(key) or {}).get("ts_ms") or 0):
            latest[key] = row

    publisher = AgentBridgeRuntimePublisher(
        event_bus=None,
        execution_position=None,
        output_dir=output_dir,
        symbols=symbols,
        source_owner="aurora_main_feature_mirror_relay",
    )
    for key in sorted(latest):
        publisher.ingest_mirror_record(latest[key])
    publisher.publish_initial()
    return {
        "schema_version": "agent-bridge-publication-relay/v0",
        "published_symbols": sorted(item[0] for item in latest),
        "tf_sec": tf_sec,
        "source_path": str(mirror_path),
        "source_size_bytes": mirror_path.stat().st_size if mirror_path.exists() else None,
        "bounded_tail_diagnostics": diagnostics,
        "source_owner": "aurora_main_feature_mirror_relay",
        "execution_runtime_available": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a safe atomic Agent Bridge snapshot from Aurora's main-owned feature mirror.")
    parser.add_argument("--mirror", type=Path, default=Path("logs/alpha_input/alpha_input_v1_live.jsonl"))
    parser.add_argument("--output-dir", type=Path, default=Path("ops/agent_bridge/runtime"))
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT")
    parser.add_argument("--tf-sec", type=int, default=300)
    parser.add_argument("--poll-sec", type=float, default=1.0)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    symbols = list(dict.fromkeys(part.strip().upper() for part in args.symbols.split(",") if part.strip()))
    if not symbols:
        parser.error("at least one symbol is required")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    stopped = False

    def stop(_signum, _frame):
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGINT, stop)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, stop)

    last_mtime_ns = -1
    while not stopped:
        try:
            mtime_ns = args.mirror.stat().st_mtime_ns
            if mtime_ns != last_mtime_ns:
                result = publish_latest(
                    mirror_path=args.mirror,
                    output_dir=args.output_dir,
                    symbols=symbols,
                    tf_sec=args.tf_sec,
                )
                LOG.info("PUBLICATION %s", json.dumps(result, separators=(",", ":")))
                last_mtime_ns = mtime_ns
        except Exception as exc:
            LOG.error("publication relay failed: %s", exc)
            if args.once:
                raise
        if args.once:
            break
        time.sleep(max(0.25, args.poll_sec))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
