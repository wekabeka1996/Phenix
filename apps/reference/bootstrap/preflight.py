from typing import Any, List, Tuple
import logging

from apps.reference.utils import compute_effective_trading_modes

log = logging.getLogger(__name__)


class HybridIncoherenceError(Exception):
    """Raised when hybrid mode configuration is incoherent."""
    pass


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


def _nested_get(d: dict, path: List[str], default: Any = None) -> Any:
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def check_hybrid_coherence(cfg) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    mode_label = "hybrid_testnet"

    # 1) data must be live if будь-який з data-доменів live
    cfg_for_modes = cfg
    # AuroraConfig.to_dict() returns AuroraConfigDict with config_v2 attribute that
    # still points to repo-level modes. During isolated tests we only want the
    # serialized payload, so strip the auxiliary attribute to avoid cross-contamination.
    if hasattr(cfg_for_modes, "config_v2"):
        cfg_for_modes = dict(cfg_for_modes)
    modes = compute_effective_trading_modes(cfg_for_modes)
    any_live = any(
        modes.domain_modes.get(domain) == "live"
        for domain in ("market_data", "feature_engineering", "decision_making")
    )
    if not any_live:
        reasons.append(
            "Market data trading_mode is 'testnet', expected 'live'.")

    # 2) risk portfolio source → testnet (follow_execution у гібриді = testnet)
    rps = _nested_get(cfg, ["_resolved", "risk_portfolio_source"],
                      _nested_get(cfg, ["trading", "domain_configuration", "risk_management", "data_sources", "portfolio_state"],
                                  _nested_get(cfg, ["trading", "risk_management", "data_sources", "portfolio_state"],
                                              _nested_get(cfg, ["risk_management", "data_sources", "portfolio_state"]))))
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
        error_msg = f"HYBRID_INCOHERENT: Hybrid mode pre-flight check failed. Reasons: {'; '.join(reasons)}"
        log.error(error_msg)
        raise HybridIncoherenceError(error_msg)
    else:
        log.info("✅ Hybrid mode pre-flight check passed.")
    return ok, reasons
