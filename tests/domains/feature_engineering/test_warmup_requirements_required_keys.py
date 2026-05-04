from __future__ import annotations

from types import SimpleNamespace

from apps.reference.domains.feature_engineering.types import FeatureEngineeringConfig


def _mk_cfg(*, required_by_symbol: dict[str, list[str]] | None = None, required_global: list[str] | None = None):
    cfg = FeatureEngineeringConfig.__new__(FeatureEngineeringConfig)
    cfg._cfg = SimpleNamespace(
        readiness_registry=SimpleNamespace(
            declared_keys=[
                "obi",
                "tfi",
                "delta_price",
                "depth_imbalance",
                "liquidity_kappa",
                "spread_bps",
                "macro_sync",
                "large_trade_imbalance",
            ]
        ),
        warmup=SimpleNamespace(
            enforcement_mode="fail_fast",
            validate_essential_subset=True,
            check_full_ready_invariant=True,
            required_ready_keys=required_global,
            required_ready_keys_by_symbol=required_by_symbol,
        ),
        absorption=SimpleNamespace(mode="disabled"),
        macro_resid=SimpleNamespace(enabled=False),
        macro_sync=SimpleNamespace(enabled=True),
    )
    return cfg


def test_optional_not_ready_does_not_block_full_ready_when_required_ready():
    fe_cfg = _mk_cfg(required_by_symbol={"DOGEUSDT": ["spread_bps"]})

    ready_map = {
        "obi": True,
        "tfi": True,
        "delta_price": True,
        "depth_imbalance": True,
        "liquidity_kappa": True,
        "spread_bps": True,
        # Optional under DOGE override:
        "macro_sync": False,
        "large_trade_imbalance": False,
    }

    assert fe_cfg.compute_warmup_full_ready_for_symbol(symbol="DOGEUSDT", ready_map=ready_map) is True


def test_required_not_ready_blocks_full_ready_fail_closed():
    fe_cfg = _mk_cfg(required_by_symbol={"DOGEUSDT": ["spread_bps"]})

    ready_map = {
        "obi": True,
        "tfi": True,
        "delta_price": True,
        "depth_imbalance": True,
        "liquidity_kappa": True,
        "spread_bps": False,
        "macro_sync": True,
        "large_trade_imbalance": True,
    }

    assert fe_cfg.compute_warmup_full_ready_for_symbol(symbol="DOGEUSDT", ready_map=ready_map) is False


def test_global_required_ready_keys_apply_when_no_symbol_override():
    fe_cfg = _mk_cfg(required_by_symbol=None, required_global=["spread_bps", "liquidity_kappa"])

    ready_map = {
        "obi": False,
        "tfi": False,
        "delta_price": False,
        "depth_imbalance": False,
        "liquidity_kappa": True,
        "spread_bps": True,
        "macro_sync": False,
        "large_trade_imbalance": False,
    }

    assert fe_cfg.compute_warmup_full_ready_for_symbol(symbol="XRPUSDT", ready_map=ready_map) is True
