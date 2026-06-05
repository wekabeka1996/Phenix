import json
from pathlib import Path
import pytest
from jsonschema.exceptions import ValidationError

from vfoundation.core.schema_registry import VerbSchemaRegistry

@pytest.fixture
def temp_project(tmp_path: Path):
    """
    Creates a temporary project structure with a verb registry YAML
    and a couple of mock JSON schemas for testing.
    """
    # Create schema files
    schema_dir = tmp_path / "schemas"
    schema_dir.mkdir()

    cmd_open_schema = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "qty": {"type": "number"}
        },
        "required": ["symbol", "qty"]
    }
    
    with open(schema_dir / "cmd_open.json", "w", encoding="utf-8") as f:
        json.dump(cmd_open_schema, f)

    # Missing/invalid schemas won't be created on disk so we can test error handling.

    # Create verb_registry.yaml
    yaml_content = """
    version: 1
    registry:
    - op: CMD
      verb: OPEN
      schema: schemas/cmd_open.json
    - op: DEC
      verb: CLOSE
      schema: null
    - op: EVT
      verb: MISSING_FILE
      schema: schemas/does_not_exist.json
    - op: ERR
      verb: BAD_JSON
      schema: schemas/bad.json
    """
    
    yaml_file = tmp_path / "test_registry.yaml"
    with open(yaml_file, "w", encoding="utf-8") as f:
        f.write(yaml_content)

    # Create bad schema (invalid JSON content)
    with open(schema_dir / "bad.json", "w", encoding="utf-8") as f:
        f.write("{ bad json }")

    return tmp_path, "test_registry.yaml"


def test_schema_registry_loads_valid_schema(temp_project):
    root, yaml_path = temp_project
    registry = VerbSchemaRegistry(project_root=str(root))
    registry.load_registry(yaml_path)

    # Verify validator was loaded
    validator = registry.get_validator("CMD", "OPEN")
    assert validator is not None

    # Test validator works
    validator.validate({"symbol": "BTCUSD", "qty": 1.5})  # Should pass
    
    with pytest.raises(ValidationError):
        validator.validate({"symbol": "BTCUSD"})  # Missing qty


def test_schema_registry_handles_null_schema(temp_project):
    root, yaml_path = temp_project
    registry = VerbSchemaRegistry(project_root=str(root))
    registry.load_registry(yaml_path)

    # DEC:CLOSE has schema: null
    validator = registry.get_validator("DEC", "CLOSE")
    assert validator is None
    assert registry.is_schema_missing("DEC", "CLOSE") is True


def test_schema_registry_handles_missing_file(temp_project, caplog):
    root, yaml_path = temp_project
    registry = VerbSchemaRegistry(project_root=str(root))
    registry.load_registry(yaml_path)

    # EVT:MISSING_FILE points to non-existent file
    validator = registry.get_validator("EVT", "MISSING_FILE")
    assert validator is None
    assert registry.is_schema_missing("EVT", "MISSING_FILE") is True
    assert "Schema file not found" in caplog.text


def test_schema_registry_handles_invalid_json(temp_project, caplog):
    root, yaml_path = temp_project
    registry = VerbSchemaRegistry(project_root=str(root))
    registry.load_registry(yaml_path)

    # ERR:BAD_JSON points to malformed JSON file
    validator = registry.get_validator("ERR", "BAD_JSON")
    assert validator is None
    assert registry.is_schema_missing("ERR", "BAD_JSON") is True
    assert "Failed to compile schema" in caplog.text


def test_schema_registry_missing_yaml_file(tmp_path, caplog):
    registry = VerbSchemaRegistry(project_root=str(tmp_path))
    registry.load_registry("does_not_exist.yaml")
    
    # Should log error and safely continue empty
    assert "Verb registry file not found" in caplog.text
    assert registry.get_validator("CMD", "OPEN") is None
    assert registry.total_validators == 0
