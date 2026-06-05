from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from apps.reference.domains.neocortex.contracts.failure_taxonomy import (
    FailureOutcomeTaxonomy,
    FailureReasonCode,
    get_failure_outcome_total,
    reset_failure_outcomes,
)
from apps.reference.domains.neocortex.logic.datasets.time_provenance import (
    CausalTimeProvenance,
)
from apps.reference.domains.neocortex.logic.ingest.parsers.core_parser import (
    CoreEventType,
    _extract_field,
    _normalize_epoch_to_ms as _core_normalize_epoch_to_ms,
    extract_position_closes,
    parse_core_log_file,
    parse_core_log_line,
    parse_scientific_notation,
    parse_timestamp,
    parse_timestamp_ms,
)
from apps.reference.domains.neocortex.logic.ingest.parsers.feature_parser import (
    _extract_feature_event_ts_ms,
    _flatten_and_coerce_features,
    _normalize_epoch_to_ms as _feature_normalize_epoch_to_ms,
    parse_feature_log_file,
    parse_feature_log_line,
)
from apps.reference.domains.neocortex.logic.ingest.parsers.order_parser import (
    OrderEventType,
    _normalize_epoch_to_ms as _order_normalize_epoch_to_ms,
    _optional_str,
    parse_order_log_file,
    parse_order_log_line,
)


def setup_function() -> None:
    reset_failure_outcomes()


def test_feature_log_parser_helper_and_causal_branches() -> None:
    assert _feature_normalize_epoch_to_ms(None) is None
    assert _feature_normalize_epoch_to_ms(False) is None
    assert _feature_normalize_epoch_to_ms("bad") is None
    assert _feature_normalize_epoch_to_ms(123.0) is None
    assert _feature_normalize_epoch_to_ms(-1) is None
    assert _feature_normalize_epoch_to_ms(float("nan")) is None
    assert _feature_normalize_epoch_to_ms(1_700_000_000) == 1_700_000_000_000
    assert _feature_normalize_epoch_to_ms(
        1_700_000_000_000) == 1_700_000_000_000

    event_ts_ms, sanitized, source_key = _extract_feature_event_ts_ms(
        {"timestamp": "bad", "ts": 1_700_000_000_000,
            "event_time_source": "captured_wallclock"}
    )
    assert event_ts_ms == 1_700_000_000_000
    assert source_key == "ts"
    assert "ts" not in sanitized

    flattened = _flatten_and_coerce_features(
        {
            "outer.inner": "1.5",
            "outer": {"inner": 2.0},
            1: {"two.three": 4},
            "nested": {"leaf": None},
        }
    )
    assert flattened["outer_inner"] == 1.5
    assert flattened["1_two_three"] == 4.0
    assert flattened["nested_leaf"] == 0.0

    causal = parse_feature_log_line(
        json.dumps(
            {
                "event_ts_ms": 1_700_000_000_000,
                "event_time_source": "captured_wallclock",
                "obi": "0.5",
            }
        ),
        symbol="BTCUSDT",
    )
    assert causal is not None
    assert causal.time_provenance is CausalTimeProvenance.CAPTURED_WALLCLOCK
    assert causal.trainable is False
    assert causal.dataset_visibility == "diagnostics_only"
    assert causal.event_time_is_causal is False

    aurora_event = parse_feature_log_line(
        json.dumps(
            {
                "ts": 1_700_000_000_000,
                "obi": "0.5",
            }
        ),
        symbol="BTCUSDT",
    )
    assert aurora_event is not None
    assert aurora_event.time_provenance is CausalTimeProvenance.AURORA_EVENT
    assert aurora_event.trainable is True
    assert aurora_event.event_time_is_causal is True

    legacy = parse_feature_log_line(
        json.dumps({"obi": "0.5"}),
        symbol="BTCUSDT",
        missing_timestamp_policy="legacy_non_causal_file_offset",
        synthetic_event_ts_ms=1_700_000_000_000,
    )
    assert legacy is not None
    assert legacy.time_provenance is CausalTimeProvenance.FILE_OFFSET_LEGACY
    assert legacy.trainable is False
    assert legacy.dataset_visibility == "diagnostics_only"

    assert (
        parse_feature_log_line(
            json.dumps({"obi": "0.5"}),
            symbol="BTCUSDT",
            missing_timestamp_policy="legacy_non_causal_file_offset",
            synthetic_event_ts_ms=None,
        )
        is None
    )
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.SKIP_ROW,
        reason_code=FailureReasonCode.MISSING_REQUIRED_STATE,
    ) == 1

    with pytest.raises(ValueError, match="Unsupported missing_timestamp_policy"):
        parse_feature_log_line(
            json.dumps({"obi": "0.5"}),
            symbol="BTCUSDT",
            missing_timestamp_policy="unexpected",
        )


def test_feature_log_parser_error_and_file_paths(tmp_path: Path) -> None:
    assert parse_feature_log_line("   ", symbol="BTCUSDT") is None
    assert parse_feature_log_line('{"obi": 1,', symbol="BTCUSDT") is None
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.SKIP_ROW,
        reason_code=FailureReasonCode.MALFORMED_JSON,
    ) == 1

    with patch(
        "apps.reference.domains.neocortex.logic.ingest.parsers.feature_parser.json.loads",
        return_value=[],
    ):
        assert (
            parse_feature_log_line(
                json.dumps(
                    {
                        "event_ts_ms": 1_700_000_000_000,
                        "obi": "0.5",
                    }
                ),
                symbol="BTCUSDT",
            )
            is None
        )

    with patch(
        "apps.reference.domains.neocortex.logic.ingest.parsers.feature_parser.json.loads",
        return_value=[],
    ):
        assert (
            parse_feature_log_line(
                "2026-01-09 12:58:42,585 - module - INFO - Calculated features for BTCUSDT: {\"obi\": \"0.5\"}",
                symbol="BTCUSDT",
            )
            is None
        )

    with patch(
        "apps.reference.domains.neocortex.logic.ingest.parsers.feature_parser.datetime"
    ) as mock_datetime:
        mock_datetime.strptime.side_effect = ValueError("bad timestamp")
        assert (
            parse_feature_log_line(
                "2026-01-09 12:58:42,585 - module - INFO - Calculated features for BTCUSDT: {\"obi\": \"0.5\"}",
                symbol="BTCUSDT",
            )
            is None
        )

    assert (
        parse_feature_log_line(
            "2026-01-09 12:58:42,585 - module - INFO - Calculated features for BTCUSDT: {bad}",
            symbol="BTCUSDT",
        )
        is None
    )

    assert _core_normalize_epoch_to_ms(None) is None
    assert _core_normalize_epoch_to_ms(False) is None
    assert _core_normalize_epoch_to_ms("bad") is None
    assert _core_normalize_epoch_to_ms(123.0) is None
    assert _core_normalize_epoch_to_ms(1_700_000_000) == 1_700_000_000_000
    assert _core_normalize_epoch_to_ms(1_700_000_000_000) == 1_700_000_000_000
    assert _core_normalize_epoch_to_ms(float("inf")) is None
    assert _core_normalize_epoch_to_ms(float("nan")) is None

    parsed = parse_feature_log_line(
        "2026-01-09 12:58:42,585 - module - INFO - Calculated features for BTCUSDT: {\"obi\": \"0.5\"}",
        symbol="BTCUSDT",
    )
    assert parsed is not None
    assert parsed.time_provenance is CausalTimeProvenance.CAPTURED_WALLCLOCK

    duplicate = _flatten_and_coerce_features(
        {"outer.inner": 1.0, "outer": {"inner": 2.0}})
    assert duplicate["outer_inner"] == 1.0

    feature_log = tmp_path / "features.log"
    feature_log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_ts_ms": 1_700_000_000_000,
                        "obi": "0.5",
                    }
                ),
                "2026-01-09 12:58:42,585 - module - INFO - Calculated features for BTCUSDT: {bad}",
            ]
        ),
        encoding="utf-8",
    )
    entries = parse_feature_log_file(feature_log)
    assert len(entries) == 1
    assert entries[0].time_provenance is CausalTimeProvenance.AURORA_EVENT


def test_core_log_parser_helpers_and_structured_branches(tmp_path: Path) -> None:
    assert parse_core_log_line("   ") is None
    assert parse_timestamp_ms("bad") is None
    assert parse_timestamp("bad") == 0.0
    assert parse_timestamp("2026-01-09 12:58:42,585") > 0
    assert parse_scientific_notation("bad") == 0.0
    assert _extract_field('{"symbol":"BTCUSDT"}', "symbol") == "BTCUSDT"
    assert _extract_field("symbol=BTCUSDT", "symbol") == "BTCUSDT"
    assert _core_normalize_epoch_to_ms("bad") is None
    assert _core_normalize_epoch_to_ms(123.0) is None
    assert _core_normalize_epoch_to_ms(-1) is None
    assert _core_normalize_epoch_to_ms(float("nan")) is None
    assert _core_normalize_epoch_to_ms(1_700_000_000) == 1_700_000_000_000
    assert _core_normalize_epoch_to_ms(1_700_000_000_000) == 1_700_000_000_000

    structured_close = parse_core_log_line(
        "2026-01-09 12:58:42,585 - module - INFO - TRADE_CLOSED symbol=BTCUSDT realized_pnl=1.23 realized_pnl_net=1.11 trade_id=t1 close_ts_ms=1700000000000 entry_price=99.5 close_price=100.5 quantity=2 fees=0.01"
    )
    assert structured_close is not None
    assert structured_close.event_type is CoreEventType.TRADE_CLOSED
    assert structured_close.time_source == "close_ts_ms"
    assert structured_close.time_provenance is CausalTimeProvenance.AURORA_EVENT
    assert structured_close.trainable is True
    assert structured_close.realized_pnl == 1.23
    assert structured_close.realized_pnl_net == 1.11
    assert structured_close.entry_price == 99.5
    assert structured_close.close_price == 100.5
    assert structured_close.quantity == 2.0
    assert structured_close.fees == 0.01

    structured_fallback = parse_core_log_line(
        "2026-01-09 12:58:42,585 - module - INFO - POSITION_CLOSED symbol=BTCUSDT realized_pnl_net=1.11 trade_id=t2 entry_price=99.5 close_price=100.5 quantity=2 fees=0.01"
    )
    assert structured_fallback is not None
    assert structured_fallback.event_type is CoreEventType.POSITION_CLOSED
    assert structured_fallback.time_source == "log_timestamp"
    assert structured_fallback.time_provenance is CausalTimeProvenance.CAPTURED_WALLCLOCK

    assert (
        parse_core_log_line(
            "POSITION_CLOSED symbol=BTCUSDT realized_pnl=1.0 trade_id=t3"
        )
        is None
    )
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.SKIP_ROW,
        reason_code=FailureReasonCode.MISSING_REQUIRED_STATE,
    ) >= 1

    position_line = "2026-01-09 12:58:42,585 - module - INFO - [BTCUSDT] Position closed (neutral)"
    position_entry = parse_core_log_line(position_line)
    assert position_entry is not None
    assert position_entry.event_type is CoreEventType.POSITION_CLOSED
    assert position_entry.time_provenance is CausalTimeProvenance.CAPTURED_WALLCLOCK

    assert parse_core_log_line(
        "2026-01-09 12:58:42,585 - module - INFO - POSITION_CLOSED"
    ) is None

    equity_line = (
        "2026-01-09 12:58:42,585 - module - INFO - Emitted positions update: 0 open positions, "
        "totalWalletBalance=293.27, totalUnrealizedProfit=0.0"
    )
    equity_entry = parse_core_log_line(equity_line)
    assert equity_entry is not None
    assert equity_entry.event_type is CoreEventType.EQUITY_UPDATE

    portfolio_line = (
        "2026-01-09 12:58:42,585 - module - INFO - ON_PORTFOLIO_DEBUG: state=ok equity_raw=293.27"
    )
    portfolio_entry = parse_core_log_line(portfolio_line)
    assert portfolio_entry is not None
    assert portfolio_entry.event_type is CoreEventType.PORTFOLIO_UPDATE

    assert parse_core_log_line("unrelated text") is None

    with patch(
        "apps.reference.domains.neocortex.logic.ingest.parsers.core_parser.parse_timestamp_ms",
        return_value=None,
    ):
        assert parse_core_log_line(position_line) is None
        assert parse_core_log_line(equity_line) is None
        assert parse_core_log_line(portfolio_line) is None

    core_log = tmp_path / "core.log"
    core_log.write_text(
        "\n".join(
            [
                position_line,
                equity_line,
                "unrelated text",
            ]
        ),
        encoding="utf-8",
    )
    entries = parse_core_log_file(core_log)
    assert len(entries) == 2
    assert len(extract_position_closes(core_log)) == 1


def test_order_log_parser_helpers_and_branches(tmp_path: Path) -> None:
    assert _order_normalize_epoch_to_ms(None) is None
    assert _order_normalize_epoch_to_ms(False) is None
    assert _order_normalize_epoch_to_ms("bad") is None
    assert _order_normalize_epoch_to_ms(123.0) is None
    assert _order_normalize_epoch_to_ms(-1) is None
    assert _order_normalize_epoch_to_ms(float("nan")) is None
    assert _order_normalize_epoch_to_ms(1_700_000_000) == 1_700_000_000_000
    assert _order_normalize_epoch_to_ms(1_700_000_000_000) == 1_700_000_000_000
    assert _optional_str(None) is None
    assert _optional_str("   ") is None
    assert _optional_str(5) == "5"

    explicit = parse_order_log_line(
        json.dumps(
            {
                "event_ts_ms": 1_700_000_000_000,
                "event_type": "ORDER_INTENT",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "metadata": "oops",
                "adapter_response": ["oops"],
                "trade_id": "T-1",
                "order_id": "O-1",
                "client_order_id": "C-1",
                "rid": "R-1",
                "time_source": "captured_wallclock",
            }
        )
    )
    assert explicit is not None
    assert explicit.event_type is OrderEventType.INTENT
    assert explicit.time_provenance is CausalTimeProvenance.CAPTURED_WALLCLOCK
    assert explicit.metadata == {}
    assert explicit.trade_id == "T-1"
    assert explicit.order_id == "O-1"
    assert explicit.client_order_id == "C-1"
    assert explicit.legacy_rid == "R-1"

    entry = parse_order_log_line(
        json.dumps(
            {
                "event_ts_ms": 1_700_000_000_000,
                "event_type": "ORDER_INTENT",
                "symbol": "BTCUSDT",
                "side": "BUY",
                "metadata": {"order_type": "MARKET_ENTRY"},
            }
        )
    )
    assert entry is not None
    assert entry.is_entry is True

    fallback = parse_order_log_line(
        json.dumps(
            {
                "timestamp": "bad",
                "ts": 1_700_000_000_000,
                "event_type": "NOT_REAL",
                "symbol": "BTCUSDT",
                "side": "SELL",
                "metadata": {"reduce_only": True},
            }
        )
    )
    assert fallback is not None
    assert fallback.event_type is OrderEventType.UNKNOWN
    assert fallback.time_provenance is CausalTimeProvenance.AURORA_EVENT
    assert fallback.is_exit is True
    assert fallback.time_is_causal is True

    assert parse_order_log_line(
        json.dumps(
            {
                "event_type": "ORDER_INTENT",
                "symbol": "BTCUSDT",
                "side": "BUY",
            }
        )
    ) is None
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.SKIP_ROW,
        reason_code=FailureReasonCode.MISSING_REQUIRED_STATE,
    ) == 1

    assert parse_order_log_line("not valid json {{{") is None
    assert get_failure_outcome_total(
        taxonomy=FailureOutcomeTaxonomy.SKIP_ROW,
        reason_code=FailureReasonCode.MALFORMED_JSON,
    ) == 1

    order_log = tmp_path / "orders.log"
    order_log.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "event_ts_ms": 1_700_000_000_000,
                        "event_type": "ORDER_INTENT",
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                    }
                ),
                "",
                json.dumps(
                    {
                        "event_ts_ms": 1_700_000_000_100,
                        "event_type": "ORDER_FILLED",
                        "symbol": "BTCUSDT",
                        "side": "SELL",
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    entries = parse_order_log_file(order_log)
    assert len(entries) == 2
    assert entries[0].event_type is OrderEventType.INTENT
    assert entries[1].event_type is OrderEventType.FILLED
