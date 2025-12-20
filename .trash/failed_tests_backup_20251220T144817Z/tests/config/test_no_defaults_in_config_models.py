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

    # TASK23.FIX.B: allow a very small set of legacy-root-alias defaults.
    # These defaults do NOT create a second SSOT; they only prevent startup blocking
    # on deprecated root-level override aliases.
    allowed = {
        ("AuroraConfig", "decision"),
        ("AuroraConfig", "execution"),
        ("AuroraConfig", "brackets"),
        ("AuroraConfig", "trailing"),
    }
    found = {(d.get("class"), d.get("field")) for d in json_data}
    assert found == allowed

    # Also verify the tool can detect defaults on a synthetic file
    synthetic = tmp_path / "synthetic_defaults.py"
    synthetic.write_text(
        """
from pydantic import BaseModel, Field, ConfigDict


class Demo(BaseModel):
    model_config = ConfigDict(extra='allow')
    a: int = 1
    b: int = Field(default=2)
    c: int = Field(...)
""".lstrip(),
        encoding="utf-8",
    )

    out_md2 = tmp_path / "synthetic_inventory.md"
    out_json2 = tmp_path / "synthetic_inventory.json"
    result2 = subprocess.run(
        [
            sys.executable,
            str(script_path),
            "--file",
            str(synthetic),
            "--out-md",
            str(out_md2),
            "--out-json",
            str(out_json2),
        ],
        capture_output=True,
        text=True,
    )

    assert result2.returncode == 0, f"Script failed: {result2.stderr}"
    json_data2 = json.loads(out_json2.read_text())
    assert isinstance(json_data2, list)
    assert any(d.get("field") == "model_config" for d in json_data2)
    assert any(d.get("field") == "a" for d in json_data2)
    assert any(d.get("field") == "b" for d in json_data2)