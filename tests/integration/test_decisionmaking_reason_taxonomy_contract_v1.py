import time

from vfoundation.core.fsm_core import FSMCore

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.decision_making.normalized_reject_reasons import NormalizedRejectReasons
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector


def test_intent_deferred_reason_is_nrr_normalizable_for_warmup_guard() -> None:
    cfg = ConfigLoader().load_config()
    fsm = FSMCore()

    deferred: list[dict] = []
    fsm.listen("EVT:INTENT_DEFERRED", lambda msg: deferred.append(msg.pld))

    # Order matters: RegimeDetector listener should run before DecisionMaking.on_features.
    det = RegimeDetector(config=cfg, fsm=fsm)
    _dm = DecisionMaking(fsm=fsm, config=cfg)
    det.start()

    symbol = "ETHUSDT"

    # Provide portfolio + risk so DM reaches arming/warmup paths.
    fsm.emit(
        "EVT:PORTFOLIO_STATE_UPDATED",
        {"equity_free_usdt": "1000", "equity_cross_usdt": "1000", "positions": []},
        why="test",
    )
    fsm.emit(
        "EVT:RISK_ASSESSMENT_COMPLETED",
        {"symbol": symbol, "risk_parameters": {"is_trading_allowed": True}},
        why="test",
    )

    now_ms = int(time.time() * 1000)
    fsm.emit(
        "EVT:FEATURES_CALCULATED",
        {"ts": now_ms, "symbol": symbol, "features": {"price": "100.0"}},
        why="test",
    )

    # Force a warmup-not-ready regime event to drive a defer.
    fsm.emit(
        "EVT:REGIME_DETECTED",
        {"symbol": symbol, "regime": "UNCERTAIN", "warmup": {"full_ready": False, "ticks_seen": 1}},
        why="test",
    )

    # Depending on config, DM may defer or silently block. If it defers, reason must be normalizable.
    for d in deferred:
        reason = str(d.get("reason") or "")
        assert NormalizedRejectReasons.normalize(reason) != NormalizedRejectReasons.UNKNOWN_ERROR
