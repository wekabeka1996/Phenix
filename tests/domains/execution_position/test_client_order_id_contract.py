"""Tests for the execution_position clientOrderId contract."""

from apps.reference.domains.execution_position.utils import (
    ClientOrderIntent,
    build_bracket_client_ids,
    build_client_order_id,
    parse_client_order_id,
)


def test_build_client_order_id_structure() -> None:
    meta = build_client_order_id(
        intent=ClientOrderIntent.STOP_LOSS,
        rid="RID-123",
        symbol="BTCUSDT",
        decision_id="dec-456",
        extra="unit",
    )

    assert meta.raw.startswith("ep")
    assert len(meta.raw) <= 36

    parsed = parse_client_order_id(meta.raw)
    assert parsed is not None
    assert parsed.intent == ClientOrderIntent.STOP_LOSS
    assert parsed.bundle_key() == meta.bundle_key()


def test_build_bracket_client_ids_share_bundle() -> None:
    entry, sl_meta, tp_meta = build_bracket_client_ids(
        rid="RID-789",
        symbol="ETHUSDT",
        decision_id="dec-789",
    )

    assert entry.bundle_key() == sl_meta.bundle_key() == tp_meta.bundle_key()
    assert sl_meta.intent == ClientOrderIntent.STOP_LOSS
    assert tp_meta.intent == ClientOrderIntent.TAKE_PROFIT


def test_parse_client_order_id_legacy_suffix() -> None:
    legacy_sl = "abc123_sl"
    meta = parse_client_order_id(legacy_sl)

    assert meta is not None
    assert meta.intent == ClientOrderIntent.STOP_LOSS
    assert meta.bundle_key() == "legacy:abc123"
