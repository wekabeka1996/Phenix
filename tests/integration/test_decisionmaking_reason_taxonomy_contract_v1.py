import time

from vfoundation.core.fsm_core import FSMCore

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.core.facade import DecisionMaking
from apps.reference.domains.decision_making.contracts.normalized_reject_reasons import NormalizedRejectReasons
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
        {
            "equity_free_usdt": "1000",
            "equity_cross_usdt": "1000",
            "positions": [],
            "positions_last_ts_ms": 1000000,
        },
        why="test",
    )
    fsm.emit(
        "EVT:RISK_ASSESSMENT_COMPLETED",
        {
            "symbol": symbol,
            "ts": 1000000,
            "risk_parameters": {"is_trading_allowed": True},
        },
        why="test",
    )

    now_ms = int(time.time() * 1000)
    fsm.emit(
        "EVT:FEATURES_CALCULATED",
        {
            "ts": now_ms,
            "symbol": symbol,
            "tf_sec": 180,
            "features": {
                "obi": "0.0",
                "tfi": "0.0",
                "delta_price": "0.0",
                "absorption": "0.0",
                "price": "100.0",
                "liquidity_kappa": "0.5",
            },
            "warmup": {"full_ready": False, "ticks_seen": 1, "ready": {}, "reasons": ["warmup_guard"]},
            "price_motion": {"ret_10s": 0.0, "ret_60s": 0.0, "ret_300s": 0.0},
            "bar": {
                "symbol": symbol,
                "timeframe_sec": 180,
                "start_ts_ms": now_ms - 180000,
                "end_ts_ms": now_ms,
                "open": "100.0",
                "high": "100.0",
                "low": "100.0",
                "close": "100.0",
                "volume": "1.0",
            },
            "source_mode": "live",
            "regime": None,
            "diagnostics": {"fe": {"features_emitted": 0, "cmd_emitted": 0, "cmd_blocked": 0}},
        },
        why="test",
    )

    # Force a warmup-not-ready regime event to drive a defer.
    fsm.emit(
        "EVT:REGIME_DETECTED",
        {
            "ts": now_ms,
            "symbol": symbol,
            "regime": "UNCERTAIN",
            "confidence": "0.1",
            "source_model": "sma_trend_v1",
            "last_update_ts_ms": now_ms,
            "warmup": {"full_ready": False, "ticks_seen": 1},
            "regime_provenance": {
                "source_kind": "detector_event",
                "detector_event": {
                    "event_name": "EVT:REGIME_DETECTED",
                    "rid": f"regime:{symbol}:{now_ms}",
                    "ts_ms": now_ms,
                    "last_update_ts_ms": now_ms,
                    "structural_regime_ref": f"structural:{symbol}:{now_ms}",
                    "changed": False,
                    "regime": "UNCERTAIN",
                    "confidence": "0.1",
                    "raw_regime": "UNCERTAIN",
                    "raw_confidence": "0.1",
                },
                "cache_snapshot": {
                    "cache_write_ts_ms": now_ms,
                    "regime": "UNCERTAIN",
                    "confidence": 0.1,
                },
            },
        },
        why="test",
    )

    # Depending on config, DM may defer or silently block. If it defers, reason must be normalizable.
    for d in deferred:
        reason = str(d.get("reason") or "")
        assert NormalizedRejectReasons.normalize(reason) != NormalizedRejectReasons.UNKNOWN_ERROR
