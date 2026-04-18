import pandas as pd
import numpy as np

# Read the CSV
df = pd.read_csv(
    "logs/alpha_search_runtime/20260417_004222/aggregate/aggregate_metrics.csv")

print("=" * 100)
print("CSV COLUMNS AND TYPES")
print("=" * 100)
print("\nAll columns:")
for col in df.columns:
    print(f"  {col}: {df[col].dtype}")

print("\n\n" + "=" * 100)
print("SAMPLE DATA (First 5 rows)")
print("=" * 100)
print(df.head(5).to_string())

print("\n\n" + "=" * 100)
print("PnL AND PROFITABILITY ANALYSIS BY SCENARIO")
print("=" * 100)

# Try to find PnL-related columns
pnl_cols = [col for col in df.columns if 'pnl' in col.lower(
) or 'profit' in col.lower() or 'loss' in col.lower()]
print(f"\nPnL-related columns found: {pnl_cols}")

# Get unique scenarios
scenarios = sorted(df['scenario_id'].unique())

for scenario in scenarios:
    s_data = df[df['scenario_id'] == scenario]

    print(f"\n{'='*80}")
    print(f"📊 {scenario}")
    print(f"{'='*80}")

    # Signal statistics
    signals = s_data[s_data['side'] != 'NEUTRAL']
    if len(signals) > 0:
        long_signals = len(s_data[s_data['side'] == 'LONG'])
        short_signals = len(s_data[s_data['side'] == 'SHORT'])
        total_signals = long_signals + short_signals
        win_rate = (total_signals / len(s_data) *
                    100) if len(s_data) > 0 else 0

        print(f"\nSignal Statistics:")
        print(
            f"  Total Signals (L/S): {long_signals}/{short_signals} = {total_signals}")
        print(
            f"  Win Rate: {win_rate:.2f}% of snapshots had actionable signals")
    else:
        print(f"\nSignal Statistics:")
        print(f"  Total Signals: 0 (all NEUTRAL)")
        print(f"  Win Rate: 0.00%")

    # Confidence stats for signals
    if len(signals) > 0:
        print(f"\nConfidence (for signals only):")
        print(f"  Mean: {signals['confidence'].mean():.4f}")
        print(f"  Median: {signals['confidence'].median():.4f}")
        print(f"  Min: {signals['confidence'].min():.4f}")
        print(f"  Max: {signals['confidence'].max():.4f}")

    # Check for PnL columns
    if pnl_cols:
        for pnl_col in pnl_cols:
            col_data = pd.to_numeric(s_data[pnl_col], errors='coerce')
            if col_data.notna().any():
                print(f"\n{pnl_col}:")
                print(f"  Total: {col_data.sum():.6f}")
                print(f"  Mean: {col_data.mean():.6f}")
                print(f"  Min: {col_data.min():.6f}")
                print(f"  Max: {col_data.max():.6f}")
    else:
        print(f"\n⚠️  No PnL columns found in CSV")

print(f"\n{'='*100}\n")
