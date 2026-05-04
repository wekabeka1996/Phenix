"""Extending schema validator coverage for import fallbacks and edge branches."""
import pytest
import sys
import importlib
import json
from pathlib import Path
from unittest.mock import MagicMock
from vfoundation.core.schema_validator import SchemaValidator, patch_emit_validation

def test_has_jsonschema_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "jsonschema", None)
    import vfoundation.core.schema_validator as sv
    importlib.reload(sv)
    assert not sv.HAS_JSONSCHEMA
    importlib.reload(sv) # restore

def test_has_yaml_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "yaml", None)
    import vfoundation.core.schema_validator as sv
    importlib.reload(sv)
    assert not sv.HAS_YAML
    importlib.reload(sv) # restore

def test_load_registry_no_yaml(tmp_path, monkeypatch):
    import vfoundation.core.schema_validator as sv
    monkeypatch.setattr(sv, "HAS_YAML", False)
    
    # Instantiate should hit the LOG.warning and return early
    validator = sv.SchemaValidator(repo_root=tmp_path)
    assert validator._schemas == {}

def test_detect_repo_root_fallback(monkeypatch, tmp_path):
    import vfoundation.core.schema_validator as sv
    
    # We want to test the _detect_repo_root fallback when it doesn't find pytest.ini or pyproject.toml
    # Patch Path.exists to return False during detect
    original_exists = Path.exists
    def fake_exists(path):
        if path.name in ("pytest.ini", "pyproject.toml"):
            return False
        return original_exists(path)
        
    monkeypatch.setattr(Path, "exists", fake_exists)
    root = sv.SchemaValidator._detect_repo_root()
    # Should fallback to 3 levels up from the file
    assert root == Path(sv.__file__).resolve().parent.parent.parent

def test_validate_no_jsonschema(monkeypatch, tmp_path):
    import vfoundation.core.schema_validator as sv
    val = sv.SchemaValidator(repo_root=tmp_path)
    val._schemas[("A", "B")] = {"type": "object"}
    
    monkeypatch.setattr(sv, "HAS_JSONSCHEMA", False)
    res = val.validate("A", "B", {})
    assert res == []

def test_validate_schema_error(monkeypatch, tmp_path):
    import vfoundation.core.schema_validator as sv
    import jsonschema
    val = sv.SchemaValidator(repo_root=tmp_path)
    val._schemas[("C", "D")] = {"type": "invalid"}
    
    def fake_validate(*args, **kwargs):
        raise jsonschema.SchemaError("bad schema")
        
    monkeypatch.setattr(jsonschema, "validate", fake_validate)
    res = val.validate("C", "D", {})
    assert "invalid schema: bad schema" in res[0]

def test_load_registry_missing_file(tmp_path):
    import vfoundation.core.schema_validator as sv
    # tmp_path has no registry file
    val = sv.SchemaValidator(repo_root=tmp_path, registry_path="missing.yaml")
    assert val._schemas == {}

def test_load_registry_missing_schema_file(tmp_path, monkeypatch):
    import vfoundation.core.schema_validator as sv
    import yaml
    
    registry_file = tmp_path / "registry.yaml"
    registry_file.write_text(yaml.dump({"registry": [{"op": "A", "verb": "B", "schema": "missing.json"}]}))
    
    val = sv.SchemaValidator(repo_root=tmp_path, registry_path="registry.yaml")
    assert val._schemas == {}

def test_load_registry_schema_decode_error(tmp_path, monkeypatch):
    import vfoundation.core.schema_validator as sv
    import yaml
    
    schema_file = tmp_path / "bad.json"
    schema_file.write_text("not json")
    
    registry_file = tmp_path / "registry.yaml"
    registry_file.write_text(yaml.dump({"registry": [{"op": "A", "verb": "B", "schema": "bad.json"}]}))
    
    val = sv.SchemaValidator(repo_root=tmp_path, registry_path="registry.yaml")
    assert val._schemas == {}

def test_patch_emit_validation_auto_create(tmp_path):
    import vfoundation.core.schema_validator as sv
    bus = MagicMock()
    # Providing None automatically instantiates a new validator 
    # To prevent it from hitting the real registry, pass a bad path or mock _detect_repo_root
    
    # We test the auto instantiation branch
    sv.patch_emit_validation(bus, None)
    
    # it replaces bus.emit
    assert bus.emit != MagicMock

def test_patch_emit_no_colon_in_event_name():
    import vfoundation.core.schema_validator as sv
    bus = MagicMock()
    bus.emit = MagicMock()
    orig = bus.emit
    
    val_mock = MagicMock()
    # strict False
    sv.patch_emit_validation(bus, val_mock, strict=False)
    
    bus.emit("JUST_EVENT_NO_COLON", {}, "why", None)
    
    # Validate wasn't called because there was no colon
    val_mock.validate.assert_not_called()
    # original emit was called
    orig.assert_called()

def test_patch_emit_returns_early_on_strict_failure():
    import vfoundation.core.schema_validator as sv
    bus = MagicMock()
    bus.emit = MagicMock()
    # original emit
    orig = bus.emit
    
    val_mock = MagicMock()
    val_mock.validate.return_value = ["error"]
    
    # strict True
    sv.patch_emit_validation(bus, val_mock, strict=True)
    
    # Call patched emit
    bus.emit("EVT:TEST", {}, "why", None)
    
    val_mock.validate.assert_called_with("EVT", "TEST", {})
    # orig shouldn't be called because strict returned early
    orig.assert_not_called()
