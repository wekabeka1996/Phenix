from types import SimpleNamespace
import time

from apps.reference.config_loader import get_config
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
from apps.reference.domains.decision_making.aurora_handler import AuroraHandler
from apps.reference.domains.decision_making.quadratic_scoring_kernel import QuadraticScoringKernel


class _MockFSM:
    def __init__(self) -> None:
        self.listeners: dict[str, list] = {}
        self.emitted: list[tuple[str, dict, str | None, object | None]] = []

    def listen(self, event: str, handler) -> None:
        self.listeners.setdefault(event, []).append(handler)

    def emit(self, event_name: str, payload=None, why=None, data_ref=None) -> None:
        payload = payload or {}
        self.emitted.append((event_name, payload, why, data_ref))
        msg = SimpleNamespace(pld=payload, verb=event_name.split(":")[-1], op=event_name.split(":")[0])
        for handler in self.listeners.get(event_name, []):
            handler(msg)


def _bar(symbol: str, tf_sec: int, ts_ms: int, close: str = "100.0") -> dict:
    return {
        "symbol": symbol,
        "timeframe_sec": tf_sec,
        "open": close,
        "high": close,
        "low": close,
        "close": close,
        "volume": "10.0",
        "end_ts_ms": ts_ms,
    }


def test_internal_h4_bar_updates_pillars_without_emission() -> None:
    cfg = get_config().model_copy(deep=True)
    cfg.domains.feature_engineering.enabled_timeframes_sec = [300]
    cfg.domains.feature_engineering.warmup.enforcement_mode = "disabled"
    cfg.domains.feature_engineering.pillars.enabled = True
    cfg.domains.feature_engineering.pillars.tactician.timeframe_sec = 300
    cfg.domains.feature_engineering.pillars.operator.timeframe_sec = 14400
    cfg.domains.feature_engineering.pillars.strategist.timeframe_sec = 86400

    fsm = _MockFSM()
    fe = FeatureEngineering(fsm=fsm, config=cfg)
    fe._log_features_to_file = lambda *_a, **_kw: None

    # Deterministic pillars for wiring checks.
    fe.calc_engine.compute_pillars = lambda *args: {
        "pillar_sum": 0.35,
        "pillar_tactician": 0.20,
        "pillar_operator": 0.50,
        "pillar_strategist": 0.10,
        "pillar_contribs": {"operator": 0.20},
    }

    symbol = "BTCUSDT"
    fsm.emit("EVT:BAR_CLOSED", {"bar": _bar(symbol, 14400, 1_700_000_000_000)}, why="test_h4")

    produced = [e for e in fsm.emitted if e[0] in ("EVT:FEATURES_CALCULATED", "CMD:PROCESS_STRATEGY")]
    assert produced == [], "Internal H4 TF must not emit FEATURES/CMD events"


def test_basis_bar_flows_into_quadratic_with_pillar_sum() -> None:
    cfg = get_config().model_copy(deep=True)
    cfg.domains.feature_engineering.enabled_timeframes_sec = [300]
    cfg.domains.feature_engineering.warmup.enforcement_mode = "disabled"
    cfg.domains.feature_engineering.pillars.enabled = True
    cfg.domains.feature_engineering.pillars.tactician.timeframe_sec = 300
    cfg.domains.feature_engineering.pillars.operator.timeframe_sec = 14400
    cfg.domains.feature_engineering.pillars.strategist.timeframe_sec = 86400
    cfg.strategies.aurora.decision.scoring_version = "quadratic"

    fsm = _MockFSM()
    fe = FeatureEngineering(fsm=fsm, config=cfg)
    fe._log_features_to_file = lambda *_a, **_kw: None
    fe.calc_engine.compute_pillars = lambda *args: {
        "pillar_sum": 0.42,
        "pillar_tactician": 0.30,
        "pillar_operator": 0.60,
        "pillar_strategist": 0.10,
        "pillar_contribs": {"tactician": 0.09, "operator": 0.24, "strategist": 0.03},
    }

    handler = AuroraHandler(config=cfg, emit_fn=fsm.emit, strategy_id="aurora")
    handler._basis_required_bars_override = 0
    symbol = "BTCUSDT"
    handler._symbol_states[symbol].last_regime_heartbeat_ms = int(time.time() * 1000)

    captured: dict = {}
    real_compute = QuadraticScoringKernel.compute

    def _spy_compute(**kwargs):
        captured["features"] = dict(kwargs.get("features", {}))
        res = real_compute(**kwargs)
        captured["deferred"] = bool(getattr(res, "deferred", False))
        captured["defer_reason"] = getattr(res, "defer_reason", None)
        return res

    handler.scoring_kernel_cls.compute = _spy_compute
    fsm.listen("CMD:PROCESS_STRATEGY", lambda msg: handler.on_process_strategy(msg.pld))

    fsm.emit("EVT:BAR_CLOSED", {"bar": _bar(symbol, 300, 1_700_000_300_000, close="101.0")}, why="test_m5")

    cmd_events = [e for e in fsm.emitted if e[0] == "CMD:PROCESS_STRATEGY"]
    assert cmd_events, "Basis TF must emit CMD:PROCESS_STRATEGY"
    features = cmd_events[-1][1]["features"]
    assert features["pillar_sum"] == 0.42
    assert "pillar_contribs" in features

    assert "features" in captured, "Quadratic compute was not called"
    assert captured["features"].get("pillar_sum") == 0.42
    assert captured.get("defer_reason") != "PILLAR_SUM_MISSING"

