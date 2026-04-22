import decimal

import pytest

from apps.reference.domains.decision_making.intent_builder_validators import (
    normalize_trade_inputs,
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
