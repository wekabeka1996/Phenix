import json
import pytest
import pathlib
from typer.testing import CliRunner
from vfoundation.cli.vfound.__main__ import app

runner = CliRunner()

def test_debug_cli(tmp_path):
    d = tmp_path / "dict.yaml"
    d.write_text("""
invalid: yaml: :
""")
    
    result = runner.invoke(app, ["dict", "validate", str(d)])
    print(f"\nEXIT CODE: {result.exit_code}")
    print(f"OUTPUT:\n{result.output}")
