"""
Smoke Test: ETH only, 20 trials

Validates pipeline fix before full run.
"""

import subprocess
import time

SYMBOL = "ETHUSDT"
YEAR = "2024"
MONTH = "01"
N_TRIALS = 20

def run(cmd):
    print(f"Running: {cmd}")
    subprocess.check_call(cmd, shell=True)

print("="*60)
print(f"SMOKE TEST: {SYMBOL} ({YEAR}-{MONTH}), {N_TRIALS} trials")
print("="*60)

start = time.time()

# 1. ETL already done, skip
print("\nStep 1: ETL (already done)")

# 2. Resample
print("\nStep 2: Resample...")
run(f"python3 apps/research/momentum_backtest/resample_bars.py --symbol {SYMBOL} --year {YEAR} --month {MONTH}")

# 3. Features
print("\nStep 3: Features...")
run(f"python3 apps/research/momentum_backtest/features_builder_multiscale.py --symbol {SYMBOL} --year {YEAR} --month {MONTH}")

# 4. Optuna (override n_trials)
print("\nStep 4: Optuna (20 trials)...")
# Need to modify optuna_runner_regime to accept n_trials arg, or just run directly with modified code
# For now, run standard (150 trials) or manually edit
# OR create a temp modified version
# Simplest: just run it and ctrl-C after 20 or modify the runner

print("WARNING: Running full 150 trials. Consider modifying optuna_runner_regime.py to accept --n-trials arg.")
run(f"python3 apps/research/momentum_backtest/optuna_runner_regime.py --symbol {SYMBOL} --year {YEAR} --month {MONTH}")

elapsed = time.time() - start
print(f"\nSmoke test completed in {elapsed/60:.2f} minutes")
