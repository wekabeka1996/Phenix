from __future__ import annotations

from typing import Any


TPSL_OWNER_REGIME_TPSL = "regime_tpsl"
TPSL_OWNER_ENTRY_PLAN = "entry_plan"

TPSL_OWNER_LOSS_DISABLED_OR_MISSING = "REGIME_TPSL_DISABLED_OR_MISSING"
TPSL_OWNER_LOSS_CONFIG_ERROR = "REGIME_TPSL_CONFIG_ERROR"
TPSL_OWNER_LOSS_ATR_UNAVAILABLE = "REGIME_TPSL_ATR_UNAVAILABLE"
TPSL_OWNER_LOSS_INVALID_INPUT = "REGIME_TPSL_INVALID_INPUT"
TPSL_OWNER_LOSS_UNSUPPORTED_MODE = "REGIME_TPSL_UNSUPPORTED_MODE"
TPSL_OWNER_LOSS_SL_WRONG_SIDE = "TPSL_GUARDRAIL_SL_WRONG_SIDE"
TPSL_OWNER_LOSS_TP_WRONG_SIDE = "TPSL_GUARDRAIL_TP_WRONG_SIDE"
TPSL_OWNER_LOSS_SL_MIN_DIST_BPS = "TPSL_GUARDRAIL_SL_MIN_DIST_BPS"
TPSL_OWNER_LOSS_TP_MIN_DIST_BPS = "TPSL_GUARDRAIL_TP_MIN_DIST_BPS"


def build_tpsl_owner_ctx(
    *,
    intended_owner: str | None,
    final_owner: str | None,
    owner_loss_reason: str | None,
) -> dict[str, str | None] | None:
    if intended_owner is None:
        return None
    return {
        "intended_owner": intended_owner,
        "final_owner": final_owner,
        "owner_loss_reason": owner_loss_reason,
    }


def clone_tpsl_owner_ctx(raw: Any) -> dict[str, str | None] | None:
    if not isinstance(raw, dict):
        return None

    intended_owner = raw.get("intended_owner")
    if intended_owner in (None, ""):
        return None

    final_owner = raw.get("final_owner")
    if final_owner == "":
        final_owner = None

    owner_loss_reason = raw.get("owner_loss_reason")
    if owner_loss_reason in ("", "NONE"):
        owner_loss_reason = None

    return build_tpsl_owner_ctx(
        intended_owner=str(intended_owner),
        final_owner=str(final_owner) if final_owner is not None else None,
        owner_loss_reason=(
            str(owner_loss_reason) if owner_loss_reason is not None else None
        ),
    )


def resolve_gateway_tpsl_owner_ctx(
    signal_tpsl_owner_ctx: Any,
    entry_plan_trace: Any,
) -> dict[str, str | None] | None:
    base = clone_tpsl_owner_ctx(signal_tpsl_owner_ctx)
    if base is None:
        return None

    if base.get("final_owner") is None and isinstance(entry_plan_trace, dict) and entry_plan_trace:
        base["final_owner"] = TPSL_OWNER_ENTRY_PLAN

    return base
