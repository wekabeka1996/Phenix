"""Tests for CLI test-gen command — Phase 15.3."""
import ast
import pathlib
import tempfile

import pytest
from typer.testing import CliRunner

from vfoundation.cli.vfound.__main__ import app

runner = CliRunner()


class TestTestGen:
    """Phase 15.3: vfound test-gen command tests."""

    def test_test_gen_generates_valid_python(self, tmp_path: pathlib.Path):
        """Generated output must be valid Python (parseable by ast)."""
        out = tmp_path / "test_out.py"
        result = runner.invoke(app, ["test-gen", "vfoundation.core.schema_version", "-o", str(out)])
        assert result.exit_code == 0, result.output
        content = out.read_text(encoding="utf-8")
        # Must parse without SyntaxError
        ast.parse(content)

    def test_test_gen_has_test_per_public_function(self, tmp_path: pathlib.Path):
        """Generated template should have a test for each public function."""
        out = tmp_path / "test_out.py"
        # data_ref has coerce_data_ref as public function
        result = runner.invoke(app, ["test-gen", "vfoundation.core.data_ref", "-o", str(out)])
        assert result.exit_code == 0, result.output
        content = out.read_text(encoding="utf-8")
        assert "def test_coerce_data_ref" in content

    def test_test_gen_has_test_per_class_method(self, tmp_path: pathlib.Path):
        """Generated template should have a test class per public class with method tests."""
        out = tmp_path / "test_out.py"
        # deprecation.py has DeprecationRegistry.register, .get, .is_deprecated etc
        result = runner.invoke(app, ["test-gen", "vfoundation.core.deprecation", "-o", str(out)])
        assert result.exit_code == 0, result.output
        content = out.read_text(encoding="utf-8")
        assert "class TestDeprecationRegistry" in content
        assert "def test_register" in content

    def test_test_gen_dry_run_prints_stdout(self):
        """--dry-run should print to stdout, not write a file."""
        result = runner.invoke(app, ["test-gen", "vfoundation.core.schema_version", "--dry-run"])
        assert result.exit_code == 0
        assert "Auto-generated test template" in result.output
        assert "class TestSchemaRegistry" in result.output

    def test_test_gen_unknown_module_exits_1(self):
        """Unknown module should exit with code 1."""
        result = runner.invoke(app, ["test-gen", "nonexistent.module.xyz"])
        assert result.exit_code == 1
        assert "Module not found" in result.output
