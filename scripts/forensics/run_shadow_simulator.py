import argparse
import json
import logging
import sys
from pathlib import Path
from typing import List

import pandas as pd
import yaml

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from apps.reference.domains.alpha_search.judge.config_models import ShadowSimulatorConfig
from apps.reference.domains.alpha_search.judge.shadow_simulator import ShadowPlanSimulator
from apps.reference.domains.alpha_search.judge.simulation_models import ShadowSimulationResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)-8s | %(message)s")
LOG = logging.getLogger(__name__)

def load_config() -> ShadowSimulatorConfig:
    config_path = PROJECT_ROOT / "config" / "alpha_search.yaml"
    if not config_path.exists():
        LOG.warning(f"Config not found at {config_path}, using defaults")
        return ShadowSimulatorConfig(enabled=True)
        
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        
    judge_config = data.get("alpha_search", {}).get("judge", {})
    sim_data = judge_config.get("simulator", {})
    
    # Check for the user's preferred key if different
    if not sim_data:
        sim_data = judge_config.get("shadow_plan_simulator", {})
        
    return ShadowSimulatorConfig.model_validate(sim_data)

def main():
    parser = argparse.ArgumentParser(description="Shadow Plan Fill Simulator CLI")
    parser.add_argument("--max-bars", type=int, help="Override max_bars_after_signal")
    parser.add_argument("--output", type=str, help="Output JSONL filename")
    args = parser.parse_args()
    
    config = load_config()
    if args.max_bars:
        # Pydantic models are frozen, but we can update a dict and re-validate
        sim_data = config.model_dump()
        sim_data["max_bars_after_signal"] = args.max_bars
        config = ShadowSimulatorConfig.model_validate(sim_data)
        
    simulator = ShadowPlanSimulator(config)
    
    log_dir = PROJECT_ROOT / "logs" / "judge_experts"
    data_dir = PROJECT_ROOT / "data" / "recorder"
    
    plan_files = list(log_dir.glob("shadow_entry_plan_*.jsonl"))
    
    if not plan_files:
        LOG.error(f"No shadow entry plans found in {log_dir}")
        return

    all_results: List[ShadowSimulationResult] = []
    
    for plan_file in plan_files:
        LOG.info(f"Simulating plans in {plan_file.name} (max_bars={config.max_bars_after_signal})...")
        results = simulator.run_batch(plan_file, data_dir)
        all_results.extend(results)
        
    if not all_results:
        LOG.warning("No actionable plans simulated.")
        return

    # Aggregate Statistics
    df = pd.DataFrame([r.model_dump() for r in all_results])
    
    summary = df.groupby(["confidence_tier", "outcome"]).size().unstack(fill_value=0)
    
    print("\n" + "="*80)
    print("SHADOW PLAN SIMULATION SUMMARY")
    print("="*80)
    print(summary)
    
    # Calculate PnL by tier
    pnl_summary = df[df["outcome"].isin(["FILLED_TP", "FILLED_SL", "FILLED_TIMEOUT"])].groupby("confidence_tier")["net_pnl_pct"].agg(["count", "sum", "mean"]).rename(columns={"sum": "total_pnl_pct", "mean": "avg_pnl_pct"})
    
    print("\nPROFITABILITY BY TIER (Actionable Only)")
    print(pnl_summary)
    
    # Save all results
    output_filename = args.output if args.output else "shadow_simulation_results.jsonl"
    results_path = log_dir / output_filename
    with open(results_path, "w") as f:
        for res in all_results:
            f.write(json.dumps(res.model_dump()) + "\n")
    
    LOG.info(f"Detailed results saved to {results_path}")

if __name__ == "__main__":
    main()
