from __future__ import annotations

import json
from pathlib import Path
import pytest
from pydantic import ValidationError
import jsonschema

from apps.reference.domains.agent_bridge.session_context_contract import SessionContextV1
from apps.reference.domains.agent_bridge.session_context_read_model import SessionContextReadModel

_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "apps" / "reference" / "domains" / "agent_bridge" / "schemas" / "session_context_v1.json"


def test_missing_store_fails_closed(tmp_path):
    """Test that a missing memory store or missing session fails closed with FileNotFoundError."""
    # 1. Missing memory root directory
    reader = SessionContextReadModel(memory_root=tmp_path / "nonexistent_store")
    with pytest.raises(FileNotFoundError) as excinfo:
        reader.load_context("session_123")
    assert "Memory root directory does not exist" in str(excinfo.value)

    # 2. Missing sessions directory
    tmp_path.mkdir(exist_ok=True)
    reader_empty = SessionContextReadModel(memory_root=tmp_path)
    with pytest.raises(FileNotFoundError) as excinfo:
        reader_empty.load_context("session_123")
    assert "Sessions directory does not exist" in str(excinfo.value)

    # 3. Missing session folder / files
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    with pytest.raises(FileNotFoundError) as excinfo:
        reader_empty.load_context("session_123")
    assert "Session state file not found" in str(excinfo.value)


def test_no_order_sizing_leverage_payload():
    """Test that SessionContextV1 prohibits order, sizing, and leverage payload fields."""
    valid_data = {
        "session_id": "session_123",
        "source": "cockpit-session://session_123",
        "created_at": "2026-07-08T17:48:15.000Z",
        "operator_notes_refs": [],
        "memory_atom_refs": [],
        "attachment_refs": [],
        "pattern_refs": [],
        "token_budget": 100000,
        "compression_lineage_refs": [],
        "approval_status": "none",
        "provenance": {"title": "Strategy Session", "status": "active"}
    }

    # Prohibits "order" field
    with pytest.raises(ValidationError):
        SessionContextV1(**{**valid_data, "order": {"price": 100}})

    # Prohibits "sizing" field
    with pytest.raises(ValidationError):
        SessionContextV1(**{**valid_data, "sizing": 0.5})

    # Prohibits "leverage" field
    with pytest.raises(ValidationError):
        SessionContextV1(**{**valid_data, "leverage": 20})


def test_source_required():
    """Test that the source reference field is strictly required and validated by the contract."""
    invalid_data = {
        "session_id": "session_123",
        # "source" is missing
        "created_at": "2026-07-08T17:48:15.000Z",
        "operator_notes_refs": [],
        "memory_atom_refs": [],
        "attachment_refs": [],
        "pattern_refs": [],
        "token_budget": 100000,
        "compression_lineage_refs": [],
        "approval_status": "none",
        "provenance": {"title": "Strategy Session", "status": "active"}
    }
    with pytest.raises(ValidationError):
        SessionContextV1(**invalid_data)

    # Test invalid source prefix
    invalid_source_data = {
        **invalid_data,
        "source": "invalid-ref://session_123"
    }
    with pytest.raises(ValidationError) as excinfo:
        SessionContextV1(**invalid_source_data)
    assert "source reference must start with 'cockpit-session://'" in str(excinfo.value)


def test_provenance_validation():
    """Test that provenance requires title and status keys."""
    data = {
        "session_id": "session_123",
        "source": "cockpit-session://session_123",
        "created_at": "2026-07-08T17:48:15.000Z",
        "token_budget": 100000,
        "approval_status": "none",
        "provenance": {}  # empty is invalid
    }
    with pytest.raises(ValidationError) as excinfo:
        SessionContextV1(**data)
    assert "provenance must contain keys" in str(excinfo.value)


def test_schema_validates_examples():
    """Test that the JSON schema correctly validates valid examples and rejects invalid structures."""
    assert _SCHEMA_PATH.exists(), f"Schema file not found at: {_SCHEMA_PATH}"
    
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)

    valid_example = {
        "session_id": "session_123",
        "source": "cockpit-session://session_123",
        "created_at": "2026-07-08T17:48:15.000Z",
        "operator_notes_refs": ["agent-memory://operator-note/op_123"],
        "memory_atom_refs": ["agent-memory://atom/atom_abc"],
        "attachment_refs": ["agent-memory://artifact/artifact_xyz.json"],
        "pattern_refs": ["agent-memory://playbooks"],
        "token_budget": 150000,
        "compression_lineage_refs": ["agent-memory://spine/spine_789"],
        "approval_status": "approved",
        "provenance": {
            "title": "Strategy Session",
            "status": "active"
        }
    }

    # Should validate successfully
    jsonschema.validate(instance=valid_example, schema=schema)

    # Invalid: extra property "sizing"
    invalid_extra = {**valid_example, "sizing": 10.0}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_extra, schema=schema)

    # Invalid: invalid source pattern
    invalid_source = {**valid_example, "source": "http://example.com"}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_source, schema=schema)

    # Invalid: missing title/status in provenance
    invalid_provenance = {**valid_example, "provenance": {}}
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance=invalid_provenance, schema=schema)


def test_routes_session_context(tmp_path):
    """Test that the GET /agent-session-context/v0/{session_id} route functions correctly."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from apps.reference.domains.agent_bridge.routes import register_agent_feed_routes

    app = FastAPI()
    register_agent_feed_routes(app, project_root=tmp_path)
    client = TestClient(app)

    # 1. Nonexistent memory store returns 503 (fails closed)
    response = client.get("/agent-session-context/v0/session_999")
    assert response.status_code == 503
    assert "memory store is unavailable" in response.json()["detail"].lower()

    # 2. Store exists but missing session folder returns 404
    memory_root = tmp_path / "tools" / "deepseek-terminal-agent" / ".agent_memory"
    memory_root.mkdir(parents=True)
    sessions_dir = memory_root / "sessions"
    sessions_dir.mkdir()
    response = client.get("/agent-session-context/v0/session_999")
    assert response.status_code == 404

    # 3. Populate mock session inside correct Cockpit memory directory
    session_dir = sessions_dir / "session_123"
    session_dir.mkdir()
    
    session_state = {
        "schema_version": 1,
        "session_id": "session_123",
        "title": "Strategy Session",
        "created_at": "2026-07-08T17:48:15.000Z",
        "updated_at": "2026-07-08T17:48:15.000Z",
        "active_profile": {
            "context_budget_chars": 250000,
            "model_id": "deepseek-v4-pro"
        },
        "pinned_memory_atom_ids": ["atom_abc"],
        "current_spine_id": "spine_xyz",
        "status": "active",
        "metadata": {}
    }
    with open(session_dir / "session.dsstate.json", "w", encoding="utf-8") as f:
        json.dump(session_state, f)

    # 4. Successful fetch
    response = client.get("/agent-session-context/v0/session_123")
    assert response.status_code == 200
    data = response.json()
    assert data["session_id"] == "session_123"
    assert data["source"] == "cockpit-session://session_123"
    assert data["token_budget"] == 250000
    assert "agent-memory://spine/spine_xyz" in data["compression_lineage_refs"]

    # 5. Verify endpoint is GET-only (POST should raise 405 Method Not Allowed)
    post_response = client.post("/agent-session-context/v0/session_123", json={})
    assert post_response.status_code == 405
