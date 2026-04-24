"""
BTCUSDT Aurora Runtime Field Audit (Jan 2026)

Goal: Prove that the BTCUSDT fields in `config/aurora/strategies/aurora.yaml`
are (1) loaded by ConfigLoader and (2) affect runtime components.

Scope:
- AuroraHandler (strategy-side): weights, side_bias overrides, regime_thresholds, liquidity_gate,
  holding_period, reentry_cooldown_sec, signal_threshold override, volatility_entry_logic, regime_tpsl.
- DecisionMaking (gateway): regime_sizing multiplier reaches sizing call, position_mode + cooldown_sec reach helpers.
- ExecutionPosition (manage/open bootstrap surfaces): take_profit, trailing_stop, max_hold_sec, leverage.
"""

import shutil
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest
import yaml

from apps.reference.config_loader import ConfigLoader


def _copy_config_to_tmp(tmp_path: Path) -> Path:
    cfg_dir = tmp_path / "aurora"
    shutil.copytree(Path("config/aurora"), cfg_dir)
    return cfg_dir


def _write_yaml(path: Path, data: Dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _mutate_btc_aurora_fields(cfg_dir: Path) -> None:
    """Mutate BTCUSDT fields to unique values to prove runtime wiring (no silent defaults)."""
    # Disable backtest overlay for this audit test (user request: ignore backtest YAML).
    system_path = cfg_dir / "system.yaml"
    system_data = yaml.safe_load(system_path.read_text(encoding="utf-8"))
    assert isinstance(system_data, dict)
    system_data["trading_mode"] = "live"
    _write_yaml(system_path, system_data)

    trading_path = cfg_dir / "trading.yaml"
    trading_data = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
    assert isinstance(trading_data, dict)
    if isinstance(trading_data.get("trading"), dict):
        trading_data["trading"]["mode"] = "live"
    _write_yaml(trading_path, trading_data)

    # ── Instruments SSOT leverage (used by ExecPos bootstrap) ──
    instruments_path = cfg_dir / "instruments.yaml"
    instruments_data = yaml.safe_load(instruments_path.read_text(encoding="utf-8"))
    instruments_data["instruments"]["BTCUSDT"]["execution"]["target_leverage"] = 21
    instruments_data["instruments"]["BTCUSDT"]["execution"]["margin_mode"] = "isolated"
    _write_yaml(instruments_path, instruments_data)

    aurora_path = cfg_dir / "strategies" / "aurora.yaml"
    data = yaml.safe_load(aurora_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    aurora = data["aurora"]
    btc = aurora["assets"]["BTCUSDT"]

    # Leverage (stale copy in aurora.yaml, kept for legacy audit)
    btc["leverage"]["target"] = 21
    btc["leverage"]["mode"] = "ISOLATED"

    # Weights (unique pattern)
    btc["weights"] = {
        "ema_bias": 0.21,
        "volume_spike": 0.16,
        "macro_resid": 0.14,
        "obi": 0.19,
        "tfi": 0.09,
        "volatility_state": 0.11,
        "depth_imbalance": -0.06,
        "delta_price": 0.07,
    }

    # Enabled + position_mode
    btc["enabled"] = True
    btc["position_mode"] = "STRICT"

    # Holding period overrides
    btc["holding_period"]["min_duration_sec"] = 21
    btc["holding_period"]["emergency_exit_threshold"] = 0.77

    # Re-entry cooldown override
    btc["reentry_cooldown_sec"] = 77

    # Liquidity gate (enable + high min to exercise)
    btc["liquidity_gate"]["enabled"] = True
    btc["liquidity_gate"]["kappa_min"] = 0.8
    btc["liquidity_gate"]["kappa_max"] = 0.9
    btc["liquidity_gate"]["failsafe_qty_check"] = True

    # Side-bias overrides (per-symbol)
    btc["side_bias"]["penalty_factor"] = 0.99
    btc["side_bias"]["window_sec"] = 123
    btc["side_bias"]["target_ratio"] = 0.11

    # Regime threshold override (per-symbol)
    btc["regime_thresholds"]["LOW_VOLATILITY"] = 2.5

    # Regime sizing multiplier (used by DecisionMaking sizing)
    btc["regime_sizing"]["LOW_VOLATILITY"] = 2.0

    # Exit + regime TP/SL is already enabled; make base values unique
    btc["exit"]["sl_pct"] = 0.021
    btc["exit"]["max_hold_sec"] = 1234

    # Take profit / trailing stop (used by ExecPos manage flow)
    btc["take_profit"]["tp_low_ratio"] = 0.55
    btc["take_profit"]["tp_high_ratio"] = 1.23
    btc["take_profit"]["partial_exit_pct"] = 0.66

    btc["trailing_stop"]["enabled"] = True
    btc["trailing_stop"]["activation_pct"] = 0.031
    btc["trailing_stop"]["trail_pct"] = 0.017
    btc["trailing_stop"]["min_update_interval_sec"] = 7

    # Regime allowlist: keep LOW_VOLATILITY for test regime
    btc["allowed_regimes"] = ["LOW_VOLATILITY"]

    # Per-symbol threshold override (enabled) + per-symbol DM cooldown
    btc["signal_threshold"]["enabled"] = True
    btc["signal_threshold"]["value"] = 0.345
    btc["cooldown_sec"] = 99

    # Volatility entry logic: make LOW_VOLATILITY multiplier unique
    btc["volatility_entry_logic"]["enabled"] = True
    btc["volatility_entry_logic"]["regime_multipliers"]["LOW_VOLATILITY"] = 0.5
    btc["volatility_entry_logic"]["regime_multipliers"]["DEFAULT"] = 0.2

    _write_yaml(aurora_path, data)


class TestBtcusdtAuroraRuntimeFields:
    def test_fields_load_and_reach_runtime(self, tmp_path: Path) -> None:
        cfg_dir = _copy_config_to_tmp(tmp_path)
        _mutate_btc_aurora_fields(cfg_dir)

        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()

        btc_cfg = config.strategies.aurora.assets["BTCUSDT"]
        assert btc_cfg.leverage.target == 21
        assert btc_cfg.reentry_cooldown_sec == 77
        assert btc_cfg.holding_period.min_duration_sec == 21
        assert btc_cfg.cooldown_sec == 99

        # ── AuroraHandler: prove per-symbol overrides are used ──
        from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler

        emitted: list[tuple[str, dict]] = []

        def emit_fn(name: str, payload: dict) -> None:
            emitted.append((name, payload))

        now = 1000.0
        handler = AuroraHandler(
            config=config,
            emit_fn=emit_fn,
            monotonic_fn=lambda: now,
            wall_time_fn=lambda: now,
        )
        handler._basis_required_bars_override = 0

        symbol = "BTCUSDT"
        state = handler._symbol_states[symbol]
        state.regime = "LOW_VOLATILITY"
        state.regime_effective = "LOW_VOLATILITY"
        state.last_regime_heartbeat_ms = int(now * 1000)

        # Side-bias override affects both parameters + pruning window
        state.buy_timestamps = [now - 200, now - 10]   # one should be pruned by 123s window
        state.sell_timestamps = [now - 50]
        sb = handler._get_side_bias_state(symbol)
        assert sb.window_sec == 123
        assert sb.penalty_factor == 0.99
        assert sb.target_ratio == 0.11
        assert sb.buy_count == 1  # pruned (now-200) outside 123s window
        assert sb.sell_count == 1

        # Holding/reentry overrides reach runtime
        assert handler._get_min_duration_sec(symbol) == 21.0
        assert handler._get_emergency_threshold(symbol) == 0.77
        assert handler._get_reentry_cooldown_sec(symbol) == 77.0

        # Weights come from per-symbol config (not global)
        weights = handler._get_signal_weights(symbol, btc_cfg)
        assert weights["ema_bias"] == 0.21
        assert weights["depth_imbalance"] == -0.06

        # Spy kernel: validate the handler passes per-symbol threshold + regime_thresholds
        captured: dict[str, Any] = {}

        class _SpyKernel:
            @staticmethod
            def compute(**kwargs):  # type: ignore[no-untyped-def]
                captured.update(kwargs)
                return SimpleNamespace(
                    side="buy",
                    score=Decimal("0.9"),
                    thr_buy=Decimal("0.1"),
                    thr_sell=Decimal("0.1"),
                    why_chain=[],
                    psi_vector={},
                    regime=kwargs.get("regime_name"),
                    deferred=False,
                    defer_reason=None,
                    shield_multiplier=Decimal("1.0"),
                )

        handler.scoring_kernel_cls = _SpyKernel

        handler.on_process_strategy(
            {
                "symbol": symbol,
                "tf_sec": 300,
                "bar_close_ts": int(now * 1000),
                "bar": {"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1},
                "features": {
                    "price": "100",
                    "atr": "10",
                    "liquidity_kappa": "0.85",  # passes kappa_min=0.8
                },
                "warmup": {
                    "full_ready": True,
                    "ready": {"liquidity_kappa": True},
                },
            }
        )

        assert Decimal(str(captured["base_threshold"])) == Decimal("0.345")
        assert captured["regime_thresholds"]["LOW_VOLATILITY"] == 2.5

        # Signal emitted; entry_price must reflect volatility_entry_logic multiplier (BUY: 100 - 10*0.5 = 95)
        assert any(name == "EVT:STRATEGY_SIGNAL_PRODUCED" for name, _ in emitted)
        sig = next(payload for name, payload in emitted if name == "EVT:STRATEGY_SIGNAL_PRODUCED")
        assert sig["symbol"] == symbol
        assert sig["side"] == "BUY"
        assert Decimal(sig["price_ctx"]["entry_price"]) == Decimal("95")
        # Regime TP/SL injected (proves exit + take_profit + regime_tpsl are processed by handler)
        assert "stop_price" in sig["price_ctx"]
        assert "target_price" in sig["price_ctx"]
        assert sig.get("tpsl_ctx", {}).get("mode") == "pct_mult"

        # ── ExecutionPosition ManageFlow: take_profit / trailing_stop / max_hold_sec wired ──
        from apps.reference.domains.execution_position.fsm_manage import ManageFlowFSM

        manage = ManageFlowFSM(config=config)
        assert manage._get_take_profit_params(symbol) == (0.55, 1.23, 0.66)
        assert manage._get_trailing_stop_params(symbol) == (True, 0.031, 0.017, 7)
        assert manage._get_max_hold_sec(symbol) == 1234

        # ── ExecutionPosition bootstrap surface: leverage config reaches collector ──
        from apps.reference.domains.execution_position.fsm import ExecPosFSM

        ep = ExecPosFSM(config=config, fsm=MagicMock(), shadow_mode=True)
        leverage_cfgs = ep._collect_leverage_configs()
        assert leverage_cfgs["BTCUSDT"].target == 21
        assert leverage_cfgs["BTCUSDT"].mode == "ISOLATED"

    def test_liquidity_gate_blocks_when_kappa_low(self, tmp_path: Path) -> None:
        cfg_dir = _copy_config_to_tmp(tmp_path)
        _mutate_btc_aurora_fields(cfg_dir)

        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()

        from apps.reference.domains.strategies.runtimes.aurora.handler import AuroraHandler

        emitted: list[tuple[str, dict]] = []

        def emit_fn(name: str, payload: dict) -> None:
            emitted.append((name, payload))

        now = 1000.0
        handler = AuroraHandler(
            config=config,
            emit_fn=emit_fn,
            monotonic_fn=lambda: now,
            wall_time_fn=lambda: now,
        )
        handler._basis_required_bars_override = 0

        symbol = "BTCUSDT"
        state = handler._symbol_states[symbol]
        state.regime = "LOW_VOLATILITY"
        state.regime_effective = "LOW_VOLATILITY"
        state.last_regime_heartbeat_ms = int(now * 1000)

        # Kernel would emit BUY, but liquidity gate must block before scoring/emit.
        handler.scoring_kernel_cls = MagicMock()
        handler.scoring_kernel_cls.compute.return_value = SimpleNamespace(
            side="buy",
            score=Decimal("0.9"),
            thr_buy=Decimal("0.1"),
            thr_sell=Decimal("0.1"),
            why_chain=[],
            psi_vector={},
            regime=state.regime,
            deferred=False,
            defer_reason=None,
        )

        handler.on_process_strategy(
            {
                "symbol": symbol,
                "tf_sec": 300,
                "bar_close_ts": int(now * 1000),
                "bar": {"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1},
                "features": {
                    "price": "100",
                    "atr": "10",
                    "liquidity_kappa": "0.75",  # below kappa_min=0.8
                },
                "warmup": {
                    "full_ready": True,
                    "ready": {"liquidity_kappa": True},
                },
            }
        )

        assert not any(name == "EVT:STRATEGY_SIGNAL_PRODUCED" for name, _ in emitted)
        assert any(name == "EVT:STRATEGY_DECISION_BLOCKED" for name, _ in emitted)
        blocked = next(payload for name, payload in emitted if name == "EVT:STRATEGY_DECISION_BLOCKED")
        assert blocked["symbol"] == symbol
        assert blocked["reason_code"] == "LIQUIDITY_LOW"

    def test_regime_sizing_reaches_decision_making(self, tmp_path: Path) -> None:
        cfg_dir = _copy_config_to_tmp(tmp_path)
        _mutate_btc_aurora_fields(cfg_dir)

        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()

        from apps.reference.domains.decision_making.core.facade import DecisionMaking

        dm = DecisionMaking(fsm=MagicMock(), config=config)
        dm._shared["latest_portfolio"] = {"equity": "1000"}
        dm._clock = SimpleNamespace(now_ms=lambda: 1_000_000, now_sec=lambda: 1000.0)

        # Bypass unrelated gates for this audit test
        dm._record_blocked_intent = MagicMock()
        dm._emit_trade_intent_rejected = MagicMock()
        dm._emit_intent_deferred_v1 = MagicMock()
        dm._check_strategy_arbitration = MagicMock(return_value={"allowed": True})
        dm._warmup_gate_before_trade_intent = MagicMock(return_value=False)
        dm._precheck_exposure_cache = MagicMock(return_value=True)
        dm._is_strategy_qos_enabled = MagicMock(return_value=False)
        dm._handle_flip_orchestration = MagicMock(return_value=None)
        dm._propose_trade_intent = MagicMock()

        dm.symbol_states["BTCUSDT"]["risk"] = {
            "risk_parameters": {"is_trading_allowed": True, "risk_score": 0.0}
        }

        dm._calculate_position_size = MagicMock(
            return_value=(Decimal("1"), "ok", None, {})
        )

        dm._on_strategy_signal_gateway(
            SimpleNamespace(
                pld={
                    "strategy_id": "aurora",
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "rid": "rid-1",
                    "why_chain": [],
                    "readiness": {"warmup_ok": True},
                    "price_ctx": {"entry_price": "100.0"},
                    "ts_ms": 1_000_000,
                    "tf_sec": 300,
                    "scoring": {"regime": "LOW_VOLATILITY"},
                }
            )
        )

        # Regime sizing multiplier from config: strategies.aurora.assets.BTCUSDT.regime_sizing.LOW_VOLATILITY = 2.0
        kwargs = dm._calculate_position_size.call_args.kwargs
        assert kwargs["margin_pct_mult"] == Decimal("2.0")

        # Position mode + per-symbol cooldown are reachable via helpers (no magic fallbacks)
        assert dm._resolve_position_mode(symbol="BTCUSDT", source="aurora") == "STRICT"
        assert dm._get_symbol_cooldown("BTCUSDT", strategy_id="aurora") == 99
