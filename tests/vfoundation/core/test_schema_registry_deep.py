import pytest
import os
import yaml
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
from vfoundation.core.schema_registry import VerbSchemaRegistry

def test_schema_registry_load_registry_missing_file(tmp_path):
    """Test load_registry with missing YAML."""
    registry = VerbSchemaRegistry(project_root=str(tmp_path))
    # Should log error and return
    registry.load_registry("non_existent.yaml")
    assert registry.total_validators == 0

def test_schema_registry_load_registry_success(tmp_path):
    """Test successful registry loading."""
    # 1. Create a schema file
    s_dir = tmp_path / "schemas"
    s_dir.mkdir()
    schema_file = s_dir / "test_v1.json"
    schema_content = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {"a": {"type": "integer"}},
        "required": ["a"]
    }
    schema_file.write_text(json.dumps(schema_content))
    
    # 2. Create registry YAML
    reg_yaml = tmp_path / "registry.yaml"
    reg_content = {
        "registry": [
            {
                "op": "EVT",
                "verb": "TEST",
                "schema": "schemas/test_v1.json"
            },
            {
                "op": "CMD",
                "verb": "NOSCHEMA",
                "schema": None
            }
        ]
    }
    reg_yaml.write_text(yaml.dump(reg_content))
    
    registry = VerbSchemaRegistry(project_root=str(tmp_path))
    registry.load_registry("registry.yaml")
    
    assert registry.total_validators == 1
    assert registry.get_validator("EVT", "TEST") is not None
    assert registry.is_schema_missing("CMD", "NOSCHEMA") is True

def test_schema_registry_invalid_json_compilation(tmp_path):
    """Test registry behavior when schema file is invalid JSON."""
    s_dir = tmp_path / "schemas"
    s_dir.mkdir()
    f = s_dir / "invalid.json"
    f.write_text("{invalid json}")
    
    reg_yaml = tmp_path / "registry.yaml"
    reg_yaml.write_text(yaml.dump({
        "registry": [{"op": "X", "verb": "Y", "schema": "schemas/invalid.json"}]
    }))
    
    registry = VerbSchemaRegistry(project_root=str(tmp_path))
    registry.load_registry("registry.yaml")
    assert registry.total_validators == 0
    assert registry.is_schema_missing("X", "Y") is True
