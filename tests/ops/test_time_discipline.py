"""
Test Time Discipline (T2B-04).

This test enforces that no direct time.time(), datetime.now(), 
or asyncio.sleep() calls exist in business logic.

Purpose: Ensure deterministic testing and simulation is possible.

Whitelist:
- apps/reference/core/time/clock.py (the source of truth)
- tests/ directory
- ops/ directory (operational tooling)
"""

import os
import re
from pathlib import Path
from typing import List, Set

import pytest


# Directories to scan
SCAN_DIRS = [
    "apps/reference/domains/decision_making",
    "apps/reference/domains/feature_engineering",
    "apps/reference/domains/regime_detector",
]

# Whitelisted files (can use direct time calls)
WHITELIST_PATTERNS = [
    r".*clock\.py$",  # Clock abstraction itself
    r".*/tests/.*",   # Test files
    r".*/ops/.*",     # Operational tooling
    r".*_test\.py$",  # Test files
    r".*test_.*\.py$",  # Test files
]

# Forbidden patterns (enemies of determinism)
FORBIDDEN_PATTERNS = [
    (r"datetime\.now\s*\(", "datetime.now()"),
    (r"datetime\.utcnow\s*\(", "datetime.utcnow()"),
    (r"time\.time\s*\(", "time.time()"),
    (r"time\.monotonic\s*\(", "time.monotonic()"),
]

# Warning patterns (future deprecation)
WARNING_PATTERNS = [
    (r"asyncio\.sleep\s*\(", "asyncio.sleep()"),
    (r"time\.sleep\s*\(", "time.sleep()"),
]

# Legacy files allowed to have time usages (strict limits)
# Format: "rel_path": max_count
# T2B-04: These limits MUST decrease over time as we migrate to Clock abstraction
# T2B-08: Reduced limits after Clock migration for critical QoS/gateway paths
# REG-FIX-01: RegimeDetector migrated to Clock (limit 1→0)
LEGACY_USAGE_LIMITS = {
    "apps/reference/domains/decision_making/decision_making.py": 20,  # T2B-08: reduced from 45→20 after Clock migration
    "apps/reference/domains/decision_making/aurora_handler.py": 3,    # Uses wall_time_fn (injectable)
    "apps/reference/domains/decision_making/mean_reversion_handler.py": 4,  # TODO: migrate to Clock
    "apps/reference/domains/feature_engineering/bar_resampler.py": 2,  # TODO: migrate to Clock
    "apps/reference/domains/decision_making/dm_log_adapter.py": 1,    # TODO: migrate to Clock
    "apps/reference/domains/decision_making/deferred_scheduler.py": 1,  # TODO: migrate to Clock
    "apps/reference/domains/decision_making/trade_intent_reject_wal.py": 2,  # WAL persistence uses wall-clock time
    # REG-FIX-01: RegimeDetector now uses Clock - no time.time() allowed
}


def is_whitelisted(file_path: str) -> bool:
    """Check if file is in whitelist."""
    for pattern in WHITELIST_PATTERNS:
        if re.match(pattern, file_path):
            return True
    return False


def scan_file(file_path: Path, patterns: List[tuple]) -> List[dict]:
    """Scan a file for forbidden patterns.
    
    Returns list of violations.
    """
    violations = []
    
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []
    
    lines = content.split("\n")
    for line_num, line in enumerate(lines, 1):
        # Skip comments
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        
        for pattern, description in patterns:
            if re.search(pattern, line):
                violations.append({
                    "file": str(file_path),
                    "line": line_num,
                    "pattern": description,
                    "content": line.strip()[:100],
                })
    
    return violations


def scan_directory(directory: str, root_path: Path) -> List[dict]:
    """Scan directory for time discipline violations."""
    violations = []
    dir_path = root_path / directory
    
    if not dir_path.exists():
        return []
    
    for py_file in dir_path.rglob("*.py"):
        rel_path = str(py_file.relative_to(root_path))
        
        if is_whitelisted(rel_path):
            continue
        
        # Check for FORBIDDEN patterns
        file_violations = scan_file(py_file, FORBIDDEN_PATTERNS)
        
        # Check limits
        if file_violations:
            limit = LEGACY_USAGE_LIMITS.get(rel_path, 0)
            if len(file_violations) > limit:
                # Add only the excess violations or flag the file
                for v in file_violations:
                     v["limit"] = limit
                     v["count"] = len(file_violations)
                violations.extend(file_violations)
            else:
                # Within limits - OK (legacy)
                pass
    
    return violations


class TestTimeDiscipline:
    """Enforce time discipline in business logic."""
    
    @pytest.fixture
    def root_path(self) -> Path:
        """Get project root path."""
        # Go up from tests/ops to project root
        current = Path(__file__).resolve()
        # Navigate up to find the project root (where apps/ exists)
        for _ in range(5):
            if (current / "apps").exists():
                return current
            current = current.parent
        
        raise RuntimeError("Could not find project root")
    
    def test_no_time_violations_in_business_logic(self, root_path: Path):
        """
        Ensure strict time discipline in business logic.
        
        Forbidden:
        - datetime.now() / utcnow()
        - time.time() (unless in legacy list)
        - time.monotonic() (unless in legacy list)
        
        Use Clock.now_ms() or Clock.now_sec() instead.
        """
        all_violations = []
        
        for directory in SCAN_DIRS:
            violations = scan_directory(directory, root_path)
            all_violations.extend(violations)
        
        if all_violations:
            report_lines = []
            for v in all_violations:
                msg = f"  {v['file']}:{v['line']} - {v['pattern']}: {v['content']}"
                if "limit" in v:
                     msg += f" (Limit: {v['limit']}, Actual: {v['count']})"
                report_lines.append(msg)
            
            report = "\n".join(report_lines)
            
            pytest.fail(
                f"Time discipline violation: Forbidden time functions found.\n"
                f"Use Clock abstraction instead.\n\n{report}"
            )
    
    def test_clock_module_exists(self, root_path: Path):
        """Verify Clock abstraction exists."""
        clock_path = root_path / "apps/reference/core/time/clock.py"
        assert clock_path.exists(), f"Clock module not found at {clock_path}"
    
    def test_clock_has_required_methods(self):
        """Verify Clock has all required methods."""
        from apps.reference.core.time import Clock, LiveClock, MockClock
        
        # Check abstract methods exist
        assert hasattr(Clock, "now_ms")
        assert hasattr(Clock, "now_sec")
        assert hasattr(Clock, "monotonic")
        assert hasattr(Clock, "sleep_ms")
        assert hasattr(Clock, "sleep_sec")
        
        # Check LiveClock implementation
        live = LiveClock()
        assert isinstance(live.now_ms(), int)
        assert isinstance(live.now_sec(), float)
        assert isinstance(live.monotonic(), float)
        
        # Check MockClock implementation
        mock = MockClock(start_ms=1000000)
        assert mock.now_ms() == 1000000
        mock.advance_ms(5000)
        assert mock.now_ms() == 1005000


class TestTimeDisciplineWarnings:
    """Report warnings for time.time() usage (not hard fail yet).
    
    Note: After full migration, these can become hard failures.
    """
    
    @pytest.fixture
    def root_path(self) -> Path:
        """Get project root path."""
        current = Path(__file__).resolve()
        for _ in range(5):
            if (current / "apps").exists():
                return current
            current = current.parent
        raise RuntimeError("Could not find project root")
    
    def test_report_time_usage(self, root_path: Path):
        """
        Report (but don't fail) for time.time() usage.
        
        This is informational during migration phase.
        """
        all_warnings = []
        
        for directory in SCAN_DIRS:
            dir_path = root_path / directory
            if not dir_path.exists():
                continue
            
            for py_file in dir_path.rglob("*.py"):
                rel_path = str(py_file.relative_to(root_path))
                
                if is_whitelisted(rel_path):
                    continue
                
                warnings = scan_file(py_file, WARNING_PATTERNS)
                all_warnings.extend(warnings)
        
        if all_warnings:
            # Group by file
            by_file = {}
            for w in all_warnings:
                fname = w["file"]
                if fname not in by_file:
                    by_file[fname] = 0
                by_file[fname] += 1
            
            report = "\n".join([
                f"  {fname}: {count} usages"
                for fname, count in sorted(by_file.items())
            ])
            
            # This is informational, not a failure (during migration)
            print(f"\n⚠️ TIME USAGE REPORT (T2B-04 Migration Progress):\n{report}")
            print(f"\nTotal: {len(all_warnings)} usages across {len(by_file)} files")
            print("These should migrate to Clock abstraction.")
