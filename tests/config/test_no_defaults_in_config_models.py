"""
Test for zero defaults policy in config models.

TASK20: CFG-ZERO-DEFAULTS-INVENTORY-AND-GATE-P1-20
"""

import subprocess
import sys
from pathlib import Path

import pytest


def test_inventory_defaults_tool_works(tmp_path):
    """Test that the inventory tool generates reports correctly."""
    script_path = Path(__file__).parent.parent.parent / "tools" / "inventory_config_defaults.py"
    config_file = Path(__file__).parent.parent.parent / "apps" / "reference" / "config_models.py"

    out_md = tmp_path / "inventory.md"
    out_json = tmp_path / "inventory.json"

    # Run the inventory script to generate reports
    result = subprocess.run([
        sys.executable, str(script_path),
        "--file", str(config_file),
        "--out-md", str(out_md),
        "--out-json", str(out_json)
    ], capture_output=True, text=True)

    assert result.returncode == 0, f"Script failed: {result.stderr}"
    assert "Generated" in result.stdout

    # Check that files were created
    assert out_md.exists()
    assert out_json.exists()

    # Check that MD has table
    md_content = out_md.read_text()
    assert "| Class | Field | Type | Default | Line |" in md_content
    assert "|-------|-------|------|---------|------|" in md_content

    # Check that JSON is valid
    import json
    json_data = json.loads(out_json.read_text())
    assert isinstance(json_data, list)
    assert len(json_data) > 0  # Should have found defaults