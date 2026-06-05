"""Tests for vfoundation.core.schema_validator — Phase 3.2."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from vfoundation.core.schema_validator import SchemaValidator, patch_emit_validation


# ── Helpers ──────────────────────────────────────────────────────────

def _repo_root() -> Path:
    """Return repo root (contains pytest.ini)."""
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pytest.ini").exists():
            return parent
    raise RuntimeError("Cannot detect repo root")


def _valid_bar_closed_pld() -> Dict[str, Any]:
    """Minimal valid payload for EVT:BAR_CLOSED."""
    return {
        "symbol": "BTCUSDT",
        "ts_ms": 1700000000000,
        "tf_sec": 300,
        "bar_close_ts": 1700000300000,
        "bar": {
            "symbol": "BTCUSDT",
            "timeframe_sec": 300,
            "start_ts_ms": 1700000000000,
            "end_ts_ms": 1700000300000,
            "open": "42000.00",
            "high": "42100.00",
            "low": "41900.00",
            "close": "42050.00",
            "volume": "1.5",
        },
    }


# ── SchemaValidator tests ────────────────────────────────────────────

class TestSchemaValidator:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.validator = SchemaValidator(repo_root=_repo_root())

    def test_loads_some_schemas(self) -> None:
        verbs = self.validator.registered_verbs_with_schema()
        assert len(verbs) >= 3, f"Expected ≥3 schemas loaded, got {len(verbs)}"

    def test_bar_closed_has_schema(self) -> None:
        assert self.validator.has_schema("EVT", "BAR_CLOSED")

    def test_unknown_verb_has_no_schema(self) -> None:
        assert not self.validator.has_schema("CMD", "NONEXISTENT_VERB_XYZ")

    def test_valid_bar_closed_passes(self) -> None:
        errors = self.validator.validate("EVT", "BAR_CLOSED", _valid_bar_closed_pld())
        assert errors == []

    def test_missing_required_field_fails(self) -> None:
        pld = _valid_bar_closed_pld()
        del pld["symbol"]
        errors = self.validator.validate("EVT", "BAR_CLOSED", pld)
        assert len(errors) == 1
        assert "symbol" in errors[0].lower()

    def test_wrong_type_fails(self) -> None:
        pld = _valid_bar_closed_pld()
        pld["ts_ms"] = "not_a_number"
        errors = self.validator.validate("EVT", "BAR_CLOSED", pld)
        assert len(errors) == 1

    def test_no_schema_returns_empty(self) -> None:
        """Verbs without schema always pass validation (lenient)."""
        errors = self.validator.validate("CMD", "CLOSE", {"anything": True})
        assert errors == []


# ── patch_emit_validation tests ──────────────────────────────────────

class _FakeBus:
    """Minimal FSMCore stand-in for testing patch_emit_validation."""

    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict, str]] = []

    def emit(self, event_name: str, payload: dict, why: str, data_ref: list | None = None) -> None:
        self.emitted.append((event_name, payload, why))


class TestPatchEmitValidation:
    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.validator = SchemaValidator(repo_root=_repo_root())

    def test_valid_payload_passes_through(self) -> None:
        bus = _FakeBus()
        patch_emit_validation(bus, self.validator)
        bus.emit("EVT:BAR_CLOSED", _valid_bar_closed_pld(), "test")
        assert len(bus.emitted) == 1

    def test_invalid_payload_in_fail_open_mode(self) -> None:
        """Default: log warning but still emit."""
        bus = _FakeBus()
        patch_emit_validation(bus, self.validator, strict=False)
        bus.emit("EVT:BAR_CLOSED", {"bad": True}, "test")
        assert len(bus.emitted) == 1  # Still emitted

    def test_invalid_payload_in_strict_mode(self) -> None:
        """Strict: skip emit on validation error."""
        bus = _FakeBus()
        patch_emit_validation(bus, self.validator, strict=True)
        bus.emit("EVT:BAR_CLOSED", {"bad": True}, "test")
        assert len(bus.emitted) == 0  # Dropped

    def test_no_schema_passes_in_strict_mode(self) -> None:
        """Verbs without schema should not be blocked even in strict mode."""
        bus = _FakeBus()
        patch_emit_validation(bus, self.validator, strict=True)
        bus.emit("EVT:SOME_UNKNOWN_VERB", {"any": "data"}, "test")
        assert len(bus.emitted) == 1
