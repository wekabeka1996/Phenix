from __future__ import annotations

from pathlib import Path

import yaml


def test_depth_imbalance_contract_global_defaults_present_and_validated() -> None:
    """C3: Instrument config presence test.

    Contract:
    - instruments.yaml is SSOT for precision/execution/sizing only (no depth_imbalance per-symbol params).
    - depth_imbalance params are global and must be validated by Pydantic models via ConfigLoader.
    """

    from apps.reference.config_loader import ConfigLoader

    repo_root = Path(__file__).resolve().parents[2]
    config_dir = repo_root / "config" / "aurora"

    # Load full config through canonical loader (Pydantic validation).
    cfg = ConfigLoader(config_dir=config_dir).load_config()

    # Active instruments are defined by instruments.yaml.
    instruments_yaml = config_dir / "instruments.yaml"
    raw = yaml.safe_load(instruments_yaml.read_text(encoding="utf-8"))
    instruments = (raw or {}).get("instruments") or {}
    assert isinstance(instruments, dict)
    assert instruments, "instruments.yaml must define at least 1 instrument"

    # 1) Per-symbol depth_imbalance params are NOT part of instruments contract.
    for symbol, spec in instruments.items():
        assert isinstance(spec, dict)
        assert "depth_imbalance" not in spec, f"{symbol}: instruments.yaml must not contain depth_imbalance params"

    # 2) Global defaults must exist and be validated (no runtime get(..., default)).
    fe = cfg.domains.feature_engineering
    assert fe.liquidity.depth_half > 0
    assert isinstance(fe.depth_imbalance.use_laplace_smoothing, bool)
