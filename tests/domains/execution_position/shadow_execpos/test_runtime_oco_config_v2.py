from apps.reference.domains.execution_position.shadow_execpos.runtime import ExecPosRuntimeV2
from apps.reference.domains.execution_position.shadow_execpos.bracket_service import BracketRulesConfig
from apps.reference.domains.execution_position.config import (
    ExecutionPositionConfig,
    AggregatedOcoConfig,
    TrailingConfig,
    CloseConfig,
)


def test_bracket_cfg_uses_typed_execution_position_config():
    """
    Test that typed ExecutionPositionConfig is used when available.

    NOTE: sl_roi_pct and tp_roi_pct are set to 0 to disable ROI-based calculation
    and test the direct sl_pct/tp_rr values.
    """
    ep_cfg = ExecutionPositionConfig(
        aggregated_oco=AggregatedOcoConfig(
            enabled=True,
            sl_pct=0.05,
            tp_rr=3.0,
            sl_roi_pct=0.0,  # Disable ROI calculation to test direct sl_pct
            tp_roi_pct=0.0,  # Disable ROI calculation to test direct tp_rr
            allow_unprotected_position=True,
            ttl_protect_new_bracket_ms=1234,
            max_tp_legs=2,
            max_sl_legs=2,
            recalc_on_partial_close=True,
            recalc_on_scale_in=False,
        ),
        trailing=TrailingConfig(),
        close=CloseConfig(),
    )

    rt = ExecPosRuntimeV2(config={}, adapter=None,
                          price_service=None, ep_config=ep_cfg)

    cfg: BracketRulesConfig = rt._get_bracket_cfg()
    assert cfg.enabled is True
    assert cfg.sl_pct == 0.05
    assert cfg.tp_rr == 3.0
    assert cfg.allow_unprotected_position is True
    assert cfg.ttl_protect_new_bracket_ms == 1234
    assert cfg.max_tp_legs == 2
    assert cfg.max_sl_legs == 2
    assert cfg.recalc_on_partial_close is True
    assert cfg.recalc_on_scale_in is False


def test_bracket_cfg_legacy_fallback_matches_dict_values():
    legacy_cfg = {
        "execution_position": {
            "aggregated_oco": {
                "enabled": True,
                "sl_pct": 0.02,
                "tp_rr": 2.5,
                "allow_unprotected_position": False,
                "ttl_protect_new_bracket_ms": 5000,
                "max_tp_legs": 1,
                "max_sl_legs": 1,
                "recalc_on_partial_close": True,
                "recalc_on_scale_in": True,
            }
        }
    }

    rt = ExecPosRuntimeV2(config=legacy_cfg, adapter=None,
                          price_service=None, ep_config=None)
    cfg = rt._get_bracket_cfg()

    assert cfg.enabled is True
    assert cfg.sl_pct == 0.02
    assert cfg.tp_rr == 2.5
    assert cfg.allow_unprotected_position is False
    assert cfg.ttl_protect_new_bracket_ms == 5000
    assert cfg.max_tp_legs == 1
    assert cfg.max_sl_legs == 1
    assert cfg.recalc_on_partial_close is True
    assert cfg.recalc_on_scale_in is True
