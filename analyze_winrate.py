import pandas as pd
import numpy as np
from collections import defaultdict

# Read the CSV
df = pd.read_csv(
    "logs/alpha_search_runtime/20260417_004222/aggregate/aggregate_metrics.csv")

print("=" * 100)
print("ALPHA SEARCH WIN RATE & SIGNAL ANALYSIS")
print("=" * 100)
print("\n⚠️  NOTE: CSV contains SIGNAL GENERATION only (no actual PnL)")
print("    PnL would be calculated by decision_making/execution_position domains")
print("    analyzing wins/losses from actual trade fills\n")

print("=" * 100)
print("WIN RATE BY SCENARIO (% of actionable signals)")
print("=" * 100)

scenarios = sorted(df['scenario_id'].unique())
results = []

for scenario in scenarios:
    s_data = df[df['scenario_id'] == scenario]

    total_rows = len(s_data)
    neutral = len(s_data[s_data['side'] == 'NEUTRAL'])
    long = len(s_data[s_data['side'] == 'LONG'])
    short = len(s_data[s_data['side'] == 'SHORT'])
    actionable = long + short

    win_rate = (actionable / total_rows * 100) if total_rows > 0 else 0

    results.append({
        'Scenario': scenario,
        'Total': total_rows,
        'LONG': long,
        'SHORT': short,
        'Actionable': actionable,
        'Win_Rate_%': win_rate,
        'NEUTRAL_%': (neutral/total_rows*100) if total_rows > 0 else 0
    })

    print(f"\n{scenario}:")
    print(f"  Total Signals:     {total_rows:>6,}")
    print(f"  Actionable (L+S):  {actionable:>6,} ({win_rate:>5.2f}%)")
    print(f"    - LONG:          {long:>6,}")
    print(f"    - SHORT:         {short:>6,}")
    print(
        f"  NEUTRAL:           {neutral:>6,} ({neutral/total_rows*100:>5.2f}%)")

results_df = pd.DataFrame(results)

print(f"\n{'='*100}")
print("SUMMARY TABLE")
print(f"{'='*100}\n")
print(results_df.to_string(index=False))

print(f"\n{'='*100}")
print("STATISTICS")
print(f"{'='*100}")
print(
    f"Average Win Rate across all scenarios: {results_df['Win_Rate_%'].mean():.4f}%")
print(
    f"Max Win Rate: {results_df['Win_Rate_%'].max():.4f}% ({results_df.loc[results_df['Win_Rate_%'].idxmax(), 'Scenario']})")
print(
    f"Min Win Rate: {results_df['Win_Rate_%'].min():.4f}% ({results_df.loc[results_df['Win_Rate_%'].idxmin(), 'Scenario']})")

print(f"\n{'='*100}")
print("TOP SIGNALS BY CONFIDENCE")
print(f"{'='*100}\n")

# Find top signals (LONG/SHORT with highest confidence)
signals_df = df[df['side'].isin(['LONG', 'SHORT'])].copy()
if len(signals_df) > 0:
    top_signals = signals_df.nlargest(20, 'confidence')[
        ['scenario_id', 'symbol', 'side', 'confidence', 'score', 'regime', 'provider_id']]
    print(top_signals.to_string(index=False))
else:
    print("No actionable signals (LONG/SHORT) found in dataset")

print(f"\n{'='*100}")
print("CONFIDENCE ANALYSIS (for NEUTRAL signals)")
print(f"{'='*100}\n")

neutral_df = df[df['side'] == 'NEUTRAL'].copy()
if len(neutral_df) > 0:
    print(f"NEUTRAL signals with HIGH confidence (>0.8):")
    high_conf_neutral = neutral_df[neutral_df['confidence'] > 0.8]
    if len(high_conf_neutral) > 0:
        print(
            f"  Count: {len(high_conf_neutral):,} ({len(high_conf_neutral)/len(neutral_df)*100:.2f}% of NEUTRAL)")
        print(f"\n  Top 10 by confidence:")
        top = high_conf_neutral.nlargest(10, 'confidence')[
            ['scenario_id', 'symbol', 'confidence', 'score', 'regime']]
        print(top.to_string(index=False))
    else:
        print(f"  None found (high confidence threshold: >0.8)")

print(f"\n{'='*100}\n")
