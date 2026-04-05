from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from apps.reference.config_contract import ConfigContractError
from apps.reference.config_loader import AuroraConfig
from apps.reference.domains.account_balance.account_connector import AccountConnector
from apps.reference.domains.data_recorder.recorder import CsvRecorder
from apps.reference.domains.decision_making.decision_making import DecisionMaking
from apps.reference.domains.execution_position.fsm import ExecPosFSM
from apps.reference.domains.feature_engineering.feature_engineering import FeatureEngineering
from apps.reference.domains.market_data.bar_aggregator import BarAggregator
from apps.reference.domains.market_data.market_data_connector import MarketDataConnector
from apps.reference.domains.market_data.proxy import MarketDataProxy
from apps.reference.domains.objective_engine.runtime import ObjectiveEngineRuntime
from apps.reference.domains.position_tracking.position_tracking import PositionTracking
from apps.reference.domains.regime_detector.regime_detector import RegimeDetector
from apps.reference.domains.risk_management.risk_management import RiskManagement
from apps.reference.domains.system_stress.system_stress_overlay import SystemStressOverlay
from apps.reference.domains.ta_features import TAFeaturesEngine
from vfoundation.core import FSMCore


@dataclass
class LiveDomainBundle:
    account_balance: AccountConnector
    market_data: Any
    feature_engineering: FeatureEngineering
    risk_management: RiskManagement
    position_tracking: PositionTracking
    execution_position: ExecPosFSM
    decision_making: DecisionMaking
    regime_detector: RegimeDetector
    csv_recorder: CsvRecorder
    bar_aggregator: Optional[BarAggregator]
    system_stress_overlay: Optional[SystemStressOverlay] = None
    objective_engine_runtime: Optional[ObjectiveEngineRuntime] = None
    ta_features_engine: Optional[TAFeaturesEngine] = None


_DEBUG_EVENTS = [
    "EVT:MARKET_TICK_RECEIVED",
    "EVT:FEATURES_CALCULATED",
    "EVT:RISK_ASSESSMENT_COMPLETED",
    "EVT:PORTFOLIO_STATE_UPDATED",
    "EVT:TRADE_INTENT_PROPOSED",
]


def build_live_domains(
    *,
    config: AuroraConfig,
    fsm: FSMCore,
    logger: logging.Logger,
    debug_event_listener: Optional[Callable[[Any], None]] = None,
) -> LiveDomainBundle:
    """Compose live domains and return a typed bundle for runtime wiring."""
    if bool(getattr(config.system, "debug_event_listener_enabled", False)):
        if debug_event_listener is not None:
            for event_name in _DEBUG_EVENTS:
                fsm.listen(event_name, debug_event_listener)
            logger.info(
                "Debug event listener ENABLED via config.system.debug_event_listener_enabled")
    else:
        logger.debug("Debug event listener DISABLED in config")

    account_balance = AccountConnector(fsm=fsm, config=config)

    if config.trading.market_data is None:
        raise ConfigContractError(
            path="trading.market_data",
            why="Missing required config (market_data).",
        )
    use_multiprocessing = bool(config.trading.market_data.use_multiprocessing)

    if use_multiprocessing:
        logger.info("Using MarketDataProxy (multiprocessing mode)")
        market_data = MarketDataProxy(fsm=fsm, config=config)
    else:
        logger.info("Using MarketDataConnector (legacy single-process mode)")
        market_data = MarketDataConnector(fsm=fsm, config=config)

    ta_features_engine: Optional[TAFeaturesEngine] = None
    ta_features_cfg = getattr(config.domains, "ta_features", None)
    if ta_features_cfg is None:
        logger.info(
            "TAFeaturesEngine disabled",
            extra={
                "why": "ta_features_absent",
                "reason": "config.domains.ta_features not defined",
            },
        )
    elif not ta_features_cfg.enabled:
        logger.info(
            "TAFeaturesEngine disabled",
            extra={
                "why": "ta_features_disabled",
                "reason": "config.domains.ta_features.enabled=false",
            },
        )
    else:
        # Register TA first so same-bar TA cache exists before FE can trigger
        # downstream decision scoring on CMD:PROCESS_STRATEGY.
        ta_features_engine = TAFeaturesEngine(fsm=fsm, config=ta_features_cfg)

    feature_engineering = FeatureEngineering(fsm=fsm, config=config)

    bar_aggregator: Optional[BarAggregator] = None
    bar_config = getattr(config.trading.market_data, "bar_aggregator", None)
    if bar_config is None:
        logger.info(
            "BarAggregator disabled",
            extra={"why": "bar_agg_disabled_missing_config",
                   "reason": "config.trading.market_data.bar_aggregator not defined"},
        )
    elif not bar_config.enabled:
        logger.info(
            "BarAggregator disabled",
            extra={"why": "bar_agg_disabled_config",
                   "reason": "bar_aggregator.enabled=false"},
        )
    else:
        timeframes = bar_config.timeframes_sec
        if not timeframes:
            logger.warning(
                "BarAggregator enabled but timeframes_sec empty, using defaults [60, 300]",
                extra={"why": "bar_agg_timeframes_default"},
            )
            timeframes = [60, 300]
        bar_aggregator = BarAggregator(
            timeframes_sec=timeframes, emit_fn=fsm.emit)
        fsm.listen("EVT:MARKET_TICK_RECEIVED", bar_aggregator.on_market_tick)
        logger.info(
            "BarAggregator enabled",
            extra={"why": "bar_agg_enabled", "timeframes_sec": timeframes},
        )

    risk_management = RiskManagement(fsm=fsm, config=config)
    execution_position = ExecPosFSM(config=config, fsm=fsm)
    position_tracking = PositionTracking(fsm=fsm, config=config)
    decision_making = DecisionMaking(fsm=fsm, config=config)
    regime_detector = RegimeDetector(config=config, fsm=fsm)
    csv_recorder = CsvRecorder(fsm=fsm, config=config)

    # Phase 0.5: System Stress Overlay (no-op when system_stress.enabled=false)
    system_stress_overlay = SystemStressOverlay(config=config, fsm=fsm)
    objective_engine_runtime = ObjectiveEngineRuntime(config=config, fsm=fsm)

    return LiveDomainBundle(
        account_balance=account_balance,
        market_data=market_data,
        feature_engineering=feature_engineering,
        risk_management=risk_management,
        position_tracking=position_tracking,
        execution_position=execution_position,
        decision_making=decision_making,
        regime_detector=regime_detector,
        csv_recorder=csv_recorder,
        bar_aggregator=bar_aggregator,
        system_stress_overlay=system_stress_overlay,
        objective_engine_runtime=objective_engine_runtime,
        ta_features_engine=ta_features_engine,
    )
