from __future__ import annotations

from .exit_policies import sidecar_only_exit, tp_sl_only_exit
from .gates import evaluate_gate_chain
from .models import CanonicalEntry, GateDecision, ScenarioRuntime, ScenarioSpec


def _allow_all(_: CanonicalEntry, __: ScenarioRuntime) -> GateDecision:
    return GateDecision(
        allowed=True,
        gate_id="ALLOW_ALL",
        reason="ALLOW",
        detail="scenario_has_no_entry_filters",
        support_quality="not_applicable",
    )


def _gate_filter(*gate_ids: str):
    gate_tuple = tuple(gate_ids)

    def _inner(entry: CanonicalEntry, runtime: ScenarioRuntime) -> GateDecision:
        return evaluate_gate_chain(entry, runtime, gate_tuple)

    return _inner


def build_scenario_registry() -> dict[str, ScenarioSpec]:
    return {
        "tp_sl_only": ScenarioSpec(
            id="tp_sl_only",
            entry_filter=_allow_all,
            exit_policy=tp_sl_only_exit,
            required_surfaces=("order_log_v1.jsonl", "1m_candles", "aurora_tpsl_config"),
            report_contract="Pure TP/SL replay with no alternate close logic.",
        ),
        "nrr026_only": ScenarioSpec(
            id="nrr026_only",
            entry_filter=_gate_filter("NRR026"),
            exit_policy=tp_sl_only_exit,
            required_surfaces=("order_log_v1.jsonl", "1m_candles", "directional_sanity_config"),
            report_contract="TP/SL replay with only counterfactual NRR026 enforced.",
        ),
        "nrr027_only": ScenarioSpec(
            id="nrr027_only",
            entry_filter=_gate_filter("NRR027"),
            exit_policy=tp_sl_only_exit,
            required_surfaces=("order_log_v1.jsonl", "1m_candles", "directional_sanity_config"),
            report_contract="TP/SL replay with only counterfactual NRR027 enforced.",
        ),
        "nrr028_only": ScenarioSpec(
            id="nrr028_only",
            entry_filter=_gate_filter("NRR028"),
            exit_policy=tp_sl_only_exit,
            required_surfaces=("order_log_v1.jsonl", "1m_candles", "price_motion_sanity_config"),
            report_contract="TP/SL replay with only counterfactual NRR028 enforced.",
        ),
        "nrr029_only": ScenarioSpec(
            id="nrr029_only",
            entry_filter=_gate_filter("NRR029"),
            exit_policy=tp_sl_only_exit,
            required_surfaces=("order_log_v1.jsonl", "1m_candles", "price_motion_sanity_config"),
            report_contract="TP/SL replay with only counterfactual NRR029 enforced.",
        ),
        "nrr030_only": ScenarioSpec(
            id="nrr030_only",
            entry_filter=_gate_filter("NRR030"),
            exit_policy=tp_sl_only_exit,
            required_surfaces=("order_log_v1.jsonl", "1m_candles", "price_motion_sanity_config"),
            report_contract="TP/SL replay with only counterfactual NRR030 enforced.",
        ),
        "nrr027_030_no_regime_flip": ScenarioSpec(
            id="nrr027_030_no_regime_flip",
            entry_filter=_gate_filter("NRR027", "NRR028", "NRR029", "NRR030"),
            exit_policy=tp_sl_only_exit,
            required_surfaces=("order_log_v1.jsonl", "1m_candles", "directional_and_price_motion_config"),
            report_contract="TP/SL replay with NRR027..030 only and regime-flip exits explicitly disabled.",
            allow_regime_flip_exits=False,
        ),
        "sidecar_only": ScenarioSpec(
            id="sidecar_only",
            entry_filter=_allow_all,
            exit_policy=sidecar_only_exit,
            required_surfaces=("order_log_v1.jsonl", "trade_lifecycle.jsonl", "1m_candles"),
            report_contract="Pure sidecar exit replay using recorded sidecar request surfaces only.",
            allow_regime_flip_exits=False,
        ),
    }
