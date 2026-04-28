import json
from pathlib import Path

import pytest
from jsonschema import Draft7Validator

from apps.reference.domains.alpha_search.judge.config_models import (
    ConfidenceLadderTier,
    ShadowPlanConfig,
)
from apps.reference.domains.alpha_search.judge.contracts import (
    JudgeVerdict,
    ShadowEntryPlan,
)
from apps.reference.domains.alpha_search.judge.shadow_entry_plan import (
    derive_shadow_entry_plans,
    write_jsonl_shadow_entry_plan_log,
)

SCHEMA_PATH = Path(
    "apps/reference/domains/alpha_search/judge/schemas/shadow_entry_plan_v1.json"
)


def _load_schema() -> dict:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _make_shadow_plan_config(*, emit_all_tiers: bool = True) -> ShadowPlanConfig:
    return ShadowPlanConfig(
        enabled=True,
        emit_all_tiers=emit_all_tiers,
        confidence_ladder=[
            ConfidenceLadderTier(
                name="low",
                min_confidence=0.20,
                limit_offset_bps=0,
                tp_offset_pct=0.010,
                sl_offset_pct=0.006,
            ),
            ConfidenceLadderTier(
                name="medium",
                min_confidence=0.35,
                limit_offset_bps=3,
                tp_offset_pct=0.015,
                sl_offset_pct=0.008,
            ),
            ConfidenceLadderTier(
                name="high",
                min_confidence=0.50,
                limit_offset_bps=5,
                tp_offset_pct=0.020,
                sl_offset_pct=0.010,
            ),
        ],
    )


def _make_verdict(**overrides) -> JudgeVerdict:
    payload = dict(
        verdict_id="vrd_entry_BTCUSDT_1712000000300",
        envelope_id="env_entry_BTCUSDT_1712000000200",
        chamber_id="ch_entry_BTCUSDT_1712000000100",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1712000000300,
        verdict_scope="ENTRY",
        entry_verdict="OPEN_LONG",
        lifecycle_verdict=None,
        suppression_reason=None,
        suppression_code=None,
        confidence=0.42,
        reasoning=["chamber_consensus:LONG"],
        dissent_noted=False,
        authority_mode="shadow",
        applied=False,
        strategy_id="aurora",
        schema_version="1",
    )
    payload.update(overrides)
    return JudgeVerdict(**payload)


def _make_plan(**overrides) -> ShadowEntryPlan:
    payload = dict(
        plan_id="sep_low_BTCUSDT_1712000000300",
        source_verdict_id="vrd_entry_BTCUSDT_1712000000300",
        source_envelope_id="env_entry_BTCUSDT_1712000000200",
        symbol="BTCUSDT",
        tf_sec=300,
        ts_ms=1712000000300,
        authority_mode="shadow",
        applied=False,
        shadow_only=True,
        final_entry_verdict="OPEN_LONG",
        suppressed=False,
        suppression_reason=None,
        entry_side="BUY",
        confidence=0.42,
        confidence_tier="low",
        tier_min_confidence=0.20,
        actionable=True,
        entry_price_ref=100.0,
        limit_offset_bps=0,
        limit_price=100.0,
        tp_price=101.0,
        sl_price=99.4,
        tp_offset_pct=0.010,
        sl_offset_pct=0.006,
        risk_reward=1.6666666666666667,
        entry_order_type="HYPOTHETICAL_LIMIT",
        plan_reason_codes=["tier_threshold_met"],
        strategy_id="aurora",
        schema_version="1",
    )
    payload.update(overrides)
    return ShadowEntryPlan(**payload)


class TestShadowEntryPlanContract:
    def test_valid_buy_plan_passes_validation(self):
        plan = _make_plan()
        assert plan.entry_side == "BUY"
        assert plan.cycle_key == "ENTRY:BTCUSDT:300:1712000000300"

    def test_valid_sell_plan_passes_validation(self):
        plan = _make_plan(
            plan_id="sep_medium_BTCUSDT_1712000000300",
            final_entry_verdict="OPEN_SHORT",
            entry_side="SELL",
            confidence_tier="medium",
            tier_min_confidence=0.35,
            limit_offset_bps=3,
            limit_price=100.03,
            tp_price=98.52955,
            sl_price=100.83024,
            tp_offset_pct=0.015,
            sl_offset_pct=0.008,
            risk_reward=1.875,
        )
        assert plan.entry_side == "SELL"

    def test_shadow_only_false_rejected(self):
        with pytest.raises(ValueError, match="shadow_only must be True"):
            _make_plan(shadow_only=False)

    def test_applied_true_rejected(self):
        with pytest.raises(ValueError, match="applied must be False"):
            _make_plan(applied=True)

    def test_authority_mode_not_shadow_rejected(self):
        with pytest.raises(ValueError, match="authority_mode must be 'shadow'"):
            _make_plan(authority_mode="off")

    def test_suppressed_plan_with_non_null_prices_rejected(self):
        with pytest.raises(ValueError, match="requires entry_price_ref/price fields to be null"):
            _make_plan(
                final_entry_verdict="NO_ENTRY",
                suppressed=True,
                entry_side=None,
                entry_price_ref=100.0,
                limit_price=100.0,
                tp_price=101.0,
                sl_price=99.4,
            )


class TestShadowEntryPlanDerivation:
    def test_open_long_derives_buy_side_and_prices(self):
        verdict = _make_verdict(entry_verdict="OPEN_LONG", confidence=0.42)
        plans = derive_shadow_entry_plans(
            verdict,
            price_ref=100.0,
            shadow_plan_config=_make_shadow_plan_config(),
        )
        assert [plan.confidence_tier for plan in plans] == [
            "low", "medium", "high"]
        assert [plan.actionable for plan in plans] == [True, True, False]
        assert all(plan.entry_side == "BUY" for plan in plans)
        assert plans[0].limit_price == pytest.approx(100.0)
        assert plans[0].tp_price == pytest.approx(101.0)
        assert plans[0].sl_price == pytest.approx(99.4)
        assert plans[1].limit_price == pytest.approx(99.97)
        assert plans[1].tp_price == pytest.approx(101.46955)
        assert plans[1].sl_price == pytest.approx(99.17024)
        assert plans[2].limit_price == pytest.approx(99.95)
        assert plans[2].tp_price == pytest.approx(101.949)
        assert plans[2].sl_price == pytest.approx(98.9505)

    def test_open_short_derives_sell_side_and_inverted_prices(self):
        verdict = _make_verdict(entry_verdict="OPEN_SHORT", confidence=0.55)
        plans = derive_shadow_entry_plans(
            verdict,
            price_ref=100.0,
            shadow_plan_config=_make_shadow_plan_config(),
        )
        assert all(plan.entry_side == "SELL" for plan in plans)
        assert all(plan.actionable is True for plan in plans)
        assert plans[0].limit_price == pytest.approx(100.0)
        assert plans[0].tp_price == pytest.approx(99.0)
        assert plans[0].sl_price == pytest.approx(100.6)
        assert plans[1].limit_price == pytest.approx(100.03)
        assert plans[1].tp_price == pytest.approx(98.52955)
        assert plans[1].sl_price == pytest.approx(100.83024)
        assert plans[2].limit_price == pytest.approx(100.05)
        assert plans[2].tp_price == pytest.approx(98.049)
        assert plans[2].sl_price == pytest.approx(101.0505)

    def test_no_entry_is_suppressed_with_null_prices(self):
        verdict = _make_verdict(entry_verdict="NO_ENTRY")
        plans = derive_shadow_entry_plans(
            verdict,
            price_ref=100.0,
            shadow_plan_config=_make_shadow_plan_config(),
        )
        assert all(plan.suppressed is True for plan in plans)
        assert all(plan.entry_side is None for plan in plans)
        assert all(plan.entry_price_ref is None for plan in plans)
        assert all(plan.limit_price is None for plan in plans)

    def test_suppress_verdict_uses_suppression_reason(self):
        verdict = _make_verdict(
            entry_verdict="SUPPRESS",
            suppression_reason="entry_chamber_inadmissible:scope_mismatch",
            suppression_code="ENTRY_CHAMBER_SCOPE_MISMATCH",
        )
        plans = derive_shadow_entry_plans(
            verdict,
            price_ref=100.0,
            shadow_plan_config=_make_shadow_plan_config(),
        )
        assert all(plan.suppression_reason ==
                   "entry_chamber_inadmissible:scope_mismatch" for plan in plans)
        assert all(
            "ENTRY_CHAMBER_SCOPE_MISMATCH" in plan.plan_reason_codes for plan in plans)

    def test_unknown_verdict_is_suppressed(self):
        verdict = _make_verdict(entry_verdict="UNKNOWN", confidence=0.0)
        plans = derive_shadow_entry_plans(
            verdict,
            price_ref=100.0,
            shadow_plan_config=_make_shadow_plan_config(),
        )
        assert all(plan.suppressed is True for plan in plans)
        assert all(plan.suppression_reason ==
                   "entry_verdict:unknown" for plan in plans)

    def test_emit_all_tiers_false_only_returns_qualifying_tiers(self):
        verdict = _make_verdict(confidence=0.42)
        plans = derive_shadow_entry_plans(
            verdict,
            price_ref=100.0,
            shadow_plan_config=_make_shadow_plan_config(emit_all_tiers=False),
        )
        assert [plan.confidence_tier for plan in plans] == ["low", "medium"]

    def test_emit_all_tiers_true_marks_non_qualifying_tier_non_actionable(self):
        verdict = _make_verdict(confidence=0.42)
        plans = derive_shadow_entry_plans(
            verdict,
            price_ref=100.0,
            shadow_plan_config=_make_shadow_plan_config(emit_all_tiers=True),
        )
        assert [plan.actionable for plan in plans] == [True, True, False]
        assert "below_tier_threshold" in plans[2].plan_reason_codes

    def test_price_ref_none_nulls_prices_and_marks_non_actionable(self):
        verdict = _make_verdict(confidence=0.42)
        plans = derive_shadow_entry_plans(
            verdict,
            price_ref=None,
            shadow_plan_config=_make_shadow_plan_config(),
        )
        assert all(plan.entry_price_ref is None for plan in plans)
        assert all(plan.limit_price is None for plan in plans)
        assert all(plan.actionable is False for plan in plans)
        assert all(
            "no_valid_price_ref" in plan.plan_reason_codes for plan in plans)

    def test_price_ref_zero_nulls_prices(self):
        verdict = _make_verdict(confidence=0.42)
        plans = derive_shadow_entry_plans(
            verdict,
            price_ref=0.0,
            shadow_plan_config=_make_shadow_plan_config(),
        )
        assert all(plan.entry_price_ref is None for plan in plans)
        assert all(plan.limit_price is None for plan in plans)
        assert all(
            "no_valid_price_ref" in plan.plan_reason_codes for plan in plans)

    def test_confidence_exactly_at_tier_boundary_is_actionable(self):
        verdict = _make_verdict(confidence=0.35)
        plans = derive_shadow_entry_plans(
            verdict,
            price_ref=100.0,
            shadow_plan_config=_make_shadow_plan_config(),
        )
        by_tier = {plan.confidence_tier: plan for plan in plans}
        assert by_tier["medium"].actionable is True
        assert by_tier["high"].actionable is False

    def test_cycle_key_propagates_from_verdict(self):
        verdict = _make_verdict()
        plans = derive_shadow_entry_plans(
            verdict,
            price_ref=100.0,
            shadow_plan_config=_make_shadow_plan_config(),
        )
        assert all(plan.cycle_key == verdict.cycle_key for plan in plans)

    def test_risk_reward_matches_tp_sl_ratio(self):
        verdict = _make_verdict()
        plans = derive_shadow_entry_plans(
            verdict,
            price_ref=100.0,
            shadow_plan_config=_make_shadow_plan_config(),
        )
        assert plans[0].risk_reward == pytest.approx(0.010 / 0.006)
        assert plans[1].risk_reward == pytest.approx(0.015 / 0.008)
        assert plans[2].risk_reward == pytest.approx(0.020 / 0.010)


class TestShadowEntryPlanSchema:
    def test_model_dump_passes_json_schema(self):
        schema = _load_schema()
        validator = Draft7Validator(schema)
        validator.validate(_make_plan().model_dump())

    def test_extra_field_rejected_by_json_schema(self):
        schema = _load_schema()
        validator = Draft7Validator(schema)
        payload = _make_plan().model_dump()
        payload["extra_field"] = "bad"
        with pytest.raises(Exception):
            validator.validate(payload)


class TestShadowEntryPlanJsonl:
    def test_write_and_read_roundtrip(self, tmp_path):
        plan = _make_plan()
        write_jsonl_shadow_entry_plan_log(plan, str(tmp_path))

        written_files = list(tmp_path.glob(
            "shadow_entry_plan_BTCUSDT_*.jsonl"))
        assert len(written_files) == 1

        line = written_files[0].read_text(encoding="utf-8").strip()
        restored = ShadowEntryPlan.model_validate_json(line)
        assert restored == plan
