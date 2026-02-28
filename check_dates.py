import polars as pl
df1 = pl.read_parquet('data/processed/BTCUSDT/5m/2023-06_enriched.parquet')
df2 = pl.read_parquet('data/processed/BTCUSDT/5m/2024-03_enriched.parquet')
print(f"Start: {df1['open_time'].min()}")
print(f"End: {df2['open_time'].max()}")
