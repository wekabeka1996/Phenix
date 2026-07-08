"""Local read-only Scenario Memory index/query utility."""
from __future__ import annotations

import argparse
from pathlib import Path

from apps.reference.domains.agent_bridge.scenario_memory import ScenarioMemoryStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "query", "summary"))
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--query-type", default="latest")
    parser.add_argument("--symbol")
    parser.add_argument("--horizon")
    parser.add_argument("--scenario")
    parser.add_argument("--packet-id")
    parser.add_argument("--symbols", default="BTCUSDT,ETHUSDT")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--max-tokens", type=int)
    args = parser.parse_args()
    store = ScenarioMemoryStore(Path(args.project_root))
    if args.command == "build":
        result = store.build_index(persist=True)
    elif args.command == "summary":
        kwargs = {"max_tokens": args.max_tokens} if args.max_tokens is not None else {}
        result = store.summary(args.symbols.split(","), **kwargs)
    else:
        kwargs = {"max_tokens": args.max_tokens} if args.max_tokens is not None else {}
        result = store.query(
            query_type=args.query_type,
            symbol=args.symbol,
            horizon=args.horizon,
            scenario=args.scenario,
            packet_id=args.packet_id,
            limit=args.limit,
            **kwargs,
        )
    print(result.model_dump_json(exclude_none=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
