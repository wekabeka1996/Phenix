from apps.reference.domains.execution_position.utils import calc_tp_sl_from_mark

cases = [
    ({'markPrice': '114000.0'}, 'LONG', 100, 50, 0.1),
    (114000.0, 'SHORT', '200', '100', 0.1),
]

for c in cases:
    mark, side, tp_bps, sl_bps, tick = c
    tp, sl = calc_tp_sl_from_mark(mark, side, tp_bps, sl_bps, tick_size=tick)
    print(side, '->', 'tp=', tp, 'sl=', sl)
