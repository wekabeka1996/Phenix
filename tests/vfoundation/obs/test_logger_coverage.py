
import logging
import json
import io
import sys
import pytest
from vfoundation.obs.logger import JsonFormatter, setup_logging, log_event
from dataclasses import dataclass, field
from typing import Any

@dataclass
class RotationConfig:
    max_bytes: int = 1000
    backup_count: int = 5

@dataclass
class CoreConfig:
    path: str = "logs/test.log"

@dataclass
class LoggingConfig:
    default_level: str = "DEBUG"
    core: CoreConfig = field(default_factory=CoreConfig)
    default_format: str = "json"
    rotation: RotationConfig = field(default_factory=RotationConfig)

@dataclass
class ObsConfig:
    logging: LoggingConfig = field(default_factory=LoggingConfig)

@dataclass
class AppConfig:
    observability: ObsConfig = field(default_factory=ObsConfig)

def test_json_formatter_with_extra():
    formatter = JsonFormatter()
    logger = logging.getLogger("test_json")
    record = logger.makeRecord("test", logging.INFO, "file.py", 10, "msg", (), None, "func", {"extra_field": "val"})
    output = formatter.format(record)
    data = json.loads(output)
    assert data["message"] == "msg"
    assert data["extra_field"] == "val"

def test_json_formatter_with_exception():
    formatter = JsonFormatter()
    try:
        raise ValueError("error")
    except ValueError:
        record = logging.LogRecord("test", logging.ERROR, "file.py", 10, "msg", (), sys.exc_info())
        output = formatter.format(record)
        data = json.loads(output)
        assert "exception" in data
        assert "ValueError: error" in data["exception"]

def test_setup_logging_new_structure(tmp_path):
    log_file = tmp_path / "new.log"
    config = AppConfig()
    config.observability.logging.core.path = str(log_file)
    setup_logging(config)
    
    logging.info("hello new")
    assert log_file.exists()

def test_setup_logging_legacy_structure(tmp_path):
    log_file = tmp_path / "legacy.log"
    class LegacyConfig:
        class System:
            class Logging:
                level = "INFO"
                file = str(log_file)
                format = "json"
                rotation = {"max_bytes": 100, "backup_count": 2}
            logging = Logging()
        system = System()
    
    setup_logging(LegacyConfig())
    logging.info("hello legacy")
    assert log_file.exists()

def test_setup_logging_dict_fallback(tmp_path):
    log_file = tmp_path / "dict.log"
    class DictConfig:
        system = {
            "logging": {
                "level": "INFO",
                "file": str(log_file),
                "rotation": {"max_bytes": 50}
            }
        }
    setup_logging(DictConfig())
    logging.info("hello dict")
    assert log_file.exists()

def test_setup_logging_empty_config():
    class EmptyConfig:
        pass
    setup_logging(EmptyConfig()) # Should use defaults

def test_log_event(capsys):
    log_event(event="TEST", value=123)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["event"] == "TEST"
    assert data["value"] == 123
    assert "ts" in data

def test_setup_logging_attribute_error_obs():
    # Triggering the nested attribute error in obs logging
    class BadObsConfig:
        observability = None # Triggers AttributeError when accessing observability.logging
    setup_logging(BadObsConfig())
