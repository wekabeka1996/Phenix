from __future__ import annotations

from dataclasses import asdict

from tools.alpha_search.j6_s17_b_forward_outcome_join import (
    build_joined_dataset,
    build_outcome_index_from_records,
)


def _policy_row(cycle_key: str) -> dict[str, object]:
    return {
        'cycle_key': cycle_key,
        'symbol': 'BTCUSDT',
        'side': 'BUY',
        'tf_sec': 300,
        'ts_ms': 1712000000300,
        'regime': 'TREND_UP',
        'strategy_id': 'aurora',
        'surface_key': 'surface-1',
        'matched_surface_label': 'PROMISING_BUT_CONCENTRATED',
        'classifier_output': 'TRACK_ONLY',
        'final_shadow_policy': 'KEEP',
        'reason_codes': ['tier_threshold_met'],
        'sample_size': 10,
        'authority_mode': 'shadow',
        'applied': False,
        'advisory': True,
        'production_authority': False,
    }


def _verdict_row(cycle_key: str) -> dict[str, object]:
    return {
        'cycle_key': cycle_key,
        'verdict_id': f'verdict-{cycle_key}',
        'entry_verdict': 'OPEN_LONG',
        'confidence': 0.82,
        'suppression_reason': None,
    }


def _shadow_plan(cycle_key: str, tier: str, *, plan_id: str | None) -> dict[str, object]:
    return {
        'cycle_key': cycle_key,
        'plan_id': plan_id,
        'confidence_tier': tier,
        'actionable': True,
        'entry_price_ref': 100.0,
        'limit_price': 100.0,
        'tp_price': 101.0,
        'sl_price': 99.5,
        'tp_offset_pct': 0.01,
        'sl_offset_pct': 0.005,
        'risk_reward': 2.0,
    }


def _outcome_row(cycle_key: str | None, tier: str | None, *, plan_id: str | None, outcome: str = 'FILLED_TP') -> dict[str, object]:
    return {
        'cycle_key': cycle_key,
        'tier': tier,
        'plan_id': plan_id,
        'outcome': outcome,
        'outcome_reason': outcome,
        'fill_ts_ms': 1712000000300,
        'fill_price': 100.0,
        'exit_ts_ms': 1712000300300,
        'exit_price': 101.0,
        'gross_pnl_pct': 1.0,
        'net_pnl_pct': 0.94,
        'fees_paid_pct': 0.06,
    }


def _build_rows(shadow_plans: list[dict[str, object]], outcome_rows: list[dict[str, object]]) -> tuple[list[dict[str, object]], object]:
    policy_index = {}
    verdict_index = {}
    shadow_index = {}
    for shadow_plan in shadow_plans:
        cycle_key = str(shadow_plan['cycle_key'])
        policy_index[cycle_key] = _policy_row(cycle_key)
        verdict_index[cycle_key] = _verdict_row(cycle_key)
        shadow_index.setdefault(cycle_key, []).append(shadow_plan)
    outcome_index = build_outcome_index_from_records(outcome_rows)
    return build_joined_dataset(policy_index, verdict_index, shadow_index, outcome_index)


def test_cycle_key_tier_join_succeeds_even_when_plan_id_is_missing() -> None:
    shadow_plan = _shadow_plan('ENTRY:BTCUSDT:300:1', 'low', plan_id=None)
    outcome_row = _outcome_row('ENTRY:BTCUSDT:300:1', 'low', plan_id=None)
    rows, metrics = _build_rows([shadow_plan], [outcome_row])

    assert rows[0]['outcome_available'] is True
    assert rows[0]['outcome'] == 'FILLED_TP'
    assert rows[0]['plan_id'] is None
    assert metrics.rows_with_outcome == 1


def test_cycle_key_tier_join_succeeds_when_plan_id_is_duplicate() -> None:
    shadow_plans = [
        _shadow_plan('ENTRY:BTCUSDT:300:1', 'low', plan_id='dup-plan'),
        _shadow_plan('ENTRY:ETHUSDT:300:1', 'low', plan_id='dup-plan'),
    ]
    outcome_rows = [
        _outcome_row('ENTRY:BTCUSDT:300:1', 'low',
                     plan_id='dup-plan', outcome='FILLED_TP'),
        _outcome_row('ENTRY:ETHUSDT:300:1', 'low',
                     plan_id='dup-plan', outcome='FILLED_SL'),
    ]
    rows, metrics = _build_rows(shadow_plans, outcome_rows)

    assert [row['outcome'] for row in rows] == ['FILLED_TP', 'FILLED_SL']
    assert metrics.rows_with_outcome == 2
    assert metrics.duplicate_plan_id_count == 1


def test_plan_id_alone_does_not_join_without_cycle_key_tier() -> None:
    shadow_plan = _shadow_plan(
        'ENTRY:BTCUSDT:300:1', 'low', plan_id='plan-only')
    outcome_row = _outcome_row(None, None, plan_id='plan-only')
    rows, metrics = _build_rows([shadow_plan], [outcome_row])

    assert rows[0]['outcome_available'] is False
    assert rows[0]['outcome_join_warning'] == 'no_canonical_outcome_match'
    assert metrics.rows_without_outcome == 1
    assert metrics.missing_canonical_outcome_key_rows == 1


def test_duplicate_cycle_key_tier_is_reported_and_fails_closed() -> None:
    shadow_plan = _shadow_plan('ENTRY:BTCUSDT:300:1', 'low', plan_id='plan-a')
    outcome_rows = [
        _outcome_row('ENTRY:BTCUSDT:300:1', 'low',
                     plan_id='plan-a', outcome='FILLED_TP'),
        _outcome_row('ENTRY:BTCUSDT:300:1', 'low',
                     plan_id='plan-b', outcome='FILLED_SL'),
    ]
    rows, metrics = _build_rows([shadow_plan], outcome_rows)

    assert rows[0]['outcome_available'] is False
    assert rows[0]['outcome_join_warning'] == 'duplicate_cycle_key_tier_in_outcomes'
    assert metrics.duplicate_canonical_outcome_key_count == 1
    assert metrics.outcome_join_integrity_error_count == 1


def test_report_metadata_no_longer_declares_plan_id_primary() -> None:
    shadow_plan = _shadow_plan(
        'ENTRY:BTCUSDT:300:1', 'low', plan_id='diag-plan')
    outcome_row = _outcome_row(
        'ENTRY:BTCUSDT:300:1', 'low', plan_id='diag-plan')
    _, metrics = _build_rows([shadow_plan], [outcome_row])
    payload = asdict(metrics)

    assert payload['canonical_outcome_join'] == 'cycle_key+tier'
    assert payload['plan_id_usage'] == 'diagnostics_only'
