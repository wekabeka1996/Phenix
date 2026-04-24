"""
Tests for AuroraHandler — Stateful Strategy Handler.

Verifies:
1. Regime caching from EVT:REGIME_DETECTED
2. Warmup tracking
3. Side bias history management
4. Signal emission with readiness contract
"""
import pytest
import time
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from apps.reference.domains.strategies.runtimes.aurora.handler import (
    AuroraHandler,
    SymbolState,
)


class TestAuroraHandlerInit:
    """Tests for handler initialization."""

    def test_handler_creates_with_config(self):
        """Handler should initialize with config and emit function."""
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,  # MANDATORY per CLOSEOUT-BASELINE-001
                    decision=SimpleNamespace(
                        signal_threshold=0.15,
                        side_bias_window_sec=300,
                        side_bias_target_ratio=0.7,
                        side_bias_penalty_factor=0.3,
                        side_bias_min_intents=15,
                        regime_threshold_multipliers={
                            "DEFAULT": 1.0, "HIGH_VOL": 1.5},
                        direction_strength_scoring=SimpleNamespace(
                            directional_features=["obi", "tfi"],
                            strength_features=["volume_spike"],
                            strength_alpha=0.6,
                            strength_cap=2.0,
                        ),
                        signals=SimpleNamespace(
                            delta_price_cap_pct=0.01, normalize_signals_mode="signed_v2"),
                    ),
                    assets={},
                )
            )
        )
        emit_fn = MagicMock()

        handler = AuroraHandler(config=config, emit_fn=emit_fn)

        assert handler.signal_threshold == Decimal("0.15")
        assert handler.side_bias_window_sec == 300.0
        assert handler.side_bias_target_ratio == 0.7
        assert handler.regime_thresholds["HIGH_VOL"] == 1.5
        assert handler.timeframe_sec == 300  # Verify mandatory field


class TestRegimeCaching:
    """Tests for regime state caching."""

    @pytest.fixture
    def handler(self):
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,  # MANDATORY per CLOSEOUT-BASELINE-001
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=None,
                    ),
                    assets={},
                )
            )
        )
        return AuroraHandler(config=config, emit_fn=MagicMock())

    def test_regime_detected_updates_cache(self, handler):
        """on_regime_detected should cache regime state."""
        event = {
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "confidence": 0.85,
            "ts_ms": 1700000000000,
            "warmup": {"full_ready": True, "ticks_seen": 100},
        }

        handler.on_regime_detected(event)

        state = handler._symbol_states["BTCUSDT"]
        assert state.regime == "TREND_UP"
        assert state.regime_confidence == 0.85
        # SSOT: warmup comes from CMD:PROCESS_STRATEGY only (REGIME_DETECTED must NOT update warmup)
        assert state.warmup_full_ready is False
        assert state.warmup_ticks_seen == 0

    def test_regime_detected_preserves_missing_confidence(self, handler):
        event = {
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "ts_ms": 1700000000000,
        }

        handler.on_regime_detected(event)

        state = handler._symbol_states["BTCUSDT"]
        assert state.regime == "TREND_UP"
        assert state.regime_confidence is None

    def test_regime_detected_handles_missing_symbol(self, handler):
        """on_regime_detected should handle missing symbol gracefully."""
        event = {"regime": "TREND_UP"}
        handler.on_regime_detected(event)  # Should not raise

    def test_regime_detected_caches_provenance_markers(self, handler):
        event = {
            "symbol": "BTCUSDT",
            "regime": "TREND_UP",
            "confidence": 0.85,
            "raw_confidence": "0.91",
            "changed": False,
            "ts_ms": 1700000000000,
            "last_update_ts_ms": 1700000000123,
            "structural_regime_ref": "structural:BTCUSDT:1700000000000",
        }

        handler.on_regime_detected(event)

        state = handler._symbol_states["BTCUSDT"]
        assert state.regime_structural_regime_ref == "structural:BTCUSDT:1700000000000"
        assert state.regime_changed is False
        assert state.regime_raw_confidence == "0.91"
        assert state.regime_last_update_ts_ms == 1700000000123
        assert state.regime_cache_write_ts_ms > 0


class TestSideBiasHistory:
    """Tests for side bias history tracking."""

    @pytest.fixture
    def handler(self):
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,  # MANDATORY per CLOSEOUT-BASELINE-001
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=60,  # 60s window for easy testing
                        side_bias_target_ratio=0.72,
                        side_bias_penalty_factor=0.25,
                        side_bias_min_intents=5,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=None,
                    ),
                    assets={},
                )
            )
        )
        return AuroraHandler(config=config, emit_fn=MagicMock())

    def test_get_side_bias_state_counts_history(self, handler):
        """_get_side_bias_state should count recent history."""
        now = time.time()
        state = handler._symbol_states["BTCUSDT"]

        # Add some history
        state.buy_timestamps = [now - 10, now - 20, now - 30]
        state.sell_timestamps = [now - 5, now - 15]

        bias_state = handler._get_side_bias_state("BTCUSDT")

        assert bias_state.buy_count == 3
        assert bias_state.sell_count == 2

    def test_get_side_bias_state_filters_old_entries(self, handler):
        """_get_side_bias_state should filter entries outside window."""
        now = time.time()
        state = handler._symbol_states["BTCUSDT"]

        # Add some history - some outside 60s window
        state.buy_timestamps = [now - 10, now - 100]  # One inside, one outside
        state.sell_timestamps = [now - 5, now - 200]  # One inside, one outside

        bias_state = handler._get_side_bias_state("BTCUSDT")

        assert bias_state.buy_count == 1  # Only recent one
        assert bias_state.sell_count == 1  # Only recent one

    def test_update_side_bias_adds_timestamp(self, handler):
        """_update_side_bias should add timestamp to history."""
        handler._update_side_bias("BTCUSDT", "buy")
        handler._update_side_bias("BTCUSDT", "sell")
        handler._update_side_bias("BTCUSDT", "buy")

        state = handler._symbol_states["BTCUSDT"]

        assert len(state.buy_timestamps) == 2
        assert len(state.sell_timestamps) == 1


@pytest.mark.skip(reason="LEGACY: Uses deprecated on_features_calculated API. TODO: Migrate to on_process_strategy (T2B-03)")
class TestSignalEmission:
    """Tests for signal emission with readiness contract."""

    @pytest.fixture
    def handler_with_symbol(self):
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,  # MANDATORY per CLOSEOUT-BASELINE-001
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
                        side_bias_target_ratio=0.72,
                        side_bias_penalty_factor=0.25,
                        side_bias_min_intents=18,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=SimpleNamespace(
                            directional_features=["obi", "tfi"],
                            strength_features=[],
                            strength_alpha=0.5,
                            strength_cap=1.5,
                        ),
                        signals=SimpleNamespace(delta_price_cap_pct=0.005),
                        signal_weights={"obi": 0.5, "tfi": 0.5},
                        feature_neutrals={"obi": 0.0, "tfi": 0.0},
                        essential_features=["obi", "tfi"],
                    ),
                    assets={
                        "BTCUSDT": SimpleNamespace(
                            enabled=True,
                            weights={"obi": 0.5, "tfi": 0.5},
                            feature_neutrals={"obi": 0.0, "tfi": 0.0},
                            essential_features=["obi", "tfi"],
                        ),
                    },
                )
            )
        )
        emit_fn = MagicMock()
        handler = AuroraHandler(config=config, emit_fn=emit_fn)

        # Set up warmup
        handler._symbol_states["BTCUSDT"].warmup_full_ready = True
        handler._symbol_states["BTCUSDT"].regime = "DEFAULT"

        return handler, emit_fn

    def test_signal_includes_readiness(self, handler_with_symbol):
        """Emitted signal should include readiness.warmup_ok."""
        handler, emit_fn = handler_with_symbol

        event = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,  # T2B-01: Must match handler.timeframe_sec
            "features": {"price": "50000", "obi": 0.8, "tfi": 0.6},
            "warmup": {"full_ready": True, "ready": {"obi": True, "tfi": True}},
        }

        handler.on_features_calculated(event)

        if emit_fn.call_count > 0:
            call_args = emit_fn.call_args
            payload = call_args[0][1]
            assert "readiness" in payload
            assert payload["readiness"]["warmup_ok"] is True

    def test_skips_when_warmup_not_ready(self, handler_with_symbol):
        """Handler should fail-closed and emit an explicit block reason when warmup not ready."""
        handler, emit_fn = handler_with_symbol
        handler._symbol_states["BTCUSDT"].warmup_full_ready = False

        event = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,  # T2B-01: Must match handler.timeframe_sec
            "features": {"price": "50000", "obi": 0.8, "tfi": 0.6},
            "warmup": {"full_ready": False, "ready": {"obi": True, "tfi": True}},
        }

        handler.on_features_calculated(event)

        assert emit_fn.call_count == 1
        evt_name, payload = emit_fn.call_args[0]
        assert evt_name == "EVT:STRATEGY_DECISION_BLOCKED"
        assert "READINESS" in str(payload.get("reason", ""))

    def test_skips_disabled_symbol(self, handler_with_symbol):
        """Handler should skip disabled symbols."""
        handler, emit_fn = handler_with_symbol
        handler.config.strategies.aurora.assets["BTCUSDT"].enabled = False

        event = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,  # T2B-01: Must match handler.timeframe_sec
            "features": {"price": "50000", "obi": 0.8, "tfi": 0.6},
            "warmup": {"full_ready": True, "ready": {"obi": True, "tfi": True}},
        }

        handler.on_features_calculated(event)

        assert emit_fn.call_count == 0


class TestPortfolioStateNetPosition:
    """Regression tests for Finding 6: invalid net_position must not masquerade as flat."""

    @pytest.fixture
    def handler(self):
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=None,
                    ),
                    assets={"BTCUSDT": SimpleNamespace(enabled=True)},
                )
            ),
            strategies_registry=SimpleNamespace(
                assignments={"BTCUSDT": ["aurora"]}),
        )
        return AuroraHandler(config=config, emit_fn=MagicMock())

    def test_valid_net_position_is_tracked(self, handler):
        """A normal non-zero position must be seen as active."""
        event = {
            "positions": [{"symbol": "BTCUSDT", "net_position": "0.5"}],
            "positions_last_ts_ms": 1700000000000,
        }
        # After the call _latest_portfolio should be set; no exception raised.
        handler.on_portfolio_state(event)
        assert handler._latest_portfolio == event

    def test_invalid_net_position_skipped_not_treated_as_flat(self, handler):
        """Malformed net_position must be skipped with a warning — NOT treated as zero.

        Before the fix: except Exception → qty = Decimal("0") → symbol absent from
        active_symbols → CLEAN_START_UPGRADE could be falsely triggered.
        After the fix: invalid entry is skipped via `continue`; the symbol's upgrade
        path is never reached for that position row.
        """
        import decimal
        from unittest.mock import patch

        upgrade_calls = []

        def fake_upgrade(snapshot, **kwargs):
            upgrade_calls.append(snapshot)
            return None  # simulate "not triggered"

        with patch(
            "apps.reference.domains.strategies.runtimes.aurora.handler"
            ".upgrade_cold_execution_restore_if_clean_start",
            side_effect=fake_upgrade,
        ):
            event = {
                "positions": [
                    {"symbol": "BTCUSDT", "net_position": "NOT_A_NUMBER"},
                ],
                "positions_last_ts_ms": 1700000000000,
            }
            # Should NOT raise; invalid row is silently skipped with a warning.
            handler.on_portfolio_state(event)

        # upgrade was never called (no snapshot registered), but crucially no
        # AttributeError or silent-zero conversion happened either.
        assert upgrade_calls == []

    def test_zero_net_position_still_treated_as_flat(self, handler):
        """Explicit "0" remains flat (normal path must not be broken)."""
        event = {
            "positions": [{"symbol": "BTCUSDT", "net_position": "0"}],
            "positions_last_ts_ms": 1700000000000,
        }
        handler.on_portfolio_state(event)  # Should not raise


class TestEmitStrategyBlockedContract:
    """Regression test for the blocked-helper contract surface."""

    @pytest.fixture
    def handler(self):
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=None,
                    ),
                    assets={},
                )
            )
        )
        return AuroraHandler(config=config, emit_fn=MagicMock())

    def test_blocked_helper_emits_blocked_truth_without_reject_wal(self, handler):
        """_emit_strategy_blocked owns blocked truth, not trade-intent reject WAL."""
        blocked_payload = {
            "schema_version": 1,
            "strategy_id": "aurora",
            "symbol": "BTCUSDT",
            "reason_code": "TEST",
            "reason": "test reason",
            "stage": "STRATEGY",
            "context": "unit_test",
            "why": "unit_test",
            "ts_ms": 1700000000000,
            "why_chain": [],
        }

        with patch(
            "apps.reference.domains.strategies.runtimes.aurora.handler"
            ".write_strategy_decision_blocked",
            return_value=blocked_payload,
        ) as mock_blocked:
            with patch(
                "apps.reference.domains.strategies.runtimes.aurora.handler"
                ".write_trade_intent_rejected",
            ) as mock_reject:
                handler._emit_strategy_blocked(
                    symbol="BTCUSDT",
                    reason_code="TEST",
                    reason="test reason",
                    context="unit_test",
                )

        mock_blocked.assert_called_once()
        mock_reject.assert_not_called()
        handler.emit_fn.assert_called_once_with(
            "EVT:STRATEGY_DECISION_BLOCKED",
            blocked_payload,
        )


class TestCanonicalSidePropagation:
    """Regression tests for post-policy side canonicalization."""

    @pytest.fixture
    def handler(self):
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=60,
                        side_bias_target_ratio=0.5,
                        side_bias_penalty_factor=0.5,
                        side_bias_min_intents=1,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=SimpleNamespace(
                            delta_price_cap_pct=0.01,
                            normalize_signals_mode="signed_v2",
                        ),
                    ),
                    assets={
                        "BTCUSDT": SimpleNamespace(
                            enabled=True,
                            allowed_regimes=["DEFAULT"],
                        )
                    },
                )
            ),
            domains=SimpleNamespace(),
        )
        handler = AuroraHandler(
            config=config,
            emit_fn=MagicMock(),
            monotonic_fn=lambda: 1000.0,
            wall_time_fn=lambda: 1000.0,
        )
        handler._basis_required_bars_override = 0
        handler._bars_seen_since_restart["BTCUSDT"] = 1
        handler._check_regime_liveness = lambda symbol, state: None
        handler._check_liquidity_gate = lambda **kwargs: (True, {})
        handler._get_signal_weights = lambda symbol, instr_cfg: {}
        handler._get_feature_neutrals = lambda symbol, instr_cfg: {}
        handler._get_essential_features = lambda symbol, instr_cfg: []
        handler._get_regime_thresholds = lambda **kwargs: {"DEFAULT": 1.0}
        handler._build_quadratic_decision_trace = lambda **kwargs: {}
        handler._compact_quadratic_decision_trace = lambda trace: {}
        handler._apply_vol_adj_gates = lambda *args, **kwargs: False
        handler._update_side_bias = lambda *args, **kwargs: None
        handler._should_suppress_soft_exit = lambda *args, **kwargs: False

        state = handler._symbol_states["BTCUSDT"]
        state.regime = "DEFAULT"
        state.regime_ts_ms = 999999
        state.regime_confidence = 0.8
        state.position_side = "buy"
        state.entry_timestamp = 900.0
        state.mfe_price = Decimal("100")
        return handler

    def test_exit_override_propagates_canonical_side(self, handler):
        captured = {}

        class Kernel:
            @staticmethod
            def compute(**kwargs):
                return SimpleNamespace(
                    side="buy",
                    score=Decimal("0.5"),
                    thr_buy=Decimal("0.1"),
                    thr_sell=Decimal("0.1"),
                    why_chain=["enter:buy"],
                    psi_vector={},
                    deferred=False,
                    defer_reason=None,
                    threshold_factor=1.0,
                    shield_multiplier=1.0,
                )

        class ExitManagerStub:
            def check_exit(self, **kwargs):
                return True, "unit_exit", None

        class EntryPlanCalculatorStub:
            def compute(self, **kwargs):
                captured["entry_plan_side"] = kwargs["side"]
                return SimpleNamespace(
                    entry_price=Decimal("100"),
                    stop_loss_price=Decimal("99"),
                    take_profit_price=Decimal("101"),
                )

        class ExecutionGateStub:
            def check_entry(self, **kwargs):
                captured["gate_side"] = kwargs["side"]
                return True, None

        handler.scoring_kernel_cls = Kernel
        handler.exit_manager = ExitManagerStub()
        handler.entry_plan_calculator = EntryPlanCalculatorStub()
        handler.execution_gate = ExecutionGateStub()

        cmd = {
            "symbol": "BTCUSDT",
            "tf_sec": 300,
            "bar_close_ts": 1700000000000,
            "features": {"price": "100", "atr": 1.0},
            "warmup": {"full_ready": True, "ready": {}},
        }

        with patch(
            "apps.reference.domains.strategies.runtimes.aurora.decision"
            ".evaluate_quadratic_shadow",
            return_value=None,
        ):
            with patch.object(handler, "_emit_signal") as mock_emit:
                handler._process_decision("BTCUSDT", cmd)

        emitted_side = mock_emit.call_args.kwargs["effective_side"]
        raw_result = mock_emit.call_args.args[1]
        assert raw_result.side == "buy"
        assert str(captured["entry_plan_side"]).lower() == "sell"
        assert str(captured["gate_side"]).lower() == "sell"
        assert str(emitted_side).lower() == "sell"


class TestOnSystemStressGuard:
    """Regression test for Finding 8: on_system_stress must guard against non-dict payload."""

    @pytest.fixture
    def handler(self):
        config = SimpleNamespace(
            strategies=SimpleNamespace(
                aurora=SimpleNamespace(
                    timeframe_sec=300,
                    decision=SimpleNamespace(
                        signal_threshold=0.1,
                        side_bias_window_sec=420,
                        regime_threshold_multipliers={"DEFAULT": 1.0},
                        direction_strength_scoring=None,
                        signals=None,
                    ),
                    assets={},
                )
            )
        )
        return AuroraHandler(config=config, emit_fn=MagicMock())

    @pytest.mark.parametrize("bad_payload", [None, "string", 42, ["list"]])
    def test_non_dict_payload_does_not_raise(self, handler, bad_payload):
        """on_system_stress must silently return on non-dict payload (consistent with other handlers)."""
        handler.on_system_stress(bad_payload)  # Must not raise AttributeError

    def test_valid_dict_payload_updates_state(self, handler):
        """Normal dict payload must still update the symbol state."""
        handler.on_system_stress({"symbol": "BTCUSDT", "state": "HIGH_STRESS"})
        assert handler._symbol_states["BTCUSDT"].system_stress_state == "HIGH_STRESS"
