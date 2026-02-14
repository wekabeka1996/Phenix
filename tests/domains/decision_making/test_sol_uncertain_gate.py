from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from apps.reference.config_loader import ConfigLoader
from apps.reference.config_models import AuroraConfig
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler


@pytest.fixture
def production_config() -> AuroraConfig:
    config_dir = Path(__file__).parents[3] / "config" / "aurora"
    return ConfigLoader(config_dir=config_dir).load_config()


def test_sol_uncertain_blocked(production_config: AuroraConfig) -> None:
    emit_mock = MagicMock()
    handler = AuroraHandler(config=production_config, emit_fn=emit_mock)

    state = handler._symbol_states["SOLUSDT"]
    state.regime = "UNCERTAIN"
    state.regime_effective = "UNCERTAIN"
    state.warmup_full_ready = True
    state.last_regime_heartbeat_ms = int(time.time() * 1000)

    handler.scoring_kernel_cls = MagicMock()
    handler.scoring_kernel_cls.compute.return_value = SimpleNamespace(
        side="SELL",
        score=Decimal("-0.9"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=["unit:test"],
        psi_vector={},
        regime="UNCERTAIN",
        deferred=False,
        defer_reason=None,
    )

    handler.on_process_strategy(
        {
            "symbol": "SOLUSDT",
            "tf_sec": 300,
            "bar_close_ts": int(time.time()),
            "bar": {"open": 79.7, "high": 79.9, "low": 79.3, "close": 79.64, "volume": 100},
            "features": {
                "price": "79.6401785714285714300",
                "atr": "0.55",
                "volatility": 0.2,
                "liquidity_kappa": "0.5",
                "liquidity": {"depth_usd": 150000},
            },
            "warmup": {"full_ready": True, "ready": {"liquidity_kappa": True}},
        }
    )

    emitted_types = [call.args[0] for call in emit_mock.call_args_list]
    assert "EVT:STRATEGY_SIGNAL_PRODUCED" not in emitted_types
    assert "EVT:STRATEGY_DECISION_BLOCKED" in emitted_types

    blocked_payload = next(
        call.args[1]
        for call in emit_mock.call_args_list
        if call.args[0] == "EVT:STRATEGY_DECISION_BLOCKED"
    )
    assert blocked_payload["reason_code"] == "REGIME_NOT_ALLOWLISTED"
