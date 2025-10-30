from apps.reference.domains.execution_position.utils import (
    calc_tp_sl_from_mark,
    validate_not_immediate,
)

m = {"markPrice": "114000.0"}
tp, sl = calc_tp_sl_from_mark(m, "LONG", 100, 50, tick_size=0.1)
assert validate_not_immediate("LONG", tp, sl, m) == 114000.0

tp, sl = calc_tp_sl_from_mark(m, "SHORT", 100, 50, tick_size=0.1)
assert validate_not_immediate("SHORT", tp, sl, m) == 114000.0

print("All tests passed!")
