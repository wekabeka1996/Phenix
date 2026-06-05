"""
Phase 11.2-11.4 tests: why_chain_coverage, otlp_exporter, alert_manager.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, List

import pytest

# ── why_chain_coverage ────────────────────────────────────────────────────────
from vfoundation.obs.why_chain_coverage import analyze_why_chain, WhyCoverageReport


class TestWhyChainCoverage:
    def test_empty_records_returns_full_coverage(self) -> None:
        """Empty input should return 100% coverage (vacuously true)."""
        report = analyze_why_chain([])
        assert report.coverage_pct == 100.0
        assert report.total_events == 0

    def test_all_events_have_why(self) -> None:
        """All events with non-empty WHY → 100% is_fully_covered."""
        records = [
            {"rid": "r1", "verb": "EVAL", "why": "initial evaluation"},
            {"rid": "r1", "verb": "OPEN", "why": "position opened by signal"},
        ]
        report = analyze_why_chain(records, rid="r1")
        assert report.is_fully_covered is True
        assert report.coverage_pct == 100.0
        assert report.missing_why == []

    def test_missing_why_detected(self) -> None:
        """Events with no WHY should appear in missing_why list."""
        records = [
            {"rid": "r1", "verb": "EVAL", "why": ""},
            {"rid": "r1", "verb": "OPEN", "why": "opened"},
        ]
        report = analyze_why_chain(records)
        assert len(report.missing_why) == 1
        assert report.missing_why[0].verb == "EVAL"
        assert report.is_fully_covered is False

    def test_weak_why_detected(self) -> None:
        """WHY shorter than min_length (but non-empty) should be in weak_why."""
        records = [{"rid": "r1", "verb": "CLOSE", "why": "ok"}]  # < 5 chars
        report = analyze_why_chain(records, why_min_length=5)
        assert len(report.weak_why) == 1
        assert report.weak_why[0].verb == "CLOSE"

    def test_coverage_pct_calculation(self) -> None:
        """coverage_pct should be covered/total * 100.0."""
        records = [
            {"rid": "r1", "verb": "A", "why": "covered event"},
            {"rid": "r1", "verb": "B", "why": "covered event"},
            {"rid": "r1", "verb": "C", "why": ""},  # missing
            {"rid": "r1", "verb": "D", "why": "covered event"},
        ]
        report = analyze_why_chain(records)
        assert report.coverage_pct == pytest.approx(75.0)

    def test_rid_auto_detected(self) -> None:
        """rid should be auto-detected from first record if not supplied."""
        records = [{"rid": "auto-rid", "verb": "EVAL", "why": "test"}]
        report = analyze_why_chain(records)
        assert report.rid == "auto-rid"


# ── otlp_exporter ─────────────────────────────────────────────────────────────
from vfoundation.obs.otlp_exporter import NoopOTLPExporter, OTLPExporter, SpanRecord


class TestNoopOTLPExporter:
    def test_is_otlp_exporter_subclass(self) -> None:
        """NoopOTLPExporter must implement OTLPExporter ABC."""
        exporter = NoopOTLPExporter()
        assert isinstance(exporter, OTLPExporter)

    def test_export_increments_count(self) -> None:
        """export() should count total spans exported."""
        exporter = NoopOTLPExporter()
        spans = [
            SpanRecord(trace_id="t1", span_id="s1", name="test"),
            SpanRecord(trace_id="t1", span_id="s2", name="test2"),
        ]
        exporter.export(spans)
        assert exporter.export_count == 2, f"expected 2 spans counted, got {exporter.export_count}"

    def test_is_healthy_before_shutdown(self) -> None:
        """is_healthy should return True before shutdown."""
        exporter = NoopOTLPExporter()
        assert exporter.is_healthy is True

    def test_shutdown_marks_unhealthy(self) -> None:
        """After shutdown(), is_healthy should return False."""
        exporter = NoopOTLPExporter()
        exporter.shutdown()
        assert exporter.is_healthy is False

    def test_export_empty_batch(self) -> None:
        """export([]) should not raise and increment count by 0."""
        exporter = NoopOTLPExporter()
        exporter.export([])
        assert exporter.export_count == 0

    def test_span_record_structure(self) -> None:
        """SpanRecord should be constructable with required fields."""
        span = SpanRecord(
            trace_id="trace-001", span_id="span-001", name="fsm.eval",
            rid="r1", attributes={"verb": "EVAL"}, status_ok=True
        )
        assert span.rid == "r1"
        assert span.attributes["verb"] == "EVAL"


# ── alert_manager ─────────────────────────────────────────────────────────────
from vfoundation.obs.alert_manager import (
    Alert, AlertHook, AlertLevel, AlertManager, InMemoryAlertHook
)


class TestAlertManager:
    @pytest.fixture()
    def manager(self) -> AlertManager:
        return AlertManager()

    @pytest.fixture()
    def hook(self) -> InMemoryAlertHook:
        return InMemoryAlertHook()

    def test_register_hook(self, manager: AlertManager, hook: InMemoryAlertHook) -> None:
        """Registered hook should receive fired alerts."""
        manager.register(hook)
        alert = Alert(level=AlertLevel.WARNING, title="Test", message="test message")
        manager.fire(alert)
        assert len(hook.alerts) == 1
        assert hook.alerts[0].title == "Test"

    def test_fire_increments_fired_total(self, manager: AlertManager) -> None:
        """fire() should increment fired_total counter."""
        manager.fire(Alert(level=AlertLevel.INFO, title="t", message="m"))
        assert manager.fired_total == 1

    def test_min_level_filter(self) -> None:
        """Alerts below min_level should be silently dropped."""
        manager = AlertManager(min_level=AlertLevel.ERROR)
        hook = InMemoryAlertHook()
        manager.register(hook)
        manager.fire(Alert(level=AlertLevel.INFO, title="low", message="below min"))
        manager.fire(Alert(level=AlertLevel.WARNING, title="warn", message="below min"))
        manager.fire(Alert(level=AlertLevel.ERROR, title="err", message="at min"))
        assert len(hook.alerts) == 1
        assert hook.alerts[0].title == "err"

    def test_hook_error_suppressed(self, manager: AlertManager) -> None:
        """Hook that raises should NOT propagate exception; error_total incremented."""
        class BrokenHook(AlertHook):
            def on_alert(self, alert: Alert) -> None:
                raise RuntimeError("hook failure")

        manager.register(BrokenHook())
        manager.fire(Alert(level=AlertLevel.CRITICAL, title="t", message="m"))
        assert manager.error_total == 1

    def test_multiple_hooks_all_receive(self, manager: AlertManager) -> None:
        """All registered hooks should receive the alert."""
        hooks = [InMemoryAlertHook() for _ in range(3)]
        for h in hooks:
            manager.register(h)
        manager.fire(Alert(level=AlertLevel.WARNING, title="multi", message="m"))
        for h in hooks:
            assert len(h.alerts) == 1

    def test_alert_title_too_long_raises(self) -> None:
        """Alert with title > 120 chars should raise ValueError."""
        with pytest.raises(ValueError, match="120"):
            Alert(level=AlertLevel.INFO, title="x" * 121, message="m")

    def test_thread_safety(self, manager: AlertManager, hook: InMemoryAlertHook) -> None:
        """Concurrent fire() calls should not lose alerts."""
        manager.register(hook)
        errors: List[Exception] = []

        def fire_worker() -> None:
            try:
                for _ in range(10):
                    manager.fire(Alert(level=AlertLevel.INFO, title="t", message="m"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=fire_worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == [], f"expected no errors, got {errors}"
        assert len(hook.alerts) == 50, f"expected 50 alerts, got {len(hook.alerts)}"
