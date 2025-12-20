import pytest


def test_task25_execpos_fsm_rejects_dict_config():
    from apps.reference.domains.execution_position.exposure_guard import ExposureGuard

    with pytest.raises(TypeError):
        ExposureGuard(fsm_core=object(), config={})


def test_task25_risk_management_rejects_dict_config():
    from apps.reference.domains.risk_management.risk_management import RiskManagement

    with pytest.raises(TypeError):
        RiskManagement(fsm=object(), config={})
