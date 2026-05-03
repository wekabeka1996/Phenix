import json
from pathlib import Path

import jsonschema

from apps.reference.domains.execution_position.contract_layer.terminal_order_contracts import (
    normalize_order_rejected_payload,
    normalize_order_state_changed_payload,
)
from apps.reference.telemetry.shadow_journal import build_payload_fragment


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _load_schema(relative_path: str) -> dict:
    path = PROJECT_ROOT / relative_path
    return json.loads(path.read_text(encoding="utf-8"))


def test_normalize_order_rejected_payload_promotes_canonical_fields():
    payload = normalize_order_rejected_payload(
        {
            "symbol": "BNBUSDT",
            "side": "sell",
            "orderId": "12345",
            "clientOrderId": "ENTRY_BNB_1",
            "reason": "maker_only_reject",
            "origin_class": "execution_adapter",
        },
        fallback_rid="rid-1",
        fallback_ts_ms=123456,
    )

    assert payload["symbol"] == "BNBUSDT"
    assert payload["side"] == "SELL"
    assert payload["order_id"] == "12345"
    assert payload["client_order_id"] == "ENTRY_BNB_1"
    assert payload["reject_reason"] == "MAKER_ONLY_REJECT"
    assert payload["reject_reason_normalized"] == "MAKER_ONLY_REJECT"
    assert payload["reject_reason_source"] == "reason"
    assert payload["origin_class"] == "execution_adapter"
    assert payload["terminal_non_fill"] is True
    assert payload["terminal_state_kind"] == "REJECTED"
    assert payload["identity_quality"] == "order_identity_exact"
    assert payload["event_ts_ms"] == 123456


def test_normalize_order_state_changed_payload_marks_terminal_non_fill():
    payload = normalize_order_state_changed_payload(
        {
            "symbol": "BTCUSDT",
            "orderId": "o2",
            "client_order_id": "c1",
            "status": "canceled",
        },
        fallback_ts_ms=10000,
    )

    assert payload["status"] == "CANCELED"
    assert payload["terminal_non_fill"] is True
    assert payload["terminal_state_kind"] == "CANCELED"
    assert payload["identity_quality"] == "order_identity_exact"
    assert payload["canonical_identity_key"] == (
        "evt:order_state_changed:symbol=BTCUSDT:order_id=o2:client_order_id=c1:terminal_state=CANCELED"
    )


def test_shadow_payload_fragment_keeps_canonical_terminal_order_fields():
    fragment = build_payload_fragment(
        {
            "symbol": "BTCUSDT",
            "orderId": "o2",
            "client_order_id": "c1",
            "status": "CANCELED",
            "event_ts_ms": 10000,
            "terminal_non_fill": True,
            "terminal_state_kind": "CANCELED",
            "origin_class": "execution_adapter",
            "identity_quality": "order_identity_exact",
            "canonical_identity_key": "evt:order_state_changed:symbol=BTCUSDT:order_id=o2",
            "reject_reason_normalized": "MAKER_ONLY_REJECT",
            "compatibility_aliases_retained": True,
        }
    )

    assert fragment["terminal_non_fill"] is True
    assert fragment["terminal_state_kind"] == "CANCELED"
    assert fragment["origin_class"] == "execution_adapter"
    assert fragment["identity_quality"] == "order_identity_exact"
    assert fragment["canonical_identity_key"] == "evt:order_state_changed:symbol=BTCUSDT:order_id=o2"
    assert fragment["reject_reason_normalized"] == "MAKER_ONLY_REJECT"
    assert fragment["compatibility_aliases_retained"] is True


def test_terminal_non_fill_schemas_accept_normalized_payloads():
    order_rejected_schema = _load_schema(
        "apps/reference/domains/execution_position/schemas/order_rejected_v1.json"
    )
    order_state_changed_schema = _load_schema(
        "apps/reference/domains/execution_position/schemas/order_state_changed_v1.json"
    )

    rejected_payload = normalize_order_rejected_payload(
        {
            "symbol": "BNBUSDT",
            "rid": "rid-1",
            "reason_code": "ADAPTER_ERROR",
            "reason_text": "timeout",
            "origin_class": "execution_adapter",
        },
        fallback_ts_ms=1,
    )
    state_changed_payload = normalize_order_state_changed_payload(
        {
            "symbol": "BTCUSDT",
            "orderId": "o2",
            "status": "EXPIRED",
        },
        fallback_ts_ms=2,
    )

    jsonschema.validate(instance=rejected_payload, schema=order_rejected_schema)
    jsonschema.validate(instance=state_changed_payload, schema=order_state_changed_schema)
