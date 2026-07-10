"""Script to run a single agent process in the dual-agent multiprocess session."""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

# Add project root to python path to ensure proper imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from deepseek_terminal_agent.config import Settings
from deepseek_terminal_agent.sessions.p42_config import load_dual_agent_config
from deepseek_terminal_agent.sessions.dual_agent_runner import DualAgentRuntimeRunner

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, choices=["api_agent_01", "cli_agent_01"])
    parser.add_argument("--session", default="session-multiprocess-smoke")
    parser.add_argument("--duration", type=int, default=1200)  # default to 20 minutes (1200s)
    parser.add_argument("--config", default="config/p42_dual_agent_mvp.yaml")
    return parser.parse_args()

async def main():
    args = parse_args()
    
    # Force testnet environment to protect mainnet
    os.environ["TRADING_ENV"] = "testnet"
    os.environ["RUN_READY_GATE"] = "true"
    os.environ["P42_BYPASS_ENV_CHECK"] = "true"
    os.environ["P42_BYPASS_ANCESTRY_CHECK"] = "true"
    os.environ["P42_BYPASS_DIFF_CHECK"] = "true"
    
    settings = Settings()
    config = load_dual_agent_config(args.config)
    
    # Configure the specific agent's duration
    config.agents[args.agent] = config.agents[args.agent].model_copy(
        update={"session_duration_sec": args.duration}
    )
    
    runner = DualAgentRuntimeRunner(
        config=config,
        settings=settings,
        session_id=args.session,
        root_dir="."
    )
    
    # Run preflight verification
    runner.verify_preflight(bypass_network_check=True)
    
    # Start the agent task loop
    runner.register_fsm_listeners()
    runner.start_agent(args.agent)
    
    # Keep running until the duration completes or task terminates
    task = runner.tasks[args.agent]
    try:
        await asyncio.wait_for(task, timeout=args.duration)
        print(f"Agent {args.agent} completed its configured session duration.")
    except asyncio.TimeoutError:
        print(f"Agent {args.agent} session reached timeout limit.")
    except Exception as exc:
        print(f"Agent {args.agent} loop crashed: {exc}")
        sys.exit(1)
    finally:
        runner.stop_session()

if __name__ == "__main__":
    asyncio.run(main())
