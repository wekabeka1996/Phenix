"""
T1 Timer Governance: Dead-field governance tests.

These tests assert that specific config timer fields in system.yaml have no active
runtime consumers in apps/reference/. If a future package wants to activate them,
it must remove/update this test, add explicit Pydantic ownership, add runtime wiring,
add behavior tests, and produce a T-package report.

Fields guarded:
- hardening.ttl_config.* (entry_place_ttl_ms, bracket_place_ttl_ms, cancel_ttl_ms)
- hardening.retry_config.* (max_tries, retry_config — see NOTEs below for exclusions)
- hawkes.* (decay_beta_ms, eta_max, update_interval_ms, config.hawkes access pattern)

Fields NOT guarded here (intentionally):
- order_index.ttl_sec: T2 wiring target — config declared, consumer NOT yet wired;
  intentionally excluded so T2 can add the wiring without first removing a guard.
- pending_ttl_sec: live in domains.yaml ExposureGuard; dead copies in system/trading
  yaml are a separate SSOT-dedup cleanup (T3), not a dead-field governance issue.
- fill_ttl_ms: active watchdog field — OrderTimeoutWatchdog reads it every cycle.

NOTE — backoff_ms and jitter exclusions from retry_config scan:
  'backoff_ms' as a string literal appears in apps/reference/adapters/binance_adapter.py,
  apps/reference/domains/decision_making/intent/emitter.py, and
  apps/reference/domains/execution_position/adapters/watchdog.py as a local dict key
  reading from execution.fallback config or as an in-memory retry dict key — NOT from
  hardening.retry_config. Including it in the scan would produce false positives.
  'jitter' is a substring of 'jitter_ms' which appears in retry_scheduler.py and
  main.py as an unrelated function parameter.
  The guard for hardening.retry_config uses 'max_tries' and 'retry_config' (the section
  key string) which are sufficiently unique to the hardening section.

NOTE — hawkes field exclusions:
  'window_ms' appears in multiple unrelated runtime paths (feature_engineering,
  config_resolver arbitration logic). 'enabled' is too generic. 'bivariate' appears
  in a code comment in mean_reversion/handler.py (not a config access). These three
  are excluded from the scan. 'config.hawkes' (the attribute access pattern) and the
  three remaining unique names cover any true consumer attempt.
"""

from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APPS_RUNTIME_DIR = REPO_ROOT / "apps" / "reference"

# Excluded from runtime scan: these files may mention field names without consuming them.
# config_models.py: type definitions only (Pydantic Field declarations).
# config_loader.py: loader metadata mapping only, no behavioral consumption.
EXCLUDED_FILES = {
    APPS_RUNTIME_DIR / "config_models.py",
    APPS_RUNTIME_DIR / "config_loader.py",
}


def _scan_runtime_files_for_strings(field_names: list) -> list:
    """
    Returns list of (filepath_relative, lineno, line_stripped) for any
    match of any field_name string found in apps/reference/ Python files,
    excluding EXCLUDED_FILES.
    """
    hits = []
    for py_file in APPS_RUNTIME_DIR.rglob("*.py"):
        if py_file in EXCLUDED_FILES:
            continue
        try:
            text = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            for field in field_names:
                if field in line:
                    hits.append((str(py_file.relative_to(REPO_ROOT)), lineno, line.strip()))
    return hits


# ---------------------------------------------------------------------------
# T1 target field groups — populated from system.yaml hardening.* and hawkes.*
# ---------------------------------------------------------------------------

# system.yaml:hardening.ttl_config
HARDENING_TTL_CONFIG_FIELDS = [
    "entry_place_ttl_ms",
    "bracket_place_ttl_ms",
    "cancel_ttl_ms",
]

# system.yaml:hardening.retry_config
# NOTE: backoff_ms excluded — 'backoff_ms' appears as a local dict key in
#   binance_adapter.py, intent/emitter.py, and watchdog.py for unrelated config paths.
# NOTE: jitter excluded — 'jitter' is a substring of 'jitter_ms' which appears in
#   retry_scheduler.py and main.py as an unrelated function parameter.
# 'max_tries' is unique to the hardening section (zero callsites confirmed).
# 'retry_config' as a string literal does not appear in any runtime file (zero callsites);
#   including it guards against dict-key access patterns like hardening["retry_config"].
HARDENING_RETRY_CONFIG_FIELDS = [
    "max_tries",
    "retry_config",
]

# system.yaml:hawkes.*
# NOTE: window_ms, enabled, bivariate excluded — see module docstring.
# config.hawkes is the attribute access pattern that any true consumer would use.
HAWKES_FIELDS = [
    "decay_beta_ms",
    "eta_max",
    "update_interval_ms",
    "config.hawkes",
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_hardening_ttl_config_has_no_runtime_consumers():
    """
    entry_place_ttl_ms, bracket_place_ttl_ms, cancel_ttl_ms are declared in
    system.yaml hardening.ttl_config but have no active runtime consumers.

    Confirmed dead by T0 audit (AURORA_TIMER_TRUTH_MATRIX_T0.md, F3):
    'No Python runtime code accesses config.hardening, config.system_meta.hardening.ttl_config,
    or the individual placement TTL fields. Confirmed by exhaustive rg scan.'

    If this test fails, a new consumer was added — ensure it is intentional, update
    this test with a T-package report, add explicit Pydantic ownership, and add
    behavior tests for the new wiring.
    """
    hits = _scan_runtime_files_for_strings(HARDENING_TTL_CONFIG_FIELDS)
    assert not hits, (
        "hardening.ttl_config fields found in runtime code — "
        "these were classified as DEAD_PLACEHOLDER in T0 audit (T004, T005, T006). "
        "A new consumer must be intentional: update this test, add Pydantic model "
        "ownership, add behavior tests, and produce a T-package report. "
        f"Hits:\n" + "\n".join(f"  {f}:{ln}  {l}" for f, ln, l in hits)
    )


def test_hardening_retry_config_has_no_runtime_consumers():
    """
    hardening.retry_config.max_tries (and retry_config as a section-key guard) are
    declared in system.yaml but have no active runtime consumers.

    NOTE: hardening.retry_config.backoff_ms is excluded from this scan because the
    string 'backoff_ms' appears as a local dict key in binance_adapter.py, intent/
    emitter.py, and watchdog.py reading from unrelated config paths (NOT hardening).
    NOTE: hardening.retry_config.jitter is excluded because 'jitter' is a substring
    of 'jitter_ms' which appears in retry_scheduler.py and main.py as an unrelated
    function parameter.

    Confirmed dead by T0 audit (AURORA_TIMER_TRUTH_MATRIX_T0.md, T078):
    'Confirmed dead by system_passport.md'
    """
    hits = _scan_runtime_files_for_strings(HARDENING_RETRY_CONFIG_FIELDS)
    assert not hits, (
        "hardening.retry_config fields (max_tries, retry_config) found in runtime code — "
        "these were classified as DEAD_PLACEHOLDER in T0 audit (T078). "
        "A new consumer must be intentional: update this test, add Pydantic model "
        "ownership, add behavior tests, and produce a T-package report. "
        f"Hits:\n" + "\n".join(f"  {f}:{ln}  {l}" for f, ln, l in hits)
    )


def test_hawkes_fields_have_no_runtime_consumers():
    """
    hawkes.* fields (decay_beta_ms, eta_max, update_interval_ms) and the
    config.hawkes access pattern have no active runtime consumers.

    NOTE: window_ms, enabled, bivariate are intentionally excluded from this scan
    to avoid false positives from unrelated runtime code. The scanned fields
    are sufficient to detect any genuine hawkes consumer implementation.

    Confirmed dead by T0 audit (AURORA_TIMER_TRUTH_MATRIX_T0.md, F5, T079):
    'No runtime consumer found (no code accesses config.hawkes outside the loader
    and config_models).'

    If this test fails, a Hawkes process implementation was added — ensure it is
    intentional, update this test with a T-package report, wire the fields through
    a proper typed Pydantic model (not Dict[str, Any]), and add behavior tests.
    """
    hits = _scan_runtime_files_for_strings(HAWKES_FIELDS)
    assert not hits, (
        "hawkes fields found in runtime code — "
        "these were classified as DEAD_PLACEHOLDER in T0 audit (T079). "
        "hawkes.* represents an unimplemented Hawkes process intensity estimator. "
        "A new consumer must be intentional: update this test, replace Dict[str, Any] "
        "with a typed Pydantic model, add behavior tests, produce a T-package report. "
        f"Hits:\n" + "\n".join(f"  {f}:{ln}  {l}" for f, ln, l in hits)
    )
