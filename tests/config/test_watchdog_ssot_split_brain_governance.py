"""T5A.1 Timer Governance: Watchdog config SSOT split-brain fix.

Enforces:
1. trading.execution.watchdog.* is the single canonical YAML path.
2. system.yaml execution.watchdog.* is absent (noncanonical copy removed).
3. ExecPosFSM does NOT resolve watchdog from system path first.
4. Non-default fill_ttl_ms via trading path propagates into watchdog instance.
5. Noncanonical system value cannot override the canonical trading value.
6. Missing canonical watchdog config fails closed (no silent fallback to defaults).

Tests 2 and 3 MUST FAIL before the T5A.1 fix is applied.
Tests 2 and 3 MUST PASS after the T5A.1 fix is applied.

SSOT after fix:
  config/aurora/trading.yaml -> trading.execution.watchdog.*
  apps/reference/domains/execution_position/fsm.py -> _get_config_value(["trading", "execution", "watchdog"]) only
  apps/reference/config_models.py -> ExecutionConfig.watchdog: Optional[WatchdogConfig] = Field(default=None)

DO NOT change fill_ttl_ms, ack_ttl_ms, check_interval_ms, or rps_limit.
"""
from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
TRADING_YAML = REPO_ROOT / "config" / "aurora" / "trading.yaml"
SYSTEM_YAML = REPO_ROOT / "config" / "aurora" / "system.yaml"
FSM_PY = REPO_ROOT / "apps" / "reference" / \
    "domains" / "execution_position" / "fsm.py"

# Canonical values — current calibrated watchdog SSOT
CANONICAL_ACK_TTL_MS = 8_000
CANONICAL_FILL_TTL_MS = 1_800_000
CANONICAL_CHECK_INTERVAL_MS = 1_000
CANONICAL_RPS_LIMIT = 10

# ---------------------------------------------------------------------------
# Test 1 — canonical trading watchdog exists and holds correct values
# ---------------------------------------------------------------------------


class TestCanonicalTradingWatchdogExists:
    """T5A.1-1: trading.execution.watchdog.* must exist with correct canonical values."""

    def test_canonical_trading_watchdog_exists(self):
        """trading.execution.watchdog must be present in trading.yaml.

        SSOT: config/aurora/trading.yaml -> trading.execution.watchdog.*
        All four keys (ack_ttl_ms, fill_ttl_ms, check_interval_ms, rps_limit) must
        be present and match canonical values.
        """
        raw = yaml.safe_load(TRADING_YAML.read_text(encoding="utf-8"))
        watchdog = (
            (raw.get("trading") or {})
            .get("execution", {})
            .get("watchdog")
        )

        assert watchdog is not None, (
            "trading.yaml is missing trading.execution.watchdog block. "
            "This is the canonical SSOT path for watchdog config."
        )
        assert isinstance(watchdog, dict), (
            f"trading.execution.watchdog must be a dict, got {type(watchdog)!r}"
        )

        for key, expected in [
            ("ack_ttl_ms", CANONICAL_ACK_TTL_MS),
            ("fill_ttl_ms", CANONICAL_FILL_TTL_MS),
            ("check_interval_ms", CANONICAL_CHECK_INTERVAL_MS),
            ("rps_limit", CANONICAL_RPS_LIMIT),
        ]:
            assert key in watchdog, (
                f"trading.execution.watchdog.{key} is missing from trading.yaml. "
                f"Expected canonical value: {expected}."
            )
            assert watchdog[key] == expected, (
                f"trading.execution.watchdog.{key} = {watchdog[key]!r}, "
                f"expected {expected!r}."
            )


# ---------------------------------------------------------------------------
# Test 2 — noncanonical system watchdog ABSENT
# ---------------------------------------------------------------------------


class TestNoncanonicalSystemWatchdogAbsent:
    """T5A.1-2: system.yaml must NOT contain execution.watchdog block.

    THIS TEST MUST FAIL before the T5A.1 cleanup and PASS after.
    """

    def test_noncanonical_system_watchdog_absent(self):
        """system.yaml execution.watchdog must be absent after T5A.1 SSOT fix.

        Before fix: system.yaml has execution.watchdog.* (split-brain source).
        After fix: system.yaml execution.watchdog block is removed.

        CANONICAL source is trading.yaml -> trading.execution.watchdog.*
        """
        raw = yaml.safe_load(SYSTEM_YAML.read_text(encoding="utf-8"))
        system_execution = raw.get("execution") or {}
        system_watchdog = system_execution.get("watchdog")

        assert system_watchdog is None, (
            "NONCANONICAL watchdog block still present in system.yaml at "
            "execution.watchdog. This is the T5A.1 split-brain duplicate. "
            "Remove execution.watchdog from system.yaml. "
            "Canonical source is trading.yaml -> trading.execution.watchdog.*\n"
            f"Found: {system_watchdog!r}"
        )


# ---------------------------------------------------------------------------
# Test 3 — ExecPosFSM does NOT use system path first
# ---------------------------------------------------------------------------


class TestFsmNotUsingSystemPathFirst:
    """T5A.1-3: fsm.py must not contain the system-first watchdog lookup pattern.

    THIS TEST MUST FAIL before the T5A.1 FSM fix and PASS after.
    """

    def test_fsm_not_using_system_path_first(self):
        """fsm.py must not contain _get_config_value(["execution", "watchdog"]) as watchdog source.

        Before fix: fsm.py probes ["execution", "watchdog"] (system path) first,
        then falls back to ["trading", "execution", "watchdog"] (trading path).
        After fix: only ["trading", "execution", "watchdog"] is used.

        Pattern checked: the string '["execution", "watchdog"]' (system path lookup)
        must not appear in the FSM watchdog initialization block.
        """
        source = FSM_PY.read_text(encoding="utf-8")

        # This is the exact system-first lookup that must be removed.
        # After the fix, only ["trading", "execution", "watchdog"] is used.
        system_first_pattern = '["execution", "watchdog"]'

        assert system_first_pattern not in source, (
            f"fsm.py still contains the system-first watchdog lookup pattern: "
            f"  _get_config_value({system_first_pattern!r})\n"
            "This reads execution.watchdog (system.yaml path) before the canonical "
            "trading.execution.watchdog (trading.yaml path). "
            "Remove this lookup and use ONLY _get_config_value([\"trading\", \"execution\", \"watchdog\"])."
        )

    def test_fsm_uses_canonical_trading_path_for_watchdog(self):
        """fsm.py must contain _get_config_value(["trading", "execution", "watchdog"]).

        After the T5A.1 fix, the canonical trading path must be present and be the
        only watchdog resolution path in the FSM.
        """
        source = FSM_PY.read_text(encoding="utf-8")

        canonical_pattern = '["trading", "execution", "watchdog"]'
        assert canonical_pattern in source, (
            "fsm.py does not contain the canonical watchdog lookup: "
            f"  _get_config_value({canonical_pattern!r})\n"
            "After T5A.1, this must be the sole watchdog resolution path in the FSM."
        )


# ---------------------------------------------------------------------------
# Test 4 — non-default fill_ttl_ms via trading path propagates into watchdog
# ---------------------------------------------------------------------------


class TestNonDefaultTradingFillTtlPropagates:
    """T5A.1-4: fill_ttl_ms set in trading.execution.watchdog must propagate to FSM.

    This test uses the real ConfigLoader with tmp_path to mutate trading.yaml
    and verify the non-default value reaches the Pydantic model.
    """

    def test_nondefault_trading_fill_ttl_propagates(self, tmp_path: Path):
        """Sentinel fill_ttl_ms=12345 via trading.execution.watchdog reaches config.

        Sets trading.execution.watchdog.fill_ttl_ms=12345 in a temp copy of
        trading.yaml and confirms it is accessible as config.trading.execution.watchdog.fill_ttl_ms.
        This proves the canonical trading path is read by the config loader.
        """
        import shutil
        from apps.reference.config_loader import ConfigLoader

        cfg_dir = tmp_path / "aurora"
        shutil.copytree(REPO_ROOT / "config" / "aurora", cfg_dir)

        trading_path = cfg_dir / "trading.yaml"
        trading = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
        trading["trading"]["execution"]["watchdog"]["fill_ttl_ms"] = 12345
        trading_path.write_text(yaml.safe_dump(
            trading, sort_keys=False), encoding="utf-8")

        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()

        assert config.trading.execution.watchdog.fill_ttl_ms == 12345, (
            f"Expected config.trading.execution.watchdog.fill_ttl_ms == 12345, "
            f"got {config.trading.execution.watchdog.fill_ttl_ms!r}. "
            "The canonical trading.execution.watchdog path must propagate through "
            "ConfigLoader -> TradingConfig -> ExecutionConfig -> WatchdogConfig."
        )


# ---------------------------------------------------------------------------
# Test 5 — noncanonical system value cannot override trading (structural)
# ---------------------------------------------------------------------------


class TestNoncanonicalSystemCannotOverrideTrading:
    """T5A.1-5: system.execution.watchdog is structurally rejected or absent.

    After the T5A.1 fix, there is no system.execution.watchdog block to contest
    the canonical trading value. This test verifies the absence makes an override
    structurally impossible.
    """

    def test_noncanonical_system_watchdog_structurally_absent(self):
        """system.yaml has no execution.watchdog block after T5A.1 fix.

        If system.execution.watchdog is absent, it cannot override trading.execution.watchdog.
        The split-brain is eliminated structurally, not by precedence rules.
        """
        raw = yaml.safe_load(SYSTEM_YAML.read_text(encoding="utf-8"))
        system_watchdog = (raw.get("execution") or {}).get("watchdog")

        assert system_watchdog is None, (
            "system.yaml still has execution.watchdog; split-brain possible. "
            "T5A.1 requires removal of the noncanonical duplicate."
        )

    def test_fsm_system_path_not_consulted_as_primary(self):
        """fsm.py must not probe execution.watchdog (system path) as primary source.

        After T5A.1, the FSM uses only ["trading", "execution", "watchdog"].
        Any code path that reads ["execution", "watchdog"] first would allow
        system.yaml to override trading.yaml values.
        """
        source = FSM_PY.read_text(encoding="utf-8")

        # The system-first pattern must be absent
        assert '["execution", "watchdog"]' not in source, (
            "fsm.py still probes the system path first (execution.watchdog). "
            "Remove _get_config_value([\"execution\", \"watchdog\"]) from the watchdog "
            "initialization block in fsm.py."
        )

    def test_execution_config_watchdog_is_optional_not_required(self):
        """ExecutionConfig.watchdog must be Optional with default=None after T5A.1.

        Before T5A.1: ExecutionConfig.watchdog = Optional[WatchdogConfig] = Field(...)
        forces system.yaml (and trading.yaml) to always provide the watchdog block.
        After T5A.1: ExecutionConfig.watchdog = Optional[WatchdogConfig] = Field(default=None)
        makes system.yaml watchdog truly optional (can be absent without validation error).
        """
        from apps.reference.config_models import ExecutionConfig

        field_info = ExecutionConfig.model_fields.get("watchdog")
        assert field_info is not None, "ExecutionConfig.watchdog field is missing entirely."

        is_required = field_info.is_required()
        assert not is_required, (
            "ExecutionConfig.watchdog is still Required (Field(...)). "
            "After T5A.1, it must be Optional with default=None "
            "so that system.yaml execution block can omit the watchdog key. "
            "Change to: watchdog: Optional[WatchdogConfig] = Field(default=None)"
        )


# ---------------------------------------------------------------------------
# Test 6 — missing canonical watchdog config fails closed
# ---------------------------------------------------------------------------


class TestMissingCanonicalWatchdogFailsClosed:
    """T5A.1-6: Missing trading.execution.watchdog must fail config load, not silently default."""

    def test_missing_trading_watchdog_produces_none_not_default(self, tmp_path: Path):
        """Removing trading.execution.watchdog yields None on config, not a silent default.

        After T5A.1, ExecutionConfig.watchdog is Optional[WatchdogConfig] with
        default=None (changed from Field(...) required). This is necessary so that
        system.yaml's execution block can parse without watchdog.

        When trading.yaml watchdog is absent:
          - config.trading.execution.watchdog is None (not a default WatchdogConfig)
          - OrderTimeoutWatchdog is NOT instantiated with silent constructor defaults
          - FSM raises ValueError at init (see test_fsm_get_watchdog_setting_raises_on_missing_key
            in test_watchdog_ttl_governance.py for the FSM-level fail-closed proof)

        This test verifies absence produces None (not a silent default dict/object).
        """
        import shutil
        from apps.reference.config_loader import ConfigLoader

        cfg_dir = tmp_path / "aurora"
        shutil.copytree(REPO_ROOT / "config" / "aurora", cfg_dir)

        # Remove the entire watchdog block from trading.yaml
        trading_path = cfg_dir / "trading.yaml"
        trading = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
        execution = trading["trading"]["execution"]
        del execution["watchdog"]
        trading_path.write_text(yaml.safe_dump(
            trading, sort_keys=False), encoding="utf-8")

        # Config load succeeds (Optional field allows None)
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()

        # Result must be None — no silent default WatchdogConfig
        watchdog = config.trading.execution.watchdog
        assert watchdog is None, (
            f"Expected config.trading.execution.watchdog to be None when "
            f"trading.yaml watchdog block is absent. Got: {watchdog!r}. "
            "ExecutionConfig.watchdog must NOT silently produce a default "
            "WatchdogConfig when the key is missing. "
            "The FSM raises ValueError when watchdog is None (fail-closed at init)."
        )

    def test_missing_fill_ttl_ms_in_canonical_watchdog_fails_closed(self, tmp_path: Path):
        """Missing fill_ttl_ms inside trading.execution.watchdog must fail config load.

        WatchdogConfig.fill_ttl_ms is Field(...) (required, no default).
        Omitting it from trading.yaml must raise ValidationError — not silently
        use the OrderTimeoutWatchdog constructor default (30000).
        """
        import shutil
        from pydantic import ValidationError
        from apps.reference.config_loader import ConfigLoader

        cfg_dir = tmp_path / "aurora"
        shutil.copytree(REPO_ROOT / "config" / "aurora", cfg_dir)

        # Remove fill_ttl_ms from trading.yaml watchdog section
        trading_path = cfg_dir / "trading.yaml"
        trading = yaml.safe_load(trading_path.read_text(encoding="utf-8"))
        del trading["trading"]["execution"]["watchdog"]["fill_ttl_ms"]
        trading_path.write_text(yaml.safe_dump(
            trading, sort_keys=False), encoding="utf-8")

        with pytest.raises((ValidationError, ValueError)) as exc_info:
            loader = ConfigLoader(config_dir=cfg_dir)
            loader.load_config()

        error_str = str(exc_info.value).lower()
        assert "fill_ttl_ms" in error_str or "watchdog" in error_str, (
            f"Config load did not fail with fill_ttl_ms-related error. "
            f"Got: {exc_info.value!r}. "
            "WatchdogConfig.fill_ttl_ms must be Field(...) with no default."
        )
