import logging
from apps.reference.core.time.clock import LiveClock


class _DummyDM:
    def __init__(self):
        self.logger = logging.getLogger("tests.dm.degraded_ctx_gate")
        self.emitted: list[dict] = []
        self.blocked: list[str] = []
        self._clock = LiveClock()

        # Enable the gate explicitly.
        self._fail_closed_on_degraded_context = True

    def _stable_retry_key(self, *, prefix: str, symbol: str, rid: str | None, side: str | None = None, ts_ms: int | None = None) -> str:
        # Keep deterministic for tests.
        return f"{prefix}:{symbol}:{rid}:{ts_ms}"

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
