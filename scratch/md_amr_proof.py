from decimal import Decimal
import math

def _clamp(v, lo, hi): 
    return max(lo, min(hi, v))

print('================================================================================')
print('PROOF 1: KILLSWITCH VS SCALEOUT CONFLICT (LONG POSITION)')
print('================================================================================')
avg_high = 100.0
avg_close = 95.0
avg_low = 90.0
band = avg_high - avg_low # 10.0
hysteresis_mult = 1.0
thr_buy = 0.20
conf_min = 0.1

print(f"Setup: avg_low={avg_low}, avg_close (TARGET)={avg_close}, thr_buy={thr_buy}, conf_min={conf_min}")
for close_now in [85.0, 87.0, 89.0, 89.5, 90.0, 92.0, 95.0]:
    long_score = max(0.0, (avg_low - close_now) / band) * hysteresis_mult
    short_score = max(0.0, (close_now - avg_high) / band) * hysteresis_mult
    score = _clamp(long_score - short_score, -1.0, 1.0)
    conf_ratio = _clamp(max(0.0, score) / max(thr_buy, 1e-6), 0.0, 1.0)
    edge_gone = conf_ratio < conf_min
    reached_target = close_now >= avg_close
    print(f'Price: {close_now:<4.1f} | score: {score:<5.3f} | conf_ratio: {conf_ratio:<5.3f} | EDGE_GONE (Killswitch): {str(edge_gone):<5} | TARGET_REACHED: {str(reached_target)}')


print('\n================================================================================')
print('PROOF 2: VOLATILITY DAMPENING PARADOX')
print('================================================================================')
weights_raw = {'d1': 0.25, 'h1': 0.25, 'm30': 0.25, 'm15': 0.25}
volatility_dampening_factor = 0.1 # Example drop
dir_components = {'d1': 1.0, 'h1': 1.0, 'm30': -1.0, 'm15': -1.0}

print("Scenario: HTF is deeply LONG (+1.0), but LTF is crashing SHORT (-1.0).")

# Normal
w_norm_normal = {k: v / sum(weights_raw.values()) for k, v in weights_raw.items()}
dir_score_normal = sum(dir_components[k] * w_norm_normal[k] for k in dir_components)
print(f"NORMAL VOLATILITY:")
print(f"  Weights: d1/h1={w_norm_normal['d1']:.2f}, m30/m15={w_norm_normal['m15']:.2f}")
print(f"  Resulting dir_score: {dir_score_normal:.3f} (Neutral/Flat)")

# High Vol
w_high_vol = dict(weights_raw)
w_high_vol['d1'] *= volatility_dampening_factor
w_high_vol['h1'] *= volatility_dampening_factor
total = sum(w_high_vol.values())
w_norm_high_vol = {k: v / total for k, v in w_high_vol.items()}
dir_score_high_vol = sum(dir_components[k] * w_norm_high_vol[k] for k in dir_components)
print(f"\nHIGH VOLATILITY (atr_zscore > threshold_z):")
print(f"  Weights: d1/h1 dampens to {w_norm_high_vol['d1']:.3f}, m30/m15 spikes to {w_norm_high_vol['m15']:.3f}")
print(f"  Resulting dir_score: {dir_score_high_vol:.3f} (Aggressively SHORT)")


print('\n================================================================================')
print('PROOF 3: PSEUDO-MTF LOOKBACKS')
print('================================================================================')
# Simulate arrays for 96 bars
closes_flat = [100.0] * 95 # 95 bars at 100
closes_flat.append(100.0)
curr_close_flat = closes_flat[-1]
calc_d1_flat = (curr_close_flat - closes_flat[-1 - 95]) / max(abs(closes_flat[-1 - 95]), 1e-9)
print(f"Flat 96 bars: d1 component = {math.tanh(calc_d1_flat * 6.0):.3f}")

closes_spike = [100.0] * 95
closes_spike[0] = 50.0  # Bar 96 periods ago was 50 (a giant spike afterwards, then flat for 95 bars)
curr_close_spike = closes_spike[-1]
calc_d1_spike = (curr_close_spike - closes_spike[-1 - 95]) / max(abs(closes_spike[-1 - 95]), 1e-9)
print(f"Bar -96 = 50, inside 95 bars = 100: d1 component = {math.tanh(calc_d1_spike * 6.0):.3f}")
print("Conclusion: D1 component is heavily skewed by a single bar 96 periods ago, completely ignoring the 95 flat bars in between.")
