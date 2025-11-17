#!/usr/bin/env python3
"""
Quick script to check which config resolvers use `config_v2` vs legacy and print key values.
Usage: python tools/check_config_sources.py
"""
from apps.reference.config_symbols import get_trading_symbols
from apps.reference.config_features import resolve_feature_engineering_config
from apps.reference.config_decision import resolve_decision_policy
from apps.reference.config_risk import resolve_daily_risk_state, resolve_trading_allowed_thresholds
from apps.reference.domains.execution_position.brackets_config import resolve_brackets_config
from apps.reference.domains.execution_position.manage_config import resolve_execution_manage_config
from apps.reference.config_exposure_policy import resolve_exposure_policy
from apps.reference.config_loader import get_config
import sys
from pathlib import Path
# Ensure repository root on sys.path for `apps` import
sys.path.insert(0, str(Path.cwd()))


def print_source(name, resolver, *args, **kwargs):
    try:
        res = resolver(*args, **kwargs)
        src = getattr(res, 'source', 'legacy')
        print(f"{name}: source={src}")
        return res
    except Exception as e:
        print(f"{name}: ERROR -> {e}")
        return None


def main():
    cfg = get_config()
    print("=== Effective trading_mode ===")
    try:
        print("trading_mode:", cfg.trading_mode)
    except Exception:
        print("trading_mode: (unknown)")

    print("\n=== Domain resolvers source checks ===")
    exposure = print_source("exposure", resolve_exposure_policy, cfg)
    manage = print_source(
        "manage_config", resolve_execution_manage_config, cfg)
    brackets = print_source("brackets", resolve_brackets_config, cfg)
    risk = print_source("risk_state", resolve_daily_risk_state, cfg)
    thresholds = print_source(
        "risk_thresholds", resolve_trading_allowed_thresholds, cfg)
    decision = print_source("decision", resolve_decision_policy, cfg)
    features = print_source(
        "features", resolve_feature_engineering_config, cfg)

    print("\n=== Selected values ===")
    try:
        print("decision.thresholds:", decision.signal_threshold,
              decision.neutral_threshold)
    except Exception:
        pass
    try:
        print("risk.max_risk_score:", thresholds.max_risk_score)
    except Exception:
        pass
    try:
        print("exposure.max_equity_utilization_ratio:", getattr(
            exposure.caps, 'max_equity_utilization_ratio', None))
    except Exception:
        pass

    print("\n=== Configv2 presence ===")
    print('config_v2 present:', hasattr(
        cfg, 'config_v2') and cfg.config_v2 is not None)

    print("\n=== Sample symbols ===")
    print(get_trading_symbols()[:20])


if __name__ == '__main__':
    main()
