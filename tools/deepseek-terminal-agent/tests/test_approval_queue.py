"""Tests for ApprovalQueue."""
from __future__ import annotations

import pytest

from deepseek_terminal_agent.sessions.approval_queue import ApprovalQueue


def test_create_approval_request(tmp_path):
    queue = ApprovalQueue(root_dir=tmp_path)
    req = queue.create_request(
        session_id="sess-1",
        requested_action="edit config file",
        risk_level="high",
        reason="Need to update strategy parameters",
        files_or_scopes=["config/aurora/regime.yaml"],
    )
    assert req.status == "pending"
    assert req.risk_level == "high"
    assert req.session_id == "sess-1"
    assert req.schema_version == 1


def test_approval_request_persisted(tmp_path):
    queue = ApprovalQueue(root_dir=tmp_path)
    req = queue.create_request(
        session_id="sess-1",
        requested_action="update_config",
    )
    loaded = queue.get_request(req.approval_id)
    assert loaded.approval_id == req.approval_id
    assert loaded.status == "pending"


def test_approve_request(tmp_path):
    queue = ApprovalQueue(root_dir=tmp_path)
    req = queue.create_request(session_id="s1", requested_action="edit file")
    approved = queue.resolve(
        req.approval_id, status="approved", note="looks good")
    assert approved.status == "approved"
    assert approved.resolution_note == "looks good"
    assert approved.resolved_at is not None


def test_reject_request(tmp_path):
    queue = ApprovalQueue(root_dir=tmp_path)
    req = queue.create_request(session_id="s1", requested_action="deploy")
    rejected = queue.resolve(
        req.approval_id, status="rejected", note="too risky")
    assert rejected.status == "rejected"


def test_double_resolve_raises(tmp_path):
    queue = ApprovalQueue(root_dir=tmp_path)
    req = queue.create_request(session_id="s1", requested_action="edit")
    queue.resolve(req.approval_id, status="approved")
    with pytest.raises(ValueError, match="Cannot resolve"):
        queue.resolve(req.approval_id, status="rejected")


def test_list_requests(tmp_path):
    queue = ApprovalQueue(root_dir=tmp_path)
    queue.create_request(session_id="s1", requested_action="action1")
    queue.create_request(session_id="s1", requested_action="action2")
    queue.create_request(session_id="s2", requested_action="action3")

    all_reqs = queue.list_requests()
    assert len(all_reqs) == 3

    s1_reqs = queue.list_requests(session_id="s1")
    assert len(s1_reqs) == 2

    pending = queue.list_requests(status="pending")
    assert len(pending) == 3


def test_is_approved(tmp_path):
    queue = ApprovalQueue(root_dir=tmp_path)
    req = queue.create_request(session_id="s1", requested_action="edit")
    assert queue.is_approved(req.approval_id) is False
    queue.resolve(req.approval_id, status="approved")
    assert queue.is_approved(req.approval_id) is True


def test_get_not_found(tmp_path):
    queue = ApprovalQueue(root_dir=tmp_path)
    with pytest.raises(KeyError):
        queue.get_request("nonexistent-id")


def test_request_persists_after_reload(tmp_path):
    queue1 = ApprovalQueue(root_dir=tmp_path)
    req = queue1.create_request(
        session_id="s1", requested_action="test action")

    queue2 = ApprovalQueue(root_dir=tmp_path)
    loaded = queue2.get_request(req.approval_id)
    assert loaded.requested_action == "test action"
