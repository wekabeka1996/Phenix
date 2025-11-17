import copy

from apps.reference.config_loader import AuroraConfig
from apps.reference.config_models import ConfigV2


def _sample_config_v2() -> ConfigV2:
    return ConfigV2(domains={
        "decision": {
            "thresholds": {
                "signal_threshold": 0.05,
                "neutral_threshold": 0.15,
            }
        }
    })


def test_to_dict_preserves_config_v2_attribute():
    cfg = AuroraConfig()
    cfg.config_v2 = _sample_config_v2()

    snapshot = cfg.to_dict()

    assert hasattr(
        snapshot, "config_v2"), "config_v2 attribute should propagate to dict snapshot"
    assert snapshot.config_v2.domains["decision"]["thresholds"]["signal_threshold"] == 0.05


def test_deepcopy_retains_config_v2_attribute():
    cfg = AuroraConfig()
    cfg.config_v2 = _sample_config_v2()

    snapshot = copy.deepcopy(cfg.to_dict())

    assert hasattr(
        snapshot, "config_v2"), "config_v2 attribute should survive deepcopy"
    assert snapshot.config_v2.domains["decision"]["thresholds"]["neutral_threshold"] == 0.15
