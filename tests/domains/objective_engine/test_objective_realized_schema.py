from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator
from jsonschema.exceptions import ValidationError

from apps.reference.domains.objective_engine.realized_types import (
    ObjectiveRealizedEvent,
)


SCHEMA_PATH = Path(
    "apps/reference/domains/objective_engine/schemas/objective_realized_v1.json"
)


def _load_schema() -> dict:
    with SCHEMA_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _valid_payload() -> dict:
    event = ObjectiveRealizedEvent(
        strategy_id="aurora",
        symbol="BTCUSDT",
        entry_rid="entry-rid-1",
        close_rid="close-rid-1",
        regime_entry="TREND_UP",
        regime_exit="MEAN_REVERSION",
        pretrade_objective_trace={
            "trace_id": "obj-1",
            "multiplier": 0.9,
            "objective_score": 0.45,
            "components": {"cost": -0.1, "risk": -0.05},
        },
        realized_components={
            "realized_pnl_efficiency": 0.7,
            "duration_efficiency": 0.8,
        },
        realized_quality_score=0.75,
        realized_pnl=15.0,
        fees=0.5,
        duration_sec=600.0,
        mae=-1.0,
        mfe=2.0,
        close_reason="TP_HIT",
        signal_id="sig-1",
    )
    return event.model_dump()


def test_objective_realized_schema_compiles() -> None:
    Draft7Validator.check_schema(_load_schema())


def test_objective_realized_valid_payload_passes_validation() -> None:
    validator = Draft7Validator(_load_schema())
    validator.validate(_valid_payload())


def test_objective_realized_missing_required_field_rejects() -> None:
    validator = Draft7Validator(_load_schema())
    payload = _valid_payload()
    del payload["close_reason"]

    with pytest.raises(ValidationError, match="close_reason"):
        validator.validate(payload)


def test_objective_realized_unknown_field_rejects() -> None:
    validator = Draft7Validator(_load_schema())
    payload = _valid_payload()
    payload["unexpected_field"] = "boom"

    with pytest.raises(ValidationError, match="unexpected_field"):
        validator.validate(payload)
