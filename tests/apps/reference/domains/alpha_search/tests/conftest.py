"""
Shared fixtures for Alpha Search domain tests.
================================================

Provides factory functions, mock objects, and reusable fixtures
for all test tiers (T1-T4 + cross-cutting).
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
import yaml


# ---------------------------------------------------------------------------
# Snapshot / Contract Factories
# ---------------------------------------------------------------------------

def make_snapshot(
    *,
    symbol: str = "BTCUSDT",
    price: float = 96000.0,
    ts_ms: int = 1740000000000,
    bar_close_ts: int = 1740000000000,
    tf_sec: int = 300,
    features: Optional[Dict[str, Any]] = None,
    regime: str = "DEFAULT",
    warmup_status: Optional[Dict[str, bool]] = None,
) -> Dict[str, Any]:
    """Return a raw dict that validates as AlphaInputV1."""
    return {
        "ts_ms": ts_ms,
        "symbol": symbol,
        "tf_sec": tf_sec,
        "bar_close_ts": bar_close_ts,
        "price": price,
        "features": features or _base_features_full(),
        "regime": regime,
        "warmup_status": warmup_status or {},
    }


def make_result(
    *,
    scenario_id: str = "S01_AURORA_BASELINE",
    strategy_type: str = "aurora",
    score: float = 0.15,
    confidence: float = 0.8,
    threshold: float = 0.155,
    side: str = "NEUTRAL",
    provider_id: str = "aurora",
    model_name: str = "aurora_adapter",
) -> Dict[str, Any]:
    """Return a dict matching AlphaShadowResultV1 shape."""
    return {
        "scenario_id": scenario_id,
        "strategy_type": strategy_type,
        "ts_ms": 1740000000000,
        "symbol": "BTCUSDT",
        "score": score,
        "confidence": confidence,
        "threshold": threshold,
        "side": side,
        "provider_id": provider_id,
        "model_name": model_name,
        "why": ["test"],
        "features_used": ["obi", "delta_price"],
        "shadow": True,
        "regime": "DEFAULT",
    }


# ---------------------------------------------------------------------------
# Feature dict factories
# ---------------------------------------------------------------------------

def _base_features_aurora() -> Dict[str, Any]:
    """Minimal features for Aurora scoring."""
    return {
        "obi": 0.12,
        "delta_price": 0.003,
        "macro_resid": 0.05,
        "tfi": 0.4,
        "ema_bias": 0.002,
        "volume_spike": 1.3,
        "volatility_state": 0.8,
        "depth_imbalance": 0.15,
        "macro_sync": True,
        "close": 96000.0,
    }


def _base_features_mr() -> Dict[str, Any]:
    """Minimal features for MeanReversion scoring."""
    return {
        "bb_position": 0.3,
        "bb_width": 0.02,
        "rsi_14": 45.0,
        "price_sma_20_deviation": -0.005,
        "stoch_k": 35.0,
        "stoch_d": 38.0,
        "volume_ratio": 1.1,
        "close": 96000.0,
    }


def _base_features_full() -> Dict[str, Any]:
    """Union of all strategy features."""
    d = _base_features_aurora()
    d.update(_base_features_mr())
    # Ensemble / momentum / volatility extras
    d.update({
        "momentum_5": 0.002,
        "momentum_60": 0.005,
        "momentum_1440": 0.01,
        "volume_momentum": 1.1,
        "macd_histogram": 0.0005,
        "atr_pct": 0.015,
        "realized_volatility": 0.012,
        "range_pct": 0.018,
        "price": 96000.0,
    })
    return d


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_features_aurora():
    return _base_features_aurora()


@pytest.fixture
def base_features_mr():
    return _base_features_mr()


@pytest.fixture
def base_features_full():
    return _base_features_full()


@pytest.fixture
def snapshot_dict():
    """A valid snapshot as raw dict."""
    return make_snapshot()


@pytest.fixture
def tmp_session_dir(tmp_path):
    """Temporary session directory with aggregate subdir."""
    session = tmp_path / "session_test"
    (session / "aggregate").mkdir(parents=True, exist_ok=True)
    return session


@pytest.fixture
def mock_bus():
    """A real LocalBus for isolated testing."""
    from apps.reference.orchestrator.utils_event_bus import LocalBus
    return LocalBus()


@pytest.fixture
def project_root():
    """Project root (5 levels up from runtime/launcher.py)."""
    # Use the actual project root
    return Path(__file__).resolve().parents[4]


@pytest.fixture
def yaml_config_dir(tmp_path, project_root):
    """
    Create a temp directory with minimal valid YAML configs
    for full_config mode testing.
    """
    cfg_dir = tmp_path / "scenario_configs" / "S_TEST"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    # alpha_search.yaml
    alpha_search_cfg = {
        "enabled": True,
        "shadow_mode": True,
        "triggers": {
            "feature_event": "EVT:FEATURES_CALCULATED",
            "decision_event": "CMD:PROCESS_STRATEGY",
            "emit_event": "EVT:ALPHA_SCORE_CALCULATED",
        },
        "cache": {
            "max_per_symbol": 10,
            "require_same_bar_close_ts": False,
        },
        "providers": {
            "aurora": {
                "enabled": True,
                "symbols": ["BTCUSDT"],
                "threshold": 0.155,
                "fail_closed": True,
                "adapter": {
                    "scoring_version": "v2",
                    "essential_features": ["obi", "delta_price", "macro_resid"],
                },
            },
        },
        "virtual_trader": {
            "enabled": False,
            "per_provider": True,
            "max_positions_per_symbol": 1,
            "notional_size": 1000,
            "exit": {"max_bars": 12, "max_hold_sec": 3600},
        },
        "legacy": {},
    }
    with open(cfg_dir / "alpha_search.yaml", "w") as f:
        yaml.dump(alpha_search_cfg, f)

    # alpha_search_system.yaml (empty = defaults)
    with open(cfg_dir / "alpha_search_system.yaml", "w") as f:
        yaml.dump({}, f)

    return cfg_dir


@pytest.fixture
def aurora_override_scenario_spec():
    """A ScenarioSpec for aurora override mode."""
    from apps.reference.domains.alpha_search.runtime.contracts import ScenarioSpec
    return ScenarioSpec(
        scenario_id="S_TEST_AURORA",
        enabled=True,
        strategy_type="aurora",
        config_mode="override",
        base_refs={
            "aurora": "config/aurora/strategies/aurora.yaml",
            "alpha_search": "config/alpha_search.yaml",
        },
        overrides={},
    )


@pytest.fixture
def runtime_config_sequential():
    """RuntimeConfig with sequential execution (for debugging tests)."""
    from apps.reference.domains.alpha_search.runtime.contracts import RuntimeConfig
    return RuntimeConfig(
        parallelism="sequential",
        max_workers=1,
        scenario_timeout_sec=5.0,
        health_heartbeat_sec=30.0,
    )


@pytest.fixture
def runtime_config_parallel():
    """RuntimeConfig with thread_pool execution."""
    from apps.reference.domains.alpha_search.runtime.contracts import RuntimeConfig
    return RuntimeConfig(
        parallelism="thread_pool",
        max_workers=4,
        scenario_timeout_sec=5.0,
        health_heartbeat_sec=30.0,
    )


def write_jsonl_file(path: Path, records: List[Dict[str, Any]]) -> Path:
    """Write a list of dicts as JSONL file. Returns path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    return path
