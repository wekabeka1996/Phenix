from typing import Any, List, Tuple
from vfoundation.apps.reference.telemetry.metrics import AURORA_HYBRID_COHERENT, AURORA_HYBRID_INCOHERENT_REASONS_TOTAL
import logging

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


def _nested_get(d: dict, path: List[str], default: Any = None) -> Any:
    cur = d
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur


def check_hybrid_coherence(cfg) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    mode_label = 'hybrid_testnet'

    # market_data.trading_mode може лежати в різних місцях
    md_mode = _nested_get(cfg, ['trading', 'domain_configuration', 'market_data', 'trading_mode'],
                          _nested_get(cfg, ['domain_configuration', 'market_data', 'trading_mode'],
                                      _nested_get(cfg, ['market_data', 'trading_mode'], None)))
    if md_mode != 'live':
        reasons.append(
            'Market data trading_mode is \'testnet\', expected \'live\'.')

    # risk_portfolio_source: приймаємо як _resolved або як явне в trading.yaml
    rps = _nested_get(cfg, ['_resolved', 'risk_portfolio_source'],
                      _nested_get(cfg, ['trading', 'domain_configuration', 'risk_management', 'data_sources', 'portfolio_state'],
                                  _nested_get(cfg, ['risk_management', 'data_sources', 'portfolio_state'], None)))
    # follow_execution у гібриді означає testnet
    if rps == 'follow_execution':
        rps = 'testnet'
    if rps != 'testnet':
        reasons.append(
            'Risk portfolio source is \'live\', expected \'testnet\'.')

    ok = (len(reasons) == 0)
    AURORA_HYBRID_COHERENT.labels(mode=mode_label).set(1.0 if ok else 0.0)
    if not ok:
        for r in reasons:
            AURORA_HYBRID_INCOHERENT_REASONS_TOTAL.labels(
                reason=_slug(r)).inc()
        log.warning(
            'HYBRID_INCOHERENT: Hybrid mode pre-flight check failed. Reasons: %s', '; '.join(reasons))
    else:
        log.info(' Hybrid mode pre-flight check passed.')

    # Update state
    _HYBRID_COHERENCE_STATE['last_result'] = {'ok': ok, 'reasons': reasons}
    _HYBRID_COHERENCE_STATE['risk_portfolio_source'] = rps
    _HYBRID_COHERENCE_STATE['execution_mode'] = 'testnet'

    return ok, reasons
