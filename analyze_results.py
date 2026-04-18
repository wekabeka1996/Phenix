#!/usr/bin/env python3
import pandas as pd

csv_path = 'logs/alpha_search_runtime/20260417_004222/aggregate/aggregate_metrics.csv'
print('=== ALPHA SEARCH RUN RESULTS ===\n')

df = pd.read_csv(csv_path)
print(f'Total snapshots: {len(df):,}')
print(f'Symbols: {sorted(df["symbol"].unique().tolist())}')
print()

print('=== Per-Scenario Summary ===')
for scenario in sorted(df['scenario_id'].unique()):
    subset = df[df['scenario_id'] == scenario]
    long_count = (subset['side'] == 'LONG').sum()
    short_count = (subset['side'] == 'SHORT').sum()
    neutral_count = (subset['side'] == 'NEUTRAL').sum()
    avg_conf = subset['confidence'].astype(float).mean()
    avg_score = subset['score'].astype(float).mean()

    print(f'{scenario:30} | L={long_count:5d} S={short_count:5d} N={neutral_count:5d} | Conf={avg_conf:.3f} Score={avg_score:.3f}')

print()
print('=== Top Signals (by confidence) ===')
top_signals = df.nlargest(10, 'confidence')[['scenario_id', 'symbol', 'side', 'confidence', 'score', 'regime']]
print(top_signals.to_string(index=False))
