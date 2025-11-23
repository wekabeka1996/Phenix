import types

import pytest

from apps.reference.domains.execution_position.adapter_factory import build_execution_adapter
from apps.reference.domains.execution_position.binance_execution_adapter import (
    BinanceExecutionAdapter,
)


def _cfg_with_mode(mode: str):
    cfg = types.SimpleNamespace()
    cfg.to_dict = lambda: {"trading": {"trading_mode": mode}}
    return cfg


def test_build_adapter_for_testnet_mode_returns_binance():
    cfg = _cfg_with_mode("testnet")
    adapter = build_execution_adapter(cfg, fsm=None)
    assert isinstance(adapter, BinanceExecutionAdapter)


def test_build_adapter_for_hybrid_returns_binance():
    cfg = _cfg_with_mode("hybrid_live_data_testnet_exec")
    adapter = build_execution_adapter(cfg, fsm=None)
    assert isinstance(adapter, BinanceExecutionAdapter)


def test_build_adapter_for_sim_or_shadow_mode_returns_simulated_or_none():
    for mode in ("sim", "shadow"):
        cfg = _cfg_with_mode(mode)
        adapter = build_execution_adapter(cfg, fsm=None)
        # Accept None if SimulatedExecutionAdapter is not available
        assert adapter is None or adapter.__class__.__name__ == "SimulatedExecutionAdapter"


@pytest.mark.asyncio
async def test_binance_adapter_place_order_v2_shadow_mode():
    cfg = _cfg_with_mode("testnet")
    adapter = BinanceExecutionAdapter(fsm=None, config=cfg, shadow_mode=True)
    res = await adapter.place_order_v2(
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        quantity="0.01",
        client_order_id="cid-test",
    )
    assert res
    assert res.get("order_id") or res.get("orderId")
