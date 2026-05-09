"""Example rows for each dataset schema.

Examples are provided for validation and schema contract testing.
Most examples use synthetic=True to indicate they are not runtime truth.
"""

from calibrators.datasets.schemas import (
    CalibrationFeatureSnapshotRowV1,
    CalibrationLowVolGateRowV1,
    CalibrationMarketBarRowV1,
    CalibrationOracleRegimeLabelRowV1,
    CalibrationRealizedTradeRowV1,
    CalibrationTradeDecisionRowV1,
    CalibrationWalkforwardManifestV1,
)


def example_market_bar_row() -> CalibrationMarketBarRowV1:
    """Example market bar row (synthetic test data)."""
    return CalibrationMarketBarRowV1(
        dataset_schema="calibration_market_bar_dataset_v1",
        dataset_version="1.0.0",
        source_surface="recorder_csv",
        source_file="data/recorder/BTCUSDT_300.csv",
        session_date="2026-05-01",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1714568400000,  # Synthetic timestamp
        bar_close_ts_ms=1714568400000,
        open=98765.0,
        high=98900.0,
        low=98700.0,
        close=98850.0,
        volume=1234.5,
        trade_count=456,
        data_quality="good",
        synthetic=True,
    )


def example_feature_snapshot_row() -> CalibrationFeatureSnapshotRowV1:
    """Example feature snapshot row (synthetic test data)."""
    return CalibrationFeatureSnapshotRowV1(
        dataset_schema="calibration_feature_snapshot_dataset_v1",
        dataset_version="1.0.0",
        source_surface="ta_features_log",
        source_file="logs/features/BTCUSDT_300_features.jsonl",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1714568400000,
        close=98850.0,
        features={
            "rsi": 65.5,
            "bb_position": 0.7,
            "momentum": 0.05,
            "volatility_state": "normal",
            "ema_bias": 0.002,
            "trade_volume_imbalance": 0.55,
        },
        feature_version="v2.1.0",
        ready=True,
        not_ready_reasons=[],
        regime="up",
        regime_confidence=0.82,
        missingness_mask={
            "rsi": False,
            "bb_position": False,
            "momentum": False,
            "volatility_state": False,
            "ema_bias": False,
            "trade_volume_imbalance": False,
        },
        freshness_ms=100,
        synthetic=True,
    )


def example_oracle_regime_label_row() -> CalibrationOracleRegimeLabelRowV1:
    """Example oracle regime label row (synthetic training data)."""
    return CalibrationOracleRegimeLabelRowV1(
        dataset_schema="calibration_oracle_regime_labels_v1",
        dataset_version="1.0.0",
        source_dataset_id="calibration_market_bar_dataset_v1",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1714568400000,
        horizon_bars=10,
        future_return_bps=150.0,
        future_volatility_bps=50.0,
        flip_rate=0.1,
        oracle_regime="up",
        label_version="oracle_v1",
        split_bucket="train",
        synthetic=True,
    )


def example_trade_decision_row() -> CalibrationTradeDecisionRowV1:
    """Example trade decision row (synthetic causal data)."""
    return CalibrationTradeDecisionRowV1(
        dataset_schema="calibration_trade_decision_dataset_v1",
        dataset_version="1.0.0",
        decision_id="dec_20260501_001",
        rid="req_20260501_001",
        symbol="BTCUSDT",
        strategy_id="aurora_thresholds",
        side="long",
        proposed_action="open_long",
        decision_basis_ts_ms=1714568400000,
        request_ts_ms=1714568400050,
        response_ts_ms=1714568400150,
        authority_mode="live",
        action="open_long",
        apply_result="accepted",
        reason_code=None,
        dataset_visibility="causal_complete",
        observation_causal=True,
        source_paths=["authority_request_journal_v1.jsonl:line_123",
                      "decision_ledger_v1.jsonl:line_456"],
        synthetic=True,
    )


def example_realized_trade_row() -> CalibrationRealizedTradeRowV1:
    """Example realized trade outcome row (synthetic closed trade)."""
    return CalibrationRealizedTradeRowV1(
        dataset_schema="calibration_realized_trade_dataset_v1",
        dataset_version="1.0.0",
        attempt_id="att_20260501_001",
        decision_id="dec_20260501_001",
        rid="req_20260501_001",
        lifecycle_id="lc_20260501_001",
        symbol="BTCUSDT",
        strategy_id="aurora_thresholds",
        side="long",
        intent_ts_ms=1714568400000,
        entry_ts_ms=1714568402000,
        exit_ts_ms=1714568600000,
        entry_price=98850.0,
        exit_price=98950.0,
        qty=0.5,
        outcome="closed_win",
        gross_pnl=50.0,
        realized_pnl_net=45.0,
        fees=5.0,
        commission=0.0,
        mfe=100.0,
        mae=-20.0,
        bars_held=20,
        exact_roundtrip=True,
        terminal_status="closed",
        source_paths=["executed_trades_master.csv:row_123",
                      "decision_ledger_v1.jsonl:line_456"],
        synthetic=True,
    )


def example_low_vol_gate_row() -> CalibrationLowVolGateRowV1:
    """Example low-vol gate outcome row (synthetic gate decision)."""
    return CalibrationLowVolGateRowV1(
        dataset_schema="calibration_low_vol_gate_dataset_v1",
        dataset_version="1.0.0",
        attempt_id="att_20260501_lv_001",
        decision_id="dec_20260501_lv_001",
        symbol="ETHUSDT",
        strategy_id="low_vol_cost_floor",
        side="long",
        regime="low_vol",
        regime_confidence=0.75,
        direction_confidence=0.65,
        target_net_fee_multiple=2.5,
        required_gross_tp_bps_floor=25.0,
        min_rr=1.5,
        gross_tp_bps=30.0,
        realized_pnl_net=28.0,
        commission=2.0,
        outcome="gate_allowed",
        counterfactual_source=None,
        exact_roundtrip=True,
        source_paths=["authority_request_journal_v1.jsonl:line_789"],
        synthetic=True,
    )


def example_walkforward_manifest_row() -> CalibrationWalkforwardManifestV1:
    """Example walk-forward manifest row (synthetic split metadata)."""
    return CalibrationWalkforwardManifestV1(
        dataset_schema="calibration_walkforward_manifest_v1",
        dataset_version="1.0.0",
        dataset_id="calibration_market_bar_dataset_v1",
        source_dataset="raw_recorder_bars",
        train_start="2026-01-01",
        train_end="2026-03-01",
        validation_start="2026-03-02",
        validation_end="2026-03-31",
        forward_start="2026-04-01",
        forward_end="2026-04-30",
        excluded_sessions=["2026-02-15", "2026-03-20"],
        label_horizon_bars=10,
        config_snapshot={
            "strategy": "aurora_thresholds",
            "param_version": "v2.1.0",
            "split_method": "time_based_walkforward",
        },
        synthetic_allowed=False,
        notes="Standard 90/30/30 walk-forward split for BTCUSDT tf_sec=300",
    )
