import logging
from unittest.mock import MagicMock

from apps.reference.core.time.clock import LiveClock


class _DummyDM:
    def __init__(self):
        self.logger = logging.getLogger("tests.dm.degraded_ctx_gate")
        self.emitted: list[dict] = []
        self.blocked: list[str] = []
        self._clock = LiveClock()

        self._fail_closed_on_degraded_context = True
        self._degraded_context_critical_keys = {"ema_bias", "price"}
        self._degraded_context_critical_keys_by_strategy = {}

        from apps.reference.domains.decision_making.readiness_gates import ReadinessGates

        def _emit_deferred(**kw):
            self.emitted.append(kw)

        def _record_blocked(symbol):
            self.blocked.append(symbol)

        self._readiness = ReadinessGates(
            clock=self._clock,
            config=MagicMock(),
            features_ttl_sec=60,
            symbol_states={},
            per_symbol_regimes={},
            get_portfolio=lambda: None,
            get_exposure_cache=lambda: (None, 0.0),
            emit_intent_deferred_v1=_emit_deferred,
            record_blocked_intent=_record_blocked,
            fail_closed_on_degraded_context=self._fail_closed_on_degraded_context,
            degraded_context_critical_keys=self._degraded_context_critical_keys,
            degraded_context_critical_keys_by_strategy=self._degraded_context_critical_keys_by_strategy,
            logger=self.logger,
        )

    def _emit_intent_deferred_v1(self, **payload):
        self.emitted.append(payload)

    def _record_blocked_intent(self, symbol: str) -> None:
        self.blocked.append(symbol)


def test_degraded_context_gate_defers_on_missing_critical_features():
    from apps.reference.domains.decision_making.decision_context import create_decision_context
    from apps.reference.domains.decision_making.decision_making import DecisionMaking
    from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons

    dm = _DummyDM()

    # Bind the method from DecisionMaking onto our dummy instance.
    gate = DecisionMaking._degraded_context_gate_should_defer.__get__(dm, _DummyDM)

    # Features missing critical keys.
    features_evt = {"ts": 123, "features": {}}
    ctx = create_decision_context("BTCUSDT", 123, features_evt["features"])

    should_defer = gate(symbol="BTCUSDT", rid="rid-1", ctx=ctx, features_evt=features_evt)

    assert should_defer is True
    assert dm.blocked == ["BTCUSDT"]
    assert len(dm.emitted) == 1

    emitted = dm.emitted[0]
    assert emitted["symbol"] == "BTCUSDT"
    assert emitted["reason"] == NormalizedRejectReasons.DATA_NOT_READY
    assert emitted["original_event_name"] == "EVT:FEATURES_CALCULATED"
    assert "missing_critical" in emitted["original_payload_min"]
    assert emitted["original_payload_min"]["missing_critical"]
