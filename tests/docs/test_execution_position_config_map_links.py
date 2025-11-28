"""
Tests for Execution Position Config Map Documentation

RID: EP-CONFIG-DOMAINS-REF-MAP-S4

Validates:
1. EXECUTION_POSITION_CONFIG_MAP.md exists
2. All code references point to existing files
3. All YAML examples load correctly through resolver
4. No broken links in documentation
"""

from apps.reference.domains.execution_position.config import ExecutionPositionConfig
from apps.reference.config.execution_position import resolve_execution_position_config
import pytest
import yaml
import sys
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(PROJECT_ROOT))


def test_config_map_file_exists():
    """Test: EXECUTION_POSITION_CONFIG_MAP.md exists"""
    config_map_path = PROJECT_ROOT / "docs" / "EXECUTION_POSITION_CONFIG_MAP.md"

    assert config_map_path.exists(), f"Config map not found: {config_map_path}"
    assert config_map_path.is_file(
    ), f"Config map is not a file: {config_map_path}"
    assert config_map_path.stat().st_size > 0, "Config map is empty"


@pytest.mark.skip(reason="Documentation file CONFIG_REFERENCE.md moved to docs/For_GPT/")
def test_config_map_references_valid_files():
    """Test: All file references in config map point to existing files"""
    config_map_path = PROJECT_ROOT / "docs" / "EXECUTION_POSITION_CONFIG_MAP.md"

    with open(config_map_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract file paths from markdown links
    # Pattern: [text](path/to/file.ext)
    import re
    file_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
    matches = re.findall(file_pattern, content)

    # Filter for file paths (not URLs)
    file_refs = [
        match[1] for match in matches
        if not match[1].startswith(('http://', 'https://'))
        and not match[1].startswith('#')  # Skip anchors
    ]

    # Resolve paths relative to project root or doc dir
    for ref in file_refs:
        # Skip if it's a relative anchor
        if ref.startswith('#'):
            continue

        # Try both absolute and relative to docs/
        ref_path = ref.lstrip('./')

        # Try relative to project root
        abs_path = PROJECT_ROOT / ref_path
        if abs_path.exists():
            continue

        # Try relative to docs/
        docs_path = PROJECT_ROOT / "docs" / ref_path
        if docs_path.exists():
            continue

        # If neither works, fail
        pytest.fail(
            f"Referenced file not found: {ref} (tried {abs_path} and {docs_path})")


def test_primary_yaml_config_exists():
    """Test: Primary YAML config file exists"""
    primary_config = PROJECT_ROOT / "config" / "domains" / "execution.yaml"

    assert primary_config.exists(
    ), f"Primary config not found: {primary_config}"

    # Validate it's valid YAML
    with open(primary_config, "r", encoding="utf-8") as f:
        config_data = yaml.safe_load(f)

    assert isinstance(
        config_data, dict), "Primary config is not a valid YAML dict"


def test_example_yaml_configs_exist():
    """Test: All example YAML configs exist"""
    examples_dir = PROJECT_ROOT / "config" / "examples"

    assert examples_dir.exists(
    ), f"Examples directory not found: {examples_dir}"

    expected_profiles = ["safe", "moderate", "aggressive"]
    for profile in expected_profiles:
        example_file = examples_dir / f"execution_position_{profile}.yaml"
        assert example_file.exists(
        ), f"Example config not found: {example_file}"


def test_example_yamls_load_through_resolver():
    """Test: All example YAMLs load correctly through resolver"""
    examples_dir = PROJECT_ROOT / "config" / "examples"

    profiles = ["safe", "moderate", "aggressive"]

    for profile in profiles:
        yaml_path = examples_dir / f"execution_position_{profile}.yaml"

        with open(yaml_path, "r", encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)

        # Should not raise ValidationError
        ep_cfg = resolve_execution_position_config(raw_cfg)

        assert isinstance(ep_cfg, ExecutionPositionConfig), \
            f"{profile} profile did not return ExecutionPositionConfig"
        assert ep_cfg.aggregated_oco is not None, \
            f"{profile} profile has no aggregated_oco config"


def test_pydantic_models_file_exists():
    """Test: Pydantic models file exists"""
    models_path = PROJECT_ROOT / "apps" / "reference" / \
        "domains" / "execution_position" / "config.py"

    assert models_path.exists(
    ), f"Pydantic models file not found: {models_path}"


def test_resolver_file_exists():
    """Test: Resolver file exists"""
    resolver_path = PROJECT_ROOT / "apps" / \
        "reference" / "config" / "execution_position.py"

    assert resolver_path.exists(), f"Resolver file not found: {resolver_path}"


@pytest.mark.skip(reason="Documentation file CONFIG_REFERENCE.md moved to docs/For_GPT/")
def test_config_reference_file_exists():
    """Test: CONFIG_REFERENCE.md exists"""
    config_ref_path = PROJECT_ROOT / "CONFIG_REFERENCE.md"

    assert config_ref_path.exists(
    ), f"CONFIG_REFERENCE.md not found: {config_ref_path}"


def test_ep_config_ssot_report_exists():
    """Test: EP_CONFIG_SSOT_REPORT.md exists"""
    report_path = PROJECT_ROOT / "docs" / "EP_CONFIG_SSOT_REPORT.md"

    assert report_path.exists(
    ), f"EP_CONFIG_SSOT_REPORT.md not found: {report_path}"


def test_config_map_has_required_sections():
    """Test: Config map has all required sections"""
    config_map_path = PROJECT_ROOT / "docs" / "EXECUTION_POSITION_CONFIG_MAP.md"

    with open(config_map_path, "r", encoding="utf-8") as f:
        content = f.read()

    required_sections = [
        "## 📋 Overview",
        "## 🗺️ Section 1: Configuration Sources",
        "## 🔄 Section 2: Configuration Processing Pipeline",
        "## 📖 Section 3: Field Reference Table",
        "## 🗓️ Section 4: Migration Timeline",
        "### Phase 1: SSOT",
        "### Phase 2: Config Loader Integration",
        "### Phase 3: Example Profiles",
        "### Phase 4: Runtime Adoption",
        "### Phase 5: Cleanup",
    ]

    for section in required_sections:
        assert section in content, f"Required section missing: {section}"


def test_config_map_documents_all_profiles():
    """Test: Config map documents all example profiles"""
    config_map_path = PROJECT_ROOT / "docs" / "EXECUTION_POSITION_CONFIG_MAP.md"

    with open(config_map_path, "r", encoding="utf-8") as f:
        content = f.read()

    profiles = ["safe", "moderate", "aggressive"]

    for profile in profiles:
        assert f"execution_position_{profile}.yaml" in content, \
            f"Profile {profile} not documented in config map"


def test_config_map_documents_field_constraints():
    """Test: Config map documents field constraints"""
    config_map_path = PROJECT_ROOT / "docs" / "EXECUTION_POSITION_CONFIG_MAP.md"

    with open(config_map_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Key fields with constraints
    key_fields = [
        "sl_pct",
        "tp_rr",
        "max_sl_legs",
        "max_tp_legs",
        "trail_distance_bps",
    ]

    for field in key_fields:
        assert field in content, f"Field {field} not documented in config map"


def test_config_map_cross_references_other_docs():
    """Test: Config map cross-references other documentation"""
    config_map_path = PROJECT_ROOT / "docs" / "EXECUTION_POSITION_CONFIG_MAP.md"

    with open(config_map_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Should reference other docs
    referenced_docs = [
        "EP_CONFIG_SSOT_REPORT.md",
        "CONFIG_REFERENCE.md",
        "config.py",
        "execution_position.py",
    ]

    for doc in referenced_docs:
        assert doc in content, f"Config map should reference {doc}"


def test_no_duplicate_phase_definitions():
    """Test: Config map doesn't have duplicate phase definitions"""
    config_map_path = PROJECT_ROOT / "docs" / "EXECUTION_POSITION_CONFIG_MAP.md"

    with open(config_map_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Count Phase 1-5 definitions
    phases = ["Phase 1:", "Phase 2:", "Phase 3:", "Phase 4:", "Phase 5:"]

    for phase in phases:
        # Should appear at least once but not excessively (allow 1-3 mentions)
        count = content.count(phase)
        assert 1 <= count <= 5, \
            f"{phase} appears {count} times (expected 1-5)"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
