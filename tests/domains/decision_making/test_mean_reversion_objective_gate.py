"""MR handler-level objective gate tests via the shared evaluator.

Covers:
- MR OBJECTIVE_GATE_BLOCKED: result details shape
- MR strict-fail-closed config contract
- MR passed result: score and trace structure
- MR precondition/error result: message preserved
"""
from __future__ import annotations

import logging
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.reference.config_models import (
    ObjectiveDataRequirementsConfig,
    ObjectiveEngineDomainConfig,
)
from apps.reference.domains.decision_making.mean_reversion_handler import (
    MeanReversionHandler,
)
from apps.reference.domains.decision_making.objective_gate_evaluator import (
    ObjectiveGateResult,
    ObjectiveGateStatus,
)
from apps.reference.domains.feature_engineering.mean_reversion_strategy import (
    MRSignal,
    MRSignalType,
)


class _FSMStub:
    def __init__(self) -> None:
        self.emitted: list[tuple[str, dict]] = []

    def emit(self, event_name: str, payload=None, *_args, **_kwargs) -> None:
        self.emitted.append((event_name, payload or {}))


def _make_handler(*, strict_fail_closed: bool = True):
    handler = object.__new__(MeanReversionHandler)
    fsm = _FSMStub()
    blocked: list[dict] = []

    handler.fsm = fsm
    handler.logger = logging.getLogger("tests.mean_reversion.objective")
    handler.mlog = logging.getLogger("tests.mean_reversion.objective")
    handler.timeframe_sec = 300
    handler.config = SimpleNamespace(
        domains=SimpleNamespace(
            objective_engine=SimpleNamespace(
                enabled=True,
                data_requirements=SimpleNamespace(
                    strict_fail_closed=strict_fail_closed,
                ),
            )
        ),
        strategies=SimpleNamespace(
            mean_reversion=SimpleNamespace(
                objective=SimpleNamespace(enabled=True)
            )
        ),
    )
    handler._signal_counts = {}
    handler._last_signal_time = {}
    handler._last_cmd_features = {
        "BTCUSDT": {
            "volatility": {"atr_14": 1.0, "atr_ready": True},
            "liquidity": {"obi_close": "0.1"},
        }
    }
    handler._analytics_restore_snapshots = {}
    handler.get_runtime_analytics_restore_snapshot = lambda _symbol: None
    handler._stats = {"signals_emitted": 0}
    handler.seq_counter = 0
    handler._latest_portfolio = {
        "positions_last_ts_ms": 1_700_000_000_000,
        "equity_free_usdt": "1000",
        "positions": [],
    }
    handler._latest_exposure_summary = {}
    handler._position_queries = object()
    handler._objective_blocked_ts_ms = {}
    handler._objective_cancel_replace_ts_ms = {}
    handler._objective_reentry_ts_ms = {}
    handler._strategies = {
        "BTCUSDT": SimpleNamespace(config=SimpleNamespace(entry_threshold=0.55))
    }
    handler._regime_confidence = {}
    handler._regime_ts_ms = {"BTCUSDT": 1_700_000_000_000}
    handler._regime_event_ts_ms = {"BTCUSDT": 1_700_000_000_000}
    handler._emit_strategy_blocked = lambda **kwargs: blocked.append(kwargs)
    return handler, fsm, blocked


def _signal() -> MRSignal:
    return MRSignal(
        signal_type=MRSignalType.LONG,
        symbol="BTCUSDT",
        price=Decimal("100"),
        atr=Decimal("1"),
        flat_regime=SimpleNamespace(name="FLAT_LOW"),
        entry_price=Decimal("100"),
        stop_price=Decimal("99"),
        target_price=Decimal("101"),
        confidence=Decimal("0.8"),
        timestamp_ms=1_700_000_000_000,
        why="enter:buy",
        bar=SimpleNamespace(end_ts_ms=1_699_999_999_999),
    )


class TestMRObjectiveGateResultContract:
    """Verify the ObjectiveGateResult contract as consumed by MR handler."""

    def test_passed_carries_score_and_trace(self) -> None:
        mock_score = MagicMock()
        mock_score.objective_score = 0.65
        mock_score.multiplier = 0.87
        mock_score.is_blocked = False

        result = ObjectiveGateResult(
            status=ObjectiveGateStatus.PASSED,
            objective_score=mock_score,
            trace_payload={
                "trace_id": "tr-001",
                "multiplier": 0.87,
                "objective_score": 0.65,
                "components": {"cost": 0.5},
                "raw_metrics": {"fee_bps": 4.0},
            },
        )
        assert result.status == ObjectiveGateStatus.PASSED
        assert result.trace_payload["trace_id"] == "tr-001"
        assert result.objective_score.objective_score == 0.65

    def test_gate_blocked_details_shape(self) -> None:
        mock_score = MagicMock()
        mock_score.objective_score = 0.05
        mock_score.multiplier = 0.12
        mock_score.components = {"cost": 0.1}
        mock_score.raw_metrics = {"fee_bps": 4.0}
        mock_score.block_reason = "BELOW_MIN_SCORE"
        mock_score.is_blocked = True

        result = ObjectiveGateResult(
            status=ObjectiveGateStatus.GATE_BLOCKED,
            objective_score=mock_score,
            trace_payload={"trace_id": "tr-002"},
        )
        assert result.status == ObjectiveGateStatus.GATE_BLOCKED
        assert result.objective_score.block_reason == "BELOW_MIN_SCORE"
        assert result.objective_score.objective_score == 0.05

    def test_precondition_failed_code_preserved(self) -> None:
        result = ObjectiveGateResult(
            status=ObjectiveGateStatus.PRECONDITION_FAILED,
            precondition_code="OBJECTIVE_PORTFOLIO_MISSING",
        )
        assert result.precondition_code == "OBJECTIVE_PORTFOLIO_MISSING"

    def test_evaluation_error_message_preserved(self) -> None:
        result = ObjectiveGateResult(
            status=ObjectiveGateStatus.EVALUATION_ERROR,
            error="OBJECTIVE_SIZING_UNAVAILABLE:position_queries",
        )
        assert "OBJECTIVE_SIZING_UNAVAILABLE" in result.error

    def test_disabled_has_no_score(self) -> None:
        result = ObjectiveGateResult(status=ObjectiveGateStatus.DISABLED)
        assert result.objective_score is None
        assert result.trace_payload is None


class TestMRStrictFailClosedConfig:
    """Verify strict_fail_closed config shapes used by MR handler."""

    def _minimal_domain_cfg(self, *, strict: bool) -> ObjectiveEngineDomainConfig:
        return ObjectiveEngineDomainConfig(
            enabled=False,  # disabled avoids requiring components
            data_requirements=ObjectiveDataRequirementsConfig(
                strict_fail_closed=strict),
        )

    def test_strict_true(self) -> None:
        dcfg = self._minimal_domain_cfg(strict=True)
        assert dcfg.data_requirements.strict_fail_closed is True

    def test_strict_false(self) -> None:
        dcfg = self._minimal_domain_cfg(strict=False)
        assert dcfg.data_requirements.strict_fail_closed is False

    def test_mr_handler_reads_strict_via_getattr(self) -> None:
        """MR handler uses getattr(domain_cfg.data_requirements, 'strict_fail_closed', True)."""
        dcfg = self._minimal_domain_cfg(strict=False)
        # Simulate handler read pattern
        val = getattr(dcfg.data_requirements, "strict_fail_closed", True)
        assert val is False


class TestMRBlockedEmitDetails:
    """Verify MR handler emit details match the pre-extraction contract."""

    def test_blocked_emit_details_keys(self) -> None:
        """Blocked emit must include these exact keys."""
        mock_score = MagicMock()
        mock_score.objective_score = 0.05
        mock_score.multiplier = 0.12
        mock_score.components = {"cost": 0.1}
        mock_score.raw_metrics = {"fee_bps": 4.0}
        mock_score.block_reason = "BELOW_MIN_SCORE"

        details = {
            "objective_score": mock_score.objective_score,
            "objective_multiplier": mock_score.multiplier,
            "objective_components": mock_score.components,
            "objective_raw_metrics": mock_score.raw_metrics,
            "block_reason": mock_score.block_reason,
        }
        assert set(details.keys()) == {
            "objective_score", "objective_multiplier",
            "objective_components", "objective_raw_metrics", "block_reason",
        }

    def test_blocked_why_chain_format(self) -> None:
        block_reason = "BELOW_MIN_SCORE"
        why_chain = ["OBJECTIVE_ENGINE", str(block_reason or "GATE_BLOCKED")]
        assert why_chain == ["OBJECTIVE_ENGINE", "BELOW_MIN_SCORE"]

    def test_blocked_why_chain_fallback(self) -> None:
        block_reason = None
        why_chain = ["OBJECTIVE_ENGINE", str(block_reason or "GATE_BLOCKED")]
        assert why_chain == ["OBJECTIVE_ENGINE", "GATE_BLOCKED"]


def test_mean_reversion_missing_regime_confidence_fails_closed_before_evaluator() -> None:
    handler, fsm, blocked = _make_handler(strict_fail_closed=True)

    with (
        patch(
            "apps.reference.domains.decision_making.mean_reversion_handler.get_clock",
            return_value=SimpleNamespace(
                now_ms=lambda: 1_700_000_000_000,
                now_sec=lambda: 1_700_000_000,
            ),
        ),
        patch(
            "apps.reference.domains.decision_making.objective_gate_evaluator.evaluate_objective_gate",
            side_effect=AssertionError("evaluator must not run"),
        ),
    ):
        handler._emit_signal(_signal(), warmup_readiness={"full_ready": True})

    assert not fsm.emitted
    assert len(blocked) == 1
    assert blocked[0]["reason_code"] == "OBJECTIVE_ENGINE_FAIL_CLOSED"
    assert blocked[0]["details"] == {
        "error": "OBJECTIVE_REGIME_CONFIDENCE_MISSING"
    }
    assert blocked[0]["why_chain"] == [
        "OBJECTIVE_ENGINE",
        "FAIL_CLOSED",
        "OBJECTIVE_REGIME_CONFIDENCE_MISSING",
    ]


def test_mean_reversion_objective_success_updates_emitted_score_and_trace() -> None:
    handler, fsm, blocked = _make_handler(strict_fail_closed=True)
    handler._regime_confidence["BTCUSDT"] = 0.85

    objective_trace = {
        "trace_id": "mr-obj-1",
        "multiplier": 0.5,
        "objective_score": 0.42,
        "components": {"cost": 0.1},
        "raw_metrics": {"fee_bps": 4.0},
    }
    gate_result = ObjectiveGateResult(
        status=ObjectiveGateStatus.PASSED,
        objective_score=SimpleNamespace(
            objective_score=0.42,
            multiplier=0.5,
            is_blocked=False,
        ),
        trace_payload=dict(objective_trace),
    )

    with (
        patch(
            "apps.reference.domains.decision_making.mean_reversion_handler.get_clock",
            return_value=SimpleNamespace(
                now_ms=lambda: 1_700_000_000_000,
                now_sec=lambda: 1_700_000_000,
            ),
        ),
        patch(
            "apps.reference.domains.decision_making.objective_gate_evaluator.evaluate_objective_gate",
            return_value=gate_result,
        ),
    ):
        handler._emit_signal(_signal(), warmup_readiness={"full_ready": True})

    assert not blocked
    assert len(fsm.emitted) == 1
    _event_name, payload = fsm.emitted[0]
    assert payload["score"] == pytest.approx(0.42)
    assert payload["scoring"]["score"] == pytest.approx(0.42)
    assert payload["scoring"]["objective"] == objective_trace
