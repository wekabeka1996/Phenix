from tools.metrics_summary import _mget


def test_mget_simple_gauge():
    txt = "exposure_equity_usd 5121.05\n"
    assert _mget(txt, "exposure_equity_usd") == 5121.05


def test_mget_counter_with_label():
    txt = 'fsm_guard_rejects_total{guard="exposure"} 7\n'
    assert _mget(txt, "fsm_guard_rejects_total", 'guard="exposure"') == 7.0
