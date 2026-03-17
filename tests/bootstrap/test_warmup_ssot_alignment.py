"""
WARMUP-SSOT: Alignment and drift-prevention tests.

Verifies:
1. startup_warmup regime_basis_candles >= regime_detector_required_bars(config)
2. basis_import_buffer from config is honoured
3. No hardcoded literal `320` in startup_warmup.py or main.py (drift prevention)
4. regime_detector_required_bars raises on missing model config (fail-closed)
"""
import ast
import inspect
from types import SimpleNamespace

import pytest

from apps.reference.bootstrap.startup_warmup import resolve_feature_engineering_backfill_plan
from apps.reference.contracts.strategy_compatibility_matrix import regime_detector_required_bars


def _regime_config(sma_long: int = 192, atr_period: int = 14, atr_sma_length: int = 288, buffer: int = 20) -> SimpleNamespace:
    """Minimal config fixture with regime models and basis_import_buffer."""
    return SimpleNamespace(
        basis_import_buffer=buffer,
        regime=SimpleNamespace(
            models=SimpleNamespace(
                sma_trend=SimpleNamespace(sma_long_period=sma_long),
                volatility=SimpleNamespace(
                    atr_period=atr_period, atr_sma_length=atr_sma_length),
            )
        ),
        domains=SimpleNamespace(
            feature_engineering=SimpleNamespace(
                pillars=SimpleNamespace(
                    enabled=True,
                    backfill=SimpleNamespace(
                        enabled=True,
                        d1_candles=200,
                        h4_candles=100,
                        m15_candles=50,
                    ),
                )
            )
        ),
        strategies_registry=SimpleNamespace(
            assignments={
                "BTCUSDT": ["aurora"],
                "ETHUSDT": ["md_amr"],
            }
        ),
        instruments={
            "BTCUSDT": object(),
            "ETHUSDT": object(),
        },
    )


# ── A: canonical alignment ────────────────────────────────────────────────────

def test_startup_warmup_plan_ge_regime_required() -> None:
    """FeatureEngineeringBackfillPlan.regime_basis_candles must be
    at least regime_detector_required_bars(config)."""
    cfg = _regime_config()
    plan = resolve_feature_engineering_backfill_plan(cfg)
    canonical = regime_detector_required_bars(cfg)
    assert plan.regime_basis_candles >= canonical, (
        f"Startup warmup plan {plan.regime_basis_candles} < canonical {canonical}: "
        "hydration would under-seed the RegimeDetector."
    )


def test_startup_warmup_plan_equals_canonical_plus_buffer() -> None:
    """regime_basis_candles == regime_detector_required_bars(config) + basis_import_buffer."""
    cfg = _regime_config(buffer=20)
    plan = resolve_feature_engineering_backfill_plan(cfg)
    canonical = regime_detector_required_bars(cfg)
    assert plan.regime_basis_candles == canonical + 20


def test_startup_warmup_plan_uses_config_buffer() -> None:
    """If basis_import_buffer is set to 42 in config, regime_basis_candles must reflect it."""
    cfg = _regime_config(buffer=42)
    plan = resolve_feature_engineering_backfill_plan(cfg)
    canonical = regime_detector_required_bars(cfg)
    assert plan.regime_basis_candles == canonical + 42, (
        f"Expected {canonical + 42}, got {plan.regime_basis_candles}: "
        "basis_import_buffer from config is not being used."
    )


def test_startup_warmup_plan_adapts_when_sma_long_changes() -> None:
    """If sma_long_period is the dominant term, regime_basis_candles must track it."""
    cfg_large_sma = _regime_config(
        sma_long=400, atr_period=14, atr_sma_length=288, buffer=0)
    plan = resolve_feature_engineering_backfill_plan(cfg_large_sma)
    assert plan.regime_basis_candles == 400, (
        "large sma_long_period should dominate regime_basis_candles"
    )


# ── B: regime_detector_required_bars formula correctness ─────────────────────

def test_regime_detector_required_bars_formula() -> None:
    cfg = _regime_config(sma_long=192, atr_period=14, atr_sma_length=288)
    result = regime_detector_required_bars(cfg)
    assert result == 301  # max(192, 14+288-1) = max(192, 301) = 301


def test_regime_detector_required_bars_sma_dominant() -> None:
    cfg = _regime_config(sma_long=500, atr_period=14, atr_sma_length=200)
    result = regime_detector_required_bars(cfg)
    assert result == 500  # max(500, 213) = 500


def test_regime_detector_required_bars_raises_if_models_missing() -> None:
    """If regime model config is unreachable, must raise ValueError (fail-closed)."""
    cfg = SimpleNamespace(
        basis_import_buffer=20,
        regime=SimpleNamespace(models=None),  # models is None
        instruments={},
        strategies_registry=None,
        domains=SimpleNamespace(feature_engineering=SimpleNamespace(
            pillars=SimpleNamespace(enabled=False, backfill=None))),
    )
    with pytest.raises(ValueError, match="regime.models.sma_trend"):
        regime_detector_required_bars(cfg)


def test_regime_detector_required_bars_raises_if_volatility_missing() -> None:
    """If volatility model is missing, must raise ValueError."""
    cfg = SimpleNamespace(
        basis_import_buffer=20,
        regime=SimpleNamespace(
            models=SimpleNamespace(
                sma_trend=SimpleNamespace(sma_long_period=192),
                volatility=None,  # missing
            )
        ),
        instruments={},
        strategies_registry=None,
        domains=SimpleNamespace(feature_engineering=SimpleNamespace(
            pillars=SimpleNamespace(enabled=False, backfill=None))),
    )
    with pytest.raises(ValueError, match="regime.models.sma_trend"):
        regime_detector_required_bars(cfg)


# ── C: drift prevention — no hardcoded 320 ───────────────────────────────────

def test_no_hardcoded_320_in_startup_warmup() -> None:
    """Drift prevention: no literal 320 in startup_warmup.py.
    If this test fails, hardcoded `320` was re-introduced — use regime_detector_required_bars()."""
    import apps.reference.bootstrap.startup_warmup as module
    source = inspect.getsource(module)
    tree = ast.parse(source)
    literals_320 = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and n.value == 320
    ]
    assert not literals_320, (
        f"Hardcoded literal 320 found in startup_warmup.py. "
        "Use regime_detector_required_bars(config) + basis_import_buffer instead."
    )


def test_no_hardcoded_320_in_main() -> None:
    """Drift prevention: no literal 320 in main.py legacy regime-backfill path.
    If this test fails, hardcoded `320` was re-introduced."""
    import apps.reference.main as module
    source = inspect.getsource(module)
    tree = ast.parse(source)
    literals_320 = [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and n.value == 320
    ]
    assert not literals_320, (
        f"Hardcoded literal 320 found in main.py. "
        "Use regime_detector_required_bars(config) + basis_import_buffer instead."
    )
