"""
Cross-Asset Pipeline Orchestrator

Runs ETL -> Features -> Optuna for all target symbols.
"""

import subprocess
import sys
import time

TARGET_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"]
YEAR = "2024"
MONTH = "01" # Using Jan 2024 as baseline

def run_command(cmd):
    print(f"Running: {cmd}")
    try:
        subprocess.check_call(cmd, shell=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        # Decide whether to continue or stop. For batch, maybe continue?
        # But if ETL fails, Features will fail.
        raise e

def main():
    start_time = time.time()
    
    for symbol in TARGET_SYMBOLS:
        print(f"\n{'='*60}")
        print(f"PROCESSING {symbol} ({YEAR}-{MONTH})")
        print(f"{'='*60}")
        
        try:
            # 1. ETL (Golden 1s)
            print(f"Step 1: ETL...")
            run_command(f"python3 apps/research/momentum_backtest/etl.py --symbol {symbol} --year {YEAR} --month {MONTH}")
            
            # 2. RESAMPLE (1s → 5s, 10s)
            print(f"Step 2: Resampling...")
            run_command(f"python3 apps/research/momentum_backtest/resample_bars.py --symbol {symbol} --year {YEAR} --month {MONTH}")
            
            # 3. Features (5s + Regimes)
            print(f"Step 3: Features...")
            run_command(f"python3 apps/research/momentum_backtest/features_builder_multiscale.py --symbol {symbol} --year {YEAR} --month {MONTH}")
            
            # 4. Optuna (Regime Optimization)
            print(f"Step 4: Optuna ({N_TRIALS} trials)...")
            run_command(f"python3 apps/research/momentum_backtest/optuna_runner_regime.py --symbol {symbol} --year {YEAR} --month {MONTH} --n-trials {N_TRIALS}")
            
        except Exception as e:
            print(f"FAILED processing {symbol}: {e}")
            continue
            
    elapsed = time.time() - start_time
    print(f"\nALL DONE in {elapsed/60:.2f} minutes.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Cross-Asset Pipeline Orchestrator")
    parser.add_argument("--n-trials", type=int, default=50, help="Number of trials for Optuna optimization.")
    args = parser.parse_args()
    
    N_TRIALS = args.n_trials
    
    main()
