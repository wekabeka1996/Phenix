"""Integration tests for config loading without errors."""


def test_risk_management_loads_config():
    """Test that RiskManagement initializes with real config."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path.cwd()))

    from apps.reference.config_loader import get_config
    from apps.reference.domains.risk_management.risk_management import RiskManagement
    from vfoundation.core import FSMCore

    config = get_config()
    fsm = FSMCore()
    risk_mgmt = RiskManagement(fsm, config.to_dict())

    assert risk_mgmt is not None


def test_decision_making_loads_config():
    """Test that DecisionMaking initializes with real config."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path.cwd()))

    from apps.reference.config_loader import get_config
    from apps.reference.domains.decision_making.decision_making import DecisionMaking
    from vfoundation.core import FSMCore

    config = get_config()
    fsm = FSMCore()
    decision_making = DecisionMaking(fsm, config.to_dict())

    assert decision_making is not None


def test_all_domains_initialize():
    """Test that all core domains initialize without errors."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path.cwd()))

    from apps.reference.config_loader import get_config
    from apps.reference.domains.risk_management.risk_management import RiskManagement
    from apps.reference.domains.decision_making.decision_making import DecisionMaking
    from apps.reference.domains.feature_engineering.feature_engineering import (
        FeatureEngineering,
    )
    from vfoundation.core import FSMCore

    config = get_config()
    fsm = FSMCore()
    config_dict = config.to_dict()

    fe = FeatureEngineering(fsm, config_dict)
    rm = RiskManagement(fsm, config_dict)
    dm = DecisionMaking(fsm, config_dict)

    assert fe is not None
    assert rm is not None
    assert dm is not None
