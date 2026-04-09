from decimal import Decimal

def _clamp(v, lo, hi): 
    return max(lo, min(hi, v))

avg_high = 100.0
avg_close = 95.0
avg_low = 90.0
band = 10.0
hysteresis_mult = 1.0
thr_sell = 0.20
conf_min = 0.1

print('--- PROOF 1: SHORT SYMMETRY ---')
# Short position. We entered when max(0, (close_now - avg_high)/band) was high. We shorted at e.g. 105.0. Target is avg_close (95.0).
for close_now in [105.0, 103.0, 101.0, 100.5, 100.0, 98.0, 95.0]:
    long_score = max(0.0, (avg_low - close_now) / band) * hysteresis_mult
    short_score = max(0.0, (close_now - avg_high) / band) * hysteresis_mult
    score = _clamp(long_score - short_score, -1.0, 1.0)
    conf_ratio = _clamp(max(0.0, -score) / max(thr_sell, 1e-6), 0.0, 1.0)
    edge_gone = conf_ratio < conf_min
    reached_target = close_now <= avg_close
    print(f'Price: {close_now:<4.1f} | score: {score:<6.3f} | conf_ratio: {conf_ratio:<5.3f} | EDGE_GONE: {str(edge_gone):<5} | TARGET_REACHED: {str(reached_target)}')
