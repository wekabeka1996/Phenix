from __future__ import annotations

import copy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml

from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    build_canonical_bar_identity,
)
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
from apps.reference.domains.decision_making.entry_plan import resolve_strategy_entry_prices
from apps.reference.domains.decision_making.strategy_gateway import StrategyGateway
from apps.reference.domains.decision_making.tpsl_owner import (
    TPSL_OWNER_ENTRY_PLAN,
    TPSL_OWNER_LOSS_TP_MIN_DIST_BPS,
    TPSL_OWNER_REGIME_TPSL,
)
from vfoundation.core.protocol import Message


REPO_ROOT = Path(__file__).resolve().parents[3]
STRATEGY_PATH = REPO_ROOT / "config/aurora/strategies/aurora.yaml"
DOMAINS_PATH = REPO_ROOT / "config/aurora/domains.yaml"


def _load_current_aurora_assets() -> dict:
    payload = yaml.safe_load(STRATEGY_PATH.read_text(encoding="utf-8"))
    return payload["aurora"]["assets"]


def _load_current_entry_plan_cfg() -> dict:
    payload = yaml.safe_load(DOMAINS_PATH.read_text(encoding="utf-8"))
    return payload["decision_making"]["entry_plan"]


def _build_instr_cfg(raw: dict) -> SimpleNamespace:
    exit_raw = raw["exit"]
    regime_tpsl_raw = exit_raw["regime_tpsl"]
    take_profit_raw = raw["take_profit"]
    volatility_entry_raw = raw.get("volatility_entry_logic") or {}
    return SimpleNamespace(
        exit=SimpleNamespace(
            sl_pct=exit_raw["sl_pct"],
            regime_tpsl=SimpleNamespace(
                enabled=bool(regime_tpsl_raw["enabled"]),
                mode=str(regime_tpsl_raw["mode"]),
                sl_mult=dict(regime_tpsl_raw.get("sl_mult") or {}),
                tp_mult=dict(regime_tpsl_raw.get("tp_mult") or {}),
                sl_k_atr=dict(regime_tpsl_raw.get("sl_k_atr") or {}),
                rr_by_regime=dict(regime_tpsl_raw.get("rr_by_regime") or {}),
                min_sl_pct=regime_tpsl_raw.get("min_sl_pct"),
                max_sl_pct=regime_tpsl_raw.get("max_sl_pct"),
                min_tp_rr=regime_tpsl_raw.get("min_tp_rr"),
                max_tp_rr=regime_tpsl_raw.get("max_tp_rr"),
                min_dist_bps=regime_tpsl_raw.get("min_dist_bps"),
            ),
        ),
        take_profit=SimpleNamespace(
            tp_low_ratio=take_profit_raw["tp_low_ratio"],
            tp_high_ratio=take_profit_raw.get("tp_high_ratio"),
        ),
        volatility_entry_logic=SimpleNamespace(
            enabled=bool(volatility_entry_raw.get("enabled", False)),
            regime_multipliers=dict(
                volatility_entry_raw.get("regime_multipliers") or {}),
        ),
        regime_sizing=dict(raw.get("regime_sizing") or {}),
        max_risk_score=None,
    )


def _build_entry_plan_cfg(raw: dict) -> SimpleNamespace:
    return SimpleNamespace(**copy.deepcopy(raw))


def _wrap_domains_cfg(entry_plan_raw: dict) -> SimpleNamespace:
    return SimpleNamespace(
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                entry_plan=_build_entry_plan_cfg(entry_plan_raw),
            )
        )
    )


def _make_handler(symbol: str, instr_cfg: SimpleNamespace) -> tuple[AuroraHandler, list[tuple[str, dict]]]:
    emitted: list[tuple[str, dict]] = []

    def _emit(name: str, payload: dict) -> None:
        emitted.append((name, payload))

    config = SimpleNamespace(
        strategies=SimpleNamespace(aurora=SimpleNamespace()),
        instruments=None,
    )

    with patch.object(AuroraHandler, "_load_config", lambda self: None):
        handler = AuroraHandler(
            config=config,
            emit_fn=_emit,
            monotonic_fn=lambda: 1_700_000_000.0,
            wall_time_fn=lambda: 1_700_000_000.0,
        )

    handler.timeframe_sec = 300
    handler._get_instrument_config = lambda _symbol: instr_cfg

    state = handler._symbol_states[symbol]
    state.warmup_full_ready = True
    state.regime = "LOW_VOLATILITY"
    state.regime_ts_ms = 1_700_000_000_000
    state.regime_confidence = 0.42
    return handler, emitted


def _make_source_event(symbol: str) -> dict:
    identity = build_canonical_bar_identity(
        symbol=symbol,
        timeframe_sec=300,
        bar_start_ts_ms=1_699_999_700_000,
        close_boundary_ts_ms=1_700_000_000_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )
    return {
        "bar_close_ts": identity.bar_end_ts_ms,
        "source_mode": "live",
        "bar_identity": identity.to_payload(),
        "replay_identity": identity.to_replay_identity().to_payload(),
        "replay_generation": 0,
    }


def _make_result() -> SimpleNamespace:
    return SimpleNamespace(
        side="buy",
        score=Decimal("0.9"),
        thr_buy=Decimal("0.1"),
        thr_sell=Decimal("0.1"),
        why_chain=["enter:buy"],
        psi_vector={},
        regime="LOW_VOLATILITY",
    )


def _make_gateway(symbol: str, instr_cfg: SimpleNamespace, entry_plan_raw: dict) -> tuple[StrategyGateway, MagicMock]:
    dm = MagicMock()
    dm._clock.now_ms.return_value = 1_700_000_000_000
    dm.symbol_states = {
        symbol: {
            "risk": {
                "risk_parameters": {
                    "is_trading_allowed": True,
                    "risk_score": 0.0,
                },
                "ts": 0,
            },
            "features": {"ts": 0, "features": {}},
        }
    }
    dm.config = SimpleNamespace(
        domains=SimpleNamespace(
            decision_making=SimpleNamespace(
                entry_plan=_build_entry_plan_cfg(entry_plan_raw),
            ),
            risk_management=SimpleNamespace(
                trading_allowed_thresholds=SimpleNamespace(max_risk_score=100),
            ),
        ),
        system=SimpleNamespace(market_data=None),
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(
                decision=SimpleNamespace(
                    retry_max_count=5, retry_backoff_factor=2.0),
            )
        ),
    )
    dm.latest_portfolio = {"equity": 1000}
    dm.features_ttl_sec = 30
    dm._check_strategy_arbitration.return_value = {"allowed": True}
    dm._handle_flip_orchestration.return_value = None
    dm._qos_enabled_for_strategy.return_value = False
    dm._calculate_position_size.return_value = (
        Decimal("1.0"), "ok", None, None)
    dm._precheck_exposure_cache.return_value = True
    dm._warmup_gate_before_trade_intent.return_value = False
    dm._degraded_context_gate_should_defer.return_value = False
    dm._get_aurora_instrument_cfg.return_value = instr_cfg
    dm._propose_trade_intent = MagicMock()

    gateway = StrategyGateway(dm)
    gateway._reject = MagicMock()
    gateway._defer = MagicMock()
    return gateway, dm


def _make_signal_message(payload: dict) -> Message:
    return Message(
        op="EVT",
        verb="produced",
        src="decision_making",
        dst="decision_making",
        name="EVT:STRATEGY_SIGNAL_PRODUCED",
        pld=payload,
    )


def _resolve_fallback(
    *,
    side: str,
    entry_price_dec: Decimal,
    atr_value: str,
    obi_close: str,
    entry_plan_raw: dict,
    pld_extra: dict | None = None,
) -> tuple[str, str, dict | None]:
    rejects: list[dict] = []
    pld = {
        "volatility": {"atr_14": atr_value, "atr_ready": True},
        "liquidity": {"obi_close": obi_close},
    }
    if pld_extra:
        pld.update(pld_extra)
    return resolve_strategy_entry_prices(
        symbol="TESTUSDT",
        strategy_id="aurora",
        side=side,
        rid="rid-1",
        price_ctx={"entry_price": str(entry_price_dec)},
        pld=pld,
        entry_price_dec=entry_price_dec,
        why_chain=[],
        config=_wrap_domains_cfg(entry_plan_raw),
        logger=MagicMock(),
        reject_fn=lambda **kwargs: rejects.append(kwargs),
    )


def test_current_eth_low_vol_regime_tpsl_survives_guardrails() -> None:
    assets = _load_current_aurora_assets()
    instr_cfg = _build_instr_cfg(assets["ETHUSDT"])
    handler, _ = _make_handler("ETHUSDT", instr_cfg)

    result = handler._compute_regime_tpsl(
        symbol="ETHUSDT",
        entry_price=Decimal("2000"),
        side="BUY",
        regime="LOW_VOLATILITY",
        instr_cfg=instr_cfg,
        features={"volatility": {"atr_14": "10.0", "atr_ready": True}},
    )

    assert result is not None
    assert result["stop_price"] < Decimal("2000")
    assert result["target_price"] > Decimal("2000")
    assert result["tpsl_ctx"]["regime_used"] == "LOW_VOLATILITY"


def test_current_sol_low_vol_regime_tpsl_fails_tp_min_dist_guardrail() -> None:
    assets = _load_current_aurora_assets()
    instr_cfg = _build_instr_cfg(assets["SOLUSDT"])
    handler, _ = _make_handler("SOLUSDT", instr_cfg)
    regime_tpsl_cfg = instr_cfg.exit.regime_tpsl

    candidate = handler._compute_tpsl_pct_mult(
        entry_price=Decimal("100"),
        side="BUY",
        regime_used="LOW_VOLATILITY",
        exit_cfg=instr_cfg.exit,
        tp_cfg=instr_cfg.take_profit,
        regime_tpsl_cfg=regime_tpsl_cfg,
    )

    assert candidate is not None
    tp_dist_bps = ((candidate["target_price"] -
                   Decimal("100")) / Decimal("100")) * Decimal("10000")
    assert tp_dist_bps < Decimal(str(regime_tpsl_cfg.min_dist_bps))

    guarded = handler._apply_tpsl_guardrails(
        symbol="SOLUSDT",
        entry_price=Decimal("100"),
        side="BUY",
        result=candidate,
        regime_tpsl_cfg=regime_tpsl_cfg,
    )

    assert guarded is None
    assert handler._get_tpsl_owner_loss_reason() == TPSL_OWNER_LOSS_TP_MIN_DIST_BPS


def test_aurora_success_path_keeps_regime_tpsl_as_final_owner() -> None:
    assets = _load_current_aurora_assets()
    entry_plan_raw = _load_current_entry_plan_cfg()
    instr_cfg = _build_instr_cfg(assets["ETHUSDT"])
    handler, emitted = _make_handler("ETHUSDT", instr_cfg)

    handler._emit_signal(
        "ETHUSDT",
        _make_result(),
        {
            "price": "2000.0",
            "volatility": {"atr_14": "10.0", "atr_ready": True},
            "liquidity": {"obi_close": "0.10"},
        },
        _make_source_event("ETHUSDT"),
    )

    assert len(emitted) == 1
    _, payload = emitted[0]
    assert payload["price_ctx"]["stop_price"] is not None
    assert payload["price_ctx"]["target_price"] is not None
    assert payload["tpsl_owner_ctx"] == {
        "intended_owner": TPSL_OWNER_REGIME_TPSL,
        "final_owner": TPSL_OWNER_REGIME_TPSL,
        "owner_loss_reason": None,
    }

    payload["runtime_permissions"] = {
        "can_manage_existing_risk": True,
        "can_open_new_risk": True,
        "mode": "OPEN_AND_MANAGE",
    }

    gateway, dm = _make_gateway("ETHUSDT", instr_cfg, entry_plan_raw)
    gateway.process_signal(_make_signal_message(payload))

    gateway._reject.assert_not_called()
    dm._propose_trade_intent.assert_called_once()
    kwargs = dm._propose_trade_intent.call_args.kwargs
    assert kwargs["stop_price"] == payload["price_ctx"]["stop_price"]
    assert kwargs["target_price"] == payload["price_ctx"]["target_price"]
    assert kwargs["entry_plan_trace"] is None
    assert kwargs["tpsl_owner_ctx"] == {
        "intended_owner": TPSL_OWNER_REGIME_TPSL,
        "final_owner": TPSL_OWNER_REGIME_TPSL,
        "owner_loss_reason": None,
    }
    assert any(
        call.args == (
            "[%s] TPSL_OWNER_RESOLVED intended=%s final=%s reason=%s",
            "ETHUSDT",
            TPSL_OWNER_REGIME_TPSL,
            TPSL_OWNER_REGIME_TPSL,
            None,
        )
        for call in gateway.logger.info.call_args_list
    )


def test_aurora_guardrail_fail_falls_back_to_entry_plan_owner() -> None:
    assets = _load_current_aurora_assets()
    entry_plan_raw = _load_current_entry_plan_cfg()
    instr_cfg = _build_instr_cfg(assets["SOLUSDT"])
    handler, emitted = _make_handler("SOLUSDT", instr_cfg)

    handler._emit_signal(
        "SOLUSDT",
        _make_result(),
        {
            "price": "100.0",
            "volatility": {"atr_14": "1.0", "atr_ready": True},
            "liquidity": {"obi_close": "0.05"},
        },
        _make_source_event("SOLUSDT"),
    )

    assert len(emitted) == 1
    _, payload = emitted[0]
    assert payload["price_ctx"].get("stop_price") is None
    assert payload["price_ctx"].get("target_price") is None
    assert payload.get("tpsl_ctx") is None
    assert payload["tpsl_owner_ctx"] == {
        "intended_owner": TPSL_OWNER_REGIME_TPSL,
        "final_owner": None,
        "owner_loss_reason": TPSL_OWNER_LOSS_TP_MIN_DIST_BPS,
    }

    payload["runtime_permissions"] = {
        "can_manage_existing_risk": True,
        "can_open_new_risk": True,
        "mode": "OPEN_AND_MANAGE",
    }

    gateway, dm = _make_gateway("SOLUSDT", instr_cfg, entry_plan_raw)
    gateway.process_signal(_make_signal_message(payload))

    gateway._reject.assert_not_called()
    dm._propose_trade_intent.assert_called_once()
    kwargs = dm._propose_trade_intent.call_args.kwargs
    assert kwargs["entry_plan_trace"] is not None
    assert kwargs["stop_price"] is not None
    assert kwargs["target_price"] is not None
    assert kwargs["tpsl_owner_ctx"] == {
        "intended_owner": TPSL_OWNER_REGIME_TPSL,
        "final_owner": TPSL_OWNER_ENTRY_PLAN,
        "owner_loss_reason": TPSL_OWNER_LOSS_TP_MIN_DIST_BPS,
    }
    assert any(
        call.args == (
            "[%s] TPSL_OWNER_RESOLVED intended=%s final=%s reason=%s",
            "SOLUSDT",
            TPSL_OWNER_REGIME_TPSL,
            TPSL_OWNER_ENTRY_PLAN,
            TPSL_OWNER_LOSS_TP_MIN_DIST_BPS,
        )
        for call in gateway.logger.info.call_args_list
    )

    ref_price = Decimal(payload["price_ctx"]["entry_price"])
    atr_value = Decimal(str(payload["volatility"]["atr_14"]))
    min_offset = ref_price * Decimal("0.0001")
    sl_offset = max(
        Decimal(str(entry_plan_raw["sl_k_atr"])) * atr_value, min_offset)
    tp_offset = max(
        Decimal(str(entry_plan_raw["tp_k_atr"])) * atr_value, min_offset)

    assert kwargs["stop_price"] == str(ref_price - sl_offset)
    assert kwargs["target_price"] == str(ref_price + tp_offset)


def test_entry_plan_fallback_preserves_long_and_short_geometry() -> None:
    entry_plan_raw = _load_current_entry_plan_cfg()
    ref_price = Decimal("100")
    atr_value = Decimal("2")
    min_offset = ref_price * Decimal("0.0001")
    sl_offset = max(
        Decimal(str(entry_plan_raw["sl_k_atr"])) * atr_value, min_offset)
    tp_offset = max(
        Decimal(str(entry_plan_raw["tp_k_atr"])) * atr_value, min_offset)

    long_stop, long_target, long_trace = _resolve_fallback(
        side="BUY",
        entry_price_dec=ref_price,
        atr_value=str(atr_value),
        obi_close="0.25",
        entry_plan_raw=entry_plan_raw,
    )
    short_stop, short_target, short_trace = _resolve_fallback(
        side="SELL",
        entry_price_dec=ref_price,
        atr_value=str(atr_value),
        obi_close="-0.25",
        entry_plan_raw=entry_plan_raw,
    )

    assert long_trace is not None
    assert short_trace is not None
    assert Decimal(long_target) > ref_price > Decimal(long_stop)
    assert Decimal(short_stop) > ref_price > Decimal(short_target)
    assert long_stop == str(ref_price - sl_offset)
    assert long_target == str(ref_price + tp_offset)
    assert short_stop == str(ref_price + sl_offset)
    assert short_target == str(ref_price - tp_offset)


def test_fallback_owner_knobs_are_domains_entry_plan_not_regime_or_obi() -> None:
    entry_plan_raw = _load_current_entry_plan_cfg()
    base_stop, base_target, base_trace = _resolve_fallback(
        side="BUY",
        entry_price_dec=Decimal("100"),
        atr_value="2",
        obi_close="0.90",
        entry_plan_raw=entry_plan_raw,
        pld_extra={
            "regime_ctx": {"regime": "LOW_VOLATILITY"},
            "scoring": {"regime": "LOW_VOLATILITY"},
        },
    )
    alt_stop, alt_target, alt_trace = _resolve_fallback(
        side="BUY",
        entry_price_dec=Decimal("100"),
        atr_value="2",
        obi_close="-0.90",
        entry_plan_raw=entry_plan_raw,
        pld_extra={
            "regime_ctx": {"regime": "HIGH_VOLATILITY"},
            "scoring": {"regime": "HIGH_VOLATILITY"},
        },
    )

    tuned_entry_plan = copy.deepcopy(entry_plan_raw)
    tuned_entry_plan["sl_k_atr"] = entry_plan_raw["sl_k_atr"] + 1.0
    tuned_entry_plan["tp_k_atr"] = entry_plan_raw["tp_k_atr"] + 1.0
    tuned_stop, tuned_target, _ = _resolve_fallback(
        side="BUY",
        entry_price_dec=Decimal("100"),
        atr_value="2",
        obi_close="0.90",
        entry_plan_raw=tuned_entry_plan,
    )

    assert base_trace is not None
    assert alt_trace is not None
    assert base_stop == alt_stop
    assert base_target == alt_target
    assert base_trace["obi_multiplier"] != alt_trace["obi_multiplier"]
    assert tuned_stop != base_stop
    assert tuned_target != base_target
