from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.reference.domains.decision_making.readiness_gates import ReadinessGates
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector


class _ClockStub:
    def __init__(self, now_ms: int) -> None:
        self._now_ms = int(now_ms)

    def now_ms(self) -> int:
        return int(self._now_ms)


def test_anchor_missing_ts_produces_explicit_blocker_signal() -> None:
    fe = FeatureEngineering.__new__(FeatureEngineering)
    fe._anchor_intake_diag = {}
    fe._fe_readiness_diag = {}
    fe._macro_sync_anchor_ts_missing = False
    fe.logger = MagicMock()

    evt = SimpleNamespace(
        pld={"anchor": "BTCUSDT", "price": "100.0", "ts_ms": None})
    fe._on_anchor_updated_event(evt)

    evidence = fe.get_live_blocker_evidence("BTCUSDT")
    anchor = evidence["anchor_intake"]["BTCUSDT"]
    assert anchor["updates_received"] == 1
    assert anchor["missing_ts_ms"] == 1
    assert anchor["malformed_ts_ms"] == 0
    assert anchor["anchor_ts_missing_latch"] is True


def test_fe_warmup_false_cmd_suppression_is_counted_and_explained() -> None:
    fe = FeatureEngineering.__new__(FeatureEngineering)
    fe._fe_readiness_diag = {}

    diag = fe._record_cmd_blocked(
        "DOGEUSDT",
        300,
        reason_code="WARMUP_NOT_FULL_READY",
        why="warmup full_ready=false",
        warmup={"full_ready": False, "ready": {
            "macro_sync": False, "ema_bias": True}},
    )

    assert diag.cmd_blocked == 1
    assert diag.cmd_suppressed_due_to_warmup is True
    assert diag.last_cmd_block_reason_code == "WARMUP_NOT_FULL_READY"
    assert diag.last_cmd_block_why == "warmup full_ready=false"
    assert diag.warmup_full_ready is False
    assert "macro_sync" in diag.warmup_false_keys


def test_features_emitted_vs_cmd_emitted_divergence_is_visible() -> None:
    fe = FeatureEngineering.__new__(FeatureEngineering)
    fe._anchor_intake_diag = {}
    fe._fe_readiness_diag = {}

    fe._record_features_emitted(
        "DOGEUSDT", 300, {"full_ready": True, "ready": {}})
    fe._record_features_emitted(
        "DOGEUSDT", 300, {"full_ready": True, "ready": {}})
    fe._record_cmd_emitted("DOGEUSDT", 300, {"full_ready": True, "ready": {}})

    evidence = fe.get_live_blocker_evidence("DOGEUSDT")
    readiness = evidence["fe_readiness"]["DOGEUSDT:300"]
    assert readiness["features_emitted"] == 2
    assert readiness["cmd_emitted"] == 1
    assert readiness["cmd_blocked"] == 0


def test_rd_basis_lag_or_missing_emit_is_visible() -> None:
    rd = RegimeDetector.__new__(RegimeDetector)
    rd._basis_tf_sec = 300
    rd._rd_diag = {}

    rd._update_basis_diag(
        symbol="BTCUSDT",
        close_boundary_ts_ms=300_000,
        warmup={"full_ready": True, "reasons": []},
        emit_ts_ms=300_000,
    )
    rd._update_basis_diag(
        symbol="BTCUSDT",
        close_boundary_ts_ms=1_000_000,
        warmup={"full_ready": False, "reasons": ["atr_not_ready"]},
        emit_ts_ms=1_000_000,
    )

    evidence = rd.get_live_blocker_evidence("BTCUSDT")["BTCUSDT"]
    assert evidence["fe_basis_bars_seen"] == 2
    assert evidence["rd_basis_events_received"] == 2
    assert evidence["last_rd_emit_ts_ms"] == 1_000_000
    assert evidence["rd_warmup_full_ready"] is False
    assert evidence["rd_lagging_expected_fe_basis_cadence"] is True
    assert evidence["rd_lag_events"] >= 1


def test_dm_dual_warmup_blocker_visibility_is_explicit() -> None:
    symbol = "BTCUSDT"
    now_ms = 2_000_000
    features_evt = {
        "ts": now_ms,
        "tf_sec": 300,
        "warmup": {"full_ready": False, "ready": {"macro_sync": False}},
    }

    gate = ReadinessGates(
        clock=_ClockStub(now_ms),
        config=SimpleNamespace(
            domains=SimpleNamespace(
                decision_making=SimpleNamespace(
                    warmup=SimpleNamespace(enforcement_mode="fail_fast"))
            ),
            system=None,
        ),
        features_ttl_sec=10,
        symbol_states={
            symbol: {"features": features_evt, "risk": {"ok": True}}},
        per_symbol_regimes={
            symbol: {"warmup": {"full_ready": False, "ticks_seen": 7}}},
        get_portfolio=lambda: {"equity": "1000"},
        get_exposure_cache=lambda: ({}, {}),
        emit_intent_deferred_v1=lambda **_: None,
        record_blocked_intent=lambda _symbol: None,
        fail_closed_on_degraded_context=False,
        degraded_context_critical_keys=None,
        degraded_context_critical_keys_by_strategy=None,
        logger=MagicMock(),
    )

    blocked = gate.warmup_gate_before_trade_intent(
        symbol=symbol,
        rid="rid-1",
        reduce_only=False,
        context="unit-test",
    )
    assert blocked is True

    evidence = gate.get_live_blocker_evidence(symbol)[symbol]
    assert evidence["blocked_by_fe_warmup"] is True
    assert evidence["blocked_by_rd_warmup"] is True
    assert evidence["blocked_by_both"] is True
    assert evidence["last_blocking_reason_code"] == "regime_not_ready"
