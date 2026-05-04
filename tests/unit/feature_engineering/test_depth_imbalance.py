import decimal
from pathlib import Path


from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.feature_engineering.calculation_engine import FeatureCalculationEngine
from apps.reference.domains.feature_engineering.types import FeatureEngineeringConfig


def _load_prod_config():
    repo_root = Path(__file__).resolve().parents[3]
    return ConfigLoader(config_dir=repo_root / "config" / "aurora").load_config()


def test_depth_imbalance_monotonic_and_neutral_with_smoothing():
    cfg = _load_prod_config()
    fe_cfg = FeatureEngineeringConfig(cfg)
    engine = FeatureCalculationEngine(fe_cfg)

    # balanced book -> neutral
    phi_eq = engine.compute_depth_imbalance(decimal.Decimal("1000"), decimal.Decimal("1000"))
    assert phi_eq == decimal.Decimal("0.5")

    # ask dominance -> bearish -> phi > 0.5
    phi_ask = engine.compute_depth_imbalance(decimal.Decimal("100"), decimal.Decimal("10000"))
    assert phi_ask > decimal.Decimal("0.5")

    # bid dominance -> bullish -> phi < 0.5
    phi_bid = engine.compute_depth_imbalance(decimal.Decimal("10000"), decimal.Decimal("100"))
    assert phi_bid < decimal.Decimal("0.5")


def test_depth_imbalance_no_smoothing_handles_zero_denominator():
    cfg = _load_prod_config()
    # Toggle config flag and verify it is honored.
    cfg.domains.feature_engineering.depth_imbalance.use_laplace_smoothing = False

    fe_cfg = FeatureEngineeringConfig(cfg)
    engine = FeatureCalculationEngine(fe_cfg)

    # 0/0 -> neutral
    phi_00 = engine.compute_depth_imbalance(decimal.Decimal("0"), decimal.Decimal("0"))
    assert phi_00 == fe_cfg.neutral_value

    # ask>0, bid=0 -> extreme bearish
    phi_ask_only = engine.compute_depth_imbalance(decimal.Decimal("0"), decimal.Decimal("10"))
    assert phi_ask_only == decimal.Decimal("1")

    # bid>0, ask=0 -> extreme bullish (phi close to 0)
    phi_bid_only = engine.compute_depth_imbalance(decimal.Decimal("10"), decimal.Decimal("0"))
    assert phi_bid_only == decimal.Decimal("0")
