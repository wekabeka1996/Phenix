"""Tests for MemoryPatchStore."""
from __future__ import annotations

import pytest

from deepseek_terminal_agent.sessions.memory_patch import MemoryPatchStore


def test_create_patch(tmp_path):
    store = MemoryPatchStore(root_dir=tmp_path)
    patch = store.create_patch(
        proposed_change="Update deep checkpoint phase to v7",
        affected_checkpoint_section="current_phase",
        reason="Phase completed",
        risk="medium",
        diff="--- old\n+++ new",
        source_report_ids=["r1", "r2"],
    )
    assert patch.patch_id
    assert patch.status == "pending"
    assert patch.risk == "medium"
    assert patch.source_report_ids == ["r1", "r2"]
    assert patch.schema_version == 1


def test_patch_persists(tmp_path):
    store = MemoryPatchStore(root_dir=tmp_path)
    patch = store.create_patch(proposed_change="Test change")
    loaded = store.get_patch(patch.patch_id)
    assert loaded.proposed_change == "Test change"


def test_approve_patch(tmp_path):
    store = MemoryPatchStore(root_dir=tmp_path)
    patch = store.create_patch(proposed_change="Test")
    approved = store.approve(patch.patch_id, approved_by="operator")
    assert approved.status == "approved"
    assert approved.approved_by == "operator"


def test_reject_patch(tmp_path):
    store = MemoryPatchStore(root_dir=tmp_path)
    patch = store.create_patch(proposed_change="Test")
    rejected = store.reject(patch.patch_id, reason="Not enough evidence")
    assert rejected.status == "rejected"
    assert rejected.rejected_reason == "Not enough evidence"


def test_cannot_approve_rejected(tmp_path):
    store = MemoryPatchStore(root_dir=tmp_path)
    patch = store.create_patch(proposed_change="Test")
    store.reject(patch.patch_id)
    with pytest.raises(ValueError, match="Cannot approve"):
        store.approve(patch.patch_id)


def test_mark_applied(tmp_path):
    store = MemoryPatchStore(root_dir=tmp_path)
    patch = store.create_patch(proposed_change="Test")
    store.approve(patch.patch_id)
    applied = store.mark_applied(patch.patch_id)
    assert applied.status == "applied"
    assert applied.applied_at is not None


def test_cannot_apply_without_approval(tmp_path):
    store = MemoryPatchStore(root_dir=tmp_path)
    patch = store.create_patch(proposed_change="Test")
    with pytest.raises(ValueError, match="not approved"):
        store.mark_applied(patch.patch_id)


def test_list_patches(tmp_path):
    store = MemoryPatchStore(root_dir=tmp_path)
    p1 = store.create_patch(proposed_change="P1")
    p2 = store.create_patch(proposed_change="P2")
    store.approve(p2.patch_id)

    all_patches = store.list_patches()
    assert len(all_patches) == 2

    pending = store.list_patches(status="pending")
    assert len(pending) == 1
    assert pending[0].patch_id == p1.patch_id

    approved = store.list_patches(status="approved")
    assert len(approved) == 1
    assert approved[0].patch_id == p2.patch_id


def test_patch_not_found(tmp_path):
    store = MemoryPatchStore(root_dir=tmp_path)
    with pytest.raises(KeyError):
        store.get_patch("nonexistent")


def test_memory_update_requires_approval(tmp_path):
    """Memory patch flow: cannot apply without going through approval."""
    store = MemoryPatchStore(root_dir=tmp_path)
    patch = store.create_patch(
        proposed_change="Critical memory update",
        risk="high",
    )
    # Attempt to apply directly without approval
    with pytest.raises(ValueError):
        store.mark_applied(patch.patch_id)
