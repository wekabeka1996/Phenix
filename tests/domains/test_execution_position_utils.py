import pytest
from apps.reference.domains.execution_position import utils
from decimal import Decimal


def test_rounding_quantize_stop_price_buy_sell():
    # BUY should ceil, SELL should floor
    assert utils.quantize_stop_price(100.1234, 0.01, side="BUY") >= 100.12
    assert utils.quantize_stop_price(100.1299, 0.01, side="SELL") <= 100.12


def test_validate_anti_2021_adjusts_and_quantizes():
    # SELL STOP must be < trigger
    sp, adjusted, reason = utils.validate_anti_2021("SELL", "STOP", 10.0, 10.0, 0.01)
    assert adjusted
    assert "sell STOP" in reason or "nudge" in reason

    # BUY TP must be < trigger for TAKE_PROFIT on SHORT
    sp2, adjusted2, reason2 = utils.validate_anti_2021("BUY", "TAKE_PROFIT", 5.0, 5.0, 0.01)
    assert adjusted2


def test_generate_client_order_id_and_allowed_chars():
    cid = utils.generate_client_order_id("PR", "DEC123", "extra", max_len=20)
    assert isinstance(cid, str)
    assert len(cid) <= 20
    # only allowed chars
    import re
    assert re.match(r"^[A-Za-z0-9_\-]+$", cid)


def test_to_float_and_calc_tp_sl_and_validate_not_immediate():
    mark = {"markPrice": "100"}
    tp, sl = utils.calc_tp_sl_from_mark(mark, "LONG", 100, 50)
    assert tp > sl

    # With tick_size rounding
    tp2, sl2 = utils.calc_tp_sl_from_mark(Decimal("100"), "SHORT", "50", "25", tick_size=0.1)
    assert isinstance(tp2, float) and isinstance(sl2, float)

    # validate_not_immediate should return mark for valid pairs
    m = utils.validate_not_immediate("LONG", tp, sl, mark)
    assert isinstance(m, float)


def test_to_float_errors():
    with pytest.raises(ValueError):
        utils._to_float(None)

    with pytest.raises(TypeError):
        utils._to_float(object())


def test_opposite_side():
    assert utils.opposite_side("BUY") == "SELL"
    assert utils.opposite_side("SELL") == "BUY"
import pytest
from decimal import Decimal
from apps.reference.domains.execution_position.utils import _to_float, calc_tp_sl_from_mark, validate_not_immediate


class TestToFloat:
    def test_float(self):
        assert _to_float(123.45) == 123.45

    def test_int(self):
        assert _to_float(42) == 42.0

    def test_decimal(self):
        assert _to_float(Decimal('1.23')) == 1.23

    def test_str(self):
        assert _to_float('456.78') == 456.78

    def test_dict_mark_price(self):
        assert _to_float({'markPrice': '100.0'}) == 100.0

    def test_dict_price(self):
        assert _to_float({'price': '200.5'}) == 200.5

    def test_dict_last(self):
        assert _to_float({'last': '300.0'}) == 300.0

    def test_dict_last_price(self):
        assert _to_float({'lastPrice': '400.0'}) == 400.0

    def test_dict_index_price(self):
        assert _to_float({'indexPrice': '500.0'}) == 500.0

    def test_none_raises(self):
        with pytest.raises(ValueError, match="value is None"):
            _to_float(None)

    def test_invalid_type_raises(self):
        with pytest.raises(TypeError, match="Expected number-like"):
            _to_float([1, 2, 3])


class TestCalcTpSlFromMark:
    def test_long_basic(self):
        tp, sl = calc_tp_sl_from_mark(100.0, 'LONG', 100, 50)
        assert tp == 101.0  # 100 * (1 + 100/10000)
        assert sl == 99.5   # 100 * (1 - 50/10000)

    def test_short_basic(self):
        tp, sl = calc_tp_sl_from_mark(100.0, 'SHORT', 100, 50)
        assert tp == pytest.approx(99.0)   # 100 * (1 - 100/10000)
        assert sl == pytest.approx(100.5)  # 100 * (1 + 50/10000)

    def test_long_with_tick_quantization(self):
        tp, sl = calc_tp_sl_from_mark(100.0, 'LONG', 100, 50, tick_size=0.1)
        # TP ceil to 0.1: 101.0 -> 101.0
        # SL floor to 0.1: 99.5 -> 99.5
        assert tp == 101.0
        assert sl == 99.5

    def test_short_with_tick_quantization(self):
        tp, sl = calc_tp_sl_from_mark(100.0, 'SHORT', 100, 50, tick_size=0.1)
        # TP floor to 0.1: 99.0 -> 99.0
        # SL ceil to 0.1: 100.5 -> 100.5
        assert tp == 99.0
        assert sl == 100.5

    def test_long_anti_2021_passes(self):
        tp, sl = calc_tp_sl_from_mark(100.0, 'LONG', 100, 50)
        assert sl < 100.0 < tp

    def test_short_anti_2021_passes(self):
        tp, sl = calc_tp_sl_from_mark(100.0, 'SHORT', 100, 50)
        assert sl > 100.0 > tp

    def test_long_anti_2021_fails(self):
        with pytest.raises(ValueError, match="anti-2021.*failed"):
            calc_tp_sl_from_mark(100.0, 'LONG', -1, 50)  # tp < mark

    def test_short_anti_2021_fails(self):
        with pytest.raises(ValueError, match="anti-2021.*failed"):
            calc_tp_sl_from_mark(100.0, 'SHORT', -1, 50)  # tp > mark

    def test_mark_as_dict(self):
        tp, sl = calc_tp_sl_from_mark({'markPrice': '100.0'}, 'LONG', 100, 50)
        assert tp == 101.0
        assert sl == 99.5

    def test_bps_as_str(self):
        tp, sl = calc_tp_sl_from_mark(100.0, 'LONG', '100', '50')
        assert tp == 101.0
        assert sl == 99.5

    def test_invalid_side(self):
        with pytest.raises(ValueError, match="Side must be"):
            calc_tp_sl_from_mark(100.0, 'INVALID', 100, 50)


class TestValidateNotImmediate:
    def test_long_valid(self):
        mark = validate_not_immediate('LONG', 101.0, 99.5, 100.0)
        assert mark == 100.0

    def test_short_valid(self):
        mark = validate_not_immediate('SHORT', 99.0, 100.5, 100.0)
        assert mark == 100.0

    def test_long_sl_too_high(self):
        with pytest.raises(ValueError, match="SL.*>= mark"):
            validate_not_immediate('LONG', 101.0, 100.0, 100.0)

    def test_long_tp_too_low(self):
        with pytest.raises(ValueError, match="TP.*<= mark"):
            validate_not_immediate('LONG', 100.0, 99.5, 100.0)

    def test_short_sl_too_low(self):
        with pytest.raises(ValueError, match="SL.*<= mark"):
            validate_not_immediate('SHORT', 99.0, 100.0, 100.0)

    def test_short_tp_too_high(self):
        with pytest.raises(ValueError, match="TP.*>= mark"):
            validate_not_immediate('SHORT', 100.0, 100.5, 100.0)

    def test_mark_as_dict(self):
        mark = validate_not_immediate('LONG', 101.0, 99.5, {'markPrice': '100.0'})
        assert mark == 100.0

    def test_tp_sl_as_str(self):
        mark = validate_not_immediate('LONG', '101.0', '99.5', 100.0)
        assert mark == 100.0

    def test_invalid_side(self):
        with pytest.raises(ValueError, match="Unknown side"):
            validate_not_immediate('INVALID', 101.0, 99.5, 100.0)