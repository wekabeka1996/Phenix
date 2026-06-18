import decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.reference.config_loader import ConfigLoader
from apps.reference.domains.decision_making.intent.builder_validators import (
    normalize_trade_inputs,
    resolve_kelly_metadata,
    resolve_risk_budgets,
    resolve_tca_preferences,
    sanitize_tpsl_payload,
)


def _get_strict(obj, key: str, err_msg: str):
    if isinstance(obj, dict):
        value = obj[key] if key in obj else None
    else:
        value = getattr(obj, key, None)
    if value is None:
        raise ValueError(err_msg)
    return value


def _safe_decimal(value, default=None):
    if value in (None, "", "None"):
        return default
    try:
        return decimal.Decimal(str(value))
    except Exception:
        return default


def _make_config(
    *,
    base_probability: str = "0.5",
    payoff_ratio_r: str = "1.5",
    kelly_cap: str = "0.25",
    p_min: str = "0.45",
    p_max: str = "0.65",
    kelly_alpha: str = "0.8",
    uplift_factor: str = "0.2",
    legacy_fraction: str | None = None,
    overrides: dict | None = None,
):
    kelly_kwargs = {
        "base_probability": base_probability,
        "kelly_cap": kelly_cap,
        "kelly_alpha": kelly_alpha,
        "payoff_ratio_r": payoff_ratio_r,
        "p_min": p_min,
        "p_max": p_max,
        "uplift_factor": uplift_factor,
        "overrides": overrides or {},
    }
    if legacy_fraction is not None:
        kelly_kwargs["fraction"] = legacy_fraction
    strategy_cfg = SimpleNamespace(
        decision=SimpleNamespace(kelly=SimpleNamespace(**kelly_kwargs))
    )
    return SimpleNamespace(strategies=SimpleNamespace(aurora=strategy_cfg))


def test_normalize_trade_inputs_uses_decimal_string_coercion() -> None:
    normalized = normalize_trade_inputs(qty=0.1, price="50000.125")

    assert normalized.qty == decimal.Decimal("0.1")
    assert normalized.price == decimal.Decimal("50000.125")


def test_resolve_tca_preferences_preserves_override_and_stringifies_maker_pref() -> None:
    resolved = resolve_tca_preferences(
        tca_prefs={
            "max_slippage_bps": 10,
            "max_latency_ms": 100,
            "maker_preference": False,
        },
        max_slippage_bps=25,
        max_latency_ms=3000,
        get_strict=_get_strict,
    )

    assert resolved.max_slippage_bps == "25"
    assert resolved.max_latency_ms == 3000
    assert resolved.maker_preference == "False"


def test_resolve_risk_budgets_reads_required_fields_as_strings() -> None:
    resolved = resolve_risk_budgets(
        risk_budgets={
            "trade_cvar95_max_bps": 100,
            "session_cvar95_max_bps": 200,
        },
        get_strict=_get_strict,
    )

    assert resolved.trade_cvar95_max_bps == "100"
    assert resolved.session_cvar95_max_bps == "200"


def test_resolve_risk_budgets_raises_for_missing_required_field() -> None:
    with pytest.raises(ValueError, match="Missing session_cvar95_max_bps"):
        resolve_risk_budgets(
            risk_budgets={"trade_cvar95_max_bps": 100},
            get_strict=_get_strict,
        )


def test_sanitize_tpsl_payload_canonicalizes_values_and_clones_owner_ctx() -> None:
    owner_ctx = {
        "intended_owner": "regime_tpsl",
        "final_owner": "entry_plan",
        "owner_loss_reason": "TPSL_GUARDRAIL_TP_MIN_DIST_BPS",
    }

    sanitized = sanitize_tpsl_payload(
        stop_price="49000.50",
        target_price=decimal.Decimal("51000.75"),
        safe_decimal_fn=_safe_decimal,
        tpsl_owner_ctx=owner_ctx,
    )

    assert sanitized.stop_price == "49000.50"
    assert sanitized.target_price == "51000.75"
    assert sanitized.owner_ctx == owner_ctx
    assert sanitized.owner_ctx is not owner_ctx


def test_sanitize_tpsl_payload_drops_unparseable_values() -> None:
    sanitized = sanitize_tpsl_payload(
        stop_price="not-a-number",
        target_price="",
        safe_decimal_fn=_safe_decimal,
        tpsl_owner_ctx=None,
    )

    assert sanitized.stop_price is None
    assert sanitized.target_price is None
    assert sanitized.owner_ctx is None


def test_resolve_kelly_metadata_uses_ssot_fields_and_ignores_legacy_fraction() -> None:
    resolved = resolve_kelly_metadata(
        config=_make_config(legacy_fraction="0.99"),
        strategy_id="aurora",
        symbol="BTCUSDT",
        regime="TREND_UP",
        side="BUY",
    )

    expected_fraction = str(
        decimal.Decimal("0.5")
        - ((decimal.Decimal("1") - decimal.Decimal("0.5")) / decimal.Decimal("1.5"))
    )
    assert resolved.p == "0.5"
    assert resolved.payoff_ratio_r == "1.5"
    assert resolved.kelly_fraction == expected_fraction
    assert resolved.provenance["kelly_fraction"][
        "formula"] == "p - (1 - p) / payoff_ratio_r"
    assert resolved.provenance["cohort"]["override_applied"] is False
    assert resolved.provenance["unapplied_config_fields"]["kelly_alpha"]["reason"] == "deprecated_without_calibrated_score_probability_model"


def test_resolve_kelly_metadata_clamps_probability_to_p_bounds() -> None:
    resolved = resolve_kelly_metadata(
        config=_make_config(base_probability="0.9"),
        strategy_id="aurora",
        symbol="BTCUSDT",
        regime="TREND_UP",
        side="BUY",
    )

    assert resolved.p == "0.65"
    assert resolved.kelly_fraction == "0.25"


def test_resolve_kelly_metadata_does_not_require_deprecated_score_fields() -> None:
    config = _make_config()
    kelly = config.strategies.aurora.decision.kelly
    kelly.kelly_alpha = None
    kelly.uplift_factor = None

    resolved = resolve_kelly_metadata(
        config=config,
        strategy_id="aurora",
        symbol="BTCUSDT",
        regime="TREND_UP",
        side="BUY",
    )

    assert resolved.provenance["unapplied_config_fields"]["kelly_alpha"]["value"] is None
    assert resolved.provenance["unapplied_config_fields"]["uplift_factor"]["value"] is None


def test_resolve_kelly_metadata_raises_for_missing_kelly_config() -> None:
    config = SimpleNamespace(
        strategies=SimpleNamespace(
            aurora=SimpleNamespace(decision=SimpleNamespace()))
    )

    with pytest.raises(ValueError, match="Missing decision.kelly config"):
        resolve_kelly_metadata(
            config=config,
            strategy_id="aurora",
            symbol="BTCUSDT",
            regime="TREND_UP",
            side="BUY",
        )


def test_resolve_kelly_metadata_uses_exact_symbol_regime_side_override() -> None:
    resolved = resolve_kelly_metadata(
        config=_make_config(overrides={
            "ETHUSDT": {
                "MEAN_REVERSION": {
                    "BUY": SimpleNamespace(
                        base_probability="0.58",
                        payoff_ratio_r="1.8",
                        kelly_cap="0.02",
                        p_min="0.50",
                        p_max="0.62",
                    )
                }
            }
        }),
        strategy_id="aurora",
        symbol="ETHUSDT",
        regime="MEAN_REVERSION",
        side="BUY",
    )

    assert resolved.p == "0.58"
    assert resolved.payoff_ratio_r == "1.8"
    assert resolved.kelly_fraction == "0.02"
    assert resolved.provenance["cohort"]["override_applied"] is True
    assert resolved.provenance["source_path"].endswith(
        "overrides.ETHUSDT.MEAN_REVERSION.BUY")


def test_resolve_kelly_metadata_does_not_cross_apply_other_side_override() -> None:
    resolved = resolve_kelly_metadata(
        config=_make_config(overrides={
            "ETHUSDT": {
                "MEAN_REVERSION": {
                    "BUY": SimpleNamespace(
                        base_probability="0.58",
                        payoff_ratio_r="1.8",
                        kelly_cap="0.02",
                        p_min=None,
                        p_max=None,
                    )
                }
            }
        }),
        strategy_id="aurora",
        symbol="ETHUSDT",
        regime="MEAN_REVERSION",
        side="SELL",
    )

    assert resolved.p == "0.5"
    assert resolved.provenance["cohort"]["override_applied"] is False


def test_resolve_kelly_metadata_reports_base_sources_for_partial_override() -> None:
    resolved = resolve_kelly_metadata(
        config=_make_config(overrides={
            "ETHUSDT": {
                "MEAN_REVERSION": {
                    "BUY": SimpleNamespace(
                        base_probability="0.58",
                        payoff_ratio_r=None,
                        kelly_cap="0.02",
                        p_min=None,
                        p_max=None,
                    )
                }
            }
        }),
        strategy_id="aurora",
        symbol="ETHUSDT",
        regime="MEAN_REVERSION",
        side="BUY",
    )

    base_path = "config.strategies.aurora.decision.kelly"
    override_path = f"{base_path}.overrides.ETHUSDT.MEAN_REVERSION.BUY"
    assert resolved.provenance["p"]["source"] == f"{override_path}.base_probability"
    assert resolved.provenance["p"]["p_min_source"] == f"{base_path}.p_min"
    assert resolved.provenance["p"]["p_max_source"] == f"{base_path}.p_max"
    assert resolved.provenance["payoff_ratio_r"]["source"] == f"{base_path}.payoff_ratio_r"
    assert resolved.provenance["kelly_fraction"]["kelly_cap_source"] == f"{override_path}.kelly_cap"


def test_loaded_real_aurora_config_has_no_kelly_fraction_field() -> None:
    config_dir = Path(__file__).resolve().parents[3] / "config" / "aurora"
    cfg = ConfigLoader(config_dir=config_dir).load_config()

    kelly_cfg = cfg.strategies.aurora.decision.kelly
    assert not hasattr(kelly_cfg, "fraction")
    assert "fraction" not in getattr(kelly_cfg.__class__, "model_fields", {})
    assert hasattr(kelly_cfg, "base_probability")
    assert hasattr(kelly_cfg, "payoff_ratio_r")
