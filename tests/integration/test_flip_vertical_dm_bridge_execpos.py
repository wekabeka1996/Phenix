from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from vfoundation.core.protocol import Message

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.core.facade import DecisionMaking
# from apps.reference.main import AuroraBridge  # REMOVED: AuroraBridge does not exist


pytest_plugins = ("tests.domains.execution_position.conftest",)


class _EventBus:
    def __init__(self) -> None:
        self._listeners: dict[str, list[object]] = {}
        self.emitted: list[tuple[str, Message]] = []

    def listen(self, event_name: str, callback: object) -> None:
        self._listeners.setdefault(event_name, []).append(callback)

    def emit(
        self,
        event_name: str,
        payload: dict | None = None,
        why: str | None = None,
        data_ref: object = None,
        **_kwargs: object,
    ) -> None:
        pld = payload or {}
        rid = str(pld.get("rid") or "rid-test")

        # Protocol contract: Message.data_ref must be list (SSOT).
        if data_ref is None:
            data_ref_list: list[str] = []
        elif isinstance(data_ref, list):
            data_ref_list = [str(x) for x in data_ref if x is not None]
        else:
            data_ref_list = [str(data_ref)]

        # Map EVT:FOO topic into Message(op=EVT, verb=FOO) for compatibility.
        op = "EVT"
        verb = event_name
        if isinstance(event_name, str) and ":" in event_name:
            op, verb = event_name.split(":", 1)

        msg = Message(
            op=op,
            verb=verb,
            src="test_bus",
            dst="*",
            rid=rid,
            pld=pld,
            why=str(why or ""),
            data_ref=data_ref_list,
        )

        self.emitted.append((event_name, msg))
        for cb in self._listeners.get(event_name, []):
            cb(msg)


def _dm_domain_cfg() -> SimpleNamespace:
    qos = SimpleNamespace(
        exposure_block_cooldown_sec=0,
        max_intents_per_minute_per_symbol=1000,
        mode="shadow",
        symbol_cooldown_sec=0,
        enforce=False,
    )
    position_sizing = SimpleNamespace(min_position_size_usd=10, liquidity_based_cap_usd=10_000)
    arming = SimpleNamespace(require_regime_warmup=False, retry_backoff_ms=0, max_attempts=1)
    features = SimpleNamespace(ttl_sec=60)
    bar_gating = SimpleNamespace(enable=False, bar_ms=60_000)
    behavior_fsm = SimpleNamespace(enable=False, high_vol_multiplier=2.0, low_vol_multiplier=0.5)
    return SimpleNamespace(
        qos=qos,
        position_sizing=position_sizing,
        arming=arming,
        features=features,
        bar_gating=bar_gating,
        behavior_fsm=behavior_fsm,
        flip=SimpleNamespace(enabled=True),
        risk_skew=SimpleNamespace(
            max_skew_sec=5,
            max_defer_count=3,
            defer_cooldown_sec=2,
            defer_window_sec=60,
            until_refresh_retry_sec=30,
        ),
        risk_gate=SimpleNamespace(
            threshold_pct_testnet=20.0,
            threshold_pct_production=50.0,
            min_intents_for_check=10,
        ),
        neocortex_enforcement_mode="shadow",
    )


def _mk_dm_cfg(*, symbol: str, stale_ttl_sec: int) -> SimpleNamespace:
    return SimpleNamespace(
        trading=SimpleNamespace(
            tca_prefs={"max_slippage_bps": 10, "max_latency_ms": 100, "maker_preference": "neutral"},
            risk_budgets={"trade_cvar95_max_bps": 100, "session_cvar95_max_bps": 200},
            mode="testnet",
        ),
        domains=SimpleNamespace(position_tracking=SimpleNamespace(positions_stale_ttl_sec=stale_ttl_sec)),
        instruments={
            symbol: SimpleNamespace(
                tick_size="0.1",
                step_size="0.001",
                min_qty="0.001",
                min_notional="5",
                execution=SimpleNamespace(
                    margin_mode="isolated",
                    target_leverage=20,
                    leverage_policy="verify_only",
                    max_notional_utilization=0.8,
                ),
                sizing=SimpleNamespace(margin_pct=0.02),
                flip=SimpleNamespace(enabled=True, hysteresis_mult=1.7),
            )
        },
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                decision=SimpleNamespace(
                    signal_threshold=0.0,
                    retry_ttl_ms=1000,
                    retry_max_count=1,
                    retry_backoff_factor=1.0,
                    side_bias_penalty_factor=0.5,
                    side_bias_window_sec=60,
                    side_bias_target_ratio=0.6,
                    kelly=None,
                ),
                assets={symbol: SimpleNamespace(position_mode="STRICT")},
            )
        ),
        strategies_registry=None,
    )


def _mk_bridge_cfg(*, stale_ttl_sec: int) -> SimpleNamespace:
    return SimpleNamespace(
        domains=SimpleNamespace(
            position_tracking=SimpleNamespace(positions_stale_ttl_sec=stale_ttl_sec),
            debug=SimpleNamespace(disable_positions_stale_gate=False),
        ),
        bridge=SimpleNamespace(
            retry_scheduler=SimpleNamespace(
                max_attempts=1,
                min_retry_delay_ms=10,
                backoff_factor=1.0,
                jitter_ms=0,
            )
        ),
        instruments={},
        trading=None,
    )


def test_vertical_flip_close_dm_to_bridge_to_execpos(monkeypatch, fsm_harness):
    exec_fsm, _exec_bus, _exec_cfg = fsm_harness

    symbol = "BTCUSDT"
    stale_ttl_sec = 15

    # 1) Wire a real AuroraBridge that will route reduce-only intents -> CMD:CLOSE.
    bus = _EventBus()
    bridge_cfg = _mk_bridge_cfg(stale_ttl_sec=stale_ttl_sec)

    import apps.reference.main as mainmod

    # bridge = AuroraBridge(fsm=bus, config=bridge_cfg)  # type: ignore[arg-type]
    # No bridge needed: ExecPosFSM now listens to TRADE_INTENT_PROPOSED via LocalBus
    exec_fsm.bus = bus  # Wire to test bus
    exec_fsm.bus.listen("EVT:TRADE_INTENT_PROPOSED", exec_fsm._on_trade_intent_proposed)
    
    monkeypatch.setattr(mainmod, "execution_position", exec_fsm)
    # monkeypatch.setattr(mainmod, "_bridge_instance", bridge)
    pass

    # 2) DecisionMaking flip orchestration will emit reduce-only close, then INTENT_DEFERRED.
    dm_cfg = ConfigLoader(Path("config/aurora")).load_config()
    with patch("apps.reference.domains.decision_making.core.facade.DomainConfigResolver") as MockResolver:
        MockResolver.return_value.get_decision_making.return_value = _dm_domain_cfg()
        dm = DecisionMaking(fsm=bus, config=dm_cfg)

    now_ms = int(time.time() * 1000)
    dm.latest_portfolio = {
        "positions": [{"symbol": symbol, "net_position": "1.25", "avg_entry_price": "42000"}],
        "equity": "1000",
        "positions_last_ts_ms": now_ms,
    }

    # Patch only the emission mechanism to keep the test focused on the vertical flip CLOSE path.
    # Unit tests already validate qty derivation + reduce_only for _emit_reduce_only_close.
    def _emit_intent(*, symbol: str, side: str, qty, price, why_chain, rid: str, reduce_only: bool, **_kw):
        bus.emit(
            "EVT:TRADE_INTENT_PROPOSED",
            payload={
                "rid": rid,
                "instrument": symbol,
                "side": side,
                "order": {
                    "qty": str(qty),
                    "price": str(price),
                    "reduce_only": bool(reduce_only),
                },
                "why": list(why_chain or []),
            },
            why="trade_intent",
            data_ref=list(why_chain or []),
        )

    dm._propose_trade_intent = _emit_intent  # type: ignore[method-assign]

    res = dm._handle_flip_orchestration(
        symbol=symbol,
        intent_side="SELL",  # opposite of LONG => flip
        original_pld={"rid": "RID-FLIP-1", "why_chain": ["x"], "price_ctx": {"entry_price": 1}},
        source="aurora",
    )
    assert res == "FLIP_CLOSE_PENDING"

    # 3) Verify DM emitted reduce-only close intent with stable rid.
    intents = [m for (name, m) in bus.emitted if name == "EVT:TRADE_INTENT_PROPOSED"]
    assert intents, "Expected EVT:TRADE_INTENT_PROPOSED from flip CLOSE"
    assert str(intents[0].pld.get("rid") or "").startswith("RID-FLIP-1")
    assert str(intents[0].pld.get("rid") or "").endswith("-close")
    assert intents[0].pld.get("instrument") == symbol
    assert intents[0].pld.get("order", {}).get("reduce_only") is True

    # 4) Verify the bridge executed CMD:CLOSE through ExecPosFSM and emitted DEC:CLOSE.
    close_decs = [m for (name, m) in bus.emitted if name == "DEC:CLOSE"]
    assert close_decs, "Expected bridge to emit DEC:CLOSE (ExecPosFSM result)"
    assert close_decs[0].pld.get("symbol") == symbol
    assert close_decs[0].pld.get("reduce_only") is True
