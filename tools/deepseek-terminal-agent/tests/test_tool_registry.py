"""Tests for ToolRegistry."""
from __future__ import annotations

import pytest
import yaml

from deepseek_terminal_agent.sessions.tool_registry import ToolRegistry


@pytest.fixture
def tool_registry_yaml(tmp_path):
    data = {
        "tools": [
            {
                "tool_id": "read_repo",
                "description": "Read files",
                "risk_level": "low",
                "allowed_agents": ["ScoutAgent", "main"],
                "approval_required": False,
                "audit_logging": True,
                "enabled": True,
                "manual_only": False,
            },
            {
                "tool_id": "deploy",
                "description": "Deploy to prod",
                "risk_level": "critical",
                "allowed_agents": [],
                "approval_required": True,
                "audit_logging": True,
                "enabled": True,
                "manual_only": True,
            },
            {
                "tool_id": "update_config",
                "description": "Modify config",
                "risk_level": "high",
                "allowed_agents": ["main"],
                "approval_required": True,
                "audit_logging": True,
                "enabled": True,
                "manual_only": False,
            },
        ]
    }
    path = tmp_path / "tool_registry.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


def test_tool_registry_loads(tool_registry_yaml):
    registry = ToolRegistry(tool_registry_yaml)
    tools = registry.list_tools()
    assert len(tools) == 3


def test_read_repo_is_low_risk(tool_registry_yaml):
    registry = ToolRegistry(tool_registry_yaml)
    tool = registry.get_tool("read_repo")
    assert tool.risk_level == "low"
    assert tool.approval_required is False


def test_update_config_requires_approval(tool_registry_yaml):
    registry = ToolRegistry(tool_registry_yaml)
    tool = registry.get_tool("update_config")
    assert tool.requires_approval() is True


def test_deploy_is_manual_only(tool_registry_yaml):
    registry = ToolRegistry(tool_registry_yaml)
    tool = registry.get_tool("deploy")
    assert tool.manual_only is True
    assert tool.requires_approval() is True


def test_tool_not_found(tool_registry_yaml):
    registry = ToolRegistry(tool_registry_yaml)
    with pytest.raises(KeyError):
        registry.get_tool("nonexistent")


def test_tool_allowed(tool_registry_yaml):
    registry = ToolRegistry(tool_registry_yaml)
    assert registry.is_allowed("read_repo", "ScoutAgent") is True


def test_tool_not_allowed_for_agent(tool_registry_yaml):
    registry = ToolRegistry(tool_registry_yaml)
    # deploy has no allowed_agents — returns False for specific agent
    assert registry.is_allowed("deploy", "ScoutAgent") is False


def test_real_tool_registry_yaml_loads():
    """Smoke test: the actual tool_registry.yaml loads without error."""
    from pathlib import Path
    real_path = Path(__file__).resolve(
    ).parents[1] / "config" / "tool_registry.yaml"
    if not real_path.exists():
        pytest.skip("config/tool_registry.yaml not found")
    registry = ToolRegistry(real_path)
    tools = registry.list_tools()
    assert len(tools) >= 11
    tool_ids = [t.tool_id for t in tools]
    assert "read_repo" in tool_ids
    assert "terminal_exec" in tool_ids
    assert "deploy" in tool_ids
    deploy = registry.get_tool("deploy")
    assert deploy.manual_only is True
