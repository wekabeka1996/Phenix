import pytest
from prometheus_client import REGISTRY

# We use the existing metrics from the modules instead of creating duplicates


@pytest.fixture
def metrics():
    # Import the existing metrics instead of creating new ones
    from vfoundation.apps.reference.telemetry.metrics import AURORA_HYBRID_COHERENT, AURORA_HYBRID_INCOHERENT_REASONS_TOTAL
    return AURORA_HYBRID_COHERENT, AURORA_HYBRID_INCOHERENT_REASONS_TOTAL


def test_hybrid_incoherent_metrics_export(metrics):
    from apps.reference.bootstrap.preflight import check_hybrid_coherence, get_hybrid_coherence_state
    from vfoundation.apps.reference.telemetry.metrics import update_hybrid_coherence_metrics

    # Simulate an incoherent configuration
    mock_config = {
        "trading": {
            "domain_configuration": {
                "market_data": {"trading_mode": "testnet"},  # Incoherent
                "execution_position": {"trading_mode": "testnet"},
            }
        },
        "_resolved": {"risk_portfolio_source": "live"},  # Incoherent
    }

    # Perform the check
    check_hybrid_coherence(mock_config)

    # Update metrics based on the state
    from apps.reference.bootstrap.preflight import get_hybrid_coherence_state
    state = get_hybrid_coherence_state()
    from vfoundation.apps.reference.telemetry.metrics import update_hybrid_coherence_metrics
    update_hybrid_coherence_metrics(state)

    # Assertions for incoherent state
    assert REGISTRY.get_sample_value('aurora_hybrid_coherent', {
                                     'mode': 'hybrid_testnet'}) == 0.0

    state = get_hybrid_coherence_state()
    reasons = state['last_result']['reasons']

    for reason in reasons:
        reason_slug = reason.lower().replace(' ', '_').replace('.', '').replace("'", '')
        assert REGISTRY.get_sample_value('aurora_hybrid_incoherent_reasons_total', {
                                         'reason': reason_slug}) > 0


def test_hybrid_coherent_metrics_export(metrics):
    from apps.reference.bootstrap.preflight import check_hybrid_coherence, get_hybrid_coherence_state
    from vfoundation.apps.reference.telemetry.metrics import update_hybrid_coherence_metrics

    # Simulate a coherent configuration
    mock_config = {
        "trading": {
            "domain_configuration": {
                "market_data": {"trading_mode": "live"},
                "execution_position": {"trading_mode": "testnet"},
            }
        },
        "_resolved": {"risk_portfolio_source": "testnet"},
    }

    # Perform the check
    check_hybrid_coherence(mock_config)

    # Update metrics based on the state
    from apps.reference.bootstrap.preflight import get_hybrid_coherence_state
    state = get_hybrid_coherence_state()
    from vfoundation.apps.reference.telemetry.metrics import update_hybrid_coherence_metrics
    update_hybrid_coherence_metrics(state)

    # Assertions for coherent state
    assert REGISTRY.get_sample_value('aurora_hybrid_coherent', {
                                     'mode': 'hybrid_testnet'}) == 1.0

    state = get_hybrid_coherence_state()
    reasons = state['last_result']['reasons']
    assert len(reasons) == 0
