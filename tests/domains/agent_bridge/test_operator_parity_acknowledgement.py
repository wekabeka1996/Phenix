from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from apps.reference.domains.agent_bridge.exchange_info import PublicExchangeInfoSymbolV0
from apps.reference.domains.agent_bridge.parity_governance import (
    ACK_FILENAME,
    FilterParityHistoryStore,
    OperatorParityAcknowledgementInputV0,
    OperatorParityAcknowledgementsFileV0,
    validate_operator_acknowledgement,
)


NOW = 1_800_000_000_000
DAY_MS = 24 * 60 * 60 * 1000


def _instrument(*, tick="0.1", step="0.001", qty="0.001", notional="100"):
    return SimpleNamespace(
        tick_size=Decimal(tick), step_size=Decimal(step),
        min_qty=Decimal(qty), min_notional=Decimal(notional),
    )


def _runtime(instrument):
    return SimpleNamespace(config=SimpleNamespace(instruments={"BTCUSDT": instrument}))


def _exchange(*, freshness="fresh", step="0.0001", qty="0.0001", notional="50"):
    return PublicExchangeInfoSymbolV0(
        symbol="BTCUSDT", source_ts_ms=NOW - 100, fetched_ts_ms=NOW,
        freshness=freshness, tick_size="0.1", step_size=step,
        min_qty=qty, min_notional=notional,
    )


def _entry(
    state_ref: str,
    *,
    symbol="BTCUSDT",
    environment="testnet",
    parity_status="conservative_mismatch",
    compatibility="compatible_conservative",
    ack_status="acknowledged_conservative",
    created=NOW,
    expires=NOW + 30 * DAY_MS,
    review_by=NOW + 30 * DAY_MS,
):
    return {
        "schema_version": "operator-parity-acknowledgement/v0",
        "ack_id": "ack_btcusdt_20260701_001",
        "operator_id": "operator.market-risk.1",
        "operator_display_name": "Market Risk Reviewer",
        "created_ts_ms": created,
        "expires_ts_ms": expires,
        "symbol": symbol,
        "venue": "binance_usdm",
        "environment": environment,
        "state_ref": state_ref,
        "parity_status": parity_status,
        "compatibility_assessment": compatibility,
        "ack_status": ack_status,
        "ack_reason": "Reviewed exact conservative filter drift; no configuration relaxation.",
        "review_required_by_ts_ms": review_by,
        "provenance": {
            "source": "operator_authored_offline_file",
            "format_version": "v0",
        },
    }


def _write(path: Path, entry: dict, *, pretty=False) -> None:
    document = {
        "schema_version": "filter-parity-operator-acknowledgements/v0",
        "acknowledgements": [entry],
    }
    path.write_text(
        json.dumps(document, indent=2 if pretty else None), encoding="utf-8"
    )


def _conservative_state(store: FilterParityHistoryStore, ts=NOW):
    return store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument()), exchange=_exchange(),
        environment="testnet", observed_ts_ms=ts,
    )


def test_model_requires_identity_expiry_reason_and_forbids_trade_authority_status() -> None:
    with pytest.raises(ValidationError):
        OperatorParityAcknowledgementInputV0.model_validate(
            {**_entry("state"), "operator_id": ""}
        )
    with pytest.raises(ValidationError, match="30 days"):
        OperatorParityAcknowledgementInputV0.model_validate(
            {**_entry("state"), "expires_ts_ms": NOW + 31 * DAY_MS,
             "review_required_by_ts_ms": NOW + 31 * DAY_MS}
        )
    with pytest.raises(ValidationError):
        OperatorParityAcknowledgementInputV0.model_validate(
            {**_entry("state"), "ack_status": "acknowledged_ok_to_trade"}
        )


def test_valid_conservative_ack_has_identity_expiry_and_normalized_hash(tmp_path: Path) -> None:
    store = FilterParityHistoryStore(tmp_path)
    state = _conservative_state(store)
    entry = _entry(state.state_ref)
    _write(tmp_path / ACK_FILENAME, entry, pretty=False)
    compact = store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument()), exchange=_exchange(),
        environment="testnet", observed_ts_ms=NOW + 1,
    )
    first_hash = compact.operator_ack_file_hash
    assert compact.operator_ack_status == "acknowledged_conservative"
    assert compact.operator_ack_validation_status == "valid"
    assert compact.operator_id == "operator.market-risk.1"
    assert compact.operator_ack_expires_ts_ms == NOW + 30 * DAY_MS
    assert compact.operator_ack_provenance_ref.endswith(first_hash)

    _write(tmp_path / ACK_FILENAME, entry, pretty=True)
    pretty = store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument()), exchange=_exchange(),
        environment="testnet", observed_ts_ms=NOW + 2,
    )
    assert pretty.operator_ack_file_hash == first_hash


def test_wrong_state_env_and_symbol_are_rejected(tmp_path: Path) -> None:
    store = FilterParityHistoryStore(tmp_path)
    state = _conservative_state(store)
    _write(tmp_path / ACK_FILENAME, _entry(state.state_ref + "-old"))
    mismatched = store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument()), exchange=_exchange(),
        environment="testnet", observed_ts_ms=NOW + 1,
    )
    assert (mismatched.operator_ack_status, mismatched.operator_ack_validation_status) == (
        "expired", "state_mismatch"
    )

    input_model = OperatorParityAcknowledgementInputV0.model_validate(
        _entry(state.state_ref, symbol="ETHUSDT")
    )
    rejected = validate_operator_acknowledgement(
        input_model, expected_symbol="BTCUSDT", expected_venue="binance_usdm",
        expected_environment="testnet", expected_state_ref=state.state_ref,
        expected_parity_status="conservative_mismatch",
        expected_compatibility="compatible_conservative", observed_ts_ms=NOW + 1,
        file_hash="0" * 64,
    )
    assert (rejected.validation_status, rejected.invalid_reason) == ("rejected", "wrong_symbol")

    _write(tmp_path / ACK_FILENAME, _entry(state.state_ref, environment="live"))
    wrong_env = store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument()), exchange=_exchange(),
        environment="testnet", observed_ts_ms=NOW + 2,
    )
    assert (wrong_env.operator_ack_status, wrong_env.operator_ack_invalid_reason) == (
        "rejected", "wrong_environment"
    )


def test_expiry_and_review_due_are_fail_closed(tmp_path: Path) -> None:
    store = FilterParityHistoryStore(tmp_path)
    state = _conservative_state(store)
    _write(tmp_path / ACK_FILENAME, _entry(
        state.state_ref, created=NOW - 2 * DAY_MS,
        expires=NOW + DAY_MS, review_by=NOW - 1,
    ))
    expired = store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument()), exchange=_exchange(),
        environment="testnet", observed_ts_ms=NOW,
    )
    assert (expired.operator_ack_status, expired.operator_ack_validation_status) == (
        "expired", "expired"
    )


def test_risky_ack_requires_review_and_never_removes_authority_block(tmp_path: Path) -> None:
    store = FilterParityHistoryStore(tmp_path)
    runtime = _runtime(_instrument(step="0.00001", qty="0.00001", notional="10"))
    risky = store.observe(
        symbol="BTCUSDT", runtime=runtime, exchange=_exchange(),
        environment="testnet", observed_ts_ms=NOW,
    )
    _write(tmp_path / ACK_FILENAME, _entry(
        risky.state_ref, parity_status="risky_mismatch",
        compatibility="incompatible_or_looser",
        ack_status="acknowledged_requires_review",
    ))
    reviewed = store.observe(
        symbol="BTCUSDT", runtime=runtime, exchange=_exchange(),
        environment="testnet", observed_ts_ms=NOW + 1,
    )
    assert reviewed.operator_ack_status == "acknowledged_requires_review"
    assert reviewed.operator_ack_validation_status == "valid"
    assert reviewed.requires_yaml_review is True
    assert reviewed.requires_execution_block_before_authority is True


def test_stale_or_missing_never_accepts_ack_and_match_is_not_required(tmp_path: Path) -> None:
    store = FilterParityHistoryStore(tmp_path)
    stale = store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument()),
        exchange=_exchange(freshness="stale"), environment="testnet", observed_ts_ms=NOW,
    )
    _write(tmp_path / ACK_FILENAME, _entry(
        stale.state_ref, parity_status="stale", compatibility="not_assessable",
        ack_status="rejected",
    ))
    stale_checked = store.observe(
        symbol="BTCUSDT", runtime=_runtime(_instrument()),
        exchange=_exchange(freshness="stale"), environment="testnet", observed_ts_ms=NOW + 1,
    )
    assert stale_checked.operator_ack_status == "rejected"
    assert stale_checked.operator_ack_validation_status == "rejected"
    assert stale_checked.requires_execution_block_before_authority is True

    match = store.observe(
        symbol="BTCUSDT",
        runtime=_runtime(_instrument(step="0.0001", qty="0.0001", notional="50")),
        exchange=_exchange(), environment="testnet", observed_ts_ms=NOW + 2,
    )
    assert match.operator_ack_status == "not_required"
    assert match.operator_ack_validation_status == "not_required"


def test_duplicate_ack_ids_make_manifest_invalid() -> None:
    entry = _entry("state")
    with pytest.raises(ValidationError, match="unique"):
        OperatorParityAcknowledgementsFileV0.model_validate({
            "schema_version": "filter-parity-operator-acknowledgements/v0",
            "acknowledgements": [entry, entry],
        })
