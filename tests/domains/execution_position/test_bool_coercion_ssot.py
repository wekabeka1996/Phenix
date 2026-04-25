"""
BOOL-COERCE-02: Tests for canonical exchange bool coercion helper.

Proves:
 1. coerce_exchange_bool correctly handles all Binance-realistic inputs.
 2. Native bool pass-through (True/False).
 3. String coercion: "true"/"false" (case-insensitive).
 4. None → False.
 5. Edge cases: empty string, whitespace, int 0/1.
 6. The helper is deterministic and side-effect free.
 7. Production consumers import from the canonical helper.
"""
from __future__ import annotations

import pytest

from apps.reference.domains.execution_position.utils import coerce_exchange_bool


# ---- Core contract tests ----


class TestCoerceExchangeBoolContract:
    """Each input type must produce the documented output."""

    # --- Native bool ---

    def test_true_passthrough(self):
        assert coerce_exchange_bool(True) is True

    def test_false_passthrough(self):
        assert coerce_exchange_bool(False) is False

    # --- String (Binance canonical forms) ---

    def test_string_true_lowercase(self):
        assert coerce_exchange_bool("true") is True

    def test_string_false_lowercase(self):
        assert coerce_exchange_bool("false") is False

    def test_string_true_uppercase(self):
        assert coerce_exchange_bool("TRUE") is True

    def test_string_false_uppercase(self):
        assert coerce_exchange_bool("FALSE") is False

    def test_string_true_mixed_case(self):
        assert coerce_exchange_bool("True") is True

    def test_string_false_mixed_case(self):
        assert coerce_exchange_bool("False") is False

    # --- None ---

    def test_none_returns_false(self):
        assert coerce_exchange_bool(None) is False

    # --- Empty / whitespace strings ---

    def test_empty_string_returns_false(self):
        assert coerce_exchange_bool("") is False

    def test_whitespace_string_returns_false(self):
        assert coerce_exchange_bool("  ") is False

    def test_string_true_with_whitespace(self):
        assert coerce_exchange_bool(" true ") is True

    # --- Integer fallback (via bool()) ---

    def test_int_zero_returns_false(self):
        assert coerce_exchange_bool(0) is False

    def test_int_one_returns_true(self):
        assert coerce_exchange_bool(1) is True

    # --- Unrecognized strings are False, not truthy ---

    def test_string_yes_returns_false(self):
        """'yes' is NOT a Binance exchange bool — must be False."""
        assert coerce_exchange_bool("yes") is False

    def test_string_one_returns_false(self):
        """String '1' is NOT 'true' — must be False."""
        assert coerce_exchange_bool("1") is False

    def test_string_arbitrary_returns_false(self):
        assert coerce_exchange_bool("maybe") is False


# ---- Binance realistic payload simulation ----


class TestBinancePayloadSimulation:
    """Simulate payloads as they arrive from Binance REST/WS."""

    def test_rest_open_orders_bool_true(self):
        """Binance REST /openOrders returns native bool."""
        order = {"reduceOnly": True, "closePosition": False}
        assert coerce_exchange_bool(order["reduceOnly"]) is True
        assert coerce_exchange_bool(order["closePosition"]) is False

    def test_ws_order_update_string(self):
        """Binance WS ORDER_TRADE_UPDATE may send string."""
        payload = {"reduceOnly": "true", "closePosition": "false"}
        assert coerce_exchange_bool(payload["reduceOnly"]) is True
        assert coerce_exchange_bool(payload["closePosition"]) is False

    def test_missing_key_with_get_default(self):
        """dict.get() returns None for missing keys — must coerce to False."""
        payload = {}
        assert coerce_exchange_bool(payload.get("reduceOnly")) is False
        assert coerce_exchange_bool(payload.get("closePosition")) is False

    def test_mixed_types_in_single_payload(self):
        """One field bool, another string — both must coerce correctly."""
        payload = {"reduceOnly": True, "closePosition": "true"}
        assert coerce_exchange_bool(payload["reduceOnly"]) is True
        assert coerce_exchange_bool(payload["closePosition"]) is True


# ---- Determinism and idempotency ----


class TestDeterminism:
    """Helper must be stateless and deterministic."""

    @pytest.mark.parametrize(
        "value",
        [True, False, "true", "false", None, "", 0, 1],
    )
    def test_repeated_calls_same_result(self, value):
        first = coerce_exchange_bool(value)
        second = coerce_exchange_bool(value)
        assert first is second


# ---- Consumer import verification (drift guard) ----


class TestConsumerImportDriftGuard:
    """Verify that production consumers import from the canonical location."""

    _CONSUMER_FILES = [
        "apps/reference/domains/execution_position/order_guardian.py",
        "apps/reference/domains/execution_position/bracket_health.py",
        "apps/reference/domains/execution_position/fsm_manage.py",
        "apps/reference/domains/execution_position/close_executor.py",
    ]

    @pytest.mark.parametrize("filepath", _CONSUMER_FILES)
    def test_consumer_imports_coerce_exchange_bool(self, filepath: str):
        """Each consumer file must import coerce_exchange_bool."""
        from pathlib import Path
        source = Path(filepath).read_text(encoding="utf-8")
        assert "coerce_exchange_bool" in source, (
            f"{filepath} does not import coerce_exchange_bool"
        )

    @pytest.mark.parametrize("filepath", _CONSUMER_FILES)
    def test_no_inline_str_lower_true_pattern(self, filepath: str):
        """No consumer should contain inline '.lower() == \"true\"' for reduceOnly/closePosition."""
        from pathlib import Path
        import re
        source = Path(filepath).read_text(encoding="utf-8")
        # Find inline bool coercion patterns (not inside comments)
        lines = source.splitlines()
        violations = []
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if '.lower() == "true"' in line and ("reduceOnly" in line or "closePosition" in line or "close_position" in line or "reduce_only" in line):
                violations.append(f"  line {i}: {line.strip()}")
        assert not violations, (
            f"{filepath} still has inline bool coercion:\n" +
            "\n".join(violations)
        )
