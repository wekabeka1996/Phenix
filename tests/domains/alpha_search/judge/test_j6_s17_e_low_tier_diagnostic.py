from __future__ import annotations

from tools.alpha_search.j6_s17_e_low_tier_diagnostic import (
    build_decision_matrix,
    build_low_inventory_payload,
    build_simulator_skip_audit,
    build_shadow_plan_generation_audit,
    build_join_augmentation_audit,
    classify_root_cause,
)


def _row(
    *,
    tier: str,
    cycle_key: str,
    plan_id: str,
    actionable: bool,
    suppressed: bool,
    skipped_reason: str | None = None,
    outcome_available: bool = False,
    simulation_status: str = "skipped",
    invalid_outcome_reason: str | None = None,
    symbol: str = "BTCUSDT",
    tf_sec: str = "300",
    side: str | None = "BUY",
    ts_ms: str = "1712000000300",
    classifier_output: str = "UNKNOWN",
) -> dict[str, str]:
    return {
        "tier": tier,
        "cycle_key": cycle_key,
        "plan_id": plan_id,
        "actionable": "True" if actionable else "False",
        "suppressed": "True" if suppressed else "False",
        "skipped_reason": skipped_reason or "",
        "outcome_available": "True" if outcome_available else "False",
        "simulation_status": simulation_status,
        "invalid_outcome_reason": invalid_outcome_reason or "",
        "symbol": symbol,
        "tf_sec": tf_sec,
        "side": side or "",
        "ts_ms": ts_ms,
        "plan_ts_ms": ts_ms,
        "classifier_output": classifier_output,
        "matched_surface_label": "UNKNOWN",
        "regime": "LOW_VOLATILITY",
        "limit_price": "100.0" if not suppressed else "",
        "entry_price_ref": "100.1" if not suppressed else "",
        "tp_price": "101.0" if not suppressed else "",
        "sl_price": "99.0" if not suppressed else "",
        "risk_reward": "1.6",
        "limit_filled": "False",
        "tp_hit": "False",
        "sl_hit": "False",
        "timeout_hit": "False",
        "net_pnl_pct": "",
        "join_match_method": "cycle_key+tier",
    }


def _sim_row(*, tier: str, cycle_key: str, plan_id: str, symbol: str = "BTCUSDT", tf_sec: str = "300", skipped_reason: str = "non_actionable_plan") -> dict[str, str]:
    return {
        "tier": tier,
        "cycle_key": cycle_key,
        "plan_id": plan_id,
        "symbol": symbol,
        "tf_sec": tf_sec,
        "simulation_status": "skipped",
        "skipped_reason": skipped_reason,
    }


def test_inventory_counts_tiers_and_nulls_and_skips_not_outcomes() -> None:
    rows = [
        _row(tier="low", cycle_key="c1", plan_id="p1", actionable=False,
             suppressed=False, skipped_reason="non_actionable_plan"),
        _row(tier="low", cycle_key="c2", plan_id="p2", actionable=False,
             suppressed=True, skipped_reason="suppressed_plan", side=None),
        _row(tier="medium", cycle_key="c1", plan_id="p3", actionable=True,
             suppressed=False, outcome_available=True, simulation_status="success"),
        _row(tier="high", cycle_key="c1", plan_id="p4", actionable=True,
             suppressed=False, outcome_available=True, simulation_status="success"),
    ]

    inventory = build_low_inventory_payload(rows)
    low = inventory["low_tier_inventory"]

    assert low["total_rows"] == 2
    assert low["actionable_distribution"]["False"] == 2
    assert low["outcome_available_distribution"]["False"] == 2
    assert low["skipped_reason_distribution"]["non_actionable_plan"] == 1
    assert low["skipped_reason_distribution"]["suppressed_plan"] == 1
    assert low["null_limit_price_count"] == 1


def test_root_cause_non_actionable_by_design() -> None:
    rows = []
    for i in range(10):
        rows.append(_row(tier="low", cycle_key=f"l{i}", plan_id=f"pl{i}",
                    actionable=False, suppressed=False, skipped_reason="non_actionable_plan"))
    rows.append(_row(tier="medium", cycle_key="m1", plan_id="pm1", actionable=True,
                suppressed=False, outcome_available=True, simulation_status="success"))
    rows.append(_row(tier="high", cycle_key="h1", plan_id="ph1", actionable=True,
                suppressed=False, outcome_available=True, simulation_status="success"))

    sim_rows = [
        _sim_row(tier="low", cycle_key=f"l{i}", plan_id=f"pl{i}") for i in range(10)]
    source_flags = {
        "simulator_skips_non_actionable_or_suppressed": True,
        "wrapper_emits_non_actionable_skip": True,
        "wrapper_emits_suppressed_skip": True,
        "entry_plan_has_actionable_tier_filter": True,
        "entry_plan_marks_excluded_tier": True,
    }
    config_info = {
        "emit_all_tiers": True,
        "actionable_tiers": ["medium", "high"],
        "confidence_ladder_names": ["low", "medium", "high"],
    }

    inventory = build_low_inventory_payload(rows)
    shadow = build_shadow_plan_generation_audit(
        config_info=config_info, source_flags=source_flags, rows=rows)
    sim = build_simulator_skip_audit(
        sim_rows=sim_rows, rows=rows, source_flags=source_flags)
    join = build_join_augmentation_audit(rows, sim_rows)

    root = classify_root_cause(
        inventory=inventory, shadow_audit=shadow, simulator_audit=sim, join_audit=join)
    assert root["primary_bucket"] == "LOW_TIER_NON_ACTIONABLE_BY_DESIGN"


def test_root_cause_join_defect_when_low_join_misses_material() -> None:
    rows = []
    sim_rows = []
    for i in range(10):
        miss = i < 3
        rows.append(
            _row(
                tier="low",
                cycle_key=f"l{i}",
                plan_id=f"pl{i}",
                actionable=True,
                suppressed=False,
                skipped_reason="",
                simulation_status="",
                invalid_outcome_reason="missing_outcome_key_match" if miss else "",
            )
        )
        if not miss:
            sim_rows.append(
                _sim_row(tier="low", cycle_key=f"l{i}", plan_id=f"pl{i}"))

    source_flags = {
        "simulator_skips_non_actionable_or_suppressed": True,
        "wrapper_emits_non_actionable_skip": True,
        "wrapper_emits_suppressed_skip": True,
        "entry_plan_has_actionable_tier_filter": True,
        "entry_plan_marks_excluded_tier": True,
    }
    config_info = {
        "emit_all_tiers": True,
        "actionable_tiers": ["low", "medium", "high"],
        "confidence_ladder_names": ["low", "medium", "high"],
    }

    inventory = build_low_inventory_payload(rows)
    shadow = build_shadow_plan_generation_audit(
        config_info=config_info, source_flags=source_flags, rows=rows)
    sim = build_simulator_skip_audit(
        sim_rows=sim_rows, rows=rows, source_flags=source_flags)
    join = build_join_augmentation_audit(rows, sim_rows)

    root = classify_root_cause(
        inventory=inventory, shadow_audit=shadow, simulator_audit=sim, join_audit=join)
    assert root["primary_bucket"] == "AUGMENTATION_JOIN_DEFECT"


def test_root_cause_simulator_skip_non_actionable_plans() -> None:
    rows = []
    sim_rows = []
    for i in range(10):
        rows.append(_row(tier="low", cycle_key=f"l{i}", plan_id=f"pl{i}",
                    actionable=True, suppressed=False, skipped_reason="non_actionable_plan"))
        sim_rows.append(_sim_row(
            tier="low", cycle_key=f"l{i}", plan_id=f"pl{i}", skipped_reason="non_actionable_plan"))

    source_flags = {
        "simulator_skips_non_actionable_or_suppressed": True,
        "wrapper_emits_non_actionable_skip": True,
        "wrapper_emits_suppressed_skip": True,
        "entry_plan_has_actionable_tier_filter": True,
        "entry_plan_marks_excluded_tier": True,
    }
    config_info = {
        "emit_all_tiers": True,
        "actionable_tiers": ["low", "medium", "high"],
        "confidence_ladder_names": ["low", "medium", "high"],
    }

    inventory = build_low_inventory_payload(rows)
    shadow = build_shadow_plan_generation_audit(
        config_info=config_info, source_flags=source_flags, rows=rows)
    sim = build_simulator_skip_audit(
        sim_rows=sim_rows, rows=rows, source_flags=source_flags)
    join = build_join_augmentation_audit(rows, sim_rows)

    root = classify_root_cause(
        inventory=inventory, shadow_audit=shadow, simulator_audit=sim, join_audit=join)
    assert root["primary_bucket"] == "SIMULATOR_SKIPS_NON_ACTIONABLE_PLANS"


def test_decision_logic_non_actionable_design_defaults() -> None:
    rows = []
    for i in range(5):
        rows.append(_row(tier="low", cycle_key=f"l{i}", plan_id=f"pl{i}",
                    actionable=False, suppressed=False, skipped_reason="non_actionable_plan"))
    rows.append(_row(tier="medium", cycle_key="m1", plan_id="pm1", actionable=True, suppressed=False,
                outcome_available=True, simulation_status="success", classifier_output="TRACK_ONLY"))
    rows.append(_row(tier="high", cycle_key="h1", plan_id="ph1", actionable=True, suppressed=False,
                outcome_available=True, simulation_status="success", classifier_output="UNKNOWN"))

    decision = build_decision_matrix(root_classification={
                                     "primary_bucket": "LOW_TIER_NON_ACTIONABLE_BY_DESIGN"}, rows=rows)
    assert decision["decision_include_low_tier_in_hit_miss"] == "EXCLUDE_FROM_TRADE_PERFORMANCE_INCLUDE_IN_COVERAGE"
    assert decision["decision_patch_justified_now"] == "NO_PATCH_DIAGNOSTIC_ONLY"
    assert decision["decision_d_closure_impact"] == "D_CLOSURE_STANDS"
