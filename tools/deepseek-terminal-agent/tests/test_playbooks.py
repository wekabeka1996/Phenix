"""Tests for PlaybookRegistry."""
from __future__ import annotations

import pytest
import yaml

from deepseek_terminal_agent.sessions.playbooks import PlaybookRegistry


@pytest.fixture
def playbooks_yaml(tmp_path):
    data = {
        "playbooks": [
            {
                "playbook_id": "scout_test",
                "title": "Scout Test",
                "description": "Test playbook",
                "risk_level": "low",
                "enabled": True,
                "agents": ["ScoutAgent"],
                "done_criteria": ["EvidencePack created"],
            },
            {
                "playbook_id": "disabled_pb",
                "title": "Disabled Playbook",
                "description": "",
                "risk_level": "high",
                "enabled": False,
            },
        ]
    }
    path = tmp_path / "playbooks.yaml"
    path.write_text(yaml.dump(data), encoding="utf-8")
    return path


def test_playbook_registry_loads(playbooks_yaml):
    registry = PlaybookRegistry(playbooks_yaml)
    all_pbs = registry.list_playbooks(enabled_only=False)
    assert len(all_pbs) == 2


def test_playbook_registry_enabled_only(playbooks_yaml):
    registry = PlaybookRegistry(playbooks_yaml)
    enabled = registry.list_playbooks(enabled_only=True)
    assert len(enabled) == 1
    assert enabled[0].playbook_id == "scout_test"


def test_playbook_registry_get_by_id(playbooks_yaml):
    registry = PlaybookRegistry(playbooks_yaml)
    pb = registry.get_playbook("disabled_pb")
    assert pb.enabled is False
    assert pb.risk_level == "high"


def test_playbook_registry_not_found(playbooks_yaml):
    registry = PlaybookRegistry(playbooks_yaml)
    with pytest.raises(KeyError):
        registry.get_playbook("nonexistent")


def test_playbook_registry_missing_file(tmp_path):
    registry = PlaybookRegistry(tmp_path / "missing.yaml")
    assert registry.list_playbooks() == []


def test_playbook_registry_invalid_yaml(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("[this is not a mapping]", encoding="utf-8")
    registry = PlaybookRegistry(path)
    with pytest.raises(ValueError):
        registry.list_playbooks()


def test_playbook_to_public_dict(playbooks_yaml):
    registry = PlaybookRegistry(playbooks_yaml)
    pb = registry.get_playbook("scout_test")
    d = pb.to_public_dict()
    assert d["playbook_id"] == "scout_test"
    assert d["schema_version"] == 1


def test_real_playbooks_yaml_loads():
    """Smoke test: the actual playbooks.yaml loads without error."""
    from pathlib import Path
    real_path = Path(__file__).resolve(
    ).parents[1] / "config" / "playbooks.yaml"
    if not real_path.exists():
        pytest.skip("config/playbooks.yaml not found")
    registry = PlaybookRegistry(real_path)
    playbooks = registry.list_playbooks(enabled_only=False)
    assert len(playbooks) >= 10
    ids = [pb.playbook_id for pb in playbooks]
    assert "scout_before_implementation" in ids
    assert "update_memory_checkpoint" in ids
