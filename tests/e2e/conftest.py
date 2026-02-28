"""
Shared fixtures for E2E tests (TASK26).

Provides:
- Mock FSM and config fixtures
- Metric collector hooks
- Proof artifact generation on session finish
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Generator

import pytest

from tests.e2e.scenario_runner import (
    MockFSM,
    ScenarioRunner,
    MetricCollector,
    MetricsSnapshot,
)


# Global collectors for proof artifact generation
_all_timelines: list = []
_all_metrics: list = []
_all_failure_modes: list = []


@pytest.fixture
def mock_fsm() -> MockFSM:
    """Provide clean MockFSM for each test."""
    return MockFSM()


@pytest.fixture
def scenario_runner(request) -> Generator[ScenarioRunner, None, None]:
    """Provide ScenarioRunner that auto-collects proof artifacts."""
    # Use test name as scenario name
    scenario_name = request.node.name
    runner = ScenarioRunner(scenario_name)
    
    yield runner
    
    # Collect artifacts after test
    _all_timelines.append({
        "scenario": scenario_name,
        "events": [e.to_dict() for e in runner.timeline],
    })
    _all_metrics.append({
        "scenario": scenario_name,
        "metrics": runner.metrics.to_dict(),
    })
    _all_failure_modes.extend([
        {"scenario": scenario_name, **fm.to_dict()} for fm in runner.failure_modes
    ])


@pytest.fixture
def metric_collector(scenario_runner: ScenarioRunner) -> MetricCollector:
    """Provide metric collector tied to scenario runner."""
    return MetricCollector(scenario_runner.metrics)


@pytest.fixture
def monkeypatch_metrics(monkeypatch, metric_collector: MetricCollector):
    """Monkeypatch telemetry metrics to use collector."""
    monkeypatch.setattr(
        "apps.reference.telemetry.metrics.inc_warmup_block",
        metric_collector.inc_warmup_block,
    )
    monkeypatch.setattr(
        "apps.reference.telemetry.metrics.inc_data_quality_drop",
        metric_collector.inc_data_quality_drop,
    )
    monkeypatch.setattr(
        "apps.reference.telemetry.metrics.inc_data_quality_bad_dt",
        metric_collector.inc_data_quality_bad_dt,
    )
    monkeypatch.setattr(
        "apps.reference.telemetry.metrics.inc_retry_scheduler_no_loop",
        metric_collector.inc_retry_scheduler_no_loop,
    )
    return metric_collector


def pytest_sessionfinish(session, exitstatus):
    """Generate proof artifacts after test session."""
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    
    # Only generate if e2e tests ran
    if not _all_timelines:
        return
    
    # TASK26_proof_timeline.md
    timeline_md = ["# TASK26 Proof Timeline", "", "## Scenarios", ""]
    for scenario_data in _all_timelines:
        timeline_md.append(f"### {scenario_data['scenario']}")
        timeline_md.append("")
        timeline_md.append("| ts_ms | event_type | source | payload |")
        timeline_md.append("|-------|------------|--------|---------|")
        for evt in scenario_data["events"][:20]:  # Limit to 20 events per scenario
            payload_str = json.dumps(evt["payload"])[:40] + "..." if len(json.dumps(evt["payload"])) > 40 else json.dumps(evt["payload"])
            timeline_md.append(f"| {evt['ts_ms']} | {evt['event_type']} | {evt['source']} | {payload_str} |")
        timeline_md.append("")
    
    (reports_dir / "TASK26_proof_timeline.md").write_text("\n".join(timeline_md), encoding="utf-8")
    
    # TASK26_metrics_snapshot.json
    metrics_data = {
        "generated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ"),
        "scenarios": _all_metrics,
        "summary": {
            "total_warmup_blocks": sum(m["metrics"]["warmup_blocks"] for m in _all_metrics),
            "total_data_quality_drops": sum(m["metrics"]["data_quality_drops"] for m in _all_metrics),
            "total_retry_no_loop": sum(m["metrics"]["retry_scheduler_no_loop"] for m in _all_metrics),
            "total_intents_proposed": sum(m["metrics"]["intents_proposed"] for m in _all_metrics),
            "total_intents_dropped": sum(m["metrics"]["intents_dropped"] for m in _all_metrics),
        },
    }
    (reports_dir / "TASK26_metrics_snapshot.json").write_text(json.dumps(metrics_data, indent=2), encoding="utf-8")
    
    # TASK26_failure_modes.md
    fm_md = [
        "# TASK26 Failure Modes",
        "",
        "How the system fails closed (safe) in error conditions.",
        "",
        "| Scenario | Trigger | Expected | Observed | Fail-Closed |",
        "|----------|---------|----------|----------|-------------|",
    ]
    for fm in _all_failure_modes:
        closed = "✅" if fm["fail_closed"] else "❌"
        fm_md.append(f"| {fm['scenario']} | {fm['trigger']} | {fm['expected_behavior']} | {fm['observed_behavior']} | {closed} |")
    
    (reports_dir / "TASK26_failure_modes.md").write_text("\n".join(fm_md), encoding="utf-8")
