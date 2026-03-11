import json
from pathlib import Path

import pytest

try:
    from jsonschema import validate

    HAS_JSONSCHEMA = True
except ImportError:  # pragma: no cover
    HAS_JSONSCHEMA = False

from apps.reference.contracts.runtime_bar_identity import (
    RuntimeBarSourceMode,
    build_canonical_bar_identity,
)
from apps.reference.contracts.runtime_gap_policy import (
    RuntimeGapPolicyAction,
    RuntimeGapState,
    attach_gap_status_payload,
    build_basis_bar_status_from_gap,
    build_gap_status,
    build_trading_status_from_gap,
    extract_gap_status,
    gap_blocks_open_new_risk,
)


SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schemas"
CMD_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "apps"
    / "reference"
    / "domains"
    / "feature_engineering"
    / "schemas"
    / "cmd_process_strategy_v1.json"
)


def _load_schema(name: str) -> dict:
    with open(SCHEMA_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


def test_extract_gap_status_from_gap_bar_defaults_to_non_trading_degrade() -> None:
    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=180,
        bar_start_ts_ms=1_700_000_000_000,
        close_boundary_ts_ms=1_700_000_180_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )
    payload = {
        "symbol": "BTCUSDT",
        "tf_sec": 180,
        "source_mode": "live",
        "bar_identity": identity.to_payload(),
        "bar": {
            "symbol": "BTCUSDT",
            "timeframe_sec": 180,
            "start_ts_ms": 1_700_000_000_000,
            "end_ts_ms": 1_700_000_179_999,
            "open": "100.0",
            "high": "101.0",
            "low": "99.0",
            "close": "100.5",
            "volume": "12.0",
            "gap_bars_skipped": 2,
            "is_gap_bar": True,
        },
    }

    gap = extract_gap_status(
        payload,
        default_source="market_data:bar_aggregator",
        default_source_mode=RuntimeBarSourceMode.LIVE,
    )

    assert gap is not None
    assert gap.state == RuntimeGapState.GAP_DETECTED
    assert gap.policy_action == RuntimeGapPolicyAction.DEGRADE_TO_NON_TRADING
    assert gap.gap_bars_skipped == 2
    assert gap.evidence_ref == identity.to_ref()


def test_gap_runtime_statuses_fail_closed_until_repaired() -> None:
    gap = build_gap_status(
        state=RuntimeGapState.GAP_DETECTED,
        policy_action=RuntimeGapPolicyAction.DEGRADE_TO_NON_TRADING,
        gap_bars_skipped=3,
        is_gap_bar=True,
        why=["gap_detected", "gap_bars_skipped:3"],
        detected_at=1_700_000_179_999,
        source="market_data:bar_aggregator",
        evidence_ref="bar:BTCUSDT:180:1700000180000:live",
    )

    basis_status = build_basis_bar_status_from_gap(
        gap,
        updated_at=1_700_000_179_999,
        source="market_data:payload_bridge",
    )
    trading_status = build_trading_status_from_gap(
        gap,
        updated_at=1_700_000_179_999,
        source="decision_making:test",
        allow_open_new_risk=False,
        blocked_why=["protect_only"],
    )

    assert gap_blocks_open_new_risk(gap) is True
    assert basis_status.state.value == "INVALIDATED_GAP"
    assert "basis_bar_gap" in basis_status.why
    assert trading_status.state.value == "BLOCKED"
    assert "protect_only" in trading_status.why
    assert "degrade_to_non_trading" in trading_status.why


def test_repaired_gap_restores_open_new_risk_contract() -> None:
    gap = build_gap_status(
        state=RuntimeGapState.REPAIRED,
        policy_action=RuntimeGapPolicyAction.NONE,
        gap_bars_skipped=2,
        is_gap_bar=False,
        why=["gap_repaired"],
        detected_at=1_700_000_179_999,
        source="bootstrap:repair",
        evidence_ref="repair:BTCUSDT:180:1700000180000",
    )

    basis_status = build_basis_bar_status_from_gap(
        gap,
        updated_at=1_700_000_179_999,
        source="market_data:payload_bridge",
    )
    trading_status = build_trading_status_from_gap(
        gap,
        updated_at=1_700_000_179_999,
        source="decision_making:test",
        allow_open_new_risk=True,
    )

    assert gap_blocks_open_new_risk(gap) is False
    assert basis_status.state.value == "READY"
    assert trading_status.state.value == "READY"


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_bar_closed_schema_accepts_gap_contract_fields() -> None:
    schema = _load_schema("bar_closed_v1.json")
    identity = build_canonical_bar_identity(
        symbol="BTCUSDT",
        timeframe_sec=180,
        bar_start_ts_ms=1_700_000_000_000,
        close_boundary_ts_ms=1_700_000_180_000,
        source_mode=RuntimeBarSourceMode.LIVE,
    )
    payload = {
        "symbol": "BTCUSDT",
        "ts_ms": 1_700_000_180_123,
        "tf_sec": 180,
        "bar_close_ts": 1_700_000_179_999,
        "source_mode": "live",
        "bar_identity": identity.to_payload(),
        "bar": {
            "symbol": "BTCUSDT",
            "timeframe_sec": 180,
            "start_ts_ms": 1_700_000_000_000,
            "end_ts_ms": 1_700_000_179_999,
            "open": "100.0",
            "high": "101.0",
            "low": "99.0",
            "close": "100.5",
            "volume": "12.0",
        },
    }
    attach_gap_status_payload(
        payload,
        gap=build_gap_status(
            state=RuntimeGapState.GAP_DETECTED,
            policy_action=RuntimeGapPolicyAction.DEGRADE_TO_NON_TRADING,
            gap_bars_skipped=2,
            is_gap_bar=True,
            why=["gap_detected"],
            detected_at=1_700_000_179_999,
            source="market_data:bar_aggregator",
            evidence_ref=identity.to_ref(),
        ),
    )
    validate(instance=payload, schema=schema)


@pytest.mark.skipif(not HAS_JSONSCHEMA, reason="jsonschema not installed")
def test_cmd_process_strategy_schema_accepts_gap_contract_fields() -> None:
    with open(CMD_SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)

    payload = {
        "symbol": "BTCUSDT",
        "tf_sec": 180,
        "bar_close_ts": 1_700_000_179_999,
        "bar": {
            "symbol": "BTCUSDT",
            "timeframe_sec": 180,
            "start_ts_ms": 1_700_000_000_000,
            "end_ts_ms": 1_700_000_179_999,
            "open": "100.0",
            "high": "101.0",
            "low": "99.0",
            "close": "100.5",
            "volume": "12.0",
        },
        "features": {},
        "warmup": {"full_ready": True, "ticks_seen": 100},
        "regime": {"regime": "TREND_UP"},
    }
    attach_gap_status_payload(
        payload,
        gap=build_gap_status(
            state=RuntimeGapState.CLEAR,
            policy_action=RuntimeGapPolicyAction.NONE,
            gap_bars_skipped=0,
            is_gap_bar=False,
            why=["contiguous"],
            detected_at=1_700_000_179_999,
            source="market_data:payload_bridge",
            evidence_ref="bar:BTCUSDT:180:1700000180000:live",
        ),
    )
    validate(instance=payload, schema=schema)
