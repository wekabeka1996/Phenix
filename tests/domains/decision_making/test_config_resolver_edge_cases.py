"""
Phase-4 coverage: DMConfigResolver — edge cases for strategy arbitration,
symbol lookup, and fallback chain behavior.

Current coverage of core/config_resolver.py: 52% (81 miss lines).
Target: cover arbitration paths (multi-strategy, rank conflict, window logic),
missing instrument fallbacks, and is_strategy_assigned edge cases.
"""
from typing import Any, Dict, Tuple
from unittest.mock import MagicMock, patch
import logging
import pytest

from apps.reference.domains.decision_making.core.config_resolver import DMConfigResolver
from apps.reference.config_contract import ConfigContractError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry(
    assignments: Dict[str, list] | None = None,
    mode: str = "priority",
    priority: Dict[str, int] | None = None,
    window_ms: int = 200,
    rejected_why_prefix: str = "ARB_DROPPED",
):
    reg = MagicMock()
    reg.assignments = assignments or {}
    reg.arbitration.mode = mode
    reg.arbitration.priority = priority or {}
    reg.arbitration.window_ms = window_ms
    reg.arbitration.logging.rejected_why_prefix = rejected_why_prefix
    return reg


def _make_config(
    btcusdt_cooldown: int | None = None,
    btcusdt_signal_threshold: float = 0.15,
    flip_enabled: bool = True,
    flip_hysteresis: float = 1.2,
    tick_size: float | None = 0.1,
    step_size: float | None = 0.001,
):
    cfg = MagicMock()
    # Aurora decision global config
    cfg.strategies.aurora.decision.signal_threshold = btcusdt_signal_threshold
    cfg.strategies.aurora.decision.regime_threshold_multipliers = {}
    # Assets
    btc_asset = MagicMock()
    btc_asset.cooldown_sec = btcusdt_cooldown
    btc_asset.signal_threshold.enabled = False
    btc_asset.signal_threshold.value = None
    btc_asset.regime_thresholds = None
    cfg.strategies.aurora.assets = {"BTCUSDT": btc_asset}
    # Domains
    cfg.domains.decision_making.qos.symbol_cooldown_sec = 5
    # Instruments
    instr = MagicMock()
    instr.flip.enabled = flip_enabled
    instr.flip.hysteresis_mult = flip_hysteresis
    instr.tick_size = tick_size
    instr.step_size = step_size
    cfg.instruments = {"BTCUSDT": instr}
    return cfg


def _make_resolver(
    registry=None,
    config=None,
    flip_global_enabled: bool = True,
) -> DMConfigResolver:
    return DMConfigResolver(
        config=config or _make_config(),
        strategies_registry=registry,
        arb_signal_buffer={},
        arb_window_winner={},
        flip_global_enabled=flip_global_enabled,
        logger=logging.getLogger("test"),
    )


# ---------------------------------------------------------------------------
# is_strategy_assigned
# ---------------------------------------------------------------------------

class TestIsStrategyAssigned:
    def test_no_registry_aurora_is_always_assigned(self):
        resolver = _make_resolver(registry=None)
        assert resolver.is_strategy_assigned("BTCUSDT", "aurora") is True

    def test_no_registry_non_aurora_not_assigned(self):
        resolver = _make_resolver(registry=None)
        assert resolver.is_strategy_assigned("BTCUSDT", "md_amr") is False

    def test_registry_symbol_assigned(self):
        reg = _make_registry(assignments={"BTCUSDT": ["aurora"]})
        resolver = _make_resolver(registry=reg)
        assert resolver.is_strategy_assigned("BTCUSDT", "aurora") is True

    def test_registry_symbol_not_assigned(self):
        reg = _make_registry(assignments={"ETHUSDT": ["aurora"]})
        resolver = _make_resolver(registry=reg)
        assert resolver.is_strategy_assigned("BTCUSDT", "aurora") is False


# ---------------------------------------------------------------------------
# check_strategy_arbitration — no registry (passthrough)
# ---------------------------------------------------------------------------

class TestArbitrationNoRegistry:
    def test_no_registry_always_allowed(self):
        resolver = _make_resolver(registry=None)
        result = resolver.check_strategy_arbitration("BTCUSDT", "aurora")
        assert result["allowed"] is True

    def test_symbol_not_in_registry_blocks(self):
        reg = _make_registry(assignments={})
        resolver = _make_resolver(registry=reg)
        result = resolver.check_strategy_arbitration("BTCUSDT", "aurora")
        assert result["allowed"] is False
        assert "symbol_not_in_registry" in result["reason"]

    def test_strategy_not_in_assignments_blocks(self):
        reg = _make_registry(assignments={"BTCUSDT": ["md_amr"]})
        resolver = _make_resolver(registry=reg)
        result = resolver.check_strategy_arbitration("BTCUSDT", "aurora")
        assert result["allowed"] is False
        assert "strategy_not_assigned" in result["reason"]

    def test_single_assignment_always_allowed(self):
        reg = _make_registry(assignments={"BTCUSDT": ["aurora"]})
        resolver = _make_resolver(registry=reg)
        result = resolver.check_strategy_arbitration("BTCUSDT", "aurora")
        assert result["allowed"] is True


# ---------------------------------------------------------------------------
# check_strategy_arbitration — multi-strategy priority mode
# ---------------------------------------------------------------------------

class TestArbitrationPriorityMode:
    def test_unknown_mode_blocks(self):
        reg = _make_registry(
            assignments={"BTCUSDT": ["aurora", "md_amr"]},
            mode="round_robin",  # unknown mode
            priority={"aurora": 1, "md_amr": 2},
        )
        resolver = _make_resolver(registry=reg)
        result = resolver.check_strategy_arbitration("BTCUSDT", "aurora")
        assert result["allowed"] is False
        assert "unknown_mode" in result["reason"]

    def test_missing_rank_blocks(self):
        """Strategy in assignments but missing from priority → fail-closed."""
        reg = _make_registry(
            assignments={"BTCUSDT": ["aurora", "md_amr"]},
            mode="priority",
            priority={"md_amr": 2},  # aurora rank is missing
        )
        resolver = _make_resolver(registry=reg)
        result = resolver.check_strategy_arbitration("BTCUSDT", "aurora")
        assert result["allowed"] is False
        assert "missing_priority" in result["reason"]

    def test_other_strategy_missing_priority_blocks(self):
        """A peer strategy missing its rank → fail-closed."""
        reg = _make_registry(
            assignments={"BTCUSDT": ["aurora", "md_amr"]},
            mode="priority",
            priority={"aurora": 1},  # md_amr has no rank
        )
        resolver = _make_resolver(registry=reg)
        result = resolver.check_strategy_arbitration("BTCUSDT", "aurora")
        assert result["allowed"] is False

    def test_no_ts_skips_window_check(self):
        """When ts_ms=None, no window comparison; strategy is allowed."""
        reg = _make_registry(
            assignments={"BTCUSDT": ["aurora", "md_amr"]},
            mode="priority",
            priority={"aurora": 1, "md_amr": 2},
            window_ms=200,
        )
        resolver = _make_resolver(registry=reg)
        result = resolver.check_strategy_arbitration("BTCUSDT", "aurora", ts_ms=None)
        assert result["allowed"] is True

    def test_higher_priority_overrides_lower_in_window(self):
        """aurora(rank=1) overrides md_amr(rank=2) within window."""
        reg = _make_registry(
            assignments={"BTCUSDT": ["aurora", "md_amr"]},
            mode="priority",
            priority={"aurora": 1, "md_amr": 2},
            window_ms=200,
        )
        arb_buf = {"BTCUSDT": (1_000_000, "md_amr", 2)}
        resolver = DMConfigResolver(
            config=_make_config(),
            strategies_registry=reg,
            arb_signal_buffer=arb_buf,
            arb_window_winner={},
            flip_global_enabled=True,
            logger=logging.getLogger("test"),
        )
        # aurora at ts+50ms (within 200ms window)
        result = resolver.check_strategy_arbitration(
            "BTCUSDT", "aurora", ts_ms=1_000_050, commit=False
        )
        assert result["allowed"] is True

    def test_lower_priority_dropped_in_window(self):
        """md_amr(rank=2) dropped when aurora(rank=1) already claimed window."""
        reg = _make_registry(
            assignments={"BTCUSDT": ["aurora", "md_amr"]},
            mode="priority",
            priority={"aurora": 1, "md_amr": 2},
            window_ms=200,
        )
        arb_buf = {"BTCUSDT": (1_000_000, "aurora", 1)}
        resolver = DMConfigResolver(
            config=_make_config(),
            strategies_registry=reg,
            arb_signal_buffer=arb_buf,
            arb_window_winner={},
            flip_global_enabled=True,
            logger=logging.getLogger("test"),
        )
        result = resolver.check_strategy_arbitration(
            "BTCUSDT", "md_amr", ts_ms=1_000_050, commit=False
        )
        assert result["allowed"] is False
        assert "lower_priority" in result["reason"]

    def test_commit_updates_buffer(self):
        reg = _make_registry(
            assignments={"BTCUSDT": ["aurora", "md_amr"]},
            mode="priority",
            priority={"aurora": 1, "md_amr": 2},
            window_ms=200,
        )
        resolver = _make_resolver(registry=reg)
        result = resolver.check_strategy_arbitration(
            "BTCUSDT", "aurora", ts_ms=1_000_000, commit=True
        )
        assert result["allowed"] is True
        assert "BTCUSDT" in resolver._arb_signal_buffer

    def test_invalid_window_ms_blocks(self):
        reg = _make_registry(
            assignments={"BTCUSDT": ["aurora", "md_amr"]},
            mode="priority",
            priority={"aurora": 1, "md_amr": 2},
            window_ms=0,
        )
        resolver = _make_resolver(registry=reg)
        result = resolver.check_strategy_arbitration("BTCUSDT", "aurora", ts_ms=1_000_000)
        assert result["allowed"] is False
        assert "invalid_window_ms" in result["reason"]


# ---------------------------------------------------------------------------
# get_symbol_cooldown
# ---------------------------------------------------------------------------

class TestGetSymbolCooldown:
    def test_per_instrument_override_returned(self):
        cfg = _make_config(btcusdt_cooldown=30)
        cfg.strategies.aurora.assets["BTCUSDT"].cooldown_sec = 30
        resolver = _make_resolver(config=cfg)
        assert resolver.get_symbol_cooldown("BTCUSDT", "aurora") == 30

    def test_global_default_returned_when_no_override(self):
        cfg = _make_config(btcusdt_cooldown=None)
        cfg.strategies.aurora.assets["BTCUSDT"].cooldown_sec = None
        resolver = _make_resolver(config=cfg)
        assert resolver.get_symbol_cooldown("BTCUSDT", "aurora") == 5  # from qos config

    def test_non_aurora_strategy_skips_instrument_lookup(self):
        resolver = _make_resolver()
        # md_amr skips instrument config, returns default
        result = resolver.get_symbol_cooldown("BTCUSDT", "md_amr")
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# get_flip_config
# ---------------------------------------------------------------------------

class TestGetFlipConfig:
    def test_global_disable_returns_false_immediately(self):
        resolver = _make_resolver(flip_global_enabled=False)
        enabled, mult = resolver.get_flip_config("BTCUSDT")
        assert enabled is False

    def test_missing_instrument_raises(self):
        cfg = _make_config()
        cfg.instruments = {}  # BTCUSDT missing
        resolver = _make_resolver(config=cfg)
        with pytest.raises(ConfigContractError):
            resolver.get_flip_config("BTCUSDT")

    def test_missing_flip_section_raises(self):
        cfg = _make_config()
        cfg.instruments["BTCUSDT"].flip = None
        resolver = _make_resolver(config=cfg)
        with pytest.raises(ConfigContractError):
            resolver.get_flip_config("BTCUSDT")

    def test_valid_flip_config_returned(self):
        resolver = _make_resolver()
        enabled, mult = resolver.get_flip_config("BTCUSDT")
        assert enabled is True
        assert mult >= 1.0


# ---------------------------------------------------------------------------
# get_precision
# ---------------------------------------------------------------------------

class TestGetPrecision:
    def test_missing_symbol_raises(self):
        cfg = _make_config()
        cfg.instruments = {}
        resolver = _make_resolver(config=cfg)
        with pytest.raises(ValueError, match="Missing instrument config"):
            resolver.get_precision("ETHUSDT")

    def test_valid_precision_returned(self):
        resolver = _make_resolver()
        tick, step = resolver.get_precision("BTCUSDT")
        assert isinstance(tick, float)
        assert isinstance(step, float)

    def test_missing_tick_size_raises(self):
        from apps.reference.utils.accessors import aget
        cfg = _make_config(tick_size=None, step_size=0.001)
        resolver = _make_resolver(config=cfg)
        # aget returns None for tick_size → should raise
        with pytest.raises(ValueError, match="Missing precision"):
            resolver.get_precision("BTCUSDT")


# ---------------------------------------------------------------------------
# get_aurora_instrument_cfg
# ---------------------------------------------------------------------------

class TestGetAuroraInstrumentCfg:
    def test_returns_none_when_no_config(self):
        resolver = DMConfigResolver(
            config=None,  # explicitly None — falsy guard triggers
            strategies_registry=None,
            arb_signal_buffer={},
            arb_window_winner={},
            flip_global_enabled=True,
            logger=logging.getLogger("test"),
        )
        result = resolver.get_aurora_instrument_cfg("BTCUSDT")
        assert result is None

    def test_returns_none_when_aurora_absent(self):
        cfg = MagicMock()
        cfg.strategies = MagicMock(spec=[])  # no 'aurora' attribute
        resolver = DMConfigResolver(
            config=cfg,
            strategies_registry=None,
            arb_signal_buffer={},
            arb_window_winner={},
            flip_global_enabled=True,
            logger=logging.getLogger("test"),
        )
        result = resolver.get_aurora_instrument_cfg("BTCUSDT")
        assert result is None

    def test_returns_instrument_config_for_known_symbol(self):
        resolver = _make_resolver()
        result = resolver.get_aurora_instrument_cfg("BTCUSDT")
        assert result is not None

    def test_returns_none_for_unknown_symbol(self):
        resolver = _make_resolver()
        result = resolver.get_aurora_instrument_cfg("UNKNOWN")
        assert result is None
