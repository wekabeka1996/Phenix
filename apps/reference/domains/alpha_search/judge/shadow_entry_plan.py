"""LLM Judge J6-S3 shadow LIMIT plan derivation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from apps.reference.domains.alpha_search.judge.config_models import ShadowPlanConfig
from apps.reference.domains.alpha_search.judge.contracts import (
    JudgeVerdict,
    ShadowEntryPlan,
)
from apps.reference.domains.alpha_search.judge.identity import utc_day_from_ts_ms

LOG = logging.getLogger(__name__)

_SUPPRESSED_ENTRY_VERDICTS = {"NO_ENTRY", "SUPPRESS", "UNKNOWN"}
_ENTRY_SIDE_BY_VERDICT = {
    "OPEN_LONG": "BUY",
    "OPEN_SHORT": "SELL",
}


def _valid_price_ref(price_ref: Optional[float]) -> Optional[float]:
    try:
        normalized = float(price_ref)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0.0 else None


def _suppression_reason(verdict: JudgeVerdict) -> Optional[str]:
    if verdict.entry_verdict == "SUPPRESS":
        return verdict.suppression_reason or "entry_verdict:suppress"
    if verdict.entry_verdict == "NO_ENTRY":
        return "entry_verdict:no_entry"
    if verdict.entry_verdict == "UNKNOWN":
        return "entry_verdict:unknown"
    return None


def _derive_limit_price(
    *,
    entry_side: str,
    price_ref: float,
    limit_offset_bps: int,
) -> float:
    offset_multiplier = limit_offset_bps / 10_000.0
    if entry_side == "BUY":
        return price_ref * (1.0 - offset_multiplier)
    return price_ref * (1.0 + offset_multiplier)


def _derive_tp_sl_prices(
    *,
    entry_side: str,
    limit_price: float,
    tp_offset_pct: float,
    sl_offset_pct: float,
) -> tuple[float, float]:
    if entry_side == "BUY":
        tp_price = limit_price * (1.0 + tp_offset_pct)
        sl_price = limit_price * (1.0 - sl_offset_pct)
    else:
        tp_price = limit_price * (1.0 - tp_offset_pct)
        sl_price = limit_price * (1.0 + sl_offset_pct)
    return tp_price, sl_price


def derive_shadow_entry_plans(
    verdict: JudgeVerdict,
    *,
    price_ref: Optional[float],
    shadow_plan_config: ShadowPlanConfig,
) -> list[ShadowEntryPlan]:
    """Derive shadow LIMIT plan telemetry from one entry verdict."""
    if verdict.verdict_scope != "ENTRY":
        raise ValueError(
            "derive_shadow_entry_plans requires ENTRY verdict_scope")
    if verdict.entry_verdict is None:
        raise ValueError("derive_shadow_entry_plans requires entry_verdict")
    if not shadow_plan_config.enabled:
        return []

    normalized_price_ref = _valid_price_ref(price_ref)
    is_suppressed = verdict.entry_verdict in _SUPPRESSED_ENTRY_VERDICTS
    entry_side = _ENTRY_SIDE_BY_VERDICT.get(verdict.entry_verdict)
    base_suppression_reason = _suppression_reason(verdict)

    plans: list[ShadowEntryPlan] = []
    for tier in shadow_plan_config.confidence_ladder:
        threshold_met = verdict.confidence >= tier.min_confidence
        if not shadow_plan_config.emit_all_tiers and not threshold_met:
            continue

        reason_codes = [
            "tier_threshold_met" if threshold_met else "below_tier_threshold"
        ]

        actionable = bool(threshold_met)
        if actionable and shadow_plan_config.actionable_tiers:
            if tier.name not in shadow_plan_config.actionable_tiers:
                actionable = False
                reason_codes.append("excluded_tier")
                
        entry_price_ref = normalized_price_ref
        limit_price = None
        tp_price = None
        sl_price = None

        if is_suppressed:
            actionable = False
            entry_price_ref = None
            reason_codes.append(
                f"entry_verdict:{str(verdict.entry_verdict).lower()}"
            )
            if verdict.suppression_code:
                reason_codes.append(str(verdict.suppression_code))
        elif normalized_price_ref is None:
            actionable = False
            entry_price_ref = None
            reason_codes.append("no_valid_price_ref")
        else:
            limit_price = _derive_limit_price(
                entry_side=entry_side,
                price_ref=normalized_price_ref,
                limit_offset_bps=tier.limit_offset_bps,
            )
            tp_price, sl_price = _derive_tp_sl_prices(
                entry_side=entry_side,
                limit_price=limit_price,
                tp_offset_pct=tier.tp_offset_pct,
                sl_offset_pct=tier.sl_offset_pct,
            )

        plans.append(
            ShadowEntryPlan(
                plan_id=f"sep_{tier.name}_{verdict.symbol}_{verdict.ts_ms}",
                source_verdict_id=verdict.verdict_id,
                source_envelope_id=verdict.envelope_id,
                symbol=verdict.symbol,
                tf_sec=verdict.tf_sec,
                ts_ms=verdict.ts_ms,
                cycle_key=verdict.cycle_key,
                authority_mode="shadow",
                applied=False,
                shadow_only=True,
                final_entry_verdict=verdict.entry_verdict,
                suppressed=is_suppressed,
                suppression_reason=base_suppression_reason,
                entry_side=entry_side,
                confidence=verdict.confidence,
                confidence_tier=tier.name,
                tier_min_confidence=tier.min_confidence,
                actionable=actionable,
                entry_price_ref=entry_price_ref,
                limit_offset_bps=tier.limit_offset_bps,
                limit_price=limit_price,
                tp_price=tp_price,
                sl_price=sl_price,
                tp_offset_pct=tier.tp_offset_pct,
                sl_offset_pct=tier.sl_offset_pct,
                risk_reward=tier.tp_offset_pct / tier.sl_offset_pct,
                entry_order_type="HYPOTHETICAL_LIMIT",
                plan_reason_codes=reason_codes,
                strategy_id=verdict.strategy_id,
                schema_version="1",
            )
        )

    return plans


def write_jsonl_shadow_entry_plan_log(
    plan: ShadowEntryPlan,
    log_dir: str,
) -> None:
    """Append one shadow entry plan to its JSONL log file."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = utc_day_from_ts_ms(plan.ts_ms)
    filename = f"shadow_entry_plan_{plan.symbol}_{date_str}.jsonl"
    filepath = log_path / filename

    line = plan.model_dump_json()
    try:
        with open(filepath, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        LOG.exception("Failed to write shadow entry plan log to %s", filepath)
