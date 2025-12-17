from typing import Any, List, Tuple
import logging

from apps.reference.config_contract import ConfigContractError
from apps.reference.config_models import AuroraConfig

log = logging.getLogger(__name__)


_HYBRID_COHERENCE_STATE = {
    'last_check_ts': None,
    'last_result': {'ok': False, 'reasons': []},
    'risk_portfolio_source': None,
    'execution_mode': None,
}


def get_hybrid_coherence_state() -> dict:
    return _HYBRID_COHERENCE_STATE


def _slug(s: str) -> str:
    return ''.join(ch if ch.isalnum() or ch in '-_' else '_' for ch in s.lower())


def check_hybrid_coherence(cfg: AuroraConfig) -> Tuple[bool, List[str]]:
    if isinstance(cfg, dict):
        raise TypeError("check_hybrid_coherence requires AuroraConfig, got dict")
    reasons: List[str] = []
    mode_label = "hybrid_testnet"

    # 1) data must be live if any data-domain is live
    dc = cfg.trading.domain_configuration
    md_mode_candidates = [
        dc.market_data.trading_mode,
        dc.feature_engineering.trading_mode,
        dc.decision_making.trading_mode,
    ]
    any_live = any(m == "live" for m in md_mode_candidates)
    if not any_live:
        reasons.append(
            "Market data trading_mode is 'testnet', expected 'live'.")

    # 2) risk portfolio source → testnet (follow_execution in hybrid = testnet)
    try:
        rps = cfg.trading.risk_management.data_sources.portfolio_state
    except AttributeError as e:
        raise ConfigContractError(
            path="trading.risk_management.data_sources.portfolio_state",
            why=f"Missing required risk portfolio source config: {e}",
        )
    if rps == "follow_execution":
        rps = "testnet"
    if rps != "testnet":
        reasons.append("Risk portfolio source is 'live', expected 'testnet'.")

    ok = (len(reasons) == 0)
    # Optional: emit metrics if available
    try:
        from apps.reference.telemetry.metrics import AURORA_HYBRID_COHERENT, AURORA_HYBRID_INCOHERENT_REASONS_TOTAL
        AURORA_HYBRID_COHERENT.labels(mode=mode_label).set(1.0 if ok else 0.0)
        if not ok:
            for r in reasons:
                AURORA_HYBRID_INCOHERENT_REASONS_TOTAL.labels(
                    reason=_slug(r)).inc()
    except ImportError:
        pass  # Metrics unavailable, continue

    if not ok:
        log.warning(
            "HYBRID_INCOHERENT: Hybrid mode pre-flight check failed. Reasons: %s", "; ".join(reasons))
    else:
        log.info("✅ Hybrid mode pre-flight check passed.")
    return ok, reasons
