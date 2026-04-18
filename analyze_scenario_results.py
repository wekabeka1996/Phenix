import pandas as pd
import json

# Read the CSV
df = pd.read_csv(
    "logs/alpha_search_runtime/20260417_004222/aggregate/aggregate_metrics.csv")

print("=" * 100)
print("ALPHA SEARCH RESULTS BY SCENARIO")
print("=" * 100)
print(f"\nTotal snapshots processed: {len(df):,}")
print(f"Available columns: {list(df.columns)}\n")

# Get unique scenarios
scenarios = sorted(df['scenario_id'].unique())

for scenario in scenarios:
    s_data = df[df['scenario_id'] == scenario]

    print(f"\n{'='*80}")
    print(f"📊 {scenario}")
    print(f"{'='*80}")
    print(f"Total snapshots: {len(s_data):,}")

    # Signal distribution
    if 'side' in df.columns:
        signal_dist = s_data['side'].value_counts()
        print(f"\nSignal Distribution:")
        for side in ['LONG', 'SHORT', 'NEUTRAL']:
            count = signal_dist.get(side, 0)
            pct = (count / len(s_data) * 100) if len(s_data) > 0 else 0
            print(f"  {side:10s}: {count:6,} ({pct:5.1f}%)")

    # Confidence metrics
    if 'confidence' in df.columns:
        conf = pd.to_numeric(
            df[df['scenario_id'] == scenario]['confidence'], errors='coerce')
        print(f"\nConfidence Levels:")
        print(f"  Mean:      {conf.mean():.4f}")
        print(f"  Median:    {conf.median():.4f}")
        print(f"  Min:       {conf.min():.4f}")
        print(f"  Max:       {conf.max():.4f}")
        print(f"  Std Dev:   {conf.std():.4f}")

    # Score metrics
    if 'score' in df.columns:
        score = pd.to_numeric(
            df[df['scenario_id'] == scenario]['score'], errors='coerce')
        print(f"\nScore Distribution:")
        print(f"  Mean:      {score.mean():.6f}")
        print(f"  Median:    {score.median():.6f}")
        print(f"  Min:       {score.min():.6f}")
        print(f"  Max:       {score.max():.6f}")

    # Regime distribution
    if 'regime' in df.columns:
        regimes = s_data['regime'].value_counts()
        print(f"\nRegime Distribution:")
        for regime in sorted(regimes.index):
            count = regimes[regime]
            pct = (count / len(s_data) * 100)
            print(f"  {regime:20s}: {count:6,} ({pct:5.1f}%)")

    # Symbol distribution
    if 'symbol' in df.columns:
        symbols = s_data['symbol'].value_counts()
        print(f"\nSymbol Coverage:")
        for symbol in sorted(symbols.index):
            count = symbols[symbol]
            print(f"  {symbol:12s}: {count:6,}")

print(f"\n{'='*100}\n")
