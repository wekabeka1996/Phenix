from __future__ import annotations

import pytest

from apps.reference.domains.alpha_search.judge.central_brain.calibration import (
    bucket_confidence_bands,
    build_calibration_proposal,
    compute_band_metrics,
    compute_breakdowns,
    detect_toxic_bands,
    render_policy_patch_proposal,
    split_train_holdout,
    validate_calibration_dataset,
)

from tests.domains.alpha_search.judge.central_brain.test_judge_confidence_calibration_contract import (
    valid_row,
)


def row(
    row_id: str,
    *,
    ts_ms: int,
    confidence: float | None,
    net: float | None,
    gross: float | None = None,
    symbol: str = "BTCUSDT",
    regime: str | None = "TREND_UP",
    side: str = "BUY",
):
    return valid_row(
        row_id=row_id,
        decision_ts_ms=ts_ms,
        outcome_ts_ms=ts_ms + 1000,
        judge_confidence=confidence,
        symbol=symbol,
        regime_label=regime,
        side=side,
        outcome={
            "horizon_sec": 300,
            "gross_pnl_usd": gross if gross is not None else net,
            "net_pnl_usd": net,
            "fees_usd": None,
            "slippage_usd": None,
            "max_favorable_usd": None,
            "max_adverse_usd": None,
            "terminal_status": "closed" if net is not None else "unresolved",
        },
    )


def test_buckets_confidence_into_deterministic_bands():
    buckets = bucket_confidence_bands(
        [
            row("a", ts_ms=1000, confidence=0.11, net=1.0),
            row("b", ts_ms=2000, confidence=0.19, net=1.0),
            row("c", ts_ms=3000, confidence=0.91, net=1.0),
        ],
        band_step=0.10,
    )
    assert list(buckets) == [(0.1, 0.2), (0.9, 1.0)]
    assert [item.row_id for item in buckets[(0.1, 0.2)]] == ["a", "b"]


def test_excludes_missing_confidence_from_numeric_bands():
    rows = [
        row("a", ts_ms=1000, confidence=None, net=1.0),
        row("b", ts_ms=2000, confidence=0.22, net=1.0),
    ]
    assert "a:missing_judge_confidence" in validate_calibration_dataset(rows)
    buckets = bucket_confidence_bands(rows, band_step=0.10)
    assert [item.row_id for bucket in buckets.values() for item in bucket] == ["b"]


def test_excludes_unresolved_net_pnl_rows_from_economics():
    buckets = bucket_confidence_bands(
        [
            row("a", ts_ms=1000, confidence=0.45, net=None, gross=1.0),
            row("b", ts_ms=2000, confidence=0.46, net=2.0),
        ],
        band_step=0.10,
    )
    metrics = compute_band_metrics(buckets, min_rows=1)
    assert metrics[0].rows == 2
    assert metrics[0].avg_net_pnl_usd == pytest.approx(2.0)
    assert metrics[0].win_rate == pytest.approx(1.0)


def test_computes_win_rate_average_total_and_expectancy():
    buckets = bucket_confidence_bands(
        [
            row("a", ts_ms=1000, confidence=0.55, net=2.0),
            row("b", ts_ms=2000, confidence=0.56, net=-1.0),
        ],
        band_step=0.10,
    )
    band = compute_band_metrics(buckets, min_rows=2)[0]
    assert band.win_rate == pytest.approx(0.5)
    assert band.avg_net_pnl_usd == pytest.approx(0.5)
    assert band.total_net_pnl_usd == pytest.approx(1.0)
    assert band.expectancy_net_usd == pytest.approx(0.5)


def test_labels_sparse_bands_low_power():
    buckets = bucket_confidence_bands([row("a", ts_ms=1000, confidence=0.65, net=2.0)], band_step=0.10)
    assert compute_band_metrics(buckets, min_rows=2)[0].status == "LOW_POWER"


def test_labels_negative_expectancy_band_toxic():
    buckets = bucket_confidence_bands(
        [
            row("a", ts_ms=1000, confidence=0.75, net=-2.0),
            row("b", ts_ms=2000, confidence=0.76, net=-1.0),
        ],
        band_step=0.10,
    )
    metrics = compute_band_metrics(buckets, min_rows=2)
    assert metrics[0].status == "TOXIC"
    assert detect_toxic_bands(metrics)[0].band_id == metrics[0].band_id


def test_labels_positive_sufficient_band_candidate():
    buckets = bucket_confidence_bands(
        [
            row("a", ts_ms=1000, confidence=0.85, net=2.0),
            row("b", ts_ms=2000, confidence=0.86, net=1.0),
        ],
        band_step=0.10,
    )
    band = compute_band_metrics(buckets, min_rows=2)[0]
    assert band.status == "CANDIDATE"
    assert band.action == "allow"


def test_computes_symbol_regime_and_side_breakdowns():
    breakdowns = compute_breakdowns(
        [
            row("a", ts_ms=1000, confidence=0.5, net=1.0, symbol="BTCUSDT", regime="TREND_UP", side="BUY"),
            row("b", ts_ms=2000, confidence=0.6, net=-1.0, symbol="ETHUSDT", regime="TREND_DOWN", side="SELL"),
        ]
    )
    assert breakdowns["by_symbol"]["BTCUSDT"]["rows"] == 1
    assert breakdowns["by_regime"]["TREND_DOWN"]["rows"] == 1
    assert breakdowns["by_side"]["SELL"]["rows"] == 1


def test_train_holdout_split_is_timestamp_ordered():
    rows = [
        row("c", ts_ms=3000, confidence=0.5, net=1.0),
        row("a", ts_ms=1000, confidence=0.5, net=1.0),
        row("b", ts_ms=2000, confidence=0.5, net=1.0),
        row("d", ts_ms=4000, confidence=0.5, net=1.0),
    ]
    train, holdout = split_train_holdout(rows, holdout_ratio=0.25)
    assert [item.row_id for item in train] == ["a", "b", "c"]
    assert [item.row_id for item in holdout] == ["d"]


def test_leakage_check_fails_if_holdout_overlaps_train():
    with pytest.raises(ValueError):
        split_train_holdout([row("a", ts_ms=1000, confidence=0.5, net=1.0)], holdout_ratio=1.0)


def test_proposal_has_promotion_allowed_false_and_patch_suggestion_only():
    proposal = build_calibration_proposal(
        [
            row("a", ts_ms=1000, confidence=0.85, net=2.0),
            row("b", ts_ms=2000, confidence=0.86, net=1.0),
            row("c", ts_ms=3000, confidence=0.95, net=-2.0),
            row("d", ts_ms=4000, confidence=0.96, net=-1.0),
        ],
        created_ts_ms=5000,
        band_step=0.10,
        cadence_days=4,
        min_rows=2,
        min_symbols=1,
    )
    dumped = proposal.model_dump(mode="json", by_alias=True)
    assert dumped["gates"]["promotion_allowed"] is False
    assert dumped["recommended_policy"]["auto_apply"] is False
    assert dumped["recommended_policy"]["yaml_patch"] is not None


def test_gross_pnl_fallback_is_explicitly_labeled():
    buckets = bucket_confidence_bands(
        [
            row("a", ts_ms=1000, confidence=0.45, net=None, gross=1.0),
            row("b", ts_ms=2000, confidence=0.46, net=2.0),
        ],
        band_step=0.10,
    )
    band = compute_band_metrics(buckets, min_rows=2, gross_pnl_fallback=True)[0]
    assert band.status == "CANDIDATE"
    assert "gross_pnl_fallback_used" in band.reason_codes


def test_policy_patch_proposal_returns_none_without_candidate_bands():
    assert render_policy_patch_proposal([]) is None


def test_proposal_id_is_deterministic_for_same_input_and_config():
    rows = [
        row("a", ts_ms=1000, confidence=0.85, net=2.0),
        row("b", ts_ms=2000, confidence=0.86, net=1.0),
    ]
    first = build_calibration_proposal(
        rows,
        created_ts_ms=5000,
        band_step=0.10,
        cadence_days=4,
        min_rows=2,
        min_symbols=1,
    )
    second = build_calibration_proposal(
        list(reversed(rows)),
        created_ts_ms=5000,
        band_step=0.10,
        cadence_days=4,
        min_rows=2,
        min_symbols=1,
    )
    assert first.proposal_id == second.proposal_id
