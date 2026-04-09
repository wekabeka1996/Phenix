import pandas as pd
import numpy as np
from scipy.stats import spearmanr, pearsonr

trades_df = pd.read_csv(r"C:\Users\user\Music\Phenix\scratch\stage3_trades.csv")
profiles_df = pd.read_csv(r"C:\Users\user\Music\Phenix\scratch\stage3_profiles.csv")

# 1. EXIT OUTCOME MATRIX
print("=== EXIT OUTCOMES ===")
def exit_stats(df_t):
    if len(df_t) == 0: return {}
    outcomes = df_t['exit_reason'].value_counts().to_dict()
    total = len(df_t)
    ks = outcomes.get('EDGE_GONE_KILLSWITCH', 0)
    sc = outcomes.get('FEE_AWARE_SCALEOUT', 0)
    zt = outcomes.get('ZOMBIE_POSITION_TIMEOUT', 0)
    return {"Total": total, "Killswitch%": round(ks/total*100,1), "Scaleout%": round(sc/total*100,1), "Zombie%": round(zt/total*100,1)}

print("All Trades:", exit_stats(trades_df))
print("Gross Replay:", exit_stats(trades_df[trades_df['mode'] == 'gross']))
print("Net Replay:", exit_stats(trades_df[trades_df['mode'] == 'net_config']))

print("\nLong vs Short (Net):")
print("Long:", exit_stats(trades_df[(trades_df['mode'] == 'net_config') & (trades_df['side'] == 'LONG')]))
print("Short:", exit_stats(trades_df[(trades_df['mode'] == 'net_config') & (trades_df['side'] == 'SHORT')]))

# Sample case studies (Killswitch before target)
print("\n=== TOP 5 LONG KILLSWITCH CASES ===")
longs = trades_df[(trades_df['mode'] == 'gross') & (trades_df['side'] == 'LONG') & (trades_df['exit_reason'] == 'EDGE_GONE_KILLSWITCH')]
print(longs[['entry_ts', 'exit_ts', 'holding_bars', 'pnl_pct', 'regime_at_entry']].head(5))
print("\n=== TOP 5 SHORT KILLSWITCH CASES ===")
shorts = trades_df[(trades_df['mode'] == 'gross') & (trades_df['side'] == 'SHORT') & (trades_df['exit_reason'] == 'EDGE_GONE_KILLSWITCH')]
print(shorts[['entry_ts', 'exit_ts', 'holding_bars', 'pnl_pct', 'regime_at_entry']].head(5))

# 2. VOLATILITY DAMPENING
print("\n=== DAMPENING ANALYSIS ===")
net_prof = profiles_df[profiles_df['mode'] == 'net_config']
nodamp_prof = profiles_df[profiles_df['mode'] == 'net_no_dampening']

high_vol = net_prof[net_prof['atr_zscore'] > 2.20].copy()
if not high_vol.empty:
    high_vol_nodamp = nodamp_prof[nodamp_prof['ts'].isin(high_vol['ts'])]
    
    # Merge on symbol + ts
    merged_vol = pd.merge(high_vol, high_vol_nodamp, on=['symbol', 'ts'], suffixes=('_damp', '_nodamp'))
    
    # Cases where they differ
    diff = merged_vol[merged_vol['dir_score_damp'] != merged_vol['dir_score_nodamp']]
    print(f"High Volatility Bars (> 2.2 zscore): {len(high_vol)}")
    print(f"Bars where dampening shifted dir_score: {len(diff)}")
    
    # How often did dampening switch the dominant side?
    switched = diff[(diff['dir_score_damp'] * diff['dir_score_nodamp'] < 0)]
    print(f"Bars where dampening inverted the bias sign: {len(switched)}")
    
    # Let's inspect D1 weight drop
    avg_d1_damp = diff['w_norm_d1_damp'].mean()
    avg_d1_nodamp = diff['w_norm_d1_nodamp'].mean()
    print(f"Average D1 w_norm WITHOUT dampening: {avg_d1_nodamp:.3f}")
    print(f"Average D1 w_norm WITH dampening: {avg_d1_damp:.3f}")

# 3. PSEUDO-MTF
print("\n=== PSEUDO-MTF FRAGILITY ===")
mtf_df = net_prof.dropna(subset=['boundary_lookback_val'])
if not mtf_df.empty:
    # Look for instances where dir_comp_d1 is extreme (>0.9 or <-0.9)
    # but the overall SMA96 slope is very small (flat structural trend)
    extreme_d1 = mtf_df[mtf_df['dir_comp_d1'].abs() > 0.9]
    print(f"Bars with extreme pseudo D1 score (>0.9): {len(extreme_d1)}")
    
    # Structural flat
    flat_slope = extreme_d1[extreme_d1['sma_slope_96'].abs() < extreme_d1['sma_96'] * 0.0005] # flat slope is < 5 bps change per bar
    print(f"Of those, bars where structural true trend (SMA_Slope) is FLAT: {len(flat_slope)}")

# 4. CONFIDENCE ANALYSIS
print("\n=== CONFIDENCE ===")
val_profs = net_prof[net_prof['conf_ratio'] > 0]
if not val_profs.empty:
    p_corr, _ = pearsonr(val_profs['score'].abs(), val_profs['conf_ratio'])
    s_corr, _ = spearmanr(val_profs['score'].abs(), val_profs['conf_ratio'])
    print(f"Pearson Correlation (abs(score) vs conf_ratio): {p_corr:.4f}")
    print(f"Spearman Correlation (abs(score) vs conf_ratio): {s_corr:.4f}")
    
    val_profs['score_bucket'] = pd.qcut(val_profs['score'].abs(), q=5, duplicates='drop')
    print("Average conf_ratio by |score| bucket:")
    print(val_profs.groupby('score_bucket')['conf_ratio'].mean())

# 5. CHOP EXPLOSION
print("\n=== FLAT CHOP ===")
# Find situations with tiny band compared to price. (e.g. band <= 3 bps of price)
chop = net_prof[(net_prof['band'] / net_prof['close']) < 0.0003]
print(f"Bars with extreme narrow channel (<3bps): {len(chop)}")
chop_extreme_score = chop[chop['score'].abs() > 0.9]
print(f"Of those, bars registering MAX SCORE (>0.9): {len(chop_extreme_score)}")
