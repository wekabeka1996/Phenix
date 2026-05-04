"""Tests for config loading, env overrides, and fail-fast validation."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

# ── Helpers ───────────────────────────────────────────────────────────────────


def write_yaml(path: Path, data: dict) -> str:
    p = path / "agent.yaml"
    p.write_text(yaml.dump(data))
    return str(p)


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_loads_yaml_defaults(tmp_path, monkeypatch):
    """YAML values are loaded and env key override works."""
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")

    cfg_file = write_yaml(
        tmp_path,
        {"deepseek": {"model": "deepseek-v4-pro",
                      "temperature": 0.3, "request_timeout_sec": 240}},
    )

    from deepseek_terminal_agent.config import load_settings

    settings = load_settings(config_path=cfg_file, env_file=None)
    assert settings.deepseek.api_key == "sk-test-key"
    assert settings.deepseek.model == "deepseek-v4-pro"
    assert settings.deepseek.temperature == pytest.approx(0.3)
    assert settings.deepseek.request_timeout_sec == 240


def test_env_overrides_yaml_model(tmp_path, monkeypatch):
    """DEEPSEEK_MODEL env var overrides the YAML model value."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    cfg_file = write_yaml(tmp_path, {"deepseek": {"model": "deepseek-v4-pro"}})

    from deepseek_terminal_agent.config import load_settings

    settings = load_settings(config_path=cfg_file, env_file=None)
    assert settings.deepseek.model == "deepseek-v4-flash"


def test_env_overrides_deepseek_request_timeout(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    monkeypatch.setenv("DEEPSEEK_REQUEST_TIMEOUT_SEC", "45")

    cfg_file = write_yaml(tmp_path, {"deepseek": {"request_timeout_sec": 300}})

    from deepseek_terminal_agent.config import load_settings

    settings = load_settings(config_path=cfg_file, env_file=None)
    assert settings.deepseek.request_timeout_sec == 45


def test_env_overrides_workspace(tmp_path, monkeypatch):
    """AGENT_WORKSPACE env var overrides the YAML workspace_root."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    monkeypatch.setenv("AGENT_WORKSPACE", "/tmp/custom-ws")

    cfg_file = write_yaml(tmp_path, {})

    from deepseek_terminal_agent.config import load_settings

    settings = load_settings(config_path=cfg_file, env_file=None)
    assert settings.terminal.workspace_root == "/tmp/custom-ws"


def test_missing_api_key_fails(tmp_path, monkeypatch):
    """Missing DEEPSEEK_API_KEY triggers SystemExit with a clear message."""
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    cfg_file = write_yaml(tmp_path, {"deepseek": {"model": "deepseek-v4-pro"}})

    from deepseek_terminal_agent.config import load_settings

    with pytest.raises(SystemExit):
        load_settings(config_path=cfg_file, env_file=None)


def test_invalid_timeout_fails(tmp_path, monkeypatch):
    """Negative timeout triggers a validation error / SystemExit."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    monkeypatch.setenv("AGENT_COMMAND_TIMEOUT_SEC", "-5")

    cfg_file = write_yaml(tmp_path, {})

    from deepseek_terminal_agent.config import load_settings

    with pytest.raises((SystemExit, Exception)):
        load_settings(config_path=cfg_file, env_file=None)


def test_invalid_max_iterations_fails(tmp_path, monkeypatch):
    """max_iterations=0 triggers a validation error / SystemExit."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    monkeypatch.setenv("AGENT_MAX_ITERATIONS", "0")

    cfg_file = write_yaml(tmp_path, {})

    from deepseek_terminal_agent.config import load_settings

    with pytest.raises((SystemExit, Exception)):
        load_settings(config_path=cfg_file, env_file=None)


def test_missing_yaml_uses_defaults(tmp_path, monkeypatch):
    """When the YAML file doesn't exist, defaults are used."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")

    from deepseek_terminal_agent.config import load_settings

    settings = load_settings(
        config_path=str(tmp_path / "nonexistent.yaml"),
        env_file=None,
    )
    assert settings.deepseek.model == "deepseek-v4-pro"
    assert settings.terminal.default_timeout_sec == 120
    assert settings.agent.max_iterations == 20


def test_reasoning_flag_parsed(tmp_path, monkeypatch):
    """DEEPSEEK_REASONING_ENABLED=false correctly disables reasoning."""
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")
    monkeypatch.setenv("DEEPSEEK_REASONING_ENABLED", "false")

    from deepseek_terminal_agent.config import load_settings

    settings = load_settings(config_path=str(
        tmp_path / "none.yaml"), env_file=None)
    assert settings.deepseek.reasoning_enabled is False


def test_loads_new_workbench_sections(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")

    cfg_file = write_yaml(
        tmp_path,
        {
            "models": {"registry_cache_path": ".agent_memory/custom.dsmodels.json"},
            "sessions": {"root_dir": ".agent_memory/custom_sessions"},
            "memory": {"path": ".agent_memory/custom_memory.dsmem.jsonl"},
            "compression": {"model_id": "deepseek-v4-flash"},
            "subagents": {"default_tool_policy": "read_only"},
            "dashboard": {"chat_enabled": True},
            "project_capsule": {"path": "config/custom_project_capsule.yaml"},
        },
    )

    from deepseek_terminal_agent.config import load_settings

    settings = load_settings(config_path=cfg_file, env_file=None)
    assert settings.models.registry_cache_path == ".agent_memory/custom.dsmodels.json"
    assert settings.sessions.root_dir == ".agent_memory/custom_sessions"
    assert settings.memory.path == ".agent_memory/custom_memory.dsmem.jsonl"
    assert settings.compression.model_id == "deepseek-v4-flash"
    assert settings.subagents.default_tool_policy == "read_only"
    assert settings.dashboard.chat_enabled is True
    assert settings.project_capsule.path == "config/custom_project_capsule.yaml"


def test_unsafe_local_storage_path_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test-key")

    cfg_file = write_yaml(
        tmp_path,
        {"models": {"registry_cache_path": "../escape.dsmodels.json"}},
    )

    from deepseek_terminal_agent.config import load_settings

    with pytest.raises(SystemExit):
        load_settings(config_path=cfg_file, env_file=None)


def test_gitignore_contains_agent_memory():
    project_root = Path(__file__).resolve().parents[1]
    gitignore = (project_root / ".gitignore").read_text(encoding="utf-8")
    assert ".agent_memory/" in gitignore


def test_docker_compose_mounts_repo_root_and_config_uses_repo_workspace():
    """Compose must expose the Phenix root while the agent keeps repo-root access."""
    project_root = Path(__file__).resolve().parents[1]

    compose = yaml.safe_load(
        (project_root / "docker-compose.yml").read_text(encoding="utf-8")
    )
    agent_service = compose["services"]["deepseek-agent"]
    dashboard_service = compose["services"]["dashboard"]

    assert agent_service["env_file"] == ["./.env"]
    assert dashboard_service["env_file"] == ["./.env"]
    assert agent_service["volumes"] == ["../../:/workspace/project"]
    assert dashboard_service["volumes"] == ["../../:/workspace/project"]
    assert agent_service["working_dir"] == "/workspace/project/tools/deepseek-terminal-agent"
    assert dashboard_service["working_dir"] == "/workspace/project/tools/deepseek-terminal-agent"

    agent_config = yaml.safe_load(
        (project_root / "config" / "agent.yaml").read_text(encoding="utf-8")
    )
    assert agent_config["terminal"]["workspace_root"] == "/workspace/project"
