from decimal import Decimal

import pytest

from apps.reference.config_loader import AuroraConfig
from apps.reference.config_models import ConfigV2
from apps.reference.domains.execution_position.brackets_config import (
    DEFAULT_OFFSET_BPS,
    DEFAULT_SL_BPS,
    DEFAULT_TP_BPS,
    clear_brackets_warning_cache,
    resolve_brackets_config,
)


def test_resolver_prefers_canonical_fixed_bps():
    # This test now verifies V2 config behavior
    cfg = AuroraConfig(
        trading={},
        config_v2=ConfigV2(
            domains={
                "execution": {
                    "brackets": {
                        "sl": {"fixed_bps": 80},
                        "tp": {"fixed_bps": 160},
                        "offset_bps": 9,
                    }
                }
            }
        ),
    )

    result = resolve_brackets_config(cfg)

    assert result.sl_bps == Decimal("80")
    assert result.tp_bps == Decimal("160")
    assert result.offset_bps == 9
    assert result.sl_source == "sl.fixed_bps"
    assert result.tp_source == "tp.fixed_bps"


@pytest.mark.parametrize(
    "config",
    [
        {},
        {"trading": {}},
        {"trading": {"execution": {}}},
    ],
)
def test_resolver_defaults_when_config_missing(config):
    result = resolve_brackets_config(config)

    assert result.sl_bps == DEFAULT_SL_BPS
    assert result.tp_bps == DEFAULT_TP_BPS
    assert result.offset_bps == DEFAULT_OFFSET_BPS
    assert result.sl_source == "default"
    assert result.tp_source == "default"


def test_resolver_uses_canonical_v2_block():
    cfg = AuroraConfig(
        trading={},
        config_v2=ConfigV2(
            domains={
                "execution": {
                    "brackets": {
                        "sl": {"fixed_bps": 70},
                        "tp": {"fixed_bps": 140},
                        "offset_bps": 7,
                    }
                }
            }
        ),
    )

    result = resolve_brackets_config(cfg)

    assert result.source == "config_v2"
    assert result.sl_bps == Decimal("70")
    assert result.tp_bps == Decimal("140")
    assert result.offset_bps == 7


def test_resolver_warns_when_only_manage_brackets(caplog):
    clear_brackets_warning_cache()
    caplog.set_level("WARNING")

    cfg = AuroraConfig(
        trading={},
        config_v2=ConfigV2(
            domains={
                "execution": {
                    "manage": {
                        "brackets": {
                            "sl": {"fixed_bps": 65},
                            "tp": {"fixed_bps": 130},
                            "offset_bps": 8,
                        }
                    }
                }
            }
        ),
    )

    result = resolve_brackets_config(cfg)

    assert result.source == "config_v2"
    assert "execution.manage.brackets" in caplog.text
