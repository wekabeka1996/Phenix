import pytest
from unittest.mock import MagicMock
from jsonschema.exceptions import ValidationError

from vfoundation.core.fsm_core import FSMCore, InvalidMessagePayloadError
from vfoundation.core.schema_registry import VerbSchemaRegistry, _global_registry
import vfoundation.core.schema_registry as sr

@pytest.fixture
def mock_registry(monkeypatch):
    registry = MagicMock(spec=VerbSchemaRegistry)
    
    # Store old
    old_registry = sr._global_registry
    sr._global_registry = registry
    yield registry
    # Restore old
    sr._global_registry = old_registry


def test_emit_validation_success(mock_registry):
    fsm = FSMCore()
    
    # Setup mock validator
    mock_validator = MagicMock()
    mock_registry.get_validator.return_value = mock_validator
    
    # Emit should validate and NOT raise
    fsm.emit("EVT:TEST_EVENT", {"key": "value"}, "why")
    
    mock_registry.get_validator.assert_called_with("EVT", "TEST_EVENT")
    mock_validator.validate.assert_called_with({"key": "value"})


def test_emit_validation_failure(mock_registry):
    fsm = FSMCore()
    
    # Setup mock validator to raise ValidationError
    mock_validator = MagicMock()
    mock_validator.validate.side_effect = ValidationError("Bad data")
    mock_registry.get_validator.return_value = mock_validator
    
    with pytest.raises(InvalidMessagePayloadError) as exc:
        fsm.emit("EVT:TEST_EVENT", {"bad": "data"}, "why")
        
    assert "Payload validation failed for EVT:TEST_EVENT: Bad data" in str(exc.value)


def test_emit_missing_schema_logs_warning(mock_registry, caplog):
    fsm = FSMCore()
    
    # Setup mock registry to report missing schema
    mock_registry.get_validator.return_value = None
    mock_registry.is_schema_missing.return_value = True
    
    fsm.emit("EVT:DEPRECATED_EVENT", {"some": "data"}, "why")
    
    # Should not raise, but log warning
    assert "DEPRECATION: Emitting EVT:DEPRECATED_EVENT without JSON Schema validation." in caplog.text


def test_emit_no_registry_bypasses_validation(mock_registry, monkeypatch):
    # Set global registry to None
    sr._global_registry = None
    
    fsm = FSMCore()
    # Should succeed without calling validators
    fsm.emit("EVT:NO_REGISTRY", {"key": "val"}, "why")
