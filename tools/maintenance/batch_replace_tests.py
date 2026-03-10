#!/usr/bin/env python3
"""Batch replace BTCUSDT with SOLUSDT in all test files."""

import os
import re

test_files = [
    "tests/adapters/test_binance_adapter.py",
    "tests/bugfixes/test_p1_002_adapter_precision.py",
    "tests/domains/test_account_observer.py",
    "tests/domains/test_binance_execution_adapter.py",
    "tests/domains/test_config_loader.py",
    "tests/domains/test_decision_making_logic_branches.py",
    "tests/domains/test_decision_making_side_bias.py",
    "tests/domains/test_execution_position_contracts.py",
    "tests/domains/test_exposure_guard_side_caps.py",
    "tests/domains/test_feature_engineering.py",
    "tests/domains/test_integration_three_domains.py",
    "tests/domains/test_market_data.py",
    "tests/domains/test_market_data_coverage_gaps.py",
    "tests/domains/test_portfolio_equity_flow.py",
    "tests/domains/test_position_tracking.py",
    "tests/domains/test_position_tracking_logic.py",
    "tests/domains/test_position_tracking_margins.py",
    "tests/domains/test_position_tracking_wal_integration.py",
    "tests/domains/test_risk_management.py",
    "tests/domains/test_simulated_adapter.py",
    "tests/dr/test_dr_loader.py",
    "tests/dr/test_position_tracking_snapshot.py",
    "tests/integration/test_account_connector.py",
    "tests/integration/test_aurora_core_flow.py",
    "tests/integration/test_bridge_portfolio_freshness_gate.py",
    "tests/integration/test_daily_gate_block_open.py",
    "tests/integration/test_decision_qos_features_burst.py",
    "tests/integration/test_e2e_lifecycle.py",
    "tests/integration/test_e2e_smoke.py",
    "tests/integration/test_exposure_release_hooks.py",
    "tests/integration/test_features_and_risk_join.py",
    "tests/integration/test_features_full_chain_happy.py",
    "tests/integration/test_happy_path_dec_open.py",
    "tests/integration/test_hotloop_defer_then_open.py",
    "tests/integration/test_live_bridge_to_marketdata.py",
    "tests/integration/test_metrics_summary.py",
    "tests/integration/test_open_exposure_guard.py",
    "tests/integration/test_order_lifecycle_correlation.py",
    "tests/integration/test_order_lifecycle_scenarios.py",
    "tests/integration/test_order_logger_flow.py",
    "tests/integration/test_panic_killswitch.py",
    "tests/integration/test_positions_notional_aggregate.py",
    "tests/integration/test_postfill_hold_until_portfolio_ok.py",
    "tests/integration/test_qos_symbol_cooldown_nrr017.py",
    "tests/integration/test_resilience_scenarios.py",
    "tests/integration/test_timeout_nrr019.py",
    "tests/test_acl_message_contracts.py",
    "tests/test_alpha_models.py",
    "tests/test_cli_shadow.py",
    "tests/test_debug_drift_integration.py",
    "tests/test_decision_making_qos.py",
    "tests/test_drift_unit.py",
    "tests/test_ensemble.py",
    "tests/test_execpos_contracts_pydantic_v2.py",
    "tests/test_execution_position_basic.py",
    "tests/test_feature_collection.py",
    "tests/test_features_and_signals_live.py",
    "tests/test_features_signals_core.py",
    "tests/test_fsm_open.py",
    "tests/test_fsm_shadow_roundtrip.py",
    "tests/test_orchestrator_fsm.py",
    "tests/unit/test_order_logger_schema.py",
    "tests/units/test_binance_execution_adapter_unit.py",
    "tests/units/test_execution_position_fsm_unit.py",
    "tests/units/test_exposure_guard_unit.py",
    "tests/units/test_feature_math_basic.py",
    "tests/units/test_manage_flow_fsm_unit.py",
    "tests/units/test_risk_score_not_null.py",
    "tests/units/test_vfoundation_binance_adapter_unit.py",
]

count = 0
for filepath in test_files:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        # Replace BTCUSDT with SOLUSDT
        new_content = content.replace('BTCUSDT', 'SOLUSDT')

        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            replacements = content.count('BTCUSDT')
            print(f"✅ {filepath}: {replacements} replacements")
            count += 1
    except Exception as e:
        print(f"❌ {filepath}: {e}")

print(f"\n✅ Updated {count} files total")
