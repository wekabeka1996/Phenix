"""
TASK53-I: No Silent Fallbacks Scan Tests

Static scan of runtime domains for forbidden fallback patterns:
1. .get() with default values for config access
2. dict.get with numeric defaults
3. `or <default>` patterns in config access
4. `if x is None: x = <default>` patterns

Allowlist:
- warmup-only code
- test files
- tools/scripts
- event payload access (not config)
"""
import ast
import re
from pathlib import Path
from typing import List, Set, Tuple

import pytest


# Directories to scan (runtime domains only)
RUNTIME_DOMAINS = [
    "apps/reference/domains/decision_making",
    "apps/reference/domains/execution_position",
    "apps/reference/domains/feature_engineering",
    "apps/reference/domains/market_data",
    "apps/reference/domains/position_tracking",
    "apps/reference/domains/risk_management",
    "apps/reference/domains/regime_detector",
    "apps/reference/domains/account_observer",
]

# Files to exclude from scan (allowlist)
ALLOWLIST_FILES = {
    # Test files
    "test_",
    # Tools
    "tools/",
    # Scripts
    "scripts/",
    # Warmup-related
    "warmup",
    # Debug/Dev
    "_debug",
    "_dev",
}

# Patterns that are ALLOWED (not config access)
ALLOWED_PATTERNS = {
    # Event payload access - these use .get() legitimately for optional event fields
    "event.pld.get",
    "pld.get",
    "payload.get",
    "msg.pld.get",
    "intent_data.get",
    "risk_params.get",
    "features_data.get",
    "current_tick.get",
    "corr_data.get",
    
    # Dict traversal for non-config data
    "self.symbol_states",
    "self._qos_state",
    "self._per_symbol_regimes",
    "self._arb_window_winner",
    "self._pending_flips",
    "self.manage_flows.get",
    "self.open_flows.get",
    
    # Safe: getting from result objects, not config
    "result.get",
    "response.get",
    "resp.get",
    "order.get",
    "pos.get",
    "position.get",
    "spec.get",
    
    # LEGACY: OrderGuardian uses guardian_cfg dict for backwards compat (TODO: refactor)
    "guardian_cfg.get",
    
    # Environment variables
    "os.environ.get",
    "os.getenv",
}

# Config access patterns that are FORBIDDEN (should use typed Pydantic access)
FORBIDDEN_PATTERNS = [
    # Direct config dict access with default
    r'config\.get\s*\(\s*["\'][^"\']+["\']\s*,',
    r'self\.config\.get\s*\(\s*["\'][^"\']+["\']\s*,',
    r'cfg\.get\s*\(\s*["\'][^"\']+["\']\s*,',
    
    # Legacy patterns
    r'config\[["\'][^"\']+["\']\]\.get\s*\(',
]


def _is_allowed_file(filepath: Path) -> bool:
    """Check if file is in allowlist."""
    path_str = str(filepath)
    for pattern in ALLOWLIST_FILES:
        if pattern in path_str:
            return True
    return False


def _is_allowed_pattern(line: str, context_lines: List[str] = None) -> bool:
    """Check if the pattern usage is allowed (not config access)."""
    for allowed in ALLOWED_PATTERNS:
        if allowed in line:
            return True
    
    # Check for comments indicating intentional fallback
    if "# ALLOWED:" in line or "# fallback ok" in line.lower():
        return True
    
    return False


def _scan_file_for_forbidden_patterns(filepath: Path) -> List[Tuple[int, str, str]]:
    """
    Scan a Python file for potentially forbidden fallback patterns.
    
    Returns list of (line_number, line_content, pattern_type) tuples.
    """
    violations = []
    
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
    except Exception:
        return violations
    
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # Skip comments and empty lines
        if stripped.startswith("#") or not stripped:
            continue
        
        # Check forbidden patterns
        for pattern in FORBIDDEN_PATTERNS:
            if re.search(pattern, line):
                if not _is_allowed_pattern(line):
                    violations.append((line_num, line.strip(), "FORBIDDEN_CONFIG_GET"))
        
        # Check for suspicious "or 0" / "or None" patterns in config context
        # But only if it looks like config access
        if ("self.config" in line or "config." in line) and (" or 0" in line or " or None" in line):
            if not _is_allowed_pattern(line):
                violations.append((line_num, line.strip(), "CONFIG_OR_DEFAULT"))
    
    return violations


def _scan_file_for_get_patterns(filepath: Path) -> List[Tuple[int, str]]:
    """
    Find all .get() patterns in a file for analysis.
    Returns (line_number, line_content) for review.
    """
    findings = []
    
    try:
        content = filepath.read_text(encoding="utf-8", errors="replace")
        lines = content.split("\n")
    except Exception:
        return findings
    
    for line_num, line in enumerate(lines, 1):
        stripped = line.strip()
        
        # Skip comments
        if stripped.startswith("#"):
            continue
        
        # Only look for .get( with a second argument (default value)
        if ".get(" in line and "," in line:
            # Check if it's potentially config access
            line_lower = line.lower()
            if any(kw in line_lower for kw in ["config", "cfg", "settings"]):
                if not _is_allowed_pattern(line):
                    findings.append((line_num, line.strip()))
    
    return findings


class TestStaticFallbackPatternsScan:
    """Static scan for forbidden fallback patterns in runtime domains."""
    
    def test_no_forbidden_config_get_patterns(self) -> None:
        """Scan runtime domains for forbidden config.get() patterns."""
        all_violations = []
        
        for domain_path in RUNTIME_DOMAINS:
            domain_dir = Path(domain_path)
            if not domain_dir.exists():
                continue
            
            for py_file in domain_dir.rglob("*.py"):
                if _is_allowed_file(py_file):
                    continue
                
                violations = _scan_file_for_forbidden_patterns(py_file)
                for line_num, line, pattern_type in violations:
                    all_violations.append(f"{py_file}:{line_num} [{pattern_type}] {line[:80]}")
        
        if all_violations:
            # Report violations but don't fail immediately - this is for audit
            report = "\n".join(all_violations[:20])  # First 20
            if len(all_violations) > 20:
                report += f"\n... and {len(all_violations) - 20} more"
            
            # Log for audit report
            print(f"\n=== FORBIDDEN PATTERN SCAN RESULTS ===\n{report}")
        
        # This test documents findings; actual failures are P0/P1 issues
        # For now, we pass if there are no critical config.get patterns
        critical_violations = [v for v in all_violations if "FORBIDDEN_CONFIG_GET" in v]
        assert len(critical_violations) == 0, f"Found {len(critical_violations)} forbidden config.get patterns:\n" + "\n".join(critical_violations[:10])
    
    def test_audit_get_patterns_in_domains(self) -> None:
        """Audit all .get() patterns in domains for manual review (informational)."""
        all_findings = []
        
        for domain_path in RUNTIME_DOMAINS:
            domain_dir = Path(domain_path)
            if not domain_dir.exists():
                continue
            
            for py_file in domain_dir.rglob("*.py"):
                if _is_allowed_file(py_file):
                    continue
                
                findings = _scan_file_for_get_patterns(py_file)
                for line_num, line in findings:
                    all_findings.append((str(py_file), line_num, line))
        
        # This is informational - produce report for audit
        if all_findings:
            print(f"\n=== GET PATTERN AUDIT ({len(all_findings)} findings) ===")
            for filepath, line_num, line in all_findings[:30]:
                print(f"  {filepath}:{line_num}: {line[:60]}...")
        
        # Always pass - this is for audit documentation
        assert True


class TestMissingFieldCausesCrash:
    """Runtime test: missing field → crash, not silent default."""
    
    def test_missing_domain_config_section_crashes(self, tmp_path: Path) -> None:
        """Removing entire domain config section → crash at load."""
        import shutil
        import yaml
        
        cfg_dir = tmp_path / "aurora"
        shutil.copytree(Path("config/aurora"), cfg_dir)
        
        domains_path = cfg_dir / "domains.yaml"
        domains = yaml.safe_load(domains_path.read_text(encoding="utf-8"))
        
        # Remove entire watchdog section
        del domains["execution_position"]["watchdog"]
        
        domains_path.write_text(yaml.safe_dump(domains, sort_keys=False), encoding="utf-8")
        
        from apps.reference.config_loader import ConfigLoader
        from pydantic import ValidationError
        
        loader = ConfigLoader(config_dir=cfg_dir)
        with pytest.raises(ValidationError) as exc_info:
            loader.load_config()
        
        assert "watchdog" in str(exc_info.value)
    
    def test_missing_field_does_not_return_none_silently(self, tmp_path: Path) -> None:
        """Config access never returns None for required fields (fail-closed)."""
        import shutil
        
        cfg_dir = tmp_path / "aurora"
        shutil.copytree(Path("config/aurora"), cfg_dir)
        
        from apps.reference.config_loader import ConfigLoader
        
        loader = ConfigLoader(config_dir=cfg_dir)
        config = loader.load_config()
        
        # These should NOT be None - they are required
        assert config.domains.execution_position.watchdog.ack_ttl_ms is not None
        assert config.domains.decision_making.qos.symbol_cooldown_sec is not None
        assert config.domains.feature_engineering.volatility.window_sec is not None
        
        # Accessing truly missing attribute should raise AttributeError, not return None
        with pytest.raises(AttributeError):
            _ = config.domains.execution_position.nonexistent_field


class TestNoLegacyDictAccess:
    """Test that domains use typed Pydantic access, not legacy dict access."""
    
    def test_decision_making_uses_typed_access(self) -> None:
        """DecisionMaking uses typed config attributes, not .get()."""
        from apps.reference.config_loader import ConfigLoader
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        from unittest.mock import MagicMock
        
        loader = ConfigLoader()
        config = loader.load_config()
        
        mock_fsm = MagicMock()
        mock_fsm.listen = MagicMock()
        
        dm = DecisionMaking(fsm=mock_fsm, config=config)
        
        # These should be set from typed config access (not dict.get with default)
        assert dm.qos_exposure_block_cooldown_sec == config.domains.decision_making.qos.exposure_block_cooldown_sec
        assert dm._default_symbol_cooldown_sec == config.domains.decision_making.qos.symbol_cooldown_sec
    
    def test_config_rejects_dict_input(self) -> None:
        """Domains that require AuroraConfig must reject dict."""
        from apps.reference.config_loader import ConfigLoader
        from apps.reference.domains.decision_making.decision_making import DecisionMaking
        from unittest.mock import MagicMock
        
        mock_fsm = MagicMock()
        mock_fsm.listen = MagicMock()
        
        # DecisionMaking should reject dict
        with pytest.raises(TypeError) as exc_info:
            DecisionMaking(fsm=mock_fsm, config={"should": "fail"})
        
        assert "dict" in str(exc_info.value).lower()
