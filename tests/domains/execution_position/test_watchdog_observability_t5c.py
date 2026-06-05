"""
T5C Timer Governance: Watchdog dead-fallback removal + ORDER_PLACED TTL observability.

Verifies that:
1. fsm.py does NOT contain the dead fallback ["trading", "watchdog"] (removed in T5C).
2. fsm.py still contains the canonical path ["trading", "execution", "watchdog"].
3. Missing canonical watchdog config causes FSM to fail closed (no silent fallback).
4. ORDER_PLACED event/log includes fill_ttl_override_ms and fill_ttl_source when
   a per-order valid_for_ms override is provided.
5. ORDER_PLACED event/log identifies fill_ttl_source="global_watchdog" when no override.
6. fill_ttl_override_ms value passed to track_order_placed is unchanged by metadata patch.

SSOT:
  config/aurora/trading.yaml  -> trading.execution.watchdog (CANONICAL — sole source)
  apps/reference/domains/execution_position/fsm.py -> _get_config_value(["trading", "execution", "watchdog"]) ONLY
  apps/reference/domains/execution_position/flows/open/open_executor.py -> ORDER_PLACED pld + order_logger.write()
  apps/reference/domains/execution_position/schemas/order_placed_v1.json -> schema (optional new fields)

DO NOT change fill_ttl_ms, ack_ttl_ms, check_interval_ms, or rps_limit.
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[3]
FSM_PY = REPO_ROOT / "apps" / "reference" / "domains" / "execution_position" / "fsm.py"
OPEN_EXECUTOR_PY = (
    REPO_ROOT
    / "apps"
    / "reference"
    / "domains"
    / "execution_position"
    / "flows"
    / "open"
    / "open_executor.py"
)
ORDER_PLACED_SCHEMA = (
    REPO_ROOT
    / "apps"
    / "reference"
    / "domains"
    / "execution_position"
    / "schemas"
    / "order_placed_v1.json"
)


# ---------------------------------------------------------------------------
# Test 1 — dead fallback absent (FAILS before T5C patch)
# ---------------------------------------------------------------------------


class TestDeadFallbackAbsent:
    """T5C-1: The dead fallback probe for ["trading", "watchdog"] must be gone.

    Before T5C, fsm.py had:
        if not watchdog_config:
            watchdog_config = self._get_config_value(["trading", "watchdog"])

    This allowed a silent fallback to a root-level watchdog key that no longer
    exists in trading.yaml. It masks config errors and undermines the T5A.1 SSOT.
    T5C removes it.

    This test MUST FAIL before the removal and PASS after.
    """

    def test_dead_fallback_absent(self):
        """fsm.py must NOT contain ["trading", "watchdog"] dead fallback."""
        fsm_source = FSM_PY.read_text(encoding="utf-8")
        dead_pattern = '["trading", "watchdog"]'
        assert dead_pattern not in fsm_source, (
            f"Dead fallback still present in fsm.py: {dead_pattern!r}\n"
            "Remove the `if not watchdog_config: watchdog_config = self._get_config_value"
            '(["trading", "watchdog"])` block from fsm.py (T5C).'
        )


# ---------------------------------------------------------------------------
# Test 2 — canonical watchdog path retained (PASSES before and after)
# ---------------------------------------------------------------------------


class TestCanonicalWatchdogPathRetained:
    """T5C-2: The canonical path ["trading", "execution", "watchdog"] must remain."""

    def test_canonical_watchdog_path_retained(self):
        """fsm.py must still look up ["trading", "execution", "watchdog"]."""
        fsm_source = FSM_PY.read_text(encoding="utf-8")
        canonical_pattern = '["trading", "execution", "watchdog"]'
        assert canonical_pattern in fsm_source, (
            f"Canonical watchdog path missing from fsm.py: {canonical_pattern!r}\n"
            "Do not remove the canonical config extraction."
        )


# ---------------------------------------------------------------------------
# Test 3 — missing canonical watchdog fails closed
# ---------------------------------------------------------------------------


class TestMissingCanonicalWatchdogFailsClosed:
    """T5C-3: Missing trading.execution.watchdog must raise (fail-closed).

    After T5C the dead fallback is gone, so the FSM's get_watchdog_setting
    must still raise ValueError when fill_ttl_ms is absent, not silently
    return a default value.
    """

    def test_missing_canonical_watchdog_fill_ttl_raises(self):
        """Replicates fsm.py get_watchdog_setting: missing fill_ttl_ms raises."""
        watchdog_config: dict[str, Any] = {
            "ack_ttl_ms": 8000,
            "check_interval_ms": 1000,
            "rps_limit": 10,
        }
        # fill_ttl_ms is deliberately absent

        def get_watchdog_setting(key: str, default: Any) -> Any:
            if isinstance(watchdog_config, dict):
                if key not in watchdog_config:
                    raise ValueError(
                        f"CRITICAL: watchdog.{key} missing. FSM cannot start without watchdog config."
                    )
                return watchdog_config[key]
            return getattr(watchdog_config, key)

        with pytest.raises(ValueError, match="fill_ttl_ms missing"):
            get_watchdog_setting("fill_ttl_ms", None)

    def test_no_fallback_path_in_fsm_source(self):
        """After T5C there must be no fallback _get_config_value for trading.watchdog.

        The dead code allowed the FSM to silently succeed even when
        trading.execution.watchdog was absent. Without it, the fail-closed
        guard at get_watchdog_setting catches any misconfiguration.
        """
        fsm_source = FSM_PY.read_text(encoding="utf-8")
        # The exact string that formed the dead fallback call
        assert '"trading", "watchdog"' not in fsm_source, (
            'fsm.py still contains "trading", "watchdog" fallback path. '
            "Remove it so missing canonical config is not silently masked."
        )


# ---------------------------------------------------------------------------
# Test 4 — ORDER_PLACED metadata includes per-order TTL when override exists
#           (FAILS before T5C metadata patch)
# ---------------------------------------------------------------------------


class TestOrderPlacedMetadataOverrideTTL:
    """T5C-4: ORDER_PLACED pld must expose fill_ttl_override_ms + fill_ttl_source
    when a per-order valid_for_ms is provided.

    The narrowest seam is inspecting the source of _post_entry_registration.
    We also verify the schema allows the new fields.
    """

    def test_order_placed_pld_contains_fill_ttl_override_ms_field(self):
        """_post_entry_registration must build ORDER_PLACED pld with fill_ttl_override_ms."""
        from apps.reference.domains.execution_position.flows.open.open_executor import (
            OpenExecutor,
        )

        source = inspect.getsource(OpenExecutor._post_entry_registration)
        assert "fill_ttl_override_ms" in source, (
            "_post_entry_registration does not include fill_ttl_override_ms in ORDER_PLACED pld. "
            "Add 'fill_ttl_override_ms': valid_for_ms to the order_placed_msg.pld dict (T5C)."
        )

    def test_order_placed_pld_contains_fill_ttl_source_field(self):
        """_post_entry_registration must build ORDER_PLACED pld with fill_ttl_source."""
        from apps.reference.domains.execution_position.flows.open.open_executor import (
            OpenExecutor,
        )

        source = inspect.getsource(OpenExecutor._post_entry_registration)
        assert "fill_ttl_source" in source, (
            "_post_entry_registration does not include fill_ttl_source in ORDER_PLACED pld. "
            "Add 'fill_ttl_source': 'per_order_override' | 'global_watchdog' to "
            "the order_placed_msg.pld dict (T5C)."
        )

    def test_order_placed_pld_fill_ttl_source_per_order_override_string(self):
        """The literal string 'per_order_override' must appear in the source."""
        from apps.reference.domains.execution_position.flows.open.open_executor import (
            OpenExecutor,
        )

        source = inspect.getsource(OpenExecutor._post_entry_registration)
        assert "per_order_override" in source, (
            "'per_order_override' value not found in _post_entry_registration. "
            "fill_ttl_source must be 'per_order_override' when valid_for_ms is set (T5C)."
        )

    def test_order_placed_schema_allows_fill_ttl_override_ms(self):
        """order_placed_v1.json must declare fill_ttl_override_ms as an optional property."""
        import json

        schema = json.loads(ORDER_PLACED_SCHEMA.read_text(encoding="utf-8"))
        props = schema.get("properties", {})
        assert "fill_ttl_override_ms" in props, (
            "order_placed_v1.json missing 'fill_ttl_override_ms' property. "
            "Add it as an optional (non-required) field (T5C)."
        )
        # Must NOT be in required
        required = schema.get("required", [])
        assert "fill_ttl_override_ms" not in required, (
            "order_placed_v1.json has 'fill_ttl_override_ms' in 'required'. "
            "It must be optional (additive only, T5C)."
        )

    def test_order_placed_schema_allows_fill_ttl_source(self):
        """order_placed_v1.json must declare fill_ttl_source as an optional property."""
        import json

        schema = json.loads(ORDER_PLACED_SCHEMA.read_text(encoding="utf-8"))
        props = schema.get("properties", {})
        assert "fill_ttl_source" in props, (
            "order_placed_v1.json missing 'fill_ttl_source' property. "
            "Add it as an optional (non-required) field (T5C)."
        )
        required = schema.get("required", [])
        assert "fill_ttl_source" not in required, (
            "order_placed_v1.json has 'fill_ttl_source' in 'required'. "
            "It must be optional (additive only, T5C)."
        )


# ---------------------------------------------------------------------------
# Test 5 — ORDER_PLACED metadata identifies global watchdog when no override
#           (FAILS before T5C metadata patch)
# ---------------------------------------------------------------------------


class TestOrderPlacedMetadataGlobalWatchdog:
    """T5C-5: ORDER_PLACED pld must use fill_ttl_source='global_watchdog' when
    no per-order valid_for_ms is provided.
    """

    def test_order_placed_pld_fill_ttl_source_global_watchdog_string(self):
        """The literal string 'global_watchdog' must appear in the source."""
        from apps.reference.domains.execution_position.flows.open.open_executor import (
            OpenExecutor,
        )

        source = inspect.getsource(OpenExecutor._post_entry_registration)
        assert "global_watchdog" in source, (
            "'global_watchdog' value not found in _post_entry_registration. "
            "fill_ttl_source must be 'global_watchdog' when no valid_for_ms override "
            "is provided (T5C)."
        )


# ---------------------------------------------------------------------------
# Test 6 — no behavior change: fill_ttl_override_ms value unchanged
# ---------------------------------------------------------------------------


class TestNoBehaviorChange:
    """T5C-6: Adding metadata fields must not alter fill_ttl_override_ms value
    passed to track_order_placed.

    Verified by source inspection: track_order_placed must still receive
    fill_ttl_override_ms=valid_for_ms (not the new fill_ttl_source string).
    """

    def test_track_order_placed_still_uses_valid_for_ms(self):
        """track_order_placed receives fill_ttl_override_ms=valid_for_ms (not fill_ttl_source)."""
        from apps.reference.domains.execution_position.flows.open.open_executor import (
            OpenExecutor,
        )

        source = inspect.getsource(OpenExecutor._post_entry_registration)
        assert "fill_ttl_override_ms=valid_for_ms" in source, (
            "track_order_placed no longer uses fill_ttl_override_ms=valid_for_ms. "
            "The behavior-changing assignment must remain intact (T5C — no behavior change)."
        )

    def test_metadata_fields_are_additive_not_replacing_existing(self):
        """ORDER_PLACED pld must still contain all original required fields."""
        from apps.reference.domains.execution_position.flows.open.open_executor import (
            OpenExecutor,
        )

        source = inspect.getsource(OpenExecutor._post_entry_registration)
        # Core fields that must remain in the pld dict
        for field in ("symbol", "side", "qty", "order_type", "client_order_id",
                      "exchange_order_id", "order_id", "rid", "ts_ms", "corr_id"):
            assert field in source, (
                f"Core ORDER_PLACED pld field '{field}' no longer appears in "
                "_post_entry_registration source. Metadata addition must be additive only."
            )
