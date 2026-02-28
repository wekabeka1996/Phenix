#!/usr/bin/env python3
"""
Task 3: Real YAML Loading Test

Loads the real project YAML config via ConfigLoader and asserts that critical
paths map correctly to strict Pydantic models (no dict fallbacks, no silent defaults).
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    from apps.reference.config_loader import ConfigLoader
    from apps.reference.config_models import LeverageConfig

    try:
        config_dir = repo_root / "config" / "aurora"
        cfg = ConfigLoader(config_dir=config_dir).load_config()

        # Fallback config must exist and be typed
        fb = cfg.domains.execution_position.fallback
        assert fb.policy in {"fail_closed", "reduce_exposure"}
        assert fb.risk_reduction_pct is not None

        # Aurora: BTC leverage config must exist and be typed
        aurora = cfg.strategies.aurora
        assert aurora is not None, "strategies.aurora missing (profile not loaded)"
        btc = aurora.assets["BTCUSDT"]
        assert btc.leverage is not None, "aurora.assets.BTCUSDT.leverage missing"
        assert isinstance(btc.leverage, LeverageConfig), "Aurora BTC leverage must be LeverageConfig"
        assert btc.leverage.target == 20

        # Mean Reversion: DOGE leverage config must exist and be typed
        mr = cfg.strategies.mean_reversion
        assert mr is not None, "strategies.mean_reversion missing (profile not loaded)"
        doge = mr.assets["DOGEUSDT"]
        assert doge.leverage is not None, "mean_reversion.assets.DOGEUSDT.leverage missing"
        assert isinstance(doge.leverage, LeverageConfig), "MR DOGE leverage must be LeverageConfig"
        assert doge.leverage.target == 10

        print("✅ All YAML configurations loaded and validated successfully.")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
