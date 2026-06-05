"""Tests for LossReport generation and context_loss module."""
from __future__ import annotations

import pytest

from deepseek_terminal_agent.sessions.context_loss import LossReport, generate_loss_report


def test_loss_report_basic():
    report = generate_loss_report(
        session_id="sess-1",
        source_turn_ids=["t1", "t2", "t3"],
        spine_summary="Summary of context",
        omitted_items=["Some user turn content", "Some answer content"],
        preserved_facts=["fact A", "fact B"],
        source_chars=1000,
        compressed_chars=200,
    )
    assert isinstance(report, LossReport)
    assert report.session_id == "sess-1"
    assert len(report.source_turn_ids) == 3
    assert report.compression_ratio == pytest.approx(0.2, abs=0.01)
    assert "fact A" in report.preserved
    assert report.schema_version == 1


def test_loss_report_risky_drops():
    report = generate_loss_report(
        session_id="sess-1",
        source_turn_ids=["t1"],
        spine_summary="Summary",
        omitted_items=["This was a decision about X",
                       "Normal content", "Error occurred"],
        preserved_facts=[],
    )
    assert len(report.risky_drops) >= 1
    assert report.requires_review is True


def test_loss_report_no_risky_drops():
    report = generate_loss_report(
        session_id="sess-1",
        source_turn_ids=["t1"],
        spine_summary="Summary",
        omitted_items=["Hello there", "Simple user message"],
        preserved_facts=[],
    )
    assert report.requires_review is False
    assert report.risky_drops == []


def test_loss_report_compression_ratio_zero_source():
    report = generate_loss_report(
        session_id="sess-1",
        source_turn_ids=[],
        spine_summary="",
        omitted_items=[],
        preserved_facts=[],
        source_chars=0,
        compressed_chars=100,
    )
    assert report.compression_ratio == 0.0


def test_loss_report_pydantic_model():
    data = LossReport(
        loss_report_id="lr-1",
        session_id="sess-1",
        source_turn_ids=["t1"],
        compression_ratio=0.5,
        preserved=["fact A"],
        dropped=["turn content"],
        risky_drops=[],
        requires_review=False,
    )
    dumped = data.model_dump()
    assert dumped["loss_report_id"] == "lr-1"
    assert dumped["schema_version"] == 1
