"""Tests for Project Capsule YAML loading."""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from deepseek_terminal_agent.config import ProjectCapsuleConfig, Settings
from deepseek_terminal_agent.sessions.project_capsule import ProjectCapsuleStore


def _write_capsule(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def test_project_capsule_store_loads_yaml(tmp_path):
    capsule_path = tmp_path / "config" / "project_capsule.yaml"
    _write_capsule(
        capsule_path,
        {
            "project_capsule": {
                "project": {
                    "name": "Aurora/Phenix",
                    "domain": "algorithmic_trading_system",
                    "mode": "live_runtime_sensitive",
                    "current_phase": "project_agent_os_transition",
                },
                "ssot_rules": {
                    "config": ["YAML + Pydantic only"],
                    "development": ["Contract-first"],
                    "runtime": ["Logs are evidence"],
                },
                "memory": {
                    "deep_checkpoint": True,
                    "accepted_reports_only": True,
                    "default_agent_search_mode": "current_ssot_and_accepted_facts",
                },
                "permissions": {
                    "production_changes": "approval_required",
                    "config_changes": "approval_required",
                    "registry_changes": "approval_required",
                    "memory_updates": "patch_approval_required",
                },
                "current_phase": {
                    "name": "Transition",
                    "status": "in_progress",
                    "completed": ["baseline"],
                    "in_progress": ["capsule"],
                    "blockers": ["docker proof pending"],
                    "risks": ["raw logs without evidence bundle"],
                    "next_best_step": ["render capsule in dashboard"],
                },
            }
        },
    )

    settings = Settings(
        project_capsule=ProjectCapsuleConfig(
            path="config/project_capsule.yaml")
    )
    store = ProjectCapsuleStore(settings, root_dir=tmp_path)

    capsule = store.load()

    assert capsule.project.name == "Aurora/Phenix"
    assert capsule.current_phase.status == "in_progress"
    assert capsule.to_public_dict()["counts"]["risks"] == 1


def test_project_capsule_store_requires_root_mapping(tmp_path):
    capsule_path = tmp_path / "config" / "project_capsule.yaml"
    _write_capsule(capsule_path, {"unexpected": {"name": "Aurora/Phenix"}})

    settings = Settings(
        project_capsule=ProjectCapsuleConfig(
            path="config/project_capsule.yaml")
    )
    store = ProjectCapsuleStore(settings, root_dir=tmp_path)

    with pytest.raises(ValueError, match="project_capsule root mapping is required"):
        store.load()
